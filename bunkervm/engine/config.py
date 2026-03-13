"""
BunkerVM Engine Config — Engine-specific configuration.

Separate from bunkervm/config.py (which is VM config). This handles:
  - Engine listen port (default: 9551)
  - Max concurrent sandboxes
  - PID file and state directory locations
  - Default sandbox resource limits
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger("bunkervm.engine.config")

# ── Constants ──

DEFAULT_ENGINE_PORT = 9551
DEFAULT_ENGINE_HOST = "127.0.0.1"
DEFAULT_MAX_SANDBOXES = 10
DEFAULT_SANDBOX_CPUS = 1
DEFAULT_SANDBOX_MEMORY = 512  # MB

# Engine state directory
ENGINE_HOME = os.path.expanduser("~/.bunkervm/engine")
ENGINE_PID_FILE = os.path.join(ENGINE_HOME, "engine.pid")
ENGINE_STATE_FILE = os.path.join(ENGINE_HOME, "state.json")
ENGINE_LOG_FILE = os.path.expanduser("~/.bunkervm/logs/engine.log")


@dataclass
class EngineConfig:
    """Configuration for the BunkerVM engine daemon.

    These settings control the engine itself, not individual sandboxes.
    Sandbox-level settings (cpus, memory) are per-sandbox overrides
    passed to the create endpoint.
    """

    # Engine server
    host: str = DEFAULT_ENGINE_HOST
    port: int = DEFAULT_ENGINE_PORT

    # Sandbox limits
    max_sandboxes: int = DEFAULT_MAX_SANDBOXES
    default_cpus: int = DEFAULT_SANDBOX_CPUS
    default_memory: int = DEFAULT_SANDBOX_MEMORY
    default_network: bool = True

    # Paths
    home_dir: str = ENGINE_HOME
    pid_file: str = ENGINE_PID_FILE
    state_file: str = ENGINE_STATE_FILE
    log_file: str = ENGINE_LOG_FILE

    # Timeouts
    health_timeout: int = 60
    default_exec_timeout: int = 30

    def ensure_dirs(self) -> None:
        """Create engine directories if they don't exist."""
        os.makedirs(self.home_dir, exist_ok=True)
        log_dir = os.path.dirname(self.log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

    def write_pid(self, pid: int) -> None:
        """Write the engine PID file."""
        self.ensure_dirs()
        with open(self.pid_file, "w") as f:
            f.write(str(pid))

    def read_pid(self) -> int | None:
        """Read the engine PID file. Returns None if not found or stale."""
        if not os.path.exists(self.pid_file):
            return None
        try:
            with open(self.pid_file, "r") as f:
                pid = int(f.read().strip())
            # Check if process is actually running
            if pid_alive(pid):
                return pid
            # Stale PID file
            self.clear_pid()
            return None
        except (ValueError, OSError):
            return None

    def clear_pid(self) -> None:
        """Remove the PID file."""
        try:
            os.remove(self.pid_file)
        except FileNotFoundError:
            pass


def pid_alive(pid: int) -> bool:
    """Check if a process with the given PID is running.

    Uses os.kill(pid, 0) — sends no signal, just checks existence.
    """
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False
