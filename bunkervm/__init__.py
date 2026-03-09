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

    # Direct client (advanced)
    from bunkervm import SandboxClient

CLI:
    bunkervm demo                  # See it in action
    bunkervm run script.py         # Run a script safely
    bunkervm run -c "print(42)"    # Run inline code
    bunkervm server --transport sse  # Start MCP server
"""

__version__ = "0.2.6"

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
    """Shortcut to create a BunkerVMToolkit (requires langchain extras)."""
    from bunkervm.langchain import BunkerVMToolkit
    return BunkerVMToolkit(**kwargs)


def get_openai_tools(**kwargs):
    """Shortcut to create BunkerVMTools (requires openai-agents extras)."""
    from bunkervm.openai_agents import BunkerVMTools
    return BunkerVMTools(**kwargs)


def get_crewai_tools(**kwargs):
    """Shortcut to create BunkerVMCrewTools (requires crewai extras)."""
    from bunkervm.crewai import BunkerVMCrewTools
    return BunkerVMCrewTools(**kwargs)
