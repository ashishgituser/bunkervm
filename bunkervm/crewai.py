"""
BunkerVM CrewAI Integration — secure sandbox tools for CrewAI agents.

Usage (auto-boot — zero config):
    from bunkervm.crewai import BunkerVMCrewTools
    from crewai import Agent, Task, Crew

    tools = BunkerVMCrewTools()          # auto-boots a Firecracker VM

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
    tools.stop()                         # destroy VM when done

Usage (attach to running VM):
    tools = BunkerVMCrewTools(vsock_uds="/tmp/bunkervm-vsock.sock")
    tools = BunkerVMCrewTools(host="172.16.0.2", port=8080)

Requires: pip install bunkervm[crewai]
"""

from __future__ import annotations

from typing import Type

from bunkervm.integrations.base import BunkerVMToolsBase


class BunkerVMCrewTools(BunkerVMToolsBase):
    """CrewAI-compatible tool provider for BunkerVM.

    Provides tools for: run_command, write_file, read_file,
    list_directory, upload_file, download_file

    All operations execute inside a hardware-isolated Firecracker MicroVM.

    Modes:
        - ``BunkerVMCrewTools()`` — auto-boots a VM (zero config).
        - ``BunkerVMCrewTools(vsock_uds=...)`` — attach to a running VM via vsock.
        - ``BunkerVMCrewTools(host=..., port=...)`` — attach via TCP.

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
        """Return CrewAI-compatible tool instances.

        Returns a list of ``BaseTool`` subclass instances with Pydantic
        input schemas, as required by CrewAI.

        Requires ``crewai`` to be installed.
        """
        try:
            from crewai.tools import BaseTool
            from pydantic import BaseModel, Field
        except ImportError:
            raise ImportError(
                "crewai is required for BunkerVMCrewTools.get_tools(). "
                "Install: pip install bunkervm[crewai]"
            )

        base = self

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
                return base._run_command(command)

        class WriteFileTool(BaseTool):
            name: str = "write_file"
            description: str = "Write a file inside the BunkerVM sandbox. Creates parent dirs automatically."
            args_schema: Type[BaseModel] = WriteFileInput

            def _run(self, path: str, content: str) -> str:
                return base._write_file(path, content)

        class ReadFileTool(BaseTool):
            name: str = "read_file"
            description: str = "Read the contents of a file from the BunkerVM sandbox."
            args_schema: Type[BaseModel] = ReadFileInput

            def _run(self, path: str) -> str:
                return base._read_file(path)

        class ListDirectoryTool(BaseTool):
            name: str = "list_directory"
            description: str = "List files and directories at a path in the BunkerVM sandbox."
            args_schema: Type[BaseModel] = ListDirectoryInput

            def _run(self, path: str = "/") -> str:
                return base._list_directory(path)

        class UploadFileTool(BaseTool):
            name: str = "upload_file"
            description: str = "Upload a file from the host into the BunkerVM sandbox."
            args_schema: Type[BaseModel] = UploadFileInput

            def _run(self, local_path: str, remote_path: str) -> str:
                return base._upload_file(local_path, remote_path)

        class DownloadFileTool(BaseTool):
            name: str = "download_file"
            description: str = "Download a file from the BunkerVM sandbox to the host."
            args_schema: Type[BaseModel] = DownloadFileInput

            def _run(self, remote_path: str, local_path: str) -> str:
                return base._download_file(remote_path, local_path)

        return [
            RunCommandTool(),
            WriteFileTool(),
            ReadFileTool(),
            ListDirectoryTool(),
            UploadFileTool(),
            DownloadFileTool(),
        ]
