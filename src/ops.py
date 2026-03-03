"""Ops & observability helpers.

Phase 8 introduces light-weight tooling for understanding which backend is
currently active (store vs sync cache) and basic DB-level stats.

This module stays stdlib-only so it can be used by both the CLI and web API.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class StoreStats:
    total_events: int
    total_action_items: int
    completed_action_items: int
    pending_action_items: int
    events_by_source_type: dict[str, int]
    action_items_by_source_type: dict[str, int]


def compute_store_stats(store: Any) -> StoreStats:
    """Compute basic counts from a BeaconStore.

    The `store` parameter is intentionally typed as Any to avoid circular imports.
    It must provide `query_events(...)` and `query_action_items(...)`.
    """

    events = store.query_events(limit=1000000)
    actions = store.query_action_items(limit=1000000)

    events_by_st: dict[str, int] = {}
    for e in events:
        st_val = getattr(e, "source_type", "custom")
        st = st_val.value if hasattr(st_val, "value") else str(st_val)
        events_by_st[st] = events_by_st.get(st, 0) + 1

    actions_by_st: dict[str, int] = {}
    completed = 0
    pending = 0
    for a in actions:
        st_val = getattr(a, "source_type", "custom")
        st = st_val.value if hasattr(st_val, "value") else str(st_val)
        actions_by_st[st] = actions_by_st.get(st, 0) + 1
        if getattr(a, "completed", False):
            completed += 1
        else:
            pending += 1

    return StoreStats(
        total_events=len(events),
        total_action_items=len(actions),
        completed_action_items=completed,
        pending_action_items=pending,
        events_by_source_type=events_by_st,
        action_items_by_source_type=actions_by_st,
    )


def safe_path_str(p: Path | None) -> str | None:
    if p is None:
        return None
    try:
        return str(p)
    except Exception:
        return None
