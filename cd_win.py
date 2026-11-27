"""
ClipDock Windows layer (ctypes only, no third-party packages).

* window helpers (no-activate, topmost, work area ...)
* clipboard: read images / files, write images / files, find the app that copied
* NativeHost: one background thread that owns the global hotkeys AND the tray icon
* start-with-Windows (registry Run key)

Everything here is defensive: a failure in the tray or hotkey code must never stop the clipboard
manager itself, so errors are recorded in `NativeHost.error` and the app carries on.
"""
import ctypes
import os
import queue
import sys
import threading
import time
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
shell32 = ctypes.windll.shell32

# ---------------------------------------------------------------- prototypes (64-bit safe)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.GetAncestor.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = ctypes.c_void_p
user32.SetClipboardData.argtypes = [wintypes.UINT, ctypes.c_void_p]
user32.SetClipboardData.restype = ctypes.c_void_p
user32.GetClipboardOwner.restype = wintypes.HWND
user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
kernel32.GlobalSize.argtypes = [ctypes.c_void_p]
kernel32.GlobalSize.restype = ctypes.c_size_t
kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                 ctypes.POINTER(wintypes.DWORD)]
shell32.DragQueryFileW.argtypes = [ctypes.c_void_p, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]

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
IGNORED_TARGET_CLASSES = {"Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Progman", "WorkerW", "ClipDockHost"}


# ---------------------------------------------------------------- window helpers
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


def foreground_window():
    return user32.GetForegroundWindow()


def set_foreground(hwnd):
    return user32.SetForegroundWindow(hwnd)


def send_ctrl_v():
    VK_CONTROL, VK_V, KEYUP = 0x11, 0x56, 0x0002
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    user32.keybd_event(VK_V, 0, 0, 0)
    user32.keybd_event(VK_V, 0, KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, KEYUP, 0)


VK_MODIFIERS = (0x10, 0x11, 0x12, 0x5B, 0x5C)  # Shift, Ctrl, Alt, LWin, RWin
user32.GetAsyncKeyState.restype = ctypes.c_short


def modifiers_down():
    """True while the user still holds Shift/Ctrl/Alt/Win (e.g. right after pressing a hotkey)."""
    return any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in VK_MODIFIERS)


def release_modifiers():
    """Send key-up for any held modifier so a synthetic Ctrl+V is not turned into Ctrl+Alt+V."""
    for vk in VK_MODIFIERS:
        if user32.GetAsyncKeyState(vk) & 0x8000:
            user32.keybd_event(vk, 0, 0x0002, 0)


def force_foreground(hwnd):
    """Bring our window to the front even though we are a background app (needed for keyboard mode)."""
    try:
        if user32.GetForegroundWindow() == hwnd:
            return True
        fg = user32.GetForegroundWindow()
        tid_fg = user32.GetWindowThreadProcessId(fg, None) if fg else 0
        tid_me = kernel32.GetCurrentThreadId()
        attached = bool(tid_fg and tid_fg != tid_me and user32.AttachThreadInput(tid_me, tid_fg, True))
        try:
            return bool(user32.SetForegroundWindow(hwnd))
        finally:
            if attached:
                user32.AttachThreadInput(tid_me, tid_fg, False)
    except Exception:
        return False


def clipboard_sequence():
    return user32.GetClipboardSequenceNumber()


# ---------------------------------------------------------------- clipboard: images, files, source app
CF_DIB, CF_UNICODETEXT, CF_HDROP = 8, 13, 15
GMEM_MOVEABLE = 0x0002
MAX_CLIP_BYTES = 80 * 1024 * 1024


def _open_clipboard(retries=8):
    for _ in range(retries):
        if user32.OpenClipboard(None):
            return True
        time.sleep(0.03)
    return False


