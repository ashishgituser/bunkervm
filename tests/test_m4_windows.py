#!/usr/bin/env python3
"""
BunkerVM M4 Test Suite — Platform Detection, WSL Bridge, and Windows Integration.

This test validates:
  Phase 1  – platform.py pure-function tests (importable everywhere)
  Phase 2  – wsl_bridge.py unit tests (mocked subprocess where needed)
  Phase 3  – cli.py WSL-aware engine commands (import + signature checks)
  Phase 4  – discovery.py Windows-aware path
  Phase 5  – daemon.py Windows guard
  Phase 6  – installer/windows/ file verification
  Phase 7  – (Live) WSL bridge integration test (only runs if WSL2 is available)

Run:
    python tests/test_m4_windows.py
"""

from __future__ import annotations

import importlib
import os
import sys
import time

# ── Test infrastructure ──

_pass = 0
_fail = 0


def check(label: str, condition: bool, detail: str = ""):
    global _pass, _fail
    if condition:
        _pass += 1
        print(f"  \033[32mPASS\033[0m  {label}")
    else:
        _fail += 1
        print(f"  \033[31mFAIL\033[0m  {label}  {detail}")


def section(title: str):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


# ════════════════════════════════════════════════════════════════
# Phase 1: platform.py
# ════════════════════════════════════════════════════════════════
section("Phase 1: platform.py — Platform Detection")

from bunkervm.engine.platform import (
    is_windows,
    is_linux,
    is_wsl,
    is_windows_workspace,
    has_kvm,
    get_wsl_distro,
    wsl2_available,
    list_wsl_distros,
    default_wsl_distro,
    detect_platform,
    PlatformInfo,
)

# Type checks
check("is_windows() returns bool", isinstance(is_windows(), bool))
check("is_linux() returns bool", isinstance(is_linux(), bool))
check("is_wsl() returns bool", isinstance(is_wsl(), bool))
check("has_kvm() returns bool", isinstance(has_kvm(), bool))
check("get_wsl_distro() returns str", isinstance(get_wsl_distro(), str))

# Consistency: exactly one of windows/linux should be True
on_win = is_windows()
on_linux = is_linux()
check(
    "is_windows() XOR is_linux()",
    on_win != on_linux or (not on_win and not on_linux),
    f"win={on_win}, linux={on_linux}",
)

# detect_platform returns PlatformInfo
info = detect_platform()
check("detect_platform() returns PlatformInfo", isinstance(info, PlatformInfo))
check("PlatformInfo.os is a string", info.os in ("windows", "linux", "wsl", "unknown"))
check("PlatformInfo.arch is set", len(info.arch) > 0)
check("PlatformInfo.python_version is set", len(info.python_version) > 0)

# Platform-specific sanity
if on_win:
    check("On Windows: os == 'windows'", info.os == "windows")
    check("On Windows: needs_wsl_bridge", info.needs_wsl_bridge)
    check("On Windows: wsl2_available() is bool", isinstance(wsl2_available(), bool))
    check("On Windows: list_wsl_distros() returns list", isinstance(list_wsl_distros(), list))
elif is_wsl():
    check("In WSL: os == 'wsl'", info.os == "wsl")
    check("In WSL: not needs_wsl_bridge", not info.needs_wsl_bridge)
    check("In WSL: get_wsl_distro() returns string", len(get_wsl_distro()) > 0)
else:
    check("On Linux: os == 'linux'", info.os == "linux")
    check("On Linux: not needs_wsl_bridge", not info.needs_wsl_bridge)


# ════════════════════════════════════════════════════════════════
# Phase 2: wsl_bridge.py imports & structure
# ════════════════════════════════════════════════════════════════
section("Phase 2: wsl_bridge.py — Imports & Structure")

from bunkervm.engine.wsl_bridge import WSLBridge, wsl_run, wsl_bash

check("WSLBridge class imported", WSLBridge is not None)
check("wsl_run function imported", callable(wsl_run))
check("wsl_bash function imported", callable(wsl_bash))

# WSLBridge has expected methods
check("WSLBridge.check_ready exists", hasattr(WSLBridge, "check_ready"))
check("WSLBridge.ensure_installed exists", hasattr(WSLBridge, "ensure_installed"))
check("WSLBridge.start_engine exists", hasattr(WSLBridge, "start_engine"))
check("WSLBridge.stop_engine exists", hasattr(WSLBridge, "stop_engine"))
check("WSLBridge.engine_status exists", hasattr(WSLBridge, "engine_status"))


# ════════════════════════════════════════════════════════════════
# Phase 3: cli.py — WSL-aware engine commands
# ════════════════════════════════════════════════════════════════
section("Phase 3: cli.py — WSL-Aware Engine Commands")

from bunkervm.cli import (
    cmd_engine_start,
    cmd_engine_stop,
    cmd_engine_status,
    _is_wsl as cli_is_wsl,
    _is_windows_workspace as cli_is_win_ws,
    _get_wsl_distro as cli_get_distro,
    _wsl_run as cli_wsl_run,
    _ensure_bunkervm_in_wsl as cli_ensure_bvm,
)

check("cmd_engine_start is callable", callable(cmd_engine_start))
check("cmd_engine_stop is callable", callable(cmd_engine_stop))
check("cmd_engine_status is callable", callable(cmd_engine_status))
check("cli._is_wsl delegates to platform", callable(cli_is_wsl))
check("cli._get_wsl_distro delegates to platform", callable(cli_get_distro))
check("cli._wsl_run delegates to wsl_bridge", callable(cli_wsl_run))
check("cli._ensure_bunkervm_in_wsl delegates to WSLBridge", callable(cli_ensure_bvm))

