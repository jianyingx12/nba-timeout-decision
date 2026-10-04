"""Validate normalized partitions against their manifest and game catalog."""

import csv
import json
import os
from collections import Counter, defaultdict
from pathlib import Path

import pyarrow.parquet as parquet

from .batch import GAME_TYPES
from ..io.manifest import partition_key, read_manifest
from ..io.storage import inspect_partition
from .pipeline import CANONICAL_COLUMNS
from .runner import PIPELINE_VERSION


def _catalog_games(path: Path) -> dict[str, set[str]]:
    games: dict[str, set[str]] = defaultdict(set)
    with path.open(encoding="utf-8", newline="") as source:
        for row in csv.DictReader(source):
            key = partition_key(int(row["season_start_year"]), row["game_type"])
            game_id = row["game_id"].zfill(10)
            if game_id in games[key]:
                raise ValueError(f"Duplicate catalog game ID in {key}: {game_id}")
            games[key].add(game_id)
    return games


def validate_normalization(
    *,
    manifest_path: Path,
    catalog_path: Path,
    seasons: list[int],
    game_types: tuple[str, ...] = GAME_TYPES,
) -> dict[str, object]:
    manifest = read_manifest(manifest_path)
    records = manifest["partitions"]
    assert isinstance(records, dict)
    catalog_games = _catalog_games(catalog_path)
    expected_keys = {
        partition_key(season, game_type)
        for season in sorted(set(seasons))
        for game_type in game_types
    }
    issues: list[str] = []
    warnings: Counter[str] = Counter()
    rejection_reasons: Counter[str] = Counter()
    partition_reports: list[dict[str, object]] = []
    total_source_rows = 0
    total_normalized_rows = 0
    total_rejected_rows = 0
    total_normalized_games = 0
    total_rejected_games = 0

    unexpected_keys = sorted(set(records) - expected_keys)
    missing_keys = sorted(expected_keys - set(records))
    if unexpected_keys:
        issues.append(f"Unexpected manifest partitions: {unexpected_keys}")
    if missing_keys:
        issues.append(f"Missing manifest partitions: {missing_keys}")

    for key in sorted(expected_keys & set(records)):
        record = records[key]
        if not isinstance(record, dict):
            issues.append(f"Invalid manifest record: {key}")
            continue
        partition_issues: list[str] = []
        if record.get("status") != "complete":
            partition_issues.append(f"status is {record.get('status')!r}")
        if record.get("pipeline_version") != PIPELINE_VERSION:
            partition_issues.append("pipeline version does not match")

        output = Path(str(record.get("output_path", "")))
        try:
            stored = inspect_partition(output)
            columns = parquet.read_schema(output).names
            normalized_game_ids = set(
                parquet.read_table(output, columns=["game_id"])["game_id"].to_pylist()
            )
        except (OSError, ValueError) as error:
            partition_issues.append(f"output cannot be read: {error}")
            stored = None
            columns = []
            normalized_game_ids = set()

        rejected = record.get("rejected_games", [])
        if not isinstance(rejected, list):
            partition_issues.append("rejected_games is not a list")
            rejected = []
        rejected_game_ids = {
            str(item["game_id"]).zfill(10)
            for item in rejected
            if isinstance(item, dict) and "game_id" in item
        }
        rejected_rows = sum(
            int(item["raw_row_count"])
            for item in rejected
            if isinstance(item, dict) and "raw_row_count" in item
        )
        for item in rejected:
            if isinstance(item, dict) and "reason" in item:
                rejection_reasons[str(item["reason"])] += 1

        expected_games = catalog_games.get(key, set())
        overlap = normalized_game_ids & rejected_game_ids
        if overlap:
            partition_issues.append("games appear in both output and rejections")
        missing_games = expected_games - normalized_game_ids - rejected_game_ids
        extra_games = (normalized_game_ids | rejected_game_ids) - expected_games
        if missing_games:
            partition_issues.append(f"{len(missing_games)} catalog games are unaccounted for")
        if extra_games:
            partition_issues.append(f"{len(extra_games)} non-catalog games are present")

        source_rows = int(record.get("source_row_count", 0))
        normalized_rows = int(record.get("normalized_row_count", 0))
        if normalized_rows + rejected_rows != source_rows:
            partition_issues.append("normalized and rejected rows do not equal source rows")
        if stored is not None:
            if stored.sha256 != record.get("output_sha256"):
                partition_issues.append("output hash does not match")
            if stored.file_size != record.get("output_file_size"):
                partition_issues.append("output size does not match")
            if stored.row_count != normalized_rows:
                partition_issues.append("output row count does not match")
        if columns != list(CANONICAL_COLUMNS):
            partition_issues.append("canonical columns do not match")

        record_warnings = record.get("warnings", {})
        if isinstance(record_warnings, dict):
            warnings.update(
                {str(name): int(count) for name, count in record_warnings.items()}
            )
        total_source_rows += source_rows
        total_normalized_rows += normalized_rows
        total_rejected_rows += rejected_rows
        total_normalized_games += len(normalized_game_ids)
        total_rejected_games += len(rejected_game_ids)
        issues.extend(f"{key}: {issue}" for issue in partition_issues)
        partition_reports.append(
            {
                "partition": key,
                "source_rows": source_rows,
                "normalized_rows": normalized_rows,
                "rejected_rows": rejected_rows,
                "normalized_games": len(normalized_game_ids),
                "rejected_games": len(rejected_game_ids),
                "warnings": record_warnings,
                "valid": not partition_issues,
            }
        )

    return {
        "valid": not issues,
        "pipeline_version": PIPELINE_VERSION,
        "partitions": len(partition_reports),
        "catalog_games": sum(len(games) for games in catalog_games.values()),
        "normalized_games": total_normalized_games,
        "rejected_games": total_rejected_games,
        "source_rows": total_source_rows,
        "normalized_rows": total_normalized_rows,
        "rejected_rows": total_rejected_rows,
        "warnings": dict(sorted(warnings.items())),
        "rejection_reasons": dict(sorted(rejection_reasons.items())),
        "issues": issues,
        "partition_results": partition_reports,
    }


def write_validation_report(path: Path, report: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.part-{os.getpid()}")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as output:
            json.dump(report, output, indent=2, sort_keys=True)
            output.write("\n")
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
