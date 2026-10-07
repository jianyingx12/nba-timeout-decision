"""Tests for scoring-run validation arguments."""

import unittest
from pathlib import Path

from nba_timeout_decision.runs.cli.validate import parse_args


class RunValidationCliTests(unittest.TestCase):
    def test_uses_full_project_paths_by_default(self) -> None:
        args = parse_args([])

        self.assertEqual(args.first_season, 2013)
        self.assertEqual(args.last_season, 2025)
        self.assertEqual(args.output_root, Path("data/derived/runs"))
        self.assertEqual(args.report, Path("data/reports/run-validation.json"))
        self.assertFalse(args.skip_recompute)


if __name__ == "__main__":
    unittest.main()
