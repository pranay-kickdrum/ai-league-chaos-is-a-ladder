"""Resilience utilities: retry with exponential backoff + circuit breaker."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from functools import wraps
from typing import Any, Callable, TypeVar

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

# ---------------------------------------------------------------------------
# Circuit breaker state
# ---------------------------------------------------------------------------

_failure_counts: dict[str, int] = defaultdict(int)
_circuit_open_until: dict[str, float] = defaultdict(float)

CIRCUIT_THRESHOLD = 5  # consecutive failures to trip
CIRCUIT_COOLDOWN = 300  # seconds to skip the source


def _is_circuit_open(source: str) -> bool:
    if _circuit_open_until[source] > time.time():
        return True
    if _circuit_open_until[source] > 0:
        # Cooldown expired — reset
        _failure_counts[source] = 0
        _circuit_open_until[source] = 0.0
    return False


def record_success(source: str) -> None:
    _failure_counts[source] = 0


def record_failure(source: str) -> None:
    _failure_counts[source] += 1
    if _failure_counts[source] >= CIRCUIT_THRESHOLD:
        _circuit_open_until[source] = time.time() + CIRCUIT_COOLDOWN
        logger.warning("Circuit OPEN for %s (cooldown %ds)", source, CIRCUIT_COOLDOWN)


class CircuitOpenError(Exception):
    """Raised when circuit is tripped — skip this source."""

    def __init__(self, source: str):
        self.source = source
        super().__init__(f"Circuit open for {source}")


# ---------------------------------------------------------------------------
# Retry decorator
# ---------------------------------------------------------------------------

api_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    retry=retry_if_exception_type((Exception,)),
    reraise=True,
)


def resilient_api_call(source: str):
    """Decorator: circuit breaker check + tenacity retry + failure tracking."""

    def decorator(fn: F) -> F:
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if _is_circuit_open(source):
                raise CircuitOpenError(source)

            @api_retry
            async def _inner() -> Any:
                return await fn(*args, **kwargs)

            try:
                result = await _inner()
                record_success(source)
                return result
            except CircuitOpenError:
                raise
            except Exception:
                record_failure(source)
                raise

        return wrapper  # type: ignore[return-value]

    return decorator
