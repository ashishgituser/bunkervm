"""
BunkerVM MCP Server — Tool definitions.

Exposes sandbox operations as MCP tools that any AI model can call.
Each tool routes to the exec agent running inside the Firecracker MicroVM.

Tools:
  sandbox_exec        — Run any shell command (the core tool)
  sandbox_read_file   — Read file contents
  sandbox_write_file  — Write/create files
  sandbox_list_dir    — List directory contents
  sandbox_status      — VM health, CPU, RAM, disk, uptime
  sandbox_reset       — Destroy and recreate the sandbox
"""

from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

from .safety import classify_command, SafetyLevel

logger = logging.getLogger("bunkervm.mcp")

# ── Global state (set by __main__.py before server starts) ──
_client = None       # SandboxClient
_audit = None        # AuditLogger
_vm_manager = None   # VMManager (optional)
_config = None       # BunkerVMConfig


def set_globals(client, audit, vm_manager=None, config=None):
    """Set shared state for MCP tool handlers."""
    global _client, _audit, _vm_manager, _config
    _client = client
    _audit = audit
    _vm_manager = vm_manager
    _config = config


def _get_client():
    if _client is None:
        raise RuntimeError("Sandbox not initialized — server misconfiguration")
    return _client


def _get_audit():
    if _audit is None:
        raise RuntimeError("Audit logger not initialized")
    return _audit


def create_server() -> FastMCP:
    """Create and return the configured MCP server instance."""
    return mcp


# ── MCP Server ──

mcp = FastMCP(
    "bunkervm",
    instructions=(
        "Hardware-isolated Linux sandbox powered by Firecracker MicroVM. "
        "Execute shell commands, read/write files, and manage a secure "
        "sandbox environment. All operations run inside a KVM-isolated "
        "virtual machine — completely safe for the host system."
    ),
)


# ── Tool: Execute Command ──

@mcp.tool()
def sandbox_exec(
    command: str,
    timeout: int = 30,
    workdir: str = "/root",
) -> str:
    """Execute a shell command inside the hardware-isolated Linux sandbox.

    The sandbox is a full Alpine Linux environment running in a Firecracker
    MicroVM with KVM hardware isolation. Commands run as root inside the VM.
    The host system is completely protected.

    Common uses:
    - Run any Linux command: ls, cat, grep, awk, sed, curl, python3, etc.
    - Install packages: apk add <package>
    - Compile and run code
    - Inspect system state: ps, top, free, df, ip addr
    - Process data, transform files, run scripts

    Args:
        command: Shell command to execute (e.g., "ls -la /", "python3 -c 'print(1+1)'")
        timeout: Maximum execution time in seconds (1-300, default: 30)
        workdir: Working directory for the command (default: /root)

    Returns:
        Command output with exit code, stdout, stderr, safety classification,
        and execution duration.
    """
    client = _get_client()
    audit = _get_audit()

    # Classify command safety
    safety = classify_command(command)
    timeout = max(1, min(timeout, 300))

    audit.log(
        "exec",
        command=command,
        safety_level=safety["level"],
        timeout=timeout,
        workdir=workdir,
    )

    # Check if blocked
    if safety["level"] == SafetyLevel.BLOCKED and _config and _config.enforce_safety:
        audit.log("exec_blocked", command=command, reason=safety["message"])
        return (
            f"[BLOCKED] Command rejected by safety policy.\n"
            f"Reason: {safety['message']}\n"
            f"Command: {command}\n\n"
            f"The sandbox blocks commands that could destroy the VM's ability to function. "
            f"You can still run most commands. If you need this specific operation, "
            f"ask the user to disable safety enforcement in bunkervm.toml."
        )

    # Execute
    try:
        result = client.exec(command, timeout=timeout, workdir=workdir)
    except ConnectionError as e:
        audit.log("exec_error", command=command, error=str(e))
        return f"[ERROR] Sandbox unreachable: {e}\nThe VM may have crashed or not started yet."
    except Exception as e:
        audit.log("exec_error", command=command, error=str(e))
        return f"[ERROR] {e}"

    # Format response
    exit_code = result.get("exit_code", -1)
    stdout = result.get("stdout", "")
    stderr = result.get("stderr", "")
    duration = result.get("duration_ms", 0)
    timed_out = result.get("timed_out", False)
    truncated = result.get("truncated", False)

    audit.log(
        "exec_result",
        command=command,
        exit_code=exit_code,
        stdout_bytes=len(stdout),
        stderr_bytes=len(stderr),
        duration_ms=duration,
        timed_out=timed_out,
    )

    parts = []

    # Header line
    safety_tag = f"[{safety['level'].upper()}]" if safety["level"] != SafetyLevel.READ else ""
    if timed_out:
        parts.append(f"[TIMEOUT after {timeout}s] {safety_tag}")
    elif exit_code == 0:
        parts.append(f"[OK] {safety_tag} ({duration:.0f}ms)")
    else:
        parts.append(f"[EXIT {exit_code}] {safety_tag} ({duration:.0f}ms)")

    if stdout:
        parts.append(stdout)
    if stderr:
        parts.append(f"--- stderr ---\n{stderr}")
    if not stdout and not stderr:
        parts.append("(no output)")
    if truncated:
        parts.append("(output truncated)")

    return "\n".join(parts)


