@echo off
setlocal
cd /d "%~dp0"

if not exist logs mkdir logs

echo [%DATE% %TIME%] Starting 1TamilVT-TG Bot... >> logs\bot.log

:loop
echo [%DATE% %TIME%] Launching bot process... >> logs\bot.log
python -m bot >> logs\bot.log 2>&1
set EXIT_CODE=%ERRORLEVEL%

echo [%DATE% %TIME%] Bot exited with code %EXIT_CODE%. Restarting in 3 seconds... >> logs\bot.log
timeout /t 3 /nobreak >nul
goto loop
