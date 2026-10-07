"""Command-line interface for scoring-run detection."""

import argparse
import json
from pathlib import Path
from typing import Sequence

from ..workflows.batch import GAME_TYPES, detect_partitions


def parse_args(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Detect scoring runs from reconstructed NBA possessions."
    )
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
    parser.add_argument("--refresh", action="store_true")
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
    result = detect_partitions(
        seasons=list(range(args.first_season, args.last_season + 1)),
        game_types=args.game_types,
        possession_root=args.possession_root,
        possession_manifest=args.possession_manifest,
        catalog_root=args.catalog_root,
        output_root=args.output_root,
        manifest_path=args.manifest,
        refresh=args.refresh,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
