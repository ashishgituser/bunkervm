"""
BunkerVM — Hardware-isolated sandbox for AI agents.

Run untrusted AI-generated code inside disposable Firecracker microVM sandboxes.
One function call. Zero config. Hardware-level isolation.

Quick start:
    # Run code safely
    from bunkervm import run_code
    result = run_code("print('Hello from BunkerVM!')")

    # Secure an AI agent
    from bunkervm import secure_agent
    safe = secure_agent(my_agent)
    safe.run("write a script to compute primes")

    # Reusable sandbox
    from bunkervm import Sandbox
    with Sandbox() as sb:
        sb.run("x = 42")
        sb.run("print(x)")

    # Framework integrations (auto-boot VM, zero config):
    from bunkervm.langchain import BunkerVMToolkit       # LangChain/LangGraph
    from bunkervm.openai_agents import BunkerVMTools     # OpenAI Agents SDK
    from bunkervm.crewai import BunkerVMCrewTools        # CrewAI

    # Direct client (advanced)
    from bunkervm import SandboxClient

CLI:
    bunkervm demo                  # See it in action
    bunkervm run script.py         # Run a script safely
    bunkervm run -c "print(42)"    # Run inline code
    bunkervm server --transport sse  # Start MCP server
"""

__version__ = "0.7.0"

# ── Core API (always available) ──
from bunkervm.sandbox_client import SandboxClient  # noqa: F401
from bunkervm.multi_vm import VMPool  # noqa: F401
from bunkervm.runtime import run_code, Sandbox  # noqa: F401
from bunkervm.agent_runtime import secure_agent, SecureAgentRuntime  # noqa: F401

__all__ = [
    "run_code",
    "secure_agent",
    "Sandbox",
    "SandboxClient",
    "SecureAgentRuntime",
    "VMPool",
    "__version__",
]


def get_toolkit(**kwargs):
    """Create a BunkerVMToolkit for LangChain/LangGraph (requires langchain extras).

    No args = auto-boots a VM. Pass vsock_uds or host/port to attach to a
    running VM.

    Example:
        toolkit = get_toolkit()  # auto-boot
        tools = toolkit.get_tools()
    """
    from bunkervm.langchain import BunkerVMToolkit
    return BunkerVMToolkit(**kwargs)


def get_openai_tools(**kwargs):
    """Create BunkerVMTools for OpenAI Agents SDK (requires openai-agents extras).

    No args = auto-boots a VM. Pass vsock_uds or host/port to attach to a
    running VM.

    Example:
        tools_provider = get_openai_tools()
        tools = tools_provider.get_tools()
    """
    from bunkervm.openai_agents import BunkerVMTools
    return BunkerVMTools(**kwargs)


def get_crewai_tools(**kwargs):
    """Create BunkerVMCrewTools for CrewAI (requires crewai extras).

    No args = auto-boots a VM. Pass vsock_uds or host/port to attach to a
    running VM.

    Example:
        crew_tools = get_crewai_tools()
        tools = crew_tools.get_tools()
    """
    from bunkervm.crewai import BunkerVMCrewTools
    return BunkerVMCrewTools(**kwargs)
