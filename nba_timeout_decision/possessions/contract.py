"""Possession output contract and controlled values."""

import pyarrow as pa

POSSESSION_STATUSES = (
    "complete",
    "censored",
    "ambiguous",
)

START_REASONS = (
    "period_start",
    "made_basket_inbound",
    "made_free_throw_inbound",
    "defensive_rebound",
    "turnover",
    "jump_ball_control",
    "unknown",
)

END_REASONS = (
    "made_field_goal",
    "made_final_free_throw",
    "defensive_rebound",
    "turnover",
    "jump_ball_change",
    "period_end",
    "unknown",
)

AMBIGUITY_REASONS = (
    "missing_initial_control",
    "missing_rebound_control",
    "contradictory_team_control",
    "unresolved_jump_ball",
    "unresolved_free_throw_sequence",
    "unresolved_review",
    "unexplained_score_change",
    "score_revision_crosses_boundary",
    "missing_terminal_event",
)

POSSESSION_SCHEMA = pa.schema(
    [
        pa.field("game_id", pa.string(), nullable=False),
        pa.field("season", pa.string(), nullable=False),
        pa.field("season_start_year", pa.int16(), nullable=False),
        pa.field("game_type", pa.string(), nullable=False),
        pa.field("game_date", pa.date32(), nullable=False),
        pa.field("possession_number", pa.int32(), nullable=False),
        pa.field("period", pa.int8(), nullable=False),
        pa.field("first_action_id", pa.int64(), nullable=False),
        pa.field("last_action_id", pa.int64(), nullable=False),
        pa.field("first_source_row_number", pa.int64(), nullable=False),
        pa.field("last_source_row_number", pa.int64(), nullable=False),
        pa.field("offense_team_id", pa.int64()),
        pa.field("offense_team_code", pa.string()),
        pa.field("defense_team_id", pa.int64()),
        pa.field("defense_team_code", pa.string()),
        pa.field("start_seconds_remaining_in_period", pa.float64(), nullable=False),
        pa.field("end_seconds_remaining_in_period", pa.float64(), nullable=False),
        pa.field("start_home_score", pa.int64(), nullable=False),
        pa.field("start_away_score", pa.int64(), nullable=False),
        pa.field("end_home_score", pa.int64(), nullable=False),
        pa.field("end_away_score", pa.int64(), nullable=False),
        pa.field("offense_points", pa.int16()),
        pa.field("defense_points", pa.int16()),
        pa.field("duration_seconds", pa.float64(), nullable=False),
        pa.field("possession_status", pa.string(), nullable=False),
        pa.field("start_reason", pa.string(), nullable=False),
        pa.field("end_reason", pa.string(), nullable=False),
        pa.field("is_censored_at_period_end", pa.bool_(), nullable=False),
        pa.field("contains_timeout", pa.bool_(), nullable=False),
        pa.field("contains_review", pa.bool_(), nullable=False),
        pa.field("contains_score_revision", pa.bool_(), nullable=False),
        pa.field("possession_is_ambiguous", pa.bool_(), nullable=False),
        pa.field("ambiguity_reason", pa.string()),
    ]
)

POSSESSION_COLUMNS = tuple(POSSESSION_SCHEMA.names)
