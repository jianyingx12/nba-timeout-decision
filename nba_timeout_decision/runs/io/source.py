"""Validate possession partitions before scoring-run detection."""

from dataclasses import dataclass
from pathlib import Path

import pyarrow.parquet as parquet

from ...possessions.contract import POSSESSION_SCHEMA
from ...possessions.io.manifest import partition_key, read_manifest
from ...possessions.io.storage import sha256
from ...possessions.workflows.runner import RECONSTRUCTION_VERSION


@dataclass(frozen=True)
class SourcePartition:
    path: Path
    row_count: int
    game_count: int
    sha256: str
    file_size: int


def validate_source_partition(
    source: Path,
    possession_manifest: Path,
    *,
    season: int,
    game_type: str,
) -> SourcePartition:
    manifest = read_manifest(possession_manifest)
    records = manifest["partitions"]
    assert isinstance(records, dict)
    key = partition_key(season, game_type)
    record = records.get(key)
    if not isinstance(record, dict):
        raise ValueError(f"Possession manifest has no record for {key}")
    if record.get("status") != "complete":
        raise ValueError(f"Possession source is not complete for {key}")
    if record.get("reconstruction_version") != RECONSTRUCTION_VERSION:
        raise ValueError(f"Possession reconstruction version does not match for {key}")
    if int(record.get("rejected_game_count", -1)) != 0:
        raise ValueError(f"Possession source contains rejected games for {key}")

    recorded_path = Path(str(record.get("output_path", "")))
    if source.resolve() != recorded_path.resolve():
        raise ValueError(f"Possession source path does not match manifest for {key}")

    metadata = parquet.ParquetFile(source).metadata
    source_hash = sha256(source)
    schema = parquet.read_schema(source)
    checks = {
        "hash": source_hash == record.get("output_sha256"),
        "file size": source.stat().st_size == record.get("output_file_size"),
        "row count": metadata.num_rows == record.get("possession_count"),
        "canonical schema": schema.equals(POSSESSION_SCHEMA),
    }
    failed = [name for name, valid in checks.items() if not valid]
    if failed:
        raise ValueError(
            f"Possession source failed manifest validation for {key}: "
            + ", ".join(failed)
        )

    return SourcePartition(
        path=source,
        row_count=metadata.num_rows,
        game_count=int(record["accepted_game_count"]),
        sha256=source_hash,
        file_size=source.stat().st_size,
    )
