"""
BunkerVM OpenAI Agents SDK Integration — drop-in secure sandbox tools.

Usage (auto-boot — zero config):
    from bunkervm.openai_agents import BunkerVMTools
    from agents import Agent, Runner

    tools = BunkerVMTools()              # auto-boots a Firecracker VM
    agent = Agent(
        name="coder",
        instructions="You write and run code in a secure sandbox.",
        tools=tools.get_tools(),
    )
    result = Runner.run_sync(agent, "Write a hello world script and run it")
    tools.stop()                         # destroy VM when done

Usage (attach to running VM):
    tools = BunkerVMTools(vsock_uds="/tmp/bunkervm-vsock.sock")
    tools = BunkerVMTools(host="172.16.0.2", port=8080)

Requires: pip install bunkervm[openai-agents]
"""

from __future__ import annotations

from bunkervm.integrations.base import BunkerVMToolsBase


class BunkerVMTools(BunkerVMToolsBase):
    """OpenAI Agents SDK-compatible tool provider for BunkerVM.

    Provides: run_command, write_file, read_file, list_directory,
              upload_file, download_file

    All operations execute inside a hardware-isolated Firecracker MicroVM.

    Modes:
        - ``BunkerVMTools()`` — auto-boots a VM (zero config).
        - ``BunkerVMTools(vsock_uds=...)`` — attach to a running VM via vsock.
        - ``BunkerVMTools(host=..., port=...)`` — attach via TCP.

    Args:
        vsock_uds: Path to BunkerVM vsock socket (omit to auto-boot).
        vsock_port: Vsock port (default 8080).
        host: TCP host for network mode.
        port: TCP port for network mode.
        command_timeout: Default command execution timeout in seconds.
        cpus: vCPUs for auto-booted VM.
        memory: Memory in MB for auto-booted VM.
        network: Allow internet in auto-booted VM.
    """

    def get_tools(self) -> list:
        """Return OpenAI Agents SDK-compatible function tools.

        Returns a list of tool definitions using the ``@function_tool``
        decorator from the ``agents`` SDK.

        Requires ``openai-agents`` to be installed.
        """
        try:
            from agents import function_tool
        except ImportError:
            raise ImportError(
                "openai-agents is required for BunkerVMTools.get_tools(). "
                "Install: pip install bunkervm[openai-agents]"
            )

        base = self

        @function_tool
        def run_command(command: str) -> str:
            """Run a shell command inside the secure BunkerVM sandbox.
            The sandbox is a full Linux environment with hardware isolation.
            Use this for running scripts, installing packages, processing data, etc."""
            return base._run_command(command)

        @function_tool
        def write_file(path: str, content: str) -> str:
            """Write a file inside the secure BunkerVM sandbox.
            Creates parent directories automatically. Use absolute paths."""
            return base._write_file(path, content)

        @function_tool
        def read_file(path: str) -> str:
            """Read the contents of a file from the BunkerVM sandbox."""
            return base._read_file(path)

        @function_tool
        def list_directory(path: str = "/") -> str:
            """List files and directories at a path in the BunkerVM sandbox."""
            return base._list_directory(path)

        @function_tool
        def upload_file(local_path: str, remote_path: str) -> str:
            """Upload a file from the host into the BunkerVM sandbox."""
            return base._upload_file(local_path, remote_path)

        @function_tool
        def download_file(remote_path: str, local_path: str) -> str:
            """Download a file from the BunkerVM sandbox to the host."""
            return base._download_file(remote_path, local_path)

        return [run_command, write_file, read_file, list_directory, upload_file, download_file]
