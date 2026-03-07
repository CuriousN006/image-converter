@echo off
REM Register the image converter to start automatically at user logon.

setlocal
cd /d "%~dp0"

set "APP_NAME=ImageConverter"
set "PYTHONW=%~dp0.venv\Scripts\pythonw.exe"
set "SCRIPT=%~dp0image_converter.py"

if not exist "%PYTHONW%" (
    echo Local virtual environment not found: "%PYTHONW%"
    echo Create it with: python -m venv .venv
    exit /b 1
)

if not exist "%SCRIPT%" (
    echo Script not found: "%SCRIPT%"
    exit /b 1
)

reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "%APP_NAME%" /t REG_SZ /d "\"%PYTHONW%\" \"%SCRIPT%\"" /f >nul
if errorlevel 1 (
    echo Failed to enable autostart.
    exit /b 1
)

echo Autostart enabled for %APP_NAME%.
