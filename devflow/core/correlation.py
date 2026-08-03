"""Correlation ID system for full-chain traceability.

Every log line, MinIO file, and EvidenceRecord carries its correlation IDs.
Traceability: just follow the ID chain backward.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass
class CorrelationId:
    """Hierarchical correlation IDs spanning the full task lifecycle."""

    task_id: str                                          # e.g. "task-2026-0042"
    phase: str = ""                                       # "1" | "2" | "3" | "4" | "5"
    agent: str = ""                                       # "analyst" | "architect" | ...
    agent_run_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    llm_call_id: str = ""                                 # per-LLM-call ID
    parent_run_id: str = ""                               # upstream agent run

    @property
    def phase_id(self) -> str:
        return f"{self.task_id}/p{self.phase}"

    @property
    def full_chain(self) -> str:
        """Full correlation chain string for logging."""
        parts = [self.task_id]
        if self.phase:
            parts.append(f"p{self.phase}")
        if self.agent:
            parts.append(self.agent)
        if self.agent_run_id:
            parts.append(self.agent_run_id)
        if self.llm_call_id:
            parts.append(self.llm_call_id)
        return "/".join(parts)

    def child(self, agent: str) -> "CorrelationId":
        """Create a child correlation for a downstream agent."""
        return CorrelationId(
            task_id=self.task_id,
            phase=self.phase,
            agent=agent,
            parent_run_id=self.agent_run_id,
        )

    def with_phase(self, phase: str) -> "CorrelationId":
        """Create a correlation for a new phase."""
        return CorrelationId(task_id=self.task_id, phase=phase)

    def with_llm_call(self) -> "CorrelationId":
        """Create a correlation for a single LLM call."""
        return CorrelationId(
            task_id=self.task_id,
            phase=self.phase,
            agent=self.agent,
            agent_run_id=self.agent_run_id,
            llm_call_id=str(uuid.uuid4())[:8],
            parent_run_id=self.parent_run_id,
        )


def new_correlation(task_type: str = "task") -> CorrelationId:
    """Create a new top-level correlation for a task."""
    task_num = str(uuid.uuid4())[:8]
    return CorrelationId(task_id=f"{task_type}-{task_num}")
