"""Command-line interface for possession output validation."""

import argparse
import json
from pathlib import Path
from typing import Sequence

from ..workflows.batch import GAME_TYPES
from ..workflows.validation import validate_possessions, write_validation_report


def parse_args(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate reconstructed NBA possession partitions."
    )
    parser.add_argument("--first-season", type=int, default=2013)
    parser.add_argument("--last-season", type=int, default=2025)
    parser.add_argument(
        "--game-types", nargs="+", choices=GAME_TYPES, default=list(GAME_TYPES)
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/derived/possession-manifest.json"),
    )
    parser.add_argument(
        "--normalization-manifest",
        type=Path,
        default=Path("data/normalized/manifest.json"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("data/reports/possession-validation.json"),
    )
    args = parser.parse_args(arguments)
    if not 2013 <= args.first_season <= 2025:
        parser.error("--first-season must be between 2013 and 2025")
    if not 2013 <= args.last_season <= 2025:
        parser.error("--last-season must be between 2013 and 2025")
    if args.first_season > args.last_season:
        parser.error("--first-season cannot be greater than --last-season")
    return args


def main() -> None:
    args = parse_args()
    report = validate_possessions(
        manifest_path=args.manifest,
        normalization_manifest=args.normalization_manifest,
        seasons=list(range(args.first_season, args.last_season + 1)),
        game_types=args.game_types,
    )
    write_validation_report(args.report, report)
    summary = {name: value for name, value in report.items() if name != "partition_results"}
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not report["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
