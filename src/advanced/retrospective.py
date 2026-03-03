"""Weekly retrospective generator.

Reads the sync cache and produces a structured summary of the past 7 days,
with comparison against the prior 7-day window.

Usage::

    from src.advanced.retrospective import generate_retrospective
    retro = generate_retrospective(cache)
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any


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


def _week_bounds(ref: datetime, weeks_ago: int = 0) -> tuple[datetime, datetime]:
    """Return (start, end) for a 7-day window ending *weeks_ago* weeks before ref."""
    end = ref - timedelta(weeks=weeks_ago)
    start = end - timedelta(days=7)
    return start, end


def _events_in_window(
    events: list[dict[str, Any]], start: datetime, end: datetime
) -> list[dict[str, Any]]:
    result = []
    for ev in events:
        dt = _parse_dt(ev.get("occurred_at") or ev.get("created_at"))
        if dt and start <= dt < end:
            result.append(ev)
    return result


def _actions_completed_in_window(
    action_items: list[dict[str, Any]], start: datetime, end: datetime
) -> list[dict[str, Any]]:
    result = []
    for ai in action_items:
        if not ai.get("completed"):
            continue
        # Use created_at as a proxy if no completed_at
        dt = _parse_dt(ai.get("completed_at") or ai.get("created_at"))
        if dt and start <= dt < end:
            result.append(ai)
    return result


def _count_by_source(items: list[dict[str, Any]]) -> dict[str, int]:
    return dict(Counter(ev.get("source_type", "custom") for ev in items))


def _meetings(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e for e in events if e.get("source_type") == "calendar"]


def _prs(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        e
        for e in events
        if e.get("source_type") == "github"
        and "pull_request" in (e.get("title", "") + e.get("summary", "")).lower()
    ]


def _emails(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e for e in events if e.get("source_type") == "email"]


def _pct_change(current: int | float, previous: int | float) -> float | None:
    if previous == 0:
        return None
    return round((current - previous) / previous * 100, 1)


def generate_retrospective(
    cache: dict[str, Any],
    ref_dt: datetime | None = None,
) -> dict[str, Any]:
    """Generate a weekly retrospective report from *cache*.

    Args:
        cache: The ``last_sync.json`` cache dict
                (keys: ``synced_at``, ``events``, ``action_items``).
        ref_dt: Reference point for "now" (defaults to current UTC time).
                Useful for testing.

    Returns:
        A dict with keys:
        ``period``, ``metrics``, ``top_sources``, ``highlights``,
        ``trend_vs_prior_week``, ``generated_at``.
    """
    if ref_dt is None:
        ref_dt = datetime.now(tz=timezone.utc)

    events: list[dict[str, Any]] = cache.get("events", [])
    action_items: list[dict[str, Any]] = cache.get("action_items", [])

    # ── current week ──────────────────────────────────────────────────────
    cur_start, cur_end = _week_bounds(ref_dt, weeks_ago=0)
    cur_events = _events_in_window(events, cur_start, cur_end)
    cur_actions_done = _actions_completed_in_window(action_items, cur_start, cur_end)

    cur_meetings = _meetings(cur_events)
    cur_prs = _prs(cur_events)
    cur_emails = _emails(cur_events)

    # ── prior week ────────────────────────────────────────────────────────
    prev_start, prev_end = _week_bounds(ref_dt, weeks_ago=1)
    prev_events = _events_in_window(events, prev_start, prev_end)
    prev_actions_done = _actions_completed_in_window(action_items, prev_start, prev_end)

    prev_meetings = _meetings(prev_events)
    prev_prs = _prs(prev_events)
    prev_emails = _emails(prev_events)

    # ── highlights: top 5 events by priority keywords ─────────────────────
    highlight_keywords = {"merged", "approved", "accepted", "completed", "done", "resolved"}
    highlights = [
        ev
        for ev in cur_events
        if any(k in (ev.get("title", "") + ev.get("summary", "")).lower() for k in highlight_keywords)
    ][:5]

    return {
        "period": {
            "start": cur_start.isoformat(),
            "end": cur_end.isoformat(),
        },
        "metrics": {
            "total_events": len(cur_events),
            "meetings": len(cur_meetings),
            "prs_reviewed": len(cur_prs),
            "emails_processed": len(cur_emails),
            "actions_completed": len(cur_actions_done),
            "by_source": _count_by_source(cur_events),
        },
        "trend_vs_prior_week": {
            "total_events_pct": _pct_change(len(cur_events), len(prev_events)),
            "meetings_pct": _pct_change(len(cur_meetings), len(prev_meetings)),
            "prs_pct": _pct_change(len(cur_prs), len(prev_prs)),
            "emails_pct": _pct_change(len(cur_emails), len(prev_emails)),
            "actions_completed_pct": _pct_change(len(cur_actions_done), len(prev_actions_done)),
            "prior_period": {
                "start": prev_start.isoformat(),
                "end": prev_end.isoformat(),
                "total_events": len(prev_events),
                "meetings": len(prev_meetings),
                "prs_reviewed": len(prev_prs),
                "emails_processed": len(prev_emails),
                "actions_completed": len(prev_actions_done),
            },
        },
        "top_sources": sorted(
            _count_by_source(cur_events).items(), key=lambda x: x[1], reverse=True
        ),
        "highlights": [
            {"title": ev.get("title", ""), "source_type": ev.get("source_type", ""), "url": ev.get("url", "")}
            for ev in highlights
        ],
        "generated_at": ref_dt.isoformat(),
    }
