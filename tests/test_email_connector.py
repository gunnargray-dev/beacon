"""Tests for the Email connector (IMAP via imaplib)."""

from __future__ import annotations

import email as _email_mod
from datetime import datetime, timezone
from email.mime.text import MIMEText
from unittest.mock import MagicMock, patch, call

import pytest

from src.connectors.base import ConnectorError
from src.connectors.email_connector import (
    EmailConnector,
    _decode_header_value,
    _parse_date,
)
from src.models import Priority, Source, SourceType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_source(config: dict | None = None) -> Source:
    return Source(
        name="test-email",
        source_type=SourceType.EMAIL,
        config=config or {},
    )


def _full_config() -> dict:
    return {
        "imap_host": "imap.example.com",
        "imap_port": 993,
        "email_user": "user@example.com",
        "email_password": "secret",
        "mailbox": "INBOX",
    }


def _make_raw_header(subject: str, from_: str, date: str = "Mon, 01 Jan 2024 12:00:00 +0000") -> bytes:
    msg = MIMEText("body")
    msg["Subject"] = subject
    msg["From"] = from_
    msg["Date"] = date
    msg["Message-ID"] = "<test-id@example.com>"
    return msg.as_bytes()


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestDecodeHeaderValue:
    def test_plain_string(self):
        assert _decode_header_value("Hello World") == "Hello World"

    def test_none_returns_empty(self):
        assert _decode_header_value(None) == ""

    def test_encoded_utf8(self):
        # RFC 2047 encoded
        encoded = "=?utf-8?b?SGVsbG8gV29ybGQ=?="
        result = _decode_header_value(encoded)
        assert "Hello World" in result

    def test_bytes_input(self):
        result = _decode_header_value(b"plain bytes")
        assert "plain bytes" in result


class TestParseDateEmail:
    def test_valid_rfc2822(self):
        dt = _parse_date("Mon, 01 Jan 2024 12:00:00 +0000")
        assert dt.year == 2024
        assert dt.tzinfo is not None

    def test_invalid_returns_now(self):
        before = datetime.now(tz=timezone.utc)
        dt = _parse_date("not-a-date")
        after = datetime.now(tz=timezone.utc)
        assert before <= dt <= after


# ---------------------------------------------------------------------------
# EmailConnector.validate_config
# ---------------------------------------------------------------------------


class TestEmailConnectorValidateConfig:
    def test_valid_with_all_required(self):
        conn = EmailConnector(_make_source(_full_config()))
        assert conn.validate_config() is True

    def test_missing_host(self):
        cfg = _full_config()
        del cfg["imap_host"]
        conn = EmailConnector(_make_source(cfg))
        assert conn.validate_config() is False

    def test_missing_user(self):
        cfg = _full_config()
        del cfg["email_user"]
        conn = EmailConnector(_make_source(cfg))
        assert conn.validate_config() is False

    def test_missing_password(self):
        cfg = _full_config()
        del cfg["email_password"]
        conn = EmailConnector(_make_source(cfg))
        assert conn.validate_config() is False

    def test_empty_config_invalid(self):
        conn = EmailConnector(_make_source())
        assert conn.validate_config() is False


# ---------------------------------------------------------------------------
# EmailConnector.test_connection
# ---------------------------------------------------------------------------


class TestEmailConnectorTestConnection:
    def test_returns_false_if_invalid_config(self):
        conn = EmailConnector(_make_source())
        assert conn.test_connection() is False

    def test_returns_true_on_successful_login(self):
        mock_imap = MagicMock()
        with patch("imaplib.IMAP4_SSL", return_value=mock_imap):
            conn = EmailConnector(_make_source(_full_config()))
            result = conn.test_connection()
        assert result is True
        mock_imap.login.assert_called_once()
        mock_imap.logout.assert_called_once()

    def test_returns_false_on_login_failure(self):
        mock_imap = MagicMock()
        mock_imap.login.side_effect = Exception("auth failed")
        with patch("imaplib.IMAP4_SSL", return_value=mock_imap):
            conn = EmailConnector(_make_source(_full_config()))
            result = conn.test_connection()
        assert result is False

    def test_returns_false_on_connection_error(self):
        with patch("imaplib.IMAP4_SSL", side_effect=OSError("refused")):
            conn = EmailConnector(_make_source(_full_config()))
            result = conn.test_connection()
        assert result is False


