# BunkerDesktop — Master Implementation Plan

> **Goal:** Make BunkerVM as easy as Docker Desktop. Install BunkerDesktop → everything
> works. CLI, Python SDK, LangGraph, CrewAI, OpenAI Agents, VS Code MCP, Claude Desktop —
> all auto-discover the running engine. Users never think about WSL2, Firecracker, vsock,
> or rootfs images.
>
> **Platforms:** Windows (WSL2-backed) + Linux (native). macOS deferred.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  BunkerDesktop (Tauri — system tray + dashboard UI)     │
│  - Start/Stop engine                                    │
│  - Sandbox monitor (list, logs, resource usage)         │
│  - Settings (CPU/memory limits, auto-start)             │
└──────────────────────┬──────────────────────────────────┘
                       │ spawns & manages
┌──────────────────────▼──────────────────────────────────┐
│  Engine Daemon (bunkervm/engine/daemon.py)               │
│  - REST API on localhost:9551                            │
│  - Manages Firecracker VMs via existing vm_manager.py    │
│  - Multi-sandbox via existing multi_vm.py (VMPool)       │
│  - On Windows: runs inside WSL2, port forwarded          │
│  - On Linux: runs natively                               │
└──────────────────────┬──────────────────────────────────┘
                       │ localhost:9551
       ┌───────────────┼───────────────────┐
       ▼               ▼                   ▼
  Python SDK       CLI Client        MCP Server
  (pip install     (bunkervm run)    (Claude, VS Code)
   bunkervm)
  LangGraph / CrewAI / OpenAI Agents
```

**Key principle:** The engine daemon is the ONLY component that touches Firecracker.
Everything else is a thin HTTP client to `localhost:9551`.

---

## Decision Log

| Decision | Choice | Rationale |
|---|---|---|
| Engine API protocol | REST over HTTP on localhost:9551 | Simple, debuggable, works across WSL2 boundary |
| Desktop GUI framework | Tauri (decided later, not blocking M1-M3) | Lightweight (~5MB), reuse dashboard.py HTML/CSS/JS |
| Windows backend | WSL2 | Already provides /dev/kvm, proven path |
| macOS support | Deferred | No nested virtualization in Apple Virtualization.framework |
| SDK fallback | Direct Firecracker if engine not running | Backward compat for Linux power users |

---

## Milestone Checklist

### M1: Engine Daemon + REST API
> Foundation. Everything else is a client to this.

**New files to create:**

- [x] `bunkervm/engine/__init__.py` — Package init, version
- [x] `bunkervm/engine/daemon.py` — Main daemon process (starts HTTP server, manages VMPool)
- [x] `bunkervm/engine/api.py` — REST API route handlers (stdlib `http.server` or lightweight framework)
- [x] `bunkervm/engine/models.py` — Request/response dataclasses for API (SandboxCreateRequest, SandboxInfo, etc.)
- [x] `bunkervm/engine/config.py` — Engine-specific config (listen port, max sandboxes, resource defaults)

**API endpoints:**

- [x] `GET  /engine/status` — Engine health, version, platform, running sandbox count
- [x] `POST /engine/stop` — Graceful shutdown (stop all sandboxes, then exit)
- [x] `GET  /sandboxes` — List all running sandboxes (id, name, status, uptime, resources)
- [x] `POST /sandboxes` — Create a new sandbox (params: name, cpus, memory, network)
- [x] `GET  /sandboxes/{id}` — Get sandbox details
- [x] `DELETE /sandboxes/{id}` — Destroy a sandbox
- [x] `POST /sandboxes/{id}/exec` — Execute command (params: command, timeout, workdir)
- [x] `POST /sandboxes/{id}/write-file` — Write file (params: path, content)
- [x] `GET  /sandboxes/{id}/read-file?path=...` — Read file
- [x] `GET  /sandboxes/{id}/list-dir?path=...` — List directory
- [x] `POST /sandboxes/{id}/upload` — Upload file from host
- [x] `GET  /sandboxes/{id}/download?path=...` — Download file to host
- [x] `GET  /sandboxes/{id}/status` — VM health, CPU, RAM, disk, uptime
- [x] `POST /sandboxes/{id}/reset` — Destroy and recreate with fresh rootfs

**Code changes to existing files:**

- [x] `bunkervm/__init__.py` — Add engine discovery import
- [x] `bunkervm/cli.py` — Add `engine start`, `engine stop`, `engine status` subcommands

**Internal design:**
- Daemon wraps existing `VMPool` from `multi_vm.py` — no reinventing VM management
- Each sandbox gets a UUID + optional name
- Engine stores state in `~/.bunkervm/engine/` (pid file, sandbox metadata)
- Daemon logs to `~/.bunkervm/logs/engine.log`

**Validation:**
- [x] `bunkervm engine start` launches daemon, prints PID
- [x] `curl localhost:9551/engine/status` returns JSON with version + sandbox count
- [x] `curl -X POST localhost:9551/sandboxes -d '{"name":"test"}'` creates a sandbox
- [x] `curl -X POST localhost:9551/sandboxes/{id}/exec -d '{"command":"echo hi"}'` returns stdout
- [x] `curl -X DELETE localhost:9551/sandboxes/{id}` destroys it
- [x] `bunkervm engine stop` gracefully shuts down everything

---

### M2: SDK Refactor (Thin Client)
> `pip install bunkervm` auto-discovers engine, routes through it.

**New files to create:**

- [x] `bunkervm/engine/client.py` — `EngineClient` class + `EngineBackedClient` adapter (HTTP calls to engine REST API)
- [x] `bunkervm/engine/discovery.py` — Auto-detect running engine (check pid file, probe localhost:9551)

**Code changes to existing files:**

- [x] `bunkervm/runtime.py` — `run_code()` and `Sandbox`: check for engine first, route through `EngineClient` if available, fall back to direct Firecracker boot if not
- [x] `bunkervm/integrations/base.py` — `BunkerVMToolsBase.__init__()`: add engine auto-discovery before falling back to direct `Sandbox()` boot. New mode: no args + engine running = connect via engine
- [x] `bunkervm/sandbox_client.py` — No changes needed (engine creates the sandbox, SDK gets back connection details)
- [x] `bunkervm/__init__.py` — Expose `EngineClient`, `EngineBackedClient`, `discover_engine`, `is_engine_running`

**How auto-discovery works:**
```python
# In runtime.py / integrations/base.py:
from bunkervm.engine.discovery import find_engine

