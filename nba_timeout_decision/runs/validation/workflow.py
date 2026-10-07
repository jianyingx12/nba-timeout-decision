"""Validate stored run partitions against their sources and manifests."""

import json
import os
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

import pyarrow.parquet as parquet

from ...possessions.io.storage import sha256
from ..contract import (
    RUN_SCHEMA,
    SENSITIVITY_SIGNAL_SCHEMA,
    THRESHOLD_CROSSING_SCHEMA,
)
from ..io.catalog import read_game_teams
from ..io.manifest import partition_key, read_manifest
from ..io.source import validate_source_partition
from ..io.storage import inspect_output, output_paths
from ..workflows.partition import detect_partition
from ..workflows.runner import DETECTION_VERSION
from .checks import validate_outputs


@dataclass(frozen=True)
class PartitionValidation:
    season: int
    game_type: str
    valid: bool
    errors: tuple[str, ...]
    game_count: int
    run_count: int
    primary_eligible_run_count: int
    threshold_crossing_count: int
    sensitivity_signal_count: int
    recomputed: bool


def _record_errors(
    *,
    record: object,
    paths: object,
    source_hash: str,
    catalog_hash: str,
) -> list[str]:
    if not isinstance(record, dict):
        return ["Run manifest record is missing"]
    errors: list[str] = []
    expected = {
        "status": "complete",
        "detection_version": DETECTION_VERSION,
        "input_sha256": source_hash,
        "catalog_sha256": catalog_hash,
    }
    for name, value in expected.items():
        if record.get(name) != value:
            errors.append(f"Manifest {name} does not match")
    outputs = record.get("outputs")
    if not isinstance(outputs, dict):
        return [*errors, "Manifest outputs are missing"]
    schemas = {
        "runs": RUN_SCHEMA,
        "threshold_crossings": THRESHOLD_CROSSING_SCHEMA,
        "sensitivity_signals": SENSITIVITY_SIGNAL_SCHEMA,
    }
    for name, schema in schemas.items():
        path = getattr(paths, name)
        output = outputs.get(name)
        if not isinstance(output, dict):
            errors.append(f"Manifest output is missing: {name}")
            continue
        try:
            stored = inspect_output(path)
            stored_schema = parquet.read_schema(path)
        except (OSError, ValueError) as error:
            errors.append(f"Cannot inspect {name}: {error}")
            continue
        checks = {
            "path": output.get("path") == path.as_posix(),
            "hash": output.get("sha256") == stored.sha256,
            "file size": output.get("file_size") == stored.file_size,
            "row count": output.get("row_count") == stored.row_count,
            "schema": stored_schema.equals(schema),
        }
        errors.extend(
            f"{name} {check} does not match"
            for check, valid in checks.items()
            if not valid
        )
    return errors


def validate_materialized_partition(
    source: Path,
    *,
    possession_manifest: Path,
    catalog_root: Path,
    output_root: Path,
    manifest_path: Path,
    season: int,
    game_type: str,
    recompute: bool = True,
) -> PartitionValidation:
    source_partition = validate_source_partition(
        source,
        possession_manifest,
        season=season,
        game_type=game_type,
    )
    catalog_path = catalog_root / str(season) / f"{game_type}.csv"
    catalog_hash = sha256(catalog_path)
    paths = output_paths(output_root, season, game_type)
    records = read_manifest(manifest_path)["partitions"]
    assert isinstance(records, dict)
    record = records.get(partition_key(season, game_type))
    errors = _record_errors(
        record=record,
        paths=paths,
        source_hash=source_partition.sha256,
        catalog_hash=catalog_hash,
    )
    if errors:
        return PartitionValidation(
            season,
            game_type,
            False,
            tuple(errors),
            source_partition.game_count,
            0,
            0,
            0,
            0,
            False,
        )

    runs = parquet.read_table(paths.runs)
    crossings = parquet.read_table(paths.threshold_crossings)
    sensitivity = parquet.read_table(paths.sensitivity_signals)
    checked = validate_outputs(runs, crossings, sensitivity)
    errors.extend(checked.errors)
    if isinstance(record, dict):
        if record.get("accepted_game_count") != source_partition.game_count:
            errors.append("Accepted game count does not match the possession source")
        if int(record.get("rejected_game_count", -1)) != 0:
            errors.append("Run partition contains rejected games")

    if recompute and not errors:
        teams = read_game_teams(catalog_path, season=season, game_type=game_type)
        expected = detect_partition(parquet.read_table(source), teams)
        comparisons = {
            "runs": runs.equals(expected.runs),
            "threshold crossings": crossings.equals(expected.threshold_crossings),
            "sensitivity signals": sensitivity.equals(expected.sensitivity_signals),
        }
        errors.extend(
            f"Stored {name} differ from deterministic recomputation"
            for name, matches in comparisons.items()
            if not matches
        )

    return PartitionValidation(
        season=season,
        game_type=game_type,
        valid=not errors,
        errors=tuple(errors),
        game_count=source_partition.game_count,
        run_count=checked.run_count,
        primary_eligible_run_count=checked.primary_eligible_run_count,
        threshold_crossing_count=checked.threshold_crossing_count,
        sensitivity_signal_count=checked.sensitivity_signal_count,
        recomputed=recompute and not errors,
    )


