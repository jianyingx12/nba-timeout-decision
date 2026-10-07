"""Validate reconstructed possession partitions and write reports."""

import json
import os
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import pyarrow.parquet as parquet

from ..contract import POSSESSION_SCHEMA
from ...io.manifest import partition_key, read_manifest
from ..io.source import validate_source_partition
from ..io.storage import inspect_partition
from ..validation.checks import check_partition
from .batch import GAME_TYPES
from .runner import RECONSTRUCTION_VERSION


def validate_possessions(
    *,
    manifest_path: Path,
    normalization_manifest: Path,
    seasons: list[int],
    game_types: tuple[str, ...] | list[str] = GAME_TYPES,
) -> dict[str, object]:
    manifest = read_manifest(manifest_path)
    records = manifest["partitions"]
    assert isinstance(records, dict)
    expected_keys = {
        partition_key(season, game_type)
        for season in sorted(set(seasons))
        for game_type in game_types
    }
    issues = [
        f"Missing manifest partition: {key}"
        for key in sorted(expected_keys - set(records))
    ]
    warnings: Counter[str] = Counter()
    reports: list[dict[str, object]] = []

    for key in sorted(expected_keys & set(records)):
        record = records[key]
        if not isinstance(record, dict):
            issues.append(f"{key}: manifest record is invalid")
            continue
        partition_issues: list[str] = []
        if record.get("status") != "complete":
            partition_issues.append(f"status is {record.get('status')!r}")
        if record.get("reconstruction_version") != RECONSTRUCTION_VERSION:
            partition_issues.append("reconstruction version does not match")

        season_text, game_type = key.split("/", maxsplit=1)
        season = int(season_text)
        source = Path(str(record.get("input_path", "")))
        output = Path(str(record.get("output_path", "")))
        try:
            validated_source = validate_source_partition(
                source,
                normalization_manifest,
                season=season,
                game_type=game_type,
            )
        except (OSError, ValueError) as error:
            partition_issues.append(f"input validation failed: {error}")
            validated_source = None

        try:
            stored = inspect_partition(output)
            columns = parquet.read_schema(output).names
        except (OSError, ValueError) as error:
            partition_issues.append(f"output cannot be read: {error}")
            stored = None
            columns = []

        checks = None
        rejected = record.get("rejected_games", [])
        if not isinstance(rejected, list):
            partition_issues.append("rejected_games is not a list")
            rejected = []
        rejected_ids = {
            str(item["game_id"])
            for item in rejected
            if isinstance(item, dict) and "game_id" in item
        }
        if validated_source is not None and stored is not None:
            source_table = parquet.read_table(
                source, columns=["game_id", "home_score", "away_score"]
            )
            output_table = parquet.read_table(output)
            checks = check_partition(
                source_table,
                output_table,
                rejected_game_ids=rejected_ids,
            )
            partition_issues.extend(checks.issues)

        if validated_source is not None:
            if validated_source.sha256 != record.get("input_sha256"):
                partition_issues.append("input hash does not match")
            if validated_source.row_count != record.get("source_event_count"):
                partition_issues.append("source event count does not match")
        if stored is not None:
            if columns != POSSESSION_SCHEMA.names:
                partition_issues.append("possession columns do not match")
            if stored.sha256 != record.get("output_sha256"):
                partition_issues.append("output hash does not match")
            if stored.file_size != record.get("output_file_size"):
                partition_issues.append("output file size does not match")
            if stored.row_count != record.get("possession_count"):
                partition_issues.append("possession count does not match")
        if checks is not None:
            count_checks = {
                "accepted game count": (
                    checks.accepted_games,
                    record.get("accepted_game_count"),
                ),
                "rejected game count": (
                    checks.rejected_games,
                    record.get("rejected_game_count"),
                ),
                "ambiguous possession count": (
                    checks.ambiguous_possessions,
                    dict(record.get("warnings", {})).get(
                        "ambiguous_possessions", 0
                    ),
                ),
            }
            for name, (actual, recorded) in count_checks.items():
                if actual != recorded:
                    partition_issues.append(f"{name} does not match")

        record_warnings = record.get("warnings", {})
        if isinstance(record_warnings, dict):
            warnings.update(
                {str(name): int(count) for name, count in record_warnings.items()}
            )
        report = {
            "partition": key,
            "valid": not partition_issues,
            "issues": partition_issues,
            "warnings": record_warnings,
        }
        if checks is not None:
            report.update(asdict(checks))
            report["issues"] = partition_issues
        reports.append(report)
        issues.extend(f"{key}: {issue}" for issue in partition_issues)

    return {
        "valid": not issues,
        "reconstruction_version": RECONSTRUCTION_VERSION,
        "partitions": len(reports),
        "source_games": sum(int(item.get("source_games", 0)) for item in reports),
        "accepted_games": sum(
            int(item.get("accepted_games", 0)) for item in reports
        ),
        "rejected_games": sum(
            int(item.get("rejected_games", 0)) for item in reports
        ),
        "possessions": sum(int(item.get("possessions", 0)) for item in reports),
        "ambiguous_possessions": sum(
            int(item.get("ambiguous_possessions", 0)) for item in reports
        ),
        "unassigned_score_points": sum(
            int(item.get("unassigned_score_points", 0)) for item in reports
        ),
        "imbalanced_games": sum(
            int(item.get("imbalanced_games", 0)) for item in reports
        ),
        "warnings": dict(sorted(warnings.items())),
        "issues": issues,
        "partition_results": reports,
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
