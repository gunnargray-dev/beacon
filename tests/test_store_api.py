from __future__ import annotations

from src.store import BeaconStore


def test_store_query_events_supports_since_until(tmp_path):
    store = BeaconStore(db_path=tmp_path / "beacon.db")
    store.init_db()

    # empty store should return empty list and not error
    out = store.query_events(limit=10)
    assert out == []


def test_store_query_action_items_supports_completed_filter(tmp_path):
    store = BeaconStore(db_path=tmp_path / "beacon.db")
    store.init_db()

    out = store.query_action_items(completed=False, limit=10)
    assert out == []
