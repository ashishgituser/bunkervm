"""
BunkerVM CrewAI Integration — secure sandbox tools for CrewAI agents.

Usage:
    from bunkervm.crewai import BunkerVMCrewTools
    from crewai import Agent, Task, Crew

    tools = BunkerVMCrewTools()

    coder = Agent(
        role="Software Engineer",
        goal="Write and test code in a secure sandbox",
        tools=tools.get_tools(),
        backstory="You write code inside a hardware-isolated VM.",
    )
    task = Task(
        description="Write a Python script that calculates fibonacci numbers and run it",
        agent=coder,
        expected_output="The fibonacci sequence results",
    )
    crew = Crew(agents=[coder], tasks=[task])
    result = crew.kickoff()
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Type

from bunkervm.sandbox_client import SandboxClient

logger = logging.getLogger("bunkervm.crewai")

_DEFAULT_VSOCK_UDS = "/tmp/bunkervm-vsock.sock"
_DEFAULT_VSOCK_PORT = 8080


def _make_tool_classes(client: SandboxClient, command_timeout: int = 30):
    """Create CrewAI tool classes bound to a SandboxClient.

    Returns tool classes lazily so crewai_tools import is deferred.
    """
    from crewai.tools import BaseTool
    from pydantic import BaseModel, Field

    # ── Input schemas ──

    class RunCommandInput(BaseModel):
        command: str = Field(description="Shell command to execute inside the sandbox")

    class WriteFileInput(BaseModel):
        path: str = Field(description="Absolute path for the file (e.g., /tmp/script.py)")
        content: str = Field(description="Text content to write")

    class ReadFileInput(BaseModel):
        path: str = Field(description="Absolute path to the file")

    class ListDirectoryInput(BaseModel):
        path: str = Field(default="/", description="Directory path to list")

    class UploadFileInput(BaseModel):
        local_path: str = Field(description="Path to file on the host")
        remote_path: str = Field(description="Destination path inside the VM")

    class DownloadFileInput(BaseModel):
        remote_path: str = Field(description="Path to file inside the VM")
        local_path: str = Field(description="Destination path on the host")

    # ── Tool classes ──

    class RunCommandTool(BaseTool):
        name: str = "run_command"
        description: str = (
            "Run a shell command inside the secure BunkerVM sandbox. "
            "The sandbox is a full Linux environment with hardware isolation."
        )
        args_schema: Type[BaseModel] = RunCommandInput

        def _run(self, command: str) -> str:
            logger.info("\u2192 run_command: %s", command[:120])
            r = client.exec(command, timeout=command_timeout)
            stdout = r.get("stdout", "")
            stderr = r.get("stderr", "")
            exit_code = r.get("exit_code", -1)
            duration = r.get("duration_ms", 0)
            output = stdout
            if stderr:
                output += f"\n[stderr] {stderr}" if output else stderr
            if exit_code != 0:
                output += f"\n[exit_code: {exit_code}]"
            logger.info("  \u2190 %s (%dms)", "OK" if exit_code == 0 else f"EXIT {exit_code}", duration)
            return output or "(no output)"

    class WriteFileTool(BaseTool):
        name: str = "write_file"
        description: str = "Write a file inside the BunkerVM sandbox. Creates parent dirs automatically."
        args_schema: Type[BaseModel] = WriteFileInput

        def _run(self, path: str, content: str) -> str:
            logger.info("\u2192 write_file: %s (%d bytes)", path, len(content))
            r = client.write_file(path, content)
            size = r.get("bytes_written", r.get("size", 0))
            return f"Wrote {size} bytes to {path}"

    class ReadFileTool(BaseTool):
        name: str = "read_file"
        description: str = "Read the contents of a file from the BunkerVM sandbox."
        args_schema: Type[BaseModel] = ReadFileInput

        def _run(self, path: str) -> str:
            logger.info("\u2192 read_file: %s", path)
            r = client.read_file(path)
            return r.get("content", "(empty file)")

    class ListDirectoryTool(BaseTool):
        name: str = "list_directory"
        description: str = "List files and directories at a path in the BunkerVM sandbox."
        args_schema: Type[BaseModel] = ListDirectoryInput

        def _run(self, path: str = "/") -> str:
            logger.info("\u2192 list_directory: %s", path)
            r = client.list_dir(path)
            entries = r.get("entries", [])
            if not entries:
                return f"(empty directory: {path})"
            lines = []
            for e in entries:
                name = e.get("name", "?")
                kind = e.get("type", "?")
                suffix = "/" if kind == "directory" else ""
                size = e.get("size", "")
                size_str = f"  ({size} bytes)" if size and kind == "file" else ""
                lines.append(f"  {name}{suffix}{size_str}")
            return f"{path}:\n" + "\n".join(lines)

    class UploadFileTool(BaseTool):
        name: str = "upload_file"
        description: str = "Upload a file from the host into the BunkerVM sandbox."
        args_schema: Type[BaseModel] = UploadFileInput

        def _run(self, local_path: str, remote_path: str) -> str:
            logger.info("\u2192 upload_file: %s -> %s", local_path, remote_path)
            if not os.path.exists(local_path):
                return f"[ERROR] Local file not found: {local_path}"
            try:
                result = client.upload_file(local_path, remote_path)
                size = result.get("size", os.path.getsize(local_path))
                return f"Uploaded {local_path} -> {remote_path} ({size} bytes)"
            except Exception as e:
                return f"[ERROR] Upload failed: {e}"

    class DownloadFileTool(BaseTool):
        name: str = "download_file"
        description: str = "Download a file from the BunkerVM sandbox to the host."
        args_schema: Type[BaseModel] = DownloadFileInput

        def _run(self, remote_path: str, local_path: str) -> str:
            logger.info("\u2192 download_file: %s -> %s", remote_path, local_path)
            try:
                data = client.download_file(remote_path)
                os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
                with open(local_path, "wb") as f:
                    f.write(data)
                return f"Downloaded {remote_path} -> {local_path} ({len(data)} bytes)"
            except Exception as e:
                return f"[ERROR] Download failed: {e}"

    return [
        RunCommandTool(),
        WriteFileTool(),
        ReadFileTool(),
        ListDirectoryTool(),
        UploadFileTool(),
        DownloadFileTool(),
    ]


class BunkerVMCrewTools:
    """CrewAI-compatible tool provider for BunkerVM.

    Provides tools for: run_command, write_file, read_file,
    list_directory, upload_file, download_file

    All operations execute inside a hardware-isolated Firecracker MicroVM.
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
        logger.info("BunkerVMCrewTools connected (%s)", self._client.label)

    @property
    def client(self) -> SandboxClient:
        return self._client

    def get_tools(self) -> list:
        """Return CrewAI-compatible tool instances."""
        return _make_tool_classes(self._client, self._command_timeout)

    def health(self) -> bool:
        """Check if the BunkerVM sandbox is reachable."""
        try:
            r = self._client.health()
            return r.get("status") == "ok"
        except Exception:
            return False
