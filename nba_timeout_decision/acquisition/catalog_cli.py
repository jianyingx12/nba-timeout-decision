"""Command-line interface for game catalog extraction."""

import argparse
import json
from pathlib import Path

from .archive import SEASON_TYPES, catalog_path
from .catalog import add_play_by_play_counts, extract_games, write_catalog


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a game catalog from one shot-detail partition."
    )
    parser.add_argument("--shot-detail", required=True, type=Path)
    parser.add_argument("--play-by-play", required=True, type=Path)
    parser.add_argument("--season", required=True, type=int)
    parser.add_argument("--season-type", required=True, choices=SEASON_TYPES)
    parser.add_argument("--output-root", type=Path, default=Path("data/catalog"))
    args = parser.parse_args()

    if not 2013 <= args.season <= 2025:
        parser.error("--season must be between 2013 and 2025")
    if not args.shot_detail.is_file():
        parser.error(f"--shot-detail does not exist or is not a file: {args.shot_detail}")
    if not args.play_by_play.is_file():
        parser.error(f"--play-by-play does not exist or is not a file: {args.play_by_play}")
    return args


def main() -> None:
    args = parse_args()
    destination = catalog_path(args.output_root, args.season, args.season_type)
    games, shot_detail_rows = extract_games(
        args.shot_detail, args.season, args.season_type
    )
    play_by_play_rows = add_play_by_play_counts(
        games, args.play_by_play, args.season, args.season_type
    )
    digest = write_catalog(games, destination)
    result = {
        "status": "created",
        "path": str(destination),
        "games": len(games),
        "shot_detail_rows": shot_detail_rows,
        "play_by_play_rows": play_by_play_rows,
        "sha256": digest,
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
