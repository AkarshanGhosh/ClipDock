"""
ClipDock - clipboard history that docks above the Windows taskbar.

Daily use
  * Global hotkey (default Ctrl+Alt+V) shows/hides ClipDock from any app.
  * Keyboard mode: arrows + Enter, number keys 1-9, type to search, Esc to close.
  * Right-click (or the dots button) an item: paste as UPPER / lower / Title / one line ..., open links,
    pretty-print JSON, rename, pin, save as snippet.
  * Paste stack: copy several things, then paste them back in order (hotkey Ctrl+Alt+N).
  * Smart badges for links, e-mails, JSON and colours. Images and copied files are kept too.
  * Snippets with variables like {date} and {clipboard}, organised in folders.
  * Every item shows the app it came from; filter the list by app.
App
  * Settings panel, tray icon, start with Windows, day/night + accent colour, opacity, font size.
  * Export / import / OneDrive-style folder sync.
  * Send feedback (pre-filled GitHub issue), "What's new" after updates, one-click auto-update.

Run from source:  pythonw clipdock.pyw   (Python 3.8+ on Windows, no extra packages)
Install as an app: double-click install_shortcut.bat once.
"""
import ctypes
import hashlib
import json
import os
import platform
import queue
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import urllib.parse
import urllib.request
import webbrowser
import zipfile
import zlib
from tkinter import filedialog
from tkinter import font as tkfont

if sys.platform != "win32":
    sys.exit("ClipDock runs on Windows only.")

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

import cd_core as core  # noqa: E402
import cd_win as win  # noqa: E402

# ---------------------------------------------------------------- release info (stamped by release.py)
VERSION = "1.2.0"
UPDATE_URL = "https://raw.githubusercontent.com/AkarshanGhosh/ClipDock/main/version.json"
SITE_URL = "https://github.com/AkarshanGhosh/ClipDock"
REPO = "AkarshanGhosh/ClipDock"
# <<WHATS_NEW>>
WHATS_NEW = [
    "Global hotkey (Ctrl+Alt+V) shows or hides ClipDock from any app",
    "Keyboard mode: arrows + Enter, number keys 1-9, type to search, Esc to close",
    "Right-click menu: paste as UPPER, lower, Title Case, one line; open links; pretty-print JSON",
    "Paste stack: copy several things, then paste them back in order (Ctrl+Alt+N)",
    "Smart badges for links, e-mails, JSON and colours; images and copied files are kept with thumbnails",
    "Snippets with variables like {date} and {clipboard}, organised in folders",
    "See which app each item came from and filter by app",
    "Settings panel, tray icon, start with Windows, accent colour, opacity and text size",
    "Export, import and OneDrive-style folder sync",
    "Send feedback button, What's new after updates, one-click auto-update",
]
# <<END>>

# ---------------------------------------------------------------- theme (day / night + accent)
PALETTES = {
    "dark": dict(BG="#17181c", HEADER="#1f2127", CARD="#25272e", CARD_HOVER="#30333c",
                 FG="#e9eaee", MUTED="#8a8f9c", ACCENT="#4f8cff", DANGER="#ff6b6b", OK="#3ddc97"),
    "light": dict(BG="#e9edf5", HEADER="#f8fafd", CARD="#ffffff", CARD_HOVER="#e3eaf8",
                  FG="#1b2130", MUTED="#677086", ACCENT="#2f6df0", DANGER="#d93a3a", OK="#14a05f"),
}
WHITE = "#fefefe"
ACCENT_CHOICES = ["#4f8cff", "#8b5cf6", "#14b8a6", "#22c55e", "#f59e0b", "#ef4444", "#ec4899"]


def palette(name, accent=""):
    p = dict(PALETTES[name])
    if accent:
        p["ACCENT"] = accent
    return p


def set_theme(name, accent=""):
    globals().update(palette(name, accent))


set_theme("dark")

W, H, H_COLLAPSED, MARGIN = 400, 580, 46, 12
MIN_W, MIN_H = 340, 280
EDGE, CORNER = 6, 12
MAX_CHARS, MAX_NAME, MAX_IMAGES = 50000, 60, 40

DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "ClipDock")
DATA_FILE = os.path.join(DATA_DIR, "history.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
SNIPPETS_FILE = os.path.join(DATA_DIR, "snippets.json")
IMG_DIR = os.path.join(DATA_DIR, "images")
LOG_FILE = os.path.join(DATA_DIR, "clipdock.log")
SYNC_NAME = "ClipDock-sync.json"
APP_DIR = os.path.dirname(os.path.abspath(__file__))

DEFAULTS = dict(theme="dark", w=W, h=H, x=None, y=None,
                hotkey="ctrl+alt+v", stack_hotkey="ctrl+alt+n",
                history_limit=200, opacity=100, font_size=10, accent="",
                always_on_top=True, close_to_tray=True, hide_after_paste=True,
                stack_order="fifo", sync_dir="", last_seen="")
TABS = (("history", "History"), ("pinned", "Pinned"), ("snippets", "Snippets"), ("stack", "Stack"))


def log(msg):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 200_000:
            os.remove(LOG_FILE)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + str(msg) + "\n")
    except Exception:
        pass


def clamp(v, lo, hi):
    return max(lo, min(v, hi))


def write_json_atomic(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


# ---------------------------------------------------------------- small UI helpers
class Tooltip:
    """Hover hint. Never takes focus, flips above the widget near the screen bottom."""

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
            left, _top, right, bottom = win.work_area()
            x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2 - w // 2
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
            if y + h > bottom:
                y = self.widget.winfo_rooty() - h - 8
            x = max(left + 4, min(x, right - w - 4))
            tip.geometry(f"+{x}+{y}")
            win.set_noactivate(win.user32.GetAncestor(tip.winfo_id(), 2) or tip.winfo_id(), True)
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


class PopupMenu:
    """A tiny context menu that never steals focus (rows = (label, callback) or None for a separator)."""

    def __init__(self, app, rows, x, y):
        self.app = app
        self.top = tk.Toplevel(app.root)
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        outer = tk.Frame(self.top, bg=CARD_HOVER, padx=1, pady=1)
        outer.pack()
        inner = tk.Frame(outer, bg=CARD, pady=4)
        inner.pack()
        for row in rows:
            if row is None:
                tk.Frame(inner, bg=CARD_HOVER, height=1).pack(fill="x", padx=8, pady=3)
                continue
            text, cb = row
            lbl = tk.Label(inner, text=text, anchor="w", bg=CARD, fg=FG, font=app.f_body, padx=14, pady=4,
                           cursor="hand2")
            lbl.pack(fill="x")
            lbl.bind("<Enter>", lambda e, w=lbl: w.config(bg=CARD_HOVER))
            lbl.bind("<Leave>", lambda e, w=lbl: w.config(bg=CARD))
            lbl.bind("<Button-1>", lambda e, c=cb: self.choose(c))
        self.top.update_idletasks()
        w, h = self.top.winfo_reqwidth(), self.top.winfo_reqheight()
        left, top, right, bottom = win.work_area()
        x = clamp(x, left + 4, right - w - 4)
        y = y if y + h <= bottom - 4 else max(top + 4, y - h)
        self.top.geometry(f"+{x}+{y}")
        win.set_noactivate(win.user32.GetAncestor(self.top.winfo_id(), 2) or self.top.winfo_id(), True)
        self.job = app.root.after(12000, self.close)

    def choose(self, cb):
        self.close()
        self.app.root.after(15, cb)

    def contains(self, widget):
        return str(widget).startswith(str(self.top))

    def close(self):
        try:
            self.app.root.after_cancel(self.job)
        except Exception:
            pass
        try:
            self.top.destroy()
        except tk.TclError:
            pass
        if self.app.popup is self:
            self.app.popup = None


class ScrollFrame(tk.Frame):
    """A vertically scrolling frame (used by the settings and info pages)."""

    def __init__(self, parent, app):
        super().__init__(parent, bg=BG)
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0, bd=0)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self.win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.pack(fill="both", expand=True)
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.win, width=e.width))
        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._wheel))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))
        app.bind_drag(self.canvas)
        app.bind_drag(self.inner)

    def _wheel(self, e):
        self.canvas.yview_scroll(int(-e.delta / 120) * 2, "units")


