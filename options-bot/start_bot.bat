@echo off
title Options Bot
cd /d "c:\Trading Bot v2\Options-Bot\options-bot"
reg add "HKCU\Console" /v QuickEdit /t REG_DWORD /d 0 /f >nul 2>&1
start "" "http://localhost:8000"
python main.py
pause
