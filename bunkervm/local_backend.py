"""
BunkerVM Local Backend — zero-isolation subprocess execution.

No Firecracker, no VM, no container. Code runs as a plain subprocess on
the host, inside a private per-instance directory. This exists so the
record / restore / diff workflow can be tried in seconds on machines that
can't run Firecracker (macOS, bare Windows without WSL2) — it deliberately
does NOT provide any of BunkerVM's isolation guarantees.

Never selected automatically by Sandbox()/run_code(). Only used when
explicitly requested via backend="local" (Sandbox(backend="local"),
`bunkervm demo --local`, `bunkervm run --local`).

Path mapping: absolute paths handed to THIS CLIENT's own methods
(write_file, read_file, exec's workdir, upload/download) are transparently
mapped onto this instance's own private directory, mirroring the
guest-filesystem convention the VM/engine backends use.

Important limitation: this only covers paths BunkerVM itself resolves.
Code executed via exec()/run() is a real subprocess with the real host
filesystem — if that code opens an absolute path itself (e.g. Python doing
`open("/output/result.csv")`), it hits the real host path, not the
sandbox, and won't appear in filesystem traces. Relative paths (resolved
against the mapped workdir) and Sandbox.upload()/download() are traced
correctly; hardcoded absolute guest-style paths in your own code are not
redirected. There is no way to fix this without a real filesystem
boundary — which is precisely what this backend doesn't have.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Optional

logger = logging.getLogger("bunkervm.local")

_SNAPSHOTS_DIR = os.path.join(os.path.expanduser("~"), ".bunkervm", "snapshots")
_MAX_OUTPUT = 65536

# BunkerVM's own control files — excluded from traces the same way
# rootfs/bunkervm/exec_agent.py excludes them for VM mode, otherwise every
# step's trace is dominated by the namespace pickle rewriting itself.
_TRACE_EXCLUDE_NAMES = {"_ns.pkl", "_code.py", "_runner.py", "_run.sh", "_run.js"}

# Interpreter and test-runner caches. These are written by the toolchain, not
# chosen by whatever is driving the sandbox, and they swamp the file counts —
# a single `pytest` run can "create" a dozen files the agent never touched.
_TRACE_EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".git"}


def _snapshot_dir(root: str) -> dict:
    """Walk a directory and record {real_path: (mtime, size)} for every file,
    skipping BunkerVM's own control files and toolchain caches."""
    snapshot = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _TRACE_EXCLUDE_DIRS]
        for fname in filenames:
            if fname in _TRACE_EXCLUDE_NAMES:
                continue
            fpath = os.path.join(dirpath, fname)
            try:
                st = os.stat(fpath)
                snapshot[fpath] = (st.st_mtime, st.st_size)
            except OSError:
                pass
    return snapshot


def _to_virtual(root: str, real_path: str) -> str:
    """Convert a real path under root back into the "/tmp/..."-style virtual
    path callers gave us, so trace output reads the same as VM-mode traces."""
    rel = os.path.relpath(real_path, root)
    return "/" + rel.replace(os.sep, "/")


def _diff_dir(root: str, pre_snapshot: dict) -> dict:
    """Compare current directory state to a pre-execution snapshot.

    Same shape as rootfs/bunkervm/exec_agent.py's _diff_filesystem, scoped
    to this sandbox's own private directory instead of a VM's whole disk.
    """
    post_snapshot = _snapshot_dir(root)

    created, modified, deleted = [], [], []
    bytes_written = 0

    for path, (mtime, size) in post_snapshot.items():
        if path not in pre_snapshot:
            created.append({"path": _to_virtual(root, path), "size": size})
            bytes_written += size
        else:
            old_mtime, old_size = pre_snapshot[path]
            if mtime != old_mtime or size != old_size:
                modified.append(
                    {"path": _to_virtual(root, path), "old_size": old_size, "new_size": size}
                )
                bytes_written += max(0, size - old_size)

    for path in pre_snapshot:
        if path not in post_snapshot:
            deleted.append({"path": _to_virtual(root, path), "size": pre_snapshot[path][1]})

    return {
        "files_created": created,
        "files_modified": modified,
        "files_deleted": deleted,
        # atime-based "files read" tracking is unreliable across platforms
        # (Windows often disables atime updates entirely) — omitted rather
        # than reported inaccurately.
        "files_read": [],
        "bytes_written": bytes_written,
    }


