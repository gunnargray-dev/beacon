"""Tests for src/advanced/api.py — FastAPI router endpoints."""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

REF = datetime(2024, 3, 15, 12, 0, 0, tzinfo=timezone.utc)


def _event(title="Test", source_type="github", days_ago=1, **kwargs):
    dt = REF - timedelta(days=days_ago)
    return {
        "id": f"evt-{title[:6]}",
        "title": title,
        "source_type": source_type,
        "source_id": source_type,
        "occurred_at": dt.isoformat(),
        "summary": "",
        "url": "",
        "metadata": kwargs.pop("metadata", {}),
        **kwargs,
    }


def _action(title="Do thing", priority="medium", completed=False, days_ago=1):
    dt = REF - timedelta(days=days_ago)
    return {
        "id": f"act-{title[:6]}",
        "title": title,
        "source_type": "github",
        "source_id": "github",
        "priority": priority,
        "completed": completed,
        "created_at": dt.isoformat(),
    }


def _make_cache(events=None, action_items=None):
    return {
        "synced_at": REF.isoformat(),
        "events": events or [],
        "action_items": action_items or [],
    }


# ---------------------------------------------------------------------------
# We use the TestClient from FastAPI / Starlette.
# If fastapi is not installed the tests are skipped gracefully.
# ---------------------------------------------------------------------------

try:
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False

SKIP_MSG = "fastapi not installed"


def _make_app(cache: dict) -> "TestClient":
    """Create a minimal FastAPI app with the advanced router and mock cache."""
    app = FastAPI()

    import src.advanced.api as adv_api

    def _fake_load():
        return cache

    # Patch _load_cache in the api module
    with patch.object(adv_api, "_load_cache", side_effect=_fake_load):
        app.include_router(adv_api.router, prefix="/api")
    return app, adv_api


@unittest.skipUnless(_FASTAPI_AVAILABLE, SKIP_MSG)
class TestAdvancedApiRoutes(unittest.TestCase):

    def _client(self, cache=None):
        """Return a TestClient with patched _load_cache."""
        import src.advanced.api as adv_api
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(adv_api.router, prefix="/api")

        _cache = cache or _make_cache()

        # patch at the module level
        patcher = patch.object(adv_api, "_load_cache", return_value=_cache)
        patcher.start()
        self.addCleanup(patcher.stop)

        return TestClient(app)

    # ── /api/briefing ────────────────────────────────────────────────────

    def test_briefing_200(self):
        client = self._client()
        r = client.get("/api/briefing")
        self.assertEqual(r.status_code, 200)

    def test_briefing_structure(self):
        cache = _make_cache(
            events=[_event("E1"), _event("E2")],
            action_items=[_action("A1"), _action("A2", completed=True)],
        )
        client = self._client(cache)
        data = client.get("/api/briefing").json()
        self.assertIn("recent_events", data)
        self.assertIn("pending_action_items", data)
        self.assertIn("urgent_count", data)
        self.assertIn("total_events", data)

    def test_briefing_filters_completed_actions(self):
        cache = _make_cache(
            action_items=[
                _action("Open", completed=False),
                _action("Done", completed=True),
            ]
        )
        client = self._client(cache)
        data = client.get("/api/briefing").json()
        titles = [a["title"] for a in data["pending_action_items"]]
        self.assertIn("Open", titles)
        self.assertNotIn("Done", titles)

    def test_briefing_urgent_count(self):
        cache = _make_cache(
            action_items=[
                _action("Urgent task", priority="urgent"),
                _action("Normal task", priority="medium"),
            ]
        )
        client = self._client(cache)
        data = client.get("/api/briefing").json()
        self.assertEqual(data["urgent_count"], 1)

    # ── /api/actions ─────────────────────────────────────────────────────

    def test_actions_200(self):
        client = self._client()
        r = client.get("/api/actions")
        self.assertEqual(r.status_code, 200)

    def test_actions_excludes_completed_by_default(self):
        cache = _make_cache(
            action_items=[
                _action("Open"),
                _action("Done", completed=True),
            ]
        )
        client = self._client(cache)
        data = client.get("/api/actions").json()
        self.assertEqual(data["total"], 1)

    def test_actions_include_completed(self):
        cache = _make_cache(
            action_items=[
                _action("Open"),
                _action("Done", completed=True),
            ]
        )
        client = self._client(cache)
        data = client.get("/api/actions?include_completed=true").json()
        self.assertEqual(data["total"], 2)

    # ── /api/retrospective ───────────────────────────────────────────────

    def test_retrospective_200(self):
        client = self._client()
        r = client.get("/api/retrospective")
        self.assertEqual(r.status_code, 200)

    def test_retrospective_has_metrics(self):
        cache = _make_cache(events=[_event("PR merged", "github", days_ago=1)])
        client = self._client(cache)
        data = client.get("/api/retrospective").json()
        self.assertIn("metrics", data)
        self.assertIn("period", data)
        self.assertIn("trend_vs_prior_week", data)

    # ── /api/relationships ───────────────────────────────────────────────

    def test_relationships_200(self):
        client = self._client()
        r = client.get("/api/relationships")
        self.assertEqual(r.status_code, 200)

    def test_relationships_has_structure(self):
        cache = _make_cache(
            events=[_event("E", "email", days_ago=1, metadata={"from": "alice@co.com"})]
        )
        client = self._client(cache)
        data = client.get("/api/relationships").json()
        self.assertIn("total_contacts", data)
        self.assertIn("top_contacts", data)
        self.assertIn("dormant_contacts", data)

    # ── /api/time-audit ──────────────────────────────────────────────────

    def test_time_audit_200(self):
        client = self._client()
        r = client.get("/api/time-audit")
        self.assertEqual(r.status_code, 200)

    def test_time_audit_has_categories(self):
        cache = _make_cache(events=[_event("Meeting", "calendar", days_ago=1)])
        client = self._client(cache)
        data = client.get("/api/time-audit").json()
        self.assertIn("category_totals", data)
        self.assertIn("meeting_overload", data)
        self.assertIn("daily", data)

    # ── /api/trends ──────────────────────────────────────────────────────

    def test_trends_200(self):
        client = self._client()
        r = client.get("/api/trends")
        self.assertEqual(r.status_code, 200)

    def test_trends_has_alerts(self):
        cache = _make_cache(events=[_event(source_type="github", days_ago=i) for i in range(1, 10)])
        client = self._client(cache)
        data = client.get("/api/trends").json()
        self.assertIn("alerts", data)
        self.assertIn("source_trends", data)
        self.assertIn("rolling_baseline", data)

    def test_trends_empty_cache(self):
        client = self._client(_make_cache())
        data = client.get("/api/trends").json()
        self.assertEqual(data["alerts"], [])

    # ── router registration ──────────────────────────────────────────────

    def test_router_has_correct_routes(self):
        import src.advanced.api as adv_api
        route_paths = {r.path for r in adv_api.router.routes}
        assert "/briefing" in route_paths
        assert "/actions" in route_paths
        assert "/retrospective" in route_paths
        assert "/relationships" in route_paths
        assert "/time-audit" in route_paths
        assert "/trends" in route_paths


if __name__ == "__main__":
    unittest.main()
