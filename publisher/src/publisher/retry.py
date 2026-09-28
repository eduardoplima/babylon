"""Retry with exponential backoff for transient API errors."""
import random
import time
from typing import Callable, TypeVar

T = TypeVar("T")


class PlatformError(Exception):
    """An API call failed. `status` and `reason` come from the platform's response."""

    def __init__(self, message: str, *, status: int | None = None, reason: str | None = None):
        super().__init__(message)
        self.status = status
        self.reason = reason


class TransientError(PlatformError):
    """Worth retrying: 5xx, rate limits, network errors."""


class PermanentError(PlatformError):
    """Retrying now won't help: invalid input, forbidden, quota exhausted.
    `retry_later=True` marks limits that reset (daily quotas): no immediate retries, but
    publish-due tries again after the platform's cooldown."""

    def __init__(self, message: str, *, status: int | None = None, reason: str | None = None,
                 retry_later: bool = False):
        super().__init__(message, status=status, reason=reason)
        self.retry_later = retry_later


def with_retry(fn: Callable[[], T], *, attempts: int = 5, base_delay: float = 2.0, max_delay: float = 60.0,
               sleep: Callable[[float], None] = time.sleep, on_retry: Callable[[int, Exception, float], None] | None = None) -> T:
    """Call `fn`, retrying TransientError with full-jitter exponential backoff.
    PermanentError and anything else propagate immediately."""
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except TransientError as exc:
            if attempt == attempts:
                raise
            delay = random.uniform(0, min(max_delay, base_delay * 2 ** (attempt - 1)))
            if on_retry:
                on_retry(attempt, exc, delay)
            sleep(delay)
    raise AssertionError("unreachable")
