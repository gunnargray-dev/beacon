"""Tests for the Beacon CLI."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path


def run_cli(*args, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "src.cli", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )


# ---------------------------------------------------------------------------
# --help / --version
# ---------------------------------------------------------------------------


def test_cli_help():
    result = run_cli("--help")
    assert result.returncode == 0
    assert "beacon" in result.stdout.lower() or "personal ops" in result.stdout.lower()


def test_cli_no_args_shows_help():
    result = run_cli()
    assert result.returncode == 0
    assert "beacon" in result.stdout.lower() or "usage" in result.stdout.lower()


def test_cli_version():
    result = run_cli("--version")
    assert result.returncode == 0
    assert "0.1.0" in result.stdout


# ---------------------------------------------------------------------------
# beacon status
# ---------------------------------------------------------------------------


def test_cli_status_no_config(tmp_path):
    """Status without a config file should print a friendly message."""
    result = run_cli("status", cwd=str(tmp_path))
    assert result.returncode == 0
    assert "Beacon" in result.stdout


def test_cli_status_with_config(tmp_path):
    """Status with a valid config should show user and source info."""
    config = textwrap.dedent("""\
        [user]
        name = "Alice"
        email = "alice@example.com"
        timezone = "UTC"

        [[sources]]
        name = "github"
        type = "github"
        enabled = true
        token = "tok"
    """)
    (tmp_path / "beacon.toml").write_text(config, encoding="utf-8")
    result = run_cli("status", "--config", str(tmp_path / "beacon.toml"))
    assert result.returncode == 0
    assert "Alice" in result.stdout
    assert "github" in result.stdout


def test_cli_status_empty_sources(tmp_path):
    config = textwrap.dedent("""\
        [user]
        name = "Bob"
        email = "bob@example.com"
    """)
    (tmp_path / "beacon.toml").write_text(config, encoding="utf-8")
    result = run_cli("status", "--config", str(tmp_path / "beacon.toml"))
    assert result.returncode == 0
    assert "None configured" in result.stdout or "No" in result.stdout


# ---------------------------------------------------------------------------
# beacon init
# ---------------------------------------------------------------------------


def test_cli_init_creates_file(tmp_path):
    target = tmp_path / "beacon.toml"
    result = run_cli("init", "--path", str(target))
    assert result.returncode == 0
    assert target.exists()
    assert "Created" in result.stdout


def test_cli_init_fails_if_exists(tmp_path):
    target = tmp_path / "beacon.toml"
    target.touch()
    result = run_cli("init", "--path", str(target))
    assert result.returncode != 0 or "already exists" in result.stdout


# ---------------------------------------------------------------------------
# beacon sources
# ---------------------------------------------------------------------------


def test_cli_sources_no_config(tmp_path):
    result = run_cli("sources", cwd=str(tmp_path))
    assert result.returncode != 0 or "No config" in result.stdout


def test_cli_sources_empty(tmp_path):
    (tmp_path / "beacon.toml").write_text("[user]\nname='X'\n", encoding="utf-8")
    result = run_cli("sources", "--config", str(tmp_path / "beacon.toml"))
    assert result.returncode == 0
    assert "No sources" in result.stdout


def test_cli_sources_lists(tmp_path):
    config = textwrap.dedent("""\
        [[sources]]
        name = "gh"
        type = "github"
        enabled = true
    """)
    (tmp_path / "beacon.toml").write_text(config, encoding="utf-8")
    result = run_cli("sources", "--config", str(tmp_path / "beacon.toml"))
    assert result.returncode == 0
    assert "gh" in result.stdout


# ---------------------------------------------------------------------------
# beacon sources (enhanced -- connector info)
# ---------------------------------------------------------------------------


def test_cli_sources_shows_connector_column(tmp_path):
    """Enhanced sources listing shows connector class name."""
    config = textwrap.dedent("""\
        [[sources]]
        name = "mycal"
        type = "calendar"
        enabled = true
        calendar_url = "https://example.com/cal.ics"
    """)
    (tmp_path / "beacon.toml").write_text(config, encoding="utf-8")
    result = run_cli("sources", "--config", str(tmp_path / "beacon.toml"))
    assert result.returncode == 0
    assert "mycal" in result.stdout
    # Should show connector class or "(not registered)"
    assert "CalendarConnector" in result.stdout or "Connector" in result.stdout


def test_cli_sources_shows_disabled(tmp_path):
    config = textwrap.dedent("""\
        [[sources]]
        name = "rss"
        type = "news"
        enabled = false
        feeds = ["https://example.com/feed.rss"]
    """)
    (tmp_path / "beacon.toml").write_text(config, encoding="utf-8")
    result = run_cli("sources", "--config", str(tmp_path / "beacon.toml"))
    assert result.returncode == 0
    assert "disabled" in result.stdout


def test_cli_sources_unknown_type(tmp_path):
    """Unknown connector type should show '(unknown type)' not crash."""
    config = textwrap.dedent("""\
        [[sources]]
        name = "custom"
        type = "myCustomType"
        enabled = true
    """)
    (tmp_path / "beacon.toml").write_text(config, encoding="utf-8")
    result = run_cli("sources", "--config", str(tmp_path / "beacon.toml"))
    assert result.returncode == 0
    assert "unknown type" in result.stdout.lower() or "custom" in result.stdout


# ---------------------------------------------------------------------------
# beacon sources test <name>
# ---------------------------------------------------------------------------


def test_cli_sources_test_invalid_config(tmp_path):
    """sources test <name> with invalid connector config should exit non-zero."""
    config = textwrap.dedent("""\
        [[sources]]
        name = "myCal"
        type = "calendar"
        enabled = true
    """)
    (tmp_path / "beacon.toml").write_text(config, encoding="utf-8")
    result = run_cli(
        "sources", "test", "myCal", "--config", str(tmp_path / "beacon.toml")
    )
    # Missing calendar_url/calendar_file => config invalid => non-zero exit
    assert result.returncode != 0
    assert "FAIL" in result.stdout or "invalid" in result.stdout.lower()


def test_cli_sources_test_not_found(tmp_path):
    """sources test <name> for unknown source should exit non-zero."""
    (tmp_path / "beacon.toml").write_text("[user]\nname='X'\n", encoding="utf-8")
    result = run_cli(
        "sources", "test", "nosource", "--config", str(tmp_path / "beacon.toml")
    )
    assert result.returncode != 0
    assert "not found" in result.stdout.lower() or "No config" in result.stdout


def test_cli_sources_test_no_config(tmp_path):
    """sources test without config exits non-zero."""
    result = run_cli("sources", "test", "x", cwd=str(tmp_path))
    assert result.returncode != 0


def test_cli_sources_test_all_skipped(tmp_path):
    """sources test with no sources just returns cleanly."""
    (tmp_path / "beacon.toml").write_text("[user]\nname='X'\n", encoding="utf-8")
    result = run_cli(
        "sources", "test", "--config", str(tmp_path / "beacon.toml")
    )
    # No sources configured
    assert result.returncode == 0 or "No sources" in result.stdout


# ---------------------------------------------------------------------------
# beacon sync
# ---------------------------------------------------------------------------


def test_cli_sync_no_config(tmp_path):
    """sync without a config exits non-zero."""
    result = run_cli("sync", cwd=str(tmp_path))
    assert result.returncode != 0


def test_cli_sync_no_sources(tmp_path):
    """sync with no enabled sources exits cleanly with a message."""
    (tmp_path / "beacon.toml").write_text("[user]\nname='X'\n", encoding="utf-8")
    result = run_cli("sync", "--config", str(tmp_path / "beacon.toml"))
    assert result.returncode == 0
    assert "No enabled sources" in result.stdout


def test_cli_sync_skips_disabled_source(tmp_path):
    """Disabled sources are not synced."""
    config = textwrap.dedent("""\
        [[sources]]
        name = "gh"
        type = "github"
        enabled = false
        github_token = "tok"
    """)
    (tmp_path / "beacon.toml").write_text(config, encoding="utf-8")
    result = run_cli("sync", "--config", str(tmp_path / "beacon.toml"))
    assert result.returncode == 0
    assert "No enabled sources" in result.stdout


def test_cli_sync_skips_invalid_config_source(tmp_path):
    """Source with invalid connector config is skipped with a message."""
    config = textwrap.dedent("""\
        [[sources]]
        name = "mycal"
        type = "calendar"
        enabled = true
    """)
    (tmp_path / "beacon.toml").write_text(config, encoding="utf-8")
    result = run_cli("sync", "--config", str(tmp_path / "beacon.toml"))
    # Invalid calendar config (no url/file) -> SKIP
    assert "SKIP" in result.stdout or result.returncode == 0


def test_cli_sync_skips_unknown_type(tmp_path):
    """Source with unknown type is skipped gracefully."""
    config = textwrap.dedent("""\
        [[sources]]
        name = "weird"
        type = "myUnknownType"
        enabled = true
    """)
    (tmp_path / "beacon.toml").write_text(config, encoding="utf-8")
    result = run_cli("sync", "--config", str(tmp_path / "beacon.toml"))
    assert "SKIP" in result.stdout


def test_cli_sync_writes_cache_file(tmp_path, monkeypatch):
    """A successful sync writes a JSON cache file."""
    import json
    import textwrap

    monkeypatch.setenv("HOME", str(tmp_path))

    config = textwrap.dedent("""\
        [[sources]]
        name = "hn"
        type = "hacker_news"
        enabled = true
        story_count = 1
    """)
    (tmp_path / "beacon.toml").write_text(config, encoding="utf-8")

    # Patch urlopen to return fake HN data
    hn_ids = [42]
    hn_story = {
        "id": 42,
        "type": "story",
        "title": "Test Story",
        "url": "https://example.com/test",
        "score": 100,
        "descendants": 5,
        "by": "tester",
        "time": 1704067200,
    }
    import json as _json
    from unittest.mock import MagicMock, patch

    def _make_resp(data):
        resp = MagicMock()
        resp.read.return_value = _json.dumps(data).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    with patch("urllib.request.urlopen", side_effect=[_make_resp(hn_ids), _make_resp(hn_story)]):
        result = run_cli("sync", "--config", str(tmp_path / "beacon.toml"))

    cache_file = tmp_path / ".cache" / "beacon" / "last_sync.json"
    assert cache_file.exists(), f"Cache file not written; stdout: {result.stdout}"
    data = json.loads(cache_file.read_text())
    assert "events" in data
    assert "action_items" in data
    assert "synced_at" in data
