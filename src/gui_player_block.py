import asyncio
import ctypes
import logging
import threading
import time
import tkinter as tk
from PIL import Image, ImageTk

from controller import (
    Controller,
    VibrationData,
    NSO_GAMECUBE_CONTROLLER_PID,
    CONTROLER_NAMES,
    COMMAND_RESPONSE_UUID,
    INPUT_REPORT_UUID,
)
from virtual_controller import VirtualController
from config import get_resource

logger = logging.getLogger(__name__)

background_color = "#2D2D2D"
block_color = background_color
button_gray = "#4B4B4B"
player_number_bg_color = "#2D2D2D"
text_color = "#FFFFFF"

def _scaled_px(base_value, minimum=1, scale=None):
    import gui
    return gui._scaled_px(base_value, minimum, scale)

def scale_font(font_tuple):
    import gui
    return gui.scale_font(font_tuple)

def make_rounded_button(*args, **kwargs):
    import gui
    return gui.make_rounded_button(*args, **kwargs)

def set_rounded_button_bg(*args, **kwargs):
    import gui
    return gui.set_rounded_button_bg(*args, **kwargs)

def apply_window_dark_theme_and_icon(*args, **kwargs):
    import gui
    return gui.apply_window_dark_theme_and_icon(*args, **kwargs)

def update_toggle_button(*args, **kwargs):
    import gui
    return gui.update_toggle_button(*args, **kwargs)

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

class _DynamicIntProxy:
    def __init__(self, attr_name):
        self.attr_name = attr_name
    def __int__(self):
        import gui
        return int(getattr(gui, self.attr_name))
    def __index__(self):
        import gui
        return int(getattr(gui, self.attr_name))

player_led_width = _DynamicIntProxy("player_led_width")
player_led_height = _DynamicIntProxy("player_led_height")

