"""Detect scoring runs for every game in one possession partition."""

from collections import Counter, defaultdict
from dataclasses import dataclass

import pyarrow as pa

from ...possessions.contract import POSSESSION_SCHEMA
from ..contract import (
    RUN_SCHEMA,
    SENSITIVITY_SIGNAL_SCHEMA,
    THRESHOLD_CROSSING_SCHEMA,
)
from ..detection import detect_primary_runs
from ..io.catalog import GameTeams
from ..ledger.builder import build_game_ledger
from ..sensitivity import sensitivity_signals
from ..signals import primary_window_signals


@dataclass(frozen=True)
class GameRejection:
    game_id: str
    reason: str
    possession_count: int


@dataclass(frozen=True)
class PartitionRuns:
    runs: pa.Table
    threshold_crossings: pa.Table
    sensitivity_signals: pa.Table
    source_possession_count: int
    accepted_game_count: int
    rejected_games: tuple[GameRejection, ...]
    reset_counts: tuple[tuple[str, int], ...]
    catalog_only_game_count: int


def _concat(tables: list[pa.Table], schema: pa.Schema) -> pa.Table:
    return pa.concat_tables(tables) if tables else pa.Table.from_pylist([], schema=schema)


def detect_partition(
    possessions: pa.Table, game_teams: dict[str, GameTeams]
) -> PartitionRuns:
    if not possessions.schema.equals(POSSESSION_SCHEMA):
        raise ValueError("Possession partition does not match the canonical schema")

    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in possessions.to_pylist():
        grouped[str(row["game_id"])].append(row)
    possession_ids = set(grouped)
    catalog_ids = set(game_teams)
    missing_catalog = sorted(possession_ids - catalog_ids)
    if missing_catalog:
        raise ValueError(
            "Possession games are missing from the catalog: "
            f"{missing_catalog[:5]}"
        )

    run_tables: list[pa.Table] = []
    crossing_tables: list[pa.Table] = []
    sensitivity_tables: list[pa.Table] = []
    rejections: list[GameRejection] = []
    resets: Counter[str] = Counter()

    for game_id in sorted(grouped):
        rows = grouped[game_id]
        teams = game_teams[game_id]
        try:
            game = pa.Table.from_pylist(rows, schema=POSSESSION_SCHEMA)
            ledger = build_game_ledger(
                game,
                home_team_code=teams.home_team_code,
                away_team_code=teams.away_team_code,
            )
            primary_signals = primary_window_signals(ledger.table)
            detected = detect_primary_runs(ledger.table, signals=primary_signals)
            sensitivity = sensitivity_signals(
                ledger.table, primary_signals=primary_signals
            )
        except (TypeError, ValueError) as error:
            rejections.append(GameRejection(game_id, str(error), len(rows)))
            continue

        run_tables.append(detected.runs)
        crossing_tables.append(detected.threshold_crossings)
        sensitivity_tables.append(sensitivity)
        resets.update(dict(ledger.reset_counts))

    return PartitionRuns(
        runs=_concat(run_tables, RUN_SCHEMA),
        threshold_crossings=_concat(crossing_tables, THRESHOLD_CROSSING_SCHEMA),
        sensitivity_signals=_concat(sensitivity_tables, SENSITIVITY_SIGNAL_SCHEMA),
        source_possession_count=possessions.num_rows,
        accepted_game_count=len(grouped) - len(rejections),
        rejected_games=tuple(rejections),
        reset_counts=tuple(sorted(resets.items())),
        catalog_only_game_count=len(catalog_ids - possession_ids),
    )
