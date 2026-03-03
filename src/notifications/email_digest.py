"""HTML email digest sender for Beacon notifications.

Sends the compiled Digest as an HTML email using stdlib smtplib — no
third-party dependencies.

Config in beacon.toml:

    [notifications.email]
    smtp_host = "smtp.example.com"
    smtp_port = 587
    from_addr = "beacon@example.com"
    to_addr = "you@example.com"
    username = "beacon@example.com"   # optional
    password = "secret"               # optional
    use_tls = true                    # STARTTLS (port 587 default)
    use_ssl = false                   # direct TLS (port 465)
    subject_prefix = "[Beacon]"       # optional
"""

from __future__ import annotations

import smtplib
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from src.notifications.digest import Digest


class EmailError(Exception):
    """Raised when email delivery fails."""


@dataclass
class EmailConfig:
    """SMTP email configuration for digest delivery."""

    smtp_host: str
    from_addr: str
    to_addr: str
    smtp_port: int = 587
    username: str = ""
    password: str = ""
    use_tls: bool = True
    use_ssl: bool = False
    subject_prefix: str = "[Beacon]"


def send_email_digest(
    digest: Digest,
    config: EmailConfig | dict[str, Any],
) -> None:
    """Send a Digest as an HTML email.

    Args:
        digest: The compiled Digest object.
        config: EmailConfig or raw beacon.toml notifications.email dict.

    Raises:
        EmailError: if SMTP delivery fails.
    """
    if isinstance(config, dict):
        config = _parse_email_config(config)

    subject = _build_subject(digest, config.subject_prefix)
    html_body = digest.as_html()
    text_body = digest.as_text()

    msg = _build_message(
        from_addr=config.from_addr,
        to_addr=config.to_addr,
        subject=subject,
        text_body=text_body,
        html_body=html_body,
    )

    _send_message(msg, config)


def _build_subject(digest: Digest, prefix: str) -> str:
    ts = digest.generated_at.strftime("%Y-%m-%d")
    window = digest.window.title()
    n_events = len(digest.events)
    n_actions = len(digest.action_items)
    summary = f"{n_events} event{'s' if n_events != 1 else ''}, {n_actions} action{'s' if n_actions != 1 else ''}"
    return f"{prefix} {window} Digest {ts} \u2014 {summary}"


def _build_message(
    from_addr: str,
    to_addr: str,
    subject: str,
    text_body: str,
    html_body: str,
) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    return msg


def _send_message(msg: MIMEMultipart, config: EmailConfig) -> None:
    """Connect to SMTP and deliver the message."""
    try:
        if config.use_ssl:
            smtp_cls = smtplib.SMTP_SSL
            with smtp_cls(config.smtp_host, config.smtp_port, timeout=30) as smtp:
                if config.username:
                    smtp.login(config.username, config.password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=30) as smtp:
                smtp.ehlo()
                if config.use_tls:
                    smtp.starttls()
                    smtp.ehlo()
                if config.username:
                    smtp.login(config.username, config.password)
                smtp.send_message(msg)
    except smtplib.SMTPException as exc:
        raise EmailError(f"SMTP error: {exc}") from exc
    except OSError as exc:
        raise EmailError(f"Connection error: {exc}") from exc


def _parse_email_config(raw: dict[str, Any]) -> EmailConfig:
    """Parse EmailConfig from a raw beacon.toml dict (notifications.email section)."""
    return EmailConfig(
        smtp_host=raw.get("smtp_host", "localhost"),
        smtp_port=int(raw.get("smtp_port", 587)),
        from_addr=raw.get("from_addr", ""),
        to_addr=raw.get("to_addr", ""),
        username=raw.get("username", ""),
        password=raw.get("password", ""),
        use_tls=bool(raw.get("use_tls", True)),
        use_ssl=bool(raw.get("use_ssl", False)),
        subject_prefix=raw.get("subject_prefix", "[Beacon]"),
    )


def load_email_config(raw_config: dict[str, Any]) -> EmailConfig | None:
    """Parse email config from raw beacon.toml dict. Returns None if not configured."""
    notifications = raw_config.get("notifications", {})
    email_raw = notifications.get("email", {})
    if not email_raw.get("smtp_host") and not email_raw.get("to_addr"):
        return None
    return _parse_email_config(email_raw)
