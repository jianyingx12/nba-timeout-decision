"""Tests for possession partition checks."""

import unittest

import pyarrow as pa

from nba_timeout_decision.possessions.validation.checks import check_partition


class PossessionCheckTests(unittest.TestCase):
    def test_reconciles_scores_and_reports_between_possession_points(self) -> None:
        source = pa.table(
            {
                "game_id": ["1", "1"],
                "home_score": [0, 3],
                "away_score": [0, 2],
            }
        )
        possessions = pa.Table.from_pylist(
            [
                {
                    "game_id": "1",
                    "possession_number": 1,
                    "offense_team_id": 10,
                    "start_home_score": 0,
                    "start_away_score": 0,
                    "end_home_score": 2,
                    "end_away_score": 0,
                    "possession_is_ambiguous": False,
                },
                {
                    "game_id": "1",
                    "possession_number": 2,
                    "offense_team_id": 20,
                    "start_home_score": 3,
                    "start_away_score": 0,
                    "end_home_score": 3,
                    "end_away_score": 2,
                    "possession_is_ambiguous": True,
                },
            ]
        )

        result = check_partition(source, possessions, rejected_game_ids=set())

        self.assertEqual(result.source_games, 1)
        self.assertEqual(result.ambiguous_possessions, 1)
        self.assertEqual(result.unassigned_score_points, 1)
        self.assertEqual(result.imbalanced_games, 0)
        self.assertEqual(result.issues, ())

    def test_reports_missing_games_and_nonsequential_possessions(self) -> None:
        source = pa.table(
            {
                "game_id": ["1", "2"],
                "home_score": [0, 0],
                "away_score": [0, 0],
            }
        )
        possessions = pa.Table.from_pylist(
            [
                {
                    "game_id": "1",
                    "possession_number": 2,
                    "offense_team_id": 10,
                    "start_home_score": 0,
                    "start_away_score": 0,
                    "end_home_score": 0,
                    "end_away_score": 0,
                    "possession_is_ambiguous": False,
                }
            ]
        )

        result = check_partition(source, possessions, rejected_game_ids=set())

        self.assertIn("1 source games are unaccounted for", result.issues)
        self.assertIn("1: possession numbers are not sequential", result.issues)
        self.assertEqual(result.imbalanced_games, 1)


if __name__ == "__main__":
    unittest.main()
