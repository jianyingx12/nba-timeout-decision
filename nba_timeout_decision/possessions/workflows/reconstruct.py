"""Reconstruct one game's ordered possession sequence."""

from dataclasses import dataclass

import pyarrow as pa

from ..contract import POSSESSION_SCHEMA
from ..models import PossessionBuilder
from ..steps.boundaries import (
    BoundaryDecision,
    free_throw_boundary,
    ordinary_boundary,
)
from ..steps.free_throws import (
    is_and_one_made_shot,
    parse_free_throw,
    retained_possession_team_id,
)
from ..steps.ownership import carry_control, control_evidence, game_teams
from ..steps.reviews import review_follows_boundary


@dataclass(frozen=True)
class GameReconstruction:
    table: pa.Table
    ignored_event_count: int


def _apply_cross_boundary_revision(
    possessions: list[dict[str, object]], row: dict[str, object]
) -> None:
    if not possessions:
        return
    possession = possessions[-1]
    possession["last_action_id"] = int(row["action_id"])
    possession["last_source_row_number"] = int(row["source_row_number"])
    possession["end_seconds_remaining_in_period"] = float(
        row["seconds_remaining_in_period"]
    )
    possession["end_home_score"] = int(row["home_score"])
    possession["end_away_score"] = int(row["away_score"])
    possession["offense_points"] = None
    possession["defense_points"] = None
    possession["duration_seconds"] = max(
        0.0,
        float(possession["start_seconds_remaining_in_period"])
        - float(row["seconds_remaining_in_period"]),
    )
    possession["contains_review"] = (
        bool(possession["contains_review"]) or row["event_type"] == "review"
    )
    possession["contains_score_revision"] = True
    possession["possession_status"] = "ambiguous"
    possession["possession_is_ambiguous"] = True
    possession["ambiguity_reason"] = (
        possession["ambiguity_reason"] or "score_revision_crosses_boundary"
    )


