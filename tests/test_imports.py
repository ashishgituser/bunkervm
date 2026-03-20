"""Test all imports — core API, integrations, and convenience functions."""

import pytest


def test_core_api_imports():
    """Core API symbols are importable."""
    from bunkervm import run_code, secure_agent, Sandbox, SandboxClient, VMPool, SecureAgentRuntime
    from bunkervm.cli import main
    from bunkervm.runtime import Sandbox as Sandbox2
    from bunkervm.agent_runtime import SecureAgent

    assert Sandbox is Sandbox2


def test_integrations_base_import():
    """BunkerVMToolsBase is importable from both paths."""
    from bunkervm.integrations.base import BunkerVMToolsBase
    from bunkervm.integrations import BunkerVMToolsBase as B2

    assert B2 is BunkerVMToolsBase


def test_framework_imports():
    """Framework adapter modules import without their framework packages installed."""
    from bunkervm.langchain import BunkerVMToolkit
    from bunkervm.openai_agents import BunkerVMTools
    from bunkervm.crewai import BunkerVMCrewTools
    from bunkervm.integrations.base import BunkerVMToolsBase

    assert issubclass(BunkerVMToolkit, BunkerVMToolsBase)
    assert issubclass(BunkerVMTools, BunkerVMToolsBase)
    assert issubclass(BunkerVMCrewTools, BunkerVMToolsBase)


def test_shared_tool_methods():
    """Base class exposes all 6 shared tool methods."""
    from bunkervm.integrations.base import BunkerVMToolsBase

    for m in [
        "_run_command",
        "_write_file",
        "_read_file",
        "_list_directory",
        "_upload_file",
        "_download_file",
    ]:
        assert hasattr(BunkerVMToolsBase, m), f"Missing method: {m}"


def test_convenience_functions():
    """Convenience factory functions are importable."""
    from bunkervm import get_toolkit, get_openai_tools, get_crewai_tools


def test_version():
    """Package exposes a version string."""
    import bunkervm

    assert isinstance(bunkervm.__version__, str)
    assert len(bunkervm.__version__) > 0
