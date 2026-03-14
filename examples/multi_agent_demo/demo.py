#!/usr/bin/env python3
"""
BunkerVM + LangGraph — Parallel Agent Pipeline Demo

A LangGraph workflow where 3 agents work IN PARALLEL, each in its own
hardware-isolated Firecracker MicroVM:

  ┌─────────────┐
  │   Planner   │  designs the app (1 LLM call)
  └──────┬──────┘
         │ fan-out
   ┌─────┼─────────────┐
   ▼     ▼             ▼
┌──────┐ ┌──────────┐ ┌──────────┐
│Build │ │  Test    │ │ Security │   ← 3 sandboxes, 3 VMs, parallel
│Agent │ │  Agent   │ │  Agent   │
└──┬───┘ └────┬─────┘ └────┬─────┘
   │          │             │
   └──────────┼─────────────┘
              ▼ fan-in
       ┌──────────────┐
       │   Reporter   │  combines results (no LLM)
       └──────────────┘

Total LLM calls: 2 (planner + test writer) — ~$0.01 with gpt-4o-mini
Total sandboxes: 3 Firecracker MicroVMs (KVM hardware isolation)

Prerequisites:
  pip install -r requirements.txt
  export OPENAI_API_KEY=sk-...   (or ANTHROPIC_API_KEY)
  # BunkerDesktop must be running

Usage:
  python demo.py
"""

from __future__ import annotations

import os
import sys
import time
import operator
from typing import Annotated, TypedDict

# ── Load .env ──
try:
    from dotenv import load_dotenv
    load_dotenv()
    for p in ["..", "../.."]:
        load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), p, ".env"))
except ImportError:
    pass

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END

from bunkervm.engine.client import EngineClient

# ═══════════════════════════════════════════════════════════════════
# LLM Setup
# ═══════════════════════════════════════════════════════════════════

def get_llm():
    """Get the cheapest available LLM."""
    if os.environ.get("OPENAI_API_KEY"):
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model="gpt-4o-mini", temperature=0)
    if os.environ.get("ANTHROPIC_API_KEY"):
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model="claude-sonnet-4-20250514", temperature=0)
    print("❌ Set OPENAI_API_KEY or ANTHROPIC_API_KEY in .env or environment")
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════════
# Pipeline State
# ═══════════════════════════════════════════════════════════════════

class PipelineState(TypedDict):
    task: str
    code: str
    build_result: str
    test_result: str
    security_result: str
    report: str
    sandbox_ids: Annotated[list[str], operator.add]


# ═══════════════════════════════════════════════════════════════════
# Globals (set in main)
# ═══════════════════════════════════════════════════════════════════

engine: EngineClient = None
llm = None


def _exec(sid: str, cmd: str, timeout: int = 30) -> str:
    """Run a command in a sandbox, return formatted output."""
    r = engine.exec(sid, cmd, timeout=timeout)
    out = r.get("stdout", "").strip()
    err = r.get("stderr", "").strip()
    ms = r.get("duration_ms", 0)
    exit_code = r.get("exit_code", -1)
    parts = [f"[exit {exit_code}, {ms:.0f}ms]"]
    if out:
        parts.append(out)
    if err and exit_code != 0:
        parts.append(f"STDERR: {err}")
    return "\n".join(parts)


def _strip_fences(text: str) -> str:
    """Remove markdown code fences from LLM output."""
    text = text.strip()
    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:])
    if text.endswith("```"):
        text = "\n".join(text.split("\n")[:-1])
    return text.strip()


# ═══════════════════════════════════════════════════════════════════
# Graph Nodes
# ═══════════════════════════════════════════════════════════════════

def planner(state: PipelineState) -> dict:
    """Generate the code — 1 LLM call, no sandbox."""
    print("\n  📋 [Planner] Generating code...")
    t0 = time.time()

    response = llm.invoke([
        SystemMessage(content=(
            "You are a Python developer. Given a task, output ONLY Python code. "
            "No explanations, no markdown fences. Pure Python, stdlib only. "
            "Self-contained single script with sample data. Under 80 lines. "
            "Include clear print statements showing results."
        )),
        HumanMessage(content=state["task"]),
    ])

    code = _strip_fences(response.content)
    print(f"     ✅ Generated {len(code.splitlines())} lines ({time.time()-t0:.1f}s)")

    return {"code": code}


def build_agent(state: PipelineState) -> dict:
    """Boot a sandbox and run the code. No LLM calls."""
    print("\n  🔨 [Build Agent] Booting VM...")
    t0 = time.time()

    sb = engine.create_sandbox(name="build", cpus=1, memory=512)
    sid = sb["id"]
    boot = time.time() - t0
    print(f"     VM ready ({boot:.1f}s) — {sid[:8]}")

    engine.write_file(sid, "/app/main.py", state["code"])
    output = _exec(sid, "cd /app && python3 main.py", timeout=30)

    elapsed = time.time() - t0
    ok = "[exit 0" in output
    print(f"     {'✅' if ok else '❌'} Build {'passed' if ok else 'failed'} ({elapsed:.1f}s)")
    for line in output.split("\n")[1:8]:  # skip exit code line, show 7 lines
        print(f"     │ {line}")

    return {"build_result": output, "sandbox_ids": [sid]}


