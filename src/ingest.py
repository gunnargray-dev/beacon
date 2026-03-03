"""Ingest sync cache JSON into the persistent Beacon store."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src.models import ActionItem, Event, Priority, SourceType
from src.store import BeaconStore


@dataclass
class IngestResult:
    events_written: int
    actions_written: int


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _event_from_dict(d: dict[str, Any]) -> Event:
    return Event(
        id=d.get("id") or "",
        title=d.get("title") or "",
        source_id=d.get("source_id") or "",
        source_type=SourceType(d.get("source_type") or "custom"),
        occurred_at=_parse_dt(d.get("occurred_at")) or datetime.utcnow(),
        summary=d.get("summary") or "",
        url=d.get("url") or "",
        metadata=d.get("metadata") or {},
        created_at=_parse_dt(d.get("created_at")) or datetime.utcnow(),
    )


def _action_from_dict(d: dict[str, Any]) -> ActionItem:
    return ActionItem(
        id=d.get("id") or "",
        title=d.get("title") or "",
        source_id=d.get("source_id") or "",
        source_type=SourceType(d.get("source_type") or "custom"),
        priority=Priority(d.get("priority") or "medium"),
        due_at=_parse_dt(d.get("due_at")),
        url=d.get("url") or "",
        completed=bool(d.get("completed", False)),
        notes=d.get("notes") or "",
        metadata=d.get("metadata") or {},
        created_at=_parse_dt(d.get("created_at")) or datetime.utcnow(),
    )


def ingest_sync_cache(
    sync_path: str | Path,
    *,
    db_path: str | Path | None = None,
) -> IngestResult:
    """Read a Beacon sync cache JSON file and upsert it into the SQLite store."""

    path = Path(sync_path)
    payload = json.loads(path.read_text(encoding="utf-8"))

    events = [_event_from_dict(e) for e in payload.get("events", [])]
    actions = [_action_from_dict(a) for a in payload.get("action_items", [])]

    store = BeaconStore(db_path=db_path)
    events_written = store.upsert_events(events)
    actions_written = store.upsert_action_items(actions)

    return IngestResult(events_written=events_written, actions_written=actions_written)
