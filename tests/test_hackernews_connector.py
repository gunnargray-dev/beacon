"""Tests for the Hacker News connector."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.connectors.base import ConnectorError
from src.connectors.hackernews import (
    HackerNewsConnector,
    _fetch_item,
    _fetch_json,
    _fetch_top_story_ids,
    _item_to_event,
)
from src.models import Event, Source, SourceType


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_STORY = {
    "id": 12345,
    "type": "story",
    "title": "Ask HN: Favorite programming languages in 2024?",
    "url": "https://example.com/article",
    "score": 342,
    "descendants": 87,
    "by": "hacker42",
    "time": 1704067200,  # 2024-01-01 00:00:00 UTC
}

SAMPLE_IDS = [12345, 99999, 11111, 22222, 33333, 44444, 55555, 66666, 77777, 88888]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_source(config: dict | None = None) -> Source:
    return Source(
        name="test-hn",
        source_type=SourceType.HACKER_NEWS,
        config=config or {},
    )


def _make_connector(config: dict | None = None) -> HackerNewsConnector:
    return HackerNewsConnector(_make_source(config or {}))


def _mock_urlopen(data):
    response = MagicMock()
    response.read.return_value = json.dumps(data).encode()
    response.__enter__ = lambda s: s
    response.__exit__ = MagicMock(return_value=False)
    return response


# ---------------------------------------------------------------------------
# _fetch_json
# ---------------------------------------------------------------------------


class TestFetchJson:
    def test_returns_parsed_data(self):
        with patch("urllib.request.urlopen", return_value=_mock_urlopen([1, 2, 3])):
            result = _fetch_json("https://example.com/data.json")
        assert result == [1, 2, 3]

    def test_raises_on_http_error(self):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(
            url="", code=503, msg="Service Unavailable", hdrs=None, fp=None  # type: ignore[arg-type]
        )):
            with pytest.raises(ConnectorError, match="503"):
                _fetch_json("https://example.com/data.json")

    def test_raises_on_url_error(self):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
            with pytest.raises(ConnectorError, match="network error"):
                _fetch_json("https://example.com/data.json")

    def test_raises_on_invalid_json(self):
        resp = MagicMock()
        resp.read.return_value = b"not json {"
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=resp):
            with pytest.raises(ConnectorError, match="Invalid JSON"):
                _fetch_json("https://example.com/data.json")


# ---------------------------------------------------------------------------
# _item_to_event
# ---------------------------------------------------------------------------


class TestItemToEvent:
    def test_basic_story(self):
        event = _item_to_event(SAMPLE_STORY, "src-id")
        assert isinstance(event, Event)
        assert event.source_type == SourceType.HACKER_NEWS

    def test_title_preserved(self):
        event = _item_to_event(SAMPLE_STORY, "src-id")
        assert event.title == SAMPLE_STORY["title"]

    def test_url_from_story(self):
        event = _item_to_event(SAMPLE_STORY, "src-id")
        assert event.url == SAMPLE_STORY["url"]

    def test_url_falls_back_to_hn_item_url(self):
        story = dict(SAMPLE_STORY)
        del story["url"]
        event = _item_to_event(story, "src-id")
        assert "news.ycombinator.com" in event.url

    def test_score_in_summary(self):
        event = _item_to_event(SAMPLE_STORY, "src-id")
        assert "342" in event.summary

    def test_comments_in_summary(self):
        event = _item_to_event(SAMPLE_STORY, "src-id")
        assert "87" in event.summary

    def test_author_in_summary(self):
        event = _item_to_event(SAMPLE_STORY, "src-id")
        assert "hacker42" in event.summary

    def test_timestamp_converted(self):
        event = _item_to_event(SAMPLE_STORY, "src-id")
        assert event.occurred_at == datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    def test_metadata_contains_score(self):
        event = _item_to_event(SAMPLE_STORY, "src-id")
        assert event.metadata["score"] == 342

    def test_metadata_contains_hn_url(self):
        event = _item_to_event(SAMPLE_STORY, "src-id")
        assert "hn_url" in event.metadata
        assert "news.ycombinator.com" in event.metadata["hn_url"]

    def test_missing_timestamp_uses_now(self):
        story = dict(SAMPLE_STORY)
        story["time"] = 0
        event = _item_to_event(story, "src-id")
        assert event.occurred_at.tzinfo is not None


# ---------------------------------------------------------------------------
# HackerNewsConnector.validate_config
# ---------------------------------------------------------------------------


class TestValidateConfig:
    def test_default_config_valid(self):
        conn = _make_connector()
        assert conn.validate_config() is True

    def test_explicit_valid_count(self):
        conn = _make_connector({"story_count": 5})
        assert conn.validate_config() is True

    def test_count_zero_invalid(self):
        conn = _make_connector({"story_count": 0})
        assert conn.validate_config() is False

    def test_count_101_invalid(self):
        conn = _make_connector({"story_count": 101})
        assert conn.validate_config() is False

    def test_non_numeric_count_invalid(self):
        conn = _make_connector({"story_count": "abc"})
        assert conn.validate_config() is False


# ---------------------------------------------------------------------------
# HackerNewsConnector.test_connection
# ---------------------------------------------------------------------------


class TestTestConnection:
    def test_returns_true_on_success(self):
        conn = _make_connector()
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(SAMPLE_IDS)):
            assert conn.test_connection() is True

    def test_returns_false_on_error(self):
        import urllib.error
        conn = _make_connector()
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("fail")):
            assert conn.test_connection() is False


# ---------------------------------------------------------------------------
# HackerNewsConnector.sync
# ---------------------------------------------------------------------------


class TestSync:
    def test_sync_returns_stories(self):
        conn = _make_connector({"story_count": 2})
        story2 = dict(SAMPLE_STORY, id=99999, title="Another story")
        with patch("urllib.request.urlopen", side_effect=[
            _mock_urlopen(SAMPLE_IDS),   # topstories
            _mock_urlopen(SAMPLE_STORY), # item 12345
            _mock_urlopen(story2),       # item 99999
        ]):
            events, action_items = conn.sync()
        assert len(events) == 2
        assert action_items == []

    def test_sync_respects_story_count(self):
        conn = _make_connector({"story_count": 3})
        responses = [_mock_urlopen(SAMPLE_IDS)]
        for i in range(3):
            responses.append(_mock_urlopen(dict(SAMPLE_STORY, id=SAMPLE_IDS[i])))
        with patch("urllib.request.urlopen", side_effect=responses):
            events, _ = conn.sync()
        assert len(events) == 3

    def test_sync_skips_non_story_items(self):
        conn = _make_connector({"story_count": 2})
        comment_item = {"id": 99999, "type": "comment", "text": "A comment"}
        with patch("urllib.request.urlopen", side_effect=[
            _mock_urlopen(SAMPLE_IDS),
            _mock_urlopen(comment_item),  # skipped (not story type)
            _mock_urlopen(SAMPLE_STORY),  # fetched
            _mock_urlopen(dict(SAMPLE_STORY, id=11111, title="Third")),
        ]):
            events, _ = conn.sync()
        assert len(events) == 2

    def test_sync_respects_min_score(self):
        # Use story_count=1 so we only need one passing story
        conn = _make_connector({"story_count": 1, "min_score": 500})
        low_score = dict(SAMPLE_STORY, id=SAMPLE_IDS[0], score=100)
        high_score = dict(SAMPLE_STORY, id=SAMPLE_IDS[1], title="High scorer", score=600)
        with patch("urllib.request.urlopen", side_effect=[
            _mock_urlopen(SAMPLE_IDS),
            _mock_urlopen(low_score),   # first ID: score 100, filtered out
            _mock_urlopen(high_score),  # second ID: score 600, included
        ]):
            events, _ = conn.sync()
        assert len(events) == 1
        assert events[0].metadata["score"] == 600

    def test_sync_keyword_filter(self):
        # Use story_count=1 to keep the test simple
        conn = _make_connector({"story_count": 1, "keywords": ["python"]})
        rust_story = dict(SAMPLE_STORY, id=SAMPLE_IDS[0], title="Rust 2024 edition")
        python_story = dict(SAMPLE_STORY, id=SAMPLE_IDS[1], title="Python 4.0 released")
        with patch("urllib.request.urlopen", side_effect=[
            _mock_urlopen(SAMPLE_IDS),
            _mock_urlopen(rust_story),    # first ID: no keyword match
            _mock_urlopen(python_story),  # second ID: matches "python"
        ]):
            events, _ = conn.sync()
        assert len(events) == 1
        assert "python" in events[0].title.lower()

    def test_sync_raises_on_topstories_failure(self):
        import urllib.error
        conn = _make_connector()
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
            with pytest.raises(ConnectorError):
                conn.sync()

    def test_sync_skips_failed_item_fetch(self):
        import urllib.error
        conn = _make_connector({"story_count": 2})
        with patch("urllib.request.urlopen", side_effect=[
            _mock_urlopen(SAMPLE_IDS),          # topstories
            urllib.error.URLError("item fail"),   # item 12345 fails
            _mock_urlopen(SAMPLE_STORY),          # item 99999 succeeds
            _mock_urlopen(dict(SAMPLE_STORY, id=11111, title="Third")),
        ]):
            events, _ = conn.sync()
        assert len(events) == 2

    def test_sync_caps_at_max_story_count(self):
        """story_count is capped at 30 internally."""
        conn = _make_connector({"story_count": 99})
        ids = list(range(1, 50))
        responses = [_mock_urlopen(ids)]
        for i in range(31):  # provide 31 items; should only consume 30
            responses.append(_mock_urlopen(dict(SAMPLE_STORY, id=i + 1)))
        with patch("urllib.request.urlopen", side_effect=responses):
            events, _ = conn.sync()
        assert len(events) <= 30
