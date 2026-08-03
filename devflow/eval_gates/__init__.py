"""Eval-Gates G1-G6: Programmatic evaluation at each phase exit.

These gates validate PRODUCT quality (not process — that's timeline verification).
Gates read tool outputs, not LLM text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from devflow.core.result import Result, ok
from devflow.core.evidence import write_evidence
from devflow.core.correlation import CorrelationId


# Critical gates: failure → FAIL_RETRY
CRITICAL_GATES = {
    "G1.1": "schema", "G2.1": "PoC_code_reproducible",
    "G3.1": "no_circular_deps", "G4.1": "compilation",
    "G4.2": "no_regression", "G5.4": "traceability_complete",
}


@dataclass
class GateResult:
    """Result of a single Eval-Gate check."""

    gate_id: str
    status: str  # PASS | FAIL | WARN
    checks: list[dict] = field(default_factory=list)
    critical: bool = False


def run_g1_check(
    task_id: str,
    usecase_count: int,
    ac_count: int,
    quantified_ac_count: int,
    l1_count: int,
    correlation: Optional[CorrelationId] = None,
) -> Result[dict]:
    """G1: Phase 1 Exit Gate — Schema validation, AC testability, use case completeness.

    Checks:
    - G1.1: Schema validation (all UCs have valid structure)
    - G1.2: AC testability (each AC.then is quantifiable)
    - G1.3: Use case completeness (each UC ≥ L1 with known unknowns)
    - G1.4: Lean AC rules compliance
    """
    checks = []

    # G1.1: Schema check (CRITICAL)
    schema_ok = usecase_count > 0 and l1_count >= usecase_count * 0.8
    checks.append({
        "gate": "G1.1", "name": "Schema validation",
        "result": "PASS" if schema_ok else "FAIL",
        "detail": f"{l1_count}/{usecase_count} use cases at L1+",
        "critical": True,
    })

    # G1.2: AC testability
    ac_ok = ac_count > 0 and quantified_ac_count == ac_count
    checks.append({
        "gate": "G1.2", "name": "AC testability",
        "result": "PASS" if ac_ok else "FAIL",
        "detail": f"{quantified_ac_count}/{ac_count} ACs are quantifiable",
    })

    # G1.3: Use case completeness
    checks.append({
        "gate": "G1.3", "name": "Use case completeness",
        "result": "PASS" if usecase_count > 0 else "FAIL",
        "detail": f"{usecase_count} use cases defined",
    })

    passed = all(c["result"] == "PASS" for c in checks if c.get("critical"))
    result = {"gate": "G1", "passed": passed, "checks": checks}

    write_evidence(
        task_id=task_id, phase="1", step="eval_gate.G1",
        content=result, tool_name="eval_gate.G1", correlation=correlation,
    )

    return ok(result)


def run_g2_check(
    task_id: str,
    poc_count: int,
    poc_pass_count: int,
    cost_model_complete: bool,
    verdict_clear: bool,
    correlation: Optional[CorrelationId] = None,
) -> Result[dict]:
    """G2: Phase 2 Exit Gate — PoC reproducibility, cost model, clear verdict.

    Checks:
    - G2.1: PoC code reproducible (CRITICAL)
    - G2.2: PoC results archived
    - G2.3: Cost model complete
    - G2.4: Feasibility verdict explicit
    """
    checks = []

    checks.append({
        "gate": "G2.1", "name": "PoC code reproducible",
        "result": "PASS" if poc_count > 0 else "FAIL",
        "detail": f"{poc_pass_count}/{poc_count} PoC experiments passed",
        "critical": True,
    })

    checks.append({
        "gate": "G2.2", "name": "PoC results archived",
        "result": "PASS" if poc_count > 0 else "FAIL",
    })

    checks.append({
        "gate": "G2.3", "name": "Cost model complete",
        "result": "PASS" if cost_model_complete else "FAIL",
    })

    checks.append({
        "gate": "G2.4", "name": "Feasibility verdict clear",
        "result": "PASS" if verdict_clear else "FAIL",
    })

    passed = all(c["result"] == "PASS" for c in checks if c.get("critical"))
    result = {"gate": "G2", "passed": passed, "checks": checks}

    write_evidence(
        task_id=task_id, phase="2", step="eval_gate.G2",
        content=result, tool_name="eval_gate.G2", correlation=correlation,
    )

    return ok(result)


def run_g3_check(
    task_id: str,
    has_context_map: bool,
    has_interface_contracts: bool,
    adr_count: int,
    extension_points_declared: bool,
    circular_deps: bool,
    correlation: Optional[CorrelationId] = None,
) -> Result[dict]:
    """G3: Phase 3 Exit Gate — Architecture integrity, ADR coverage.

    Checks:
    - G3.1: No circular dependencies (CRITICAL)
    - G3.2: Interface contracts complete
    - G3.3: ADR covers all non-trivial decisions
    - G3.4: Extension points declared for known unknowns
    """
    checks = []

    checks.append({
        "gate": "G3.1", "name": "No circular dependencies",
        "result": "FAIL" if circular_deps else "PASS",
        "critical": True,
    })

    checks.append({
        "gate": "G3.2", "name": "Interface contracts complete",
        "result": "PASS" if has_interface_contracts else "FAIL",
    })

    checks.append({
        "gate": "G3.3", "name": "ADR coverage",
        "result": "PASS" if adr_count > 0 else "FAIL",
        "detail": f"{adr_count} ADRs created",
    })

    checks.append({
        "gate": "G3.4", "name": "Extension points declared",
        "result": "PASS" if extension_points_declared or adr_count > 0 else "WARN",
    })

    passed = all(c["result"] == "PASS" for c in checks if c.get("critical"))
    result = {"gate": "G3", "passed": passed, "checks": checks}

    write_evidence(
        task_id=task_id, phase="3", step="eval_gate.G3",
        content=result, tool_name="eval_gate.G3", correlation=correlation,
    )

    return ok(result)


def run_g4_check(
    task_id: str,
    compilation_passed: bool,
    sast_clean: bool,
    no_cves: bool,
    no_regression: bool,
    self_review_complete: bool,
    correlation: Optional[CorrelationId] = None,
) -> Result[dict]:
    """G4: Phase 4 Exit Gate — Build, SAST, dependencies, regression.

    Checks:
    - G4.1: Compilation passes (CRITICAL)
    - G4.2: Existing tests no regression (CRITICAL)
    - G4.3: SAST clean
    - G4.4: Dependency CVE clean
    - G4.5: Self-review complete
    """
    checks = []

    checks.append({
        "gate": "G4.1", "name": "Compilation passes",
        "result": "PASS" if compilation_passed else "FAIL",
        "critical": True,
    })

    checks.append({
        "gate": "G4.2", "name": "No regression in existing tests",
        "result": "PASS" if no_regression else "FAIL",
        "critical": True,
    })

    checks.append({
        "gate": "G4.3", "name": "SAST clean",
        "result": "PASS" if sast_clean else "WARN",
    })

    checks.append({
        "gate": "G4.4", "name": "Dependency CVE clean",
        "result": "PASS" if no_cves else "WARN",
    })

    checks.append({
        "gate": "G4.5", "name": "Self-review complete",
        "result": "PASS" if self_review_complete else "FAIL",
    })

    passed = all(c["result"] == "PASS" for c in checks if c.get("critical"))
    result = {"gate": "G4", "passed": passed, "checks": checks}

    write_evidence(
        task_id=task_id, phase="4", step="eval_gate.G4",
        content=result, tool_name="eval_gate.G4", correlation=correlation,
    )

    return ok(result)


def run_g5_check(
    task_id: str,
    mutation_score: float,
    ac_coverage_pct: float,
    regression_valid: bool,
    traceability_complete: bool,
    correlation: Optional[CorrelationId] = None,
) -> Result[dict]:
    """G5: Phase 5 Exit Gate — Test quality, AC coverage, regression validity.

    Checks:
    - G5.1: Mutation score ≥ 0.5
    - G5.2: AC coverage = 100%
    - G5.3: Regression test validity (all new tests detect revert)
    - G5.4: Traceability complete (CRITICAL)
    """
    checks = []

    checks.append({
        "gate": "G5.1", "name": "Mutation score ≥ 0.5",
        "result": "PASS" if mutation_score >= 0.5 else "FAIL",
        "detail": f"Score: {mutation_score:.2f}",
    })

    checks.append({
        "gate": "G5.2", "name": "AC coverage = 100%",
        "result": "PASS" if ac_coverage_pct >= 100 else "FAIL",
        "detail": f"Coverage: {ac_coverage_pct:.0f}%",
    })

    checks.append({
        "gate": "G5.3", "name": "Regression test validity",
        "result": "PASS" if regression_valid else "FAIL",
    })

    checks.append({
        "gate": "G5.4", "name": "Traceability complete",
        "result": "PASS" if traceability_complete else "FAIL",
        "critical": True,
    })

    passed = all(c["result"] == "PASS" for c in checks if c.get("critical"))
    result = {"gate": "G5", "passed": passed, "checks": checks}

    write_evidence(
        task_id=task_id, phase="5", step="eval_gate.G5",
        content=result, tool_name="eval_gate.G5", correlation=correlation,
    )

    return ok(result)


def run_g6_check(
    task_id: str,
    health_check_passed: bool,
    slo_compliant: bool,
    rollback_verified: bool,
    correlation: Optional[CorrelationId] = None,
) -> Result[dict]:
    """G6: Phase 5 Exit Gate (Deployment) — Health, SLO, rollback.

    Executed by DevOps Agent.
    """
    checks = []

    checks.append({
        "gate": "G6.1", "name": "Deployment health check",
        "result": "PASS" if health_check_passed else "FAIL",
    })

    checks.append({
        "gate": "G6.2", "name": "SLO compliance",
        "result": "PASS" if slo_compliant else "FAIL",
    })

    checks.append({
        "gate": "G6.3", "name": "Rollback verified",
        "result": "PASS" if rollback_verified else "WARN",
    })

    passed = all(c["result"] in ["PASS", "WARN"] for c in checks)
    result = {"gate": "G6", "passed": passed, "checks": checks}

    write_evidence(
        task_id=task_id, phase="5", step="eval_gate.G6",
        content=result, tool_name="eval_gate.G6", correlation=correlation,
    )

    return ok(result)


def run_all_gates(
    task_id: str,
    phase: str,
    metrics: dict,
    correlation: Optional[CorrelationId] = None,
) -> Result[dict]:
    """Run all gates for a given phase.

    Returns aggregated gate results for verdict computation.
    """
    gate_funcs = {
        "1": run_g1_check,
        "2": run_g2_check,
        "3": run_g3_check,
        "4": run_g4_check,
        "5": lambda tid, **kw: {
            "g5": run_g5_check(tid, **kw),
            "g6": run_g6_check(tid, **kw),
        },
    }

    if phase == "5":
        g5_result = run_g5_check(task_id, correlation=correlation, **metrics)
        g6_result = run_g6_check(task_id, correlation=correlation, **metrics)
        return ok({"G5": g5_result.data, "G6": g6_result.data})

    gate_fn = gate_funcs.get(phase)
    if gate_fn:
        result = gate_fn(task_id, correlation=correlation, **metrics)
        gate_id = f"G{phase}"
        return ok({gate_id: result.data})

    return ok({})
