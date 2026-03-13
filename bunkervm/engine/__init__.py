"""
BunkerVM Engine — Background daemon that manages Firecracker sandboxes.

The engine is the single component that touches Firecracker. Everything else
(CLI, Python SDK, framework integrations, desktop GUI) is a thin client
that talks to the engine via its REST API on localhost:9551.

Architecture:
    BunkerDesktop / CLI / SDK
           │
           ▼  HTTP (localhost:9551)
    ┌──────────────┐
    │ Engine Daemon │  ← This package
    │  (api.py)    │
    └──────┬───────┘
           │  wraps
    ┌──────▼───────┐
    │   VMPool     │  ← bunkervm/multi_vm.py (existing)
    │ vm_manager   │  ← bunkervm/vm_manager.py (existing)
    └──────────────┘

Usage:
    # Start the engine daemon
    bunkervm engine start

    # Check engine status
    bunkervm engine status

    # Stop the engine daemon
    bunkervm engine stop

    # Programmatic access
    from bunkervm.engine import EngineClient
    engine = EngineClient()
    sandbox_id = engine.create_sandbox(name="my-sandbox")
    result = engine.exec(sandbox_id, "echo hello")
    engine.destroy_sandbox(sandbox_id)
"""

from .config import EngineConfig, DEFAULT_ENGINE_PORT
from .client import EngineClient, EngineBackedClient, EngineAPIError, EngineConnectionError
from .daemon import EngineDaemon
from .discovery import discover_engine, is_engine_running, parse_engine_url
from .platform import PlatformInfo, detect_platform, is_windows, is_wsl, has_kvm

__all__ = [
    "EngineConfig",
    "EngineClient",
    "EngineBackedClient",
    "EngineAPIError",
    "EngineConnectionError",
    "EngineDaemon",
    "DEFAULT_ENGINE_PORT",
    "discover_engine",
    "is_engine_running",
    "parse_engine_url",
    "PlatformInfo",
    "detect_platform",
    "is_windows",
    "is_wsl",
    "has_kvm",
]
