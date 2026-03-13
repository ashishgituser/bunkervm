"""
BunkerVM Runtime — Simple code execution API.

Run arbitrary code inside a hardware-isolated Firecracker microVM
with a single function call. No framework needed.

Usage:
    from bunkervm import run_code

    result = run_code("print('Hello from BunkerVM!')")
    print(result)  # Hello from BunkerVM!

    # Run with custom timeout
    result = run_code('''
    import time
    for i in range(5):
        print(f"Step {i}")
        time.sleep(0.1)
    ''', timeout=30)

    # Keep VM alive for multiple runs
    with Sandbox() as sb:
        sb.run("x = 42")
        sb.run("print(x)")      # 42
        sb.run("print(x * 2)")  # 84
"""

from __future__ import annotations

import atexit
import logging
import sys
import time
from typing import Optional

logger = logging.getLogger("bunkervm.runtime")


def _print(msg: str, end: str = "\n") -> None:
    """Print to stderr (stdout may be captured by callers)."""
    print(msg, file=sys.stderr, end=end, flush=True)


def run_code(
    code: str,
    *,
    language: str = "python",
    timeout: int = 30,
    cpus: int = 1,
    memory: int = 512,
    network: bool = True,
    quiet: bool = False,
) -> str:
    """Run code inside a disposable BunkerVM sandbox.

    If a BunkerVM engine daemon is running (localhost:9551), the code
    executes through the engine. Otherwise, boots a Firecracker microVM
    directly (requires Linux with /dev/kvm).

    Args:
        code: Source code to execute.
        language: Language runtime ("python", "bash", "node"). Default: "python".
        timeout: Execution timeout in seconds. Default: 30.
        cpus: Number of vCPUs. Default: 1.
        memory: Memory in MB. Default: 512.
        network: Enable internet inside the VM. Default: True.
        quiet: Suppress progress messages. Default: False.

    Returns:
        stdout output from the code execution.

    Raises:
        RuntimeError: If VM fails to start or code execution fails.

    Example:
        >>> from bunkervm import run_code
        >>> run_code("print('Hello from BunkerVM!')")
        'Hello from BunkerVM!'
    """
    # Try engine first (fast path — no Firecracker setup needed)
    engine = _try_engine_discovery()
    if engine is not None:
        return _run_code_via_engine(
            engine, code, language=language, timeout=timeout,
            cpus=cpus, memory=memory, network=network, quiet=quiet,
        )

    # Fall back to direct Firecracker boot
    return _run_code_direct(
        code, language=language, timeout=timeout,
        cpus=cpus, memory=memory, network=network, quiet=quiet,
    )


def _try_engine_discovery():
    """Try to discover a running engine. Returns EngineClient or None."""
    try:
        from .engine.discovery import discover_engine
        return discover_engine()
    except Exception:
        return None


def _run_code_via_engine(
    engine,
    code: str,
    *,
    language: str,
    timeout: int,
    cpus: int,
    memory: int,
    network: bool,
    quiet: bool,
) -> str:
    """Execute code through the engine daemon (no direct Firecracker)."""
    if not quiet:
        _print("Running via BunkerVM engine...")

    # Create a disposable sandbox
    sb_info = engine.create_sandbox(cpus=cpus, memory=memory, network=network)
    sandbox_id = sb_info["id"]

    try:
        if not quiet:
            _print("Running code inside sandbox...")

        # Build the execution command
        if language == "python":
            engine.write_file(sandbox_id, "/tmp/_run.py", code)
            result = engine.exec(sandbox_id, "python3 /tmp/_run.py", timeout=timeout)
        elif language == "bash":
            engine.write_file(sandbox_id, "/tmp/_run.sh", code)
            result = engine.exec(sandbox_id, "bash /tmp/_run.sh", timeout=timeout)
        elif language == "node":
            engine.write_file(sandbox_id, "/tmp/_run.js", code)
            result = engine.exec(sandbox_id, "node /tmp/_run.js", timeout=timeout)
        else:
            raise ValueError(f"Unsupported language: {language}")

        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        exit_code = result.get("exit_code", -1)

        if exit_code != 0:
            error_msg = stderr.strip() or f"Code exited with status {exit_code}"
            raise RuntimeError(f"Execution failed:\n{error_msg}")

        return stdout.rstrip("\n")

    finally:
        # Always destroy the disposable sandbox
        if not quiet:
            _print("Destroying sandbox...")
        try:
            engine.destroy_sandbox(sandbox_id)
        except Exception:
            pass
        if not quiet:
            _print("Done.")


