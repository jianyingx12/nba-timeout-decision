"""Read authoritative home and away teams from the game catalog."""

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GameTeams:
    game_id: str
    home_team_code: str
    away_team_code: str


def read_game_teams(
    path: Path, *, season: int, game_type: str
) -> dict[str, GameTeams]:
    teams: dict[str, GameTeams] = {}
    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        required = {
            "game_id",
            "season_start_year",
            "game_type",
            "home_team",
            "away_team",
        }
        missing = sorted(required - set(reader.fieldnames or ()))
        if missing:
            raise ValueError(f"Game catalog is missing columns: {missing}")

        for row in reader:
            if int(row["season_start_year"]) != season or row["game_type"] != game_type:
                continue
            game_id = str(row["game_id"]).zfill(10)
            home = str(row["home_team"]).strip()
            away = str(row["away_team"]).strip()
            if not home or not away or home == away:
                raise ValueError(f"Game catalog has invalid teams for {game_id}")
            if game_id in teams:
                raise ValueError(f"Game catalog contains duplicate game {game_id}")
            teams[game_id] = GameTeams(game_id, home, away)

    if not teams:
        raise ValueError(f"Game catalog has no games for {season}/{game_type}")
    return teams
