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

python autonomous_agent.py

if %errorlevel% neq 0 (
    echo.
    echo [!] Process exited with code %errorlevel%.
)

pause
