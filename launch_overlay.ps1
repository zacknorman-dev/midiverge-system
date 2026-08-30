# Launch MIDI Overlay
# Simple launcher without cache clearing

Write-Host "Starting MIDI Overlay..." -ForegroundColor Cyan

# Navigate to the script directory
Set-Location "C:\Users\zackn\Documents\midi overlay"

# Launch the Python overlay directly (shows errors if any)
python main.py

# If we get here, Python exited (either crashed or user closed)
Write-Host ""
Write-Host "Overlay closed." -ForegroundColor Yellow
Read-Host "Press Enter to exit"
