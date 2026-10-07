"""Store run, crossing, and sensitivity partitions."""

import os
from dataclasses import dataclass
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as parquet

from ...possessions.io.storage import sha256
from ..contract import (
    RUN_SCHEMA,
    SENSITIVITY_SIGNAL_SCHEMA,
    THRESHOLD_CROSSING_SCHEMA,
)


@dataclass(frozen=True)
class OutputPaths:
    runs: Path
    threshold_crossings: Path
    sensitivity_signals: Path


@dataclass(frozen=True)
class StoredOutput:
    path: Path
    row_count: int
    sha256: str
    file_size: int


@dataclass(frozen=True)
class StoredOutputs:
    runs: StoredOutput
    threshold_crossings: StoredOutput
    sensitivity_signals: StoredOutput


def output_paths(output_root: Path, season: int, game_type: str) -> OutputPaths:
    directory = output_root / str(season) / game_type
    return OutputPaths(
        runs=directory / "runs.parquet",
        threshold_crossings=directory / "threshold-crossings.parquet",
        sensitivity_signals=directory / "sensitivity-signals.parquet",
    )


def inspect_output(path: Path) -> StoredOutput:
    metadata = parquet.ParquetFile(path).metadata
    return StoredOutput(
        path=path,
        row_count=metadata.num_rows,
        sha256=sha256(path),
        file_size=path.stat().st_size,
    )


def _write(table: pa.Table, path: Path, schema: pa.Schema) -> StoredOutput:
    if not table.schema.equals(schema):
        raise ValueError(f"Output does not match the canonical schema for {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.part-{os.getpid()}")
    try:
        parquet.write_table(table, temporary, compression="zstd")
        stored = inspect_output(temporary)
        if stored.row_count != table.num_rows:
            raise ValueError(f"Output row count changed while writing {path.name}")
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return StoredOutput(path, stored.row_count, stored.sha256, stored.file_size)


def write_outputs(
    *,
    runs: pa.Table,
    threshold_crossings: pa.Table,
    sensitivity_signals: pa.Table,
    paths: OutputPaths,
) -> StoredOutputs:
    expected = (
        (runs, RUN_SCHEMA, paths.runs),
        (threshold_crossings, THRESHOLD_CROSSING_SCHEMA, paths.threshold_crossings),
        (sensitivity_signals, SENSITIVITY_SIGNAL_SCHEMA, paths.sensitivity_signals),
    )
    invalid = [path.name for table, schema, path in expected if not table.schema.equals(schema)]
    if invalid:
        raise ValueError(f"Output does not match the canonical schema: {invalid}")
    return StoredOutputs(
        runs=_write(runs, paths.runs, RUN_SCHEMA),
        threshold_crossings=_write(
            threshold_crossings,
            paths.threshold_crossings,
            THRESHOLD_CROSSING_SCHEMA,
        ),
        sensitivity_signals=_write(
            sensitivity_signals,
            paths.sensitivity_signals,
            SENSITIVITY_SIGNAL_SCHEMA,
        ),
    )
