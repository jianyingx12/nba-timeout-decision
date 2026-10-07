"""Tests for primary four-possession run signals."""

import unittest

import pyarrow as pa

from nba_timeout_decision.runs.ledger.builder import build_game_ledger
from nba_timeout_decision.runs.signals import primary_window_signals
from tests.runs.ledger.test_builder import BUILD_ARGUMENTS, possession


def ledger(rows: list[dict[str, object]]) -> pa.Table:
    return build_game_ledger(
        pa.Table.from_pylist(rows), **BUILD_ARGUMENTS
    ).table


class PrimarySignalTests(unittest.TestCase):
    def test_detects_home_run_after_four_possessions(self) -> None:
        table = ledger(
            [
                possession(1, end_home=2),
                possession(2, offense_id=20, start_home=2, end_home=2),
                possession(3, start_home=2, end_home=4),
                possession(4, offense_id=20, start_home=4, end_home=6),
            ]
        )

        signals = primary_window_signals(table)

        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].run_team_code, "HOM")
        self.assertEqual(signals[0].start_possession_number, 1)
        self.assertEqual(signals[0].net_points, 6)
        self.assertTrue(signals[0].strict_unanswered)

    def test_detects_away_run_symmetrically(self) -> None:
        table = ledger(
            [
                possession(1, offense_id=20, end_away=3),
                possession(2, start_away=3, end_away=3),
                possession(3, offense_id=20, start_away=3, end_away=5),
                possession(4, start_away=5, end_away=7),
            ]
        )

        signal = primary_window_signals(table)[0]

        self.assertEqual(signal.run_team_code, "AWY")
        self.assertFalse(signal.run_team_is_home)
        self.assertEqual(signal.run_team_points, 7)
        self.assertEqual(signal.opponent_points, 0)

    def test_between_possession_points_can_cross_threshold(self) -> None:
        table = ledger(
            [
                possession(1, end_home=2),
                possession(2, offense_id=20, start_home=2, end_home=2),
                possession(3, start_home=2, end_home=4),
                possession(4, offense_id=20, start_home=4, end_home=4),
                possession(5, start_home=6, end_home=6),
            ]
        )

        signals = primary_window_signals(table)

        self.assertEqual(signals[0].checkpoint_type, "between_possessions")
        self.assertEqual(signals[0].possession_number, 5)
        self.assertEqual(signals[0].between_possession_net_points, 2)
        self.assertIsNone(signals[0].action_id)

    def test_period_change_prevents_cross_period_window(self) -> None:
        table = ledger(
            [
                possession(1, end_home=2),
                possession(2, start_home=2, end_home=4, censored=True),
                possession(3, period=2, start_home=4, end_home=6),
                possession(4, period=2, start_home=6, end_home=8),
            ]
        )

        self.assertEqual(primary_window_signals(table), ())

    def test_overtime_uses_a_fresh_window(self) -> None:
        table = ledger(
            [
                possession(1, period=4, end_home=2, censored=True),
                possession(2, period=5, start_home=2, end_home=4),
                possession(3, period=5, start_home=4, end_home=6),
                possession(4, period=5, start_home=6, end_home=8),
                possession(5, period=5, start_home=8, end_home=10),
            ]
        )

        signal = primary_window_signals(table)[0]

        self.assertEqual(signal.period, 5)
        self.assertEqual(signal.start_possession_number, 2)

    def test_ambiguous_possession_prevents_cross_reset_window(self) -> None:
        table = ledger(
            [
                possession(1, end_home=2),
                possession(2, start_home=2, end_home=4, ambiguous=True),
                possession(3, start_home=4, end_home=6),
                possession(4, start_home=6, end_home=8),
                possession(5, start_home=8, end_home=10),
            ]
        )

        self.assertEqual(primary_window_signals(table), ())


if __name__ == "__main__":
    unittest.main()
