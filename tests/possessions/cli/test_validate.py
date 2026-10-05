"""Tests for possession validation arguments."""

import unittest
from pathlib import Path

from nba_timeout_decision.possessions.cli.validate import parse_args


class PossessionValidationCliTests(unittest.TestCase):
    def test_uses_generated_data_paths_by_default(self) -> None:
        args = parse_args([])

        self.assertEqual(args.manifest, Path("data/derived/possession-manifest.json"))
        self.assertEqual(args.report, Path("data/reports/possession-validation.json"))

    def test_accepts_a_playoff_sample(self) -> None:
        args = parse_args(
            [
                "--first-season",
                "2019",
                "--last-season",
                "2019",
                "--game-types",
                "playoffs",
            ]
        )

        self.assertEqual(args.game_types, ["playoffs"])


if __name__ == "__main__":
    unittest.main()
