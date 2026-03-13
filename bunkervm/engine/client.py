"""
BunkerVM Engine Client — Thin HTTP client for the engine REST API.

This is the SDK-side counterpart to engine/api.py. All sandbox operations
go through localhost:9551 instead of directly launching Firecracker.

Uses only stdlib (urllib) — no external HTTP libraries.

Usage:
    from bunkervm.engine.client import EngineClient

    engine = EngineClient()         # localhost:9551
    sb = engine.create_sandbox(name="my-sandbox")
    result = engine.exec(sb["id"], "echo hello")
    engine.destroy_sandbox(sb["id"])
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from .config import DEFAULT_ENGINE_PORT

logger = logging.getLogger("bunkervm.engine.client")


class EngineClient:
    """HTTP client for the BunkerVM engine daemon REST API.

    All methods raise EngineAPIError on non-2xx responses.

    Args:
        host: Engine bind address. Default: 127.0.0.1
        port: Engine port. Default: 9551
    """

    def __init__(self, host: str = "127.0.0.1", port: int = DEFAULT_ENGINE_PORT):
        self.base_url = f"http://{host}:{port}"

    # ── Engine operations ──

    def status(self) -> Dict[str, Any]:
        """GET /engine/status — engine health, version, sandbox count."""
        return self._get("/engine/status")

    def stop_engine(self) -> Dict[str, Any]:
        """POST /engine/stop — graceful shutdown."""
        return self._post("/engine/stop")

    # ── Sandbox CRUD ──

    def create_sandbox(
        self,
        name: Optional[str] = None,
        cpus: Optional[int] = None,
        memory: Optional[int] = None,
        network: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """POST /sandboxes — create a new sandbox. Returns SandboxInfo dict."""
        body: Dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if cpus is not None:
            body["cpus"] = cpus
        if memory is not None:
            body["memory"] = memory
        if network is not None:
            body["network"] = network
        return self._post("/sandboxes", body)

    def list_sandboxes(self) -> List[Dict[str, Any]]:
        """GET /sandboxes — list all running sandboxes."""
        result = self._get("/sandboxes")
        return result.get("sandboxes", [])

    def get_sandbox(self, sandbox_id: str) -> Dict[str, Any]:
        """GET /sandboxes/{id} — get sandbox details."""
        return self._get(f"/sandboxes/{sandbox_id}")

    def destroy_sandbox(self, sandbox_id: str) -> Dict[str, Any]:
        """DELETE /sandboxes/{id} — destroy a sandbox."""
        return self._request("DELETE", f"/sandboxes/{sandbox_id}")

    # ── Sandbox operations ──

    def exec(
        self,
        sandbox_id: str,
        command: str,
        timeout: int = 30,
        workdir: str = "/root",
    ) -> Dict[str, Any]:
        """POST /sandboxes/{id}/exec — execute a command."""
        return self._post(f"/sandboxes/{sandbox_id}/exec", {
            "command": command,
            "timeout": timeout,
            "workdir": workdir,
        })

    def write_file(
        self,
        sandbox_id: str,
        path: str,
        content: str,
    ) -> Dict[str, Any]:
        """POST /sandboxes/{id}/write-file — write a file in the sandbox."""
        return self._post(f"/sandboxes/{sandbox_id}/write-file", {
            "path": path,
            "content": content,
        })

    def read_file(self, sandbox_id: str, path: str) -> Dict[str, Any]:
        """GET /sandboxes/{id}/read-file?path=... — read a file."""
        return self._get(f"/sandboxes/{sandbox_id}/read-file?path={path}")

    def list_dir(self, sandbox_id: str, path: str = "/") -> Dict[str, Any]:
        """GET /sandboxes/{id}/list-dir?path=... — list a directory."""
        return self._get(f"/sandboxes/{sandbox_id}/list-dir?path={path}")

    def sandbox_status(self, sandbox_id: str) -> Dict[str, Any]:
        """GET /sandboxes/{id}/status — sandbox health/resource info."""
        return self._get(f"/sandboxes/{sandbox_id}/status")

    def reset_sandbox(self, sandbox_id: str) -> Dict[str, Any]:
        """POST /sandboxes/{id}/reset — destroy and recreate."""
        return self._post(f"/sandboxes/{sandbox_id}/reset")

    # ── Upload / Download ──

    def upload_file(
        self,
        sandbox_id: str,
        local_path: str,
        remote_path: str,
    ) -> Dict[str, Any]:
        """Upload a file: read locally, write via engine API."""
        with open(local_path, "r") as f:
            content = f.read()
        return self.write_file(sandbox_id, remote_path, content)

    def download_file(self, sandbox_id: str, remote_path: str) -> str:
        """Download a file: read via engine API, return content."""
        result = self.read_file(sandbox_id, remote_path)
        return result.get("content", "")

    # ── HTTP helpers ──

    def _get(self, path: str) -> Dict[str, Any]:
        return self._request("GET", path)

    def _post(self, path: str, body: Optional[Dict] = None) -> Dict[str, Any]:
        return self._request("POST", path, body)

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Make an HTTP request to the engine API."""
        url = f"{self.base_url}{path}"

        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"} if data else {},
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read().decode("utf-8")
                if raw:
                    return json.loads(raw)
                return {}
        except urllib.error.HTTPError as e:
            body_text = ""
            try:
                body_text = e.read().decode("utf-8")
            except Exception:
                pass
            detail = ""
            try:
                detail = json.loads(body_text).get("detail", body_text)
            except Exception:
                detail = body_text
            raise EngineAPIError(e.code, detail) from e
        except urllib.error.URLError as e:
            raise EngineConnectionError(
                f"Cannot connect to engine at {self.base_url}: {e.reason}"
            ) from e


