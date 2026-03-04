"""Config validation (lint) helpers for beacon.toml.

This module is intentionally conservative: it catches common foot-guns without
preventing advanced/unknown configuration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.config import BeaconConfig, ConfigError, find_config_file, load_config


@dataclass(frozen=True)
class ConfigLintIssue:
    level: str  # "error" | "warn"
    message: str


@dataclass(frozen=True)
class ConfigLintReport:
    path: Path | None
    issues: list[ConfigLintIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(i.level == "error" for i in self.issues)

    def as_text(self) -> str:
        lines: list[str] = []
        if self.path:
            lines.append(f"Config: {self.path}")
        else:
            lines.append("Config: (not found)")
        if not self.issues:
            lines.append("OK: no issues found")
            return "\n".join(lines)
        lines.append("")
        for issue in self.issues:
            tag = "ERROR" if issue.level == "error" else "WARN"
            lines.append(f"{tag}: {issue.message}")
        return "\n".join(lines)


def _is_nonempty_str(v: Any) -> bool:
    return isinstance(v, str) and v.strip() != ""


def lint_config(path: str | Path | None = None) -> ConfigLintReport:
    """Lint a Beacon config file.

    - If path is None, attempts to locate config file.
    - If config file is missing, reports an error.
    """

    config_path = find_config_file(path)
    if config_path is None:
        return ConfigLintReport(
            path=None,
            issues=[ConfigLintIssue("error", "No beacon.toml found. Run 'beacon init' first.")],
        )

    issues: list[ConfigLintIssue] = []

    try:
        cfg = load_config(config_path)
    except ConfigError as exc:
        return ConfigLintReport(path=config_path, issues=[ConfigLintIssue("error", str(exc))])

    issues.extend(_lint_user(cfg))
    issues.extend(_lint_sources(cfg))

    return ConfigLintReport(path=config_path, issues=issues)


def _lint_user(cfg: BeaconConfig) -> list[ConfigLintIssue]:
    issues: list[ConfigLintIssue] = []

    if not _is_nonempty_str(cfg.user.name):
        issues.append(ConfigLintIssue("warn", "[user].name is empty"))

    if not _is_nonempty_str(cfg.user.email):
        issues.append(ConfigLintIssue("warn", "[user].email is empty"))

    if not _is_nonempty_str(cfg.user.timezone):
        issues.append(ConfigLintIssue("warn", "[user].timezone is empty"))

    return issues


def _lint_sources(cfg: BeaconConfig) -> list[ConfigLintIssue]:
    issues: list[ConfigLintIssue] = []

    if not cfg.sources:
        issues.append(ConfigLintIssue("warn", "No [[sources]] configured"))
        return issues

    seen_names: set[str] = set()
    for i, src in enumerate(cfg.sources, 1):
        prefix = f"sources[{i}]"

        if not _is_nonempty_str(src.name):
            issues.append(ConfigLintIssue("error", f"{prefix}.name is required"))
        elif src.name in seen_names:
            issues.append(ConfigLintIssue("error", f"Duplicate source name {src.name!r}"))
        else:
            seen_names.add(src.name)

        if not _is_nonempty_str(src.type):
            issues.append(ConfigLintIssue("error", f"{prefix}.type is required"))

        # Connector-specific common checks (non-blocking warnings)
        stype = (src.type or "").strip().lower()
        if stype == "github":
            if "token" not in src.config or not _is_nonempty_str(src.config.get("token")):
                issues.append(ConfigLintIssue("warn", f"{prefix} (github) missing token"))
        elif stype == "news":
            feeds = src.config.get("feeds")
            if feeds is None:
                issues.append(ConfigLintIssue("warn", f"{prefix} (news) missing feeds=[...]"))
            elif not isinstance(feeds, list) or not feeds:
                issues.append(ConfigLintIssue("warn", f"{prefix} (news) feeds should be a non-empty list"))
        elif stype == "weather":
            if "location" not in src.config or not _is_nonempty_str(src.config.get("location")):
                issues.append(ConfigLintIssue("warn", f"{prefix} (weather) missing location"))
        elif stype == "calendar":
            if "calendar_id" not in src.config or not _is_nonempty_str(src.config.get("calendar_id")):
                issues.append(ConfigLintIssue("warn", f"{prefix} (calendar) missing calendar_id"))

    return issues
