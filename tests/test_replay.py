from __future__ import annotations

import unittest

from av_trace.replay import ReplayProtocolError, SyntheticReplayBackend
from av_trace.schemas import SchemaRegistry

from tests.helpers import ROOT, action, channel_outage_family, positive_family, records


class ReplayBackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = SchemaRegistry(ROOT)

    def test_deterministic_replay_equality(self) -> None:
        family = positive_family()
        first = SyntheticReplayBackend(family, "CLEAN", records(), self.registry)
        second = SyntheticReplayBackend(family, "CLEAN", records(), self.registry)
        actions = [
            action(
                "syn_family.clean",
                0,
                "search_speech",
                {
                    "query": "pressure",
                    "top_k": 5,
                    "time_range": {"start_s": 0.0, "end_s": 1200.0},
                    "exclude_result_ids": [],
                    "speaker_hint": None,
                },
            ),
            action(
                "syn_family.clean",
                1,
                "read_transcript",
                {
                    "interval": {"start_s": 100.0, "end_s": 110.0},
                    "source": "asr",
                    "include_word_timestamps": False,
                },
            ),
        ]
        first_responses = [first.execute(item) for item in actions]
        second_responses = [second.execute(item) for item in actions]
        self.assertEqual(first_responses, second_responses)
        self.assertEqual(first.state_hash, second.state_hash)
        for response in first_responses:
            self.assertTrue(self.registry.validate("tool-response", response).ok)

    def test_necessity_group_is_unavailable_until_restoration(self) -> None:
        backend = SyntheticReplayBackend(positive_family(), "RESTORED", records(), self.registry)
        before = backend.execute(
            action(
                "syn_family.restored",
                0,
                "read_transcript",
                {
                    "interval": {"start_s": 100.0, "end_s": 110.0},
                    "source": "asr",
                    "include_word_timestamps": False,
                },
            )
        )
        self.assertEqual(before["status"], "not_found")
        status = backend.execute(
            action("syn_family.restored", 1, "get_channel_status", {"channels": ["speech"]})
        )
        self.assertEqual(status["status"], "ok")
        self.assertEqual(backend.last_active_hook_ids, ("restore1",))
        after = backend.execute(
            action(
                "syn_family.restored",
                2,
                "read_transcript",
                {
                    "interval": {"start_s": 100.0, "end_s": 110.0},
                    "source": "asr",
                    "include_word_timestamps": False,
                },
            )
        )
        self.assertEqual(after["status"], "ok")
        self.assertEqual(after["results"][0]["observation_id"], "obs.e1")

    def test_channel_outage_returns_typed_error_and_restores(self) -> None:
        family = channel_outage_family()
        backend = SyntheticReplayBackend(family, "RESTORED", records(), self.registry)
        unavailable = backend.execute(
            action(
                "syn_family.restored",
                0,
                "search_speech",
                {
                    "query": "pressure",
                    "top_k": 5,
                    "time_range": {"start_s": 0.0, "end_s": 1200.0},
                    "exclude_result_ids": [],
                    "speaker_hint": None,
                },
            )
        )
        self.assertEqual(unavailable["status"], "channel_unavailable")
        self.assertEqual(unavailable["error"]["code"], "SPEECH_CHANNEL_UNAVAILABLE")
        restored = backend.execute(
            action("syn_family.restored", 1, "get_channel_status", {"channels": ["speech"]})
        )
        self.assertEqual(restored["results"][0]["channels"]["speech"]["status"], "available")
        found = backend.execute(
            action(
                "syn_family.restored",
                2,
                "search_speech",
                {
                    "query": "pressure",
                    "top_k": 5,
                    "time_range": {"start_s": 0.0, "end_s": 1200.0},
                    "exclude_result_ids": [],
                    "speaker_hint": None,
                },
            )
        )
        self.assertEqual(found["status"], "ok")

    def test_non_contiguous_action_is_rejected(self) -> None:
        backend = SyntheticReplayBackend(positive_family(), "CLEAN", records(), self.registry)
        with self.assertRaisesRegex(ReplayProtocolError, "REPLAY-STEP-MISMATCH"):
            backend.execute(action("syn_family.clean", 2, "get_channel_status", {"channels": ["speech"]}))

    def test_search_exclusion_uses_returned_result_id(self) -> None:
        backend = SyntheticReplayBackend(positive_family(), "CLEAN", records(), self.registry)
        response = backend.execute(
            action(
                "syn_family.clean",
                0,
                "search_speech",
                {
                    "query": "pressure",
                    "top_k": 5,
                    "time_range": {"start_s": 0.0, "end_s": 1200.0},
                    "exclude_result_ids": ["ptr.e1"],
                    "speaker_hint": None,
                },
            )
        )
        self.assertEqual(response["status"], "not_found")

    def test_partial_overlap_does_not_leak_whole_observation(self) -> None:
        backend = SyntheticReplayBackend(positive_family(), "CLEAN", records(), self.registry)
        response = backend.execute(
            action(
                "syn_family.clean",
                0,
                "read_transcript",
                {
                    "interval": {"start_s": 105.0, "end_s": 106.0},
                    "source": "asr",
                    "include_word_timestamps": False,
                },
            )
        )
        self.assertEqual(response["status"], "not_found")
        self.assertEqual(response["results"], [])

    def test_duplicate_request_id_is_rejected(self) -> None:
        backend = SyntheticReplayBackend(positive_family(), "CLEAN", records(), self.registry)
        backend.execute(action("syn_family.clean", 0, "get_channel_status", {"channels": ["speech"]}, request_id="same"))
        with self.assertRaisesRegex(ReplayProtocolError, "REPLAY-REQUEST-DUPLICATE"):
            backend.execute(action("syn_family.clean", 1, "get_channel_status", {"channels": ["speech"]}, request_id="same"))

    def test_max_steps_is_enforced(self) -> None:
        family = positive_family()
        for episode in family["episodes"]:
            episode["budget"]["max_steps"] = 1
        backend = SyntheticReplayBackend(family, "CLEAN", records(), self.registry)
        backend.execute(action("syn_family.clean", 0, "get_channel_status", {"channels": ["speech"]}))
        with self.assertRaisesRegex(ReplayProtocolError, "REPLAY-MAX-STEPS"):
            backend.execute(action("syn_family.clean", 1, "finalize", {
                "p_sufficient": 0.2,
                "verdict": "insufficient",
                "answer_mode": "abstain",
                "claims": [],
                "diagnosis": {
                    "modality_probabilities": {"vision": 0.1, "speech": 0.8, "ambient": 0.1},
                    "hop_types": ["speech_content"],
                    "cause_probabilities": {
                        "source_evidence_absent": 0.05,
                        "evidence_in_source_but_inaccessible": 0.75,
                        "evidence_accessible_but_not_found": 0.1,
                        "not_missing": 0.05,
                        "uncertain": 0.05,
                    },
                    "recovery_route_declared": False,
                    "description": "Synthetic.",
                },
                "natural_language_answer": "",
                "termination_reason": "no_recovery_route",
            }))

    def test_state_hash_binds_record_content(self) -> None:
        original = records()
        changed = records()
        changed["e1"]["payload"] = {"text": "A speaker states that pressure dropped."}
        first = SyntheticReplayBackend(positive_family(), "CLEAN", original, self.registry)
        second = SyntheticReplayBackend(positive_family(), "CLEAN", changed, self.registry)
        self.assertNotEqual(first.state_hash, second.state_hash)

    def test_subtitle_request_does_not_return_asr_record(self) -> None:
        backend = SyntheticReplayBackend(positive_family(), "CLEAN", records(), self.registry)
        response = backend.execute(
            action(
                "syn_family.clean",
                0,
                "read_transcript",
                {
                    "interval": {"start_s": 100.0, "end_s": 110.0},
                    "source": "subtitle",
                    "include_word_timestamps": False,
                },
            )
        )
        self.assertEqual(response["status"], "not_found")

    def test_semantically_invalid_family_is_rejected(self) -> None:
        family = positive_family()
        family["episodes"][1]["replay"]["seed"] = 999
        with self.assertRaisesRegex(ReplayProtocolError, "REPLAY-INVALID-FAMILY"):
            SyntheticReplayBackend(family, "CLEAN", records(), self.registry)

    def test_action_after_finalize_is_rejected(self) -> None:
        family = positive_family()
        backend = SyntheticReplayBackend(family, "CLEAN", records(), self.registry)
        final = {
            "p_sufficient": 0.2,
            "verdict": "insufficient",
            "answer_mode": "abstain",
            "claims": [],
            "diagnosis": {
                "modality_probabilities": {"vision": 0.1, "speech": 0.8, "ambient": 0.1},
                "hop_types": ["speech_content"],
                "cause_probabilities": {
                    "source_evidence_absent": 0.05,
                    "evidence_in_source_but_inaccessible": 0.75,
                    "evidence_accessible_but_not_found": 0.1,
                    "not_missing": 0.05,
                    "uncertain": 0.05,
                },
                "recovery_route_declared": False,
                "description": "Synthetic.",
            },
            "natural_language_answer": "",
            "termination_reason": "no_recovery_route",
        }
        backend.execute(action("syn_family.clean", 0, "finalize", final))
        with self.assertRaisesRegex(ReplayProtocolError, "REPLAY-AFTER-FINALIZE"):
            backend.execute(action("syn_family.clean", 1, "get_channel_status", {"channels": ["speech"]}))


if __name__ == "__main__":
    unittest.main()
