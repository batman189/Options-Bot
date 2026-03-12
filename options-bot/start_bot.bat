@echo off
title Options Bot
cd /d "%~dp0"
start /b python main.py
timeout /t 5 /nobreak >nul
start "" "http://localhost:8000"
timeout /t 1 /nobreak >nul
start "" "http://localhost:8000/system"
pause
