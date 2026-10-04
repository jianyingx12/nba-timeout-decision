"""Command-line interface for normalized-data validation."""

import argparse
import json
from pathlib import Path

from ..workflows.validation import validate_normalization, write_validation_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate normalized NBA events.")
    parser.add_argument("--first-season", type=int, default=2013)
    parser.add_argument("--last-season", type=int, default=2025)
    parser.add_argument(
        "--manifest", type=Path, default=Path("data/normalized/manifest.json")
    )
    parser.add_argument("--catalog", type=Path, default=Path("data/catalog/games.csv"))
    parser.add_argument(
        "--report", type=Path, default=Path("data/reports/normalization.json")
    )
    args = parser.parse_args()
    if not 2013 <= args.first_season <= args.last_season <= 2025:
        parser.error("season range must be between 2013 and 2025")
    return args


def main() -> None:
    args = parse_args()
    report = validate_normalization(
        manifest_path=args.manifest,
        catalog_path=args.catalog,
        seasons=list(range(args.first_season, args.last_season + 1)),
    )
    write_validation_report(args.report, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
