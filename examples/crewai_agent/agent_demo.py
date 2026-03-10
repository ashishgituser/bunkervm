#!/usr/bin/env python3
"""
BunkerVM + CrewAI — Full sandbox toolkit demo.

Shows how to give a CrewAI agent full access to a BunkerVM sandbox
(run commands, write/read files, list directories, upload/download).

The VM boots automatically — no pre-running VM needed.

Prerequisites:
    pip install bunkervm[crewai] python-dotenv
    export OPENAI_API_KEY=your-key-here

Usage:
    python examples/crewai_agent/agent_demo.py
"""

from dotenv import load_dotenv

load_dotenv()

from crewai import Agent, Task, Crew
from bunkervm.crewai import BunkerVMCrewTools


def main():
    print("\n🔒 BunkerVM + CrewAI Demo")
    print("=" * 45)

    # 1. Create tools (auto-boots a Firecracker VM)
    print("\n⏳ Booting sandbox VM...")
    tools = BunkerVMCrewTools()
    print("✅ Sandbox ready\n")

    # 2. Define a CrewAI agent with sandbox tools
    coder = Agent(
        role="Software Engineer",
        goal="Write and test code in a secure sandbox",
        backstory=(
            "You are a Python developer with access to a hardware-isolated "
            "BunkerVM sandbox. You write, save, and run code inside the VM."
        ),
        tools=tools.get_tools(),
        verbose=True,
    )

    # 3. Define a task
    task = Task(
        description=(
            "Write a Python script that sorts a list of 10 random numbers "
            "using bubble sort. Save it to /tmp/sort.py, run it, and "
            "show the sorted output."
        ),
        agent=coder,
        expected_output="The sorted list of numbers printed by the script",
    )

    # 4. Run the crew
    crew = Crew(agents=[coder], tasks=[task], verbose=True)
    result = crew.kickoff()

    print(f"\n🤖 Result: {result}\n")

    # 5. Clean up
    tools.stop()
    print("🧹 Sandbox destroyed.")


if __name__ == "__main__":
    main()
