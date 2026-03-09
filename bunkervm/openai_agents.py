"""
BunkerVM OpenAI Agents SDK Integration — drop-in secure sandbox tools.

Works with the OpenAI Agents SDK (openai-agents / agents-sdk).

Usage:
    from bunkervm.openai_agents import BunkerVMTools
    from agents import Agent, Runner

    tools = BunkerVMTools()
    agent = Agent(
        name="coder",
        instructions="You write and run code in a secure sandbox.",
        tools=tools.get_tools(),
    )
    result = Runner.run_sync(agent, "Write a hello world script and run it")
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from bunkervm.sandbox_client import SandboxClient

logger = logging.getLogger("bunkervm.openai_agents")

_DEFAULT_VSOCK_UDS = "/tmp/bunkervm-vsock.sock"
_DEFAULT_VSOCK_PORT = 8080


class BunkerVMTools:
    """OpenAI Agents SDK-compatible tool provider for BunkerVM.

    Provides: run_command, write_file, read_file, list_directory,
              upload_file, download_file

    All operations execute inside a hardware-isolated Firecracker MicroVM.

    Args:
        vsock_uds: Path to BunkerVM vsock socket
        vsock_port: Vsock port (default 8080)
        host: TCP host for network mode
        port: TCP port for network mode
        command_timeout: Default command execution timeout in seconds
    """

    def __init__(
        self,
        vsock_uds: Optional[str] = _DEFAULT_VSOCK_UDS,
        vsock_port: int = _DEFAULT_VSOCK_PORT,
        host: Optional[str] = None,
        port: int = 8080,
        command_timeout: int = 30,
    ):
        if host:
            self._client = SandboxClient(host=host, port=port)
        else:
            self._client = SandboxClient(vsock_uds=vsock_uds, vsock_port=vsock_port)
        self._command_timeout = command_timeout
        logger.info("BunkerVMTools connected (%s)", self._client.label)

    @property
    def client(self) -> SandboxClient:
        return self._client

    def get_tools(self) -> list:
        """Return OpenAI Agents SDK-compatible function tools.

        Returns a list of tool definitions using the @function_tool decorator
        from the agents SDK.
        """
        from agents import function_tool

        client = self._client
        timeout = self._command_timeout

        @function_tool
        def run_command(command: str) -> str:
            """Run a shell command inside the secure BunkerVM sandbox.
            The sandbox is a full Linux environment with hardware isolation.
            Use this for running scripts, installing packages, processing data, etc."""
            logger.info("\u2192 run_command: %s", command[:120])
            r = client.exec(command, timeout=timeout)
            stdout = r.get("stdout", "")
            stderr = r.get("stderr", "")
            exit_code = r.get("exit_code", -1)
            duration = r.get("duration_ms", 0)
            output = stdout
            if stderr:
                output += f"\n[stderr] {stderr}" if output else stderr
            if exit_code != 0:
                output += f"\n[exit_code: {exit_code}]"
            logger.info("  \u2190 %s (%dms, %d bytes)",
                        "OK" if exit_code == 0 else f"EXIT {exit_code}",
                        duration, len(stdout))
            return output or "(no output)"

        @function_tool
        def write_file(path: str, content: str) -> str:
            """Write a file inside the secure BunkerVM sandbox.
            Creates parent directories automatically. Use absolute paths."""
            logger.info("\u2192 write_file: %s (%d bytes)", path, len(content))
            r = client.write_file(path, content)
            size = r.get("bytes_written", r.get("size", 0))
            return f"Wrote {size} bytes to {path}"

        @function_tool
        def read_file(path: str) -> str:
            """Read the contents of a file from the BunkerVM sandbox."""
            logger.info("\u2192 read_file: %s", path)
            r = client.read_file(path)
            return r.get("content", "(empty file)")

        @function_tool
        def list_directory(path: str = "/") -> str:
            """List files and directories at a path in the BunkerVM sandbox."""
            logger.info("\u2192 list_directory: %s", path)
            r = client.list_dir(path)
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

        @function_tool
        def upload_file(local_path: str, remote_path: str) -> str:
            """Upload a file from the host into the BunkerVM sandbox."""
            logger.info("\u2192 upload_file: %s -> %s", local_path, remote_path)
            if not os.path.exists(local_path):
                return f"[ERROR] Local file not found: {local_path}"
            try:
                result = client.upload_file(local_path, remote_path)
                size = result.get("size", os.path.getsize(local_path))
                return f"Uploaded {local_path} -> {remote_path} ({size} bytes)"
            except Exception as e:
                return f"[ERROR] Upload failed: {e}"

        @function_tool
        def download_file(remote_path: str, local_path: str) -> str:
            """Download a file from the BunkerVM sandbox to the host."""
            logger.info("\u2192 download_file: %s -> %s", remote_path, local_path)
            try:
                data = client.download_file(remote_path)
                os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
                with open(local_path, "wb") as f:
                    f.write(data)
                return f"Downloaded {remote_path} -> {local_path} ({len(data)} bytes)"
            except Exception as e:
                return f"[ERROR] Download failed: {e}"

        return [run_command, write_file, read_file, list_directory, upload_file, download_file]

    def health(self) -> bool:
        """Check if the BunkerVM sandbox is reachable."""
        try:
            r = self._client.health()
            return r.get("status") == "ok"
        except Exception:
            return False
