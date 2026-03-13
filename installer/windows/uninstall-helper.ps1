# BunkerDesktop — Uninstall Helper
# Called during Inno Setup uninstallation to clean up WSL resources.

Write-Host "Cleaning up BunkerDesktop..." -ForegroundColor Cyan

# Stop engine
try {
    Invoke-WebRequest -Uri "http://localhost:9551/engine/stop" -Method POST -TimeoutSec 5 -ErrorAction SilentlyContinue | Out-Null
    Write-Host "  Engine stopped" -ForegroundColor Green
} catch {
    Write-Host "  Engine was not running" -ForegroundColor Gray
}

# Remove scheduled task
try {
    Unregister-ScheduledTask -TaskName "BunkerVM Engine" -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "  Scheduled task removed" -ForegroundColor Green
} catch {}

Write-Host ""
$answer = Read-Host "Remove BunkerVM from WSL too? This deletes ~/.bunkervm (y/N)"
if ($answer -match "^[yY]$") {
    & wsl -d Ubuntu -- rm -rf "~/.bunkervm" 2>$null
    Write-Host "  WSL data removed" -ForegroundColor Green
}

Write-Host ""
Write-Host "Cleanup complete." -ForegroundColor Green
