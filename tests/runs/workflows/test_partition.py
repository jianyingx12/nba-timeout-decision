"""Tests for partition-level scoring-run detection."""

import unittest

import pyarrow as pa

from nba_timeout_decision.possessions.contract import POSSESSION_SCHEMA
from nba_timeout_decision.runs.io.catalog import GameTeams
from nba_timeout_decision.runs.workflows.partition import detect_partition
from tests.runs.ledger.test_builder import possession


class PartitionDetectionTests(unittest.TestCase):
    def test_detects_each_cataloged_game_and_combines_outputs(self) -> None:
        rows: list[dict[str, object]] = []
        for game_index, game_id in enumerate(("0000000001", "0000000002")):
            for number in range(1, 5):
                row = possession(
                    number,
                    start_home=(number - 1) * 2,
                    end_home=number * 2,
                    offense_id=10 if number % 2 else 20,
                )
                row["game_id"] = game_id
                row["game_date"] = row["game_date"].replace(day=21 + game_index)
                rows.append(row)
        table = pa.Table.from_pylist(rows, schema=POSSESSION_SCHEMA)
        teams = {
            game_id: GameTeams(game_id, "HOM", "AWY")
            for game_id in ("0000000001", "0000000002")
        }

        result = detect_partition(table, teams)

        self.assertEqual(result.source_possession_count, 8)
        self.assertEqual(result.accepted_game_count, 2)
        self.assertEqual(result.rejected_games, ())
        self.assertEqual(result.catalog_only_game_count, 0)
        self.assertEqual(result.runs.num_rows, 2)
        self.assertEqual(result.threshold_crossings.num_rows, 4)

    def test_requires_catalog_and_possession_game_sets_to_match(self) -> None:
        table = pa.Table.from_pylist([possession(1)], schema=POSSESSION_SCHEMA)

        with self.assertRaisesRegex(ValueError, "missing from the catalog"):
            detect_partition(table, {})

    def test_counts_catalog_games_rejected_by_upstream_processing(self) -> None:
        table = pa.Table.from_pylist([possession(1)], schema=POSSESSION_SCHEMA)
        teams = {
            "0000000001": GameTeams("0000000001", "HOM", "AWY"),
            "0000000002": GameTeams("0000000002", "AAA", "BBB"),
        }

        result = detect_partition(table, teams)

        self.assertEqual(result.accepted_game_count, 1)
        self.assertEqual(result.catalog_only_game_count, 1)


if __name__ == "__main__":
    unittest.main()
