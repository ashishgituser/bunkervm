<p align="center">
  <img src="docs/logo.png" alt="BunkerVM" width="120" />
</p>

<h1 align="center">BunkerVM</h1>

<p align="center">
  <strong>Run AI-generated code in disposable microVM sandboxes.</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/bunkervm/"><img src="https://img.shields.io/pypi/v/bunkervm?color=7c5cfc" alt="PyPI"></a>
  <a href="https://github.com/ashishgituser/bunkervm"><img src="https://img.shields.io/github/stars/ashishgituser/bunkervm?style=flat&color=34d399" alt="Stars"></a>
  <img src="https://img.shields.io/badge/isolation-hardware%20(KVM)-22d3ee" alt="Isolation">
  <img src="https://img.shields.io/badge/boot-~3s-fb923c" alt="Boot time">
  <img src="https://img.shields.io/badge/python-3.10+-blue" alt="Python">
</p>

<p align="center">
  AI agents generate and execute code.<br>
  Running that code on your machine is risky.<br>
  <strong>BunkerVM runs it inside disposable microVM sandboxes — hardware-isolated, not containers.</strong>
</p>

---

## Quick Start

```bash
pip install bunkervm
bunkervm demo
```

> **Note:** BunkerVM needs access to `/dev/kvm`. If you get a permission error, either add your user to the `kvm` group (`sudo usermod -aG kvm $USER`, then re-login) or run with `sudo`.

```
  ╔══════════════════════════════════════╗
  ║         BunkerVM Demo                ║
  ║  Hardware-isolated AI sandbox        ║
  ╚══════════════════════════════════════╝

Starting BunkerVM...
Launching Firecracker microVM...
Running code inside sandbox...

==================================================
  BunkerVM — Hardware-Isolated Sandbox Demo
==================================================

OS:       Linux-6.1.102-x86_64-with
Hostname: bunkervm
Python:   3.12.12

Prime numbers under 100:
2 3 5 7 11 13 17 19 23 29 31 37 41 43 47 53 59 61 67 71 73 79 83 89 97

Found 25 primes

File I/O test: Hello from BunkerVM!

✓ Code ran safely inside a Firecracker microVM
✓ Full Linux environment (not a container)
✓ Hardware-level isolation via KVM
✓ VM will be destroyed after this demo

Destroying sandbox...
Done.
✓ Demo completed in 3.6s
```

That code ran on a **real virtual machine** — not your host, not a container.

---

## Run Code Safely

```python
from bunkervm import run_code

result = run_code("print('Hello from BunkerVM!')")
print(result)  # Hello from BunkerVM!
```

One function. VM boots, code runs, VM dies. Zero config.

```python
# Multi-line code, any Python
result = run_code("""
import math
primes = [n for n in range(2, 100) if all(n % i for i in range(2, int(math.sqrt(n))+1))]
print(f"Found {len(primes)} primes")
print(primes)
""")
```

### Reusable Sandbox

Keep the VM alive for multiple executions (faster — no re-boot between runs):

```python
from bunkervm import Sandbox

with Sandbox() as sb:
    sb.run("x = 42")
    sb.run("y = x * 2")
    result = sb.run("print(f'{x} * 2 = {y}')")
    print(result)  # 42 * 2 = 84
```

State persists between `run()` calls — variables, imports, everything stays.

### From the CLI

```bash
# Run a script
bunkervm run script.py

# Run inline code
bunkervm run -c "print('Hello!')"

# Check system readiness
bunkervm info
```

---

## Secure AI Agents

Make any AI agent's code execution safe with one line:

```python
from bunkervm import secure_agent

runtime = secure_agent()
result = runtime.run("print('This runs in a sandbox!')")
print(result)
runtime.stop()
```

---

## Framework Integrations

Every integration auto-boots a Firecracker VM and gives your agent **6 sandboxed tools**:

| Tool | What it does |
|---|---|
| `run_command` | Execute any shell command inside the VM |
| `write_file` | Create / overwrite a file inside the VM |
| `read_file` | Read a file from the VM |
| `list_directory` | List files and folders in the VM |
| `upload_file` | Upload a file from host → VM |
| `download_file` | Download a file from VM → host |

All toolkits share the same `BunkerVMToolsBase` — identical behaviour regardless of framework.

### LangChain / LangGraph

```bash
pip install bunkervm[langgraph] langchain-openai python-dotenv
```

```python
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from bunkervm.langchain import BunkerVMToolkit

toolkit = BunkerVMToolkit()   # boots a Firecracker VM (~3s)

agent = create_agent(
    ChatOpenAI(model="gpt-4o"),
    tools=toolkit.get_tools(),  # 6 sandbox tools
)
result = agent.invoke({
    "messages": [("user", "Write a Python script that finds primes under 100, then run it")]
})

toolkit.stop()   # destroy VM
```

> **Context manager** — `BunkerVMToolkit` supports `with` blocks:
> ```python
> with BunkerVMToolkit() as toolkit:
>     agent = create_agent(llm, toolkit.get_tools())
>     agent.invoke(...)
> # VM auto-destroyed on exit
> ```

