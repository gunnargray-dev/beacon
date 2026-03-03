"""Meeting preparation brief generator.

Given an upcoming calendar event (as a dict from the sync cache), this module
gathers context from the rest of the cache — related emails, GitHub activity
mentioning attendees, and recent interactions — and returns a structured
meeting prep brief.

Usage::

    from src.advanced.meeting_prep import generate_meeting_prep
    brief = generate_meeting_prep(event, cache)
"""

from __future__ import annotations

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


def _extract_attendees(event: dict[str, Any]) -> list[str]:
    """Extract attendee names/emails from event metadata."""
    meta = event.get("metadata", {})
    attendees: list[str] = []

    # Common calendar event metadata shapes
    for key in ("attendees", "participants", "guests"):
        val = meta.get(key)
        if isinstance(val, list):
            for item in val:
                if isinstance(item, str):
                    attendees.append(item)
                elif isinstance(item, dict):
                    name = item.get("name") or item.get("email") or item.get("displayName", "")
                    if name:
                        attendees.append(name)

    return list(dict.fromkeys(attendees))  # deduplicate preserving order


def _related_emails(
    attendees: list[str],
    events: list[dict[str, Any]],
    lookback_days: int = 14,
    ref_dt: datetime | None = None,
) -> list[dict[str, Any]]:
    """Find email events mentioning any attendee within the lookback window."""
    if not attendees:
        return []
    if ref_dt is None:
        ref_dt = datetime.now(tz=timezone.utc)
    cutoff = ref_dt - timedelta(days=lookback_days)

    results = []
    for ev in events:
        if ev.get("source_type") != "email":
            continue
        dt = _parse_dt(ev.get("occurred_at") or ev.get("created_at"))
        if dt and dt < cutoff:
            continue
        text = (ev.get("title", "") + " " + ev.get("summary", "")).lower()
        if any(a.lower() in text for a in attendees):
            results.append(ev)
    return results[:10]


def _related_github(
    attendees: list[str],
    events: list[dict[str, Any]],
    lookback_days: int = 14,
    ref_dt: datetime | None = None,
) -> list[dict[str, Any]]:
    """Find GitHub events mentioning any attendee within the lookback window."""
    if not attendees:
        return []
    if ref_dt is None:
        ref_dt = datetime.now(tz=timezone.utc)
    cutoff = ref_dt - timedelta(days=lookback_days)

    results = []
    for ev in events:
        if ev.get("source_type") != "github":
            continue
        dt = _parse_dt(ev.get("occurred_at") or ev.get("created_at"))
        if dt and dt < cutoff:
            continue
        text = (ev.get("title", "") + " " + ev.get("summary", "")).lower()
        if any(a.lower() in text for a in attendees):
            results.append(ev)
    return results[:10]


def _pending_actions_for_attendees(
    attendees: list[str],
    action_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return open action items that mention any attendee."""
    if not attendees:
        return []
    results = []
    for ai in action_items:
        if ai.get("completed"):
            continue
        text = (ai.get("title", "") + " " + ai.get("notes", "")).lower()
        if any(a.lower() in text for a in attendees):
            results.append(ai)
    return results


def _event_title_topics(event: dict[str, Any]) -> list[str]:
    """Extract likely topic keywords from event title."""
    stop_words = {"the", "a", "an", "and", "or", "with", "for", "of", "to", "in", "on"}
    title = event.get("title", "")
    words = [w.strip(".,:-()[]") for w in title.split()]
    return [w for w in words if len(w) > 2 and w.lower() not in stop_words]


def generate_meeting_prep(
    event: dict[str, Any],
    cache: dict[str, Any],
    lookback_days: int = 14,
    ref_dt: datetime | None = None,
) -> dict[str, Any]:
    """Generate a structured meeting prep brief for *event*.

    Args:
        event: A calendar event dict from the sync cache.
        cache: The full ``last_sync.json`` cache dict.
        lookback_days: How many days back to search for context.
        ref_dt: Reference "now" for the lookback window (defaults to UTC now).

    Returns:
        A dict with keys: ``event``, ``attendees``, ``topics``,
        ``related_emails``, ``related_github``, ``pending_actions``,
        ``suggested_talking_points``, ``generated_at``.
    """
    if ref_dt is None:
        ref_dt = datetime.now(tz=timezone.utc)

    all_events: list[dict[str, Any]] = cache.get("events", [])
    action_items: list[dict[str, Any]] = cache.get("action_items", [])

    attendees = _extract_attendees(event)
    topics = _event_title_topics(event)

    related_emails = _related_emails(attendees, all_events, lookback_days, ref_dt)
    related_github = _related_github(attendees, all_events, lookback_days, ref_dt)
    # Use topics as fallback search terms when no attendees are extracted
    search_terms = attendees or topics
    pending_actions = _pending_actions_for_attendees(search_terms, action_items)

    # Derive talking points from context
    talking_points: list[str] = []

    if pending_actions:
        talking_points.append(
            f"Follow up on {len(pending_actions)} open action item(s) involving attendees."
        )
    if related_github:
        pr_titles = [
            ev.get("title", "")
            for ev in related_github
            if "pull_request" in (ev.get("title", "") + ev.get("summary", "")).lower()
        ]
        if pr_titles:
            talking_points.append(f"Recent PR activity: {pr_titles[0][:80]}")
    if related_emails:
        talking_points.append(
            f"{len(related_emails)} recent email thread(s) with attendees."
        )
    if topics:
        talking_points.append(f"Agenda keywords: {', '.join(topics[:5])}")

    return {
        "event": {
            "id": event.get("id", ""),
            "title": event.get("title", ""),
            "occurred_at": event.get("occurred_at", ""),
            "summary": event.get("summary", ""),
            "url": event.get("url", ""),
        },
        "attendees": attendees,
        "topics": topics,
        "related_emails": [
            {"title": e.get("title", ""), "occurred_at": e.get("occurred_at", ""), "url": e.get("url", "")}
            for e in related_emails
        ],
        "related_github": [
            {"title": e.get("title", ""), "occurred_at": e.get("occurred_at", ""), "url": e.get("url", "")}
            for e in related_github
        ],
        "pending_actions": [
            {"title": ai.get("title", ""), "priority": ai.get("priority", "medium"), "url": ai.get("url", "")}
            for ai in pending_actions
        ],
        "suggested_talking_points": talking_points,
        "generated_at": ref_dt.isoformat(),
    }
