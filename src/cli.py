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
    import importlib
    import json
    import uuid
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

    from src.connectors.base import ConnectorError, registry as connector_registry
    from src.models import Source, SourceType

    enabled = config.enabled_sources()
    if not enabled:
        print("No enabled sources configured.")
        return

    all_events: list[dict] = []
    all_action_items: list[dict] = []
    any_error = False

    for src_cfg in enabled:
        print(f"Syncing {src_cfg.name!r} ({src_cfg.type}) ...", end=" ", flush=True)
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
            print(f"SKIP -- config invalid for {connector_cls.__name__}")
            continue

        try:
            events, action_items = connector.sync()
            print(f"done ({len(events)} events, {len(action_items)} action items)")
            for ev in events:
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
            for ai in action_items:
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
        except ConnectorError as exc:
            print(f"ERROR -- {exc}")
            any_error = True

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

    if any_error:
        sys.exit(1)


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
    """Show a distraction-free view of today's top 3 priorities."""
    import json
    from pathlib import Path

    from src.intelligence.actions import ActionExtractor
    from src.intelligence.briefing import _action_from_dict, _event_from_dict, _load_sync_data
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

    pending = [a for a in all_actions if not a.completed]

    if not pending:
        print("Nothing to focus on. Your plate is clear.")
        return

    count = getattr(args, "count", 3) or 3
    scorer = PriorityScorer()
    top = scorer.top_n(pending, n=count)

    print(f"=== Focus Mode -- Top {len(top)} ===\n")
    for i, item in enumerate(top, 1):
        print(f"  {i}. {item.title}")
        if item.due_at:
            print(f"     Due: {item.due_at.strftime('%Y-%m-%d %H:%M')}")
        if item.url:
            print(f"     URL: {item.url}")
        print()


def _load_sync_cache() -> dict:
    """Load ~/.cache/beacon/last_sync.json or return empty cache."""
    import json
    from pathlib import Path

    cache_file = Path.home() / ".cache" / "beacon" / "last_sync.json"
    if not cache_file.exists():
        return {"events": [], "action_items": []}
    try:
        return json.loads(cache_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"events": [], "action_items": []}


def cmd_notify(args: argparse.Namespace) -> None:
    """Send a test notification via configured webhook or email."""
    config_path = find_config_file(getattr(args, "config", None))
    if config_path is None:
        print("No config file found. Run 'beacon init' first.")
        sys.exit(1)

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print(f"Error loading config: {exc}")
        sys.exit(1)

    raw = config.raw

    from src.notifications.digest import compile_digest
    from src.notifications.silence import load_silence_config
    from src.notifications.webhooks import WebhookError, load_webhook_config, send_webhook
    from src.notifications.email_digest import EmailError, load_email_config, send_email_digest

    silence_cfg = load_silence_config(raw)
    if silence_cfg.is_silenced():
        print("Notifications are currently silenced (focus/quiet hours).")
        if not getattr(args, "force", False):
            print("Use --force to send anyway.")
            sys.exit(0)

    cache = _load_sync_cache()
    events = cache.get("events", [])
    action_items = cache.get("action_items", [])
    digest = compile_digest(events, action_items, window="all", max_events=5, max_actions=5)

    title = "Beacon Test Notification"
    body = f"Events: {len(digest.events)}, Actions: {len(digest.action_items)}"
    items = digest.action_items[:5] + digest.events[:3]

    sent_any = False

    wh_cfg = load_webhook_config(raw)
    if wh_cfg:
        print(f"Sending test webhook to {wh_cfg.platform} ...", end=" ", flush=True)
        try:
            send_webhook(wh_cfg, title, body, items)
            print("OK")
            sent_any = True
        except WebhookError as exc:
            print(f"FAIL -- {exc}")

    email_cfg = load_email_config(raw)
    if email_cfg:
        print(f"Sending test email to {email_cfg.to_addr} ...", end=" ", flush=True)
        try:
            send_email_digest(digest, email_cfg)
            print("OK")
            sent_any = True
        except EmailError as exc:
            print(f"FAIL -- {exc}")

    if not sent_any:
        print("No notification channels configured.")
        print("  Add [notifications.webhook] or [notifications.email] to beacon.toml")


def cmd_digest(args: argparse.Namespace) -> None:
    """Compile and send a digest of current events and action items."""
    config_path = find_config_file(getattr(args, "config", None))
    if config_path is None:
        print("No config file found. Run 'beacon init' first.")
        sys.exit(1)

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print(f"Error loading config: {exc}")
        sys.exit(1)

    raw = config.raw

    from src.notifications.digest import compile_digest
    from src.notifications.silence import load_silence_config
    from src.notifications.webhooks import WebhookError, load_webhook_config, send_webhook
    from src.notifications.email_digest import EmailError, load_email_config, send_email_digest

    silence_cfg = load_silence_config(raw)
    if silence_cfg.is_silenced():
        print("Notifications are currently silenced (focus/quiet hours).")
        if not getattr(args, "force", False):
            print("Use --force to send anyway.")
            sys.exit(0)

    window = getattr(args, "window", "all") or "all"
    cache = _load_sync_cache()
    events = cache.get("events", [])
    action_items = cache.get("action_items", [])
    digest = compile_digest(events, action_items, window=window)

    output_fmt = getattr(args, "output", None)
    if output_fmt == "text":
        print(digest.as_text())
        return
    if output_fmt == "html":
        print(digest.as_html())
        return

    # Send via configured channels
    title = f"Beacon {window.title()} Digest"
    body = digest.as_text()[:500]
    items_combined = digest.action_items + digest.events

    sent_any = False

    wh_cfg = load_webhook_config(raw)
    if wh_cfg:
        print(f"Sending digest via {wh_cfg.platform} webhook ...", end=" ", flush=True)
        try:
            send_webhook(wh_cfg, title, body, items_combined)
            print("OK")
            sent_any = True
        except WebhookError as exc:
            print(f"FAIL -- {exc}")

    email_cfg = load_email_config(raw)
    if email_cfg:
        print(f"Sending digest email to {email_cfg.to_addr} ...", end=" ", flush=True)
        try:
            send_email_digest(digest, email_cfg)
            print("OK")
            sent_any = True
        except EmailError as exc:
            print(f"FAIL -- {exc}")

    if not sent_any:
        print("No notification channels configured — printing digest to stdout.")
        print()
        print(digest.as_text())


