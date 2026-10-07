"""Check scoring-run tables for contract and relationship violations."""

from collections import Counter, defaultdict
from dataclasses import dataclass

import pyarrow as pa

from ..contract import (
    EXCLUSION_REASONS,
    RUN_SCHEMA,
    RUN_THRESHOLDS,
    SENSITIVITY_SIGNAL_SCHEMA,
    SENSITIVITY_WINDOW_SIZES,
    TERMINATION_REASONS,
    THRESHOLD_CROSSING_SCHEMA,
)
from ..sensitivity import STRICT_THRESHOLDS


@dataclass(frozen=True)
class RunValidation:
    valid: bool
    errors: tuple[str, ...]
    run_count: int
    threshold_crossing_count: int
    sensitivity_signal_count: int
    primary_eligible_run_count: int
    threshold_counts: tuple[tuple[int, int], ...]
    termination_counts: tuple[tuple[str, int], ...]
    exclusion_counts: tuple[tuple[str, int], ...]


def _schema_error(table: pa.Table, expected: pa.Schema, name: str) -> str | None:
    if not table.schema.equals(expected):
        return f"{name} does not match its canonical schema"
    return None


def _run_errors(rows: list[dict[str, object]]) -> list[str]:
    errors: list[str] = []
    run_ids = [str(row["run_id"]) for row in rows]
    if len(run_ids) != len(set(run_ids)):
        errors.append("Run IDs are not unique")
    for row in rows:
        run_id = str(row["run_id"])
        if not run_id.startswith(f"{row['game_id']}-R"):
            errors.append(f"Run ID does not match its game: {run_id}")
        if not (
            int(row["start_possession_number"])
            <= int(row["qualification_possession_number"])
            <= int(row["end_possession_number"])
        ):
            errors.append(f"Possession bounds are invalid for {run_id}")
        if not (
            int(row["start_checkpoint_number"])
            <= int(row["qualification_checkpoint_number"])
            <= int(row["end_checkpoint_number"])
        ):
            errors.append(f"Checkpoint bounds are invalid for {run_id}")
        if int(row["first_threshold"]) != RUN_THRESHOLDS[0]:
            errors.append(f"First threshold is invalid for {run_id}")
        if int(row["maximum_threshold"]) not in RUN_THRESHOLDS:
            errors.append(f"Maximum threshold is invalid for {run_id}")
        if int(row["net_points_at_qualification"]) < RUN_THRESHOLDS[0]:
            errors.append(f"Qualification net points are invalid for {run_id}")
        if row["termination_reason"] not in TERMINATION_REASONS:
            errors.append(f"Termination reason is invalid for {run_id}")
        exclusion = row["exclusion_reason"]
        if exclusion is not None and exclusion not in EXCLUSION_REASONS:
            errors.append(f"Exclusion reason is invalid for {run_id}")
        if bool(row["primary_analysis_eligible"]) != (exclusion is None):
            errors.append(f"Eligibility and exclusion disagree for {run_id}")
        if (
            exclusion == "period_ended_at_qualification"
            and row["termination_reason"] != "period_end"
        ):
            errors.append(f"Period-end exclusion is inconsistent for {run_id}")
    return errors


def _crossing_errors(
    rows: list[dict[str, object]], runs: dict[str, dict[str, object]]
) -> list[str]:
    errors: list[str] = []
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    seen: set[tuple[str, int]] = set()
    for row in rows:
        run_id = str(row["run_id"])
        threshold = int(row["threshold"])
        if run_id not in runs:
            errors.append(f"Threshold crossing references unknown run {run_id}")
            continue
        if (run_id, threshold) in seen:
            errors.append(f"Threshold {threshold} is duplicated for {run_id}")
        seen.add((run_id, threshold))
        grouped[run_id].append(row)
        run = runs[run_id]
        if row["game_id"] != run["game_id"] or row["period"] != run["period"]:
            errors.append(f"Threshold crossing identity disagrees for {run_id}")
        if threshold not in RUN_THRESHOLDS:
            errors.append(f"Threshold value is invalid for {run_id}")
        elif int(row["crossing_sequence"]) != RUN_THRESHOLDS.index(threshold) + 1:
            errors.append(f"Threshold sequence is invalid for {run_id}")
        if int(row["net_points"]) < threshold:
            errors.append(f"Threshold evidence is insufficient for {run_id}")

    for run_id, run in runs.items():
        crossings = grouped.get(run_id, [])
        thresholds = [int(row["threshold"]) for row in crossings]
        if thresholds != sorted(thresholds):
            errors.append(f"Threshold crossings are not ordered for {run_id}")
        if not thresholds or thresholds[0] != RUN_THRESHOLDS[0]:
            errors.append(f"Run has no primary threshold crossing: {run_id}")
        elif thresholds[-1] != int(run["maximum_threshold"]):
            errors.append(f"Maximum threshold disagrees for {run_id}")
    return errors


