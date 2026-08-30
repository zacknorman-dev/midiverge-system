# Clear Python cache from deployed Remote Scripts
# Run this after making changes to force Ableton to reload

$scriptPath = "C:\Users\zackn\Music\Ableton\User Library\Remote Scripts"

Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "  Clearing Remote Script Cache" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan

if (Test-Path $scriptPath) {
    Get-ChildItem $scriptPath -Recurse -Filter "__pycache__" -Directory | ForEach-Object {
        Write-Host "🗑️  Clearing: $($_.FullName)" -ForegroundColor Yellow
        Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
    }
    Write-Host "✅ All cache cleared!" -ForegroundColor Green
} else {
    Write-Host "❌ Remote Scripts folder not found: $scriptPath" -ForegroundColor Red
}

Write-Host ""
Write-Host "📝 Next: Restart Ableton to reload scripts" -ForegroundColor Cyan
