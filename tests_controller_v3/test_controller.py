from __future__ import annotations

import json
from typing import Any

from av_trace_controller_v3.controller import STATE_HEADS, execute_v3_case

from .fixtures import fictional_case


class FakeModel:
    def __init__(self, outputs: list[bytes]) -> None:
        self.outputs = list(outputs)
        self.requests: list[dict[str, Any]] = []

    def generate(self, **kwargs: Any) -> dict[str, Any]:
        self.requests.append(kwargs)
        return {
            "raw_text": self.outputs.pop(0),
            "prompt_tokens": 10,
            "generated_tokens": 5,
            "latency_seconds": 0.1,
            "peak_rss_kib": 10,
            "peak_rss_bytes": 10240,
            "constraint_engine": "xgrammar",
        }


def _outputs() -> list[bytes]:
    return [
        b'{"action_index":0}',
        b'{"choice_index":1}',
        b'{"choice_index":1}',
        b'{"choice_index":0}',
        b'{"choice_index":0}',
        b'{"choice_index":0}',
        b'{"choice_index":0}',
    ]


def test_six_heads_are_independent_and_receive_only_public_state() -> None:
    model = FakeModel(_outputs())

    def finalizer(*args: Any) -> dict[str, Any]:
        return {"final": {"verdict": "answer"}, "model_calls": []}

    result = execute_v3_case(
        model, fictional_case(), finalizer=finalizer
    )
    assert len(model.requests) == 7
    assert result["public_state"] == {
        "p_sufficient": 1.0,
        "covered_claim_handles": ["fixture.slot.mark"],
        "missing_modalities": [],
        "missing_hops": [],
        "missingness_cause": "not_missing",
        "recovery_intent": "finalize_answer",
    }
    forbidden = {
        "expect",
        "expected",
        "oracle_evidence",
        "oracle_support",
        "required_terms",
        "selected_action_index",
    }
    for request in model.requests[1:]:
        payload = request["payload"]
        assert forbidden.isdisjoint(payload)
        assert "public_state" not in payload
        assert "state_head_outputs" not in payload
        assert payload["field"] in STATE_HEADS


def test_invalid_state_head_is_not_filled_deterministically() -> None:
    outputs = _outputs()
    outputs[3] = b'{"choice_index":99}'
    result = execute_v3_case(
        FakeModel(outputs),
        fictional_case(),
        finalizer=lambda *_: {"final": {"verdict": "answer"}, "model_calls": []},
    )
    assert result["state_heads"]["missing_modalities"]["syntax_valid"] is False
    assert result["state_heads"]["missing_modalities"]["value"] is None
    assert result["public_state"] is None


def test_finalizer_does_not_receive_controller_state() -> None:
    captured: list[Any] = []

    def finalizer(*args: Any) -> dict[str, Any]:
        captured.append(args)
        return {"final": {"verdict": "answer"}, "model_calls": []}

    case = fictional_case()
    result = execute_v3_case(FakeModel(_outputs()), case, finalizer=finalizer)
    assert result["finalizer_called"] is True
    assert captured[0][1] == case["question"]
    assert captured[0][2] == case["public_claim_slots"]
    assert captured[0][3] == case["citable_observations"]
    assert "p_sufficient" not in json.dumps(captured[0], default=str)


def test_logs_exclude_prompts_and_payloads() -> None:
    result = execute_v3_case(
        FakeModel(_outputs()),
        fictional_case(),
        finalizer=lambda *_: {"final": {"verdict": "answer"}, "model_calls": []},
    )
    forbidden = {"system", "system_prompt", "payload", "request_payload"}
    for call in result["model_calls"]:
        assert forbidden.isdisjoint(call)
