<#
.SYNOPSIS
    BunkerDesktop Windows Installer — complete installation of BunkerDesktop
    with WSL2 backend, engine, dashboard, and desktop shortcuts.

.DESCRIPTION
    Run with Administrator privileges:
        powershell -ExecutionPolicy Bypass -File install-desktop.ps1

    This installer:
      1. Checks Windows version and prerequisites
      2. Enables WSL2 and installs Ubuntu (if needed)
      3. Configures nested virtualisation for KVM
      4. Installs BunkerVM Python package inside WSL
      5. Downloads Firecracker bundle
      6. Deploys BunkerDesktop dashboard files
      7. Creates CLI shim, launcher, and desktop shortcuts
      8. Registers uninstaller in Add/Remove Programs
      9. (Optional) auto-start engine on login

.PARAMETER SkipReboot
    Skip reboot prompt even if WSL2 was just enabled.

.PARAMETER AutoStart
    Register a scheduled task to start the engine on login.

.PARAMETER Distro
    WSL distro name (default: Ubuntu).

.PARAMETER InstallDir
    Installation directory (default: %LOCALAPPDATA%\BunkerDesktop).
#>

[CmdletBinding()]
param(
    [switch]$SkipReboot,
    [switch]$AutoStart,
    [string]$Distro = "Ubuntu",
    [string]$InstallDir = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ══════════════════════════════════════
#  Constants
# ══════════════════════════════════════

$AppName        = "BunkerDesktop"
$AppVersion     = "0.7.2"
$AppPublisher   = "BunkerVM"
$AppExe         = "BunkerDesktop.cmd"

if (-not $InstallDir) {
    $InstallDir = Join-Path $env:LOCALAPPDATA $AppName
}

$DashboardDir   = Join-Path $InstallDir "dashboard"
$LogFile        = Join-Path $InstallDir "install-log.txt"
$ShimPath       = Join-Path $InstallDir "bunkervm.cmd"
$LauncherPath   = Join-Path $InstallDir $AppExe
$UninstallerPath= Join-Path $InstallDir "uninstall.ps1"
$WslConfig      = Join-Path $env:USERPROFILE ".wslconfig"
$StartMenuDir   = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\$AppName"
$DesktopShortcut= Join-Path ([Environment]::GetFolderPath("Desktop")) "$AppName.lnk"
$RegistryPath   = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$AppName"

# ── Source paths (relative to this script) ──
$ScriptDir      = $PSScriptRoot
$ProjectRoot    = Split-Path (Split-Path $ScriptDir -Parent) -Parent
$DesktopSrc     = Join-Path $ProjectRoot "desktop\src"

# ══════════════════════════════════════
#  Helpers
# ══════════════════════════════════════

function Write-Banner {
    Write-Host ""
    Write-Host "  ╔══════════════════════════════════════════╗" -ForegroundColor Magenta
    Write-Host "  ║       BunkerDesktop Windows Installer    ║" -ForegroundColor Magenta
    Write-Host "  ║              Version $AppVersion                ║" -ForegroundColor DarkMagenta
    Write-Host "  ╚══════════════════════════════════════════╝" -ForegroundColor Magenta
    Write-Host ""
}

function Write-Step($n, $msg)  { Write-Host "  [$n] $msg" -ForegroundColor Cyan }
function Write-Ok($msg)        { Write-Host "      ✓ $msg" -ForegroundColor Green }
function Write-Warn($msg)      { Write-Host "      ! $msg" -ForegroundColor Yellow }
function Write-Fail($msg)      { Write-Host "      ✗ $msg" -ForegroundColor Red }
function Write-Info($msg)      { Write-Host "      $msg" -ForegroundColor Gray }

function Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $LogFile -Value "[$ts] $msg" -ErrorAction SilentlyContinue
}

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $pr = [Security.Principal.WindowsPrincipal]$id
    return $pr.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Invoke-Wsl {
    param([string]$Script, [int]$Timeout = 120)
    return (& wsl -d $Distro -- bash -lc $Script 2>&1)
}

