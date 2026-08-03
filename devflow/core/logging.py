"""Structured logging — unified JSON format for all agents.

All agents MUST use this for logging. Logs go to Loki via OTel Collector.
Query: {agent="devflow-developer", action="code_gen.*", result="error"}
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Optional, Any


@dataclass
class LogEntry:
    """Standard log entry format for all DevFlow agents."""

    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S.000Z"))
    correlation: dict[str, str] = field(default_factory=dict)
    agent: str = ""
    action: str = ""
    result: str = "ok"  # ok | error | retry | skip
    input_ref: str = ""
    input_hash: str = ""
    output_ref: str = ""
    output_hash: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str)

    def to_loki(self) -> dict:
        """Format for Loki ingestion (structured metadata labels)."""
        return {
            "ts": self.timestamp,
            "line": self.to_json(),
            "tags": {
                "agent": self.agent,
                "action": self.action,
                "result": self.result,
                "task_id": self.correlation.get("task_id", ""),
                "phase": self.correlation.get("phase", ""),
            },
        }


def structured_log(
    agent: str,
    action: str,
    result: str = "ok",
    correlation: Optional[dict] = None,
    input_ref: str = "",
    output_ref: str = "",
    metrics: Optional[dict] = None,
    errors: Optional[list[str]] = None,
    **extra: Any,
) -> LogEntry:
    """Create a structured log entry.

    All tools call this internally. In production, ships to Loki.
    """
    entry = LogEntry(
        correlation=correlation or {},
        agent=agent,
        action=action,
        result=result,
        input_ref=input_ref,
        output_ref=output_ref,
        metrics=metrics or {},
        errors=errors or [],
    )
    # Append extra fields to metrics
    entry.metrics.update(extra)
    return entry
