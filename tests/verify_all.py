"""Full verification of BunkerVM v0.4.0 — imports, version, exports."""
import sys
sys.path.insert(0, "/mnt/c/ashish/NervOS")

import bunkervm
print("Version:", bunkervm.__version__)
assert bunkervm.__version__ == "0.4.0", f"Expected 0.4.0, got {bunkervm.__version__}"
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
from bunkervm.crewai import BunkerVMCrewTools
from bunkervm.openai_agents import BunkerVMTools

print()
print("All imports OK")
print("VERIFICATION 1/7 PASSED: Imports & Version")
