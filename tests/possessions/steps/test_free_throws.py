"""Tests for free-throw parsing and penalty context."""

import unittest

from nba_timeout_decision.possessions.steps.free_throws import (
    FreeThrowAttempt,
    foul_awards_retained_possession,
    is_and_one_made_shot,
    parse_free_throw,
    retained_possession_team_id,
)
from nba_timeout_decision.possessions.steps.ownership import GameTeams, Team


class FreeThrowTests(unittest.TestCase):
    def test_parses_ordinary_attempts(self) -> None:
        attempt = parse_free_throw(
            {
                "event_type": "free_throw",
                "event_subtype": "Free Throw 2 of 2",
                "event_team_id": 10,
                "shot_result": "Made",
            }
        )

        self.assertEqual(attempt, FreeThrowAttempt(2, 2, "ordinary", 10, True))
        self.assertTrue(attempt.is_final)
        self.assertFalse(attempt.awards_retained_possession)

    def test_parses_numbered_special_penalties(self) -> None:
        flagrant = parse_free_throw(
            {
                "event_type": "free_throw",
                "event_subtype": "Free Throw Flagrant 1 of 2",
                "event_team_id": 20,
                "shot_result": "Missed",
            }
        )
        clear_path = parse_free_throw(
            {
                "event_type": "free_throw",
                "event_subtype": "Free Throw Clear Path 2 of 2",
                "event_team_id": 20,
                "shot_result": "Made",
            }
        )

        self.assertEqual(flagrant.penalty, "flagrant")
        self.assertTrue(flagrant.awards_retained_possession)
        self.assertEqual(clear_path.penalty, "clear_path")
        self.assertTrue(clear_path.is_final)

    def test_unnumbered_technical_is_one_attempt(self) -> None:
        attempt = parse_free_throw(
            {
                "event_type": "free_throw",
                "event_subtype": "Free Throw Technical",
                "event_team_id": 10,
                "description": "MISS Player Free Throw Technical",
            }
        )

        self.assertEqual(attempt, FreeThrowAttempt(1, 1, "technical", 10, False))
        self.assertTrue(attempt.is_technical)

    def test_uses_description_only_when_result_field_is_missing(self) -> None:
        attempt = parse_free_throw(
            {
                "event_type": "free_throw",
                "event_subtype": "Free Throw 1 of 1",
                "event_team_id": 10,
                "description": "Player Free Throw 1 of 1 (10 PTS)",
            }
        )

        self.assertTrue(attempt.made)

    def test_rejects_malformed_attempts(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported free-throw subtype"):
            parse_free_throw(
                {
                    "event_type": "free_throw",
                    "event_subtype": "Free Throw Unknown",
                }
            )
        with self.assertRaisesRegex(ValueError, "attempt exceeds total"):
            parse_free_throw(
                {
                    "event_type": "free_throw",
                    "event_subtype": "Free Throw 3 of 2",
                    "description": "Player Free Throw 3 of 2",
                }
            )

    def test_identifies_fouls_that_retain_possession(self) -> None:
        for subtype in (
            "Defense 3 Second",
            "Flagrant Type 1",
            "Clear Path",
            "Transition Take",
            "Away From Play",
        ):
            self.assertTrue(foul_awards_retained_possession(subtype))
        self.assertFalse(foul_awards_retained_possession("Shooting"))
        self.assertFalse(foul_awards_retained_possession("Personal Take"))

    def test_identifies_team_awarded_possession_after_special_foul(self) -> None:
        teams = GameTeams(home=Team(10, "HOM"), away=Team(20, "AWY"))
        self.assertEqual(
            retained_possession_team_id(
                {"event_subtype": "Clear Path", "event_team_id": 20}, teams
            ),
            10,
        )
        self.assertIsNone(
            retained_possession_team_id(
                {"event_subtype": "Shooting", "event_team_id": 20}, teams
            )
        )

    def test_detects_and_one_with_intervening_substitution(self) -> None:
        events = [
            {
                "event_type": "made_shot",
                "event_team_id": 10,
                "period": 1,
                "seconds_remaining_in_period": 600.0,
            },
            {
                "event_type": "foul",
                "event_subtype": "Shooting",
                "event_team_id": 20,
                "period": 1,
                "seconds_remaining_in_period": 600.0,
            },
            {
                "event_type": "substitution",
                "period": 1,
                "seconds_remaining_in_period": 600.0,
            },
            {
                "event_type": "free_throw",
                "event_subtype": "Free Throw 1 of 1",
                "event_team_id": 10,
                "shot_result": "Made",
                "period": 1,
                "seconds_remaining_in_period": 600.0,
            },
        ]

        self.assertTrue(is_and_one_made_shot(events, 0))

    def test_detects_and_one_recorded_as_personal_foul(self) -> None:
        events = [
            {
                "event_type": "made_shot",
                "event_team_id": 10,
                "period": 1,
                "seconds_remaining_in_period": 600.0,
            },
            {
                "event_type": "foul",
                "event_subtype": "Personal",
                "event_team_id": 20,
                "period": 1,
                "seconds_remaining_in_period": 600.0,
            },
            {
                "event_type": "free_throw",
                "event_subtype": "Free Throw 1 of 1",
                "event_team_id": 10,
                "shot_result": "Made",
                "period": 1,
                "seconds_remaining_in_period": 600.0,
            },
        ]

        self.assertTrue(is_and_one_made_shot(events, 0))

    def test_does_not_treat_unrelated_single_free_throw_as_and_one(self) -> None:
        events = [
            {
                "event_type": "made_shot",
                "event_team_id": 10,
                "period": 1,
                "seconds_remaining_in_period": 600.0,
            },
            {
                "event_type": "foul",
                "event_subtype": "Away From Play",
                "event_team_id": 10,
                "period": 1,
                "seconds_remaining_in_period": 600.0,
            },
            {
                "event_type": "free_throw",
                "event_subtype": "Free Throw 1 of 1",
                "event_team_id": 20,
                "shot_result": "Made",
                "period": 1,
                "seconds_remaining_in_period": 600.0,
            },
        ]

        self.assertFalse(is_and_one_made_shot(events, 0))


if __name__ == "__main__":
    unittest.main()
