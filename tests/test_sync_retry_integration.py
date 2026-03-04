from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.connectors.base import BaseConnector, ConnectorError, registry
from src.models import ActionItem, Event, Priority, Source, SourceType
from src.retry import RetryPolicy
from src.sync import sync_enabled_sources


@dataclass
class _Cfg:
    name: str
    type: str
    enabled: bool
    config: dict


class _TransientConnector(BaseConnector):
    connector_type = SourceType.GITHUB

    def __init__(self, source: Source) -> None:
        super().__init__(source)
        self.calls = 0

    def validate_config(self) -> bool:
        return True

    def sync(self) -> tuple[list[Event], list[ActionItem]]:
        self.calls += 1
        if self.calls < 3:
            raise ConnectorError("Timeout while calling API")
        return (
            [
                Event(
                    title="ok",
                    source_id=self.source.name,
                    source_type=self.source.source_type,
                    occurred_at=__import__("datetime").datetime.now(tz=__import__("datetime").timezone.utc),
                    id="e1",
                )
            ],
            [
                ActionItem(
                    id="a1",
                    title="do",
                    source_id=self.source.name,
                    source_type=self.source.source_type,
                    priority=Priority.MEDIUM,
                )
            ],
        )


class _PermanentConnector(BaseConnector):
    connector_type = SourceType.EMAIL

    def validate_config(self) -> bool:
        return True

    def sync(self) -> tuple[list[Event], list[ActionItem]]:
        raise ConnectorError("Invalid API token")


def test_sync_enabled_sources_retries_transient_connector_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    registry.clear()
    registry.register(_TransientConnector)

    # avoid actual sleeping
    import src.retry as retry_mod

    monkeypatch.setattr(retry_mod.time, "sleep", lambda _s: None)

    cfg = _Cfg(name="gh", type=SourceType.GITHUB.value, enabled=True, config={})
    res = sync_enabled_sources([cfg], policy=RetryPolicy(max_attempts=5, base_delay_s=0.0, jitter_s=0.0))
    assert not res.any_error
    assert len(res.events) == 1
    assert len(res.action_items) == 1


def test_sync_enabled_sources_does_not_retry_permanent_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    registry.clear()
    registry.register(_PermanentConnector)

    import src.retry as retry_mod

    monkeypatch.setattr(retry_mod.time, "sleep", lambda _s: None)

    cfg = _Cfg(name="em", type=SourceType.EMAIL.value, enabled=True, config={})
    res = sync_enabled_sources([cfg], policy=RetryPolicy(max_attempts=5, base_delay_s=0.0, jitter_s=0.0))
    assert res.any_error
    assert res.events == []
    assert res.action_items == []