function New-Shortcut($Path, $Target, $Arguments, $Icon, $Description) {
    $shell = New-Object -ComObject WScript.Shell
    $sc = $shell.CreateShortcut($Path)
    $sc.TargetPath = $Target
    if ($Arguments) { $sc.Arguments = $Arguments }
    if ($Icon)      { $sc.IconLocation = $Icon }
    if ($Description) { $sc.Description = $Description }
    $sc.WorkingDirectory = $InstallDir
    $sc.Save()
}

# ══════════════════════════════════════
#  Main Installation
# ══════════════════════════════════════

Write-Banner

# Create install directory
if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
}
Log "=== BunkerDesktop Installer v$AppVersion started ==="
Log "Install directory: $InstallDir"

$stepTotal = 9
$step = 0

# ────────────────────────────────────
#  Step 1: Check Windows version
# ────────────────────────────────────
$step++
Write-Step $step "Checking Windows version..."

$build = [System.Environment]::OSVersion.Version.Build
if ($build -lt 19041) {
    Write-Fail "Windows build $build is too old. Need 19041+ (Windows 10 2004 or later)."
    Log "FAIL: build $build"
    exit 1
}
Write-Ok "Windows build $build ✔"
Log "Build: $build"

# ────────────────────────────────────
#  Step 2: Check / Enable WSL2
# ────────────────────────────────────
$step++
Write-Step $step "Checking WSL2..."

$wslReady = $false
try {
    $null = & wsl --version 2>&1
    if ($LASTEXITCODE -eq 0) { $wslReady = $true }
} catch {}

if (-not $wslReady) {
    if (-not (Test-Admin)) {
        Write-Fail "WSL2 installation requires Administrator privileges."
        Write-Info "Re-run: powershell -ExecutionPolicy Bypass -File install-desktop.ps1"
        exit 1
    }
    Write-Info "Installing WSL2 (this takes 2-5 minutes)..."
    Log "Installing WSL2"
    & wsl --install --no-distribution 2>&1 | Out-Null

    if (-not $SkipReboot) {
        Write-Warn "WSL2 enabled. A reboot is required before continuing."
        Write-Info "After rebooting, run this installer again."
        Log "Reboot required for WSL2"
        $answer = Read-Host "      Reboot now? (y/N)"
        if ($answer -match "^[yY]$") {
            Log "Rebooting"
            Restart-Computer -Force
        }
        exit 0
    }
}
Write-Ok "WSL2 is available"
Log "WSL2: OK"

# ────────────────────────────────────
#  Step 3: Install distro
# ────────────────────────────────────
$step++
Write-Step $step "Checking $Distro distro..."

$distroList = & wsl --list --quiet 2>&1 | Out-String
if ($distroList -notmatch $Distro) {
    Write-Info "Installing $Distro (this takes 3-10 minutes)..."
    Log "Installing $Distro"
    & wsl --install -d $Distro 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Failed to install $Distro"
        Log "FAIL: distro"
        exit 1
    }
    Write-Ok "$Distro installed"
} else {
    Write-Ok "$Distro already installed"
}
Log "Distro: $Distro OK"

# ────────────────────────────────────
#  Step 4: Configure .wslconfig
# ────────────────────────────────────
$step++
Write-Step $step "Configuring nested virtualisation..."

$needsWslConfig = $true
if (Test-Path $WslConfig) {
    $wslContent = Get-Content $WslConfig -Raw
    if ($wslContent -match "nestedVirtualization\s*=\s*true") {
        $needsWslConfig = $false
    }
}

if ($needsWslConfig) {
    $wslSection = "`n[wsl2]`nnestedVirtualization=true`n"
    if (Test-Path $WslConfig) {
        $existing = Get-Content $WslConfig -Raw
        if ($existing -match "\[wsl2\]") {
            $existing = $existing -replace "(\[wsl2\])", "`$1`nnestedVirtualization=true"
            Set-Content -Path $WslConfig -Value $existing
        } else {
            Add-Content -Path $WslConfig -Value $wslSection
        }
    } else {
        Set-Content -Path $WslConfig -Value "[wsl2]`nnestedVirtualization=true"
    }
    Write-Ok ".wslconfig updated"
    Write-Warn "Run 'wsl --shutdown' if WSL was already running"
} else {
    Write-Ok ".wslconfig already configured"
}
Log ".wslconfig: OK"

