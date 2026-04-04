"""Packaged launch entry points."""

from __future__ import annotations

import argparse
import sys

from .cli import main as cli_main
from .desktop import launch_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch CCFII Display Share.")
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Run the original command-line sharing flow for troubleshooting.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cli:
        cli_main()
        return 0
    launch_app()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
