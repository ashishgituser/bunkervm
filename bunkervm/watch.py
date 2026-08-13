"""Passive recording of coding-agent sessions via Claude Code hooks.

The rest of BunkerVM asks you to change how you run things — wrap your code in
`Sandbox(record=True)`, then compare the sessions afterwards. That's fine for a
deliberate experiment and useless for daily work, because nobody sets up an
experiment before letting an agent loose on a bug.

This module inverts that. `bunkervm watch` installs a PostToolUse hook into
Claude Code's settings, and from then on every command the agent runs in that
repo is appended to a log. You never "use" it. `bunkervm review` then answers
the question you actually have at the end of a session: what did it *do*?

The flag this exists for is `test count dropped`. An agent can turn a red suite
green by deleting the failing test, and `git diff` will show you that deleted
file in the middle of a large diff without you ever registering that the suite
got smaller. A number going down is much harder to skim past.

Design constraints, in priority order:

  1. **Never break the agent.** The hook wraps everything and always exits 0.
     A crash here would surface as a tool error mid-session, which is a far
     worse outcome than losing a log line.
  2. **Never slow the agent down.** The hook only appends a line of JSON; all
     parsing and analysis happens later, in `review`.
  3. **Record, don't interpret.** Raw events go to disk. Interpretation can
     change between versions without invalidating logs already captured.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import sys
import time
from typing import Optional

WATCH_DIRNAME = os.path.join(".bunkervm", "watch")

# PostToolUse fires after the tool has run, so tool_response is populated —
# that's where test output lives. Bash is the one that matters; Edit/Write are
# recorded so file activity is visible without shelling out to git.
_HOOK_MATCHER = "Bash|Edit|Write|NotebookEdit"
_HOOK_EVENT = "PostToolUse"


def hook_command() -> str:
    """The command Claude Code should invoke, as an absolute path when we can
    resolve one.

    Writing a bare "bunkervm _hook" is the obvious thing and it's wrong: the
    common install is `pip install bunkervm` inside a project venv, and the
    shell Claude Code spawns hooks in does not necessarily have that venv on
    PATH. The failure is silent and looks exactly like the feature not working
    — you'd work all day and `review` would report no sessions.
    """
    # argv[0] first, deliberately: it is the interpreter/console script the
    # user actually invoked. Asking PATH instead picks whichever bunkervm comes
    # first globally, so a venv install would silently wire the hook to a
    # different (possibly older) copy than the one being configured.
    exe = ""
    argv0 = sys.argv[0] if sys.argv else ""
    if argv0 and os.path.isabs(argv0) and "bunkervm" in os.path.basename(argv0).lower():
        exe = argv0
    if not exe:
        exe = shutil.which("bunkervm") or ""
    if not exe:
        return "bunkervm _hook"  # last resort; PATH had better be right
    return f'"{exe}" _hook' if " " in exe else f"{exe} _hook"


_MAX_OUTPUT = 20000


# ── Hook installation ──


def settings_path(project_dir: str, scope: str = "project") -> str:
    if scope == "user":
        return os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
    return os.path.join(project_dir, ".claude", "settings.json")


def _load_settings(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _our_hook(entry: dict) -> bool:
    """Is this matcher block one we installed? Matched loosely on shape rather
    than on an exact string, so a hook written by an older version (or by a
    different install path) is still recognised for upgrade and removal. A
    user's own PostToolUse hooks are never touched."""
    for h in entry.get("hooks", []):
        cmd = (h.get("command") or "").strip().replace("\\", "/")
        if cmd.endswith("_hook") and "bunkervm" in cmd.lower():
            return True
    return False


def install_hooks(project_dir: str, scope: str = "project") -> str:
    """Add our PostToolUse hook, preserving any hooks already configured."""
    path = settings_path(project_dir, scope)
    settings = _load_settings(path)

    hooks = settings.setdefault("hooks", {})
    entries = hooks.setdefault(_HOOK_EVENT, [])
    if any(_our_hook(e) for e in entries):
        return path  # already installed; installing twice would double-log

    entries.append(
        {
            "matcher": _HOOK_MATCHER,
            "hooks": [{"type": "command", "command": hook_command()}],
        }
    )

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")
    return path


