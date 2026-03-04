"""Beacon CLI -- your personal ops agent from the terminal."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from src.config import ConfigError, find_config_file, load_config, write_default_config

VERSION = "0.1.0"


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def cmd_status(args: argparse.Namespace) -> None:
    """Show connected sources, last sync time, and pending action items."""
    print(f"Beacon v{VERSION}")
    print()

    config_path = find_config_file(getattr(args, "config", None))
    if config_path is None:
        print("Status: No configuration file found.")
        print()
        print("  Run 'beacon init' to create a default config at ~/.config/beacon/beacon.toml")
        print("  or create ./beacon.toml in your project directory.")
        return

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print(f"Error loading config: {exc}")
        sys.exit(1)

    print(f"Config:  {config_path}")
    print(f"User:    {config.user.name} <{config.user.email}>")
    print(f"Timezone:{config.user.timezone}")
    print()

    sources = config.sources
    if not sources:
        print("Sources: None configured")
        print()
        print("  Add a [[sources]] block to your beacon.toml to connect a source.")
        return

    enabled = config.enabled_sources()
    print(f"Sources: {len(sources)} configured, {len(enabled)} enabled")
    print()
    for src in sources:
        status_icon = "+" if src.enabled else "-"
        print(f"  [{status_icon}] {src.name!s:<20} type={src.type}")


def cmd_init(args: argparse.Namespace) -> None:
    """Create a default beacon.toml config file."""
    target = getattr(args, "path", None)
    try:
        path = write_default_config(target)
        print(f"Created config at: {path}")
        print("Edit it to add your sources and credentials.")
    except ConfigError as exc:
        print(f"Error: {exc}")
        sys.exit(1)


def _load_connector_registry() -> None:
    """Import all connector modules so they self-register via @registry.register."""
    import importlib

    _connector_modules = [
        "src.connectors.calendar_connector",
        "src.connectors.email_connector",
        "src.connectors.news",
        "src.connectors.github_connector",
        "src.connectors.weather",
        "src.connectors.hackernews",
    ]
    for mod in _connector_modules:
        try:
            importlib.import_module(mod)
        except ImportError:
            pass


def cmd_sources(args: argparse.Namespace) -> None:
    """List all configured sources with connector info and enabled/disabled status."""
    config_path = find_config_file(getattr(args, "config", None))
    if config_path is None:
        print("No config file found. Run 'beacon init' first.")
        sys.exit(1)

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print(f"Error loading config: {exc}")
        sys.exit(1)

    if not config.sources:
        print("No sources configured.")
        return

    _load_connector_registry()

    from src.connectors.base import registry as connector_registry
    from src.models import SourceType

    print(f"{'Name':<22} {'Type':<14} {'Status':<12} {'Connector'}")
    print("-" * 65)
    for src in config.sources:
        enabled_str = "enabled" if src.enabled else "disabled"
        try:
            st = SourceType(src.type)
            connector_cls = connector_registry.get(st)
            connector_str = connector_cls.__name__ if connector_cls else "(not registered)"
        except ValueError:
            connector_str = "(unknown type)"
        print(f"  {src.name!s:<20} {src.type!s:<14} {enabled_str:<12} {connector_str}")


def cmd_sources_test(args: argparse.Namespace) -> None:
    """Test connectivity for one or all configured sources."""
    config_path = find_config_file(getattr(args, "config", None))
    if config_path is None:
        print("No config file found. Run 'beacon init' first.")
        sys.exit(1)

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print(f"Error loading config: {exc}")
        sys.exit(1)

    _load_connector_registry()

    target_name: str | None = getattr(args, "name", None)
    sources_to_test = (
        [s for s in config.sources if s.name == target_name]
        if target_name
        else list(config.sources)
    )

    if target_name and not sources_to_test:
        print(f"Source {target_name!r} not found in config.")
        sys.exit(1)

    if not sources_to_test:
        print("No sources configured.")
        return

    from src.connectors.base import ConnectorError, registry as connector_registry
    from src.models import Source, SourceType

    any_failed = False
    for src_cfg in sources_to_test:
        print(f"Testing {src_cfg.name!r} ({src_cfg.type}) ...", end=" ", flush=True)
        try:
            src_type = SourceType(src_cfg.type)
        except ValueError:
            print(f"SKIP -- unknown type {src_cfg.type!r}")
            continue

        connector_cls = connector_registry.get(src_type)
        if connector_cls is None:
            print(f"SKIP -- no connector registered for {src_cfg.type!r}")
            continue

        source = Source(
            name=src_cfg.name,
            source_type=src_type,
            enabled=src_cfg.enabled,
            config=src_cfg.config,
        )
        connector = connector_cls(source)

        if not connector.validate_config():
            print(f"FAIL -- config invalid for {connector_cls.__name__}")
            any_failed = True
            continue

        try:
            ok = connector.test_connection()
        except ConnectorError as exc:
            print(f"FAIL -- {exc}")
            any_failed = True
            continue

        if ok:
            print(f"OK ({connector_cls.__name__})")
        else:
            print(f"FAIL -- {connector_cls.__name__} could not connect")
            any_failed = True

    if any_failed:
        sys.exit(1)


def cmd_sync(args: argparse.Namespace) -> None:
    """Sync all enabled sources and cache results to ~/.cache/beacon/last_sync.json."""
    import json
    from pathlib import Path

    config_path = find_config_file(getattr(args, "config", None))
    if config_path is None:
        print("No config file found. Run 'beacon init' first.")
        sys.exit(1)

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print(f"Error loading config: {exc}")
        sys.exit(1)

    _load_connector_registry()

    from src.sync import sync_enabled_sources
    from src.models import SourceType

    enabled = config.enabled_sources()
    if not enabled:
        print("No enabled sources configured.")
        return

    result = sync_enabled_sources(enabled)

    # Provide human-readable progress output (tests expect skip messages).
    # The structured logger emits skip reasons as log events; we also surface
    # a minimal summary on stdout for CLI ergonomics.
    for src_cfg in enabled:
        try:
            _ = SourceType(src_cfg.type)
        except ValueError:
            print(f"SKIP -- unknown type {src_cfg.type!r}")

    all_events: list[dict] = []
    all_action_items: list[dict] = []
    for ev in result.events:
        all_events.append(
            {
                "id": ev.id,
                "title": ev.title,
                "source_id": ev.source_id,
                "source_type": ev.source_type.value,
                "occurred_at": ev.occurred_at.isoformat() if ev.occurred_at else None,
                "summary": ev.summary,
                "url": ev.url,
                "metadata": ev.metadata,
            }
        )
    for ai in result.action_items:
        all_action_items.append(
            {
                "id": ai.id,
                "title": ai.title,
                "source_id": ai.source_id,
                "source_type": ai.source_type.value,
                "priority": ai.priority.value,
                "due_at": ai.due_at.isoformat() if ai.due_at else None,
                "url": ai.url,
                "completed": ai.completed,
                "notes": ai.notes,
                "metadata": ai.metadata,
            }
        )

    # Write cache
    cache_dir = Path.home() / ".cache" / "beacon"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / "last_sync.json"
    from datetime import datetime, timezone

    payload = {
        "synced_at": datetime.now(tz=timezone.utc).isoformat(),
        "events": all_events,
        "action_items": all_action_items,
    }
    cache_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print()
    print(f"Sync complete: {len(all_events)} events, {len(all_action_items)} action items")
    print(f"Cached to: {cache_file}")

    if result.any_error:
        sys.exit(1)


def cmd_sync_daemon(args: argparse.Namespace) -> None:
    """Run beacon sync repeatedly on an interval (cron-friendly daemon mode)."""
    from datetime import datetime, timezone
    from pathlib import Path
    import time

    interval = int(getattr(args, "interval", 300))
    if interval < 5:
        print("Error: --interval must be >= 5 seconds")
        sys.exit(2)

    max_runs_raw = getattr(args, "max_runs", None)
    max_runs = int(max_runs_raw) if max_runs_raw is not None else None
    if max_runs is not None and max_runs < 1:
        print("Error: --max-runs must be >= 1")
        sys.exit(2)

    once = bool(getattr(args, "once", False))
    show_times = bool(getattr(args, "show_times", False))

    config_path = find_config_file(getattr(args, "config", None))
    if config_path is None:
        print("No config file found. Run 'beacon init' first.")
        sys.exit(1)

    _load_connector_registry()

    from src.sync import sync_enabled_sources

    run = 0
    while True:
        run += 1
        started = datetime.now(tz=timezone.utc)
        if show_times:
            print(f"\n=== beacon sync --daemon run {run} @ {started.isoformat()} ===")

        try:
            config = load_config(config_path)
        except ConfigError as exc:
            print(f"Error loading config: {exc}")
            sys.exit(1)

        enabled = config.enabled_sources()
        if not enabled:
            print("No enabled sources configured.")
            return

        result = sync_enabled_sources(
            enabled,
            json_logs=bool(getattr(args, "json_logs", False)),
            log_level=str(getattr(args, "log_level", "INFO")),
        )

        all_events: list[dict] = []
        all_action_items: list[dict] = []
        for ev in result.events:
            all_events.append(
                {
                    "id": ev.id,
                    "title": ev.title,
                    "source_id": ev.source_id,
                    "source_type": ev.source_type.value,
                    "occurred_at": ev.occurred_at.isoformat() if ev.occurred_at else None,
                    "summary": ev.summary,
                    "url": ev.url,
                    "metadata": ev.metadata,
                }
            )
        for ai in result.action_items:
            all_action_items.append(
                {
                    "id": ai.id,
                    "title": ai.title,
                    "source_id": ai.source_id,
                    "source_type": ai.source_type.value,
                    "priority": ai.priority.value,
                    "due_at": ai.due_at.isoformat() if ai.due_at else None,
                    "url": ai.url,
                    "completed": ai.completed,
                    "notes": ai.notes,
                    "metadata": ai.metadata,
                }
            )

        cache_dir = Path.home() / ".cache" / "beacon"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / "last_sync.json"
        payload = {
            "synced_at": datetime.now(tz=timezone.utc).isoformat(),
            "events": all_events,
            "action_items": all_action_items,
            "request_id": result.request_id,
        }
        cache_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        print()
        print(f"Sync complete: {len(all_events)} events, {len(all_action_items)} action items")
        print(f"Cached to: {cache_file}")
        print(f"Request ID: {result.request_id}")

        if once:
            if result.any_error:
                sys.exit(1)
            return

        if max_runs is not None and run >= max_runs:
            if result.any_error:
                sys.exit(1)
            return

        if result.any_error and getattr(args, "stop_on_error", False):
            sys.exit(1)

        elapsed = (datetime.now(tz=timezone.utc) - started).total_seconds()
        sleep_for = max(0.0, float(interval) - elapsed)
        if show_times:
            print(f"Sleeping {sleep_for:.1f}s (interval={interval}s)")
        time.sleep(sleep_for)


def cmd_brief(args: argparse.Namespace) -> None:
    """Generate and display today's briefing."""
    from pathlib import Path

    from src.intelligence.briefing import BriefingGenerator

    sync_path = getattr(args, "sync_file", None)
    if sync_path:
        sync_path = Path(sync_path)

    gen = BriefingGenerator(sync_path=sync_path)
    briefing = gen.generate()

    if not briefing.events and not briefing.action_items:
        print("No data available. Run 'beacon sync' first.")
        return

    print(gen.format_text(briefing))


