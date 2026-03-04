import sqlite3

import pytest

from src.migrations import Migration, apply_migrations, get_user_version


def test_get_user_version_defaults_to_zero(tmp_path):
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    try:
        assert get_user_version(conn) == 0
    finally:
        conn.close()


def test_apply_migrations_applies_in_order_and_sets_user_version(tmp_path):
    db = tmp_path / "t.db"

    def v1(conn: sqlite3.Connection) -> None:
        conn.execute("CREATE TABLE t1 (id INTEGER PRIMARY KEY)")

    def v2(conn: sqlite3.Connection) -> None:
        conn.execute("ALTER TABLE t1 ADD COLUMN name TEXT")

    conn = sqlite3.connect(db)
    try:
        applied = apply_migrations(
            conn,
            [
                Migration(version=2, name="v2", apply=v2),
                Migration(version=1, name="v1", apply=v1),
            ],
        )
        assert applied == 2
        assert get_user_version(conn) == 2

        # Idempotent: re-run should do nothing.
        applied2 = apply_migrations(
            conn,
            [
                Migration(version=1, name="v1", apply=v1),
                Migration(version=2, name="v2", apply=v2),
            ],
        )
        assert applied2 == 0
        assert get_user_version(conn) == 2

        # Schema updated.
        cols = [r[1] for r in conn.execute("PRAGMA table_info(t1)").fetchall()]
        assert cols == ["id", "name"]
    finally:
        conn.close()


def test_apply_migrations_rejects_duplicate_versions(tmp_path):
    db = tmp_path / "t.db"

    def v1(conn: sqlite3.Connection) -> None:
        conn.execute("CREATE TABLE t1 (id INTEGER PRIMARY KEY)")

    conn = sqlite3.connect(db)
    try:
        with pytest.raises(ValueError):
            apply_migrations(
                conn,
                [
                    Migration(version=1, name="v1a", apply=v1),
                    Migration(version=1, name="v1b", apply=v1),
                ],
            )
    finally:
        conn.close()
