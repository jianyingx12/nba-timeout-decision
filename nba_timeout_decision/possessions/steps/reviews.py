"""Identify review windows that can alter a possession boundary."""

from typing import Mapping, Sequence


def review_follows_boundary(
    events: Sequence[Mapping[str, object]], boundary_index: int
) -> bool:
    boundary = events[boundary_index]
    period = boundary.get("period")
    seconds = boundary.get("seconds_remaining_in_period")

    for event in events[boundary_index + 1 :]:
        if event.get("period") != period:
            break
        if event.get("seconds_remaining_in_period") != seconds:
            break
        if event.get("event_type") == "review":
            return True
    return False