def _run_code_direct(
    code: str,
    *,
    language: str,
    timeout: int,
    cpus: int,
    memory: int,
    network: bool,
    quiet: bool,
) -> str:
    """Execute code by directly booting a Firecracker VM (fallback path)."""
    from .config import load_config
    from .bootstrap import ensure_ready
    from .vm_manager import VMManager
    from .sandbox_client import SandboxClient

    if not quiet:
        _print("Starting BunkerVM...")

    # Load config and override resources
    config = load_config()
    config.vcpu_count = cpus
    config.mem_size_mib = memory

    # Ensure bundle is ready (downloads on first run)
    bundle = ensure_ready()
    config.firecracker_bin = bundle.firecracker
    config.kernel_path = bundle.kernel
    config.rootfs_path = bundle.rootfs

    # Boot VM
    if not quiet:
        _print("Launching Firecracker microVM...")

    vm = VMManager(config, network=network)
    try:
        vm.start()
    except Exception as e:
        raise RuntimeError(f"Failed to start VM: {e}") from e

    try:
        # Connect
        client = SandboxClient(
            vsock_uds=config.vsock_uds_path,
            vsock_port=config.vm_port,
        )
        if not client.wait_for_health(timeout=config.health_timeout):
            raise RuntimeError("VM started but sandbox agent is not responding")

        if not quiet:
            _print("Running code inside sandbox...")

        # Build the execution command
        if language == "python":
            # Write code to a temp file and execute
            client.write_file("/tmp/_run.py", code)
            result = client.exec(f"python3 /tmp/_run.py", timeout=timeout)
        elif language == "bash":
            client.write_file("/tmp/_run.sh", code)
            result = client.exec(f"bash /tmp/_run.sh", timeout=timeout)
        elif language == "node":
            client.write_file("/tmp/_run.js", code)
            result = client.exec(f"node /tmp/_run.js", timeout=timeout)
        else:
            raise ValueError(f"Unsupported language: {language}")

        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        exit_code = result.get("exit_code", -1)

        if exit_code != 0:
            error_msg = stderr.strip() or f"Code exited with status {exit_code}"
            raise RuntimeError(f"Execution failed:\n{error_msg}")

        return stdout.rstrip("\n")

    finally:
        # Always destroy VM
        if not quiet:
            _print("Destroying sandbox...")
        vm.stop()
        if not quiet:
            _print("Done.")


