"""Materialize and cache one scoring-run partition."""

from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as parquet

from ...io.files import sha256
from ...io.manifest import partition_key, read_manifest, upsert_partition
from ..contract import (
    RUN_SCHEMA,
    SENSITIVITY_SIGNAL_SCHEMA,
    THRESHOLD_CROSSING_SCHEMA,
)
from ..io.catalog import read_game_teams
from ..io.source import validate_source_partition
from ..io.storage import (
    OutputPaths,
    StoredOutput,
    inspect_output,
    output_paths,
    write_outputs,
)
from .partition import detect_partition

DETECTION_VERSION = 3


@dataclass(frozen=True)
class MaterializedRuns:
    status: str
    paths: OutputPaths
    source_possession_count: int
    accepted_game_count: int
    rejected_game_count: int
    run_count: int
    threshold_crossing_count: int
    sensitivity_signal_count: int


def _stored_output(
    record: dict[str, object], name: str, path: Path, schema: pa.Schema
) -> StoredOutput | None:
    outputs = record.get("outputs")
    if not isinstance(outputs, dict):
        return None
    expected = outputs.get(name)
    if not isinstance(expected, dict) or expected.get("path") != path.as_posix():
        return None
    try:
        stored = inspect_output(path)
        stored_schema = parquet.read_schema(path)
    except (OSError, ValueError):
        return None
    checks = (
        stored_schema.equals(schema),
        stored.sha256 == expected.get("sha256"),
        stored.row_count == expected.get("row_count"),
        stored.file_size == expected.get("file_size"),
    )
    return stored if all(checks) else None


def _cached_result(
    *,
    record: object,
    source_hash: str,
    catalog_hash: str,
    paths: OutputPaths,
) -> MaterializedRuns | None:
    if not isinstance(record, dict):
        return None
    expected = {
        "status": "complete",
        "detection_version": DETECTION_VERSION,
        "input_sha256": source_hash,
        "catalog_sha256": catalog_hash,
    }
    if any(record.get(name) != value for name, value in expected.items()):
        return None

    stored = {
        "runs": _stored_output(record, "runs", paths.runs, RUN_SCHEMA),
        "threshold_crossings": _stored_output(
            record,
            "threshold_crossings",
            paths.threshold_crossings,
            THRESHOLD_CROSSING_SCHEMA,
        ),
        "sensitivity_signals": _stored_output(
            record,
            "sensitivity_signals",
            paths.sensitivity_signals,
            SENSITIVITY_SIGNAL_SCHEMA,
        ),
    }
    if any(value is None for value in stored.values()):
        return None
    return MaterializedRuns(
        status="reused",
        paths=paths,
        source_possession_count=int(record["source_possession_count"]),
        accepted_game_count=int(record["accepted_game_count"]),
        rejected_game_count=int(record["rejected_game_count"]),
        run_count=int(record["run_count"]),
        threshold_crossing_count=int(record["threshold_crossing_count"]),
        sensitivity_signal_count=int(record["sensitivity_signal_count"]),
    )


def _output_record(stored: StoredOutput) -> dict[str, object]:
    return {
        "path": stored.path.as_posix(),
        "sha256": stored.sha256,
        "file_size": stored.file_size,
        "row_count": stored.row_count,
    }


def materialize_partition(
    source: Path,
    *,
    possession_manifest: Path,
    catalog_root: Path,
    output_root: Path,
    manifest_path: Path,
    season: int,
    game_type: str,
    refresh: bool = False,
) -> MaterializedRuns:
    paths = output_paths(output_root, season, game_type)
    catalog_path = catalog_root / str(season) / f"{game_type}.csv"
    source_hash: str | None = None
    catalog_hash: str | None = None
    try:
        source_partition = validate_source_partition(
            source,
            possession_manifest,
            season=season,
            game_type=game_type,
        )
        source_hash = source_partition.sha256
        catalog_hash = sha256(catalog_path)
        manifest = read_manifest(manifest_path)
        records = manifest["partitions"]
        assert isinstance(records, dict)
        if not refresh:
            cached = _cached_result(
                record=records.get(partition_key(season, game_type)),
                source_hash=source_hash,
                catalog_hash=catalog_hash,
                paths=paths,
            )
            if cached is not None:
                return cached

        teams = read_game_teams(catalog_path, season=season, game_type=game_type)
        possessions = parquet.read_table(source)
        result = detect_partition(possessions, teams)
        stored = write_outputs(
            runs=result.runs,
            threshold_crossings=result.threshold_crossings,
            sensitivity_signals=result.sensitivity_signals,
            paths=paths,
        )
    except Exception as error:
        upsert_partition(
            manifest_path,
            season,
            game_type,
            {
                "status": "failed",
                "detection_version": DETECTION_VERSION,
                "season": season,
                "game_type": game_type,
                "input_path": source.as_posix(),
                "input_sha256": source_hash,
                "possession_manifest_path": possession_manifest.as_posix(),
                "catalog_path": catalog_path.as_posix(),
                "catalog_sha256": catalog_hash,
                "output_directory": paths.runs.parent.as_posix(),
                "stale_outputs_present": any(
                    path.exists()
                    for path in (
                        paths.runs,
                        paths.threshold_crossings,
                        paths.sensitivity_signals,
                    )
                ),
                "error": str(error),
            },
        )
        raise

    threshold_counts = Counter(result.threshold_crossings["threshold"].to_pylist())
    termination_counts = Counter(result.runs["termination_reason"].to_pylist())
    exclusion_counts = Counter(
        value for value in result.runs["exclusion_reason"].to_pylist() if value
    )
    record: dict[str, object] = {
        "status": "complete",
        "detection_version": DETECTION_VERSION,
        "season": season,
        "game_type": game_type,
        "input_path": source.as_posix(),
        "input_sha256": source_hash,
        "possession_manifest_path": possession_manifest.as_posix(),
        "catalog_path": catalog_path.as_posix(),
        "catalog_sha256": catalog_hash,
        "outputs": {
            "runs": _output_record(stored.runs),
            "threshold_crossings": _output_record(stored.threshold_crossings),
            "sensitivity_signals": _output_record(stored.sensitivity_signals),
        },
        "source_possession_count": result.source_possession_count,
        "accepted_game_count": result.accepted_game_count,
        "rejected_game_count": len(result.rejected_games),
        "rejected_games": [asdict(item) for item in result.rejected_games],
        "run_count": stored.runs.row_count,
        "primary_eligible_run_count": sum(
            result.runs["primary_analysis_eligible"].to_pylist()
        ),
        "threshold_crossing_count": stored.threshold_crossings.row_count,
        "sensitivity_signal_count": stored.sensitivity_signals.row_count,
        "threshold_counts": {
            str(key): value for key, value in sorted(threshold_counts.items())
        },
        "termination_counts": dict(sorted(termination_counts.items())),
        "exclusion_counts": dict(sorted(exclusion_counts.items())),
        "reset_counts": dict(result.reset_counts),
        "catalog_only_game_count": result.catalog_only_game_count,
    }
    upsert_partition(manifest_path, season, game_type, record)
    return MaterializedRuns(
        status="written",
        paths=paths,
        source_possession_count=result.source_possession_count,
        accepted_game_count=result.accepted_game_count,
        rejected_game_count=len(result.rejected_games),
        run_count=stored.runs.row_count,
        threshold_crossing_count=stored.threshold_crossings.row_count,
        sensitivity_signal_count=stored.sensitivity_signals.row_count,
    )
