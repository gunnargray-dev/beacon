from __future__ import annotations

import json
from datetime import datetime, timezone

from src.models import ActionItem, Event, Priority, SourceType
from src.store import BeaconStore


def test_store_upsert_and_query_events(tmp_path):
    db = tmp_path / "beacon.db"
    store = BeaconStore(db)

    e1 = Event(
        id="e1",
        title="Test event",
        source_id="GitHub",
        source_type=SourceType.GITHUB,
        occurred_at=datetime(2026, 3, 3, 12, 0, tzinfo=timezone.utc),
        summary="hello",
        url="https://example.com",
        metadata={"k": 1},
    )

    changed = store.upsert_events([e1])
    assert changed >= 1

    events = store.query_events(limit=10)
    assert len(events) == 1
    assert events[0].id == "e1"
    assert events[0].source_type == SourceType.GITHUB
    assert events[0].metadata == {"k": 1}

    # Update same id
    e1b = Event(
        id="e1",
        title="Updated",
        source_id="GitHub",
        source_type=SourceType.GITHUB,
        occurred_at=datetime(2026, 3, 3, 13, 0, tzinfo=timezone.utc),
        summary="updated",
        url="",
        metadata={"k": 2},
    )
    store.upsert_events([e1b])

    events2 = store.query_events(limit=10)
    assert len(events2) == 1
    assert events2[0].title == "Updated"
    assert events2[0].metadata == {"k": 2}


def test_store_upsert_and_query_action_items(tmp_path):
    db = tmp_path / "beacon.db"
    store = BeaconStore(db)

    a1 = ActionItem(
        id="a1",
        title="Do thing",
        source_id="Email",
        source_type=SourceType.EMAIL,
        priority=Priority.HIGH,
        due_at=datetime(2026, 3, 5, 9, 0, tzinfo=timezone.utc),
        url="",
        completed=False,
        notes="n",
        metadata={"x": True},
    )

    store.upsert_action_items([a1])

    pending = store.query_action_items(limit=10)
    assert len(pending) == 1
    assert pending[0].priority == Priority.HIGH
    assert pending[0].completed is False

    # Mark completed
    a1b = ActionItem(
        id="a1",
        title="Do thing",
        source_id="Email",
        source_type=SourceType.EMAIL,
        priority=Priority.HIGH,
        due_at=datetime(2026, 3, 5, 9, 0, tzinfo=timezone.utc),
        completed=True,
        notes="done",
        metadata={"x": True},
    )
    store.upsert_action_items([a1b])

    completed = store.query_action_items(completed=True, limit=10)
    assert len(completed) == 1
    assert completed[0].notes == "done"


def test_store_filters(tmp_path):
    db = tmp_path / "beacon.db"
    store = BeaconStore(db)

    now = datetime(2026, 3, 3, 12, 0, tzinfo=timezone.utc)
    store.upsert_events(
        [
            Event(
                id="e1",
                title="A",
                source_id="GitHub",
                source_type=SourceType.GITHUB,
                occurred_at=now,
            ),
            Event(
                id="e2",
                title="B",
                source_id="Calendar",
                source_type=SourceType.CALENDAR,
                occurred_at=now,
            ),
        ]
    )

    gh = store.query_events(source_type="github", limit=10)
    assert len(gh) == 1
    assert gh[0].id == "e1"

    cal = store.query_events(source_name="Calendar", limit=10)
    assert len(cal) == 1
    assert cal[0].id == "e2"
