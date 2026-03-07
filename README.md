# NervOS

Run AI agent code inside a Firecracker microVM instead of your host machine.

NervOS provides a lightweight sandbox for AI agents executing arbitrary code.

> Give your AI agent a computer. Isolated. Instant. Self-hosted.

NervOS is a tiny operating system that boots in **2 seconds** and gives AI agents a safe, isolated Linux machine to work in. Install it with one command. No Docker. No cloud. No config files.

## Install

```
pip install nervos-sandbox
```

## Use with Claude Desktop

Add this to your Claude Desktop config:

**Windows (WSL2):**
```json
{
  "mcpServers": {
    "nervos": {
      "command": "wsl",
      "args": ["-d", "Ubuntu", "--", "sudo", "python3", "-m", "nervos_server"]
    }
  }
}
```

**Linux / macOS:**
```json
{
  "mcpServers": {
    "nervos": {
      "command": "sudo",
      "args": ["python3", "-m", "nervos_server"]
    }
  }
}
```

That's it. On first run, NervOS downloads a ~100MB pre-built micro-OS. After that, every launch boots a fresh VM in ~2 seconds.

## What can it do?

Once connected, your AI agent gets these tools:

| Tool | What it does |
|---|---|
| `sandbox_exec` | Run any shell command |
| `sandbox_write_file` | Create or edit files |
| `sandbox_read_file` | Read files |
| `sandbox_list_dir` | Browse directories |
| `sandbox_status` | Check VM health, CPU, RAM, disk |
| `sandbox_reset` | Wipe everything, start fresh |

**Example:** Ask Claude to *"write a Python script that fetches the top 10 Hacker News stories, then run it"* — it writes the code inside the VM, executes it, and shows you the results. All isolated.

## Why not Docker?

| | NervOS | Docker |
|---|---|---|
| Isolation | **Hardware (KVM)** — separate kernel | Shared kernel |
| Escape risk | Near zero | Container escapes exist |
| Boot time | ~2s | ~0.5s |
| Self-hosted | Yes | Yes |
| Internet access | Optional | Yes |
| Setup | `pip install` | Dockerfile + build + run |

NervOS runs each agent in a real virtual machine. If the agent goes rogue, it can't touch your host.

## Requirements

- **Linux** with KVM support, or **Windows** with WSL2
- Python 3.10+
- ~100MB disk for the micro-OS bundle

For WSL2, enable nested virtualization in `%USERPROFILE%\.wslconfig`:
```ini
[wsl2]
nestedVirtualization=true
```

## Works with any MCP client

NervOS speaks the [Model Context Protocol](https://modelcontextprotocol.io). It works with:
- Claude Desktop
- LangGraph / LangChain
- Any MCP-compatible agent framework

```bash
# For LangGraph integration:
pip install nervos-sandbox[langgraph]
```

See [tests/test_langgraph.py](tests/test_langgraph.py) for a working example.

## How it works (you don't need to know this)

<details>
<summary>Under the hood</summary>

NervOS is a custom Alpine Linux micro-OS (~256MB) purpose-built for AI agent sandboxing:

```
Your AI  ──MCP──▶  nervos_server  ──vsock──▶  Firecracker MicroVM
                   (host)                      ┌──────────────┐
                                               │ Alpine Linux │
                                               │ Python 3     │
                                               │ gcc, git,    │
                                               │ curl, etc.   │
                                               │              │
                                               │ exec_agent   │
                                               └──────────────┘
```

- **Firecracker** — Amazon's micro-VM engine (same tech as AWS Lambda)
- **vsock** — Direct host↔VM communication, no networking needed
- **TAP networking** — Optional, gives the VM internet access
- **exec_agent** — HTTP server inside the VM that executes commands

The pre-built bundle (~100MB) includes Firecracker, a Linux kernel, and the rootfs. Downloaded once on first run to `~/.nervos/bundle/`.

</details>

## For contributors

<details>
<summary>Building from source</summary>

```bash
# Clone
git clone https://github.com/ashishgituser/NervOS.git
cd NervOS

# Build the micro-OS locally (needs Linux/WSL2 + sudo)
sudo bash build/setup-firecracker.sh    # Download Firecracker + kernel
sudo bash build/build-sandbox-rootfs.sh  # Build the 256MB rootfs

# Install in dev mode
pip install -e ".[dev]"

# Run
sudo python -m nervos_server
```

Files go into `build/` locally. The bootstrap module auto-detects local builds.

</details>

## License

AGPL-3.0 — Free for personal and open-source use. If you modify NervOS and offer it as a service, you must open-source your changes under the same license.

For commercial licensing, contact the author.
