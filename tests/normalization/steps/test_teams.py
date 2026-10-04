"""Tests for team normalization."""

import unittest

import pyarrow as pa

from nba_timeout_decision.normalization.steps.teams import normalize_teams


class NormalizationTeamTests(unittest.TestCase):
    def test_assigns_team_roles_and_marks_teamless_events(self) -> None:
        table = pa.table(
            {
                "game_id": ["0022500001"] * 3,
                "event_team_id": [1610612760, 1610612745, None],
                "event_team_code": ["OKC", "HOU", None],
                "home_team": ["OKC"] * 3,
                "away_team": ["HOU"] * 3,
            }
        )

        result = normalize_teams(table)

        self.assertEqual(result.table["event_team_role"].to_pylist(), ["home", "away", None])
        self.assertEqual(result.table["event_is_teamless"].to_pylist(), [False, False, True])
        self.assertEqual(
            result.table["event_team_is_conflicting"].to_pylist(),
            [False, False, False],
        )
        self.assertEqual(result.conflicting_game_ids, ())

    def test_preserves_and_flags_contradictory_team_fields(self) -> None:
        table = pa.table(
            {
                "game_id": ["0022500001"] * 3,
                "event_team_id": [1610612760, 1610612760, None],
                "event_team_code": ["OKC", "HOU", "OKC"],
                "home_team": ["OKC"] * 3,
                "away_team": ["HOU"] * 3,
            }
        )

        result = normalize_teams(table)

        self.assertEqual(result.table["event_team_code"].to_pylist(), ["OKC", "HOU", "OKC"])
        self.assertEqual(result.table["event_team_role"].to_pylist(), [None, None, None])
        self.assertEqual(result.conflicting_event_count, 3)
        self.assertEqual(result.conflicting_game_ids, ("0022500001",))


if __name__ == "__main__":
    unittest.main()
