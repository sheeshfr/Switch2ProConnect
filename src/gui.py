# Switch2Connect - A Python and ESP32-S3 bridge utility for Switch 2 controller inputs.
# Copyright (C) 2026 TommyWabg
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# Contact Information:
# Electronic Mail: tommyw9318@gmail.com

import sys
import os
import ctypes

# If running without console (noconsole), ensure sys.stdout and sys.stderr are valid
# to prevent crashes from any module calling print() or logging to stderr
if sys.stdout is None:
    try:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    except Exception:
        pass
if sys.stderr is None:
    try:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    except Exception:
        pass

try:
    import traceback
    def _app_excepthook(exc_type, exc_value, exc_tb):
        try:
            log_dir = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))
            crash_path = os.path.join(log_dir, "crash.log")
            with open(crash_path, "a", encoding="utf-8") as f:
                import time
                f.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Unhandled exception:\n")
                traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
        except Exception:
            pass
        sys.__excepthook__(exc_type, exc_value, exc_tb)
    sys.excepthook = _app_excepthook
except Exception:
    pass

if __name__ == "__main__":
    # Single-Instance Enforcement
    _SINGLE_INSTANCE_MUTEX_NAME = "Global\\Switch2ProConnect_ShFr_UI_Mod_SingleInstance"
    try:
        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32
        ERROR_ALREADY_EXISTS = 183

        _app_instance_mutex = kernel32.CreateMutexW(None, True, _SINGLE_INSTANCE_MUTEX_NAME)
        if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            try:
                msg_id = user32.RegisterWindowMessageW("Switch2ProConnect_ShowWindow_Message")
                if msg_id:
                    HWND_BROADCAST = 0xFFFF
                    user32.PostMessageW(HWND_BROADCAST, msg_id, 0, 0)
            except Exception:
                pass

            for title in (
                "Switch 2 Pro Connect",
                "Switch 2 Connect (ShFr UI Mod)",
                "Switch 2 Connect (SheeshFr Modded)",
                "Switch 2 Connect",
            ):
                hwnd = user32.FindWindowW(None, title)
                if hwnd:
                    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                    user32.SetForegroundWindow(hwnd)
                    break

            if _app_instance_mutex:
                kernel32.CloseHandle(_app_instance_mutex)
            sys.exit(0)
    except Exception:
        pass

import queue
import time
import json
import webbrowser
import threading
import weakref
import tkinter as tk
from tkinter import filedialog, ttk
import tkinter.font as tkFont
import yaml
import logging
import asyncio
import os
import re
import ctypes
import uuid
from controller import Controller, INPUT_REPORT_UUID, COMMAND_RESPONSE_UUID, NSO_GAMECUBE_CONTROLLER_PID, PRO_CONTROLLER2_PID, CONTROLER_NAMES, controller_calibration_keys, normalize_calibration_key
from discoverer import (
    start_discoverer,
    set_shutting_down,
    set_suspending,
    emergency_cleanup,
    request_wired_rescan,
    set_wired_auto_scan_enabled,
)
from config import get_resource, CONFIG, BACK_BUTTON_OPTIONS, JOYSTICK_OPTIONS, SWITCH_BUTTONS, get_driver_path, GYRO_LOCK_TOKEN, GYRO_LOCK_LABEL, MODE_SHIFT_TOKEN, MODE_SHIFT_LABEL, IN_APP_GYRO_TOKEN, IN_APP_GYRO_LABEL, _YamlLoader, _YamlDumper, SWITCH_INPUT_DAMPENING_OPTIONS, MOUSE_CLICK_BACK_BUTTON_TOKENS, back_button_label, normalize_dampening_inputs, packaged_winuhid_available, refresh_packaged_winuhid_capability, confirm_packaged_winuhid_capability
from cemuhook_udp import cemuhook_server
from virtual_controller import VirtualController
from discoverer import split_controller, merge_controllers, VIRTUAL_CONTROLLERS
from utils import set_startup, disable_power_throttling
import utils
import keyboard_output
import raw_input_mouse
from gyro import GYRO_PHASE0_RECORDER
from mag_tester import export_recorded_file, mag_tester_build_enabled
import pystray
from pystray import MenuItem as item
from PIL import Image, ImageTk
import win32gui
import win32con
from ctypes import wintypes
from driver_install_helper import (
    HIDHIDE_HEALTHY,
    HIDHIDE_PARTIAL,
    HIDHIDE_UNKNOWN,
    USBIP_HEALTHY,
    USBIP_PARTIAL,
    USBIP_UNKNOWN,
    VIGEMBUS_ABSENT,
    VIGEMBUS_HEALTHY,
    VIGEMBUS_PARTIAL,
    VIGEMBUS_UNKNOWN,
    WINUHID_ABSENT,
    WINUHID_HEALTHY,
    WINUHID_PARTIAL,
    WINUHID_UNKNOWN,
    invalidate_driver_status_cache,
    get_hidhide_status,
    get_usbip_status,
    get_winuhid_status,
    get_vigembus_status,
)

print("Switch 2 Pro Connect (ShFr UI Mod)  Copyright (C) 2026  TommyWabg / SheeshFr")
print("Forked and vibecode modded by SheeshFr. Thanks to TommyWabg and all the rest for their hard work!")
print("This program comes with ABSOLUTELY NO WARRANTY; for details type `show w'.")
print("This is free software, and you are welcome to redistribute it")
print("under certain conditions; type `show c' for details.")

APP_VERSION = "v1.0"
MAG_TESTER_BUILD_ENABLED = mag_tester_build_enabled()

def _set_current_thread_priority(level):
    try:
        if os.name == "nt":
            kernel32 = ctypes.windll.kernel32
            kernel32.SetThreadPriority(kernel32.GetCurrentThread(), int(level))
    except Exception:
        pass

def _get_current_thread_priority():
    try:
        if os.name == "nt":
            kernel32 = ctypes.windll.kernel32
            priority = int(kernel32.GetThreadPriority(kernel32.GetCurrentThread()))
            return None if priority == 0x7FFFFFFF else priority
    except Exception:
        pass
    return None

from gui_listeners import (
    SHELLEXECUTEINFOW,
    WINDOWPLACEMENT,
    GUID,
    DEV_BROADCAST_HDR,
    DEV_BROADCAST_DEVICEINTERFACE_W,
    PowerListener,
    WiredDeviceChangeListener,
    SEE_MASK_NOCLOSEPROCESS,
    WAIT_TIMEOUT,
    WAIT_OBJECT_0,
    PROCESS_QUERY_LIMITED_INFORMATION,
)

# Explicitly set types for Win32 API to ensure compatibility
ctypes.windll.shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(SHELLEXECUTEINFOW)]
ctypes.windll.shell32.ShellExecuteExW.restype = wintypes.BOOL

ctypes.windll.kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
ctypes.windll.kernel32.WaitForSingleObject.restype = wintypes.DWORD

ctypes.windll.kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
ctypes.windll.kernel32.GetExitCodeProcess.restype = wintypes.BOOL

ctypes.windll.user32.GetWindowPlacement.argtypes = [wintypes.HWND, ctypes.POINTER(WINDOWPLACEMENT)]
ctypes.windll.user32.GetWindowPlacement.restype = wintypes.BOOL
ctypes.windll.user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
ctypes.windll.user32.GetAncestor.restype = wintypes.HWND
ctypes.windll.user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
ctypes.windll.user32.GetWindowRect.restype = wintypes.BOOL
ctypes.windll.user32.IsIconic.argtypes = [wintypes.HWND]
ctypes.windll.user32.IsIconic.restype = wintypes.BOOL
ctypes.windll.user32.SetWindowPos.argtypes = [
    wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, ctypes.c_int, wintypes.UINT,
]
ctypes.windll.user32.SetWindowPos.restype = wintypes.BOOL
ctypes.windll.user32.RegisterDeviceNotificationW.argtypes = [
    wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
]
ctypes.windll.user32.RegisterDeviceNotificationW.restype = wintypes.HANDLE
ctypes.windll.user32.UnregisterDeviceNotification.argtypes = [wintypes.HANDLE]
ctypes.windll.user32.UnregisterDeviceNotification.restype = wintypes.BOOL

ctypes.windll.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
ctypes.windll.kernel32.CloseHandle.restype = wintypes.BOOL

ctypes.windll.kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
ctypes.windll.kernel32.OpenProcess.restype = wintypes.HANDLE

ctypes.windll.kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
ctypes.windll.kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL

ctypes.windll.user32.GetForegroundWindow.argtypes = []
ctypes.windll.user32.GetForegroundWindow.restype = wintypes.HWND

from gui_widgets import (
    normalize_app_path,
    get_exe_display_name,
    get_file_icon,
    get_window_taskbar_icon,
    get_rounded_rect_image,
    make_rounded_button,
    set_rounded_button_bg,
    update_toggle_button,
    Tooltip,
    RecordingEntry,
    FocusOutline,
    BackButtonSelector,
    ProfileBackButtonSelector,
    ToggleSwitch,
    COLOR_OFF,
    COLOR_OFF_HOVER,
    COLOR_OFF_PRESS,
    COLOR_ON,
    COLOR_ON_HOVER,
    COLOR_ON_PRESS,
    apply_window_dark_theme_and_icon,
)

def check_driver_registry():
    return bool(get_winuhid_status(use_cache=True).registry_exists)

def check_driver_pnputil():
    return bool(get_winuhid_status(use_cache=True).present_instances)

def is_driver_installed():
    return get_winuhid_status(use_cache=True).installed


def verify_winuhid_runtime(attempts=1, delay_seconds=0.1):
    """Create, submit one neutral report to, and destroy a temporary WinUHid pad."""
    import winuhid_client
    for attempt in range(max(1, attempts)):
        pad = None
        try:
            pad = winuhid_client.VX360Gamepad()
            if getattr(pad, "device", None) and pad.update() is not False:
                return True
        except Exception as exc:
            logger.debug("WinUHid runtime smoke test attempt %d failed: %s", attempt + 1, exc)
        finally:
            if pad is not None:
                try:
                    pad.close()
                except Exception:
                    pass
        if attempt + 1 < attempts:
            time.sleep(delay_seconds)
    logger.error("WinUHid runtime smoke test failed after %d attempts", attempts)
    return False

def hidhide_service_state():
    """HidHide service registration: True / False / None (undeterminable).

    Never raises. None must not be persisted as "not installed" - a registry key
    that exists but cannot be read would otherwise write a wrong answer into
    config.yaml that survives restarts.
    """
    try:
        import hidhide
        return hidhide.service_state()
    except Exception as exc:
        logger.debug("HidHide state could not be read: %s", exc)
        return None


def removal_verified(status, runtime_probe):
    """True when a driver can be considered gone.

    Normally every layer must read absent. When the layers cannot be read at all
    (older pnputil), fall back to the runtime probe: if a client can no longer be
    created, the driver is effectively removed.
    """
    if status.absent:
        return True
    if status.unknown:
        return not runtime_probe(attempts=2)
    return False


def check_vigembus_registry():
    status = get_vigembus_status(use_cache=True)
    return bool(status.service_exists) or bool(status.msi_entries)

def check_vigembus_pnputil():
    status = get_vigembus_status(use_cache=True)
    return bool(status.bound_instances and status.driver_packages)

def is_vigembus_installed():
    return get_vigembus_status(use_cache=True).installed


def verify_vigembus_runtime(attempts=1, delay_seconds=0.1):
    for attempt in range(max(1, attempts)):
        bus = None
        try:
            from virtual_controller import get_vigem
            vigem = get_vigem()
            bus = vigem.win.virtual_gamepad.VBus()
            return True
        except Exception as exc:
            logger.debug("ViGEmBus runtime smoke test attempt %d failed: %s", attempt + 1, exc)
        finally:
            if bus is not None:
                try:
                    del bus
                except Exception:
                    pass
        if attempt + 1 < attempts:
            time.sleep(delay_seconds)
    return False


def verify_vigembus_ready(attempts=12, delay_seconds=0.5):
    """Wait for both PnP/service health and an actual client connection.

    When the PnP layers cannot be determined (pnputil without /properties), the
    runtime connection alone decides - it is what the app actually depends on.
    """
    for attempt in range(max(1, attempts)):
        invalidate_driver_status_cache("vigembus")
        status = get_vigembus_status()
        if (status.installed or status.unknown) and verify_vigembus_runtime(attempts=1):
            return True
        if attempt + 1 < attempts:
            time.sleep(delay_seconds)
    return False

# Wired pads the USB watcher can adopt, mirrored here so the WM_DEVICECHANGE filter
# stays in sync without importing usb_hid_controller (and hidapi) at GUI import time.
try:
    from usb_hid_controller import WIRED_USB_PIDS as WIRED_USB_DEVICE_PIDS
except Exception:
    WIRED_USB_DEVICE_PIDS = (0x2069, 0x2073)


def wired_controller_label(product_ids, sentence=False):
    """Name the wired pad(s) currently connected, for UI text.

    Every wired string used to be hardcoded to "Pro Controller 2", so plugging in a
    GameCube controller produced buttons and prompts naming the wrong device. Names
    come from CONTROLER_NAMES so wired text matches what the rest of the app calls
    the same pad.

    ``sentence`` returns a subject phrase to open a sentence with ("A wired NSO
    GameCube Controller"), rather than the bare button label.
    """
    ids = [pid for pid in dict.fromkeys(product_ids or ()) if pid in CONTROLER_NAMES]
    if len(ids) > 1:
        # Mixed set (e.g. a Pro Controller 2 and a GameCube pad): naming one of them
        # would be wrong, so stay generic rather than pick a winner.
        return "Wired controllers were" if sentence else "Wired Controllers"
    if not ids:
        return "A wired controller was" if sentence else "Wired Controller"
    name = CONTROLER_NAMES[ids[0]]
    if sentence:
        return f"{'An' if name[0] in 'AEIOU' else 'A'} wired {name} was"
    return f"Wired {name}"


# No WinUSB status helper lives here any more. Nintendo's pads advertise the
# MS_COMP_WINUSB compatible id, so Windows binds its own inbox winusb.inf with no
# user action. The USB transport layer uses it automatically when available and
# falls back to HID without exposing a manual route selector. Input always remains
# on the HID interface. usb_hid_controller.winusb_binding_state() remains as the
# single implementation used for connection diagnostics.

logger = logging.getLogger(__name__)
logger.info(
    "GUI executable=%s frozen=%s",
    sys.executable, bool(getattr(sys, "frozen", False)))

try:
    # Break out of Windows terminal DPI virtualization cache to get TRUE physical resolution
    ctypes.windll.shcore.SetProcessDpiAwareness(2) # PROCESS_PER_MONITOR_DPI_AWARE
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

try:
    screen_height = ctypes.windll.user32.GetSystemMetrics(1) # SM_CYSCREEN
    if not screen_height or screen_height <= 0:
        screen_height = 1440
except Exception:
    screen_height = 1440

# Baseline is 1440p physical height.
from gui_player_block import (
    MockControllerInfo,
    MockPhysicalController,
    MockVirtualController,
    PlayerInfoBlock,
)

resolution_ratio = 1.0
window_resolution_ratio = 1.0
scaling_factor = 1.0
ui_dpi = 120
ui_dpi_scale = 1.25
controller_frame_size = 180
battery_height = 24
player_row_height = 30
player_led_width = 54
player_led_height = 8
BASE_WINDOW_WIDTH = 635
BASE_WINDOW_HEIGHT = 335

def _scaled_px(base_value, minimum=1, scale=None):
    if scale is None:
        scale = scaling_factor
    return max(minimum, int(base_value * scale))

def _normalized_user_ui_scale(value=None):
    return 1.0

def _monitor_content_ratio(current_screen_height, user_scale=1.0):
    """Resolution-only UI ratio anchored at the proven 1440p layout."""
    try:
        height = max(1, int(current_screen_height))
        scale = float(user_scale)
    except (TypeError, ValueError):
        height, scale = 1440, 1.0
    return (height / 1440.0) * scale

def _get_window_non_client_height():
    caption_height = ctypes.windll.user32.GetSystemMetrics(4)   # SM_CYCAPTION
    frame_height = ctypes.windll.user32.GetSystemMetrics(33)    # SM_CYFRAME
    padded_border = ctypes.windll.user32.GetSystemMetrics(92)   # SM_CXPADDEDBORDER
    return caption_height + (2 * frame_height) + (2 * padded_border)

class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def _monitor_metrics(monitor):
    """Return physical monitor/work-area metrics for an HMONITOR."""
    if not monitor:
        return None
    try:
        get_monitor_info = ctypes.windll.user32.GetMonitorInfoW
        get_monitor_info.argtypes = [ctypes.c_void_p, ctypes.POINTER(_MONITORINFO)]
        get_monitor_info.restype = wintypes.BOOL
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(info)
        if not get_monitor_info(ctypes.c_void_p(int(monitor)), ctypes.byref(info)):
            return None
        return {
            "handle": int(monitor),
            "left": int(info.rcMonitor.left),
            "top": int(info.rcMonitor.top),
            "right": int(info.rcMonitor.right),
            "bottom": int(info.rcMonitor.bottom),
            "width": int(info.rcMonitor.right - info.rcMonitor.left),
            "height": int(info.rcMonitor.bottom - info.rcMonitor.top),
            "work_left": int(info.rcWork.left),
            "work_top": int(info.rcWork.top),
            "work_right": int(info.rcWork.right),
            "work_bottom": int(info.rcWork.bottom),
            "work_width": int(info.rcWork.right - info.rcWork.left),
            "work_height": int(info.rcWork.bottom - info.rcWork.top),
        }
    except Exception:
        return None


def _monitor_metrics_from_point(x, y):
    """Return the nearest display for a physical screen coordinate."""
    try:
        user32 = ctypes.windll.user32
        user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
        user32.MonitorFromPoint.restype = ctypes.c_void_p
        monitor = user32.MonitorFromPoint(
            wintypes.POINT(int(x), int(y)), 2)  # MONITOR_DEFAULTTONEAREST
        return _monitor_metrics(monitor)
    except Exception:
        return None


def _monitor_metrics_from_window(hwnd):
    """Return the display containing most of a top-level window."""
    try:
        user32 = ctypes.windll.user32
        user32.MonitorFromWindow.argtypes = [ctypes.c_void_p, wintypes.DWORD]
        user32.MonitorFromWindow.restype = ctypes.c_void_p
        monitor = user32.MonitorFromWindow(
            ctypes.c_void_p(int(hwnd)), 2)  # MONITOR_DEFAULTTONEAREST
        return _monitor_metrics(monitor)
    except Exception:
        return None


def _monitor_work_signature(monitor):
    if not monitor:
        return None
    return (
        monitor["width"], monitor["height"],
        monitor["work_left"], monitor["work_top"],
        monitor["work_right"], monitor["work_bottom"],
    )


def _top_level_hwnd(widget):
    """Return Tk's actual outer/root HWND, including title bar and borders."""
    try:
        raw_hwnd = int(widget.winfo_id())
        user32 = ctypes.windll.user32
        user32.GetAncestor.argtypes = [ctypes.c_void_p, wintypes.UINT]
        user32.GetAncestor.restype = ctypes.c_void_p
        outer_hwnd = user32.GetAncestor(
            ctypes.c_void_p(raw_hwnd), 2)  # GA_ROOT
        return int(outer_hwnd or raw_hwnd)
    except Exception:
        return None


def _get_window_dpi(hwnd):
    """Return a top-level window's live DPI without affecting UI scaling."""
    try:
        get_dpi = getattr(ctypes.windll.user32, "GetDpiForWindow", None)
        if get_dpi and hwnd:
            get_dpi.argtypes = [wintypes.HWND]
            get_dpi.restype = wintypes.UINT
            dpi = int(get_dpi(wintypes.HWND(int(hwnd))))
            return dpi if dpi > 0 else None
    except Exception:
        pass
    return None


def _fit_window_to_work_area(monitor, desired_client_width,
                             desired_client_height, hwnd=None, x=None, y=None):
    """Fit a decorated main window inside rcWork without changing its width rule."""
    desired_client_width = max(1, int(desired_client_width))
    desired_client_height = max(1, int(desired_client_height))
    non_client_width = 0
    non_client_height = 0
    try:
        if hwnd:
            outer = win32gui.GetWindowRect(int(hwnd))
            client = win32gui.GetClientRect(int(hwnd))
            non_client_width = max(
                0, (outer[2] - outer[0]) - (client[2] - client[0]))
            non_client_height = max(
                0, (outer[3] - outer[1]) - (client[3] - client[1]))
        else:
            user32 = ctypes.windll.user32
            non_client_width = 2 * (
                user32.GetSystemMetrics(32) + user32.GetSystemMetrics(92))
            non_client_height = _get_window_non_client_height()
    except Exception:
        non_client_width = 0
        non_client_height = 0

    if monitor:
        max_client_height = max(
            1, int(monitor["work_height"]) - non_client_height)
        client_height = min(desired_client_height, max_client_height)
    else:
        client_height = desired_client_height

    outer_width = desired_client_width + non_client_width
    outer_height = client_height + non_client_height
    target_x = int(x if x is not None else (monitor["work_left"] if monitor else 0))
    target_y = int(y if y is not None else (monitor["work_top"] if monitor else 0))
    if monitor:
        if outer_width <= monitor["work_width"]:
            target_x = min(
                max(target_x, monitor["work_left"]),
                monitor["work_right"] - outer_width)
        target_y = min(
            max(target_y, monitor["work_top"]),
            monitor["work_bottom"] - outer_height)

    return {
        "client_width": desired_client_width,
        "client_height": client_height,
        "outer_width": outer_width,
        "outer_height": outer_height,
        "x": target_x,
        "y": target_y,
    }


def _get_current_dpi_scale():
    try:
        get_dpi = getattr(ctypes.windll.user32, "GetDpiForSystem", None)
        if get_dpi:
            dpi = int(get_dpi())
            if dpi > 0:
                return dpi, dpi / 96.0
    except Exception:
        pass
    try:
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        hdc = user32.GetDC(0)
        if hdc:
            try:
                dpi = int(gdi32.GetDeviceCaps(hdc, 88))  # LOGPIXELSX
                if dpi > 0:
                    return dpi, dpi / 96.0
            finally:
                user32.ReleaseDC(0, hdc)
    except Exception:
        pass
    return 120, 1.25

def refresh_ui_scaling(current_screen_height=None, current_work_height=None):
    global screen_height, resolution_ratio, window_resolution_ratio, scaling_factor
    global ui_dpi, ui_dpi_scale
    global controller_frame_size, battery_height, player_row_height
    global player_led_width, player_led_height

    if current_screen_height:
        screen_height = current_screen_height

    ui_scale = _normalized_user_ui_scale()
    CONFIG.ui_scale = ui_scale
    ui_dpi, ui_dpi_scale = _get_current_dpi_scale()
    # Content size depends only on physical display resolution and the in-app
    # slider. rcWork/taskbar height is handled by the window fit + scroll
    # viewport and must never make widgets smaller. This removes the old
    # discontinuity where exactly 1440p used a different formula.
    resolution_ratio = _monitor_content_ratio(screen_height, ui_scale)
    # The monitor ratio owns window height. The in-app scale is applied only
    # to width at the geometry call sites below.
    window_resolution_ratio = screen_height / 1440.0
    scaling_factor = 1.2 * resolution_ratio
    controller_frame_size = _scaled_px(180)
    battery_height = _scaled_px(24)
    player_row_height = _scaled_px(30)
    player_led_width = _scaled_px(54)
    player_led_height = _scaled_px(8)

refresh_ui_scaling()

def scale_font(font_tuple):
    if not font_tuple:
        return font_tuple
    if isinstance(font_tuple, tuple) and len(font_tuple) >= 2:
        family, size = font_tuple[0], font_tuple[1]
        weight = font_tuple[2] if len(font_tuple) > 2 else ""
        # Convert Tkinter points to physical pixels (1 point = 96/72 pixels)
        base_pixel_size = size * (96.0 / 72.0)
        scaled_pixel_size = max(8, int(base_pixel_size * scaling_factor))
        
        # Negative size tells Tkinter to use exact physical pixels, preventing DPI double-scaling
        return (family, -scaled_pixel_size, weight)
    return font_tuple


# Keyboard modifier tokens that keep their bare name on screen (no "KB" prefix), so a
# combo reads e.g. "CONTROL+KBC" rather than "KBCONTROL+KBC".
_INPUT_MODIFIER_TOKENS = {
    "VK_CONTROL", "VK_CONTROL_L", "VK_CONTROL_R", "VK_LCONTROL", "VK_RCONTROL",
    "VK_SHIFT", "VK_SHIFT_L", "VK_SHIFT_R", "VK_LSHIFT", "VK_RSHIFT",
    "VK_MENU", "VK_ALT", "VK_ALT_L", "VK_ALT_R", "VK_LMENU", "VK_RMENU",
    "VK_WIN", "VK_LWIN", "VK_RWIN", "VK_WIN_L", "VK_WIN_R",
}


def format_input_display(text):
    """Human-readable form of a recorded Custom input token string. Mouse buttons are
    shown as M1/M2/M3 (left/right/middle), keyboard keys as KB<key> (e.g. KB1, KBA),
    keyboard modifiers keep their bare name (CONTROL, SHIFT, ...), and controller buttons
    keep their bare name. The stored config value still uses the raw MB_/VK_/BTN_ tokens;
    this only affects what the recorder entry displays."""
    parts = []
    for token in text.split("+"):
        if token in _INPUT_MODIFIER_TOKENS:
            parts.append(token[3:])          # strip "VK_", keep modifier name as-is
        elif token.startswith("VK_"):
            parts.append("KB" + token[3:])
        elif token.startswith("MB_"):
            parts.append({"MB_1": "M1", "MB_2": "M3", "MB_3": "M2"}.get(token, "M" + token[3:]))
        elif token.startswith("BTN_"):
            parts.append(token[4:])
        else:
            parts.append(token)
    return "+".join(parts)


MOUSE_CLICK_CUSTOM_TOKENS = {v: k for k, v in MOUSE_CLICK_BACK_BUTTON_TOKENS.items()}


def parse_mouse_click_mapping(value):
    if not isinstance(value, str):
        return None
    if value in MOUSE_CLICK_BACK_BUTTON_TOKENS:
        return value, "Hold"
    if value.startswith("Custom[Tap]:"):
        mode = "Tap"
        payload = value[12:]
    elif value.startswith("Custom[Hold]:"):
        mode = "Hold"
        payload = value[13:]
    elif value.startswith("Custom:"):
        mode = "Hold"
        payload = value[7:]
    else:
        return None
    if "+" in payload:
        return None
    option_token = MOUSE_CLICK_CUSTOM_TOKENS.get(payload)
    if option_token is None:
        return None
    return option_token, mode


# Current Color Scheme (Space Gray / Cyan Accent)
background_color = "#2D2D2D"
tab_black = "#1E1E1E"
block_color = background_color
player_number_bg_color = "#2D2D2D"
highlight_color = "#00C3E3"
text_color = "#FFFFFF"
button_gray = "#4B4B4B"

CONTROLLER_UPDATED_EVENT = '<<ControllersUpdated>>'
pending_merge_vc_index = None

from gui_drivers_mixin import ControllerWindowDriversMixin
from gui_settings_mixin import ControllerWindowSettingsMixin
from gui_wizards import (
    CalibrationOverlay,
    JoystickCalibrationWizard,
    MagnetometerCalibrationWizard,
    GyroCalibrationWizard,
    GCTriggerCalibrationWizard,
)

class ControllerWindow(ControllerWindowDriversMixin, ControllerWindowSettingsMixin):
    _current_instance = None

    def __init__(self):
        ControllerWindow._current_instance = self
        import sys
        sys._switch2proconnect_gui_instance = self
        sys._switch2connect_gui_instance = self
        self._ui_base_thread_priority = _get_current_thread_priority()
        initial_power_saving_mode = getattr(CONFIG, "power_saving_mode", "Off")
        if initial_power_saving_mode in ("Auto", "Full"):
            self._apply_power_saving_ui_priority(initial_power_saving_mode)
        self.root = None
        self.main_frame = None
        self.settings_frame = None
        self.no_controllers = True
        self.message_queue = queue.Queue()
        self.quit_event = threading.Event()
        self.discoverer_callback = None
        self.power_listener = PowerListener(
            self.handle_power_event,
            show_window_callback=lambda: self.root and self.root.after(0, self.restore_and_bring_to_front)
        )
        self.last_width = CONFIG.window_width
        self.last_height = CONFIG.window_height
        self.last_x = CONFIG.window_x
        self.last_y = CONFIG.window_y
        self._ui_monitor_handle = None
        self._ui_monitor_signature = None
        self._ui_window_dpi = None
        self._dpi_independent_client_size = None
        self._dpi_independent_outer_size = None
        self._dpi_independent_outer_position = None
        self._width_reconcile_after_id = None
        self._monitor_check_after_id = None
        self._dynamic_scale_in_progress = False
        self._dynamic_widget_baselines = weakref.WeakKeyDictionary()
        self.last_foreground_app_path = None
        self.last_external_app_path = None
        self.last_external_app_exe = None
        self.app_profile_poll_suspended = False
        self.app_profile_switching = False
        self.mag_tester_window = None
        self.mag_tester_refresh_after_id = None
        self.mag_tester_values = {}
        self.mag_tester_last_recording = None
        self.mag_tester_stop_pending = False
        self.esp32s3_bridge_status = None
        self.esp32s3_detected = False
        # Wired USB Pro Controller 2 detection (drives the HidHide button visibility).
        self.wired_pro2_detected = False
        # PIDs of the wired pads currently connected, so every wired label names the
        # controller actually plugged in rather than assuming a Pro Controller 2.
        self.wired_controller_pids = []
        self._hidhide_installed_cached = False
        self._wired_pro2_refresh_running = False
        self._wired_pro2_prompt_shown = False
        self.wired_device_event_queue = queue.Queue()
        self.wired_device_listener = WiredDeviceChangeListener(self.wired_device_event_queue)
        self._wired_device_change_after_id = None
        self._esp32s3_refresh_running = False
        self._esp32s3_auto_firmware_running = False
        self._esp32s3_auto_firmware_attempted = set()
        self._esp32s3_current_seen = False
        # Mirrors esp32s3_detected as seen by the periodic status timer. Must be kept
        # in sync whenever detection state is set elsewhere (startup / post-flash
        # resume), otherwise the timer misreads the first poll as a fresh plug-in
        # event and needlessly restarts the discoverer, dropping a live controller.
        self._esp32s3_was_detected = False
        # True while a firmware flash + replug window is in progress. While set, the
        # periodic status timer must NOT open the COM port, otherwise it collides
        # with esptool during the flash and holds the port open during the replug,
        # forcing the user to restart the app to clear the occupancy.
        self._esp32s3_firmware_busy = False
        self.active_joystick_calibration_wizards = {}
        
        import utils
        utils.change_profile_callback = self.on_cycle_profile
        utils.switch_profile_callback = self.on_profile_combo_switch
        utils.profile_nav_callback = self.on_profile_nav
        utils.profile_confirm_callback = self.on_profile_confirm
        utils.profile_cancel_callback = self.on_profile_cancel
        utils.force_ui_update_callback = self.force_refresh_player_slots

    def center_window_on_root(self, window, width, height, owner=None):
        """Center a child window over the owner window (or main window) in screen coordinates."""
        if owner is None:
            owner = self.root
        width = max(1, int(width))
        height = max(1, int(height))
        anchor = {"x": None, "y": None}
        pixel_anchor = {"x": None, "y": None}

        def top_level_hwnd(widget):
            try:
                hwnd = widget.winfo_id()
                root_hwnd = ctypes.windll.user32.GetAncestor(hwnd, 2)  # GA_ROOT
                return root_hwnd or hwnd
            except (tk.TclError, AttributeError, OSError):
                return None

        def capture_physical_root_center():
            """Return the owner-window center in Win32 physical screen pixels."""
            hwnd = top_level_hwnd(owner)
            rect = wintypes.RECT()
            try:
                valid = (
                    hwnd and
                    not ctypes.windll.user32.IsIconic(hwnd) and
                    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)) and
                    rect.right > rect.left and rect.bottom > rect.top and
                    rect.left > -10000 and rect.top > -10000
                )
                if valid:
                    center = ((rect.left + rect.right) // 2,
                              (rect.top + rect.bottom) // 2)
                    if owner == self.root:
                        self._last_main_window_center_px = center
                    return center
            except (AttributeError, OSError):
                pass
            return getattr(self, "_last_main_window_center_px", None) if owner == self.root else None

        def place():
            try:
                if not window.winfo_exists() or not owner.winfo_exists():
                    return
                owner.update_idletasks()
                window.update_idletasks()

                if pixel_anchor["x"] is None:
                    physical_center = capture_physical_root_center()
                    if physical_center:
                        pixel_anchor["x"], pixel_anchor["y"] = physical_center

                if anchor["x"] is None:
                    rx = owner.winfo_rootx()
                    ry = owner.winfo_rooty()
                    rw = max(1, owner.winfo_width())
                    rh = max(1, owner.winfo_height())
                    try:
                        owner_state = owner.state()
                    except tk.TclError:
                        owner_state = "withdrawn"

                    owner_position_valid = (
                        (owner != self.root or owner_state not in ("iconic", "withdrawn")) and
                        rx > -10000 and ry > -10000 and rw > 1 and rh > 1
                    )
                    if owner_position_valid:
                        anchor["x"] = rx + rw // 2
                        anchor["y"] = ry + rh // 2
                        if owner == self.root:
                            self._last_main_window_center = (anchor["x"], anchor["y"])
                    else:
                        cached_center = getattr(self, "_last_main_window_center", None)
                        if cached_center and owner == self.root:
                            anchor["x"], anchor["y"] = cached_center
                        else:
                            hwnd = self.get_root_hwnd()
                            placement = WINDOWPLACEMENT()
                            placement.length = ctypes.sizeof(WINDOWPLACEMENT)
                            if hwnd and ctypes.windll.user32.GetWindowPlacement(
                                    hwnd, ctypes.byref(placement)):
                                rect = placement.rcNormalPosition
                                anchor["x"] = (rect.left + rect.right) // 2
                                anchor["y"] = (rect.top + rect.bottom) // 2
                                if owner == self.root:
                                    self._last_main_window_center = (anchor["x"], anchor["y"])
                            else:
                                anchor["x"] = rx + rw // 2
                                anchor["y"] = ry + rh // 2
                x = anchor["x"] - width // 2
                y = anchor["y"] - height // 2

                try:
                    virtual_x = ctypes.windll.user32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
                    virtual_y = ctypes.windll.user32.GetSystemMetrics(77)  # SM_YVIRTUALSCREEN
                    virtual_w = ctypes.windll.user32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
                    virtual_h = ctypes.windll.user32.GetSystemMetrics(79)  # SM_CYVIRTUALSCREEN
                except (AttributeError, OSError):
                    virtual_x = self.root.winfo_vrootx()
                    virtual_y = self.root.winfo_vrooty()
                    virtual_w = self.root.winfo_vrootwidth()
                    virtual_h = self.root.winfo_vrootheight()
                if virtual_w > 1 and virtual_h > 1:
                    x = min(max(x, virtual_x), virtual_x + virtual_w - width)
                    y = min(max(y, virtual_y), virtual_y + virtual_h - height)

                window.geometry(f"{width}x{height}+{x}+{y}")
                window.lift(owner)

                dialog_hwnd = top_level_hwnd(window)
                dialog_rect = wintypes.RECT()
                if (pixel_anchor["x"] is not None and dialog_hwnd and
                        ctypes.windll.user32.GetWindowRect(
                            dialog_hwnd, ctypes.byref(dialog_rect))):
                    measured_w = dialog_rect.right - dialog_rect.left
                    measured_h = dialog_rect.bottom - dialog_rect.top
                    outer_w = measured_w if measured_w > 10 else width
                    outer_h = measured_h if measured_h > 10 else height
                    physical_x = pixel_anchor["x"] - outer_w // 2
                    physical_y = pixel_anchor["y"] - outer_h // 2
                    ctypes.windll.user32.SetWindowPos(
                        dialog_hwnd, 0, physical_x, physical_y, 0, 0,
                        0x0001 | 0x0004 | 0x0010,  # NOSIZE | NOZORDER | NOACTIVATE
                    )
            except (tk.TclError, RuntimeError, OSError, ValueError, ctypes.ArgumentError):
                pass

        place()
        try:
            window.after_idle(place)
        except (tk.TclError, RuntimeError):
            pass

    def start_joystick_calibration_from_callback(self, virtual_controller):
        if threading.current_thread() != threading.main_thread():
            self.root.after(0, self.start_joystick_calibration_from_callback, virtual_controller)
            return
        if virtual_controller is None or not getattr(virtual_controller, "controllers", None):
            utils.show_notification("Joysticks Calibration", "No joystick found for this player slot.")
            return
        if getattr(self, "calibration_overlay", None):
            self.calibration_overlay.close()
        key = id(virtual_controller)
        existing = self.active_joystick_calibration_wizards.get(key)
        if existing is not None and not getattr(existing, "closed", False):
            existing.cancel()
        wizard = JoystickCalibrationWizard(
            self.root,
            virtual_controller,
            on_closed=lambda w, k=key: self.active_joystick_calibration_wizards.pop(k, None)
        )
        if getattr(wizard, "window", None) is not None:
            self.active_joystick_calibration_wizards[key] = wizard

    def start_joystick_calibration(self, virtual_controller):
        self.start_joystick_calibration_from_callback(virtual_controller)

    def cancel_joystick_calibration_from_callback(self, virtual_controller):
        if threading.current_thread() != threading.main_thread():
            self.root.after(0, self.cancel_joystick_calibration_from_callback, virtual_controller)
            return
        key = id(virtual_controller) if virtual_controller is not None else None
        wizard = self.active_joystick_calibration_wizards.get(key)
        if wizard is not None and not getattr(wizard, "closed", False):
            wizard.cancel()
            return
        if virtual_controller is not None:
            for controller in getattr(virtual_controller, "controllers", []) or []:
                controller.is_joystick_calibrating = False
                controller.back_button_calibration_active = False

    def cancel_all_calibration_after_profile_switch(self):
        if threading.current_thread() != threading.main_thread():
            self.root.after(0, self.cancel_all_calibration_after_profile_switch)
            return
        calibration_active = False
        for wizard in list(getattr(self, "active_joystick_calibration_wizards", {}).values()):
            if wizard is not None and not getattr(wizard, "closed", False):
                calibration_active = True
                wizard.cancel()
        getattr(self, "active_joystick_calibration_wizards", {}).clear()
        for vc in getattr(self, "current_controllers", []) or []:
            for controller in getattr(vc, "controllers", []) or []:
                if (getattr(controller, "is_calibration_counting_down", False) or
                        getattr(controller, "is_calibrating", False) or
                        getattr(controller, "is_mag_calibration_waiting", False) or
                        getattr(controller, "is_mag_calibrating", False) or
                        getattr(controller, "is_joystick_calibrating", False) or
                        getattr(controller, "back_button_calibration_active", False)):
                    calibration_active = True
                cancel = getattr(controller, "cancel_back_button_calibration_state", None)
                if callable(cancel):
                    cancel()
                else:
                    controller.is_calibration_counting_down = False
                    controller.is_calibrating = False
                    controller.is_mag_calibration_waiting = False
                    controller.is_mag_calibrating = False
                    controller.is_joystick_calibrating = False
                    controller.back_button_calibration_active = False
                    controller.prev_calibration = False
        if calibration_active and getattr(self, "calibration_overlay", None):
            self.calibration_overlay.close()

    def get_root_hwnd(self):
        return _top_level_hwnd(self.root)

    def show_centered_dialog(self, title, message, buttons=("OK",), default=None, parent_window=None):
        if threading.current_thread() != threading.main_thread():
            done = threading.Event()
            result = {"value": default or buttons[-1]}

            def run_on_ui_thread():
                try:
                    result["value"] = self.show_centered_dialog(title, message, buttons, default, parent_window=parent_window)
                finally:
                    done.set()

            try:
                self.root.after(0, run_on_ui_thread)
                done.wait()
            except RuntimeError:
                pass
            return result["value"]

        # Resolve active parent window / owner
        if parent_window is None:
            for attr in ("edit_profiles_dialog", "settings_window"):
                candidate = getattr(self, attr, None)
                if candidate is not None and hasattr(candidate, "winfo_exists") and candidate.winfo_exists():
                    try:
                        if candidate.winfo_viewable():
                            parent_window = candidate
                            break
                    except Exception:
                        pass

        owner = parent_window if (parent_window is not None and parent_window.winfo_exists()) else self.root

        dialog_w = int(500 * scaling_factor)
        extra_lines = message.count("\n") + max(0, len(message) // 70)
        dialog_h = max(int(150 * scaling_factor), min(int(280 * scaling_factor), int((135 + extra_lines * 18) * scaling_factor)))
        dialog = tk.Toplevel(owner)
        dialog.withdraw()
        dialog.title(title)
        dialog.resizable(False, False)
        dialog.config(bg=background_color)
        dialog.transient(owner)
        apply_window_dark_theme_and_icon(dialog, background_color)

        result = {"value": default or buttons[-1]}

        tk.Label(
            dialog,
            text=message,
            fg="white",
            bg=background_color,
            font=scale_font(("Arial", 11, "bold")),
            justify=tk.CENTER,
            wraplength=int(440 * scaling_factor),
        ).pack(padx=int(24 * scaling_factor), pady=(int(24 * scaling_factor), int(12 * scaling_factor)), fill=tk.BOTH, expand=True)

        button_frame = tk.Frame(dialog, bg=background_color, bd=0, highlightthickness=0)
        button_frame.pack(pady=(0, int(18 * scaling_factor)))

        def close(value):
            result["value"] = value
            try:
                dialog.grab_release()
            except Exception:
                pass
            dialog.destroy()
            if owner and owner != self.root and hasattr(owner, "winfo_exists") and owner.winfo_exists():
                try:
                    owner.lift()
                    owner.focus_set()
                except Exception:
                    pass

        for button_text in buttons:
            btn = make_rounded_button(
                button_frame,
                text=button_text,
                width=86,
                height=28,
                radius=6,
                bg_color=button_gray,
                hover_color="#5A5A5A",
                press_color="#3A3A3A",
                fg=text_color,
                parent_bg=background_color,
                font=scale_font(("Arial", 10, "bold")),
                command=lambda value=button_text: close(value),
            )
            btn.pack(side=tk.LEFT, padx=int(8 * scaling_factor))
            if button_text == (default or buttons[-1]):
                btn.focus_set()

        dialog.protocol("WM_DELETE_WINDOW", lambda: close(default or buttons[-1]))
        dialog.update_idletasks()
        self.center_window_on_root(dialog, dialog_w, dialog_h, owner=owner)
        dialog.deiconify()
        dialog.lift(owner)
        dialog.focus_force()
        dialog.grab_set()
        try:
            dialog.attributes("-topmost", True)
            dialog.after(100, lambda: dialog.winfo_exists() and dialog.attributes("-topmost", False))
        except Exception:
            pass
        dialog.wait_window()
        return result["value"]

    def ask_centered_yes_no(self, title, message, parent_window=None):
        return self.show_centered_dialog(title, message, ("Yes", "No"), "No", parent_window=parent_window) == "Yes"

    def show_centered_message(self, title, message, parent_window=None):
        self.show_centered_dialog(title, message, ("OK",), "OK", parent_window=parent_window)

    def refresh_esp32s3_status(self):
        try:
            try:
                from usb_serial_bridge import detect_bridge
                status = detect_bridge()
                self.esp32s3_bridge_status = status
            except Exception:
                self.esp32s3_bridge_status = None
            self.esp32s3_detected = bool(self.esp32s3_bridge_status and self.esp32s3_bridge_status.board_present)
        except Exception as e:
            logger.debug(f"ESP32-S3 status refresh failed: {e}")
            self.esp32s3_bridge_status = None
            self.esp32s3_detected = False
        self.update_driver_buttons_visibility()
        return self.esp32s3_bridge_status

    def refresh_esp32s3_status_async(self):
        if getattr(self, '_esp32s3_refresh_running', False) or getattr(self, 'is_quitting', False):
            return
        # The completed-flash dialog owns unplug detection until it and the
        # ESP32-S3 button can be removed in one UI transaction.
        if getattr(self, '_esp32s3_waiting_for_removal', False):
            return
        # Never probe the COM port while a firmware flash / replug is in progress —
        # doing so collides with esptool and re-occupies the port during replug.
        if getattr(self, '_esp32s3_firmware_busy', False):
            return
        self._esp32s3_refresh_running = True

        def worker():
            status = None
            detected = False
            try:
                from usb_serial_bridge import detect_bridge
                status = detect_bridge()
                detected = bool(status and status.board_present)
            except Exception as e:
                logger.debug(f"ESP32-S3 async status refresh failed: {e}")

            def apply_status():
                self._esp32s3_refresh_running = False
                if getattr(self, 'is_quitting', False):
                    return
                was_current = self._esp32s3_current_seen
                was_detected = getattr(self, '_esp32s3_was_detected', False)

                # If the bridge was recently ready and the new probe returns
                # "no firmware" (board still physically present), this is almost
                # certainly a transient PermissionError because the discoverer's
                # shared_client is holding the COM port open. Discarding the
                # result keeps Boot-mode detection confined to the firmware-flash
                # UI and prevents it from disrupting any connection logic.
                # Exception: OTG-only boards have no CDC serial port for the
                # discoverer to hold open, so a firmware_installed=False probe
                # on OTG is a genuine boot+reset event and must not be discarded.
                if (was_current
                        and status
                        and getattr(status, 'board_present', False)
                        and not getattr(status, 'firmware_installed', False)
                        and not getattr(status, 'otg_only', False)):
                    return  # transient probe failure — keep previous state

                self.esp32s3_bridge_status = status
                self.esp32s3_detected = detected
                self._esp32s3_was_detected = detected
                self._esp32s3_current_seen = bool(status and getattr(status, "bridge_ready", False))
                self.update_driver_buttons_visibility()
                self.maybe_auto_update_esp32s3_firmware(status)
                discoverer_running = bool(
                    getattr(self, 'discoverer_thread', None)
                    and self.discoverer_thread
                    and self.discoverer_thread.is_alive()
                )
                # Never tear down a live bridge session: if a controller is already
                # connected, a restart would disconnect it. A transient status-probe
                # timeout can briefly drop bridge_ready and make it look like the
                # bridge "just became ready" again on the next poll — restarting then
                # would kick the user's controller mid-use.
                has_live_controllers = any(
                    vc is not None for vc in getattr(self, 'current_controllers', []) or []
                )

                # Restart discoverer if bridge became ready OR if board was just plugged
                # in — but only when no controller is currently connected.
                if (((self._esp32s3_current_seen and not was_current) or (detected and not was_detected))
                        and discoverer_running and not has_live_controllers):
                    logger.info("ESP32-S3 state changed. Restarting discoverer...")
                    # Pause this 5 s status timer while the discoverer (re)opens the
                    # bridge COM port. Otherwise a transient detect_bridge probe from a
                    # later tick races the discoverer's persistent open on the freshly
                    # hot-plugged port and one side gets "port occupied" — which is why
                    # plugging the ESP32-S3 in AFTER launch failed but before launch
                    # worked. Resume probing once the open window has passed.
                    self._esp32s3_firmware_busy = True

                    def _hotplug_restart():
                        try:
                            self.start_discoverer_thread()
                        finally:
                            self.root.after(4000, lambda: setattr(self, '_esp32s3_firmware_busy', False))

                    self.root.after(100, _hotplug_restart)

            try:
                self.root.after(0, apply_status)
            except RuntimeError:
                self._esp32s3_refresh_running = False

        threading.Thread(target=worker, daemon=True).start()

    def maybe_auto_update_esp32s3_firmware(self, status, on_complete=None):
        # Never auto-flash via OTG: esptool requires manual BOOT button hold on native USB
        if getattr(status, "otg_only", False):
            return False
        if (
            not status
            or not getattr(status, "board_present", False)
            or not getattr(status, "firmware_update_required", False)
            or not getattr(status, "status_text", "")
            or not getattr(status, "firmware_version", "")
            or getattr(self, "_esp32s3_auto_firmware_running", False)
            or getattr(self, "is_quitting", False)
        ):
            return False

        serial_port = getattr(status, "serial_port", None)
        if not serial_port:
            logger.warning("ESP32-S3 firmware update is required, but CH343 flashing port was not detected.")
            return False

        attempt_key = (
            serial_port.port,
            getattr(status, "firmware_version", ""),
            getattr(status, "firmware_mode", ""),
            getattr(status, "expected_version", ""),
        )
        if attempt_key in self._esp32s3_auto_firmware_attempted:
            return False
        self._esp32s3_auto_firmware_attempted.add(attempt_key)
        self._esp32s3_auto_firmware_running = True

        discoverer_was_running = bool(
            getattr(self, 'discoverer_thread', None)
            and self.discoverer_thread
            and self.discoverer_thread.is_alive()
        )
        if discoverer_was_running:
            self.stop_discoverer_thread()

        def completed(ok):
            self._esp32s3_auto_firmware_running = False

            def resume():
                # Reopen the port only after the device re-enumerates post-replug.
                self._esp32s3_firmware_busy = False
                self.start_discoverer_thread()

            if on_complete:
                self._esp32s3_firmware_busy = False
                self.refresh_esp32s3_status_async()
                on_complete(ok)
            elif ok or discoverer_was_running:
                if ok:
                    # Keep the COM port free while the user replugs; resume once current.
                    self.root.after(1000, lambda: self.wait_for_current_esp32s3_then(resume))
                else:
                    self._esp32s3_firmware_busy = False
                    self.refresh_esp32s3_status_async()
                    self.root.after(0, self.start_discoverer_thread)
            else:
                self._esp32s3_firmware_busy = False
                self.refresh_esp32s3_status_async()

        logger.info(
            "ESP32-S3 firmware update required: current version=%s mode=%s expected=%s",
            getattr(status, "firmware_version", ""),
            getattr(status, "firmware_mode", ""),
            getattr(status, "expected_version", ""),
        )
        self.run_esp32s3_firmware_task("install", auto=True, status=status, on_complete=completed)
        return True

    def wait_for_current_esp32s3_then(self, callback, attempts=24):
        if getattr(self, "is_quitting", False):
            return

        def worker(remaining):
            status = None
            try:
                from usb_serial_bridge import detect_bridge
                status = detect_bridge()
            except Exception as e:
                logger.debug(f"Waiting for ESP32-S3 firmware HID failed: {e}")

            def apply_status():
                if getattr(self, "is_quitting", False):
                    return
                self.esp32s3_bridge_status = status
                board_present = bool(status and getattr(status, "board_present", False))
                self.esp32s3_detected = board_present
                self._esp32s3_was_detected = board_present
                self._esp32s3_current_seen = bool(status and getattr(status, "bridge_ready", False))
                self.update_driver_buttons_visibility()
                if self._esp32s3_current_seen or remaining <= 0:
                    callback()
                elif not board_present:
                    # ESP32 fully disconnected — clear state and fall back to System BLE immediately
                    self.esp32s3_bridge_status = None
                    self.esp32s3_detected = False
                    self._esp32s3_was_detected = False
                    self.update_driver_buttons_visibility()
                    callback()
                else:
                    self.root.after(500, lambda: self.wait_for_current_esp32s3_then(callback, remaining - 1))

            try:
                self.root.after(0, apply_status)
            except RuntimeError:
                pass

        threading.Thread(target=worker, args=(attempts,), daemon=True).start()

    def wait_for_esp32s3_removal_then(self, callback, should_continue=None,
                                      consecutive_missing=0, saw_absent=False):
        """Close the completed-flash dialog on unplug or replug initialization.

        Two consecutive absent samples avoid treating a transient detection failure
        during post-flash USB settling as a physical removal.  If the board returns
        after an observed absence, its first detected state is the replug
        initialization stage and closes the dialog immediately.
        """
        if getattr(self, "is_quitting", False):
            return
        if should_continue is not None and not should_continue():
            return

        def worker(previous_missing):
            status = None
            detection_failed = False
            try:
                from usb_serial_bridge import detect_bridge
                status = detect_bridge()
            except Exception as e:
                detection_failed = True
                logger.debug(f"Waiting for ESP32-S3 removal failed: {e}")

            def apply_status():
                if getattr(self, "is_quitting", False):
                    return
                if should_continue is not None and not should_continue():
                    return
                board_present = bool(status and getattr(status, "board_present", False))
                missing = previous_missing + 1 if not board_present else 0
                replug_initializing = bool(
                    not detection_failed and board_present and saw_absent)
                confirmed_removed = bool(
                    not detection_failed and not board_present and missing >= 2)
                if replug_initializing or confirmed_removed:
                    self._esp32s3_waiting_for_removal = False
                    self.esp32s3_bridge_status = status if replug_initializing else None
                    self.esp32s3_detected = replug_initializing
                    self._esp32s3_was_detected = replug_initializing
                    # bridge_ready only means the firmware answered its status probe.
                    # Runtime readiness is established later by discoverer after it
                    # opens CDC and sends "scan on"; keep this edge unconsumed here.
                    self._esp32s3_current_seen = False
                    self.update_driver_buttons_visibility()
                    callback("reinserted" if replug_initializing else "removed", status)
                    return
                self.root.after(
                    500,
                    lambda: self.wait_for_esp32s3_removal_then(
                        callback, should_continue, missing,
                        saw_absent or (not detection_failed and not board_present)))

            try:
                self.root.after(0, apply_status)
            except RuntimeError:
                pass

        threading.Thread(target=worker, args=(consecutive_missing,), daemon=True).start()

    def run_esp32s3_firmware_task(self, action, auto=False, status=None, on_complete=None):
        from tkinter import messagebox
        try:
            from usb_serial_bridge import ESP32S3_LABEL, flash_firmware
        except Exception:
            ESP32S3_LABEL = "ESP32-S3 CDC"
            flash_firmware = None
        
        # COM Port Release Protection Mechanism
        # Mark firmware busy BEFORE stopping discovery so the 5 s status timer can't
        # sneak in a COM-port probe between stop and flash (which would block esptool
        # or re-occupy the port across the replug).
        self._esp32s3_firmware_busy = True
        discoverer_was_running = False
        if hasattr(self, 'discoverer_thread') and self.discoverer_thread and self.discoverer_thread.is_alive():
            discoverer_was_running = True
            self.stop_discoverer_thread()

        # Run emergency cleanup to close all virtual controller handles
        from discoverer import emergency_cleanup
        emergency_cleanup()

        # Explicitly release every open serial client BEFORE flashing so esptool gets
        # exclusive access to the COM port. The discoverer's own shutdown should have
        # closed the shared client, but a lingering handle here is exactly what leaves
        # the port "occupied" after install and forces an app restart.
        try:
            from usb_serial_bridge import close_all_clients
            close_all_clients()
        except Exception:
            pass

        status = status or self.refresh_esp32s3_status()
        if not status or not status.serial_port:
            self._esp32s3_firmware_busy = False
            if discoverer_was_running:
                self.start_discoverer_thread()
            messagebox.showerror(
                ESP32S3_LABEL,
                "Could not find the ESP32-S3 N16R8 CH343/COM flashing port.\nConnect the flashing Type-C/CH343P port and try again."
            )
            return

        title_map = {
            "install": "Installing ESP32-S3 N16R8 Firmware",
            "repair": "Repairing ESP32-S3 N16R8 Firmware",
            "delete": "Deleting ESP32-S3 N16R8 Firmware",
        }
        verb_map = {
            "install": "installing",
            "repair": "repairing",
            "delete": "deleting",
        }

        progress_win = tk.Toplevel(self.root)
        progress_win.title(title_map.get(action, "ESP32-S3 N16R8 Firmware"))
        progress_win.geometry(f"{int(460 * scaling_factor)}x{int(150 * scaling_factor)}+180+180")
        progress_win.resizable(False, False)
        progress_win.config(bg=background_color)
        progress_win.transient(self.root)
        progress_win.grab_set()
        apply_window_dark_theme_and_icon(progress_win, background_color)

        label = tk.Label(
            progress_win,
            text=f"{ESP32S3_LABEL}: {verb_map.get(action, 'working')} firmware on {status.serial_port.port}...",
            fg="white", bg=background_color,
            font=scale_font(("Arial", 11, "bold")),
            wraplength=int(420 * scaling_factor),
            justify=tk.CENTER
        )
        label.pack(pady=(int(18 * scaling_factor), int(10 * scaling_factor)), padx=int(16 * scaling_factor))

        progress_var = tk.DoubleVar(value=0)
        progress_bar = ttk.Progressbar(
            progress_win,
            orient=tk.HORIZONTAL,
            mode="determinate",
            maximum=100,
            variable=progress_var,
            length=int(380 * scaling_factor)
        )
        progress_bar.pack(padx=int(24 * scaling_factor), fill=tk.X)

        percent_label = tk.Label(
            progress_win,
            text="0%",
            fg="white", bg="#1E1E1E",
            font=scale_font(("Arial", 11, "bold"))
        )
        percent_label.pack(pady=(int(8 * scaling_factor), 0))
        progress_win.protocol("WM_DELETE_WINDOW", lambda: None)

        done = {"ok": False, "error": None}
        progress_queue = queue.Queue()

        def progress(payload):
            progress_queue.put(("progress", payload))

        def worker():
            try:
                flash_firmware(status.serial_port.port, mode=action, progress=progress)
                done["ok"] = True
            except Exception as e:
                done["error"] = e
                logger.exception("ESP32-S3 firmware task failed")
            finally:
                progress_queue.put(("done", None))

        def finish():
            if progress_win.winfo_exists():
                progress_win.grab_release()
                progress_win.destroy()

            def resume_discovery():
                # Clear the busy flag only once we're ready to reopen the port, so the
                # 5 s status timer stays quiet through the whole flash + replug window.
                self._esp32s3_firmware_busy = False
                if discoverer_was_running:
                    self.start_discoverer_thread()

            if done["ok"]:
                # Release the COM port so replug is clean and Windows doesn't report a stale handle.
                try:
                    from usb_serial_bridge import close_all_clients
                    close_all_clients()
                except Exception:
                    pass

                if action == "delete":
                    # Uninstall succeeded — firmware is gone, no replug needed.
                    messagebox.showinfo(
                        ESP32S3_LABEL,
                        "ESP32-S3 N16R8 firmware uninstalled successfully.",
                    )
                elif not auto:
                    messagebox.showinfo(
                        ESP32S3_LABEL,
                        "ESP32-S3 N16R8 firmware installed successfully.\n\n"
                        "Please replug the ESP32-S3 USB cable (unplug then reinsert) "
                        "to complete initialization and avoid port conflicts.",
                    )
                else:
                    # Auto-update path: show a brief replug reminder in a non-blocking way.
                    messagebox.showinfo(
                        ESP32S3_LABEL,
                        "Firmware auto-updated. Please replug the ESP32-S3 USB cable.",
                    )

                if on_complete:
                    # Auto-update path manages its own busy-clear + delayed restart.
                    on_complete(done["ok"])
                elif action == "delete":
                    # Firmware removed: nothing to wait for, resume discovery now.
                    self.refresh_esp32s3_status()
                    resume_discovery()
                else:
                    # Manual install/repair: the user must replug. Keep the COM port
                    # free and wait until the device re-enumerates with current
                    # firmware before reopening it, then resume discovery. This is what
                    # stops the "port occupied" state that previously needed an app restart.
                    self.root.after(1500, lambda: self.wait_for_current_esp32s3_then(resume_discovery))
            else:
                self._esp32s3_firmware_busy = False
                error_str = str(done["error"])
                try:
                    from usb_serial_bridge import flash_log, get_flash_log_path
                    flash_log(f"flash failed: {error_str}")
                    _log_path = get_flash_log_path()
                except Exception:
                    _log_path = ""
                if ("Could not communicate with ESP32-S3" in error_str
                        or ("Could not put ESP32-S3" in error_str
                            and "into flashing mode" in error_str)):
                    messagebox.showerror(ESP32S3_LABEL, (
                        "Could not enter flashing mode.\n\n"
                        "To enter Boot mode manually:\n"
                        "  1. Hold the BOOT button\n"
                        "  2. Tap RESET once, then release BOOT\n"
                        "  3. Click Repair to retry\n\n"
                        f"Details logged to:\n{_log_path}"
                    ))
                else:
                    messagebox.showerror(ESP32S3_LABEL, f"ESP32-S3 N16R8 firmware operation failed:\n{done['error']}")
                self.refresh_esp32s3_status()
                if on_complete:
                    on_complete(done["ok"])
                elif discoverer_was_running:
                    self.start_discoverer_thread()

        def apply_progress(payload):
            current = float(progress_var.get())
            percent = None
            message = None
            if isinstance(payload, dict):
                if "percent" in payload:
                    percent = float(payload["percent"])
                elif "write_percent" in payload:
                    percent = 25.0 + (max(0.0, min(100.0, float(payload["write_percent"]))) * 0.70)
                message = payload.get("message")
            else:
                text = str(payload)
                match = re.search(r"\((\d{1,3})\s*%\)", text)
                if match:
                    percent = 25.0 + (max(0.0, min(100.0, float(match.group(1)))) * 0.70)

            if percent is None:
                # Plain esptool log lines are diagnostic text, not progress.  In
                # particular, retries during bootloader synchronization must not
                # appear as a misleading 16% partial flash.
                percent = current
            percent = max(current, min(100.0, percent))
            progress_var.set(percent)
            percent_label.config(text=f"{int(percent)}%")
            if message and progress_win.winfo_exists():
                label.config(text=message)

        def poll_progress_queue():
            should_finish = False
            while True:
                try:
                    kind, payload = progress_queue.get_nowait()
                except queue.Empty:
                    break
                if kind == "progress":
                    if progress_win.winfo_exists():
                        apply_progress(payload)
                elif kind == "done":
                    should_finish = True
            if should_finish:
                progress_var.set(100)
                percent_label.config(text="100%")
                finish()
            elif progress_win.winfo_exists():
                progress_win.after(50, poll_progress_queue)

        threading.Thread(target=worker, daemon=True).start()
        progress_win.after(50, poll_progress_queue)
        self.root.wait_window(progress_win)

    def on_esp32s3_btn_clicked(self):
        self.close_settings_popup()
        from tkinter import messagebox
        try:
            from usb_serial_bridge import ESP32S3_LABEL
        except Exception:
            ESP32S3_LABEL = "ESP32-S3 CDC"

        # Normal discovery intentionally excludes blank/generic serial devices.
        # The firmware dialog is the only scope allowed to expose an unverified
        # candidate, and doing so must not mark the global bridge as detected.
        self.refresh_esp32s3_status()
        try:
            from usb_serial_bridge import detect_bridge
            status = detect_bridge(allow_unverified=True)
        except Exception:
            status = self.esp32s3_bridge_status
        dialog_state = {"status": status, "operation_started": False, "probe_running": False}
        otg_only = bool(status and getattr(status, "otg_only", False))
        # OTG in Boot mode: firmware_installed=False means ROM bootloader is running → can flash directly
        otg_boot_mode = otg_only and not bool(status and getattr(status, "firmware_installed", False))

        if status and getattr(status, "bridge_ready", False):
            firmware_text = f"Installed ({getattr(status, 'firmware_version', '')})"
        elif status and getattr(status, "firmware_current", False):
            firmware_text = f"Installed ({getattr(status, 'firmware_version', '')}, waiting for USB transport)"
        elif status and getattr(status, "firmware_update_required", False):
            current = getattr(status, "firmware_version", "") or "unknown"
            expected = getattr(status, "expected_version", "") or "bundled"
            firmware_text = f"Update required ({current} -> {expected})"
        elif status and getattr(status, "board_present", False):
            firmware_text = "Detected, waiting for status"
        else:
            firmware_text = "Not installed"
        port_text = status.serial_port.port if status and status.serial_port else "CH343/COM not detected"

        dialog_w = int(560 * scaling_factor)
        dialog_h = int(330 * scaling_factor)
        dialog = tk.Toplevel(self.root)
        # Keep the native toplevel hidden until every child widget and the first
        # serial-port list are ready.  WMI enumeration can otherwise expose a
        # short-lived empty window while this function is still constructing it.
        dialog.withdraw()
        dialog.title(ESP32S3_LABEL)
        dialog.resizable(False, False)
        dialog.config(bg=background_color)
        dialog.transient(self.root)
        apply_window_dark_theme_and_icon(dialog, background_color)
        # Center on main window
        self.root.update_idletasks()
        rx = self.root.winfo_x()
        ry = self.root.winfo_y()
        rw = self.root.winfo_width()
        rh = self.root.winfo_height()
        dx = rx + (rw - dialog_w) // 2
        dy = ry + (rh - dialog_h) // 2
        dialog.geometry(f"{dialog_w}x{dialog_h}+{dx}+{dy}")

        info_label = tk.Label(
            dialog,
            text=f"{ESP32S3_LABEL}\nFirmware: {firmware_text}",
            fg="white", bg=background_color,
            font=scale_font(("Arial", 11, "bold")),
            justify=tk.LEFT,
        )
        info_label.pack(pady=(int(16 * scaling_factor), int(4 * scaling_factor)), padx=int(16 * scaling_factor), anchor=tk.W)

        port_frame = tk.Frame(dialog, bg=background_color)
        port_frame.pack(fill=tk.X, padx=int(16 * scaling_factor), pady=(0, int(4 * scaling_factor)))
        tk.Label(port_frame, text="Flashing Port:", fg="white", bg=background_color,
                 font=scale_font(("Arial", 10, "bold"))).pack(side=tk.LEFT)
        port_choice = tk.StringVar()
        port_combo = ttk.Combobox(port_frame, textvariable=port_choice, state="readonly",
                                  width=40, font=scale_font(("Arial", 9)))
        port_combo.pack(side=tk.LEFT, padx=(int(8 * scaling_factor), 0), fill=tk.X, expand=True)
        port_lookup = {}

        def refresh_port_choices():
            try:
                from usb_serial_bridge import list_bridge_port_candidates, format_port_label
                ports = list_bridge_port_candidates()
            except Exception as e:
                logger.debug(f"ESP32-S3 port list refresh failed: {e}")
                ports = []
            values = ["Auto"]
            port_lookup.clear()
            for item in ports:
                verified = bool(status and status.serial_port
                                and status.serial_port.port.upper() == item.port.upper()
                                and getattr(status, "firmware_installed", False))
                label = format_port_label(item, verified=verified)
                values.append(label)
                port_lookup[label] = item.port
            port_combo["values"] = values
            configured = str(getattr(CONFIG, "esp32_serial_port", "") or "").upper()
            if getattr(CONFIG, "esp32_serial_port_mode", "auto") == "manual":
                selected = next((label for label, port in port_lookup.items()
                                 if port.upper() == configured), "Auto")
            else:
                selected = "Auto"
            port_choice.set(selected)

        def select_port(_event=None):
            label = port_choice.get()
            selected_port = port_lookup.get(label, "")
            CONFIG.esp32_serial_port_mode = "manual" if selected_port else "auto"
            CONFIG.esp32_serial_port = selected_port.upper()
            CONFIG.save_config()
            dialog_state["probe_running"] = True

            def worker():
                try:
                    from usb_serial_bridge import detect_bridge
                    selected_status = detect_bridge(
                        selected_port or None, allow_unverified=True)
                except Exception as e:
                    logger.debug(f"ESP32-S3 selected port probe failed: {e}")
                    selected_status = None
                def apply():
                    dialog_state["probe_running"] = False
                    if not dialog.winfo_exists():
                        return
                    self.esp32s3_bridge_status = selected_status
                    self.esp32s3_detected = bool(
                        selected_status and getattr(selected_status, "board_present", False))
                    render_status(selected_status)
                dialog.after(0, apply)
            threading.Thread(target=worker, daemon=True).start()

        port_combo.bind("<<ComboboxSelected>>", select_port)
        tk.Button(port_frame, text="Refresh", bg=button_gray, fg=text_color,
                  bd=0, relief=tk.FLAT, font=scale_font(("Arial", 9, "bold")),
                  command=refresh_port_choices).pack(side=tk.LEFT, padx=(int(6 * scaling_factor), 0))
        refresh_port_choices()

        boot_status_label = tk.Label(
            dialog, text="", fg="white", bg="#1E1E1E",
            font=scale_font(("Arial", 9, "bold")), justify=tk.LEFT,
            wraplength=int(440 * scaling_factor),
        )
        boot_status_label.pack(padx=int(16 * scaling_factor), anchor=tk.W)

        # Progress bar (hidden until operation starts)
        progress_var = tk.DoubleVar(value=0)
        progress_bar = ttk.Progressbar(
            dialog, orient=tk.HORIZONTAL, mode="determinate", maximum=100,
            variable=progress_var, length=int(380 * scaling_factor),
        )
        percent_label = tk.Label(dialog, text="0%", fg="white", bg="#1E1E1E",
                                 font=scale_font(("Arial", 11, "bold")))

        # Result label (hidden until done)
        result_label = tk.Label(
            dialog, text="", fg="lightgreen", bg="#1E1E1E",
            font=scale_font(("Arial", 10, "bold")),
            wraplength=int(440 * scaling_factor), justify=tk.CENTER,
        )

        # Phase 1: action selection buttons
        sel_frame = tk.Frame(dialog, bg="#1E1E1E")
        sel_frame.pack(pady=int(8 * scaling_factor))
        action_buttons = {}

        def close_dialog():
            self._esp32s3_waiting_for_removal = False
            resume_callback = getattr(dialog, "_esp32s3_resume_after_close", None)
            if resume_callback is not None:
                dialog._esp32s3_resume_after_close = None
                resume_callback()
            try:
                dialog.grab_release()
            except Exception:
                pass
            dialog.destroy()

        def render_status(new_status):
            dialog_state["status"] = new_status
            current_otg = bool(new_status and getattr(new_status, "otg_only", False))
            current_boot = current_otg and not bool(
                new_status and getattr(new_status, "firmware_installed", False))
            if new_status and getattr(new_status, "bridge_ready", False):
                firmware = f"Installed ({getattr(new_status, 'firmware_version', '')})"
            elif new_status and getattr(new_status, "firmware_current", False):
                firmware = (
                    f"Installed ({getattr(new_status, 'firmware_version', '')}, waiting for USB transport)")
            elif new_status and getattr(new_status, "firmware_update_required", False):
                current = getattr(new_status, "firmware_version", "") or "unknown"
                expected = getattr(new_status, "expected_version", "") or "bundled"
                firmware = f"Update required ({current} -> {expected})"
            elif new_status and getattr(new_status, "unverified_candidate", False):
                firmware = "Unverified flashing candidate"
            elif new_status and getattr(new_status, "board_present", False):
                if (getattr(CONFIG, "esp32_serial_port_mode", "auto") == "manual"
                        and not getattr(new_status, "firmware_installed", False)
                        and not current_boot):
                    firmware = "Selected port did not answer ESP32-S3 firmware status"
                else:
                    firmware = "Boot mode" if current_boot else "Detected, waiting for status"
            else:
                firmware = "Not installed"
            port = (new_status.serial_port.port
                    if new_status and new_status.serial_port else "CH343/COM not detected")
            info_label.config(text=f"{ESP32S3_LABEL}\nFirmware: {firmware}")
            if current_boot:
                boot_status_label.config(
                    text="OTG Boot mode detected — ready to install firmware.", fg="#55CC55")
            elif current_otg:
                boot_status_label.config(
                    text=("OTG port detected (firmware running). Please enter Boot mode first:\n"
                          "Hold BOOT, tap RESET once, release BOOT — then click Install."),
                    fg="#FF8800")
            else:
                boot_status_label.config(text="")
            flash_button_state = tk.NORMAL if (not current_otg or current_boot) else tk.DISABLED
            for action in ("install", "repair"):
                button = action_buttons.get(action)
                if button is not None:
                    button.config(state=flash_button_state)

        def poll_boot_status():
            if not dialog.winfo_exists() or dialog_state["operation_started"]:
                return
            if dialog_state["probe_running"]:
                # A manual selection/refresh may overlap this tick.  Do not let
                # that one overlap permanently stop the live OTG/Boot monitor.
                dialog.after(100, poll_boot_status)
                return
            dialog_state["probe_running"] = True

            def worker():
                detected_status = None
                succeeded = False
                try:
                    from usb_serial_bridge import detect_bridge
                    detected_status = detect_bridge(allow_unverified=True)
                    succeeded = True
                except Exception as e:
                    logger.debug(f"ESP32-S3 dialog status refresh failed: {e}")

                def apply():
                    dialog_state["probe_running"] = False
                    if not dialog.winfo_exists() or dialog_state["operation_started"]:
                        return
                    if succeeded:
                        self.esp32s3_bridge_status = detected_status
                        self.esp32s3_detected = bool(
                            detected_status and getattr(detected_status, "board_present", False))
                        render_status(detected_status)
                    dialog.after(500, poll_boot_status)

                try:
                    self.root.after(0, apply)
                except RuntimeError:
                    pass

            threading.Thread(target=worker, daemon=True).start()

        def choose(action):
            current_status = dialog_state["status"]
            current_otg = bool(current_status and getattr(current_status, "otg_only", False))
            current_boot = current_otg and not bool(
                current_status and getattr(current_status, "firmware_installed", False))
            if action == "delete":
                if not messagebox.askyesno(ESP32S3_LABEL, "Erase ESP32-S3 N16R8 firmware?", parent=dialog):
                    return

            # OTG port with firmware running — cannot flash until Boot mode is entered.
            # Show guidance in large red text; do NOT attempt to run esptool.
            if current_otg and not current_boot and action in ("install", "repair"):
                sel_frame.pack_forget()
                tk.Label(
                    dialog,
                    text=(
                        "ESP32 is not in Boot mode — firmware cannot be installed.\n\n"
                        "To enter Boot mode:\n"
                        "  1. Hold the BOOT button\n"
                        "  2. Tap RESET once, then release BOOT\n"
                        "  3. Wait for Status to show \"Boot\", then click Install"
                    ),
                    fg="#FF3333", bg="#1E1E1E",
                    font=scale_font(("Arial", 12, "bold")),
                    justify=tk.LEFT,
                    wraplength=int(440 * scaling_factor),
                ).pack(pady=int(10 * scaling_factor), padx=int(16 * scaling_factor), anchor=tk.W)
                close_btn_frame = tk.Frame(dialog, bg=button_gray)
                close_btn_frame.pack(pady=int(6 * scaling_factor))
                tk.Button(
                    close_btn_frame, text="Close", bg=button_gray, fg=text_color,
                    bd=0, relief=tk.FLAT, font=scale_font(("Arial", 10, "bold")), width=8,
                    command=close_dialog,
                ).pack(padx=int(2 * scaling_factor), pady=int(2 * scaling_factor))
                dialog.protocol("WM_DELETE_WINDOW", close_dialog)
                return

            # Transition: hide buttons, show progress
            dialog_state["operation_started"] = True
            sel_frame.pack_forget()
            progress_bar.pack(padx=int(24 * scaling_factor), fill=tk.X)
            percent_label.pack(pady=(int(8 * scaling_factor), 0))
            dialog.protocol("WM_DELETE_WINDOW", lambda: None)

            def on_flash_done(ok, message):
                progress_bar.pack_forget()
                percent_label.pack_forget()
                is_boot_guidance = not ok and message.startswith("Could not enter flashing mode")
                result_label.config(
                    text=message,
                    fg="lightgreen" if ok else "#FF3333",
                    font=scale_font(("Arial", 12, "bold")) if is_boot_guidance else scale_font(("Arial", 10, "bold")),
                )
                result_label.pack(pady=int(8 * scaling_factor), padx=int(16 * scaling_factor))
                close_btn_frame = tk.Frame(dialog, bg=button_gray)
                close_btn_frame.pack(pady=int(6 * scaling_factor))
                tk.Button(
                    close_btn_frame, text="Close", bg=button_gray, fg=text_color,
                    bd=0, relief=tk.FLAT, font=scale_font(("Arial", 10, "bold")), width=8,
                    command=close_dialog,
                ).pack(padx=int(2 * scaling_factor), pady=int(2 * scaling_factor))
                dialog.protocol("WM_DELETE_WINDOW", close_dialog)

            self._run_flash_in_dialog(
                action, current_status, dialog, info_label, progress_var, percent_label, on_flash_done)

        for text, action in (("Install", "install"), ("Repair", "repair"), ("Delete", "delete")):
            frame = tk.Frame(sel_frame, bg=button_gray)
            frame.pack(side=tk.LEFT, padx=int(6 * scaling_factor))
            action_button = tk.Button(
                frame, text=text, bg=button_gray, fg=text_color, bd=0, relief=tk.FLAT,
                font=scale_font(("Arial", 10, "bold")), width=8,
                command=lambda a=action: choose(a),
            )
            action_button.pack(padx=int(2 * scaling_factor), pady=int(2 * scaling_factor))
            action_buttons[action] = action_button

        cancel_frame = tk.Frame(sel_frame, bg=button_gray)
        cancel_frame.pack(side=tk.LEFT, padx=int(6 * scaling_factor))
        tk.Button(
            cancel_frame, text="Cancel", bg=button_gray, fg=text_color, bd=0, relief=tk.FLAT,
            font=scale_font(("Arial", 10, "bold")), width=8, command=close_dialog,
        ).pack(padx=int(2 * scaling_factor), pady=int(2 * scaling_factor))

        render_status(status)
        dialog.update_idletasks()
        dialog.deiconify()
        dialog.lift()
        dialog.grab_set()
        dialog.after(500, poll_boot_status)

    def _show_boot_mode_prompt(self, label="ESP32-S3 CDC"):
        dialog_w = int(480 * scaling_factor)
        dialog_h = int(220 * scaling_factor)
        dialog = tk.Toplevel(self.root)
        dialog.title(label)
        dialog.resizable(False, False)
        dialog.config(bg=background_color)
        dialog.transient(self.root)
        dialog.grab_set()
        apply_window_dark_theme_and_icon(dialog, background_color)
        self.root.update_idletasks()
        rx = self.root.winfo_x()
        ry = self.root.winfo_y()
        rw = self.root.winfo_width()
        rh = self.root.winfo_height()
        dx = rx + (rw - dialog_w) // 2
        dy = ry + (rh - dialog_h) // 2
        dialog.geometry(f"{dialog_w}x{dialog_h}+{dx}+{dy}")

        tk.Label(
            dialog,
            text=(
                "ESP32-S3 is connected via OTG / native USB.\n\n"
                "Firmware cannot be flashed automatically on this port.\n\n"
                "To install firmware, please:\n"
                "  1. Hold the BOOT button on the ESP32-S3 board\n"
                "  2. Tap the RESET button once, then release BOOT\n"
                "  3. Connect the CH343P / UART Type-C port and retry."
            ),
            fg="white", bg=background_color,
            font=scale_font(("Arial", 10, "bold")),
            justify=tk.LEFT,
            wraplength=int(440 * scaling_factor),
        ).pack(pady=int(16 * scaling_factor), padx=int(16 * scaling_factor), anchor=tk.W)

        close_frame = tk.Frame(dialog, bg=button_gray)
        close_frame.pack(pady=int(6 * scaling_factor))
        tk.Button(
            close_frame, text="OK", bg=button_gray, fg=text_color, bd=0, relief=tk.FLAT,
            font=scale_font(("Arial", 10, "bold")), width=8,
            command=lambda: (dialog.grab_release(), dialog.destroy()),
        ).pack(padx=int(2 * scaling_factor), pady=int(2 * scaling_factor))

    def _run_flash_in_dialog(self, action, status, dialog, info_label, progress_var, percent_label, on_done):
        try:
            from usb_serial_bridge import ESP32S3_LABEL, flash_firmware
        except Exception:
            ESP32S3_LABEL = "ESP32-S3 CDC"
            flash_firmware = None

        self._esp32s3_firmware_busy = True
        discoverer_was_running = False
        if hasattr(self, 'discoverer_thread') and self.discoverer_thread and self.discoverer_thread.is_alive():
            discoverer_was_running = True
            self.stop_discoverer_thread()

        from discoverer import emergency_cleanup
        emergency_cleanup()

        try:
            from usb_serial_bridge import close_all_clients
            close_all_clients()
        except Exception:
            pass

        if not status or not status.serial_port:
            self._esp32s3_firmware_busy = False
            if discoverer_was_running:
                self.start_discoverer_thread()
            on_done(False, "Could not find the ESP32-S3 N16R8 CH343/COM flashing port.\nConnect the flashing port and try again.")
            return

        verb_map = {"install": "Installing", "repair": "Repairing", "delete": "Deleting"}
        if dialog.winfo_exists():
            info_label.config(
                text=f"{ESP32S3_LABEL}: {verb_map.get(action, 'Working')} firmware on {status.serial_port.port}..."
            )

        done = {"ok": False, "error": None}
        progress_queue_obj = queue.Queue()

        def progress(payload):
            progress_queue_obj.put(("progress", payload))

        def worker():
            try:
                flash_firmware(status.serial_port.port, mode=action, progress=progress)
                done["ok"] = True
            except Exception as e:
                done["error"] = e
                logger.exception("ESP32-S3 firmware task failed")
            finally:
                progress_queue_obj.put(("done", None))

        def apply_progress(payload):
            current = float(progress_var.get())
            percent = None
            if isinstance(payload, dict):
                if "percent" in payload:
                    percent = float(payload["percent"])
                elif "write_percent" in payload:
                    percent = 25.0 + (max(0.0, min(100.0, float(payload["write_percent"]))) * 0.70)
            else:
                text = str(payload)
                m = re.search(r"\((\d{1,3})\s*%\)", text)
                if m:
                    percent = 25.0 + (max(0.0, min(100.0, float(m.group(1)))) * 0.70)
            if percent is None:
                # Plain esptool log lines are diagnostic text, not progress.
                percent = current
            percent = max(current, min(100.0, percent))
            progress_var.set(percent)
            if dialog.winfo_exists():
                percent_label.config(text=f"{int(percent)}%")

        def finish():
            discovery_resumed = {"value": False}

            def resume_discovery(reinserted_status=None):
                if discovery_resumed["value"]:
                    return
                discovery_resumed["value"] = True
                self._esp32s3_firmware_busy = False
                if discoverer_was_running:
                    startup_context = None
                    if (reinserted_status
                            and getattr(reinserted_status, "bridge_ready", False)
                            and getattr(reinserted_status, "firmware_current", False)
                            and getattr(reinserted_status, "serial_port", None)):
                        startup_context = {
                            "status": reinserted_status,
                            "observed_mono": time.monotonic(),
                        }
                    self.start_discoverer_thread(startup_context)

            if done["ok"]:
                try:
                    from usb_serial_bridge import close_all_clients
                    close_all_clients()
                except Exception:
                    pass
                progress_var.set(100)
                if dialog.winfo_exists():
                    percent_label.config(text="100%")
                if action == "delete":
                    on_done(True, "ESP32-S3 N16R8 firmware uninstalled successfully.")
                    self.refresh_esp32s3_status()
                    resume_discovery()
                else:
                    on_done(
                        True,
                        "ESP32-S3 N16R8 firmware installed successfully.\n\n"
                        "Please replug the ESP32-S3 USB cable (unplug then reinsert) "
                        "to complete initialization and avoid port conflicts.",
                    )
                    def dialog_exists():
                        try:
                            return bool(dialog.winfo_exists())
                        except Exception:
                            return False

                    def close_after_replug_event(event, detected_status):
                        if not dialog_exists():
                            resume_discovery(
                                detected_status if event == "reinserted" else None)
                            return
                        try:
                            dialog.grab_release()
                        except Exception:
                            pass
                        dialog.destroy()
                        resume_discovery(
                            detected_status if event == "reinserted" else None)

                    # Let the esptool hard-reset/re-enumeration settle first, then
                    # close this completed-install dialog when the user unplugs it.
                    self._esp32s3_waiting_for_removal = True
                    dialog._esp32s3_resume_after_close = resume_discovery
                    self.root.after(
                        1500,
                        lambda: self.wait_for_esp32s3_removal_then(
                            close_after_replug_event, dialog_exists))
            else:
                self._esp32s3_firmware_busy = False
                error_str = str(done["error"])
                try:
                    from usb_serial_bridge import flash_log, get_flash_log_path
                    flash_log(f"flash failed: {error_str}")
                    _log_path = get_flash_log_path()
                except Exception:
                    _log_path = ""
                if ("Could not communicate with ESP32-S3" in error_str
                        or ("Could not put ESP32-S3" in error_str
                            and "into flashing mode" in error_str)):
                    on_done(False, (
                        "Could not enter flashing mode.\n\n"
                        "To enter Boot mode manually:\n"
                        "  1. Hold the BOOT button\n"
                        "  2. Tap RESET once, then release BOOT\n"
                        "  3. Click Repair to retry\n\n"
                        f"Details logged to:\n{_log_path}"
                    ))
                else:
                    on_done(False, f"ESP32-S3 N16R8 firmware operation failed:\n{done['error']}")
                self.refresh_esp32s3_status()
                if discoverer_was_running:
                    self.start_discoverer_thread()

        def poll():
            should_finish = False
            while True:
                try:
                    kind, payload = progress_queue_obj.get_nowait()
                except queue.Empty:
                    break
                if kind == "progress":
                    if dialog.winfo_exists():
                        apply_progress(payload)
                elif kind == "done":
                    should_finish = True
            if should_finish:
                progress_var.set(100)
                if dialog.winfo_exists():
                    percent_label.config(text="100%")
                finish()
            elif dialog.winfo_exists():
                dialog.after(50, poll)

        threading.Thread(target=worker, daemon=True).start()
        dialog.after(50, poll)

    def check_vigembus_installation(self, save=True, prompt_user=False):
        status = get_vigembus_status()
        if status.unknown:
            # The query failed (e.g. pnputil without /properties); asking the user to
            # repair a state we cannot read only nags them. The runtime bus connection
            # is the authoritative answer, so try that before prompting for anything.
            logger.warning("ViGEmBus status undetermined: %s", status.describe())
            if verify_vigembus_runtime(attempts=1):
                CONFIG.vigembus_installed = True
                if save:
                    CONFIG.save_config()
                return True

        if not status.installed:
            CONFIG.vigembus_installed = False
            if save:
                CONFIG.save_config()
            self.update_driver_button()

            if not prompt_user:
                return False

            partial = status.state == VIGEMBUS_PARTIAL
            answer = self.ask_centered_yes_no(
                "Repair ViGEmBus Driver" if partial else "Install ViGEmBus Driver",
                (("ViGEmBus is partially installed and cannot start.\n\n"
                 f"{status.describe()}\n\nDo you want to clean it up and reinstall it now?\n")
                 if partial else
                 ("ViGEmBus driver is not installed.\n\nDo you want to "
                  + ("install" if utils.is_packaged() else "download and install")
                  + " it now?\n")) +
                "(Requires administrator privileges.)"
            )

            if answer:
                if partial and not self.run_vigembus_uninstall():
                    return False
                installed = self.install_vigembus_driver(show_success_msg=True)
                if installed:
                    CONFIG.vigembus_installed = True
                    if save:
                        CONFIG.save_config()
                    return True
            return False

        if verify_vigembus_runtime(attempts=1):
            CONFIG.vigembus_installed = True
            if save:
                CONFIG.save_config()
            return True

        if prompt_user:
            self.show_centered_message(
                "ViGEmBus Connection Error",
                "ViGEmBus files and device are present, but the runtime bus connection failed.\n\n"
                f"{status.describe()}\n\nUse Repair ViGEmBus Driver to cleanly reinstall it."
            )
        if utils.is_packaged():
            # WinUHid is not shipped by the Store build.  Do not silently switch
            # to a driver that the package deliberately cannot install.
            CONFIG.vigembus_installed = False
            if save:
                CONFIG.save_config()
            self.update_driver_button()
            return False
        CONFIG.driver_type = "WinUHid"
        CONFIG.simulation_mode = CONFIG.winuhid_sim_mode
        CONFIG.vigembus_installed = False
        if save:
            CONFIG.save_config()
        if hasattr(self, 'driver_switch'):
            self.driver_switch.set_value("WinUHid")
        self.update_driver_button()
        return False

    def update_header_status(self):
        if not hasattr(self, 'header_label'):
            return
        status = getattr(self, 'esp32s3_bridge_status', None)
        esp32_detected = getattr(self, 'esp32s3_detected', False)

        conn_method = "ESP32-S3" if esp32_detected else "System BLE"

        if status and esp32_detected:
            otg_only = getattr(status, 'otg_only', False)
            fw_installed = getattr(status, 'firmware_installed', False)
            was_ready = getattr(self, '_esp32_header_was_ready', False)
            if getattr(status, 'bridge_ready', False):
                try:
                    import usb_serial_bridge as _usb_sb
                    scan_active = _usb_sb.BRIDGE_SCAN_ACTIVE
                except Exception:
                    scan_active = True
                if scan_active:
                    conn_status = "Ready"
                    status_color = "#55EE99"
                else:
                    conn_status = "Initializing"
                    status_color = "#888888"
            elif otg_only and not fw_installed:
                if was_ready:
                    # Firmware was running but just stopped responding → brief disconnect transition
                    conn_status = "Disconnect"
                    status_color = "#888888"
                else:
                    # OTG in ROM bootloader (no version reported) — ready for manual flash
                    conn_status = "Boot"
                    status_color = "#FF8800"
            elif getattr(status, 'firmware_update_required', False):
                conn_status = "Error"
                status_color = "#FF4444"
            elif getattr(status, 'board_present', False):
                conn_status = "Initializing"
                status_color = "#888888"
            else:
                conn_status = "Initializing"
                status_color = "#888888"
        else:
            try:
                from discoverer import is_system_bluetooth_available
                bt_ok = is_system_bluetooth_available()
            except Exception:
                bt_ok = True
            if bt_ok:
                conn_status = "Ready"
                status_color = "#55EE99"
            else:
                # No Bluetooth radio (or it was switched off): the app keeps running in
                # wired-only mode, so report the USB route rather than a bare "Disconnect"
                # that made it look like nothing could connect at all.
                conn_method = "USB"
                if getattr(self, 'wired_pro2_detected', False):
                    conn_status = "USB Connected"
                    status_color = "#55EE99"
                else:
                    conn_status = "Pending USB Connection"
                    status_color = "#888888"

        if hasattr(self, 'header_label') and self.header_label and self.header_label.winfo_exists():
            try:
                self.header_label.config(text="")
            except Exception:
                pass

        # Update driver installed spots underneath
        try:
            winuhid_state = get_winuhid_status(use_cache=True).state
            hidhide_installed = self._sync_hidhide_installed(save=False, use_cache=True)

            if hasattr(self, 'winuhid_status_dot') and self.winuhid_status_dot and self.winuhid_status_dot.winfo_exists():
                if winuhid_state == WINUHID_HEALTHY:
                    self.winuhid_status_dot.config(text="●", fg="#55EE99")
                    self.winuhid_status_label.config(text=" WinUHid: Installed", fg="#D0D0D0")
                else:
                    self.winuhid_status_dot.config(text="○", fg="#FF6666")
                    self.winuhid_status_label.config(text=" WinUHid: Not Installed", fg="#888888")

            if hasattr(self, 'hidhide_status_dot') and self.hidhide_status_dot and self.hidhide_status_dot.winfo_exists():
                if hidhide_installed:
                    self.hidhide_status_dot.config(text="●", fg="#55EE99")
                    self.hidhide_status_label.config(text=" HidHide: Installed", fg="#D0D0D0")
                else:
                    self.hidhide_status_dot.config(text="○", fg="#FF6666")
                    self.hidhide_status_label.config(text=" HidHide: Not Installed", fg="#888888")
        except Exception as e:
            logger.debug(f"Failed to update driver status spots: {e}")

        # Track whether we were in bridge_ready for next poll's disconnect detection
        self._esp32_header_was_ready = (conn_status == "Ready" and esp32_detected)
        self._esp32_last_rendered_status = conn_status

        # When transitioning to Disconnect, start fast-polling so Boot mode is detected
        # within ~500ms instead of waiting up to 5s for the regular timer.
        if conn_status == "Disconnect" and not getattr(self, '_esp32_fast_poll_active', False):
            self._esp32_fast_poll_active = True
            self._esp32_fast_poll_count = 0
            self.root.after(500, self._esp32_fast_poll)

    def _esp32_fast_poll(self):
        """Poll at 500ms intervals after a Disconnect event until status stabilises."""
        if getattr(self, 'is_quitting', False):
            self._esp32_fast_poll_active = False
            return

        self.refresh_esp32s3_status_async()

        count = getattr(self, '_esp32_fast_poll_count', 0) + 1
        self._esp32_fast_poll_count = count

        # Stop if the last rendered status is no longer "Disconnect", or after 30 polls (15s).
        last_status = getattr(self, '_esp32_last_rendered_status', 'Disconnect')
        if last_status != 'Disconnect' or count >= 30:
            self._esp32_fast_poll_active = False
            self._esp32_fast_poll_count = 0
        else:
            self.root.after(500, self._esp32_fast_poll)

    def init_interface(self):
        # 1. Enable Windows High DPI Mode
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except:
                pass

        try: ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Switch 2 Pro Connect')
        except: pass
        self.root = tk.Tk()
        self.root.tk.call('tk', 'scaling', 1.3333333333333333)
        self.root.withdraw() # Hide while building the UI, then show from start().

        # 2. Re-apply the existing resolution-based scaling rule for the display
        # that owns the saved window position.  DPI deliberately does not enter
        # this calculation: two displays with the same physical resolution must
        # produce the same application scale regardless of Windows' DPI setting.
        x = CONFIG.window_x if CONFIG.window_x is not None else 50
        y = CONFIG.window_y if CONFIG.window_y is not None else 50
        initial_monitor = _monitor_metrics_from_point(x, y)
        try:
            if initial_monitor:
                refresh_ui_scaling(
                    initial_monitor["height"], initial_monitor["work_height"])
                self._ui_monitor_handle = initial_monitor["handle"]
                self._ui_monitor_signature = _monitor_work_signature(
                    initial_monitor)
            else:
                refresh_ui_scaling(self.root.winfo_screenheight())
        except Exception:
            refresh_ui_scaling()

        self.calibration_overlay = CalibrationOverlay(self.root)
        import utils
        utils.show_notification_callback = self.calibration_overlay.update
        utils.joystick_calibration_callback = self.start_joystick_calibration_from_callback
        utils.joystick_calibration_cancel_callback = self.cancel_joystick_calibration_from_callback

        def safe_ui_update():
            if getattr(self, 'discoverer_callback', None):
                self.discoverer_callback(list(VIRTUAL_CONTROLLERS))
        utils.force_ui_update_callback = safe_ui_update
        try:
            from config import get_resource
            from PIL import ImageTk
            photo = ImageTk.PhotoImage(file=get_resource('images/icon.png'))
            self.root.wm_iconphoto(True, photo)
            self._root_icon_ref = photo
        except Exception as e1:
            try:
                from config import get_resource
                photo = tk.PhotoImage(file=get_resource('images/icon.png'))
                self.root.wm_iconphoto(True, photo)
                self._root_icon_ref = photo
            except Exception as e2:
                logger.debug(f"Failed to set root window icon: e1={e1}, e2={e2}")
        self.root.title("Switch 2 Pro Connect")
        self.root.protocol("WM_DELETE_WINDOW", self.handle_window_delete)
        
        # 3. Handle window geometry & minsize (remembering position)
        desired_w = int(
            BASE_WINDOW_WIDTH * window_resolution_ratio
            * _normalized_user_ui_scale())
        desired_h = int(BASE_WINDOW_HEIGHT * window_resolution_ratio)
        initial_fit = _fit_window_to_work_area(
            initial_monitor, desired_w, desired_h, x=x, y=y)
        default_w = initial_fit["client_width"]
        default_h = initial_fit["client_height"]
        x, y = initial_fit["x"], initial_fit["y"]
        self.root.geometry(f"{default_w}x{default_h}+{x}+{y}")
        self.root.minsize(default_w, default_h)
        self.root.config(bg=background_color, padx=int(8 * scaling_factor), pady=int(6 * scaling_factor))
        self.root.bind("<Configure>", self.on_configure)
        self.root.bind("<Map>", self._relayout_after_restore, add="+")
        
        # Set title bar color to match background
        try:
            self.root.update()
            hwnd = _top_level_hwnd(self.root)
            if not hwnd:
                raise RuntimeError("Could not resolve Tk top-level HWND")
            self.top_hwnd = hwnd
            logger.info(
                "Tk HWND resolved: widget=%s top_level=%s rect=%s state=%s",
                self.root.winfo_id(), hwnd, win32gui.GetWindowRect(hwnd),
                self.root.state())
            color = background_color.lstrip('#')
            r, g, b = int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)
            color_int = (b << 16) | (g << 8) | r # BGR format
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(ctypes.c_int(color_int)), 4) # Caption color
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(ctypes.c_int(0xFFFFFF)), 4)  # Title text color (White)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(ctypes.c_int(1)), 4)         # Immersive dark mode
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(ctypes.c_int(2)), 4)         # Rounded corners
            
            # Force the geometry, minsize, and scaling factor back to defaults to overwrite any initial scaling applied during update()
            self.root.tk.call('tk', 'scaling', 1.3333333333333333)
            self.root.geometry(f"{default_w}x{default_h}+{x}+{y}")
            self.root.minsize(default_w, default_h)
            self.root.update()
            actual_monitor = _monitor_metrics_from_window(hwnd) or initial_monitor
            actual_fit = _fit_window_to_work_area(
                actual_monitor, desired_w, desired_h, hwnd=hwnd, x=x, y=y)
            default_w = actual_fit["client_width"]
            default_h = actual_fit["client_height"]
            x, y = actual_fit["x"], actual_fit["y"]
            self.root.minsize(default_w, default_h)
            self.root.geometry(f"{default_w}x{default_h}+{x}+{y}")
            win32gui.SetWindowPos(
                int(hwnd), 0, x, y,
                actual_fit["outer_width"], actual_fit["outer_height"],
                win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE)
            self.root.update_idletasks()
            stable_rect = win32gui.GetWindowRect(hwnd)
            self._ui_window_dpi = _get_window_dpi(hwnd)
            self._dpi_independent_client_size = (default_w, default_h)
            self._dpi_independent_outer_size = (
                stable_rect[2] - stable_rect[0],
                stable_rect[3] - stable_rect[1],
            )
            self._dpi_independent_outer_position = (
                stable_rect[0], stable_rect[1])
        except Exception as e:
            logger.debug(f"Failed to initialize native window appearance: {e}")

        # Dropdown (Combobox) Styling
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TCombobox", 
                        fieldbackground=button_gray, 
                        background=button_gray, 
                        foreground="white", 
                        arrowcolor="white",
                        borderwidth=0,
                        relief="flat",
                        bordercolor=button_gray,
                        darkcolor=button_gray,
                        lightcolor=button_gray,
                        font=scale_font(("Arial", 11, "bold")))
        style.map("TCombobox", 
                  fieldbackground=[('readonly', button_gray)],
                  background=[('readonly', button_gray), ('active', button_gray), ('pressed', button_gray)],
                  foreground=[('readonly', 'white')],
                  bordercolor=[('readonly', button_gray)],
                  lightcolor=[('readonly', button_gray)],
                  darkcolor=[('readonly', button_gray)])
        
        self.root.option_add("*TCombobox*Listbox.background", button_gray)
        self.root.option_add("*TCombobox*Listbox.foreground", "white")
        self.root.option_add("*TCombobox*Listbox.selectBackground", highlight_color)
        self.root.option_add("*TCombobox*Listbox.selectForeground", "white")
        self.root.option_add("*TCombobox*Listbox.font", scale_font(("Arial", 11, "bold")))
        self.root.option_add("*TCombobox*Listbox.borderwidth", 0)
        self.root.option_add("*TCombobox*Listbox.highlightthickness", 0)
        self.root.option_add("*TCombobox*Listbox.relief", "flat")

        # Modern Scrollbar Styling for Dropdowns
        style.configure("Vertical.TScrollbar", 
                        gripcount=0,
                        background=button_gray,
                        troughcolor=background_color,
                        borderwidth=0,
                        arrowsize=0,
                        relief="flat")
        style.map("Vertical.TScrollbar",
                  background=[('pressed', highlight_color), ('active', highlight_color)],
                  troughcolor=[('pressed', background_color), ('active', background_color)])

        self.font = tkFont.Font(family="Arial", size=int(15 * scaling_factor), weight="bold")
        
        try:
            hint_img = Image.open(get_resource("images/pairing_hint.png"))
            hw, hh = hint_img.size
            target_scale = 0.62 * scaling_factor
            hint_img = hint_img.resize((max(1, int(hw * target_scale)), max(1, int(hh * target_scale))), Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.ANTIALIAS)
            self.pairing_hint_image = ImageTk.PhotoImage(hint_img)
        except Exception as e:
            logger.error(f"Failed to load/scale pairing hint image: {e}")
            self.pairing_hint_image = tk.PhotoImage(file=get_resource("images/pairing_hint.png"))

        # Side-by-side layout: Centered cluster with left controller panel and right settings panel
        self.content_container = tk.Frame(self.root, bg=background_color)
        self.content_container.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=0)

        self.center_cluster = tk.Frame(self.content_container, bg=background_color)
        self.center_cluster.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        # Left Column: Controller graphic / Player info
        self.left_column = tk.Frame(self.center_cluster, bg=background_color)
        self.left_column.pack(side=tk.LEFT, padx=0)

        self.main_frame = tk.Frame(self.left_column, bg=background_color)
        self.main_frame.pack()
        self.players_info = None
        self._layout_connected_state = False
        self._slide_animation_id = None

        # Right Column: Settings, Profile, Action Buttons, Back Buttons
        self.right_column = tk.Frame(self.center_cluster, bg=background_color)
        self.scroll_content_frame = self.right_column

        # Bottom footer bar — connection method + status, Driver spots, and Settings Gear
        self.footer_frame = tk.Frame(self.root, bg=background_color, height=int(40 * scaling_factor))
        self.footer_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, int(4 * scaling_factor)))
        self.footer_frame.pack_propagate(False)

        # Settings gear icon button (bottom-right corner) with rounded edges
        try:
            self.gear_btn = make_rounded_button(
                self.footer_frame,
                width=34,
                height=30,
                radius=6,
                bg_color=button_gray,
                hover_color="#5A5A5A",
                press_color="#3A3A3A",
                parent_bg=background_color,
                icon_image="images/gear.png",
                icon_size=(20, 20),
                command=self.toggle_settings_popup,
            )
        except Exception as e:
            self.gear_btn = make_rounded_button(
                self.footer_frame,
                text="⚙",
                font=scale_font(("Arial", 14, "bold")),
                width=34,
                height=30,
                radius=6,
                bg_color=button_gray,
                hover_color="#5A5A5A",
                press_color="#3A3A3A",
                parent_bg=background_color,
                command=self.toggle_settings_popup,
            )
        self.gear_btn.pack(side=tk.RIGHT, padx=(0, int(16 * scaling_factor)))
        Tooltip(self.gear_btn, lambda: "Settings")

        if MAG_TESTER_BUILD_ENABLED:
            self.mag_tester_button = make_rounded_button(
                self.footer_frame,
                text="Mag Tester",
                width=70,
                height=24,
                radius=4,
                command=self.open_mag_tester,
                font=scale_font(("Arial", 8, "bold"))
            )
            self.mag_tester_button.pack(side=tk.LEFT, padx=(int(12 * scaling_factor), 0))

        # Status text & driver spots centered horizontally in bottom footer
        self.footer_status_container = tk.Frame(self.footer_frame, bg=background_color)
        self.footer_status_container.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        self.header_label = tk.Label(self.footer_status_container, bg=background_color)

        # Spots showing if drivers are installed
        self.footer_drivers_frame = tk.Frame(self.footer_status_container, bg=background_color)
        self.footer_drivers_frame.pack(side=tk.TOP)

        self.winuhid_status_dot = tk.Label(self.footer_drivers_frame, text="●", fg="#55EE99", bg=background_color, font=scale_font(("Arial", 8, "bold")))
        self.winuhid_status_dot.pack(side=tk.LEFT)
        self.winuhid_status_label = tk.Label(self.footer_drivers_frame, text=" WinUHid: Installed", fg="#D0D0D0", bg=background_color, font=scale_font(("Arial", 8, "bold")))
        self.winuhid_status_label.pack(side=tk.LEFT, padx=(0, int(8 * scaling_factor)))

        self.footer_driver_sep = tk.Label(self.footer_drivers_frame, text="|", fg="#666666", bg=background_color, font=scale_font(("Arial", 8, "bold")))
        self.footer_driver_sep.pack(side=tk.LEFT, padx=(0, int(8 * scaling_factor)))

        self.hidhide_status_dot = tk.Label(self.footer_drivers_frame, text="●", fg="#55EE99", bg=background_color, font=scale_font(("Arial", 8, "bold")))
        self.hidhide_status_dot.pack(side=tk.LEFT)
        self.hidhide_status_label = tk.Label(self.footer_drivers_frame, text=" HidHide: Installed", fg="#D0D0D0", bg=background_color, font=scale_font(("Arial", 8, "bold")))
        self.hidhide_status_label.pack(side=tk.LEFT)

        self.init_settings_panel()

        self.update_driver_button()
        self.update_usbip_button()
        self.update_driver_buttons_visibility()

        self.update([None])

        def get_focusable_widgets(parent, lst=None):
            if lst is None:
                lst = []
            if parent.winfo_ismapped():
                if isinstance(parent, (tk.Button, ttk.Combobox, tk.Scale, tk.Entry, tk.Checkbutton, tk.Radiobutton)) or getattr(parent, 'is_custom_recording_entry', False):
                    try:
                        if parent.cget('state') != 'disabled' and parent.cget('state') != tk.DISABLED:
                            lst.append(parent)
                    except:
                        lst.append(parent)
                for child in parent.winfo_children():
                    get_focusable_widgets(child, lst)
            return lst
            
        def spatial_navigate(current_widget, direction):
            # Modal scoping: a grabbed dialog Toplevel wins over Frame popups; while either
            # is open restrict navigation to it so focus can't escape into the main window.
            _dialog = self._nav_top_dialog()
            in_dialog = _dialog is not None
            if in_dialog:
                # FocusOutline draws on self.root (behind the Toplevel), so use native
                # focus_set for every dialog widget instead.
                widgets = get_focusable_widgets(_dialog)
            else:
                _attr, _top_frame, _top_anchor = self._nav_top_popup()
                if _top_frame is not None:
                    widgets = get_focusable_widgets(_top_frame)
                    if isinstance(_top_anchor, tk.Widget):
                        try:
                            if (_top_anchor.winfo_exists() and _top_anchor.winfo_ismapped()
                                    and _top_anchor not in widgets):
                                widgets.append(_top_anchor)
                        except Exception:
                            pass
                else:
                    widgets = get_focusable_widgets(self.root)
            if not widgets: return

            def _select(target):
                if isinstance(target, tk.Button) and not in_dialog:
                    self.root.focus_set()
                    try: self.focus_outline.update(target)
                    except Exception: pass
                else:
                    target.focus_set()
                if not in_dialog:
                    self.root.after_idle(
                        self._ensure_scrolled_widget_visible, target)

            if not current_widget or current_widget not in widgets:
                # Resume at the position we exited from (change: re-entry starts where the
                # user last left off), falling back to the first widget if it's gone.
                resume = getattr(self, "_nav_last_widget", None)
                target = resume if (isinstance(resume, tk.Widget) and resume.winfo_exists() and resume in widgets) else widgets[0]
                _select(target)
                return

            cx = current_widget.winfo_rootx() + current_widget.winfo_width() / 2
            cy = current_widget.winfo_rooty() + current_widget.winfo_height() / 2

            candidates = []
            for w in widgets:
                if w == current_widget: continue
                wx = w.winfo_rootx() + w.winfo_width() / 2
                wy = w.winfo_rooty() + w.winfo_height() / 2
                dx = wx - cx
                dy = wy - cy
                
                # Filter candidates by strictly checking direction
                if direction == "UP" and dy >= -5: continue
                if direction == "DOWN" and dy <= 5: continue
                if direction == "LEFT" and dx >= -5: continue
                if direction == "RIGHT" and dx <= 5: continue
                
                candidates.append((w, dx, dy))
                
            if not candidates: return
            
            best_widget = None
            
            if direction in ("UP", "DOWN"):
                # Sort by vertical distance first to find the closest row
                candidates.sort(key=lambda item: abs(item[2]))
                min_dy = abs(candidates[0][2])
                # Filter candidates that belong to this closest row (within 15px)
                row_candidates = [c for c in candidates if abs(abs(c[2]) - min_dy) < 15]
                # Within this row, pick the one with smallest horizontal distance
                row_candidates.sort(key=lambda item: abs(item[1]))
                best_widget = row_candidates[0][0]
                
            else: # LEFT, RIGHT
                # For Left/Right, prefer staying on the same row.
                candidates.sort(key=lambda item: abs(item[2]))
                same_row_candidates = [c for c in candidates if abs(c[2]) < 15]
                
                if same_row_candidates:
                    same_row_candidates.sort(key=lambda item: abs(item[1]))
                    best_widget = same_row_candidates[0][0]
                else:
                    # If nothing on the same row, find the next closest column overall
                    candidates.sort(key=lambda item: abs(item[1]))
                    min_dx = abs(candidates[0][1])
                    col_candidates = [c for c in candidates if abs(abs(c[1]) - min_dx) < 15]
                    col_candidates.sort(key=lambda item: abs(item[2]))
                    best_widget = col_candidates[0][0]

            if best_widget:
                # For standard buttons (outside a dialog), hide the native dashed focus and
                # draw the FocusOutline instead; in a dialog, use native focus (the outline
                # would be hidden behind the Toplevel).
                _select(best_widget)

        self.focus_outline = FocusOutline(self.root)

        def on_mouse_click(e):
            if getattr(self, 'ui_navigation_active', False):
                self.ui_navigation_active = False
                if hasattr(self, 'focus_outline'):
                    self.focus_outline.hide()
                    
        self.root.bind_all("<Button-1>", on_mouse_click, add='+')

        def on_global_focus_in(e):
            if getattr(self, 'ui_navigation_active', False):
                if isinstance(e.widget, (tk.Button, ttk.Combobox, tk.Scale, tk.Entry, tk.Checkbutton, tk.Radiobutton)) or getattr(e.widget, 'is_custom_recording_entry', False):
                    self.focus_outline.update(e.widget)

        self.root.bind_all("<FocusIn>", on_global_focus_in)
        
        def poll_ui_navigation():
            if not getattr(self, 'root', None) or not self.root.winfo_exists():
                return

            self.root.after(50, poll_ui_navigation)

            from config import SWITCH_BUTTONS

            # Flush the deferred gamepad-edit save once the numeric hold has stopped. Runs
            # every tick (before the focus/state guards below) so suppression never sticks.
            import time as _flush_time
            if getattr(self, "_nav_save_suppressed", False) and (_flush_time.time() - getattr(self, "_nav_num_last_active", 0.0)) > self.NUM_REPEAT_RELEASE_GAP:
                self._nav_save_suppressed = False
                try: CONFIG.suppress_saves(False)
                except Exception: pass

            if getattr(self, 'recording_controllers', False):
                return

            # Direct Back Button Controller Assignment
            if getattr(self, "waiting_for_assign_release", False):
                any_btn = False
                for vc in getattr(self, 'current_controllers', []) or []:
                    if vc is None: continue
                    for c in getattr(vc, 'controllers', []) or []:
                        if getattr(c, 'raw_buttons', 0):
                            any_btn = True
                            break
                if not any_btn:
                    self.waiting_for_assign_release = False
                return

            if getattr(self, "waiting_for_back_button_assign", None):
                key, btn = self.waiting_for_back_button_assign
                detected_token = None
                for vc in getattr(self, 'current_controllers', []) or []:
                    if vc is None: continue
                    for c in getattr(vc, 'controllers', []) or []:
                        raw = getattr(c, 'raw_buttons', 0)
                        last_data = getattr(c, 'last_input_data', None)
                        if raw:
                            for bit, token in [
                                (SWITCH_BUTTONS.get("B", 0x00000004), "B"),
                                (SWITCH_BUTTONS.get("A", 0x00000008), "A"),
                                (SWITCH_BUTTONS.get("Y", 0x00000001), "Y"),
                                (SWITCH_BUTTONS.get("X", 0x00000002), "X"),
                                (SWITCH_BUTTONS.get("ZL", 0x00000080), "ZL"),
                                (SWITCH_BUTTONS.get("L", 0x00000040), "L"),
                                (SWITCH_BUTTONS.get("ZR", 0x00000080), "ZR"),
                                (SWITCH_BUTTONS.get("R", 0x00000040), "R"),
                                (SWITCH_BUTTONS.get("L_STK", 0x00000800), "L_STK"),
                                (SWITCH_BUTTONS.get("R_STK", 0x00000400), "R_STK"),
                                (SWITCH_BUTTONS.get("PLUS", 0x00000200), "PLUS"),
                                (SWITCH_BUTTONS.get("MINUS", 0x00000100), "MINUS"),
                                (SWITCH_BUTTONS.get("UP", 0x00020000), "UP"),
                                (SWITCH_BUTTONS.get("DOWN", 0x00010000), "DOWN"),
                                (SWITCH_BUTTONS.get("LEFT", 0x00080000), "LEFT"),
                                (SWITCH_BUTTONS.get("RIGHT", 0x00040000), "RIGHT"),
                                (SWITCH_BUTTONS.get("CAPT", 0x00002000), "Capture"),
                                (SWITCH_BUTTONS.get("HOME", 0x00001000), "Home"),
                                (SWITCH_BUTTONS.get("C", 0x00004000), "Chat"),
                                (0x00008000, "Chat"),
                                (0x10000000, "Chat"),
                                (0x20000000, "Chat"),
                                (0x02000000, "GL"),
                                (0x08000000, "GL"),
                                (0x01000000, "GR"),
                                (0x04000000, "GR"),
                            ]:
                                if raw & bit:
                                    detected_token = token
                                    break
                        if not detected_token and last_data:
                            extra = getattr(last_data, 'extra_buttons', 0)
                            if extra & 0x0009:
                                detected_token = "GL"
                            elif extra & 0x0006:
                                detected_token = "GR"
                            elif extra & 0x0030:
                                detected_token = "Chat"
                        if not detected_token and last_data:
                            tl = getattr(last_data, 'trigger_l', 0.0)
                            tr = getattr(last_data, 'trigger_r', 0.0)
                            if isinstance(tl, (int, float)) and tl > 0.3:
                                detected_token = "ZL"
                            elif isinstance(tr, (int, float)) and tr > 0.3:
                                detected_token = "ZR"
                        if detected_token:
                            break
                    if detected_token:
                        break

                if detected_token:
                    target_profile = getattr(btn, "target_profile", "ACTIVE_CONTEXT")
                    if target_profile == "ACTIVE_CONTEXT":
                        active_ctx = CONFIG.get_active_game_context()
                        if active_ctx:
                            CONFIG.set_game_mapping(active_ctx, key, detected_token)
                        CONFIG.set_mapping_setting_scoped(key, detected_token)
                    elif target_profile is None:
                        CONFIG.set_game_mapping(None, key, detected_token)
                        if CONFIG.get_active_game_context() is None:
                            CONFIG.set_mapping_setting_scoped(key, detected_token)
                    else:
                        CONFIG.set_game_mapping(target_profile, key, detected_token)
                        if CONFIG.get_active_game_context() == target_profile:
                            CONFIG.set_mapping_setting_scoped(key, detected_token)
                    CONFIG.save_config()
                    btn.set(detected_token)
                    try:
                        btn.config(fg="white")
                    except Exception:
                        pass
                    if hasattr(self, "_refresh_mapping_comboboxes"):
                        self._refresh_mapping_comboboxes()
                    if hasattr(self, "_back_button_assign_timer") and self._back_button_assign_timer:
                        try:
                            self.root.after_cancel(self._back_button_assign_timer)
                        except Exception:
                            pass
                        self._back_button_assign_timer = None
                    if getattr(self, "_back_button_esc_bind_id", None):
                        try:
                            self.root.unbind("<Escape>", self._back_button_esc_bind_id)
                        except Exception:
                            pass
                        self._back_button_esc_bind_id = None
                    self.waiting_for_back_button_assign = None
                    self.waiting_for_assign_release = True
                    return

            def safe_focus_get():
                try:
                    return self.root.focus_get()
                except KeyError:
                    return None

            # Check if OS active window is our app
            try:
                import win32process
                import os
                import ctypes
                hwnd = ctypes.windll.user32.GetForegroundWindow()
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid != os.getpid():
                    return
            except:
                pass

                
            if self.root.state() != 'normal' and self.root.state() != 'zoomed':
                return
                
            from config import SWITCH_BUTTONS
            import time
            current_time = time.time()
            
            if not hasattr(self, 'nav_last_move_time'): self.nav_last_move_time = 0
            if not hasattr(self, 'nav_last_click_time'): self.nav_last_click_time = 0
            if not hasattr(self, 'nav_last_cancel_time'): self.nav_last_cancel_time = 0
            if not hasattr(self, 'ui_navigation_active'): self.ui_navigation_active = False
            if not hasattr(self, 'debug_print_count'): self.debug_print_count = 0
                
            if not hasattr(self, 'nav_last_right_time'): self.nav_last_right_time = 0

            # A modal dialog (grabbed Toplevel, e.g. the reset-confirm) is open: pull
            # gamepad control into it and make sure one of its buttons is selected.
            _dlg = self._nav_top_dialog()
            if _dlg is not None:
                self.ui_navigation_active = True
                _dfocused = safe_focus_get()
                _dbtns = get_focusable_widgets(_dlg)
                if _dbtns and (not isinstance(_dfocused, tk.Widget) or _dfocused not in _dbtns):
                    try: _dbtns[0].focus_set()
                    except Exception: pass

            nav_dir = None
            right_nav_dir = None
            click_pressed = False
            cancel_pressed = False
            
            up_mask = SWITCH_BUTTONS.get("UP", 0x00020000)
            down_mask = SWITCH_BUTTONS.get("DOWN", 0x00010000)
            left_mask = SWITCH_BUTTONS.get("LEFT", 0x00080000)
            right_mask = SWITCH_BUTTONS.get("RIGHT", 0x00040000)
            a_mask = SWITCH_BUTTONS.get("A", 0x00000008) # Physical A button (Right)
            b_mask = SWITCH_BUTTONS.get("B", 0x00000004) # Physical B button (Down)

            # NOTE: CONFIG is the module-level import (top of file). Do NOT re-import it
            # locally here -- a local `from config import CONFIG` would make CONFIG a local
            # for the whole function, breaking the earlier flush (UnboundLocalError) and
            # leaving save suppression stuck on.
            if getattr(CONFIG, 'abxy_mode', 'Switch') == 'Xbox':
                click_mask = b_mask
                cancel_mask = a_mask
            else:
                click_mask = a_mask
                cancel_mask = b_mask
            
            vcs = getattr(self, 'current_controllers', [])
            
            for vc in vcs:
                if vc is None: continue
                for c in vc.controllers:
                    last_data = getattr(c, 'last_input_data', None)
                    if last_data:
                        if not getattr(c, 'is_joycon_right', lambda: False)():
                            lx, ly = last_data.left_stick
                            if lx > 0.5: nav_dir = "RIGHT"
                            elif lx < -0.5: nav_dir = "LEFT"
                            elif ly > 0.5: nav_dir = "UP"
                            elif ly < -0.5: nav_dir = "DOWN"
                        
                        if not getattr(c, 'is_joycon_left', lambda: False)():
                            rx, ry = last_data.right_stick
                            if rx > 0.5: right_nav_dir = "RIGHT"
                            elif rx < -0.5: right_nav_dir = "LEFT"
                            elif ry > 0.5: right_nav_dir = "UP"
                            elif ry < -0.5: right_nav_dir = "DOWN"
                    
                    buttons = getattr(c, 'mapped_buttons', None)
                    if buttons is None:
                        buttons = getattr(c, 'raw_buttons', 0)
                    if buttons & up_mask: nav_dir = "UP"
                    if buttons & down_mask: nav_dir = "DOWN"
                    if buttons & left_mask: nav_dir = "LEFT"
                    if buttons & right_mask: nav_dir = "RIGHT"
                    if buttons & click_mask: click_pressed = True
                    if buttons & cancel_mask: cancel_pressed = True
                        
            if nav_dir or click_pressed or cancel_pressed or right_nav_dir:
                
                # Definitively check if we are currently inside an open combobox popdown via Tcl
                popdown_is_open = False
                popdown = None
                listbox = None
                cb = None
                
                if hasattr(self, 'focus_outline') and self.focus_outline.target_widget:
                    cb = self.focus_outline.target_widget
                    if isinstance(cb, ttk.Combobox):
                        try:
                            popdown = self.root.tk.call('ttk::combobox::PopdownWindow', cb)
                            if self.root.tk.call('winfo', 'exists', popdown) and self.root.tk.call('winfo', 'ismapped', popdown):
                                popdown_is_open = True
                                listbox = f"{popdown}.f.l"
                        except Exception:
                            pass

                if popdown_is_open and listbox:
                    try:
                        # Both Right Stick and Left Stick (D-Pad) can navigate the list
                        if right_nav_dir in ("UP", "DOWN") or nav_dir in ("UP", "DOWN"):
                            if current_time - self.nav_last_right_time > 0.2:
                                self.nav_last_right_time = current_time
                                self.nav_last_move_time = current_time
                                try:
                                    size = int(self.root.tk.call(listbox, 'size'))
                                    if size > 0:
                                        selected = self.root.tk.call(listbox, 'curselection')
                                        if not selected:
                                            curr = 0
                                        else:
                                            curr = int(selected[0]) if isinstance(selected, (tuple, list)) else int(selected)
                                            
                                        if right_nav_dir == "UP" or nav_dir == "UP":
                                            curr -= 1
                                        else:
                                            curr += 1
                                            
                                        if curr < 0: curr = 0
                                        if curr >= size: curr = size - 1
                                        
                                        self.root.tk.call(listbox, 'selection', 'clear', 0, 'end')
                                        self.root.tk.call(listbox, 'selection', 'set', curr)
                                        self.root.tk.call(listbox, 'activate', curr)
                                        self.root.tk.call(listbox, 'see', curr)
                                except Exception as listbox_e:
                                    import logging
                                    logging.getLogger(__name__).error(f"Listbox nav error: {listbox_e}")
                        elif click_pressed and current_time - self.nav_last_click_time > 0.3:
                            self.nav_last_click_time = current_time
                            self.nav_last_cancel_time = current_time # Sync to prevent A/B swap bounce
                            self.root.tk.call('event', 'generate', listbox, '<Return>')
                        elif cancel_pressed and current_time - self.nav_last_cancel_time > 0.3:
                            self.nav_last_cancel_time = current_time
                            self.nav_last_click_time = current_time # Sync to prevent A/B swap bounce
                            self.root.tk.call('event', 'generate', listbox, '<Escape>')
                            
                        # Prevent spatial navigation from taking place while menu is open
                        nav_dir = None
                        click_pressed = False
                        cancel_pressed = False
                        right_nav_dir = None
                    except Exception as e:
                        import logging
                        logging.getLogger(__name__).error(f"Dropdown error: {e}")

            if nav_dir or click_pressed or cancel_pressed:
                import logging
                logging.getLogger(__name__).info(f"Input detected: dir={nav_dir}, click={click_pressed}, cancel={cancel_pressed}")

            if cancel_pressed and self.ui_navigation_active and current_time - self.nav_last_cancel_time > 0.3:
                self.nav_last_cancel_time = current_time
                self.nav_last_click_time = current_time # Sync
                _dlg_b = self._nav_top_dialog()
                if _dlg_b is not None:
                    # Close the modal dialog (destroy releases the grab; both dialog helpers
                    # return their safe default -> treated as cancel). Stay in control mode.
                    try: _dlg_b.destroy()
                    except Exception: pass
                elif self._nav_close_top_popup():
                    pass  # closed the top-most floating window; stay in UI-control mode
                else:
                    # True exit: remember the current selection so re-entry resumes here.
                    self._nav_last_widget = (getattr(self.focus_outline, "target_widget", None) or safe_focus_get())
                    self.ui_navigation_active = False
                    if hasattr(self, 'focus_outline'):
                        self.focus_outline.hide()
                    self.root.focus_set()

            # Numeric text entries use an independent accelerating hold-to-repeat (not the
            # fixed 0.2s throttle). Intercept here and consume the direction so the throttled
            # blocks below don't also adjust the entry or move focus off it.
            if self.ui_navigation_active:
                _nfocus = safe_focus_get()
                if (not _nfocus or _nfocus == self.root) and getattr(getattr(self, "focus_outline", None), "target_widget", None):
                    _nfocus = self.focus_outline.target_widget
                _nup = None
                if self._is_numeric_entry(_nfocus):
                    if right_nav_dir:
                        _nup = right_nav_dir in ("UP", "RIGHT")
                    elif nav_dir and click_pressed:
                        _nup = nav_dir in ("UP", "RIGHT")
                if _nup is not None:
                    # Defer disk saves while actively adjusting; flush once on release (top
                    # of poll). In-memory value + settings_generation still update, so the
                    # runtime effect is immediate -- only the frequent disk write is coalesced.
                    self._nav_num_last_active = current_time
                    if not getattr(self, "_nav_save_suppressed", False):
                        try: CONFIG.suppress_saves(True)
                        except Exception: pass
                        self._nav_save_suppressed = True
                    if self._nav_numeric_hold_should_step(_nfocus, _nup, current_time):
                        self._nav_adjust_numeric_entry(_nfocus, _nup)
                    if right_nav_dir:
                        right_nav_dir = None
                    if nav_dir and click_pressed:
                        nav_dir = None

            if nav_dir and current_time - self.nav_last_move_time > 0.2:
                self.nav_last_move_time = current_time
                self.ui_navigation_active = True
                focused = safe_focus_get()
                if (not focused or focused == self.root) and hasattr(self, 'focus_outline') and self.focus_outline.target_widget:
                    focused = self.focus_outline.target_widget
                
                if click_pressed and isinstance(focused, tk.Scale):
                    try:
                        val = float(focused.get())
                        res = float(focused.cget('resolution')) or 1.0
                        if nav_dir in ("UP", "RIGHT"):
                            val += res
                        else:
                            val -= res
                        focused.set(val)
                    except: pass
                elif click_pressed and isinstance(focused, tk.Entry) and self._nav_adjust_numeric_entry(focused, nav_dir in ("UP", "RIGHT")):
                    pass
                else:
                    spatial_navigate(focused, nav_dir)
                
            if right_nav_dir and self.ui_navigation_active and current_time - self.nav_last_right_time > 0.2:
                self.nav_last_right_time = current_time
                focused = safe_focus_get()
                if (not focused or focused == self.root) and hasattr(self, 'focus_outline') and self.focus_outline.target_widget:
                    focused = self.focus_outline.target_widget
                
                if focused:
                    if isinstance(focused, tk.Entry):
                        self._nav_adjust_numeric_entry(focused, right_nav_dir in ("UP", "RIGHT"))
                    elif isinstance(focused, tk.Scale):
                        try:
                            val = float(focused.get())
                            res = float(focused.cget('resolution')) or 1.0
                            if right_nav_dir in ("UP", "RIGHT"):
                                val += res
                            else:
                                val -= res
                            focused.set(val)
                        except: pass
                    elif isinstance(focused, ttk.Combobox):
                        try:
                            vals = focused['values']
                            if vals:
                                try:
                                    idx = vals.index(focused.get())
                                except ValueError:
                                    idx = 0
                                if right_nav_dir in ("UP", "LEFT"):
                                    idx = (idx - 1) % len(vals)
                                else:
                                    idx = (idx + 1) % len(vals)
                                focused.set(vals[idx])
                                focused.event_generate("<<ComboboxSelected>>")
                        except: pass
                
            if click_pressed and self.ui_navigation_active and current_time - self.nav_last_click_time > 0.3:
                self.nav_last_click_time = current_time
                self.nav_last_cancel_time = current_time # Sync
                focused = safe_focus_get()
                if (not focused or focused == self.root) and hasattr(self, 'focus_outline') and self.focus_outline.target_widget:
                    focused = self.focus_outline.target_widget
                    
                if focused:
                    if isinstance(focused, ttk.Combobox):
                        focused.focus_set() # Regain native focus before trying to open popdown
                        focused.event_generate('<Down>')
                    elif getattr(focused, 'is_custom_recording_entry', False):
                        if callable(getattr(focused, 'restart_custom_recording_fn', None)):
                            focused.restart_custom_recording_fn()
                    elif hasattr(focused, 'invoke') and callable(getattr(focused, 'invoke')):
                        try:
                            focused.invoke()
                        except:
                            pass
                    elif isinstance(focused, tk.Entry):
                        # A on a text entry must NOT type a space (numeric entries are
                        # adjusted via A+direction / right-stick instead). No-op.
                        pass
                    else:
                        try:
                            focused.event_generate('<space>')
                            focused.event_generate('<Return>')
                        except:
                            pass
                            
        # All lazy-independent panels now exist, so perform the first natural
        # width measurement before the withdrawn window is revealed.
        self._reconcile_main_window_width()
        self._show_centered_connection_guide()
        poll_ui_navigation()
        self.root.after(1000, self._poll_monitor_work_area)


    def _init_ui_scale_footer(self):
        pass

    def _sync_ui_scale_footer_height(self):
        pass

    def _init_scrollable_content(self):
        pass

    def _update_content_scrollregion(self, _event=None):
        try:
            self.content_canvas.configure(
                scrollregion=self.content_canvas.bbox("all"))
            needed = (self.scroll_content_frame.winfo_reqheight()
                      > self.content_canvas.winfo_height())
            mapped = bool(self.content_scrollbar.winfo_manager())
            if needed and not mapped:
                self.content_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            elif not needed and mapped:
                self.content_scrollbar.pack_forget()
                self.content_canvas.yview_moveto(0.0)
        except (AttributeError, tk.TclError):
            pass

    def _resize_scroll_content_width(self, event):
        try:
            required = self._measure_scroll_content_width()
            self.content_canvas.itemconfigure(
                self._scroll_content_window,
                width=max(1, event.width, required))
            self._update_content_scrollregion()
        except tk.TclError:
            pass

    def _measure_scroll_content_width(self):
        """Natural width of the widest middle-area panel in physical pixels."""
        widths = []
        try:
            for child in self.scroll_content_frame.winfo_children():
                widths.append(child.winfo_reqwidth())
            # DJG can be hidden inside the selected tab, but it remains the
            # widest supported row and must still participate in measurement.
            for name in ("djg_frame", "gyro_frame", "comp_frame",
                         "auto_disconnect_frame", "settings_frame"):
                widget = getattr(self, name, None)
                if widget is not None and widget.winfo_exists():
                    widths.append(widget.winfo_reqwidth())
        except (AttributeError, tk.TclError):
            pass
        return max([1, *widths])

    def _measure_required_client_width(self):
        """Minimum client width that keeps every fixed and scroll panel inside."""
        try:
            self.root.update_idletasks()
            root_pad = self.root.winfo_pixels(self.root.cget("padx"))
            content_widths = []
            for name in ("header_frame", "content_container", "main_frame", "settings_frame"):
                widget = getattr(self, name, None)
                if widget is not None and widget.winfo_exists():
                    content_widths.append(widget.winfo_reqwidth())
            min_content = (max(content_widths) + (2 * root_pad) + 4) if content_widths else 0
            base = int(BASE_WINDOW_WIDTH * window_resolution_ratio)
            return max(base, min_content)
        except (AttributeError, tk.TclError, TypeError, ValueError):
            return int(BASE_WINDOW_WIDTH * window_resolution_ratio)

    def _queue_width_reconcile(self, delay=0):
        try:
            if self._width_reconcile_after_id is not None:
                self.root.after_cancel(self._width_reconcile_after_id)
            self._width_reconcile_after_id = self.root.after(
                delay, self._reconcile_main_window_width)
        except (AttributeError, tk.TclError):
            self._width_reconcile_after_id = None

    def _reconcile_main_window_width(self):
        """Expand the main window only when real content requires more width."""
        self._width_reconcile_after_id = None
        if getattr(self, "is_quitting", False):
            return
        if getattr(self, "_dynamic_scale_in_progress", False):
            self._queue_width_reconcile(100)
            return
        self._dynamic_scale_in_progress = True
        try:
            hwnd = _top_level_hwnd(self.root)
            if not hwnd or self.root.state() not in ("normal", "withdrawn"):
                return
            monitor = _monitor_metrics_from_window(hwnd)
            rect = win32gui.GetWindowRect(hwnd)
            formula_width = int(
                BASE_WINDOW_WIDTH * window_resolution_ratio
                * _normalized_user_ui_scale())
            required_width = self._measure_required_client_width()
            width = max(formula_width, required_width)
            desired_height = int(BASE_WINDOW_HEIGHT * window_resolution_ratio)
            fitted = _fit_window_to_work_area(
                monitor, width, desired_height, hwnd=hwnd,
                x=rect[0], y=rect[1])
            self.root.minsize(
                fitted["client_width"], fitted["client_height"])
            self.root.geometry(
                f"{fitted['client_width']}x{fitted['client_height']}"
                f"+{fitted['x']}+{fitted['y']}")
            win32gui.SetWindowPos(
                int(hwnd), 0, fitted["x"], fitted["y"],
                fitted["outer_width"], fitted["outer_height"],
                win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE)
            self.root.update_idletasks()
            applied = win32gui.GetWindowRect(hwnd)
            self._dpi_independent_client_size = (
                fitted["client_width"], fitted["client_height"])
            self._dpi_independent_outer_size = (
                applied[2] - applied[0], applied[3] - applied[1])
            self._dpi_independent_outer_position = (applied[0], applied[1])
            logger.info(
                "Main window width reconciled: formula=%d required=%d "
                "applied_client=%d", formula_width, required_width,
                fitted["client_width"])
        except Exception:
            logger.exception("Failed to reconcile main window content width")
        finally:
            self._dynamic_scale_in_progress = False

    def _on_content_mousewheel(self, event):
        try:
            if not self.content_scrollbar.winfo_manager():
                return
            if getattr(event, "num", None) == 4:
                units = -3
            elif getattr(event, "num", None) == 5:
                units = 3
            else:
                units = -int(event.delta / 120) * 3
            if units:
                self.content_canvas.yview_scroll(units, "units")
                return "break"
        except (AttributeError, tk.TclError, TypeError, ValueError):
            pass

    def _on_ui_scale_slider(self, value):
        pass

    def _on_ui_scale_press(self, _event=None):
        pass

    def _on_ui_scale_release(self, _event=None):
        pass

    def _schedule_user_ui_scale(self, value, apply_delay=120):
        value = _normalized_user_ui_scale(value)
        try:
            if self._ui_scale_apply_after_id is not None:
                self.root.after_cancel(self._ui_scale_apply_after_id)
            self._ui_scale_apply_after_id = self.root.after(
                apply_delay, self._apply_user_ui_scale, value)
            if self._ui_scale_save_after_id is not None:
                self.root.after_cancel(self._ui_scale_save_after_id)
            self._ui_scale_save_after_id = self.root.after(
                450, self._save_user_ui_scale, value)
        except tk.TclError:
            pass

    def _save_user_ui_scale(self, value):
        self._ui_scale_save_after_id = None
        CONFIG.ui_scale = _normalized_user_ui_scale(value)
        CONFIG.save_config()

    def _apply_user_ui_scale(self, value):
        global scaling_factor
        self._ui_scale_apply_after_id = None
        value = _normalized_user_ui_scale(value)
        if self._dynamic_scale_in_progress:
            self._on_ui_scale_slider(value)
            return
        old_scale = float(scaling_factor)
        if abs(value - _normalized_user_ui_scale()) < 0.0001:
            return
        self._dynamic_scale_in_progress = True
        try:
            CONFIG.ui_scale = value
            hwnd = _top_level_hwnd(self.root)
            monitor = _monitor_metrics_from_window(hwnd) if hwnd else None
            if monitor:
                refresh_ui_scaling(monitor["height"], monitor["work_height"])
            else:
                refresh_ui_scaling()
            new_scale = float(scaling_factor)
            self._rescale_widget_tree(old_scale, new_scale)
            self._refresh_resolution_scaled_images()
            self.force_refresh_player_slots()
            self.root.update_idletasks()
            formula_width = int(
                BASE_WINDOW_WIDTH * window_resolution_ratio * value)
            required_width = self._measure_required_client_width()
            width = max(formula_width, required_width)
            # User scaling deliberately never changes the monitor-owned height.
            desired_height = int(BASE_WINDOW_HEIGHT * window_resolution_ratio)
            rect = win32gui.GetWindowRect(hwnd) if hwnd else (0, 0, 0, 0)
            fitted = _fit_window_to_work_area(
                monitor, width, desired_height, hwnd=hwnd,
                x=rect[0], y=rect[1])
            width = fitted["client_width"]
            height = fitted["client_height"]
            self.root.minsize(width, height)
            self.root.geometry(
                f"{width}x{height}+{fitted['x']}+{fitted['y']}")
            if hwnd:
                win32gui.SetWindowPos(
                    int(hwnd), 0, fitted["x"], fitted["y"],
                    fitted["outer_width"], fitted["outer_height"],
                    win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE)
            self.root.update_idletasks()
            if hwnd:
                stable_rect = win32gui.GetWindowRect(hwnd)
                self._dpi_independent_client_size = (width, height)
                self._dpi_independent_outer_size = (
                    stable_rect[2] - stable_rect[0],
                    stable_rect[3] - stable_rect[1],
                )
                self._dpi_independent_outer_position = (
                    stable_rect[0], stable_rect[1])
                self._ui_window_dpi = _get_window_dpi(hwnd)
            self.content_canvas.itemconfigure(
                self._scroll_content_window,
                width=max(self.content_canvas.winfo_width(),
                          self._measure_scroll_content_width()))
            self.root.after_idle(self._update_content_scrollregion)
            logger.info(
                "In-app UI scale applied: %.1f; content %.4f -> %.4f; "
                "window=%dx%d formula_width=%d required_width=%d",
                value, old_scale, new_scale, width, height,
                formula_width, required_width)
        except Exception:
            logger.exception("Failed to apply in-app UI scaling")
        finally:
            self._dynamic_scale_in_progress = False

    def _ensure_scrolled_widget_visible(self, widget):
        try:
            current = widget
            while current is not None and current != self.scroll_content_frame:
                current = current.master
            if current != self.scroll_content_frame:
                return
            self.root.update_idletasks()
            top = widget.winfo_rooty() - self.scroll_content_frame.winfo_rooty()
            bottom = top + widget.winfo_height()
            visible_top = self.content_canvas.canvasy(0)
            visible_bottom = visible_top + self.content_canvas.winfo_height()
            total = max(1, self.scroll_content_frame.winfo_reqheight())
            if top < visible_top:
                self.content_canvas.yview_moveto(max(0.0, top / total))
            elif bottom > visible_bottom:
                self.content_canvas.yview_moveto(
                    min(1.0, max(0.0, (bottom - self.content_canvas.winfo_height()) / total)))
        except (AttributeError, tk.TclError):
            pass


    def pack_controls_under_player(self):
        if getattr(self, "settings_frame", None) is not None:
            self.settings_frame.pack_forget()
            self.settings_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(int(5 * scaling_factor), 0))


    @staticmethod
    def _scaled_layout_value(base_value, target_scale, allow_negative=False):
        values = tuple(int(round(value * target_scale))
                       for value in base_value)
        if not allow_negative:
            values = tuple(max(0, value) for value in values)
        return values[0] if len(values) == 1 else values

    def _pixel_layout_value(self, widget, value, source_scale):
        """Normalize a Tk distance (including two-sided padding) to scale 1.0."""
        try:
            parts = widget.tk.splitlist(value)
        except Exception:
            parts = (value,)
        if not parts:
            return None
        pixels = []
        for part in parts:
            if part in (None, ""):
                return None
            try:
                pixels.append(float(widget.winfo_pixels(part)) / source_scale)
            except Exception:
                try:
                    pixels.append(float(part) / source_scale)
                except (TypeError, ValueError):
                    return None
        return tuple(pixels)

    def _rescale_widget_tree(self, old_scale, new_scale):
        """Apply a new absolute scale to the already-created Tk widget tree.

        Widget construction throughout this module deliberately uses physical
        pixels.  Tk has no per-window transform for existing child widgets, so
        retain each widget's first-seen scale-1.0 dimensions and reapply them.
        Character-count widths on labels, buttons and entries are intentionally
        excluded; their pixel size follows their font and geometry manager.
        """
        if old_scale <= 0 or new_scale <= 0:
            return

        common_options = (
            "padx", "pady", "borderwidth", "highlightthickness",
            "insertwidth", "selectborderwidth", "wraplength",
        )
        pixel_sized_classes = {
            "Frame", "Labelframe", "TFrame", "TLabelframe", "Canvas",
            "Scale", "Scrollbar", "TScrollbar", "Panedwindow",
        }

        def visit(widget):
            try:
                children = widget.winfo_children()
            except tk.TclError:
                return
            try:
                baseline = self._dynamic_widget_baselines.get(widget)
                manager = widget.winfo_manager()
                if baseline is None:
                    baseline = {"options": {}, "manager": manager, "layout": {}}
                    option_names = list(common_options)
                    if widget.winfo_class() in pixel_sized_classes:
                        option_names.extend(("width", "height"))
                    if isinstance(widget, tk.Scale):
                        option_names.extend(("length", "sliderlength"))
                    # Some custom Tk subclasses in this module intentionally
                    # override configure() as a write-only convenience method and
                    # return None when called without options. Misc.keys() queries
                    # Tcl directly and therefore remains reliable for introspection.
                    available = set(widget.keys())
                    for option in dict.fromkeys(option_names):
                        if option not in available:
                            continue
                        normalized = self._pixel_layout_value(
                            widget, widget.cget(option), old_scale)
                        if normalized is not None:
                            baseline["options"][option] = normalized

                    if manager in ("pack", "grid", "place"):
                        info = getattr(widget, manager + "_info")()
                        layout_names = (
                            ("padx", "pady", "ipadx", "ipady")
                            if manager in ("pack", "grid")
                            else ("x", "y", "width", "height")
                        )
                        for option in layout_names:
                            value = info.get(option)
                            if value in (None, ""):
                                continue
                            normalized = self._pixel_layout_value(
                                widget, value, old_scale)
                            if normalized is not None:
                                baseline["layout"][option] = normalized

                    if "font" in available:
                        try:
                            font_parts = list(widget.tk.splitlist(widget.cget("font")))
                            if len(font_parts) >= 2:
                                font_size = int(font_parts[1])
                                baseline["font"] = (
                                    font_parts,
                                    abs(font_size) / old_scale,
                                    -1 if font_size < 0 else 1,
                                )
                        except (tk.TclError, TypeError, ValueError):
                            pass
                    self._dynamic_widget_baselines[widget] = baseline

                updates = {
                    option: self._scaled_layout_value(value, new_scale)
                    for option, value in baseline["options"].items()
                }
                if updates:
                    widget.configure(**updates)

                font_data = baseline.get("font")
                if font_data:
                    parts, base_size, sign = font_data
                    parts = list(parts)
                    parts[1] = sign * max(1, int(round(base_size * new_scale)))
                    widget.configure(font=tuple(parts))

                if baseline.get("manager") == manager and baseline["layout"]:
                    layout = {
                        option: self._scaled_layout_value(
                            value, new_scale,
                            allow_negative=manager == "place" and option in ("x", "y"))
                        for option, value in baseline["layout"].items()
                    }
                    getattr(widget, manager + "_configure")(**layout)

            except (tk.TclError, RuntimeError):
                # One unsupported option must not prevent the rest of that
                # container's descendants from being scaled.
                pass
            for child in children:
                visit(child)

        for child in self.root.winfo_children():
            visit(child)

        # This named font is shared by the main action buttons and therefore does
        # not appear as a numeric font tuple on each individual widget.
        try:
            self.font.configure(size=max(1, int(15 * new_scale)))
        except (AttributeError, tk.TclError):
            pass

        try:
            style = ttk.Style(self.root)
            style.configure(
                "TCombobox", font=scale_font(("Arial", 11, "bold")))
            self.root.option_add(
                "*TCombobox*Listbox.font", scale_font(("Arial", 11, "bold")))
        except tk.TclError:
            pass
        self._sync_ui_scale_footer_height()

    def _replace_widget_image(self, parent, old_image, new_image):
        if old_image is None or new_image is None:
            return
        old_name = str(old_image)
        for widget in parent.winfo_children():
            try:
                if "image" in widget.keys() and str(widget.cget("image")) == old_name:
                    widget.configure(image=new_image)
                self._replace_widget_image(widget, old_image, new_image)
            except tk.TclError:
                pass

    def _refresh_resolution_scaled_images(self):
        old_hint = getattr(self, "pairing_hint_image", None)
        try:
            hint_img = Image.open(get_resource("images/pairing_hint.png"))
            width, height = hint_img.size
            target_scale = 0.62 * scaling_factor
            hint_img = hint_img.resize(
                (max(1, int(width * target_scale)),
                 max(1, int(height * target_scale))),
                Image.Resampling.LANCZOS if hasattr(Image, "Resampling")
                else Image.ANTIALIAS)
            self.pairing_hint_image = ImageTk.PhotoImage(hint_img)
            self._replace_widget_image(
                self.root, old_hint, self.pairing_hint_image)
        except Exception as exc:
            logger.debug("Failed to refresh pairing image after display change: %s", exc)

        if getattr(self, "gear_btn", None) is not None:
            try:
                w = int(34 * scaling_factor)
                h = int(30 * scaling_factor)
                r = int(6 * scaling_factor)
                isize = (int(20 * scaling_factor), int(20 * scaling_factor))
                self.gear_btn.image_normal = get_rounded_rect_image(w, h, r, button_gray, parent_bg=background_color, icon_img="images/gear.png", icon_size=isize, parent=getattr(self, "footer_frame", None))
                self.gear_btn.image_hover = get_rounded_rect_image(w, h, r, "#5A5A5A", parent_bg=background_color, icon_img="images/gear.png", icon_size=isize, parent=getattr(self, "footer_frame", None))
                self.gear_btn.image_press = get_rounded_rect_image(w, h, r, "#3A3A3A", parent_bg=background_color, icon_img="images/gear.png", icon_size=isize, parent=getattr(self, "footer_frame", None))
                self.gear_btn.configure(image=self.gear_btn.image_normal)
            except Exception as exc:
                logger.debug("Failed to refresh gear image after display change: %s", exc)

    def _queue_monitor_scale_check(self, delay=80):
        if not getattr(self, "root", None) or getattr(self, "is_quitting", False):
            return
        try:
            if self._monitor_check_after_id is not None:
                self.root.after_cancel(self._monitor_check_after_id)
            self._monitor_check_after_id = self.root.after(
                delay, self._apply_monitor_scaling_if_needed)
        except tk.TclError:
            self._monitor_check_after_id = None

    def _poll_monitor_work_area(self):
        """Notice taskbar/work-area changes even when Tk emits no Configure."""
        if getattr(self, "is_quitting", False) or not getattr(self, "root", None):
            return
        try:
            hwnd = _top_level_hwnd(self.root)
            monitor = _monitor_metrics_from_window(hwnd) if hwnd else None
            signature = _monitor_work_signature(monitor)
            dpi = _get_window_dpi(hwnd) if hwnd else None
            if (signature != self._ui_monitor_signature
                    or (dpi is not None and dpi != self._ui_window_dpi)):
                self._queue_monitor_scale_check(0)
            self.root.after(1000, self._poll_monitor_work_area)
        except (tk.TclError, RuntimeError):
            pass

    def _commit_dynamic_window_size(self, monitor_handle, client_width,
                                    client_height, outer_width, outer_height):
        """Commit size once more after the monitor-change callback has unwound."""
        if (getattr(self, "is_quitting", False)
                or monitor_handle != self._ui_monitor_handle):
            return
        try:
            if self.root.state() != "normal":
                logger.info(
                    "Deferred dynamic window resize skipped: state=%s",
                    self.root.state())
                return
            hwnd = _top_level_hwnd(self.root)
            if not hwnd:
                raise RuntimeError("Could not resolve Tk top-level HWND")
            rect = win32gui.GetWindowRect(hwnd)
            self.root.geometry(f"{client_width}x{client_height}")
            win32gui.MoveWindow(
                hwnd, rect[0], rect[1], outer_width, outer_height, True)
            self.root.update_idletasks()
            applied = win32gui.GetWindowRect(hwnd)
            logger.info(
                "Deferred dynamic window resize committed: outer=%dx%d",
                applied[2] - applied[0], applied[3] - applied[1])
        except Exception:
            logger.exception("Failed to commit deferred dynamic window size")

    def _restore_dpi_independent_window_size(self, expected_dpi=None):
        """Undo Windows' automatic WM_DPICHANGED top-level window resize."""
        if getattr(self, "is_quitting", False):
            return
        try:
            hwnd = _top_level_hwnd(self.root)
            if not hwnd or self.root.state() != "normal":
                return
            if expected_dpi is not None and _get_window_dpi(hwnd) != expected_dpi:
                return
            client_size = self._dpi_independent_client_size
            outer_size = self._dpi_independent_outer_size
            outer_position = self._dpi_independent_outer_position
            if not client_size or not outer_size or not outer_position:
                return
            monitor = _monitor_metrics_from_window(hwnd)
            current_outer = win32gui.GetWindowRect(hwnd)
            current_client = win32gui.GetClientRect(hwnd)
            non_client_height = max(
                0, (current_outer[3] - current_outer[1])
                - (current_client[3] - current_client[1]))
            target_outer_width = int(outer_size[0])
            target_outer_height = int(outer_size[1])
            target_x, target_y = outer_position
            if monitor:
                target_outer_height = min(
                    target_outer_height, monitor["work_height"])
                if target_outer_width <= monitor["work_width"]:
                    target_x = min(
                        max(target_x, monitor["work_left"]),
                        monitor["work_right"] - target_outer_width)
                target_y = min(
                    max(target_y, monitor["work_top"]),
                    monitor["work_bottom"] - target_outer_height)
            target_client_height = max(
                1, target_outer_height - non_client_height)
            self.root.minsize(client_size[0], target_client_height)
            self.root.geometry(
                f"{client_size[0]}x{target_client_height}"
                f"+{int(target_x)}+{int(target_y)}")
            win32gui.SetWindowPos(
                int(hwnd), 0, int(target_x), int(target_y),
                target_outer_width, target_outer_height,
                win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE)
            self.root.update_idletasks()
            applied = win32gui.GetWindowRect(hwnd)
            logger.info(
                "DPI-only window size restored: dpi=%s client=%dx%d "
                "outer=%dx%d", expected_dpi, client_size[0], target_client_height,
                applied[2] - applied[0], applied[3] - applied[1])
            self._dpi_independent_client_size = (
                client_size[0], target_client_height)
            self._dpi_independent_outer_size = (
                applied[2] - applied[0], applied[3] - applied[1])
            self._dpi_independent_outer_position = (
                applied[0], applied[1])
        except Exception:
            logger.exception("Failed to restore DPI-independent window size")

    def _apply_monitor_scaling_if_needed(self):
        global scaling_factor
        self._monitor_check_after_id = None
        if self._dynamic_scale_in_progress or getattr(self, "is_quitting", False):
            return
        try:
            hwnd = _top_level_hwnd(self.root)
            if not hwnd:
                raise RuntimeError("Could not resolve Tk top-level HWND")
            monitor = _monitor_metrics_from_window(hwnd)
            if not monitor:
                return
            current_dpi = _get_window_dpi(hwnd)
            previous_dpi = self._ui_window_dpi
            signature = _monitor_work_signature(monitor)
            scale_changed = signature != self._ui_monitor_signature
            dpi_only_changed = (
                current_dpi is not None
                and previous_dpi is not None
                and current_dpi != previous_dpi
                and self._ui_monitor_signature is not None
                and monitor["height"] == self._ui_monitor_signature[1]
            )
            logger.info(
                "Monitor scale check: widget_hwnd=%s top_hwnd=%s monitor=%s "
                "signature=%s previous=%s rect=%s state=%s",
                self.root.winfo_id(), hwnd, monitor["handle"], signature,
                self._ui_monitor_signature, win32gui.GetWindowRect(hwnd),
                self.root.state())
            self._ui_monitor_handle = monitor["handle"]
            self._ui_monitor_signature = signature
            self._ui_window_dpi = current_dpi
            if dpi_only_changed:
                # A DPI change can also alter rcWork by changing the native
                # taskbar thickness.  Resolution is still identical, so this
                # must win over the work-area signature comparison.
                logger.info(
                    "DPI-only change detected: %s -> %s; preserving app size",
                    previous_dpi, current_dpi)
                self._dynamic_scale_in_progress = True
                try:
                    self._restore_dpi_independent_window_size(current_dpi)
                    self.root.after(
                        120, self._restore_dpi_independent_window_size,
                        current_dpi)
                finally:
                    self._dynamic_scale_in_progress = False
                return
            if not scale_changed:
                # A normal user move (same monitor/DPI) becomes the next stable
                # position.  This runs only after the DPI-only branch above, so
                # Windows' suggested WM_DPICHANGED position is never accepted.
                stable_rect = win32gui.GetWindowRect(hwnd)
                self._dpi_independent_outer_position = (
                    stable_rect[0], stable_rect[1])
                return

            old_scale = float(scaling_factor)
            refresh_ui_scaling(monitor["height"], monitor["work_height"])
            new_scale = float(scaling_factor)
            content_scale_changed = abs(new_scale - old_scale) >= 0.0001

            self._dynamic_scale_in_progress = True
            if content_scale_changed:
                logger.info(
                    "Display change detected: %sp work area %sp; "
                    "UI scale %.4f -> %.4f",
                    monitor["height"], monitor["work_height"],
                    old_scale, new_scale)
                self._rescale_widget_tree(old_scale, new_scale)
                self._refresh_resolution_scaled_images()
            else:
                logger.info(
                    "Monitor work area changed without content scaling: %s",
                    signature)

            if content_scale_changed:
                self.force_refresh_player_slots()
            self.root.update_idletasks()
            formula_width = int(
                BASE_WINDOW_WIDTH * window_resolution_ratio
                * _normalized_user_ui_scale())
            required_width = self._measure_required_client_width()
            width = max(formula_width, required_width)
            desired_height = int(BASE_WINDOW_HEIGHT * window_resolution_ratio)

            # Tk may defer root.geometry() until after this callback returns, so
            # synchronously resize the native top-level HWND as well.  The window
            # procedure deliberately does not override WM_WINDOWPOSCHANGING; doing
            # so would lock the window to its previous display's outer dimensions.
            outer_rect = win32gui.GetWindowRect(int(hwnd))
            fitted = _fit_window_to_work_area(
                monitor, width, desired_height, hwnd=hwnd,
                x=outer_rect[0], y=outer_rect[1])
            width = fitted["client_width"]
            height = fitted["client_height"]
            target_outer_width = fitted["outer_width"]
            target_outer_height = fitted["outer_height"]
            self.root.minsize(width, height)
            self.root.geometry(
                f"{width}x{height}+{fitted['x']}+{fitted['y']}")
            win32gui.SetWindowPos(
                int(hwnd), 0,
                fitted["x"], fitted["y"],
                target_outer_width, target_outer_height,
                win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE)
            self.root.configure(
                padx=int(10 * scaling_factor), pady=int(10 * scaling_factor))
            self.root.update_idletasks()

            applied_rect = win32gui.GetWindowRect(int(hwnd))
            applied_width = applied_rect[2] - applied_rect[0]
            applied_height = applied_rect[3] - applied_rect[1]
            if (applied_width != target_outer_width
                    or applied_height != target_outer_height):
                # MoveWindow is a deliberately independent fallback for window
                # managers/Tk builds that coalesce the preceding SetWindowPos.
                win32gui.MoveWindow(
                    int(hwnd), fitted["x"], fitted["y"],
                    target_outer_width, target_outer_height, True)
                self.root.update_idletasks()
                applied_rect = win32gui.GetWindowRect(int(hwnd))
                applied_width = applied_rect[2] - applied_rect[0]
                applied_height = applied_rect[3] - applied_rect[1]
            logger.info(
                "Dynamic window resize: client=%dx%d outer_target=%dx%d "
                "outer_applied=%dx%d state=%s",
                width, height, target_outer_width, target_outer_height,
                applied_width, applied_height, self.root.state())
            self._dpi_independent_client_size = (width, height)
            self._dpi_independent_outer_size = (
                applied_width, applied_height)
            self._dpi_independent_outer_position = (
                applied_rect[0], applied_rect[1])
            self._ui_window_dpi = current_dpi

            self.content_canvas.itemconfigure(
                self._scroll_content_window,
                width=max(self.content_canvas.winfo_width(),
                          self._measure_scroll_content_width()))
            self.root.after_idle(self._update_content_scrollregion)
            self.root.after(
                0, self._commit_dynamic_window_size,
                monitor["handle"], width, height,
                target_outer_width, target_outer_height)
        except Exception:
            logger.exception("Failed to apply dynamic monitor UI scaling")
        finally:
            self._dynamic_scale_in_progress = False


    def on_configure(self, event):
        if event.widget == self.root:
            try:
                if self.root.state() == 'normal':
                    w = self.root.winfo_width()
                    h = self.root.winfo_height()
                    rx = self.root.winfo_x()
                    ry = self.root.winfo_y()
                    if w > 100 and h > 100:
                        self.last_width = w
                        self.last_height = h
                        self.last_x = rx
                        self.last_y = ry
                        self._relayout_after_restore()
            except Exception:
                pass
            if not getattr(self, "_dynamic_scale_in_progress", False):
                self._queue_monitor_scale_check(120)

    def _relayout_after_restore(self, event=None):
        if event is not None and getattr(event, "widget", None) != self.root:
            return
        try:
            if not getattr(self, 'root', None) or not self.root.winfo_exists():
                return
            if hasattr(self, 'center_cluster') and self.center_cluster.winfo_exists():
                self.center_cluster.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
            if hasattr(self, 'footer_status_container') and self.footer_status_container.winfo_exists():
                self.footer_status_container.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
            self.root.update_idletasks()
        except Exception:
            pass

    def init_compensation_panel(self, parent=None):
        parent = parent or self.root
        panel_bg = parent.cget("bg") if parent is not self.root else background_color
        self.comp_frame = tk.LabelFrame(parent, text=" Gyro Pass-Through ", bg=panel_bg, fg=text_color, font=scale_font(("Arial", 11, "bold")), padx=int(10 * scaling_factor), pady=int(10 * scaling_factor))
        self.comp_frame.pack(side=tk.TOP, fill=tk.X, pady=int(5 * scaling_factor))
        
        tk.Label(self.comp_frame, text="9-axis Assist:", bg=panel_bg, fg=text_color, font=scale_font(("Arial", 11, "bold"))).grid(row=0, column=0, padx=int(5 * scaling_factor), sticky="e")
        self.stabilized_gyro_switch = ToggleSwitch(self.comp_frame, labels=["ON", "OFF"], values=[True, False], initial_value=getattr(CONFIG, "gyro_passthrough_9axis_enabled", False), command=self.update_stabilized_gyro_setting, bg_color=panel_bg)
        self.stabilized_gyro_switch.grid(row=0, column=1, columnspan=2, padx=int(5 * scaling_factor), sticky="w")
        tk.Label(self.comp_frame, text="Horizon Lock:", bg=panel_bg, fg=text_color, font=scale_font(("Arial", 11, "bold"))).grid(row=0, column=3, padx=(int(20 * scaling_factor), int(5 * scaling_factor)), sticky="e")
        self.steam_roll_comp_switch = ToggleSwitch(self.comp_frame, labels=["ON", "OFF"], values=[True, False], initial_value=getattr(CONFIG, "steam_roll_compensation", False), command=self.update_steam_roll_comp_setting, bg_color=panel_bg)
        self.steam_roll_comp_switch.grid(row=0, column=4, columnspan=2, padx=int(5 * scaling_factor), sticky="w")

        tk.Label(self.comp_frame, text="Deadzone:", bg=panel_bg, fg=text_color, font=scale_font(("Arial", 11, "bold"))).grid(row=0, column=6, padx=(int(20 * scaling_factor), int(5 * scaling_factor)), sticky="e")
        self.deadzone_scale = tk.Scale(
            self.comp_frame,
            from_=0.0,
            to=100.0,
            resolution=0.5,
            orient=tk.HORIZONTAL,
            length=int(120 * scaling_factor),
            bg=panel_bg,
            fg=text_color,
            troughcolor=button_gray,
            activebackground=highlight_color,
            highlightthickness=0,
            bd=0,
            sliderrelief=tk.FLAT,
            sliderlength=int(15 * scaling_factor),
            width=int(15 * scaling_factor),
            font=scale_font(("Arial", 11, "bold")),
            command=self.update_virtual_gyro_soft_deadzone_setting
        )
        self.deadzone_scale.set(getattr(CONFIG, "virtual_gyro_soft_deadzone", 0.0))
        self.deadzone_scale.grid(row=0, column=7, columnspan=2, padx=int(5 * scaling_factor), sticky="w")

        tk.Label(self.comp_frame, text="Mode:", bg=panel_bg, fg=text_color, font=scale_font(("Arial", 11, "bold"))).grid(row=1, column=0, padx=int(5 * scaling_factor), pady=(int(5 * scaling_factor), 0), sticky="e")
        self.passthrough_mode_switch = ToggleSwitch(self.comp_frame, labels=["Default", "Cemuhook"], values=["Default", "Cemuhook"], 
initial_value=getattr(CONFIG, "gyro_passthrough_mode", "Default"), command=self.update_passthrough_mode, 
bg_color=panel_bg, widths=[8, 10])
        self.passthrough_mode_switch.grid(row=1, column=1, columnspan=2, padx=int(5 * scaling_factor), pady=(int(5 * scaling_factor), 0), sticky="w")

        self.sens_label = tk.Label(self.comp_frame, text="Sensitivity:", bg=panel_bg, fg=text_color, font=scale_font(("Arial", 11, "bold")))
        self.cemuhook_sens_scale = tk.Scale(
            self.comp_frame,
            from_=1,
            to=5,
            resolution=1,
            orient=tk.HORIZONTAL,
            length=int(120 * scaling_factor),
            bg=panel_bg,
            fg=text_color,
            troughcolor=button_gray,
            activebackground=highlight_color,
            highlightthickness=0,
            bd=0,
            sliderrelief=tk.FLAT,
            sliderlength=int(15 * scaling_factor),
            width=int(15 * scaling_factor),
            font=scale_font(("Arial", 11, "bold")),
            command=self.update_cemuhook_sensitivity
        )
        self.cemuhook_sens_scale.set(getattr(CONFIG, "cemuhook_sensitivity", 1))
        
        self.update_sens_visibility(getattr(CONFIG, "gyro_passthrough_mode", "Default"))

        if getattr(CONFIG, "gyro_passthrough_mode", "Default") == "Cemuhook":
            cemuhook_server.start()

    def update_sens_visibility(self, mode):
        if mode == "Cemuhook":
            self.sens_label.grid(row=1, column=3, padx=(int(20 * scaling_factor), int(5 * scaling_factor)), pady=(int(5 * scaling_factor), 0), sticky="e")
            self.cemuhook_sens_scale.grid(row=1, column=4, columnspan=2, padx=int(5 * scaling_factor), pady=(int(5 * scaling_factor), 0), sticky="w")
        else:
            self.sens_label.grid_forget()
            self.cemuhook_sens_scale.grid_forget()

    def update_passthrough_mode(self, mode):
        CONFIG.gyro_passthrough_mode = mode
        CONFIG.save_config()
        if mode == "Cemuhook":
            cemuhook_server.start()
        else:
            cemuhook_server.stop()
        self.update_sens_visibility(mode)
        logger.info(f"Gyro Passthrough Mode updated to {mode}")

    def update_cemuhook_sensitivity(self, val):
        val = int(float(val))
        CONFIG.cemuhook_sensitivity = val
        CONFIG.save_config()
        logger.info(f"Cemuhook Sensitivity updated to {val}")

    def init_djg_panel(self, parent=None):
        parent = parent or self.root
        panel_bg = parent.cget("bg") if parent is not self.root else background_color
        self.djg_frame = tk.LabelFrame(parent, text=" Dual Joy-con Gyro (DJG) ", bg=panel_bg, fg=text_color, font=scale_font(("Arial", 11, "bold")), padx=int(10 * scaling_factor), pady=int(10 * scaling_factor))
        if getattr(CONFIG, 'simulation_mode', '') != "Switch1":
            self.djg_frame.pack(side=tk.TOP, fill=tk.X, pady=int(5 * scaling_factor))
        
        tk.Label(self.djg_frame, text="DJG:", bg=panel_bg, fg=text_color, font=scale_font(("Arial", 11, "bold"))).grid(row=0, column=0, padx=int(5 * scaling_factor), sticky="e")
        self.djg_enabled_switch = ToggleSwitch(self.djg_frame, labels=["ON", "OFF"], values=[True, False], initial_value=getattr(CONFIG, "djg_enabled", False), command=self.update_djg_enabled_setting, bg_color=panel_bg)
        self.djg_enabled_switch.grid(row=0, column=1, columnspan=2, padx=int(5 * scaling_factor), sticky="w")
        
        self.djg_dominant_label = tk.Label(self.djg_frame, text="Dominant Side:", bg=panel_bg, fg=text_color, font=scale_font(("Arial", 11, "bold")))
        self.djg_dominant_label.grid(row=0, column=3, padx=(int(20 * scaling_factor), int(5 * scaling_factor)), sticky="e")
        djg_dominant = getattr(CONFIG, "djg_dominant_side", "Right")
        self.djg_dominant_switch = ToggleSwitch(
            self.djg_frame, labels=["Left", "Right"], values=["Left", "Right"],
            initial_value=djg_dominant if djg_dominant in ("Left", "Right") else "Right",
            command=self.update_djg_dominant_setting, bg_color=panel_bg)
        self.djg_dominant_switch.grid(row=0, column=4, columnspan=2, padx=int(5 * scaling_factor), sticky="w")
        self.djg_dominant_var = tk.StringVar(value=djg_dominant)
        self.djg_dominant_combo = ttk.Combobox(
            self.djg_frame, textvariable=self.djg_dominant_var,
            values=["Left", "Right", "None"], state="readonly",
            font=scale_font(("Arial", 11, "bold")), width=6, justify="center")
        self.djg_dominant_combo.grid(row=0, column=4, columnspan=2, padx=int(5 * scaling_factor), sticky="w")
        self.djg_dominant_combo.bind(
            "<<ComboboxSelected>>",
            lambda e: self.update_djg_dominant_setting(self.djg_dominant_var.get()))
        
        tk.Label(self.djg_frame, text="Mode:", bg=panel_bg, fg=text_color, font=scale_font(("Arial", 11, "bold"))).grid(row=0, column=6, padx=(int(20 * scaling_factor), int(5 * scaling_factor)), sticky="e")
        
        self.djg_mode_var = tk.StringVar(value=getattr(CONFIG, "djg_mode", "Single Side Toggle"))
        djg_modes = ["Switch Dominant Side", "Switch Gyro Side", "Single Side Toggle"]
        
        # Calculate max width for dropdown
        max_mode_len = max(len(m) for m in djg_modes)
        
        self.djg_mode_combo = ttk.Combobox(self.djg_frame, textvariable=self.djg_mode_var, values=djg_modes, state="readonly", font=scale_font(("Arial", 11, "bold")), width=max_mode_len, justify="center")
        self.djg_mode_combo.grid(row=0, column=7, padx=int(5 * scaling_factor), sticky="w")
        self.djg_mode_combo.bind("<<ComboboxSelected>>", lambda e: self.update_djg_mode_setting(self.djg_mode_var.get()))

        self.djg_activation_label = tk.Label(self.djg_frame, text="Activation:", bg=panel_bg, fg=text_color, font=scale_font(("Arial", 11, "bold")))
        self.djg_activation_label.grid(row=0, column=8, padx=(int(20 * scaling_factor), int(5 * scaling_factor)), sticky="e")
        self.djg_activation_switch = ToggleSwitch(self.djg_frame, labels=["Hold", "Toggle"], values=["Hold", "Toggle"], initial_value=getattr(CONFIG, "djg_activation", "Toggle"), command=self.update_djg_activation_setting, bg_color=panel_bg)
        self.djg_activation_switch.grid(row=0, column=9, columnspan=2, padx=int(5 * scaling_factor), sticky="w")

        self._apply_djg_mode_ui_state()
        self._update_djg_panel_visibility()

    def _apply_djg_mode_ui_state(self):
        if not hasattr(self, 'djg_mode_var'):
            return
        single_side_toggle = self.djg_mode_var.get() == "Single Side Toggle"
        dominant_combo = getattr(self, "djg_dominant_combo", None)
        dominant_switch = getattr(self, "djg_dominant_switch", None)
        if dominant_combo is not None:
            if single_side_toggle:
                dominant_combo.grid()
            else:
                dominant_combo.grid_remove()
        if dominant_switch is not None:
            if single_side_toggle:
                dominant_switch.grid_remove()
            else:
                dominant_switch.grid()
        if getattr(self, "root", None) is not None:
            self._queue_width_reconcile(0)

    def _update_djg_panel_visibility(self):
        pass

    def update_djg_activation_setting(self, val):
        CONFIG.djg_activation = val
        CONFIG.save_config()
        logger.info(f"DJG Activation: {val}")

    def update_djg_mode_setting(self, val):
        legacy_direct_merge = val == "Direct Merge"
        if legacy_direct_merge:
            # The config setter performs the atomic legacy migration so None is
            # not rejected against the previously selected non-Single mode.
            CONFIG.djg_mode = "Direct Merge"
            val = CONFIG.djg_mode
            if hasattr(self, "djg_dominant_var"):
                self.djg_dominant_var.set(CONFIG.djg_dominant_side)
        elif val != "Single Side Toggle" and getattr(CONFIG, "djg_dominant_side", "Right") == "None":
            CONFIG.djg_dominant_side = "Right"
            if hasattr(self, "djg_dominant_var"):
                self.djg_dominant_var.set("Right")
            if hasattr(self, "djg_dominant_switch"):
                self.djg_dominant_switch.set_value("Right")
        if not legacy_direct_merge:
            CONFIG.djg_mode = val
        CONFIG.save_config()
        logger.info(f"DJG Mode: {val}")
        if hasattr(self, "djg_mode_var"):
            self.djg_mode_var.set(val)
        self._apply_djg_mode_ui_state()
        self.force_refresh_player_slots()


    def update_djg_enabled_setting(self, val):
        CONFIG.djg_enabled = val
        CONFIG.save_config()
        logger.info(f"DJG Enabled: {val}")
        if not val:
            for vc in VIRTUAL_CONTROLLERS:
                if vc:
                    side = getattr(CONFIG, "djg_dominant_side", "Right")
                    vc.active_gyro_side = side if side in ("Left", "Right") else "Right"
        self.force_refresh_player_slots()

    def update_djg_dominant_setting(self, val):
        if val not in ("Left", "Right", "None"):
            val = "Right"
        if val == "None" and getattr(CONFIG, "djg_mode", "Single Side Toggle") != "Single Side Toggle":
            val = "Right"
        if hasattr(self, "djg_dominant_var"):
            self.djg_dominant_var.set(val)
        if val in ("Left", "Right") and hasattr(self, "djg_dominant_switch"):
            self.djg_dominant_switch.set_value(val)
        CONFIG.djg_dominant_side = val
        CONFIG.save_config()
        logger.info(f"DJG Dominant Side: {val}")
        if not getattr(CONFIG, "djg_enabled", False):
            for vc in VIRTUAL_CONTROLLERS:
                if vc:
                    vc.active_gyro_side = val if val in ("Left", "Right") else "Right"
        else:
            mode = getattr(CONFIG, "djg_mode", "Single Side Toggle")
            if mode == "Switch Dominant Side":
                for vc in VIRTUAL_CONTROLLERS:
                    if vc:
                        vc.djg_left_active = True
                        vc.djg_right_active = True
            elif mode == "Switch Gyro Side":
                for vc in VIRTUAL_CONTROLLERS:
                    if vc:
                        vc.active_gyro_side = val
        self.force_refresh_player_slots()


    def init_gyro_settings_panel(self, parent=None):
        parent = parent or self.root
        panel_bg = parent.cget("bg") if parent is not self.root else background_color
        self.gyro_frame = tk.LabelFrame(parent, text=" In-app Gyro Mode ", bg=panel_bg, fg=text_color, font=scale_font(("Arial", 11, "bold")), padx=int(10 * scaling_factor), pady=int(10 * scaling_factor))
        self.gyro_frame.pack(side=tk.TOP, fill=tk.X, pady=int(5 * scaling_factor))

        # ---- Shared calibration controls ----
        gyro_calib_row = tk.Frame(self.gyro_frame, bg=panel_bg)
        self.calib_frame = tk.Frame(gyro_calib_row, bg=panel_bg)
        self.calib_frame.pack(side=tk.LEFT)
        self.calib_button_frame = tk.Frame(self.calib_frame, bg=panel_bg)
        self.calib_button_frame.pack(side=tk.LEFT)
        self.calibrate_btn = make_rounded_button(
            self.calib_button_frame,
            text="Calibrate Gyro",
            command=self.on_calibrate_clicked,
            width=130,
            height=30,
            radius=8,
            bg_color=button_gray,
            hover_color="#5A5A5A",
            press_color="#3A3A3A",
            fg=text_color,
            parent_bg=panel_bg,
            font=scale_font(("Arial", 11, "bold"))
        )
        self.calibrate_btn.pack(side=tk.LEFT)

        self.calib_hint_label = tk.Label(self.calib_frame, text="Keep controller stationary\nbefore calibrating.", bg=panel_bg, fg=text_color, font=scale_font(("Arial", 11, "bold")), justify=tk.LEFT)
        self.calib_hint_label.pack(side=tk.LEFT, padx=(int(10 * scaling_factor), int(2 * scaling_factor)), pady=int(2 * scaling_factor))

        mag_hint_frame = tk.Frame(self.gyro_frame, bg=panel_bg)

        l1 = tk.Frame(mag_hint_frame, bg=panel_bg)
        l1.pack(side=tk.TOP, anchor="w")
        tk.Label(l1, text="Calibrate Mag (Mag Cal): Move controller in a", bg=panel_bg, fg=text_color, font=scale_font(("Arial", 11, "bold"))).pack(side=tk.LEFT)

        l2 = tk.Frame(mag_hint_frame, bg=panel_bg)
        l2.pack(side=tk.TOP, anchor="w")

        lnk = tk.Label(l2, text="'figure 8'", bg=panel_bg, fg=highlight_color, font=scale_font(("Arial", 11, "bold", "underline")), cursor="hand2")
        lnk.pack(side=tk.LEFT)
        lnk.bind("<Button-1>", lambda e: (logger.info(f"Opening YouTube link via webbrowser..."), webbrowser.open("https://youtu.be/J_cZnPcW-Yw?si=ID2vdzURiOph8x77&t=6")))

        tk.Label(l2, text=" pattern during calibration.", bg=panel_bg, fg=text_color, font=scale_font(("Arial", 11, "bold"))).pack(side=tk.LEFT)

        # ---- Row 1: Gyro Control + Sensitivity + Calibrate Gyro ----
        tk.Label(self.gyro_frame, text="Gyro Control:", bg=panel_bg, fg=text_color, font=scale_font(("Arial", 11, "bold"))).grid(row=1, column=0, padx=int(5 * scaling_factor), pady=(int(10 * scaling_factor), 0), sticky="e")
        initial_gyro_control = "Steering" if getattr(CONFIG, "gyro_mode", "World") == "Roll" else getattr(CONFIG, "gyro_control_mode", "Mouse")
        self.gyro_control_switch = ToggleSwitch(self.gyro_frame, labels=["Mouse", "R Joystick", "Steering"], values=["Mouse", "R Joystick", "Steering"], initial_value=initial_gyro_control, command=self.update_gyro_control_mode, bg_color=panel_bg)
        self.gyro_control_switch.grid(row=1, column=1, padx=int(5 * scaling_factor), pady=(int(10 * scaling_factor), 0), sticky="w")
        tk.Label(self.gyro_frame, text="Sensitivity:", bg=panel_bg, fg=text_color, font=scale_font(("Arial", 11, "bold"))).grid(row=1, column=2, padx=(int(20 * scaling_factor), int(5 * scaling_factor)), pady=(int(10 * scaling_factor), 0), sticky="e")
        self.sens_scale = tk.Scale(self.gyro_frame, from_=1, to=10, resolution=0.2, orient=tk.HORIZONTAL, length=int(120 * scaling_factor), bg=panel_bg, fg=text_color, troughcolor=button_gray, activebackground=highlight_color, highlightthickness=0, bd=0, sliderrelief=tk.FLAT, sliderlength=int(15 * scaling_factor), width=int(15 * scaling_factor), font=scale_font(("Arial", 11, "bold")), command=self.on_gyro_setting_changed)
        self.sens_scale.set(self._current_gyro_control_sensitivity())
        self.sens_scale.grid(row=1, column=3, padx=int(5 * scaling_factor), pady=(int(10 * scaling_factor), 0), sticky="w")
        gyro_calib_row.grid(row=1, column=4, columnspan=3, padx=(int(20 * scaling_factor), int(5 * scaling_factor)), pady=(int(10 * scaling_factor), 0), sticky="w")

        # ---- Row 2: Mode + Deadzone + Mag Cal hint ----
        tk.Label(self.gyro_frame, text="Mode:", bg=panel_bg, fg=text_color, font=scale_font(("Arial", 11, "bold"))).grid(row=2, column=0, padx=int(5 * scaling_factor), pady=(int(10 * scaling_factor), 0), sticky="e")
        self.gyro_mode_switch = ToggleSwitch(self.gyro_frame, labels=["9-Axis", "6-Axis"], values=["World", "Yaw"], initial_value=(CONFIG.gyro_mode if CONFIG.gyro_mode in ("World", "Yaw") else "World"), command=self.update_mode_setting, bg_color=panel_bg)
        self.gyro_mode_switch.grid(row=2, column=1, padx=int(5 * scaling_factor), pady=(int(10 * scaling_factor), 0), sticky="w")
        tk.Label(self.gyro_frame, text="Deadzone:", bg=panel_bg, fg=text_color, font=scale_font(("Arial", 11, "bold"))).grid(row=2, column=2, padx=(int(20 * scaling_factor), int(5 * scaling_factor)), pady=(int(10 * scaling_factor), 0), sticky="e")
        mag_hint_frame.grid(row=2, column=4, columnspan=3, padx=(int(20 * scaling_factor), int(5 * scaling_factor)), pady=(int(10 * scaling_factor), 0), sticky="w")

        # ---- Row 3: Mode Shift + Stick Assist ----
        tk.Label(self.gyro_frame, text="Mode Shift:", bg=panel_bg, fg=text_color, font=scale_font(("Arial", 11, "bold"))).grid(row=3, column=0, padx=int(5 * scaling_factor), pady=(int(10 * scaling_factor), 0), sticky="e")
        self.mode_shift_switch = ToggleSwitch(self.gyro_frame, labels=["On", "Off"], values=[True, False], initial_value=CONFIG.mode_shift_enabled, command=self.update_mode_shift_setting, bg_color=panel_bg)
        self.mode_shift_switch.grid(row=3, column=1, padx=int(5 * scaling_factor), pady=(int(10 * scaling_factor), 0), sticky="w")

        self.in_app_deadzone_scale = tk.Scale(
            self.gyro_frame,
            from_=0.0,
            to=100.0,
            resolution=0.5,
            orient=tk.HORIZONTAL,
            length=int(120 * scaling_factor),
            bg=panel_bg,
            fg=text_color,
            troughcolor=button_gray,
            activebackground=highlight_color,
            highlightthickness=0,
            bd=0,
            sliderrelief=tk.FLAT,
            sliderlength=int(15 * scaling_factor),
            width=int(15 * scaling_factor),
            font=scale_font(("Arial", 11, "bold")),
            command=self.update_in_app_gyro_soft_deadzone_setting
        )
        self.in_app_deadzone_scale.set(getattr(CONFIG, "in_app_gyro_soft_deadzone", 0.0))
        self.in_app_deadzone_scale.grid(row=2, column=3, padx=int(5 * scaling_factor), pady=(int(10 * scaling_factor), 0), sticky="w")

        self.stick_assist_label = tk.Label(self.gyro_frame, text="Stick Assist:", bg=panel_bg, fg=text_color, font=scale_font(("Arial", 11, "bold")))
        self.stick_assist_label.grid(row=3, column=2, padx=(int(20 * scaling_factor), int(5 * scaling_factor)), pady=(int(10 * scaling_factor), 0), sticky="e")
        self.stick_scale = tk.Scale(self.gyro_frame, from_=0, to=10, resolution=0.2, orient=tk.HORIZONTAL, length=int(120 * scaling_factor), bg=panel_bg, fg=text_color, troughcolor=button_gray, activebackground=highlight_color, highlightthickness=0, bd=0, sliderrelief=tk.FLAT, sliderlength=int(15 * scaling_factor), width=int(15 * scaling_factor), font=scale_font(("Arial", 11, "bold")), command=self.on_gyro_setting_changed)
        self.stick_scale.set(getattr(CONFIG, "stick_mouse_sensitivity", 5.0))
        self.stick_scale.grid(row=3, column=3, padx=int(5 * scaling_factor), pady=(int(10 * scaling_factor), 0), sticky="w")

        self._update_gyro_control_visibility(initial_gyro_control)


    def init_auto_disconnect_popup(self, parent=None):
        parent = parent or self.root
        spacing = int(10 * scaling_factor)
        popup = tk.Frame(parent, bg=background_color, padx=spacing, pady=spacing)
        popup.pack(fill=tk.BOTH, expand=True)
        self.auto_disconnect_popup = popup

        # Row 1: Mode Switch
        row1 = tk.Frame(popup, bg=background_color)
        row1.pack(side=tk.TOP, fill=tk.X, pady=int(4 * scaling_factor))
        tk.Label(row1, text="Auto Disconnect:", bg=background_color, fg=text_color, font=scale_font(("Arial", 11, "bold"))).pack(side=tk.LEFT, padx=(0, int(5 * scaling_factor)))
        self.auto_disconnect_switch = ToggleSwitch(row1, labels=["OFF", "Inactive", "Absolute"], values=["OFF", "Inactive", "Absolute"], initial_value=getattr(CONFIG, "auto_disconnect_mode", "OFF"), command=self.update_auto_disconnect_mode, bg_color=background_color)
        self.auto_disconnect_switch.pack(side=tk.LEFT, padx=int(5 * scaling_factor))

        # Row 2: Disconnect after inputs
        row2 = tk.Frame(popup, bg=background_color)
        row2.pack(side=tk.TOP, fill=tk.X, pady=int(4 * scaling_factor))
        tk.Label(row2, text="Disconnect after:", bg=background_color, fg=text_color, font=scale_font(("Arial", 11, "bold"))).pack(side=tk.LEFT, padx=(0, int(5 * scaling_factor)))

        # Validation to only allow digits in time entries
        def validate_numeric(char):
            return char.isdigit() or char == ""
        vcmd = (self.root.register(validate_numeric), '%S')

        # Day Entry
        self.day_entry = tk.Entry(row2, width=4, bg=button_gray, fg=text_color, insertbackground=text_color, bd=0, relief=tk.FLAT, font=scale_font(("Arial", 11, "bold")), justify=tk.CENTER, validate="key", validatecommand=vcmd)
        self.day_entry.insert(0, str(getattr(CONFIG, "auto_disconnect_days", 0)))
        self.day_entry.pack(side=tk.LEFT, padx=int(2 * scaling_factor))
        self.day_entry.is_time_entry = True
        tk.Label(row2, text="Day", bg=background_color, fg=text_color, font=scale_font(("Arial", 11, "bold"))).pack(side=tk.LEFT, padx=(int(2 * scaling_factor), int(8 * scaling_factor)))

        # Hour Entry
        self.hour_entry = tk.Entry(row2, width=4, bg=button_gray, fg=text_color, insertbackground=text_color, bd=0, relief=tk.FLAT, font=scale_font(("Arial", 11, "bold")), justify=tk.CENTER, validate="key", validatecommand=vcmd)
        self.hour_entry.insert(0, str(getattr(CONFIG, "auto_disconnect_hours", 0)))
        self.hour_entry.pack(side=tk.LEFT, padx=int(2 * scaling_factor))
        self.hour_entry.is_time_entry = True
        tk.Label(row2, text="Hour", bg=background_color, fg=text_color, font=scale_font(("Arial", 11, "bold"))).pack(side=tk.LEFT, padx=(int(2 * scaling_factor), int(8 * scaling_factor)))

        # Minute Entry
        self.minute_entry = tk.Entry(row2, width=4, bg=button_gray, fg=text_color, insertbackground=text_color, bd=0, relief=tk.FLAT, font=scale_font(("Arial", 11, "bold")), justify=tk.CENTER, validate="key", validatecommand=vcmd)
        self.minute_entry.insert(0, str(getattr(CONFIG, "auto_disconnect_minutes", 0)))
        self.minute_entry.pack(side=tk.LEFT, padx=int(2 * scaling_factor))
        self.minute_entry.is_time_entry = True
        tk.Label(row2, text="Minute", bg=background_color, fg=text_color, font=scale_font(("Arial", 11, "bold"))).pack(side=tk.LEFT, padx=(int(2 * scaling_factor), int(5 * scaling_factor)))

        # Bind events
        self.day_entry.bind("<KeyRelease>", self.on_auto_disconnect_time_changed)
        self.hour_entry.bind("<KeyRelease>", self.on_auto_disconnect_time_changed)
        self.minute_entry.bind("<KeyRelease>", self.on_auto_disconnect_time_changed)

    def init_auto_disconnect_panel(self):
        self.init_auto_disconnect_popup()

    def update_auto_disconnect_mode(self, val):
        CONFIG.auto_disconnect_mode = val
        CONFIG.save_config()

    def on_auto_disconnect_time_changed(self, event=None):
        try:
            days_str = self.day_entry.get()
            hours_str = self.hour_entry.get()
            minutes_str = self.minute_entry.get()
            
            days = int(days_str) if days_str else 0
            hours = int(hours_str) if hours_str else 0
            minutes = int(minutes_str) if minutes_str else 0
            
            CONFIG.auto_disconnect_days = days
            CONFIG.auto_disconnect_hours = hours
            CONFIG.auto_disconnect_minutes = minutes
            CONFIG.save_config()
        except Exception as e:
            logger.error(f"Failed to save auto disconnect settings: {e}")

    def on_rumble_delay_changed(self, event=None):
        val_str = getattr(self, "rumble_delay_entry", tk.Entry(self.root)).get().strip()
        if not val_str:
            val = 0
        else:
            try:
                val = int(val_str)
            except ValueError:
                val = 0
        CONFIG.rumble_delay_ms = val
        CONFIG.save_config()

    def update_mode_setting(self, val):
        CONFIG.gyro_mode = val
        self.on_gyro_setting_changed()

    def update_stabilized_gyro_setting(self, val):
        # Pass-through only: ON selects the quality-gated V2 9-axis estimator;
        # OFF selects the independent pure V2 6-axis estimator.
        CONFIG.gyro_passthrough_9axis_enabled = val
        CONFIG._bump_settings_generation()
        CONFIG.save_config()
        logger.info(f"Pass-through V2 9-axis Assist: {val}")

    def update_steam_roll_comp_setting(self, val):
        # Drives V2 Horizon while V2 is active, Legacy Horizon Lock otherwise.
        CONFIG.steam_roll_compensation = val
        CONFIG._bump_settings_generation()
        CONFIG.save_config()
        logger.info(f"Horizon Lock: {val}")

    def update_virtual_gyro_soft_deadzone_setting(self, val):
        val = float(val)
        CONFIG.virtual_gyro_soft_deadzone = val
        CONFIG.save_config()
        logger.info(f"Gyro Pass-Through Deadzone: {val}")

    def update_in_app_gyro_soft_deadzone_setting(self, val):
        val = float(val)
        CONFIG.in_app_gyro_soft_deadzone = val
        CONFIG.save_config()
        logger.info(f"In-app Gyro Deadzone: {val}")

    def update_mouse_setting(self, val):
        CONFIG.mouse_config.enabled = val
        try:
            with open(CONFIG.config_file_path, 'r', encoding='utf-8') as f: data = yaml.load(f, Loader=_YamlLoader) or {}
            if 'mouse' not in data: data['mouse'] = {}
            data['mouse']['enabled'] = val
            with open(CONFIG.config_file_path, 'w', encoding='utf-8') as f: yaml.dump(data, f, Dumper=_YamlDumper, default_flow_style=False)
        except Exception as e: logger.error(f"Failed to save mouse settings: {e}")

    def update_act_setting(self, val):
        CONFIG.gyro_activation_mode = val
        self.on_gyro_setting_changed()

    def update_mode_shift_setting(self, val):
        # Stored per (profile, Gyro Control mode). Controls only whether In-app Gyro
        # auto-applies the Mode Shift Mapping; the mapping tab stays visible regardless.
        CONFIG.mode_shift_enabled = bool(val)
        # Turning Mode Shift On re-engages the In-app Gyro activation-button sync between
        # Controller Mapping and the Mode Shift Mapping store (Off leaves them independent).
        if val:
            CONFIG.sync_active_in_app_gyro_activation()
        CONFIG.save_config()
        self._refresh_mapping_comboboxes()
        # The Joy-con IR Sensor 'function' is cross-synced by the toggle too; refresh
        # its buttons so both the base and Mode Shift labels reflect the new state.
        self.refresh_joycon_ir_sensor_buttons()

    def _current_gyro_control_sensitivity(self):
        if getattr(CONFIG, "gyro_control_mode", "Mouse") == "R Joystick":
            return getattr(CONFIG, "r_joystick_gyro_sensitivity", 5.0)
        return getattr(CONFIG, "gyro_sensitivity", 0.3)

    def _save_current_gyro_control_sensitivity(self):
        if not hasattr(self, 'sens_scale'):
            return
        if getattr(CONFIG, "gyro_control_mode", "Mouse") == "R Joystick":
            CONFIG.r_joystick_gyro_sensitivity = float(self.sens_scale.get())
        else:
            CONFIG.gyro_sensitivity = float(self.sens_scale.get())

    def update_gyro_control_mode(self, val):
        self._save_current_gyro_control_sensitivity()
        CONFIG.gyro_control_mode = val
        if val == "Steering":
            CONFIG.gyro_mode = "Roll"
        elif getattr(CONFIG, "gyro_mode", "World") == "Roll":
            CONFIG.gyro_mode = self.gyro_mode_switch.values[self.gyro_mode_switch.current_index] if hasattr(self, "gyro_mode_switch") else "World"
        if hasattr(self, 'sens_scale'):
            self._updating_gyro_control_sensitivity = True
            self.sens_scale.set(self._current_gyro_control_sensitivity())
            self._updating_gyro_control_sensitivity = False
        # Mode Shift is stored per (profile, Gyro Control mode): reload its state for the
        # newly selected mode so the toggle and the mapping tab reflect that mode.
        if hasattr(self, 'mode_shift_switch'):
            self.mode_shift_switch.set_value(CONFIG.mode_shift_enabled)
        self._update_gyro_control_visibility(val)
        # The active In-app Gyro store switches with the mode; re-sync its In-app Gyro
        # activation buttons with Controller Mapping, then refresh the mapping tab so it
        # shows the mappings (and synced In-app Gyro buttons) for the selected mode.
        CONFIG.sync_active_in_app_gyro_activation()
        CONFIG.save_config()
        self._refresh_mapping_comboboxes()
        # The active In-app Gyro scope changed with the mode; refresh the IR buttons
        # so their labels reflect the reconciled function for the selected mode.
        self.refresh_joycon_ir_sensor_buttons()

    def _update_gyro_control_visibility(self, val):
        # Stick Assist only applies to gyro Mouse control; hide it for R Joystick/Steering.
        if not hasattr(self, 'stick_scale') or not hasattr(self, 'stick_assist_label'):
            return
        if val in ("R Joystick", "Steering"):
            self.stick_assist_label.grid_remove()
            self.stick_scale.grid_remove()
        else:
            self.stick_assist_label.grid()
            self.stick_scale.grid()
        self._update_in_app_gyro_mapping_tab_visibility()

    def _update_in_app_gyro_mapping_tab_visibility(self):
        # The Mode Shift Mapping tab is always visible. The Mode Shift On/Off toggle only
        # controls whether the mapping is applied at runtime (auto-applied on In-app Gyro
        # when On; otherwise applied only via the Mode Shift back button) -- it no longer
        # shows/hides this tab.
        widgets = getattr(self, "settings_tab_buttons", {}).get("in_app_gyro_mode_mapping")
        if not widgets:
            return
        btn, frame = widgets
        if not frame.winfo_ismapped():
            before_widgets = getattr(self, "settings_tab_buttons", {}).get("gyro_passthrough")
            pack_kwargs = {"side": tk.LEFT, "padx": (int(2 * scaling_factor), int(2 * scaling_factor))}
            if before_widgets:
                pack_kwargs["before"] = before_widgets[1]
            frame.pack(**pack_kwargs)

    def _sync_active_mode_shift_mapping_ui(self, save=False):
        try:
            CONFIG.sync_active_in_app_gyro_activation()
            if save:
                CONFIG.save_config()
        except Exception:
            logger.exception("Failed to sync active Mode Shift mapping state")

    def update_mouse_sensitivity(self, val):
        new_sens = float(val)
        CONFIG.mouse_config.sensitivity = new_sens
        try:
            with open(CONFIG.config_file_path, 'r', encoding='utf-8') as f: data = yaml.load(f, Loader=_YamlLoader) or {}
            if 'mouse' not in data: data['mouse'] = {}
            data['mouse']['sensitivity'] = new_sens
            with open(CONFIG.config_file_path, 'w', encoding='utf-8') as f: yaml.dump(data, f, Dumper=_YamlDumper, default_flow_style=False)
        except Exception as e: logger.error(f"Failed to save mouse sensitivity: {e}")

    def update_ir_activate_threshold(self, val):
        new_val = int(float(val))
        CONFIG.mouse_config.ir_activate_threshold = new_val
        try:
            with open(CONFIG.config_file_path, 'r', encoding='utf-8') as f: data = yaml.load(f, Loader=_YamlLoader) or {}
            if 'mouse' not in data: data['mouse'] = {}
            data['mouse']['ir_activate_threshold'] = new_val
            with open(CONFIG.config_file_path, 'w', encoding='utf-8') as f: yaml.dump(data, f, Dumper=_YamlDumper, default_flow_style=False)
        except Exception as e: logger.error(f"Failed to save IR activate threshold: {e}")

    def on_gyro_setting_changed(self, *args):
        if not hasattr(self, 'sens_scale') or not hasattr(self, 'stick_scale'):
            return
        if not getattr(self, '_updating_gyro_control_sensitivity', False):
            if getattr(CONFIG, "gyro_control_mode", "Mouse") == "R Joystick":
                CONFIG.r_joystick_gyro_sensitivity = float(self.sens_scale.get())
            else:
                CONFIG.gyro_sensitivity = float(self.sens_scale.get())
        CONFIG.stick_mouse_sensitivity = float(self.stick_scale.get())
        CONFIG.set_joystick_setting_scoped("l_joystick", "mouse_sensitivity", CONFIG.stick_mouse_sensitivity, "in_app_gyro_mode_mappings")
        CONFIG.set_joystick_setting_scoped("r_joystick", "mouse_sensitivity", CONFIG.stick_mouse_sensitivity, "in_app_gyro_mode_mappings")
        CONFIG.save_config()

    def on_calibrate_clicked(self):
        if not hasattr(self, 'current_controllers') or self.no_controllers:
            return
        try:
            vc = self.current_controllers[0] if self.current_controllers else None
            GyroCalibrationWizard(self.root, vc)
        except Exception as e:
            logger.error(f"Failed to launch GyroCalibrationWizard: {e}")



    def _mapping_scope_suffix(self, mapping_scope=None):
        return "_in_app_gyro_mode" if mapping_scope == "in_app_gyro_mode_mappings" else ""

    def _mapping_attr(self, key, suffix):
        return f"{key}{suffix}"

    def start_custom_recording(self, key, entry, combo, custom_frame, mode_var, mapping_scope=None, prefix=None,
                               value_writer=None, empty_writer=None, complete_callback=None):
        entry.config(state="normal")
        entry.delete(0, tk.END)
        entry.insert(0, "Recording...")
        entry.config(state="readonly")
        entry.focus_set()
        
        pressed_keys = set()
        recorded_seq = []
        recording_cancelled = {"value": False}
        recording_bind_ids = {}
        restore_in_app_outside_click = {"value": False}
        restore_joystick_outside_click = {"value": False}
        self.recording_controllers = True
        self.recorded_controller_buttons = set()
        self.waiting_for_controller_release = True

        in_app_bind_id = getattr(self, "in_app_gyro_popup_bind_id", None)
        if in_app_bind_id:
            try:
                self.root.unbind("<ButtonPress>", in_app_bind_id)
            except tk.TclError:
                pass
            self.in_app_gyro_popup_bind_id = None
            restore_in_app_outside_click["value"] = True

        joystick_bind_id = getattr(self, "joystick_custom_popup_bind_id", None)
        if joystick_bind_id:
            try:
                self.root.unbind("<ButtonPress>", joystick_bind_id)
            except tk.TclError:
                pass
            self.joystick_custom_popup_bind_id = None
            restore_joystick_outside_click["value"] = True

        def unbind_recording_events():
            for sequence, bind_id in list(recording_bind_ids.items()):
                try:
                    self.root.unbind(sequence, bind_id)
                except tk.TclError:
                    pass
            recording_bind_ids.clear()

        def restore_popup_outside_clicks(delay_ms=100):
            if restore_joystick_outside_click["value"] and getattr(self, "joystick_custom_popup", None) is not None:
                self.root.after(delay_ms, self.bind_joystick_custom_popup_outside_click)
            if restore_in_app_outside_click["value"] and getattr(self, "in_app_gyro_popup", None) is not None:
                self.root.after(delay_ms, self.bind_in_app_gyro_popup_outside_click)

        def cancel_recording_without_commit():
            recording_cancelled["value"] = True
            pressed_keys.clear()
            recorded_seq.clear()
            self.recording_controllers = False
            self.recorded_controller_buttons = set()
            self.waiting_for_controller_release = False
            unbind_recording_events()
            if getattr(self, "_cancel_custom_recording_without_commit", None) is cancel_recording_without_commit:
                self._cancel_custom_recording_without_commit = None
            restore_popup_outside_clicks(delay_ms=0)

        self._cancel_custom_recording_without_commit = cancel_recording_without_commit

        def end_recording():
            if recording_cancelled["value"]:
                return
            self.recording_controllers = False
            unbind_recording_events()
            if getattr(self, "_cancel_custom_recording_without_commit", None) is cancel_recording_without_commit:
                self._cancel_custom_recording_without_commit = None
            raw_seq = recorded_seq
            
            normalized_seq = []
            for k in raw_seq:
                if k in ("VK_CONTROL", "VK_CONTROL_L", "VK_CONTROL_R", "VK_LCONTROL", "VK_RCONTROL"):
                    nk = "VK_CONTROL"
                elif k in ("VK_SHIFT", "VK_SHIFT_L", "VK_SHIFT_R", "VK_LSHIFT", "VK_RSHIFT"):
                    nk = "VK_SHIFT"
                elif k in ("VK_MENU", "VK_ALT", "VK_ALT_L", "VK_ALT_R", "VK_LMENU", "VK_RMENU"):
                    nk = "VK_MENU"
                elif k in ("VK_WIN", "VK_LWIN", "VK_RWIN", "VK_WIN_L", "VK_WIN_R"):
                    nk = "VK_LWIN"
                else:
                    nk = k
                if nk not in normalized_seq:
                    normalized_seq.append(nk)
            
            final_seq = normalized_seq

            def sync_joystick_direction(value):
                base_key, sep, direction = key.rpartition("_")
                if sep and base_key in ("l_joystick", "r_joystick") and direction in ("up", "down", "left", "right", "click"):
                    current = CONFIG.get_joystick_custom_scoped(base_key, mapping_scope)
                    current[direction] = value
                    CONFIG.set_joystick_custom_scoped(base_key, current, mapping_scope)
            
            if not final_seq:
                if empty_writer is not None:
                    empty_writer()
                else:
                    custom_frame.pack_forget()
                    combo.pack(side=tk.LEFT)
                    combo.set("Default")
                    CONFIG.set_mapping_setting_scoped(key, "Default", mapping_scope)
                    self._joycon_ir_live_save(key, "Default")
                    sync_joystick_direction("Default")
            else:
                mode = mode_var.get()
                val_content = "+".join(final_seq)
                if prefix:
                    val = f"Custom[{mode}]:{prefix}+{val_content}"
                else:
                    val = f"Custom[{mode}]:{val_content}"
                if value_writer is not None:
                    value_writer(val)
                else:
                    CONFIG.set_mapping_setting_scoped(key, val, mapping_scope)
                    self._joycon_ir_live_save(key, val)
                    sync_joystick_direction(val)
                entry.config(state="normal")
                entry.delete(0, tk.END)
                display_val = format_input_display(val_content)
                entry.insert(0, display_val)
                entry.config(state="readonly")
            if complete_callback is not None:
                complete_callback(None if not final_seq else val)
            else:
                self.on_setting_changed()
            restore_popup_outside_clicks(delay_ms=100)

        def check_release():
            if not pressed_keys and not getattr(self, 'controller_buttons_pressed', False):
                if not recorded_seq and not self.recorded_controller_buttons:
                    return
                end_recording()

        def on_key_press(e):
            vk = e.keysym.upper()
            pressed_keys.add(f"VK_{vk}")
            if f"VK_{vk}" not in recorded_seq:
                recorded_seq.append(f"VK_{vk}")
            return "break"

        def on_key_release(e):
            vk = e.keysym.upper()
            if f"VK_{vk}" in pressed_keys:
                pressed_keys.remove(f"VK_{vk}")
            check_release()
            return "break"

        def on_mouse_press(e):
            btn = f"MB_{e.num}"
            pressed_keys.add(btn)
            if btn not in recorded_seq:
                recorded_seq.append(btn)
            return "break"

        def on_mouse_release(e):
            btn = f"MB_{e.num}"
            if btn in pressed_keys:
                pressed_keys.remove(btn)
            check_release()
            return "break"

        def on_mouse_wheel(e):
            dir_str = "UP" if e.delta > 0 else "DOWN"
            if f"MW_{dir_str}" not in recorded_seq:
                recorded_seq.append(f"MW_{dir_str}")
            self.root.after(100, check_release)
            return "break"

        recording_bind_ids["<KeyPress>"] = self.root.bind("<KeyPress>", on_key_press, add="+")
        recording_bind_ids["<KeyRelease>"] = self.root.bind("<KeyRelease>", on_key_release, add="+")
        recording_bind_ids["<ButtonPress>"] = self.root.bind("<ButtonPress>", on_mouse_press, add="+")
        recording_bind_ids["<ButtonRelease>"] = self.root.bind("<ButtonRelease>", on_mouse_release, add="+")
        recording_bind_ids["<MouseWheel>"] = self.root.bind("<MouseWheel>", on_mouse_wheel, add="+")
        
        def on_focus_out(e):
            if e.widget == self.root and getattr(self, 'recording_controllers', False):
                try:
                    if self.root.focus_get():
                        return
                except: pass
                import ctypes
                import win32con
                vk_map = {}
                for name in dir(win32con):
                    if name.startswith("VK_"):
                        val = getattr(win32con, name)
                        if val not in vk_map:
                            vk_map[val] = name[3:]
                for vk in range(8, 255):
                    if ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000:
                        if vk in vk_map:
                            if f"VK_{vk_map[vk]}" not in recorded_seq:
                                recorded_seq.append(f"VK_{vk_map[vk]}")
                        elif (65 <= vk <= 90) or (48 <= vk <= 57):
                            if f"VK_{chr(vk)}" not in recorded_seq:
                                recorded_seq.append(f"VK_{chr(vk)}")
                end_recording()
        recording_bind_ids["<FocusOut>"] = self.root.bind("<FocusOut>", on_focus_out, add="+")
        

        def poll_controller():
            if not getattr(self, 'recording_controllers', False):
                return
            from config import SWITCH_BUTTONS
            any_pressed = False
            reverse_map = {v: k for k, v in SWITCH_BUTTONS.items() if k not in ["Capture", "PS_C_Click"]}
            
            for vc in getattr(self, 'current_controllers', []):
                if vc is None: continue
                for c in vc.controllers:
                    raw = getattr(c, 'raw_buttons', 0)
                    if raw:
                        any_pressed = True
                        if not getattr(self, 'waiting_for_controller_release', False):
                            for bit, btn_name in reverse_map.items():
                                if raw & bit:
                                    self.recorded_controller_buttons.add(f"BTN_{btn_name}")
                                    if f"BTN_{btn_name}" not in recorded_seq:
                                        recorded_seq.append(f"BTN_{btn_name}")
            
            if getattr(self, 'waiting_for_controller_release', False):
                if not any_pressed:
                    self.waiting_for_controller_release = False
            else:
                self.controller_buttons_pressed = any_pressed
                if not any_pressed and self.recorded_controller_buttons and not pressed_keys:
                    end_recording()
                    return
            self.root.after(50, poll_controller)
            
        poll_controller()

    def create_mapping_widget(self, parent, key, label_text, mapping_scope=None, compact=False, fixed_size=None):
        suffix = self._mapping_scope_suffix(mapping_scope)
        attr_key = self._mapping_attr(key, suffix)
        is_in_app_simul = key.endswith("_in_app_gyro_simul")
        parent_bg = parent.cget("bg") if hasattr(parent, "cget") else background_color
        if label_text:
            tk.Label(parent, text=label_text, bg=parent_bg, fg=text_color, font=scale_font(("Arial", 11, "bold"))).pack(side=tk.LEFT, padx=(int(5 * scaling_factor), int(2 * scaling_factor)))
        container = tk.Frame(parent, bg=parent_bg)
        if fixed_size is not None:
            container.config(width=fixed_size[0], height=fixed_size[1])
            container.pack(side=tk.LEFT)
            container.pack_propagate(False)
        else:
            container.pack(side=tk.LEFT, padx=0 if compact else int(2 * scaling_factor))

        def pack_combo():
            if fixed_size is not None:
                combo.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            else:
                combo.pack(side=tk.LEFT)

        def sync_joystick_direction(value):
            base_key, sep, direction = key.rpartition("_")
            if sep and base_key in ("l_joystick", "r_joystick") and direction in ("up", "down", "left", "right", "click"):
                current = CONFIG.get_joystick_custom_scoped(base_key, mapping_scope)
                current[direction] = value
                CONFIG.set_joystick_custom_scoped(base_key, current, mapping_scope)

        def set_mapping_value(value):
            """Write a Mapping value and mirror Joy-Con IR bridge controls live."""
            CONFIG.set_mapping_setting_scoped(key, value, mapping_scope)
            self._joycon_ir_live_save(key, value)
        
        combo = BackButtonSelector(
            container,
            self,
            key=key,
            font=scale_font(("Arial", 10 if fixed_size is not None else 11, "bold")),
            auto_fit=fixed_size is None,
            fixed_size=fixed_size,
        )

        custom_frame = tk.Frame(container, bg=parent_bg)
        
        mode_var = tk.StringVar(value="Hold")
        def toggle_mode():
            new_mode = "Tap" if mode_var.get() == "Hold" else "Hold"
            mode_var.set(new_mode)
            mode_btn.config(text=new_mode)
            current_val = CONFIG.get_mapping_setting_scoped(key, "Default", mapping_scope)
            mouse_click_mapping = parse_mouse_click_mapping(current_val)
            if mouse_click_mapping:
                option_token, _mode = mouse_click_mapping
                new_val = f"Custom[{new_mode}]:{MOUSE_CLICK_BACK_BUTTON_TOKENS[option_token]}"
                set_mapping_value(new_val)
                sync_joystick_direction(new_val)
                self.on_setting_changed()
            elif isinstance(current_val, str) and current_val.startswith("Custom"):
                if current_val.startswith("Custom[Tap]:") or current_val.startswith("Custom[Hold]:"):
                    new_val = f"Custom[{new_mode}]:{current_val.split(':', 1)[1]}"
                else:
                    new_val = f"Custom[{new_mode}]:{current_val[7:]}"
                set_mapping_value(new_val)
                sync_joystick_direction(new_val)
                self.on_setting_changed()

        mode_btn = tk.Button(custom_frame, text="Hold", bg=button_gray, fg="white", font=scale_font(("Arial", 9, "bold")), bd=0, relief=tk.FLAT, command=toggle_mode, width=4)
        mode_btn.pack(side=tk.LEFT, padx=(0, int(2 * scaling_factor)), fill=tk.Y)
        
        entry = RecordingEntry(custom_frame, normal_font=scale_font(("Arial", 11, "bold")), prefix_font=scale_font(("Arial", 8, "bold")), width=14 if is_in_app_simul else 11, bg=button_gray, fg="white")
        entry.pack(side=tk.LEFT, fill=tk.Y)
        # Hovering the (fixed-width, often clipped) recording shows its full content.
        Tooltip(entry, entry.get)
        
        entry.restart_custom_recording_fn = lambda: self.start_custom_recording(key, entry, combo, custom_frame, mode_var, mapping_scope)
        # Gyro Lock / Mode Shift are fixed tokens, not recorded inputs, so don't re-record on click.
        entry.bind("<Button-1>", lambda e: None if combo.get() in (GYRO_LOCK_LABEL, MODE_SHIFT_LABEL) else entry.restart_custom_recording_fn())
        
        in_app_gyro_btn = tk.Button(custom_frame, bg=button_gray, fg="white", font=scale_font(("Arial", 10, "bold")), bd=0, relief=tk.FLAT, command=lambda: show_in_app_gyro_popup())
        mouse_click_btn = tk.Button(custom_frame, bg=button_gray, fg="white", font=scale_font(("Arial", 10, "bold")), bd=0, relief=tk.FLAT)

        def select_mouse_click_popup_value(value):
            apply_back_button_selection(value)

        mouse_click_btn._mouse_click_token = "Default"
        mouse_click_btn.get = lambda: getattr(mouse_click_btn, "_mouse_click_token", "Default")
        mouse_click_btn.display_label = back_button_label
        mouse_click_btn.select_value = select_mouse_click_popup_value
        mouse_click_btn.config(command=lambda: self.open_back_button_popup(mouse_click_btn))

        def clear_mouse_click_state(reset_mode=False):
            mouse_click_btn._mouse_click_token = "Default"
            mouse_click_btn.pack_forget()
            if reset_mode:
                mode_var.set("Hold")
                mode_btn.config(text="Hold")

        def request_in_app_simul_reflow(force_base=False):
            if not is_in_app_simul:
                return
            popup_for_reflow = getattr(self, "in_app_gyro_popup", None)
            if popup_for_reflow is None:
                return
            if force_base:
                reflow_now = getattr(popup_for_reflow, "in_app_reflow_simultaneous_input", None)
                if callable(reflow_now):
                    try:
                        reflow_now(force_base=True)
                        return
                    except tk.TclError:
                        pass
            def do_reflow():
                try:
                    if popup_for_reflow.winfo_exists():
                        popup_for_reflow.event_generate("<<InAppGyroSimulReflow>>")
                except tk.TclError:
                    pass
            self.root.after_idle(do_reflow)

        def reset_custom_mapping_widgets(reset_mouse=False):
            if reset_mouse:
                mouse_click_btn._mouse_click_token = "Default"
            for widget in (mode_btn, entry, in_app_gyro_btn, mouse_click_btn, close_btn):
                try:
                    widget.pack_forget()
                except tk.TclError:
                    pass

        def render_custom_mapping(include_close=True):
            reset_custom_mapping_widgets(reset_mouse=True)
            mode_btn.pack(side=tk.LEFT, padx=(0, int(2 * scaling_factor)), fill=tk.Y)
            entry.pack(side=tk.LEFT, fill=tk.Y)
            if include_close:
                close_btn.pack(side=tk.LEFT, padx=(int(2 * scaling_factor), 0), fill=tk.Y)
            custom_frame.pack(side=tk.LEFT)
            request_in_app_simul_reflow()

        def render_action_button_mapping(button, include_close=True, expand_button=False):
            reset_custom_mapping_widgets(reset_mouse=(button is not mouse_click_btn))
            mode_btn.pack(side=tk.LEFT, padx=(0, int(2 * scaling_factor)), fill=tk.Y)
            button.pack(side=tk.LEFT, fill=tk.BOTH if expand_button else tk.Y, expand=expand_button)
            if include_close:
                close_btn.pack(side=tk.LEFT, padx=(int(2 * scaling_factor), 0), fill=tk.Y)
            custom_frame.pack(side=tk.LEFT)
            request_in_app_simul_reflow()

        def clear_in_app_gyro_settings():
            CONFIG.set_mapping_setting_scoped(f"{key}_in_app_gyro_simul", "None", None)
            CONFIG.set_mapping_setting_scoped(f"{key}_in_app_gyro_dampening_mode", "Off", None)
            CONFIG.set_mapping_setting_scoped(f"{key}_in_app_gyro_dampening_amount", 90, None)
            CONFIG.set_mapping_setting_scoped(f"{key}_in_app_gyro_dampening_effect_after_released_ms", 200, None)
            CONFIG.set_mapping_setting_scoped(f"{key}_in_app_gyro_deadzone_mode", [], None)
            CONFIG.set_mapping_setting_scoped(f"{key}_in_app_gyro_deadzone_amount", 15.0, None)
            CONFIG.set_mapping_setting_scoped(f"{key}_in_app_gyro_deadzone_pause_after_pressed_ms", 100, None)
            CONFIG.set_mapping_setting_scoped(f"{key}_in_app_gyro_deadzone_pause_after_released_ms", 100, None)
            CONFIG.set_mapping_setting_scoped(f"{key}_in_app_gyro_deadzone_effect_after_released_ms", 200, None)

        def on_close():
            reset_value = "None" if is_in_app_simul else "Default"
            cancel_recording = getattr(self, "_cancel_custom_recording_without_commit", None)
            if callable(cancel_recording):
                cancel_recording()
            reset_custom_mapping_widgets(reset_mouse=True)
            custom_frame.pack_forget()
            cp_frame.pack_forget()
            mode_var.set("Hold")
            mode_btn.config(text="Hold")
            pack_combo()
            combo.set(reset_value)
            set_mapping_value(reset_value)
            sync_joystick_direction(reset_value)
            if reset_value == "Default":
                clear_in_app_gyro_settings()
            self.on_setting_changed()
            request_in_app_simul_reflow(force_base=True)
            if is_in_app_simul and getattr(self, "in_app_gyro_popup", None) is not None:
                self.root.after_idle(self.bind_in_app_gyro_popup_outside_click)
            if hasattr(self, 'focus_outline') and getattr(self.focus_outline, 'target_widget', None) == close_btn:
                try:
                    self.focus_outline.update(combo)
                except: pass

        close_btn = tk.Button(custom_frame, text="X", bg="#ff4444", fg="white", font=scale_font(("Arial", 10, "bold")), bd=0, relief=tk.FLAT, command=on_close)
        def cancel_recording_on_close_press(_event=None):
            cancel_recording = getattr(self, "_cancel_custom_recording_without_commit", None)
            if callable(cancel_recording):
                cancel_recording()
        close_btn.bind("<ButtonPress-1>", cancel_recording_on_close_press, add="+")

        def show_close_button():
            if not close_btn.winfo_ismapped():
                close_btn.pack(side=tk.LEFT, padx=(int(2 * scaling_factor), 0), fill=tk.Y)

        def hide_close_button():
            if close_btn.winfo_ismapped():
                close_btn.pack_forget()

        # "Change Profile" shows a button (opens an Auto/Manual popup) + X, like a
        # Joystick Custom mapping, instead of a plain combo selection.
        cp_frame = tk.Frame(container, bg=parent_bg)
        cp_btn = tk.Button(cp_frame, text="Change Profile", bg=button_gray, fg="white", font=scale_font(("Arial", 10, "bold")), bd=0, relief=tk.FLAT)
        cp_btn.pack(side=tk.LEFT, fill=tk.Y)
        cp_btn.config(command=lambda: self.open_change_profile_popup(cp_btn))

        def cp_close():
            cp_frame.pack_forget()
            clear_mouse_click_state(reset_mode=True)
            pack_combo()
            combo.set("Default")
            set_mapping_value("Default")
            sync_joystick_direction("Default")
            clear_in_app_gyro_settings()
            self.on_setting_changed()

        cp_close_btn = tk.Button(cp_frame, text="X", bg="#ff4444", fg="white", font=scale_font(("Arial", 10, "bold")), bd=0, relief=tk.FLAT, command=cp_close)
        cp_close_btn.pack(side=tk.LEFT, padx=(int(2 * scaling_factor), 0), fill=tk.Y)

        def show_change_profile(event=None):
            set_mapping_value("Change Profile")
            sync_joystick_direction("Change Profile")
            combo.pack_forget()
            custom_frame.pack_forget()
            clear_mouse_click_state(reset_mode=True)
            cp_frame.pack(side=tk.LEFT)
            self.on_setting_changed(event)

        def show_mouse_click_mapping(option_token, event=None, mode=None, preserve_mode=False, write_config=True):
            custom_token = MOUSE_CLICK_BACK_BUTTON_TOKENS.get(option_token)
            if custom_token is None:
                return
            if mode not in ("Hold", "Tap"):
                mode = mode_var.get() if preserve_mode and mode_var.get() in ("Hold", "Tap") else "Hold"
            mode_var.set(mode)
            mode_btn.config(text=mode)
            value = f"Custom[{mode}]:{custom_token}"
            mouse_click_btn._mouse_click_token = option_token
            mouse_click_btn.config(text=back_button_label(option_token))
            combo.pack_forget()
            render_action_button_mapping(
                mouse_click_btn,
                include_close=not is_in_app_simul,
                expand_button=is_in_app_simul,
            )
            combo.set(option_token)
            if write_config:
                set_mapping_value(value)
                sync_joystick_direction(value)
                self.on_setting_changed(event)

        def show_current():
            base_key, sep, direction = key.rpartition("_")
            if sep and base_key in ("l_joystick", "r_joystick") and direction in ("up", "down", "left", "right", "click"):
                current_val = CONFIG.get_joystick_custom_scoped(base_key, mapping_scope).get(direction, "Default")
            else:
                current_val = CONFIG.get_mapping_setting_scoped(key, "Default", mapping_scope)

            mouse_click_mapping = parse_mouse_click_mapping(current_val)
            if mouse_click_mapping:
                option_token, mode = mouse_click_mapping
                if current_val == option_token:
                    value = f"Custom[{mode}]:{MOUSE_CLICK_BACK_BUTTON_TOKENS[option_token]}"
                    set_mapping_value(value)
                    sync_joystick_direction(value)
                show_mouse_click_mapping(option_token, mode=mode, write_config=False)
                return
            
            if isinstance(current_val, str) and current_val.startswith("Custom") and IN_APP_GYRO_TOKEN in current_val:
                combo.pack_forget()
                
                simul_val = CONFIG.get_mapping_setting_scoped(f"{key}_in_app_gyro_simul", "None", None)
                display_str = IN_APP_GYRO_LABEL
                if simul_val not in ("None", "Default"):
                    if isinstance(simul_val, str) and simul_val.startswith("Custom"):
                        if "]:" in simul_val:
                            display_str += " + " + format_input_display(simul_val.split("]:")[1])
                        elif ":" in simul_val:
                            display_str += " + " + format_input_display(simul_val.split(":")[1])
                    else:
                        if simul_val == "HOME": display_str += " + Home"
                        elif simul_val == "CAPTURE": display_str += " + Capture"
                        elif simul_val == "PRTSC": display_str += " + PrtSc"
                        else: display_str += f" + {format_input_display(simul_val)}"
                
                in_app_gyro_btn.config(text=display_str)
                render_action_button_mapping(in_app_gyro_btn, include_close=True)
                combo.set(IN_APP_GYRO_LABEL)
                return

            if isinstance(current_val, str) and current_val.startswith("Custom"):
                render_custom_mapping(include_close=True)
                entry.config(state="normal")
                entry.delete(0, tk.END)

                if current_val.startswith("Custom[Tap]:"):
                    mode_var.set("Tap")
                    mode_btn.config(text="Tap")
                    display_val = current_val[12:]
                elif current_val.startswith("Custom[Hold]:"):
                    mode_var.set("Hold")
                    mode_btn.config(text="Hold")
                    display_val = current_val[13:]
                else:
                    mode_var.set("Hold")
                    mode_btn.config(text="Hold")
                    display_val = current_val[7:]

                if display_val == GYRO_LOCK_TOKEN:
                    entry.insert(0, GYRO_LOCK_LABEL)
                    combo.set(GYRO_LOCK_LABEL)
                elif display_val == MODE_SHIFT_TOKEN:
                    entry.insert(0, MODE_SHIFT_LABEL)
                    combo.set(MODE_SHIFT_LABEL)
                else:
                    display_val = format_input_display(display_val)
                    entry.insert(0, display_val)
                    combo.set("Custom")
                entry.config(state="readonly")
            elif current_val == "Change Profile":
                combo.set("Change Profile")
                custom_frame.pack_forget()
                clear_mouse_click_state(reset_mode=True)
                cp_frame.pack(side=tk.LEFT)
            else:
                combo.set(current_val)
                custom_frame.pack_forget()
                clear_mouse_click_state(reset_mode=True)
                pack_combo()

        show_current()

        def show_token_mapping(token, label, event=None):
            try:
                mode = mode_var.get() if mode_var.get() in ("Hold", "Tap") else "Hold"
            except tk.TclError:
                return
            mode_var.set(mode)
            mode_btn.config(text=mode)
            set_mapping_value(f"Custom[{mode}]:{token}")
            sync_joystick_direction(f"Custom[{mode}]:{token}")
            if in_app_gyro_btn:
                in_app_gyro_btn.pack_forget()
            render_custom_mapping(include_close=True)
            entry.config(state="normal")
            entry.delete(0, tk.END)
            entry.insert(0, label)
            entry.config(state="readonly")
            combo.pack_forget()
            self.on_setting_changed(event)

        def show_in_app_gyro_popup(event=None):
            # A click can be queued while its owning Mapping popup is being rebuilt.
            # Never let a stale command closure configure widgets that Tk has already
            # destroyed; the newly-created control owns subsequent interactions.
            try:
                if not in_app_gyro_btn.winfo_exists() or not mode_btn.winfo_exists():
                    return
            except tk.TclError:
                return
            # A Simultaneous Input button is a descendant of the In-app Gyro popup
            # which owns it.  Replacing that owner would destroy mode_btn midway
            # through this callback; leave the owner alive instead of recursing.
            existing_popup = getattr(self, "in_app_gyro_popup", None)
            if existing_popup is not None and existing_popup.winfo_exists():
                try:
                    ancestor = in_app_gyro_btn
                    while ancestor is not None:
                        if ancestor is existing_popup:
                            return
                        parent_name = ancestor.winfo_parent()
                        if not parent_name:
                            break
                        ancestor = ancestor.nametowidget(parent_name)
                except (tk.TclError, KeyError):
                    return
            if self._toggle_in_app_gyro_popup(in_app_gyro_btn): return
            if existing_popup is not None and existing_popup.winfo_exists():
                self.close_in_app_gyro_popup()
            
            mode = mode_var.get() if mode_var.get() in ("Hold", "Tap") else "Hold"
            mode_var.set(mode)
            try:
                if not mode_btn.winfo_exists():
                    return
                mode_btn.config(text=mode)
            except tk.TclError:
                return
            
            spacing = int(10 * scaling_factor)
            row_gap = int(8 * scaling_factor)
            section_gap = int(10 * scaling_factor)
            popup_padding = spacing
            popup = tk.Frame(self.root, bg=background_color, bd=1, relief=tk.SOLID, padx=popup_padding, pady=popup_padding)
            self.in_app_gyro_popup = popup
            self.in_app_gyro_popup_anchor = in_app_gyro_btn

            content_frame = tk.Frame(popup, bg=background_color)
            content_frame.pack(side=tk.TOP, anchor=tk.CENTER)
            popup_control_font = scale_font(("Arial", 10, "bold"))
            popup_control_measure = tkFont.Font(font=popup_control_font)
            popup_control_width = popup_control_measure.measure("0" * 14) + int(18 * scaling_factor)
            base_popup_control_width = popup_control_width
            simul_control_width = base_popup_control_width
            popup_control_height = popup_control_measure.metrics("linespace") + int(10 * scaling_factor)
            placement_state = {"anchor_coords": None, "full_size": None, "ready": False}
            popup_rows = []
            popup_row_meta = {}
            popup_separators = []
            numeric_committers = []
            numeric_commit_state = {"done": False}

            def create_aligned_popup_row(label_text, pady_top=0, pack_now=True):
                row = tk.Frame(content_frame, bg=background_color)
                row_index = len(popup_rows) + len(popup_separators)
                label_widget = tk.Label(
                    content_frame,
                    text=label_text,
                    bg=background_color,
                    fg=text_color,
                    font=scale_font(("Arial", 11, "bold")),
                    anchor="e",
                )
                control_cell = tk.Frame(content_frame, bg=background_color, width=popup_control_width, height=popup_control_height)
                control_cell.grid_propagate(False)
                meta = {
                    "row": row,
                    "row_index": row_index,
                    "label": label_widget,
                    "control_cell": control_cell,
                    "pady_top": int(pady_top * scaling_factor),
                    "visible": False,
                }
                popup_rows.append(meta)
                popup_row_meta[row] = meta
                if pack_now:
                    show_popup_row(row)
                return row, control_cell

            def create_popup_separator(pady_top=None, pack_now=True):
                row_index = len(popup_rows) + len(popup_separators)
                line = tk.Frame(content_frame, bg=button_gray, height=1)
                meta = {
                    "row_index": row_index,
                    "line": line,
                    "pady_top": section_gap if pady_top is None else int(pady_top * scaling_factor),
                    "visible": False,
                }
                popup_separators.append(meta)
                if pack_now:
                    show_popup_separator(meta)
                return meta

            def show_popup_separator(meta):
                meta["line"].grid(row=meta["row_index"], column=0, columnspan=2, sticky=tk.EW, pady=(meta["pady_top"], 0))
                meta["visible"] = True

            def show_popup_row(row):
                meta = popup_row_meta[row]
                pady = (meta["pady_top"], 0)
                meta["label"].grid(row=meta["row_index"], column=0, sticky=tk.E, padx=(0, int(5 * scaling_factor)), pady=pady)
                meta["control_cell"].grid(row=meta["row_index"], column=1, sticky=tk.W, pady=pady)
                meta["visible"] = True

            def hide_popup_row(row):
                meta = popup_row_meta[row]
                meta["label"].grid_remove()
                meta["control_cell"].grid_remove()
                meta["visible"] = False

            def sync_in_app_popup_layout(force_all=False):
                active_rows = popup_rows if force_all else [meta for meta in popup_rows if meta["visible"]]
                if not active_rows:
                    return
                popup.update_idletasks()
                label_col_width = max(meta["label"].winfo_reqwidth() for meta in active_rows)
                content_frame.grid_columnconfigure(0, minsize=label_col_width)
                content_frame.grid_columnconfigure(1, minsize=popup_control_width)
                content_width = label_col_width + int(5 * scaling_factor) + popup_control_width
                for meta in popup_rows:
                    meta["label"].config(width=0)
                    cell_width = simul_control_width if meta["control_cell"] is simul_cell else base_popup_control_width
                    meta["control_cell"].config(width=cell_width, height=popup_control_height)
                for meta in popup_separators:
                    meta["line"].config(width=content_width, height=1)
                popup.update_idletasks()

            def estimate_full_requested_size():
                popup.update_idletasks()
                label_col_width = max((meta["label"].winfo_reqwidth() for meta in popup_rows), default=0)
                width = label_col_width + int(5 * scaling_factor) + popup_control_width + popup_padding * 2 + 2
                height = popup_padding * 2 + 2
                for meta in popup_rows:
                    height += meta["pady_top"] + max(meta["label"].winfo_reqheight(), popup_control_height)
                for meta in popup_separators:
                    height += meta["pady_top"] + 1
                return (max(1, width), max(1, height))

            def _place_in_app_gyro_popup():
                if not placement_state["ready"]:
                    return
                # sync_in_app_popup_layout() ends with update_idletasks and
                # _place_popup_within_root_bounds does its own, so an extra pass here is
                # redundant reflow on every row show/hide.
                sync_in_app_popup_layout()
                anchor = getattr(popup, "in_app_visible_anchor", in_app_gyro_btn)
                self._place_popup_within_root_bounds(
                    popup,
                    anchor,
                    fallback_coords=placement_state["anchor_coords"],
                    requested_size=placement_state["full_size"],
                )
                for menu_attr, anchor_attr in (
                    ("deadzone_input_popup", "deadzone_input_popup_anchor"),
                    ("dampening_input_popup", "dampening_input_popup_anchor"),
                ):
                    menu = getattr(self, menu_attr, None)
                    anchor = getattr(self, anchor_attr, None)
                    if menu is not None and menu.winfo_exists():
                        if anchor is not None and anchor.winfo_exists():
                            self._place_popup_within_root_bounds(menu, anchor)
                        menu.lift()

            _row, simul_cell = create_aligned_popup_row("Simultaneous Input:", pady_top=0)
            simul_inner = tk.Frame(simul_cell, bg=background_color)
            simul_inner.pack(side=tk.LEFT)
            
            simul_key = f"{key}_in_app_gyro_simul"
            self.create_mapping_widget(
                simul_inner,
                simul_key,
                "",
                None,
                compact=True,
                fixed_size=(popup_control_width, popup_control_height),
            )
            
            suffix = self._mapping_scope_suffix(None)
            simul_combo = getattr(self, f"{self._mapping_attr(simul_key, suffix)}_combo", None)
            simul_container = getattr(self, f"{self._mapping_attr(simul_key, suffix)}_container", None)
            simul_entry = getattr(self, f"{self._mapping_attr(simul_key, suffix)}_entry", None)
            simul_custom_frame = getattr(self, f"{self._mapping_attr(simul_key, suffix)}_custom_frame", None)
            simul_mode_btn = getattr(self, f"{self._mapping_attr(simul_key, suffix)}_mode_btn", None)
            simul_mode_var = getattr(self, f"{self._mapping_attr(simul_key, suffix)}_mode_var", None)
            
            s_val = CONFIG.get_mapping_setting_scoped(simul_key, "None", None)
            if simul_combo:
                simul_combo.set(s_val)
                Tooltip(simul_combo, lambda: simul_combo.cget("text"))
            
            if isinstance(s_val, str) and s_val.startswith("Custom") and simul_combo and simul_custom_frame and simul_entry:
                simul_combo.pack_forget()
                simul_custom_frame.pack(side=tk.LEFT)
                simul_entry.config(state="normal")
                simul_entry.delete(0, tk.END)
                if s_val.startswith("Custom[Tap]:"):
                    if simul_mode_var: simul_mode_var.set("Tap")
                    if simul_mode_btn: simul_mode_btn.config(text="Tap")
                    display_val = s_val[12:]
                elif s_val.startswith("Custom[Hold]:"):
                    if simul_mode_var: simul_mode_var.set("Hold")
                    if simul_mode_btn: simul_mode_btn.config(text="Hold")
                    display_val = s_val[13:]
                else:
                    if simul_mode_var: simul_mode_var.set("Hold")
                    if simul_mode_btn: simul_mode_btn.config(text="Hold")
                    display_val = s_val[7:]
                simul_entry.insert(0, format_input_display(display_val))
                simul_entry.config(state="readonly")

            def reflow_simultaneous_input(*_args, force_base=False):
                """Let the compound Mapping control widen the In-app Gyro popup.

                A fixed standard control column is sufficient for a selector, but not
                for Hold/Tap + a full action label + X.  The requested width grows to
                the actual compound control width; placement then preferentially
                extends right from the anchor and clamps only at the root boundary.
                """
                nonlocal popup_control_width, simul_control_width
                try:
                    popup.update_idletasks()
                    current_value = CONFIG.get_mapping_setting_scoped(simul_key, "None", None)
                    required = base_popup_control_width
                    if (not force_base
                            and simul_custom_frame is not None
                            and isinstance(current_value, str)
                            and current_value.startswith("Custom")):
                        required = max(required, simul_custom_frame.winfo_reqwidth() + int(2 * scaling_factor))
                except Exception:
                    return
                if required == simul_control_width:
                    return
                simul_control_width = required
                popup_control_width = max(base_popup_control_width, simul_control_width)
                simul_cell.config(width=simul_control_width, height=popup_control_height)
                simul_inner.config(width=simul_control_width, height=popup_control_height)
                if simul_container is not None:
                    simul_container.config(width=simul_control_width, height=popup_control_height)
                if simul_custom_frame is not None:
                    simul_custom_frame.update_idletasks()
                placement_state["full_size"] = estimate_full_requested_size()
                popup.in_app_full_requested_size = placement_state["full_size"]
                sync_in_app_popup_layout()
                popup.update_idletasks()
                anchor = getattr(popup, "in_app_visible_anchor", in_app_gyro_btn)
                self._place_popup_within_root_bounds(
                    popup,
                    anchor,
                    fallback_coords=placement_state["anchor_coords"],
                    requested_size=placement_state["full_size"],
                )

            popup.in_app_reflow_simultaneous_input = reflow_simultaneous_input

            def schedule_simultaneous_reflow(*_args):
                self.root.after_idle(reflow_simultaneous_input)

            if simul_combo is not None:
                simul_combo.bind("<<ComboboxSelected>>", schedule_simultaneous_reflow, add="+")
            if simul_custom_frame is not None:
                simul_custom_frame.bind("<Configure>", schedule_simultaneous_reflow, add="+")
                simul_custom_frame.bind("<ButtonRelease-1>", schedule_simultaneous_reflow, add="+")
            for widget in (simul_inner, simul_container, simul_entry, simul_mode_btn):
                if widget is not None:
                    widget.bind("<ButtonRelease-1>", schedule_simultaneous_reflow, add="+")
                    widget.bind("<KeyRelease>", schedule_simultaneous_reflow, add="+")
            popup.bind("<<InAppGyroSimulReflow>>", schedule_simultaneous_reflow, add="+")
            self.root.after_idle(reflow_simultaneous_input)

            create_popup_separator()
            dz_row, dz_control_cell = create_aligned_popup_row("Trigger Deadzone:", pady_top=section_gap / scaling_factor)

            dz_mode_key = f"{key}_in_app_gyro_deadzone_mode"
            dz_button_group = tk.Frame(dz_control_cell, bg=background_color, width=popup_control_width, height=popup_control_height)
            dz_button_group.pack(side=tk.LEFT)
            dz_button_group.pack_propagate(False)
            dz_button = tk.Button(
                dz_button_group,
                bg=button_gray,
                fg="white",
                font=popup_control_font,
                bd=0,
                relief=tk.FLAT,
                width=14,
            )
            dz_button.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

            def create_numeric_setting_row(label_text, setting_key, default_value, min_value=0.0, max_value=None, integer=False, suffix_text=""):
                row, control_cell = create_aligned_popup_row(label_text, pady_top=row_gap / scaling_factor, pack_now=False)
                try:
                    initial_value = float(CONFIG.get_mapping_setting_scoped(setting_key, default_value, None))
                except Exception:
                    initial_value = float(default_value)
                if integer:
                    initial_text = str(int(round(initial_value)))
                elif initial_value.is_integer():
                    initial_text = str(int(initial_value))
                else:
                    initial_text = str(initial_value)
                var = tk.StringVar(value=initial_text)
                input_group = tk.Frame(control_cell, bg=background_color, width=popup_control_width, height=popup_control_height)
                input_group.pack(side=tk.LEFT)
                input_group.pack_propagate(False)
                entry_widget = tk.Entry(
                    input_group,
                    textvariable=var,
                    bg=button_gray,
                    fg=text_color,
                    insertbackground=text_color,
                    relief=tk.FLAT,
                    bd=0,
                    font=popup_control_font,
                    justify=tk.CENTER,
                )
                # Metadata for gamepad numeric adjust (_nav_adjust_numeric_entry) so it steps
                # and clamps precisely; commit still flows through the textvariable trace.
                entry_widget.num_min = min_value
                entry_widget.num_max = max_value
                entry_widget.num_integer = integer
                if suffix_text:
                    suffix_label = tk.Label(input_group, text=suffix_text, bg=background_color, fg=text_color, font=popup_control_font)
                    suffix_label.pack(side=tk.RIGHT, fill=tk.Y, padx=(int(4 * scaling_factor), 0))
                    entry_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                else:
                    entry_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

                def commit_value(event=None, normalize_text=True, save=True):
                    # Re-entrancy guard: the var.set(...) normalization below re-fires the
                    # write-trace commit_on_change, which would save again (save defaults
                    # True) -- that cascade was the residual save when the popup closes
                    # (commit_numeric_settings / FocusOut both trigger it). Suppress the
                    # trace-driven commit while we are inside commit_value.
                    if getattr(self, "_in_app_numeric_committing", False):
                        return
                    # An empty / non-numeric var is a transient state (widget teardown, a
                    # <FocusOut> during re-navigation, or mid-edit). Keep the last committed
                    # value instead of collapsing to default_value -- that fallback was the
                    # only source of the "jumps to default" on gamepad re-adjust after reopen.
                    try:
                        raw = (var.get() or "").strip()
                    except Exception:
                        raw = ""
                    if raw == "":
                        return
                    try:
                        value = float(raw)
                    except (TypeError, ValueError):
                        return
                    self._in_app_numeric_committing = True
                    try:
                        value = max(float(min_value), value)
                        if max_value is not None:
                            value = min(float(max_value), value)
                        stored = int(round(value)) if integer else float(value)
                        CONFIG.set_mapping_setting_scoped(setting_key, stored, None)
                        self._joycon_ir_live_save(setting_key, stored)
                        if save:
                            CONFIG.save_config()
                        if normalize_text:
                            if isinstance(stored, float) and stored.is_integer():
                                var.set(str(int(stored)))
                            else:
                                var.set(str(stored))
                    finally:
                        self._in_app_numeric_committing = False

                def commit_on_change(*_args):
                    if getattr(self, "_in_app_numeric_committing", False):
                        return
                    try:
                        float(var.get())
                    except Exception:
                        return
                    commit_value(normalize_text=False)

                # FocusOut fires when the popup is closed (focus leaves the entry); the value
                # is already persisted live by commit_on_change per keystroke, so don't save
                # again here -- that was the residual save on window close.
                entry_widget.bind("<FocusOut>", lambda e: commit_value(e, save=False))
                entry_widget.bind("<Return>", commit_value)
                var.trace_add("write", commit_on_change)
                numeric_committers.append(commit_value)
                return row, commit_value

            def commit_numeric_settings():
                if numeric_commit_state["done"]:
                    return
                numeric_commit_state["done"] = True
                # Runs only on close: a final (harmless) commit of each numeric value with
                # NO save -- every edit already persisted live per keystroke / FocusOut (and
                # live-saved into the IR store via _joycon_ir_live_save), so closing does no
                # extra save.
                for commit in numeric_committers:
                    try:
                        commit(save=False)
                    except Exception:
                        pass

            self.in_app_gyro_popup_commit_numeric = commit_numeric_settings

            dz_amt_key = f"{key}_in_app_gyro_deadzone_amount"
            dz_pause_pressed_key = f"{key}_in_app_gyro_deadzone_pause_after_pressed_ms"
            dz_pause_released_key = f"{key}_in_app_gyro_deadzone_pause_after_released_ms"
            dz_effect_released_key = f"{key}_in_app_gyro_deadzone_effect_after_released_ms"

            dz_amt_row, _commit_dz_amt = create_numeric_setting_row("Deadzone:", dz_amt_key, 15.0, 0.0, None, False)
            dz_pause_pressed_row, _commit_dz_pause_pressed = create_numeric_setting_row("Gyro Pause After Pressed:", dz_pause_pressed_key, 100, 0, None, True, "ms")
            dz_pause_released_row, _commit_dz_pause_released = create_numeric_setting_row("Gyro Pause After Released:", dz_pause_released_key, 100, 0, None, True, "ms")
            dz_effect_released_row, _commit_dz_effect_released = create_numeric_setting_row("Deadzone Effect After Released:", dz_effect_released_key, 200, 0, None, True, "ms")
            dz_setting_rows = [
                dz_amt_row,
                dz_pause_pressed_row,
                dz_pause_released_row,
                dz_effect_released_row,
            ]

            def dz_display_text():
                selected = normalize_dampening_inputs(CONFIG.get_mapping_setting_scoped(dz_mode_key, [], None))
                if not selected:
                    return "None"
                return " | ".join(back_button_label(token) for token in selected)

            def refresh_dz_button():
                selected = normalize_dampening_inputs(CONFIG.get_mapping_setting_scoped(dz_mode_key, [], None))
                dz_button.config(text=dz_display_text())
                if selected:
                    for setting_row in dz_setting_rows:
                        show_popup_row(setting_row)
                else:
                    for setting_row in dz_setting_rows:
                        hide_popup_row(setting_row)
                _place_in_app_gyro_popup()

            Tooltip(dz_button, dz_display_text)

            def close_deadzone_input_popup():
                dz_popup = getattr(self, "deadzone_input_popup", None)
                if dz_popup is not None and dz_popup.winfo_exists():
                    dz_popup.destroy()
                self.deadzone_input_popup = None
                self.deadzone_input_popup_anchor = None

            def open_deadzone_input_popup():
                existing = getattr(self, "deadzone_input_popup", None)
                if existing is not None and existing.winfo_exists() and getattr(self, "deadzone_input_popup_anchor", None) is dz_button:
                    close_deadzone_input_popup()
                    return
                close_deadzone_input_popup()
                selected = set(normalize_dampening_inputs(CONFIG.get_mapping_setting_scoped(dz_mode_key, [], None)))
                from config import BACK_BUTTON_CATEGORIES

                spacing2 = int(10 * scaling_factor)
                column_gap = int(8 * scaling_factor)
                btn_gap = int(5 * scaling_factor)
                btn_font = scale_font(("Arial", 9, "bold"))
                measure = tkFont.Font(font=btn_font)
                max_label_w = 0
                for _title, rows in BACK_BUTTON_CATEGORIES:
                    for row_values in rows:
                        for token in row_values:
                            max_label_w = max(max_label_w, measure.measure(back_button_label(token)))
                btn_w = max_label_w + int(16 * scaling_factor)
                btn_h = measure.metrics("linespace") + int(10 * scaling_factor)

                dz_popup = tk.Frame(self.root, bg=background_color, bd=1, relief=tk.SOLID, padx=column_gap, pady=spacing2)
                self.deadzone_input_popup = dz_popup
                self.deadzone_input_popup_anchor = dz_button
                button_refs = {}

                def set_button_state(token):
                    frame, btn = button_refs[token]
                    is_selected = token in selected
                    bd = int(2 * scaling_factor) if is_selected else 0
                    frame.config(bg=highlight_color if is_selected else background_color)
                    btn.place(x=bd, y=bd, width=btn_w - 2 * bd, height=btn_h - 2 * bd)

                def toggle_token(token):
                    if token in selected:
                        selected.remove(token)
                    else:
                        selected.add(token)
                    ordered = [token for token in SWITCH_INPUT_DAMPENING_OPTIONS if token in selected]
                    CONFIG.set_mapping_setting_scoped(dz_mode_key, ordered, None)
                    self._joycon_ir_live_save(dz_mode_key, ordered)
                    CONFIG.save_config()
                    set_button_state(token)
                    refresh_dz_button()

                cats = dict(BACK_BUTTON_CATEGORIES)
                block = tk.Frame(dz_popup, bg=background_color)
                block.pack(side=tk.TOP, anchor=tk.W)
                for c_idx, col in enumerate(cats["Switch Input"]):
                    for r_idx, token in enumerate(col):
                        cell = tk.Frame(block, bg=background_color, width=btn_w, height=btn_h)
                        cell.grid(row=r_idx, column=c_idx, padx=(0, btn_gap), pady=(0, btn_gap), sticky="nsew")
                        cell.grid_propagate(False)
                        btn = tk.Button(cell, text=back_button_label(token), font=btn_font,
                                        bg=button_gray, fg="white", relief=tk.FLAT, bd=0,
                                        highlightthickness=0, takefocus=0,
                                        activebackground=highlight_color, activeforeground="white",
                                        command=lambda t=token: toggle_token(t))
                        button_refs[token] = (cell, btn)
                        set_button_state(token)

                dz_popup.place(in_=self.root, x=-10000, y=-10000)
                dz_popup.update_idletasks()
                self._place_popup_within_root_bounds(dz_popup, dz_button)

            dz_button.config(command=open_deadzone_input_popup)
            refresh_dz_button()

            create_popup_separator()
            damp_row, damp_control_cell = create_aligned_popup_row("Trigger Dampening:", pady_top=section_gap / scaling_factor)
            
            damp_mode_key = f"{key}_in_app_gyro_dampening_mode"
            damp_button_width = 14
            damp_button_group = tk.Frame(damp_control_cell, bg=background_color, width=popup_control_width, height=popup_control_height)
            damp_button_group.pack(side=tk.LEFT)
            damp_button_group.pack_propagate(False)
            damp_button = tk.Button(
                damp_button_group,
                bg=button_gray,
                fg="white",
                font=popup_control_font,
                bd=0,
                relief=tk.FLAT,
                width=damp_button_width,
            )
            damp_button.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    
            damp_amt_row, damp_amt_control_cell = create_aligned_popup_row("Dampening Amount %:", pady_top=row_gap / scaling_factor, pack_now=False)
            
            damp_amt_key = f"{key}_in_app_gyro_dampening_amount"
            damp_amt_val = CONFIG.get_mapping_setting_scoped(damp_amt_key, 90, None)
            
            def on_damp_amt_change(val):
                CONFIG.set_mapping_setting_scoped(damp_amt_key, int(float(val)), None)
                self._joycon_ir_live_save(damp_amt_key, int(float(val)))
                CONFIG.save_config()
                
            damp_scale = tk.Scale(damp_amt_control_cell, from_=0, to=100, resolution=1, orient=tk.HORIZONTAL, length=popup_control_width, bg=background_color, fg=text_color, troughcolor=button_gray, activebackground=highlight_color, highlightthickness=0, bd=0, sliderrelief=tk.FLAT, sliderlength=int(15 * scaling_factor), width=int(15 * scaling_factor), font=popup_control_font, command=on_damp_amt_change)
            damp_scale.set(damp_amt_val)
            damp_scale.pack(side=tk.LEFT)

            damp_effect_released_key = f"{key}_in_app_gyro_dampening_effect_after_released_ms"
            damp_effect_released_row, _commit_damp_effect_released = create_numeric_setting_row(
                "Dampening Effect After Released:",
                damp_effect_released_key,
                200,
                0,
                None,
                True,
                "ms",
            )
            damp_setting_rows = [damp_amt_row, damp_effect_released_row]

            def damp_display_text():
                selected = normalize_dampening_inputs(CONFIG.get_mapping_setting_scoped(damp_mode_key, [], None))
                if not selected:
                    return "None"
                return " | ".join(back_button_label(token) for token in selected)

            def refresh_damp_button():
                selected = normalize_dampening_inputs(CONFIG.get_mapping_setting_scoped(damp_mode_key, [], None))
                damp_button.config(text=damp_display_text())
                if selected:
                    for setting_row in damp_setting_rows:
                        show_popup_row(setting_row)
                else:
                    for setting_row in damp_setting_rows:
                        hide_popup_row(setting_row)
                _place_in_app_gyro_popup()

            Tooltip(damp_button, damp_display_text)

            def close_dampening_input_popup():
                damp_popup = getattr(self, "dampening_input_popup", None)
                if damp_popup is not None and damp_popup.winfo_exists():
                    damp_popup.destroy()
                self.dampening_input_popup = None
                self.dampening_input_popup_anchor = None

            def open_dampening_input_popup():
                existing = getattr(self, "dampening_input_popup", None)
                if existing is not None and existing.winfo_exists() and getattr(self, "dampening_input_popup_anchor", None) is damp_button:
                    close_dampening_input_popup()
                    return
                close_dampening_input_popup()
                selected = set(normalize_dampening_inputs(CONFIG.get_mapping_setting_scoped(damp_mode_key, [], None)))
                from config import BACK_BUTTON_CATEGORIES

                spacing2 = int(10 * scaling_factor)
                column_gap = int(8 * scaling_factor)
                btn_gap = int(5 * scaling_factor)
                btn_font = scale_font(("Arial", 9, "bold"))
                measure = tkFont.Font(font=btn_font)
                max_label_w = 0
                for _title, rows in BACK_BUTTON_CATEGORIES:
                    for row_values in rows:
                        for token in row_values:
                            max_label_w = max(max_label_w, measure.measure(back_button_label(token)))
                btn_w = max_label_w + int(16 * scaling_factor)
                btn_h = measure.metrics("linespace") + int(10 * scaling_factor)

                damp_popup = tk.Frame(self.root, bg=background_color, bd=1, relief=tk.SOLID, padx=column_gap, pady=spacing2)
                self.dampening_input_popup = damp_popup
                self.dampening_input_popup_anchor = damp_button
                button_refs = {}

                def set_button_state(token):
                    frame, btn = button_refs[token]
                    is_selected = token in selected
                    bd = int(2 * scaling_factor) if is_selected else 0
                    frame.config(bg=highlight_color if is_selected else background_color)
                    btn.place(x=bd, y=bd, width=btn_w - 2 * bd, height=btn_h - 2 * bd)

                def toggle_token(token):
                    if token in selected:
                        selected.remove(token)
                    else:
                        selected.add(token)
                    ordered = [token for token in SWITCH_INPUT_DAMPENING_OPTIONS if token in selected]
                    CONFIG.set_mapping_setting_scoped(damp_mode_key, ordered, None)
                    self._joycon_ir_live_save(damp_mode_key, ordered)
                    CONFIG.save_config()
                    set_button_state(token)
                    refresh_damp_button()

                cats = dict(BACK_BUTTON_CATEGORIES)
                block = tk.Frame(damp_popup, bg=background_color)
                block.pack(side=tk.TOP, anchor=tk.W)
                for c_idx, col in enumerate(cats["Switch Input"]):
                    for r_idx, token in enumerate(col):
                        cell = tk.Frame(block, bg=background_color, width=btn_w, height=btn_h)
                        cell.grid(row=r_idx, column=c_idx, padx=(0, btn_gap), pady=(0, btn_gap), sticky="nsew")
                        cell.grid_propagate(False)
                        btn = tk.Button(cell, text=back_button_label(token), font=btn_font,
                                        bg=button_gray, fg="white", relief=tk.FLAT, bd=0,
                                        highlightthickness=0, takefocus=0,
                                        activebackground=highlight_color, activeforeground="white",
                                        command=lambda t=token: toggle_token(t))
                        button_refs[token] = (cell, btn)
                        set_button_state(token)

                damp_popup.place(in_=self.root, x=-10000, y=-10000)
                damp_popup.update_idletasks()
                self._place_popup_within_root_bounds(damp_popup, damp_button)

            damp_button.config(command=open_dampening_input_popup)
            refresh_damp_button()

            def on_popup_destroy(e):
                if str(e.widget) == str(popup):
                    commit_numeric_settings()
                    close_deadzone_input_popup()
                    close_dampening_input_popup()
                    final_val = CONFIG.get_mapping_setting_scoped(simul_key, "None", None)
                    display_str = IN_APP_GYRO_LABEL
                    if final_val == "None":
                        pass
                    elif final_val == "Default":
                        def get_key_name(k):
                            return {"home": "Home", "capt": "Capture", "c": "Chat", "plus": "Plus", "minus": "Minus", "up": "Dpad Up", "down": "Dpad Down", "left": "Dpad Left", "right": "Dpad Right", "l_stk": "L Joystick Click", "r_stk": "R Joystick Click", "sll": "SL_L", "srl": "SR_L", "slr": "SL_R", "srr": "SR_R"}.get(k, k.upper())
                        display_str += f" + {get_key_name(key)}"
                    else:
                        if isinstance(final_val, str) and final_val.startswith("Custom"):
                            if "]:" in final_val:
                                display_str += " + " + format_input_display(final_val.split("]:")[1])
                            elif ":" in final_val:
                                display_str += " + " + format_input_display(final_val.split(":")[1])
                        else:
                            if final_val == "HOME": display_str += " + Home"
                            elif final_val == "CAPTURE": display_str += " + Capture"
                            elif final_val == "PRTSC": display_str += " + PrtSc"
                            else: display_str += f" + {format_input_display(final_val)}"
                    if in_app_gyro_btn and in_app_gyro_btn.winfo_exists():
                        in_app_gyro_btn.config(text=display_str)
            
            popup.bind("<Destroy>", on_popup_destroy, add="+")
            
            try:
                ax = in_app_gyro_btn.winfo_rootx()
                ay = in_app_gyro_btn.winfo_rooty()
                aw = in_app_gyro_btn.winfo_width()
                ah = in_app_gyro_btn.winfo_height()
                anchor_coords = (ax, ay, aw, ah)
            except Exception:
                anchor_coords = None

            placement_state["anchor_coords"] = anchor_coords
            placement_state["full_size"] = estimate_full_requested_size()
            popup.in_app_full_requested_size = placement_state["full_size"]

            # The live popup is never expanded just to measure placement; otherwise Tk can
            # paint the hidden rows for one frame before they are collapsed.
            refresh_dz_button()
            refresh_damp_button()
            sync_in_app_popup_layout()

            placement_state["ready"] = True
            self._place_popup_within_root_bounds(
                popup,
                in_app_gyro_btn,
                fallback_coords=anchor_coords,
                requested_size=placement_state["full_size"],
            )

            popup.lift()
            
            self.root.after(100, self.bind_in_app_gyro_popup_outside_click)

        def apply_back_button_selection(selected, event=None):
            combo.set(selected)
            if selected != IN_APP_GYRO_LABEL:
                clear_in_app_gyro_settings()
                
            if selected == "Custom":
                combo.pack_forget()
                render_custom_mapping(include_close=True)
                if is_in_app_simul and getattr(self, "in_app_gyro_popup", None) is not None:
                    set_mapping_value("Custom")
                    entry.config(state="normal")
                    entry.delete(0, tk.END)
                    entry.insert(0, "Recording...")
                    entry.config(state="readonly")
                    def start_after_reflow():
                        request_in_app_simul_reflow()
                        self.root.after_idle(lambda: self.start_custom_recording(key, entry, combo, custom_frame, mode_var, mapping_scope))
                    self.root.after_idle(start_after_reflow)
                else:
                    self.start_custom_recording(key, entry, combo, custom_frame, mode_var, mapping_scope)
            elif selected == GYRO_LOCK_LABEL:
                show_token_mapping(GYRO_LOCK_TOKEN, GYRO_LOCK_LABEL, event)
            elif selected == MODE_SHIFT_LABEL:
                show_token_mapping(MODE_SHIFT_TOKEN, MODE_SHIFT_LABEL, event)
            elif selected == IN_APP_GYRO_LABEL:
                mode = mode_var.get() if mode_var.get() in ("Hold", "Tap") else "Hold"
                mode_var.set(mode)
                mode_btn.config(text=mode)
                set_mapping_value(f"Custom[{mode}]:{IN_APP_GYRO_TOKEN}")
                sync_joystick_direction(f"Custom[{mode}]:{IN_APP_GYRO_TOKEN}")
                self.on_setting_changed(event)
                
                in_app_gyro_btn.config(text=IN_APP_GYRO_LABEL)
                combo.pack_forget()
                render_action_button_mapping(in_app_gyro_btn, include_close=True)
                show_in_app_gyro_popup(event)
            elif selected == "Change Profile":
                show_change_profile(event)
            elif selected in MOUSE_CLICK_BACK_BUTTON_TOKENS:
                show_mouse_click_mapping(selected, event, preserve_mode=True)
            else:
                custom_frame.pack_forget()
                cp_frame.pack_forget()
                clear_mouse_click_state(reset_mode=True)
                combo.set(selected)
                pack_combo()
                set_mapping_value(selected)
                sync_joystick_direction(selected)
                self.on_setting_changed(event)

        def on_combo_selected(event):
            apply_back_button_selection(combo.get(), event)

        combo.bind("<<ComboboxSelected>>", on_combo_selected)
        setattr(self, f"{attr_key}_combo", combo)
        setattr(self, f"{attr_key}_container", container)
        setattr(self, f"{attr_key}_custom_frame", custom_frame)
        setattr(self, f"{attr_key}_entry", entry)
        setattr(self, f"{attr_key}_in_app_gyro_btn", in_app_gyro_btn)
        setattr(self, f"{attr_key}_mouse_click_btn", mouse_click_btn)
        setattr(self, f"{attr_key}_mode_btn", mode_btn)
        setattr(self, f"{attr_key}_mode_var", mode_var)
        setattr(self, f"{attr_key}_cp_frame", cp_frame)
        setattr(self, f"{attr_key}_close_btn", close_btn)

    def create_joystick_mapping_widget(self, parent, key, label_text, mapping_scope=None):
        suffix = self._mapping_scope_suffix(mapping_scope)
        attr_key = self._mapping_attr(key, suffix)
        parent_bg = parent.cget("bg") if hasattr(parent, "cget") else background_color
        tk.Label(parent, text=label_text, bg=parent_bg, fg=text_color, font=scale_font(("Arial", 11, "bold"))).pack(side=tk.LEFT, padx=(int(5 * scaling_factor), int(2 * scaling_factor)))
        container = tk.Frame(parent, bg=parent_bg)
        container.pack(side=tk.LEFT, padx=int(2 * scaling_factor))

        combo = ttk.Combobox(container, values=JOYSTICK_OPTIONS, font=scale_font(("Arial", 11, "bold")), state="readonly", width=11, justify="center")
        custom_frame = tk.Frame(container, bg=parent_bg)
        scroll_activation_var = tk.StringVar(value=CONFIG.get_joystick_setting_scoped(key, "scroll_activation", "Hold", mapping_scope))

        def toggle_scroll_activation():
            new_mode = "Tap" if scroll_activation_var.get() == "Hold" else "Hold"
            scroll_activation_var.set(new_mode)
            scroll_mode_btn.config(text=new_mode)
            CONFIG.set_joystick_setting_scoped(key, "scroll_activation", new_mode, mapping_scope)
            CONFIG.save_config()

        scroll_mode_btn = tk.Button(custom_frame, text=scroll_activation_var.get(), bg=button_gray, fg="white", font=scale_font(("Arial", 9, "bold")), bd=0, relief=tk.FLAT, command=toggle_scroll_activation, width=4)
        custom_btn = tk.Button(custom_frame, text="Custom", bg=button_gray, fg="white", font=scale_font(("Arial", 10, "bold")), bd=0, relief=tk.FLAT)
        custom_btn.pack(side=tk.LEFT, fill=tk.Y)

        def open_current_popup():
            mode = CONFIG.get_mapping_setting_scoped(key, "Default", mapping_scope)
            if mode == "Mouse":
                self.root.after(50, lambda: self.open_joystick_mouse_popup(key, custom_btn, mapping_scope))
            elif mode == "Scroll Wheel":
                self.root.after(50, lambda: self.open_joystick_scroll_popup(key, custom_btn, mapping_scope))
            else:
                self.root.after(50, lambda: self.open_joystick_custom_popup(key, custom_btn, mapping_scope))

        custom_btn.config(command=open_current_popup)

        def close_custom():
            scroll_mode_btn.pack_forget()
            custom_frame.pack_forget()
            combo.pack(side=tk.LEFT)
            combo.set("Default")
            CONFIG.set_mapping_setting_scoped(key, "Default", mapping_scope)
            self.on_setting_changed()

        close_btn = tk.Button(custom_frame, text="X", bg="#ff4444", fg="white", font=scale_font(("Arial", 10, "bold")), bd=0, relief=tk.FLAT, command=close_custom)
        close_btn.pack(side=tk.LEFT, padx=(int(2 * scaling_factor), 0), fill=tk.Y)

        def show_current():
            current_val = CONFIG.get_mapping_setting_scoped(key, "Default", mapping_scope)
            if current_val in ("Custom", "Mouse", "Scroll Wheel"):
                combo.pack_forget()
                custom_frame.pack(side=tk.LEFT)
                if current_val == "Scroll Wheel":
                    scroll_activation_var.set(CONFIG.get_joystick_setting_scoped(key, "scroll_activation", "Hold", mapping_scope))
                    scroll_mode_btn.config(text=scroll_activation_var.get())
                    scroll_mode_btn.pack(side=tk.LEFT, padx=(0, int(2 * scaling_factor)), fill=tk.Y, before=custom_btn)
                else:
                    scroll_mode_btn.pack_forget()
                custom_btn.config(text=current_val)
                combo.set(current_val)
            else:
                scroll_mode_btn.pack_forget()
                custom_frame.pack_forget()
                combo.pack(side=tk.LEFT)
                combo.set(current_val)

        def on_combo_selected(event):
            selected = combo.get()
            CONFIG.set_mapping_setting_scoped(key, selected, mapping_scope)
            CONFIG.save_config()
            if selected in ("Custom", "Mouse", "Scroll Wheel"):
                combo.pack_forget()
                custom_frame.pack(side=tk.LEFT)
                if selected == "Scroll Wheel":
                    scroll_activation_var.set(CONFIG.get_joystick_setting_scoped(key, "scroll_activation", "Hold", mapping_scope))
                    scroll_mode_btn.config(text=scroll_activation_var.get())
                    scroll_mode_btn.pack(side=tk.LEFT, padx=(0, int(2 * scaling_factor)), fill=tk.Y, before=custom_btn)
                else:
                    scroll_mode_btn.pack_forget()
                custom_btn.config(text=selected)
                self.root.update_idletasks()
                open_current_popup()
            else:
                self.on_setting_changed(event)

        combo.bind("<<ComboboxSelected>>", on_combo_selected)
        show_current()
        setattr(self, f"{attr_key}_combo", combo)
        setattr(self, f"{attr_key}_custom_frame", custom_frame)
        setattr(self, f"{attr_key}_custom_btn", custom_btn)
        setattr(self, f"{attr_key}_scroll_mode_btn", scroll_mode_btn)
        setattr(self, f"{attr_key}_scroll_activation_var", scroll_activation_var)

    def _event_in_widget(self, widget, event):
        # True if a <ButtonPress> landed inside the given widget (used so an outside-click
        # handler can ignore clicks on the button that owns the popup, letting that button's
        # own command toggle the popup closed instead of close-then-reopen flashing).
        if widget is None or not widget.winfo_exists():
            return False
        wx, wy = widget.winfo_rootx(), widget.winfo_rooty()
        return wx <= event.x_root <= wx + widget.winfo_width() and wy <= event.y_root <= wy + widget.winfo_height()

    def _toggle_joystick_popup(self, anchor_widget):
        # If the joystick popup is already open for this same anchor, close it and report
        # that the caller should abort (so re-clicking the anchor just closes the popup).
        existing = getattr(self, "joystick_custom_popup", None)
        if existing is not None and existing.winfo_exists() and getattr(self, "joystick_custom_popup_anchor", None) is anchor_widget:
            self.close_joystick_custom_popup()
            return True
        return False

    def close_joystick_custom_popup(self):
        self.close_joycon_ir_mouse_popup()
        self._close_joycon_ir_switch_input_popup()
        ir_change_popup = getattr(self, "joycon_ir_change_profile_popup", None)
        if ir_change_popup is not None and ir_change_popup.winfo_exists():
            ir_change_popup.destroy()
        self.joycon_ir_change_profile_popup = None
        commit_deadzone = getattr(self, "joystick_deadzone_popup_commit", None)
        if callable(commit_deadzone):
            try:
                commit_deadzone()
            except Exception:
                pass
        popup = getattr(self, "joystick_custom_popup", None)
        if popup is not None and popup.winfo_exists():
            popup.destroy()
        self.joystick_custom_popup = None
        self.joystick_custom_popup_anchor = None
        self.joystick_deadzone_popup_commit = None
        bind_id = getattr(self, "joystick_custom_popup_bind_id", None)
        if bind_id:
            try:
                self.root.unbind("<ButtonPress>", bind_id)
            except:
                pass
            self.joystick_custom_popup_bind_id = None

    def bind_joystick_custom_popup_outside_click(self):
        popup = getattr(self, "joystick_custom_popup", None)
        if popup is None or not popup.winfo_exists():
            return
        bind_id = getattr(self, "joystick_custom_popup_bind_id", None)
        if bind_id:
            try:
                self.root.unbind("<ButtonPress>", bind_id)
            except:
                pass
            self.joystick_custom_popup_bind_id = None

        def close_if_outside(event):
            current_popup = getattr(self, "joystick_custom_popup", None)
            if current_popup is None or not current_popup.winfo_exists():
                self.close_joystick_custom_popup()
                return
            if self._event_in_widget(current_popup, event):
                return
            # A Back Button Options popup opened from inside this popup is a separate frame
            # on the root, so clicks inside it must not be treated as "outside".
            if self._event_in_widget(getattr(self, "back_button_popup", None), event):
                return
            if self._event_in_widget(getattr(self, "joycon_ir_mouse_popup", None), event):
                return
            if self._event_in_widget(getattr(self, "joycon_ir_switch_input_popup", None), event):
                return
            if self._event_in_widget(getattr(self, "joycon_ir_change_profile_popup", None), event):
                return
            if self._event_in_widget(getattr(self, "in_app_gyro_popup", None), event):
                return
            if self._event_in_widget(getattr(self, "deadzone_input_popup", None), event):
                return
            if self._event_in_widget(getattr(self, "dampening_input_popup", None), event):
                return
            if self._event_in_widget(getattr(self, "joycon_ir_in_app_gyro_bridge", None), event):
                return
            if self._event_in_widget(getattr(self, "joycon_ir_in_app_gyro_anchor", None), event):
                return
            # Leave clicks on the owning anchor to its command (toggles the popup closed).
            if self._event_in_widget(getattr(self, "joystick_custom_popup_anchor", None), event):
                return
            self.close_joystick_custom_popup()

        self.joystick_custom_popup_bind_id = self.root.bind("<ButtonPress>", close_if_outside, add="+")

    # Gamepad numeric-entry hold-to-repeat acceleration (all easily tunable here).
    NUM_REPEAT_BASE_HZ = 5.0          # initial steps/sec while held (pre-accel speed = 0.2s)
    NUM_REPEAT_ACCEL_DELAY = 3.0      # seconds held before acceleration starts
    NUM_REPEAT_ACCEL_INTERVAL = 0.5   # seconds between each speed-up (reaches max ~6.5s in)
    NUM_REPEAT_ACCEL_FACTOR = 1.2     # frequency multiplier per interval
    NUM_REPEAT_MAX_HZ = 20.0          # max steps/sec cap (poll limit ~20/sec)
    NUM_REPEAT_RELEASE_GAP = 0.15     # no-input gap (s) that counts as release -> reset

    def _is_numeric_entry(self, w):
        if not isinstance(w, tk.Entry):
            return False
        try:
            if not w.winfo_exists():
                return False
            t = (w.get() or "").strip()
            if t == "":
                return True
            float(t)
            return True
        except (TypeError, ValueError, tk.TclError):
            return False

    def _nav_numeric_hold_should_step(self, entry, up, now):
        """Return True if the held numeric direction should fire a step this tick, using an
        accelerating repeat: BASE_HZ until ACCEL_DELAY, then x ACCEL_FACTOR every
        ACCEL_INTERVAL, capped at MAX_HZ. A gap > RELEASE_GAP restarts the ramp."""
        token = (id(entry), bool(up))
        prev = getattr(self, "_num_hold", None)  # (token, start, seen, next_fire)
        if prev is None or prev[0] != token or (now - prev[2]) > self.NUM_REPEAT_RELEASE_GAP:
            self._num_hold = (token, now, now, now + 1.0 / max(0.001, self.NUM_REPEAT_BASE_HZ))
            return True  # new hold -> immediate first step
        _tok, start, _seen, next_fire = prev
        if now >= next_fire:
            elapsed = now - start
            rate = self.NUM_REPEAT_BASE_HZ
            if elapsed >= self.NUM_REPEAT_ACCEL_DELAY:
                n = int((elapsed - self.NUM_REPEAT_ACCEL_DELAY) // self.NUM_REPEAT_ACCEL_INTERVAL) + 1
                rate = min(self.NUM_REPEAT_MAX_HZ, self.NUM_REPEAT_BASE_HZ * (self.NUM_REPEAT_ACCEL_FACTOR ** n))
            interval = 1.0 / max(0.001, rate)
            # Accumulate the phase (don't reset to now) so the average rate matches the
            # target even though poll ticks are quantized to 50ms; otherwise sub-poll
            # interval changes get rounded back up to the base rate (no perceived accel).
            nf = next_fire + interval
            if nf < now:  # fell behind (e.g. a poll stall) -> resync, avoid a burst
                nf = now + interval
            self._num_hold = (token, start, now, nf)
            return True
        self._num_hold = (token, start, now, next_fire)  # update "seen" so release is detected
        return False

    def _nav_adjust_numeric_entry(self, entry, up):
        """Gamepad numeric adjust for ANY text Entry holding a number. Steps the value and
        fires the entry's own commit bindings (Return/KeyRelease/textvariable-trace) so it
        clamps / re-displays / saves exactly like typing. Returns True if it adjusted a
        numeric entry, False otherwise (so callers can fall back to spatial navigation).

        Optional per-entry tuning via widget attributes (defaults suit every current entry):
        num_step (default 1), num_min (default 0), num_max (default None), num_integer."""
        if not isinstance(entry, tk.Entry):
            return False
        try:
            txt = (entry.get() or "").strip()
        except Exception:
            return False
        try:
            cur = float(txt) if txt else 0.0
        except (TypeError, ValueError):
            return False  # free-text entry -> not adjustable
        step = float(getattr(entry, "num_step", 1) or 1)
        new = cur + (step if up else -step)
        nmin = getattr(entry, "num_min", 0)
        nmax = getattr(entry, "num_max", None)
        if nmin is not None:
            new = max(float(nmin), new)
        if nmax is not None:
            new = min(float(nmax), new)
        integer = getattr(entry, "num_integer", None)
        if integer is None:
            integer = float(step).is_integer() and ("." not in txt)
        text = str(int(round(new))) if integer else ("%g" % new)
        try:
            varname = entry.cget("textvariable")
        except Exception:
            varname = ""
        if varname:
            try:
                entry.setvar(varname, text)  # single write -> textvariable trace commits
            except Exception:
                varname = ""
        if not varname:
            try:
                entry.delete(0, tk.END)
                entry.insert(0, text)
            except Exception:
                return False
        # Fire the entry's own commit bindings (clamp / normalize display / save). Whichever
        # is bound runs; the other is a harmless no-op.
        for seq in ("<KeyRelease>", "<Return>"):
            try:
                entry.event_generate(seq)
            except Exception:
                pass
        return True

    def _nav_top_dialog(self):
        """Return the top-most open modal dialog Toplevel (found via the Tk grab), or None.
        Only grabbed dialogs qualify, so non-modal transients/tooltips are ignored. These
        are custom Toplevels (custom_messagebox / show_centered_dialog) with navigable
        tk.Buttons; the gamepad nav targets them so dialogs like reset-confirm are usable."""
        try:
            g = self.root.grab_current()
        except Exception:
            g = None
        w = g
        while isinstance(w, tk.Widget) and not isinstance(w, tk.Toplevel):
            try:
                p = w.winfo_parent()
                w = self.root.nametowidget(p) if p else None
            except Exception:
                w = None
        if isinstance(w, tk.Toplevel) and w is not self.root:
            try:
                if w.winfo_exists() and w.winfo_ismapped():
                    return w
            except Exception:
                return None
        return None

    def _nav_top_popup(self):
        """Return (attr, frame, anchor) of the top-most open floating window (popup), or
        (None, None, None) if none is open. Popups are root-child tk.Frames stored in
        self.<name>_popup with the opener in self.<name>_popup_anchor. The top-most is the
        inner-most: a popup whose anchor lives inside another open popup's frame."""
        open_popups = []  # (attr, frame, anchor)
        for attr, w in list(vars(self).items()):
            if not attr.endswith("_popup") or not isinstance(w, tk.Widget):
                continue
            try:
                if not w.winfo_exists():
                    continue
            except Exception:
                continue
            open_popups.append((attr, w, getattr(self, f"{attr}_anchor", None)))
        if not open_popups:
            return (None, None, None)
        frames = {w for _, w, _ in open_popups}
        def anchor_inside_other(anchor, own):
            w, seen = anchor, 0
            while isinstance(w, tk.Widget) and w is not self.root and seen < 60:
                if w in frames and w is not own:
                    return True
                p = w.winfo_parent()
                w = self.root.nametowidget(p) if p else None
                seen += 1
            return False
        target = next((t for t in open_popups if t[2] is not None and anchor_inside_other(t[2], t[1])), None)
        return target or open_popups[0]

    def _nav_close_top_popup(self):
        """Gamepad UI-nav helper: close the top-most open floating window (popup) and
        re-highlight the button that opened it, staying in UI-control mode. Returns True
        if a popup was closed, else False (so the caller exits control mode instead)."""
        attr, frame, anchor = self._nav_top_popup()
        if frame is None:
            return False
        close_fn = getattr(self, f"close_{attr}", None)
        if callable(close_fn):
            try: close_fn()
            except Exception: pass
        else:
            try: frame.destroy()
            except Exception: pass
            setattr(self, attr, None)
        if isinstance(anchor, tk.Widget):
            try:
                if anchor.winfo_exists():
                    self.root.focus_set()
                    self.focus_outline.update(anchor)
            except Exception:
                pass
        return True

    def _toggle_in_app_gyro_popup(self, anchor_widget):
        existing = getattr(self, "in_app_gyro_popup", None)
        if existing is not None and existing.winfo_exists() and getattr(self, "in_app_gyro_popup_anchor", None) is anchor_widget:
            self.close_in_app_gyro_popup()
            return True
        return False

    def close_in_app_gyro_popup(self):
        commit_numeric = getattr(self, "in_app_gyro_popup_commit_numeric", None)
        if commit_numeric:
            try:
                commit_numeric()
            except Exception:
                pass
        # Every control persists at change time. Closing must not perform another
        # bulk transfer or disk save; it only finalizes no-save numeric state.
        self._joycon_ir_in_app_live_ctx = None
        # Hide every placed frame FIRST so they all vanish in a single repaint. These are
        # embedded root-child frames (not Toplevels); destroying them one-by-one repaints
        # the exposed root background in grid-cell strips -> the "bar-like segmented" close.
        # place_forget unmaps them atomically; the subsequent destroy() is then invisible.
        for _attr in ("deadzone_input_popup", "dampening_input_popup",
                      "in_app_gyro_popup", "joycon_ir_in_app_gyro_bridge"):
            _frame = getattr(self, _attr, None)
            if _frame is not None and _frame.winfo_exists():
                try:
                    _frame.place_forget()
                except Exception:
                    pass
        dz_popup = getattr(self, "deadzone_input_popup", None)
        if dz_popup is not None and dz_popup.winfo_exists():
            dz_popup.destroy()
        self.deadzone_input_popup = None
        self.deadzone_input_popup_anchor = None
        damp_popup = getattr(self, "dampening_input_popup", None)
        if damp_popup is not None and damp_popup.winfo_exists():
            damp_popup.destroy()
        self.dampening_input_popup = None
        self.dampening_input_popup_anchor = None
        popup = getattr(self, "in_app_gyro_popup", None)
        if popup is not None and popup.winfo_exists():
            popup.destroy()
        self.in_app_gyro_popup = None
        self.in_app_gyro_popup_anchor = None
        self.in_app_gyro_popup_commit_numeric = None
        bridge = getattr(self, "joycon_ir_in_app_gyro_bridge", None)
        if bridge is not None and bridge.winfo_exists():
            bridge.destroy()
        self.joycon_ir_in_app_gyro_bridge = None
        self.joycon_ir_in_app_gyro_anchor = None
        bind_id = getattr(self, "in_app_gyro_popup_bind_id", None)
        if bind_id:
            try:
                self.root.unbind("<ButtonPress>", bind_id)
            except:
                pass
            self.in_app_gyro_popup_bind_id = None

    def bind_in_app_gyro_popup_outside_click(self):
        popup = getattr(self, "in_app_gyro_popup", None)
        if popup is None or not popup.winfo_exists():
            return
        bind_id = getattr(self, "in_app_gyro_popup_bind_id", None)
        if bind_id:
            try:
                self.root.unbind("<ButtonPress>", bind_id)
            except:
                pass
            self.in_app_gyro_popup_bind_id = None

        def close_if_outside(event):
            current_popup = getattr(self, "in_app_gyro_popup", None)
            if current_popup is None or not current_popup.winfo_exists():
                self.close_in_app_gyro_popup()
                return

            # Auto-close an open Trigger Deadzone / Trigger Dampening sub-menu whenever the
            # click lands outside that sub-menu and outside its own toggle button (the
            # button's command handles clicks on itself). The sub-menus are separate frames
            # on the root, so this covers clicks elsewhere inside the main In-app Gyro popup.
            def _dismiss_sub_menu(attr):
                menu = getattr(self, attr, None)
                if menu is None or not menu.winfo_exists():
                    return
                if self._event_in_widget(menu, event):
                    return
                if self._event_in_widget(getattr(self, attr + "_anchor", None), event):
                    return
                menu.destroy()
                setattr(self, attr, None)
                setattr(self, attr + "_anchor", None)

            _dismiss_sub_menu("deadzone_input_popup")
            _dismiss_sub_menu("dampening_input_popup")

            if self._event_in_widget(current_popup, event):
                return
            if self._event_in_widget(getattr(self, "deadzone_input_popup", None), event):
                return
            if self._event_in_widget(getattr(self, "dampening_input_popup", None), event):
                return
            if self._event_in_widget(getattr(self, "back_button_popup", None), event):
                return
            if self._event_in_widget(getattr(self, "in_app_gyro_popup_anchor", None), event):
                return
            self.close_in_app_gyro_popup()

        self.in_app_gyro_popup_bind_id = self.root.bind("<ButtonPress>", close_if_outside, add="+")

    def _joycon_ir_in_app_mapping_specs(self):
        return (
            ("simul", "joycon_ir_sensor_in_app_gyro_simul", "None"),
            ("deadzone_mode", "joycon_ir_sensor_in_app_gyro_deadzone_mode", []),
            ("deadzone_amount", "joycon_ir_sensor_in_app_gyro_deadzone_amount", 15.0),
            ("deadzone_pause_after_pressed_ms", "joycon_ir_sensor_in_app_gyro_deadzone_pause_after_pressed_ms", 100),
            ("deadzone_pause_after_released_ms", "joycon_ir_sensor_in_app_gyro_deadzone_pause_after_released_ms", 100),
            ("deadzone_effect_after_released_ms", "joycon_ir_sensor_in_app_gyro_deadzone_effect_after_released_ms", 200),
            ("dampening_mode", "joycon_ir_sensor_in_app_gyro_dampening_mode", []),
            ("dampening_amount", "joycon_ir_sensor_in_app_gyro_dampening_amount", 90),
            ("dampening_effect_after_released_ms", "joycon_ir_sensor_in_app_gyro_dampening_effect_after_released_ms", 200),
        )

    def _load_joycon_ir_in_app_mapping_scope(self, side, profile_name=None, category=None, mapping_scope=None):
        for ir_key, mapping_key, default in self._joycon_ir_in_app_mapping_specs():
            value = CONFIG.get_joycon_ir_in_app_gyro_setting_scoped(side, ir_key, default, profile_name, category, mapping_scope)
            CONFIG.set_mapping_setting_scoped(mapping_key, value, None)

    def _save_joycon_ir_in_app_mapping_scope(self, side, profile_name=None, category=None, mapping_scope=None):
        for ir_key, mapping_key, default in self._joycon_ir_in_app_mapping_specs():
            value = CONFIG.get_mapping_setting_scoped(mapping_key, default, None)
            CONFIG.set_joycon_ir_in_app_gyro_setting_scoped(side, ir_key, value, profile_name, category, mapping_scope)

    def _joycon_ir_live_save(self, mapping_key, value):
        """Mirror a transient `joycon_ir_sensor_in_app_gyro_*` mapping write straight into
        the per-side IR store so the change takes effect immediately (the runtime reads the
        IR store, not the mapping keys). Only fires while the Joy-con IR In-app Gyro bridge
        popup is open; the key-prefix guard keeps ordinary Joystick In-app Gyro popups from
        writing into the IR store. Removes the need for the close-time bulk transfer."""
        ctx = getattr(self, "_joycon_ir_in_app_live_ctx", None)
        prefix = "joycon_ir_sensor_in_app_gyro_"
        if not ctx or not isinstance(mapping_key, str) or not mapping_key.startswith(prefix):
            return
        side, profile_name, category, mapping_scope = ctx
        CONFIG.set_joycon_ir_in_app_gyro_setting_scoped(
            side, mapping_key[len(prefix):], value, profile_name, category, mapping_scope)

    def open_joycon_ir_in_app_gyro_settings(self, side, anchor_widget, profile_name=None, category=None, mode="Hold", mapping_scope=None):
        """Open the existing In-app Gyro settings popup for the Joy-con IR sensor.

        The full popup builder currently lives inside create_mapping_widget and is
        keyed by mapping name.  A tiny bridge widget lets the Joy-con Function button
        reuse that builder while storing the settings under joycon_ir_sensor_* keys,
        which the controller path already reads when the IR sensor activates In-app
        Gyro.
        """
        existing = getattr(self, "in_app_gyro_popup", None)
        if (existing is not None and existing.winfo_exists()
                and getattr(self, "joycon_ir_in_app_gyro_anchor", None) is anchor_widget):
            self.close_in_app_gyro_popup()
            return

        self.close_in_app_gyro_popup()
        mode = mode if mode in ("Hold", "Tap") else "Hold"
        self._load_joycon_ir_in_app_mapping_scope(side, profile_name, category, mapping_scope)
        CONFIG.set_mapping_setting_scoped("joycon_ir_sensor", f"Custom[{mode}]:{IN_APP_GYRO_TOKEN}", None)

        self.root.update_idletasks()
        anchor_x = anchor_widget.winfo_rootx() - self.root.winfo_rootx()
        anchor_y = anchor_widget.winfo_rooty() - self.root.winfo_rooty()
        bridge = tk.Frame(self.root, bg=background_color, width=max(1, anchor_widget.winfo_width()),
                          height=max(1, anchor_widget.winfo_height()))
        bridge.place(in_=self.root, x=anchor_x, y=anchor_y,
                     width=max(1, anchor_widget.winfo_width()),
                     height=max(1, anchor_widget.winfo_height()))
        try:
            bridge.lower()
        except Exception:
            pass
        self.joycon_ir_in_app_gyro_bridge = bridge
        self.joycon_ir_in_app_gyro_anchor = anchor_widget

        # Live-save context: every control change in the reused popup mirrors straight into
        # the per-side IR store (via _joycon_ir_live_save), so settings take effect
        # immediately and no bulk transfer is needed on close.
        self._joycon_ir_in_app_live_ctx = (side, profile_name, category, mapping_scope)

        self.create_mapping_widget(
            bridge,
            "joycon_ir_sensor",
            "",
            None,
            compact=True,
            fixed_size=(max(1, anchor_widget.winfo_width()), max(1, anchor_widget.winfo_height())),
        )
        suffix = self._mapping_scope_suffix(None)
        attr_key = self._mapping_attr("joycon_ir_sensor", suffix)
        in_app_button = getattr(self, f"{attr_key}_in_app_gyro_btn", None)
        if in_app_button is not None and in_app_button.winfo_exists():
            in_app_button.invoke()
            popup = getattr(self, "in_app_gyro_popup", None)
            if popup is not None and popup.winfo_exists():
                # No close-time save: each control change already live-saves into the IR
                # store via _joycon_ir_live_save, so closing does no extra (bulk) save.
                self.in_app_gyro_popup_anchor = anchor_widget
                popup.in_app_visible_anchor = anchor_widget
                self._place_popup_within_root_bounds(
                    popup,
                    anchor_widget,
                    requested_size=getattr(popup, "in_app_full_requested_size", None),
                )
                popup.lift()

    def open_joystick_custom_popup(self, key, anchor_widget, mapping_scope=None):
        if self._toggle_joystick_popup(anchor_widget):
            return
        self.close_joystick_custom_popup()

        spacing = int(10 * scaling_factor)
        cell_padx = int(2 * scaling_factor)  # container.pack padx inside create_mapping_widget
        popup = tk.Frame(self.root, bg=background_color, bd=1, relief=tk.SOLID, padx=spacing - cell_padx, pady=spacing)
        self.joystick_custom_popup = popup
        self.joystick_custom_popup_anchor = anchor_widget

        self.root.update_idletasks()
        popup.place(in_=anchor_widget, relx=0, rely=1, x=-int(3 * scaling_factor), y=int(2 * scaling_factor), anchor=tk.NW)
        popup.lift()
        inner = tk.Frame(popup, bg=background_color)
        inner.pack(side=tk.TOP)

        values = CONFIG.get_joystick_custom_scoped(key, mapping_scope)
        # grid layout: col 0=left labels, col 1=left combos, col 2=right labels, col 3=right combos
        layout = [
            ("up",    "Up:",    0, 0),
            ("down",  "Down:",  0, 2),
            ("left",  "Left:",  1, 0),
            ("right", "Right:", 1, 2),
        ]
        row_pady = spacing
        col_gap  = int(8 * scaling_factor)

        for direction, label_text, grow, lcol in layout:
            pady = (0, row_pady) if grow == 0 else 0
            lpadx = (col_gap, cell_padx) if lcol == 2 else (0, cell_padx)
            tk.Label(inner, text=label_text, bg=background_color, fg=text_color,
                     font=scale_font(("Arial", 11, "bold")), anchor=tk.E).grid(
                         row=grow, column=lcol, sticky=tk.E, padx=lpadx, pady=pady)
            cell = tk.Frame(inner, bg=background_color)
            cell.grid(row=grow, column=lcol + 1, sticky=tk.W, pady=pady)
            self.create_mapping_widget(cell, f"{key}_{direction}", "", mapping_scope)

        def enable_outside_click_close():
            if popup.winfo_exists():
                self.bind_joystick_custom_popup_outside_click()

        popup.update_idletasks()
        self.root.after(100, enable_outside_click_close)

    def _create_joystick_option_popup(self, anchor_widget, defer_place=False):
        self.close_joystick_custom_popup()
        spacing = int(10 * scaling_factor)
        parent = anchor_widget.winfo_toplevel() if (anchor_widget and anchor_widget.winfo_exists()) else self.root
        popup = tk.Frame(parent, bg=background_color, bd=1, relief=tk.SOLID, padx=spacing, pady=spacing)
        self.joystick_custom_popup = popup
        self.joystick_custom_popup_anchor = anchor_widget
        if not defer_place:
            parent.update_idletasks()
            popup.place(in_=anchor_widget, relx=0, rely=1, x=-int(3 * scaling_factor), y=int(2 * scaling_factor), anchor=tk.NW)
            popup.lift()
        return popup

    def _place_popup_within_root_bounds(self, popup, anchor_widget, fallback_coords=None, requested_size=None, position_adjust=(0, 0)):
        target_root = anchor_widget.winfo_toplevel() if (anchor_widget and anchor_widget.winfo_exists()) else self.root
        target_root.update_idletasks()
        popup.update_idletasks()

        if anchor_widget and anchor_widget.winfo_exists():
            anchor_x = anchor_widget.winfo_rootx()
            anchor_y = anchor_widget.winfo_rooty()
            anchor_w = anchor_widget.winfo_width()
            anchor_h = anchor_widget.winfo_height()
            anchor_bottom = anchor_y + anchor_h
            use_anchor = True
        elif fallback_coords:
            anchor_x, anchor_y, anchor_w, anchor_h = fallback_coords
            anchor_bottom = anchor_y + anchor_h
            use_anchor = False
        else:
            return

        root_left = target_root.winfo_rootx()
        root_top = target_root.winfo_rooty()
        root_right = root_left + target_root.winfo_width()
        root_bottom = root_top + target_root.winfo_height()
        anchor_right = anchor_x + anchor_w

        if requested_size:
            popup_w, popup_h = requested_size
        else:
            popup_w = popup.winfo_reqwidth()
            popup_h = popup.winfo_reqheight()
        x_offset = int(3 * scaling_factor)
        y_offset = int(2 * scaling_factor)
        x_adjust, y_adjust = position_adjust

        # Prefer the four anchor-relative positions. Left-anchored (NW/SW) opens the popup
        # rightward from the anchor's left edge; right-anchored (NE/SE) opens leftward from
        # its right edge. If the popup is too wide to fit inside the window either way, fall
        # back to sliding it horizontally so it sits flush within the window bounds.
        fits_left_anchored = anchor_x - x_offset + popup_w <= root_right
        fits_right_anchored = anchor_right + x_offset - popup_w >= root_left
        enough_bottom = anchor_bottom + y_offset + popup_h <= root_bottom

        if fits_left_anchored:
            h_mode = "left"
        elif fits_right_anchored:
            h_mode = "right"
        else:
            h_mode = "clamp"

        if h_mode == "clamp":
            # Slide horizontally to stay inside the window while keeping the vertical
            # anchor identical to the normal below/above cases.
            clamped_left = max(root_left, root_right - popup_w)
            if use_anchor:
                x_from_anchor_left = clamped_left - anchor_x
                if enough_bottom:
                    popup.place(in_=anchor_widget, relx=0, rely=1, x=x_from_anchor_left + x_adjust, y=y_offset + y_adjust, anchor=tk.NW)
                else:
                    popup.place(in_=anchor_widget, relx=0, rely=0, x=x_from_anchor_left + x_adjust, y=-y_offset + y_adjust, anchor=tk.SW)
            else:
                x_rel = clamped_left - root_left
                if enough_bottom:
                    popup.place(in_=target_root, x=x_rel + x_adjust, y=anchor_bottom + y_offset - root_top + y_adjust, anchor=tk.NW)
                else:
                    popup.place(in_=target_root, x=x_rel + x_adjust, y=anchor_y - y_offset - root_top + y_adjust, anchor=tk.SW)
        elif use_anchor:
            if h_mode == "left" and enough_bottom:
                popup.place(in_=anchor_widget, relx=0, rely=1, x=-x_offset + x_adjust, y=y_offset + y_adjust, anchor=tk.NW)
            elif h_mode == "right" and enough_bottom:
                popup.place(in_=anchor_widget, relx=1, rely=1, x=x_offset + x_adjust, y=y_offset + y_adjust, anchor=tk.NE)
            elif h_mode == "left" and not enough_bottom:
                popup.place(in_=anchor_widget, relx=0, rely=0, x=-x_offset + x_adjust, y=-y_offset + y_adjust, anchor=tk.SW)
            else:
                popup.place(in_=anchor_widget, relx=1, rely=0, x=x_offset + x_adjust, y=-y_offset + y_adjust, anchor=tk.SE)
        else:
            rx = root_left
            ry = root_top
            if h_mode == "left" and enough_bottom:
                popup.place(in_=target_root, x=anchor_x - rx - x_offset + x_adjust, y=anchor_bottom - ry + y_offset + y_adjust, anchor=tk.NW)
            elif h_mode == "right" and enough_bottom:
                popup.place(in_=target_root, x=anchor_x + anchor_w - rx + x_offset + x_adjust, y=anchor_bottom - ry + y_offset + y_adjust, anchor=tk.NE)
            elif h_mode == "left" and not enough_bottom:
                popup.place(in_=target_root, x=anchor_x - rx - x_offset + x_adjust, y=anchor_y - ry - y_offset + y_adjust, anchor=tk.SW)
            else:
                popup.place(in_=target_root, x=anchor_x + anchor_w - rx + x_offset + x_adjust, y=anchor_y - ry - y_offset + y_adjust, anchor=tk.SE)
        popup.lift()

    def open_change_profile_popup(self, anchor_widget):
        existing = getattr(self, "change_profile_popup", None)
        if existing is not None and existing.winfo_exists() and getattr(self, "change_profile_popup_anchor", None) is anchor_widget:
            existing.destroy()
            return
        if existing is not None and existing.winfo_exists():
            existing.destroy()
            
        try:
            ax = anchor_widget.winfo_rootx()
            ay = anchor_widget.winfo_rooty()
            aw = anchor_widget.winfo_width()
            ah = anchor_widget.winfo_height()
            anchor_coords = (ax, ay, aw, ah)
        except Exception:
            anchor_coords = None
            
        spacing = int(10 * scaling_factor)
        popup = tk.Frame(self.root, bg=background_color, bd=1, relief=tk.SOLID, padx=spacing, pady=spacing)
        self.change_profile_popup = popup
        self.change_profile_popup_anchor = anchor_widget
        
        row = tk.Frame(popup, bg=background_color)
        row.pack(side=tk.TOP, fill=tk.X)
        tk.Label(row, text="Select & Change Profile:", bg=background_color, fg=text_color, font=scale_font(("Arial", 11, "bold"))).pack(side=tk.LEFT, padx=(0, int(5 * scaling_factor)))

        def set_change_profile_mode(val):
            CONFIG.change_profile_mode = val
            CONFIG.save_config()

        switch = ToggleSwitch(row, ["Auto", "Manual"], ["Auto", "Manual"], getattr(CONFIG, "change_profile_mode", "Manual"), set_change_profile_mode, background_color)
        switch.pack(side=tk.LEFT)
        popup.update_idletasks()
        self._place_popup_within_root_bounds(popup, anchor_widget, fallback_coords=anchor_coords)
        
        def enable_outside_click_close():
            if popup.winfo_exists():
                bind_id = getattr(self, "change_profile_popup_bind_id", None)
                if bind_id:
                    try:
                        self.root.unbind("<ButtonPress>", bind_id)
                    except:
                        pass
                def close_if_outside(event):
                    current_popup = getattr(self, "change_profile_popup", None)
                    if current_popup and current_popup.winfo_exists():
                        x, y, w, h = current_popup.winfo_rootx(), current_popup.winfo_rooty(), current_popup.winfo_width(), current_popup.winfo_height()
                        if not (x <= event.x_root <= x + w and y <= event.y_root <= y + h):
                            anchor = getattr(self, "change_profile_popup_anchor", None)
                            if anchor and anchor.winfo_exists():
                                ax, ay, aw, ah = anchor.winfo_rootx(), anchor.winfo_rooty(), anchor.winfo_width(), anchor.winfo_height()
                                if ax <= event.x_root <= ax + aw and ay <= event.y_root <= ay + ah:
                                    return
                            current_popup.destroy()
                            bid = getattr(self, "change_profile_popup_bind_id", None)
                            if bid:
                                try: self.root.unbind("<ButtonPress>", bid)
                                except: pass
                                self.change_profile_popup_bind_id = None
                self.change_profile_popup_bind_id = self.root.bind("<ButtonPress>", close_if_outside, add="+")
        
        self.root.after(100, enable_outside_click_close)

    def close_back_button_popup(self):
        popup = getattr(self, "back_button_popup", None)
        if popup is not None and popup.winfo_exists():
            try:
                popup.place_forget()
                self.root.update_idletasks()
            except Exception:
                pass
            popup.destroy()
        self.back_button_popup = None
        self.back_button_popup_anchor = None
        bind_id = getattr(self, "back_button_popup_bind_id", None)
        if bind_id:
            try:
                self.root.unbind("<ButtonPress>", bind_id)
            except:
                pass
            self.back_button_popup_bind_id = None
        top_bind = getattr(self, "back_button_popup_top_bind_id", None)
        if top_bind:
            top_win, b_id = top_bind
            try:
                if top_win and top_win.winfo_exists():
                    top_win.unbind("<ButtonPress>", b_id)
            except:
                pass
            self.back_button_popup_top_bind_id = None
        if getattr(self, "in_app_gyro_popup", None) and self.in_app_gyro_popup.winfo_exists():
            self.bind_in_app_gyro_popup_outside_click()
        if getattr(self, "joystick_custom_popup", None) and self.joystick_custom_popup.winfo_exists():
            self.bind_joystick_custom_popup_outside_click()

    def bind_back_button_popup_outside_click(self):
        popup = getattr(self, "back_button_popup", None)
        if popup is None or not popup.winfo_exists():
            return
        bind_id = getattr(self, "back_button_popup_bind_id", None)
        if bind_id:
            try:
                self.root.unbind("<ButtonPress>", bind_id)
            except:
                pass
            self.back_button_popup_bind_id = None

        def close_if_outside(event):
            current_popup = getattr(self, "back_button_popup", None)
            if current_popup is None or not current_popup.winfo_exists():
                self.close_back_button_popup()
                return
            px, py = current_popup.winfo_rootx(), current_popup.winfo_rooty()
            pw, ph = current_popup.winfo_width(), current_popup.winfo_height()
            if px <= event.x_root <= px + pw and py <= event.y_root <= py + ph:
                return
            # A click on the owning selector is left for its command to toggle the popup
            # closed, so it isn't closed here and immediately reopened (which would flash).
            anchor = getattr(self, "back_button_popup_anchor", None)
            if anchor is not None and anchor.winfo_exists():
                ax, ay = anchor.winfo_rootx(), anchor.winfo_rooty()
                aw, ah = anchor.winfo_width(), anchor.winfo_height()
                if ax <= event.x_root <= ax + aw and ay <= event.y_root <= ay + ah:
                    return
            self.close_back_button_popup()

        self.back_button_popup_bind_id = self.root.bind("<ButtonPress>", close_if_outside, add="+")
        top = popup.winfo_toplevel()
        if top != self.root:
            bid = top.bind("<ButtonPress>", close_if_outside, add="+")
            self.back_button_popup_top_bind_id = (top, bid)

    def open_back_button_popup(self, selector):
        # Floating, categorized replacement for the Back Button Option dropdown. Opened
        # by a BackButtonSelector; positioned like the Change Profile popup.
        from config import BACK_BUTTON_CATEGORIES, back_button_label

        # Clicking the selector whose popup is already open toggles it closed (the outside-
        # click handler leaves the selector alone so this command does the closing).
        existing = getattr(self, "back_button_popup", None)
        if existing is not None and existing.winfo_exists() and getattr(self, "back_button_popup_anchor", None) is selector:
            self.close_back_button_popup()
            return
        self.close_back_button_popup()

        spacing = int(10 * scaling_factor)
        column_gap = int(8 * scaling_factor)
        btn_gap = int(5 * scaling_factor)

        toplevel = selector.winfo_toplevel() if (selector and selector.winfo_exists()) else self.root
        popup = tk.Frame(toplevel, bg=background_color, bd=1, relief=tk.SOLID, padx=column_gap, pady=spacing)
        self.back_button_popup = popup
        self.back_button_popup_anchor = selector

        header_font = scale_font(("Arial", 9, "bold"))
        btn_font = scale_font(("Arial", 9, "bold"))
        measure = tkFont.Font(font=btn_font)
        display_label = back_button_label

        # All option buttons share one size, wide enough for the longest label.
        max_label_w = 0
        for _title, rows in BACK_BUTTON_CATEGORIES:
            for row in rows:
                for token in row:
                    max_label_w = max(max_label_w, measure.measure(display_label(token)))
        btn_w = max_label_w + int(16 * scaling_factor)
        btn_h = measure.metrics("linespace") + int(10 * scaling_factor)

        current_value = selector.get()

        def choose(token):
            selector.select_value(token)
            self.close_back_button_popup()

        # Category blocks: each defined row becomes a vertical column of buttons. General
        # sits top-left with Switch Input directly beneath it; the remaining small
        # categories share the top row to its right. Inter-category spacing matches the
        # gap between buttons: every cell carries a trailing btn_gap on its right/bottom,
        # so packing the blocks flush leaves exactly one btn_gap between categories.
        cats = dict(BACK_BUTTON_CATEGORIES)
        body = tk.Frame(popup, bg=background_color)
        body.pack(side=tk.TOP, anchor=tk.N)

        def render_category(parent, title):
            cat_frame = tk.Frame(parent, bg=background_color)
            cat_frame.pack(side=tk.LEFT, anchor=tk.N)
            tk.Label(cat_frame, text=title, bg=background_color, fg=text_color,
                     font=header_font, anchor=tk.W).pack(side=tk.TOP, anchor=tk.W, pady=(0, btn_gap))
            block = tk.Frame(cat_frame, bg=background_color)
            block.pack(side=tk.TOP, anchor=tk.W)
            for c_idx, col in enumerate(cats[title]):
                for r_idx, token in enumerate(col):
                    is_sel = (token == current_value)
                    cell = tk.Frame(block, bg=highlight_color if is_sel else background_color,
                                    width=btn_w, height=btn_h)
                    cell.grid(row=r_idx, column=c_idx, padx=(0, btn_gap), pady=(0, btn_gap), sticky="nsew")
                    cell.grid_propagate(False)
                    bd = int(2 * scaling_factor) if is_sel else 0
                    btn = tk.Button(cell, text=display_label(token), font=btn_font,
                                    bg=button_gray, fg="white", relief=tk.FLAT, bd=0,
                                    highlightthickness=0, takefocus=0,
                                    activebackground=highlight_color, activeforeground="white",
                                    command=lambda t=token: choose(t))
                    btn.place(x=bd, y=bd, width=btn_w - 2 * bd, height=btn_h - 2 * bd)

        top_row = tk.Frame(body, bg=background_color)
        top_row.pack(side=tk.TOP, anchor=tk.W)
        for title in ("General", "In-app Gyro", "PS Input", "Windows", "Mouse Click"):
            render_category(top_row, title)

        bottom_row = tk.Frame(body, bg=background_color)
        bottom_row.pack(side=tk.TOP, anchor=tk.W)
        for title in ("Switch Input", "Media Keys"):
            render_category(bottom_row, title)

        # Pre-realize and paint the popup off-screen so every button is already drawn with
        # its gray background before the popup appears at the anchor. Mapping the buttons
        # directly at their final spot is what makes them flash their default (white)
        # background for one frame; painting off-screen first avoids that.
        popup.place(in_=toplevel, x=-10000, y=-10000)
        popup.update_idletasks()
        self._place_popup_within_root_bounds(popup, selector)
        self.root.after(100, self.bind_back_button_popup_outside_click)

    def open_joystick_mouse_popup(self, key, anchor_widget, mapping_scope=None):
        if self._toggle_joystick_popup(anchor_widget):
            return
        popup = self._create_joystick_option_popup(anchor_widget)
        row = tk.Frame(popup, bg=background_color)
        row.pack(side=tk.TOP, fill=tk.X)
        tk.Label(row, text="Sensitivity:", bg=background_color, fg=text_color, font=scale_font(("Arial", 11, "bold"))).pack(side=tk.LEFT, padx=(0, int(5 * scaling_factor)))
        def update_mouse_sensitivity(val):
            CONFIG.set_joystick_setting_scoped(key, "mouse_sensitivity", float(val), mapping_scope)
            if mapping_scope == "in_app_gyro_mode_mappings" and hasattr(self, "stick_scale"):
                self.stick_scale.set(float(val))
            CONFIG.save_config()
        scale = tk.Scale(
            row,
            from_=0,
            to=10,
            resolution=0.2,
            orient=tk.HORIZONTAL,
            length=int(120 * scaling_factor),
            bg=background_color,
            fg=text_color,
            troughcolor=button_gray,
            activebackground=highlight_color,
            highlightthickness=0,
            bd=0,
            sliderrelief=tk.FLAT,
            sliderlength=int(15 * scaling_factor),
            width=int(15 * scaling_factor),
            font=scale_font(("Arial", 11, "bold")),
            command=update_mouse_sensitivity
        )
        scale.set(float(CONFIG.get_joystick_setting_scoped(key, "mouse_sensitivity", 5.0, mapping_scope)))
        scale.pack(side=tk.LEFT)
        popup.update_idletasks()
        self.root.after(100, self.bind_joystick_custom_popup_outside_click)

    def open_joystick_scroll_popup(self, key, anchor_widget, mapping_scope=None):
        if self._toggle_joystick_popup(anchor_widget):
            return
        popup = self._create_joystick_option_popup(anchor_widget)
        row = tk.Frame(popup, bg=background_color)
        row.pack(side=tk.TOP, fill=tk.X)
        tk.Label(row, text="Scroll Wheel Mode:", bg=background_color, fg=text_color, font=scale_font(("Arial", 11, "bold"))).pack(side=tk.LEFT, padx=(0, int(5 * scaling_factor)))

        mode = CONFIG.get_joystick_setting_scoped(key, "scroll_mode", "Up/Down", mapping_scope)
        switch = ToggleSwitch(
            row,
            ["Up/Down", "Up/Down/Left/Right"],
            ["Up/Down", "Up/Down/Left/Right"],
            mode,
            lambda val: (CONFIG.set_joystick_setting_scoped(key, "scroll_mode", val, mapping_scope), CONFIG.save_config()),
            background_color,
            widths=[10, 20]
        )
        switch.pack(side=tk.LEFT)
        popup.update_idletasks()
        self.root.after(100, self.bind_joystick_custom_popup_outside_click)

    def _format_profile_combo_input(self, value):
        if not value:
            return "None"
        display = value
        if display.startswith("Custom[Tap]:"):
            display = display[12:]
        elif display.startswith("Custom[Hold]:"):
            display = display[13:]
        elif display.startswith("Custom:"):
            display = display[7:]
        return format_input_display(display)

    def _get_game_icon(self, exe_key, size=(18, 18), exe_path=None):
        if not exe_key:
            return None
        exe_key = str(exe_key).lower().strip()
        path = exe_path
        if not path or not os.path.exists(path):
            if hasattr(CONFIG, "game_mappings") and exe_key in CONFIG.game_mappings:
                game_data = CONFIG.game_mappings[exe_key]
                if isinstance(game_data, dict):
                    path = game_data.get("path")
        if not path or not os.path.exists(path):
            if hasattr(self, "last_foreground_app_path") and self.last_foreground_app_path:
                if os.path.basename(self.last_foreground_app_path).lower() == exe_key:
                    path = self.last_foreground_app_path
        if path and os.path.exists(path):
            return get_file_icon(path, size)
        return None

    def _set_profile_button_text(self):
        if not hasattr(self, "profile_button") or not self.profile_button.winfo_exists():
            return
        active_ctx = CONFIG.get_active_game_context()
        if active_ctx:
            known = CONFIG.get_known_games()
            display_name = known.get(active_ctx) or getattr(CONFIG, "active_game_name", None) or active_ctx
            self.profile_button.config(text=str(display_name))
        else:
            self.profile_button.config(text="Default")

    def start_back_button_assign(self, key, selector_btn):
        self.cancel_back_button_assign()
        self.waiting_for_back_button_assign = (key, selector_btn)
        try:
            selector_btn.config(text="Waiting...", fg=highlight_color)
        except Exception:
            pass

        def _timeout():
            if getattr(self, "waiting_for_back_button_assign", None) == (key, selector_btn):
                self.cancel_back_button_assign()

        self._back_button_assign_timer = self.root.after(5000, _timeout)

        def _on_escape(e=None):
            if getattr(self, "waiting_for_back_button_assign", None) == (key, selector_btn):
                self.cancel_back_button_assign()
                return "break"

        try:
            if getattr(self, "_back_button_esc_bind_id", None):
                self.root.unbind("<Escape>", self._back_button_esc_bind_id)
        except Exception:
            pass
        self._back_button_esc_bind_id = self.root.bind("<Escape>", _on_escape, add="+")
        try:
            top = selector_btn.winfo_toplevel()
            if top != self.root:
                top.bind("<Escape>", _on_escape, add="+")
        except Exception:
            pass

    def cancel_back_button_assign(self):
        if hasattr(self, "_back_button_assign_timer") and self._back_button_assign_timer:
            try:
                self.root.after_cancel(self._back_button_assign_timer)
            except Exception:
                pass
            self._back_button_assign_timer = None

        if getattr(self, "_back_button_esc_bind_id", None):
            try:
                self.root.unbind("<Escape>", self._back_button_esc_bind_id)
            except Exception:
                pass
            self._back_button_esc_bind_id = None

        if getattr(self, "waiting_for_back_button_assign", None):
            key, btn = self.waiting_for_back_button_assign
            try:
                btn.set(btn.get())
                btn.config(fg="white")
            except Exception:
                pass
            self.waiting_for_back_button_assign = None

    def on_select_game_profile(self, exe_key):
        CONFIG.selected_game_preset = None
        if exe_key:
            CONFIG.active_game_exe = exe_key
            known = CONFIG.get_known_games()
            CONFIG.active_game_name = known.get(exe_key)
            if not hasattr(self, "recent_game_order"):
                self.recent_game_order = []
            exe_lower = exe_key.lower().strip()
            if exe_lower in self.recent_game_order:
                self.recent_game_order.remove(exe_lower)
            self.recent_game_order.append(exe_lower)
        else:
            CONFIG.active_game_exe = None
            CONFIG.active_game_name = None
        CONFIG._bump_settings_generation()
        self._set_profile_button_text()
        self._refresh_mapping_comboboxes()
        self.close_profile_popup()

    def on_browse_and_add_game(self):
        self.close_profile_popup()
        app_path = self.choose_app_path()
        if not app_path:
            return
        exe_name = os.path.basename(app_path).lower().strip()
        display_name = get_exe_display_name(app_path)
        CONFIG.set_game_mapping(exe_name, "gl", "None", display_name=display_name)
        CONFIG.set_game_mapping(exe_name, "gr", "None")
        if exe_name in CONFIG.game_mappings:
            CONFIG.game_mappings[exe_name]["path"] = app_path
            CONFIG.save_config()
        self.on_select_game_profile(exe_name)

    def on_save_back_button_profile(self):
        self.on_setting_changed()
        CONFIG.save_config()
        if hasattr(self, "back_button_save_btn") and self.back_button_save_btn.winfo_exists():
            orig_bg = self.back_button_save_btn.cget("bg")
            self.back_button_save_btn.config(bg="#1e3d2f", text="Saved!")
            self.root.after(800, lambda: self.back_button_save_btn.config(bg=orig_bg, text="Save") if self.back_button_save_btn.winfo_exists() else None)

    def on_reset_back_button_profile(self):
        active_ctx = CONFIG.get_active_game_context()
        if active_ctx:
            CONFIG.set_game_mapping(active_ctx, "gl", "None")
            CONFIG.set_game_mapping(active_ctx, "gr", "None")
        else:
            CONFIG.gl_mapping = "None"
            CONFIG.gr_mapping = "None"
        CONFIG.save_config()
        self._refresh_mapping_comboboxes()
        if hasattr(self, "back_button_reset_btn") and self.back_button_reset_btn.winfo_exists():
            orig_bg = self.back_button_reset_btn.cget("bg")
            self.back_button_reset_btn.config(bg="#552222", text="Reset!")
            self.root.after(800, lambda: self.back_button_reset_btn.config(bg=orig_bg, text="Reset") if self.back_button_reset_btn.winfo_exists() else None)

    def on_popup_profile_selected(self, profile_name, name_frame, name_btn, frame_w, frame_h):
        # Selecting a profile in the popup: 1) move the highlight border onto the new
        # profile, 2) close the popup cleanly, 3) then run the actual profile switch.
        if not profile_name or profile_name == getattr(CONFIG, "active_profile", ""):
            self.close_profile_popup()
            return
        border = 2
        try:
            name_frame.config(bg=highlight_color)
            name_btn.place_configure(
                x=border, y=border,
                width=max(1, frame_w - border * 2),
                height=max(1, frame_h - border * 2),
            )
            self.root.update_idletasks()
        except Exception:
            pass

        def _close_popup():
            # Close exactly like the outside-click path: just close and return to the
            # event loop so the OS paints the clean close with nothing competing.
            self.close_profile_popup()
            # Run the (heavier) switch only after the close has had a full cycle to
            # paint; running it in the same idle tick made the close tear down in
            # stripes as the switch's repaints interleaved.
            self.root.after(50, lambda: self.switch_to_profile(profile_name))

        # Brief delay so the new highlight is actually visible before the popup closes.
        self.root.after(50, _close_popup)

    def close_profile_popup(self):
        popup = getattr(self, "profile_popup", None)
        if popup is not None and popup.winfo_exists():
            try:
                popup.destroy()
            except Exception:
                pass
        self.profile_popup = None
        self.profile_popup_anchor = None
        bind_id = getattr(self, "profile_popup_bind_id", None)
        if bind_id:
            try:
                self.root.unbind_all("<ButtonPress>")
            except Exception:
                pass
            self.profile_popup_bind_id = None

    def bind_profile_popup_outside_click(self):
        popup = getattr(self, "profile_popup", None)
        if popup is None or not popup.winfo_exists():
            return

        bind_id = getattr(self, "profile_popup_bind_id", None)
        if bind_id:
            try:
                self.root.unbind_all("<ButtonPress>")
            except Exception:
                pass
            self.profile_popup_bind_id = None

        def close_if_outside(event):
            current_popup = getattr(self, "profile_popup", None)
            if current_popup is None or not current_popup.winfo_exists():
                self.close_profile_popup()
                return
            try:
                ex, ey = event.x_root, event.y_root
                px, py = current_popup.winfo_rootx(), current_popup.winfo_rooty()
                pw, ph = current_popup.winfo_width(), current_popup.winfo_height()
                if px <= ex <= px + pw and py <= ey <= py + ph:
                    return

                for btn_name in ("profile_button", "profile_actions_arrow_btn"):
                    btn = getattr(self, btn_name, None)
                    if btn and btn.winfo_exists():
                        bx, by = btn.winfo_rootx(), btn.winfo_rooty()
                        bw, bh = btn.winfo_width(), btn.winfo_height()
                        if bx <= ex <= bx + bw and by <= ey <= by + bh:
                            return
            except Exception:
                pass
            self.close_profile_popup()

        self.profile_popup_bind_id = self.root.bind_all("<ButtonPress>", close_if_outside, add="+")

    def _record_profile_combo_input(self, button, clear_button, save_callback, unique_profile=None):
        import utils
        button.config(text="Recording...")
        button.focus_set()
        if clear_button:
            if not clear_button.winfo_ismapped():
                clear_button.pack(side=tk.LEFT, padx=(int(2 * scaling_factor), 0), fill=tk.Y)

        pressed_keys = set()
        recorded_seq = []
        self.recording_controllers = True
        self.recorded_controller_buttons = set()
        self.controller_buttons_pressed = False
        self.waiting_for_controller_release = True

        def cleanup_recording_binds():
            self.recording_controllers = False
            if getattr(utils, "profile_combo_record_callback", None) is handle_controller_profile_combo:
                utils.profile_combo_record_callback = None
            self.root.unbind("<KeyPress>")
            self.root.unbind("<KeyRelease>")
            self.root.unbind("<ButtonPress>")
            self.root.unbind("<ButtonRelease>")
            self.root.unbind("<MouseWheel>")
            self.root.unbind("<FocusOut>")

        def restore_clear_button(value_exists):
            if clear_button:
                default_command = getattr(clear_button, "profile_combo_clear_command", None)
                if default_command:
                    clear_button.config(command=default_command)
                if value_exists:
                    if not clear_button.winfo_ismapped():
                        clear_button.pack(side=tk.LEFT, padx=(int(2 * scaling_factor), 0), fill=tk.Y)
                else:
                    clear_button.pack_forget()

        def cancel_recording():
            if not getattr(self, 'recording_controllers', False):
                return
            cleanup_recording_binds()
            save_callback("")
            button.config(text="None")
            restore_clear_button(False)
            CONFIG.save_config()
            self.root.after(100, self.bind_profile_popup_outside_click)

        if clear_button:
            clear_button.config(command=cancel_recording)

        def set_recorded_value(seq):
            final_seq = []
            for k in seq:
                if k in ("VK_CONTROL", "VK_CONTROL_L", "VK_CONTROL_R", "VK_LCONTROL", "VK_RCONTROL"):
                    nk = "VK_CONTROL"
                elif k in ("VK_SHIFT", "VK_SHIFT_L", "VK_SHIFT_R", "VK_LSHIFT", "VK_RSHIFT"):
                    nk = "VK_SHIFT"
                elif k in ("VK_MENU", "VK_ALT", "VK_ALT_L", "VK_ALT_R", "VK_LMENU", "VK_RMENU"):
                    nk = "VK_MENU"
                elif k in ("VK_WIN", "VK_LWIN", "VK_RWIN", "VK_WIN_L", "VK_WIN_R"):
                    nk = "VK_LWIN"
                else:
                    nk = k
                if nk not in final_seq:
                    final_seq.append(nk)
            value = "+".join(final_seq)
            if unique_profile and value:
                for profile_name, profile_data in CONFIG.profiles.items():
                    if profile_name != unique_profile and profile_data.get("profile_switching_combo", "") == value:
                        self.root.after(100, lambda: self._record_profile_combo_input(button, clear_button, save_callback, unique_profile))
                        return
            save_callback(value)
            button.config(text=self._format_profile_combo_input(value))
            if clear_button:
                if value:
                    restore_clear_button(True)
                else:
                    restore_clear_button(False)

        def end_recording():
            cleanup_recording_binds()
            if not recorded_seq:
                save_callback("")
                button.config(text="None")
                restore_clear_button(False)
            else:
                set_recorded_value(recorded_seq)
            CONFIG.save_config()
            self.root.after(100, self.bind_profile_popup_outside_click)

        def check_release():
            if not pressed_keys and not getattr(self, 'controller_buttons_pressed', False):
                if not recorded_seq and not self.recorded_controller_buttons:
                    return
                end_recording()

        def handle_controller_profile_combo(states):
            if not getattr(self, 'recording_controllers', False):
                return
            any_pressed = any(bool(v) for v in states.values())
            if getattr(self, 'waiting_for_controller_release', False):
                if not any_pressed:
                    self.waiting_for_controller_release = False
                return
            if any_pressed:
                for btn_name, pressed in states.items():
                    if pressed:
                        token = f"BTN_{btn_name}"
                        self.recorded_controller_buttons.add(token)
                        if token not in recorded_seq:
                            recorded_seq.append(token)
            self.controller_buttons_pressed = any_pressed
            if not any_pressed and self.recorded_controller_buttons and not pressed_keys:
                end_recording()

        def on_key_press(e):
            if self.recorded_controller_buttons:
                return "break"
            vk = e.keysym.upper()
            pressed_keys.add(f"VK_{vk}")
            if f"VK_{vk}" not in recorded_seq:
                recorded_seq.append(f"VK_{vk}")
            return "break"

        def on_key_release(e):
            vk = e.keysym.upper()
            pressed_keys.discard(f"VK_{vk}")
            check_release()
            return "break"

        def on_mouse_press(e):
            # Clicking the [X] button during recording cancels and reverts to None
            # instead of recording the click as a mouse-button input.
            if clear_button is not None and e.widget is clear_button:
                cancel_recording()
                return "break"
            if self.recorded_controller_buttons:
                return "break"
            btn = f"MB_{e.num}"
            pressed_keys.add(btn)
            if btn not in recorded_seq:
                recorded_seq.append(btn)
            return "break"

        def on_mouse_release(e):
            btn = f"MB_{e.num}"
            pressed_keys.discard(btn)
            check_release()
            return "break"

        def on_mouse_wheel(e):
            if self.recorded_controller_buttons:
                return "break"
            dir_str = "UP" if e.delta > 0 else "DOWN"
            if f"MW_{dir_str}" not in recorded_seq:
                recorded_seq.append(f"MW_{dir_str}")
            self.root.after(100, check_release)
            return "break"

        self.root.bind("<KeyPress>", on_key_press)
        self.root.bind("<KeyRelease>", on_key_release)
        self.root.bind("<ButtonPress>", on_mouse_press)
        self.root.bind("<ButtonRelease>", on_mouse_release)
        self.root.bind("<MouseWheel>", on_mouse_wheel)
        utils.profile_combo_record_callback = handle_controller_profile_combo

        def on_focus_out(e):
            if e.widget == self.root and getattr(self, 'recording_controllers', False):
                try:
                    if self.root.focus_get():
                        return
                except:
                    pass
                if not self.recorded_controller_buttons:
                    for vk in range(8, 255):
                        try:
                            if ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000:
                                if 65 <= vk <= 90 or 48 <= vk <= 57:
                                    token = f"VK_{chr(vk)}"
                                    if token not in recorded_seq:
                                        recorded_seq.append(token)
                        except:
                            pass
                end_recording()
        self.root.bind("<FocusOut>", on_focus_out)

        def poll_controller():
            if not getattr(self, 'recording_controllers', False):
                return
            any_pressed = False
            reverse_map = {v: k for k, v in SWITCH_BUTTONS.items() if k not in ["Capture", "PS_C_Click"]}
            for vc in getattr(self, 'current_controllers', []):
                if vc is None:
                    continue
                for c in vc.controllers:
                    raw = getattr(c, 'raw_buttons', 0)
                    if raw:
                        any_pressed = True
                        if not getattr(self, 'waiting_for_controller_release', False) and not self.recorded_controller_buttons:
                            for bit, btn_name in reverse_map.items():
                                if raw & bit:
                                    token = f"BTN_{btn_name}"
                                    self.recorded_controller_buttons.add(token)
                                    if token not in recorded_seq:
                                        recorded_seq.append(token)
            if getattr(self, 'waiting_for_controller_release', False):
                if not any_pressed:
                    self.waiting_for_controller_release = False
            else:
                self.controller_buttons_pressed = any_pressed
                if not any_pressed and self.recorded_controller_buttons and not pressed_keys:
                    end_recording()
                    return
            self.root.after(50, poll_controller)

        poll_controller()

    def _create_profile_combo_input_widget(self, parent, value_getter, value_setter, unique_profile=None, fill_width=False):
        frame = tk.Frame(parent, bg=background_color)
        btn = tk.Button(
            frame,
            text=self._format_profile_combo_input(value_getter()),
            font=scale_font(("Arial", 10, "bold")),
            bg=button_gray,
            fg="white",
            relief=tk.FLAT,
            bd=0,
            width=12 if not fill_width else 1,
            anchor=tk.CENTER
        )
        btn.pack(side=tk.LEFT, fill=tk.BOTH if fill_width else tk.Y, expand=fill_width)

        def save_value(value):
            value_setter(value)
            btn.config(text=self._format_profile_combo_input(value))

        def clear_value():
            save_value("")
            clear_btn.pack_forget()
            CONFIG.save_config()

        clear_btn = tk.Button(frame, text="X", bg="#ff4444", fg="white", font=scale_font(("Arial", 10, "bold")), bd=0, relief=tk.FLAT, command=clear_value)
        clear_btn.profile_combo_clear_command = clear_value
        if value_getter():
            clear_btn.pack(side=tk.LEFT, padx=(int(2 * scaling_factor), 0), fill=tk.Y)

        btn.config(command=lambda: self._record_profile_combo_input(btn, clear_btn, save_value, unique_profile))
        return frame

    def get_running_non_blocked_processes(self):
        """Scans interactive desktop applications (Apps section like Task Manager / Task View)
        filtering out background services, invisible processes, and AUTOBLOCK entries."""
        from config import AUTOBLOCK_NON_GAMING_PROCESSES, is_blocked_process
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        known_saved = set(CONFIG.get_known_games().keys())
        results = {}

        my_pid = os.getpid()
        my_exe = os.path.basename(sys.executable).lower().strip()

        def enum_cb(hwnd, lparam):
            if not user32.IsWindowVisible(hwnd):
                return True

            # Exclude own application root and dialogs
            if getattr(self, "root", None) and hwnd == self.root.winfo_id():
                return True
            if getattr(self, "top_hwnd", None) and hwnd == self.top_hwnd:
                return True
            for sub_win in [getattr(self, "add_game_dialog", None), getattr(self, "settings_window", None), getattr(self, "profile_popup", None), getattr(self, "edit_profiles_dialog", None)]:
                if sub_win and sub_win.winfo_exists() and hwnd == sub_win.winfo_id():
                    return True

            # Length of window title
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True

            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value.strip()
            title_lower = title.lower()
            if not title or title in ("Program Manager", "Windows Input Experience", "Windows Shell Experience Host", "Settings"):
                return True

            # Filter out titles matching Switch2ProConnect, Switch2Connect or Wabbajack
            if ("switch2proconnect" in title_lower or "switch 2 pro connect" in title_lower
                    or "switch2connect" in title_lower or "switch 2 connect" in title_lower or "wabbajack" in title_lower):
                return True

            # Window styles: exclude tool windows unless explicitly marked as app window
            GWL_EXSTYLE = -20
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_APPWINDOW = 0x00040000
            if (ex_style & WS_EX_TOOLWINDOW) and not (ex_style & WS_EX_APPWINDOW):
                return True

            # Exclude owned popups/dialogs (unless marked WS_EX_APPWINDOW)
            owner = user32.GetWindow(hwnd, 4) # GW_OWNER = 4
            if owner and not (ex_style & WS_EX_APPWINDOW):
                return True

            # Window rect size check (must be an actual desktop window with area)
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            if (rect.right - rect.left <= 10) or (rect.bottom - rect.top <= 10):
                return True

            # Exclude DWM cloaked windows (e.g. suspended UWP apps or off-screen virtual desktop frames)
            cloaked = wintypes.DWORD(0)
            DWMWA_CLOAKED = 14
            ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
            if cloaked.value != 0:
                return True

            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value <= 4 or pid.value == my_pid:
                return True

            h_proc = kernel32.OpenProcess(0x1000, False, pid.value)
            if not h_proc:
                return True

            path_buf = ctypes.create_unicode_buffer(512)
            sz = wintypes.DWORD(512)
            full_path = ""
            if kernel32.QueryFullProcessImageNameW(h_proc, 0, path_buf, ctypes.byref(sz)):
                full_path = path_buf.value
            kernel32.CloseHandle(h_proc)

            if not full_path:
                return True

            exe = os.path.basename(full_path).lower().strip()
            if (is_blocked_process(exe)
                    or "wabbajack" in exe
                    or "switch2proconnect" in exe
                    or "switch2connect" in exe
                    or exe == my_exe
                    or exe in known_saved
                    or exe in results):
                return True

            dname = get_exe_display_name(full_path) or title or exe[:-4]
            results[exe] = {
                "exe": exe,
                "path": full_path,
                "hwnd": hwnd,
                "display_name": dname,
                "title": title,
                "z_order": len(results)
            }
            return True

        cb = WNDENUMPROC(enum_cb)
        try:
            desktop = user32.OpenDesktopW("default", 0, False, 0x01FF)
            if desktop:
                user32.EnumDesktopWindows(desktop, cb, 0)
                user32.CloseDesktop(desktop)
            else:
                user32.EnumWindows(cb, 0)
        except Exception as e:
            logger.debug(f"Window enumeration failed, falling back: {e}")
            try:
                user32.EnumWindows(cb, 0)
            except Exception:
                pass

        # Sort candidate games: last active / foreground external app always at the very top,
        # followed by exact most-recently-focused Z-order
        last_exe = getattr(self, "last_external_app_exe", None)
        def sort_key(item):
            if last_exe and item["exe"] == last_exe:
                return (0, 0)
            return (1, item.get("z_order", 9999))

        return sorted(list(results.values()), key=sort_key)

    def open_add_game_dialog(self):
        """Opens a true secondary window to add a game profile from running processes or browse."""
        existing = getattr(self, "add_game_dialog", None)
        if existing is not None and existing.winfo_exists():
            try:
                existing.lift()
                existing.focus_set()
            except Exception:
                pass
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Add Game Profile")
        dialog.configure(bg=background_color)
        dialog.transient(self.root)
        dialog.resizable(False, False)
        self.add_game_dialog = dialog

        self._apply_dark_title_bar(dialog)

        spacing = int(12 * scaling_factor)
        container = tk.Frame(dialog, bg=background_color, padx=spacing, pady=spacing)
        container.pack(fill=tk.BOTH, expand=True)

        header_lbl = tk.Label(
            container,
            text="Detected Running Games",
            font=scale_font(("Arial", 11, "bold")),
            fg=text_color,
            bg=background_color,
        )
        header_lbl.pack(side=tk.TOP, pady=(0, int(8 * scaling_factor)))

        # Bottom manual browse button
        browse_frame = tk.Frame(container, bg=background_color)
        browse_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(int(8 * scaling_factor), 0))

        browse_btn = make_rounded_button(
            browse_frame,
            text="+ Browse for Game (.exe)...",
            width=280,
            height=32,
            radius=6,
            command=lambda: self._browse_and_add_game_dialog(dialog),
            font=scale_font(("Arial", 9, "bold"))
        )
        browse_btn.pack(fill=tk.X)

        candidates = self.get_running_non_blocked_processes()
        self._add_dialog_icons = []
        n_candidates = len(candidates)

        row_height = int(36 * scaling_factor)
        row_pady = int(2 * scaling_factor)
        item_h = row_height + (2 * row_pady)

        if n_candidates == 0:
            canvas_h = 0
        elif n_candidates <= 5:
            canvas_h = n_candidates * item_h
        else:
            # Show 5 items fully and peek into the 6th so the user knows there is more to scroll
            canvas_h = int(5.25 * item_h)

        # Canvas for scrollable running games
        canvas = tk.Canvas(container, bg=background_color, highlightthickness=0, height=canvas_h)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollable = tk.Frame(canvas, bg=background_color)
        canvas_win = canvas.create_window((0, 0), window=scrollable, anchor="nw")

        def update_scroll(event=None):
            bbox = canvas.bbox("all")
            if not bbox:
                return
            canvas.configure(scrollregion=bbox)
            canvas_w = canvas.winfo_width()
            if canvas_w > 1:
                canvas.itemconfig(canvas_win, width=canvas_w)
            content_h = bbox[3] - bbox[1]
            if content_h > canvas_h and canvas_h > 20:
                if not scrollbar.winfo_ismapped():
                    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            else:
                if scrollbar.winfo_ismapped():
                    scrollbar.pack_forget()
                canvas.yview_moveto(0)

        canvas.configure(yscrollcommand=scrollbar.set)
        if n_candidates > 0:
            canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
            scrollable.bind("<Configure>", update_scroll)
            canvas.bind("<Configure>", update_scroll)

        def on_mousewheel(e):
            bbox = canvas.bbox("all")
            if not bbox:
                return "break"
            content_h = bbox[3] - bbox[1]
            if content_h <= canvas_h:
                return "break"
            canvas.yview_scroll(-1 if e.delta > 0 else 1, "units")
            return "break"
        dialog.bind("<MouseWheel>", on_mousewheel)

        for item in candidates:
            exe = item["exe"]
            dname = item["display_name"]
            path = item["path"]
            hwnd = item.get("hwnd")

            r_frame = tk.Frame(scrollable, bg=button_gray, height=row_height)
            r_frame.pack(fill=tk.X, pady=row_pady)
            r_frame.pack_propagate(False)

            icon = get_window_taskbar_icon(
                hwnd=hwnd,
                file_path=path,
                size=(int(22 * scaling_factor), int(22 * scaling_factor))
            )
            if icon:
                self._add_dialog_icons.append(icon)

            plus_btn = make_rounded_button(
                r_frame,
                text="+",
                width=28,
                height=26,
                radius=5,
                bg_color="#2e7d32",
                hover_color="#388e3c",
                press_color="#1b5e20",
                fg="white",
                font=scale_font(("Arial", 11, "bold")),
                command=lambda e=exe, n=dname, p=path: self._add_game_and_select(e, n, p, dialog)
            )
            plus_btn.pack(side=tk.RIGHT, padx=int(4 * scaling_factor))
            Tooltip(plus_btn, lambda: "Add profile for this game")

            if icon:
                icon_lbl = tk.Label(r_frame, image=icon, bg=button_gray, cursor="hand2")
                icon_lbl.pack(side=tk.LEFT, padx=(int(8 * scaling_factor), int(4 * scaling_factor)))
                icon_lbl.bind("<Button-1>", lambda e, ex=exe, n=dname, p=path: self._add_game_and_select(ex, n, p, dialog))

            lbl = tk.Label(
                r_frame,
                text=dname,
                font=scale_font(("Arial", 9, "bold")),
                bg=button_gray,
                fg="white",
                anchor=tk.W,
                cursor="hand2",
                padx=int(4 * scaling_factor) if not icon else 0,
            )
            lbl.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            lbl.bind("<Button-1>", lambda e, ex=exe, n=dname, p=path: self._add_game_and_select(ex, n, p, dialog))
            r_frame.bind("<Button-1>", lambda e, ex=exe, n=dname, p=path: self._add_game_and_select(ex, n, p, dialog))
            Tooltip(lbl, lambda n=dname, e=exe: f"{n} ({e})")

        dialog.bind("<Escape>", lambda e: dialog.destroy())
        dialog.update_idletasks()

        content_w = int(350 * scaling_factor)
        base_h = header_lbl.winfo_reqheight() + browse_frame.winfo_reqheight() + (spacing * 2) + int(16 * scaling_factor)
        content_h = base_h + canvas_h
        self.center_window_on_root(dialog, content_w, content_h)

    def _add_game_and_select(self, exe, name, path, dialog=None):
        CONFIG.set_game_mapping(exe, "gl", "None", display_name=name)
        CONFIG.set_game_mapping(exe, "gr", "None")
        if not hasattr(CONFIG, "game_mappings") or not isinstance(CONFIG.game_mappings, dict):
            CONFIG.game_mappings = {}
        if exe in CONFIG.game_mappings and isinstance(CONFIG.game_mappings[exe], dict):
            CONFIG.game_mappings[exe]["path"] = path
        CONFIG.save_config()
        self.on_select_game_profile(exe)
        if not hasattr(self, "recent_game_order"):
            self.recent_game_order = []
        exe_lower = exe.lower().strip()
        if exe_lower in self.recent_game_order:
            self.recent_game_order.remove(exe_lower)
        self.recent_game_order.append(exe_lower)
        if dialog and dialog.winfo_exists():
            dialog.destroy()

    def _browse_and_add_game_dialog(self, dialog):
        from config import is_blocked_process
        app_path = self.choose_app_path()
        if not app_path:
            return
        exe_name = os.path.basename(app_path).lower().strip()
        if is_blocked_process(exe_name):
            self.show_centered_message("Invalid Selection", f"'{exe_name}' is an excluded application or utility and cannot be added as a game profile.", parent_window=dialog)
            return
        display_name = get_exe_display_name(app_path) or exe_name[:-4]
        self._add_game_and_select(exe_name, display_name, app_path, dialog)

    def open_edit_profiles_dialog(self):
        """Opens a secondary window showing all profiles and what buttons they have assigned."""
        existing = getattr(self, "edit_profiles_dialog", None)
        if existing is not None and existing.winfo_exists():
            try:
                existing.lift()
                return
            except Exception:
                pass

        # Determine owner window (Settings window if open and visible, otherwise root)
        owner = self.settings_window if (hasattr(self, "settings_window") and self.settings_window is not None and self.settings_window.winfo_exists() and self.settings_window.winfo_viewable()) else self.root

        dialog = tk.Toplevel(owner)
        dialog.withdraw()
        self.edit_profiles_dialog = dialog
        dialog._owner = owner
        dialog.title("Edit Profiles")
        dialog.resizable(False, False)
        dialog.configure(bg=background_color)
        dialog.transient(owner)
        self._apply_dark_title_bar(dialog)

        def close_dialog():
            self.cancel_back_button_assign()
            try:
                dialog.grab_release()
            except Exception:
                pass
            dialog.destroy()
            self.edit_profiles_dialog = None
            if owner and owner != self.root and hasattr(owner, "winfo_exists") and owner.winfo_exists():
                try:
                    owner.lift()
                    owner.focus_set()
                except Exception:
                    pass

        self._populate_edit_profiles_dialog(dialog, owner=owner)
        dialog.protocol("WM_DELETE_WINDOW", close_dialog)

    def _populate_edit_profiles_dialog(self, dialog, owner=None):
        for w in dialog.winfo_children():
            w.destroy()

        if owner is None:
            owner = getattr(dialog, "_owner", None) or (self.settings_window if (hasattr(self, "settings_window") and self.settings_window is not None and self.settings_window.winfo_exists() and self.settings_window.winfo_viewable()) else self.root)

        self._edit_dialog_icons = []
        self._edit_dialog_cards = []
        scaling_factor = getattr(self, "scaling_factor", 1.0)
        row_height = int(66 * scaling_factor)
        card_w = int(486 * scaling_factor)
        card_r = int(16 * scaling_factor)
        canvas_height = int(300 * scaling_factor)
        pill_w = int(76 * scaling_factor)
        pill_h = int(28 * scaling_factor)
        del_size = 20

        header_frame = tk.Frame(dialog, bg=background_color)
        header_frame.pack(side=tk.TOP, fill=tk.X, padx=int(14 * scaling_factor), pady=(int(12 * scaling_factor), int(6 * scaling_factor)))
        tk.Label(
            header_frame,
            text="Profiles & Button Assignments",
            font=scale_font(("Arial", 11, "bold")),
            bg=background_color,
            fg=text_color,
        ).pack(anchor="w")

        # Bottom Finish button packed first to ensure it's pinned to bottom
        finish_frame = tk.Frame(dialog, bg=background_color)
        finish_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(int(8 * scaling_factor), int(10 * scaling_factor)))

        def close_dialog():
            self.cancel_back_button_assign()
            dialog.destroy()

        finish_btn = make_rounded_button(
            finish_frame,
            text="Finish",
            width=110,
            height=28,
            radius=5,
            bg_color=button_gray,
            hover_color=highlight_color,
            press_color=highlight_color,
            fg="white",
            font=scale_font(("Arial", 9, "bold")),
            command=close_dialog
        )
        finish_btn.pack(anchor="center")

        container = tk.Frame(dialog, bg=background_color)
        container.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=int(14 * scaling_factor))

        canvas = tk.Canvas(container, bg=background_color, highlightthickness=0, height=canvas_height)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollable = tk.Frame(canvas, bg=background_color)
        canvas_win = canvas.create_window((0, 0), window=scrollable, anchor="nw")

        def update_scroll(event=None):
            bbox = canvas.bbox("all")
            if not bbox:
                return
            canvas.configure(scrollregion=bbox)
            canvas_w = canvas.winfo_width()
            if canvas_w > 1:
                canvas.itemconfig(canvas_win, width=canvas_w)
            canvas_h = canvas.winfo_height()
            content_h = scrollable.winfo_reqheight()
            if content_h > canvas_h and canvas_h > 20:
                if not scrollbar.winfo_ismapped():
                    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            else:
                if scrollbar.winfo_ismapped():
                    scrollbar.pack_forget()

        def _on_mousewheel(e):
            if scrollable.winfo_reqheight() <= canvas.winfo_height():
                return "break"
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
            return "break"

        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollable.bind("<Configure>", update_scroll)
        canvas.bind("<Configure>", update_scroll)
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        card_img = get_rounded_rect_image(card_w, row_height, card_r, bg="#3A3A3A", parent_bg=background_color, parent=dialog)
        self._edit_dialog_cards.append(card_img)

        def make_profile_row(parent, profile_key, display_name, icon=None, is_default=False, exe_key=None):
            # Pill-shaped rounded card canvas
            card_cv = tk.Canvas(parent, width=card_w, height=row_height, bg=background_color, highlightthickness=0)
            card_cv.pack(pady=int(4 * scaling_factor))
            card_cv.create_image(0, 0, image=card_img, anchor="nw")

            # Left section: icon + profile name
            left_frame = tk.Frame(card_cv, bg="#3A3A3A")
            if icon:
                self._edit_dialog_icons.append(icon)
                icon_lbl = tk.Label(left_frame, image=icon, bg="#3A3A3A")
                icon_lbl.pack(side=tk.LEFT, padx=(0, int(8 * scaling_factor)))

            name_lbl = tk.Label(
                left_frame,
                text=display_name,
                font=scale_font(("Arial", 11 if is_default else 10, "bold")),
                bg="#3A3A3A",
                fg="white",
                anchor="w",
            )
            name_lbl.pack(side=tk.LEFT)
            card_cv.create_window(int(22 * scaling_factor), row_height // 2, window=left_frame, anchor="w")

            # Right section: GL column, GR column, and Red X
            right_frame = tk.Frame(card_cv, bg="#3A3A3A")

            current_gl = CONFIG.get_game_mapping(profile_key, "gl")
            current_gr = CONFIG.get_game_mapping(profile_key, "gr")

            # GL column
            gl_col = tk.Frame(right_frame, bg="#3A3A3A")
            gl_col.pack(side=tk.LEFT, padx=(0, int(10 * scaling_factor)))
            tk.Label(gl_col, text="GL", font=scale_font(("Arial", 9, "bold")), bg="#3A3A3A", fg="white").pack(side=tk.TOP, pady=(0, int(3 * scaling_factor)))
            gl_selector = ProfileBackButtonSelector(gl_col, self, profile_key, "gl", current_gl, fixed_size=(pill_w, pill_h))
            gl_selector.pack(side=tk.TOP)

            # GR column
            gr_col = tk.Frame(right_frame, bg="#3A3A3A")
            gr_col.pack(side=tk.LEFT, padx=(0, int(14 * scaling_factor)))
            tk.Label(gr_col, text="GR", font=scale_font(("Arial", 9, "bold")), bg="#3A3A3A", fg="white").pack(side=tk.TOP, pady=(0, int(3 * scaling_factor)))
            gr_selector = ProfileBackButtonSelector(gr_col, self, profile_key, "gr", current_gr, fixed_size=(pill_w, pill_h))
            gr_selector.pack(side=tk.TOP)

            # End container: Red X button
            end_col = tk.Frame(right_frame, bg="#3A3A3A")
            end_col.pack(side=tk.LEFT, padx=(0, int(4 * scaling_factor)))
            # Spacer label matching the top "GL"/"GR" label height so the X aligns with the pills
            tk.Frame(end_col, bg="#3A3A3A", height=int(16 * scaling_factor), width=int(del_size * scaling_factor)).pack(side=tk.TOP)

            if is_default:
                def on_reset_default():
                    msg = "Are you sure you want to reset the Default profile button assignments back to unassigned?"
                    if self.ask_centered_yes_no("Reset Default Profile", msg, parent_window=dialog):
                        CONFIG.set_game_mapping(None, "gl", "Default")
                        CONFIG.set_game_mapping(None, "gr", "Default")
                        CONFIG.save_config()
                        if hasattr(self, "_refresh_mapping_comboboxes"):
                            self._refresh_mapping_comboboxes()
                        self._populate_edit_profiles_dialog(dialog)

                del_btn = make_rounded_button(
                    end_col,
                    text="✕",
                    width=del_size,
                    height=del_size,
                    radius=del_size // 2,
                    bg_color="#552222",
                    hover_color="#c62828",
                    press_color="#8b0000",
                    fg="white",
                    parent_bg="#3A3A3A",
                    font=scale_font(("Arial", 8, "bold")),
                    command=on_reset_default
                )
                del_btn.pack(side=tk.TOP)
                Tooltip(del_btn, lambda: "Reset Default button assignments")
            else:
                del_btn = make_rounded_button(
                    end_col,
                    text="✕",
                    width=del_size,
                    height=del_size,
                    radius=del_size // 2,
                    bg_color="#552222",
                    hover_color="#c62828",
                    press_color="#8b0000",
                    fg="white",
                    parent_bg="#3A3A3A",
                    font=scale_font(("Arial", 8, "bold")),
                    command=lambda e=exe_key, dn=display_name: self.confirm_delete_game_profile(e, dn, dialog)
                )
                del_btn.pack(side=tk.TOP)
                Tooltip(del_btn, lambda: "Delete this game profile")

            card_cv.create_window(card_w - int(16 * scaling_factor), row_height // 2, window=right_frame, anchor="e")

        # 1. Default (Neutral) Profile
        make_profile_row(scrollable, profile_key=None, display_name="Default", is_default=True)

        # 2. Saved Game Profiles
        saved_games = getattr(CONFIG, "game_mappings", {})

        if isinstance(saved_games, dict) and saved_games:
            for exe, data in sorted(saved_games.items(), key=lambda x: str(x[1].get("display_name") or x[0]).lower()):
                dname = data.get("display_name") or exe
                path = data.get("path")
                icon = self._get_game_icon(exe, size=(int(22 * scaling_factor), int(22 * scaling_factor)), exe_path=path)
                make_profile_row(scrollable, profile_key=exe, display_name=dname, icon=icon, is_default=False, exe_key=exe)

        dialog.bind("<Escape>", lambda e: close_dialog())
        dialog.protocol("WM_DELETE_WINDOW", close_dialog)
        dialog.update_idletasks()
        content_w = int(520 * scaling_factor)
        needed_h = scrollable.winfo_reqheight() + finish_frame.winfo_reqheight() + header_frame.winfo_reqheight() + int(36 * scaling_factor)
        content_h = min(int(490 * scaling_factor), max(int(220 * scaling_factor), needed_h))
        self.center_window_on_root(dialog, content_w, content_h, owner=owner)
        dialog.deiconify()
        dialog.lift(owner)
        dialog.focus_force()
        dialog.grab_set()
        try:
            dialog.attributes("-topmost", True)
            dialog.after(100, lambda: dialog.winfo_exists() and dialog.attributes("-topmost", False))
        except Exception:
            pass

    def confirm_delete_game_profile(self, exe, display_name, dialog=None):
        """Shows a confirmation warning dialog before deleting a game profile."""
        msg = f"Are you sure you want to delete the profile for \"{display_name}\"?\n\nThis will permanently delete this profile and its custom button assignments."
        if self.ask_centered_yes_no("Delete Profile", msg, parent_window=dialog):
            self.delete_game_profile(exe, dialog)

    def delete_game_profile(self, exe, dialog=None):
        """Deletes a game profile mapping and refreshes active state."""
        exe_lower = exe.lower().strip()
        if hasattr(CONFIG, "game_mappings") and isinstance(CONFIG.game_mappings, dict):
            if exe in CONFIG.game_mappings:
                del CONFIG.game_mappings[exe]
            elif exe_lower in CONFIG.game_mappings:
                del CONFIG.game_mappings[exe_lower]
        CONFIG.save_config()

        if hasattr(self, "recent_game_order") and exe_lower in self.recent_game_order:
            self.recent_game_order.remove(exe_lower)

        if getattr(CONFIG, "active_game_exe", None) in (exe, exe_lower):
            alive_games = [g for g in getattr(self, "recent_game_order", []) if self.is_game_process_running(g)]
            self.recent_game_order = alive_games
            if self.recent_game_order:
                CONFIG.active_game_exe = self.recent_game_order[-1]
                CONFIG.active_game_name = CONFIG.game_mappings.get(CONFIG.active_game_exe, {}).get("display_name") or CONFIG.active_game_exe
            else:
                CONFIG.active_game_exe = None
                CONFIG.active_game_name = None
            CONFIG._bump_settings_generation()
            self._set_profile_button_text()
            self._refresh_mapping_comboboxes()

        if dialog is not None and dialog.winfo_exists():
            self._populate_edit_profiles_dialog(dialog)

    def init_settings_panel(self):
        parent = getattr(self, "scroll_content_frame", self.root)
        self.settings_outer_frame = tk.Frame(parent, bg=background_color)
        self.settings_outer_frame.pack()

        self.settings_frame = tk.Frame(self.settings_outer_frame, bg=background_color)
        self.settings_frame.pack()

        def center_row(pady=None):
            row = tk.Frame(self.settings_frame, bg=background_color)
            if pady is None:
                pady = int(4 * scaling_factor)
            row.pack(side=tk.TOP, pady=pady)
            return row

        # Row 1: Profile Selector + Add Game Button (Total span: 172 + 8 + 34 = 214px, aligning with Row 2)
        row_profile = center_row(pady=(0, int(18 * scaling_factor)))
        self.profile_button = make_rounded_button(
            row_profile,
            text=CONFIG.active_profile,
            width=172,
            height=34,
            radius=6,
            command=None,
            bg_color="#3A3A3A",
            hover_color="#3A3A3A",
            press_color="#3A3A3A",
            parent_bg=background_color,
            cursor="arrow",
            font=scale_font(("Arial", 11, "bold"))
        )
        self.profile_button.pack(side=tk.LEFT, padx=(0, int(8 * scaling_factor)))
        Tooltip(self.profile_button, lambda b=self.profile_button: f"Active Profile: {b.cget('text')}")

        self.profile_actions_arrow_btn = make_rounded_button(
            row_profile,
            text="+",
            width=34,
            height=34,
            radius=6,
            bg_color="#2E7D32",
            hover_color="#388E3C",
            press_color="#1B5E20",
            parent_bg=background_color,
            command=self.open_add_game_dialog,
            font=scale_font(("Arial", 14, "bold"))
        )
        self.profile_actions_arrow_btn.pack(side=tk.LEFT)
        Tooltip(self.profile_actions_arrow_btn, lambda: "Add Game Profile")

        # Row 2: GL and GR Back Buttons (Side-by-side columns with labels above buttons)
        row_pro_combos = center_row(pady=(0, int(6 * scaling_factor)))

        # GL Column
        col_gl = tk.Frame(row_pro_combos, bg=background_color)
        col_gl.pack(side=tk.LEFT, padx=(0, int(12 * scaling_factor)))
        tk.Label(
            col_gl,
            text="GL",
            bg=background_color,
            fg=text_color,
            font=scale_font(("Arial", 11, "bold")),
            anchor=tk.CENTER
        ).pack(side=tk.TOP, pady=(0, int(4 * scaling_factor)))
        self.create_mapping_widget(
            col_gl, "gl", label_text=None,
            fixed_size=(int(95 * scaling_factor), int(32 * scaling_factor))
        )

        # GR Column
        col_gr = tk.Frame(row_pro_combos, bg=background_color)
        col_gr.pack(side=tk.LEFT, padx=(int(12 * scaling_factor), 0))
        tk.Label(
            col_gr,
            text="GR",
            bg=background_color,
            fg=text_color,
            font=scale_font(("Arial", 11, "bold")),
            anchor=tk.CENTER
        ).pack(side=tk.TOP, pady=(0, int(4 * scaling_factor)))
        self.create_mapping_widget(
            col_gr, "gr", label_text=None,
            fixed_size=(int(95 * scaling_factor), int(32 * scaling_factor))
        )

        # Row 3: GL/GR Reset Button
        row_reset = center_row(pady=(int(8 * scaling_factor), 0))
        self.gl_gr_reset_btn = make_rounded_button(
            row_reset,
            text="Reset",
            width=214,
            height=30,
            radius=8,
            bg_color=button_gray,
            hover_color="#5A5A5A",
            press_color="#3A3A3A",
            parent_bg=background_color,
            command=self.on_reset_gl_gr_clicked,
            font=scale_font(("Arial", 10, "bold"))
        )
        self.gl_gr_reset_btn.pack(side=tk.TOP)

    def on_reset_gl_gr_clicked(self):
        confirmed = self.custom_messagebox(
            "Reset Mappings",
            "Are you sure you want to reset GL and GR mappings?",
            type="yesno",
            confirm_text="Yes",
            cancel_text="No"
        )
        if confirmed:
            active_scope = "in_app_gyro_mode_mappings" if getattr(self, "settings_active_tab", None) == "in_app_gyro_mode_mapping" else None
            active_ctx = CONFIG.get_active_game_context()
            if active_ctx:
                CONFIG.set_game_mapping(active_ctx, "gl", "None")
                CONFIG.set_game_mapping(active_ctx, "gr", "None")
            else:
                CONFIG.set_mapping_setting_scoped("gl", "None", active_scope)
                CONFIG.set_mapping_setting_scoped("gr", "None", active_scope)
            CONFIG.save_config()
            self._refresh_mapping_comboboxes()
            self.on_setting_changed()
            if hasattr(self, "gl_gr_reset_btn") and self.gl_gr_reset_btn.winfo_exists():
                orig_text = self.gl_gr_reset_btn.cget("text")
                self.gl_gr_reset_btn.config(text="Reset!")
                self.root.after(800, lambda: self.gl_gr_reset_btn.config(text=orig_text) if (hasattr(self, "gl_gr_reset_btn") and self.gl_gr_reset_btn.winfo_exists()) else None)

    def on_use_default_controller_mapping_for_gyro_mode(self):
        CONFIG.copy_controller_mapping_to_in_app_gyro_mode_mapping()
        CONFIG.save_config()
        self._refresh_mapping_comboboxes()

    def on_reset_in_app_gyro_mode_mapping(self):
        CONFIG.reset_in_app_gyro_mode_mapping()
        mapping_keys = [
            "home", "capt", "c", "plus", "minus", "a", "b", "x", "y",
            "up", "down", "left", "right", "zl", "l", "zr", "r",
            "l_stk", "r_stk", "gl", "gr", "sll", "srl", "slr", "srr",
            "gc_l_click", "gc_r_click"
        ]
        for key in mapping_keys:
            CONFIG.set_mapping_setting_scoped(f"{key}_in_app_gyro_simul", "None", None)
        CONFIG.save_config()
        self._refresh_mapping_comboboxes()

    def show_settings_tab(self, tab_id=None):
        pass

    def open_audio_haptics_settings(self, anchor_widget):
        if self._toggle_joystick_popup(anchor_widget):
            return
        popup = self._create_joystick_option_popup(anchor_widget, defer_place=True)

        content_frame = tk.Frame(popup, bg=background_color)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=int(5 * scaling_factor), pady=int(5 * scaling_factor))

        def update_audio_haptics(val):
            CONFIG.audio_haptics_enabled = val
            CONFIG.save_config()
            if hasattr(self, 'current_controllers'):
                for vc in getattr(self, 'current_controllers', []):
                    if vc is not None and getattr(vc, 'mode', '') == "PS5" and getattr(CONFIG, "driver_type", "WinUHid") == "USBIP":
                        try:
                            vc._setup_vg_controller()
                        except Exception as e:
                            pass

        def update_adaptive_triggers(val):
            CONFIG.adaptive_triggers_enabled = val
            CONFIG.save_config()

        # Use a shared, natural-width grid column instead of Label.width.
        # Label.width is character-cell based and created asymmetric visual
        # padding with proportional bold fonts.
        audio_label = tk.Label(content_frame, text="Audio Haptics:", font=scale_font(("Arial", 11, "bold")), bg=background_color, fg=text_color, anchor="e")
        audio_label.grid(row=0, column=0, sticky=tk.E, padx=(0, int(5 * scaling_factor)), pady=(0, int(15 * scaling_factor)))
        ToggleSwitch(content_frame, ["On", "Off"], [True, False], getattr(CONFIG, "audio_haptics_enabled", True), update_audio_haptics, background_color).grid(row=0, column=1, sticky=tk.W, pady=(0, int(15 * scaling_factor)))

        adaptive_label = tk.Label(content_frame, text="Adaptive Triggers:", font=scale_font(("Arial", 11, "bold")), bg=background_color, fg=text_color, anchor="e")
        adaptive_label.grid(row=1, column=0, sticky=tk.E, padx=(0, int(5 * scaling_factor)))
        ToggleSwitch(content_frame, ["On", "Off"], [True, False], getattr(CONFIG, "adaptive_triggers_enabled", True), update_adaptive_triggers, background_color).grid(row=1, column=1, sticky=tk.W)

        popup.update_idletasks()
        self._place_popup_within_root_bounds(popup, anchor_widget)
        self.root.after(100, self.bind_joystick_custom_popup_outside_click)

    def open_impulse_trigger_settings(self, anchor_widget):
        if self._toggle_joystick_popup(anchor_widget):
            return
        popup = self._create_joystick_option_popup(anchor_widget, defer_place=True)

        content_frame = tk.Frame(popup, bg=background_color)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=int(5 * scaling_factor), pady=int(5 * scaling_factor))

        def clear_active_xbox_impulses():
            for vc in VIRTUAL_CONTROLLERS:
                if (vc is not None and getattr(vc, 'mode', '') == "Xbox One"
                        and getattr(vc, 'driver_type', '') == "WinUHid"):
                    try:
                        vc.clear_xbox_impulse_triggers()
                    except Exception:
                        pass

        def update_impulse_enabled(value):
            CONFIG.impulse_trigger_enabled = value
            CONFIG.save_config()
            if not value:
                clear_active_xbox_impulses()

        def update_dynamic_frequency(value):
            CONFIG.impulse_trigger_dynamic_frequency = value
            CONFIG.save_config()
            refresh_frequency_visibility()

        def update_fixed_frequency(value):
            CONFIG.impulse_trigger_frequency = int(float(value))
            CONFIG.save_config()

        def update_impulse_strength(value):
            CONFIG.impulse_trigger_strength = int(float(value))
            CONFIG.save_config()

        def refresh_frequency_visibility():
            if getattr(CONFIG, 'impulse_trigger_dynamic_frequency', True):
                frequency_label.grid_remove()
                frequency_scale.grid_remove()
            else:
                frequency_label.grid()
                frequency_scale.grid()
            popup.update_idletasks()
            self._place_popup_within_root_bounds(popup, anchor_widget)

        # A shared two-column grid gives a natural-width title column: its
        # longest label starts at the real popup padding, while all titles
        # still share a right edge and all controls share a left edge.
        impulse_label = tk.Label(content_frame, text="Impulse Trigger:", font=scale_font(("Arial", 11, "bold")), bg=background_color, fg=text_color, anchor="e")
        impulse_label.grid(row=0, column=0, sticky=tk.E, padx=(0, int(5 * scaling_factor)), pady=(0, int(15 * scaling_factor)))
        ToggleSwitch(content_frame, ["On", "Off"], [True, False], getattr(CONFIG, 'impulse_trigger_enabled', True), update_impulse_enabled, background_color).grid(row=0, column=1, sticky=tk.W, pady=(0, int(15 * scaling_factor)))

        dynamic_label = tk.Label(content_frame, text="Dynamic Frequency:", font=scale_font(("Arial", 11, "bold")), bg=background_color, fg=text_color, anchor="e")
        dynamic_label.grid(row=1, column=0, sticky=tk.E, padx=(0, int(5 * scaling_factor)))
        ToggleSwitch(content_frame, ["On", "Off"], [True, False], getattr(CONFIG, 'impulse_trigger_dynamic_frequency', True), update_dynamic_frequency, background_color).grid(row=1, column=1, sticky=tk.W)

        strength_label = tk.Label(content_frame, text="Strength:", font=scale_font(("Arial", 11, "bold")), bg=background_color, fg=text_color, anchor="e")
        strength_label.grid(row=2, column=0, sticky=tk.E, padx=(0, int(5 * scaling_factor)), pady=(int(15 * scaling_factor), 0))
        strength_scale = tk.Scale(content_frame, from_=1, to=10, resolution=1, orient=tk.HORIZONTAL, length=int(120 * scaling_factor), bg=background_color, fg=text_color, troughcolor=button_gray, activebackground=highlight_color, highlightthickness=0, bd=0, sliderrelief=tk.FLAT, sliderlength=int(15 * scaling_factor), width=int(15 * scaling_factor), font=scale_font(("Arial", 11, "bold")), command=update_impulse_strength)
        strength_scale.set(getattr(CONFIG, 'impulse_trigger_strength', 5))
        strength_scale.grid(row=2, column=1, sticky=tk.W, pady=(int(15 * scaling_factor), 0))

        frequency_label = tk.Label(content_frame, text="Frequency:", font=scale_font(("Arial", 11, "bold")), bg=background_color, fg=text_color, anchor="e")
        frequency_label.grid(row=3, column=0, sticky=tk.E, padx=(0, int(5 * scaling_factor)), pady=(int(15 * scaling_factor), 0))
        frequency_scale = tk.Scale(content_frame, from_=1, to=10, resolution=1, orient=tk.HORIZONTAL, length=int(120 * scaling_factor), bg=background_color, fg=text_color, troughcolor=button_gray, activebackground=highlight_color, highlightthickness=0, bd=0, sliderrelief=tk.FLAT, sliderlength=int(15 * scaling_factor), width=int(15 * scaling_factor), font=scale_font(("Arial", 11, "bold")), command=update_fixed_frequency)
        frequency_scale.set(getattr(CONFIG, 'impulse_trigger_frequency', 10))
        frequency_scale.grid(row=3, column=1, sticky=tk.W, pady=(int(15 * scaling_factor), 0))

        refresh_frequency_visibility()
        self.root.after(100, self.bind_joystick_custom_popup_outside_click)

    def open_joystick_deadzone_settings(self, anchor_widget):
        """Open the Profile × Emu Mode physical joystick deadzone editor."""
        if self._toggle_joystick_popup(anchor_widget):
            return
        popup = self._create_joystick_option_popup(anchor_widget, defer_place=True)
        profile_name = CONFIG.active_profile
        category = CONFIG.get_current_category()
        content = tk.Frame(popup, bg=background_color)
        content.pack(fill=tk.BOTH, expand=True, padx=int(5 * scaling_factor), pady=int(5 * scaling_factor))
        syncing = {"value": False, "dirty": False}
        rows = {}
        # Keep the link icon at the exact former Entry-based size. Sliders are taller
        # than the old controls and must not enlarge this button.
        icon_images_by_height = {}
        popup.joystick_deadzone_icon_images = icon_images_by_height

        icon_size_reference = tk.Entry(
            content, width=3, font=scale_font(("Arial", 11, "bold")), bd=0)
        previous_entry_height = icon_size_reference.winfo_reqheight()
        icon_size_reference.destroy()

        def get_icon_images(entry_height):
            icon_height = max(1, int(round(entry_height * 0.8)))
            if icon_height not in icon_images_by_height:
                icon_images_by_height[icon_height] = {}
                for icon_name in ("link", "unlink"):
                    image = Image.open(get_resource(f"images/{icon_name}.png"))
                    image = image.resize((icon_height, icon_height), Image.Resampling.LANCZOS)
                    icon_images_by_height[icon_height][icon_name] = ImageTk.PhotoImage(image)
            return icon_images_by_height[icon_height]

        def commit_row(family, side=None):
            row = rows[family]
            selected = ("left", "right") if side is None else (side,)
            changed = False
            for current_side in selected:
                CONFIG.set_joystick_deadzone_percent(
                    family, current_side, row[current_side].get(), profile_name, category)
                changed = True
            values = CONFIG.get_joystick_deadzone_settings(profile_name, category)[family]
            syncing["value"] = True
            row["left"].set(values["left"])
            row["right"].set(values["right"])
            syncing["value"] = False
            syncing["dirty"] = syncing["dirty"] or changed
            return changed

        def sync_from_slider(family, side, value):
            if syncing["value"]:
                return
            CONFIG.set_joystick_deadzone_percent(family, side, int(float(value)), profile_name, category)
            values = CONFIG.get_joystick_deadzone_settings(profile_name, category)[family]
            if values["linked"]:
                other = "right" if side == "left" else "left"
                syncing["value"] = True
                rows[family][other].set(values[other])
                syncing["value"] = False
            syncing["dirty"] = True

        def toggle_link(family):
            values = CONFIG.get_joystick_deadzone_settings(profile_name, category)[family]
            values = CONFIG.set_joystick_deadzone_linked(family, not values["linked"], profile_name, category)
            syncing["value"] = True
            rows[family]["left"].set(values["left"])
            rows[family]["right"].set(values["right"])
            syncing["value"] = False
            rows[family]["refresh_link"]()
            syncing["dirty"] = True

        def commit_all():
            for family in rows:
                commit_row(family)
            if syncing["dirty"]:
                CONFIG.save_config()
                syncing["dirty"] = False

        for grid_row, (family, title) in enumerate((
                ("pro_controller", "Pro Controller:"),
                ("joycon", "Joy-Con:"),
                ("nso_gamecube_controller", "NSO GameCube Controller:"))):
            row_pady = (0, int(10 * scaling_factor)) if grid_row < 2 else (0, 0)
            values = CONFIG.get_joystick_deadzone_settings(profile_name, category)[family]
            tk.Label(content, text=title, bg=background_color, fg=text_color,
                     font=scale_font(("Arial", 11, "bold")), anchor=tk.E).grid(
                         row=grid_row, column=0, sticky=tk.E,
                         padx=(0, int(8 * scaling_factor)), pady=row_pady)
            tk.Label(content, text="L Joystick:", bg=background_color, fg=text_color,
                     font=scale_font(("Arial", 11, "bold")), anchor=tk.E).grid(row=grid_row, column=1, sticky=tk.E)
            left_var, right_var = tk.IntVar(value=values["left"]), tk.IntVar(value=values["right"])
            rows[family] = {"left": left_var, "right": right_var}
            slider_options = {
                "from_": 0, "to": 100, "resolution": 1, "orient": tk.HORIZONTAL,
                "length": int(120 * scaling_factor), "bg": background_color,
                "fg": text_color, "troughcolor": button_gray,
                "activebackground": highlight_color, "highlightthickness": 0,
                "bd": 0, "sliderrelief": tk.FLAT,
                "sliderlength": int(15 * scaling_factor), "width": int(15 * scaling_factor),
                "font": scale_font(("Arial", 10, "bold")),
            }
            left = tk.Scale(
                content, variable=left_var,
                command=lambda value, f=family: sync_from_slider(f, "left", value),
                **slider_options)
            left.grid(row=grid_row, column=2, sticky=tk.W, padx=(int(4 * scaling_factor), 0))
            icon_images = get_icon_images(previous_entry_height)
            link_button = tk.Button(content, image=icon_images["unlink"], bg=background_color,
                                    activebackground=background_color, relief=tk.FLAT, bd=0,
                                    highlightthickness=0, cursor="hand2", padx=0, pady=0)
            # grid's default placement is centered; sticky only accepts n/e/s/w.
            link_button.grid(row=grid_row, column=3, padx=int(8 * scaling_factor))
            tk.Label(content, text="R Joystick:", bg=background_color, fg=text_color,
                     font=scale_font(("Arial", 11, "bold")), anchor=tk.E).grid(row=grid_row, column=4, sticky=tk.E)
            right = tk.Scale(
                content, variable=right_var,
                command=lambda value, f=family: sync_from_slider(f, "right", value),
                **slider_options)
            right.grid(row=grid_row, column=5, sticky=tk.W, padx=(int(4 * scaling_factor), 0))
            def refresh_link(f=family, button=link_button):
                linked = CONFIG.get_joystick_deadzone_settings(profile_name, category)[f]["linked"]
                button.config(image=icon_images["link" if linked else "unlink"])
            rows[family]["refresh_link"] = refresh_link
            refresh_link()
            link_button.config(command=lambda f=family: toggle_link(f))
            # Every cell in this row must reserve the same vertical padding.
            # Otherwise only the controller label is shifted by the row gap.
            for widget in content.grid_slaves(row=grid_row):
                widget.grid_configure(pady=row_pady)

        self.joystick_deadzone_popup_commit = commit_all
        popup.update_idletasks()
        self._place_popup_within_root_bounds(popup, anchor_widget)
        self.root.after(100, self.bind_joystick_custom_popup_outside_click)

    def _joycon_ir_popup_layout(self, popup):
        """The same two-column geometry used by the In-app Gyro popup."""
        content = tk.Frame(popup, bg=background_color)
        content.pack(side=tk.TOP, anchor=tk.CENTER)
        control_font = scale_font(("Arial", 10, "bold"))
        measure = tkFont.Font(font=control_font)
        control_width = measure.measure("0" * 14) + int(18 * scaling_factor)
        control_height = measure.metrics("linespace") + int(10 * scaling_factor)
        rows = []

        def row(label_text, pady_top=0):
            index = len(rows)
            label = tk.Label(content, text=label_text, bg=background_color, fg=text_color,
                             font=scale_font(("Arial", 11, "bold")), anchor=tk.E)
            cell = tk.Frame(content, bg=background_color, width=control_width,
                            height=control_height)
            cell.grid_propagate(False)
            label.grid(row=index, column=0, sticky=tk.E,
                       padx=(0, int(5 * scaling_factor)), pady=(pady_top, 0))
            cell.grid(row=index, column=1, sticky=tk.W, pady=(pady_top, 0))
            rows.append(label)
            return cell

        def finalize():
            popup.update_idletasks()
            label_width = max((item.winfo_reqwidth() for item in rows), default=0)
            content.grid_columnconfigure(0, minsize=label_width)
            content.grid_columnconfigure(1, minsize=control_width)

        return row, finalize, control_font, control_width, control_height

    def _close_joycon_ir_switch_input_popup(self):
        popup = getattr(self, "joycon_ir_switch_input_popup", None)
        if popup is not None and popup.winfo_exists():
            popup.destroy()
        self.joycon_ir_switch_input_popup = None
        self.joycon_ir_switch_input_popup_anchor = None
        bind_id = getattr(self, "joycon_ir_switch_input_popup_bind_id", None)
        if bind_id:
            try:
                self.root.unbind("<ButtonPress>", bind_id)
            except Exception:
                pass
        self.joycon_ir_switch_input_popup_bind_id = None

    def _open_joycon_ir_switch_input_popup(self, anchor_widget, selected, on_change):
        """IR Mouse uses the exact multi-select behaviour of Trigger Deadzone."""
        existing = getattr(self, "joycon_ir_switch_input_popup", None)
        if existing is not None and existing.winfo_exists() and getattr(self, "joycon_ir_switch_input_popup_anchor", None) is anchor_widget:
            self._close_joycon_ir_switch_input_popup()
            return
        self._close_joycon_ir_switch_input_popup()
        spacing = int(10 * scaling_factor)
        gap = int(5 * scaling_factor)
        font = scale_font(("Arial", 9, "bold"))
        measure = tkFont.Font(font=font)
        selected = set(normalize_dampening_inputs(selected))
        button_width = max(measure.measure(back_button_label(token)) for token in SWITCH_INPUT_DAMPENING_OPTIONS) + int(16 * scaling_factor)
        button_height = measure.metrics("linespace") + int(10 * scaling_factor)
        popup = tk.Frame(self.root, bg=background_color, bd=1, relief=tk.SOLID,
                         padx=int(8 * scaling_factor), pady=spacing)
        self.joycon_ir_switch_input_popup = popup
        self.joycon_ir_switch_input_popup_anchor = anchor_widget
        block = tk.Frame(popup, bg=background_color)
        block.pack(side=tk.TOP, anchor=tk.W)
        # Keep the Trigger Deadzone matrix and toggle semantics intact.  Empty is
        # represented by the anchor text "None", not by an extra option cell.
        from config import BACK_BUTTON_CATEGORIES
        columns = dict(BACK_BUTTON_CATEGORIES)["Switch Input"]
        button_refs = {}

        def set_button_state(token):
            cell, btn = button_refs[token]
            is_selected = token in selected
            border = int(2 * scaling_factor) if is_selected else 0
            cell.config(bg=highlight_color if is_selected else background_color)
            btn.place(x=border, y=border, width=button_width - border * 2,
                      height=button_height - border * 2)

        def toggle_token(token):
            if token in selected:
                selected.remove(token)
            else:
                selected.add(token)
            ordered = [item for item in SWITCH_INPUT_DAMPENING_OPTIONS if item in selected]
            on_change(ordered)
            set_button_state(token)

        for col_index, column in enumerate(columns):
            for row_index, token in enumerate(column):
                selected_now = token in selected
                cell = tk.Frame(block, bg=highlight_color if selected_now else background_color,
                                width=button_width, height=button_height)
                cell.grid(row=row_index, column=col_index, padx=(0, gap), pady=(0, gap), sticky="nsew")
                cell.grid_propagate(False)
                border = int(2 * scaling_factor) if selected_now else 0
                btn = tk.Button(cell, text=back_button_label(token), font=font, bg=button_gray,
                                fg="white", relief=tk.FLAT, bd=0, highlightthickness=0,
                                activebackground=highlight_color, activeforeground="white",
                                command=lambda value=token: toggle_token(value))
                button_refs[token] = (cell, btn)
                set_button_state(token)
        popup.place(in_=self.root, x=-10000, y=-10000)
        popup.update_idletasks()
        self._place_popup_within_root_bounds(popup, anchor_widget)

        def close_if_outside(event):
            current = getattr(self, "joycon_ir_switch_input_popup", None)
            if current is None or not current.winfo_exists():
                self._close_joycon_ir_switch_input_popup()
                return
            if self._event_in_widget(current, event) or self._event_in_widget(anchor_widget, event):
                return
            # Clicking in the owning IR Mouse popup is not outside its parent, but it
            # should dismiss the previous selector before another control is used.
            self._close_joycon_ir_switch_input_popup()

        self.joycon_ir_switch_input_popup_bind_id = self.root.bind("<ButtonPress>", close_if_outside, add="+")

    def refresh_joycon_ir_sensor_buttons(self):
        button_specs = (
            (None, "left", getattr(self, "joycon_ir_left_button", None)),
            (None, "right", getattr(self, "joycon_ir_right_button", None)),
            ("in_app_gyro_mode_mappings", "left", getattr(self, "gyro_joycon_ir_left_button", None)),
            ("in_app_gyro_mode_mappings", "right", getattr(self, "gyro_joycon_ir_right_button", None)),
        )
        for mapping_scope, side, button in button_specs:
            if button is not None:
                value = CONFIG.get_joycon_ir_sensor_settings_scoped(side, scope=mapping_scope).get("function", "Default")
                if value == "Default":
                    label = "IR Mouse"
                elif isinstance(value, str) and value.startswith("Custom"):
                    payload = value.split(":", 1)[-1]
                    label = {IN_APP_GYRO_TOKEN: IN_APP_GYRO_LABEL, MODE_SHIFT_TOKEN: MODE_SHIFT_LABEL,
                             GYRO_LOCK_TOKEN: GYRO_LOCK_LABEL}.get(
                                 payload,
                                 back_button_label(MOUSE_CLICK_CUSTOM_TOKENS[payload])
                                 if payload in MOUSE_CLICK_CUSTOM_TOKENS else "Custom")
                else:
                    label = back_button_label(value)
                button.config(text=f"{'Left' if side == 'left' else 'Right'} Joy-con: {label}")

    def open_joycon_ir_sensor_settings(self, side, anchor_widget, mapping_scope=None):
        if self._toggle_joystick_popup(anchor_widget):
            return
        # Freeze the edited scope for the entire parent/child popup lifetime.
        profile_name, category = CONFIG.active_profile, CONFIG.get_current_category()
        popup = self._create_joystick_option_popup(anchor_widget, defer_place=True)
        popup.joycon_ir_context = (side, profile_name, category, mapping_scope)
        settings = CONFIG.get_joycon_ir_sensor_settings_scoped(side, profile_name, category, mapping_scope)
        create_row, finalize, control_font, control_width, control_height = self._joycon_ir_popup_layout(popup)
        function_cell = create_row("Function:")
        # Normal Function state must match Trigger Deadzone exactly.  Only a
        # compound special action grows this cell at runtime.
        compound_width = max(control_width, tkFont.Font(font=control_font).measure("In-app Gyro") + int(105 * scaling_factor))
        function_cell.config(width=control_width)
        holder = tk.Frame(function_cell, bg=background_color, width=control_width, height=control_height)
        holder.pack(side=tk.LEFT)
        holder.pack_propagate(False)
        selector = BackButtonSelector(holder, self, font=control_font, auto_fit=False,
                                      display_overrides={"Default": "Default (IR Mouse)"})
        selector.config(width=14)

        def canonical(value):
            aliases = {"In-app Gyro": f"Custom[Hold]:{IN_APP_GYRO_TOKEN}",
                       "Gyro": f"Custom[Hold]:{IN_APP_GYRO_TOKEN}",
                       "Mode Shift": f"Custom[Hold]:{MODE_SHIFT_TOKEN}",
                       "Gyro Lock": f"Custom[Hold]:{GYRO_LOCK_TOKEN}"}
            if value in MOUSE_CLICK_BACK_BUTTON_TOKENS:
                return f"Custom[Hold]:{MOUSE_CLICK_BACK_BUTTON_TOKENS[value]}"
            return aliases.get(value, value)

        mode_var = tk.StringVar(value="Hold")
        mode_btn = tk.Button(holder, text="Hold", bg=button_gray, fg="white",
                             font=scale_font(("Arial", 9, "bold")), relief=tk.FLAT, bd=0, width=4)
        action_btn = tk.Button(holder, bg=button_gray, fg="white", font=control_font,
                               relief=tk.FLAT, bd=0)
        close_btn = tk.Button(holder, text="X", bg="#ff4444", fg="white", font=control_font,
                              relief=tk.FLAT, bd=0)
        record_entry = RecordingEntry(holder, normal_font=scale_font(("Arial", 11, "bold")),
                                      prefix_font=scale_font(("Arial", 8, "bold")), width=11,
                                      bg=button_gray, fg="white")
        Tooltip(record_entry, record_entry.get)

        def custom_parts(value):
            if value.startswith("Custom[Tap]:"):
                return "Tap", value[12:]
            if value.startswith("Custom[Hold]:"):
                return "Hold", value[13:]
            return "Hold", value[7:] if value.startswith("Custom:") else ""

        def is_in_app_gyro_function(value):
            if not isinstance(value, str) or not value.startswith("Custom"):
                return False
            _mode, payload = custom_parts(value)
            return payload == IN_APP_GYRO_TOKEN

        def set_function(value, save=True):
            old_value = CONFIG.get_joycon_ir_sensor_settings_scoped(side, profile_name, category, mapping_scope).get("function", "Default")
            value = canonical(value)
            leaving_in_app_gyro = is_in_app_gyro_function(old_value) and not is_in_app_gyro_function(value)
            if leaving_in_app_gyro:
                self.close_in_app_gyro_popup()
            CONFIG.set_joycon_ir_sensor_setting_scoped(side, "function", value, profile_name, category, mapping_scope)
            if leaving_in_app_gyro:
                CONFIG.reset_joycon_ir_in_app_gyro_settings_scoped(side, profile_name, category, mapping_scope)
            if save:
                CONFIG.save_config()
            self.refresh_joycon_ir_sensor_buttons()
            refresh_function(value)

        def clear_function():
            self.close_joycon_ir_mouse_popup()
            self._close_joycon_ir_switch_input_popup()
            selector.set("None")
            set_function("None")

        close_btn.config(command=clear_function)

        def toggle_mode():
            value = CONFIG.get_joycon_ir_sensor_settings_scoped(side, profile_name, category, mapping_scope).get("function", "None")
            if not isinstance(value, str) or not value.startswith("Custom"):
                return
            old_mode, payload = custom_parts(value)
            new_mode = "Tap" if old_mode == "Hold" else "Hold"
            mode_var.set(new_mode)
            mode_btn.config(text=new_mode)
            set_function(f"Custom[{new_mode}]:{payload}")

        mode_btn.config(command=toggle_mode)

        def begin_custom_recording(_event=None):
            value = CONFIG.get_joycon_ir_sensor_settings_scoped(side, profile_name, category, mapping_scope).get("function", "Custom")
            mode, _payload = custom_parts(value if isinstance(value, str) else "Custom")
            mode_var.set(mode)
            mode_btn.config(text=mode)
            self.start_custom_recording(
                "joycon_ir_sensor", record_entry, selector, holder, mode_var,
                value_writer=lambda recorded: CONFIG.set_joycon_ir_sensor_setting_scoped(side, "function", recorded, profile_name, category, mapping_scope),
                empty_writer=lambda: CONFIG.set_joycon_ir_sensor_setting_scoped(side, "function", "Default", profile_name, category, mapping_scope),
                complete_callback=lambda _value: (CONFIG.save_config(), self.refresh_joycon_ir_sensor_buttons(), refresh_function(), self.root.after(100, self.bind_joystick_custom_popup_outside_click)),
            )

        record_entry.bind("<Button-1>", begin_custom_recording)

        def open_action_popup():
            value = CONFIG.get_joycon_ir_sensor_settings_scoped(side, profile_name, category, mapping_scope).get("function", "None")
            if value == "Default":
                self.open_joycon_ir_mouse_settings(side, action_btn, profile_name, category, mapping_scope)
            elif value == "Change Profile":
                self.open_change_profile_popup(action_btn)
                self.joycon_ir_change_profile_popup = getattr(self, "change_profile_popup", None)
            elif isinstance(value, str) and value.startswith("Custom"):
                mode, payload = custom_parts(value)
                if payload == IN_APP_GYRO_TOKEN:
                    self.open_joycon_ir_in_app_gyro_settings(side, action_btn, profile_name, category, mode, mapping_scope)

        action_btn.config(command=open_action_popup)

        def select_function_popup_value(token, button=action_btn):
            if token in MOUSE_CLICK_BACK_BUTTON_TOKENS:
                button._mouse_click_token = token
            set_function(token)

        def refresh_function(value=None):
            value = value if value is not None else CONFIG.get_joycon_ir_sensor_settings_scoped(side, profile_name, category, mapping_scope).get("function", "Default")
            selector.pack_forget(); mode_btn.pack_forget(); action_btn.pack_forget(); record_entry.pack_forget(); close_btn.pack_forget()
            action_btn._mouse_click_token = "None"
            action_btn.get = lambda button=action_btn: getattr(button, "_mouse_click_token", "None")
            action_btn.display_label = back_button_label
            action_btn.select_value = select_function_popup_value
            is_compound = isinstance(value, str) and value.startswith("Custom")
            active_width = compound_width if is_compound else control_width
            function_cell.config(width=active_width, height=control_height)
            holder.config(width=active_width, height=control_height)
            popup.update_idletasks()
            self._place_popup_within_root_bounds(popup, anchor_widget)
            if value == "Default":
                action_btn.config(text="IR Mouse")
                action_btn.config(command=open_action_popup)
                action_btn.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                close_btn.pack(side=tk.LEFT, fill=tk.Y, padx=(int(2 * scaling_factor), 0))
            elif value == "Change Profile":
                action_btn.config(text="Change Profile")
                action_btn.config(command=open_action_popup)
                action_btn.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                close_btn.pack(side=tk.LEFT, fill=tk.Y, padx=(int(2 * scaling_factor), 0))
            elif isinstance(value, str) and value.startswith("Custom"):
                mode, payload = custom_parts(value)
                mode_var.set(mode)
                mode_btn.config(text=mode)
                mode_btn.pack(side=tk.LEFT, fill=tk.Y, padx=(0, int(2 * scaling_factor)))
                special_text = {IN_APP_GYRO_TOKEN: IN_APP_GYRO_LABEL,
                                MODE_SHIFT_TOKEN: MODE_SHIFT_LABEL,
                                GYRO_LOCK_TOKEN: GYRO_LOCK_LABEL}.get(payload)
                mouse_token = MOUSE_CLICK_CUSTOM_TOKENS.get(payload)
                if special_text or mouse_token:
                    action_btn.config(text=special_text or back_button_label(mouse_token))
                    if mouse_token:
                        action_btn._mouse_click_token = mouse_token
                        action_btn.config(command=lambda button=action_btn: self.open_back_button_popup(button))
                    else:
                        action_btn.config(command=open_action_popup)
                    action_btn.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                    if not mouse_token:
                        close_btn.pack(side=tk.LEFT, fill=tk.Y, padx=(int(2 * scaling_factor), 0))
                else:
                    record_entry.config(state="normal")
                    record_entry.delete(0, tk.END)
                    record_entry.insert(0, format_input_display(payload) if payload else "Record input")
                    record_entry.config(state="readonly")
                    record_entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                    close_btn.pack(side=tk.LEFT, fill=tk.Y, padx=(int(2 * scaling_factor), 0))
                if value == "Custom":
                    self.root.after_idle(begin_custom_recording)
            else:
                selector.set(value)
                selector.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        selector.set(settings.get("function", "Default"))
        def _on_function_selected(_event):
            set_function(selector.get())
            # Auto-open the settings floating window for functions that have one.
            # refresh_function (run inside set_function) packs action_btn and wires its
            # popup command only for Default / In-App Gyro / Change Profile / Mouse Click;
            # Mode Shift / Gyro Lock pack it as a label with a no-op command, and
            # record/None don't pack it -- so invoking only when mapped opens exactly the
            # functions that have a window. Deferred so the repack/realize finishes first.
            self.root.after(50, lambda: action_btn.winfo_ismapped() and action_btn.invoke())
        selector.bind("<<ComboboxSelected>>", _on_function_selected)
        refresh_function(settings.get("function", "Default"))

        threshold_cell = create_row("Activate Threshold:", int(8 * scaling_factor))
        threshold = tk.Scale(threshold_cell, from_=1, to=3, resolution=1, orient=tk.HORIZONTAL,
                             length=control_width, bg=background_color, fg=text_color,
                             troughcolor=button_gray, activebackground=highlight_color,
                             highlightthickness=0, bd=0, sliderrelief=tk.FLAT,
                             sliderlength=int(15 * scaling_factor), width=int(15 * scaling_factor),
                             font=control_font)
        threshold.set(settings.get("activate_threshold", 1))
        threshold.pack(side=tk.LEFT)
        threshold.bind("<ButtonRelease-1>", lambda _event: (CONFIG.set_joycon_ir_sensor_setting_scoped(side, "activate_threshold", int(float(threshold.get())), profile_name, category, mapping_scope), CONFIG.save_config()))
        finalize()
        popup.update_idletasks()
        self._place_popup_within_root_bounds(popup, anchor_widget)

        self.root.after(100, self.bind_joystick_custom_popup_outside_click)

    def open_joycon_ir_mouse_settings(self, side, anchor_widget, profile_name=None, category=None, mapping_scope=None):
        profile_name = profile_name or CONFIG.active_profile
        category = category or CONFIG.get_current_category()
        existing = getattr(self, "joycon_ir_mouse_popup", None)
        if existing is not None and existing.winfo_exists() and getattr(self, "joycon_ir_mouse_popup_anchor", None) is anchor_widget:
            self.close_joycon_ir_mouse_popup()
            return
        self.close_joycon_ir_mouse_popup()
        self._close_joycon_ir_switch_input_popup()
        popup = tk.Frame(self.root, bg=background_color, bd=1, relief=tk.SOLID,
                         padx=int(10 * scaling_factor), pady=int(10 * scaling_factor))
        self.joycon_ir_mouse_popup = popup
        self.joycon_ir_mouse_popup_anchor = anchor_widget
        popup.joycon_ir_context = (side, profile_name, category, mapping_scope)
        settings = CONFIG.get_joycon_ir_sensor_settings_scoped(side, profile_name, category, mapping_scope)["ir_mouse"]

        create_row, finalize, control_font, control_width, _control_height = self._joycon_ir_popup_layout(popup)
        sensitivity_cell = create_row("Sensitivity:")
        sensitivity = tk.Scale(sensitivity_cell, from_=1, to=10, resolution=.2, orient=tk.HORIZONTAL,
                               length=control_width, bg=background_color, fg=text_color,
                               troughcolor=button_gray, activebackground=highlight_color,
                               highlightthickness=0, bd=0, sliderrelief=tk.FLAT,
                               sliderlength=int(15 * scaling_factor), width=int(15 * scaling_factor),
                               font=control_font)
        sensitivity.set(settings.get("sensitivity", 4.0))
        sensitivity.pack(side=tk.LEFT)
        sensitivity.bind("<ButtonRelease-1>", lambda _event: (CONFIG.set_joycon_ir_mouse_setting_scoped(side, "sensitivity", float(sensitivity.get()), profile_name, category, mapping_scope), CONFIG.save_config()))

        def display_tokens(tokens):
            return " | ".join(back_button_label(token) for token in tokens) if tokens else "None"

        def create_ir_mouse_click_button(cell):
            group = tk.Frame(cell, bg=background_color, width=control_width, height=_control_height)
            group.pack(side=tk.LEFT)
            group.pack_propagate(False)
            button = tk.Button(
                group,
                bg=button_gray,
                fg="white",
                font=control_font,
                relief=tk.FLAT,
                bd=0,
                activebackground=button_gray,
                activeforeground="white",
            )
            button.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            return button

        for key, title in (("left_click", "Mouse Left Click:"), ("right_click", "Mouse Right Click:"), ("middle_click", "Mouse Middle Click:")):
            cell = create_row(title, int(8 * scaling_factor))
            btn = create_ir_mouse_click_button(cell)
            def select_token(tokens, setting_key=key, button=btn):
                CONFIG.set_joycon_ir_mouse_setting_scoped(side, setting_key, tokens, profile_name, category, mapping_scope)
                CONFIG.save_config()
                button.config(text=display_tokens(tokens))
            btn.config(text=display_tokens(settings.get(key, [])),
                       command=lambda button=btn, setting_key=key: self._open_joycon_ir_switch_input_popup(
                           button,
                           CONFIG.get_joycon_ir_sensor_settings_scoped(side, profile_name, category, mapping_scope)["ir_mouse"].get(setting_key, []),
                           lambda tokens, k=setting_key, b=button: select_token(tokens, k, b)))
            Tooltip(btn, lambda k=key: display_tokens(CONFIG.get_joycon_ir_sensor_settings_scoped(side, profile_name, category, mapping_scope)["ir_mouse"].get(k, [])))
        finalize()
        popup.update_idletasks()
        self._place_popup_within_root_bounds(popup, anchor_widget)

        bind_id = getattr(self, "joycon_ir_mouse_popup_bind_id", None)
        if bind_id:
            try:
                self.root.unbind("<ButtonPress>", bind_id)
            except Exception:
                pass

        def close_if_outside_ir_mouse(event):
            current = getattr(self, "joycon_ir_mouse_popup", None)
            if current is None or not current.winfo_exists():
                self.close_joycon_ir_mouse_popup()
                return
            if (self._event_in_widget(current, event)
                    or self._event_in_widget(getattr(self, "joycon_ir_switch_input_popup", None), event)
                    or self._event_in_widget(anchor_widget, event)):
                return
            self.close_joycon_ir_mouse_popup()

        self.joycon_ir_mouse_popup_bind_id = self.root.bind("<ButtonPress>", close_if_outside_ir_mouse, add="+")

    def close_joycon_ir_mouse_popup(self):
        self._close_joycon_ir_switch_input_popup()
        popup = getattr(self, "joycon_ir_mouse_popup", None)
        if popup is not None and popup.winfo_exists():
            popup.destroy()
        self.joycon_ir_mouse_popup = None
        self.joycon_ir_mouse_popup_anchor = None
        bind_id = getattr(self, "joycon_ir_mouse_popup_bind_id", None)
        if bind_id:
            try:
                self.root.unbind("<ButtonPress>", bind_id)
            except Exception:
                pass
        self.joycon_ir_mouse_popup_bind_id = None

    def on_gc_trigger_calib_clicked(self):
        gc_controller = None
        for vc in VIRTUAL_CONTROLLERS:
            if vc and len(vc.controllers) > 0:
                for c in vc.controllers:
                    if getattr(c.controller_info, 'product_id', 0) == NSO_GAMECUBE_CONTROLLER_PID:
                        gc_controller = c
                        break
                if gc_controller:
                    break
        if not gc_controller:
            from tkinter import messagebox
            messagebox.showinfo("Not Found", "No NSO GameCube Controller is currently connected.")
            return

        GCTriggerCalibrationWizard(self.root, gc_controller)

    def update_driver_type_setting(self, val, persist_preference=True):
        self.close_joystick_custom_popup()
        # Redirect a saved/manual WinUHid selection only when the external driver
        # is actually unavailable.  MSIX never installs it from inside the app.
        if (utils.is_packaged()
                and getattr(CONFIG, "driver_fallback_active", False)
                and val == "WinUHid"):
            val = "ViGEmBus"
        # 1. 霈??(Removed load_config to prevent async save race condition)

        old_driver = getattr(CONFIG, "driver_type", "WinUHid")
        old_sim_mode = getattr(CONFIG, "simulation_mode", "Xbox One")

        # A successful USBIP uninstall is not complete until Windows restarts.
        # Block the selection before changing profile/config state and repeat the
        # restart prompt even if the UI was switched to another driver meanwhile.
        if val == "USBIP" and getattr(self, "_usbip_restart_pending", False):
            self.driver_switch.set_value(old_driver)
            self._prompt_usbip_restart_required()
            return
        
        if (persist_preference and hasattr(CONFIG, 'active_profile')
                and CONFIG.active_profile in CONFIG.profiles):
            CONFIG.profiles[CONFIG.active_profile]["driver_type"] = val
            
        if old_driver == val:
            CONFIG.save_config()
            return
            
        # Check driver installation BEFORE updating CONFIG or recreating controllers!
        if val == "ViGEmBus":
            if not self.check_vigembus_installation(save=False):
                # Revert to old driver
                self.driver_switch.set_value(old_driver)
                return
        elif val == "USBIP":
            from utils import get_usbip_exe_path
            usbip_exe = get_usbip_exe_path()

            def usbip_ready():
                invalidate_driver_status_cache("usbip")
                status = get_usbip_status()
                return status.installed or (
                    status.unknown and os.path.exists(usbip_exe)), status

            ready, usbip_status = usbip_ready()
            if not ready:
                partial = usbip_status.state == USBIP_PARTIAL
                answer = self.ask_centered_yes_no(
                    "Repair USBIP Driver" if partial else "Install USBIP Driver",
                    (("USBIP is partially installed.\n\n" + usbip_status.describe() + "\n\n"
                      "Do you want to remove it now? Restart Windows before "
                      "installing USBIP again.\n")
                     if partial else
                     "The USBIP driver is required but is not installed.\n\n"
                     "Do you want to install it now?\n") +
                    "(Requires administrator privileges and will temporarily reset USB connections.)"
                )
                if answer:
                    if partial:
                        self.run_usbip_uninstall()
                        self.driver_switch.set_value(old_driver)
                        return
                    self.run_usbip_install(show_success_msg=True)
                    if not usbip_ready()[0]:
                        self.driver_switch.set_value(old_driver)
                        return
                else:
                    self.driver_switch.set_value(old_driver)
                    return
        else:
            winuhid_status = get_winuhid_status()
            if winuhid_status.unknown and verify_winuhid_runtime(attempts=2):
                # State unreadable but the driver actually works - do not prompt.
                logger.warning("WinUHid status undetermined: %s", winuhid_status.describe())
                winuhid_status = None
            if winuhid_status is not None and not winuhid_status.installed:
                if getattr(CONFIG, 'driver_installed', False):
                    CONFIG.driver_installed = False
                    CONFIG.save_config()
                    self.update_driver_button()
                answer = self.ask_centered_yes_no(
                    "Repair Virtual Controller Driver" if winuhid_status.state == WINUHID_PARTIAL else "Install Virtual Controller Driver",
                    (("WinUHid is partially installed.\n\n" + winuhid_status.describe() + "\n\n"
                      "Do you want to clean up and reinstall it now?")
                     if winuhid_status.state == WINUHID_PARTIAL else
                     "WinUHid driver is not installed.\n\nDo you want to install it now?")
                    + "\n(Requires administrator privileges.)"
                )
                if answer:
                    if winuhid_status.state == WINUHID_PARTIAL and not self.run_driver_uninstall():
                        self.driver_switch.set_value(old_driver)
                        return
                    self.run_driver_install(show_success_msg=False)
                    invalidate_driver_status_cache("winuhid")
                    installed_now = get_winuhid_status()
                    if not (installed_now.installed
                            or (installed_now.unknown and verify_winuhid_runtime(attempts=2))):
                        self.driver_switch.set_value(old_driver)
                        return
                else:
                    self.driver_switch.set_value(old_driver)
                    return

        # If we got here, checking was successful! Apply the mode switch in memory:
        CONFIG.driver_type = val
        if persist_preference:
            CONFIG.preferred_driver_type = val
            CONFIG.driver_fallback_active = False
        self.update_driver_button()
        
        # Load the remembered simulation mode for the target driver
        if val == "ViGEmBus":
            CONFIG.simulation_mode = CONFIG.vigembus_sim_mode
        elif val == "USBIP":
            CONFIG.simulation_mode = CONFIG.usbip_sim_mode
        else:
            CONFIG.simulation_mode = CONFIG.winuhid_sim_mode
            
        # Update sim mode switch options and set value
        if val == "ViGEmBus":
            self.sim_mode_switch.update_options(["Xbox360", "PS4"], ["Xbox360", "PS4"], CONFIG.simulation_mode)
        elif val == "USBIP":
            self.sim_mode_switch.update_options(["Switch1", "Switch2"], ["Switch1", "Switch2"], CONFIG.simulation_mode)
        else:
            self.sim_mode_switch.update_options(["Xbox One", "PS4"], ["Xbox One", "PS4"], CONFIG.simulation_mode)
            
        self.update_dynamic_rumble_mode_options()
            
        # Apply the driver change to all running virtual controllers immediately
        success = True
        if hasattr(self, 'current_controllers'):
            try:
                # Pass 1: Cleanly close all running virtual controllers
                for vc in self.current_controllers:
                    if vc is not None:
                        with vc.state_lock:
                            if hasattr(vc, 'vg_controller') and vc.vg_controller is not None:
                                vc.cleanup_vg_controller()
                
                # Wait for PnP subsystem to settle
                import gc
                gc.collect()
                import time
                end_t = time.time() + 0.5
                while time.time() < end_t:
                    self.root.update()
                    time.sleep(0.01)
                
                # Pass 2: Recreate them under the new driver/mode sequentially
                for i, vc in enumerate(self.current_controllers):
                    if vc is not None:
                        if i > 0:
                            end_t2 = time.time() + 0.2
                            while time.time() < end_t2:
                                self.root.update()
                                time.sleep(0.01)
                        with vc.state_lock:
                            vc.mode = CONFIG.simulation_mode
                            if vc.mode == "Switch1":
                                vc.hold_mode = "Vertical"
                            elif vc.is_single() and len(vc.controllers) > 0:
                                addr = vc.controllers[0].device.address
                                if addr in CONFIG.joycon_hold_mode:
                                    vc.hold_mode = CONFIG.joycon_hold_mode[addr]
                                else:
                                    vc.hold_mode = "Vertical"
                            vc._setup_vg_controller()
                        if vc.loop and vc.loop.is_running():
                            asyncio.run_coroutine_threadsafe(vc.update_leds(), vc.loop)
            except Exception as e:
                logger.error(f"Failed to recreate controllers during driver mode switch: {e}")
                success = False

        if not success:
            # Revert CONFIG memory values by reloading from disk
            CONFIG.load_config()
            # Revert the GUI switches
            self.driver_switch.set_value(old_driver)
            self.update_driver_button()
            
            if old_driver == "ViGEmBus":
                self.sim_mode_switch.update_options(["Xbox360", "PS4"], ["Xbox360", "PS4"], old_sim_mode)
            elif old_driver == "USBIP":
                self.sim_mode_switch.update_options(["Switch1", "Switch2"], ["Switch1", "Switch2"], old_sim_mode)
            else:
                self.sim_mode_switch.update_options(["Xbox One", "PS4"], ["Xbox One", "PS4"], old_sim_mode)
                
            # Recreate controllers under old config
            if hasattr(self, 'current_controllers'):
                try:
                    for vc in self.current_controllers:
                        if vc is not None:
                            with vc.state_lock:
                                vc.mode = old_sim_mode
                                if vc.mode == "Switch1":
                                    vc.hold_mode = "Vertical"
                                elif vc.is_single() and len(vc.controllers) > 0:
                                    addr = vc.controllers[0].device.address
                                    if addr in CONFIG.joycon_hold_mode:
                                        vc.hold_mode = CONFIG.joycon_hold_mode[addr]
                                    else:
                                        vc.hold_mode = "Vertical"
                                vc._setup_vg_controller()
                            if vc.loop and vc.loop.is_running():
                                asyncio.run_coroutine_threadsafe(vc.update_leds(), vc.loop)
                except Exception as re_err:
                    logger.error(f"Failed to restore controllers to old driver: {re_err}")
        else:
            # 摮?
            CONFIG.save_config()
            
        self.close_joystick_custom_popup()
        self.close_in_app_gyro_popup()
        self.refresh_joycon_ir_sensor_buttons()
        self._refresh_mapping_comboboxes()
        self.force_refresh_player_slots()
 
    def force_refresh_player_slots(self):
        # While a batch UI update is in progress (e.g. a profile switch), skip the
        # rebuild so the player area isn't destroyed/recreated and repainted multiple
        # times (which causes ghosting). The caller does one rebuild when the batch ends.
        if getattr(self, '_suppress_player_slot_refresh', False):
            self._player_slot_refresh_pending = True
            return
        self._update_djg_panel_visibility()
        if hasattr(self, 'djg_dominant_var'):
            djg_dominant = getattr(CONFIG, "djg_dominant_side", "Right")
            self.djg_dominant_var.set(djg_dominant)
            if djg_dominant in ("Left", "Right") and hasattr(self, 'djg_dominant_switch'):
                self.djg_dominant_switch.set_value(djg_dominant)
        if hasattr(self, 'current_controllers'):
            if getattr(self, 'players_info', None) is not None:
                for p in self.players_info:
                    if hasattr(p, 'main_frame') and p.main_frame:
                        p.main_frame.destroy()
                self.players_info = None
            self.update(self.current_controllers)
            try:
                self.root.update_idletasks()
            except:
                pass
    def _refresh_mapping_comboboxes(self):
        mapping_keys = [
            "home", "capt", "c", "plus", "minus",
            "a", "b", "x", "y",
            "up", "down", "left", "right",
            "zl", "l", "zr", "r",
            "l_stk", "r_stk",
            "gl", "gr", "sll", "srl", "slr", "srr",
            "gc_l_click", "gc_r_click"
        ]
        for j_key in ("l_joystick", "r_joystick"):
            for direction in ("up", "down", "left", "right"):
                mapping_keys.append(f"{j_key}_{direction}")
            mapping_keys.append(j_key)
                
        active_scope = "in_app_gyro_mode_mappings" if getattr(self, "settings_active_tab", None) == "in_app_gyro_mode_mapping" else None
        for mapping_scope in (active_scope,):
            suffix = self._mapping_scope_suffix(mapping_scope)
            for key in mapping_keys:
                attr_key = self._mapping_attr(key, suffix)
                combo = getattr(self, f"{attr_key}_combo", None)
                custom_frame = getattr(self, f"{attr_key}_custom_frame", None)
                entry = getattr(self, f"{attr_key}_entry", None)
                in_app_gyro_btn = getattr(self, f"{attr_key}_in_app_gyro_btn", None)
                mouse_click_btn = getattr(self, f"{attr_key}_mouse_click_btn", None)
                mode_btn = getattr(self, f"{attr_key}_mode_btn", None)
                mode_var = getattr(self, f"{attr_key}_mode_var", None)
                cp_frame = getattr(self, f"{attr_key}_cp_frame", None)
                close_btn = getattr(self, f"{attr_key}_close_btn", None)

                if not combo or not combo.winfo_exists():
                    continue
                base_key, sep, direction = key.rpartition("_")
                if sep and base_key in ("l_joystick", "r_joystick") and direction in ("up", "down", "left", "right", "click"):
                    current_val = CONFIG.get_joystick_custom_scoped(base_key, mapping_scope).get(direction, "Default")
                else:
                    current_val = CONFIG.get_mapping_setting_scoped(key, "Default", mapping_scope)
                if current_val == "Gyro":
                    current_val = "In-app Gyro"
                if cp_frame:
                    cp_frame.pack_forget()
                if current_val == "Change Profile" and cp_frame:
                    combo.set("Change Profile")
                    combo.pack_forget()
                    if custom_frame:
                        custom_frame.pack_forget()
                    if mouse_click_btn:
                        mouse_click_btn._mouse_click_token = "Default"
                        mouse_click_btn.pack_forget()
                    if mode_var and mode_btn:
                        mode_var.set("Hold")
                        mode_btn.config(text="Hold")
                    cp_frame.pack(side=tk.LEFT)
                else:
                    mouse_click_mapping = parse_mouse_click_mapping(current_val)
                    if mouse_click_mapping and custom_frame and mouse_click_btn and mode_btn and mode_var and close_btn:
                        option_token, mode = mouse_click_mapping
                        combo.pack_forget()
                        if entry:
                            entry.pack_forget()
                        if in_app_gyro_btn:
                            in_app_gyro_btn.pack_forget()
                        close_btn.pack_forget()
                        mode_var.set(mode)
                        mode_btn.config(text=mode)
                        mouse_click_btn._mouse_click_token = option_token
                        mouse_click_btn.config(text=back_button_label(option_token))
                        combo.set(option_token)
                        mouse_click_btn.pack(side=tk.LEFT, fill=tk.Y)
                        custom_frame.pack(side=tk.LEFT)
                        if current_val == option_token:
                            value = f"Custom[{mode}]:{MOUSE_CLICK_BACK_BUTTON_TOKENS[option_token]}"
                            CONFIG.set_mapping_setting_scoped(key, value, mapping_scope)
                    elif isinstance(current_val, str) and current_val.startswith("Custom"):
                        combo.pack_forget()
                        if custom_frame and entry and mode_btn and mode_var:
                            if not close_btn.winfo_ismapped():
                                close_btn.pack(side=tk.LEFT, padx=(int(2 * scaling_factor), 0), fill=tk.Y)
                            entry.config(state="normal")
                            entry.delete(0, tk.END)

                            if current_val.startswith("Custom[Tap]:"):
                                mode_var.set("Tap")
                                mode_btn.config(text="Tap")
                                display_val = current_val[12:]
                            elif current_val.startswith("Custom[Hold]:"):
                                mode_var.set("Hold")
                                mode_btn.config(text="Hold")
                                display_val = current_val[13:]
                            else:
                                mode_var.set("Hold")
                                mode_btn.config(text="Hold")
                                display_val = current_val[7:]

                            if display_val != IN_APP_GYRO_TOKEN and not display_val.startswith(IN_APP_GYRO_TOKEN):
                                if entry and in_app_gyro_btn and close_btn:
                                    in_app_gyro_btn.pack_forget()
                                    if mouse_click_btn:
                                        mouse_click_btn._mouse_click_token = "Default"
                                        mouse_click_btn.pack_forget()
                                    entry.pack(side=tk.LEFT, fill=tk.Y, before=close_btn)
                            if display_val == GYRO_LOCK_TOKEN:
                                combo.set(GYRO_LOCK_LABEL)
                                entry.insert(0, GYRO_LOCK_LABEL)
                            elif display_val == MODE_SHIFT_TOKEN:
                                combo.set(MODE_SHIFT_LABEL)
                                entry.insert(0, MODE_SHIFT_LABEL)
                            elif display_val.startswith(IN_APP_GYRO_TOKEN):
                                combo.set(IN_APP_GYRO_LABEL)
                                simul_val = CONFIG.get_mapping_setting_scoped(f"{key}_in_app_gyro_simul", "None", None)
                                display_str = IN_APP_GYRO_LABEL
                                if simul_val == "None":
                                    pass
                                elif simul_val == "Default":
                                    def get_key_name(k):
                                        return {"home": "Home", "capt": "Capture", "c": "Chat", "plus": "Plus", "minus": "Minus", "up": "Dpad Up", "down": "Dpad Down", "left": "Dpad Left", "right": "Dpad Right", "l_stk": "L Joystick Click", "r_stk": "R Joystick Click", "sll": "SL_L", "srl": "SR_L", "slr": "SL_R", "srr": "SR_R"}.get(k, k.upper())
                                    display_str += f" + {get_key_name(key)}"
                                else:
                                    if isinstance(simul_val, str) and simul_val.startswith("Custom"):
                                        if "]:" in simul_val:
                                            display_str += " + " + format_input_display(simul_val.split("]:")[1])
                                        elif ":" in simul_val:
                                            display_str += " + " + format_input_display(simul_val.split(":")[1])
                                    else:
                                        if simul_val == "HOME": display_str += " + Home"
                                        elif simul_val == "CAPTURE": display_str += " + Capture"
                                        elif simul_val == "PRTSC": display_str += " + PrtSc"
                                        else: display_str += f" + {format_input_display(simul_val)}"
                                if entry and in_app_gyro_btn and close_btn:
                                    entry.pack_forget()
                                    if mouse_click_btn:
                                        mouse_click_btn._mouse_click_token = "Default"
                                        mouse_click_btn.pack_forget()
                                    in_app_gyro_btn.config(text=display_str)
                                    in_app_gyro_btn.pack(side=tk.LEFT, fill=tk.Y, before=close_btn)
                            else:
                                combo.set("Custom")
                                if entry and in_app_gyro_btn and close_btn:
                                    in_app_gyro_btn.pack_forget()
                                    if mouse_click_btn:
                                        mouse_click_btn._mouse_click_token = "Default"
                                        mouse_click_btn.pack_forget()
                                    entry.pack(side=tk.LEFT, fill=tk.Y, before=close_btn)
                                display_val = format_input_display(display_val)
                                if entry:
                                    entry.insert(0, display_val)
                            if entry:
                                entry.config(state="readonly")
                            if custom_frame:
                                custom_frame.pack(side=tk.LEFT)
                        else:
                            combo.set("Custom")
                    else:
                        combo.set(current_val)
                        if custom_frame:
                            custom_frame.pack_forget()
                        if mouse_click_btn:
                            mouse_click_btn._mouse_click_token = "Default"
                            mouse_click_btn.pack_forget()
                        if mode_var and mode_btn:
                            mode_var.set("Hold")
                            mode_btn.config(text="Hold")
                        combo.pack(side=tk.LEFT)

        for mapping_scope in (None, "in_app_gyro_mode_mappings"):
            suffix = self._mapping_scope_suffix(mapping_scope)
            for key in ["l_joystick", "r_joystick"]:
                attr_key = self._mapping_attr(key, suffix)
                combo = getattr(self, f"{attr_key}_combo", None)
                custom_frame = getattr(self, f"{attr_key}_custom_frame", None)
                custom_btn = getattr(self, f"{attr_key}_custom_btn", None)
                scroll_mode_btn = getattr(self, f"{attr_key}_scroll_mode_btn", None)
                scroll_activation_var = getattr(self, f"{attr_key}_scroll_activation_var", None)
                if not combo:
                    continue
                current_val = CONFIG.get_mapping_setting_scoped(key, "Default", mapping_scope)
                if current_val in ("Custom", "Mouse", "Scroll Wheel"):
                    combo.set(current_val)
                    combo.pack_forget()
                    if custom_btn:
                        custom_btn.config(text=current_val)
                    if scroll_mode_btn:
                        if current_val == "Scroll Wheel":
                            if scroll_activation_var:
                                scroll_activation_var.set(CONFIG.get_joystick_setting_scoped(key, "scroll_activation", "Hold", mapping_scope))
                            scroll_mode_btn.config(text=CONFIG.get_joystick_setting_scoped(key, "scroll_activation", "Hold", mapping_scope))
                            scroll_mode_btn.pack(side=tk.LEFT, padx=(0, int(2 * scaling_factor)), fill=tk.Y, before=custom_btn)
                        else:
                            scroll_mode_btn.pack_forget()
                    if custom_frame:
                        custom_frame.pack(side=tk.LEFT)
                else:
                    combo.set(current_val if current_val in JOYSTICK_OPTIONS else "Default")
                    if scroll_mode_btn:
                        scroll_mode_btn.pack_forget()
                    if custom_frame:
                        custom_frame.pack_forget()
                    combo.pack(side=tk.LEFT)
                    
        if hasattr(self, 'gc_trigger_combo'):
            try:
                idx = self.gc_trigger_values.index(CONFIG.gc_trigger_mode)
                self.gc_trigger_combo.set(self.gc_trigger_labels[idx])
            except ValueError:
                pass
            if hasattr(self, 'gc_click_map_frame'):
                if CONFIG.gc_trigger_mode == "100% at Max":
                    self.gc_click_map_frame.pack_forget()
                else:
                    self.gc_click_map_frame.pack(side=tk.LEFT, padx=(int(scaling_factor * 5), 0))
        if hasattr(self, 'gyro_gc_trigger_combo'):
            gyro_gc_mode = CONFIG.get_scoped_category_setting("gc_trigger_mode", "Hair Trigger", "in_app_gyro_mode_mappings")
            try:
                idx = self.gc_trigger_values.index(gyro_gc_mode)
                self.gyro_gc_trigger_combo.set(self.gc_trigger_labels[idx])
            except ValueError:
                pass
            if hasattr(self, 'gyro_gc_click_map_frame'):
                if gyro_gc_mode == "100% at Max":
                    self.gyro_gc_click_map_frame.pack_forget()
                else:
                    self.gyro_gc_click_map_frame.pack(side=tk.LEFT, padx=(int(scaling_factor * 5), 0))
        if hasattr(self, 'layout_switch'):
            self.layout_switch.set_value(CONFIG.abxy_mode)
        if hasattr(self, 'rumble_mode_switch'):
            self.rumble_mode_switch.set_value(CONFIG.rumble_mode)
            self.update_rumble_mode_ui(CONFIG.rumble_mode)
        if hasattr(self, 'vibration_strength_scale'):
            self.vibration_strength_scale.set(CONFIG.vibration_strength)
        if hasattr(self, 'vibration_frequency_scale'):
            self.vibration_frequency_scale.set(CONFIG.vibration_frequency)

    def update_gc_trigger_mode_setting(self, val):
        CONFIG.gc_trigger_mode = val
        CONFIG.save_config()
        # No need to restart discovery, controllers can read the setting dynamically or on reconnect

    def update_sim_mode_setting(self, val):
        self.close_joystick_custom_popup()
        # 1. 霈??(Removed load_config to prevent async save race condition)
        
        old_mode = getattr(CONFIG, "simulation_mode", "Xbox One")
        
        if hasattr(CONFIG, 'active_profile') and CONFIG.active_profile in CONFIG.profiles:
            CONFIG.profiles[CONFIG.active_profile]["simulation_mode"] = val
        
        if old_mode == val:
            CONFIG.save_config()
            return
            
        CONFIG.simulation_mode = val
        driver_type = getattr(CONFIG, "driver_type", "WinUHid")
        if driver_type == "ViGEmBus":
            CONFIG.vigembus_sim_mode = val
        elif driver_type == "USBIP":
            CONFIG.usbip_sim_mode = val
        else:
            CONFIG.winuhid_sim_mode = val
            
        success = True
        reverted_vcs = []
        if hasattr(self, 'current_controllers'):
            try:
                for vc in self.current_controllers:
                    if vc is not None:
                        vc.set_mode(val)
                        reverted_vcs.append(vc)
            except Exception as e:
                logger.error(f"Failed to switch emulation mode: {e}")
                success = False
                
        if not success:
            # Revert CONFIG memory values by reloading from disk
            CONFIG.load_config()
            # Revert set_mode on already switched controllers
            for vc in reverted_vcs:
                if vc is not None:
                    try:
                        vc.set_mode(old_mode)
                    except Exception:
                        pass
            # Revert the UI switch
            self.sim_mode_switch.set_value(old_mode)
        else:
            # 摮?
            CONFIG.save_config()
            self.update_dynamic_rumble_mode_options()

        self.close_joystick_custom_popup()
        self.close_in_app_gyro_popup()
        self.refresh_joycon_ir_sensor_buttons()
        self._refresh_mapping_comboboxes()
        self.force_refresh_player_slots()

    def _revert_from_switch2_pro(self):
        default_mode = "PS4" if getattr(CONFIG, "driver_type", "WinUHid") == "ViGEmBus" else "PS5"
        CONFIG.simulation_mode = default_mode
        if getattr(CONFIG, "driver_type", "WinUHid") == "ViGEmBus":
            CONFIG.vigembus_sim_mode = default_mode
        else:
            CONFIG.winuhid_sim_mode = default_mode
        self.sim_mode_switch.set_value(default_mode)
        CONFIG.save_config()
        self._refresh_mapping_comboboxes()
        self.force_refresh_player_slots()

    def update_layout_setting(self, val):
        CONFIG.abxy_mode = val
        self.on_setting_changed()

    def update_vibration_strength(self, val):
        try:
            CONFIG.vibration_strength = int(float(val))
            CONFIG.save_config()
        except Exception as e:
            logger.error(f"Failed to save vibration strength setting: {e}")

    def update_vibration_frequency(self, val):
        try:
            CONFIG.vibration_frequency = int(float(val))
            CONFIG.save_config()
        except Exception as e:
            logger.error(f"Failed to save vibration frequency setting: {e}")

    def update_rumble_mode_setting(self, val):
        CONFIG.rumble_mode = val
        CONFIG.save_config()
        self.update_rumble_mode_ui(val)
        self.vibration_strength_scale.set(CONFIG.vibration_strength)
        self.vibration_frequency_scale.set(CONFIG.vibration_frequency)

    def update_dynamic_rumble_mode_options(self):
        if not hasattr(self, 'rumble_mode_switch'):
            return
            
        driver_type = getattr(CONFIG, "driver_type", "WinUHid")
        sim_mode = getattr(CONFIG, "simulation_mode", "Xbox One")
        current_rumble = getattr(CONFIG, "rumble_mode", "Xbox")
        allowed_values = ["Xbox", "Switch"]

        if current_rumble not in allowed_values:
            current_rumble = "Xbox"
            CONFIG.rumble_mode = current_rumble
            CONFIG.save_config()

        # These buttons occupy the same Rumble Mode position and are mutually
        # exclusive by the active emulation transport.
        if hasattr(self, 'audio_haptics_button'):
            self.audio_haptics_button.pack_forget()
        if hasattr(self, 'impulse_trigger_button'):
            self.impulse_trigger_button.pack_forget()
            
        if driver_type == "WinUHid" and sim_mode == "Xbox One":
            self.rumble_mode_switch.update_options(["Xbox", "Switch"], ["Xbox", "Switch"], current_rumble)
            self.impulse_trigger_button.pack(side=tk.LEFT, after=self.rumble_mode_switch, padx=(int(10 * scaling_factor), 0))
        else:
            self.rumble_mode_switch.update_options(["Xbox", "Switch"], ["Xbox", "Switch"], current_rumble)

        if hasattr(self, 'vibration_frequency_label') and hasattr(self, 'vibration_frequency_scale'):
            self.update_rumble_mode_ui(current_rumble)
        if hasattr(self, 'vibration_strength_scale'):
            self.vibration_strength_scale.set(CONFIG.vibration_strength)
        if hasattr(self, 'vibration_frequency_scale'):
            self.vibration_frequency_scale.set(CONFIG.vibration_frequency)

    def update_rumble_mode_ui(self, mode):
        if hasattr(self, 'row_vibration_freq') and hasattr(self, 'row_vibration_delay'):
            if mode == "Switch":
                self.row_vibration_freq.pack_forget()
            else:
                self.row_vibration_freq.pack(side=tk.TOP, fill=tk.X, pady=int(4 * scaling_factor), before=self.row_vibration_delay)
        elif hasattr(self, 'vibration_frequency_label') and hasattr(self, 'vibration_frequency_scale'):
            if mode == "Switch":
                self.vibration_frequency_label.pack_forget()
                self.vibration_frequency_scale.pack_forget()
            elif hasattr(self, 'delay_label'):
                self.vibration_frequency_label.pack(side=tk.LEFT, before=self.delay_label, padx=(int(20 * scaling_factor), int(2 * scaling_factor)))
                self.vibration_frequency_scale.pack(side=tk.LEFT, before=self.delay_label)

    def update_startup_setting(self, val):
        CONFIG.open_when_startup = val
        set_startup(val)
        CONFIG.save_config()
        if hasattr(self, 'startup_var') and self.startup_var is not None:
            self.startup_var.set(val)
        if hasattr(self, 'startup_btn') and self.startup_btn and self.startup_btn.winfo_exists():
            update_toggle_button(self.startup_btn, val, "Run At Startup")

    def _confirm_power_saving_mode(self, target):
        suppressed = bool(getattr(
            CONFIG, f"power_saving_{target.lower()}_warning_suppressed", False))
        if suppressed:
            return True
        messages = {
            "Auto": (
                "Auto mode reduces idle CPU power use by requesting precision timing only "
                "while it is needed.\n\n"
                "Buttons, sticks, triggers and motion controls remain fully enabled.\n\n"
                "HD Rumble, Audio Haptics and Impulse Trigger feedback may be less consistent, "
                "delayed, interrupted or occasionally lost."
            ),
            "Full": (
                "Full mode prioritizes the lowest CPU power use.\n\n"
                "Buttons, sticks, triggers and non-motion mappings remain enabled.\n\n"
                "Vibration output and motion-based and mouse features are disabled, including Gyro Pass-Through, In-app Gyro, "
                "DJG, IR Mouse, and Joystick Mouse.\n\n"
                "Periodic ESP32 and Wired/HidHide scanner will be disabled.\n\n"
                "Automatic controller scanning pauses after 1 Pro/NSO GCN controller "
                "or 2 Joy-Con controllers are connected. Existing controller connections "
                "will not be disconnected."
            ),
        }
        owner = (self.settings_window if hasattr(self, "settings_window")
                 and self.settings_window is not None
                 and self.settings_window.winfo_exists()
                 and self.settings_window.winfo_viewable()
                 else self.root)
        dialog = tk.Toplevel(owner)
        dialog.withdraw()
        dialog.title(f"PC Battery Saver: {target}")
        dialog.resizable(False, False)
        dialog.config(bg=background_color)
        dialog.transient(owner)
        apply_window_dark_theme_and_icon(dialog, background_color)
        dialog_height = 300 if target == "Auto" else 390
        self.center_window_on_root(
            dialog, int(540 * scaling_factor), int(dialog_height * scaling_factor), owner=owner)
        result = {"proceed": False}
        suppress_var = tk.BooleanVar(value=False)
        tk.Label(dialog, text=messages[target], fg="white", bg=background_color,
                 font=scale_font(("Arial", 11, "bold")), justify=tk.CENTER,
                 wraplength=int(480 * scaling_factor)).pack(
                     padx=int(24 * scaling_factor), pady=(int(24 * scaling_factor), int(12 * scaling_factor)))
        tk.Checkbutton(dialog, text="Do not show again.", variable=suppress_var,
                       bg=background_color, fg="white", activebackground=background_color,
                       activeforeground="white", selectcolor=button_gray,
                       font=scale_font(("Arial", 10))).pack(pady=(0, int(12 * scaling_factor)))
        buttons = tk.Frame(dialog, bg=background_color)
        buttons.pack(pady=(0, int(18 * scaling_factor)))
        def close(proceed):
            result["proceed"] = bool(proceed)
            if proceed and suppress_var.get():
                setattr(CONFIG, f"power_saving_{target.lower()}_warning_suppressed", True)
            try:
                dialog.grab_release()
            except Exception:
                pass
            dialog.destroy()
            if owner and owner != self.root and hasattr(owner, "winfo_exists") and owner.winfo_exists():
                try:
                    owner.lift()
                    owner.focus_set()
                except Exception:
                    pass
        for text, proceed in (("Proceed", True), ("Cancel", False)):
            tk.Button(buttons, text=text, bg=button_gray, fg=text_color,
                      bd=0, relief=tk.FLAT, width=9,
                      font=scale_font(("Arial", 10, "bold")),
                      command=lambda value=proceed: close(value)).pack(
                          side=tk.LEFT, padx=int(6 * scaling_factor))
        dialog.protocol("WM_DELETE_WINDOW", lambda: close(False))
        dialog.update_idletasks()
        dialog.deiconify()
        dialog.lift(owner)
        dialog.focus_force()
        try:
            dialog.grab_set()
        except Exception:
            pass
        self.root.wait_window(dialog)
        return result["proceed"]

    def cycle_power_saving_mode(self):
        import power_saving
        current = getattr(CONFIG, "power_saving_mode", "Off")
        target = "Off" if current != "Off" else "Auto"
        if target != "Off" and not self._confirm_power_saving_mode(target):
            return
        previous_mode = current
        CONFIG.power_saving_mode = target
        CONFIG.save_config()
        power_saving.notify_mode_changed()
        self._apply_power_saving_ui_priority(target)
        request_wired_rescan("power_saving_mode_changed", manual=False)
        for vc in getattr(self, "current_controllers", ()) or ():
            wake_update = getattr(vc, "_update_wake", None)
            if wake_update is not None:
                wake_update.set()
            for controller in getattr(vc, "controllers", ()) or ():
                controller._poke_rumble_scheduler()
                apply_mode = getattr(controller, "on_power_saving_mode_changed", None)
                if callable(apply_mode):
                    apply_mode(previous_mode, target)
        if hasattr(self, 'power_saving_var') and self.power_saving_var is not None:
            self.power_saving_var.set(target != "Off")
        if hasattr(self, "power_saving_btn") and self.power_saving_btn and self.power_saving_btn.winfo_exists():
            update_toggle_button(self.power_saving_btn, target != "Off", "Power Saving")

    def _apply_power_saving_ui_priority(self, mode):
        # Prioritize only Tk's main thread while it is runnable. Thread priority
        # does not create a periodic wake source or request precision timing.
        if mode in ("Auto", "Full"):
            _set_current_thread_priority(1)  # THREAD_PRIORITY_ABOVE_NORMAL
        elif self._ui_base_thread_priority is not None:
            _set_current_thread_priority(self._ui_base_thread_priority)

    def update_minimized_setting(self, val):
        CONFIG.start_minimized = val
        CONFIG.save_config()
        if hasattr(self, 'minimized_var') and self.minimized_var is not None:
            self.minimized_var.set(val)
        if hasattr(self, 'minimized_btn') and self.minimized_btn and self.minimized_btn.winfo_exists():
            update_toggle_button(self.minimized_btn, val, "Start Minimized")

    def _schedule_wired_device_change_rescan(self, reason="device_arrival", candidate_path=None):
        if not bool(getattr(CONFIG, "wired_auto_scan_enabled", getattr(CONFIG, "wired_usb_enabled", True))):
            return
        pending = getattr(self, "_wired_device_change_after_id", None)
        if pending is not None:
            try:
                self.root.after_cancel(pending)
            except Exception:
                pass
        self._wired_device_change_after_id = self.root.after(
            500,
            lambda r=reason, p=candidate_path: request_wired_rescan(r, candidate_path=p),
        )

    def poll_wired_device_events(self):
        if getattr(self, 'is_quitting', False):
            return
        # Keep the latest of each kind: the queue now carries wired-controller events and
        # Bluetooth-radio events, and collapsing to a single "latest" would let one kind
        # swallow the other.
        latest = {}
        try:
            q = getattr(self, "wired_device_event_queue", None)
            if q is not None:
                while True:
                    try:
                        event = q.get_nowait()
                    except queue.Empty:
                        break
                    latest[event.get("kind", "wired")] = event
        except Exception:
            latest = {}

        wired_event = latest.get("wired")
        if wired_event:
            self._schedule_wired_device_change_rescan(
                wired_event.get("reason", "device_arrival"),
                wired_event.get("path"),
            )

        if latest.get("bluetooth_radio"):
            try:
                from discoverer import notify_bluetooth_radio_changed
                notify_bluetooth_radio_changed()
            except Exception:
                logger.debug("Bluetooth radio change notification failed", exc_info=True)

        try:
            self.root.after(250, self.poll_wired_device_events)
        except Exception:
            pass

    def close_wired_pro_controller_settings_popup(self):
        if hasattr(self, "wired_pro_settings_window") and self.wired_pro_settings_window is not None and self.wired_pro_settings_window.winfo_exists():
            self.wired_pro_settings_window.destroy()
        self.wired_pro_settings_window = None
        popup = getattr(self, "wired_pro_settings_popup", None)
        if popup is not None and popup.winfo_exists():
            popup.destroy()
        self.wired_pro_settings_popup = None
        self.wired_pro_settings_popup_anchor = None
        bind_id = getattr(self, "wired_pro_settings_popup_bind_id", None)
        if bind_id:
            try:
                self.root.unbind("<ButtonPress>", bind_id)
            except Exception:
                pass
            self.wired_pro_settings_popup_bind_id = None

    def custom_askstring(self, title, prompt, initialvalue=""):
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.configure(bg=background_color)
        dialog.transient(self.root)
        dialog.grab_set()
        apply_window_dark_theme_and_icon(dialog, background_color)
        
        w = int(350 * scaling_factor)
        h = int(150 * scaling_factor)
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (w // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (h // 2)
        dialog.geometry(f"{w}x{h}+{x}+{y}")
        
        tk.Label(dialog, text=prompt, font=scale_font(("Arial", 11, "bold")), bg=background_color, fg=text_color).pack(pady=(int(15*scaling_factor), int(5*scaling_factor)))
        
        entry = tk.Entry(dialog, font=scale_font(("Arial", 11, "bold")), bg=button_gray, fg="white", insertbackground="white", justify="center")
        entry.pack(padx=int(20*scaling_factor), fill=tk.X)
        if initialvalue:
            entry.insert(0, initialvalue)
            entry.select_range(0, tk.END)
        
        result = [None]
        def on_ok(event=None):
            result[0] = entry.get()
            dialog.destroy()
        def on_cancel(event=None):
            dialog.destroy()
            
        entry.bind("<Return>", on_ok)
        entry.bind("<Escape>", on_cancel)
        
        btn_frame = tk.Frame(dialog, bg=background_color)
        btn_frame.pack(pady=int(15*scaling_factor))
        tk.Button(btn_frame, text="OK", font=scale_font(("Arial", 11, "bold")), bg=button_gray, fg="white", width=8, relief=tk.FLAT, bd=0, command=on_ok).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Cancel", font=scale_font(("Arial", 11, "bold")), bg=button_gray, fg="white", width=8, relief=tk.FLAT, bd=0, command=on_cancel).pack(side=tk.LEFT, padx=5)
        
        entry.focus_set()
        self.root.wait_window(dialog)
        return result[0]

    def custom_messagebox(self, title, message, type="info", confirm_text="Yes", cancel_text="No"):
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.configure(bg=background_color)
        dialog.transient(self.root)
        dialog.grab_set()
        apply_window_dark_theme_and_icon(dialog, background_color)
        
        w = int(360 * scaling_factor)
        h = int(150 * scaling_factor)
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (w // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (h // 2)
        dialog.geometry(f"{w}x{h}+{x}+{y}")
        
        tk.Label(dialog, text=message, font=scale_font(("Arial", 11, "bold")), bg=background_color, fg=text_color, wraplength=int(340*scaling_factor), justify="center").pack(pady=(int(20*scaling_factor), int(10*scaling_factor)), expand=True)
        
        result = [None]
        btn_frame = tk.Frame(dialog, bg=background_color)
        btn_frame.pack(pady=(0, int(15*scaling_factor)))
        
        def set_res(res):
            result[0] = res
            dialog.destroy()
            
        if type == "yesno":
            make_rounded_button(
                btn_frame, text=confirm_text, width=86, height=28, radius=6,
                bg_color=button_gray, hover_color="#5A5A5A", press_color="#3A3A3A",
                parent_bg=background_color, command=lambda: set_res(True),
                font=scale_font(("Arial", 11, "bold"))
            ).pack(side=tk.LEFT, padx=5)
            make_rounded_button(
                btn_frame, text=cancel_text, width=86, height=28, radius=6,
                bg_color=button_gray, hover_color="#5A5A5A", press_color="#3A3A3A",
                parent_bg=background_color, command=lambda: set_res(False),
                font=scale_font(("Arial", 11, "bold"))
            ).pack(side=tk.LEFT, padx=5)
        else:
            make_rounded_button(
                btn_frame, text="OK", width=86, height=28, radius=6,
                bg_color=button_gray, hover_color="#5A5A5A", press_color="#3A3A3A",
                parent_bg=background_color, command=lambda: set_res(True),
                font=scale_font(("Arial", 11, "bold"))
            ).pack()
            
        dialog.bind("<Return>", lambda e: set_res(True))
        if type == "yesno":
            dialog.bind("<Escape>", lambda e: set_res(False))
        else:
            dialog.bind("<Escape>", lambda e: set_res(True))
            
        self.root.wait_window(dialog)
        return result[0]

    def refresh_profile_switching_combo_trigger_ui(self):
        pass

    def choose_app_path(self):
        initial_dir = os.environ.get("ProgramFiles") or os.path.expanduser("~")
        self.app_profile_poll_suspended = True
        try:
            return filedialog.askopenfilename(
                parent=self.root,
                title="Choose App",
                initialdir=initial_dir,
                filetypes=[("Applications", "*.exe"), ("All files", "*.*")],
            )
        finally:
            self.app_profile_poll_suspended = False

    def get_foreground_app_path(self):
        try:
            import win32process
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if not hwnd:
                return ""

            _thread_id, pid = win32process.GetWindowThreadProcessId(hwnd)
            if not pid:
                return ""
            self._last_foreground_pid = pid

            process_handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not process_handle:
                return ""

            try:
                size = wintypes.DWORD(32768)
                buffer = ctypes.create_unicode_buffer(size.value)
                if ctypes.windll.kernel32.QueryFullProcessImageNameW(process_handle, 0, buffer, ctypes.byref(size)):
                    return normalize_app_path(buffer.value)
            finally:
                ctypes.windll.kernel32.CloseHandle(process_handle)
        except Exception as e:
            logger.debug(f"Failed to read foreground app path: {e}")
        return ""

    def is_game_process_running(self, exe_name):
        """Checks if a game executable process is actively running on the system."""
        if not exe_name:
            return False
        exe_lower = exe_name.lower().strip()

        # 1. Check cached PID first (ultra-fast check)
        cached_pid = getattr(self, "_game_pids", {}).get(exe_lower)
        if cached_pid:
            try:
                h = ctypes.windll.kernel32.OpenProcess(0x0400, False, cached_pid)
                if h:
                    code = wintypes.DWORD()
                    ret = ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
                    ctypes.windll.kernel32.CloseHandle(h)
                    if ret != 0 and code.value == 259: # STILL_ACTIVE
                        return True
            except Exception:
                pass

        # 2. Snapshot scan fallback if PID expired or not yet cached
        try:
            hSnap = ctypes.windll.kernel32.CreateToolhelp32Snapshot(0x02, 0)
            if hSnap and hSnap != -1:
                class PROCESSENTRY32(ctypes.Structure):
                    _fields_ = [
                        ('dwSize', wintypes.DWORD),
                        ('cntUsage', wintypes.DWORD),
                        ('th32ProcessID', wintypes.DWORD),
                        ('th32DefaultHeapID', ctypes.c_size_t),
                        ('th32ModuleID', wintypes.DWORD),
                        ('cntThreads', wintypes.DWORD),
                        ('th32ParentProcessID', wintypes.DWORD),
                        ('pcPriClassBase', ctypes.c_long),
                        ('dwFlags', wintypes.DWORD),
                        ('szExeFile', ctypes.c_char * 260)
                    ]
                pe = PROCESSENTRY32()
                pe.dwSize = ctypes.sizeof(PROCESSENTRY32)
                found_pid = None
                if ctypes.windll.kernel32.Process32First(hSnap, ctypes.byref(pe)):
                    while True:
                        if pe.szExeFile.decode('ansi', errors='ignore').lower() == exe_lower:
                            found_pid = pe.th32ProcessID
                            break
                        if not ctypes.windll.kernel32.Process32Next(hSnap, ctypes.byref(pe)):
                            break
                ctypes.windll.kernel32.CloseHandle(hSnap)
                if found_pid:
                    if not hasattr(self, "_game_pids"):
                        self._game_pids = {}
                    self._game_pids[exe_lower] = found_pid
                    return True
        except Exception as e:
            logger.debug(f"is_game_process_running scan failed: {e}")
        return False

    def save_active_profile_runtime_settings(self):
        if hasattr(CONFIG, 'active_profile') and CONFIG.active_profile in CONFIG.profiles:
            CONFIG.profiles[CONFIG.active_profile]["driver_type"] = getattr(CONFIG, "driver_type", "WinUHid")
            CONFIG.profiles[CONFIG.active_profile]["simulation_mode"] = getattr(CONFIG, "simulation_mode", "Xbox One")

    def switch_to_profile(self, profile_name):
        if not profile_name or profile_name == getattr(CONFIG, "active_profile", ""):
            return False
        if profile_name not in CONFIG.profiles:
            return False

        if hasattr(self, 'profile_apply_timer') and self.profile_apply_timer:
            self.root.after_cancel(self.profile_apply_timer)
            self.profile_apply_timer = None
        self.pending_profile = None
        self.save_active_profile_runtime_settings()

        if CONFIG.switch_profile(profile_name):
            self._set_profile_button_text()
            self.app_profile_switching = True
            try:
                self.apply_profile_switch()
            finally:
                self.app_profile_switching = False
            self.close_joystick_custom_popup()
            self.close_in_app_gyro_popup()
            self.refresh_joycon_ir_sensor_buttons()
            # Close the popup last, after the UI has been updated, and without forcing
            # an intermediate repaint of it. Refreshing/painting the popup right before
            # destroying it (and closing before the main UI updated) caused the brief
            # ghosting during the switch.
            if getattr(self, "profile_popup", None) is not None and self.profile_popup.winfo_exists():
                self.close_profile_popup()
            return True
        return False

    def poll_assigned_app_focus(self):
        if not getattr(self, "root", None) or getattr(self, "is_quitting", False):
            return

        IGNORED_SYSTEM_PROCESSES = {
            "explorer.exe", "dwm.exe", "searchhost.exe", "shellexperiencehost.exe",
            "taskmgr.exe", "lockapp.exe", "applicationframehost.exe", "startmenuexperiencehost.exe",
            "switch2proconnect.exe", "switch2proconnect_v1.0.exe", "switch2proconnect_v1.0_(shfr_ui_mod).exe", "switch2proconnect_v2.8.exe", "switch2proconnect_v2.8_(shfr_ui_mod).exe", "switch2proconnect_v2.8_shfr_ui_mod.exe",
            "switch2connect.exe", "switch2connect_v2.8.exe", "switch2connect_v2.8_(shfr_ui_mod).exe", "switch2connect_v2.8_shfr_ui_mod.exe", "switch2connect_v2.8_(sheeshfr_modded).exe", "python.exe", "pythonw.exe",
            "wabbajack.exe", "cmd.exe", "powershell.exe", "conhost.exe", "textinputhost.exe", "systemsettings.exe",
            "openwith.exe", "pickerhost.exe", "idle.exe"
        }

        try:
            if not self.app_profile_poll_suspended and not self.app_profile_switching:
                foreground_app_path = self.get_foreground_app_path()

                # Automatic per-game back-button & mapping auto-detection
                from config import AUTOBLOCK_NON_GAMING_PROCESSES, is_blocked_process
                if foreground_app_path:
                    exe_name = os.path.basename(foreground_app_path).lower().strip()
                    if not is_blocked_process(exe_name) and exe_name not in IGNORED_SYSTEM_PROCESSES:
                        if hasattr(CONFIG, "game_mappings") and isinstance(CONFIG.game_mappings, dict) and exe_name in CONFIG.game_mappings:
                            # A configured game gained focus!
                            fg_pid = getattr(self, "_last_foreground_pid", None)
                            if not hasattr(self, "_game_pids"):
                                self._game_pids = {}
                            if fg_pid:
                                self._game_pids[exe_name] = fg_pid

                            if not hasattr(self, "recent_game_order"):
                                self.recent_game_order = []
                            if exe_name in self.recent_game_order:
                                self.recent_game_order.remove(exe_name)
                            self.recent_game_order.append(exe_name)

                            if not CONFIG.game_mappings[exe_name].get("path"):
                                CONFIG.game_mappings[exe_name]["path"] = foreground_app_path

                # Maintain recent_game_order: keep only games whose process is still actively running
                if not hasattr(self, "recent_game_order"):
                    self.recent_game_order = []

                alive_games = []
                for g_exe in self.recent_game_order:
                    if self.is_game_process_running(g_exe):
                        alive_games.append(g_exe)
                self.recent_game_order = alive_games

                # If any configured game is open, stay on the latest running game
                if self.recent_game_order:
                    detected_game = self.recent_game_order[-1]
                    detected_name = CONFIG.game_mappings.get(detected_game, {}).get("display_name") or detected_game
                else:
                    # All game threads have closed -> revert to Default
                    detected_game = None
                    detected_name = None

                # If in live auto-detect mode (not locking a preset), update active game
                if getattr(CONFIG, "selected_game_preset", None) is None:
                    if getattr(CONFIG, "active_game_exe", None) != detected_game:
                        CONFIG.active_game_exe = detected_game
                        CONFIG.active_game_name = detected_name
                        CONFIG._bump_settings_generation()
                        self._set_profile_button_text()
                        self._refresh_mapping_comboboxes()

                if foreground_app_path:
                    _f_exe = os.path.basename(foreground_app_path).lower().strip()
                    if not (_f_exe.startswith("switch2proconnect") or _f_exe.startswith("switch2connect") or _f_exe in ("python.exe", "pythonw.exe")):
                        self.last_external_app_path = foreground_app_path
                        self.last_external_app_exe = _f_exe

                self.last_foreground_app_path = foreground_app_path
        except Exception as e:
            logger.debug(f"Assigned app focus poll failed: {e}")
        finally:
            try:
                self.root.after(500, self.poll_assigned_app_focus)
            except Exception:
                pass

    def _profile_sort_key(self, s):
        import re
        tokens = re.findall(r'[a-zA-Z]+|\d+|[^a-zA-Z\d]+', s)
        key = []
        for t in tokens:
            if t.isalpha():
                key.append((0, t.lower()))
            elif t.isdigit():
                key.append((1, int(t)))
            else:
                key.append((2, t))
        return key

    def get_sorted_profiles(self):
        return sorted(
            list(CONFIG.profiles.keys()),
            key=lambda name: (0 if CONFIG.profiles.get(name, {}).get("change_profile_list", False) else 1, self._profile_sort_key(name))
        )

    def _change_list_profiles(self):
        return [
            name for name in self.get_sorted_profiles()
            if CONFIG.profiles.get(name, {}).get("change_profile_list", False)
        ]

    def _show_profile_selection_notification(self, manual):
        lst = self._change_list_profiles()
        if not lst:
            return
        sel = self.pending_profile if self.pending_profile in lst else lst[0]
        idx = lst.index(sel)
        prev_name = lst[(idx - 1) % len(lst)]
        next_name = lst[(idx + 1) % len(lst)]
        layout = getattr(CONFIG, "abxy_mode", "Xbox")
        auto_close = None if manual else 3000
        # Widen the window to fit the longest profile name in the change list.
        try:
            sel_font = tkFont.Font(font=scale_font(("Segoe UI", 11, "bold")))
            name_px = max((sel_font.measure(n) for n in lst), default=0)
        except Exception:
            name_px = 0
        self.calibration_overlay.show_profile_selection(prev_name, sel, next_name, manual, layout, auto_close, name_px)

    def on_cycle_profile(self):
        if not hasattr(CONFIG, 'active_profile') or not CONFIG.profiles:
            return

        # Execute on main thread to avoid Tkinter threading errors
        if threading.current_thread() != threading.main_thread():
            self.root.after(0, self.on_cycle_profile)
            return

        sorted_profiles = self._change_list_profiles()
        if not sorted_profiles:
            return

        # Initialize pending profile if not set
        if not hasattr(self, 'pending_profile') or not self.pending_profile:
            self.pending_profile = CONFIG.active_profile

        try:
            curr_idx = sorted_profiles.index(self.pending_profile)
            next_idx = (curr_idx + 1) % len(sorted_profiles)
        except ValueError:
            next_idx = 0

        self.pending_profile = sorted_profiles[next_idx]

        import utils
        manual = getattr(CONFIG, "change_profile_mode", "Manual") == "Manual"

        # Cancel any pending auto-apply timer
        if hasattr(self, 'profile_apply_timer') and self.profile_apply_timer:
            self.root.after_cancel(self.profile_apply_timer)
            self.profile_apply_timer = None

        if manual:
            # Enter selection mode: pause virtual output, wait for A (confirm) / B (cancel).
            utils.profile_selection_active = True
            self._show_profile_selection_notification(True)
        else:
            # Auto: show the selection and auto-apply after a second of inactivity.
            utils.profile_selection_active = False
            self._show_profile_selection_notification(False)
            self.profile_apply_timer = self.root.after(1000, self.apply_pending_profile)

    def on_profile_nav(self, direction):
        if threading.current_thread() != threading.main_thread():
            self.root.after(0, self.on_profile_nav, direction)
            return
        import utils
        if not utils.profile_selection_active:
            return
        # Debounce so a single flick / Dpad tap doesn't advance multiple steps even
        # when reported by both controllers of a merged pair.
        now = time.perf_counter()
        if now - getattr(self, "_last_profile_nav_time", 0.0) < 0.18:
            return
        self._last_profile_nav_time = now
        lst = self._change_list_profiles()
        if not lst:
            return
        sel = self.pending_profile if self.pending_profile in lst else lst[0]
        idx = lst.index(sel)
        self.pending_profile = lst[(idx + direction) % len(lst)]
        self._show_profile_selection_notification(True)

    def on_profile_confirm(self):
        if threading.current_thread() != threading.main_thread():
            self.root.after(0, self.on_profile_confirm)
            return
        import utils
        if not utils.profile_selection_active:
            return
        utils.profile_selection_active = False
        self.calibration_overlay.close_profile_selection()
        target = getattr(self, "pending_profile", None)
        self.pending_profile = None
        if target and target != getattr(CONFIG, "active_profile", ""):
            self.switch_to_profile(target)

    def on_profile_cancel(self):
        if threading.current_thread() != threading.main_thread():
            self.root.after(0, self.on_profile_cancel)
            return
        import utils
        utils.profile_selection_active = False
        self.calibration_overlay.close_profile_selection()
        self.pending_profile = None

    def on_profile_combo_switch(self, profile_name):
        if threading.current_thread() != threading.main_thread():
            self.root.after(0, lambda p=profile_name: self.on_profile_combo_switch(p))
            return
        if profile_name not in CONFIG.profiles:
            return
        if profile_name == getattr(CONFIG, "active_profile", ""):
            return
        import utils
        if self.switch_to_profile(profile_name):
            self.root.after(0, lambda p=profile_name: utils.show_notification("Profile Switched", f"Current Profile: {p}"))
        
    def apply_pending_profile(self):
        self.profile_apply_timer = None
        if not hasattr(self, 'pending_profile') or not self.pending_profile:
            return
            
        if self.pending_profile == getattr(CONFIG, 'active_profile', ""):
            return # No change
            
        self.switch_to_profile(self.pending_profile)
            
        self.pending_profile = None

    def apply_profile_switch(self):
        self.close_joystick_custom_popup()
        new_profile_name = getattr(CONFIG, 'active_profile', "")
        if not new_profile_name or new_profile_name not in CONFIG.profiles:
            return
            
        new_driver = "WinUHid"
        new_emu = "Xbox One"
        CONFIG.driver_type = "WinUHid"
        CONFIG.simulation_mode = "Xbox One"
        CONFIG.abxy_mode = "Xbox"
        if new_profile_name in CONFIG.profiles:
            CONFIG.profiles[new_profile_name]["driver_type"] = "WinUHid"
            CONFIG.profiles[new_profile_name]["simulation_mode"] = "Xbox One"
            CONFIG.profiles[new_profile_name]["abxy_mode"] = "Xbox"
        CONFIG.save_config()
            
        # 3. ???單?rofile?mu Mode (If driver changed, it was already applied, but we ensure UI is updated)
        if not driver_changed and emu_changed:
            if getattr(self, 'sim_mode_switch', None):
                self.sim_mode_switch.set_value(new_emu)
            self.update_sim_mode_setting(new_emu)
        elif getattr(self, 'sim_mode_switch', None):
            self.sim_mode_switch.set_value(new_emu)

        # Reconcile the Profile-scoped keyboard backend immediately. Controller
        # workers observe settings_generation and reconcile their mouse devices.
        keyboard_output.initialize()
        self.wake_controller_mouse_output_reconcile()
        self.refresh_profile_switching_combo_trigger_ui()
        if (getattr(self, "winuhid_manager_popup", None) is not None
                and self.winuhid_manager_popup.winfo_exists()):
            self.refresh_winuhid_driver_manager()

        self.refresh_ui_for_profile()
        self.cancel_all_calibration_after_profile_switch()

    def refresh_ui_for_profile(self):
        self._set_profile_button_text()
        self._sync_active_mode_shift_mapping_ui(save=True)
        self.layout_switch.set_value(CONFIG.abxy_mode)
        self.rumble_mode_switch.set_value(getattr(CONFIG, "rumble_mode", "Xbox"))
        self.update_rumble_mode_ui(getattr(CONFIG, "rumble_mode", "Xbox"))
        self.vibration_strength_scale.set(CONFIG.vibration_strength)
        self.vibration_frequency_scale.set(CONFIG.vibration_frequency)
        if hasattr(self, "rumble_delay_entry"):
            self.rumble_delay_entry.delete(0, tk.END)
            self.rumble_delay_entry.insert(0, str(getattr(CONFIG, "rumble_delay_ms", 0)))
        self._refresh_mapping_comboboxes()
        if hasattr(self, 'gc_trigger_combo'):
            current_val = getattr(CONFIG, "gc_trigger_mode", "100% at Bump")
            try:
                idx = self.gc_trigger_values.index(current_val)
                self.gc_trigger_combo.set(self.gc_trigger_labels[idx])
            except ValueError:
                self.gc_trigger_combo.set(self.gc_trigger_labels[1])
                
            if hasattr(self, 'gc_click_map_frame'):
                if current_val == "100% at Max":
                    self.gc_click_map_frame.pack_forget()
                else:
                    self.gc_click_map_frame.pack(side=tk.LEFT, padx=(int(5 * scaling_factor), 0))

        # Update Built-in Gyro Mouse
        if hasattr(self, 'gyro_mode_switch'):
            mode_value = getattr(CONFIG, "gyro_mode", "World")
            self.gyro_mode_switch.set_value(mode_value if mode_value in ("World", "Yaw") else "World")
        if hasattr(self, 'mode_shift_switch'):
            self.mode_shift_switch.set_value(CONFIG.mode_shift_enabled)
        if hasattr(self, 'gyro_control_switch'):
            gyro_control_mode = "Steering" if getattr(CONFIG, "gyro_mode", "World") == "Roll" else getattr(CONFIG, "gyro_control_mode", "Mouse")
            self.gyro_control_switch.set_value(gyro_control_mode)
            self._update_gyro_control_visibility(gyro_control_mode)
        if hasattr(self, 'sens_scale'):
            self._updating_gyro_control_sensitivity = True
            self.sens_scale.set(self._current_gyro_control_sensitivity())
            self._updating_gyro_control_sensitivity = False
        if hasattr(self, 'stick_scale'):
            self.stick_scale.set(getattr(CONFIG, "stick_mouse_sensitivity", 20.0))
                
        # Update Gyro Passthrough Mode
        if hasattr(self, 'passthrough_mode_switch'):
            current_passthrough = getattr(CONFIG, "gyro_passthrough_mode", "Default")
            self.passthrough_mode_switch.set_value(current_passthrough)
            try:
                idx = self.passthrough_mode_switch.values.index(current_passthrough)
                self.update_passthrough_mode(current_passthrough)
            except ValueError:
                pass
                
        # Update 9-axis Assist / Horizon Lock.  The V2 pipeline and V2 Horizon are
        # derived from these two, so there is nothing else to re-sync here.
        if hasattr(self, 'stabilized_gyro_switch'):
            self.stabilized_gyro_switch.set_value(getattr(CONFIG, "gyro_passthrough_9axis_enabled", False))

        if hasattr(self, 'steam_roll_comp_switch'):
            self.steam_roll_comp_switch.set_value(getattr(CONFIG, "steam_roll_compensation", False))

        if hasattr(self, 'deadzone_scale'):
            self.deadzone_scale.set(getattr(CONFIG, "virtual_gyro_soft_deadzone", 0.0))
        if hasattr(self, 'in_app_deadzone_scale'):
            self.in_app_deadzone_scale.set(getattr(CONFIG, "in_app_gyro_soft_deadzone", 0.0))
                
        # Update Cemuhook Sensitivity
        if hasattr(self, 'cemuhook_sens_scale'):
            self.cemuhook_sens_scale.set(getattr(CONFIG, "cemuhook_sensitivity", 1))
                
        # Update DJG Settings as the last step. The DJG handlers each rebuild the
        # player area, so suppress those rebuilds and do a single one at the end to
        # avoid the player slots flashing/ghosting several times during the switch.
        self._suppress_player_slot_refresh = True
        self._player_slot_refresh_pending = False
        try:
            if hasattr(self, 'djg_enabled_switch'):
                djg_enabled = getattr(CONFIG, "djg_enabled", False)
                self.djg_enabled_switch.set_value(djg_enabled)
                self.update_djg_enabled_setting(djg_enabled)

            if hasattr(self, 'djg_dominant_var'):
                djg_dominant = getattr(CONFIG, "djg_dominant_side", "Right")
                self.djg_dominant_var.set(djg_dominant)
                if djg_dominant in ("Left", "Right") and hasattr(self, 'djg_dominant_switch'):
                    self.djg_dominant_switch.set_value(djg_dominant)
                self.update_djg_dominant_setting(djg_dominant)

            if hasattr(self, 'djg_mode_combo'):
                djg_mode = getattr(CONFIG, "djg_mode", "Single Side Toggle")
                self.djg_mode_var.set(djg_mode)
                self.update_djg_mode_setting(djg_mode)

            if hasattr(self, 'djg_activation_switch'):
                djg_activation = getattr(CONFIG, "djg_activation", "Toggle")
                self.djg_activation_switch.set_value(djg_activation)
                self.update_djg_activation_setting(djg_activation)
        finally:
            self._suppress_player_slot_refresh = False

        if getattr(self, '_player_slot_refresh_pending', False):
            self._player_slot_refresh_pending = False
            self.force_refresh_player_slots()

    def on_setting_changed(self, event=None):
        def get_mapping(key, mapping_scope=None):
            suffix = self._mapping_scope_suffix(mapping_scope)
            attr_key = self._mapping_attr(key, suffix)
            combo = getattr(self, f"{attr_key}_combo", None)
            if combo is None: return "Default"
            val = combo.get()
            if val in MOUSE_CLICK_BACK_BUTTON_TOKENS:
                curr = CONFIG.get_mapping_setting_scoped(key, "Default", mapping_scope)
                mouse_click_mapping = parse_mouse_click_mapping(curr)
                if mouse_click_mapping:
                    option_token, mode = mouse_click_mapping
                    if option_token == val:
                        return f"Custom[{mode}]:{MOUSE_CLICK_BACK_BUTTON_TOKENS[option_token]}"
                return f"Custom[Hold]:{MOUSE_CLICK_BACK_BUTTON_TOKENS[val]}"
            if val in ("Custom", GYRO_LOCK_LABEL, MODE_SHIFT_LABEL, IN_APP_GYRO_LABEL):
                curr = CONFIG.get_mapping_setting_scoped(key, "Default", mapping_scope)
                if curr.startswith("Custom"):
                    return curr
            return val

        # Only write back the scope the user is actually editing. The other
        # scope's config is already kept in sync at the config level (In-app
        # Gyro cross-mapping) and its hidden combos hold stale values, so
        # writing them back here would clobber the just-applied sync.
        active_scope = "in_app_gyro_mode_mappings" if getattr(self, "settings_active_tab", None) == "in_app_gyro_mode_mapping" else None
        for mapping_scope in (active_scope,):
            suffix = self._mapping_scope_suffix(mapping_scope)
            for key in [
                "home", "capt", "c", "plus", "minus",
                "a", "b", "x", "y",
                "up", "down", "left", "right",
                "zl", "l", "zr", "r",
                "l_stk", "r_stk",
                "gl", "gr", "sll", "srl", "slr", "srr",
                "gc_l_click", "gc_r_click"
            ]:
                attr_key = self._mapping_attr(key, suffix)
                if getattr(self, f"{attr_key}_combo", None) is not None:
                    CONFIG.set_mapping_setting_scoped(key, get_mapping(key, mapping_scope), mapping_scope)
            for key in ["l_joystick", "r_joystick"]:
                attr_key = self._mapping_attr(key, suffix)
                combo = getattr(self, f"{attr_key}_combo", None)
                if combo is not None:
                    CONFIG.set_mapping_setting_scoped(key, combo.get(), mapping_scope)
        if hasattr(self, 'gc_trigger_combo'):
            pass # Value is already saved by the Combobox command
        CONFIG.save_config()
        self._refresh_mapping_comboboxes()
        self.root.focus_set()

    def toggle_mock_controller(self):
        from discoverer import VIRTUAL_CONTROLLERS
        self.debug_mock_controller = not getattr(self, "debug_mock_controller", False)
        state_str = "ON" if self.debug_mock_controller else "OFF"
        btn_bg = highlight_color if self.debug_mock_controller else button_gray
        if hasattr(self, "debug_btn") and self.debug_btn and self.debug_btn.winfo_exists():
            self.debug_btn.config(text=f"Debug: Pro Pad [{state_str}]", bg=btn_bg)
        if hasattr(self, "settings_debug_btn") and self.settings_debug_btn and self.settings_debug_btn.winfo_exists():
            update_toggle_button(self.settings_debug_btn, self.debug_mock_controller, "Controller Connected")
        self.update(list(VIRTUAL_CONTROLLERS))

    def update(self, controllers_info):
        if getattr(self, "debug_mock_controller", False):
            controllers_info = [
                MockVirtualController(1, "pro", 3.9),
            ]
        if self.main_frame is None:
            self.main_frame = tk.Frame(self.left_column if hasattr(self, 'left_column') else self.root, bg=background_color)
            self.main_frame.pack()
            self.players_info = None
        self.current_controllers = controllers_info
        # This is the fast path -- it runs the moment a pad connects, ahead of the
        # background WinUSB poll -- so the wired PIDs are collected here too, or every
        # wired label would keep the previous controller's name until that poll lands.
        detected = False
        wired_pids = set()
        for vc in controllers_info or []:
            if vc is None:
                continue
            for controller in getattr(vc, "controllers", []) or []:
                if controller is None:
                    continue
                is_usb_hid = controller.__class__.__name__ == "USBHidController"
                if is_usb_hid or getattr(controller, "_hidhide_instance_id", None):
                    detected = True
                if is_usb_hid:
                    wired_pids.add(getattr(controller, "usb_product_id", PRO_CONTROLLER2_PID))
        self.wired_pro2_detected = detected
        self.wired_controller_pids = sorted(wired_pids)
        self.update_driver_buttons_visibility()
        # Refresh the header here too. In wired-only mode it reads wired_pro2_detected, and
        # its other callers are the button-layout rebuild and the 5 s ESP32 status poll --
        # neither of which fires when a wired pad connects, so the status would otherwise sit
        # on "Pending USB Connection" for up to 5 seconds after the controller is ready.
        try:
            self.update_header_status()
        except Exception:
            logger.debug("Header status refresh failed", exc_info=True)
        
        if hasattr(self, 'djg_dominant_var'):
            djg_dominant = getattr(CONFIG, "djg_dominant_side", "Right")
            self.djg_dominant_var.set(djg_dominant)
            if djg_dominant in ("Left", "Right") and hasattr(self, 'djg_dominant_switch'):
                self.djg_dominant_switch.set_value(djg_dominant)

        # Single Pro controller slot presentation
        any_connected = any(c is not None and len(getattr(c, 'controllers', [])) > 0 for c in controllers_info)
        self.no_controllers = not any_connected
        if any_connected:
            self._slide_and_fade_in_connected()
            if self.players_info is None:
                for w in self.main_frame.winfo_children(): w.destroy()
                p = PlayerInfoBlock(self.main_frame, self)
                p.main_frame.pack()
                self.players_info = [p]

            vc = controllers_info[0] if len(controllers_info) > 0 else None
            if vc is not None and len(getattr(vc, 'controllers', [])) > 0: 
                self.players_info[0].main_frame.pack()
                self.players_info[0].displayControllersInfo(vc)
            else: 
                self.players_info[0].clearControllerInfo()
                self.players_info[0].main_frame.pack_forget()
        else:
            if self.players_info is not None:
                for p in self.players_info: p.main_frame.destroy()
                self.players_info = None
            self._show_centered_connection_guide()

    def _show_centered_connection_guide(self):
        if getattr(self, "_slide_animation_id", None) is not None:
            try:
                self.root.after_cancel(self._slide_animation_id)
            except Exception:
                pass
            self._slide_animation_id = None
        self._layout_connected_state = False
        if hasattr(self, "right_column") and self.right_column.winfo_manager():
            self.right_column.pack_forget()
        if hasattr(self, "left_column"):
            self.left_column.pack_configure(padx=0)
        if hasattr(self, "center_cluster"):
            self.center_cluster.place_configure(relx=0.5, rely=0.5, anchor=tk.CENTER, x=0)
        if hasattr(self, "main_frame") and self.main_frame.winfo_exists():
            if not any(isinstance(w, tk.Label) and w.cget("text").startswith("Press button") for w in self.main_frame.winfo_children()):
                for w in self.main_frame.winfo_children():
                    w.destroy()
                scaling_factor = getattr(self, "scaling_factor", 1.0)
                tk.Label(self.main_frame, image=self.pairing_hint_image, bg=background_color).pack(pady=(0, int(8 * scaling_factor)))
                tk.Label(
                    self.main_frame,
                    text="Press button of a paired controller,\nor hold sync button to pair",
                    font=scale_font(("Arial", 10, "bold")),
                    bg=background_color,
                    fg=text_color,
                    justify=tk.CENTER
                ).pack(pady=(0, int(4 * scaling_factor)))

    def _slide_and_fade_in_connected(self):
        if not hasattr(self, "left_column") or not hasattr(self, "right_column"):
            return
        if getattr(self, "_layout_connected_state", False):
            return
        self._layout_connected_state = True
        if getattr(self, "_slide_animation_id", None) is not None:
            try:
                self.root.after_cancel(self._slide_animation_id)
            except Exception:
                pass
            self._slide_animation_id = None

        scaling_factor = getattr(self, "scaling_factor", 1.0)
        pad_gap = int(22 * scaling_factor)
        self.left_column.pack_configure(padx=(0, pad_gap))
        self.right_column.pack(side=tk.LEFT, padx=(pad_gap, 0))
        self.root.update_idletasks()

        r_width = self.right_column.winfo_reqwidth()
        shift = (r_width + 2 * pad_gap) // 2

        self.center_cluster.place_configure(relx=0.5, rely=0.5, anchor=tk.CENTER, x=shift)

        def _interp_color(c1_hex, c2_hex, frac):
            try:
                r1, g1, b1 = int(c1_hex[1:3], 16), int(c1_hex[3:5], 16), int(c1_hex[5:7], 16)
                r2, g2, b2 = int(c2_hex[1:3], 16), int(c2_hex[3:5], 16), int(c2_hex[5:7], 16)
                r = int(r1 + (r2 - r1) * frac)
                g = int(g1 + (g2 - g1) * frac)
                b = int(b1 + (b2 - b1) * frac)
                return f"#{max(0, min(255, r)):02x}{max(0, min(255, g)):02x}{max(0, min(255, b)):02x}"
            except Exception:
                return c2_hex

        # Collect buttons and labels in right_column for smooth color fade-in
        fade_buttons = []
        for btn in (getattr(self, "profile_btn", None),
                    getattr(self, "gl_combo", None),
                    getattr(self, "gr_combo", None),
                    getattr(self, "gl_gr_reset_btn", None)):
            if btn is not None and btn.winfo_exists():
                fade_buttons.append((btn, getattr(btn, "rounded_bg", button_gray)))

        add_btn = getattr(self, "add_profile_btn", None)
        add_target_bg = getattr(add_btn, "rounded_bg", "#2e7d32") if add_btn else "#2e7d32"

        fade_labels = []
        for child in self.right_column.winfo_children():
            if isinstance(child, tk.Label):
                fade_labels.append(child)
            elif isinstance(child, tk.Frame):
                for sub in child.winfo_children():
                    if isinstance(sub, tk.Label):
                        fade_labels.append(sub)
                    elif isinstance(sub, tk.Frame):
                        for sub2 in sub.winfo_children():
                            if isinstance(sub2, tk.Label):
                                fade_labels.append(sub2)

        def _apply_fade(p):
            fg_val = _interp_color(background_color, "#FFFFFF", p)
            for btn, target_bg in fade_buttons:
                cur_bg = _interp_color(background_color, target_bg, p)
                set_rounded_button_bg(btn, cur_bg)
                try:
                    btn.config(fg=fg_val)
                except Exception:
                    pass
            if add_btn and add_btn.winfo_exists():
                cur_add_bg = _interp_color(background_color, add_target_bg, p)
                set_rounded_button_bg(add_btn, cur_add_bg)
                try:
                    add_btn.config(fg=fg_val)
                except Exception:
                    pass
            for lbl in fade_labels:
                try:
                    lbl.config(fg=fg_val)
                except Exception:
                    pass

        # Frame 0
        _apply_fade(0.0)

        total_frames = 18

        def _step(frame=1):
            if not getattr(self, "_layout_connected_state", False):
                return
            t = min(1.0, frame / float(total_frames))
            # Cubic ease-out
            factor = 1.0 - (1.0 - t) ** 3
            curr_x = int(shift * (1.0 - factor))
            try:
                self.center_cluster.place_configure(relx=0.5, rely=0.5, anchor=tk.CENTER, x=curr_x)
            except Exception:
                pass
            _apply_fade(factor)

            if frame < total_frames:
                self._slide_animation_id = self.root.after(16, lambda: _step(frame + 1))
            else:
                self._slide_animation_id = None
                try:
                    self.center_cluster.place_configure(relx=0.5, rely=0.5, anchor=tk.CENTER, x=0)
                except Exception:
                    pass
                for btn, target_bg in fade_buttons:
                    set_rounded_button_bg(btn, target_bg)
                    try:
                        btn.config(fg="#FFFFFF")
                    except Exception:
                        pass
                if add_btn and add_btn.winfo_exists():
                    set_rounded_button_bg(add_btn, add_target_bg)
                    try:
                        add_btn.config(fg="#FFFFFF")
                    except Exception:
                        pass
                for lbl in fade_labels:
                    try:
                        lbl.config(fg=text_color)
                    except Exception:
                        pass

        self._slide_animation_id = self.root.after(16, lambda: _step(1))

    def _is_close_from_titlebar_x(self) -> bool:
        try:
            raw_hwnd = self.root.winfo_id()
            top_hwnd = ctypes.windll.user32.GetAncestor(raw_hwnd, 2)
            if not top_hwnd or not ctypes.windll.user32.IsWindow(top_hwnd):
                return False

            # If window is not normal (e.g. iconic/minimized) or not visible, it wasn't clicked from title bar
            if self.root.state() != 'normal' or ctypes.windll.user32.IsIconic(top_hwnd):
                return False

            class POINT(ctypes.Structure):
                _fields_ = [('x', ctypes.c_long), ('y', ctypes.c_long)]

            pt = POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))

            # Send WM_NCHITTEST (0x0084) to determine if cursor is over the titlebar close button (HTCLOSE = 20)
            lparam = ((pt.y & 0xFFFF) << 16) | (pt.x & 0xFFFF)
            hit = ctypes.windll.user32.SendMessageW(top_hwnd, 0x0084, 0, lparam)
            if hit == 20:  # HTCLOSE
                return True

            # Geometric fallback around the top-right corner of the window frame
            class RECT(ctypes.Structure):
                _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long), ('right', ctypes.c_long), ('bottom', ctypes.c_long)]
            rect = RECT()
            ctypes.windll.user32.GetWindowRect(top_hwnd, ctypes.byref(rect))
            cx_size = ctypes.windll.user32.GetSystemMetrics(30)  # SM_CXSIZE
            cy_size = ctypes.windll.user32.GetSystemMetrics(31)  # SM_CYSIZE
            button_w = max(int(cx_size * 1.5), 45)
            button_h = max(int(cy_size * 1.5), 35)
            if (rect.right - button_w <= pt.x <= rect.right + 5) and (rect.top - 5 <= pt.y <= rect.top + button_h):
                return True

            return False
        except Exception as e:
            logger.debug(f"Error checking close source: {e}")
            return False

    def close_all_sub_windows(self):
        for closer in (
            getattr(self, "close_about_popup", None),
            getattr(self, "close_settings_popup", None),
            getattr(self, "close_rumble_popup", None),
            getattr(self, "close_gyro_config_popup", None),
            getattr(self, "close_auto_disconnect_popup", None),
            getattr(self, "close_profile_popup", None),
            getattr(self, "close_back_button_popup", None),
            getattr(self, "cancel_back_button_assign", None),
            getattr(self, "_close_kofi_window", None),
        ):
            if callable(closer):
                try: closer()
                except Exception: pass

        if hasattr(self, "edit_profiles_dialog") and self.edit_profiles_dialog and self.edit_profiles_dialog.winfo_exists():
            try: self.edit_profiles_dialog.destroy()
            except Exception: pass
            self.edit_profiles_dialog = None
        if hasattr(self, "add_game_dialog") and self.add_game_dialog and self.add_game_dialog.winfo_exists():
            try: self.add_game_dialog.destroy()
            except Exception: pass
            self.add_game_dialog = None

        for p in (getattr(self, "players_info", None) or []):
            menu = getattr(p, "calibration_menu_window", None)
            if menu and menu.winfo_exists():
                try: menu.destroy()
                except Exception: pass
                p.calibration_menu_window = None

        if hasattr(self, "root") and self.root:
            try:
                for w in list(self.root.winfo_children()):
                    if isinstance(w, tk.Toplevel) and w.winfo_exists():
                        try:
                            w.destroy()
                        except Exception:
                            pass
            except Exception:
                pass

    def handle_window_delete(self):
        self.close_all_sub_windows()
        if self._is_close_from_titlebar_x():
            logger.info("Window close requested via titlebar X button -> minimizing to tray.")
            self.hide_to_tray()
        else:
            logger.info("Window close requested via taskbar context menu or system exit -> performing hard shutoff.")
            self.on_quit()

    def hide_to_tray(self):
        self.close_all_sub_windows()
        if self.root:
            self.root.withdraw()
        if not getattr(self, '_tray_setup_done', False):
            self.setup_tray()

    def restore_and_bring_to_front(self):
        try:
            prev_hwnd = ctypes.windll.user32.GetForegroundWindow()
            if prev_hwnd:
                pid = ctypes.wintypes.DWORD()
                ctypes.windll.user32.GetWindowThreadProcessId(prev_hwnd, ctypes.byref(pid))
                if pid.value > 4:
                    h_proc = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid.value)
                    if h_proc:
                        p_buf = ctypes.create_unicode_buffer(512)
                        sz = ctypes.wintypes.DWORD(512)
                        if ctypes.windll.kernel32.QueryFullProcessImageNameW(h_proc, 0, p_buf, ctypes.byref(sz)):
                            if p_buf.value:
                                p_val = p_buf.value
                                from config import is_blocked_process
                                if not (is_blocked_process(p_exe) or p_exe.startswith("switch2proconnect") or p_exe.startswith("switch2connect") or "wabbajack" in p_exe):
                                    self.last_external_app_path = p_val
                                    self.last_external_app_exe = p_exe
                        ctypes.windll.kernel32.CloseHandle(h_proc)
        except Exception:
            pass

        try:
            root = self.root
            if not root or not root.winfo_exists():
                return

            try:
                root.deiconify()
                root.state('normal')
                root.update_idletasks()
            except Exception as _deiconify_err:
                logger.debug(f"deiconify error: {_deiconify_err}")

            top_hwnd = getattr(self, "top_hwnd", None) or _top_level_hwnd(root)
            if not top_hwnd:
                top_hwnd = root.winfo_id()

            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            # Win32 SW_RESTORE to un-minimize native window:
            user32.ShowWindow(top_hwnd, 9)  # SW_RESTORE

            try:
                root.deiconify()
                root.state('normal')
                self._relayout_after_restore()
                root.update_idletasks()
                root.update()
            except Exception as _deiconify_err:
                logger.debug(f"deiconify error: {_deiconify_err}")

            fore_hwnd = user32.GetForegroundWindow()
            fore_thread = user32.GetWindowThreadProcessId(fore_hwnd, None) if fore_hwnd else 0
            cur_thread = kernel32.GetCurrentThreadId()
            gui_thread = user32.GetWindowThreadProcessId(top_hwnd, None) or cur_thread

            try:
                user32.LockSetForegroundWindow(2)   # LSFW_UNLOCK
                user32.AllowSetForegroundWindow(-1) # ASFW_ANY
            except Exception:
                pass

            attached = False
            if fore_thread and fore_thread != gui_thread:
                attached = bool(user32.AttachThreadInput(gui_thread, fore_thread, True))

            def _is_fullscreen_game(hwnd):
                if not hwnd: return False
                try:
                    cls_buf = ctypes.create_unicode_buffer(256)
                    user32.GetClassNameW(hwnd, cls_buf, 256)
                    cls_name = cls_buf.value
                    if cls_name in ("Shell_TrayWnd", "Progman", "WorkerW", "Windows.UI.Core.CoreWindow", "NotifyIconOverflowWindow"):
                        return False
                    rect = ctypes.wintypes.RECT()
                    if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                        sw = user32.GetSystemMetrics(0)
                        sh = user32.GetSystemMetrics(1)
                        if rect.left <= 0 and rect.top <= 0 and (rect.right - rect.left) >= sw and (rect.bottom - rect.top) >= sh:
                            return True
                except Exception:
                    pass
                return False

            if fore_hwnd and fore_hwnd != top_hwnd and _is_fullscreen_game(fore_hwnd):
                user32.ShowWindow(fore_hwnd, 6)   # SW_MINIMIZE (drops exclusive fullscreen game)

            # VK_MENU (Alt key) pulse grants foreground lock permission under Windows restrictions
            user32.keybd_event(0x12, 0, 0, 0)
            user32.keybd_event(0x12, 0, 2, 0)

            user32.SetWindowPos(top_hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)  # HWND_TOPMOST, SWP_NOMOVE|SWP_NOSIZE|SWP_SHOWWINDOW
            user32.SetForegroundWindow(top_hwnd)
            user32.BringWindowToTop(top_hwnd)

            try:
                user32.SwitchToThisWindow(top_hwnd, True)
            except Exception:
                pass

            if attached:
                user32.AttachThreadInput(gui_thread, fore_thread, False)

            root.lift()
            root.attributes("-topmost", True)
            root.focus_force()

            # Force immediate Windows and Tkinter repainting so all widgets display fully without requiring a mouse click:
            try:
                user32.RedrawWindow(top_hwnd, None, None, 0x0001 | 0x0002 | 0x0004 | 0x0080 | 0x0100)
                raw_id = root.winfo_id()
                if raw_id and raw_id != top_hwnd:
                    user32.RedrawWindow(raw_id, None, None, 0x0001 | 0x0002 | 0x0004 | 0x0080 | 0x0100)
                self._relayout_after_restore()
                root.update_idletasks()
                root.update()
            except Exception:
                pass

            # Temporarily stay topmost for 800ms to guarantee appearing above fullscreen/borderless games,
            # then release topmost so user can interact normally with other apps
            root.after(800, lambda: root.attributes("-topmost", False) if (root and root.winfo_exists()) else None)
        except Exception as e:
            logger.error(f"restore_and_bring_to_front failed: {e}", exc_info=True)

    def show_window(self, icon=None, item=None):
        logger.info("Open/Restore requested (tray icon or C button).")
        def _restore_to_main():
            self.close_all_sub_windows()
            self.restore_and_bring_to_front()
        if self.root:
            self.root.after(0, _restore_to_main)

    def hard_exit(self, icon=None, item=None):
        logger.info("Hard exit requested from tray icon.")
        try:
            if self.root:
                self.root.after(0, self.on_quit)
            else:
                self.on_quit()
        except Exception:
            self.on_quit()

    def setup_tray(self):
        if getattr(self, '_tray_setup_done', False):
            return
        self._tray_setup_done = True
        try:
            try:
                img = Image.open(get_resource('images/icon.png'))
            except Exception:
                img = Image.new('RGB', (64, 64), color=(0, 195, 227)) # Cyan fallback
            
            menu = pystray.Menu(
                item('Open', self.show_window, default=True),
                item('Exit', self.hard_exit)
            )
            self.tray_icon = pystray.Icon("Switch2ProConnect", img, "Switch 2 Pro Connect", menu)
            self.tray_icon.run_detached()
            logger.info("System tray icon initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize tray icon: {e}", exc_info=True)

    def _shutdown_virtual_devices_for_power_event(self, detach_timeout=1.0):
        """Detach USBIP first, then stop every virtual-device server.

        Windows must not be allowed to tear down this process while usbip-win2
        still has an attached device backed by our user-mode socket.  Mark every
        controller terminal before detaching so a PS5 disconnect callback cannot
        race the shutdown by starting its reconnect worker.
        """
        vcs = [vc for vc in getattr(self, 'current_controllers', []) or [] if vc is not None]
        try:
            from discoverer import VIRTUAL_CONTROLLERS
            for vc in VIRTUAL_CONTROLLERS:
                if vc is not None and vc not in vcs:
                    vcs.append(vc)
        except Exception:
            pass
        for vc in vcs:
            try:
                vc.running = False
                vc._suppress_usbip_reconnect = True
                with vc._usbip_reconnect_lock:
                    vc._usbip_reconnect_generation += 1
                    vc._usbip_reconnect_active = False
                for controller in getattr(vc, 'controllers', []) or []:
                    controller.interp_running = False
                    controller.suspended = True
                    controller._is_suspending = True
            except Exception:
                logger.debug("Failed to mark virtual controller for power shutdown", exc_info=True)

        # One inventory query handles every player.  This must happen before any
        # server/socket is stopped, otherwise the kernel USBIP client observes an
        # abrupt transport loss and can display an error during Windows shutdown.
        try:
            from virtual_controller import detach_all_usbip_devices
            detach_all_usbip_devices(timeout=detach_timeout)
        except Exception:
            logger.debug("Power shutdown USBIP detach failed", exc_info=True)

        for vc in vcs:
            try:
                vc.force_close(usbip_already_detached=True)
            except Exception:
                logger.debug("Power shutdown virtual-device close failed", exc_info=True)

    def on_quit(self):
        if getattr(self, 'is_cleaning_up', False): return
        self.close_all_sub_windows()
        self._close_kofi_window()
        try:
            if (MAG_TESTER_BUILD_ENABLED
                    and (self.mag_tester_window is not None
                         or GYRO_PHASE0_RECORDER.is_recording)):
                self._close_mag_tester()
        except Exception:
            logger.exception("Failed to close Mag Tester")
        try:
            if getattr(self, "wired_device_listener", None):
                self.wired_device_listener.stop()
        except Exception as e:
            logger.debug("Failed to stop wired device listener: %s", e)
        
        # Fallback query current root window geometry directly before saving
        try:
            if self.root and self.root.state() == 'normal':
                w = self.root.winfo_width()
                h = self.root.winfo_height()
                rx = self.root.winfo_x()
                ry = self.root.winfo_y()
                if w > 100 and h > 100:
                    self.last_width = w
                    self.last_height = h
                    self.last_x = rx
                    self.last_y = ry
        except Exception:
            pass
            
        # Save last window size if we tracked a normal state size
        if getattr(self, 'last_width', None) is not None and getattr(self, 'last_height', None) is not None:
            CONFIG.window_width = self.last_width
            CONFIG.window_height = self.last_height
            CONFIG.window_x = getattr(self, 'last_x', None)
            CONFIG.window_y = getattr(self, 'last_y', None)
            CONFIG.save_config()
            
        self.is_cleaning_up = True; self.is_quitting = True; set_shutting_down(True); self.root.withdraw()
        if hasattr(self, 'tray_icon') and self.tray_icon:
            try: self.tray_icon.stop()
            except: pass

        def _hard_exit_watchdog():
            time.sleep(5.0)
            try:
                os._exit(0)
            except Exception:
                pass
        threading.Thread(target=_hard_exit_watchdog, daemon=True).start()

        def cleanup():
            try:
                self._shutdown_virtual_devices_for_power_event(detach_timeout=1.5)
                vcs = [vc for vc in getattr(self, 'current_controllers', []) if vc and getattr(vc, 'loop', None) and vc.loop.is_running()]
                if vcs:
                    async def disconnect():
                        for vc in vcs:
                            if hasattr(vc, 'vg_controller') and vc.vg_controller:
                                try: vc.vg_controller.unregister_notification()
                                except: pass
                            for c in vc.controllers[:]:
                                if c.client and c.client.is_connected: 
                                    await c.disconnect()
                                    await asyncio.sleep(0.3)
                        await asyncio.sleep(3.5)
                    
                    fut = asyncio.run_coroutine_threadsafe(disconnect(), vcs[0].loop)
                    try:
                        # Increased timeout protection to 20 seconds to ensure clean sequential shutdown for 3+ controllers
                        fut.result(timeout=20.0)
                    except:
                        pass
                # Issue 5: even if there were no active virtual controllers (e.g. a
                # controller was mid-connect), make sure the ESP32-S3 stops scanning,
                # disables auto-connect and drops any remaining BLE links before exit,
                # so nothing stays connected and the bridge idles until the next launch.
                try:
                    from usb_serial_bridge import shutdown_all_bridges
                    shutdown_all_bridges()
                except Exception:
                    pass
            except: pass
            finally:
                try:
                    self.root.after(0, lambda: (self.root.destroy(), os._exit(0)))
                except Exception:
                    pass
                time.sleep(0.3)
                try:
                    os._exit(0)
                except Exception:
                    pass
        threading.Thread(target=cleanup, daemon=True).start()

    def handle_power_event(self, wparam):
        current_time = time.strftime("%H:%M:%S")
        if wparam == win32con.PBT_APMSUSPEND:
            logger.info(f"[{current_time}] System Suspend detected (PBT_APMSUSPEND). Starting cleanup...")
            set_suspending(True)
            # Release the shared virtual/standard keyboard before controller
            # threads stop producing edges; otherwise a held mapping can remain
            # logically down across sleep until the next physical transition.
            keyboard_output.release_all()

            # Match the proven 2.1 suspend path.  Do not touch CDC here: once the
            # host sleeps, heartbeat stops naturally and firmware releases BLE via
            # its host-lease timeout without a serial write/close race.
            if hasattr(self, 'current_controllers'):
                for vc in self.current_controllers:
                    if vc is not None:
                        vc.running = False
                        vc.reset_inputs()
                        for c in vc.controllers:
                            c.interp_running = False
                            c.suspended = True
                            c._is_suspending = True
                            c._interp_wake_event.set()
                            c._release_standard_mouse_buttons()
                        vc.force_close()
            # VMouse devices represent live physical connections; do not leave
            # their handles or latched buttons alive across system sleep.
            raw_input_mouse.shutdown()
            
            # CRITICAL: Reset the ViGEm bus singleton to release the driver handle entirely
            from virtual_controller import reset_vigem_bus
            reset_vigem_bus()

            # Preserve the 2.1 settling interval for OS driver handle cleanup.
            time.sleep(1.0)
            
            self.quit_event.set()
            self._is_restarting_discovery = False
            logger.info(f"[{current_time}] Suspend preparation complete. quit_event set.")
        
        elif wparam in [win32con.PBT_APMRESUMESUSPEND, 0x0012]: # PBT_APMRESUMESUSPEND or PBT_APMRESUMEAUTOMATIC
            event_name = "PBT_APMRESUMESUSPEND" if wparam == win32con.PBT_APMRESUMESUSPEND else "PBT_APMRESUMEAUTOMATIC"
            logger.info(f"[{current_time}] System Resume detected ({event_name}).")
            
            # Reset suspension state immediately
            set_suspending(False)
            self.quit_event.clear()
            
            # CRITICAL: Force immediate cleanup of any potentially stale handles that survived
            # This also re-initializes the ViGEm bus singleton via its internal call.
            emergency_cleanup()
            
            # Force UI to clear old/stale controller displays immediately
            self.root.after(0, lambda: self.update([]))
            
            logger.info(f"[{current_time}] quit_event cleared. UI cleared. Preparing to restart discovery...")
            
            if getattr(self, '_is_restarting_discovery', False):
                logger.info("Restart already in progress. Skipping...")
                return
            self._is_restarting_discovery = True

            def restart():
                try:
                    # Longer delay to ensure Bluetooth radio and driver handles are stable
                    # 7 seconds is safer for some slower BT adapters on wake
                    time.sleep(7.0)
                    
                    if not getattr(self, '_is_restarting_discovery', False): return
                    
                    # Double-check we didn't suspend again during the sleep
                    from discoverer import _IS_SUSPENDING
                    if _IS_SUSPENDING:
                        logger.info("System is suspending again. Aborting restart.")
                        self._is_restarting_discovery = False
                        return
                        
                    logger.info("Restarting discovery loop...")
                    self.start_discoverer_thread()
                except Exception as e:
                    logger.error(f"Restart failed: {e}")
                finally:
                    self._is_restarting_discovery = False

            threading.Thread(target=restart, daemon=True).start()

    def start_battery_refresh_timer(self):
        if not getattr(self, 'is_quitting', False):
            if hasattr(self, 'current_controllers') and self.current_controllers:
                try:
                    self.update(self.current_controllers)
                except Exception as e:
                    logger.debug(f"Failed to refresh battery indicators: {e}")
            self.root.after(300000, self.start_battery_refresh_timer) # 5 minutes

    def start_esp32s3_refresh_timer(self):
        if not getattr(self, 'is_quitting', False):
            import power_saving
            if not power_saving.is_full():
                self.refresh_esp32s3_status_async()
                self.refresh_wired_pro2_status_async()
            self.root.after(5000, self.start_esp32s3_refresh_timer)

    def refresh_wired_pro2_status_async(self):
        """Poll for a wired controller, then update the HidHide button.

        WinUSB is not checked or managed by the GUI: the USB transport selects it
        automatically when available and falls back to HID otherwise. When a pad is
        present and HidHide is absent, prompt to install HidHide once per session."""
        if getattr(self, '_wired_pro2_refresh_running', False) or getattr(self, 'is_quitting', False):
            return
        self._wired_pro2_refresh_running = True

        def worker():
            wired_pids = set()
            detected = False
            for vc in getattr(self, "current_controllers", []) or []:
                if vc is None:
                    continue
                for controller in getattr(vc, "controllers", []) or []:
                    if controller is None:
                        continue
                    is_usb_hid = controller.__class__.__name__ == "USBHidController"
                    if is_usb_hid or getattr(controller, "_hidhide_instance_id", None):
                        detected = True
                    if is_usb_hid:
                        wired_pids.add(getattr(controller, "usb_product_id", 0x2069))
            hh_installed = False
            if detected:
                state = self._sync_hidhide_installed(save=False, use_cache=True)
                hh_installed = (self._hidhide_installed_cached if state is None
                                else state)

            def apply():
                self._wired_pro2_refresh_running = False
                self.wired_pro2_detected = detected
                self.wired_controller_pids = sorted(wired_pids)
                self._hidhide_installed_cached = hh_installed
                self.update_driver_buttons_visibility()

                # Auto-prompt HidHide install on first detection while it's absent.
                if (detected and not hh_installed
                        and not getattr(CONFIG, 'hidhide_install_prompt_suppressed', False)
                        and not getattr(self, '_wired_pro2_prompt_shown', False)):
                    self._wired_pro2_prompt_shown = True
                    if self.ask_hidhide_auto_install():
                        self.run_hidhide_install(prompt_restart=True)

                if not detected:
                    # Allow the prompt again next time a pad is (re)connected.
                    self._wired_pro2_prompt_shown = False

            try:
                self.root.after(0, apply)
            except Exception:
                self._wired_pro2_refresh_running = False

        threading.Thread(target=worker, daemon=True).start()

    def start_detection_and_discovery(self):
        if getattr(self, '_startup_detection_done', False) or getattr(self, 'is_quitting', False):
            return
        self._startup_detection_done = True

        def start_driver_check_and_discovery(startup_bridge_context=None):
            self.start_discoverer_thread(startup_bridge_context)

            def bg_driver_check():
                try:
                    self.check_driver_installation(save=True, prompt_user=False)
                    keyboard_output.initialize()
                    self.root.after(0, self.refresh_profile_switching_combo_trigger_ui)
                    self.root.after(0, self.update_driver_button)
                except Exception as e:
                    logger.debug(f"Startup driver check failed: {e}")

            threading.Thread(target=bg_driver_check, daemon=True).start()

        def worker():
            status = None
            detected = False
            try:
                from usb_serial_bridge import detect_bridge
                status = detect_bridge()
                detected = bool(status and status.board_present)
            except Exception as e:
                logger.debug(f"Startup ESP32-S3 detection failed: {e}")

            def apply_status():
                if getattr(self, 'is_quitting', False):
                    return
                self.esp32s3_bridge_status = status
                self.esp32s3_detected = detected
                self._esp32s3_was_detected = detected
                self._esp32s3_current_seen = bool(status and getattr(status, "bridge_ready", False))
                self.update_driver_buttons_visibility()

                def after_auto_update(ok):
                    if ok:
                        self.root.after(1000, lambda: self.wait_for_current_esp32s3_then(start_driver_check_and_discovery))
                    else:
                        self.root.after(0, start_driver_check_and_discovery)

                if self.maybe_auto_update_esp32s3_firmware(status, on_complete=after_auto_update):
                    return
                bridge_context = None
                if (status
                        and getattr(status, "bridge_ready", False)
                        and getattr(status, "firmware_current", False)
                        and getattr(status, "serial_port", None)):
                    bridge_context = {
                        "status": status,
                        "observed_mono": time.monotonic(),
                    }
                start_driver_check_and_discovery(bridge_context)

            try:
                self.root.after(0, apply_status)
            except RuntimeError:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def start(self):
        self.is_quitting = False
        def callback(vcs):
            if not getattr(self, 'is_quitting', False):
                try:
                    self.message_queue.put(vcs)
                    self.root.event_generate(CONTROLLER_UPDATED_EVENT)
                except Exception as e:
                    logger.debug(f"Ignored Tkinter event generation error: {e}")
        self.discoverer_callback = callback
        self.root.bind(CONTROLLER_UPDATED_EVENT, lambda e: self.update(self.message_queue.get()))
        
        self.power_listener.start()
        try:
            self.wired_device_listener.start()
            self.root.after(250, self.poll_wired_device_events)
        except Exception as e:
            logger.debug("Failed to start wired device listener: %s", e)
        
        if CONFIG.start_minimized:
            self.hide_to_tray()
        else:
            try:
                self.root.attributes("-alpha", 0.0)
            except Exception:
                pass
            self.root.deiconify()
            self.root.update_idletasks()
            try:
                self.root.attributes("-alpha", 1.0)
            except Exception:
                pass
            self.root.after(200, self.setup_tray)

        # Startup probing is non-blocking.  Settings tabs are built only when the
        # user selects them; cycling through them after the window is visible
        # causes a noticeable full-window flash.
        self.root.after(0, self.start_detection_and_discovery)
            
        # Start battery refresh timer (5 minutes)
        self.root.after(300000, self.start_battery_refresh_timer)
        self.root.after(5000, self.start_esp32s3_refresh_timer)
        self.root.after(1000, self.poll_assigned_app_focus)
            
        self.root.protocol("WM_DELETE_WINDOW", self.handle_window_delete); self.root.mainloop()

if __name__ == "__main__":
    disable_power_throttling()
    win = ControllerWindow()
    win.init_interface()
    win.start()
