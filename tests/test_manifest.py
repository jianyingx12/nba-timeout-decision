import csv
import tempfile
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as parquet

from nba_timeout_decision.acquisition.manifest import success_record, upsert


class ManifestTests(unittest.TestCase):
    def test_cached_update_preserves_live_source_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            partition = root / "partition.parquet"
            manifest = root / "partitions.csv"
            parquet.write_table(pa.table({"value": [1, 2, 3]}), partition)

            downloaded = {
                "status": "downloaded",
                "url": "https://example.test/partition.parquet",
                "path": str(partition),
                "bytes": partition.stat().st_size,
                "sha256": "abc123",
                "attempt": 1,
                "http_status": 200,
                "source_revision": "revision-1",
                "source_object_id": "object-1",
            }
            upsert(
                manifest,
                success_record(
                    data_type="shotdetail",
                    season=2013,
                    season_type="playoffs",
                    result=downloaded,
                ),
            )

            cached = {
                "status": "cached",
                "url": downloaded["url"],
                "path": str(partition),
                "bytes": partition.stat().st_size,
                "sha256": "abc123",
                "attempt": 0,
            }
            upsert(
                manifest,
                success_record(
                    data_type="shotdetail",
                    season=2013,
                    season_type="playoffs",
                    result=cached,
                ),
            )

            with manifest.open(encoding="utf-8", newline="") as source:
                rows = list(csv.DictReader(source))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["download_status"], "cached")
            self.assertEqual(rows[0]["attempt_count"], "0")
            self.assertEqual(rows[0]["source_revision"], "revision-1")
            self.assertEqual(rows[0]["source_object_id"], "object-1")
            self.assertEqual(rows[0]["http_status"], "200")
            self.assertEqual(rows[0]["row_count"], "3")


if __name__ == "__main__":
    unittest.main()
