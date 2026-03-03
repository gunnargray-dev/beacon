"""Tests for src/notifications — rules, digest, webhooks, email_digest, silence."""

from __future__ import annotations

import json
import smtplib
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.notifications.rules import (
    MatchedNotification,
    Rule,
    RuleEngine,
    load_rules_from_config,
)
from src.notifications.digest import Digest, compile_digest, load_digest_config
from src.notifications.silence import (
    SilenceConfig,
    SilenceWindow,
    is_silenced,
    load_silence_config,
)
from src.notifications.webhooks import (
    WebhookConfig,
    WebhookError,
    load_webhook_config,
    send_webhook,
    _slack_payload,
    _discord_payload,
)
from src.notifications.email_digest import (
    EmailConfig,
    EmailError,
    load_email_config,
    send_email_digest,
    _build_subject,
    _parse_email_config,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ev(title="Test Event", source_type="github", occurred_at=None):
    return {
        "id": "e1",
        "title": title,
        "source_type": source_type,
        "occurred_at": occurred_at or "2026-03-03T10:00:00",
        "summary": "A test event",
        "url": "https://example.com",
        "metadata": {},
    }


def _ai(title="Test Action", source_type="github", priority="medium", completed=False):
    return {
        "id": "a1",
        "title": title,
        "source_type": source_type,
        "priority": priority,
        "completed": completed,
        "url": "https://example.com/action",
        "notes": "",
        "metadata": {},
    }


# ---------------------------------------------------------------------------
# Rules tests
# ---------------------------------------------------------------------------

class TestRule(unittest.TestCase):
    def test_match_event_no_conditions(self):
        rule = Rule(action="notify")
        assert rule.matches_event(_ev()) is True

    def test_match_event_source_type(self):
        rule = Rule(action="notify", source_type="github")
        assert rule.matches_event(_ev(source_type="github")) is True
        assert rule.matches_event(_ev(source_type="email")) is False

    def test_match_event_item_type_filter(self):
        rule = Rule(action="notify", item_type="action")
        assert rule.matches_event(_ev()) is False

    def test_match_action_no_conditions(self):
        rule = Rule(action="notify")
        assert rule.matches_action(_ai()) is True

    def test_match_action_source_type(self):
        rule = Rule(action="notify", source_type="email")
        assert rule.matches_action(_ai(source_type="email")) is True
        assert rule.matches_action(_ai(source_type="github")) is False

    def test_match_action_priority_min(self):
        rule = Rule(action="notify", priority_min="high")
        assert rule.matches_action(_ai(priority="urgent")) is True
        assert rule.matches_action(_ai(priority="high")) is True
        assert rule.matches_action(_ai(priority="medium")) is False
        assert rule.matches_action(_ai(priority="low")) is False

    def test_match_action_item_type_filter(self):
        rule = Rule(action="notify", item_type="event")
        assert rule.matches_action(_ai()) is False

    def test_priority_ordering(self):
        rule = Rule(action="notify", priority_min="medium")
        assert rule.matches_action(_ai(priority="medium")) is True
        assert rule.matches_action(_ai(priority="high")) is True
        assert rule.matches_action(_ai(priority="low")) is False


class TestRuleEngine(unittest.TestCase):
    def setUp(self):
        self.rules = [
            Rule(action="notify", source_type="github", item_type="action", priority_min="high"),
            Rule(action="digest", source_type="calendar"),
            Rule(action="silence", source_type="news"),
        ]
        self.engine = RuleEngine(self.rules)

    def test_evaluate_events(self):
        events = [_ev(source_type="calendar"), _ev(source_type="news")]
        results = self.engine.evaluate(events, [])
        assert len(results) == 2
        actions = {r.action for r in results}
        assert "digest" in actions
        assert "silence" in actions

    def test_evaluate_actions(self):
        ais = [
            _ai(source_type="github", priority="urgent"),
            _ai(source_type="github", priority="low"),
        ]
        results = self.engine.evaluate([], ais)
        # Only high/urgent github actions match rule 1; low priority github has no match
        assert len(results) == 1
        assert results[0].action == "notify"

    def test_first_rule_wins(self):
        # Both rules match; first wins
        engine = RuleEngine([
            Rule(action="notify"),
            Rule(action="digest"),
        ])
        results = engine.evaluate([_ev()], [])
        assert len(results) == 1
        assert results[0].action == "notify"

    def test_notify_items(self):
        events = [_ev(source_type="calendar")]
        ais = [_ai(source_type="github", priority="urgent")]
        notify = self.engine.notify_items(events, ais)
        assert all(n.action == "notify" for n in notify)

    def test_digest_items(self):
        events = [_ev(source_type="calendar")]
        digest = self.engine.digest_items(events, [])
        assert all(n.action == "digest" for n in digest)

    def test_silenced_items(self):
        events = [_ev(source_type="news")]
        silenced = self.engine.silenced_items(events, [])
        assert all(n.action == "silence" for n in silenced)

    def test_empty_inputs(self):
        assert self.engine.evaluate([], []) == []

    def test_item_type_on_result(self):
        results = self.engine.evaluate([_ev(source_type="calendar")], [])
        assert results[0].item_type == "event"


class TestLoadRulesFromConfig(unittest.TestCase):
    def test_load_empty(self):
        assert load_rules_from_config({}) == []

    def test_load_rules(self):
        raw = {
            "notifications": {
                "rules": [
                    {"name": "r1", "source_type": "github", "action": "notify"},
                    {"name": "r2", "action": "digest", "priority_min": "high"},
                ]
            }
        }
        rules = load_rules_from_config(raw)
        assert len(rules) == 2
        assert rules[0].source_type == "github"
        assert rules[0].action == "notify"
        assert rules[1].priority_min == "high"

    def test_default_action_is_notify(self):
        raw = {"notifications": {"rules": [{"name": "r"}]}}
        rules = load_rules_from_config(raw)
        assert rules[0].action == "notify"


# ---------------------------------------------------------------------------
# Silence tests
# ---------------------------------------------------------------------------

class TestSilenceWindow(unittest.TestCase):
    def test_normal_window(self):
        w = SilenceWindow(start_hour=9, end_hour=12)
        assert w.contains(datetime(2026, 3, 3, 9, 0)) is True
        assert w.contains(datetime(2026, 3, 3, 11, 59)) is True
        assert w.contains(datetime(2026, 3, 3, 12, 0)) is False
        assert w.contains(datetime(2026, 3, 3, 8, 59)) is False

    def test_overnight_window(self):
        w = SilenceWindow(start_hour=22, end_hour=7)
        assert w.contains(datetime(2026, 3, 3, 22, 0)) is True
        assert w.contains(datetime(2026, 3, 3, 23, 59)) is True
        assert w.contains(datetime(2026, 3, 3, 6, 59)) is True
        assert w.contains(datetime(2026, 3, 3, 7, 0)) is False
        assert w.contains(datetime(2026, 3, 3, 12, 0)) is False

    def test_day_filter(self):
        w = SilenceWindow(start_hour=9, end_hour=12, days=["mon", "tue"])
        # 2026-03-02 is a Monday (weekday=0)
        assert w.contains(datetime(2026, 3, 2, 10, 0)) is True
        # 2026-03-03 is a Tuesday (weekday=1)
        assert w.contains(datetime(2026, 3, 3, 10, 0)) is True
        # 2026-03-04 is a Wednesday (weekday=2)
        assert w.contains(datetime(2026, 3, 4, 10, 0)) is False

    def test_no_days_matches_all(self):
        w = SilenceWindow(start_hour=9, end_hour=12, days=[])
        for day in range(7):
            dt = datetime(2026, 3, 2 + day, 10, 0)
            assert w.contains(dt) is True


class TestSilenceConfig(unittest.TestCase):
    def test_disabled(self):
        cfg = SilenceConfig(enabled=False, windows=[
            SilenceWindow(start_hour=0, end_hour=23),
        ])
        assert cfg.is_silenced() is False

    def test_silenced(self):
        cfg = SilenceConfig(enabled=True, windows=[
            SilenceWindow(start_hour=0, end_hour=23),
        ])
        assert cfg.is_silenced(datetime(2026, 3, 3, 10, 0)) is True

    def test_not_silenced(self):
        cfg = SilenceConfig(enabled=True, windows=[
            SilenceWindow(start_hour=22, end_hour=23),
        ])
        assert cfg.is_silenced(datetime(2026, 3, 3, 10, 0)) is False

    def test_no_windows(self):
        cfg = SilenceConfig(enabled=True, windows=[])
        assert cfg.is_silenced() is False


class TestIsSilenced(unittest.TestCase):
    def test_none_config(self):
        assert is_silenced(None) is False

    def test_silence_config_object(self):
        cfg = SilenceConfig(enabled=True, windows=[SilenceWindow(start_hour=9, end_hour=17)])
        assert is_silenced(cfg, datetime(2026, 3, 3, 10, 0)) is True
        assert is_silenced(cfg, datetime(2026, 3, 3, 8, 0)) is False

    def test_raw_dict(self):
        raw = {
            "notifications": {
                "silence": {
                    "enabled": True,
                    "windows": [{"start_hour": 9, "end_hour": 17}],
                }
            }
        }
        assert is_silenced(raw, datetime(2026, 3, 3, 10, 0)) is True
        assert is_silenced(raw, datetime(2026, 3, 3, 20, 0)) is False


class TestLoadSilenceConfig(unittest.TestCase):
    def test_empty(self):
        cfg = load_silence_config({})
        assert cfg.enabled is True
        assert cfg.windows == []

    def test_parse(self):
        raw = {
            "notifications": {
                "silence": {
                    "enabled": False,
                    "windows": [
                        {"name": "focus", "start_hour": 9, "end_hour": 12, "days": ["mon"]},
                    ],
                }
            }
        }
        cfg = load_silence_config(raw)
        assert cfg.enabled is False
        assert len(cfg.windows) == 1
        assert cfg.windows[0].name == "focus"
        assert cfg.windows[0].start_hour == 9
        assert cfg.windows[0].days == ["mon"]


# ---------------------------------------------------------------------------
# Digest tests
# ---------------------------------------------------------------------------

class TestDigest(unittest.TestCase):
    def _make_digest(self):
        return Digest(
            generated_at=datetime(2026, 3, 3, 9, 0, tzinfo=timezone.utc),
            window="morning",
            events=[_ev()],
            action_items=[_ai()],
        )

    def test_as_text_contains_title(self):
        d = self._make_digest()
        text = d.as_text()
        assert "Beacon Digest" in text
        assert "morning" in text.lower()

    def test_as_text_events(self):
        d = self._make_digest()
        text = d.as_text()
        assert "EVENTS" in text
        assert "Test Event" in text

    def test_as_text_action_items(self):
        d = self._make_digest()
        text = d.as_text()
        assert "ACTION ITEMS" in text
        assert "Test Action" in text

    def test_as_text_empty(self):
        d = Digest(
            generated_at=datetime(2026, 3, 3, 9, 0),
            window="all",
            events=[],
            action_items=[],
        )
        assert "Nothing to report" in d.as_text()

    def test_as_html_doctype(self):
        d = self._make_digest()
        html = d.as_html()
        assert "<!DOCTYPE html>" in html
        assert "<html>" in html

    def test_as_html_title(self):
        d = self._make_digest()
        html = d.as_html()
        assert "Beacon Digest" in html

    def test_as_html_events(self):
        d = self._make_digest()
        html = d.as_html()
        assert "Test Event" in html

    def test_as_html_actions(self):
        d = self._make_digest()
        html = d.as_html()
        assert "Test Action" in html

    def test_as_html_empty(self):
        d = Digest(generated_at=datetime(2026, 3, 3), window="all")
        assert "Nothing to report" in d.as_html()

    def test_completed_actions_excluded(self):
        d = Digest(
            generated_at=datetime(2026, 3, 3),
            window="all",
            events=[],
            action_items=[_ai(completed=True)],
        )
        # completed items are shown in HTML with strikethrough class
        html = d.as_html()
        assert "completed" in html


class TestCompileDigest(unittest.TestCase):
    def test_compiles_events_and_actions(self):
        events = [_ev(), _ev(title="Event 2")]
        ais = [_ai(), _ai(title="Action 2")]
        d = compile_digest(events, ais, window="all")
        assert len(d.events) == 2
        assert len(d.action_items) == 2

    def test_excludes_completed_actions(self):
        ais = [_ai(completed=False), _ai(title="Done", completed=True)]
        d = compile_digest([], ais, window="all")
        assert len(d.action_items) == 1
        assert d.action_items[0]["title"] == "Test Action"

    def test_max_events(self):
        events = [_ev() for _ in range(30)]
        d = compile_digest(events, [], max_events=5)
        assert len(d.events) == 5

    def test_max_actions(self):
        ais = [_ai() for _ in range(20)]
        d = compile_digest([], ais, max_actions=3)
        assert len(d.action_items) == 3

    def test_morning_window(self):
        now = datetime(2026, 3, 3, 9, 0, tzinfo=timezone.utc)
        events = [
            _ev(occurred_at="2026-03-03T08:00:00"),  # morning
            _ev(occurred_at="2026-03-03T15:00:00"),  # afternoon
        ]
        d = compile_digest(events, [], window="morning", now=now)
        assert len(d.events) == 1
        assert d.events[0]["occurred_at"] == "2026-03-03T08:00:00"

    def test_evening_window(self):
        now = datetime(2026, 3, 3, 18, 0, tzinfo=timezone.utc)
        events = [
            _ev(occurred_at="2026-03-03T08:00:00"),  # morning
            _ev(occurred_at="2026-03-03T15:00:00"),  # afternoon
        ]
        d = compile_digest(events, [], window="evening", now=now)
        assert len(d.events) == 1
        assert d.events[0]["occurred_at"] == "2026-03-03T15:00:00"

    def test_all_window(self):
        events = [
            _ev(occurred_at="2026-03-03T08:00:00"),
            _ev(occurred_at="2026-03-03T15:00:00"),
        ]
        d = compile_digest(events, [], window="all")
        assert len(d.events) == 2

    def test_window_stored(self):
        d = compile_digest([], [], window="evening")
        assert d.window == "evening"


# ---------------------------------------------------------------------------
# Webhook tests
# ---------------------------------------------------------------------------

class TestSlackPayload(unittest.TestCase):
    def test_has_blocks(self):
        p = _slack_payload("Title", "Body", None)
        assert "blocks" in p
        assert len(p["blocks"]) >= 2

    def test_header_text(self):
        p = _slack_payload("My Title", "Body", None)
        header = p["blocks"][0]
        assert header["type"] == "header"
        assert "My Title" in header["text"]["text"]

    def test_with_items(self):
        items = [_ai(), _ev()]
        p = _slack_payload("Title", "Body", items)
        types = [b["type"] for b in p["blocks"]]
        assert "section" in types

    def test_overflow_items(self):
        items = [_ai() for _ in range(15)]
        p = _slack_payload("T", "B", items)
        # Should have context block mentioning overflow
        block_types = [b["type"] for b in p["blocks"]]
        assert "context" in block_types


class TestDiscordPayload(unittest.TestCase):
    def test_has_embeds(self):
        p = _discord_payload("Title", "Body", None)
        assert "embeds" in p
        assert len(p["embeds"]) == 1

    def test_embed_title(self):
        p = _discord_payload("My Title", "Body", None)
        assert p["embeds"][0]["title"] == "My Title"

    def test_embed_description(self):
        p = _discord_payload("T", "My Body", None)
        assert p["embeds"][0]["description"] == "My Body"

    def test_with_items(self):
        items = [_ai(priority="urgent"), _ai()]
        p = _discord_payload("T", "B", items)
        embed = p["embeds"][0]
        assert "fields" in embed

    def test_urgent_color(self):
        items = [_ai(priority="urgent")]
        p = _discord_payload("T", "B", items)
        assert p["embeds"][0]["color"] == 0xC0392B  # red


class TestWebhookConfig(unittest.TestCase):
    def test_defaults(self):
        cfg = WebhookConfig(url="https://example.com/hook")
        assert cfg.platform == "slack"

    def test_discord(self):
        cfg = WebhookConfig(url="https://discord.com/hook", platform="discord")
        assert cfg.platform == "discord"


class TestLoadWebhookConfig(unittest.TestCase):
    def test_empty(self):
        assert load_webhook_config({}) is None

    def test_configured(self):
        raw = {"notifications": {"webhook": {"url": "https://example.com", "platform": "discord"}}}
        cfg = load_webhook_config(raw)
        assert cfg is not None
        assert cfg.url == "https://example.com"
        assert cfg.platform == "discord"

    def test_no_url(self):
        raw = {"notifications": {"webhook": {"platform": "slack"}}}
        assert load_webhook_config(raw) is None


class TestSendWebhook(unittest.TestCase):
    @patch("src.notifications.webhooks.urllib.request.urlopen")
    def test_sends_slack(self, mock_urlopen):
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=cm)
        cm.__exit__ = MagicMock(return_value=False)
        cm.status = 200
        mock_urlopen.return_value = cm

        cfg = WebhookConfig(url="https://hooks.slack.com/test", platform="slack")
        send_webhook(cfg, "Title", "Body", [_ai()])
        mock_urlopen.assert_called_once()

    @patch("src.notifications.webhooks.urllib.request.urlopen")
    def test_sends_discord(self, mock_urlopen):
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=cm)
        cm.__exit__ = MagicMock(return_value=False)
        cm.status = 204
        mock_urlopen.return_value = cm

        cfg = WebhookConfig(url="https://discord.com/hook", platform="discord")
        send_webhook(cfg, "Title", "Body", None)
        mock_urlopen.assert_called_once()

    @patch("src.notifications.webhooks.urllib.request.urlopen")
    def test_http_error_raises(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="u", code=500, msg="Error", hdrs={}, fp=None
        )
        cfg = WebhookConfig(url="https://example.com", platform="slack")
        with self.assertRaises(WebhookError):
            send_webhook(cfg, "T", "B", None)

    def test_no_url_raises(self):
        cfg = WebhookConfig(url="", platform="slack")
        with self.assertRaises(WebhookError):
            send_webhook(cfg, "T", "B", None)

    @patch("src.notifications.webhooks.urllib.request.urlopen")
    def test_raw_dict_config(self, mock_urlopen):
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=cm)
        cm.__exit__ = MagicMock(return_value=False)
        cm.status = 200
        mock_urlopen.return_value = cm

        raw = {"url": "https://example.com", "platform": "slack"}
        send_webhook(raw, "T", "B", None)
        mock_urlopen.assert_called_once()


