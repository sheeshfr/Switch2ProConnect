import ctypes
from ctypes import wintypes
import logging
import math
import os
import sys
import tkinter as tk
from tkinter import ttk
import tkinter.font as tkFont
from PIL import Image, ImageTk, ImageDraw
from config import back_button_label

logger = logging.getLogger(__name__)

background_color = "#2D2D2D"
button_gray = "#4B4B4B"
highlight_color = "#00C3E3"
text_color = "#FFFFFF"

COLOR_OFF = "#C62828"
COLOR_OFF_HOVER = "#D32F2F"
COLOR_OFF_PRESS = "#B71C1C"

COLOR_ON = "#2E7D32"
COLOR_ON_HOVER = "#388E3C"
COLOR_ON_PRESS = "#1B5E20"

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

def normalize_app_path(path):
    if not path:
        return ""
    try:
        return os.path.normcase(os.path.abspath(os.path.normpath(path)))
    except Exception:
        return os.path.normcase(os.path.normpath(path))

def get_exe_display_name(path):
    if not path:
        return "Choose App"
    try:
        import win32api
        info = win32api.GetFileVersionInfo(path, "\\")
        lang, codepage = win32api.GetFileVersionInfo(path, "\\VarFileInfo\\Translation")[0]
        for key in ("FileDescription", "ProductName"):
            value = win32api.GetFileVersionInfo(path, f"\\StringFileInfo\\{lang:04x}{codepage:04x}\\{key}")
            if value:
                return str(value)
    except Exception:
        pass
    return os.path.splitext(os.path.basename(path))[0] or "Choose App"

_EXE_ICON_CACHE = {}
_TASKBAR_ICON_CACHE = {}

