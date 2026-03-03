"""Time audit module.

Categorises the user's time based on events in the sync cache:
- meetings    (calendar events)
- deep_work   (GitHub PRs, code reviews, commits)
- admin       (emails, general notifications)
- learning    (news, hacker_news)
- other       (anything that doesn't fit the above)

Produces daily and weekly breakdowns and flags meeting overload.

Usage::

    from src.advanced.time_audit import generate_time_audit
    audit = generate_time_audit(cache)
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

# Number of consecutive meeting-heavy days that triggers overload alert
MEETING_OVERLOAD_THRESHOLD = 0.5  # fraction of a day's events that are meetings
MEETING_OVERLOAD_DAYS = 3  # alert if threshold exceeded this many days in a row


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


def _categorise(event: dict[str, Any]) -> str:
    source = event.get("source_type", "custom")
    if source == "calendar":
        return "meetings"
    if source == "github":
        return "deep_work"
    if source == "email":
        return "admin"
    if source in ("news", "hacker_news"):
        return "learning"
    return "other"


def _week_bounds(ref: datetime, weeks_ago: int = 0) -> tuple[datetime, datetime]:
    end = ref - timedelta(weeks=weeks_ago)
    start = end - timedelta(days=7)
    return start, end


def generate_time_audit(
    cache: dict[str, Any],
    ref_dt: datetime | None = None,
    lookback_days: int = 7,
) -> dict[str, Any]:
    """Generate a time audit report from *cache*.

    Args:
        cache: The ``last_sync.json`` cache dict.
        ref_dt: Reference "now" (defaults to UTC now).
        lookback_days: How many days to include in the audit window.

    Returns:
        A dict with keys: ``period``, ``category_totals``, ``daily``,
        ``meeting_overload``, ``insights``, ``generated_at``.
    """
    if ref_dt is None:
        ref_dt = datetime.now(tz=timezone.utc)

    events: list[dict[str, Any]] = cache.get("events", [])
    cutoff = ref_dt - timedelta(days=lookback_days)

    # Filter to window
    window_events = []
    for ev in events:
        dt = _parse_dt(ev.get("occurred_at") or ev.get("created_at"))
        if dt and dt >= cutoff:
            window_events.append((dt, ev))

    # ── category totals ──────────────────────────────────────────────────
    category_counts: dict[str, int] = defaultdict(int)
    for _, ev in window_events:
        category_counts[_categorise(ev)] += 1

    total = sum(category_counts.values()) or 1
    category_totals = {
        cat: {"count": count, "pct": round(count / total * 100, 1)}
        for cat, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True)
    }

    # ── daily breakdown ──────────────────────────────────────────────────
    daily: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for dt, ev in window_events:
        day = dt.strftime("%Y-%m-%d")
        cat = _categorise(ev)
        daily[day][cat] += 1

    daily_list = [
        {
            "date": day,
            **{k: int(v) for k, v in counts.items()},
            "total": sum(counts.values()),
        }
        for day, counts in sorted(daily.items())
    ]

    # ── meeting overload detection ───────────────────────────────────────
    overload_days: list[str] = []
    for day_data in daily_list:
        day_total = day_data.get("total", 0)
        if day_total == 0:
            continue
        meeting_frac = day_data.get("meetings", 0) / day_total
        if meeting_frac >= MEETING_OVERLOAD_THRESHOLD:
            overload_days.append(day_data["date"])

    # Check for consecutive overload streak
    consecutive_streak = 0
    max_streak = 0
    for day_data in daily_list:
        if day_data["date"] in overload_days:
            consecutive_streak += 1
            max_streak = max(max_streak, consecutive_streak)
        else:
            consecutive_streak = 0

    meeting_overload = {
        "overload_days": overload_days,
        "max_consecutive_streak": max_streak,
        "alert": max_streak >= MEETING_OVERLOAD_DAYS,
    }

    # ── insights ─────────────────────────────────────────────────────────
    insights: list[str] = []
    meeting_pct = category_totals.get("meetings", {}).get("pct", 0.0)
    if meeting_pct > 50:
        insights.append(f"Meetings dominate at {meeting_pct}% of activity — consider blocking focus time.")
    deep_work_pct = category_totals.get("deep_work", {}).get("pct", 0.0)
    if deep_work_pct < 10 and total > 5:
        insights.append("Low deep-work signal — fewer than 10% of events are GitHub/coding activity.")
    if meeting_overload["alert"]:
        insights.append(
            f"Meeting overload detected: {max_streak} consecutive days with ≥50% meeting load."
        )
    if not insights:
        insights.append("Time distribution looks balanced.")

    return {
        "period": {
            "start": cutoff.isoformat(),
            "end": ref_dt.isoformat(),
            "days": lookback_days,
        },
        "category_totals": category_totals,
        "daily": daily_list,
        "meeting_overload": meeting_overload,
        "insights": insights,
        "generated_at": ref_dt.isoformat(),
    }
