from __future__ import annotations

import hashlib
from typing import Any

import pytest

from av_trace_scale1b_agent.controller import (
    GenerationConfig,
    LearnedCallFailure,
    _generate_validated,
)
from av_trace_scale1b_agent.process import ModelProcessError
from av_trace_scale1b_agent.schema import PublicSchemaError


class SequenceModel:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    def generate(
        self,
        *,
        system: str,
        payload: dict[str, Any],
        max_new_tokens: int,
    ) -> dict[str, Any]:
        self.requests.append(
            {
                "system": system,
                "payload": dict(payload),
                "max_new_tokens": max_new_tokens,
            }
        )
        return self.responses.pop(0)


def _reject(_: Any) -> dict[str, Any]:
    raise PublicSchemaError("TEST_SCHEMA_REJECTION")


def test_malformed_after_repair_retains_both_raw_attempts() -> None:
    raw_initial = '{"bad":"initial"}'
    raw_repair = '{"bad":"repair"}'
    model = SequenceModel(
        [
            {
                "raw_text": raw_initial,
                "parsed": {"bad": "initial"},
                "prompt_tokens": 11,
                "generated_tokens": 4,
            },
            {
                "raw_text": raw_repair,
                "parsed": {"bad": "repair"},
                "prompt_tokens": 19,
                "generated_tokens": 5,
            },
        ]
    )

    with pytest.raises(LearnedCallFailure) as caught:
        _generate_validated(
            model,  # type: ignore[arg-type]
            system_prompt="initial-system",
            payload={"task": "test", "question": "q"},
            validator=_reject,
            config=GenerationConfig(),
        )

    failure = caught.value
    assert failure.code == "MALFORMED_AFTER_REPAIR"
    assert [item["raw_text"] for item in failure.attempts] == [
        raw_initial,
        raw_repair,
    ]
    assert [item["raw_sha256"] for item in failure.attempts] == [
        "sha256:" + hashlib.sha256(raw_initial.encode()).hexdigest(),
        "sha256:" + hashlib.sha256(raw_repair.encode()).hexdigest(),
    ]
    assert all(
        item["validation_error_type"] == "PublicSchemaError"
        for item in failure.attempts
    )
    assert failure.to_record()["details"]["attempts"] == list(failure.attempts)
    assert model.requests[1]["payload"]["invalid_response"] == raw_initial


class CrashAfterInitialModel(SequenceModel):
    def generate(
        self,
        *,
        system: str,
        payload: dict[str, Any],
        max_new_tokens: int,
    ) -> dict[str, Any]:
        if self.responses:
            return super().generate(
                system=system,
                payload=payload,
                max_new_tokens=max_new_tokens,
            )
        raise ModelProcessError(
            "PROCESS_CRASH",
            "worker exited",
            details={
                "stderr_text": "fatal worker marker",
                "returncode": 23,
                "session_id": "session-test",
            },
        )


def test_repair_process_crash_retains_initial_raw_and_typed_metadata() -> None:
    raw_initial = "not-valid"
    model = CrashAfterInitialModel(
        [{"raw_text": raw_initial, "parsed": {"bad": True}}]
    )

    with pytest.raises(LearnedCallFailure) as caught:
        _generate_validated(
            model,  # type: ignore[arg-type]
            system_prompt="initial-system",
            payload={"task": "test", "question": "q"},
            validator=_reject,
            config=GenerationConfig(),
        )

    failure = caught.value
    assert failure.code == "PROCESS_CRASH"
    assert len(failure.attempts) == 2
    assert failure.attempts[0]["raw_text"] == raw_initial
    process_attempt = failure.attempts[1]
    assert process_attempt["raw_text"] is None
    assert process_attempt["error_code"] == "PROCESS_CRASH"
    assert process_attempt["process_error"]["details"]["stderr_text"] == (
        "fatal worker marker"
    )
    assert failure.details["process_error"]["details"]["returncode"] == 23
