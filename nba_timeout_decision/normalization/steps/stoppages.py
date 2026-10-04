"""Normalize substitutions and stoppage events."""

import re
from collections import Counter
from dataclasses import dataclass

import pyarrow as pa

from .table_ops import set_column

SUBSTITUTION_PATTERN = re.compile(r"^SUB:\s*(?P<incoming>.+?)\s+FOR\s+.+?\s*$")
INJURY_PATTERN = re.compile(r"\binjur(?:y|ed|ies)\b", re.IGNORECASE)

STOPPAGE_CLASSES = {
    "timeout": "timeout",
    "substitution": "substitution",
    "review": "review",
    "period_marker": "period_break",
    "foul": "foul",
    "free_throw": "free_throw",
    "violation": "other",
    "ejection": "other",
}


@dataclass(frozen=True)
class StoppageNormalization:
    table: pa.Table
    class_counts: tuple[tuple[str, int], ...]
    ambiguous_substitution_count: int


def _stoppage_class(event_type: str, description: str | None) -> str:
    if event_type in STOPPAGE_CLASSES:
        return STOPPAGE_CLASSES[event_type]
    if description is not None and INJURY_PATTERN.search(description):
        return "injury"
    return "none"


def normalize_stoppages(table: pa.Table) -> StoppageNormalization:
    event_types = table["event_type"].cast(pa.string()).to_pylist()
    descriptions = table["description"].cast(pa.string()).to_pylist()
    person_ids = table["person_id"].cast(pa.int64()).to_pylist()
    event_team_ids = table["event_team_id"].cast(pa.int64()).to_pylist()

    stoppage_classes: list[str] = []
    substitution_team_ids: list[int | None] = []
    outgoing_player_ids: list[int | None] = []
    incoming_player_ids: list[int | None] = []
    incoming_player_names: list[str | None] = []
    ambiguous_substitutions: list[bool] = []

    for event_type, description, person_id, team_id in zip(
        event_types, descriptions, person_ids, event_team_ids, strict=True
    ):
        stoppage_classes.append(_stoppage_class(event_type, description))
        if event_type != "substitution":
            substitution_team_ids.append(None)
            outgoing_player_ids.append(None)
            incoming_player_ids.append(None)
            incoming_player_names.append(None)
            ambiguous_substitutions.append(False)
            continue

        match = SUBSTITUTION_PATTERN.fullmatch(description or "")
        incoming_name = match.group("incoming").strip() if match else None
        substitution_team_ids.append(team_id)
        outgoing_player_ids.append(person_id)
        incoming_player_ids.append(None)
        incoming_player_names.append(incoming_name)
        ambiguous_substitutions.append(
            team_id is None or person_id is None or incoming_name is None
        )

    normalized = set_column(
        table,
        "stoppage_class",
        pa.array(stoppage_classes, type=pa.string()),
    )
    normalized = set_column(
        normalized,
        "substitution_team_id",
        pa.array(substitution_team_ids, type=pa.int64()),
    )
    normalized = set_column(
        normalized,
        "substitution_out_player_id",
        pa.array(outgoing_player_ids, type=pa.int64()),
    )
    normalized = set_column(
        normalized,
        "substitution_in_player_id",
        pa.array(incoming_player_ids, type=pa.int64()),
    )
    normalized = set_column(
        normalized,
        "substitution_in_player_name",
        pa.array(incoming_player_names, type=pa.string()),
    )
    normalized = set_column(
        normalized,
        "substitution_is_ambiguous",
        pa.array(ambiguous_substitutions, type=pa.bool_()),
    )
    return StoppageNormalization(
        table=normalized,
        class_counts=tuple(sorted(Counter(stoppage_classes).items())),
        ambiguous_substitution_count=sum(ambiguous_substitutions),
    )
