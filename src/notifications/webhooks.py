"""Webhook sender for Beacon notifications.

Sends formatted payloads to Slack (Block Kit) or Discord (embeds)
using only stdlib urllib.request — no third-party dependencies.

Config in beacon.toml:

    [notifications.webhook]
    url = "https://hooks.slack.com/services/..."
    platform = "slack"   # "slack" | "discord"

    # Or for Discord:
    [notifications.webhook]
    url = "https://discord.com/api/webhooks/..."
    platform = "discord"
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


class WebhookError(Exception):
    """Raised when a webhook delivery fails."""


@dataclass
class WebhookConfig:
    """Webhook endpoint configuration."""

    url: str
    platform: str = "slack"  # "slack" | "discord"


def send_webhook(
    config: WebhookConfig | dict[str, Any],
    title: str,
    body: str,
    items: list[dict[str, Any]] | None = None,
) -> None:
    """Send a notification via Slack or Discord webhook.

    Args:
        config: WebhookConfig or raw beacon.toml notifications.webhook dict.
        title: Notification title / header text.
        body: Main notification body text.
        items: Optional list of item dicts to include as structured fields.

    Raises:
        WebhookError: if the HTTP request fails.
    """
    if isinstance(config, dict):
        config = WebhookConfig(
            url=config.get("url", ""),
            platform=config.get("platform", "slack"),
        )
    if not config.url:
        raise WebhookError("Webhook URL is not configured.")

    if config.platform == "discord":
        payload = _discord_payload(title, body, items)
    else:
        payload = _slack_payload(title, body, items)

    _post_json(config.url, payload)


def _post_json(url: str, payload: dict[str, Any]) -> None:
    """POST a JSON payload to *url*."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
            if status not in (200, 204):
                body = resp.read(256).decode("utf-8", errors="replace")
                raise WebhookError(f"Webhook returned HTTP {status}: {body}")
    except urllib.error.HTTPError as exc:
        raise WebhookError(f"Webhook HTTP error {exc.code}: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise WebhookError(f"Webhook connection error: {exc.reason}") from exc


# ---------------------------------------------------------------------------
# Slack Block Kit formatting
# ---------------------------------------------------------------------------

def _slack_payload(
    title: str,
    body: str,
    items: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Build a Slack Block Kit payload."""
    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": title[:150], "emoji": True},
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": body[:3000]},
        },
    ]

    if items:
        blocks.append({"type": "divider"})
        # Slack sections can have at most 10 fields
        fields: list[dict[str, str]] = []
        for item in items[:10]:
            item_title = item.get("title", "(no title)")
            priority = item.get("priority", "")
            src = item.get("source_type", "")
            label_parts = []
            if priority:
                label_parts.append(priority.upper())
            if src:
                label_parts.append(src)
            label = f"[{', '.join(label_parts)}] " if label_parts else ""
            fields.append({"type": "mrkdwn", "text": f"*{label}{item_title[:75]}*"})

        blocks.append({"type": "section", "fields": fields})

        if len(items) > 10:
            blocks.append({
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"_…and {len(items) - 10} more items_"}
                ],
            })

    return {"blocks": blocks}


# ---------------------------------------------------------------------------
# Discord embed formatting
# ---------------------------------------------------------------------------

_PRIORITY_COLORS = {
    "urgent": 0xC0392B,   # red
    "high":   0xE67E22,   # orange
    "medium": 0x2980B9,   # blue
    "low":    0x7F8C8D,   # grey
}
_DEFAULT_COLOR = 0x4A90D9  # beacon blue


def _discord_payload(
    title: str,
    body: str,
    items: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Build a Discord webhook payload with an embed."""
    embed: dict[str, Any] = {
        "title": title[:256],
        "description": body[:4096],
        "color": _DEFAULT_COLOR,
    }

    if items:
        fields: list[dict[str, Any]] = []
        for item in items[:25]:  # Discord max 25 fields
            item_title = item.get("title", "(no title)")
            priority = item.get("priority", "medium").lower()
            src = item.get("source_type", "")
            value_parts = []
            if src:
                value_parts.append(f"source: {src}")
            url = item.get("url", "")
            if url:
                value_parts.append(f"[link]({url})")
            fields.append({
                "name": f"[{priority.upper()}] {item_title[:100]}",
                "value": " · ".join(value_parts) or "\u200b",  # zero-width space if empty
                "inline": True,
            })
        embed["fields"] = fields

        # Use highest-priority item's color
        top_priority = "medium"
        for item in items:
            p = item.get("priority", "medium").lower()
            if _PRIORITY_COLORS.get(p, 0) > _PRIORITY_COLORS.get(top_priority, 0):
                top_priority = p
        embed["color"] = _PRIORITY_COLORS.get(top_priority, _DEFAULT_COLOR)

    return {"embeds": [embed]}


def load_webhook_config(raw_config: dict[str, Any]) -> WebhookConfig | None:
    """Parse webhook config from raw beacon.toml dict. Returns None if not configured."""
    notifications = raw_config.get("notifications", {})
    wh = notifications.get("webhook", {})
    url = wh.get("url", "")
    if not url:
        return None
    return WebhookConfig(url=url, platform=wh.get("platform", "slack"))
