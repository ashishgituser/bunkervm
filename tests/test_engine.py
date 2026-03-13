#!/usr/bin/env python3
"""
M1+M2 Engine Integration Test — validates engine daemon + SDK auto-discovery.

Run:
    python3 tests/test_engine.py

Phases:
  1. Import validation
  2. Engine startup (foreground in a thread)
  3. API endpoint tests via EngineClient
  4. SDK auto-discovery test (Sandbox → engine)
  5. Shutdown
"""

import json
import os
import sys
import threading
import time
import urllib.request
import urllib.error

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = 0
FAIL = 0


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ── Phase 1: Import Validation ──

section("Phase 1: Import Validation")

try:
    from bunkervm.engine.config import EngineConfig, DEFAULT_ENGINE_PORT, pid_alive
    check("EngineConfig import", True)
    check("DEFAULT_ENGINE_PORT = 9551", DEFAULT_ENGINE_PORT == 9551)
    check("pid_alive is callable", callable(pid_alive))
except Exception as e:
    check("EngineConfig import", False, str(e))

try:
    from bunkervm.engine.models import (
        SandboxCreateRequest, ExecRequest, WriteFileRequest,
        SandboxInfo, EngineStatus, ExecResult, ApiError,
    )
    check("Models import", True)
except Exception as e:
    check("Models import", False, str(e))

try:
    from bunkervm.engine.client import (
        EngineClient, EngineBackedClient,
        EngineAPIError, EngineConnectionError,
    )
    check("Client imports (EngineClient, EngineBackedClient)", True)
except Exception as e:
    check("Client imports", False, str(e))

try:
    from bunkervm.engine.discovery import (
        discover_engine, is_engine_running, parse_engine_url, engine_url,
    )
    check("Discovery imports", True)
except Exception as e:
    check("Discovery imports", False, str(e))

try:
    from bunkervm.engine.api import EngineAPIHandler
    check("API handler import", True)
except Exception as e:
    check("API handler import", False, str(e))

try:
    from bunkervm.engine.daemon import EngineDaemon
    check("Daemon import", True)
except Exception as e:
    check("Daemon import", False, str(e))

try:
    from bunkervm.engine import (
        EngineConfig, EngineClient, EngineBackedClient,
        EngineDaemon, DEFAULT_ENGINE_PORT,
        discover_engine, is_engine_running, parse_engine_url,
    )
    check("Package __init__ exports", True)
except Exception as e:
    check("Package __init__ exports", False, str(e))

try:
    from bunkervm import EngineClient, discover_engine, is_engine_running
    check("Top-level bunkervm exports", True)
except Exception as e:
    check("Top-level bunkervm exports", False, str(e))

# ── Phase 1b: Unit tests for pure functions ──

section("Phase 1b: Pure Function Tests")

# parse_engine_url
host, port = parse_engine_url("http://localhost:9551")
check("parse_engine_url('http://localhost:9551')", host == "localhost" and port == 9551,
      f"got ({host}, {port})")

host, port = parse_engine_url("http://10.0.0.1:8080")
check("parse_engine_url('http://10.0.0.1:8080')", host == "10.0.0.1" and port == 8080,
      f"got ({host}, {port})")

host, port = parse_engine_url("myhost")
check("parse_engine_url('myhost')", host == "myhost" and port == 9551,
      f"got ({host}, {port})")

# SandboxCreateRequest.from_dict
req = SandboxCreateRequest.from_dict({"name": "test", "cpus": 2})
check("SandboxCreateRequest.from_dict", req.name == "test" and req.cpus == 2)

# ExecRequest.from_dict
req = ExecRequest.from_dict({"command": "echo hi", "timeout": 10})
check("ExecRequest.from_dict", req.command == "echo hi" and req.timeout == 10)

# EngineStatus.to_dict
status = EngineStatus(status="running", version="0.7.2", sandbox_count=3)
d = status.to_dict()
check("EngineStatus.to_dict", d["status"] == "running" and d["sandbox_count"] == 3)

# ApiError.to_dict
err = ApiError(error="Not found", detail="No such sandbox")
d = err.to_dict()
check("ApiError.to_dict", d["error"] == "Not found" and d["detail"] == "No such sandbox")

# EngineConfig defaults
cfg = EngineConfig()
check("EngineConfig defaults", cfg.port == 9551 and cfg.max_sandboxes == 10)

# pid_alive for current process (should be alive)
check("pid_alive(os.getpid())", pid_alive(os.getpid()))

# pid_alive for impossible PID
check("pid_alive(99999999) is False", not pid_alive(99999999))

# is_engine_running before engine starts (should be False)
check("is_engine_running() before start", not is_engine_running())

# discover_engine before engine starts (should be None)
check("discover_engine() before start", discover_engine() is None)

# ── Phase 2: Engine Startup ──

section("Phase 2: Engine Startup")

# Use a non-default port to avoid conflicts
TEST_PORT = 19551
engine_config = EngineConfig(port=TEST_PORT, max_sandboxes=5)

daemon = EngineDaemon(config=engine_config)

# Start daemon in a background thread
daemon_thread = threading.Thread(target=daemon.start, daemon=True)
daemon_thread.start()

# Wait for the server to be ready
time.sleep(2)

check("Daemon thread is alive", daemon_thread.is_alive())
check("Daemon is running", daemon._running)

# ── Phase 3: API Endpoint Tests via EngineClient ──

section("Phase 3: API Endpoint Tests")

client = EngineClient(port=TEST_PORT)

# GET /engine/status
try:
    status = client.status()
    check("GET /engine/status returns data", "status" in status)
    check("  status = running", status.get("status") == "running")
    check("  has version", "version" in status)
    check("  sandbox_count = 0", status.get("sandbox_count") == 0)
    check("  has platform", "platform" in status)
    check("  has uptime_seconds", "uptime_seconds" in status)
