"""Build primary run episodes and their threshold-crossing histories."""

from dataclasses import dataclass

import pyarrow as pa

from ..contract import (
    RUN_SCHEMA,
    RUN_THRESHOLDS,
    SCORE_LEDGER_COLUMNS,
    THRESHOLD_CROSSING_SCHEMA,
)
from ..signals import WindowSignal, primary_window_signals


@dataclass(frozen=True)
class DetectedRuns:
    runs: pa.Table
    threshold_crossings: pa.Table


@dataclass
class _ActiveRun:
    values: dict[str, object]
    reached_thresholds: set[int]
    last_signal: WindowSignal


def _thresholds(net_points: int) -> tuple[int, ...]:
    return tuple(value for value in RUN_THRESHOLDS if net_points >= value)


def _termination_reason(row: dict[str, object]) -> str:
    reset = row["reset_before_reason"] or row["reset_after_reason"]
    if reset == "ambiguous_possession":
        return "ambiguous_possession"
    if reset == "period_start":
        return "period_end"
    return "net_advantage_lost"


def _last_audit_bounds(row: dict[str, object]) -> tuple[int, int]:
    if row["checkpoint_action_id"] is not None:
        return (
            int(row["checkpoint_action_id"]),
            int(row["checkpoint_source_row_number"]),
        )
    if row["previous_possession_last_action_id"] is not None:
        return (
            int(row["previous_possession_last_action_id"]),
            int(row["previous_possession_last_source_row_number"]),
        )
    return (
        int(row["current_possession_first_action_id"]),
        int(row["current_possession_first_source_row_number"]),
    )


def _start_run(
    *,
    signal: WindowSignal,
    row: dict[str, object],
    run_id: str,
) -> _ActiveRun:
    reached = set(_thresholds(signal.net_points))
    exclusion_reason = None
    if row["reset_after_reason"] == "period_start":
        exclusion_reason = "period_ended_at_qualification"
    elif signal.contains_censored_possession:
        exclusion_reason = "censored_qualification"

    values: dict[str, object] = {
        "game_id": str(row["game_id"]),
        "season": str(row["season"]),
        "season_start_year": int(row["season_start_year"]),
        "game_type": str(row["game_type"]),
        "game_date": row["game_date"],
        "run_id": run_id,
        "period": signal.period,
        "run_team_id": signal.run_team_id,
        "run_team_code": signal.run_team_code,
        "opponent_team_id": signal.opponent_team_id,
        "opponent_team_code": signal.opponent_team_code,
        "start_possession_number": signal.start_possession_number,
        "qualification_possession_number": signal.possession_number,
        "end_possession_number": signal.possession_number,
        "start_checkpoint_number": signal.window_start_checkpoint_number,
        "qualification_checkpoint_number": signal.checkpoint_number,
        "end_checkpoint_number": signal.checkpoint_number,
        "first_action_id": signal.window_start_action_id,
        "qualification_action_id": signal.action_id,
        "last_action_id": _last_audit_bounds(row)[0],
        "first_source_row_number": signal.window_start_source_row_number,
        "qualification_source_row_number": signal.source_row_number,
        "last_source_row_number": _last_audit_bounds(row)[1],
        "window_size": signal.window_size,
        "run_team_points_at_qualification": signal.run_team_points,
        "opponent_points_at_qualification": signal.opponent_points,
        "net_points_at_qualification": signal.net_points,
        "first_threshold": min(reached),
        "maximum_threshold": max(reached),
        "score_margin_before_qualification": signal.score_margin_before,
        "score_margin_at_qualification": signal.score_margin_at_checkpoint,
        "seconds_remaining_at_qualification": signal.seconds_remaining_in_period,
        "run_team_is_home": signal.run_team_is_home,
        "strict_unanswered": signal.strict_unanswered,
        "contains_censored_possession": signal.contains_censored_possession,
        "contains_timeout": signal.contains_timeout,
        "contains_review": signal.contains_review,
        "contains_score_revision": signal.contains_score_revision,
        "between_possession_net_points": signal.between_possession_net_points,
        "termination_reason": "game_end",
        "primary_analysis_eligible": exclusion_reason is None,
        "exclusion_reason": exclusion_reason,
    }
    return _ActiveRun(values=values, reached_thresholds=reached, last_signal=signal)


