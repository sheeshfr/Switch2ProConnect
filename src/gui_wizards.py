import asyncio
import logging
import math
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

import utils
from config import CONFIG
from controller import Controller, controller_calibration_keys, normalize_calibration_key
from gui_widgets import apply_window_dark_theme_and_icon, make_rounded_button

logger = logging.getLogger(__name__)

background_color = "#2D2D2D"
button_gray = "#4B4B4B"
highlight_color = "#00C3E3"

def scale_font(font_tuple):
    import gui
    return gui.scale_font(font_tuple)

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

def __getattr__(name):
    import gui
    if hasattr(gui, name):
        return getattr(gui, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

class CalibrationOverlay:
    def __init__(self, root):
        self.root = root
        self.window = None
        self.lbl_title = None
        self.lbl_msg = None
        self.close_timer = None
        self.profile_window = None
        self.profile_close_timer = None

    def update(self, title, message):
        # We must run this on the main thread. If we are called from a background thread,
        # we schedule it via self.root.after
        if threading.current_thread() != threading.main_thread():
            self.root.after(0, self.update, title, message)
            return

        # Suppress calibration completion, cancellation, and status bottom-right toasts
        msg_lower = (message or "").lower()
        if (
            "calibration complete" in msg_lower
            or "calibration cancelled" in msg_lower
            or "calibration finished" in msg_lower
            or "calibration saved" in msg_lower
            or "magnetometer calibration" in msg_lower
            or "gyroscope calibration" in msg_lower
            or "joysticks calibration" in msg_lower
            or "joystick calibration" in msg_lower
        ):
            return

        if self.window is None or not self.window.winfo_exists():
            self._create_window()
            
        # Highlight colors depending on status
        if "started" in message.lower() or "progress" in message.lower() or "stationary" in message.lower():
            color = "#ff9f0a" # Orange
        elif "complete" in message.lower() or "success" in message.lower():
            color = "#30d158" # Green
        elif "cancelled" in message.lower():
            color = "#ff453a" # Red
        else:
            color = "#0a84ff" # Blue
            
        self.lbl_title.config(text=title, fg=color)
        self.lbl_msg.config(text=message)
        
        # Cancel any pending auto-close timer
        if self.close_timer:
            self.root.after_cancel(self.close_timer)
            self.close_timer = None
            
        # Auto close after 3 seconds for final completion / cancellation
        # We do not auto-close on Gyro completion because it has instructions waiting for Mag start
        is_final_complete = "magnetometer calibration complete" in message.lower()
        is_cancelled = "cancelled" in message.lower()
        is_profile = "profile" in title.lower()
        if is_final_complete or is_cancelled or is_profile:
            self.close_timer = self.root.after(3000, self.close)

    def _create_window(self):
        self.window = tk.Toplevel(self.root)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.attributes("-alpha", 0.95)
        self.window.configure(bg="#1c1c1e")
        
        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()
        w, h = int(500 * scaling_factor), int(110 * scaling_factor)
        x = screen_width - w - int(30 * scaling_factor)
        y = screen_height - h - int(70 * scaling_factor) # Bottom-right, staying above the taskbar
        self.window.geometry(f"{w}x{h}+{x}+{y}")
        
        frame = tk.Frame(self.window, bg="#1c1c1e", highlightbackground="#3a3a3c", highlightthickness=2, bd=0)
        frame.pack(fill="both", expand=True)
        
        self.lbl_title = tk.Label(frame, text="Switch 2 Pro Connect", fg="#0a84ff", bg="#1c1c1e", font=scale_font(("Segoe UI", 11, "bold")))
        self.lbl_title.pack(anchor="w", padx=int(20 * scaling_factor), pady=(int(12 * scaling_factor), int(2 * scaling_factor)))
        
        self.lbl_msg = tk.Label(frame, text="", fg="#ffffff", bg="#1c1c1e", font=scale_font(("Segoe UI", 11)), justify="left", wraplength=int(460 * scaling_factor))
        self.lbl_msg.pack(anchor="w", padx=int(20 * scaling_factor), pady=(0, int(12 * scaling_factor)))

    def close(self):
        if threading.current_thread() != threading.main_thread():
            self.root.after(0, self.close)
            return
            
        if self.window and self.window.winfo_exists():
            self.window.destroy()
        self.window = None

    def show_profile_selection(self, prev_name, selected_name, next_name, manual, layout_label, auto_close_ms=None, name_px=0):
        if threading.current_thread() != threading.main_thread():
            self.root.after(0, self.show_profile_selection, prev_name, selected_name, next_name, manual, layout_label, auto_close_ms, name_px)
            return

        CYAN = "#00e5ff"
        GREEN = "#30d158"
        RED = "#ff453a"
        WHITE = "#ffffff"
        BG = "#1c1c1e"

        # Rebuild the window/content only when it doesn't exist or the mode/layout
        # changed. During cycling we only update the three profile-name labels so the
        # window doesn't flicker (title, background and instructions stay put).
        rebuild = (self.profile_window is None or not self.profile_window.winfo_exists()
                   or not hasattr(self, "_profile_sel_lbl")
                   or getattr(self, "_profile_manual", None) != manual
                   or getattr(self, "_profile_layout", None) != layout_label)

        if rebuild:
            if self.profile_window is not None and self.profile_window.winfo_exists():
                self.profile_window.destroy()
            self.profile_window = tk.Toplevel(self.root)
            self.profile_window.overrideredirect(True)
            self.profile_window.attributes("-topmost", True)
            self.profile_window.attributes("-alpha", 0.95)
            self.profile_window.configure(bg=BG)
            self._profile_manual = manual
            self._profile_layout = layout_label

            pad = int(14 * scaling_factor)
            frame = tk.Frame(self.profile_window, bg=BG, highlightbackground="#3a3a3c", highlightthickness=2, bd=0)
            frame.pack(fill="both", expand=True)

            tk.Label(frame, text="Change Profile To", fg=WHITE, bg=BG, font=scale_font(("Segoe UI", 11, "bold"))).pack(padx=pad, pady=(int(10 * scaling_factor), int(6 * scaling_factor)))

            self._profile_prev_lbl = tk.Label(frame, text=" ", fg=WHITE, bg=BG, font=scale_font(("Segoe UI", 11)))
            self._profile_prev_lbl.pack(padx=pad)

            sel_wrap = tk.Frame(frame, bg=BG, highlightbackground=CYAN, highlightcolor=CYAN, highlightthickness=2, bd=0)
            sel_wrap.pack(pady=int(2 * scaling_factor))
            self._profile_sel_lbl = tk.Label(sel_wrap, text=" ", fg=WHITE, bg=BG, font=scale_font(("Segoe UI", 11, "bold")))
            self._profile_sel_lbl.pack(padx=int(6 * scaling_factor), pady=int(1 * scaling_factor))

            self._profile_next_lbl = tk.Label(frame, text=" ", fg=WHITE, bg=BG, font=scale_font(("Segoe UI", 11)))
            self._profile_next_lbl.pack(padx=pad)

            if manual:
                tk.Label(frame, text=f"Press {layout_label} Layout", fg=WHITE, bg=BG, font=scale_font(("Segoe UI", 10))).pack(pady=(int(8 * scaling_factor), 0))
                row = tk.Frame(frame, bg=BG)
                row.pack(pady=(0, int(10 * scaling_factor)))
                tk.Label(row, text="A button to SELECT", fg=GREEN, bg=BG, font=scale_font(("Segoe UI", 10, "bold"))).pack(side=tk.LEFT)
                tk.Label(row, text=" or ", fg=WHITE, bg=BG, font=scale_font(("Segoe UI", 10))).pack(side=tk.LEFT)
                tk.Label(row, text="B button to CANCEL", fg=RED, bg=BG, font=scale_font(("Segoe UI", 10, "bold"))).pack(side=tk.LEFT)
            else:
                tk.Frame(frame, bg=BG, height=int(8 * scaling_factor)).pack()

            self._profile_prev_lbl.config(text=prev_name or " ")
            self._profile_sel_lbl.config(text=selected_name or " ")
            self._profile_next_lbl.config(text=next_name or " ")

            # Width: 2/3 of the old notification width as a lower bound, widened to fit
            # the longest profile name in the change list (name_px) so cycling never
            # clips or resizes; height fits the content.
            target_w = int(500 * scaling_factor * 2 / 3)
            self.profile_window.update_idletasks()
            w = max(target_w, self.profile_window.winfo_reqwidth(), int(name_px) + int(40 * scaling_factor))
            h = self.profile_window.winfo_reqheight()
            sw = self.profile_window.winfo_screenwidth()
            sh = self.profile_window.winfo_screenheight()
            x = sw - w - int(30 * scaling_factor)
            y = sh - h - int(70 * scaling_factor)
            self.profile_window.geometry(f"{w}x{h}+{x}+{y}")
        else:
            self._profile_prev_lbl.config(text=prev_name or " ")
            self._profile_sel_lbl.config(text=selected_name or " ")
            self._profile_next_lbl.config(text=next_name or " ")

        self.profile_window.lift()

        if self.profile_close_timer:
            self.root.after_cancel(self.profile_close_timer)
            self.profile_close_timer = None
        if auto_close_ms:
            self.profile_close_timer = self.root.after(auto_close_ms, self.close_profile_selection)

    def close_profile_selection(self):
        if threading.current_thread() != threading.main_thread():
            self.root.after(0, self.close_profile_selection)
            return
        if self.profile_close_timer:
            try:
                self.root.after_cancel(self.profile_close_timer)
            except Exception:
                pass
            self.profile_close_timer = None
        if self.profile_window and self.profile_window.winfo_exists():
            self.profile_window.destroy()
        self.profile_window = None

class JoystickCalibrationWizard:
    ROTATE_SECONDS = 10.0
    RELEASE_SECONDS = 3.0
    STILL_BEFORE_COUNTDOWN = 2.0
    MOVE_THRESHOLD = 10
    TOUCH_THRESHOLD = 45

    def __init__(self, root, virtual_controller, on_closed=None):
        self.root = root
        self.virtual_controller = virtual_controller
        self.on_closed = on_closed
        self.closed = False
        self.completed = False
        self.sources = self._build_sources(virtual_controller)
        if not self.sources:
            utils.show_notification("Joysticks Calibration", "No joystick found for this player slot.")
            return
        if any(getattr(source["controller"], "last_input_data", None) is None for source in self.sources):
            utils.show_notification("Joysticks Calibration", "Waiting for joystick input data. Please try again in a moment.")
            return

        self.stage = "rotate"
        self.last_tick = time.perf_counter()
        self.auto_close_timer = None
        self.data = {}
        for source in self.sources:
            sample = self._read_raw(source)
            self.data[source["key"]] = {
                "source": source,
                "rotate_elapsed": 0.0,
                "release_elapsed": 0.0,
                "observed_min": list(sample),
                "observed_max": list(sample),
                "prev": sample,
                "still_since": None,
                "anchor": sample,
                "idle_samples": [],
                "rotate_done": False,
                "release_done": False,
            }
        self._set_controller_flags(True)

        self.window = tk.Toplevel(root)
        self.window.title("Joysticks Calibration")
        self.window.resizable(False, False)
        self.window.configure(bg=background_color)
        self.window.transient(root)

        apply_window_dark_theme_and_icon(self.window, background_color)

        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda e: self.cancel())
        try:
            self._root_esc_bind_id = self.root.bind("<Escape>", lambda e: self.cancel(), add="+")
        except Exception:
            self._root_esc_bind_id = None

        self.frame = tk.Frame(self.window, bg=background_color, padx=int(20 * scaling_factor), pady=int(16 * scaling_factor))
        self.frame.pack(fill="both", expand=True)
        self.title_label = tk.Label(self.frame, text="Joysticks Calibration", fg="white", bg=background_color, font=scale_font(("Arial", 12, "bold")))
        self.title_label.pack(anchor="w", pady=(0, int(6 * scaling_factor)))
        self.message_label = tk.Label(self.frame, text="", fg="#DDDDDD", bg=background_color, font=scale_font(("Arial", 10)), justify="center", wraplength=int(380 * scaling_factor))
        self.message_label.pack(pady=(0, int(10 * scaling_factor)))
        self.grid_frame = tk.Frame(self.frame, bg=button_gray, padx=int(14 * scaling_factor), pady=int(10 * scaling_factor))
        self.grid_frame.pack(fill=tk.X, pady=(0, int(14 * scaling_factor)))
        self.value_labels = {}
        self._build_counter_grid()

        self.btn_row = tk.Frame(self.frame, bg=background_color)
        self.btn_row.pack(fill=tk.X)
        self.cancel_btn = make_rounded_button(
            self.btn_row,
            text="Cancel (ESC)",
            width=110,
            height=28,
            radius=14,
            bg_color=button_gray,
            hover_color="#5A5A5A",
            press_color="#3A3A3A",
            fg="white",
            parent_bg=background_color,
            font=scale_font(("Arial", 9, "bold")),
            command=self.cancel
        )
        self.cancel_btn.pack(side=tk.RIGHT)

        self._center_window()
        self._refresh_text()
        self._tick()

    def _set_controller_flags(self, active):
        for controller in getattr(self.virtual_controller, "controllers", []) or []:
            controller.is_joystick_calibrating = active
            controller.back_button_calibration_active = active

    def _build_sources(self, vc):
        sources = []
        for controller in vc.controllers:
            if controller.is_joycon_left():
                sources.append({"controller": controller, "side": "left", "label": "L Joystick", "key": f"{controller.device.address}:left"})
            elif controller.is_joycon_right():
                sources.append({"controller": controller, "side": "right", "label": "R Joystick", "key": f"{controller.device.address}:right"})
            else:
                sources.append({"controller": controller, "side": "right", "label": "R Joystick", "key": f"{controller.device.address}:right"})
                sources.append({"controller": controller, "side": "left", "label": "L Joystick", "key": f"{controller.device.address}:left"})
        side_order = {"left": 0, "right": 1}
        return sorted(sources, key=lambda s: side_order.get(s["side"], 2))

    def _read_raw(self, source):
        input_data = getattr(source["controller"], "last_input_data", None)
        if input_data is None:
            return (2048, 2048)
        attr = "raw_left_stick" if source["side"] == "left" else "raw_right_stick"
        return tuple(int(v) for v in getattr(input_data, attr, (2048, 2048)))

    def _build_counter_grid(self):
        for child in self.grid_frame.winfo_children():
            child.destroy()
        self.value_labels.clear()
        col_count = len(self.sources)
        for idx, source in enumerate(self.sources):
            tk.Label(self.grid_frame, text=source["label"], fg="white", bg=button_gray, font=scale_font(("Arial", 11, "bold")), width=14).grid(row=0, column=idx, padx=int(12 * scaling_factor))
            value = tk.Label(self.grid_frame, text="10", fg="#30d158", bg=button_gray, font=scale_font(("Arial", 18, "bold")), width=8)
            value.grid(row=1, column=idx, padx=int(12 * scaling_factor), pady=(int(4 * scaling_factor), 0))
            self.value_labels[source["key"]] = value
        for idx in range(col_count):
            self.grid_frame.grid_columnconfigure(idx, weight=1)

    def _center_window(self):
        self.window.update_idletasks()
        sf = getattr(self.root, "scaling_factor", 1.0)
        w = max(int(450 * sf), self.window.winfo_reqwidth())
        h = max(int(230 * sf), self.window.winfo_reqheight())
        try:
            rx = self.root.winfo_rootx()
            ry = self.root.winfo_rooty()
            rw = self.root.winfo_width()
            rh = self.root.winfo_height()
            x = rx + (rw - w) // 2
            y = ry + (rh - h) // 2
        except Exception:
            sw = self.window.winfo_screenwidth()
            sh = self.window.winfo_screenheight()
            x = (sw - w) // 2
            y = (sh - h) // 2
        self.window.geometry(f"{w}x{h}+{x}+{y}")

    def _distance(self, a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def _tick(self):
        if not self.window.winfo_exists():
            return
        now = time.perf_counter()
        dt = min(0.1, max(0.0, now - self.last_tick))
        self.last_tick = now

        if self.stage == "rotate":
            self._tick_rotate(dt)
            if all(item["rotate_done"] for item in self.data.values()):
                self.stage = "release"
                for item in self.data.values():
                    sample = self._read_raw(item["source"])
                    item["prev"] = sample
                    item["anchor"] = sample
                    item["still_since"] = now
                    item["idle_samples"] = []
                self._refresh_text()
        elif self.stage == "release":
            self._tick_release(dt, now)
            if all(item["release_done"] for item in self.data.values()):
                self._finish()
                return

        self._refresh_text()
        self.root.after(50, self._tick)

    def _tick_rotate(self, dt):
        for item in self.data.values():
            if item["rotate_done"]:
                continue
            sample = self._read_raw(item["source"])
            item["observed_min"][0] = min(item["observed_min"][0], sample[0])
            item["observed_min"][1] = min(item["observed_min"][1], sample[1])
            item["observed_max"][0] = max(item["observed_max"][0], sample[0])
            item["observed_max"][1] = max(item["observed_max"][1], sample[1])
            if self._distance(sample, item["prev"]) >= self.MOVE_THRESHOLD:
                item["rotate_elapsed"] += dt
            item["prev"] = sample
            if item["rotate_elapsed"] >= self.ROTATE_SECONDS:
                item["rotate_done"] = True

    def _tick_release(self, dt, now):
        for item in self.data.values():
            if item["release_done"]:
                continue
            sample = self._read_raw(item["source"])
            moved = self._distance(sample, item["prev"]) >= self.MOVE_THRESHOLD
            touched = self._distance(sample, item["anchor"]) >= self.TOUCH_THRESHOLD
            if moved or touched:
                item["still_since"] = None
                item["anchor"] = sample
            elif item["still_since"] is None:
                item["still_since"] = now
                item["anchor"] = sample

            if item["still_since"] is not None and now - item["still_since"] >= self.STILL_BEFORE_COUNTDOWN:
                item["release_elapsed"] += dt
                item["idle_samples"].append(sample)
            item["prev"] = sample
            if item["release_elapsed"] >= self.RELEASE_SECONDS:
                item["release_done"] = True

    def _refresh_text(self):
        if self.stage == "rotate":
            self.message_label.config(text="Please fully rotate both joysticks for 10 seconds each.")
            for key, item in self.data.items():
                text = "Done" if item["rotate_done"] else str(max(0, int(self.ROTATE_SECONDS - item["rotate_elapsed"] + 0.999)))
                self.value_labels[key].config(text=text)
        elif self.stage == "release":
            self.message_label.config(text="Please release and don't touch the joysticks for 3 seconds.")
            for key, item in self.data.items():
                text = "Done" if item["release_done"] else str(max(0, int(self.RELEASE_SECONDS - item["release_elapsed"] + 0.999)))
                self.value_labels[key].config(text=text)

    def _finish(self):
        self.completed = True
        updates_by_controller = {}
        for item in self.data.values():
            source = item["source"]
            samples = item["idle_samples"] or [self._read_raw(source)]
            cx = int(round(sum(s[0] for s in samples) / len(samples)))
            cy = int(round(sum(s[1] for s in samples) / len(samples)))
            cal = {
                "center": [cx, cy],
                "max": [max(1, item["observed_max"][0] - cx), max(1, item["observed_max"][1] - cy)],
                "min": [max(1, cx - item["observed_min"][0]), max(1, cy - item["observed_min"][1])],
            }
            controller = source["controller"]
            updates_by_controller.setdefault(controller, {})[source["side"]] = cal

        store = getattr(CONFIG, "joystick_calibration_data", {}) or {}
        for controller, sides in updates_by_controller.items():
            existing = {}
            keys = controller_calibration_keys(controller)
            normalized_keys = {normalize_calibration_key(key) for key in keys}
            for key in keys:
                if isinstance(store.get(key), dict):
                    existing.update(store[key])
            for key, value in store.items():
                if normalize_calibration_key(key) in normalized_keys and isinstance(value, dict):
                    existing.update(value)
            existing.update(sides)
            for key in keys:
                store[key] = existing
        CONFIG.joystick_calibration_data = store
        CONFIG.save_config()

        for controller in self.virtual_controller.controllers:
            try:
                controller.apply_in_app_joystick_calibration()
            except Exception as e:
                logger.warning(f"Failed to apply joystick calibration for {controller.device.address}: {e}")
        self._set_controller_flags(False)

        for child in self.grid_frame.winfo_children():
            child.destroy()
        self.message_label.config(text="Joysticks calibration complete and saved!")
        self.title_label.config(fg="#30d158")
        if hasattr(self, "cancel_btn") and self.cancel_btn.winfo_exists():
            self.cancel_btn.destroy()
        done_btn = make_rounded_button(
            self.btn_row,
            text="Done",
            width=100,
            height=28,
            radius=14,
            bg_color="#2E7D32",
            hover_color="#388E3C",
            press_color="#1B5E20",
            fg="white",
            parent_bg=background_color,
            font=scale_font(("Arial", 9, "bold")),
            command=self.close
        )
        done_btn.pack(side=tk.RIGHT)
        self.auto_close_timer = self.root.after(2500, self.close)

    def cancel(self):
        self._set_controller_flags(False)
        self.close()

    def close(self):
        if self.closed:
            return
        self.closed = True
        if getattr(self, "_root_esc_bind_id", None):
            try:
                self.root.unbind("<Escape>", self._root_esc_bind_id)
            except Exception:
                pass
            self._root_esc_bind_id = None
        if not self.completed:
            self._set_controller_flags(False)
        if self.auto_close_timer:
            try:
                self.root.after_cancel(self.auto_close_timer)
            except Exception:
                pass
            self.auto_close_timer = None
        if getattr(self, "window", None) and self.window.winfo_exists():
            self.window.destroy()
        if self.on_closed is not None:
            self.on_closed(self)


class MagnetometerCalibrationWizard:
    def __init__(self, root, virtual_controller, on_closed=None):
        self.root = root
        self.virtual_controller = virtual_controller
        self.on_closed = on_closed
        self.closed = False

        controllers = []
        if virtual_controller is not None:
            controllers = getattr(virtual_controller, "controllers", []) or [virtual_controller]

        if not controllers:
            utils.show_notification("Magnetometer Calibration", "No controller found for magnetometer calibration.")
            return

        self.controllers = controllers

        # Store previous state for rollback on cancel
        self._prev_mag_data = {}
        for c in self.controllers:
            self._prev_mag_data[c] = {
                "bias": getattr(c, "mag_bias", (0.0, 0.0, 0.0)),
                "matrix": getattr(c, "mag_matrix", None),
                "valid": getattr(c, "mag_calibration_valid", False),
            }
            if hasattr(c, "start_mag_calibration"):
                c.start_mag_calibration()

        self.window = tk.Toplevel(root)
        self.window.title("Magnetometer Calibration")
        self.window.resizable(False, False)
        self.window.configure(bg=background_color)
        self.window.transient(root)

        apply_window_dark_theme_and_icon(self.window, background_color)

        sf = getattr(root, "scaling_factor", 1.0)
        self.frame = tk.Frame(self.window, bg=background_color, padx=int(20 * sf), pady=int(16 * sf))
        self.frame.pack(fill="both", expand=True)

        self.title_lbl = tk.Label(
            self.frame,
            text="Magnetometer Calibration",
            font=scale_font(("Arial", 12, "bold")),
            fg="white",
            bg=background_color,
        )
        self.title_lbl.pack(anchor="w", pady=(0, int(6 * sf)))

        self.instr_lbl = tk.Label(
            self.frame,
            text="Slowly rotate the controller in all directions (move it in a slow figure-8 pattern) to map the magnetic field in 3D.",
            font=scale_font(("Arial", 10)),
            fg="#DDDDDD",
            bg=background_color,
            wraplength=int(380 * sf),
            justify=tk.LEFT
        )
        self.instr_lbl.pack(anchor="w", pady=(0, int(14 * sf)))

        # Status & Sample Counter Frame
        self.stats_frame = tk.Frame(self.frame, bg=button_gray, padx=int(14 * sf), pady=int(10 * sf))
        self.stats_frame.pack(fill=tk.X, pady=(0, int(14 * sf)))

        self.samples_lbl = tk.Label(
            self.stats_frame,
            text="Samples Collected: 0",
            font=scale_font(("Arial", 11, "bold")),
            fg="#00C3E3",
            bg=button_gray
        )
        self.samples_lbl.pack(side=tk.LEFT)

        self.status_hint = tk.Label(
            self.stats_frame,
            text="Collecting points...",
            font=scale_font(("Arial", 9)),
            fg="#BBBBBB",
            bg=button_gray
        )
        self.status_hint.pack(side=tk.RIGHT)

        # Button row: Finish Calibration & Cancel
        self.btn_row = tk.Frame(self.frame, bg=background_color)
        self.btn_row.pack(fill=tk.X, pady=(int(4 * sf), 0))

        self.finish_btn = make_rounded_button(
            self.btn_row,
            text="Finish Calibration",
            width=135,
            height=30,
            radius=15,
            bg_color="#2E7D32",
            hover_color="#388E3C",
            press_color="#1B5E20",
            fg="white",
            parent_bg=background_color,
            font=scale_font(("Arial", 9, "bold")),
            command=self.finish
        )
        self.finish_btn.pack(side=tk.RIGHT, padx=(int(6 * sf), 0))

        self.cancel_btn = make_rounded_button(
            self.btn_row,
            text="Cancel (ESC)",
            width=100,
            height=30,
            radius=15,
            bg_color=button_gray,
            hover_color="#5A5A5A",
            press_color="#3A3A3A",
            fg="white",
            parent_bg=background_color,
            font=scale_font(("Arial", 9, "bold")),
            command=self.cancel
        )
        self.cancel_btn.pack(side=tk.RIGHT)

        self.window.protocol("WM_DELETE_WINDOW", self.cancel)
        self.window.bind("<Escape>", lambda e: self.cancel())

        self._center_window()
        self._tick()

    def _center_window(self):
        self.window.update_idletasks()
        sf = getattr(self.root, "scaling_factor", 1.0)
        w = max(int(440 * sf), self.window.winfo_reqwidth())
        h = max(int(220 * sf), self.window.winfo_reqheight())
        try:
            rx = self.root.winfo_rootx()
            ry = self.root.winfo_rooty()
            rw = self.root.winfo_width()
            rh = self.root.winfo_height()
            x = rx + (rw - w) // 2
            y = ry + (rh - h) // 2
        except Exception:
            sw = self.window.winfo_screenwidth()
            sh = self.window.winfo_screenheight()
            x = (sw - w) // 2
            y = (sh - h) // 2
        self.window.geometry(f"{w}x{h}+{x}+{y}")

    def _tick(self):
        if self.closed or not self.window.winfo_exists():
            return
        total_samples = 0
        for c in self.controllers:
            samples = getattr(c, "mag_calibration_samples", []) or []
            total_samples += len(samples)

        if hasattr(self, "samples_lbl") and self.samples_lbl.winfo_exists():
            self.samples_lbl.config(text=f"Samples Collected: {total_samples}")
            if total_samples >= 80:
                self.status_hint.config(text="Good coverage! Click Finish when ready.", fg="#30d158")
            else:
                self.status_hint.config(text="Keep rotating in all directions...", fg="#BBBBBB")

        self.window.after(100, self._tick)

    def finish(self):
        if self.closed:
            return
        self.closed = True
        for c in self.controllers:
            if hasattr(c, "stop_mag_calibration"):
                c.stop_mag_calibration()
        self.close()

    def cancel(self):
        if self.closed:
            return
        self.closed = True
        for c, prev in getattr(self, "_prev_mag_data", {}).items():
            if hasattr(c, "cancel_mag_calibration"):
                c.cancel_mag_calibration()
            else:
                c.is_mag_calibrating = False
                c.mag_calibration_samples = []
            c.mag_bias = prev["bias"]
            c.mag_matrix = prev["matrix"]
            c.mag_calibration_valid = prev["valid"]
        self.close()

    def close(self):
        self.closed = True
        try:
            self.window.destroy()
        except Exception:
            pass
        if callable(self.on_closed):
            self.on_closed(self)


class GyroCalibrationWizard:
    def __init__(self, root, virtual_controller=None, on_closed=None):
        self.root = root
        self.virtual_controller = virtual_controller
        self.on_closed = on_closed
        self.closed = False
        self._timers = []

        controllers = []
        if virtual_controller is not None:
            controllers = getattr(virtual_controller, "controllers", []) or [virtual_controller]
        elif hasattr(root, "current_controllers"):
            for vc in root.current_controllers:
                if vc:
                    controllers.extend(getattr(vc, "controllers", []) or [vc])

        if not controllers:
            utils.show_notification("Gyro Calibration", "No controller connected to calibrate gyro.")
            return

        self.controllers = controllers

        # Backup previous gyro biases for rollback on cancel
        self._prev_biases = {}
        for c in self.controllers:
            self._prev_biases[c] = getattr(c, "gyro_bias", (0.0, 0.0, 0.0))

        self.window = tk.Toplevel(root)
        self.window.title("Gyroscope Calibration")
        self.window.resizable(False, False)
        self.window.configure(bg=background_color)
        self.window.transient(root)

        apply_window_dark_theme_and_icon(self.window, background_color)

        sf = getattr(root, "scaling_factor", 1.0)
        self.frame = tk.Frame(self.window, bg=background_color, padx=int(20 * sf), pady=int(16 * sf))
        self.frame.pack(fill="both", expand=True)

        self.title_lbl = tk.Label(
            self.frame,
            text="Gyroscope Calibration",
            font=scale_font(("Arial", 12, "bold")),
            fg="white",
            bg=background_color,
        )
        self.title_lbl.pack(anchor="w", pady=(0, int(6 * sf)))

        self.instr_lbl = tk.Label(
            self.frame,
            text="Place the controller on a flat, stationary surface and keep it completely still.",
            font=scale_font(("Arial", 10)),
            fg="#DDDDDD",
            bg=background_color,
            wraplength=int(380 * sf),
            justify=tk.LEFT
        )
        self.instr_lbl.pack(anchor="w", pady=(0, int(12 * sf)))

        # Status & Countdown container
        self.status_box = tk.Frame(self.frame, bg=button_gray, padx=int(14 * sf), pady=int(12 * sf))
        self.status_box.pack(fill=tk.X, pady=(0, int(14 * sf)))

        self.stage_lbl = tk.Label(
            self.status_box,
            text="Get Ready...",
            font=scale_font(("Arial", 11, "bold")),
            fg="#00C3E3",
            bg=button_gray
        )
        self.stage_lbl.pack(anchor="w")

        self.countdown_lbl = tk.Label(
            self.status_box,
            text="Starting in 3..",
            font=scale_font(("Arial", 14, "bold")),
            fg="white",
            bg=button_gray
        )
        self.countdown_lbl.pack(anchor="w", pady=(int(4 * sf), 0))

        # Buttons row
        self.btn_row = tk.Frame(self.frame, bg=background_color)
        self.btn_row.pack(fill=tk.X, pady=(int(4 * sf), 0))

        self.cancel_btn = make_rounded_button(
            self.btn_row,
            text="Cancel (ESC)",
            width=110,
            height=30,
            radius=15,
            bg_color=button_gray,
            hover_color="#5A5A5A",
            press_color="#3A3A3A",
            fg="white",
            parent_bg=background_color,
            font=scale_font(("Arial", 9, "bold")),
            command=self.cancel
        )
        self.cancel_btn.pack(side=tk.RIGHT)

        self.window.protocol("WM_DELETE_WINDOW", self.cancel)
        self.window.bind("<Escape>", lambda e: self.cancel())

        self._center_window()
        self._start_sequence()

    def _center_window(self):
        self.window.update_idletasks()
        sf = getattr(self.root, "scaling_factor", 1.0)
        w = max(int(440 * sf), self.window.winfo_reqwidth())
        h = max(int(230 * sf), self.window.winfo_reqheight())
        try:
            rx = self.root.winfo_rootx()
            ry = self.root.winfo_rooty()
            rw = self.root.winfo_width()
            rh = self.root.winfo_height()
            x = rx + (rw - w) // 2
            y = ry + (rh - h) // 2
        except Exception:
            sw = self.window.winfo_screenwidth()
            sh = self.window.winfo_screenheight()
            x = (sw - w) // 2
            y = (sh - h) // 2
        self.window.geometry(f"{w}x{h}+{x}+{y}")

    def _start_sequence(self):
        self._schedule(1000, lambda: self._set_countdown("Starting in 2.."))
        self._schedule(2000, lambda: self._set_countdown("Starting in 1.."))
        self._schedule(3000, self._start_calibrating)

    def _set_countdown(self, text):
        if self.closed or not self.window.winfo_exists():
            return
        self.countdown_lbl.config(text=text)

    def _schedule(self, ms, callback):
        t = self.root.after(ms, callback)
        self._timers.append(t)

    def _start_calibrating(self):
        if self.closed or not self.window.winfo_exists():
            return
        for c in self.controllers:
            if hasattr(c, "start_calibration"):
                c.start_calibration()

        self.stage_lbl.config(text="Calibrating Gyroscope... Keep still!", fg="#30d158")
        self._set_countdown("Calibrating 5..")

        self._schedule(1000, lambda: self._set_countdown("Calibrating 4.."))
        self._schedule(2000, lambda: self._set_countdown("Calibrating 3.."))
        self._schedule(3000, lambda: self._set_countdown("Calibrating 2.."))
        self._schedule(4000, lambda: self._set_countdown("Calibrating 1.."))
        self._schedule(5000, self._finish)

    def _finish(self):
        if self.closed or not self.window.winfo_exists():
            return
        self.stage_lbl.config(text="Calibration Complete!", fg="#30d158")
        self.countdown_lbl.config(text="Gyro bias successfully calibrated and saved.", font=scale_font(("Arial", 10)))
        
        if hasattr(self, "cancel_btn") and self.cancel_btn.winfo_exists():
            self.cancel_btn.destroy()

        done_btn = make_rounded_button(
            self.btn_row,
            text="Done",
            width=100,
            height=30,
            radius=15,
            bg_color="#2E7D32",
            hover_color="#388E3C",
            press_color="#1B5E20",
            fg="white",
            parent_bg=background_color,
            font=scale_font(("Arial", 9, "bold")),
            command=self.close
        )
        done_btn.pack(side=tk.RIGHT)

        self._schedule(2500, self.close)

    def cancel(self):
        if self.closed:
            return
        self.closed = True
        for t in self._timers:
            try: self.root.after_cancel(t)
            except Exception: pass
        self._timers = []

        for c in self.controllers:
            if hasattr(c, "cancel_calibration"):
                c.cancel_calibration()
            if c in self._prev_biases:
                c.gyro_bias = self._prev_biases[c]

        self.close()

    def close(self):
        self.closed = True
        for t in self._timers:
            try: self.root.after_cancel(t)
            except Exception: pass
        self._timers = []
        try:
            self.window.destroy()
        except Exception:
            pass
        if callable(self.on_closed):
            self.on_closed(self)


class GCTriggerCalibrationWizard:
    def __init__(self, root, gc_controller):
        self.root = root
        self.gc_controller = gc_controller
        self.window = tk.Toplevel(root)
        self.window.title("GameCube Trigger Calibration")
        w, h = int(450 * scaling_factor), int(180 * scaling_factor)
        self.window.geometry(f"{w}x{h}")
        self.window.attributes("-topmost", True)
        self.window.configure(bg=background_color)
        
        self.step = 0
        self.min_l = 36
        self.bump_l = 190
        self.max_l = 240
        self.min_r = 36
        self.bump_r = 190
        self.max_r = 240

        self.title_label = tk.Label(self.window, text="Step 1: Base State", font=scale_font(("Arial", 14, "bold")), bg=background_color, fg=highlight_color)
        self.title_label.pack(pady=(int(10 * scaling_factor), 0))

        self.desc_label = tk.Label(self.window, text="Release both triggers completely and wait a moment.\nThen click Next.", font=scale_font(("Arial", 11)), bg=background_color, fg="white", wraplength=int(400 * scaling_factor))
        self.desc_label.pack(pady=int(10 * scaling_factor))

        self.val_label = tk.Label(self.window, text="L: 0 | R: 0", font=scale_font(("Arial", 10)), bg=background_color, fg="#888888")
        self.val_label.pack(pady=(0, int(10 * scaling_factor)))

        self.btn_frame = tk.Frame(self.window, bg=background_color)
        self.btn_frame.pack()

        self.cancel_btn = tk.Button(self.btn_frame, text="Cancel", font=scale_font(("Arial", 10)), bg=button_gray, fg="white", bd=0, command=self.close)
        self.cancel_btn.pack(side=tk.LEFT, padx=int(10 * scaling_factor))

        self.next_btn = tk.Button(self.btn_frame, text="Next", font=scale_font(("Arial", 10, "bold")), bg=highlight_color, fg="black", bd=0, command=self.on_next)
        self.next_btn.pack(side=tk.LEFT, padx=int(10 * scaling_factor))

        self.update_loop()

    def update_loop(self):
        if not self.window.winfo_exists():
            return
        if hasattr(self.gc_controller, 'last_input_data') and self.gc_controller.last_input_data:
            l = self.gc_controller.last_input_data.left_trigger_raw
            r = self.gc_controller.last_input_data.right_trigger_raw
            self.val_label.config(text=f"L: {l} | R: {r}")
            
            if self.step == 0:
                self.min_l = l
                self.min_r = r
            elif self.step == 1:
                if l > self.bump_l: self.bump_l = l
            elif self.step == 2:
                if l > self.max_l: self.max_l = l
            elif self.step == 3:
                if r > self.bump_r: self.bump_r = r
            elif self.step == 4:
                if r > self.max_r: self.max_r = r

        self.root.after(50, self.update_loop)

    def on_next(self):
        if self.step == 0:
            self.step = 1
            self.title_label.config(text="Step 2: Left Trigger (Bump)")
            self.desc_label.config(text="Press the LEFT trigger down just until you feel the click (bump).\nHold it there and click Next.")
            self.bump_l = 0
        elif self.step == 1:
            self.step = 2
            self.title_label.config(text="Step 3: Left Trigger (Max)")
            self.desc_label.config(text="Fully press the LEFT trigger all the way down past the click.\nWhile holding it down, click Next.")
            self.max_l = 0
        elif self.step == 2:
            self.step = 3
            self.title_label.config(text="Step 4: Right Trigger (Bump)")
            self.desc_label.config(text="Press the RIGHT trigger down just until you feel the click (bump).\nHold it there and click Next.")
            self.bump_r = 0
        elif self.step == 3:
            self.step = 4
            self.title_label.config(text="Step 5: Right Trigger (Max)")
            self.desc_label.config(text="Fully press the RIGHT trigger all the way down past the click.\nWhile holding it down, click Finish.")
            self.max_r = 0
            self.next_btn.config(text="Finish")
        elif self.step == 4:
            CONFIG.gc_trigger_calibration_data[self.gc_controller.device.address] = [self.min_l, self.bump_l, self.max_l, self.min_r, self.bump_r, self.max_r]
            CONFIG.save_config()
            logger.info(f"Saved GC Trigger Calibration for {self.gc_controller.device.address}: {CONFIG.gc_trigger_calibration_data[self.gc_controller.device.address]}")
            from tkinter import messagebox
            messagebox.showinfo("Success", "GameCube Trigger Calibration saved successfully!")
            self.close()

    def close(self):
        if self.window and self.window.winfo_exists():
            self.window.destroy()

