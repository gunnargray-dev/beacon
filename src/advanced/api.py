"""FastAPI router for advanced intelligence endpoints.

Mounts under the existing ``src.web`` application via::

    from src.advanced.api import router as advanced_router
    app.include_router(advanced_router, prefix="/api")

Endpoints
---------
GET /api/briefing          — full daily briefing (events + actions)
GET /api/actions           — pending action items (deduped with web routes)
GET /api/retrospective     — weekly retrospective
GET /api/relationships     — relationship report
GET /api/time-audit        — time audit
GET /api/trends            — trend detection
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["advanced"])
advanced_router = router  # alias for server.py import

_CACHE_FILE = Path.home() / ".cache" / "beacon" / "last_sync.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_cache() -> dict[str, Any]:
    """Load last_sync.json; return empty structure on missing/corrupt file."""
    if _CACHE_FILE.exists():
        try:
            return json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"synced_at": None, "events": [], "action_items": []}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/briefing")
async def api_briefing() -> JSONResponse:
    """Return a full daily briefing: events + pending action items."""
    cache = _load_cache()
    events = sorted(
        cache.get("events", []),
        key=lambda e: e.get("occurred_at") or e.get("created_at") or "",
        reverse=True,
    )[:50]
    pending = [a for a in cache.get("action_items", []) if not a.get("completed")]
    urgent = [a for a in pending if a.get("priority") == "urgent"]
    return JSONResponse(
        {
            "synced_at": cache.get("synced_at"),
            "total_events": len(cache.get("events", [])),
            "recent_events": events,
            "pending_action_items": pending,
            "urgent_count": len(urgent),
        }
    )


@router.get("/actions")
async def api_actions(include_completed: bool = False) -> JSONResponse:
    """Return action items, excluding completed by default."""
    cache = _load_cache()
    items = cache.get("action_items", [])
    if not include_completed:
        items = [a for a in items if not a.get("completed")]
    return JSONResponse({"action_items": items, "total": len(items)})


@router.get("/retrospective")
async def api_retrospective() -> JSONResponse:
    """Return a weekly retrospective report."""
    from src.advanced.retrospective import generate_retrospective
    cache = _load_cache()
    return JSONResponse(generate_retrospective(cache))


@router.get("/relationships")
async def api_relationships(top_n: int = 10) -> JSONResponse:
    """Return a relationship report."""
    from src.advanced.relationships import RelationshipTracker
    cache = _load_cache()
    tracker = RelationshipTracker(cache)
    return JSONResponse(tracker.report())


@router.get("/time-audit")
async def api_time_audit(lookback_days: int = 7) -> JSONResponse:
    """Return a time audit report."""
    from src.advanced.time_audit import generate_time_audit
    cache = _load_cache()
    return JSONResponse(generate_time_audit(cache, lookback_days=lookback_days))


@router.get("/trends")
async def api_trends(window_days: int = 7, history_days: int = 28) -> JSONResponse:
    """Return trend detection results."""
    from src.advanced.trends import detect_trends
    cache = _load_cache()
    return JSONResponse(detect_trends(cache, window_days=window_days, history_days=history_days))