def read_clipboard_nontext():
    """If the clipboard has no text, return ('image', DIB bytes) or ('files', [paths]); otherwise None."""
    try:
        if user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return None
        if user32.IsClipboardFormatAvailable(CF_HDROP):
            kind = "files"
        elif user32.IsClipboardFormatAvailable(CF_DIB):
            kind = "image"
        else:
            return None
        if not _open_clipboard():
            return None
        try:
            if kind == "files":
                h = user32.GetClipboardData(CF_HDROP)
                if not h:
                    return None
                count = shell32.DragQueryFileW(h, 0xFFFFFFFF, None, 0)
                paths = []
                for i in range(min(count, 200)):
                    n = shell32.DragQueryFileW(h, i, None, 0)
                    buf = ctypes.create_unicode_buffer(n + 1)
                    shell32.DragQueryFileW(h, i, buf, n + 1)
                    paths.append(buf.value)
                return ("files", paths) if paths else None
            h = user32.GetClipboardData(CF_DIB)
            if not h:
                return None
            size = kernel32.GlobalSize(h)
            if size <= 0 or size > MAX_CLIP_BYTES:
                return None
            ptr = kernel32.GlobalLock(h)
            if not ptr:
                return None
            try:
                data = ctypes.string_at(ptr, size)
            finally:
                kernel32.GlobalUnlock(h)
            return ("image", data)
        finally:
            user32.CloseClipboard()
    except Exception:
        return None


def _set_clipboard(fmt, data):
    if not _open_clipboard():
        return False
    try:
        user32.EmptyClipboard()
        h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not h:
            return False
        ptr = kernel32.GlobalLock(h)
        ctypes.memmove(ptr, data, len(data))
        kernel32.GlobalUnlock(h)
        if not user32.SetClipboardData(fmt, h):
            kernel32.GlobalFree(h)
            return False
        return True
    finally:
        user32.CloseClipboard()


def set_clipboard_dib(dib):
    return _set_clipboard(CF_DIB, dib)


def set_clipboard_files(paths):
    import struct
    header = struct.pack("<IiiII", 20, 0, 0, 0, 1)  # DROPFILES: offset, pt.x, pt.y, fNC, fWide
    body = ("\0".join(paths) + "\0\0").encode("utf-16-le")
    return _set_clipboard(CF_HDROP, header + body)


def clipboard_source():
    """Name of the program that last wrote to the clipboard (e.g. 'chrome.exe'), or ''."""
    try:
        hwnd = user32.GetClipboardOwner() or user32.GetForegroundWindow()
        if not hwnd:
            return ""
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return ""
        h = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(520)
            size = wintypes.DWORD(520)
            if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                return os.path.basename(buf.value)
        finally:
            kernel32.CloseHandle(h)
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------- start with Windows
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def autostart_command():
    exe = sys.executable
    if exe.lower().endswith("python.exe"):
        exe = exe[:-10] + "pythonw.exe"
    return f'"{exe}" "{os.path.abspath(sys.argv[0])}"'


def get_autostart():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, "ClipDock")
            return True
    except Exception:
        return False


def set_autostart(enabled):
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if enabled:
                winreg.SetValueEx(k, "ClipDock", 0, winreg.REG_SZ, autostart_command())
            else:
                try:
                    winreg.DeleteValue(k, "ClipDock")
                except FileNotFoundError:
                    pass
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- native host: hotkeys + tray icon
WM_NULL, WM_CLOSE, WM_DESTROY, WM_HOTKEY = 0x0000, 0x0010, 0x0002, 0x0312
WM_LBUTTONUP, WM_RBUTTONUP = 0x0202, 0x0205
WM_APP = 0x8000
WM_TRAY, WM_REREGISTER, WM_QUIT_HOST = WM_APP + 1, WM_APP + 3, WM_APP + 4
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP = 1, 2, 4
MF_STRING, MF_SEPARATOR = 0x0, 0x800
TPM_RIGHTBUTTON, TPM_NONOTIFY, TPM_RETURNCMD = 0x2, 0x80, 0x100
MOD_NOREPEAT = 0x4000

