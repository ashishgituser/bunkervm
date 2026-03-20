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
# Import tests (no VM needed)
python tests/test_imports.py

# Full smoke test (requires /dev/kvm)
python tests/smoke_test.py

# All tests
pytest tests/
```

## Project Structure

```
bunkervm/              # Host-side Python package
  integrations/        # Framework adapters (LangChain, OpenAI, CrewAI)
  engine/              # Engine daemon for BunkerDesktop
rootfs/bunkervm/       # Guest-side code (runs inside the VM)
build/                 # Rootfs build scripts
tests/                 # Test suite
docs/                  # Landing page and assets
examples/              # Working examples for each framework
```

## Key Conventions

- **Guest code (`rootfs/bunkervm/`)** — stdlib-only Python. No pip packages. Must run on Alpine/musl.
- **`sandbox_client.py`** — stdlib-only HTTP client. No `requests`/`httpx`.
- **Framework integrations** — subclass `BunkerVMToolsBase` from `integrations/base.py`. Never duplicate tool logic in adapters.
- **Print to stderr** — user-facing messages go to `sys.stderr` because stdout may be captured by MCP transport.
- **Line length** — 100 characters. Use `black` and `ruff` for formatting.

## Adding a New Framework Integration

1. Create `bunkervm/<framework>.py`
2. Subclass `BunkerVMToolsBase` from `integrations/base.py`
3. Implement `get_tools()` wrapping the 6 base methods
4. Add optional dependency group in `pyproject.toml`
5. Add convenience factory in `bunkervm/__init__.py`

See `langchain.py` (~20 lines of framework glue) as the reference.

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

By contributing, you agree that your contributions will be licensed under the [Apache-2.0 License](LICENSE).
