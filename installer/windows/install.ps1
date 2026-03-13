<#
.SYNOPSIS
    BunkerVM Windows Installer — sets up WSL2, Ubuntu, and BunkerVM
    so that `bunkervm engine start` works from any Windows terminal.

.DESCRIPTION
    Run with Administrator privileges:
        powershell -ExecutionPolicy Bypass -File install.ps1

    Steps:
      1. Check Windows version
      2. Enable WSL2 (may reboot)
      3. Install Ubuntu distro
      4. Configure .wslconfig for nested virtualisation
      5. Install BunkerVM inside WSL
      6. Download Firecracker bundle
      7. Create CLI shim on PATH
      8. (Optional) create auto-start scheduled task

.PARAMETER SkipReboot
    If set, the script will not prompt for a reboot even if WSL2 was just enabled.

.PARAMETER AutoStart
    If set, register a scheduled task to start the engine on login.

.PARAMETER Distro
    WSL distro name to use (default: Ubuntu).
#>

[CmdletBinding()]
param(
    [switch]$SkipReboot,
    [switch]$AutoStart,
    [string]$Distro = "Ubuntu"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Globals ──

$BunkerDir  = Join-Path $env:LOCALAPPDATA "BunkerVM"
$ShimPath   = Join-Path $BunkerDir "bunkervm.cmd"
$LogFile    = Join-Path $BunkerDir "install-log.txt"
$WslConfig  = Join-Path $env:USERPROFILE ".wslconfig"

# ── Helpers ──

function Write-Step($msg)  { Write-Host "  → $msg" -ForegroundColor Cyan }
function Write-Ok($msg)    { Write-Host "  ✓ $msg" -ForegroundColor Green }
function Write-Warn($msg)  { Write-Host "  ! $msg" -ForegroundColor Yellow }
function Write-Fail($msg)  { Write-Host "  ✗ $msg" -ForegroundColor Red }

function Log($msg) {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $LogFile -Value "[$timestamp] $msg"
}

function Test-Admin {
    $identity  = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]$identity
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Invoke-Wsl {
    param([string]$Script, [int]$Timeout = 120)
    $result = & wsl -d $Distro -- bash -lc $Script 2>&1
    return $result
}

# ── Main ──

Write-Host ""
Write-Host "  ╔══════════════════════════════════════╗" -ForegroundColor Magenta
Write-Host "  ║       BunkerVM Windows Installer     ║" -ForegroundColor Magenta
Write-Host "  ╚══════════════════════════════════════╝" -ForegroundColor Magenta
Write-Host ""

# Create dirs
if (-not (Test-Path $BunkerDir)) {
    New-Item -ItemType Directory -Path $BunkerDir -Force | Out-Null
}
Log "Installer started"

# ── Step 1: Check Windows version ──

Write-Step "Checking Windows version..."
$build = [System.Environment]::OSVersion.Version.Build
if ($build -lt 19041) {
    Write-Fail "Windows build $build is too old. Need build 19041+ (Windows 10 2004 or later)."
    Log "FAIL: Windows build $build < 19041"
    exit 1
}
Write-Ok "Windows build $build"
Log "Windows build: $build"

# ── Step 2: Check / Enable WSL2 ──

Write-Step "Checking WSL..."
$wslInstalled = $false
try {
    $wslVersion = & wsl --version 2>&1 | Out-String
    if ($LASTEXITCODE -eq 0) {
        $wslInstalled = $true
    }
} catch {
    $wslInstalled = $false
}

if (-not $wslInstalled) {
    Write-Step "Installing WSL2 (this may take a few minutes)..."
    Log "Installing WSL2"

    if (-not (Test-Admin)) {
        Write-Fail "WSL2 installation requires Administrator privileges."
        Write-Warn "Re-run this script as Administrator:"
        Write-Host "    powershell -ExecutionPolicy Bypass -File install.ps1" -ForegroundColor White
        exit 1
    }

    & wsl --install --no-distribution 2>&1 | Out-Null

    if (-not $SkipReboot) {
        Write-Warn "WSL2 has been enabled. A reboot is required."
        Write-Host "    After rebooting, run this installer again." -ForegroundColor White
        Log "WSL2 installed — reboot required"

        $answer = Read-Host "  Reboot now? (y/N)"
        if ($answer -eq "y" -or $answer -eq "Y") {
            Log "Rebooting..."
            Restart-Computer -Force
        }
        exit 0
    }
}
Write-Ok "WSL2 is available"
Log "WSL2 OK"

# ── Step 3: Install distro ──

Write-Step "Checking for $Distro distro..."
$distros = & wsl --list --quiet 2>&1 | Out-String
$hasDistro = $distros -match $Distro

if (-not $hasDistro) {
    Write-Step "Installing $Distro (this may take a few minutes)..."
    Log "Installing distro: $Distro"
    & wsl --install -d $Distro 2>&1 | Out-Null

    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Failed to install $Distro distro."
        Log "FAIL: distro install failed"
        exit 1
    }
    Write-Ok "$Distro installed"
} else {
    Write-Ok "$Distro already installed"
}
Log "Distro: $Distro OK"

