"""Tests for the Calendar connector (iCal/ICS parser)."""

from __future__ import annotations

import textwrap
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.connectors.base import ConnectorError
from src.connectors.calendar_connector import (
    CalendarConnector,
    _detect_conflicts,
    _parse_dt,
    _parse_ics,
    _unfold,
)
from src.models import Source, SourceType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FUTURE_DATE = "20990101T120000Z"
_FUTURE_DATE2 = "20990101T130000Z"
_PAST_DATE = "19990101T120000Z"


def _make_source(config: dict | None = None) -> Source:
    return Source(
        name="test-cal",
        source_type=SourceType.CALENDAR,
        config=config or {},
    )


MINIMAL_ICS = textwrap.dedent(f"""\
    BEGIN:VCALENDAR
    VERSION:2.0
    BEGIN:VEVENT
    SUMMARY:Team Standup
    DTSTART:{_FUTURE_DATE}
    DTEND:{_FUTURE_DATE2}
    LOCATION:Zoom
    DESCRIPTION:Daily sync
    UID:abc-123@example.com
    END:VEVENT
    END:VCALENDAR
""")

MULTI_EVENT_ICS = textwrap.dedent(f"""\
    BEGIN:VCALENDAR
    VERSION:2.0
    BEGIN:VEVENT
    SUMMARY:Meeting A
    DTSTART:{_FUTURE_DATE}
    DTEND:{_FUTURE_DATE2}
    UID:aaa@example.com
    END:VEVENT
    BEGIN:VEVENT
    SUMMARY:Meeting B
    DTSTART:{_FUTURE_DATE}
    DTEND:{_FUTURE_DATE2}
    UID:bbb@example.com
    END:VEVENT
    END:VCALENDAR
""")

FOLDED_ICS = textwrap.dedent(f"""\
    BEGIN:VCALENDAR
    VERSION:2.0
    BEGIN:VEVENT
    SUMMARY:Long Title That Is Folded
     Continuation Here
    DTSTART:{_FUTURE_DATE}
    END:VEVENT
    END:VCALENDAR
""")


# ---------------------------------------------------------------------------
# _parse_dt
# ---------------------------------------------------------------------------


class TestParseDt:
    def test_utc_datetime(self):
        dt = _parse_dt("20240315T143000Z")
        assert dt is not None
        assert dt.tzinfo == timezone.utc
        assert dt.year == 2024
        assert dt.month == 3
        assert dt.day == 15

    def test_date_only(self):
        dt = _parse_dt("20240315")
        assert dt is not None
        assert dt.year == 2024

    def test_local_datetime(self):
        dt = _parse_dt("20240315T143000")
        assert dt is not None
        assert dt.year == 2024

    def test_with_tzid_prefix(self):
        dt = _parse_dt("DTSTART;TZID=America/New_York:20240315T143000")
        assert dt is not None
        assert dt.year == 2024

    def test_invalid_returns_none(self):
        assert _parse_dt("not-a-date") is None

    def test_empty_returns_none(self):
        assert _parse_dt("") is None


# ---------------------------------------------------------------------------
# _unfold
# ---------------------------------------------------------------------------


class TestUnfold:
    def test_unfolds_continuation(self):
        lines = ["SUMMARY:Long", " Continuation"]
        result = _unfold(lines)
        assert len(result) == 1
        assert result[0] == "SUMMARY:LongContinuation"

    def test_tab_continuation(self):
        lines = ["SUMMARY:Hello", "\tWorld"]
        result = _unfold(lines)
        assert result[0] == "SUMMARY:HelloWorld"

    def test_no_fold(self):
        lines = ["SUMMARY:Short", "DTSTART:20240315T120000Z"]
        result = _unfold(lines)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# _parse_ics
# ---------------------------------------------------------------------------


class TestParseIcs:
    def test_parses_single_event(self):
        events = _parse_ics(MINIMAL_ICS)
        assert len(events) == 1
        ev = events[0]
        assert ev["SUMMARY"] == "Team Standup"
        assert ev["LOCATION"] == "Zoom"
        assert ev["UID"] == "abc-123@example.com"

    def test_parses_multiple_events(self):
        events = _parse_ics(MULTI_EVENT_ICS)
        assert len(events) == 2

    def test_empty_ics_returns_empty(self):
        events = _parse_ics("BEGIN:VCALENDAR\nEND:VCALENDAR\n")
        assert events == []

    def test_dtstart_key_preserved(self):
        events = _parse_ics(MINIMAL_ICS)
        assert "DTSTART" in events[0]