# ── Tool: Read File ──

@mcp.tool()
def sandbox_read_file(path: str) -> str:
    """Read the contents of a file from the sandbox filesystem.

    Supports text files (returned as UTF-8) and binary files (returned as
    base64). Maximum file size: 2MB.

    Args:
        path: Absolute path to the file (e.g., "/etc/os-release", "/root/output.txt")

    Returns:
        File contents as text, or base64-encoded string for binary files.
    """
    client = _get_client()
    audit = _get_audit()

    audit.log("read_file", path=path)

    try:
        result = client.read_file(path)
    except Exception as e:
        return f"[ERROR] {e}"

    if "error" in result:
        return f"[ERROR] {result['error']}"

    content = result.get("content", "")
    encoding = result.get("encoding", "utf-8")
    size = result.get("size", 0)

    if encoding == "base64":
        return f"[Binary file: {path}, {size} bytes, base64-encoded]\n{content}"

    return content


# ── Tool: Write File ──

@mcp.tool()
def sandbox_write_file(path: str, content: str, append: bool = False) -> str:
    """Write content to a file in the sandbox filesystem.

    Creates parent directories automatically. Can overwrite or append.

    Args:
        path: Absolute path for the file (e.g., "/root/script.py", "/tmp/data.json")
        content: Text content to write
        append: If true, append to existing file instead of overwriting

    Returns:
        Confirmation with file path and final size.
    """
    client = _get_client()
    audit = _get_audit()

    mode = "append" if append else "overwrite"
    audit.log("write_file", path=path, content_length=len(content), mode=mode)

    try:
        result = client.write_file(path, content, mode=mode)
    except Exception as e:
        return f"[ERROR] {e}"

    if "error" in result:
        return f"[ERROR] {result['error']}"

    size = result.get("size", 0)
    return f"Written {size} bytes to {path}"


# ── Tool: List Directory ──

@mcp.tool()
def sandbox_list_dir(path: str = "/") -> str:
    """List the contents of a directory in the sandbox.

    Returns file names, types (file/directory/symlink), sizes, and permissions.

    Args:
        path: Directory path to list (default: "/")

    Returns:
        Formatted directory listing.
    """
    client = _get_client()

    try:
        result = client.list_dir(path)
    except Exception as e:
        return f"[ERROR] {e}"

    if "error" in result:
        return f"[ERROR] {result['error']}"

    entries = result.get("entries", [])
    count = result.get("count", len(entries))

    if not entries:
        return f"Directory {path} is empty"

    lines = [f"Directory: {path}  ({count} entries)\n"]
    for e in entries:
        type_char = {"directory": "d", "symlink": "l", "file": "-"}.get(e.get("type", ""), "?")
        size = f"{e['size']:>10,}" if e.get("size") is not None else "         -"
        perm = e.get("permissions", "---")
        name = e.get("name", "?")
        if e.get("type") == "directory":
            name += "/"
        lines.append(f"  {type_char} {perm} {size}  {name}")

    return "\n".join(lines)


