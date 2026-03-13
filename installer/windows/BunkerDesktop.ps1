# ==========================================================
#  BunkerDesktop Launcher (PowerShell)
#
#  Self-contained launcher that:
#    1. Checks WSL2 + distro
#    2. Auto-installs BunkerVM into a WSL venv if missing
#    3. Starts the engine daemon
#    4. Opens the dashboard in the default browser
#
#  No manual steps required - just run this script.
# ==========================================================

$ErrorActionPreference = "Continue"
$Host.UI.RawUI.WindowTitle = "BunkerDesktop"

# -- Configuration --
$Distro     = "Ubuntu"
$EnginePort = 9551
$StatusUrl  = "http://localhost:${EnginePort}/engine/status"
$DashUrl    = "http://localhost:${EnginePort}/dashboard"
$MaxWait    = 45   # seconds to wait for engine

function Write-Header {
    Write-Host ""
    Write-Host "  BunkerDesktop" -ForegroundColor Cyan
    Write-Host "  =============" -ForegroundColor Cyan
    Write-Host ""
}

function Test-EngineRunning {
    try {
        $null = Invoke-WebRequest -Uri $StatusUrl -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

function Get-WslHome {
    $output = & wsl -d $Distro -- bash -c 'echo $HOME' 2>$null
    if ($LASTEXITCODE -eq 0 -and $output) {
        return $output.Trim()
    }
    return "/root"
}

function Install-BunkerVM {
    param([string]$Venv)

    Write-Host "  BunkerVM not found in WSL. Setting up..." -ForegroundColor Yellow
    Write-Host ""

    # Step 1: Python
    Write-Host "  [1/3] Checking Python3..."
    & wsl -d $Distro -- bash -c "python3 --version" 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "        Installing Python3..." -ForegroundColor Gray
        & wsl -d $Distro -- bash -c "sudo apt-get update -qq && sudo apt-get install -y -qq python3 python3-venv" 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  [ERROR] Failed to install Python3." -ForegroundColor Red
            return $false
        }
    }
    Write-Host "        Python3 OK" -ForegroundColor Green

    # Step 2: Venv
    Write-Host "  [2/3] Creating virtual environment..."
    & wsl -d $Distro -- bash -c "mkdir -p ~/.bunkervm && python3 -m venv '$Venv'" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [ERROR] Failed to create venv." -ForegroundColor Red
        Write-Host "  Fix: wsl -d $Distro -- sudo apt install python3-venv -y" -ForegroundColor Gray
        return $false
    }
    Write-Host "        Venv created" -ForegroundColor Green

    # Step 3: Install package (bundled source > dev checkout > PyPI)
    Write-Host "  [3/3] Installing BunkerVM (this may take a minute)..."

    $pip = "$Venv/bin/pip"
    $scriptDir = $PSScriptRoot
    $installed = $false

    # Strategy A: Bundled source ({app}\src\pyproject.toml)
    $bundledSrc = Join-Path $scriptDir "src"
    if (Test-Path (Join-Path $bundledSrc "pyproject.toml")) {
        Write-Host "        Found bundled source..." -ForegroundColor Gray
        $wslPath = Convert-ToWslPath $bundledSrc
        if ($wslPath) {
            & wsl -d $Distro -- bash -c "rm -rf ~/.bunkervm/src && cp -r '$wslPath' ~/.bunkervm/src && cd ~/.bunkervm/src && '$pip' install --quiet . 2>&1" 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) {
                Write-Host "        Installed from bundled source" -ForegroundColor Green
                $installed = $true
            }
        }
    }

    # Strategy B: Dev checkout (../../pyproject.toml)
    if (-not $installed) {
        $devRoot = (Resolve-Path (Join-Path $scriptDir "..\..") -ErrorAction SilentlyContinue).Path
        if ($devRoot -and (Test-Path (Join-Path $devRoot "pyproject.toml"))) {
            Write-Host "        Found dev checkout..." -ForegroundColor Gray
            $wslPath = Convert-ToWslPath $devRoot
            if ($wslPath) {
                & wsl -d $Distro -- bash -c "rm -rf ~/.bunkervm/src && cp -r '$wslPath' ~/.bunkervm/src && cd ~/.bunkervm/src && '$pip' install --quiet . 2>&1" 2>$null | Out-Null
                if ($LASTEXITCODE -eq 0) {
                    Write-Host "        Installed from dev source" -ForegroundColor Green
                    $installed = $true
                }
            }
        }
    }

    # Strategy C: PyPI
    if (-not $installed) {
        Write-Host "        Trying PyPI..." -ForegroundColor Gray
        & wsl -d $Distro -- bash -c "'$pip' install --quiet bunkervm 2>&1" 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "        Installed from PyPI" -ForegroundColor Green
            $installed = $true
        }
    }

    if (-not $installed) {
        Write-Host "  [ERROR] All install strategies failed." -ForegroundColor Red
        return $false
    }

    Write-Host ""
    Write-Host "  BunkerVM installed successfully!" -ForegroundColor Green
    Write-Host ""
    return $true
}

