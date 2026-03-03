"""Pagination and sorting helpers for Beacon store queries.

This module is stdlib-only.

We deliberately keep the "cursor" format opaque but stable:
    base64url(json({"created_at": "...", "id": "..."}))

Cursor semantics: return items *after* the cursor (exclusive) using the
requested sort order.

Supported sort keys:
- events: occurred_at desc (default), occurred_at asc
- action items: default store ordering (completed/due/created_at), created_at desc

The initial focus is API compatibility + deterministic ordering.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable


def _dt_to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _iso_to_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def encode_cursor(*, created_at: datetime, item_id: str) -> str:
    payload = {"created_at": _dt_to_iso(created_at), "id": item_id}
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


@dataclass(frozen=True)
class Cursor:
    created_at: datetime
    item_id: str


def decode_cursor(value: str) -> Cursor:
    # restore padding
    padded = value + "=" * (-len(value) % 4)
    raw = base64.urlsafe_b64decode(padded.encode("ascii"))
    obj = json.loads(raw.decode("utf-8"))
    if not isinstance(obj, dict) or "created_at" not in obj or "id" not in obj:
        raise ValueError("Invalid cursor")
    return Cursor(created_at=_iso_to_dt(str(obj["created_at"])), item_id=str(obj["id"]))


def clamp_limit(limit: int, *, default: int = 100, min_value: int = 1, max_value: int = 500) -> int:
    if limit is None:
        return default
    if limit < min_value or limit > max_value:
        raise ValueError(f"limit must be between {min_value} and {max_value}")
    return int(limit)


def slice_after_cursor(rows: list[dict[str, Any]], *, cursor: Cursor | None) -> list[dict[str, Any]]:
    """Filter rows to those strictly after cursor using (created_at, id) ascending tie-break.

    Caller should have already ordered rows consistently with this tuple.
    """

    if cursor is None:
        return rows

    out: list[dict[str, Any]] = []
    for r in rows:
        created_at = r.get("created_at")
        item_id = r.get("id")
        if created_at is None or item_id is None:
            continue
        if isinstance(created_at, str):
            created_at_dt = _iso_to_dt(created_at)
        else:
            created_at_dt = created_at
        if (created_at_dt, str(item_id)) > (cursor.created_at, cursor.item_id):
            out.append(r)
    return out
