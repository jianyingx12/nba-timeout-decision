"""Calculate primary rolling net-point signals from a game score ledger."""

from dataclasses import dataclass

import pyarrow as pa

from .contract import PRIMARY_WINDOW_SIZE, SCORE_LEDGER_COLUMNS


@dataclass(frozen=True)
class WindowSignal:
    checkpoint_number: int
    checkpoint_type: str
    possession_number: int
    period: int
    run_team_id: int
    run_team_code: str
    opponent_team_id: int
    opponent_team_code: str
    run_team_is_home: bool
    window_size: int
    start_possession_number: int
    window_start_checkpoint_number: int
    window_start_action_id: int
    window_start_source_row_number: int
    window_start_seconds_remaining_in_period: float
    action_id: int | None
    source_row_number: int | None
    previous_possession_last_action_id: int | None
    current_possession_first_action_id: int
    previous_possession_last_source_row_number: int | None
    current_possession_first_source_row_number: int
    seconds_remaining_in_period: float
    run_team_points: int
    opponent_points: int
    net_points: int
    score_margin_before: int
    score_margin_at_checkpoint: int
    strict_unanswered: bool
    contains_censored_possession: bool
    contains_timeout: bool
    contains_review: bool
    contains_score_revision: bool
    between_possession_net_points: int


@dataclass(frozen=True)
class _Boundary:
    checkpoint_number: int
    home_score: int
    away_score: int


def _team_ids(rows: list[dict[str, object]]) -> dict[str, int]:
    ids: dict[str, set[int]] = {}
    for row in rows:
        for code_field, id_field in (
            ("offense_team_code", "offense_team_id"),
            ("defense_team_code", "defense_team_id"),
        ):
            code = row[code_field]
            team_id = row[id_field]
            if code is not None and team_id is not None:
                ids.setdefault(str(code), set()).add(int(team_id))
    if any(len(values) != 1 for values in ids.values()):
        raise ValueError("Ledger contains conflicting team IDs")
    return {code: next(iter(values)) for code, values in ids.items()}


def _signal(
    *,
    row: dict[str, object],
    base: _Boundary,
    start: dict[str, object],
    window_rows: list[dict[str, object]],
    home_team_code: str,
    away_team_code: str,
    team_ids: dict[str, int],
    window_size: int,
    minimum_net_points: int,
) -> WindowSignal | None:
    home_points = int(row["home_score_after"]) - base.home_score
    away_points = int(row["away_score_after"]) - base.away_score
    home_net = home_points - away_points
    if home_net >= minimum_net_points:
        run_code = home_team_code
        opponent_code = away_team_code
        run_points = home_points
        opponent_points = away_points
        net_points = home_net
        margin_before = base.home_score - base.away_score
        margin_at = int(row["home_score_after"]) - int(row["away_score_after"])
        is_home = True
        between_net = sum(
            int(item["home_points"]) - int(item["away_points"])
            for item in window_rows
            if item["checkpoint_type"] == "between_possessions"
        )
    elif home_net <= -minimum_net_points:
        run_code = away_team_code
        opponent_code = home_team_code
        run_points = away_points
        opponent_points = home_points
        net_points = -home_net
        margin_before = base.away_score - base.home_score
        margin_at = int(row["away_score_after"]) - int(row["home_score_after"])
        is_home = False
        between_net = sum(
            int(item["away_points"]) - int(item["home_points"])
            for item in window_rows
            if item["checkpoint_type"] == "between_possessions"
        )
    else:
        return None

    try:
        run_team_id = team_ids[run_code]
        opponent_team_id = team_ids[opponent_code]
    except KeyError as error:
        raise ValueError(f"Ledger is missing team identity for {error.args[0]}") from error

    return WindowSignal(
        checkpoint_number=int(row["checkpoint_number"]),
        checkpoint_type=str(row["checkpoint_type"]),
        possession_number=int(row["possession_number"]),
        period=int(row["period"]),
        run_team_id=run_team_id,
        run_team_code=run_code,
        opponent_team_id=opponent_team_id,
        opponent_team_code=opponent_code,
        run_team_is_home=is_home,
        window_size=window_size,
        start_possession_number=int(start["possession_number"]),
        window_start_checkpoint_number=int(start["checkpoint_number"]),
        window_start_action_id=int(start["current_possession_first_action_id"]),
        window_start_source_row_number=int(
            start["current_possession_first_source_row_number"]
        ),
        window_start_seconds_remaining_in_period=float(
            start["current_possession_start_seconds_remaining_in_period"]
        ),
        action_id=(
            int(row["checkpoint_action_id"])
            if row["checkpoint_action_id"] is not None
            else None
        ),
        source_row_number=(
            int(row["checkpoint_source_row_number"])
            if row["checkpoint_source_row_number"] is not None
            else None
        ),
        previous_possession_last_action_id=(
            int(row["previous_possession_last_action_id"])
            if row["previous_possession_last_action_id"] is not None
            else None
        ),
        current_possession_first_action_id=int(
            row["current_possession_first_action_id"]
        ),
        previous_possession_last_source_row_number=(
            int(row["previous_possession_last_source_row_number"])
            if row["previous_possession_last_source_row_number"] is not None
            else None
        ),
        current_possession_first_source_row_number=int(
            row["current_possession_first_source_row_number"]
        ),
        seconds_remaining_in_period=float(row["seconds_remaining_in_period"]),
        run_team_points=run_points,
        opponent_points=opponent_points,
        net_points=net_points,
        score_margin_before=margin_before,
        score_margin_at_checkpoint=margin_at,
        strict_unanswered=opponent_points == 0,
        contains_censored_possession=any(
            item["possession_status"] == "censored" for item in window_rows
        ),
        contains_timeout=any(bool(item["contains_timeout"]) for item in window_rows),
        contains_review=any(bool(item["contains_review"]) for item in window_rows),
        contains_score_revision=any(
            bool(item["contains_score_revision"]) for item in window_rows
        ),
        between_possession_net_points=between_net,
    )


