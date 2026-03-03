"""Export system for advanced intelligence reports.

Supports JSON, HTML (with print CSS), and pseudo-PDF (HTML + print media).

Usage::

    from src.advanced.export import export_report
    path = export_report(report_dict, fmt="json", output_path="/tmp/report.json")
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _default_output_path(fmt: str, label: str = "beacon_report") -> Path:
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    return Path.home() / ".cache" / "beacon" / "exports" / f"{label}_{ts}.{fmt}"


def _to_html(report: dict[str, Any], title: str = "Beacon Report") -> str:
    """Render a report dict to a minimal HTML document."""
    generated = report.get("generated_at", datetime.now(tz=timezone.utc).isoformat())

    def _render_value(value: Any, depth: int = 0) -> str:
        indent = "  " * depth
        if isinstance(value, dict):
            rows = "".join(
                f"<tr><th>{k}</th><td>{_render_value(v, depth + 1)}</td></tr>"
                for k, v in value.items()
            )
            return f"<table class='nested'>{rows}</table>"
        if isinstance(value, list):
            if not value:
                return "<em>—</em>"
            items = "".join(f"<li>{_render_value(item, depth + 1)}</li>" for item in value)
            return f"<ul>{items}</ul>"
        if value is None:
            return "<em>null</em>"
        return str(value)

    sections = "".join(
        f"<section><h2>{key}</h2>{_render_value(val)}</section>"
        for key, val in report.items()
        if key != "generated_at"
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      max-width: 900px; margin: 0 auto; padding: 2rem 1rem;
      color: #1a1a1a; background: #fff;
    }}
    h1 {{ font-size: 1.5rem; border-bottom: 2px solid #3b82f6; padding-bottom: .5rem; }}
    h2 {{ font-size: 1.1rem; color: #3b82f6; margin-top: 2rem; }}
    table {{ border-collapse: collapse; width: 100%; margin: .5rem 0; }}
    table.nested {{ margin: 0; }}
    th, td {{ text-align: left; padding: .3rem .6rem; border: 1px solid #e5e7eb; }}
    th {{ background: #f9fafb; font-weight: 600; width: 35%; }}
    ul {{ margin: 0; padding-left: 1.2rem; }}
    li {{ margin: .2rem 0; }}
    .meta {{ color: #6b7280; font-size: .85rem; margin-top: .5rem; }}
    @media print {{
      body {{ max-width: 100%; padding: 1cm; }}
      h2 {{ page-break-before: auto; }}
      section {{ page-break-inside: avoid; }}
    }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <p class="meta">Generated: {generated}</p>
  {sections}
</body>
</html>"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def export_report(
    report: dict[str, Any],
    fmt: str = "json",
    output_path: str | Path | None = None,
    title: str = "Beacon Report",
) -> Path:
    """Export *report* to a file in the requested format.

    Args:
        report: Any dict returned by the advanced intelligence modules.
        fmt: Output format — ``"json"``, ``"html"``, or ``"pdf"``.
             ``"pdf"`` produces an HTML file styled for print/PDF export.
        output_path: Destination file path.  If *None*, an automatic path
                     under ``~/.cache/beacon/exports/`` is used.
        title: Document title (used in HTML output).

    Returns:
        The :class:`~pathlib.Path` of the written file.

    Raises:
        ValueError: If *fmt* is not one of ``json``, ``html``, ``pdf``.
    """
    fmt = fmt.lower()
    if fmt not in ("json", "html", "pdf"):
        raise ValueError(f"Unsupported format {fmt!r}. Choose json, html, or pdf.")

    # pdf is HTML with print-optimised CSS — same file extension .html
    file_fmt = "html" if fmt == "pdf" else fmt

    if output_path is None:
        output_path = _default_output_path(file_fmt)

    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "json":
        dest.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    else:
        dest.write_text(_to_html(report, title=title), encoding="utf-8")

    return dest
