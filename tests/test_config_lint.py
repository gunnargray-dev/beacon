from __future__ import annotations

from pathlib import Path

from src.config_lint import lint_config


def test_lint_config_missing_file_is_error(tmp_path: Path) -> None:
    report = lint_config(tmp_path / "does-not-exist.toml")
    assert not report.ok
    assert any(i.level == "error" for i in report.issues)


def test_lint_config_duplicate_source_names(tmp_path: Path) -> None:
    p = tmp_path / "beacon.toml"
    p.write_text(
        """
[user]
name = "x"
email = "x@example.com"
timezone = "UTC"

[[sources]]
name = "github"
type = "github"
token = "t"

[[sources]]
name = "github"
type = "weather"
location = "mpls"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    report = lint_config(p)
    assert not report.ok
    assert any("Duplicate" in i.message for i in report.issues)


def test_lint_config_warns_on_missing_user_email(tmp_path: Path) -> None:
    p = tmp_path / "beacon.toml"
    p.write_text(
        """
[user]
name = "x"
timezone = "UTC"

[[sources]]
name = "weather"
type = "weather"
location = "mpls"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    report = lint_config(p)
    assert report.ok
    assert any(i.level == "warn" for i in report.issues)
    assert any("email" in i.message for i in report.issues)
