"""Run normalization across cached play-by-play partitions."""

from pathlib import Path
from typing import Callable

from .runner import MaterializedPartition, materialize_partition

GAME_TYPES = ("regular", "playoffs")


def normalize_partitions(
    *,
    seasons: list[int],
    game_types: list[str],
    raw_root: Path,
    catalog: Path,
    output_root: Path,
    manifest_path: Path,
    refresh: bool = False,
    materialize: Callable[..., MaterializedPartition] = materialize_partition,
) -> dict[str, object]:
    requests = [
        (season, game_type)
        for season in sorted(set(seasons))
        for game_type in game_types
    ]
    results: list[dict[str, object]] = []

    for season, game_type in requests:
        source = raw_root / "nbastatsv3" / str(season) / f"{game_type}.parquet"
        try:
            result = materialize(
                source,
                catalog,
                raw_root=raw_root,
                output_root=output_root,
                manifest_path=manifest_path,
                season=season,
                game_type=game_type,
                refresh=refresh,
            )
        except Exception as error:
            results.append(
                {
                    "season": season,
                    "game_type": game_type,
                    "status": "failed",
                    "error": str(error),
                }
            )
            continue

        results.append(
            {
                "season": season,
                "game_type": game_type,
                "status": result.status,
                "source_rows": result.source_row_count,
                "normalized_rows": result.normalized_row_count,
                "rejected_games": result.rejected_game_count,
                "path": result.path.as_posix(),
                "sha256": result.output_sha256,
            }
        )

    counts = {
        status: sum(result["status"] == status for result in results)
        for status in ("written", "reused", "failed")
    }
    successful = [result for result in results if result["status"] != "failed"]
    return {
        "requested": len(requests),
        **counts,
        "source_rows": sum(int(result["source_rows"]) for result in successful),
        "normalized_rows": sum(
            int(result["normalized_rows"]) for result in successful
        ),
        "rejected_games": sum(
            int(result["rejected_games"]) for result in successful
        ),
        "results": results,
    }
