import json

from src.models import ActionItem, Event, Priority, SourceType
from src.store import BeaconStore


def test_store_init_runs_migrations_and_sets_user_version(tmp_path):
    db_path = tmp_path / "store.db"
    store = BeaconStore(db_path)

    # init_db should run migrations.
    store.init_db()

    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("PRAGMA user_version").fetchone()
        assert row is not None
        assert int(row[0]) == BeaconStore.LATEST_SCHEMA_VERSION

        # Tables exist.
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "events" in tables
        assert "action_items" in tables
    finally:
        conn.close()


def test_store_upsert_still_works_with_migrations(tmp_path):
    db_path = tmp_path / "store.db"
    store = BeaconStore(db_path)

    e = Event(
        id="e1",
        title="Test",
        source_id="github",
        source_type=SourceType.GITHUB,
        occurred_at=None,  # store should fill
        summary="",
        url="",
        metadata={"x": 1},
        created_at=None,
    )

    a = ActionItem(
        id="a1",
        title="Do thing",
        source_id="github",
        source_type=SourceType.GITHUB,
        priority=Priority.HIGH,
        due_at=None,
        url="",
        completed=False,
        notes="",
        metadata={"y": 2},
        created_at=None,
    )

    assert store.upsert_events([e]) >= 1
    assert store.upsert_action_items([a]) >= 1

    # Query returns stored metadata.
    evs = store.query_events(limit=10)
    assert len(evs) == 1
    assert json.loads(json.dumps(evs[0].metadata)) == {"x": 1}

    items = store.query_action_items(limit=10)
    assert len(items) == 1
    assert json.loads(json.dumps(items[0].metadata)) == {"y": 2}
