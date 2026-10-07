"""Tests for primary scoring-run episodes and threshold crossings."""

import unittest

import pyarrow as pa

from nba_timeout_decision.runs.detection import detect_primary_runs
from nba_timeout_decision.runs.ledger.builder import build_game_ledger
from tests.runs.ledger.test_builder import BUILD_ARGUMENTS, possession


def detect(rows: list[dict[str, object]]):
    ledger = build_game_ledger(
        pa.Table.from_pylist(rows), **BUILD_ARGUMENTS
    ).table
    return detect_primary_runs(ledger)


class RunEpisodeTests(unittest.TestCase):
    def test_groups_escalations_under_one_stable_run_id(self) -> None:
        result = detect(
            [
                possession(1, end_home=2),
                possession(2, offense_id=20, start_home=2, end_home=2),
                possession(3, start_home=2, end_home=4),
                possession(4, offense_id=20, start_home=4, end_home=6),
                possession(5, start_home=6, end_home=8),
                possession(6, offense_id=20, start_home=8, end_home=10),
                possession(7, start_home=10, end_home=12),
            ]
        )

        runs = result.runs.to_pylist()
        crossings = result.threshold_crossings.to_pylist()

        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["run_id"], "0000000001-R0001")
        self.assertEqual(runs[0]["start_checkpoint_number"], 1)
        self.assertEqual(runs[0]["qualification_checkpoint_number"], 4)
        self.assertEqual(runs[0]["maximum_threshold"], 8)
        self.assertEqual(runs[0]["termination_reason"], "game_end")
        self.assertEqual([row["threshold"] for row in crossings], [6, 8])
        self.assertEqual([row["crossing_sequence"] for row in crossings], [1, 2])
        self.assertEqual(
            {row["run_id"] for row in crossings}, {"0000000001-R0001"}
        )

    def test_records_all_thresholds_reached_at_first_crossing(self) -> None:
        result = detect(
            [
                possession(1, end_home=3),
                possession(2, offense_id=20, start_home=3, end_home=3),
                possession(3, start_home=3, end_home=7),
                possession(4, offense_id=20, start_home=7, end_home=12),
            ]
        )

        self.assertEqual(
            [row["threshold"] for row in result.threshold_crossings.to_pylist()],
            [6, 8, 10, 12],
        )
        self.assertEqual(result.runs.to_pylist()[0]["maximum_threshold"], 12)

    def test_opponent_signal_starts_a_new_run(self) -> None:
        result = detect(
            [
                possession(1, end_home=2),
                possession(2, offense_id=20, start_home=2, end_home=2),
                possession(3, start_home=2, end_home=4),
                possession(4, offense_id=20, start_home=4, end_home=6),
                possession(
                    5,
                    offense_id=20,
                    start_home=6,
                    end_home=6,
                    end_away=3,
                ),
                possession(
                    6,
                    start_home=6,
                    end_home=6,
                    start_away=3,
                    end_away=5,
                ),
                possession(
                    7,
                    offense_id=20,
                    start_home=6,
                    end_home=6,
                    start_away=5,
                    end_away=8,
                ),
                possession(
                    8,
                    start_home=6,
                    end_home=6,
                    start_away=8,
                    end_away=10,
                ),
            ]
        )

        runs = result.runs.to_pylist()

        self.assertEqual(len(runs), 2)
        self.assertEqual([row["run_team_code"] for row in runs], ["HOM", "AWY"])
        self.assertEqual(runs[0]["termination_reason"], "net_advantage_lost")
        self.assertEqual(runs[1]["run_id"], "0000000001-R0002")

    def test_period_end_closes_and_excludes_new_qualification(self) -> None:
        result = detect(
            [
                possession(1, end_home=2),
                possession(2, offense_id=20, start_home=2, end_home=2),
                possession(3, start_home=2, end_home=4),
                possession(
                    4,
                    offense_id=20,
                    start_home=4,
                    end_home=6,
                    censored=True,
                ),
            ]
        )

        row = result.runs.to_pylist()[0]

        self.assertEqual(row["termination_reason"], "period_end")
        self.assertFalse(row["primary_analysis_eligible"])
        self.assertEqual(row["exclusion_reason"], "period_ended_at_qualification")

    def test_between_possession_crossing_keeps_adjacent_event_bounds(self) -> None:
        result = detect(
            [
                possession(1, end_home=2),
                possession(2, start_home=2, end_home=2),
                possession(3, start_home=2, end_home=4),
                possession(4, start_home=4, end_home=4),
                possession(5, start_home=6, end_home=6),
            ]
        )

        crossing = result.threshold_crossings.to_pylist()[0]

        self.assertIsNone(crossing["action_id"])
        self.assertEqual(crossing["previous_possession_last_action_id"], 45)
        self.assertEqual(crossing["current_possession_first_action_id"], 50)
        self.assertEqual(
            crossing["previous_possession_last_source_row_number"], 44
        )
        self.assertEqual(
            crossing["current_possession_first_source_row_number"], 49
        )

    def test_ambiguity_terminates_an_active_run(self) -> None:
        result = detect(
            [
                possession(1, end_home=2),
                possession(2, offense_id=20, start_home=2, end_home=2),
                possession(3, start_home=2, end_home=4),
                possession(4, offense_id=20, start_home=4, end_home=6),
                possession(5, start_home=6, end_home=6, ambiguous=True),
            ]
        )

        self.assertEqual(
            result.runs.to_pylist()[0]["termination_reason"],
            "ambiguous_possession",
        )


if __name__ == "__main__":
    unittest.main()