# ────────────────────────────────────
#  Step 5: Install BunkerVM in WSL
# ────────────────────────────────────
$step++
Write-Step $step "Installing BunkerVM in WSL..."

$wslHome = (Invoke-Wsl "echo `$HOME").Trim()
$venvDir = "$wslHome/.bunkervm/venv"
$bvmBin  = "$venvDir/bin/bunkervm"

# Determine where to install from:
#  1. Bundled source (installer deployed {app}\src\pyproject.toml)
#  2. Development checkout (..\..\pyproject.toml)
#  3. PyPI fallback (production)
$bundledSrc  = Join-Path $InstallDir "src"
$devRoot     = $ProjectRoot
$wslSrcDir   = "$wslHome/.bunkervm/src"

$testBin = & wsl -d $Distro -- test -f $bvmBin 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Ok "BunkerVM already installed"
    Write-Info "Reinstalling to pick up any updates..."
} else {
    Write-Info "Creating Python venv..."
    & wsl -d $Distro -- bash -c "mkdir -p ~/.bunkervm && python3 -m venv $venvDir" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Failed to create venv."
        Write-Info "Fix: wsl -d $Distro -- sudo apt install python3 python3-venv -y"
        Log "FAIL: venv"
        exit 1
    }
    Write-Ok "Virtual environment created"
}

# Pick source location (bundled > dev checkout > PyPI)
$sourceFound = $false
$sourceLabel = ""
$winSourceDir = ""

if (Test-Path (Join-Path $bundledSrc "pyproject.toml")) {
    $winSourceDir = $bundledSrc
    $sourceLabel  = "bundled source"
    $sourceFound  = $true
} elseif (Test-Path (Join-Path $devRoot "pyproject.toml")) {
    $winSourceDir = $devRoot
    $sourceLabel  = "development checkout"
    $sourceFound  = $true
}

if ($sourceFound) {
    Write-Info "Installing from $sourceLabel..."
    # Convert Windows path for wslpath usage
    $escapedPath = $winSourceDir -replace "'", "'\''"
    & wsl -d $Distro -- bash -c "rm -rf '$wslSrcDir' && cp -r `$(wslpath -u '$escapedPath') '$wslSrcDir'" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Failed to copy source to WSL"
        Log "FAIL: copy source"
        exit 1
    }
    & wsl -d $Distro -- bash -c "cd '$wslSrcDir' && '$venvDir/bin/pip' install --quiet ." 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "pip install from $sourceLabel failed"
        Log "FAIL: pip from $sourceLabel"
        exit 1
    }
    Write-Ok "BunkerVM installed from $sourceLabel"
} else {
    # No local source — try PyPI
    Write-Info "Installing from PyPI..."
    & wsl -d $Distro -- bash -c "'$venvDir/bin/pip' install --quiet bunkervm" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "pip install from PyPI failed. Package may not be published yet."
        Write-Info "Place project source at: $bundledSrc"
        Log "FAIL: pip from PyPI"
        exit 1
    }
    Write-Ok "BunkerVM installed from PyPI"
}
Log "BunkerVM WSL: OK"

# ────────────────────────────────────
#  Step 6: Bootstrap Firecracker
# ────────────────────────────────────
$step++
Write-Step $step "Downloading Firecracker bundle..."

$null = & wsl -d $Distro -- $bvmBin info 2>&1
Write-Ok "Firecracker bundle ready"
Log "Bootstrap: OK"

# ────────────────────────────────────
#  Step 7: Deploy Dashboard Files
# ────────────────────────────────────
$step++
Write-Step $step "Deploying BunkerDesktop dashboard..."

if (-not (Test-Path $DashboardDir)) {
    New-Item -ItemType Directory -Path $DashboardDir -Force | Out-Null
}

if (Test-Path $DesktopSrc) {
    # Copy from source checkout
    Copy-Item -Path "$DesktopSrc\*" -Destination $DashboardDir -Recurse -Force
    Write-Ok "Dashboard deployed from source"
} else {
    Write-Warn "Desktop source not found at $DesktopSrc"
    Write-Info "Dashboard will be served by engine. You can copy files later."
}
Log "Dashboard: deployed to $DashboardDir"

