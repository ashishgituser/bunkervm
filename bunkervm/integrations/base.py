"""
BunkerVM Integrations Base — shared tool logic for all frameworks.

Every framework integration (LangChain, OpenAI Agents SDK, CrewAI) inherits
from BunkerVMToolsBase, which provides:

    1. Auto-boot mode — no args = spins up a Firecracker VM automatically.
    2. Connection mode — pass vsock_uds or host/port to attach to a running VM.
    3. Shared tool implementations (_run_command, _write_file, etc.) that each
       framework adapter wraps with its own decorator/schema style.
    4. Lifecycle management (start/stop, context manager, cleanup).
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger("bunkervm.integrations")


class BunkerVMToolsBase:
    """Shared base for all framework integrations.

    Constructor modes:
        - **No args (auto-boot):** Spins up a Firecracker microVM automatically.
          The VM is destroyed when `stop()` is called or the context manager exits.
        - **vsock_uds:** Connect to a pre-running VM via vsock UDS.
        - **host / port:** Connect to a pre-running VM via TCP.

    Args:
        vsock_uds: Path to BunkerVM vsock socket (e.g. /tmp/bunkervm-vsock.sock).
        vsock_port: Vsock port (default 8080).
        host: TCP host for network mode (alternative to vsock).
        port: TCP port for network mode.
        command_timeout: Default timeout for command execution (seconds).
        cpus: vCPUs for auto-booted VM (ignored when connecting to existing VM).
        memory: Memory in MB for auto-booted VM.
        network: Allow internet in auto-booted VM.
    """

    def __init__(
        self,
        *,
        vsock_uds: Optional[str] = None,
        vsock_port: int = 8080,
        host: Optional[str] = None,
        port: int = 8080,
        command_timeout: int = 30,
        # Auto-boot VM options (only used when no vsock_uds/host given)
        cpus: int = 1,
        memory: int = 512,
        network: bool = True,
    ):
        from bunkervm.sandbox_client import SandboxClient

        self._sandbox = None  # only set in auto-boot mode

        if host:
            # TCP connection to pre-running VM
            self._client = SandboxClient(host=host, port=port)
        elif vsock_uds:
            # Vsock connection to pre-running VM
            self._client = SandboxClient(vsock_uds=vsock_uds, vsock_port=vsock_port)
        else:
            # Auto-boot mode: spin up a disposable Sandbox VM
            from bunkervm.runtime import Sandbox

            self._sandbox = Sandbox(
                cpus=cpus,
                memory=memory,
                network=network,
                timeout=command_timeout,
                quiet=True,
            )
            self._sandbox.start()
            self._client = self._sandbox.client

        self._command_timeout = command_timeout
        logger.info("%s ready (%s)", type(self).__name__, self._client.label)

    # ── Properties ──

    @property
    def client(self):
        """Direct access to the SandboxClient."""
        return self._client

    # ── Lifecycle ──

    def stop(self) -> None:
        """Destroy the auto-booted VM (no-op if using external connection)."""
        if self._sandbox is not None:
            self._sandbox.stop()
            self._sandbox = None

    def health(self) -> bool:
        """Check if the BunkerVM sandbox is reachable."""
        try:
            r = self._client.health()
            return r.get("status") == "ok"
        except Exception:
            return False

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    def __del__(self) -> None:
        try:
            self.stop()
        except Exception:
            pass

    # ── Shared tool implementations ──
    # These are framework-agnostic. Each integration wraps them with its
    # own decorator / schema style (e.g. @langchain_tool, @function_tool,
    # CrewAI BaseTool subclass).

    def _run_command(self, command: str) -> str:
        """Execute a shell command inside the sandbox."""
        logger.info("→ run_command: %s", command[:120])
        r = self._client.exec(command, timeout=self._command_timeout)
        stdout = r.get("stdout", "")
        stderr = r.get("stderr", "")
        exit_code = r.get("exit_code", -1)
        duration = r.get("duration_ms", 0)
        output = stdout
        if stderr:
            output += f"\n[stderr] {stderr}" if output else stderr
        if exit_code != 0:
            output += f"\n[exit_code: {exit_code}]"
        logger.info(
            "  ← %s (%dms, %d bytes)",
            "OK" if exit_code == 0 else f"EXIT {exit_code}",
            duration,
            len(stdout),
        )
        return output or "(no output)"

    def _write_file(self, path: str, content: str) -> str:
        """Write a file inside the sandbox."""
        logger.info("→ write_file: %s (%d bytes)", path, len(content))
        r = self._client.write_file(path, content)
        size = r.get("bytes_written", r.get("size", 0))
        return f"Wrote {size} bytes to {path}"

    def _read_file(self, path: str) -> str:
        """Read a file from the sandbox."""
        logger.info("→ read_file: %s", path)
        r = self._client.read_file(path)
        return r.get("content", "(empty file)")

    def _list_directory(self, path: str = "/") -> str:
        """List files and directories inside the sandbox."""
        logger.info("→ list_directory: %s", path)
        r = self._client.list_dir(path)
        entries = r.get("entries", [])
        if not entries:
            return f"(empty directory: {path})"
        lines = []
        for e in entries:
            name = e.get("name", "?")
            kind = e.get("type", "?")
            size = e.get("size", "")
            suffix = "/" if kind == "directory" else ""
            size_str = f"  ({size} bytes)" if size and kind == "file" else ""
            lines.append(f"  {name}{suffix}{size_str}")
        return f"{path}:\n" + "\n".join(lines)

    def _upload_file(self, local_path: str, remote_path: str) -> str:
        """Upload a file from the host into the sandbox."""
        logger.info("→ upload_file: %s -> %s", local_path, remote_path)
        if not os.path.exists(local_path):
            return f"[ERROR] Local file not found: {local_path}"
        try:
            result = self._client.upload_file(local_path, remote_path)
            size = result.get("size", os.path.getsize(local_path))
            logger.info("  ← uploaded %d bytes", size)
            return f"Uploaded {local_path} -> {remote_path} ({size} bytes)"
        except Exception as e:
            return f"[ERROR] Upload failed: {e}"

    def _download_file(self, remote_path: str, local_path: str) -> str:
        """Download a file from the sandbox to the host."""
        logger.info("→ download_file: %s -> %s", remote_path, local_path)
        try:
            data = self._client.download_file(remote_path)
            os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
            with open(local_path, "wb") as f:
                f.write(data)
            logger.info("  ← downloaded %d bytes", len(data))
            return f"Downloaded {remote_path} -> {local_path} ({len(data)} bytes)"
        except Exception as e:
            return f"[ERROR] Download failed: {e}"
