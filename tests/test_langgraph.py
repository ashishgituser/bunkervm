#!/usr/bin/env python3
"""
BunkerVM + LangGraph Integration Test

Demonstrates using BunkerVM MCP sandbox as a tool within a LangGraph agent.
The agent gets a task, reasons about it, and executes code inside the
hardware-isolated Firecracker MicroVM via vsock.

Prerequisites:
  pip install langchain-openai langgraph langchain-core
  # BunkerVM VM must be running (or use --skip-vm with external VM)

Usage:
  # Start BunkerVM (boots VM automatically):
  sudo python -m bunkervm &

  # Set your API key
  export OPENAI_API_KEY=sk-...

  # Run the example
  python tests/test_langgraph.py

Architecture:
  LangGraph Agent (Claude) → tool calls → BunkerVM sandbox client → vsock → Firecracker VM
"""

from __future__ import annotations

import json
import os
import socket
import sys
from typing import Annotated, Any

# Load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except ImportError:
    pass  # dotenv not installed — rely on env vars

# ── LangGraph / LangChain imports ──
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode

# ── Choose your LLM ──
# Option A: OpenAI GPT-4o
try:
    from langchain_openai import ChatOpenAI
    LLM_AVAILABLE = "openai"
except ImportError:
    LLM_AVAILABLE = None

# Option B: Anthropic fallback
if not LLM_AVAILABLE:
    try:
        from langchain_anthropic import ChatAnthropic
        LLM_AVAILABLE = "anthropic"
    except ImportError:
        pass


# ═══════════════════════════════════════════════════════════════════
# BunkerVM Sandbox Client (direct vsock — no MCP server needed)
# ═══════════════════════════════════════════════════════════════════

VSOCK_UDS = os.environ.get("BUNKERVM_VSOCK_UDS", "/tmp/bunkervm-vsock.sock")
VSOCK_PORT = int(os.environ.get("BUNKERVM_VSOCK_PORT", "8080"))


def _update_vsock_uds(path: str):
    global VSOCK_UDS
    VSOCK_UDS = path


