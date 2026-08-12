"""
BunkerVM CLI — Developer-friendly command-line interface.

Commands:
    bunkervm demo                   # See BunkerVM in action (10 seconds)
    bunkervm run script.py          # Run a script inside a sandbox
    bunkervm run -c "print(42)"     # Run inline code
    bunkervm server                 # Start MCP server (existing behavior)
    bunkervm info                   # Show system info and readiness
    bunkervm vscode-setup           # Set up VS Code MCP integration
    bunkervm enable-network         # One-time: enable VM networking without sudo
    bunkervm engine start           # Start the engine daemon
    bunkervm engine stop            # Stop the engine daemon
    bunkervm engine status          # Check engine status
    bunkervm sandbox list           # List running sandboxes
    bunkervm sandbox create         # Create a new sandbox
    bunkervm sandbox exec           # Execute command in a sandbox
    bunkervm sandbox destroy        # Destroy a sandbox
    bunkervm replay <session>       # Replay a recorded time-travel session
    bunkervm snapshot list          # List VM snapshots
    bunkervm snapshot delete <name> # Delete a VM snapshot
    bunkervm diff <a> <b>           # Compare two agent sessions side-by-side
    bunkervm compare <a> <b> <c>    # Score and rank multiple sessions

Usage:
    pip install bunkervm
    bunkervm demo
"""

from __future__ import annotations

import argparse
import json
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


_DEMO_SCRIPT = """\
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
"""


def cmd_demo(args: argparse.Namespace) -> int:
    """Run the BunkerVM demo — shows the product in 10 seconds."""
    if getattr(args, "local", False):
        return _cmd_demo_local()

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
        _print(f"{_DIM}No Firecracker/KVM? Try: bunkervm demo --local{_RESET}")
        return 1


def _cmd_demo_local() -> int:
    """Local-backend demo: proves record/rewind, NOT isolation.

    Deliberately does not reuse _DEMO_SCRIPT — that script prints the VM's
    hostname/OS/process ID to demonstrate isolation, which would be actively
    misleading here (it would just print the user's own real machine).
    The local backend has no isolation to demonstrate; it demonstrates the
    other half of the product instead: record every step, rewind to any of
    them, on a machine that can't run Firecracker at all.
    """
    from .runtime import Sandbox

    _print()
    _print(f"{_BOLD}{_PURPLE}  ╔══════════════════════════════════════╗{_RESET}")
    _print(f"{_BOLD}{_PURPLE}  ║      BunkerVM Demo (local backend)   ║{_RESET}")
    _print(f"{_BOLD}{_PURPLE}  ║  Record + rewind — NO isolation      ║{_RESET}")
    _print(f"{_BOLD}{_PURPLE}  ╚══════════════════════════════════════╝{_RESET}")
    _print()
    _print(f"{_YELLOW}This mode runs code as a plain subprocess — no VM, no isolation.{_RESET}")
    _print(f"{_YELLOW}It exists to try record/restore/diff on machines without KVM.{_RESET}")
    _print()

    t0 = time.time()
    try:
        with Sandbox(record=True, backend="local", quiet=True) as sb:
            sb.run("x = 1")
            sb.run("x = x + 10")
            sb.run("x = x * 100")
            after_three = sb.run("print(x)")
            _print(f"  {_CYAN}x = 1; x += 10; x *= 100 -> print(x){_RESET}")
            print(after_three)

            sb.restore(step=2)
            after_restore = sb.run("print(x)")
            _print(f"\n  {_CYAN}sb.restore(step=2); print(x){_RESET}")
            print(after_restore)

            sid = sb.session_id

        elapsed = time.time() - t0
        _print()
        _print(f"{_CHECK} Demo completed in {elapsed:.1f}s")
        _print(f"{_CHECK} Record + rewind worked — real subprocess, no VM required")
        _print(f"{_CROSS} No isolation — this is NOT what you'd run untrusted agent code in")
        _print()
        _print(f"{_DIM}Learn more:{_RESET}")
        _print(f"  {_ARROW} Inspect this session:  {_CYAN}bunkervm replay {sid} --trace{_RESET}")
        _print(
            f"  {_ARROW} Real isolation:         {_CYAN}bunkervm demo{_RESET} {_DIM}(Linux, or Windows+WSL2){_RESET}"
        )
        _print(
            f'  {_ARROW} Python API:             {_CYAN}Sandbox(record=True, backend="local"){_RESET}'
        )
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
        _print("  Usage: bunkervm run script.py")
        _print("  Usage: bunkervm run -c \"print('hello')\"")
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
            backend="local" if getattr(args, "local", False) else None,
        )
        print(output)
        return 0
    except RuntimeError as e:
        _print(f"\n{_CROSS} {e}")
        if not getattr(args, "local", False):
            _print(f"{_DIM}No Firecracker/KVM? Try: bunkervm run --local ...{_RESET}")
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
            _print("              WSL2: Add nestedVirtualization=true to .wslconfig")
    else:
        _print(f"  Linux:      {_YELLOW}! Not on Linux (use WSL2 on Windows){_RESET}")

    # Local backend (always available — no isolation, subprocess only)
    _print()
    _print(f"  Local backend:  {_CHECK} available (no isolation, subprocess only)")
    _print(f"                  {_DIM}bunkervm demo --local{_RESET}")

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


# ── VS Code Setup Command ──


_SUDOERS_FILE = "/etc/sudoers.d/bunkervm"


# Platform helpers — thin wrappers around engine.platform (avoid heavy
# import at module level so `bunkervm --help` stays fast).


def _get_wsl_distro() -> str:
    from bunkervm.engine.platform import get_wsl_distro

    return get_wsl_distro()


def _is_wsl() -> bool:
    from bunkervm.engine.platform import is_wsl

    return is_wsl()


def _is_windows_workspace() -> bool:
    from bunkervm.engine.platform import is_windows_workspace

    return is_windows_workspace()


def _wsl_run(distro: str, *args: str, timeout: int = 120):
    """Run a command inside WSL — delegates to wsl_bridge.wsl_run."""
    from bunkervm.engine.wsl_bridge import wsl_run

    return wsl_run(distro, *args, timeout=timeout)


