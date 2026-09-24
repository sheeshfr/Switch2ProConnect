import ctypes
from ctypes import wintypes
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk, filedialog
import webbrowser
from PIL import Image, ImageTk

from config import CONFIG, get_resource
from gyro import GYRO_PHASE0_RECORDER
from mag_tester import export_recorded_file, mag_tester_build_enabled
from discoverer import request_wired_rescan, set_wired_auto_scan_enabled
from gui_widgets import (
    ToggleSwitch,
    get_checkbox_images,
    create_tooltip,
    COLOR_OFF,
    COLOR_OFF_HOVER,
    COLOR_OFF_PRESS,
    COLOR_ON,
    COLOR_ON_HOVER,
    COLOR_ON_PRESS,
)

logger = logging.getLogger(__name__)

background_color = "#2D2D2D"
button_gray = "#4B4B4B"
highlight_color = "#00C3E3"
text_color = "#FFFFFF"

APP_VERSION = "v1.0"

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

class _MagTesterBuildProxy:
    def __bool__(self):
        import gui
        return bool(getattr(gui, "MAG_TESTER_BUILD_ENABLED", False))

MAG_TESTER_BUILD_ENABLED = _MagTesterBuildProxy()

def scale_font(font_tuple):
    import gui
    return gui.scale_font(font_tuple)

def make_rounded_button(*args, **kwargs):
    import gui
    return gui.make_rounded_button(*args, **kwargs)

def set_rounded_button_bg(*args, **kwargs):
    import gui
    return gui.set_rounded_button_bg(*args, **kwargs)

def update_toggle_button(*args, **kwargs):
    import gui
    return gui.update_toggle_button(*args, **kwargs)

def _top_level_hwnd(w):
    import gui
    return gui._top_level_hwnd(w)

def hidhide_service_state():
    import gui
    return gui.hidhide_service_state()

