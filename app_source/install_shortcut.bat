@echo off
setlocal
title Installing ClipDock
cd /d "%~dp0"

echo ===================================================
echo   ClipDock installer (works with Smart App Control)
echo ===================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found. Install it from https://www.python.org/downloads/
    echo and tick "Add python.exe to PATH", then run this file again.
    pause
    exit /b 1
)

for /f "delims=" %%P in ('python -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))"') do set "PYW=%%P"
if not exist "%PYW%" (
    echo Could not find pythonw.exe next to your Python install.
    pause
    exit /b 1
)

set "INSTALL=%LOCALAPPDATA%\ClipDock"
if not exist "%INSTALL%" mkdir "%INSTALL%"
copy /y "clipdock.pyw" "%INSTALL%\clipdock.pyw" >nul
copy /y "clipdock.ico" "%INSTALL%\clipdock.ico" >nul

set "DESK=%USERPROFILE%\Desktop"
if exist "%USERPROFILE%\OneDrive\Desktop" set "DESK=%USERPROFILE%\OneDrive\Desktop"
set "START=%APPDATA%\Microsoft\Windows\Start Menu\Programs"

echo Creating shortcuts...
powershell -NoProfile -Command "$w=New-Object -ComObject WScript.Shell; foreach($p in @('%DESK%\ClipDock.lnk','%START%\ClipDock.lnk')){ $s=$w.CreateShortcut($p); $s.TargetPath='%PYW%'; $s.Arguments='\"%INSTALL%\clipdock.pyw\"'; $s.WorkingDirectory='%INSTALL%'; $s.IconLocation='%INSTALL%\clipdock.ico'; $s.Description='ClipDock clipboard history'; $s.Save() }" >nul 2>nul

if errorlevel 1 goto :manual
if not exist "%DESK%\ClipDock.lnk" goto :manual

echo.
echo Done!  Click "ClipDock" on your Desktop or search it in the Start menu.
echo Tip: right-click it ^> "Pin to taskbar" for one-click launch.
start "" "%PYW%" "%INSTALL%\clipdock.pyw"
timeout /t 4 >nul
exit /b 0

:manual
echo.
echo Windows blocked automatic shortcut creation. Make it by hand (30 seconds):
echo   1. Right-click the Desktop ^> New ^> Shortcut
echo   2. Paste this as the location:
echo      "%PYW%" "%INSTALL%\clipdock.pyw"
echo   3. Name it ClipDock ^> Finish
echo   4. Right-click it ^> Properties ^> Change Icon ^> Browse ^> pick:
echo      %INSTALL%\clipdock.ico
echo.
echo Starting ClipDock now...
start "" "%PYW%" "%INSTALL%\clipdock.pyw"
pause
exit /b 0
