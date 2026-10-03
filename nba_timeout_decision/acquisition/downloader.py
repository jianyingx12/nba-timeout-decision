"""Cached partition downloads with validation and retries."""

import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import archive
from .files import sha256, validate_parquet


def _cached_result(path: Path, source_url: str) -> dict[str, object]:
    size = validate_parquet(path)
    return {
        "status": "cached",
        "url": source_url,
        "path": str(path),
        "bytes": size,
        "sha256": sha256(path),
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
        return _cached_result(target, source_url)

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.part-{os.getpid()}")
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            request = Request(source_url, headers={"User-Agent": "nba-timeout-decision"})
            with urlopen(request, timeout=timeout_seconds) as response:
                size_header = response.headers.get("Content-Length")
                expected_size = int(size_header) if size_header else None
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
            }
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
            last_error = error
            temporary.unlink(missing_ok=True)
            if attempt < attempts:
                time.sleep(2 ** (attempt - 1))

    raise RuntimeError(f"Download failed after {attempts} attempts: {last_error}") from last_error