def uninstall_hooks(project_dir: str, scope: str = "project") -> bool:
    """Remove only our hook. Returns True if something was removed."""
    path = settings_path(project_dir, scope)
    settings = _load_settings(path)
    entries = settings.get("hooks", {}).get(_HOOK_EVENT, [])
    kept = [e for e in entries if not _our_hook(e)]
    if len(kept) == len(entries):
        return False

    if kept:
        settings["hooks"][_HOOK_EVENT] = kept
    else:
        settings["hooks"].pop(_HOOK_EVENT, None)
        if not settings["hooks"]:
            settings.pop("hooks", None)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")
    return True


def is_installed(project_dir: str, scope: str = "project") -> bool:
    entries = (
        _load_settings(settings_path(project_dir, scope)).get("hooks", {}).get(_HOOK_EVENT, [])
    )
    return any(_our_hook(e) for e in entries)


# ── Recording ──


def watch_dir(project_dir: str) -> str:
    return os.path.join(project_dir, WATCH_DIRNAME)


def _response_text(tool_response) -> str:
    """tool_response is documented as {"type": "text", "text": ...} but is not
    guaranteed to be — be permissive rather than lose the event."""
    if isinstance(tool_response, str):
        return tool_response
    if isinstance(tool_response, dict):
        for key in ("text", "stdout", "output", "content"):
            v = tool_response.get(key)
            if isinstance(v, str):
                return v
        return json.dumps(tool_response, default=str)
    if isinstance(tool_response, list):
        return "\n".join(_response_text(x) for x in tool_response)
    return "" if tool_response is None else str(tool_response)


def record_event(payload: dict) -> Optional[str]:
    """Append one hook payload to the session log. Returns the log path.

    Called from the hook, so it must not raise — the caller also guards, but
    keeping the failure modes local makes the guarantee easier to verify.
    """
    cwd = payload.get("cwd") or os.getcwd()
    session_id = payload.get("session_id") or "unknown"
    tool_input = payload.get("tool_input") or {}

    event = {
        "ts": time.time(),
        "tool": payload.get("tool_name", ""),
        "command": tool_input.get("command", ""),
        "file_path": tool_input.get("file_path", ""),
        "description": tool_input.get("description", ""),
        "output": _response_text(payload.get("tool_response"))[:_MAX_OUTPUT],
        "agent_type": payload.get("agent_type", ""),
    }

    d = watch_dir(cwd)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{session_id}.jsonl")
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, default=str) + "\n")
    return path


def load_events(path: str) -> list[dict]:
    events = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # a torn final line shouldn't lose the whole session
    return events


def list_sessions(project_dir: str) -> list[str]:
    """Session logs, newest last."""
    d = watch_dir(project_dir)
    if not os.path.isdir(d):
        return []
    paths = [os.path.join(d, n) for n in os.listdir(d) if n.endswith(".jsonl")]
    return sorted(paths, key=lambda p: os.path.getmtime(p))


# ── Analysis ──

# pytest prints a summary like "1 failed, 4 passed in 0.12s". Deselected tests
# were filtered out by the caller, not removed from the suite, so they never
# count toward the total.
_OUTCOME = re.compile(
    r"(\d+)\s+(passed|failed|skipped|errors?|xfailed|xpassed|todo|pending)\b", re.I
)
_JEST_TOTAL = re.compile(r"^Tests:.*?(\d+)\s+total", re.I | re.M)
_UNITTEST_RAN = re.compile(r"^Ran\s+(\d+)\s+tests?\b", re.I | re.M)
_UNITTEST_SKIP = re.compile(r"\bskipped\s*=\s*(\d+)", re.I)

