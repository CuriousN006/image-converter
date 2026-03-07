@echo off
REM Remove the current user's automatic start entry.

setlocal
set "APP_NAME=ImageConverter"

reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "%APP_NAME%" /f >nul 2>&1
if errorlevel 1 (
    echo Autostart entry was not found.
    exit /b 1
)

echo Autostart disabled for %APP_NAME%.
