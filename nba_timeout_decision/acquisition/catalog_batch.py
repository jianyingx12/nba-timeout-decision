"""Catalog generation across multiple seasons."""

from pathlib import Path

from .archive import SEASON_TYPES, catalog_path, local_path
from .catalog import add_play_by_play_counts, extract_games, write_catalog


def build_catalogs(
    *,
    seasons: list[int],
    raw_root: Path,
    output_root: Path,
) -> dict[str, object]:
    combined_rows: list[dict[str, object]] = []
    partition_results: list[dict[str, object]] = []
    seen_game_ids: set[str] = set()
    total_shot_rows = 0
    total_play_by_play_rows = 0

    for season in sorted(set(seasons)):
        for season_type in SEASON_TYPES:
            shotdetail = local_path(raw_root, "shotdetail", season, season_type)
            play_by_play = local_path(raw_root, "nbastatsv3", season, season_type)
            destination = catalog_path(output_root, season, season_type)

            rows, shot_rows = extract_games(shotdetail, season, season_type)
            play_by_play_rows = add_play_by_play_counts(
                rows, play_by_play, season, season_type
            )
            digest = write_catalog(rows, destination)

            game_ids = {str(row["game_id"]) for row in rows}
            duplicates = sorted(seen_game_ids & game_ids)
            if duplicates:
                raise ValueError(f"Duplicate game IDs across partitions: {duplicates[:5]}")
            seen_game_ids.update(game_ids)
            combined_rows.extend(rows)
            total_shot_rows += shot_rows
            total_play_by_play_rows += play_by_play_rows
            partition_results.append(
                {
                    "season": season,
                    "game_type": season_type,
                    "games": len(rows),
                    "shot_rows": shot_rows,
                    "play_by_play_rows": play_by_play_rows,
                    "path": str(destination),
                    "sha256": digest,
                }
            )

    combined_rows.sort(key=lambda row: (str(row["game_date"]), str(row["game_id"])))
    combined_path = output_root / "games.csv"
    combined_hash = write_catalog(combined_rows, combined_path)
    return {
        "partitions": len(partition_results),
        "games": len(combined_rows),
        "shot_rows": total_shot_rows,
        "play_by_play_rows": total_play_by_play_rows,
        "combined_path": str(combined_path),
        "combined_sha256": combined_hash,
        "partition_results": partition_results,
    }
