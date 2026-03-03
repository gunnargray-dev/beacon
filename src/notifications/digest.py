"""Digest compiler for Beacon notifications.

Compiles Events and ActionItems into a structured digest with plain-text
and HTML renderings.

Config in beacon.toml:

    [notifications.digest]
    window = "morning"   # "morning" | "evening" | "all"
    max_events = 20
    max_actions = 10
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Digest:
    """A compiled digest of events and action items."""

    generated_at: datetime
    window: str  # "morning" | "evening" | "all"
    events: list[dict[str, Any]] = field(default_factory=list)
    action_items: list[dict[str, Any]] = field(default_factory=list)

    def as_text(self) -> str:
        """Render as plain text."""
        lines: list[str] = []
        ts = self.generated_at.strftime("%Y-%m-%d %H:%M")
        lines.append(f"=== Beacon Digest ({self.window}) — {ts} ===")
        lines.append("")

        if self.events:
            lines.append(f"EVENTS ({len(self.events)})")
            lines.append("-" * 40)
            for ev in self.events:
                title = ev.get("title", "(no title)")
                src = ev.get("source_type", "")
                occurred = ev.get("occurred_at", "")
                if occurred:
                    try:
                        dt = datetime.fromisoformat(occurred)
                        occurred = dt.strftime("%Y-%m-%d %H:%M")
                    except ValueError:
                        pass
                lines.append(f"  [{src}] {title}")
                if occurred:
                    lines.append(f"        {occurred}")
                summary = ev.get("summary", "")
                if summary:
                    lines.append(f"        {summary[:120]}")
                url = ev.get("url", "")
                if url:
                    lines.append(f"        {url}")
            lines.append("")

        if self.action_items:
            lines.append(f"ACTION ITEMS ({len(self.action_items)})")
            lines.append("-" * 40)
            for ai in self.action_items:
                title = ai.get("title", "(no title)")
                priority = ai.get("priority", "medium").upper()
                src = ai.get("source_type", "")
                completed = ai.get("completed", False)
                status = "[x]" if completed else "[ ]"
                lines.append(f"  {status} [{priority}] {title} ({src})")
                due = ai.get("due_at", "")
                if due:
                    try:
                        dt = datetime.fromisoformat(due)
                        due = dt.strftime("%Y-%m-%d %H:%M")
                    except ValueError:
                        pass
                    lines.append(f"        Due: {due}")
                url = ai.get("url", "")
                if url:
                    lines.append(f"        {url}")
            lines.append("")

        if not self.events and not self.action_items:
            lines.append("  Nothing to report.")
            lines.append("")

        return "\n".join(lines)

    def as_html(self) -> str:
        """Render as HTML."""
        ts = self.generated_at.strftime("%Y-%m-%d %H:%M")
        parts: list[str] = [
            "<!DOCTYPE html>",
            "<html>",
            "<head>",
            "<meta charset='utf-8'>",
            "<style>",
            "body{font-family:sans-serif;max-width:700px;margin:0 auto;padding:20px;color:#333}",
            "h1{font-size:1.4em;border-bottom:2px solid #4a90d9;padding-bottom:8px}",
            "h2{font-size:1.1em;margin-top:24px;margin-bottom:8px;color:#4a90d9}",
            ".item{margin-bottom:12px;padding:10px;background:#f8f9fa;border-radius:4px;border-left:3px solid #4a90d9}",
            ".action-item{border-left-color:#e67e22}",
            ".meta{font-size:0.85em;color:#777;margin-top:4px}",
            ".priority-urgent{color:#c0392b;font-weight:bold}",
            ".priority-high{color:#e67e22;font-weight:bold}",
            ".priority-medium{color:#2980b9}",
            ".priority-low{color:#7f8c8d}",
            ".completed{opacity:0.6;text-decoration:line-through}",
            "a{color:#4a90d9}",
            "</style>",
            "</head>",
            "<body>",
            f"<h1>Beacon Digest &mdash; {html.escape(self.window.title())} &mdash; {html.escape(ts)}</h1>",
        ]

        if self.events:
            parts.append(f"<h2>Events ({len(self.events)})</h2>")
            for ev in self.events:
                title = html.escape(ev.get("title", "(no title)"))
                src = html.escape(ev.get("source_type", ""))
                occurred = ev.get("occurred_at", "")
                if occurred:
                    try:
                        dt = datetime.fromisoformat(occurred)
                        occurred = dt.strftime("%Y-%m-%d %H:%M")
                    except ValueError:
                        pass
                summary = html.escape(ev.get("summary", ""))
                url = ev.get("url", "")
                parts.append("<div class='item'>")
                if url:
                    parts.append(f"<strong><a href='{html.escape(url)}'>{title}</a></strong>")
                else:
                    parts.append(f"<strong>{title}</strong>")
                meta_parts = []
                if src:
                    meta_parts.append(f"source: {src}")
                if occurred:
                    meta_parts.append(occurred)
                if meta_parts:
                    parts.append(f"<div class='meta'>{' &bull; '.join(meta_parts)}</div>")
                if summary:
                    parts.append(f"<div>{summary}</div>")
                parts.append("</div>")

        if self.action_items:
            parts.append(f"<h2>Action Items ({len(self.action_items)})</h2>")
            for ai in self.action_items:
                title = html.escape(ai.get("title", "(no title)"))
                priority = ai.get("priority", "medium").lower()
                src = html.escape(ai.get("source_type", ""))
                completed = ai.get("completed", False)
                url = ai.get("url", "")
                due = ai.get("due_at", "")
                if due:
                    try:
                        dt = datetime.fromisoformat(due)
                        due = dt.strftime("%Y-%m-%d %H:%M")
                    except ValueError:
                        pass
                css = "item action-item"
                if completed:
                    css += " completed"
                parts.append(f"<div class='{css}'>")
                if url:
                    parts.append(
                        f"<strong><a href='{html.escape(url)}'>{title}</a></strong> "
                        f"<span class='priority-{html.escape(priority)}'>[{html.escape(priority.upper())}]</span>"
                    )
                else:
                    parts.append(
                        f"<strong>{title}</strong> "
                        f"<span class='priority-{html.escape(priority)}'>[{html.escape(priority.upper())}]</span>"
                    )
                meta_parts = []
                if src:
                    meta_parts.append(f"source: {src}")
                if due:
                    meta_parts.append(f"due: {html.escape(due)}")
                if meta_parts:
                    parts.append(f"<div class='meta'>{' &bull; '.join(meta_parts)}</div>")
                parts.append("</div>")

        if not self.events and not self.action_items:
            parts.append("<p><em>Nothing to report.</em></p>")

        parts.extend(["</body>", "</html>"])
        return "\n".join(parts)


def compile_digest(
    events: list[dict[str, Any]],
    action_items: list[dict[str, Any]],
    window: str = "all",
    max_events: int = 20,
    max_actions: int = 10,
    now: datetime | None = None,
) -> Digest:
    """Compile events and action items into a Digest.

    Args:
        events: List of event dicts (from last_sync.json).
        action_items: List of action item dicts.
        window: "morning", "evening", or "all".
        max_events: Maximum number of events to include.
        max_actions: Maximum number of action items to include.
        now: Reference datetime (default: UTC now).
    """
    if now is None:
        now = datetime.now(tz=timezone.utc)

    filtered_events = _filter_by_window(events, window, now)
    filtered_actions = [ai for ai in action_items if not ai.get("completed", False)]

    return Digest(
        generated_at=now,
        window=window,
        events=filtered_events[:max_events],
        action_items=filtered_actions[:max_actions],
    )


def _filter_by_window(
    events: list[dict[str, Any]],
    window: str,
    now: datetime,
) -> list[dict[str, Any]]:
    """Filter events based on morning/evening/all time window."""
    if window == "all":
        return list(events)

    result = []
    for ev in events:
        occurred = ev.get("occurred_at")
        if occurred is None:
            result.append(ev)
            continue
        try:
            dt = datetime.fromisoformat(occurred)
        except ValueError:
            result.append(ev)
            continue

        # Make naive for comparison
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        now_naive = now.replace(tzinfo=None) if now.tzinfo else now

        today_start = now_naive.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = now_naive.replace(hour=23, minute=59, second=59, microsecond=0)

        if window == "morning":
            # Events from today up to noon
            morning_end = now_naive.replace(hour=12, minute=0, second=0, microsecond=0)
            if today_start <= dt <= morning_end:
                result.append(ev)
        elif window == "evening":
            # Events from noon to end of day
            evening_start = now_naive.replace(hour=12, minute=0, second=0, microsecond=0)
            if evening_start <= dt <= today_end:
                result.append(ev)
        else:
            result.append(ev)

    return result


def load_digest_config(raw_config: dict[str, Any]) -> dict[str, Any]:
    """Extract digest settings from raw beacon.toml config."""
    notifications = raw_config.get("notifications", {})
    return notifications.get("digest", {})