def _vsock_request(method: str, path: str, body: dict | None = None) -> dict:
    """Send an HTTP request to the exec agent over Firecracker vsock."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(120)  # generous timeout for long commands
    s.connect(VSOCK_UDS)

    # Firecracker vsock handshake
    s.sendall(f"CONNECT {VSOCK_PORT}\n".encode())
    resp = s.recv(256)
    if b"OK" not in resp:
        s.close()
        raise ConnectionError(f"Vsock handshake failed: {resp!r}")

    # Build raw HTTP request
    if body:
        payload = json.dumps(body).encode()
        req = (
            f"{method} {path} HTTP/1.0\r\n"
            f"Host: localhost\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(payload)}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        ).encode() + payload
    else:
        req = (
            f"{method} {path} HTTP/1.0\r\n"
            f"Host: localhost\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        ).encode()

    s.sendall(req)

    # Read full response
    data = b""
    while True:
        chunk = s.recv(65536)
        if not chunk:
            break
        data += chunk
    s.close()

    # Parse HTTP body
    parts = data.split(b"\r\n\r\n", 1)
    body_str = parts[1].decode() if len(parts) > 1 else data.decode()
    return json.loads(body_str)


# ═══════════════════════════════════════════════════════════════════
# LangGraph Tools — Backed by BunkerVM Sandbox
# ═══════════════════════════════════════════════════════════════════

@tool
def sandbox_exec(command: str, timeout: int = 30) -> str:
    """Execute a shell command inside a hardware-isolated Linux sandbox.

    The sandbox is a full Alpine Linux environment running in a Firecracker
    MicroVM with KVM isolation. Commands run as root. The host is fully
    protected — you can run anything safely.

    Args:
        command: Shell command to execute (e.g., "ls -la /", "python3 -c 'print(42)'")
        timeout: Max seconds to wait (default: 30, max: 300)
    """
    result = _vsock_request("POST", "/exec", {
        "command": command,
        "timeout": min(timeout, 300),
    })

    exit_code = result.get("exit_code", -1)
    stdout = result.get("stdout", "")
    stderr = result.get("stderr", "")
    duration = result.get("duration_ms", 0)

    parts = []
    if exit_code == 0:
        parts.append(f"[OK] ({duration:.0f}ms)")
    else:
        parts.append(f"[EXIT {exit_code}] ({duration:.0f}ms)")

    if stdout:
        parts.append(stdout.rstrip())
    if stderr:
        parts.append(f"STDERR: {stderr.rstrip()}")
    if not stdout and not stderr:
        parts.append("(no output)")

    return "\n".join(parts)


@tool
def sandbox_write_file(path: str, content: str) -> str:
    """Write content to a file inside the sandbox.

    Creates parent directories automatically.

    Args:
        path: Absolute path (e.g., "/root/script.py")
        content: File content to write
    """
    result = _vsock_request("POST", "/write-file", {
        "path": path,
        "content": content,
    })
    if "error" in result:
        return f"[ERROR] {result['error']}"
    return f"Written {result.get('size', 0)} bytes to {path}"


@tool
def sandbox_read_file(path: str) -> str:
    """Read a file from the sandbox filesystem.

    Args:
        path: Absolute path to the file
    """
    result = _vsock_request("POST", "/read-file", {"path": path})
    if "error" in result:
        return f"[ERROR] {result['error']}"
    return result.get("content", "")


@tool
def sandbox_status() -> str:
    """Get sandbox VM status: CPU, memory, disk, uptime, processes."""
    result = _vsock_request("GET", "/status")

    mem = result.get("memory", {})
    total_mb = mem.get("total_bytes", 0) / 1_048_576
    used_mb = mem.get("used_bytes", 0) / 1_048_576

    disk = result.get("disk", {})
    disk_total = disk.get("total_bytes", 0) / 1_048_576
    disk_free = disk.get("free_bytes", 0) / 1_048_576

    return (
        f"Status: {result.get('status', '?')}\n"
        f"Uptime: {result.get('uptime_seconds', 0):.0f}s\n"
        f"CPU: {result.get('cpu', {}).get('cores', '?')} cores\n"
        f"Memory: {used_mb:.0f}/{total_mb:.0f} MB\n"
        f"Disk: {disk_total - disk_free:.0f}/{disk_total:.0f} MB used\n"
        f"Processes: {result.get('processes', '?')}"
    )


# ═══════════════════════════════════════════════════════════════════
# LangGraph Agent
# ═══════════════════════════════════════════════════════════════════

TOOLS = [sandbox_exec, sandbox_write_file, sandbox_read_file, sandbox_status]

SYSTEM_PROMPT = """You are a coding agent with access to a hardware-isolated Linux sandbox.

The sandbox is a full Alpine Linux VM (Firecracker MicroVM) with:
- Python 3.12, shell utilities, networking tools
- Root access — install anything with `apk add <package>`
- 2 CPU cores, 2GB RAM, ~600MB free disk
- KVM hardware isolation — completely safe to run any code

Use the sandbox tools to complete tasks. Write code, run it, iterate.
Always verify your work by checking output.