# ---------------------------------------------------------------------------
# Email digest tests
# ---------------------------------------------------------------------------

class TestEmailConfig(unittest.TestCase):
    def test_defaults(self):
        cfg = EmailConfig(
            smtp_host="smtp.example.com",
            from_addr="from@example.com",
            to_addr="to@example.com",
        )
        assert cfg.smtp_port == 587
        assert cfg.use_tls is True
        assert cfg.use_ssl is False
        assert cfg.subject_prefix == "[Beacon]"

    def test_parse_from_dict(self):
        raw = {
            "smtp_host": "smtp.test.com",
            "smtp_port": 465,
            "from_addr": "a@test.com",
            "to_addr": "b@test.com",
            "use_ssl": True,
            "use_tls": False,
            "subject_prefix": "[Test]",
        }
        cfg = _parse_email_config(raw)
        assert cfg.smtp_host == "smtp.test.com"
        assert cfg.smtp_port == 465
        assert cfg.use_ssl is True
        assert cfg.use_tls is False
        assert cfg.subject_prefix == "[Test]"


class TestBuildSubject(unittest.TestCase):
    def test_subject(self):
        digest = Digest(
            generated_at=datetime(2026, 3, 3, 9, 0),
            window="morning",
            events=[_ev()],
            action_items=[_ai()],
        )
        subject = _build_subject(digest, "[Beacon]")
        assert "[Beacon]" in subject
        assert "2026-03-03" in subject
        assert "Morning" in subject
        assert "1 event" in subject
        assert "1 action" in subject

    def test_plural(self):
        digest = Digest(
            generated_at=datetime(2026, 3, 3),
            window="all",
            events=[_ev(), _ev()],
            action_items=[_ai(), _ai(), _ai()],
        )
        subject = _build_subject(digest, "[Beacon]")
        assert "2 events" in subject
        assert "3 actions" in subject


