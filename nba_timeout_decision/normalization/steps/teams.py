"""Normalize team identity against game participants."""

from collections import defaultdict
from dataclasses import dataclass

import pyarrow as pa

from .table_ops import set_column


@dataclass(frozen=True)
class TeamNormalization:
    table: pa.Table
    conflicting_game_ids: tuple[str, ...]
    conflicting_event_count: int


def normalize_teams(table: pa.Table) -> TeamNormalization:
    game_ids = table["game_id"].cast(pa.string()).to_pylist()
    team_ids = table["event_team_id"].cast(pa.int64()).to_pylist()
    team_codes = table["event_team_code"].cast(pa.string()).to_pylist()
    home_teams = table["home_team"].cast(pa.string()).to_pylist()
    away_teams = table["away_team"].cast(pa.string()).to_pylist()

    id_to_codes: dict[tuple[str, int], set[str]] = defaultdict(set)
    code_to_ids: dict[tuple[str, str], set[int]] = defaultdict(set)
    for game_id, team_id, team_code in zip(
        game_ids, team_ids, team_codes, strict=True
    ):
        if team_id is not None and team_code is not None:
            id_to_codes[(game_id, team_id)].add(team_code)
            code_to_ids[(game_id, team_code)].add(team_id)

    teamless: list[bool] = []
    conflicts: list[bool] = []
    roles: list[str | None] = []
    conflicting_games: set[str] = set()

    for game_id, team_id, team_code, home_team, away_team in zip(
        game_ids,
        team_ids,
        team_codes,
        home_teams,
        away_teams,
        strict=True,
    ):
        is_teamless = team_id is None
        conflict = (
            (team_id is None) != (team_code is None)
            or (team_code is not None and team_code not in {home_team, away_team})
            or (
                team_id is not None
                and len(id_to_codes[(game_id, team_id)]) != 1
            )
            or (
                team_code is not None
                and len(code_to_ids[(game_id, team_code)]) != 1
            )
        )

        role: str | None = None
        if not conflict and team_code == home_team:
            role = "home"
        elif not conflict and team_code == away_team:
            role = "away"

        if conflict:
            conflicting_games.add(game_id)
        teamless.append(is_teamless)
        conflicts.append(conflict)
        roles.append(role)

    normalized = set_column(
        table, "event_is_teamless", pa.array(teamless, type=pa.bool_())
    )
    normalized = set_column(
        normalized,
        "event_team_is_conflicting",
        pa.array(conflicts, type=pa.bool_()),
    )
    normalized = set_column(
        normalized, "event_team_role", pa.array(roles, type=pa.string())
    )
    return TeamNormalization(
        table=normalized,
        conflicting_game_ids=tuple(sorted(conflicting_games)),
        conflicting_event_count=sum(conflicts),
    )
