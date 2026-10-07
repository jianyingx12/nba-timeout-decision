"""Tests for resumable scoring-run materialization."""

import tempfile
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as parquet

from nba_timeout_decision.possessions.contract import POSSESSION_SCHEMA
from nba_timeout_decision.possessions.io.manifest import write_manifest
from nba_timeout_decision.possessions.io.storage import sha256
from nba_timeout_decision.possessions.workflows.runner import RECONSTRUCTION_VERSION
from nba_timeout_decision.runs.io.manifest import read_manifest
from nba_timeout_decision.runs.workflows.runner import materialize_partition
from tests.runs.ledger.test_builder import possession


class RunRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "possessions" / "2025" / "regular.parquet"
        self.source.parent.mkdir(parents=True)
        rows = [
            possession(
                number,
                start_home=(number - 1) * 2,
                end_home=number * 2,
                offense_id=10 if number % 2 else 20,
            )
            for number in range(1, 5)
        ]
        for row in rows:
            row.update(
                {
                    "offense_points": row["end_home_score"]
                    - row["start_home_score"],
                    "defense_points": 0,
                    "duration_seconds": row["start_seconds_remaining_in_period"]
                    - row["end_seconds_remaining_in_period"],
                    "start_reason": "period_start",
                    "end_reason": "made_field_goal",
                    "ambiguity_reason": None,
                }
            )
        parquet.write_table(
            pa.Table.from_pylist(rows, schema=POSSESSION_SCHEMA), self.source
        )
        self.possession_manifest = self.root / "possession-manifest.json"
        write_manifest(
            self.possession_manifest,
            {
                "format_version": 1,
                "partitions": {
                    "2025/regular": {
                        "status": "complete",
                        "reconstruction_version": RECONSTRUCTION_VERSION,
                        "output_path": self.source.as_posix(),
                        "output_sha256": sha256(self.source),
                        "output_file_size": self.source.stat().st_size,
                        "possession_count": 4,
                        "accepted_game_count": 1,
                        "rejected_game_count": 0,
                    }
                },
            },
        )
        self.catalog_root = self.root / "catalog"
        catalog = self.catalog_root / "2025" / "regular.csv"
        catalog.parent.mkdir(parents=True)
        catalog.write_text(
            "game_id,season_start_year,game_type,home_team,away_team\n"
            "0000000001,2025,regular,HOM,AWY\n",
            encoding="utf-8",
        )
        self.output_root = self.root / "runs"
        self.manifest = self.root / "run-manifest.json"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def materialize(self):
        return materialize_partition(
            self.source,
            possession_manifest=self.possession_manifest,
            catalog_root=self.catalog_root,
            output_root=self.output_root,
            manifest_path=self.manifest,
            season=2025,
            game_type="regular",
        )

    def test_reuses_only_manifest_and_schema_valid_outputs(self) -> None:
        first = self.materialize()
        second = self.materialize()
        second.paths.runs.write_bytes(b"corrupt output")
        third = self.materialize()

        self.assertEqual(first.status, "written")
        self.assertEqual(second.status, "reused")
        self.assertEqual(third.status, "written")
        self.assertEqual(third.run_count, 1)

    def test_records_input_validation_failure(self) -> None:
        self.source.write_bytes(b"corrupt source")

        with self.assertRaises(Exception):
            self.materialize()

        record = read_manifest(self.manifest)["partitions"]["2025/regular"]
        self.assertEqual(record["status"], "failed")
        self.assertIn("error", record)
        self.assertFalse(record["stale_outputs_present"])


if __name__ == "__main__":
    unittest.main()