def window_signals(
    ledger: pa.Table, *, window_size: int, minimum_net_points: int = 6
) -> tuple[WindowSignal, ...]:
    if window_size < 1:
        raise ValueError("Window size must be positive")
    if minimum_net_points < 1:
        raise ValueError("Minimum net points must be positive")
    if tuple(ledger.column_names) != SCORE_LEDGER_COLUMNS:
        raise ValueError("Score ledger does not match the canonical schema")
    if ledger.num_rows == 0:
        return ()

    rows = ledger.to_pylist()
    game_ids = {str(row["game_id"]) for row in rows}
    if len(game_ids) != 1:
        raise ValueError("Primary signals accept exactly one game ledger")
    numbers = [int(row["checkpoint_number"]) for row in rows]
    if numbers != list(range(1, len(rows) + 1)):
        raise ValueError("Ledger checkpoints must be sequential and ordered")

    home_team_code = str(rows[0]["home_team_code"])
    away_team_code = str(rows[0]["away_team_code"])
    if any(
        row["home_team_code"] != home_team_code
        or row["away_team_code"] != away_team_code
        for row in rows
    ):
        raise ValueError("Ledger home and away teams must be constant within a game")
    team_ids = _team_ids(rows)

    boundaries: list[_Boundary] = []
    possession_rows: list[dict[str, object]] = []
    segment_rows: list[dict[str, object]] = []
    signals: list[WindowSignal] = []

    for row in rows:
        if row["reset_before_reason"] is not None or not boundaries:
            boundaries = [
                _Boundary(
                    checkpoint_number=int(row["checkpoint_number"]) - 1,
                    home_score=int(row["home_score_before"]),
                    away_score=int(row["away_score_before"]),
                )
            ]
            possession_rows = []
            segment_rows = []

        if not bool(row["primary_window_eligible"]):
            boundaries = [
                _Boundary(
                    checkpoint_number=int(row["checkpoint_number"]),
                    home_score=int(row["home_score_after"]),
                    away_score=int(row["away_score_after"]),
                )
            ]
            possession_rows = []
            segment_rows = []
            continue

        segment_rows.append(row)
        if bool(row["increments_possession_window"]):
            possession_rows.append(row)
            boundaries.append(
                _Boundary(
                    checkpoint_number=int(row["checkpoint_number"]),
                    home_score=int(row["home_score_after"]),
                    away_score=int(row["away_score_after"]),
                )
            )

        if len(possession_rows) >= window_size:
            base = boundaries[-(window_size + 1)]
            start = possession_rows[-window_size]
            window_rows = [
                item
                for item in segment_rows
                if int(item["checkpoint_number"]) > base.checkpoint_number
            ]
            signal = _signal(
                row=row,
                base=base,
                start=start,
                window_rows=window_rows,
                home_team_code=home_team_code,
                away_team_code=away_team_code,
                team_ids=team_ids,
                window_size=window_size,
                minimum_net_points=minimum_net_points,
            )
            if signal is not None:
                signals.append(signal)

        if row["reset_after_reason"] is not None:
            boundaries = [
                _Boundary(
                    checkpoint_number=int(row["checkpoint_number"]),
                    home_score=int(row["home_score_after"]),
                    away_score=int(row["away_score_after"]),
                )
            ]
            possession_rows = []
            segment_rows = []

    return tuple(signals)


def primary_window_signals(ledger: pa.Table) -> tuple[WindowSignal, ...]:
    return window_signals(ledger, window_size=PRIMARY_WINDOW_SIZE)
