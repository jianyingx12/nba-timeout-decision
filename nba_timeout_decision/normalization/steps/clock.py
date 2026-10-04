"""Normalize period and clock values."""

import re

import pyarrow as pa

from .table_ops import set_column

CLOCK_PATTERN = re.compile(r"^PT(?:(\d+)M)?(\d+(?:\.\d+)?)S$")
REGULATION_SECONDS = 12 * 60
OVERTIME_SECONDS = 5 * 60


def parse_clock(value: str) -> float:
    match = CLOCK_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError(f"Invalid game clock: {value!r}")
    minutes = int(match.group(1) or 0)
    seconds = float(match.group(2))
    if seconds >= 60:
        raise ValueError(f"Invalid game clock: {value!r}")
    return minutes * 60 + seconds


def normalize_period_and_clock(table: pa.Table) -> pa.Table:
    game_ids = table["game_id"].cast(pa.string()).to_pylist()
    periods = table["period"].cast(pa.int8()).to_pylist()
    clocks = table["clock"].cast(pa.string()).to_pylist()
    if any(value is None for value in game_ids):
        raise ValueError("game_id contains null values")
    if any(value is None for value in periods):
        raise ValueError("period contains null values")
    if any(value is None for value in clocks):
        raise ValueError("clock contains null values")

    seconds_remaining: list[float] = []
    clock_increases: list[bool] = []
    previous: dict[tuple[str, int], float] = {}

    for game_id, period, clock in zip(game_ids, periods, clocks, strict=True):
        if period < 1:
            raise ValueError(f"Invalid period for game {game_id}: {period}")
        remaining = parse_clock(clock)
        maximum = REGULATION_SECONDS if period <= 4 else OVERTIME_SECONDS
        if remaining > maximum:
            raise ValueError(
                f"Clock exceeds period length for game {game_id}, "
                f"period {period}: {clock}"
            )

        key = (game_id, period)
        prior = previous.get(key)
        clock_increases.append(prior is not None and remaining > prior)
        previous[key] = remaining
        seconds_remaining.append(remaining)

    normalized = set_column(table, "period", pa.array(periods, type=pa.int8()))
    normalized = set_column(
        normalized, "clock", pa.array(clocks, type=pa.string())
    )
    normalized = set_column(
        normalized,
        "seconds_remaining_in_period",
        pa.array(seconds_remaining, type=pa.float64()),
    )
    return set_column(
        normalized,
        "clock_increases_within_period",
        pa.array(clock_increases, type=pa.bool_()),
    )
