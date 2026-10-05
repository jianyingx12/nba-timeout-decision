"""Check game coverage, score state, and possession sequencing."""

from collections import Counter, defaultdict
from dataclasses import dataclass

import pyarrow as pa


@dataclass(frozen=True)
class PartitionChecks:
    source_games: int
    accepted_games: int
    rejected_games: int
    possessions: int
    ambiguous_possessions: int
    unassigned_score_points: int
    imbalanced_games: int
    issues: tuple[str, ...]


def check_partition(
    source: pa.Table,
    possessions: pa.Table,
    *,
    rejected_game_ids: set[str],
) -> PartitionChecks:
    source_rows: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in source.select(["game_id", "home_score", "away_score"]).to_pylist():
        source_rows[str(row["game_id"])].append(row)

    possession_rows: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in possessions.to_pylist():
        possession_rows[str(row["game_id"])].append(row)

    source_games = set(source_rows)
    accepted_games = set(possession_rows)
    issues: list[str] = []
    overlap = accepted_games & rejected_game_ids
    missing = source_games - accepted_games - rejected_game_ids
    extra = (accepted_games | rejected_game_ids) - source_games
    if overlap:
        issues.append(f"{len(overlap)} games are both accepted and rejected")
    if missing:
        issues.append(f"{len(missing)} source games are unaccounted for")
    if extra:
        issues.append(f"{len(extra)} non-source games are present")

    ambiguous = 0
    unassigned_points = 0
    imbalanced_games = 0
    for game_id, rows in possession_rows.items():
        rows.sort(key=lambda row: int(row["possession_number"]))
        numbers = [int(row["possession_number"]) for row in rows]
        if numbers != list(range(1, len(rows) + 1)):
            issues.append(f"{game_id}: possession numbers are not sequential")

        ambiguous += sum(bool(row["possession_is_ambiguous"]) for row in rows)
        team_counts = Counter(row["offense_team_id"] for row in rows)
        if len(team_counts) != 2 or max(team_counts.values()) - min(
            team_counts.values()
        ) > 1:
            imbalanced_games += 1

        source_game = source_rows.get(game_id)
        if source_game is None:
            continue
        initial_home = int(source_game[0]["home_score"])
        initial_away = int(source_game[0]["away_score"])
        final_home = int(source_game[-1]["home_score"])
        final_away = int(source_game[-1]["away_score"])
        previous_home = initial_home
        previous_away = initial_away
        assigned_home = 0
        assigned_away = 0
        gap_home = 0
        gap_away = 0
        for row in rows:
            start_home = int(row["start_home_score"])
            start_away = int(row["start_away_score"])
            end_home = int(row["end_home_score"])
            end_away = int(row["end_away_score"])
            deltas = (
                start_home - previous_home,
                start_away - previous_away,
                end_home - start_home,
                end_away - start_away,
            )
            if any(delta < 0 for delta in deltas):
                revision_is_recorded = bool(
                    row.get("contains_score_revision", False)
                ) or (
                    row.get("ambiguity_reason")
                    == "score_revision_crosses_boundary"
                )
                if not revision_is_recorded:
                    issues.append(f"{game_id}: possession score state decreases")
                    break
            gap_home += deltas[0]
            gap_away += deltas[1]
            assigned_home += deltas[2]
            assigned_away += deltas[3]
            previous_home = end_home
            previous_away = end_away
        else:
            trailing_home = final_home - previous_home
            trailing_away = final_away - previous_away
            if trailing_home < 0 or trailing_away < 0:
                issues.append(f"{game_id}: output exceeds canonical final score")
                continue
            gap_home += trailing_home
            gap_away += trailing_away
            if (
                initial_home + assigned_home + gap_home != final_home
                or initial_away + assigned_away + gap_away != final_away
            ):
                issues.append(f"{game_id}: score accounting does not reconcile")
            unassigned_points += gap_home + gap_away

    return PartitionChecks(
        source_games=len(source_games),
        accepted_games=len(accepted_games),
        rejected_games=len(rejected_game_ids),
        possessions=possessions.num_rows,
        ambiguous_possessions=ambiguous,
        unassigned_score_points=unassigned_points,
        imbalanced_games=imbalanced_games,
        issues=tuple(issues),
    )
