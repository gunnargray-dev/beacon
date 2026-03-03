from __future__ import annotations

import json
from datetime import datetime, timezone

from src.ingest import ingest_sync_cache
from src.store import BeaconStore


def test_ingest_sync_cache_into_store(tmp_path):
    sync = {
        "synced_at": "2026-03-03T12:00:00+00:00",
        "events": [
            {
                "id": "e1",
                "title": "PR review requested",
                "source_id": "GitHub",
                "source_type": "github",
                "occurred_at": "2026-03-03T11:00:00+00:00",
                "summary": "please review",
                "url": "",
                "metadata": {"n": 1},
                "created_at": "2026-03-03T11:00:00+00:00",
            }
        ],
        "action_items": [
            {
                "id": "a1",
                "title": "Review PR",
                "source_id": "GitHub",
                "source_type": "github",
                "priority": "urgent",
                "due_at": "2026-03-03T18:00:00+00:00",
                "url": "",
                "completed": False,
                "notes": "",
                "metadata": {},
                "created_at": "2026-03-03T11:00:00+00:00",
            }
        ],
    }

    sync_path = tmp_path / "last_sync.json"
    sync_path.write_text(json.dumps(sync), encoding="utf-8")

    db_path = tmp_path / "beacon.db"
    res = ingest_sync_cache(sync_path, db_path=db_path)
    assert res.events_written >= 1
    assert res.actions_written >= 1

    store = BeaconStore(db_path)
    events = store.query_events(limit=10)
    actions = store.query_action_items(limit=10)

    assert len(events) == 1
    assert events[0].id == "e1"
    assert events[0].metadata == {"n": 1}

    assert len(actions) == 1
    assert actions[0].id == "a1"
    assert actions[0].priority.value == "urgent"
