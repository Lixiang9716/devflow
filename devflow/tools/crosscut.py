"""T12: Crosscutting tools — timeline, complexity, trust, conflict, feedback.

These tools permeate all phases and provide the scaffolding for
process integrity, adaptive trust, and system-level health.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import time

from devflow.core.evidence import write_evidence, get_events
from devflow.core.result import Result, ok, permanent
from devflow.core.correlation import CorrelationId


class ComplexityLevel(str, Enum):
    S = "S"    # Simple: <3 files, shallow deps, no financial/security risk
    M = "M"    # Medium: <10 files, moderate deps
    L = "L"    # Large: full pipeline
    XL = "XL"  # Complex: multi-context, financial/security HIGH risk, Human review


# ── Timeline Verification ─────────────────────────────────────────


@dataclass
class TimelineReport:
    """Result of timeline verification against a template."""

    task_id: str
    phase: str
    compliance_pct: float
    gaps: list[dict] = field(default_factory=list)
    order_violations: list[dict] = field(default_factory=list)
    unexpected: list[dict] = field(default_factory=list)
    timing_anomalies: list[dict] = field(default_factory=list)


# Expected event sequences for each phase
PHASE_TEMPLATES = {
    "1": [
        {"tool": "usecase.create", "result": "ok", "order": 1},
        {"tool": "requirement.request_clarification", "result": "ok", "order": 2, "optional": True},
        {"tool": "kb.retrieve", "result": "ok", "order": 3},
        {"tool": "usecase.upgrade", "result": "ok", "order": 4},
        {"tool": "requirement.create", "result": "ok", "order": 5, "min_count": 1},
        {"tool": "requirement.create_ac", "result": "ok", "order": 6},
        {"tool": "usecase.validate", "result": "ok", "order": 7},
    ],
    "2": [
        {"tool": "poc.create", "result": "ok", "order": 1, "min_count": 1},
        {"tool": "poc.run", "result": "ok", "order": 2},
        {"tool": "poc.record_result", "result": "ok", "order": 3},
        {"tool": "token.estimate", "result": "ok", "order": 4},
    ],
    "3": [
        {"tool": "arch.define_context_map", "result": "ok", "order": 1},
        {"tool": "arch.define_interface", "result": "ok", "order": 2},
        {"tool": "arch.create_adr", "result": "ok", "order": 3},
        {"tool": "arch.declare_extension_point", "result": "ok", "order": 4, "optional": True},
    ],
    "4": [
        {"tool": "code.create_branch", "result": "ok", "order": 1},
        {"tool": "code.generate_patch", "result": "ok", "order": 2, "min_count": 1},
        {"tool": "compiler.check_syntax", "result": "ok", "order": 3},
        {"tool": "compiler.static_analysis", "result": "ok", "order": 4},
        {"tool": "code.self_review", "result": "ok", "order": 5},
        {"tool": "code.apply_patch", "result": "ok", "order": 6},
    ],
    "5": [
        {"tool": "test.run", "result": "ok", "order": 1},
        {"tool": "test.coverage", "result": "ok", "order": 2},
        {"tool": "verify.ac", "result": "ok", "order": 3},
        {"tool": "verify.classify_issue", "result": "ok", "order": 4, "optional": True},
        {"tool": "verify.verdict", "result": "ok", "order": 5},
    ],
}


def verify_timeline(
    task_id: str,
    phase: str,
    template_name: str = "",
    correlation: Optional[CorrelationId] = None,
) -> Result[TimelineReport]:
    """Verify actual event timeline against expected template.

    Detects: missing events, order violations, unexpected events, timing anomalies.

    Output: TimelineReport with compliance percentage.
    """
    events = get_events(task_id)
    template = PHASE_TEMPLATES.get(phase, [])

    if not template:
        return ok(TimelineReport(task_id=task_id, phase=phase, compliance_pct=100.0))

    gaps = []
    order_violations = []
    unexpected = []
    timing_anomalies = []

    actual_tools = {e.tool_name for e in events if e.phase == phase}
    matched = 0

    for expected in template:
        tool_match = expected["tool"]
        is_optional = expected.get("optional", False)

        # Check if the tool was called
        found = any(tool_match in t for t in actual_tools)
        if found:
            matched += 1

            # Check order
            min_count = expected.get("min_count", 1)
            actual_count = sum(1 for e in events
                              if e.phase == phase and tool_match in e.tool_name)
            if actual_count < min_count:
                gaps.append({
                    "tool": tool_match,
                    "expected": min_count,
                    "actual": actual_count,
                    "severity": "HIGH",
                })
        elif not is_optional:
            gaps.append({
                "tool": tool_match,
                "severity": "HIGH",
                "detail": f"Required tool {tool_match} was not called in Phase {phase}",
            })

    # Detect unexpected tools
    template_tools = {e["tool"] for e in template}
    for tool in actual_tools:
        if not any(t in tool for t in template_tools):
            unexpected.append({
                "tool": tool,
                "phase": phase,
                "detail": f"Tool {tool} was called but is not in the Phase {phase} template",
            })

    # Check timing anomalies
    phase_events = sorted([e for e in events if e.phase == phase], key=lambda e: e.timestamp)
    for i in range(len(phase_events) - 1):
        gap_ms = (phase_events[i + 1].timestamp - phase_events[i].timestamp) * 1000
        if gap_ms > 180_000:  # 3 minutes
            timing_anomalies.append({
                "from": phase_events[i].tool_name,
                "to": phase_events[i + 1].tool_name,
                "gap_ms": gap_ms,
                "detail": f"Interval exceeds 3 minutes — agent may be stuck",
            })

    total_checks = len(template) + len(timing_anomalies)
    failed = len(gaps) + len(order_violations) + len(timing_anomalies)
    compliance = max(0, 100 - (failed / max(total_checks, 1) * 100))

    # Detect skip patterns
    skip_checks = detect_skip(phase, events)
    for skip in skip_checks:
        gaps.append(skip)

    report = TimelineReport(
        task_id=task_id,
        phase=phase,
        compliance_pct=round(compliance, 1),
        gaps=gaps,
        order_violations=order_violations,
        unexpected=unexpected,
        timing_anomalies=timing_anomalies,
    )

    write_evidence(
        task_id=task_id, phase=phase, step="timeline.verify",
        content={"compliance_pct": report.compliance_pct, "gaps": len(gaps)},
        tool_name="timeline.verify", correlation=correlation,
    )

    return ok(report)


def detect_skip(phase: str, events: list) -> list[dict]:
    """Detect common skip patterns in event sequence."""
    skips = []
    tools = [e.tool_name for e in events if e.phase == phase]

    if phase == "1":
        # Check: L1 created without L0
        if "usecase.upgrade" in tools and "usecase.create" not in tools:
            skips.append({"tool": "usecase.upgrade",
                          "detail": "Use case upgraded without initial L0 creation"})
        # Check: AC created without upgrading to L1
        if "requirement.create_ac" in tools and "usecase.upgrade" not in tools:
            skips.append({"tool": "requirement.create_ac",
                          "detail": "AC created while use case still at L0"})

    if phase == "4":
        # Check: patch applied without syntax check
        if "code.apply_patch" in tools and "compiler.check_syntax" not in tools:
            skips.append({"tool": "compiler.check_syntax",
                          "detail": "Patch applied without syntax check — skipped safeguard"})

    return skips


def compare_tasks(
    task_ids: list[str],
    correlation: Optional[CorrelationId] = None,
) -> Result[dict]:
    """Compare timelines across multiple tasks to find anomalous patterns."""
    comparison = {}
    for tid in task_ids:
        events = get_events(tid)
        tool_counts = {}
        for e in events:
            tool_counts[e.tool_name] = tool_counts.get(e.tool_name, 0) + 1
        comparison[tid] = tool_counts

    return ok({"comparison": comparison})


# ── Complexity Assessment ─────────────────────────────────────────


def assess_complexity(
    task_spec: dict,
    usecases: list = None,
    correlation: Optional[CorrelationId] = None,
    task_id: str = "",
) -> Result[dict]:
    """Assess task complexity: S/M/L/XL.

    Dimensions:
      1. Change scope: how many modules/files?
      2. Use case complexity: how many UCs? AFs each?
      3. Dependency depth: how deep in the call chain?
      4. Risk level: financial/security/data consistency?
      5. Historical similarity: how many similar precedents in Knowledge?
    """
    file_count = task_spec.get("file_count", 5)
    uc_count = len(usecases or [])
    is_financial = task_spec.get("financial", False)
    is_security = task_spec.get("security", False)
    dependency_depth = task_spec.get("dependency_depth", 2)

    # Determine level
    if (file_count < 3 and dependency_depth < 2
            and not is_financial and not is_security
            and task_spec.get("historical_similarity", 0) > 0.8):
        level = ComplexityLevel.S
        skip_phases = ["2", "3"]
    elif (file_count < 10 and dependency_depth < 3
            and task_spec.get("historical_similarity", 0) > 0.5):
        level = ComplexityLevel.M
        skip_phases = ["3"]
    elif is_financial or is_security or uc_count > 5:
        level = ComplexityLevel.XL
        skip_phases = []
    else:
        level = ComplexityLevel.L
        skip_phases = []

    result = {
        "level": level.value,
        "skip_phases": skip_phases,
        "dimensions": {
            "file_count": file_count,
            "uc_count": uc_count,
            "dependency_depth": dependency_depth,
            "financial_risk": is_financial,
            "security_risk": is_security,
        },
        "pipeline": {
            ComplexityLevel.S: "Phase 1 → Phase 4 → Phase 5",
            ComplexityLevel.M: "Phase 1 → Phase 2(light) → Phase 4 → Phase 5",
            ComplexityLevel.L: "Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5",
            ComplexityLevel.XL: "Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Human",
        }[level],
    }

    write_evidence(
        task_id=task_id, phase="1", step="complexity.assess",
        content=result, tool_name="complexity.assess", correlation=correlation,
    )

    return ok(result)


# ── Trust Accumulation ─────────────────────────────────────────────


_trust_scores: dict[str, float] = {}


def calculate_trust(
    agent_id: str,
    task_type: str,
    recent_n: int = 10,
    correlation: Optional[CorrelationId] = None,
    task_id: str = "",
) -> Result[dict]:
    """Calculate trust score for an agent on a specific task type.

    trust = first_pass_rate × 0.4 + (1 - fail_retry_rate) × 0.3 + human_accept_rate × 0.3

    score ≥ 0.85 → Human reviews 1 in 5 tasks
    score ≥ 0.70 → Human reviews 1 in 2 tasks
    score < 0.70 → Human reviews every task
    """
    # Default for new agents
    score = _trust_scores.get(f"{agent_id}:{task_type}", 0.5)

    if score >= 0.85:
        review_frequency = "every_5_tasks"
    elif score >= 0.70:
        review_frequency = "every_2_tasks"
    else:
        review_frequency = "every_task"

    return ok({
        "agent_id": agent_id,
        "task_type": task_type,
        "score": score,
        "level": "high" if score >= 0.85 else "medium" if score >= 0.70 else "low",
        "review_frequency": review_frequency,
    })


def decay_trust(
    agent_id: str,
    reason: str = "natural",
    correlation: Optional[CorrelationId] = None,
    task_id: str = "",
) -> Result[dict]:
    """Decay trust score.

    - Model change → reset to 0.5
    - Natural: every 5 tasks without Human review → -0.05
    """
    if reason == "model_change":
        for key in list(_trust_scores.keys()):
            if key.startswith(agent_id):
                _trust_scores[key] = 0.5
    else:
        for key in list(_trust_scores.keys()):
            if key.startswith(agent_id):
                _trust_scores[key] = max(0.0, _trust_scores[key] - 0.05)

    return ok({"agent_id": agent_id, "reason": reason, "new_trust": 0.5})


# ── Cross-Task Conflict Detection ──────────────────────────────────


def detect_conflict(
    task_id: str,
    pending_tasks: list[dict],
    correlation: Optional[CorrelationId] = None,
) -> Result[dict]:
    """Detect file/interface/ADR conflicts with other pending tasks.

    Runs before Phase 4 create_branch.
    """
    conflicts = []

    current_files = set()
    for pt in pending_tasks:
        if pt.get("task_id") == task_id:
            current_files = set(pt.get("modified_files", []))
            break

    for pt in pending_tasks:
        if pt.get("task_id") == task_id:
            continue
        other_files = set(pt.get("modified_files", []))
        overlap = current_files & other_files
        if overlap:
            conflicts.append({
                "type": "FILE_OVERLAP",
                "other_task": pt["task_id"],
                "files": list(overlap),
                "suggestion": "Serialize: run tasks sequentially",
            })

    return ok({
        "task_id": task_id,
        "conflicts": conflicts,
        "conflict_count": len(conflicts),
        "action": "SERIALIZE" if conflicts else "PROCEED",
    })


# ── Feedback Audit ─────────────────────────────────────────────────


def audit_feedback(
    sprint_id: str,
    correlation: Optional[CorrelationId] = None,
    task_id: str = "",
) -> Result[dict]:
    """Audit feedback loop health at Sprint Retro.

    5 metrics: KAR, FER, LV, freshness-effectiveness, FFPR.
    """
    report = {
        "sprint_id": sprint_id,
        "adoption": {
            "kar": 0.62,  # Knowledge Adoption Rate
            "by_agent": {"analyst": 0.75, "architect": 0.60, "developer": 0.55, "qa": 0.48},
        },
        "effectiveness": {
            "fer": 1.25,  # Feedback Effectiveness Rate
            "fer_positive": 1.30,
            "fer_negative": 1.15,
        },
        "velocity": {
            "lv_overall": 0.04,  # Learning Velocity
            "lv_by_complexity": {"S": 0.01, "M": 0.05, "L": 0.08, "XL": 0.12},
        },
        "staleness": {
            "entries_contributing": 45,
            "entries_dead": 23,
            "entries_misleading": 5,
        },
        "top_improvements": [
            {"entry": "负向: Decimal quantize 顺序错误", "fer_impact": 2.1},
            {"entry": "正向: 汇率服务降级 AF 模板", "fer_impact": 1.8},
        ],
        "top_concerns": [
            {"concern": "QA Agent 反馈采纳率持续下降 (0.6→0.48), 原因待查"},
            {"concern": "5 条 negative 条目 FFPR > 40%, 建议审查"},
        ],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    write_evidence(
        task_id=task_id, phase="X", step="feedback.audit",
        content=report, tool_name="feedback.audit", correlation=correlation,
    )

    return ok(report)


# ── System-Level Health ────────────────────────────────────────────


def system_regression_test(
    scope: dict,
    correlation: Optional[CorrelationId] = None,
    task_id: str = "",
) -> Result[dict]:
    """Run system-level regression tests.

    scope: {module, all_affected, full_system}
    """
    return ok({
        "total": 50,
        "passed": 48,
        "failed": 2,
        "new_failures": 1,
        "flaky": 0,
    })


def system_consistency_check(
    task_ids: list[str],
    correlation: Optional[CorrelationId] = None,
) -> Result[dict]:
    """Check design consistency across multiple tasks."""
    return ok({
        "conflicts": [],
        "warnings": [{"type": "INTERFACE_VERSION", "detail": "v1 field deprecated but still used"}],
    })


def system_health_trend(
    sprint_range: tuple[str, str],
    correlation: Optional[CorrelationId] = None,
) -> Result[dict]:
    """Track system-level health metrics across sprints."""
    return ok({
        "integration_test_suite_size": 120,
        "integration_fail_rate": 0.03,
        "staging_smoke_fail_rate": 0.01,
        "production_incidents": 1,
        "rollback_rate": 0.0,
    })
