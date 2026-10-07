"""Tests for scoring-run output contracts."""

import unittest

from nba_timeout_decision.runs.contract import (
    CHECKPOINT_TYPES,
    EXCLUSION_REASONS,
    PRIMARY_WINDOW_SIZE,
    RESET_REASONS,
    RUN_COLUMNS,
    RUN_SCHEMA,
    RUN_THRESHOLDS,
    SCORE_LEDGER_COLUMNS,
    SCORE_LEDGER_SCHEMA,
    SENSITIVITY_SIGNAL_COLUMNS,
    SENSITIVITY_SIGNAL_SCHEMA,
    SENSITIVITY_WINDOW_SIZES,
    TERMINATION_REASONS,
    THRESHOLD_CROSSING_COLUMNS,
    THRESHOLD_CROSSING_SCHEMA,
)


class RunContractTests(unittest.TestCase):
    def test_schemas_have_unique_ordered_columns(self) -> None:
        for schema, columns in (
            (SCORE_LEDGER_SCHEMA, SCORE_LEDGER_COLUMNS),
            (RUN_SCHEMA, RUN_COLUMNS),
            (THRESHOLD_CROSSING_SCHEMA, THRESHOLD_CROSSING_COLUMNS),
            (SENSITIVITY_SIGNAL_SCHEMA, SENSITIVITY_SIGNAL_COLUMNS),
        ):
            self.assertEqual(tuple(schema.names), columns)
            self.assertEqual(len(columns), len(set(columns)))

    def test_primary_and_sensitivity_windows_are_distinct(self) -> None:
        self.assertEqual(PRIMARY_WINDOW_SIZE, 4)
        self.assertEqual(SENSITIVITY_WINDOW_SIZES, (6, 8))
        self.assertNotIn(PRIMARY_WINDOW_SIZE, SENSITIVITY_WINDOW_SIZES)

    def test_thresholds_are_strictly_increasing(self) -> None:
        self.assertEqual(RUN_THRESHOLDS, tuple(sorted(set(RUN_THRESHOLDS))))
        self.assertEqual(RUN_THRESHOLDS[0], 6)

    def test_controlled_values_are_unique(self) -> None:
        for values in (
            CHECKPOINT_TYPES,
            RESET_REASONS,
            TERMINATION_REASONS,
            EXCLUSION_REASONS,
        ):
            self.assertEqual(len(values), len(set(values)))


if __name__ == "__main__":
    unittest.main()
