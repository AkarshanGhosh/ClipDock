"""
ClipDock core logic - pure Python, no Windows APIs, so it is easy to test anywhere.

* text transforms (UPPER, lower, Title, join lines ...)
* smart detection (URL / email / JSON / colour) and JSON helpers
* snippet variables ({date}, {time}, {clipboard} ...)
* hotkey parsing / formatting
* history + snippet merge (used for backup import and OneDrive-style sync)
* clipboard image (DIB) -> PNG + thumbnail, with no third-party packages
"""
import datetime
import getpass
import hashlib
import json
import re
import struct
import zlib

# --------------------------------------------------------------------------- text transforms


def t_trim(s):
    return "\n".join(line.strip() for line in s.strip().splitlines())


def t_upper(s):
    return s.upper()


def t_lower(s):
    return s.lower()


def t_title(s):
    return re.sub(r"[A-Za-z0-9']+", lambda m: m.group(0).capitalize(), s)


def t_oneline(s):
    return re.sub(r"\s+", " ", s).strip()


def t_noblank(s):
    return "\n".join(line for line in s.splitlines() if line.strip())


def t_spaces(s):
    return "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in s.splitlines())


# (menu label, function) - shown in the item menu as "Paste as ..."
TRANSFORMS = [
    ("Plain text (trimmed)", t_trim),
    ("UPPERCASE", t_upper),
    ("lowercase", t_lower),
    ("Title Case", t_title),
    ("Join into one line", t_oneline),
    ("Remove blank lines", t_noblank),
    ("Remove extra spaces", t_spaces),
]

# --------------------------------------------------------------------------- smart detection
URL_RE = re.compile(r"^(https?://|www\.)\S+$", re.I)
EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")
COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def detect(text):
    """Return 'url' | 'email' | 'json' | 'color' | None for a copied text."""
    s = (text or "").strip()
    if not s or len(s) > 20000:
        return None
    if "\n" not in s:
        if URL_RE.match(s):
            return "url"
        if EMAIL_RE.match(s):
            return "email"
        if COLOR_RE.match(s):
            return "color"
    if s[0] in "{[" and s[-1] in "}]":
        try:
            json.loads(s)
            return "json"
        except ValueError:
            return None
    return None


def url_of(text):
    s = text.strip()
    return s if s.lower().startswith("http") else "https://" + s


def json_pretty(text):
    return json.dumps(json.loads(text), indent=2, ensure_ascii=False)


def json_minify(text):
    return json.dumps(json.loads(text), separators=(",", ":"), ensure_ascii=False)


# --------------------------------------------------------------------------- snippet variables
_VAR = re.compile(r"\{(date|time|datetime|day|month|year|weekday|clipboard|user)(?::([^}]*))?\}")
VARIABLES = ["{date}", "{time}", "{datetime}", "{weekday}", "{clipboard}", "{user}"]


def expand_snippet(text, clipboard="", now=None):
    """Replace {date}, {time}, {clipboard} ... in a snippet. {date:%d/%m/%Y} accepts a strftime format."""
    now = now or datetime.datetime.now()

    def rep(m):
        key, fmt = m.group(1), m.group(2)
        try:
            if key == "date":
                return now.strftime(fmt or "%Y-%m-%d")
            if key == "time":
                return now.strftime(fmt or "%H:%M")
            if key == "datetime":
                return now.strftime(fmt or "%Y-%m-%d %H:%M")
            if key == "day":
                return now.strftime("%d")
            if key == "month":
                return now.strftime("%B")
            if key == "year":
                return now.strftime("%Y")
            if key == "weekday":
                return now.strftime("%A")
            if key == "clipboard":
                return clipboard
            if key == "user":
                return getpass.getuser()
        except (ValueError, KeyError, OSError):
            return m.group(0)
        return m.group(0)

    return _VAR.sub(rep, text)


