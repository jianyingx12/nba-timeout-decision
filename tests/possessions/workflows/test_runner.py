"""Tests for possession partition materialization."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as parquet

from nba_timeout_decision.io.files import sha256
from nba_timeout_decision.io.manifest import read_manifest, write_manifest
from nba_timeout_decision.normalization.workflows.pipeline import CANONICAL_COLUMNS
from nba_timeout_decision.normalization.workflows.runner import PIPELINE_VERSION
from nba_timeout_decision.possessions.contract import POSSESSION_SCHEMA
from nba_timeout_decision.possessions.workflows.partition import (
    PartitionReconstruction,
)
from nba_timeout_decision.possessions.workflows.runner import materialize_partition


class PossessionRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "events" / "2025" / "regular.parquet"
        self.source.parent.mkdir(parents=True)
        source_table = pa.table(
            {name: pa.array([], type=pa.null()) for name in CANONICAL_COLUMNS}
        )
        parquet.write_table(source_table, self.source)
        self.normalization_manifest = self.root / "normalization.json"
        write_manifest(
            self.normalization_manifest,
            {
                "format_version": 1,
                "partitions": {
                    "2025/regular": {
                        "status": "complete",
                        "pipeline_version": PIPELINE_VERSION,
                        "output_path": self.source.as_posix(),
                        "output_sha256": sha256(self.source),
                        "output_file_size": self.source.stat().st_size,
                        "normalized_row_count": 0,
                    }
                },
            },
        )
        self.output_root = self.root / "possessions"
        self.manifest = self.root / "possessions.json"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def materialize(self):
        return materialize_partition(
            self.source,
            normalization_manifest=self.normalization_manifest,
            output_root=self.output_root,
            manifest_path=self.manifest,
            season=2025,
            game_type="regular",
        )

    @patch(
        "nba_timeout_decision.possessions.workflows.runner.reconstruct_partition"
    )
    def test_reuses_only_valid_manifest_output(self, reconstruct) -> None:
        reconstruct.return_value = PartitionReconstruction(
            table=pa.Table.from_pylist([], schema=POSSESSION_SCHEMA),
            source_event_count=0,
            accepted_game_count=0,
            rejected_games=(),
            warnings=(),
        )

        first = self.materialize()
        second = self.materialize()
        second.path.write_bytes(b"corrupt output")
        third = self.materialize()

        self.assertEqual(first.status, "written")
        self.assertEqual(second.status, "reused")
        self.assertEqual(third.status, "written")
        self.assertEqual(reconstruct.call_count, 2)

    def test_records_input_validation_failure(self) -> None:
        self.source.write_bytes(b"corrupt source")

        with self.assertRaises(Exception):
            self.materialize()

        record = read_manifest(self.manifest)["partitions"]["2025/regular"]
        self.assertEqual(record["status"], "failed")
        self.assertIn("error", record)
        self.assertFalse(record["stale_output_present"])


if __name__ == "__main__":
    unittest.main()
