"""Build run signals used only for alternate-definition comparisons."""

import pyarrow as pa

from .contract import (
    SENSITIVITY_SIGNAL_SCHEMA,
    SENSITIVITY_WINDOW_SIZES,
)
from .signals import WindowSignal, primary_window_signals, window_signals

STRICT_THRESHOLDS = (6, 8, 10)


def _pace(signal: WindowSignal) -> tuple[float, float | None]:
    elapsed = max(
        0.0,
        signal.window_start_seconds_remaining_in_period
        - signal.seconds_remaining_in_period,
    )
    pace = signal.net_points * 60.0 / elapsed if elapsed > 0 else None
    return elapsed, pace


def _row(
    signal: WindowSignal, *, definition: str, threshold: int
) -> dict[str, object]:
    elapsed, pace = _pace(signal)
    return {
        "game_id": None,
        "period": signal.period,
        "checkpoint_number": signal.checkpoint_number,
        "possession_number": signal.possession_number,
        "run_team_id": signal.run_team_id,
        "run_team_code": signal.run_team_code,
        "definition": definition,
        "window_size": signal.window_size,
        "threshold": threshold,
        "run_team_points": signal.run_team_points,
        "opponent_points": signal.opponent_points,
        "net_points": signal.net_points,
        "strict_unanswered": signal.strict_unanswered,
        "elapsed_seconds": elapsed,
        "net_points_per_minute": pace,
    }


def sensitivity_signals(
    ledger: pa.Table, *, primary_signals: tuple[WindowSignal, ...] | None = None
) -> pa.Table:
    """Return strict-unanswered and alternate-window signal rows."""
    if ledger.num_rows == 0:
        return pa.Table.from_pylist([], schema=SENSITIVITY_SIGNAL_SCHEMA)

    game_ids = ledger.column("game_id").unique().to_pylist()
    if len(game_ids) != 1:
        raise ValueError("Sensitivity signals accept exactly one game ledger")
    game_id = str(game_ids[0])
    rows: list[dict[str, object]] = []

    primary = (
        primary_window_signals(ledger)
        if primary_signals is None
        else primary_signals
    )
    for signal in primary:
        if not signal.strict_unanswered:
            continue
        for threshold in STRICT_THRESHOLDS:
            if signal.run_team_points >= threshold:
                row = _row(
                    signal,
                    definition=f"strict_unanswered_{threshold}_0",
                    threshold=threshold,
                )
                row["game_id"] = game_id
                rows.append(row)

    for window_size in SENSITIVITY_WINDOW_SIZES:
        for signal in window_signals(ledger, window_size=window_size):
            row = _row(
                signal,
                definition=f"net_plus_6_over_{window_size}_possessions",
                threshold=6,
            )
            row["game_id"] = game_id
            rows.append(row)

    rows.sort(
        key=lambda row: (
            int(row["checkpoint_number"]),
            str(row["definition"]),
            str(row["run_team_code"]),
        )
    )
    return pa.Table.from_pylist(rows, schema=SENSITIVITY_SIGNAL_SCHEMA)
