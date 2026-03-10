#!/usr/bin/env python3
"""
BunkerVM + AI Agent Demo — Secure code execution with LangGraph.

Shows how to run an AI agent that generates and executes code
inside a hardware-isolated BunkerVM sandbox.

For per-framework examples, see:
    examples/langchain_agent/agent_demo.py
    examples/openai_agent/agent_demo.py
    examples/crewai_agent/agent_demo.py

Prerequisites:
    pip install bunkervm[langgraph] langchain-openai python-dotenv
    export OPENAI_API_KEY=your-key-here

Usage:
    python examples/agent_demo.py
"""

from dotenv import load_dotenv

load_dotenv()

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from bunkervm.langchain import BunkerVMToolkit


def main():
    print("\n🔒 BunkerVM Agent Demo")
    print("=" * 40)

    # 1. Create toolkit (auto-boots a Firecracker VM with full sandbox tools)
    toolkit = BunkerVMToolkit()

    agent = create_react_agent(
        ChatOpenAI(model="gpt-4o"),
        tools=toolkit.get_tools(),
    )

    # 2. Ask the agent to write and run code
    prompt = "Write a Python script that finds all prime numbers under 50 and prints them"

    print(f"\nPrompt: {prompt}\n")

    result = agent.invoke({"messages": [("user", prompt)]})

    # 3. Print the result
    for msg in result["messages"]:
        if hasattr(msg, "content") and msg.content:
            print(msg.content)

    # 4. Clean up
    toolkit.stop()
    print("\n✓ Sandbox destroyed")


if __name__ == "__main__":
    main()