# Outcomes that mean "this test did not actually assert anything today".
# xfail belongs here: marking a failing test as expected-to-fail silences it
# just as effectively as skipping it, and is a favourite way to reach green.
_SILENCED = {"skipped", "xfailed", "todo", "pending"}


def parse_test_result(output: str) -> Optional[dict]:
    """Outcome counts for a test run, or None if this isn't test output.

    Deliberately format-sniffing rather than command-sniffing: an agent may
    invoke the suite via make, tox, a shell alias or a wrapper script, and the
    output shape is more reliable than the command line.

    Returns total/passed/silenced. `total` alone is not enough — an agent that
    slaps @pytest.mark.skip on the failing test leaves the total untouched, so
    silenced has to be tracked separately or that shortcut is invisible.
    """
    if not output:
        return None

    counts = {}
    for n, word in _OUTCOME.findall(output):
        counts[word.lower().rstrip("s") if word.lower() == "errors" else word.lower()] = int(n)

    total = None
    m = _JEST_TOTAL.search(output)
    if m:
        total = int(m.group(1))
    elif _UNITTEST_RAN.search(output):
        total = int(_UNITTEST_RAN.search(output).group(1))
        m = _UNITTEST_SKIP.search(output)
        if m:
            counts["skipped"] = int(m.group(1))
    elif counts:
        total = sum(counts.values())

    if total is None:
        return None

    silenced = sum(v for k, v in counts.items() if k in _SILENCED)
    # unittest reports "Ran 5 tests" + "OK" and never states a passed count,
    # so infer it rather than reporting 0 for a suite that fully passed.
    passed = counts.get("passed")
    if passed is None:
        broken = counts.get("failed", 0) + counts.get("error", 0) + counts.get("xpassed", 0)
        passed = max(0, total - silenced - broken)
    return {"total": total, "passed": passed, "silenced": silenced}


def parse_test_total(output: str) -> Optional[int]:
    """Total tests a run reported, or None if this isn't test output."""
    result = parse_test_result(output)
    return result["total"] if result else None


_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*")

# Fragments that mean the regex ran off into embedded source rather than a
# real shell argument.
_NOT_A_PATH = re.compile(r"""["'{}()\[\]<>=,]|^\$|^-""")


def _shell_part(command: str) -> str:
    """The portion of a command that is actually shell.

    Everything from a heredoc marker onwards is another language's source, and
    scanning it for shell constructs produces nonsense.
    """
    cut = command.find("<<")
    return command if cut == -1 else command[:cut]


def _raw_shell_statements(command: str) -> list[str]:
    """Split shell source at unquoted statement separators.

    This is intentionally a small shell-ish scanner, not a full parser. It is
    enough for review flags: don't let `; python -c ...` leak into an install
    warning, and treat multi-line commands as multiple statements while leaving
    newlines inside quoted Python snippets alone.
    """
    source = _shell_part(command)
    statements = []
    start = 0
    quote = ""
    escaped = False
    i = 0
    while i < len(source):
        ch = source[i]
        if quote:
            if escaped:
                escaped = False
            elif ch == "\\" and quote == '"':
                escaped = True
            elif ch == quote:
                quote = ""
        elif ch in ("'", '"'):
            quote = ch
        elif ch in (";", "\n"):
            statements.append(source[start:i])
            start = i + 1
        elif source.startswith("&&", i) or source.startswith("||", i):
            statements.append(source[start:i])
            i += 1
            start = i + 1
        i += 1

    statements.append(source[start:])
    return [s.strip() for s in statements if s.strip()]


def _shell_tokens(statement: str) -> list[str]:
    try:
        lex = shlex.shlex(statement, posix=True, punctuation_chars="&|()")
        lex.whitespace_split = True
        lex.commenters = ""
        return list(lex)
    except ValueError:
        return []


def _command_start(tokens: list[str]) -> int:
    i = 0
    if i < len(tokens) and tokens[i] == "sudo":
        i += 1
    while i < len(tokens) and _ASSIGNMENT.match(tokens[i]):
        i += 1
    return i


