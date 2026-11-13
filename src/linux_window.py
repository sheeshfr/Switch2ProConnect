# Switch2ProConnect - Linux Window and Process Tracker
# Copyright (C) 2026 Switch2ProConnect Contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Linux window and active process tracking for automatic per-game profile switching.

Provides:
- get_active_window_process_path(): Returns the absolute executable path of the active foreground window.
- is_app_foreground(tk_root): Checks if the Switch2ProConnect window has focus.
- is_process_running(exe_name): Checks if a given game or application executable is currently running.
"""

import sys
import os
import logging
import subprocess

logger = logging.getLogger(__name__)

XLIB_AVAILABLE = False
try:
    from Xlib import display, X, error
    XLIB_AVAILABLE = True
except ImportError:
    pass


class LinuxWindowTracker:
    def __init__(self):
        self._display = None
        if XLIB_AVAILABLE and os.environ.get("DISPLAY"):
            try:
                self._display = display.Display()
            except Exception as e:
                logger.debug("Could not connect to X11 display: %s", e)
                self._display = None

    def get_active_window_pid(self):
        """Returns the PID of the active foreground window on X11."""
        if self._display is None:
            return self._fallback_active_pid()

        try:
            root = self._display.screen().root
            net_active_atom = self._display.intern_atom("_NET_ACTIVE_WINDOW")
            active_prop = root.get_full_property(net_active_atom, X.AnyPropertyType)
            if not active_prop or not active_prop.value:
                return None

            window_id = active_prop.value[0]
            if not window_id:
                return None

            window = self._display.create_resource_object("window", window_id)
            pid_atom = self._display.intern_atom("_NET_WM_PID")
            pid_prop = window.get_full_property(pid_atom, X.AnyPropertyType)
            if pid_prop and pid_prop.value:
                return int(pid_prop.value[0])
        except Exception as e:
            logger.debug("Xlib query active window failed: %s", e)
            return self._fallback_active_pid()

        return None

    def _fallback_active_pid(self):
        """Fallback using xdotool if Xlib is not present or failed."""
        try:
            out = subprocess.check_output(
                ["xdotool", "getactivewindow", "getwindowpid"],
                stderr=subprocess.DEVNULL,
                timeout=0.3,
            )
            return int(out.decode().strip())
        except Exception:
            return None

    def get_active_process_path(self):
        """Returns the filesystem path of the executable for the active foreground window."""
        pid = self.get_active_window_pid()
        if not pid:
            return ""

        try:
            exe_link = f"/proc/{pid}/exe"
            if os.path.exists(exe_link):
                return os.path.realpath(exe_link)
        except (PermissionError, FileNotFoundError):
            pass

        # Try reading cmdline if exe symlink is unreadable
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                cmd = f.read().split(b"\x00")[0].decode("utf-8", errors="replace")
                if cmd and os.path.isfile(cmd):
                    return os.path.realpath(cmd)
                elif cmd:
                    return cmd
        except Exception:
            pass

        return ""

    def is_app_foreground(self, tk_root=None):
        """Returns True if this application is currently in the foreground."""
        pid = self.get_active_window_pid()
        if pid is not None:
            return pid == os.getpid()

        # Fallback to Tkinter focus check
        if tk_root is not None:
            try:
                return bool(tk_root.focus_displayof())
            except Exception:
                return tk_root.state() in ("normal", "zoomed")

        return True


_TRACKER = None


def _get_tracker():
    global _TRACKER
    if _TRACKER is None:
        _TRACKER = LinuxWindowTracker()
    return _TRACKER


def get_active_window_process_path():
    """Returns the executable path of the active foreground process on Linux."""
    return _get_tracker().get_active_process_path()


def is_app_foreground(tk_root=None):
    """Returns True if Switch2ProConnect is the active foreground window."""
    return _get_tracker().is_app_foreground(tk_root)


def is_process_running(exe_name):
    """Checks whether any running process matches the given executable name."""
    if not exe_name:
        return False

    target = os.path.basename(exe_name).lower().strip()
    # Strip extension (e.g. .exe for Wine/Proton games)
    target_no_ext = os.path.splitext(target)[0]

    try:
        proc_entries = os.listdir("/proc")
    except Exception:
        return False

    for entry in proc_entries:
        if not entry.isdigit():
            continue

        # 1. Check comm (process name)
        try:
            with open(f"/proc/{entry}/comm", "r", encoding="utf-8", errors="replace") as f:
                comm = f.read().strip().lower()
                if comm == target or comm == target_no_ext:
                    return True
        except (FileNotFoundError, PermissionError):
            continue

        # 2. Check /proc/<pid>/exe target
        try:
            exe_link = f"/proc/{entry}/exe"
            if os.path.exists(exe_link):
                real_exe = os.path.basename(os.path.realpath(exe_link)).lower()
                if real_exe == target or real_exe == target_no_ext:
                    return True
        except (FileNotFoundError, PermissionError):
            pass

        # 3. Check cmdline (especially for Wine/Proton games where comm is 'wine64-preloader')
        try:
            with open(f"/proc/{entry}/cmdline", "rb") as f:
                cmdline = f.read().decode("utf-8", errors="replace").lower()
                if target in cmdline or (target_no_ext and target_no_ext in cmdline):
                    return True
        except (FileNotFoundError, PermissionError):
            pass

    return False


def get_running_desktop_apps(known_saved=None, my_pid=None, last_external_app_exe=None):
    """Enumerates running user applications/games on Linux, including Wine/Proton games."""
    from config import is_blocked_process

    if known_saved is None:
        known_saved = set()
    if my_pid is None:
        my_pid = os.getpid()

    results = {}
    try:
        proc_entries = os.listdir("/proc")
    except Exception:
        return []

    for entry in proc_entries:
        if not entry.isdigit():
            continue
        pid = int(entry)
        if pid <= 4 or pid == my_pid:
            continue

        full_path = ""
        exe = ""
        try:
            exe_link = f"/proc/{pid}/exe"
            if os.path.exists(exe_link):
                full_path = os.path.realpath(exe_link)
                exe = os.path.basename(full_path).lower().strip()
        except (PermissionError, FileNotFoundError):
            pass

        # Check for Wine / Proton games where exe is wine64-preloader
        if "wine" in exe or not full_path:
            try:
                with open(f"/proc/{pid}/cmdline", "rb") as f:
                    cmd_parts = f.read().split(b"\x00")
                    for part in cmd_parts:
                        p_str = part.decode("utf-8", errors="replace")
                        if p_str.lower().endswith(".exe"):
                            full_path = p_str
                            exe = os.path.basename(p_str).lower().strip()
                            break
            except Exception:
                pass

        if not full_path or not exe:
            continue

        # Filter out blocked system processes, daemons, and our own app
        if (is_blocked_process(exe)
                or "switch2proconnect" in exe
                or "switch2connect" in exe
                or "wabbajack" in exe
                or exe in known_saved
                or exe in results):
            continue

        # Common Linux background daemons to filter
        if exe in ("systemd", "dbus-daemon", "pipewire", "pulseaudio", "wireplumber",
                   "bash", "sh", "zsh", "python3", "python", "xorg", "wayland",
                   "kwin", "gnome-shell", "xfwm4", "sway"):
            continue

        dname = os.path.splitext(os.path.basename(full_path))[0]
        dname = dname.replace("-", " ").replace("_", " ").title()

        results[exe] = {
            "exe": exe,
            "path": full_path,
            "hwnd": None,
            "display_name": dname,
            "title": dname,
            "z_order": len(results)
        }

    last_exe = (last_external_app_exe or "").lower()
    def sort_key(item):
        if last_exe and item["exe"] == last_exe:
            return (0, 0)
        return (1, item.get("z_order", 9999))

    return sorted(list(results.values()), key=sort_key)

