@echo off
echo ==================================
echo   MIDI OVERLAY LAUNCHER
echo ==================================
echo.
echo Killing old Python instances...
taskkill /F /IM python.exe 2>nul
timeout /t 1 /nobreak >nul
echo.
echo Starting overlay...
cd /d "C:\Users\zackn\Documents\midi overlay"
python main.py
echo.
echo Overlay closed.
pause
