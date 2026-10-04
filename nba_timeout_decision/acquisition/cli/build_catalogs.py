"""Command-line interface for full catalog generation."""

import argparse
import json
from pathlib import Path

from ..catalog.batch import build_catalogs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build game catalogs from cached partitions.")
    parser.add_argument("--first-season", type=int, default=2013)
    parser.add_argument("--last-season", type=int, default=2025)
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--output-root", type=Path, default=Path("data/catalog"))
    args = parser.parse_args()
    if not 2013 <= args.first_season <= 2025:
        parser.error("--first-season must be between 2013 and 2025")
    if not 2013 <= args.last_season <= 2025:
        parser.error("--last-season must be between 2013 and 2025")
    if args.first_season > args.last_season:
        parser.error("--first-season cannot be greater than --last-season")
    return args


def main() -> None:
    args = parse_args()
    result = build_catalogs(
        seasons=list(range(args.first_season, args.last_season + 1)),
        raw_root=args.raw_root,
        output_root=args.output_root,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
