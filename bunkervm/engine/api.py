"""
BunkerVM Engine API — REST API route handlers.

Uses stdlib http.server — no external HTTP framework dependencies.
All routes speak JSON. The API server runs on localhost:9551.

Routes:
    GET  /engine/status                 Engine health, version, sandbox count
    POST /engine/stop                   Graceful shutdown
    GET  /dashboard                     BunkerDesktop web UI
    GET  /dashboard/{file}              Dashboard static assets
    GET  /sandboxes                     List all running sandboxes
    POST /sandboxes                     Create a new sandbox
    GET  /sandboxes/{id}                Get sandbox details
    DELETE /sandboxes/{id}              Destroy a sandbox
    POST /sandboxes/{id}/exec           Execute command
    POST /sandboxes/{id}/write-file     Write file
    GET  /sandboxes/{id}/read-file      Read file (?path=...)
    GET  /sandboxes/{id}/list-dir       List directory (?path=...)
    GET  /sandboxes/{id}/status         VM health + resource usage
    POST /sandboxes/{id}/reset          Reset sandbox (destroy + recreate)
"""

from __future__ import annotations

import json
import logging
import os
import platform
import re
import time
from http.server import BaseHTTPRequestHandler
from typing import TYPE_CHECKING, Any, Callable, Optional
from urllib.parse import parse_qs, urlparse

from .models import (
    ApiError,
    EngineStatus,
    ExecRequest,
    ExecResult,
    SandboxCreateRequest,
    SandboxInfo,
    WriteFileRequest,
    _new_id,
)

if TYPE_CHECKING:
    from .daemon import EngineDaemon

logger = logging.getLogger("bunkervm.engine.api")


class EngineAPIHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the engine REST API.

    The daemon instance is accessible via self.server.daemon (set by EngineDaemon).
    Routes are matched via _ROUTES table to avoid scattered regex matching.
    """

    # Suppress default access log — we do our own logging
    def log_message(self, format, *args):
        logger.debug("API %s", format % args)

    @property
    def daemon(self) -> "EngineDaemon":
        return self.server.daemon  # type: ignore[attr-defined]

    # ── Route Table ──
    # Each entry: (method, regex_pattern, handler_name, needs_body)
    # Sandbox ID is captured via group(1) where applicable.

    _GET_ROUTES = [
        (re.compile(r"^/engine/status$"), "_handle_engine_status"),
        (re.compile(r"^/engine/logs$"), "_handle_engine_logs"),
        (re.compile(r"^/sandboxes$"), "_handle_list_sandboxes"),
        (re.compile(r"^/sandboxes/([^/]+)$"), "_handle_get_sandbox"),
        (re.compile(r"^/sandboxes/([^/]+)/read-file$"), "_handle_read_file"),
        (re.compile(r"^/sandboxes/([^/]+)/list-dir$"), "_handle_list_dir"),
        (re.compile(r"^/sandboxes/([^/]+)/status$"), "_handle_sandbox_status"),
    ]

    _POST_ROUTES = [
        (re.compile(r"^/engine/stop$"), "_handle_engine_stop"),
        (re.compile(r"^/sandboxes$"), "_handle_create_sandbox"),
        (re.compile(r"^/sandboxes/([^/]+)/exec$"), "_handle_exec"),
        (re.compile(r"^/sandboxes/([^/]+)/write-file$"), "_handle_write_file"),
        (re.compile(r"^/sandboxes/([^/]+)/reset$"), "_handle_reset_sandbox"),
    ]

    _DELETE_ROUTES = [
        (re.compile(r"^/sandboxes/([^/]+)$"), "_handle_destroy_sandbox"),
    ]

    # ── HTTP Methods ──

    def do_GET(self):
        """Handle GET — serves dashboard static files and API routes."""
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        # Serve dashboard UI at /dashboard and its assets
        if path == "/dashboard" or path.startswith("/dashboard/"):
            self._serve_dashboard(path)
            return

        self._dispatch(self._GET_ROUTES, with_body=False)

    def do_POST(self):
        self._dispatch(self._POST_ROUTES, with_body=True)

    def do_DELETE(self):
        self._dispatch(self._DELETE_ROUTES, with_body=False)

    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def _dispatch(self, routes: list, with_body: bool = False):
        """Match path against route table and dispatch to handler."""
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)

        for pattern, handler_name in routes:
            match = pattern.match(path)
            if match:
                handler = getattr(self, handler_name)
                try:
                    args = list(match.groups())
                    if with_body:
                        args.append(self._read_body())
                    else:
                        args.append(query)
                    handler(*args)
                except Exception as e:
                    logger.exception("Unhandled error in %s %s", self.command, path)
                    self._send_error(500, "Internal server error", str(e))
                return

        self._send_error(404, "Not found", f"No route for {self.command} {path}")

    # ── Engine Routes ──

    def _handle_engine_status(self, _query: dict):
        from bunkervm import __version__
        status = EngineStatus(
            status="running",
            version=__version__,
            platform=platform.platform(),
            sandbox_count=self.daemon.sandbox_count,
            max_sandboxes=self.daemon.config.max_sandboxes,
            uptime_seconds=round(time.time() - self.daemon.start_time, 1),
        )
        self._send_json(200, status.to_dict())

    def _handle_engine_logs(self, query: dict):
        """Return recent engine log entries.

        Query params:
            after: sequence number — only return entries after this (for polling)
            limit: max entries to return (default 200)
        """
        after_seq = int(query.get("after", ["0"])[0])
        limit = int(query.get("limit", ["200"])[0])
        entries = self.daemon.log_handler.get_logs(after_seq=after_seq, limit=limit)
        last_seq = entries[-1]["seq"] if entries else after_seq
        self._send_json(200, {"logs": entries, "last_seq": last_seq})

    def _handle_engine_stop(self, _body: dict):
        """Initiate graceful shutdown."""
        self._send_json(200, {"status": "stopping", "message": "Engine shutting down..."})
        # Schedule shutdown after response is sent
        import threading
        threading.Thread(target=self.daemon.stop, daemon=True).start()

    # ── Sandbox CRUD Routes ──

    def _handle_list_sandboxes(self, _query: dict):
        sandboxes = self.daemon.list_sandboxes()
        self._send_json(200, {"sandboxes": [s.to_dict() for s in sandboxes]})

    def _handle_create_sandbox(self, body: dict):
        req = SandboxCreateRequest.from_dict(body)

        try:
            info = self.daemon.create_sandbox(
                name=req.name,
                cpus=req.cpus,
                memory=req.memory,
                network=req.network,
            )
            logger.info("Created sandbox %s (%s)", info.id, info.name)
            self._send_json(201, info.to_dict())
        except ValueError as e:
            self._send_error(409, "Conflict", str(e))
        except Exception as e:
            self._send_error(500, "Failed to create sandbox", str(e))

    def _handle_get_sandbox(self, sandbox_id: str, _query: dict):
        info = self.daemon.get_sandbox(sandbox_id)
        if info is None:
            self._send_error(404, "Sandbox not found", f"No sandbox with id '{sandbox_id}'")
            return
        self._send_json(200, info.to_dict())

    def _handle_destroy_sandbox(self, sandbox_id: str, _query: dict):
        ok = self.daemon.destroy_sandbox(sandbox_id)
        if ok:
            logger.info("Destroyed sandbox %s", sandbox_id)
            self._send_json(200, {"status": "destroyed", "id": sandbox_id})
        else:
            self._send_error(404, "Sandbox not found", f"No sandbox with id '{sandbox_id}'")

    # ── Sandbox Operation Routes ──

    def _handle_exec(self, sandbox_id: str, body: dict):
        client = self.daemon.get_client(sandbox_id)
        if client is None:
            self._send_error(404, "Sandbox not found", f"No sandbox with id '{sandbox_id}'")
            return

        req = ExecRequest.from_dict(body)
        if not req.command:
            self._send_error(400, "Bad request", "Missing 'command' field")
            return

        info = self.daemon.get_sandbox(sandbox_id)
        sb_name = info.name if info else sandbox_id
        logger.info("[%s] exec: %s", sb_name, req.command[:120])

        try:
            result = client.exec(
                command=req.command,
                timeout=req.timeout,
                workdir=req.workdir,
            )
            exit_code = result.get('exit_code', '?')
            logger.info("[%s] exec done (exit=%s)", sb_name, exit_code)
            self._send_json(200, result)
        except Exception as e:
            logger.error("[%s] exec failed: %s", sb_name, e)
            self._send_error(500, "Execution failed", str(e))

    def _handle_write_file(self, sandbox_id: str, body: dict):
        client = self.daemon.get_client(sandbox_id)
        if client is None:
            self._send_error(404, "Sandbox not found", f"No sandbox with id '{sandbox_id}'")
            return

        req = WriteFileRequest.from_dict(body)
        if not req.path:
            self._send_error(400, "Bad request", "Missing 'path' field")
            return

        info = self.daemon.get_sandbox(sandbox_id)
        sb_name = info.name if info else sandbox_id
        logger.info("[%s] write-file: %s", sb_name, req.path)

        try:
            result = client.write_file(req.path, req.content)
            self._send_json(200, result)
        except Exception as e:
            logger.error("[%s] write-file failed: %s", sb_name, e)
            self._send_error(500, "Write failed", str(e))

    def _handle_read_file(self, sandbox_id: str, query: dict):
        client = self.daemon.get_client(sandbox_id)
        if client is None:
            self._send_error(404, "Sandbox not found", f"No sandbox with id '{sandbox_id}'")
            return

        file_path = query.get("path", ["/"])[0]
        info = self.daemon.get_sandbox(sandbox_id)
        sb_name = info.name if info else sandbox_id
        logger.info("[%s] read-file: %s", sb_name, file_path)

        try:
            result = client.read_file(file_path)
            self._send_json(200, result)
        except Exception as e:
            logger.error("[%s] read-file failed: %s", sb_name, e)
            self._send_error(500, "Read failed", str(e))

    def _handle_list_dir(self, sandbox_id: str, query: dict):
        client = self.daemon.get_client(sandbox_id)
        if client is None:
            self._send_error(404, "Sandbox not found", f"No sandbox with id '{sandbox_id}'")
            return

        dir_path = query.get("path", ["/"])[0]
        try:
            result = client.list_dir(dir_path)
            self._send_json(200, result)
        except Exception as e:
            self._send_error(500, "List directory failed", str(e))

    def _handle_sandbox_status(self, sandbox_id: str, _query: dict):
        client = self.daemon.get_client(sandbox_id)
        if client is None:
            self._send_error(404, "Sandbox not found", f"No sandbox with id '{sandbox_id}'")
            return

        try:
            result = client.status()
            self._send_json(200, result)
        except Exception as e:
            self._send_error(500, "Status check failed", str(e))

    def _handle_reset_sandbox(self, sandbox_id: str, _body: dict):
        try:
            info = self.daemon.reset_sandbox(sandbox_id)
            if info is None:
                self._send_error(404, "Sandbox not found", f"No sandbox with id '{sandbox_id}'")
                return
            logger.info("Reset sandbox %s", sandbox_id)
            self._send_json(200, info.to_dict())
        except Exception as e:
            self._send_error(500, "Reset failed", str(e))

    # ── HTTP Helpers ──

    # Dashboard static file content types
    _MIME_TYPES = {
        ".html": "text/html",
        ".css": "text/css",
        ".js": "application/javascript",
        ".json": "application/json",
        ".png": "image/png",
        ".svg": "image/svg+xml",
        ".ico": "image/x-icon",
    }

    def _serve_dashboard(self, path: str):
        """Serve BunkerDesktop web UI static files.

        Searches for dashboard assets in this order:
          1. BUNKERVM_DASHBOARD_DIR env var (set by Windows installer)
          2. bundled inside Python package (bunkervm/dashboard_assets/)
          3. development checkout (project_root/desktop/src/)
        Falls back to index.html for SPA routing.
        """
        dashboard_dir = self._find_dashboard_dir()
        if dashboard_dir is None:
            self._send_error(
                404, "Dashboard not found",
                "Desktop UI not installed. Set BUNKERVM_DASHBOARD_DIR or "
                "reinstall the package.",
            )
            return

        # Strip /dashboard prefix to get relative file path
        rel = path.replace("/dashboard", "", 1).lstrip("/")
        if not rel:
            rel = "index.html"

        # Security: prevent path traversal
        safe_path = os.path.normpath(rel)
        if safe_path.startswith("..") or os.path.isabs(safe_path):
            self._send_error(403, "Forbidden", "Path traversal not allowed")
            return

        file_path = os.path.join(dashboard_dir, safe_path)

        # SPA fallback: if file doesn't exist, serve index.html
        if not os.path.isfile(file_path):
            file_path = os.path.join(dashboard_dir, "index.html")

        try:
            with open(file_path, "rb") as f:
                content = f.read()

            ext = os.path.splitext(file_path)[1].lower()
            content_type = self._MIME_TYPES.get(ext, "application/octet-stream")

            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(content)
        except IOError:
            self._send_error(500, "File read error", f"Could not read {safe_path}")

    def _read_body(self) -> dict:
        """Read and parse JSON request body. Returns {} for empty bodies."""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return {}
        raw = self.rfile.read(content_length)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def _find_dashboard_dir():
        """Locate the dashboard static files directory.

        Search order:
          1. BUNKERVM_DASHBOARD_DIR env var
          2. Bundled inside package: bunkervm/dashboard_assets/
          3. Dev checkout: project_root/desktop/src/
        Returns the path or None.
        """
        # 1. Explicit env override (set by Windows installer / BunkerDesktop.cmd)
        env_dir = os.environ.get("BUNKERVM_DASHBOARD_DIR")
        if env_dir and os.path.isdir(env_dir):
            return env_dir

        # 2. Bundled inside the installed package
        pkg_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        bundled = os.path.join(pkg_dir, "dashboard_assets")
        if os.path.isdir(bundled) and os.path.isfile(os.path.join(bundled, "index.html")):
            return bundled

        # 3. Development checkout (bunkervm/engine/api.py -> bunkervm -> project root)
        project_root = os.path.dirname(pkg_dir)
        dev_dir = os.path.join(project_root, "desktop", "src")
        if os.path.isdir(dev_dir) and os.path.isfile(os.path.join(dev_dir, "index.html")):
            return dev_dir

        return None

    def _send_json(self, status_code: int, data: Any):
        """Send a JSON response."""
        body = json.dumps(data, default=str, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status_code: int, error: str, detail: str = ""):
        """Send a JSON error response."""
        err = ApiError(error=error, detail=detail)
        self._send_json(status_code, err.to_dict())
