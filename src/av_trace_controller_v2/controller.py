"""Split-head controller-v2 invocation and v1 comparison adapter."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from av_trace_scale1b_agent.controller import (
    GenerationConfig as V1GenerationConfig,
)
from av_trace_scale1b_agent.controller import (
    LearnedCallFailure,
    run_controller_decision,
    run_grounded_generator,
)
from av_trace_scale1b_agent.process import ModelProcessError

from .parser import (
    ControllerOutputError,
    parse_action_output,
    parse_state_output,
)
from .prompts import ACTION_SYSTEM_PROMPT, STATE_SYSTEM_PROMPT
from .schemas import (
    action_grammar_schema,
    canonical_json_bytes,
    sha256_json,
    state_grammar_schema,
)

_PERSISTED_CALL_KEYS = {
    "attempt",
    "status",
    "request_hash",
    "system_prompt_sha256",
    "raw_sha256",
    "prompt_tokens",
    "generated_tokens",
    "latency_seconds",
    "peak_rss_kib",
    "peak_rss_bytes",
    "error_code",
    "error",
    "validation_error",
}


class ControllerModel(Protocol):
    def generate(
        self,
        *,
        system: str,
        payload: Mapping[str, Any],
        max_new_tokens: int,
        constraint_schema: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ControllerV2Config:
    action_max_new_tokens: int = 32
    state_max_new_tokens: int = 256
    finalizer_max_new_tokens: int = 512


Finalizer = Callable[
    [ControllerModel, str, list[dict[str, Any]], list[dict[str, Any]], int],
    dict[str, Any],
]


def _sha256_bytes(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _request_hash(
    system: str,
    payload: Mapping[str, Any],
    constraint_schema: Mapping[str, Any] | None,
) -> str:
    return _sha256_bytes(
        canonical_json_bytes(
            {
                "system": system,
                "payload": dict(payload),
                "constraint_schema": (
                    dict(constraint_schema)
                    if constraint_schema is not None
                    else None
                ),
            }
        )
    )


def _base_public_payload(case: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "policy": case["policy"],
        "question": case["question"],
        "public_claim_slots": case["public_claim_slots"],
        "known_pointers": case["known_pointers"],
        "citable_observations": case["citable_observations"],
        "recent_public_events": case["recent_public_events"],
        "no_progress_rounds": case["no_progress_rounds"],
        "remaining_budget": case["remaining_budget"],
        "action_menu": case["action_menu"],
    }


def _call_head(
    model: ControllerModel,
    *,
    phase: str,
    system: str,
    payload: Mapping[str, Any],
    constraint_schema: Mapping[str, Any],
    max_new_tokens: int,
    parser: Callable[[bytes], dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    request_hash = _request_hash(system, payload, constraint_schema)
    grammar_hash = sha256_json(constraint_schema)
    system_hash = _sha256_bytes(system.encode("utf-8"))
    try:
        response = model.generate(
            system=system,
            payload=payload,
            max_new_tokens=max_new_tokens,
            constraint_schema=constraint_schema,
        )
    except ModelProcessError as exc:
        status = (
            "constraint_runtime_failure"
            if exc.code == "CONSTRAINT_RUNTIME_FAILURE"
            else "process_error"
        )
        return None, {
            "phase": phase,
            "attempt": 0,
            "status": status,
            "error_code": exc.code,
            "request_hash": request_hash,
            "grammar_hash": grammar_hash,
            "system_prompt_sha256": system_hash,
            "raw_output_utf8": None,
            "raw_sha256": None,
            "prompt_tokens": None,
            "generated_tokens": None,
            "latency_seconds": None,
            "peak_rss_kib": None,
            "peak_rss_bytes": None,
            "constraint_engine": None,
        }

    raw_value = response.get("raw_text", "")
    if isinstance(raw_value, bytes):
        raw = raw_value
        display = raw.decode("utf-8", errors="replace")
    else:
        display = str(raw_value)
        raw = display.encode("utf-8")
    record = {
        "phase": phase,
        "attempt": 0,
        "status": "generated",
        "request_hash": request_hash,
        "grammar_hash": grammar_hash,
        "system_prompt_sha256": system_hash,
        "raw_output_utf8": display,
        "raw_sha256": _sha256_bytes(raw),
        "prompt_tokens": response.get("prompt_tokens"),
        "generated_tokens": response.get("generated_tokens"),
        "latency_seconds": response.get("latency_seconds"),
        "peak_rss_kib": response.get("peak_rss_kib"),
        "peak_rss_bytes": response.get("peak_rss_bytes"),
        "constraint_engine": response.get("constraint_engine", "xgrammar"),
    }
    try:
        parsed = parser(raw)
    except ControllerOutputError as exc:
        record["status"] = "invalid"
        record["error_code"] = exc.code
        return None, record
    record["status"] = "valid"
    return parsed, record


def _default_finalizer(
    model: ControllerModel,
    question: str,
    claim_slots: list[dict[str, Any]],
    observations: list[dict[str, Any]],
    max_new_tokens: int,
) -> dict[str, Any]:
    generated = run_grounded_generator(
        model,  # type: ignore[arg-type]
        question=question,
        claim_slots=claim_slots,
        observations=observations,
        condition="controller_v2_public_packet_finalization",
        config=V1GenerationConfig(
            max_new_tokens=max_new_tokens,
            repair_max_new_tokens=max_new_tokens,
        ),
    )
    return generated


def _sanitized_v1_call(phase: str, call: Mapping[str, Any]) -> dict[str, Any]:
    """Persist v1 provenance without ever persisting a request or prompt."""

    result = {
        "phase": phase,
        "grammar_hash": None,
        "constraint_engine": None,
        **{
            key: value
            for key, value in call.items()
            if key in _PERSISTED_CALL_KEYS
        },
    }
    result["raw_output_utf8"] = call.get("raw_text")
    return result


def execute_v2_case(
    model: ControllerModel,
    case: Mapping[str, Any],
    *,
    action_schema_path: Path,
    state_schema_path: Path,
    config: ControllerV2Config | None = None,
    finalizer: Finalizer | None = None,
) -> dict[str, Any]:
    """Execute one public case while preserving both model-authorship boundaries."""

    cfg = config or ControllerV2Config()
    allowed_indices = list(
        case["action_output_contract"]["allowed_action_indices"]
    )
    allowed_claims = list(
        case["state_output_contract"]["allowed_claim_handles"]
    )
    base = _base_public_payload(case)
    public_payload_hash = sha256_json(base)
    action_payload = {
        **base,
        "task": "choose_public_action_index",
        "output_contract": {
            "exact_keys": ["action_index"],
            "allowed_action_indices": allowed_indices,
        },
    }
    action_grammar = action_grammar_schema(
        action_schema_path,
        allowed_action_indices=allowed_indices,
    )
    action_result, action_call = _call_head(
        model,
        phase="action_head",
        system=ACTION_SYSTEM_PROMPT,
        payload=action_payload,
        constraint_schema=action_grammar,
        max_new_tokens=cfg.action_max_new_tokens,
        parser=lambda raw: parse_action_output(
            raw, allowed_action_indices=allowed_indices
        ),
    )
    selected_index = (
        action_result["action_index"] if action_result is not None else None
    )

    state_payload = {
        **base,
        "task": "estimate_public_evidence_state",
        "selected_action_index": selected_index,
        "output_contract": {
            "exact_keys": [
                "p_sufficient",
                "covered_claim_handles",
                "missing_modalities",
                "missing_hops",
                "missingness_cause",
                "recovery_intent",
            ],
            "allowed_claim_handles": allowed_claims,
            "canonical_missing_modalities": [
                "vision",
                "speech",
                "ambient",
            ],
            "canonical_missing_hops": [
                "entity_identity",
                "event_detection",
                "speech_content",
                "ambient_event",
                "temporal_order",
                "cross_modal_binding",
                "causal_link",
                "state_change",
                "comparison",
                "counting",
                "other",
            ],
        },
    }
    state_grammar = state_grammar_schema(
        state_schema_path,
        allowed_claim_handles=allowed_claims,
    )
    state_result, state_call = _call_head(
        model,
        phase="state_head",
        system=STATE_SYSTEM_PROMPT,
        payload=state_payload,
        constraint_schema=state_grammar,
        max_new_tokens=cfg.state_max_new_tokens,
        parser=lambda raw: parse_state_output(
            raw, allowed_claim_handles=allowed_claims
        ),
    )

    dispatched_action = (
        dict(case["action_menu"][selected_index])
        if selected_index is not None
        else None
    )
    model_calls = [action_call, state_call]
    final = None
    finalization_error = None
    if dispatched_action is not None and dispatched_action.get("type") == "finalize":
        run_finalizer = finalizer or _default_finalizer
        try:
            generated = run_finalizer(
                model,
                str(case["question"]),
                list(case["public_claim_slots"]),
                list(case["citable_observations"]),
                cfg.finalizer_max_new_tokens,
            )
            final = generated.get("final")
            for call in generated.get("model_calls", []):
                model_calls.append(
                    _sanitized_v1_call("grounded_finalization", call)
                )
        except LearnedCallFailure as exc:
            finalization_error = exc.code
            for call in exc.details.get("attempts", []):
                model_calls.append(
                    _sanitized_v1_call("grounded_finalization", call)
                )

    return {
        "case_id": case["case_id"],
        "arm": "v2",
        "public_payload_hash": public_payload_hash,
        "action_syntax_valid": action_result is not None,
        "state_syntax_valid": state_result is not None,
        "selected_action_index": selected_index,
        "dispatched_action": dispatched_action,
        "public_state": state_result,
        "finalizer_called": (
            dispatched_action is not None
            and dispatched_action.get("type") == "finalize"
        ),
        "final": final,
        "finalization_error": finalization_error,
        "model_calls": model_calls,
    }


def _available_tools(case: Mapping[str, Any]) -> list[str]:
    tools: set[str] = set()
    pointers = {
        str(pointer["pointer_id"]): pointer
        for pointer in case["known_pointers"]
    }
    for action in case["action_menu"]:
        kind = action.get("type")
        if kind == "search":
            tool = {
                "vision": "search_visual",
                "speech": "search_speech",
                "ambient": "search_ambient_audio",
            }.get(action.get("modality"))
            if tool:
                tools.add(tool)
        elif kind == "status":
            tools.add("get_channel_status")
        elif kind == "observe":
            pointer = pointers.get(str(action.get("pointer_id")), {})
            tools.add(
                "read_transcript"
                if pointer.get("modality") == "speech"
                else "inspect_clip"
            )
    return sorted(tools)


def execute_v1_case(
    model: ControllerModel,
    case: Mapping[str, Any],
    *,
    config: ControllerV2Config | None = None,
    finalizer: Finalizer | None = None,
) -> dict[str, Any]:
    """Run the frozen v1 monolithic controller without changing v1 semantics."""

    cfg = config or ControllerV2Config()
    public_payload_hash = sha256_json(_base_public_payload(case))
    calls: list[dict[str, Any]] = []
    try:
        generated = run_controller_decision(
            model,  # type: ignore[arg-type]
            policy=str(case["policy"]),
            turn=len(case["recent_public_events"]),
            question=str(case["question"]),
            claim_slots=list(case["public_claim_slots"]),
            available_tools=_available_tools(case),
            remaining_budget=dict(case["remaining_budget"]),
            known_pointers=list(case["known_pointers"]),
            citable_observations=list(case["citable_observations"]),
            recent_public_events=list(case["recent_public_events"]),
            action_menu=list(case["action_menu"]),
            no_progress_rounds=int(case["no_progress_rounds"]),
            config=V1GenerationConfig(
                max_new_tokens=cfg.state_max_new_tokens,
                repair_max_new_tokens=cfg.state_max_new_tokens,
            ),
        )
    except LearnedCallFailure as exc:
        calls.extend(
            _sanitized_v1_call("v1_monolithic", call)
            for call in exc.details.get("attempts", [])
        )
        return {
            "case_id": case["case_id"],
            "arm": "v1",
            "public_payload_hash": public_payload_hash,
            "action_syntax_valid": False,
            "state_syntax_valid": False,
            "selected_action_index": None,
            "dispatched_action": None,
            "public_state": None,
            "finalizer_called": False,
            "final": None,
            "finalization_error": exc.code,
            "model_calls": calls,
        }
    decision = generated["decision"]
    calls.extend(
        _sanitized_v1_call("v1_monolithic", call)
        for call in generated["model_calls"]
    )
    action = dict(decision["action"])
    final = None
    finalization_error = None
    if action.get("type") == "finalize":
        run_finalizer = finalizer or _default_finalizer
        try:
            finalized = run_finalizer(
                model,
                str(case["question"]),
                list(case["public_claim_slots"]),
                list(case["citable_observations"]),
                cfg.finalizer_max_new_tokens,
            )
            final = finalized.get("final")
            calls.extend(
                _sanitized_v1_call("grounded_finalization", call)
                for call in finalized.get("model_calls", [])
            )
        except LearnedCallFailure as exc:
            finalization_error = exc.code
            calls.extend(
                _sanitized_v1_call("grounded_finalization", call)
                for call in exc.details.get("attempts", [])
            )
    return {
        "case_id": case["case_id"],
        "arm": "v1",
        "public_payload_hash": public_payload_hash,
        "action_syntax_valid": True,
        "state_syntax_valid": True,
        "selected_action_index": decision["action_index"],
        "dispatched_action": action,
        "public_state": decision["public_state"],
        "finalizer_called": action.get("type") == "finalize",
        "final": final,
        "finalization_error": finalization_error,
        "model_calls": calls,
    }
