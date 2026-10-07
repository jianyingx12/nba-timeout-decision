"""Tests for shared partition manifests."""

import json
import tempfile
import unittest
from pathlib import Path

from nba_timeout_decision.io.manifest import read_manifest, upsert_partition


class PartitionManifestTests(unittest.TestCase):
    def test_upsert_preserves_other_partitions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"

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

    def test_rejects_unknown_manifest_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(
                json.dumps({"format_version": 2, "partitions": {}}),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "manifest version"):
                read_manifest(path)


if __name__ == "__main__":
    unittest.main()
