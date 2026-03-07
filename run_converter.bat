@echo off
REM Run the image converter in the background using the local project venv.

setlocal
cd /d "%~dp0"
set "PYTHONW=%~dp0.venv\Scripts\pythonw.exe"

if not exist "%PYTHONW%" (
    echo Local virtual environment not found: "%PYTHONW%"
    echo Create it with: python -m venv .venv
    exit /b 1
)

start "" "%PYTHONW%" "%~dp0image_converter.py"