<details>
<summary>Agent execution output</summary>

```
🔒 BunkerVM + LangGraph Agent Demo
=============================================

⏳ Booting sandbox VM...
✅ Sandbox ready

Prompt: Write a Python script that finds all prime numbers under 100,
        save it to /tmp/primes.py, run it, and show me the output.

→ write_file: /tmp/primes.py (312 bytes)
  ← wrote 312 bytes
→ run_command: python3 /tmp/primes.py
  ← OK (42ms, 89 bytes)

🤖 The Python script was executed successfully, and here is the list of
   all prime numbers under 100:

   [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47,
    53, 59, 61, 67, 71, 73, 79, 83, 89, 97]

🧹 Sandbox destroyed.
```

</details>
<br>

### OpenAI Agents SDK

```bash
pip install bunkervm[openai-agents] python-dotenv
```

```python
from agents import Agent, Runner
from bunkervm.openai_agents import BunkerVMTools

tools = BunkerVMTools()   # boots a Firecracker VM (~3s)

agent = Agent(
    name="coder",
    instructions="You write and run code inside a secure VM.",
    tools=tools.get_tools(),  # 6 sandbox tools
)

result = Runner.run_sync(agent, "Calculate the first 20 Fibonacci numbers")
print(result.final_output)
tools.stop()
```

<details>
<summary>Agent execution output</summary>

```
🔒 BunkerVM + OpenAI Agents SDK Demo
=============================================

⏳ Booting sandbox VM...
✅ Sandbox ready

Prompt: Write a Python script that generates the first 20 Fibonacci numbers,
        save it to /tmp/fib.py, run it, and show me the output.

→ write_file: /tmp/fib.py (198 bytes)
  ← wrote 198 bytes
→ run_command: python3 /tmp/fib.py
  ← OK (38ms, 76 bytes)

🤖 The script was executed successfully. The first 20 Fibonacci numbers are:

   0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377,
   610, 987, 1597, 2584, 4181

🧹 Sandbox destroyed.
```

</details>
<br>

### CrewAI

```bash
pip install bunkervm[crewai] python-dotenv
```

```python
from crewai import Agent, Task, Crew
from bunkervm.crewai import BunkerVMCrewTools

tools = BunkerVMCrewTools()   # boots a Firecracker VM (~3s)

coder = Agent(
    role="Software Engineer",
    goal="Write and test code inside a secure sandbox",
    tools=tools.get_tools(),  # 6 sandbox tools
)
task = Task(
    description="Write a bubble sort script and run it",
    agent=coder,
    expected_output="The sorted list of numbers",
)
Crew(agents=[coder], tasks=[task]).kickoff()
tools.stop()
```

<details>
<summary>Agent execution output</summary>

```
🔒 BunkerVM + CrewAI Demo
=============================================

⏳ Booting sandbox VM...
✅ Sandbox ready

╭──── 🚀 Crew Execution Started ────╮
│  Name: crew                       │
╰───────────────────────────────────╯

╭──── 📋 Task Started ────╮
│  Write a Python script that sorts a list of 10 random numbers  │
│  using bubble sort. Save it to /tmp/sort.py, run it.           │
╰────────────────────────╯

🔧 Tool: write_file
   Args: {path: /tmp/sort.py, content: "..."}
   ✅ Wrote 403 bytes to /tmp/sort.py

🔧 Tool: run_command
   Args: {command: python3 /tmp/sort.py}
   ✅ Original list: [83, 11, 25, 19, 86, 52, 97, 5, 70, 69]
      Sorted list:   [5, 11, 19, 25, 52, 69, 70, 83, 86, 97]

╭──── ✅ Agent Final Answer ────╮
│  Original list: [83, 11, 25, 19, 86, 52, 97, 5, 70, 69]  │
│  Sorted list:   [5, 11, 19, 25, 52, 69, 70, 83, 86, 97]  │
╰───────────────────────────────╯

🤖 Result: Sorted list: [5, 11, 19, 25, 52, 69, 70, 83, 86, 97]

🧹 Sandbox destroyed.
```

</details>
<br>

### All extras

```bash
pip install bunkervm[all]    # LangChain + OpenAI Agents SDK + CrewAI
```

> Full working examples for each framework: [`examples/`](examples/)

---

### With Claude Desktop (MCP)

Add to your Claude Desktop config (`claude_desktop_config.json`):

**Linux:**
```json
{
  "mcpServers": {
    "bunkervm": {
      "command": "python3",
      "args": ["-m", "bunkervm"]
    }
  }
}
```

**Windows (WSL2):**
```json
{
  "mcpServers": {
    "bunkervm": {
      "command": "wsl",
      "args": ["-d", "Ubuntu", "--", "python3", "-m", "bunkervm"]
    }
  }
}
```

---

## Why Not Docker?

|  | BunkerVM | Docker |
|---|---|---|
| **Isolation** | Hardware (KVM) — separate kernel | Shared kernel |
| **Escape risk** | Near zero | Container escapes exist |
| **Boot time** | ~3s | ~0.5s |
| **Self-hosted** | ✓ | ✓ |
| **Setup** | `pip install bunkervm` | Dockerfile + build + run |

