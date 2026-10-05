"""Tests for possession output storage."""

import tempfile
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as parquet

from nba_timeout_decision.possessions.contract import POSSESSION_SCHEMA
from nba_timeout_decision.possessions.io.storage import (
    inspect_partition,
    possession_path,
    write_partition,
)


class PossessionStorageTests(unittest.TestCase):
    def test_writes_partition_atomically_to_deterministic_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = possession_path(root, 2025, "regular")
            table = pa.Table.from_pylist([], schema=POSSESSION_SCHEMA)

            stored = write_partition(table, path)

            self.assertEqual(path, root / "2025" / "regular.parquet")
            self.assertEqual(stored.row_count, 0)
            self.assertEqual(inspect_partition(path), stored)
            self.assertEqual(parquet.read_table(path), table)
            self.assertEqual(list(path.parent.glob("*.part-*")), [])

    def test_rejects_noncanonical_schema_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "regular.parquet"

            with self.assertRaisesRegex(ValueError, "canonical schema"):
                write_partition(pa.table({"game_id": ["0022500001"]}), path)

            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
