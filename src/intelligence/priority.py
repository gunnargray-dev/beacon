"""Priority scorer -- rank action items by urgency, sender importance, deadline proximity."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

from src.models import ActionItem, Priority


# ---------------------------------------------------------------------------
# Scoring weights (higher = more important)
# ---------------------------------------------------------------------------

_PRIORITY_WEIGHT: dict[Priority, float] = {
    Priority.URGENT: 100.0,
    Priority.HIGH: 70.0,
    Priority.MEDIUM: 40.0,
    Priority.LOW: 10.0,
}

_IMPORTANT_SENDERS: set[str] = set()  # populated via configure()


class PriorityScorer:
    """Score and rank action items by composite urgency.

    The composite score considers:
      - Base priority weight (urgent > high > medium > low)
      - Deadline proximity (closer = higher score)
      - Sender / source importance (configurable)
      - Overdue penalty (overdue items get a boost)

    Usage::

        scorer = PriorityScorer()
        scorer.configure(important_senders={"ceo@company.com", "manager@company.com"})
        ranked = scorer.rank(action_items)
        score  = scorer.score(single_item)
    """

    def __init__(self) -> None:
        self._important_senders: set[str] = set()
        self._deadline_weight: float = 50.0
        self._sender_bonus: float = 25.0
        self._overdue_bonus: float = 30.0

    def configure(
        self,
        important_senders: set[str] | None = None,
        deadline_weight: float | None = None,
        sender_bonus: float | None = None,
        overdue_bonus: float | None = None,
    ) -> None:
        """Update scoring parameters."""
        if important_senders is not None:
            self._important_senders = {s.lower() for s in important_senders}
        if deadline_weight is not None:
            self._deadline_weight = deadline_weight
        if sender_bonus is not None:
            self._sender_bonus = sender_bonus
        if overdue_bonus is not None:
            self._overdue_bonus = overdue_bonus

    def score(self, item: ActionItem) -> float:
        """Compute a composite priority score for a single action item.

        Returns a float (higher = more urgent). Typical range 0-200.
        """
        total = _PRIORITY_WEIGHT.get(item.priority, 40.0)

        # Deadline proximity bonus
        if item.due_at is not None:
            total += self._deadline_score(item.due_at)

        # Overdue bonus -- safe comparison handling naive/aware mismatch
        if item.due_at is not None and not item.completed:
            due = item.due_at
            now = datetime.now(tz=timezone.utc)
            if due.tzinfo is None:
                due = due.replace(tzinfo=timezone.utc)
            if now > due:
                total += self._overdue_bonus

        # Sender importance bonus
        total += self._sender_score(item)

        return round(total, 2)

    def rank(self, items: list[ActionItem]) -> list[tuple[ActionItem, float]]:
        """Score and sort action items, highest first.

        Returns a list of (action_item, score) tuples.
        """
        scored = [(item, self.score(item)) for item in items]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def top_n(self, items: list[ActionItem], n: int = 3) -> list[ActionItem]:
        """Return the top *n* highest-priority action items."""
        ranked = self.rank(items)
        return [item for item, _ in ranked[:n]]

    # ------------------------------------------------------------------
    # Internal scoring helpers
    # ------------------------------------------------------------------

    def _deadline_score(self, due_at: datetime) -> float:
        """Compute a deadline proximity score.

        Closer deadlines receive higher scores. Past-due items get maximum score.
        """
        now = datetime.now(tz=timezone.utc)
        due = due_at
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)

        delta = (due - now).total_seconds()
        if delta <= 0:
            return self._deadline_weight  # already past due

        hours_until = delta / 3600.0
        if hours_until <= 1:
            return self._deadline_weight * 0.95
        if hours_until <= 4:
            return self._deadline_weight * 0.8
        if hours_until <= 24:
            return self._deadline_weight * 0.5
        if hours_until <= 72:
            return self._deadline_weight * 0.25

        # Beyond 72 hours, decay logarithmically
        return max(0.0, self._deadline_weight * (1.0 - math.log10(hours_until / 24.0) * 0.3))

    def _sender_score(self, item: ActionItem) -> float:
        """Check if the item originates from an important sender."""
        if not self._important_senders:
            return 0.0

        meta = item.metadata or {}
        sender = str(meta.get("sender", "")).lower()
        author = str(meta.get("author", "")).lower()

        for candidate in (sender, author):
            if candidate and candidate in self._important_senders:
                return self._sender_bonus

        return 0.0
