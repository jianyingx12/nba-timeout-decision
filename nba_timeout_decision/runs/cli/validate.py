"""Command-line interface for scoring-run validation."""

import argparse
import json
from pathlib import Path
from typing import Sequence

from ..validation.workflow import validate_partitions, write_report
from ..workflows.batch import GAME_TYPES


def parse_args(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate materialized scoring runs.")
    parser.add_argument("--first-season", type=int, default=2013)
    parser.add_argument("--last-season", type=int, default=2025)
    parser.add_argument(
        "--game-types", nargs="+", choices=GAME_TYPES, default=list(GAME_TYPES)
    )
    parser.add_argument(
        "--possession-root", type=Path, default=Path("data/derived/possessions")
    )
    parser.add_argument(
        "--possession-manifest",
        type=Path,
        default=Path("data/derived/possession-manifest.json"),
    )
    parser.add_argument("--catalog-root", type=Path, default=Path("data/catalog"))
    parser.add_argument(
        "--output-root", type=Path, default=Path("data/derived/runs")
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/derived/run-manifest.json"),
    )
    parser.add_argument(
        "--report", type=Path, default=Path("data/reports/run-validation.json")
    )
    parser.add_argument("--skip-recompute", action="store_true")
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
    report = validate_partitions(
        seasons=list(range(args.first_season, args.last_season + 1)),
        game_types=args.game_types,
        possession_root=args.possession_root,
        possession_manifest=args.possession_manifest,
        catalog_root=args.catalog_root,
        output_root=args.output_root,
        manifest_path=args.manifest,
        recompute=not args.skip_recompute,
    )
    write_report(args.report, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