def _crossing_rows(
    active: _ActiveRun,
    signal: WindowSignal,
    new_thresholds: tuple[int, ...],
) -> list[dict[str, object]]:
    return [
        {
            "game_id": active.values["game_id"],
            "run_id": active.values["run_id"],
            "period": signal.period,
            "run_team_id": signal.run_team_id,
            "run_team_code": signal.run_team_code,
            "threshold": threshold,
            "crossing_sequence": RUN_THRESHOLDS.index(threshold) + 1,
            "checkpoint_number": signal.checkpoint_number,
            "checkpoint_type": signal.checkpoint_type,
            "possession_number": signal.possession_number,
            "action_id": signal.action_id,
            "source_row_number": signal.source_row_number,
            "previous_possession_last_action_id": (
                signal.previous_possession_last_action_id
            ),
            "current_possession_first_action_id": (
                signal.current_possession_first_action_id
            ),
            "previous_possession_last_source_row_number": (
                signal.previous_possession_last_source_row_number
            ),
            "current_possession_first_source_row_number": (
                signal.current_possession_first_source_row_number
            ),
            "seconds_remaining_in_period": signal.seconds_remaining_in_period,
            "run_team_points": signal.run_team_points,
            "opponent_points": signal.opponent_points,
            "net_points": signal.net_points,
            "score_margin": signal.score_margin_at_checkpoint,
        }
        for threshold in new_thresholds
    ]


def _extend_run(
    active: _ActiveRun, signal: WindowSignal, row: dict[str, object]
) -> tuple[int, ...]:
    new_thresholds = tuple(
        value
        for value in _thresholds(signal.net_points)
        if value not in active.reached_thresholds
    )
    active.reached_thresholds.update(new_thresholds)
    last_action_id, last_source_row = _last_audit_bounds(row)
    active.values.update(
        {
            "end_possession_number": signal.possession_number,
            "end_checkpoint_number": signal.checkpoint_number,
            "last_action_id": last_action_id,
            "last_source_row_number": last_source_row,
            "maximum_threshold": max(active.reached_thresholds),
            "contains_censored_possession": bool(
                active.values["contains_censored_possession"]
            )
            or signal.contains_censored_possession,
            "contains_timeout": bool(active.values["contains_timeout"])
            or signal.contains_timeout,
            "contains_review": bool(active.values["contains_review"])
            or signal.contains_review,
            "contains_score_revision": bool(
                active.values["contains_score_revision"]
            )
            or signal.contains_score_revision,
        }
    )
    active.last_signal = signal
    return new_thresholds


def detect_primary_runs(
    ledger: pa.Table, *, signals: tuple[WindowSignal, ...] | None = None
) -> DetectedRuns:
    """Group qualifying primary signals from one game into run episodes."""
    if tuple(ledger.column_names) != SCORE_LEDGER_COLUMNS:
        raise ValueError("Score ledger does not match the canonical schema")
    if ledger.num_rows == 0:
        return DetectedRuns(
            runs=pa.Table.from_pylist([], schema=RUN_SCHEMA),
            threshold_crossings=pa.Table.from_pylist(
                [], schema=THRESHOLD_CROSSING_SCHEMA
            ),
        )

    rows = ledger.to_pylist()
    signals_by_checkpoint = {
        signal.checkpoint_number: signal
        for signal in (
            primary_window_signals(ledger) if signals is None else signals
        )
    }
    game_id = str(rows[0]["game_id"])
    run_rows: list[dict[str, object]] = []
    crossing_rows: list[dict[str, object]] = []
    active: _ActiveRun | None = None
    next_sequence = 1

    for row in rows:
        checkpoint = int(row["checkpoint_number"])
        signal = signals_by_checkpoint.get(checkpoint)

        if active is not None and (
            signal is None or signal.run_team_id != active.values["run_team_id"]
        ):
            active.values["termination_reason"] = _termination_reason(row)
            run_rows.append(active.values)
            active = None

        if signal is not None and active is None:
            run_id = f"{game_id}-R{next_sequence:04d}"
            next_sequence += 1
            active = _start_run(signal=signal, row=row, run_id=run_id)
            crossing_rows.extend(
                _crossing_rows(active, signal, tuple(sorted(active.reached_thresholds)))
            )
        elif signal is not None and active is not None:
            new_thresholds = _extend_run(active, signal, row)
            crossing_rows.extend(_crossing_rows(active, signal, new_thresholds))

        if active is not None and row["reset_after_reason"] is not None:
            active.values["termination_reason"] = _termination_reason(row)
            run_rows.append(active.values)
            active = None

    if active is not None:
        active.values["termination_reason"] = "game_end"
        run_rows.append(active.values)

    return DetectedRuns(
        runs=pa.Table.from_pylist(run_rows, schema=RUN_SCHEMA),
        threshold_crossings=pa.Table.from_pylist(
            crossing_rows, schema=THRESHOLD_CROSSING_SCHEMA
        ),
    )
