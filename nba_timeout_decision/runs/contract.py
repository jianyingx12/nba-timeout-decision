"""Output schemas and controlled values for scoring-run detection."""

import pyarrow as pa

PRIMARY_WINDOW_SIZE = 4
SENSITIVITY_WINDOW_SIZES = (6, 8)
RUN_THRESHOLDS = (6, 8, 10, 12)

CHECKPOINT_TYPES = (
    "between_possessions",
    "possession_end",
)

RESET_REASONS = (
    "game_start",
    "period_start",
    "ambiguous_possession",
    "score_discontinuity",
)

TERMINATION_REASONS = (
    "net_advantage_lost",
    "period_end",
    "ambiguous_possession",
    "game_end",
)

EXCLUSION_REASONS = (
    "period_ended_at_qualification",
    "censored_qualification",
)

SCORE_LEDGER_SCHEMA = pa.schema(
    [
        pa.field("game_id", pa.string(), nullable=False),
        pa.field("season", pa.string(), nullable=False),
        pa.field("season_start_year", pa.int16(), nullable=False),
        pa.field("game_type", pa.string(), nullable=False),
        pa.field("game_date", pa.date32(), nullable=False),
        pa.field("home_team_code", pa.string(), nullable=False),
        pa.field("away_team_code", pa.string(), nullable=False),
        pa.field("checkpoint_number", pa.int32(), nullable=False),
        pa.field("checkpoint_type", pa.string(), nullable=False),
        pa.field("period", pa.int8(), nullable=False),
        pa.field("possession_number", pa.int32(), nullable=False),
        pa.field("completed_possession_count", pa.int32(), nullable=False),
        pa.field("increments_possession_window", pa.bool_(), nullable=False),
        pa.field("offense_team_id", pa.int64()),
        pa.field("offense_team_code", pa.string()),
        pa.field("defense_team_id", pa.int64()),
        pa.field("defense_team_code", pa.string()),
        pa.field("previous_possession_last_action_id", pa.int64()),
        pa.field("current_possession_first_action_id", pa.int64(), nullable=False),
        pa.field("checkpoint_action_id", pa.int64()),
        pa.field("previous_possession_last_source_row_number", pa.int64()),
        pa.field(
            "current_possession_first_source_row_number",
            pa.int64(),
            nullable=False,
        ),
        pa.field(
            "current_possession_start_seconds_remaining_in_period",
            pa.float64(),
            nullable=False,
        ),
        pa.field("checkpoint_source_row_number", pa.int64()),
        pa.field("seconds_remaining_in_period", pa.float64(), nullable=False),
        pa.field("home_score_before", pa.int64(), nullable=False),
        pa.field("away_score_before", pa.int64(), nullable=False),
        pa.field("home_score_after", pa.int64(), nullable=False),
        pa.field("away_score_after", pa.int64(), nullable=False),
        pa.field("home_points", pa.int16(), nullable=False),
        pa.field("away_points", pa.int16(), nullable=False),
        pa.field("contains_timeout", pa.bool_(), nullable=False),
        pa.field("contains_review", pa.bool_(), nullable=False),
        pa.field("contains_score_revision", pa.bool_(), nullable=False),
        pa.field("possession_status", pa.string()),
        pa.field("reset_before_reason", pa.string()),
        pa.field("reset_after_reason", pa.string()),
        pa.field("primary_window_eligible", pa.bool_(), nullable=False),
    ]
)