class Sandbox:
    """A reusable BunkerVM sandbox context manager.

    If a BunkerVM engine daemon is running, the sandbox is created through
    the engine (no direct Firecracker access needed). Otherwise, boots a
    VM directly (requires Linux with /dev/kvm).

    Usage:
        with Sandbox() as sb:
            sb.run("x = 42")
            result = sb.run("print(x)")
            print(result)  # 42

        # Or without context manager:
        sb = Sandbox()
        sb.start()
        sb.run("print('hello')")
        sb.stop()

        # Explicitly use engine (skip auto-discovery):
        sb = Sandbox(engine_url="http://localhost:9551")
    """

    def __init__(
        self,
        cpus: int = 1,
        memory: int = 512,
        network: bool = True,
        timeout: int = 30,
        quiet: bool = False,
        engine_url: Optional[str] = None,
    ):
        self._cpus = cpus
        self._memory = memory
        self._network = network
        self._timeout = timeout
        self._quiet = quiet
        self._engine_url = engine_url  # explicit engine override
        # Direct mode state
        self._vm: Optional[object] = None
        self._client: Optional[object] = None
        # Engine mode state
        self._engine: Optional[object] = None
        self._engine_sandbox_id: Optional[str] = None

    def start(self) -> "Sandbox":
        """Boot the sandbox VM.

        Tries engine daemon first, then falls back to direct Firecracker.
        """
        if self._client is not None:
            return self

        # Try engine mode first
        engine = self._resolve_engine()
        if engine is not None:
            return self._start_via_engine(engine)

        # Fall back to direct Firecracker boot
        return self._start_direct()

    def _install_runner(self) -> None:
        """Install a persistent-namespace runner script inside the VM.

        This script uses exec() with a pickled namespace so that
        variables defined in one run() call survive into the next.
        """
        runner = (
            "import sys, os, pickle, io, traceback\n"
            "NS_FILE   = '/tmp/_ns.pkl'\n"
            "CODE_FILE = '/tmp/_code.py'\n"
            "\n"
            "ns = {}\n"
            "if os.path.exists(NS_FILE):\n"
            "    with open(NS_FILE, 'rb') as f:\n"
            "        ns = pickle.load(f)\n"
            "\n"
            "with open(CODE_FILE) as f:\n"
            "    code = f.read()\n"
            "\n"
            "old_stdout = sys.stdout\n"
            "sys.stdout = buf = io.StringIO()\n"
            "failed = False\n"
            "try:\n"
            "    exec(compile(code, '<sandbox>', 'exec'), ns)\n"
            "except Exception:\n"
            "    sys.stdout = old_stdout\n"
            "    traceback.print_exc()\n"
            "    failed = True\n"
            "finally:\n"
            "    sys.stdout = old_stdout\n"
            "\n"
            "# Save namespace (only picklable items)\n"
            "safe = {}\n"
            "for k, v in ns.items():\n"
            "    if k.startswith('__'):\n"
            "        continue\n"
            "    try:\n"
            "        pickle.dumps(v)\n"
            "        safe[k] = v\n"
            "    except Exception:\n"
            "        pass\n"
            "with open(NS_FILE, 'wb') as f:\n"
            "    pickle.dump(safe, f)\n"
            "\n"
            "output = buf.getvalue()\n"
            "if output:\n"
            "    print(output, end='')\n"
            "if failed:\n"
            "    sys.exit(1)\n"
        )
        # self._client handles routing: SandboxClient for direct mode,
        # EngineBackedClient for engine mode — no need to branch here.
        self._client.write_file("/tmp/_runner.py", runner)

    # ── Engine discovery and start helpers ──

    def _resolve_engine(self):
        """Try to get an EngineClient. Returns client or None."""
        if self._engine_url:
            from .engine.client import EngineClient
            from .engine.discovery import parse_engine_url
            host, port = parse_engine_url(self._engine_url)
            return EngineClient(host=host, port=port)

        # Auto-discovery
        return _try_engine_discovery()

    def _start_via_engine(self, engine) -> "Sandbox":
        """Start sandbox through the engine daemon."""
        from .engine.client import EngineBackedClient

        if not self._quiet:
            _print("Starting sandbox via BunkerVM engine...")

        sb_info = engine.create_sandbox(
            cpus=self._cpus,
            memory=self._memory,
            network=self._network,
        )
        self._engine = engine
        self._engine_sandbox_id = sb_info["id"]

        # EngineBackedClient wraps engine API calls with the same
        # interface as SandboxClient — existing code works unchanged.
        self._client = EngineBackedClient(
            engine=engine,
            sandbox_id=self._engine_sandbox_id,
        )

        # Install the persistent namespace runner
        self._install_runner()

        if not self._quiet:
            _print("Sandbox ready (via engine).")
        return self

    def _start_direct(self) -> "Sandbox":
        """Start sandbox by directly booting a Firecracker VM."""
        from .config import load_config
        from .bootstrap import ensure_ready
        from .vm_manager import VMManager
        from .sandbox_client import SandboxClient

        if not self._quiet:
            _print("Starting BunkerVM sandbox...")

        config = load_config()
        config.vcpu_count = self._cpus
        config.mem_size_mib = self._memory

        bundle = ensure_ready()
        config.firecracker_bin = bundle.firecracker
        config.kernel_path = bundle.kernel
        config.rootfs_path = bundle.rootfs

        self._vm = VMManager(config, network=self._network)
        self._vm.start()

        self._client = SandboxClient(
            vsock_uds=config.vsock_uds_path,
            vsock_port=config.vm_port,
        )
        if not self._client.wait_for_health(timeout=config.health_timeout):
            self._vm.stop()
            self._vm = None
            raise RuntimeError("Sandbox agent not responding")

        # Install the persistent Python namespace runner
        self._install_runner()

        if not self._quiet:
            _print("Sandbox ready.")
        return self

    def stop(self) -> None:
        """Destroy the sandbox VM."""
        if self._engine is not None and self._engine_sandbox_id:
            # Engine mode: destroy via engine API
            if not self._quiet:
                _print("Destroying sandbox...")
            try:
                self._engine.destroy_sandbox(self._engine_sandbox_id)
            except Exception:
                pass
            self._engine = None
            self._engine_sandbox_id = None
            self._client = None
            if not self._quiet:
                _print("Done.")
        elif self._vm is not None:
            # Direct mode: stop the VM
            if not self._quiet:
                _print("Destroying sandbox...")
            self._vm.stop()
            self._vm = None
            self._client = None
            if not self._quiet:
                _print("Done.")

    def run(
        self,
        code: str,
        language: str = "python",
        timeout: Optional[int] = None,
    ) -> str:
        """Execute code inside the running sandbox.

        For Python, state (variables, imports) persists between calls:
            sb.run("x = 42")
            sb.run("print(x)")  # 42

        Args:
            code: Source code to execute.
            language: "python", "bash", or "node".
            timeout: Override default timeout.

        Returns:
            stdout output.
        """
        if self._client is None:
            raise RuntimeError("Sandbox not started. Call .start() or use 'with Sandbox()'")

        t = timeout or self._timeout

        if language == "python":
            # Use the persistent namespace runner
            self._client.write_file("/tmp/_code.py", code)
            result = self._client.exec("python3 /tmp/_runner.py", timeout=t)
        elif language == "bash":
            self._client.write_file("/tmp/_run.sh", code)
            result = self._client.exec("bash /tmp/_run.sh", timeout=t)
        elif language == "node":
            self._client.write_file("/tmp/_run.js", code)
            result = self._client.exec("node /tmp/_run.js", timeout=t)
        else:
            raise ValueError(f"Unsupported language: {language}")

        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        exit_code = result.get("exit_code", -1)

        if exit_code != 0:
            error_msg = stderr.strip() or f"Code exited with status {exit_code}"
            raise RuntimeError(f"Execution failed:\n{error_msg}")

        return stdout.rstrip("\n")

    def exec(self, command: str, timeout: Optional[int] = None) -> str:
        """Execute a shell command directly.

        Args:
            command: Shell command to run.
            timeout: Override default timeout.

        Returns:
            stdout output.
        """
        if self._client is None:
            raise RuntimeError("Sandbox not started. Call .start() or use 'with Sandbox()'")

        result = self._client.exec(command, timeout=timeout or self._timeout)
        return result.get("stdout", "")

    def upload(self, local_path: str, remote_path: str) -> None:
        """Upload a file into the sandbox."""
        if self._client is None:
            raise RuntimeError("Sandbox not started")
        self._client.upload_file(local_path, remote_path)

    def download(self, remote_path: str) -> bytes:
        """Download a file from the sandbox."""
        if self._client is None:
            raise RuntimeError("Sandbox not started")
        return self._client.download_file(remote_path)

    @property
    def client(self):
        """Direct access to the SandboxClient for advanced usage."""
        return self._client

    def __enter__(self) -> "Sandbox":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    def __del__(self) -> None:
        try:
            self.stop()
        except Exception:
            pass
