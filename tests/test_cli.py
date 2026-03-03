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
