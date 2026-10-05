"""Tests for ordinary possession boundaries."""

import unittest

from nba_timeout_decision.possessions.steps.boundaries import (
    NO_BOUNDARY,
    free_throw_boundary,
    ordinary_boundary,
)
from nba_timeout_decision.possessions.steps.free_throws import FreeThrowAttempt
from nba_timeout_decision.possessions.steps.ownership import GameTeams, Team


TEAMS = GameTeams(home=Team(10, "HOM"), away=Team(20, "AWY"))


class OrdinaryBoundaryTests(unittest.TestCase):
    def test_made_shot_ends_with_opponent_inbound(self) -> None:
        decision = ordinary_boundary(
            {"event_type": "made_shot", "event_team_id": 10},
            offense_team_id=10,
            teams=TEAMS,
        )

        self.assertTrue(decision.ends_possession)
        self.assertEqual(decision.end_reason, "made_field_goal")
        self.assertEqual(decision.next_offense_team_id, 20)
        self.assertEqual(decision.next_start_reason, "made_basket_inbound")

    def test_turnover_ends_with_opponent_control(self) -> None:
        decision = ordinary_boundary(
            {"event_type": "turnover", "event_team_id": 20},
            offense_team_id=20,
            teams=TEAMS,
        )

        self.assertEqual(decision.end_reason, "turnover")
        self.assertEqual(decision.next_offense_team_id, 10)
        self.assertEqual(decision.next_start_reason, "turnover")

    def test_teamless_turnover_is_attributed_to_current_offense(self) -> None:
        decision = ordinary_boundary(
            {"event_type": "turnover", "event_team_id": None},
            offense_team_id=20,
            teams=TEAMS,
        )

        self.assertEqual(decision.end_reason, "turnover")
        self.assertEqual(decision.next_offense_team_id, 10)

    def test_offensive_rebound_continues_possession(self) -> None:
        decision = ordinary_boundary(
            {"event_type": "rebound", "event_team_id": 10},
            offense_team_id=10,
            teams=TEAMS,
        )

        self.assertEqual(decision, NO_BOUNDARY)

    def test_defensive_rebound_changes_control(self) -> None:
        decision = ordinary_boundary(
            {"event_type": "rebound", "event_team_id": 20},
            offense_team_id=10,
            teams=TEAMS,
        )

        self.assertEqual(decision.end_reason, "defensive_rebound")
        self.assertEqual(decision.next_offense_team_id, 20)
        self.assertEqual(decision.next_start_reason, "defensive_rebound")

    def test_team_rebound_waits_for_later_control_evidence(self) -> None:
        decision = ordinary_boundary(
            {"event_type": "rebound", "event_team_id": None},
            offense_team_id=10,
            teams=TEAMS,
        )

        self.assertFalse(decision.ends_possession)
        self.assertEqual(decision.ambiguity_reason, "missing_rebound_control")

    def test_period_end_censors_open_possession(self) -> None:
        decision = ordinary_boundary(
            {"event_type": "period_marker", "event_subtype": "end"},
            offense_team_id=20,
            teams=TEAMS,
        )

        self.assertTrue(decision.ends_possession)
        self.assertEqual(decision.end_reason, "period_end")
        self.assertTrue(decision.is_censored)
        self.assertIsNone(decision.next_offense_team_id)

    def test_contradictory_terminal_event_is_ambiguous(self) -> None:
        decision = ordinary_boundary(
            {"event_type": "turnover", "event_team_id": 20},
            offense_team_id=10,
            teams=TEAMS,
        )

        self.assertTrue(decision.ends_possession)
        self.assertEqual(decision.end_reason, "unknown")
        self.assertEqual(decision.ambiguity_reason, "contradictory_team_control")

    def test_final_made_free_throw_ends_ordinary_sequence(self) -> None:
        decision = free_throw_boundary(
            FreeThrowAttempt(2, 2, "ordinary", 10, True),
            offense_team_id=10,
            teams=TEAMS,
            retained_team_id=None,
        )

        self.assertEqual(decision.end_reason, "made_final_free_throw")
        self.assertEqual(decision.next_offense_team_id, 20)
        self.assertEqual(decision.next_start_reason, "made_free_throw_inbound")

    def test_missed_or_retained_final_attempt_does_not_end_possession(self) -> None:
        missed = free_throw_boundary(
            FreeThrowAttempt(2, 2, "ordinary", 10, False),
            offense_team_id=10,
            teams=TEAMS,
            retained_team_id=None,
        )
        retained = free_throw_boundary(
            FreeThrowAttempt(1, 1, "ordinary", 10, True),
            offense_team_id=10,
            teams=TEAMS,
            retained_team_id=10,
        )

        self.assertEqual(missed, NO_BOUNDARY)
        self.assertEqual(retained, NO_BOUNDARY)

    def test_technical_attempt_does_not_end_current_possession(self) -> None:
        decision = free_throw_boundary(
            FreeThrowAttempt(1, 1, "technical", 20, True),
            offense_team_id=10,
            teams=TEAMS,
            retained_team_id=None,
        )

        self.assertEqual(decision, NO_BOUNDARY)


if __name__ == "__main__":
    unittest.main()