class EngineAPIError(Exception):
    """Raised when the engine API returns a non-2xx status."""

    def __init__(self, status_code: int, detail: str = ""):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Engine API error {status_code}: {detail}")


class EngineConnectionError(Exception):
    """Raised when the engine daemon is not reachable."""
    pass


class EngineBackedClient:
    """Duck-typed SandboxClient adapter that routes through the engine REST API.

    Provides the same interface as SandboxClient (exec, write_file, read_file,
    etc.) so that Sandbox and BunkerVMToolsBase work unchanged regardless of
    whether the sandbox is managed locally or via the engine daemon.

    This is the Adapter pattern — existing code that expects a SandboxClient
    gets one of these instead when the engine is in use.
    """

    def __init__(self, engine: EngineClient, sandbox_id: str):
        self._engine = engine
        self._sandbox_id = sandbox_id
        self.label = f"engine:{sandbox_id}"

    def exec(self, command: str, timeout: int = 30, **kwargs) -> dict:
        return self._engine.exec(self._sandbox_id, command, timeout=timeout)

    def write_file(self, path: str, content: str) -> dict:
        return self._engine.write_file(self._sandbox_id, path, content)

    def read_file(self, path: str) -> dict:
        return self._engine.read_file(self._sandbox_id, path)

    def list_dir(self, path: str = "/") -> dict:
        return self._engine.list_dir(self._sandbox_id, path)

    def health(self) -> dict:
        try:
            return self._engine.sandbox_status(self._sandbox_id)
        except Exception:
            return {"status": "error"}

    def wait_for_health(self, timeout: int = 30) -> bool:
        """Engine already waits for health during create, so just verify."""
        try:
            status = self._engine.sandbox_status(self._sandbox_id)
            return status.get("status") in ("running", "ok")
        except Exception:
            return False

    def upload_file(self, local_path: str, remote_path: str) -> dict:
        return self._engine.upload_file(self._sandbox_id, local_path, remote_path)

    def download_file(self, remote_path: str) -> bytes:
        content = self._engine.download_file(self._sandbox_id, remote_path)
        if isinstance(content, str):
            return content.encode("utf-8")
        return content