def _hicon_to_photoimage(hicon, size=(22, 22), should_destroy=False):
    if not hicon:
        return None
    try:
        from PIL import Image, ImageTk
        from ctypes import wintypes
        import ctypes

        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32

        gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
        gdi32.DeleteObject.restype = wintypes.BOOL
        user32.DestroyIcon.argtypes = [wintypes.HICON]
        user32.DestroyIcon.restype = wintypes.BOOL
        user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
        user32.ReleaseDC.restype = ctypes.c_int
        user32.GetDC.argtypes = [wintypes.HWND]
        user32.GetDC.restype = wintypes.HDC
        gdi32.GetObjectW.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p]
        gdi32.GetObjectW.restype = ctypes.c_int
        gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
        gdi32.GetDIBits.restype = ctypes.c_int

        class ICONINFO(ctypes.Structure):
            _fields_ = [
                ('fIcon', wintypes.BOOL),
                ('xHotspot', wintypes.DWORD),
                ('yHotspot', wintypes.DWORD),
                ('hbmMask', wintypes.HBITMAP),
                ('hbmColor', wintypes.HBITMAP)
            ]

        user32.GetIconInfo.argtypes = [wintypes.HICON, ctypes.POINTER(ICONINFO)]
        user32.GetIconInfo.restype = wintypes.BOOL

        class BITMAP(ctypes.Structure):
            _fields_ = [
                ('bmType', wintypes.LONG),
                ('bmWidth', wintypes.LONG),
                ('bmHeight', wintypes.LONG),
                ('bmWidthBytes', wintypes.LONG),
                ('bmPlanes', wintypes.WORD),
                ('bmBitsPixel', wintypes.WORD),
                ('bmBits', ctypes.c_void_p)
            ]

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ('biSize', wintypes.DWORD),
                ('biWidth', wintypes.LONG),
                ('biHeight', wintypes.LONG),
                ('biPlanes', wintypes.WORD),
                ('biBitCount', wintypes.WORD),
                ('biCompression', wintypes.DWORD),
                ('biSizeImage', wintypes.DWORD),
                ('biXPelsPerMeter', wintypes.LONG),
                ('biYPelsPerMeter', wintypes.LONG),
                ('biClrUsed', wintypes.DWORD),
                ('biClrImportant', wintypes.DWORD)
            ]

        ii = ICONINFO()
        if not user32.GetIconInfo(hicon, ctypes.byref(ii)):
            if should_destroy:
                user32.DestroyIcon(hicon)
            return None

        bm = BITMAP()
        hbm = ii.hbmColor if ii.hbmColor else ii.hbmMask
        if not hbm or not gdi32.GetObjectW(hbm, ctypes.sizeof(bm), ctypes.byref(bm)):
            if ii.hbmColor: gdi32.DeleteObject(ii.hbmColor)
            if ii.hbmMask: gdi32.DeleteObject(ii.hbmMask)
            if should_destroy: user32.DestroyIcon(hicon)
            return None

        w, h = bm.bmWidth, bm.bmHeight
        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth = w
        bmi.biHeight = -h
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        bmi.biCompression = 0

        buf = ctypes.create_string_buffer(w * h * 4)
        hdc = user32.GetDC(0)
        gdi32.GetDIBits(hdc, hbm, 0, h, buf, ctypes.byref(bmi), 0)
        user32.ReleaseDC(0, hdc)

        if ii.hbmColor: gdi32.DeleteObject(ii.hbmColor)
        if ii.hbmMask: gdi32.DeleteObject(ii.hbmMask)
        if should_destroy: user32.DestroyIcon(hicon)

        img = Image.frombuffer('RGBA', (w, h), buf, 'raw', 'BGRA', 0, 1)
        if size != (w, h):
            img = img.resize(size, Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(img)
    except Exception as e:
        logger.debug(f"_hicon_to_photoimage error: {e}")
        return None

def get_file_icon(file_path, size=(18, 18)):
    if not file_path or not os.path.exists(file_path):
        return None
    cache_key = (os.path.normpath(file_path).lower(), size)
    if cache_key in _EXE_ICON_CACHE:
        return _EXE_ICON_CACHE[cache_key]

    try:
        from ctypes import wintypes
        import ctypes

        class SHFILEINFO(ctypes.Structure):
            _fields_ = [
                ('hIcon', wintypes.HICON),
                ('iIcon', ctypes.c_int),
                ('dwAttributes', wintypes.DWORD),
                ('szDisplayName', wintypes.WCHAR * 260),
                ('szTypeName', wintypes.WCHAR * 80)
            ]

        SHGFI_ICON = 0x000000100
        SHGFI_SMALLICON = 0x000000001

        sfi = SHFILEINFO()
        res = ctypes.windll.shell32.SHGetFileInfoW(
            file_path, 0, ctypes.byref(sfi), ctypes.sizeof(sfi),
            SHGFI_ICON | SHGFI_SMALLICON
        )
        if not res or not sfi.hIcon:
            _EXE_ICON_CACHE[cache_key] = None
            return None

        photo = _hicon_to_photoimage(sfi.hIcon, size, should_destroy=True)
        _EXE_ICON_CACHE[cache_key] = photo
        return photo
    except Exception as e:
        logger.debug(f"Failed to extract icon from {file_path}: {e}")
        _EXE_ICON_CACHE[cache_key] = None
        return None

def get_window_taskbar_icon(hwnd=None, file_path=None, size=(22, 22)):
    cache_key = (hwnd, os.path.normpath(file_path).lower() if file_path else "", size)
    if cache_key in _TASKBAR_ICON_CACHE:
        return _TASKBAR_ICON_CACHE[cache_key]

    photo = None
    if hwnd:
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            user32.GetClassLongPtrW.restype = ctypes.c_void_p
            user32.GetClassLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]

            # 1. Ask the window directly via WM_GETICON (ICON_SMALL2, ICON_SMALL, ICON_BIG)
            hicon = None
            for itype in (2, 0, 1):
                res = ctypes.c_void_p()
                if user32.SendMessageTimeoutW(hwnd, 0x007F, itype, 0, 0x0002, 100, ctypes.byref(res)):
                    if res.value:
                        hicon = res.value
                        break
            # 2. Get window class icon
            if not hicon:
                hicon = user32.GetClassLongPtrW(hwnd, -34)  # GCLP_HICONSM
            if not hicon:
                hicon = user32.GetClassLongPtrW(hwnd, -14)  # GCLP_HICON

            if hicon:
                photo = _hicon_to_photoimage(hicon, size, should_destroy=False)
        except Exception as e:
            logger.debug(f"Failed to extract taskbar icon from hwnd {hwnd}: {e}")

    # 3. Fallback to executable file icon
    if not photo and file_path and os.path.exists(file_path):
        photo = get_file_icon(file_path, size)

    _TASKBAR_ICON_CACHE[cache_key] = photo
    return photo

