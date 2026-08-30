# Quick check: Did the scan update?
$json = Get-Item "C:\Users\zackn\Local Ableton\PMC Set 6 Project\PMC Set 20_midi_map_scan.json"
$user = Get-Item "C:\Users\zackn\Local Ableton\PMC Set 6 Project\user_param_mappings.json"

Write-Host "`n=== FILE TIMESTAMPS ==="
Write-Host "Scanner JSON: $($json.LastWriteTime)"
Write-Host "User mappings: $($user.LastWriteTime)"

if ($json.LastWriteTime -gt $user.LastWriteTime) {
    Write-Host "`n✓ SCANNER IS UP TO DATE!" -ForegroundColor Green
    Write-Host "Your learned names should now appear in the overlay"
} else {
    Write-Host "`n⚠ SCANNER IS STALE" -ForegroundColor Yellow
    Write-Host "Save your Ableton project (Ctrl+S) to trigger a new scan"
}
