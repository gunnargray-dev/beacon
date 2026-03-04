"""Export helpers that read from the Beacon SQLite store.

This module is stdlib-only (no runtime dependencies beyond the Beacon core).

Usage::

    from src.store_export.exporter import export_store_query
    path = export_store_query(store, fmt="json")

The ``build_store_export_payload`` function produces a plain dict that the
existing ``src.advanced.export.export_report`` renderer can consume.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.store import BeaconStore, dump_action_item, dump_event


# -------------------------------------------------------------------
# Payload builder
# -------------------------------------------------------------------


def build_store_export_payload(
    store: BeaconStore,
    *,
    source_type: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 5000,
) -> dict[str, Any]:
    """Query the store and build a dict suitable for ``export_report``.

    Returns a dict with keys:
        generated_at, event_count, action_item_count, events, action_items
    """
    events = store.query_events(
        source_type=source_type,
        since=since,
        until=until,
        limit=limit,
    )
    actions = store.query_action_items(
        source_type=source_type,
        limit=limit,
    )

    return {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "event_count": len(events),
        "action_item_count": len(actions),
        "events": [dump_event(e) for e in events],
        "action_items": [dump_action_item(a) for a in actions],
    }


# -------------------------------------------------------------------
# One-shot export
# -------------------------------------------------------------------


def export_store_query(
    store: BeaconStore,
    fmt: str = "json",
    output_path: str | Path | None = None,
    *,
    source_type: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 5000,
    title: str = "Beacon Store Export",
) -> Path:
    """Query the store and write an export file.

    Args:
        store: An initialised :class:`BeaconStore`.
        fmt: ``"json"``, ``"html"``, or ``"pdf"`` (HTML styled for print).
        output_path: Destination.  ``None`` picks an automatic path.
        source_type: Optional filter by source type.
        since: Optional lower-bound on ``occurred_at``.
        until: Optional upper-bound on ``occurred_at``.
        limit: Max rows to export.
        title: Document title for HTML output.

    Returns:
        The :class:`~pathlib.Path` of the written file.
    """
    from src.advanced.export import export_report

    payload = build_store_export_payload(
        store,
        source_type=source_type,
        since=since,
        until=until,
        limit=limit,
    )

    return export_report(payload, fmt=fmt, output_path=output_path, title=title)
