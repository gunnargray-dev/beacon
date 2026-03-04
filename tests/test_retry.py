from __future__ import annotations

from src.retry import RetryPolicy, compute_backoff_delay


def test_compute_backoff_delay_attempt_must_be_positive() -> None:
    policy = RetryPolicy()
    try:
        compute_backoff_delay(policy, 0)
    except ValueError as exc:
        assert "attempt" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_compute_backoff_delay_monotonic_without_jitter() -> None:
    policy = RetryPolicy(base_delay_s=0.5, max_delay_s=10.0, backoff_factor=2.0, jitter_s=0.0)
    d1 = compute_backoff_delay(policy, 1)
    d2 = compute_backoff_delay(policy, 2)
    d3 = compute_backoff_delay(policy, 3)
    assert d1 == 0.5
    assert d2 == 1.0
    assert d3 == 2.0


def test_compute_backoff_delay_caps_at_max_delay() -> None:
    policy = RetryPolicy(base_delay_s=1.0, max_delay_s=1.5, backoff_factor=10.0, jitter_s=0.0)
    assert compute_backoff_delay(policy, 1) == 1.0
    assert compute_backoff_delay(policy, 2) == 1.5
    assert compute_backoff_delay(policy, 3) == 1.5
