"""Test all imports — core API."""

import pytest


def test_core_api_imports():
    """Core API symbols are importable."""
    from bunkervm import run_code, secure_agent, Sandbox, SandboxClient, VMPool, SecureAgentRuntime
    from bunkervm.cli import main
    from bunkervm.runtime import Sandbox as Sandbox2
    from bunkervm.agent_runtime import SecureAgent

    assert Sandbox is Sandbox2


def test_agent_tool_adapters():
    """SecureAgentRuntime exposes single-tool adapters for LangChain/OpenAI Agents SDK."""
    from bunkervm.agent_runtime import SecureAgentRuntime

    assert hasattr(SecureAgentRuntime, "as_tool")
    assert hasattr(SecureAgentRuntime, "as_openai_tool")


def test_version():
    """Package exposes a version string."""
    import bunkervm

    assert isinstance(bunkervm.__version__, str)
    assert len(bunkervm.__version__) > 0
