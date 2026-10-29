@echo off
chcp 65001 >nul
title QQ AI Companion Runner
cd /d "%~dp0"

echo =========================================================
echo       QQ AI Companion - Starting Agent (Windows)
echo =========================================================
echo.

if exist "venv\Scripts\activate.bat" (
    echo [*] Activating virtual environment...
    call venv\Scripts\activate.bat
)

REM Keep NapCat's OneBot API (no token) reachable from this computer only
python secure_napcat.py

python autonomous_agent.py

if %errorlevel% neq 0 (
    echo.
    echo [!] Process exited with code %errorlevel%.
)

pause
