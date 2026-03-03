"""Daily briefing generator -- structured morning summary across all sources."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.models import ActionItem, Briefing, Event, Priority, SourceType


_CACHE_DIR = Path.home() / ".cache" / "beacon"
_SYNC_FILE = _CACHE_DIR / "last_sync.json"


def _load_sync_data(path: Path | None = None) -> dict[str, Any]:
    """Load the last sync cache file.

    Args:
        path: Override path to the sync cache file. Defaults to
              ~/.cache/beacon/last_sync.json

    Returns:
        Parsed JSON dict, or empty dict if file missing / malformed.
    """
    target = path or _SYNC_FILE
    if not target.exists():
        return {}
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _event_from_dict(d: dict[str, Any]) -> Event:
    """Reconstruct an Event from a sync-cache dict."""
    occurred = _parse_iso(d.get("occurred_at"))
    if occurred is None:
        occurred = datetime.now(tz=timezone.utc)
    try:
        stype = SourceType(d.get("source_type", "custom"))
    except ValueError:
        stype = SourceType.CUSTOM
    return Event(
        title=d.get("title", ""),
        source_id=d.get("source_id", ""),
        source_type=stype,
        occurred_at=occurred,
        summary=d.get("summary", ""),
        url=d.get("url", ""),
        metadata=d.get("metadata", {}),
    )


def _action_from_dict(d: dict[str, Any]) -> ActionItem:
    """Reconstruct an ActionItem from a sync-cache dict."""
    try:
        stype = SourceType(d.get("source_type", "custom"))
    except ValueError:
        stype = SourceType.CUSTOM
    try:
        pri = Priority(d.get("priority", "medium"))
    except ValueError:
        pri = Priority.MEDIUM
    return ActionItem(
        title=d.get("title", ""),
        source_id=d.get("source_id", ""),
        source_type=stype,
        priority=pri,
        due_at=_parse_iso(d.get("due_at")),
        url=d.get("url", ""),
        completed=d.get("completed", False),
        notes=d.get("notes", ""),
        metadata=d.get("metadata", {}),
    )


class BriefingGenerator:
    """Generate structured daily briefings from sync data.

    Usage::

        gen = BriefingGenerator()
        briefing = gen.generate()          # from default cache
        briefing = gen.generate(events=my_events, action_items=my_actions)
    """

    def __init__(self, sync_path: Path | None = None) -> None:
        self._sync_path = sync_path

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        events: list[Event] | None = None,
        action_items: list[ActionItem] | None = None,
    ) -> Briefing:
        """Build a Briefing for today.

        If *events* / *action_items* are not provided, they are loaded from
        the sync cache.
        """
        if events is None or action_items is None:
            data = _load_sync_data(self._sync_path)
            if events is None:
                events = [_event_from_dict(e) for e in data.get("events", [])]
            if action_items is None:
                action_items = [_action_from_dict(a) for a in data.get("action_items", [])]

        now = datetime.now(tz=timezone.utc)
        briefing = Briefing(date=now)

        # Track which sources contributed
        seen_sources: set[str] = set()
        for ev in events:
            briefing.add_event(ev)
            seen_sources.add(ev.source_type.value)
        for ai in action_items:
            briefing.add_action_item(ai)
            seen_sources.add(ai.source_type.value)

        briefing.sources_synced = sorted(seen_sources)
        briefing.summary = self._build_summary(briefing)
        return briefing

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    @staticmethod
    def _build_summary(briefing: Briefing) -> str:
        parts: list[str] = []
        n_events = len(briefing.events)
        n_actions = len(briefing.action_items)
        n_urgent = len(briefing.urgent_actions())
        n_pending = len(briefing.pending_actions())

        parts.append(f"{n_events} event(s) across {len(briefing.sources_synced)} source(s).")

        if n_urgent:
            parts.append(f"{n_urgent} urgent action(s) requiring immediate attention.")
        if n_pending:
            parts.append(f"{n_pending} pending action item(s).")
        if not n_actions:
            parts.append("No action items -- clear schedule ahead.")

        return " ".join(parts)

    @staticmethod
    def format_text(briefing: Briefing) -> str:
        """Render a briefing as a human-readable text block."""
        lines: list[str] = []
        lines.append(f"=== Beacon Briefing -- {briefing.date.strftime('%A, %B %d, %Y')} ===")
        lines.append("")
        lines.append(briefing.summary)
        lines.append("")

        if briefing.events:
            lines.append("--- Events ---")
            for ev in briefing.events:
                ts = ev.occurred_at.strftime("%H:%M") if ev.occurred_at else "??:??"
                lines.append(f"  [{ev.source_type.value:<12}] {ts}  {ev.title}")
            lines.append("")

        pending = briefing.pending_actions()
        if pending:
            lines.append("--- Action Items ---")
            for ai in pending:
                marker = "!" if ai.priority in (Priority.HIGH, Priority.URGENT) else " "
                lines.append(f"  [{marker}] [{ai.priority.value:<6}] {ai.title}")
            lines.append("")

        lines.append(f"Sources: {', '.join(briefing.sources_synced) or 'none'}")
        return "\n".join(lines)
