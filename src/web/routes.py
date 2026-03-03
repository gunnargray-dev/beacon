"""Beacon web dashboard -- route handlers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from src.web.data import _CACHE_FILE as _DATA_CACHE_FILE
from src.web.data import load_dashboard_data
from src.web.server import templates

# Backwards-compatible symbol for tests that patch the cache file location.
_CACHE_FILE = _DATA_CACHE_FILE

router = APIRouter()



def _load_cache() -> dict[str, Any]:
    """Backwards-compatible test hook.

    The web module historically exposed `_load_cache()` and `_CACHE_FILE`, which
    unit tests patch to simulate different last_sync.json contents.

    We keep this API stable while still allowing the dashboard to read from the
    SQLite store when present.
    """

    return load_dashboard_data(cache_file=_CACHE_FILE)


def _format_synced_at(synced_at: str | None) -> str:
    if not synced_at:
        return "Never"
    try:
        dt = datetime.fromisoformat(synced_at)
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return synced_at


def _source_icon(source_type: str) -> str:
    icons = {
        "github": "⌥",
        "calendar": "◈",
        "email": "◉",
        "weather": "◎",
        "news": "◆",
        "hacker_news": "▲",
        "custom": "◇",
    }
    return icons.get(source_type.lower(), "·")


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
async def landing(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "landing.html")


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    cache = _load_cache()
    events = cache.get("events", [])
    action_items = cache.get("action_items", [])

    # Sort events newest-first
    def _sort_key(e: dict[str, Any]) -> str:
        return e.get("occurred_at") or e.get("created_at") or ""

    events_sorted = sorted(events, key=_sort_key, reverse=True)[:50]

    pending_actions = [a for a in action_items if not a.get("completed")]
    urgent_actions = [a for a in action_items if not a.get("completed") and a.get("priority") == "urgent"]

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "events": events_sorted,
            "action_items": pending_actions,
            "urgent_count": len(urgent_actions),
            "total_events": len(events),
            "synced_at": _format_synced_at(cache.get("synced_at")),
            "source_icon": _source_icon,
        },
    )


@router.get("/briefing", response_class=HTMLResponse)
async def briefing(request: Request) -> HTMLResponse:
    cache = _load_cache()
    events = cache.get("events", [])
    action_items = cache.get("action_items", [])

    today_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    # Group events by source type
    by_source: dict[str, list[dict[str, Any]]] = {}
    for ev in events:
        st = ev.get("source_type", "custom")
        by_source.setdefault(st, []).append(ev)

    pending_actions = [a for a in action_items if not a.get("completed")]
    urgent_actions = [a for a in pending_actions if a.get("priority") == "urgent"]
    high_actions = [a for a in pending_actions if a.get("priority") == "high"]

    return templates.TemplateResponse(
        request,
        "briefing.html",
        {
            "today": today_str,
            "events_by_source": by_source,
            "total_events": len(events),
            "pending_actions": pending_actions,
            "urgent_actions": urgent_actions,
            "high_actions": high_actions,
            "synced_at": _format_synced_at(cache.get("synced_at")),
            "source_icon": _source_icon,
        },
    )


@router.get("/calendar", response_class=HTMLResponse)
async def calendar_view(request: Request) -> HTMLResponse:
    cache = _load_cache()
    events = cache.get("events", [])

    # Build a simple day-keyed dict of events
    day_events: dict[str, list[dict[str, Any]]] = {}
    for ev in events:
        ts = ev.get("occurred_at") or ev.get("created_at") or ""
        if ts:
            try:
                day = datetime.fromisoformat(ts).strftime("%Y-%m-%d")
            except ValueError:
                day = "unknown"
        else:
            day = "unknown"
        day_events.setdefault(day, []).append(ev)

    # Past 7 days + next 7 days
    from datetime import timedelta

    today = datetime.now(tz=timezone.utc).date()
    week_days = [(today + timedelta(days=i)).isoformat() for i in range(-3, 8)]

    return templates.TemplateResponse(
        request,
        "calendar.html",
        {
            "week_days": week_days,
            "today": today.isoformat(),
            "day_events": day_events,
            "synced_at": _format_synced_at(cache.get("synced_at")),
            "source_icon": _source_icon,
        },
    )


@router.get("/sources", response_class=HTMLResponse)
async def sources_view(request: Request) -> HTMLResponse:
    cache = _load_cache()
    events = cache.get("events", [])
    action_items = cache.get("action_items", [])

    # Summarise per source
    source_stats: dict[str, dict[str, Any]] = {}
    for ev in events:
        st = ev.get("source_type", "custom")
        sid = ev.get("source_id", st)
        key = sid or st
        if key not in source_stats:
            source_stats[key] = {
                "id": key,
                "type": st,
                "icon": _source_icon(st),
                "event_count": 0,
                "action_count": 0,
                "latest": None,
            }
        source_stats[key]["event_count"] += 1
        ts = ev.get("occurred_at") or ev.get("created_at")
        if ts and (source_stats[key]["latest"] is None or ts > source_stats[key]["latest"]):
            source_stats[key]["latest"] = ts

    for ai in action_items:
        st = ai.get("source_type", "custom")
        sid = ai.get("source_id", st)
        key = sid or st
        if key in source_stats:
            source_stats[key]["action_count"] += 1

    return templates.TemplateResponse(
        request,
        "sources.html",
        {
            "sources": list(source_stats.values()),
            "synced_at": _format_synced_at(cache.get("synced_at")),
        },
    )


@router.get("/settings", response_class=HTMLResponse)
async def settings(request: Request) -> HTMLResponse:
    # Try to load beacon.toml for display
    config_info: dict[str, Any] = {}
    config_paths = [
        Path("beacon.toml"),
        Path.home() / ".config" / "beacon" / "beacon.toml",
    ]
    for cp in config_paths:
        if cp.exists():
            config_info["path"] = str(cp)
            try:
                import tomllib  # type: ignore[import-not-found]

                config_info["raw"] = tomllib.loads(cp.read_text(encoding="utf-8"))
            except Exception:
                config_info["raw"] = {}
            break

    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "config": config_info,
        },
    )


# ---------------------------------------------------------------------------
# JSON API routes
# ---------------------------------------------------------------------------


@router.get("/api/status")
async def api_status() -> JSONResponse:
    cache = _load_cache()
    return JSONResponse(
        {
            "status": "ok",
            "synced_at": cache.get("synced_at"),
            "event_count": len(cache.get("events", [])),
            "action_item_count": len(cache.get("action_items", [])),
        }
    )


@router.get("/api/events")
async def api_events(limit: int = 50, source_type: str | None = None) -> JSONResponse:
    cache = _load_cache()
    events = cache.get("events", [])
    if source_type:
        events = [e for e in events if e.get("source_type") == source_type]
    events = sorted(
        events,
        key=lambda e: e.get("occurred_at") or e.get("created_at") or "",
        reverse=True,
    )[:limit]
    return JSONResponse({"events": events, "total": len(events)})


@router.get("/api/actions")
async def api_actions(include_completed: bool = False) -> JSONResponse:
    cache = _load_cache()
    items = cache.get("action_items", [])
    if not include_completed:
        items = [a for a in items if not a.get("completed")]
    return JSONResponse({"action_items": items, "total": len(items)})
