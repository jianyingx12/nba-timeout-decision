"""Tests for normalized output storage."""

import tempfile
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as parquet

from nba_timeout_decision.normalization.io.manifest import (
    read_manifest,
    upsert_partition,
)
from nba_timeout_decision.normalization.io.storage import (
    inspect_partition,
    normalized_path,
    write_partition,
)


class NormalizationStorageTests(unittest.TestCase):
    def test_writes_partition_atomically_to_deterministic_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = normalized_path(root, 2025, "regular")
            table = pa.table({"game_id": ["0022500001"], "action_id": [1]})

            stored = write_partition(table, path)

            self.assertEqual(path, root / "2025" / "regular.parquet")
            self.assertEqual(stored.row_count, 1)
            self.assertEqual(inspect_partition(path), stored)
            self.assertEqual(parquet.read_table(path), table)
            self.assertEqual(list(path.parent.glob("*.part-*")), [])

    def test_manifest_upsert_preserves_other_partitions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "normalization.json"

            upsert_partition(path, 2025, "regular", {"status": "complete"})
            upsert_partition(path, 2025, "playoffs", {"status": "failed"})
            manifest = read_manifest(path)

            self.assertEqual(manifest["format_version"], 1)
            self.assertEqual(
                manifest["partitions"],
                {
                    "2025/playoffs": {"status": "failed"},
                    "2025/regular": {"status": "complete"},
                },
            )
            self.assertEqual(list(path.parent.glob("*.part-*")), [])


if __name__ == "__main__":
    unittest.main()
