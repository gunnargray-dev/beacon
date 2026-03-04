"""SQLite schema migrations for Beacon store.

This is intentionally stdlib-only.

Design goals:
- Keep migrations simple and explicit.
- Support auto-upgrade on startup.
- Be safe when running concurrently (best-effort with BEGIN IMMEDIATE).

We store schema version in PRAGMA user_version.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Callable, Iterable


MigrationFn = Callable[[sqlite3.Connection], None]


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    apply: MigrationFn


def _set_user_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(f"PRAGMA user_version = {int(version)}")


def get_user_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version").fetchone()
    if row is None:
        return 0
    return int(row[0])


def apply_migrations(conn: sqlite3.Connection, migrations: Iterable[Migration]) -> int:
    """Apply any pending migrations in ascending version order.

    Returns the number of migrations applied.
    """
    # Ensure stable ordering.
    migs = sorted(migrations, key=lambda m: m.version)

    current = get_user_version(conn)

    # Validate monotonic versions.
    seen: set[int] = set()
    for m in migs:
        if m.version <= 0:
            raise ValueError(f"Invalid migration version: {m.version}")
        if m.version in seen:
            raise ValueError(f"Duplicate migration version: {m.version}")
        seen.add(m.version)

    applied = 0

    # Wrap all migrations in a single transaction.
    # BEGIN IMMEDIATE takes a write lock early, reducing likelihood of races.
    conn.execute("BEGIN IMMEDIATE")
    try:
        for m in migs:
            if m.version <= current:
                continue
            m.apply(conn)
            _set_user_version(conn, m.version)
            current = m.version
            applied += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return applied
