@echo off
title Video Scheduling Dashboard — Creator Studio
chcp 65001 >nul
cls

echo ============================================================================
echo   🎬 VIDEO SCHEDULING - CREATOR STUDIO LAUNCHER
echo ============================================================================
echo.

:: 1. Check Python installation
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python 3 is not installed or not in your system PATH.
    echo Please install Python 3.10 or newer from https://www.python.org/
    echo Make sure to check the box "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

echo [✓] Python detected:
python --version
echo.

:: 2. Check if virtual environment exists, activate if present
if exist "venv\Scripts\activate.bat" (
    echo [i] Activating virtual environment 'venv'...
    call venv\Scripts\activate.bat
) else if exist ".venv\Scripts\activate.bat" (
    echo [i] Activating virtual environment '.venv'...
    call .venv\Scripts\activate.bat
)

:: 3. Launch Dashboard & Open Browser
echo.
echo [i] Starting Video Scheduling Dashboard at http://127.0.0.1:8899 ...
echo [i] Press Ctrl+C in this terminal window anytime to stop the server.
echo.

start "" "http://127.0.0.1:8899"
python launch_gui.py

if %errorlevel% neq 0 (
    echo.
    echo [!] Server exited with an error code: %errorlevel%
    pause
)
