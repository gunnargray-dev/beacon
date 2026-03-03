"""Tests for the News/RSS connector."""

from __future__ import annotations

import textwrap
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.connectors.base import ConnectorError
from src.connectors.news import (
    NewsConnector,
    _fetch_feed,
    _matches_keywords,
    _parse_date,
    _parse_feed_xml,
    _parse_rss,
    _parse_atom,
)
from src.models import Source, SourceType


# ---------------------------------------------------------------------------
# Sample XML
# ---------------------------------------------------------------------------

RSS_FEED = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>Test Feed</title>
        <item>
          <title>Article One</title>
          <link>https://example.com/1</link>
          <description>First article about Python</description>
          <pubDate>Mon, 01 Jan 2024 12:00:00 +0000</pubDate>
        </item>
        <item>
          <title>Article Two</title>
          <link>https://example.com/2</link>
          <description>Second article about Rust</description>
          <pubDate>Tue, 02 Jan 2024 12:00:00 +0000</pubDate>
        </item>
      </channel>
    </rss>
""")

ATOM_FEED = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <title>Atom Test Feed</title>
      <entry>
        <title>Atom Entry One</title>
        <link href="https://atom.example.com/1"/>
        <summary>Summary of entry one</summary>
        <published>2024-01-01T12:00:00Z</published>
      </entry>
      <entry>
        <title>Atom Entry Two</title>
        <link href="https://atom.example.com/2"/>
        <summary>Entry about Go programming</summary>
        <published>2024-01-02T12:00:00Z</published>
      </entry>
    </feed>
""")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_source(config: dict | None = None) -> Source:
    return Source(
        name="test-news",
        source_type=SourceType.NEWS,
        config=config or {},
    )


# ---------------------------------------------------------------------------
# _parse_date
# ---------------------------------------------------------------------------


class TestParseDateNews:
    def test_rfc2822(self):
        dt = _parse_date("Mon, 01 Jan 2024 12:00:00 +0000")
        assert dt.year == 2024
        assert dt.tzinfo is not None

    def test_iso8601(self):
        dt = _parse_date("2024-01-01T12:00:00Z")
        assert dt.year == 2024

    def test_empty_returns_now(self):
        before = datetime.now(tz=timezone.utc)
        dt = _parse_date("")
        after = datetime.now(tz=timezone.utc)
        assert before <= dt <= after

    def test_invalid_returns_now(self):
        dt = _parse_date("not-a-date")
        assert isinstance(dt, datetime)


# ---------------------------------------------------------------------------
# _parse_rss / _parse_atom / _parse_feed_xml
# ---------------------------------------------------------------------------


class TestParseRss:
    def test_parses_items(self):
        import xml.etree.ElementTree as ET
        root = ET.fromstring(RSS_FEED)
        items = _parse_rss(root, "example.com")
        assert len(items) == 2
        assert items[0]["title"] == "Article One"
        assert items[0]["link"] == "https://example.com/1"
        assert items[0]["source"] == "example.com"

    def test_description_present(self):
        import xml.etree.ElementTree as ET
        root = ET.fromstring(RSS_FEED)
        items = _parse_rss(root, "x")
        assert "Python" in items[0]["description"]


class TestParseAtom:
    def test_parses_entries(self):
        import xml.etree.ElementTree as ET
        root = ET.fromstring(ATOM_FEED)
        items = _parse_atom(root, "atom.example.com")
        assert len(items) == 2
        assert items[0]["title"] == "Atom Entry One"
        assert items[0]["link"] == "https://atom.example.com/1"

    def test_summary_present(self):
        import xml.etree.ElementTree as ET
        root = ET.fromstring(ATOM_FEED)
        items = _parse_atom(root, "x")
        assert "Summary" in items[0]["description"]


class TestParseFeedXml:
    def test_detects_rss(self):
        items = _parse_feed_xml(RSS_FEED, "example.com")
        assert len(items) == 2
        assert items[0]["title"] == "Article One"

    def test_detects_atom(self):
        items = _parse_feed_xml(ATOM_FEED, "atom.example.com")
        assert len(items) == 2
        assert items[0]["title"] == "Atom Entry One"

    def test_invalid_xml_raises(self):
        with pytest.raises(ConnectorError, match="Invalid XML"):
            _parse_feed_xml("not xml at all {{{{", "x")


# ---------------------------------------------------------------------------
# _matches_keywords
# ---------------------------------------------------------------------------


