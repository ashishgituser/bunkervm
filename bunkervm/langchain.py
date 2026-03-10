"""
BunkerVM LangChain/LangGraph Integration — drop-in secure sandbox tools.

Usage (auto-boot — zero config):
    from bunkervm.langchain import BunkerVMToolkit
    from langchain_openai import ChatOpenAI
    from langchain.agents import create_agent

    toolkit = BunkerVMToolkit()          # auto-boots a Firecracker VM
    agent = create_agent(ChatOpenAI(model="gpt-4o"), toolkit.get_tools())
    result = agent.invoke({"messages": [("user", "Write and run hello.py")]})
    toolkit.stop()                       # destroy VM when done

Usage (attach to running VM):
    toolkit = BunkerVMToolkit(vsock_uds="/tmp/bunkervm-vsock.sock")
    toolkit = BunkerVMToolkit(host="172.16.0.2", port=8080)

Requires: pip install bunkervm[langgraph]
"""

from __future__ import annotations

from bunkervm.integrations.base import BunkerVMToolsBase


class BunkerVMToolkit(BunkerVMToolsBase):
    """LangChain-compatible toolkit that routes all tool calls to BunkerVM.

    Provides: run_command, write_file, read_file, list_directory,
              upload_file, download_file

    All operations execute inside a hardware-isolated Firecracker MicroVM —
    zero risk to the host system.

    Modes:
        - ``BunkerVMToolkit()`` — auto-boots a VM (zero config).
        - ``BunkerVMToolkit(vsock_uds=...)`` — attach to a running VM via vsock.
        - ``BunkerVMToolkit(host=..., port=...)`` — attach via TCP.

    Args:
        vsock_uds: Path to BunkerVM vsock socket (omit to auto-boot).
        vsock_port: Vsock port (default 8080).
        host: TCP host for network mode (alternative to vsock).
        port: TCP port for network mode.
        command_timeout: Default timeout for command execution (seconds).
        cpus: vCPUs for auto-booted VM.
        memory: Memory in MB for auto-booted VM.
        network: Allow internet in auto-booted VM.
    """

    def get_tools(self) -> list:
        """Return LangChain-compatible tools bound to this VM.

        Returns a list of tools ready to pass to ``create_agent()``,
        ``ToolNode()``, or ``bind_tools()``.

        Requires ``langchain-core`` to be installed.
        """
        try:
            from langchain_core.tools import tool as langchain_tool
        except ImportError:
            raise ImportError(
                "langchain-core is required for BunkerVMToolkit.get_tools(). "
                "Install: pip install bunkervm[langgraph]"
            )

        base = self

        @langchain_tool
        def run_command(command: str) -> str:
            """Run a shell command inside the secure BunkerVM sandbox.
            Use this to execute any bash command, run scripts, install packages, etc.
            The sandbox is a full Linux environment with Python, network access, and
            a real filesystem — but hardware-isolated from the host."""
            return base._run_command(command)

        @langchain_tool
        def write_file(path: str, content: str) -> str:
            """Write a file inside the secure BunkerVM sandbox.
            Creates parent directories automatically. Use absolute paths like /tmp/script.py."""
            return base._write_file(path, content)

        @langchain_tool
        def read_file(path: str) -> str:
            """Read the contents of a file from the BunkerVM sandbox."""
            return base._read_file(path)

        @langchain_tool
        def list_directory(path: str = "/") -> str:
            """List files and directories at a path in the BunkerVM sandbox."""
            return base._list_directory(path)

        @langchain_tool
        def upload_file(local_path: str, remote_path: str) -> str:
            """Upload a file from the host into the BunkerVM sandbox.
            Use this to provide datasets, configs, or other files to the sandbox."""
            return base._upload_file(local_path, remote_path)

        @langchain_tool
        def download_file(remote_path: str, local_path: str) -> str:
            """Download a file from the BunkerVM sandbox to the host.
            Use this to save results, generated files, or artifacts."""
            return base._download_file(remote_path, local_path)

        return [run_command, write_file, read_file, list_directory, upload_file, download_file]
