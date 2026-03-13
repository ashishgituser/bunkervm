"""
BunkerVM Engine Daemon — Long-running process that manages sandboxes.

The daemon is the ONLY component that touches Firecracker. It:
  1. Boots a VMPool (from existing multi_vm.py)
  2. Exposes a REST API on localhost:9551 (from api.py)
  3. Manages sandbox lifecycle (create/destroy/reset)
  4. Writes PID file for discovery by CLI/SDK

Usage:
    # As a foreground process (for development / CLI):
    daemon = EngineDaemon(config)
    daemon.start()     # blocks

    # As a background process (for BunkerDesktop):
    daemon.start_background()
    ...
    daemon.stop()
"""

from __future__ import annotations

import collections
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from http.server import HTTPServer
from socketserver import ThreadingMixIn
from typing import Dict, List, Optional

from .api import EngineAPIHandler
from .config import EngineConfig
from .models import SandboxInfo, _new_id

logger = logging.getLogger("bunkervm.engine.daemon")


class _RingBufferHandler(logging.Handler):
    """In-memory ring buffer that captures log records for the /engine/logs API."""

    def __init__(self, capacity: int = 500):
        super().__init__()
        self._buffer: collections.deque = collections.deque(maxlen=capacity)
        self._lock = threading.Lock()
        self._counter = 0  # monotonic sequence id

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = {
                "seq": self._counter,
                "ts": record.created,
                "level": record.levelname,
                "logger": record.name,
                "message": self.format(record),
            }
            with self._lock:
                self._counter += 1
                entry["seq"] = self._counter
                self._buffer.append(entry)
        except Exception:
            pass

    def get_logs(self, after_seq: int = 0, limit: int = 200) -> List[dict]:
        """Return log entries with seq > after_seq, up to limit."""
        with self._lock:
            entries = [e for e in self._buffer if e["seq"] > after_seq]
        return entries[-limit:]


class _ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """HTTP server that handles each request in a new thread."""
    daemon_threads = True
    allow_reuse_address = True


