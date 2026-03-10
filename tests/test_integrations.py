"""Test BunkerVMToolsBase auto-boot mode — the core of the refactored integrations."""
import sys
sys.path.insert(0, "/mnt/c/ashish/NervOS")

from bunkervm.integrations.base import BunkerVMToolsBase

print("=== Test: BunkerVMToolsBase auto-boot ===\n")

# Auto-boot mode (no args = spins up a Firecracker VM)
base = BunkerVMToolsBase()
print("1. Auto-boot: VM started")
assert base._sandbox is not None, "Expected auto-boot sandbox"
assert base.client is not None, "Expected client"

# Test shared tool implementations
r1 = base._run_command("echo hello-from-base")
print(f"2. _run_command: {r1!r}")
assert "hello-from-base" in r1

r2 = base._write_file("/tmp/test_base.txt", "base-content-123")
print(f"3. _write_file: {r2!r}")
assert "bytes" in r2

r3 = base._read_file("/tmp/test_base.txt")
print(f"4. _read_file: {r3!r}")
assert "base-content-123" in r3

r4 = base._list_directory("/tmp")
print(f"5. _list_directory: {r4[:80]!r}...")
assert "test_base.txt" in r4

# Health check
h = base.health()
print(f"6. health(): {h}")
assert h is True

# Stop and verify
base.stop()
print("7. stop(): sandbox destroyed")
assert base._sandbox is None

print("\nAll BunkerVMToolsBase tests passed!")