def _examples(output_root: Path, requests: list[tuple[int, str]]) -> dict[str, object]:
    candidates: dict[str, dict[str, object]] = {}
    fields = (
        "run_id",
        "period",
        "run_team_code",
        "start_possession_number",
        "qualification_possession_number",
        "end_possession_number",
        "net_points_at_qualification",
        "maximum_threshold",
        "termination_reason",
        "contains_timeout",
        "contains_review",
    )
    for season, game_type in requests:
        path = output_paths(output_root, season, game_type).runs
        if not path.exists():
            continue
        for row in parquet.read_table(path).to_pylist():
            labels = []
            if int(row["maximum_threshold"]) > 6:
                labels.append("escalation")
            if row["termination_reason"] == "period_end":
                labels.append("period_end")
            if bool(row["contains_timeout"]):
                labels.append("timeout")
            if bool(row["contains_review"]):
                labels.append("review")
            if int(row["period"]) > 4:
                labels.append("overtime")
            for label in labels:
                candidates.setdefault(
                    label,
                    {
                        "season_start_year": season,
                        "game_type": game_type,
                        **{field: row[field] for field in fields},
                    },
                )
    return candidates


def validate_partitions(
    *,
    seasons: list[int],
    game_types: list[str],
    possession_root: Path,
    possession_manifest: Path,
    catalog_root: Path,
    output_root: Path,
    manifest_path: Path,
    recompute: bool = True,
) -> dict[str, object]:
    requests = [
        (season, game_type)
        for season in sorted(set(seasons))
        for game_type in game_types
    ]
    results: list[PartitionValidation] = []
    for season, game_type in requests:
        source = possession_root / str(season) / f"{game_type}.parquet"
        try:
            result = validate_materialized_partition(
                source,
                possession_manifest=possession_manifest,
                catalog_root=catalog_root,
                output_root=output_root,
                manifest_path=manifest_path,
                season=season,
                game_type=game_type,
                recompute=recompute,
            )
        except Exception as error:
            result = PartitionValidation(
                season, game_type, False, (str(error),), 0, 0, 0, 0, 0, False
            )
        results.append(result)

    totals = Counter()
    for result in results:
        totals["games"] += result.game_count
        totals["runs"] += result.run_count
        totals["primary_eligible_runs"] += result.primary_eligible_run_count
        totals["threshold_crossings"] += result.threshold_crossing_count
        totals["sensitivity_signals"] += result.sensitivity_signal_count
    return {
        "valid": all(result.valid for result in results),
        "requested": len(requests),
        "valid_partitions": sum(result.valid for result in results),
        "invalid_partitions": sum(not result.valid for result in results),
        "recomputed_partitions": sum(result.recomputed for result in results),
        **dict(totals),
        "examples": _examples(output_root, requests),
        "results": [asdict(result) for result in results],
    }


def write_report(path: Path, report: dict[str, object]) -> None:
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
