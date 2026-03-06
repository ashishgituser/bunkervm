"""
NervOS Audit Logger — Structured event logging (JSONL).

Logs all sandbox operations to a JSONL file for audit, debugging,
and compliance. Each line is a self-contained JSON object with:
  - ISO 8601 timestamp
  - Monotonic sequence number
  - Event type
  - Event-specific payload

Thread-safe: uses a lock for concurrent writes.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any

logger = logging.getLogger("nervos.audit")

_DEFAULT_LOG_DIR = os.path.expanduser("~/.nervos/logs")
_DEFAULT_LOG_FILE = "audit.jsonl"


class AuditLogger:
    """Append-only JSONL audit logger.

    Usage:
        audit = AuditLogger("/var/log/nervos/audit.jsonl")
        audit.log("exec", command="ls -la", exit_code=0)
        audit.log("sandbox_reset")
    """

    def __init__(self, log_path: str | None = None):
        if log_path is None:
            log_path = os.path.join(_DEFAULT_LOG_DIR, _DEFAULT_LOG_FILE)

        self.log_path = log_path
        self._lock = threading.Lock()
        self._sequence = 0

        # Ensure directory exists
        log_dir = os.path.dirname(self.log_path)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

        logger.info("Audit log: %s", self.log_path)

    def log(self, event_type: str, **kwargs: Any) -> None:
        """Append an audit event.

        Args:
            event_type: Event name (e.g., "exec", "read_file", "sandbox_reset").
            **kwargs: Arbitrary key-value pairs for the event payload.
        """
        with self._lock:
            self._sequence += 1
            entry = {
                "seq": self._sequence,
                "ts": time.time(),
                "iso": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
                "event": event_type,
                **kwargs,
            }

            try:
                line = json.dumps(entry, default=str, ensure_ascii=False)
                with open(self.log_path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except Exception as e:
                # Never let audit failures break the server
                logger.error("Failed to write audit log: %s", e)

    def read_recent(self, n: int = 50) -> list[dict]:
        """Read the last N audit entries. For debugging."""
        if not os.path.exists(self.log_path):
            return []

        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            entries = []
            for line in lines[-n:]:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
            return entries
        except Exception as e:
            logger.error("Failed to read audit log: %s", e)
            return []

    @property
    def entry_count(self) -> int:
        """Approximate number of log entries."""
        return self._sequence
