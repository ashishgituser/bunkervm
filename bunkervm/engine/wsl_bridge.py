"""
BunkerVM WSL2 Bridge — Manage the engine daemon inside WSL2 from Windows.

On Windows the host cannot run Firecracker directly.  Instead we:

  1. Validate that WSL 2 is installed with a suitable distro.
  2. Ensure ``bunkervm`` is installed inside that distro (in a venv at
     ``~/.bunkervm/venv``).
  3. Start / stop / query the engine daemon inside WSL2.
  4. Port forwarding is automatic — WSL2 listens on „localhost:9551" and
     Windows can reach it natively.

All subprocess calls go through :func:`wsl_run` so every invocation is
visible in logs and easy to test in isolation.

Usage from CLI::

    from bunkervm.engine.wsl_bridge import WSLBridge
    bridge = WSLBridge()                   # auto-detects distro
    bridge.ensure_installed()              # idempotent install
    bridge.start_engine(port=9551)         # starts daemon in WSL2
    bridge.stop_engine(port=9551)
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

from .config import DEFAULT_ENGINE_PORT

logger = logging.getLogger("bunkervm.engine.wsl_bridge")

# Where we install bunkervm inside WSL
_WSL_VENV_DIR = "~/.bunkervm/venv"
_WSL_LOG_FILE = "~/.bunkervm/logs/engine.log"


# ── Low-level WSL helpers ───────────────────────────────────────────


def wsl_run(
    distro: str,
    *args: str,
    timeout: int = 120,
    capture: bool = True,
) -> subprocess.CompletedProcess:
    """Run a command inside a WSL distro and return the result.

    Args:
        distro: WSL distribution name (e.g. ``"Ubuntu"``).
        *args: Command tokens to run.
        timeout: Seconds before we give up.
        capture: Whether to capture stdout/stderr (set ``False`` for
                 interactive commands that need the terminal).

    Returns:
        ``subprocess.CompletedProcess`` — always text mode.
    """
    cmd = ["wsl", "-d", distro, "--", *args]
    logger.debug("wsl_run: %s", " ".join(cmd))
    return subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        timeout=timeout,
    )


def wsl_bash(distro: str, script: str, timeout: int = 120) -> subprocess.CompletedProcess:
    """Run a bash one-liner inside WSL.

    Equivalent to ``wsl -d <distro> -- bash -lc '<script>'``.
    """
    return wsl_run(distro, "bash", "-lc", script, timeout=timeout)


def _wsl_home(distro: str) -> str:
    """Return the home directory of the default WSL user."""
    result = wsl_bash(distro, "echo $HOME", timeout=10)
    if result.returncode != 0:
        raise RuntimeError(f"Cannot determine WSL home directory in {distro}")
    return result.stdout.strip()


# ── WSLBridge ───────────────────────────────────────────────────────


@dataclass
class WSLBridge:
    """Manages the BunkerVM engine daemon inside a WSL2 distro.

    Attributes:
        distro: WSL distribution to use.  Auto-detected if ``None``.
    """

    distro: Optional[str] = None
    _wsl_home: Optional[str] = field(default=None, repr=False)
    _bunkervm_bin: Optional[str] = field(default=None, repr=False)

    def __post_init__(self):
        if self.distro is None:
            from .platform import default_wsl_distro
            self.distro = default_wsl_distro()
            if self.distro is None:
                raise RuntimeError(
                    "No WSL2 distro found.  Install one with:  "
                    "wsl --install -d Ubuntu"
                )

    # ── High-level lifecycle ──────────────────────────────────────

    def check_ready(self) -> list[str]:
        """Verify WSL2 prerequisites.  Returns a list of problems (empty = OK)."""
        problems: list[str] = []

        # 1. WSL2 itself
        from .platform import wsl2_available
        if not wsl2_available():
            problems.append("WSL2 is not installed or no version-2 distro found")
            return problems  # nothing else to check

        # 2. Distro reachable
        try:
            r = wsl_bash(self.distro, "echo ok", timeout=15)  # type: ignore[arg-type]
            if r.returncode != 0 or r.stdout.strip() != "ok":
                problems.append(f"WSL distro '{self.distro}' is not responding")
                return problems
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            problems.append(f"Cannot reach WSL distro '{self.distro}': {exc}")
            return problems

        # 3. Python 3 available
        r = wsl_bash(self.distro, "python3 --version", timeout=10)  # type: ignore[arg-type]
        if r.returncode != 0:
            problems.append("python3 not found inside WSL — run: wsl sudo apt install python3 python3-venv")

        # 4. /dev/kvm
        r = wsl_bash(self.distro, "test -r /dev/kvm && test -w /dev/kvm && echo ok", timeout=10)  # type: ignore[arg-type]
        if r.stdout.strip() != "ok":
            problems.append("/dev/kvm not accessible — add nestedVirtualization=true to .wslconfig and restart WSL")

        return problems

    def ensure_installed(self) -> str:
        """Install BunkerVM inside WSL if not already present.

        Creates a venv at ``~/.bunkervm/venv`` inside the distro and
        ``pip install``s bunkervm.  Returns the path to the ``bunkervm``
        binary inside WSL.
        """
        if self._bunkervm_bin:
            return self._bunkervm_bin

        home = self._get_home()
        venv_dir = f"{home}/.bunkervm/venv"
        bunkervm_bin = f"{venv_dir}/bin/bunkervm"

        # Already installed?
        r = wsl_run(self.distro, "test", "-f", bunkervm_bin, timeout=10)  # type: ignore[arg-type]
        if r.returncode == 0:
            logger.info("BunkerVM already installed at %s", bunkervm_bin)
            self._bunkervm_bin = bunkervm_bin
            return bunkervm_bin

        # Create venv
        logger.info("Creating venv at %s in WSL (%s)", venv_dir, self.distro)
        r = wsl_run(self.distro, "python3", "-m", "venv", venv_dir, timeout=60)  # type: ignore[arg-type]
        if r.returncode != 0:
            raise RuntimeError(
                f"Failed to create venv: {r.stderr.strip()}\n"
                f"Try: wsl -d {self.distro} -- sudo apt install python3-venv"
            )

        # Install bunkervm
        pip_bin = f"{venv_dir}/bin/pip"
        logger.info("Installing bunkervm via pip in WSL")
        r = wsl_run(self.distro, pip_bin, "install", "bunkervm", timeout=120)  # type: ignore[arg-type]
        if r.returncode != 0:
            raise RuntimeError(f"pip install bunkervm failed: {r.stderr.strip()}")

        # Verify
        r = wsl_run(self.distro, "test", "-f", bunkervm_bin, timeout=10)  # type: ignore[arg-type]
        if r.returncode != 0:
            raise RuntimeError(
                f"Install succeeded but binary not found at {bunkervm_bin}"
            )

        logger.info("BunkerVM installed in WSL: %s", bunkervm_bin)
        self._bunkervm_bin = bunkervm_bin
        return bunkervm_bin

    # ── Engine start / stop ──────────────────────────────────────

    def start_engine(
        self,
        port: int = DEFAULT_ENGINE_PORT,
        max_sandboxes: int = 10,
        cpus: int = 1,
        memory: int = 512,
        foreground: bool = False,
    ) -> bool:
        """Start the engine daemon inside WSL2.

        By default the daemon runs in the background (nohup + disown) so
        the WSL session can close without killing it.  Pass
        ``foreground=True`` to block (useful for development).

        Returns ``True`` if the engine is running after this call.
        """
        bunkervm_bin = self.ensure_installed()

        # Check if already running (probe port — WSL2 auto-forwards)
        if self._probe(port):
            logger.info("Engine already running on port %d", port)
            return True

        cmd_parts = (
            f"{bunkervm_bin} engine start"
            f" --port {port}"
            f" --max-sandboxes {max_sandboxes}"
            f" --cpus {cpus}"
            f" --memory {memory}"
        )

        if foreground:
            # Block — let the user see output directly
            wsl_run(
                self.distro,  # type: ignore[arg-type]
                "bash", "-lc", cmd_parts,
                capture=False,
                timeout=0,  # no timeout for foreground
            )
            return True

        # Background: nohup + redirect output, disown
        home = self._get_home()
        log_file = f"{home}/.bunkervm/logs/engine.log"
        bg_script = (
            f"mkdir -p {home}/.bunkervm/logs && "
            f"nohup {cmd_parts} >> {log_file} 2>&1 &"
        )
        r = wsl_bash(self.distro, bg_script, timeout=15)  # type: ignore[arg-type]
        if r.returncode != 0:
            logger.error("Failed to launch engine in WSL: %s", r.stderr.strip())
            return False

        # Wait for it to become reachable
        for _ in range(10):
            time.sleep(1)
            if self._probe(port):
                logger.info("Engine started in WSL on port %d", port)
                return True

        logger.error("Engine did not become reachable within 10 seconds")
        return False

    def stop_engine(self, port: int = DEFAULT_ENGINE_PORT) -> bool:
        """Stop the engine daemon inside WSL2 via the REST API.

        We POST to ``/engine/stop`` directly — WSL2 port forwarding
        means ``localhost:<port>`` reaches the WSL2 process.

        Returns ``True`` if the engine was stopped (or wasn't running).
        """
        import json
        import urllib.error
        import urllib.request

        url = f"http://127.0.0.1:{port}/engine/stop"
        try:
            req = urllib.request.Request(url, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                json.loads(resp.read())
            logger.info("Engine stopped via API")
            return True
        except (urllib.error.URLError, OSError):
            # Not running — clean up stale PID file inside WSL
            if self._bunkervm_bin:
                wsl_bash(self.distro, f"rm -f ~/.bunkervm/engine/engine.pid", timeout=10)  # type: ignore[arg-type]
            return True

    def engine_status(self, port: int = DEFAULT_ENGINE_PORT) -> Optional[dict]:
        """Query engine status.  Returns the status dict or ``None``."""
        import json
        import urllib.error
        import urllib.request

        url = f"http://127.0.0.1:{port}/engine/status"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            return None

    # ── Helpers ──────────────────────────────────────────────────

    def _get_home(self) -> str:
        if self._wsl_home is None:
            self._wsl_home = _wsl_home(self.distro)  # type: ignore[arg-type]
        return self._wsl_home

    @staticmethod
    def _probe(port: int) -> bool:
        """Check if the engine is reachable on localhost:<port>."""
        import json
        import urllib.error
        import urllib.request

        url = f"http://127.0.0.1:{port}/engine/status"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("status") in ("running", "ok")
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            return False
