"""Tests for alternate scoring-run definitions."""

import unittest

import pyarrow as pa

from nba_timeout_decision.runs.ledger.builder import build_game_ledger
from nba_timeout_decision.runs.sensitivity import sensitivity_signals
from tests.runs.ledger.test_builder import BUILD_ARGUMENTS, possession


class SensitivitySignalTests(unittest.TestCase):
    def test_keeps_strict_thresholds_and_alternate_windows_separate(self) -> None:
        rows = []
        home_score = 0
        for number in range(1, 9):
            end_home = home_score + (2 if number <= 5 else 0)
            rows.append(
                possession(
                    number,
                    start_home=home_score,
                    end_home=end_home,
                    offense_id=10 if number % 2 else 20,
                )
            )
            home_score = end_home
        ledger = build_game_ledger(
            pa.Table.from_pylist(rows), **BUILD_ARGUMENTS
        ).table

        result = sensitivity_signals(ledger).to_pylist()
        definitions = {str(row["definition"]) for row in result}

        self.assertIn("strict_unanswered_6_0", definitions)
        self.assertIn("strict_unanswered_8_0", definitions)
        self.assertIn("net_plus_6_over_6_possessions", definitions)
        self.assertIn("net_plus_6_over_8_possessions", definitions)
        self.assertNotIn("strict_unanswered_10_0", definitions)

    def test_records_intensity_and_scoring_pace(self) -> None:
        rows = [
            possession(
                number,
                start_home=(number - 1) * 2,
                end_home=number * 2,
                offense_id=10 if number % 2 else 20,
            )
            for number in range(1, 7)
        ]
        ledger = build_game_ledger(
            pa.Table.from_pylist(rows), **BUILD_ARGUMENTS
        ).table

        result = sensitivity_signals(ledger).to_pylist()
        alternate = next(
            row
            for row in result
            if row["definition"] == "net_plus_6_over_6_possessions"
        )

        self.assertEqual(alternate["net_points"], 12)
        self.assertGreater(alternate["elapsed_seconds"], 0)
        self.assertIsNotNone(alternate["net_points_per_minute"])


if __name__ == "__main__":
    unittest.main()
