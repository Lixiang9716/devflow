"""Circuit Breaker pattern for external service resilience.

State machine: CLOSED → OPEN → HALF_OPEN → CLOSED (or back to OPEN).
Prevents cascading failures when LLM API, MCP servers, or Qdrant are down.
"""

from __future__ import annotations

import time
from enum import Enum
from dataclasses import dataclass, field


class CircuitState(str, Enum):
    CLOSED = "CLOSED"        # Normal — requests pass through
    OPEN = "OPEN"            # Tripped — requests fail immediately
    HALF_OPEN = "HALF_OPEN"  # Testing — one probe request allowed


@dataclass
class CircuitBreaker:
    """Per-service circuit breaker."""

    name: str
    failure_threshold: int = 5       # Consecutive failures to trip
    timeout_seconds: float = 30.0    # How long to stay OPEN before HALF_OPEN
    reset_timeout_seconds: float = 60.0

    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: float = 0.0
    last_success_time: float = 0.0
    opened_at: float = 0.0

    def call(self, func: callable, *args, **kwargs) -> object:
        """Execute a function through the circuit breaker.

        Returns the function result on success, or raises on OPEN circuit.
        """
        if self.state == CircuitState.OPEN:
            if time.time() - self.opened_at >= self.timeout_seconds:
                self.state = CircuitState.HALF_OPEN
            else:
                raise CircuitOpenError(
                    f"Circuit {self.name} is OPEN. "
                    f"Retry in {self.timeout_seconds - (time.time() - self.opened_at):.0f}s"
                )

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise e

    def _on_success(self):
        self.failure_count = 0
        self.last_success_time = time.time()
        self.state = CircuitState.CLOSED

    def _on_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            self.opened_at = time.time()

    def record_success(self):
        """Record a success (for async/non-exception calls)."""
        self._on_success()

    def record_failure(self):
        """Record a failure (for async/non-exception calls)."""
        self._on_failure()

    def is_allowed(self) -> bool:
        """Check if a request is currently allowed."""
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if time.time() - self.opened_at >= self.timeout_seconds:
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        return True  # HALF_OPEN allows one probe


class CircuitOpenError(Exception):
    """Raised when attempting to call through an OPEN circuit."""
    pass


# Pre-configured breakers for DevFlow services
DEFAULT_BREAKERS = {
    "cb_llm_api": CircuitBreaker(name="cb_llm_api"),
    "cb_github_mcp": CircuitBreaker(name="cb_github_mcp"),
    "cb_qdrant": CircuitBreaker(name="cb_qdrant"),
    "cb_cicd": CircuitBreaker(name="cb_cicd"),
}
