@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title ClipDock installer

set "INSTALL=%LOCALAPPDATA%\ClipDock"
set "START=%APPDATA%\Microsoft\Windows\Start Menu\Programs"
set "DESK=%USERPROFILE%\Desktop"
for /f "delims=" %%D in ('powershell -NoProfile -Command "[Environment]::GetFolderPath('Desktop')" 2^>nul') do set "DESK=%%D"

echo.
echo ===================================================
echo   ClipDock installer
echo ===================================================
echo.

if not exist "clipdock.pyw" (
    echo Could not find clipdock.pyw next to this installer.
    echo Unzip the whole download first ^(right-click the zip ^> Extract All^),
    echo then run install_shortcut.bat from the unzipped folder.
    pause
    exit /b 1
)

set "NEWVER=?"
for /f "tokens=2 delims==# " %%V in ('findstr /b /c:"VERSION" "clipdock.pyw"') do set "NEWVER=%%~V"

rem ===================================================================
rem  1/4  Python
rem ===================================================================
echo [1/4] Checking for Python...
call :find_python
if defined PYW goto :python_ok

echo       Python was not found. Installing it now ^(one time, about 1-2 minutes^)...
call :install_python
call :find_python
if defined PYW goto :python_ok

echo.
echo       Could not install Python automatically ^(no internet, or it was blocked^).
echo       Please install it yourself from https://www.python.org/downloads/
echo       and tick "Add python.exe to PATH", then run this installer again.
pause
exit /b 1

:python_ok
echo       OK: %PYW%

rem ===================================================================
rem  2/4  Remove any previous ClipDock
rem ===================================================================
echo [2/4] Checking for a previous ClipDock...
set "OLDVER="
set "HAD_OLD="
if exist "%INSTALL%\clipdock.pyw" (
    set "HAD_OLD=1"
    for /f "tokens=2 delims==# " %%V in ('findstr /b /c:"VERSION" "%INSTALL%\clipdock.pyw"') do set "OLDVER=%%~V"
)
if exist "%INSTALL%\ClipDock.exe" set "HAD_OLD=1"
if exist "%DESK%\ClipDock.lnk" set "HAD_OLD=1"
if exist "%START%\ClipDock.lnk" set "HAD_OLD=1"

if defined HAD_OLD (
    if defined OLDVER (
        echo       Found ClipDock v%OLDVER%. Removing it before installing v%NEWVER%...
    ) else (
        echo       Found an older ClipDock. Removing it before installing v%NEWVER%...
    )
    call :stop_clipdock
    if exist "%INSTALL%" rmdir /s /q "%INSTALL%"
    call :remove_shortcuts
    echo       Old version removed. Your clipboard history and settings are kept.
) else (
    echo       None found - this is a fresh install.
)

rem ===================================================================
rem  3/4  Install the new version
rem ===================================================================
echo [3/4] Installing ClipDock v%NEWVER%...
mkdir "%INSTALL%" >nul 2>nul
copy /y "clipdock.pyw" "%INSTALL%\clipdock.pyw" >nul
if errorlevel 1 goto :copy_failed
copy /y "clipdock.ico" "%INSTALL%\clipdock.ico" >nul
if exist "uninstall_clipdock.bat" copy /y "uninstall_clipdock.bat" "%INSTALL%\uninstall_clipdock.bat" >nul

echo       Creating Desktop and Start menu shortcuts...
powershell -NoProfile -Command "$w=New-Object -ComObject WScript.Shell; foreach($p in @('%DESK%\ClipDock.lnk','%START%\ClipDock.lnk')){ $s=$w.CreateShortcut($p); $s.TargetPath='%PYW%'; $s.Arguments='\"%INSTALL%\clipdock.pyw\"'; $s.WorkingDirectory='%INSTALL%'; $s.IconLocation='%INSTALL%\clipdock.ico'; $s.Description='ClipDock clipboard history'; $s.Save() }" >nul 2>nul
set "SHORTCUT_OK=1"
if errorlevel 1 set "SHORTCUT_OK="
if not exist "%START%\ClipDock.lnk" set "SHORTCUT_OK="

rem ===================================================================
rem  4/4  Launch
rem ===================================================================
echo [4/4] Starting ClipDock...
start "" "%PYW%" "%INSTALL%\clipdock.pyw"

