# BunkerVM — Copilot Instructions

## Project Overview

BunkerVM is a Python library (`pip install bunkervm`) that boots disposable **Firecracker microVMs** for AI agents to execute untrusted code with hardware-level (KVM) isolation. The core loop: boot VM (~3s) → execute code → destroy VM. Only dependency is `mcp`.

## Architecture

```
Host side (bunkervm/)                    Guest side (rootfs/bunkervm/)
─────────────────────                    ────────────────────────────
cli.py / __main__.py  →  vm_manager.py  →  [Firecracker process]
                              ↕ vsock                ↕
                       sandbox_client.py  ←→  exec_agent.py (HTTP over vsock)
                              ↑
              mcp_server.py / integrations/
```

- **`vm_manager.py`** — Firecracker process lifecycle (start/stop/restart), TAP networking setup, rootfs copies. Communicates via vsock UDS (`/tmp/bunkervm-vsock.sock`).
- **`sandbox_client.py`** — Stdlib-only HTTP client that speaks the Firecracker vsock handshake protocol (`CONNECT <port>\n` → `OK <port>\n` → HTTP). No external HTTP libs.
- **`rootfs/bunkervm/exec_agent.py`** — Runs *inside* the VM. Zero-dependency HTTP server (stdlib only, must work on Alpine/musl). Endpoints: `/exec`, `/read-file`, `/write-file`, `/list-dir`, `/health`, `/status`.
- **`mcp_server.py`** — Exposes sandbox operations as MCP tools via `FastMCP`. Global state set by `__main__.py` before server starts.
- **`integrations/base.py`** — `BunkerVMToolsBase` provides 6 shared tool implementations (`_run_command`, `_write_file`, `_read_file`, `_list_directory`, `_upload_file`, `_download_file`). Framework adapters (`langchain.py`, `openai_agents.py`, `crewai.py`) wrap these with framework-specific decorators — **never duplicate tool logic in adapters**.
- **`safety.py`** — Regex-based command classifier (READ/WRITE/SYSTEM/DESTRUCTIVE/BLOCKED). Defense-in-depth only; the VM is the real isolation boundary.
- **`bootstrap.py`** — Auto-downloads Firecracker bundle to `~/.bunkervm/bundle/` on first run. Falls back to `build/` dir in dev mode.
- **`config.py`** — Layered config: CLI args > env vars (`BUNKERVM_*`) > `bunkervm.toml` > built-in defaults.

## Key Conventions

- **Stdlib-only in guest code**: Everything under `rootfs/bunkervm/` must use Python stdlib only — no pip packages. It runs on minimal Alpine Linux.
- **Stdlib-only for `sandbox_client.py`**: The client uses raw sockets + hand-built HTTP. No `requests`/`httpx`.
- **Context manager pattern**: `Sandbox`, all toolkit classes, and `VMPool` support `with` statements for automatic VM cleanup.
- **Auto-boot vs attach**: All integration classes accept either no args (auto-boot a VM) or `vsock_uds`/`host`+`port` (connect to existing VM).
- **Print to stderr**: User-facing messages go to `sys.stderr` (`_print()` helper) because stdout may be captured by MCP stdio transport.
- **Safety classifier is advisory**: Even "destructive" commands are safe inside the VM. The classifier exists for audit trails and optional policy (`enforce_safety` config flag).

## Adding a New Framework Integration

1. Create `bunkervm/<framework>.py`
2. Subclass `BunkerVMToolsBase` from `integrations/base.py`
3. Implement `get_tools()` that wraps `self._run_command`, `self._write_file`, etc. with the framework's tool decorator
4. Add optional dependency group in `pyproject.toml` under `[project.optional-dependencies]`
5. Add convenience factory in `bunkervm/__init__.py`

See `langchain.py` (20 lines of framework glue) as the reference implementation.

## Development & Testing

```bash
# Install in dev mode
pip install -e ".[dev]"

# Run tests (requires Linux with /dev/kvm — use WSL2 on Windows)
pytest tests/

# Smoke test against a running VM
python tests/smoke_test.py

# Run the demo
bunkervm demo

# Start MCP server (stdio for Claude Desktop, sse for web)
python -m bunkervm                      # stdio
python -m bunkervm --transport sse      # SSE on port 3000

# Lint
ruff check bunkervm/
black --check bunkervm/
```

- **KVM required**: Tests that boot VMs need Linux + `/dev/kvm`. On Windows, run inside WSL2.
- **Test files are standalone scripts**: Most tests in `tests/` are runnable scripts (`python tests/test_sandbox.py`), not pure pytest.
- **Config format**: `bunkervm.toml` (not YAML). Line length 100, Python 3.10+ target.

