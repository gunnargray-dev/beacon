from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from src.models import ActionItem, Event, Priority, SourceType
from src.store import BeaconStore
from src.web.server import create_app


def test_store_stats_missing_db(tmp_path, monkeypatch):
    monkeypatch.setenv("BEACON_DB", str(tmp_path / "missing.db"))
    app = create_app()
    client = TestClient(app)

    resp = client.get("/api/store/stats")
    assert resp.status_code == 404


def test_store_stats_counts(tmp_path, monkeypatch):
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
            )
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
            )
        ]
    )

    monkeypatch.setenv("BEACON_DB", str(db))

    app = create_app()
    client = TestClient(app)

    resp = client.get("/api/store/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["events"]["total"] == 1
    assert data["action_items"]["total"] == 1
    assert data["action_items"]["pending"] == 1
    assert data["action_items"]["completed"] == 0
    assert data["events"]["by_source_type"]["github"] == 1
    assert data["action_items"]["by_source_type"]["github"] == 1
