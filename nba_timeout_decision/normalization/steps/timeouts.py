"""Normalize timeout type and ownership."""

from collections import Counter, defaultdict
from dataclasses import dataclass

import pyarrow as pa

from .challenges import link_challenge_reviews
from .table_ops import set_column


@dataclass(frozen=True)
class TimeoutNormalization:
    table: pa.Table
    class_counts: tuple[tuple[str, int], ...]
    orphan_challenge_review_count: int


def _description_supports(subtype: str, description: str | None) -> bool:
    if description is None:
        return False
    text = description.lower()
    if "timeout" not in text:
        return False
    if subtype == "Regular":
        return "regular" in text or "reg." in text or "full" in text
    if subtype == "Short":
        return "short" in text
    if subtype == "Official":
        return "official" in text
    if subtype == "Coach Challenge":
        return "challenge" in text
    return False


def normalize_timeouts(table: pa.Table) -> TimeoutNormalization:
    challenge_links = link_challenge_reviews(table)
    game_ids = table["game_id"].cast(pa.string()).to_pylist()
    action_types = table["action_type"].cast(pa.string()).to_pylist()
    subtypes = table["event_subtype"].cast(pa.string()).to_pylist()
    descriptions = table["description"].cast(pa.string()).to_pylist()
    source_team_ids = table["source_team_id"].cast(pa.int64()).to_pylist()
    source_person_ids = table["source_person_id"].cast(pa.int64()).to_pylist()
    event_team_ids = table["event_team_id"].cast(pa.int64()).to_pylist()
    event_team_roles = table["event_team_role"].cast(pa.string()).to_pylist()

    participants: dict[str, set[int]] = defaultdict(set)
    for game_id, team_id, role in zip(
        game_ids, event_team_ids, event_team_roles, strict=True
    ):
        if team_id is not None and role in {"home", "away"}:
            participants[game_id].add(team_id)

    classes: list[str] = []
    timeout_team_ids: list[int | None] = []
    ambiguous: list[bool] = []
    ownership_sources: list[str] = []
    challenge_outcomes: list[str] = []

    for (
        game_id,
        action_type,
        subtype,
        description,
        team_id,
        person_id,
        challenge_outcome,
    ) in zip(
        game_ids,
        action_types,
        subtypes,
        descriptions,
        source_team_ids,
        source_person_ids,
        challenge_links.timeout_outcomes,
        strict=True,
    ):
        if action_type != "Timeout":
            classes.append("none")
            timeout_team_ids.append(None)
            ambiguous.append(False)
            ownership_sources.append("none")
            challenge_outcomes.append("none")
            continue

        game_teams = participants[game_id]
        team_candidate = team_id if team_id in game_teams else None
        person_candidate = person_id if person_id in game_teams else None
        candidates = {team_candidate, person_candidate} - {None}

        owner: int | None = None
        ownership_source = "none"
        if len(candidates) == 1:
            owner = candidates.pop()
            if team_candidate is not None and person_candidate is not None:
                ownership_source = "event_team_and_person_id"
            elif team_candidate is not None:
                ownership_source = "event_team"
            else:
                ownership_source = "person_id"
        elif len(candidates) > 1:
            ownership_source = "conflicting"

        supported = _description_supports(subtype or "", description)
        if subtype == "Official" and supported:
            timeout_class = "official"
            owner = None
            ownership_source = "none"
        elif (
            (subtype == "Coach Challenge" and supported)
            or challenge_outcome is not None
        ) and owner is not None:
            timeout_class = "coach_challenge"
        elif subtype == "Regular" and supported and owner is not None:
            timeout_class = "team_regular"
        elif subtype == "Short" and supported and owner is not None:
            timeout_class = "team_short"
        else:
            timeout_class = "ambiguous"

        classes.append(timeout_class)
        timeout_team_ids.append(owner)
        ambiguous.append(timeout_class == "ambiguous")
        ownership_sources.append(ownership_source)
        if timeout_class == "coach_challenge":
            challenge_outcomes.append(challenge_outcome or "unknown")
        else:
            challenge_outcomes.append("none")

    normalized = set_column(
        table, "timeout_class", pa.array(classes, type=pa.string())
    )
    normalized = set_column(
        normalized,
        "timeout_team_id",
        pa.array(timeout_team_ids, type=pa.int64()),
    )
    normalized = set_column(
        normalized,
        "timeout_is_ambiguous",
        pa.array(ambiguous, type=pa.bool_()),
    )
    normalized = set_column(
        normalized,
        "timeout_ownership_source",
        pa.array(ownership_sources, type=pa.string()),
    )
    normalized = set_column(
        normalized,
        "coach_challenge_outcome",
        pa.array(challenge_outcomes, type=pa.string()),
    )
    return TimeoutNormalization(
        table=normalized,
        class_counts=tuple(sorted(Counter(classes).items())),
        orphan_challenge_review_count=challenge_links.orphan_review_count,
    )
