"""Tests for the connector plugin architecture."""

from __future__ import annotations

import pytest

from src.connectors.base import (
    BaseConnector,
    ConnectorError,
    ConnectorRegistry,
)
from src.models import ActionItem, Event, Source, SourceType


# ---------------------------------------------------------------------------
# Minimal concrete connector for testing
# ---------------------------------------------------------------------------


class _FakeConnector(BaseConnector):
    connector_type = SourceType.GITHUB

    def validate_config(self) -> bool:
        return bool(self.source.config.get("token"))

    def sync(self) -> tuple[list[Event], list[ActionItem]]:
        return [], []


class _AlwaysValidConnector(BaseConnector):
    connector_type = SourceType.CALENDAR

    def validate_config(self) -> bool:
        return True

    def sync(self) -> tuple[list[Event], list[ActionItem]]:
        return [], []


# ---------------------------------------------------------------------------
# BaseConnector
# ---------------------------------------------------------------------------


class TestBaseConnector:
    def _make_source(self, config=None) -> Source:
        return Source(
            name="test-gh",
            source_type=SourceType.GITHUB,
            config=config or {},
        )

    def test_instantiation(self):
        src = self._make_source({"token": "abc"})
        conn = _FakeConnector(src)
        assert conn.source is src

    def test_validate_config_returns_false_missing_token(self):
        conn = _FakeConnector(self._make_source())
        assert conn.validate_config() is False

    def test_validate_config_returns_true_with_token(self):
        conn = _FakeConnector(self._make_source({"token": "tok_xyz"}))
        assert conn.validate_config() is True

    def test_test_connection_delegates_to_validate_config(self):
        conn = _FakeConnector(self._make_source({"token": "t"}))
        assert conn.test_connection() is True

    def test_test_connection_false_when_invalid(self):
        conn = _FakeConnector(self._make_source())
        assert conn.test_connection() is False

    def test_get_config(self):
        conn = _FakeConnector(self._make_source({"token": "t", "org": "acme"}))
        assert conn.get_config("token") == "t"
        assert conn.get_config("org") == "acme"

    def test_get_config_default(self):
        conn = _FakeConnector(self._make_source())
        assert conn.get_config("missing") is None
        assert conn.get_config("missing", "fallback") == "fallback"

    def test_sync_returns_empty_lists(self):
        conn = _FakeConnector(self._make_source({"token": "t"}))
        events, actions = conn.sync()
        assert events == []
        assert actions == []

    def test_repr(self):
        conn = _FakeConnector(self._make_source())
        assert "_FakeConnector" in repr(conn)
        assert "test-gh" in repr(conn)

    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            BaseConnector(self._make_source())  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# ConnectorRegistry
# ---------------------------------------------------------------------------


class TestConnectorRegistry:
    def setup_method(self):
        self.reg = ConnectorRegistry()

    def test_register_and_get(self):
        self.reg.register(_FakeConnector)
        cls = self.reg.get(SourceType.GITHUB)
        assert cls is _FakeConnector

    def test_get_unregistered_returns_none(self):
        assert self.reg.get(SourceType.GITHUB) is None

    def test_register_as_decorator(self):
        @self.reg.register
        class MyConnector(BaseConnector):
            connector_type = SourceType.WEATHER

            def validate_config(self):
                return True

            def sync(self):
                return [], []

        assert self.reg.get(SourceType.WEATHER) is MyConnector

    def test_register_duplicate_raises(self):
        self.reg.register(_FakeConnector)
        with pytest.raises(ValueError, match="already registered"):
            self.reg.register(_FakeConnector)

    def test_register_missing_connector_type_raises(self):
        class BadConnector(BaseConnector):
            def validate_config(self):
                return True

            def sync(self):
                return [], []

        with pytest.raises(ValueError, match="connector_type"):
            self.reg.register(BadConnector)

    def test_available(self):
        self.reg.register(_FakeConnector)
        self.reg.register(_AlwaysValidConnector)
        avail = self.reg.available()
        assert SourceType.GITHUB in avail
        assert SourceType.CALENDAR in avail

    def test_all(self):
        self.reg.register(_FakeConnector)
        result = self.reg.all()
        assert SourceType.GITHUB in result
        # all() returns a copy — mutations don't affect registry
        result[SourceType.EMAIL] = _FakeConnector
        assert self.reg.get(SourceType.EMAIL) is None

    def test_unregister(self):
        self.reg.register(_FakeConnector)
        self.reg.unregister(SourceType.GITHUB)
        assert self.reg.get(SourceType.GITHUB) is None

    def test_unregister_nonexistent_noop(self):
        self.reg.unregister(SourceType.GITHUB)  # should not raise

    def test_clear(self):
        self.reg.register(_FakeConnector)
        self.reg.register(_AlwaysValidConnector)
        self.reg.clear()
        assert len(self.reg) == 0

    def test_len(self):
        assert len(self.reg) == 0
        self.reg.register(_FakeConnector)
        assert len(self.reg) == 1

    def test_repr(self):
        self.reg.register(_FakeConnector)
        r = repr(self.reg)
        assert "ConnectorRegistry" in r
        assert "github" in r

    def test_load_from_nonexistent_package_noop(self):
        self.reg.load_from_package("src.connectors.nonexistent_xyz")
        assert len(self.reg) == 0


# ---------------------------------------------------------------------------
# ConnectorError
# ---------------------------------------------------------------------------


class TestConnectorError:
    def test_raise_and_catch(self):
        with pytest.raises(ConnectorError, match="boom"):
            raise ConnectorError("boom")

    def test_is_exception(self):
        assert issubclass(ConnectorError, Exception)
