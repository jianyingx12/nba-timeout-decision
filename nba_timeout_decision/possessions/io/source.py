"""Validate normalized event partitions before reconstruction."""

from dataclasses import dataclass
from pathlib import Path

import pyarrow.parquet as parquet

from ...normalization.io.manifest import partition_key, read_manifest
from ...normalization.workflows.pipeline import CANONICAL_COLUMNS
from ...normalization.workflows.runner import PIPELINE_VERSION
from .storage import sha256


@dataclass(frozen=True)
class SourcePartition:
    path: Path
    row_count: int
    sha256: str
    file_size: int


def validate_source_partition(
    source: Path,
    normalization_manifest: Path,
    *,
    season: int,
    game_type: str,
) -> SourcePartition:
    manifest = read_manifest(normalization_manifest)
    records = manifest["partitions"]
    assert isinstance(records, dict)
    key = partition_key(season, game_type)
    record = records.get(key)
    if not isinstance(record, dict):
        raise ValueError(f"Normalization manifest has no record for {key}")
    if record.get("status") != "complete":
        raise ValueError(f"Normalized source is not complete for {key}")
    if record.get("pipeline_version") != PIPELINE_VERSION:
        raise ValueError(f"Normalization pipeline version does not match for {key}")

    recorded_path = Path(str(record.get("output_path", "")))
    if source.resolve() != recorded_path.resolve():
        raise ValueError(f"Normalized source path does not match manifest for {key}")

    metadata = parquet.ParquetFile(source).metadata
    source_hash = sha256(source)
    columns = parquet.read_schema(source).names
    checks = {
        "hash": source_hash == record.get("output_sha256"),
        "file size": source.stat().st_size == record.get("output_file_size"),
        "row count": metadata.num_rows == record.get("normalized_row_count"),
        "canonical columns": columns == list(CANONICAL_COLUMNS),
    }
    failed = [name for name, valid in checks.items() if not valid]
    if failed:
        raise ValueError(
            f"Normalized source failed manifest validation for {key}: "
            + ", ".join(failed)
        )

    return SourcePartition(
        path=source,
        row_count=metadata.num_rows,
        sha256=source_hash,
        file_size=source.stat().st_size,
    )
