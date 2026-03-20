# Changelog

All notable changes to BunkerVM are documented here.

## [Unreleased]

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

[Unreleased]: https://github.com/ashishgituser/bunkervm/compare/v0.8.6...HEAD
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
