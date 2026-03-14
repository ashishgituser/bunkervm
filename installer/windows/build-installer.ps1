<#
.SYNOPSIS
    Build the BunkerDesktop Windows installer (.exe).

.DESCRIPTION
    Two-step build:
      1. PyInstaller → BunkerDesktop.exe (native pywebview app)
      2. Inno Setup  → BunkerDesktopSetup-x.y.z.exe (installer)

    Requirements:
      - Python 3.10+ with: pip install pyinstaller pywebview
      - Inno Setup 6.x: https://jrsoftware.org/isdl.php

    Usage:
        .\build-installer.ps1
        .\build-installer.ps1 -InnoSetupPath "C:\Program Files (x86)\Inno Setup 6"
        .\build-installer.ps1 -SkipPyInstaller    # if BunkerDesktop.exe already built

.PARAMETER InnoSetupPath
    Path to Inno Setup installation directory.

.PARAMETER SkipPyInstaller
    Skip the PyInstaller step (use existing desktop\dist\BunkerDesktop.exe).
#>

param(
    [string]$InnoSetupPath = "",
    [switch]$SkipPyInstaller
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "  Building BunkerDesktop Installer" -ForegroundColor Cyan
Write-Host "  ================================" -ForegroundColor Cyan
Write-Host ""

$scriptDir = $PSScriptRoot
$rootDir = (Resolve-Path (Join-Path $scriptDir "..\..")).Path

# ── Step 1: Build BunkerDesktop.exe via PyInstaller ──
$desktopExe = Join-Path $rootDir "desktop\dist\BunkerDesktop.exe"

if ($SkipPyInstaller -and (Test-Path $desktopExe)) {
    Write-Host "  Skipping PyInstaller (using existing exe)" -ForegroundColor Yellow
} else {
    Write-Host "  Step 1: Building BunkerDesktop.exe (PyInstaller)..." -ForegroundColor Cyan

    # Check PyInstaller is installed
    $pyinstaller = Get-Command "pyinstaller" -ErrorAction SilentlyContinue
    if (-not $pyinstaller) {
        Write-Host "  ! PyInstaller not found. Install it:" -ForegroundColor Red
        Write-Host '    pip install pyinstaller pywebview' -ForegroundColor Gray
        exit 1
    }

    Push-Location (Join-Path $rootDir "desktop")
    try {
        & pyinstaller BunkerDesktop.spec --noconfirm
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  ! PyInstaller build failed" -ForegroundColor Red
            exit 1
        }
    } finally {
        Pop-Location
    }

    if (-not (Test-Path $desktopExe)) {
        Write-Host "  ! BunkerDesktop.exe was not created" -ForegroundColor Red
        exit 1
    }

    $size = [math]::Round((Get-Item $desktopExe).Length / 1MB, 2)
    Write-Host "  BunkerDesktop.exe built: $size MB" -ForegroundColor Green
}

# ── Step 2: Find Inno Setup Compiler ──
Write-Host "  Step 2: Building installer (Inno Setup)..." -ForegroundColor Cyan

# ── Find Inno Setup Compiler ──
$iscc = $null

$iscc = $null

if ($InnoSetupPath) {
    $iscc = Join-Path $InnoSetupPath "ISCC.exe"
} else {
    $candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) {
            $iscc = $c
            break
        }
    }
}

if (-not $iscc) {
    $found = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($found) { $iscc = $found.Source }
}

if (-not $iscc -or -not (Test-Path $iscc)) {
    Write-Host "  ! Inno Setup Compiler (ISCC.exe) not found." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Install Inno Setup 6 from: https://jrsoftware.org/isdl.php" -ForegroundColor White
    Write-Host "  Then run this script again, or specify the path:" -ForegroundColor White
    Write-Host '    .\build-installer.ps1 -InnoSetupPath "C:\Path\To\Inno Setup 6"' -ForegroundColor Gray
    Write-Host ""
    exit 1
}

Write-Host "  Found ISCC: $iscc" -ForegroundColor Green

# ── Ensure assets directory exists ──
$assetsDir = Join-Path $scriptDir "assets"
if (-not (Test-Path $assetsDir)) {
    New-Item -ItemType Directory -Path $assetsDir -Force | Out-Null
}

# ── Create placeholder icon if missing ──
$iconPath = Join-Path $assetsDir "icon.ico"
if (-not (Test-Path $iconPath)) {
    Write-Host "  ! No icon.ico found in assets/. Using blank placeholder." -ForegroundColor Yellow
    Write-Host "    Replace $iconPath with your real icon before release." -ForegroundColor Gray
    $icoBytes = [byte[]]@(
        0,0,1,0,1,0,16,16,2,0,0,0,1,0,56+128,0,0,0,22,0,0,0
    )
    $bih = [byte[]]@(
        40,0,0,0,16,0,0,0,32,0,0,0,1,0,1,0,0,0,0,0,0,0,0,0,
        0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
    )
    $colors = [byte[]]@(0x1A,0x10,0x06,0,0xFC,0x5C,0x7C,0)
    $xor = New-Object byte[] 64
    $and = New-Object byte[] 64
    $allBytes = $icoBytes + $bih + $colors + $xor + $and
    [System.IO.File]::WriteAllBytes($iconPath, $allBytes)
    Write-Host "  Placeholder icon created" -ForegroundColor Green
}

# ── Ensure Output directory exists ──
$outputDir = Join-Path $scriptDir "Output"
if (-not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
}

# ── Read version from pyproject.toml ──
$pyproject = Join-Path $rootDir "pyproject.toml"
$version = "0.8.3"
if (Test-Path $pyproject) {
    $match = Select-String -Path $pyproject -Pattern 'version\s*=\s*"([^"]+)"' | Select-Object -First 1
    if ($match) {
        $version = $match.Matches[0].Groups[1].Value
    }
}
Write-Host "  Version: $version" -ForegroundColor White

# ── Compile ──
$issFile = Join-Path $scriptDir "BunkerDesktopSetup.iss"
Write-Host "  Compiling installer..." -ForegroundColor Cyan

& $iscc "/DMyAppVersion=$version" $issFile
if ($LASTEXITCODE -ne 0) {
    Write-Host "  x Build failed" -ForegroundColor Red
    exit 1
}

# ── Report ──
$installer = Get-ChildItem (Join-Path $outputDir "BunkerDesktopSetup-*.exe") -ErrorAction SilentlyContinue | Select-Object -First 1
if ($installer) {
    $size = [math]::Round($installer.Length / 1MB, 2)
    Write-Host ""
    Write-Host "  Build successful!" -ForegroundColor Green
    Write-Host "    Output: $($installer.FullName)" -ForegroundColor White
    Write-Host "    Size:   $size MB" -ForegroundColor White
    Write-Host ""
    Write-Host "  To test locally:" -ForegroundColor White
    Write-Host "    .\Output\$($installer.Name)" -ForegroundColor Gray
    Write-Host ""
} else {
    Write-Host "  Build completed. Check Output\ directory." -ForegroundColor Green
}