def reconstruct_game(events: pa.Table) -> GameReconstruction:
    if events.num_rows == 0:
        return GameReconstruction(
            table=pa.Table.from_pylist([], schema=POSSESSION_SCHEMA),
            ignored_event_count=0,
        )

    rows = events.to_pylist()
    game_ids = {str(row["game_id"]) for row in rows}
    if len(game_ids) != 1:
        raise ValueError("Possession reconstruction accepts exactly one game")

    teams = game_teams(events)
    possessions: list[dict[str, object]] = []
    active: PossessionBuilder | None = None
    pending_team_id: int | None = None
    pending_start_reason = "period_start"
    retained_team_id: int | None = None
    pending_review_boundary: BoundaryDecision | None = None
    unresolved_team_rebound = False
    unresolved_jump_ball = False
    pending_period_end = False
    previous_home_score = int(rows[0]["home_score"])
    previous_away_score = int(rows[0]["away_score"])
    ignored_event_count = 0

    and_one_indices = {
        index
        for index, row in enumerate(rows)
        if row["event_type"] == "made_shot"
        and is_and_one_made_shot(rows, index)
    }

    for index, row in enumerate(rows):
        if row["event_type"] == "period_marker" and row["event_subtype"] == "start":
            if active is not None:
                if not pending_period_end:
                    raise ValueError("Period started before the prior possession ended")
                possessions.append(
                    active.finish(end_reason="period_end", is_censored=True)
                )
                active = None
            pending_team_id = None
            pending_start_reason = "period_start"
            retained_team_id = None
            pending_review_boundary = None
            unresolved_team_rebound = False
            unresolved_jump_ball = False
            pending_period_end = False
            previous_home_score = int(row["home_score"])
            previous_away_score = int(row["away_score"])
            continue

        if row["event_type"] == "period_marker" and row["event_subtype"] == "end":
            if active is None:
                ignored_event_count += 1
            else:
                active.include(row)
            pending_period_end = True
            previous_home_score = int(row["home_score"])
            previous_away_score = int(row["away_score"])
            continue

        if active is None and bool(row["score_update_is_revision"]):
            _apply_cross_boundary_revision(possessions, row)
            ignored_event_count += 1
            previous_home_score = int(row["home_score"])
            previous_away_score = int(row["away_score"])
            continue

        if pending_period_end:
            if active is None or int(row["period"]) != active.period:
                ignored_event_count += 1
            else:
                active.include(row)
            previous_home_score = int(row["home_score"])
            previous_away_score = int(row["away_score"])
            continue

        if row["event_type"] == "foul":
            awarded_team_id = retained_possession_team_id(row, teams)
            if awarded_team_id is not None:
                retained_team_id = awarded_team_id
                if active is None and pending_team_id != awarded_team_id:
                    pending_team_id = awarded_team_id
                    pending_start_reason = "unknown"

        free_throw_attempt = (
            parse_free_throw(row) if row["event_type"] == "free_throw" else None
        )

        evidence = control_evidence(row, teams)
        evidence_team_id = carry_control(None, evidence)
        if (
            evidence.kind == "offense_action"
            and evidence.team_id is None
        ):
            if active is not None:
                evidence_team_id = active.offense.team_id
            elif pending_team_id is not None:
                evidence_team_id = pending_team_id
        if (
            active is not None
            and pending_review_boundary is not None
            and evidence_team_id is not None
        ):
            expected_team_id = pending_review_boundary.next_offense_team_id
            if evidence_team_id == active.offense.team_id:
                pending_review_boundary = None
            elif evidence_team_id == expected_team_id:
                possessions.append(
                    active.finish(
                        end_reason=pending_review_boundary.end_reason or "unknown",
                        is_censored=pending_review_boundary.is_censored,
                        ambiguity_reason=pending_review_boundary.ambiguity_reason,
                    )
                )
                active = None
                pending_team_id = evidence_team_id
                pending_start_reason = (
                    pending_review_boundary.next_start_reason or "unknown"
                )
                retained_team_id = None
                unresolved_team_rebound = False
                unresolved_jump_ball = False
                pending_review_boundary = None
            else:
                possessions.append(
                    active.finish(
                        end_reason="unknown",
                        is_censored=False,
                        ambiguity_reason="unresolved_review",
                    )
                )
                active = None
                pending_team_id = evidence_team_id
                pending_start_reason = "unknown"
                retained_team_id = None
                unresolved_team_rebound = False
                unresolved_jump_ball = False
                pending_review_boundary = None
        if (
            active is not None
            and unresolved_jump_ball
            and evidence_team_id is not None
        ):
            if evidence_team_id != active.offense.team_id:
                possessions.append(
                    active.finish(
                        end_reason="jump_ball_change",
                        is_censored=False,
                    )
                )
                active = None
                pending_team_id = evidence_team_id
                pending_start_reason = "jump_ball_control"
                retained_team_id = None
                unresolved_team_rebound = False
            unresolved_jump_ball = False
        if (
            active is not None
            and unresolved_team_rebound
            and evidence_team_id is not None
        ):
            if evidence_team_id != active.offense.team_id:
                possessions.append(
                    active.finish(
                        end_reason="defensive_rebound",
                        is_censored=False,
                    )
                )
                active = None
                pending_team_id = evidence_team_id
                pending_start_reason = "defensive_rebound"
            unresolved_team_rebound = False

        if active is None:
            if evidence_team_id is None:
                if (
                    free_throw_attempt is not None
                    and free_throw_attempt.is_final
                    and retained_team_id == free_throw_attempt.team_id
                ):
                    retained_team_id = None
                ignored_event_count += 1
                previous_home_score = int(row["home_score"])
                previous_away_score = int(row["away_score"])
                continue

            ambiguity_reason = None
            if pending_team_id is not None and evidence_team_id != pending_team_id:
                ambiguity_reason = "contradictory_team_control"
            active = PossessionBuilder.start(
                row,
                possession_number=len(possessions) + 1,
                offense=teams.team(evidence_team_id),
                teams=teams,
                start_reason=(
                    pending_start_reason if ambiguity_reason is None else "unknown"
                ),
                start_home_score=previous_home_score,
                start_away_score=previous_away_score,
                ambiguity_reason=ambiguity_reason,
            )
        else:
            active.include(row)

        if row["event_type"] == "jump_ball" and active is not None:
            unresolved_jump_ball = True

        if row["event_type"] == "free_throw":
            assert free_throw_attempt is not None
            attempt = free_throw_attempt
            decision = free_throw_boundary(
                attempt,
                offense_team_id=active.offense.team_id,
                teams=teams,
                retained_team_id=retained_team_id,
            )
            if (
                attempt.is_final
                and retained_team_id is not None
                and attempt.team_id == retained_team_id
            ):
                retained_team_id = None
        elif row["event_type"] == "made_shot" and index in and_one_indices:
            decision = ordinary_boundary(
                {"event_type": "other"},
                offense_team_id=active.offense.team_id,
                teams=teams,
            )
        else:
            decision = ordinary_boundary(
                row,
                offense_team_id=active.offense.team_id,
                teams=teams,
            )
        if (
            row["event_type"] == "rebound"
            and row["event_team_id"] is None
            and decision.ambiguity_reason == "missing_rebound_control"
        ):
            unresolved_team_rebound = True
        if decision.ends_possession:
            if row["event_type"] == "period_marker":
                unresolved_team_rebound = False
            if (
                row["event_type"] != "period_marker"
                and review_follows_boundary(rows, index)
            ):
                pending_review_boundary = decision
            else:
                possessions.append(
                    active.finish(
                        end_reason=decision.end_reason or "unknown",
                        is_censored=decision.is_censored,
                        ambiguity_reason=(
                            "missing_rebound_control"
                            if unresolved_team_rebound
                            else (
                                "unresolved_jump_ball"
                                if unresolved_jump_ball
                                else decision.ambiguity_reason
                            )
                        ),
                    )
                )
                active = None
                retained_team_id = None
                unresolved_team_rebound = False
                unresolved_jump_ball = False
                pending_review_boundary = None
                pending_team_id = decision.next_offense_team_id
                pending_start_reason = decision.next_start_reason or "period_start"

        previous_home_score = int(row["home_score"])
        previous_away_score = int(row["away_score"])

    if active is not None:
        possessions.append(
            active.finish(
                end_reason="period_end" if pending_period_end else "unknown",
                is_censored=pending_period_end,
                ambiguity_reason=(
                    None
                    if pending_period_end
                    else (
                        "unresolved_review"
                        if pending_review_boundary is not None
                        else (
                            "missing_rebound_control"
                            if unresolved_team_rebound
                            else (
                                "unresolved_jump_ball"
                                if unresolved_jump_ball
                                else "missing_terminal_event"
                            )
                        )
                    )
                ),
            )
        )

    return GameReconstruction(
        table=pa.Table.from_pylist(possessions, schema=POSSESSION_SCHEMA),
        ignored_event_count=ignored_event_count,
    )