def apply_window_dark_theme_and_icon(window, bg_color=None):
    """Apply immersive dark mode, caption color (#2D2D2D), white text, and Switch 2 Joy-Con icon to a window."""
    if bg_color is None:
        bg_color = background_color
    try:
        window.configure(bg=bg_color)
    except Exception:
        pass

    # 1. Apply Switch 2 Joy-Con icon via Tkinter iconphoto
    try:
        from config import get_resource
        icon_path = get_resource("images/icon.png")
        if icon_path and os.path.exists(icon_path):
            img = ImageTk.PhotoImage(file=icon_path)
            window._top_icon_ref = img
            window.iconphoto(False, img)
    except Exception:
        pass

    # 2. Apply Windows DWM dark titlebar and native icon via Win32 API
    def _apply_dwm():
        try:
            window.update_idletasks()
            raw_hwnd = int(window.winfo_id())
            user32 = ctypes.windll.user32
            user32.GetAncestor.argtypes = [ctypes.c_void_p, wintypes.UINT]
            user32.GetAncestor.restype = ctypes.c_void_p
            hwnd = user32.GetAncestor(ctypes.c_void_p(raw_hwnd), 2) or raw_hwnd
            if hwnd:
                color = bg_color.lstrip('#')
                r, g, b = int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)
                color_int = (b << 16) | (g << 8) | r
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(ctypes.c_int(color_int)), 4)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(ctypes.c_int(0xFFFFFF)), 4)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(ctypes.c_int(1)), 4)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(ctypes.c_int(2)), 4)

                # Set native icon for titlebar and Alt-Tab
                try:
                    from config import get_resource
                    ico_path = get_resource("images/icon.ico")
                    if ico_path and os.path.exists(ico_path):
                        IMAGE_ICON = 1
                        LR_LOADFROMFILE = 0x00000010
                        WM_SETICON = 0x0080
                        ICON_SMALL = 0
                        ICON_BIG = 1
                        user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
                        user32.LoadImageW.restype = wintypes.HANDLE
                        hicon_sm = user32.LoadImageW(None, ico_path, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
                        if hicon_sm:
                            user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon_sm)
                        hicon_lg = user32.LoadImageW(None, ico_path, IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
                        if hicon_lg:
                            user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon_lg)
                except Exception:
                    pass
        except Exception:
            pass

    _apply_dwm()
    try:
        window.after(30, _apply_dwm)
    except Exception:
        pass

_ROUNDED_RECT_CACHE = {}

