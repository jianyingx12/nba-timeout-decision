"""Tests for authoritative team-role catalog loading."""

import tempfile
import unittest
from pathlib import Path

from nba_timeout_decision.runs.io.catalog import read_game_teams


class GameCatalogTests(unittest.TestCase):
    def test_filters_partition_and_preserves_team_roles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "games.csv"
            path.write_text(
                "game_id,season_start_year,game_type,home_team,away_team\n"
                "1,2025,regular,HOM,AWY\n"
                "2,2025,playoffs,AAA,BBB\n",
                encoding="utf-8",
            )

            teams = read_game_teams(path, season=2025, game_type="regular")

        self.assertEqual(list(teams), ["0000000001"])
        self.assertEqual(teams["0000000001"].home_team_code, "HOM")
        self.assertEqual(teams["0000000001"].away_team_code, "AWY")


if __name__ == "__main__":
    unittest.main()
