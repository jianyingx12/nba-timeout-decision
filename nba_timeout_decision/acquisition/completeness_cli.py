"""Command-line interface for completeness reports."""

import argparse
import json
from pathlib import Path

from .completeness import build_report, write_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check cached acquisition completeness.")
    parser.add_argument(
        "--manifest", type=Path, default=Path("data/manifests/partitions.csv")
    )
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument(
        "--output", type=Path, default=Path("data/reports/completeness.json")
    )
    parser.add_argument("--first-season", type=int, default=2013)
    parser.add_argument("--last-season", type=int, default=2025)
    args = parser.parse_args()
    if args.first_season > args.last_season:
        parser.error("--first-season cannot be greater than --last-season")
    return args


def main() -> None:
    args = parse_args()
    report = build_report(
        manifest_path=args.manifest,
        raw_root=args.raw_root,
        project_root=args.project_root,
        first_season=args.first_season,
        last_season=args.last_season,
    )
    write_report(report, args.output)
    print(json.dumps(report["summary"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
