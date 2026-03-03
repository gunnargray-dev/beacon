"""Notification rules engine for Beacon.

Rules are defined in beacon.toml under [notifications.rules] and matched
against Events and ActionItems to decide whether to notify, digest, or silence.

Example TOML:
    [[notifications.rules]]
    name = "urgent-github"
    source_type = "github"
    item_type = "action"
    priority_min = "high"
    action = "notify"

    [[notifications.rules]]
    name = "calendar-digest"
    source_type = "calendar"
    action = "digest"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Priority ordering for comparison
_PRIORITY_ORDER = {"low": 0, "medium": 1, "high": 2, "urgent": 3}


@dataclass
class Rule:
    """A single notification rule with a condition and an action.

    Condition fields (all optional — omit to match any value):
        source_type: Match events/actions from this source type (e.g. "github").
        item_type:   "event", "action", or None (matches both).
        priority_min: Minimum priority level for ActionItems ("low"/"medium"/"high"/"urgent").

    Action field:
        action: "notify" | "digest" | "silence"
    """

    action: str  # "notify" | "digest" | "silence"
    name: str = ""
    source_type: str | None = None
    item_type: str | None = None  # "event" | "action" | None
    priority_min: str | None = None

    def matches_event(self, event: dict[str, Any]) -> bool:
        """Return True if this rule applies to the given event dict."""
        if self.item_type not in (None, "event"):
            return False
        if self.source_type is not None:
            if event.get("source_type", "") != self.source_type:
                return False
        # priority_min does not apply to events
        return True

    def matches_action(self, action_item: dict[str, Any]) -> bool:
        """Return True if this rule applies to the given action_item dict."""
        if self.item_type not in (None, "action"):
            return False
        if self.source_type is not None:
            if action_item.get("source_type", "") != self.source_type:
                return False
        if self.priority_min is not None:
            item_priority = action_item.get("priority", "low")
            min_rank = _PRIORITY_ORDER.get(self.priority_min, 0)
            item_rank = _PRIORITY_ORDER.get(item_priority, 0)
            if item_rank < min_rank:
                return False
        return True


@dataclass
class MatchedNotification:
    """The result of a rule match — carries item + action to take."""

    item: dict[str, Any]
    item_type: str  # "event" | "action"
    action: str  # "notify" | "digest" | "silence"
    rule_name: str = ""


class RuleEngine:
    """Matches a list of rules against Events and ActionItems.

    Usage:
        engine = RuleEngine(rules)
        notifications = engine.evaluate(events, action_items)
    """

    def __init__(self, rules: list[Rule]) -> None:
        self.rules = rules

    def evaluate(
        self,
        events: list[dict[str, Any]],
        action_items: list[dict[str, Any]],
    ) -> list[MatchedNotification]:
        """Evaluate all items against all rules.

        Each item is matched against rules in order; the *first* matching rule
        wins (short-circuit).  Items with no matching rule are skipped.
        """
        results: list[MatchedNotification] = []

        for event in events:
            for rule in self.rules:
                if rule.matches_event(event):
                    results.append(
                        MatchedNotification(
                            item=event,
                            item_type="event",
                            action=rule.action,
                            rule_name=rule.name,
                        )
                    )
                    break

        for ai in action_items:
            for rule in self.rules:
                if rule.matches_action(ai):
                    results.append(
                        MatchedNotification(
                            item=ai,
                            item_type="action",
                            action=rule.action,
                            rule_name=rule.name,
                        )
                    )
                    break

        return results

    def notify_items(
        self,
        events: list[dict[str, Any]],
        action_items: list[dict[str, Any]],
    ) -> list[MatchedNotification]:
        """Return only items matched with action == 'notify'."""
        return [n for n in self.evaluate(events, action_items) if n.action == "notify"]

    def digest_items(
        self,
        events: list[dict[str, Any]],
        action_items: list[dict[str, Any]],
    ) -> list[MatchedNotification]:
        """Return only items matched with action == 'digest'."""
        return [n for n in self.evaluate(events, action_items) if n.action == "digest"]

    def silenced_items(
        self,
        events: list[dict[str, Any]],
        action_items: list[dict[str, Any]],
    ) -> list[MatchedNotification]:
        """Return only items matched with action == 'silence'."""
        return [n for n in self.evaluate(events, action_items) if n.action == "silence"]


def load_rules_from_config(raw_config: dict[str, Any]) -> list[Rule]:
    """Parse rules from a beacon.toml raw dict.

    Reads ``raw_config["notifications"]["rules"]`` (list of dicts).
    Returns an empty list if the section is absent.
    """
    notifications = raw_config.get("notifications", {})
    raw_rules = notifications.get("rules", [])
    rules: list[Rule] = []
    for r in raw_rules:
        action = r.get("action", "notify")
        rule = Rule(
            name=r.get("name", ""),
            source_type=r.get("source_type") or None,
            item_type=r.get("item_type") or None,
            priority_min=r.get("priority_min") or None,
            action=action,
        )
        rules.append(rule)
    return rules
