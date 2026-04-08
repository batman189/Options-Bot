@echo off
title Options Bot
cd /d "c:\Trading Bot v2\Options-Bot\options-bot"

:: Disable QuickEdit mode for this console window.
:: Without this, clicking in the terminal freezes the entire Python process.
powershell -Command "$console = [Console]::Title; $h = (Get-Process -Id $PID).MainWindowHandle; Add-Type -Name W -Namespace C -MemberDefinition '[DllImport(\"kernel32.dll\")] public static extern IntPtr GetStdHandle(int h); [DllImport(\"kernel32.dll\")] public static extern bool GetConsoleMode(IntPtr h, out uint m); [DllImport(\"kernel32.dll\")] public static extern bool SetConsoleMode(IntPtr h, uint m);'; $hIn = [C.W]::GetStdHandle(-10); $m = 0; [C.W]::GetConsoleMode($hIn, [ref]$m) | Out-Null; $m = $m -band (-bnot 0x0040); [C.W]::SetConsoleMode($hIn, $m) | Out-Null" 2>nul

start "" "http://localhost:8000"
python main.py
pause
