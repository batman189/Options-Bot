@echo off
title Options Bot
cd /d "%~dp0"
start "" "http://localhost:3000"
timeout /t 3 /nobreak >nul
start "" "http://localhost:3000/system"
python main.py
pause
