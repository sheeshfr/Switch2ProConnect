import sys
import os
import ctypes
import logging
import threading
import time
import uuid

from ctypes import wintypes

if sys.platform == "win32":
    import win32con
    import win32gui
else:
    try:
        import linux_uinput
        linux_uinput.install_win32_shims()
    except Exception:
        pass
    import win32con
    import win32gui

try:
    from usb_hid_controller import WIRED_USB_PIDS as WIRED_USB_DEVICE_PIDS
except Exception:
    WIRED_USB_DEVICE_PIDS = (0x2069, 0x2073)

logger = logging.getLogger(__name__)


class SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("fMask", ctypes.c_ulong),
        ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR),
        ("lpFile", wintypes.LPCWSTR),
        ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR),
        ("nShow", ctypes.c_int),
        ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", ctypes.c_void_p),
        ("lpClass", wintypes.LPCWSTR),
        ("hkeyClass", wintypes.HKEY),
        ("dwHotKey", wintypes.DWORD),
        ("hIconOrMonitor", wintypes.HANDLE),
        ("hProcess", wintypes.HANDLE),
    ]


class WINDOWPLACEMENT(ctypes.Structure):
    _fields_ = [
        ("length", wintypes.UINT),
        ("flags", wintypes.UINT),
        ("showCmd", wintypes.UINT),
        ("ptMinPosition", wintypes.POINT),
        ("ptMaxPosition", wintypes.POINT),
        ("rcNormalPosition", wintypes.RECT),
    ]


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def from_string(cls, value):
        parsed = uuid.UUID(str(value).strip("{}"))
        return cls.from_buffer_copy(parsed.bytes_le)


class DEV_BROADCAST_HDR(ctypes.Structure):
    _fields_ = [
        ("dbch_size", wintypes.DWORD),
        ("dbch_devicetype", wintypes.DWORD),
        ("dbch_reserved", wintypes.DWORD),
    ]


class DEV_BROADCAST_DEVICEINTERFACE_W(ctypes.Structure):
    _fields_ = [
        ("dbcc_size", wintypes.DWORD),
        ("dbcc_devicetype", wintypes.DWORD),
        ("dbcc_reserved", wintypes.DWORD),
        ("dbcc_classguid", GUID),
        ("dbcc_name", wintypes.WCHAR * 1),
    ]


# Explicitly set types for Win32 API to ensure compatibility
if sys.platform == "win32":
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


SEE_MASK_NOCLOSEPROCESS = 0x00000040
WAIT_TIMEOUT = 0x00000102
WAIT_OBJECT_0 = 0x00000000
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


class PowerListener:
    def __init__(self, callback, show_window_callback=None):
        self.callback = callback
        self.show_window_callback = show_window_callback
        self.hwnd = None
        self._running = False
        if sys.platform == "win32":
            try:
                self.wm_show_app = win32gui.RegisterWindowMessage("Switch2ProConnect_ShowWindow_Message")
                self.wm_show_app_legacy = win32gui.RegisterWindowMessage("Switch2Connect_ShowWindow_Message")
            except Exception:
                self.wm_show_app = 0
                self.wm_show_app_legacy = 0
        else:
            self.wm_show_app = 0
            self.wm_show_app_legacy = 0
            import tempfile
            uid = os.getuid() if hasattr(os, "getuid") else 1000
            self._sock_path = os.path.join(tempfile.gettempdir(), f"switch2proconnect_{uid}.sock")

    def start(self):
        if sys.platform == "win32":
            def _listen():
                wc = win32gui.WNDCLASS()
                wc.lpfnWndProc = self.wndproc
                wc.lpszClassName = "PowerListenerWindow"
                hInstance = win32gui.GetModuleHandle(None)
                wc.hInstance = hInstance
                try:
                    class_atom = win32gui.RegisterClass(wc)
                    self.hwnd = win32gui.CreateWindow(class_atom, "PowerListener", 0, 0, 0, 0, 0, 0, 0, hInstance, None)
                    win32gui.PumpMessages()
                except Exception as e:
                    logger.error(f"PowerListener failed: {e}")
                
            threading.Thread(target=_listen, daemon=True).start()
        else:
            def _listen_linux():
                import socket
                try:
                    if os.path.exists(self._sock_path):
                        try:
                            os.unlink(self._sock_path)
                        except OSError:
                            pass
                    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    s.bind(self._sock_path)
                    s.listen(2)
                    s.settimeout(1.0)
                    self._running = True
                    while self._running:
                        try:
                            conn, _ = s.accept()
                            data = conn.recv(1024)
                            conn.close()
                            if b"SHOW" in data and self.show_window_callback:
                                self.show_window_callback()
                        except socket.timeout:
                            continue
                        except Exception:
                            break
                    s.close()
                except Exception as e:
                    logger.debug("Linux IPC listener failed: %s", e)
            threading.Thread(target=_listen_linux, daemon=True).start()


    def wndproc(self, hwnd, msg, wparam, lparam):
        if msg == win32con.WM_POWERBROADCAST:
            self.callback(wparam)
        elif ((getattr(self, "wm_show_app", 0) and msg == self.wm_show_app)
              or (getattr(self, "wm_show_app_legacy", 0) and msg == self.wm_show_app_legacy)):
            if self.show_window_callback:
                try:
                    self.show_window_callback()
                except Exception as e:
                    logger.debug(f"Error in show_window_callback: {e}")
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)