def get_rounded_rect_image(w, h, r=6, bg="#3A3A3A", border_color=None, border_width=0, parent_bg=None, icon_img=None, icon_size=None, parent=None):
    if parent_bg is None:
        parent_bg = background_color
    icon_key = None
    if icon_img is not None:
        icon_key = icon_img if isinstance(icon_img, str) else id(icon_img)
    root = getattr(parent, "_root", lambda: None)() or getattr(parent, "tk", None) or getattr(getattr(parent, "master", None), "tk", None) or tk._default_root
    key = (id(root), w, h, r, bg, border_color, border_width, parent_bg, icon_key, icon_size)
    cached = _ROUNDED_RECT_CACHE.get(key)
    if cached is not None:
        if root is not None:
            try:
                tk_call = getattr(root, "call", None) or getattr(getattr(root, "tk", None), "call", None)
                if tk_call:
                    tk_call('image', 'type', str(cached))
                    return cached
            except Exception:
                pass
        _ROUNDED_RECT_CACHE.pop(key, None)

    from PIL import Image, ImageTk, ImageDraw
    scale = 3
    sw, sh, sr = max(1, int(w * scale)), max(1, int(h * scale)), max(1, int(r * scale))
    bw = int(border_width * scale)
    p_hex = parent_bg.lstrip('#') if isinstance(parent_bg, str) else "2D2D2D"
    if len(p_hex) == 6:
        p_rgb = (int(p_hex[0:2], 16), int(p_hex[2:4], 16), int(p_hex[4:6], 16), 255)
    else:
        p_rgb = (45, 45, 45, 255)
    img = Image.new('RGBA', (sw, sh), p_rgb)
    draw = ImageDraw.Draw(img)
    if border_color and bw > 0:
        draw.rounded_rectangle([0, 0, sw - 1, sh - 1], radius=sr, fill=bg, outline=border_color, width=bw)
    else:
        draw.rounded_rectangle([0, 0, sw - 1, sh - 1], radius=sr, fill=bg)

    if icon_img is not None:
        try:
            if isinstance(icon_img, str):
                from config import get_resource
                raw_icon = Image.open(get_resource(icon_img)).convert('RGBA')
            else:
                raw_icon = icon_img.convert('RGBA')
            if icon_size:
                iw, ih = int(icon_size[0] * scale), int(icon_size[1] * scale)
            else:
                iw = min(int(raw_icon.width * scale), sw - int(8 * scale))
                ih = min(int(raw_icon.height * scale), sh - int(8 * scale))
            raw_icon = raw_icon.resize((iw, ih), Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.ANTIALIAS)
            img.paste(raw_icon, ((sw - iw) // 2, (sh - ih) // 2), mask=raw_icon)
        except Exception as e:
            logger.debug("Failed to composite icon on rounded rect: %s", e)

    img = img.resize((w, h), Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.ANTIALIAS)
    _ROUNDED_RECT_CACHE[key] = ImageTk.PhotoImage(img)
    return _ROUNDED_RECT_CACHE[key]

def make_rounded_button(parent, text="", command=None, width=100, height=32, radius=6,
                        bg_color=None, hover_color="#4A4A4A", press_color="#2A2A2A",
                        fg="white", font=None, parent_bg=None, icon_image=None, icon_size=None, **kwargs):
    if bg_color is None:
        bg_color = button_gray
    if parent_bg is None:
        parent_bg = getattr(parent, "cget", lambda k: background_color)("bg") if parent is not None else background_color
    if font is None:
        font = scale_font(("Arial", 10, "bold"))
    w = int(width * scaling_factor)
    h = int(height * scaling_factor)
    r = int(radius * scaling_factor)
    scaled_icon_size = (int(icon_size[0] * scaling_factor), int(icon_size[1] * scaling_factor)) if icon_size else None

    img_normal = get_rounded_rect_image(w, h, r, bg_color, parent_bg=parent_bg, icon_img=icon_image, icon_size=scaled_icon_size, parent=parent)
    img_hover = get_rounded_rect_image(w, h, r, hover_color, parent_bg=parent_bg, icon_img=icon_image, icon_size=scaled_icon_size, parent=parent)
    img_press = get_rounded_rect_image(w, h, r, press_color, parent_bg=parent_bg, icon_img=icon_image, icon_size=scaled_icon_size, parent=parent)

    cursor = kwargs.pop("cursor", "hand2" if command is not None else "arrow")
    btn = tk.Button(
        parent,
        text=text,
        image=img_normal,
        compound=tk.CENTER,
        font=font,
        fg=fg,
        bg=parent_bg,
        activebackground=parent_bg,
        activeforeground=fg,
        relief=tk.FLAT,
        bd=0,
        highlightthickness=0,
        cursor=cursor,
        command=command,
        **kwargs
    )
    btn.image_normal = img_normal
    btn.image_hover = img_hover
    btn.image_press = img_press
    btn.rounded_w = w
    btn.rounded_h = h
    btn.rounded_r = r
    btn.rounded_bg = bg_color
    btn.rounded_parent_bg = parent_bg
    btn.icon_image = icon_image
    btn.icon_size = icon_size

    def on_enter(e):
        try:
            if btn.cget("state") != tk.DISABLED:
                btn.config(image=btn.image_hover)
        except Exception:
            pass

    def on_leave(e):
        try:
            if btn.cget("state") != tk.DISABLED:
                btn.config(image=btn.image_normal)
        except Exception:
            pass

    def on_press(e):
        try:
            if btn.cget("state") != tk.DISABLED:
                btn.config(image=btn.image_press)
        except Exception:
            pass

    def on_release(e):
        try:
            if btn.cget("state") != tk.DISABLED:
                btn.config(image=btn.image_hover)
        except Exception:
            pass

    btn.bind("<Enter>", on_enter, add="+")
    btn.bind("<Leave>", on_leave, add="+")
    btn.bind("<ButtonPress-1>", on_press, add="+")
    btn.bind("<ButtonRelease-1>", on_release, add="+")

    return btn

COLOR_OFF = "#C62828"
COLOR_OFF_HOVER = "#D32F2F"
COLOR_OFF_PRESS = "#B71C1C"

COLOR_ON = "#2E7D32"
COLOR_ON_HOVER = "#388E3C"
COLOR_ON_PRESS = "#1B5E20"

def set_rounded_button_bg(btn, bg_color, hover_color=None, press_color=None):
    if not hasattr(btn, "rounded_w"):
        return
    w, h, r = btn.rounded_w, btn.rounded_h, btn.rounded_r
    parent_bg = getattr(btn, "rounded_parent_bg", background_color)
    if hover_color is None:
        hover_color = bg_color
    if press_color is None:
        press_color = bg_color
    btn.image_normal = get_rounded_rect_image(w, h, r, bg_color, parent_bg=parent_bg)
    btn.image_hover = get_rounded_rect_image(w, h, r, hover_color, parent_bg=parent_bg)
    btn.image_press = get_rounded_rect_image(w, h, r, press_color, parent_bg=parent_bg)
    btn.rounded_bg = bg_color
    try:
        btn.config(image=btn.image_normal)
    except Exception:
        pass

def update_toggle_button(btn, is_on, label_prefix):
    text = f"{label_prefix} - {'ON' if is_on else 'OFF'}"
    bg = COLOR_ON if is_on else COLOR_OFF
    hover = COLOR_ON_HOVER if is_on else COLOR_OFF_HOVER
    press = COLOR_ON_PRESS if is_on else COLOR_OFF_PRESS
    set_rounded_button_bg(btn, bg, hover, press)
    try:
        btn.config(text=text)
    except Exception:
        pass


class Tooltip:
    """Hover tooltips disabled per user request."""

    def __init__(self, widget=None, text_getter=None, delay_ms=350, position_adjust=None):
        self.widget = widget
        self.text_getter = text_getter
        self.delay_ms = delay_ms
        self.position_adjust = position_adjust or (2, -2)
        self.tip = None
        self.after_id = None

    def _schedule(self, event=None):
        pass

    def _cancel(self):
        pass

    def _show(self):
        pass

    def _hide(self, event=None):
        pass


def create_tooltip(widget, text, delay_ms=300):
    tip_window = None
    after_id = None

    def show():
        nonlocal tip_window
        if tip_window or not widget.winfo_exists():
            return
        try:
            x = widget.winfo_rootx() + 20
            y = widget.winfo_rooty() + widget.winfo_height() + 4
            tip_window = tw = tk.Toplevel(widget)
            tw.wm_overrideredirect(True)
            tw.configure(bg="#1E1E1E")
            try:
                tw.attributes("-topmost", True)
            except Exception:
                pass
            border_frame = tk.Frame(tw, bg="#555555", padx=1, pady=1)
            border_frame.pack()
            inner_frame = tk.Frame(border_frame, bg="#1E1E1E", padx=8, pady=5)
            inner_frame.pack()
            lbl = tk.Label(
                inner_frame,
                text=text,
                fg="#FFFFFF",
                bg="#1E1E1E",
                font=("Arial", 9),
                justify=tk.LEFT,
                wraplength=280
            )
            lbl.pack()
            tw.geometry(f"+{x}+{y}")
        except Exception:
            pass

    def enter(event=None):
        nonlocal after_id
        cancel()
        after_id = widget.after(delay_ms, show)

    def cancel(event=None):
        nonlocal after_id, tip_window
        if after_id:
            try:
                widget.after_cancel(after_id)
            except Exception:
                pass
            after_id = None
        if tip_window:
            try:
                tip_window.destroy()
            except Exception:
                pass
            tip_window = None

    widget.bind("<Enter>", enter, add="+")
    widget.bind("<Leave>", cancel, add="+")
    widget.bind("<ButtonPress>", cancel, add="+")
    widget.bind("<Destroy>", cancel, add="+")
    widget._tooltip_show = show
    widget._tooltip_enter = enter
    widget._tooltip_cancel = cancel
    return cancel


class RecordingEntry(tk.Text):
    """Single-line, read-only display of a recorded Custom input. It is a drop-in for the
    tk.Entry it replaces (entry-style get/insert/delete, and config(state=...) is accepted
    and ignored since it is always read-only), but renders the leading M/KB prefix of each
    token two font sizes smaller than the rest via text tags.

    The default "Text" bindtag is removed so the widget can't be typed into and never
    consumes keystrokes; while it holds focus during recording, key events still bubble up
    to the root recorder binding exactly as the old readonly Entry allowed."""

    def __init__(self, parent, normal_font, prefix_font, width, bg, fg):
        super().__init__(parent, height=1, width=width, font=normal_font, bg=bg, fg=fg,
                         bd=0, highlightthickness=0, wrap="none", cursor="arrow",
                         insertwidth=0, padx=0, pady=0, takefocus=1, exportselection=0)
        self.is_custom_recording_entry = True
        self.tag_configure("normal", font=normal_font, justify="center")
        self.tag_configure("prefix", font=prefix_font, justify="center")
        self.bindtags(tuple(t for t in self.bindtags() if t != "Text"))
        # tk.Text top-aligns its single line; when fill=Y stretches it to the row height,
        # split the leftover space into equal top/bottom padding so the text is centered.
        self._line_font = tkFont.Font(font=normal_font)
        self._applied_pady = -1
        self.bind("<Configure>", self._recenter, add="+")

    def _recenter(self, event=None):
        try:
            pad = max(0, (self.winfo_height() - self._line_font.metrics("linespace")) // 2)
            if pad != self._applied_pady:
                self._applied_pady = pad
                super().configure(pady=pad)
        except Exception:
            pass

    @staticmethod
    def _split_prefix(segment):
        # Leading prefix to shrink: "M" before mouse-button digits, "KB" before a key name.
        if len(segment) > 1 and segment[0] == "M" and segment[1:].isdigit():
            return "M", segment[1:]
        if len(segment) > 2 and segment.startswith("KB"):
            return "KB", segment[2:]
        return "", segment

    def get(self, *args):
        if args:
            return super().get(*args)
        return super().get("1.0", "end-1c")

    def delete(self, *args):
        super().delete("1.0", "end")

    def insert(self, index, text="", *args):
        for i, seg in enumerate(str(text).split("+")):
            if i:
                super().insert("end", "+", ("normal",))
            prefix, rest = self._split_prefix(seg)
            if prefix:
                super().insert("end", prefix, ("prefix",))
            if rest:
                super().insert("end", rest, ("normal",))

    def config(self, cnf=None, **kwargs):
        if cnf:
            kwargs.update(cnf)
        kwargs.pop("state", None)
        if kwargs:
            super().configure(**kwargs)

    configure = config


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

class FocusOutline:
    def __init__(self, root):
        self.root = root
        self.lines = [tk.Frame(root, bg="white") for _ in range(4)]
        self.active = False
        self.target_widget = None

    def update(self, widget):
        if not widget or not widget.winfo_exists():
            self.hide()
            return
            
        self.target_widget = widget
        try:
            w = widget.winfo_width()
            h = widget.winfo_height()
            
            pad = 2
            t = 2 # thickness
            
            is_toggle_switch = False
            is_standard_btn = False
            is_dropdown_or_slider = False
            
            try:
                if isinstance(widget, (ttk.Combobox, tk.Scale)):
                    is_dropdown_or_slider = True
                elif isinstance(widget, tk.Button):
                    if hasattr(widget.master, 'master') and hasattr(widget.master.master, 'buttons'):
                        is_toggle_switch = True
                    else:
                        is_standard_btn = True
            except:
                pass
            
            if is_dropdown_or_slider:
                shift = 0
            elif is_toggle_switch:
                shift = 1
            elif is_standard_btn:
                shift = 2
            else:
                shift = 0
            
            start_x = -pad - t - shift
            start_y = -pad - t - shift
            
            right_x = w + pad - shift
            bottom_y = h + pad - shift
            
            self.lines[0].place(in_=widget, x=start_x, y=start_y, width=w+2*pad+2*t, height=t)
            self.lines[1].place(in_=widget, x=start_x, y=bottom_y, width=w+2*pad+2*t, height=t)
            self.lines[2].place(in_=widget, x=start_x, y=start_y, width=t, height=h+2*pad+2*t)
            self.lines[3].place(in_=widget, x=right_x, y=start_y, width=t, height=h+2*pad+2*t)
            
            for line in self.lines:
                line.lift()
            self.active = True
        except Exception:
            self.hide()
            
    def hide(self):
        if self.active:
            for line in self.lines:
                line.place_forget()
            self.active = False
            self.target_widget = None

    def refresh(self):
        if self.target_widget:
            self.update(self.target_widget)


class BackButtonSelector(tk.Button):
    """Drop-in replacement for the Back Button Option with direct controller listening and rounded styling."""

    def __init__(self, parent, gui, key=None, font=None, auto_fit=True, display_overrides=None, fixed_size=None):
        self._gui = gui
        self._key = key
        self._value = "None"
        self._font = font or scale_font(("Arial", 11, "bold"))
        self._auto_fit = auto_fit
        self._display_overrides = display_overrides or {}
        self._fnt = tkFont.Font(font=self._font)
        self._char_px = self._fnt.measure("0") or 1
        self._min_chars = max(1, self._fit_chars("Waiting..."))
        self._fixed_size = fixed_size

        btn_w = fixed_size[0] if fixed_size else int(100 * scaling_factor)
        btn_h = fixed_size[1] if fixed_size else int(32 * scaling_factor)
        btn_r = int(6 * scaling_factor)

        self._img_normal = get_rounded_rect_image(btn_w, btn_h, btn_r, button_gray)
        self._img_hover = get_rounded_rect_image(btn_w, btn_h, btn_r, "#4A4A4A")
        self._img_press = get_rounded_rect_image(btn_w, btn_h, btn_r, "#2A2A2A")

        self.rounded_w = btn_w
        self.rounded_h = btn_h
        self.rounded_r = btn_r
        self.image_normal = self._img_normal
        self.image_hover = self._img_hover
        self.image_press = self._img_press

        super().__init__(
            parent,
            text="",
            image=self._img_normal,
            compound=tk.CENTER,
            font=self._font,
            fg="white",
            bg=background_color,
            activebackground=background_color,
            activeforeground="white",
            relief=tk.FLAT,
            bd=0,
            highlightthickness=0,
            cursor="hand2",
            command=self._on_click,
        )

        def on_enter(e):
            try:
                if self.cget("state") != tk.DISABLED:
                    self.config(image=getattr(self, "image_hover", self._img_hover))
            except Exception:
                pass

        def on_leave(e):
            try:
                if self.cget("state") != tk.DISABLED:
                    self.config(image=getattr(self, "image_normal", self._img_normal))
            except Exception:
                pass

        def on_press(e):
            try:
                if self.cget("state") != tk.DISABLED:
                    self.config(image=getattr(self, "image_press", self._img_press))
            except Exception:
                pass

        def on_release(e):
            try:
                if self.cget("state") != tk.DISABLED:
                    self.config(image=getattr(self, "image_hover", self._img_hover))
            except Exception:
                pass

        self.bind("<Enter>", on_enter, add="+")
        self.bind("<Leave>", on_leave, add="+")
        self.bind("<ButtonPress-1>", on_press, add="+")
        self.bind("<ButtonRelease-1>", on_release, add="+")

    def _fit_chars(self, label):
        return -(-self._fnt.measure(label) // self._char_px)

    def _on_click(self):
        if self._key in ("gl", "gr"):
            if getattr(self._gui, "waiting_for_back_button_assign", None) == (self._key, self):
                self._gui.cancel_back_button_assign()
            else:
                self._gui.start_back_button_assign(self._key, self)
        else:
            self._gui.open_back_button_popup(self)

    def get(self):
        return self._value

    def display_label(self, value):
        if not value or value in ("Default", "None"):
            return ""
        return self._display_overrides.get(value, back_button_label(value))

    def set(self, value):
        self._value = value
        label = self.display_label(value)
        self.config(text=label)

    def select_value(self, value):
        self.set(value)
        self.event_generate("<<ComboboxSelected>>")


class ProfileBackButtonSelector(BackButtonSelector):
    """BackButtonSelector tailored for the Edit Profiles dialog with dark pill styling and direct profile binding."""

    def __init__(self, parent, gui, profile_key, key, current_val, font=None, fixed_size=None):
        self.profile_key = profile_key  # None for Default, exe name string for game
        self.target_profile = profile_key
        self._button_key = key          # "gl" or "gr"
        self._gui = gui

        sf = getattr(gui, "scaling_factor", 1.0)
        size = fixed_size or (int(76 * sf), int(28 * sf))
        btn_w, btn_h = size
        btn_r = max(1, btn_h // 2)

        super().__init__(
            parent,
            gui,
            key=key,
            font=font or scale_font(("Arial", 9, "bold")),
            auto_fit=False,
            fixed_size=size
        )

        dark_bg = "#222222"
        dark_hover = "#2E2E2E"
        dark_press = "#181818"
        self._img_normal = get_rounded_rect_image(btn_w, btn_h, btn_r, dark_bg, parent_bg="#3A3A3A", parent=parent)
        self._img_hover = get_rounded_rect_image(btn_w, btn_h, btn_r, dark_hover, parent_bg="#3A3A3A", parent=parent)
        self._img_press = get_rounded_rect_image(btn_w, btn_h, btn_r, dark_press, parent_bg="#3A3A3A", parent=parent)
        self.image_normal = self._img_normal
        self.image_hover = self._img_hover
        self.image_press = self._img_press
        self.rounded_r = btn_r
        self.config(image=self._img_normal, bg="#3A3A3A", activebackground="#3A3A3A", fg="white")
        self.set(current_val)

        self.bind("<Button-3>", lambda e: self._gui.open_back_button_popup(self))
        Tooltip(self, lambda: f"Click to assign {self._button_key.upper()} via controller (or Right-Click for menu)")

    def _on_click(self):
        if getattr(self._gui, "waiting_for_back_button_assign", None) == (self._button_key, self):
            self._gui.cancel_back_button_assign()
        else:
            self._gui.start_back_button_assign(self._button_key, self)

    def select_value(self, value):
        from config import CONFIG
        self.set(value)
        if self.profile_key is None:
            CONFIG.set_game_mapping(None, self._button_key, value)
            if CONFIG.get_active_game_context() is None:
                CONFIG.set_mapping_setting_scoped(self._button_key, value)
        else:
            CONFIG.set_game_mapping(self.profile_key, self._button_key, value)
            if CONFIG.get_active_game_context() == self.profile_key:
                CONFIG.set_mapping_setting_scoped(self._button_key, value)
        CONFIG.save_config()
        if hasattr(self._gui, "_refresh_mapping_comboboxes"):
            self._gui._refresh_mapping_comboboxes()
        self.event_generate("<<ComboboxSelected>>")



class ToggleSwitch(tk.Frame):
    def __init__(self, parent, labels, values, initial_value, command, bg_color, widths=None):
        super().__init__(parent, bg=bg_color)
        self.labels = labels  
        self.values = values  
        self.command = command
        self.bg_color = bg_color
        self.buttons = []

        for i, label in enumerate(labels):
            # Create a wrapper frame to simulate the border/outline
            frame = tk.Frame(self, bg=bg_color)
            frame.pack(side=tk.LEFT, padx=int(2 * scaling_factor))
            
            w = widths[i] if widths else 8
            btn = tk.Button(frame, text=label, width=w, font=scale_font(("Arial", 11, "bold")),
                            bd=0, relief=tk.FLAT, highlightthickness=0,
                            command=lambda idx=i: self._on_click(idx))
            btn.pack(padx=0, pady=0) # Base state: no padding
            self.buttons.append((btn, frame))

        try:
            self.current_index = values.index(initial_value)
        except ValueError:
            self.current_index = 0
        self._update_ui()

    def _on_click(self, index):
        if self.current_index != index:
            self.current_index = index
            self._update_ui()
            self.command(self.values[index])

    def _update_ui(self):
        for i, (btn, frame) in enumerate(self.buttons):
            if i == self.current_index:
                # Active: Show Cyan Frame Border
                frame.config(bg=highlight_color)
            else:
                # Inactive: Border matches button color
                frame.config(bg=button_gray)
            btn.config(bg=button_gray, fg="#FFFFFF", padx=0, pady=0)
            btn.pack(padx=int(2 * scaling_factor), pady=int(2 * scaling_factor)) # Consistent size

    def set_value(self, value):
        try:
            self.current_index = self.values.index(value)
            self._update_ui()
        except ValueError:
            pass

    def update_options(self, labels, values, current_value, widths=None):
        # Destroy all old buttons and frames
        for btn, frame in self.buttons:
            try:
                btn.destroy()
            except:
                pass
            try:
                frame.destroy()
            except:
                pass
        self.buttons.clear()
        
        self.labels = labels
        self.values = values
        
        for i, label in enumerate(labels):
            # Create a wrapper frame to simulate the border/outline
            frame = tk.Frame(self, bg=self.bg_color)
            frame.pack(side=tk.LEFT, padx=int(2 * scaling_factor))
            
            w = widths[i] if widths else 8
            btn = tk.Button(frame, text=label, width=w, font=scale_font(("Arial", 11, "bold")),
                            bd=0, relief=tk.FLAT, highlightthickness=0,
                            command=lambda idx=i: self._on_click(idx))
            btn.pack(padx=0, pady=0) # Base state: no padding
            self.buttons.append((btn, frame))
            
        try:
            self.current_index = values.index(current_value)
        except ValueError:
            self.current_index = 0
        self._update_ui()


def get_checkbox_images(size_px=18, scaling=1.0):
    s = max(16, int(size_px * scaling))
    r = max(2, int(3 * scaling))
    bw = max(1, int(1.5 * scaling))

    # Unchecked image: dark rounded rect with subtle border
    img_uncheck = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img_uncheck)
    d.rounded_rectangle([1, 1, s - 2, s - 2], radius=r, fill="#383838", outline="#686868", width=bw)

    # Checked image: accent green (#2E7D32) with white checkmark
    img_check = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d2 = ImageDraw.Draw(img_check)
    d2.rounded_rectangle([1, 1, s - 2, s - 2], radius=r, fill="#2E7D32", outline="#43A047", width=bw)
    p1 = (int(0.24 * s), int(0.50 * s))
    p2 = (int(0.42 * s), int(0.72 * s))
    p3 = (int(0.76 * s), int(0.28 * s))
    lw = max(2, int(2.2 * scaling))
    d2.line([p1, p2, p3], fill="white", width=lw, joint="curve")

    return ImageTk.PhotoImage(img_uncheck), ImageTk.PhotoImage(img_check)

