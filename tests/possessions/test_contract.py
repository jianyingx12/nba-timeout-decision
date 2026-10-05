"""Tests for the possession output contract."""

import unittest

import pyarrow as pa

from nba_timeout_decision.possessions.contract import (
    AMBIGUITY_REASONS,
    END_REASONS,
    POSSESSION_COLUMNS,
    POSSESSION_SCHEMA,
    POSSESSION_STATUSES,
    START_REASONS,
)


class PossessionContractTests(unittest.TestCase):
    def test_schema_has_unique_ordered_columns(self) -> None:
        self.assertEqual(POSSESSION_COLUMNS, tuple(POSSESSION_SCHEMA.names))
        self.assertEqual(len(POSSESSION_COLUMNS), len(set(POSSESSION_COLUMNS)))
        self.assertEqual(POSSESSION_SCHEMA.field("game_date").type, pa.date32())
        self.assertTrue(POSSESSION_SCHEMA.field("offense_team_id").nullable)
        self.assertTrue(POSSESSION_SCHEMA.field("offense_points").nullable)
        self.assertTrue(POSSESSION_SCHEMA.field("ambiguity_reason").nullable)

    def test_controlled_values_are_unique(self) -> None:
        for values in (
            POSSESSION_STATUSES,
            START_REASONS,
            END_REASONS,
            AMBIGUITY_REASONS,
        ):
            self.assertEqual(len(values), len(set(values)))

    def test_statuses_cover_complete_censored_and_ambiguous_rows(self) -> None:
        self.assertEqual(
            set(POSSESSION_STATUSES),
            {"complete", "censored", "ambiguous"},
        )


if __name__ == "__main__":
    unittest.main()
