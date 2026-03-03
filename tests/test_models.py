"""Tests for core Beacon data models."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.models import (
    ActionItem,
    Briefing,
    Event,
    Priority,
    Source,
    SourceType,
    SyncStatus,
    User,
)


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------


class TestUser:
    def test_create_basic(self):
        user = User(name="Alice", email="alice@example.com")
        assert user.name == "Alice"
        assert user.email == "alice@example.com"
        assert user.timezone == "UTC"

    def test_create_with_timezone(self):
        user = User(name="Bob", email="bob@example.com", timezone="America/New_York")
        assert user.timezone == "America/New_York"

    def test_id_auto_generated(self):
        u1 = User(name="A", email="a@a.com")
        u2 = User(name="B", email="b@b.com")
        assert u1.id != u2.id

    def test_created_at_auto_set(self):
        before = datetime.utcnow()
        user = User(name="C", email="c@c.com")
        after = datetime.utcnow()
        assert before <= user.created_at <= after

    def test_repr(self):
        user = User(name="Dana", email="dana@example.com")
        assert "Dana" in repr(user)
        assert "dana@example.com" in repr(user)


# ---------------------------------------------------------------------------
# Source
# ---------------------------------------------------------------------------


class TestSource:
    def test_create_defaults(self):
        src = Source(name="gh", source_type=SourceType.GITHUB)
        assert src.enabled is True
        assert src.sync_status == SyncStatus.PENDING
        assert src.last_synced_at is None
        assert src.error_message is None
        assert src.config == {}

    def test_mark_synced(self):
        src = Source(name="gh", source_type=SourceType.GITHUB)
        before = datetime.utcnow()
        src.mark_synced()
        after = datetime.utcnow()
        assert src.sync_status == SyncStatus.OK
        assert before <= src.last_synced_at <= after
        assert src.error_message is None

    def test_mark_error(self):
        src = Source(name="gh", source_type=SourceType.GITHUB)
        src.mark_error("rate limit exceeded")
        assert src.sync_status == SyncStatus.ERROR
        assert src.error_message == "rate limit exceeded"

    def test_mark_synced_clears_error(self):
        src = Source(name="gh", source_type=SourceType.GITHUB)
        src.mark_error("oops")
        src.mark_synced()
        assert src.sync_status == SyncStatus.OK
        assert src.error_message is None

    def test_is_healthy_enabled_ok(self):
        src = Source(name="gh", source_type=SourceType.GITHUB)
        src.mark_synced()
        assert src.is_healthy() is True

    def test_is_healthy_enabled_pending(self):
        src = Source(name="gh", source_type=SourceType.GITHUB)
        assert src.is_healthy() is True  # PENDING is healthy

    def test_is_healthy_disabled(self):
        src = Source(name="gh", source_type=SourceType.GITHUB, enabled=False)
        assert src.is_healthy() is False

    def test_is_healthy_error(self):
        src = Source(name="gh", source_type=SourceType.GITHUB)
        src.mark_error("boom")
        assert src.is_healthy() is False

    def test_unique_ids(self):
        s1 = Source(name="a", source_type=SourceType.GITHUB)
        s2 = Source(name="b", source_type=SourceType.GITHUB)
        assert s1.id != s2.id

    def test_repr(self):
        src = Source(name="gh", source_type=SourceType.GITHUB)
        assert "gh" in repr(src)
        assert "github" in repr(src)


# ---------------------------------------------------------------------------
# Event
# ---------------------------------------------------------------------------


class TestEvent:
    def test_create(self):
        now = datetime.utcnow()
        ev = Event(
            title="PR opened",
            source_id="src-1",
            source_type=SourceType.GITHUB,
            occurred_at=now,
        )
        assert ev.title == "PR opened"
        assert ev.summary == ""
        assert ev.url == ""
        assert ev.metadata == {}

    def test_id_auto(self):
        now = datetime.utcnow()
        e1 = Event(title="a", source_id="s", source_type=SourceType.GITHUB, occurred_at=now)
        e2 = Event(title="b", source_id="s", source_type=SourceType.GITHUB, occurred_at=now)
        assert e1.id != e2.id

    def test_repr(self):
        now = datetime.utcnow()
        ev = Event(title="Meeting", source_id="s", source_type=SourceType.CALENDAR, occurred_at=now)
        assert "Meeting" in repr(ev)
        assert "calendar" in repr(ev)


# ---------------------------------------------------------------------------
# ActionItem
# ---------------------------------------------------------------------------


class TestActionItem:
    def test_create_defaults(self):
        item = ActionItem(title="Review PR", source_id="s", source_type=SourceType.GITHUB)
        assert item.priority == Priority.MEDIUM
        assert item.completed is False
        assert item.due_at is None
        assert item.notes == ""

    def test_complete(self):
        item = ActionItem(title="Review PR", source_id="s", source_type=SourceType.GITHUB)
        item.complete()
        assert item.completed is True

    def test_is_overdue_no_due_date(self):
        item = ActionItem(title="t", source_id="s", source_type=SourceType.GITHUB)
        assert item.is_overdue() is False

    def test_is_overdue_future(self):
        item = ActionItem(
            title="t",
            source_id="s",
            source_type=SourceType.GITHUB,
            due_at=datetime.utcnow() + timedelta(hours=1),
        )
        assert item.is_overdue() is False

    def test_is_overdue_past(self):
        item = ActionItem(
            title="t",
            source_id="s",
            source_type=SourceType.GITHUB,
            due_at=datetime.utcnow() - timedelta(hours=1),
        )
        assert item.is_overdue() is True

    def test_is_overdue_completed_not_overdue(self):
        item = ActionItem(
            title="t",
            source_id="s",
            source_type=SourceType.GITHUB,
            due_at=datetime.utcnow() - timedelta(hours=1),
        )
        item.complete()
        assert item.is_overdue() is False

    def test_repr(self):
        item = ActionItem(title="Fix bug", source_id="s", source_type=SourceType.GITHUB)
        assert "Fix bug" in repr(item)
        assert "medium" in repr(item)


# ---------------------------------------------------------------------------
# Briefing
# ---------------------------------------------------------------------------


class TestBriefing:
    def _make_event(self, title: str) -> Event:
        return Event(
            title=title,
            source_id="s",
            source_type=SourceType.GITHUB,
            occurred_at=datetime.utcnow(),
        )

    def _make_action(self, title: str, priority: Priority = Priority.MEDIUM) -> ActionItem:
        return ActionItem(title=title, source_id="s", source_type=SourceType.GITHUB, priority=priority)

    def test_create_empty(self):
        b = Briefing(date=datetime.utcnow())
        assert b.events == []
        assert b.action_items == []
        assert b.summary == ""

    def test_add_event(self):
        b = Briefing(date=datetime.utcnow())
        ev = self._make_event("Meeting")
        b.add_event(ev)
        assert len(b.events) == 1
        assert b.events[0].title == "Meeting"

    def test_add_action_item(self):
        b = Briefing(date=datetime.utcnow())
        item = self._make_action("Review PR")
        b.add_action_item(item)
        assert len(b.action_items) == 1

    def test_pending_actions(self):
        b = Briefing(date=datetime.utcnow())
        a1 = self._make_action("A")
        a2 = self._make_action("B")
        a2.complete()
        b.add_action_item(a1)
        b.add_action_item(a2)
        pending = b.pending_actions()
        assert len(pending) == 1
        assert pending[0].title == "A"

    def test_urgent_actions(self):
        b = Briefing(date=datetime.utcnow())
        b.add_action_item(self._make_action("normal", Priority.MEDIUM))
        b.add_action_item(self._make_action("urgent", Priority.URGENT))
        urgent = b.urgent_actions()
        assert len(urgent) == 1
        assert urgent[0].title == "urgent"

    def test_urgent_actions_excludes_completed(self):
        b = Briefing(date=datetime.utcnow())
        item = self._make_action("done", Priority.URGENT)
        item.complete()
        b.add_action_item(item)
        assert b.urgent_actions() == []

    def test_repr(self):
        b = Briefing(date=datetime.utcnow())
        r = repr(b)
        assert "events=0" in r
        assert "action_items=0" in r
