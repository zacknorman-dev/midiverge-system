# Emergency kill script for all Python processes
# Use this if overlay won't close or system is slow

Write-Host "==================================" -ForegroundColor Red
Write-Host "KILLING ALL PYTHON PROCESSES" -ForegroundColor Red  
Write-Host "==================================" -ForegroundColor Red
Write-Host ""

$processes = Get-Process python* -ErrorAction SilentlyContinue

if ($processes) {
    Write-Host "Found $($processes.Count) Python process(es):" -ForegroundColor Yellow
    $processes | ForEach-Object {
        Write-Host "  - PID $($_.Id): $($_.ProcessName) (CPU: $($_.CPU)s, Memory: $([math]::Round($_.WorkingSet/1MB,1))MB)" -ForegroundColor Cyan
    }
    Write-Host ""
    Write-Host "Killing all..." -ForegroundColor Yellow
    Stop-Process -Name python* -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 500
    Write-Host "Done!" -ForegroundColor Green
} else {
    Write-Host "No Python processes found." -ForegroundColor Green
}

Write-Host ""
Read-Host "Press Enter to exit"
