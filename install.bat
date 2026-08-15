@echo off
chcp 65001 >nul
title 1TamilVT-TG Installer
color 0A

echo.
echo  ╔══════════════════════════════════════════════════════════╗
echo  ║        1TamilVT-TG  —  One-Click Installer               ║
echo  ║        Tamil Movie Bot for Telegram                      ║
echo  ╚══════════════════════════════════════════════════════════╝
echo.

:: Check for Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  [❌] Python not found. Installing Python 3.11...
    curl -L -o python_installer.exe "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
    start /wait python_installer.exe /quiet InstallAllUsers=1 PrependPath=1
    del python_installer.exe
    echo  [✅] Python installed. Please restart CMD and run this script again.
    pause
    exit /b
)

for /f "tokens=*" %%a in ('python --version 2^>^&1') do set PYVER=%%a
echo  [✅] Found %PYVER%

:: Clone repo if not present
if not exist "1tamilvt-tg" (
    echo  [📥] Cloning repository...
    git clone https://github.com/aj-2-c-2-a/1tamilvt-tg.git
    if errorlevel 1 (
        echo  [⚠️] Git not found. Downloading ZIP instead...
        curl -L -o 1tamilvt-tg.zip "https://github.com/aj-2-c-2-a/1tamilvt-tg/archive/refs/heads/main.zip"
        tar -xf 1tamilvt-tg.zip
        move 1tamilvt-tg-main 1tamilvt-tg
        del 1tamilvt-tg.zip
    )
)

cd 1tamilvt-tg

:: Create venv
echo  [🔧] Creating virtual environment...
python -m venv venv

:: Activate and install
call venv\Scripts\activate.bat
echo  [📦] Installing dependencies...
pip install --upgrade pip
pip install -r requirements.txt

:: Prompt for config
echo.
echo  ──────────────────────────────────────────────────────────
echo   CONFIGURATION
set /p TOKEN="Enter Telegram Bot Token (from @BotFather): "
set /p CHANNEL_ID="Enter Telegram Channel ID (e.g. -1001234567890): "
set /p CHANNEL_USERNAME="Enter Channel Username (without @): "

(
echo TOKEN=%TOKEN%
echo CHANNEL_ID=%CHANNEL_ID%
echo CHANNEL_USERNAME=%CHANNEL_USERNAME%
echo TAMILMV_URL=https://www.1tamilmv.fi
echo PORT=8080
echo SCRAPE_INTERVAL=300
echo LOG_LEVEL=INFO
) > .env

echo  [✅] Configuration saved to .env
echo.
echo  ╔══════════════════════════════════════════════════════════╗
echo  ║  🚀 Starting 1TamilVT-TG Bot...                          ║
echo  ╚══════════════════════════════════════════════════════════╝
echo.

python -m bot

echo.
pause
