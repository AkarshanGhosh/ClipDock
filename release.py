"""
ClipDock release tool
=====================
Edit the app in  app_source/  then publish a new version with ONE command:

    python release.py 1.1.0 -n "Added dark mode" -n "Fixed a paste bug"

or just run it with no arguments (or double-click release.bat) and answer the questions.

What it does
  1. writes the version into app_source/clipdock.pyw
  2. zips app_source/ into downloads/ClipDock-v<version>.zip
  3. copies it to downloads/ClipDock-latest.zip   <- the website's Download button
  4. updates version.json (used by the app's update check) and version.js (used by the website)
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
    if not SEMVER.match(version):
        sys.exit("Version must look like 1.2.3")
    if not os.path.exists(APP_FILE):
        sys.exit("app_source/clipdock.pyw not found")
    if not notes:
        notes = ["Improvements and fixes"]

    stamp_version(version)
    _, size, sha = build_zip(version)

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
        "releases": releases,
    })
    with open(VERSION_JSON, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    with open(VERSION_JS, "w", encoding="utf-8") as f:
        f.write("window.CLIPDOCK_RELEASE = " + json.dumps(state, indent=2, ensure_ascii=False) + ";\n")

    print(f"\nReleased ClipDock v{version}  ({size / 1024:.1f} KB)")
    print("  downloads/ClipDock-latest.zip  updated")
    print("  version.json / version.js      updated")
    print("Now upload this folder to your website host.")


if __name__ == "__main__":
    main()