class EngineDaemon:
    """The BunkerVM engine daemon.

    Manages Firecracker sandboxes via VMPool and exposes a REST API.
    This is the single process that owns all VM resources.

    Args:
        config: Engine configuration.
    """

    def __init__(self, config: Optional[EngineConfig] = None):
        self.config = config or EngineConfig()
        self._pool = None  # VMPool — lazily created on first sandbox
        self._vm_config = None  # BunkerVMConfig — loaded once
        self._server: Optional[_ThreadedHTTPServer] = None
        self._sandboxes: Dict[str, _SandboxEntry] = {}
        self._lock = threading.Lock()
        self._running = False
        self.start_time: float = 0.0

        # In-memory log buffer for dashboard streaming
        self.log_handler = _RingBufferHandler(capacity=500)
        self.log_handler.setLevel(logging.DEBUG)
        self.log_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s",
                              datefmt="%H:%M:%S")
        )
        # Attach to root logger to capture all bunkervm.* logs
        root_logger = logging.getLogger("bunkervm")
        root_logger.setLevel(logging.DEBUG)
        root_logger.addHandler(self.log_handler)

    # ── Properties ──

    @property
    def sandbox_count(self) -> int:
        return len(self._sandboxes)

    # ── Lifecycle ──

    def start(self) -> None:
        """Start the engine daemon (blocks until stopped).

        Boots the HTTP API server, writes PID file, and waits for requests.

        Raises:
            RuntimeError: If called on Windows (use :class:`WSLBridge` instead).
        """
        from .platform import is_windows
        if is_windows():
            raise RuntimeError(
                "The engine daemon cannot run on Windows directly.  "
                "Use bunkervm.engine.wsl_bridge.WSLBridge to start it "
                "inside WSL2, or run 'bunkervm engine start' from the CLI."
            )

        self.config.ensure_dirs()
        self.start_time = time.time()
        self._running = True

        # Auto-fix /dev/kvm permissions (WSL2 resets these on every reboot)
        self._fix_kvm_permissions()

        # Write PID file
        self.config.write_pid(os.getpid())

        # Set up signal handlers for graceful shutdown (only works in main thread)
        try:
            signal.signal(signal.SIGTERM, self._signal_handler)
            signal.signal(signal.SIGINT, self._signal_handler)
        except ValueError:
            # Not in main thread — skip signal handlers (e.g. testing)
            logger.debug("Skipping signal handlers (not main thread)")

        # Initialize VM infrastructure
        self._init_vm_pool()

        # Start HTTP server
        self._server = _ThreadedHTTPServer(
            (self.config.host, self.config.port),
            EngineAPIHandler,
        )
        self._server.daemon = self  # type: ignore[attr-defined]

        _print(f"BunkerVM engine started (PID {os.getpid()})")
        _print(f"  API: http://{self.config.host}:{self.config.port}")
        _print(f"  Max sandboxes: {self.config.max_sandboxes}")
        logger.info(
            "Engine started on %s:%d (PID %d)",
            self.config.host, self.config.port, os.getpid(),
        )

        try:
            self._server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            self._cleanup()

    @staticmethod
    def _fix_kvm_permissions() -> None:
        """Ensure /dev/kvm is accessible.

        In WSL2, /dev/kvm permissions reset to root-only on every reboot.
        This auto-fixes it so users don't have to manually run chmod.
        """
        kvm_path = "/dev/kvm"
        if not os.path.exists(kvm_path):
            logger.warning("/dev/kvm not found - KVM may not be enabled")
            return
        if os.access(kvm_path, os.R_OK | os.W_OK):
            return  # Already accessible

        logger.info("/dev/kvm not accessible, attempting to fix permissions...")
        try:
            subprocess.run(
                ["sudo", "-n", "chmod", "666", kvm_path],
                capture_output=True, timeout=5
            )
            if os.access(kvm_path, os.R_OK | os.W_OK):
                logger.info("/dev/kvm permissions fixed successfully")
                _print("  /dev/kvm permissions fixed automatically")
            else:
                logger.warning(
                    "/dev/kvm still not accessible after chmod. "
                    "Run manually: sudo chmod 666 /dev/kvm"
                )
        except Exception as e:
            logger.warning("Could not fix /dev/kvm permissions: %s", e)

    def stop(self) -> None:
        """Stop the engine daemon gracefully."""
        if not self._running:
            return

        logger.info("Engine stopping...")
        _print("Engine stopping...")
        self._running = False

        # Destroy all sandboxes
        self._destroy_all_sandboxes()

        # Shut down HTTP server
        if self._server:
            self._server.shutdown()

    def _signal_handler(self, signum, frame):
        """Handle SIGTERM/SIGINT for graceful shutdown."""
        logger.info("Received signal %d, shutting down...", signum)
        self.stop()

    def _cleanup(self):
        """Final cleanup: stop VMs, remove PID file."""
        self._destroy_all_sandboxes()
        self.config.clear_pid()
        logger.info("Engine stopped")
        _print("Engine stopped")

    # ── VM Pool Initialization ──

    def _init_vm_pool(self):
        """Initialize the VMPool and base VM config.

        Uses existing bunkervm config loading + bootstrap to ensure
        Firecracker bundle is ready.
        """
        from bunkervm.bootstrap import ensure_ready
        from bunkervm.config import load_config
        from bunkervm.multi_vm import VMPool

        # Load VM config (picks up bunkervm.toml, env vars, defaults)
        self._vm_config = load_config()

        # Ensure Firecracker bundle is downloaded
        bundle = ensure_ready()
        self._vm_config.firecracker_bin = bundle.firecracker
        self._vm_config.kernel_path = bundle.kernel
        self._vm_config.rootfs_path = bundle.rootfs

        # Create the pool
        self._pool = VMPool(
            base_config=self._vm_config,
            network=self.config.default_network,
            max_vms=self.config.max_sandboxes,
        )

        logger.info("VM pool initialized (max %d sandboxes)", self.config.max_sandboxes)

    # ── Sandbox Management ──

    def create_sandbox(
        self,
        name: Optional[str] = None,
        cpus: Optional[int] = None,
        memory: Optional[int] = None,
        network: Optional[bool] = None,
    ) -> SandboxInfo:
        """Create a new sandbox.

        Args:
            name: Optional human-readable name. Auto-generated if not provided.
            cpus: vCPU count (default: from engine config).
            memory: Memory in MB (default: from engine config).
            network: Enable networking (default: from engine config).

        Returns:
            SandboxInfo with the new sandbox details.

        Raises:
            ValueError: If name already exists or pool is full.
        """
        sandbox_id = _new_id()

        # Generate name if not provided
        if not name:
            name = f"sandbox-{sandbox_id}"

        # Check for name collision
        with self._lock:
            for entry in self._sandboxes.values():
                if entry.info.name == name:
                    raise ValueError(f"Sandbox with name '{name}' already exists")

        # Use defaults from engine config if not specified
        use_cpus = cpus or self.config.default_cpus
        use_memory = memory or self.config.default_memory

        # Pool name is the sandbox ID (unique key for VMPool)
        pool_name = f"engine-{sandbox_id}"

        logger.info(
            "Creating sandbox %s (%s): cpus=%d, memory=%dMB",
            sandbox_id, name, use_cpus, use_memory,
        )

        # Start the VM via VMPool
        client = self._pool.start(
            name=pool_name,
            cpus=use_cpus,
            memory=use_memory,
            network=network,
        )

        # Build sandbox info
        pool_status = self._pool.status(pool_name)
        info = SandboxInfo(
            id=sandbox_id,
            name=name,
            status="running",
            created_at=time.time(),
            cpus=use_cpus,
            memory_mb=use_memory,
            network=network if network is not None else self.config.default_network,
            pid=pool_status.get("pid"),
            vsock=pool_status.get("vsock"),
        )

        entry = _SandboxEntry(
            info=info,
            pool_name=pool_name,
        )

        with self._lock:
            self._sandboxes[sandbox_id] = entry

        return info

    def destroy_sandbox(self, sandbox_id: str) -> bool:
        """Destroy a sandbox by ID. Returns True if found and destroyed."""
        # Also try to find by name
        entry = self._find_sandbox(sandbox_id)
        if entry is None:
            return False

        with self._lock:
            self._sandboxes.pop(entry.info.id, None)

        try:
            self._pool.stop(entry.pool_name)
        except Exception as e:
            logger.error("Error destroying sandbox %s: %s", sandbox_id, e)

        return True

    def reset_sandbox(self, sandbox_id: str) -> Optional[SandboxInfo]:
        """Reset a sandbox (destroy and recreate with same config)."""
        entry = self._find_sandbox(sandbox_id)
        if entry is None:
            return None

        old_info = entry.info

        # Destroy
        self.destroy_sandbox(old_info.id)

        # Recreate with same settings
        return self.create_sandbox(
            name=old_info.name,
            cpus=old_info.cpus,
            memory=old_info.memory_mb,
            network=old_info.network,
        )

    def get_sandbox(self, sandbox_id: str) -> Optional[SandboxInfo]:
        """Get sandbox info by ID or name."""
        entry = self._find_sandbox(sandbox_id)
        if entry is None:
            return None
        return entry.info

    def get_client(self, sandbox_id: str):
        """Get the SandboxClient for a sandbox (by ID or name).

        Returns None if not found.
        """
        entry = self._find_sandbox(sandbox_id)
        if entry is None:
            return None

        try:
            return self._pool.client(entry.pool_name)
        except KeyError:
            return None

    def list_sandboxes(self) -> list[SandboxInfo]:
        """List all running sandboxes."""
        with self._lock:
            return [entry.info for entry in self._sandboxes.values()]

    def _find_sandbox(self, id_or_name: str) -> Optional["_SandboxEntry"]:
        """Find a sandbox by ID or name."""
        with self._lock:
            # Try by ID first
            if id_or_name in self._sandboxes:
                return self._sandboxes[id_or_name]
            # Try by name
            for entry in self._sandboxes.values():
                if entry.info.name == id_or_name:
                    return entry
        return None

    def _destroy_all_sandboxes(self):
        """Destroy all running sandboxes."""
        with self._lock:
            ids = list(self._sandboxes.keys())

        for sandbox_id in ids:
            try:
                self.destroy_sandbox(sandbox_id)
            except Exception as e:
                logger.error("Error destroying sandbox %s during shutdown: %s", sandbox_id, e)

        # Also stop the pool (belt and suspenders)
        if self._pool:
            try:
                self._pool.stop_all()
            except Exception as e:
                logger.error("Error stopping VM pool: %s", e)


class _SandboxEntry:
    """Internal tracking entry for a sandbox."""

    __slots__ = ("info", "pool_name")

    def __init__(self, info: SandboxInfo, pool_name: str):
        self.info = info
        self.pool_name = pool_name


def _print(msg: str, end: str = "\n") -> None:
    """Print to stderr (stdout may be captured by MCP stdio transport)."""
    print(msg, file=sys.stderr, end=end, flush=True)
