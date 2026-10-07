"""Group rolling score signals into scoring-run episodes."""

from .episodes import DetectedRuns, detect_primary_runs

__all__ = ["DetectedRuns", "detect_primary_runs"]