def _sensitivity_errors(rows: list[dict[str, object]]) -> list[str]:
    errors: list[str] = []
    alternate_definitions = {
        f"net_plus_6_over_{size}_possessions": size
        for size in SENSITIVITY_WINDOW_SIZES
    }
    strict_definitions = {
        f"strict_unanswered_{threshold}_0": threshold
        for threshold in STRICT_THRESHOLDS
    }
    for row in rows:
        definition = str(row["definition"])
        if definition in alternate_definitions:
            if int(row["window_size"]) != alternate_definitions[definition]:
                errors.append(f"Sensitivity window disagrees for {definition}")
            if int(row["threshold"]) != 6:
                errors.append(f"Sensitivity threshold disagrees for {definition}")
        elif definition in strict_definitions:
            threshold = strict_definitions[definition]
            if not bool(row["strict_unanswered"]):
                errors.append(f"Strict definition contains opponent points: {definition}")
            if int(row["run_team_points"]) < threshold:
                errors.append(f"Strict definition has insufficient points: {definition}")
        else:
            errors.append(f"Unknown sensitivity definition: {definition}")
        if float(row["elapsed_seconds"]) < 0:
            errors.append(f"Sensitivity duration is negative for {definition}")
    return errors


def validate_outputs(
    runs: pa.Table,
    threshold_crossings: pa.Table,
    sensitivity_signals: pa.Table,
) -> RunValidation:
    errors = [
        error
        for error in (
            _schema_error(runs, RUN_SCHEMA, "Runs"),
            _schema_error(
                threshold_crossings,
                THRESHOLD_CROSSING_SCHEMA,
                "Threshold crossings",
            ),
            _schema_error(
                sensitivity_signals,
                SENSITIVITY_SIGNAL_SCHEMA,
                "Sensitivity signals",
            ),
        )
        if error is not None
    ]
    if errors:
        return RunValidation(
            False,
            tuple(errors),
            runs.num_rows,
            threshold_crossings.num_rows,
            sensitivity_signals.num_rows,
            0,
            (),
            (),
            (),
        )

    run_rows = runs.to_pylist()
    crossing_rows = threshold_crossings.to_pylist()
    sensitivity_rows = sensitivity_signals.to_pylist()
    run_by_id = {str(row["run_id"]): row for row in run_rows}
    errors.extend(_run_errors(run_rows))
    errors.extend(_crossing_errors(crossing_rows, run_by_id))
    errors.extend(_sensitivity_errors(sensitivity_rows))
    threshold_counts = Counter(int(row["threshold"]) for row in crossing_rows)
    termination_counts = Counter(str(row["termination_reason"]) for row in run_rows)
    exclusion_counts = Counter(
        str(row["exclusion_reason"])
        for row in run_rows
        if row["exclusion_reason"] is not None
    )
    return RunValidation(
        valid=not errors,
        errors=tuple(errors),
        run_count=len(run_rows),
        threshold_crossing_count=len(crossing_rows),
        sensitivity_signal_count=len(sensitivity_rows),
        primary_eligible_run_count=sum(
            bool(row["primary_analysis_eligible"]) for row in run_rows
        ),
        threshold_counts=tuple(sorted(threshold_counts.items())),
        termination_counts=tuple(sorted(termination_counts.items())),
        exclusion_counts=tuple(sorted(exclusion_counts.items())),
    )
