"""Command-line interface for game catalog extraction."""

import argparse
import json
from pathlib import Path

from .archive import SEASON_TYPES, catalog_path
from .catalog import extract_games, write_catalog


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a game catalog from one shot-detail partition."
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--season", required=True, type=int)
    parser.add_argument("--season-type", required=True, choices=SEASON_TYPES)
    parser.add_argument("--output-root", type=Path, default=Path("data/catalog"))
    args = parser.parse_args()

    if not 2013 <= args.season <= 2025:
        parser.error("--season must be between 2013 and 2025")
    if not args.input.is_file():
        parser.error(f"--input does not exist or is not a file: {args.input}")
    return args


def main() -> None:
    args = parse_args()
    destination = catalog_path(args.output_root, args.season, args.season_type)
    games, source_rows = extract_games(args.input, args.season, args.season_type)
    digest = write_catalog(games, destination)
    result = {
        "status": "created",
        "path": str(destination),
        "games": len(games),
        "source_rows": source_rows,
        "sha256": digest,
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
