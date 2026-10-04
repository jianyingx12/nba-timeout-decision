"""Command-line interface for multi-partition acquisition."""

import argparse
import json
from pathlib import Path

from ..download.archive import DATA_TYPES, SEASON_TYPES
from ..download.batch import acquire


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download multiple NBA archive partitions.")
    parser.add_argument("--seasons", nargs="+", required=True, type=int)
    parser.add_argument("--data-types", nargs="+", choices=DATA_TYPES, default=list(DATA_TYPES))
    parser.add_argument(
        "--season-types", nargs="+", choices=SEASON_TYPES, default=list(SEASON_TYPES)
    )
    parser.add_argument("--output-root", type=Path, default=Path("data/raw"))
    parser.add_argument(
        "--manifest", type=Path, default=Path("data/manifests/partitions.csv")
    )
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--attempts", type=int, default=4)
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    parser.add_argument("--interval-seconds", type=float, default=1.0)
    args = parser.parse_args()

    if any(not 2013 <= season <= 2025 for season in args.seasons):
        parser.error("every season must be between 2013 and 2025")
    if args.attempts < 1:
        parser.error("--attempts must be at least 1")
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")
    if args.interval_seconds < 0:
        parser.error("--interval-seconds cannot be negative")
    return args


def main() -> None:
    args = parse_args()
    summary = acquire(
        seasons=args.seasons,
        data_types=args.data_types,
        season_types=args.season_types,
        output_root=args.output_root,
        manifest_path=args.manifest,
        refresh=args.refresh,
        attempts=args.attempts,
        timeout_seconds=args.timeout_seconds,
        interval_seconds=args.interval_seconds,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    if summary["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
