# Full MIDIverge recovery workflow.
# Run this file through Restart MIDIverge System.bat.

$ErrorActionPreference = 'Stop'

$workspace = 'C:\Users\zackn\Documents\midi overlay'
$sourceScript = Join-Path $workspace 'remote_scripts\MIDIverge\__init__.py'
$deployedDirectory = 'C:\Users\zackn\Music\Ableton\User Library\Remote Scripts\MIDIverge'
$deployedScript = Join-Path $deployedDirectory '__init__.py'
$cacheDirectory = Join-Path $deployedDirectory '__pycache__'
$overlayScript = Join-Path $workspace 'main.py'

function Write-Step($message) {
    Write-Host "`n$message" -ForegroundColor Cyan
}

Write-Host '========================================' -ForegroundColor Cyan
Write-Host '  MIDIverge System Recovery' -ForegroundColor Cyan
Write-Host '========================================' -ForegroundColor Cyan

if (-not (Test-Path $sourceScript)) {
    throw "MIDIverge source file is missing: $sourceScript"
}

if (-not (Test-Path $deployedDirectory)) {
    throw "MIDIverge deployment folder is missing: $deployedDirectory"
}

Write-Step '1. Stopping the existing overlay...'
$overlayProcesses = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match '^python(\.exe)?$' -and $_.CommandLine -match 'main\.py'
}

foreach ($process in $overlayProcesses) {
    Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
}
Write-Host 'Overlay stopped.' -ForegroundColor Green

Write-Step '2. Synchronizing MIDIverge to Ableton...'
Copy-Item $sourceScript -Destination $deployedScript -Force
$sourceHash = (Get-FileHash $sourceScript).Hash
$deployedHash = (Get-FileHash $deployedScript).Hash
if ($sourceHash -ne $deployedHash) {
    throw 'MIDIverge deployment verification failed.'
}
Write-Host 'Deployed script verified.' -ForegroundColor Green

Write-Step '3. Clearing MIDIverge cache...'
if (Test-Path $cacheDirectory) {
    Remove-Item $cacheDirectory -Recurse -Force
}
Write-Host 'MIDIverge cache cleared.' -ForegroundColor Green

Write-Step '4. Starting one fresh overlay...'
$pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
if (-not $pythonCommand -or -not $pythonCommand.Source) {
    throw 'python.exe was not found on PATH.'
}

Start-Process -FilePath $pythonCommand.Source -ArgumentList "`"$overlayScript`"" -WorkingDirectory $workspace
Write-Host 'Overlay started.' -ForegroundColor Green

Write-Step '5. Restart Ableton when it is safe...'
$ableton = Get-Process -Name 'Ableton Live 12 Suite' -ErrorAction SilentlyContinue
if ($ableton) {
    Write-Host 'Ableton is still open. Close it normally, then start it again.' -ForegroundColor Yellow
} else {
    Write-Host 'Start Ableton now.' -ForegroundColor Yellow
}

Write-Host "`nRecovery complete: overlay restarted, deployed MIDIverge verified, and its cache cleared." -ForegroundColor Green
Read-Host 'Press Enter to close this window'
