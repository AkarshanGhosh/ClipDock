ClipDock - clipboard history that pastes where your cursor is
==============================================================

INSTALL (about 1 minute)
  1. Unzip the whole download (right-click > Extract All).
  2. Double-click  install_shortcut.bat
     - If you don't have Python, it is downloaded and installed for you.
     - If an older ClipDock is installed, it is removed first and the latest
       version is installed in its place (your history and settings are kept).
  3. Done! Open "ClipDock" from your Desktop or Start menu.

QUICK START
  Ctrl+Alt+V      show / hide ClipDock from any app (change it in Settings)
  Up / Down       move through items          Enter        paste the selected item
  1 - 9           paste that item             Shift+Enter  paste as plain text
  type            search                      Tab          switch tab
  F2 rename       Del delete                  Esc          close

  Right-click an item (or click the three dots) for: paste as UPPERCASE /
  lowercase / Title Case / one line, open link, write e-mail, pretty-print JSON,
  rename, pin, save as snippet.

PASTE STACK
  Click the stack button in the header, copy several things, then press
  Ctrl+Alt+N to paste them back one at a time, in order.

SNIPPETS
  Snippets tab > New snippet. Use variables: {date} {time} {datetime} {weekday}
  {clipboard} {user}, or {date:%d/%m/%Y} for a custom format. Folders group them.

MOVE / RESIZE / LOOK
  Drag from any empty spot to move. Drag any edge or corner to resize.
  Gear button = Settings: hotkeys, theme, accent colour, opacity, text size,
  history size, start with Windows, tray behaviour, backup and sync.

BACKUP AND SYNC
  Settings > Backup & sync: Export / Import a backup file, or pick a OneDrive
  (or Dropbox) folder to share your history between PCs. (Images stay on one PC.)

FEEDBACK
  Click the envelope button in ClipDock: it opens a pre-filled GitHub issue.

UPDATE
  ClipDock tells you when an update exists: click "Update vX" and choose
  "Install now" - it downloads, verifies and installs itself, keeping your
  history. You can also run install_shortcut.bat from a newer zip.

UNINSTALL
  Run uninstall_clipdock.bat (also saved in %LOCALAPPDATA%\ClipDock).
  It asks whether to delete your history too.

Windows shows "Windows protected your PC" (SmartScreen)?
  Click "More info" > "Run anyway". The installer is a plain text .bat file.

Smart App Control blocks unsigned .exe files. ClipDock is not an .exe: it runs
as a script through Python, so it is not affected.