class WiredDeviceChangeListener:
    """Watches for wired controller arrival/removal, and for Bluetooth radios.

    Both live on one hidden window: RegisterDeviceNotificationW can be called more than
    once for the same hwnd, and the two interfaces are told apart in _wndproc. The radio
    notification lets the wireless route sit idle until a radio actually appears instead
    of retrying on a timer.
    """

    WM_DEVICECHANGE = 0x0219
    DBT_DEVICEARRIVAL = 0x8000
    DBT_DEVICEREMOVECOMPLETE = 0x8004
    DBT_DEVTYP_DEVICEINTERFACE = 0x00000005
    DEVICE_NOTIFY_WINDOW_HANDLE = 0x00000000
    HID_INTERFACE_GUID = "{4D1E55B2-F16F-11CF-88CB-001111000030}"
    BLUETOOTH_RADIO_GUID = "{0850302A-B344-4FDA-9BE9-90576B8D46F0}"

    def __init__(self, event_queue):
        self.event_queue = event_queue
        self.hwnd = None
        self.thread = None
        self._stop_event = threading.Event()
        self._class_name = f"Switch2WiredDeviceChangeWindow_{id(self)}"
        self.notification_handle = None
        self.bluetooth_notification_handle = None

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self._stop_event.clear()
        if sys.platform == "win32":
            self.thread = threading.Thread(target=self._listen, daemon=True)
        else:
            self.thread = threading.Thread(target=self._listen_linux, daemon=True)
        self.thread.start()

    def stop(self):
        self._stop_event.set()
        if sys.platform == "win32":
            hwnd = self.hwnd
            if hwnd:
                try:
                    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                except Exception:
                    pass
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        self.thread = None
        self.hwnd = None

    def _listen_linux(self):
        try:
            import pyudev
            context = pyudev.Context()
            monitor = pyudev.Monitor.from_netlink(context)
            monitor.filter_by(subsystem="hidraw")
            monitor.filter_by(subsystem="bluetooth")
            for device in iter(monitor.poll, None):
                if self._stop_event.is_set():
                    break
                action = device.action
                if action not in ("add", "remove"):
                    continue
                reason = "device_arrival" if action == "add" else "device_removal"
                subsystem = device.subsystem
                if subsystem == "bluetooth":
                    self.event_queue.put_nowait({
                        "kind": "bluetooth_radio",
                        "reason": reason,
                        "path": device.device_node or str(device),
                        "timestamp": time.time(),
                    })
                elif subsystem == "hidraw":
                    parent = device.find_parent("usb")
                    if parent:
                        id_vendor = parent.get("ID_VENDOR_ID") or ""
                        id_model = parent.get("ID_MODEL_ID") or ""
                        try:
                            vid = int(id_vendor, 16)
                            pid = int(id_model, 16)
                            if vid == 0x057E and pid in WIRED_USB_DEVICE_PIDS:
                                self.event_queue.put_nowait({
                                    "kind": "wired",
                                    "reason": reason,
                                    "path": device.device_node,
                                    "timestamp": time.time(),
                                })
                        except (ValueError, TypeError):
                            pass
        except ImportError:
            logger.info("pyudev not installed; using polling for wired USB controller detection.")
            self._poll_linux()
        except Exception as e:
            logger.error("Linux device change listener error: %s", e)

    def _poll_linux(self):
        known_nodes = set()
        while not self._stop_event.is_set():
            try:
                if os.path.exists("/dev"):
                    current_nodes = set(
                        os.path.join("/dev", f) for f in os.listdir("/dev") if f.startswith("hidraw")
                    )
                    added = current_nodes - known_nodes
                    removed = known_nodes - current_nodes
                    for node in added:
                        self.event_queue.put_nowait({
                            "kind": "wired",
                            "reason": "device_arrival",
                            "path": node,
                            "timestamp": time.time(),
                        })
                    for node in removed:
                        self.event_queue.put_nowait({
                            "kind": "wired",
                            "reason": "device_removal",
                            "path": node,
                            "timestamp": time.time(),
                        })
                    known_nodes = current_nodes
            except Exception:
                pass
            time.sleep(2.0)


    def _listen(self):
        wc = win32gui.WNDCLASS()
        wc.lpfnWndProc = self._wndproc
        wc.lpszClassName = self._class_name
        hinstance = win32gui.GetModuleHandle(None)
        wc.hInstance = hinstance
        try:
            class_atom = win32gui.RegisterClass(wc)
            self.hwnd = win32gui.CreateWindow(class_atom, self._class_name, 0, 0, 0, 0, 0, 0, 0, hinstance, None)
            device_filter = DEV_BROADCAST_DEVICEINTERFACE_W()
            device_filter.dbcc_size = ctypes.sizeof(DEV_BROADCAST_DEVICEINTERFACE_W)
            device_filter.dbcc_devicetype = self.DBT_DEVTYP_DEVICEINTERFACE
            device_filter.dbcc_classguid = GUID.from_string(self.HID_INTERFACE_GUID)
            self.notification_handle = ctypes.windll.user32.RegisterDeviceNotificationW(
                self.hwnd,
                ctypes.byref(device_filter),
                self.DEVICE_NOTIFY_WINDOW_HANDLE,
            )
            if not self.notification_handle:
                raise ctypes.WinError(ctypes.get_last_error())
            logger.info("Wired HID device notification registered.")

            # Second registration on the same window for Bluetooth radios.
            try:
                radio_filter = DEV_BROADCAST_DEVICEINTERFACE_W()
                radio_filter.dbcc_size = ctypes.sizeof(DEV_BROADCAST_DEVICEINTERFACE_W)
                radio_filter.dbcc_devicetype = self.DBT_DEVTYP_DEVICEINTERFACE
                radio_filter.dbcc_classguid = GUID.from_string(self.BLUETOOTH_RADIO_GUID)
                self.bluetooth_notification_handle = ctypes.windll.user32.RegisterDeviceNotificationW(
                    self.hwnd,
                    ctypes.byref(radio_filter),
                    self.DEVICE_NOTIFY_WINDOW_HANDLE,
                )
                if self.bluetooth_notification_handle:
                    logger.info("Bluetooth radio device notification registered.")
                else:
                    logger.warning("Bluetooth radio notification could not be registered; "
                                   "the wireless route will fall back to its periodic check.")
            except Exception as e:
                logger.warning("Bluetooth radio notification setup failed: %s", e)

            win32gui.PumpMessages()
        except Exception as e:
            logger.error("Wired device change listener failed: %s", e)
        finally:
            for attr in ("notification_handle", "bluetooth_notification_handle"):
                handle = getattr(self, attr, None)
                if handle:
                    try:
                        ctypes.windll.user32.UnregisterDeviceNotification(handle)
                    except Exception:
                        pass
                    setattr(self, attr, None)
            self.hwnd = None
            try:
                win32gui.UnregisterClass(self._class_name, hinstance)
            except Exception:
                pass

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == self.WM_DEVICECHANGE:
            reason = None
            if int(wparam) == self.DBT_DEVICEARRIVAL:
                reason = "device_arrival"
            elif int(wparam) == self.DBT_DEVICEREMOVECOMPLETE:
                reason = "device_removal"
            path = None
            if reason and lparam:
                try:
                    header = ctypes.cast(
                        lparam, ctypes.POINTER(DEV_BROADCAST_HDR)).contents
                    if header.dbch_devicetype == self.DBT_DEVTYP_DEVICEINTERFACE:
                        path = ctypes.wstring_at(
                            lparam + DEV_BROADCAST_DEVICEINTERFACE_W.dbcc_name.offset)
                except Exception:
                    path = None
            target_path = (path or "").upper()
            if reason and any(f"VID_057E&PID_{pid:04X}" in target_path
                              for pid in WIRED_USB_DEVICE_PIDS):
                try:
                    self.event_queue.put_nowait({
                        "kind": "wired",
                        "reason": reason,
                        "path": path,
                        "timestamp": time.time(),
                    })
                except Exception:
                    pass
            elif reason and self.BLUETOOTH_RADIO_GUID.strip("{}") in target_path:
                # A Bluetooth radio came or went. The wireless route is parked waiting for
                # exactly this instead of retrying an adapter that is not there.
                try:
                    self.event_queue.put_nowait({
                        "kind": "bluetooth_radio",
                        "reason": reason,
                        "path": path,
                        "timestamp": time.time(),
                    })
                except Exception:
                    pass
        elif msg == win32con.WM_CLOSE:
            try:
                win32gui.DestroyWindow(hwnd)
            except Exception:
                pass
            return 0
        elif msg == win32con.WM_DESTROY:
            win32gui.PostQuitMessage(0)
            return 0
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)
