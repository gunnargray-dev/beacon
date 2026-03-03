"""Beacon advanced intelligence modules.

This package provides higher-order analysis on top of the core sync cache:

- retrospective  — weekly activity summary with trend comparison
- meeting_prep   — structured prep brief for upcoming calendar events
- relationships  — interaction frequency and dormant contact detection
- time_audit     — time categorisation and meeting-overload detection
- trends         — rolling-average anomaly detection
- export         — JSON / HTML / PDF export helpers
- api            — FastAPI router wired into src.web.server
"""

from src.advanced.retrospective import generate_retrospective
from src.advanced.meeting_prep import generate_meeting_prep
from src.advanced.relationships import RelationshipTracker
from src.advanced.time_audit import generate_time_audit
from src.advanced.trends import detect_trends
from src.advanced.export import export_report

__all__ = [
    "generate_retrospective",
    "generate_meeting_prep",
    "RelationshipTracker",
    "generate_time_audit",
    "detect_trends",
    "export_report",
]
