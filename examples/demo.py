#!/usr/bin/env python3
"""BunkerVM Demo — AI agent executes code in a hardware-isolated VM."""
import logging, time, sys

logging.basicConfig(level=logging.INFO, format="  %(message)s")

# Suppress noisy loggers
for name in ["httpx", "httpcore", "openai"]:
    logging.getLogger(name).setLevel(logging.WARNING)

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from bunkervm.langchain import BunkerVMToolkit


def print_banner():
    print("\033[1;36m")
    print("  ╔══════════════════════════════════════════════╗")
    print("  ║         🔒 BunkerVM Demo                    ║")
    print("  ║   AI agent + hardware-isolated sandbox      ║")
    print("  ╚══════════════════════════════════════════════╝")
    print("\033[0m")


def print_step(n, text):
    print(f"\n\033[1;33m  [{n}] {text}\033[0m")


def print_result(text):
    print(f"\033[1;32m  {text}\033[0m")


def main():
    load_dotenv()
    print_banner()

    # Step 1: Connect to VM
    print_step(1, "Connecting to BunkerVM...")
    toolkit = BunkerVMToolkit()
    if toolkit.health():
        print_result("✓ Connected to Firecracker MicroVM")
    else:
        print("\033[1;31m  ✗ VM not running. Start with: sudo python3 -m bunkervm\033[0m")
        sys.exit(1)

    # Show VM info
    from bunkervm.sandbox_client import SandboxClient
    c = toolkit.client
    r = c.exec("hostname && uname -r && cat /etc/os-release | grep PRETTY_NAME | cut -d= -f2")
    vm_info = r.get("stdout", "").strip().split("\n")
    if len(vm_info) >= 3:
        print(f"  VM: {vm_info[2].strip('\"')} | Kernel: {vm_info[1]} | Host: {vm_info[0]}")

    # Step 2: Create agent
    print_step(2, "Creating LangGraph agent with GPT-4o...")
    agent = create_react_agent(
        ChatOpenAI(model="gpt-4o", temperature=0),
        toolkit.get_tools(),
    )
    print_result("✓ Agent ready with tools: run_command, write_file, read_file, list_directory")

    # Step 3: Give it a real task
    task = "Write a Python script that calculates the first 10 Fibonacci numbers, save it to /tmp/fib.py, run it, and show results."
    print_step(3, f"Task → \"{task}\"")
    print()

    result = agent.invoke({"messages": [("human", task)]})

    # Print tool calls and final answer
    for msg in result["messages"]:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                args = tc["args"]
                detail = args.get("command", args.get("path", ""))
                print(f"  \033[1;34m⚡ {tc['name']}\033[0m → {detail}")
        elif msg.type == "tool":
            content = msg.content.strip()
            if content and content != "(no output)":
                for line in content.split("\n")[:5]:
                    print(f"     \033[0;37m{line}\033[0m")
        elif msg.type == "ai" and msg.content:
            print(f"\n  \033[1;32m🤖 {msg.content[:200]}\033[0m")

    # Step 4: Prove isolation
    print_step(4, "Proving VM isolation...")
    import platform
    host_hostname = platform.node()
    vm_hostname = c.exec("hostname")["stdout"].strip()
    host_pid1 = open("/proc/1/comm").read().strip()
    vm_pid1 = c.exec("cat /proc/1/comm")["stdout"].strip()

    print(f"  {'':>12} {'HOST':>15}  {'VM (Firecracker)':>18}")
    print(f"  {'Hostname:':>12} {host_hostname:>15}  {vm_hostname:>18}")
    print(f"  {'PID 1:':>12} {host_pid1:>15}  {vm_pid1:>18}")
    print(f"  {'Kernel:':>12} {platform.release()[:15]:>15}  {c.exec('uname -r')['stdout'].strip():>18}")

    print(f"\n  \033[1;32m✅ Code executed inside KVM-isolated Firecracker MicroVM!\033[0m\n")


if __name__ == "__main__":
    main()
