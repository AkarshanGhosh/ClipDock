"""
ClipDock - clipboard history that docks above the Windows taskbar.

* Always on top, sits just above the taskbar (bottom-right of the work area).
* Never steals focus, so the text cursor stays where you left it.
* Click any item -> it is pasted at the cursor of the app you were using.
* Drag the window by ANY empty spot (or by dragging an item), resize it from any edge or corner.
* Name your items (pencil button) and search by text or by name.
* Day / night theme, pin favourites, delete, pause capture, collapse to a slim bar.
* Hover any button to see what it does. Only one copy runs at a time.
* Size, position and theme are remembered between runs.
* History:  %APPDATA%\\ClipDock\\history.json      Settings: %APPDATA%\\ClipDock\\settings.json

Run from source:  pythonw clipdock.pyw   (Python 3.8+ on Windows, no extra packages)
Install as an app: double-click install_shortcut.bat once.
"""
import ctypes
import json
import os
import sys
import threading
import time
import tkinter as tk
import urllib.request
import webbrowser
from ctypes import wintypes
from tkinter import font as tkfont

if sys.platform != "win32":
    sys.exit("ClipDock runs on Windows only.")

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

# ---------------------------------------------------------------- Win32 helpers
user32 = ctypes.windll.user32
user32.GetForegroundWindow.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.GetAncestor.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]

_get_long = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
_set_long = getattr(user32, "SetWindowLongPtrW", None) or user32.SetWindowLongW
_get_long.restype = ctypes.c_ssize_t
_get_long.argtypes = [wintypes.HWND, ctypes.c_int]
_set_long.restype = ctypes.c_ssize_t
_set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_FRAMECHANGED = 0x1, 0x2, 0x10, 0x20
HWND_TOPMOST = -1
IGNORED_TARGET_CLASSES = {"Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Progman", "WorkerW"}


def set_noactivate(hwnd, on):
    ex = _get_long(hwnd, GWL_EXSTYLE)
    ex = (ex | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW) if on else (ex & ~WS_EX_NOACTIVATE)
    _set_long(hwnd, GWL_EXSTYLE, ex)
    user32.SetWindowPos(hwnd, None, 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED)


def keep_topmost(hwnd):
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)


def work_area():
    r = wintypes.RECT()
    user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0)  # SPI_GETWORKAREA
    return r.left, r.top, r.right, r.bottom


def virtual_screen():
    """Bounding box of ALL monitors (so a window saved on a 2nd screen is restored there)."""
    gm = user32.GetSystemMetrics
    x, y, w, h = gm(76), gm(77), gm(78), gm(79)
    return x, y, x + w, y + h


def window_class(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def send_ctrl_v():
    VK_CONTROL, VK_V, KEYUP = 0x11, 0x56, 0x0002
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    user32.keybd_event(VK_V, 0, 0, 0)
    user32.keybd_event(VK_V, 0, KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, KEYUP, 0)


# ---------------------------------------------------------------- Theme (day / night)
PALETTES = {
    "dark": dict(BG="#17181c", HEADER="#1f2127", CARD="#25272e", CARD_HOVER="#30333c",
                 FG="#e9eaee", MUTED="#8a8f9c", ACCENT="#4f8cff", DANGER="#ff6b6b", OK="#3ddc97"),
    "light": dict(BG="#e9edf5", HEADER="#f8fafd", CARD="#ffffff", CARD_HOVER="#e3eaf8",
                  FG="#1b2130", MUTED="#677086", ACCENT="#2f6df0", DANGER="#d93a3a", OK="#14a05f"),
}
WHITE = "#fefefe"  # text on accent-coloured buttons


def set_theme(name):
    globals().update(PALETTES[name])


set_theme("dark")

W, H, H_COLLAPSED, MARGIN = 380, 560, 46, 12
MIN_W, MIN_H = 300, 260
EDGE, CORNER = 6, 12          # resize grab zones (pixels)
MAX_ITEMS, MAX_CHARS, MAX_NAME = 200, 50000, 60

VERSION = "1.1.2"  # release.py keeps this in sync with the website
# Set once after you host the website, e.g. "https://yourname.github.io/clipdock/version.json"
UPDATE_URL = ""

DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "ClipDock")
DATA_FILE = os.path.join(DATA_DIR, "history.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")


