@echo off
setlocal EnableExtensions
set "INSTALL=%LOCALAPPDATA%\ClipDock"
set "START=%APPDATA%\Microsoft\Windows\Start Menu\Programs"

rem If we are running from inside the folder we are about to delete, re-run from TEMP first.
if /i "%~dp0"=="%INSTALL%\" (
    copy /y "%~f0" "%TEMP%\clipdock_uninstall.bat" >nul
    start "" "%TEMP%\clipdock_uninstall.bat"
    exit /b 0
)

title ClipDock uninstaller
echo.
echo ===================================================
echo   ClipDock uninstaller
echo ===================================================
echo.
echo Closing ClipDock...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { ($_.Name -match '^pythonw?\.exe$' -and $_.CommandLine -like '*clipdock.pyw*') -or $_.Name -eq 'ClipDock.exe' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>nul
taskkill /f /im ClipDock.exe >nul 2>nul
timeout /t 1 >nul

echo Removing program files and shortcuts...
if exist "%INSTALL%" rmdir /s /q "%INSTALL%"
del "%USERPROFILE%\Desktop\ClipDock.lnk" >nul 2>nul
del "%USERPROFILE%\OneDrive\Desktop\ClipDock.lnk" >nul 2>nul
for /f "delims=" %%D in ('powershell -NoProfile -Command "[Environment]::GetFolderPath('Desktop')" 2^>nul') do del "%%D\ClipDock.lnk" >nul 2>nul
del "%START%\ClipDock.lnk" >nul 2>nul

echo.
choice /c YN /n /m "Also delete your clipboard history and settings? [Y/N] "
if errorlevel 2 goto :keep
if exist "%APPDATA%\ClipDock" rmdir /s /q "%APPDATA%\ClipDock"
echo History and settings deleted.
goto :done
:keep
echo Your history and settings were kept ^(%APPDATA%\ClipDock^).
:done
echo.
echo ClipDock has been uninstalled.
pause
exit /b 0
