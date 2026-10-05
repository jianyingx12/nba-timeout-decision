"""Parse canonical free-throw attempts and penalty context."""

import re
from dataclasses import dataclass
from typing import Mapping, Sequence

from .ownership import GameTeams

FREE_THROW_PATTERN = re.compile(
    r"^Free Throw"
    r"(?: (?P<penalty>Technical|Flagrant|Clear Path))?"
    r"(?: (?P<attempt>[1-9]\d*) of (?P<total>[1-9]\d*))?$"
)

RETAINED_FOUL_SUBTYPES = {
    "Defense 3 Second",
    "Flagrant Type 1",
    "Flagrant Type 2",
    "Clear Path",
    "Transition Take",
    "Away From Play",
}


@dataclass(frozen=True)
class FreeThrowAttempt:
    attempt: int
    total: int
    penalty: str
    team_id: int | None
    made: bool

    @property
    def is_final(self) -> bool:
        return self.attempt == self.total

    @property
    def is_technical(self) -> bool:
        return self.penalty == "technical"

    @property
    def awards_retained_possession(self) -> bool:
        return self.penalty in {"technical", "flagrant", "clear_path"}


def parse_free_throw(event: Mapping[str, object]) -> FreeThrowAttempt:
    if event.get("event_type") != "free_throw":
        raise ValueError("Event is not a free throw")

    subtype = str(event.get("event_subtype") or "")
    match = FREE_THROW_PATTERN.fullmatch(subtype)
    if match is None:
        raise ValueError(f"Unsupported free-throw subtype: {subtype!r}")

    penalty = (match.group("penalty") or "ordinary").lower().replace(" ", "_")
    attempt_text = match.group("attempt")
    total_text = match.group("total")
    if attempt_text is None or total_text is None:
        if penalty != "technical":
            raise ValueError(f"Free throw is missing attempt numbers: {subtype!r}")
        attempt = total = 1
    else:
        attempt = int(attempt_text)
        total = int(total_text)
    if attempt > total:
        raise ValueError(f"Free-throw attempt exceeds total: {subtype!r}")

    shot_result = event.get("shot_result")
    if shot_result not in {"Made", "Missed"}:
        description = str(event.get("description") or "")
        if description.startswith("MISS "):
            shot_result = "Missed"
        elif description:
            shot_result = "Made"
        else:
            raise ValueError("Free throw has no supported result")

    team_id = event.get("event_team_id")
    if team_id is not None and not isinstance(team_id, int):
        raise ValueError(f"Invalid free-throw team ID: {team_id}")
    return FreeThrowAttempt(
        attempt=attempt,
        total=total,
        penalty=penalty,
        team_id=team_id,
        made=shot_result == "Made",
    )


def foul_awards_retained_possession(event_subtype: str | None) -> bool:
    return event_subtype in RETAINED_FOUL_SUBTYPES


def retained_possession_team_id(
    foul: Mapping[str, object], teams: GameTeams
) -> int | None:
    subtype = foul.get("event_subtype")
    if not foul_awards_retained_possession(
        str(subtype) if subtype is not None else None
    ):
        return None
    foul_team_id = foul.get("event_team_id")
    if not isinstance(foul_team_id, int) or not teams.contains(foul_team_id):
        return None
    return teams.opponent(foul_team_id).team_id


def is_and_one_made_shot(
    events: Sequence[Mapping[str, object]], made_shot_index: int
) -> bool:
    shot = events[made_shot_index]
    if shot.get("event_type") != "made_shot":
        return False
    team_id = shot.get("event_team_id")
    period = shot.get("period")
    seconds = shot.get("seconds_remaining_in_period")
    saw_shooting_foul = False

    for event in events[made_shot_index + 1 :]:
        if (
            event.get("period") != period
            or event.get("seconds_remaining_in_period") != seconds
        ):
            break
        if event.get("event_type") == "foul" and event.get("event_subtype") in {
            "Personal",
            "Shooting",
            "Shooting Block",
        }:
            saw_shooting_foul = True
            continue
        if event.get("event_type") == "free_throw":
            attempt = parse_free_throw(event)
            if attempt.is_technical:
                continue
            return (
                saw_shooting_foul
                and attempt.team_id == team_id
                and attempt.attempt == 1
                and attempt.total == 1
            )
        if event.get("event_type") in {"substitution", "timeout", "review"}:
            continue
    return False
