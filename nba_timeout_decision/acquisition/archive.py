"""NBA Data Archive partition locations."""

from pathlib import Path

BASE_URL = (
    "https://huggingface.co/datasets/cdechoch/nba-data-archive/resolve/main/per_season"
)
DATA_TYPES = ("nbastatsv3", "shotdetail")
SEASON_TYPES = ("regular", "playoffs")


def filename(season: int, season_type: str) -> str:
    prefix = "po_" if season_type == "playoffs" else ""
    return f"{prefix}{season}.parquet"


def url(data_type: str, season: int, season_type: str) -> str:
    return f"{BASE_URL}/{data_type}/{filename(season, season_type)}"


def local_path(
    output_root: Path, data_type: str, season: int, season_type: str
) -> Path:
    return output_root / data_type / str(season) / f"{season_type}.parquet"
