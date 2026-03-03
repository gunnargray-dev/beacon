"""Store-backed JSON API endpoints.

These endpoints expose the SQLite store directly for programmatic queries.
They are designed to be stdlib-first for core logic, and use FastAPI only
at the boundary.

Mounted under /api/store via src.web.server.

Endpoints
---------
GET /api/store/meta
GET /api/store/events
GET /api/store/action-items
GET /api/store/stats
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from src.store import BeaconStore, dump_action_item, dump_event
from src.ops import compute_store_stats

router = APIRouter(tags=["store"])


def _parse_iso_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid datetime: {value!r}") from e
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _get_store() -> BeaconStore:
    db_path = os.environ.get("BEACON_DB")
    return BeaconStore(db_path=db_path) if db_path else BeaconStore()


@router.get("/meta")
async def api_store_meta() -> JSONResponse:
    store = _get_store()
    return JSONResponse(
        {
            "db_path": str(store.db_path),
            "db_exists": store.db_path.exists(),
            "backend": "store" if store.db_path.exists() else "missing",
        }
    )


@router.get("/events")
async def api_store_events(
    source_type: str | None = None,
    source_id: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 100,
) -> JSONResponse:
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 500")

    store = _get_store()
    if not store.db_path.exists():
        raise HTTPException(status_code=404, detail="store database not found")

    events = store.query_events(
        source_type=source_type,
        source_name=source_id,
        since=_parse_iso_dt(since),
        until=_parse_iso_dt(until),
        limit=limit,
    )
    payload: list[dict[str, Any]] = [dump_event(e) for e in events]
    return JSONResponse({"events": payload, "count": len(payload)})


@router.get("/stats")
async def api_store_stats() -> JSONResponse:
    store = _get_store()
    if not store.db_path.exists():
        raise HTTPException(status_code=404, detail="store database not found")

    stats = compute_store_stats(store)
    return JSONResponse(
        {
            "db_path": str(store.db_path),
            "events": {
                "total": stats.total_events,
                "by_source_type": stats.events_by_source_type,
            },
            "action_items": {
                "total": stats.total_action_items,
                "completed": stats.completed_action_items,
                "pending": stats.pending_action_items,
                "by_source_type": stats.action_items_by_source_type,
            },
        }
    )


@router.get("/action-items")
async def api_store_action_items(
    source_type: str | None = None,
    source_id: str | None = None,
    priority: str | None = None,
    completed: bool | None = None,
    due_before: str | None = None,
    limit: int = 100,
) -> JSONResponse:
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 500")

    store = _get_store()
    if not store.db_path.exists():
        raise HTTPException(status_code=404, detail="store database not found")

    items = store.query_action_items(
        source_type=source_type,
        source_name=source_id,
        priority=priority,
        completed=completed,
        due_before=_parse_iso_dt(due_before),
        limit=limit,
    )
    payload: list[dict[str, Any]] = [dump_action_item(a) for a in items]
    return JSONResponse({"action_items": payload, "count": len(payload)})