def __getattr__(name):
    import gui
    if hasattr(gui, name):
        return getattr(gui, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

class MockControllerInfo:
    def __init__(self, product_id=0):
        self.product_id = product_id

class MockPhysicalController:
    def __init__(self, ctype="pro", battery=3.9):
        self.ctype = ctype
        self.battery_voltage = battery
        self.controller_info = MockControllerInfo()
        self.is_mag_calibrating = False
        class Device:
            address = "00:00:00:00:00:00"
        self.device = Device()

    def is_joycon_left(self):
        return self.ctype == "left"

    def is_joycon_right(self):
        return self.ctype == "right"

    def is_joycon(self):
        return self.ctype in ("left", "right")

class MockVirtualController:
    def __init__(self, player_number, ctype="pro", battery=3.9):
        self.player_number = player_number
        self.ctype = ctype
        self.mode = "Switch2"
        self.hold_mode = "Vertical"
        self.controllers = [MockPhysicalController(ctype, battery)]
        self.running = True
        self.active_gyro_side = "Right"
        self.djg_left_active = True
        self.djg_right_active = True
        self.vg_controller = None
        self.loop = None
        self.on_disconnected_callback = None

    def is_single(self):
        return True

    def is_single_joycon_left(self):
        return self.ctype == "left"

    def is_single_joycon_right(self):
        return self.ctype == "right"

resolution_ratio = 1.0
window_resolution_ratio = 1.0
scaling_factor = 1.0
ui_dpi = 120
ui_dpi_scale = 1.25
controller_frame_size = 180

class PlayerInfoBlock:
    def __init__(self, parent, window):
        self.parent = parent
        self.window = window
        self.controller_label = None
        self.player_led_label = None
        self.current_vc = None
        self.mag_btn_single = None
        self.mag_frame_single = None
        self.mag_btn_l = None
        self.mag_frame_l = None
        self.mag_btn_r = None
        self.mag_frame_r = None
        self.joystick_cal_btn = None
        self.joystick_cal_frame = None

        self.load_pictures()
        self.init_interface()

    def get_left_controller(self):
        if self.current_vc is None: return None
        for c in self.current_vc.controllers:
            if c.is_joycon_left():
                return c
        return None

    def get_right_controller(self):
        if self.current_vc is None: return None
        for c in self.current_vc.controllers:
            if c.is_joycon_right():
                return c
        return None

    def get_single_controller(self):
        if self.current_vc is None or not self.current_vc.controllers: return None
        return self.current_vc.controllers[0]

    def _on_mag_clicked(self, controller, btn, frame):
        if controller is None: return
        if isinstance(self.current_vc, MockVirtualController):
            if not getattr(controller, 'is_mag_calibrating', False):
                controller.is_mag_calibrating = True
                btn.config(text="Stop Cal", fg="white")
                frame.config(bg="#FF8C00")
            else:
                controller.is_mag_calibrating = False
                btn.config(text="Mag Cal", fg="white")
                frame.config(bg=button_gray)
            btn.pack(padx=int(2 * scaling_factor), pady=int(2 * scaling_factor))
            return
        if not getattr(controller, 'is_mag_calibrating', False):
            controller.start_mag_calibration()
            btn.config(text="Stop Cal", fg="white")
            frame.config(bg="#FF8C00")
            btn.pack(padx=int(2 * scaling_factor), pady=int(2 * scaling_factor))
        else:
            controller.stop_mag_calibration()
            btn.config(text="Mag Cal", fg="white")
            frame.config(bg=button_gray)
            btn.pack(padx=int(2 * scaling_factor), pady=int(2 * scaling_factor))

    def _on_joystick_cal_clicked(self):
        if isinstance(self.current_vc, MockVirtualController):
            return
        if self.current_vc is not None and self.current_vc.controllers:
            self.window.start_joystick_calibration_from_callback(self.current_vc)

    def _update_controller_image(self):
        if self.current_vc is None: return
        if not self.current_vc.is_single():
            image = self.joycon2leftandright
        elif self.current_vc.is_single_joycon_right():
            image = self.joycon2right_sideway if self.current_vc.hold_mode == "Horizontal" else self.joycon2right_vertical
        elif self.current_vc.is_single_joycon_left():
            image = self.joycon2left_sideway if self.current_vc.hold_mode == "Horizontal" else self.joycon2left_vertical
        elif len(self.current_vc.controllers) > 0 and getattr(self.current_vc.controllers[0].controller_info, 'product_id', 0) == NSO_GAMECUBE_CONTROLLER_PID:
            image = self.gamecubecontroller
        else:
            image = self.procontroller2
        if image:
            self.controller_label.configure(image=image)

    def init_interface(self):
        block_w = controller_frame_size
        box_h = int(126 * scaling_factor)
        ping_h = int(28 * scaling_factor)
        calib_h = int(32 * scaling_factor)
        total_h = box_h + ping_h + calib_h + int(14 * scaling_factor)

        self.main_frame = tk.Frame(self.parent, width=block_w, height=total_h, bg=player_number_bg_color)
        self.main_frame.pack_propagate(True)
        self.controllers_frame = tk.Frame(self.main_frame, width=block_w, height=box_h, bg=block_color)
        self.controllers_frame.pack(side=tk.TOP)
        self.controllers_frame.pack_propagate(False)
        self.battery_frame = tk.Frame(self.main_frame, width=block_w, height=0, bg=block_color)
        self.player_row = None
        self.controller_label = None
        self.player_led_label = None

    async def _disconnect_merged_sequential(self, vc):
        async with vc._disconnect_lock:
            if not getattr(vc, 'running', False) and vc.vg_controller is None and not vc.controllers:
                return
                
            vc.running = False
            import time
            import gc
            current_time = time.strftime("%H:%M:%S")
            logger.info(f"[{current_time}] Player {vc.player_number} (Merged): Starting safe sequential disconnect sequence...")
            
            # Wait for the update thread to finish before proceeding with handle cleanup
            if hasattr(vc, 'update_thread') and vc.update_thread.is_alive():
                logger.info(f"Player {vc.player_number}: Waiting for update thread to exit...")
                vc.update_thread.join(timeout=0.5)
                if vc.update_thread.is_alive():
                    logger.warning(f"Player {vc.player_number}: Update thread did not exit in time!")
            
            if not vc.controllers and vc.vg_controller is None:
                return

            logger.info(f"Player {vc.player_number}: Cleaning up virtual device and physical connections sequentially...")
            
            with vc.state_lock:
                if hasattr(vc, 'vg_controller') and vc.vg_controller is not None:
                    logger.info(f"Player {vc.player_number}: Unregistering notifications and clearing vg_controller")
                    try:
                        vc.vg_controller.unregister_notification()
                    except Exception as e:
                        logger.debug(f"Unregister notification failed: {e}")
                    if hasattr(vc.vg_controller, 'cmp_func'):
                        vc.vg_controller.cmp_func = None
                    if hasattr(vc.vg_controller, 'close'):
                        try:
                            vc.vg_controller.close()
                        except Exception:
                            pass
                    vc.vg_controller = None
            
            gc.collect()
            
            # Disconnect each physical controller sequentially with a delay to prevent Windows BLE driver bottlenecks
            for c in list(vc.controllers):
                c.interp_running = False
                if hasattr(c, 'interp_thread') and c.interp_thread.is_alive():
                    logger.info(f"Controller {c.device.address}: Joining interpolation thread (non-blocking)...")
                    try:
                        await asyncio.to_thread(c.interp_thread.join, 0.5)
                    except Exception as e:
                        logger.warning(f"Failed to join interpolation thread: {e}")
                        
                if hasattr(c, 'client') and c.client and c.client.is_connected:
                    logger.info(f"Safe Disconnect: Disconnecting {c.device.address}...")
                    try:
                        await c.client.stop_notify(INPUT_REPORT_UUID)
                    except Exception:
                        pass
                    try:
                        await c.client.stop_notify(COMMAND_RESPONSE_UUID)
                    except Exception:
                        pass
                        
                    try:
                        await asyncio.wait_for(c.client.disconnect(), timeout=2.5)
                    except Exception as e:
                        logger.debug(f"Bluetooth disconnect error (ignored): {e}")
                        
                # Call the disconnect callback while c.client is still not None to completely avoid AttributeError
                if vc.on_disconnected_callback:
                    try:
                        await vc.on_disconnected_callback(c)
                    except Exception as e:
                        logger.error(f"Error in on_disconnected_callback: {e}")
                        
                c.client = None
                await asyncio.sleep(0.3)
                
            vc.controllers.clear()
            logger.info(f"Player {vc.player_number} (Merged): Safe sequential disconnect complete.")

    def _on_close_clicked(self):
        if self.current_vc is not None:
            vc = self.current_vc
            if hasattr(self, 'close_btn') and self.close_btn:
                self.close_btn.config(state=tk.DISABLED)
            
            if isinstance(vc, MockVirtualController):
                if hasattr(self.window, "debug_mock_controller"):
                    self.window.debug_mock_controller = False
                if hasattr(self.window, "settings_debug_btn") and self.window.settings_debug_btn and self.window.settings_debug_btn.winfo_exists():
                    update_toggle_button(self.window.settings_debug_btn, False, "Controller Connected")
                self.clearControllerInfo()
                if hasattr(self.window, "update"):
                    self.window.update([])
                return

            # Immediately transition the GUI to the "no controller connected" state
            self.clearControllerInfo()
            if hasattr(self.window, "update"):
                self.window.update([])
            
            if not vc.is_single():
                # Merge mode close button: run the highly safe sequential disconnect
                if vc.loop and vc.loop.is_running():
                    asyncio.run_coroutine_threadsafe(self._disconnect_merged_sequential(vc), vc.loop)
                else:
                    logger.error("Event loop not found or not running for merged controller.")
            else:
                # Single mode: standard trigger disconnect
                vc.trigger_disconnect()

    def load_pictures(self):
        sf = scaling_factor
        
        def load_img(path, w=None, h=None):
            try:
                img = Image.open(get_resource(path))
                if w is None or h is None:
                    orig_w, orig_h = img.size
                    w = _scaled_px(orig_w, scale=sf)
                    h = _scaled_px(orig_h, scale=sf)
                else:
                    w = max(1, int(w))
                    h = max(1, int(h))
                img = img.resize((w, h), Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.ANTIALIAS)
                return ImageTk.PhotoImage(img)
            except Exception as e:
                logger.error(f"Error scaling image {path}: {e}")
                try:
                    return tk.PhotoImage(file=get_resource(path))
                except Exception:
                    return None
        
        self.joycon2leftandright = load_img("images/joycon2leftandright.png", _scaled_px(90), _scaled_px(104))
        self.joycon2right_sideway = load_img("images/joycon2right_sideway.png", _scaled_px(104), _scaled_px(40))
        self.joycon2left_sideway = load_img("images/joycon2left_sideway.png", _scaled_px(104), _scaled_px(40))
        try:
            self.joycon2right_vertical = load_img("images/joycon2right.png", _scaled_px(40), _scaled_px(104))
            self.joycon2left_vertical = load_img("images/joycon2left.png", _scaled_px(40), _scaled_px(104))
        except Exception:
            self.joycon2right_vertical = self.joycon2right_sideway
            self.joycon2left_vertical = self.joycon2left_sideway
        self.procontroller2 = load_img("images/procontroller2.png", _scaled_px(130), _scaled_px(92))
        self.gamecubecontroller = load_img("images/nsogamecubecontroller.png", _scaled_px(130), _scaled_px(92))
        
        bat_w, bat_h = _scaled_px(34, scale=sf), _scaled_px(18, scale=sf)
        self.battery_h = load_img("images/battery_h.png", bat_w, bat_h)
        self.battery_m = load_img("images/battery_m.png", bat_w, bat_h)
        self.battery_l = load_img("images/battery_l.png", bat_w, bat_h)
        
        self.player_leds = {
            nb: load_img(f"images/player{nb}.png", player_led_width, player_led_height)
            for nb in range(1,5)
        }

    def clearControllerInfo(self):
        for attr in ['controller_label', 'player_led_label', 'close_btn', 'split_btn', 'split_frame', 'merge_btn', 'merge_frame', 'mode_switch', 'gyro_btn_l', 'gyro_btn_r', 'gyro_frame_l', 'gyro_frame_r', 'vibrate_btn', 'vibrate_frame', 'player_row', 'battery_row', 'battery_label', 'battery_label2', 'ping_row', 'ping_btn', 'calib_row', 'calib_btn', 'mag_btn_single', 'mag_frame_single', 'mag_btn_l', 'mag_frame_l', 'mag_btn_r', 'mag_frame_r', 'joystick_cal_btn', 'joystick_cal_frame']:
            widget = getattr(self, attr, None)
            if widget is not None:
                if attr in ['controller_label', 'player_row', 'battery_row', 'ping_row', 'calib_row']: widget.pack_forget()
                else: widget.place_forget()

    def get_image_for_battery_level(self, controller: Controller):
        # No accepted input report yet is an unknown state, not low battery.
        # Return None so a reconnect cannot retain a stale icon from a previous
        # controller in this player slot.
        if controller.battery_voltage is None: return None
        if controller.battery_voltage > 3.25: return self.battery_h
        if controller.battery_voltage > 3.125: return self.battery_m
        return self.battery_l

    def _set_battery_image(self, label, controller: Controller):
        image = self.get_image_for_battery_level(controller)
        label.config(image="" if image is None else image)

    def displayControllersInfo(self, virtualController : VirtualController):
        self.current_vc = virtualController
        if not self.controller_label:
            self.controller_label = tk.Label(self.controllers_frame, bg=block_color)
        self.controller_label.place(relx=0.5, rely=0.44, anchor=tk.CENTER)
        self._update_controller_image()

        if getattr(self, 'close_btn', None):
            self.close_btn.place_forget()

        # Ensure joystick and mag overlay buttons are removed
        if getattr(self, 'joystick_cal_frame', None):
            self.joystick_cal_frame.place_forget()
        if getattr(self, 'mag_frame_single', None):
            self.mag_frame_single.place_forget()
        if getattr(self, 'mag_frame_l', None):
            self.mag_frame_l.place_forget()
        if getattr(self, 'mag_frame_r', None):
            self.mag_frame_r.place_forget()

        if virtualController.is_single():
            if not getattr(self, 'battery_label', None):
                self.battery_label = tk.Label(self.controllers_frame, bg=block_color)
            self.battery_label.place(relx=0.5, rely=0.88, anchor=tk.CENTER)
            if virtualController.controllers:
                self._set_battery_image(self.battery_label, virtualController.controllers[0])
            if getattr(self, 'battery_label2', None):
                self.battery_label2.place_forget()
        else:
            if not getattr(self, 'battery_label', None):
                self.battery_label = tk.Label(self.controllers_frame, bg=block_color)
            if not getattr(self, 'battery_label2', None):
                self.battery_label2 = tk.Label(self.controllers_frame, bg=block_color)
            self.battery_label.place(relx=0.38, rely=0.88, anchor=tk.CENTER)
            if len(virtualController.controllers) > 0:
                self._set_battery_image(self.battery_label, virtualController.controllers[0])
            self.battery_label2.place(relx=0.62, rely=0.88, anchor=tk.CENTER)
            if len(virtualController.controllers) > 1:
                self._set_battery_image(self.battery_label2, virtualController.controllers[1])

        if not getattr(self, 'ping_row', None):
            self.ping_row = tk.Frame(self.main_frame, bg=background_color, width=controller_frame_size, height=int(28 * scaling_factor))
            self.ping_row.pack_propagate(False)
            self.ping_btn = make_rounded_button(
                self.ping_row,
                text="Ping",
                width=88,
                height=24,
                radius=10,
                bg_color=button_gray,
                hover_color="#5A5A5A",
                press_color="#3A3A3A",
                fg="white",
                parent_bg=background_color,
                font=scale_font(("Arial", 9, "bold")),
                command=self._on_ping_clicked
            )
            self.ping_btn.pack(pady=int(2 * scaling_factor))
        self.ping_row.pack(side=tk.TOP, pady=(int(6 * scaling_factor), 0))

        if not getattr(self, 'calib_row', None):
            self.calib_row = tk.Frame(self.main_frame, bg=background_color, width=controller_frame_size, height=int(28 * scaling_factor))
            self.calib_row.pack_propagate(False)
            self.calib_btn = make_rounded_button(
                self.calib_row,
                text="Calibration",
                width=110,
                height=24,
                radius=12,
                bg_color=button_gray,
                hover_color="#5A5A5A",
                press_color="#3A3A3A",
                fg="white",
                parent_bg=background_color,
                font=scale_font(("Arial", 9, "bold")),
                command=self._on_calibration_menu_clicked
            )
            self.calib_btn.pack(pady=int(2 * scaling_factor))
            self.window.under_controller_calib_btn = self.calib_btn
        self.calib_row.pack(side=tk.TOP, pady=(int(4 * scaling_factor), 0))

    def _on_ping_clicked(self):
        from controller import VibrationData
        if self.current_vc is not None and getattr(self.current_vc, 'loop', None) and self.current_vc.loop.is_running():
            vib = VibrationData(lf_amp=800, hf_amp=800)
            off = VibrationData(lf_amp=0, hf_amp=0)
            for controller in getattr(self.current_vc, 'controllers', []) or []:
                asyncio.run_coroutine_threadsafe(controller.set_vibration(vib, ignore_freq_scaling=True), self.current_vc.loop)
                self.window.root.after(100, lambda c=controller, loop=self.current_vc.loop, o=off: 
                    asyncio.run_coroutine_threadsafe(c.set_vibration(o, ignore_freq_scaling=True), loop))
                self.window.root.after(200, lambda c=controller, loop=self.current_vc.loop, v=vib: 
                    asyncio.run_coroutine_threadsafe(c.set_vibration(v, ignore_freq_scaling=True), loop))
                self.window.root.after(300, lambda c=controller, loop=self.current_vc.loop, o=off: 
                    asyncio.run_coroutine_threadsafe(c.set_vibration(o, ignore_freq_scaling=True), loop))

    def _on_calibration_menu_clicked(self):
        if getattr(self, 'calibration_menu_window', None) and self.calibration_menu_window.winfo_exists():
            self.calibration_menu_window.lift()
            return

        dialog = tk.Toplevel(self.window.root)
        dialog.title("Calibration")
        dialog.configure(bg=background_color)
        dialog.transient(self.window.root)
        dialog.resizable(False, False)
        self.calibration_menu_window = dialog

        apply_window_dark_theme_and_icon(dialog, bg_color=background_color)

        sf = getattr(self.window, "scaling_factor", 1.0)
        w = int(280 * sf)
        h = int(240 * sf)
        x = self.window.root.winfo_x() + (self.window.root.winfo_width() // 2) - (w // 2)
        y = self.window.root.winfo_y() + (self.window.root.winfo_height() // 2) - (h // 2)
        dialog.geometry(f"{w}x{h}+{x}+{y}")

        title_lbl = tk.Label(
            dialog,
            text="Calibration",
            font=scale_font(("Arial", 11, "bold")),
            bg=background_color,
            fg=text_color
        )
        title_lbl.pack(pady=(int(12 * sf), int(8 * sf)))

        btn_w = 230
        btn_h = 32
        btn_r = 16

        def choose_action(action):
            dialog.destroy()
            self.calibration_menu_window = None
            if action == "joystick":
                self._start_joystick_calibration_test()
            elif action == "mag":
                self._start_mag_calibration_test()
            elif action == "gyro":
                self._start_gyro_calibration_test()
            elif action == "disconnect":
                self._on_close_clicked()

        # 1. Joysticks Calibration
        btn_joy = make_rounded_button(
            dialog,
            text="Joysticks Calibration",
            width=btn_w,
            height=btn_h,
            radius=btn_r,
            bg_color=button_gray,
            hover_color="#5A5A5A",
            press_color="#3A3A3A",
            parent_bg=background_color,
            command=lambda: choose_action("joystick"),
            font=scale_font(("Arial", 10, "bold"))
        )
        btn_joy.pack(pady=int(4 * sf))

        # 2. Magnetometer Calibration
        btn_mag = make_rounded_button(
            dialog,
            text="Magnetometer Calibration",
            width=btn_w,
            height=btn_h,
            radius=btn_r,
            bg_color=button_gray,
            hover_color="#5A5A5A",
            press_color="#3A3A3A",
            parent_bg=background_color,
            command=lambda: choose_action("mag"),
            font=scale_font(("Arial", 10, "bold"))
        )
        btn_mag.pack(pady=int(4 * sf))

        # 3. Gyro Calibration
        btn_gyro = make_rounded_button(
            dialog,
            text="Gyro Calibration",
            width=btn_w,
            height=btn_h,
            radius=btn_r,
            bg_color=button_gray,
            hover_color="#5A5A5A",
            press_color="#3A3A3A",
            parent_bg=background_color,
            command=lambda: choose_action("gyro"),
            font=scale_font(("Arial", 10, "bold"))
        )
        btn_gyro.pack(pady=int(4 * sf))

        # 4. Disconnect (in red, below the rest)
        btn_disconnect = make_rounded_button(
            dialog,
            text="Disconnect",
            width=btn_w,
            height=btn_h,
            radius=btn_r,
            bg_color="#C62828",
            hover_color="#D32F2F",
            press_color="#B71C1C",
            fg="white",
            parent_bg=background_color,
            command=lambda: choose_action("disconnect"),
            font=scale_font(("Arial", 10, "bold"))
        )
        btn_disconnect.pack(pady=(int(6 * sf), int(10 * sf)))

        dialog.bind("<Escape>", lambda e: dialog.destroy())

    def _start_joystick_calibration_test(self):
        if self.current_vc is not None:
            if isinstance(self.current_vc, MockVirtualController):
                return
            from gui_wizards import JoystickCalibrationWizard
            JoystickCalibrationWizard(self.window.root, self.current_vc)

    def _start_mag_calibration_test(self):
        if self.current_vc is not None:
            if isinstance(self.current_vc, MockVirtualController):
                return
            from gui_wizards import MagnetometerCalibrationWizard
            MagnetometerCalibrationWizard(self.window.root, self.current_vc)

    def _start_gyro_calibration_test(self):
        if self.current_vc is not None:
            if isinstance(self.current_vc, MockVirtualController):
                return
            from gui_wizards import GyroCalibrationWizard
            GyroCalibrationWizard(self.window.root, self.current_vc)

