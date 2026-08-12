# Changelog

All notable changes to BunkerVM are documented here.

## [Unreleased]

## [0.11.0] — 2026-08-12

### Added
- **Local backend** (`Sandbox(backend="local")`, `bunkervm demo --local`, `bunkervm run --local`) — runs code as a plain subprocess instead of a Firecracker VM. No isolation, but the record/rewind/diff workflow works identically, and it needs nothing beyond Python (no `/dev/kvm`, no WSL2) — the main gap this closes is macOS, which can't run Firecracker at all. Never selected automatically; must be requested explicitly, and every checkpoint records which backend produced it (`backend` field on sessions/checkpoints).
- `bunkervm compare <a> <b> <c> [--html report.html]` — scores and ranks multiple recorded sessions using only data `record=True` already captured: exit codes, timing, the existing safety classifier's risk tier per command, and filesystem trace. No judge model, no rubric. Ranks by completed-without-failure, then fewest destructive/blocked commands, then time, and flags the first step where each run diverges from a baseline. `bunkervm/report.py` holds the scoring/rendering logic.

### Fixed
- `restore()` in direct mode raised on every call — the snapshot's frozen rootfs was never restored to the fixed working path Firecracker recorded as the block device backing file. Found and verified by actually running the demo, not just reading the README.
- Filesystem tracing was silently dropped across the entire engine-mode call chain (the only mode on Windows), returning `trace: null` with no error.

### Changed
- README repositioned around the felt debugging pain ("what did the agent actually do, and can I get back to before it broke") instead of leading with the security pitch; isolation is now presented as the mechanism, not the headline. Added the tier table, a real (not staged) terminal visual up top, an "Is this for you?" section, and cut ~80 lines of duplicated walkthrough between "What it does" and the old "Four capabilities" section. Fixed example session IDs that implied custom naming when IDs are actually auto-generated hex.
- `docs/index.html` (GitHub Pages landing page) updated to match: hero copy mentions the local backend/macOS path, a new "Two ways to run it" section mirrors the README's tier table, and the Time-Travel section's tool grid gained a fourth card for `bunkervm compare`.
- GitHub repo metadata: description, topics, and homepage were all empty/placeholder; set them and enabled GitHub Pages (the docs/ landing page was live in the repo but never actually served).
- CI: pinned `ruff==0.15.1` and pointed the lint job at the same `pip install -e .[dev]` the test job already uses, instead of an unpinned `pip install ruff black` that silently drifted to a much newer ruff with a different default rule set.

### Removed
- `demo.tape` / `record_demo.sh` — referenced the removed `bunkervm[langgraph]` extra and a backed-up example script. Replaced by a static `docs/demo-terminal.svg` embedded in the README, showing real verified output.

## [0.10.0] — 2026-08-11

### Changed
- License changed from Apache-2.0 to MIT.

### Removed
- Desktop GUI app (`desktop/`) and its Windows installer — unfinished mid-pivot (PyInstaller → planned Tauri rewrite), untested, not part of the core value proposition. Moved to a local `backup/` folder (gitignored, not in version control).
- Dedicated LangChain, OpenAI Agents SDK, and CrewAI integration modules/extras (`bunkervm.langchain`, `bunkervm.openai_agents`, `bunkervm.crewai`, and their `pip install bunkervm[...]` extras) — untested in CI, high maintenance surface for three framework APIs. `SecureAgentRuntime.as_tool()` / `.as_openai_tool()` remain as lightweight single-tool adapters using the upstream SDKs directly.
- Stale/ad-hoc dev scripts from `tests/` (`test_v030.py`, `verify_all.py`, `smoke_test.py`, `test_escape.py`) that were hardcoded to old versions/paths and not real regression tests.

### Added
- CI workflow with lint + import tests across Python 3.10-3.13
- Resource limits in guest exec agent (ulimit memory/processes, write-file size cap)
- `CHANGELOG.md`
- Fat rootfs build script with common data-science packages

### Fixed
- Binary file upload in `EngineClient.upload_file` (UTF-8 fallback to base64)

### Changed
- License changed from AGPL-3.0 to Apache-2.0
- README restructured: pip-first, E2B comparison table, BunkerDesktop moved down
- PyPI status upgraded from Alpha to Beta

### Added (v0.8.6 commit)
- `SECURITY.md`, `CONTRIBUTING.md`, issue templates
- Social preview SVG and og:image meta tags

---

## [0.8.6] — 2025-06-07

### Fixed
- Document Smart App Control bypass, update SmartScreen docs

## [0.8.5] — 2025-06-07

### Added
- SmartScreen bypass documentation

## [0.8.4] — 2025-06-06

### Changed
- CI: switch to Azure Trusted Signing

## [0.8.3] — 2025-06-06

### Fixed
- Hide CMD window flicker on WSL subprocess calls (Windows)

## [0.8.2] — 2025-06-05

