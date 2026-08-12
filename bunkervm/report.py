"""
BunkerVM Compare/Report — score recorded sessions from data already captured.

No judge model, no rubric library, no LLM scoring. Every number here comes
straight from what record=True already captured for each step: exit code,
duration, the safety classifier's risk tier for the command that ran, and
the filesystem trace. The point is not to be a general eval platform — it's
to answer "which of these agent runs actually did what, and how risky was
it" using facts observed from real execution, not self-reported transcripts.
"""

from __future__ import annotations

import html
import time
from typing import Optional

from .safety import SafetyLevel, classify_command

_RISK_LEVELS = ["read", "write", "system", "destructive", "blocked"]


def score_session(session: dict) -> dict:
    """Score a single recorded session using only data it already contains."""
    checkpoints = session.get("checkpoints", [])
    real_checkpoints = [
        cp for cp in checkpoints if not cp.get("command", "").startswith("[manual checkpoint:")
    ]

    failed = [cp for cp in real_checkpoints if cp.get("exit_code", 0) != 0]
    total_duration_ms = sum(cp.get("duration_ms", 0) for cp in checkpoints)

    risk_counts = {level: 0 for level in _RISK_LEVELS}
    highest_risk = "read"
    for cp in real_checkpoints:
        cmd = cp.get("command", "")
        if not cmd.strip():
            continue
        result = classify_command(cmd)
        level = result["level"]
        risk_counts[level] = risk_counts.get(level, 0) + 1
        if SafetyLevel.severity(level) > SafetyLevel.severity(highest_risk):
            highest_risk = level

    files_created = files_modified = files_deleted = 0
    bytes_written = 0
    for cp in checkpoints:
        trace = cp.get("trace")
        if not trace:
            continue
        files_created += len(trace.get("files_created", []))
        files_modified += len(trace.get("files_modified", []))
        files_deleted += len(trace.get("files_deleted", []))
        bytes_written += trace.get("bytes_written", 0)

    backend = session.get("backend")
    if not backend and checkpoints:
        backend = checkpoints[0].get("backend")

    return {
        "session_id": session.get("session_id", "unknown"),
        "backend": backend or "unknown",
        "steps": len(checkpoints),
        "success": len(failed) == 0,
        "failed_steps": [cp["step"] for cp in failed],
        "total_duration_ms": total_duration_ms,
        "risk_counts": risk_counts,
        "highest_risk": highest_risk,
        "files_created": files_created,
        "files_modified": files_modified,
        "files_deleted": files_deleted,
        "bytes_written": bytes_written,
    }


def compare_sessions(sessions: list[dict], labels: Optional[list[str]] = None) -> dict:
    """Score and rank multiple sessions, and flag where each first diverged
    from the first (baseline) session's command sequence.

    Ranking is transparent, not a black-box composite score: sessions that
    completed without a failed step rank above ones that didn't; among those,
    fewer destructive/blocked commands wins; ties broken by total duration.
    """
    if not sessions:
        raise ValueError("compare_sessions requires at least one session")
    labels = (
        list(labels)
        if labels
        else [s.get("session_id", f"session-{i + 1}") for i, s in enumerate(sessions)]
    )
    if len(labels) != len(sessions):
        raise ValueError("labels must match sessions in length")

    scored = []
    for label, session in zip(labels, sessions):
        s = score_session(session)
        s["label"] = label
        scored.append(s)

    def sort_key(s: dict):
        risky = s["risk_counts"]["destructive"] + s["risk_counts"]["blocked"]
        return (0 if s["success"] else 1, risky, s["total_duration_ms"])

    ranked = sorted(scored, key=sort_key)
    for i, s in enumerate(ranked, 1):
        s["rank"] = i

    by_label = {s["label"]: s for s in ranked}
    ordered = [by_label[label] for label in labels]

    baseline_label = labels[0]
    baseline_cmds = [cp.get("command", "") for cp in sessions[0].get("checkpoints", [])]
    divergences = []
    for label, session in zip(labels[1:], sessions[1:]):
        cmds = [cp.get("command", "") for cp in session.get("checkpoints", [])]
        first_diff = None
        for i in range(min(len(baseline_cmds), len(cmds))):
            if baseline_cmds[i] != cmds[i]:
                first_diff = i + 1
                break
        if first_diff is None and len(baseline_cmds) != len(cmds):
            first_diff = min(len(baseline_cmds), len(cmds)) + 1
        divergences.append(
            {"baseline": baseline_label, "compared": label, "first_diverging_step": first_diff}
        )

    return {"sessions": ordered, "baseline": baseline_label, "divergences": divergences}


# ── HTML report ──