def cmd_actions(args: argparse.Namespace) -> None:
    """List prioritized action items across all sources."""
    import json
    from pathlib import Path

    from src.intelligence.actions import ActionExtractor
    from src.intelligence.briefing import (
        BriefingGenerator,
        _action_from_dict,
        _event_from_dict,
        _load_sync_data,
    )
    from src.intelligence.priority import PriorityScorer

    sync_path = getattr(args, "sync_file", None)
    if sync_path:
        sync_path = Path(sync_path)

    data = _load_sync_data(sync_path)
    events = [_event_from_dict(e) for e in data.get("events", [])]
    existing_actions = [_action_from_dict(a) for a in data.get("action_items", [])]

    extractor = ActionExtractor()
    extracted = extractor.extract(events, existing_actions=existing_actions)
    all_actions = existing_actions + extracted

    if not all_actions:
        print("No action items found. Run 'beacon sync' first.")
        return

    scorer = PriorityScorer()
    ranked = scorer.rank([a for a in all_actions if not a.completed])

    print(f"=== Action Items ({len(ranked)} pending) ===")
    print()
    from src.models import Priority

    for item, score in ranked:
        marker = "!" if item.priority in (Priority.HIGH, Priority.URGENT) else " "
        print(f"  [{marker}] [{item.priority.value:<6}] (score: {score:>6.1f})  {item.title}")


