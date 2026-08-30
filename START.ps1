# ============================================
# THE ONLY OVERLAY LAUNCHER - USE THIS ONE
# ============================================

# Keep window open no matter what
$ErrorActionPreference = "Continue"

Write-Host "==================================" -ForegroundColor Cyan
Write-Host "  MIDI OVERLAY LAUNCHER" -ForegroundColor Cyan
Write-Host "==================================" -ForegroundColor Cyan
Write-Host ""

# Kill any existing Python processes
Write-Host "Killing old instances..." -ForegroundColor Yellow
Stop-Process -Name python* -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500

# Navigate to script directory
Write-Host "Navigating to: C:\Users\zackn\Documents\midi overlay" -ForegroundColor Cyan
Set-Location "C:\Users\zackn\Documents\midi overlay"

# Launch overlay
Write-Host "Starting overlay..." -ForegroundColor Green
Write-Host ""

try {
    python main.py
    Write-Host ""
    Write-Host "Overlay closed normally." -ForegroundColor Yellow
} catch {
    Write-Host ""
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""
Read-Host "Press Enter to exit"
