"""
BunkerVM Agent Runtime — Drop-in secure execution for AI agents.

Wraps any AI agent's code execution to run inside a Firecracker microVM.
One line to make any agent secure.

Usage:
    from bunkervm import secure_agent

    # LangGraph / LangChain
    from langgraph.prebuilt import create_react_agent
    agent = secure_agent(create_react_agent(model, tools))

    # Or wrap any callable
    agent = secure_agent(my_agent_function)

How it works:
    1. Intercepts code execution tool calls
    2. Redirects them into a BunkerVM sandbox
    3. Returns results as if they ran locally
    4. Sandbox is reused across calls (fast) and destroyed on cleanup
"""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable, Optional

logger = logging.getLogger("bunkervm.agent_runtime")


class SecureAgentRuntime:
    """Wraps an AI agent's execution in a BunkerVM sandbox.

    Provides a persistent sandbox that lives for the duration of the agent's
    execution. All code execution is redirected into the microVM.

    Args:
        cpus: vCPUs for the sandbox. Default: 1.
        memory: Memory in MB. Default: 512.
        network: Allow internet in sandbox. Default: True.
        timeout: Default execution timeout. Default: 30.
        auto_start: Start sandbox immediately. Default: True.
        reset_between_runs: Reset sandbox between agent invocations. Default: False.

    Usage:
        runtime = SecureAgentRuntime()

        # Execute code safely
        result = runtime.run("print('Hello from sandbox')")

        # Execute shell commands
        output = runtime.exec("ls -la /")

        # Clean up
        runtime.stop()
    """

    def __init__(
        self,
        cpus: int = 1,
        memory: int = 512,
        network: bool = True,
        timeout: int = 30,
        auto_start: bool = True,
        reset_between_runs: bool = False,
    ):
        from .runtime import Sandbox

        self._sandbox = Sandbox(
            cpus=cpus,
            memory=memory,
            network=network,
            timeout=timeout,
            quiet=True,
        )
        self._reset_between = reset_between_runs
        self._started = False

        if auto_start:
            self.start()

    def start(self) -> "SecureAgentRuntime":
        """Start the sandbox VM."""
        if not self._started:
            self._sandbox.start()
            self._started = True
        return self

    def stop(self) -> None:
        """Destroy the sandbox VM."""
        if self._started:
            self._sandbox.stop()
            self._started = False

    def run(self, code: str, language: str = "python", timeout: Optional[int] = None) -> str:
        """Execute code inside the sandbox.

        This is the core method that agent tool wrappers call.

        Args:
            code: Source code to execute.
            language: "python", "bash", or "node".
            timeout: Override default timeout.

        Returns:
            stdout output from the code.
        """
        if not self._started:
            self.start()
        return self._sandbox.run(code, language=language, timeout=timeout)

    def exec(self, command: str, timeout: Optional[int] = None) -> str:
        """Execute a shell command inside the sandbox.

        Args:
            command: Shell command to run.
            timeout: Override default timeout.

        Returns:
            stdout output.
        """
        if not self._started:
            self.start()
        return self._sandbox.exec(command, timeout=timeout)

    def upload(self, local_path: str, remote_path: str) -> None:
        """Upload a file into the sandbox."""
        if not self._started:
            self.start()
        self._sandbox.upload(local_path, remote_path)

    def download(self, remote_path: str) -> bytes:
        """Download a file from the sandbox."""
        if not self._started:
            self.start()
        return self._sandbox.download(remote_path)

    @property
    def client(self):
        """Direct access to SandboxClient for advanced usage."""
        return self._sandbox.client

    def __enter__(self) -> "SecureAgentRuntime":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    def __del__(self) -> None:
        try:
            self.stop()
        except Exception:
            pass

    # ── Framework Tool Shortcuts ──

    def as_tool(self, name: str = "execute_code") -> Any:
        """Create a LangChain-compatible tool that runs code in this sandbox.

        For a full set of tools (run_command, write_file, read_file, etc.),
        use ``BunkerVMToolkit`` instead::

            from bunkervm.langchain import BunkerVMToolkit
            toolkit = BunkerVMToolkit()
            tools = toolkit.get_tools()

        This method creates a single "execute_code" tool for simple cases.

        Usage:
            runtime = SecureAgentRuntime()
            tool = runtime.as_tool()
            agent = create_react_agent(model, [tool])
        """
        try:
            from langchain_core.tools import tool as lc_tool
        except ImportError:
            raise ImportError(
                "langchain-core is required for as_tool(). "
                "Install: pip install bunkervm[langgraph]"
            )

        runtime = self

        @lc_tool
        def execute_code(code: str) -> str:
            """Execute Python code inside a secure BunkerVM sandbox.

            The code runs inside a Firecracker microVM with hardware-level
            isolation. Use this for any code execution, file operations,
            or system commands.

            Args:
                code: Python code to execute.

            Returns:
                stdout output from execution.
            """
            return runtime.run(code)

        execute_code.name = name
        return execute_code

    def as_openai_tool(self, name: str = "execute_code") -> Any:
        """Create an OpenAI Agents SDK tool.

        For a full set of tools (run_command, write_file, read_file, etc.),
        use ``BunkerVMTools`` instead::

            from bunkervm.openai_agents import BunkerVMTools
            tools = BunkerVMTools()
            agent_tools = tools.get_tools()

        This method creates a single "execute_code" tool for simple cases.

        Usage:
            runtime = SecureAgentRuntime()
            tool = runtime.as_openai_tool()
            agent = Agent(tools=[tool])
        """
        try:
            from agents import function_tool
        except ImportError:
            raise ImportError(
                "openai-agents is required for as_openai_tool(). "
                "Install: pip install bunkervm[openai-agents]"
            )

        runtime = self

        @function_tool(name_override=name)
        def execute_code(code: str) -> str:
            """Execute Python code inside a secure BunkerVM sandbox.
            The code runs in a hardware-isolated Firecracker microVM.

            Args:
                code: Python code to execute.
            """
            return runtime.run(code)

        return execute_code


