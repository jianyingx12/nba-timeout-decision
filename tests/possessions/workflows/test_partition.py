"""Tests for partition-level possession reconstruction."""

import unittest

import pyarrow as pa

from nba_timeout_decision.possessions.workflows.partition import (
    INPUT_COLUMNS,
    reconstruct_partition,
)
from tests.possessions.workflows.test_reconstruct import event


def game_event(game_id: str, action_id: int, **values: object) -> dict[str, object]:
    row = event(action_id, **values)
    row["game_id"] = game_id
    return row


class PartitionReconstructionTests(unittest.TestCase):
    def test_reconstructs_games_and_isolates_failures(self) -> None:
        events = pa.Table.from_pylist(
            [
                game_event(
                    "0000000001",
                    1,
                    event_type="made_shot",
                    team_id=10,
                    team_code="HOM",
                    team_role="home",
                    seconds=100,
                    home_score=2,
                    away_score=0,
                ),
                game_event(
                    "0000000001",
                    2,
                    event_type="substitution",
                    team_id=20,
                    team_code="AWY",
                    team_role="away",
                    seconds=100,
                    home_score=2,
                    away_score=0,
                ),
                game_event(
                    "0000000002",
                    1,
                    event_type="made_shot",
                    team_id=10,
                    team_code="HOM",
                    team_role="home",
                    seconds=100,
                    home_score=2,
                    away_score=0,
                ),
                game_event(
                    "0000000002",
                    2,
                    event_type="turnover",
                    team_id=30,
                    team_code="BAD",
                    team_role="away",
                    seconds=90,
                    home_score=2,
                    away_score=0,
                ),
                game_event(
                    "0000000002",
                    3,
                    event_type="substitution",
                    team_id=20,
                    team_code="AWY",
                    team_role="away",
                    seconds=90,
                    home_score=2,
                    away_score=0,
                ),
            ]
        )

        result = reconstruct_partition(events)

        self.assertEqual(result.source_event_count, 5)
        self.assertEqual(result.accepted_game_count, 1)
        self.assertEqual(result.table.num_rows, 1)
        self.assertEqual(result.table["game_id"].to_pylist(), ["0000000001"])
        self.assertEqual(len(result.rejected_games), 1)
        self.assertEqual(result.rejected_games[0].game_id, "0000000002")

    def test_rejects_missing_canonical_columns(self) -> None:
        missing_column = INPUT_COLUMNS[-1]
        table = pa.table(
            {
                name: pa.array([], type=pa.null())
                for name in INPUT_COLUMNS
                if name != missing_column
            }
        )

        with self.assertRaisesRegex(ValueError, "missing columns"):
            reconstruct_partition(table)


if __name__ == "__main__":
    unittest.main()