# ================================================================ the application
class ClipDock:
    def __init__(self):
        self.first_run = not os.path.exists(SETTINGS_FILE)
        self.cfg = dict(DEFAULTS)
        self.cfg.update(read_json(SETTINGS_FILE, {}) if isinstance(read_json(SETTINGS_FILE, {}), dict) else {})
        self.sanitize_cfg()
        self.theme = self.cfg["theme"]
        set_theme(self.theme, self.cfg["accent"])

        self.items = self.load_items()
        self.snippets = read_json(SNIPPETS_FILE, [])
        if not isinstance(self.snippets, list):
            self.snippets = []

        # state
        self.tab = "history"
        self.page = "list"
        self.alt_page = None
        self.paused = False
        self.collapsed = False
        self.visible = True
        self.focus_active = False       # True only while we deliberately hold keyboard focus
        self.kb_mode = False            # opened with the hotkey -> arrows / Enter / 1-9 work
        self.opened_by_hotkey = False
        self.recording = None           # hotkey id being recorded in settings
        self.rename_item = None
        self.stack_mode = False
        self.stack = []
        self.src_filter = None
        self.snip_tag = None
        self.shown = []
        self.sel = -1
        self.sel_frame = None
        self.card_frames = []
        self.popup = None
        self.target = None
        self.last_seq = win.clipboard_sequence()
        self.skip_text, self.skip_until = None, 0.0
        self.suppress_until = 0.0
        self._press = None
        self.resize = None
        self._cursor = ""
        self.wrap_labels = []
        self.thumbs = {}
        self._upd = None
        self.update_ready = None
        self.update_info = None
        self._dl = None
        self.sync_mtime = 0.0
        self._sync_job = None
        self._tick_n = 0
        self.quitting = False
        self.events = queue.Queue()
        self.host = None
        self.hotkey_status = {}

        self.root = tk.Tk()
        self.root.title("ClipDock")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", self.cfg["always_on_top"])
        self.root.attributes("-alpha", self.cfg["opacity"] / 100)
        self.root.configure(bg=BG)
        self.f_body = tkfont.Font(family="Segoe UI")
        self.f_name = tkfont.Font(family="Segoe UI Semibold")
        self.f_small = tkfont.Font(family="Segoe UI")
        self.f_title = tkfont.Font(family="Segoe UI Semibold")
        self.f_icon = tkfont.Font(family="Segoe UI Symbol")
        self.apply_fonts()

        wl, wt, wr, wb = win.work_area()
        vl, vt, vr, vb = win.virtual_screen()
        self.w = clamp(int(self.cfg["w"]), MIN_W, max(MIN_W, wr - wl))
        self.h = clamp(int(self.cfg["h"]), MIN_H, max(MIN_H, wb - wt))
        x, y = self.cfg.get("x"), self.cfg.get("y")
        if not isinstance(x, int) or not isinstance(y, int):
            x, y = wr - self.w - MARGIN, wb - self.h - MARGIN
        x, y = clamp(x, vl, max(vl, vr - self.w)), clamp(y, vt, max(vt, vb - self.h))
        self.root.geometry(f"{self.w}x{self.h}+{x}+{y}")

        self.build_ui()
        self.root.update()
        self.hwnd = win.user32.GetAncestor(self.root.winfo_id(), 2) or self.root.winfo_id()
        win.set_noactivate(self.hwnd, True)

        self.root.bind_all("<Motion>", self.on_motion, add="+")
        self.root.bind_all("<ButtonPress-1>", self.on_press_all, add="+")
        self.root.bind_all("<B1-Motion>", self.on_drag_all, add="+")
        self.root.bind_all("<ButtonRelease-1>", self.on_release_all, add="+")
        self.root.bind("<Key>", self.on_key)

        self.start_host()
        self.sync_pull()
        self.render()
        self.root.after(250, self.tick)
        self.root.after(60, self.poll_events)
        self.root.after(900, self.startup_pages)
        self.root.after(6000, lambda: self.check_update(silent=True))

    # ============================================================ config / persistence
    def sanitize_cfg(self):
        c = self.cfg

        def num(key, lo, hi):
            try:
                c[key] = clamp(int(c[key]), lo, hi)
            except (TypeError, ValueError):
                c[key] = DEFAULTS[key]

        num("history_limit", 20, 5000)
        num("opacity", 40, 100)
        num("font_size", 8, 14)
        for key in ("always_on_top", "close_to_tray", "hide_after_paste"):
            c[key] = bool(c.get(key, DEFAULTS[key]))
        if c.get("theme") not in PALETTES:
            c["theme"] = "dark"
        if c.get("stack_order") not in ("fifo", "lifo"):
            c["stack_order"] = "fifo"
        acc = str(c.get("accent") or "")
        c["accent"] = acc if len(acc) == 7 and acc.startswith("#") else ""
        for key in ("hotkey", "stack_hotkey"):
            if not core.parse_hotkey(str(c.get(key, ""))):
                c[key] = DEFAULTS[key]
        c["sync_dir"] = str(c.get("sync_dir") or "")
        c["last_seen"] = str(c.get("last_seen") or "")

    def save_settings(self):
        try:
            x, y = self.root.winfo_x(), self.root.winfo_y()
            if self.collapsed:
                y = y + self.root.winfo_height() - self.h
            self.cfg.update(theme=self.theme, w=self.w, h=self.h, x=x, y=y)
            write_json_atomic(SETTINGS_FILE, self.cfg)
        except Exception as e:
            log(f"save_settings: {e}")

    def load_items(self):
        data = read_json(DATA_FILE, [])
        items = []
        for i in data if isinstance(data, list) else []:
            if not isinstance(i, dict) or not i.get("t"):
                continue
            if i.get("kind") == "image" and not os.path.exists(os.path.join(IMG_DIR, f"{i.get('k')}.dib.z")):
                continue
            items.append(i)
        return items

    def save(self):
        try:
            write_json_atomic(DATA_FILE, self.items)
        except Exception as e:
            log(f"save: {e}")
        self.schedule_sync()

    def save_snippets(self):
        try:
            write_json_atomic(SNIPPETS_FILE, self.snippets)
        except Exception as e:
            log(f"save_snippets: {e}")
        self.schedule_sync()

    def apply_fonts(self):
        fs = self.cfg["font_size"]
        self.f_body.configure(size=fs)
        self.f_name.configure(size=fs)
        self.f_small.configure(size=max(7, fs - 2))
        self.f_title.configure(size=fs + 1)
        self.f_icon.configure(size=fs + 1)

    # ============================================================ UI construction
    def build_ui(self):
        hdr = tk.Frame(self.root, bg=HEADER, height=H_COLLAPSED)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        self.hdr = hdr
        title = tk.Label(hdr, text="  \u2398 ClipDock", bg=HEADER, fg=FG, font=self.f_title)
        title.pack(side="left")
        for w in (hdr, title):
            self.bind_drag(w)

        self.btn_close = self.icon_btn(hdr, "\u2715", self.on_close_button)
        self.btn_close.pack_configure(padx=(0, 6))
        self.btn_collapse = self.icon_btn(hdr, "\u2014", self.toggle_collapse)
        self.btn_settings = self.icon_btn(hdr, "\u2699", self.toggle_settings)
        self.btn_feedback = self.icon_btn(hdr, "\u2709", lambda: self.open_feedback_menu(self.btn_feedback))
        self.btn_theme = self.icon_btn(hdr, "\u2600" if self.theme == "dark" else "\u263E", self.toggle_theme)
        self.btn_pause = self.icon_btn(hdr, "\u25CF", self.toggle_pause)
        self.btn_stack = self.icon_btn(hdr, "\u2263", self.toggle_stack)
        self.btn_update = self.icon_btn(hdr, "\u21BB", self.on_update_button)
        self.btn_pause.config(fg=OK)
        tip = lambda w, t: Tooltip(self.root, w, t)  # noqa: E731
        tip(self.btn_close, lambda: "Hide to the tray icon\n(right-click the tray icon to quit)"
            if self.cfg["close_to_tray"] and self.host and self.host.tray_ok else "Close ClipDock")
        tip(self.btn_collapse, lambda: "Expand the window" if self.collapsed else "Collapse to a slim bar")
        tip(self.btn_settings, "Settings")
        tip(self.btn_feedback, "Send feedback \u2014 report a bug or suggest a feature")
        tip(self.btn_theme, lambda: "Night mode is on\nClick for day (light) mode" if self.theme == "dark"
            else "Day mode is on\nClick for night (dark) mode")
        tip(self.btn_pause, lambda: "Capture paused\nClick to resume saving copies" if self.paused
            else "Capturing your clipboard\nClick to pause saving")
        tip(self.btn_stack, lambda: "Paste stack is ON \u2014 copies queue up\nPaste them in order with "
            + core.pretty_hotkey(self.cfg["stack_hotkey"]) if self.stack_mode
            else "Paste stack: copy several things, then paste them back in order")
        tip(self.btn_update, lambda: f"Version {self.update_ready} is available \u2014 click to install"
            if self.update_ready else f"ClipDock v{VERSION}\nClick to check for updates")
        tip(title, f"ClipDock v{VERSION}\nDrag to move \u00B7 drag any edge to resize\n"
            f"{core.pretty_hotkey(self.cfg['hotkey'])} shows / hides it from any app")

        self.body = tk.Frame(self.root, bg=BG)
        self.body.pack(fill="both", expand=True)
        self.bind_drag(self.body)
        self.list_page = tk.Frame(self.body, bg=BG)
        self.list_page.pack(fill="both", expand=True)
        self.bind_drag(self.list_page)

        tabs = tk.Frame(self.list_page, bg=BG)
        tabs.pack(fill="x", padx=10, pady=(10, 4))
        self.bind_drag(tabs)
        self.tab_btns = {}
        tab_tips = {"history": "Everything you copied, newest first",
                    "pinned": "Items you starred \u2014 never auto-deleted",
                    "snippets": "Reusable text with variables like {date}",
                    "stack": "Items queued for the paste stack, in paste order"}
        for key, label in TABS:
            b = tk.Label(tabs, text=label, font=self.f_body, padx=10, pady=4, cursor="hand2")
            b.pack(side="left", padx=(0, 4))
            b.bind("<Button-1>", lambda e, k=key: self.set_tab(k))
            Tooltip(self.root, b, tab_tips[key])
            self.tab_btns[key] = b

        self.sbox = tk.Frame(self.list_page, bg=CARD, padx=8, pady=5)
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
        self.search.bind("<FocusOut>", lambda e: self.root.after(80, self.maybe_release))
        self.search.bind("<Tab>", lambda e: (self.cycle_tab(), "break")[1])
        Tooltip(self.root, self.search, "Search text, names or the app an item came from\n"
                "Click to type \u00B7 in keyboard mode just start typing")
        self.src_btn = tk.Label(self.sbox, text="All apps \u25BE", bg=CARD, fg=MUTED, font=self.f_small,
                                cursor="hand2", padx=4)
        self.src_btn.pack(side="right")
        self.src_btn.bind("<Button-1>", lambda e: self.open_source_menu())
        Tooltip(self.root, self.src_btn, "Show only items copied from one app")

        wrap = tk.Frame(self.list_page, bg=BG)
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

        foot = tk.Frame(self.list_page, bg=HEADER, height=34)
        foot.pack(fill="x", side="bottom")
        foot.pack_propagate(False)
        self.bind_drag(foot)
        self.count_lbl = tk.Label(foot, text="", bg=HEADER, fg=MUTED, font=self.f_small, cursor="hand2")
        self.count_lbl.pack(side="left", padx=10)
        self.bind_drag(self.count_lbl, click=self.on_count_click)
        self.clear_lbl = tk.Label(foot, text="Clear history", bg=HEADER, fg=DANGER, font=self.f_small, cursor="hand2")
        self.clear_lbl.pack(side="right", padx=10)
        self.clear_lbl.bind("<Button-1>", lambda e: self.clear_current())
        Tooltip(self.root, self.clear_lbl, "Delete everything in this tab\n(pinned items and snippets are kept)")
        Tooltip(self.root, self.count_lbl, "Click for what's new / updates")

    def icon_btn(self, parent, text, cmd):
        b = tk.Label(parent, text=text, bg=HEADER, fg=MUTED, font=self.f_icon, cursor="hand2", padx=6)
        b.pack(side="right")
        b.bind("<Button-1>", lambda e: cmd())
        return b

    # ============================================================ moving: drag from anywhere
    def bind_drag(self, widget, click=None, menu=None):
        widget.bind("<ButtonPress-1>", lambda e: self.press_begin(e, click), add="+")
        widget.bind("<B1-Motion>", self.press_move, add="+")
        widget.bind("<ButtonRelease-1>", self.press_end, add="+")
        if menu:
            widget.bind("<Button-3>", menu, add="+")

    def press_begin(self, e, click):
        if self.focus_active and self.page == "list":
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

    # ============================================================ resizing: any edge or corner
    def edge_zone(self, e):
        if self.collapsed or not self.visible:
            return None
        x = e.x_root - self.root.winfo_rootx()
        y = e.y_root - self.root.winfo_rooty()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        if x < 0 or y < 0 or x >= w or y >= h:
            return None
        nl, nr, nt, nb = x < CORNER, x >= w - CORNER, y < CORNER, y >= h - CORNER
        if (nl or nr) and (nt or nb):
            return (nl, nr, nt, nb)
        if x < EDGE or x >= w - EDGE or y < EDGE or y >= h - EDGE:
            return (x < EDGE, x >= w - EDGE, y < EDGE, y >= h - EDGE)
        return None

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
        if self.popup and not self.popup.contains(e.widget):
            self.popup.close()
        z = self.edge_zone(e)
        if z:
            self._press = None
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
        wl, wt, wr, wb = win.work_area()
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
        wrap = max(120, e.width - 170)
        for lbl in self.wrap_labels:
            try:
                lbl.config(wraplength=wrap)
            except tk.TclError:
                pass

    # ============================================================ window show / hide / keyboard focus
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

    def show_window(self, kb=False):
        if not self.visible:
            self.root.deiconify()
            self.visible = True
            win.set_noactivate(self.hwnd, True)
            if self.cfg["always_on_top"]:
                win.keep_topmost(self.hwnd)
        if self.collapsed:
            self.toggle_collapse()
        if kb:
            self.enter_kb_mode()

    def hide_window(self):
        if self.focus_active:
            self.release_focus()
        self.opened_by_hotkey = False
        self.close_popup()
        self.root.withdraw()
        self.visible = False

    def toggle_window(self, from_hotkey=False):
        if self.visible and (not from_hotkey or self.kb_mode):
            self.hide_window()
        elif self.visible:
            self.opened_by_hotkey = True
            self.enter_kb_mode()
        else:
            self.opened_by_hotkey = from_hotkey
            self.show_window(kb=from_hotkey)

    def activate_keyboard(self):
        self.focus_active = True
        win.set_noactivate(self.hwnd, False)
        win.force_foreground(self.hwnd)
        self.root.focus_force()

    def enter_kb_mode(self):
        if self.page != "list":
            self.close_page()
        self.kb_mode = True
        self.activate_keyboard()
        self.sel = 0
        self.render()

    def focus_entry(self, entry):
        try:
            if not entry.winfo_exists():
                return
        except tk.TclError:
            return
        if not self.focus_active:
            self.activate_keyboard()
        entry.focus_force()
        if entry is not self.search:
            try:
                entry.select_range(0, "end")
                entry.icursor("end")
            except (tk.TclError, AttributeError):
                pass

    def release_focus(self, restore=True):
        if not self.focus_active:
            return
        was_kb = self.kb_mode
        self.focus_active = False
        self.kb_mode = False
        self.recording = None
        win.set_noactivate(self.hwnd, True)
        self.root.focus_set()
        if restore and self.target:
            win.set_foreground(self.target)
        if was_kb and self.visible and self.page == "list":
            self.root.after_idle(lambda: self.render(keep_scroll=True))

    def maybe_release(self):
        """Search box lost focus: give focus back unless we are in keyboard mode."""
        if self.focus_active and not self.kb_mode and self.page == "list" and self.rename_item is None:
            fw = self.root.focus_get()
            if not isinstance(fw, (tk.Entry, tk.Text)):
                self.release_focus()

    def on_close_button(self):
        if self.cfg["close_to_tray"] and self.host and self.host.tray_ok:
            self.hide_window()
        else:
            self.quit_app()

    def quit_app(self):
        self.quitting = True
        self.save_settings()
        try:
            if self.host:
                self.host.stop()
        except Exception:
            pass
        self.root.destroy()

    # ============================================================ keyboard handling
    def on_key(self, e):
        if self.recording:
            self.record_key(e)
            return "break"
        if not self.focus_active or self.page != "list":
            return None
        ks = e.keysym
        fw = self.root.focus_get()
        typing = isinstance(fw, (tk.Entry, tk.Text))
        if typing and fw is not self.search:
            return None  # renaming: let the entry handle everything
        if ks == "Escape":
            if typing and self.query.get():
                self.query.set("")
                self.root.focus_set()
            elif self.opened_by_hotkey:
                self.hide_window()
            else:
                self.release_focus()
            return "break"
        if ks in ("Down", "Up", "Next", "Prior"):
            step = {"Down": 1, "Up": -1, "Next": 5, "Prior": -5}[ks]
            self.move_selection(step)
            return "break"
        if ks in ("Return", "KP_Enter"):
            if 0 <= self.sel < len(self.shown):
                self.activate_index(self.sel, plain=bool(e.state & 0x1))
            return "break"
        if ks == "Tab":
            self.cycle_tab()
            return "break"
        if typing:
            return None
        if ks in ("Home", "End"):
            self.move_selection(-9999 if ks == "Home" else 9999)
            return "break"
        if ks.isdigit() and ks != "0":
            i = int(ks) - 1
            if i < len(self.shown):
                self.activate_index(i)
            return "break"
        if ks == "Delete" and 0 <= self.sel < len(self.shown) and self.tab != "snippets":
            self.delete(self.shown[self.sel])
            return "break"
        if ks == "F2" and 0 <= self.sel < len(self.shown) and self.tab in ("history", "pinned"):
            self.start_rename(self.shown[self.sel])
            return "break"
        if ks == "slash":
            self.focus_entry(self.search)
            return "break"
        if e.char and e.char.isprintable() and not (e.state & 0x4):
            self.focus_entry(self.search)
            self.search.insert("end", e.char)
            return "break"
        return None

    def cycle_tab(self):
        keys = [k for k, _ in TABS]
        self.set_tab(keys[(keys.index(self.tab) + 1) % len(keys)])
        if self.kb_mode:
            self.sel = 0
            self.apply_selection()

    def move_selection(self, step):
        if not self.shown:
            return
        self.sel = clamp((self.sel if self.sel >= 0 else 0) + step, 0, len(self.shown) - 1)
        self.apply_selection()

    def apply_selection(self):
        if self.sel_frame is not None:
            try:
                self.sel_frame.config(highlightbackground=CARD)
            except tk.TclError:
                pass
        self.sel_frame = None
        if 0 <= self.sel < len(self.card_frames):
            f = self.card_frames[self.sel]
            f.config(highlightbackground=ACCENT)
            self.sel_frame = f
            self.root.update_idletasks()
            top, bottom = f.winfo_y(), f.winfo_y() + f.winfo_height()
            total = max(1, self.inner.winfo_height())
            view_h = self.canvas.winfo_height()
            y0 = self.canvas.yview()[0] * total
            if top < y0:
                self.canvas.yview_moveto(max(0, top - 6) / total)
            elif bottom > y0 + view_h:
                self.canvas.yview_moveto((bottom - view_h + 6) / total)

    def activate_index(self, i, plain=False):
        it = self.shown[i]
        if self.tab == "snippets":
            self.paste_snippet(it)
        else:
            self.activate_item(it, transform=core.t_trim if plain else None)

    # ============================================================ global events (hotkeys / tray)
    def start_host(self):
        try:
            icon = os.path.join(APP_DIR, "clipdock.ico")
            self.host = win.NativeHost(self.events, icon, f"ClipDock \u2014 {core.pretty_hotkey(self.cfg['hotkey'])}")
            self.host.start(self.hotkey_map())
            self.host.menu_state.update(paused=self.paused, stack=self.stack_mode)
            if self.host.error:
                log(f"host: {self.host.error}")
        except Exception as e:
            log(f"start_host: {e}")
            self.host = None

    def hotkey_map(self):
        m = {}
        for hid, key in ((win.HOTKEY_TOGGLE, "hotkey"), (win.HOTKEY_STACK, "stack_hotkey")):
            parsed = core.parse_hotkey(self.cfg[key])
            if parsed:
                m[hid] = parsed
        return m

    def poll_events(self):
        try:
            while True:
                ev = self.events.get_nowait()
                self.handle_event(ev)
        except queue.Empty:
            pass
        except Exception as e:
            log(f"poll_events: {e}")
        if not self.quitting:
            self.root.after(60, self.poll_events)

    def handle_event(self, ev):
        kind = ev[0]
        if kind == "hotkey":
            _, hid, fg = ev
            if fg and fg != self.hwnd and win.window_class(fg) not in win.IGNORED_TARGET_CLASSES:
                self.target = fg
            if hid == win.HOTKEY_TOGGLE:
                self.toggle_window(from_hotkey=True)
            elif hid == win.HOTKEY_STACK:
                self.paste_next()
        elif kind == "tray_cmd":
            cmd = ev[1]
            if cmd == win.TRAY_TOGGLE:
                self.toggle_window()
            elif cmd == win.TRAY_PAUSE:
                self.toggle_pause()
            elif cmd == win.TRAY_STACK:
                self.toggle_stack()
            elif cmd == win.TRAY_SETTINGS:
                self.show_window()
                self.show_settings()
            elif cmd == win.TRAY_FEEDBACK:
                self.show_window()
                self.open_feedback_menu(self.btn_feedback)
            elif cmd == win.TRAY_UPDATE:
                self.show_window()
                self.on_update_button()
            elif cmd == win.TRAY_QUIT:
                self.quit_app()

    # ============================================================ toggles in the header
    def toggle_pause(self):
        self.paused = not self.paused
        self.btn_pause.config(fg=DANGER if self.paused else OK)
        self.last_seq = win.clipboard_sequence()
        if self.host:
            self.host.menu_state["paused"] = self.paused

    def toggle_stack(self):
        self.stack_mode = not self.stack_mode
        self.btn_stack.config(fg=ACCENT if self.stack_mode else MUTED)
        if self.host:
            self.host.menu_state["stack"] = self.stack_mode
        self.flash_status("Paste stack ON \u2014 copy things, then paste with "
                          + core.pretty_hotkey(self.cfg["stack_hotkey"]) if self.stack_mode else "Paste stack OFF")
        if self.tab == "stack":
            self.render()

    def toggle_theme(self):
        self.apply_theme("light" if self.theme == "dark" else "dark", self.cfg["accent"])

    def apply_theme(self, theme, accent):
        old = palette(self.theme, self.cfg["accent"])
        self.theme = theme
        self.cfg["theme"], self.cfg["accent"] = theme, accent
        set_theme(theme, accent)
        self.retheme(old, palette(theme, accent))
        self.btn_theme.config(text="\u2600" if theme == "dark" else "\u263E")
        self.btn_stack.config(fg=ACCENT if self.stack_mode else MUTED)
        self.update_count()
        if self.page == "settings":
            self.show_settings(keep_scroll=True)
        self.render(keep_scroll=True)
        self.save_settings()

    def retheme(self, old, new):
        """Recolour every existing widget by mapping each old palette colour to its new one."""
        mapping = {old[k].lower(): new[k] for k in old}

        def walk(w):
            for opt in ("bg", "fg", "insertbackground", "highlightbackground"):
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
        self.src_filter = None if key in ("snippets", "stack") else self.src_filter
        self.sel = 0 if self.kb_mode else -1
        self.render()

    def on_wheel(self, e):
        self.canvas.yview_scroll(int(-e.delta / 120) * 2, "units")

    # ============================================================ clipboard capture
    def tick(self):
        try:
            self._tick_n += 1
            fg = win.foreground_window()
            if (fg and fg != self.hwnd and not self.focus_active
                    and win.window_class(fg) not in win.IGNORED_TARGET_CLASSES):
                self.target = fg
            if self.cfg["always_on_top"] and self.visible:
                win.keep_topmost(self.hwnd)
            if self._upd:
                self.handle_update_result()
            if self._dl:
                self.refresh_update_page()
            seq = win.clipboard_sequence()
            if seq != self.last_seq:
                self.last_seq = seq
                if not self.paused:
                    self.capture()
            if self._tick_n % 120 == 0:
                self.sync_pull()
        except Exception as e:
            log(f"tick: {type(e).__name__}: {e}")
        finally:
            if not self.quitting:
                self.root.after(250, self.tick)

    def capture(self):
        now = time.time()
        if now < self.suppress_until:
            return
        src = core.friendly_source(win.clipboard_source())
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            text = None
        if text is not None:
            if not text.strip():
                return
            if text == self.skip_text and now < self.skip_until:
                return
            self.add_item({"t": text[:MAX_CHARS], "ts": now, "pin": False, "src": src})
            return
        data = win.read_clipboard_nontext()
        if not data:
            return
        kind, payload = data
        if kind == "files":
            self.add_item({"kind": "files", "files": payload, "t": "\n".join(payload), "ts": now,
                           "pin": False, "src": src})
        elif kind == "image":
            self.capture_image(payload, src, now)

    def capture_image(self, dib, src, now):
        key = core.short_hash(dib)
        if not any(i.get("k") == key for i in self.items):
            assets = core.image_assets(dib)
            if not assets:
                return
            try:
                os.makedirs(IMG_DIR, exist_ok=True)
                with open(os.path.join(IMG_DIR, f"{key}_t.png"), "wb") as f:
                    f.write(assets["thumb"])
                with open(os.path.join(IMG_DIR, f"{key}.dib.z"), "wb") as f:
                    f.write(zlib.compress(dib, 3))
            except OSError as e:
                log(f"capture_image: {e}")
                return
            entry = {"kind": "image", "k": key, "t": f"Image {assets['w']}\u00D7{assets['h']}", "w": assets["w"],
                     "h": assets["h"], "ts": now, "pin": False, "src": src}
        else:
            entry = {"kind": "image", "k": key, "t": next(i["t"] for i in self.items if i.get("k") == key),
                     "ts": now, "pin": False, "src": src}
        self.add_item(entry)

    def add_item(self, entry):
        key = core.item_key(entry)
        for it in list(self.items):
            if core.item_key(it) == key:
                entry["pin"] = it.get("pin", False)
                if it.get("name"):
                    entry["name"] = it["name"]
                for extra in ("w", "h"):
                    if extra in it and extra not in entry:
                        entry[extra] = it[extra]
                self.items.remove(it)
                if it in self.stack:
                    self.stack.remove(it)
                break
        self.items.insert(0, entry)
        if self.stack_mode:
            self.stack.append(entry)
        self.enforce_limits()
        self.save()
        if self.rename_item is None and self.page == "list":
            self.render(keep_scroll=True)
        else:
            self.update_count()

    def enforce_limits(self):
        limit = self.cfg["history_limit"]
        unpinned = [i for i in self.items if not i.get("pin")]
        for extra in unpinned[limit:]:
            self.drop_item(extra)
        images = [i for i in self.items if i.get("kind") == "image" and not i.get("pin")]
        for extra in images[MAX_IMAGES:]:
            self.drop_item(extra)

    def drop_item(self, it):
        if it in self.items:
            self.items.remove(it)
        if it in self.stack:
            self.stack.remove(it)
        if it.get("kind") == "image" and not any(o is not it and o.get("k") == it.get("k") for o in self.items):
            for name in (f"{it.get('k')}_t.png", f"{it.get('k')}.dib.z"):
                try:
                    os.remove(os.path.join(IMG_DIR, name))
                except OSError:
                    pass
            self.thumbs.pop(it.get("k"), None)

    def load_dib(self, it):
        try:
            with open(os.path.join(IMG_DIR, f"{it.get('k')}.dib.z"), "rb") as f:
                return zlib.decompress(f.read())
        except (OSError, zlib.error):
            return None

    def get_thumb(self, it):
        k = it.get("k")
        if k in self.thumbs:
            return self.thumbs[k]
        try:
            img = tk.PhotoImage(file=os.path.join(IMG_DIR, f"{k}_t.png"))
        except tk.TclError:
            img = None
        self.thumbs[k] = img
        return img

    # ============================================================ pasting
    def set_text_clip(self, text):
        self.skip_text, self.skip_until = text, time.time() + 1.5
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update_idletasks()
        return True

    def safe_clip_text(self):
        try:
            return self.root.clipboard_get()
        except tk.TclError:
            return ""

    def paste(self, it, transform=None):
        kind = it.get("kind", "text")
        if kind == "image":
            dib = self.load_dib(it)
            ok = bool(dib) and win.set_clipboard_dib(dib)
            self.suppress_until = time.time() + 1.5
        elif kind == "files":
            ok = win.set_clipboard_files(it.get("files", []))
            self.suppress_until = time.time() + 1.5
        else:
            text = transform(it["t"]) if transform else it["t"]
            ok = self.set_text_clip(text)
        if not ok:
            self.flash_status("Couldn't paste that item")
            return
        self.finish_paste()

    def paste_snippet(self, sn):
        self.set_text_clip(core.expand_snippet(sn.get("text", ""), clipboard=self.safe_clip_text()))
        self.finish_paste()

    def finish_paste(self):
        was_kb = self.kb_mode
        if self.focus_active:
            self.release_focus()
        if was_kb and self.cfg["hide_after_paste"]:
            self.hide_window()
        if self.target and win.foreground_window() != self.target:
            win.set_foreground(self.target)
        self.root.after(90, self.send_paste)

    def send_paste(self, tries=0):
        if win.modifiers_down() and tries < 15:     # wait until the hotkey keys are released
            self.root.after(40, lambda: self.send_paste(tries + 1))
            return
        win.release_modifiers()
        win.send_ctrl_v()

    def activate_item(self, it, transform=None):
        if self.tab == "stack" and it in self.stack:
            self.stack.remove(it)
        self.paste(it, transform)
        if self.tab == "stack":
            self.render(keep_scroll=True)

    def paste_next(self):
        if not self.stack:
            self.flash_status("Paste stack is empty")
            return
        it = self.stack.pop(0 if self.cfg["stack_order"] == "fifo" else -1)
        self.paste(it)
        self.update_count()
        if self.tab == "stack" and self.visible:
            self.render(keep_scroll=True)

    # ============================================================ item actions
    def toggle_pin(self, it):
        it["pin"] = not it.get("pin", False)
        self.save()
        self.render(keep_scroll=True)

    def delete(self, it):
        if it is self.rename_item:
            self.rename_item = None
            self.release_focus()
        self.drop_item(it)
        self.save()
        self.render(keep_scroll=True)

    def clear_current(self):
        self.rename_item = None
        self.release_focus()
        if self.tab == "stack":
            self.stack.clear()
        elif self.tab in ("history", "pinned"):
            for it in [i for i in self.items if not i.get("pin")]:
                self.drop_item(it)
            self.save()
        self.render()

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

    def open_url(self, url):
        try:
            webbrowser.open(url)
        except Exception as e:
            log(f"open_url: {e}")

    def save_image_as(self, it):
        dib = self.load_dib(it)
        assets = core.image_assets(dib) if dib else None
        if not assets:
            self.flash_status("Couldn't read that image")
            return
        path = self.run_dialog(filedialog.asksaveasfilename, defaultextension=".png",
                               filetypes=[("PNG image", "*.png")], initialfile="ClipDock-image.png")
        if path:
            with open(path, "wb") as f:
                f.write(assets["png"])
            self.flash_status("Image saved")

    def item_menu(self, it, event):
        kind = it.get("kind", "text")
        rows = [("Paste", lambda: self.activate_item(it))]
        if kind == "text":
            text = it["t"]
            rows.append(None)
            for label, fn in core.TRANSFORMS:
                rows.append((f"Paste as {label}", lambda f=fn: self.activate_item(it, transform=f)))
            what = core.detect(text)
            extra = []
            if what == "url":
                extra.append(("Open link in browser", lambda: self.open_url(core.url_of(text))))
            elif what == "email":
                extra.append(("Write an e-mail", lambda: self.open_url("mailto:" + text.strip())))
            elif what == "json":
                extra.append(("Paste pretty-printed JSON", lambda: self.activate_item(it, transform=core.json_pretty)))
                extra.append(("Paste minified JSON", lambda: self.activate_item(it, transform=core.json_minify)))
            if extra:
                rows.append(None)
                rows.extend(extra)
        elif kind == "image":
            rows += [None, ("Save image as\u2026", lambda: self.save_image_as(it))]
        rows.append(None)
        if self.tab in ("history", "pinned", "stack"):
            rows.append(("Rename\u2026" if it.get("name") else "Give it a name\u2026", lambda: self.start_rename(it)))
            rows.append(("Unpin" if it.get("pin") else "Pin", lambda: self.toggle_pin(it)))
            if kind == "text":
                rows.append(("Save as snippet\u2026", lambda: self.open_snippet_editor(prefill=it["t"])))
            if it in self.stack:
                rows.append(("Remove from paste stack", lambda: (self.stack.remove(it), self.render(keep_scroll=True))))
            else:
                rows.append(("Add to paste stack", lambda: (self.stack.append(it), self.update_count(),
                                                            self.flash_status("Added to the paste stack"))))
            rows.append(("Delete", lambda: self.delete(it)))
        self.open_popup(rows, event.x_root, event.y_root)

    def open_popup(self, rows, x, y):
        self.close_popup()
        self.popup = PopupMenu(self, rows, x, y)

    def close_popup(self):
        if self.popup:
            self.popup.close()

    def open_source_menu(self):
        counts = {}
        for it in self.items:
            if it.get("src"):
                counts[it["src"]] = counts.get(it["src"], 0) + 1
        rows = [(f"All apps ({len(self.items)})", lambda: self.set_source(None))]
        for name, n in sorted(counts.items(), key=lambda kv: -kv[1])[:14]:
            check = "\u2713 " if self.src_filter == name else ""
            rows.append((f"{check}{name} ({n})", lambda s=name: self.set_source(s)))
        b = self.src_btn
        self.open_popup(rows, b.winfo_rootx() - 120, b.winfo_rooty() + b.winfo_height() + 4)

    def set_source(self, name):
        self.src_filter = name
        self.src_btn.config(text=(name if name else "All apps") + " \u25BE", fg=ACCENT if name else MUTED)
        self.render()

    # ============================================================ rendering the list
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

    @staticmethod
    def preview(text):
        lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
        out = "\n".join(lines[:3])
        if len(out) > 180:
            out = out[:180]
        return out + (" \u2026" if len(lines) > 3 or len(text.strip()) > len(out) else "")

    def inside(self, widget):
        cur = self.root.winfo_containing(*self.root.winfo_pointerxy())
        while cur is not None:
            if cur is widget:
                return True
            cur = cur.master
        return False

    def update_count(self):
        if self.update_ready:
            txt, fg = f"Update v{self.update_ready} \u2197", ACCENT
        elif self.stack_mode:
            txt, fg = f"Stack ON \u00B7 {len(self.stack)} queued", ACCENT
        else:
            txt, fg = f"v{VERSION} \u00B7 {len(self.items)} items", MUTED
        self.count_lbl.config(text=txt, fg=fg)
        self.btn_update.config(fg=ACCENT if self.update_ready else MUTED)

    def flash_status(self, msg):
        self.count_lbl.config(text=msg, fg=MUTED)
        self.root.after(4000, self.update_count)

    def visible_items(self):
        q = self.query.get().strip().lower()

        def match(i):
            if not q:
                return True
            return (q in i.get("t", "").lower() or q in i.get("name", "").lower()
                    or q in i.get("src", "").lower())

        if self.tab == "stack":
            order = list(self.stack) if self.cfg["stack_order"] == "fifo" else list(reversed(self.stack))
            return [i for i in order if match(i)]
        base = [i for i in self.items if (self.tab == "history" or i.get("pin"))]
        if self.src_filter:
            base = [i for i in base if i.get("src") == self.src_filter]
        return [i for i in base if match(i)]

    def visible_snippets(self):
        q = self.query.get().strip().lower()
        out = []
        for s in self.snippets:
            if self.snip_tag and s.get("tag", "") != self.snip_tag:
                continue
            if q and q not in s.get("name", "").lower() and q not in s.get("text", "").lower() \
                    and q not in s.get("tag", "").lower():
                continue
            out.append(s)
        return sorted(out, key=lambda s: (s.get("tag", "").lower(), s.get("name", "").lower()))

    def render(self, keep_scroll=False):
        if not hasattr(self, "inner"):
            return
        top = self.canvas.yview()[0] if keep_scroll else 0.0
        for k, b in self.tab_btns.items():
            on = k == self.tab
            label = dict(TABS)[k]
            if k == "pinned":
                label = f"Pinned ({sum(1 for i in self.items if i.get('pin'))})"
            if k == "stack" and self.stack:
                label = f"Stack ({len(self.stack)})"
            b.config(text=label, bg=ACCENT if on else CARD, fg=WHITE if on else MUTED)
        self.update_count()
        self.clear_lbl.config(text={"history": "Clear history", "pinned": "Clear history",
                                    "stack": "Clear stack", "snippets": ""}[self.tab])
        self.src_btn.pack_forget() if self.tab in ("snippets", "stack") else self.src_btn.pack(side="right")

        for w in self.inner.winfo_children():
            w.destroy()
        self.wrap_labels, self.card_frames = [], []
        self.sel_frame = None

        if self.tab == "snippets":
            self.render_snippets()
        else:
            self.shown = self.visible_items()
            if not self.shown:
                msg = {"pinned": "Nothing pinned yet.\nTap \u2606 on an item to keep it here.",
                       "stack": "The paste stack is empty.\nTurn it on with the \u2263 button, copy a few things,\n"
                                f"then press {core.pretty_hotkey(self.cfg['stack_hotkey'])} to paste them in order."
                       }.get(self.tab, "Copy something (Ctrl+C) and it will appear here.")
                if self.query.get().strip() or self.src_filter:
                    msg = "No matches."
                lbl = tk.Label(self.inner, text=msg, bg=BG, fg=MUTED, font=self.f_body, justify="center", pady=40)
                lbl.pack(fill="x")
                self.bind_drag(lbl)
            for idx, it in enumerate(self.shown[:120]):
                self.make_card(it, idx)
        if self.kb_mode:
            self.sel = clamp(self.sel, 0, max(0, len(self.card_frames) - 1)) if self.card_frames else -1
        else:
            self.sel = -1
        self.root.update_idletasks()
        self.canvas.yview_moveto(top)
        self.apply_selection()

    @staticmethod
    def badge_for(it):
        kind = it.get("kind", "text")
        if kind == "files":
            n = len(it.get("files", []))
            return (f"\U0001F4CE {n} file{'s' if n != 1 else ''}", None)
        if kind != "text":
            return None
        what = core.detect(it["t"])
        if what == "url":
            return ("\U0001F517 link", "url")
        if what == "email":
            return ("\u2709 email", "email")
        if what == "json":
            return ("{ } JSON", "json")
        if what == "color":
            return (f"\u25CF {it['t'].strip()}", "color")
        return None

    def make_card(self, it, idx):
        kind = it.get("kind", "text")
        renaming = it is self.rename_item
        pinned = it.get("pin", False)
        name = it.get("name", "")
        cw = self.canvas.winfo_width()
        wrap = max(120, (cw if cw > 50 else self.w) - 170)

        card = tk.Frame(self.inner, bg=CARD, cursor="" if renaming else "hand2", padx=10, pady=8,
                        highlightthickness=2, highlightbackground=CARD)
        card.pack(fill="x", padx=10, pady=3)
        card.columnconfigure(1, weight=1)
        self.card_frames.append(card)
        parts, clickable = [card], [card]

        if self.kb_mode and idx < 9:
            num = tk.Label(card, text=str(idx + 1), bg=CARD, fg=ACCENT, font=self.f_name, width=2)
            num.grid(row=0, column=0, sticky="nw", padx=(0, 4))
            parts.append(num)
            clickable.append(num)

        row = 0
        if renaming:
            ent = tk.Entry(card, bg=BG, fg=FG, insertbackground=FG, bd=0, relief="flat", font=self.f_body)
            ent.insert(0, name)
            ent.grid(row=0, column=1, sticky="we", pady=(0, 4), padx=(0, 6), ipady=4)
            ent.bind("<Return>", lambda e, i=it, w=ent: self.commit_rename(i, w))
            ent.bind("<Escape>", lambda e: self.cancel_rename())
            ent.bind("<FocusOut>", lambda e, i=it, w=ent: self.commit_rename(i, w))
            self.root.after(40, lambda w=ent: self.focus_entry(w))
            row = 1
        elif name:
            nl = tk.Label(card, text=name, bg=CARD, fg=ACCENT, font=self.f_name, anchor="w",
                          justify="left", wraplength=wrap)
            nl.grid(row=0, column=1, sticky="we")
            self.wrap_labels.append(nl)
            parts.append(nl)
            clickable.append(nl)
            row = 1

        if kind == "image":
            thumb = self.get_thumb(it)
            body = tk.Label(card, image=thumb, bg=CARD, anchor="w") if thumb else \
                tk.Label(card, text=it["t"], bg=CARD, fg=FG, font=self.f_body, anchor="w")
        elif kind == "files":
            names = [os.path.basename(p.rstrip("\\/")) or p for p in it.get("files", [])]
            shown = "\n".join(names[:3]) + (f"\n\u2026 and {len(names) - 3} more" if len(names) > 3 else "")
            body = tk.Label(card, text="\U0001F4C4 " + shown.replace("\n", "\n    "), bg=CARD, fg=FG,
                            font=self.f_body, justify="left", anchor="w", wraplength=wrap)
            self.wrap_labels.append(body)
        else:
            body = tk.Label(card, text=self.preview(it["t"]), bg=CARD, fg=FG, font=self.f_body,
                            justify="left", anchor="w", wraplength=wrap)
            self.wrap_labels.append(body)
        body.grid(row=row, column=1, sticky="we")
        parts.append(body)
        clickable.append(body)

        mf = tk.Frame(card, bg=CARD)
        mf.grid(row=row + 1, column=1, sticky="we", pady=(2, 0))
        size = {"image": f"{it.get('w', '?')}\u00D7{it.get('h', '?')}",
                "files": f"{len(it.get('files', []))} item(s)"}.get(kind, f"{len(it['t'])} chars")
        bits = [self.ago(it["ts"]), size] + ([it["src"]] if it.get("src") else [])
        if self.tab == "stack" and it in self.stack:
            order = self.stack if self.cfg["stack_order"] == "fifo" else list(reversed(self.stack))
            bits.insert(0, f"#{order.index(it) + 1}")
        meta = tk.Label(mf, text="  \u00B7  ".join(bits), bg=CARD, fg=MUTED, font=self.f_small, anchor="w")
        meta.pack(side="left")
        parts += [mf, meta]
        clickable += [mf, meta]
        b = self.badge_for(it)
        if b:
            text, action = b
            col = ACCENT
            if action == "color":
                try:
                    col = it["t"].strip()
                    card.winfo_rgb(col)
                except tk.TclError:
                    col = ACCENT
            bl = tk.Label(mf, text=text, bg=CARD, fg=col, font=self.f_small, padx=8,
                          cursor="hand2" if action in ("url", "email") else "")
            bl.pack(side="left")
            parts.append(bl)
            if action == "url":
                bl.bind("<Button-1>", lambda e, t=it["t"]: self.open_url(core.url_of(t)))
                Tooltip(self.root, bl, "Open this link in your browser")
            elif action == "email":
                bl.bind("<Button-1>", lambda e, t=it["t"]: self.open_url("mailto:" + t.strip()))
                Tooltip(self.root, bl, "Write an e-mail to this address")
            elif action == "json":
                bl.bind("<Button-1>", lambda e, i=it: self.activate_item(i, transform=core.json_pretty))
                bl.config(cursor="hand2")
                Tooltip(self.root, bl, "Click to paste this JSON pretty-printed\nRight-click the item for more")

        edit = tk.Label(card, text="\u270E", bg=CARD, fg=ACCENT if name else MUTED, font=self.f_icon,
                        cursor="hand2", padx=2)
        pin = tk.Label(card, text="\u2605" if pinned else "\u2606", bg=CARD, font=self.f_icon,
                       fg=ACCENT if pinned else MUTED, cursor="hand2", padx=2)
        dele = tk.Label(card, text="\u2715", bg=CARD, fg=MUTED, font=self.f_small, cursor="hand2", padx=2)
        more = tk.Label(card, text="\u22EE", bg=CARD, fg=MUTED, font=self.f_icon, cursor="hand2", padx=2)
        for c, w in enumerate((edit, pin, dele, more), start=2):
            w.grid(row=0, column=c, sticky="ne")
        parts += [edit, pin, dele, more]
        edit.bind("<Button-1>", lambda e, i=it: self.start_rename(i))
        pin.bind("<Button-1>", lambda e, i=it: self.toggle_pin(i))
        dele.bind("<Button-1>", lambda e, i=it: self.delete(i))
        more.bind("<Button-1>", lambda e, i=it: self.item_menu(i, e))
        dele.bind("<Enter>", lambda e, w=dele: w.config(fg=DANGER))
        dele.bind("<Leave>", lambda e, w=dele: w.config(fg=MUTED))
        Tooltip(self.root, edit, "Rename this item" if name else "Give this item a name\n(then search for it by name)")
        Tooltip(self.root, pin, "Unpin this item" if pinned else "Pin \u2014 keep this item permanently")
        Tooltip(self.root, dele, "Delete this item")
        Tooltip(self.root, more, "More: paste as UPPER / lower / one line, open link, save as snippet\u2026")

        click = None if renaming else (lambda i=it: self.activate_item(i))
        for w in clickable:
            self.bind_drag(w, click, menu=lambda e, i=it: self.item_menu(i, e))
            if not renaming:
                Tooltip(self.root, w, "Click to paste at your cursor\nRight-click for more \u00B7 drag to move the window",
                        delay=800)

        def hover(on):
            if self.sel_frame is not card:
                card.config(highlightbackground=CARD_HOVER if on else CARD)
            for w in parts:
                try:
                    w.config(bg=CARD_HOVER if on else CARD)
                except tk.TclError:
                    pass

        for w in parts:
            w.bind("<Enter>", lambda e: hover(True), add="+")
            w.bind("<Leave>", lambda e, c=card: hover(self.inside(c)), add="+")

    # ---- snippets list
    def render_snippets(self):
        tags = sorted({s.get("tag", "") for s in self.snippets if s.get("tag")}, key=str.lower)
        top = tk.Frame(self.inner, bg=BG)
        top.pack(fill="x", padx=10, pady=(0, 4))
        self.bind_drag(top)
        add = tk.Label(top, text="\uFF0B New snippet", bg=ACCENT, fg=WHITE, font=self.f_body, padx=12, pady=4,
                       cursor="hand2")
        add.pack(side="left", padx=(0, 8))
        add.bind("<Button-1>", lambda e: self.open_snippet_editor())
        Tooltip(self.root, add, "Create reusable text. Variables: {date} {time} {clipboard} {user} \u2026")
        for tag in [None] + tags:
            on = self.snip_tag == tag
            chip = tk.Label(top, text=tag or "All", bg=CARD_HOVER if on else CARD, fg=ACCENT if on else MUTED,
                            font=self.f_small, padx=8, pady=3, cursor="hand2")
            chip.pack(side="left", padx=2)
            chip.bind("<Button-1>", lambda e, t=tag: self.set_snip_tag(t))
        self.shown = self.visible_snippets()
        if not self.shown:
            lbl = tk.Label(self.inner, text="No snippets yet.\nClick \u201C\uFF0B New snippet\u201D or right-click a "
                           "copied item \u2192 Save as snippet.", bg=BG, fg=MUTED, font=self.f_body,
                           justify="center", pady=30)
            lbl.pack(fill="x")
            self.bind_drag(lbl)
        cw = self.canvas.winfo_width()
        wrap = max(120, (cw if cw > 50 else self.w) - 150)
        for idx, sn in enumerate(self.shown[:200]):
            card = tk.Frame(self.inner, bg=CARD, cursor="hand2", padx=10, pady=8, highlightthickness=2,
                            highlightbackground=CARD)
            card.pack(fill="x", padx=10, pady=3)
            card.columnconfigure(1, weight=1)
            self.card_frames.append(card)
            parts = [card]
            if self.kb_mode and idx < 9:
                num = tk.Label(card, text=str(idx + 1), bg=CARD, fg=ACCENT, font=self.f_name, width=2)
                num.grid(row=0, column=0, sticky="nw", padx=(0, 4))
                parts.append(num)
            nl = tk.Label(card, text=sn.get("name") or "(unnamed)", bg=CARD, fg=ACCENT, font=self.f_name,
                          anchor="w", wraplength=wrap, justify="left")
            nl.grid(row=0, column=1, sticky="we")
            tx = tk.Label(card, text=self.preview(sn.get("text", "")), bg=CARD, fg=FG, font=self.f_body,
                          anchor="w", justify="left", wraplength=wrap)
            tx.grid(row=1, column=1, sticky="we")
            self.wrap_labels += [nl, tx]
            tag = tk.Label(card, text=("\U0001F4C1 " + sn["tag"]) if sn.get("tag") else "no folder", bg=CARD,
                           fg=MUTED, font=self.f_small, anchor="w")
            tag.grid(row=2, column=1, sticky="w", pady=(2, 0))
            edit = tk.Label(card, text="\u270E", bg=CARD, fg=MUTED, font=self.f_icon, cursor="hand2", padx=2)
            dele = tk.Label(card, text="\u2715", bg=CARD, fg=MUTED, font=self.f_small, cursor="hand2", padx=2)
            edit.grid(row=0, column=2, sticky="ne")
            dele.grid(row=0, column=3, sticky="ne")
            edit.bind("<Button-1>", lambda e, s=sn: self.open_snippet_editor(s))
            dele.bind("<Button-1>", lambda e, s=sn: self.delete_snippet(s))
            Tooltip(self.root, edit, "Edit this snippet")
            Tooltip(self.root, dele, "Delete this snippet")
            parts += [nl, tx, tag, edit, dele]
            for w in (card, nl, tx, tag) + ((parts[1],) if self.kb_mode and idx < 9 else ()):
                self.bind_drag(w, lambda s=sn: self.paste_snippet(s))
                Tooltip(self.root, w, "Click to paste (variables like {date} are filled in)", delay=800)

            def hover(on, c=card, ps=tuple(parts)):
                if self.sel_frame is not c:
                    c.config(highlightbackground=CARD_HOVER if on else CARD)
                for w in ps:
                    try:
                        w.config(bg=CARD_HOVER if on else CARD)
                    except tk.TclError:
                        pass

            for w in parts:
                w.bind("<Enter>", lambda e, h=hover: h(True), add="+")
                w.bind("<Leave>", lambda e, c=card, h=hover: h(self.inside(c)), add="+")

    def set_snip_tag(self, tag):
        self.snip_tag = tag
        self.render()

    def delete_snippet(self, sn):
        if sn in self.snippets:
            self.snippets.remove(sn)
            self.save_snippets()
        self.render(keep_scroll=True)

    # ============================================================ pages (settings, editor, info)
    def open_page(self, name, builder):
        self.close_popup()
        if self.page != "list":
            self.close_page(render=False)
        self.page = name
        self.list_page.pack_forget()
        self.alt_page = tk.Frame(self.body, bg=BG)
        self.alt_page.pack(fill="both", expand=True)
        self.bind_drag(self.alt_page)
        builder(self.alt_page)

    def close_page(self, render=True):
        if self.alt_page is not None:
            self.alt_page.destroy()
            self.alt_page = None
        if self.focus_active and not self.kb_mode:
            self.release_focus()
        self.page = "list"
        self.recording = None
        self.list_page.pack(fill="both", expand=True)
        if render:
            self.render()

    def page_header(self, parent, title, on_back=None):
        bar = tk.Frame(parent, bg=BG)
        bar.pack(fill="x", padx=10, pady=(10, 4))
        self.bind_drag(bar)
        back = tk.Label(bar, text="\u2190", bg=BG, fg=ACCENT, font=self.f_icon, cursor="hand2", padx=4)
        back.pack(side="left")
        back.bind("<Button-1>", lambda e: (on_back or self.close_page)())
        Tooltip(self.root, back, "Back")
        t = tk.Label(bar, text=title, bg=BG, fg=FG, font=self.f_title)
        t.pack(side="left", padx=6)
        self.bind_drag(t)

    def button(self, parent, text, cmd, primary=False, danger=False):
        b = tk.Label(parent, text=text, bg=ACCENT if primary else CARD_HOVER, fg=WHITE if primary else
                     (DANGER if danger else FG), font=self.f_small, padx=10, pady=4, cursor="hand2")
        b.bind("<Button-1>", lambda e: cmd())
        return b

    # ---- settings
    def toggle_settings(self):
        if self.page == "settings":
            self.close_page()
        else:
            self.show_settings()

    def show_settings(self, keep_scroll=False):
        pos = 0.0
        if keep_scroll and self.page == "settings" and getattr(self, "settings_sf", None):
            pos = self.settings_sf.canvas.yview()[0]
        self.open_page("settings", self.build_settings)
        if keep_scroll:
            self.root.update_idletasks()
            self.settings_sf.canvas.yview_moveto(pos)

    def build_settings(self, page):
        self.page_header(page, "Settings")
        sf = ScrollFrame(page, self)
        sf.pack(fill="both", expand=True)
        self.settings_sf = sf
        box = sf.inner

        def section(title):
            tk.Label(box, text=title.upper(), bg=BG, fg=MUTED, font=self.f_small, anchor="w").pack(
                fill="x", padx=14, pady=(14, 4))

        def row(label, hint=""):
            f = tk.Frame(box, bg=CARD, padx=12, pady=8)
            f.pack(fill="x", padx=10, pady=2)
            left = tk.Frame(f, bg=CARD)
            left.pack(side="left", fill="x", expand=True)
            tk.Label(left, text=label, bg=CARD, fg=FG, font=self.f_body, anchor="w").pack(anchor="w")
            if hint:
                tk.Label(left, text=hint, bg=CARD, fg=MUTED, font=self.f_small, anchor="w",
                         justify="left", wraplength=210).pack(anchor="w")
            right = tk.Frame(f, bg=CARD)
            right.pack(side="right")
            self.bind_drag(f)
            return right

        def toggle(label, key, hint="", on_change=None, value=None):
            right = row(label, hint)
            state = bool(self.cfg[key]) if value is None else value
            pill = tk.Label(right, text="ON" if state else "OFF", bg=ACCENT if state else CARD_HOVER,
                            fg=WHITE if state else MUTED, font=self.f_small, padx=12, pady=3, cursor="hand2")
            pill.pack()

            def flip(_e=None):
                new = not (bool(self.cfg[key]) if value is None else pill.cget("text") == "ON")
                if on_change:
                    res = on_change(new)
                    new = new if res is None else res
                self.cfg[key] = new
                pill.config(text="ON" if new else "OFF", bg=ACCENT if new else CARD_HOVER, fg=WHITE if new else MUTED)
                self.save_settings()

            pill.bind("<Button-1>", flip)

        def chips(label, options, current, on_pick, hint=""):
            right = row(label, hint)
            labels = []
            for text, val in options:
                on = val == current
                c = tk.Label(right, text=text, bg=ACCENT if on else CARD_HOVER, fg=WHITE if on else FG,
                             font=self.f_small, padx=8, pady=3, cursor="hand2")
                c.pack(side="left", padx=2)
                labels.append((c, val))

                def pick(_e=None, v=val):
                    on_pick(v)
                    for lbl, vv in labels:
                        try:
                            lbl.config(bg=ACCENT if vv == v else CARD_HOVER, fg=WHITE if vv == v else FG)
                        except tk.TclError:
                            return

                c.bind("<Button-1>", pick)

        def slider(label, key, lo, hi, on_change, unit=""):
            f = tk.Frame(box, bg=CARD, padx=12, pady=8)
            f.pack(fill="x", padx=10, pady=2)
            head = tk.Frame(f, bg=CARD)
            head.pack(fill="x")
            tk.Label(head, text=label, bg=CARD, fg=FG, font=self.f_body).pack(side="left")
            val = tk.Label(head, text=f"{self.cfg[key]}{unit}", bg=CARD, fg=MUTED, font=self.f_small)
            val.pack(side="right")
            sc = tk.Scale(f, from_=lo, to=hi, orient="horizontal", showvalue=0, bd=0, highlightthickness=0,
                          bg=CARD, fg=FG, troughcolor=CARD_HOVER, activebackground=ACCENT, sliderrelief="flat",
                          length=200)
            sc.set(self.cfg[key])
            sc.pack(fill="x")

            def moved(v):
                self.cfg[key] = int(float(v))
                val.config(text=f"{self.cfg[key]}{unit}")
                on_change()

            sc.config(command=moved)
            sc.bind("<ButtonRelease-1>", lambda e: self.save_settings())

        # --- general
        section("General")
        toggle("Start with Windows", "autostart", "Open ClipDock automatically when you sign in",
               on_change=self.set_autostart_ui, value=win.get_autostart())
        toggle("Always on top", "always_on_top", "Keep ClipDock above other windows",
               on_change=self.set_topmost)
        toggle("Close button hides to tray", "close_to_tray",
               "The \u2715 hides ClipDock; quit from the tray icon's menu")
        toggle("Hide after pasting", "hide_after_paste", "When opened with the hotkey, close after you paste")

        # --- shortcuts
        section("Shortcuts")
        self.hotkey_rows = {}
        for key, label, hid in (("hotkey", "Show / hide ClipDock", win.HOTKEY_TOGGLE),
                                ("stack_hotkey", "Paste next from the stack", win.HOTKEY_STACK)):
            right = row(label, "Click, then press the new keys")
            ok = self.host.status.get(hid) if self.host else None
            mark = "" if ok is None else ("  \u2713" if ok else "  \u2717 in use")
            btn = self.button(right, core.pretty_hotkey(self.cfg[key]) + mark, lambda k=key: self.start_recording(k))
            btn.pack()
            self.hotkey_rows[key] = btn
        tk.Label(box, text="Inside ClipDock: \u2191\u2193 move \u00B7 Enter paste \u00B7 Shift+Enter paste as plain text \u00B7 "
                 "1\u20139 paste that item \u00B7 Tab switch tab \u00B7 type to search \u00B7 F2 rename \u00B7 Del delete "
                 "\u00B7 Esc close", bg=BG, fg=MUTED, font=self.f_small, justify="left", anchor="w",
                 wraplength=max(200, self.w - 50)).pack(fill="x", padx=14, pady=(4, 0))

        # --- appearance
        section("Appearance")
        chips("Theme", [("Night", "dark"), ("Day", "light")], self.theme,
              lambda v: self.apply_theme(v, self.cfg["accent"]) if v != self.theme else None)
        f = tk.Frame(box, bg=CARD, padx=12, pady=8)
        f.pack(fill="x", padx=10, pady=2)
        tk.Label(f, text="Accent colour", bg=CARD, fg=FG, font=self.f_body).pack(anchor="w")
        sw = tk.Frame(f, bg=CARD)
        sw.pack(anchor="w", pady=(6, 0))
        current = self.cfg["accent"] or PALETTES[self.theme]["ACCENT"]
        for col in ACCENT_CHOICES:
            s = tk.Label(sw, text="\u2713" if col.lower() == current.lower() else "  ", bg=col, fg=WHITE,
                         font=self.f_small, width=3, cursor="hand2")
            s.pack(side="left", padx=2)
            s.bind("<Button-1>", lambda e, c=col: self.apply_theme(self.theme, c))
        reset = self.button(sw, "Default", lambda: self.apply_theme(self.theme, ""))
        reset.pack(side="left", padx=(8, 0))
        slider("Opacity", "opacity", 40, 100, lambda: self.root.attributes("-alpha", self.cfg["opacity"] / 100), "%")
        slider("Text size", "font_size", 8, 14, self.on_font_change)

        # --- history
        section("History")
        chips("History size", [(str(n), n) for n in (50, 100, 200, 500, 1000)], self.cfg["history_limit"],
              self.set_history_limit, "How many unpinned items to keep")
        chips("Paste stack order", [("First in, first out", "fifo"), ("Last in, first out", "lifo")],
              self.cfg["stack_order"], self.set_stack_order)

        # --- backup & sync
        section("Backup & sync")
        right = row("Backup file", "Text items, names, pins and snippets (images stay on this PC)")
        self.button(right, "Export\u2026", self.export_backup).pack(side="left", padx=2)
        self.button(right, "Import\u2026", self.import_backup).pack(side="left", padx=2)
        right = row("Sync folder", self.cfg["sync_dir"] or "Off \u2014 choose a OneDrive / Dropbox folder to share "
                    "history between PCs")
        self.button(right, "Choose\u2026", self.choose_sync_dir).pack(side="left", padx=2)
        self.button(right, "OneDrive", self.use_onedrive).pack(side="left", padx=2)
        if self.cfg["sync_dir"]:
            self.button(right, "Off", lambda: self.set_sync_dir("")).pack(side="left", padx=2)
            self.button(right, "Sync now", lambda: (self.sync_pull(announce=True), self.sync_push())).pack(
                side="left", padx=2)

        # --- help
        section("Help & updates")
        right = row(f"ClipDock v{VERSION}", "Hover any button to see what it does")
        self.button(right, "What's new", self.show_whatsnew).pack(side="left", padx=2)
        self.button(right, "Check for updates", self.on_update_button).pack(side="left", padx=2)
        right = row("Feedback", "Report a bug, suggest a feature, or vote on ideas")
        fb = self.button(right, "Send feedback", lambda: None, primary=True)
        fb.pack()
        fb.bind("<Button-1>", lambda e: self.open_feedback_menu(fb))
        right = row("Data folder", "History, settings and the log file live here")
        self.button(right, "Open", lambda: os.startfile(DATA_DIR) if os.path.isdir(DATA_DIR) else None).pack()
        if self.host and self.host.error:
            tk.Label(box, text="Note: " + self.host.error, bg=BG, fg=DANGER, font=self.f_small, anchor="w",
                     wraplength=max(200, self.w - 50), justify="left").pack(fill="x", padx=14, pady=(8, 0))
        tk.Frame(box, bg=BG, height=16).pack()

    def set_autostart_ui(self, enable):
        ok = win.set_autostart(enable)
        if not ok:
            self.flash_status("Couldn't change the start-up setting")
        return enable if ok else (not enable)

    def set_topmost(self, on):
        self.root.attributes("-topmost", on)
        return bool(on)

    def on_font_change(self):
        self.apply_fonts()
        for _, b in self.tab_btns.items():
            b.config(font=self.f_body)

    def set_history_limit(self, n):
        self.cfg["history_limit"] = n
        self.enforce_limits()
        self.save()
        self.save_settings()

    def set_stack_order(self, v):
        self.cfg["stack_order"] = v
        self.save_settings()

    # ---- hotkey recording
    def start_recording(self, key):
        self.recording = key
        btn = self.hotkey_rows.get(key)
        if btn:
            btn.config(text="Press keys\u2026 (Esc cancels)", bg=ACCENT, fg=WHITE)
        self.activate_keyboard()

    def record_key(self, e):
        key = self.recording
        ks = e.keysym
        if ks in ("Control_L", "Control_R", "Shift_L", "Shift_R", "Alt_L", "Alt_R", "Meta_L", "Meta_R",
                  "Super_L", "Super_R", "Caps_Lock"):
            return
        if ks == "Escape":
            self.stop_recording()
            return
        name = core.keysym_to_keyname(ks)
        mods = (core.MOD_CONTROL if e.state & 0x4 else 0) | (core.MOD_SHIFT if e.state & 0x1 else 0) \
            | (core.MOD_ALT if e.state & 0x20000 else 0)
        if not name or not mods:
            btn = self.hotkey_rows.get(key)
            if btn:
                btn.config(text="Use Ctrl/Alt + a letter, digit or F-key")
            return
        combo = core.format_hotkey(mods, core.parse_hotkey("ctrl+" + name)[1])
        other = "stack_hotkey" if key == "hotkey" else "hotkey"
        if combo == self.cfg[other]:
            btn = self.hotkey_rows.get(key)
            if btn:
                btn.config(text="Already used by the other shortcut")
            return
        self.cfg[key] = combo
        self.save_settings()
        if self.host:
            self.host.set_hotkeys(self.hotkey_map())
        self.stop_recording()
        self.root.after(250, lambda: self.show_settings(keep_scroll=True) if self.page == "settings" else None)

    def stop_recording(self):
        self.recording = None
        if self.page == "settings":
            self.release_focus()
            self.show_settings(keep_scroll=True)

    # ---- backup / sync
    def run_dialog(self, fn, **kw):
        self.root.attributes("-topmost", False)
        try:
            return fn(**kw)
        finally:
            self.root.attributes("-topmost", self.cfg["always_on_top"])

    def backup_data(self):
        return {"app": "ClipDock", "version": VERSION, "saved": time.time(),
                "items": [i for i in self.items if i.get("kind", "text") != "image"],
                "snippets": self.snippets}

    def export_backup(self):
        path = self.run_dialog(filedialog.asksaveasfilename, defaultextension=".json",
                               filetypes=[("ClipDock backup", "*.json")],
                               initialfile=time.strftime("ClipDock-backup-%Y-%m-%d.json"))
        if path:
            try:
                write_json_atomic(path, self.backup_data())
                self.flash_status("Backup saved")
            except OSError as e:
                self.flash_status(f"Couldn't save: {e.strerror or e}")

    def import_backup(self):
        path = self.run_dialog(filedialog.askopenfilename, filetypes=[("ClipDock backup", "*.json")])
        if path:
            n = self.merge_remote(read_json(path, {}))
            self.flash_status(f"Imported {n} change(s)" if n else "Nothing new to import")

    def merge_remote(self, data):
        if not isinstance(data, dict):
            return 0
        items, ch1 = core.merge_items(self.items, [i for i in data.get("items", []) if isinstance(i, dict)])
        snips, ch2 = core.merge_snippets(self.snippets, [s for s in data.get("snippets", []) if isinstance(s, dict)])
        n = (len(items) - len(self.items) if ch1 else 0) + (len(snips) - len(self.snippets) if ch2 else 0)
        if ch1:
            self.items = items
            self.enforce_limits()
            try:
                write_json_atomic(DATA_FILE, self.items)
            except OSError:
                pass
        if ch2:
            self.snippets = snips
            try:
                write_json_atomic(SNIPPETS_FILE, self.snippets)
            except OSError:
                pass
        if ch1 or ch2:
            if self.page == "list":
                self.render(keep_scroll=True)
            return max(n, 1)
        return 0

    def sync_file(self):
        d = self.cfg.get("sync_dir")
        return os.path.join(d, SYNC_NAME) if d else ""

    def schedule_sync(self):
        if self.cfg.get("sync_dir") and not self._sync_job:
            self._sync_job = self.root.after(4000, self.sync_push)

    def sync_push(self):
        self._sync_job = None
        path = self.sync_file()
        if not path:
            return
        try:
            write_json_atomic(path, self.backup_data())
            self.sync_mtime = os.path.getmtime(path)
        except OSError as e:
            log(f"sync_push: {e}")

    def sync_pull(self, announce=False):
        path = self.sync_file()
        if not path or not os.path.exists(path):
            return
        try:
            mt = os.path.getmtime(path)
            if mt == self.sync_mtime and not announce:
                return
            self.sync_mtime = mt
            n = self.merge_remote(read_json(path, {}))
            if announce:
                self.flash_status(f"Synced {n} change(s)" if n else "Already up to date")
            elif n:
                self.flash_status(f"Synced {n} change(s) from another PC")
        except OSError as e:
            log(f"sync_pull: {e}")

    def set_sync_dir(self, path):
        self.cfg["sync_dir"] = path
        self.save_settings()
        if path:
            self.sync_pull(announce=True)
            self.sync_push()
        self.show_settings(keep_scroll=True)

    def choose_sync_dir(self):
        path = self.run_dialog(filedialog.askdirectory, title="Choose a folder that syncs between your PCs")
        if path:
            self.set_sync_dir(os.path.normpath(path))

    def use_onedrive(self):
        base = os.environ.get("OneDrive") or os.environ.get("OneDriveConsumer") or os.environ.get("OneDriveCommercial")
        if not base or not os.path.isdir(base):
            self.flash_status("OneDrive folder not found \u2014 use Choose\u2026")
            return
        folder = os.path.join(base, "ClipDock")
        os.makedirs(folder, exist_ok=True)
        self.set_sync_dir(folder)

    # ---- snippet editor
    def open_snippet_editor(self, snip=None, prefill=None):
        self.open_page("editor", lambda page: self.build_editor(page, snip, prefill))

    def build_editor(self, page, snip, prefill):
        self.page_header(page, "Edit snippet" if snip else "New snippet")
        box = tk.Frame(page, bg=BG)
        box.pack(fill="both", expand=True, padx=12)
        self.bind_drag(box)

        def field(label):
            tk.Label(box, text=label, bg=BG, fg=MUTED, font=self.f_small, anchor="w").pack(fill="x", pady=(8, 2))

        field("Name")
        name = tk.Entry(box, bg=CARD, fg=FG, insertbackground=FG, bd=0, relief="flat", font=self.f_body)
        name.pack(fill="x", ipady=5)
        field("Folder (optional) \u2014 used to group snippets")
        tag = tk.Entry(box, bg=CARD, fg=FG, insertbackground=FG, bd=0, relief="flat", font=self.f_body)
        tag.pack(fill="x", ipady=5)
        field("Text")
        text = tk.Text(box, height=7, bg=CARD, fg=FG, insertbackground=FG, bd=0, relief="flat", font=self.f_body,
                       wrap="word", padx=6, pady=6, undo=True)
        text.pack(fill="both", expand=True)
        vars_row = tk.Frame(box, bg=BG)
        vars_row.pack(fill="x", pady=(6, 0))
        tk.Label(vars_row, text="Insert:", bg=BG, fg=MUTED, font=self.f_small).pack(side="left")
        for v in core.VARIABLES:
            c = tk.Label(vars_row, text=v, bg=CARD_HOVER, fg=ACCENT, font=self.f_small, padx=6, pady=2, cursor="hand2")
            c.pack(side="left", padx=2)
            c.bind("<Button-1>", lambda e, vv=v: (text.insert("insert", vv), text.focus_force()))
        if snip:
            name.insert(0, snip.get("name", ""))
            tag.insert(0, snip.get("tag", ""))
            text.insert("1.0", snip.get("text", ""))
        elif prefill:
            text.insert("1.0", prefill)
            name.insert(0, " ".join(prefill.split())[:30])
        msg = tk.Label(box, text="", bg=BG, fg=DANGER, font=self.f_small, anchor="w")
        msg.pack(fill="x", pady=(6, 0))
        btns = tk.Frame(box, bg=BG)
        btns.pack(fill="x", pady=(2, 10))

        def save():
            body = text.get("1.0", "end").rstrip("\n")
            if not body.strip():
                msg.config(text="Write some text for the snippet first.")
                return
            data = {"name": name.get().strip() or " ".join(body.split())[:30], "tag": tag.get().strip()[:30],
                    "text": body}
            if snip:
                snip.update(data)
            else:
                self.snippets.append({"id": hashlib.sha1(f"{time.time()}{body}".encode()).hexdigest()[:12], **data})
            self.save_snippets()
            self.tab = "snippets"
            self.close_page()

        self.button(btns, "Save", save, primary=True).pack(side="left")
        self.button(btns, "Cancel", self.close_page).pack(side="left", padx=6)
        self.activate_keyboard()
        name.focus_force()

    # ============================================================ feedback
    def feedback_url(self, kind):
        body = ("**What happened / what would you like?**\n\n\n\n**Steps or details (optional)**\n\n\n\n---\n"
                f"ClipDock v{VERSION} \u00B7 {platform.platform()} \u00B7 {self.theme} theme \u00B7 "
                f"Python {platform.python_version()}")
        title = "Bug: " if kind == "bug" else "Idea: "
        q = urllib.parse.urlencode({"title": title, "body": body, "labels": "bug" if kind == "bug" else "enhancement"})
        return f"https://github.com/{REPO}/issues/new?{q}"

    def open_feedback_menu(self, anchor):
        rows = [("Report a bug", lambda: self.open_url(self.feedback_url("bug"))),
                ("Suggest a feature", lambda: self.open_url(self.feedback_url("feature"))),
                ("Vote on ideas (Discussions)", lambda: self.open_url(f"https://github.com/{REPO}/discussions")),
                None,
                ("Send feedback from the website", lambda: self.open_url(SITE_URL.rstrip("/") + "/#feedback"))]
        self.open_popup(rows, anchor.winfo_rootx() - 150, anchor.winfo_rooty() + anchor.winfo_height() + 4)

    # ============================================================ what's new / welcome
    def startup_pages(self):
        if self.first_run:
            self.show_welcome()
        elif self.cfg["last_seen"] != VERSION:
            self.show_whatsnew()

    def mark_seen(self):
        self.cfg["last_seen"] = VERSION
        self.save_settings()

    def show_whatsnew(self):
        def build(page):
            self.page_header(page, f"What's new in v{VERSION}", self.leave_info_page)
            sf = ScrollFrame(page, self)
            sf.pack(fill="both", expand=True)
            box = sf.inner
            for line in WHATS_NEW:
                f = tk.Frame(box, bg=CARD, padx=12, pady=8)
                f.pack(fill="x", padx=10, pady=3)
                tk.Label(f, text="\u2726", bg=CARD, fg=ACCENT, font=self.f_body).pack(side="left", anchor="n")
                tk.Label(f, text=line, bg=CARD, fg=FG, font=self.f_body, justify="left", anchor="w",
                         wraplength=max(200, self.w - 90)).pack(side="left", padx=8, fill="x")
            row = tk.Frame(box, bg=BG)
            row.pack(fill="x", padx=10, pady=12)
            self.button(row, "Got it", self.leave_info_page, primary=True).pack(side="left")
            self.button(row, "Settings", self.show_settings).pack(side="left", padx=6)
        self.show_window()
        self.open_page("whatsnew", build)

    def show_welcome(self):
        tips = [f"{core.pretty_hotkey(self.cfg['hotkey'])} shows or hides ClipDock from any app.",
                "Inside: \u2191\u2193 + Enter to paste, 1\u20139 for the top items, just type to search.",
                "Right-click an item for UPPER/lower case, one line, open link, pretty-print JSON\u2026",
                "Turn on the \u2263 paste stack to copy several things and paste them back in order.",
                "Drag from anywhere to move, drag any edge to resize, \u2699 for settings.",
                "The \u2709 button sends feedback straight to GitHub."]

        def build(page):
            self.page_header(page, "Welcome to ClipDock", self.leave_info_page)
            sf = ScrollFrame(page, self)
            sf.pack(fill="both", expand=True)
            for t in tips:
                f = tk.Frame(sf.inner, bg=CARD, padx=12, pady=8)
                f.pack(fill="x", padx=10, pady=3)
                tk.Label(f, text="\u2726", bg=CARD, fg=ACCENT, font=self.f_body).pack(side="left", anchor="n")
                tk.Label(f, text=t, bg=CARD, fg=FG, font=self.f_body, justify="left", anchor="w",
                         wraplength=max(200, self.w - 90)).pack(side="left", padx=8, fill="x")
            row = tk.Frame(sf.inner, bg=BG)
            row.pack(fill="x", padx=10, pady=12)
            self.button(row, "Let's go", self.leave_info_page, primary=True).pack(side="left")
        self.open_page("welcome", build)

    def leave_info_page(self):
        self.mark_seen()
        self.close_page()

    def on_count_click(self):
        if self.update_ready:
            self.on_update_button()
        else:
            self.show_whatsnew()

    # ============================================================ updates (check + one-click install)
    @staticmethod
    def ver_tuple(v):
        try:
            return tuple(int(p) for p in str(v).strip().lstrip("v").split("."))
        except ValueError:
            return (0,)

    def on_update_button(self):
        if self.update_ready:
            self.show_update_page()
        else:
            self.check_update()

    def check_update(self, silent=False):
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
                self.flash_status("Couldn't reach the update server")
            return
        latest = str(info.get("latest", ""))
        if self.ver_tuple(latest) > self.ver_tuple(VERSION):
            self.update_ready, self.update_info = latest, info
            self.update_count()
            if not silent:
                self.show_update_page()
        elif not silent:
            self.flash_status("You're up to date \u2713")

    def show_update_page(self):
        info = self.update_info or {}
        notes = (info.get("releases") or [{}])[0].get("notes", [])

        def build(page):
            self.page_header(page, f"Update to v{self.update_ready}")
            sf = ScrollFrame(page, self)
            sf.pack(fill="both", expand=True)
            box = sf.inner
            tk.Label(box, text=f"You have v{VERSION}. The new version installs in a few seconds and keeps your "
                     "history and settings.", bg=BG, fg=MUTED, font=self.f_small, justify="left", anchor="w",
                     wraplength=max(200, self.w - 50)).pack(fill="x", padx=14, pady=(4, 8))
            for line in notes:
                f = tk.Frame(box, bg=CARD, padx=12, pady=6)
                f.pack(fill="x", padx=10, pady=2)
                tk.Label(f, text="\u2726", bg=CARD, fg=ACCENT, font=self.f_body).pack(side="left", anchor="n")
                tk.Label(f, text=line, bg=CARD, fg=FG, font=self.f_body, justify="left", anchor="w",
                         wraplength=max(200, self.w - 90)).pack(side="left", padx=8, fill="x")
            self.upd_status = tk.Label(box, text="", bg=BG, fg=MUTED, font=self.f_small, anchor="w",
                                       wraplength=max(200, self.w - 50), justify="left")
            self.upd_status.pack(fill="x", padx=14, pady=(10, 0))
            row = tk.Frame(box, bg=BG)
            row.pack(fill="x", padx=10, pady=10)
            self.upd_btn = self.button(row, "Install now", self.start_update, primary=True)
            self.upd_btn.pack(side="left")
            self.button(row, "Later", self.close_page).pack(side="left", padx=6)
            self.button(row, "Release page", lambda: self.open_url(SITE_URL)).pack(side="left")
        self.show_window()
        self.open_page("update", build)

    def start_update(self):
        if self._dl and self._dl.get("state") in ("downloading", "verifying", "launching"):
            return
        self._dl = {"state": "downloading", "pct": 0}
        self.upd_btn.config(bg=CARD_HOVER, fg=MUTED)
        threading.Thread(target=self.update_worker, daemon=True).start()

    def update_worker(self):
        try:
            info = self.update_info or {}
            base = UPDATE_URL.rsplit("/", 1)[0] + "/"
            url = urllib.parse.urljoin(base, info.get("download", "downloads/ClipDock-latest.zip"))
            tmp = tempfile.mkdtemp(prefix="ClipDock-update-")
            zpath = os.path.join(tmp, "ClipDock.zip")
            req = urllib.request.Request(url, headers={"User-Agent": f"ClipDock/{VERSION}"})
            with urllib.request.urlopen(req, timeout=25) as r, open(zpath, "wb") as f:
                total = int(r.headers.get("Content-Length") or 0)
                got = 0
                while True:
                    chunk = r.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
                    self._dl = {"state": "downloading", "pct": int(got * 100 / total) if total else 0}
            self._dl = {"state": "verifying"}
            want = str(info.get("sha256", "")).lower()
            if want:
                h = hashlib.sha256()
                with open(zpath, "rb") as f:
                    for block in iter(lambda: f.read(1 << 20), b""):
                        h.update(block)
                if h.hexdigest() != want:
                    raise ValueError("The download did not match its checksum. If you just published a release, "
                                     "wait a few minutes and try again.")
            with zipfile.ZipFile(zpath) as z:
                root = os.path.realpath(tmp)
                for member in z.namelist():
                    if not os.path.realpath(os.path.join(tmp, member)).startswith(root):
                        raise ValueError("The download looks unsafe.")
                z.extractall(tmp)
            folder = os.path.join(tmp, "ClipDock")
            if not os.path.exists(os.path.join(folder, "install_shortcut.bat")):
                raise ValueError("The download is missing its installer.")
            self._dl = {"state": "launching"}
            subprocess.Popen(["cmd.exe", "/c", "install_shortcut.bat", "/silent"], cwd=folder,
                             creationflags=0x08000000 | 0x00000200, close_fds=True)
            self._dl = {"state": "done"}
        except Exception as e:
            log(f"update_worker: {e}")
            self._dl = {"state": "error", "msg": str(e)}

    def refresh_update_page(self):
        st = self._dl
        if not st:
            return
        text = {"downloading": f"Downloading\u2026 {st.get('pct', 0)}%", "verifying": "Checking the download\u2026",
                "launching": "Installing\u2026", "done": "Installing the new version \u2014 ClipDock will restart "
                "by itself.", "error": "Couldn't update: " + st.get("msg", "")}.get(st["state"], "")
        if self.page == "update" and getattr(self, "upd_status", None):
            try:
                self.upd_status.config(text=text, fg=DANGER if st["state"] == "error" else MUTED)
                if st["state"] == "error":
                    self.upd_btn.config(bg=ACCENT, fg=WHITE)
            except tk.TclError:
                pass
        if st["state"] == "error":
            self._dl = None
        elif st["state"] == "done":
            self._dl = None
            self.root.after(1500, self.quit_app)

    # ============================================================ run
    def run(self):
        self.root.mainloop()


_mutex = None


def already_running():
    """Named mutex so double-clicking the app twice doesn't open two docks."""
    global _mutex
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "ClipDock_SingleInstance")
    return ctypes.windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


if __name__ == "__main__":
    if already_running():
        ctypes.windll.user32.MessageBoxW(None, "ClipDock is already running.", "ClipDock", 0x40)
        sys.exit(0)
    try:
        ClipDock().run()
    except Exception as exc:  # leave a trace for the feedback button / log file
        log(f"fatal: {type(exc).__name__}: {exc}")
        raise
