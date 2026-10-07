"""Tests for the scoring-run manifest."""

import tempfile
import unittest
from pathlib import Path

from nba_timeout_decision.runs.io.manifest import read_manifest, upsert_partition


class RunManifestTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
