from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from av_trace_scale1b_agent.checkpoint import read_checkpoint, write_checkpoint
from av_trace_scale1b_agent.controller import (
    LearnedCallFailure,
    run_grounded_generator,
    run_learned_agent,
)
from av_trace_scale1b_agent.core import (
    GAPilotError,
    _experiment_matrix,
    _inputs,
    build_ga_pilot,
)
from av_trace_scale1b_agent.gates import verify_prerequisite_gates
from av_trace_scale1b_agent.process import ModelProcessError, ProcessConfig, QwenProcess
from av_trace_scale1b_agent.schema import (
    PublicSchemaError,
    validate_controller_decision,
    validate_finalization,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_WORKER = ROOT / "tests_scale1b_agent/fixture_worker.py"


def _final() -> dict:
    return {
        "verdict": "answer",
        "answer_text": "A supported answer.",
        "asserted_claims": [
            {
                "claim_handle": "slot.c01",
                "text": "A supported answer.",
                "citations": ["obs.a"],
            }
        ],
        "claim_to_citations": {"slot.c01": ["obs.a"]},
        "missing_modalities": [],
        "missing_hops": [],
        "missingness_cause": "not_missing",
        "p_sufficient": 0.9,
        "recovery_intent": "",
        "stop_rationale": "Evidence is cited.",
    }


def test_gate_is_fail_closed_until_task109_exists():
    result = verify_prerequisite_gates(ROOT)
    if not (ROOT / "data/restricted/scale1b/manifests/ga_model_acquisition.json").exists():
        assert not result["ready"]
        assert "PREREQUISITE_ARTIFACTS_MISSING" in result["errors"]


def test_build_refuses_missing_gate():
    if verify_prerequisite_gates(ROOT)["ready"]:
        pytest.skip("parallel Task 109 became ready")
    with pytest.raises(GAPilotError, match="PREREQUISITE_GATES_NOT_READY"):
        build_ga_pilot(ROOT)


def test_finalization_accepts_only_public_handles():
    assert validate_finalization(
        _final(),
        claim_handles={"slot.c01"},
        observation_ids={"obs.a"},
    )["verdict"] == "answer"
    bad = _final()
    bad["asserted_claims"][0]["claim_handle"] = "claim.r004.visual"
    bad["claim_to_citations"] = {"claim.r004.visual": ["obs.a"]}
    with pytest.raises(PublicSchemaError):
        validate_finalization(
            bad,
            claim_handles={"slot.c01"},
            observation_ids={"obs.a"},
        )


def test_unknown_citation_fails_closed():
    bad = _final()
    bad["asserted_claims"][0]["citations"] = ["obs.unknown"]
    bad["claim_to_citations"]["slot.c01"] = ["obs.unknown"]
    with pytest.raises(PublicSchemaError, match="UNKNOWN_CITATION"):
        validate_finalization(
            bad,
            claim_handles={"slot.c01"},
            observation_ids={"obs.a"},
        )


def test_nonanswer_cannot_assert_claims():
    bad = _final()
    bad["verdict"] = "insufficient"
    with pytest.raises(PublicSchemaError, match="NONANSWER_WITH_ASSERTIONS"):
        validate_finalization(
            bad,
            claim_handles={"slot.c01"},
            observation_ids={"obs.a"},
        )


def test_controller_cannot_select_unknown_pointer():
    value = {
        "public_state": {
            "p_sufficient": 0.1,
            "covered_claim_handles": [],
            "missing_modalities": ["vision"],
            "missing_hops": ["event_detection"],
            "missingness_cause": "evidence_accessible_but_not_found",
            "recovery_intent": "Inspect a result.",
        },
        "action_index": 0,
    }
    with pytest.raises(PublicSchemaError, match="UNKNOWN_POINTER"):
        validate_controller_decision(
            value,
        claim_handles={"slot.c01"},
            pointer_ids={"ptr.a"},
            observation_ids=set(),
            available_tools={"search_visual", "inspect_clip", "finalize"},
            action_menu=[{"type": "observe", "pointer_id": "ptr.unknown"}],
        )


def test_process_boundary_drops_proxy_and_token_environment(tmp_path):
    with QwenProcess(
        tmp_path,
        config=ProcessConfig(startup_timeout_s=5, generation_timeout_s=5),
        command=[sys.executable, str(FIXTURE_WORKER), "environment"],
    ) as process:
        result = process.generate(system="x", payload={}, max_new_tokens=1)
    assert result["parsed"]["restricted_environment_present"] is False


def test_one_repair_attempt_succeeds(tmp_path):
    with QwenProcess(
        tmp_path,
        config=ProcessConfig(startup_timeout_s=5, generation_timeout_s=5),
        command=[sys.executable, str(FIXTURE_WORKER), "repair"],
    ) as process:
        result = run_grounded_generator(
            process,
            question="Question?",
            claim_slots=[{"claim_handle": "slot.c01", "description": "component"}],
            observations=[
                {
                    "observation_id": "obs.a",
                    "modality": "vision",
                    "interval": {"start_s": 0.0, "end_s": 1.0},
                    "content": "A supported answer.",
                }
            ],
            condition="test",
        )
    assert result["final"]["verdict"] == "answer"
    assert [row["status"] for row in result["model_calls"]] == ["invalid", "valid"]
    for row in result["model_calls"]:
        assert "system_prompt" not in row
        assert "request_payload" not in row
        assert row["system_prompt_sha256"].startswith("sha256:")


def test_one_repair_attempt_fails_closed(tmp_path):
    with QwenProcess(
        tmp_path,
        config=ProcessConfig(startup_timeout_s=5, generation_timeout_s=5),
        command=[sys.executable, str(FIXTURE_WORKER), "always_invalid"],
    ) as process, pytest.raises(
        LearnedCallFailure, match="MALFORMED_AFTER_REPAIR"
    ) as caught:
        run_grounded_generator(
            process,
            question="Question?",
            claim_slots=[
                {"claim_handle": "slot.c01", "description": "component"}
            ],
            observations=[],
            condition="test",
        )
    for row in caught.value.details["attempts"]:
        assert "system_prompt" not in row
        assert "request_payload" not in row
        assert row["system_prompt_sha256"].startswith("sha256:")


@pytest.mark.parametrize(
    ("mode", "code"),
    [("oom", "OOM"), ("crash", "PROCESS_CRASH"), ("timeout", "TIMEOUT")],
)
def test_model_process_failures_are_typed(tmp_path, mode, code):
    config = ProcessConfig(
        startup_timeout_s=5,
        generation_timeout_s=0.1 if mode == "timeout" else 5,
    )
    with QwenProcess(
        tmp_path,
        config=config,
        command=[sys.executable, str(FIXTURE_WORKER), mode],
    ) as process, pytest.raises(ModelProcessError) as caught:
        process.generate(system="x", payload={}, max_new_tokens=1)
    assert caught.value.code == code


def test_process_error_call_record_omits_full_prompt_and_payload(tmp_path):
    with QwenProcess(
        tmp_path,
        config=ProcessConfig(startup_timeout_s=5, generation_timeout_s=5),
        command=[sys.executable, str(FIXTURE_WORKER), "oom"],
    ) as process, pytest.raises(LearnedCallFailure, match="OOM") as caught:
        run_grounded_generator(
            process,
            question="Question?",
            claim_slots=[
                {"claim_handle": "slot.c01", "description": "component"}
            ],
            observations=[],
            condition="test",
        )
    [record] = caught.value.details["attempts"]
    assert record["status"] == "process_error"
    assert "system_prompt" not in record
    assert "request_payload" not in record
    assert record["system_prompt_sha256"].startswith("sha256:")


def test_checkpoint_rejects_semantic_tampering(tmp_path):
    path = tmp_path / "checkpoint.json"
    write_checkpoint(path, config_hash="sha256:x", record={"a": 1})
    assert read_checkpoint(path, config_hash="sha256:x") is not None
    document = json.loads(path.read_text())
    document["record"]["a"] = 2
    path.write_text(json.dumps(document))
    assert read_checkpoint(path, config_hash="sha256:x") is None


def test_matrix_has_matched_core_and_diagnostics():
    families, _ = _inputs(ROOT)
    matrix = _experiment_matrix(families)
    assert len(matrix) == 5 * (2 * 3 * 5 + 2 * 2 + 2) + 5
    assert {
        row["system"] for row in matrix
    } == {
        "deterministic_react_control",
        "deterministic_evidence_sufficiency_control",
        "single_shot_learned_generator",
        "learned_react",
        "learned_evidence_sufficiency",
        "learned_generator_diagnostic",
    }
    assert sum(row["condition"] == "no_trigger" for row in matrix) == 20


class _FakeBackend:
    def __init__(self):
        self.events = []
        self.observation_private = {}
        self.evidence_by_observation = {}
        self.start = {
            "question": "What is shown?",
            "claim_slots": [
                {
                    "claim_handle": "slot.c01",
                    "description": "slot",
                }
            ],
            "available_tools": [
                "search_visual",
                "search_speech",
                "search_ambient_audio",
                "inspect_clip",
                "read_transcript",
                "get_channel_status",
                "finalize",
            ],
            "budget": {"max_steps": 4, "cost_limit": 4.0},
            "tool_costs": {
                "search_visual": 1.0,
                "search_speech": 1.0,
                "search_ambient_audio": 1.0,
                "inspect_clip": 1.0,
                "read_transcript": 1.0,
                "get_channel_status": 0.25,
                "finalize": 0.0,
            },
        }
        self.steps = 0

    def public_start(self):
        return self.start

    def snapshot(self):
        return {
            "remaining_steps": self.start["budget"]["max_steps"] - self.steps,
            "remaining_cost": 4.0 - self.steps,
            "known_pointer_ids": [],
            "known_observation_ids": [],
            "triggered": False,
        }

    def search(self, modality, query, top_k):
        self.steps += 1
        return {
            "status": "ok",
            "results": [
                {
                    "pointer_id": "ptr.a",
                    "modality": "vision",
                    "interval": {"start_s": 0.0, "end_s": 1.0},
                    "preview": "candidate",
                }
            ],
        }

    def observe(self, pointer_id):
        self.steps += 1
        observation = {
            "observation_id": "obs.a",
            "modality": "vision",
            "interval": {"start_s": 0.0, "end_s": 1.0},
            "content": "A supported answer.",
        }
        self.observation_private["obs.a"] = observation
        return {"status": "ok", "observation": observation}

    def status(self, modalities):
        self.steps += 1
        return {"status": "ok", "channels": {}}

    def finalize(self, final):
        self.steps += 1
        return {"status": "finalized", "verdict": final["verdict"]}


def test_learned_controller_runs_only_model_authored_actions(tmp_path):
    with QwenProcess(
        tmp_path,
        config=ProcessConfig(startup_timeout_s=5, generation_timeout_s=5),
        command=[sys.executable, str(FIXTURE_WORKER), "agent"],
    ) as process:
        result = run_learned_agent(
            process, backend=_FakeBackend(), policy="evidence_sufficiency"
        )
    assert result["actual_learned_model"] is True
    assert result["final"]["verdict"] == "answer"
    assert [row["action"]["type"] for row in result["events"]] == [
        "search",
        "observe",
        "finalize",
    ]
