"""Link coach-challenge reviews to timeout rows."""

from dataclasses import dataclass

import pyarrow as pa

CHALLENGE_OUTCOMES = {
    "Coach Challenge Overturn Ruling": "overturned",
    "Coach Challenge Ruling Stands": "ruling_stands",
    "Coach Challenge Support Ruling": "ruling_supported",
}


@dataclass(frozen=True)
class ChallengeLinks:
    timeout_outcomes: tuple[str | None, ...]
    orphan_review_count: int


def link_challenge_reviews(table: pa.Table) -> ChallengeLinks:
    game_ids = table["game_id"].cast(pa.string()).to_pylist()
    periods = table["period"].cast(pa.int8()).to_pylist()
    clocks = table["clock"].cast(pa.string()).to_pylist()
    action_types = table["action_type"].cast(pa.string()).to_pylist()
    subtypes = table["event_subtype"].cast(pa.string()).to_pylist()

    outcomes: list[str | None] = [None] * table.num_rows
    orphan_count = 0
    for review_index, subtype in enumerate(subtypes):
        outcome = CHALLENGE_OUTCOMES.get(subtype or "")
        if action_types[review_index] != "Instant Replay" or outcome is None:
            continue

        timeout_index = review_index - 1
        while timeout_index >= 0:
            same_stoppage = (
                game_ids[timeout_index] == game_ids[review_index]
                and periods[timeout_index] == periods[review_index]
                and clocks[timeout_index] == clocks[review_index]
            )
            if not same_stoppage:
                break
            if action_types[timeout_index] == "Timeout":
                outcomes[timeout_index] = outcome
                break
            timeout_index -= 1
        else:
            timeout_index = -1

        if timeout_index < 0 or outcomes[timeout_index] is None:
            orphan_count += 1

    return ChallengeLinks(tuple(outcomes), orphan_count)
