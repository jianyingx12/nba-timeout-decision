"""Tests for field normalization."""

import unittest

import pyarrow as pa

from nba_timeout_decision.normalization.steps.fields import (
    normalize_identifiers_and_labels,
)


def source_table(action_ids: list[int]) -> pa.Table:
    row_count = len(action_ids)
    return pa.table(
        {
            "game_id": ["0022500001"] * row_count,
            "actionId": action_ids,
            "actionNumber": list(range(10, 10 + row_count)),
            "teamId": [0, 1610612745][:row_count],
            "teamTricode": [None, " HOU "][:row_count],
            "personId": [0, 1641708][:row_count],
            "playerName": [None, " Thompson "][:row_count],
            "playerNameI": [None, " A. Thompson "][:row_count],
            "shotResult": [None, " Made "][:row_count],
            "location": [None, " H "][:row_count],
            "actionType": [" Timeout ", "Made Shot"][:row_count],
            "subType": ["   ", " Pullup Jump shot "][:row_count],
            "description": [None, " Thompson makes shot "][:row_count],
        }
    )


class NormalizationFieldTests(unittest.TestCase):
    def test_normalizes_identifiers_and_labels_without_losing_raw_values(self) -> None:
        result = normalize_identifiers_and_labels(source_table([1, 2]))

        self.assertEqual(result["action_id"].type, pa.int64())
        self.assertEqual(result["action_id"].to_pylist(), [1, 2])
        self.assertEqual(result["source_team_id"].to_pylist(), [0, 1610612745])
        self.assertEqual(result["event_team_id"].to_pylist(), [None, 1610612745])
        self.assertEqual(result["person_id"].to_pylist(), [None, 1641708])
        self.assertEqual(result["event_team_code"].to_pylist(), [None, "HOU"])
        self.assertEqual(result["action_type"].to_pylist(), ["Timeout", "Made Shot"])
        self.assertEqual(result["event_subtype"].to_pylist(), [None, "Pullup Jump shot"])
        self.assertEqual(result["description"].to_pylist(), [None, "Thompson makes shot"])
        self.assertEqual(result["source_action_type"].to_pylist(), [" Timeout ", "Made Shot"])
        self.assertEqual(result["source_sub_type"].to_pylist(), ["   ", " Pullup Jump shot "])

    def test_rejects_nonincreasing_action_ids_within_a_game(self) -> None:
        with self.assertRaisesRegex(ValueError, "not strictly increasing"):
            normalize_identifiers_and_labels(source_table([2, 1]))


if __name__ == "__main__":
    unittest.main()
