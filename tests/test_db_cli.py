from __future__ import annotations

from datetime import datetime, timezone

from src.models import ActionItem, Event, Priority, SourceType
from src.store import BeaconStore


def test_beacon_db_missing_db(tmp_path, monkeypatch, capsys):
    from src.db_cli import cmd_db

    missing = tmp_path / "missing.db"
    code = cmd_db(str(missing))
    assert code == 1

    out = capsys.readouterr().out
    assert "DB path:" in out
    assert "DB exists: False" in out


def test_beacon_db_prints_counts(tmp_path, capsys):
    from src.db_cli import cmd_db

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

    code = cmd_db(str(db))
    assert code == 0

    out = capsys.readouterr().out
    assert "DB exists: True" in out
    assert "Events:" in out
    assert "total: 1" in out
    assert "Action items:" in out
    assert "pending: 1" in out

