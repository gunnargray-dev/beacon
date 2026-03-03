"""Hacker News connector -- top stories via the HN Firebase REST API."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from src.connectors.base import BaseConnector, ConnectorError, registry
from src.models import ActionItem, Event, Source, SourceType

_HN_API = "https://hacker-news.firebaseio.com/v0"
_DEFAULT_STORY_COUNT = 10
_MAX_STORY_COUNT = 30


def _fetch_json(url: str) -> Any:
    """Fetch and parse JSON from a URL."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Beacon/0.1 (HN reader; +https://github.com/gunnargray-dev/beacon)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ConnectorError(f"HN API error {exc.code} for {url}: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise ConnectorError(f"HN network error for {url}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ConnectorError(f"Invalid JSON from HN API: {exc}") from exc


def _fetch_top_story_ids() -> list[int]:
    """Return the list of current top story IDs from HN."""
    return _fetch_json(f"{_HN_API}/topstories.json")


def _fetch_item(item_id: int) -> dict[str, Any]:
    """Fetch a single HN item by ID."""
    return _fetch_json(f"{_HN_API}/item/{item_id}.json")


def _item_to_event(item: dict[str, Any], source_id: str) -> Event:
    """Convert an HN item dict into an Event."""
    title = item.get("title", "(No title)")
    url = item.get("url", f"https://news.ycombinator.com/item?id={item.get('id', '')}")
    score = item.get("score", 0)
    comment_count = item.get("descendants", 0)
    by = item.get("by", "?")
    timestamp = item.get("time", 0)
    item_id = item.get("id", "")

    occurred_at = (
        datetime.fromtimestamp(timestamp, tz=timezone.utc)
        if timestamp
        else datetime.now(tz=timezone.utc)
    )
    hn_url = f"https://news.ycombinator.com/item?id={item_id}"

    return Event(
        title=title,
        source_id=source_id,
        source_type=SourceType.HACKER_NEWS,
        occurred_at=occurred_at,
        summary=f"Score: {score} | Comments: {comment_count} | by {by}",
        url=url,
        metadata={
            "type": "story",
            "hn_id": item_id,
            "hn_url": hn_url,
            "score": score,
            "comments": comment_count,
            "author": by,
        },
    )


# ---------------------------------------------------------------------------
# Connector
# ---------------------------------------------------------------------------


@registry.register
class HackerNewsConnector(BaseConnector):
    """Connector for Hacker News top stories via the Firebase REST API."""

    connector_type = SourceType.HACKER_NEWS

    def validate_config(self) -> bool:
        # No required keys -- story_count is optional
        count = self.get_config("story_count", _DEFAULT_STORY_COUNT)
        try:
            return 1 <= int(count) <= 100
        except (TypeError, ValueError):
            return False

    def test_connection(self) -> bool:
        try:
            _fetch_top_story_ids()
            return True
        except ConnectorError:
            return False

    def sync(self) -> tuple[list[Event], list[ActionItem]]:
        story_count = min(
            int(self.get_config("story_count", _DEFAULT_STORY_COUNT)),
            _MAX_STORY_COUNT,
        )
        min_score = int(self.get_config("min_score", 0))
        keywords: list[str] = self.get_config("keywords", [])

        try:
            ids = _fetch_top_story_ids()
        except ConnectorError as exc:
            raise ConnectorError(f"Failed to fetch HN top stories: {exc}") from exc

        events: list[Event] = []
        fetched = 0
        for story_id in ids:
            if fetched >= story_count:
                break
            try:
                item = _fetch_item(story_id)
            except ConnectorError:
                continue

            if not item or item.get("type") != "story":
                continue
            if item.get("score", 0) < min_score:
                continue

            # Keyword filter
            if keywords:
                title = item.get("title", "").lower()
                if not any(kw.lower() in title for kw in keywords):
                    continue

            events.append(_item_to_event(item, self.source.id))
            fetched += 1

        return events, []
