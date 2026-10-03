import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from nba_timeout_decision.acquisition.batch import acquire
from nba_timeout_decision.acquisition.downloader import DownloadError


def downloaded_result(data_type: str, season: int, game_type: str) -> dict[str, object]:
    return {
        "status": "downloaded",
        "url": "https://example.test/file.parquet",
        "path": f"data/raw/{data_type}/{season}/{game_type}.parquet",
        "bytes": 100,
        "sha256": "abc123",
        "attempt": 1,
        "http_status": 200,
    }


class BatchTests(unittest.TestCase):
    def test_batch_continues_after_failure_and_throttles_remote_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            responses = [
                downloaded_result("nbastatsv3", 2013, "playoffs"),
                DownloadError("not found", attempts=1, http_status=404),
            ]
            sleep = Mock()

            with (
                patch(
                    "nba_timeout_decision.acquisition.batch.download",
                    side_effect=responses,
                ),
                patch("nba_timeout_decision.acquisition.batch.success_record", return_value={}),
                patch("nba_timeout_decision.acquisition.batch.failure_record", return_value={}),
                patch("nba_timeout_decision.acquisition.batch.upsert") as upsert,
            ):
                summary = acquire(
                    seasons=[2013],
                    data_types=["nbastatsv3", "shotdetail"],
                    season_types=["playoffs"],
                    output_root=root / "raw",
                    manifest_path=root / "manifest.csv",
                    refresh=False,
                    attempts=2,
                    timeout_seconds=10,
                    interval_seconds=1.5,
                    sleep=sleep,
                )

            self.assertEqual(summary["requested"], 2)
            self.assertEqual(summary["downloaded"], 1)
            self.assertEqual(summary["failed"], 1)
            self.assertEqual(upsert.call_count, 2)
            sleep.assert_called_once_with(1.5)


if __name__ == "__main__":
    unittest.main()
