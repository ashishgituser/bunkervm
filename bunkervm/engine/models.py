"""
BunkerVM Engine Models — Request/response dataclasses for the REST API.

All API data flows through these models for consistency. JSON serialization
uses stdlib json + dataclass asdict().
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Optional


def _new_id() -> str:
    """Generate a short unique sandbox ID (8 hex chars)."""
    return uuid.uuid4().hex[:8]


def _now() -> float:
    """Current timestamp."""
    return time.time()


# ── Request Models ──


@dataclass
class SandboxCreateRequest:
    """Request body for POST /sandboxes."""
    name: Optional[str] = None
    cpus: Optional[int] = None
    memory: Optional[int] = None
    network: Optional[bool] = None

    @classmethod
    def from_dict(cls, data: dict) -> "SandboxCreateRequest":
        return cls(
            name=data.get("name"),
            cpus=data.get("cpus"),
            memory=data.get("memory"),
            network=data.get("network"),
        )


@dataclass
class ExecRequest:
    """Request body for POST /sandboxes/{id}/exec."""
    command: str = ""
    timeout: int = 30
    workdir: str = "/root"

    @classmethod
    def from_dict(cls, data: dict) -> "ExecRequest":
        return cls(
            command=data.get("command", ""),
            timeout=data.get("timeout", 30),
            workdir=data.get("workdir", "/root"),
        )


@dataclass
class WriteFileRequest:
    """Request body for POST /sandboxes/{id}/write-file."""
    path: str = ""
    content: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "WriteFileRequest":
        return cls(
            path=data.get("path", ""),
            content=data.get("content", ""),
        )


# ── Response Models ──


@dataclass
class SandboxInfo:
    """Info about a running sandbox, returned by list and get endpoints."""
    id: str
    name: str
    status: str  # "running", "starting", "stopped", "error"
    created_at: float
    cpus: int
    memory_mb: int
    network: bool
    pid: Optional[int] = None
    vsock: Optional[str] = None
    vm_ip: Optional[str] = None
    uptime_seconds: float = 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["uptime_seconds"] = round(time.time() - self.created_at, 1)
        return d


@dataclass
class EngineStatus:
    """Response for GET /engine/status."""
    status: str = "running"  # "running", "stopping"
    version: str = ""
    platform: str = ""
    sandbox_count: int = 0
    max_sandboxes: int = 0
    uptime_seconds: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExecResult:
    """Response for POST /sandboxes/{id}/exec."""
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    duration_ms: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ApiError:
    """Standard error response."""
    error: str
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
