"""Test configuration for Beacon.

Tests invoke the CLI using `python -m src.cli` from temporary working
directories. Ensure the repository root is available on PYTHONPATH.
"""

from __future__ import annotations

import os
from pathlib import Path


def pytest_configure() -> None:
    root = str(Path(__file__).resolve().parents[1])
    existing = os.environ.get("PYTHONPATH", "")
    paths = [p for p in existing.split(os.pathsep) if p]
    if root not in paths:
        paths.insert(0, root)
    os.environ["PYTHONPATH"] = os.pathsep.join(paths)
