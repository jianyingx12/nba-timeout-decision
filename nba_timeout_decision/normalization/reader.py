"""Read raw play-by-play with validated game metadata."""

import csv
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as parquet

SOURCE_COLUMNS = (
    "actionNumber",
    "clock",
    "period",
    "teamId",
    "teamTricode",
    "personId",
    "playerName",
    "playerNameI",
    "xLegacy",
    "yLegacy",
    "shotDistance",
    "shotResult",
    "isFieldGoal",
    "scoreHome",
    "scoreAway",
    "pointsTotal",
    "location",
    "description",
    "actionType",
    "subType",
    "videoAvailable",
    "actionId",
    "gameId",
    "_season",
    "_season_type",
)
OPTIONAL_SOURCE_COLUMNS = ("shotValue",)
CATALOG_COLUMNS = (
    "game_id",
    "season",
    "season_start_year",
    "game_type",
    "game_date",
    "home_team",
    "away_team",
)
SEASON_TYPE_CODES = {"regular": "rg", "playoffs": "po"}


@dataclass(frozen=True)
class GameMetadata:
    season: str
    season_start_year: int
    game_type: str
    game_date: date
    home_team: str
    away_team: str


@dataclass(frozen=True)
class GameRejection:
    game_id: str
    reason: str
    raw_row_count: int


@dataclass(frozen=True)
class PartitionProjection:
    table: pa.Table
    source_row_count: int
    rejected_games: tuple[GameRejection, ...]


def _read_catalog(
    path: Path, expected_season: int, expected_game_type: str
) -> dict[str, GameMetadata]:
    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        missing = set(CATALOG_COLUMNS) - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"Missing catalog columns: {', '.join(sorted(missing))}")

        games: dict[str, GameMetadata] = {}
        for row in reader:
            if int(row["season_start_year"]) != expected_season:
                continue
            if row["game_type"] != expected_game_type:
                continue

            game_id = row["game_id"].zfill(10)
            if game_id in games:
                raise ValueError(f"Duplicate catalog game ID: {game_id}")
            metadata = GameMetadata(
                season=row["season"],
                season_start_year=expected_season,
                game_type=expected_game_type,
                game_date=date.fromisoformat(row["game_date"]),
                home_team=row["home_team"].strip(),
                away_team=row["away_team"].strip(),
            )
            if not metadata.home_team or not metadata.away_team:
                raise ValueError(f"Missing catalog team for game {game_id}")
            games[game_id] = metadata

    if not games:
        raise ValueError(
            f"Catalog has no games for season={expected_season}, "
            f"game_type={expected_game_type}"
        )
    return games


def _source_name(source: Path, raw_root: Path) -> str:
    try:
        return source.resolve().relative_to(raw_root.resolve()).as_posix()
    except ValueError as error:
        raise ValueError(f"Source is outside raw root: {source}") from error


def read_partition(
    source: Path,
    catalog: Path,
    *,
    raw_root: Path,
    expected_season: int,
    expected_game_type: str,
) -> PartitionProjection:
    schema_names = set(parquet.read_schema(source).names)
    missing = set(SOURCE_COLUMNS) - schema_names
    if missing:
        raise ValueError(f"Missing play-by-play columns: {', '.join(sorted(missing))}")

    selected = list(SOURCE_COLUMNS)
    selected.extend(name for name in OPTIONAL_SOURCE_COLUMNS if name in schema_names)
    raw = parquet.read_table(source, columns=selected)
    source_row_count = raw.num_rows

    if "shotValue" not in raw.column_names:
        raw = raw.append_column("shotValue", pa.nulls(raw.num_rows, pa.int64()))

    seasons = set(raw["_season"].to_pylist())
    if seasons != {expected_season}:
        raise ValueError(f"Unexpected source seasons: {sorted(seasons)}")
    expected_type_code = SEASON_TYPE_CODES[expected_game_type]
    season_types = {str(value).strip() for value in raw["_season_type"].to_pylist()}
    if season_types != {expected_type_code}:
        raise ValueError(f"Unexpected source season types: {sorted(season_types)}")

    catalog_games = _read_catalog(catalog, expected_season, expected_game_type)
    game_ids = [str(value).zfill(10) for value in raw["gameId"].to_pylist()]
    missing_counts = Counter(game_id for game_id in game_ids if game_id not in catalog_games)
    rejected_games = tuple(
        GameRejection(
            game_id=game_id,
            reason="game absent from catalog",
            raw_row_count=row_count,
        )
        for game_id, row_count in sorted(missing_counts.items())
    )

    accepted = [game_id in catalog_games for game_id in game_ids]
    if rejected_games:
        raw = raw.filter(pa.array(accepted, type=pa.bool_()))
    accepted_game_ids = [
        game_id for game_id, is_accepted in zip(game_ids, accepted, strict=True) if is_accepted
    ]
    metadata = [catalog_games[game_id] for game_id in accepted_game_ids]
    source_name = _source_name(source, raw_root)
    source_row_numbers = [
        index for index, is_accepted in enumerate(accepted) if is_accepted
    ]

    projected = pa.table(
        {
            "game_id": pa.array(accepted_game_ids, type=pa.string()),
            "season": pa.array([game.season for game in metadata], type=pa.string()),
            "season_start_year": pa.array(
                [game.season_start_year for game in metadata], type=pa.int16()
            ),
            "game_type": pa.array(
                [game.game_type for game in metadata], type=pa.string()
            ),
            "game_date": pa.array(
                [game.game_date for game in metadata], type=pa.date32()
            ),
            "home_team": pa.array(
                [game.home_team for game in metadata], type=pa.string()
            ),
            "away_team": pa.array(
                [game.away_team for game in metadata], type=pa.string()
            ),
            "source_partition": pa.array(
                [source_name] * len(metadata), type=pa.string()
            ),
            "source_row_number": pa.array(source_row_numbers, type=pa.int64()),
        }
    )
    for name in (*SOURCE_COLUMNS, *OPTIONAL_SOURCE_COLUMNS):
        projected = projected.append_column(name, raw[name])

    return PartitionProjection(
        table=projected,
        source_row_count=source_row_count,
        rejected_games=rejected_games,
    )
