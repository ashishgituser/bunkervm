"""
Engine-backed sandbox client for MCP server.

Implements the same interface as SandboxClient but proxies all operations
through the BunkerVM engine REST API (localhost:9551). Auto-creates a
sandbox on first use and reuses it for the session.

This allows the MCP server to connect to an already-running BunkerDesktop
engine instead of booting its own VM.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request

logger = logging.getLogger("bunkervm.engine_client")


class EngineSandboxClient:
    """Sandbox client backed by the BunkerVM engine REST API.

    Drop-in replacement for SandboxClient. Auto-creates a sandbox on first
    use and proxies exec/read/write/list operations through the engine.
    """

    def __init__(
        self,
        engine_url: str = "http://localhost:9551",
        sandbox_name: str = "mcp-sandbox",
        cpus: int = 1,
        memory: int = 512,
        network: bool = True,
    ):
        self._engine_url = engine_url.rstrip("/")
        self._sandbox_name = sandbox_name
        self._sandbox_id = None
        self._cpus = cpus
        self._memory = memory
        self._network = network
        self._mode = "engine"
        self._label = f"engine@{engine_url}"

        # Eagerly create sandbox so it appears on the dashboard immediately
        try:
            self._ensure_sandbox()
        except Exception as e:
            logger.warning("Could not create sandbox eagerly: %s (will retry on first use)", e)

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def label(self) -> str:
        return self._label

    @property
    def sandbox_id(self) -> str | None:
        return self._sandbox_id

    def _api(self, method: str, path: str, body: dict | None = None,
             timeout: int = 30) -> dict:
        """Make an HTTP request to the engine API."""
        url = f"{self._engine_url}{path}"
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")

        req = urllib.request.Request(
            url, method=method, data=data,
            headers={"Content-Type": "application/json"} if data else {},
        )
        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
            return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body_text = e.read().decode("utf-8", errors="replace")
            try:
                err = json.loads(body_text)
                raise ConnectionError(
                    err.get("detail", err.get("error", f"HTTP {e.code}"))
                )
            except (json.JSONDecodeError, ConnectionError):
                if isinstance(body_text, str) and "detail" not in body_text:
                    raise ConnectionError(f"HTTP {e.code}: {body_text[:200]}")
                raise
        except urllib.error.URLError as e:
            raise ConnectionError(f"Engine unreachable: {e.reason}")

    def _ensure_sandbox(self) -> str:
        """Ensure a sandbox exists, creating one if needed. Returns sandbox ID."""
        if self._sandbox_id:
            # Verify it still exists
            try:
                self._api("GET", f"/sandboxes/{self._sandbox_id}", timeout=5)
                return self._sandbox_id
            except ConnectionError:
                logger.info("Sandbox %s gone, will create new one",
                            self._sandbox_id)
                self._sandbox_id = None

        # Check if our named sandbox already exists
        try:
            data = self._api("GET", "/sandboxes", timeout=5)
            for sb in data.get("sandboxes", []):
                if sb.get("name") == self._sandbox_name:
                    self._sandbox_id = sb["id"]
                    logger.info("Reusing existing sandbox: %s (%s)",
                                self._sandbox_name, self._sandbox_id)
                    return self._sandbox_id
        except ConnectionError:
            pass

        # Create new sandbox
        logger.info("Creating sandbox '%s' via engine...", self._sandbox_name)
        result = self._api("POST", "/sandboxes", {
            "name": self._sandbox_name,
            "cpus": self._cpus,
            "memory": self._memory,
            "network": self._network,
        }, timeout=60)

        self._sandbox_id = result["id"]
        logger.info("Sandbox created: %s (%s)", self._sandbox_name,
                     self._sandbox_id)
        return self._sandbox_id

    # ── SandboxClient interface ──

    def exec(self, command: str, timeout: int = 30,
             workdir: str = "/root") -> dict:
        """Execute a shell command inside the sandbox."""
        sid = self._ensure_sandbox()
        return self._api("POST", f"/sandboxes/{sid}/exec", {
            "command": command,
            "timeout": timeout,
            "workdir": workdir,
        }, timeout=timeout + 15)

    def read_file(self, path: str) -> dict:
        """Read a file from the sandbox."""
        sid = self._ensure_sandbox()
        from urllib.parse import quote
        return self._api(
            "GET",
            f"/sandboxes/{sid}/read-file?path={quote(path, safe='')}",
            timeout=15,
        )

    def write_file(self, path: str, content: str, mode: str = "overwrite",
                   encoding: str = "utf-8") -> dict:
        """Write a file to the sandbox."""
        sid = self._ensure_sandbox()
        return self._api("POST", f"/sandboxes/{sid}/write-file", {
            "path": path,
            "content": content,
            "mode": mode,
            "encoding": encoding,
        }, timeout=15)

    def list_dir(self, path: str = "/") -> dict:
        """List directory contents."""
        sid = self._ensure_sandbox()
        from urllib.parse import quote
        return self._api(
            "GET",
            f"/sandboxes/{sid}/list-dir?path={quote(path, safe='')}",
            timeout=15,
        )

    def upload_file(self, local_path: str, remote_path: str) -> dict:
        """Upload a file from host to sandbox."""
        import base64
        with open(local_path, "rb") as f:
            data = f.read()
        encoded = base64.b64encode(data).decode("ascii")
        return self.write_file(remote_path, encoded, encoding="base64")

    def download_file(self, remote_path: str) -> bytes:
        """Download a file from sandbox."""
        import base64
        result = self.read_file(remote_path)
        content = result.get("content", "")
        encoding = result.get("encoding", "utf-8")
        if encoding == "base64":
            return base64.b64decode(content)
        return content.encode("utf-8")

    def health(self) -> dict:
        """Health check — verify engine is reachable."""
        try:
            self._api("GET", "/engine/status", timeout=3)
            return {"status": "ok"}
        except Exception:
            return {"status": "error"}

    def status(self) -> dict:
        """System status from engine."""
        try:
            return self._api("GET", "/engine/status", timeout=5)
        except ConnectionError:
            return {"status": "offline"}

    def wait_for_health(self, timeout: int = 60, interval: float = 1.0) -> bool:
        """Wait for the engine to become reachable."""
        deadline = time.monotonic() + timeout
        attempt = 0
        while time.monotonic() < deadline:
            attempt += 1
            try:
                result = self.health()
                if result.get("status") == "ok":
                    logger.info("Engine reachable after %d attempts", attempt)
                    return True
            except Exception:
                pass
            time.sleep(interval)
        logger.warning("Engine not reachable after %ds", timeout)
        return False

    def reset(self) -> dict:
        """Reset the sandbox (destroy + recreate)."""
        if self._sandbox_id:
            try:
                result = self._api(
                    "POST", f"/sandboxes/{self._sandbox_id}/reset", timeout=60
                )
                return result
            except ConnectionError:
                pass
        # If reset fails, destroy and recreate
        self.destroy()
        self._ensure_sandbox()
        return {"status": "ok", "message": "Sandbox reset"}

    def destroy(self) -> None:
        """Destroy the sandbox."""
        if self._sandbox_id:
            try:
                self._api("DELETE", f"/sandboxes/{self._sandbox_id}", timeout=15)
            except ConnectionError:
                pass
            self._sandbox_id = None
