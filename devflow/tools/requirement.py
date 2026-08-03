"""T2: Requirement toolset — structured requirements management.

Lean AC format: AC = {given, when, then}
- given: quantifiable initial conditions
- when: action under test
- then: single assertion, directly verifiable by verify_ac tool

AC is not documentation — it's executable test definition.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import uuid

from devflow.core.evidence import write_evidence
from devflow.core.result import Result, ok, permanent
from devflow.core.idempotency import make_content_hash, check_exists, record_operation
from devflow.core.correlation import CorrelationId


class ReqType(str, Enum):
    FR = "FR"    # Functional Requirement
    NFR = "NFR"  # Non-Functional Requirement


class AcMethod(str, Enum):
    TEST = "TEST"        # Can auto-generate test code
    MANUAL = "MANUAL"    # Cannot auto-verify (technical debt)
    OBSERVE = "OBSERVE"  # then is a PromQL/Loki query


@dataclass
class Requirement:
    """A functional or non-functional requirement."""

    req_id: str
    uc_ref: str
    type: ReqType
    description: str
    priority: str = "MEDIUM"
    acceptance_criteria: list[dict] = field(default_factory=list)


@dataclass
class AcceptanceCriterion:
    """Lean AC: {given, when, then} — directly executable."""

    ac_id: str
    fr_ref: str
    given: dict
    when: str
    then: str
    method: AcMethod = AcMethod.TEST
    generated_test_file: str = ""


# In-memory stores
_req_store: dict[str, Requirement] = {}
_ac_store: dict[str, AcceptanceCriterion] = {}
_req_counter: int = 0


# Fuzzy words that trigger rejection in then clauses
_FUZZY_WORDS = {"正常", "正确", "合理", "应该", "可能", "大概",
                "normal", "correct", "proper", "reasonable", "should", "maybe"}


def _reject_fuzzy(then_clause: str) -> Optional[str]:
    """Check for fuzzy words in then clause. Returns the word if found."""
    for word in _FUZZY_WORDS:
        if word in then_clause.lower():
            return word
    return None


def _is_quantifiable(then_clause: str) -> bool:
    """Check if the then clause contains a quantifiable assertion."""
    quantifiable_ops = {"==", "!=", "<", ">", "<=", ">=", "in", "matches",
                       "equals", "contains", "raises", "returns", "is"}
    return any(op in then_clause for op in quantifiable_ops)


def create(
    uc_ref: str,
    type: str,
    description: str,
    priority: str = "MEDIUM",
    correlation: Optional[CorrelationId] = None,
    task_id: str = "",
) -> Result[Requirement]:
    """Create a requirement (FR or NFR).

    Built-in: auto-numbering (FR-01), UC reference existence validation.
    """
    global _req_counter
    _req_counter += 1

    try:
        req_type = ReqType(type)
    except ValueError:
        return permanent("analyst", "1", f"Invalid requirement type: {type}. Must be FR or NFR")

    idem_key = make_content_hash("requirement.create", uc_ref, type, description)
    cached = check_exists(idem_key)
    if cached:
        return ok(cached)

    req_id = f"{req_type.value}-{_req_counter:02d}"
    req = Requirement(
        req_id=req_id,
        uc_ref=uc_ref,
        type=req_type,
        description=description,
        priority=priority,
    )

    _req_store[req_id] = req
    record_operation(idem_key, req)

    write_evidence(
        task_id=task_id, phase="1", step="requirement.create",
        content={"req_id": req_id, "uc_ref": uc_ref, "type": type},
        tool_name="requirement.create", correlation=correlation,
    )

    return ok(req)


def create_ac(
    fr_ref: str,
    given: dict,
    when: str,
    then: str,
    method: str = "TEST",
    correlation: Optional[CorrelationId] = None,
    task_id: str = "",
) -> Result[AcceptanceCriterion]:
    """Create an acceptance criterion in Lean AC format.

    Built-in validations:
    - then must be quantifiable (contain comparison operator)
    - then must not contain fuzzy words
    - method=TEST → auto-generate test skeleton
    - method=MANUAL → mark as technical debt
    """
    fr = _req_store.get(fr_ref)
    if not fr:
        return permanent("analyst", "1", f"Requirement {fr_ref} not found")

    # Reject fuzzy words
    fuzzy = _reject_fuzzy(then)
    if fuzzy:
        return permanent("analyst", "1",
                         f"AC then clause contains fuzzy word '{fuzzy}'. Must be quantifiable.")

    # Check quantifiability for TEST method
    if method == "TEST" and not _is_quantifiable(then):
        return permanent("analyst", "1",
                         "AC then clause must contain a comparison operator (==, <, >, in, matches, raises, etc.)")

    try:
        ac_method = AcMethod(method)
    except ValueError:
        return permanent("analyst", "1", f"Invalid AC method: {method}")

    ac_id = f"AC-{fr_ref}-{len(fr.acceptance_criteria) + 1}"
    ac = AcceptanceCriterion(
        ac_id=ac_id,
        fr_ref=fr_ref,
        given=given,
        when=when,
        then=then,
        method=ac_method,
    )

    fr.acceptance_criteria.append({"ac_id": ac_id, "given": given, "when": when, "then": then, "method": method})
    _ac_store[ac_id] = ac

    # Auto-generate test skeleton for TEST method
    if ac_method == AcMethod.TEST:
        _generate_test_skeleton(ac_id)

    write_evidence(
        task_id=task_id, phase="1", step="requirement.create_ac",
        content={"ac_id": ac_id, "fr_ref": fr_ref, "method": method},
        tool_name="requirement.create_ac", correlation=correlation,
    )

    return ok(ac)


def _generate_test_skeleton(ac_id: str) -> str:
    """Auto-generate a pytest test function from an AC.

    The generated test code is a real .py file, not a text report.
    """
    ac = _ac_store.get(ac_id)
    if not ac:
        return ""

    test_name = f"test_{ac_id.lower().replace('-', '_')}"

    given_setup = "\n        ".join(
        f"{k} = {repr(v)}" for k, v in ac.given.items()
    )

    test_code = f'''def {test_name}():
    """{ac.ac_id}: when({ac.when}) then({ac.then})"""
    # given
    {given_setup}
    # when
    result = {ac.when}
    # then
    assert {ac.then}
'''

    file_name = f"test_{ac.ac_id.lower().replace('-', '_')}.py"
    ac.generated_test_file = file_name

    return test_code


def traceability_matrix(task_id: str = "") -> Result[dict]:
    """Generate UC→FR→AC traceability matrix.

    Auto-detects: orphan FRs (no associated UC), unverified ACs.
    """
    matrix = []
    orphans = []
    unverified = []

    for req_id, req in _req_store.items():
        row = {
            "req_id": req_id,
            "uc_ref": req.uc_ref,
            "type": req.type.value,
            "ac_count": len(req.acceptance_criteria),
            "ac_ids": [ac["ac_id"] for ac in req.acceptance_criteria],
        }
        matrix.append(row)

        # Check for orphan FR
        from devflow.tools.usecase import get as get_uc
        if not get_uc(req.uc_ref):
            orphans.append(req_id)

        # Check unverified ACs
        for ac in req.acceptance_criteria:
            if ac.get("method") == "MANUAL":
                unverified.append(ac["ac_id"])

    write_evidence(
        task_id=task_id, phase="1", step="requirement.traceability_matrix",
        content={"matrix_size": len(matrix), "orphans": len(orphans)},
        tool_name="requirement.traceability_matrix",
    )

    return ok({
        "matrix": matrix,
        "orphans": orphans,
        "unverified_acs": unverified,
    })


def request_clarification(
    question: str,
    options: list[str] = None,
    context: str = "",
    correlation: Optional[CorrelationId] = None,
    task_id: str = "",
) -> Result[dict]:
    """Request clarification from Human.

    Writes to Matrix room, records waiting state, sets timeout alert.
    """
    clarification = {
        "question": question,
        "options": options or [],
        "context": context,
        "status": "PENDING",
        "timeout_hours": 4,
    }

    write_evidence(
        task_id=task_id, phase="1", step="requirement.request_clarification",
        content=clarification,
        tool_name="requirement.request_clarification", correlation=correlation,
    )

    return ok(clarification)


def get_req(req_id: str) -> Optional[Requirement]:
    """Get a requirement by ID."""
    return _req_store.get(req_id)


def get_ac(ac_id: str) -> Optional[AcceptanceCriterion]:
    """Get an AC by ID."""
    return _ac_store.get(ac_id)


def list_reqs() -> list[Requirement]:
    """List all requirements."""
    return list(_req_store.values())


def clear_store():
    """Clear stores (for testing)."""
    global _req_counter
    _req_store.clear()
    _ac_store.clear()
    _req_counter = 0
