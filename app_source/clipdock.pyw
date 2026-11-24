"""
ClipDock - clipboard history that docks above the Windows taskbar.

* Always on top, sits just above the taskbar (bottom-right of the work area).
* Never steals focus, so the text cursor stays where you left it.
* Click any item -> it is pasted at the cursor of the app you were using.
* Search, pin favourites, delete, pause capture, collapse to a slim bar.
* Hover any button to see what it does.
* Only one copy runs at a time.
* History is saved to %APPDATA%\\ClipDock\\history.json.

Run from source:  pythonw clipdock.pyw   (Python 3.8+ on Windows, no extra packages)
Build the app:    double-click build_app.bat once -> installs ClipDock.exe + shortcuts.
"""
import ctypes
import json
import os
import sys
import time
import threading
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


# ---------------------------------------------------------------- Theme
BG, HEADER, CARD, CARD_HOVER = "#17181c", "#1f2127", "#25272e", "#30333c"
FG, MUTED, ACCENT, DANGER, OK = "#e9eaee", "#8a8f9c", "#4f8cff", "#ff6b6b", "#3ddc97"
W, H, H_COLLAPSED, MARGIN = 380, 560, 46, 12
MAX_ITEMS, MAX_CHARS = 200, 50000

VERSION = "1.0.0"  # release.py keeps this in sync with the website
# Set once after you host the website, e.g. "https://yourname.github.io/clipdock/version.json"
UPDATE_URL = ""

DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "ClipDock")
DATA_FILE = os.path.join(DATA_DIR, "history.json")


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
            tk.Label(tip, text=text, bg="#0d0e12", fg=FG, font=("Segoe UI", 9), padx=10, pady=6,
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
        self.items = self.load()
        self.tab = "history"
        self.paused = False
        self.collapsed = False
        self.topmost = True
        self.search_active = False
        self.target = None
        self.last_seq = user32.GetClipboardSequenceNumber()
        self.skip_text, self.skip_until = None, 0.0
        self.drag = (0, 0)
        self._upd = None          # result handed over from the update-check thread
        self.update_ready = None  # newer version string, once found

        self.root = tk.Tk()
        self.root.title("ClipDock")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=BG)
        self.f_body = tkfont.Font(family="Segoe UI", size=10)
        self.f_small = tkfont.Font(family="Segoe UI", size=8)
        self.f_title = tkfont.Font(family="Segoe UI Semibold", size=11)
        self.f_icon = tkfont.Font(family="Segoe UI Symbol", size=11)

        left, top, right, bottom = work_area()
        self.root.geometry(f"{W}x{H}+{right - W - MARGIN}+{bottom - H - MARGIN}")
        self.build_ui()
        self.root.update()
        self.hwnd = user32.GetAncestor(self.root.winfo_id(), 2) or self.root.winfo_id()
        set_noactivate(self.hwnd, True)
        self.render()
        self.root.after(250, self.tick)
        if UPDATE_URL:
            self.root.after(5000, lambda: self.check_update(silent=True))

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
            w.bind("<Button-1>", self.drag_start)
            w.bind("<B1-Motion>", self.drag_move)

        self.btn_close = self.icon_btn(hdr, "\u2715", self.root.destroy)
        self.btn_collapse = self.icon_btn(hdr, "\u2014", self.toggle_collapse)
        self.btn_pin = self.icon_btn(hdr, "\u25C9", self.toggle_topmost)
        self.btn_pause = self.icon_btn(hdr, "\u25CF", self.toggle_pause)
        self.btn_update = self.icon_btn(hdr, "\u21BB", self.check_update)
        self.btn_pause.config(fg=OK)
        self.btn_pin.config(fg=ACCENT)
        Tooltip(self.root, self.btn_update,
                lambda: f"Version {self.update_ready} is available\nClick to open the download page" if self.update_ready
                else f"ClipDock v{VERSION}\nClick to check for updates")
        Tooltip(self.root, self.btn_close, "Close ClipDock")
        Tooltip(self.root, self.btn_collapse,
                lambda: "Expand the window" if self.collapsed else "Collapse to a slim bar")
        Tooltip(self.root, self.btn_pin,
                lambda: "Always on top: ON\nClick to let other windows cover it" if self.topmost
                else "Always on top: OFF\nClick to keep it above other windows")
        Tooltip(self.root, self.btn_pause,
                lambda: "Capture paused\nClick to resume saving copied text" if self.paused
                else "Capturing your clipboard\nClick to pause saving")
        Tooltip(self.root, title, f"ClipDock v{VERSION} \u2014 drag the header to move it")
        Tooltip(self.root, self.count_lbl, "Total items saved in your history")

        self.body = tk.Frame(self.root, bg=BG)
        self.body.pack(fill="both", expand=True)

        tabs = tk.Frame(self.body, bg=BG)
        tabs.pack(fill="x", padx=10, pady=(10, 4))
        self.tab_btns = {}
        for key, label in (("history", "History"), ("pinned", "Pinned")):
            b = tk.Label(tabs, text=label, font=self.f_body, padx=14, pady=4, cursor="hand2")
            b.pack(side="left", padx=(0, 6))
            b.bind("<Button-1>", lambda e, k=key: self.set_tab(k))
            Tooltip(self.root, b, "Everything you copied, newest first" if key == "history"
                    else "Only the items you starred \u2014 they are never auto-deleted")
            self.tab_btns[key] = b

        sbox = tk.Frame(self.body, bg=CARD, padx=8, pady=5)
        sbox.pack(fill="x", padx=10, pady=(2, 6))
        tk.Label(sbox, text="\u2315", bg=CARD, fg=MUTED, font=self.f_icon).pack(side="left")
        self.query = tk.StringVar()
        self.query.trace_add("write", lambda *a: self.render())
        self.search = tk.Entry(sbox, textvariable=self.query, bg=CARD, fg=FG, bd=0,
                               insertbackground=FG, font=self.f_body, relief="flat")
        self.search.pack(side="left", fill="x", expand=True, padx=6)
        self.search.bind("<Button-1>", self.activate_search)
        self.search.bind("<Escape>", lambda e: self.release_search())
        self.search.bind("<FocusOut>", lambda e: self.release_search())
        Tooltip(self.root, self.search, "Search your history\nClick to type, press Esc to go back to your app")

        wrap = tk.Frame(self.body, bg=BG)
        wrap.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(wrap, bg=BG, highlightthickness=0, bd=0)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self.win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.pack(fill="both", expand=True)
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.win, width=e.width))
        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self.on_wheel))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

        foot = tk.Frame(self.body, bg=HEADER, height=34)
        foot.pack(fill="x", side="bottom")
        foot.pack_propagate(False)
        tk.Label(foot, text="Click an item to paste at your cursor", bg=HEADER, fg=MUTED,
                 font=self.f_small).pack(side="left", padx=10)
        clear = tk.Label(foot, text="Clear history", bg=HEADER, fg=DANGER, font=self.f_small, cursor="hand2")
        clear.pack(side="right", padx=10)
        clear.bind("<Button-1>", lambda e: self.clear_history())
        Tooltip(self.root, clear, "Delete all history\n(pinned items are kept)")

    def icon_btn(self, parent, text, cmd):
        b = tk.Label(parent, text=text, bg=HEADER, fg=MUTED, font=self.f_icon, cursor="hand2", padx=7)
        b.pack(side="right")
        b.bind("<Button-1>", lambda e: cmd())
        return b

    # ------------------------------------------------------------ window behaviour
    def drag_start(self, e):
        self.drag = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())

    def drag_move(self, e):
        self.root.geometry(f"+{e.x_root - self.drag[0]}+{e.y_root - self.drag[1]}")

    def toggle_collapse(self):
        self.collapsed = not self.collapsed
        bottom = self.root.winfo_y() + self.root.winfo_height()
        h = H_COLLAPSED if self.collapsed else H
        if self.collapsed:
            self.body.pack_forget()
        else:
            self.body.pack(fill="both", expand=True)
        self.root.geometry(f"{W}x{h}+{self.root.winfo_x()}+{bottom - h}")

    def toggle_topmost(self):
        self.topmost = not self.topmost
        self.root.attributes("-topmost", self.topmost)
        self.btn_pin.config(fg=ACCENT if self.topmost else MUTED)

    def toggle_pause(self):
        self.paused = not self.paused
        self.btn_pause.config(fg=DANGER if self.paused else OK)
        self.last_seq = user32.GetClipboardSequenceNumber()

    def set_tab(self, key):
        self.tab = key
        self.render()

    def on_wheel(self, e):
        self.canvas.yview_scroll(int(-e.delta / 120) * 2, "units")

    # ------------------------------------------------------------ search focus (only time we take focus)
    def activate_search(self, e=None):
        self.search_active = True
        set_noactivate(self.hwnd, False)
        user32.SetForegroundWindow(self.hwnd)
        self.search.focus_force()

    def release_search(self):
        if not self.search_active:
            return
        self.search_active = False
        set_noactivate(self.hwnd, True)
        self.root.focus_set()
        if self.target:
            user32.SetForegroundWindow(self.target)

    # ------------------------------------------------------------ clipboard capture
    def tick(self):
        try:
            fg = user32.GetForegroundWindow()
            if fg and fg != self.hwnd and not self.search_active and window_class(fg) not in IGNORED_TARGET_CLASSES:
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
        pinned = False
        for it in self.items:
            if it["t"] == text:
                pinned = it.get("pin", False)
                self.items.remove(it)
                break
        self.items.insert(0, {"t": text, "ts": time.time(), "pin": pinned})
        unpinned = [i for i in self.items if not i.get("pin")]
        for extra in unpinned[MAX_ITEMS:]:
            self.items.remove(extra)
        self.save()
        self.render()

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
        if self.search_active:
            self.release_search()
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
        self.render()

    def delete(self, it):
        if it in self.items:
            self.items.remove(it)
        self.save()
        self.render()

    def clear_history(self):
        self.items = [i for i in self.items if i.get("pin")]
        self.save()
        self.render()

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

    def render(self):
        for k, b in self.tab_btns.items():
            on = k == self.tab
            b.config(bg=ACCENT if on else CARD, fg="#ffffff" if on else MUTED)
        n_pin = sum(1 for i in self.items if i.get("pin"))
        self.tab_btns["pinned"].config(text=f"Pinned ({n_pin})")
        self.update_count()

        for w in self.inner.winfo_children():
            w.destroy()
        q = self.query.get().strip().lower()
        shown = [i for i in self.items if (self.tab == "history" or i.get("pin")) and (not q or q in i["t"].lower())]
        if not shown:
            msg = "Nothing pinned yet.\nTap \u2606 on an item to keep it here." if self.tab == "pinned" and not q \
                else ("No matches." if q else "Copy something (Ctrl+C) and it will appear here.")
            tk.Label(self.inner, text=msg, bg=BG, fg=MUTED, font=self.f_body, justify="center",
                     pady=40).pack(fill="x")
        for it in shown[:120]:
            self.make_card(it)
        self.canvas.yview_moveto(0)

    def make_card(self, it):
        card = tk.Frame(self.inner, bg=CARD, cursor="hand2", padx=10, pady=8)
        card.pack(fill="x", padx=10, pady=3)
        card.columnconfigure(0, weight=1)
        txt = tk.Label(card, text=self.preview(it["t"]), bg=CARD, fg=FG, font=self.f_body,
                       justify="left", anchor="w", wraplength=W - 120)
        txt.grid(row=0, column=0, sticky="we")
        meta = tk.Label(card, text=f"{self.ago(it['ts'])}  \u00B7  {len(it['t'])} chars", bg=CARD,
                        fg=MUTED, font=self.f_small, anchor="w")
        meta.grid(row=1, column=0, sticky="w", pady=(2, 0))
        pinned = it.get("pin", False)
        pin = tk.Label(card, text="\u2605" if pinned else "\u2606", bg=CARD, font=self.f_icon,
                       fg=ACCENT if pinned else MUTED, cursor="hand2", padx=4)
        pin.grid(row=0, column=1, sticky="ne")
        dele = tk.Label(card, text="\u2715", bg=CARD, fg=MUTED, font=self.f_small, cursor="hand2", padx=4)
        dele.grid(row=0, column=2, sticky="ne")
        pin.bind("<Button-1>", lambda e, i=it: self.toggle_pin(i))
        dele.bind("<Button-1>", lambda e, i=it: self.delete(i))
        dele.bind("<Enter>", lambda e, w=dele: w.config(fg=DANGER))
        dele.bind("<Leave>", lambda e, w=dele: w.config(fg=MUTED))

        parts = (card, txt, meta, pin, dele)
        for w in (card, txt, meta):
            w.bind("<Button-1>", lambda e, i=it: self.paste(i))
            Tooltip(self.root, w, "Click to paste this at your cursor", delay=700)
        Tooltip(self.root, pin, "Unpin this item" if pinned else "Pin \u2014 keep this item permanently")
        Tooltip(self.root, dele, "Delete this item")

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
