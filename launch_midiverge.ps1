# Launch MIDIverge Overlay
# Starts the unified MIDIverge overlay UI

Write-Host "Starting MIDIverge Overlay..." -ForegroundColor Cyan

# Launch the Python overlay
$pythonPath = "python"
$scriptPath = "c:\Users\zackn\Documents\midi overlay\midiverge_overlay.py"

Start-Process -FilePath $pythonPath -ArgumentList $scriptPath -NoNewWindow

Write-Host "MIDIverge Overlay launched!" -ForegroundColor Green
