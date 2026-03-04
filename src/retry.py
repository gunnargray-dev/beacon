"""Retry utilities for transient connector failures.

Beacon's connectors are intentionally dependency-free; this module provides
simple exponential backoff with jitter using only the standard library.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Callable, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    """Configuration for retry behavior."""

    max_attempts: int = 3
    base_delay_s: float = 0.25
    max_delay_s: float = 5.0
    backoff_factor: float = 2.0
    jitter_s: float = 0.1


class RetryableError(Exception):
    """Raised for errors that should be retried."""


def compute_backoff_delay(policy: RetryPolicy, attempt: int) -> float:
    """Return delay for the given 1-indexed attempt.

    attempt=1 is the first failure (before the second try).
    """

    if attempt < 1:
        raise ValueError("attempt must be >= 1")
    raw = policy.base_delay_s * (policy.backoff_factor ** (attempt - 1))
    capped = min(float(raw), float(policy.max_delay_s))
    jitter = random.uniform(0.0, float(policy.jitter_s)) if policy.jitter_s > 0 else 0.0
    return capped + jitter


def retry_call(
    fn: Callable[[], T],
    *,
    policy: RetryPolicy | None = None,
    is_retryable: Callable[[Exception], bool] | None = None,
    on_retry: Callable[[int, Exception, float], None] | None = None,
) -> T:
    """Call fn() with retries.

    Args:
        fn: Callable with no args.
        policy: RetryPolicy. Defaults to a conservative policy.
        is_retryable: Function to classify retryable exceptions.
        on_retry: Callback invoked before sleeping for a retry: (attempt, exc, delay)
    """

    policy = policy or RetryPolicy()
    if policy.max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    attempt = 0
    while True:
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            attempt += 1
            should_retry = is_retryable(exc) if is_retryable else isinstance(exc, RetryableError)
            if not should_retry or attempt >= policy.max_attempts:
                raise
            delay = compute_backoff_delay(policy, attempt)
            if on_retry:
                on_retry(attempt, exc, delay)
            time.sleep(delay)
