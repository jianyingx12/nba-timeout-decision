"""Validation of cached acquisition partitions."""

from pathlib import Path

import pyarrow.parquet as parquet

from ..download.files import sha256, validate_parquet
from ..download.manifest import PartitionKey

SEASON_TYPE_CODES = {"regular": "rg", "playoffs": "po"}
GAME_ID_COLUMNS = {"nbastatsv3": "gameId", "shotdetail": "GAME_ID"}


def local_path(record: dict[str, str], project_root: Path) -> Path:
    path = Path(record["local_path"])
    return path if path.is_absolute() else project_root / path


def inspect_partition(
    key: PartitionKey, record: dict[str, str], project_root: Path
) -> tuple[dict[str, object], set[str]]:
    data_type, season, game_type = key
    path = local_path(record, project_root)
    issues: list[str] = []
    game_ids: set[str] = set()
    actual_rows = 0

    if record.get("download_status") not in {"downloaded", "cached"}:
        issues.append("unsuccessful_status")
    if not path.is_file():
        issues.append("missing_file")
    else:
        try:
            validate_parquet(path)
            if sha256(path) != record.get("sha256"):
                issues.append("hash_mismatch")

            actual_rows = parquet.ParquetFile(path).metadata.num_rows
            if str(actual_rows) != record.get("row_count"):
                issues.append("row_count_mismatch")

            game_id_column = GAME_ID_COLUMNS[data_type]
            table = parquet.read_table(
                path, columns=[game_id_column, "_season", "_season_type"]
            )
            values = table.to_pydict()
            seasons = {int(value) for value in values["_season"]}
            season_types = {str(value).strip() for value in values["_season_type"]}
            if seasons != {season} or season_types != {SEASON_TYPE_CODES[game_type]}:
                issues.append("partition_value_mismatch")
            game_ids = {str(value).zfill(10) for value in values[game_id_column]}
        except (OSError, ValueError, KeyError) as error:
            issues.append(f"malformed_file:{error}")

    return {
        "data_type": data_type,
        "season": season,
        "game_type": game_type,
        "path": str(path),
        "status": "valid" if not issues else "invalid",
        "issues": issues,
        "row_count": actual_rows,
        "game_count": len(game_ids),
    }, game_ids


def find_unexpected_files(
    records: dict[PartitionKey, dict[str, str]],
    raw_root: Path,
    project_root: Path,
) -> list[str]:
    manifest_files = {
        local_path(record, project_root).resolve() for record in records.values()
    }
    resolved_raw_root = raw_root if raw_root.is_absolute() else project_root / raw_root
    if not resolved_raw_root.exists():
        return []
    return sorted(
        str(path)
        for path in resolved_raw_root.rglob("*.parquet")
        if path.resolve() not in manifest_files
    )
