"""
ClipDock release tool
=====================
Edit the app in  app_source/  then publish a new version with ONE command:

    python release.py 1.1.0 -n "Added dark mode" -n "Fixed a paste bug"
    python release.py 1.1.0 -n "..." --site-url https://your-site.workers.dev   (remembered after the first time)

or just run it with no arguments (or double-click release.bat) and answer the questions.

What it does
  1. writes the version into app_source/clipdock.pyw
  2. zips app_source/ into downloads/ClipDock-v<version>.zip
  3. copies it to downloads/ClipDock-latest.zip   <- the website's Download button
  4. updates version.json (used by the app's update check) and version.js (used by the website)
  5. stamps the release notes into the app (shown in its "What's new" page after an update)
  6. writes downloads/checksums.txt (SHA-256 of every download, also shown on the website)
  7. builds downloads/ClipDock-Setup.bat, a one-file online installer that downloads the latest
     zip (from your site, falling back to GitHub) and installs it, Python included
Then upload the folder to your host again and everyone gets the new version.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "app_source")
DOWNLOADS = os.path.join(ROOT, "downloads")
VERSION_JSON = os.path.join(ROOT, "version.json")
VERSION_JS = os.path.join(ROOT, "version.js")
APP_FILE = os.path.join(SRC, "clipdock.pyw")
SETUP_TEMPLATE = os.path.join(ROOT, "tools", "ClipDock-Setup.template.bat")
SETUP_OUT = os.path.join(DOWNLOADS, "ClipDock-Setup.bat")
DEFAULT_REPO = "AkarshanGhosh/ClipDock"
EXCLUDE = {"__pycache__", "make_icon.py", ".DS_Store", "Thumbs.db"}
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def load_state():
    if os.path.exists(VERSION_JSON):
        with open(VERSION_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"app": "ClipDock", "latest": "0.0.0", "releases": []}


def stamp_version(version):
    with open(APP_FILE, "r", encoding="utf-8") as f:
        src = f.read()
    new, n = re.subn(r'^VERSION\s*=\s*"[^"]*"', f'VERSION = "{version}"', src, count=1, flags=re.M)
    if n == 0:
        sys.exit("Could not find a VERSION = \"...\" line in app_source/clipdock.pyw")
    with open(APP_FILE, "w", encoding="utf-8", newline="") as f:
        f.write(new)


def stamp_notes(notes, repo):
    """Put this release's notes (and the GitHub repo) into the app so it can show 'What's new' offline."""
    with open(APP_FILE, "r", encoding="utf-8") as f:
        src = f.read()
    block = "# <<WHATS_NEW>>\nWHATS_NEW = [\n" + "".join(f"    {json.dumps(n)},\n" for n in notes) + "]\n# <<END>>"
    src, n = re.subn(r"# <<WHATS_NEW>>\n.*?# <<END>>", lambda m: block, src, count=1, flags=re.S)
    if n == 0:
        print("  (note: no WHATS_NEW markers found in clipdock.pyw - skipped)")
    src = re.sub(r'^REPO\s*=\s*".*"', f'REPO = "{repo}"', src, count=1, flags=re.M)
    with open(APP_FILE, "w", encoding="utf-8", newline="") as f:
        f.write(src)


def write_checksums(version):
    lines = []
    for name in (f"ClipDock-v{version}.zip", "ClipDock-latest.zip", "ClipDock-Setup.bat"):
        path = os.path.join(DOWNLOADS, name)
        if os.path.exists(path):
            with open(path, "rb") as f:
                lines.append(f"{hashlib.sha256(f.read()).hexdigest()}  {name}")
    with open(os.path.join(DOWNLOADS, "checksums.txt"), "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(lines) + "\n")


def stamp_urls(site_url, repo):
    """Point the app's update check at the website (or GitHub if no website address is known)."""
    with open(APP_FILE, "r", encoding="utf-8") as f:
        src = f.read()
    if site_url:
        update, site = site_url + "/version.json", site_url + "/"
    else:
        update = f"https://raw.githubusercontent.com/{repo}/main/version.json"
        site = f"https://github.com/{repo}"
    src = re.sub(r'^UPDATE_URL\s*=\s*".*"', f'UPDATE_URL = "{update}"', src, count=1, flags=re.M)
    src = re.sub(r'^SITE_URL\s*=\s*".*"', f'SITE_URL = "{site}"', src, count=1, flags=re.M)
    with open(APP_FILE, "w", encoding="utf-8", newline="") as f:
        f.write(src)


