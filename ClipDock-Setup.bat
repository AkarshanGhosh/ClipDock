@echo off
setlocal EnableExtensions
title ClipDock setup
echo.
echo ===================================================
echo   ClipDock one-file setup
echo   Downloads the latest ClipDock and installs it
echo   (and Python too, if you don't have it).
echo ===================================================
echo.
set "TMPD=%TEMP%\ClipDock-setup"
set "ZIP=%TMPD%\ClipDock.zip"
if exist "%TMPD%" rmdir /s /q "%TMPD%"
mkdir "%TMPD%"

echo Downloading the latest ClipDock...
set "OK="
for %%U in ("https://raw.githubusercontent.com/AkarshanGhosh/ClipDock/main/downloads/ClipDock-latest.zip") do (
    if not defined OK (
        curl.exe -L --fail --silent --show-error -o "%ZIP%" "%%U" && set "OK=1"
    )
)
if not defined OK (
    echo.
    echo Download failed. Check your internet connection and try again.
    pause
    exit /b 1
)

tar -xf "%ZIP%" -C "%TMPD%"
if not exist "%TMPD%\ClipDock\install_shortcut.bat" (
    echo.
    echo The download looked incomplete. Please try again.
    pause
    exit /b 1
)
call "%TMPD%\ClipDock\install_shortcut.bat"
rmdir /s /q "%TMPD%" >nul 2>nul
exit /b 0