# ── Tool: Sandbox Status ──

@mcp.tool()
def sandbox_status() -> str:
    """Get the current status of the sandbox VM.

    Returns system information including hostname, uptime, CPU, memory usage,
    disk usage, load average, and process count.
    """
    client = _get_client()

    try:
        status = client.status()
    except Exception as e:
        return f"[ERROR] Sandbox unreachable: {e}"

    lines = [f"Sandbox Status: {status.get('status', 'unknown')}\n"]

    if "hostname" in status:
        lines.append(f"  Hostname:    {status['hostname']}")

    if "uptime_seconds" in status:
        s = int(status["uptime_seconds"])
        h, s = divmod(s, 3600)
        m, s = divmod(s, 60)
        lines.append(f"  Uptime:      {h}h {m}m {s}s")

    if "cpu" in status:
        cpu = status["cpu"]
        lines.append(f"  CPU:         {cpu.get('model', 'unknown')} ({cpu.get('cores', '?')} cores)")

    if "memory" in status:
        mem = status["memory"]
        total = mem.get("total_bytes", 0) / 1_048_576
        used = mem.get("used_bytes", 0) / 1_048_576
        available = mem.get("available_bytes", mem.get("free_bytes", 0)) / 1_048_576
        pct = (used / total * 100) if total > 0 else 0
        lines.append(f"  Memory:      {used:.0f} / {total:.0f} MB ({pct:.0f}% used, {available:.0f} MB available)")

    if "disk" in status:
        disk = status["disk"]
        total = disk.get("total_bytes", 0) / 1_048_576
        used = disk.get("used_bytes", 0) / 1_048_576
        free = disk.get("free_bytes", 0) / 1_048_576
        pct = (used / total * 100) if total > 0 else 0
        lines.append(f"  Disk:        {used:.0f} / {total:.0f} MB ({pct:.0f}% used, {free:.0f} MB free)")

    if "load" in status:
        ld = status["load"]
        lines.append(f"  Load (1/5/15m): {ld.get('1m', 0):.2f} / {ld.get('5m', 0):.2f} / {ld.get('15m', 0):.2f}")

    if "processes" in status:
        lines.append(f"  Processes:   {status['processes']}")

    return "\n".join(lines)


# ── Tool: Reset Sandbox ──

@mcp.tool()
def sandbox_reset() -> str:
    """Reset the sandbox to a clean state.

    Destroys the current VM and boots a fresh one from the base rootfs image.
    All files created, packages installed, and changes made will be lost.
    Takes approximately 5-15 seconds.

    Use this when you need a clean environment or if the sandbox is in a
    broken state.
    """
    audit = _get_audit()
    audit.log("sandbox_reset")

    if _vm_manager is None:
        return (
            "[ERROR] VM manager not available. The sandbox was started externally.\n"
            "Reset it manually by restarting the Firecracker process."
        )

    try:
        logger.info("Resetting sandbox VM...")
        _vm_manager.restart()

        # Wait for new VM
        client = _get_client()
        if client.wait_for_health(timeout=30):
            audit.log("sandbox_reset_complete")
            return "Sandbox reset complete. Fresh environment ready."
        else:
            audit.log("sandbox_reset_timeout")
            return "[WARNING] Sandbox reset initiated but health check timed out. It may still be booting."
    except Exception as e:
        audit.log("sandbox_reset_error", error=str(e))
        return f"[ERROR] Reset failed: {e}"
