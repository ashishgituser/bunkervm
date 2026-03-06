"""
NervOS Safety Classifier — Regex-based command risk assessment.

Classifies shell commands into safety levels before execution.
This is a defense-in-depth measure — the VM itself is the primary
isolation boundary. Safety classification adds visibility and
optional blocking of obviously destructive commands.

Levels:
  READ        — Read-only commands (ls, cat, ps, free, df)
  WRITE       — File modifications (echo >, mkdir, cp, mv)
  SYSTEM      — System-level changes (apk add, kill, mount)
  DESTRUCTIVE — High-risk operations (rm -rf /, dd of=/dev)
  BLOCKED     — Commands that could break the exec agent itself

Note: Even DESTRUCTIVE commands are safe thanks to VM isolation.
The classification exists for audit trails and optional policy enforcement.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


class SafetyLevel:
    """Command risk levels, ordered from safest to most dangerous."""
    READ = "read"
    WRITE = "write"
    SYSTEM = "system"
    DESTRUCTIVE = "destructive"
    BLOCKED = "blocked"

    _ORDER = {"read": 0, "write": 1, "system": 2, "destructive": 3, "blocked": 4}

    @classmethod
    def severity(cls, level: str) -> int:
        return cls._ORDER.get(level, -1)


@dataclass
class SafetyResult:
    level: str
    command: str
    pattern: Optional[str]
    message: str

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "command": self.command,
            "pattern": self.pattern,
            "message": self.message,
        }


# ── Pattern definitions ──
# Each tuple: (compiled regex, human-readable description)

_BLOCKED_PATTERNS = [
    # Commands that would kill the exec agent or make the VM unresponsive
    (re.compile(r'kill\s+.*\b1\b', re.I), "Killing PID 1 (init) would crash the VM"),
    (re.compile(r'kill\s+-9\s+.*python', re.I), "Killing Python would stop the exec agent"),
    (re.compile(r'pkill\s+.*python', re.I), "Killing Python would stop the exec agent"),
    (re.compile(r':\(\)\s*\{\s*:\|:\s*&\s*\}\s*;', re.I), "Fork bomb detected"),
    (re.compile(r'rm\s+.*\b(exec_agent|nervos)\b', re.I), "Deleting the exec agent"),
]

_DESTRUCTIVE_PATTERNS = [
    (re.compile(r'\brm\s+(-[a-zA-Z]*[rR][a-zA-Z]*\s+)*/\s*$', re.I), "Recursive delete of root filesystem"),
    (re.compile(r'\brm\s+(-[a-zA-Z]*[rR][a-zA-Z]*\s+)*/\s', re.I), "Recursive delete from root"),
    (re.compile(r'\bdd\s+.*of=/dev/', re.I), "Direct write to block device"),
    (re.compile(r'\bmkfs\b', re.I), "Formatting filesystem"),
    (re.compile(r'\bfdisk\b', re.I), "Partition table modification"),
    (re.compile(r'\bparted\b', re.I), "Partition modification"),
    (re.compile(r'>\s*/dev/(sd|vd|hd|nvme|loop)', re.I), "Redirect to block device"),
    (re.compile(r'\bshutdown\b', re.I), "System shutdown"),
    (re.compile(r'\breboot\b', re.I), "System reboot"),
    (re.compile(r'\bhalt\b', re.I), "System halt"),
    (re.compile(r'\binit\s+0\b', re.I), "Runlevel 0 (halt)"),
    (re.compile(r'\bpoweroff\b', re.I), "System poweroff"),
    (re.compile(r'\bswapoff\s+-a\b', re.I), "Disable all swap"),
    (re.compile(r'\bsysrq\b', re.I), "SysRq trigger"),
]

_SYSTEM_PATTERNS = [
    (re.compile(r'\bapk\s+(add|del|remove)\b', re.I), "Package management"),
    (re.compile(r'\bpip3?\s+install\b', re.I), "Python package install"),
    (re.compile(r'\bkill\s', re.I), "Process termination"),
    (re.compile(r'\bkillall\b', re.I), "Process termination (all)"),
    (re.compile(r'\bpkill\b', re.I), "Process termination (pattern)"),
    (re.compile(r'\bmount\b', re.I), "Mount filesystem"),
    (re.compile(r'\bumount\b', re.I), "Unmount filesystem"),
    (re.compile(r'\bchmod\b', re.I), "Change file permissions"),
    (re.compile(r'\bchown\b', re.I), "Change file ownership"),
    (re.compile(r'\bchroot\b', re.I), "Change root directory"),
    (re.compile(r'\biptables\b', re.I), "Firewall rule modification"),
    (re.compile(r'\bip\s+route\b', re.I), "Network route modification"),
    (re.compile(r'\bip\s+addr\s+add\b', re.I), "Network address modification"),
    (re.compile(r'\bsysctl\b', re.I), "Kernel parameter change"),
    (re.compile(r'\bmodprobe\b', re.I), "Kernel module loading"),
    (re.compile(r'\binsmod\b', re.I), "Kernel module insertion"),
    (re.compile(r'\brmmod\b', re.I), "Kernel module removal"),
    (re.compile(r'\bservice\b', re.I), "Service management"),
    (re.compile(r'\brc-service\b', re.I), "Service management"),
    (re.compile(r'\bcrontab\b', re.I), "Cron job management"),
    (re.compile(r'\buseradd\b', re.I), "User creation"),
    (re.compile(r'\buserdel\b', re.I), "User deletion"),
    (re.compile(r'\bpasswd\b', re.I), "Password change"),
]

_WRITE_PATTERNS = [
    (re.compile(r'>\s*\S', re.I), "File redirect (overwrite)"),
    (re.compile(r'>>\s*\S', re.I), "File redirect (append)"),
    (re.compile(r'\btee\b', re.I), "Tee to file"),
    (re.compile(r'\bsed\s+-i\b', re.I), "In-place file edit (sed)"),
    (re.compile(r'\bmkdir\b', re.I), "Directory creation"),
    (re.compile(r'\btouch\b', re.I), "File creation"),
    (re.compile(r'\bcp\b', re.I), "File copy"),
    (re.compile(r'\bmv\b', re.I), "File move/rename"),
    (re.compile(r'\brm\b', re.I), "File deletion"),
    (re.compile(r'\bln\b', re.I), "Link creation"),
    (re.compile(r'\bcurl\b.*-[oO]\b', re.I), "Download to file (curl)"),
    (re.compile(r'\bwget\b', re.I), "Download to file (wget)"),
    (re.compile(r'\btar\b.*-[xz]', re.I), "Archive extraction"),
    (re.compile(r'\bunzip\b', re.I), "ZIP extraction"),
    (re.compile(r'\bgit\s+clone\b', re.I), "Git clone"),
    (re.compile(r'\bpython3?\s+-c\b', re.I), "Python code execution"),
    (re.compile(r'\bnode\s+-e\b', re.I), "Node.js code execution"),
    (re.compile(r'\bperl\s+-e\b', re.I), "Perl code execution"),
]


def classify_command(command: str) -> dict:
    """Classify a shell command's risk level.

    Args:
        command: The shell command string to classify.

    Returns:
        dict with keys: level, command, pattern, message.
    """
    cmd = command.strip()

    # Check each level from most dangerous to least
    for patterns, level in [
        (_BLOCKED_PATTERNS, SafetyLevel.BLOCKED),
        (_DESTRUCTIVE_PATTERNS, SafetyLevel.DESTRUCTIVE),
        (_SYSTEM_PATTERNS, SafetyLevel.SYSTEM),
        (_WRITE_PATTERNS, SafetyLevel.WRITE),
    ]:
        for regex, description in patterns:
            if regex.search(cmd):
                return {
                    "level": level,
                    "command": cmd,
                    "pattern": regex.pattern,
                    "message": description,
                }

    # Default: read-only
    return {
        "level": SafetyLevel.READ,
        "command": cmd,
        "pattern": None,
        "message": "Read-only command",
    }


def is_dangerous(command: str) -> bool:
    """Quick check: is the command DESTRUCTIVE or BLOCKED?"""
    result = classify_command(command)
    return SafetyLevel.severity(result["level"]) >= SafetyLevel.severity(
        SafetyLevel.DESTRUCTIVE
    )
