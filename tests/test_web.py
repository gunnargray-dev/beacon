"""Tests for the Beacon web dashboard routes and API endpoints."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.web.server import create_app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_CACHE = {
    "synced_at": "2026-03-03T12:00:00+00:00",
    "events": [
        {
            "id": "evt-1",
            "title": "Review PR #42",
            "source_id": "my-github",
            "source_type": "github",
            "occurred_at": "2026-03-03T09:00:00+00:00",
            "summary": "Fix authentication bug",
            "url": "https://github.com/example/repo/pull/42",
            "metadata": {},
        },
        {
            "id": "evt-2",
            "title": "Team standup",
            "source_id": "work-cal",
            "source_type": "calendar",
            "occurred_at": "2026-03-03T10:00:00+00:00",
            "summary": "Daily standup meeting",
            "url": "",
            "metadata": {},
        },
    ],
    "action_items": [
        {
            "id": "ai-1",
            "title": "Merge auth PR before EOD",
            "source_id": "my-github",
            "source_type": "github",
            "priority": "high",
            "due_at": "2026-03-03T18:00:00+00:00",
            "url": "https://github.com/example/repo/pull/42",
            "completed": False,
            "notes": "",
            "metadata": {},
        },
    ],
}

EMPTY_CACHE = {"synced_at": None, "events": [], "action_items": []}


@pytest.fixture()
def client_with_data(tmp_path: Path):
    """TestClient with a populated sync cache."""
    cache_file = tmp_path / "last_sync.json"
    cache_file.write_text(json.dumps(SAMPLE_CACHE), encoding="utf-8")
    app = create_app()
    with patch("src.web.routes._CACHE_FILE", cache_file):
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c


@pytest.fixture()
def client_empty(tmp_path: Path):
    """TestClient with an empty (no data) sync cache."""
    cache_file = tmp_path / "last_sync.json"
    cache_file.write_text(json.dumps(EMPTY_CACHE), encoding="utf-8")
    app = create_app()
    with patch("src.web.routes._CACHE_FILE", cache_file):
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c


@pytest.fixture()
def client_no_cache(tmp_path: Path):
    """TestClient where the cache file does not exist."""
    missing = tmp_path / "nonexistent.json"
    app = create_app()
    with patch("src.web.routes._CACHE_FILE", missing):
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c


# ---------------------------------------------------------------------------
# Page routes — 200 OK
# ---------------------------------------------------------------------------


def test_landing_returns_200(client_with_data):
    resp = client_with_data.get("/")
    assert resp.status_code == 200
    assert "beacon" in resp.text.lower()


def test_dashboard_returns_200(client_with_data):
    resp = client_with_data.get("/dashboard")
    assert resp.status_code == 200
    assert "dashboard" in resp.text.lower()


def test_briefing_returns_200(client_with_data):
    resp = client_with_data.get("/briefing")
    assert resp.status_code == 200
    assert "briefing" in resp.text.lower()


def test_calendar_returns_200(client_with_data):
    resp = client_with_data.get("/calendar")
    assert resp.status_code == 200
    assert "calendar" in resp.text.lower()


def test_sources_returns_200(client_with_data):
    resp = client_with_data.get("/sources")
    assert resp.status_code == 200
    assert "sources" in resp.text.lower()


def test_settings_returns_200(client_with_data):
    resp = client_with_data.get("/settings")
    assert resp.status_code == 200
    assert "settings" in resp.text.lower()


# ---------------------------------------------------------------------------
# Page routes — empty cache still renders
# ---------------------------------------------------------------------------


def test_dashboard_empty_cache(client_empty):
    resp = client_empty.get("/dashboard")
    assert resp.status_code == 200


def test_dashboard_no_cache_file(client_no_cache):
    resp = client_no_cache.get("/dashboard")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Page content — events and actions appear
# ---------------------------------------------------------------------------


def test_dashboard_shows_event_title(client_with_data):
    resp = client_with_data.get("/dashboard")
    assert "Review PR #42" in resp.text


def test_dashboard_shows_action_item(client_with_data):
    resp = client_with_data.get("/dashboard")
    assert "Merge auth PR before EOD" in resp.text


def test_briefing_shows_event(client_with_data):
    resp = client_with_data.get("/briefing")
    assert "Review PR #42" in resp.text or "github" in resp.text.lower()


def test_calendar_shows_today(client_with_data):
    resp = client_with_data.get("/calendar")
    assert "today" in resp.text.lower() or "cal-day" in resp.text


def test_sources_shows_source_types(client_with_data):
    resp = client_with_data.get("/sources")
    assert "github" in resp.text.lower() or "calendar" in resp.text.lower()


# ---------------------------------------------------------------------------
# API: /api/status
# ---------------------------------------------------------------------------


def test_api_status_returns_200(client_with_data):
    resp = client_with_data.get("/api/status")
    assert resp.status_code == 200


def test_api_status_json_structure(client_with_data):
    data = client_with_data.get("/api/status").json()
    assert data["status"] == "ok"
    assert "event_count" in data
    assert "action_item_count" in data
    assert "synced_at" in data


def test_api_status_event_count(client_with_data):
    data = client_with_data.get("/api/status").json()
    assert data["event_count"] == 2


def test_api_status_no_cache(client_no_cache):
    data = client_no_cache.get("/api/status").json()
    assert data["status"] == "ok"
    assert data["event_count"] == 0


# ---------------------------------------------------------------------------
# API: /api/events
# ---------------------------------------------------------------------------


def test_api_events_returns_200(client_with_data):
    resp = client_with_data.get("/api/events")
    assert resp.status_code == 200


def test_api_events_json_structure(client_with_data):
    data = client_with_data.get("/api/events").json()
    assert "events" in data
    assert "total" in data


def test_api_events_returns_all(client_with_data):
    data = client_with_data.get("/api/events").json()
    assert data["total"] == 2


def test_api_events_filter_by_source_type(client_with_data):
    data = client_with_data.get("/api/events?source_type=github").json()
    assert all(e["source_type"] == "github" for e in data["events"])


def test_api_events_filter_returns_subset(client_with_data):
    data = client_with_data.get("/api/events?source_type=github").json()
    assert data["total"] == 1


def test_api_events_limit(client_with_data):
    data = client_with_data.get("/api/events?limit=1").json()
    assert len(data["events"]) == 1


def test_api_events_empty_cache(client_empty):
    data = client_empty.get("/api/events").json()
    assert data["events"] == []
    assert data["total"] == 0


# ---------------------------------------------------------------------------
# API: /api/actions
# ---------------------------------------------------------------------------


def test_api_actions_returns_200(client_with_data):
    resp = client_with_data.get("/api/actions")
    assert resp.status_code == 200


def test_api_actions_json_structure(client_with_data):
    data = client_with_data.get("/api/actions").json()
    assert "action_items" in data
    assert "total" in data


def test_api_actions_pending_only_by_default(client_with_data):
    data = client_with_data.get("/api/actions").json()
    assert all(not a["completed"] for a in data["action_items"])


def test_api_actions_include_completed(client_with_data):
    data = client_with_data.get("/api/actions?include_completed=true").json()
    assert data["total"] >= 1


def test_api_actions_empty_cache(client_empty):
    data = client_empty.get("/api/actions").json()
    assert data["action_items"] == []
    assert data["total"] == 0


# ---------------------------------------------------------------------------
# HTML structure — nav links present on every page
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/", "/dashboard", "/briefing", "/calendar", "/sources", "/settings"])
def test_nav_links_present(client_with_data, path):
    resp = client_with_data.get(path)
    assert resp.status_code == 200
    assert 'href="/dashboard"' in resp.text
    assert 'href="/briefing"' in resp.text
    assert 'href="/sources"' in resp.text


@pytest.mark.parametrize("path", ["/", "/dashboard", "/briefing", "/calendar", "/sources", "/settings"])
def test_static_css_linked(client_with_data, path):
    resp = client_with_data.get(path)
    assert "/static/style.css" in resp.text


@pytest.mark.parametrize("path", ["/", "/dashboard", "/briefing", "/calendar", "/sources", "/settings"])
def test_static_js_linked(client_with_data, path):
    resp = client_with_data.get(path)
    assert "/static/app.js" in resp.text