# ---------------------------------------------------------------------------
# _detect_conflicts
# ---------------------------------------------------------------------------


class TestDetectConflicts:
    def _ev(self, summary: str, start: str, end: str) -> dict:
        return {"SUMMARY": summary, "DTSTART": start, "DTEND": end}

    def test_no_events_no_conflicts(self):
        assert _detect_conflicts([]) == []

    def test_non_overlapping_no_conflict(self):
        evs = [
            self._ev("A", "20990101T090000Z", "20990101T100000Z"),
            self._ev("B", "20990101T110000Z", "20990101T120000Z"),
        ]
        assert _detect_conflicts(evs) == []

    def test_overlapping_returns_pair(self):
        evs = [
            self._ev("A", "20990101T090000Z", "20990101T110000Z"),
            self._ev("B", "20990101T100000Z", "20990101T120000Z"),
        ]
        conflicts = _detect_conflicts(evs)
        assert len(conflicts) == 1

    def test_identical_time_is_conflict(self):
        evs = [
            self._ev("A", "20990101T090000Z", "20990101T110000Z"),
            self._ev("B", "20990101T090000Z", "20990101T110000Z"),
        ]
        conflicts = _detect_conflicts(evs)
        assert len(conflicts) >= 1


# ---------------------------------------------------------------------------
# CalendarConnector
# ---------------------------------------------------------------------------


class TestCalendarConnectorValidateConfig:
    def test_valid_with_url(self):
        conn = CalendarConnector(_make_source({"calendar_url": "https://example.com/cal.ics"}))
        assert conn.validate_config() is True

    def test_valid_with_file(self, tmp_path):
        f = tmp_path / "cal.ics"
        f.write_text(MINIMAL_ICS)
        conn = CalendarConnector(_make_source({"calendar_file": str(f)}))
        assert conn.validate_config() is True

    def test_invalid_empty_config(self):
        conn = CalendarConnector(_make_source())
        assert conn.validate_config() is False


class TestCalendarConnectorSync:
    def test_sync_from_file(self, tmp_path):
        f = tmp_path / "test.ics"
        f.write_text(MINIMAL_ICS)
        conn = CalendarConnector(_make_source({"calendar_file": str(f), "days_ahead": 36500}))
        events, actions = conn.sync()
        assert len(events) == 1
        assert events[0].title == "Team Standup"
        assert events[0].source_type == SourceType.CALENDAR
        assert "location" in events[0].metadata

    def test_sync_filters_past_events(self, tmp_path):
        ics = textwrap.dedent(f"""\
            BEGIN:VCALENDAR
            BEGIN:VEVENT
            SUMMARY:Past Meeting
            DTSTART:{_PAST_DATE}
            DTEND:19990101T130000Z
            END:VEVENT
            END:VCALENDAR
        """)
        f = tmp_path / "past.ics"
        f.write_text(ics)
        conn = CalendarConnector(_make_source({"calendar_file": str(f)}))
        events, _ = conn.sync()
        assert all(ev.title != "Past Meeting" for ev in events)

    def test_sync_detects_conflicts(self, tmp_path):
        f = tmp_path / "conflicts.ics"
        f.write_text(MULTI_EVENT_ICS)
        conn = CalendarConnector(_make_source({"calendar_file": str(f), "days_ahead": 36500}))
        events, action_items = conn.sync()
        # Both events overlap, so conflicts should be detected
        assert len(action_items) >= 1

    def test_sync_missing_file_raises(self):
        conn = CalendarConnector(_make_source({"calendar_file": "/nonexistent/path/cal.ics"}))
        with pytest.raises(ConnectorError):
            conn.sync()

    def test_sync_no_config_raises(self):
        conn = CalendarConnector(_make_source())
        with pytest.raises(ConnectorError):
            conn.sync()

    def test_sync_from_url(self):
        with patch("urllib.request.urlopen") as mock_open:
            mock_resp = MagicMock()
            mock_resp.read.return_value = MINIMAL_ICS.encode()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_resp

            conn = CalendarConnector(
                _make_source({"calendar_url": "https://example.com/cal.ics", "days_ahead": 36500})
            )
            events, _ = conn.sync()
            assert len(events) == 1

    def test_event_has_correct_source_id(self, tmp_path):
        f = tmp_path / "test.ics"
        f.write_text(MINIMAL_ICS)
        src = _make_source({"calendar_file": str(f), "days_ahead": 36500})
        conn = CalendarConnector(src)
        events, _ = conn.sync()
        assert all(ev.source_id == src.id for ev in events)

    def test_connector_type(self):
        assert CalendarConnector.connector_type == SourceType.CALENDAR
