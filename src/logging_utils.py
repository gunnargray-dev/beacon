"""Structured logging utilities.

Beacon is intentionally dependency-free for core logic; this module provides
lightweight JSON log formatting using only the standard library.

The goal is to make logs machine-readable (for grepping, ingestion, and
correlation) while keeping call sites simple.
"""

from __future__ import annotations

import json
import logging
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping


def new_request_id() -> str:
    """Return a new request id suitable for correlating log lines."""

    return uuid.uuid4().hex


@dataclass(frozen=True)
class LogContext:
    """Context attached to a series of log lines (e.g., a sync run)."""

    request_id: str


class JsonFormatter(logging.Formatter):
    """Format log records as one-line JSON objects."""

    def __init__(self, *, ctx: LogContext | None = None) -> None:
        super().__init__()
        self._ctx = ctx

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        if self._ctx is not None:
            payload["request_id"] = self._ctx.request_id

        extra = getattr(record, "extra", None)
        if isinstance(extra, Mapping):
            payload.update(dict(extra))

        if record.exc_info:
            payload["exc_type"] = record.exc_info[0].__name__
            payload["exc"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def setup_json_logging(
    *,
    level: str | int = "INFO",
    ctx: LogContext | None = None,
    stream: Any = None,
) -> logging.Logger:
    """Configure root logger for JSON output.

    This is intentionally minimal: it removes existing handlers to avoid duplicate
    logs and sets a single StreamHandler with JsonFormatter.
    """

    root = logging.getLogger()
    root.handlers.clear()

    if isinstance(level, str):
        resolved = getattr(logging, level.upper(), logging.INFO)
    else:
        resolved = int(level)
    root.setLevel(resolved)

    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setLevel(resolved)
    handler.setFormatter(JsonFormatter(ctx=ctx))
    root.addHandler(handler)
    return root