engine = find_engine()  # Returns EngineClient or None
if engine:
    # Route through engine daemon
    sandbox_id = engine.create_sandbox(cpus=1, memory=512)
    result = engine.exec(sandbox_id, command)
    engine.destroy_sandbox(sandbox_id)
else:
    # Fallback: direct Firecracker boot (current behavior)
    vm = VMManager(config)
    vm.start()
    ...
```

**Validation:**
- [x] Engine running + `from bunkervm import run_code; run_code("echo hi")` → routes through engine (visible in engine logs)
- [x] Engine NOT running + same code → falls back to direct boot (current behavior)
- [x] `BunkerVMToolkit()` (LangGraph) auto-discovers engine
- [x] `BunkerVMTools()` (OpenAI) auto-discovers engine
- [x] `BunkerVMCrewTools()` (CrewAI) auto-discovers engine
- [x] All 6 tools work identically through engine vs direct boot

---

### M3: CLI as Engine Client
> CLI talks to the running engine instead of managing VMs directly.

**Code changes to existing files:**

- [ ] `bunkervm/cli.py` — Add new subcommands:
  - `bunkervm engine start [--port 9551] [--cpus 2] [--memory 2048]`
  - `bunkervm engine stop`
  - `bunkervm engine status`
  - `bunkervm sandbox list` — table of running sandboxes
  - `bunkervm sandbox create [--name NAME] [--cpus N] [--memory N]`
  - `bunkervm sandbox exec <id|name> "command"`
  - `bunkervm sandbox destroy <id|name>`
  - `bunkervm sandbox logs <id|name>` — stream audit log for that sandbox
- [ ] `bunkervm/cli.py` — Modify existing `run` and `demo` commands to route through engine when available
- [ ] `bunkervm/__main__.py` — Ensure `engine` is in the CLI dispatch set

**Validation:**
- [ ] `bunkervm engine start` → daemon starts
- [ ] `bunkervm sandbox create --name test1` → sandbox created, ID printed
- [ ] `bunkervm sandbox list` → table shows test1 with status, uptime, resources
- [ ] `bunkervm sandbox exec test1 "uname -a"` → prints Linux kernel info
- [ ] `bunkervm run -c "print(42)"` → auto-routes through engine
- [ ] `bunkervm sandbox destroy test1` → destroyed
- [ ] `bunkervm engine stop` → all sandboxes destroyed, daemon exits

---

### M4: Windows Installer + WSL2 Auto-Setup
> One-click install on Windows. User downloads .exe, runs it, done.

**New files to create:**

- [x] `bunkervm/engine/wsl_bridge.py` — Windows-side helper:
  - Check if WSL2 is installed and enabled
  - Install Ubuntu distro if needed (silent)
  - Install bunkervm inside WSL2 (`wsl pip install bunkervm`)
  - Start engine daemon inside WSL2 (`wsl bunkervm engine start`)
  - Forward port 9551 from WSL2 to Windows localhost (automatic in WSL2)
  - Stop engine (`wsl bunkervm engine stop`)
- [x] `installer/windows/` — Installer config:
  - [x] `installer/windows/install.ps1` — PowerShell installer for WSL2 setup
  - [x] `installer/windows/README.md` — Build instructions for the installer
- [x] `bunkervm/engine/platform.py` — Platform detection (Windows vs Linux), WSL2 detection

**Code changes to existing files:**

- [x] `bunkervm/engine/daemon.py` — On Windows, raises RuntimeError (must use WSLBridge)
- [x] `bunkervm/engine/discovery.py` — On Windows, skips PID file and probes localhost:9551 (WSL2 auto-forwards)
- [x] `bunkervm/cli.py` — `bunkervm engine start` on Windows triggers WSL2 bridge flow; platform helpers refactored to use engine.platform

**Installer does:**
1. Check Windows version >= 10 build 19041
2. Enable WSL2 feature if not enabled (may need reboot)
3. Install Ubuntu WSL2 distro
4. Configure .wslconfig for nested virtualisation
5. Inside WSL2: `pip install bunkervm`, download Firecracker bundle
6. Create CLI shim on Windows PATH
7. Register startup task (optional: auto-start engine on login)

**Validation:**
- [x] Platform detection works on Windows (54/54 test_m4_windows.py on Windows)
- [x] Platform detection works in WSL (48/48 test_m4_windows.py in WSL)
- [x] WSLBridge auto-detects distro and runs commands in WSL2
- [x] `bunkervm engine start` from PowerShell → routes through WSLBridge
- [x] `bunkervm engine stop` from PowerShell → HTTP to localhost works
- [x] No regression in M1-M3 tests (54/54 test_engine.py)

**BunkerDesktop Windows Installer (post-M5):**

- [x] `installer/windows/install-desktop.ps1` — Full 9-step PowerShell installer:
  1. Windows version check (build 19041+)
  2. Enable WSL2
  3. Install Ubuntu distro
  4. Configure .wslconfig (nested virtualisation)
  5. Install BunkerVM in WSL venv
  6. Download Firecracker bundle
  7. Deploy dashboard files + launcher + CLI shim + PATH
  8. Create Start Menu + Desktop shortcuts (WScript.Shell COM)
  9. Register in Add/Remove Programs + generate uninstaller
- [x] `installer/windows/BunkerDesktop.cmd` — Launcher: starts engine via WSL, waits 30s, opens dashboard
- [x] `installer/windows/BunkerDesktopSetup.iss` — Inno Setup 6 script for professional .exe installer
- [x] `installer/windows/build-installer.ps1` — Finds ISCC.exe, creates placeholder icon, compiles .exe
- [x] `installer/windows/uninstall-helper.ps1` — Stops engine, removes scheduled task, optional WSL cleanup
- [x] `installer/windows/README.md` — Documents both install methods (PowerShell + Inno Setup)
- [x] Installer tests: 109/109 pass (test_installer_windows.py)

---

### M5: Desktop GUI (Tauri)
> System tray app with dashboard. The "BunkerDesktop" product.

**New directory:**

- [x] `desktop/` — Tauri project root
  - [x] `desktop/src-tauri/` — Rust backend (system tray, engine lifecycle)
  - [x] `desktop/src/` — Web frontend (HTML/CSS/JS — reuse dashboard.py patterns)
  - [x] `desktop/src-tauri/src/main.rs` — System tray, engine start/stop, window management
  - [x] `desktop/src/index.html` — Main dashboard page (SPA with sidebar navigation)
  - [x] `desktop/src/app.js` — Dashboard logic (poll engine API, render sandbox list)
  - [x] `desktop/src/styles.css` — Full design system (dark theme, glassmorphism, animations)

**Features:**
- [x] System tray icon (green = engine running, red = stopped, yellow = starting)
- [x] Tray menu: Start Engine / Stop Engine / Open Dashboard / Quit
- [x] Dashboard page — running sandboxes table (name, status, CPU, RAM, uptime)
- [x] Create sandbox button (name, CPU, memory fields) — modal dialog
- [x] Destroy sandbox button
- [x] Sandbox detail view — exec command via interactive terminal page
- [x] Settings page — default CPU/memory, engine port, about info
- [ ] Auto-start engine on app launch (configurable) — deferred to Tauri packaging

**Code reuse from existing codebase:**
- `dashboard.py` design language (CSS variables, dark theme) adapted for premium UI
- Engine API (`localhost:9551`) is the data source — dashboard polls every 4 seconds
- Engine API handler (`api.py`) serves dashboard at `/dashboard` route

**Validation:**
- [ ] Launch BunkerDesktop → system tray icon appears (red)
- [ ] Click "Start Engine" → icon turns green
- [ ] Open Dashboard → shows empty sandbox list
- [ ] Click "Create Sandbox" → sandbox appears in list with status
- [ ] Click sandbox → detail view, run a command, see output
- [ ] Click "Destroy" → sandbox removed
- [ ] Close BunkerDesktop → engine keeps running (tray "Quit" stops engine)

---

### M6: Linux Installer + Packaging
> Parity with Windows for Linux desktop users.

**New files to create:**

- [ ] `installer/linux/` — Packaging configs:
  - [ ] `installer/linux/bunkervm.service` — systemd unit for engine daemon
  - [ ] `installer/linux/bunkervm-desktop.desktop` — .desktop entry for GUI
  - [ ] `installer/linux/build-deb.sh` — Build .deb package
  - [ ] `installer/linux/build-rpm.sh` — Build .rpm package
  - [ ] `installer/linux/build-appimage.sh` — Build AppImage
  - [ ] `installer/linux/postinst.sh` — Post-install: add user to kvm group, download bundle

**Validation:**
- [ ] `sudo dpkg -i bunkervm-desktop.deb` → installs engine + GUI
- [ ] Engine auto-starts via systemd
- [ ] BunkerDesktop appears in application menu
- [ ] Same UX as Windows version

---

## File Map (New vs Modified)

### New files (to create):
```
bunkervm/engine/
    __init__.py
    daemon.py          ← M1
    api.py             ← M1
    models.py          ← M1
    config.py          ← M1
    client.py          ← M2
    discovery.py       ← M2
    wsl_bridge.py      ← M4
    platform.py        ← M4