When writing code:
1. Write the file to the sandbox using sandbox_write_file
2. Run it with sandbox_exec
3. Check the output and fix any issues
"""


def create_agent():
    """Build the LangGraph agent with BunkerVM sandbox tools."""

    # Select LLM
    if LLM_AVAILABLE == "openai":
        llm = ChatOpenAI(model="gpt-4o", max_tokens=4096)
    elif LLM_AVAILABLE == "anthropic":
        llm = ChatAnthropic(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
        )
    else:
        print("ERROR: No LLM package found.")
        print("Install one of:")
        print("  pip install langchain-anthropic")
        print("  pip install langchain-openai")
        sys.exit(1)

    llm_with_tools = llm.bind_tools(TOOLS)

    # Agent function — calls LLM
    def agent(state: MessagesState):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}

    # Should we continue or stop?
    def should_continue(state: MessagesState):
        last = state["messages"][-1]
        if hasattr(last, "tool_calls") and last.tool_calls:
            return "tools"
        return END

    # Build graph
    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent)
    graph.add_node("tools", ToolNode(TOOLS))

    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    return graph.compile()


# ═══════════════════════════════════════════════════════════════════
# Test Scenarios
# ═══════════════════════════════════════════════════════════════════

SCENARIOS = {
    "hello": "Say hello by running 'echo Hello from BunkerVM sandbox!'",

    "sysinfo": (
        "Check the sandbox status, then get detailed system information: "
        "kernel version, CPU info, memory, disk space, and Python version."
    ),

    "code": (
        "Write a Python script that calculates the first 20 Fibonacci numbers "
        "and saves them to /tmp/fibonacci.json as a JSON array. "
        "Then read the file back and verify it's correct."
    ),

    "webserver": (
        "Create a simple Python HTTP server script at /root/server.py that "
        "responds with JSON {\"message\": \"Hello from BunkerVM\", \"timestamp\": <current_unix_time>}. "
        "Start it in the background on port 9090, then use curl to test it, "
        "and finally kill the server."
    ),

    "data_pipeline": (
        "Build a data processing pipeline:\n"
        "1. Create a CSV file at /tmp/sales.csv with 10 rows of sample sales data "
        "(columns: date, product, quantity, price)\n"
        "2. Write a Python script that reads the CSV, calculates total revenue per product, "
        "and outputs a summary\n"
        "3. Run the script and show the results"
    ),

    "compile": (
        "Write a C program that prints the first 10 prime numbers. "
        "Install gcc if needed (apk add gcc musl-dev), compile it, and run it."
    ),
}


def test_connectivity():
    """Quick connectivity check before running tests."""
    try:
        result = _vsock_request("GET", "/health")
        if result.get("status") == "ok":
            print("  Sandbox connected via vsock")
            return True
    except Exception as e:
        print(f"  Connection failed: {e}")
    return False


def run_scenario(agent, name: str, task: str):
    """Run a single test scenario."""
    print(f"\n{'='*60}")
    print(f"SCENARIO: {name}")
    print(f"{'='*60}")
    print(f"Task: {task}\n")

    result = agent.invoke({"messages": [HumanMessage(content=task)]})

    print("\n--- Agent Response ---")
    for msg in result["messages"]:
        role = msg.__class__.__name__.replace("Message", "")
        if role == "AI" and hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                args_str = json.dumps(tc["args"], indent=2)
                print(f"\n[Tool Call: {tc['name']}]")
                print(f"  Args: {args_str[:200]}{'...' if len(args_str) > 200 else ''}")
        elif role == "Tool":
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            preview = content[:500]
            print(f"\n[Tool Result]")
            print(f"  {preview}{'...' if len(content) > 500 else ''}")
        elif role == "AI":
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            if content:
                print(f"\n[Agent]: {content[:800]}")

    print(f"\n{'='*60}\n")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="BunkerVM + LangGraph Integration Test")
    parser.add_argument(
        "scenario",
        nargs="?",
        default="code",
        choices=list(SCENARIOS.keys()) + ["all"],
        help=f"Test scenario to run (default: code). Choices: {', '.join(SCENARIOS.keys())}, all",
    )
    parser.add_argument(
        "--vsock-uds",
        default=VSOCK_UDS,
        help="Path to Firecracker vsock UDS (default: /tmp/bunkervm-vsock.sock)",
    )
    parser.add_argument(
        "--custom",
        type=str,
        default=None,
        help="Run a custom task instead of a preset scenario",
    )
    args = parser.parse_args()

    # Update vsock path if overridden
    _update_vsock_uds(args.vsock_uds)

    print("╔══════════════════════════════════════════╗")
    print("║  BunkerVM + LangGraph Integration Test   ║")
    print("╚══════════════════════════════════════════╝")
    print()

    # Check connectivity
    print("Checking sandbox connectivity...")
    if not test_connectivity():
        print("\nERROR: Cannot connect to BunkerVM sandbox VM.")
        print("Make sure the VM is running:")
        print("  sudo python -m bunkervm")
        sys.exit(1)

    # Check LLM API key
    if LLM_AVAILABLE == "openai" and not os.environ.get("OPENAI_API_KEY"):
        print("\nERROR: OPENAI_API_KEY not set.")
        print("  export OPENAI_API_KEY=sk-...")
        sys.exit(1)
    elif LLM_AVAILABLE == "anthropic" and not os.environ.get("ANTHROPIC_API_KEY"):
        print("\nERROR: ANTHROPIC_API_KEY not set.")
        print("  export ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)

    print(f"  LLM provider: {LLM_AVAILABLE}")
    print()

    # Build agent
    agent = create_agent()

    # Run scenario(s)
    if args.custom:
        run_scenario(agent, "custom", args.custom)
    elif args.scenario == "all":
        for name, task in SCENARIOS.items():
            run_scenario(agent, name, task)
    else:
        run_scenario(agent, args.scenario, SCENARIOS[args.scenario])

    print("Done!")


if __name__ == "__main__":
    main()
