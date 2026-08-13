# Changelog

All notable changes to BunkerVM are documented here.

## [Unreleased]

## [0.12.0] — 2026-08-13

The theme: an agent can turn a failing test suite green by deleting the test. Exit codes can't tell that apart from a real fix — the filesystem trace can, and `compare` now uses it.

### Added
- `examples/agent-bakeoff/` — a runnable example built around exactly that failure. One project with a real bug (`average([])` divides by zero), three agents told to make the suite pass, all three ending green with exit code 0. Uses the `local` backend, so it needs no API key and no KVM. `docs/bakeoff-example.html` is the rendered report; `docs/bakeoff.mp4` / `docs/bakeoff.gif` are the demo video.
- `score_session()` now returns `deleted_paths` and `flags`. Flags are labelled heuristics for a human reader — "ended green after deleting `tests/test_stats.py`" — and are shown in both the CLI and the HTML report. They **never** affect ranking; that stays on observed facts only.
- `score_session()` returns `final_success` alongside `success` (see Changed).

### Changed
- **Ranking now counts deleted files** (after failed steps and destructive/blocked commands, before duration). Previously `files_deleted` was computed and then ignored by the sort key, so an agent that deleted the failing test ranked *first* — it was fast and ran nothing risky. Caught by building the bake-off example and running it.
- **`success` split into two signals.** `success` still means "no step ever failed"; the new `final_success` means "the run ended in a working state", and ranking uses that. The old definition punished the correct behaviour of running the suite first to see it red. The result column now reads `ended green`, `ended green (recovered from 1 failing step)`, or `ended failing (step N)`.
- `bunkervm compare` text output now prints the full risk profile (`read x1  write x3  system x1`), not just a destructive/blocked count. A `system`-tier command like `chmod` or `pip install` was previously visible only in the HTML report.
- Local-backend filesystem traces now skip `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache` and `.git`. These are written by the toolchain rather than chosen by the agent, and a single `pytest` run was inflating a step to "+9 files created".
- `docs/compare-example.html` regenerated against the new scoring.

## [0.11.1] — 2026-08-12

### Added
- `bunkervm compare --label NAME` (repeatable) — display names for sessions instead of raw hex IDs. `report.compare_sessions()` already took a `labels` argument; the CLI didn't expose it.
- `docs/compare-example.html` — a real `bunkervm compare` run (three agents cleaning the same messy CSV, one crashes, one succeeds but trips a risk flag it isn't penalized for) hosted as a static page and linked from the README and the landing page's Compare tool card, replacing the synthetic placeholder example that was there before.

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

[Unreleased]: https://github.com/ashishgituser/bunkervm/compare/v0.11.1...HEAD
[0.11.1]: https://github.com/ashishgituser/bunkervm/compare/v0.11.0...v0.11.1
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