# ---------------------------------------------------------------------------
# EmailConnector.sync
# ---------------------------------------------------------------------------


class TestEmailConnectorSync:
    def _make_imap_mock(
        self,
        unread_ids: list[str] | None = None,
        flagged_ids: list[str] | None = None,
        headers: list[bytes] | None = None,
    ) -> MagicMock:
        """Build a mock IMAP4_SSL that returns controllable data."""
        mock_imap = MagicMock()
        mock_imap.select.return_value = ("OK", [b"5"])

        unread_bytes = b" ".join(s.encode() for s in (unread_ids or []))
        flagged_bytes = b" ".join(s.encode() for s in (flagged_ids or []))

        def search_side_effect(_charset, criterion):
            if criterion == "UNSEEN":
                return ("OK", [unread_bytes])
            if criterion == "FLAGGED":
                return ("OK", [flagged_bytes])
            return ("OK", [b""])

        mock_imap.search.side_effect = search_side_effect

        # Build fetch return value from provided headers
        fetch_data = []
        for raw in (headers or []):
            fetch_data.append((b"1 (RFC822.HEADER ...)", raw))
        mock_imap.fetch.return_value = ("OK", fetch_data)
        return mock_imap

    def test_sync_raises_if_invalid_config(self):
        conn = EmailConnector(_make_source())
        with pytest.raises(ConnectorError, match="incomplete"):
            conn.sync()

    def test_sync_with_no_messages_returns_empty(self):
        mock_imap = self._make_imap_mock(unread_ids=[], flagged_ids=[])
        with patch("imaplib.IMAP4_SSL", return_value=mock_imap):
            conn = EmailConnector(_make_source(_full_config()))
            events, actions = conn.sync()
        # No unread messages -> no unread summary event
        assert events == []
        assert actions == []

    def test_sync_with_unread_creates_events(self):
        raw_hdr = _make_raw_header("Re: Project Update", "alice@example.com")
        mock_imap = self._make_imap_mock(
            unread_ids=["1"], headers=[raw_hdr]
        )
        with patch("imaplib.IMAP4_SSL", return_value=mock_imap):
            conn = EmailConnector(_make_source(_full_config()))
            events, actions = conn.sync()
        # Should have unread summary + individual message event(s)
        assert len(events) >= 1
        # At least one event should mention unread
        titles = [ev.title for ev in events]
        assert any("unread" in t.lower() for t in titles)

    def test_sync_with_flagged_creates_action_items(self):
        raw_hdr = _make_raw_header("Important!", "boss@example.com")
        mock_imap = self._make_imap_mock(
            unread_ids=[], flagged_ids=["2"], headers=[raw_hdr]
        )
        with patch("imaplib.IMAP4_SSL", return_value=mock_imap):
            conn = EmailConnector(_make_source(_full_config()))
            events, actions = conn.sync()
        assert len(actions) >= 1
        assert all(a.source_type == SourceType.EMAIL for a in actions)
        assert all(a.priority == Priority.HIGH for a in actions)

    def test_sync_logs_out_even_on_error(self):
        mock_imap = MagicMock()
        mock_imap.select.side_effect = Exception("select failed")
        with patch("imaplib.IMAP4_SSL", return_value=mock_imap):
            conn = EmailConnector(_make_source(_full_config()))
            with pytest.raises(Exception):
                conn.sync()
        mock_imap.logout.assert_called()

    def test_connector_type(self):
        assert EmailConnector.connector_type == SourceType.EMAIL

    def test_source_id_on_events(self):
        raw_hdr = _make_raw_header("Hello", "x@x.com")
        mock_imap = self._make_imap_mock(unread_ids=["1"], headers=[raw_hdr])
        with patch("imaplib.IMAP4_SSL", return_value=mock_imap):
            src = _make_source(_full_config())
            conn = EmailConnector(src)
            events, _ = conn.sync()
        assert all(ev.source_id == src.id for ev in events)
