"""Downloaded file validation and hashing."""

import hashlib
import os
from pathlib import Path

PARQUET_MAGIC = b"PAR1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_parquet(path: Path, expected_size: int | None = None) -> int:
    size = path.stat().st_size
    if size < 12:
        raise ValueError(f"File is too small to be Parquet: {size} bytes")
    if expected_size is not None and size != expected_size:
        raise ValueError(f"Size mismatch: expected {expected_size} bytes, received {size}")

    with path.open("rb") as source:
        header = source.read(4)
        source.seek(-4, os.SEEK_END)
        footer = source.read(4)
    if header != PARQUET_MAGIC or footer != PARQUET_MAGIC:
        raise ValueError("File does not have valid Parquet boundary markers")
    return size