installer/
    windows/           ← M4
    linux/             ← M6
desktop/               ← M5
    src-tauri/
    src/
```

### Existing files to modify:
```
bunkervm/__init__.py        ← M2 (add EngineClient export)
bunkervm/__main__.py        ← M3 (add "engine" to CLI dispatch)
bunkervm/cli.py             ← M1+M3+M4 (engine + sandbox + WSL2 bridge)
bunkervm/runtime.py         ← M2 (engine auto-discovery in run_code/Sandbox)
bunkervm/integrations/base.py ← M2 (engine auto-discovery in BunkerVMToolsBase)
bunkervm/engine/daemon.py   ← M4 (Windows guard — raises RuntimeError)
bunkervm/engine/discovery.py ← M4 (skip PID file on Windows, probe localhost)
bunkervm/engine/__init__.py ← M4 (export platform detection utilities)
```

### Files NOT modified:
```
bunkervm/sandbox_client.py  — Stays as-is (vsock/TCP to exec_agent inside VM)
bunkervm/vm_manager.py      — Stays as-is (engine daemon wraps it)
bunkervm/multi_vm.py        — Stays as-is (engine daemon uses VMPool internally)
bunkervm/mcp_server.py      — Stays as-is (MCP server becomes another engine client)
bunkervm/safety.py          — Stays as-is
bunkervm/audit.py           — Stays as-is
bunkervm/bootstrap.py       — Stays as-is (engine daemon calls it)
bunkervm/langchain.py       — Stays as-is (inherits engine discovery from base.py)
bunkervm/openai_agents.py   — Stays as-is
bunkervm/crewai.py          — Stays as-is
rootfs/                     — Stays as-is (guest code unchanged)
```

---

## Implementation Order & Dependencies

```
M1 (Engine Daemon + API)     ← START HERE
 ├── M2 (SDK Refactor)       ← depends on M1 API being stable
 ├── M3 (CLI Client)         ← depends on M1 API being stable
 ├── M4 (Windows Installer)  ← depends on M1 (engine must exist)
 └── M5 (Desktop GUI)        ← depends on M1 + M3
      └── M6 (Linux pkg)     ← depends on M5 (packages the GUI)
