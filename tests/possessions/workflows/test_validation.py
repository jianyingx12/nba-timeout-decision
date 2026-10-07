"""Tests for possession manifest validation."""

import tempfile
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as parquet

from nba_timeout_decision.io.files import sha256
from nba_timeout_decision.io.manifest import write_manifest
from nba_timeout_decision.normalization.workflows.pipeline import CANONICAL_COLUMNS
from nba_timeout_decision.normalization.workflows.runner import PIPELINE_VERSION
from nba_timeout_decision.possessions.contract import POSSESSION_SCHEMA
from nba_timeout_decision.io.manifest import (
    write_manifest as write_possession_manifest,
)
from nba_timeout_decision.possessions.io.storage import write_partition
from nba_timeout_decision.possessions.workflows.runner import (
    RECONSTRUCTION_VERSION,
)
from nba_timeout_decision.possessions.workflows.validation import (
    validate_possessions,
)


class PossessionValidationTests(unittest.TestCase):
    def test_validates_manifest_input_and_output_together(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "events" / "2025" / "regular.parquet"
            source.parent.mkdir(parents=True)
            source_table = pa.table(
                {name: pa.array([], type=pa.null()) for name in CANONICAL_COLUMNS}
            )
            parquet.write_table(source_table, source)
            normalization_manifest = root / "normalization.json"
            write_manifest(
                normalization_manifest,
                {
                    "format_version": 1,
                    "partitions": {
                        "2025/regular": {
                            "status": "complete",
                            "pipeline_version": PIPELINE_VERSION,
                            "output_path": source.as_posix(),
                            "output_sha256": sha256(source),
                            "output_file_size": source.stat().st_size,
                            "normalized_row_count": 0,
                        }
                    },
                },
            )
            output = root / "possessions" / "2025" / "regular.parquet"
            stored = write_partition(
                pa.Table.from_pylist([], schema=POSSESSION_SCHEMA), output
            )
            possession_manifest = root / "possessions.json"
            write_possession_manifest(
                possession_manifest,
                {
                    "format_version": 1,
                    "partitions": {
                        "2025/regular": {
                            "status": "complete",
                            "reconstruction_version": RECONSTRUCTION_VERSION,
                            "input_path": source.as_posix(),
                            "input_sha256": sha256(source),
                            "source_event_count": 0,
                            "output_path": output.as_posix(),
                            "output_sha256": stored.sha256,
                            "output_file_size": stored.file_size,
                            "possession_count": 0,
                            "accepted_game_count": 0,
                            "rejected_game_count": 0,
                            "rejected_games": [],
                            "warnings": {},
                        }
                    },
                },
            )

            report = validate_possessions(
                manifest_path=possession_manifest,
                normalization_manifest=normalization_manifest,
                seasons=[2025],
                game_types=["regular"],
            )

            self.assertTrue(report["valid"])
            self.assertEqual(report["partitions"], 1)
            self.assertEqual(report["issues"], [])


if __name__ == "__main__":
    unittest.main()
