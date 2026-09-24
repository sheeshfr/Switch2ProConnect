import ctypes
from ctypes import wintypes
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

import utils
import keyboard_output
import raw_input_mouse
from config import (
    CONFIG,
    get_resource,
    get_driver_path,
    packaged_winuhid_available,
    confirm_packaged_winuhid_capability,
    refresh_packaged_winuhid_capability,
)
from gui_listeners import (
    SHELLEXECUTEINFOW,
    SEE_MASK_NOCLOSEPROCESS,
    WAIT_TIMEOUT,
)
from driver_install_helper import (
    VIGEMBUS_ABSENT,
    VIGEMBUS_HEALTHY,
    VIGEMBUS_PARTIAL,
    VIGEMBUS_UNKNOWN,
    WINUHID_ABSENT,
    WINUHID_HEALTHY,
    WINUHID_PARTIAL,
    WINUHID_UNKNOWN,
    USBIP_HEALTHY,
    USBIP_PARTIAL,
    invalidate_driver_status_cache,
    get_hidhide_status,
    get_usbip_status,
    get_winuhid_status,
    get_vigembus_status,
)
import winuhid_client

class _VirtualControllersProxy:
    def __iter__(self):
        import gui
        return iter(getattr(gui, "VIRTUAL_CONTROLLERS", []))
    def __len__(self):
        import gui
        return len(getattr(gui, "VIRTUAL_CONTROLLERS", []))
    def __getitem__(self, idx):
        import gui
        return getattr(gui, "VIRTUAL_CONTROLLERS", [])[idx]

VIRTUAL_CONTROLLERS = _VirtualControllersProxy()

logger = logging.getLogger(__name__)

background_color = "#2D2D2D"
button_gray = "#4B4B4B"
text_color = "#FFFFFF"

class _ScalingProxy:
    def __mul__(self, other):
        import gui
        return gui.scaling_factor * other
    def __rmul__(self, other):
        import gui
        return other * gui.scaling_factor
    def __int__(self):
        import gui
        return int(gui.scaling_factor)
    def __float__(self):
        import gui
        return float(gui.scaling_factor)

scaling_factor = _ScalingProxy()

def scale_font(font_tuple):
    import gui
    return gui.scale_font(font_tuple)

def set_rounded_button_bg(*args, **kwargs):
    import gui
    return gui.set_rounded_button_bg(*args, **kwargs)

def _set_current_thread_priority(*args, **kwargs):
    import gui
    return gui._set_current_thread_priority(*args, **kwargs)

def verify_winuhid_runtime(*args, **kwargs):
    import gui
    return gui.verify_winuhid_runtime(*args, **kwargs)

def verify_vigembus_ready(*args, **kwargs):
    import gui
    return gui.verify_vigembus_ready(*args, **kwargs)

def verify_vigembus_runtime(*args, **kwargs):
    import gui
    return gui.verify_vigembus_runtime(*args, **kwargs)

def removal_verified(*args, **kwargs):
    import gui
    return gui.removal_verified(*args, **kwargs)

def hidhide_service_state(*args, **kwargs):
    import gui
    return gui.hidhide_service_state(*args, **kwargs)