# --------------------------------------------------------------------------- hotkeys
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN = 0x1, 0x2, 0x4, 0x8
_MOD_NAMES = {"alt": MOD_ALT, "ctrl": MOD_CONTROL, "control": MOD_CONTROL, "shift": MOD_SHIFT, "win": MOD_WIN}
_NAMED_VK = {
    "space": 0x20, "enter": 0x0D, "tab": 0x09, "backspace": 0x08, "insert": 0x2D, "delete": 0x2E,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
}
_VK_NAME = {v: k for k, v in _NAMED_VK.items()}
_KEYSYM_NAMES = {
    "space": "space", "Return": "enter", "Tab": "tab", "BackSpace": "backspace", "Insert": "insert",
    "Delete": "delete", "Home": "home", "End": "end", "Prior": "pageup", "Next": "pagedown",
    "Left": "left", "Up": "up", "Right": "right", "Down": "down",
}


def parse_hotkey(text):
    """'ctrl+alt+v' -> (modifiers, virtual-key) or None if it is not a valid combination."""
    mods, key = 0, None
    for part in (text or "").lower().replace(" ", "").split("+"):
        if not part:
            return None
        if part in _MOD_NAMES:
            mods |= _MOD_NAMES[part]
        elif key is None:
            key = part
        else:
            return None
    if key is None or mods == 0:
        return None
    if len(key) == 1 and (key.isalpha() or key.isdigit()):
        vk = ord(key.upper())
    elif re.fullmatch(r"f([1-9]|1[0-9]|2[0-4])", key):
        vk = 0x70 + int(key[1:]) - 1
    elif key in _NAMED_VK:
        vk = _NAMED_VK[key]
    else:
        return None
    return mods, vk


def format_hotkey(mods, vk):
    parts = []
    for name, bit in (("ctrl", MOD_CONTROL), ("alt", MOD_ALT), ("shift", MOD_SHIFT), ("win", MOD_WIN)):
        if mods & bit:
            parts.append(name)
    if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
        parts.append(chr(vk).lower())
    elif 0x70 <= vk <= 0x87:
        parts.append(f"f{vk - 0x70 + 1}")
    else:
        parts.append(_VK_NAME.get(vk, f"vk{vk}"))
    return "+".join(parts)


def pretty_hotkey(text):
    return " + ".join(p.capitalize() if len(p) > 1 else p.upper() for p in (text or "").split("+"))


def keysym_to_keyname(keysym):
    """Tk keysym ('v', 'F5', 'Prior' ...) -> the key part of a hotkey string, or None if unsupported."""
    if keysym in _KEYSYM_NAMES:
        return _KEYSYM_NAMES[keysym]
    if len(keysym) == 1 and (keysym.isalpha() or keysym.isdigit()):
        return keysym.lower()
    if re.fullmatch(r"F([1-9]|1[0-9]|2[0-4])", keysym):
        return keysym.lower()
    return None


# --------------------------------------------------------------------------- history / snippets merge
def item_key(it):
    return it.get("k") or it.get("t", "")


def merge_items(local, remote):
    """Union of two histories. Returns (merged list newest-first, True if `local` changed)."""
    by = {item_key(i): dict(i) for i in local}
    changed = False
    for r in remote:
        if r.get("kind") == "image" or not r.get("t"):
            continue  # images live in files on one PC only
        k = item_key(r)
        if k in by:
            cur = by[k]
            if r.get("pin") and not cur.get("pin"):
                cur["pin"], changed = True, True
            if r.get("name") and not cur.get("name"):
                cur["name"], changed = r["name"], True
            if r.get("src") and not cur.get("src"):
                cur["src"], changed = r["src"], True
            if r.get("ts", 0) > cur.get("ts", 0):
                cur["ts"], changed = r["ts"], True
        else:
            by[k] = dict(r)
            changed = True
    merged = sorted(by.values(), key=lambda i: i.get("ts", 0), reverse=True)
    return merged, changed


def merge_snippets(local, remote):
    by = {s.get("id"): dict(s) for s in local}
    changed = False
    for r in remote:
        sid = r.get("id")
        if sid and sid not in by:
            by[sid] = dict(r)
            changed = True
    return list(by.values()), changed


