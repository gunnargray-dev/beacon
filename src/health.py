"""Health diagnostics for Beacon.

Provides a single ``run_health_check`` function that inspects the local
environment and returns a structured report covering:

* Configuration file status
* SQLite store status (exists, row counts)
* Sync cache status (exists, age, event/action counts)
* Connector summary (enabled/disabled counts)

This module is stdlib-only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class HealthReport:
    """Structured output of ``run_health_check``."""

    config_found: bool = False
    config_path: str | None = None
    config_error: str | None = None

    store_exists: bool = False
    store_path: str | None = None
    store_event_count: int = 0
    store_action_count: int = 0

    cache_exists: bool = False
    cache_path: str | None = None
    cache_synced_at: str | None = None
    cache_event_count: int = 0
    cache_action_count: int = 0

    sources_total: int = 0
    sources_enabled: int = 0

    checks: list[dict[str, str]] = field(default_factory=list)

    def add_check(self, name: str, status: str, detail: str = "") -> None:
        self.checks.append({"name": name, "status": status, "detail": detail})

    @property
    def ok(self) -> bool:
        return all(c["status"] == "ok" for c in self.checks)

    def as_text(self) -> str:
        lines: list[str] = []
        lines.append("=== Beacon Health Check ===")
        lines.append("")
        for c in self.checks:
            icon = "+" if c["status"] == "ok" else ("!" if c["status"] == "warn" else "x")
            detail = f"  {c['detail']}" if c["detail"] else ""
            lines.append(f"  [{icon}] {c['name']}{detail}")
        lines.append("")
        overall = "HEALTHY" if self.ok else "ISSUES DETECTED"
        lines.append(f"Overall: {overall}")
        return "\n".join(lines)


def run_health_check(
    config_path: str | Path | None = None,
    db_path: str | Path | None = None,
) -> HealthReport:
    """Run health diagnostics and return a :class:`HealthReport`.

    This function does *not* require any optional dependencies.
    """
    report = HealthReport()

    # ----- Config -----
    try:
        from src.config import ConfigError, find_config_file, load_config

        found = find_config_file(config_path)
        if found:
            report.config_found = True
            report.config_path = str(found)
            try:
                cfg = load_config(found)
                report.sources_total = len(cfg.sources)
                report.sources_enabled = len(cfg.enabled_sources())
                report.add_check("config", "ok", str(found))
            except ConfigError as exc:
                report.config_error = str(exc)
                report.add_check("config", "fail", f"parse error: {exc}")
        else:
            report.add_check("config", "warn", "no config file found")
    except Exception as exc:
        report.add_check("config", "fail", str(exc))

    # ----- Store -----
    try:
        from src.store import BeaconStore

        store = BeaconStore(db_path)
        report.store_path = str(store.db_path)

        if store.db_path.exists():
            report.store_exists = True
            events = store.query_events(limit=1)
            actions = store.query_action_items(limit=1)
            # Get actual counts via a lightweight SQL query
            with store.connect() as conn:
                row = conn.execute("SELECT COUNT(*) FROM events").fetchone()
                report.store_event_count = row[0] if row else 0
                row = conn.execute("SELECT COUNT(*) FROM action_items").fetchone()
                report.store_action_count = row[0] if row else 0
            report.add_check(
                "store",
                "ok",
                f"{report.store_event_count} events, {report.store_action_count} actions",
            )
        else:
            report.add_check("store", "warn", f"DB not found at {store.db_path}")
    except Exception as exc:
        report.add_check("store", "fail", str(exc))

    # ----- Sync cache -----
    cache_file = Path.home() / ".cache" / "beacon" / "last_sync.json"
    report.cache_path = str(cache_file)
    try:
        if cache_file.exists():
            report.cache_exists = True
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            report.cache_synced_at = data.get("synced_at")
            report.cache_event_count = len(data.get("events", []))
            report.cache_action_count = len(data.get("action_items", []))
            report.add_check(
                "sync_cache",
                "ok",
                f"synced {report.cache_synced_at or 'unknown'} "
                f"({report.cache_event_count} events, {report.cache_action_count} actions)",
            )
        else:
            report.add_check("sync_cache", "warn", "no sync cache found (run 'beacon sync')")
    except Exception as exc:
        report.add_check("sync_cache", "fail", str(exc))

    # ----- Sources -----
    if report.config_found:
        if report.sources_enabled == 0:
            report.add_check("sources", "warn", "no sources enabled")
        else:
            report.add_check(
                "sources",
                "ok",
                f"{report.sources_enabled}/{report.sources_total} enabled",
            )
    else:
        report.add_check("sources", "warn", "no config to check")

    return report
