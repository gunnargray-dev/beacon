"""Beacon CLI -- your personal ops agent from the terminal."""

import argparse
import sys


def cmd_status(args):
    """Show connected sources, last sync time, and pending action items."""
    print("Beacon v0.1.0")
    print("Status: No sources configured yet.")
    print("Run 'beacon sources --add' to connect your first source.")


def main():
    parser = argparse.ArgumentParser(
        prog="beacon",
        description="Your personal ops agent -- unified briefings, action items, and smart notifications.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # status
    sub_status = subparsers.add_parser("status", help="Show connection status and pending items")
    sub_status.set_defaults(func=cmd_status)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
