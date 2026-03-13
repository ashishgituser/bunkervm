"""
BunkerVM Engine Platform Detection.

Centralises all platform / environment detection so that CLI, daemon,
discovery, and the WSL bridge share a single source of truth.

Detection hierarchy:
  1. Native Linux with /dev/kvm  → "linux"
  2. Inside WSL2                 → "wsl"
  3. Native Windows              → "windows"
  4. Other / unsupported         → "unknown"
"""

from __future__ import annotations

import os
import platform as _platform
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional


# ── Primitives ──


def is_windows() -> bool:
    """True when running on native Windows (NOT inside WSL)."""
    return sys.platform == "win32"


def is_linux() -> bool:
    """True when running on Linux (including WSL2)."""
    return sys.platform.startswith("linux")


def is_wsl() -> bool:
    """True when running inside a WSL2 distribution."""
    if not is_linux():
        return False
    try:
        return "microsoft" in _platform.uname().release.lower()
    except Exception:
        return False


def is_windows_workspace() -> bool:
    """True inside WSL when the cwd is a Windows‑mounted path (``/mnt/…``)."""
    return is_wsl() and os.getcwd().startswith("/mnt/")


def has_kvm() -> bool:
    """True if ``/dev/kvm`` exists and the user can read+write it."""
    return os.path.exists("/dev/kvm") and os.access("/dev/kvm", os.R_OK | os.W_OK)


def get_wsl_distro() -> str:
    """Return the WSL distribution name (or ``'Ubuntu'`` as fallback)."""
    return os.environ.get("WSL_DISTRO_NAME", "Ubuntu")


# ── Windows → WSL2 helpers ──


def wsl2_available() -> bool:
    """Check whether WSL 2 is installed and at least one distro exists.

    Only meaningful when called from native Windows.
    """
    if not is_windows():
        return False
    try:
        result = subprocess.run(
            ["wsl", "--list", "--verbose"],
            capture_output=True, text=True, timeout=10,
        )
        # Output contains VERSION 2 lines for WSL2 distros.
        # The output is sometimes UTF‑16‑LE on Windows, so decode defensively.
        text = result.stdout or ""
        return "2" in text and result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def list_wsl_distros() -> list[str]:
    """Return a list of installed WSL distro names (Windows only)."""
    if not is_windows():
        return []
    try:
        result = subprocess.run(
            ["wsl", "--list", "--quiet"],
            capture_output=True, timeout=10,
        )
        if result.returncode != 0:
            return []
        # wsl --list --quiet outputs UTF‑16‑LE on some Windows versions
        text = result.stdout.decode("utf-16-le", errors="replace").strip()
        if not text:
            text = result.stdout.decode("utf-8", errors="replace").strip()
        return [d.strip() for d in text.splitlines() if d.strip()]
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return []


def default_wsl_distro() -> Optional[str]:
    """Return a suitable WSL2 distro name, or ``None`` if none found.

    Prefers Ubuntu, then falls back to the first available distro.
    """
    distros = list_wsl_distros()
    if not distros:
        return None
    for d in distros:
        if d.lower().startswith("ubuntu"):
            return d
    return distros[0]


# ── High‑level summary ──


@dataclass
class PlatformInfo:
    """Snapshot of the runtime environment."""

    os: str                     # "windows" | "linux" | "wsl" | "unknown"
    arch: str                   # e.g. "x86_64", "aarch64"
    python_version: str
    kvm_available: bool
    wsl2_available: bool
    wsl_distro: Optional[str]  # Only set inside WSL or when WSL2 found on Windows

    @property
    def can_run_firecracker(self) -> bool:
        """True when this environment can boot Firecracker VMs directly."""
        return self.os in ("linux", "wsl") and self.kvm_available

    @property
    def needs_wsl_bridge(self) -> bool:
        """True when we must delegate to WSL2 for VM operations."""
        return self.os == "windows"


def detect_platform() -> PlatformInfo:
    """Detect the current runtime platform.

    Cheap to call — results are not cached because the caller can decide
    whether to cache.
    """
    if is_windows():
        os_name = "windows"
        distro = default_wsl_distro()
        wsl2 = wsl2_available()
    elif is_wsl():
        os_name = "wsl"
        distro = get_wsl_distro()
        wsl2 = True
    elif is_linux():
        os_name = "linux"
        distro = None
        wsl2 = False
    else:
        os_name = "unknown"
        distro = None
        wsl2 = False

    return PlatformInfo(
        os=os_name,
        arch=_platform.machine(),
        python_version=_platform.python_version(),
        kvm_available=has_kvm(),
        wsl2_available=wsl2,
        wsl_distro=distro,
    )