echo.
echo ===================================================
if defined OLDVER (
    echo   ClipDock v%NEWVER% is ready - upgraded from v%OLDVER%
) else (
    echo   ClipDock v%NEWVER% is ready!
)
echo ===================================================
if defined SHORTCUT_OK goto :msg_shortcut_ok
echo   Windows blocked automatic shortcut creation. Make one by hand ^(30 seconds^):
echo     1. Right-click the Desktop ^> New ^> Shortcut
echo     2. Paste this as the location:
echo        "%PYW%" "%INSTALL%\clipdock.pyw"
echo     3. Name it ClipDock ^> Finish
echo     4. Right-click it ^> Properties ^> Change Icon ^> Browse ^> %INSTALL%\clipdock.ico
goto :msg_done
:msg_shortcut_ok
echo   Open it any time from your Desktop or Start menu ^(search "ClipDock"^).
echo   Tip: right-click the shortcut ^> Pin to taskbar.
:msg_done
if defined HAD_OLD echo   If an old ClipDock window was open, close it with the X and reopen from the shortcut.
echo.
echo   To uninstall later, run:  %INSTALL%\uninstall_clipdock.bat
echo.
if defined SHORTCUT_OK timeout /t 8 >nul
if not defined SHORTCUT_OK pause
exit /b 0

:copy_failed
echo.
echo Could not copy files to %INSTALL%
echo Close ClipDock if it is open and try again.
pause
exit /b 1


rem ===================================================================
rem  Subroutines
rem ===================================================================

:find_python
rem Finds a working Python (with tkinter) and sets PYW to its pythonw.exe
set "PYW="
set "PYEXE="
for /f "delims=" %%P in ('python -c "import sys,tkinter;print(sys.executable)" 2^>nul') do set "PYEXE=%%P"
if not defined PYEXE for /f "delims=" %%P in ('py -3 -c "import sys,tkinter;print(sys.executable)" 2^>nul') do set "PYEXE=%%P"
if not defined PYEXE (
    for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*" "%ProgramFiles%\Python3*") do (
        if exist "%%D\python.exe" (
            "%%D\python.exe" -c "import tkinter" >nul 2>nul
            if not errorlevel 1 set "PYEXE=%%D\python.exe"
        )
    )
)
if defined PYEXE for %%F in ("%PYEXE%") do set "PYW=%%~dpFpythonw.exe"
if defined PYW if not exist "%PYW%" set "PYW="
exit /b 0

:install_python
rem 1) Windows Package Manager (winget), 2) direct download from python.org
where winget >nul 2>nul
if not errorlevel 1 (
    echo       Trying winget ^(Windows Package Manager^)...
    winget install -e --id Python.Python.3.13 --scope user --silent --accept-package-agreements --accept-source-agreements
    call :find_python
    if defined PYW exit /b 0
)
echo       Downloading the Python installer from python.org...
set "PYSETUP=%TEMP%\python-setup.exe"
if exist "%PYSETUP%" del "%PYSETUP%" >nul 2>nul
for %%V in (3.13.17 3.13.16 3.13.15 3.13.14) do (
    if not exist "%PYSETUP%" (
        curl.exe -L --fail --progress-bar -o "%PYSETUP%" "https://www.python.org/ftp/python/%%V/python-%%V-amd64.exe"
        if errorlevel 1 del "%PYSETUP%" >nul 2>nul
    )
)
if not exist "%PYSETUP%" exit /b 1
echo       Installing Python silently ^(please wait^)...
start "" /wait "%PYSETUP%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=0 Include_test=0 Include_doc=0 Shortcuts=0
del "%PYSETUP%" >nul 2>nul
exit /b 0

:stop_clipdock
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { ($_.Name -match '^pythonw?\.exe$' -and $_.CommandLine -like '*clipdock.pyw*') -or $_.Name -eq 'ClipDock.exe' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>nul
taskkill /f /im ClipDock.exe >nul 2>nul
timeout /t 1 >nul
exit /b 0

:remove_shortcuts
del "%DESK%\ClipDock.lnk" >nul 2>nul
del "%USERPROFILE%\Desktop\ClipDock.lnk" >nul 2>nul
del "%USERPROFILE%\OneDrive\Desktop\ClipDock.lnk" >nul 2>nul
del "%START%\ClipDock.lnk" >nul 2>nul
exit /b 0
