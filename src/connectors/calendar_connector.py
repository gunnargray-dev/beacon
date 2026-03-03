"""Calendar connector -- parses iCal/ICS feeds via urllib (stdlib only)."""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.connectors.base import BaseConnector, ConnectorError, registry
from src.models import ActionItem, Event, Priority, Source, SourceType

# ---------------------------------------------------------------------------
# iCal parser (pure stdlib, no third-party icalendar library)
# ---------------------------------------------------------------------------

_DTFMT_BASIC = "%Y%m%dT%H%M%SZ"
_DTFMT_BASIC_LOCAL = "%Y%m%dT%H%M%S"
_DTFMT_DATE_ONLY = "%Y%m%d"


def _parse_dt(value: str) -> datetime | None:
    """Parse an iCal DTSTART/DTEND value string into a datetime."""
    # Strip TZID= or VALUE= parameter prefixes: e.g. "TZID=America/New_York:20240101T090000"
    if ":" in value:
        value = value.split(":")[-1]
    value = value.strip()
    for fmt in (_DTFMT_BASIC, _DTFMT_BASIC_LOCAL, _DTFMT_DATE_ONLY):
        try:
            dt = datetime.strptime(value, fmt)
            if fmt == _DTFMT_BASIC:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def _unfold(lines: list[str]) -> list[str]:
    """Unfold iCal line continuations (RFC 5545 §3.1)."""
    result: list[str] = []
    for line in lines:
        if line.startswith((" ", "\t")) and result:
            result[-1] += line[1:]
        else:
            result.append(line)
    return result


def _parse_ics(text: str) -> list[dict[str, str]]:
    """Parse an ICS string and return a list of VEVENT property dicts."""
    lines = _unfold(text.splitlines())
    events: list[dict[str, str]] = []
    current: dict[str, str] | None = None

    for line in lines:
        if line.strip() == "BEGIN:VEVENT":
            current = {}
        elif line.strip() == "END:VEVENT":
            if current is not None:
                events.append(current)
            current = None
        elif current is not None and ":" in line:
            # Key may carry parameters: DTSTART;TZID=America/New_York:20240101T090000
            raw_key, _, raw_val = line.partition(":")
            # Normalise key to bare property name
            key = raw_key.split(";")[0].upper().strip()
            # Re-attach value (partition consumed first ":")
            # For DTSTART;TZID=...:value we want the full "raw_key:raw_val" for dt parsing
            if key in ("DTSTART", "DTEND", "DTSTART", "DUE"):
                current[key] = raw_key + ":" + raw_val  # keep param for _parse_dt
            else:
                current[key] = raw_val.strip()

    return events


def _fetch_ics(source_cfg: dict[str, Any]) -> str:
    """Fetch ICS content from a URL or local file path."""
    url = source_cfg.get("calendar_url", "")
    file_path = source_cfg.get("calendar_file", "")

    if file_path:
        try:
            return Path(file_path).expanduser().read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise ConnectorError(f"Failed to read calendar file {file_path}: {exc}") from exc

    if url:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Beacon/0.1"})
            with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.URLError as exc:
            raise ConnectorError(f"Failed to fetch calendar from {url}: {exc}") from exc

    raise ConnectorError("Calendar connector requires 'calendar_url' or 'calendar_file' in config")


def _detect_conflicts(vevents: list[dict[str, str]]) -> list[tuple[dict, dict]]:
    """Return pairs of events that overlap in time."""
    timed: list[tuple[datetime, datetime, dict]] = []
    for ev in vevents:
        start = _parse_dt(ev.get("DTSTART", ""))
        end = _parse_dt(ev.get("DTEND", ""))
        if start and end:
            timed.append((start, end, ev))

    conflicts: list[tuple[dict, dict]] = []
    for i, (s1, e1, ev1) in enumerate(timed):
        for s2, e2, ev2 in timed[i + 1 :]:
            if s1 < e2 and s2 < e1:  # overlap
                conflicts.append((ev1, ev2))
    return conflicts


# ---------------------------------------------------------------------------
# Connector
# ---------------------------------------------------------------------------


@registry.register
class CalendarConnector(BaseConnector):
    """Connector for iCal/ICS calendar feeds."""

    connector_type = SourceType.CALENDAR

    # How far ahead (days) to look for upcoming events (default: 36500 days / ~100 years)
    LOOKAHEAD_DAYS = 36500

    def validate_config(self) -> bool:
        has_url = bool(self.get_config("calendar_url"))
        has_file = bool(self.get_config("calendar_file"))
        return has_url or has_file

    def sync(self) -> tuple[list[Event], list[ActionItem]]:
        ics_text = _fetch_ics(self.source.config)
        vevents = _parse_ics(ics_text)

        now = datetime.now(tz=timezone.utc)
        cutoff = now + timedelta(days=self.LOOKAHEAD_DAYS)

        events: list[Event] = []
        action_items: list[ActionItem] = []

        conflicts = _detect_conflicts(vevents)
        conflict_summaries = {ev.get("SUMMARY", "") for pair in conflicts for ev in pair}

        for vevent in vevents:
            summary = vevent.get("SUMMARY", "(No title)")
            dtstart_raw = vevent.get("DTSTART", "")
            dtend_raw = vevent.get("DTEND", "")
            location = vevent.get("LOCATION", "")
            description = vevent.get("DESCRIPTION", "")
            url = vevent.get("URL", "")
            uid = vevent.get("UID", "")
            attendees_raw = vevent.get("ATTENDEE", "")

            start = _parse_dt(dtstart_raw)
            end = _parse_dt(dtend_raw)

            if start is None:
                continue

            # Make start timezone-aware for comparison
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            if end and end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)

            # Only include events in our lookahead window
            if start > cutoff or (end and end < now):
                continue

            meta: dict[str, Any] = {
                "uid": uid,
                "location": location,
                "start": start.isoformat(),
                "end": end.isoformat() if end else "",
                "attendees": attendees_raw,
            }

            event = Event(
                title=summary,
                source_id=self.source.id,
                source_type=SourceType.CALENDAR,
                occurred_at=start,
                summary=description[:500] if description else "",
                url=url,
                metadata=meta,
            )
            events.append(event)

            # Conflict => action item
            if summary in conflict_summaries:
                action_items.append(
                    ActionItem(
                        title=f"Scheduling conflict: {summary}",
                        source_id=self.source.id,
                        source_type=SourceType.CALENDAR,
                        priority=Priority.HIGH,
                        due_at=start,
                        notes=f"Overlaps with another event. Location: {location}",
                        metadata=meta,
                    )
                )

        return events, action_items
