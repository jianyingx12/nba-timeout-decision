"""Build score checkpoints from one game's ordered possessions."""

from collections import Counter
from dataclasses import dataclass

import pyarrow as pa

from ..contract import SCORE_LEDGER_SCHEMA

REQUIRED_COLUMNS = (
    "game_id",
    "season",
    "season_start_year",
    "game_type",
    "game_date",
    "possession_number",
    "period",
    "first_action_id",
    "last_action_id",
    "first_source_row_number",
    "last_source_row_number",
    "offense_team_id",
    "offense_team_code",
    "defense_team_id",
    "defense_team_code",
    "start_seconds_remaining_in_period",
    "end_seconds_remaining_in_period",
    "start_home_score",
    "start_away_score",
    "end_home_score",
    "end_away_score",
    "possession_status",
    "is_censored_at_period_end",
    "contains_timeout",
    "contains_review",
    "contains_score_revision",
    "possession_is_ambiguous",
)


@dataclass(frozen=True)
class GameLedger:
    table: pa.Table
    possession_count: int
    between_possession_checkpoint_count: int
    reset_counts: tuple[tuple[str, int], ...]


def _base_values(
    row: dict[str, object], *, home_team_code: str, away_team_code: str
) -> dict[str, object]:
    return {
        "game_id": str(row["game_id"]),
        "season": str(row["season"]),
        "season_start_year": int(row["season_start_year"]),
        "game_type": str(row["game_type"]),
        "game_date": row["game_date"],
        "home_team_code": home_team_code,
        "away_team_code": away_team_code,
        "period": int(row["period"]),
        "possession_number": int(row["possession_number"]),
        "current_possession_first_action_id": int(row["first_action_id"]),
        "current_possession_first_source_row_number": int(
            row["first_source_row_number"]
        ),
        "current_possession_start_seconds_remaining_in_period": float(
            row["start_seconds_remaining_in_period"]
        ),
    }


def _reset_before(
    row: dict[str, object], previous: dict[str, object] | None
) -> str | None:
    if previous is None:
        return "game_start"
    if int(row["period"]) != int(previous["period"]):
        return "period_start"
    if bool(previous["possession_is_ambiguous"]) or bool(
        row["possession_is_ambiguous"]
    ):
        return "ambiguous_possession"
    return None


