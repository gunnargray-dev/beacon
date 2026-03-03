"""Configuration system for Beacon.

Loads and saves beacon.toml. Supports per-source config and default generation.
Config file is searched in the following order:
  1. Path provided explicitly
  2. ./beacon.toml (current directory)
  3. ~/.config/beacon/beacon.toml
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_DEFAULT_CONFIG_PATHS = [
    Path("beacon.toml"),
    Path.home() / ".config" / "beacon" / "beacon.toml",
]


@dataclass
class UserConfig:
    name: str = "Beacon User"
    email: str = ""
    timezone: str = "UTC"


@dataclass
class SourceConfig:
    """Configuration for a single source connector."""

    name: str
    type: str
    enabled: bool = True
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class BeaconConfig:
    """Root configuration object parsed from beacon.toml."""

    user: UserConfig = field(default_factory=UserConfig)
    sources: list[SourceConfig] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def get_source(self, name: str) -> SourceConfig | None:
        """Return the SourceConfig with the given name, or None."""
        for src in self.sources:
            if src.name == name:
                return src
        return None

    def enabled_sources(self) -> list[SourceConfig]:
        return [s for s in self.sources if s.enabled]


class ConfigError(Exception):
    """Raised when configuration cannot be loaded or is invalid."""


def find_config_file(path: str | Path | None = None) -> Path | None:
    """Locate the beacon.toml file.

    Args:
        path: Explicit path to use. If None, searches default locations.

    Returns:
        Resolved Path if found, None otherwise.
    """
    if path is not None:
        p = Path(path).expanduser().resolve()
        return p if p.exists() else None

    for candidate in _DEFAULT_CONFIG_PATHS:
        resolved = candidate.expanduser().resolve()
        if resolved.exists():
            return resolved

    return None


def load_config(path: str | Path | None = None) -> BeaconConfig:
    """Load and parse beacon.toml.

    Args:
        path: Explicit config file path. If None, searches default locations.

    Returns:
        BeaconConfig populated from the file.

    Raises:
        ConfigError if the file cannot be found or is malformed.
    """
    config_path = find_config_file(path)
    if config_path is None:
        return BeaconConfig()

    try:
        with open(config_path, "rb") as fh:
            raw = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"Failed to load config from {config_path}: {exc}") from exc

    return _parse_config(raw)


def _parse_config(raw: dict[str, Any]) -> BeaconConfig:
    """Parse a raw TOML dict into a BeaconConfig."""
    user_raw = raw.get("user", {})
    user = UserConfig(
        name=user_raw.get("name", "Beacon User"),
        email=user_raw.get("email", ""),
        timezone=user_raw.get("timezone", "UTC"),
    )

    sources: list[SourceConfig] = []
    for src_raw in raw.get("sources", []):
        name = src_raw.get("name", "")
        src_type = src_raw.get("type", "custom")
        enabled = src_raw.get("enabled", True)
        # Everything else is per-source connector config
        config = {k: v for k, v in src_raw.items() if k not in ("name", "type", "enabled")}
        sources.append(SourceConfig(name=name, type=src_type, enabled=enabled, config=config))

    return BeaconConfig(user=user, sources=sources, raw=raw)


def generate_default_config() -> str:
    """Return a default beacon.toml as a string."""
    return """\
# Beacon Configuration
# Place this file at ./beacon.toml or ~/.config/beacon/beacon.toml

[user]
name = "Your Name"
email = "you@example.com"
timezone = "America/New_York"

# Add sources below. Each [[sources]] block configures one connector.
# Example GitHub source:
# [[sources]]
# name = "github"
# type = "github"
# enabled = true
# token = "ghp_..."

# Example Calendar source:
# [[sources]]
# name = "calendar"
# type = "calendar"
# enabled = true
# calendar_id = "primary"
"""


def write_default_config(path: str | Path | None = None) -> Path:
    """Write a default beacon.toml to the given path (or ~/.config/beacon/beacon.toml).

    Args:
        path: Target file path. Defaults to ~/.config/beacon/beacon.toml.

    Returns:
        The Path that was written.

    Raises:
        ConfigError if the file already exists (won't overwrite).
    """
    if path is None:
        target = Path.home() / ".config" / "beacon" / "beacon.toml"
    else:
        target = Path(path).expanduser().resolve()

    if target.exists():
        raise ConfigError(f"Config file already exists at {target}. Remove it first.")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(generate_default_config(), encoding="utf-8")
    return target