def cmd_focus(args: argparse.Namespace) -> None:
    """Distraction-free view of today's top priorities."""
    from pathlib import Path

    from src.intelligence.actions import ActionExtractor
    from src.intelligence.briefing import (
        BriefingGenerator,
        _action_from_dict,
        _event_from_dict,
        _load_sync_data,
    )
    from src.intelligence.priority import PriorityScorer

    count = int(getattr(args, "count", 3))
    if count < 1:
        print("Error: --count must be >= 1")
        sys.exit(2)

    sync_path = getattr(args, "sync_file", None)
    if sync_path:
        sync_path = Path(sync_path)

    data = _load_sync_data(sync_path)
    events = [_event_from_dict(e) for e in data.get("events", [])]
    existing_actions = [_action_from_dict(a) for a in data.get("action_items", [])]

    extractor = ActionExtractor()
    extracted = extractor.extract(events, existing_actions=existing_actions)
    all_actions = existing_actions + extracted

    if not all_actions:
        print("No action items found. Run 'beacon sync' first.")
        return

    scorer = PriorityScorer()
    ranked = scorer.rank([a for a in all_actions if not a.completed])
    top = ranked[:count]

    print(f"=== Focus ({len(top)} items) ===")
    print()
    from src.models import Priority

    for item, score in top:
        marker = "!" if item.priority in (Priority.HIGH, Priority.URGENT) else " "
        print(f"  [{marker}] [{item.priority.value:<6}] (score: {score:>6.1f})  {item.title}")


