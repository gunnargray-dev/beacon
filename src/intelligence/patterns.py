"""Pattern analyzer -- identify recurring meetings, email response times, commit velocity."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from src.models import Event, SourceType


@dataclass
class Pattern:
    """A detected behavioral pattern."""

    name: str
    category: str  # "meeting" | "email" | "commit" | "activity"
    description: str
    frequency: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return f"Pattern(name={self.name!r}, category={self.category!r}, freq={self.frequency})"


class PatternAnalyzer:
    """Analyze events to detect behavioral patterns.

    Usage::

        analyzer = PatternAnalyzer()
        patterns = analyzer.analyze(events)
        text = analyzer.format_patterns(patterns)
    """

    def analyze(self, events: list[Event]) -> list[Pattern]:
        """Run all pattern detectors and return combined results."""
        patterns: list[Pattern] = []
        patterns.extend(self._recurring_meetings(events))
        patterns.extend(self._source_activity(events))
        patterns.extend(self._peak_hours(events))
        patterns.extend(self._commit_velocity(events))
        return patterns

    # ------------------------------------------------------------------
    # Detectors
    # ------------------------------------------------------------------

    def _recurring_meetings(self, events: list[Event]) -> list[Pattern]:
        """Identify meetings that appear multiple times (by title)."""
        calendar_events = [e for e in events if e.source_type == SourceType.CALENDAR]
        title_counts: Counter[str] = Counter()
        for ev in calendar_events:
            normalized = ev.title.strip().lower()
            if normalized:
                title_counts[normalized] += 1

        patterns: list[Pattern] = []
        for title, count in title_counts.most_common():
            if count >= 2:
                patterns.append(Pattern(
                    name=title.title(),
                    category="meeting",
                    description=f"Recurring meeting appearing {count} time(s).",
                    frequency=count,
                    metadata={"raw_title": title},
                ))

        return patterns

    def _source_activity(self, events: list[Event]) -> list[Pattern]:
        """Count events per source type to identify dominant sources."""
        counts: Counter[str] = Counter()
        for ev in events:
            counts[ev.source_type.value] += 1

        patterns: list[Pattern] = []
        for source, count in counts.most_common():
            patterns.append(Pattern(
                name=f"{source} activity",
                category="activity",
                description=f"{count} event(s) from {source}.",
                frequency=count,
                metadata={"source_type": source},
            ))

        return patterns

    def _peak_hours(self, events: list[Event]) -> list[Pattern]:
        """Identify the busiest hours of the day."""
        hour_counts: Counter[int] = Counter()
        for ev in events:
            if ev.occurred_at:
                hour_counts[ev.occurred_at.hour] += 1

        if not hour_counts:
            return []

        top_hour, top_count = hour_counts.most_common(1)[0]
        if top_count < 2:
            return []

        return [Pattern(
            name=f"Peak hour: {top_hour:02d}:00",
            category="activity",
            description=f"Most active hour with {top_count} event(s).",
            frequency=top_count,
            metadata={"hour": top_hour},
        )]

    def _commit_velocity(self, events: list[Event]) -> list[Pattern]:
        """Analyze GitHub commit frequency."""
        github_events = [
            e for e in events
            if e.source_type == SourceType.GITHUB
        ]
        if not github_events:
            return []

        # Group by day
        day_counts: Counter[str] = Counter()
        for ev in github_events:
            if ev.occurred_at:
                day_counts[ev.occurred_at.strftime("%Y-%m-%d")] += 1

        if not day_counts:
            return []

        total = sum(day_counts.values())
        days = len(day_counts)
        avg = total / days if days else 0

        return [Pattern(
            name="GitHub velocity",
            category="commit",
            description=f"{total} GitHub event(s) across {days} day(s) (avg {avg:.1f}/day).",
            frequency=total,
            metadata={"total": total, "days": days, "avg_per_day": round(avg, 1)},
        )]

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    @staticmethod
    def format_patterns(patterns: list[Pattern]) -> str:
        """Render patterns as a human-readable text block."""
        if not patterns:
            return "No patterns detected yet. Sync more data for analysis."

        lines: list[str] = [f"Detected {len(patterns)} pattern(s):"]
        lines.append("")
        for p in patterns:
            lines.append(f"  [{p.category:<10}] {p.name} -- {p.description}")
        return "\n".join(lines)