def build_setup(site_url, repo):
    """One-file online installer: tries the website first, then the GitHub copy."""
    if not os.path.exists(SETUP_TEMPLATE):
        return False
    urls = []
    if site_url:
        urls.append(f'"{site_url}/downloads/ClipDock-latest.zip"')
    urls.append(f'"https://raw.githubusercontent.com/{repo}/main/downloads/ClipDock-latest.zip"')
    with open(SETUP_TEMPLATE, "r", encoding="utf-8") as f:
        text = f.read().replace("__URLS__", " ".join(urls))
    os.makedirs(DOWNLOADS, exist_ok=True)
    with open(SETUP_OUT, "w", encoding="utf-8", newline="") as f:
        f.write(text.replace("\r\n", "\n").replace("\n", "\r\n"))
    return True


def build_zip(version):
    os.makedirs(DOWNLOADS, exist_ok=True)
    versioned = os.path.join(DOWNLOADS, f"ClipDock-v{version}.zip")
    with zipfile.ZipFile(versioned, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(os.listdir(SRC)):
            if name in EXCLUDE:
                continue
            path = os.path.join(SRC, name)
            if os.path.isfile(path):
                z.write(path, arcname=f"ClipDock/{name}")
    latest = os.path.join(DOWNLOADS, "ClipDock-latest.zip")
    shutil.copyfile(versioned, latest)
    with open(latest, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    return latest, os.path.getsize(latest), sha


def main():
    ap = argparse.ArgumentParser(description="Publish a new ClipDock version")
    ap.add_argument("version", nargs="?", help="new version, e.g. 1.1.0")
    ap.add_argument("-n", "--note", action="append", default=[], help="changelog line (repeat for more)")
    ap.add_argument("--site-url", help="your website address, e.g. https://clipdock.example.workers.dev (remembered)")
    ap.add_argument("--repo", help="GitHub repo as owner/name (remembered)")
    args = ap.parse_args()

    state = load_state()
    version = args.version
    notes = args.note
    if not version:
        print(f"Current version: {state['latest']}")
        version = input("New version (e.g. 1.1.0): ").strip()
        print("What changed? One line per change, empty line to finish:")
        while True:
            line = input("  - ").strip()
            if not line:
                break
            notes.append(line)
    site_url = (args.site_url if args.site_url is not None else state.get("site_url", "")).strip().rstrip("/")
    repo = (args.repo or state.get("repo") or DEFAULT_REPO).strip().strip("/")
    if not SEMVER.match(version):
        sys.exit("Version must look like 1.2.3")
    if not os.path.exists(APP_FILE):
        sys.exit("app_source/clipdock.pyw not found")
    if not notes:
        notes = ["Improvements and fixes"]

    stamp_version(version)
    stamp_urls(site_url, repo)
    stamp_notes(notes, repo)
    _, size, sha = build_zip(version)
    has_setup = build_setup(site_url, repo)
    write_checksums(version)

    today = datetime.date.today().isoformat()
    releases = [r for r in state.get("releases", []) if r.get("version") != version]
    releases.insert(0, {"version": version, "date": today, "notes": notes})
    state.update({
        "app": "ClipDock",
        "latest": version,
        "released": today,
        "size_bytes": size,
        "sha256": sha,
        "download": "downloads/ClipDock-latest.zip",
        "setup": "downloads/ClipDock-Setup.bat" if has_setup else "",
        "site_url": site_url,
        "repo": repo,
        "releases": releases,
    })
    with open(VERSION_JSON, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    with open(VERSION_JS, "w", encoding="utf-8") as f:
        f.write("window.CLIPDOCK_RELEASE = " + json.dumps(state, indent=2, ensure_ascii=False) + ";\n")

    print(f"\nReleased ClipDock v{version}  ({size / 1024:.1f} KB)")
    print("  downloads/ClipDock-latest.zip  updated")
    print("  version.json / version.js      updated")
    print("  downloads/checksums.txt        written")
    if has_setup:
        print("  downloads/ClipDock-Setup.bat   rebuilt (one-file online installer)")
    print(f"  app update check -> {'your website' if site_url else 'GitHub (' + repo + ')'}")
    print("Now upload this folder to your website host.")


if __name__ == "__main__":
    main()
