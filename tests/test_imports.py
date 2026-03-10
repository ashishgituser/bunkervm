"""Test all imports — core API, integrations, and convenience functions."""

# ── Core API ──
from bunkervm import run_code, secure_agent, Sandbox, SandboxClient, VMPool, SecureAgentRuntime
from bunkervm.cli import main
from bunkervm.runtime import Sandbox as Sandbox2
from bunkervm.agent_runtime import SecureAgent

# ── Integrations base ──
from bunkervm.integrations.base import BunkerVMToolsBase
from bunkervm.integrations import BunkerVMToolsBase as B2
assert B2 is BunkerVMToolsBase, "integrations package re-export"

# ── Framework modules (lazy — no framework packages required at import) ──
from bunkervm.langchain import BunkerVMToolkit
from bunkervm.openai_agents import BunkerVMTools
from bunkervm.crewai import BunkerVMCrewTools

# ── Inheritance check ──
assert issubclass(BunkerVMToolkit, BunkerVMToolsBase), "BunkerVMToolkit must extend base"
assert issubclass(BunkerVMTools, BunkerVMToolsBase), "BunkerVMTools must extend base"
assert issubclass(BunkerVMCrewTools, BunkerVMToolsBase), "BunkerVMCrewTools must extend base"

# ── Shared tool methods ──
for m in ["_run_command", "_write_file", "_read_file", "_list_directory", "_upload_file", "_download_file"]:
    assert hasattr(BunkerVMToolsBase, m), f"Missing method: {m}"

# ── Convenience functions ──
from bunkervm import get_toolkit, get_openai_tools, get_crewai_tools

# ── Version ──
print('Version:', __import__('bunkervm').__version__)
print('All imports OK')
