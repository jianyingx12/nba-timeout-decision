"""Offline acquisition completeness checks."""

import json
import os
from datetime import datetime, timezone
from itertools import product
from pathlib import Path

from .archive import DATA_TYPES, SEASON_TYPES
from .manifest import PartitionKey, read
from .validation import find_unexpected_files, inspect_partition


def _expected_keys(first_season: int, last_season: int) -> set[PartitionKey]:
    return {
        (data_type, season, game_type)
        for data_type, season, game_type in product(
            DATA_TYPES, range(first_season, last_season + 1), SEASON_TYPES
        )
    }
def build_report(
    *,
    manifest_path: Path,
    raw_root: Path,
    project_root: Path,
    first_season: int,
    last_season: int,
) -> dict[str, object]:
    expected = _expected_keys(first_season, last_season)
    records, duplicate_keys = read(manifest_path)
    expected_records = expected & set(records)
    missing_keys = sorted(expected - set(records))
    unexpected_keys = sorted(set(records) - expected)
    inspections: dict[PartitionKey, dict[str, object]] = {}
    game_sets: dict[PartitionKey, set[str]] = {}

    for key in sorted(expected_records):
        inspection, game_ids = inspect_partition(key, records[key], project_root)
        inspections[key] = inspection
        game_sets[key] = game_ids

    unexpected_files = find_unexpected_files(records, raw_root, project_root)

    season_results: list[dict[str, object]] = []
    mismatched_game_sets = 0
    total_games = 0
    total_play_by_play_events = 0
    for season, game_type in product(
        range(first_season, last_season + 1), SEASON_TYPES
    ):
        pbp_key = ("nbastatsv3", season, game_type)
        shots_key = ("shotdetail", season, game_type)
        pbp_valid = inspections.get(pbp_key, {}).get("status") == "valid"
        shots_valid = inspections.get(shots_key, {}).get("status") == "valid"
        sets_match: bool | None = None
        games = 0
        events = 0
        if pbp_valid:
            events = int(inspections[pbp_key]["row_count"])
            total_play_by_play_events += events
        if pbp_valid and shots_valid:
            sets_match = game_sets[pbp_key] == game_sets[shots_key]
            if sets_match:
                games = len(game_sets[pbp_key])
                total_games += games
            else:
                mismatched_game_sets += 1

        season_results.append(
            {
                "season": season,
                "game_type": game_type,
                "valid_partitions": int(pbp_valid) + int(shots_valid),
                "game_sets_match": sets_match,
                "games": games,
                "play_by_play_events": events,
            }
        )

    partition_results = [inspections[key] for key in sorted(inspections)]
    valid_partitions = sum(result["status"] == "valid" for result in partition_results)
    invalid_partitions = len(partition_results) - valid_partitions
    issue_counts: dict[str, int] = {}
    for result in partition_results:
        for issue in result["issues"]:
            name = str(issue).split(":", 1)[0]
            issue_counts[name] = issue_counts.get(name, 0) + 1

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "study_period": {"first_season": first_season, "last_season": last_season},
        "summary": {
            "expected_partitions": len(expected),
            "manifest_entries": len(records),
            "valid_partitions": valid_partitions,
            "invalid_partitions": invalid_partitions,
            "missing_partitions": len(missing_keys),
            "unexpected_manifest_entries": len(unexpected_keys),
            "duplicate_manifest_entries": len(duplicate_keys),
            "unexpected_files": len(unexpected_files),
            "mismatched_game_sets": mismatched_game_sets,
            "games_in_matched_partitions": total_games,
            "play_by_play_events": total_play_by_play_events,
            "issue_counts": issue_counts,
        },
        "missing_partitions": [
            {"data_type": key[0], "season": key[1], "game_type": key[2]}
            for key in missing_keys
        ],
        "unexpected_manifest_entries": [list(key) for key in unexpected_keys],
        "duplicate_manifest_entries": [list(key) for key in duplicate_keys],
        "unexpected_files": unexpected_files,
        "partition_results": partition_results,
        "season_results": season_results,
    }


def write_report(report: dict[str, object], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.part-{os.getpid()}")
    try:
        with temporary.open("w", encoding="utf-8") as output:
            json.dump(report, output, indent=2, sort_keys=True)
            output.write("\n")
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
