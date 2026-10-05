"""Tests for game possession reconstruction."""

import unittest
from datetime import date

import pyarrow as pa

from nba_timeout_decision.possessions.workflows.reconstruct import (
    reconstruct_game,
)


def event(
    action_id: int,
    *,
    event_type: str,
    team_id: int | None,
    team_code: str | None,
    team_role: str | None,
    seconds: float,
    home_score: int,
    away_score: int,
    event_subtype: str | None = None,
    shot_result: str | None = None,
    score_revision: bool = False,
    unexplained_score: bool = False,
) -> dict[str, object]:
    return {
        "game_id": "0000000001",
        "season": "2025-26",
        "season_start_year": 2025,
        "game_type": "regular",
        "game_date": date(2025, 10, 21),
        "source_row_number": action_id - 1,
        "action_id": action_id,
        "period": 1,
        "seconds_remaining_in_period": seconds,
        "event_team_id": team_id,
        "event_team_code": team_code,
        "event_team_role": team_role,
        "action_type": None,
        "event_type": event_type,
        "event_subtype": event_subtype,
        "shot_result": shot_result,
        "description": None,
        "home_score": home_score,
        "away_score": away_score,
        "score_update_is_unexplained": unexplained_score,
        "score_update_is_revision": score_revision,
    }


