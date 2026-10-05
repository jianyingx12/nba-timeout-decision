"""Run possession reconstruction across normalized partitions."""

from pathlib import Path
from typing import Callable

from .runner import MaterializedPartition, materialize_partition

GAME_TYPES = ("regular", "playoffs")


def reconstruct_partitions(
    *,
    seasons: list[int],
    game_types: list[str],
    normalized_root: Path,
    normalization_manifest: Path,
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
        source = normalized_root / str(season) / f"{game_type}.parquet"
        try:
            result = materialize(
                source,
                normalization_manifest=normalization_manifest,
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
                "source_events": result.source_event_count,
                "possessions": result.possession_count,
                "accepted_games": result.accepted_game_count,
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
    totals = {
        field: sum(int(result[field]) for result in successful)
        for field in (
            "source_events",
            "possessions",
            "accepted_games",
            "rejected_games",
        )
    }
    return {"requested": len(requests), **counts, **totals, "results": results}
