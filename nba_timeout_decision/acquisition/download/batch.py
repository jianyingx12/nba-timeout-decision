"""Acquisition of multiple archive partitions."""

import time
from pathlib import Path
from typing import Callable

from .downloader import DownloadError, download
from .manifest import failure_record, success_record, upsert


def acquire(
    *,
    seasons: list[int],
    data_types: list[str],
    season_types: list[str],
    output_root: Path,
    manifest_path: Path,
    refresh: bool,
    attempts: int,
    timeout_seconds: float,
    interval_seconds: float,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, object]:
    requests = [
        (data_type, season, season_type)
        for season in sorted(set(seasons))
        for season_type in season_types
        for data_type in data_types
    ]
    results: list[dict[str, object]] = []

    for index, (data_type, season, season_type) in enumerate(requests):
        made_remote_attempt = False
        try:
            result = download(
                data_type=data_type,
                season=season,
                season_type=season_type,
                output_root=output_root,
                refresh=refresh,
                attempts=attempts,
                timeout_seconds=timeout_seconds,
            )
            made_remote_attempt = int(result["attempt"]) > 0
            upsert(
                manifest_path,
                success_record(
                    data_type=data_type,
                    season=season,
                    season_type=season_type,
                    result=result,
                ),
            )
            results.append(
                {
                    "data_type": data_type,
                    "season": season,
                    "game_type": season_type,
                    "status": result["status"],
                }
            )
        except DownloadError as error:
            made_remote_attempt = True
            record = failure_record(
                data_type=data_type,
                season=season,
                season_type=season_type,
                output_root=output_root,
                attempts=error.attempts,
                http_status=error.http_status,
                error=str(error),
            )
            upsert(manifest_path, record)
            results.append(
                {
                    "data_type": data_type,
                    "season": season,
                    "game_type": season_type,
                    "status": "failed",
                    "error": str(error),
                }
            )

        if made_remote_attempt and index < len(requests) - 1:
            sleep(interval_seconds)

    counts = {
        status: sum(result["status"] == status for result in results)
        for status in ("downloaded", "cached", "failed")
    }
    return {"requested": len(requests), **counts, "results": results}
