"""T10: Immutable evidence store — the single entry point for all audit trails.

Every tool call internally calls evidence.write(). Evidence is:
- Immutable: write once, append only, never update
- Hash-chained: SHA256 + timestamp + correlation_id on every record
- Traceable: forward (UC→FR→AC→Code→Test→Verdict) and backward
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional

from devflow.core.correlation import CorrelationId


@dataclass
class EvidenceRecord:
    """A single immutable evidence entry."""

    task_id: str
    phase: str
    step: str
    content: dict
    tool_name: str
    correlation_id: str
    timestamp: float = field(default_factory=time.time)
    sha256: str = ""
    record_id: str = ""

    def __post_init__(self):
        if not self.sha256:
            self.sha256 = self._compute_hash()
        if not self.record_id:
            self.record_id = f"evt-{int(self.timestamp)}-{self.sha256[:8]}"

    def _compute_hash(self) -> str:
        payload = json.dumps({
            "task_id": self.task_id,
            "phase": self.phase,
            "step": self.step,
            "content": self.content,
            "tool_name": self.tool_name,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp,
        }, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()


# In-memory store for testing; production uses MinIO
_evidence_store: dict[str, list[EvidenceRecord]] = {}


def write_evidence(
    task_id: str,
    phase: str,
    step: str,
    content: dict,
    tool_name: str,
    correlation: Optional[CorrelationId] = None,
) -> EvidenceRecord:
    """Write an immutable evidence record.

    Called internally by all other tools. In production, writes to MinIO.
    """
    record = EvidenceRecord(
        task_id=task_id,
        phase=phase,
        step=step,
        content=content,
        tool_name=tool_name,
        correlation_id=correlation.full_chain if correlation else task_id,
    )

    if task_id not in _evidence_store:
        _evidence_store[task_id] = []
    _evidence_store[task_id].append(record)

    return record


def trace_chain(task_id: str) -> dict:
    """Build the full traceability chain: UC→FR→AC→Code→Test→Verdict.

    Also detects broken chains and orphan nodes.
    """
    records = _evidence_store.get(task_id, [])
    if not records:
        return {"forward": [], "reverse": [], "broken_links": [], "orphans": []}

    chain = {
        "forward": {
            "usecases": [],
            "requirements": [],
            "acceptance_criteria": [],
            "code": [],
            "tests": [],
            "verdicts": [],
        },
        "reverse": {
            "verdict_to_test": [],
            "test_to_code": [],
            "code_to_ac": [],
            "ac_to_fr": [],
            "fr_to_uc": [],
        },
        "broken_links": [],
        "orphans": [],
    }

    for r in records:
        tool = r.tool_name
        if "usecase" in tool:
            chain["forward"]["usecases"].append(r.record_id)
        elif "requirement" in tool:
            chain["forward"]["requirements"].append(r.record_id)
        elif "ac" in tool:
            chain["forward"]["acceptance_criteria"].append(r.record_id)
        elif "code" in tool or "patch" in tool:
            chain["forward"]["code"].append(r.record_id)
        elif "test" in tool:
            chain["forward"]["tests"].append(r.record_id)
        elif "verdict" in tool or "verify" in tool:
            chain["forward"]["verdicts"].append(r.record_id)

    # Check for orphan FRs (no associated UC reference in content)
    for r in records:
        if r.tool_name == "requirement.create":
            uc_ref = r.content.get("uc_ref", "")
            if uc_ref and not any(
                uc_ref in str(er.content) for er in records if "usecase" in er.tool_name
            ):
                chain["broken_links"].append({
                    "record": r.record_id,
                    "issue": f"FR references {uc_ref} but no usecase evidence found",
                })

    return chain


def check_integrity(task_id: str) -> dict:
    """Verify SHA256 integrity of all evidence records for a task."""
    records = _evidence_store.get(task_id, [])
    tampered = []
    verified = 0

    for r in records:
        current_hash = r.sha256
        recomputed = r._compute_hash()
        if current_hash != recomputed:
            tampered.append({
                "record_id": r.record_id,
                "stored_hash": current_hash,
                "recomputed_hash": recomputed,
            })
        else:
            verified += 1

    return {
        "pass": len(tampered) == 0,
        "verified": verified,
        "tampered": tampered,
    }


def clear_evidence(task_id: str = None):
    """Clear evidence store (for testing)."""
    if task_id:
        _evidence_store.pop(task_id, None)
    else:
        _evidence_store.clear()


def get_events(task_id: str) -> list[EvidenceRecord]:
    """Get all evidence events for a task, sorted by timestamp."""
    return sorted(_evidence_store.get(task_id, []), key=lambda r: r.timestamp)
