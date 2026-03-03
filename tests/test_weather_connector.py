"""Tests for the Weather connector."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.connectors.base import ConnectorError
from src.connectors.weather import (
    WeatherConnector,
    _c_to_f,
    _fetch_weather,
    _parse_current,
    _parse_forecast,
)
from src.models import Event, Source, SourceType


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_WEATHER = {
    "current_condition": [
        {
            "temp_C": "15",
            "temp_F": "59",
            "humidity": "72",
            "FeelsLikeC": "13",
            "FeelsLikeF": "55",
            "windspeedKmph": "20",
            "weatherDesc": [{"value": "Partly cloudy"}],
        }
    ],
    "weather": [
        {
            "date": "2024-01-01",
            "maxtempC": "18",
            "mintempC": "10",
            "maxtempF": "64",
            "mintempF": "50",
            "hourly": [{"weatherDesc": [{"value": "Sunny"}]}],
        },
        {
            "date": "2024-01-02",
            "maxtempC": "16",
            "mintempC": "8",
            "maxtempF": "61",
            "mintempF": "46",
            "hourly": [{"weatherDesc": [{"value": "Cloudy"}]}],
        },
        {
            "date": "2024-01-03",
            "maxtempC": "12",
            "mintempC": "5",
            "maxtempF": "54",
            "mintempF": "41",
            "hourly": [{"weatherDesc": [{"value": "Rain"}]}],
        },
    ],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_source(config: dict | None = None) -> Source:
    return Source(
        name="test-weather",
        source_type=SourceType.WEATHER,
        config=config or {},
    )


def _make_connector(config: dict | None = None) -> WeatherConnector:
    if config is None:
        config = {"location": "London"}
    return WeatherConnector(_make_source(config))


def _mock_urlopen(data: dict):
    response = MagicMock()
    response.read.return_value = json.dumps(data).encode()
    response.__enter__ = lambda s: s
    response.__exit__ = MagicMock(return_value=False)
    return response


# ---------------------------------------------------------------------------
# _c_to_f
# ---------------------------------------------------------------------------


class TestCToF:
    def test_zero_celsius(self):
        assert _c_to_f("0") == "32"

    def test_hundred_celsius(self):
        assert _c_to_f("100") == "212"

    def test_negative_celsius(self):
        assert _c_to_f("-10") == "14"

    def test_invalid_returns_input(self):
        assert _c_to_f("abc") == "abc"

    def test_empty_returns_input(self):
        assert _c_to_f("") == ""


# ---------------------------------------------------------------------------
# _parse_current
# ---------------------------------------------------------------------------


class TestParseCurrent:
    def test_returns_event(self):
        event = _parse_current(SAMPLE_WEATHER, "src-id", "London")
        assert isinstance(event, Event)
        assert "London" in event.title
        assert event.source_type == SourceType.WEATHER

    def test_includes_temp_in_title(self):
        event = _parse_current(SAMPLE_WEATHER, "src-id", "London")
        assert "15" in event.title  # temp_C

    def test_includes_description_in_title(self):
        event = _parse_current(SAMPLE_WEATHER, "src-id", "London")
        assert "Partly cloudy" in event.title

    def test_summary_contains_humidity(self):
        event = _parse_current(SAMPLE_WEATHER, "src-id", "London")
        assert "72" in event.summary  # humidity

    def test_metadata_type_is_current(self):
        event = _parse_current(SAMPLE_WEATHER, "src-id", "London")
        assert event.metadata.get("type") == "current"

    def test_returns_none_when_no_current_condition(self):
        data = {"current_condition": [], "weather": []}
        result = _parse_current(data, "src-id", "London")
        assert result is None


# ---------------------------------------------------------------------------
# _parse_forecast
# ---------------------------------------------------------------------------


class TestParseForecast:
    def test_returns_three_events(self):
        events = _parse_forecast(SAMPLE_WEATHER, "src-id", "London")
        assert len(events) == 3

    def test_event_type_is_forecast(self):
        events = _parse_forecast(SAMPLE_WEATHER, "src-id", "London")
        assert all(ev.metadata.get("type") == "forecast" for ev in events)

    def test_event_dates_are_correct(self):
        events = _parse_forecast(SAMPLE_WEATHER, "src-id", "London")
        assert events[0].occurred_at == datetime(2024, 1, 1, tzinfo=timezone.utc)
        assert events[1].occurred_at == datetime(2024, 1, 2, tzinfo=timezone.utc)

    def test_event_titles_contain_location(self):
        events = _parse_forecast(SAMPLE_WEATHER, "src-id", "Paris")
        assert all("Paris" in ev.title for ev in events)

    def test_source_type_is_weather(self):
        events = _parse_forecast(SAMPLE_WEATHER, "src-id", "London")
        assert all(ev.source_type == SourceType.WEATHER for ev in events)

    def test_empty_forecast_returns_empty(self):
        data = {"current_condition": [], "weather": []}
        events = _parse_forecast(data, "src-id", "London")
        assert events == []

    def test_max_three_days(self):
        data = dict(SAMPLE_WEATHER)
        data["weather"] = SAMPLE_WEATHER["weather"] + [
            {"date": "2024-01-04", "maxtempC": "20", "mintempC": "10", "hourly": []},
            {"date": "2024-01-05", "maxtempC": "20", "mintempC": "10", "hourly": []},
        ]
        events = _parse_forecast(data, "src-id", "London")
        assert len(events) == 3  # capped at 3


# ---------------------------------------------------------------------------
# WeatherConnector.validate_config
# ---------------------------------------------------------------------------


class TestValidateConfig:
    def test_valid_location(self):
        conn = _make_connector({"location": "Berlin"})
        assert conn.validate_config() is True

    def test_missing_location(self):
        conn = WeatherConnector(_make_source({}))
        assert conn.validate_config() is False

    def test_empty_location(self):
        conn = WeatherConnector(_make_source({"location": ""}))
        assert conn.validate_config() is False


# ---------------------------------------------------------------------------
# WeatherConnector.test_connection
# ---------------------------------------------------------------------------


class TestTestConnection:
    def test_returns_true_on_success(self):
        conn = _make_connector()
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(SAMPLE_WEATHER)):
            assert conn.test_connection() is True

    def test_returns_false_when_config_invalid(self):
        conn = WeatherConnector(_make_source({}))
        assert conn.test_connection() is False

    def test_returns_false_on_network_error(self):
        import urllib.error
        conn = _make_connector()
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
            assert conn.test_connection() is False


# ---------------------------------------------------------------------------
# WeatherConnector.sync
# ---------------------------------------------------------------------------


class TestSync:
    def test_sync_returns_four_events(self):
        """1 current + 3 forecast = 4 events."""
        conn = _make_connector()
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(SAMPLE_WEATHER)):
            events, action_items = conn.sync()
        assert len(events) == 4
        assert action_items == []

    def test_sync_first_event_is_current(self):
        conn = _make_connector()
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(SAMPLE_WEATHER)):
            events, _ = conn.sync()
        assert events[0].metadata.get("type") == "current"

    def test_sync_forecast_events_are_last_three(self):
        conn = _make_connector()
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(SAMPLE_WEATHER)):
            events, _ = conn.sync()
        assert all(ev.metadata.get("type") == "forecast" for ev in events[1:])

    def test_sync_raises_on_network_error(self):
        import urllib.error
        conn = _make_connector()
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
            with pytest.raises(ConnectorError):
                conn.sync()

    def test_sync_raises_when_config_invalid(self):
        conn = WeatherConnector(_make_source({}))
        with pytest.raises(ConnectorError, match="location"):
            conn.sync()

    def test_sync_with_no_current_condition(self):
        data = {"current_condition": [], "weather": SAMPLE_WEATHER["weather"]}
        conn = _make_connector()
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(data)):
            events, _ = conn.sync()
        # No current event, only forecast
        assert len(events) == 3
