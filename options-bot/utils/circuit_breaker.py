"""
Circuit breaker pattern for external service calls.
Prevents cascading failures when Theta Terminal or Alpaca is down.

States:
    CLOSED   — Normal operation, calls pass through
    OPEN     — Service is down, calls fail fast (no network call)
    HALF_OPEN — One test call allowed; success → CLOSED, failure → OPEN

Usage:
    breaker = CircuitBreaker(name="theta", failure_threshold=3, reset_timeout=300)

    if breaker.can_execute():
        try:
            result = call_theta(...)
            breaker.record_success()
        except Exception as e:
            breaker.record_failure()
            raise
    else:
        logger.warning(f"Circuit breaker {breaker.name} is OPEN — skipping call")
"""

import logging
import threading
import time
from enum import Enum

logger = logging.getLogger("options-bot.circuit_breaker")


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Thread-safe circuit breaker for external service calls."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        reset_timeout: float = 300.0,
        half_open_max_calls: int = 1,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.half_open_max_calls = half_open_max_calls

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._half_open_calls = 0
        self._lock = threading.Lock()

        self._total_successes = 0
        self._total_failures = 0
        self._total_rejected = 0

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if time.time() - self._last_failure_time >= self.reset_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                    logger.info(
                        f"Circuit breaker '{self.name}': OPEN → HALF_OPEN "
                        f"(reset timeout elapsed)"
                    )
            return self._state

    def can_execute(self) -> bool:
        """Check if a call is allowed."""
        current = self.state
        with self._lock:
            if current == CircuitState.CLOSED:
                return True
            elif current == CircuitState.HALF_OPEN:
                if self._half_open_calls < self.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                return False
            else:  # OPEN
                self._total_rejected += 1
                return False

    def record_success(self):
        """Record a successful call."""
        with self._lock:
            self._total_successes += 1
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                logger.info(
                    f"Circuit breaker '{self.name}': HALF_OPEN → CLOSED "
                    f"(test call succeeded)"
                )
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0

    def record_failure(self):
        """Record a failed call."""
        with self._lock:
            self._total_failures += 1
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning(
                    f"Circuit breaker '{self.name}': HALF_OPEN → OPEN "
                    f"(test call failed)"
                )
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    self._state = CircuitState.OPEN
                    logger.warning(
                        f"Circuit breaker '{self.name}': CLOSED → OPEN "
                        f"(threshold {self.failure_threshold} reached). "
                        f"Will retry in {self.reset_timeout}s."
                    )

    def get_stats(self) -> dict:
        """Return circuit breaker stats for monitoring."""
        with self._lock:
            return {
                "name": self.name,
                "state": self._state.value,
                "failure_count": self._failure_count,
                "total_successes": self._total_successes,
                "total_failures": self._total_failures,
                "total_rejected": self._total_rejected,
                "last_failure_time": self._last_failure_time,
            }


def exponential_backoff(attempt: int, base: float = 2.0, max_delay: float = 60.0) -> float:
    """
    Calculate exponential backoff delay with jitter.
    attempt=1 → ~2s, attempt=2 → ~4s, attempt=3 → ~8s, etc.
    """
    import random
    delay = min(base ** attempt, max_delay)
    # Add ±25% jitter to prevent thundering herd
    jitter = delay * 0.25 * (2 * random.random() - 1)
    return max(0.1, delay + jitter)
