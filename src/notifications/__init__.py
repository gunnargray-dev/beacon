"""Beacon notifications package — rules, digest, webhooks, email, and smart silence."""

from __future__ import annotations

from .digest import Digest, compile_digest
from .email_digest import EmailConfig, send_email_digest
from .rules import Rule, RuleEngine, load_rules_from_config
from .silence import SilenceConfig, SilenceWindow, is_silenced, load_silence_config
from .webhooks import WebhookConfig, send_webhook

__all__ = [
    "Rule",
    "RuleEngine",
    "load_rules_from_config",
    "Digest",
    "compile_digest",
    "WebhookConfig",
    "send_webhook",
    "EmailConfig",
    "send_email_digest",
    "SilenceConfig",
    "SilenceWindow",
    "is_silenced",
    "load_silence_config",
]
