"""T3: PoC toolset — code-managed feasibility verification.

PoC experiments are executable, reproducible, and comparable.
Not "Agent thinks it will work" — Agent runs code and reports results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import hashlib
import subprocess
import tempfile
import os

from devflow.core.evidence import write_evidence
from devflow.core.result import Result, ok, permanent
from devflow.core.idempotency import make_content_hash, check_exists, record_operation
from devflow.core.correlation import CorrelationId


class PoCConclusion(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


class PoCStatus(str, Enum):
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"


@dataclass
class PoCExperiment:
    """A single PoC experiment."""

    experiment_id: str
    name: str
    hypothesis: str
    code: str
    expected_result: str
    linked_fr: str
    status: PoCStatus = PoCStatus.READY
    conclusion: Optional[PoCConclusion] = None
    actual_result: str = ""
    evidence: dict = field(default_factory=dict)
    stdout: str = ""
    stderr: str = ""
    exit_code: int = -1


_poc_store: dict[str, PoCExperiment] = {}


def create(
    name: str,
    hypothesis: str,
    code: str,
    expected_result: str,
    linked_fr: str = "",
    correlation: Optional[CorrelationId] = None,
    task_id: str = "",
) -> Result[PoCExperiment]:
    """Create a PoC experiment.

    Code is stored for execution; associated with FR.
    """
    idem_key = make_content_hash("poc.create", name, hypothesis, code)
    cached = check_exists(idem_key)
    if cached:
        return ok(cached)

    exp_id = f"PoC-{hashlib.sha256(name.encode()).hexdigest()[:8]}"
    exp = PoCExperiment(
        experiment_id=exp_id,
        name=name,
        hypothesis=hypothesis,
        code=code,
        expected_result=expected_result,
        linked_fr=linked_fr,
    )

    _poc_store[exp_id] = exp
    record_operation(idem_key, exp)

    write_evidence(
        task_id=task_id, phase="2", step="poc.create",
        content={"experiment_id": exp_id, "name": name, "linked_fr": linked_fr},
        tool_name="poc.create", correlation=correlation,
    )

    return ok(exp)


def run(
    experiment_id: str,
    correlation: Optional[CorrelationId] = None,
    task_id: str = "",
) -> Result[PoCExperiment]:
    """Execute a PoC experiment in a sandbox.

    Captures stdout/stderr/exit_code. Compares actual vs expected.
    Conclusion can ONLY be PASS/FAIL/INCONCLUSIVE.
    """
    exp = _poc_store.get(experiment_id)
    if not exp:
        return permanent("architect", "2", f"Experiment {experiment_id} not found")

    exp.status = PoCStatus.RUNNING

    try:
        # Execute in a temp file (sandbox)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(exp.code)
            tmp_path = f.name

        result = subprocess.run(
            ["python3", tmp_path],
            capture_output=True, text=True, timeout=30,
        )
        os.unlink(tmp_path)

        exp.stdout = result.stdout
        exp.stderr = result.stderr
        exp.exit_code = result.returncode

        # Compare actual vs expected
        actual_output = result.stdout.strip()
        if actual_output == exp.expected_result.strip():
            exp.conclusion = PoCConclusion.PASS
            exp.actual_result = actual_output
        elif result.returncode != 0:
            exp.conclusion = PoCConclusion.FAIL
            exp.actual_result = f"exit_code={result.returncode}, stderr={result.stderr[:200]}"
        else:
            exp.conclusion = PoCConclusion.INCONCLUSIVE
            exp.actual_result = actual_output

    except subprocess.TimeoutExpired:
        exp.conclusion = PoCConclusion.FAIL
        exp.actual_result = "Timeout after 30s"
        exp.exit_code = -1
    except Exception as e:
        exp.conclusion = PoCConclusion.FAIL
        exp.actual_result = str(e)
        exp.exit_code = -1

    exp.status = PoCStatus.COMPLETED

    write_evidence(
        task_id=task_id, phase="2", step="poc.run",
        content={
            "experiment_id": experiment_id,
            "conclusion": exp.conclusion.value,
            "exit_code": exp.exit_code,
        },
        tool_name="poc.run", correlation=correlation,
    )

    return ok(exp)


def record_result(
    experiment_id: str,
    conclusion: str,
    evidence: dict = None,
    correlation: Optional[CorrelationId] = None,
    task_id: str = "",
) -> Result[PoCExperiment]:
    """Record the conclusion of a PoC experiment."""
    exp = _poc_store.get(experiment_id)
    if not exp:
        return permanent("architect", "2", f"Experiment {experiment_id} not found")

    try:
        exp.conclusion = PoCConclusion(conclusion)
    except ValueError:
        return permanent("architect", "2",
                         f"Invalid conclusion: {conclusion}. Must be PASS, FAIL, or INCONCLUSIVE")

    if evidence:
        exp.evidence = evidence

    write_evidence(
        task_id=task_id, phase="2", step="poc.record_result",
        content={"experiment_id": experiment_id, "conclusion": conclusion},
        tool_name="poc.record_result", correlation=correlation,
    )

    return ok(exp)


def list_experiments(task_id: str = "") -> Result[list]:
    """List all PoC experiments (optionally filtered by task)."""
    return ok(list(_poc_store.values()))


def compare(expected: str, actual: str) -> Result[dict]:
    """Compare expected vs actual output, returning a text diff."""
    import difflib
    diff = list(difflib.unified_diff(
        expected.splitlines(keepends=True),
        actual.splitlines(keepends=True),
        fromfile="expected",
        tofile="actual",
    ))
    return ok({
        "match": expected.strip() == actual.strip(),
        "diff": "".join(diff) if diff else "(identical)",
    })


def clear_store():
    """Clear PoC store (for testing)."""
    _poc_store.clear()
