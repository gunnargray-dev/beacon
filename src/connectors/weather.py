"""Weather connector -- current conditions and 3-day forecast via wttr.in."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from src.connectors.base import BaseConnector, ConnectorError, registry
from src.models import ActionItem, Event, Source, SourceType

_WTTR_BASE = "https://wttr.in"


def _fetch_weather(location: str) -> dict[str, Any]:
    """Fetch weather JSON from wttr.in for the given location."""
    encoded = urllib.parse.quote(location, safe="")
    url = f"{_WTTR_BASE}/{encoded}?format=j1"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Beacon/0.1 (weather; +https://github.com/gunnargray-dev/beacon)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ConnectorError(
            f"Weather fetch error {exc.code} for {location!r}: {exc.reason}"
        ) from exc
    except urllib.error.URLError as exc:
        raise ConnectorError(f"Weather network error for {location!r}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ConnectorError(f"Invalid JSON from wttr.in for {location!r}: {exc}") from exc


def _c_to_f(celsius: str) -> str:
    """Convert Celsius string to Fahrenheit string."""
    try:
        f = int(celsius) * 9 / 5 + 32
        return f"{f:.0f}"
    except (ValueError, TypeError):
        return celsius


def _parse_current(data: dict[str, Any], source_id: str, location: str) -> Event | None:
    """Parse current_condition from wttr.in JSON into an Event."""
    conditions = data.get("current_condition", [])
    if not conditions:
        return None
    cond = conditions[0]
    temp_c = cond.get("temp_C", "?")
    temp_f = cond.get("temp_F", _c_to_f(temp_c))
    humidity = cond.get("humidity", "?")
    feels_c = cond.get("FeelsLikeC", "?")
    feels_f = cond.get("FeelsLikeF", _c_to_f(feels_c))
    wind_kmph = cond.get("windspeedKmph", "?")
    desc = ""
    weather_descs = cond.get("weatherDesc", [])
    if weather_descs:
        desc = weather_descs[0].get("value", "")

    summary = (
        f"{desc} | {temp_c}°C ({temp_f}°F), feels like {feels_c}°C ({feels_f}°F), "
        f"humidity {humidity}%, wind {wind_kmph} km/h"
    )
    return Event(
        title=f"Weather in {location}: {desc} {temp_c}°C",
        source_id=source_id,
        source_type=SourceType.WEATHER,
        occurred_at=datetime.now(tz=timezone.utc),
        summary=summary,
        url=f"https://wttr.in/{location}",
        metadata={
            "type": "current",
            "location": location,
            "temp_c": temp_c,
            "temp_f": temp_f,
            "humidity": humidity,
            "description": desc,
            "wind_kmph": wind_kmph,
        },
    )


def _parse_forecast(data: dict[str, Any], source_id: str, location: str) -> list[Event]:
    """Parse weather[] forecast days from wttr.in JSON into Events."""
    events: list[Event] = []
    for day in data.get("weather", [])[:3]:
        date_str = day.get("date", "")
        max_c = day.get("maxtempC", "?")
        min_c = day.get("mintempC", "?")
        max_f = day.get("maxtempF", _c_to_f(max_c))
        min_f = day.get("mintempF", _c_to_f(min_c))

        desc = ""
        for hourly in day.get("hourly", []):
            descs = hourly.get("weatherDesc", [])
            if descs:
                desc = descs[0].get("value", "")
                break

        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            dt = datetime.now(tz=timezone.utc)

        summary = f"{desc} | High: {max_c}°C ({max_f}°F), Low: {min_c}°C ({min_f}°F)"
        events.append(
            Event(
                title=f"Forecast {date_str} in {location}: {desc} {max_c}/{min_c}°C",
                source_id=source_id,
                source_type=SourceType.WEATHER,
                occurred_at=dt,
                summary=summary,
                url=f"https://wttr.in/{location}",
                metadata={
                    "type": "forecast",
                    "location": location,
                    "date": date_str,
                    "max_c": max_c,
                    "min_c": min_c,
                    "description": desc,
                },
            )
        )
    return events


# ---------------------------------------------------------------------------
# Connector
# ---------------------------------------------------------------------------


@registry.register
class WeatherConnector(BaseConnector):
    """Connector for weather data via the wttr.in free API (no key required)."""

    connector_type = SourceType.WEATHER

    def validate_config(self) -> bool:
        return bool(self.get_config("location"))

    def test_connection(self) -> bool:
        if not self.validate_config():
            return False
        try:
            _fetch_weather(self.get_config("location"))
            return True
        except ConnectorError:
            return False

    def sync(self) -> tuple[list[Event], list[ActionItem]]:
        if not self.validate_config():
            raise ConnectorError("Weather connector requires 'location' in config")

        location: str = self.get_config("location")
        data = _fetch_weather(location)

        events: list[Event] = []
        current = _parse_current(data, self.source.id, location)
        if current:
            events.append(current)
        events.extend(_parse_forecast(data, self.source.id, location))

        return events, []
