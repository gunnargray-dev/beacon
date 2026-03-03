"""GitHub connector -- fetches notifications, PRs, issues, and commits via REST API."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from src.connectors.base import BaseConnector, ConnectorError, registry
from src.models import ActionItem, Event, Priority, Source, SourceType

_GITHUB_API = "https://api.github.com"


def _parse_dt(value: str) -> datetime:
    """Parse a GitHub ISO-8601 timestamp into a UTC-aware datetime."""
    if not value:
        return datetime.now(tz=timezone.utc)
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            continue
    return datetime.now(tz=timezone.utc)


def _gh_request(path: str, token: str, params: dict[str, str] | None = None) -> Any:
    """Make an authenticated GitHub API request and return the parsed JSON."""
    url = f"{_GITHUB_API}{path}"
    if params:
        from urllib.parse import urlencode
        url = f"{url}?{urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Beacon/0.1",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ConnectorError(f"GitHub API error {exc.code} for {path}: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise ConnectorError(f"GitHub network error for {path}: {exc}") from exc


# ---------------------------------------------------------------------------
# Connector
# ---------------------------------------------------------------------------


@registry.register
class GitHubConnector(BaseConnector):
    """Connector for GitHub: notifications, review requests, assigned issues, commits."""

    connector_type = SourceType.GITHUB

    def validate_config(self) -> bool:
        return bool(self.get_config("github_token"))

    def test_connection(self) -> bool:
        if not self.validate_config():
            return False
        try:
            _gh_request("/user", self.get_config("github_token"))
            return True
        except ConnectorError:
            return False

    def sync(self) -> tuple[list[Event], list[ActionItem]]:
        if not self.validate_config():
            raise ConnectorError("GitHub connector requires 'github_token' in config")

        token: str = self.get_config("github_token")
        username: str = self.get_config("github_username", "")
        repos: list[str] = self.get_config("repos", [])

        events: list[Event] = []
        action_items: list[ActionItem] = []

        # --- Notifications ---
        try:
            notifications = _gh_request("/notifications", token, {"all": "false", "per_page": "50"})
            if isinstance(notifications, list):
                for notif in notifications:
                    subject = notif.get("subject", {})
                    title = subject.get("title", "(No title)")
                    notif_type = subject.get("type", "")
                    repo = notif.get("repository", {}).get("full_name", "")
                    url = notif.get("subject", {}).get("url", "")
                    # Convert API URL to HTML URL
                    html_url = url.replace("https://api.github.com/repos/", "https://github.com/")
                    html_url = html_url.replace("/pulls/", "/pull/")
                    updated_at = notif.get("updated_at", "")
                    reason = notif.get("reason", "")

                    events.append(
                        Event(
                            title=f"[{repo}] {title}",
                            source_id=self.source.id,
                            source_type=SourceType.GITHUB,
                            occurred_at=_parse_dt(updated_at),
                            summary=f"{notif_type} notification (reason: {reason})",
                            url=html_url,
                            metadata={
                                "type": "notification",
                                "repo": repo,
                                "subject_type": notif_type,
                                "reason": reason,
                            },
                        )
                    )

                    # Review requests and mentions become action items
                    if reason in ("review_requested", "assign", "mention", "team_mention"):
                        priority = Priority.HIGH if reason == "review_requested" else Priority.MEDIUM
                        action_items.append(
                            ActionItem(
                                title=f"[{repo}] {title}",
                                source_id=self.source.id,
                                source_type=SourceType.GITHUB,
                                priority=priority,
                                url=html_url,
                                notes=f"GitHub notification reason: {reason}",
                                metadata={
                                    "type": "notification",
                                    "repo": repo,
                                    "reason": reason,
                                },
                            )
                        )
        except ConnectorError:
            pass  # skip if notifications fail, try other endpoints

        # --- Review-requested PRs (search) ---
        if username:
            try:
                query = f"is:open is:pr review-requested:{username}"
                result = _gh_request("/search/issues", token, {"q": query, "per_page": "30"})
                for item in result.get("items", []):
                    repo_url = item.get("repository_url", "")
                    repo_name = repo_url.replace("https://api.github.com/repos/", "")
                    title = item.get("title", "(No title)")
                    html_url = item.get("html_url", "")
                    created_at = item.get("created_at", "")
                    action_items.append(
                        ActionItem(
                            title=f"[{repo_name}] Review requested: {title}",
                            source_id=self.source.id,
                            source_type=SourceType.GITHUB,
                            priority=Priority.HIGH,
                            url=html_url,
                            notes=f"PR opened by {item.get('user', {}).get('login', '?')}",
                            metadata={
                                "type": "review_requested",
                                "repo": repo_name,
                                "pr_number": item.get("number"),
                            },
                        )
                    )
                    events.append(
                        Event(
                            title=f"[{repo_name}] PR review requested: {title}",
                            source_id=self.source.id,
                            source_type=SourceType.GITHUB,
                            occurred_at=_parse_dt(created_at),
                            summary=f"Review requested on PR #{item.get('number')}",
                            url=html_url,
                            metadata={"type": "review_requested", "repo": repo_name},
                        )
                    )
            except ConnectorError:
                pass

        # --- Assigned issues ---
        if username:
            try:
                query = f"is:open is:issue assignee:{username}"
                result = _gh_request("/search/issues", token, {"q": query, "per_page": "30"})
                for item in result.get("items", []):
                    repo_url = item.get("repository_url", "")
                    repo_name = repo_url.replace("https://api.github.com/repos/", "")
                    title = item.get("title", "(No title)")
                    html_url = item.get("html_url", "")
                    created_at = item.get("created_at", "")
                    due_label = next(
                        (
                            lbl["name"]
                            for lbl in item.get("labels", [])
                            if "due" in lbl["name"].lower() or "deadline" in lbl["name"].lower()
                        ),
                        None,
                    )
                    action_items.append(
                        ActionItem(
                            title=f"[{repo_name}] Issue #{item.get('number')}: {title}",
                            source_id=self.source.id,
                            source_type=SourceType.GITHUB,
                            priority=Priority.MEDIUM,
                            url=html_url,
                            notes=f"Assigned issue. Labels: {due_label or 'none'}",
                            metadata={
                                "type": "assigned_issue",
                                "repo": repo_name,
                                "issue_number": item.get("number"),
                            },
                        )
                    )
                    events.append(
                        Event(
                            title=f"[{repo_name}] Issue #{item.get('number')}: {title}",
                            source_id=self.source.id,
                            source_type=SourceType.GITHUB,
                            occurred_at=_parse_dt(created_at),
                            summary=item.get("body", "")[:300] if item.get("body") else "",
                            url=html_url,
                            metadata={"type": "assigned_issue", "repo": repo_name},
                        )
                    )
            except ConnectorError:
                pass

        # --- Recent commits for configured repos ---
        for repo_full in repos:
            repo_full = repo_full.strip()
            if not repo_full or "/" not in repo_full:
                continue
            try:
                commits = _gh_request(
                    f"/repos/{repo_full}/commits",
                    token,
                    {"per_page": "10"},
                )
                if isinstance(commits, list):
                    for commit in commits:
                        sha = commit.get("sha", "")[:7]
                        msg = (commit.get("commit", {}).get("message", "") or "").splitlines()[0]
                        author = (
                            commit.get("commit", {}).get("author", {}).get("name", "?")
                        )
                        date_str = (
                            commit.get("commit", {}).get("author", {}).get("date", "")
                        )
                        html_url = commit.get("html_url", "")
                        events.append(
                            Event(
                                title=f"[{repo_full}] {sha}: {msg}",
                                source_id=self.source.id,
                                source_type=SourceType.GITHUB,
                                occurred_at=_parse_dt(date_str),
                                summary=f"Commit by {author}",
                                url=html_url,
                                metadata={
                                    "type": "commit",
                                    "repo": repo_full,
                                    "sha": sha,
                                    "author": author,
                                },
                            )
                        )
            except ConnectorError:
                pass  # skip repo on error

        return events, action_items
