from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from av_trace_controller_v2.controller import execute_v2_case
from av_trace_scale1b_agent.process import ModelProcessError

from .fixtures import VALID_STATE, fictional_case

ROOT = Path(__file__).resolve().parents[1]
ACTION_SCHEMA = ROOT / "docs/spec/controller_v2_action_schema.json"
STATE_SCHEMA = ROOT / "docs/spec/controller_v2_state_schema.json"


class FakeModel:
    def __init__(self, outputs: list[bytes | Exception]) -> None:
        self.outputs = list(outputs)
        self.requests: list[dict[str, Any]] = []

    def generate(self, **kwargs: Any) -> dict[str, Any]:
        self.requests.append(kwargs)
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return {
            "raw_text": output,
            "prompt_tokens": 31,
            "generated_tokens": 8,
            "latency_seconds": 0.25,
            "peak_rss_kib": 100,
            "peak_rss_bytes": 102400,
            "constraint_engine": "xgrammar",
        }


def _execute(model: FakeModel, case=None, finalizer=None):
    return execute_v2_case(
        model,
        case or fictional_case(),
        action_schema_path=ACTION_SCHEMA,
        state_schema_path=STATE_SCHEMA,
        finalizer=finalizer,
    )


def test_constraint_runtime_failure_is_not_converted_to_choice() -> None:
    model = FakeModel(
        [
            ModelProcessError(
                "CONSTRAINT_RUNTIME_FAILURE", "fictional compiler failure"
            ),
            VALID_STATE,
        ]
    )
    result = _execute(model)
    assert result["selected_action_index"] is None
    assert result["dispatched_action"] is None
    assert result["state_syntax_valid"] is True
    assert result["model_calls"][0]["error_code"] == (
        "CONSTRAINT_RUNTIME_FAILURE"
    )
    assert model.requests[1]["payload"]["selected_action_index"] is None


def test_invalid_action_still_invokes_state_and_never_dispatches() -> None:
    model = FakeModel([b'{"action_index":99}', VALID_STATE])
    result = _execute(model)
    assert len(model.requests) == 2
    assert result["action_syntax_valid"] is False
    assert result["dispatched_action"] is None
    assert result["finalizer_called"] is False


def test_finalizer_only_runs_after_model_authored_finalize() -> None:
    calls: list[tuple[Any, ...]] = []

    def finalizer(*args):
        calls.append(args)
        return {"final": {"verdict": "fictional"}, "model_calls": []}

    case = fictional_case(finalize_index=1)
    result = _execute(
        FakeModel([b'{"action_index":1}', VALID_STATE]),
        case,
        finalizer,
    )
    assert result["dispatched_action"] == {"type": "finalize"}
    assert result["finalizer_called"] is True
    assert result["final"] == {"verdict": "fictional"}
    assert len(calls) == 1
    assert calls[0][1] == case["question"]
    assert calls[0][2] == case["public_claim_slots"]
    assert calls[0][3] == case["citable_observations"]
    assert VALID_STATE.decode() not in json.dumps(calls[0], default=str)


def test_controller_state_is_never_mapped_into_an_answer() -> None:
    result = _execute(
        FakeModel([b'{"action_index":0}', VALID_STATE]),
        fictional_case(),
    )
    assert result["finalizer_called"] is False
    assert result["final"] is None
    assert result["dispatched_action"]["type"] == "search"


def test_model_call_records_do_not_persist_prompts_or_payloads() -> None:
    result = _execute(FakeModel([b'{"action_index":0}', VALID_STATE]))
    forbidden = {"system", "system_prompt", "payload", "request_payload"}
    for call in result["model_calls"]:
        assert forbidden.isdisjoint(call)
        assert call["raw_output_utf8"]


def test_dynamic_grammars_are_supplied_to_both_heads() -> None:
    model = FakeModel([b'{"action_index":0}', VALID_STATE])
    _execute(model)
    action_schema = model.requests[0]["constraint_schema"]
    state_schema = model.requests[1]["constraint_schema"]
    assert action_schema["properties"]["action_index"]["enum"] == [0, 1, 2]
    covered_enum = state_schema["properties"]["covered_claim_handles"]["enum"]
    assert [] in covered_enum
    assert ["v2slot.fictional_mark"] in covered_enum
    assert [
        "v2slot.fictional_mark",
        "v2slot.fictional_color",
    ] in covered_enum
    assert [
        "v2slot.fictional_color",
        "v2slot.fictional_mark",
    ] not in covered_enum
    result = _execute(FakeModel([b'{"action_index":0}', VALID_STATE]))
    assert result["public_payload_hash"].startswith("sha256:")
