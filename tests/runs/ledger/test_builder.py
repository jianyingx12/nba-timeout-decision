"""Tests for ordered score-ledger construction."""

import unittest
from datetime import date

import pyarrow as pa

from nba_timeout_decision.runs.ledger.builder import build_game_ledger

BUILD_ARGUMENTS = {"home_team_code": "HOM", "away_team_code": "AWY"}


def possession(
    number: int,
    *,
    period: int = 1,
    offense_id: int = 10,
    start_home: int = 0,
    start_away: int = 0,
    end_home: int = 0,
    end_away: int = 0,
    ambiguous: bool = False,
    censored: bool = False,
) -> dict[str, object]:
    defense_id = 20 if offense_id == 10 else 10
    return {
        "game_id": "0000000001",
        "season": "2025-26",
        "season_start_year": 2025,
        "game_type": "regular",
        "game_date": date(2025, 10, 21),
        "possession_number": number,
        "period": period,
        "first_action_id": number * 10,
        "last_action_id": number * 10 + 5,
        "first_source_row_number": number * 10 - 1,
        "last_source_row_number": number * 10 + 4,
        "offense_team_id": offense_id,
        "offense_team_code": "HOM" if offense_id == 10 else "AWY",
        "defense_team_id": defense_id,
        "defense_team_code": "HOM" if defense_id == 10 else "AWY",
        "start_seconds_remaining_in_period": 700.0 - number * 20,
        "end_seconds_remaining_in_period": 690.0 - number * 20,
        "start_home_score": start_home,
        "start_away_score": start_away,
        "end_home_score": end_home,
        "end_away_score": end_away,
        "possession_status": "ambiguous" if ambiguous else "complete",
        "is_censored_at_period_end": censored,
        "contains_timeout": False,
        "contains_review": False,
        "contains_score_revision": False,
        "possession_is_ambiguous": ambiguous,
    }


class GameLedgerTests(unittest.TestCase):
    def test_builds_one_checkpoint_per_continuous_possession(self) -> None:
        table = pa.Table.from_pylist(
            [
                possession(1, end_home=2),
                possession(
                    2,
                    offense_id=20,
                    start_home=2,
                    end_home=2,
                    end_away=3,
                ),
            ]
        )

        result = build_game_ledger(table, **BUILD_ARGUMENTS)
        rows = result.table.to_pylist()

        self.assertEqual(result.possession_count, 2)
        self.assertEqual(result.between_possession_checkpoint_count, 0)
        self.assertEqual([row["checkpoint_number"] for row in rows], [1, 2])
        self.assertEqual(rows[0]["reset_before_reason"], "game_start")
        self.assertEqual((rows[1]["home_points"], rows[1]["away_points"]), (0, 3))

    def test_emits_between_possession_score_checkpoint(self) -> None:
        table = pa.Table.from_pylist(
            [
                possession(1, end_home=2),
                possession(
                    2,
                    offense_id=20,
                    start_home=3,
                    end_home=3,
                    end_away=2,
                ),
            ]
        )

        result = build_game_ledger(table, **BUILD_ARGUMENTS)
        rows = result.table.to_pylist()

        self.assertEqual(result.between_possession_checkpoint_count, 1)
        self.assertEqual(rows[1]["checkpoint_type"], "between_possessions")
        self.assertFalse(rows[1]["increments_possession_window"])
        self.assertEqual(rows[1]["completed_possession_count"], 1)
        self.assertEqual((rows[1]["home_points"], rows[1]["away_points"]), (1, 0))
        self.assertTrue(rows[1]["primary_window_eligible"])

    def test_period_change_resets_at_first_new_period_checkpoint(self) -> None:
        table = pa.Table.from_pylist(
            [
                possession(1, end_home=2, censored=True),
                possession(
                    2,
                    period=2,
                    offense_id=20,
                    start_home=2,
                    start_away=1,
                    end_home=2,
                    end_away=3,
                ),
            ]
        )

        rows = build_game_ledger(table, **BUILD_ARGUMENTS).table.to_pylist()

        self.assertEqual(rows[0]["reset_after_reason"], "period_start")
        self.assertEqual(rows[1]["checkpoint_type"], "between_possessions")
        self.assertEqual(rows[1]["reset_before_reason"], "period_start")
        self.assertFalse(rows[1]["primary_window_eligible"])
        self.assertIsNone(rows[2]["reset_before_reason"])

    def test_ambiguous_possession_resets_both_sides(self) -> None:
        table = pa.Table.from_pylist(
            [
                possession(1, end_home=2),
                possession(2, start_home=2, end_home=2, ambiguous=True),
                possession(3, start_home=2, end_home=4),
            ]
        )

        rows = build_game_ledger(table, **BUILD_ARGUMENTS).table.to_pylist()

        self.assertEqual(rows[1]["reset_before_reason"], "ambiguous_possession")
        self.assertEqual(rows[1]["reset_after_reason"], "ambiguous_possession")
        self.assertFalse(rows[1]["primary_window_eligible"])
        self.assertEqual(rows[2]["reset_before_reason"], "ambiguous_possession")

    def test_rejects_nonsequential_possession_numbers(self) -> None:
        table = pa.Table.from_pylist([possession(1), possession(3)])

        with self.assertRaisesRegex(ValueError, "sequential"):
            build_game_ledger(table, **BUILD_ARGUMENTS)


if __name__ == "__main__":
    unittest.main()
