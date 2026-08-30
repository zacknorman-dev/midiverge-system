# Launch MIDI Overlay
# Simple launcher without cache clearing

Write-Host "Starting MIDI Overlay..." -ForegroundColor Cyan

# Launch the Python overlay
$pythonPath = "python"
$scriptPath = "c:\Users\zackn\Documents\midi overlay\main.py"

Start-Process -FilePath $pythonPath -ArgumentList $scriptPath -NoNewWindow

Write-Host "Overlay launched!" -ForegroundColor Green
