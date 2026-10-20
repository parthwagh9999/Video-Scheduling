@echo off
setlocal
cd /d "%~dp0"
title Video Scheduling Dashboard

echo ========================================================
echo   Video Scheduling Automation GUI Launching...
echo ========================================================
echo.
echo Starting dashboard server and opening your browser...
echo.

python launch_gui.py

if errorlevel 1 (
    echo.
    echo [ERROR] The application stopped or encountered an error.
    pause
)
