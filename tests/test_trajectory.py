from __future__ import annotations

import unittest

from av_trace.schemas import SchemaRegistry
from av_trace.trajectory import validate_action, validate_trajectory
from av_trace.util import response_content_hash, trajectory_content_hash

from tests.helpers import ROOT, fixture, positive_trajectory


class TrajectoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = SchemaRegistry(ROOT)

    def test_positive_trajectory_passes(self) -> None:
        report = validate_trajectory(positive_trajectory(), self.registry)
        self.assertTrue(report.ok, report.to_dict())

    def test_cause_probabilities_must_sum_to_one(self) -> None:
        action = fixture("docs/spec/fixtures/positive_agent_action.json")
        action["belief_state"]["missingness_cause_probabilities"]["uncertain"] = 0.5
        report = validate_action(action, self.registry)
        self.assertFalse(report.ok)
        self.assertIn("TRJ-006", {issue.code for issue in report.issues})

    def test_finalize_belief_must_match_final_answer(self) -> None:
        trajectory = positive_trajectory()
        trajectory["events"][-1]["action"]["belief_state"]["p_sufficient"] = 0.5
        report = validate_trajectory(trajectory, self.registry)
        self.assertIn("TRJ-007", {issue.code for issue in report.issues})

    def test_step_indices_must_be_contiguous(self) -> None:
        trajectory = positive_trajectory()
        trajectory["events"][1]["action"]["step_index"] = 4
        trajectory["events"][1]["response"]["step_index"] = 4
        report = validate_trajectory(trajectory, self.registry)
        self.assertIn("TRJ-001", {issue.code for issue in report.issues})

    def test_action_and_response_tool_must_match(self) -> None:
        trajectory = positive_trajectory()
        trajectory["events"][1]["response"]["tool"] = "search_speech"
        report = validate_trajectory(trajectory, self.registry)
        self.assertIn("TRJ-001", {issue.code for issue in report.issues})

    def test_citation_must_reference_returned_observation(self) -> None:
        trajectory = positive_trajectory()
        final = trajectory["events"][-1]["action"]["action"]["arguments"]
        final["claims"][0]["citations"][0]["observation_id"] = "obs.missing"
        trajectory["final_output"] = final
        report = validate_trajectory(trajectory, self.registry)
        self.assertIn("TRJ-003", {issue.code for issue in report.issues})

    def test_cost_must_match_schedule(self) -> None:
        trajectory = positive_trajectory()
        trajectory["events"][1]["response"]["cost_charged"] = 2.0
        report = validate_trajectory(trajectory, self.registry)
        self.assertIn("TRJ-004", {issue.code for issue in report.issues})

    def test_payload_hash_must_match_payload(self) -> None:
        trajectory = positive_trajectory()
        trajectory["events"][1]["response"]["results"][0]["payload"]["text"] = "tampered"
        report = validate_trajectory(trajectory, self.registry)
        self.assertIn("TRJ-003", {issue.code for issue in report.issues})

    def test_response_hash_must_match_response(self) -> None:
        trajectory = positive_trajectory()
        trajectory["events"][0]["response"]["response_hash"] = "sha256:" + "0" * 64
        report = validate_trajectory(trajectory, self.registry)
        self.assertIn("TRJ-003", {issue.code for issue in report.issues})

    def test_trajectory_hash_must_match_content(self) -> None:
        trajectory = positive_trajectory()
        trajectory["replay"]["trajectory_hash"] = "sha256:" + "0" * 64
        report = validate_trajectory(trajectory, self.registry)
        self.assertIn("TRJ-003", {issue.code for issue in report.issues})

    def test_protocol_invalid_completion_cannot_pass(self) -> None:
        trajectory = positive_trajectory()
        trajectory["completion"]["status"] = "invalid"
        trajectory["completion"]["protocol_valid"] = False
        from av_trace.util import trajectory_content_hash
        trajectory["replay"]["trajectory_hash"] = trajectory_content_hash(trajectory)
        report = validate_trajectory(trajectory, self.registry)
        self.assertIn("TRJ-005", {issue.code for issue in report.issues})

    def test_action_interval_must_be_within_source(self) -> None:
        trajectory = positive_trajectory()
        trajectory["events"][1]["action"]["action"]["arguments"]["interval"]["end_s"] = 1300.0
        from av_trace.util import trajectory_content_hash
        trajectory["replay"]["trajectory_hash"] = trajectory_content_hash(trajectory)
        report = validate_trajectory(trajectory, self.registry)
        self.assertIn("TIME-002", {issue.code for issue in report.issues})

    def test_tool_result_type_must_match_tool(self) -> None:
        trajectory = positive_trajectory()
        response = trajectory["events"][0]["response"]
        response["results"] = [
            {
                "result_type": "search_pointer",
                "result_id": "ptr.e1",
                "interval": {"start_s": 100.0, "end_s": 110.0},
                "score": 1.0,
                "preview": "wrong result type",
            }
        ]
        response["response_hash"] = response_content_hash(response)
        trajectory["replay"]["trajectory_hash"] = trajectory_content_hash(trajectory)
        report = validate_trajectory(trajectory, self.registry)
        self.assertIn("TRJ-001", {issue.code for issue in report.issues})

    def test_event_timestamps_must_be_nondecreasing(self) -> None:
        trajectory = positive_trajectory()
        trajectory["events"][1]["recorded_at"] = "2026-09-04T23:59:59Z"
        trajectory["replay"]["trajectory_hash"] = trajectory_content_hash(trajectory)
        report = validate_trajectory(trajectory, self.registry)
        self.assertIn("TRJ-002", {issue.code for issue in report.issues})

    def test_budget_exhausted_response_can_be_zero_cost(self) -> None:
        trajectory = positive_trajectory()
        trajectory["episode_start"]["budget"]["cost_limit"] = 0.25
        trajectory["events"][0]["response"]["cost_remaining"] = 0.0
        trajectory["events"][0]["response"]["response_hash"] = response_content_hash(
            trajectory["events"][0]["response"]
        )
        event = trajectory["events"][1]
        event["response"].update(
            {
                "status": "budget_exhausted",
                "cost_charged": 0.0,
                "cost_used_total": 0.25,
                "cost_remaining": 0.0,
                "results": [],
                "error": {
                    "code": "BUDGET_EXHAUSTED",
                    "retryable": False,
                    "message": "The requested call would exceed the episode budget.",
                    "retry_after_step": None,
                },
            }
        )
        trajectory["completion"]["total_cost"] = 0.25
        final = trajectory["events"][-1]["action"]["action"]["arguments"]
        final["answer_mode"] = "abstain"
        final["claims"] = []
        final["natural_language_answer"] = ""
        final["termination_reason"] = "budget_guard"
        trajectory["final_output"] = final
        event["response"]["response_hash"] = response_content_hash(event["response"])
        trajectory["replay"]["trajectory_hash"] = trajectory_content_hash(trajectory)
        report = validate_trajectory(trajectory, self.registry)
        self.assertTrue(report.ok, report.to_dict())

    def test_false_budget_exhaustion_is_rejected(self) -> None:
        trajectory = positive_trajectory()
        event = trajectory["events"][1]
        event["response"].update(
            {
                "status": "budget_exhausted",
                "cost_charged": 0.0,
                "cost_used_total": 0.25,
                "cost_remaining": 11.75,
                "results": [],
                "error": {
                    "code": "BUDGET_EXHAUSTED",
                    "retryable": False,
                    "message": "The requested call would exceed the episode budget.",
                    "retry_after_step": None,
                },
            }
        )
        event["response"]["response_hash"] = response_content_hash(event["response"])
        final = trajectory["events"][-1]["action"]["action"]["arguments"]
        final["answer_mode"] = "abstain"
        final["claims"] = []
        final["natural_language_answer"] = ""
        final["termination_reason"] = "budget_guard"
        trajectory["final_output"] = final
        trajectory["completion"]["total_cost"] = 0.25
        trajectory["replay"]["trajectory_hash"] = trajectory_content_hash(trajectory)
        report = validate_trajectory(trajectory, self.registry)
        self.assertIn("TRJ-004", {issue.code for issue in report.issues})

    def test_observation_must_be_contained_in_request_interval(self) -> None:
        trajectory = positive_trajectory()
        trajectory["events"][1]["action"]["action"]["arguments"]["interval"] = {
            "start_s": 109.0,
            "end_s": 109.5,
        }
        trajectory["replay"]["trajectory_hash"] = trajectory_content_hash(trajectory)
        report = validate_trajectory(trajectory, self.registry)
        self.assertIn("TRJ-003", {issue.code for issue in report.issues})

    def test_standalone_action_rejects_reversed_interval(self) -> None:
        action = fixture("docs/spec/fixtures/positive_agent_action.json")
        action["action"] = {
            "tool": "read_transcript",
            "arguments": {
                "interval": {"start_s": 3.0, "end_s": 2.0},
                "source": "asr",
                "include_word_timestamps": False,
            },
        }
        report = validate_action(action, self.registry)
        self.assertIn("TIME-001", {issue.code for issue in report.issues})

    def test_direct_nonfinite_input_returns_report(self) -> None:
        trajectory = positive_trajectory()
        trajectory["completion"]["total_cost"] = float("nan")
        report = validate_trajectory(trajectory, self.registry)
        self.assertFalse(report.ok)
        self.assertIn("INPUT-001", {issue.code for issue in report.issues})

    def test_finalize_must_be_last(self) -> None:
        trajectory = positive_trajectory()
        trajectory["events"][1], trajectory["events"][2] = trajectory["events"][2], trajectory["events"][1]
        report = validate_trajectory(trajectory, self.registry)
        self.assertIn("TRJ-005", {issue.code for issue in report.issues})


if __name__ == "__main__":
    unittest.main()