# --------------------------------------------------------------------------- source app names
_FRIENDLY = {
    "chrome": "Chrome", "msedge": "Edge", "firefox": "Firefox", "brave": "Brave", "opera": "Opera",
    "code": "VS Code", "winword": "Word", "excel": "Excel", "powerpnt": "PowerPoint", "outlook": "Outlook",
    "onenote": "OneNote", "notepad": "Notepad", "notepad++": "Notepad++", "explorer": "Explorer",
    "teams": "Teams", "slack": "Slack", "discord": "Discord", "whatsapp": "WhatsApp", "telegram": "Telegram",
    "windowsterminal": "Terminal", "cmd": "Command Prompt", "powershell": "PowerShell",
    "pythonw": "Python", "python": "Python", "pycharm64": "PyCharm", "devenv": "Visual Studio",
    "acrord32": "Acrobat", "spotify": "Spotify", "mspaint": "Paint", "snippingtool": "Snipping Tool",
    "screenclippinghost": "Snipping Tool",
}


def friendly_source(exe):
    base = (exe or "").strip()
    if base.lower().endswith(".exe"):
        base = base[:-4]
    if not base:
        return ""
    return _FRIENDLY.get(base.lower(), base[:1].upper() + base[1:])


# --------------------------------------------------------------------------- images (DIB -> PNG)
MAX_PIXELS = 40_000_000


def short_hash(data):
    return hashlib.sha1(data).hexdigest()[:16]


def dib_to_rgb(dib):
    """Windows clipboard DIB (24 or 32 bit) -> (width, height, [RGB row bytes, top-down]) or None."""
    if len(dib) < 40:
        return None
    size, w, h, planes, bpp, comp, _img, _x, _y, clr_used, _clr_imp = struct.unpack_from("<IiiHHIIiiII", dib, 0)
    if size < 40 or w <= 0 or h == 0 or planes != 1 or bpp not in (24, 32) or comp not in (0, 3):
        return None
    top_down = h < 0
    h = abs(h)
    if w * h > MAX_PIXELS:
        return None
    off = size + (12 if (comp == 3 and size == 40) else 0) + clr_used * 4
    stride = ((w * bpp + 31) // 32) * 4
    if len(dib) < off + stride * h:
        return None
    rows = []
    for y in range(h):
        sy = y if top_down else h - 1 - y
        src = dib[off + sy * stride: off + sy * stride + stride]
        rgb = bytearray(w * 3)
        if bpp == 32:
            rgb[0::3], rgb[1::3], rgb[2::3] = src[2:w * 4:4], src[1:w * 4:4], src[0:w * 4:4]
        else:
            rgb[0::3], rgb[1::3], rgb[2::3] = src[2:w * 3:3], src[1:w * 3:3], src[0:w * 3:3]
        rows.append(bytes(rgb))
    return w, h, rows


def png_from_rows(w, h, rows):
    raw = b"".join(b"\x00" + r for r in rows)

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 3))
            + chunk(b"IEND", b""))


def thumb_rows(w, h, rows, max_w=240, max_h=120):
    scale = max(w / max_w, h / max_h, 1.0)
    tw, th = max(1, int(w / scale)), max(1, int(h / scale))
    xs = [min(w - 1, int(x * w / tw)) * 3 for x in range(tw)]
    out = []
    for ty in range(th):
        src = rows[min(h - 1, int(ty * h / th))]
        row = bytearray(tw * 3)
        for tx, sx in enumerate(xs):
            row[tx * 3:tx * 3 + 3] = src[sx:sx + 3]
        out.append(bytes(row))
    return tw, th, out


def image_assets(dib):
    """DIB bytes -> dict(w, h, png, thumb) with PNG data for the full image and a small thumbnail, or None."""
    parsed = dib_to_rgb(dib)
    if not parsed:
        return None
    w, h, rows = parsed
    tw, th, trows = thumb_rows(w, h, rows)
    return {"w": w, "h": h, "png": png_from_rows(w, h, rows), "thumb": png_from_rows(tw, th, trows)}
