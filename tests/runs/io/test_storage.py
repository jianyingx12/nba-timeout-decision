"""Tests for deterministic scoring-run output storage."""

import tempfile
import unittest
from pathlib import Path

import pyarrow as pa

from nba_timeout_decision.runs.contract import (
    RUN_SCHEMA,
    SENSITIVITY_SIGNAL_SCHEMA,
    THRESHOLD_CROSSING_SCHEMA,
)
from nba_timeout_decision.runs.io.storage import (
    inspect_output,
    output_paths,
    write_outputs,
)


class RunStorageTests(unittest.TestCase):
    def test_writes_all_outputs_to_partition_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = output_paths(root, 2025, "regular")

            stored = write_outputs(
                runs=pa.Table.from_pylist([], schema=RUN_SCHEMA),
                threshold_crossings=pa.Table.from_pylist(
                    [], schema=THRESHOLD_CROSSING_SCHEMA
                ),
                sensitivity_signals=pa.Table.from_pylist(
                    [], schema=SENSITIVITY_SIGNAL_SCHEMA
                ),
                paths=paths,
            )

            self.assertEqual(paths.runs, root / "2025" / "regular" / "runs.parquet")
            self.assertEqual(inspect_output(paths.runs), stored.runs)
            self.assertEqual(
                inspect_output(paths.threshold_crossings), stored.threshold_crossings
            )
            self.assertEqual(
                inspect_output(paths.sensitivity_signals), stored.sensitivity_signals
            )
            self.assertEqual(list(paths.runs.parent.glob("*.part-*")), [])

    def test_rejects_noncanonical_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = output_paths(Path(directory), 2025, "regular")

            with self.assertRaisesRegex(ValueError, "canonical schema"):
                write_outputs(
                    runs=pa.table({"game_id": ["1"]}),
                    threshold_crossings=pa.Table.from_pylist(
                        [], schema=THRESHOLD_CROSSING_SCHEMA
                    ),
                    sensitivity_signals=pa.Table.from_pylist(
                        [], schema=SENSITIVITY_SIGNAL_SCHEMA
                    ),
                    paths=paths,
                )


if __name__ == "__main__":
    unittest.main()