```

M2, M3, M4 can be built in parallel after M1 is done.
M5 depends on M1 + M3 being stable.
M6 is just packaging of M5.

---

## Current Progress

| Milestone | Status | Notes |
|---|---|---|
| M1: Engine Daemon + REST API | 🟢 Done | All 54/54 tests pass (WSL2 Ubuntu, /dev/kvm) |
| M2: SDK Refactor (thin client) | 🟢 Done | Auto-discovery, EngineBackedClient, fallback all validated |
| M3: CLI as Engine Client | 🟢 Done | `engine` + `sandbox` subcommands added to cli.py |
| M4: Windows Installer + WSL2 | � Done | platform.py, wsl_bridge.py, install.ps1; 54/54 Windows + 48/48 WSL |
| M5: Desktop GUI (Tauri) | � Done | Web frontend + Tauri scaffolding + engine serves at /dashboard |
| M6: Linux Packaging | 🔴 Not started | Blocked by M5 |

### M1 Detailed Progress

**Files created:**
- [x] `bunkervm/engine/__init__.py`
- [x] `bunkervm/engine/config.py` — EngineConfig, PID file, engine home dir
- [x] `bunkervm/engine/models.py` — SandboxCreateRequest, ExecRequest, SandboxInfo, EngineStatus, etc.
- [x] `bunkervm/engine/api.py` — EngineAPIHandler with all REST routes
- [x] `bunkervm/engine/daemon.py` — EngineDaemon wrapping VMPool

**API endpoints implemented:**
- [x] `GET  /engine/status`
- [x] `POST /engine/stop`
- [x] `GET  /sandboxes`
- [x] `POST /sandboxes`
- [x] `GET  /sandboxes/{id}`
- [x] `DELETE /sandboxes/{id}`
- [x] `POST /sandboxes/{id}/exec`
- [x] `POST /sandboxes/{id}/write-file`
- [x] `GET  /sandboxes/{id}/read-file`
- [x] `GET  /sandboxes/{id}/list-dir`
- [x] `GET  /sandboxes/{id}/status`
- [x] `POST /sandboxes/{id}/reset`

**CLI commands added (M3):**
- [x] `bunkervm engine start [--port] [--background]`
- [x] `bunkervm engine stop`
- [x] `bunkervm engine status`
- [x] `bunkervm sandbox list`
- [x] `bunkervm sandbox create [--name] [--cpus] [--memory]`
- [x] `bunkervm sandbox exec <id|name> "command"`
- [x] `bunkervm sandbox destroy <id|name>`
- [x] `bunkervm sandbox logs <id|name>`

**Existing files modified:**
- [x] `bunkervm/__main__.py` — Added "engine", "sandbox" to CLI dispatch set
- [x] `bunkervm/cli.py` — Added engine/sandbox subcommands + API helper functions

**Remaining for M1 (needs Linux/WSL2 to validate):**
- [x] Test `bunkervm engine start` → daemon boots, API responds
- [x] Test `curl localhost:9551/engine/status` returns version + sandbox count
- [x] Test sandbox create → exec → destroy lifecycle via API
- [x] Test `bunkervm engine start -d` (background mode) — daemon thread validated in test harness
- [x] Test graceful shutdown (SIGTERM, `bunkervm engine stop`)

### M2 Detailed Progress

**New files created:**
- [x] `bunkervm/engine/client.py` — EngineClient (stdlib urllib HTTP client for engine API)
- [x] `bunkervm/engine/discovery.py` — `discover_engine()`, `is_engine_running()`, auto-probe

**Existing files modified:**
- [x] `bunkervm/runtime.py` — `run_code()` tries engine first, falls back to direct Firecracker
- [x] `bunkervm/runtime.py` — `Sandbox` class: engine-backed mode with `_EngineBackedClient` adapter
- [x] `bunkervm/integrations/base.py` — `BunkerVMToolsBase.__init__()`: auto-discovers engine as 3rd mode
- [x] `bunkervm/engine/__init__.py` — Exports `EngineClient`, `discover_engine`, `is_engine_running`
- [x] `bunkervm/__init__.py` — Top-level exports: `EngineClient`, `discover_engine`, `is_engine_running`

**Key patterns:**
- `_EngineBackedClient` in runtime.py: duck-typed SandboxClient that routes through engine REST API
- Discovery order: env var `BUNKERVM_ENGINE_URL` → PID file check → probe localhost:9551 → None (fallback)
- All integrations (LangChain, CrewAI, OpenAI Agents) inherit from `BunkerVMToolsBase` — engine support is free

**Remaining for M2 (needs Linux/WSL2 to validate):**
- [x] Test `Sandbox()` auto-discovers engine and routes through it
- [x] Test `run_code()` auto-discovers engine
- [x] Test `BunkerVMToolkit()` (LangChain) auto-discovers engine
- [x] Test fallback to direct Firecracker when engine not running
- [x] Test explicit `engine_url` parameter override

### M4 Detailed Progress

**Files created:**
- [x] `bunkervm/engine/platform.py` — PlatformInfo, detect_platform(), is_windows(), is_wsl(), has_kvm()
- [x] `bunkervm/engine/wsl_bridge.py` — WSLBridge: manage engine lifecycle from Windows via WSL2
- [x] `installer/windows/install.ps1` — Full PowerShell installer (WSL2, pip, KVM, bundle)
- [x] `installer/windows/README.md` — Windows installation guide
- [x] `tests/test_m4_windows.py` — 54 tests covering platform detection, WSLBridge, CLI integration

**Existing files modified:**
- [x] `bunkervm/cli.py` — cmd_engine_start branches Windows (WSLBridge) vs Linux (direct daemon)
- [x] `bunkervm/engine/daemon.py` — Windows guard in start()
- [x] `bunkervm/engine/discovery.py` — Skips PID file on Windows
- [x] `bunkervm/engine/__init__.py` — Exports PlatformInfo, detect_platform, is_windows, is_wsl, has_kvm

### M5 Detailed Progress

**Files created:**
- [x] `desktop/src/index.html` — SPA with 4 pages: Dashboard, Sandbox Manager, Terminal, Settings
- [x] `desktop/src/styles.css` — Full design system (dark theme, glassmorphism, CSS variables, animations)
- [x] `desktop/src/app.js` — API client, state management, polling, toast notifications, keyboard shortcuts
- [x] `desktop/src-tauri/src/main.rs` — Tauri backend: system tray, menu, engine lifecycle, window management
- [x] `desktop/src-tauri/Cargo.toml` — Rust dependencies (tauri v2 with tray-icon)
- [x] `desktop/src-tauri/tauri.conf.json` — App config: window size, CSP, tray, bundle settings
- [x] `desktop/src-tauri/build.rs` — Tauri build script
- [x] `desktop/package.json` — Node.js project metadata

**Existing files modified:**
- [x] `bunkervm/engine/api.py` — Added dashboard static file serving at `/dashboard` route

**Key UI features:**
- Dashboard: 4 stat cards (status, sandboxes, uptime, platform), quick actions, sandbox table
- Sandbox Manager: Card grid with create/destroy/reset/terminal actions
- Terminal: Interactive command execution with history (arrow keys), per-sandbox
- Settings: Engine config (port, max sandboxes, vCPUs, memory), about section
- Create modal: Name, vCPUs, memory, network toggle
- Toast notifications: Success/error/info with slide-in animation
- Keyboard shortcuts: Ctrl+K (terminal), Ctrl+N (new sandbox), Escape (close modal)
- Responsive: Sidebar collapses at 900px, stats reflow at 1200px

**Architecture:**
- Web frontend at `desktop/src/` works standalone (open in browser, talks to 9551)
- Engine API serves dashboard at `http://localhost:9551/dashboard`
- Tauri wraps the frontend as a native app with system tray
- API polling every 4 seconds for automatic state sync

