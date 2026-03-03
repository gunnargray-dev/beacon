"""Tests for the Beacon CLI."""

import subprocess
import sys


def test_cli_help():
    result = subprocess.run(
        [sys.executable, "-m", "src.cli", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "beacon" in result.stdout.lower() or "personal ops" in result.stdout.lower()


def test_cli_status():
    result = subprocess.run(
        [sys.executable, "-m", "src.cli", "status"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Beacon" in result.stdout
