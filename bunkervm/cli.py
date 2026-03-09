"""
BunkerVM CLI — Developer-friendly command-line interface.

Commands:
    bunkervm demo                   # See BunkerVM in action (10 seconds)
    bunkervm run script.py          # Run a script inside a sandbox
    bunkervm run -c "print(42)"     # Run inline code
    bunkervm server                 # Start MCP server (existing behavior)
    bunkervm info                   # Show system info and readiness

Usage:
    pip install bunkervm
    bunkervm demo
"""

from __future__ import annotations

import argparse
import os
import sys
import time

# ANSI colors for terminal output
_BOLD = "\033[1m"
_DIM = "\033[2m"
_GREEN = "\033[32m"
_CYAN = "\033[36m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_PURPLE = "\033[35m"
_RESET = "\033[0m"
_CHECK = f"{_GREEN}✓{_RESET}"
_CROSS = f"{_RED}✗{_RESET}"
_ARROW = f"{_CYAN}→{_RESET}"

# Disable colors if not a TTY
if not sys.stderr.isatty():
    _BOLD = _DIM = _GREEN = _CYAN = _YELLOW = _RED = _PURPLE = _RESET = ""
    _CHECK = "✓"
    _CROSS = "✗"
    _ARROW = "→"


def _print(msg: str = "", end: str = "\n") -> None:
    """Print to stderr (stdout reserved for output)."""
    print(msg, file=sys.stderr, end=end, flush=True)


# ── Demo Command ──


_DEMO_SCRIPT = '''\
import math, time

print("=" * 50)
print("  BunkerVM — Hardware-Isolated Sandbox Demo")
print("=" * 50)
print()

# 1. Prove we're inside a real VM
import platform
print(f"OS:       {platform.platform()}")
print(f"Hostname: {platform.node()}")
print(f"Python:   {platform.python_version()}")
print()

# 2. Compute primes (real work inside the sandbox)
def sieve(n):
    is_prime = [True] * (n + 1)
    is_prime[0] = is_prime[1] = False
    for i in range(2, int(math.sqrt(n)) + 1):
        if is_prime[i]:
            for j in range(i*i, n + 1, i):
                is_prime[j] = False
    return [x for x in range(n + 1) if is_prime[x]]

primes = sieve(100)
print(f"Prime numbers under 100:")
print(" ".join(str(p) for p in primes))
print(f"\\nFound {len(primes)} primes")
print()

# 3. File system access (sandboxed)
with open("/tmp/demo.txt", "w") as f:
    f.write("Hello from BunkerVM!")
with open("/tmp/demo.txt") as f:
    print(f"File I/O test: {f.read()}")
print()

# 4. Show isolation
print(f"Process ID:  {__import__('os').getpid()}")
print(f"User:        {__import__('os').getenv('USER', 'root')}")
print(f"Working dir: {__import__('os').getcwd()}")
print()
print("✓ Code ran safely inside a Firecracker microVM")
print("✓ Full Linux environment (not a container)")
print("✓ Hardware-level isolation via KVM")
print("✓ VM will be destroyed after this demo")
'''


def cmd_demo(args: argparse.Namespace) -> int:
    """Run the BunkerVM demo — shows the product in 10 seconds."""
    from .runtime import run_code

    _print()
    _print(f"{_BOLD}{_PURPLE}  ╔══════════════════════════════════════╗{_RESET}")
    _print(f"{_BOLD}{_PURPLE}  ║         BunkerVM Demo                ║{_RESET}")
    _print(f"{_BOLD}{_PURPLE}  ║  Hardware-isolated AI sandbox        ║{_RESET}")
    _print(f"{_BOLD}{_PURPLE}  ╚══════════════════════════════════════╝{_RESET}")
    _print()

    t0 = time.time()

    try:
        output = run_code(
            _DEMO_SCRIPT,
            cpus=1,
            memory=512,
            quiet=False,
        )
        _print()
        # Print output to stdout (so it can be captured/piped)
        print(output)
        _print()

        elapsed = time.time() - t0
        _print(f"{_CHECK} Demo completed in {elapsed:.1f}s")
        _print()
        _print(f"{_DIM}Learn more:{_RESET}")
        _print(f"  {_ARROW} Run your own code:  {_CYAN}bunkervm run script.py{_RESET}")
        _print(f"  {_ARROW} Python API:          {_CYAN}from bunkervm import run_code{_RESET}")
        _print(f"  {_ARROW} AI agent wrapper:    {_CYAN}from bunkervm import secure_agent{_RESET}")
        _print()
        return 0

    except Exception as e:
        _print(f"\n{_CROSS} Demo failed: {e}")
        return 1


# ── Run Command ──


def cmd_run(args: argparse.Namespace) -> int:
    """Run a script or inline code inside a BunkerVM sandbox."""
    from .runtime import run_code

    # Get code to run
    if args.code:
        code = args.code
        language = args.language or "python"
    elif args.file:
        if not os.path.exists(args.file):
            _print(f"{_CROSS} File not found: {args.file}")
            return 1
        with open(args.file, "r") as f:
            code = f.read()
        # Detect language from extension
        ext = os.path.splitext(args.file)[1].lower()
        language = args.language or {
            ".py": "python",
            ".sh": "bash",
            ".bash": "bash",
            ".js": "node",
        }.get(ext, "python")
    else:
        _print(f"{_CROSS} Provide a file or use -c for inline code")
        _print(f"  Usage: bunkervm run script.py")
        _print(f"  Usage: bunkervm run -c \"print('hello')\"")
        return 1

    try:
        output = run_code(
            code,
            language=language,
            timeout=args.timeout,
            cpus=args.cpus,
            memory=args.memory,
            network=not args.no_network,
            quiet=args.quiet,
        )
        print(output)
        return 0
    except RuntimeError as e:
        _print(f"\n{_CROSS} {e}")
        return 1
    except KeyboardInterrupt:
        _print(f"\n{_YELLOW}Interrupted{_RESET}")
        return 130


# ── Info Command ──


def cmd_info(args: argparse.Namespace) -> int:
    """Show BunkerVM system info and readiness."""
    import platform

    _print(f"\n{_BOLD}BunkerVM System Check{_RESET}\n")

    # Version
    from . import __version__
    _print(f"  Version:    {_CYAN}{__version__}{_RESET}")
    _print(f"  Platform:   {platform.platform()}")
    _print(f"  Python:     {platform.python_version()}")

    # Architecture
    arch = platform.machine()
    if arch in ("x86_64", "amd64", "AMD64"):
        _print(f"  Arch:       {_CHECK} {arch}")
    else:
        _print(f"  Arch:       {_CROSS} {arch} (x86_64 required)")

    # Linux / KVM
    if sys.platform == "linux":
        _print(f"  Linux:      {_CHECK}")
        if os.path.exists("/dev/kvm"):
            _print(f"  KVM:        {_CHECK} /dev/kvm available")
            # Check permissions
            if os.access("/dev/kvm", os.R_OK | os.W_OK):
                _print(f"  KVM access: {_CHECK} readable & writable")
            else:
                _print(f"  KVM access: {_CROSS} permission denied (try: sudo chmod 666 /dev/kvm)")
        else:
            _print(f"  KVM:        {_CROSS} /dev/kvm not found")
            _print(f"              WSL2: Add nestedVirtualization=true to .wslconfig")
    else:
        _print(f"  Linux:      {_YELLOW}! Not on Linux (use WSL2 on Windows){_RESET}")

    # Bundle
    _print()
    from .bootstrap import BUNDLE_DIR, REQUIRED_FILES
    bundle_ok = True
    for name, filename in REQUIRED_FILES.items():
        path = BUNDLE_DIR / filename
        if path.exists():
            size_mb = path.stat().st_size / (1024 * 1024)
            _print(f"  {name:14s} {_CHECK} {path} ({size_mb:.1f} MB)")
        else:
            _print(f"  {name:14s} {_CROSS} not found")
            bundle_ok = False

    if not bundle_ok:
        _print(f"\n  {_YELLOW}Run 'bunkervm demo' to auto-download the bundle.{_RESET}")

    # Firecracker check
    _print()
    import shutil
    fc = shutil.which("firecracker")
    if fc:
        _print(f"  Firecracker: {_CHECK} {fc}")
    elif (BUNDLE_DIR / "firecracker").exists():
        _print(f"  Firecracker: {_CHECK} {BUNDLE_DIR / 'firecracker'}")
    else:
        _print(f"  Firecracker: {_CROSS} not found")

    _print()
    return 0


# ── Main CLI Parser ──


def main() -> int:
    """BunkerVM CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="bunkervm",
        description="BunkerVM — Hardware-isolated sandbox for AI agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  bunkervm demo                        See it in action
  bunkervm run script.py               Run a script safely
  bunkervm run -c "print(42)"          Run inline code
  bunkervm server --transport sse      Start MCP server
  bunkervm info                        Check system readiness
""",
    )
    sub = parser.add_subparsers(dest="command")

    # ── demo ──
    demo_p = sub.add_parser("demo", help="See BunkerVM in action (10 seconds)")
    demo_p.set_defaults(func=cmd_demo)

    # ── run ──
    run_p = sub.add_parser("run", help="Run code inside a sandbox")
    run_p.add_argument("file", nargs="?", help="Script file to execute")
    run_p.add_argument("-c", "--code", help="Inline code to execute")
    run_p.add_argument("-l", "--language", choices=["python", "bash", "node"],
                       help="Language (auto-detected from extension)")
    run_p.add_argument("-t", "--timeout", type=int, default=30,
                       help="Execution timeout in seconds (default: 30)")
    run_p.add_argument("--cpus", type=int, default=1, help="vCPUs (default: 1)")
    run_p.add_argument("--memory", type=int, default=512, help="Memory in MB (default: 512)")
    run_p.add_argument("--no-network", action="store_true", help="Disable internet in VM")
    run_p.add_argument("-q", "--quiet", action="store_true", help="Suppress progress messages")
    run_p.set_defaults(func=cmd_run)

    # ── server ──
    server_p = sub.add_parser("server", help="Start MCP server (full mode)")
    server_p.add_argument("--transport", choices=["stdio", "sse"], default="stdio")
    server_p.add_argument("--port", type=int, default=3000)
    server_p.add_argument("--config", default=None)
    server_p.add_argument("--no-network", action="store_true")
    server_p.add_argument("--skip-vm", action="store_true")
    server_p.add_argument("--cpus", type=int, default=None)
    server_p.add_argument("--memory", type=int, default=None)
    server_p.add_argument("--dashboard", action="store_true")
    server_p.add_argument("--dashboard-port", type=int, default=None)
    server_p.add_argument("-v", "--verbose", action="store_true")
    server_p.set_defaults(func=cmd_server)

    # ── info ──
    info_p = sub.add_parser("info", help="Show system info and readiness")
    info_p.set_defaults(func=cmd_info)

    args = parser.parse_args()

    if not args.command:
        # No subcommand — check if legacy __main__.py args are being used
        # For backward compat: `bunkervm --transport sse` still works
        if len(sys.argv) > 1 and sys.argv[1].startswith("--"):
            # Legacy mode — delegate to __main__.main()
            from .__main__ import main as legacy_main
            legacy_main()
            return 0
        parser.print_help()
        _print()
        _print(f"  {_ARROW} Quick start: {_CYAN}bunkervm demo{_RESET}")
        _print()
        return 0

    return args.func(args)


def cmd_server(args: argparse.Namespace) -> int:
    """Start the MCP server (delegates to existing __main__)."""
    # Reconstruct sys.argv for the legacy parser
    new_argv = ["bunkervm"]
    new_argv.extend(["--transport", args.transport])
    if args.port != 3000:
        new_argv.extend(["--port", str(args.port)])
    if args.config:
        new_argv.extend(["--config", args.config])
    if args.no_network:
        new_argv.append("--no-network")
    if args.skip_vm:
        new_argv.append("--skip-vm")
    if args.cpus:
        new_argv.extend(["--cpus", str(args.cpus)])
    if args.memory:
        new_argv.extend(["--memory", str(args.memory)])
    if args.dashboard:
        new_argv.append("--dashboard")
    if args.dashboard_port:
        new_argv.extend(["--dashboard-port", str(args.dashboard_port)])
    if args.verbose:
        new_argv.append("--verbose")

    sys.argv = new_argv

    from .__main__ import main as legacy_main
    legacy_main()
    return 0
