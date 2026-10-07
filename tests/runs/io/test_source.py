"""Tests for manifest-valid possession input."""

import tempfile
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as parquet

from nba_timeout_decision.possessions.contract import POSSESSION_SCHEMA
from nba_timeout_decision.possessions.io.manifest import write_manifest
from nba_timeout_decision.possessions.io.storage import sha256
from nba_timeout_decision.possessions.workflows.runner import RECONSTRUCTION_VERSION
from nba_timeout_decision.runs.io.source import validate_source_partition


class RunSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "possessions" / "2025" / "regular.parquet"
        self.source.parent.mkdir(parents=True)
        parquet.write_table(
            pa.Table.from_pylist([], schema=POSSESSION_SCHEMA), self.source
        )
        self.manifest = self.root / "possession-manifest.json"
        self.record = {
            "status": "complete",
            "reconstruction_version": RECONSTRUCTION_VERSION,
            "output_path": self.source.as_posix(),
            "output_sha256": sha256(self.source),
            "output_file_size": self.source.stat().st_size,
            "possession_count": 0,
            "accepted_game_count": 0,
            "rejected_game_count": 0,
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_record(self) -> None:
        write_manifest(
            self.manifest,
            {"format_version": 1, "partitions": {"2025/regular": self.record}},
        )

    def test_accepts_manifest_valid_possession_source(self) -> None:
        self.write_record()

        result = validate_source_partition(
            self.source,
            self.manifest,
            season=2025,
            game_type="regular",
        )

        self.assertEqual(result.row_count, 0)
        self.assertEqual(result.game_count, 0)
        self.assertEqual(result.sha256, self.record["output_sha256"])

    def test_rejects_partition_with_upstream_game_failures(self) -> None:
        self.record["rejected_game_count"] = 1
        self.write_record()

        with self.assertRaisesRegex(ValueError, "rejected games"):
            validate_source_partition(
                self.source,
                self.manifest,
                season=2025,
                game_type="regular",
            )


if __name__ == "__main__":
    unittest.main()
