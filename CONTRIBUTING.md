# Contributing to BunkerVM

Thanks for your interest in contributing to BunkerVM! This project provides hardware-isolated sandboxes for AI agents using Firecracker microVMs.

## Getting Started

### Prerequisites

- **Linux with `/dev/kvm`** (or Windows WSL2 with nested virtualization)
- Python 3.10+
- Git

### Development Setup

```bash
git clone https://github.com/ashishgituser/bunkervm.git
cd bunkervm
pip install -e ".[dev]"

# Build the VM rootfs (Linux only)
sudo bash build/setup-firecracker.sh
sudo bash build/build-sandbox-rootfs.sh

# Verify everything works
bunkervm demo
```

### Running Tests

```bash
# Import + host-side feature tests (no VM needed) — what CI runs
pytest tests/test_imports.py tests/test_features.py

# Tests needing real Firecracker/KVM or WSL2 (run manually, not in CI)
python tests/test_engine.py
python tests/test_sandbox.py
python tests/test_m4_windows.py   # Windows/WSL2 platform detection

# All tests
pytest tests/
```

## Project Structure

```
bunkervm/              # Host-side Python package
  engine/              # Engine daemon (Windows/WSL2 bridge, REST API)
rootfs/bunkervm/       # Guest-side code (runs inside the VM)
build/                 # Rootfs build scripts
tests/                 # Test suite
docs/                  # Landing page and assets
examples/              # Working examples (quickstart, session record/replay)
backup/                # Gitignored — code moved out of scope, see backup/README.md
```

## Key Conventions

- **Guest code (`rootfs/bunkervm/`)** — stdlib-only Python. No pip packages. Must run on Alpine/musl.
- **`sandbox_client.py`** — stdlib-only HTTP client. No `requests`/`httpx`.
- **Print to stderr** — user-facing messages go to `sys.stderr` because stdout may be captured by MCP transport.
- **Line length** — 100 characters. Use `black` and `ruff` for formatting.

## Submitting Changes

1. Fork the repo and create a branch from `main`
2. Make your changes — keep commits focused and descriptive
3. Run `ruff check bunkervm/` and `black --check bunkervm/` to lint
4. Run `python tests/test_imports.py` at minimum
5. Open a pull request with a clear description of what and why

## Reporting Issues

- Use [GitHub Issues](https://github.com/ashishgituser/bunkervm/issues)
- Include your OS, Python version, and `bunkervm info` output
- For VM issues, include the Firecracker log if available

## Code of Conduct

Be respectful, constructive, and inclusive. We're building something useful — let's keep it collaborative.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
