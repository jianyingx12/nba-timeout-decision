"""Mutable state used while assembling one possession."""

from dataclasses import dataclass
from typing import Mapping

from .steps.ownership import GameTeams, Team


@dataclass(frozen=True)
class PossessionRejection:
    game_id: str
    reason: str
    event_count: int


@dataclass
class PossessionBuilder:
    game_id: str
    season: str
    season_start_year: int
    game_type: str
    game_date: object
    possession_number: int
    period: int
    offense: Team
    defense: Team
    offense_is_home: bool
    first_action_id: int
    last_action_id: int
    first_source_row_number: int
    last_source_row_number: int
    start_seconds_remaining_in_period: float
    end_seconds_remaining_in_period: float
    start_home_score: int
    start_away_score: int
    end_home_score: int
    end_away_score: int
    start_reason: str
    contains_timeout: bool = False
    contains_review: bool = False
    contains_score_revision: bool = False
    ambiguity_reason: str | None = None

    @classmethod
    def start(
        cls,
        event: Mapping[str, object],
        *,
        possession_number: int,
        offense: Team,
        teams: GameTeams,
        start_reason: str,
        start_home_score: int,
        start_away_score: int,
        ambiguity_reason: str | None = None,
    ) -> "PossessionBuilder":
        builder = cls(
            game_id=str(event["game_id"]),
            season=str(event["season"]),
            season_start_year=int(event["season_start_year"]),
            game_type=str(event["game_type"]),
            game_date=event["game_date"],
            possession_number=possession_number,
            period=int(event["period"]),
            offense=offense,
            defense=teams.opponent(offense.team_id),
            offense_is_home=offense.team_id == teams.home.team_id,
            first_action_id=int(event["action_id"]),
            last_action_id=int(event["action_id"]),
            first_source_row_number=int(event["source_row_number"]),
            last_source_row_number=int(event["source_row_number"]),
            start_seconds_remaining_in_period=float(
                event["seconds_remaining_in_period"]
            ),
            end_seconds_remaining_in_period=float(
                event["seconds_remaining_in_period"]
            ),
            start_home_score=start_home_score,
            start_away_score=start_away_score,
            end_home_score=int(event["home_score"]),
            end_away_score=int(event["away_score"]),
            start_reason=start_reason,
            ambiguity_reason=ambiguity_reason,
        )
        builder.include(event)
        return builder

    def include(self, event: Mapping[str, object]) -> None:
        if str(event["game_id"]) != self.game_id:
            raise ValueError("A possession cannot span games")
        if int(event["period"]) != self.period:
            raise ValueError("A possession cannot span periods")
        self.last_action_id = int(event["action_id"])
        self.last_source_row_number = int(event["source_row_number"])
        self.end_seconds_remaining_in_period = float(
            event["seconds_remaining_in_period"]
        )
        self.end_home_score = int(event["home_score"])
        self.end_away_score = int(event["away_score"])
        self.contains_timeout = self.contains_timeout or event["event_type"] == "timeout"
        self.contains_review = self.contains_review or event["event_type"] == "review"
        self.contains_score_revision = self.contains_score_revision or bool(
            event["score_update_is_revision"]
        )
        if bool(event.get("score_update_is_unexplained", False)):
            self.ambiguity_reason = (
                self.ambiguity_reason or "unexplained_score_change"
            )

    def finish(
        self,
        *,
        end_reason: str,
        is_censored: bool,
        ambiguity_reason: str | None = None,
    ) -> dict[str, object]:
        reason = self.ambiguity_reason or ambiguity_reason
        home_points = self.end_home_score - self.start_home_score
        away_points = self.end_away_score - self.start_away_score
        if home_points < 0 or away_points < 0:
            reason = reason or "unexplained_score_change"

        if reason is not None:
            status = "ambiguous"
        elif is_censored:
            status = "censored"
        else:
            status = "complete"

        if self.offense.team_id == self.defense.team_id:
            raise ValueError("Offense and defense must differ")
        offense_points = (
            home_points if self.offense_is_home else away_points
        )
        defense_points = (
            away_points if self.offense_is_home else home_points
        )

        return {
            "game_id": self.game_id,
            "season": self.season,
            "season_start_year": self.season_start_year,
            "game_type": self.game_type,
            "game_date": self.game_date,
            "possession_number": self.possession_number,
            "period": self.period,
            "first_action_id": self.first_action_id,
            "last_action_id": self.last_action_id,
            "first_source_row_number": self.first_source_row_number,
            "last_source_row_number": self.last_source_row_number,
            "offense_team_id": self.offense.team_id,
            "offense_team_code": self.offense.code,
            "defense_team_id": self.defense.team_id,
            "defense_team_code": self.defense.code,
            "start_seconds_remaining_in_period": (
                self.start_seconds_remaining_in_period
            ),
            "end_seconds_remaining_in_period": self.end_seconds_remaining_in_period,
            "start_home_score": self.start_home_score,
            "start_away_score": self.start_away_score,
            "end_home_score": self.end_home_score,
            "end_away_score": self.end_away_score,
            "offense_points": offense_points if reason is None else None,
            "defense_points": defense_points if reason is None else None,
            "duration_seconds": max(
                0.0,
                self.start_seconds_remaining_in_period
                - self.end_seconds_remaining_in_period,
            ),
            "possession_status": status,
            "start_reason": self.start_reason,
            "end_reason": end_reason,
            "is_censored_at_period_end": is_censored,
            "contains_timeout": self.contains_timeout,
            "contains_review": self.contains_review,
            "contains_score_revision": self.contains_score_revision,
            "possession_is_ambiguous": reason is not None,
            "ambiguity_reason": reason,
        }
