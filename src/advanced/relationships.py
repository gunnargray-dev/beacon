"""Relationship tracker.

Analyses the sync cache to surface who the user interacts with most,
how frequently, response patterns, and which contacts have gone quiet.

Usage::

    from src.advanced.relationships import RelationshipTracker
    tracker = RelationshipTracker(cache)
    report = tracker.report()
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


def _extract_contacts(event: dict[str, Any]) -> list[str]:
    """Extract person names / email addresses from an event."""
    contacts: list[str] = []
    meta = event.get("metadata", {})

    for key in ("from", "sender", "author", "assignee", "attendees", "participants", "reviewer", "reviewers"):
        val = meta.get(key)
        if isinstance(val, str) and val:
            contacts.append(val)
        elif isinstance(val, list):
            for item in val:
                if isinstance(item, str) and item:
                    contacts.append(item)
                elif isinstance(item, dict):
                    name = item.get("name") or item.get("email") or item.get("login", "")
                    if name:
                        contacts.append(name)

    return contacts


class RelationshipTracker:
    """Build and query a relationship map from a sync cache."""

    def __init__(
        self,
        cache: dict[str, Any],
        ref_dt: datetime | None = None,
        dormant_days: int = 30,
    ) -> None:
        self._ref_dt = ref_dt or datetime.now(tz=timezone.utc)
        self._dormant_days = dormant_days
        self._events: list[dict[str, Any]] = cache.get("events", [])
        self._contact_events: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._build()

    # ── internal ────────────────────────────────────────────────────────────

    def _build(self) -> None:
        for ev in self._events:
            for contact in _extract_contacts(ev):
                self._contact_events[contact].append(ev)

    # ── public ──────────────────────────────────────────────────────────────

    def interaction_counts(self) -> list[tuple[str, int]]:
        """Return (contact, count) pairs sorted by interaction count descending."""
        return sorted(
            ((c, len(evs)) for c, evs in self._contact_events.items()),
            key=lambda x: x[1],
            reverse=True,
        )

    def last_interaction(self, contact: str) -> datetime | None:
        evs = self._contact_events.get(contact, [])
        dts = [
            _parse_dt(ev.get("occurred_at") or ev.get("created_at"))
            for ev in evs
        ]
        valid = [d for d in dts if d is not None]
        return max(valid) if valid else None

    def dormant_contacts(self) -> list[dict[str, Any]]:
        """Contacts not seen in the last *dormant_days* days."""
        cutoff = self._ref_dt - timedelta(days=self._dormant_days)
        dormant = []
        for contact in self._contact_events:
            last = self.last_interaction(contact)
            if last and last < cutoff:
                days_since = (self._ref_dt - last).days
                dormant.append(
                    {
                        "contact": contact,
                        "last_seen": last.isoformat(),
                        "days_since": days_since,
                        "total_interactions": len(self._contact_events[contact]),
                    }
                )
        return sorted(dormant, key=lambda x: x["days_since"], reverse=True)

    def source_breakdown(self, contact: str) -> dict[str, int]:
        """Count interactions per source_type for a given contact."""
        return dict(
            Counter(
                ev.get("source_type", "custom")
                for ev in self._contact_events.get(contact, [])
            )
        )

    def top_contacts(self, n: int = 10) -> list[dict[str, Any]]:
        """Return the top *n* contacts with full detail."""
        result = []
        for contact, count in self.interaction_counts()[:n]:
            last = self.last_interaction(contact)
            result.append(
                {
                    "contact": contact,
                    "total_interactions": count,
                    "last_interaction": last.isoformat() if last else None,
                    "by_source": self.source_breakdown(contact),
                }
            )
        return result

    def report(self) -> dict[str, Any]:
        """Return a full relationship report."""
        return {
            "total_contacts": len(self._contact_events),
            "top_contacts": self.top_contacts(10),
            "dormant_contacts": self.dormant_contacts()[:10],
            "generated_at": self._ref_dt.isoformat(),
        }
