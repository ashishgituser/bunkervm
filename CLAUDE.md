# BunkerVM

Hardware-isolated Linux sandbox for AI agents — Firecracker microVMs with record/replay/snapshot/diff. Pip package `bunkervm`, console script `bunkervm`, current version 0.9.4. Core dep is just `mcp>=1.0.0`.

**Repo scope (as of the 2026-08 trim-down, see CHANGELOG.md):** trimmed to the core differentiated pitch — time-travel debugging (record/snapshot/restore/diff) — plus MCP support. The desktop GUI app and the dedicated LangChain/OpenAI-Agents-SDK/CrewAI integration modules were untested, high-maintenance, and diluted focus; they were moved to `backup/` (gitignored, not tracked, still in git history). Don't recreate them without deliberately deciding to re-scope — check `backup/README.md` first if something seems to be "missing." `SecureAgentRuntime.as_tool()` / `.as_openai_tool()` in `agent_runtime.py` remain as minimal single-tool adapters (lazy-import the upstream SDK directly, no bundled toolkit class).

## Two operating modes (pervasive throughout the codebase)

- **Direct mode** — talks straight to Firecracker via KVM (Linux only). `Sandbox._vm` = `bunkervm/vm_manager.py::VMManager`, comms over vsock UDS via `bunkervm/sandbox_client.py`. Supports true Firecracker snapshots (instant, full VM state: memory/fs/processes).
- **Engine mode** — a background daemon (`bunkervm/engine/daemon.py`, REST API on `localhost:9551`) owns the only Firecracker access; everything else (CLI, SDK, desktop, MCP server) is a thin HTTP client via `bunkervm/engine_client.py` / `bunkervm/engine/client.py`. Used transparently on Windows via a WSL2 bridge (`bunkervm/engine/wsl_bridge.py`). README lists only Linux (native `/dev/kvm`) and Windows+WSL2 as supported; macOS is not a documented supported platform (Firecracker requires KVM, which macOS lacks). Cannot do real VM snapshots — some direct-mode-only features raise `RuntimeError` here (manual `checkpoint()`, true snapshot `restore()`).
- `Sandbox.start()` tries `_resolve_engine()` first, then falls back to `_start_direct()`. Capability parity between the two modes is incomplete **by design**, not a bug.

## Key files

- `bunkervm/__init__.py` — public API: `run_code`, `secure_agent`, `Sandbox`, `SandboxClient`, `VMPool`, `SnapshotManager`, `EngineClient`.
- `bunkervm/runtime.py` — `Sandbox` class, the central context manager. Persistent variable namespace across `run()` calls via pickling to `/tmp/_ns.pkl` inside the VM.
- `bunkervm/cli.py` (~1450 lines) — `main()`, all `bunkervm` subcommands (`demo`, `run`, `info`, `engine start/stop/status`, `sandbox ...`, `replay`, `snapshot ...`, `diff`, `server`, etc).
- `bunkervm/mcp_server.py` + `bunkervm/__main__.py` — MCP tool exposure (`sandbox_exec`, `sandbox_read_file`, etc) via `mcp.server.fastmcp.FastMCP`.
- `bunkervm/snapshot.py` — `SnapshotManager` + hand-rolled `FirecrackerAPIClient` (HTTP-over-Unix-socket) for pause/snapshot/resume. Snapshots stored at `~/.bunkervm/snapshots/<name>/`.
- `bunkervm/safety.py` — regex-based command risk classifier (defense-in-depth on top of VM isolation). `bunkervm/audit.py` — JSONL audit log.
- `bunkervm/config.py` — loads `bunkervm.toml`; precedence CLI args > `BUNKERVM_*` env vars > toml > defaults.
- `bunkervm/agent_runtime.py` — `secure_agent()` / `SecureAgentRuntime`, the "one line to make any agent secure" API; `.as_tool()` / `.as_openai_tool()` are minimal single-tool adapters for LangChain/OpenAI Agents SDK (lazy-import the upstream SDK, no bundled toolkit).
- `bunkervm/dashboard.py` + `bunkervm/dashboard_assets/` — lightweight stdlib-only localhost monitoring UI, auto-starts alongside the MCP SSE server.
- `bunkervm/multi_vm.py::VMPool` — run multiple named sandbox instances at once.
- `rootfs/bunkervm/` — code baked into the *guest* VM image (`exec_agent.py`, `orchestrator.py`, `tools.py`) — distinct from the host-side `bunkervm/` package.
- `installer/windows/install.ps1` — sets up WSL2 + Ubuntu + BunkerVM so `bunkervm engine start` works from Windows.
- `build/` — VM image build pipeline (`build-fat-rootfs.sh`, `setup-firecracker.sh`); `build/rootfs.ext4` (~1.2GB) and `build/vmlinux` (~21MB) are gitignored local build outputs, not tracked in git.

## Record / replay / restore / diff

- `Sandbox(record=True)` — after every `run()`, `_auto_checkpoint()` stores `{step, command, exit_code, stdout, stderr, trace, snapshot_name}`. In direct mode also triggers a real Firecracker snapshot per step; engine mode leaves `snapshot_name=None`.
- Sessions persist to `~/.bunkervm/sessions/<session_id>.json` (`Sandbox.save_session()`).
- `Sandbox.restore(step)`: **direct mode** with a snapshot → true instant restore (stop VM, `start_from_snapshot()`, reconnect). **Engine mode / no snapshot** → best-effort fallback (since v0.9.4): clears the pickled namespace, disables recording, and *replays* every `run(cmd)` from step 1 up to the target, swallowing per-command `RuntimeError`s. This only reconstructs variable state, not real filesystem/process state — approximate, not a true restore.
- `bunkervm diff session-a session-b` (`cli.py::cmd_diff` / `_compute_diff`) — step-by-step command/exit-code comparison plus filesystem trace diffing between two saved sessions.

## Tests / CI

- `.github/workflows/ci.yml`: lint job (ruff + black on `bunkervm/`) and test job (py3.10–3.13) running `tests/test_imports.py` + `tests/test_features.py` (pytest, host-side snapshot/diff/recording logic, no KVM needed).
- Everything needing real KVM/Firecracker (`test_engine.py`, `test_engine_client.py`, `test_sandbox.py`, `test_secure_agent.py`, `test_run_code.py`) or WSL2 (`test_m4_windows.py`) must be run manually — they're standalone scripts, not CI-wired.

## Notable gotchas

- Windows support is bolted on via WSL2 bridging, not native — Firecracker fundamentally requires Linux/KVM. macOS isn't supported at all.
- Engine-mode `restore()` silently swallows exceptions during replay — don't assume `diff`/`restore` semantics are identical across direct vs engine mode.
