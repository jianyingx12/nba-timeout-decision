"""Classify ordinary possession boundaries."""

from dataclasses import dataclass
from typing import Mapping

from .free_throws import FreeThrowAttempt
from .ownership import GameTeams


@dataclass(frozen=True)
class BoundaryDecision:
    ends_possession: bool
    end_reason: str | None = None
    next_offense_team_id: int | None = None
    next_start_reason: str | None = None
    is_censored: bool = False
    ambiguity_reason: str | None = None


NO_BOUNDARY = BoundaryDecision(ends_possession=False)


def ordinary_boundary(
    event: Mapping[str, object],
    *,
    offense_team_id: int,
    teams: GameTeams,
) -> BoundaryDecision:
    event_type = event.get("event_type")
    event_subtype = event.get("event_subtype")
    event_team_id = event.get("event_team_id")

    if event_type == "period_marker" and event_subtype == "end":
        return BoundaryDecision(
            ends_possession=True,
            end_reason="period_end",
            is_censored=True,
        )

    if event_type == "made_shot":
        if event_team_id != offense_team_id:
            return BoundaryDecision(
                ends_possession=True,
                end_reason="unknown",
                ambiguity_reason="contradictory_team_control",
            )
        opponent = teams.opponent(offense_team_id)
        return BoundaryDecision(
            ends_possession=True,
            end_reason="made_field_goal",
            next_offense_team_id=opponent.team_id,
            next_start_reason="made_basket_inbound",
        )

    if event_type == "turnover":
        if event_team_id not in {None, offense_team_id}:
            return BoundaryDecision(
                ends_possession=True,
                end_reason="unknown",
                ambiguity_reason="contradictory_team_control",
            )
        opponent = teams.opponent(offense_team_id)
        return BoundaryDecision(
            ends_possession=True,
            end_reason="turnover",
            next_offense_team_id=opponent.team_id,
            next_start_reason="turnover",
        )

    if event_type == "rebound":
        if event_team_id is None:
            return BoundaryDecision(
                ends_possession=False,
                ambiguity_reason="missing_rebound_control",
            )
        if event_team_id == offense_team_id:
            return NO_BOUNDARY
        if not isinstance(event_team_id, int) or not teams.contains(event_team_id):
            return BoundaryDecision(
                ends_possession=True,
                end_reason="unknown",
                ambiguity_reason="contradictory_team_control",
            )
        return BoundaryDecision(
            ends_possession=True,
            end_reason="defensive_rebound",
            next_offense_team_id=event_team_id,
            next_start_reason="defensive_rebound",
        )

    return NO_BOUNDARY


def free_throw_boundary(
    attempt: FreeThrowAttempt,
    *,
    offense_team_id: int,
    teams: GameTeams,
    retained_team_id: int | None,
) -> BoundaryDecision:
    if attempt.is_technical or not attempt.is_final or not attempt.made:
        return NO_BOUNDARY
    if retained_team_id == attempt.team_id:
        return NO_BOUNDARY
    if attempt.team_id != offense_team_id:
        return BoundaryDecision(
            ends_possession=True,
            end_reason="unknown",
            ambiguity_reason="unresolved_free_throw_sequence",
        )
    opponent = teams.opponent(offense_team_id)
    return BoundaryDecision(
        ends_possession=True,
        end_reason="made_final_free_throw",
        next_offense_team_id=opponent.team_id,
        next_start_reason="made_free_throw_inbound",
    )
