"""Tests for possession ownership evidence."""

import unittest

import pyarrow as pa

from nba_timeout_decision.possessions.steps.ownership import (
    ControlEvidence,
    carry_control,
    control_evidence,
    game_teams,
)


def participant_table() -> pa.Table:
    return pa.table(
        {
            "event_team_role": ["home", "away", None],
            "event_team_id": [10, 20, None],
            "event_team_code": ["HOM", "AWY", None],
        }
    )


class OwnershipTests(unittest.TestCase):
    def test_maps_home_and_away_teams_symmetrically(self) -> None:
        teams = game_teams(participant_table())

        self.assertEqual((teams.home.team_id, teams.home.code), (10, "HOM"))
        self.assertEqual((teams.away.team_id, teams.away.code), (20, "AWY"))
        self.assertEqual(teams.opponent(10), teams.away)
        self.assertEqual(teams.opponent(20), teams.home)

    def test_rejects_conflicting_participant_identity(self) -> None:
        table = pa.table(
            {
                "event_team_role": ["home", "home", "away"],
                "event_team_id": [10, 11, 20],
                "event_team_code": ["HOM", "ALT", "AWY"],
            }
        )

        with self.assertRaisesRegex(ValueError, "Expected one home team"):
            game_teams(table)

    def test_classifies_direct_and_neutral_evidence(self) -> None:
        teams = game_teams(participant_table())

        shot = control_evidence(
            {"event_type": "made_shot", "event_team_id": 10}, teams
        )
        rebound = control_evidence(
            {"event_type": "rebound", "event_team_id": 20}, teams
        )
        timeout = control_evidence(
            {"event_type": "timeout", "event_team_id": None}, teams
        )

        self.assertEqual(shot, ControlEvidence(10, "offense_action"))
        self.assertEqual(rebound, ControlEvidence(20, "gained_control"))
        self.assertEqual(timeout, ControlEvidence(None, "none"))

    def test_technical_shooter_does_not_replace_current_control(self) -> None:
        teams = game_teams(participant_table())
        evidence = control_evidence(
            {
                "event_type": "free_throw",
                "event_subtype": "Free Throw Technical",
                "event_team_id": 20,
            },
            teams,
        )

        self.assertEqual(evidence, ControlEvidence(20, "penalty_shooter"))
        self.assertEqual(carry_control(10, evidence), 10)

    def test_supported_event_changes_control_and_neutral_event_carries_it(self) -> None:
        self.assertEqual(carry_control(10, ControlEvidence(None, "none")), 10)
        self.assertEqual(
            carry_control(10, ControlEvidence(None, "offense_action")), 10
        )
        self.assertEqual(carry_control(10, ControlEvidence(20, "gained_control")), 20)
        self.assertEqual(carry_control(None, ControlEvidence(10, "offense_action")), 10)

    def test_rejects_nonparticipant_event_team(self) -> None:
        teams = game_teams(participant_table())
        with self.assertRaisesRegex(ValueError, "Invalid event team ID"):
            control_evidence(
                {"event_type": "turnover", "event_team_id": 30}, teams
            )


if __name__ == "__main__":
    unittest.main()
