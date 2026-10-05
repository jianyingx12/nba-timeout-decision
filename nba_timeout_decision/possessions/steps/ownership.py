"""Identify game participants and event-level control evidence."""

from dataclasses import dataclass
from typing import Mapping

import pyarrow as pa


@dataclass(frozen=True)
class Team:
    team_id: int
    code: str


@dataclass(frozen=True)
class GameTeams:
    home: Team
    away: Team

    def contains(self, team_id: int) -> bool:
        return team_id in {self.home.team_id, self.away.team_id}

    def opponent(self, team_id: int) -> Team:
        if team_id == self.home.team_id:
            return self.away
        if team_id == self.away.team_id:
            return self.home
        raise ValueError(f"Team {team_id} is not a game participant")

    def team(self, team_id: int) -> Team:
        if team_id == self.home.team_id:
            return self.home
        if team_id == self.away.team_id:
            return self.away
        raise ValueError(f"Team {team_id} is not a game participant")


@dataclass(frozen=True)
class ControlEvidence:
    team_id: int | None
    kind: str


DIRECT_OFFENSE_EVENTS = {
    "made_shot",
    "missed_shot",
    "heave",
    "turnover",
}


def game_teams(table: pa.Table) -> GameTeams:
    roles = table["event_team_role"].cast(pa.string()).to_pylist()
    team_ids = table["event_team_id"].cast(pa.int64()).to_pylist()
    codes = table["event_team_code"].cast(pa.string()).to_pylist()
    by_role: dict[str, set[tuple[int, str]]] = {"home": set(), "away": set()}

    for role, team_id, code in zip(roles, team_ids, codes, strict=True):
        if role in by_role and team_id is not None and code is not None:
            by_role[role].add((team_id, code))

    for role, teams in by_role.items():
        if len(teams) != 1:
            raise ValueError(f"Expected one {role} team, found {sorted(teams)}")

    home_id, home_code = next(iter(by_role["home"]))
    away_id, away_code = next(iter(by_role["away"]))
    if home_id == away_id:
        raise ValueError("Home and away team IDs must differ")
    return GameTeams(
        home=Team(home_id, home_code),
        away=Team(away_id, away_code),
    )


def control_evidence(
    event: Mapping[str, object], teams: GameTeams
) -> ControlEvidence:
    team_id = event.get("event_team_id")
    if team_id is not None:
        if not isinstance(team_id, int) or not teams.contains(team_id):
            raise ValueError(f"Invalid event team ID: {team_id}")

    event_type = event.get("event_type")
    event_subtype = event.get("event_subtype")
    action_type = event.get("action_type")

    if event_type in DIRECT_OFFENSE_EVENTS:
        return ControlEvidence(team_id=team_id, kind="offense_action")
    if event_type == "rebound":
        return ControlEvidence(team_id=team_id, kind="gained_control")
    if action_type == "Steal":
        return ControlEvidence(team_id=team_id, kind="gained_control")
    if event_type == "free_throw":
        kind = (
            "penalty_shooter"
            if "Technical" in str(event_subtype or "")
            else "offense_action"
        )
        return ControlEvidence(team_id=team_id, kind=kind)
    return ControlEvidence(team_id=None, kind="none")


def carry_control(
    current_team_id: int | None, evidence: ControlEvidence
) -> int | None:
    if (
        evidence.kind in {"offense_action", "gained_control"}
        and evidence.team_id is not None
    ):
        return evidence.team_id
    return current_team_id