function Convert-ToWslPath {
    param([string]$WindowsPath)
    # C:\foo\bar -> /mnt/c/foo/bar
    $p = $WindowsPath -replace '\\', '/'
    if ($p -match '^([A-Za-z]):/?(.*)$') {
        $drive = $Matches[1].ToLower()
        $rest = $Matches[2].TrimEnd('/')
        return "/mnt/$drive/$rest"
    }
    return $null
}

# ======================================
#  Main
# ======================================

Write-Header

# 1. Check WSL
Write-Host "  Checking WSL2..."
& wsl --version 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [ERROR] WSL2 is not installed." -ForegroundColor Red
    Write-Host "  Install: wsl --install" -ForegroundColor Gray
    Read-Host "  Press Enter to exit"
    exit 1
}

# 2. Check distro
& wsl -d $Distro -- echo ok 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [ERROR] WSL distro '$Distro' not found." -ForegroundColor Red
    Write-Host "  Install: wsl --install -d $Distro" -ForegroundColor Gray
    Read-Host "  Press Enter to exit"
    exit 1
}

# 3. Already running?
Write-Host "  Checking engine status..."
if (Test-EngineRunning) {
    Write-Host "  Engine is already running." -ForegroundColor Green
    Start-Process $DashUrl
    Write-Host ""
    Write-Host "  Dashboard opened: $DashUrl" -ForegroundColor Cyan
    Write-Host "  You can close this window." -ForegroundColor Gray
    Write-Host ""
    Read-Host "  Press Enter to exit" | Out-Null
    exit 0
}

# 4. Resolve paths
$wslHome = Get-WslHome
$venv = "$wslHome/.bunkervm/venv"
$bvm  = "$venv/bin/bunkervm"

# 5. Ensure BunkerVM is installed
Write-Host "  Checking BunkerVM installation..."
& wsl -d $Distro -- test -x $bvm 2>$null
if ($LASTEXITCODE -ne 0) {
    $ok = Install-BunkerVM -Venv $venv
    if (-not $ok) {
        Write-Host ""
        Write-Host "  Manual install:" -ForegroundColor Yellow
        Write-Host "    wsl -d $Distro" -ForegroundColor Gray
        Write-Host "    python3 -m venv ~/.bunkervm/venv" -ForegroundColor Gray
        Write-Host "    ~/.bunkervm/venv/bin/pip install bunkervm" -ForegroundColor Gray
        Write-Host ""
        Read-Host "  Press Enter to exit"
        exit 1
    }
}

# 6. Start engine (hidden WSL process - fully detached)
Write-Host "  Starting BunkerVM engine..."
Start-Process -WindowStyle Hidden -FilePath "wsl" -ArgumentList "-d", $Distro, "--", $bvm, "engine", "start"

# 7. Wait for engine
Write-Host "  Waiting for engine to initialize..."
$started = $false
for ($i = 1; $i -le $MaxWait; $i++) {
    Start-Sleep -Seconds 1
    if (Test-EngineRunning) {
        $started = $true
        break
    }
    Write-Host "  Waiting... ($i/$MaxWait)"
}

if (-not $started) {
    Write-Host ""
    Write-Host "  [ERROR] Engine did not start within $MaxWait seconds." -ForegroundColor Red
    Write-Host ""
    Write-Host "  Debug: run engine manually to see errors:" -ForegroundColor Yellow
    Write-Host "    wsl -d $Distro -- $bvm engine start" -ForegroundColor Gray
    Write-Host ""
    Read-Host "  Press Enter to exit"
    exit 1
}

Write-Host "  Engine started!" -ForegroundColor Green

# 8. Open dashboard
Write-Host ""
Start-Process $DashUrl
Write-Host "  Dashboard opened: $DashUrl" -ForegroundColor Cyan
Write-Host ""
Write-Host "  BunkerDesktop is running." -ForegroundColor Green
Write-Host "  You can close this window - the engine keeps running." -ForegroundColor Gray
Write-Host ""
Write-Host "  Stop engine: wsl -d $Distro -- $bvm engine stop" -ForegroundColor Gray
Write-Host ""
Read-Host "  Press Enter to exit" | Out-Null
