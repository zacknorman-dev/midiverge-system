# Deploy MIDIverge Remote Script to Ableton
# SOURCE OF TRUTH: Git repo in Documents\midi overlay\remote_scripts\MIDIverge\
# DEPLOYMENT TARGET: Music\Ableton\User Library\Remote Scripts\MIDIverge\

$source = "C:\Users\zackn\Documents\midi overlay\remote_scripts\MIDIverge\__init__.py"
$dest = "C:\Users\zackn\Music\Ableton\User Library\Remote Scripts\MIDIverge\__init__.py"
$cache = "C:\Users\zackn\Music\Ableton\User Library\Remote Scripts\MIDIverge\__pycache__"

Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "  MIDIverge Deployment Script" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan

# Check if Ableton is running
$ableton = Get-Process -Name "Ableton Live 12 Suite" -ErrorAction SilentlyContinue
if ($ableton) {
    Write-Host "⚠️  WARNING: Ableton is running!" -ForegroundColor Yellow
    Write-Host "   Close Ableton before deploying to avoid file locks" -ForegroundColor Yellow
    Write-Host ""
    $response = Read-Host "Continue anyway? (y/n)"
    if ($response -ne "y") {
        Write-Host "❌ Deployment cancelled" -ForegroundColor Red
        exit 1
    }
}

# Clear cache first
if (Test-Path $cache) {
    Write-Host "🗑️  Clearing Python cache..." -ForegroundColor Yellow
    Remove-Item $cache -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "✅ Cache cleared" -ForegroundColor Green
}

# Copy file
Write-Host "📦 Deploying MIDIverge..." -ForegroundColor Yellow
try {
    Copy-Item $source -Destination $dest -Force -ErrorAction Stop
    Write-Host "✅ MIDIverge deployed successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "📝 Next steps:" -ForegroundColor Cyan
    Write-Host "   1. Start Ableton Live" -ForegroundColor White
    Write-Host "   2. Check Preferences > MIDI > Control Surface" -ForegroundColor White
    Write-Host "   3. Verify 'MIDIverge' is enabled" -ForegroundColor White
    Write-Host ""
} catch {
    Write-Host "❌ Deployment FAILED: $_" -ForegroundColor Red
    exit 1
}
