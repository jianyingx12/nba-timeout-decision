"""Reconstruct every game in one canonical event partition."""

from collections import Counter, defaultdict
from dataclasses import dataclass

import pyarrow as pa

from ..contract import POSSESSION_SCHEMA
from ..models import PossessionRejection
from .reconstruct import reconstruct_game

INPUT_COLUMNS = (
    "game_id",
    "season",
    "season_start_year",
    "game_type",
    "game_date",
    "source_row_number",
    "action_id",
    "period",
    "seconds_remaining_in_period",
    "event_team_id",
    "event_team_code",
    "event_team_role",
    "action_type",
    "event_type",
    "event_subtype",
    "description",
    "shot_result",
    "home_score",
    "away_score",
    "score_update_is_unexplained",
    "score_update_is_revision",
)


@dataclass(frozen=True)
class PartitionReconstruction:
    table: pa.Table
    source_event_count: int
    accepted_game_count: int
    rejected_games: tuple[PossessionRejection, ...]
    warnings: tuple[tuple[str, int], ...]


def reconstruct_partition(events: pa.Table) -> PartitionReconstruction:
    missing = sorted(set(INPUT_COLUMNS) - set(events.column_names))
    if missing:
        raise ValueError(f"Canonical partition is missing columns: {missing}")

    selected = events.select(INPUT_COLUMNS)
    games: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in selected.to_pylist():
        games[str(row["game_id"])].append(row)

    tables: list[pa.Table] = []
    rejections: list[PossessionRejection] = []
    warning_counts: Counter[str] = Counter()
    for game_id, rows in games.items():
        try:
            result = reconstruct_game(pa.Table.from_pylist(rows))
        except (TypeError, ValueError) as error:
            rejections.append(
                PossessionRejection(
                    game_id=game_id,
                    reason=str(error),
                    event_count=len(rows),
                )
            )
            continue

        tables.append(result.table)
        warning_counts["ignored_events"] += result.ignored_event_count
        warning_counts["ambiguous_possessions"] += sum(
            result.table["possession_is_ambiguous"].to_pylist()
        )

    table = (
        pa.concat_tables(tables)
        if tables
        else pa.Table.from_pylist([], schema=POSSESSION_SCHEMA)
    )
    return PartitionReconstruction(
        table=table,
        source_event_count=events.num_rows,
        accepted_game_count=len(games) - len(rejections),
        rejected_games=tuple(rejections),
        warnings=tuple(
            sorted((name, count) for name, count in warning_counts.items() if count)
        ),
    )
