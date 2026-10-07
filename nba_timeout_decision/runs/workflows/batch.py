"""Run scoring-run detection across possession partitions."""

from pathlib import Path
from typing import Callable

from .runner import MaterializedRuns, materialize_partition

GAME_TYPES = ("regular", "playoffs")


def detect_partitions(
    *,
    seasons: list[int],
    game_types: list[str],
    possession_root: Path,
    possession_manifest: Path,
    catalog_root: Path,
    output_root: Path,
    manifest_path: Path,
    refresh: bool = False,
    materialize: Callable[..., MaterializedRuns] = materialize_partition,
) -> dict[str, object]:
    requests = [
        (season, game_type)
        for season in sorted(set(seasons))
        for game_type in game_types
    ]
    results: list[dict[str, object]] = []
    for season, game_type in requests:
        source = possession_root / str(season) / f"{game_type}.parquet"
        try:
            result = materialize(
                source,
                possession_manifest=possession_manifest,
                catalog_root=catalog_root,
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
                "source_possessions": result.source_possession_count,
                "accepted_games": result.accepted_game_count,
                "rejected_games": result.rejected_game_count,
                "runs": result.run_count,
                "threshold_crossings": result.threshold_crossing_count,
                "sensitivity_signals": result.sensitivity_signal_count,
                "output_directory": result.paths.runs.parent.as_posix(),
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
            "source_possessions",
            "accepted_games",
            "rejected_games",
            "runs",
            "threshold_crossings",
            "sensitivity_signals",
        )
    }
    return {"requested": len(requests), **counts, **totals, "results": results}
