"""Tests for the store-backed export module (src.store_export)."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.models import ActionItem, Event, Priority, SourceType
from src.store import BeaconStore
from src.store_export.exporter import build_store_export_payload, export_store_query


# -------------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------------


@pytest.fixture()
def tmp_store(tmp_path: Path) -> BeaconStore:
    """Create a temporary BeaconStore with sample data."""
    store = BeaconStore(tmp_path / "test.db")
    store.init_db()

    now = datetime.now(tz=timezone.utc)
    events = [
        Event(
            id="evt-1",
            title="PR Review Requested",
            source_id="github-main",
            source_type=SourceType.GITHUB,
            occurred_at=now,
            summary="Review PR #42",
            url="https://github.com/test/repo/pull/42",
        ),
        Event(
            id="evt-2",
            title="Team Standup",
            source_id="calendar-work",
            source_type=SourceType.CALENDAR,
            occurred_at=now,
            summary="Daily standup at 9 AM",
            url="",
        ),
    ]
    actions = [
        ActionItem(
            id="act-1",
            title="Reply to investor email",
            source_id="email-main",
            source_type=SourceType.EMAIL,
            priority=Priority.HIGH,
            due_at=now,
            url="",
            completed=False,
            notes="Follow up on term sheet",
        ),
        ActionItem(
            id="act-2",
            title="Fix CI pipeline",
            source_id="github-main",
            source_type=SourceType.GITHUB,
            priority=Priority.MEDIUM,
            completed=True,
        ),
    ]
    store.upsert_events(events)
    store.upsert_action_items(actions)
    return store


# -------------------------------------------------------------------
# build_store_export_payload tests
# -------------------------------------------------------------------


class TestBuildStoreExportPayload:
    def test_basic_payload_structure(self, tmp_store: BeaconStore) -> None:
        payload = build_store_export_payload(tmp_store)
        assert "generated_at" in payload
        assert "event_count" in payload
        assert "action_item_count" in payload
        assert "events" in payload
        assert "action_items" in payload

    def test_event_count_matches(self, tmp_store: BeaconStore) -> None:
        payload = build_store_export_payload(tmp_store)
        assert payload["event_count"] == 2
        assert len(payload["events"]) == 2

    def test_action_item_count_matches(self, tmp_store: BeaconStore) -> None:
        payload = build_store_export_payload(tmp_store)
        assert payload["action_item_count"] == 2
        assert len(payload["action_items"]) == 2

    def test_filter_by_source_type(self, tmp_store: BeaconStore) -> None:
        payload = build_store_export_payload(tmp_store, source_type="github")
        assert payload["event_count"] == 1
        assert payload["events"][0]["title"] == "PR Review Requested"

    def test_events_are_serialisable(self, tmp_store: BeaconStore) -> None:
        payload = build_store_export_payload(tmp_store)
        # Should not raise
        text = json.dumps(payload, default=str)
        assert "PR Review Requested" in text

    def test_empty_store(self, tmp_path: Path) -> None:
        store = BeaconStore(tmp_path / "empty.db")
        store.init_db()
        payload = build_store_export_payload(store)
        assert payload["event_count"] == 0
        assert payload["action_item_count"] == 0
        assert payload["events"] == []
        assert payload["action_items"] == []

    def test_limit_parameter(self, tmp_store: BeaconStore) -> None:
        payload = build_store_export_payload(tmp_store, limit=1)
        assert payload["event_count"] == 1
        assert payload["action_item_count"] == 1

    def test_generated_at_is_iso(self, tmp_store: BeaconStore) -> None:
        payload = build_store_export_payload(tmp_store)
        # Should parse without error
        dt = datetime.fromisoformat(payload["generated_at"])
        assert dt.tzinfo is not None


# -------------------------------------------------------------------
# export_store_query tests
# -------------------------------------------------------------------


class TestExportStoreQuery:
    def test_json_export(self, tmp_store: BeaconStore, tmp_path: Path) -> None:
        out = tmp_path / "export.json"
        result = export_store_query(tmp_store, fmt="json", output_path=out)
        assert result == out
        assert out.exists()
        data = json.loads(out.read_text())
        assert data["event_count"] == 2

    def test_html_export(self, tmp_store: BeaconStore, tmp_path: Path) -> None:
        out = tmp_path / "export.html"
        result = export_store_query(tmp_store, fmt="html", output_path=out)
        assert result == out
        assert out.exists()
        content = out.read_text()
        assert "<html" in content
        assert "Beacon Store Export" in content

    def test_pdf_export(self, tmp_store: BeaconStore, tmp_path: Path) -> None:
        out = tmp_path / "export.html"
        result = export_store_query(tmp_store, fmt="pdf", output_path=out)
        assert result == out
        content = out.read_text()
        assert "@media print" in content

    def test_invalid_format(self, tmp_store: BeaconStore) -> None:
        with pytest.raises(ValueError, match="Unsupported format"):
            export_store_query(tmp_store, fmt="csv")

    def test_auto_output_path(self, tmp_store: BeaconStore) -> None:
        result = export_store_query(tmp_store, fmt="json")
        assert result.exists()
        assert result.suffix == ".json"
        # Cleanup
        result.unlink(missing_ok=True)

    def test_filtered_export(self, tmp_store: BeaconStore, tmp_path: Path) -> None:
        out = tmp_path / "filtered.json"
        result = export_store_query(
            tmp_store,
            fmt="json",
            output_path=out,
            source_type="github",
        )
        data = json.loads(out.read_text())
        assert data["event_count"] == 1

    def test_custom_title_in_html(self, tmp_store: BeaconStore, tmp_path: Path) -> None:
        out = tmp_path / "titled.html"
        export_store_query(
            tmp_store,
            fmt="html",
            output_path=out,
            title="My Custom Report",
        )
        content = out.read_text()
        assert "My Custom Report" in content