def cmd_query(args: argparse.Namespace) -> None:
    """Query events and action items from the local Beacon store."""
    import json

    from src.store import BeaconStore, dump_action_item, dump_event

    store = BeaconStore(getattr(args, "db", None))

    mode = getattr(args, "mode", "actions") or "actions"
    limit = int(getattr(args, "limit", 25) or 25)

    if mode == "events":
        since = getattr(args, "since", None)
        until = getattr(args, "until", None)
        src_type = getattr(args, "source_type", None)
        src_name = getattr(args, "source", None)
        from datetime import datetime

        events = store.query_events(
            source_type=src_type,
            source_name=src_name,
            since=datetime.fromisoformat(since) if since else None,
            until=datetime.fromisoformat(until) if until else None,
            limit=limit,
        )
        print(json.dumps([dump_event(e) for e in events], indent=2, sort_keys=True))
        return

    # actions
    src_type = getattr(args, "source_type", None)
    src_name = getattr(args, "source", None)
    priority = getattr(args, "priority", None)
    completed_flag = getattr(args, "completed", None)
    completed: bool | None
    if completed_flag is None:
        completed = None
    else:
        completed = bool(completed_flag)

    actions = store.query_action_items(
        source_type=src_type,
        source_name=src_name,
        priority=priority,
        completed=completed,
        limit=limit,
    )
    print(json.dumps([dump_action_item(a) for a in actions], indent=2, sort_keys=True))


def cmd_ingest(args: argparse.Namespace) -> None:
    """Ingest a sync cache JSON into the local Beacon store."""
    from pathlib import Path

    from src.ingest import ingest_sync_cache

    sync_file = getattr(args, "sync_file", None)
    if not sync_file:
        print("Error: --sync-file is required")
        sys.exit(1)

    db_path = getattr(args, "db", None)
    res = ingest_sync_cache(Path(sync_file), db_path=db_path)
    print(f"Ingested: {res.events_written} events written, {res.actions_written} action items written")


def cmd_dashboard(args: argparse.Namespace) -> None:
    """Start the Beacon web dashboard."""
    try:
        import uvicorn
    except ImportError:
        print("Error: uvicorn is not installed.")
        print("  Install web dependencies: pip install 'beacon[web]'")
        sys.exit(1)

    try:
        from src.web.server import create_app
    except ImportError as exc:
        print(f"Error loading web module: {exc}")
        sys.exit(1)

    host = getattr(args, "host", "127.0.0.1")
    port = getattr(args, "port", 8000)

    print(f"Beacon dashboard starting at http://{host}:{port}")
    print("Press Ctrl+C to stop.")

    app = create_app()
    uvicorn.run(app, host=host, port=port, log_level="warning")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="beacon",
        description="Your personal ops agent — unified briefings, action items, and smart notifications.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {VERSION}",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # status
    sub_status = subparsers.add_parser("status", help="Show connection status and pending items")
    sub_status.add_argument("--config", metavar="PATH", default=None, help="Path to beacon.toml")
    sub_status.set_defaults(func=cmd_status)

    # init
    sub_init = subparsers.add_parser("init", help="Create a default config file")
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
    sub_ingest = subparsers.add_parser("ingest", help="Import a sync cache into the local store")
    sub_ingest.add_argument("--sync-file", metavar="PATH", required=True, help="Path to sync cache JSON")
    sub_ingest.add_argument(
        "--db",
        metavar="PATH",
        default=None,
        help="Path to SQLite DB (default: ~/.cache/beacon/beacon.db)",
    )
    sub_ingest.set_defaults(func=cmd_ingest)

    # query
    sub_query = subparsers.add_parser("query", help="Query the local store")
    sub_query.add_argument(
        "mode",
        nargs="?",
        choices=["actions", "events"],
        default="actions",
        help="What to query (default: actions)",
    )
    sub_query.add_argument(
        "--db",
        metavar="PATH",
        default=None,
        help="Path to SQLite DB (default: ~/.cache/beacon/beacon.db)",
    )
    sub_query.add_argument("--limit", type=int, default=25, help="Max results (default: 25)")
    sub_query.add_argument("--source-type", dest="source_type", default=None, help="Filter by source type (e.g. github)")
    sub_query.add_argument("--source", default=None, help="Filter by source name/id")
    sub_query.add_argument("--priority", default=None, help="Filter action items by priority")
    sub_query.add_argument("--completed", action="store_true", help="Only completed action items")
    sub_query.add_argument("--since", default=None, help="Events since ISO datetime")
    sub_query.add_argument("--until", default=None, help="Events until ISO datetime")
    sub_query.set_defaults(func=cmd_query)

    # dashboard
    sub_dash = subparsers.add_parser("dashboard", help="Start the web dashboard")
    sub_dash.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    sub_dash.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    sub_dash.set_defaults(func=cmd_dashboard)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)
    args.func(args)


if __name__ == "__main__":
    main()