### Fixed
- Packaging fix (version bump for PyPI)

## [0.8.1] — 2025-06-05

### Fixed
- Packaging fix (version bump for PyPI)

## [0.8.0] — 2025-06-05

### Added
- **BunkerDesktop** — native Windows desktop app (pywebview + PyInstaller)
- Engine daemon (`localhost:9551`) with REST API for VM management
- `EngineClient` SDK for programmatic engine access
- 4-job CI/CD pipeline: build-bundle, build-desktop, release, publish-pypi
- Desktop shortcut creation (no admin required)

## [0.7.2] — 2025-06-04

### Fixed
- Remove `--stdio` from generated `mcp.json` (server defaults to stdio)

## [0.7.1] — 2025-06-04

### Fixed
- Version bump for PyPI (v0.7.0 already uploaded)

## [0.7.0] — 2025-06-04

### Added
- VS Code MCP integration + `enable-network` CLI command
- Zero-config Windows experience — `vscode-setup` auto-installs BunkerVM in WSL

## [0.6.0] — 2025-06-03

### Changed
- **Unified integration architecture**: shared `BunkerVMToolsBase` class
- LangChain, OpenAI Agents, CrewAI adapters now wrap base class (no duplicated logic)
- Migrated to `langchain.agents.create_agent` pattern
- Polished integration docs and demo scripts

## [0.5.0] — 2025-06-02

### Added
- One-liner API (`bunkervm.run_code()`)
- Developer CLI (`bunkervm demo`, `bunkervm shell`)
- `SecureAgentRuntime` for agent sandboxing
- CRLF → LF fix for CI shell scripts

## [0.2.6] — 2025-06-01

### Fixed
- PyPI version sequencing fix

## [0.2.5] — 2025-06-01

### Added
- Logging in example `test_agent.py`

## [0.2.4] — 2025-06-01

### Added
- Live tool-call logging in MCP server and toolkit

## [0.2.3] — 2025-05-31

### Added
- `BunkerVMToolkit` — clean LangChain/LangGraph integration
- `SandboxClient` with sensible defaults

## [0.2.2] — 2025-05-31

### Fixed
- PyPI version bump (rejects re-upload of 0.2.1)

## [0.2.1] — 2025-05-31

### Fixed
- Exclude `.debug` file from Firecracker binary extraction
- Exclude `.config` files from kernel URL discovery

## [0.2.0] — 2025-05-30

### Changed
- **Renamed NervOS → BunkerVM** across entire codebase
- Full test suite added

## [0.1.0] — 2025-05-29

### Added
- Initial release as NervOS
- Firecracker microVM sandbox with vsock communication
- `exec_agent.py` guest-side HTTP server
- `sandbox_client.py` stdlib-only HTTP client
- MCP server with tool exposure via FastMCP
- Safety classifier (READ/WRITE/SYSTEM/DESTRUCTIVE/BLOCKED)
- Bootstrap auto-download of Firecracker bundle
- GitHub Pages landing site

[Unreleased]: https://github.com/ashishgituser/bunkervm/compare/v0.11.0...HEAD
[0.11.0]: https://github.com/ashishgituser/bunkervm/compare/v0.10.0...v0.11.0
[0.10.0]: https://github.com/ashishgituser/bunkervm/compare/v0.8.6...v0.10.0
[0.8.6]: https://github.com/ashishgituser/bunkervm/compare/v0.8.5...v0.8.6
[0.8.5]: https://github.com/ashishgituser/bunkervm/compare/v0.8.4...v0.8.5
[0.8.4]: https://github.com/ashishgituser/bunkervm/compare/v0.8.3...v0.8.4
[0.8.3]: https://github.com/ashishgituser/bunkervm/compare/v0.8.2...v0.8.3
[0.8.2]: https://github.com/ashishgituser/bunkervm/compare/v0.8.1...v0.8.2
[0.8.1]: https://github.com/ashishgituser/bunkervm/compare/v0.8.0...v0.8.1
[0.8.0]: https://github.com/ashishgituser/bunkervm/compare/v0.7.2...v0.8.0
[0.7.2]: https://github.com/ashishgituser/bunkervm/compare/v0.7.1...v0.7.2
[0.7.1]: https://github.com/ashishgituser/bunkervm/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/ashishgituser/bunkervm/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/ashishgituser/bunkervm/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/ashishgituser/bunkervm/compare/v0.2.6...v0.5.0
[0.2.6]: https://github.com/ashishgituser/bunkervm/compare/v0.2.5...v0.2.6
[0.2.5]: https://github.com/ashishgituser/bunkervm/compare/v0.2.4...v0.2.5
[0.2.4]: https://github.com/ashishgituser/bunkervm/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/ashishgituser/bunkervm/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/ashishgituser/bunkervm/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/ashishgituser/bunkervm/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/ashishgituser/bunkervm/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/ashishgituser/bunkervm/releases/tag/v0.1.0
