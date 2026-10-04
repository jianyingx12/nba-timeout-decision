"""Command-line interface for partition normalization."""

import argparse
import json
from pathlib import Path

from ..workflows.batch import GAME_TYPES, normalize_partitions


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize cached NBA play-by-play partitions."
    )
    parser.add_argument("--first-season", type=int, default=2013)
    parser.add_argument("--last-season", type=int, default=2025)
    parser.add_argument(
        "--game-types", nargs="+", choices=GAME_TYPES, default=list(GAME_TYPES)
    )
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--catalog", type=Path, default=Path("data/catalog/games.csv"))
    parser.add_argument(
        "--output-root", type=Path, default=Path("data/normalized/events")
    )
    parser.add_argument(
        "--manifest", type=Path, default=Path("data/normalized/manifest.json")
    )
    parser.add_argument("--refresh", action="store_true")
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
    result = normalize_partitions(
        seasons=list(range(args.first_season, args.last_season + 1)),
        game_types=args.game_types,
        raw_root=args.raw_root,
        catalog=args.catalog,
        output_root=args.output_root,
        manifest_path=args.manifest,
        refresh=args.refresh,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
