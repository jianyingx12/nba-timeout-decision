import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from nba_timeout_decision.acquisition.downloader import DownloadError, download

PARQUET_BYTES = b"PAR1dataPAR1"


class FakeResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.offset = 0
        self.status = 200
        self.headers = {
            "Content-Length": str(len(content)),
            "ETag": '"source-object-id"',
        }

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, size: int) -> bytes:
        chunk = self.content[self.offset : self.offset + size]
        self.offset += len(chunk)
        return chunk


class DownloaderTests(unittest.TestCase):
    def test_download_writes_valid_file_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory)
            with patch(
                "nba_timeout_decision.acquisition.downloader.urlopen",
                return_value=FakeResponse(PARQUET_BYTES),
            ):
                result = download(
                    data_type="shotdetail",
                    season=2013,
                    season_type="playoffs",
                    output_root=output_root,
                )

            target = output_root / "shotdetail" / "2013" / "playoffs.parquet"
            self.assertEqual(target.read_bytes(), PARQUET_BYTES)
            self.assertEqual(result["status"], "downloaded")
            self.assertEqual(result["source_object_id"], "source-object-id")
            self.assertEqual(result["sha256"], hashlib.sha256(PARQUET_BYTES).hexdigest())
            self.assertEqual(list(target.parent.glob("*.part-*")), [])

    def test_valid_cache_avoids_network_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory)
            target = output_root / "shotdetail" / "2013" / "playoffs.parquet"
            target.parent.mkdir(parents=True)
            target.write_bytes(PARQUET_BYTES)

            with patch(
                "nba_timeout_decision.acquisition.downloader.urlopen",
                side_effect=AssertionError("network should not be called"),
            ):
                result = download(
                    data_type="shotdetail",
                    season=2013,
                    season_type="playoffs",
                    output_root=output_root,
                )

            self.assertEqual(result["status"], "cached")
            self.assertEqual(result["attempt"], 0)

    def test_retry_succeeds_after_temporary_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch(
                    "nba_timeout_decision.acquisition.downloader.urlopen",
                    side_effect=[URLError("temporary"), FakeResponse(PARQUET_BYTES)],
                ),
                patch("nba_timeout_decision.acquisition.downloader.time.sleep") as sleep,
            ):
                result = download(
                    data_type="shotdetail",
                    season=2013,
                    season_type="playoffs",
                    output_root=Path(directory),
                )

            self.assertEqual(result["attempt"], 2)
            sleep.assert_called_once_with(1)

    def test_invalid_cache_is_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory)
            target = output_root / "shotdetail" / "2013" / "playoffs.parquet"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"invalid")

            with patch(
                "nba_timeout_decision.acquisition.downloader.urlopen",
                return_value=FakeResponse(PARQUET_BYTES),
            ):
                result = download(
                    data_type="shotdetail",
                    season=2013,
                    season_type="playoffs",
                    output_root=output_root,
                )

            self.assertEqual(result["status"], "downloaded")
            self.assertEqual(target.read_bytes(), PARQUET_BYTES)

    def test_nonretryable_http_error_stops_immediately(self) -> None:
        error = HTTPError("https://example.test", 404, "Not Found", None, None)
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch(
                    "nba_timeout_decision.acquisition.downloader.urlopen",
                    side_effect=error,
                ) as request,
                patch("nba_timeout_decision.acquisition.downloader.time.sleep") as sleep,
                self.assertRaises(DownloadError) as raised,
            ):
                download(
                    data_type="shotdetail",
                    season=2013,
                    season_type="playoffs",
                    output_root=Path(directory),
                )

            self.assertEqual(raised.exception.attempts, 1)
            self.assertEqual(raised.exception.http_status, 404)
            self.assertEqual(request.call_count, 1)
            sleep.assert_not_called()

    def test_malformed_download_leaves_no_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory)
            with (
                patch(
                    "nba_timeout_decision.acquisition.downloader.urlopen",
                    side_effect=[FakeResponse(b"invalid"), FakeResponse(b"invalid")],
                ),
                patch("nba_timeout_decision.acquisition.downloader.time.sleep"),
                self.assertRaises(DownloadError) as raised,
            ):
                download(
                    data_type="shotdetail",
                    season=2013,
                    season_type="playoffs",
                    output_root=output_root,
                    attempts=2,
                )

            target = output_root / "shotdetail" / "2013" / "playoffs.parquet"
            self.assertEqual(raised.exception.attempts, 2)
            self.assertFalse(target.exists())
            self.assertEqual(list(target.parent.glob("*.part-*")), [])


if __name__ == "__main__":
    unittest.main()
