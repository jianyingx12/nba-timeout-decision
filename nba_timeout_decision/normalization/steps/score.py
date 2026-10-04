"""Normalize and validate event-level score state."""

import math
from collections import Counter
from dataclasses import dataclass

import pyarrow as pa

from ..models import GameRejection
from .table_ops import set_column

SCORING_ACTION_TYPES = {"Made Shot", "Free Throw"}


@dataclass(frozen=True)
class FinalScore:
    game_id: str
    home_score: int
    away_score: int


@dataclass(frozen=True)
class ScoreNormalization:
    table: pa.Table
    rejected_games: tuple[GameRejection, ...]
    final_scores: tuple[FinalScore, ...]
    unexplained_update_count: int
    revision_count: int


def _score(value: float | None) -> int | None:
    if value is None:
        return None
    if not math.isfinite(value) or value < 0 or not value.is_integer():
        raise ValueError(f"Invalid score value: {value!r}")
    return int(value)


def normalize_scores(table: pa.Table) -> ScoreNormalization:
    game_ids = table["game_id"].cast(pa.string()).to_pylist()
    periods = table["period"].cast(pa.int8()).to_pylist()
    action_types = table["action_type"].cast(pa.string()).to_pylist()
    source_home = table["scoreHome"].cast(pa.float64()).to_pylist()
    source_away = table["scoreAway"].cast(pa.float64()).to_pylist()
    row_counts = Counter(game_ids)

    current: dict[str, tuple[int, int]] = {}
    observed_score: set[str] = set()
    rejection_reasons: dict[str, str] = {}
    normalized_home: list[int] = []
    normalized_away: list[int] = []
    carried_forward: list[bool] = []
    unexplained_updates: list[bool] = []
    revisions: list[bool] = []
    previous_action_types: dict[str, str | None] = {}

    for game_id, period, action_type, raw_home, raw_away in zip(
        game_ids,
        periods,
        action_types,
        source_home,
        source_away,
        strict=True,
    ):
        home, away = current.get(game_id, (0, 0))
        carried = raw_home is None or raw_away is None
        unexplained = False
        revision = False

        if (raw_home is None) != (raw_away is None):
            rejection_reasons.setdefault(game_id, "partial score pair")
        elif raw_home is None:
            if game_id not in observed_score and period > 1:
                rejection_reasons.setdefault(
                    game_id, "score unavailable before a later period"
                )
        elif raw_home == 0 and raw_away == 0 and (home > 0 or away > 0):
            carried = True
        else:
            try:
                next_home = _score(raw_home)
                next_away = _score(raw_away)
            except ValueError as error:
                rejection_reasons.setdefault(game_id, str(error))
            else:
                assert next_home is not None and next_away is not None
                home_change = next_home - home
                away_change = next_away - away
                if home_change < 0 or away_change < 0:
                    if action_type == "period":
                        carried = True
                    elif (
                        action_type == "Instant Replay"
                        or previous_action_types.get(game_id) == "Instant Replay"
                    ):
                        home, away = next_home, next_away
                        revision = True
                        observed_score.add(game_id)
                    else:
                        rejection_reasons.setdefault(game_id, "score decreases")
                elif home_change > 3 or away_change > 3:
                    rejection_reasons.setdefault(game_id, "score increases by more than 3")
                elif home_change > 0 and away_change > 0:
                    rejection_reasons.setdefault(game_id, "both teams score on one event")
                else:
                    if (home_change > 0 or away_change > 0) and (
                        action_type not in SCORING_ACTION_TYPES
                    ):
                        if action_type == "Instant Replay":
                            revision = True
                        else:
                            unexplained = True
                    home, away = next_home, next_away
                    observed_score.add(game_id)

        current[game_id] = (home, away)
        previous_action_types[game_id] = action_type
        normalized_home.append(home)
        normalized_away.append(away)
        carried_forward.append(carried)
        unexplained_updates.append(unexplained)
        revisions.append(revision)

    for game_id in row_counts:
        if game_id not in observed_score:
            rejection_reasons.setdefault(game_id, "game has no observed score")

    rejected_games = tuple(
        GameRejection(
            game_id=game_id,
            reason=reason,
            raw_row_count=row_counts[game_id],
        )
        for game_id, reason in sorted(rejection_reasons.items())
    )
    accepted = [game_id not in rejection_reasons for game_id in game_ids]

    normalized = set_column(
        table, "source_home_score", table["scoreHome"].cast(pa.float64())
    )
    normalized = set_column(
        normalized, "source_away_score", table["scoreAway"].cast(pa.float64())
    )
    normalized = set_column(
        normalized, "home_score", pa.array(normalized_home, type=pa.int32())
    )
    normalized = set_column(
        normalized, "away_score", pa.array(normalized_away, type=pa.int32())
    )
    normalized = set_column(
        normalized,
        "score_is_carried_forward",
        pa.array(carried_forward, type=pa.bool_()),
    )
    normalized = set_column(
        normalized,
        "score_update_is_unexplained",
        pa.array(unexplained_updates, type=pa.bool_()),
    )
    normalized = set_column(
        normalized,
        "score_update_is_revision",
        pa.array(revisions, type=pa.bool_()),
    )
    if rejected_games:
        normalized = normalized.filter(pa.array(accepted, type=pa.bool_()))

    final_scores = tuple(
        FinalScore(game_id=game_id, home_score=scores[0], away_score=scores[1])
        for game_id, scores in sorted(current.items())
        if game_id not in rejection_reasons
    )
    accepted_unexplained = sum(
        is_unexplained and is_accepted
        for is_unexplained, is_accepted in zip(
            unexplained_updates, accepted, strict=True
        )
    )
    accepted_revisions = sum(
        is_revision and is_accepted
        for is_revision, is_accepted in zip(revisions, accepted, strict=True)
    )
    return ScoreNormalization(
        table=normalized,
        rejected_games=rejected_games,
        final_scores=final_scores,
        unexplained_update_count=accepted_unexplained,
        revision_count=accepted_revisions,
    )