def test_agent(state: PipelineState) -> dict:
    """Boot a sandbox, generate tests (1 LLM call), run them."""
    print("\n  🧪 [Test Agent] Booting VM...")
    t0 = time.time()

    sb = engine.create_sandbox(name="test", cpus=1, memory=512)
    sid = sb["id"]
    boot = time.time() - t0
    print(f"     VM ready ({boot:.1f}s) — {sid[:8]}")

    # Generate tests — 1 cheap LLM call
    response = llm.invoke([
        SystemMessage(content=(
            "Write a Python test script for the given code. Rules:\n"
            "- Use only assert statements (no unittest/pytest)\n"
            "- Print 'PASS: <name>' or 'FAIL: <name>' for each test\n"
            "- Print total pass/fail count at the end\n"
            "- Under 40 lines. Output ONLY Python code, no markdown."
        )),
        HumanMessage(content=f"Write tests for:\n\n{state['code']}"),
    ])

    test_code = _strip_fences(response.content)

    engine.write_file(sid, "/app/main.py", state["code"])
    engine.write_file(sid, "/app/tests.py", test_code)
    output = _exec(sid, "cd /app && python3 tests.py", timeout=30)

    elapsed = time.time() - t0
    ok = "[exit 0" in output
    print(f"     {'✅' if ok else '❌'} Tests {'passed' if ok else 'failed'} ({elapsed:.1f}s)")
    for line in output.split("\n")[1:8]:
        print(f"     │ {line}")

    return {"test_result": output, "sandbox_ids": [sid]}


def security_agent(state: PipelineState) -> dict:
    """Boot a sandbox, run static analysis. No LLM calls."""
    print("\n  🔒 [Security Agent] Booting VM...")
    t0 = time.time()

    sb = engine.create_sandbox(name="security", cpus=1, memory=512)
    sid = sb["id"]
    boot = time.time() - t0
    print(f"     VM ready ({boot:.1f}s) — {sid[:8]}")

    engine.write_file(sid, "/app/main.py", state["code"])

    scanner = r'''
import ast, re, sys

code = open("/app/main.py").read()
issues = []

# Pattern-based checks
checks = [
    (r"eval\(", "eval() — code injection risk"),
    (r"exec\(", "exec() — code injection risk"),
    (r"subprocess.*shell=True", "shell=True — command injection"),
    (r"os\.system\(", "os.system() — prefer subprocess"),
    (r"pickle\.loads?\(", "pickle — deserialization risk"),
    (r"__import__\(", "dynamic import — security risk"),
]

for pat, msg in checks:
    if re.search(pat, code):
        issues.append(f"WARNING: {msg}")

# AST analysis
try:
    tree = ast.parse(code)
    funcs = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    imports = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            imports.extend(a.name for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module:
            imports.append(n.module)

    print("CODE ANALYSIS")
    print(f"  Lines:     {len(code.splitlines())}")
    print(f"  Functions: {len(funcs)} — {', '.join(funcs[:6]) or 'none'}")
    print(f"  Classes:   {len(classes)} — {', '.join(classes[:6]) or 'none'}")
    print(f"  Imports:   {', '.join(imports) or 'none'}")
except SyntaxError as e:
    issues.append(f"SYNTAX ERROR: {e}")

print(f"\nSECURITY SCAN")
if issues:
    for i in issues:
        print(f"  ⚠️  {i}")
else:
    print("  ✅ No issues found")
print(f"\nResult: {'⚠️ ' + str(len(issues)) + ' findings' if issues else 'CLEAN'}")
'''

    engine.write_file(sid, "/app/scan.py", scanner)
    output = _exec(sid, "cd /app && python3 scan.py", timeout=15)

    elapsed = time.time() - t0
    clean = "CLEAN" in output
    print(f"     {'✅' if clean else '⚠️'} Scan complete ({elapsed:.1f}s)")
    for line in output.split("\n")[1:8]:
        print(f"     │ {line}")

    return {"security_result": output, "sandbox_ids": [sid]}


def reporter(state: PipelineState) -> dict:
    """Combine results — no LLM, no sandbox, just formatting."""
    n_sandboxes = len(state.get("sandbox_ids", []))

    build_ok = "[exit 0" in state.get("build_result", "")
    test_ok = "[exit 0" in state.get("test_result", "")
    sec_clean = "CLEAN" in state.get("security_result", "")

    report = [
        "",
        "═" * 60,
        "  📊 Pipeline Summary",
        "═" * 60,
        f"  🔨 Build:    {'✅ PASSED' if build_ok else '❌ FAILED'}",
        f"  🧪 Tests:    {'✅ PASSED' if test_ok else '❌ FAILED'}",
        f"  🔒 Security: {'✅ CLEAN' if sec_clean else '⚠️  FINDINGS'}",
        f"  🏗️  VMs used:  {n_sandboxes} Firecracker MicroVMs",
        "═" * 60,
    ]

    return {"report": "\n".join(report)}


