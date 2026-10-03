"""Command-line interface for archive downloads."""

import argparse
import json
from pathlib import Path

from .archive import DATA_TYPES, SEASON_TYPES
from .downloader import download


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download one NBA archive partition.")
    parser.add_argument("--data-type", required=True, choices=DATA_TYPES)
    parser.add_argument("--season", required=True, type=int)
    parser.add_argument("--season-type", required=True, choices=SEASON_TYPES)
    parser.add_argument("--output-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--attempts", type=int, default=4)
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    args = parser.parse_args()

    if not 2013 <= args.season <= 2025:
        parser.error("--season must be between 2013 and 2025")
    if args.attempts < 1:
        parser.error("--attempts must be at least 1")
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")
    return args


def main() -> None:
    args = parse_args()
    result = download(
        data_type=args.data_type,
        season=args.season,
        season_type=args.season_type,
        output_root=args.output_root,
        refresh=args.refresh,
        attempts=args.attempts,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
