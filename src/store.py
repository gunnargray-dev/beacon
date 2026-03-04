"""SQLite-backed persistent store for Beacon.

This module is deliberately stdlib-only.

The store is optional: if the database path does not exist, Beacon can
continue operating from the sync cache.
"""

from __future__ import annotations

import base64
import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from src.migrations import Migration, apply_migrations
from src.models import ActionItem, Event, Priority, SourceType


def default_db_path() -> Path:
    """Default store location under ~/.cache/beacon."""
    return Path.home() / ".cache" / "beacon" / "beacon.db"


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _dt_to_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        # Treat naive datetimes as UTC for storage.
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _iso_to_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    # datetime.fromisoformat supports offsets.
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class BeaconStore:
    """SQLite store for events and action items."""

    LATEST_SCHEMA_VERSION = 1

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else default_db_path()

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _migrations(self) -> list[Migration]:
        def v1_init(conn: sqlite3.Connection) -> None:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    url TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS action_items (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    due_at TEXT,
                    url TEXT NOT NULL,
                    completed INTEGER NOT NULL,
                    notes TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

        return [
            Migration(version=1, name="init_store", apply=v1_init),
        ]

    def init_db(self) -> None:
        with self.connect() as conn:
            apply_migrations(conn, self._migrations())

    def encode_event_cursor(self, event: Event, *, sort: str = "occurred_at_desc") -> str:
        """Return an opaque cursor string for pagination."""
        if sort not in {"occurred_at_desc", "occurred_at_asc"}:
            raise ValueError(f"Invalid sort: {sort!r}")
        payload = {
            "occurred_at": _dt_to_iso(event.occurred_at),
            "created_at": _dt_to_iso(event.created_at),
            "id": event.id,
        }
        raw = json.dumps(payload, sort_keys=True).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    def encode_action_item_cursor(self, item: ActionItem, *, sort: str = "default") -> str:
        if sort not in {"default", "created_at_desc"}:
            raise ValueError(f"Invalid sort: {sort!r}")
        payload = {
            "created_at": _dt_to_iso(item.created_at),
            "id": item.id,
        }
        raw = json.dumps(payload, sort_keys=True).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    # ---------------------------------------------------------------------
    # Upserts / ingestion
    # ---------------------------------------------------------------------

    def upsert_events(self, events: Iterable[Event]) -> int:
        self.init_db()
        rows = [
            (
                e.id,
                e.title,
                e.source_id,
                e.source_type.value,
                _dt_to_iso(e.occurred_at) or _dt_to_iso(_utcnow()),
                e.summary or "",
                e.url or "",
                json.dumps(e.metadata or {}, sort_keys=True),
                _dt_to_iso(e.created_at) or _dt_to_iso(_utcnow()),
            )
            for e in events
        ]
        if not rows:
            return 0
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO events (
                    id, title, source_id, source_type, occurred_at,
                    summary, url, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    source_id=excluded.source_id,
                    source_type=excluded.source_type,
                    occurred_at=excluded.occurred_at,
                    summary=excluded.summary,
                    url=excluded.url,
                    metadata_json=excluded.metadata_json
                """,
                rows,
            )
            return conn.total_changes

    def upsert_action_items(self, items: Iterable[ActionItem]) -> int:
        self.init_db()
        rows = [
            (
                a.id,
                a.title,
                a.source_id,
                a.source_type.value,
                a.priority.value,
                _dt_to_iso(a.due_at),
                a.url or "",
                1 if a.completed else 0,
                a.notes or "",
                json.dumps(a.metadata or {}, sort_keys=True),
                _dt_to_iso(a.created_at) or _dt_to_iso(_utcnow()),
            )
            for a in items
        ]
        if not rows:
            return 0
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO action_items (
                    id, title, source_id, source_type, priority, due_at,
                    url, completed, notes, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    source_id=excluded.source_id,
                    source_type=excluded.source_type,
                    priority=excluded.priority,
                    due_at=excluded.due_at,
                    url=excluded.url,
                    completed=excluded.completed,
                    notes=excluded.notes,
                    metadata_json=excluded.metadata_json
                """,
                rows,
            )
            return conn.total_changes

    # ---------------------------------------------------------------------
    # Queries
    # ---------------------------------------------------------------------

    def query_events(
        self,
        *,
        source_type: str | None = None,
        source_name: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 100,
        cursor: str | None = None,
        sort: str = "occurred_at_desc",
    ) -> list[Event]:
        self.init_db()
        where: list[str] = []
        params: list[Any] = []

        if source_type:
            where.append("source_type = ?")
            params.append(source_type)
        if source_name:
            where.append("source_id = ?")
            params.append(source_name)
        if since:
            where.append("occurred_at >= ?")
            params.append(_dt_to_iso(since))
        if until:
            where.append("occurred_at <= ?")
            params.append(_dt_to_iso(until))

        if sort not in {"occurred_at_desc", "occurred_at_asc"}:
            raise ValueError(f"Invalid sort: {sort!r}")

        order_sql = (
            "ORDER BY occurred_at DESC, created_at DESC, id DESC "
            if sort == "occurred_at_desc"
            else "ORDER BY occurred_at ASC, created_at ASC, id ASC "
        )

        if cursor:
            # Cursor pagination uses (occurred_at, created_at, id) with the chosen direction.
            cur = json.loads(
                base64.urlsafe_b64decode((cursor + "=" * (-len(cursor) % 4)).encode("ascii")).decode(
                    "utf-8"
                )
            )
            c_occ = str(cur.get("occurred_at"))
            c_created = str(cur.get("created_at"))
            c_id = str(cur.get("id"))
            if sort == "occurred_at_desc":
                where.append(
                    "(occurred_at < ? OR (occurred_at = ? AND (created_at < ? OR (created_at = ? AND id < ?))))"
                )
                params.extend([c_occ, c_occ, c_created, c_created, c_id])
            else:
                where.append(
                    "(occurred_at > ? OR (occurred_at = ? AND (created_at > ? OR (created_at = ? AND id > ?))))"
                )
                params.extend([c_occ, c_occ, c_created, c_created, c_id])

        where_sql = (" WHERE " + " AND ".join(where)) if where else ""

        sql = (
            "SELECT id, title, source_id, source_type, occurred_at, summary, url, metadata_json, created_at "
            "FROM events"
            f"{where_sql} "
            f"{order_sql}"
            "LIMIT ?"
        )
        params.append(int(limit))

        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        out: list[Event] = []
        for r in rows:
            out.append(
                Event(
                    id=r["id"],
                    title=r["title"],
                    source_id=r["source_id"],
                    source_type=SourceType(r["source_type"]),
                    occurred_at=_iso_to_dt(r["occurred_at"]) or _utcnow(),
                    summary=r["summary"],
                    url=r["url"],
                    metadata=json.loads(r["metadata_json"] or "{}"),
                    created_at=_iso_to_dt(r["created_at"]) or _utcnow(),
                )
            )
        return out

    def query_action_items(
        self,
        *,
        source_type: str | None = None,
        source_name: str | None = None,
        priority: str | None = None,
        completed: bool | None = None,
        due_before: datetime | None = None,
        limit: int = 100,
        cursor: str | None = None,
        sort: str = "default",
    ) -> list[ActionItem]:
        self.init_db()
        where: list[str] = []
        params: list[Any] = []

        if source_type:
            where.append("source_type = ?")
            params.append(source_type)
        if source_name:
            where.append("source_id = ?")
            params.append(source_name)
        if priority:
            where.append("priority = ?")
            params.append(priority)
        if completed is not None:
            where.append("completed = ?")
            params.append(1 if completed else 0)
        if due_before:
            where.append("due_at IS NOT NULL AND due_at <= ?")
            params.append(_dt_to_iso(due_before))

        if sort not in {"default", "created_at_desc"}:
            raise ValueError(f"Invalid sort: {sort!r}")

        if sort == "created_at_desc":
            order_sql = "ORDER BY created_at DESC, id DESC "
        else:
            order_sql = "ORDER BY completed ASC, due_at IS NULL, due_at ASC, created_at DESC, id DESC "

        if cursor:
            cur = json.loads(
                base64.urlsafe_b64decode((cursor + "=" * (-len(cursor) % 4)).encode("ascii")).decode(
                    "utf-8"
                )
            )
            c_created = str(cur.get("created_at"))
            c_id = str(cur.get("id"))
            # Both supported sorts are descending on (created_at, id)
            where.append("(created_at < ? OR (created_at = ? AND id < ?))")
            params.extend([c_created, c_created, c_id])

        where_sql = (" WHERE " + " AND ".join(where)) if where else ""

        sql = (
            "SELECT id, title, source_id, source_type, priority, due_at, url, completed, notes, metadata_json, created_at "
            "FROM action_items"
            f"{where_sql} "
            f"{order_sql}"
            "LIMIT ?"
        )
        params.append(int(limit))

        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        out: list[ActionItem] = []
        for r in rows:
            out.append(
                ActionItem(
                    id=r["id"],
                    title=r["title"],
                    source_id=r["source_id"],
                    source_type=SourceType(r["source_type"]),
                    priority=Priority(r["priority"]),
                    due_at=_iso_to_dt(r["due_at"]),
                    url=r["url"],
                    completed=bool(r["completed"]),
                    notes=r["notes"],
                    metadata=json.loads(r["metadata_json"] or "{}"),
                    created_at=_iso_to_dt(r["created_at"]) or _utcnow(),
                )
            )
        return out


def dump_event(event: Event) -> dict[str, Any]:
    """Lossless dict form for printing/debugging."""
    d = asdict(event)
    d["source_type"] = event.source_type.value
    d["occurred_at"] = _dt_to_iso(event.occurred_at)
    d["created_at"] = _dt_to_iso(event.created_at)
    return d


def dump_action_item(item: ActionItem) -> dict[str, Any]:
    d = asdict(item)
    d["source_type"] = item.source_type.value
    d["priority"] = item.priority.value
    d["due_at"] = _dt_to_iso(item.due_at)
    d["created_at"] = _dt_to_iso(item.created_at)
    return d