def cmd_digest(args: argparse.Namespace) -> None:
    """Compile and send a digest."""
    from datetime import datetime, timezone
    from pathlib import Path

    from src.notifications import DigestWindow, NotificationError, Notifications

    config_path = find_config_file(getattr(args, "config", None))
    if config_path is None:
        print("No config file found. Run 'beacon init' first.")
        sys.exit(1)

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print(f"Error loading config: {exc}")
        sys.exit(1)

    sync_path = Path.home() / ".cache" / "beacon" / "last_sync.json"
    if not sync_path.exists():
        print("No sync cache found. Run 'beacon sync' first.")
        sys.exit(1)

    window = DigestWindow(getattr(args, "window", "all"))
    output = getattr(args, "output", None)

    if output:
        # Just print digest to stdout
        from src.intelligence.briefing import BriefingGenerator

        gen = BriefingGenerator(sync_path=sync_path)
        briefing = gen.generate()
        print(gen.format_text(briefing))
        return

    # Send digest
    try:
        notifier = Notifications.from_config(config)
    except NotificationError as exc:
        print(f"Notification config error: {exc}")
        sys.exit(1)

    # Respect silence hours unless forced
    if notifier.is_silenced() and not getattr(args, "force", False):
        print("Notifications are currently silenced by smart silence rules.")
        print("Use --force to send anyway.")
        return

    try:
        notifier.send_digest(window=window)
        print(f"Digest sent ({window.value}).")
    except NotificationError as exc:
        print(f"Error sending digest: {exc}")
        sys.exit(1)


def cmd_notify(args: argparse.Namespace) -> None:
    """Send a test notification."""
    from src.notifications import NotificationError, Notifications

    config_path = find_config_file(getattr(args, "config", None))
    if config_path is None:
        print("No config file found. Run 'beacon init' first.")
        sys.exit(1)

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print(f"Error loading config: {exc}")
        sys.exit(1)

    try:
        notifier = Notifications.from_config(config)
    except NotificationError as exc:
        print(f"Notification config error: {exc}")
        sys.exit(1)

    # Respect silence hours unless forced
    if notifier.is_silenced() and not getattr(args, "force", False):
        print("Notifications are currently silenced by smart silence rules.")
        print("Use --force to send anyway.")
        return

    try:
        notifier.send_test()
        print("Test notification sent.")
    except NotificationError as exc:
        print(f"Error sending notification: {exc}")
        sys.exit(1)


