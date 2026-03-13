"""
BunkerVM Engine Discovery — Auto-detect a running engine daemon.

The discovery logic is used by Sandbox, run_code(), and all framework
integrations to transparently route through the engine when available,
falling back to direct Firecracker boot when not.

Discovery order:
  1. Check BUNKERVM_ENGINE_URL env var (explicit override)
  2. Read PID file at ~/.bunkervm/engine/engine.pid
     - If PID is alive, probe the API endpoint
  3. Probe default localhost:9551 (in case started externally)
  4. Return None → caller should fall back to direct boot

This module is intentionally cheap to import and call — no heavy deps.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .client import EngineClient

from .config import DEFAULT_ENGINE_PORT, EngineConfig, pid_alive

logger = logging.getLogger("bunkervm.engine.discovery")

# Env var to explicitly point to a running engine
_ENGINE_URL_ENV = "BUNKERVM_ENGINE_URL"

# How long to wait for the probe (seconds)
_PROBE_TIMEOUT = 2


def discover_engine() -> Optional["EngineClient"]:
    """Try to find and connect to a running BunkerVM engine.

    Returns an EngineClient if an engine is reachable, None otherwise.
    This function is designed to be fast and side-effect-free.
    """
    host, port = _resolve_engine_address()
    if host is None:
        return None

    # Try to actually reach the engine
    if _probe_engine(host, port):
        from .client import EngineClient
        logger.info("Engine discovered at %s:%d", host, port)
        return EngineClient(host=host, port=port)

    return None


def is_engine_running() -> bool:
    """Quick check: is there a reachable engine daemon?

    Faster than discover_engine() when you just need a boolean.
    """
    host, port = _resolve_engine_address()
    if host is None:
        return False
    return _probe_engine(host, port)


def engine_url() -> Optional[str]:
    """Return the engine base URL if running, None otherwise."""
    host, port = _resolve_engine_address()
    if host is None:
        return None
    if _probe_engine(host, port):
        return f"http://{host}:{port}"
    return None


def _resolve_engine_address() -> Tuple[Optional[str], int]:
    """Determine the engine address to probe.

    Returns (host, port) or (None, 0) if no candidate found.
    """
    # 1. Explicit env var: BUNKERVM_ENGINE_URL=http://host:port
    env_url = os.environ.get(_ENGINE_URL_ENV)
    if env_url:
        return parse_engine_url(env_url)

    # 2. PID file check — if PID is alive, engine is probably there
    #    (only meaningful on Linux / WSL where the PID lives)
    from .platform import is_windows
    if not is_windows():
        config = EngineConfig()
        pid = config.read_pid()
        if pid is not None and pid_alive(pid):
            return config.host, config.port

    # 3. Fallback: just try the default address (engine may have been
    #    started externally, e.g. by BunkerDesktop, systemd, or inside
    #    WSL2 on Windows where the port auto-forwards to localhost)
    return "127.0.0.1", DEFAULT_ENGINE_PORT


def _probe_engine(host: str, port: int) -> bool:
    """Probe the engine API at /engine/status. Returns True if reachable."""
    url = f"http://{host}:{port}/engine/status"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=_PROBE_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("status") in ("running", "ok")
    except (urllib.error.URLError, OSError, json.JSONDecodeError, KeyError):
        return False


def parse_engine_url(url: str) -> Tuple[str, int]:
    """Parse an engine URL like http://host:port into (host, port).

    Shared utility used by discovery, Sandbox, and BunkerVMToolsBase
    to avoid duplicating URL parsing logic.
    """
    url = url.rstrip("/")
    if url.startswith("http://"):
        url = url[7:]
    elif url.startswith("https://"):
        url = url[8:]

    if ":" in url:
        parts = url.rsplit(":", 1)
        try:
            return parts[0], int(parts[1])
        except (ValueError, IndexError):
            pass

    return url or "127.0.0.1", DEFAULT_ENGINE_PORT
