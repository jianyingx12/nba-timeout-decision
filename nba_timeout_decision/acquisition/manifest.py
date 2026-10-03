"""Partition manifest records."""

import csv
import os
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as parquet

from . import archive

FIELDS = (
    "source",
    "source_url",
    "source_revision",
    "source_object_id",
    "data_type",
    "season",
    "game_type",
    "local_path",
    "sha256",
    "download_status",
    "attempt_count",
    "last_attempt_utc",
    "http_status",
    "error",
    "row_count",
    "file_size",
)
KEY_FIELDS = ("data_type", "season", "game_type")


def success_record(
    *,
    data_type: str,
    season: int,
    season_type: str,
    result: dict[str, object],
) -> dict[str, object | None]:
    path = Path(str(result["path"]))
    return {
        "source": "cdechoch/nba-data-archive",
        "source_url": result["url"],
        "source_revision": result.get("source_revision"),
        "source_object_id": result.get("source_object_id"),
        "data_type": data_type,
        "season": season,
        "game_type": season_type,
        "local_path": str(path),
        "sha256": result["sha256"],
        "download_status": result["status"],
        "attempt_count": result["attempt"],
        "last_attempt_utc": datetime.now(timezone.utc).isoformat(),
        "http_status": result.get("http_status"),
        "error": "",
        "row_count": parquet.ParquetFile(path).metadata.num_rows,
        "file_size": result["bytes"],
    }


def failure_record(
    *,
    data_type: str,
    season: int,
    season_type: str,
    output_root: Path,
    attempts: int,
    http_status: int | None,
    error: str,
) -> dict[str, object | None]:
    return {
        "source": "cdechoch/nba-data-archive",
        "source_url": archive.url(data_type, season, season_type),
        "data_type": data_type,
        "season": season,
        "game_type": season_type,
        "local_path": str(archive.local_path(output_root, data_type, season, season_type)),
        "download_status": "failed",
        "attempt_count": attempts,
        "last_attempt_utc": datetime.now(timezone.utc).isoformat(),
        "http_status": http_status,
        "error": error,
    }


def _key(record: dict[str, object]) -> tuple[str, str, str]:
    return tuple(str(record[field]) for field in KEY_FIELDS)


def upsert(path: Path, record: dict[str, object | None]) -> None:
    records: dict[tuple[str, str, str], dict[str, str]] = {}
    if path.exists():
        with path.open(encoding="utf-8", newline="") as source:
            for existing in csv.DictReader(source):
                records[_key(existing)] = existing

    record_key = _key(record)
    merged = records.get(record_key, {field: "" for field in FIELDS})
    for field, value in record.items():
        if value is not None:
            merged[field] = str(value)
    records[record_key] = merged

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.part-{os.getpid()}")
    try:
        with temporary.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(records[key] for key in sorted(records))
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
