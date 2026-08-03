"""Idempotency patterns for all write operations.

f(x) executed 1 time = f(x) executed N times.

Implementation:
- MinIO: filename includes content hash → overwrite same file
- Qdrant: use task_id + entry_hash as point ID → upsert
- GitHub: conditional requests (check existence before create)
- LLM: cache key = sha256(prompt + model + params) → return cached
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional, Any


def make_content_hash(*args: Any, **kwargs: Any) -> str:
    """Generate a deterministic content hash from operation parameters."""
    payload = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def make_idempotency_key(prefix: str, *components: str) -> str:
    """Create an idempotency key from prefix + hash(components)."""
    content = ":".join(str(c) for c in components)
    content_hash = hashlib.sha256(content.encode()).hexdigest()[:12]
    return f"{prefix}-{content_hash}"


@dataclass
class IdempotencyStore:
    """In-memory store mapping idempotency keys to results.

    In production, backed by Redis or a MinIO metadata index.
    """

    _store: dict[str, Any] = field(default_factory=dict)

    def check(self, key: str) -> Optional[Any]:
        """Return cached result if this operation was already performed."""
        return self._store.get(key)

    def record(self, key: str, result: Any):
        """Record a new operation result."""
        self._store[key] = result

    def clear(self):
        self._store.clear()


# Global instance
_idempotency = IdempotencyStore()


def idempotent(key: str):
    """Decorator for idempotent operations.

    Same key → returns cached result without re-execution.
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            cached = _idempotency.check(key)
            if cached is not None:
                return cached
            result = func(*args, **kwargs)
            _idempotency.record(key, result)
            return result

        return wrapper

    return decorator


def check_exists(key: str) -> Optional[Any]:
    """Check if an idempotent operation was already performed."""
    return _idempotency.check(key)


def record_operation(key: str, result: Any):
    """Record an idempotent operation result."""
    _idempotency.record(key, result)


def clear_store():
    """Clear the idempotency store (for testing)."""
    _idempotency.clear()
