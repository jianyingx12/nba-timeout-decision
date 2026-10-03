"""Game catalog extraction from shot-detail partitions."""

import csv
import os
from datetime import datetime
from pathlib import Path

import pyarrow.parquet as parquet

from .files import sha256

SOURCE_COLUMNS = (
    "GAME_ID",
    "GAME_DATE",
    "HTM",
    "VTM",
    "_season",
    "_season_type",
)
OUTPUT_COLUMNS = (
    "game_id",
    "season",
    "season_start_year",
    "game_type",
    "game_date",
    "home_team",
    "away_team",
    "shot_rows",
    "play_by_play_rows",
    "has_shotdetail",
    "has_play_by_play",
)
PLAY_BY_PLAY_COLUMNS = ("gameId", "actionId", "_season", "_season_type")
SEASON_TYPE_CODES = {"regular": "rg", "playoffs": "po"}


def _season_label(start_year: int) -> str:
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def _iso_date(value: object) -> str:
    return datetime.strptime(str(value), "%Y%m%d").date().isoformat()


def extract_games(
    source: Path, expected_season: int, expected_season_type: str
) -> tuple[list[dict[str, object]], int]:
    schema_names = set(parquet.read_schema(source).names)
    missing = set(SOURCE_COLUMNS) - schema_names
    if missing:
        raise ValueError(f"Missing shot-detail columns: {', '.join(sorted(missing))}")

    table = parquet.read_table(source, columns=list(SOURCE_COLUMNS))
    columns = table.to_pydict()
    expected_type_code = SEASON_TYPE_CODES[expected_season_type]
    games: dict[str, dict[str, object]] = {}

    for index in range(table.num_rows):
        season = int(columns["_season"][index])
        season_type = str(columns["_season_type"][index]).strip()
        if season != expected_season or season_type != expected_type_code:
            raise ValueError(
                f"Unexpected partition values at row {index}: season={season}, "
                f"season_type={season_type!r}"
            )

        game_id = str(columns["GAME_ID"][index]).zfill(10)
        identity = {
            "game_id": game_id,
            "season": _season_label(season),
            "season_start_year": season,
            "game_type": expected_season_type,
            "game_date": _iso_date(columns["GAME_DATE"][index]),
            "home_team": str(columns["HTM"][index]).strip(),
            "away_team": str(columns["VTM"][index]).strip(),
        }

        existing = games.get(game_id)
        if existing is None:
            games[game_id] = {**identity, "shot_rows": 1}
        else:
            for field, value in identity.items():
                if existing[field] != value:
                    raise ValueError(
                        f"Conflicting {field} values for game {game_id}: "
                        f"{existing[field]!r} and {value!r}"
                    )
            existing["shot_rows"] = int(existing["shot_rows"]) + 1

    return sorted(games.values(), key=lambda row: (str(row["game_date"]), str(row["game_id"]))), table.num_rows


def add_play_by_play_counts(
    rows: list[dict[str, object]],
    source: Path,
    expected_season: int,
    expected_season_type: str,
) -> int:
    schema_names = set(parquet.read_schema(source).names)
    missing = set(PLAY_BY_PLAY_COLUMNS) - schema_names
    if missing:
        raise ValueError(f"Missing play-by-play columns: {', '.join(sorted(missing))}")

    table = parquet.read_table(source, columns=list(PLAY_BY_PLAY_COLUMNS))
    columns = table.to_pydict()
    expected_type_code = SEASON_TYPE_CODES[expected_season_type]
    counts: dict[str, int] = {}
    last_action_ids: dict[str, int] = {}

    for index in range(table.num_rows):
        season = int(columns["_season"][index])
        season_type = str(columns["_season_type"][index]).strip()
        if season != expected_season or season_type != expected_type_code:
            raise ValueError(
                f"Unexpected play-by-play partition values at row {index}: season={season}, "
                f"season_type={season_type!r}"
            )

        game_id = str(columns["gameId"][index]).zfill(10)
        action_id = int(columns["actionId"][index])
        previous_action_id = last_action_ids.get(game_id)
        if previous_action_id is not None and action_id <= previous_action_id:
            raise ValueError(
                f"Play-by-play actionId is not strictly increasing for game {game_id}: "
                f"{previous_action_id} then {action_id}"
            )
        last_action_ids[game_id] = action_id
        counts[game_id] = counts.get(game_id, 0) + 1

    catalog_ids = {str(row["game_id"]) for row in rows}
    play_by_play_ids = set(counts)
    missing_play_by_play = sorted(catalog_ids - play_by_play_ids)
    missing_shotdetail = sorted(play_by_play_ids - catalog_ids)
    if missing_play_by_play or missing_shotdetail:
        raise ValueError(
            "Game sets do not match: "
            f"missing play-by-play={missing_play_by_play[:5]}, "
            f"missing shot detail={missing_shotdetail[:5]}"
        )

    for row in rows:
        game_id = str(row["game_id"])
        row["play_by_play_rows"] = counts[game_id]
        row["has_shotdetail"] = True
        row["has_play_by_play"] = True
    return table.num_rows


def write_catalog(rows: list[dict[str, object]], destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.part-{os.getpid()}")
    try:
        with temporary.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=OUTPUT_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        digest = sha256(temporary)
        os.replace(temporary, destination)
        return digest
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
