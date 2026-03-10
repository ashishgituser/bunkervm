#!/usr/bin/env python3
"""
BunkerVM + LangChain/LangGraph — Full sandbox toolkit demo.

Shows how to give a LangGraph agent full access to a BunkerVM sandbox
(run commands, write/read files, list directories, upload/download).

The VM boots automatically — no pre-running VM needed.

Prerequisites:
    pip install bunkervm[langgraph] langchain-openai python-dotenv
    export OPENAI_API_KEY=your-key-here

Usage:
    python examples/langchain_agent/agent_demo.py
"""

from dotenv import load_dotenv

load_dotenv()

from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from bunkervm.langchain import BunkerVMToolkit


def main():
    print("\n🔒 BunkerVM + LangGraph Agent Demo")
    print("=" * 45)

    # 1. Create toolkit (auto-boots a Firecracker VM)
    print("\n⏳ Booting sandbox VM...")
    toolkit = BunkerVMToolkit()
    print("✅ Sandbox ready\n")

    # 2. Wire tools into a LangChain ReAct agent
    agent = create_agent(
        ChatOpenAI(model="gpt-4o"),
        tools=toolkit.get_tools(),
    )

    # 3. Ask the agent to do something interesting
    prompt = (
        "Write a Python script that finds all prime numbers under 100, "
        "save it to /tmp/primes.py, run it, and show me the output."
    )
    print(f"Prompt: {prompt}\n")

    result = agent.invoke({"messages": [("user", prompt)]})

    # 4. Print results
    for msg in result["messages"]:
        if hasattr(msg, "content") and msg.content:
            role = getattr(msg, "type", "unknown")
            if role == "ai":
                print(f"🤖 {msg.content}\n")

    # 5. Clean up
    toolkit.stop()
    print("🧹 Sandbox destroyed.")


if __name__ == "__main__":
    main()
