"""Interactive REPL for ad-hoc Beacon store queries.

This is intentionally stdlib-only.

The shell is a lightweight convenience layer over :class:`src.store.BeaconStore`.
It is designed for quick exploration, not as a full scripting environment.
"""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from src.store import BeaconStore, dump_action_item, dump_event


class ShellError(Exception):
    pass


@dataclass(frozen=True)
class ShellResult:
    """A structured response from a shell command."""

    rows: list[dict]
    next_cursor: str | None = None

    def as_json(self) -> str:
        return json.dumps(
            {"rows": self.rows, "next_cursor": self.next_cursor},
            indent=2,
            sort_keys=True,
        )


def _parse_iso_dt(val: str | None) -> datetime | None:
    if not val:
        return None
    try:
        return datetime.fromisoformat(val)
    except ValueError as exc:
        raise ShellError(f"Invalid datetime: {val!r} (expected ISO format)") from exc


def _parse_bool(val: str | None) -> bool | None:
    if val is None:
        return None
    v = val.strip().lower()
    if v in {"true", "1", "yes", "y"}:
        return True
    if v in {"false", "0", "no", "n"}:
        return False
    raise ShellError(f"Invalid boolean: {val!r} (expected true/false)")


def _parse_kv_args(tokens: Iterable[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for t in tokens:
        if "=" not in t:
            raise ShellError(f"Invalid arg: {t!r} (expected key=value)")
        k, v = t.split("=", 1)
        k = k.strip()
        if not k:
            raise ShellError(f"Invalid arg: {t!r} (empty key)")
        out[k] = v
    return out


def execute_shell_command(cmd: str, *, store: BeaconStore) -> ShellResult:
    """Execute a single shell command and return structured results.

    Supported commands:
      - help
      - exit / quit
      - events [key=value...]
      - actions [key=value...]

    Common args (both events/actions):
      - limit=50
      - cursor=<opaque>
      - source_type=<type>
      - source_name=<name>

    Events args:
      - since=<ISO datetime>
      - until=<ISO datetime>
      - sort=occurred_at_desc|occurred_at_asc

    Actions args:
      - completed=true|false
      - priority=low|medium|high|urgent
      - due_before=<ISO datetime>
      - sort=default|created_at_desc
    """

    raw = cmd.strip()
    if not raw:
        return ShellResult(rows=[])

    parts = shlex.split(raw)
    if not parts:
        return ShellResult(rows=[])

    name = parts[0].lower()
    args = _parse_kv_args(parts[1:])

    if name in {"help", "?"}:
        return ShellResult(
            rows=[
                {
                    "help": (
                        "Commands: events, actions, help, exit\n"
                        "Examples:\n"
                        "  events limit=5\n"
                        "  events source_type=github since=2026-01-01T00:00:00+00:00 limit=10\n"
                        "  actions completed=false limit=10\n"
                        "  actions priority=urgent due_before=2026-03-01T00:00:00+00:00\n"
                    )
                }
            ]
        )

    if name in {"exit", "quit"}:
        return ShellResult(rows=[{"exit": True}])

    limit = int(args.get("limit", "50"))
    if limit < 1 or limit > 500:
        raise ShellError("limit must be between 1 and 500")

    cursor = args.get("cursor")
    source_type = args.get("source_type")
    source_name = args.get("source_name")

    if name == "events":
        since = _parse_iso_dt(args.get("since"))
        until = _parse_iso_dt(args.get("until"))
        sort = args.get("sort", "occurred_at_desc")
        events = store.query_events(
            source_type=source_type,
            source_name=source_name,
            since=since,
            until=until,
            limit=limit,
            cursor=cursor,
            sort=sort,
        )
        rows = [dump_event(e) for e in events]
        next_cursor = store.encode_event_cursor(events[-1], sort=sort) if events else None
        return ShellResult(rows=rows, next_cursor=next_cursor)

    if name in {"actions", "action_items"}:
        completed = _parse_bool(args.get("completed"))
        due_before = _parse_iso_dt(args.get("due_before"))
        priority = args.get("priority")
        sort = args.get("sort", "default")
        items = store.query_action_items(
            source_type=source_type,
            source_name=source_name,
            priority=priority,
            completed=completed,
            due_before=due_before,
            limit=limit,
            cursor=cursor,
            sort=sort,
        )
        rows = [dump_action_item(a) for a in items]
        next_cursor = store.encode_action_item_cursor(items[-1], sort=sort) if items else None
        return ShellResult(rows=rows, next_cursor=next_cursor)

    raise ShellError(f"Unknown command: {name!r} (try 'help')")


def run_shell(*, db_path: str | Path) -> int:
    """Run the interactive shell. Returns a process exit code."""

    store = BeaconStore(Path(db_path))
    store.init_db()

    print("Beacon shell. Type 'help' for commands. Type 'exit' to quit.")
    while True:
        try:
            line = input("beacon> ")
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print()
            return 130

        try:
            result = execute_shell_command(line, store=store)
        except ShellError as exc:
            print(f"Error: {exc}")
            continue

        if result.rows and result.rows[0].get("exit") is True:
            return 0

        # Pretty-print results as JSON to make copy/paste easy.
        print(result.as_json())
