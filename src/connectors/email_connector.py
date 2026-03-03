"""Email connector -- fetches unread/flagged mail via IMAP (stdlib imaplib)."""

from __future__ import annotations

import email
import email.header
import imaplib
from collections import Counter
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from src.connectors.base import BaseConnector, ConnectorError, registry
from src.models import ActionItem, Event, Priority, Source, SourceType


def _decode_header_value(raw: str | bytes | None) -> str:
    """Decode an RFC-2047-encoded email header value to a plain string."""
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    parts = email.header.decode_header(raw)
    decoded_parts: list[str] = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded_parts.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded_parts.append(part)
    return "".join(decoded_parts).strip()


def _parse_date(date_str: str) -> datetime:
    """Parse an email Date header into a UTC-aware datetime."""
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.astimezone(timezone.utc)
    except Exception:
        return datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# Connector
# ---------------------------------------------------------------------------


@registry.register
class EmailConnector(BaseConnector):
    """Connector for IMAP email accounts."""

    connector_type = SourceType.EMAIL

    # Maximum messages to fetch per sync
    MAX_FETCH = 50

    def validate_config(self) -> bool:
        required = ("imap_host", "email_user", "email_password")
        return all(bool(self.get_config(k)) for k in required)

    def test_connection(self) -> bool:
        """Try to log in and immediately log out."""
        if not self.validate_config():
            return False
        try:
            imap = self._connect()
            imap.logout()
            return True
        except (ConnectorError, imaplib.IMAP4.error, OSError, Exception):
            return False

    def sync(self) -> tuple[list[Event], list[ActionItem]]:
        if not self.validate_config():
            raise ConnectorError("Email connector config is incomplete")

        imap = self._connect()
        try:
            return self._fetch_data(imap)
        finally:
            try:
                imap.logout()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _connect(self) -> imaplib.IMAP4_SSL:
        host = self.get_config("imap_host")
        port = int(self.get_config("imap_port", 993))
        user = self.get_config("email_user")
        password = self.get_config("email_password")

        try:
            imap = imaplib.IMAP4_SSL(host, port)
            imap.login(user, password)
            return imap
        except imaplib.IMAP4.error as exc:
            raise ConnectorError(f"IMAP login failed for {user}@{host}: {exc}") from exc
        except OSError as exc:
            raise ConnectorError(f"Cannot connect to IMAP server {host}:{port}: {exc}") from exc

    def _fetch_data(self, imap: imaplib.IMAP4_SSL) -> tuple[list[Event], list[ActionItem]]:
        mailbox = self.get_config("mailbox", "INBOX")
        imap.select(mailbox, readonly=True)

        events: list[Event] = []
        action_items: list[ActionItem] = []
        sender_counts: Counter[str] = Counter()

        # --- Unread messages ---
        _status, unread_ids_data = imap.search(None, "UNSEEN")
        unread_ids: list[str] = (
            unread_ids_data[0].decode().split() if unread_ids_data and unread_ids_data[0] else []
        )
        recent_unread = unread_ids[-self.MAX_FETCH :]

        for msg_id in recent_unread:
            msg = self._fetch_message(imap, msg_id)
            if msg is None:
                continue
            ev, sender = self._message_to_event(msg, flagged=False)
            events.append(ev)
            if sender:
                sender_counts[sender] += 1

        # --- Flagged/starred messages ---
        _status, flagged_ids_data = imap.search(None, "FLAGGED")
        flagged_ids: list[str] = (
            flagged_ids_data[0].decode().split() if flagged_ids_data and flagged_ids_data[0] else []
        )
        recent_flagged = flagged_ids[-self.MAX_FETCH :]

        for msg_id in recent_flagged:
            msg = self._fetch_message(imap, msg_id)
            if msg is None:
                continue
            ev, sender = self._message_to_event(msg, flagged=True)
            # Convert flagged mails directly to action items
            subject = ev.title
            action_items.append(
                ActionItem(
                    title=f"Flagged email: {subject}",
                    source_id=self.source.id,
                    source_type=SourceType.EMAIL,
                    priority=Priority.HIGH,
                    due_at=ev.occurred_at,
                    url=ev.url,
                    notes=f"From: {ev.metadata.get('from', '')}",
                    metadata=ev.metadata,
                )
            )
            if sender:
                sender_counts[sender] += 1

        # Summary action item for high-volume senders
        for sender, count in sender_counts.most_common(3):
            if count >= 3:
                action_items.append(
                    ActionItem(
                        title=f"Frequent sender: {sender} ({count} messages)",
                        source_id=self.source.id,
                        source_type=SourceType.EMAIL,
                        priority=Priority.LOW,
                        notes=f"{sender} sent {count} messages recently",
                    )
                )

        # Unread count summary event
        if unread_ids:
            events.insert(
                0,
                Event(
                    title=f"{len(unread_ids)} unread message(s) in {mailbox}",
                    source_id=self.source.id,
                    source_type=SourceType.EMAIL,
                    occurred_at=datetime.now(tz=timezone.utc),
                    summary=f"Unread count: {len(unread_ids)}",
                    metadata={"unread_count": len(unread_ids), "mailbox": mailbox},
                ),
            )

        return events, action_items

    def _fetch_message(self, imap: imaplib.IMAP4_SSL, msg_id: str) -> email.message.Message | None:
        try:
            _status, data = imap.fetch(msg_id, "(RFC822.HEADER)")
            if not data or data[0] is None:
                return None
            raw = data[0][1] if isinstance(data[0], tuple) else data[0]
            if isinstance(raw, bytes):
                return email.message_from_bytes(raw)
            return email.message_from_string(raw)
        except Exception:
            return None

    def _message_to_event(
        self, msg: email.message.Message, flagged: bool
    ) -> tuple[Event, str]:
        subject = _decode_header_value(msg.get("Subject", "(No subject)"))
        from_raw = _decode_header_value(msg.get("From", ""))
        date_raw = msg.get("Date", "")
        msg_id = msg.get("Message-ID", "")

        occurred = _parse_date(date_raw) if date_raw else datetime.now(tz=timezone.utc)
        sender = from_raw.split("<")[-1].rstrip(">").strip() if "<" in from_raw else from_raw

        meta: dict[str, Any] = {
            "from": from_raw,
            "message_id": msg_id,
            "flagged": flagged,
            "mailbox": self.get_config("mailbox", "INBOX"),
        }

        event = Event(
            title=subject,
            source_id=self.source.id,
            source_type=SourceType.EMAIL,
            occurred_at=occurred,
            summary=f"From: {from_raw}",
            metadata=meta,
        )
        return event, sender
