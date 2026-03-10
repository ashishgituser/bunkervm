"""
BunkerVM Framework Integrations.

Shared base and per-framework tool providers for LangChain, OpenAI Agents SDK,
and CrewAI.

Usage (auto-detects installed framework):
    from bunkervm.integrations import get_tools

Or import a specific integration:
    from bunkervm.integrations.langchain import BunkerVMToolkit
    from bunkervm.integrations.openai_agents import BunkerVMTools
    from bunkervm.integrations.crewai import BunkerVMCrewTools
"""

from bunkervm.integrations.base import BunkerVMToolsBase  # noqa: F401

__all__ = ["BunkerVMToolsBase"]
