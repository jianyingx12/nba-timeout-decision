"""Tests for scoring-run detection arguments."""

import unittest
from pathlib import Path

from nba_timeout_decision.runs.cli.detect import parse_args


class RunCliTests(unittest.TestCase):
    def test_uses_project_data_paths_by_default(self) -> None:
        args = parse_args([])

        self.assertEqual(args.first_season, 2013)
        self.assertEqual(args.last_season, 2025)
        self.assertEqual(args.possession_root, Path("data/derived/possessions"))
        self.assertEqual(args.catalog_root, Path("data/catalog"))
        self.assertEqual(args.output_root, Path("data/derived/runs"))

    def test_accepts_a_single_partition(self) -> None:
        args = parse_args(
            [
                "--first-season",
                "2025",
                "--last-season",
                "2025",
                "--game-types",
                "regular",
                "--refresh",
            ]
        )

        self.assertEqual(args.game_types, ["regular"])
        self.assertTrue(args.refresh)


if __name__ == "__main__":
    unittest.main()
