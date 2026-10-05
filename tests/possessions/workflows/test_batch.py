"""Tests for batch possession reconstruction."""

import unittest
from pathlib import Path

from nba_timeout_decision.possessions.workflows.batch import (
    reconstruct_partitions,
)
from nba_timeout_decision.possessions.workflows.runner import (
    MaterializedPartition,
)


class PossessionBatchTests(unittest.TestCase):
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
                path=Path(f"possessions/{season}/{game_type}.parquet"),
                source_event_count=100,
                possession_count=40,
                accepted_game_count=2,
                rejected_game_count=1,
                output_sha256="abc123",
            )

        result = reconstruct_partitions(
            seasons=[2014, 2013, 2013],
            game_types=["regular", "playoffs"],
            normalized_root=Path("normalized/events"),
            normalization_manifest=Path("normalized/manifest.json"),
            output_root=Path("derived/possessions"),
            manifest_path=Path("derived/possessions-manifest.json"),
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
        self.assertEqual(result["source_events"], 300)
        self.assertEqual(result["possessions"], 120)
        self.assertEqual(result["accepted_games"], 6)
        self.assertEqual(result["rejected_games"], 3)


if __name__ == "__main__":
    unittest.main()
