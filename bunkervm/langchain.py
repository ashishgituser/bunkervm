"""
BunkerVM LangChain/LangGraph Integration — drop-in secure sandbox tools.

Usage:
    from bunkervm.langchain import BunkerVMToolkit
    from langchain_openai import ChatOpenAI
    from langgraph.prebuilt import create_react_agent

    toolkit = BunkerVMToolkit()          # auto-connects to running VM
    agent = create_react_agent(ChatOpenAI(model="gpt-4o"), toolkit.get_tools())
    result = agent.invoke({"messages": [("human", "Write and run hello.py")]})
"""

from __future__ import annotations

import logging
from typing import Optional

from langchain_core.tools import tool as langchain_tool

from bunkervm.sandbox_client import SandboxClient

logger = logging.getLogger("bunkervm.langchain")

# Default vsock path (matches BunkerVM server default)
_DEFAULT_VSOCK_UDS = "/tmp/bunkervm-vsock.sock"
_DEFAULT_VSOCK_PORT = 8080


class BunkerVMToolkit:
    """LangChain-compatible toolkit that routes all tool calls to BunkerVM.

    Provides: run_command, write_file, read_file, list_dir

    All operations execute inside a hardware-isolated Firecracker MicroVM —
    zero risk to the host system.

    Args:
        vsock_uds: Path to BunkerVM vsock socket. Default: /tmp/bunkervm-vsock.sock
        vsock_port: Vsock port (default 8080)
        host: TCP host for network mode (alternative to vsock)
        port: TCP port for network mode
        command_timeout: Default timeout for command execution (seconds)
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
        logger.info("BunkerVMToolkit connected (%s)", self._client.label)

    @property
    def client(self) -> SandboxClient:
        """Direct access to the underlying SandboxClient."""
        return self._client

    def get_tools(self) -> list:
        """Return LangChain-compatible tools bound to this VM.

        Returns a list of tools ready to pass to create_react_agent(),
        ToolNode(), or bind_tools().
        """
        client = self._client
        timeout = self._command_timeout

        @langchain_tool
        def run_command(command: str) -> str:
            """Run a shell command inside the secure BunkerVM sandbox.
            Use this to execute any bash command, run scripts, install packages, etc.
            The sandbox is a full Linux environment with Python, network access, and
            a real filesystem — but hardware-isolated from the host."""
            r = client.exec(command, timeout=timeout)
            stdout = r.get("stdout", "")
            stderr = r.get("stderr", "")
            exit_code = r.get("exit_code", -1)
            output = stdout
            if stderr:
                output += f"\n[stderr] {stderr}" if output else stderr
            if exit_code != 0:
                output += f"\n[exit_code: {exit_code}]"
            return output or "(no output)"

        @langchain_tool
        def write_file(path: str, content: str) -> str:
            """Write a file inside the secure BunkerVM sandbox.
            Creates parent directories automatically. Use absolute paths like /tmp/script.py."""
            r = client.write_file(path, content)
            bytes_written = r.get("bytes_written", 0)
            return f"Wrote {bytes_written} bytes to {path}"

        @langchain_tool
        def read_file(path: str) -> str:
            """Read the contents of a file from the BunkerVM sandbox."""
            r = client.read_file(path)
            return r.get("content", "(empty file)")

        @langchain_tool
        def list_directory(path: str = "/") -> str:
            """List files and directories at a path in the BunkerVM sandbox."""
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

        return [run_command, write_file, read_file, list_directory]

    def health(self) -> bool:
        """Check if the BunkerVM sandbox is reachable."""
        try:
            r = self._client.health()
            return r.get("status") == "ok"
        except Exception:
            return False
