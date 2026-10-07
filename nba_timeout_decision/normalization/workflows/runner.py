"""Run, cache, and record one normalized partition."""

from dataclasses import asdict, dataclass
from pathlib import Path

import pyarrow.parquet as parquet

from ...io.files import sha256
from ...io.manifest import partition_key, read_manifest, upsert_partition
from ..io.storage import inspect_partition, normalized_path, write_partition
from .pipeline import CANONICAL_COLUMNS, normalize_partition

PIPELINE_VERSION = 2


@dataclass(frozen=True)
class MaterializedPartition:
    status: str
    path: Path
    source_row_count: int
    normalized_row_count: int
    rejected_game_count: int
    output_sha256: str


def _cached_result(
    *,
    record: object,
    source_hash: str,
    catalog_hash: str,
    output: Path,
) -> MaterializedPartition | None:
    if not isinstance(record, dict):
        return None
    expected = {
        "status": "complete",
        "pipeline_version": PIPELINE_VERSION,
        "input_sha256": source_hash,
        "catalog_sha256": catalog_hash,
        "output_path": output.as_posix(),
    }
    if any(record.get(name) != value for name, value in expected.items()):
        return None
    try:
        stored = inspect_partition(output)
        columns = parquet.read_schema(output).names
    except (OSError, ValueError):
        return None
    if columns != list(CANONICAL_COLUMNS):
        return None
    if stored.sha256 != record.get("output_sha256"):
        return None
    if stored.row_count != record.get("normalized_row_count"):
        return None
    if stored.file_size != record.get("output_file_size"):
        return None
    return MaterializedPartition(
        status="reused",
        path=output,
        source_row_count=int(record["source_row_count"]),
        normalized_row_count=stored.row_count,
        rejected_game_count=int(record["rejected_game_count"]),
        output_sha256=stored.sha256,
    )


def materialize_partition(
    source: Path,
    catalog: Path,
    *,
    raw_root: Path,
    output_root: Path,
    manifest_path: Path,
    season: int,
    game_type: str,
    refresh: bool = False,
) -> MaterializedPartition:
    source_hash = sha256(source)
    catalog_hash = sha256(catalog)
    output = normalized_path(output_root, season, game_type)
    manifest = read_manifest(manifest_path)
    partitions = manifest["partitions"]
    assert isinstance(partitions, dict)

    if not refresh:
        cached = _cached_result(
            record=partitions.get(partition_key(season, game_type)),
            source_hash=source_hash,
            catalog_hash=catalog_hash,
            output=output,
        )
        if cached is not None:
            return cached

    try:
        result = normalize_partition(
            source,
            catalog,
            raw_root=raw_root,
            expected_season=season,
            expected_game_type=game_type,
        )
        stored = write_partition(result.table, output)
    except Exception as error:
        upsert_partition(
            manifest_path,
            season,
            game_type,
            {
                "status": "failed",
                "pipeline_version": PIPELINE_VERSION,
                "season": season,
                "game_type": game_type,
                "input_path": source.as_posix(),
                "input_sha256": source_hash,
                "catalog_path": catalog.as_posix(),
                "catalog_sha256": catalog_hash,
                "output_path": output.as_posix(),
                "stale_output_present": output.exists(),
                "error": str(error),
            },
        )
        raise

    rejected_rows = sum(
        rejection.raw_row_count for rejection in result.rejected_games
    )
    record: dict[str, object] = {
        "status": "complete",
        "pipeline_version": PIPELINE_VERSION,
        "season": season,
        "game_type": game_type,
        "input_path": source.as_posix(),
        "input_sha256": source_hash,
        "catalog_path": catalog.as_posix(),
        "catalog_sha256": catalog_hash,
        "output_path": output.as_posix(),
        "output_sha256": stored.sha256,
        "output_file_size": stored.file_size,
        "source_row_count": result.source_row_count,
        "normalized_row_count": stored.row_count,
        "rejected_row_count": rejected_rows,
        "rejected_game_count": len(result.rejected_games),
        "rejected_games": [asdict(item) for item in result.rejected_games],
        "warnings": dict(result.warnings),
    }
    upsert_partition(manifest_path, season, game_type, record)

    return MaterializedPartition(
        status="written",
        path=output,
        source_row_count=result.source_row_count,
        normalized_row_count=stored.row_count,
        rejected_game_count=len(result.rejected_games),
        output_sha256=stored.sha256,
    )
