"""Tests for the GitHub connector."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.connectors.base import ConnectorError
from src.connectors.github_connector import (
    GitHubConnector,
    _gh_request,
    _parse_dt,
)
from src.models import ActionItem, Event, Priority, Source, SourceType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_source(config: dict | None = None) -> Source:
    return Source(
        name="test-github",
        source_type=SourceType.GITHUB,
        config=config or {},
    )


def _make_connector(config: dict | None = None) -> GitHubConnector:
    if config is None:
        config = {"github_token": "tok", "github_username": "alice"}
    return GitHubConnector(_make_source(config))


def _mock_urlopen(data):
    """Return a context manager mock that reads json-encoded data."""
    response = MagicMock()
    response.read.return_value = json.dumps(data).encode()
    response.__enter__ = lambda s: s
    response.__exit__ = MagicMock(return_value=False)
    return response


# ---------------------------------------------------------------------------
# _parse_dt
# ---------------------------------------------------------------------------


class TestParseDt:
    def test_utc_z(self):
        dt = _parse_dt("2024-06-15T10:30:00Z")
        assert dt == datetime(2024, 6, 15, 10, 30, 0, tzinfo=timezone.utc)

    def test_with_offset(self):
        dt = _parse_dt("2024-06-15T10:30:00+00:00")
        assert dt == datetime(2024, 6, 15, 10, 30, 0, tzinfo=timezone.utc)

    def test_empty_returns_now(self):
        dt = _parse_dt("")
        assert dt.tzinfo is not None  # timezone-aware

    def test_invalid_returns_now(self):
        dt = _parse_dt("not-a-date")
        assert dt.tzinfo is not None


# ---------------------------------------------------------------------------
# _gh_request
# ---------------------------------------------------------------------------


class TestGhRequest:
    def test_returns_parsed_json(self):
        payload = {"login": "alice"}
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(payload)):
            result = _gh_request("/user", "mytoken")
        assert result == {"login": "alice"}

    def test_raises_on_http_error(self):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(
            url="", code=401, msg="Unauthorized", hdrs=None, fp=None  # type: ignore[arg-type]
        )):
            with pytest.raises(ConnectorError, match="401"):
                _gh_request("/user", "badtoken")

    def test_raises_on_url_error(self):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
            with pytest.raises(ConnectorError, match="network error"):
                _gh_request("/user", "tok")


# ---------------------------------------------------------------------------
# GitHubConnector.validate_config
# ---------------------------------------------------------------------------


class TestValidateConfig:
    def test_valid_config(self):
        conn = _make_connector({"github_token": "tok123", "github_username": "alice"})
        assert conn.validate_config() is True

    def test_missing_token(self):
        conn = _make_connector({"github_username": "alice"})
        assert conn.validate_config() is False

    def test_empty_token(self):
        conn = _make_connector({"github_token": "", "github_username": "alice"})
        assert conn.validate_config() is False

    def test_token_only_is_valid(self):
        # username is optional for validate_config
        conn = _make_connector({"github_token": "tok"})
        assert conn.validate_config() is True


# ---------------------------------------------------------------------------
# GitHubConnector.test_connection
# ---------------------------------------------------------------------------


class TestTestConnection:
    def test_returns_true_on_success(self):
        conn = _make_connector()
        with patch("urllib.request.urlopen", return_value=_mock_urlopen({"login": "alice"})):
            assert conn.test_connection() is True

    def test_returns_false_when_config_invalid(self):
        conn = _make_connector({})
        assert conn.test_connection() is False

    def test_returns_false_on_api_error(self):
        import urllib.error
        conn = _make_connector()
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("fail")):
            assert conn.test_connection() is False


# ---------------------------------------------------------------------------
# GitHubConnector.sync  -- notifications
# ---------------------------------------------------------------------------


class TestSyncNotifications:
    def _notification(self, title="PR title", reason="review_requested", repo="org/repo"):
        return {
            "id": "n1",
            "subject": {"title": title, "type": "PullRequest", "url": "https://api.github.com/repos/org/repo/pulls/1"},
            "repository": {"full_name": repo},
            "updated_at": "2024-01-01T10:00:00Z",
            "reason": reason,
        }

    def test_notification_becomes_event(self):
        conn = _make_connector()
        notifs = [self._notification(reason="subscribed")]
        with patch("urllib.request.urlopen", side_effect=[
            _mock_urlopen(notifs),    # /notifications
            _mock_urlopen({"items": []}),  # review-requested search
            _mock_urlopen({"items": []}),  # assigned issues search
        ]):
            events, action_items = conn.sync()
        assert any("PR title" in ev.title for ev in events)

    def test_review_requested_reason_creates_action_item(self):
        conn = _make_connector()
        notifs = [self._notification(reason="review_requested")]
        with patch("urllib.request.urlopen", side_effect=[
            _mock_urlopen(notifs),
            _mock_urlopen({"items": []}),
            _mock_urlopen({"items": []}),
        ]):
            events, action_items = conn.sync()
        assert any(ai.priority == Priority.HIGH for ai in action_items)

    def test_failed_notifications_does_not_abort(self):
        import urllib.error
        conn = _make_connector()
        with patch("urllib.request.urlopen", side_effect=[
            urllib.error.URLError("fail"),  # notifications fail
            _mock_urlopen({"items": []}),   # review search
            _mock_urlopen({"items": []}),   # assigned issues
        ]):
            # Should not raise, just return empty
            events, action_items = conn.sync()
        assert isinstance(events, list)


# ---------------------------------------------------------------------------
# GitHubConnector.sync  -- review requests
# ---------------------------------------------------------------------------


class TestSyncReviewRequests:
    def _pr_item(self, number=42, title="Fix bug", repo="org/repo"):
        return {
            "number": number,
            "title": title,
            "html_url": f"https://github.com/{repo}/pull/{number}",
            "repository_url": f"https://api.github.com/repos/{repo}",
            "created_at": "2024-01-01T09:00:00Z",
            "updated_at": "2024-01-01T09:00:00Z",
            "user": {"login": "bob"},
            "labels": [],
        }

    def test_review_request_creates_action_item(self):
        conn = _make_connector()
        with patch("urllib.request.urlopen", side_effect=[
            _mock_urlopen([]),  # notifications
            _mock_urlopen({"items": [self._pr_item()]}),  # review search
            _mock_urlopen({"items": []}),  # assigned issues
        ]):
            events, action_items = conn.sync()
        review_items = [ai for ai in action_items if "Review" in ai.title or "review" in ai.notes]
        assert len(review_items) >= 1
        assert review_items[0].priority == Priority.HIGH

    def test_review_request_creates_event(self):
        conn = _make_connector()
        with patch("urllib.request.urlopen", side_effect=[
            _mock_urlopen([]),
            _mock_urlopen({"items": [self._pr_item(title="Add feature")]}),
            _mock_urlopen({"items": []}),
        ]):
            events, action_items = conn.sync()
        assert any("Add feature" in ev.title for ev in events)


# ---------------------------------------------------------------------------
# GitHubConnector.sync  -- assigned issues
# ---------------------------------------------------------------------------


class TestSyncAssignedIssues:
    def _issue_item(self, number=10, title="Bug found", repo="org/repo", labels=None):
        return {
            "number": number,
            "title": title,
            "html_url": f"https://github.com/{repo}/issues/{number}",
            "repository_url": f"https://api.github.com/repos/{repo}",
            "created_at": "2024-01-01T08:00:00Z",
            "updated_at": "2024-01-01T08:00:00Z",
            "user": {"login": "charlie"},
            "labels": labels or [],
            "body": "Issue description here.",
        }

    def test_assigned_issue_creates_action_item(self):
        conn = _make_connector()
        with patch("urllib.request.urlopen", side_effect=[
            _mock_urlopen([]),
            _mock_urlopen({"items": []}),
            _mock_urlopen({"items": [self._issue_item()]}),
        ]):
            events, action_items = conn.sync()
        issue_items = [ai for ai in action_items if "Issue" in ai.title or "issue" in ai.notes.lower()]
        assert len(issue_items) >= 1

    def test_assigned_issue_creates_event(self):
        conn = _make_connector()
        with patch("urllib.request.urlopen", side_effect=[
            _mock_urlopen([]),
            _mock_urlopen({"items": []}),
            _mock_urlopen({"items": [self._issue_item(title="Crash on startup")]}),
        ]):
            events, action_items = conn.sync()
        assert any("Crash on startup" in ev.title for ev in events)


# ---------------------------------------------------------------------------
# GitHubConnector.sync  -- commits
# ---------------------------------------------------------------------------


class TestSyncCommits:
    def _commit(self, sha="abc1234567", msg="Initial commit", author="alice"):
        return {
            "sha": sha,
            "html_url": f"https://github.com/org/repo/commit/{sha}",
            "commit": {
                "message": msg,
                "author": {"name": author, "date": "2024-01-01T08:00:00Z"},
                "committer": {"name": author, "date": "2024-01-01T08:00:00Z"},
            },
        }

    def test_repo_commits_become_events(self):
        conn = _make_connector({"github_token": "tok", "github_username": "alice", "repos": ["org/repo"]})
        with patch("urllib.request.urlopen", side_effect=[
            _mock_urlopen([]),  # notifications
            _mock_urlopen({"items": []}),  # review-requested
            _mock_urlopen({"items": []}),  # assigned issues
            _mock_urlopen([self._commit()]),  # commits
        ]):
            events, action_items = conn.sync()
        commit_events = [ev for ev in events if "abc1234" in ev.title]
        assert len(commit_events) == 1

    def test_invalid_repo_format_skipped(self):
        conn = _make_connector({"github_token": "tok", "github_username": "alice", "repos": ["not-valid"]})
        with patch("urllib.request.urlopen", side_effect=[
            _mock_urlopen([]),
            _mock_urlopen({"items": []}),
            _mock_urlopen({"items": []}),
        ]):
            # Should not raise, just skip invalid repos
            events, action_items = conn.sync()
        assert isinstance(events, list)

    def test_sync_raises_when_invalid_config(self):
        conn = GitHubConnector(_make_source({}))
        with pytest.raises(ConnectorError, match="github_token"):
            conn.sync()