# ── Launcher: keep the bundled BunkerDesktop.cmd (don't overwrite) ──
if (Test-Path $LauncherPath) {
    Write-Ok "Launcher already deployed (keeping bundled version)"
} else {
    # Fallback: copy from source if available
    $srcLauncher = Join-Path $ScriptDir "BunkerDesktop.cmd"
    if (Test-Path $srcLauncher) {
        Copy-Item $srcLauncher $LauncherPath -Force
        Write-Ok "Launcher deployed from installer"
    } else {
        Write-Warn "No launcher found — BunkerDesktop.cmd missing"
    }
}
Log "Launcher: $LauncherPath"

# ── CLI shim ──
$shimContent = @"
@echo off
wsl -d $Distro -- $bvmBin %*
"@
Set-Content -Path $ShimPath -Value $shimContent -Encoding ASCII
Write-Ok "CLI shim created"
Log "CLI shim: $ShimPath"

# Add to PATH
$userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($userPath -notlike "*$InstallDir*") {
    [Environment]::SetEnvironmentVariable("PATH", "$userPath;$InstallDir", "User")
    Write-Ok "Added to PATH (restart terminal to use)"
} else {
    Write-Ok "Already on PATH"
}
Log "PATH: updated"

# ────────────────────────────────────
#  Step 8: Create Shortcuts
# ────────────────────────────────────
$step++
Write-Step $step "Creating shortcuts..."

# Start Menu
if (-not (Test-Path $StartMenuDir)) {
    New-Item -ItemType Directory -Path $StartMenuDir -Force | Out-Null
}

# Main shortcut
$scMain = Join-Path $StartMenuDir "$AppName.lnk"
New-Shortcut -Path $scMain `
    -Target "cmd.exe" `
    -Arguments "/c `"$LauncherPath`"" `
    -Description "Launch BunkerDesktop dashboard"
Write-Ok "Start Menu shortcut created"

# Desktop shortcut
New-Shortcut -Path $DesktopShortcut `
    -Target "cmd.exe" `
    -Arguments "/c `"$LauncherPath`"" `
    -Description "Launch BunkerDesktop dashboard"
Write-Ok "Desktop shortcut created"
Log "Shortcuts: OK"

# ────────────────────────────────────
#  Step 9: Register Uninstaller
# ────────────────────────────────────
$step++
Write-Step $step "Registering application..."

# Create uninstaller script
$uninstallScript = @'
# BunkerDesktop Uninstaller
$AppName = "BunkerDesktop"
$InstallDir = Split-Path $MyInvocation.MyCommand.Path -Parent
$StartMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\$AppName"
$DesktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "$AppName.lnk"
$RegistryPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$AppName"

Write-Host ""
Write-Host "  Uninstalling BunkerDesktop..." -ForegroundColor Cyan
Write-Host ""

# Stop engine
try {
    $null = Invoke-WebRequest -Uri "http://localhost:9551/engine/stop" -Method POST -TimeoutSec 5 -ErrorAction SilentlyContinue
    Write-Host "  ✓ Engine stopped" -ForegroundColor Green
} catch {
    Write-Host "  - Engine was not running" -ForegroundColor Gray
}

# Remove shortcuts
if (Test-Path $DesktopShortcut) { Remove-Item $DesktopShortcut -Force }
if (Test-Path $StartMenuDir) { Remove-Item $StartMenuDir -Recurse -Force }
Write-Host "  ✓ Shortcuts removed" -ForegroundColor Green

# Remove from PATH
$p = [Environment]::GetEnvironmentVariable("PATH", "User")
$p = ($p -split ";" | Where-Object { $_ -ne $InstallDir }) -join ";"
[Environment]::SetEnvironmentVariable("PATH", $p, "User")
Write-Host "  ✓ Removed from PATH" -ForegroundColor Green

# Remove scheduled task
try {
    Unregister-ScheduledTask -TaskName "BunkerVM Engine" -Confirm:$false -ErrorAction SilentlyContinue
} catch {}