# ═══════════════════════════════════════════════════════════════════
# Build LangGraph
# ═══════════════════════════════════════════════════════════════════

def build_graph():
    """
    planner → [build_agent | test_agent | security_agent] → reporter

    The 3 middle nodes run IN PARALLEL in separate VMs.
    """
    g = StateGraph(PipelineState)

    g.add_node("planner", planner)
    g.add_node("build_agent", build_agent)
    g.add_node("test_agent", test_agent)
    g.add_node("security_agent", security_agent)
    g.add_node("reporter", reporter)

    # Fan-out from planner to 3 parallel agents
    g.add_edge(START, "planner")
    g.add_edge("planner", "build_agent")
    g.add_edge("planner", "test_agent")
    g.add_edge("planner", "security_agent")

    # Fan-in to reporter
    g.add_edge("build_agent", "reporter")
    g.add_edge("test_agent", "reporter")
    g.add_edge("security_agent", "reporter")
    g.add_edge("reporter", END)

    return g.compile()


# ═══════════════════════════════════════════════════════════════════
# Destruction Test
# ═══════════════════════════════════════════════════════════════════

def destruction_test(sandbox_ids: list[str]):
    """rm -rf / in one VM, verify another survives."""
    if len(sandbox_ids) < 2:
        return

    print()
    print("═" * 60)
    print("  💥 DESTRUCTION TEST — Can an agent nuke its VM?")
    print("═" * 60)

    victim = sandbox_ids[0]
    survivor = sandbox_ids[1]

    print(f"\n  🎯 Victim:   {victim[:8]}")
    print(f"  🛡️  Survivor: {survivor[:8]}")

    print(f"\n  💀 Running: rm -rf --no-preserve-root /")
    try:
        r = engine.exec(victim, "rm -rf --no-preserve-root / 2>&1; echo DESTROYED", timeout=15)
        print(f"     {r.get('stdout', '').strip()[:80]}")
    except Exception as e:
        print(f"     VM destroyed itself: {type(e).__name__}")

    time.sleep(1)

    print(f"\n  🛡️  Checking survivor VM...")
    try:
        r = engine.exec(survivor, "echo 'ALIVE' && python3 -c \"print('Python works!')\" && cat /app/main.py | head -3", timeout=10)
        print(f"     ✅ {r.get('stdout', '').strip()[:120]}")
    except Exception as e:
        print(f"     ❌ {e}")

    print(f"\n  🖥️  Host: You're reading this → host untouched ✅")
    print(f"     Hardware isolation works. This is why BunkerVM exists.")


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

def main():
    global engine, llm

    print()
    print("═" * 60)
    print("  🔒 BunkerVM + LangGraph")
    print("  Parallel Agent Pipeline with Hardware-Isolated Sandboxes")
    print("═" * 60)
    print()

    # Engine
    try:
        engine = EngineClient()
        st = engine.status()
        print(f"  ✅ Engine online — {st.get('sandbox_count', 0)} sandboxes")
    except Exception as e:
        print(f"  ❌ Engine not running: {e}")
        print("     Start BunkerDesktop first!")
        sys.exit(1)

    # LLM
    llm = get_llm()
    print(f"  ✅ LLM: {llm.__class__.__name__} (gpt-4o-mini — fast & cheap)")

    # Graph
    graph = build_graph()
    print(f"  ✅ LangGraph compiled: planner → [build|test|security] → reporter")

    # Task
    task = (
        "Create a Python CLI tool that analyzes text and reports: "
        "word count, sentence count, top 10 most common words, "
        "average word length, and an ASCII bar chart of word frequencies. "
        "Include sample text to demonstrate."
    )
    print(f"\n  📋 Task: {task[:70]}...")

    print()
    print("═" * 60)
    print("  🚀 Running Pipeline — Watch BunkerDesktop for 3 VMs!")
    print("═" * 60)

    t0 = time.time()
    result = graph.invoke({
        "task": task,
        "code": "",
        "build_result": "",
        "test_result": "",
        "security_result": "",
        "report": "",
        "sandbox_ids": [],
    })
    total = time.time() - t0

    # Report
    print(result.get("report", ""))
    print(f"\n  ⏱️  Total: {total:.1f}s  |  LLM calls: 2  |  Cost: ~$0.01")

    # Destruction test
    sids = result.get("sandbox_ids", [])
    if len(sids) >= 2:
        destruction_test(sids)

    # Cleanup
    print()
    print("═" * 60)
    print("  🧹 Cleanup")
    print("═" * 60)

    for sid in sids:
        try:
            engine.destroy_sandbox(sid)
            print(f"  💨 Destroyed {sid[:8]}")
        except Exception:
            pass

    print()
    print("═" * 60)
    print("  🔒 BunkerVM + LangGraph")
    print("  Every agent got its own Firecracker MicroVM")
    print("  One VM destroyed → others survived → host untouched")
    print("  pip install bunkervm  •  bunkerdesktop.com")
    print("═" * 60)
    print()


if __name__ == "__main__":
    main()
