"""Cached partition downloads with validation and retries."""

import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import archive
from ...io.files import sha256
from .files import validate_parquet


class DownloadError(RuntimeError):
    def __init__(self, message: str, attempts: int, http_status: int | None = None) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.http_status = http_status


def _cached_result(path: Path, source_url: str) -> dict[str, object]:
    size = validate_parquet(path)
    return {
        "status": "cached",
        "url": source_url,
        "path": str(path),
        "bytes": size,
        "sha256": sha256(path),
        "attempt": 0,
    }


def download(
    *,
    data_type: str,
    season: int,
    season_type: str,
    output_root: Path,
    refresh: bool = False,
    attempts: int = 4,
    timeout_seconds: float = 60.0,
) -> dict[str, object]:
    source_url = archive.url(data_type, season, season_type)
    target = archive.local_path(output_root, data_type, season, season_type)

    if target.exists() and not refresh:
        try:
            return _cached_result(target, source_url)
        except ValueError:
            refresh = True

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.part-{os.getpid()}")
    last_error: Exception | None = None
    last_http_status: int | None = None
    attempts_made = 0

    for attempt in range(1, attempts + 1):
        attempts_made = attempt
        try:
            request = Request(source_url, headers={"User-Agent": "nba-timeout-decision"})
            with urlopen(request, timeout=timeout_seconds) as response:
                http_status = response.status
                size_header = response.headers.get("Content-Length")
                expected_size = int(size_header) if size_header else None
                revision = response.headers.get("X-Repo-Commit")
                object_id = response.headers.get("X-Linked-Etag") or response.headers.get("ETag")
                object_id = object_id.strip('"') if object_id else None
                with temporary.open("wb") as destination:
                    while chunk := response.read(1024 * 1024):
                        destination.write(chunk)

            size = validate_parquet(temporary, expected_size)
            digest = sha256(temporary)
            os.replace(temporary, target)
            return {
                "status": "downloaded",
                "url": source_url,
                "path": str(target),
                "bytes": size,
                "sha256": digest,
                "attempt": attempt,
                "http_status": http_status,
                "source_revision": revision,
                "source_object_id": object_id,
            }
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
            last_error = error
            last_http_status = error.code if isinstance(error, HTTPError) else None
            temporary.unlink(missing_ok=True)
            retryable = not isinstance(error, HTTPError) or error.code in {408, 429} or error.code >= 500
            if attempt >= attempts or not retryable:
                break
            time.sleep(2 ** (attempt - 1))

    raise DownloadError(
        f"Download failed after {attempts_made} attempts: {last_error}",
        attempts=attempts_made,
        http_status=last_http_status,
    ) from last_error
