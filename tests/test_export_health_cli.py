"""Tests for the `beacon export` and `beacon health` CLI commands."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.cli import build_parser
from src.models import ActionItem, Event, Priority, SourceType
from src.store import BeaconStore


# -------------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------------


@pytest.fixture()
def populated_store(tmp_path: Path) -> BeaconStore:
    store = BeaconStore(tmp_path / "test_cli.db")
    store.init_db()
    store.upsert_events([
        Event(
            id="evt-cli-1",
            title="CLI Test Event",
            source_id="test",
            source_type=SourceType.GITHUB,
            occurred_at=datetime.now(tz=timezone.utc),
            summary="Test event for CLI",
        ),
    ])
    store.upsert_action_items([
        ActionItem(
            id="act-cli-1",
            title="CLI Test Action",
            source_id="test",
            source_type=SourceType.GITHUB,
            priority=Priority.HIGH,
        ),
    ])
    return store


# -------------------------------------------------------------------
# beacon export
# -------------------------------------------------------------------


class TestCmdExport:
    def test_export_json(self, populated_store: BeaconStore, tmp_path: Path) -> None:
        out_file = tmp_path / "out.json"
        parser = build_parser()
        args = parser.parse_args([
            "export",
            "--format", "json",
            "--output", str(out_file),
            "--db", str(populated_store.db_path),
        ])
        args.func(args)
        assert out_file.exists()
        data = json.loads(out_file.read_text())
        assert data["event_count"] == 1

    def test_export_html(self, populated_store: BeaconStore, tmp_path: Path) -> None:
        out_file = tmp_path / "out.html"
        parser = build_parser()
        args = parser.parse_args([
            "export",
            "--format", "html",
            "--output", str(out_file),
            "--db", str(populated_store.db_path),
        ])
        args.func(args)
        assert out_file.exists()
        content = out_file.read_text()
        assert "<html" in content

    def test_export_missing_store(self, tmp_path: Path) -> None:
        parser = build_parser()
        args = parser.parse_args([
            "export",
            "--db", str(tmp_path / "nonexistent.db"),
        ])
        with pytest.raises(SystemExit):
            args.func(args)

    def test_export_with_source_filter(self, populated_store: BeaconStore, tmp_path: Path) -> None:
        out_file = tmp_path / "filtered.json"
        parser = build_parser()
        args = parser.parse_args([
            "export",
            "--format", "json",
            "--output", str(out_file),
            "--db", str(populated_store.db_path),
            "--source-type", "github",
        ])
        args.func(args)
        data = json.loads(out_file.read_text())
        assert data["event_count"] == 1


# -------------------------------------------------------------------
# beacon health
# -------------------------------------------------------------------


class TestCmdHealth:
    def test_health_no_config(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        parser = build_parser()
        args = parser.parse_args([
            "health",
            "--config", str(tmp_path / "none.toml"),
            "--db", str(tmp_path / "none.db"),
        ])
        # Health check should exit 1 when issues found
        with pytest.raises(SystemExit) as exc_info:
            args.func(args)
        assert exc_info.value.code == 1
        output = capsys.readouterr().out
        assert "Beacon Health Check" in output

    def test_health_with_store(self, populated_store: BeaconStore, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        parser = build_parser()
        args = parser.parse_args([
            "health",
            "--config", str(tmp_path / "none.toml"),
            "--db", str(populated_store.db_path),
        ])
        # Will still exit 1 because config is missing, but store check should pass
        with pytest.raises(SystemExit):
            args.func(args)
        output = capsys.readouterr().out
        assert "1 events" in output
        assert "1 actions" in output

    def test_parser_registers_export(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["export", "--format", "json"])
        assert args.command == "export"

    def test_parser_registers_health(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["health"])
        assert args.command == "health"