# ── Step 4: Configure .wslconfig ──

Write-Step "Configuring .wslconfig for nested virtualisation..."
$needsConfig = $true

if (Test-Path $WslConfig) {
    $content = Get-Content $WslConfig -Raw
    if ($content -match "nestedVirtualization\s*=\s*true") {
        $needsConfig = $false
        Write-Ok ".wslconfig already configured"
    }
}

if ($needsConfig) {
    # Append or create
    $section = @"

[wsl2]
nestedVirtualization=true
"@
    if (Test-Path $WslConfig) {
        $existing = Get-Content $WslConfig -Raw
        if ($existing -match "\[wsl2\]") {
            # Section exists — add the key under it
            $existing = $existing -replace "(\[wsl2\])", "`$1`nnestedVirtualization=true"
            Set-Content -Path $WslConfig -Value $existing
        } else {
            Add-Content -Path $WslConfig -Value $section
        }
    } else {
        Set-Content -Path $WslConfig -Value $section.TrimStart()
    }
    Write-Ok ".wslconfig updated (nestedVirtualization=true)"
    Write-Warn "Restart WSL for .wslconfig changes: wsl --shutdown && wsl"
    Log ".wslconfig updated"
}

# ── Step 5: Install BunkerVM inside WSL ──

Write-Step "Installing BunkerVM inside WSL..."
Log "Installing BunkerVM in WSL"

$wslHome = (Invoke-Wsl "echo `$HOME").Trim()
$venvDir = "$wslHome/.bunkervm/venv"
$bunkervmBin = "$venvDir/bin/bunkervm"

# Check if already installed
$testResult = & wsl -d $Distro -- test -f $bunkervmBin 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Ok "BunkerVM already installed: $bunkervmBin"
} else {
    # Create venv
    Write-Step "Creating Python venv..."
    & wsl -d $Distro -- python3 -m venv $venvDir 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Failed to create venv. Try: wsl -d $Distro -- sudo apt install python3-venv"
        Log "FAIL: venv creation"
        exit 1
    }

    # Install
    Write-Step "Running pip install bunkervm..."
    $pipBin = "$venvDir/bin/pip"
    & wsl -d $Distro -- $pipBin install bunkervm 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "pip install bunkervm failed"
        Log "FAIL: pip install"
        exit 1
    }

    Write-Ok "BunkerVM installed in WSL"
}
Log "BunkerVM in WSL: OK"

# ── Step 6: Bootstrap Firecracker bundle ──

Write-Step "Downloading Firecracker bundle (first run)..."
$bootstrapOut = & wsl -d $Distro -- $bunkervmBin info 2>&1 | Out-String
Write-Ok "Firecracker bundle ready"
Log "Bootstrap: OK"

# ── Step 7: Create CLI shim ──

Write-Step "Creating CLI shim..."
$shimContent = @"
@echo off
REM BunkerVM CLI shim — delegates to WSL
wsl -d $Distro -- $bunkervmBin %*
"@
Set-Content -Path $ShimPath -Value $shimContent -Encoding ASCII

# Add to PATH if not already there
$userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($userPath -notlike "*$BunkerDir*") {
    [Environment]::SetEnvironmentVariable("PATH", "$userPath;$BunkerDir", "User")
    Write-Ok "Added $BunkerDir to PATH (restart terminal to use)"
} else {
    Write-Ok "CLI shim already on PATH"
}
Log "CLI shim: $ShimPath"

# ── Step 8: Optional auto-start ──

if ($AutoStart) {
    Write-Step "Creating auto-start task..."
    $taskName = "BunkerVM Engine"

    $existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Ok "Scheduled task already exists"
    } else {
        $action  = New-ScheduledTaskAction `
            -Execute "wsl" `
            -Argument "-d $Distro -- $bunkervmBin engine start"
        $trigger = New-ScheduledTaskTrigger -AtLogOn
        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

        Register-ScheduledTask `
            -TaskName $taskName `
            -Action $action `
            -Trigger $trigger `
            -Settings $settings `
            -Description "Start BunkerVM engine daemon on login" `
            | Out-Null

        Write-Ok "Auto-start task created ($taskName)"
    }
    Log "Auto-start: registered"
}

# ── Done ──

Write-Host ""
Write-Host "  ╔══════════════════════════════════════╗" -ForegroundColor Green
Write-Host "  ║       Installation Complete!         ║" -ForegroundColor Green
Write-Host "  ╚══════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "  Quick start:" -ForegroundColor White
Write-Host "    bunkervm engine start        # Start the engine" -ForegroundColor Gray
Write-Host "    bunkervm engine status       # Check status" -ForegroundColor Gray
Write-Host "    bunkervm sandbox create      # Spin up a sandbox" -ForegroundColor Gray
Write-Host "    bunkervm engine stop         # Stop everything" -ForegroundColor Gray
Write-Host ""

Log "Installation complete"
