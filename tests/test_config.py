"""Tests for the Beacon configuration system."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from src.config import (
    BeaconConfig,
    ConfigError,
    SourceConfig,
    UserConfig,
    _parse_config,
    find_config_file,
    generate_default_config,
    load_config,
    write_default_config,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_toml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "beacon.toml"
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# generate_default_config
# ---------------------------------------------------------------------------


class TestGenerateDefaultConfig:
    def test_returns_string(self):
        cfg = generate_default_config()
        assert isinstance(cfg, str)

    def test_contains_user_section(self):
        cfg = generate_default_config()
        assert "[user]" in cfg

    def test_contains_example_source(self):
        cfg = generate_default_config()
        assert "sources" in cfg.lower()

    def test_valid_toml(self):
        import tomllib
        raw = generate_default_config()
        # Should parse without error (strip comment-only example blocks)
        parsed = tomllib.loads(raw)
        assert "user" in parsed


# ---------------------------------------------------------------------------
# _parse_config (internal)
# ---------------------------------------------------------------------------


class TestParseConfig:
    def test_empty_dict(self):
        cfg = _parse_config({})
        assert cfg.user.name == "Beacon User"
        assert cfg.sources == []

    def test_user_parsed(self):
        raw = {
            "user": {
                "name": "Alice",
                "email": "alice@example.com",
                "timezone": "America/Chicago",
            }
        }
        cfg = _parse_config(raw)
        assert cfg.user.name == "Alice"
        assert cfg.user.email == "alice@example.com"
        assert cfg.user.timezone == "America/Chicago"

    def test_sources_parsed(self):
        raw = {
            "sources": [
                {"name": "gh", "type": "github", "enabled": True, "token": "tok"},
                {"name": "cal", "type": "calendar", "enabled": False},
            ]
        }
        cfg = _parse_config(raw)
        assert len(cfg.sources) == 2
        gh = cfg.get_source("gh")
        assert gh is not None
        assert gh.type == "github"
        assert gh.enabled is True
        assert gh.config["token"] == "tok"

        cal = cfg.get_source("cal")
        assert cal is not None
        assert cal.enabled is False

    def test_raw_preserved(self):
        raw = {"user": {"name": "X"}, "custom_key": "hello"}
        cfg = _parse_config(raw)
        assert cfg.raw["custom_key"] == "hello"


# ---------------------------------------------------------------------------
# find_config_file
# ---------------------------------------------------------------------------


class TestFindConfigFile:
    def test_explicit_path_exists(self, tmp_path):
        p = tmp_path / "my.toml"
        p.touch()
        result = find_config_file(p)
        assert result == p.resolve()

    def test_explicit_path_missing_returns_none(self, tmp_path):
        result = find_config_file(tmp_path / "nope.toml")
        assert result is None

    def test_no_config_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        result = find_config_file()
        assert result is None

    def test_finds_local_beacon_toml(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        p = tmp_path / "beacon.toml"
        p.write_text("[user]\nname='X'\n", encoding="utf-8")
        result = find_config_file()
        assert result is not None
        assert result.name == "beacon.toml"


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------


class TestLoadConfig:
    def test_no_file_returns_default(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg = load_config()
        assert isinstance(cfg, BeaconConfig)
        assert cfg.sources == []

    def test_loads_from_path(self, tmp_path):
        p = _write_toml(
            tmp_path,
            """\
            [user]
            name = "Bob"
            email = "bob@example.com"
            timezone = "UTC"

            [[sources]]
            name = "github"
            type = "github"
            enabled = true
            token = "ghp_test"
            """,
        )
        cfg = load_config(p)
        assert cfg.user.name == "Bob"
        assert len(cfg.sources) == 1
        assert cfg.sources[0].config["token"] == "ghp_test"

    def test_malformed_toml_raises(self, tmp_path):
        p = tmp_path / "beacon.toml"
        p.write_text("[[[[invalid", encoding="utf-8")
        with pytest.raises(ConfigError, match="Failed to load config"):
            load_config(p)

    def test_enabled_sources_filter(self, tmp_path):
        p = _write_toml(
            tmp_path,
            """\
            [[sources]]
            name = "a"
            type = "github"
            enabled = true

            [[sources]]
            name = "b"
            type = "calendar"
            enabled = false
            """,
        )
        cfg = load_config(p)
        enabled = cfg.enabled_sources()
        assert len(enabled) == 1
        assert enabled[0].name == "a"

    def test_get_source_not_found(self, tmp_path):
        p = _write_toml(tmp_path, "[user]\nname='X'\n")
        cfg = load_config(p)
        assert cfg.get_source("nope") is None


# ---------------------------------------------------------------------------
# write_default_config
# ---------------------------------------------------------------------------


class TestWriteDefaultConfig:
    def test_writes_file(self, tmp_path):
        target = tmp_path / "beacon.toml"
        result = write_default_config(target)
        assert result == target
        assert target.exists()

    def test_creates_parent_dirs(self, tmp_path):
        target = tmp_path / "subdir" / "beacon" / "beacon.toml"
        write_default_config(target)
        assert target.exists()

    def test_raises_if_file_exists(self, tmp_path):
        target = tmp_path / "beacon.toml"
        target.touch()
        with pytest.raises(ConfigError, match="already exists"):
            write_default_config(target)

    def test_written_content_is_valid_toml(self, tmp_path):
        import tomllib

        target = tmp_path / "beacon.toml"
        write_default_config(target)
        with open(target, "rb") as fh:
            parsed = tomllib.load(fh)
        assert "user" in parsed


# ---------------------------------------------------------------------------
# BeaconConfig helpers
# ---------------------------------------------------------------------------


class TestBeaconConfig:
    def test_get_source_returns_correct(self):
        cfg = BeaconConfig(
            sources=[
                SourceConfig(name="a", type="github"),
                SourceConfig(name="b", type="calendar"),
            ]
        )
        assert cfg.get_source("b").type == "calendar"

    def test_get_source_missing(self):
        cfg = BeaconConfig()
        assert cfg.get_source("x") is None

    def test_enabled_sources(self):
        cfg = BeaconConfig(
            sources=[
                SourceConfig(name="a", type="github", enabled=True),
                SourceConfig(name="b", type="calendar", enabled=False),
            ]
        )
        enabled = cfg.enabled_sources()
        assert len(enabled) == 1
        assert enabled[0].name == "a"
