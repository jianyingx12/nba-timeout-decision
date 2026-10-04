"""Tests for normalized input reading."""

import csv
import tempfile
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as parquet

from nba_timeout_decision.normalization.io.reader import read_partition


def write_play_by_play(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    parquet.write_table(
        pa.table(
            {
                "actionNumber": [10, 11, 20],
                "clock": ["PT12M00.00S", "PT11M42.00S", "PT12M00.00S"],
                "period": [1, 1, 1],
                "teamId": [0, 1610612754, 0],
                "teamTricode": [None, "IND", None],
                "personId": [0, 123, 0],
                "playerName": [None, "Player", None],
                "playerNameI": [None, "P. Player", None],
                "xLegacy": [0, 10, 0],
                "yLegacy": [0, 20, 0],
                "shotDistance": [0, 3, 0],
                "shotResult": [None, "Made", None],
                "isFieldGoal": [0, 1, 0],
                "scoreHome": [None, 2.0, None],
                "scoreAway": [None, 0.0, None],
                "pointsTotal": [0, 2, 0],
                "location": [None, "H", None],
                "description": ["Game start", "Made shot", "Game start"],
                "actionType": ["Game", "Made Shot", "Game"],
                "subType": [None, "Driving Layup", None],
                "videoAvailable": [0, 1, 0],
                "actionId": [1, 2, 1],
                "gameId": [21300001, 21300001, 21300002],
                "_season": [2013, 2013, 2013],
                "_season_type": ["rg", "rg", "rg"],
            }
        ),
        path,
    )


def write_catalog(path: Path, include_second_game: bool = True) -> None:
    fieldnames = [
        "game_id",
        "season",
        "season_start_year",
        "game_type",
        "game_date",
        "home_team",
        "away_team",
    ]
    rows = [
        {
            "game_id": "0021300001",
            "season": "2013-14",
            "season_start_year": 2013,
            "game_type": "regular",
            "game_date": "2013-10-29",
            "home_team": "IND",
            "away_team": "ORL",
        }
    ]
    if include_second_game:
        rows.append(
            {
                "game_id": "0021300002",
                "season": "2013-14",
                "season_start_year": 2013,
                "game_type": "regular",
                "game_date": "2013-10-29",
                "home_team": "MIA",
                "away_team": "CHI",
            }
        )
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class NormalizationReaderTests(unittest.TestCase):
    def test_projects_source_rows_with_catalog_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_root = root / "raw"
            source = raw_root / "nbastatsv3" / "2013" / "regular.parquet"
            catalog = root / "games.csv"
            write_play_by_play(source)
            write_catalog(catalog)

            result = read_partition(
                source,
                catalog,
                raw_root=raw_root,
                expected_season=2013,
                expected_game_type="regular",
            )

            self.assertEqual(result.source_row_count, 3)
            self.assertEqual(result.table.num_rows, 3)
            self.assertEqual(result.rejected_games, ())
            self.assertEqual(result.table["actionId"].to_pylist(), [1, 2, 1])
            self.assertEqual(result.table["source_row_number"].to_pylist(), [0, 1, 2])
            self.assertEqual(
                result.table["game_id"].to_pylist(),
                ["0021300001", "0021300001", "0021300002"],
            )
            self.assertEqual(
                result.table["source_partition"].to_pylist(),
                ["nbastatsv3/2013/regular.parquet"] * 3,
            )
            self.assertEqual(result.table["shotValue"].null_count, 3)

    def test_rejects_an_entire_game_missing_from_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_root = root / "raw"
            source = raw_root / "nbastatsv3" / "2013" / "regular.parquet"
            catalog = root / "games.csv"
            write_play_by_play(source)
            write_catalog(catalog, include_second_game=False)

            result = read_partition(
                source,
                catalog,
                raw_root=raw_root,
                expected_season=2013,
                expected_game_type="regular",
            )

            self.assertEqual(result.table.num_rows, 2)
            self.assertEqual(result.table["source_row_number"].to_pylist(), [0, 1])
            self.assertEqual(len(result.rejected_games), 1)
            self.assertEqual(result.rejected_games[0].game_id, "0021300002")
            self.assertEqual(result.rejected_games[0].raw_row_count, 1)


if __name__ == "__main__":
    unittest.main()
