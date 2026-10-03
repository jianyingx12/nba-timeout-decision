import csv
import tempfile
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as parquet

from nba_timeout_decision.acquisition.catalog import (
    add_play_by_play_counts,
    extract_games,
    write_catalog,
)


def write_shotdetail(path: Path) -> None:
    parquet.write_table(
        pa.table(
            {
                "GAME_ID": [41300101, 41300101, 41300102],
                "GAME_DATE": [20140419, 20140419, 20140420],
                "HTM": ["IND", "IND", "MIA"],
                "VTM": ["ATL", "ATL", "CHA"],
                "_season": [2013, 2013, 2013],
                "_season_type": ["po", "po", "po"],
            }
        ),
        path,
    )


def write_play_by_play(path: Path, game_ids: list[int]) -> None:
    parquet.write_table(
        pa.table(
            {
                "gameId": game_ids,
                "actionId": list(range(1, len(game_ids) + 1)),
                "_season": [2013] * len(game_ids),
                "_season_type": ["po"] * len(game_ids),
            }
        ),
        path,
    )


class CatalogTests(unittest.TestCase):
    def test_catalog_combines_metadata_and_event_counts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shotdetail = root / "shotdetail.parquet"
            play_by_play = root / "play_by_play.parquet"
            output = root / "catalog.csv"
            write_shotdetail(shotdetail)
            write_play_by_play(play_by_play, [41300101, 41300101, 41300102])

            rows, shot_rows = extract_games(shotdetail, 2013, "playoffs")
            play_by_play_rows = add_play_by_play_counts(
                rows, play_by_play, 2013, "playoffs"
            )
            write_catalog(rows, output)

            with output.open(encoding="utf-8", newline="") as source:
                written = list(csv.DictReader(source))
            self.assertEqual(shot_rows, 3)
            self.assertEqual(play_by_play_rows, 3)
            self.assertEqual([row["game_id"] for row in written], ["0041300101", "0041300102"])
            self.assertEqual([row["play_by_play_rows"] for row in written], ["2", "1"])

    def test_catalog_rejects_mismatched_game_sets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shotdetail = root / "shotdetail.parquet"
            play_by_play = root / "play_by_play.parquet"
            write_shotdetail(shotdetail)
            write_play_by_play(play_by_play, [41300101])
            rows, _ = extract_games(shotdetail, 2013, "playoffs")

            with self.assertRaisesRegex(ValueError, "Game sets do not match"):
                add_play_by_play_counts(rows, play_by_play, 2013, "playoffs")

    def test_catalog_rejects_nonincreasing_action_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shotdetail = root / "shotdetail.parquet"
            play_by_play = root / "play_by_play.parquet"
            write_shotdetail(shotdetail)
            parquet.write_table(
                pa.table(
                    {
                        "gameId": [41300101, 41300101, 41300102],
                        "actionId": [2, 1, 3],
                        "_season": [2013, 2013, 2013],
                        "_season_type": ["po", "po", "po"],
                    }
                ),
                play_by_play,
            )
            rows, _ = extract_games(shotdetail, 2013, "playoffs")

            with self.assertRaisesRegex(ValueError, "not strictly increasing"):
                add_play_by_play_counts(rows, play_by_play, 2013, "playoffs")


if __name__ == "__main__":
    unittest.main()
