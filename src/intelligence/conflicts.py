"""Conflict detector -- flag calendar overlaps, double-booked slots."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.models import Event, SourceType


@dataclass
class Conflict:
    """A pair of overlapping events."""

    event_a: Event
    event_b: Event
    overlap_minutes: float = 0.0
    severity: str = "warning"  # "warning" | "critical"

    def __repr__(self) -> str:
        return (
            f"Conflict({self.event_a.title!r} <-> {self.event_b.title!r}, "
            f"overlap={self.overlap_minutes:.0f}m, severity={self.severity!r})"
        )


def _get_start_end(ev: Event) -> tuple[datetime, datetime] | None:
    """Extract start and end times from an event.

    End time is derived from metadata['end'] if present, otherwise returns None.
    """
    start = ev.occurred_at
    if start is None:
        return None

    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)

    meta = ev.metadata or {}
    end_str = meta.get("end", "")
    end: datetime | None = None
    if end_str:
        try:
            end = datetime.fromisoformat(end_str)
        except (ValueError, TypeError):
            end = None

    if end is None:
        return None

    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    return start, end


class ConflictDetector:
    """Detect scheduling conflicts among calendar events.

    Usage::

        detector = ConflictDetector()
        conflicts = detector.detect(events)
        text = detector.format_conflicts(conflicts)
    """

    def __init__(self, min_overlap_minutes: float = 1.0) -> None:
        self._min_overlap = min_overlap_minutes

    def detect(self, events: list[Event]) -> list[Conflict]:
        """Find all pairs of overlapping events.

        Only considers CALENDAR events with valid start and end times.
        """
        # Filter to calendar events with valid time ranges
        timed: list[tuple[datetime, datetime, Event]] = []
        for ev in events:
            if ev.source_type != SourceType.CALENDAR:
                continue
            times = _get_start_end(ev)
            if times is None:
                continue
            timed.append((times[0], times[1], ev))

        # Sort by start time
        timed.sort(key=lambda t: t[0])

        conflicts: list[Conflict] = []
        for i, (s1, e1, ev1) in enumerate(timed):
            for s2, e2, ev2 in timed[i + 1:]:
                if s2 >= e1:
                    break  # no more overlaps possible (sorted)
                # Overlap exists: s1 < e2 and s2 < e1
                overlap_start = max(s1, s2)
                overlap_end = min(e1, e2)
                overlap_minutes = (overlap_end - overlap_start).total_seconds() / 60.0

                if overlap_minutes < self._min_overlap:
                    continue

                severity = "critical" if overlap_minutes >= 30 else "warning"
                conflicts.append(Conflict(
                    event_a=ev1,
                    event_b=ev2,
                    overlap_minutes=round(overlap_minutes, 1),
                    severity=severity,
                ))

        return conflicts

    @staticmethod
    def format_conflicts(conflicts: list[Conflict]) -> str:
        """Render conflicts as a human-readable text block."""
        if not conflicts:
            return "No scheduling conflicts detected."

        lines: list[str] = [f"Found {len(conflicts)} scheduling conflict(s):"]
        lines.append("")
        for i, c in enumerate(conflicts, 1):
            icon = "!!" if c.severity == "critical" else " !"
            lines.append(
                f"  [{icon}] {c.event_a.title} <-> {c.event_b.title} "
                f"({c.overlap_minutes:.0f} min overlap)"
            )
        return "\n".join(lines)
