"""Trend detection module.

Compares recent activity against rolling averages to flag unusual patterns:
- Spike in events of a particular source type
- Drop in response / activity rates
- Unusually high or low meeting load
- Quiet periods

Usage::

    from src.advanced.trends import detect_trends
    alerts = detect_trends(cache)
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

# How many standard deviations above the mean constitutes a spike
SPIKE_THRESHOLD = 1.5
QUIET_THRESHOLD = 1.5  # same magnitude, below mean


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _daily_counts(
    events: list[dict[str, Any]],
    start: datetime,
    end: datetime,
    source_type: str | None = None,
) -> list[int]:
    """Return a list of daily event counts for the [start, end) window."""
    total_days = max(1, (end - start).days)
    buckets: dict[int, int] = defaultdict(int)
    for ev in events:
        dt = _parse_dt(ev.get("occurred_at") or ev.get("created_at"))
        if not dt:
            continue
        if source_type and ev.get("source_type") != source_type:
            continue
        if start <= dt < end:
            day_idx = (dt - start).days
            buckets[day_idx] += 1
    return [buckets[i] for i in range(total_days)]


def _source_types(events: list[dict[str, Any]]) -> set[str]:
    return {ev.get("source_type", "custom") for ev in events if ev.get("source_type")}


def detect_trends(
    cache: dict[str, Any],
    ref_dt: datetime | None = None,
    window_days: int = 7,
    history_days: int = 28,
) -> dict[str, Any]:
    """Detect trend anomalies in *cache* relative to a rolling history window.

    Args:
        cache: The ``last_sync.json`` cache dict.
        ref_dt: Reference "now" (defaults to UTC now).
        window_days: Number of recent days to evaluate.
        history_days: Total days of history used to compute rolling averages
                      (must be > window_days).

    Returns:
        A dict with keys: ``period``, ``alerts``, ``source_trends``,
        ``rolling_baseline``, ``generated_at``.
    """
    if ref_dt is None:
        ref_dt = datetime.now(tz=timezone.utc)

    events: list[dict[str, Any]] = cache.get("events", [])

    history_start = ref_dt - timedelta(days=history_days)
    recent_start = ref_dt - timedelta(days=window_days)

    # ── per-source trend analysis ────────────────────────────────────────
    source_trends: list[dict[str, Any]] = []
    alerts: list[dict[str, Any]] = []

    all_sources = _source_types(events)

    for src in sorted(all_sources):
        # Historical daily counts (full history window, excluding recent)
        historical_counts = _daily_counts(events, history_start, recent_start, source_type=src)
        # Recent daily counts
        recent_counts = _daily_counts(events, recent_start, ref_dt, source_type=src)

        recent_total = sum(recent_counts)
        recent_avg = recent_total / max(1, window_days)

        # Need at least a few data points for meaningful stats
        if len(historical_counts) >= 3:
            hist_mean = statistics.mean(historical_counts)
            hist_stdev = statistics.pstdev(historical_counts)
        else:
            hist_mean = recent_avg
            hist_stdev = 0.0

        # Determine trend direction
        if hist_stdev > 0:
            z_score = (recent_avg - hist_mean) / hist_stdev
        else:
            z_score = 0.0

        trend_dir = "stable"
        alert_msg: str | None = None

        if z_score >= SPIKE_THRESHOLD:
            trend_dir = "spike"
            alert_msg = (
                f"Spike in {src} activity: {recent_total} events in last {window_days} days "
                f"(historical avg {hist_mean:.1f}/day)."
            )
        elif z_score <= -QUIET_THRESHOLD:
            trend_dir = "quiet"
            alert_msg = (
                f"Quiet period for {src}: {recent_total} events in last {window_days} days "
                f"(historical avg {hist_mean:.1f}/day)."
            )

        entry = {
            "source_type": src,
            "recent_total": recent_total,
            "recent_avg_per_day": round(recent_avg, 2),
            "historical_avg_per_day": round(hist_mean, 2),
            "historical_stdev": round(hist_stdev, 2),
            "z_score": round(z_score, 2),
            "trend": trend_dir,
        }
        source_trends.append(entry)

        if alert_msg:
            alerts.append(
                {
                    "source_type": src,
                    "trend": trend_dir,
                    "message": alert_msg,
                    "severity": "high" if abs(z_score) >= SPIKE_THRESHOLD * 2 else "medium",
                }
            )

    # ── overall activity trend ────────────────────────────────────────────
    overall_recent = _daily_counts(events, recent_start, ref_dt)
    overall_hist = _daily_counts(events, history_start, recent_start)

    overall_recent_avg = sum(overall_recent) / max(1, window_days)
    if len(overall_hist) >= 3:
        overall_hist_mean = statistics.mean(overall_hist)
        overall_hist_stdev = statistics.pstdev(overall_hist)
    else:
        overall_hist_mean = overall_recent_avg
        overall_hist_stdev = 0.0

    return {
        "period": {
            "recent_start": recent_start.isoformat(),
            "recent_end": ref_dt.isoformat(),
            "history_start": history_start.isoformat(),
            "window_days": window_days,
            "history_days": history_days,
        },
        "alerts": alerts,
        "source_trends": source_trends,
        "rolling_baseline": {
            "overall_recent_avg_per_day": round(overall_recent_avg, 2),
            "overall_historical_avg_per_day": round(overall_hist_mean, 2),
            "overall_historical_stdev": round(overall_hist_stdev, 2),
        },
        "generated_at": ref_dt.isoformat(),
    }