def _is_install_statement(statement: str) -> bool:
    tokens = _shell_tokens(statement)
    i = _command_start(tokens)
    if i >= len(tokens):
        return False

    cmd = tokens[i].lower()
    nxt = tokens[i + 1].lower() if i + 1 < len(tokens) else ""
    nxt2 = tokens[i + 2].lower() if i + 2 < len(tokens) else ""

    if cmd in ("pip", "pip3") and nxt == "install":
        return True
    if cmd == "uv" and nxt == "pip" and nxt2 == "install":
        return True
    if cmd == "npm" and nxt in ("i", "install", "add"):
        return True
    return (cmd, nxt) in {
        ("yarn", "add"),
        ("pnpm", "add"),
        ("poetry", "add"),
        ("cargo", "add"),
        ("go", "get"),
    }


def _rm_targets(statement: str) -> list[str]:
    tokens = _shell_tokens(statement)
    if "|" in tokens or "|&" in tokens:
        return []

    i = _command_start(tokens)
    if i >= len(tokens) or tokens[i] != "rm":
        return []

    targets = []
    for token in tokens[i + 1 :]:
        if token in ("--help", "--version", "-h"):
            return []
        if token == "--":
            continue
        if token.startswith("-"):
            continue
        targets.append(token)
    return targets


def short_cmd(command: str, limit: int = 60) -> str:
    """One-line, length-capped form of a command, for flag text.

    Real agent commands are frequently multi-line with embedded scripts;
    interpolating one whole into a warning makes the warning unreadable.
    """
    first = command.strip().splitlines()[0].strip() if command.strip() else ""
    return first if len(first) <= limit else first[: limit - 3].rstrip() + "..."

# Deleting build output, caches and vendored deps is routine housekeeping. If
# the deletion flag fires on `rm -rf node_modules` it becomes noise, and a flag
# people learn to ignore is worse than no flag — this one is the whole point of
# the feature, so it stays quiet unless it's about something a human wrote.
_NOISE_DELETE = re.compile(
    r"(^|/)(node_modules|__pycache__|\.pytest_cache|\.mypy_cache|\.ruff_cache"
    r"|dist|build|target|\.venv|venv|coverage|\.coverage|htmlcov|\.tox)(/|$)"
    r"|\.(pyc|pyo|log|tmp|lock)$"
    r"|^/?tmp/",
    re.I,
)


def _is_noise_deletion(path: str) -> bool:
    return bool(_NOISE_DELETE.search(path.replace("\\", "/")))


def _group_by_command(test_runs: list[dict]) -> dict[str, list[dict]]:
    """Runs of the same invocation, in order.

    Comparing the session's first test run against its last is wrong, and
    wrong in the direction that destroys the feature: agents routinely run the
    whole suite and then iterate on one file, so `pytest` (88) followed by
    `pytest -k TestFoo` (8) would scream about 80 deleted tests every single
    session. Grouping by command means the comparison is always like-for-like
    — the same invocation, before and after — which is exactly the shape of
    the case worth catching.
    """
    groups: dict[str, list[dict]] = {}
    for r in test_runs:
        groups.setdefault(r["command"].strip(), []).append(r)
    return groups


def _largest_change(
    test_runs: list[dict], key: str, direction: str
) -> Optional[tuple[int, int, str]]:
    """Biggest first->last movement in `key` among runs of the same command.

    direction "down" finds shrinkage (tests disappearing), "up" finds growth
    (tests being silenced). Returns (first, last, command).
    """
    best = None
    for cmd, runs in _group_by_command(test_runs).items():
        if len(runs) < 2:
            continue
        first, last = runs[0][key], runs[-1][key]
        delta = (first - last) if direction == "down" else (last - first)
        if delta <= 0:
            continue
        if best is None or delta > best[0]:
            best = (delta, first, last, cmd)

    return (best[1], best[2], best[3]) if best else None


