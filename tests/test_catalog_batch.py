import csv
import tempfile
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as parquet

from nba_timeout_decision.acquisition.archive import local_path
from nba_timeout_decision.acquisition.catalog_batch import build_catalogs


def write_source_pair(
    raw_root: Path, season: int, season_type: str, game_ids: list[int]
) -> None:
    type_code = "rg" if season_type == "regular" else "po"
    shotdetail = local_path(raw_root, "shotdetail", season, season_type)
    play_by_play = local_path(raw_root, "nbastatsv3", season, season_type)
    shotdetail.parent.mkdir(parents=True, exist_ok=True)
    play_by_play.parent.mkdir(parents=True, exist_ok=True)

    parquet.write_table(
        pa.table(
            {
                "GAME_ID": game_ids,
                "GAME_DATE": [20131029 + index for index in range(len(game_ids))],
                "HTM": ["HOME"] * len(game_ids),
                "VTM": ["AWAY"] * len(game_ids),
                "_season": [season] * len(game_ids),
                "_season_type": [type_code] * len(game_ids),
            }
        ),
        shotdetail,
    )
    parquet.write_table(
        pa.table(
            {
                "gameId": game_ids,
                "actionId": [1] * len(game_ids),
                "_season": [season] * len(game_ids),
                "_season_type": [type_code] * len(game_ids),
            }
        ),
        play_by_play,
    )


class CatalogBatchTests(unittest.TestCase):
    def test_builds_partition_and_combined_catalogs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_root = root / "raw"
            output_root = root / "catalog"
            write_source_pair(raw_root, 2013, "regular", [21300001, 21300002])
            write_source_pair(raw_root, 2013, "playoffs", [41300101, 41300102])

            result = build_catalogs(
                seasons=[2013], raw_root=raw_root, output_root=output_root
            )

            with (output_root / "games.csv").open(
                encoding="utf-8", newline=""
            ) as source:
                rows = list(csv.DictReader(source))
            self.assertEqual(result["partitions"], 2)
            self.assertEqual(result["games"], 4)
            self.assertEqual(result["shot_rows"], 4)
            self.assertEqual(result["play_by_play_rows"], 4)
            self.assertTrue((output_root / "2013" / "regular.csv").is_file())
            self.assertTrue((output_root / "2013" / "playoffs.csv").is_file())
            self.assertEqual(len(rows), 4)
            self.assertEqual(len({row["game_id"] for row in rows}), 4)
            self.assertTrue(all(row["has_shotdetail"] == "True" for row in rows))
            self.assertTrue(all(row["has_play_by_play"] == "True" for row in rows))


if __name__ == "__main__":
    unittest.main()
