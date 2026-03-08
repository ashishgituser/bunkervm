#!/usr/bin/env python3
"""Quick smoke test — talks directly to the VM via vsock."""
import socket, json, sys

def vsock_req(method, path, body=None):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(30)
    s.connect("/tmp/bunkervm-vsock.sock")
    s.sendall(b"CONNECT 8080\n")
    resp = s.recv(256)
    if b"OK" not in resp:
        raise Exception(f"handshake failed: {resp}")
    if body:
        payload = json.dumps(body).encode()
        req = (
            f"{method} {path} HTTP/1.0\r\n"
            f"Host: localhost\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(payload)}\r\n"
            f"Connection: close\r\n\r\n"
        ).encode() + payload
    else:
        req = (
            f"{method} {path} HTTP/1.0\r\n"
            f"Host: localhost\r\n"
            f"Connection: close\r\n\r\n"
        ).encode()
    s.sendall(req)
    data = b""
    while True:
        chunk = s.recv(65536)
        if not chunk:
            break
        data += chunk
    s.close()
    parts = data.split(b"\r\n\r\n", 1)
    return json.loads(parts[1]) if len(parts) > 1 else {}

passed = 0
failed = 0

def test(name, fn):
    global passed, failed
    try:
        fn()
        print(f"  PASS  {name}")
        passed += 1
    except Exception as e:
        print(f"  FAIL  {name}: {e}")
        failed += 1

def t_health():
    r = vsock_req("GET", "/health")
    assert r.get("status") == "ok", f"Expected ok, got {r}"

def t_exec():
    r = vsock_req("POST", "/exec", {"command": "echo Hello from BunkerVM!"})
    assert r.get("exit_code") == 0, f"exit_code={r.get('exit_code')}"
    assert "Hello from BunkerVM" in r.get("stdout", ""), f"stdout={r.get('stdout')}"

def t_write_file():
    r = vsock_req("POST", "/write-file", {"path": "/tmp/test.txt", "content": "BunkerVM works!"})
    assert "error" not in r, f"error={r.get('error')}"

def t_read_file():
    r = vsock_req("POST", "/read-file", {"path": "/tmp/test.txt"})
    assert r.get("content", "").strip() == "BunkerVM works!", f"content={r.get('content')}"

def t_status():
    r = vsock_req("GET", "/status")
    assert r.get("status") in ("ok", "running"), f"status={r.get('status')}"
    assert r.get("uptime_seconds", 0) > 0, "no uptime"

def t_python():
    r = vsock_req("POST", "/exec", {"command": "python3 -c 'print(2+2)'"})
    assert r.get("exit_code") == 0
    assert "4" in r.get("stdout", "")

def t_list_dir():
    r = vsock_req("POST", "/exec", {"command": "ls /tmp/test.txt"})
    assert r.get("exit_code") == 0

print("BunkerVM Smoke Test")
print("=" * 40)

test("health", t_health)
test("exec (echo)", t_exec)
test("write_file", t_write_file)
test("read_file", t_read_file)
test("status", t_status)
test("python", t_python)
test("list_dir", t_list_dir)

print("=" * 40)
print(f"{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