def cmd_health(args: argparse.Namespace) -> None:
    """Run health diagnostics."""
    from src.health import HealthReport

    config_path = find_config_file(getattr(args, "config", None))
    if config_path is None:
        print("No config file found. Run 'beacon init' first.")
        sys.exit(1)

    report = HealthReport(config_path=config_path)
    print(report.format_text())

    if report.has_errors:
        sys.exit(1)


def cmd_export(args: argparse.Namespace) -> None:
    """Export store data to JSON/HTML/PDF."""
    from src.export import export_store

    config_path = find_config_file(getattr(args, "config", None))
    if config_path is None:
        print("No config file found. Run 'beacon init' first.")
        sys.exit(1)

    out_format = getattr(args, "format", None)
    if out_format is None:
        out_format = "json"

    try:
        export_store(config_path=config_path, fmt=str(out_format), output_path=getattr(args, "output", None))
    except Exception as exc:  # noqa: BLE001
        print(f"Export failed: {exc}")
        sys.exit(1)


def cmd_db(args: argparse.Namespace) -> None:
    """Print db_path + counts for events/action_items."""
    from src.db_cli import db_status

    config_path = find_config_file(getattr(args, "config", None))
    if config_path is None:
        print("No config file found. Run 'beacon init' first.")
        sys.exit(1)

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print(f"Error loading config: {exc}")
        sys.exit(1)

    db_path = getattr(config, "db_path", None)
    if not db_path:
        print("No db_path configured in beacon.toml.")
        sys.exit(1)

    print(db_status(db_path))


def cmd_ingest(args: argparse.Namespace) -> None:
    """Ingest last_sync.json into the local store."""
    from pathlib import Path

    from src.ingest import ingest_sync_cache

    db_path = getattr(args, "db_path", None)
    if not db_path:
        print("Error: --db-path is required")
        sys.exit(2)

    sync_path = getattr(args, "sync_file", None)
    if sync_path:
        sync_path = Path(sync_path)

    try:
        counts = ingest_sync_cache(db_path=db_path, sync_path=sync_path)
    except Exception as exc:  # noqa: BLE001
        print(f"Ingest failed: {exc}")
        sys.exit(1)

    print(
        f"Ingest complete: {counts['events_inserted']} events inserted, "
        f"{counts['action_items_inserted']} action items inserted"
    )


