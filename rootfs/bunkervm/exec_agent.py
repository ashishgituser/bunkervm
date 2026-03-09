#!/usr/bin/env python3
"""
BunkerVM Exec Agent — Lightweight command execution server.

Runs INSIDE the Firecracker MicroVM. Accepts HTTP requests from
the host-side MCP server to execute commands, read/write files,
and report system status.

Purposefully zero external dependencies — stdlib only.
Must work on Alpine Linux (musl libc) with just python3 installed.

Transport:
  1. VSOCK (preferred) — zero network config, host connects via UDS
  2. TCP fallback — 0.0.0.0:8080 (always started for init health check)

Endpoints:
  POST /exec          Execute a shell command
  POST /read-file     Read file contents
  POST /write-file    Write file contents
  POST /list-dir      List directory contents
  GET  /health        Health check
  GET  /status        System status (CPU, RAM, disk, uptime)
"""

import http.server
import json
import subprocess
import os
import sys
import time
import signal
import socket as _socket
import socketserver
import base64
import threading
import traceback

# ── Configuration ──
LISTEN_HOST = os.environ.get("EXEC_HOST", "0.0.0.0")
LISTEN_PORT = int(os.environ.get("EXEC_PORT", "8080"))
VSOCK_PORT = int(os.environ.get("VSOCK_PORT", "8080"))
MAX_OUTPUT = 65536          # 64KB max stdout/stderr per command
MAX_FILE_READ = 2097152     # 2MB max file read
DEFAULT_TIMEOUT = 30        # 30s default command timeout
MAX_TIMEOUT = 300           # 5min absolute maximum

# VSOCK CID constants (in case socket module doesn't define them)
VMADDR_CID_ANY = getattr(_socket, "VMADDR_CID_ANY", 0xFFFFFFFF)


class ExecHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for sandbox operations."""

    protocol_version = "HTTP/1.1"
    server_version = "BunkerVM-ExecAgent/1.0"

    # ── Response helpers ──

    def _send_json(self, status: int, data: dict):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    # ── Route dispatch ──

    def do_GET(self):
        try:
            if self.path == "/health":
                self._send_json(200, {"status": "ok", "agent": "bunkervm-exec", "version": "1.0"})
            elif self.path == "/status":
                self._handle_status()
            else:
                self._send_json(404, {"error": f"unknown endpoint: {self.path}"})
        except Exception as e:
            self._send_json(500, {"error": str(e)})

    def do_POST(self):
        try:
            body = self._read_body()
        except json.JSONDecodeError as e:
            self._send_json(400, {"error": f"invalid JSON: {e}"})
            return
        except Exception as e:
            self._send_json(400, {"error": f"invalid request: {e}"})
            return

        try:
            if self.path == "/exec":
                self._handle_exec(body)
            elif self.path == "/read-file":
                self._handle_read_file(body)
            elif self.path == "/write-file":
                self._handle_write_file(body)
            elif self.path == "/list-dir":
                self._handle_list_dir(body)
            else:
                self._send_json(404, {"error": f"unknown endpoint: {self.path}"})
        except Exception as e:
            self._send_json(500, {"error": str(e), "traceback": traceback.format_exc()})

    # ── Handlers ──

    def _handle_exec(self, body: dict):
        """Execute a shell command."""
        command = body.get("command", "")
        if not command or not command.strip():
            self._send_json(400, {"error": "command is required"})
            return

        timeout = min(max(body.get("timeout", DEFAULT_TIMEOUT), 1), MAX_TIMEOUT)
        workdir = body.get("workdir", "/root")
        if not os.path.isdir(workdir):
            workdir = "/"

        start_time = time.monotonic()
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=workdir,
                env={
                    **os.environ,
                    "TERM": "dumb",
                    "COLUMNS": "200",
                    "LANG": "C.UTF-8",
                    "HOME": "/root",
                    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                },
            )
            elapsed = time.monotonic() - start_time
            self._send_json(200, {
                "exit_code": result.returncode,
                "stdout": result.stdout[:MAX_OUTPUT],
                "stderr": result.stderr[:MAX_OUTPUT],
                "duration_ms": round(elapsed * 1000, 1),
                "truncated": len(result.stdout) > MAX_OUTPUT or len(result.stderr) > MAX_OUTPUT,
            })
        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - start_time
            self._send_json(200, {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Command timed out after {timeout}s",
                "duration_ms": round(elapsed * 1000, 1),
                "timed_out": True,
            })
        except Exception as e:
            self._send_json(500, {"error": f"execution failed: {e}"})

    def _handle_read_file(self, body: dict):
        """Read file contents."""
        path = body.get("path", "")
        if not path:
            self._send_json(400, {"error": "path is required"})
            return

        if not os.path.exists(path):
            self._send_json(404, {"error": f"not found: {path}"})
            return

        if os.path.isdir(path):
            self._send_json(400, {"error": f"is a directory: {path}"})
            return

        try:
            stat_info = os.stat(path)
            if stat_info.st_size > MAX_FILE_READ:
                self._send_json(400, {
                    "error": f"file too large: {stat_info.st_size} bytes (max {MAX_FILE_READ})"
                })
                return

            # Try UTF-8 text first, fallback to base64
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                self._send_json(200, {
                    "path": path,
                    "content": content,
                    "size": stat_info.st_size,
                    "encoding": "utf-8",
                })
            except (UnicodeDecodeError, ValueError):
                with open(path, "rb") as f:
                    content = base64.b64encode(f.read()).decode("ascii")
                self._send_json(200, {
                    "path": path,
                    "content": content,
                    "size": stat_info.st_size,
                    "encoding": "base64",
                })
        except PermissionError:
            self._send_json(403, {"error": f"permission denied: {path}"})

    def _handle_write_file(self, body: dict):
        """Write content to a file."""
        path = body.get("path", "")
        content = body.get("content", "")
        encoding = body.get("encoding", "utf-8")
        mode = body.get("mode", "overwrite")  # overwrite or append

        if not path:
            self._send_json(400, {"error": "path is required"})
            return

        try:
            # Create parent directories
            parent = os.path.dirname(path)
            if parent and not os.path.exists(parent):
                os.makedirs(parent, exist_ok=True)

            if encoding == "base64":
                write_mode = "ab" if mode == "append" else "wb"
                with open(path, write_mode) as f:
                    f.write(base64.b64decode(content))
            else:
                write_mode = "a" if mode == "append" else "w"
                with open(path, write_mode, encoding="utf-8") as f:
                    f.write(content)

            stat_info = os.stat(path)
            self._send_json(200, {
                "path": path,
                "size": stat_info.st_size,
                "written": True,
            })
        except PermissionError:
            self._send_json(403, {"error": f"permission denied: {path}"})
        except Exception as e:
            self._send_json(500, {"error": str(e)})

    def _handle_list_dir(self, body: dict):
        """List directory contents."""
        path = body.get("path", "/")

        if not os.path.exists(path):
            self._send_json(404, {"error": f"not found: {path}"})
            return

        if not os.path.isdir(path):
            self._send_json(400, {"error": f"not a directory: {path}"})
            return

        try:
            entries = []
            for name in sorted(os.listdir(path)):
                full = os.path.join(path, name)
                try:
                    s = os.stat(full, follow_symlinks=False)
                    is_dir = os.path.isdir(full)
                    is_link = os.path.islink(full)
                    entries.append({
                        "name": name,
                        "type": "symlink" if is_link else ("directory" if is_dir else "file"),
                        "size": s.st_size if not is_dir else None,
                        "permissions": oct(s.st_mode)[-3:],
                        "modified": s.st_mtime,
                    })
                except OSError:
                    entries.append({"name": name, "type": "unknown", "size": None})

            self._send_json(200, {"path": path, "count": len(entries), "entries": entries})
        except PermissionError:
            self._send_json(403, {"error": f"permission denied: {path}"})

    def _handle_status(self):
        """Gather system status."""
        status = {"status": "running"}

        # Hostname
        try:
            import socket as _socket
            status["hostname"] = _socket.gethostname()
        except Exception:
            pass

        # Uptime
        try:
            with open("/proc/uptime") as f:
                status["uptime_seconds"] = round(float(f.read().split()[0]), 1)
        except Exception:
            pass

        # Memory
        try:
            meminfo = {}
            with open("/proc/meminfo") as f:
                for line in f:
                    parts = line.split(":")
                    if len(parts) == 2:
                        key = parts[0].strip()
                        val = parts[1].strip().split()[0]
                        meminfo[key] = int(val) * 1024  # KB to bytes
            status["memory"] = {
                "total_bytes": meminfo.get("MemTotal", 0),
                "free_bytes": meminfo.get("MemFree", 0) + meminfo.get("Buffers", 0) + meminfo.get("Cached", 0),
                "available_bytes": meminfo.get("MemAvailable", 0),
            }
            status["memory"]["used_bytes"] = status["memory"]["total_bytes"] - status["memory"]["free_bytes"]
        except Exception:
            pass

        # Disk
        try:
            st = os.statvfs("/")
            status["disk"] = {
                "total_bytes": st.f_blocks * st.f_frsize,
                "free_bytes": st.f_bfree * st.f_frsize,
                "available_bytes": st.f_bavail * st.f_frsize,
                "used_bytes": (st.f_blocks - st.f_bfree) * st.f_frsize,
            }
        except Exception:
            pass

        # CPU
        try:
            with open("/proc/cpuinfo") as f:
                cpuinfo = f.read()
            cores = cpuinfo.count("processor")
            model = "unknown"
            for line in cpuinfo.splitlines():
                if "model name" in line:
                    model = line.split(":")[1].strip()
                    break
            status["cpu"] = {"cores": cores, "model": model}
        except Exception:
            pass

        # Load
        try:
            with open("/proc/loadavg") as f:
                parts = f.read().split()
            status["load"] = {
                "1m": float(parts[0]),
                "5m": float(parts[1]),
                "15m": float(parts[2]),
            }
        except Exception:
            pass

        # Running processes
        try:
            result = subprocess.run(
                ["ps", "aux"], capture_output=True, text=True, timeout=5
            )
            status["processes"] = len(result.stdout.strip().splitlines()) - 1  # minus header
        except Exception:
            pass

        self._send_json(200, status)

    def log_message(self, format, *args):
        """Suppress default HTTP request logging to keep console clean."""
        pass


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """Thread-per-request HTTP server for concurrent command execution."""
    allow_reuse_address = True
    daemon_threads = True


class VsockHTTPServer(ThreadedHTTPServer):
    """HTTP server listening on AF_VSOCK instead of AF_INET.

    Firecracker exposes a virtio-vsock device. The guest listens on a
    vsock port and the host connects through the UDS that Firecracker
    creates. Zero network configuration required.
    """
    address_family = getattr(_socket, "AF_VSOCK", None)

    def __init__(self, port, handler):
        # Skip HTTPServer.__init__ which tries AF_INET
        socketserver.TCPServer.__init__(
            self, ("", port), handler, bind_and_activate=False
        )
        # Create vsock socket manually
        self.socket = _socket.socket(_socket.AF_VSOCK, _socket.SOCK_STREAM)
        self.socket.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
        self.socket.bind((VMADDR_CID_ANY, port))
        self.server_activate()

    def server_bind(self):
        """Already bound in __init__, skip."""
        pass


def _has_vsock() -> bool:
    """Check if the kernel supports AF_VSOCK."""
    if not hasattr(_socket, "AF_VSOCK"):
        return False
    try:
        s = _socket.socket(_socket.AF_VSOCK, _socket.SOCK_STREAM)
        s.close()
        return True
    except (OSError, AttributeError):
        return False


def main():
    """Start the exec agent on both TCP and VSOCK (if available)."""
    servers = []

    # Always start TCP server (used by init health check + fallback)
    tcp_server = ThreadedHTTPServer((LISTEN_HOST, LISTEN_PORT), ExecHandler)
    servers.append(("TCP", f"{LISTEN_HOST}:{LISTEN_PORT}", tcp_server))
    sys.stderr.write(f"BunkerVM exec agent listening on TCP {LISTEN_HOST}:{LISTEN_PORT}\n")

    # Start VSOCK server if kernel supports it
    vsock_ok = False
    if _has_vsock():
        try:
            vsock_server = VsockHTTPServer(VSOCK_PORT, ExecHandler)
            servers.append(("VSOCK", f"CID_ANY:{VSOCK_PORT}", vsock_server))
            vsock_ok = True
            sys.stderr.write(f"BunkerVM exec agent listening on VSOCK port {VSOCK_PORT}\n")
        except Exception as e:
            sys.stderr.write(f"VSOCK setup failed ({e}), using TCP only\n")
    else:
        sys.stderr.write("VSOCK not available, using TCP only\n")

    sys.stderr.flush()

    # Signal handling
    def shutdown_handler(signum, frame):
        sys.stderr.write("Exec agent shutting down...\n")
        for _, _, srv in servers:
            srv.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    # Run each server in its own thread
    threads = []
    for name, addr, srv in servers:
        t = threading.Thread(target=srv.serve_forever, daemon=True, name=f"srv-{name}")
        t.start()
        threads.append(t)

    # Block on threads
    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        pass
    finally:
        for _, _, srv in servers:
            srv.server_close()


if __name__ == "__main__":
    main()
