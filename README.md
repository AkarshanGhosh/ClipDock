# ClipDock website

```
clipdock/
├── index.html, style.css, app.js     the website (no build step, no sign-up)
├── version.js / version.json         current version + changelog (written by release.py)
├── downloads/
│   ├── ClipDock-latest.zip           <- the Download button always points here
│   └── ClipDock-v1.0.0.zip           <- every past version is kept
├── app_source/                       <- edit the app HERE
│   ├── clipdock.pyw, clipdock.ico, install_shortcut.bat, README.txt
├── release.py / release.bat          <- publish a new version
└── README.md
```

## Publish an update (30 seconds)
1. Change the app in `app_source/clipdock.pyw`.
2. Double-click `release.bat` (or run `python release.py 1.1.0 -n "What changed"`).
3. Upload the folder to your host again.

That rebuilds `downloads/ClipDock-latest.zip`, bumps the version inside the app, and the
website shows the new version number, size, date and changelog automatically.

## Host it free
- **GitHub Pages**: push the folder to a repo, Settings > Pages > deploy from main.
- **Netlify Drop** (app.netlify.com/drop): drag the whole folder in.
- **Cloudflare Pages**: connect the repo or upload the folder.

## Let the app tell users about updates
After hosting, open `app_source/clipdock.pyw` and set once:

    UPDATE_URL = "https://YOUR-SITE/version.json"

then run `release.bat` again. ClipDock checks on startup and when the user clicks the
header's refresh button; when a newer version exists it shows "Update v1.x.x" and
opens your download page on click.

## Preview locally
Just double-click `index.html`.