def build_game_ledger(
    possessions: pa.Table, *, home_team_code: str, away_team_code: str
) -> GameLedger:
    if not home_team_code or not away_team_code:
        raise ValueError("Home and away team codes are required")
    if home_team_code == away_team_code:
        raise ValueError("Home and away team codes must differ")
    missing = sorted(set(REQUIRED_COLUMNS) - set(possessions.column_names))
    if missing:
        raise ValueError(f"Possession input is missing columns: {missing}")
    if possessions.num_rows == 0:
        return GameLedger(
            table=pa.Table.from_pylist([], schema=SCORE_LEDGER_SCHEMA),
            possession_count=0,
            between_possession_checkpoint_count=0,
            reset_counts=(),
        )

    rows = possessions.select(REQUIRED_COLUMNS).to_pylist()
    game_ids = {str(row["game_id"]) for row in rows}
    if len(game_ids) != 1:
        raise ValueError("Score-ledger construction accepts exactly one game")
    numbers = [int(row["possession_number"]) for row in rows]
    if numbers != list(range(1, len(rows) + 1)):
        raise ValueError("Possession numbers must be sequential and ordered")
    periods = [int(row["period"]) for row in rows]
    if periods != sorted(periods):
        raise ValueError("Possession periods must be nondecreasing")
    observed_codes = {
        str(row[field])
        for row in rows
        for field in ("offense_team_code", "defense_team_code")
    }
    expected_codes = {home_team_code, away_team_code}
    if observed_codes != expected_codes:
        raise ValueError(
            "Possession team codes do not match the supplied home and away teams"
        )

    checkpoints: list[dict[str, object]] = []
    reset_counts: Counter[str] = Counter()
    previous: dict[str, object] | None = None
    checkpoint_number = 0
    gap_count = 0

    for completed_count, row in enumerate(rows, start=1):
        reset_before = _reset_before(row, previous)
        ambiguous = bool(row["possession_is_ambiguous"])
        gap_added = False

        if previous is not None:
            before_home = int(previous["end_home_score"])
            before_away = int(previous["end_away_score"])
            after_home = int(row["start_home_score"])
            after_away = int(row["start_away_score"])
            if (before_home, before_away) != (after_home, after_away):
                checkpoint_number += 1
                gap_count += 1
                gap_added = True
                if reset_before is not None:
                    reset_counts[reset_before] += 1
                checkpoints.append(
                    {
                        **_base_values(
                            row,
                            home_team_code=home_team_code,
                            away_team_code=away_team_code,
                        ),
                        "checkpoint_number": checkpoint_number,
                        "checkpoint_type": "between_possessions",
                        "completed_possession_count": completed_count - 1,
                        "increments_possession_window": False,
                        "offense_team_id": None,
                        "offense_team_code": None,
                        "defense_team_id": None,
                        "defense_team_code": None,
                        "previous_possession_last_action_id": int(
                            previous["last_action_id"]
                        ),
                        "checkpoint_action_id": None,
                        "previous_possession_last_source_row_number": int(
                            previous["last_source_row_number"]
                        ),
                        "checkpoint_source_row_number": None,
                        "seconds_remaining_in_period": float(
                            row["start_seconds_remaining_in_period"]
                        ),
                        "home_score_before": before_home,
                        "away_score_before": before_away,
                        "home_score_after": after_home,
                        "away_score_after": after_away,
                        "home_points": after_home - before_home,
                        "away_points": after_away - before_away,
                        "contains_timeout": False,
                        "contains_review": False,
                        "contains_score_revision": False,
                        "possession_status": None,
                        "reset_before_reason": reset_before,
                        "reset_after_reason": (
                            "ambiguous_possession" if ambiguous else None
                        ),
                        "primary_window_eligible": (
                            reset_before is None and not ambiguous
                        ),
                    }
                )

        checkpoint_number += 1
        possession_reset = (
            "ambiguous_possession"
            if ambiguous and gap_added
            else (None if gap_added else reset_before)
        )
        if possession_reset is not None:
            reset_counts[possession_reset] += 1
        reset_after = None
        if ambiguous:
            reset_after = "ambiguous_possession"
        elif bool(row["is_censored_at_period_end"]):
            reset_after = "period_start"
        if reset_after is not None:
            reset_counts[reset_after] += 1

        before_home = int(row["start_home_score"])
        before_away = int(row["start_away_score"])
        after_home = int(row["end_home_score"])
        after_away = int(row["end_away_score"])
        checkpoints.append(
            {
                **_base_values(
                    row,
                    home_team_code=home_team_code,
                    away_team_code=away_team_code,
                ),
                "checkpoint_number": checkpoint_number,
                "checkpoint_type": "possession_end",
                "completed_possession_count": completed_count,
                "increments_possession_window": True,
                "offense_team_id": int(row["offense_team_id"]),
                "offense_team_code": str(row["offense_team_code"]),
                "defense_team_id": int(row["defense_team_id"]),
                "defense_team_code": str(row["defense_team_code"]),
                "previous_possession_last_action_id": (
                    int(previous["last_action_id"])
                    if previous is not None
                    else None
                ),
                "checkpoint_action_id": int(row["last_action_id"]),
                "previous_possession_last_source_row_number": (
                    int(previous["last_source_row_number"])
                    if previous is not None
                    else None
                ),
                "checkpoint_source_row_number": int(
                    row["last_source_row_number"]
                ),
                "seconds_remaining_in_period": float(
                    row["end_seconds_remaining_in_period"]
                ),
                "home_score_before": before_home,
                "away_score_before": before_away,
                "home_score_after": after_home,
                "away_score_after": after_away,
                "home_points": after_home - before_home,
                "away_points": after_away - before_away,
                "contains_timeout": bool(row["contains_timeout"]),
                "contains_review": bool(row["contains_review"]),
                "contains_score_revision": bool(
                    row["contains_score_revision"]
                ),
                "possession_status": str(row["possession_status"]),
                "reset_before_reason": possession_reset,
                "reset_after_reason": reset_after,
                "primary_window_eligible": not ambiguous,
            }
        )
        previous = row

    return GameLedger(
        table=pa.Table.from_pylist(checkpoints, schema=SCORE_LEDGER_SCHEMA),
        possession_count=len(rows),
        between_possession_checkpoint_count=gap_count,
        reset_counts=tuple(sorted(reset_counts.items())),
    )
