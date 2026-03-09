"""
BunkerVM Sandbox Client — Connects to the exec agent inside the VM.

Transport priority:
  1. VSOCK via Firecracker UDS (zero network config — default)
  2. TCP fallback (when --network mode is used)

The Firecracker vsock UDS protocol:
  - Host connects to the Unix Domain Socket that Firecracker creates
  - Sends "CONNECT <port>\n"
  - Receives "OK <port>\n"
  - Socket becomes a transparent bidirectional stream
  - We speak HTTP over that stream

Uses only stdlib — no requests, no httpx, no external dependencies.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import time
from typing import Optional

logger = logging.getLogger("bunkervm.sandbox")

# Default timeouts
_CONNECT_TIMEOUT = 5       # seconds to wait for connection
_READ_TIMEOUT = 60         # seconds to wait for response (long commands)
_HEALTH_TIMEOUT = 3        # seconds for health check
_MAX_RETRIES = 2           # retry on transient failures
_RETRY_DELAY = 0.5         # seconds between retries
_RECV_BUF = 65536          # 64KB recv buffer


class SandboxError(Exception):
    """Base exception for sandbox operations."""
    pass


class SandboxConnectionError(SandboxError, ConnectionError):
    """Cannot reach the sandbox VM."""
    pass


class SandboxTimeoutError(SandboxError, TimeoutError):
    """Operation timed out."""
    pass


class SandboxClient:
    """Client to the exec agent inside the Firecracker VM.

    Connects via vsock (UDS) by default, falls back to TCP.

    Usage:
        # VSOCK mode (default — no network config needed):
        client = SandboxClient(vsock_uds="/tmp/bunkervm-vsock.sock", vsock_port=8080)

        # TCP mode (when VM has TAP networking):
        client = SandboxClient(host="172.16.0.2", port=8080)

        client.wait_for_health(timeout=30)
        result = client.exec("ls -la /")
    """

    def __init__(
        self,
        vsock_uds: Optional[str] = "/tmp/bunkervm-vsock.sock",
        vsock_port: int = 8080,
        host: Optional[str] = None,
        port: int = 8080,
    ):
        self._vsock_uds = vsock_uds
        self._vsock_port = vsock_port
        self._tcp_host = host
        self._tcp_port = port

        # Determine mode
        if host:
            self._mode = "tcp"
            self._label = f"tcp:{host}:{port}"
        elif vsock_uds:
            self._mode = "vsock"
            self._label = f"vsock:{vsock_uds}:{vsock_port}"
        else:
            raise ValueError("Either vsock_uds or host must be provided")

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def label(self) -> str:
        return self._label

    def exec(
        self,
        command: str,
        timeout: int = 30,
        workdir: str = "/root",
    ) -> dict:
        """Execute a shell command inside the sandbox."""
        return self._request(
            "POST", "/exec",
            {"command": command, "timeout": timeout, "workdir": workdir},
            timeout=timeout + 10,
        )

    def read_file(self, path: str) -> dict:
        """Read a file from the sandbox."""
        return self._request("POST", "/read-file", {"path": path})

    def write_file(
        self,
        path: str,
        content: str,
        mode: str = "overwrite",
        encoding: str = "utf-8",
    ) -> dict:
        """Write a file to the sandbox."""
        return self._request(
            "POST", "/write-file",
            {"path": path, "content": content, "mode": mode, "encoding": encoding},
        )

    def list_dir(self, path: str = "/") -> dict:
        """List directory contents."""
        return self._request("POST", "/list-dir", {"path": path})

    def upload_file(
        self,
        local_path: str,
        remote_path: str,
    ) -> dict:
        """Upload a file from host to sandbox (binary-safe via base64)."""
        import base64
        with open(local_path, "rb") as f:
            data = f.read()
        encoded = base64.b64encode(data).decode("ascii")
        return self._request(
            "POST", "/write-file",
            {"path": remote_path, "content": encoded, "encoding": "base64", "mode": "overwrite"},
        )

    def download_file(self, remote_path: str) -> bytes:
        """Download a file from sandbox to host (returns raw bytes)."""
        import base64
        result = self._request("POST", "/read-file", {"path": remote_path})
        content = result.get("content", "")
        encoding = result.get("encoding", "utf-8")
        if encoding == "base64":
            return base64.b64decode(content)
        return content.encode("utf-8")

    def health(self) -> dict:
        """Health check."""
        return self._request("GET", "/health", timeout=_HEALTH_TIMEOUT)

    def status(self) -> dict:
        """System status."""
        return self._request("GET", "/status", timeout=_HEALTH_TIMEOUT)

    def wait_for_health(self, timeout: int = 60, interval: float = 0.5) -> bool:
        """Block until the exec agent is reachable or timeout expires."""
        deadline = time.monotonic() + timeout
        attempt = 0
        while time.monotonic() < deadline:
            attempt += 1
            try:
                result = self.health()
                if result.get("status") == "ok":
                    elapsed = timeout - (deadline - time.monotonic())
                    logger.info(
                        "Sandbox healthy (%s) after %d attempts (%.1fs)",
                        self._mode, attempt, elapsed,
                    )
                    return True
            except Exception:
                pass
            time.sleep(interval)

        logger.warning("Sandbox health check timed out after %ds", timeout)
        return False

    # ── Transport layer ──

    def _connect(self) -> socket.socket:
        """Create a connected socket to the exec agent."""
        if self._mode == "vsock":
            return self._connect_vsock()
        else:
            return self._connect_tcp()

    def _connect_vsock(self) -> socket.socket:
        """Connect via Firecracker's vsock UDS.

        Protocol:
          1. Connect to the Unix Domain Socket
          2. Send "CONNECT <port>\n"
          3. Receive "OK <port>\n"
          4. Socket is now a transparent stream to the guest
        """
        uds_path = self._vsock_uds
        if not uds_path or not os.path.exists(uds_path):
            raise SandboxConnectionError(
                f"Vsock UDS not found: {uds_path}. Is the VM running?"
            )

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(_CONNECT_TIMEOUT)

        try:
            sock.connect(uds_path)
        except (ConnectionRefusedError, FileNotFoundError, OSError) as e:
            sock.close()
            raise SandboxConnectionError(f"Cannot connect to vsock UDS {uds_path}: {e}")

        # Firecracker CONNECT handshake
        connect_msg = f"CONNECT {self._vsock_port}\n".encode()
        sock.sendall(connect_msg)

        # Read response (expect "OK <port>\n")
        response = b""
        while b"\n" not in response:
            chunk = sock.recv(256)
            if not chunk:
                sock.close()
                raise SandboxConnectionError("Vsock connection closed during handshake")
            response += chunk

        response_str = response.decode("utf-8", errors="replace").strip()
        if not response_str.startswith("OK"):
            sock.close()
            raise SandboxConnectionError(f"Vsock CONNECT failed: {response_str}")

        return sock

    def _connect_tcp(self) -> socket.socket:
        """Connect via TCP (fallback for --network mode)."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(_CONNECT_TIMEOUT)

        try:
            sock.connect((self._tcp_host, self._tcp_port))
        except (ConnectionRefusedError, TimeoutError, OSError) as e:
            sock.close()
            raise SandboxConnectionError(
                f"Cannot reach sandbox at {self._tcp_host}:{self._tcp_port}: {e}"
            )

        return sock

    # ── HTTP-over-socket ──

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[dict] = None,
        timeout: float = _READ_TIMEOUT,
    ) -> dict:
        """Send an HTTP request over the connected socket and parse response."""
        last_error = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                sock = self._connect()
                sock.settimeout(timeout)

                # Build HTTP request
                lines = [f"{method} {path} HTTP/1.0"]
                lines.append("Accept: application/json")
                lines.append("Connection: close")

                if body is not None:
                    data = json.dumps(body).encode("utf-8")
                    lines.append("Content-Type: application/json")
                    lines.append(f"Content-Length: {len(data)}")
                else:
                    data = None

                # Send request
                request = "\r\n".join(lines) + "\r\n\r\n"
                sock.sendall(request.encode("utf-8"))
                if data:
                    sock.sendall(data)

                # Read full response
                raw = b""
                while True:
                    chunk = sock.recv(_RECV_BUF)
                    if not chunk:
                        break
                    raw += chunk

                sock.close()

                # Parse HTTP response
                if b"\r\n\r\n" not in raw:
                    raise SandboxError(f"Malformed HTTP response from sandbox")

                header_bytes, _, resp_body = raw.partition(b"\r\n\r\n")
                status_line = header_bytes.split(b"\r\n")[0].decode("utf-8")
                # e.g. "HTTP/1.0 200 OK"
                parts = status_line.split(" ", 2)
                status_code = int(parts[1]) if len(parts) >= 2 else 0

                result = json.loads(resp_body.decode("utf-8"))

                if status_code >= 500 and attempt < _MAX_RETRIES:
                    last_error = SandboxError(f"HTTP {status_code}: {result}")
                    time.sleep(_RETRY_DELAY)
                    continue

                return result

            except (SandboxConnectionError, ConnectionError) as e:
                last_error = SandboxConnectionError(str(e))
                if attempt < _MAX_RETRIES:
                    time.sleep(_RETRY_DELAY)
                    continue
                raise

            except TimeoutError:
                raise SandboxTimeoutError(
                    f"{method} {path} timed out after {timeout}s"
                )

            except json.JSONDecodeError as e:
                raise SandboxError(f"Invalid JSON response: {e}")

            except Exception as e:
                last_error = SandboxError(f"Unexpected error: {e}")
                if attempt < _MAX_RETRIES:
                    time.sleep(_RETRY_DELAY)
                    continue

        raise last_error
