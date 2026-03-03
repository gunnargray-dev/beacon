"""Additional route and API tests for the Beacon web dashboard."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.web.server import create_app

_app = create_app()
_client = TestClient(_app, raise_server_exceptions=True)

# ---------------------------------------------------------------------------
# Sample cache payload
# ---------------------------------------------------------------------------

_SAMPLE_CACHE = {
    "synced_at": "2026-03-03T12:00:00+00:00",
    "events": [
        {
            "id": "evt-1",
            "title": "Test notification",
            "source_id": "gh",
            "source_type": "github",
            "occurred_at": "2026-03-03T10:00:00+00:00",
            "summary": "PR review requested",
            "url": "https://github.com/foo/bar/pull/1",
            "metadata": {},
        },
        {
            "id": "evt-2",
            "title": "Weather: London",
            "source_id": "weather",
            "source_type": "weather",
            "occurred_at": "2026-03-03T09:00:00+00:00",
            "summary": "15°C / 59°F, Partly cloudy",
            "url": "",
            "metadata": {},
        },
    ],
    "action_items": [
        {
            "id": "act-1",
            "title": "Review PR #42",
            "source_id": "gh",
            "source_type": "github",
            "priority": "high",
            "due_at": None,
            "url": "https://github.com/foo/bar/pull/42",
            "completed": False,
            "notes": "",
            "metadata": {},
        },
        {
            "id": "act-2",
            "title": "Fix critical bug",
            "source_id": "gh",
            "source_type": "github",
            "priority": "urgent",
            "due_at": "2026-03-04T00:00:00+00:00",
            "url": "",
            "completed": False,
            "notes": "blocks release",
            "metadata": {},
        },
        {
            "id": "act-3",
            "title": "Completed task",
            "source_id": "gh",
            "source_type": "github",
            "priority": "low",
            "due_at": None,
            "url": "",
            "completed": True,
            "notes": "",
            "metadata": {},
        },
    ],
}


def _mock_cache(data: dict | None = None):
    """Context manager patching _load_cache."""
    return patch(
        "src.web.routes._load_cache",
        return_value=data if data is not None else _SAMPLE_CACHE,
    )


# ---------------------------------------------------------------------------
# Page routes — status codes
# ---------------------------------------------------------------------------


class TestPageRoutes(unittest.TestCase):

    def test_landing_returns_200(self):
        with _mock_cache({}):
            r = _client.get("/")
        self.assertEqual(r.status_code, 200)

    def test_landing_contains_beacon(self):
        with _mock_cache({}):
            r = _client.get("/")
        self.assertIn(b"beacon", r.content.lower())

    def test_dashboard_returns_200(self):
        with _mock_cache():
            r = _client.get("/dashboard")
        self.assertEqual(r.status_code, 200)

    def test_dashboard_shows_events(self):
        with _mock_cache():
            r = _client.get("/dashboard")
        self.assertIn(b"Test notification", r.content)

    def test_dashboard_shows_action_items(self):
        with _mock_cache():
            r = _client.get("/dashboard")
        self.assertIn(b"Review PR #42", r.content)

    def test_dashboard_empty_cache(self):
        with _mock_cache({"synced_at": None, "events": [], "action_items": []}):
            r = _client.get("/dashboard")
        self.assertEqual(r.status_code, 200)

    def test_briefing_returns_200(self):
        with _mock_cache():
            r = _client.get("/briefing")
        self.assertEqual(r.status_code, 200)

    def test_briefing_shows_urgent(self):
        with _mock_cache():
            r = _client.get("/briefing")
        self.assertIn(b"Fix critical bug", r.content)

    def test_briefing_groups_by_source(self):
        with _mock_cache():
            r = _client.get("/briefing")
        self.assertIn(b"github", r.content.lower())

    def test_calendar_returns_200(self):
        with _mock_cache():
            r = _client.get("/calendar")
        self.assertEqual(r.status_code, 200)

    def test_calendar_shows_today(self):
        with _mock_cache():
            r = _client.get("/calendar")
        self.assertIn(b"today", r.content)

    def test_sources_returns_200(self):
        with _mock_cache():
            r = _client.get("/sources")
        self.assertEqual(r.status_code, 200)

    def test_sources_shows_source_id(self):
        with _mock_cache():
            r = _client.get("/sources")
        self.assertIn(b"gh", r.content)

    def test_sources_empty_cache(self):
        with _mock_cache({"synced_at": None, "events": [], "action_items": []}):
            r = _client.get("/sources")
        self.assertEqual(r.status_code, 200)

    def test_settings_returns_200(self):
        with _mock_cache({}):
            r = _client.get("/settings")
        self.assertEqual(r.status_code, 200)

    def test_settings_shows_cli_reference(self):
        with _mock_cache({}):
            r = _client.get("/settings")
        self.assertIn(b"beacon init", r.content)


# ---------------------------------------------------------------------------
# API routes — JSON
# ---------------------------------------------------------------------------


class TestApiStatus(unittest.TestCase):

    def test_returns_200(self):
        with _mock_cache():
            r = _client.get("/api/status")
        self.assertEqual(r.status_code, 200)

    def test_returns_json(self):
        with _mock_cache():
            r = _client.get("/api/status")
        self.assertIsInstance(r.json(), dict)

    def test_has_required_keys(self):
        with _mock_cache():
            data = _client.get("/api/status").json()
        for key in ("status", "synced_at", "event_count", "action_item_count"):
            self.assertIn(key, data)

    def test_counts_match_cache(self):
        with _mock_cache():
            data = _client.get("/api/status").json()
        self.assertEqual(data["event_count"], 2)
        self.assertEqual(data["action_item_count"], 3)

    def test_status_ok(self):
        with _mock_cache():
            self.assertEqual(_client.get("/api/status").json()["status"], "ok")

    def test_empty_cache(self):
        with _mock_cache({"synced_at": None, "events": [], "action_items": []}):
            data = _client.get("/api/status").json()
        self.assertEqual(data["event_count"], 0)


class TestApiEvents(unittest.TestCase):

    def test_returns_200(self):
        with _mock_cache():
            self.assertEqual(_client.get("/api/events").status_code, 200)

    def test_has_events_key(self):
        with _mock_cache():
            data = _client.get("/api/events").json()
        self.assertIn("events", data)
        self.assertIsInstance(data["events"], list)

    def test_returns_all_events_by_default(self):
        with _mock_cache():
            data = _client.get("/api/events").json()
        self.assertEqual(len(data["events"]), 2)

    def test_filter_by_source_type(self):
        with _mock_cache():
            data = _client.get("/api/events?source_type=github").json()
        self.assertEqual(len(data["events"]), 1)
        self.assertEqual(data["events"][0]["source_type"], "github")

    def test_filter_returns_empty_for_unknown_type(self):
        with _mock_cache():
            data = _client.get("/api/events?source_type=nonexistent").json()
        self.assertEqual(len(data["events"]), 0)

    def test_limit_parameter(self):
        with _mock_cache():
            data = _client.get("/api/events?limit=1").json()
        self.assertEqual(len(data["events"]), 1)

    def test_events_sorted_newest_first(self):
        with _mock_cache():
            events = _client.get("/api/events").json()["events"]
        if len(events) >= 2:
            self.assertGreaterEqual(
                events[0].get("occurred_at", ""),
                events[1].get("occurred_at", ""),
            )


class TestApiActions(unittest.TestCase):

    def test_returns_200(self):
        with _mock_cache():
            self.assertEqual(_client.get("/api/actions").status_code, 200)

    def test_has_action_items_key(self):
        with _mock_cache():
            data = _client.get("/api/actions").json()
        self.assertIn("action_items", data)
        self.assertIsInstance(data["action_items"], list)

    def test_excludes_completed_by_default(self):
        with _mock_cache():
            data = _client.get("/api/actions").json()
        self.assertEqual(len(data["action_items"]), 2)
        for item in data["action_items"]:
            self.assertFalse(item["completed"])

    def test_include_completed(self):
        with _mock_cache():
            data = _client.get("/api/actions?include_completed=true").json()
        self.assertEqual(len(data["action_items"]), 3)

    def test_total_key_present(self):
        with _mock_cache():
            self.assertIn("total", _client.get("/api/actions").json())

    def test_empty_cache(self):
        with _mock_cache({"synced_at": None, "events": [], "action_items": []}):
            data = _client.get("/api/actions").json()
        self.assertEqual(len(data["action_items"]), 0)


# ---------------------------------------------------------------------------
# Cache loading
# ---------------------------------------------------------------------------


class TestLoadCache(unittest.TestCase):

    def test_returns_empty_structure_when_no_file(self):
        from src.web.routes import _load_cache
        with patch("src.web.routes._CACHE_FILE", Path("/nonexistent/path/cache.json")):
            result = _load_cache()
        self.assertEqual(result["events"], [])
        self.assertEqual(result["action_items"], [])

    def test_loads_valid_json(self):
        from src.web.routes import _load_cache
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(_SAMPLE_CACHE, f)
            tmp_path = Path(f.name)
        try:
            with patch("src.web.routes._CACHE_FILE", tmp_path):
                result = _load_cache()
            self.assertEqual(len(result["events"]), 2)
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_handles_corrupt_json(self):
        from src.web.routes import _load_cache
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{ bad json !!!")
            tmp_path = Path(f.name)
        try:
            with patch("src.web.routes._CACHE_FILE", tmp_path):
                result = _load_cache()
            self.assertEqual(result["events"], [])
        finally:
            tmp_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# CLI dashboard command
# ---------------------------------------------------------------------------


class TestCliDashboard(unittest.TestCase):

    def test_dashboard_command_registered(self):
        from src.cli import build_parser
        args = build_parser().parse_args(["dashboard", "--port", "9000"])
        self.assertEqual(args.command, "dashboard")
        self.assertEqual(args.port, 9000)

    def test_dashboard_default_host_port(self):
        from src.cli import build_parser
        args = build_parser().parse_args(["dashboard"])
        self.assertEqual(args.host, "127.0.0.1")
        self.assertEqual(args.port, 8000)

    def test_dashboard_exits_without_uvicorn(self):
        import sys
        from src.cli import build_parser
        args = build_parser().parse_args(["dashboard"])
        with patch.dict(sys.modules, {"uvicorn": None}):
            with self.assertRaises(SystemExit) as ctx:
                args.func(args)
        self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
