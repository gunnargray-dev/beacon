from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from src.models import ActionItem, Event, Priority, SourceType
from src.shell import ShellError, execute_shell_command
from src.store import BeaconStore


def _mk_store(tmp_path):
    db = tmp_path / "beacon.db"
    store = BeaconStore(db)
    store.init_db()
    return store


def test_shell_help_returns_text(tmp_path):
    store = _mk_store(tmp_path)
    res = execute_shell_command("help", store=store)
    assert res.rows
    assert "Commands" in res.rows[0]["help"]


def test_shell_exit_sets_exit_flag(tmp_path):
    store = _mk_store(tmp_path)
    res = execute_shell_command("exit", store=store)
    assert res.rows[0]["exit"] is True


def test_shell_events_query_and_cursor(tmp_path):
    store = _mk_store(tmp_path)

    now = datetime(2026, 3, 4, 12, 0, tzinfo=timezone.utc)
    ev1 = Event(
        id="e1",
        title="First",
        source_id="gh",
        source_type=SourceType.GITHUB,
        occurred_at=now,
        summary="",
        url="",
        metadata={},
        created_at=now,
    )
    ev2 = Event(
        id="e2",
        title="Second",
        source_id="gh",
        source_type=SourceType.GITHUB,
        occurred_at=now,
        summary="",
        url="",
        metadata={},
        created_at=now,
    )
    store.upsert_events([ev1, ev2])

    res = execute_shell_command("events limit=1", store=store)
    assert len(res.rows) == 1
    assert res.next_cursor

    res2 = execute_shell_command(f"events limit=10 cursor={res.next_cursor}", store=store)
    assert len(res2.rows) >= 1


def test_shell_actions_filters_and_json(tmp_path):
    store = _mk_store(tmp_path)

    now = datetime(2026, 3, 4, 12, 0, tzinfo=timezone.utc)
    a1 = ActionItem(
        id="a1",
        title="Urgent thing",
        source_id="gh",
        source_type=SourceType.GITHUB,
        priority=Priority.URGENT,
        due_at=now,
        url="",
        completed=False,
        notes="",
        metadata={},
        created_at=now,
    )
    a2 = ActionItem(
        id="a2",
        title="Done thing",
        source_id="gh",
        source_type=SourceType.GITHUB,
        priority=Priority.LOW,
        due_at=None,
        url="",
        completed=True,
        notes="",
        metadata={},
        created_at=now,
    )
    store.upsert_action_items([a1, a2])

    res = execute_shell_command("actions completed=false limit=10", store=store)
    assert len(res.rows) == 1
    assert res.rows[0]["id"] == "a1"

    payload = json.loads(res.as_json())
    assert "rows" in payload


def test_shell_rejects_invalid_tokens(tmp_path):
    store = _mk_store(tmp_path)
    with pytest.raises(ShellError):
        execute_shell_command("events bogus", store=store)
