"""Native action head plus six independent public-state classification heads."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from av_trace_controller_v2.parser import (
    ControllerOutputError,
    parse_action_output,
)
from av_trace_scale1b_agent.controller import (
    GenerationConfig as FinalizerGenerationConfig,
)
from av_trace_scale1b_agent.controller import (
    LearnedCallFailure,
    run_grounded_generator,
)
from av_trace_scale1b_agent.process import ModelProcessError

from .parser import ControllerV3OutputError, parse_choice_output
from .prompts import ACTION_SYSTEM_PROMPT, STATE_SYSTEM_PROMPTS
from .schemas import (
    action_grammar_schema,
    canonical_json_bytes,
    choice_grammar_schema,
    sha256_json,
)

STATE_HEADS = (
    "p_sufficient",
    "covered_claim_handles",
    "missing_modalities",
    "missing_hops",
    "missingness_cause",
    "recovery_intent",
)
FORBIDDEN_PUBLIC_KEYS = {
    "expect",
    "expected",
    "oracle_evidence",
    "oracle_support",
    "required_terms",
    "private_label",
    "evaluator_label",
}
_PERSISTED_FINALIZER_CALL_KEYS = {
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
class ControllerV3Config:
    action_max_new_tokens: int = 16
    state_max_new_tokens: int = 16
    finalizer_max_new_tokens: int = 512


Finalizer = Callable[
    [ControllerModel, str, list[dict[str, Any]], list[dict[str, Any]], int],
    dict[str, Any],
]


def _sha256_bytes(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            str(key) in FORBIDDEN_PUBLIC_KEYS
            or _contains_forbidden_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def _base_public_payload(case: Mapping[str, Any]) -> dict[str, Any]:
    payload = {
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
    if _contains_forbidden_key(payload):
        raise ValueError("PRIVATE_LABEL_IN_PUBLIC_PAYLOAD")
    return payload


def _request_hash(
    system: str,
    payload: Mapping[str, Any],
    constraint_schema: Mapping[str, Any],
) -> str:
    return _sha256_bytes(
        canonical_json_bytes(
            {
                "system": system,
                "payload": dict(payload),
                "constraint_schema": dict(constraint_schema),
            }
        )
    )


def _call(
    model: ControllerModel,
    *,
    phase: str,
    system: str,
    payload: Mapping[str, Any],
    grammar: Mapping[str, Any],
    max_new_tokens: int,
    parser: Callable[[bytes], dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    request_hash = _request_hash(system, payload, grammar)
    record: dict[str, Any] = {
        "phase": phase,
        "attempt": 0,
        "request_hash": request_hash,
        "grammar_hash": sha256_json(grammar),
        "system_prompt_sha256": _sha256_bytes(system.encode("utf-8")),
    }
    try:
        response = model.generate(
            system=system,
            payload=payload,
            max_new_tokens=max_new_tokens,
            constraint_schema=grammar,
        )
    except ModelProcessError as exc:
        record.update(
            {
                "status": (
                    "constraint_runtime_failure"
                    if exc.code == "CONSTRAINT_RUNTIME_FAILURE"
                    else "process_error"
                ),
                "error_code": exc.code,
                "raw_output_utf8": None,
                "raw_sha256": None,
                "prompt_tokens": None,
                "generated_tokens": None,
                "latency_seconds": None,
                "peak_rss_kib": None,
                "peak_rss_bytes": None,
                "constraint_engine": None,
            }
        )
        return None, record
    raw_value = response.get("raw_text", "")
    if isinstance(raw_value, bytes):
        raw = raw_value
        display = raw.decode("utf-8", errors="replace")
    else:
        display = str(raw_value)
        raw = display.encode("utf-8")
    record.update(
        {
            "status": "generated",
            "raw_output_utf8": display,
            "raw_sha256": _sha256_bytes(raw),
            "prompt_tokens": response.get("prompt_tokens"),
            "generated_tokens": response.get("generated_tokens"),
            "latency_seconds": response.get("latency_seconds"),
            "peak_rss_kib": response.get("peak_rss_kib"),
            "peak_rss_bytes": response.get("peak_rss_bytes"),
            "constraint_engine": response.get("constraint_engine", "xgrammar"),
        }
    )
    try:
        parsed = parser(raw)
    except (ControllerOutputError, ControllerV3OutputError) as exc:
        record.update({"status": "invalid", "error_code": exc.code})
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
    """Call the existing model-authored finalizer with unchanged semantics."""

    return run_grounded_generator(
        model,  # type: ignore[arg-type]
        question=question,
        claim_slots=claim_slots,
        observations=observations,
        condition="controller_v3_development_finalization",
        config=FinalizerGenerationConfig(
            max_new_tokens=max_new_tokens,
            repair_max_new_tokens=max_new_tokens,
        ),
    )


def _sanitize_finalizer_call(call: Mapping[str, Any]) -> dict[str, Any]:
    result = {
        "phase": "grounded_finalization",
        "grammar_hash": None,
        "constraint_engine": None,
        **{
            key: value
            for key, value in call.items()
            if key in _PERSISTED_FINALIZER_CALL_KEYS
        },
    }
    result["raw_output_utf8"] = call.get("raw_text")
    return result


def execute_v3_case(
    model: ControllerModel,
    case: Mapping[str, Any],
    *,
    config: ControllerV3Config | None = None,
    finalizer: Finalizer | None = None,
) -> dict[str, Any]:
    """Execute action and six independent heads against one public state."""

    cfg = config or ControllerV3Config()
    base = _base_public_payload(case)
    public_payload_hash = sha256_json(base)
    allowed_actions = list(range(len(case["action_menu"])))
    action_payload = {
        **base,
        "task": "choose_public_action_index",
        "output_contract": {
            "exact_keys": ["action_index"],
            "allowed_action_indices": allowed_actions,
        },
    }
    action_grammar = action_grammar_schema(
        allowed_action_indices=allowed_actions
    )
    action_result, action_call = _call(
        model,
        phase="action_head",
        system=ACTION_SYSTEM_PROMPT,
        payload=action_payload,
        grammar=action_grammar,
        max_new_tokens=cfg.action_max_new_tokens,
        parser=lambda raw: parse_action_output(
            raw, allowed_action_indices=allowed_actions
        ),
    )
    selected_action_index = (
        action_result["action_index"] if action_result is not None else None
    )

    public_state: dict[str, Any] = {}
    head_outputs: dict[str, Any] = {}
    model_calls = [action_call]
    for head in STATE_HEADS:
        choices = list(case["state_choice_enums"][head])
        allowed_choices = list(range(len(choices)))
        payload = {
            **base,
            "task": "classify_one_public_state_field",
            "field": head,
            "choices": [
                {"choice_index": index, "value": value}
                for index, value in enumerate(choices)
            ],
            "output_contract": {
                "exact_keys": ["choice_index"],
                "allowed_choice_indices": allowed_choices,
            },
        }
        grammar = choice_grammar_schema(
            allowed_choice_indices=allowed_choices
        )
        parsed, call = _call(
            model,
            phase=f"state_head.{head}",
            system=STATE_SYSTEM_PROMPTS[head],
            payload=payload,
            grammar=grammar,
            max_new_tokens=cfg.state_max_new_tokens,
            parser=lambda raw, allowed=allowed_choices: parse_choice_output(
                raw, allowed_choice_indices=allowed
            ),
        )
        model_calls.append(call)
        selected_choice_index = (
            parsed["choice_index"] if parsed is not None else None
        )
        selected_value = (
            choices[selected_choice_index]
            if selected_choice_index is not None
            else None
        )
        head_outputs[head] = {
            "syntax_valid": parsed is not None,
            "choice_index": selected_choice_index,
            "value": selected_value,
        }
        if parsed is not None:
            public_state[head] = selected_value

    dispatched_action = (
        dict(case["action_menu"][selected_action_index])
        if selected_action_index is not None
        else None
    )
    final = None
    finalization_error = None
    finalizer_called = bool(
        dispatched_action is not None
        and dispatched_action.get("type") == "finalize"
    )
    if finalizer_called:
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
            model_calls.extend(
                _sanitize_finalizer_call(call)
                for call in generated.get("model_calls", [])
            )
        except LearnedCallFailure as exc:
            finalization_error = exc.code
            model_calls.extend(
                _sanitize_finalizer_call(call)
                for call in exc.details.get("attempts", [])
            )

    return {
        "case_id": case["case_id"],
        "public_payload_hash": public_payload_hash,
        "action_syntax_valid": action_result is not None,
        "selected_action_index": selected_action_index,
        "dispatched_action": dispatched_action,
        "state_heads": head_outputs,
        "public_state": (
            public_state if len(public_state) == len(STATE_HEADS) else None
        ),
        "finalizer_called": finalizer_called,
        "final": final,
        "finalization_error": finalization_error,
        "model_calls": model_calls,
    }
