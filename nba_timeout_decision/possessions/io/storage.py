"""Write and inspect reconstructed possession partitions."""

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as parquet

from ..contract import POSSESSION_SCHEMA


@dataclass(frozen=True)
class StoredPartition:
    path: Path
    row_count: int
    sha256: str
    file_size: int


def possession_path(
    output_root: Path, season: int, game_type: str
) -> Path:
    return output_root / str(season) / f"{game_type}.parquet"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_partition(path: Path) -> StoredPartition:
    metadata = parquet.ParquetFile(path).metadata
    return StoredPartition(
        path=path,
        row_count=metadata.num_rows,
        sha256=sha256(path),
        file_size=path.stat().st_size,
    )


def write_partition(table: pa.Table, path: Path) -> StoredPartition:
    if not table.schema.equals(POSSESSION_SCHEMA):
        raise ValueError("Possession output does not match the canonical schema")

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.part-{os.getpid()}")
    try:
        parquet.write_table(table, temporary, compression="zstd")
        stored = inspect_partition(temporary)
        if stored.row_count != table.num_rows:
            raise ValueError(
                "Possession output row count changed while writing: "
                f"{stored.row_count} != {table.num_rows}"
            )
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    return StoredPartition(
        path=path,
        row_count=stored.row_count,
        sha256=stored.sha256,
        file_size=stored.file_size,
    )
