"""Normalize event types and details."""

from collections import Counter
from dataclasses import dataclass

import pyarrow as pa

from .table_ops import set_column

EVENT_TYPES = {
    "Game": "game_marker",
    "period": "period_marker",
    "Made Shot": "made_shot",
    "Missed Shot": "missed_shot",
    "Heave": "heave",
    "Free Throw": "free_throw",
    "Rebound": "rebound",
    "Turnover": "turnover",
    "Foul": "foul",
    "Violation": "violation",
    "Jump Ball": "jump_ball",
    "Timeout": "timeout",
    "Substitution": "substitution",
    "Instant Replay": "review",
    "Ejection": "ejection",
}


@dataclass(frozen=True)
class EventNormalization:
    table: pa.Table
    unmapped_labels: tuple[tuple[str, int], ...]


def _boolean_column(table: pa.Table, source_name: str) -> pa.Array:
    values = table[source_name].to_pylist()
    unexpected = sorted({value for value in values if value not in {None, 0, 1}})
    if unexpected:
        raise ValueError(f"Unexpected {source_name} values: {unexpected}")
    return pa.array(
        [None if value is None else bool(value) for value in values], type=pa.bool_()
    )


def normalize_events(table: pa.Table) -> EventNormalization:
    action_types = table["action_type"].cast(pa.string()).to_pylist()
    event_types: list[str] = []
    unmapped: Counter[str] = Counter()
    for action_type in action_types:
        if action_type is None:
            event_types.append("other")
        elif action_type in EVENT_TYPES:
            event_types.append(EVENT_TYPES[action_type])
        else:
            event_types.append("other")
            unmapped[action_type] += 1

    normalized = set_column(
        table, "event_type", pa.array(event_types, type=pa.string())
    )
    normalized = set_column(
        normalized, "x_legacy", table["xLegacy"].cast(pa.int64())
    )
    normalized = set_column(
        normalized, "y_legacy", table["yLegacy"].cast(pa.int64())
    )
    normalized = set_column(
        normalized, "shot_distance", table["shotDistance"].cast(pa.int64())
    )
    normalized = set_column(
        normalized, "is_field_goal", _boolean_column(table, "isFieldGoal")
    )
    normalized = set_column(
        normalized, "points_total", table["pointsTotal"].cast(pa.int64())
    )
    normalized = set_column(
        normalized, "video_available", _boolean_column(table, "videoAvailable")
    )
    normalized = set_column(
        normalized, "shot_value", table["shotValue"].cast(pa.int64())
    )
    return EventNormalization(
        table=normalized,
        unmapped_labels=tuple(sorted(unmapped.items())),
    )