except Exception as e:
    check("GET /engine/status", False, str(e))

# GET /sandboxes (empty)
try:
    sandboxes = client.list_sandboxes()
    check("GET /sandboxes (empty)", sandboxes == [])
except Exception as e:
    check("GET /sandboxes", False, str(e))

# GET /sandboxes/nonexistent → 404
try:
    client.get_sandbox("nonexistent")
    check("GET /sandboxes/nonexistent", False, "Expected 404")
except EngineAPIError as e:
    check("GET /sandboxes/nonexistent → 404", e.status_code == 404)
except Exception as e:
    check("GET /sandboxes/nonexistent", False, str(e))

# POST /sandboxes/{bad}/exec → 404
try:
    client.exec("nonexistent", "echo hi")
    check("POST /sandboxes/bad/exec", False, "Expected 404")
except EngineAPIError as e:
    check("POST /sandboxes/bad/exec → 404", e.status_code == 404)
except Exception as e:
    check("POST /sandboxes/bad/exec", False, str(e))

# DELETE /sandboxes/{bad} → 404
try:
    client.destroy_sandbox("nonexistent")
    check("DELETE /sandboxes/bad", False, "Expected 404")
except EngineAPIError as e:
    check("DELETE /sandboxes/bad → 404", e.status_code == 404)
except Exception as e:
    check("DELETE /sandboxes/bad", False, str(e))

# Bad route → 404
try:
    url = f"http://127.0.0.1:{TEST_PORT}/doesnotexist"
    req = urllib.request.Request(url)
    urllib.request.urlopen(req, timeout=5)
    check("GET /doesnotexist", False, "Expected 404")
except urllib.error.HTTPError as e:
    check("GET /doesnotexist → 404", e.code == 404)
except Exception as e:
    check("GET /doesnotexist", False, str(e))

# ── Phase 4: Sandbox Lifecycle (requires /dev/kvm) ──

section("Phase 4: Sandbox Lifecycle (requires KVM)")

has_kvm = os.path.exists("/dev/kvm")
if not has_kvm:
    print("  SKIP  /dev/kvm not available — skipping VM-based tests")
    print("        (Engine API structure is validated, VM operations need KVM)")
else:
    try:
        # Create sandbox
        sb = client.create_sandbox(name="test-sandbox", cpus=1, memory=256)
        sb_id = sb["id"]
        check("POST /sandboxes (create)", "id" in sb and "name" in sb)
        check("  name = test-sandbox", sb.get("name") == "test-sandbox")
        check("  status = running", sb.get("status") == "running")

        # List should now have 1
        sandboxes = client.list_sandboxes()
        check("GET /sandboxes (1 sandbox)", len(sandboxes) == 1)

        # Get sandbox by ID
        info = client.get_sandbox(sb_id)
        check("GET /sandboxes/{id}", info.get("id") == sb_id)

        # Exec command
        result = client.exec(sb_id, "echo hello-from-engine")
        check("POST /sandboxes/{id}/exec", "stdout" in result)
        check("  stdout contains hello", "hello-from-engine" in result.get("stdout", ""))

        # Write file
        client.write_file(sb_id, "/tmp/test.txt", "engine test content")
        check("POST /sandboxes/{id}/write-file", True)

        # Read file
        content = client.read_file(sb_id, "/tmp/test.txt")
        check("GET /sandboxes/{id}/read-file",
              "engine test content" in content.get("content", ""))

        # List dir
        listing = client.list_dir(sb_id, "/tmp")
        check("GET /sandboxes/{id}/list-dir", "entries" in listing)

        # Sandbox status
        sb_status = client.sandbox_status(sb_id)
        check("GET /sandboxes/{id}/status", sb_status is not None)

        # Destroy
        result = client.destroy_sandbox(sb_id)
        check("DELETE /sandboxes/{id}", result.get("status") == "destroyed")

        # Verify destroyed
        sandboxes = client.list_sandboxes()
        check("Sandbox removed after destroy", len(sandboxes) == 0)

    except Exception as e:
        check("Sandbox lifecycle", False, str(e))

# ── Phase 5: Auto-Discovery Test ──

section("Phase 5: Auto-Discovery (M2)")

# Set env var to point to our test engine
os.environ["BUNKERVM_ENGINE_URL"] = f"http://127.0.0.1:{TEST_PORT}"

try:
    discovered = discover_engine()
    check("discover_engine() finds engine via env var",
          discovered is not None)
    if discovered:
        status = discovered.status()
        check("  discovered client can call status()",
              status.get("status") == "running")
except Exception as e:
    check("discover_engine() via env var", False, str(e))

try:
    check("is_engine_running() returns True", is_engine_running())
except Exception as e:
    check("is_engine_running()", False, str(e))

try:
    url = engine_url()
    check("engine_url() returns URL", url is not None and str(TEST_PORT) in url)
except Exception as e:
    check("engine_url()", False, str(e))

# EngineBackedClient adapter test
try:
    adapter = EngineBackedClient(engine=client, sandbox_id="fake-id")
    check("EngineBackedClient creation", adapter.label == "engine:fake-id")
except Exception as e:
    check("EngineBackedClient creation", False, str(e))

# Clean up env var
del os.environ["BUNKERVM_ENGINE_URL"]

# ── Phase 6: Shutdown ──

section("Phase 6: Engine Shutdown")

try:
    daemon.stop()
    time.sleep(1)
    check("Daemon stopped", not daemon._running)
except Exception as e:
    check("Daemon stop", False, str(e))

# ── Summary ──

section("Summary")
total = PASS + FAIL
print(f"\n  {PASS}/{total} passed, {FAIL} failed\n")
sys.exit(1 if FAIL > 0 else 0)
