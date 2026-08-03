"""Tests for core infrastructure: Result, Correlation, Evidence, Circuit Breaker."""

import pytest
from devflow.core.result import (
    ok, retryable, permanent, need_human,
    is_ok, is_failure, unwrap, match_result,
    ErrorCode, Success, Failure,
)
from devflow.core.correlation import CorrelationId, new_correlation
from devflow.core.evidence import (
    write_evidence, trace_chain, check_integrity,
    clear_evidence, get_events, EvidenceRecord,
)
from devflow.core.circuit_breaker import CircuitBreaker, CircuitState, CircuitOpenError


class TestResult:
    """Unified Result type tests."""

    def test_ok_creates_success(self):
        result = ok({"name": "test"})
        assert is_ok(result)
        assert not is_failure(result)
        assert result.data == {"name": "test"}

    def test_retryable_creates_failure(self):
        result = retryable("analyst", "1", "LLM timeout")
        assert is_failure(result)
        assert result.code == ErrorCode.RETRYABLE
        assert result.agent == "analyst"

    def test_permanent_creates_failure(self):
        result = permanent("developer", "4", "Schema validation failed")
        assert result.code == ErrorCode.PERMANENT

    def test_need_human_creates_failure(self):
        result = need_human("analyst", "1", "Ambiguous requirement")
        assert result.code == ErrorCode.NEED_HUMAN
        assert "Ambiguous" in result.message

    def test_unwrap_success(self):
        result = ok(42)
        assert unwrap(result) == 42

    def test_unwrap_failure_raises(self):
        result = permanent("agent", "1", "error")
        with pytest.raises(ValueError, match="Cannot unwrap failure"):
            unwrap(result)

    def test_match_result_success(self):
        result = ok(100)
        matched = match_result(result, on_success=lambda d: d * 2)
        assert matched == 200

    def test_match_result_retryable(self):
        result = retryable("a", "1", "msg")
        handled = match_result(result, on_retryable=lambda f: "retry")
        assert handled == "retry"


class TestCorrelation:
    """Correlation ID tests."""

    def test_new_correlation(self):
        corr = new_correlation()
        assert corr.task_id.startswith("task-")
        assert len(corr.agent_run_id) > 0

    def test_phase_id(self):
        corr = CorrelationId(task_id="task-0042", phase="3")
        assert corr.phase_id == "task-0042/p3"

    def test_full_chain(self):
        corr = CorrelationId(task_id="task-0042", phase="4", agent="developer")
        chain = corr.full_chain
        assert "task-0042" in chain
        assert "p4" in chain
        assert "developer" in chain

    def test_child(self):
        parent = CorrelationId(task_id="task-0042", phase="3", agent="architect", agent_run_id="run-001")
        child = parent.child("developer")
        assert child.task_id == parent.task_id
        assert child.parent_run_id == "run-001"

    def test_with_phase(self):
        corr = CorrelationId(task_id="task-0042", phase="1")
        p2 = corr.with_phase("2")
        assert p2.phase == "2"


class TestEvidence:
    """Evidence store tests."""

    def setup_method(self):
        clear_evidence()

    def test_write_evidence(self):
        record = write_evidence("task-001", "1", "test", {"key": "val"}, "test.tool")
        assert record.task_id == "task-001"
        assert len(record.sha256) == 64
        assert record.record_id.startswith("evt-")

    def test_evidence_integrity(self):
        """Verify evidence integrity checking — clean records pass."""
        write_evidence("task-002", "1", "step1", {"data": "original"}, "tool1")
        result = check_integrity("task-002")
        assert result["pass"], f"Clean records should pass: {result}"
        assert result["verified"] == 1

    def test_trace_chain_forward(self):
        write_evidence("task-003", "1", "step1", {}, "usecase.create")
        write_evidence("task-003", "1", "step2", {}, "requirement.create")
        write_evidence("task-003", "4", "step3", {}, "code.generate_patch")
        write_evidence("task-003", "5", "step4", {}, "test.run")
        write_evidence("task-003", "5", "step5", {}, "verify.verdict")

        chain = trace_chain("task-003")
        assert len(chain["forward"]["usecases"]) == 1
        assert len(chain["forward"]["requirements"]) == 1
        assert len(chain["forward"]["code"]) == 1
        assert len(chain["forward"]["tests"]) == 1
        assert len(chain["forward"]["verdicts"]) == 1

    def test_trace_chain_empty(self):
        chain = trace_chain("nonexistent")
        assert chain["forward"] == []

    def test_get_events_sorted(self):
        write_evidence("task-004", "1", "first", {}, "tool1")
        import time
        time.sleep(0.01)
        write_evidence("task-004", "1", "second", {}, "tool2")
        write_evidence("task-004", "1", "third", {}, "tool3")

        events = get_events("task-004")
        assert len(events) == 3
        assert events[0].step == "first"
        assert events[-1].step == "third"


class TestCircuitBreaker:
    """Circuit breaker tests."""

    def test_initial_state_closed(self):
        cb = CircuitBreaker(name="test")
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_success_keeps_closed(self):
        cb = CircuitBreaker(name="test")
        result = cb.call(lambda: "ok")
        assert result == "ok"
        assert cb.state == CircuitState.CLOSED

    def test_failures_trip_open(self):
        cb = CircuitBreaker(name="test", failure_threshold=2)
        for i in range(2):
            try:
                cb.call(lambda: 1 / 0)
            except ZeroDivisionError:
                pass
        assert cb.state == CircuitState.OPEN

    def test_open_raises(self):
        cb = CircuitBreaker(name="test", failure_threshold=1)
        try:
            cb.call(lambda: 1 / 0)
        except ZeroDivisionError:
            pass

        with pytest.raises(CircuitOpenError):
            cb.call(lambda: "should not execute")
