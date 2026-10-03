import json
import unittest
from pathlib import Path


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "play_by_play"
    / "2025_regular_0022500001.json"
)


def load_events() -> list[dict[str, object]]:
    with FIXTURE.open(encoding="utf-8") as source:
        return json.load(source)["events"]


class EventFixtureTests(unittest.TestCase):
    def test_timeout_fixture_preserves_source_encoding(self) -> None:
        events = load_events()
        timeout = next(event for event in events if event["actionType"] == "Timeout")

        self.assertEqual(timeout["actionId"], 44)
        self.assertEqual(timeout["teamId"], 0)
        self.assertEqual(timeout["personId"], 1610612745)
        self.assertEqual(timeout["subType"], "Regular")
        self.assertIn("Rockets Timeout", timeout["description"])

    def test_substitution_fixture_preserves_context_and_order(self) -> None:
        events = load_events()
        action_ids = [int(event["actionId"]) for event in events]
        substitution = next(
            event for event in events if event["actionType"] == "Substitution"
        )

        self.assertEqual(action_ids, list(range(42, 52)))
        self.assertEqual(substitution["actionId"], 49)
        self.assertEqual(substitution["teamId"], 1610612745)
        self.assertEqual(substitution["personId"], 1631095)
        self.assertIsNone(substitution["subType"])
        self.assertEqual(substitution["description"], "SUB: Eason FOR Smith Jr.")


if __name__ == "__main__":
    unittest.main()
