import argparse
from unittest.mock import patch

import pytest

from src.cli import build_parser, main


def _base_daemon_args(**overrides):
    ns = argparse.Namespace(
        command="sync",
        config="/tmp/beacon.toml",
        daemon=True,
        interval=300,
        max_runs=1,
        once=False,
        stop_on_error=False,
        show_times=False,
    )
    for k, v in overrides.items():
        setattr(ns, k, v)
    return ns


def test_parser_accepts_sync_daemon_flags():
    parser = build_parser()
    args = parser.parse_args(["sync", "--daemon", "--interval", "10", "--max-runs", "2", "--show-times"])
    assert args.command == "sync"
    assert args.daemon is True
    assert args.interval == 10
    assert args.max_runs == 2
    assert args.show_times is True


def test_main_routes_sync_daemon_to_daemon_handler():
    with patch("src.cli.build_parser") as bp:
        bp.return_value.parse_args.return_value = _base_daemon_args(max_runs=1)

        with patch("src.cli.cmd_sync_daemon") as daemon:
            main()
            assert daemon.call_count == 1


@pytest.mark.parametrize(
    "interval",
    [0, 1, 4],
)
def test_sync_daemon_rejects_too_small_interval(interval):
    from src.cli import cmd_sync_daemon

    args = _base_daemon_args(interval=interval, config="/tmp/beacon.toml")
    with pytest.raises(SystemExit) as exc:
        cmd_sync_daemon(args)
    assert exc.value.code == 2


def test_sync_daemon_rejects_invalid_max_runs():
    from src.cli import cmd_sync_daemon

    args = _base_daemon_args(max_runs=0, config="/tmp/beacon.toml")
    with pytest.raises(SystemExit) as exc:
        cmd_sync_daemon(args)
    assert exc.value.code == 2
