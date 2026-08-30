@echo off
set "SCRIPT=C:\Users\zackn\Documents\midi overlay\restart_system.ps1"

if not exist "%SCRIPT%" (
	echo Recovery script not found: "%SCRIPT%"
	pause
	exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%"
pause