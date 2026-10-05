"""Tests for normalized possession source validation."""

import tempfile
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as parquet

from nba_timeout_decision.normalization.io.manifest import write_manifest
from nba_timeout_decision.normalization.workflows.pipeline import CANONICAL_COLUMNS
from nba_timeout_decision.normalization.workflows.runner import PIPELINE_VERSION
from nba_timeout_decision.possessions.io.source import validate_source_partition
from nba_timeout_decision.possessions.io.storage import sha256


class PossessionSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "events" / "2025" / "regular.parquet"
        self.source.parent.mkdir(parents=True)
        table = pa.table(
            {name: pa.array([], type=pa.null()) for name in CANONICAL_COLUMNS}
        )
        parquet.write_table(table, self.source)
        self.manifest = self.root / "normalization.json"
        self.record = {
            "status": "complete",
            "pipeline_version": PIPELINE_VERSION,
            "output_path": self.source.as_posix(),
            "output_sha256": sha256(self.source),
            "output_file_size": self.source.stat().st_size,
            "normalized_row_count": 0,
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_record(self) -> None:
        write_manifest(
            self.manifest,
            {"format_version": 1, "partitions": {"2025/regular": self.record}},
        )

    def test_accepts_source_that_matches_normalization_manifest(self) -> None:
        self.write_record()

        result = validate_source_partition(
            self.source,
            self.manifest,
            season=2025,
            game_type="regular",
        )

        self.assertEqual(result.row_count, 0)
        self.assertEqual(result.sha256, self.record["output_sha256"])

    def test_rejects_source_with_stale_hash(self) -> None:
        self.record["output_sha256"] = "stale"
        self.write_record()

        with self.assertRaisesRegex(ValueError, "hash"):
            validate_source_partition(
                self.source,
                self.manifest,
                season=2025,
                game_type="regular",
            )


if __name__ == "__main__":
    unittest.main()