# tray menu command ids (also used by the app)
TRAY_TOGGLE, TRAY_PAUSE, TRAY_STACK, TRAY_SETTINGS, TRAY_FEEDBACK, TRAY_UPDATE, TRAY_QUIT = 1, 2, 3, 4, 5, 6, 9
HOTKEY_TOGGLE, HOTKEY_STACK = 1, 2


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT),
                ("uFlags", wintypes.UINT), ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HANDLE),
                ("szTip", wintypes.WCHAR * 128), ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD),
                ("szInfo", wintypes.WCHAR * 256), ("uTimeoutOrVersion", wintypes.UINT),
                ("szInfoTitle", wintypes.WCHAR * 64), ("dwInfoFlags", wintypes.DWORD),
                ("guidItem", GUID), ("hBalloonIcon", wintypes.HANDLE)]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", ctypes.c_void_p), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HANDLE), ("hIcon", wintypes.HANDLE),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HANDLE),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]


class NativeHost:
    """Owns a hidden window on its own thread: receives global hotkeys and tray-icon clicks and
    hands them to the Tk thread through `events` (a queue.Queue)."""

    def __init__(self, events, icon_path="", tooltip="ClipDock"):
        self.events = events
        self.icon_path = icon_path
        self.tooltip = tooltip[:127]
        self.hwnd = None
        self.error = ""
        self.tray_ok = False
        self.status = {}                       # hotkey id -> True/False (registered?)
        self.menu_state = {"paused": False, "stack": False}
        self._wanted = {}                      # hotkey id -> (mods, vk)
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._thread = None
        self._icon = None
        self._taskbar_msg = 0
        self._wndproc = None

    # ------------------------------------------------------------ public API (Tk thread)
    def start(self, hotkeys):
        self._wanted = dict(hotkeys)
        self._thread = threading.Thread(target=self._run, name="ClipDockHost", daemon=True)
        self._thread.start()
        self._ready.wait(4)

    def set_hotkeys(self, hotkeys):
        with self._lock:
            self._wanted = dict(hotkeys)
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_REREGISTER, 0, 0)

    def stop(self):
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_QUIT_HOST, 0, 0)

    # ------------------------------------------------------------ host thread
    def _run(self):
        try:
            self._setup()
        except Exception as e:  # never let the host take the app down
            self.error = f"{type(e).__name__}: {e}"
            self._ready.set()
            return
        self._ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _setup(self):
        LRESULT = ctypes.c_ssize_t
        WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        user32.DefWindowProcW.restype = LRESULT
        user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                           ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                           wintypes.HANDLE, wintypes.HANDLE, ctypes.c_void_p]
        user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.CreatePopupMenu.restype = wintypes.HANDLE
        user32.AppendMenuW.argtypes = [wintypes.HANDLE, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
        user32.TrackPopupMenu.argtypes = [wintypes.HANDLE, wintypes.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                          wintypes.HWND, ctypes.c_void_p]
        user32.DestroyMenu.argtypes = [wintypes.HANDLE]
        user32.DestroyWindow.argtypes = [wintypes.HWND]
        user32.LoadImageW.restype = wintypes.HANDLE
        user32.LoadImageW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int,
                                      ctypes.c_int, wintypes.UINT]
        shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
        kernel32.GetModuleHandleW.restype = wintypes.HANDLE
        user32.LoadIconW.restype = wintypes.HANDLE
        user32.LoadIconW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]

        def wndproc(hwnd, msg, wparam, lparam):
            try:
                if msg == WM_HOTKEY:
                    self.events.put(("hotkey", int(wparam), user32.GetForegroundWindow()))
                    return 0
                if msg == WM_TRAY:
                    ev = int(lparam) & 0xFFFF
                    if ev == WM_LBUTTONUP:
                        self.events.put(("tray_cmd", TRAY_TOGGLE))
                    elif ev == WM_RBUTTONUP:
                        self._show_menu(hwnd)
                    return 0
                if msg == WM_REREGISTER:
                    self._register_hotkeys()
                    return 0
                if msg == WM_QUIT_HOST or msg == WM_CLOSE:
                    self._teardown()
                    user32.DestroyWindow(hwnd)
                    return 0
                if msg == WM_DESTROY:
                    user32.PostQuitMessage(0)
                    return 0
                if self._taskbar_msg and msg == self._taskbar_msg:  # Explorer restarted -> re-add the icon
                    self._add_tray()
                    return 0
            except Exception as e:
                self.error = f"{type(e).__name__}: {e}"
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._wndproc = WNDPROC(wndproc)  # keep a reference so it is not garbage collected
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSW()
        wc.lpfnWndProc = ctypes.cast(self._wndproc, ctypes.c_void_p).value
        wc.hInstance = hinst
        wc.lpszClassName = "ClipDockHost"
        user32.RegisterClassW(ctypes.byref(wc))
        self.hwnd = user32.CreateWindowExW(WS_EX_TOOLWINDOW, "ClipDockHost", "ClipDockHost", 0x80000000,
                                           0, 0, 0, 0, None, None, hinst, None)
        if not self.hwnd:
            raise OSError("could not create the hidden host window")
        self._taskbar_msg = user32.RegisterWindowMessageW("TaskbarCreated")
        self._register_hotkeys()
        try:
            self._add_tray()
        except Exception as e:
            self.error = f"tray: {type(e).__name__}: {e}"

    def _register_hotkeys(self):
        with self._lock:
            wanted = dict(self._wanted)
        for hid in (HOTKEY_TOGGLE, HOTKEY_STACK):
            user32.UnregisterHotKey(self.hwnd, hid)
        for hid, (mods, vk) in wanted.items():
            self.status[hid] = bool(user32.RegisterHotKey(self.hwnd, hid, mods | MOD_NOREPEAT, vk))

    def _nid(self):
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAY
        nid.hIcon = self._icon
        nid.szTip = self.tooltip
        return nid

    def _add_tray(self):
        if self._icon is None and self.icon_path and os.path.exists(self.icon_path):
            self._icon = user32.LoadImageW(None, self.icon_path, 1, 16, 16, 0x10)  # IMAGE_ICON, LR_LOADFROMFILE
        if not self._icon:
            self._icon = user32.LoadIconW(None, 32512)  # IDI_APPLICATION fallback
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid()))
        self.tray_ok = bool(shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self._nid())))

    def _teardown(self):
        for hid in (HOTKEY_TOGGLE, HOTKEY_STACK):
            user32.UnregisterHotKey(self.hwnd, hid)
        if self.tray_ok:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid()))
            self.tray_ok = False

    def _show_menu(self, hwnd):
        st = self.menu_state
        menu = user32.CreatePopupMenu()
        rows = [(TRAY_TOGGLE, "Show / hide ClipDock"),
                (TRAY_PAUSE, "Resume capturing" if st.get("paused") else "Pause capturing"),
                (TRAY_STACK, "Paste stack: turn " + ("OFF" if st.get("stack") else "ON")),
                (TRAY_SETTINGS, "Settings"),
                (TRAY_FEEDBACK, "Send feedback"),
                (TRAY_UPDATE, "Check for updates"),
                (0, None),
                (TRAY_QUIT, "Quit ClipDock")]
        for cid, text in rows:
            if text is None:
                user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            else:
                user32.AppendMenuW(menu, MF_STRING, cid, text)
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(hwnd)  # required so the menu closes when you click elsewhere
        cmd = user32.TrackPopupMenu(menu, TPM_RETURNCMD | TPM_NONOTIFY | TPM_RIGHTBUTTON, pt.x, pt.y, 0, hwnd, None)
        user32.PostMessageW(hwnd, WM_NULL, 0, 0)
        user32.DestroyMenu(menu)
        if cmd:
            self.events.put(("tray_cmd", int(cmd)))
