@echo off
chcp 65001 >nul
title QQ AI Companion Setup & Launcher (Windows)
cd /d "%~dp0"

echo =========================================================
echo       QQ AI Companion - All-in-One Setup (Windows)
echo =========================================================
echo.

:: 1. Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please download and install Python 3.10+ from https://www.python.org/
    echo (Make sure to check "Add python.exe to PATH" during installation)
    pause
    exit /b 1
)

:: 2. Setup venv
if not exist "venv" (
    echo [*] Creating Python virtual environment (venv)...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create venv.
        pause
        exit /b 1
    )
)

echo [*] Activating virtual environment...
call venv\Scripts\activate.bat

echo [*] Installing dependencies from requirements.txt...
python -m pip install --upgrade pip
pip install -r requirements.txt

:: 3. Check config.json
if not exist "config.json" (
    echo [*] config.json not found. Creating from config.example.json...
    copy config.example.json config.json >nul
    echo.
    echo [!] Created config.json. Please edit it with your API key and master QQ!
    echo.
)

:: 4. NapCatQQ Bridge Setup
echo.
echo =========================================================
echo NapCatQQ (OneBot 11 QQ Bridge) Setup
echo =========================================================
echo 1) Auto-download NapCat Windows OneKey package
echo 2) Open NapCatQQ Desktop (GUI manager) download page
echo 3) Skip (NapCat is already running or configured manually)
echo =========================================================
set /p napcat_choice="Select an option [1-3, default: 3]: "

if "%napcat_choice%"=="" set napcat_choice=3

if "%napcat_choice%"=="1" (
    echo [*] Downloading latest NapCat Windows OneKey package...
    if not exist "NapCat" mkdir NapCat
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference = 'Stop'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $url = 'https://github.com/NapNeko/NapCatQQ/releases/latest/download/NapCat.Shell.Windows.OneKey.zip'; Write-Host 'Downloading NapCat from GitHub...'; Invoke-WebRequest -Uri $url -OutFile 'NapCat\NapCat.zip'; Write-Host 'Extracting files...'; Expand-Archive -Path 'NapCat\NapCat.zip' -DestinationPath 'NapCat' -Force; Remove-Item 'NapCat\NapCat.zip'; Write-Host 'Download and extraction complete!'"
    echo.
    echo [+] NapCat has been extracted to the NapCat\ folder.
    echo [*] Please run NapCatInstaller.exe inside NapCat\ to initialize QQ login!
    echo.
)

if "%napcat_choice%"=="2" (
    echo [*] Opening NapCatQQ Desktop releases page in your default browser...
    start https://github.com/NapNeko/NapCatQQ/releases
)

echo.
echo =========================================================
echo Setup completed! Starting QQ AI Companion...
echo (Press Ctrl+C in this window to stop the agent)
echo =========================================================
echo.

python autonomous_agent.py

pause