def analyze(events: list[dict], project_dir: Optional[str] = None) -> dict:
    """Turn a recorded session into the handful of things worth telling a human.

    Everything here is derived from observed output — no model is asked to
    judge anything.
    """
    commands = [e for e in events if e.get("tool") == "Bash" and e.get("command")]
    edits = [e for e in events if e.get("tool") in ("Edit", "Write", "NotebookEdit")]

    # Only Bash events with a command: an Edit whose *output* happens to contain
    # "1 skipped" is not a test run, and counting it produces a flag attributed
    # to an empty command.
    test_runs = []
    for e in commands:
        result = parse_test_result(e.get("output", ""))
        if result is not None:
            test_runs.append({"command": e["command"], **result})

    installs = []
    for e in commands:
        for statement in _raw_shell_statements(e["command"]):
            if _is_install_statement(statement):
                installs.append(short_cmd(statement))

    deletions = []
    seen_paths = set()
    for e in commands:
        for statement in _raw_shell_statements(e["command"]):
            targets = _rm_targets(statement)
            if not targets:
                continue
            cmd = short_cmd(statement)
            for target in targets:
                path = target.strip("'\"")
                if not path or _NOT_A_PATH.search(path) or _is_noise_deletion(path):
                    continue
                if path in seen_paths:
                    continue
                seen_paths.add(path)
                deletions.append({"path": path, "command": cmd})

    outside = []
    if project_dir:
        # normcase matters on Windows: Claude Code reports cwd as "c:\..." while
        # abspath yields "C:\...", and commonpath compares strings, so without
        # it every single edit gets reported as outside the repo.
        root = os.path.normcase(os.path.abspath(project_dir))
        seen = set()
        for e in edits:
            p = e.get("file_path") or ""
            if not p or p in seen:
                continue
            seen.add(p)
            try:
                if os.path.commonpath([os.path.normcase(os.path.abspath(p)), root]) != root:
                    outside.append(p)
            except ValueError:
                outside.append(p)  # different drive on Windows — definitely outside

    flags = []

    drop = _largest_change(test_runs, "total", "down")
    if drop:
        first, last, cmd = drop
        flags.append(
            {
                "level": "warn",
                "text": (
                    f"test count dropped: {first} -> {last} "
                    f"({first - last} fewer) running `{short_cmd(cmd)}`"
                ),
            }
        )

    # Deleting the test and skipping it reach the same green suite; only the
    # first one changes the total, so this is the other half of the check.
    silenced = _largest_change(test_runs, "silenced", "up")
    if silenced:
        first, last, cmd = silenced
        n = last - first
        flags.append(
            {
                "level": "warn",
                "text": (
                    f"{n} more test{'s' if n > 1 else ''} skipped or xfailed "
                    f"({first} -> {last}) running `{short_cmd(cmd)}` - silenced "
                    f"tests turn a suite green without fixing anything"
                ),
            }
        )

    if deletions:
        shown = ", ".join(d["path"] for d in deletions[:3])
        extra = f" (+{len(deletions) - 3} more)" if len(deletions) > 3 else ""
        flags.append({"level": "warn", "text": f"deleted: {shown}{extra}"})

    if installs:
        flags.append(
            {
                "level": "info",
                "text": f"installed {len(installs)} package(s): {installs[0]}"
                + (f" (+{len(installs) - 1} more)" if len(installs) > 1 else ""),
            }
        )

    if outside:
        shown = ", ".join(outside[:3])
        flags.append({"level": "info", "text": f"wrote outside the repo: {shown}"})

    files = sorted({e["file_path"] for e in edits if e.get("file_path")})
    duration = 0.0
    if len(events) >= 2:
        duration = events[-1].get("ts", 0) - events[0].get("ts", 0)

    return {
        "events": len(events),
        "commands": len(commands),
        "edits": len(edits),
        "files": files,
        "test_runs": test_runs,
        "deletions": deletions,
        "installs": installs,
        "duration_s": duration,
        "flags": flags,
    }