class LocalClient:
    """No-isolation client: runs commands as real subprocesses on the host.

    Duck-typed to the same interface as SandboxClient/EngineBackedClient
    (exec, write_file, read_file, list_dir, upload_file, download_file,
    health, wait_for_health) so Sandbox works unchanged regardless of
    backend. Adds create_snapshot/restore_snapshot for the record/restore
    workflow — these snapshot the namespace + working directory, not real
    VM memory or process state.
    """

    def __init__(self, root: Optional[str] = None, snapshots_dir: Optional[str] = None):
        self._root = os.path.abspath(root or tempfile.mkdtemp(prefix="bunkervm-local-"))
        os.makedirs(self._root, exist_ok=True)
        self._snapshots_dir = snapshots_dir or _SNAPSHOTS_DIR
        self.label = f"local:{self._root}"
        self.mode = "local"

    @property
    def root(self) -> str:
        return self._root

    def map_path(self, path: str) -> str:
        """Map a virtual absolute path onto this sandbox's private directory.

        Idempotent: a path that's already inside this sandbox's root is
        returned unchanged, so callers can pass either the original virtual
        path ("/tmp/foo") or an already-resolved real path interchangeably.
        """
        abs_path = os.path.abspath(path)
        try:
            if os.path.commonpath([abs_path, self._root]) == self._root:
                return abs_path
        except ValueError:
            pass  # different drives on Windows — definitely not already-mapped

        rel = path.lstrip("/\\")
        real = os.path.normpath(os.path.join(self._root, rel))
        if os.path.commonpath([os.path.abspath(real), self._root]) != self._root:
            raise ValueError(f"Path escapes sandbox root: {path}")
        return real

    # ── Exec ──

    def exec(
        self,
        command: str,
        timeout: int = 30,
        workdir: str = "/root",
        trace: bool = False,
    ) -> dict:
        real_workdir = self.map_path(workdir)
        os.makedirs(real_workdir, exist_ok=True)

        # runtime.py always issues "python3 <script>" for Python execution
        # (matching the Alpine guest convention) — rewrite to the interpreter
        # actually running BunkerVM, since a bare "python3" isn't guaranteed
        # on the host (notably Windows). The trailing script path is also
        # mapped (idempotently — a fine no-op if it's already a real path),
        # so this works whether callers pass the virtual "/tmp/..." form or
        # an already-resolved path.
        run_command = command
        if command.startswith("python3 "):
            rest = command[len("python3 ") :]
            if rest and not rest.lstrip().startswith("-"):
                script_arg, _, extra = rest.partition(" ")
                rest = f'"{self.map_path(script_arg)}"' + (f" {extra}" if extra else "")
            run_command = f'"{sys.executable}" {rest}'

        pre_snapshot = _snapshot_dir(self._root) if trace else None
        start = time.monotonic()
        try:
            result = subprocess.run(
                run_command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=real_workdir,
                env={**os.environ, "HOME": self.map_path("/root"), "TMPDIR": self.map_path("/tmp")},
            )
            elapsed = time.monotonic() - start
            response = {
                "exit_code": result.returncode,
                "stdout": result.stdout[:_MAX_OUTPUT],
                "stderr": result.stderr[:_MAX_OUTPUT],
                "duration_ms": round(elapsed * 1000, 1),
            }
        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - start
            response = {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Command timed out after {timeout}s",
                "duration_ms": round(elapsed * 1000, 1),
                "timed_out": True,
            }

        if trace:
            response["trace"] = _diff_dir(self._root, pre_snapshot)
        return response

    # ── Files ──

    def write_file(
        self, path: str, content, mode: str = "overwrite", encoding: str = "utf-8"
    ) -> dict:
        real = self.map_path(path)
        os.makedirs(os.path.dirname(real), exist_ok=True)
        if encoding == "base64":
            with open(real, "ab" if mode == "append" else "wb") as f:
                f.write(base64.b64decode(content))
        else:
            with open(real, "a" if mode == "append" else "w", encoding="utf-8") as f:
                f.write(content)
        return {"path": path, "size": os.path.getsize(real), "written": True}

    def read_file(self, path: str) -> dict:
        real = self.map_path(path)
        if not os.path.exists(real):
            return {"error": f"not found: {path}"}
        try:
            with open(real, "r", encoding="utf-8") as f:
                content = f.read()
            return {
                "path": path,
                "content": content,
                "size": os.path.getsize(real),
                "encoding": "utf-8",
            }
        except UnicodeDecodeError:
            with open(real, "rb") as f:
                content = base64.b64encode(f.read()).decode("ascii")
            return {
                "path": path,
                "content": content,
                "size": os.path.getsize(real),
                "encoding": "base64",
            }

    def list_dir(self, path: str = "/") -> dict:
        real = self.map_path(path)
        if not os.path.isdir(real):
            return {"path": path, "count": 0, "entries": []}
        entries = []
        for name in sorted(os.listdir(real)):
            full = os.path.join(real, name)
            is_dir = os.path.isdir(full)
            entries.append(
                {
                    "name": name,
                    "type": "directory" if is_dir else "file",
                    "size": None if is_dir else os.path.getsize(full),
                }
            )
        return {"path": path, "count": len(entries), "entries": entries}

    def upload_file(self, local_path: str, remote_path: str) -> dict:
        real = self.map_path(remote_path)
        os.makedirs(os.path.dirname(real), exist_ok=True)
        shutil.copy2(local_path, real)
        return {"path": remote_path, "size": os.path.getsize(real), "written": True}

    def download_file(self, remote_path: str) -> bytes:
        real = self.map_path(remote_path)
        with open(real, "rb") as f:
            return f.read()

    # ── Health ──

    def health(self) -> dict:
        return {"status": "ok", "agent": "bunkervm-local", "version": "1.0"}

    def wait_for_health(self, timeout: int = 30, interval: float = 0.5) -> bool:
        return True  # no boot/handshake step — the "sandbox" is just a directory

    def status(self) -> dict:
        return {"status": "running", "backend": "local", "root": self._root}

    # ── Snapshot / restore (namespace + workdir — not real VM state) ──

    def create_snapshot(self, name: str) -> str:
        """Copy this sandbox's working directory to a named snapshot.

        This is a filesystem + namespace snapshot, not a VM snapshot: no
        memory or process state, unlike Firecracker (direct) mode.
        """
        snap_dir = os.path.join(self._snapshots_dir, f"{name}-local")
        if os.path.exists(snap_dir):
            shutil.rmtree(snap_dir)
        os.makedirs(snap_dir, exist_ok=True)
        shutil.copytree(self._root, os.path.join(snap_dir, "workdir"))
        with open(os.path.join(snap_dir, "meta.json"), "w") as f:
            json.dump({"name": name, "backend": "local", "created_at": time.time()}, f)
        return snap_dir

    def restore_snapshot(self, name: str) -> None:
        """Restore this sandbox's working directory from a named snapshot."""
        snap_workdir = os.path.join(self._snapshots_dir, f"{name}-local", "workdir")
        if not os.path.isdir(snap_workdir):
            raise RuntimeError(f"Local snapshot not found: {name}")
        if os.path.exists(self._root):
            shutil.rmtree(self._root)
        shutil.copytree(snap_workdir, self._root)

    def cleanup(self) -> None:
        """Remove this sandbox's private working directory."""
        shutil.rmtree(self._root, ignore_errors=True)
