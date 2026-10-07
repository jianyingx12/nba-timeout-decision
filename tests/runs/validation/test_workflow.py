"""Tests for batch run-validation reporting."""

import unittest
from pathlib import Path
from unittest.mock import patch

from nba_timeout_decision.runs.validation.workflow import (
    PartitionValidation,
    validate_partitions,
)


class RunValidationWorkflowTests(unittest.TestCase):
    @patch(
        "nba_timeout_decision.runs.validation.workflow."
        "validate_materialized_partition"
    )
    def test_summarizes_valid_and_invalid_partitions(self, validate) -> None:
        validate.side_effect = (
            PartitionValidation(2013, "regular", True, (), 2, 3, 3, 4, 5, True),
            PartitionValidation(
                2013, "playoffs", False, ("bad output",), 1, 0, 0, 0, 0, False
            ),
        )

        report = validate_partitions(
            seasons=[2013],
            game_types=["regular", "playoffs"],
            possession_root=Path("possessions"),
            possession_manifest=Path("possession-manifest.json"),
            catalog_root=Path("catalog"),
            output_root=Path("missing-runs"),
            manifest_path=Path("run-manifest.json"),
        )

        self.assertFalse(report["valid"])
        self.assertEqual(report["valid_partitions"], 1)
        self.assertEqual(report["invalid_partitions"], 1)
        self.assertEqual(report["games"], 3)
        self.assertEqual(report["runs"], 3)


if __name__ == "__main__":
    unittest.main()
