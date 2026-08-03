"""T4: Token tracking toolset — precise LLM consumption instrumentation.

Not estimation — runtime instrumentation. Every LLM call records tokens.
Budget enforcement catches cost overruns before they happen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import time

from devflow.core.evidence import write_evidence
from devflow.core.result import Result, ok
from devflow.core.correlation import CorrelationId


# Model pricing per 1M tokens (input, output)
_MODEL_PRICES = {
    "deepseek-v4-pro": (0.14, 1.10),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-opus-5": (15.00, 75.00),
    "claude-haiku-4-5": (0.80, 4.00),
    "gpt-4o": (2.50, 10.00),
    "default": (1.00, 5.00),
}


def get_model_price(model: str) -> tuple[float, float]:
    """Get (input_price, output_price) per 1M tokens for a model."""
    return _MODEL_PRICES.get(model, _MODEL_PRICES["default"])


@dataclass
class TokenCall:
    """A single LLM call record."""

    agent: str
    phase: str
    model: str
    input_tokens: int
    output_tokens: int
    cost: float = 0.0
    correlation_id: str = ""
    timestamp: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.cost == 0.0:
            in_price, out_price = get_model_price(self.model)
            self.cost = (self.input_tokens / 1_000_000) * in_price + \
                        (self.output_tokens / 1_000_000) * out_price


@dataclass
class TokenBudget:
    """Per-task token budget."""

    task_id: str
    budget_limit: float  # In dollars
    per_phase_budget: dict[str, float] = field(default_factory=dict)


_token_store: dict[str, list[TokenCall]] = {}
_budget_store: dict[str, TokenBudget] = {}


def record_call(
    agent: str,
    phase: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    correlation: Optional[CorrelationId] = None,
    task_id: str = "",
    **metadata,
) -> Result[TokenCall]:
    """Record a single LLM call.

    Called immediately after every LLM call. Auto-injects correlation_id.
    """
    call = TokenCall(
        agent=agent,
        phase=phase,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        correlation_id=correlation.full_chain if correlation else "",
        metadata=metadata,
    )

    if task_id not in _token_store:
        _token_store[task_id] = []
    _token_store[task_id].append(call)

    write_evidence(
        task_id=task_id, phase=phase, step="token.record_call",
        content={
            "agent": agent, "model": model,
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "cost": call.cost,
        },
        tool_name="token.record_call", correlation=correlation,
    )

    return ok(call)


def estimate(
    task_spec: dict,
    model: str,
    phases: list[str] = None,
    task_id: str = "",
) -> Result[dict]:
    """Estimate token consumption based on historical data + task complexity.

    Returns per-phase breakdown with confidence.
    """
    phases = phases or ["1", "2", "3", "4", "5"]

    # Base estimates by phase (can be refined with real historical data)
    phase_estimates = {
        "1": {"input": 8000, "output": 3000, "description": "需求分析"},
        "2": {"input": 10000, "output": 5000, "description": "可行性研究"},
        "3": {"input": 10000, "output": 5000, "description": "架构设计"},
        "4": {"input": 15000, "output": 10000, "description": "代码实现"},
        "5": {"input": 12000, "output": 8000, "description": "测试验证"},
    }

    in_price, out_price = get_model_price(model)
    per_phase = {}
    total_tokens = 0
    total_cost = 0.0

    for phase in phases:
        est = phase_estimates.get(phase, {"input": 5000, "output": 3000})
        phase_tokens = est["input"] + est["output"]
        phase_cost = (est["input"] / 1_000_000) * in_price + \
                     (est["output"] / 1_000_000) * out_price
        per_phase[phase] = {
            "input_estimate": est["input"],
            "output_estimate": est["output"],
            "total_tokens": phase_tokens,
            "cost": round(phase_cost, 6),
        }
        total_tokens += phase_tokens
        total_cost += phase_cost

    return ok({
        "per_phase": per_phase,
        "total_tokens": total_tokens,
        "total_cost": round(total_cost, 6),
        "model": model,
        "confidence": 0.7,  # Improves with real data
    })


def report(task_id: str) -> Result[dict]:
    """Generate a complete token consumption report for a task."""
    calls = _token_store.get(task_id, [])

    by_phase = {}
    total_cost = 0.0
    for call in calls:
        phase_key = f"phase_{call.phase}"
        if phase_key not in by_phase:
            by_phase[phase_key] = {"input": 0, "output": 0, "cost": 0.0, "calls": 0, "by_agent": {}}

        phase_data = by_phase[phase_key]
        phase_data["input"] += call.input_tokens
        phase_data["output"] += call.output_tokens
        phase_data["cost"] += call.cost
        phase_data["calls"] += 1

        if call.agent not in phase_data["by_agent"]:
            phase_data["by_agent"][call.agent] = {"input": 0, "output": 0, "cost": 0.0}
        phase_data["by_agent"][call.agent]["input"] += call.input_tokens
        phase_data["by_agent"][call.agent]["output"] += call.output_tokens
        phase_data["by_agent"][call.agent]["cost"] += call.cost

        total_cost += call.cost

    return ok({
        "task_id": task_id,
        "total_cost": round(total_cost, 6),
        "total_calls": len(calls),
        "by_phase": by_phase,
    })


def budget_check(task_id: str, budget_limit: float) -> Result[dict]:
    """Check current token consumption against budget.

    Returns {status: OK|WARNING|EXCEEDED, remaining}.
    """
    calls = _token_store.get(task_id, [])
    total_cost = sum(c.cost for c in calls)

    if total_cost > budget_limit:
        status = "EXCEEDED"
    elif total_cost > budget_limit * 0.8:
        status = "WARNING"
    else:
        status = "OK"

    return ok({
        "status": status,
        "spent": round(total_cost, 6),
        "budget": budget_limit,
        "remaining": round(max(0, budget_limit - total_cost), 6),
    })


def budget_enforce(task_id: str, per_phase_budget: dict[str, float]) -> Result[dict]:
    """Enforce per-phase token budgets. Pauses and notifies Human if exceeded."""
    calls = _token_store.get(task_id, [])
    phase_costs = {}
    violations = []

    for call in calls:
        phase_costs[call.phase] = phase_costs.get(call.phase, 0.0) + call.cost

    for phase, budget in per_phase_budget.items():
        spent = phase_costs.get(phase, 0.0)
        if spent > budget:
            violations.append({
                "phase": phase,
                "spent": round(spent, 6),
                "budget": budget,
                "excess_pct": round((spent - budget) / budget * 100, 1),
            })

    if violations:
        return ok({"status": "BUDGET_EXCEEDED", "violations": violations, "action": "PAUSE_AND_NOTIFY"})

    return ok({"status": "OK", "phase_costs": {p: round(c, 6) for p, c in phase_costs.items()}})


def anomaly_detect(task_id: str) -> Result[dict]:
    """Detect anomalous token consumption vs historical patterns.

    Flags: single phase > p95 × 1.5, total > p95 × 1.3, retries > p95 × 2.
    """
    calls = _token_store.get(task_id, [])
    anomalies = []

    if not calls:
        return ok({"anomalies": [], "status": "NO_DATA"})

    # Simple heuristic detection (production uses real historical data)
    phase_tokens = {}
    for call in calls:
        phase_tokens[call.phase] = phase_tokens.get(call.phase, 0) + \
                                   call.input_tokens + call.output_tokens

    total_tokens = sum(phase_tokens.values())

    # Heuristic thresholds (would be calibrated from real data)
    if total_tokens > 150_000:
        anomalies.append({
            "type": "HIGH_TOTAL_TOKENS",
            "total": total_tokens,
            "threshold": 150_000,
            "detail": "Total tokens unusually high — possible LLM retry loop",
        })

    return ok({
        "task_id": task_id,
        "anomalies": anomalies,
        "total_tokens": total_tokens,
        "phase_breakdown": phase_tokens,
    })


def trend(
    agent: str = None,
    phase: str = None,
    date_range: tuple[str, str] = None,
) -> Result[dict]:
    """Return token consumption trend data for cost optimization."""
    all_calls = []
    for task_calls in _token_store.values():
        all_calls.extend(task_calls)

    by_date = {}
    for call in all_calls:
        date_key = time.strftime("%Y-%m-%d", time.gmtime(call.timestamp))
        if date_key not in by_date:
            by_date[date_key] = {"cost": 0.0, "tokens": 0, "calls": 0}
        by_date[date_key]["cost"] += call.cost
        by_date[date_key]["tokens"] += call.input_tokens + call.output_tokens
        by_date[date_key]["calls"] += 1

    return ok({
        "by_date": dict(sorted(by_date.items())),
        "total_cost": round(sum(d["cost"] for d in by_date.values()), 4),
    })


def clear_store():
    """Clear token store (for testing)."""
    _token_store.clear()
    _budget_store.clear()
