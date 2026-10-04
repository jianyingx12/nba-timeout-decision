"""Normalize identifiers and source labels."""

import pyarrow as pa
import pyarrow.compute as pc

from .table_ops import set_column


def _required_int64(table: pa.Table, source_name: str) -> pa.ChunkedArray:
    values = table[source_name].cast(pa.int64())
    if values.null_count:
        raise ValueError(f"{source_name} contains null values")
    return values


def _trimmed_strings(table: pa.Table, source_name: str) -> pa.ChunkedArray:
    values = table[source_name].cast(pa.string())
    trimmed = pc.utf8_trim_whitespace(values)
    return pc.if_else(pc.equal(trimmed, ""), pa.scalar(None, pa.string()), trimmed)


def _validate_action_order(game_ids: list[str], action_ids: list[int]) -> None:
    previous: dict[str, int] = {}
    for game_id, action_id in zip(game_ids, action_ids, strict=True):
        prior = previous.get(game_id)
        if prior is not None and action_id <= prior:
            raise ValueError(
                f"actionId is not strictly increasing for game {game_id}: "
                f"{prior} then {action_id}"
            )
        previous[game_id] = action_id


def normalize_identifiers_and_labels(table: pa.Table) -> pa.Table:
    game_ids = table["game_id"].cast(pa.string())
    if game_ids.null_count:
        raise ValueError("game_id contains null values")

    action_ids = _required_int64(table, "actionId")
    _validate_action_order(game_ids.to_pylist(), action_ids.to_pylist())
    source_action_numbers = table["actionNumber"].cast(pa.int64())
    source_team_ids = _required_int64(table, "teamId")
    source_person_ids = _required_int64(table, "personId")

    event_team_ids = pc.if_else(
        pc.equal(source_team_ids, 0), pa.scalar(None, pa.int64()), source_team_ids
    )
    person_ids = pc.if_else(
        pc.equal(source_person_ids, 0), pa.scalar(None, pa.int64()), source_person_ids
    )

    additions: tuple[tuple[str, pa.Array | pa.ChunkedArray], ...] = (
        ("action_id", action_ids),
        ("source_action_number", source_action_numbers),
        ("source_team_id", source_team_ids),
        ("event_team_id", event_team_ids),
        ("event_team_code", _trimmed_strings(table, "teamTricode")),
        ("source_person_id", source_person_ids),
        ("person_id", person_ids),
        ("player_name", _trimmed_strings(table, "playerName")),
        ("player_name_initial", _trimmed_strings(table, "playerNameI")),
        ("shot_result", _trimmed_strings(table, "shotResult")),
        ("location", _trimmed_strings(table, "location")),
        ("source_action_type", table["actionType"].cast(pa.string())),
        ("source_sub_type", table["subType"].cast(pa.string())),
        ("source_description", table["description"].cast(pa.string())),
        ("action_type", _trimmed_strings(table, "actionType")),
        ("event_subtype", _trimmed_strings(table, "subType")),
        ("description", _trimmed_strings(table, "description")),
    )
    normalized = table
    for name, values in additions:
        normalized = set_column(normalized, name, values)
    return normalized
