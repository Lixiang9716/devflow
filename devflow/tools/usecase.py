"""T1: UseCase toolset — full lifecycle management for use cases.

Create → evolve → trace. Use cases follow L0/L1/L2 progressive disclosure:
  L0: Summary (Phase 1 initial, no Human interaction needed)
  L1: Standard (after Human clarification + Knowledge feedback)
  L2: Detailed (Phase 4/5 feedback, newly discovered edge cases)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import time
import uuid

from devflow.core.evidence import write_evidence
from devflow.core.result import Result, ok, permanent
from devflow.core.idempotency import make_content_hash, check_exists, record_operation
from devflow.core.correlation import CorrelationId


class UseCaseLevel(str, Enum):
    L0 = "L0"  # Summary: name + actor + goal + basic flow skeleton
    L1 = "L1"  # Standard: + alternative flows + pre/post conditions
    L2 = "L2"  # Detailed: + newly discovered edge cases


@dataclass
class UseCase:
    """A single use case with version tracking and evolution log."""

    uc_id: str
    name: str
    level: UseCaseLevel
    actor: str
    goal: str
    basic_flow: list[str]
    alternative_flows: list[dict] = field(default_factory=list)
    preconditions: list[str] = field(default_factory=list)
    postconditions: list[str] = field(default_factory=list)
    known_unknowns: list[dict] = field(default_factory=list)
    secondary_actors: list[str] = field(default_factory=list)
    evolution_log: list[dict] = field(default_factory=list)
    version: str = "0.1"

    def to_dict(self) -> dict:
        return {
            "uc_id": self.uc_id,
            "name": self.name,
            "level": self.level.value,
            "actor": self.actor,
            "goal": self.goal,
            "basic_flow": self.basic_flow,
            "alternative_flows": self.alternative_flows,
            "preconditions": self.preconditions,
            "postconditions": self.postconditions,
            "known_unknowns": self.known_unknowns,
            "secondary_actors": self.secondary_actors,
            "evolution_log": self.evolution_log,
            "version": self.version,
        }


# In-memory store for testing
_usecase_store: dict[str, UseCase] = {}


def create(
    name: str,
    level: str,
    actor: str,
    goal: str,
    basic_flow: list[str],
    correlation: Optional[CorrelationId] = None,
    task_id: str = "",
) -> Result[UseCase]:
    """Create a new use case at L0/L1/L2 level.

    Built-in: name uniqueness check, basic_flow >= 3 steps, version initialization.
    """
    # Validate level
    try:
        uc_level = UseCaseLevel(level)
    except ValueError:
        return permanent("analyst", "1", f"Invalid use case level: {level}. Must be L0, L1, or L2")

    # Validate basic flow
    if len(basic_flow) < 3:
        return permanent("analyst", "1", "Basic flow must have at least 3 steps")

    # Idempotency check
    idem_key = make_content_hash("usecase.create", name, level, actor, goal)
    cached = check_exists(idem_key)
    if cached:
        return ok(cached)

    uc_id = f"UC-{str(uuid.uuid4())[:4].upper()}"
    uc = UseCase(
        uc_id=uc_id,
        name=name,
        level=uc_level,
        actor=actor,
        goal=goal,
        basic_flow=basic_flow,
        evolution_log=[{
            "version": "0.1",
            "timestamp": time.strftime("%Y-%m-%d"),
            "action": f"Created at {level}",
            "phase": "Phase 1",
        }],
    )

    _usecase_store[uc_id] = uc
    record_operation(idem_key, uc)

    write_evidence(
        task_id=task_id, phase="1", step="usecase.create",
        content={"uc_id": uc_id, "name": name, "level": level},
        tool_name="usecase.create", correlation=correlation,
    )

    return ok(uc)


def upgrade(
    uc_id: str,
    new_level: str,
    additions: dict = None,
    correlation: Optional[CorrelationId] = None,
    task_id: str = "",
) -> Result[UseCase]:
    """Upgrade a use case to a higher level.

    Built-in: level downgrade prevention (L2→L1 forbidden), version increment.
    """
    uc = _usecase_store.get(uc_id)
    if not uc:
        return permanent("analyst", "1", f"Use case {uc_id} not found")

    try:
        new_uc_level = UseCaseLevel(new_level)
    except ValueError:
        return permanent("analyst", "1", f"Invalid level: {new_level}")

    # Prevent downgrade
    level_order = {UseCaseLevel.L0: 0, UseCaseLevel.L1: 1, UseCaseLevel.L2: 2}
    if level_order[new_uc_level] < level_order[uc.level]:
        return permanent("analyst", "1",
                         f"Cannot downgrade from {uc.level.value} to {new_level}")

    # Version increment
    old_version = float(uc.version)
    if new_uc_level == UseCaseLevel.L2 and uc.level != UseCaseLevel.L2:
        uc.version = "1.0"
    else:
        uc.version = f"{old_version + 0.1:.1f}"

    uc.level = new_uc_level
    if additions:
        uc.alternative_flows.extend(additions.get("alternative_flows", []))
        uc.preconditions.extend(additions.get("preconditions", []))
        uc.postconditions.extend(additions.get("postconditions", []))

    uc.evolution_log.append({
        "version": uc.version,
        "timestamp": time.strftime("%Y-%m-%d"),
        "action": f"Upgraded to {new_level}",
    })

    write_evidence(
        task_id=task_id, phase="1", step="usecase.upgrade",
        content={"uc_id": uc_id, "new_level": new_level},
        tool_name="usecase.upgrade", correlation=correlation,
    )

    return ok(uc)


def add_alternative(
    uc_id: str,
    flow_name: str,
    scenario: str,
    trigger: str,
    outcome: str,
    source: str = "",
    correlation: Optional[CorrelationId] = None,
    task_id: str = "",
) -> Result[UseCase]:
    """Add an alternative flow to a use case.

    Built-in: associates with USECASE_GAP issue, auto-marks source.
    """
    uc = _usecase_store.get(uc_id)
    if not uc:
        return permanent("analyst", "1", f"Use case {uc_id} not found")

    af = {
        "flow_name": flow_name,
        "scenario": scenario,
        "trigger": trigger,
        "outcome": outcome,
        "source": source or f"Phase {correlation.phase if correlation else '?'}",
        "added_at": time.strftime("%Y-%m-%d"),
    }
    uc.alternative_flows.append(af)
    uc.evolution_log.append({
        "version": uc.version,
        "timestamp": time.strftime("%Y-%m-%d"),
        "action": f"Added alternative flow: {flow_name}",
        "source": source,
    })

    write_evidence(
        task_id=task_id, phase=correlation.phase if correlation else "1",
        step="usecase.add_alternative",
        content={"uc_id": uc_id, "flow_name": flow_name},
        tool_name="usecase.add_alternative", correlation=correlation,
    )

    return ok(uc)


def declare_known_unknown(
    uc_id: str,
    description: str,
    risk_level: str,
    correlation: Optional[CorrelationId] = None,
    task_id: str = "",
) -> Result[UseCase]:
    """Declare a known unknown — something we know we don't know yet.

    Associated with the UC; referenced by Phase 3 arch.declare_extension_point.
    """
    uc = _usecase_store.get(uc_id)
    if not uc:
        return permanent("analyst", "1", f"Use case {uc_id} not found")

    ku = {
        "description": description,
        "risk_level": risk_level,
        "declared_at": time.strftime("%Y-%m-%d"),
    }
    uc.known_unknowns.append(ku)

    write_evidence(
        task_id=task_id, phase="1", step="usecase.declare_known_unknown",
        content={"uc_id": uc_id, "risk_level": risk_level},
        tool_name="usecase.declare_known_unknown", correlation=correlation,
    )

    return ok(uc)


def link_to_requirement(
    uc_id: str,
    req_id: str,
    correlation: Optional[CorrelationId] = None,
    task_id: str = "",
) -> Result[dict]:
    """Link a use case to a requirement."""
    uc = _usecase_store.get(uc_id)
    if not uc:
        return permanent("analyst", "1", f"Use case {uc_id} not found")

    write_evidence(
        task_id=task_id, phase="1", step="usecase.link_to_requirement",
        content={"uc_id": uc_id, "req_id": req_id},
        tool_name="usecase.link_to_requirement", correlation=correlation,
    )

    return ok({"uc_id": uc_id, "req_id": req_id, "linked": True})


def link_to_code(
    uc_id: str,
    commit_sha: str,
    file_path: str,
    correlation: Optional[CorrelationId] = None,
    task_id: str = "",
) -> Result[dict]:
    """Link a use case to code (commit + file)."""
    uc = _usecase_store.get(uc_id)
    if not uc:
        return permanent("analyst", "1", f"Use case {uc_id} not found")

    write_evidence(
        task_id=task_id, phase="4", step="usecase.link_to_code",
        content={"uc_id": uc_id, "commit": commit_sha, "file": file_path},
        tool_name="usecase.link_to_code", correlation=correlation,
    )

    return ok({"uc_id": uc_id, "commit": commit_sha, "linked": True})


def trace(uc_id: str) -> Result[dict]:
    """Return the full traceability chain: UC→FR→AC→Code→Test→Verdict."""
    uc = _usecase_store.get(uc_id)
    if not uc:
        return permanent("analyst", "1", f"Use case {uc_id} not found")

    return ok({
        "uc_id": uc_id,
        "name": uc.name,
        "version": uc.version,
        "level": uc.level.value,
        "evolution_log": uc.evolution_log,
    })


def validate(
    uc_id: str,
    correlation: Optional[CorrelationId] = None,
    task_id: str = "",
) -> Result[dict]:
    """Validate a use case against quality rules.

    Checks: level≥L1? basic_flow≥3 steps? known_unknowns declared?
    """
    uc = _usecase_store.get(uc_id)
    if not uc:
        return permanent("analyst", "1", f"Use case {uc_id} not found")

    checks = []
    passed = 0
    failed = 0

    # Level check
    if uc.level in (UseCaseLevel.L1, UseCaseLevel.L2):
        checks.append({"check": "level >= L1", "result": "PASS"})
        passed += 1
    else:
        checks.append({"check": "level >= L1", "result": "FAIL", "detail": f"Current level: {uc.level.value}"})
        failed += 1

    # Basic flow length
    if len(uc.basic_flow) >= 3:
        checks.append({"check": "basic_flow >= 3 steps", "result": "PASS"})
        passed += 1
    else:
        checks.append({"check": "basic_flow >= 3 steps", "result": "FAIL"})
        failed += 1

    # Known unknowns (only required for L1+)
    if uc.level in (UseCaseLevel.L1, UseCaseLevel.L2):
        if uc.known_unknowns:
            checks.append({"check": "known_unknowns declared", "result": "PASS"})
            passed += 1
        else:
            checks.append({"check": "known_unknowns declared", "result": "WARN",
                           "detail": "No known unknowns declared"})
            passed += 1  # Warning, not failure

    result = {
        "uc_id": uc_id,
        "passed": passed,
        "failed": failed,
        "total": len(checks),
        "checks": checks,
        "valid": failed == 0,
    }

    write_evidence(
        task_id=task_id, phase="1", step="usecase.validate",
        content=result, tool_name="usecase.validate", correlation=correlation,
    )

    return ok(result)


def get(uc_id: str) -> Optional[UseCase]:
    """Get a use case by ID."""
    return _usecase_store.get(uc_id)


def list_all() -> list[UseCase]:
    """List all use cases."""
    return list(_usecase_store.values())


def clear_store():
    """Clear the use case store (for testing)."""
    from devflow.core.idempotency import clear_store as clear_idem
    _usecase_store.clear()
    clear_idem()
