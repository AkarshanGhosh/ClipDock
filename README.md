<div align="center">

<img src="docs/logo.png" alt="ClipDock logo" width="110" height="110">

# ClipDock

**Your clipboard, with a memory.**
Clipboard history that docks above your taskbar and pastes exactly where your cursor is.

<p>
  <img alt="Version" src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2FAkarshanGhosh%2FClipDock%2Fmain%2Fversion.json&query=%24.latest&label=version&color=4f8cff&style=for-the-badge">
  <img alt="Platform" src="https://img.shields.io/badge/Windows-10%20%7C%2011-0078D4?style=for-the-badge&logo=windows&logoColor=white">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.8%2B-3776AB?style=for-the-badge&logo=python&logoColor=white">
  <img alt="Price" src="https://img.shields.io/badge/price-free-3ddc97?style=for-the-badge">
  <img alt="No sign-up" src="https://img.shields.io/badge/no%20sign--up-%E2%9C%93-8b5cf6?style=for-the-badge">
  <img alt="Hosted on Cloudflare" src="https://img.shields.io/badge/hosted%20on-Cloudflare-F38020?style=for-the-badge&logo=cloudflare&logoColor=white">
</p>

[**Download**](#download) &nbsp;·&nbsp; [Features](#features) &nbsp;·&nbsp; [Install](#install) &nbsp;·&nbsp; [Update](#updating) &nbsp;·&nbsp; [Troubleshooting](#troubleshooting) &nbsp;·&nbsp; [For maintainers](#maintainers)

<br>

<img src="docs/banner.jpg" alt="ClipDock website" width="900">

</div>

<br>

## ✨ What is ClipDock?

Copy something, copy something else, then realise you needed the first one. ClipDock remembers
**everything you copy** in a small always-on-top window above the Windows taskbar. Click any item
and it is pasted **right where your text cursor is**, in whichever app you were using.

No account. No cloud. No tracking. Just your clipboard, with a memory.

<div align="center">
  <img src="docs/app-preview.png" alt="ClipDock docked window pasting into a notepad" width="520">
</div>

<a id="features"></a>

## 🚀 Features

| | Feature | What it does |
|---|---|---|
| 🖱️ | **Click to paste** | Click an item and it lands at your cursor, in any app. |
| 📌 | **Docked above the taskbar** | Always on top and always in reach, or collapse it to a slim bar. |
| 🎯 | **Never steals focus** | Your text cursor stays exactly where you left it while you click around ClipDock. |
| ↔️ | **Move & resize freely** | Drag from *anywhere* to move it, and drag any edge or corner to resize. Size and position are remembered. |
| 🏷️ | **Name your clips** | Give any item a name like “Work email”, then find it by that name. |
| 🔍 | **Instant search** | Search by what you copied **or** by the name you gave it. |
| 🌗 | **Day & night mode** | One click switches between a light and a dark look, and ClipDock remembers it. |
| ⭐ | **Pin favourites** | Star snippets you reuse daily. Pinned items are never auto-deleted. |
| 💡 | **Hover hints** | Hover any button to see what it does. |
| 🔄 | **Update check** | A small `Update v1.x.x ↗` note appears when a new version is out. |
| 🔒 | **Private by design** | History is stored only on your PC. Nothing is uploaded. |

<div align="center">
  <img src="docs/features.jpg" alt="ClipDock feature overview" width="820">
</div>

<a id="download"></a>

## ⬇️ Download

Get the latest version from the website: **https://YOUR-SITE-ADDRESS** (the *Download for Windows* button).

> The download button always points to `downloads/ClipDock-latest.zip`, so it is always the newest version.
> Older versions are kept in [`downloads/`](downloads/) as `ClipDock-vX.Y.Z.zip`.

<a id="install"></a>

## ⚡ Install in 30 seconds

<div align="center">
  <img src="docs/how-it-works.jpg" alt="Three install steps" width="820">
</div>

1. **Install Python** (free, one time) from [python.org](https://www.python.org/downloads/), and tick **“Add python.exe to PATH”**.
2. **Unzip** the download and double-click **`install_shortcut.bat`**.
3. **Open ClipDock** from your Desktop or Start menu. Copy as usual with `Ctrl + C`, then click an item to paste it.

> 💡 Right-click the ClipDock shortcut → **Pin to taskbar** for one-click launching.

### 🎮 Quick controls

| I want to… | Do this |
|---|---|
| **Paste** an item | Click it. It pastes where your text cursor is. |
| **Move** the window | Drag from any empty spot, or press-and-drag an item. |
| **Resize** the window | Drag any edge or corner. The minimum size is 300 × 260. |
| **Name** an item | Click the pencil ✎, type a name, press **Enter** (**Esc** cancels). |
| **Find** an item | Click the search box and type part of its text or its name. |
| **Pin** an item | Click the star ☆. Pinned items live under the *Pinned* tab. |
| **Switch day / night** | Click the ☀ / ☾ button in the header. |
| **Pause** capturing | Click the ● button (for example, when copying a password). |
| **Collapse** to a slim bar | Click the — button. |

<a id="updating"></a>

## 🔄 Updating

Download the newest zip, unzip it, and run **`install_shortcut.bat`** again. It replaces the old
files and **keeps your clipboard history**. ClipDock also checks for updates by itself; when one is
ready, an **Update ↗** note appears in its header and clicking it opens the download page.

<a id="troubleshooting"></a>

## 🧰 Troubleshooting

| Problem | Fix |
|---|---|
| **Windows says a file is blocked** (Smart App Control) | Smart App Control blocks unsigned `.exe` files. ClipDock is **not** an .exe; it runs through Python, so use `install_shortcut.bat` from the zip. |
| **“Python was not found”** | Install Python from python.org and tick *Add python.exe to PATH*, then run the installer again. |
| **Nothing pastes in an admin / elevated app** | Windows blocks normal programs from typing into admin windows. Start ClipDock as administrator too. |
| **I copied a password** | History (including item names) is stored in plain text on your PC. Press the **●** pause button before copying sensitive things, or use **Clear history**. |
| **The window is off-screen or the wrong size** | Close ClipDock and delete `%APPDATA%\ClipDock\settings.json`. It will reopen above the taskbar at the default size. |
| **Shortcut wasn't created** | The installer prints 4 manual steps. It takes about 30 seconds. |
| **How do I uninstall?** | Delete the ClipDock shortcut and the folder `%LOCALAPPDATA%\ClipDock`. Delete `%APPDATA%\ClipDock` too to remove your history. |

<div align="center">
  <img src="docs/mobile.png" alt="ClipDock website on mobile" width="260">
  <br><sub>The website works on phones, too.</sub>
</div>

---

<a id="maintainers"></a>

# 🛠 For maintainers

Everything below is for whoever publishes ClipDock. It is **not** needed to just use the app.

## 📁 Project structure

```text
ClipDock/
├── index.html · style.css · app.js    the website (no build step, no sign-up)
├── version.json · version.js          current version + changelog (written by release.py)
├── downloads/
│   ├── ClipDock-latest.zip            ← the Download button always points here
│   └── ClipDock-v1.0.0.zip            ← every past version is kept
├── app_source/                        ← edit the app HERE
│   ├── clipdock.pyw                   the app (Python + Tkinter, no extra packages)
│   ├── clipdock.ico                   app icon
│   ├── install_shortcut.bat           installer users run
│   └── README.txt                     shipped inside the zip
├── docs/                              images used by this README
├── release.py · release.bat           publish a new version
└── README.md
```

## 📦 Publish an update (30 seconds)

1. Change the app in `app_source/clipdock.pyw`.
2. Double-click **`release.bat`** (or run the command below).
3. Commit and push to GitHub, including the new `.zip` files in `downloads/`.

```bash
python release.py 1.1.0 -n "Added dark mode" -n "Fixed a paste bug"
```

| `release.py` does | Result |
|---|---|
| Stamps the version into `clipdock.pyw` | The app shows the right version |
| Zips `app_source/` → `downloads/ClipDock-v1.1.0.zip` | A permanent copy of every release |
| Copies it to `downloads/ClipDock-latest.zip` | The website's Download button gets the new file |
| Rewrites `version.json` and `version.js` | Website version, size, date and changelog update automatically |

## ☁️ Deploy on Cloudflare (free)

Cloudflare serves static files with unlimited bandwidth on the free plan.

1. In the Cloudflare dashboard go to **Workers & Pages → Create application → Import a repository** and pick this repo.
2. Use these settings:

   | Setting | Value |
   |---|---|
   | Project name | `clipdock` |
   | Build command | *(leave empty)* |
   | Deploy command | `npx wrangler deploy` *(default)* |
   | Root directory | *(blank if `index.html` is at the repo root)* |
   | Protect with Cloudflare Access | **Off**, otherwise visitors must log in |

3. Click **Deploy**. Every push to `main` now redeploys the site automatically.

<details>
<summary><b>Build failed or 404? Add a <code>wrangler.jsonc</code></b></summary>

Create this file next to `index.html`. The `name` must match the project name in the dashboard.

```jsonc
{
  "name": "clipdock",
  "compatibility_date": "2026-11-24",
  "assets": { "directory": "." }
}
```

</details>

Other free hosts also work: **GitHub Pages** (Settings → Pages → deploy from `main`) and
**Netlify Drop** (drag the folder in).

## 🔔 Turn on the in-app update check

After the site is live, open `app_source/clipdock.pyw` and set this once:

```python
UPDATE_URL = "https://YOUR-SITE-ADDRESS/version.json"
```

Run `release.bat` again to ship it. ClipDock then checks on startup and when the user clicks the
**↻** button, and shows **Update v1.x.x ↗** when a newer version exists.

## 👀 Preview locally

Double-click `index.html`. Nothing to install or build.

## 🧱 Built with

- **App:** Python 3 + Tkinter + Win32 (`ctypes`). No third-party packages.
- **Website:** plain HTML, CSS and JavaScript, no frameworks and no build step.
- **Releases:** one Python script (`release.py`).
- **Hosting:** Cloudflare, with the repository on GitHub.

## 💬 Feedback

Found a bug or have an idea? [**Open an issue**](https://github.com/AkarshanGhosh/ClipDock/issues) and
it will go into the next release.

<div align="center">
<br>

Made with care by [@AkarshanGhosh](https://github.com/AkarshanGhosh) for people who copy a lot.

<sub>⭐ If ClipDock saves you time, star the repo.</sub>

</div>
