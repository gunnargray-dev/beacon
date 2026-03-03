from __future__ import annotations

from pathlib import Path

from src.ops import compute_store_stats
from src.store import BeaconStore


def cmd_db(db_path: str | None) -> int:
    """Entry point for `beacon db`.

    Returns process exit code.
    """

    store = BeaconStore(db_path)
    exists = store.db_path.exists()

    print(f"DB path: {store.db_path}")
    print(f"DB exists: {exists}")

    if not exists:
        return 1

    stats = compute_store_stats(store)

    print()
    print("Events:")
    print(f"  total: {stats.total_events}")
    for st, count in sorted(stats.events_by_source_type.items()):
        print(f"  {st}: {count}")

    print()
    print("Action items:")
    print(f"  total: {stats.total_action_items}")
    print(f"  pending: {stats.pending_action_items}")
    print(f"  completed: {stats.completed_action_items}")
    for st, count in sorted(stats.action_items_by_source_type.items()):
        print(f"  {st}: {count}")

    return 0
