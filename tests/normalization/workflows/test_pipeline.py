"""Tests for the normalization pipeline."""

import unittest
from datetime import date

import pyarrow as pa

from nba_timeout_decision.normalization.io.reader import PartitionProjection
from nba_timeout_decision.normalization.workflows.pipeline import (
    CANONICAL_COLUMNS,
    normalize_projection,
)


def projected_table() -> pa.Table:
    return pa.table(
        {
            "game_id": ["0022500001"] * 4,
            "season": ["2025-26"] * 4,
            "season_start_year": pa.array([2025] * 4, type=pa.int16()),
            "game_type": ["regular"] * 4,
            "game_date": pa.array([date(2025, 10, 21)] * 4, type=pa.date32()),
            "home_team": ["OKC"] * 4,
            "away_team": ["HOU"] * 4,
            "source_partition": ["nbastatsv3/2025/regular.parquet"] * 4,
            "source_row_number": pa.array(range(4), type=pa.int64()),
            "actionNumber": [1, 2, 3, 4],
            "clock": ["PT12M00.00S", "PT11M40.00S", "PT11M20.00S", "PT11M20.00S"],
            "period": [1, 1, 1, 1],
            "teamId": [0, 1610612760, 1610612745, 0],
            "teamTricode": [None, "OKC", "HOU", None],
            "personId": [0, 1, 1631095, 1610612745],
            "playerName": [None, "Player One", "Smith Jr.", None],
            "playerNameI": [None, "P. One", "S. Smith Jr.", None],
            "xLegacy": [0, 10, 0, 0],
            "yLegacy": [0, 20, 0, 0],
            "shotDistance": [0, 3, 0, 0],
            "shotResult": [None, "Made", None, None],
            "isFieldGoal": [0, 1, 0, 0],
            "scoreHome": [0.0, 2.0, 2.0, 2.0],
            "scoreAway": [0.0, 0.0, 0.0, 0.0],
            "pointsTotal": [0, 2, 0, 0],
            "location": [None, "H", None, None],
            "description": [
                "Start Period",
                "Made shot",
                "SUB: Eason FOR Smith Jr.",
                "Rockets Timeout: Regular (Reg.1 Short 0)",
            ],
            "actionType": ["period", "Made Shot", "Substitution", "Timeout"],
            "subType": ["Start Period", "Driving Layup", None, "Regular"],
            "videoAvailable": [0, 1, 0, 0],
            "actionId": [1, 2, 3, 4],
            "gameId": [22500001] * 4,
            "_season": [2025] * 4,
            "_season_type": ["rg"] * 4,
            "shotValue": pa.array([None, 2, None, None], type=pa.int64()),
        }
    )


class NormalizationPipelineTests(unittest.TestCase):
    def test_builds_only_the_canonical_columns_and_accounts_for_rows(self) -> None:
        projection = PartitionProjection(
            table=projected_table(),
            source_row_count=4,
            rejected_games=(),
        )

        result = normalize_projection(projection)

        self.assertEqual(result.table.column_names, list(CANONICAL_COLUMNS))
        self.assertEqual(result.table.num_rows, 4)
        self.assertEqual(result.rejected_games, ())
        self.assertEqual(result.table["event_type"].to_pylist()[-2:], ["substitution", "timeout"])
        self.assertEqual(result.table["substitution_in_player_name"][2].as_py(), "Eason")
        self.assertEqual(result.table["timeout_class"][3].as_py(), "team_regular")


if __name__ == "__main__":
    unittest.main()
