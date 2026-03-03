from __future__ import annotations

import base64
import json

import pytest

from src.store import BeaconStore


def _event_cursor(*, occurred_at: str, created_at: str, item_id: str) -> str:
    raw = json.dumps({"occurred_at": occurred_at, "created_at": created_at, "id": item_id}).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def test_store_events_pagination_cursor(tmp_path) -> None:
    db = tmp_path / "beacon.db"
    store = BeaconStore(db_path=db)
    store.init_db()
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO events (id, title, source_id, source_type, occurred_at, summary, url, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("e1", "Event 1", "s", "github", "2026-03-03T10:00:00+00:00", "", "", "{}", "2026-03-03T10:00:01+00:00"),
        )
        conn.execute(
            "INSERT INTO events (id, title, source_id, source_type, occurred_at, summary, url, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("e2", "Event 2", "s", "github", "2026-03-03T09:00:00+00:00", "", "", "{}", "2026-03-03T09:00:01+00:00"),
        )
        conn.execute(
            "INSERT INTO events (id, title, source_id, source_type, occurred_at, summary, url, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("e3", "Event 3", "s", "github", "2026-03-03T08:00:00+00:00", "", "", "{}", "2026-03-03T08:00:01+00:00"),
        )

    first = store.query_events(limit=2, sort="occurred_at_desc")
    assert [e.id for e in first] == ["e1", "e2"]

    cur = _event_cursor(
        occurred_at="2026-03-03T09:00:00+00:00",
        created_at="2026-03-03T09:00:01+00:00",
        item_id="e2",
    )
    second = store.query_events(limit=10, sort="occurred_at_desc", cursor=cur)
    assert [e.id for e in second] == ["e3"]


@pytest.mark.parametrize("sort", ["occurred_at_desc", "occurred_at_asc"])
def test_store_events_sort_validation_allows_known(sort: str, tmp_path) -> None:
    store = BeaconStore(db_path=tmp_path / "beacon.db")
    store.init_db()
    store.query_events(limit=1, sort=sort)


def test_store_events_sort_validation_rejects_unknown(tmp_path) -> None:
    store = BeaconStore(db_path=tmp_path / "beacon.db")
    store.init_db()
    with pytest.raises(ValueError):
        store.query_events(limit=1, sort="wat")
