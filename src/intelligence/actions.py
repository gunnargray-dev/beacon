"""Action item extractor -- surface todos, review requests, deadlines from all sources."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.models import ActionItem, Event, Priority, SourceType


# ---------------------------------------------------------------------------
# Extraction rules per source type
# ---------------------------------------------------------------------------

_REVIEW_KEYWORDS = {"review", "approve", "feedback", "sign-off", "sign off"}
_DEADLINE_KEYWORDS = {"deadline", "due", "expires", "by eod", "by end of day", "asap", "urgent"}
_TODO_KEYWORDS = {"todo", "to-do", "action item", "follow up", "follow-up", "action required"}


def _title_lower(ev: Event) -> str:
    return (ev.title or "").lower()


def _summary_lower(ev: Event) -> str:
    return (ev.summary or "").lower()


def _has_keyword(text: str, keywords: set[str]) -> bool:
    return any(kw in text for kw in keywords)


class ActionExtractor:
    """Extract actionable items from events across all sources.

    Usage::

        extractor = ActionExtractor()
        actions = extractor.extract(events)
        actions = extractor.extract(events, existing_actions=current_items)
    """

    def extract(
        self,
        events: list[Event],
        existing_actions: list[ActionItem] | None = None,
    ) -> list[ActionItem]:
        """Extract action items from a list of events.

        Deduplicates against *existing_actions* by title if provided.
        """
        existing_titles = set()
        if existing_actions:
            existing_titles = {a.title.lower() for a in existing_actions}

        extracted: list[ActionItem] = []
        for ev in events:
            items = self._extract_from_event(ev)
            for item in items:
                if item.title.lower() not in existing_titles:
                    extracted.append(item)
                    existing_titles.add(item.title.lower())

        return extracted

    def _extract_from_event(self, ev: Event) -> list[ActionItem]:
        """Apply source-specific heuristics to extract action items."""
        handlers = {
            SourceType.GITHUB: self._from_github,
            SourceType.EMAIL: self._from_email,
            SourceType.CALENDAR: self._from_calendar,
            SourceType.NEWS: self._from_generic,
            SourceType.HACKER_NEWS: self._from_generic,
            SourceType.WEATHER: self._from_weather,
        }
        handler = handlers.get(ev.source_type, self._from_generic)
        return handler(ev)

    # ------------------------------------------------------------------
    # Source-specific extractors
    # ------------------------------------------------------------------

    def _from_github(self, ev: Event) -> list[ActionItem]:
        items: list[ActionItem] = []
        title_l = _title_lower(ev)
        summary_l = _summary_lower(ev)
        combined = title_l + " " + summary_l

        if _has_keyword(combined, _REVIEW_KEYWORDS):
            items.append(ActionItem(
                title=f"Review: {ev.title}",
                source_id=ev.source_id,
                source_type=ev.source_type,
                priority=Priority.HIGH,
                url=ev.url,
                notes="PR/issue needs your review.",
                metadata=ev.metadata,
            ))
        elif "assigned" in combined or "mention" in combined:
            items.append(ActionItem(
                title=f"Respond: {ev.title}",
                source_id=ev.source_id,
                source_type=ev.source_type,
                priority=Priority.MEDIUM,
                url=ev.url,
                notes="You were assigned or mentioned.",
                metadata=ev.metadata,
            ))

        return items

    def _from_email(self, ev: Event) -> list[ActionItem]:
        items: list[ActionItem] = []
        combined = _title_lower(ev) + " " + _summary_lower(ev)

        if _has_keyword(combined, _DEADLINE_KEYWORDS):
            items.append(ActionItem(
                title=f"Deadline: {ev.title}",
                source_id=ev.source_id,
                source_type=ev.source_type,
                priority=Priority.URGENT,
                url=ev.url,
                notes="Email mentions a deadline or urgency.",
                metadata=ev.metadata,
            ))
        elif _has_keyword(combined, _TODO_KEYWORDS | _REVIEW_KEYWORDS):
            items.append(ActionItem(
                title=f"Action: {ev.title}",
                source_id=ev.source_id,
                source_type=ev.source_type,
                priority=Priority.HIGH,
                url=ev.url,
                notes="Email contains an action item or review request.",
                metadata=ev.metadata,
            ))

        return items

    def _from_calendar(self, ev: Event) -> list[ActionItem]:
        items: list[ActionItem] = []
        meta = ev.metadata or {}

        # Meetings starting soon are implicit action items
        if ev.occurred_at:
            now = datetime.now(tz=timezone.utc)
            start = ev.occurred_at
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            # Only flag future meetings
            if start > now:
                items.append(ActionItem(
                    title=f"Attend: {ev.title}",
                    source_id=ev.source_id,
                    source_type=ev.source_type,
                    priority=Priority.MEDIUM,
                    due_at=ev.occurred_at,
                    url=ev.url,
                    notes=f"Location: {meta.get('location', 'N/A')}",
                    metadata=ev.metadata,
                ))

        return items

    def _from_weather(self, ev: Event) -> list[ActionItem]:
        """Weather events only produce actions for severe conditions."""
        items: list[ActionItem] = []
        combined = _title_lower(ev) + " " + _summary_lower(ev)
        severe_kw = {"storm", "warning", "alert", "severe", "tornado", "hurricane", "flood"}
        if _has_keyword(combined, severe_kw):
            items.append(ActionItem(
                title=f"Weather alert: {ev.title}",
                source_id=ev.source_id,
                source_type=ev.source_type,
                priority=Priority.URGENT,
                notes="Severe weather condition detected.",
                metadata=ev.metadata,
            ))
        return items

    def _from_generic(self, ev: Event) -> list[ActionItem]:
        """Generic extractor -- only fires for clear action signals."""
        items: list[ActionItem] = []
        combined = _title_lower(ev) + " " + _summary_lower(ev)
        if _has_keyword(combined, _TODO_KEYWORDS | _DEADLINE_KEYWORDS):
            items.append(ActionItem(
                title=f"Action: {ev.title}",
                source_id=ev.source_id,
                source_type=ev.source_type,
                priority=Priority.MEDIUM,
                url=ev.url,
                notes="Detected action keywords.",
                metadata=ev.metadata,
            ))
        return items
