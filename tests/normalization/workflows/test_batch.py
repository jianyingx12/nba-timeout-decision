"""Tests for batch normalization."""

import unittest
from pathlib import Path

from nba_timeout_decision.normalization.workflows.batch import normalize_partitions
from nba_timeout_decision.normalization.workflows.runner import MaterializedPartition


class NormalizationBatchTests(unittest.TestCase):
    def test_continues_after_failure_and_summarizes_results(self) -> None:
        calls: list[tuple[int, str]] = []

        def materialize(*args: object, **kwargs: object) -> MaterializedPartition:
            season = int(kwargs["season"])
            game_type = str(kwargs["game_type"])
            calls.append((season, game_type))
            if season == 2014 and game_type == "regular":
                raise ValueError("invalid partition")
            status = "reused" if game_type == "playoffs" else "written"
            return MaterializedPartition(
                status=status,
                path=Path(f"normalized/{season}/{game_type}.parquet"),
                source_row_count=100,
                normalized_row_count=90,
                rejected_game_count=1,
                output_sha256="abc123",
            )

        result = normalize_partitions(
            seasons=[2014, 2013, 2013],
            game_types=["regular", "playoffs"],
            raw_root=Path("raw"),
            catalog=Path("catalog.csv"),
            output_root=Path("normalized"),
            manifest_path=Path("manifest.json"),
            materialize=materialize,
        )

        self.assertEqual(
            calls,
            [
                (2013, "regular"),
                (2013, "playoffs"),
                (2014, "regular"),
                (2014, "playoffs"),
            ],
        )
        self.assertEqual(result["requested"], 4)
        self.assertEqual(result["written"], 1)
        self.assertEqual(result["reused"], 2)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["source_rows"], 300)
        self.assertEqual(result["normalized_rows"], 270)
        self.assertEqual(result["rejected_games"], 3)


if __name__ == "__main__":
    unittest.main()
