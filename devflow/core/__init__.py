"""Core infrastructure: Result types, correlation IDs, evidence, logging, caching."""

from devflow.core.result import Result, Success, Failure, ErrorCode
from devflow.core.correlation import CorrelationId, new_correlation
from devflow.core.evidence import write_evidence, trace_chain, check_integrity
from devflow.core.logging import structured_log
from devflow.core.circuit_breaker import CircuitBreaker, CircuitState

__all__ = [
    "Result", "Success", "Failure", "ErrorCode",
    "CorrelationId", "new_correlation",
    "write_evidence", "trace_chain", "check_integrity",
    "structured_log",
    "CircuitBreaker", "CircuitState",
]
