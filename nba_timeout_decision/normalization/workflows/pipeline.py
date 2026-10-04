"""Compose the canonical event normalization steps."""

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pyarrow as pa

from ..io.reader import PartitionProjection, read_partition
from ..models import GameRejection
from ..steps.clock import normalize_period_and_clock
from ..steps.events import normalize_events
from ..steps.fields import normalize_identifiers_and_labels
from ..steps.score import normalize_scores
from ..steps.stoppages import normalize_stoppages
from ..steps.teams import normalize_teams
from ..steps.timeouts import normalize_timeouts

CANONICAL_COLUMNS = (
    "game_id",
    "season",
    "season_start_year",
    "game_type",
    "game_date",
    "home_team",
    "away_team",
    "source_partition",
    "source_row_number",
    "action_id",
    "source_action_number",
    "period",
    "clock",
    "seconds_remaining_in_period",
    "clock_increases_within_period",
    "source_team_id",
    "event_team_id",
    "event_team_code",
    "event_team_role",
    "event_is_teamless",
    "event_team_is_conflicting",
    "source_person_id",
    "person_id",
    "player_name",
    "player_name_initial",
    "x_legacy",
    "y_legacy",
    "shot_distance",
    "shot_result",
    "is_field_goal",
    "points_total",
    "location",
    "video_available",
    "shot_value",
    "source_action_type",
    "source_sub_type",
    "source_description",
    "action_type",
    "event_type",
    "event_subtype",
    "description",
    "stoppage_class",
    "source_home_score",
    "source_away_score",
    "home_score",
    "away_score",
    "score_is_carried_forward",
    "score_update_is_unexplained",
    "score_update_is_revision",
    "timeout_class",
    "timeout_team_id",
    "timeout_is_ambiguous",
    "timeout_ownership_source",
    "coach_challenge_outcome",
    "substitution_team_id",
    "substitution_out_player_id",
    "substitution_in_player_id",
    "substitution_in_player_name",
    "substitution_is_ambiguous",
)


@dataclass(frozen=True)
class PartitionNormalization:
    table: pa.Table
    source_row_count: int
    rejected_games: tuple[GameRejection, ...]
    warnings: tuple[tuple[str, int], ...]


def _reject_conflicting_team_games(
    table: pa.Table, game_ids: tuple[str, ...]
) -> tuple[pa.Table, tuple[GameRejection, ...]]:
    if not game_ids:
        return table, ()

    rejected = set(game_ids)
    row_counts = Counter(table["game_id"].cast(pa.string()).to_pylist())
    keep = [game_id not in rejected for game_id in table["game_id"].to_pylist()]
    rejections = tuple(
        GameRejection(
            game_id=game_id,
            reason="irreconcilable event-team identity",
            raw_row_count=row_counts[game_id],
        )
        for game_id in game_ids
    )
    return table.filter(pa.array(keep, type=pa.bool_())), rejections


def normalize_projection(projection: PartitionProjection) -> PartitionNormalization:
    table = normalize_identifiers_and_labels(projection.table)
    table = normalize_period_and_clock(table)

    scores = normalize_scores(table)
    table = scores.table

    teams = normalize_teams(table)
    table, team_rejections = _reject_conflicting_team_games(
        teams.table, teams.conflicting_game_ids
    )

    events = normalize_events(table)
    timeouts = normalize_timeouts(events.table)
    stoppages = normalize_stoppages(timeouts.table)
    table = stoppages.table.select(CANONICAL_COLUMNS)

    warning_counts = {
        "ambiguous_substitutions": stoppages.ambiguous_substitution_count,
        "ambiguous_timeouts": dict(timeouts.class_counts).get("ambiguous", 0),
        "carried_scores": sum(table["score_is_carried_forward"].to_pylist()),
        "clock_increases": sum(table["clock_increases_within_period"].to_pylist()),
        "orphan_challenge_reviews": timeouts.orphan_challenge_review_count,
        "unexplained_score_updates": scores.unexplained_update_count,
        "score_revisions": scores.revision_count,
        "unmapped_action_labels": sum(count for _, count in events.unmapped_labels),
    }
    rejected_games = (
        *projection.rejected_games,
        *scores.rejected_games,
        *team_rejections,
    )
    accounted_rows = table.num_rows + sum(
        rejection.raw_row_count for rejection in rejected_games
    )
    if accounted_rows != projection.source_row_count:
        raise ValueError(
            "Normalized and rejected row counts do not match source: "
            f"{accounted_rows} != {projection.source_row_count}"
        )

    return PartitionNormalization(
        table=table,
        source_row_count=projection.source_row_count,
        rejected_games=tuple(rejected_games),
        warnings=tuple(
            sorted((name, count) for name, count in warning_counts.items() if count)
        ),
    )


def normalize_partition(
    source: Path,
    catalog: Path,
    *,
    raw_root: Path,
    expected_season: int,
    expected_game_type: str,
) -> PartitionNormalization:
    projection = read_partition(
        source,
        catalog,
        raw_root=raw_root,
        expected_season=expected_season,
        expected_game_type=expected_game_type,
    )
    return normalize_projection(projection)
