"""Tests for partition materialization."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pyarrow as pa

from nba_timeout_decision.normalization.io.manifest import read_manifest
from nba_timeout_decision.normalization.workflows.pipeline import (
    CANONICAL_COLUMNS,
    PartitionNormalization,
)
from nba_timeout_decision.normalization.workflows.runner import materialize_partition


def normalization_result() -> PartitionNormalization:
    table = pa.table(
        {name: pa.array([None], type=pa.null()) for name in CANONICAL_COLUMNS}
    )
    return PartitionNormalization(
        table=table,
        source_row_count=1,
        rejected_games=(),
        warnings=(),
    )


class NormalizationRunnerTests(unittest.TestCase):
    def test_reuses_output_only_when_inputs_and_output_match_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "raw" / "regular.parquet"
            catalog = root / "catalog.csv"
            source.parent.mkdir()
            source.write_bytes(b"source-v1")
            catalog.write_bytes(b"catalog-v1")

            with patch(
                "nba_timeout_decision.normalization.workflows.runner.normalize_partition",
                return_value=normalization_result(),
            ) as normalize:
                first = materialize_partition(
                    source,
                    catalog,
                    raw_root=root / "raw",
                    output_root=root / "normalized",
                    manifest_path=root / "manifest.json",
                    season=2025,
                    game_type="regular",
                )
                second = materialize_partition(
                    source,
                    catalog,
                    raw_root=root / "raw",
                    output_root=root / "normalized",
                    manifest_path=root / "manifest.json",
                    season=2025,
                    game_type="regular",
                )
                second.path.write_bytes(b"corrupt output")
                third = materialize_partition(
                    source,
                    catalog,
                    raw_root=root / "raw",
                    output_root=root / "normalized",
                    manifest_path=root / "manifest.json",
                    season=2025,
                    game_type="regular",
                )
                source.write_bytes(b"source-v2")
                fourth = materialize_partition(
                    source,
                    catalog,
                    raw_root=root / "raw",
                    output_root=root / "normalized",
                    manifest_path=root / "manifest.json",
                    season=2025,
                    game_type="regular",
                )

            self.assertEqual(first.status, "written")
            self.assertEqual(second.status, "reused")
            self.assertEqual(third.status, "written")
            self.assertEqual(fourth.status, "written")
            self.assertEqual(normalize.call_count, 3)

    def test_records_failure_and_marks_existing_output_as_stale(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "raw" / "regular.parquet"
            catalog = root / "catalog.csv"
            source.parent.mkdir()
            source.write_bytes(b"source-v1")
            catalog.write_bytes(b"catalog-v1")
            output = root / "normalized" / "2025" / "regular.parquet"
            output.parent.mkdir(parents=True)
            output.write_bytes(b"old output")
            manifest_path = root / "manifest.json"

            with patch(
                "nba_timeout_decision.normalization.workflows.runner.normalize_partition",
                side_effect=ValueError("invalid partition"),
            ):
                with self.assertRaisesRegex(ValueError, "invalid partition"):
                    materialize_partition(
                        source,
                        catalog,
                        raw_root=root / "raw",
                        output_root=root / "normalized",
                        manifest_path=manifest_path,
                        season=2025,
                        game_type="regular",
                    )

            record = read_manifest(manifest_path)["partitions"]["2025/regular"]
            self.assertEqual(record["status"], "failed")
            self.assertTrue(record["stale_output_present"])
            self.assertNotIn("output_sha256", record)


if __name__ == "__main__":
    unittest.main()
