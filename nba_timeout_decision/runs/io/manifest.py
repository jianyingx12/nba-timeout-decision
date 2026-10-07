"""Read and update the scoring-run manifest."""

import json
import os
from pathlib import Path

FORMAT_VERSION = 1


def partition_key(season: int, game_type: str) -> str:
    return f"{season}/{game_type}"


def read_manifest(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"format_version": FORMAT_VERSION, "partitions": {}}

    with path.open(encoding="utf-8") as source:
        manifest = json.load(source)
    if manifest.get("format_version") != FORMAT_VERSION:
        raise ValueError("Unsupported run manifest version")
    if not isinstance(manifest.get("partitions"), dict):
        raise ValueError("Run manifest has invalid partitions")
    return manifest


def write_manifest(path: Path, manifest: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.part-{os.getpid()}")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as output:
            json.dump(manifest, output, indent=2, sort_keys=True)
            output.write("\n")
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def upsert_partition(
    path: Path, season: int, game_type: str, record: dict[str, object]
) -> None:
    manifest = read_manifest(path)
    partitions = manifest["partitions"]
    assert isinstance(partitions, dict)
    partitions[partition_key(season, game_type)] = record
    write_manifest(path, manifest)
