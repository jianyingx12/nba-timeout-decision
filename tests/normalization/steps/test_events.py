"""Tests for event classification."""

import unittest

import pyarrow as pa

from nba_timeout_decision.normalization.steps.events import normalize_events


class NormalizationEventTests(unittest.TestCase):
    def test_classifies_source_actions_and_normalizes_details(self) -> None:
        table = pa.table(
            {
                "action_type": ["Made Shot", "Heave", "Instant Replay", None],
                "xLegacy": [10, 0, 0, 0],
                "yLegacy": [20, 0, 0, 0],
                "shotDistance": [3, 50, 0, 0],
                "isFieldGoal": [1, 0, 0, 0],
                "pointsTotal": [2, 0, 0, 0],
                "videoAvailable": [1, 0, 1, 0],
                "shotValue": [2, None, None, None],
            }
        )

        result = normalize_events(table)

        self.assertEqual(
            result.table["event_type"].to_pylist(),
            ["made_shot", "heave", "review", "other"],
        )
        self.assertEqual(result.table["is_field_goal"].to_pylist(), [True, False, False, False])
        self.assertEqual(result.table["video_available"].to_pylist(), [True, False, True, False])
        self.assertEqual(result.table["shot_value"].to_pylist(), [2, None, None, None])
        self.assertEqual(result.unmapped_labels, ())

    def test_preserves_unmapped_action_as_other(self) -> None:
        table = pa.table(
            {
                "action_type": ["New Action"],
                "xLegacy": [0],
                "yLegacy": [0],
                "shotDistance": [0],
                "isFieldGoal": [0],
                "pointsTotal": [0],
                "videoAvailable": [0],
                "shotValue": [None],
            }
        )

        result = normalize_events(table)

        self.assertEqual(result.table["event_type"].to_pylist(), ["other"])
        self.assertEqual(result.table["action_type"].to_pylist(), ["New Action"])
        self.assertEqual(result.unmapped_labels, (("New Action", 1),))


if __name__ == "__main__":
    unittest.main()