class GameReconstructionTests(unittest.TestCase):
    def test_between_possession_technical_clears_retained_context(self) -> None:
        events = pa.Table.from_pylist(
            [
                event(
                    1,
                    event_type="missed_shot",
                    team_id=10,
                    team_code="HOM",
                    team_role="home",
                    seconds=100,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    2,
                    event_type="rebound",
                    team_id=20,
                    team_code="AWY",
                    team_role="away",
                    seconds=98,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    3,
                    event_type="foul",
                    event_subtype="Defense 3 Second",
                    team_id=10,
                    team_code="HOM",
                    team_role="home",
                    seconds=90,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    4,
                    event_type="free_throw",
                    event_subtype="Free Throw Technical",
                    team_id=20,
                    team_code="AWY",
                    team_role="away",
                    seconds=90,
                    home_score=0,
                    away_score=0,
                    shot_result="Missed",
                ),
                event(
                    5,
                    event_type="foul",
                    event_subtype="Shooting",
                    team_id=10,
                    team_code="HOM",
                    team_role="home",
                    seconds=80,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    6,
                    event_type="free_throw",
                    event_subtype="Free Throw 1 of 2",
                    team_id=20,
                    team_code="AWY",
                    team_role="away",
                    seconds=80,
                    home_score=0,
                    away_score=1,
                    shot_result="Made",
                ),
                event(
                    7,
                    event_type="free_throw",
                    event_subtype="Free Throw 2 of 2",
                    team_id=20,
                    team_code="AWY",
                    team_role="away",
                    seconds=80,
                    home_score=0,
                    away_score=2,
                    shot_result="Made",
                ),
            ]
        )

        rows = reconstruct_game(events).table.to_pylist()

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["first_action_id"], 6)
        self.assertEqual(rows[1]["end_reason"], "made_final_free_throw")
        self.assertFalse(rows[1]["possession_is_ambiguous"])

    def test_keeps_late_zero_clock_events_in_closing_possession(self) -> None:
        events = pa.Table.from_pylist(
            [
                event(
                    1,
                    event_type="substitution",
                    team_id=20,
                    team_code="AWY",
                    team_role="away",
                    seconds=10,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    2,
                    event_type="missed_shot",
                    team_id=10,
                    team_code="HOM",
                    team_role="home",
                    seconds=1,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    3,
                    event_type="period_marker",
                    event_subtype="end",
                    team_id=None,
                    team_code=None,
                    team_role=None,
                    seconds=0,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    4,
                    event_type="rebound",
                    team_id=None,
                    team_code=None,
                    team_role=None,
                    seconds=0,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    5,
                    event_type="free_throw",
                    event_subtype="Free Throw Technical",
                    team_id=20,
                    team_code="AWY",
                    team_role="away",
                    seconds=720,
                    home_score=0,
                    away_score=1,
                ),
                event(
                    6,
                    event_type="period_marker",
                    event_subtype="start",
                    team_id=None,
                    team_code=None,
                    team_role=None,
                    seconds=720,
                    home_score=0,
                    away_score=1,
                ),
                event(
                    7,
                    event_type="turnover",
                    team_id=20,
                    team_code="AWY",
                    team_role="away",
                    seconds=700,
                    home_score=0,
                    away_score=1,
                ),
            ]
        )
        events = events.set_column(
            events.schema.get_field_index("period"),
            "period",
            pa.array([1, 1, 1, 1, 2, 2, 2]),
        )

        rows = reconstruct_game(events).table.to_pylist()

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["end_reason"], "period_end")
        self.assertEqual(rows[0]["last_action_id"], 4)
        self.assertEqual(rows[0]["possession_status"], "censored")
        self.assertEqual(rows[1]["start_reason"], "period_start")
        self.assertEqual(rows[1]["start_away_score"], 1)

    def test_jump_ball_changes_possession_after_opponent_control(self) -> None:
        events = pa.Table.from_pylist(
            [
                event(
                    1,
                    event_type="missed_shot",
                    team_id=10,
                    team_code="HOM",
                    team_role="home",
                    seconds=100,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    2,
                    event_type="jump_ball",
                    team_id=None,
                    team_code=None,
                    team_role=None,
                    seconds=95,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    3,
                    event_type="turnover",
                    team_id=20,
                    team_code="AWY",
                    team_role="away",
                    seconds=90,
                    home_score=0,
                    away_score=0,
                ),
            ]
        )

        rows = reconstruct_game(events).table.to_pylist()

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["end_reason"], "jump_ball_change")
        self.assertEqual(rows[0]["last_action_id"], 2)
        self.assertEqual(rows[1]["start_reason"], "jump_ball_control")
        self.assertEqual(rows[1]["first_action_id"], 3)

    def test_jump_ball_retention_does_not_split_possession(self) -> None:
        events = pa.Table.from_pylist(
            [
                event(
                    1,
                    event_type="substitution",
                    team_id=20,
                    team_code="AWY",
                    team_role="away",
                    seconds=105,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    2,
                    event_type="missed_shot",
                    team_id=10,
                    team_code="HOM",
                    team_role="home",
                    seconds=100,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    3,
                    event_type="jump_ball",
                    team_id=None,
                    team_code=None,
                    team_role=None,
                    seconds=95,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    4,
                    event_type="made_shot",
                    team_id=10,
                    team_code="HOM",
                    team_role="home",
                    seconds=90,
                    home_score=2,
                    away_score=0,
                ),
            ]
        )

        rows = reconstruct_game(events).table.to_pylist()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["first_action_id"], 2)
        self.assertEqual(rows[0]["last_action_id"], 4)
        self.assertEqual(rows[0]["end_reason"], "made_field_goal")

    def test_unresolved_jump_ball_is_ambiguous(self) -> None:
        events = pa.Table.from_pylist(
            [
                event(
                    1,
                    event_type="substitution",
                    team_id=20,
                    team_code="AWY",
                    team_role="away",
                    seconds=105,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    2,
                    event_type="missed_shot",
                    team_id=10,
                    team_code="HOM",
                    team_role="home",
                    seconds=100,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    3,
                    event_type="jump_ball",
                    team_id=None,
                    team_code=None,
                    team_role=None,
                    seconds=95,
                    home_score=0,
                    away_score=0,
                ),
            ]
        )

        row = reconstruct_game(events).table.to_pylist()[0]

        self.assertEqual(row["possession_status"], "ambiguous")
        self.assertEqual(row["ambiguity_reason"], "unresolved_jump_ball")

    def test_reconstructs_made_shot_turnover_and_period_end(self) -> None:
        events = pa.Table.from_pylist(
            [
                event(
                    1,
                    event_type="period_marker",
                    event_subtype="start",
                    team_id=None,
                    team_code=None,
                    team_role=None,
                    seconds=720,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    2,
                    event_type="made_shot",
                    team_id=10,
                    team_code="HOM",
                    team_role="home",
                    seconds=700,
                    home_score=2,
                    away_score=0,
                ),
                event(
                    3,
                    event_type="turnover",
                    team_id=20,
                    team_code="AWY",
                    team_role="away",
                    seconds=680,
                    home_score=2,
                    away_score=0,
                ),
                event(
                    4,
                    event_type="missed_shot",
                    team_id=10,
                    team_code="HOM",
                    team_role="home",
                    seconds=660,
                    home_score=2,
                    away_score=0,
                ),
                event(
                    5,
                    event_type="rebound",
                    team_id=10,
                    team_code="HOM",
                    team_role="home",
                    seconds=658,
                    home_score=2,
                    away_score=0,
                ),
                event(
                    6,
                    event_type="period_marker",
                    event_subtype="end",
                    team_id=None,
                    team_code=None,
                    team_role=None,
                    seconds=0,
                    home_score=2,
                    away_score=0,
                ),
            ]
        )

        rows = reconstruct_game(events).table.to_pylist()

        self.assertEqual(len(rows), 3)
        self.assertEqual(
            [(row["offense_team_code"], row["end_reason"]) for row in rows],
            [
                ("HOM", "made_field_goal"),
                ("AWY", "turnover"),
                ("HOM", "period_end"),
            ],
        )
        self.assertEqual(rows[0]["offense_points"], 2)
        self.assertEqual(rows[1]["start_reason"], "made_basket_inbound")
        self.assertEqual(rows[2]["start_reason"], "turnover")
        self.assertEqual(rows[2]["possession_status"], "censored")

    def test_defensive_rebound_ends_one_possession_and_starts_the_next(self) -> None:
        events = pa.Table.from_pylist(
            [
                event(
                    1,
                    event_type="missed_shot",
                    team_id=20,
                    team_code="AWY",
                    team_role="away",
                    seconds=100,
                    home_score=5,
                    away_score=4,
                ),
                event(
                    2,
                    event_type="rebound",
                    team_id=10,
                    team_code="HOM",
                    team_role="home",
                    seconds=98,
                    home_score=5,
                    away_score=4,
                ),
                event(
                    3,
                    event_type="made_shot",
                    team_id=10,
                    team_code="HOM",
                    team_role="home",
                    seconds=80,
                    home_score=7,
                    away_score=4,
                ),
            ]
        )

        rows = reconstruct_game(events).table.to_pylist()

        self.assertEqual(rows[0]["end_reason"], "defensive_rebound")
        self.assertEqual(rows[0]["last_action_id"], 2)
        self.assertEqual(rows[1]["start_reason"], "defensive_rebound")
        self.assertEqual(rows[1]["first_action_id"], 3)

    def test_groups_and_one_as_one_possession(self) -> None:
        events = pa.Table.from_pylist(
            [
                event(
                    1,
                    event_type="period_marker",
                    event_subtype="start",
                    team_id=None,
                    team_code=None,
                    team_role=None,
                    seconds=720,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    2,
                    event_type="made_shot",
                    team_id=10,
                    team_code="HOM",
                    team_role="home",
                    seconds=100,
                    home_score=2,
                    away_score=0,
                ),
                event(
                    3,
                    event_type="foul",
                    team_id=20,
                    team_code="AWY",
                    team_role="away",
                    seconds=100,
                    home_score=2,
                    away_score=0,
                    event_subtype="Shooting",
                ),
                event(
                    4,
                    event_type="free_throw",
                    team_id=10,
                    team_code="HOM",
                    team_role="home",
                    seconds=100,
                    home_score=3,
                    away_score=0,
                    event_subtype="Free Throw 1 of 1",
                    shot_result="Made",
                ),
            ]
        )

        rows = reconstruct_game(events).table.to_pylist()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["first_action_id"], 2)
        self.assertEqual(rows[0]["last_action_id"], 4)
        self.assertEqual(rows[0]["offense_points"], 3)
        self.assertEqual(rows[0]["end_reason"], "made_final_free_throw")

    def test_uses_next_control_to_resolve_team_rebound(self) -> None:
        events = pa.Table.from_pylist(
            [
                event(
                    1,
                    event_type="missed_shot",
                    team_id=10,
                    team_code="HOM",
                    team_role="home",
                    seconds=100,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    2,
                    event_type="rebound",
                    team_id=None,
                    team_code=None,
                    team_role=None,
                    seconds=98,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    3,
                    event_type="made_shot",
                    team_id=20,
                    team_code="AWY",
                    team_role="away",
                    seconds=80,
                    home_score=0,
                    away_score=2,
                ),
            ]
        )

        rows = reconstruct_game(events).table.to_pylist()

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["end_reason"], "defensive_rebound")
        self.assertFalse(rows[0]["possession_is_ambiguous"])
        self.assertEqual(rows[1]["start_reason"], "defensive_rebound")
        self.assertEqual(rows[1]["offense_team_code"], "AWY")

    def test_final_missed_free_throw_waits_for_rebound(self) -> None:
        events = pa.Table.from_pylist(
            [
                event(
                    1,
                    event_type="period_marker",
                    event_subtype="start",
                    team_id=None,
                    team_code=None,
                    team_role=None,
                    seconds=720,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    2,
                    event_type="foul",
                    event_subtype="Shooting",
                    team_id=20,
                    team_code="AWY",
                    team_role="away",
                    seconds=600,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    3,
                    event_type="free_throw",
                    event_subtype="Free Throw 1 of 2",
                    shot_result="Made",
                    team_id=10,
                    team_code="HOM",
                    team_role="home",
                    seconds=600,
                    home_score=1,
                    away_score=0,
                ),
                event(
                    4,
                    event_type="free_throw",
                    event_subtype="Free Throw 2 of 2",
                    shot_result="Missed",
                    team_id=10,
                    team_code="HOM",
                    team_role="home",
                    seconds=600,
                    home_score=1,
                    away_score=0,
                ),
                event(
                    5,
                    event_type="rebound",
                    team_id=20,
                    team_code="AWY",
                    team_role="away",
                    seconds=598,
                    home_score=1,
                    away_score=0,
                ),
            ]
        )

        rows = reconstruct_game(events).table.to_pylist()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["end_reason"], "defensive_rebound")
        self.assertEqual(rows[0]["offense_points"], 1)
        self.assertEqual(rows[0]["last_action_id"], 5)

    def test_technical_free_throw_does_not_change_current_offense(self) -> None:
        events = pa.Table.from_pylist(
            [
                event(
                    1,
                    event_type="period_marker",
                    event_subtype="start",
                    team_id=None,
                    team_code=None,
                    team_role=None,
                    seconds=720,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    2,
                    event_type="missed_shot",
                    team_id=10,
                    team_code="HOM",
                    team_role="home",
                    seconds=600,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    3,
                    event_type="foul",
                    event_subtype="Technical",
                    team_id=10,
                    team_code="HOM",
                    team_role="home",
                    seconds=600,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    4,
                    event_type="free_throw",
                    event_subtype="Free Throw Technical",
                    shot_result="Made",
                    team_id=20,
                    team_code="AWY",
                    team_role="away",
                    seconds=600,
                    home_score=0,
                    away_score=1,
                ),
                event(
                    5,
                    event_type="made_shot",
                    team_id=10,
                    team_code="HOM",
                    team_role="home",
                    seconds=580,
                    home_score=2,
                    away_score=1,
                ),
            ]
        )

        rows = reconstruct_game(events).table.to_pylist()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["offense_team_code"], "HOM")
        self.assertEqual(rows[0]["offense_points"], 2)
        self.assertEqual(rows[0]["defense_points"], 1)

    def test_clear_path_free_throws_and_retained_play_stay_together(self) -> None:
        events = pa.Table.from_pylist(
            [
                event(
                    1,
                    event_type="turnover",
                    team_id=20,
                    team_code="AWY",
                    team_role="away",
                    seconds=620,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    2,
                    event_type="foul",
                    event_subtype="Clear Path",
                    team_id=20,
                    team_code="AWY",
                    team_role="away",
                    seconds=620,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    3,
                    event_type="free_throw",
                    event_subtype="Free Throw Clear Path 1 of 2",
                    shot_result="Made",
                    team_id=10,
                    team_code="HOM",
                    team_role="home",
                    seconds=620,
                    home_score=1,
                    away_score=0,
                ),
                event(
                    4,
                    event_type="free_throw",
                    event_subtype="Free Throw Clear Path 2 of 2",
                    shot_result="Made",
                    team_id=10,
                    team_code="HOM",
                    team_role="home",
                    seconds=620,
                    home_score=2,
                    away_score=0,
                ),
                event(
                    5,
                    event_type="made_shot",
                    team_id=10,
                    team_code="HOM",
                    team_role="home",
                    seconds=600,
                    home_score=4,
                    away_score=0,
                ),
            ]
        )

        rows = reconstruct_game(events).table.to_pylist()

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["start_reason"], "turnover")
        self.assertEqual(rows[1]["first_action_id"], 3)
        self.assertEqual(rows[1]["last_action_id"], 5)
        self.assertEqual(rows[1]["offense_points"], 4)

    def test_upheld_review_confirms_deferred_turnover(self) -> None:
        events = pa.Table.from_pylist(
            [
                event(
                    1,
                    event_type="period_marker",
                    event_subtype="start",
                    team_id=None,
                    team_code=None,
                    team_role=None,
                    seconds=720,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    2,
                    event_type="turnover",
                    team_id=10,
                    team_code="HOM",
                    team_role="home",
                    seconds=600,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    3,
                    event_type="timeout",
                    team_id=None,
                    team_code=None,
                    team_role=None,
                    seconds=600,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    4,
                    event_type="review",
                    event_subtype="Coach Challenge Ruling Stands",
                    team_id=None,
                    team_code=None,
                    team_role=None,
                    seconds=600,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    5,
                    event_type="made_shot",
                    team_id=20,
                    team_code="AWY",
                    team_role="away",
                    seconds=580,
                    home_score=0,
                    away_score=2,
                ),
            ]
        )

        rows = reconstruct_game(events).table.to_pylist()

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["end_reason"], "turnover")
        self.assertEqual(rows[0]["last_action_id"], 4)
        self.assertTrue(rows[0]["contains_timeout"])
        self.assertTrue(rows[0]["contains_review"])

    def test_overturned_turnover_keeps_original_offense(self) -> None:
        events = pa.Table.from_pylist(
            [
                event(
                    1,
                    event_type="substitution",
                    team_id=20,
                    team_code="AWY",
                    team_role="away",
                    seconds=620,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    2,
                    event_type="missed_shot",
                    team_id=10,
                    team_code="HOM",
                    team_role="home",
                    seconds=620,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    3,
                    event_type="turnover",
                    team_id=10,
                    team_code="HOM",
                    team_role="home",
                    seconds=600,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    4,
                    event_type="timeout",
                    team_id=None,
                    team_code=None,
                    team_role=None,
                    seconds=600,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    5,
                    event_type="review",
                    event_subtype="Coach Challenge Overturn Ruling",
                    team_id=None,
                    team_code=None,
                    team_role=None,
                    seconds=600,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    6,
                    event_type="made_shot",
                    team_id=10,
                    team_code="HOM",
                    team_role="home",
                    seconds=580,
                    home_score=2,
                    away_score=0,
                ),
            ]
        )

        rows = reconstruct_game(events).table.to_pylist()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["first_action_id"], 2)
        self.assertEqual(rows[0]["last_action_id"], 6)
        self.assertEqual(rows[0]["end_reason"], "made_field_goal")
        self.assertTrue(rows[0]["contains_review"])

    def test_review_score_revision_is_applied_once(self) -> None:
        events = pa.Table.from_pylist(
            [
                event(
                    1,
                    event_type="period_marker",
                    event_subtype="start",
                    team_id=None,
                    team_code=None,
                    team_role=None,
                    seconds=720,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    2,
                    event_type="made_shot",
                    team_id=10,
                    team_code="HOM",
                    team_role="home",
                    seconds=600,
                    home_score=2,
                    away_score=0,
                ),
                event(
                    3,
                    event_type="review",
                    event_subtype="Support Ruling",
                    team_id=None,
                    team_code=None,
                    team_role=None,
                    seconds=600,
                    home_score=3,
                    away_score=0,
                    score_revision=True,
                ),
                event(
                    4,
                    event_type="made_shot",
                    team_id=20,
                    team_code="AWY",
                    team_role="away",
                    seconds=580,
                    home_score=3,
                    away_score=2,
                ),
            ]
        )

        rows = reconstruct_game(events).table.to_pylist()

        self.assertEqual(rows[0]["offense_points"], 3)
        self.assertTrue(rows[0]["contains_score_revision"])
        self.assertEqual(rows[1]["start_home_score"], 3)

    def test_review_can_revise_a_completed_possession(self) -> None:
        events = pa.Table.from_pylist(
            [
                event(
                    1,
                    event_type="substitution",
                    team_id=20,
                    team_code="AWY",
                    team_role="away",
                    seconds=610,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    2,
                    event_type="made_shot",
                    team_id=10,
                    team_code="HOM",
                    team_role="home",
                    seconds=600,
                    home_score=3,
                    away_score=0,
                ),
                event(
                    3,
                    event_type="review",
                    event_subtype="Overturn Ruling",
                    team_id=None,
                    team_code=None,
                    team_role=None,
                    seconds=590,
                    home_score=0,
                    away_score=0,
                    score_revision=True,
                ),
                event(
                    4,
                    event_type="turnover",
                    team_id=20,
                    team_code="AWY",
                    team_role="away",
                    seconds=580,
                    home_score=0,
                    away_score=0,
                ),
            ]
        )

        rows = reconstruct_game(events).table.to_pylist()

        self.assertEqual(rows[0]["last_action_id"], 3)
        self.assertEqual(rows[0]["end_home_score"], 0)
        self.assertTrue(rows[0]["contains_score_revision"])
        self.assertEqual(
            rows[0]["ambiguity_reason"], "score_revision_crosses_boundary"
        )
        self.assertEqual(rows[1]["start_home_score"], 0)

    def test_team_rebound_before_period_end_is_not_ambiguous(self) -> None:
        events = pa.Table.from_pylist(
            [
                event(
                    1,
                    event_type="missed_shot",
                    team_id=10,
                    team_code="HOM",
                    team_role="home",
                    seconds=1,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    2,
                    event_type="rebound",
                    team_id=None,
                    team_code=None,
                    team_role=None,
                    seconds=0,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    3,
                    event_type="period_marker",
                    event_subtype="end",
                    team_id=None,
                    team_code=None,
                    team_role=None,
                    seconds=0,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    4,
                    event_type="substitution",
                    team_id=20,
                    team_code="AWY",
                    team_role="away",
                    seconds=0,
                    home_score=0,
                    away_score=0,
                ),
            ]
        )

        rows = reconstruct_game(events).table.to_pylist()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["possession_status"], "censored")
        self.assertFalse(rows[0]["possession_is_ambiguous"])

    def test_teamless_turnover_uses_pending_offense(self) -> None:
        events = pa.Table.from_pylist(
            [
                event(
                    1,
                    event_type="missed_shot",
                    team_id=20,
                    team_code="AWY",
                    team_role="away",
                    seconds=100,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    2,
                    event_type="rebound",
                    team_id=10,
                    team_code="HOM",
                    team_role="home",
                    seconds=98,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    3,
                    event_type="turnover",
                    team_id=None,
                    team_code=None,
                    team_role=None,
                    seconds=80,
                    home_score=0,
                    away_score=0,
                ),
                event(
                    4,
                    event_type="made_shot",
                    team_id=20,
                    team_code="AWY",
                    team_role="away",
                    seconds=60,
                    home_score=0,
                    away_score=2,
                ),
            ]
        )

        rows = reconstruct_game(events).table.to_pylist()

        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[1]["offense_team_code"], "HOM")
        self.assertEqual(rows[1]["end_reason"], "turnover")
        self.assertFalse(rows[2]["possession_is_ambiguous"])


if __name__ == "__main__":
    unittest.main()