def cmd_query(args: argparse.Namespace) -> None:
    """Query events/action items from the local store."""
    from datetime import datetime

    from src.store.query import query_store

    db_path = getattr(args, "db_path", None)
    if not db_path:
        print("Error: --db-path is required")
        sys.exit(2)

    start = getattr(args, "start", None)
    end = getattr(args, "end", None)
    source_type = getattr(args, "source_type", None)

    def _parse_dt(val: str | None) -> datetime | None:
        if not val:
            return None
        return datetime.fromisoformat(val)

    try:
        results = query_store(
            db_path=db_path,
            kind=str(getattr(args, "kind", "events")),
            start=_parse_dt(start),
            end=_parse_dt(end),
            source_type=str(source_type) if source_type else None,
            limit=int(getattr(args, "limit", 50)),
            offset=int(getattr(args, "offset", 0)),
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Query failed: {exc}")
        sys.exit(1)

    for row in results:
        print(row)


def cmd_web(args: argparse.Namespace) -> None:
    """Run the web dashboard server."""
    import uvicorn

    from src.web.app import create_app

    host = getattr(args, "host", "127.0.0.1")
    port = int(getattr(args, "port", 8000))
    app = create_app()
    uvicorn.run(app, host=host, port=port, log_level="warning")


def cmd_check(args: argparse.Namespace) -> None:
    """Lint beacon.toml for common errors and print actionable warnings."""
    from pathlib import Path

    from src.config_lint import lint_config

    config_path = find_config_file(getattr(args, "config", None))
    if config_path is None:
        print("No config file found. Run 'beacon init' first.")
        sys.exit(1)

    raw = Path(config_path).read_text(encoding="utf-8")
    warnings = lint_config(raw)
    if not warnings:
        print("OK -- no issues found")
        return

    for w in warnings:
        print(f"WARN: {w}")
    sys.exit(1)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the beacon CLI."""
    argv = argv if argv is not None else sys.argv[1:]

    parser = argparse.ArgumentParser(prog="beacon", description="Beacon -- your personal ops agent")
    subparsers = parser.add_subparsers(dest="cmd")

    # status
    sub_status = subparsers.add_parser("status", help="Show status")
    sub_status.add_argument("--config", metavar="PATH", default=None, help="Path to beacon.toml")
    sub_status.set_defaults(func=cmd_status)

    # init
    sub_init = subparsers.add_parser("init", help="Create default config")
    sub_init.add_argument(
        "--path",
        metavar="PATH",
        default=None,
        help="Where to write the config (default: ~/.config/beacon/beacon.toml)",
    )
    sub_init.set_defaults(func=cmd_init)

    # sources
    sub_sources = subparsers.add_parser("sources", help="List configured sources")
    sub_sources.add_argument("--config", metavar="PATH", default=None, help="Path to beacon.toml")
    sub_sources.set_defaults(func=cmd_sources)

    sources_sub = sub_sources.add_subparsers(dest="sources_action")
    # sources test [name]
    sub_src_test = sources_sub.add_parser("test", help="Test connectivity for a source")
    sub_src_test.add_argument(
        "name",
        nargs="?",
        default=None,
        help="Name of the source to test (omit to test all sources)",
    )
    sub_src_test.add_argument("--config", metavar="PATH", default=None, help="Path to beacon.toml")
    sub_src_test.set_defaults(func=cmd_sources_test)

    # sync
    sub_sync = subparsers.add_parser("sync", help="Sync all enabled sources")
    sub_sync.add_argument("--config", metavar="PATH", default=None, help="Path to beacon.toml")
    sub_sync.add_argument(
        "--daemon",
        action="store_true",
        help="Run sync repeatedly on an interval (use with --interval)",
    )
    sub_sync.add_argument(
        "--interval",
        type=int,
        default=300,
        help="Interval between sync runs in seconds when --daemon is set (default: 300)",
    )
    sub_sync.add_argument(
        "--max-runs",
        type=int,
        default=None,
        help="Stop after N runs in --daemon mode (default: run forever)",
    )
    sub_sync.add_argument(
        "--once",
        action="store_true",
        help="Run exactly one sync then exit (useful with --daemon for uniform logs)",
    )
    sub_sync.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Exit immediately if any connector errors during a daemon run",
    )
    sub_sync.add_argument(
        "--show-times",
        action="store_true",
        help="Print timestamps and sleep durations in daemon mode",
    )
    sub_sync.add_argument(
        "--json-logs",
        action="store_true",
        help="Output structured JSON logs during sync runs (daemon mode only)",
    )
    sub_sync.add_argument(
        "--log-level",
        default="INFO",
        help="Log level for JSON logs (DEBUG/INFO/WARNING/ERROR). Default: INFO",
    )
    sub_sync.set_defaults(func=cmd_sync)

    # brief
    sub_brief = subparsers.add_parser("brief", help="Generate and display today's briefing")
    sub_brief.add_argument("--sync-file", metavar="PATH", default=None, help="Path to sync cache JSON")
    sub_brief.set_defaults(func=cmd_brief)

    # actions
    sub_actions = subparsers.add_parser("actions", help="List prioritized action items")
    sub_actions.add_argument("--sync-file", metavar="PATH", default=None, help="Path to sync cache JSON")
    sub_actions.set_defaults(func=cmd_actions)

    # focus
    sub_focus = subparsers.add_parser("focus", help="Distraction-free view of top priorities")
    sub_focus.add_argument("-n", "--count", type=int, default=3, help="Number of items to show (default: 3)")
    sub_focus.add_argument("--sync-file", metavar="PATH", default=None, help="Path to sync cache JSON")
    sub_focus.set_defaults(func=cmd_focus)

    # notify
    sub_notify = subparsers.add_parser("notify", help="Send a test notification")
    sub_notify.add_argument("--config", metavar="PATH", default=None, help="Path to beacon.toml")
    sub_notify.add_argument("--force", action="store_true", help="Send even during silence hours")
    sub_notify.set_defaults(func=cmd_notify)

    # digest
    sub_digest = subparsers.add_parser("digest", help="Compile and send a digest")
    sub_digest.add_argument("--config", metavar="PATH", default=None, help="Path to beacon.toml")
    sub_digest.add_argument(
        "--window",
        choices=["morning", "evening", "all"],
        default="all",
        help="Time window for events (default: all)",
    )
    sub_digest.add_argument(
        "--output",
        choices=["text", "html"],
        default=None,
        help="Print digest to stdout instead of sending (text or html)",
    )
    sub_digest.add_argument("--force", action="store_true", help="Send even during silence hours")
    sub_digest.set_defaults(func=cmd_digest)

    # ingest
    sub_ingest = subparsers.add_parser("ingest", help="Ingest last sync cache into local store")
    sub_ingest.add_argument("--db-path", metavar="PATH", required=True, help="Path to SQLite db")
    sub_ingest.add_argument("--sync-file", metavar="PATH", default=None, help="Path to sync cache JSON")
    sub_ingest.set_defaults(func=cmd_ingest)

    # query
    sub_query = subparsers.add_parser("query", help="Query events/action items from local store")
    sub_query.add_argument("--db-path", metavar="PATH", required=True, help="Path to SQLite db")
    sub_query.add_argument(
        "--kind",
        choices=["events", "action_items"],
        default="events",
        help="What to query (events or action_items)",
    )
    sub_query.add_argument("--start", metavar="ISO", default=None, help="Start datetime (ISO format)")
    sub_query.add_argument("--end", metavar="ISO", default=None, help="End datetime (ISO format)")
    sub_query.add_argument("--source-type", metavar="TYPE", default=None, help="Filter by source type")
    sub_query.add_argument("--limit", type=int, default=50, help="Limit results (default: 50)")
    sub_query.add_argument("--offset", type=int, default=0, help="Offset results (default: 0)")
    sub_query.set_defaults(func=cmd_query)

    # web
    sub_web = subparsers.add_parser("web", help="Run the web dashboard")
    sub_web.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    sub_web.add_argument("--port", type=int, default=8000, help="Port to bind (default: 8000)")
    sub_web.set_defaults(func=cmd_web)

    # health
    sub_health = subparsers.add_parser("health", help="Run health diagnostics")
    sub_health.add_argument("--config", metavar="PATH", default=None, help="Path to beacon.toml")
    sub_health.set_defaults(func=cmd_health)

    # export
    sub_export = subparsers.add_parser("export", help="Export store data")
    sub_export.add_argument("--config", metavar="PATH", default=None, help="Path to beacon.toml")
    sub_export.add_argument(
        "--format",
        choices=["json", "html", "pdf"],
        default="json",
        help="Export format (default: json)",
    )
    sub_export.add_argument("--output", metavar="PATH", default=None, help="Output path")
    sub_export.set_defaults(func=cmd_export)

    # db
    sub_db = subparsers.add_parser("db", help="Show db status")
    sub_db.add_argument("--config", metavar="PATH", default=None, help="Path to beacon.toml")
    sub_db.set_defaults(func=cmd_db)

    # check
    sub_check = subparsers.add_parser("check", help="Lint beacon.toml")
    sub_check.add_argument("--config", metavar="PATH", default=None, help="Path to beacon.toml")
    sub_check.set_defaults(func=cmd_check)

    args = parser.parse_args(argv)

    # If sync --daemon, dispatch to daemon handler.
    if getattr(args, "cmd", None) == "sync" and getattr(args, "daemon", False):
        cmd_sync_daemon(args)
        return 0

    if not hasattr(args, "func"):
        parser.print_help()
        return 0

    try:
        args.func(args)
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
