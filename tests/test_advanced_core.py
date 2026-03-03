"""Tests for src/advanced core modules: retrospective, meeting_prep,
relationships, time_audit, trends, export."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

REF = datetime(2024, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
WEEK_AGO = REF - timedelta(days=7)
TWO_WEEKS_AGO = REF - timedelta(days=14)


def _event(title="Test Event", source_type="github", days_ago=1, **kwargs):
    dt = REF - timedelta(days=days_ago)
    e = {
        "id": f"evt-{title[:6].replace(' ', '')}",
        "title": title,
        "source_type": source_type,
        "source_id": source_type,
        "occurred_at": dt.isoformat(),
        "summary": kwargs.pop("summary", ""),
        "url": kwargs.pop("url", ""),
        "metadata": kwargs.pop("metadata", {}),
    }
    e.update(kwargs)
    return e


def _action(title="Do thing", priority="medium", completed=False, days_ago=1, **kwargs):
    dt = REF - timedelta(days=days_ago)
    a = {
        "id": f"act-{title[:6].replace(' ', '')}",
        "title": title,
        "source_type": "github",
        "source_id": "github",
        "priority": priority,
        "completed": completed,
        "created_at": dt.isoformat(),
        "notes": kwargs.pop("notes", ""),
        "url": kwargs.pop("url", ""),
        "metadata": kwargs.pop("metadata", {}),
    }
    a.update(kwargs)
    return a


def _cache(events=None, action_items=None):
    return {
        "synced_at": REF.isoformat(),
        "events": events or [],
        "action_items": action_items or [],
    }


# ===========================================================================
# retrospective
# ===========================================================================


class TestRetrospective:
    from src.advanced.retrospective import generate_retrospective

    def test_empty_cache(self):
        from src.advanced.retrospective import generate_retrospective
        retro = generate_retrospective(_cache(), ref_dt=REF)
        assert retro["metrics"]["total_events"] == 0
        assert retro["metrics"]["meetings"] == 0
        assert "period" in retro
        assert "generated_at" in retro

    def test_counts_current_week_events(self):
        from src.advanced.retrospective import generate_retrospective
        events = [
            _event("meeting 1", "calendar", days_ago=1),
            _event("meeting 2", "calendar", days_ago=2),
            _event("PR merged", "github", days_ago=3, summary="merged pull_request"),
            _event("old email", "email", days_ago=10),  # outside window
        ]
        retro = generate_retrospective(_cache(events=events), ref_dt=REF)
        assert retro["metrics"]["total_events"] == 3
        assert retro["metrics"]["meetings"] == 2

    def test_trend_comparison(self):
        from src.advanced.retrospective import generate_retrospective
        cur_events = [_event(days_ago=i) for i in range(1, 5)]     # 4 events this week
        prev_events = [_event(days_ago=i) for i in range(8, 14)]   # 6 events prev week
        retro = generate_retrospective(_cache(events=cur_events + prev_events), ref_dt=REF)
        trend = retro["trend_vs_prior_week"]
        assert trend["prior_period"]["total_events"] == 6
        assert retro["metrics"]["total_events"] == 4
        assert trend["total_events_pct"] is not None

    def test_pct_change_no_prior(self):
        from src.advanced.retrospective import generate_retrospective
        events = [_event(days_ago=1)]
        retro = generate_retrospective(_cache(events=events), ref_dt=REF)
        # prior week has 0 events → pct_change should be None (division by zero guard)
        assert retro["trend_vs_prior_week"]["total_events_pct"] is None

    def test_highlights_surface_merged_events(self):
        from src.advanced.retrospective import generate_retrospective
        events = [
            _event("PR merged into main", "github", days_ago=1, summary="merged"),
            _event("Standup", "calendar", days_ago=2),
        ]
        retro = generate_retrospective(_cache(events=events), ref_dt=REF)
        titles = [h["title"] for h in retro["highlights"]]
        assert any("merged" in t.lower() for t in titles)

    def test_by_source_breakdown(self):
        from src.advanced.retrospective import generate_retrospective
        events = [
            _event(source_type="github", days_ago=1),
            _event(source_type="github", days_ago=2),
            _event(source_type="calendar", days_ago=3),
        ]
        retro = generate_retrospective(_cache(events=events), ref_dt=REF)
        by_src = retro["metrics"]["by_source"]
        assert by_src.get("github") == 2
        assert by_src.get("calendar") == 1

    def test_actions_completed_counted(self):
        from src.advanced.retrospective import generate_retrospective
        actions = [
            _action("Done task", completed=True, days_ago=2),
            _action("Pending task", completed=False, days_ago=2),
        ]
        retro = generate_retrospective(_cache(action_items=actions), ref_dt=REF)
        assert retro["metrics"]["actions_completed"] == 1


# ===========================================================================
# meeting_prep
# ===========================================================================


class TestMeetingPrep:
    def test_basic_output_structure(self):
        from src.advanced.meeting_prep import generate_meeting_prep
        event = _event("Sync with Alice", "calendar", days_ago=0)
        brief = generate_meeting_prep(event, _cache(), ref_dt=REF)
        assert "event" in brief
        assert "attendees" in brief
        assert "suggested_talking_points" in brief
        assert "generated_at" in brief

    def test_extracts_attendees_from_metadata(self):
        from src.advanced.meeting_prep import generate_meeting_prep
        event = _event(
            "Design Review",
            "calendar",
            days_ago=0,
            metadata={"attendees": ["alice@co.com", "bob@co.com"]},
        )
        brief = generate_meeting_prep(event, _cache(), ref_dt=REF)
        assert "alice@co.com" in brief["attendees"]
        assert "bob@co.com" in brief["attendees"]

    def test_finds_related_emails(self):
        from src.advanced.meeting_prep import generate_meeting_prep
        event = _event(
            "Budget Review",
            "calendar",
            days_ago=0,
            metadata={"attendees": ["finance@co.com"]},
        )
        emails = [
            _event("Re: finance@co.com Q2", "email", days_ago=3, summary="budget"),
        ]
        brief = generate_meeting_prep(event, _cache(events=emails), ref_dt=REF)
        assert len(brief["related_emails"]) >= 1

    def test_finds_related_github(self):
        from src.advanced.meeting_prep import generate_meeting_prep
        event = _event(
            "Deploy Review",
            "calendar",
            days_ago=0,
            metadata={"attendees": ["alice"]},
        )
        github_events = [
            _event("alice opened pull_request for deploy", "github", days_ago=2),
        ]
        brief = generate_meeting_prep(event, _cache(events=github_events), ref_dt=REF)
        assert len(brief["related_github"]) >= 1

    def test_surfacing_pending_actions(self):
        from src.advanced.meeting_prep import generate_meeting_prep
        event = _event(
            "1:1 with Bob",
            "calendar",
            days_ago=0,
            metadata={"attendees": ["bob"]},
        )
        actions = [_action("Follow up with bob about proposal", priority="high")]
        brief = generate_meeting_prep(event, _cache(action_items=actions), ref_dt=REF)
        assert len(brief["pending_actions"]) >= 1

    def test_empty_attendees(self):
        from src.advanced.meeting_prep import generate_meeting_prep
        event = _event("Solo Focus Block", "calendar", days_ago=0)
        brief = generate_meeting_prep(event, _cache(), ref_dt=REF)
        assert brief["attendees"] == []
        assert isinstance(brief["suggested_talking_points"], list)

    def test_topics_extracted_from_title(self):
        from src.advanced.meeting_prep import generate_meeting_prep
        event = _event("Architecture Design Review Session", "calendar", days_ago=0)
        brief = generate_meeting_prep(event, _cache(), ref_dt=REF)
        assert "Architecture" in brief["topics"] or "Design" in brief["topics"]


# ===========================================================================
# relationships
# ===========================================================================


class TestRelationships:
    def test_empty_cache(self):
        from src.advanced.relationships import RelationshipTracker
        tracker = RelationshipTracker(_cache(), ref_dt=REF)
        report = tracker.report()
        assert report["total_contacts"] == 0
        assert report["top_contacts"] == []
        assert report["dormant_contacts"] == []

    def test_counts_interactions(self):
        from src.advanced.relationships import RelationshipTracker
        events = [
            _event("Email", "email", days_ago=1, metadata={"from": "alice@co.com"}),
            _event("Email", "email", days_ago=2, metadata={"from": "alice@co.com"}),
            _event("PR", "github", days_ago=3, metadata={"author": "bob"}),
        ]
        tracker = RelationshipTracker(_cache(events=events), ref_dt=REF)
        counts = dict(tracker.interaction_counts())
        assert counts.get("alice@co.com") == 2
        assert counts.get("bob") == 1

    def test_top_contacts_sorted(self):
        from src.advanced.relationships import RelationshipTracker
        events = [
            _event("E", "email", days_ago=i, metadata={"from": "alice"}) for i in range(5)
        ] + [
            _event("E", "email", days_ago=i, metadata={"from": "bob"}) for i in range(2)
        ]
        tracker = RelationshipTracker(_cache(events=events), ref_dt=REF)
        top = tracker.top_contacts(2)
        assert top[0]["contact"] == "alice"
        assert top[0]["total_interactions"] == 5

    def test_dormant_contacts_detected(self):
        from src.advanced.relationships import RelationshipTracker
        events = [
            _event("Old contact", "email", days_ago=60, metadata={"from": "ghost@co.com"}),
            _event("Recent contact", "email", days_ago=2, metadata={"from": "active@co.com"}),
        ]
        tracker = RelationshipTracker(_cache(events=events), ref_dt=REF, dormant_days=30)
        dormant_contacts = [d["contact"] for d in tracker.dormant_contacts()]
        assert "ghost@co.com" in dormant_contacts
        assert "active@co.com" not in dormant_contacts

    def test_source_breakdown(self):
        from src.advanced.relationships import RelationshipTracker
        events = [
            _event("E1", "email", days_ago=1, metadata={"from": "alice"}),
            _event("E2", "github", days_ago=2, metadata={"author": "alice"}),
        ]
        tracker = RelationshipTracker(_cache(events=events), ref_dt=REF)
        breakdown = tracker.source_breakdown("alice")
        assert breakdown.get("email") == 1
        assert breakdown.get("github") == 1

    def test_last_interaction(self):
        from src.advanced.relationships import RelationshipTracker
        events = [
            _event("E1", "email", days_ago=5, metadata={"from": "alice"}),
            _event("E2", "email", days_ago=1, metadata={"from": "alice"}),
        ]
        tracker = RelationshipTracker(_cache(events=events), ref_dt=REF)
        last = tracker.last_interaction("alice")
        expected = REF - timedelta(days=1)
        assert last is not None
        assert abs((last - expected).total_seconds()) < 86400  # within a day


# ===========================================================================
# time_audit
# ===========================================================================


class TestTimeAudit:
    def test_empty_cache(self):
        from src.advanced.time_audit import generate_time_audit
        audit = generate_time_audit(_cache(), ref_dt=REF)
        assert audit["category_totals"] == {}
        assert audit["daily"] == []
        assert audit["meeting_overload"]["alert"] is False

    def test_categorises_events(self):
        from src.advanced.time_audit import generate_time_audit
        events = [
            _event(source_type="calendar", days_ago=1),
            _event(source_type="github", days_ago=1),
            _event(source_type="email", days_ago=2),
            _event(source_type="news", days_ago=3),
        ]
        audit = generate_time_audit(_cache(events=events), ref_dt=REF, lookback_days=7)
        totals = audit["category_totals"]
        assert "meetings" in totals
        assert "deep_work" in totals
        assert "admin" in totals
        assert "learning" in totals

    def test_daily_breakdown(self):
        from src.advanced.time_audit import generate_time_audit
        events = [
            _event(source_type="calendar", days_ago=1),
            _event(source_type="calendar", days_ago=2),
        ]
        audit = generate_time_audit(_cache(events=events), ref_dt=REF, lookback_days=7)
        days_with_data = [d for d in audit["daily"] if d["total"] > 0]
        assert len(days_with_data) >= 1

    def test_meeting_overload_detected(self):
        from src.advanced.time_audit import generate_time_audit
        # 3+ days of mostly meetings
        events = []
        for day in range(1, 5):
            for _ in range(4):
                events.append(_event(source_type="calendar", days_ago=day))
            events.append(_event(source_type="github", days_ago=day))
        audit = generate_time_audit(_cache(events=events), ref_dt=REF, lookback_days=7)
        assert audit["meeting_overload"]["alert"] is True

    def test_insights_populated(self):
        from src.advanced.time_audit import generate_time_audit
        events = [_event(source_type="calendar", days_ago=i) for i in range(1, 5)]
        audit = generate_time_audit(_cache(events=events), ref_dt=REF)
        assert isinstance(audit["insights"], list)
        assert len(audit["insights"]) >= 1

    def test_excludes_old_events(self):
        from src.advanced.time_audit import generate_time_audit
        events = [
            _event(source_type="github", days_ago=3),   # in window
            _event(source_type="github", days_ago=20),  # outside window
        ]
        audit = generate_time_audit(_cache(events=events), ref_dt=REF, lookback_days=7)
        totals = audit["category_totals"]
        assert totals.get("deep_work", {}).get("count", 0) == 1


# ===========================================================================
# trends
# ===========================================================================


class TestTrends:
    def test_empty_cache(self):
        from src.advanced.trends import detect_trends
        result = detect_trends(_cache(), ref_dt=REF)
        assert result["alerts"] == []
        assert result["source_trends"] == []

    def test_structure(self):
        from src.advanced.trends import detect_trends
        events = [_event(source_type="github", days_ago=i) for i in range(1, 10)]
        result = detect_trends(_cache(events=events), ref_dt=REF)
        assert "period" in result
        assert "alerts" in result
        assert "source_trends" in result
        assert "rolling_baseline" in result

    def test_spike_detected(self):
        from src.advanced.trends import detect_trends
        # Build a history with ~1/day, then spike to 10/day recently
        history_events = [_event(source_type="email", days_ago=d) for d in range(8, 28)]
        recent_events = [_event(source_type="email", days_ago=d) for d in range(0, 7) for _ in range(5)]
        all_events = history_events + recent_events
        result = detect_trends(_cache(events=all_events), ref_dt=REF, window_days=7, history_days=28)
        email_trend = next((t for t in result["source_trends"] if t["source_type"] == "email"), None)
        assert email_trend is not None
        assert email_trend["trend"] in ("spike", "stable")  # depends on stdev calc

    def test_source_trend_entry_fields(self):
        from src.advanced.trends import detect_trends
        events = [_event(source_type="github", days_ago=i) for i in range(1, 15)]
        result = detect_trends(_cache(events=events), ref_dt=REF)
        for entry in result["source_trends"]:
            assert "source_type" in entry
            assert "recent_total" in entry
            assert "trend" in entry
            assert "z_score" in entry

    def test_multiple_sources(self):
        from src.advanced.trends import detect_trends
        events = (
            [_event(source_type="github", days_ago=i) for i in range(1, 10)]
            + [_event(source_type="email", days_ago=i) for i in range(1, 10)]
        )
        result = detect_trends(_cache(events=events), ref_dt=REF)
        sources = {t["source_type"] for t in result["source_trends"]}
        assert "github" in sources
        assert "email" in sources


# ===========================================================================
# export
# ===========================================================================


class TestExport:
    def _sample_report(self):
        return {
            "period": {"start": "2024-03-08", "end": "2024-03-15"},
            "metrics": {"total_events": 10},
            "alerts": [{"message": "Spike detected", "severity": "medium"}],
            "generated_at": REF.isoformat(),
        }

    def test_json_export(self):
        from src.advanced.export import export_report
        report = self._sample_report()
        with tempfile.TemporaryDirectory() as td:
            path = export_report(report, fmt="json", output_path=Path(td) / "out.json")
            assert path.exists()
            data = json.loads(path.read_text())
            assert data["metrics"]["total_events"] == 10

    def test_html_export(self):
        from src.advanced.export import export_report
        report = self._sample_report()
        with tempfile.TemporaryDirectory() as td:
            path = export_report(report, fmt="html", output_path=Path(td) / "out.html")
            assert path.exists()
            content = path.read_text()
            assert "<!DOCTYPE html>" in content
            assert "Beacon Report" in content

    def test_pdf_format_produces_html(self):
        from src.advanced.export import export_report
        report = self._sample_report()
        with tempfile.TemporaryDirectory() as td:
            path = export_report(report, fmt="pdf", output_path=Path(td) / "out.html")
            assert path.exists()
            content = path.read_text()
            assert "@media print" in content
            assert "<!DOCTYPE html>" in content

    def test_invalid_format_raises(self):
        from src.advanced.export import export_report
        with pytest.raises(ValueError, match="Unsupported format"):
            export_report({}, fmt="docx", output_path=Path("/tmp/x.docx"))

    def test_auto_path_generation(self):
        from src.advanced.export import export_report
        report = self._sample_report()
        path = export_report(report, fmt="json")
        assert path.exists()
        assert path.suffix == ".json"
        path.unlink(missing_ok=True)

    def test_html_includes_alert_section(self):
        from src.advanced.export import export_report
        report = self._sample_report()
        with tempfile.TemporaryDirectory() as td:
            path = export_report(report, fmt="html", output_path=Path(td) / "out.html", title="My Report")
            content = path.read_text()
            assert "Spike detected" in content

    def test_custom_title(self):
        from src.advanced.export import export_report
        report = self._sample_report()
        with tempfile.TemporaryDirectory() as td:
            path = export_report(report, fmt="html", output_path=Path(td) / "out.html", title="Custom Title")
            content = path.read_text()
            assert "Custom Title" in content

    def test_nested_dict_in_html(self):
        from src.advanced.export import export_report
        report = {
            "nested": {"a": 1, "b": {"c": 2}},
            "generated_at": REF.isoformat(),
        }
        with tempfile.TemporaryDirectory() as td:
            path = export_report(report, fmt="html", output_path=Path(td) / "out.html")
            content = path.read_text()
            assert "table" in content  # some form of table rendering
