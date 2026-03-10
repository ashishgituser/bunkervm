#!/usr/bin/env python3
"""
BunkerVM + OpenAI Agents SDK — Full sandbox toolkit demo.

Shows how to give an OpenAI Agents SDK agent full access to a BunkerVM
sandbox (run commands, write/read files, list directories, upload/download).

The VM boots automatically — no pre-running VM needed.

Prerequisites:
    pip install bunkervm[openai-agents] python-dotenv
    export OPENAI_API_KEY=your-key-here

Usage:
    python examples/openai_agent/agent_demo.py
"""

from dotenv import load_dotenv

load_dotenv()

from agents import Agent, Runner
from bunkervm.openai_agents import BunkerVMTools


def main():
    print("\n🔒 BunkerVM + OpenAI Agents SDK Demo")
    print("=" * 45)

    # 1. Create tools (auto-boots a Firecracker VM)
    print("\n⏳ Booting sandbox VM...")
    tools = BunkerVMTools()
    print("✅ Sandbox ready\n")

    # 2. Create an agent with sandbox tools
    agent = Agent(
        name="sandbox-coder",
        instructions=(
            "You are a coding assistant with access to a secure sandbox. "
            "Write code, save files, and run them inside the sandbox."
        ),
        tools=tools.get_tools(),
    )

    # 3. Run a task
    prompt = (
        "Write a Python script that generates the first 20 Fibonacci numbers, "
        "save it to /tmp/fib.py, run it, and show me the output."
    )
    print(f"Prompt: {prompt}\n")

    result = Runner.run_sync(agent, prompt)

    # 4. Print results
    print(f"🤖 {result.final_output}\n")

    # 5. Clean up
    tools.stop()
    print("🧹 Sandbox destroyed.")


if __name__ == "__main__":
    main()
