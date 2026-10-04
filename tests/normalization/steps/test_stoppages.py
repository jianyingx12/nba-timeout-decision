"""Tests for stoppage normalization."""

import json
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc

from nba_timeout_decision.normalization.steps.stoppages import normalize_stoppages


FIXTURE = (
    Path(__file__).parent.parent.parent
    / "fixtures"
    / "play_by_play"
    / "2025_regular_0022500001.json"
)


def stoppage_table() -> pa.Table:
    return pa.table(
        {
            "event_type": [
                "substitution",
                "substitution",
                "timeout",
                "review",
                "period_marker",
                "foul",
                "free_throw",
                "violation",
                "other",
                "made_shot",
            ],
            "description": [
                "SUB: Eason FOR Smith Jr.",
                "SUB: Jones FOR",
                "Rockets Timeout: Regular",
                "Instant Replay",
                "End Period",
                "Personal foul",
                "Free Throw 1 of 2",
                "Lane violation",
                "Player leaves with injury",
                "Made shot",
            ],
            "person_id": [1631095, 201935, None, None, None, 1, 2, 3, None, 4],
            "event_team_id": [1610612745, 1610612745, None, None, None, 1, 1, 1, None, 1],
        }
    )


class NormalizationStoppageTests(unittest.TestCase):
    def test_normalizes_substitution_fields_without_inventing_an_id(self) -> None:
        result = normalize_stoppages(stoppage_table())

        self.assertEqual(
            result.table["substitution_team_id"].to_pylist()[:2],
            [1610612745, 1610612745],
        )
        self.assertEqual(
            result.table["substitution_out_player_id"].to_pylist()[:2],
            [1631095, 201935],
        )
        self.assertEqual(
            result.table["substitution_in_player_name"].to_pylist()[:2],
            ["Eason", None],
        )
        self.assertEqual(
            result.table["substitution_in_player_id"].to_pylist()[:2],
            [None, None],
        )
        self.assertEqual(
            result.table["substitution_is_ambiguous"].to_pylist()[:2],
            [False, True],
        )
        self.assertEqual(result.ambiguous_substitution_count, 1)

    def test_classifies_supported_stoppages(self) -> None:
        result = normalize_stoppages(stoppage_table()).table

        self.assertEqual(
            result["stoppage_class"].to_pylist(),
            [
                "substitution",
                "substitution",
                "timeout",
                "review",
                "period_break",
                "foul",
                "free_throw",
                "other",
                "injury",
                "none",
            ],
        )

    def test_normalizes_saved_real_substitution_fixture(self) -> None:
        with FIXTURE.open(encoding="utf-8") as source:
            fixture = json.load(source)
        events = fixture["events"]
        raw = pa.table(
            {
                "event_type": [
                    "substitution" if event["actionType"] == "Substitution" else "other"
                    for event in events
                ],
                "description": [event["description"] for event in events],
                "person_id": [
                    event["personId"] or None for event in events
                ],
                "event_team_id": [event["teamId"] or None for event in events],
            }
        )

        result = normalize_stoppages(raw).table
        substitution = result.filter(
            pc.equal(result["event_type"], "substitution")
        )

        self.assertEqual(substitution["substitution_team_id"].to_pylist(), [1610612745])
        self.assertEqual(substitution["substitution_out_player_id"].to_pylist(), [1631095])
        self.assertEqual(substitution["substitution_in_player_name"].to_pylist(), ["Eason"])
        self.assertEqual(substitution["substitution_in_player_id"].to_pylist(), [None])
        self.assertEqual(substitution["substitution_is_ambiguous"].to_pylist(), [False])


if __name__ == "__main__":
    unittest.main()
