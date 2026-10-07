"""Tests for normalization validation."""

import csv
import tempfile
import unittest
from pathlib import Path

import pyarrow as pa

from nba_timeout_decision.io.manifest import upsert_partition
from nba_timeout_decision.normalization.io.storage import write_partition
from nba_timeout_decision.normalization.workflows.pipeline import CANONICAL_COLUMNS
from nba_timeout_decision.normalization.workflows.runner import PIPELINE_VERSION
from nba_timeout_decision.normalization.workflows.validation import validate_normalization


class NormalizationValidationTests(unittest.TestCase):
    def test_reconciles_manifest_output_and_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "normalized" / "2025" / "regular.parquet"
            table = pa.table(
                {
                    name: pa.array(
                        ["0022500001"] if name == "game_id" else [None]
                    )
                    for name in CANONICAL_COLUMNS
                }
            )
            stored = write_partition(table, output)
            manifest = root / "manifest.json"
            upsert_partition(
                manifest,
                2025,
                "regular",
                {
                    "status": "complete",
                    "pipeline_version": PIPELINE_VERSION,
                    "output_path": output.as_posix(),
                    "output_sha256": stored.sha256,
                    "output_file_size": stored.file_size,
                    "source_row_count": 1,
                    "normalized_row_count": 1,
                    "rejected_games": [],
                    "warnings": {},
                },
            )
            catalog = root / "games.csv"
            with catalog.open("w", encoding="utf-8", newline="") as destination:
                writer = csv.DictWriter(
                    destination,
                    fieldnames=[
                        "game_id",
                        "season_start_year",
                        "game_type",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "game_id": "0022500001",
                        "season_start_year": 2025,
                        "game_type": "regular",
                    }
                )

            report = validate_normalization(
                manifest_path=manifest,
                catalog_path=catalog,
                seasons=[2025],
                game_types=("regular",),
            )

            self.assertTrue(report["valid"])
            self.assertEqual(report["catalog_games"], 1)
            self.assertEqual(report["normalized_games"], 1)
            self.assertEqual(report["issues"], [])

            output.write_bytes(b"corrupt output")
            invalid = validate_normalization(
                manifest_path=manifest,
                catalog_path=catalog,
                seasons=[2025],
                game_types=("regular",),
            )

            self.assertFalse(invalid["valid"])
            self.assertTrue(
                any("output cannot be read" in issue for issue in invalid["issues"])
            )


if __name__ == "__main__":
    unittest.main()
