"""Tests for possession review windows."""

import unittest

from nba_timeout_decision.possessions.steps.reviews import review_follows_boundary


class ReviewWindowTests(unittest.TestCase):
    def test_finds_review_after_timeout_at_same_clock(self) -> None:
        events = [
            {"period": 4, "seconds_remaining_in_period": 100.0, "event_type": "turnover"},
            {"period": 4, "seconds_remaining_in_period": 100.0, "event_type": "timeout"},
            {"period": 4, "seconds_remaining_in_period": 100.0, "event_type": "review"},
        ]

        self.assertTrue(review_follows_boundary(events, 0))

    def test_stops_when_clock_changes_before_review(self) -> None:
        events = [
            {"period": 4, "seconds_remaining_in_period": 100.0, "event_type": "turnover"},
            {"period": 4, "seconds_remaining_in_period": 90.0, "event_type": "timeout"},
            {"period": 4, "seconds_remaining_in_period": 90.0, "event_type": "review"},
        ]

        self.assertFalse(review_follows_boundary(events, 0))


if __name__ == "__main__":
    unittest.main()