class TestMatchesKeywords:
    def test_no_keywords_matches_all(self):
        item = {"title": "anything", "description": ""}
        assert _matches_keywords(item, []) is True

    def test_keyword_in_title(self):
        item = {"title": "Python 3.12 released", "description": ""}
        assert _matches_keywords(item, ["python"]) is True

    def test_keyword_in_description(self):
        item = {"title": "News", "description": "Rust is fast"}
        assert _matches_keywords(item, ["rust"]) is True

    def test_keyword_case_insensitive(self):
        item = {"title": "PYTHON News", "description": ""}
        assert _matches_keywords(item, ["python"]) is True

    def test_no_match_returns_false(self):
        item = {"title": "Cooking tips", "description": "Recipe ideas"}
        assert _matches_keywords(item, ["kubernetes"]) is False


# ---------------------------------------------------------------------------
# _fetch_feed
# ---------------------------------------------------------------------------


class TestFetchFeed:
    def test_fetches_url(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"<rss/>"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = _fetch_feed("https://example.com/feed.rss")
        assert result == "<rss/>"

    def test_network_error_raises(self):
        import urllib.error
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("timeout"),
        ):
            with pytest.raises(ConnectorError, match="Failed to fetch"):
                _fetch_feed("https://example.com/bad.rss")


# ---------------------------------------------------------------------------
# NewsConnector
# ---------------------------------------------------------------------------


class TestNewsConnectorValidateConfig:
    def test_valid_with_feeds_list(self):
        conn = NewsConnector(
            _make_source({"feeds": ["https://example.com/feed.rss"]})
        )
        assert conn.validate_config() is True

    def test_invalid_empty_feeds(self):
        conn = NewsConnector(_make_source({"feeds": []}))
        assert conn.validate_config() is False

    def test_invalid_no_feeds_key(self):
        conn = NewsConnector(_make_source())
        assert conn.validate_config() is False

    def test_invalid_feeds_not_list(self):
        conn = NewsConnector(_make_source({"feeds": "https://example.com/rss"}))
        assert conn.validate_config() is False


class TestNewsConnectorSync:
    def _mock_url_fetch(self, xml_text: str):
        mock_resp = MagicMock()
        mock_resp.read.return_value = xml_text.encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return patch("urllib.request.urlopen", return_value=mock_resp)

    def test_sync_raises_if_no_feeds(self):
        conn = NewsConnector(_make_source())
        with pytest.raises(ConnectorError):
            conn.sync()

    def test_sync_rss_returns_events(self):
        with self._mock_url_fetch(RSS_FEED):
            conn = NewsConnector(
                _make_source({"feeds": ["https://example.com/feed.rss"]})
            )
            events, actions = conn.sync()
        assert len(events) == 2
        assert actions == []
        assert all(ev.source_type == SourceType.NEWS for ev in events)

    def test_sync_atom_returns_events(self):
        with self._mock_url_fetch(ATOM_FEED):
            conn = NewsConnector(
                _make_source({"feeds": ["https://atom.example.com/feed"]})
            )
            events, _ = conn.sync()
        assert len(events) == 2

    def test_sync_keyword_filter(self):
        with self._mock_url_fetch(RSS_FEED):
            conn = NewsConnector(
                _make_source({
                    "feeds": ["https://example.com/feed.rss"],
                    "keywords": ["python"],
                })
            )
            events, _ = conn.sync()
        # Only "Article One" mentions Python
        assert len(events) == 1
        assert "One" in events[0].title

    def test_sync_max_items_respected(self):
        with self._mock_url_fetch(RSS_FEED):
            conn = NewsConnector(
                _make_source({
                    "feeds": ["https://example.com/feed.rss"],
                    "max_items_per_feed": 1,
                })
            )
            events, _ = conn.sync()
        assert len(events) == 1

    def test_sync_failing_feed_is_skipped(self):
        import urllib.error
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("timeout"),
        ):
            conn = NewsConnector(
                _make_source({
                    "feeds": ["https://example.com/bad.rss"],
                })
            )
            events, _ = conn.sync()
        # Failing feed is skipped, not raised
        assert events == []

    def test_event_url_populated(self):
        with self._mock_url_fetch(RSS_FEED):
            conn = NewsConnector(
                _make_source({"feeds": ["https://example.com/feed.rss"]})
            )
            events, _ = conn.sync()
        assert all(ev.url for ev in events)

    def test_event_source_id(self):
        with self._mock_url_fetch(RSS_FEED):
            src = _make_source({"feeds": ["https://example.com/feed.rss"]})
            conn = NewsConnector(src)
            events, _ = conn.sync()
        assert all(ev.source_id == src.id for ev in events)

    def test_connector_type(self):
        assert NewsConnector.connector_type == SourceType.NEWS