def _ensure_bunkervm_in_wsl(distro: str) -> str:
    """Ensure BunkerVM is installed in a WSL venv. Returns the bunkervm binary path."""
    from bunkervm.engine.wsl_bridge import WSLBridge

    bridge = WSLBridge(distro=distro)
    try:
        path = bridge.ensure_installed()
        _print(f"  {_CHECK} BunkerVM in WSL: {_CYAN}{path}{_RESET}")
        return path
    except RuntimeError as exc:
        _print(f"  {_CROSS} {exc}")
        return ""


def _is_network_enabled() -> bool:
    """Check if passwordless sudo for networking commands is configured."""
    import subprocess

    if sys.platform == "win32":
        try:
            distro = _get_wsl_distro()
            result = _wsl_run(distro, "sudo", "-n", "ip", "link", "show", timeout=5)
            return result.returncode == 0
        except Exception:
            return False
    else:
        try:
            result = subprocess.run(
                ["sudo", "-n", "ip", "link", "show"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False


def cmd_vscode_setup(args: argparse.Namespace) -> int:
    """Generate .vscode/mcp.json for VS Code MCP integration."""
    import json
    import shutil

    workspace = os.getcwd()
    vscode_dir = os.path.join(workspace, ".vscode")
    mcp_path = os.path.join(vscode_dir, "mcp.json")

    _print(f"\n{_BOLD}BunkerVM — VS Code MCP Setup{_RESET}\n")

    # Detect environment
    is_windows = sys.platform == "win32"
    in_wsl = _is_wsl()
    win_workspace = _is_windows_workspace()

    # Determine if VS Code needs a WSL wrapper to reach BunkerVM.
    # Case 1: Running on native Windows  → needs WSL wrapper
    # Case 2: Running in WSL, cwd is /mnt/c/... → VS Code on Windows → needs WSL wrapper
    # Case 3: Running in WSL, cwd is /home/... → VS Code Remote-WSL → direct
    # Case 4: Native Linux → direct
    needs_wsl_wrapper = is_windows or win_workspace

    if needs_wsl_wrapper:
        distro = _get_wsl_distro()
        _print(f"  Platform:  {_CYAN}Windows + WSL2 ({distro}){_RESET}")

        # Auto-install BunkerVM in WSL venv
        bunkervm_bin = _ensure_bunkervm_in_wsl(distro)
        if not bunkervm_bin:
            return 1

        config = {
            "servers": {
                "bunkervm": {"command": "wsl", "args": ["-d", distro, "--", bunkervm_bin, "server"]}
            }
        }
    else:
        python_bin = shutil.which("python3") or shutil.which("python") or "python3"
        bunkervm_bin = shutil.which("bunkervm")

        if bunkervm_bin:
            config = {"servers": {"bunkervm": {"command": bunkervm_bin, "args": ["server"]}}}
        else:
            config = {
                "servers": {
                    "bunkervm": {"command": python_bin, "args": ["-m", "bunkervm", "server"]}
                }
            }

        if in_wsl:
            _print(f"  Platform:  {_CYAN}WSL2 (VS Code Remote){_RESET}")
        else:
            _print(f"  Platform:  {_CYAN}Linux{_RESET}")

    # Check if file already exists
    if os.path.exists(mcp_path):
        try:
            with open(mcp_path, "r") as f:
                existing = json.load(f)
            if "servers" in existing and "bunkervm" in existing.get("servers", {}):
                _print(f"  {_CHECK} BunkerVM already configured in {mcp_path}")
                _print(
                    f"\n  {_DIM}To reconfigure, delete .vscode/mcp.json and run again.{_RESET}\n"
                )
                return 0
            # Merge into existing config
            existing.setdefault("servers", {})
            existing["servers"]["bunkervm"] = config["servers"]["bunkervm"]
            config = existing
            _print(f"  {_ARROW} Merging into existing mcp.json")
        except (json.JSONDecodeError, OSError):
            _print(f"  {_YELLOW}! Existing mcp.json is invalid, overwriting{_RESET}")

    # Create .vscode/ if needed
    os.makedirs(vscode_dir, exist_ok=True)

    # Write config
    with open(mcp_path, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")

    _print(f"  {_CHECK} Created {mcp_path}")
    _print()
    _print(f"  {_BOLD}What's next:{_RESET}")
    _print(f'  1. Reload VS Code ({_CYAN}Ctrl+Shift+P{_RESET} → "Reload Window")')
    _print(f"  2. Open Copilot Chat ({_CYAN}Ctrl+Shift+I{_RESET})")
    _print(f'  {_DIM}Ask: "Run this Python script in the sandbox"{_RESET}')
    _print()
    _print(f"  {_DIM}Tools: sandbox_exec, sandbox_write_file, sandbox_read_file,{_RESET}")
    _print(f"  {_DIM}       sandbox_list_dir, sandbox_upload_file, sandbox_download_file,{_RESET}")
    _print(f"  {_DIM}       sandbox_status, sandbox_reset{_RESET}")
    _print()
    return 0


# ── Enable Network Command ──


def cmd_enable_network(args: argparse.Namespace) -> int:
    """Configure passwordless sudo for VM networking (one-time setup)."""
    import subprocess
    import getpass

    _print(f"\n{_BOLD}BunkerVM — Enable VM Networking{_RESET}\n")

    if sys.platform == "win32":
        # Auto-proxy to WSL — password prompt appears in this terminal
        distro = _get_wsl_distro()
        bunkervm_bin = _ensure_bunkervm_in_wsl(distro)
        if not bunkervm_bin:
            _print(
                f"  {_CROSS} BunkerVM not found in WSL. Run {_CYAN}bunkervm vscode-setup{_RESET} first.\n"
            )
            return 1

        _print(f"  {_ARROW} Running in WSL ({distro})... enter your WSL password when prompted.\n")
        result = subprocess.run(
            ["wsl", "-d", distro, "--", "sudo", bunkervm_bin, "enable-network"],
            timeout=60,
        )
        return result.returncode

    # Must be run as root
    if os.geteuid() != 0:
        _print(f"  {_CROSS} This command requires sudo.")
        _print(f"  Run: {_CYAN}sudo bunkervm enable-network{_RESET}\n")
        return 1

    # Get the actual user (not root)
    user = os.environ.get("SUDO_USER", getpass.getuser())

    # Check if already configured
    if os.path.exists(_SUDOERS_FILE):
        _print(f"  {_CHECK} Already configured: {_SUDOERS_FILE}")
        _print(f"  {_DIM}To reset, delete {_SUDOERS_FILE} and run again.{_RESET}\n")
        return 0

    # Find actual paths for ip, sysctl, iptables
    import shutil

    ip_bin = shutil.which("ip") or "/usr/sbin/ip"
    sysctl_bin = shutil.which("sysctl") or "/usr/sbin/sysctl"
    iptables_bin = shutil.which("iptables") or "/usr/sbin/iptables"

    sudoers_content = (
        f"# BunkerVM: allow passwordless networking for VM setup\n"
        f"# Created by: bunkervm enable-network\n"
        f"# Safe to remove: sudo rm {_SUDOERS_FILE}\n"
        f"{user} ALL=(ALL) NOPASSWD: {ip_bin}\n"
        f"{user} ALL=(ALL) NOPASSWD: {sysctl_bin}\n"
        f"{user} ALL=(ALL) NOPASSWD: {iptables_bin}\n"
    )

    # Write sudoers file
    try:
        with open(_SUDOERS_FILE, "w") as f:
            f.write(sudoers_content)
        os.chmod(_SUDOERS_FILE, 0o440)

        # Validate with visudo
        result = subprocess.run(
            ["visudo", "-c", "-f", _SUDOERS_FILE],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            os.remove(_SUDOERS_FILE)
            _print(f"  {_CROSS} Sudoers validation failed: {result.stderr.strip()}")
            return 1

    except OSError as e:
        _print(f"  {_CROSS} Failed to write {_SUDOERS_FILE}: {e}")
        return 1

    _print(f"  {_CHECK} Created {_SUDOERS_FILE}")
    _print(f"  {_CHECK} User '{user}' can now create VM networks without a password")
    _print()
    _print(f"  {_BOLD}Granted passwordless sudo for:{_RESET}")
    _print(f"    {_DIM}{ip_bin}{_RESET}       (TAP device setup)")
    _print(f"    {_DIM}{sysctl_bin}{_RESET}   (IP forwarding)")
    _print(f"    {_DIM}{iptables_bin}{_RESET} (NAT rules)")
    _print()
    _print(
        f"  {_BOLD}Next:{_RESET} Re-run {_CYAN}bunkervm vscode-setup{_RESET} to update VS Code config,"
    )
    _print("        or restart the MCP server in VS Code.")
    _print()
    _print(f"  {_DIM}To undo: sudo rm {_SUDOERS_FILE}{_RESET}")
    _print()
    return 0


# ── Main CLI Parser ──


def _engine_url(port: int = None) -> str:
    """Get the engine base URL."""
    from bunkervm.engine.config import DEFAULT_ENGINE_PORT

    p = port or DEFAULT_ENGINE_PORT
    return f"http://127.0.0.1:{p}"


def _engine_request(method: str, path: str, body: dict = None, port: int = None) -> dict:
    """Make an HTTP request to the engine API. Returns parsed JSON or raises."""
    import urllib.request
    import urllib.error

    url = _engine_url(port) + path
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise ConnectionError(f"Cannot reach engine at {url}: {e}") from e
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        try:
            err = json.loads(body_text)
            raise RuntimeError(err.get("error", "Unknown error") + ": " + err.get("detail", ""))
        except json.JSONDecodeError:
            raise RuntimeError(f"HTTP {e.code}: {body_text}")


# ── Engine Commands ──


def cmd_engine_start(args: argparse.Namespace) -> int:
    """Start the BunkerVM engine daemon.

    On Windows the engine is automatically started inside WSL2 via the
    WSL bridge.  On Linux / WSL it boots directly.
    """
    from bunkervm.engine.platform import is_windows

    if is_windows():
        return _engine_start_windows(args)
    return _engine_start_linux(args)


def _engine_start_windows(args: argparse.Namespace) -> int:
    """Start the engine inside WSL2 from Windows."""
    from bunkervm.engine.wsl_bridge import WSLBridge

    _print(f"\n{_BOLD}BunkerVM Engine (Windows → WSL2){_RESET}\n")

    try:
        bridge = WSLBridge()
    except RuntimeError as exc:
        _print(f"  {_CROSS} {exc}")
        _print(f"  {_DIM}Install WSL2: wsl --install -d Ubuntu{_RESET}\n")
        return 1

    # Pre-flight checks
    problems = bridge.check_ready()
    if problems:
        for p in problems:
            _print(f"  {_CROSS} {p}")
        _print()
        return 1

    # Ensure bunkervm is installed in WSL
    _print(f"  {_ARROW} Using WSL distro: {_CYAN}{bridge.distro}{_RESET}")
    try:
        bunkervm_bin = bridge.ensure_installed()
        _print(f"  {_CHECK} BunkerVM installed: {_CYAN}{bunkervm_bin}{_RESET}")
    except RuntimeError as exc:
        _print(f"  {_CROSS} {exc}")
        return 1

    # Start the engine
    foreground = not args.background
    ok = bridge.start_engine(
        port=args.port,
        max_sandboxes=args.max_sandboxes,
        cpus=args.cpus,
        memory=args.memory,
        foreground=foreground,
    )

    if ok:
        _print(f"  {_CHECK} Engine running on port {args.port}")
        _print(f"  API: http://127.0.0.1:{args.port}")
        _print()
        return 0
    else:
        _print(f"  {_CROSS} Engine failed to start.  Check logs inside WSL:")
        _print(f"  {_DIM}wsl -d {bridge.distro} -- cat ~/.bunkervm/logs/engine.log{_RESET}\n")
        return 1


def _engine_start_linux(args: argparse.Namespace) -> int:
    """Start the engine directly on Linux / WSL."""
    from bunkervm.engine.config import EngineConfig
    from bunkervm.engine.daemon import EngineDaemon

    # Auto-detect WSL2 — bind to 0.0.0.0 so Windows can reach the engine
    host = getattr(args, "host", None) or None
    if host is None:
        in_wsl = _is_wsl()
        host = "0.0.0.0" if in_wsl else "127.0.0.1"

    config = EngineConfig(
        host=host,
        port=args.port,
        max_sandboxes=args.max_sandboxes,
        default_cpus=args.cpus,
        default_memory=args.memory,
    )

    # Check if already running
    existing_pid = config.read_pid()
    if existing_pid:
        _print(f"{_CHECK} Engine already running (PID {existing_pid})")
        _print(f"  API: http://127.0.0.1:{config.port}")
        return 0

    if args.background:
        # Launch as background process
        import subprocess

        cmd = [
            sys.executable,
            "-m",
            "bunkervm",
            "engine",
            "start",
            "--host",
            host,
            "--port",
            str(args.port),
            "--max-sandboxes",
            str(args.max_sandboxes),
            "--cpus",
            str(args.cpus),
            "--memory",
            str(args.memory),
        ]
        # Don't pass --background again to avoid infinite recursion
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=open(config.log_file, "a"),
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        # Wait briefly for startup
        time.sleep(1)
        if proc.poll() is None:
            _print(f"{_CHECK} Engine started in background (PID {proc.pid})")
            _print(f"  API: http://127.0.0.1:{config.port}")
            _print(f"  Log: {config.log_file}")
            return 0
        else:
            _print(f"{_CROSS} Engine failed to start. Check {config.log_file}")
            return 1
    else:
        # Foreground mode — blocks
        _print(f"\n{_BOLD}BunkerVM Engine{_RESET}\n")
        daemon = EngineDaemon(config)
        daemon.start()
        return 0


def cmd_engine_stop(args: argparse.Namespace) -> int:
    """Stop the BunkerVM engine daemon.

    Works identically on Windows and Linux — the engine always listens on
    localhost so we just POST /engine/stop.
    """
    try:
        result = _engine_request("POST", "/engine/stop", port=args.port)
        _print(f"{_CHECK} {result.get('message', 'Engine stopping...')}")
        return 0
    except ConnectionError:
        _print(f"{_YELLOW}Engine is not running{_RESET}")
        # Clean up stale PID file (only meaningful on Linux / WSL)
        from bunkervm.engine.platform import is_windows

        if not is_windows():
            from bunkervm.engine.config import EngineConfig

            EngineConfig(port=args.port).clear_pid()
        return 0
    except Exception as e:
        _print(f"{_CROSS} Failed to stop engine: {e}")
        return 1


def cmd_engine_status(args: argparse.Namespace) -> int:
    """Show the BunkerVM engine status."""
    try:
        status = _engine_request("GET", "/engine/status", port=args.port)
        _print(f"\n{_BOLD}BunkerVM Engine Status{_RESET}\n")
        _print(f"  Status:      {_GREEN}{status['status']}{_RESET}")
        _print(f"  Version:     {_CYAN}{status['version']}{_RESET}")
        _print(f"  Platform:    {status['platform']}")
        _print(f"  Sandboxes:   {status['sandbox_count']} / {status['max_sandboxes']}")
        _print(f"  Uptime:      {_format_duration(status['uptime_seconds'])}")
        _print(f"  API:         {_engine_url(args.port)}")
        _print()
        return 0
    except ConnectionError:
        _print(f"\n{_BOLD}BunkerVM Engine Status{_RESET}\n")
        _print(f"  Status:      {_RED}not running{_RESET}")
        _print(f"  {_DIM}Start with: bunkervm engine start{_RESET}")
        _print()
        return 1


# ── Sandbox Commands ──


def cmd_sandbox_list(args: argparse.Namespace) -> int:
    """List all running sandboxes."""
    try:
        data = _engine_request("GET", "/sandboxes", port=args.port)
    except ConnectionError:
        _print(
            f"{_CROSS} Engine is not running. Start it with: {_CYAN}bunkervm engine start{_RESET}"
        )
        return 1

    sandboxes = data.get("sandboxes", [])
    if not sandboxes:
        _print(f"\n  {_DIM}No running sandboxes{_RESET}")
        _print(f"  Create one: {_CYAN}bunkervm sandbox create --name my-sandbox{_RESET}\n")
        return 0

    # Table header
    _print(
        f"\n{'ID':>10}  {'NAME':<20}  {'STATUS':<10}  {'CPUS':>4}  {'MEMORY':>8}  {'UPTIME':>10}"
    )
    _print(f"{'─' * 10}  {'─' * 20}  {'─' * 10}  {'─' * 4}  {'─' * 8}  {'─' * 10}")

    for sb in sandboxes:
        status_color = _GREEN if sb["status"] == "running" else _RED
        _print(
            f"{sb['id']:>10}  {sb['name']:<20}  "
            f"{status_color}{sb['status']:<10}{_RESET}  "
            f"{sb['cpus']:>4}  {sb['memory_mb']:>6}MB  "
            f"{_format_duration(sb.get('uptime_seconds', 0)):>10}"
        )
    _print()
    return 0


def cmd_sandbox_create(args: argparse.Namespace) -> int:
    """Create a new sandbox."""
    body = {}
    if args.name:
        body["name"] = args.name
    if args.cpus:
        body["cpus"] = args.cpus
    if args.memory:
        body["memory"] = args.memory
    if args.no_network:
        body["network"] = False

    try:
        _print(f"  {_ARROW} Creating sandbox...", end="")
        result = _engine_request("POST", "/sandboxes", body=body, port=args.port)
        _print(f"\r{_CHECK} Sandbox created")
        _print(f"  ID:   {_CYAN}{result['id']}{_RESET}")
        _print(f"  Name: {result['name']}")
        _print(f"  CPUs: {result['cpus']}   Memory: {result['memory_mb']}MB")
        _print()
        return 0
    except ConnectionError:
        _print(
            f"\r{_CROSS} Engine is not running. Start it with: {_CYAN}bunkervm engine start{_RESET}"
        )
        return 1
    except RuntimeError as e:
        _print(f"\r{_CROSS} {e}")
        return 1


def cmd_sandbox_exec(args: argparse.Namespace) -> int:
    """Execute a command in a sandbox."""
    sandbox_id = args.sandbox
    command = args.command

    if not command:
        _print(f"{_CROSS} Provide a command to execute")
        _print('  Usage: bunkervm sandbox exec <id|name> "command"')
        return 1

    try:
        result = _engine_request(
            "POST",
            f"/sandboxes/{sandbox_id}/exec",
            body={"command": command, "timeout": args.timeout},
            port=args.port,
        )
        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        exit_code = result.get("exit_code", -1)

        if stdout:
            print(stdout)
        if stderr:
            _print(f"{_RED}{stderr}{_RESET}")
        return exit_code
    except ConnectionError:
        _print(f"{_CROSS} Engine is not running")
        return 1
    except RuntimeError as e:
        _print(f"{_CROSS} {e}")
        return 1


def cmd_sandbox_destroy(args: argparse.Namespace) -> int:
    """Destroy a sandbox."""
    sandbox_id = args.sandbox

    try:
        _engine_request("DELETE", f"/sandboxes/{sandbox_id}", port=args.port)
        _print(f"{_CHECK} Sandbox '{sandbox_id}' destroyed")
        return 0
    except ConnectionError:
        _print(f"{_CROSS} Engine is not running")
        return 1
    except RuntimeError as e:
        _print(f"{_CROSS} {e}")
        return 1


def cmd_sandbox_logs(args: argparse.Namespace) -> int:
    """Show sandbox status and details."""
    sandbox_id = args.sandbox

    try:
        info = _engine_request("GET", f"/sandboxes/{sandbox_id}", port=args.port)
        _print(f"\n{_BOLD}Sandbox: {info['name']}{_RESET}\n")
        _print(f"  ID:       {_CYAN}{info['id']}{_RESET}")
        _print(f"  Status:   {_GREEN}{info['status']}{_RESET}")
        _print(f"  CPUs:     {info['cpus']}")
        _print(f"  Memory:   {info['memory_mb']}MB")
        _print(f"  Network:  {'yes' if info.get('network') else 'no'}")
        _print(f"  Uptime:   {_format_duration(info.get('uptime_seconds', 0))}")
        if info.get("pid"):
            _print(f"  PID:      {info['pid']}")
        _print()

        # Also fetch VM-level status
        try:
            vm_status = _engine_request(
                "GET",
                f"/sandboxes/{sandbox_id}/status",
                port=args.port,
            )
            if vm_status.get("status") == "ok":
                _print(f"  {_BOLD}VM Resources:{_RESET}")
                cpu = vm_status.get("cpu", {})
                mem = vm_status.get("memory", {})
                disk = vm_status.get("disk", {})
                if cpu:
                    _print(f"    CPU load:  {cpu.get('load_1m', '?')}")
                if mem:
                    used = mem.get("used_mb", "?")
                    total = mem.get("total_mb", "?")
                    _print(f"    Memory:    {used}MB / {total}MB")
                if disk:
                    used = disk.get("used_mb", "?")
                    total = disk.get("total_mb", "?")
                    _print(f"    Disk:      {used}MB / {total}MB")
                _print()
        except Exception:
            pass  # VM status is optional

        return 0
    except ConnectionError:
        _print(f"{_CROSS} Engine is not running")
        return 1
    except RuntimeError as e:
        _print(f"{_CROSS} {e}")
        return 1


# ── Replay (Time-Travel) ──


def _load_session(session_ref: str) -> dict:
    """Load a session from an ID or file path."""
    # Try as a file path first
    if os.path.isfile(session_ref):
        with open(session_ref) as f:
            return json.load(f)

    # Try as a session ID in ~/.bunkervm/sessions/
    sessions_dir = os.path.join(os.path.expanduser("~"), ".bunkervm", "sessions")
    session_path = os.path.join(sessions_dir, f"{session_ref}.json")
    if os.path.isfile(session_path):
        with open(session_path) as f:
            return json.load(f)

    # Try partial match
    if os.path.isdir(sessions_dir):
        for name in os.listdir(sessions_dir):
            if name.startswith(session_ref) and name.endswith(".json"):
                with open(os.path.join(sessions_dir, name)) as f:
                    return json.load(f)

    raise FileNotFoundError(f"Session not found: {session_ref}")


def cmd_replay(args: argparse.Namespace) -> int:
    """Replay a recorded sandbox session."""
    try:
        session = _load_session(args.session)
    except FileNotFoundError as e:
        _print(f"{_CROSS} {e}")
        return 1

    checkpoints = session.get("checkpoints", [])
    sid = session.get("session_id", "unknown")
    total = session.get("total_steps", len(checkpoints))

    if args.step:
        # Show details for a specific step
        cp = None
        for c in checkpoints:
            if c["step"] == args.step:
                cp = c
                break
        if cp is None:
            _print(f"{_CROSS} Step {args.step} not found in session {sid}")
            return 1

        _print(f"\n{_BOLD}Session {sid} — Step {cp['step']}/{total}{_RESET}\n")
        _print(f"  {_DIM}Command:{_RESET}  {cp['command']}")
        _print(f"  {_DIM}Exit:{_RESET}     {cp['exit_code']}")
        _print(f"  {_DIM}Duration:{_RESET} {cp.get('duration_ms', 0):.0f}ms")
        if cp.get("snapshot_name"):
            _print(f"  {_DIM}Snapshot:{_RESET} {_GREEN}{cp['snapshot_name']}{_RESET}")
        if cp.get("stdout"):
            _print(f"\n  {_BOLD}stdout:{_RESET}")
            for line in cp["stdout"].splitlines()[:20]:
                _print(f"    {line}")
        if cp.get("stderr"):
            _print(f"\n  {_BOLD}stderr:{_RESET}")
            for line in cp["stderr"].splitlines()[:10]:
                _print(f"    {_YELLOW}{line}{_RESET}")
        if args.trace and cp.get("trace"):
            _print_trace(cp["trace"])
        _print()
        return 0

    # Show full timeline
    _print(f"\n{_BOLD}Session: {sid}{_RESET}")
    _print(f"  Steps: {total}")
    _print(
        f"  Recorded: {time.strftime('%Y-%m-%d %H:%M', time.localtime(session.get('created_at', 0)))}"
    )
    _print(f"\n{_BOLD}Timeline:{_RESET}\n")

    for cp in checkpoints:
        step = cp["step"]
        cmd = cp["command"]
        exit_code = cp["exit_code"]
        duration = cp.get("duration_ms", 0)
        has_snap = "📸" if cp.get("snapshot_name") else "  "

        # Color code the exit status
        if exit_code == 0:
            status = f"{_GREEN}ok{_RESET}"
        else:
            status = f"{_RED}exit {exit_code}{_RESET}"

        _print(
            f"  {has_snap} {_DIM}step {step:3d}{_RESET}  [{status}]  {duration:6.0f}ms  {cmd[:70]}"
        )

        if args.trace and cp.get("trace"):
            _print_trace(cp["trace"], indent=12)

    _print()
    return 0


def _print_trace(trace: dict, indent: int = 6) -> None:
    """Print filesystem trace data."""
    pad = " " * indent
    created = trace.get("files_created", [])
    modified = trace.get("files_modified", [])
    deleted = trace.get("files_deleted", [])
    bytes_w = trace.get("bytes_written", 0)

    if created:
        _print(f"{pad}{_GREEN}+ {len(created)} files created{_RESET}", end="")
        if bytes_w:
            _print(f" ({bytes_w} bytes)", end="")
        _print()
        for f in created[:5]:
            _print(f"{pad}  {_GREEN}+ {f['path']}{_RESET} ({f.get('size', '?')}b)")
        if len(created) > 5:
            _print(f"{pad}  ... and {len(created) - 5} more")

    if modified:
        _print(f"{pad}{_YELLOW}~ {len(modified)} files modified{_RESET}")
        for f in modified[:5]:
            _print(f"{pad}  {_YELLOW}~ {f['path']}{_RESET}")

    if deleted:
        _print(f"{pad}{_RED}- {len(deleted)} files deleted{_RESET}")
        for f in deleted[:5]:
            _print(f"{pad}  {_RED}- {f['path']}{_RESET}")


# ── Snapshot Management ──


def cmd_snapshot_list(args: argparse.Namespace) -> int:
    """List available VM snapshots."""
    from .snapshot import SnapshotManager

    mgr = SnapshotManager()
    snapshots = mgr.list()

    if not snapshots:
        _print(f"\n  {_DIM}No snapshots found.{_RESET}")
        _print(f"  Create one with: {_CYAN}Sandbox(record=True){_RESET}\n")
        return 0

    _print(f"\n{_BOLD}VM Snapshots:{_RESET}\n")
    for snap in snapshots:
        created = time.strftime("%Y-%m-%d %H:%M", time.localtime(snap.created_at))
        vmstate_mb = os.path.getsize(snap.vmstate_path) / (1024 * 1024)
        memory_mb = os.path.getsize(snap.memory_path) / (1024 * 1024)
        _print(
            f"  {_CYAN}{snap.name}{_RESET}  "
            f"{created}  "
            f"{snap.vcpu_count}vcpu/{snap.mem_size_mib}MB  "
            f"vmstate={vmstate_mb:.1f}MB mem={memory_mb:.1f}MB"
        )

    _print(f"\n  {_DIM}Total: {len(snapshots)} snapshots{_RESET}\n")
    return 0


def cmd_snapshot_delete(args: argparse.Namespace) -> int:
    """Delete a VM snapshot."""
    from .snapshot import SnapshotManager

    mgr = SnapshotManager()
    if mgr.delete(args.name):
        _print(f"{_CHECK} Deleted snapshot: {args.name}")
        return 0
    else:
        _print(f"{_CROSS} Snapshot not found: {args.name}")
        return 1


# ── Agent Diff ──


def cmd_diff(args: argparse.Namespace) -> int:
    """Compare two recorded sandbox sessions side by side."""
    try:
        session_a = _load_session(args.session_a)
        session_b = _load_session(args.session_b)
    except FileNotFoundError as e:
        _print(f"{_CROSS} {e}")
        return 1

    result = _compute_diff(session_a, session_b)

    if args.format == "json":
        print(json.dumps(result, indent=2, default=str))
        return 0

    # Text format
    _print(f"\n{_BOLD}Agent Diff{_RESET}")
    _print(
        f"  Session A: {_CYAN}{session_a.get('session_id', '?')}{_RESET} ({result['summary']['steps_a']} steps)"
    )
    _print(
        f"  Session B: {_CYAN}{session_b.get('session_id', '?')}{_RESET} ({result['summary']['steps_b']} steps)"
    )
    _print()

    # Summary
    s = result["summary"]
    _print(f"  {_BOLD}Summary:{_RESET}")
    _print(f"    Total time A: {s['total_duration_a']:.0f}ms")
    _print(f"    Total time B: {s['total_duration_b']:.0f}ms")
    _print(f"    Files only in A: {len(s['files_only_a'])}")
    _print(f"    Files only in B: {len(s['files_only_b'])}")
    _print(f"    Files in both:   {len(s['files_both'])}")
    _print()

    # Show files unique to each session
    if s["files_only_a"]:
        _print(f"  {_BOLD}Files only in A:{_RESET}")
        for f in s["files_only_a"][:10]:
            _print(f"    {_RED}{f}{_RESET}")
    if s["files_only_b"]:
        _print(f"  {_BOLD}Files only in B:{_RESET}")
        for f in s["files_only_b"][:10]:
            _print(f"    {_GREEN}{f}{_RESET}")

    # Show step-by-step comparison
    if result.get("step_comparison"):
        _print(f"\n  {_BOLD}Step Comparison:{_RESET}\n")
        for comp in result["step_comparison"]:
            step = comp["step"]
            cmd_a = comp.get("command_a", "-")
            cmd_b = comp.get("command_b", "-")
            if cmd_a == cmd_b:
                _print(f"    step {step:3d}  {_DIM}[same]{_RESET}  {cmd_a[:60]}")
            else:
                _print(f"    step {step:3d}  {_YELLOW}[diff]{_RESET}")
                _print(f"      A: {cmd_a[:60]}")
                _print(f"      B: {cmd_b[:60]}")

    _print()
    return 0


def _compute_diff(session_a: dict, session_b: dict) -> dict:
    """Compute a structured diff between two sessions."""
    cps_a = session_a.get("checkpoints", [])
    cps_b = session_b.get("checkpoints", [])

    # Aggregate filesystem traces
    def aggregate_traces(checkpoints):
        all_created = set()
        all_modified = set()
        all_deleted = set()
        total_duration = 0
        for cp in checkpoints:
            total_duration += cp.get("duration_ms", 0)
            trace = cp.get("trace")
            if trace:
                for f in trace.get("files_created", []):
                    all_created.add(f["path"])
                for f in trace.get("files_modified", []):
                    all_modified.add(f["path"])
                for f in trace.get("files_deleted", []):
                    all_deleted.add(f["path"])
        all_files = all_created | all_modified
        return all_files, all_deleted, total_duration

    files_a, deleted_a, duration_a = aggregate_traces(cps_a)
    files_b, deleted_b, duration_b = aggregate_traces(cps_b)

    # Step-by-step comparison
    max_steps = max(len(cps_a), len(cps_b))
    step_comparison = []
    for i in range(max_steps):
        comp = {"step": i + 1}
        if i < len(cps_a):
            comp["command_a"] = cps_a[i].get("command", "")
            comp["exit_code_a"] = cps_a[i].get("exit_code", -1)
        if i < len(cps_b):
            comp["command_b"] = cps_b[i].get("command", "")
            comp["exit_code_b"] = cps_b[i].get("exit_code", -1)
        step_comparison.append(comp)

    return {
        "summary": {
            "steps_a": len(cps_a),
            "steps_b": len(cps_b),
            "total_duration_a": duration_a,
            "total_duration_b": duration_b,
            "files_only_a": sorted(files_a - files_b),
            "files_only_b": sorted(files_b - files_a),
            "files_both": sorted(files_a & files_b),
        },
        "step_comparison": step_comparison,
    }


# ── Agent Compare (quality matrix) ──


def cmd_compare(args: argparse.Namespace) -> int:
    """Score and rank multiple recorded sessions side by side."""
    from .report import compare_sessions, render_html_report

    sessions = []
    for ref in args.sessions:
        try:
            sessions.append(_load_session(ref))
        except FileNotFoundError as e:
            _print(f"{_CROSS} {e}")
            return 1

    labels = getattr(args, "label", None)
    if labels and len(labels) != len(sessions):
        _print(
            f"{_CROSS} --label given {len(labels)} times but {len(sessions)} sessions were passed"
        )
        return 1

    result = compare_sessions(sessions, labels=labels)

    if args.format == "json":
        print(json.dumps(result, indent=2, default=str))
    else:
        _print(f"\n{_BOLD}Agent Comparison{_RESET}  {_DIM}({len(sessions)} sessions){_RESET}\n")
        for s in result["sessions"]:
            marker = f"{_GREEN}#{s['rank']}{_RESET}" if s["rank"] == 1 else f"#{s['rank']}"
            status = (
                f"{_GREEN}completed{_RESET}"
                if s["success"]
                else f"{_RED}failed (step {s['failed_steps'][0] if s['failed_steps'] else '?'}){_RESET}"
            )
            risky = s["risk_counts"]["destructive"] + s["risk_counts"]["blocked"]
            risk_note = f" {_RED}({risky} destructive/blocked){_RESET}" if risky else ""
            _print(
                f"  {marker}  {_CYAN}{s['label']}{_RESET}  [{s['backend']}]  "
                f"{s['steps']} steps  {status}  {s['total_duration_ms']:.0f}ms{risk_note}"
            )
            _print(
                f"      files: +{s['files_created']} created  ~{s['files_modified']} modified  "
                f"-{s['files_deleted']} deleted"
            )
        if result["divergences"]:
            _print(f"\n  {_BOLD}Divergence from baseline ({result['baseline']}):{_RESET}")
            for d in result["divergences"]:
                if d["first_diverging_step"] is None:
                    _print(f"    {d['compared']}: identical command sequence")
                else:
                    _print(f"    {d['compared']}: diverged at step {d['first_diverging_step']}")
        _print(
            f"\n  {_DIM}Ranked by: completed without a failed step, then fewest "
            f"destructive/blocked commands, then total time.{_RESET}\n"
        )

    if args.html:
        render_html_report(result, args.html)
        _print(f"{_CHECK} HTML report written to {args.html}")

    return 0


def _format_duration(seconds: float) -> str:
    """Format seconds into human-readable duration."""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    else:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        return f"{h}h {m}m"


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
  bunkervm replay <session-id>         Replay a recorded session
  bunkervm replay <session> --trace    Replay with filesystem traces
  bunkervm snapshot list               List VM snapshots
  bunkervm diff <session-a> <session-b>  Compare two agent runs
  bunkervm compare <a> <b> <c> --html report.html  Rank multiple runs
""",
    )
    sub = parser.add_subparsers(dest="command")

    # ── demo ──
    demo_p = sub.add_parser("demo", help="See BunkerVM in action (10 seconds)")
    demo_p.add_argument(
        "--local",
        action="store_true",
        help="Use the local backend (no isolation, works without KVM/WSL2 — e.g. macOS)",
    )
    demo_p.set_defaults(func=cmd_demo)

    # ── run ──
    run_p = sub.add_parser("run", help="Run code inside a sandbox")
    run_p.add_argument("file", nargs="?", help="Script file to execute")
    run_p.add_argument("-c", "--code", help="Inline code to execute")
    run_p.add_argument(
        "-l",
        "--language",
        choices=["python", "bash", "node"],
        help="Language (auto-detected from extension)",
    )
    run_p.add_argument(
        "-t", "--timeout", type=int, default=30, help="Execution timeout in seconds (default: 30)"
    )
    run_p.add_argument("--cpus", type=int, default=1, help="vCPUs (default: 1)")
    run_p.add_argument("--memory", type=int, default=512, help="Memory in MB (default: 512)")
    run_p.add_argument("--no-network", action="store_true", help="Disable internet in VM")
    run_p.add_argument("-q", "--quiet", action="store_true", help="Suppress progress messages")
    run_p.add_argument(
        "--local",
        action="store_true",
        help="Use the local backend (no isolation, works without KVM/WSL2 — e.g. macOS)",
    )
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

    # ── vscode-setup ──
    vs_p = sub.add_parser("vscode-setup", help="Set up VS Code MCP integration")
    vs_p.set_defaults(func=cmd_vscode_setup)

    # ── enable-network ──
    net_p = sub.add_parser("enable-network", help="Enable VM networking without sudo (one-time)")
    net_p.set_defaults(func=cmd_enable_network)

    # ── engine ──
    engine_p = sub.add_parser("engine", help="Manage the BunkerVM engine daemon")
    engine_sub = engine_p.add_subparsers(dest="engine_command")

    engine_start_p = engine_sub.add_parser("start", help="Start the engine daemon")
    engine_start_p.add_argument(
        "--host",
        type=str,
        default=None,
        help="Bind address (default: 0.0.0.0 in WSL, 127.0.0.1 on Linux)",
    )
    engine_start_p.add_argument("--port", type=int, default=9551, help="API port (default: 9551)")
    engine_start_p.add_argument(
        "--max-sandboxes", type=int, default=10, help="Max concurrent sandboxes (default: 10)"
    )
    engine_start_p.add_argument(
        "--cpus", type=int, default=1, help="Default vCPUs per sandbox (default: 1)"
    )
    engine_start_p.add_argument(
        "--memory", type=int, default=512, help="Default memory per sandbox in MB (default: 512)"
    )
    engine_start_p.add_argument(
        "-d", "--background", action="store_true", help="Run engine in background"
    )
    engine_start_p.set_defaults(func=cmd_engine_start)

    engine_stop_p = engine_sub.add_parser("stop", help="Stop the engine daemon")
    engine_stop_p.add_argument("--port", type=int, default=9551, help="API port")
    engine_stop_p.set_defaults(func=cmd_engine_stop)

    engine_status_p = engine_sub.add_parser("status", help="Show engine status")
    engine_status_p.add_argument("--port", type=int, default=9551, help="API port")
    engine_status_p.set_defaults(func=cmd_engine_status)

    # ── sandbox ──
    sandbox_p = sub.add_parser("sandbox", help="Manage sandboxes")
    sandbox_sub = sandbox_p.add_subparsers(dest="sandbox_command")

    sb_list_p = sandbox_sub.add_parser("list", help="List running sandboxes")
    sb_list_p.add_argument("--port", type=int, default=9551, help="Engine API port")
    sb_list_p.set_defaults(func=cmd_sandbox_list)

    sb_create_p = sandbox_sub.add_parser("create", help="Create a new sandbox")
    sb_create_p.add_argument("--name", help="Sandbox name")
    sb_create_p.add_argument("--cpus", type=int, help="vCPUs")
    sb_create_p.add_argument("--memory", type=int, help="Memory in MB")
    sb_create_p.add_argument("--no-network", action="store_true", help="Disable networking")
    sb_create_p.add_argument("--port", type=int, default=9551, help="Engine API port")
    sb_create_p.set_defaults(func=cmd_sandbox_create)

    sb_exec_p = sandbox_sub.add_parser("exec", help="Execute command in a sandbox")
    sb_exec_p.add_argument("sandbox", help="Sandbox ID or name")
    sb_exec_p.add_argument("command", help="Command to execute")
    sb_exec_p.add_argument("-t", "--timeout", type=int, default=30, help="Timeout in seconds")
    sb_exec_p.add_argument("--port", type=int, default=9551, help="Engine API port")
    sb_exec_p.set_defaults(func=cmd_sandbox_exec)

    sb_destroy_p = sandbox_sub.add_parser("destroy", help="Destroy a sandbox")
    sb_destroy_p.add_argument("sandbox", help="Sandbox ID or name")
    sb_destroy_p.add_argument("--port", type=int, default=9551, help="Engine API port")
    sb_destroy_p.set_defaults(func=cmd_sandbox_destroy)

    sb_logs_p = sandbox_sub.add_parser("logs", help="Show sandbox details and status")
    sb_logs_p.add_argument("sandbox", help="Sandbox ID or name")
    sb_logs_p.add_argument("--port", type=int, default=9551, help="Engine API port")
    sb_logs_p.set_defaults(func=cmd_sandbox_logs)

    # ── replay (time-travel) ──
    replay_p = sub.add_parser("replay", help="Replay a recorded sandbox session")
    replay_p.add_argument("session", help="Session ID or path to session JSON")
    replay_p.add_argument("--step", type=int, help="Show details for a specific step")
    replay_p.add_argument(
        "--trace", action="store_true", help="Show filesystem trace for each step"
    )
    replay_p.set_defaults(func=cmd_replay)

    # ── snapshot ──
    snap_p = sub.add_parser("snapshot", help="Manage VM snapshots")
    snap_sub = snap_p.add_subparsers(dest="snapshot_command")

    snap_list_p = snap_sub.add_parser("list", help="List available snapshots")
    snap_list_p.set_defaults(func=cmd_snapshot_list)

    snap_delete_p = snap_sub.add_parser("delete", help="Delete a snapshot")
    snap_delete_p.add_argument("name", help="Snapshot name")
    snap_delete_p.set_defaults(func=cmd_snapshot_delete)

    # ── diff (agent comparison) ──
    diff_p = sub.add_parser("diff", help="Compare two agent sandbox sessions")
    diff_p.add_argument("session_a", help="First session ID or JSON path")
    diff_p.add_argument("session_b", help="Second session ID or JSON path")
    diff_p.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    diff_p.set_defaults(func=cmd_diff)

    # ── compare (agent quality matrix) ──
    compare_p = sub.add_parser(
        "compare", help="Score and rank recorded sessions (which agent/model did best)"
    )
    compare_p.add_argument("sessions", nargs="+", help="Session IDs or JSON paths to compare")
    compare_p.add_argument(
        "--label",
        action="append",
        metavar="NAME",
        help="Display name for a session, in order (repeatable, must match number of sessions)",
    )
    compare_p.add_argument(
        "--format", choices=["text", "json"], default="text", help="Output format (default: text)"
    )
    compare_p.add_argument("--html", metavar="PATH", help="Also write an HTML report to PATH")
    compare_p.set_defaults(func=cmd_compare)

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

    # Handle nested subcommands without a sub-subcommand
    if args.command == "engine" and not getattr(args, "engine_command", None):
        engine_p.print_help()
        return 0
    if args.command == "sandbox" and not getattr(args, "sandbox_command", None):
        sandbox_p.print_help()
        return 0
    if args.command == "snapshot" and not getattr(args, "snapshot_command", None):
        snap_p.print_help()
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