## Transport Modes

- **vsock** (default): Host ↔ VM via Firecracker UDS. Zero network config, no sudo needed.
- **TAP networking** (`--network`): Gives VM internet access. Requires sudo for TAP device setup. IP range `172.16.0.0/24`.
- **MCP stdio**: Default for `python -m bunkervm`. Used by Claude Desktop.
- **MCP SSE**: `--transport sse` on port 3000. Includes web dashboard at `/dashboard`.

## Guest Rootfs Build Pipeline

The root filesystem (`build/rootfs.ext4`) is a 512MB ext4 image containing Alpine Linux + Python + the exec agent:

- **`build/build-sandbox-rootfs.sh`** — Full build: downloads Alpine minirootfs, installs Python, copies `rootfs/bunkervm/exec_agent.py` and `rootfs/init` into the image. Run on Linux only.
- **`build/patch-rootfs.sh`** — Quick-patch: mounts existing `rootfs.ext4`, replaces `init`, `exec_agent.py`, `orchestrator.py`, `tools.py`, and `system_prompt.txt` without a full rebuild. Also sets `/etc/bunkervm/mode` to `sandbox`.
- **`rootfs/init`** — PID 1 init script (no systemd). Auto-detects mode: **standalone** (llama-server + orchestrator for AI OS) or **sandbox** (exec_agent.py for MCP use). Mounts `/proc`, `/sys`, `/dev`, starts networking, then launches the appropriate service.

When modifying guest code, use `patch-rootfs.sh` for fast iteration instead of a full rebuild.

## MCP Server Global State Pattern

`mcp_server.py` uses module-level globals (`_client`, `_audit`, `_vm_manager`, `_config`) set by `__main__.py` *before* the server starts:

```python
# In __main__.py:
from .mcp_server import set_globals, create_server
set_globals(client=client, audit=audit, vm_manager=vm, config=config)
server = create_server(port=args.port)
server.run(transport="stdio")  # or "sse"
```

MCP tool handlers (`@mcp.tool()` functions) access shared state via `_get_client()` and `_get_audit()` helpers that raise `RuntimeError` if called before initialization. This pattern avoids passing state through FastMCP's decorator system.

## Multi-VM / VMPool

`VMPool` manages multiple named Firecracker instances concurrently. Each VM gets isolated resources (unique vsock CID, socket path, rootfs copy, TAP device):

```python
from bunkervm.multi_vm import VMPool
pool = VMPool(base_config, max_vms=10)
client1 = pool.start("sandbox-1")               # CID=3, tap0, 172.16.0.x
client2 = pool.start("sandbox-2", cpus=4)        # CID=4, tap1, 172.16.1.x
client1.exec("echo hello from VM 1")
pool.stop_all()
```

Key details: thread-safe via `threading.Lock`, each VM gets subnet `172.16.<index>.0/24` to avoid IP conflicts, supports `with` statement for auto-cleanup.

## Orchestrator / NervOS Agent (In-VM)

The `rootfs/bunkervm/` directory contains an alternative **standalone** mode where the VM runs an autonomous AI agent powered by a local LLM:

- **`orchestrator.py`** — Chat loop: user input → LLM (via `llama-server` at `:8080`) → JSON response (`{"cmd":"..."}` or `{"reply":"..."}`) → execute → feed output back to LLM.
- **`tools.py`** — Single `execute(cmd)` function using `subprocess.run()`. The entire OS is the tool — no hardcoded tool list.
- **`system_prompt.txt`** — Instructs the model to respond in JSON only, use real commands, never guess.

This mode is activated when `llama-server` + a model are present in the rootfs (or `/etc/bunkervm/mode` is set to `standalone`). In sandbox mode (the default for `pip install bunkervm`), only `exec_agent.py` runs.

## BunkerDesktop (Active Development)

BunkerVM is evolving into **BunkerDesktop** — a Docker Desktop-like product where users install a desktop app and everything works automatically. See `.github/BUNKERDESKTOP_PLAN.md` for the full implementation plan, checklist, and architecture.

**Key architectural shift:** The engine daemon (`bunkervm/engine/daemon.py`) manages all Firecracker VMs via a REST API on `localhost:9551`. The Python SDK, CLI, and all framework integrations become thin clients that auto-discover the running engine. If no engine is running, they fall back to direct Firecracker boot (current behavior).

**When working on engine code:**
- New engine code goes in `bunkervm/engine/` package
- Engine wraps existing `VMPool` from `multi_vm.py` — never reinvent VM management
- Engine API uses stdlib `http.server` — no external HTTP framework dependencies
- Always check `.github/BUNKERDESKTOP_PLAN.md` for current milestone status before starting work
