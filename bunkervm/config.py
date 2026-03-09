"""
BunkerVM Configuration — TOML-based configuration with sensible defaults.

Loads settings from (in order of precedence):
  1. CLI arguments (highest)
  2. Environment variables (BUNKERVM_*)
  3. bunkervm.toml config file
  4. Built-in defaults (lowest)

All paths are resolved relative to the project root (location of bunkervm.toml).
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("bunkervm.config")

# ── Defaults ──

_DEFAULTS = {
    # VM resources
    "vcpu_count": 2,
    "mem_size_mib": 2048,

    # VSOCK (default transport — zero config)
    "vsock_cid": 3,
    "vsock_uds_path": "/tmp/bunkervm-vsock.sock",
    "vm_port": 8080,    # Port inside VM (both vsock and TCP)

    # Paths (auto-provisioned into ~/.bunkervm/bundle/ on first run)
    "firecracker_bin": "~/.bunkervm/bundle/firecracker",
    "kernel_path": "~/.bunkervm/bundle/vmlinux",
    "rootfs_path": "~/.bunkervm/bundle/rootfs.ext4",
    "rootfs_work_path": "/tmp/bunkervm-sandbox-rootfs.ext4",
    "socket_path": "/tmp/bunkervm-fc.sock",

    # TAP networking (optional — only with --network flag)
    "vm_ip": "172.16.0.2",
    "host_ip": "172.16.0.1",
    "subnet_mask": "24",
    "tap_device": "tap0",
    "guest_mac": "AA:FC:00:00:00:01",

    # Audit & logging
    "audit_log_path": "~/.bunkervm/logs/audit.jsonl",

    # Timeouts
    "health_timeout": 60,
    "default_exec_timeout": 30,
    "max_exec_timeout": 300,

    # Safety
    "enforce_safety": True,

    # Server
    "transport": "stdio",
    "sse_port": 3000,
}


@dataclass
class BunkerVMConfig:
    """Validated BunkerVM configuration."""

    # VM resources
    vcpu_count: int = _DEFAULTS["vcpu_count"]
    mem_size_mib: int = _DEFAULTS["mem_size_mib"]

    # VSOCK (default — zero config)
    vsock_cid: int = _DEFAULTS["vsock_cid"]
    vsock_uds_path: str = _DEFAULTS["vsock_uds_path"]
    vm_port: int = _DEFAULTS["vm_port"]

    # Paths
    firecracker_bin: str = _DEFAULTS["firecracker_bin"]
    kernel_path: str = _DEFAULTS["kernel_path"]
    rootfs_path: str = _DEFAULTS["rootfs_path"]
    rootfs_work_path: str = _DEFAULTS["rootfs_work_path"]
    socket_path: str = _DEFAULTS["socket_path"]

    # TAP networking (optional)
    vm_ip: str = _DEFAULTS["vm_ip"]
    host_ip: str = _DEFAULTS["host_ip"]
    subnet_mask: str = _DEFAULTS["subnet_mask"]
    tap_device: str = _DEFAULTS["tap_device"]
    guest_mac: str = _DEFAULTS["guest_mac"]

    # Audit
    audit_log_path: str = _DEFAULTS["audit_log_path"]

    # Timeouts
    health_timeout: int = _DEFAULTS["health_timeout"]
    default_exec_timeout: int = _DEFAULTS["default_exec_timeout"]
    max_exec_timeout: int = _DEFAULTS["max_exec_timeout"]

    # Safety
    enforce_safety: bool = _DEFAULTS["enforce_safety"]

    # Server
    transport: str = _DEFAULTS["transport"]
    sse_port: int = _DEFAULTS["sse_port"]

    # Internal
    project_root: str = ""

    def resolve_path(self, path: str) -> str:
        """Resolve a path relative to the project root."""
        path = os.path.expanduser(path)
        if os.path.isabs(path):
            return path
        return os.path.join(self.project_root, path)


def load_config(config_path: Optional[str] = None) -> BunkerVMConfig:
    """Load configuration from TOML file, env vars, and defaults.

    Args:
        config_path: Explicit path to bunkervm.toml. If None, searches
                     current directory and parent directories.

    Returns:
        Validated BunkerVMConfig instance.
    """
    config = BunkerVMConfig()

    # Find config file
    toml_path = _find_config(config_path)
    if toml_path:
        toml_data = _read_toml(toml_path)
        config.project_root = os.path.dirname(os.path.abspath(toml_path))
        _apply_toml(config, toml_data)
        logger.info("Config loaded from %s", toml_path)
    else:
        config.project_root = os.getcwd()
        logger.info("No config file found, using defaults")

    # Override with environment variables
    _apply_env(config)

    # Resolve relative paths (expand ~ for ~/.bunkervm/ paths)
    config.firecracker_bin = os.path.expanduser(config.firecracker_bin)
    config.kernel_path = config.resolve_path(os.path.expanduser(config.kernel_path))
    config.rootfs_path = config.resolve_path(os.path.expanduser(config.rootfs_path))
    config.audit_log_path = os.path.expanduser(config.audit_log_path)

    # Validate
    _validate(config)

    return config


def _find_config(explicit_path: Optional[str]) -> Optional[str]:
    """Find the bunkervm.toml config file."""
    if explicit_path:
        if os.path.exists(explicit_path):
            return explicit_path
        logger.warning("Config file not found: %s", explicit_path)
        return None

    # Search current directory and parents
    current = os.getcwd()
    for _ in range(5):  # Max 5 levels up
        candidate = os.path.join(current, "bunkervm.toml")
        if os.path.exists(candidate):
            return candidate
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent

    return None


def _read_toml(path: str) -> dict:
    """Read a TOML file. Uses tomllib (3.11+) or falls back to basic parser."""
    try:
        # Python 3.11+
        import tomllib
        with open(path, "rb") as f:
            return tomllib.load(f)
    except ImportError:
        pass

    try:
        # Third-party fallback
        import tomli
        with open(path, "rb") as f:
            return tomli.load(f)
    except ImportError:
        pass

    # Basic manual parser for simple key=value TOML
    logger.warning("No TOML parser available, using basic parser")
    return _basic_toml_parse(path)


def _basic_toml_parse(path: str) -> dict:
    """Minimal TOML parser for flat key=value files.

    Handles:
      key = "string"
      key = 123
      key = true/false
      [section]
      # comments

    Does NOT handle: arrays, inline tables, multi-line strings, etc.
    """
    result = {}
    current_section = None

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # Section header
            if line.startswith("[") and line.endswith("]"):
                current_section = line[1:-1].strip()
                if current_section not in result:
                    result[current_section] = {}
                continue

            # Key = Value
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()

                # Strip inline comments
                if " #" in value:
                    value = value[:value.index(" #")].strip()

                # Parse value
                parsed = _parse_value(value)

                if current_section:
                    result[current_section][key] = parsed
                else:
                    result[key] = parsed

    return result


def _parse_value(value: str):
    """Parse a TOML value (string, int, float, bool)."""
    # Quoted string
    if (value.startswith('"') and value.endswith('"')) or \
       (value.startswith("'") and value.endswith("'")):
        return value[1:-1]

    # Boolean
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False

    # Integer
    try:
        return int(value)
    except ValueError:
        pass

    # Float
    try:
        return float(value)
    except ValueError:
        pass

    # Bare string
    return value


def _apply_toml(config: BunkerVMConfig, data: dict) -> None:
    """Apply TOML data to config, handling sections."""
    # Flat keys at top level
    for key, value in data.items():
        if isinstance(value, dict):
            # Nested section
            for sub_key, sub_value in value.items():
                _set_config_value(config, sub_key, sub_value)
        else:
            _set_config_value(config, key, value)


def _set_config_value(config: BunkerVMConfig, key: str, value) -> None:
    """Set a config attribute if it exists."""
    if hasattr(config, key):
        expected_type = type(getattr(config, key))
        try:
            setattr(config, key, expected_type(value))
        except (ValueError, TypeError) as e:
            logger.warning("Invalid config value for %s: %s (%s)", key, value, e)
    else:
        logger.debug("Unknown config key: %s", key)


def _apply_env(config: BunkerVMConfig) -> None:
    """Override config with BUNKERVM_* environment variables."""
    env_map = {
        "BUNKERVM_VM_IP": "vm_ip",
        "BUNKERVM_VM_PORT": "vm_port",
        "BUNKERVM_HOST_IP": "host_ip",
        "BUNKERVM_TAP_DEVICE": "tap_device",
        "BUNKERVM_FIRECRACKER_BIN": "firecracker_bin",
        "BUNKERVM_KERNEL_PATH": "kernel_path",
        "BUNKERVM_ROOTFS_PATH": "rootfs_path",
        "BUNKERVM_SOCKET_PATH": "socket_path",
        "BUNKERVM_AUDIT_LOG": "audit_log_path",
        "BUNKERVM_VCPU_COUNT": "vcpu_count",
        "BUNKERVM_MEM_SIZE_MIB": "mem_size_mib",
        "BUNKERVM_HEALTH_TIMEOUT": "health_timeout",
        "BUNKERVM_ENFORCE_SAFETY": "enforce_safety",
        "BUNKERVM_TRANSPORT": "transport",
        "BUNKERVM_SSE_PORT": "sse_port",
    }

    for env_var, config_key in env_map.items():
        value = os.environ.get(env_var)
        if value is not None:
            _set_config_value(config, config_key, value)
            logger.debug("Config override from env: %s=%s", env_var, value)


def _validate(config: BunkerVMConfig) -> None:
    """Validate configuration values."""
    if config.vcpu_count < 1 or config.vcpu_count > 32:
        logger.warning("vcpu_count=%d is unusual (expected 1-32)", config.vcpu_count)

    if config.mem_size_mib < 256:
        logger.warning("mem_size_mib=%d is very low (minimum recommended: 512)", config.mem_size_mib)

    if config.vm_port < 1 or config.vm_port > 65535:
        raise ValueError(f"Invalid vm_port: {config.vm_port}")

    if config.health_timeout < 5:
        logger.warning("health_timeout=%d is very short", config.health_timeout)