# Remove registry entry
if (Test-Path $RegistryPath) { Remove-Item $RegistryPath -Force }
Write-Host "  ✓ Registry cleaned" -ForegroundColor Green

# WSL venv (ask)
$answer = Read-Host "  Remove BunkerVM from WSL too? (y/N)"
if ($answer -match "^[yY]$") {
    wsl -d Ubuntu -- rm -rf "~/.bunkervm" 2>$null
    Write-Host "  ✓ WSL venv removed" -ForegroundColor Green
}

Write-Host ""
Write-Host "  BunkerDesktop uninstalled." -ForegroundColor Green
Write-Host "  You can delete $InstallDir manually." -ForegroundColor Gray
Write-Host ""
Read-Host "  Press Enter to exit"
'@
Set-Content -Path $UninstallerPath -Value $uninstallScript -Encoding UTF8
Log "Uninstaller: $UninstallerPath"

# Register in Add/Remove Programs
if (-not (Test-Path $RegistryPath)) {
    New-Item -Path $RegistryPath -Force | Out-Null
}
Set-ItemProperty -Path $RegistryPath -Name "DisplayName"     -Value $AppName
Set-ItemProperty -Path $RegistryPath -Name "DisplayVersion"  -Value $AppVersion
Set-ItemProperty -Path $RegistryPath -Name "Publisher"       -Value $AppPublisher
Set-ItemProperty -Path $RegistryPath -Name "InstallLocation" -Value $InstallDir
Set-ItemProperty -Path $RegistryPath -Name "UninstallString" -Value "powershell -ExecutionPolicy Bypass -File `"$UninstallerPath`""
Set-ItemProperty -Path $RegistryPath -Name "NoModify"        -Value 1 -Type DWord
Set-ItemProperty -Path $RegistryPath -Name "NoRepair"        -Value 1 -Type DWord
# Estimated size in KB
$size = (Get-ChildItem $InstallDir -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum / 1KB
Set-ItemProperty -Path $RegistryPath -Name "EstimatedSize"   -Value ([int]$size) -Type DWord

Write-Ok "Registered in Add/Remove Programs"
Log "Registry: $RegistryPath"

# ── Optional: Auto-start ──

if ($AutoStart) {
    Write-Info "Creating auto-start scheduled task..."
    $taskName = "BunkerVM Engine"
    $existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if (-not $existing) {
        $action  = New-ScheduledTaskAction -Execute "wsl" -Argument "-d $Distro -- $bvmBin engine start"
        $trigger = New-ScheduledTaskTrigger -AtLogOn
        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
        Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings `
            -Description "Start BunkerVM engine on login" | Out-Null
        Write-Ok "Auto-start enabled"
    } else {
        Write-Ok "Auto-start task already exists"
    }
    Log "AutoStart: OK"
}

# ══════════════════════════════════════
#  Done!
# ══════════════════════════════════════

Log "=== Installation complete ==="

Write-Host ""
Write-Host "  ╔══════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "  ║     BunkerDesktop Installed!             ║" -ForegroundColor Green
Write-Host "  ╚══════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "  Install location: $InstallDir" -ForegroundColor White
Write-Host ""
Write-Host "  How to launch:" -ForegroundColor White
Write-Host "    • Double-click 'BunkerDesktop' on your Desktop" -ForegroundColor Gray
Write-Host "    • Or find it in Start Menu → BunkerDesktop" -ForegroundColor Gray
Write-Host "    • Or from terminal: BunkerDesktop" -ForegroundColor Gray
Write-Host ""
Write-Host "  CLI commands (open a new terminal):" -ForegroundColor White
Write-Host "    bunkervm engine start        Start the engine" -ForegroundColor Gray
Write-Host "    bunkervm engine status       Check engine status" -ForegroundColor Gray
Write-Host "    bunkervm sandbox create      Create a sandbox" -ForegroundColor Gray
Write-Host "    bunkervm sandbox list        List sandboxes" -ForegroundColor Gray
Write-Host ""
Write-Host "  Uninstall:" -ForegroundColor White
Write-Host "    Settings → Apps → BunkerDesktop → Uninstall" -ForegroundColor Gray
Write-Host ""
