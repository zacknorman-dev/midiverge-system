# Verify Active Files Script
# Run this anytime to verify you're working with the correct file versions

Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "  MIDIverge File Verification" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host ""

$allGood = $true

# ──────────────────────────────────────────────────────────────
# Check 1: MIDIverge __init__.py
# ──────────────────────────────────────────────────────────────
Write-Host "1️⃣  Checking remote_scripts\MIDIverge\__init__.py..." -ForegroundColor Yellow

$initPath = "remote_scripts\MIDIverge\__init__.py"
if (-not (Test-Path $initPath)) {
    Write-Host "   ❌ MISSING!" -ForegroundColor Red
    $allGood = $false
} else {
    $header = Get-Content $initPath -First 10 | Select-String "MIDIverge - Unified MIDI Controller"
    $functions = Select-String -Path $initPath -Pattern "def receive_midi|def _save_track_by_index|def _restore_current_track" -Quiet
    $imports = Select-String -Path $initPath -Pattern "from _Framework.ControlSurface import ControlSurface" -Quiet
    
    if ($header -and $functions -and $imports) {
        Write-Host "   ✅ CORRECT - MIDIverge unified control surface" -ForegroundColor Green
        $file = Get-Item $initPath
        Write-Host "      Size: $($file.Length) bytes, Modified: $($file.LastWriteTime)" -ForegroundColor DarkGray
    } else {
        Write-Host "   ❌ WRONG VERSION - Missing expected header or functions" -ForegroundColor Red
        $allGood = $false
    }
}
Write-Host ""

# ──────────────────────────────────────────────────────────────
# Check 2: main.py
# ──────────────────────────────────────────────────────────────
Write-Host "2️⃣  Checking main.py..." -ForegroundColor Yellow

$mainPath = "main.py"
if (-not (Test-Path $mainPath)) {
    Write-Host "   ❌ MISSING!" -ForegroundColor Red
    $allGood = $false
} else {
    $header = Get-Content $mainPath -First 10 | Select-String "Ableton MIDI Overlay - Simple Real-Time Display"
    $features = Select-String -Path $mainPath -Pattern "class MIDIOverlay|def udp_listener|9001" -Quiet
    $imports = Select-String -Path $mainPath -Pattern "import tkinter" -Quiet
    
    if ($header -and $features -and $imports) {
        Write-Host "   ✅ CORRECT - Overlay UI application" -ForegroundColor Green
        $file = Get-Item $mainPath
        Write-Host "      Size: $($file.Length) bytes, Modified: $($file.LastWriteTime)" -ForegroundColor DarkGray
    } else {
        Write-Host "   ❌ WRONG VERSION - Missing expected header or features" -ForegroundColor Red
        $allGood = $false
    }
}
Write-Host ""

# ──────────────────────────────────────────────────────────────
# Check 3: manual_mappings.json
# ──────────────────────────────────────────────────────────────
Write-Host "3️⃣  Checking manual_mappings.json..." -ForegroundColor Yellow

$mappingsPath = "manual_mappings.json"
if (-not (Test-Path $mappingsPath)) {
    Write-Host "   ❌ MISSING!" -ForegroundColor Red
    $allGood = $false
} else {
    try {
        $json = Get-Content $mappingsPath -Raw | ConvertFrom-Json
        $count = ($json | Get-Member -MemberType NoteProperty).Count
        Write-Host "   ✅ VALID - Contains $count mappings" -ForegroundColor Green
        $file = Get-Item $mappingsPath
        Write-Host "      Modified: $($file.LastWriteTime)" -ForegroundColor DarkGray
    } catch {
        Write-Host "   ❌ INVALID JSON!" -ForegroundColor Red
        $allGood = $false
    }
}
Write-Host ""

# ──────────────────────────────────────────────────────────────
# Summary
# ──────────────────────────────────────────────────────────────
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan

if ($allGood) {
    Write-Host "  ✅ ALL FILES VERIFIED!" -ForegroundColor Green
    Write-Host "     You are working with the correct versions." -ForegroundColor Green
} else {
    Write-Host "  ❌ VERIFICATION FAILED!" -ForegroundColor Red
    Write-Host "     Some files are missing or incorrect." -ForegroundColor Red
    Write-Host "     Check git status or restore from repository." -ForegroundColor Yellow
}

Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host ""
