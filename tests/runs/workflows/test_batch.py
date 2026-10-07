"""Tests for batch scoring-run detection."""

import unittest
from pathlib import Path

from nba_timeout_decision.runs.io.storage import output_paths
from nba_timeout_decision.runs.workflows.batch import detect_partitions
from nba_timeout_decision.runs.workflows.runner import MaterializedRuns


class RunBatchTests(unittest.TestCase):
    def test_continues_after_failure_and_summarizes_results(self) -> None:
        calls: list[tuple[int, str]] = []

        def materialize(*args: object, **kwargs: object) -> MaterializedRuns:
            season = int(kwargs["season"])
            game_type = str(kwargs["game_type"])
            calls.append((season, game_type))
            if season == 2014 and game_type == "regular":
                raise ValueError("invalid partition")
            status = "reused" if game_type == "playoffs" else "written"
            return MaterializedRuns(
                status=status,
                paths=output_paths(Path("runs"), season, game_type),
                source_possession_count=100,
                accepted_game_count=2,
                rejected_game_count=0,
                run_count=10,
                threshold_crossing_count=14,
                sensitivity_signal_count=20,
            )

        result = detect_partitions(
            seasons=[2014, 2013, 2013],
            game_types=["regular", "playoffs"],
            possession_root=Path("possessions"),
            possession_manifest=Path("possession-manifest.json"),
            catalog_root=Path("catalog"),
            output_root=Path("runs"),
            manifest_path=Path("run-manifest.json"),
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
        self.assertEqual(result["written"], 1)
        self.assertEqual(result["reused"], 2)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["accepted_games"], 6)
        self.assertEqual(result["runs"], 30)
        self.assertEqual(result["threshold_crossings"], 42)


if __name__ == "__main__":
    unittest.main()
