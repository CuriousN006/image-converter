@echo off
REM 이미지 자동 변환 스크립트 백그라운드 실행
REM 가상환경의 pythonw.exe를 사용하여 콘솔 창 없이 실행

cd /d "%~dp0"
start "" "d:\PythonPractice\.venv\Scripts\pythonw.exe" image_converter.py
