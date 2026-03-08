"""
BunkerVM + LangGraph — AI agent with hardware-isolated code execution.

Prerequisites:
    pip install bunkervm[langgraph]
    # Start VM in another terminal: sudo python3 -m bunkervm
    # Create .env with OPENAI_API_KEY=sk-...

Usage:
    python test_agent.py
"""
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from bunkervm.langchain import BunkerVMToolkit

load_dotenv()

# ── Setup: 2 lines ──
toolkit = BunkerVMToolkit()  # auto-connects to running VM
agent = create_react_agent(
    ChatOpenAI(model="gpt-4o", temperature=0),
    toolkit.get_tools(),
)

# ── Run it ──
print("\n🔒 BunkerVM + LangGraph\n")
task = (
    "Write a Python script that finds all prime numbers under 100, "
    "save it to /tmp/primes.py, run it, and show me the results."
)
print(f"Task: {task}\n")

result = agent.invoke({"messages": [("human", task)]})

# Print conversation
for msg in result["messages"]:
    if hasattr(msg, "tool_calls") and msg.tool_calls:
        for tc in msg.tool_calls:
            args = tc["args"]
            detail = args.get("command", args.get("path", ""))
            print(f"  🔧 [{tc['name']}] {detail}")
    elif msg.type == "tool":
        print(f"  → {msg.content[:200]}")
    elif msg.type == "ai" and msg.content:
        print(f"\n🤖 {msg.content}\n")

print("✅ Done!")