BunkerVM runs each agent in a **real virtual machine**. If the agent goes rogue, it can't touch your host.

---

## MCP Tools

When running as an MCP server, BunkerVM exposes 8 tools:

| Tool | Description |
|---|---|
| `sandbox_exec` | Run any shell command |
| `sandbox_write_file` | Create or edit files |
| `sandbox_read_file` | Read files |
| `sandbox_list_dir` | Browse directories |
| `sandbox_upload_file` | Upload files host → VM |
| `sandbox_download_file` | Download files VM → host |
| `sandbox_status` | Check VM health, CPU, RAM |
| `sandbox_reset` | Wipe sandbox, start fresh |

## Multi-VM Support

Run multiple isolated sandboxes simultaneously:

```python
from bunkervm import VMPool

pool = VMPool(max_vms=5)
pool.start("agent-1", cpus=2, memory=1024)
pool.start("agent-2", cpus=1, memory=512)

pool.client("agent-1").exec("echo 'I am agent 1'")
pool.client("agent-2").exec("echo 'I am agent 2'")

pool.stop_all()
```

## Web Dashboard

```bash
bunkervm server --transport sse --dashboard
# Dashboard at http://localhost:3001/dashboard
```

Real-time monitoring: VM status, CPU, memory, running VMs, live audit log, and reset controls.

## CLI Reference

```
bunkervm demo                        # See it in action
bunkervm run script.py               # Run a script in a sandbox
bunkervm run -c "print(42)"          # Run inline code
bunkervm server --transport sse      # Start MCP server
bunkervm info                        # Check system readiness

Options:
  --cpus N          vCPUs (default: 1 for run, 2 for server)
  --memory MB       RAM in MB (default: 512 for run, 2048 for server)
  --no-network      Disable internet inside VM
  --timeout SECS    Execution timeout (default: 30)
  --dashboard       Enable web dashboard (server mode)
```

---

## Requirements

- **Linux** with KVM (Ubuntu, Debian, Fedora, etc.)
- **Windows** — WSL2 with nested virtualization enabled
- **macOS** — Not supported (no KVM)
- Python 3.10+
- ~100MB disk (bundle auto-downloaded on first run)

### KVM Access

BunkerVM needs `/dev/kvm`. Most Linux systems and WSL2 have it. Check with:

```bash
bunkervm info    # Shows ✓ or ✗ for KVM status
```

If KVM exists but you get permission errors:

```bash
# Option 1: Add yourself to the kvm group (recommended, one-time)
sudo usermod -aG kvm $USER
# Then log out and log back in

# Option 2: Open permissions (quick fix)
sudo chmod 666 /dev/kvm
```

### WSL2 Setup (Windows)

Add to `%USERPROFILE%\.wslconfig`:
```ini
[wsl2]
nestedVirtualization=true
```
Then restart WSL: `wsl --shutdown`

---

## How It Works

```
Your AI Agent
     │
     ▼
  bunkervm        ──vsock──▶   Firecracker MicroVM
  (host)                       ┌──────────────────┐
                               │  Alpine Linux     │
                               │  Python 3.12      │
                               │  Full toolchain   │
                               │  exec_agent       │
                               └──────────────────┘
                               Hardware isolation (KVM)
                               Destroyed after use
```

- **[Firecracker](https://firecracker-microvm.github.io/)** — Amazon's micro-VM engine (powers AWS Lambda)
- **vsock** — Zero-config host↔VM communication
- **exec_agent** — Lightweight HTTP server inside the VM
- **~100MB bundle** — Firecracker + kernel + rootfs, downloaded once to `~/.bunkervm/`

---

## Install

```bash
pip install bunkervm                  # Core
pip install bunkervm[langgraph]       # + LangGraph/LangChain
pip install bunkervm[openai-agents]   # + OpenAI Agents SDK
pip install bunkervm[crewai]          # + CrewAI
pip install bunkervm[all]             # Everything
```

## Troubleshooting

| Problem | Solution |
|---|---|
| `bunkervm: command not found` with sudo | Use `sudo $(which bunkervm) demo` or add user to kvm group instead |
| `/dev/kvm not found` | Enable KVM: `sudo modprobe kvm` or enable nested virtualization in WSL2 |
| `Permission denied: /dev/kvm` | `sudo usermod -aG kvm $USER` then re-login |
| Bundle download fails | Manually download from [GitHub Releases](https://github.com/ashishgituser/bunkervm/releases) and extract to `~/.bunkervm/bundle/` |
| VM fails to start | Run `bunkervm info` to diagnose — it checks all prerequisites |

## For Contributors

<details>
<summary>Building from source</summary>

```bash
git clone https://github.com/ashishgituser/bunkervm.git
cd bunkervm

# Build the micro-OS (needs Linux/WSL2 + sudo)
sudo bash build/setup-firecracker.sh
sudo bash build/build-sandbox-rootfs.sh

# Install in dev mode
pip install -e ".[dev]"

# Run
bunkervm demo
```

</details>

## License

AGPL-3.0 — Free for personal and open-source use.
