"""Tests for clock normalization."""

import unittest

import pyarrow as pa

from nba_timeout_decision.normalization.steps.clock import normalize_period_and_clock


class NormalizationClockTests(unittest.TestCase):
    def test_parses_regulation_and_overtime_clocks(self) -> None:
        table = pa.table(
            {
                "game_id": ["0022500001"] * 6,
                "period": [1, 1, 1, 1, 5, 5],
                "clock": [
                    "PT12M00.00S",
                    "PT11M30.50S",
                    "PT11M30.50S",
                    "PT11M31.00S",
                    "PT05M00.00S",
                    "PT00M00.00S",
                ],
            }
        )

        result = normalize_period_and_clock(table)

        self.assertEqual(result["period"].type, pa.int8())
        self.assertEqual(
            result["seconds_remaining_in_period"].to_pylist(),
            [720.0, 690.5, 690.5, 691.0, 300.0, 0.0],
        )
        self.assertEqual(
            result["clock_increases_within_period"].to_pylist(),
            [False, False, False, True, False, False],
        )

    def test_rejects_clock_outside_period_limit(self) -> None:
        table = pa.table(
            {
                "game_id": ["0022500001"],
                "period": [5],
                "clock": ["PT05M00.01S"],
            }
        )

        with self.assertRaisesRegex(ValueError, "exceeds period length"):
            normalize_period_and_clock(table)


if __name__ == "__main__":
    unittest.main()
