"""News/RSS connector -- parses RSS 2.0 and Atom 1.0 feeds via stdlib xml.etree."""

from __future__ import annotations

import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from src.connectors.base import BaseConnector, ConnectorError, registry
from src.models import ActionItem, Event, Source, SourceType

# XML namespaces used in Atom feeds
_ATOM_NS = "http://www.w3.org/2005/Atom"
_CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"


def _parse_date(date_str: str) -> datetime:
    """Parse RFC-2822 or ISO-8601 date strings into a UTC-aware datetime."""
    if not date_str:
        return datetime.now(tz=timezone.utc)
    # Try RFC-2822 (RSS)
    try:
        return parsedate_to_datetime(date_str).astimezone(timezone.utc)
    except Exception:
        pass
    # Try ISO-8601 / Atom
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            continue
    return datetime.now(tz=timezone.utc)


def _fetch_feed(url: str) -> str:
    """Fetch raw XML from a feed URL."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Beacon/0.1 (RSS reader; +https://github.com/gunnargray-dev/beacon)"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        raise ConnectorError(f"Failed to fetch feed {url}: {exc}") from exc


def _parse_rss(root: ET.Element, source_name: str) -> list[dict[str, str]]:
    """Parse RSS 2.0 <item> elements."""
    items: list[dict[str, str]] = []
    for item in root.findall(".//item"):
        items.append(
            {
                "title": (item.findtext("title") or "").strip(),
                "link": (item.findtext("link") or "").strip(),
                "description": (item.findtext("description") or "").strip(),
                "pubDate": (item.findtext("pubDate") or "").strip(),
                "source": source_name,
            }
        )
    return items


def _parse_atom(root: ET.Element, source_name: str) -> list[dict[str, str]]:
    """Parse Atom 1.0 <entry> elements."""
    ns = _ATOM_NS
    items: list[dict[str, str]] = []
    for entry in root.findall(f"{{{ns}}}entry"):
        title = (entry.findtext(f"{{{ns}}}title") or "").strip()
        # Atom links are in <link href="..." />
        link_el = entry.find(f"{{{ns}}}link")
        link = (link_el.get("href", "") if link_el is not None else "").strip()
        summary = (entry.findtext(f"{{{ns}}}summary") or "").strip()
        published = (
            entry.findtext(f"{{{ns}}}published")
            or entry.findtext(f"{{{ns}}}updated")
            or ""
        ).strip()
        items.append(
            {
                "title": title,
                "link": link,
                "description": summary,
                "pubDate": published,
                "source": source_name,
            }
        )
    return items


def _parse_feed_xml(xml_text: str, source_name: str) -> list[dict[str, str]]:
    """Auto-detect RSS vs Atom and return a normalised item list."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ConnectorError(f"Invalid XML in feed: {exc}") from exc

    # Atom: root tag contains the Atom namespace
    tag = root.tag
    if "atom" in tag.lower() or tag == f"{{{_ATOM_NS}}}feed":
        return _parse_atom(root, source_name)
    # RSS: look for <channel>/<item>
    return _parse_rss(root, source_name)


def _matches_keywords(item: dict[str, str], keywords: list[str]) -> bool:
    """Return True if any keyword (case-insensitive) appears in title or description."""
    if not keywords:
        return True
    text = (item.get("title", "") + " " + item.get("description", "")).lower()
    return any(kw.lower() in text for kw in keywords)


# ---------------------------------------------------------------------------
# Connector
# ---------------------------------------------------------------------------


@registry.register
class NewsConnector(BaseConnector):
    """Connector for RSS/Atom news feeds."""

    connector_type = SourceType.NEWS

    def validate_config(self) -> bool:
        feeds = self.get_config("feeds", [])
        return bool(feeds) and isinstance(feeds, list)

    def sync(self) -> tuple[list[Event], list[ActionItem]]:
        if not self.validate_config():
            raise ConnectorError("News connector requires a 'feeds' list in config")

        feeds: list[str] = self.get_config("feeds", [])
        keywords: list[str] = self.get_config("keywords", [])
        max_items: int = int(self.get_config("max_items_per_feed", 20))

        events: list[Event] = []

        for feed_url in feeds:
            feed_url = feed_url.strip()
            if not feed_url:
                continue
            # Derive a short source label from the URL hostname
            try:
                from urllib.parse import urlparse
                host = urlparse(feed_url).netloc or feed_url
                source_label = host.replace("www.", "")
            except Exception:
                source_label = feed_url

            try:
                xml_text = _fetch_feed(feed_url)
                items = _parse_feed_xml(xml_text, source_label)
            except ConnectorError:
                # Skip failing feeds rather than aborting entire sync
                continue

            count = 0
            for item in items:
                if count >= max_items:
                    break
                if not _matches_keywords(item, keywords):
                    continue

                pub_date = _parse_date(item.get("pubDate", ""))
                meta: dict[str, Any] = {
                    "feed_url": feed_url,
                    "feed_source": item.get("source", source_label),
                    "description": item.get("description", "")[:500],
                }

                events.append(
                    Event(
                        title=item.get("title") or "(No title)",
                        source_id=self.source.id,
                        source_type=SourceType.NEWS,
                        occurred_at=pub_date,
                        summary=item.get("description", "")[:200],
                        url=item.get("link", ""),
                        metadata=meta,
                    )
                )
                count += 1

        return events, []