def clamp(v, lo, hi):
    return max(lo, min(v, hi))


class Tooltip:
    """Small hover hint. Never takes focus, flips above the widget near the screen bottom."""

    def __init__(self, root, widget, text, delay=450):
        self.root, self.widget, self.text, self.delay = root, widget, text, delay
        self.tip, self.job = None, None
        widget.bind("<Enter>", self.schedule, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<Button-1>", self.hide, add="+")
        widget.bind("<Destroy>", self.hide, add="+")

    def schedule(self, _e=None):
        self.hide()
        try:
            self.job = self.widget.after(self.delay, self.show)
        except tk.TclError:
            pass

    def show(self):
        self.job = None
        try:
            text = self.text() if callable(self.text) else self.text
            tip = tk.Toplevel(self.root)
            tip.overrideredirect(True)
            tip.attributes("-topmost", True)
            tk.Label(tip, text=text, bg="#0d0e12", fg="#eceef4", font=("Segoe UI", 9), padx=10, pady=6,
                     justify="left", bd=1, relief="solid", highlightthickness=0).pack()
            tip.update_idletasks()
            w, h = tip.winfo_reqwidth(), tip.winfo_reqheight()
            left, _top, right, bottom = work_area()
            x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2 - w // 2
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
            if y + h > bottom:
                y = self.widget.winfo_rooty() - h - 8
            x = max(left + 4, min(x, right - w - 4))
            tip.geometry(f"+{x}+{y}")
            set_noactivate(user32.GetAncestor(tip.winfo_id(), 2) or tip.winfo_id(), True)
            self.tip = tip
        except tk.TclError:
            pass

    def hide(self, _e=None):
        if self.job:
            try:
                self.widget.after_cancel(self.job)
            except tk.TclError:
                pass
            self.job = None
        if self.tip:
            try:
                self.tip.destroy()
            except tk.TclError:
                pass
            self.tip = None


class ClipDock:
    def __init__(self):
        self.settings = self.load_settings()
        self.theme = self.settings.get("theme") if self.settings.get("theme") in PALETTES else "dark"
        set_theme(self.theme)

        self.items = self.load()
        self.tab = "history"
        self.paused = False
        self.collapsed = False
        self.topmost = True
        self.focus_active = False      # True only while we deliberately hold keyboard focus (search / rename)
        self.rename_item = None
        self.target = None
        self.last_seq = user32.GetClipboardSequenceNumber()
        self.skip_text, self.skip_until = None, 0.0
        self._press = None             # pending click / window-drag state
        self.resize = None             # active edge-resize state
        self._cursor = ""
        self.wrap_labels = []
        self._upd = None               # result handed over from the update-check thread
        self.update_ready = None       # newer version string, once found

        self.root = tk.Tk()
        self.root.title("ClipDock")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=BG)
        self.f_body = tkfont.Font(family="Segoe UI", size=10)
        self.f_name = tkfont.Font(family="Segoe UI Semibold", size=10)
        self.f_small = tkfont.Font(family="Segoe UI", size=8)
        self.f_title = tkfont.Font(family="Segoe UI Semibold", size=11)
        self.f_icon = tkfont.Font(family="Segoe UI Symbol", size=11)

        # restore saved size / position (clamped so the window is always reachable)
        wl, wt, wr, wb = work_area()
        vl, vt, vr, vb = virtual_screen()
        self.w = clamp(self.num("w", W), MIN_W, max(MIN_W, wr - wl))
        self.h = clamp(self.num("h", H), MIN_H, max(MIN_H, wb - wt))
        x = self.settings.get("x")
        y = self.settings.get("y")
        if not isinstance(x, int) or not isinstance(y, int):
            x, y = wr - self.w - MARGIN, wb - self.h - MARGIN
        x = clamp(x, vl, max(vl, vr - self.w))
        y = clamp(y, vt, max(vt, vb - self.h))
        self.root.geometry(f"{self.w}x{self.h}+{x}+{y}")

        self.build_ui()
        self.root.update()
        self.hwnd = user32.GetAncestor(self.root.winfo_id(), 2) or self.root.winfo_id()
        set_noactivate(self.hwnd, True)

        # edge / corner resizing (works anywhere on the window border)
        self.root.bind_all("<Motion>", self.on_motion, add="+")
        self.root.bind_all("<ButtonPress-1>", self.on_press_all, add="+")
        self.root.bind_all("<B1-Motion>", self.on_drag_all, add="+")
        self.root.bind_all("<ButtonRelease-1>", self.on_release_all, add="+")

        self.render()
        self.root.after(250, self.tick)
        if UPDATE_URL:
            self.root.after(5000, lambda: self.check_update(silent=True))

    def num(self, key, default):
        try:
            return int(self.settings.get(key, default))
        except (TypeError, ValueError):
            return default

    # ------------------------------------------------------------ persistence
    def load(self):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [i for i in data if isinstance(i, dict) and i.get("t")]
        except Exception:
            return []

    def save(self):
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(self.items, f, ensure_ascii=False)
        except Exception:
            pass

    def load_settings(self):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def save_settings(self):
        try:
            x, y = self.root.winfo_x(), self.root.winfo_y()
            if self.collapsed:  # remember the expanded position (window is bottom-anchored)
                y = y + self.root.winfo_height() - self.h
            data = {"theme": self.theme, "w": self.w, "h": self.h, "x": x, "y": y}
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception:
            pass

    # ------------------------------------------------------------ UI
    def build_ui(self):
        hdr = tk.Frame(self.root, bg=HEADER, height=H_COLLAPSED)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        self.hdr = hdr
        title = tk.Label(hdr, text="  \u2398 ClipDock", bg=HEADER, fg=FG, font=self.f_title)
        title.pack(side="left")
        self.count_lbl = tk.Label(hdr, text="", bg=HEADER, fg=MUTED, font=self.f_small)
        self.count_lbl.pack(side="left", padx=6)
        for w in (hdr, title, self.count_lbl):
            self.bind_drag(w)

        self.btn_close = self.icon_btn(hdr, "\u2715", self.root.destroy)
        self.btn_close.pack_configure(padx=(0, 6))
        self.btn_collapse = self.icon_btn(hdr, "\u2014", self.toggle_collapse)
        self.btn_pin = self.icon_btn(hdr, "\u25C9", self.toggle_topmost)
        self.btn_theme = self.icon_btn(hdr, "\u2600" if self.theme == "dark" else "\u263E", self.toggle_theme)
        self.btn_pause = self.icon_btn(hdr, "\u25CF", self.toggle_pause)
        self.btn_update = self.icon_btn(hdr, "\u21BB", self.check_update)
        self.btn_pause.config(fg=OK)
        self.btn_pin.config(fg=ACCENT)
        Tooltip(self.root, self.btn_close, "Close ClipDock")
        Tooltip(self.root, self.btn_collapse,
                lambda: "Expand the window" if self.collapsed else "Collapse to a slim bar")
        Tooltip(self.root, self.btn_pin,
                lambda: "Always on top: ON\nClick to let other windows cover it" if self.topmost
                else "Always on top: OFF\nClick to keep it above other windows")
        Tooltip(self.root, self.btn_theme,
                lambda: "Night mode is on\nClick for day (light) mode" if self.theme == "dark"
                else "Day mode is on\nClick for night (dark) mode")
        Tooltip(self.root, self.btn_pause,
                lambda: "Capture paused\nClick to resume saving copied text" if self.paused
                else "Capturing your clipboard\nClick to pause saving")
        Tooltip(self.root, self.btn_update,
                lambda: f"Version {self.update_ready} is available\nClick to open the download page" if self.update_ready
                else f"ClipDock v{VERSION}\nClick to check for updates")
        Tooltip(self.root, title, f"ClipDock v{VERSION}\nDrag to move \u00B7 drag any edge to resize")
        Tooltip(self.root, self.count_lbl, "Total items saved in your history")

        self.body = tk.Frame(self.root, bg=BG)
        self.body.pack(fill="both", expand=True)
        self.bind_drag(self.body)

        tabs = tk.Frame(self.body, bg=BG)
        tabs.pack(fill="x", padx=10, pady=(10, 4))
        self.bind_drag(tabs)
        self.tab_btns = {}
        for key, label in (("history", "History"), ("pinned", "Pinned")):
            b = tk.Label(tabs, text=label, font=self.f_body, padx=14, pady=4, cursor="hand2")
            b.pack(side="left", padx=(0, 6))
            b.bind("<Button-1>", lambda e, k=key: self.set_tab(k))
            Tooltip(self.root, b, "Everything you copied, newest first" if key == "history"
                    else "Only the items you starred \u2014 they are never auto-deleted")
            self.tab_btns[key] = b

        self.sbox = tk.Frame(self.body, bg=CARD, padx=8, pady=5)
        self.sbox.pack(fill="x", padx=10, pady=(2, 6))
        self.bind_drag(self.sbox)
        sicon = tk.Label(self.sbox, text="\u2315", bg=CARD, fg=MUTED, font=self.f_icon)
        sicon.pack(side="left")
        self.bind_drag(sicon)
        self.query = tk.StringVar()
        self.query.trace_add("write", lambda *a: self.render())
        self.search = tk.Entry(self.sbox, textvariable=self.query, bg=CARD, fg=FG, bd=0,
                               insertbackground=FG, font=self.f_body, relief="flat")
        self.search.pack(side="left", fill="x", expand=True, padx=6)
        self.search.bind("<Button-1>", lambda e: self.focus_entry(self.search))
        self.search.bind("<Escape>", lambda e: self.release_focus())
        self.search.bind("<FocusOut>", lambda e: self.release_focus())
        Tooltip(self.root, self.search,
                "Search what you copied \u2014 or the names you gave items\nClick to type, press Esc to go back to your app")

        wrap = tk.Frame(self.body, bg=BG)
        wrap.pack(fill="both", expand=True)
        self.bind_drag(wrap)
        self.canvas = tk.Canvas(wrap, bg=BG, highlightthickness=0, bd=0)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self.win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.pack(fill="both", expand=True)
        self.bind_drag(self.canvas)
        self.bind_drag(self.inner)
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self.on_canvas_resize)
        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self.on_wheel))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

        foot = tk.Frame(self.body, bg=HEADER, height=34)
        foot.pack(fill="x", side="bottom")
        foot.pack_propagate(False)
        self.bind_drag(foot)
        hint = tk.Label(foot, text="Click to paste \u00B7 drag edges to resize", bg=HEADER, fg=MUTED,
                        font=self.f_small)
        hint.pack(side="left", padx=10)
        self.bind_drag(hint)
        clear = tk.Label(foot, text="Clear history", bg=HEADER, fg=DANGER, font=self.f_small, cursor="hand2")
        clear.pack(side="right", padx=10)
        clear.bind("<Button-1>", lambda e: self.clear_history())
        Tooltip(self.root, clear, "Delete all history\n(pinned items are kept)")

    def icon_btn(self, parent, text, cmd):
        b = tk.Label(parent, text=text, bg=HEADER, fg=MUTED, font=self.f_icon, cursor="hand2", padx=7)
        b.pack(side="right")
        b.bind("<Button-1>", lambda e: cmd())
        return b

    # ------------------------------------------------------------ moving: drag from anywhere
    def bind_drag(self, widget, click=None):
        """Dragging this widget moves the window. A press-and-release without moving runs `click`."""
        widget.bind("<ButtonPress-1>", lambda e: self.press_begin(e, click), add="+")
        widget.bind("<B1-Motion>", self.press_move, add="+")
        widget.bind("<ButtonRelease-1>", self.press_end, add="+")

    def press_begin(self, e, click):
        if self.focus_active:
            self.release_focus()
        self._press = {"x": e.x_root, "y": e.y_root, "wx": self.root.winfo_x(),
                       "wy": self.root.winfo_y(), "moved": False, "click": click}

    def press_move(self, e):
        p = self._press
        if not p or self.resize:
            return
        if not p["moved"] and abs(e.x_root - p["x"]) + abs(e.y_root - p["y"]) < 6:
            return
        p["moved"] = True
        self.root.geometry(f"+{p['wx'] + e.x_root - p['x']}+{p['wy'] + e.y_root - p['y']}")

    def press_end(self, e):
        p, self._press = self._press, None
        if not p:
            return
        if p["moved"]:
            self.save_settings()
        elif p["click"]:
            p["click"]()

    # ------------------------------------------------------------ resizing: any edge or corner
    def edge_zone(self, e):
        if self.collapsed:
            return None
        x = e.x_root - self.root.winfo_rootx()
        y = e.y_root - self.root.winfo_rooty()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        if x < 0 or y < 0 or x >= w or y >= h:
            return None
        nl, nr, nt, nb = x < CORNER, x >= w - CORNER, y < CORNER, y >= h - CORNER
        if (nl or nr) and (nt or nb):                      # corner
            return (nl, nr, nt, nb)
        return (x < EDGE, x >= w - EDGE, y < EDGE, y >= h - EDGE) if (
            x < EDGE or x >= w - EDGE or y < EDGE or y >= h - EDGE) else None

    @staticmethod
    def zone_cursor(z):
        if not z:
            return ""
        l, r, t, b = z
        if (l and t) or (r and b):
            return "size_nw_se"
        if (r and t) or (l and b):
            return "size_ne_sw"
        return "size_we" if (l or r) else "size_ns"

    def on_motion(self, e):
        if self.resize:
            return
        cur = self.zone_cursor(self.edge_zone(e))
        if cur != self._cursor:
            self._cursor = cur
            try:
                self.root.config(cursor=cur)
            except tk.TclError:
                pass

    def on_press_all(self, e):
        z = self.edge_zone(e)
        if z:
            self._press = None  # cancel any pending click / window drag
            self.resize = {"zone": z, "x0": e.x_root, "y0": e.y_root,
                           "geo": (self.root.winfo_x(), self.root.winfo_y(),
                                   self.root.winfo_width(), self.root.winfo_height())}

    def on_drag_all(self, e):
        r = self.resize
        if not r:
            return
        l, rt, t, b = r["zone"]
        x, y, w, h = r["geo"]
        dx, dy = e.x_root - r["x0"], e.y_root - r["y0"]
        wl, wt, wr, wb = work_area()
        maxw, maxh = max(MIN_W, wr - wl), max(MIN_H, wb - wt)
        nw, nh = w, h
        if rt:
            nw = w + dx
        if l:
            nw = w - dx
        if b:
            nh = h + dy
        if t:
            nh = h - dy
        nw, nh = clamp(nw, MIN_W, maxw), clamp(nh, MIN_H, maxh)
        nx = x + (w - nw) if l else x
        ny = y + (h - nh) if t else y
        self.root.geometry(f"{nw}x{nh}+{nx}+{ny}")

    def on_release_all(self, e):
        if self.resize:
            self.resize = None
            self.root.update_idletasks()
            self.w, self.h = self.root.winfo_width(), self.root.winfo_height()
            self.save_settings()

    def on_canvas_resize(self, e):
        self.canvas.itemconfigure(self.win, width=e.width)
        wrap = max(120, e.width - 140)
        for lbl in self.wrap_labels:
            try:
                lbl.config(wraplength=wrap)
            except tk.TclError:
                pass

    # ------------------------------------------------------------ window behaviour
    def toggle_collapse(self):
        self.collapsed = not self.collapsed
        bottom = self.root.winfo_y() + self.root.winfo_height()
        h = H_COLLAPSED if self.collapsed else self.h
        if self.collapsed:
            self.body.pack_forget()
        else:
            self.body.pack(fill="both", expand=True)
        self.root.geometry(f"{self.w}x{h}+{self.root.winfo_x()}+{bottom - h}")
        self.root.config(cursor="")
        self._cursor = ""

    def toggle_topmost(self):
        self.topmost = not self.topmost
        self.root.attributes("-topmost", self.topmost)
        self.btn_pin.config(fg=ACCENT if self.topmost else MUTED)

    def toggle_pause(self):
        self.paused = not self.paused
        self.btn_pause.config(fg=DANGER if self.paused else OK)
        self.last_seq = user32.GetClipboardSequenceNumber()

    def toggle_theme(self):
        old = PALETTES[self.theme]
        self.theme = "light" if self.theme == "dark" else "dark"
        set_theme(self.theme)
        self.retheme(old, PALETTES[self.theme])
        self.btn_theme.config(text="\u2600" if self.theme == "dark" else "\u263E")
        self.update_count()
        self.render(keep_scroll=True)
        self.save_settings()

    def retheme(self, old, new):
        """Recolour every existing widget by mapping each old palette colour to its new one."""
        mapping = {old[k].lower(): new[k] for k in old}

        def walk(w):
            for opt in ("bg", "fg", "insertbackground"):
                try:
                    cur = str(w.cget(opt)).lower()
                except tk.TclError:
                    continue
                if cur in mapping:
                    try:
                        w.configure(**{opt: mapping[cur]})
                    except tk.TclError:
                        pass
            for child in w.winfo_children():
                walk(child)

        walk(self.root)

    def set_tab(self, key):
        self.tab = key
        self.render()

    def on_wheel(self, e):
        self.canvas.yview_scroll(int(-e.delta / 120) * 2, "units")

    # ------------------------------------------------------------ keyboard focus (only for search / rename)
    def focus_entry(self, entry):
        try:
            if not entry.winfo_exists():
                return
        except tk.TclError:
            return
        self.focus_active = True
        set_noactivate(self.hwnd, False)
        user32.SetForegroundWindow(self.hwnd)
        entry.focus_force()
        if entry is not self.search:
            entry.select_range(0, "end")
            entry.icursor("end")

    def release_focus(self):
        if not self.focus_active:
            return
        self.focus_active = False
        set_noactivate(self.hwnd, True)
        self.root.focus_set()
        if self.target:
            user32.SetForegroundWindow(self.target)

    # ------------------------------------------------------------ clipboard capture
    def tick(self):
        try:
            fg = user32.GetForegroundWindow()
            if fg and fg != self.hwnd and not self.focus_active and window_class(fg) not in IGNORED_TARGET_CLASSES:
                self.target = fg
            if self.topmost:
                keep_topmost(self.hwnd)
            if self._upd:
                self.handle_update_result()
            seq = user32.GetClipboardSequenceNumber()
            if seq != self.last_seq:
                self.last_seq = seq
                if not self.paused:
                    self.capture()
        finally:
            self.root.after(250, self.tick)

    def capture(self):
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            return  # non-text clipboard content (image, files...)
        if not text or not text.strip():
            return
        if text == self.skip_text and time.time() < self.skip_until:
            return
        text = text[:MAX_CHARS]
        pinned, name = False, ""
        for it in self.items:
            if it["t"] == text:
                pinned, name = it.get("pin", False), it.get("name", "")
                self.items.remove(it)
                break
        entry = {"t": text, "ts": time.time(), "pin": pinned}
        if name:
            entry["name"] = name
        self.items.insert(0, entry)
        unpinned = [i for i in self.items if not i.get("pin")]
        for extra in unpinned[MAX_ITEMS:]:
            self.items.remove(extra)
        self.save()
        if self.rename_item is None:   # don't wipe a name the user is typing
            self.render()
        else:
            self.update_count()

    # ------------------------------------------------------------ updates
    @staticmethod
    def ver_tuple(v):
        try:
            return tuple(int(p) for p in str(v).strip().lstrip("v").split("."))
        except ValueError:
            return (0,)

    def update_count(self):
        if self.update_ready:
            self.count_lbl.config(text=f"Update v{self.update_ready} \u2197", fg=ACCENT)
        else:
            self.count_lbl.config(text=f"v{VERSION} \u00B7 {len(self.items)} items", fg=MUTED)

    def flash_status(self, msg):
        self.count_lbl.config(text=msg, fg=MUTED)
        self.root.after(4000, self.update_count)

    def check_update(self, silent=False):
        if self.update_ready:  # already know there is a newer one -> open the website
            webbrowser.open(UPDATE_URL.rsplit("/", 1)[0] + "/")
            return
        if not UPDATE_URL:
            if not silent:
                self.flash_status("Update link not set")
            return
        if not silent:
            self.flash_status("Checking\u2026")

        def work():
            try:
                req = urllib.request.Request(UPDATE_URL, headers={"User-Agent": f"ClipDock/{VERSION}"})
                with urllib.request.urlopen(req, timeout=8) as r:
                    self._upd = ("ok", json.loads(r.read().decode("utf-8")), silent)
            except Exception:
                self._upd = ("err", None, silent)

        threading.Thread(target=work, daemon=True).start()

    def handle_update_result(self):
        status, info, silent = self._upd
        self._upd = None
        if status != "ok":
            if not silent:
                self.flash_status("Couldn't reach server")
            return
        latest = str(info.get("latest", ""))
        if self.ver_tuple(latest) > self.ver_tuple(VERSION):
            self.update_ready = latest
            self.update_count()
        elif not silent:
            self.flash_status("You're up to date \u2713")

    # ------------------------------------------------------------ actions
    def paste(self, it):
        if self.focus_active:
            self.release_focus()
        self.skip_text, self.skip_until = it["t"], time.time() + 1.5
        self.root.clipboard_clear()
        self.root.clipboard_append(it["t"])
        self.root.update_idletasks()
        if self.target and user32.GetForegroundWindow() != self.target:
            user32.SetForegroundWindow(self.target)
        self.root.after(90, send_ctrl_v)

    def toggle_pin(self, it):
        it["pin"] = not it.get("pin", False)
        self.save()
        self.render(keep_scroll=True)

    def delete(self, it):
        if it is self.rename_item:
            self.rename_item = None
            self.release_focus()
        if it in self.items:
            self.items.remove(it)
        self.save()
        self.render(keep_scroll=True)

    def clear_history(self):
        self.rename_item = None
        self.release_focus()
        self.items = [i for i in self.items if i.get("pin")]
        self.save()
        self.render()

    # ---- naming items
    def start_rename(self, it):
        self.rename_item = it
        self.render(keep_scroll=True)

    def commit_rename(self, it, entry):
        if self.rename_item is not it:
            return
        try:
            name = entry.get().strip()[:MAX_NAME]
        except tk.TclError:
            name = it.get("name", "")
        self.rename_item = None
        if name:
            it["name"] = name
        else:
            it.pop("name", None)
        self.save()
        self.release_focus()
        self.render(keep_scroll=True)

    def cancel_rename(self):
        self.rename_item = None
        self.release_focus()
        self.render(keep_scroll=True)

    # ------------------------------------------------------------ rendering
    @staticmethod
    def preview(text):
        lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
        out = "\n".join(lines[:3])
        if len(out) > 180:
            out = out[:180]
        return out + (" \u2026" if len(lines) > 3 or len(text.strip()) > len(out) else "")

    @staticmethod
    def ago(ts):
        d = int(time.time() - ts)
        if d < 60:
            return "just now"
        if d < 3600:
            return f"{d // 60} min ago"
        if d < 86400:
            return f"{d // 3600} h ago"
        return time.strftime("%d %b", time.localtime(ts))

    def inside(self, widget):
        cur = self.root.winfo_containing(*self.root.winfo_pointerxy())
        while cur is not None:
            if cur is widget:
                return True
            cur = cur.master
        return False

    def render(self, keep_scroll=False):
        top = self.canvas.yview()[0] if keep_scroll else 0.0
        for k, b in self.tab_btns.items():
            on = k == self.tab
            b.config(bg=ACCENT if on else CARD, fg=WHITE if on else MUTED)
        n_pin = sum(1 for i in self.items if i.get("pin"))
        self.tab_btns["pinned"].config(text=f"Pinned ({n_pin})")
        self.update_count()

        for w in self.inner.winfo_children():
            w.destroy()
        self.wrap_labels = []
        q = self.query.get().strip().lower()

        def match(i):
            return not q or q in i["t"].lower() or q in i.get("name", "").lower()

        shown = [i for i in self.items if (self.tab == "history" or i.get("pin")) and match(i)]
        if not shown:
            msg = "Nothing pinned yet.\nTap \u2606 on an item to keep it here." if self.tab == "pinned" and not q \
                else ("No matches." if q else "Copy something (Ctrl+C) and it will appear here.")
            lbl = tk.Label(self.inner, text=msg, bg=BG, fg=MUTED, font=self.f_body, justify="center", pady=40)
            lbl.pack(fill="x")
            self.bind_drag(lbl)
        for it in shown[:120]:
            self.make_card(it)
        self.root.update_idletasks()
        self.canvas.yview_moveto(top)

    def make_card(self, it):
        renaming = it is self.rename_item
        pinned = it.get("pin", False)
        name = it.get("name", "")
        cw = self.canvas.winfo_width()
        wrap = max(120, (cw if cw > 50 else self.w) - 140)

        card = tk.Frame(self.inner, bg=CARD, cursor="" if renaming else "hand2", padx=10, pady=8)
        card.pack(fill="x", padx=10, pady=3)
        card.columnconfigure(0, weight=1)
        parts, clickable = [card], [card]
        row = 0

        if renaming:
            ent = tk.Entry(card, bg=BG, fg=FG, insertbackground=FG, bd=0, relief="flat", font=self.f_body)
            ent.insert(0, name)
            ent.grid(row=0, column=0, sticky="we", pady=(0, 4), padx=(0, 6), ipady=4)
            ent.bind("<Return>", lambda e, i=it, w=ent: self.commit_rename(i, w))
            ent.bind("<Escape>", lambda e: self.cancel_rename())
            ent.bind("<FocusOut>", lambda e, i=it, w=ent: self.commit_rename(i, w))
            self.root.after(40, lambda w=ent: self.focus_entry(w))
            row = 1
        elif name:
            nl = tk.Label(card, text=name, bg=CARD, fg=ACCENT, font=self.f_name, anchor="w",
                          justify="left", wraplength=wrap)
            nl.grid(row=0, column=0, sticky="we")
            self.wrap_labels.append(nl)
            parts.append(nl)
            clickable.append(nl)
            row = 1

        txt = tk.Label(card, text=self.preview(it["t"]), bg=CARD, fg=FG, font=self.f_body,
                       justify="left", anchor="w", wraplength=wrap)
        txt.grid(row=row, column=0, sticky="we")
        self.wrap_labels.append(txt)
        meta = tk.Label(card, text=f"{self.ago(it['ts'])}  \u00B7  {len(it['t'])} chars", bg=CARD,
                        fg=MUTED, font=self.f_small, anchor="w")
        meta.grid(row=row + 1, column=0, sticky="w", pady=(2, 0))
        parts += [txt, meta]
        clickable += [txt, meta]

        edit = tk.Label(card, text="\u270E", bg=CARD, fg=ACCENT if name else MUTED, font=self.f_icon,
                        cursor="hand2", padx=3)
        edit.grid(row=0, column=1, sticky="ne")
        pin = tk.Label(card, text="\u2605" if pinned else "\u2606", bg=CARD, font=self.f_icon,
                       fg=ACCENT if pinned else MUTED, cursor="hand2", padx=3)
        pin.grid(row=0, column=2, sticky="ne")
        dele = tk.Label(card, text="\u2715", bg=CARD, fg=MUTED, font=self.f_small, cursor="hand2", padx=3)
        dele.grid(row=0, column=3, sticky="ne")
        parts += [edit, pin, dele]

        edit.bind("<Button-1>", lambda e, i=it: self.start_rename(i))
        pin.bind("<Button-1>", lambda e, i=it: self.toggle_pin(i))
        dele.bind("<Button-1>", lambda e, i=it: self.delete(i))
        dele.bind("<Enter>", lambda e, w=dele: w.config(fg=DANGER))
        dele.bind("<Leave>", lambda e, w=dele: w.config(fg=MUTED))
        Tooltip(self.root, edit, "Rename this item" if name else "Give this item a name\n(then search for it by name)")
        Tooltip(self.root, pin, "Unpin this item" if pinned else "Pin \u2014 keep this item permanently")
        Tooltip(self.root, dele, "Delete this item")

        click = None if renaming else (lambda i=it: self.paste(i))
        for w in clickable:
            self.bind_drag(w, click)
            if not renaming:
                Tooltip(self.root, w, "Click to paste at your cursor\nDrag to move the window", delay=700)

        def hover(on):
            for w in parts:
                w.config(bg=CARD_HOVER if on else CARD)

        for w in parts:
            w.bind("<Enter>", lambda e: hover(True), add="+")
            w.bind("<Leave>", lambda e, c=card: hover(self.inside(c)), add="+")

    def run(self):
        self.root.mainloop()


def already_running():
    """Named mutex so double-clicking the app twice doesn't open two docks."""
    global _mutex
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "ClipDock_SingleInstance")
    return ctypes.windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


if __name__ == "__main__":
    if already_running():
        ctypes.windll.user32.MessageBoxW(None, "ClipDock is already running.", "ClipDock", 0x40)
        sys.exit(0)
    ClipDock().run()
