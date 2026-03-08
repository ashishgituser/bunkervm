"""
BunkerVM — Self-hosted, hardware-isolated sandbox for AI agents.

Exposes a Firecracker MicroVM as MCP tools that any AI model
(Claude, GPT, Ollama, LangGraph) can use for safe command execution.

Quick start with LangGraph:
    from bunkervm.langchain import BunkerVMToolkit
    from langgraph.prebuilt import create_react_agent

    tools = BunkerVMToolkit().get_tools()
    agent = create_react_agent(llm, tools)
"""

__version__ = "0.2.2"

from bunkervm.sandbox_client import SandboxClient  # noqa: F401

__all__ = ["SandboxClient", "__version__"]

# Lazy import for optional LangChain integration
def get_toolkit(**kwargs):
    """Shortcut to create a BunkerVMToolkit (requires langchain extras)."""
    from bunkervm.langchain import BunkerVMToolkit
    return BunkerVMToolkit(**kwargs)
