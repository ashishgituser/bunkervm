"""Test Sandbox context manager — reusable VM session."""
from bunkervm import Sandbox

print("=== Test: Sandbox context manager ===")
with Sandbox(quiet=False) as sb:
    # Test 1: Simple run
    r1 = sb.run("print('hello from sandbox')")
    print(f"  run() result: {r1!r}")
    assert r1 == "hello from sandbox", f"Expected greeting, got {r1!r}"

    # Test 2: State persists across runs (same VM)
    sb.run("x = 42")
    r2 = sb.run("print(x * 2)")
    print(f"  persisted state: {r2!r}")
    assert r2 == "84", f"Expected '84', got {r2!r}"

    # Test 3: exec() for raw shell commands
    r3 = sb.exec("uname -r")
    print(f"  exec('uname -r'): {r3.strip()!r}")
    assert "6.1" in r3, f"Expected kernel 6.1.x, got {r3!r}"

    # Test 4: Multi-line code
    code = """
import json
data = {"vm": "bunkervm", "version": 4}
print(json.dumps(data))
"""
    r4 = sb.run(code)
    print(f"  multi-line: {r4!r}")
    assert '"bunkervm"' in r4

print("\nAll Sandbox tests passed!")
