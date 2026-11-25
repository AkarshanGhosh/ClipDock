@echo off
setlocal EnableExtensions
title ClipDock Installer
cd /d "%~dp0"

echo ===================================================
echo   ClipDock installer
echo ===================================================
echo.

REM Find Python. If it is missing, install it from the terminal.
call :find_python
if defined PYTHON_EXE goto :python_ready

echo Python was not found. Installing Python 3.13...
where winget >nul 2>nul
if not errorlevel 1 (
    winget install --id Python.Python.3.13 --exact --scope user --silent --accept-package-agreements --accept-source-agreements
    call :find_python
)

if not defined PYTHON_EXE (
    echo.
    echo winget could not install Python. Downloading the official Python installer...
    set "PYTHON_INSTALLER=%TEMP%\ClipDock-Python-3.13.9-amd64.exe"
    where curl.exe >nul 2>nul
    if not errorlevel 1 (
        curl.exe -fL "https://www.python.org/ftp/python/3.13.9/python-3.13.9-amd64.exe" -o "%TEMP%\ClipDock-Python-3.13.9-amd64.exe"
    ) else (
        powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.13.9/python-3.13.9-amd64.exe' -OutFile '%TEMP%\ClipDock-Python-3.13.9-amd64.exe'"
    )
    if not exist "%TEMP%\ClipDock-Python-3.13.9-amd64.exe" (
        echo ERROR: Python could not be downloaded. Check your internet connection and try again.
        pause
        exit /b 1
    )
    "%TEMP%\ClipDock-Python-3.13.9-amd64.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_pip=1 Include_tcltk=1
    call :find_python
)

if not defined PYTHON_EXE (
    echo ERROR: Python installation could not be verified.
    echo Restart Windows if requested, then run this installer again.
    pause
    exit /b 1
)

:python_ready
for %%P in ("%PYTHON_EXE%") do set "PYTHON_DIR=%%~dpP"
set "PYW=%PYTHON_DIR%pythonw.exe"
if not exist "%PYW%" (
    echo ERROR: pythonw.exe was not found beside Python.
    echo Please reinstall Python with the Tcl/Tk feature enabled.
    pause
    exit /b 1
)

echo Python found: "%PYTHON_EXE%"
echo.

set "INSTALL=%LOCALAPPDATA%\ClipDock"
set "DESK=%USERPROFILE%\Desktop"
if exist "%USERPROFILE%\OneDrive\Desktop" set "DESK=%USERPROFILE%\OneDrive\Desktop"
set "START=%APPDATA%\Microsoft\Windows\Start Menu\Programs"

REM Close the currently installed ClipDock before replacing its files.
echo Closing any existing ClipDock instance...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process -Filter ""Name='pythonw.exe'"" | Where-Object { $_.CommandLine -and $_.CommandLine -like '*clipdock.pyw*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>nul

REM Remove the previous program files. User history/settings are stored separately
REM in %APPDATA%\ClipDock and are deliberately preserved.
if exist "%INSTALL%" rmdir /s /q "%INSTALL%"
mkdir "%INSTALL%"
if errorlevel 1 (
    echo ERROR: Could not create the ClipDock installation folder.
    pause
    exit /b 1
)

copy /y "%~dp0clipdock.pyw" "%INSTALL%\clipdock.pyw" >nul
if errorlevel 1 goto :copy_error
copy /y "%~dp0clipdock.ico" "%INSTALL%\clipdock.ico" >nul
if errorlevel 1 goto :copy_error

echo Creating Desktop and Start menu shortcuts...
if not exist "%START%" mkdir "%START%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$w=New-Object -ComObject WScript.Shell; foreach($p in @('%DESK%\ClipDock.lnk','%START%\ClipDock.lnk')){ $s=$w.CreateShortcut($p); $s.TargetPath='%PYW%'; $s.Arguments='""%INSTALL%\clipdock.pyw""'; $s.WorkingDirectory='%INSTALL%'; $s.IconLocation='%INSTALL%\clipdock.ico'; $s.Description='ClipDock clipboard history'; $s.Save() }" >nul 2>nul

echo.
echo Done! The latest ClipDock version is installed.
echo Your existing clipboard history and settings have been kept.
echo Open ClipDock from your Desktop or Start menu.
echo.
start "" "%PYW%" "%INSTALL%\clipdock.pyw"
timeout /t 3 >nul
exit /b 0

:find_python
set "PYTHON_EXE="
where py >nul 2>nul
if not errorlevel 1 (
    for /f "delims=" %%P in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do set "PYTHON_EXE=%%P"
)
if not defined PYTHON_EXE (
    for /f "delims=" %%P in ('where python 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
)
if not defined PYTHON_EXE if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
exit /b 0

:copy_error
echo ERROR: Could not copy the ClipDock application files.
pause
exit /b 1
