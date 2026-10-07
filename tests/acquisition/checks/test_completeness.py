"""Tests for acquisition completeness checks."""

import csv
import tempfile
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as parquet

from nba_timeout_decision.acquisition.checks.completeness import build_report
from nba_timeout_decision.io.files import sha256
from nba_timeout_decision.acquisition.download.manifest import FIELDS


def write_partition(path: Path, data_type: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    game_id_column = "gameId" if data_type == "nbastatsv3" else "GAME_ID"
    parquet.write_table(
        pa.table(
            {
                game_id_column: [41300101, 41300101, 41300102],
                "_season": [2013, 2013, 2013],
                "_season_type": ["po", "po", "po"],
            }
        ),
        path,
    )


def manifest_row(path: Path, data_type: str, digest: str | None = None) -> dict[str, str]:
    values = {field: "" for field in FIELDS}
    values.update(
        {
            "source": "test",
            "source_url": "https://example.test/file.parquet",
            "data_type": data_type,
            "season": "2013",
            "game_type": "playoffs",
            "local_path": str(path),
            "sha256": digest or sha256(path),
            "download_status": "downloaded",
            "attempt_count": "1",
            "row_count": "3",
            "file_size": str(path.stat().st_size),
        }
    )
    return values


def write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


class CompletenessTests(unittest.TestCase):
    def test_complete_partition_pair(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pbp = root / "raw" / "nbastatsv3.parquet"
            shots = root / "raw" / "shotdetail.parquet"
            manifest = root / "manifest.csv"
            write_partition(pbp, "nbastatsv3")
            write_partition(shots, "shotdetail")
            write_manifest(
                manifest,
                [manifest_row(pbp, "nbastatsv3"), manifest_row(shots, "shotdetail")],
            )

            report = build_report(
                manifest_path=manifest,
                raw_root=root / "raw",
                project_root=root,
                first_season=2013,
                last_season=2013,
            )

            summary = report["summary"]
            self.assertEqual(summary["valid_partitions"], 2)
            self.assertEqual(summary["missing_partitions"], 2)
            self.assertEqual(summary["mismatched_game_sets"], 0)
            self.assertEqual(summary["games_in_matched_partitions"], 2)
            self.assertEqual(summary["play_by_play_events"], 3)

    def test_missing_partition_and_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pbp = root / "raw" / "nbastatsv3.parquet"
            manifest = root / "manifest.csv"
            write_partition(pbp, "nbastatsv3")
            write_manifest(manifest, [manifest_row(pbp, "nbastatsv3", digest="wrong")])

            report = build_report(
                manifest_path=manifest,
                raw_root=root / "raw",
                project_root=root,
                first_season=2013,
                last_season=2013,
            )

            summary = report["summary"]
            self.assertEqual(summary["valid_partitions"], 0)
            self.assertEqual(summary["invalid_partitions"], 1)
            self.assertEqual(summary["missing_partitions"], 3)
            self.assertEqual(summary["issue_counts"], {"hash_mismatch": 1})


if __name__ == "__main__":
    unittest.main()
