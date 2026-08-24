# Deploy script - keeps trying to copy until successful
# Run this immediately after plugging in the XIAO

$source = "c:\Users\zackn\Documents\midi overlay\xiao_controller\code.py"
$dest = "D:\code.py"

Write-Host "Waiting for D: drive and trying to copy..."
for ($i = 0; $i -lt 50; $i++) {
    try {
        Copy-Item $source -Destination $dest -Force -ErrorAction Stop
        Write-Host "SUCCESS! File deployed." -ForegroundColor Green
        exit 0
    } catch {
        Start-Sleep -Milliseconds 100
    }
}
Write-Host "FAILED - drive is locked. Unplug and replug XIAO, then run this script immediately." -ForegroundColor Red
