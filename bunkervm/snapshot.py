"""
BunkerVM Snapshot Manager — Firecracker snapshot create/restore.

Uses Firecracker's built-in snapshot API to:
  1. Pause a running VM
  2. Save memory + CPU state to disk
  3. Restore a new VM from that snapshot in <100ms

The snapshot files:
  - vmstate: CPU registers, device state (~1MB)
  - memory:  Full VM RAM (CoW-friendly, sparse file)

Snapshot storage: ~/.bunkervm/snapshots/<name>/
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import socket
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("bunkervm.snapshot")

_SNAPSHOTS_DIR = os.path.join(os.path.expanduser("~"), ".bunkervm", "snapshots")


@dataclass
class SnapshotInfo:
    """Metadata for a stored snapshot."""

    name: str
    vmstate_path: str
    memory_path: str
    rootfs_path: str
    created_at: float
    vcpu_count: int
    mem_size_mib: int

    @property
    def exists(self) -> bool:
        return (
            os.path.exists(self.vmstate_path)
            and os.path.exists(self.memory_path)
            and os.path.exists(self.rootfs_path)
        )


class FirecrackerAPIClient:
    """Minimal HTTP client for Firecracker's Unix socket API.

    Firecracker exposes a REST API on the --api-sock Unix socket.
    BunkerVM already creates this socket but never sends requests to it.
    This client enables snapshot operations (pause, create, load).
    """

    def __init__(self, socket_path: str):
        self._socket_path = socket_path

    def _request(self, method: str, path: str, body: Optional[dict] = None) -> dict:
        """Send an HTTP request to the Firecracker API socket."""
        if not os.path.exists(self._socket_path):
            raise RuntimeError(f"Firecracker API socket not found: {self._socket_path}")

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(10)
        try:
            sock.connect(self._socket_path)

            # Build HTTP request
            lines = [f"{method} {path} HTTP/1.1", "Host: localhost", "Accept: application/json"]
            if body is not None:
                data = json.dumps(body).encode("utf-8")
                lines.append("Content-Type: application/json")
                lines.append(f"Content-Length: {len(data)}")
            else:
                data = None

            request = "\r\n".join(lines) + "\r\n\r\n"
            sock.sendall(request.encode("utf-8"))
            if data:
                sock.sendall(data)

            # Read response
            raw = b""
            while True:
                try:
                    chunk = sock.recv(65536)
                    if not chunk:
                        break
                    raw += chunk
                    # Check if we have complete response
                    if b"\r\n\r\n" in raw:
                        header_part, _, body_part = raw.partition(b"\r\n\r\n")
                        # Check Content-Length
                        for line in header_part.split(b"\r\n"):
                            if line.lower().startswith(b"content-length:"):
                                expected = int(line.split(b":")[1].strip())
                                if len(body_part) >= expected:
                                    raw = header_part + b"\r\n\r\n" + body_part[:expected]
                                    break
                        else:
                            # No content-length, check for empty body (204)
                            status_line = header_part.split(b"\r\n")[0]
                            if b"204" in status_line:
                                break
                            continue
                        break
                except socket.timeout:
                    break

            # Parse response
            if b"\r\n\r\n" not in raw:
                # Might be a 204 No Content
                if b"204" in raw:
                    return {}
                raise RuntimeError(f"Malformed response from Firecracker API: {raw[:200]}")

            header_bytes, _, resp_body = raw.partition(b"\r\n\r\n")
            status_line = header_bytes.split(b"\r\n")[0].decode("utf-8")
            parts = status_line.split(" ", 2)
            status_code = int(parts[1]) if len(parts) >= 2 else 0

            if status_code >= 400:
                error_msg = resp_body.decode("utf-8", errors="replace") if resp_body else ""
                raise RuntimeError(f"Firecracker API error {status_code}: {error_msg}")

            if not resp_body.strip():
                return {}
            return json.loads(resp_body.decode("utf-8"))
        finally:
            sock.close()

    def pause_vm(self) -> None:
        """Pause the VM (required before snapshot)."""
        self._request("PATCH", "/vm", {"state": "Paused"})

    def resume_vm(self) -> None:
        """Resume a paused VM."""
        self._request("PATCH", "/vm", {"state": "Resumed"})

    def create_snapshot(self, vmstate_path: str, memory_path: str) -> None:
        """Create a snapshot of the running (paused) VM."""
        self._request(
            "PUT",
            "/snapshot/create",
            {
                "snapshot_type": "Full",
                "snapshot_path": vmstate_path,
                "mem_file_path": memory_path,
            },
        )

    def load_snapshot(self, vmstate_path: str, memory_path: str) -> None:
        """Load a VM from a previously created snapshot."""
        self._request(
            "PUT",
            "/snapshot/load",
            {
                "snapshot_path": vmstate_path,
                "mem_file_path": memory_path,
            },
        )


class SnapshotManager:
    """Manages snapshot lifecycle — create, list, restore, delete.

    Snapshots are stored in ~/.bunkervm/snapshots/<name>/ with:
      - vmstate.snap   (CPU + device state)
      - memory.snap    (VM RAM — sparse file)
      - rootfs.ext4    (copy of rootfs at snapshot time)
      - meta.json      (metadata: vcpu, memory, timestamp)
    """

    def __init__(self, snapshots_dir: str = _SNAPSHOTS_DIR):
        self._dir = snapshots_dir
        os.makedirs(self._dir, exist_ok=True)

    def create(
        self,
        name: str,
        fc_api_socket: str,
        rootfs_path: str,
        vcpu_count: int,
        mem_size_mib: int,
    ) -> SnapshotInfo:
        """Create a snapshot from a running VM.

        Steps:
          1. Pause the VM
          2. Create snapshot (vmstate + memory)
          3. Copy rootfs
          4. Save metadata
          5. Resume the VM
        """
        snap_dir = os.path.join(self._dir, name)
        os.makedirs(snap_dir, exist_ok=True)

        vmstate_path = os.path.join(snap_dir, "vmstate.snap")
        memory_path = os.path.join(snap_dir, "memory.snap")
        rootfs_snap = os.path.join(snap_dir, "rootfs.ext4")

        api = FirecrackerAPIClient(fc_api_socket)

        logger.info("Creating snapshot '%s'...", name)
        t0 = time.monotonic()

        # 1. Pause VM
        api.pause_vm()

        # 2. Create snapshot files
        api.create_snapshot(vmstate_path, memory_path)

        # 3. Copy rootfs (frozen since VM is paused)
        shutil.copy2(rootfs_path, rootfs_snap)

        # 4. Save metadata
        meta = {
            "name": name,
            "created_at": time.time(),
            "vcpu_count": vcpu_count,
            "mem_size_mib": mem_size_mib,
        }
        with open(os.path.join(snap_dir, "meta.json"), "w") as f:
            json.dump(meta, f, indent=2)

        # 5. Resume VM
        api.resume_vm()

        elapsed = time.monotonic() - t0
        logger.info("Snapshot '%s' created in %.1fms", name, elapsed * 1000)

        return SnapshotInfo(
            name=name,
            vmstate_path=vmstate_path,
            memory_path=memory_path,
            rootfs_path=rootfs_snap,
            created_at=meta["created_at"],
            vcpu_count=vcpu_count,
            mem_size_mib=mem_size_mib,
        )

    def get(self, name: str) -> Optional[SnapshotInfo]:
        """Load snapshot metadata by name. Returns None if not found."""
        snap_dir = os.path.join(self._dir, name)
        meta_path = os.path.join(snap_dir, "meta.json")
        if not os.path.exists(meta_path):
            return None
        with open(meta_path) as f:
            meta = json.load(f)
        info = SnapshotInfo(
            name=meta["name"],
            vmstate_path=os.path.join(snap_dir, "vmstate.snap"),
            memory_path=os.path.join(snap_dir, "memory.snap"),
            rootfs_path=os.path.join(snap_dir, "rootfs.ext4"),
            created_at=meta["created_at"],
            vcpu_count=meta["vcpu_count"],
            mem_size_mib=meta["mem_size_mib"],
        )
        return info if info.exists else None

    def list(self) -> list[SnapshotInfo]:
        """List all available snapshots."""
        results = []
        if not os.path.isdir(self._dir):
            return results
        for name in sorted(os.listdir(self._dir)):
            info = self.get(name)
            if info:
                results.append(info)
        return results

    def delete(self, name: str) -> bool:
        """Delete a snapshot by name."""
        snap_dir = os.path.join(self._dir, name)
        if os.path.isdir(snap_dir):
            shutil.rmtree(snap_dir)
            logger.info("Deleted snapshot '%s'", name)
            return True
        return False

    def has(self, name: str) -> bool:
        """Check if a snapshot exists and is complete."""
        return self.get(name) is not None
