"""Tests for scoring-run output invariants."""

import unittest

import pyarrow as pa

from nba_timeout_decision.runs.detection import detect_primary_runs
from nba_timeout_decision.runs.ledger.builder import build_game_ledger
from nba_timeout_decision.runs.sensitivity import sensitivity_signals
from nba_timeout_decision.runs.validation import validate_outputs
from tests.runs.ledger.test_builder import BUILD_ARGUMENTS, possession


def valid_outputs():
    possessions = pa.Table.from_pylist(
        [
            possession(1, end_home=2),
            possession(2, start_home=2, end_home=4),
            possession(3, start_home=4, end_home=6),
            possession(4, start_home=6, end_home=8),
        ]
    )
    ledger = build_game_ledger(possessions, **BUILD_ARGUMENTS).table
    detected = detect_primary_runs(ledger)
    return detected.runs, detected.threshold_crossings, sensitivity_signals(ledger)


class RunValidationTests(unittest.TestCase):
    def test_accepts_consistent_outputs(self) -> None:
        result = validate_outputs(*valid_outputs())

        self.assertTrue(result.valid)
        self.assertEqual(result.errors, ())
        self.assertEqual(result.run_count, 1)
        self.assertEqual(result.threshold_counts, ((6, 1), (8, 1)))

    def test_rejects_crossing_that_exceeds_its_evidence(self) -> None:
        runs, crossings, sensitivity = valid_outputs()
        rows = crossings.to_pylist()
        rows[-1]["net_points"] = 7
        invalid_crossings = pa.Table.from_pylist(rows, schema=crossings.schema)

        result = validate_outputs(runs, invalid_crossings, sensitivity)

        self.assertFalse(result.valid)
        self.assertTrue(
            any("evidence is insufficient" in error for error in result.errors)
        )


if __name__ == "__main__":
    unittest.main()
