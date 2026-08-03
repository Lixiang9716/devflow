"""T9: Verify/Issue toolset — verification and issue classification.

Core logic: verify ACs against test results, classify failures using
the decision tree (USECASE_GAP vs BUG_IN_USECASE vs CODE_BUG vs ENV_ISSUE).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from devflow.core.evidence import write_evidence
from devflow.core.result import Result, ok, permanent
from devflow.core.correlation import CorrelationId


class IssueType(str, Enum):
    """Issue classification per the decision tree."""

    USECASE_GAP = "USECASE_GAP"        # Use case doesn't cover this scenario → Phase 1
    BUG_IN_USECASE = "BUG_IN_USECASE"  # Use case describes wrong behavior → Phase 1
    CODE_BUG = "CODE_BUG"              # Code doesn't correctly implement use case → Phase 4
    ENV_ISSUE = "ENV_ISSUE"            # Environment/infrastructure → DevOps
    INTEGRATION_BUG = "INTEGRATION_BUG"  # Task change breaks other module assumptions
    PRE_EXISTING = "PRE_EXISTING"      # Existing issue discovered by new test (good!)


class Verdict(str, Enum):
    """Final task verdict: three values only."""

    PASS = "PASS"
    FAIL_RETRY = "FAIL_RETRY"
    NEED_HUMAN = "NEED_HUMAN"


@dataclass
class ACVerificationResult:
    """Result of verifying a single AC."""

    ac_id: str
    status: str  # PASS | FAIL
    actual: str
    expected: str
    evidence_ref: str = ""


@dataclass
class IssueClassification:
    """Classified issue with target phase for remediation."""

    issue_id: str
    ac_id: str
    type: IssueType
    detail: str
    suggested_target_phase: str  # "1" or "4"
    suggested_action: str = ""


@dataclass
class TaskVerdict:
    """Final task verdict with supporting evidence."""

    task_id: str
    verdict: Verdict
    eval_gate_results: dict = field(default_factory=dict)
    timeline_compliance: float = 0.0
    issues: list[IssueClassification] = field(default_factory=list)


_issue_store: dict[str, list[IssueClassification]] = {}
_verdict_store: dict[str, TaskVerdict] = {}


def verify_ac(
    ac_id: str,
    test_run_result: dict,
    correlation: Optional[CorrelationId] = None,
    task_id: str = "",
) -> Result[ACVerificationResult]:
    """Verify a single AC against test results.

    Compares AC.then assertion with test_run_result.
    """
    actual = test_run_result.get("actual", "")
    expected = test_run_result.get("expected", "")

    status = "PASS" if actual == expected else "FAIL"

    result = ACVerificationResult(
        ac_id=ac_id,
        status=status,
        actual=str(actual),
        expected=str(expected),
        evidence_ref=f"minio://devflow/{task_id}/phase5/ac_verify/{ac_id}.json",
    )

    write_evidence(
        task_id=task_id, phase="5", step="verify.ac",
        content={"ac_id": ac_id, "status": status},
        tool_name="verify.ac", correlation=correlation,
    )

    return ok(result)


def classify_issue(
    ac_id: str,
    failure_detail: dict,
    usecase_trace_result: dict = None,
    correlation: Optional[CorrelationId] = None,
    task_id: str = "",
) -> Result[IssueClassification]:
    """Classify a failure using the decision tree.

    Decision tree:
      Step A: usecase.trace → Is this scenario in the use case?
        No → USECASE_GAP
        Yes → Step B: Does code behavior match use case?
          Yes → BUG_IN_USECASE
          No → CODE_BUG
      Environmental check: ENV_ISSUE?
    """
    scenario_in_uc = failure_detail.get("scenario_in_use_case", None)
    code_matches_uc = failure_detail.get("code_matches_use_case", None)
    is_env = failure_detail.get("is_environmental", False)

    if is_env:
        issue_type = IssueType.ENV_ISSUE
        target_phase = "ops"
    elif scenario_in_uc is False:
        issue_type = IssueType.USECASE_GAP
        target_phase = "1"
    elif code_matches_uc is True:
        issue_type = IssueType.BUG_IN_USECASE
        target_phase = "1"
    elif code_matches_uc is False:
        issue_type = IssueType.CODE_BUG
        target_phase = "4"
    else:
        issue_type = IssueType.CODE_BUG
        target_phase = "4"

    issue_id = f"ISSUE-{task_id}-{len(_issue_store.get(task_id, [])) + 1:02d}"

    classification = IssueClassification(
        issue_id=issue_id,
        ac_id=ac_id,
        type=issue_type,
        detail=failure_detail.get("detail", ""),
        suggested_target_phase=target_phase,
        suggested_action=_suggested_action(issue_type),
    )

    if task_id not in _issue_store:
        _issue_store[task_id] = []
    _issue_store[task_id].append(classification)

    write_evidence(
        task_id=task_id, phase="5", step="verify.classify_issue",
        content={"issue_id": issue_id, "type": issue_type.value, "target_phase": target_phase},
        tool_name="verify.classify_issue", correlation=correlation,
    )

    return ok(classification)


def _suggested_action(issue_type: IssueType) -> str:
    """Suggest remediation action for an issue type."""
    actions = {
        IssueType.USECASE_GAP: "Return to Phase 1: Supplement use case with missing scenario",
        IssueType.BUG_IN_USECASE: "Return to Phase 1: Correct the use case description",
        IssueType.CODE_BUG: "Return to Phase 4: Fix code to match use case specification",
        IssueType.ENV_ISSUE: "DevOps: Investigate and fix environment/infrastructure",
        IssueType.INTEGRATION_BUG: "Create sub-Task: Fix integration conflict (higher priority than original)",
        IssueType.PRE_EXISTING: "Create Bug Issue → Product Backlog (good catch!)",
    }
    return actions.get(issue_type, "Investigate")


def classify_integration(
    task_id: str,
    failing_tests: list[str],
    correlation: Optional[CorrelationId] = None,
) -> Result[list[IssueClassification]]:
    """Classify integration test failures: INTEGRATION_BUG or PRE_EXISTING.

    INTEGRATION_BUG: Task's correct change broke other modules' assumptions.
    PRE_EXISTING: Existing problem discovered by new test (good!).
    """
    issues = []
    for test_name in failing_tests:
        # Simplified: assume new test failures in other modules are INTEGRATION_BUG
        if "test_new" in test_name or "regression" in test_name:
            issue_type = IssueType.PRE_EXISTING
        else:
            issue_type = IssueType.INTEGRATION_BUG

        classification = IssueClassification(
            issue_id=f"ISSUE-{task_id}-INT-{len(issues) + 1:02d}",
            ac_id="",
            type=issue_type,
            detail=f"Integration test failure: {test_name}",
            suggested_target_phase="4",
            suggested_action=_suggested_action(issue_type),
        )
        issues.append(classification)

    return ok(issues)


def verdict(
    task_id: str,
    eval_gate_results: dict = None,
    timeline_compliance: float = 1.0,
    correlation: Optional[CorrelationId] = None,
) -> Result[TaskVerdict]:
    """Aggregate all Eval-Gate + timeline results → PASS|FAIL_RETRY|NEED_HUMAN.

    All CRITICAL gates FAIL → FAIL_RETRY
    All gates PASS → PASS
    Some non-CRITICAL gates FAIL → WARN but still PASS
    Timeline compliance < 80% → NEED_HUMAN (even if gates pass)
    """
    gates = eval_gate_results or {}
    critical_gates_failed = []
    all_passed = True

    critical_gates = {"G1", "G2", "G3", "G4", "G5", "G6"}

    for gate, result in gates.items():
        gid = gate.split(".")[0] if "." in gate else gate
        if result != "PASS":
            all_passed = False
            if gid in critical_gates:
                critical_gates_failed.append(gid)

    if critical_gates_failed:
        final_verdict = Verdict.FAIL_RETRY
    elif timeline_compliance < 0.8:
        final_verdict = Verdict.NEED_HUMAN
    elif all_passed:
        final_verdict = Verdict.PASS
    else:
        final_verdict = Verdict.PASS  # Non-critical failures → WARN but PASS

    task_verdict = TaskVerdict(
        task_id=task_id,
        verdict=final_verdict,
        eval_gate_results=gates,
        timeline_compliance=timeline_compliance,
        issues=_issue_store.get(task_id, []),
    )
    _verdict_store[task_id] = task_verdict

    write_evidence(
        task_id=task_id, phase="5", step="verify.verdict",
        content={"verdict": final_verdict.value, "gates": gates},
        tool_name="verify.verdict", correlation=correlation,
    )

    return ok(task_verdict)


def get_issues(task_id: str) -> list[IssueClassification]:
    """Get all classified issues for a task."""
    return _issue_store.get(task_id, [])


def clear_store():
    """Clear verify stores (for testing)."""
    _issue_store.clear()
    _verdict_store.clear()
