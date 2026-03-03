"""Data loading helpers for the Beacon web dashboard.

The web UI can render from either:
1) the persistent SQLite store (preferred), or
2) the last sync cache (fallback).

This module keeps the route handlers small and makes the selection logic
testable.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.models import ActionItem, Event, Priority, SourceType
from src.store import BeaconStore, default_db_path, dump_action_item, dump_event


_CACHE_FILE = Path.home() / ".cache" / "beacon" / "last_sync.json"


def _load_cache(cache_file: Path | None = None) -> dict[str, Any]:
    """Load the last sync cache, returning an empty structure if missing."""

    cache_path = cache_file or _CACHE_FILE
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"synced_at": None, "events": [], "action_items": []}


def _store_path_from_env() -> Path | None:
    value = os.environ.get("BEACON_DB")
    if not value:
        return None
    try:
        return Path(value).expanduser()
    except OSError:
        return None


def _store_is_available(db_path: Path) -> bool:
    # Use store only if DB already exists (likely after an ingest).
    return db_path.exists() and db_path.is_file()


def load_dashboard_data(*, limit_events: int = 200, limit_actions: int = 500, cache_file: Path | None = None) -> dict[str, Any]:
    """Return a dict compatible with the legacy sync-cache JSON format."""

    db_path = _store_path_from_env() or default_db_path()
    if _store_is_available(db_path):
        store = BeaconStore(db_path)
        events = store.query_events(limit=limit_events)
        actions = store.query_action_items(limit=limit_actions)

        # best-effort: infer a synced_at from most recent created_at
        all_created = [e.created_at for e in events] + [a.created_at for a in actions]
        synced_at = None
        if all_created:
            synced_at = max(all_created).astimezone(timezone.utc).isoformat()

        return {
            "synced_at": synced_at,
            "events": [dump_event(e) for e in events],
            "action_items": [dump_action_item(a) for a in actions],
            "backend": "store",
            "db_path": str(db_path),
        }

    cache = _load_cache(cache_file)
    cache["backend"] = "cache"
    return cache


def coerce_event_dicts(raw_events: list[dict[str, Any]]) -> list[Event]:
    """Convert event dicts to Event objects (primarily for tests)."""

    out: list[Event] = []
    for e in raw_events:
        out.append(
            Event(
                id=str(e.get("id", "")),
                title=str(e.get("title", "")),
                source_id=str(e.get("source_id", "")),
                source_type=SourceType(str(e.get("source_type", "custom"))),
                occurred_at=_parse_dt(e.get("occurred_at") or e.get("created_at"))
                or datetime.now(tz=timezone.utc),
                summary=str(e.get("summary", "")),
                url=str(e.get("url", "")),
                metadata=e.get("metadata") or {},
            )
        )
    return out


def coerce_action_dicts(raw_actions: list[dict[str, Any]]) -> list[ActionItem]:
    out: list[ActionItem] = []
    for a in raw_actions:
        out.append(
            ActionItem(
                id=str(a.get("id", "")),
                title=str(a.get("title", "")),
                source_id=str(a.get("source_id", "")),
                source_type=SourceType(str(a.get("source_type", "custom"))),
                priority=Priority(str(a.get("priority", "normal"))),
                due_at=_parse_dt(a.get("due_at")),
                url=str(a.get("url", "")),
                completed=bool(a.get("completed")),
                notes=str(a.get("notes", "")),
                metadata=a.get("metadata") or {},
            )
        )
    return out


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
