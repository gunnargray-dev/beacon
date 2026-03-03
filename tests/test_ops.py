from __future__ import annotations

from datetime import datetime, timezone

from src.ops import compute_store_stats
from src.store import BeaconStore

from src.models import ActionItem, Event, Priority, SourceType


def test_compute_store_stats_counts(tmp_path):
    db = tmp_path / "beacon.db"
    store = BeaconStore(db)

    store.upsert_events(
        [
            Event(
                id="e1",
                title="t",
                source_id="s1",
                source_type=SourceType.GITHUB,
                occurred_at=datetime(2026, 3, 3, tzinfo=timezone.utc),
            ),
            Event(
                id="e2",
                title="t2",
                source_id="s1",
                source_type=SourceType.EMAIL,
                occurred_at=datetime(2026, 3, 3, tzinfo=timezone.utc),
            ),
        ]
    )

    store.upsert_action_items(
        [
            ActionItem(
                id="a1",
                title="x",
                source_id="s1",
                source_type=SourceType.GITHUB,
                priority=Priority.HIGH,
                created_at=datetime(2026, 3, 3, tzinfo=timezone.utc),
                completed=False,
            ),
            ActionItem(
                id="a2",
                title="y",
                source_id="s1",
                source_type=SourceType.GITHUB,
                priority=Priority.MEDIUM,
                created_at=datetime(2026, 3, 3, tzinfo=timezone.utc),
                completed=True,
            ),
        ]
    )

    stats = compute_store_stats(store)

    assert stats.total_events == 2
    assert stats.total_action_items == 2
    assert stats.completed_action_items == 1
    assert stats.pending_action_items == 1
    assert stats.events_by_source_type["github"] == 1
    assert stats.events_by_source_type["email"] == 1
    assert stats.action_items_by_source_type["github"] == 2
