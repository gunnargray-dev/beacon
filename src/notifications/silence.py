"""Smart silence — focus/quiet hours check for Beacon notifications.

Config in beacon.toml:

    [notifications.silence]
    enabled = true

    [[notifications.silence.windows]]
    name = "focus"
    start_hour = 9
    end_hour = 12
    days = ["mon", "tue", "wed", "thu", "fri"]

    [[notifications.silence.windows]]
    name = "quiet"
    start_hour = 22
    end_hour = 7
    days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

_DAY_MAP = {
    "mon": 0, "monday": 0,
    "tue": 1, "tuesday": 1,
    "wed": 2, "wednesday": 2,
    "thu": 3, "thursday": 3,
    "fri": 4, "friday": 4,
    "sat": 5, "saturday": 5,
    "sun": 6, "sunday": 6,
}


@dataclass
class SilenceWindow:
    """A single time window during which notifications are silenced.

    start_hour and end_hour are 0–23 (inclusive).
    If start_hour > end_hour the window wraps midnight
    (e.g. start=22, end=7 means 22:00–07:00 next day).
    days: list of lowercase day names or abbreviations (mon, tue, ...).
    An empty days list matches every day.
    """

    start_hour: int
    end_hour: int
    name: str = ""
    days: list[str] = field(default_factory=list)

    def _day_matches(self, weekday: int) -> bool:
        """Return True if weekday (0=Mon) is in the configured days."""
        if not self.days:
            return True
        return weekday in {_DAY_MAP.get(d.lower(), -1) for d in self.days}

    def contains(self, dt: datetime) -> bool:
        """Return True if *dt* falls within this silence window."""
        if not self._day_matches(dt.weekday()):
            return False
        h = dt.hour
        if self.start_hour <= self.end_hour:
            # Normal window (e.g. 9–12, 14–18)
            return self.start_hour <= h < self.end_hour
        else:
            # Overnight window (e.g. 22–7: 22:00 through 06:59)
            return h >= self.start_hour or h < self.end_hour


@dataclass
class SilenceConfig:
    """Aggregated silence configuration."""

    enabled: bool = True
    windows: list[SilenceWindow] = field(default_factory=list)

    def is_silenced(self, dt: datetime | None = None) -> bool:
        """Return True if *dt* (default: now) falls within any silence window."""
        if not self.enabled:
            return False
        if dt is None:
            dt = datetime.now()
        return any(w.contains(dt) for w in self.windows)


def is_silenced(
    config: dict[str, Any] | SilenceConfig | None = None,
    dt: datetime | None = None,
) -> bool:
    """Top-level helper: return True if current time (or *dt*) is silenced.

    *config* may be:
      - A ``SilenceConfig`` instance
      - A raw beacon.toml dict (reads ``config["notifications"]["silence"]``)
      - None (returns False — not silenced)
    """
    if config is None:
        return False
    if isinstance(config, SilenceConfig):
        return config.is_silenced(dt)
    # Raw dict from beacon.toml
    silence_cfg = load_silence_config(config)
    return silence_cfg.is_silenced(dt)


def load_silence_config(raw_config: dict[str, Any]) -> SilenceConfig:
    """Parse silence config from a raw beacon.toml dict."""
    notifications = raw_config.get("notifications", {})
    silence_raw = notifications.get("silence", {})

    enabled = silence_raw.get("enabled", True)
    windows: list[SilenceWindow] = []
    for w in silence_raw.get("windows", []):
        windows.append(
            SilenceWindow(
                name=w.get("name", ""),
                start_hour=int(w.get("start_hour", 0)),
                end_hour=int(w.get("end_hour", 0)),
                days=list(w.get("days", [])),
            )
        )
    return SilenceConfig(enabled=enabled, windows=windows)