class TestLoadEmailConfig(unittest.TestCase):
    def test_empty(self):
        assert load_email_config({}) is None

    def test_configured(self):
        raw = {
            "notifications": {
                "email": {
                    "smtp_host": "smtp.example.com",
                    "to_addr": "to@example.com",
                    "from_addr": "from@example.com",
                }
            }
        }
        cfg = load_email_config(raw)
        assert cfg is not None
        assert cfg.smtp_host == "smtp.example.com"


class TestSendEmailDigest(unittest.TestCase):
    def _make_digest(self):
        return Digest(
            generated_at=datetime(2026, 3, 3, 9, 0),
            window="morning",
            events=[_ev()],
            action_items=[_ai()],
        )

    def _make_config(self):
        return EmailConfig(
            smtp_host="smtp.example.com",
            from_addr="from@example.com",
            to_addr="to@example.com",
        )

    @patch("smtplib.SMTP")
    def test_sends_tls(self, mock_smtp_cls):
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        send_email_digest(self._make_digest(), self._make_config())
        mock_smtp_cls.assert_called_once_with("smtp.example.com", 587, timeout=30)

    @patch("smtplib.SMTP_SSL")
    def test_sends_ssl(self, mock_smtp_cls):
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        cfg = EmailConfig(
            smtp_host="smtp.example.com",
            from_addr="f@e.com",
            to_addr="t@e.com",
            smtp_port=465,
            use_ssl=True,
            use_tls=False,
        )
        send_email_digest(self._make_digest(), cfg)
        mock_smtp_cls.assert_called_once_with("smtp.example.com", 465, timeout=30)

    @patch("smtplib.SMTP")
    def test_smtp_error_raises_email_error(self, mock_smtp_cls):
        mock_smtp_cls.side_effect = smtplib.SMTPException("connect fail")
        cfg = self._make_config()
        with self.assertRaises(EmailError):
            send_email_digest(self._make_digest(), cfg)

    @patch("smtplib.SMTP")
    def test_accepts_raw_dict_config(self, mock_smtp_cls):
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        raw = {
            "smtp_host": "smtp.example.com",
            "from_addr": "f@e.com",
            "to_addr": "t@e.com",
        }
        send_email_digest(self._make_digest(), raw)
        mock_smtp_cls.assert_called_once()

    @patch("smtplib.SMTP")
    def test_login_called_when_username_set(self, mock_smtp_cls):
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        cfg = EmailConfig(
            smtp_host="smtp.example.com",
            from_addr="f@e.com",
            to_addr="t@e.com",
            username="user",
            password="pass",
        )
        send_email_digest(self._make_digest(), cfg)
        mock_smtp.login.assert_called_once_with("user", "pass")


# ---------------------------------------------------------------------------
# Integration: __init__ exports
# ---------------------------------------------------------------------------

class TestPackageExports(unittest.TestCase):
    def test_public_exports(self):
        from src.notifications import (
            Rule,
            RuleEngine,
            load_rules_from_config,
            Digest,
            compile_digest,
            WebhookConfig,
            send_webhook,
            EmailConfig,
            send_email_digest,
            SilenceWindow,
            is_silenced,
        )
        assert Rule is not None
        assert RuleEngine is not None


if __name__ == "__main__":
    unittest.main()
