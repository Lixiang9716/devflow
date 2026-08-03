"""Unified Result type for all Agent outputs.

All Agent operations return Result<T> = Success<T> | Failure.
This allows callers to safely determine whether a failure is retryable,
permanent, or needs human intervention.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Generic, TypeVar, Optional, Any

T = TypeVar("T")


class ErrorCode(str, Enum):
    """Classification of failures for automatic handling decisions."""

    RETRYABLE = "RETRYABLE"    # Transient: LLM timeout, MCP unavailable — retry with backoff
    PERMANENT = "PERMANENT"    # Non-recoverable: schema validation failed, bad input
    NEED_HUMAN = "NEED_HUMAN"  # Ambiguity cannot be resolved automatically


@dataclass(frozen=True)
class Success(Generic[T]):
    """Successful operation result with metadata."""

    data: T
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def status(self) -> str:
        return "ok"


@dataclass(frozen=True)
class Failure:
    """Failed operation result with error classification."""

    code: ErrorCode
    agent: str
    phase: str
    message: str
    evidence_ref: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def status(self) -> str:
        return "error"


Result = Success[T] | Failure


def ok(data: T, **meta: Any) -> Success[T]:
    """Create a successful result."""
    meta.setdefault("timestamp", time.time())
    return Success(data=data, meta=meta)


def retryable(agent: str, phase: str, message: str, **detail: Any) -> Failure:
    """Create a retryable failure."""
    return Failure(
        code=ErrorCode.RETRYABLE,
        agent=agent,
        phase=phase,
        message=message,
        detail=detail,
    )


def permanent(agent: str, phase: str, message: str, **detail: Any) -> Failure:
    """Create a permanent failure."""
    return Failure(
        code=ErrorCode.PERMANENT,
        agent=agent,
        phase=phase,
        message=message,
        detail=detail,
    )


def need_human(agent: str, phase: str, message: str, **detail: Any) -> Failure:
    """Create a failure that requires human intervention."""
    return Failure(
        code=ErrorCode.NEED_HUMAN,
        agent=agent,
        phase=phase,
        message=message,
        detail=detail,
    )


def is_ok(result: Result[T]) -> bool:
    """Check if result is successful."""
    return isinstance(result, Success)


def is_failure(result: Result[T]) -> bool:
    """Check if result is a failure."""
    return isinstance(result, Failure)


def unwrap(result: Result[T]) -> T:
    """Extract data from a successful result or raise on failure."""
    if isinstance(result, Success):
        return result.data
    raise ValueError(f"Cannot unwrap failure: {result.message}")


def match_result(
    result: Result[T],
    on_success: callable = None,
    on_retryable: callable = None,
    on_permanent: callable = None,
    on_need_human: callable = None,
) -> Any:
    """Pattern-match a Result to handlers."""
    if isinstance(result, Success):
        if on_success:
            return on_success(result.data)
        return result
    elif isinstance(result, Failure):
        handlers = {
            ErrorCode.RETRYABLE: on_retryable,
            ErrorCode.PERMANENT: on_permanent,
            ErrorCode.NEED_HUMAN: on_need_human,
        }
        handler = handlers.get(result.code)
        if handler:
            return handler(result)
    return result