_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>BunkerVM Agent Comparison</title>
<style>
  :root {{
    --bg: #0c0c12; --panel: #14141f; --border: #2a2a4e; --text: #e8e8f0;
    --dim: #8a8aa0; --accent: #7c5cfc; --green: #34d399; --red: #f87171;
    --yellow: #fbbf24;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    background: var(--bg); color: var(--text); margin: 0; padding: 40px 24px;
    font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
  }}
  .wrap {{ max-width: 920px; margin: 0 auto; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  .sub {{ color: var(--dim); font-size: 14px; margin-bottom: 28px; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 28px; }}
  th, td {{ text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--border); font-size: 14px; }}
  th {{ color: var(--dim); font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }}
  tr:hover {{ background: var(--panel); }}
  .rank-1 {{ color: var(--green); font-weight: 700; }}
  .ok {{ color: var(--green); }}
  .fail {{ color: var(--red); }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-family: Menlo, Consolas, monospace; }}
  .badge.read {{ background: #1e2a3a; color: #7dd3fc; }}
  .badge.write {{ background: #2a2a1e; color: var(--yellow); }}
  .badge.system {{ background: #2a1e33; color: #d8b4fe; }}
  .badge.destructive, .badge.blocked {{ background: #331e1e; color: var(--red); }}
  code {{ font-family: Menlo, Consolas, monospace; background: var(--panel); padding: 1px 5px; border-radius: 4px; }}
  .note {{ color: var(--dim); font-size: 13px; margin-top: -14px; margin-bottom: 28px; }}
  .divergence {{ font-size: 14px; margin-bottom: 6px; }}
  footer {{ color: var(--dim); font-size: 12px; margin-top: 40px; border-top: 1px solid var(--border); padding-top: 16px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>Agent Comparison</h1>
  <div class="sub">{n} sessions &middot; generated {generated}</div>

  <table>
    <thead>
      <tr><th>Rank</th><th>Session</th><th>Backend</th><th>Steps</th><th>Result</th>
          <th>Time</th><th>Risk profile</th><th>Files +/~/-</th></tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>
  <div class="note">Ranked by: completed without a failed step, then fewest destructive/blocked commands, then total time. No judge model — every column above is a fact captured during the actual recorded run.</div>

  {divergence_block}

  <footer>Generated by <code>bunkervm compare</code> from data already captured by <code>Sandbox(record=True)</code> — command outcomes, per-command risk tier ({risk_note}), and filesystem trace. Not an LLM-graded evaluation.</footer>
</div>
</body>
</html>
"""

_ROW_TEMPLATE = """<tr>
  <td class="{rank_cls}">#{rank}</td>
  <td><code>{label}</code></td>
  <td>{backend}</td>
  <td>{steps}</td>
  <td class="{result_cls}">{result}</td>
  <td>{duration:.0f}ms</td>
  <td>{risk_badges}</td>
  <td>+{created} ~{modified} -{deleted}</td>
</tr>"""


def render_html_report(comparison: dict, path: str) -> str:
    """Render a compare_sessions() result to a self-contained HTML file."""
    rows = []
    for s in comparison["sessions"]:
        risk_badges = (
            " ".join(
                f'<span class="badge {level}">{level} &times;{count}</span>'
                for level, count in s["risk_counts"].items()
                if count
            )
            or '<span class="badge read">none</span>'
        )

        rows.append(
            _ROW_TEMPLATE.format(
                rank_cls="rank-1" if s["rank"] == 1 else "",
                rank=s["rank"],
                label=html.escape(s["label"]),
                backend=html.escape(s["backend"]),
                steps=s["steps"],
                result_cls="ok" if s["success"] else "fail",
                result=(
                    "completed"
                    if s["success"]
                    else f"failed (step {s['failed_steps'][0] if s['failed_steps'] else '?'})"
                ),
                duration=s["total_duration_ms"],
                risk_badges=risk_badges,
                created=s["files_created"],
                modified=s["files_modified"],
                deleted=s["files_deleted"],
            )
        )

    divergence_lines = []
    for d in comparison["divergences"]:
        if d["first_diverging_step"] is None:
            divergence_lines.append(
                f'<div class="divergence"><code>{html.escape(d["compared"])}</code> ran identical commands to baseline <code>{html.escape(d["baseline"])}</code>.</div>'
            )
        else:
            divergence_lines.append(
                f'<div class="divergence"><code>{html.escape(d["compared"])}</code> first diverged from baseline <code>{html.escape(d["baseline"])}</code> at step {d["first_diverging_step"]}.</div>'
            )
    divergence_block = ""
    if divergence_lines:
        divergence_block = (
            "<h2 style='font-size:15px;margin-bottom:10px;'>Divergence from baseline</h2>"
            + "\n".join(divergence_lines)
        )

    doc = _HTML_TEMPLATE.format(
        n=len(comparison["sessions"]),
        generated=time.strftime("%Y-%m-%d %H:%M"),
        rows="\n".join(rows),
        divergence_block=divergence_block,
        risk_note="/".join(_RISK_LEVELS),
    )

    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)
    return path
