"""Tests for score normalization."""

import unittest

import pyarrow as pa

from nba_timeout_decision.normalization.steps.score import normalize_scores


def score_table(
    game_ids: list[str],
    action_types: list[str],
    home_scores: list[float | None],
    away_scores: list[float | None],
) -> pa.Table:
    return pa.table(
        {
            "game_id": game_ids,
            "period": [1] * len(game_ids),
            "action_type": action_types,
            "scoreHome": home_scores,
            "scoreAway": away_scores,
        }
    )


class NormalizationScoreTests(unittest.TestCase):
    def test_fills_score_state_and_derives_final_score(self) -> None:
        table = score_table(
            ["0022500001"] * 4,
            ["period", "Made Shot", "Foul", "Free Throw"],
            [0.0, 2.0, None, 3.0],
            [0.0, 0.0, None, 0.0],
        )

        result = normalize_scores(table)

        self.assertEqual(result.table["home_score"].to_pylist(), [0, 2, 2, 3])
        self.assertEqual(result.table["away_score"].to_pylist(), [0, 0, 0, 0])
        self.assertEqual(
            result.table["score_is_carried_forward"].to_pylist(),
            [False, False, True, False],
        )
        self.assertEqual(result.rejected_games, ())
        self.assertEqual(result.final_scores[0].home_score, 3)
        self.assertEqual(result.final_scores[0].away_score, 0)

    def test_treats_historical_zero_pair_as_missing_after_scoring_begins(self) -> None:
        table = score_table(
            ["0021300001"] * 3,
            ["period", "Made Shot", "Missed Shot"],
            [0.0, 2.0, 0.0],
            [0.0, 0.0, 0.0],
        )

        result = normalize_scores(table)

        self.assertEqual(result.rejected_games, ())
        self.assertEqual(result.table["home_score"].to_pylist(), [0, 2, 2])
        self.assertEqual(
            result.table["score_is_carried_forward"].to_pylist(),
            [False, False, True],
        )

    def test_rejects_entire_game_with_score_decrease(self) -> None:
        table = score_table(
            ["0022500001", "0022500001", "0022500002"],
            ["Made Shot", "Free Throw", "period"],
            [2.0, 1.0, 0.0],
            [0.0, 0.0, 0.0],
        )

        result = normalize_scores(table)

        self.assertEqual(result.table["game_id"].to_pylist(), ["0022500002"])
        self.assertEqual(len(result.rejected_games), 1)
        self.assertEqual(result.rejected_games[0].game_id, "0022500001")
        self.assertEqual(result.rejected_games[0].reason, "score decreases")
        self.assertEqual(result.rejected_games[0].raw_row_count, 2)

    def test_flags_plausible_score_update_on_unexpected_event(self) -> None:
        table = score_table(
            ["0022500001", "0022500001"],
            ["period", "Foul"],
            [0.0, 2.0],
            [0.0, 0.0],
        )

        result = normalize_scores(table)

        self.assertEqual(result.rejected_games, ())
        self.assertEqual(result.unexplained_update_count, 1)
        self.assertEqual(
            result.table["score_update_is_unexplained"].to_pylist(),
            [False, True],
        )

    def test_accepts_and_flags_score_correction_around_replay(self) -> None:
        table = score_table(
            ["0022500001"] * 4,
            ["Made Shot", "Instant Replay", "Free Throw", "Free Throw"],
            [2.0, 3.0, 2.0, 3.0],
            [0.0, 0.0, 0.0, 0.0],
        )

        result = normalize_scores(table)

        self.assertEqual(result.rejected_games, ())
        self.assertEqual(result.table["home_score"].to_pylist(), [2, 3, 2, 3])
        self.assertEqual(
            result.table["score_update_is_revision"].to_pylist(),
            [False, True, True, False],
        )
        self.assertEqual(result.revision_count, 2)

    def test_ignores_stale_period_end_score(self) -> None:
        table = score_table(
            ["0022500001"] * 3,
            ["Made Shot", "Free Throw", "period"],
            [2.0, 3.0, 2.0],
            [0.0, 0.0, 0.0],
        )

        result = normalize_scores(table)

        self.assertEqual(result.rejected_games, ())
        self.assertEqual(result.table["home_score"].to_pylist(), [2, 3, 3])
        self.assertEqual(
            result.table["score_is_carried_forward"].to_pylist(),
            [False, False, True],
        )


if __name__ == "__main__":
    unittest.main()