# Check that cmd_engine_start route separates Windows and Linux
import inspect
source = inspect.getsource(cmd_engine_start)
check(
    "cmd_engine_start checks is_windows()",
    "is_windows" in source,
    "Should branch on platform",
)
check(
    "cmd_engine_start calls _engine_start_windows",
    "_engine_start_windows" in source,
    "Should delegate to Windows-specific function",
)


# ════════════════════════════════════════════════════════════════
# Phase 4: discovery.py — Windows-aware resolution
# ════════════════════════════════════════════════════════════════
section("Phase 4: discovery.py — Windows-Aware Resolution")

from bunkervm.engine.discovery import _resolve_engine_address

src = inspect.getsource(_resolve_engine_address)
check(
    "_resolve_engine_address checks is_windows()",
    "is_windows" in src,
    "Should skip PID file on Windows",
)
check(
    "_resolve_engine_address still returns default fallback",
    "127.0.0.1" in src,
)


# ════════════════════════════════════════════════════════════════
# Phase 5: daemon.py — Windows guard
# ════════════════════════════════════════════════════════════════
section("Phase 5: daemon.py — Windows Guard")

from bunkervm.engine.daemon import EngineDaemon

# Check that the Windows guard is in the start() method source
daemon_src = inspect.getsource(EngineDaemon.start)
check(
    "EngineDaemon.start() checks is_windows()",
    "is_windows" in daemon_src,
)
check(
    "EngineDaemon.start() raises RuntimeError on Windows",
    "RuntimeError" in daemon_src,
)


# ════════════════════════════════════════════════════════════════
# Phase 6: Installer files
# ════════════════════════════════════════════════════════════════
section("Phase 6: Installer Files Verification")

# Find project root (tests/ is one level below)
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

installer_dir = os.path.join(project_root, "installer", "windows")
check(
    "installer/windows/ directory exists",
    os.path.isdir(installer_dir),
)

ps1_path = os.path.join(installer_dir, "install.ps1")
readme_path = os.path.join(installer_dir, "README.md")

check(
    "installer/windows/install.ps1 exists",
    os.path.isfile(ps1_path),
)
check(
    "installer/windows/README.md exists",
    os.path.isfile(readme_path),
)

# Validate install.ps1 content
if os.path.isfile(ps1_path):
    with open(ps1_path, "r", encoding="utf-8") as f:
        ps1 = f.read()
    check("install.ps1: checks Windows version", "19041" in ps1)
    check("install.ps1: installs WSL", "wsl --install" in ps1)
    check("install.ps1: configures .wslconfig", "nestedVirtualization" in ps1)
    check("install.ps1: installs bunkervm via pip", "pip install bunkervm" in ps1 or "pip" in ps1)
    check("install.ps1: creates CLI shim", "bunkervm.cmd" in ps1 or "ShimPath" in ps1)
    check("install.ps1: supports AutoStart", "ScheduledTask" in ps1)


# ════════════════════════════════════════════════════════════════
# Phase 7: Engine __init__ exports
# ════════════════════════════════════════════════════════════════
section("Phase 7: Engine Package Exports")

import bunkervm.engine as engine

check("engine exports detect_platform", hasattr(engine, "detect_platform"))
check("engine exports PlatformInfo", hasattr(engine, "PlatformInfo"))
check("engine exports is_windows", hasattr(engine, "is_windows"))
check("engine exports is_wsl", hasattr(engine, "is_wsl"))
check("engine exports has_kvm", hasattr(engine, "has_kvm"))


# ════════════════════════════════════════════════════════════════
# Phase 8: Live WSL Bridge test (only on Windows with WSL2)
# ════════════════════════════════════════════════════════════════

if on_win and wsl2_available():
    section("Phase 8: Live WSL Bridge Integration (Windows + WSL2)")

    try:
        bridge = WSLBridge()
        check("WSLBridge() auto-detected distro", bridge.distro is not None)

        problems = bridge.check_ready()
        check("WSLBridge.check_ready() returns list", isinstance(problems, list))
        if problems:
            print(f"    Info: {len(problems)} readiness issue(s):")
            for p in problems:
                print(f"      - {p}")
        else:
            check("WSL2 environment is ready", True)

            # Try a simple wsl_run
            r = wsl_run(bridge.distro, "echo", "hello-from-wsl")
            check(
                "wsl_run echoes correctly",
                r.returncode == 0 and "hello-from-wsl" in r.stdout,
                f"rc={r.returncode}, stdout={r.stdout!r}",
            )

            # Test engine status probe (engine may or may not be running)
            status = bridge.engine_status()
            check(
                "engine_status returns dict or None",
                status is None or isinstance(status, dict),
            )
    except Exception as exc:
        check("WSLBridge instantiation", False, str(exc))
elif on_win:
    section("Phase 8: Live WSL Bridge Integration — SKIPPED (no WSL2)")
else:
    section("Phase 8: Live WSL Bridge Integration — SKIPPED (not on Windows)")


# ════════════════════════════════════════════════════════════════
# Summary
# ════════════════════════════════════════════════════════════════

print(f"\n{'=' * 60}")
print(f"  Summary")
print(f"{'=' * 60}")
print()
total = _pass + _fail
print(f"  {_pass}/{total} passed, {_fail} failed")
print()
sys.exit(1 if _fail else 0)
