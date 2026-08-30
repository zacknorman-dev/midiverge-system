# Remove Ghost MIDI Devices - Run as Administrator
# This script removes MIDI devices stuck in "Unknown" status that are blocking Ableton

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Ghost MIDI Device Removal Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if running as admin
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERROR: This script must be run as Administrator!" -ForegroundColor Red
    Write-Host "Right-click this script and select 'Run as Administrator'" -ForegroundColor Yellow
    pause
    exit
}

Write-Host "Finding ghost MIDI devices..." -ForegroundColor Yellow
Write-Host ""

# Get all Unknown MIDI-related devices
$ghostDevices = Get-PnpDevice | Where-Object { 
    $_.Status -eq "Unknown" -and (
        $_.FriendlyName -like "*MIDI*" -or 
        $_.FriendlyName -like "*Pico*" -or 
        $_.FriendlyName -like "*loopMIDI*" -or 
        $_.FriendlyName -like "*teVirtual*" -or 
        $_.FriendlyName -like "*KeyLab*" -or 
        $_.FriendlyName -like "*CircuitPython*"
    )
}

if ($ghostDevices.Count -eq 0) {
    Write-Host "No ghost MIDI devices found!" -ForegroundColor Green
    pause
    exit
}

Write-Host "Found $($ghostDevices.Count) ghost devices:" -ForegroundColor Yellow
Write-Host ""
$ghostDevices | ForEach-Object { Write-Host "  - $($_.FriendlyName)" -ForegroundColor White }
Write-Host ""

$response = Read-Host "Do you want to remove these devices? (y/n)"
if ($response -ne "y" -and $response -ne "Y") {
    Write-Host "Cancelled." -ForegroundColor Yellow
    pause
    exit
}

Write-Host ""
Write-Host "Removing devices..." -ForegroundColor Yellow
$removed = 0
$failed = 0

foreach ($device in $ghostDevices) {
    Write-Host "Removing: $($device.FriendlyName)..." -NoNewline
    try {
        $result = pnputil /remove-device $device.InstanceId 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host " OK" -ForegroundColor Green
            $removed++
        } else {
            Write-Host " FAILED" -ForegroundColor Red
            $failed++
        }
    } catch {
        Write-Host " ERROR" -ForegroundColor Red
        $failed++
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Summary:" -ForegroundColor Cyan
Write-Host "  Removed: $removed" -ForegroundColor Green
Write-Host "  Failed:  $failed" -ForegroundColor $(if ($failed -gt 0) { "Red" } else { "Green" })
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if ($removed -gt 0) {
    Write-Host "SUCCESS! Ghost devices removed." -ForegroundColor Green
    Write-Host "You should now be able to start Ableton Live." -ForegroundColor Green
    Write-Host ""
    Write-Host "Note: You may need to restart Windows for changes to fully take effect." -ForegroundColor Yellow
} else {
    Write-Host "No devices were removed. You may need to manually remove them from Device Manager." -ForegroundColor Yellow
}

Write-Host ""
pause