RUN_SCHEMA = pa.schema(
    [
        pa.field("game_id", pa.string(), nullable=False),
        pa.field("season", pa.string(), nullable=False),
        pa.field("season_start_year", pa.int16(), nullable=False),
        pa.field("game_type", pa.string(), nullable=False),
        pa.field("game_date", pa.date32(), nullable=False),
        pa.field("run_id", pa.string(), nullable=False),
        pa.field("period", pa.int8(), nullable=False),
        pa.field("run_team_id", pa.int64(), nullable=False),
        pa.field("run_team_code", pa.string(), nullable=False),
        pa.field("opponent_team_id", pa.int64(), nullable=False),
        pa.field("opponent_team_code", pa.string(), nullable=False),
        pa.field("start_possession_number", pa.int32(), nullable=False),
        pa.field("qualification_possession_number", pa.int32(), nullable=False),
        pa.field("end_possession_number", pa.int32(), nullable=False),
        pa.field("start_checkpoint_number", pa.int32(), nullable=False),
        pa.field("qualification_checkpoint_number", pa.int32(), nullable=False),
        pa.field("end_checkpoint_number", pa.int32(), nullable=False),
        pa.field("first_action_id", pa.int64(), nullable=False),
        pa.field("qualification_action_id", pa.int64()),
        pa.field("last_action_id", pa.int64(), nullable=False),
        pa.field("first_source_row_number", pa.int64(), nullable=False),
        pa.field("qualification_source_row_number", pa.int64()),
        pa.field("last_source_row_number", pa.int64(), nullable=False),
        pa.field("window_size", pa.int8(), nullable=False),
        pa.field("run_team_points_at_qualification", pa.int16(), nullable=False),
        pa.field("opponent_points_at_qualification", pa.int16(), nullable=False),
        pa.field("net_points_at_qualification", pa.int16(), nullable=False),
        pa.field("first_threshold", pa.int8(), nullable=False),
        pa.field("maximum_threshold", pa.int8(), nullable=False),
        pa.field("score_margin_before_qualification", pa.int16(), nullable=False),
        pa.field("score_margin_at_qualification", pa.int16(), nullable=False),
        pa.field(
            "seconds_remaining_at_qualification", pa.float64(), nullable=False
        ),
        pa.field("run_team_is_home", pa.bool_(), nullable=False),
        pa.field("strict_unanswered", pa.bool_(), nullable=False),
        pa.field("contains_censored_possession", pa.bool_(), nullable=False),
        pa.field("contains_timeout", pa.bool_(), nullable=False),
        pa.field("contains_review", pa.bool_(), nullable=False),
        pa.field("contains_score_revision", pa.bool_(), nullable=False),
        pa.field("between_possession_net_points", pa.int16(), nullable=False),
        pa.field("termination_reason", pa.string(), nullable=False),
        pa.field("primary_analysis_eligible", pa.bool_(), nullable=False),
        pa.field("exclusion_reason", pa.string()),
    ]
)

THRESHOLD_CROSSING_SCHEMA = pa.schema(
    [
        pa.field("game_id", pa.string(), nullable=False),
        pa.field("run_id", pa.string(), nullable=False),
        pa.field("period", pa.int8(), nullable=False),
        pa.field("run_team_id", pa.int64(), nullable=False),
        pa.field("run_team_code", pa.string(), nullable=False),
        pa.field("threshold", pa.int8(), nullable=False),
        pa.field("crossing_sequence", pa.int8(), nullable=False),
        pa.field("checkpoint_number", pa.int32(), nullable=False),
        pa.field("checkpoint_type", pa.string(), nullable=False),
        pa.field("possession_number", pa.int32(), nullable=False),
        pa.field("action_id", pa.int64()),
        pa.field("source_row_number", pa.int64()),
        pa.field("previous_possession_last_action_id", pa.int64()),
        pa.field("current_possession_first_action_id", pa.int64(), nullable=False),
        pa.field("previous_possession_last_source_row_number", pa.int64()),
        pa.field(
            "current_possession_first_source_row_number",
            pa.int64(),
            nullable=False,
        ),
        pa.field("seconds_remaining_in_period", pa.float64(), nullable=False),
        pa.field("run_team_points", pa.int16(), nullable=False),
        pa.field("opponent_points", pa.int16(), nullable=False),
        pa.field("net_points", pa.int16(), nullable=False),
        pa.field("score_margin", pa.int16(), nullable=False),
    ]
)

SENSITIVITY_SIGNAL_SCHEMA = pa.schema(
    [
        pa.field("game_id", pa.string(), nullable=False),
        pa.field("period", pa.int8(), nullable=False),
        pa.field("checkpoint_number", pa.int32(), nullable=False),
        pa.field("possession_number", pa.int32(), nullable=False),
        pa.field("run_team_id", pa.int64(), nullable=False),
        pa.field("run_team_code", pa.string(), nullable=False),
        pa.field("definition", pa.string(), nullable=False),
        pa.field("window_size", pa.int8(), nullable=False),
        pa.field("threshold", pa.int8(), nullable=False),
        pa.field("run_team_points", pa.int16(), nullable=False),
        pa.field("opponent_points", pa.int16(), nullable=False),
        pa.field("net_points", pa.int16(), nullable=False),
        pa.field("strict_unanswered", pa.bool_(), nullable=False),
        pa.field("elapsed_seconds", pa.float64(), nullable=False),
        pa.field("net_points_per_minute", pa.float64()),
    ]
)

SCORE_LEDGER_COLUMNS = tuple(SCORE_LEDGER_SCHEMA.names)
RUN_COLUMNS = tuple(RUN_SCHEMA.names)
THRESHOLD_CROSSING_COLUMNS = tuple(THRESHOLD_CROSSING_SCHEMA.names)
SENSITIVITY_SIGNAL_COLUMNS = tuple(SENSITIVITY_SIGNAL_SCHEMA.names)
