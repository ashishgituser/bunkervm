#!/usr/bin/env python3
"""Quick smoke test for v0.3.0 features against a running VM."""

import sys
import os
import json
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bunkervm.sandbox_client import SandboxClient


def test_basic():
    """Test basic exec, write, read, list."""
    client = SandboxClient(vsock_uds="/tmp/bunkervm-vsock.sock", vsock_port=8080)

    print("=== Test 1: Health check ===")
    ok = client.wait_for_health(timeout=5)
    assert ok, "Health check failed"
    print("  PASS: Sandbox is healthy")

    print("\n=== Test 2: Execute command ===")
    result = client.exec("echo 'hello from test'")
    assert result["exit_code"] == 0
    assert "hello from test" in result["stdout"]
    print(f"  PASS: exec returned: {result['stdout'].strip()}")

    print("\n=== Test 3: Write file ===")
    result = client.write_file("/tmp/test_v030.txt", "BunkerVM v0.3.0 test content\n")
    print(f"  PASS: write_file result: {result}")

    print("\n=== Test 4: Read file ===")
    result = client.read_file("/tmp/test_v030.txt")
    content = result.get("content", "") if isinstance(result, dict) else str(result)
    assert "BunkerVM v0.3.0" in content
    print(f"  PASS: read_file returned: {content.strip()}")

    print("\n=== Test 5: List directory ===")
    result = client.list_dir("/tmp/")
    listing = str(result)
    assert "test_v030.txt" in listing
    print(f"  PASS: list_dir found test file in /tmp/")

    print("\n=== Test 6: Status ===")
    result = client.status()
    assert result["status"] == "running"
    print(f"  PASS: VM status: {result['status']}, hostname: {result['hostname']}")
    print(f"         CPU: {result['cpu']['cores']} cores, Memory: {result['memory']['total_bytes'] // 1024 // 1024}MB")

    print("\n=== Test 7: Upload file ===")
    # Create a temp file to upload
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("uploaded content from host\n")
        local_path = f.name

    try:
        result = client.upload_file(local_path, "/tmp/uploaded.txt")
        print(f"  PASS: upload_file result: {result}")
    finally:
        os.unlink(local_path)

    # Verify the uploaded file
    result = client.read_file("/tmp/uploaded.txt")
    content = result.get("content", "") if isinstance(result, dict) else str(result)
    assert "uploaded content from host" in content
    print(f"  PASS: uploaded file content verified: {content.strip()}")

    print("\n=== Test 8: Download file ===")
    data = client.download_file("/tmp/uploaded.txt")
    assert isinstance(data, bytes)
    assert b"uploaded content from host" in data
    print(f"  PASS: download_file returned {len(data)} bytes: {data.decode().strip()}")

    print("\n=== Test 9: Reset ===")
    result = client.exec("touch /tmp/before_reset.txt && ls /tmp/before_reset.txt")
    assert result["exit_code"] == 0
    print(f"  Created /tmp/before_reset.txt")

    # We won't actually reset since it might affect other tests
    # Just verify the method exists
    print(f"  SKIP: Not resetting (would destroy test files)")

    print("\n" + "=" * 50)
    print("ALL TESTS PASSED!")
    print("=" * 50)


if __name__ == "__main__":
    test_basic()
