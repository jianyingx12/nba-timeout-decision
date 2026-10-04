"""Tests for timeout normalization."""

import json
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc

from nba_timeout_decision.normalization.steps.teams import normalize_teams
from nba_timeout_decision.normalization.steps.timeouts import normalize_timeouts


FIXTURE = (
    Path(__file__).parent.parent.parent
    / "fixtures"
    / "play_by_play"
    / "2025_regular_0022500001.json"
)


def timeout_table() -> pa.Table:
    return pa.table(
        {
            "game_id": ["0022500001"] * 8,
            "period": [1] * 8,
            "clock": ["PT06M00.00S"] * 8,
            "action_type": [
                "Made Shot",
                "Made Shot",
                "Timeout",
                "Timeout",
                "Timeout",
                "Timeout",
                "Timeout",
                "Timeout",
            ],
            "event_subtype": [
                None,
                None,
                "Regular",
                "Short",
                "Official",
                "Coach Challenge",
                None,
                "Regular",
            ],
            "description": [
                "Made shot",
                "Made shot",
                "Rockets Timeout: Regular (Reg.1 Short 0)",
                "Player Timeout:Short",
                "Timeout: Official",
                "Rockets Timeout: Coach Challenge",
                "Rockets Timeout: No Timeout",
                "Timeout: Regular",
            ],
            "source_team_id": [1610612760, 1610612745, 0, 1610612745, 0, 0, 0, 0],
            "source_person_id": [1, 2, 1610612745, 99, 0, 1610612745, 1610612745, 0],
            "event_team_id": [1610612760, 1610612745, None, 1610612745, None, None, None, None],
            "event_team_role": ["home", "away", None, "away", None, None, None, None],
        }
    )


class NormalizationTimeoutTests(unittest.TestCase):
    def test_classifies_timeout_types_and_ownership_sources(self) -> None:
        result = normalize_timeouts(timeout_table()).table

        self.assertEqual(
            result["timeout_class"].to_pylist(),
            [
                "none",
                "none",
                "team_regular",
                "team_short",
                "official",
                "coach_challenge",
                "ambiguous",
                "ambiguous",
            ],
        )
        self.assertEqual(
            result["timeout_team_id"].to_pylist(),
            [None, None, 1610612745, 1610612745, None, 1610612745, 1610612745, None],
        )
        self.assertEqual(
            result["timeout_ownership_source"].to_pylist(),
            ["none", "none", "person_id", "event_team", "none", "person_id", "person_id", "none"],
        )
        self.assertEqual(
            result["coach_challenge_outcome"].to_pylist(),
            ["none", "none", "none", "none", "none", "unknown", "none", "none"],
        )

    def test_classifies_saved_real_timeout_fixture(self) -> None:
        with FIXTURE.open(encoding="utf-8") as source:
            fixture = json.load(source)
        events = fixture["events"]
        team_ids = [
            None if event["teamId"] == 0 else event["teamId"] for event in events
        ]
        raw = pa.table(
            {
                "game_id": [fixture["game_id"]] * len(events),
                "action_type": [event["actionType"].strip() for event in events],
                "event_subtype": [event["subType"] for event in events],
                "description": [event["description"] for event in events],
                "source_team_id": [event["teamId"] for event in events],
                "source_person_id": [event["personId"] for event in events],
                "period": [event["period"] for event in events],
                "clock": [event["clock"] for event in events],
                "event_team_id": team_ids,
                "event_team_code": [event["teamTricode"] for event in events],
                "home_team": ["OKC"] * len(events),
                "away_team": ["HOU"] * len(events),
            }
        )

        teams = normalize_teams(raw).table
        result = normalize_timeouts(teams).table
        timeout = result.filter(pc.equal(result["action_type"], "Timeout"))

        self.assertEqual(timeout["timeout_class"].to_pylist(), ["team_regular"])
        self.assertEqual(timeout["timeout_team_id"].to_pylist(), [1610612745])
        self.assertEqual(timeout["timeout_is_ambiguous"].to_pylist(), [False])

    def test_links_regular_timeout_to_coach_challenge_result(self) -> None:
        raw = pa.table(
            {
                "game_id": ["0022500001"] * 4,
                "period": [4] * 4,
                "clock": ["PT02M00.00S"] * 4,
                "action_type": ["Made Shot", "Timeout", "Substitution", "Instant Replay"],
                "event_subtype": [None, "Regular", None, "Coach Challenge Ruling Stands"],
                "description": [
                    "Made shot",
                    "Rockets Timeout: Regular (Reg.5 Short 0)",
                    "SUB: Eason FOR Smith Jr.",
                    "Instant Replay4th Period",
                ],
                "source_team_id": [1610612760, 0, 1610612745, 0],
                "source_person_id": [1, 1610612745, 2, 3],
                "event_team_id": [1610612760, None, 1610612745, None],
                "event_team_role": ["home", None, "away", None],
            }
        )

        result = normalize_timeouts(raw)

        self.assertEqual(
            result.table["timeout_class"].to_pylist(),
            ["none", "coach_challenge", "none", "none"],
        )
        self.assertEqual(
            result.table["coach_challenge_outcome"].to_pylist(),
            ["none", "ruling_stands", "none", "none"],
        )
        self.assertEqual(result.orphan_challenge_review_count, 0)

    def test_reports_challenge_review_without_a_same_clock_timeout(self) -> None:
        raw = pa.table(
            {
                "game_id": ["0022500001"] * 3,
                "period": [4] * 3,
                "clock": ["PT02M01.00S", "PT02M00.00S", "PT02M00.00S"],
                "action_type": ["Timeout", "Made Shot", "Instant Replay"],
                "event_subtype": ["Regular", None, "Coach Challenge Overturn Ruling"],
                "description": [
                    "Rockets Timeout: Regular (Reg.5 Short 0)",
                    "Made shot",
                    "Instant Replay4th Period",
                ],
                "source_team_id": [0, 1610612745, 0],
                "source_person_id": [1610612745, 1, 3],
                "event_team_id": [None, 1610612745, None],
                "event_team_role": [None, "away", None],
            }
        )

        result = normalize_timeouts(raw)

        self.assertEqual(result.orphan_challenge_review_count, 1)
        self.assertEqual(result.table["timeout_class"][0].as_py(), "team_regular")


if __name__ == "__main__":
    unittest.main()
