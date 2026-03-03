"""Beacon CLI -- your personal ops agent from the terminal."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.config import ConfigError, find_config_file, load_config, write_default_config

VERSION = "0.1.0"


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def cmd_status(args: argparse.Namespace) -> None:
    """Show connected sources, last sync time, and pending action items."""
    print(f"Beacon v{VERSION}")
    print()

    config_path = find_config_file(getattr(args, "config", None))
    if config_path is None:
        print("Status: No configuration file found.")
        print()
        print("  Run 'beacon init' to create a default config at ~/.config/beacon/beacon.toml")
        print("  or create ./beacon.toml in your project directory.")
        return

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print(f"Error loading config: {exc}")
        sys.exit(1)

    print(f"Config:  {config_path}")
    print(f"User:    {config.user.name} <{config.user.email}>")
    print(f"Timezone:{config.user.timezone}")
    print()

    sources = config.sources
    if not sources:
        print("Sources: None configured")
        print()
        print("  Add a [[sources]] block to your beacon.toml to connect a source.")
        return

    enabled = config.enabled_sources()
    print(f"Sources: {len(sources)} configured, {len(enabled)} enabled")
    print()
    for src in sources:
        status_icon = "+" if src.enabled else "-"
        print(f"  [{status_icon}] {src.name!s:<20} type={src.type}")


def cmd_init(args: argparse.Namespace) -> None:
    """Create a default beacon.toml config file."""
    target = getattr(args, "path", None)
    try:
        path = write_default_config(target)
        print(f"Created config at: {path}")
        print("Edit it to add your sources and credentials.")
    except ConfigError as exc:
        print(f"Error: {exc}")
        sys.exit(1)


def cmd_sources(args: argparse.Namespace) -> None:
    """List configured sources (foundation for future add/remove/test)."""
    config_path = find_config_file(getattr(args, "config", None))
    if config_path is None:
        print("No config file found. Run 'beacon init' first.")
        sys.exit(1)

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print(f"Error loading config: {exc}")
        sys.exit(1)

    if not config.sources:
        print("No sources configured.")
        return

    for src in config.sources:
        enabled_str = "enabled" if src.enabled else "disabled"
        print(f"  {src.name!s:<20} [{src.type}] {enabled_str}")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="beacon",
        description="Your personal ops agent -- unified briefings, action items, and smart notifications.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {VERSION}",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # status
    sub_status = subparsers.add_parser("status", help="Show connection status and pending items")
    sub_status.add_argument("--config", metavar="PATH", default=None, help="Path to beacon.toml")
    sub_status.set_defaults(func=cmd_status)

    # init
    sub_init = subparsers.add_parser("init", help="Create a default config file")
    sub_init.add_argument(
        "--path",
        metavar="PATH",
        default=None,
        help="Where to write the config (default: ~/.config/beacon/beacon.toml)",
    )
    sub_init.set_defaults(func=cmd_init)

    # sources
    sub_sources = subparsers.add_parser("sources", help="List configured sources")
    sub_sources.add_argument("--config", metavar="PATH", default=None, help="Path to beacon.toml")
    sub_sources.set_defaults(func=cmd_sources)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)
    args.func(args)


if __name__ == "__main__":
    main()