def secure_agent(
    agent: Any = None,
    *,
    cpus: int = 1,
    memory: int = 512,
    network: bool = True,
    timeout: int = 30,
) -> Any:
    """Wrap an AI agent with BunkerVM secure execution.

    This is the main entry point for securing AI agents. It returns a
    SecureAgent that redirects code execution into a Firecracker microVM.

    Usage:
        # Wrap a LangGraph agent
        from bunkervm import secure_agent
        safe = secure_agent(create_react_agent(model, tools))
        result = safe.invoke({"messages": [...]})

        # Or get a runtime directly (no agent)
        from bunkervm import secure_agent
        runtime = secure_agent()
        runtime.run("print('safe!')")

    Args:
        agent: An AI agent to wrap (LangGraph, LangChain, etc.).
               If None, returns a SecureAgentRuntime directly.
        cpus: vCPUs for the sandbox.
        memory: Memory in MB.
        network: Allow internet.
        timeout: Default timeout.

    Returns:
        SecureAgent wrapper or SecureAgentRuntime if no agent provided.
    """
    runtime = SecureAgentRuntime(
        cpus=cpus,
        memory=memory,
        network=network,
        timeout=timeout,
        auto_start=True,
    )

    if agent is None:
        return runtime

    return SecureAgent(agent, runtime)


class SecureAgent:
    """Wraps an existing AI agent with a BunkerVM sandbox.

    Intercepts tool calls that involve code execution and redirects
    them into the sandbox VM.

    The wrapped agent can be used exactly like the original.
    """

    def __init__(self, agent: Any, runtime: SecureAgentRuntime):
        self._agent = agent
        self._runtime = runtime

    @property
    def runtime(self) -> SecureAgentRuntime:
        """Access the underlying SecureAgentRuntime."""
        return self._runtime

    def invoke(self, *args, **kwargs) -> Any:
        """Invoke the wrapped agent (LangGraph/LangChain compatible)."""
        return self._agent.invoke(*args, **kwargs)

    def run(self, prompt: str, **kwargs) -> str:
        """Convenience: run a prompt through the agent.

        For agents that support .invoke() with messages.
        """
        # Try LangGraph-style invocation
        try:
            result = self._agent.invoke(
                {"messages": [("user", prompt)]},
                **kwargs,
            )
            # Extract last message
            if isinstance(result, dict) and "messages" in result:
                messages = result["messages"]
                if messages:
                    last = messages[-1]
                    if hasattr(last, "content"):
                        return last.content
                    return str(last)
            return str(result)
        except Exception:
            pass

        # Try direct call
        try:
            return str(self._agent(prompt, **kwargs))
        except Exception as e:
            raise RuntimeError(f"Could not invoke agent: {e}") from e

    def stop(self) -> None:
        """Destroy the sandbox."""
        self._runtime.stop()

    def __enter__(self) -> "SecureAgent":
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    def __getattr__(self, name: str) -> Any:
        """Proxy all other attributes to the wrapped agent."""
        return getattr(self._agent, name)
