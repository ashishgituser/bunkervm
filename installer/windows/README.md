# BunkerDesktop Windows Installer

> Install BunkerDesktop on Windows — engine, dashboard, and CLI — with one click.

## Two Installation Methods

### Method 1: PowerShell Script (Quick, No Extra Tools)

Run directly from the checkout — no compilation or extra software needed:

```powershell
# Open PowerShell as Administrator
cd NervOS\installer\windows
powershell -ExecutionPolicy Bypass -File install-desktop.ps1
```

Options:
```powershell
# With auto-start on login
install-desktop.ps1 -AutoStart

# Custom install location
install-desktop.ps1 -InstallDir "D:\MyApps\BunkerDesktop"

# Skip reboot prompt
install-desktop.ps1 -SkipReboot
```

### Method 2: Inno Setup Installer (Professional .exe)

Builds a proper `BunkerDesktopSetup.exe` with wizard, license, and uninstaller:

```powershell
# 1. Install Inno Setup 6 from https://jrsoftware.org/isdl.php
# 2. Build the installer:
.\build-installer.ps1

# 3. Run the generated installer:
.\Output\BunkerDesktopSetup-0.8.3.exe
```

## Prerequisites (handled automatically)

| Requirement | Minimum | Notes |
|---|---|---|
| Windows | 10 build 19041+ or 11 | WSL2 support required |
| Processor | x86_64 with VT-x | Virtualisation must be enabled in BIOS |
| RAM | 4 GB (8 GB recommended) | Engine + VMs need headroom |

## What Gets Installed

```
%LOCALAPPDATA%\BunkerDesktop\
    BunkerDesktop.cmd          ← Launcher (starts engine + opens dashboard)
    bunkervm.cmd               ← CLI shim (delegates to WSL)
    uninstall.ps1              ← Uninstaller
    install-log.txt            ← Installation log
    dashboard\                 ← Web dashboard files
        index.html
        styles.css
        app.js

Start Menu\Programs\BunkerDesktop\
    BunkerDesktop.lnk          ← Start Menu shortcut

Desktop\
    BunkerDesktop.lnk          ← Desktop shortcut

WSL (Ubuntu) ~/.bunkervm\
    venv\                      ← Python venv with bunkervm
    bundle\                    ← Firecracker + vmlinux + rootfs
    engine\                    ← Runtime PID file, state
```

## How to Use (After Install)

```
1. Double-click "BunkerDesktop" on your Desktop
2. Engine starts automatically via WSL2
3. Dashboard opens at http://localhost:9551/dashboard
4. Create sandboxes, run commands, manage VMs
```

CLI:
```powershell
bunkervm engine start        # Start the engine
bunkervm engine status       # Check status
bunkervm sandbox create      # Create a sandbox
bunkervm engine stop         # Stop everything
```

## Uninstall

**From Settings:** Settings → Apps → BunkerDesktop → Uninstall

**From CLI:**
```powershell
powershell -File "%LOCALAPPDATA%\BunkerDesktop\uninstall.ps1"
```

## File Map

```
installer/windows/
    install-desktop.ps1        ← PowerShell installer (standalone, recommended)
    install.ps1                ← Legacy M4 WSL-only installer
    build-installer.ps1        ← Builds the Inno Setup .exe
    BunkerDesktopSetup.iss     ← Inno Setup script
    BunkerDesktop.cmd          ← Launcher template
    uninstall-helper.ps1       ← Cleanup for Inno uninstall
    README.md                  ← This file
    assets/                    ← App icon
    Output/                    ← Generated installer
```

```
