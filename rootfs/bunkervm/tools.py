#!/usr/bin/env python3
"""
BunkerVM Dynamic Executor — the OS itself is the tool.

No hardcoded tools. The model outputs shell commands, we execute them
and return stdout/stderr. The model interprets results and decides
what to do next. Any command the OS supports, BunkerVM can run.
"""

import subprocess
import os


def execute(cmd: str, timeout: int = 30) -> dict:
    """Execute any shell command and return structured output."""
    if not cmd or not cmd.strip():
        return {"ok": False, "error": "empty command"}
    try:
        r = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "TERM": "dumb", "COLUMNS": "120"},
        )
        result = {"ok": r.returncode == 0, "exit": r.returncode}
        if r.stdout.strip():
            result["out"] = r.stdout.strip()[:4096]
        if r.stderr.strip():
            result["err"] = r.stderr.strip()[:1024]
        return result
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"timeout ({timeout}s)"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:256]}
