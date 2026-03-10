"""Full verification of BunkerVM v0.5.0 — imports, version, exports, integrations."""
import sys
sys.path.insert(0, "/mnt/c/ashish/NervOS")

import bunkervm
print("Version:", bunkervm.__version__)
assert bunkervm.__version__ == "0.6.0", f"Expected 0.6.0, got {bunkervm.__version__}"
print()

# Check all public exports
exports = ["run_code", "secure_agent", "Sandbox", "SandboxClient", "SecureAgentRuntime", "VMPool"]
all_ok = True
for name in exports:
    obj = getattr(bunkervm, name, None)
    status = "OK" if obj is not None else "MISSING"
    if obj is None:
        all_ok = False
    print(f"  {name}: {status}")

assert all_ok, "Some exports are missing!"

# Check submodules
from bunkervm.cli import main as cli_main
from bunkervm.runtime import run_code, Sandbox
from bunkervm.agent_runtime import SecureAgentRuntime, SecureAgent, secure_agent
from bunkervm.dashboard import DashboardServer
from bunkervm.multi_vm import VMPool

# Check refactored integrations
from bunkervm.integrations.base import BunkerVMToolsBase
from bunkervm.langchain import BunkerVMToolkit
from bunkervm.openai_agents import BunkerVMTools
from bunkervm.crewai import BunkerVMCrewTools

assert issubclass(BunkerVMToolkit, BunkerVMToolsBase)
assert issubclass(BunkerVMTools, BunkerVMToolsBase)
assert issubclass(BunkerVMCrewTools, BunkerVMToolsBase)

# Convenience functions
from bunkervm import get_toolkit, get_openai_tools, get_crewai_tools

print()
print("All imports OK")
print("VERIFICATION 1/7 PASSED: Imports & Version")
