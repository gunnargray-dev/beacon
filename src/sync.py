"""Sync pipeline helpers.

This module centralizes the logic for syncing enabled sources so both the
one-shot CLI (`beacon sync`) and daemon mode (`beacon sync --daemon`) can share
behavior.

Key goals:
- Connector-level retry integration for transient failures
- Consistent structured logging with request IDs
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.connectors.base import ConnectorError, registry as connector_registry
from src.logging_utils import LogContext, new_request_id, setup_json_logging
from src.models import ActionItem, Event, Source, SourceType
from src.retry import RetryPolicy, retry_call


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SyncResult:
    events: list[Event]
    action_items: list[ActionItem]
    any_error: bool
    request_id: str
    started_at: str
    finished_at: str


def _is_transient_error(exc: Exception) -> bool:
    """Classify errors that are likely transient and worth retrying."""

    # We keep this intentionally conservative. Most connector failures raise
    # ConnectorError with a user-facing message, but for transient infrastructure
    # issues (timeouts, connection resets, rate limits) we want to retry.
    transient_tokens = (
        "timeout",
        "timed out",
        "temporarily",
        "temporary",
        "connection reset",
        "connection aborted",
        "connection refused",
        "429",
        "rate limit",
        "too many requests",
        "service unavailable",
        "502",
        "503",
        "504",
    )

    msg = str(exc).lower()
    if any(tok in msg for tok in transient_tokens):
        return True

    # If a connector wraps a lower-level network exception, it will usually be
    # present as __cause__ or __context__. We use message-based detection.
    cause = getattr(exc, "__cause__", None)
    if cause is not None and any(tok in str(cause).lower() for tok in transient_tokens):
        return True

    context = getattr(exc, "__context__", None)
    if context is not None and any(tok in str(context).lower() for tok in transient_tokens):
        return True

    return False


def sync_enabled_sources(
    enabled_sources: list[Any],
    *,
    request_id: str | None = None,
    policy: RetryPolicy | None = None,
    json_logs: bool = False,
    log_level: str = "INFO",
) -> SyncResult:
    """Sync a list of enabled source configs.

    enabled_sources are config "source" objects (from Config.sources) that have
    name/type/enabled/config fields.
    """

    started = datetime.now(tz=timezone.utc)
    rid = request_id or new_request_id()

    if json_logs:
        setup_json_logging(level=log_level, ctx=LogContext(request_id=rid))

    all_events: list[Event] = []
    all_actions: list[ActionItem] = []
    any_error = False

    for src_cfg in enabled_sources:
        logger.info(
            "sync_start",
            extra={
                "extra": {
                    "source_name": getattr(src_cfg, "name", None),
                    "source_type": getattr(src_cfg, "type", None),
                }
            },
        )

        try:
            src_type = SourceType(getattr(src_cfg, "type"))
        except ValueError:
            logger.warning(
                "sync_skip_unknown_source_type",
                extra={
                    "extra": {
                        "source_name": getattr(src_cfg, "name", None),
                        "source_type": getattr(src_cfg, "type", None),
                    }
                },
            )
            continue

        connector_cls = connector_registry.get(src_type)
        if connector_cls is None:
            logger.warning(
                "sync_skip_unregistered_connector",
                extra={
                    "extra": {
                        "source_name": getattr(src_cfg, "name", None),
                        "source_type": src_type.value,
                    }
                },
            )
            continue

        source = Source(
            name=getattr(src_cfg, "name"),
            source_type=src_type,
            enabled=getattr(src_cfg, "enabled"),
            config=getattr(src_cfg, "config"),
        )
        connector = connector_cls(source)

        if not connector.validate_config():
            logger.warning(
                "sync_skip_invalid_config",
                extra={
                    "extra": {
                        "source_name": source.name,
                        "source_type": source.source_type.value,
                        "connector": connector_cls.__name__,
                    }
                },
            )
            continue

        def _do_sync() -> tuple[list[Event], list[ActionItem]]:
            return connector.sync()

        def _on_retry(attempt: int, exc: Exception, delay: float) -> None:
            logger.warning(
                "sync_retry",
                extra={
                    "extra": {
                        "source_name": source.name,
                        "source_type": source.source_type.value,
                        "connector": connector_cls.__name__,
                        "attempt": attempt,
                        "delay_s": round(float(delay), 3),
                        "error": str(exc),
                    }
                },
            )

        try:
            events, actions = retry_call(
                _do_sync,
                policy=policy or RetryPolicy(),
                is_retryable=_is_transient_error,
                on_retry=_on_retry,
            )
            all_events.extend(events)
            all_actions.extend(actions)
            logger.info(
                "sync_done",
                extra={
                    "extra": {
                        "source_name": source.name,
                        "source_type": source.source_type.value,
                        "connector": connector_cls.__name__,
                        "events": len(events),
                        "action_items": len(actions),
                    }
                },
            )
        except ConnectorError as exc:
            logger.error(
                "sync_error",
                exc_info=True,
                extra={
                    "extra": {
                        "source_name": source.name,
                        "source_type": source.source_type.value,
                        "connector": connector_cls.__name__,
                        "error": str(exc),
                    }
                },
            )
            any_error = True
        except Exception as exc:  # noqa: BLE001
            # If a connector raised something else (bug or unexpected library
            # exception), we treat it as an error and keep going.
            logger.error(
                "sync_unhandled_error",
                exc_info=True,
                extra={
                    "extra": {
                        "source_name": source.name,
                        "source_type": source.source_type.value,
                        "connector": connector_cls.__name__,
                        "error": str(exc),
                    }
                },
            )
            any_error = True

    finished = datetime.now(tz=timezone.utc)
    return SyncResult(
        events=all_events,
        action_items=all_actions,
        any_error=any_error,
        request_id=rid,
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
    )
