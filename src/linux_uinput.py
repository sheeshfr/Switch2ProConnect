# Switch2ProConnect - Linux uinput Virtual Gamepad, Mouse, and Keyboard Driver
# Copyright (C) 2026 Switch2ProConnect Contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Linux /dev/uinput virtual controller backend using python-evdev.

Provides drop-in replacements for ViGEmBus and WinUHid on Linux:
- UInputXboxGamepad: Emulates Xbox 360 controller with analog sticks, triggers,
  D-pad, buttons, and force feedback (FF_RUMBLE).
- UInputDS4Gamepad: Emulates DualShock 4 controller.
- UInputMouse & UInputKeyboard: Virtual mouse and keyboard for gyro-to-mouse,
  IR mouse, and back-paddle macro keystrokes.
- EvdevDeviceGrabber: Native Linux exclusive device grabbing (EVIOCGRAB) to
  replace HidHide and prevent double-input in games and Steam.
- win32_compat: Shims win32api/win32con on non-Windows platforms.
"""

import sys
import os
import time
import math
import select
import logging
import threading
import ctypes
from types import ModuleType

logger = logging.getLogger(__name__)

try:
    import evdev
    from evdev import ecodes, UInput, AbsInfo, InputDevice
    EVDEV_AVAILABLE = True
except ImportError:
    evdev = None
    ecodes = None
    UInput = None
    AbsInfo = None
    InputDevice = None
    EVDEV_AVAILABLE = False
    if sys.platform != "win32":
        logger.warning("evdev module not found. Install it with: pip install evdev")


# ============================================================================
# Win32 API Compatibility Layer for Linux
# ============================================================================

class _Win32ConShim:
    """Provides Windows virtual key and mouse event constants on Linux."""
    # Mouse events
    MOUSEEVENTF_MOVE = 0x0001
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    MOUSEEVENTF_RIGHTDOWN = 0x0008
    MOUSEEVENTF_RIGHTUP = 0x0010
    MOUSEEVENTF_MIDDLEDOWN = 0x0020
    MOUSEEVENTF_MIDDLEUP = 0x0040
    MOUSEEVENTF_WHEEL = 0x0800
    MOUSEEVENTF_HWHEEL = 0x1000

    # Keyboard events
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_EXTENDEDKEY = 0x0001

    # Virtual key codes
    VK_LBUTTON = 0x01
    VK_RBUTTON = 0x02
    VK_MBUTTON = 0x04
    VK_XBUTTON1 = 0x05
    VK_XBUTTON2 = 0x06
    VK_BACK = 0x08
    VK_TAB = 0x09
    VK_RETURN = 0x0D
    VK_SHIFT = 0x10
    VK_CONTROL = 0x11
    VK_MENU = 0x12
    VK_PAUSE = 0x13
    VK_CAPITAL = 0x14
    VK_ESCAPE = 0x1B
    VK_SPACE = 0x20
    VK_PRIOR = 0x21
    VK_NEXT = 0x22
    VK_END = 0x23
    VK_HOME = 0x24
    VK_LEFT = 0x25
    VK_UP = 0x26
    VK_RIGHT = 0x27
    VK_DOWN = 0x28
    VK_SNAPSHOT = 0x2C
    VK_INSERT = 0x2D
    VK_DELETE = 0x2E
    VK_VOLUME_MUTE = 0xAD
    VK_VOLUME_DOWN = 0xAE
    VK_VOLUME_UP = 0xAF
    VK_MEDIA_NEXT_TRACK = 0xB0
    VK_MEDIA_PREV_TRACK = 0xB1
    VK_MEDIA_STOP = 0xB2
    VK_MEDIA_PLAY_PAUSE = 0xB3


class _Win32ApiShim:
    """Routes Windows mouse and keyboard API calls to Linux uinput devices."""
    @staticmethod
    def GetCursorPos():
        return (0, 0)

    @staticmethod
    def GetAsyncKeyState(vk_code):
        return 0

    @staticmethod
    def mouse_event(flags, dx, dy, data=0, extra_info=0):
        mouse = get_uinput_mouse()
        if mouse is not None:
            mouse.emit_event(flags, dx, dy, data)

    @staticmethod
    def keybd_event(vk_code, scan_code=0, flags=0, extra_info=0):
        kbd = get_uinput_keyboard()
        if kbd is not None:
            kbd.emit_key(vk_code, bool(flags & _Win32ConShim.KEYEVENTF_KEYUP))


class _Win32GuiShim:
    @staticmethod
    def GetWindowRect(hwnd):
        return (0, 0, 1920, 1080)

    @staticmethod
    def GetClientRect(hwnd):
        return (0, 0, 1920, 1080)

    @staticmethod
    def SetWindowPos(*args, **kwargs):
        return 1

    @staticmethod
    def MoveWindow(*args, **kwargs):
        return 1

    @staticmethod
    def RegisterWindowMessage(*args, **kwargs):
        return 0

    class WNDCLASS:
        def __init__(self):
            self.lpfnWndProc = None
            self.lpszClassName = ""

    @staticmethod
    def GetModuleHandle(*args, **kwargs):
        return 0

    @staticmethod
    def RegisterClass(*args, **kwargs):
        return 0

    @staticmethod
    def CreateWindow(*args, **kwargs):
        return 0

    @staticmethod
    def PumpMessages():
        pass

    @staticmethod
    def DefWindowProc(*args, **kwargs):
        return 0

    @staticmethod
    def PostMessage(*args, **kwargs):
        return 1

    @staticmethod
    def UnregisterClass(*args, **kwargs):
        pass

    @staticmethod
    def DestroyWindow(*args, **kwargs):
        pass

    @staticmethod
    def PostQuitMessage(*args, **kwargs):
        pass


class _Win32ProcessShim:
    @staticmethod
    def GetWindowThreadProcessId(hwnd, *args):
        return (0, 0)


def install_win32_shims():
    """Injects win32api, win32con, win32gui, win32process, winreg and ctypes.windll shims if not on Windows."""
    if sys.platform != "win32":
        if "win32con" not in sys.modules:
            mod_con = ModuleType("win32con")
            for k, v in _Win32ConShim.__dict__.items():
                if not k.startswith("_"):
                    setattr(mod_con, k, v)
            sys.modules["win32con"] = mod_con

        if "win32api" not in sys.modules:
            mod_api = ModuleType("win32api")
            for k, v in _Win32ApiShim.__dict__.items():
                if not k.startswith("_"):
                    setattr(mod_api, k, staticmethod(v) if callable(v) else v)
            sys.modules["win32api"] = mod_api

        if "win32gui" not in sys.modules:
            mod_gui = ModuleType("win32gui")
            for k, v in _Win32GuiShim.__dict__.items():
                if not k.startswith("_"):
                    setattr(mod_gui, k, v)
            sys.modules["win32gui"] = mod_gui

        if "win32process" not in sys.modules:
            mod_proc = ModuleType("win32process")
            for k, v in _Win32ProcessShim.__dict__.items():
                if not k.startswith("_"):
                    setattr(mod_proc, k, staticmethod(v) if callable(v) else v)
            sys.modules["win32process"] = mod_proc

        if "winreg" not in sys.modules:
            mod_reg = ModuleType("winreg")
            mod_reg.HKEY_CURRENT_USER = 1
            mod_reg.KEY_SET_VALUE = 2
            mod_reg.REG_SZ = 1
            mod_reg.OpenKey = lambda *args, **kwargs: None
            mod_reg.SetValueEx = lambda *args, **kwargs: None
            mod_reg.DeleteValue = lambda *args, **kwargs: None
            mod_reg.CloseKey = lambda *args, **kwargs: None
            sys.modules["winreg"] = mod_reg

        if not hasattr(ctypes, "windll"):
            class _DummyFunc:
                def __init__(self, name=""):
                    self.argtypes = []
                    self.restype = ctypes.c_int

                def __call__(self, *args, **kwargs):
                    return 0

            class _DummyDll:
                def __getattr__(self, name):
                    return _DummyFunc(name)

            class _DummyWindll:
                def __getattr__(self, name):
                    return _DummyDll()

            ctypes.windll = _DummyWindll()

        if not hasattr(ctypes, "WINFUNCTYPE"):
            ctypes.WINFUNCTYPE = ctypes.CFUNCTYPE


# Automatically install shims on non-Windows platforms
if sys.platform != "win32":
    install_win32_shims()



# ============================================================================
# Virtual Xbox 360 Gamepad (evdev /dev/uinput)
# ============================================================================

# XInput button bitmask mapping to Linux evdev event codes
XUSB_BUTTON_TO_EVDEV = [
    (0x0010, "BTN_START"),
    (0x0020, "BTN_SELECT"),
    (0x0040, "BTN_THUMBL"),
    (0x0080, "BTN_THUMBR"),
    (0x0100, "BTN_TL"),
    (0x0200, "BTN_TR"),
    (0x0400, "BTN_MODE"),
    (0x1000, "BTN_A"),
    (0x2000, "BTN_B"),
    (0x4000, "BTN_X"),
    (0x8000, "BTN_Y"),
]


class UInputXboxGamepad:
    """Virtual Xbox 360 gamepad for Linux via /dev/uinput.

    Exposes the exact same interface expected by VirtualController:
    set_buttons(), left_trigger(), right_trigger(), left_joystick_float(),
    right_joystick_float(), update(), and register_notification().
    """

    def __init__(self, name="Microsoft X-Box 360 pad"):
        if not EVDEV_AVAILABLE:
            raise RuntimeError("python-evdev is required for Linux uinput gamepad emulation.")

        self.name = name
        self._buttons = 0
        self._lt = 0
        self._rt = 0
        self._lx = 0
        self._ly = 0
        self._rx = 0
        self._ry = 0
        self._dpad_x = 0
        self._dpad_y = 0

        self._notification_callback = None
        self._ff_effects = {}
        self._running = True
        self._lock = threading.Lock()

        # Define Xbox 360 capabilities
        capabilities = {
            ecodes.EV_KEY: [
                ecodes.BTN_A, ecodes.BTN_B, ecodes.BTN_X, ecodes.BTN_Y,
                ecodes.BTN_TL, ecodes.BTN_TR,
                ecodes.BTN_SELECT, ecodes.BTN_START, ecodes.BTN_MODE,
                ecodes.BTN_THUMBL, ecodes.BTN_THUMBR,
            ],
            ecodes.EV_ABS: [
                (ecodes.ABS_X, AbsInfo(value=0, min=-32768, max=32767, fuzz=16, flat=128, resolution=0)),
                (ecodes.ABS_Y, AbsInfo(value=0, min=-32768, max=32767, fuzz=16, flat=128, resolution=0)),
                (ecodes.ABS_RX, AbsInfo(value=0, min=-32768, max=32767, fuzz=16, flat=128, resolution=0)),
                (ecodes.ABS_RY, AbsInfo(value=0, min=-32768, max=32767, fuzz=16, flat=128, resolution=0)),
                (ecodes.ABS_Z, AbsInfo(value=0, min=0, max=255, fuzz=0, flat=0, resolution=0)),       # LT
                (ecodes.ABS_RZ, AbsInfo(value=0, min=0, max=255, fuzz=0, flat=0, resolution=0)),      # RT
                (ecodes.ABS_HAT0X, AbsInfo(value=0, min=-1, max=1, fuzz=0, flat=0, resolution=0)),    # Dpad X
                (ecodes.ABS_HAT0Y, AbsInfo(value=0, min=-1, max=1, fuzz=0, flat=0, resolution=0)),    # Dpad Y
            ],
            ecodes.EV_FF: [
                ecodes.FF_RUMBLE,
                ecodes.FF_PERIODIC,
                ecodes.FF_GAIN,
            ]
        }

        try:
            self.ui = UInput(
                events=capabilities,
                name=self.name,
                vendor=0x045E,
                product=0x028E,
                version=0x0114,
                bustype=ecodes.BUS_USB
            )
            logger.info("Created Linux uinput Xbox 360 controller: %s", self.ui.device.path if hasattr(self.ui, 'device') else self.name)
        except PermissionError:
            logger.error("Permission denied creating /dev/uinput device. Check udev rules or run with uaccess tag.")
            raise

        # Background thread to receive force-feedback rumble events
        self._ff_thread = threading.Thread(target=self._ff_listener, name="UInputXboxGamepad-FF", daemon=True)
        self._ff_thread.start()

    def set_buttons(self, xb_btns: int):
        self._buttons = int(xb_btns)
        # Handle D-pad
        dpad_x = 0
        if self._buttons & 0x0004:  # LEFT
            dpad_x = -1
        elif self._buttons & 0x0008:  # RIGHT
            dpad_x = 1

        dpad_y = 0
        if self._buttons & 0x0001:  # UP
            dpad_y = -1
        elif self._buttons & 0x0002:  # DOWN
            dpad_y = 1

        self._dpad_x = dpad_x
        self._dpad_y = dpad_y

    def left_trigger(self, val: int):
        self._lt = max(0, min(255, int(val)))

    def right_trigger(self, val: int):
        self._rt = max(0, min(255, int(val)))

    def left_joystick_float(self, x: float, y: float):
        # Convert float (-1.0 to 1.0) to signed 16-bit (-32768 to 32767)
        self._lx = max(-32768, min(32767, int(x * 32767.0)))
        self._ly = max(-32768, min(32767, int(y * 32767.0)))

    def right_joystick_float(self, x: float, y: float):
        self._rx = max(-32768, min(32767, int(x * 32767.0)))
        self._ry = max(-32768, min(32767, int(y * 32767.0)))

    def update(self):
        """Batch-write axes and buttons, then send SYN_REPORT."""
        try:
            # Buttons
            for mask, btn_name in XUSB_BUTTON_TO_EVDEV:
                code = getattr(ecodes, btn_name)
                is_down = 1 if (self._buttons & mask) else 0
                self.ui.write(ecodes.EV_KEY, code, is_down)

            # D-pad (as ABS_HAT0X and ABS_HAT0Y)
            self.ui.write(ecodes.EV_ABS, ecodes.ABS_HAT0X, self._dpad_x)
            self.ui.write(ecodes.EV_ABS, ecodes.ABS_HAT0Y, self._dpad_y)

            # Sticks
            self.ui.write(ecodes.EV_ABS, ecodes.ABS_X, self._lx)
            self.ui.write(ecodes.EV_ABS, ecodes.ABS_Y, self._ly)
            self.ui.write(ecodes.EV_ABS, ecodes.ABS_RX, self._rx)
            self.ui.write(ecodes.EV_ABS, ecodes.ABS_RY, self._ry)

            # Triggers
            self.ui.write(ecodes.EV_ABS, ecodes.ABS_Z, self._lt)
            self.ui.write(ecodes.EV_ABS, ecodes.ABS_RZ, self._rt)

            # Commit frame
            self.ui.syn()
            return True
        except Exception as e:
            logger.debug("Error updating uinput Xbox controller: %s", e)
            return False

    def reset(self):
        self._buttons = 0
        self._lt = 0
        self._rt = 0
        self._lx = 0
        self._ly = 0
        self._rx = 0
        self._ry = 0
        self._dpad_x = 0
        self._dpad_y = 0
        self.update()

    def register_notification(self, callback_function):
        self._notification_callback = callback_function

    def unregister_notification(self):
        self._notification_callback = None

    def _ff_listener(self):
        """Monitors /dev/uinput for force-feedback rumble events from games."""
        while self._running:
            try:
                r, _, _ = select.select([self.ui.fileno()], [], [], 0.1)
                if not r:
                    continue

                for event in self.ui.read():
                    if event.type == ecodes.EV_UINPUT:
                        if event.code == ecodes.UI_FF_UPLOAD:
                            upload = self.ui.begin_upload(event.value)
                            # Store rumble magnitudes
                            if hasattr(upload, "effect"):
                                eff = upload.effect
                                if eff.type == ecodes.FF_RUMBLE:
                                    strong = eff.u.ff_rumble_effect.strong_magnitude
                                    weak = eff.u.ff_rumble_effect.weak_magnitude
                                    self._ff_effects[eff.id] = (strong, weak)
                            self.ui.end_upload(upload)

                        elif event.code == ecodes.UI_FF_ERASE:
                            erase = self.ui.begin_erase(event.value)
                            self._ff_effects.pop(erase.effect_id, None)
                            self.ui.end_erase(erase)

                    elif event.type == ecodes.EV_FF:
                        effect_id = event.code
                        value = event.value  # value > 0 means start playback, 0 means stop
                        if self._notification_callback is not None:
                            if value > 0 and effect_id in self._ff_effects:
                                strong_16, weak_16 = self._ff_effects[effect_id]
                                large_motor = int((strong_16 / 65535.0) * 255.0)
                                small_motor = int((weak_16 / 65535.0) * 255.0)
                            else:
                                large_motor = 0
                                small_motor = 0
                            try:
                                self._notification_callback(self, None, large_motor, small_motor, 0, None)
                            except Exception as e:
                                logger.debug("FF callback error: %s", e)
            except (OSError, ValueError):
                break
            except Exception as e:
                logger.debug("Exception in uinput FF listener: %s", e)
                time.sleep(0.05)

    def close(self):
        self._running = False
        try:
            if hasattr(self, "ui") and self.ui:
                self.ui.close()
        except Exception:
            pass


# ============================================================================
# Virtual DualShock 4 Gamepad (evdev /dev/uinput)
# ============================================================================

class _DS4ReportShim:
    """Proxy report object matching winuhid.VDS4Gamepad and DS4_REPORT_EX."""
    def __init__(self):
        self.ButtonSquare = 0
        self.ButtonTriangle = 0
        self.ButtonCross = 0
        self.ButtonCircle = 0
        self.ButtonL1 = 0
        self.ButtonR1 = 0
        self.ButtonL2 = 0
        self.ButtonR2 = 0
        self.ButtonShare = 0
        self.ButtonOptions = 0
        self.ButtonThumbL = 0
        self.ButtonThumbR = 0
        self.ButtonHome = 0
        self.Dpad = 8  # 8 is neutral
        self.LeftStickX = 128
        self.LeftStickY = 128
        self.RightStickX = 128
        self.RightStickY = 128
        self.LeftTrigger = 0
        self.RightTrigger = 0
        self.BatteryLevel = 0xAF
        self.BatteryLevelSpecial = 0x08


class UInputDS4Gamepad:
    """Virtual Sony DualShock 4 gamepad for Linux via /dev/uinput."""

    def __init__(self, name="Sony Interactive Entertainment Wireless Controller"):
        if not EVDEV_AVAILABLE:
            raise RuntimeError("python-evdev is required for Linux uinput gamepad emulation.")

        self.name = name
        self.report = _DS4ReportShim()
        self._notification_callback = None
        self._running = True
        self._ff_effects = {}

        capabilities = {
            ecodes.EV_KEY: [
                ecodes.BTN_A, ecodes.BTN_B, ecodes.BTN_X, ecodes.BTN_Y,
                ecodes.BTN_TL, ecodes.BTN_TR, ecodes.BTN_TL2, ecodes.BTN_TR2,
                ecodes.BTN_SELECT, ecodes.BTN_START, ecodes.BTN_MODE,
                ecodes.BTN_THUMBL, ecodes.BTN_THUMBR,
            ],
            ecodes.EV_ABS: [
                (ecodes.ABS_X, AbsInfo(value=128, min=0, max=255, fuzz=0, flat=0, resolution=0)),
                (ecodes.ABS_Y, AbsInfo(value=128, min=0, max=255, fuzz=0, flat=0, resolution=0)),
                (ecodes.ABS_RX, AbsInfo(value=128, min=0, max=255, fuzz=0, flat=0, resolution=0)),
                (ecodes.ABS_RY, AbsInfo(value=128, min=0, max=255, fuzz=0, flat=0, resolution=0)),
                (ecodes.ABS_Z, AbsInfo(value=0, min=0, max=255, fuzz=0, flat=0, resolution=0)),       # L2 analog
                (ecodes.ABS_RZ, AbsInfo(value=0, min=0, max=255, fuzz=0, flat=0, resolution=0)),      # R2 analog
                (ecodes.ABS_HAT0X, AbsInfo(value=0, min=-1, max=1, fuzz=0, flat=0, resolution=0)),
                (ecodes.ABS_HAT0Y, AbsInfo(value=0, min=-1, max=1, fuzz=0, flat=0, resolution=0)),
            ],
            ecodes.EV_FF: [
                ecodes.FF_RUMBLE,
                ecodes.FF_PERIODIC,
                ecodes.FF_GAIN,
            ]
        }

        self.ui = UInput(
            events=capabilities,
            name=self.name,
            vendor=0x054C,
            product=0x05C4,
            version=0x0100,
            bustype=ecodes.BUS_USB
        )
        logger.info("Created Linux uinput DualShock 4 controller.")

    def update(self):
        try:
            r = self.report
            self.ui.write(ecodes.EV_KEY, ecodes.BTN_X, r.ButtonSquare)
            self.ui.write(ecodes.EV_KEY, ecodes.BTN_Y, r.ButtonTriangle)
            self.ui.write(ecodes.EV_KEY, ecodes.BTN_A, r.ButtonCross)
            self.ui.write(ecodes.EV_KEY, ecodes.BTN_B, r.ButtonCircle)
            self.ui.write(ecodes.EV_KEY, ecodes.BTN_TL, r.ButtonL1)
            self.ui.write(ecodes.EV_KEY, ecodes.BTN_TR, r.ButtonR1)
            self.ui.write(ecodes.EV_KEY, ecodes.BTN_TL2, r.ButtonL2)
            self.ui.write(ecodes.EV_KEY, ecodes.BTN_TR2, r.ButtonR2)
            self.ui.write(ecodes.EV_KEY, ecodes.BTN_SELECT, r.ButtonShare)
            self.ui.write(ecodes.EV_KEY, ecodes.BTN_START, r.ButtonOptions)
            self.ui.write(ecodes.EV_KEY, ecodes.BTN_MODE, r.ButtonHome)
            self.ui.write(ecodes.EV_KEY, ecodes.BTN_THUMBL, r.ButtonThumbL)
            self.ui.write(ecodes.EV_KEY, ecodes.BTN_THUMBR, r.ButtonThumbR)

            # D-pad conversion
            dpad_map = {
                0: (0, -1),   # UP
                1: (1, -1),   # UP-RIGHT
                2: (1, 0),    # RIGHT
                3: (1, 1),    # DOWN-RIGHT
                4: (0, 1),    # DOWN
                5: (-1, 1),   # DOWN-LEFT
                6: (-1, 0),   # LEFT
                7: (-1, -1),  # UP-LEFT
            }
            hat_x, hat_y = dpad_map.get(r.Dpad, (0, 0))
            self.ui.write(ecodes.EV_ABS, ecodes.ABS_HAT0X, hat_x)
            self.ui.write(ecodes.EV_ABS, ecodes.ABS_HAT0Y, hat_y)

            # Axes
            self.ui.write(ecodes.EV_ABS, ecodes.ABS_X, r.LeftStickX)
            self.ui.write(ecodes.EV_ABS, ecodes.ABS_Y, r.LeftStickY)
            self.ui.write(ecodes.EV_ABS, ecodes.ABS_RX, r.RightStickX)
            self.ui.write(ecodes.EV_ABS, ecodes.ABS_RY, r.RightStickY)
            self.ui.write(ecodes.EV_ABS, ecodes.ABS_Z, r.LeftTrigger)
            self.ui.write(ecodes.EV_ABS, ecodes.ABS_RZ, r.RightTrigger)

            self.ui.syn()
            return True
        except Exception as e:
            logger.debug("Error updating uinput DS4 controller: %s", e)
            return False

    def reset(self):
        self.report = _DS4ReportShim()
        self.update()

    def register_notification(self, callback_function):
        self._notification_callback = callback_function

    def unregister_notification(self):
        self._notification_callback = None

    def close(self):
        self._running = False
        try:
            if hasattr(self, "ui") and self.ui:
                self.ui.close()
        except Exception:
            pass


# ============================================================================
# Virtual Mouse & Keyboard (evdev /dev/uinput)
# ============================================================================

class UInputMouse:
    """Virtual mouse for gyro cursor and IR mouse on Linux."""

    def __init__(self):
        if not EVDEV_AVAILABLE:
            self.ui = None
            return

        capabilities = {
            ecodes.EV_REL: [
                ecodes.REL_X, ecodes.REL_Y, ecodes.REL_WHEEL, ecodes.REL_HWHEEL
            ],
            ecodes.EV_KEY: [
                ecodes.BTN_LEFT, ecodes.BTN_RIGHT, ecodes.BTN_MIDDLE,
                ecodes.BTN_SIDE, ecodes.BTN_EXTRA
            ]
        }
        try:
            self.ui = UInput(
                events=capabilities,
                name="Switch 2 Virtual Mouse",
                vendor=0x057E,
                product=0x2069,
                bustype=ecodes.BUS_USB
            )
            logger.info("Created Linux uinput Virtual Mouse.")
        except Exception as e:
            logger.error("Failed to create Linux uinput mouse: %s", e)
            self.ui = None

    def emit_event(self, flags, dx, dy, data=0):
        if not self.ui:
            return
        try:
            if flags & _Win32ConShim.MOUSEEVENTF_MOVE:
                if dx != 0:
                    self.ui.write(ecodes.EV_REL, ecodes.REL_X, int(dx))
                if dy != 0:
                    self.ui.write(ecodes.EV_REL, ecodes.REL_Y, int(dy))

            if flags & _Win32ConShim.MOUSEEVENTF_LEFTDOWN:
                self.ui.write(ecodes.EV_KEY, ecodes.BTN_LEFT, 1)
            if flags & _Win32ConShim.MOUSEEVENTF_LEFTUP:
                self.ui.write(ecodes.EV_KEY, ecodes.BTN_LEFT, 0)

            if flags & _Win32ConShim.MOUSEEVENTF_RIGHTDOWN:
                self.ui.write(ecodes.EV_KEY, ecodes.BTN_RIGHT, 1)
            if flags & _Win32ConShim.MOUSEEVENTF_RIGHTUP:
                self.ui.write(ecodes.EV_KEY, ecodes.BTN_RIGHT, 0)

            if flags & _Win32ConShim.MOUSEEVENTF_MIDDLEDOWN:
                self.ui.write(ecodes.EV_KEY, ecodes.BTN_MIDDLE, 1)
            if flags & _Win32ConShim.MOUSEEVENTF_MIDDLEUP:
                self.ui.write(ecodes.EV_KEY, ecodes.BTN_MIDDLE, 0)

            if flags & _Win32ConShim.MOUSEEVENTF_WHEEL:
                self.ui.write(ecodes.EV_REL, ecodes.REL_WHEEL, int(data / 120))
            if flags & _Win32ConShim.MOUSEEVENTF_HWHEEL:
                self.ui.write(ecodes.EV_REL, ecodes.REL_HWHEEL, int(data / 120))

            self.ui.syn()
        except Exception as e:
            logger.debug("Error emitting uinput mouse event: %s", e)

    def press_or_release(self, button, state, prev_state, mouse_x, mouse_y):
        if not self.ui:
            return
        btn_code = ecodes.BTN_LEFT
        if button == _Win32ConShim.MOUSEEVENTF_RIGHTDOWN:
            btn_code = ecodes.BTN_RIGHT
        elif button == _Win32ConShim.MOUSEEVENTF_MIDDLEDOWN:
            btn_code = ecodes.BTN_MIDDLE

        if state and not prev_state:
            self.ui.write(ecodes.EV_KEY, btn_code, 1)
            self.ui.syn()
        elif not state and prev_state:
            self.ui.write(ecodes.EV_KEY, btn_code, 0)
            self.ui.syn()


class UInputKeyboard:
    """Virtual keyboard for back-paddle keystroke macros on Linux."""

    # Map Windows Virtual Key code to Linux evdev KEY code
    VK_TO_EVDEV_KEY = {
        0x08: "KEY_BACKSPACE",
        0x09: "KEY_TAB",
        0x0D: "KEY_ENTER",
        0x10: "KEY_LEFTSHIFT",
        0x11: "KEY_LEFTCTRL",
        0x12: "KEY_LEFTALT",
        0x14: "KEY_CAPSLOCK",
        0x1B: "KEY_ESC",
        0x20: "KEY_SPACE",
        0x21: "KEY_PAGEUP",
        0x22: "KEY_PAGEDOWN",
        0x23: "KEY_END",
        0x24: "KEY_HOME",
        0x25: "KEY_LEFT",
        0x26: "KEY_UP",
        0x27: "KEY_RIGHT",
        0x28: "KEY_DOWN",
        0x2D: "KEY_INSERT",
        0x2E: "KEY_DELETE",
        0xAD: "KEY_MUTE",
        0xAE: "KEY_VOLUMEDOWN",
        0xAF: "KEY_VOLUMEUP",
        0xB0: "KEY_NEXTSONG",
        0xB1: "KEY_PREVIOUSSONG",
        0xB2: "KEY_STOPCD",
        0xB3: "KEY_PLAYPAUSE",
    }

    def __init__(self):
        if not EVDEV_AVAILABLE:
            self.ui = None
            return

        all_keys = [
            getattr(ecodes, name) for name in dir(ecodes) if name.startswith("KEY_")
        ]
        capabilities = {ecodes.EV_KEY: all_keys}
        try:
            self.ui = UInput(
                events=capabilities,
                name="Switch 2 Virtual Keyboard",
                vendor=0x057E,
                product=0x2069,
                bustype=ecodes.BUS_USB
            )
            logger.info("Created Linux uinput Virtual Keyboard.")
        except Exception as e:
            logger.error("Failed to create Linux uinput keyboard: %s", e)
            self.ui = None

    def emit_key(self, vk_code, is_up=False):
        if not self.ui:
            return
        key_name = self.VK_TO_EVDEV_KEY.get(vk_code)
        if not key_name:
            if 0x41 <= vk_code <= 0x5A:  # A-Z
                key_name = f"KEY_{chr(vk_code)}"
            elif 0x30 <= vk_code <= 0x39:  # 0-9
                key_name = f"KEY_{chr(vk_code)}"
            elif 0x70 <= vk_code <= 0x7B:  # F1-F12
                key_name = f"KEY_F{vk_code - 0x6F}"

        if key_name and hasattr(ecodes, key_name):
            code = getattr(ecodes, key_name)
            val = 0 if is_up else 1
            self.ui.write(ecodes.EV_KEY, code, val)
            self.ui.syn()


_GLOBAL_UINPUT_MOUSE = None
_GLOBAL_UINPUT_KEYBOARD = None
_GLOBAL_LOCK = threading.Lock()


def get_uinput_mouse():
    global _GLOBAL_UINPUT_MOUSE
    with _GLOBAL_LOCK:
        if _GLOBAL_UINPUT_MOUSE is None and EVDEV_AVAILABLE and sys.platform != "win32":
            _GLOBAL_UINPUT_MOUSE = UInputMouse()
        return _GLOBAL_UINPUT_MOUSE


def get_uinput_keyboard():
    global _GLOBAL_UINPUT_KEYBOARD
    with _GLOBAL_LOCK:
        if _GLOBAL_UINPUT_KEYBOARD is None and EVDEV_AVAILABLE and sys.platform != "win32":
            _GLOBAL_UINPUT_KEYBOARD = UInputKeyboard()
        return _GLOBAL_UINPUT_KEYBOARD


# ============================================================================
# Linux Native Device Grabber (EVIOCGRAB - Replaces HidHide)
# ============================================================================

class EvdevDeviceGrabber:
    """Grabs physical Nintendo Switch 2 controllers to prevent double-input in games.

    Uses Linux ioctl(fd, EVIOCGRAB, 1) on /dev/input/event* to grant exclusive
    access to this application, completely preventing SDL, Steam, Wine/Proton,
    and native games from seeing duplicate raw controller events.
    """

    NINTENDO_VID = 0x057E
    SWITCH2_PIDS = {
        0x2069,  # Switch 2 Pro Controller
        0x2066,  # Joy-Con 2 (L)
        0x2067,  # Joy-Con 2 (R)
        0x2073,  # NSO GameCube Controller
    }

    def __init__(self):
        self._grabbed_devices = {}
        self._lock = threading.Lock()

    def grab_matching_devices(self):
        """Scans /dev/input/event* and grabs all physical Switch 2 controllers."""
        if not EVDEV_AVAILABLE or sys.platform == "win32":
            return

        with self._lock:
            for path in evdev.list_devices():
                if path in self._grabbed_devices:
                    continue
                try:
                    dev = InputDevice(path)
                    # Check vendor & product
                    if dev.info.vendor == self.NINTENDO_VID and dev.info.product in self.SWITCH2_PIDS:
                        dev.grab()
                        self._grabbed_devices[path] = dev
                        logger.info("Exclusively grabbed physical device %s (%s) to prevent double input.",
                                    path, dev.name)
                except Exception as e:
                    logger.debug("Could not grab %s: %s", path, e)

    def release_device(self, path):
        with self._lock:
            dev = self._grabbed_devices.pop(path, None)
            if dev:
                try:
                    dev.ungrab()
                    dev.close()
                    logger.info("Released physical device %s.", path)
                except Exception:
                    pass

    def release_all(self):
        with self._lock:
            for path, dev in list(self._grabbed_devices.items()):
                try:
                    dev.ungrab()
                    dev.close()
                except Exception:
                    pass
            self._grabbed_devices.clear()


_GLOBAL_GRABBER = None


def get_device_grabber():
    global _GLOBAL_GRABBER
    if _GLOBAL_GRABBER is None:
        _GLOBAL_GRABBER = EvdevDeviceGrabber()
    return _GLOBAL_GRABBER
