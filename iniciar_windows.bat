@echo off
cd /d "%~dp0"
py -3 -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
start "" http://127.0.0.1:8000
py -3 run.py
pause
