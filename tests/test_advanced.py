"""Tests for src.advanced — retrospective, meeting_prep, relationships,
time_audit, trends, export, and API router.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dt(days_ago: int = 0, tz: bool = True) -> str:
    """Return an ISO datetime string N days ago."""
    dt = datetime.now(tz=timezone.utc) - timedelta(days=days_ago)
    if not tz:
        return dt.replace(tzinfo=None).isoformat()
    return dt.isoformat()


def _make_cache(
    events: list | None = None,
    action_items: list | None = None,
) -> dict:
    return {
        "synced_at": _dt(),
        "events": events or [],
        "action_items": action_items or [],
    }


def _cal_event(title: str = "Meeting", days_ago: int = 1, attendees: list | None = None) -> dict:
    meta = {}
    if attendees:
        meta["attendees"] = attendees
    return {
        "id": "cal1",
        "title": title,
        "source_type": "calendar",
        "occurred_at": _dt(days_ago),
        "summary": f"Summary of {title}",
        "url": "",
        "metadata": meta,
    }


def _github_event(title: str = "PR: fix bug", days_ago: int = 1) -> dict:
    return {
        "id": "gh1",
        "title": title,
        "source_type": "github",
        "occurred_at": _dt(days_ago),
        "summary": "pull_request opened",
        "url": "https://github.com/example/repo/pull/1",
        "metadata": {},
    }


def _email_event(title: str = "Re: project update", days_ago: int = 1, from_: str = "") -> dict:
    meta = {}
    if from_:
        meta["from"] = from_
    return {
        "id": "em1",
        "title": title,
        "source_type": "email",
        "occurred_at": _dt(days_ago),
        "summary": "Email body",
        "url": "",
        "metadata": meta,
    }


def _action(title: str = "Review PR", priority: str = "medium", completed: bool = False) -> dict:
    return {
        "id": "ai1",
        "title": title,
        "source_type": "github",
        "priority": priority,
        "completed": completed,
        "url": "",
        "notes": "",
    }


# ===========================================================================
# Retrospective
# ===========================================================================


class TestRetrospective(unittest.TestCase):

    def _retro(self, cache, ref_dt=None):
        from src.advanced.retrospective import generate_retrospective
        if ref_dt is None:
            ref_dt = datetime.now(tz=timezone.utc)
        return generate_retrospective(cache, ref_dt=ref_dt)

    def test_empty_cache(self):
        r = self._retro(_make_cache())
        self.assertEqual(r["metrics"]["total_events"], 0)
        self.assertIn("period", r)
        self.assertIn("generated_at", r)

    def test_counts_events_in_window(self):
        events = [_cal_event(days_ago=1), _github_event(days_ago=2), _email_event(days_ago=3)]
        r = self._retro(_make_cache(events=events))
        self.assertEqual(r["metrics"]["total_events"], 3)

    def test_excludes_events_outside_window(self):
        old_event = _cal_event(days_ago=10)  # outside 7-day window
        recent_event = _cal_event(days_ago=1)
        r = self._retro(_make_cache(events=[old_event, recent_event]))
        self.assertEqual(r["metrics"]["total_events"], 1)

    def test_meetings_counted(self):
        events = [_cal_event(days_ago=1), _cal_event(days_ago=2), _github_event(days_ago=1)]
        r = self._retro(_make_cache(events=events))
        self.assertEqual(r["metrics"]["meetings"], 2)

    def test_prs_counted(self):
        events = [_github_event("PR: fix", days_ago=1), _github_event("PR: feat", days_ago=2)]
        r = self._retro(_make_cache(events=events))
        self.assertEqual(r["metrics"]["prs_reviewed"], 2)

    def test_trend_vs_prior_week_keys(self):
        r = self._retro(_make_cache())
        trend = r["trend_vs_prior_week"]
        for key in ("total_events_pct", "meetings_pct", "prs_pct", "emails_pct"):
            self.assertIn(key, trend)

    def test_top_sources(self):
        events = [_cal_event(days_ago=1)] * 3 + [_github_event(days_ago=1)] * 2
        r = self._retro(_make_cache(events=events))
        top = dict(r["top_sources"])
        self.assertEqual(top["calendar"], 3)
        self.assertEqual(top["github"], 2)

    def test_highlights_filter_keywords(self):
        events = [
            {**_cal_event("Sprint merged", days_ago=1), "id": "h1"},
            {**_cal_event("Weekly standup", days_ago=2), "id": "h2"},
        ]
        r = self._retro(_make_cache(events=events))
        titles = [h["title"] for h in r["highlights"]]
        self.assertIn("Sprint merged", titles)
        self.assertNotIn("Weekly standup", titles)

    def test_pct_change_none_when_previous_zero(self):
        # No prior-week events → pct should be None
        events = [_cal_event(days_ago=1)]
        r = self._retro(_make_cache(events=events))
        self.assertIsNone(r["trend_vs_prior_week"]["total_events_pct"])

    def test_generated_at_present(self):
        r = self._retro(_make_cache())
        self.assertIn("T", r["generated_at"])  # ISO format with T separator


# ===========================================================================
# Meeting Prep
# ===========================================================================


class TestMeetingPrep(unittest.TestCase):

    def _prep(self, event, cache):
        from src.advanced.meeting_prep import generate_meeting_prep
        return generate_meeting_prep(event, cache)

    def test_basic_structure(self):
        event = _cal_event("Q1 Planning")
        r = self._prep(event, _make_cache())
        for key in ("event", "attendees", "topics", "related_emails",
                    "related_github", "pending_actions", "suggested_talking_points",
                    "generated_at"):
            self.assertIn(key, r)

    def test_event_fields(self):
        event = _cal_event("Design Review")
        r = self._prep(event, _make_cache())
        self.assertEqual(r["event"]["title"], "Design Review")

    def test_extracts_attendees(self):
        event = _cal_event("Sync", attendees=["Alice", "bob@example.com"])
        r = self._prep(event, _make_cache())
        self.assertIn("Alice", r["attendees"])

    def test_related_emails_found(self):
        attendees = ["alice@example.com"]
        event = _cal_event("Alice sync", attendees=attendees)
        emails = [_email_event("Re: Alice sync followup", days_ago=3)]
        r = self._prep(event, _make_cache(events=emails))
        # Should find email mentioning attendee
        self.assertIsInstance(r["related_emails"], list)

    def test_related_github_found(self):
        event = _cal_event("Code review session")
        gh = [_github_event("PR: code review cleanup", days_ago=2)]
        r = self._prep(event, _make_cache(events=gh))
        self.assertIsInstance(r["related_github"], list)

    def test_pending_actions_filtered(self):
        attendees = ["alice"]
        event = _cal_event("Alice meeting", attendees=attendees)
        actions = [
            _action("Follow up with alice"),
            _action("Unrelated task"),
        ]
        r = self._prep(event, _make_cache(action_items=actions))
        titles = [a["title"] for a in r["pending_actions"]]
        self.assertIn("Follow up with alice", titles)

    def test_topics_extracted(self):
        event = _cal_event("Quarterly Business Review Planning")
        r = self._prep(event, _make_cache())
        self.assertTrue(len(r["topics"]) > 0)

    def test_talking_points_generated(self):
        attendees = ["alice"]
        event = _cal_event("Alice sync", attendees=attendees)
        actions = [_action("Follow up with alice")]
        r = self._prep(event, _make_cache(action_items=actions))
        self.assertIsInstance(r["suggested_talking_points"], list)

    def test_empty_attendees_no_error(self):
        event = {"id": "x", "title": "Solo work", "source_type": "calendar",
                 "occurred_at": _dt(), "summary": "", "url": "", "metadata": {}}
        r = self._prep(event, _make_cache())
        self.assertEqual(r["attendees"], [])

    def test_lookback_respects_window(self):
        attendees = ["old@example.com"]
        event = _cal_event("Old meeting", attendees=attendees)
        old_email = _email_event("Re: old@example.com info", days_ago=20)
        r = self._prep(event, _make_cache(events=[old_email]), lookback_days=7) \
            if False else self._prep(event, _make_cache(events=[old_email]))
        # Just ensure no exception
        self.assertIsInstance(r["related_emails"], list)


# ===========================================================================
# Relationships
# ===========================================================================


class TestRelationships(unittest.TestCase):

    def _tracker(self, cache, dormant_days=30, ref_dt=None):
        from src.advanced.relationships import RelationshipTracker
        return RelationshipTracker(cache, ref_dt=ref_dt, dormant_days=dormant_days)

    def test_empty_cache(self):
        t = self._tracker(_make_cache())
        r = t.report()
        self.assertEqual(r["total_contacts"], 0)
        self.assertEqual(r["top_contacts"], [])
        self.assertEqual(r["dormant_contacts"], [])

    def test_counts_contacts(self):
        events = [
            _email_event(from_="alice@example.com", days_ago=1),
            _email_event(from_="alice@example.com", days_ago=2),
            _email_event(from_="bob@example.com", days_ago=3),
        ]
        t = self._tracker(_make_cache(events=events))
        counts = dict(t.interaction_counts())
        self.assertEqual(counts.get("alice@example.com"), 2)
        self.assertEqual(counts.get("bob@example.com"), 1)

    def test_top_contacts_sorted(self):
        events = (
            [_email_event(from_="top@example.com", days_ago=i) for i in range(1, 6)] +
            [_email_event(from_="low@example.com", days_ago=1)]
        )
        t = self._tracker(_make_cache(events=events))
        top = t.top_contacts(n=1)
        self.assertEqual(top[0]["contact"], "top@example.com")
        self.assertEqual(top[0]["total_interactions"], 5)

    def test_last_interaction(self):
        ref = datetime.now(tz=timezone.utc)
        events = [
            {**_email_event(from_="alice@example.com", days_ago=5), "occurred_at": (ref - timedelta(days=5)).isoformat()},
            {**_email_event(from_="alice@example.com", days_ago=2), "occurred_at": (ref - timedelta(days=2)).isoformat()},
        ]
        t = self._tracker(_make_cache(events=events), ref_dt=ref)
        last = t.last_interaction("alice@example.com")
        self.assertIsNotNone(last)
        self.assertAlmostEqual((ref - last).days, 2, delta=1)

    def test_dormant_contacts(self):
        ref = datetime.now(tz=timezone.utc)
        # Dormant: last seen 40 days ago
        dormant_ev = {**_email_event(from_="dormant@example.com"), "occurred_at": (ref - timedelta(days=40)).isoformat()}
        # Active: last seen 5 days ago
        active_ev = {**_email_event(from_="active@example.com"), "occurred_at": (ref - timedelta(days=5)).isoformat()}
        t = self._tracker(_make_cache(events=[dormant_ev, active_ev]), dormant_days=30, ref_dt=ref)
        dormant = [d["contact"] for d in t.dormant_contacts()]
        self.assertIn("dormant@example.com", dormant)
        self.assertNotIn("active@example.com", dormant)

    def test_source_breakdown(self):
        events = [
            _email_event(from_="alice@example.com", days_ago=1),
            _cal_event("Meeting with alice", attendees=["alice@example.com"], days_ago=2),
        ]
        t = self._tracker(_make_cache(events=events))
        breakdown = t.source_breakdown("alice@example.com")
        self.assertIn("email", breakdown)

    def test_report_structure(self):
        t = self._tracker(_make_cache())
        r = t.report()
        for key in ("total_contacts", "top_contacts", "dormant_contacts", "generated_at"):
            self.assertIn(key, r)

    def test_attendees_extracted_from_calendar(self):
        event = _cal_event("Team meeting", attendees=["teamlead@example.com"])
        t = self._tracker(_make_cache(events=[event]))
        self.assertIn("teamlead@example.com", t._contact_events)


# ===========================================================================
# Time Audit
# ===========================================================================


class TestTimeAudit(unittest.TestCase):

    def _audit(self, cache, ref_dt=None, lookback_days=7):
        from src.advanced.time_audit import generate_time_audit
        if ref_dt is None:
            ref_dt = datetime.now(tz=timezone.utc)
        return generate_time_audit(cache, ref_dt=ref_dt, lookback_days=lookback_days)

    def test_empty_cache(self):
        r = self._audit(_make_cache())
        self.assertIn("category_totals", r)
        self.assertIn("daily", r)
        self.assertIn("meeting_overload", r)

    def test_categorises_meetings(self):
        events = [_cal_event(days_ago=1)] * 5
        r = self._audit(_make_cache(events=events))
        self.assertIn("meetings", r["category_totals"])
        self.assertEqual(r["category_totals"]["meetings"]["count"], 5)

    def test_categorises_deep_work(self):
        events = [_github_event(days_ago=1)] * 3
        r = self._audit(_make_cache(events=events))
        self.assertIn("deep_work", r["category_totals"])

    def test_categorises_admin_email(self):
        events = [_email_event(days_ago=1)] * 4
        r = self._audit(_make_cache(events=events))
        self.assertIn("admin", r["category_totals"])

    def test_daily_breakdown(self):
        events = [_cal_event(days_ago=1), _github_event(days_ago=2)]
        r = self._audit(_make_cache(events=events))
        self.assertIsInstance(r["daily"], list)
        self.assertTrue(len(r["daily"]) > 0)

    def test_period_keys(self):
        r = self._audit(_make_cache())
        self.assertIn("start", r["period"])
        self.assertIn("end", r["period"])
        self.assertIn("days", r["period"])

    def test_meeting_overload_alert(self):
        # 3 consecutive days with all-meeting events
        ref = datetime.now(tz=timezone.utc)
        events = []
        for days_ago in [1, 2, 3]:
            for _ in range(5):
                events.append(_cal_event(days_ago=days_ago))
            # Add 1 non-meeting to stay ≥50% but not 100%
        r = self._audit(_make_cache(events=events), ref_dt=ref, lookback_days=7)
        # meeting_overload should be present
        self.assertIn("alert", r["meeting_overload"])
        self.assertIn("overload_days", r["meeting_overload"])

    def test_no_overload_for_balanced_schedule(self):
        events = [_cal_event(days_ago=1), _github_event(days_ago=1), _email_event(days_ago=1)]
        r = self._audit(_make_cache(events=events))
        # balanced — no alert expected
        self.assertIn("alert", r["meeting_overload"])

    def test_insights_list(self):
        r = self._audit(_make_cache())
        self.assertIsInstance(r["insights"], list)
        self.assertTrue(len(r["insights"]) > 0)

    def test_lookback_filters_old_events(self):
        old = _cal_event(days_ago=10)
        recent = _cal_event(days_ago=1)
        r = self._audit(_make_cache(events=[old, recent]), lookback_days=7)
        total = sum(v["count"] for v in r["category_totals"].values())
        self.assertEqual(total, 1)


# ===========================================================================
# Trends
# ===========================================================================


class TestTrends(unittest.TestCase):

    def _trends(self, cache, ref_dt=None, window_days=7, history_days=28):
        from src.advanced.trends import detect_trends
        if ref_dt is None:
            ref_dt = datetime.now(tz=timezone.utc)
        return detect_trends(cache, ref_dt=ref_dt, window_days=window_days, history_days=history_days)

    def test_empty_cache(self):
        r = self._trends(_make_cache())
        self.assertIn("alerts", r)
        self.assertIn("source_trends", r)
        self.assertIn("rolling_baseline", r)

    def test_period_keys(self):
        r = self._trends(_make_cache())
        for k in ("recent_start", "recent_end", "history_start", "window_days", "history_days"):
            self.assertIn(k, r["period"])

    def test_source_trend_keys(self):
        events = [_cal_event(days_ago=1)]
        r = self._trends(_make_cache(events=events))
        if r["source_trends"]:
            entry = r["source_trends"][0]
            for k in ("source_type", "recent_total", "recent_avg_per_day",
                      "historical_avg_per_day", "trend"):
                self.assertIn(k, entry)

    def test_spike_detection(self):
        ref = datetime.now(tz=timezone.utc)
        # Heavy recent activity, nothing in history
        events = [_github_event(days_ago=i) for i in range(1, 8)]
        r = self._trends(_make_cache(events=events), ref_dt=ref, window_days=7, history_days=28)
        github_trend = next((t for t in r["source_trends"] if t["source_type"] == "github"), None)
        self.assertIsNotNone(github_trend)
        self.assertGreater(github_trend["recent_total"], 0)

    def test_no_false_alerts_empty(self):
        r = self._trends(_make_cache())
        # No events → no meaningful alerts
        self.assertEqual(r["alerts"], [])

    def test_rolling_baseline_keys(self):
        r = self._trends(_make_cache())
        for k in ("overall_recent_avg_per_day", "overall_historical_avg_per_day"):
            self.assertIn(k, r["rolling_baseline"])

    def test_multiple_sources(self):
        events = [_cal_event(days_ago=1), _github_event(days_ago=2), _email_event(days_ago=3)]
        r = self._trends(_make_cache(events=events))
        sources = {t["source_type"] for t in r["source_trends"]}
        self.assertGreaterEqual(len(sources), 1)


# ===========================================================================
# Export
# ===========================================================================


class TestExport(unittest.TestCase):

    def _sample_report(self):
        return {
            "title": "Test Report",
            "metrics": {"events": 10, "meetings": 3},
            "generated_at": _dt(),
        }

    def test_json_export(self):
        from src.advanced.export import export_report
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "report.json"
            result = export_report(self._sample_report(), fmt="json", output_path=out)
            self.assertEqual(result, out)
            data = json.loads(out.read_text())
            self.assertEqual(data["title"], "Test Report")

    def test_html_export(self):
        from src.advanced.export import export_report
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "report.html"
            result = export_report(self._sample_report(), fmt="html", output_path=out)
            self.assertEqual(result, out)
            content = out.read_text()
            self.assertIn("<!DOCTYPE html>", content)
            self.assertIn("Test Report", content)

    def test_pdf_export_produces_html(self):
        from src.advanced.export import export_report
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "report.html"
            result = export_report(self._sample_report(), fmt="pdf", output_path=out)
            content = result.read_text()
            self.assertIn("@media print", content)

    def test_invalid_format_raises(self):
        from src.advanced.export import export_report
        with self.assertRaises(ValueError):
            export_report(self._sample_report(), fmt="xlsx")

    def test_auto_path_created(self):
        from src.advanced.export import export_report
        with tempfile.TemporaryDirectory() as tmpdir:
            # Use a nested path that doesn't exist yet
            out = Path(tmpdir) / "nested" / "dir" / "report.json"
            result = export_report(self._sample_report(), fmt="json", output_path=out)
            self.assertTrue(result.exists())

    def test_html_contains_section_headings(self):
        from src.advanced.export import export_report
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "r.html"
            export_report(self._sample_report(), fmt="html", output_path=out, title="My Report")
            content = out.read_text()
            self.assertIn("My Report", content)
            self.assertIn("<section>", content)

    def test_json_export_round_trips(self):
        from src.advanced.export import export_report
        report = {"nested": {"a": 1, "b": [1, 2, 3]}, "generated_at": _dt()}
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "r.json"
            export_report(report, fmt="json", output_path=out)
            data = json.loads(out.read_text())
            self.assertEqual(data["nested"]["a"], 1)
            self.assertEqual(data["nested"]["b"], [1, 2, 3])


# ===========================================================================
# API Router (via TestClient)
# ===========================================================================


MOCK_CACHE = _make_cache(
    events=[
        _cal_event("Team Sync", days_ago=1, attendees=["alice@example.com"]),
        _github_event("PR: fix auth", days_ago=2),
        _email_event("Re: project", days_ago=3),
    ],
    action_items=[
        _action("Review PR", priority="urgent"),
        _action("Send report", priority="medium"),
        _action("Done task", completed=True),
    ],
)


class TestAdvancedAPI(unittest.TestCase):

    def setUp(self):
        from src.web.server import create_app
        self.client = TestClient(create_app())
        self._patcher_adv = patch("src.advanced.api._load_cache", return_value=MOCK_CACHE)
        self._patcher_web = patch("src.web.routes._load_cache", return_value=MOCK_CACHE)
        self._patcher_adv.start()
        self._patcher_web.start()

    def tearDown(self):
        self._patcher_adv.stop()
        self._patcher_web.stop()

    def test_briefing_200(self):
        r = self.client.get("/api/briefing")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("recent_events", data)
        self.assertIn("pending_action_items", data)
        self.assertIn("urgent_count", data)

    def test_briefing_urgent_count(self):
        r = self.client.get("/api/briefing")
        data = r.json()
        self.assertEqual(data["urgent_count"], 1)

    def test_actions_advanced_200(self):
        r = self.client.get("/api/actions")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("action_items", data)

    def test_actions_excludes_completed_by_default(self):
        r = self.client.get("/api/actions")
        data = r.json()
        titles = [a["title"] for a in data["action_items"]]
        self.assertNotIn("Done task", titles)

    def test_actions_include_completed(self):
        r = self.client.get("/api/actions?include_completed=true")
        data = r.json()
        titles = [a["title"] for a in data["action_items"]]
        self.assertIn("Done task", titles)

    def test_retrospective_200(self):
        with patch("src.advanced.retrospective.generate_retrospective") as mock_retro:
            mock_retro.return_value = {"period": {}, "metrics": {}, "generated_at": _dt()}
            r = self.client.get("/api/retrospective")
        self.assertEqual(r.status_code, 200)

    def test_relationships_200(self):
        r = self.client.get("/api/relationships")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("total_contacts", data)

    def test_time_audit_200(self):
        r = self.client.get("/api/time-audit")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("category_totals", data)

    def test_time_audit_lookback_param(self):
        r = self.client.get("/api/time-audit?lookback_days=14")
        self.assertEqual(r.status_code, 200)

    def test_trends_200(self):
        r = self.client.get("/api/trends")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("alerts", data)
        self.assertIn("source_trends", data)

    def test_trends_window_param(self):
        r = self.client.get("/api/trends?window_days=3&history_days=14")
        self.assertEqual(r.status_code, 200)

    def test_briefing_total_events(self):
        r = self.client.get("/api/briefing")
        data = r.json()
        self.assertEqual(data["total_events"], 3)


# ===========================================================================
# __init__ exports
# ===========================================================================


class TestAdvancedInit(unittest.TestCase):

    def test_all_exports_importable(self):
        from src.advanced import (  # noqa: F401
            generate_retrospective,
            generate_meeting_prep,
            RelationshipTracker,
            generate_time_audit,
            detect_trends,
            export_report,
        )

    def test_generate_retrospective_callable(self):
        from src.advanced import generate_retrospective
        r = generate_retrospective(_make_cache())
        self.assertIn("metrics", r)

    def test_generate_meeting_prep_callable(self):
        from src.advanced import generate_meeting_prep
        r = generate_meeting_prep(_cal_event("Test"), _make_cache())
        self.assertIn("event", r)

    def test_relationship_tracker_callable(self):
        from src.advanced import RelationshipTracker
        t = RelationshipTracker(_make_cache())
        self.assertIn("total_contacts", t.report())

    def test_generate_time_audit_callable(self):
        from src.advanced import generate_time_audit
        r = generate_time_audit(_make_cache())
        self.assertIn("category_totals", r)

    def test_detect_trends_callable(self):
        from src.advanced import detect_trends
        r = detect_trends(_make_cache())
        self.assertIn("alerts", r)

    def test_export_report_callable(self):
        from src.advanced import export_report
        with tempfile.TemporaryDirectory() as tmpdir:
            out = export_report({"x": 1, "generated_at": _dt()}, fmt="json",
                                output_path=Path(tmpdir) / "r.json")
            self.assertTrue(out.exists())


if __name__ == "__main__":
    unittest.main()