def __getattr__(name):
    import gui
    if hasattr(gui, name):
        return getattr(gui, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

class ControllerWindowDriversMixin:
    def _cleanup_driver_desktop_shortcuts(self):
        """Remove any desktop shortcuts created by third-party driver installers (HidHide, USBIP, ViGEmBus, WinUHid)."""
        try:
            import glob
            desktop_dirs = []
            try:
                import ctypes.wintypes
                buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
                # CSIDL_DESKTOP (0x0000)
                ctypes.windll.shell32.SHGetFolderPathW(None, 0x0000, None, 0, buf)
                if buf.value and buf.value not in desktop_dirs:
                    desktop_dirs.append(buf.value)
                # CSIDL_COMMON_DESKTOPDIRECTORY (0x0019)
                ctypes.windll.shell32.SHGetFolderPathW(None, 0x0019, None, 0, buf)
                if buf.value and buf.value not in desktop_dirs:
                    desktop_dirs.append(buf.value)
            except Exception:
                pass

            user_profile = os.environ.get("USERPROFILE")
            if user_profile:
                desktop_dirs.append(os.path.join(user_profile, "Desktop"))
                desktop_dirs.append(os.path.join(user_profile, "OneDrive", "Desktop"))
            public_dir = os.environ.get("PUBLIC")
            if public_dir:
                desktop_dirs.append(os.path.join(public_dir, "Desktop"))

            targets = ("*hidhide*", "*usbip*", "*vigem*", "*winuhid*")
            for d in desktop_dirs:
                if os.path.exists(d):
                    for pattern in targets:
                        for lnk in glob.glob(os.path.join(d, pattern + ".lnk")):
                            try:
                                os.remove(lnk)
                                logger.info("Removed driver desktop shortcut: %s", lnk)
                            except Exception as e:
                                logger.debug("Failed to remove shortcut %s: %s", lnk, e)
        except Exception as exc:
            logger.debug("Desktop shortcut cleanup error: %s", exc)

    def check_driver_installation(self, save=True, prompt_user=False):
        # Always clean up any driver desktop shortcuts
        self._cleanup_driver_desktop_shortcuts()

        # MSIX may consume a separately installed WinUHid, but it never installs
        # or repairs one.  Refresh the live capability silently before choosing
        # a driver so a stale config/profile cannot re-enable unavailable paths.
        if utils.is_packaged():
            previous = bool(getattr(CONFIG, "driver_installed", False))
            available = bool(refresh_packaged_winuhid_capability())
            preferred = getattr(
                CONFIG, "preferred_driver_type",
                getattr(CONFIG, "driver_type", "WinUHid"))
            # PnP enumeration can transiently miss WinUHid during startup. A
            # successful native report submission is definitive and prevents a
            # false early downgrade from becoming the session's driver choice.
            if (not available and preferred == "WinUHid"
                    and verify_winuhid_runtime(
                        attempts=2, delay_seconds=0.1)):
                available = bool(
                    confirm_packaged_winuhid_capability(True))
            CONFIG.driver_installed = available
            if available and preferred == "WinUHid":
                was_fallback = bool(getattr(
                    CONFIG, "driver_fallback_active", False))
                CONFIG.driver_type = "WinUHid"
                CONFIG.simulation_mode = getattr(
                    CONFIG, "winuhid_sim_mode", "PS5")
                CONFIG.driver_fallback_active = False
                if was_fallback:
                    logger.info(
                        "WinUHid startup revalidation succeeded; restored configured driver")
            elif (not available
                  and getattr(CONFIG, "driver_type", "WinUHid") == "WinUHid"):
                # Effective fallback for this process only. save_config()
                # serializes preferred_driver_type while this flag is active.
                CONFIG.driver_type = "ViGEmBus"
                CONFIG.simulation_mode = getattr(CONFIG, "vigembus_sim_mode", "Xbox360")
                CONFIG.driver_fallback_active = True
                logger.warning(
                    "WinUHid startup revalidation failed; using temporary ViGEmBus fallback")
            if save and previous != available:
                CONFIG.save_config()
            if hasattr(self, "driver_switch"):
                options = (["WinUHid", "ViGEmBus", "USBIP"]
                           if available else ["ViGEmBus", "USBIP"])
                self.root.after(
                    0, lambda opts=options: self.driver_switch.update_options(
                        opts, opts, getattr(CONFIG, "driver_type", opts[0])))
            if available and CONFIG.driver_type == "WinUHid":
                # The refreshed stack check or native smoke test already proved
                # this packaged-session path. Do not immediately reinterpret a
                # stale PnP cache below as a missing installation.
                return
        # If driver type is USBIP, check USBIP driver instead
        if getattr(CONFIG, "driver_type", "") == "USBIP":
            if getattr(self, "_usbip_restart_pending", False):
                return
            usbip_status = get_usbip_status()
            if usbip_status.unknown:
                # Undetermined is not "missing": fall back to the executable the
                # rest of the app invokes rather than nagging on every launch.
                logger.warning("USBIP status undetermined: %s", usbip_status.describe())
            usbip_ready = usbip_status.installed or (
                usbip_status.unknown
                and os.path.exists(utils.get_usbip_exe_path()))
            if not usbip_ready and prompt_user:
                partial = usbip_status.state == USBIP_PARTIAL
                answer = self.ask_centered_yes_no(
                    "Repair USBIP Driver" if partial else "Install USBIP Driver",
                    (("USBIP is partially installed and cannot be used reliably.\n\n"
                      f"{usbip_status.describe()}\n\nDo you want to remove it now? "
                      "Restart Windows before installing USBIP again.\n")
                     if partial else
                     "Switch emulation is selected, but the USBIP driver is not installed.\n\n"
                     "Do you want to install it now?\n") +
                    "(Requires administrator privileges and will temporarily reset USB connections.)"
                )
                if answer:
                    if partial:
                        self.run_usbip_uninstall()
                        return
                    self.run_usbip_install(show_success_msg=False)
            return

        driver_type = getattr(CONFIG, "driver_type", "WinUHid")
        if (driver_type != "WinUHid"
                or (utils.is_packaged() and not packaged_winuhid_available())):
            self.close_winuhid_driver_manager()
        if driver_type == "ViGEmBus":
            self.check_vigembus_installation(save=save, prompt_user=prompt_user)
            return

        # Check driver installation state
        winuhid_status = get_winuhid_status()
        hidhide_installed = self._sync_hidhide_installed(save=False)

        if winuhid_status.unknown:
            logger.warning("WinUHid status undetermined: %s", winuhid_status.describe())
            if verify_winuhid_runtime(attempts=1):
                CONFIG.driver_installed = True

        winuhid_ok = winuhid_status.installed or bool(getattr(CONFIG, 'driver_installed', False))
        hidhide_ok = bool(hidhide_installed)

        if winuhid_ok and hidhide_ok:
            CONFIG.driver_installed = True
            if save:
                CONFIG.save_config()
            return

        if not winuhid_ok:
            CONFIG.driver_installed = False
            if save:
                CONFIG.save_config()
            self.update_driver_button()

        if not prompt_user:
            return

        missing_names = []
        if not winuhid_ok:
            missing_names.append("WinUHid (virtual controller driver)")
        if not hidhide_ok:
            missing_names.append("HidHide (wired controller filter driver)")

        partial_winuhid = winuhid_status.state == WINUHID_PARTIAL
        if partial_winuhid:
            title = "Repair Drivers"
            prompt = (
                "WinUHid is only partially installed and cannot be used reliably.\n\n"
                f"{winuhid_status.describe()}\n\n"
                "Do you want to clean up and install the required drivers now?\n"
                "(Requires administrator privileges.)"
            )
        else:
            title = "Install Drivers"
            prompt = (
                f"The following required driver{'s are' if len(missing_names) > 1 else ' is'} not installed:\n\n"
                + "\n".join(f"• {m}" for m in missing_names) + "\n\n"
                "Do you want to install now so both wireless and wired controllers work seamlessly?\n\n"
                "(Requires administrator privileges.)"
            )

        answer = self.ask_centered_yes_no(title, prompt)
        if answer:
            if not winuhid_ok:
                if partial_winuhid and not self.run_driver_uninstall():
                    return
                self.run_driver_install(show_success_msg=False)
            if not hidhide_ok:
                self.run_hidhide_install(prompt_restart=False)
            self.update_driver_button()

    def _launch_elevated(self, lp_file, lp_params, progress_win=None, lp_dir=None, hide=True):
        """Launch a process elevated (UAC runas), bringing the consent prompt to the
        foreground and hiding the child window. Used for every driver install/uninstall
        so the PowerShell console never pops up (progress is shown in the app's own
        dialog) and the UAC prompt doesn't just flash in the taskbar.
        Returns hProcess (int) or None if the launch failed / UAC was declined.
        """
        info = SHELLEXECUTEINFOW()
        info.cbSize = ctypes.sizeof(info)
        info.fMask = SEE_MASK_NOCLOSEPROCESS
        info.hwnd = self.get_root_hwnd()
        info.lpVerb = "runas"
        info.lpFile = lp_file
        info.lpParameters = lp_params
        info.lpDirectory = lp_dir
        info.nShow = 0 if hide else 1  # SW_HIDE vs SW_SHOWNORMAL
        # Grant foreground rights + drop any modal grab so the UAC consent prompt comes
        # to the front instead of only flashing in the taskbar.
        try:
            if progress_win is not None:
                progress_win.grab_release()
            self.root.focus_force()
            ctypes.windll.user32.AllowSetForegroundWindow(-1)  # ASFW_ANY
        except Exception:
            pass
        if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info)):
            return None
        return info.hProcess

    @staticmethod
    def _ps_hidden_args(script_path):
        """PowerShell args that run a script with no visible console window."""
        return f'-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{script_path}"'

    @staticmethod
    def _read_winuhid_uninstall_log():
        log_path = os.path.join(os.environ.get("TEMP", ""), "Switch2Connect_WinUHid_uninstall.log")
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as stream:
                content = stream.read().strip()
            lines = content.splitlines()
            keywords = ("error", "failed", "incomplete", "does not exist", "fallback")
            important = [line for line in lines if any(word in line.lower() for word in keywords)]
            summary = important[-12:] if important else lines[-12:]
            return "\n".join(summary)[-1400:]
        except Exception:
            return "Uninstaller log was not available."

    @staticmethod
    def _read_vigembus_uninstall_log():
        log_path = os.path.join(os.environ.get("TEMP", ""), "Switch2Connect_ViGEmBus_uninstall.log")
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as stream:
                lines = stream.read().strip().splitlines()
            keywords = ("error", "failed", "incomplete", "does not exist")
            important = [line for line in lines if any(word in line.lower() for word in keywords)]
            return "\n".join((important or lines)[-12:])[-1400:]
        except Exception:
            return "Uninstaller log was not available."

    def install_vigembus_driver(self, show_success_msg=True):
        """Install ViGEmBus. The packaged build installs from the bundled vgamepad
        ViGEmBus MSI (no download); the standalone .exe build downloads the official
        installer (unchanged). Returns True once ViGEmBus is verified working."""
        if utils.is_packaged():
            res = self.run_vigembus_install(show_success_msg=show_success_msg)
        else:
            res = self.download_and_install_driver("ViGEmBus", verify_vigembus_ready, show_success_msg)
        self._cleanup_driver_desktop_shortcuts()
        return res

    def run_vigembus_install(self, show_success_msg=True):
        """Install ViGEmBus from the ViGEmBus MSI bundled inside the package (vgamepad),
        elevated and silent — no network access. Used by the MSIX/packaged build."""
        import os, glob
        # Locate the bundled ViGEmBusSetup MSI (vgamepad ships it under win/vigem/install).
        roots = []
        base = getattr(sys, "_MEIPASS", None)
        if base:
            roots.append(base)
        roots.append(os.path.dirname(os.path.abspath(__file__)))
        try:
            import vgamepad
            roots.append(os.path.dirname(os.path.abspath(vgamepad.__file__)))
        except Exception:
            pass
        msi = None
        for root in roots:
            hits = glob.glob(os.path.join(root, "vgamepad", "win", "vigem", "install", "x64", "ViGEmBusSetup_x64.msi"))
            hits += glob.glob(os.path.join(root, "**", "ViGEmBusSetup_x64.msi"), recursive=True)
            if hits:
                msi = hits[0]
                break
        if not msi or not os.path.exists(msi):
            self.show_centered_message("Error", "Could not find the bundled ViGEmBus installer. Please verify the application files.")
            return False

        progress_win = tk.Toplevel(self.root)
        progress_win.title("Install ViGEmBus Driver")
        progress_win.resizable(False, False)
        progress_win.config(bg="#1E1E1E")
        progress_win.transient(self.root)
        progress_win.grab_set()
        self.center_window_on_root(progress_win, int(450 * scaling_factor), int(130 * scaling_factor))
        tk.Label(progress_win, text="Installing ViGEmBus driver...\nPlease authorize the UAC prompt if asked.",
                 fg="white", bg="#1E1E1E", font=scale_font(("Arial", 11, "bold"))).pack(pady=int(40 * scaling_factor))

        hProcess = self._launch_elevated("msiexec.exe", f'/i "{msi}" /qn /norestart', progress_win=progress_win)
        if not hProcess:
            progress_win.grab_release()
            progress_win.destroy()
            self.show_centered_message("Error", "ViGEmBus install was cancelled or failed to start (UAC prompt declined).")
            return False

        def check_process():
            if hProcess and ctypes.windll.kernel32.WaitForSingleObject(hProcess, 0) == WAIT_TIMEOUT:
                progress_win.after(200, check_process)
                return
            if hProcess:
                ctypes.windll.kernel32.CloseHandle(hProcess)
            progress_win.grab_release()
            progress_win.destroy()
        progress_win.after(200, check_process)
        self.root.wait_window(progress_win)

        invalidate_driver_status_cache("vigembus")
        ok = verify_vigembus_ready()
        if ok:
            if show_success_msg:
                self.show_centered_message("Success", "ViGEmBus driver installed successfully.")
        else:
            self.show_centered_message(
                "Error",
                "ViGEmBus installation was not completed. A system restart may be required; please try again if the issue persists.")
        return ok

    def download_and_install_driver(self, driver_key, verify_fn, show_success_msg=True):
        """Download a driver installer and run it silently with UAC elevation.

        Standalone .exe build only: used for the ViGEmBus one-click install (the
        packaged build installs ViGEmBus from the bundled MSI instead, and all other
        drivers are installed from bundled files in both builds).
        Returns True if verify_fn() reports the driver installed afterwards.
        """
        return self._download_and_run_driver_action(driver_key, verify_fn, "install", show_success_msg)

    def _download_and_run_driver_action(self, driver_key, verify_fn, action, show_success_msg=True):
        """Download ViGEmBus's installer and run it silently with UAC elevation, with a
        progress dialog. Standalone .exe build only (the packaged build never downloads).
        verify_fn() returns True once ViGEmBus is installed."""
        from driver_install_helper import DRIVER_SPECS, make_download_dir, download_spec_files

        spec = DRIVER_SPECS.get(driver_key)
        if spec is None:
            self.show_centered_message("Error", f"Unknown driver: {driver_key}")
            return False

        # Present-tense / past-tense words for dialog and result messages.
        gerund = "Installing" if action == "install" else "Uninstalling"
        past = "installed" if action == "install" else "uninstalled"
        title_verb = "Install" if action == "install" else "Uninstall"
        dl_key = driver_key if action == "install" else f"{driver_key}_uninstall"

        # Tracks whether the elevated installer/uninstaller actually started (vs a
        # download failure or a declined UAC prompt). Callers can read it afterwards.
        self._last_driver_action_launched = True

        # Stop discoverer and release virtual controller handles first.
        discoverer_was_running = False
        if hasattr(self, 'discoverer_thread') and self.discoverer_thread and self.discoverer_thread.is_alive():
            discoverer_was_running = True
            self.stop_discoverer_thread()
        from discoverer import emergency_cleanup
        emergency_cleanup()

        progress_win = tk.Toplevel(self.root)
        progress_win.title(f"{title_verb} {spec.display_name} Driver")
        progress_w = int(460 * scaling_factor)
        progress_h = int(140 * scaling_factor)
        progress_win.resizable(False, False)
        progress_win.config(bg="#1E1E1E")
        progress_win.transient(self.root)
        progress_win.grab_set()
        self.center_window_on_root(progress_win, progress_w, progress_h)

        label = tk.Label(
            progress_win,
            text=f"Downloading {spec.display_name} driver...",
            fg="white", bg="#1E1E1E",
            font=scale_font(("Arial", 11, "bold")),
            justify="center"
        )
        label.pack(pady=int(45 * scaling_factor))

        state = {"result": None, "installer_path": None, "error": None, "exit_code": None}

        def set_label(text):
            try:
                label.config(text=text)
            except Exception:
                pass

        def progress_cb(filename, downloaded, total):
            if total and total > 0:
                pct = int(downloaded * 100 / total)
                self.root.after(0, set_label, f"Downloading {spec.display_name} driver... {pct}%")
            else:
                mb = downloaded / (1024 * 1024)
                self.root.after(0, set_label, f"Downloading {spec.display_name} driver... {mb:.1f} MB")

        def do_download():
            try:
                dest_dir = make_download_dir(dl_key)
                installer = download_spec_files(spec, dest_dir, progress_cb)
                state["installer_path"] = installer
            except Exception as e:
                state["error"] = str(e)
            self.root.after(0, after_download)

        def after_download():
            if state["error"]:
                self._last_driver_action_launched = False
                progress_win.grab_release()
                progress_win.destroy()
                self.show_centered_message(
                    "Download Error",
                    f"Failed to download the {spec.display_name} {action} script:\n{state['error']}\n\n"
                    "Please check your internet connection and try again."
                )
                if discoverer_was_running:
                    self.start_discoverer_thread()
                return
            set_label(f"{gerund} {spec.display_name} driver...\nPlease authorize the UAC prompt if asked.")
            self.root.after(50, launch_installer)

        def launch_installer():
            kind = spec.run[0]
            installer_path = state["installer_path"]
            if kind == "exe":
                lp_file = installer_path
                lp_params = spec.run[2]
            else:  # ps1
                lp_file = "powershell.exe"
                lp_params = self._ps_hidden_args(installer_path)

            hProcess = self._launch_elevated(
                lp_file, lp_params, progress_win=progress_win,
                lp_dir=os.path.dirname(installer_path))
            if not hProcess:
                self._last_driver_action_launched = False
                progress_win.grab_release()
                progress_win.destroy()
                self.show_centered_message(
                    "Error",
                    f"{spec.display_name} {action} was cancelled or failed to start (UAC prompt declined)."
                )
                if discoverer_was_running:
                    self.start_discoverer_thread()
                return

            def check_process():
                if hProcess:
                    res = ctypes.windll.kernel32.WaitForSingleObject(hProcess, 0)
                    if res == WAIT_TIMEOUT:
                        progress_win.after(200, check_process)
                        return
                    exit_code = wintypes.DWORD()
                    ctypes.windll.kernel32.GetExitCodeProcess(hProcess, ctypes.byref(exit_code))
                    state["exit_code"] = exit_code.value
                    ctypes.windll.kernel32.CloseHandle(hProcess)
                progress_win.grab_release()
                progress_win.destroy()

            progress_win.after(200, check_process)

        threading.Thread(target=do_download, daemon=True).start()
        self.root.wait_window(progress_win)

        action_ok = False
        try:
            action_ok = state["exit_code"] == 0 and bool(verify_fn())
        except Exception as e:
            logger.error(f"Driver verification failed for {driver_key} ({action}): {e}")

        if action_ok:
            if show_success_msg:
                self.show_centered_message("Success", f"{spec.display_name} driver {past} successfully.")
        elif state["error"] is None:
            detail = ""
            if driver_key == "WinUHid" and action == "uninstall":
                detail = "\n\n" + self._read_winuhid_uninstall_log()
            elif driver_key == "ViGEmBus" and action == "uninstall":
                detail = "\n\n" + self._read_vigembus_uninstall_log()
            self.show_centered_message(
                "Error",
                f"{spec.display_name} {action} was not completed or failed "
                f"(exit code: {state['exit_code']}).\n"
                "A system restart may be required. Please try again if the issue persists."
                f"{detail}"
            )

        if discoverer_was_running:
            self.start_discoverer_thread()
        return action_ok

    def run_driver_install(self, show_success_msg=True):
        if utils.is_packaged():
            self.show_centered_message(
                "Unavailable",
                "WinUHid Driver Mode is not available in the Microsoft Store version."
            )
            return False
        # Drivers are bundled in the package (both builds); install from the local
        # files below — never downloaded (Store policy 10.2.10.1 / 10.1.5).
        import sys
        import os
        from tkinter import messagebox

        # Stop discoverer before installation
        discoverer_was_running = False
        if hasattr(self, 'discoverer_thread') and self.discoverer_thread and self.discoverer_thread.is_alive():
            discoverer_was_running = True
            self.stop_discoverer_thread()
            
        # Run emergency cleanup to close all virtual controller handles immediately
        from discoverer import emergency_cleanup
        emergency_cleanup()

        install_ps1 = get_driver_path("install_driver.ps1")
        if os.path.exists(install_ps1):
            try:
                progress_win = tk.Toplevel(self.root)
                progress_win.title("Driver Installation")
                progress_w = int(450 * scaling_factor)
                progress_h = int(130 * scaling_factor)
                progress_win.resizable(False, False)
                progress_win.config(bg="#1E1E1E")
                progress_win.transient(self.root)
                progress_win.grab_set()
                self.center_window_on_root(progress_win, progress_w, progress_h)
                
                label = tk.Label(
                    progress_win,
                    text="Installing WinUHid Driver...\nPlease authorize the UAC prompt if asked.",
                    fg="white", bg="#1E1E1E",
                    font=scale_font(("Arial", 11, "bold"))
                )
                label.pack(pady=int(40 * scaling_factor))
                
                # Bypassing CMD and launching powershell directly via ShellExecuteExW (runas verb)
                hProcess = self._launch_elevated("powershell.exe", self._ps_hidden_args(install_ps1), progress_win=progress_win)
                if not hProcess:
                    # User cancelled the UAC prompt or it failed
                    progress_win.grab_release()
                    progress_win.destroy()
                    self.show_centered_message("Error", "Driver installation was cancelled or failed to start (UAC prompt declined).")
                    if discoverer_was_running:
                        self.start_discoverer_thread()
                    return

                proc_exit_code = [0]

                def check_process():
                    if hProcess:
                        res = ctypes.windll.kernel32.WaitForSingleObject(hProcess, 0)
                        if res == WAIT_TIMEOUT:
                            progress_win.after(200, check_process)
                        else:
                            exit_code = wintypes.DWORD()
                            ctypes.windll.kernel32.GetExitCodeProcess(hProcess, ctypes.byref(exit_code))
                            ctypes.windll.kernel32.CloseHandle(hProcess)
                            proc_exit_code[0] = exit_code.value
                            progress_win.grab_release()
                            progress_win.destroy()
                    else:
                        progress_win.grab_release()
                        progress_win.destroy()
                            
                progress_win.after(200, check_process)
                self.root.wait_window(progress_win)
                
                logger.info(f"Driver installer process exited with code: {proc_exit_code[0]}")
                
                invalidate_driver_status_cache("winuhid")
                driver_status = get_winuhid_status()
                # When the layers cannot be read, the runtime smoke test is the verdict;
                # otherwise a Win10 install that actually succeeded reports as failed.
                runtime_ok = ((driver_status.installed or driver_status.unknown)
                              and verify_winuhid_runtime())
                driver_installed_ok = proc_exit_code[0] == 0 and runtime_ok
                if driver_installed_ok:
                    CONFIG.driver_installed = True
                    # Device creation follows the active Profile, never Driver Mode.
                    keyboard_output.initialize()
                    CONFIG._bump_settings_generation()
                    CONFIG.save_config()
                    self.wake_controller_mouse_output_reconcile()
                    self.refresh_profile_switching_combo_trigger_ui()
                    self.refresh_driver_ui_status()
                    if show_success_msg:
                        self.show_centered_message("Success", "WinUHid driver installed successfully.")
                else:
                    self.refresh_driver_ui_status()
                    self.show_centered_message(
                        "Error",
                        "Driver installation was not completed or failed.\n\n"
                        f"Exit code: {proc_exit_code[0]}\nRuntime smoke test: {runtime_ok}\n"
                        f"{driver_status.describe()}"
                    )
                    if getattr(CONFIG, "keyboard_output_mode", None) == keyboard_output.RAW_INPUT:
                        keyboard_output.activate_raw_input(save=False)
                self.refresh_driver_ui_status()
            except Exception as e:
                self.show_centered_message("Error", f"Failed to start the installer: {e}")
        else:
            self.show_centered_message("Error", "Could not find install_driver.ps1. Please verify the integrity of the application files.")

        self._cleanup_driver_desktop_shortcuts()
        if discoverer_was_running:
            self.start_discoverer_thread()
        return bool(locals().get('driver_installed_ok', False))

    def run_driver_uninstall(self, show_success_msg=True):
        # MSIX may remove an externally installed WinUHid, but it must never
        # install or repair one.  The uninstall script is bundled locally so
        # this path does not download or acquire software at runtime.
        import sys
        import os
        from tkinter import messagebox

        # Stop discoverer before uninstallation
        discoverer_was_running = False
        if hasattr(self, 'discoverer_thread') and self.discoverer_thread and self.discoverer_thread.is_alive():
            discoverer_was_running = True
            self.stop_discoverer_thread()

        # Run emergency cleanup to close all virtual controller handles immediately
        from discoverer import emergency_cleanup
        emergency_cleanup()

        uninstall_ps1 = get_driver_path("uninstall_driver.ps1")
        if os.path.exists(uninstall_ps1):
            try:
                progress_win = tk.Toplevel(self.root)
                progress_win.title("Driver Uninstallation")
                progress_w = int(450 * scaling_factor)
                progress_h = int(130 * scaling_factor)
                progress_win.resizable(False, False)
                progress_win.config(bg="#1E1E1E")
                progress_win.transient(self.root)
                progress_win.grab_set()
                self.center_window_on_root(progress_win, progress_w, progress_h)
                
                label = tk.Label(
                    progress_win,
                    text="Uninstalling WinUHid Driver...\nPlease authorize the UAC prompt if asked.",
                    fg="white", bg="#1E1E1E",
                    font=scale_font(("Arial", 11, "bold"))
                )
                label.pack(pady=int(40 * scaling_factor))
                
                # Bypassing CMD and launching powershell directly via ShellExecuteExW (runas verb)
                hProcess = self._launch_elevated("powershell.exe", self._ps_hidden_args(uninstall_ps1), progress_win=progress_win)
                if not hProcess:
                    # User cancelled the UAC prompt or it failed
                    progress_win.grab_release()
                    progress_win.destroy()
                    self.show_centered_message("Error", "Driver uninstallation was cancelled or failed to start (UAC prompt declined).")
                    if discoverer_was_running:
                        self.start_discoverer_thread()
                    return

                proc_exit_code = [0]

                def check_process():
                    if hProcess:
                        res = ctypes.windll.kernel32.WaitForSingleObject(hProcess, 0)
                        if res == WAIT_TIMEOUT:
                            progress_win.after(200, check_process)
                        else:
                            exit_code = wintypes.DWORD()
                            ctypes.windll.kernel32.GetExitCodeProcess(hProcess, ctypes.byref(exit_code))
                            ctypes.windll.kernel32.CloseHandle(hProcess)
                            proc_exit_code[0] = exit_code.value
                            progress_win.grab_release()
                            progress_win.destroy()
                    else:
                        progress_win.grab_release()
                        progress_win.destroy()
                            
                progress_win.after(200, check_process)
                self.root.wait_window(progress_win)
                
                logger.info(f"Driver uninstaller process exited with code: {proc_exit_code[0]}")
                
                # Now that progress_win is destroyed, check if it was removed
                invalidate_driver_status_cache("winuhid")
                driver_status = get_winuhid_status()
                driver_removed_ok = (proc_exit_code[0] == 0 or driver_status.absent) and removal_verified(
                    driver_status, verify_winuhid_runtime)
                if driver_removed_ok:
                    CONFIG.driver_installed = False
                    keyboard_output.activate_standard(save=False)
                    raw_input_mouse.shutdown()
                    # Preserve each Profile's requested modes.  With the driver
                    # absent their effective output is Win32 API; reinstalling
                    # restores the saved Profile preference.
                    CONFIG._bump_settings_generation()
                    CONFIG.save_config()
                    self.wake_controller_mouse_output_reconcile()
                    self.refresh_profile_switching_combo_trigger_ui()
                    if utils.is_packaged():
                        refresh_packaged_winuhid_capability()
                        # A removed active WinUHid cannot keep virtual devices
                        # alive.  Move the current profile back to ViGEmBus;
                        # the normal driver-change path performs its readiness
                        # check and recreates the virtual controller safely.
                        if getattr(CONFIG, "driver_type", "") == "WinUHid":
                            self.update_driver_type_setting("ViGEmBus")
                    self.refresh_driver_ui_status()
                    if show_success_msg:
                        self.show_centered_message("Success", "WinUHid driver uninstalled successfully.")
                else:
                    self.refresh_driver_ui_status()
                    uninstall_log = self._read_winuhid_uninstall_log()
                    self.show_centered_message(
                        "Error",
                        "Driver uninstallation failed or left WinUHid components behind.\n\n"
                        f"Exit code: {proc_exit_code[0]}\n{driver_status.describe()}"
                        f"\n\nUninstaller details:\n{uninstall_log}"
                    )
                    if getattr(CONFIG, "keyboard_output_mode", None) == keyboard_output.RAW_INPUT:
                        keyboard_output.activate_raw_input(save=False)
            except Exception as e:
                self.show_centered_message("Error", f"Failed to start the uninstaller: {e}")
        else:
            self.show_centered_message("Error", "Could not find uninstall_driver.ps1. Please verify the integrity of the application files.")

        try:
            self.refresh_driver_ui_status()
        except Exception:
            pass

        if discoverer_was_running:
            self.start_discoverer_thread()
        return bool(locals().get('driver_removed_ok', False))

    def stop_discoverer_thread(self):
        if hasattr(self, 'discoverer_thread') and self.discoverer_thread and self.discoverer_thread.is_alive():
            logger.info("Stopping discoverer thread...")
            self.quit_event.set()
            self.discoverer_thread.join(timeout=5.0)
            self.discoverer_thread = None

    def start_discoverer_thread(self, startup_bridge_context=None):
        self.stop_discoverer_thread()
        self.quit_event.clear()
        
        def run():
            _set_current_thread_priority(1)
            from discoverer import start_discoverer
            start_discoverer(self.discoverer_callback, self.quit_event, startup_bridge_context)
            
        logger.info("Starting discoverer thread...")
        self.discoverer_thread = threading.Thread(target=run, daemon=True)
        self.discoverer_thread.start()

    def run_vigembus_uninstall(self):
        # Uninstall from the bundled script (both builds); nothing downloaded.
        import sys
        import os
        from tkinter import messagebox

        # Stop discoverer before uninstallation
        discoverer_was_running = False
        if hasattr(self, 'discoverer_thread') and self.discoverer_thread and self.discoverer_thread.is_alive():
            discoverer_was_running = True
            self.stop_discoverer_thread()
            
        # Run emergency cleanup to close all virtual controller handles immediately
        from discoverer import emergency_cleanup
        emergency_cleanup()

        uninstall_ps1 = get_driver_path("uninstall_vigembus.ps1")
        if os.path.exists(uninstall_ps1):
            try:
                progress_win = tk.Toplevel(self.root)
                progress_win.title("ViGEmBus Uninstallation")
                progress_w = int(450 * scaling_factor)
                progress_h = int(130 * scaling_factor)
                progress_win.resizable(False, False)
                progress_win.config(bg="#1E1E1E")
                progress_win.transient(self.root)
                progress_win.grab_set()
                self.center_window_on_root(progress_win, progress_w, progress_h)
                
                label = tk.Label(
                    progress_win,
                    text="Uninstalling ViGEmBus Driver...\nPlease authorize the UAC prompt if asked.",
                    fg="white", bg="#1E1E1E",
                    font=scale_font(("Arial", 11, "bold"))
                )
                label.pack(pady=int(40 * scaling_factor))
                
                # Bypassing CMD and launching powershell directly via ShellExecuteExW (runas verb)
                hProcess = self._launch_elevated("powershell.exe", self._ps_hidden_args(uninstall_ps1), progress_win=progress_win)
                if not hProcess:
                    # User cancelled the UAC prompt or it failed
                    progress_win.grab_release()
                    progress_win.destroy()
                    self.show_centered_message("Error", "ViGEmBus uninstallation was cancelled or failed to start (UAC prompt declined).")
                    if discoverer_was_running:
                        self.start_discoverer_thread()
                    return

                proc_exit_code = [0]

                def check_process():
                    if hProcess:
                        res = ctypes.windll.kernel32.WaitForSingleObject(hProcess, 0)
                        if res == WAIT_TIMEOUT:
                            progress_win.after(200, check_process)
                        else:
                            exit_code = wintypes.DWORD()
                            ctypes.windll.kernel32.GetExitCodeProcess(hProcess, ctypes.byref(exit_code))
                            ctypes.windll.kernel32.CloseHandle(hProcess)
                            proc_exit_code[0] = exit_code.value
                            progress_win.grab_release()
                            progress_win.destroy()
                    else:
                        progress_win.grab_release()
                        progress_win.destroy()
                            
                progress_win.after(200, check_process)
                self.root.wait_window(progress_win)
                
                logger.info(f"ViGEmBus uninstaller process exited with code: {proc_exit_code[0]}")
                
                invalidate_driver_status_cache("vigembus")
                status = get_vigembus_status()
                driver_removed_ok = proc_exit_code[0] == 0 and removal_verified(
                    status, verify_vigembus_runtime)
                if driver_removed_ok:
                    CONFIG.vigembus_installed = False
                    CONFIG.save_config()
                    self.show_centered_message("Success", "ViGEmBus driver uninstalled successfully. A system reboot is highly recommended.")
                else:
                    self.show_centered_message(
                        "Error",
                        "ViGEmBus uninstallation failed or left components behind.\n\n"
                        f"Exit code: {proc_exit_code[0]}\n{status.describe()}\n\n"
                        f"Uninstaller details:\n{self._read_vigembus_uninstall_log()}"
                    )
                self.update_driver_button()
            except Exception as e:
                self.show_centered_message("Error", f"Failed to start the uninstaller: {e}")
        else:
            self.show_centered_message("Error", "Could not find uninstall_vigembus.ps1. Please verify the integrity of the application files.")

        if discoverer_was_running:
            self.start_discoverer_thread()
        return bool(locals().get('driver_removed_ok', False))

    def on_driver_btn_clicked(self):
        self.close_settings_popup()
        driver_type = getattr(CONFIG, "driver_type", "WinUHid")
        if driver_type == "ViGEmBus":
            vigem_status = get_vigembus_status()
            if vigem_status.state == VIGEMBUS_HEALTHY:
                if self.ask_centered_yes_no("Uninstall Driver", "Are you sure you want to uninstall the ViGEmBus driver?\n(Requires administrator privileges.)"):
                    self.run_vigembus_uninstall()
            elif vigem_status.state == VIGEMBUS_PARTIAL:
                if self.ask_centered_yes_no(
                    "Repair Driver",
                    "ViGEmBus is partially installed. Clean up all broken nodes and reinstall it?\n\n"
                    f"{vigem_status.describe()}\n\n(Requires administrator privileges.)"
                ):
                    if self.run_vigembus_uninstall():
                        installed = self.install_vigembus_driver(show_success_msg=True)
                        if installed:
                            CONFIG.vigembus_installed = True
                            CONFIG.save_config()
                        self.update_driver_button()
            else:
                installed = self.install_vigembus_driver(show_success_msg=True)
                if installed:
                    CONFIG.vigembus_installed = True
                    CONFIG.save_config()
                self.update_driver_button()
        else:
            self.on_winuhid_manager_driver_action()

    def close_winuhid_driver_manager(self):
        popup = getattr(self, "winuhid_manager_popup", None)
        if popup is not None and popup.winfo_exists():
            popup.destroy()
        self.winuhid_manager_popup = None
        self.winuhid_manager_popup_anchor = None
        bind_id = getattr(self, "winuhid_manager_popup_bind_id", None)
        if bind_id:
            try:
                self.root.unbind("<ButtonPress>", bind_id)
            except Exception:
                pass
            self.winuhid_manager_popup_bind_id = None

    def bind_winuhid_driver_manager_outside_click(self):
        popup = getattr(self, "winuhid_manager_popup", None)
        if popup is None or not popup.winfo_exists():
            return
        bind_id = getattr(self, "winuhid_manager_popup_bind_id", None)
        if bind_id:
            try:
                self.root.unbind("<ButtonPress>", bind_id)
            except Exception:
                pass

        def close_if_outside(event):
            current = getattr(self, "winuhid_manager_popup", None)
            if current is None or not current.winfo_exists():
                self.close_winuhid_driver_manager()
                return
            if self._event_in_widget(current, event):
                return
            if self._event_in_widget(getattr(self, "winuhid_manager_popup_anchor", None), event):
                return
            self.close_winuhid_driver_manager()

        self.winuhid_manager_popup_bind_id = self.root.bind(
            "<ButtonPress>", close_if_outside, add="+")

    def open_winuhid_driver_manager(self, anchor_widget=None):
        anchor_widget = anchor_widget or getattr(self, "driver_frame", None)
        existing = getattr(self, "winuhid_manager_popup", None)
        if (existing is not None and existing.winfo_exists()
                and getattr(self, "winuhid_manager_popup_anchor", None) is anchor_widget):
            self.close_winuhid_driver_manager()
            return
        self.close_winuhid_driver_manager()

        spacing = int(8 * scaling_factor)
        popup = tk.Frame(
            self.root, bg=background_color, bd=1, relief=tk.SOLID,
            padx=spacing, pady=spacing)
        self.winuhid_manager_popup = popup
        self.winuhid_manager_popup_anchor = anchor_widget

        self.winuhid_manager_keyboard_button = tk.Button(
            popup, text="", bg=button_gray, fg=text_color,
            activebackground=button_gray, activeforeground=text_color,
            bd=0, relief=tk.FLAT, font=scale_font(("Arial", 11, "bold")),
            command=self.toggle_winuhid_keyboard_output,
        )
        self.winuhid_manager_keyboard_button.pack(
            fill=tk.X, padx=int(2 * scaling_factor), pady=int(2 * scaling_factor))

        self.winuhid_manager_mouse_button = tk.Button(
            popup, text="", bg=button_gray, fg=text_color,
            activebackground=button_gray, activeforeground=text_color,
            bd=0, relief=tk.FLAT, font=scale_font(("Arial", 11, "bold")),
            command=self.toggle_winuhid_mouse_output,
        )
        self.winuhid_manager_mouse_button.pack(
            fill=tk.X, padx=int(2 * scaling_factor), pady=(spacing, int(2 * scaling_factor)))

        self.winuhid_manager_driver_button = tk.Button(
            popup, text="", bg=button_gray, fg=text_color,
            activebackground=button_gray, activeforeground=text_color,
            bd=0, relief=tk.FLAT, font=scale_font(("Arial", 11, "bold")),
            command=self.on_winuhid_manager_driver_action,
        )
        self.winuhid_manager_driver_button.pack(
            fill=tk.X, padx=int(2 * scaling_factor), pady=(spacing, int(2 * scaling_factor)))

        popup.place(in_=self.root, x=-10000, y=-10000)
        popup.update_idletasks()
        self._place_popup_within_root_bounds(
            popup, anchor_widget, position_adjust=(2, -2))
        self.root.after(100, self.bind_winuhid_driver_manager_outside_click)
        self.refresh_winuhid_driver_manager(initialize_keyboard=True)

    def refresh_winuhid_driver_manager(self, initialize_keyboard=False):
        popup = getattr(self, "winuhid_manager_popup", None)
        if popup is None or not popup.winfo_exists():
            return
        invalidate_driver_status_cache("winuhid")
        status = get_winuhid_status(use_cache=False)
        self._winuhid_manager_status = status
        if status.state == WINUHID_HEALTHY:
            action_text = "Uninstall WinUHid Driver"
        else:
            action_text = "Install WinUHid Driver"
        if initialize_keyboard:
            keyboard_output.initialize()
        self.winuhid_manager_driver_button.config(text=action_text, state=tk.NORMAL)
        keyboard_label = ("WinUHid Virtual HID"
                          if keyboard_output.effective_mode() == keyboard_output.RAW_INPUT
                          else "Win32 API")
        mouse_raw = (raw_input_mouse.requested_mode() == "Raw Input"
                     and status.state == WINUHID_HEALTHY)
        self.winuhid_manager_keyboard_button.config(
            text=f"Keyboard: {keyboard_label}", state=tk.NORMAL)
        self.winuhid_manager_mouse_button.config(
            text=f"Mouse: {'WinUHid Virtual HID' if mouse_raw else 'Win32 API'}", state=tk.NORMAL)

    def on_winuhid_manager_driver_action(self):
        status = get_winuhid_status(use_cache=False)
        if status.state == WINUHID_HEALTHY:
            if self.ask_centered_yes_no(
                    "Uninstall WinUHid Driver",
                    "Uninstall WinUHid and use Win32 API output until it is reinstalled?\n"
                    "(Requires administrator privileges.)"):
                self.run_driver_uninstall()
        elif status.state == WINUHID_PARTIAL:
            if self.ask_centered_yes_no(
                    "Repair WinUHid Driver",
                    "WinUHid is partially installed. Clean up the broken installation "
                    "and reinstall it?\n\n" + status.describe()
                    + "\n\n(Requires administrator privileges.)"):
                if self.run_driver_uninstall():
                    self.run_driver_install()
        else:
            self.run_driver_install()
        self.refresh_winuhid_driver_manager()

    def toggle_winuhid_keyboard_output(self):
        button = getattr(self, "profile_keyboard_output_btn", None)
        if button is not None:
            button.config(state=tk.DISABLED)
        try:
            if keyboard_output.effective_mode() == keyboard_output.RAW_INPUT:
                keyboard_output.activate_standard(save=True)
            else:
                status = get_winuhid_status(use_cache=False)
                if status.state != WINUHID_HEALTHY:
                    return
                if not keyboard_output.activate_raw_input(save=True):
                    self.show_centered_message(
                        "Keyboard Raw Input Error",
                        "The WinUHid driver is present, but the virtual keyboard could not "
                        "be created. Keyboard output remains Standard.")
        finally:
            self.refresh_profile_switching_combo_trigger_ui()

    def toggle_winuhid_mouse_output(self):
        button = getattr(self, "profile_mouse_output_btn", None)
        if button is not None:
            button.config(state=tk.DISABLED)
        try:
            status = get_winuhid_status(use_cache=False)
            effective_raw = (raw_input_mouse.requested_mode() == "Raw Input"
                             and status.state == WINUHID_HEALTHY)
            if effective_raw:
                CONFIG.mouse_output_mode = "Standard"
            else:
                if status.state != WINUHID_HEALTHY:
                    return
                CONFIG.mouse_output_mode = "Raw Input"
            CONFIG.save_config()
            self.wake_controller_mouse_output_reconcile()
        finally:
            self.refresh_profile_switching_combo_trigger_ui()

    def wake_controller_mouse_output_reconcile(self):
        """Wake every physical controller, including Full power-saving sleepers."""
        seen = set()
        for vc in VIRTUAL_CONTROLLERS:
            for controller in (getattr(vc, "controllers", ()) or ()):
                identity = id(controller)
                if identity in seen:
                    continue
                seen.add(identity)
                wake = getattr(controller, "_interp_wake_event", None)
                if wake is not None:
                    wake.set()

    def wired_controller_label(self, sentence=False):
        """UI name for the wired pad(s) currently connected."""
        import gui
        return gui.wired_controller_label(
            getattr(self, "wired_controller_pids", ()) or (), sentence=sentence)

    def update_driver_buttons_visibility(self):
        if not hasattr(self, 'top_btn_frame') or not self.top_btn_frame:
            return
        try:
            if not self.top_btn_frame.winfo_exists():
                return
        except Exception:
            return
        scaling_factor = getattr(self, 'scaling_factor', 1.0)
        
        expected = [
            getattr(self, 'checkbox_frame', None),
            getattr(self, 'edit_profiles_frame', None),
            getattr(self, 'wireless_driver_frame', None),
            getattr(self, 'wired_driver_frame', None),
            getattr(self, 'unified_drivers_frame', None)
        ]
        expected = [f for f in expected if f and f.winfo_exists()]
        try:
            current = self.top_btn_frame.pack_slaves()
        except Exception:
            current = []

        # Only repack if current children do not match expected order
        if current != expected:
            for s in current:
                try:
                    s.pack_forget()
                except Exception:
                    pass
            if hasattr(self, 'checkbox_frame') and self.checkbox_frame.winfo_exists():
                self.checkbox_frame.pack(side=tk.TOP, fill=tk.X, pady=(int(6 * scaling_factor), int(16 * scaling_factor)))
            if hasattr(self, 'edit_profiles_frame') and self.edit_profiles_frame.winfo_exists():
                self.edit_profiles_frame.pack(side=tk.TOP, pady=(0, int(10 * scaling_factor)))
            if hasattr(self, 'wireless_driver_frame') and self.wireless_driver_frame.winfo_exists():
                self.wireless_driver_frame.pack(side=tk.TOP, pady=(0, int(10 * scaling_factor)))
            if hasattr(self, 'wired_driver_frame') and self.wired_driver_frame.winfo_exists():
                self.wired_driver_frame.pack(side=tk.TOP, pady=(0, int(10 * scaling_factor)))
            if hasattr(self, 'unified_drivers_frame') and self.unified_drivers_frame.winfo_exists():
                self.unified_drivers_frame.pack(side=tk.TOP, pady=(0, int(10 * scaling_factor)))

        if hasattr(self, 'wireless_driver_btn') and self.wireless_driver_btn:
            try:
                if self.wireless_driver_btn.winfo_exists():
                    self.wireless_driver_btn.config(text=self.get_wireless_driver_button_text())
            except Exception:
                pass

        if hasattr(self, 'wired_driver_btn') and self.wired_driver_btn:
            try:
                if self.wired_driver_btn.winfo_exists():
                    self.wired_driver_btn.config(text=self.get_wired_driver_button_text())
            except Exception:
                pass

        if hasattr(self, 'unified_drivers_btn') and self.unified_drivers_btn:
            try:
                if self.unified_drivers_btn.winfo_exists():
                    self.unified_drivers_btn.config(text=self.get_unified_drivers_button_text())
            except Exception:
                pass

        try:
            self.update_header_status()
        except Exception:
            pass

    def refresh_driver_ui_status(self):
        """Immediately invalidate driver caches and update buttons and footer status."""
        try:
            invalidate_driver_status_cache("winuhid")
            invalidate_driver_status_cache("hidhide")
            invalidate_driver_status_cache("vigembus")
            invalidate_driver_status_cache("usbip")
            self._sync_hidhide_installed(save=True, use_cache=False)
            self.update_driver_button()
            self.update_header_status()
            self.update_driver_buttons_visibility()
            if hasattr(self, 'root') and self.root:
                self.root.update_idletasks()
        except Exception as e:
            logger.debug("Failed to refresh driver UI status: %s", e)

    def get_wireless_driver_button_text(self):
        try:
            winuhid_state = get_winuhid_status(use_cache=True).state
            if winuhid_state == WINUHID_HEALTHY:
                return "Uninstall Wireless Driver (WinUHid)"
            else:
                return "Install Wireless Driver (WinUHid)"
        except Exception:
            return "Install Wireless Driver (WinUHid)"

    def get_wired_driver_button_text(self):
        try:
            hidhide_installed = self._sync_hidhide_installed(save=False, use_cache=True)
            if hidhide_installed:
                return "Uninstall Wired Driver (HidHide)"
            else:
                return "Install Wired Driver (HidHide)"
        except Exception:
            return "Install Wired Driver (HidHide)"

    def on_wireless_driver_btn_clicked(self):
        self.close_settings_popup()
        winuhid_status = get_winuhid_status(use_cache=True)
        is_installed = (winuhid_status.state == WINUHID_HEALTHY)

        if is_installed:
            if self.ask_centered_yes_no(
                "Uninstall Wireless Driver",
                "Are you sure you want to uninstall the WinUHid wireless driver?\n\n"
                "(Requires administrator privileges.)"
            ):
                self.run_driver_uninstall()
                self.refresh_driver_ui_status()
        else:
            if self.ask_centered_yes_no(
                "Install Wireless Driver",
                "Install the bundled WinUHid driver to enable virtual controller "
                "emulation for wireless Nintendo Switch controllers?\n\n"
                "(Requires administrator privileges.)"
            ):
                self.run_driver_install()
                self.refresh_driver_ui_status()

    def on_wired_driver_btn_clicked(self):
        self.close_settings_popup()
        is_installed = self._sync_hidhide_installed(save=False, use_cache=True)

        if is_installed:
            if self.ask_centered_yes_no(
                "Uninstall Wired Driver",
                "Are you sure you want to uninstall the HidHide wired driver?\n\n"
                "(Requires administrator privileges.)"
            ):
                self.run_hidhide_uninstall()
                self.refresh_driver_ui_status()
        else:
            if self.ask_centered_yes_no(
                "Install Wired Driver",
                "Install the bundled HidHide driver to prevent double-input when "
                "connecting controllers via USB cable?\n\n"
                "(Requires administrator privileges.)"
            ):
                self.run_hidhide_install()
                self.refresh_driver_ui_status()

    def get_unified_drivers_button_text(self):
        try:
            winuhid_state = get_winuhid_status(use_cache=True).state
            hidhide_installed = self._sync_hidhide_installed(save=False, use_cache=True)
            both_installed = (winuhid_state == WINUHID_HEALTHY and hidhide_installed)
            if both_installed:
                return "Uninstall WinUHid & HidHide"
            else:
                return "Install WinUHid & HidHide"
        except Exception:
            return "Install WinUHid & HidHide"

    def on_unified_drivers_btn_clicked(self):
        self.close_settings_popup()
        winuhid_status = get_winuhid_status(use_cache=True)
        hidhide_installed = self._sync_hidhide_installed(save=False, use_cache=True)
        both_installed = (winuhid_status.state == WINUHID_HEALTHY and hidhide_installed)

        if both_installed:
            if self.ask_centered_yes_no(
                "Uninstall Drivers",
                "Are you sure you want to uninstall both WinUHid and HidHide drivers?\n\n"
                "(Requires administrator privileges.)"
            ):
                winuhid_ok = self.run_driver_uninstall(show_success_msg=False)
                hidhide_ok = self.run_hidhide_uninstall(prompt_restart=False, show_success_msg=False)
                self.refresh_driver_ui_status()
                if winuhid_ok and hidhide_ok:
                    if self.ask_centered_yes_no(
                        "Drivers Uninstalled",
                        "WinUHid and HidHide drivers have been uninstalled.\n\n"
                        "A restart is recommended to complete driver removal.\n\nRestart now?"
                    ):
                        try:
                            import subprocess
                            subprocess.Popen(["shutdown", "/r", "/t", "0"])
                        except Exception as e:
                            self.show_centered_message("Error", f"Could not restart automatically: {e}\nPlease restart manually.")
        else:
            if self.ask_centered_yes_no(
                "Install Drivers",
                "Install the bundled WinUHid and HidHide drivers so both wireless "
                "and wired controllers work seamlessly without double-input?\n\n"
                "- WinUHid enables virtual controller emulation for wireless play.\n"
                "- HidHide prevents double-input when using wired USB connections.\n\n"
                "(Requires administrator privileges.)"
            ):
                winuhid_ok = True
                if winuhid_status.state != WINUHID_HEALTHY:
                    winuhid_ok = self.run_driver_install(show_success_msg=False)
                
                hidhide_ok = True
                if not self._sync_hidhide_installed(save=False):
                    hidhide_ok = self.run_hidhide_install(prompt_restart=False, show_success_msg=False)

                self.refresh_driver_ui_status()
                if winuhid_ok and hidhide_ok:
                    self.show_centered_message(
                        "Drivers Setup Complete",
                        "WinUHid and HidHide drivers have been installed successfully.\n\n"
                        "Both wireless and wired controllers are now fully supported!"
                    )

    def update_driver_button(self):
        if hasattr(self, 'wireless_driver_btn') and self.wireless_driver_btn:
            try:
                if self.wireless_driver_btn.winfo_exists():
                    self.wireless_driver_btn.config(text=self.get_wireless_driver_button_text())
            except Exception:
                pass
        if hasattr(self, 'wired_driver_btn') and self.wired_driver_btn:
            try:
                if self.wired_driver_btn.winfo_exists():
                    self.wired_driver_btn.config(text=self.get_wired_driver_button_text())
            except Exception:
                pass
        if hasattr(self, 'unified_drivers_btn') and self.unified_drivers_btn:
            try:
                if self.unified_drivers_btn.winfo_exists():
                    self.unified_drivers_btn.config(text=self.get_unified_drivers_button_text())
            except Exception:
                pass
        if hasattr(self, 'driver_btn') and self.driver_btn:
            try:
                if self.driver_btn.winfo_exists():
                    driver_type = getattr(CONFIG, "driver_type", "WinUHid")
                    if driver_type == "ViGEmBus":
                        vigem_state = get_vigembus_status(use_cache=True).state
                        text = ("Uninstall ViGEmBus Driver" if vigem_state == VIGEMBUS_HEALTHY
                                else "Repair ViGEmBus Driver" if vigem_state == VIGEMBUS_PARTIAL
                                else "Install ViGEmBus Driver")
                    else:
                        winuhid_state = get_winuhid_status(use_cache=True).state
                        text = ("Uninstall WinUHid Driver" if winuhid_state == WINUHID_HEALTHY
                                else "Install WinUHid Driver")
                    self.driver_btn.config(text=text)
            except Exception:
                pass
        self.update_driver_buttons_visibility()
        try:
            self.update_header_status()
        except Exception:
            pass

    def update_usbip_button(self):
        if not hasattr(self, 'usbip_btn') or not self.usbip_btn:
            return
        if getattr(self, "_usbip_restart_pending", False):
            self.usbip_btn.config(text="Restart Required")
            self.update_driver_buttons_visibility()
            return
        # Only a genuinely half-installed driver offers "Repair"; USBIP_UNKNOWN
        # falls through to "Install", which cleans up first and cannot dead-end.
        usbip_state = get_usbip_status(use_cache=True).state
        text = ("Uninstall USBIP Driver" if usbip_state == USBIP_HEALTHY
                else "Repair USBIP Driver" if usbip_state == USBIP_PARTIAL
                else "Install USBIP Driver")
        self.usbip_btn.config(text=text)
        self.update_driver_buttons_visibility()

    def on_usbip_btn_clicked(self):
        self.close_settings_popup()
        if getattr(self, "_usbip_restart_pending", False):
            self._prompt_usbip_restart_required()
            return
        install_warning = (
            "WARNING: During the installation of USBIP-win2, Windows USB hubs will restart briefly, "
            "which will temporarily disconnect other USB peripherals (mice, keyboards, etc.).\n\n"
            "Do you want to proceed?\n(Requires administrator privileges.)"
        )
        status = get_usbip_status()
        if status.state == USBIP_HEALTHY:
            if self.ask_centered_yes_no("Uninstall USBIP Driver", "Are you sure you want to uninstall the USBIP driver?\n(Requires administrator privileges.)"):
                self.run_usbip_uninstall()
        elif status.state == USBIP_PARTIAL:
            if self.ask_centered_yes_no(
                "Repair USBIP Driver",
                "USBIP is partially installed. Remove the broken installation now?\n\n"
                f"{status.describe()}\n\nWindows must be restarted before USBIP can be installed again.\n\n"
                "Removing USBIP requires administrator privileges."
            ):
                self.run_usbip_uninstall()
        else:
            if status.unknown:
                logger.warning("USBIP status undetermined: %s", status.describe())
            if self.ask_centered_yes_no(
                "Install USBIP Driver",
                "Are you sure you want to install the USBIP driver?\n\n" + install_warning
            ):
                self.run_usbip_install()

    def run_usbip_install(self, show_success_msg=True):
        # Install USBIP from the bundled installer (both builds); nothing downloaded.
        import os

        # Stop discoverer before installation
        discoverer_was_running = False
        if hasattr(self, 'discoverer_thread') and self.discoverer_thread and self.discoverer_thread.is_alive():
            discoverer_was_running = True
            self.stop_discoverer_thread()

        # Run emergency cleanup to close all virtual controller handles immediately
        from discoverer import emergency_cleanup
        emergency_cleanup()

        packaged_install = utils.is_packaged()
        install_payload = get_driver_path(
            "USBip-0.9.7.7-x64.exe" if packaged_install else "install_usbip.ps1")
        if os.path.exists(install_payload):
            try:
                progress_win = tk.Toplevel(self.root)
                progress_win.title("USBIP Driver Installation")
                progress_w = int(450 * scaling_factor)
                progress_h = int(130 * scaling_factor)
                progress_win.resizable(False, False)
                progress_win.config(bg="#1E1E1E")
                progress_win.transient(self.root)
                progress_win.grab_set()
                self.center_window_on_root(progress_win, progress_w, progress_h)
                
                label = tk.Label(
                    progress_win,
                    text="Installing USBIP-win2 Driver...\nPlease authorize the UAC prompt if asked.",
                    fg="white", bg="#1E1E1E",
                    font=scale_font(("Arial", 11, "bold"))
                )
                label.pack(pady=int(40 * scaling_factor))
                
                if packaged_install:
                    # Match the packaged ViGEmBus path: elevate the installer itself.
                    # The former PowerShell -> Start-Process nesting could fail when
                    # its payload lived under the protected WindowsApps directory.
                    usbip_args = (
                        '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART '
                        '/MERGETASKS="!desktopicon"'
                    )
                    hProcess = self._launch_elevated(
                        install_payload,
                        usbip_args,
                        progress_win=progress_win,
                        lp_dir=os.path.dirname(install_payload),
                    )
                else:
                    # Preserve the established standalone .exe installation path.
                    hProcess = self._launch_elevated(
                        "powershell.exe",
                        self._ps_hidden_args(install_payload),
                        progress_win=progress_win,
                    )
                if not hProcess:
                    # User cancelled the UAC prompt or it failed
                    progress_win.grab_release()
                    progress_win.destroy()
                    self.show_centered_message("Error", "USBIP driver installation was cancelled or failed to start (UAC prompt declined).")
                    if discoverer_was_running:
                        self.start_discoverer_thread()
                    return

                proc_exit_code = [0]
                verified_status = [None]
                verify_delays_ms = (0, 1000, 1000, 2000, 4000)  # cumulative 0, 1, 2, 4, 8 s

                def finish_verification(attempt=0):
                    installed = False
                    try:
                        invalidate_driver_status_cache("usbip")
                        status = get_usbip_status()
                        verified_status[0] = status
                        installed = status.installed or (
                            status.unknown
                            and os.path.exists(utils.get_usbip_exe_path()))
                    except Exception as exc:
                        logger.warning(
                            "USBIP post-install verification attempt %s failed: %s",
                            attempt + 1,
                            exc,
                        )
                    if installed or attempt >= len(verify_delays_ms) - 1:
                        progress_win.grab_release()
                        progress_win.destroy()
                        return
                    progress_win.after(
                        verify_delays_ms[attempt + 1],
                        lambda: finish_verification(attempt + 1),
                    )

                def check_process():
                    if hProcess:
                        res = ctypes.windll.kernel32.WaitForSingleObject(hProcess, 0)
                        if res == WAIT_TIMEOUT:
                            progress_win.after(200, check_process)
                        else:
                            exit_code = wintypes.DWORD()
                            ctypes.windll.kernel32.GetExitCodeProcess(hProcess, ctypes.byref(exit_code))
                            ctypes.windll.kernel32.CloseHandle(hProcess)
                            proc_exit_code[0] = exit_code.value
                            label.config(text="Finalizing USBIP-win2 Driver installation...")
                            finish_verification()
                    else:
                        progress_win.grab_release()
                        progress_win.destroy()
                            
                progress_win.after(200, check_process)
                self.root.wait_window(progress_win)
                
                logger.info(f"USBIP driver installer process exited with code: {proc_exit_code[0]}")
                
                usbip_status = verified_status[0]
                if usbip_status is None:
                    invalidate_driver_status_cache("usbip")
                    usbip_status = get_usbip_status()
                usbip_installed_ok = usbip_status.installed or (
                    usbip_status.unknown
                    and os.path.exists(utils.get_usbip_exe_path()))
                if usbip_installed_ok:
                    self._usbip_restart_pending = False
                    if proc_exit_code[0] != 0:
                        logger.warning(
                            "USBIP installer returned code %s but final verification succeeded",
                            proc_exit_code[0],
                        )
                    if show_success_msg:
                        self.show_centered_message("Success", "USBIP-win2 driver installed successfully.")
                else:
                    self.show_centered_message(
                        "Error",
                        "USBIP driver installation was not completed or failed.\n\n"
                        f"Exit code: {proc_exit_code[0]}\n{usbip_status.describe()}"
                    )
                self.update_usbip_button()
            except Exception as e:
                self.show_centered_message("Error", f"Failed to start the USBIP installer: {e}")
        else:
            self.show_centered_message(
                "Error",
                f"Could not find {os.path.basename(install_payload)}. "
                "Please verify the integrity of the application files.",
            )

        self._cleanup_driver_desktop_shortcuts()
        if discoverer_was_running:
            self.start_discoverer_thread()

    def _prompt_usbip_restart_required(self):
        """Remind the user that USBIP remains pending removal until reboot."""
        if not self.ask_centered_yes_no(
            "Restart Required",
            "A restart is required to finish removing USBIP.\n\nRestart now?",
        ):
            return
        try:
            import subprocess
            subprocess.Popen(["shutdown", "/r", "/t", "0"])
        except Exception as exc:
            self.show_centered_message(
                "Error",
                f"Could not restart automatically: {exc}\nPlease restart manually.",
            )

    def run_usbip_uninstall(self):
        # Both builds invoke the registered Inno uninstaller directly. USBIP keeps
        # driver components loaded until reboot, so do not inspect or clean them up
        # synchronously after a successful uninstall.
        import os

        # Stop discoverer before uninstallation
        discoverer_was_running = False
        if hasattr(self, 'discoverer_thread') and self.discoverer_thread and self.discoverer_thread.is_alive():
            discoverer_was_running = True
            self.stop_discoverer_thread()
            
        # Run emergency cleanup to close all virtual controller handles immediately
        from discoverer import emergency_cleanup
        emergency_cleanup()

        uninstaller_exe = os.path.join(utils.get_usbip_dir(), "unins000.exe")
        if not os.path.exists(uninstaller_exe):
            self.show_centered_message(
                "Error",
                "Could not find the USBIP uninstaller. Reinstall USBIP, then try "
                "uninstalling it again.",
            )
            if discoverer_was_running:
                self.start_discoverer_thread()
            return False

        proc_exit_code = [None]
        try:
            progress_win = tk.Toplevel(self.root)
            progress_win.title("USBIP Driver Uninstallation")
            progress_w = int(450 * scaling_factor)
            progress_h = int(130 * scaling_factor)
            progress_win.resizable(False, False)
            progress_win.config(bg="#1E1E1E")
            progress_win.transient(self.root)
            progress_win.grab_set()
            self.center_window_on_root(progress_win, progress_w, progress_h)

            tk.Label(
                progress_win,
                text="Running USBIP-win2 Uninstaller...\nPlease authorize the UAC prompt if asked.",
                fg="white", bg="#1E1E1E",
                font=scale_font(("Arial", 11, "bold"))
            ).pack(pady=int(40 * scaling_factor))

            # Both MSIX and standalone builds elevate the Inno uninstaller itself.
            hProcess = self._launch_elevated(
                uninstaller_exe, "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART",
                progress_win=progress_win, lp_dir=utils.get_usbip_dir())
            if not hProcess:
                progress_win.grab_release()
                progress_win.destroy()
                self.show_centered_message("Error", "USBIP driver uninstallation was cancelled or failed to start (UAC prompt declined).")
                if discoverer_was_running:
                    self.start_discoverer_thread()
                return False

            def check_process():
                if hProcess:
                    res = ctypes.windll.kernel32.WaitForSingleObject(hProcess, 0)
                    if res == WAIT_TIMEOUT:
                        progress_win.after(200, check_process)
                    else:
                        exit_code = wintypes.DWORD()
                        ctypes.windll.kernel32.GetExitCodeProcess(hProcess, ctypes.byref(exit_code))
                        ctypes.windll.kernel32.CloseHandle(hProcess)
                        proc_exit_code[0] = exit_code.value
                        progress_win.grab_release()
                        progress_win.destroy()
                else:
                    progress_win.grab_release()
                    progress_win.destroy()

            progress_win.after(200, check_process)
            self.root.wait_window(progress_win)

            logger.info(f"USBIP driver uninstaller process exited with code: {proc_exit_code[0]}")
        except Exception as e:
            self.show_centered_message("Error", f"Failed to start the USBIP uninstaller: {e}")
            if discoverer_was_running:
                self.start_discoverer_thread()
            return False

        if proc_exit_code[0] != 0:
            self.show_centered_message(
                "Error",
                "USBIP uninstallation failed.\n\n"
                f"Exit code: {proc_exit_code[0]}",
            )
            if discoverer_was_running:
                self.start_discoverer_thread()
            return False

        # Do not call get_usbip_status/update_usbip_button here. The loaded USBIP
        # driver, services and device node are expected to remain until reboot.
        self._usbip_restart_pending = True
        if hasattr(self, "usbip_btn") and self.usbip_btn:
            self.usbip_btn.config(text="Restart Required")

        if discoverer_was_running:
            self.start_discoverer_thread()
        self.show_centered_message(
            "Success",
            "USBIP removal started. A restart is required to complete the uninstall.",
        )
        self._prompt_usbip_restart_required()
        return True

    def _sync_hidhide_installed(self, save=True, use_cache=True):
        """Refresh the cached and persisted HidHide flag without guessing.

        Returns the effective installed flag. An undeterminable state keeps the
        previous answer rather than persisting a wrong False.
        """
        try:
            status = get_hidhide_status(use_cache=use_cache)
            state = status.installed
        except Exception:
            state = hidhide_service_state()
        if state is None:
            logger.warning("HidHide state undetermined; keeping the previous value.")
            return bool(getattr(CONFIG, "hidhide_installed", False))
        self._hidhide_installed_cached = state
        CONFIG.hidhide_installed = state
        if save:
            CONFIG.save_config()
        return state

    def on_hidhide_button(self):
        installed = self._sync_hidhide_installed(save=False, use_cache=True)
        if installed:
            if self.ask_centered_yes_no("Uninstall HidHide", "Uninstall the HidHide driver?\n(Requires administrator privileges.)"):
                self.run_hidhide_uninstall()
        else:
            if self.ask_centered_yes_no(
                "Install HidHide",
                f"{self.wired_controller_label(sentence=True)} detected.\n\nHidHide "
                "hides the physical controller's HID so games only see the virtual "
                "controller. Install it now?\n(Requires administrator privileges.)",
            ):
                self.run_hidhide_install()

    def ask_hidhide_auto_install(self):
        """Show the automatic HidHide prompt with a persistent opt-out checkbox."""
        dialog_w = int(520 * scaling_factor)
        dialog_h = int(260 * scaling_factor)
        dialog = tk.Toplevel(self.root)
        dialog.title("Install HidHide")
        dialog.resizable(False, False)
        dialog.config(bg="#1E1E1E")
        dialog.transient(self.root)
        dialog.grab_set()
        self.center_window_on_root(dialog, dialog_w, dialog_h)

        result = {"install": False}
        suppress_var = tk.BooleanVar(value=False)

        tk.Label(
            dialog,
            text=(
                f"{self.wired_controller_label(sentence=True)} detected.\n\n"
                "HidHide hides the controller's physical HID so games only see "
                "the virtual controller (no double input).\n\n"
                "Install it now?\n(Requires administrator privileges.)"
            ),
            fg="white",
            bg="#1E1E1E",
            font=scale_font(("Arial", 11, "bold")),
            justify=tk.CENTER,
            wraplength=int(460 * scaling_factor),
        ).pack(padx=int(24 * scaling_factor), pady=(int(22 * scaling_factor), int(10 * scaling_factor)))

        tk.Checkbutton(
            dialog,
            text="Do not show again",
            variable=suppress_var,
            bg="#1E1E1E",
            fg="white",
            activebackground="#1E1E1E",
            activeforeground="white",
            selectcolor=button_gray,
            font=scale_font(("Arial", 10)),
        ).pack(pady=(0, int(12 * scaling_factor)))

        button_frame = tk.Frame(dialog, bg="#1E1E1E")
        button_frame.pack(pady=(0, int(18 * scaling_factor)))

        def close(install):
            result["install"] = bool(install)
            if suppress_var.get():
                CONFIG.hidhide_install_prompt_suppressed = True
                CONFIG.save_config()
            try:
                dialog.grab_release()
            except tk.TclError:
                pass
            dialog.destroy()

        for text, install in (("Yes", True), ("No", False)):
            frame = tk.Frame(button_frame, bg=button_gray)
            frame.pack(side=tk.LEFT, padx=int(6 * scaling_factor))
            tk.Button(
                frame,
                text=text,
                bg=button_gray,
                fg=text_color,
                bd=0,
                relief=tk.FLAT,
                font=scale_font(("Arial", 10, "bold")),
                width=8,
                command=lambda value=install: close(value),
            ).pack(padx=int(2 * scaling_factor), pady=int(2 * scaling_factor))

        dialog.protocol("WM_DELETE_WINDOW", lambda: close(False))
        self.root.wait_window(dialog)
        return result["install"]


    def on_wired_usb_driver_button(self):
        self.close_settings_popup()
        # WinUSB is auto-installed by the controller's MS OS descriptor, so the only
        # optional driver here is HidHide. If it's not installed, prompt to install it
        # directly (a centered notification). If it is installed, open a small options
        # window to enable/disable filtering or uninstall.
        hidhide_installed = self._sync_hidhide_installed()
        self.update_driver_buttons_visibility()

        if not hidhide_installed:
            if self.ask_centered_yes_no(
                "Install HidHide",
                "HidHide hides the controller's physical HID so games only see the virtual "
                "controller (no double input). Install it now?\n"
                "(Optional. Requires administrator privileges.)",
            ):
                self.run_hidhide_install(prompt_restart=True)
            return

        # HidHide installed → options window (enable/disable filtering, uninstall).
        try:
            import hidhide
            hidhide_active = hidhide.is_active()
        except Exception:
            hidhide_active = False

        dialog_w = int(460 * scaling_factor)
        dialog_h = int(210 * scaling_factor)
        dialog = tk.Toplevel(self.root)
        dialog.title("HidHide")
        dialog.resizable(False, False)
        dialog.config(bg="#1E1E1E")
        dialog.transient(self.root)
        dialog.grab_set()
        self.center_window_on_root(dialog, dialog_w, dialog_h)

        info_label = tk.Label(
            dialog, text="", fg="white", bg="#1E1E1E",
            font=scale_font(("Arial", 11, "bold")), justify=tk.LEFT,
        )
        info_label.pack(pady=(int(16 * scaling_factor), int(10 * scaling_factor)), padx=int(16 * scaling_factor), anchor=tk.W)

        sel_frame = tk.Frame(dialog, bg="#1E1E1E")
        sel_frame.pack(pady=int(8 * scaling_factor))
        buttons = {}

        def refresh():
            if not dialog.winfo_exists():
                return
            nonlocal hidhide_active
            info_label.config(
                text=(
                    "HidHide (hides the physical controller from games)\n"
                    f"Status: Installed\n"
                    f"Filtering: {'Enabled' if hidhide_active else 'Disabled'}"
                )
            )
            if "active" in buttons and buttons["active"].winfo_exists():
                # While a toggle is being applied/verified the button stays locked so
                # rapid re-clicks can't start a competing write.
                if getattr(self, "_hidhide_toggle_in_progress", False):
                    buttons["active"].config(text="Applying...", state=tk.DISABLED)
                else:
                    buttons["active"].config(
                        text=("Disable HidHide" if hidhide_active else "Enable HidHide"),
                        state=tk.NORMAL
                    )

        def recheck_and_refresh():
            nonlocal hidhide_installed, hidhide_active
            hidhide_installed = self._sync_hidhide_installed()
            try:
                import hidhide
                hidhide_active = hidhide.is_active() if hidhide_installed else False
            except Exception:
                hidhide_active = False
            self.update_driver_buttons_visibility()
            if not hidhide_installed and dialog.winfo_exists():
                dialog.destroy()
                return
            refresh()

        def toggle_hidhide_active():
            # Guard against rapid re-clicks: only one toggle may be in flight. The button is
            # locked for the whole lock → write → verify → unlock cycle so the displayed and
            # stored state always reflects what was actually written to the driver.
            if getattr(self, "_hidhide_toggle_in_progress", False):
                return
            if not ("active" in buttons and buttons["active"].winfo_exists()):
                return
            self._hidhide_toggle_in_progress = True
            buttons["active"].config(state=tk.DISABLED, text="Applying...")
            dialog.update_idletasks()

            def unlock_and_refresh():
                self._hidhide_toggle_in_progress = False
                recheck_and_refresh()

            # Capture the intended target once, from the current live driver state.
            try:
                import hidhide
                if hidhide_service_state() is not True:
                    unlock_and_refresh()
                    return
                target_active = not hidhide.is_active()
            except Exception as e:
                logger.error(f"Failed to read HidHide state: {e}")
                unlock_and_refresh()
                return

            max_attempts = 5

            def attempt(n):
                success = False
                try:
                    import hidhide
                    if target_active:
                        self._hide_detected_pro2_with_hidhide()
                        hidhide.set_active(True)
                    else:
                        self._unhide_detected_pro2_with_hidhide()
                        hidhide.set_active(False)
                    # Verify the write actually landed rather than trusting the IOCTL return.
                    success = (hidhide.is_active() == target_active)
                except Exception as e:
                    logger.error(f"Failed to toggle HidHide (attempt {n}): {e}")

                if success:
                    # Persist the preference so the wired watcher won't re-hide (and thus
                    # re-activate) the controller on the next replug after a Disable.
                    CONFIG.hidhide_hide_enabled = target_active
                    CONFIG.save_config()
                    unlock_and_refresh()
                    return
                if n < max_attempts and dialog.winfo_exists():
                    # Retry until the driver confirms the new state (or attempts run out).
                    dialog.after(150, lambda: attempt(n + 1))
                    return
                unlock_and_refresh()
                if dialog.winfo_exists():
                    self.show_centered_message(
                        "Error",
                        "Failed to apply HidHide setting.\n\nPlease make sure 'HidHide Configuration Client' is CLOSED."
                    )

            # Give the kernel driver a moment before the first write/verify.
            dialog.after(50, lambda: attempt(1))

        def uninstall_hidhide():
            # Close this modal options window first so its grab doesn't keep the app in
            # the foreground — otherwise the elevated UAC prompt only flashes in the
            # taskbar. run_hidhide_uninstall refreshes the top-bar button on its own.
            if dialog.winfo_exists():
                dialog.grab_release()
                dialog.destroy()
            self.run_hidhide_uninstall()

        for key, command in (
            ("active", toggle_hidhide_active),
            ("uninstall", uninstall_hidhide),
        ):
            frame = tk.Frame(sel_frame, bg=button_gray)
            frame.pack(side=tk.LEFT, padx=int(4 * scaling_factor))
            btn = tk.Button(
                frame, text=("Uninstall HidHide" if key == "uninstall" else ""),
                bg=button_gray, fg=text_color, bd=0, relief=tk.FLAT,
                font=scale_font(("Arial", 10, "bold")), width=15, command=command,
            )
            btn.pack(padx=int(2 * scaling_factor), pady=int(2 * scaling_factor))
            buttons[key] = btn

        close_btn_frame = tk.Frame(dialog, bg=button_gray)
        close_btn_frame.pack(pady=int(10 * scaling_factor))
        tk.Button(
            close_btn_frame, text="Close", bg=button_gray, fg=text_color,
            bd=0, relief=tk.FLAT, font=scale_font(("Arial", 10, "bold")), width=8,
            command=dialog.destroy,
        ).pack(padx=int(2 * scaling_factor), pady=int(2 * scaling_factor))

        refresh()

    def _hide_detected_pro2_with_hidhide(self):
        try:
            import hidhide
            from usb_hid_controller import enumerate_wired_controllers
            for entry in enumerate_wired_controllers(reason="hidhide_action"):
                instance_id = hidhide.hid_path_to_instance_id(entry.get("path"))
                if instance_id:
                    hidhide.hide_device(instance_id)
        except Exception as e:
            logger.debug("Failed to add detected wired controller to HidHide: %s", e)

    def _unhide_detected_pro2_with_hidhide(self):
        try:
            import hidhide
            from usb_hid_controller import enumerate_wired_controllers
            for entry in enumerate_wired_controllers(reason="hidhide_action"):
                instance_id = hidhide.hid_path_to_instance_id(entry.get("path"))
                if instance_id:
                    hidhide.unhide_device(instance_id)
        except Exception as e:
            logger.debug("Failed to remove detected wired controller from HidHide: %s", e)

    def _run_hidhide_script(self, script_name, wait_text):
        """Run a bundled HidHide install/uninstall PowerShell script elevated (runas),
        blocking until it exits. Returns the process exit code, or None on cancel/error."""
        ps1 = get_driver_path(os.path.join("hidhide", script_name))
        if not os.path.exists(ps1):
            self.show_centered_message("Error", f"Could not find {script_name}. Please verify the application files.")
            return None
        exit_code = [None]
        try:
            progress_win = tk.Toplevel(self.root)
            progress_win.title("HidHide")
            progress_win.resizable(False, False)
            progress_win.config(bg="#1E1E1E")
            progress_win.transient(self.root)
            progress_win.grab_set()
            self.center_window_on_root(progress_win, int(450 * scaling_factor), int(130 * scaling_factor))
            tk.Label(progress_win, text=wait_text, fg="white", bg="#1E1E1E",
                     font=scale_font(("Arial", 11, "bold"))).pack(pady=int(40 * scaling_factor))

            hProcess = self._launch_elevated(
                "powershell.exe", self._ps_hidden_args(ps1), progress_win=progress_win)
            if not hProcess:
                progress_win.grab_release()
                progress_win.destroy()
                self.show_centered_message("Error", "HidHide operation was cancelled (UAC prompt declined).")
                return None

            def check_process():
                if hProcess and ctypes.windll.kernel32.WaitForSingleObject(hProcess, 0) == WAIT_TIMEOUT:
                    progress_win.after(200, check_process)
                else:
                    if hProcess:
                        code = wintypes.DWORD()
                        ctypes.windll.kernel32.GetExitCodeProcess(hProcess, ctypes.byref(code))
                        exit_code[0] = code.value
                        ctypes.windll.kernel32.CloseHandle(hProcess)
                    progress_win.grab_release()
                    progress_win.destroy()

            progress_win.after(200, check_process)
            self.root.wait_window(progress_win)
        except Exception as e:
            self.show_centered_message("Error", f"Failed to run HidHide operation: {e}")
        return exit_code[0]

    def run_hidhide_install(self, prompt_restart=True, show_success_msg=True):
        # Install HidHide from the bundled installer script (both builds); nothing downloaded.
        code = self._run_hidhide_script("install_hidhide.ps1", "Installing HidHide...\nPlease authorize the UAC prompt if asked.")
        if code is None:
            return False  # cancelled / could not start
        ok = self._sync_hidhide_installed(save=True)
        self._cleanup_driver_desktop_shortcuts()
        self.refresh_driver_ui_status()

        if code not in (0, 3010) and not ok:
            invalidate_driver_status_cache("hidhide")
            self.show_centered_message(
                "Error",
                "HidHide installation did not complete.\n\n"
                f"Exit code: {code}\n{get_hidhide_status().describe()}")
            return False

        # Centered success notification (on the main window).
        if show_success_msg:
            self.show_centered_message("Success", "HidHide installed successfully.")

        # HidHide's filter driver needs a reboot to attach to already-connected
        # controllers. Ask the user first — never auto-restart.
        if prompt_restart and self.ask_centered_yes_no(
            "Restart Required",
            "A restart is required to finish HidHide setup and hide the physical "
            "controller.\n\nRestart now?",
        ):
            try:
                import subprocess
                subprocess.Popen(["shutdown", "/r", "/t", "0"])
            except Exception as e:
                self.show_centered_message("Error", f"Could not restart automatically: {e}\nPlease restart manually.")
        return bool(ok or code in (0, 3010))

    def run_hidhide_uninstall(self, prompt_restart=True, show_success_msg=True):
        # Uninstall from the bundled script (both builds); nothing downloaded.
        code = self._run_hidhide_script("uninstall_hidhide.ps1", "Uninstalling HidHide...\nPlease authorize the UAC prompt if asked.")
        if code is None:
            return False  # cancelled / could not start
        invalidate_driver_status_cache("hidhide")
        self._sync_hidhide_installed(save=True, use_cache=False)
        self.refresh_driver_ui_status()

        hidhide_status = get_hidhide_status(use_cache=False)
        is_gone = (code in (0, 3010)) or hidhide_status.absent

        if not is_gone:
            log_path = os.path.join(
                os.environ.get("TEMP", ""), "Switch2Connect_HidHide_uninstall.log")
            try:
                with open(log_path, "r", encoding="utf-8-sig", errors="replace") as stream:
                    details = stream.read().strip().splitlines()[-12:]
                detail_text = "\n\n" + "\n".join(details) if details else ""
            except OSError:
                detail_text = ""
            self.show_centered_message(
                "Error",
                "HidHide uninstallation failed or left the driver service installed."
                f"\n\nExit code: {code}{detail_text}",
            )
            return False

        # The service and package are gone, but the loaded driver file may remain
        # pending removal until reboot. Report the pending restart without restoring
        # the Installed state in the UI.
        if show_success_msg:
            self.show_centered_message(
                "Success",
                "HidHide removal started. A restart is required to complete the uninstall.",
            )
        if prompt_restart and self.ask_centered_yes_no(
            "Restart Required",
            "A restart is required to finish removing HidHide.\n\nRestart now?",
        ):
            try:
                import subprocess
                subprocess.Popen(["shutdown", "/r", "/t", "0"])
            except Exception as e:
                self.show_centered_message("Error", f"Could not restart automatically: {e}\nPlease restart manually.")
        return True

