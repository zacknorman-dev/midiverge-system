@echo off
REM ============================================
REM THE ONLY OVERLAY LAUNCHER - USE THIS ONE
REM ============================================

echo ==================================
echo   MIDI OVERLAY LAUNCHER
echo ==================================
echo.

echo Killing old Python instances...
taskkill /F /IM python.exe 2>nul
timeout /t 1 /nobreak >nul

echo Navigating to folder...
cd /d "C:\Users\zackn\Documents\midi overlay"

echo Starting overlay...
echo.
python main.py

echo.
echo Overlay closed.
pause
