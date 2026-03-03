"""Tests for src/intelligence/ -- briefing, actions, priority, conflicts, patterns."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.models import ActionItem, Briefing, Event, Priority, SourceType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _make_event(
    title: str = "Test Event",
    source_type: SourceType = SourceType.CALENDAR,
    hours_from_now: float = 1.0,
    summary: str = "",
    url: str = "",
    metadata: dict | None = None,
) -> Event:
    return Event(
        title=title,
        source_id="src-1",
        source_type=source_type,
        occurred_at=_now() + timedelta(hours=hours_from_now),
        summary=summary,
        url=url,
        metadata=metadata or {},
    )


def _make_action(
    title: str = "Test Action",
    priority: Priority = Priority.MEDIUM,
    source_type: SourceType = SourceType.GITHUB,
    hours_until_due: float | None = None,
    completed: bool = False,
    metadata: dict | None = None,
) -> ActionItem:
    due = _now() + timedelta(hours=hours_until_due) if hours_until_due is not None else None
    return ActionItem(
        title=title,
        source_id="src-1",
        source_type=source_type,
        priority=priority,
        due_at=due,
        completed=completed,
        metadata=metadata or {},
    )


def _make_sync_file(events: list[dict], action_items: list[dict]) -> Path:
    """Write a temp sync cache JSON and return the path."""
    data = {
        "synced_at": _now().isoformat(),
        "events": events,
        "action_items": action_items,
    }
    path = Path(tempfile.mktemp(suffix=".json"))
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# ===========================================================================
# BriefingGenerator tests
# ===========================================================================


class TestBriefingGenerator:
    def test_generate_empty(self):
        from src.intelligence.briefing import BriefingGenerator

        gen = BriefingGenerator()
        briefing = gen.generate(events=[], action_items=[])
        assert isinstance(briefing, Briefing)
        assert len(briefing.events) == 0
        assert len(briefing.action_items) == 0
        assert "0 event(s)" in briefing.summary

    def test_generate_with_events(self):
        from src.intelligence.briefing import BriefingGenerator

        events = [
            _make_event("Meeting A", SourceType.CALENDAR),
            _make_event("PR Review", SourceType.GITHUB),
        ]
        gen = BriefingGenerator()
        briefing = gen.generate(events=events, action_items=[])
        assert len(briefing.events) == 2
        assert "calendar" in briefing.sources_synced
        assert "github" in briefing.sources_synced
        assert "2 event(s)" in briefing.summary

    def test_generate_with_actions(self):
        from src.intelligence.briefing import BriefingGenerator

        actions = [
            _make_action("Urgent task", Priority.URGENT),
            _make_action("Normal task", Priority.MEDIUM),
        ]
        gen = BriefingGenerator()
        briefing = gen.generate(events=[], action_items=actions)
        assert len(briefing.action_items) == 2
        assert len(briefing.urgent_actions()) == 1
        assert "1 urgent" in briefing.summary

    def test_generate_from_sync_file(self):
        from src.intelligence.briefing import BriefingGenerator

        sync_path = _make_sync_file(
            events=[{
                "title": "Standup",
                "source_id": "s1",
                "source_type": "calendar",
                "occurred_at": (_now() + timedelta(hours=1)).isoformat(),
                "summary": "",
                "url": "",
                "metadata": {},
            }],
            action_items=[{
                "title": "Review PR #42",
                "source_id": "s1",
                "source_type": "github",
                "priority": "high",
                "due_at": None,
                "url": "",
                "completed": False,
                "notes": "",
                "metadata": {},
            }],
        )
        try:
            gen = BriefingGenerator(sync_path=sync_path)
            briefing = gen.generate()
            assert len(briefing.events) == 1
            assert len(briefing.action_items) == 1
            assert briefing.events[0].title == "Standup"
        finally:
            sync_path.unlink(missing_ok=True)

    def test_generate_no_sync_file(self):
        from src.intelligence.briefing import BriefingGenerator

        gen = BriefingGenerator(sync_path=Path("/nonexistent/path.json"))
        briefing = gen.generate()
        assert len(briefing.events) == 0

    def test_format_text(self):
        from src.intelligence.briefing import BriefingGenerator

        events = [_make_event("Team Standup", SourceType.CALENDAR)]
        actions = [_make_action("Fix bug", Priority.HIGH)]
        gen = BriefingGenerator()
        briefing = gen.generate(events=events, action_items=actions)
        text = gen.format_text(briefing)
        assert "Beacon Briefing" in text
        assert "Team Standup" in text
        assert "Fix bug" in text
        assert "Events" in text
        assert "Action Items" in text

    def test_summary_no_actions(self):
        from src.intelligence.briefing import BriefingGenerator

        gen = BriefingGenerator()
        briefing = gen.generate(events=[_make_event()], action_items=[])
        assert "clear schedule" in briefing.summary.lower()

    def test_summary_urgent(self):
        from src.intelligence.briefing import BriefingGenerator

        gen = BriefingGenerator()
        briefing = gen.generate(events=[], action_items=[
            _make_action("Urgent!", Priority.URGENT),
        ])
        assert "urgent" in briefing.summary.lower()


# ===========================================================================
# ActionExtractor tests
# ===========================================================================


class TestActionExtractor:
    def test_extract_empty(self):
        from src.intelligence.actions import ActionExtractor

        ext = ActionExtractor()
        result = ext.extract([])
        assert result == []

    def test_extract_github_review(self):
        from src.intelligence.actions import ActionExtractor

        ev = _make_event("Review requested: fix auth flow", SourceType.GITHUB)
        ext = ActionExtractor()
        items = ext.extract([ev])
        assert len(items) == 1
        assert "Review" in items[0].title
        assert items[0].priority == Priority.HIGH

    def test_extract_github_assigned(self):
        from src.intelligence.actions import ActionExtractor

        ev = _make_event("Assigned: Deploy new version", SourceType.GITHUB)
        ext = ActionExtractor()
        items = ext.extract([ev])
        assert len(items) == 1
        assert "Respond" in items[0].title

    def test_extract_email_deadline(self):
        from src.intelligence.actions import ActionExtractor

        ev = _make_event("Project deadline approaching", SourceType.EMAIL, summary="due by EOD")
        ext = ActionExtractor()
        items = ext.extract([ev])
        assert len(items) == 1
        assert items[0].priority == Priority.URGENT

    def test_extract_email_action_required(self):
        from src.intelligence.actions import ActionExtractor

        ev = _make_event("Budget approval", SourceType.EMAIL, summary="Action required: approve budget")
        ext = ActionExtractor()
        items = ext.extract([ev])
        assert len(items) == 1
        assert items[0].priority == Priority.HIGH

    def test_extract_calendar_future_meeting(self):
        from src.intelligence.actions import ActionExtractor

        ev = _make_event("Sprint Planning", SourceType.CALENDAR, hours_from_now=2)
        ext = ActionExtractor()
        items = ext.extract([ev])
        assert len(items) == 1
        assert "Attend" in items[0].title

    def test_extract_weather_severe(self):
        from src.intelligence.actions import ActionExtractor

        ev = _make_event("Storm warning", SourceType.WEATHER)
        ext = ActionExtractor()
        items = ext.extract([ev])
        assert len(items) == 1
        assert items[0].priority == Priority.URGENT

    def test_extract_weather_normal(self):
        from src.intelligence.actions import ActionExtractor

        ev = _make_event("Sunny, 72F", SourceType.WEATHER)
        ext = ActionExtractor()
        items = ext.extract([ev])
        assert len(items) == 0

    def test_dedup_existing_actions(self):
        from src.intelligence.actions import ActionExtractor

        ev = _make_event("Review requested: auth fix", SourceType.GITHUB)
        existing = [_make_action("Review: Review requested: auth fix")]
        ext = ActionExtractor()
        items = ext.extract([ev], existing_actions=existing)
        assert len(items) == 0  # already exists

    def test_generic_todo_keyword(self):
        from src.intelligence.actions import ActionExtractor

        ev = _make_event("Weekly TODO roundup", SourceType.NEWS)
        ext = ActionExtractor()
        items = ext.extract([ev])
        assert len(items) == 1

    def test_generic_no_keywords(self):
        from src.intelligence.actions import ActionExtractor

        ev = _make_event("Tech industry news roundup", SourceType.NEWS)
        ext = ActionExtractor()
        items = ext.extract([ev])
        assert len(items) == 0


# ===========================================================================
# PriorityScorer tests
# ===========================================================================


class TestPriorityScorer:
    def test_score_basic(self):
        from src.intelligence.priority import PriorityScorer

        scorer = PriorityScorer()
        item = _make_action("Low task", Priority.LOW)
        score = scorer.score(item)
        assert score > 0

    def test_urgent_higher_than_low(self):
        from src.intelligence.priority import PriorityScorer

        scorer = PriorityScorer()
        urgent = _make_action("Urgent", Priority.URGENT)
        low = _make_action("Low", Priority.LOW)
        assert scorer.score(urgent) > scorer.score(low)

    def test_deadline_boosts_score(self):
        from src.intelligence.priority import PriorityScorer

        scorer = PriorityScorer()
        no_deadline = _make_action("No deadline", Priority.MEDIUM)
        has_deadline = _make_action("Has deadline", Priority.MEDIUM, hours_until_due=2.0)
        assert scorer.score(has_deadline) > scorer.score(no_deadline)

    def test_overdue_boosts_score(self):
        from src.intelligence.priority import PriorityScorer

        scorer = PriorityScorer()
        overdue = _make_action("Overdue task", Priority.MEDIUM, hours_until_due=-1.0)
        normal = _make_action("Normal task", Priority.MEDIUM)
        assert scorer.score(overdue) > scorer.score(normal)

    def test_rank_returns_sorted(self):
        from src.intelligence.priority import PriorityScorer

        scorer = PriorityScorer()
        items = [
            _make_action("Low", Priority.LOW),
            _make_action("Urgent", Priority.URGENT),
            _make_action("Medium", Priority.MEDIUM),
        ]
        ranked = scorer.rank(items)
        assert len(ranked) == 3
        assert ranked[0][0].title == "Urgent"
        assert ranked[-1][0].title == "Low"

    def test_top_n(self):
        from src.intelligence.priority import PriorityScorer

        scorer = PriorityScorer()
        items = [
            _make_action("Low", Priority.LOW),
            _make_action("High", Priority.HIGH),
            _make_action("Urgent", Priority.URGENT),
            _make_action("Medium", Priority.MEDIUM),
        ]
        top = scorer.top_n(items, n=2)
        assert len(top) == 2
        assert top[0].title == "Urgent"

    def test_configure_important_senders(self):
        from src.intelligence.priority import PriorityScorer

        scorer = PriorityScorer()
        scorer.configure(important_senders={"boss@corp.com"})

        normal = _make_action("Normal", Priority.MEDIUM)
        from_boss = _make_action("From boss", Priority.MEDIUM, metadata={"sender": "boss@corp.com"})

        assert scorer.score(from_boss) > scorer.score(normal)

    def test_configure_custom_weights(self):
        from src.intelligence.priority import PriorityScorer

        scorer = PriorityScorer()
        scorer.configure(deadline_weight=100.0, overdue_bonus=50.0)
        overdue = _make_action("Overdue", Priority.LOW, hours_until_due=-1.0)
        score = scorer.score(overdue)
        # Should include base (10) + deadline (100) + overdue (50) = 160
        assert score >= 150.0

    def test_empty_list(self):
        from src.intelligence.priority import PriorityScorer

        scorer = PriorityScorer()
        assert scorer.rank([]) == []
        assert scorer.top_n([]) == []


# ===========================================================================
# ConflictDetector tests
# ===========================================================================


class TestConflictDetector:
    def _calendar_event(
        self,
        title: str,
        start_hours: float,
        duration_hours: float = 1.0,
    ) -> Event:
        start = _now() + timedelta(hours=start_hours)
        end = start + timedelta(hours=duration_hours)
        return Event(
            title=title,
            source_id="cal-1",
            source_type=SourceType.CALENDAR,
            occurred_at=start,
            metadata={
                "start": start.isoformat(),
                "end": end.isoformat(),
            },
        )

    def test_no_conflicts(self):
        from src.intelligence.conflicts import ConflictDetector

        events = [
            self._calendar_event("Meeting A", 1.0, 1.0),
            self._calendar_event("Meeting B", 3.0, 1.0),
        ]
        detector = ConflictDetector()
        conflicts = detector.detect(events)
        assert len(conflicts) == 0

    def test_overlap_detected(self):
        from src.intelligence.conflicts import ConflictDetector

        events = [
            self._calendar_event("Meeting A", 1.0, 2.0),  # 1:00-3:00
            self._calendar_event("Meeting B", 2.0, 1.0),  # 2:00-3:00
        ]
        detector = ConflictDetector()
        conflicts = detector.detect(events)
        assert len(conflicts) == 1
        assert conflicts[0].overlap_minutes == 60.0

    def test_critical_severity(self):
        from src.intelligence.conflicts import ConflictDetector

        events = [
            self._calendar_event("Meeting A", 1.0, 2.0),  # 1:00-3:00
            self._calendar_event("Meeting B", 1.5, 2.0),  # 1:30-3:30
        ]
        detector = ConflictDetector()
        conflicts = detector.detect(events)
        assert len(conflicts) == 1
        assert conflicts[0].severity == "critical"  # >= 30 min overlap

    def test_warning_severity(self):
        from src.intelligence.conflicts import ConflictDetector

        events = [
            self._calendar_event("Meeting A", 1.0, 0.5),  # 1:00-1:30
            self._calendar_event("Meeting B", 1.25, 0.5),  # 1:15-1:45
        ]
        detector = ConflictDetector()
        conflicts = detector.detect(events)
        assert len(conflicts) == 1
        assert conflicts[0].severity == "warning"

    def test_non_calendar_events_ignored(self):
        from src.intelligence.conflicts import ConflictDetector

        events = [
            _make_event("GitHub PR", SourceType.GITHUB, hours_from_now=1.0),
            _make_event("Email", SourceType.EMAIL, hours_from_now=1.0),
        ]
        detector = ConflictDetector()
        conflicts = detector.detect(events)
        assert len(conflicts) == 0

    def test_min_overlap_threshold(self):
        from src.intelligence.conflicts import ConflictDetector

        events = [
            self._calendar_event("Meeting A", 1.0, 1.0),
            self._calendar_event("Meeting B", 1.99, 1.0),  # only ~0.6 min overlap
        ]
        detector = ConflictDetector(min_overlap_minutes=5.0)
        conflicts = detector.detect(events)
        assert len(conflicts) == 0

    def test_format_conflicts_empty(self):
        from src.intelligence.conflicts import ConflictDetector

        text = ConflictDetector.format_conflicts([])
        assert "No scheduling conflicts" in text

    def test_format_conflicts_with_data(self):
        from src.intelligence.conflicts import ConflictDetector

        events = [
            self._calendar_event("Meeting A", 1.0, 2.0),
            self._calendar_event("Meeting B", 2.0, 1.0),
        ]
        detector = ConflictDetector()
        conflicts = detector.detect(events)
        text = detector.format_conflicts(conflicts)
        assert "1 scheduling conflict" in text
        assert "Meeting A" in text

    def test_multiple_conflicts(self):
        from src.intelligence.conflicts import ConflictDetector

        events = [
            self._calendar_event("Meeting A", 1.0, 3.0),
            self._calendar_event("Meeting B", 2.0, 1.0),
            self._calendar_event("Meeting C", 2.5, 1.0),
        ]
        detector = ConflictDetector()
        conflicts = detector.detect(events)
        assert len(conflicts) >= 2  # A<->B, A<->C, possibly B<->C


# ===========================================================================
# PatternAnalyzer tests
# ===========================================================================


class TestPatternAnalyzer:
    def test_empty_events(self):
        from src.intelligence.patterns import PatternAnalyzer

        analyzer = PatternAnalyzer()
        patterns = analyzer.analyze([])
        assert patterns == []

    def test_recurring_meetings(self):
        from src.intelligence.patterns import PatternAnalyzer

        events = [
            _make_event("Standup", SourceType.CALENDAR, hours_from_now=1),
            _make_event("Standup", SourceType.CALENDAR, hours_from_now=2),
            _make_event("Standup", SourceType.CALENDAR, hours_from_now=3),
        ]
        analyzer = PatternAnalyzer()
        patterns = analyzer.analyze(events)
        meeting_patterns = [p for p in patterns if p.category == "meeting"]
        assert len(meeting_patterns) >= 1
        assert meeting_patterns[0].frequency == 3

    def test_source_activity(self):
        from src.intelligence.patterns import PatternAnalyzer

        events = [
            _make_event("E1", SourceType.GITHUB),
            _make_event("E2", SourceType.GITHUB),
            _make_event("E3", SourceType.EMAIL),
        ]
        analyzer = PatternAnalyzer()
        patterns = analyzer.analyze(events)
        activity_patterns = [p for p in patterns if p.category == "activity"]
        assert len(activity_patterns) >= 2

    def test_peak_hours(self):
        from src.intelligence.patterns import PatternAnalyzer

        # Create events all at the same hour
        base = _now().replace(hour=10, minute=0, second=0, microsecond=0)
        events = [
            Event(
                title=f"Event {i}",
                source_id="s1",
                source_type=SourceType.GITHUB,
                occurred_at=base + timedelta(minutes=i * 5),
            )
            for i in range(5)
        ]
        analyzer = PatternAnalyzer()
        patterns = analyzer.analyze(events)
        peak = [p for p in patterns if "Peak hour" in p.name]
        assert len(peak) == 1
        assert peak[0].frequency == 5

    def test_commit_velocity(self):
        from src.intelligence.patterns import PatternAnalyzer

        events = [
            _make_event(f"Commit {i}", SourceType.GITHUB, hours_from_now=i)
            for i in range(5)
        ]
        analyzer = PatternAnalyzer()
        patterns = analyzer.analyze(events)
        velocity = [p for p in patterns if p.category == "commit"]
        assert len(velocity) == 1
        assert velocity[0].frequency == 5

    def test_no_recurring_if_unique(self):
        from src.intelligence.patterns import PatternAnalyzer

        events = [
            _make_event("Meeting A", SourceType.CALENDAR),
            _make_event("Meeting B", SourceType.CALENDAR),
            _make_event("Meeting C", SourceType.CALENDAR),
        ]
        analyzer = PatternAnalyzer()
        patterns = analyzer.analyze(events)
        meeting_patterns = [p for p in patterns if p.category == "meeting"]
        assert len(meeting_patterns) == 0

    def test_format_patterns_empty(self):
        from src.intelligence.patterns import PatternAnalyzer

        text = PatternAnalyzer.format_patterns([])
        assert "No patterns" in text

    def test_format_patterns_with_data(self):
        from src.intelligence.patterns import PatternAnalyzer, Pattern

        patterns = [Pattern(name="Standup", category="meeting", description="Recurring", frequency=5)]
        text = PatternAnalyzer.format_patterns(patterns)
        assert "Standup" in text
        assert "meeting" in text


# ===========================================================================
# CLI integration tests for brief, actions, focus
# ===========================================================================


class TestIntelligenceCLI:
    def _write_sync_file(self, tmp_path: Path) -> Path:
        data = {
            "synced_at": _now().isoformat(),
            "events": [
                {
                    "title": "Team Standup",
                    "source_id": "s1",
                    "source_type": "calendar",
                    "occurred_at": (_now() + timedelta(hours=1)).isoformat(),
                    "summary": "",
                    "url": "",
                    "metadata": {
                        "start": (_now() + timedelta(hours=1)).isoformat(),
                        "end": (_now() + timedelta(hours=2)).isoformat(),
                    },
                },
                {
                    "title": "Review requested: auth module",
                    "source_id": "s2",
                    "source_type": "github",
                    "occurred_at": _now().isoformat(),
                    "summary": "",
                    "url": "https://github.com/example/repo/pull/1",
                    "metadata": {},
                },
            ],
            "action_items": [
                {
                    "title": "Deploy v2.0",
                    "source_id": "s1",
                    "source_type": "github",
                    "priority": "urgent",
                    "due_at": (_now() + timedelta(hours=3)).isoformat(),
                    "url": "",
                    "completed": False,
                    "notes": "",
                    "metadata": {},
                },
            ],
        }
        sync_file = tmp_path / "test_sync.json"
        sync_file.write_text(json.dumps(data), encoding="utf-8")
        return sync_file

    def test_cmd_brief(self, tmp_path, capsys):
        from src.cli import build_parser

        sync_file = self._write_sync_file(tmp_path)
        parser = build_parser()
        args = parser.parse_args(["brief", "--sync-file", str(sync_file)])
        args.func(args)
        output = capsys.readouterr().out
        assert "Beacon Briefing" in output
        assert "Team Standup" in output

    def test_cmd_brief_no_data(self, capsys):
        from src.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["brief", "--sync-file", "/nonexistent/sync.json"])
        args.func(args)
        output = capsys.readouterr().out
        assert "No data available" in output

    def test_cmd_actions(self, tmp_path, capsys):
        from src.cli import build_parser

        sync_file = self._write_sync_file(tmp_path)
        parser = build_parser()
        args = parser.parse_args(["actions", "--sync-file", str(sync_file)])
        args.func(args)
        output = capsys.readouterr().out
        assert "Action Items" in output
        assert "Deploy v2.0" in output

    def test_cmd_actions_no_data(self, capsys):
        from src.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["actions", "--sync-file", "/nonexistent/sync.json"])
        args.func(args)
        output = capsys.readouterr().out
        assert "No action items" in output

    def test_cmd_focus(self, tmp_path, capsys):
        from src.cli import build_parser

        sync_file = self._write_sync_file(tmp_path)
        parser = build_parser()
        args = parser.parse_args(["focus", "--sync-file", str(sync_file)])
        args.func(args)
        output = capsys.readouterr().out
        assert "Focus Mode" in output

    def test_cmd_focus_no_data(self, capsys):
        from src.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["focus", "--sync-file", "/nonexistent/sync.json"])
        args.func(args)
        output = capsys.readouterr().out
        assert "Nothing to focus on" in output

    def test_cmd_focus_custom_count(self, tmp_path, capsys):
        from src.cli import build_parser

        sync_file = self._write_sync_file(tmp_path)
        parser = build_parser()
        args = parser.parse_args(["focus", "-n", "1", "--sync-file", str(sync_file)])
        args.func(args)
        output = capsys.readouterr().out
        assert "Top 1" in output
