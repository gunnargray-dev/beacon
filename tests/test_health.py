"""Tests for the health diagnostics module (src.health)."""

from __future__ import annotations

import json
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from src.health import HealthReport, run_health_check
from src.models import ActionItem, Event, Priority, SourceType
from src.store import BeaconStore


# -------------------------------------------------------------------
# HealthReport unit tests
# -------------------------------------------------------------------


class TestHealthReport:
    def test_empty_report_is_healthy(self) -> None:
        report = HealthReport()
        assert report.ok is True

    def test_add_check_ok(self) -> None:
        report = HealthReport()
        report.add_check("config", "ok", "found")
        assert len(report.checks) == 1
        assert report.ok is True

    def test_add_check_fail(self) -> None:
        report = HealthReport()
        report.add_check("store", "fail", "missing")
        assert report.ok is False

    def test_add_check_warn_is_not_ok(self) -> None:
        report = HealthReport()
        report.add_check("cache", "warn", "not found")
        assert report.ok is False

    def test_as_text_contains_checks(self) -> None:
        report = HealthReport()
        report.add_check("config", "ok", "/path/to/beacon.toml")
        report.add_check("store", "fail", "not found")
        text = report.as_text()
        assert "Beacon Health Check" in text
        assert "[+] config" in text
        assert "[x] store" in text
        assert "ISSUES DETECTED" in text

    def test_as_text_healthy(self) -> None:
        report = HealthReport()
        report.add_check("config", "ok")
        text = report.as_text()
        assert "HEALTHY" in text

    def test_warn_icon_in_text(self) -> None:
        report = HealthReport()
        report.add_check("sync_cache", "warn", "not synced")
        text = report.as_text()
        assert "[!] sync_cache" in text


# -------------------------------------------------------------------
# run_health_check integration tests
# -------------------------------------------------------------------


class TestRunHealthCheck:
    def test_no_config_no_store(self, tmp_path: Path) -> None:
        """When nothing exists, health check should return warnings."""
        # Point to a non-existent config
        report = run_health_check(
            config_path=tmp_path / "nonexistent.toml",
            db_path=tmp_path / "nonexistent.db",
        )
        assert report.config_found is False
        assert report.store_exists is False

    def test_with_store(self, tmp_path: Path) -> None:
        """Health check correctly reads store counts."""
        store = BeaconStore(tmp_path / "beacon.db")
        store.init_db()
        store.upsert_events([
            Event(
                id="e1",
                title="Test",
                source_id="test",
                source_type=SourceType.GITHUB,
                occurred_at=datetime.now(tz=timezone.utc),
            ),
        ])
        store.upsert_action_items([
            ActionItem(
                id="a1",
                title="Do thing",
                source_id="test",
                source_type=SourceType.GITHUB,
                priority=Priority.HIGH,
            ),
        ])

        report = run_health_check(
            config_path=tmp_path / "none.toml",
            db_path=tmp_path / "beacon.db",
        )
        assert report.store_exists is True
        assert report.store_event_count == 1
        assert report.store_action_count == 1

    def test_with_sync_cache(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Health check reads sync cache info."""
        cache_dir = tmp_path / ".cache" / "beacon"
        cache_dir.mkdir(parents=True)
        cache_file = cache_dir / "last_sync.json"
        cache_file.write_text(
            json.dumps({
                "synced_at": "2026-03-03T12:00:00+00:00",
                "events": [{"id": "e1"}],
                "action_items": [{"id": "a1"}, {"id": "a2"}],
            })
        )

        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        report = run_health_check(
            config_path=tmp_path / "none.toml",
            db_path=tmp_path / "none.db",
        )
        assert report.cache_exists is True
        assert report.cache_event_count == 1
        assert report.cache_action_count == 2
        assert report.cache_synced_at == "2026-03-03T12:00:00+00:00"

    def test_with_config_file(self, tmp_path: Path) -> None:
        """Health check reads config and counts sources."""
        config_content = textwrap.dedent("""\
            [user]
            name = "Test"
            email = "test@example.com"
            timezone = "UTC"

            [[sources]]
            name = "my-github"
            type = "github"
            enabled = true

            [sources.config]
            token = "ghp_test"

            [[sources]]
            name = "my-calendar"
            type = "calendar"
            enabled = false

            [sources.config]
            path = "/tmp/cal"
        """)
        config_file = tmp_path / "beacon.toml"
        config_file.write_text(config_content)

        report = run_health_check(
            config_path=config_file,
            db_path=tmp_path / "none.db",
        )
        assert report.config_found is True
        assert report.config_path == str(config_file)
        assert report.sources_total == 2
        assert report.sources_enabled == 1

    def test_report_text_output(self, tmp_path: Path) -> None:
        """The text report is well-formed."""
        report = run_health_check(
            config_path=tmp_path / "none.toml",
            db_path=tmp_path / "none.db",
        )
        text = report.as_text()
        assert isinstance(text, str)
        assert "Beacon Health Check" in text