def __getattr__(name):
    import gui
    if hasattr(gui, name):
        return getattr(gui, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

class ControllerWindowSettingsMixin:
    def _close_kofi_window(self):
        pass

    def _mag_tester_value_color(value):
        normalized = str(value).strip().lower()
        blocking_terms = (
            "blocked", "rejected", "missing", "not available",
            "unavailable", "interference", "recovering", "suspended",
            "invalid", "waiting", "collecting", "frozen", "reset",
            "mismatch", "noise", "error", "failed", "adapting",
        )
        if any(term in normalized for term in blocking_terms):
            return "#ff9f0a"
        if re.search(r"\b(valid|accepted|allowed|ready)\b", normalized):
            return "#30d158"
        return text_color

    def open_mag_tester(self):
        if not MAG_TESTER_BUILD_ENABLED:
            return
        if (self.mag_tester_window is not None
                and self.mag_tester_window.winfo_exists()):
            self.mag_tester_window.lift()
            self.mag_tester_window.focus_force()
            return

        GYRO_PHASE0_RECORDER.set_monitoring(True)
        popup = tk.Toplevel(self.root)
        self.mag_tester_window = popup
        popup.title("Mag Tester")
        popup.configure(bg=background_color)
        popup.resizable(False, False)
        popup.transient(self.root)
        popup.protocol("WM_DELETE_WINDOW", self._close_mag_tester)

        content = tk.Frame(popup, bg=background_color)
        content.pack(fill=tk.BOTH, expand=True, padx=int(14 * scaling_factor),
                     pady=int(12 * scaling_factor))

        indicators = tk.LabelFrame(
            content, text="Real-time Indicators", bg=background_color,
            fg=text_color, bd=1, relief=tk.GROOVE,
            font=scale_font(("Arial", 11, "bold")))
        indicators.pack(fill=tk.X)

        tk.Label(indicators, text="Controller:", bg=background_color,
                 fg=text_color, font=scale_font(("Arial", 10, "bold"))).grid(
                     row=0, column=0, sticky="e", padx=8, pady=(8, 4))
        self.mag_tester_controller_var = tk.StringVar(value="")
        self.mag_tester_controller_combo = ttk.Combobox(
            indicators, textvariable=self.mag_tester_controller_var,
            state="readonly", width=34)
        self.mag_tester_controller_combo.grid(
            row=0, column=1, sticky="w", padx=8, pady=(8, 4))

        rows = (
            ("status", "Magnetometer Status"),
            ("magnitude", "Magnitude / Reference / Ratio"),
            ("motion", "Motion State"),
            ("confidence", "Model Confidence / Effective Authority / Eligibility"),
            ("confidence_state", "Confidence State"),
            ("heading", "Model State"),
            ("bias", "Bias Observation / Estimate"),
            ("correction", "Candidate / Pass / In-App Correction"),
            ("budget", "Pass / In-App Correction Debt Remaining | Used"),
            ("accumulated", "Pass / In-App Epoch | Session Correction"),
            ("blocked", "Blocked Reason"),
        )
        self.mag_tester_values = {}
        for row_index, (key, title) in enumerate(rows, start=1):
            tk.Label(indicators, text=f"{title}:", bg=background_color,
                     fg=text_color,
                     font=scale_font(("Arial", 10, "bold"))).grid(
                         row=row_index, column=0, sticky="e", padx=8, pady=2)
            value = tk.Label(
                indicators, text="Waiting for controller data",
                bg=background_color, fg="#AAAAAA", anchor="w",
                justify=tk.LEFT, width=68,
                font=scale_font(("Consolas", 10)))
            value.grid(row=row_index, column=1, sticky="w", padx=8, pady=2)
            self.mag_tester_values[key] = value

        controls = tk.Frame(content, bg=background_color)
        controls.pack(fill=tk.X, pady=(12, 0))
        self.mag_tester_record_border = tk.Frame(
            controls, bg=background_color, highlightbackground="#ff453a",
            highlightcolor="#ff453a", highlightthickness=0, bd=0)
        self.mag_tester_record_border.pack(side=tk.LEFT)
        self.mag_tester_record_button = tk.Button(
            self.mag_tester_record_border, text="Start Recording",
            command=self._toggle_mag_tester_recording,
            bg=button_gray, fg="white", bd=0, relief=tk.FLAT,
            font=scale_font(("Arial", 10, "bold")))
        self.mag_tester_record_button.pack(padx=2, pady=2)
        self.mag_tester_export_button = tk.Button(
            controls, text="Export Recorded File",
            command=self._export_mag_tester_recording,
            bg=button_gray, fg="white", bd=0, relief=tk.FLAT,
            state=(tk.NORMAL if self.mag_tester_last_recording else tk.DISABLED),
            font=scale_font(("Arial", 10, "bold")))
        self.mag_tester_export_button.pack(side=tk.LEFT, padx=(10, 0))

        self.mag_tester_file_label = tk.Label(
            content, text="No recording in this session.",
            bg=background_color, fg="#888888", anchor="w",
            justify=tk.LEFT, height=2,
            wraplength=int(930 * scaling_factor),
            font=scale_font(("Arial", 9)))
        self.mag_tester_file_label.pack(fill=tk.X, pady=(8, 0))

        popup.update_idletasks()
        # Size from the actual widgets so the long diagnostic values are not
        # clipped and the popup does not retain the old fixed empty area below
        # the recording controls.
        requested_width = popup.winfo_reqwidth()
        requested_height = popup.winfo_reqheight()
        popup_width = max(
            requested_width + int(8 * scaling_factor),
            int(980 * scaling_factor))
        popup_height = requested_height + int(8 * scaling_factor)
        popup_width = min(
            popup_width, max(1, int(popup.winfo_screenwidth() * 0.95)))
        popup_height = min(
            popup_height, max(1, int(popup.winfo_screenheight() * 0.90)))
        self.center_window_on_root(
            popup, popup_width, popup_height)
        self._set_mag_tester_recording_ui(GYRO_PHASE0_RECORDER.is_recording)
        self._refresh_mag_tester()

    def _set_mag_tester_recording_ui(self, recording):
        button = getattr(self, "mag_tester_record_button", None)
        border = getattr(self, "mag_tester_record_border", None)
        if button is None or border is None:
            return
        button.config(text=("Stop Recording" if recording
                            else "Start Recording"))
        border.config(highlightthickness=(2 if recording else 0))
        export = getattr(self, "mag_tester_export_button", None)
        if export is not None:
            export.config(state=(
                tk.NORMAL if not recording and self.mag_tester_last_recording
                else tk.DISABLED))

    def _toggle_mag_tester_recording(self):
        if self.mag_tester_stop_pending:
            return
        if GYRO_PHASE0_RECORDER.is_recording:
            self.mag_tester_stop_pending = True
            self.mag_tester_record_button.config(state=tk.DISABLED)

            def stop_worker():
                path = GYRO_PHASE0_RECORDER.stop_recording(timeout=5.0)
                try:
                    self.root.after(0, self._finish_mag_tester_stop, path)
                except RuntimeError:
                    pass

            threading.Thread(target=stop_worker, daemon=True).start()
            return

        directory = os.path.dirname(CONFIG.config_file_path)
        filename = f"mag-tester-{time.strftime('%Y%m%d-%H%M%S')}.txt"
        path = os.path.join(directory, filename)
        started = GYRO_PHASE0_RECORDER.start_recording(
            path, text_mode=True,
            metadata={
                "App_Version": APP_VERSION,
                "Format": "tab-separated values",
                "Config_Directory": directory,
            })
        if not started:
            self.show_centered_message(
                "Mag Tester", "Unable to start recording. Check the console log for details.")
            return
        self.mag_tester_last_recording = None
        self.mag_tester_file_label.config(text=f"Recording: {path}")
        self._set_mag_tester_recording_ui(True)

    def _finish_mag_tester_stop(self, path):
        self.mag_tester_stop_pending = False
        button = getattr(self, "mag_tester_record_button", None)
        if button is not None:
            button.config(state=tk.NORMAL)
        path = os.fspath(path) if path is not None else ""
        if path and os.path.isfile(path):
            self.mag_tester_last_recording = path
            self.mag_tester_file_label.config(text=f"Recorded: {path}")
        else:
            self.mag_tester_file_label.config(text="Recording did not create a file.")
        error = GYRO_PHASE0_RECORDER.writer_error
        if error is not None:
            self.mag_tester_file_label.config(text=f"Recording error: {error}")
        self._set_mag_tester_recording_ui(False)

    def _export_mag_tester_recording(self):
        source = self.mag_tester_last_recording
        if not source or not os.path.isfile(source):
            self.show_centered_message("Mag Tester", "No completed recording is available.")
            return
        self.app_profile_poll_suspended = True
        try:
            destination = filedialog.asksaveasfilename(
                parent=self.mag_tester_window or self.root,
                title="Choose Export Location",
                defaultextension=".txt",
                filetypes=[("Text files", "*.txt")],
                initialfile=os.path.basename(source))
        finally:
            self.app_profile_poll_suspended = False
        if not destination:
            return
        if not destination.lower().endswith(".txt"):
            destination = os.path.splitext(destination)[0] + ".txt"
        try:
            exported = export_recorded_file(source, destination)
            self.mag_tester_last_recording = None
            self.mag_tester_export_button.config(state=tk.DISABLED)
            self.mag_tester_file_label.config(
                text=f"Exported: {exported}\nTemporary recording removed.")
        except Exception as exc:
            self.show_centered_message("Mag Tester", f"Export failed: {exc}")

    def _refresh_mag_tester(self):
        popup = self.mag_tester_window
        if popup is None or not popup.winfo_exists():
            return
        snapshots = GYRO_PHASE0_RECORDER.latest_snapshots()
        choices = sorted(snapshots)
        combo = self.mag_tester_controller_combo
        if list(combo.cget("values")) != choices:
            combo.config(values=choices)
        selected = self.mag_tester_controller_var.get()
        if selected not in snapshots and choices:
            selected = choices[0]
            self.mag_tester_controller_var.set(selected)
        item = snapshots.get(selected)
        if item:
            robust_bias_mode = item["correction_law"] == "RobustBiasRate"
            model_confidence = (
                item["robust_bias_confidence"] if robust_bias_mode
                else item["consistency_confidence"])
            if robust_bias_mode:
                if item["robust_bias_valid_buckets"] < 10:
                    model_state = "Warming Up"
                elif item["robust_bias_decay_active"]:
                    model_state = "Observation Aging / Estimate Decaying"
                else:
                    model_state = "Bias Tracking"
                heading_text = (
                    f'{model_state} / bias age '
                    f'{item["robust_bias_observation_age_seconds"]:.2f} s / '
                    f'transient {item["transient_event_error_deg"]:+.2f} deg')
                bias_text = (
                    f'{item["robust_bias_raw_observation_dps"]:+.3f} / '
                    f'{item["robust_bias_bounded_observation_dps"]:+.3f} / '
                    f'{item["robust_bias_estimate_dps"]:+.3f} dps'
                    f' ({item["robust_bias_valid_buckets"]} samples)')
                budget_text = (
                    f'{item["pass_transient_debt_remaining_deg"]:+.3f} / '
                    f'{item["in_app_transient_debt_remaining_deg"]:+.3f} | '
                    f'{item["pass_transient_debt_used_deg"]:.3f} / '
                    f'{item["in_app_transient_debt_used_deg"]:.3f} deg '
                    '(Transient)')
            else:
                heading_text = (
                    f'{item["committed_heading_error_deg"]:+.3f} deg / '
                    f'{item["residual_state"]}')
                bias_text = (
                    f'{item["observed_bias_rate_dps"]:+.3f} dps / '
                    f'{"Accepted" if item["bias_rate_valid"] and item["commit_scale_valid"] else "Rejected"}')
                budget_text = (
                    f'{item["pass_repayment_budget_remaining_deg"]:.3f} / '
                    f'{item["in_app_repayment_budget_remaining_deg"]:.3f} | '
                    f'{item["pass_repayment_budget_used_deg"]:.3f} / '
                    f'{item["in_app_repayment_budget_used_deg"]:.3f} deg')
            values = {
                "calibration": ("Accepted" if item["calibration_accepted"]
                                else "Not Available"),
                "status": (
                    f'{item["mag_status"]} / '
                    f'{"Calibration Accepted" if item["calibration_accepted"] else "Calibration Missing"}'),
                "model": item.get("calibration_model") or "Unavailable",
                "magnitude": (f'{item["magnitude"]:.3f} / '
                              f'{item["reference_magnitude"]:.3f} LSB / '
                              f'{item["magnitude_ratio"]:.4f}'),
                "ratio": f'{item["magnitude_ratio"]:.4f}',
                "direction": "Yes" if item["direction_valid"] else "No",
                "heading": heading_text,
                "bias": bias_text,
                "filtered_heading": (
                    f'{item["consumer_measurement_deg"]:+.3f} deg'),
                "delta_gate": (
                    f'{item["relative_delta_innovation_deg"]:+.3f} deg / '
                    f'{"Yes" if item["relative_delta_rejected"] else "No"}'),
                "gyro_relative": (
                    f'{item["gyro_relative_heading_deg"]:+.3f} deg'),
                "mag_relative": (
                    f'{item["magnetic_relative_heading_deg"]:+.3f} deg'),
                "raw_mag_delta": (
                    f'{item["raw_magnetic_heading_delta_deg"]:+.6f} deg'),
                "norm_mag_delta": (
                    f'{item["normalized_magnetic_heading_delta_deg"]:+.6f} deg'),
                "gyro_yaw_delta": (
                    f'{item["gyro_world_yaw_delta_deg"]:+.6f} deg'),
                "gyro_heading_delta": (
                    f'{item["gyro_reference_heading_delta_deg"]:+.6f} deg'),
                "direction_agreement": (
                    "Yes" if item["heading_delta_direction_agreement"]
                    else "No"),
                "absolute_innovation": (
                    f'{item["absolute_heading_innovation_deg"]:+.3f} deg'),
                "motion": item["motion_state"],
                "rate": f'{item["gyro_yaw_rate_dps"]:+.3f} dps',
                "confidence": (
                    f'{model_confidence * 100.0:.1f}% / '
                    f'{item["confidence"] * 100.0:.1f}% / '
                    f'{"Allowed" if item["correction_eligible"] else "Blocked"}'),
                "confidence_state": (
                    f'{item["confidence_state"]} / '
                    f'{"Authority Suspended" if item["authority_suspended"] else "Authority Available"}'),
                "correction": (
                    f'{item["candidate_correction_dps"]:+.6f} / '
                    f'{item["pass_applied_correction_dps"]:+.6f} / '
                    f'{item["in_app_applied_correction_dps"]:+.6f} dps'),
                "budget": budget_text,
                "accumulated": (
                    f'{item["pass_accumulated_correction_deg"]:+.3f} / '
                    f'{item["in_app_accumulated_correction_deg"]:+.3f} | '
                    f'{item["pass_session_accumulated_correction_deg"]:+.3f} / '
                    f'{item["in_app_session_accumulated_correction_deg"]:+.3f} deg'),
                "consistency": (
                    f'{item["consistency_correlation"]:.3f} / '
                    f'{item["consistency_scale"]:.3f} / '
                    f'{item["consistency_confidence"] * 100.0:.1f}%'),
                "epoch": (
                    f'{item["measurement_epoch"]} / '
                    f'{item["heading_gravity_source"]}'),
                "window": (
                    f'{item["residual_state"]} / '
                    f'{item["window_magnetic_delta_deg"]:+.3f} / '
                    f'{item["window_gyro_delta_deg"]:+.3f} deg'),
                "committed": (
                    f'{item["committed_heading_error_deg"]:+.3f} deg'),
                "eligible": ("Allowed" if item["correction_eligible"]
                             else "Blocked"),
                "law": item["correction_law"],
                "raw_target": (
                    f'{item["raw_correction_demand_dps"]:+.6f} dps'),
                "target": f'{item["confidence_target_dps"]:+.6f} dps',
                "cap": f'{item["dynamic_safety_cap_dps"]:.6f} dps',
                "slew": (f'{item["attack_slew_dps_per_second"]:.6f} '
                         'dps/s'),
                "limit": item["limiting_reason"],
                "candidate": f'{item["candidate_correction_dps"]:+.6f} dps',
                "pass": f'{item["pass_applied_correction_dps"]:+.6f} dps',
                "pass_feedback": (
                    f'{item["pass_consumer_residual_deg"]:+.3f} / '
                    f'{item["pass_accumulated_correction_deg"]:+.3f} deg / '
                    f'{item["pass_reentry_ramp_progress"] * 100.0:.0f}% / '
                    f'Inv {"OK" if item["pass_invariant_valid"] else "FAIL"}'),
                "inapp": f'{item["in_app_applied_correction_dps"]:+.6f} dps',
                "inapp_feedback": (
                    f'{item["in_app_consumer_residual_deg"]:+.3f} / '
                    f'{item["in_app_accumulated_correction_deg"]:+.3f} deg / '
                    f'{item["in_app_reentry_ramp_progress"] * 100.0:.0f}% / '
                    f'Inv {"OK" if item["in_app_invariant_valid"] else "FAIL"}'),
                "blocked": ", ".join(item["blocked_reasons"]) or "None",
            }
            for key, label in self.mag_tester_values.items():
                value = values[key]
                label.config(
                    text=value, fg=self._mag_tester_value_color(value))
        self.mag_tester_refresh_after_id = popup.after(
            150, self._refresh_mag_tester)

    def _close_mag_tester(self):
        if self.mag_tester_stop_pending:
            self.root.after(100, self._close_mag_tester)
            return
        if GYRO_PHASE0_RECORDER.is_recording:
            path = GYRO_PHASE0_RECORDER.stop_recording(timeout=5.0)
            if path is not None and os.path.isfile(path):
                self.mag_tester_last_recording = os.fspath(path)
        popup = self.mag_tester_window
        if popup is not None and self.mag_tester_refresh_after_id is not None:
            try:
                popup.after_cancel(self.mag_tester_refresh_after_id)
            except tk.TclError:
                pass
        self.mag_tester_refresh_after_id = None
        GYRO_PHASE0_RECORDER.set_monitoring(False)
        if popup is not None and popup.winfo_exists():
            popup.destroy()
        self.mag_tester_window = None


    def _apply_dark_title_bar(self, window):
        try:
            from gui_widgets import apply_window_dark_theme_and_icon
            apply_window_dark_theme_and_icon(window, background_color)
        except Exception:
            pass

    def _add_popout_finish_button(self, parent, on_finish, show_about=False):
        finish_row = tk.Frame(parent, bg=background_color)
        finish_row.pack(side=tk.BOTTOM, fill=tk.X, pady=(int(8 * scaling_factor), 0))
        if show_about:
            about_btn = make_rounded_button(
                finish_row,
                text="About",
                width=75,
                height=30,
                radius=6,
                bg_color=button_gray,
                hover_color="#5A5A5A",
                press_color="#3A3A3A",
                parent_bg=background_color,
                font=scale_font(("Arial", 9, "bold")),
                command=self.open_about_popup
            )
            about_btn.pack(side=tk.LEFT)
        btn = make_rounded_button(
            finish_row,
            text="Finish",
            width=75,
            height=30,
            radius=6,
            bg_color=button_gray,
            hover_color=highlight_color,
            fg="white",
            font=scale_font(("Arial", 9, "bold")),
            command=on_finish
        )
        btn.pack(side=tk.RIGHT)
        return btn

    def init_settings_popup(self, parent=None):
        parent = parent or self.root
        scaling_factor = getattr(self, 'scaling_factor', 1.0)
        spacing = int(10 * scaling_factor)
        popup = tk.Frame(parent, bg=background_color, padx=spacing, pady=spacing)
        popup.pack(fill=tk.BOTH, expand=True)
        self.settings_popup = popup

        self.top_btn_frame = tk.Frame(popup, bg=background_color)
        self.top_btn_frame.pack(side=tk.TOP, fill=tk.X)

        # Checkbox images for dark theme
        self.cb_img_uncheck, self.cb_img_check = get_checkbox_images(size_px=18, scaling=scaling_factor)

        # Preferences Checkboxes Container (Top of Settings window)
        self.checkbox_frame = tk.Frame(self.top_btn_frame, bg=background_color)
        self.checkbox_frame.pack(side=tk.TOP, fill=tk.X, pady=(int(6 * scaling_factor), int(16 * scaling_factor)))

        # Row 1: Run At Startup (left) & Start Minimized (right)
        self.cb_row1 = tk.Frame(self.checkbox_frame, bg=background_color)
        self.cb_row1.pack(side=tk.TOP)

        is_st_on = bool(CONFIG.open_when_startup)
        self.startup_var = tk.BooleanVar(value=is_st_on)
        self.startup_cb = tk.Checkbutton(
            self.cb_row1,
            text="  Run At Startup",
            variable=self.startup_var,
            image=self.cb_img_uncheck,
            selectimage=self.cb_img_check,
            indicatoron=False,
            compound="left",
            bg=background_color,
            fg="white",
            activebackground=background_color,
            activeforeground="white",
            selectcolor=background_color,
            bd=0,
            relief=tk.FLAT,
            font=scale_font(("Arial", 10, "bold")),
            cursor="hand2",
            command=lambda: self.update_startup_setting(self.startup_var.get())
        )
        self.startup_cb.pack(side=tk.LEFT, padx=(0, int(20 * scaling_factor)))

        is_min_on = bool(CONFIG.start_minimized)
        self.minimized_var = tk.BooleanVar(value=is_min_on)
        self.minimized_cb = tk.Checkbutton(
            self.cb_row1,
            text="  Start Minimized",
            variable=self.minimized_var,
            image=self.cb_img_uncheck,
            selectimage=self.cb_img_check,
            indicatoron=False,
            compound="left",
            bg=background_color,
            fg="white",
            activebackground=background_color,
            activeforeground="white",
            selectcolor=background_color,
            bd=0,
            relief=tk.FLAT,
            font=scale_font(("Arial", 10, "bold")),
            cursor="hand2",
            command=lambda: self.update_minimized_setting(self.minimized_var.get())
        )
        self.minimized_cb.pack(side=tk.LEFT)

        # Row 2: Power Saving (centered below)
        self.cb_row2 = tk.Frame(self.checkbox_frame, bg=background_color)
        self.cb_row2.pack(side=tk.TOP, pady=(int(8 * scaling_factor), 0))

        is_ps_on = getattr(CONFIG, "power_saving_mode", "Off") != "Off"
        self.power_saving_var = tk.BooleanVar(value=is_ps_on)
        self.power_saving_cb = tk.Checkbutton(
            self.cb_row2,
            text="  Power Saving",
            variable=self.power_saving_var,
            image=self.cb_img_uncheck,
            selectimage=self.cb_img_check,
            indicatoron=False,
            compound="left",
            bg=background_color,
            fg="white",
            activebackground=background_color,
            activeforeground="white",
            selectcolor=background_color,
            bd=0,
            relief=tk.FLAT,
            font=scale_font(("Arial", 10, "bold")),
            cursor="hand2",
            command=self._on_power_saving_checkbox_toggled
        )
        self.power_saving_cb.pack(side=tk.TOP)
        create_tooltip(
            self.power_saving_cb,
            "reduces windows background processes to save laptop/handheld device battery life"
        )

        # Edit Profiles Button (Middle button 1)
        self.edit_profiles_frame = tk.Frame(self.top_btn_frame, bg=background_color)
        self.edit_profiles_btn = make_rounded_button(
            self.edit_profiles_frame,
            text="Edit Profiles",
            width=300,
            height=36,
            radius=6,
            bg_color=button_gray,
            hover_color="#5A5A5A",
            press_color="#3A3A3A",
            parent_bg=background_color,
            command=self.open_edit_profiles_dialog
        )
        self.edit_profiles_btn.pack(side=tk.TOP)
        self.edit_profiles_frame.pack(side=tk.TOP, pady=(0, int(10 * scaling_factor)))

        # Wireless Driver (WinUHid) Button
        self.wireless_driver_frame = tk.Frame(self.top_btn_frame, bg=background_color)
        self.wireless_driver_btn = make_rounded_button(
            self.wireless_driver_frame,
            text=self.get_wireless_driver_button_text(),
            width=300,
            height=36,
            radius=6,
            bg_color=button_gray,
            hover_color="#5A5A5A",
            press_color="#3A3A3A",
            parent_bg=background_color,
            command=self.on_wireless_driver_btn_clicked
        )
        self.wireless_driver_btn.pack(side=tk.TOP)
        self.wireless_driver_frame.pack(side=tk.TOP, pady=(0, int(10 * scaling_factor)))

        # Wired Driver (HidHide) Button
        self.wired_driver_frame = tk.Frame(self.top_btn_frame, bg=background_color)
        self.wired_driver_btn = make_rounded_button(
            self.wired_driver_frame,
            text=self.get_wired_driver_button_text(),
            width=300,
            height=36,
            radius=6,
            bg_color=button_gray,
            hover_color="#5A5A5A",
            press_color="#3A3A3A",
            parent_bg=background_color,
            command=self.on_wired_driver_btn_clicked
        )
        self.wired_driver_btn.pack(side=tk.TOP)
        self.wired_driver_frame.pack(side=tk.TOP, pady=(0, int(10 * scaling_factor)))

        self.unified_drivers_frame = tk.Frame(self.top_btn_frame, bg=background_color)
        self.unified_drivers_btn = None


        # Unused individual driver frames kept for compatibility without packing
        self.driver_frame = tk.Frame(self.top_btn_frame, bg=background_color)
        self.driver_btn = None
        self.usbip_frame = tk.Frame(self.top_btn_frame, bg=background_color)
        self.usbip_btn = None
        self.wired_pro_settings_frame = tk.Frame(self.top_btn_frame, bg=background_color)
        self.wired_pro_settings_btn = None
        self.esp32s3_frame = tk.Frame(self.top_btn_frame, bg=background_color)
        self.esp32s3_btn = None
        self.hidhide_frame = tk.Frame(self.top_btn_frame, bg=background_color)
        self.hidhide_btn = None
        self.power_saving_btn = None
        self.startup_btn = None
        self.minimized_btn = None

        self.power_saving_btn = None
        self.startup_btn = None
        self.minimized_btn = None

    def _on_power_saving_checkbox_toggled(self):
        new_val = self.power_saving_var.get()
        if new_val:
            if not self._confirm_power_saving_mode("Auto"):
                self.power_saving_var.set(False)
                return
            target = "Auto"
        else:
            target = "Off"

        import power_saving
        previous_mode = getattr(CONFIG, "power_saving_mode", "Off")
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
        if hasattr(self, "power_saving_btn") and self.power_saving_btn and self.power_saving_btn.winfo_exists():
            update_toggle_button(self.power_saving_btn, target != "Off", "Power Saving")

    def toggle_settings_popup(self):
        if hasattr(self, "settings_window") and self.settings_window is not None and self.settings_window.winfo_exists():
            self.close_settings_popup()
        else:
            self.open_settings_popup()

    def open_settings_popup(self):
        if hasattr(self, "settings_window") and self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.lift()
            self.settings_window.focus_set()
            return

        self.settings_window = tk.Toplevel(self.root)
        self.settings_window.withdraw()
        self.settings_window.title("Settings")
        self.settings_window.resizable(False, False)
        self.settings_window.configure(bg=background_color, padx=int(14 * scaling_factor), pady=int(12 * scaling_factor))
        self.settings_window.transient(self.root)
        self._apply_dark_title_bar(self.settings_window)

        self.init_settings_popup(parent=self.settings_window)
        self.update_driver_button()
        self.update_usbip_button()

        self._add_popout_finish_button(self.settings_window, self.close_settings_popup, show_about=True)

        self.settings_window.update_idletasks()
        req_w = max(int(360 * scaling_factor), self.settings_window.winfo_reqwidth())
        req_h = self.settings_window.winfo_reqheight()
        self.center_window_on_root(self.settings_window, req_w, req_h)
        self.settings_window.protocol("WM_DELETE_WINDOW", self.close_settings_popup)
        self.settings_window.deiconify()
        self.settings_window.lift(self.root)
        self.settings_window.focus_force()

    def close_settings_popup(self):
        if hasattr(self, "about_window") and self.about_window is not None and self.about_window.winfo_exists():
            self.close_about_popup()
        if hasattr(self, "settings_window") and self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.destroy()
        self.settings_window = None
        self.driver_btn = None
        self.wireless_driver_btn = None
        self.wired_driver_btn = None
        self.unified_drivers_btn = None
        self.usbip_btn = None
        self.power_saving_btn = None
        self.esp32s3_btn = None
        self.minimized_btn = None
        self.startup_btn = None
        self.power_saving_cb = None
        self.startup_cb = None
        self.minimized_cb = None
        self.power_saving_var = None
        self.startup_var = None
        self.minimized_var = None
        self.top_btn_frame = None

    def open_about_popup(self):
        owner = (self.settings_window if hasattr(self, "settings_window")
                 and self.settings_window is not None
                 and self.settings_window.winfo_exists()
                 and self.settings_window.winfo_viewable()
                 else self.root)

        if hasattr(self, "about_window") and self.about_window is not None and self.about_window.winfo_exists():
            try:
                self.about_window.transient(owner)
                self.about_window.lift(owner)
                self.about_window.focus_force()
                self.about_window.attributes("-topmost", True)
                self.about_window.after(100, lambda: self.about_window and self.about_window.winfo_exists() and self.about_window.attributes("-topmost", False))
            except Exception:
                pass
            return

        import webbrowser
        scaling_factor = getattr(self, "scaling_factor", 1.0)
        about_win = tk.Toplevel(owner)
        about_win.withdraw()
        about_win.title("About Switch 2 Pro Connect (ShFr UI Mod)")
        about_win.resizable(False, False)
        about_win.configure(bg=background_color, padx=int(24 * scaling_factor), pady=int(20 * scaling_factor))
        about_win.transient(owner)
        self._apply_dark_title_bar(about_win)
        self.about_window = about_win
        about_win._owner = owner

        content = tk.Frame(about_win, bg=background_color)
        content.pack(fill=tk.BOTH, expand=True)

        # Logo Image with full transparency
        try:
            from config import get_resource
            from PIL import Image, ImageTk
            logo_path = get_resource("images/icon.png")
            if logo_path and os.path.exists(logo_path):
                raw_logo = Image.open(logo_path).convert("RGBA")
                logo_sz = int(64 * scaling_factor)
                raw_logo = raw_logo.resize((logo_sz, logo_sz), Image.Resampling.LANCZOS)
                self._about_logo_img = ImageTk.PhotoImage(raw_logo)
                logo_lbl = tk.Label(content, image=self._about_logo_img, bg=background_color)
                logo_lbl.pack(pady=(0, int(8 * scaling_factor)))
        except Exception:
            pass

        # Title & Version
        title_lbl = tk.Label(
            content,
            text=f"Switch 2 Pro Connect {APP_VERSION} (ShFr UI Mod)",
            fg="white",
            bg=background_color,
            font=scale_font(("Arial", 14, "bold"))
        )
        title_lbl.pack(pady=(0, int(2 * scaling_factor)))

        # Copyright
        cp_lbl = tk.Label(
            content,
            text="Copyright (C) 2026  TommyWabg",
            fg="#AAAAAA",
            bg=background_color,
            font=scale_font(("Arial", 9))
        )
        cp_lbl.pack(pady=(0, int(12 * scaling_factor)))

        # Fork & Credits box
        credit_frame = tk.Frame(
            content,
            bg="#23272A",
            padx=int(14 * scaling_factor),
            pady=int(10 * scaling_factor),
            highlightbackground="#3E444D",
            highlightthickness=1
        )
        credit_frame.pack(fill=tk.X, pady=(0, int(14 * scaling_factor)))

        mod_lbl = tk.Label(
            credit_frame,
            text="Forked and vibecode modded by SheeshFr.",
            fg="#81C784",
            bg="#23272A",
            font=scale_font(("Arial", 9, "bold")),
            justify=tk.CENTER
        )
        mod_lbl.pack()

        thanks_lbl = tk.Label(
            credit_frame,
            text="Thanks to TommyWabg and all the rest for their hard work!",
            fg="white",
            bg="#23272A",
            font=scale_font(("Arial", 9)),
            justify=tk.CENTER
        )
        thanks_lbl.pack(pady=(int(4 * scaling_factor), 0))

        # Warranty Notice
        warn_lbl = tk.Label(
            content,
            text="This program comes with ABSOLUTELY NO WARRANTY;\nfor details see the license.",
            fg="#CCCCCC",
            bg=background_color,
            font=scale_font(("Arial", 9)),
            justify=tk.CENTER
        )
        warn_lbl.pack(pady=(0, int(6 * scaling_factor)))

        # Redistribution Notice
        redist_lbl = tk.Label(
            content,
            text="This is free software, and you are welcome to redistribute it under certain conditions.",
            fg="#CCCCCC",
            bg=background_color,
            font=scale_font(("Arial", 9)),
            justify=tk.CENTER,
            wraplength=int(340 * scaling_factor)
        )
        redist_lbl.pack(pady=(0, int(10 * scaling_factor)))

        # License Hyperlink
        def open_license(event=None):
            url = "https://github.com/TommyWabg/Switch2Connect/blob/main/LICENSE.md"
            try:
                webbrowser.open(url)
            except Exception:
                import os
                loc = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "LICENSE.md"))
                if os.path.exists(loc):
                    os.startfile(loc)

        link_lbl = tk.Label(
            content,
            text="GNU General Public License v3 (GPL-3.0)",
            fg="#4EA8DE",
            bg=background_color,
            font=scale_font(("Arial", 10, "underline")),
            cursor="hand2"
        )
        link_lbl.pack(pady=(0, int(16 * scaling_factor)))
        link_lbl.bind("<Button-1>", open_license)
        link_lbl.bind("<Enter>", lambda e: link_lbl.config(fg="#90CAF9"))
        link_lbl.bind("<Leave>", lambda e: link_lbl.config(fg="#4EA8DE"))

        # Close Button
        close_btn = make_rounded_button(
            content,
            text="Close",
            width=80,
            height=30,
            radius=6,
            bg_color=button_gray,
            hover_color="#5A5A5A",
            press_color="#3A3A3A",
            parent_bg=background_color,
            command=self.close_about_popup
        )
        close_btn.pack(side=tk.BOTTOM)

        about_win.bind("<Escape>", lambda e: self.close_about_popup())
        about_win.protocol("WM_DELETE_WINDOW", self.close_about_popup)

        about_win.update_idletasks()
        req_w = max(int(400 * scaling_factor), about_win.winfo_reqwidth())
        req_h = about_win.winfo_reqheight()
        self.center_window_on_root(about_win, req_w, req_h, owner=owner)
        about_win.deiconify()
        about_win.lift(owner)
        about_win.focus_force()
        try:
            about_win.attributes("-topmost", True)
            about_win.after(100, lambda: about_win.winfo_exists() and about_win.attributes("-topmost", False))
        except Exception:
            pass

    def close_about_popup(self):
        owner = None
        if hasattr(self, "about_window") and self.about_window is not None and self.about_window.winfo_exists():
            owner = getattr(self.about_window, "_owner", None)
            try:
                self.about_window.grab_release()
            except Exception:
                pass
            self.about_window.destroy()
        self.about_window = None
        if owner and owner != self.root and hasattr(owner, "winfo_exists") and owner.winfo_exists():
            try:
                owner.lift()
                owner.focus_set()
            except Exception:
                pass

    def init_rumble_popup(self):
        pass

    def toggle_rumble_popup(self):
        if hasattr(self, "rumble_window") and self.rumble_window is not None and self.rumble_window.winfo_exists():
            self.close_rumble_popup()
        else:
            self.open_rumble_popup()

    def open_rumble_popup(self):
        self.close_settings_popup()
        if hasattr(self, "rumble_window") and self.rumble_window is not None and self.rumble_window.winfo_exists():
            self.rumble_window.lift()
            self.rumble_window.focus_set()
            return

        self.rumble_window = tk.Toplevel(self.root)
        self.rumble_window.title("Rumble Settings")
        self.rumble_window.resizable(False, False)
        self.rumble_window.configure(bg=background_color, padx=int(14 * scaling_factor), pady=int(12 * scaling_factor))

        # Row 1: Rumble Mode
        row_vibration = tk.Frame(self.rumble_window, bg=background_color)
        row_vibration.pack(side=tk.TOP, fill=tk.X, pady=int(5 * scaling_factor))
        tk.Label(row_vibration, text="Rumble Mode:", bg=background_color, fg=text_color, font=scale_font(("Arial", 11, "bold")), width=12, anchor=tk.W).pack(side=tk.LEFT, padx=(0, int(5 * scaling_factor)))
        self.rumble_mode_switch = ToggleSwitch(row_vibration, ["Xbox", "Switch"], ["Xbox", "Switch"], getattr(CONFIG, "rumble_mode", "Xbox"), self.update_rumble_mode_setting, background_color)
        self.rumble_mode_switch.pack(side=tk.LEFT, padx=int(2 * scaling_factor))
        self.audio_haptics_button = tk.Button(row_vibration, text="Audio Haptics Settings", command=lambda: self.open_audio_haptics_settings(self.audio_haptics_button), font=scale_font(("Arial", 10, "bold")), bg=button_gray, fg=text_color, relief=tk.FLAT, bd=0, activebackground=highlight_color, padx=int(6 * scaling_factor))
        self.impulse_trigger_button = tk.Button(row_vibration, text="Impulse Trigger Settings", command=lambda: self.open_impulse_trigger_settings(self.impulse_trigger_button), font=scale_font(("Arial", 10, "bold")), bg=button_gray, fg=text_color, relief=tk.FLAT, bd=0, activebackground=highlight_color, padx=int(6 * scaling_factor))
        self.update_dynamic_rumble_mode_options()

        # Row 2: Strength
        row_strength = tk.Frame(self.rumble_window, bg=background_color)
        row_strength.pack(side=tk.TOP, fill=tk.X, pady=int(5 * scaling_factor))
        self.strength_label = tk.Label(row_strength, text="Strength:", bg=background_color, fg=text_color, font=scale_font(("Arial", 11, "bold")), width=12, anchor=tk.W)
        self.strength_label.pack(side=tk.LEFT, padx=(0, int(5 * scaling_factor)))
        self.vibration_strength_scale = tk.Scale(row_strength, from_=0, to=10, resolution=1, orient=tk.HORIZONTAL, length=int(120 * scaling_factor), bg=background_color, fg=text_color, troughcolor=button_gray, activebackground=highlight_color, highlightthickness=0, bd=0, sliderrelief=tk.FLAT, sliderlength=int(15 * scaling_factor), width=int(15 * scaling_factor), font=scale_font(("Arial", 11, "bold")), command=self.update_vibration_strength)
        self.vibration_strength_scale.set(getattr(CONFIG, "vibration_strength", 5))
        self.vibration_strength_scale.pack(side=tk.LEFT)

        # Row 3: Frequency
        self.row_vibration_freq = tk.Frame(self.rumble_window, bg=background_color)
        self.row_vibration_freq.pack(side=tk.TOP, fill=tk.X, pady=int(5 * scaling_factor))
        self.vibration_frequency_label = tk.Label(self.row_vibration_freq, text="Frequency:", bg=background_color, fg=text_color, font=scale_font(("Arial", 11, "bold")), width=12, anchor=tk.W)
        self.vibration_frequency_label.pack(side=tk.LEFT, padx=(0, int(5 * scaling_factor)))
        self.vibration_frequency_scale = tk.Scale(self.row_vibration_freq, from_=1, to=10, resolution=1, orient=tk.HORIZONTAL, length=int(120 * scaling_factor), bg=background_color, fg=text_color, troughcolor=button_gray, activebackground=highlight_color, highlightthickness=0, bd=0, sliderrelief=tk.FLAT, sliderlength=int(15 * scaling_factor), width=int(15 * scaling_factor), font=scale_font(("Arial", 11, "bold")), command=self.update_vibration_frequency)
        self.vibration_frequency_scale.set(getattr(CONFIG, "vibration_frequency", 10))
        self.vibration_frequency_scale.pack(side=tk.LEFT)

        # Row 4: Delay
        self.row_vibration_delay = tk.Frame(self.rumble_window, bg=background_color)
        self.row_vibration_delay.pack(side=tk.TOP, fill=tk.X, pady=int(5 * scaling_factor))
        self.delay_label = tk.Label(self.row_vibration_delay, text="Delay:", bg=background_color, fg=text_color, font=scale_font(("Arial", 11, "bold")), width=12, anchor=tk.W)
        self.delay_label.pack(side=tk.LEFT, padx=(0, int(5 * scaling_factor)))

        def validate_numeric(char):
            return char.isdigit() or char == ""
        vcmd = (self.root.register(validate_numeric), '%S')

        self.rumble_delay_entry = tk.Entry(self.row_vibration_delay, width=4, bg=button_gray, fg=text_color, insertbackground=text_color, bd=0, relief=tk.FLAT, font=scale_font(("Arial", 11, "bold")), justify=tk.CENTER, validate="key", validatecommand=vcmd)
        self.rumble_delay_entry.insert(0, str(getattr(CONFIG, "rumble_delay_ms", 0)))
        self.rumble_delay_entry.pack(side=tk.LEFT, padx=int(2 * scaling_factor))
        self.delay_ms_label = tk.Label(self.row_vibration_delay, text="ms", bg=background_color, fg=text_color, font=scale_font(("Arial", 11, "bold")))
        self.delay_ms_label.pack(side=tk.LEFT, padx=(int(2 * scaling_factor), int(5 * scaling_factor)))

        self.rumble_delay_entry.bind("<KeyRelease>", self.on_rumble_delay_changed)
        self.update_rumble_mode_ui(getattr(CONFIG, "rumble_mode", "Xbox"))

        self._add_popout_finish_button(self.rumble_window, self.close_rumble_popup)

        self.center_window_on_root(self.rumble_window, int(460 * scaling_factor), int(260 * scaling_factor))
        self._apply_dark_title_bar(self.rumble_window)
        self.rumble_window.protocol("WM_DELETE_WINDOW", self.close_rumble_popup)
        self.rumble_window.lift()

    def close_rumble_popup(self):
        if hasattr(self, "rumble_window") and self.rumble_window is not None and self.rumble_window.winfo_exists():
            self.rumble_window.destroy()
        self.rumble_window = None

    def init_gyro_config_popup(self):
        pass

    def toggle_gyro_config_popup(self):
        if hasattr(self, "gyro_config_window") and self.gyro_config_window is not None and self.gyro_config_window.winfo_exists():
            self.close_gyro_config_popup()
        else:
            self.open_gyro_config_popup()

    def open_gyro_config_popup(self):
        self.close_settings_popup()
        if hasattr(self, "gyro_config_window") and self.gyro_config_window is not None and self.gyro_config_window.winfo_exists():
            self.gyro_config_window.lift()
            self.gyro_config_window.focus_set()
            return

        self.gyro_config_window = tk.Toplevel(self.root)
        self.gyro_config_window.title("Gyro Configuration")
        self.gyro_config_window.resizable(False, False)
        self.gyro_config_window.configure(bg=background_color, padx=int(14 * scaling_factor), pady=int(12 * scaling_factor))

        self.init_gyro_settings_panel(parent=self.gyro_config_window)
        self.init_compensation_panel(parent=self.gyro_config_window)

        self._add_popout_finish_button(self.gyro_config_window, self.close_gyro_config_popup)

        self.center_window_on_root(self.gyro_config_window, int(640 * scaling_factor), int(340 * scaling_factor))
        self._apply_dark_title_bar(self.gyro_config_window)
        self.gyro_config_window.protocol("WM_DELETE_WINDOW", self.close_gyro_config_popup)
        self.gyro_config_window.lift()

    def close_gyro_config_popup(self):
        if hasattr(self, "gyro_config_window") and self.gyro_config_window is not None and self.gyro_config_window.winfo_exists():
            self.gyro_config_window.destroy()
        self.gyro_config_window = None

    def toggle_auto_disconnect_popup(self):
        if hasattr(self, "auto_disconnect_window") and self.auto_disconnect_window is not None and self.auto_disconnect_window.winfo_exists():
            self.close_auto_disconnect_popup()
        else:
            self.open_auto_disconnect_popup()

    def open_auto_disconnect_popup(self):
        self.close_settings_popup()
        if hasattr(self, "auto_disconnect_window") and self.auto_disconnect_window is not None and self.auto_disconnect_window.winfo_exists():
            self.auto_disconnect_window.lift()
            self.auto_disconnect_window.focus_set()
            return

        self.auto_disconnect_window = tk.Toplevel(self.root)
        self.auto_disconnect_window.title("Auto Disconnect Settings")
        self.auto_disconnect_window.resizable(False, False)
        self.auto_disconnect_window.configure(bg=background_color, padx=int(14 * scaling_factor), pady=int(12 * scaling_factor))

        self.init_auto_disconnect_popup(parent=self.auto_disconnect_window)

        self._add_popout_finish_button(self.auto_disconnect_window, self.close_auto_disconnect_popup)

        self.center_window_on_root(self.auto_disconnect_window, int(420 * scaling_factor), int(200 * scaling_factor))
        self._apply_dark_title_bar(self.auto_disconnect_window)
        self.auto_disconnect_window.protocol("WM_DELETE_WINDOW", self.close_auto_disconnect_popup)
        self.auto_disconnect_window.lift()

    def close_auto_disconnect_popup(self):
        if hasattr(self, "auto_disconnect_window") and self.auto_disconnect_window is not None and self.auto_disconnect_window.winfo_exists():
            self.auto_disconnect_window.destroy()
        self.auto_disconnect_window = None

    def bind_wired_pro_controller_settings_popup_outside_click(self):
        pass

    def open_wired_pro_controller_settings_popup(self, anchor_widget=None):
        self.close_settings_popup()
        if hasattr(self, "wired_pro_settings_window") and self.wired_pro_settings_window is not None and self.wired_pro_settings_window.winfo_exists():
            self.wired_pro_settings_window.lift()
            self.wired_pro_settings_window.focus_set()
            return
        self.close_wired_pro_controller_settings_popup()

        self.wired_pro_settings_window = tk.Toplevel(self.root)
        self.wired_pro_settings_window.title(f"{self.wired_controller_label()} Settings")
        self.wired_pro_settings_window.resizable(False, False)
        self.wired_pro_settings_window.configure(bg=background_color, padx=int(14 * scaling_factor), pady=int(12 * scaling_factor))

        def refresh_hidhide_button():
            installed = self._sync_hidhide_installed()
            hidhide_btn.config(text="HidHide" if installed else "Install HidHide")

        hidhide_frame = tk.Frame(self.wired_pro_settings_window, bg=button_gray)
        hidhide_frame.pack(side=tk.TOP, fill=tk.X, pady=int(3 * scaling_factor))
        hidhide_btn = tk.Button(
            hidhide_frame,
            text="HidHide" if hidhide_service_state() is True else "Install HidHide",
            bg=button_gray,
            fg=text_color,
            bd=0,
            relief=tk.FLAT,
            font=scale_font(("Arial", 10, "bold")),
            command=lambda: (self.on_wired_usb_driver_button(), refresh_hidhide_button()),
        )
        hidhide_btn.pack(fill=tk.X, padx=int(2 * scaling_factor), pady=int(2 * scaling_factor))
        refresh_hidhide_button()

        auto_scan_frame = tk.Frame(self.wired_pro_settings_window, bg=button_gray)
        auto_scan_frame.pack(side=tk.TOP, fill=tk.X, pady=int(3 * scaling_factor))

        def auto_scan_enabled():
            return bool(getattr(CONFIG, "wired_auto_scan_enabled", getattr(CONFIG, "wired_usb_enabled", True)))

        def refresh_auto_scan_button():
            auto_scan_btn.config(text=f"Auto Scan: {'On' if auto_scan_enabled() else 'Off'}")

        def toggle_auto_scan():
            val = not auto_scan_enabled()
            CONFIG.wired_auto_scan_enabled = val
            CONFIG.wired_usb_enabled = val
            CONFIG.save_config()
            set_wired_auto_scan_enabled(val)
            refresh_auto_scan_button()

        auto_scan_btn = tk.Button(
            auto_scan_frame,
            text="",
            bg=button_gray,
            fg=text_color,
            bd=0,
            relief=tk.FLAT,
            font=scale_font(("Arial", 10, "bold")),
            command=toggle_auto_scan,
        )
        auto_scan_btn.pack(fill=tk.X, padx=int(2 * scaling_factor), pady=int(2 * scaling_factor))
        refresh_auto_scan_button()

        manual_frame = tk.Frame(self.wired_pro_settings_window, bg=button_gray)
        manual_frame.pack(side=tk.TOP, fill=tk.X, pady=int(3 * scaling_factor))

        def run_manual_scan():
            request_wired_rescan("manual_refresh", manual=True)

        tk.Button(
            manual_frame,
            text="Manual Scan",
            bg=button_gray,
            fg=text_color,
            bd=0,
            relief=tk.FLAT,
            font=scale_font(("Arial", 10, "bold")),
            command=run_manual_scan,
        ).pack(fill=tk.X, padx=int(2 * scaling_factor), pady=int(2 * scaling_factor))

        self._add_popout_finish_button(self.wired_pro_settings_window, self.close_wired_pro_controller_settings_popup)

        self.center_window_on_root(self.wired_pro_settings_window, int(340 * scaling_factor), int(210 * scaling_factor))
        self._apply_dark_title_bar(self.wired_pro_settings_window)
        self.wired_pro_settings_window.protocol("WM_DELETE_WINDOW", self.close_wired_pro_controller_settings_popup)
        self.wired_pro_settings_window.lift()

