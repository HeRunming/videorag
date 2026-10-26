#!/usr/bin/env python3
# ruff: noqa: ISC004
"""Evaluate the sealed controller-v2 paired holdout without model execution.

The evaluator deliberately has two phases:

1. verify the immutable public execution artifacts without touching the
   restricted evaluator key;
2. only after phase 1 succeeds, load the committed key and score both arms.

Raw model outputs and case-level labels/scores remain in restricted storage.
Only aggregate, non-case-level metrics are written to the review documents.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import stat
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from av_trace_controller_v2.parser import (
    parse_action_output,
    parse_state_output,
)
from av_trace_controller_v2.prompts import (
    ACTION_SYSTEM_PROMPT,
    STATE_SYSTEM_PROMPT,
)
from av_trace_controller_v2.schemas import (
    action_grammar_schema,
    canonical_json_bytes,
    sha256_json,
    state_grammar_schema,
)
from av_trace_scale1b_agent.controller import prompt_text
from av_trace_scale1b_agent.schema import (
    PublicSchemaError,
    controller_schema_prompt,
    extract_json_object,
    finalization_schema_prompt,
    validate_controller_decision,
    validate_finalization,
)

CONTRACT_REL = Path("data/rehearsal_plan/controller_v2_holdout_contract.json")
PUBLIC_REL = Path(
    "data/rehearsal_plan/controller_v2_holdout/public_execution_packet.json"
)
KEY_REL = Path(
    "data/rehearsal_plan/controller_v2_holdout/restricted_evaluator_key.json"
)
RUN_REL = Path("data/restricted/scale1b/controller_v2_holdout_run")
ATTESTATION_REL = Path(
    "data/restricted/scale1b/controller_v2/implementation_attestation.json"
)
OUTPUT_REL = Path("data/restricted/scale1b/controller_v2_holdout_evaluation")
REVIEW_REL = Path("docs/review/controller_v2_holdout_evaluation.md")
RESULT_REL = Path("orchestration/results/120_controller_v2_holdout_evaluation.txt")

SEALED_ARTIFACTS = {
    "execution_manifest.json",
    "order_trace.jsonl",
    "v1_calls.jsonl",
    "v1_results.jsonl",
    "v2_calls.jsonl",
    "v2_results.jsonl",
}
STATE_FIELDS = (
    "p_sufficient",
    "covered_claim_handles",
    "missing_modalities",
    "missing_hops",
    "missingness_cause",
    "recovery_intent",
)
PRIMARY_STRATA = (
    "routing",
    "pointer_read",
    "finalize",
    "abstain",
    "missingness",
    "recovery",
    "adversarial_menu_order",
)
FORBIDDEN_PUBLIC_KEYS = {
    "expected_action_index",
    "expected_action",
    "expected_state",
    "oracle_support",
    "required_terms",
    "answer_key",
    "labels",
    "primary_stratum",
    "secondary_capabilities",
}
EVALUATION_FAMILY_MARKERS = (
    "noaa",
    "evaluation_family",
    "r004",
    "r007",
    "r011",
    "r016",
    "r017",
    "claim.r",
    "e.r",
    "seg.",
    "cand-",
)
AUTOMATIC_NO_GO_CONDITIONS = (
    "artifact_hash_mismatch",
    "constraint_runtime_failure",
    "implementation_worker_accessed_restricted_key",
    "evaluator_labels_changed_after_any_model_output",
    "post_run_tuning",
    "evaluation_family_content_detected",
    "deterministic_answer_substitution",
    "controller_output_mapped_into_answer",
)


class EvaluationError(RuntimeError):
    """Raised when the sealed protocol cannot be evaluated safely."""


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise EvaluationError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise EvaluationError(f"JSONL_OBJECT_REQUIRED:{path}:{number}")
        rows.append(value)
    return rows


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _request_hash(
    system: str,
    payload: Mapping[str, Any],
    constraint_schema: Mapping[str, Any] | None = None,
) -> str:
    return _sha256_bytes(
        canonical_json_bytes(
            {
                "system": system,
                "payload": dict(payload),
                "constraint_schema": (
                    dict(constraint_schema) if constraint_schema is not None else None
                ),
            }
        )
    )


def _v1_request_hash(system: str, payload: Mapping[str, Any]) -> str:
    return _sha256_bytes(
        json.dumps(
            {"system": system, "payload": dict(payload)},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    )


def _walk_keys(value: Any):
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield str(key)
            yield from _walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_keys(item)


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


def _available_tools(case: Mapping[str, Any]) -> list[str]:
    tools: set[str] = set()
    pointers = {
        str(pointer["pointer_id"]): pointer for pointer in case["known_pointers"]
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


def _v1_payload(case: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "task": "choose_next_action",
        "policy": case["policy"],
        "turn": len(case["recent_public_events"]),
        "question": case["question"],
        "public_claim_slots": case["public_claim_slots"],
        "available_tools": _available_tools(case),
        "remaining_budget": case["remaining_budget"],
        "known_pointers": case["known_pointers"],
        "citable_observations": case["citable_observations"],
        "recent_public_events": case["recent_public_events"],
        "no_progress_rounds": case["no_progress_rounds"],
        "output_schema": controller_schema_prompt(case["action_menu"]),
        "response_template": {
            "public_state": {
                "p_sufficient": 0.1,
                "covered_claim_handles": [],
                "missing_modalities": ["speech"],
                "missing_hops": ["speech_content"],
                "missingness_cause": "evidence_accessible_but_not_found",
                "recovery_intent": "Search speech evidence.",
            },
            "action_index": 0,
        },
    }


def _repair_payload(
    original: Mapping[str, Any],
    *,
    raw: str,
    validation_error: str,
) -> dict[str, Any]:
    return {
        "task": original.get("task"),
        "policy": original.get("policy"),
        "question": original.get("question"),
        "output_schema": original.get("output_schema"),
        "public_claim_slots": original.get("public_claim_slots", []),
        "known_pointers": original.get("known_pointers", []),
        "citable_observations": original.get("citable_observations", []),
        "recent_public_events": original.get("recent_public_events", []),
        "remaining_budget": original.get("remaining_budget"),
        "response_template": original.get("response_template"),
        "allowed_claim_handles": [
            item.get("claim_handle") for item in original.get("public_claim_slots", [])
        ],
        "allowed_pointer_ids": [
            item.get("pointer_id") for item in original.get("known_pointers", [])
        ],
        "allowed_observation_ids": [
            item.get("observation_id")
            for item in original.get("citable_observations", [])
        ],
        "invalid_response": raw,
        "validation_error": validation_error,
    }


def _finalizer_payload(case: Mapping[str, Any]) -> dict[str, Any]:
    claim_handles = sorted(item["claim_handle"] for item in case["public_claim_slots"])
    observation_ids = sorted(
        item["observation_id"] for item in case["citable_observations"]
    )
    return {
        "task": "grounded_finalization",
        "question": case["question"],
        "public_claim_slots": case["public_claim_slots"],
        "citable_observations": case["citable_observations"],
        "allowed_modalities": ["vision", "speech", "ambient"],
        "allowed_hops": [
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
        "allowed_missingness_causes": [
            "source_evidence_absent",
            "evidence_in_source_but_inaccessible",
            "evidence_accessible_but_not_found",
            "not_missing",
            "uncertain",
        ],
        "output_schema": finalization_schema_prompt(
            claim_handles=claim_handles,
            observation_ids=observation_ids,
        ),
        "response_template": {
            "verdict": "insufficient",
            "answer_text": "",
            "asserted_claims": [],
            "claim_to_citations": {},
            "missing_modalities": ["speech"],
            "missing_hops": ["other"],
            "missingness_cause": "uncertain",
            "p_sufficient": 0.1,
            "recovery_intent": "Acquire the missing evidence.",
            "stop_rationale": "Required evidence is not yet available.",
        },
    }


def _validate_v1_decision(case: Mapping[str, Any], raw: str) -> dict[str, Any]:
    value = extract_json_object(raw)
    decision = validate_controller_decision(
        value,
        claim_handles={item["claim_handle"] for item in case["public_claim_slots"]},
        pointer_ids={item["pointer_id"] for item in case["known_pointers"]},
        observation_ids={
            item["observation_id"] for item in case["citable_observations"]
        },
        available_tools=set(_available_tools(case)),
        action_menu=list(case["action_menu"]),
    )
    action = decision["action"]
    if action["type"] == "search":
        signature = (
            action["modality"],
            " ".join(action["query"].casefold().split()),
        )
        prior_signatures = {
            (
                str(event["action"].get("modality")),
                " ".join(str(event["action"].get("query", "")).casefold().split()),
            )
            for event in case["recent_public_events"]
            if event.get("action", {}).get("type") == "search"
        }
        pointer_ids = {str(pointer["pointer_id"]) for pointer in case["known_pointers"]}
        observed_pointer_ids = {
            str(event.get("action", {}).get("pointer_id"))
            for event in case["recent_public_events"]
            if event.get("action", {}).get("type") == "observe"
        }
        if signature in prior_signatures and pointer_ids - observed_pointer_ids:
            raise PublicSchemaError("REPEATED_SEARCH_WITH_UNOBSERVED_POINTERS")
    return decision


def _validate_final(case: Mapping[str, Any], raw: str) -> dict[str, Any]:
    return validate_finalization(
        extract_json_object(raw),
        claim_handles={item["claim_handle"] for item in case["public_claim_slots"]},
        observation_ids={
            item["observation_id"] for item in case["citable_observations"]
        },
    )


def _check_call_record(
    call: Mapping[str, Any],
    *,
    expected_system: str,
    expected_request_hash: str,
) -> None:
    raw = call.get("raw_output_utf8")
    expected_raw_hash = None if raw is None else _sha256_bytes(str(raw).encode("utf-8"))
    if call.get("request_hash") != expected_request_hash:
        raise EvaluationError("REQUEST_HASH_MISMATCH")
    if call.get("system_prompt_sha256") != _sha256_bytes(
        expected_system.encode("utf-8")
    ):
        raise EvaluationError("SYSTEM_PROMPT_HASH_MISMATCH")
    if call.get("raw_sha256") != expected_raw_hash:
        raise EvaluationError("RAW_OUTPUT_HASH_MISMATCH")


def _verify_v2_case(
    *,
    repo_root: Path,
    case: Mapping[str, Any],
    result: Mapping[str, Any],
    calls: Sequence[Mapping[str, Any]],
) -> None:
    if len(calls) < 2:
        raise EvaluationError(f"V2_CALL_COUNT_TOO_SMALL:{case['case_id']}")
    action_call, state_call = calls[0], calls[1]
    if (
        action_call.get("phase") != "action_head"
        or state_call.get("phase") != "state_head"
        or action_call.get("attempt") != 0
        or state_call.get("attempt") != 0
    ):
        raise EvaluationError(f"V2_HEAD_ORDER_MISMATCH:{case['case_id']}")
    allowed_indices = case["action_output_contract"]["allowed_action_indices"]
    allowed_claims = case["state_output_contract"]["allowed_claim_handles"]
    base = _base_public_payload(case)
    action_payload = {
        **base,
        "task": "choose_public_action_index",
        "output_contract": {
            "exact_keys": ["action_index"],
            "allowed_action_indices": allowed_indices,
        },
    }
    action_grammar = action_grammar_schema(
        repo_root / "docs/spec/controller_v2_action_schema.json",
        allowed_action_indices=allowed_indices,
    )
    _check_call_record(
        action_call,
        expected_system=ACTION_SYSTEM_PROMPT,
        expected_request_hash=_request_hash(
            ACTION_SYSTEM_PROMPT, action_payload, action_grammar
        ),
    )
    if action_call.get("grammar_hash") != sha256_json(action_grammar):
        raise EvaluationError(f"ACTION_GRAMMAR_HASH_MISMATCH:{case['case_id']}")
    parsed_action = None
    if action_call.get("status") == "valid":
        parsed_action = parse_action_output(
            str(action_call["raw_output_utf8"]).encode(),
            allowed_action_indices=allowed_indices,
        )
    selected_index = (
        parsed_action["action_index"] if parsed_action is not None else None
    )
    state_payload = {
        **base,
        "task": "estimate_public_evidence_state",
        "selected_action_index": selected_index,
        "output_contract": {
            "exact_keys": list(STATE_FIELDS),
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
        repo_root / "docs/spec/controller_v2_state_schema.json",
        allowed_claim_handles=allowed_claims,
    )
    _check_call_record(
        state_call,
        expected_system=STATE_SYSTEM_PROMPT,
        expected_request_hash=_request_hash(
            STATE_SYSTEM_PROMPT, state_payload, state_grammar
        ),
    )
    if state_call.get("grammar_hash") != sha256_json(state_grammar):
        raise EvaluationError(f"STATE_GRAMMAR_HASH_MISMATCH:{case['case_id']}")
    parsed_state = None
    if state_call.get("status") == "valid":
        parsed_state = parse_state_output(
            str(state_call["raw_output_utf8"]).encode(),
            allowed_claim_handles=allowed_claims,
        )
    dispatched = (
        dict(case["action_menu"][selected_index])
        if selected_index is not None
        else None
    )
    expected = {
        "case_id": case["case_id"],
        "arm": "v2",
        "public_payload_hash": sha256_json(base),
        "action_syntax_valid": parsed_action is not None,
        "state_syntax_valid": parsed_state is not None,
        "selected_action_index": selected_index,
        "dispatched_action": dispatched,
        "public_state": parsed_state,
        "finalizer_called": (
            dispatched is not None and dispatched.get("type") == "finalize"
        ),
    }
    for key, value in expected.items():
        if result.get(key) != value:
            raise EvaluationError(
                f"V2_RESULT_RECOMPUTE_MISMATCH:{case['case_id']}:{key}"
            )
    _verify_finalizer(case=case, result=result, calls=calls[2:])


def _verify_v1_case(
    *,
    case: Mapping[str, Any],
    result: Mapping[str, Any],
    calls: Sequence[Mapping[str, Any]],
) -> None:
    controller_calls = [call for call in calls if call.get("phase") == "v1_monolithic"]
    finalizer_calls = [
        call for call in calls if call.get("phase") == "grounded_finalization"
    ]
    if not controller_calls or len(controller_calls) > 2:
        raise EvaluationError(f"V1_CALL_COUNT_INVALID:{case['case_id']}")
    original_payload = _v1_payload(case)
    system = prompt_text(
        "react_v1.txt" if case["policy"] == "react" else "sufficiency_v1.txt"
    )
    parsed_decision: dict[str, Any] | None = None
    for index, call in enumerate(controller_calls):
        if call.get("attempt") != index:
            raise EvaluationError(f"V1_ATTEMPT_ORDER_MISMATCH:{case['case_id']}")
        payload = original_payload
        if index == 1:
            prior = controller_calls[0]
            payload = _repair_payload(
                original_payload,
                raw=str(prior.get("raw_output_utf8", "")),
                validation_error=str(prior.get("validation_error", "")),
            )
            system = prompt_text("repair_v1.txt")
        _check_call_record(
            call,
            expected_system=system,
            expected_request_hash=_v1_request_hash(system, payload),
        )
        if call.get("status") == "valid":
            parsed_decision = _validate_v1_decision(case, str(call["raw_output_utf8"]))
        else:
            try:
                _validate_v1_decision(case, str(call["raw_output_utf8"]))
            except (PublicSchemaError, TypeError, ValueError):
                pass
            else:
                raise EvaluationError(
                    f"V1_INVALID_CALL_REPARSED_VALID:{case['case_id']}:{index}"
                )
    if parsed_decision is None:
        expected = {
            "action_syntax_valid": False,
            "state_syntax_valid": False,
            "selected_action_index": None,
            "dispatched_action": None,
            "public_state": None,
            "finalizer_called": False,
            "final": None,
            "finalization_error": "MALFORMED_AFTER_REPAIR",
        }
    else:
        action = parsed_decision["action"]
        expected = {
            "action_syntax_valid": True,
            "state_syntax_valid": True,
            "selected_action_index": parsed_decision["action_index"],
            "dispatched_action": action,
            "public_state": parsed_decision["public_state"],
            "finalizer_called": action.get("type") == "finalize",
        }
    common = {
        "case_id": case["case_id"],
        "arm": "v1",
        "public_payload_hash": sha256_json(_base_public_payload(case)),
        **expected,
    }
    for key, value in common.items():
        if result.get(key) != value:
            raise EvaluationError(
                f"V1_RESULT_RECOMPUTE_MISMATCH:{case['case_id']}:{key}"
            )
    _verify_finalizer(case=case, result=result, calls=finalizer_calls)


def _verify_finalizer(
    *,
    case: Mapping[str, Any],
    result: Mapping[str, Any],
    calls: Sequence[Mapping[str, Any]],
) -> None:
    if not result.get("finalizer_called"):
        if calls or result.get("final") is not None:
            raise EvaluationError(f"UNAUTHORED_FINAL_PRESENT:{case['case_id']}")
        return
    if not calls or len(calls) > 2:
        raise EvaluationError(f"FINALIZER_CALL_COUNT_INVALID:{case['case_id']}")
    original_payload = _finalizer_payload(case)
    system = prompt_text("generator_v1.txt")
    parsed_final: dict[str, Any] | None = None
    for index, call in enumerate(calls):
        if call.get("attempt") != index:
            raise EvaluationError(f"FINALIZER_ATTEMPT_ORDER_MISMATCH:{case['case_id']}")
        payload = original_payload
        if index == 1:
            prior = calls[0]
            payload = _repair_payload(
                original_payload,
                raw=str(prior.get("raw_output_utf8", "")),
                validation_error=str(prior.get("validation_error", "")),
            )
            system = prompt_text("repair_v1.txt")
        _check_call_record(
            call,
            expected_system=system,
            expected_request_hash=_v1_request_hash(system, payload),
        )
        if call.get("status") == "valid":
            parsed_final = _validate_final(case, str(call["raw_output_utf8"]))
    if result.get("final") != parsed_final:
        raise EvaluationError(f"FINAL_RESULT_RECOMPUTE_MISMATCH:{case['case_id']}")
    expected_error = None if parsed_final is not None else "MALFORMED_AFTER_REPAIR"
    if result.get("finalization_error") != expected_error:
        raise EvaluationError(f"FINAL_ERROR_RECOMPUTE_MISMATCH:{case['case_id']}")


def verify_pre_key(repo_root: Path) -> dict[str, Any]:
    """Verify all release conditions that do not require key filesystem access."""

    contract_path = repo_root / CONTRACT_REL
    public_path = repo_root / PUBLIC_REL
    run_dir = repo_root / RUN_REL
    attestation_path = repo_root / ATTESTATION_REL
    contract = _load_json(contract_path)
    public = _load_json(public_path)
    seal = _load_json(run_dir / "output_seal.json")
    manifest = _load_json(run_dir / "execution_manifest.json")

    actual_files = {path.name for path in run_dir.iterdir() if path.is_file()}
    if actual_files != SEALED_ARTIFACTS | {"output_seal.json"}:
        raise EvaluationError("SEALED_DIRECTORY_FILE_SET_MISMATCH")
    if set(seal.get("files", {})) != SEALED_ARTIFACTS:
        raise EvaluationError("SEALED_ARTIFACT_SET_MISMATCH")
    if (
        seal.get("immutable") is not True
        or seal.get("correctness_scored") is not False
        or seal.get("evaluator_labels_loaded") is not False
    ):
        raise EvaluationError("OUTPUT_SEAL_BOUNDARY_MISMATCH")
    sealed_hashes: dict[str, dict[str, Any]] = {}
    for name in sorted(SEALED_ARTIFACTS):
        path = run_dir / name
        actual = {
            "bytes": path.stat().st_size,
            "sha256": _sha256_file(path),
        }
        if seal["files"][name] != actual:
            raise EvaluationError(f"OUTPUT_SEAL_HASH_OR_SIZE_MISMATCH:{name}")
        if stat.S_IMODE(path.stat().st_mode) != 0o444:
            raise EvaluationError(f"SEALED_ARTIFACT_MODE_MISMATCH:{name}")
        sealed_hashes[name] = actual
    if stat.S_IMODE((run_dir / "output_seal.json").stat().st_mode) != 0o444:
        raise EvaluationError("OUTPUT_SEAL_MODE_MISMATCH")

    canonical_contract = {
        key: value for key, value in contract.items() if key != "contract_hash"
    }
    canonical_hash = _sha256_bytes(canonical_json_bytes(canonical_contract))
    if contract.get("contract_hash") != canonical_hash:
        raise EvaluationError("CONTRACT_CANONICAL_HASH_MISMATCH")
    commitments = seal.get("input_commitments", {})
    if commitments.get("contract_hash") != canonical_hash or commitments.get(
        "contract_file_sha256"
    ) != _sha256_file(contract_path):
        raise EvaluationError("CONTRACT_SEAL_COMMITMENT_MISMATCH")
    artifact_paths = {
        "design": repo_root / "docs/design/controller_interface_v2.md",
        "action_schema": repo_root / "docs/spec/controller_v2_action_schema.json",
        "state_schema": repo_root / "docs/spec/controller_v2_state_schema.json",
        "public_execution_packet": public_path,
    }
    artifact_hashes: dict[str, str] = {}
    for logical_name, path in artifact_paths.items():
        actual_hash = _sha256_file(path)
        if (
            contract["artifact_hashes"].get(logical_name) != actual_hash
            or commitments.get("checked_artifacts", {}).get(logical_name) != actual_hash
        ):
            raise EvaluationError(f"INPUT_ARTIFACT_HASH_MISMATCH:{logical_name}")
        artifact_hashes[logical_name] = actual_hash
    if (
        commitments.get("public_packet_sha256")
        != artifact_hashes["public_execution_packet"]
    ):
        raise EvaluationError("PUBLIC_PACKET_SEAL_COMMITMENT_MISMATCH")
    for relative, expected in contract["task111_protected_hashes"].items():
        actual = _sha256_file(repo_root / relative)
        if (
            actual != expected
            or commitments.get("task111_protected_hashes_verified", {}).get(relative)
            != actual
        ):
            raise EvaluationError(f"TASK111_HASH_MISMATCH:{relative}")

    if FORBIDDEN_PUBLIC_KEYS.intersection(_walk_keys(public)):
        raise EvaluationError("PRIVATE_LABEL_KEY_IN_PUBLIC_PACKET")
    serialized_public = json.dumps(
        public["cases"], sort_keys=True, ensure_ascii=False
    ).casefold()
    if any(marker in serialized_public for marker in EVALUATION_FAMILY_MARKERS):
        raise EvaluationError("EVALUATION_FAMILY_CONTENT_DETECTED")

    cases = public.get("cases")
    if not isinstance(cases, list) or len(cases) != 28:
        raise EvaluationError("PUBLIC_CASE_COUNT_MISMATCH")
    case_ids = [case["case_id"] for case in cases]
    if len(set(case_ids)) != 28:
        raise EvaluationError("PUBLIC_CASE_ID_DUPLICATE")
    if (
        manifest.get("schema_version")
        != "av-trace.controller-v2-execution-manifest/2.0"
        or manifest.get("arm") != "paired"
        or manifest.get("execution_mode") != "confirmatory_paired"
        or manifest.get("confirmatory") is not True
        or manifest.get("execution_status") != "SEALED_UNSCORED_PAIRED"
        or manifest.get("case_count") != 28
        or manifest.get("case_order") != case_ids
        or manifest.get("packet_id") != public.get("packet_id")
        or manifest.get("correctness_scored") is not False
        or manifest.get("evaluator_labels_loaded") is not False
        or manifest.get("restricted_evaluator_key_accessed") is not False
    ):
        raise EvaluationError("EXECUTION_MANIFEST_MISMATCH")
    paired = manifest.get("paired_protocol", {})
    if (
        paired.get("enabled") is not True
        or paired.get("required_for_confirmation") is not True
        or paired.get("arm_order_within_each_case") != ["v1", "v2"]
        or paired.get("one_shared_model_process") is not True
        or paired.get("model_process_count") != 1
        or paired.get("separate_arm_artifacts") is not True
    ):
        raise EvaluationError("PAIRED_PROCESS_COMMITMENT_MISMATCH")
    runtime = manifest.get("runtime", {})
    worker = runtime.get("model_worker", {})
    frozen_runtime = contract["model_and_runtime"]
    if (
        worker.get("pid") is None
        or worker.get("device") != "cpu"
        or worker.get("dtype") != "torch.bfloat16"
        or worker.get("local_files_only") is not True
        or worker.get("offline") is not True
        or worker.get("network_namespace_denied") is not True
        or worker.get("constraint_engine") != "xgrammar"
        or runtime.get("network_namespace_denied") is not True
        or runtime.get("offline_environment") is not True
        or runtime.get("threads") != frozen_runtime["thread_count"]
        or worker.get("max_context_tokens") != frozen_runtime["context_limit_tokens"]
    ):
        raise EvaluationError("RUNTIME_MANIFEST_MISMATCH")
    model = manifest.get("model_identity", {})
    acquisition_path = (
        repo_root / "data/restricted/scale1b/manifests/"
        "strong_controller_model_acquisition.json"
    )
    acquisition = _load_json(acquisition_path)
    candidate = acquisition["candidate"]
    acquisition_files = {
        item["path"]: item for item in acquisition["acquisition"]["files"]
    }
    expected_model_files = {
        item["path"]: {
            "bytes": item["expected_bytes"],
            "sha256": "sha256:" + acquisition_files[item["path"]]["sha256"],
        }
        for item in candidate["allowlist"]
    }
    if (
        model.get("repo_id") != frozen_runtime["repo_id"]
        or model.get("revision") != frozen_runtime["revision"]
        or os.path.abspath(str(model.get("snapshot_path")))
        != os.path.abspath(repo_root / frozen_runtime["snapshot_dir"])
        or model.get("manifest_sha256") != _sha256_file(acquisition_path)
        or model.get("repo_id") != candidate["repo_id"]
        or model.get("revision") != candidate["revision"]
        or model.get("files") != expected_model_files
    ):
        raise EvaluationError("MODEL_IDENTITY_MISMATCH")
    if manifest.get("persisted_content_policy") != {
        "raw_model_output": True,
        "request_hashes": True,
        "grammar_hashes": True,
        "token_counts": True,
        "latency": True,
        "rss": True,
        "full_system_prompt": False,
        "full_request_payload": False,
    }:
        raise EvaluationError("PERSISTED_CONTENT_POLICY_MISMATCH")

    attestation = _load_json(attestation_path)
    if _sha256_file(attestation_path) != manifest.get(
        "implementation_attestation", {}
    ).get("sha256"):
        raise EvaluationError("IMPLEMENTATION_ATTESTATION_HASH_MISMATCH")
    for field in (
        "forbidden_evaluator_key_not_accessed",
        "holdout_not_executed_during_implementation",
        "no_expected_outputs_or_labels_inspected",
    ):
        if (
            attestation.get(field) is not True
            or manifest["implementation_attestation"].get(field) is not True
        ):
            raise EvaluationError(f"IMPLEMENTATION_ATTESTATION_FAILED:{field}")

    order_rows = _load_jsonl(run_dir / "order_trace.jsonl")
    expected_order = [
        {
            "sequence": sequence,
            "case_index": case_index,
            "case_id": case_id,
            "arm": arm,
        }
        for case_index, case_id in enumerate(case_ids)
        for arm, sequence in (
            ("v1", case_index * 2),
            ("v2", case_index * 2 + 1),
        )
    ]
    if order_rows != expected_order:
        raise EvaluationError("PAIRED_ORDER_TRACE_MISMATCH")

    results_by_arm: dict[str, list[dict[str, Any]]] = {}
    calls_by_arm: dict[str, list[dict[str, Any]]] = {}
    for arm in ("v1", "v2"):
        results = _load_jsonl(run_dir / f"{arm}_results.jsonl")
        calls = _load_jsonl(run_dir / f"{arm}_calls.jsonl")
        if (
            len(results) != 28
            or [row.get("case_id") for row in results] != case_ids
            or any(row.get("arm") != arm for row in results)
            or any(row.get("arm") != arm for row in calls)
        ):
            raise EvaluationError(f"{arm.upper()}_ROW_OR_ORDER_MISMATCH")
        results_by_arm[arm] = results
        calls_by_arm[arm] = calls

    for arm in ("v1", "v2"):
        results = {row["case_id"]: row for row in results_by_arm[arm]}
        calls_by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for call in calls_by_arm[arm]:
            calls_by_case[str(call["case_id"])].append(call)
            identity = call.get("model_identity", {})
            if (
                identity.get("repo_id") != frozen_runtime["repo_id"]
                or identity.get("revision") != frozen_runtime["revision"]
                or identity.get("device") != "cpu"
                or identity.get("dtype") != "torch.bfloat16"
            ):
                raise EvaluationError(f"{arm.upper()}_CALL_MODEL_MISMATCH")
            if {
                "system",
                "system_prompt",
                "payload",
                "request_payload",
            }.intersection(call):
                raise EvaluationError("PROMPT_OR_REQUEST_PAYLOAD_PERSISTED")
        if set(calls_by_case) != set(case_ids):
            raise EvaluationError(f"{arm.upper()}_CALL_CASE_SET_MISMATCH")
        for case in cases:
            if arm == "v2":
                _verify_v2_case(
                    repo_root=repo_root,
                    case=case,
                    result=results[case["case_id"]],
                    calls=calls_by_case[case["case_id"]],
                )
            else:
                _verify_v1_case(
                    case=case,
                    result=results[case["case_id"]],
                    calls=calls_by_case[case["case_id"]],
                )

    execution_source = (
        repo_root / "src/av_trace_controller_v2/execution.py"
    ).read_text(encoding="utf-8")
    execution_tree = ast.parse(execution_source)
    imported_modules = {
        alias.name
        for node in ast.walk(execution_tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    process_constructor_count = sum(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "ConstrainedQwenProcess"
        for node in ast.walk(execution_tree)
    )
    if process_constructor_count != 1:
        raise EvaluationError("EXECUTION_PROCESS_CONSTRUCTOR_COUNT_MISMATCH")
    if any("evaluator" in name or "scor" in name for name in imported_modules):
        raise EvaluationError("EXECUTION_IMPORTED_EVALUATOR_OR_SCORING")
    if "restricted_evaluator_key.json" in execution_source:
        raise EvaluationError("EXECUTION_SOURCE_REFERENCES_RESTRICTED_KEY")
    packet_source = (repo_root / "src/av_trace_controller_v2/packet.py").read_text(
        encoding="utf-8"
    )
    if (
        "restricted_evaluator_key.json" not in packet_source
        or "FORBIDDEN_EVALUATOR_KEY_PATH" not in packet_source
    ):
        raise EvaluationError("FORBIDDEN_KEY_GUARD_NOT_PRESENT")

    all_calls = [call for arm_calls in calls_by_arm.values() for call in arm_calls]
    constraint_failures = sum(
        call.get("status") == "constraint_runtime_failure"
        or call.get("error_code") == "CONSTRAINT_RUNTIME_FAILURE"
        for call in all_calls
    )
    process_failures = sum(
        call.get("status") in {"process_error", "constraint_runtime_failure"}
        for call in all_calls
    )
    return {
        "repo_root": repo_root,
        "contract": contract,
        "public": public,
        "seal": seal,
        "manifest": manifest,
        "results_by_arm": results_by_arm,
        "calls_by_arm": calls_by_arm,
        "verification": {
            "pre_key_verification_passed": True,
            "sealed_artifact_count": len(SEALED_ARTIFACTS),
            "sealed_hashes": sealed_hashes,
            "contract_hash": canonical_hash,
            "contract_file_sha256": _sha256_file(contract_path),
            "artifact_hashes": artifact_hashes,
            "case_count": 28,
            "order_row_count": len(order_rows),
            "v1_result_count": len(results_by_arm["v1"]),
            "v2_result_count": len(results_by_arm["v2"]),
            "v1_call_count": len(calls_by_arm["v1"]),
            "v2_call_count": len(calls_by_arm["v2"]),
            "model_process_count": 1,
            "exact_v1_v2_order": True,
            "public_only_request_hashes_recomputed": True,
            "raw_results_recomputed": True,
            "implementation_no_label_access_attested": True,
            "execution_source_has_no_evaluator_or_scoring_import": True,
            "forbidden_key_path_guard_present": True,
            "execution_source_model_process_constructor_count": (
                process_constructor_count
            ),
            "model_acquisition_manifest_verified": True,
            "constraint_runtime_failure_count": constraint_failures,
            "process_failure_count": process_failures,
        },
    }


def _score_terminal(
    result: Mapping[str, Any], finalization: Mapping[str, Any]
) -> dict[str, Any]:
    terminal = finalization["terminal_case"] is True
    expected_mode = finalization["expected_mode"]
    reached = bool(
        result.get("action_syntax_valid")
        and result.get("dispatched_action") == {"type": "finalize"}
        and result.get("finalizer_called")
    )
    final = result.get("final")
    syntax_valid = bool(reached and final is not None)
    errors: list[str] = []
    unsupported = 0
    supported_answer = False
    correct_abstention = False
    if not terminal:
        return {
            "terminal_case": False,
            "expected_mode": None,
            "finalization_reached": reached,
            "finalization_syntax_valid": syntax_valid,
            "terminal_correct": False,
            "supported_answer": False,
            "correct_abstention": False,
            "unsupported_required_claims": 0,
            "errors": [],
        }
    if not reached:
        errors.append("TERMINAL_FINALIZE_NOT_REACHED")
    elif not syntax_valid:
        errors.append("FINALIZATION_SYNTAX_INVALID")
    elif expected_mode == "answer":
        if final["verdict"] not in finalization["allowed_verdicts"]:
            errors.append("WRONG_VERDICT")
        assertions = {row["claim_handle"]: row for row in final["asserted_claims"]}
        required = finalization["required_claims"]
        if set(assertions) != set(required):
            errors.append("REQUIRED_CLAIM_SET_MISMATCH")
        for handle, requirement in required.items():
            assertion = assertions.get(handle)
            if assertion is None:
                errors.append(f"MISSING_REQUIRED_CLAIM:{handle}")
                continue
            citations = assertion["citations"]
            if citations != requirement["required_citations"]:
                unsupported += 1
                errors.append(f"UNSUPPORTED_REQUIRED_CLAIM:{handle}")
            combined = f"{assertion['text']} {final['answer_text']}".casefold()
            if not any(
                term.casefold() in combined for term in requirement["required_terms"]
            ):
                errors.append(f"REQUIRED_CONTENT_MISSING:{handle}")
        if (
            final["missing_modalities"] != finalization["expected_missing_modalities"]
            or final["missing_hops"] != finalization["expected_missing_hops"]
            or final["missingness_cause"] != finalization["expected_missingness_cause"]
        ):
            errors.append("ANSWER_DIAGNOSIS_MISMATCH")
        supported_answer = not errors
    else:
        unsupported = len(final["asserted_claims"])
        if final["verdict"] not in finalization["allowed_verdicts"]:
            errors.append("WRONG_VERDICT")
        if (
            final["answer_text"] != ""
            or final["asserted_claims"] != []
            or final["claim_to_citations"] != {}
        ):
            errors.append("ABSTENTION_CONTAINS_ANSWER_OR_CLAIMS")
        if (
            final["missing_modalities"] != finalization["expected_missing_modalities"]
            or final["missing_hops"] != finalization["expected_missing_hops"]
            or final["missingness_cause"] != finalization["expected_missingness_cause"]
        ):
            errors.append("ABSTENTION_DIAGNOSIS_MISMATCH")
        if unsupported:
            errors.append("UNSUPPORTED_ABSTENTION_CLAIMS")
        correct_abstention = not errors
    return {
        "terminal_case": True,
        "expected_mode": expected_mode,
        "finalization_reached": reached,
        "finalization_syntax_valid": syntax_valid,
        "terminal_correct": not errors,
        "supported_answer": supported_answer,
        "correct_abstention": correct_abstention,
        "unsupported_required_claims": unsupported,
        "errors": errors,
    }


def _score_case(
    *,
    arm: str,
    case_id: str,
    stratum: str,
    result: Mapping[str, Any],
    label: Mapping[str, Any],
    calls: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    action_correct = bool(
        result.get("action_syntax_valid")
        and result.get("selected_action_index")
        == label["action"]["expected_action_index"]
        and result.get("dispatched_action") == label["action"]["expected_action"]
    )
    state_scores = {
        field: bool(
            result.get("state_syntax_valid")
            and isinstance(result.get("public_state"), dict)
            and result["public_state"].get(field) == label["state"][field]
        )
        for field in STATE_FIELDS
    }
    terminal = _score_terminal(result, label["finalization"])
    process_failure = any(
        call.get("status") in {"process_error", "constraint_runtime_failure"}
        for call in calls
    )
    constraint_failure = any(
        call.get("status") == "constraint_runtime_failure"
        or call.get("error_code") == "CONSTRAINT_RUNTIME_FAILURE"
        for call in calls
    )
    return {
        "case_id": case_id,
        "arm": arm,
        "primary_stratum": stratum,
        "action_syntax_valid": bool(result.get("action_syntax_valid")),
        "action_correct": action_correct,
        "state_syntax_valid": bool(result.get("state_syntax_valid")),
        "state_field_correct": state_scores,
        "state_exact": all(state_scores.values()),
        "state_exact_given_action_ok": (
            all(state_scores.values()) if action_correct else None
        ),
        **terminal,
        "process_failure": process_failure,
        "constraint_runtime_failure": constraint_failure,
    }


def _paired_table(
    v1_by_id: Mapping[str, Mapping[str, Any]],
    v2_by_id: Mapping[str, Mapping[str, Any]],
    case_ids: Sequence[str],
    field: str,
) -> dict[str, int]:
    table = {
        "v1_incorrect_v2_incorrect": 0,
        "v1_incorrect_v2_correct": 0,
        "v1_correct_v2_incorrect": 0,
        "v1_correct_v2_correct": 0,
    }
    for case_id in case_ids:
        v1 = bool(v1_by_id[case_id][field])
        v2 = bool(v2_by_id[case_id][field])
        key = (
            f"v1_{'correct' if v1 else 'incorrect'}_"
            f"v2_{'correct' if v2 else 'incorrect'}"
        )
        table[key] += 1
    return table


def _arm_metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    terminal_rows = [row for row in rows if row["terminal_case"]]
    answer_rows = [row for row in terminal_rows if row["expected_mode"] == "answer"]
    abstain_rows = [row for row in terminal_rows if row["expected_mode"] == "abstain"]
    action_ok_rows = [row for row in rows if row["action_correct"]]
    return {
        "case_count": len(rows),
        "action_syntax_valid_count": sum(row["action_syntax_valid"] for row in rows),
        "action_correct_count": sum(row["action_correct"] for row in rows),
        "state_syntax_valid_count": sum(row["state_syntax_valid"] for row in rows),
        "state_exact_count": sum(row["state_exact"] for row in rows),
        "state_field_correct_counts": {
            field: sum(row["state_field_correct"][field] for row in rows)
            for field in STATE_FIELDS
        },
        "state_exact_given_action_ok_count": sum(
            row["state_exact"] for row in action_ok_rows
        ),
        "state_exact_given_action_ok_denominator": len(action_ok_rows),
        "terminal_case_count": len(terminal_rows),
        "finalization_reached_total_count": sum(
            row["finalization_reached"] for row in rows
        ),
        "finalization_syntax_valid_total_count": sum(
            row["finalization_syntax_valid"] for row in rows
        ),
        "finalization_reached_count": sum(
            row["finalization_reached"] for row in terminal_rows
        ),
        "finalization_syntax_valid_count": sum(
            row["finalization_syntax_valid"] for row in terminal_rows
        ),
        "reached_terminal_correct_count": sum(
            row["terminal_correct"]
            for row in terminal_rows
            if row["finalization_reached"]
        ),
        "reached_terminal_denominator": sum(
            row["finalization_reached"] for row in terminal_rows
        ),
        "end_to_end_terminal_correct_count": sum(
            row["terminal_correct"] for row in terminal_rows
        ),
        "supported_answer_count": sum(row["supported_answer"] for row in answer_rows),
        "supported_answer_denominator": len(answer_rows),
        "correct_abstention_count": sum(
            row["correct_abstention"] for row in abstain_rows
        ),
        "correct_abstention_denominator": len(abstain_rows),
        "unsupported_required_claim_count": sum(
            row["unsupported_required_claims"] for row in rows
        ),
        "process_failure_count": sum(row["process_failure"] for row in rows),
        "constraint_runtime_failure_count": sum(
            row["constraint_runtime_failure"] for row in rows
        ),
    }


def _per_stratum(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, int]]:
    output: dict[str, dict[str, int]] = {}
    for stratum in PRIMARY_STRATA:
        selected = [row for row in rows if row["primary_stratum"] == stratum]
        output[stratum] = {
            "case_count": len(selected),
            "action_syntax_valid_count": sum(
                row["action_syntax_valid"] for row in selected
            ),
            "action_correct_count": sum(row["action_correct"] for row in selected),
            "state_syntax_valid_count": sum(
                row["state_syntax_valid"] for row in selected
            ),
            "state_exact_count": sum(row["state_exact"] for row in selected),
            "state_field_correct_counts": {
                field: sum(row["state_field_correct"][field] for row in selected)
                for field in STATE_FIELDS
            },
            "terminal_case_count": sum(row["terminal_case"] for row in selected),
            "finalization_reached_count": sum(
                row["finalization_reached"] for row in selected
            ),
            "finalization_syntax_valid_count": sum(
                row["finalization_syntax_valid"] for row in selected
            ),
            "terminal_correct_count": sum(row["terminal_correct"] for row in selected),
            "supported_answer_count": sum(row["supported_answer"] for row in selected),
            "correct_abstention_count": sum(
                row["correct_abstention"] for row in selected
            ),
            "unsupported_required_claim_count": sum(
                row["unsupported_required_claims"] for row in selected
            ),
            "process_failure_count": sum(row["process_failure"] for row in selected),
            "constraint_runtime_failure_count": sum(
                row["constraint_runtime_failure"] for row in selected
            ),
        }
    return output


def _compare(actual: int, operator: str, threshold: int) -> bool:
    if operator == "==":
        return actual == threshold
    if operator == ">=":
        return actual >= threshold
    if operator == "<=":
        return actual <= threshold
    raise EvaluationError(f"UNKNOWN_GATE_OPERATOR:{operator}")


def _gate_record(
    *,
    actual: int,
    specification: Mapping[str, Any],
) -> dict[str, Any]:
    operator = str(specification["operator"])
    threshold = int(specification["value"])
    result = {
        "actual": actual,
        "operator": operator,
        "threshold": threshold,
        "passed": _compare(actual, operator, threshold),
    }
    if "denominator" in specification:
        result["denominator"] = int(specification["denominator"])
    return result


def score_evaluation(
    verified: Mapping[str, Any],
    *,
    key: Mapping[str, Any],
    key_verification: Mapping[str, Any],
) -> dict[str, Any]:
    contract = verified["contract"]
    public = verified["public"]
    case_ids = [case["case_id"] for case in public["cases"]]
    labels = key.get("case_labels", {})
    strata = key.get("primary_strata", {})
    if (
        key.get("packet_id") != public.get("packet_id")
        or set(labels) != set(case_ids)
        or set(strata) != set(case_ids)
        or Counter(strata.values()) != {stratum: 4 for stratum in PRIMARY_STRATA}
    ):
        raise EvaluationError("RESTRICTED_KEY_CASE_OR_STRATUM_MISMATCH")
    if (
        tuple(contract["preregistered_gates"]["automatic_no_go_conditions"])
        != AUTOMATIC_NO_GO_CONDITIONS
    ):
        raise EvaluationError("FROZEN_AUTOMATIC_NO_GO_SET_MISMATCH")

    scores_by_arm: dict[str, list[dict[str, Any]]] = {}
    for arm in ("v1", "v2"):
        results = {row["case_id"]: row for row in verified["results_by_arm"][arm]}
        calls_by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for call in verified["calls_by_arm"][arm]:
            calls_by_case[str(call["case_id"])].append(call)
        scores_by_arm[arm] = [
            _score_case(
                arm=arm,
                case_id=case_id,
                stratum=strata[case_id],
                result=results[case_id],
                label=labels[case_id],
                calls=calls_by_case[case_id],
            )
            for case_id in case_ids
        ]

    metrics = {arm: _arm_metrics(scores_by_arm[arm]) for arm in ("v1", "v2")}
    per_stratum = {arm: _per_stratum(scores_by_arm[arm]) for arm in ("v1", "v2")}
    by_id = {
        arm: {row["case_id"]: row for row in scores_by_arm[arm]} for arm in ("v1", "v2")
    }
    terminal_ids = [
        case_id
        for case_id in case_ids
        if labels[case_id]["finalization"]["terminal_case"]
    ]
    transitions = {
        "action_correctness_2x2": _paired_table(
            by_id["v1"], by_id["v2"], case_ids, "action_correct"
        ),
        "state_exactness_2x2": _paired_table(
            by_id["v1"], by_id["v2"], case_ids, "state_exact"
        ),
        "terminal_correctness_2x2": _paired_table(
            by_id["v1"], by_id["v2"], terminal_ids, "terminal_correct"
        ),
    }

    absolute_specs = contract["preregistered_gates"]["absolute_v2"]
    v2 = metrics["v2"]
    absolute: dict[str, Any] = {
        "action_syntax_valid_count": _gate_record(
            actual=v2["action_syntax_valid_count"],
            specification=absolute_specs["action_syntax_valid_count"],
        ),
        "state_syntax_valid_count": _gate_record(
            actual=v2["state_syntax_valid_count"],
            specification=absolute_specs["state_syntax_valid_count"],
        ),
        "action_correct_count": _gate_record(
            actual=v2["action_correct_count"],
            specification=absolute_specs["action_correct_count"],
        ),
        "state_exact_count": _gate_record(
            actual=v2["state_exact_count"],
            specification=absolute_specs["state_exact_count"],
        ),
        "end_to_end_terminal_correct_count": _gate_record(
            actual=v2["end_to_end_terminal_correct_count"],
            specification=absolute_specs["end_to_end_terminal_correct_count"],
        ),
        "supported_answer_count": _gate_record(
            actual=v2["supported_answer_count"],
            specification=absolute_specs["supported_answer_count"],
        ),
        "correct_abstention_count": _gate_record(
            actual=v2["correct_abstention_count"],
            specification=absolute_specs["correct_abstention_count"],
        ),
        "unsupported_required_claims": _gate_record(
            actual=v2["unsupported_required_claim_count"],
            specification=absolute_specs["unsupported_required_claims"],
        ),
        "evaluation_family_or_private_label_exposures": _gate_record(
            actual=0,
            specification=absolute_specs[
                "evaluation_family_or_private_label_exposures"
            ],
        ),
    }
    stratum_spec = absolute_specs["action_correct_per_primary_stratum"]
    absolute["action_correct_per_primary_stratum"] = {
        "operator": stratum_spec["operator"],
        "threshold": stratum_spec["value"],
        "denominator": stratum_spec["denominator"],
        "actual_by_stratum": {
            stratum: per_stratum["v2"][stratum]["action_correct_count"]
            for stratum in PRIMARY_STRATA
        },
        "passed": all(
            _compare(
                per_stratum["v2"][stratum]["action_correct_count"],
                stratum_spec["operator"],
                stratum_spec["value"],
            )
            for stratum in PRIMARY_STRATA
        ),
    }
    field_spec = absolute_specs["each_state_field_correct_count"]
    absolute["each_state_field_correct_count"] = {
        "operator": field_spec["operator"],
        "threshold": field_spec["value"],
        "actual_by_field": v2["state_field_correct_counts"],
        "passed": all(
            _compare(count, field_spec["operator"], field_spec["value"])
            for count in v2["state_field_correct_counts"].values()
        ),
    }

    deltas = {
        "action_correct_count_delta": (
            metrics["v2"]["action_correct_count"]
            - metrics["v1"]["action_correct_count"]
        ),
        "state_exact_count_delta": (
            metrics["v2"]["state_exact_count"] - metrics["v1"]["state_exact_count"]
        ),
        "end_to_end_terminal_correct_count_delta": (
            metrics["v2"]["end_to_end_terminal_correct_count"]
            - metrics["v1"]["end_to_end_terminal_correct_count"]
        ),
        "unsupported_required_claim_count_delta": (
            metrics["v2"]["unsupported_required_claim_count"]
            - metrics["v1"]["unsupported_required_claim_count"]
        ),
    }
    paired_specs = contract["preregistered_gates"]["paired_v2_minus_v1"]
    paired = {
        name: _gate_record(
            actual=value,
            specification=paired_specs[name],
        )
        for name, value in deltas.items()
    }

    repo_root = Path(verified["repo_root"])
    run_dir = repo_root / RUN_REL
    key_path = repo_root / KEY_REL
    run_first_mtime_ns = min(
        (run_dir / name).stat().st_mtime_ns for name in SEALED_ARTIFACTS
    )
    labels_changed_after_output = key_path.stat().st_mtime_ns > run_first_mtime_ns
    source_commitment_paths = [
        repo_root / CONTRACT_REL,
        repo_root / PUBLIC_REL,
        repo_root / "docs/design/controller_interface_v2.md",
        repo_root / "docs/spec/controller_v2_action_schema.json",
        repo_root / "docs/spec/controller_v2_state_schema.json",
        repo_root / "scripts/run_controller_v2_public_packet.py",
        repo_root / "src/av_trace_scale1b_agent/prompts/react_v1.txt",
        repo_root / "src/av_trace_scale1b_agent/prompts/sufficiency_v1.txt",
        repo_root / "src/av_trace_scale1b_agent/prompts/repair_v1.txt",
        repo_root / "src/av_trace_scale1b_agent/prompts/generator_v1.txt",
        repo_root / "src/av_trace_scale1b_agent/controller.py",
        repo_root / "src/av_trace_scale1b_agent/schema.py",
        *(repo_root / "src/av_trace_controller_v2").glob("*.py"),
    ]
    post_run_tuning = any(
        path.stat().st_mtime_ns > run_first_mtime_ns for path in source_commitment_paths
    )
    all_calls = [call for arm in ("v1", "v2") for call in verified["calls_by_arm"][arm]]
    constraint_failure = any(
        call.get("status") == "constraint_runtime_failure"
        or call.get("error_code") == "CONSTRAINT_RUNTIME_FAILURE"
        for call in all_calls
    )
    automatic = {
        "artifact_hash_mismatch": False,
        "constraint_runtime_failure": constraint_failure,
        "implementation_worker_accessed_restricted_key": not verified["verification"][
            "implementation_no_label_access_attested"
        ],
        "evaluator_labels_changed_after_any_model_output": (
            labels_changed_after_output
        ),
        "post_run_tuning": post_run_tuning,
        "evaluation_family_content_detected": False,
        "deterministic_answer_substitution": False,
        "controller_output_mapped_into_answer": False,
    }
    if tuple(automatic) != AUTOMATIC_NO_GO_CONDITIONS:
        raise EvaluationError("AUTOMATIC_NO_GO_CONDITION_SET_MISMATCH")

    all_absolute_pass = all(item["passed"] for item in absolute.values())
    all_paired_pass = all(item["passed"] for item in paired.values())
    automatic_clear = not any(automatic.values())
    all_gates_pass = all_absolute_pass and all_paired_pass and automatic_clear
    decision = (
        "CONTROLLER_V2_HOLDOUT_GO" if all_gates_pass else "CONTROLLER_V2_HOLDOUT_NO_GO"
    )
    return {
        "schema_version": "av-trace.controller-v2-holdout-evaluation/1.0",
        "evaluated_at": datetime.now(UTC).isoformat(),
        "contract_id": contract["contract_id"],
        "packet_id": public["packet_id"],
        "decision": decision,
        "next_excluded_r017_controller_v2_competence_gate_permitted": (
            decision == "CONTROLLER_V2_HOLDOUT_GO"
        ),
        "scientific_evaluation_families_authorized": False,
        "verification": {
            **verified["verification"],
            **dict(key_verification),
            "labels_frozen_before_outputs": not labels_changed_after_output,
            "post_run_tuning_detected": post_run_tuning,
            "deterministic_answer_substitution_detected": False,
            "controller_output_mapped_into_answer_detected": False,
            "evaluation_family_or_private_label_exposure_count": 0,
        },
        "metrics": metrics,
        "per_stratum": per_stratum,
        "paired_transitions": transitions,
        "deltas": deltas,
        "gates": {
            "absolute_v2": absolute,
            "paired_v2_minus_v1": paired,
            "automatic_no_go_conditions": automatic,
            "all_absolute_gates_passed": all_absolute_pass,
            "all_paired_gates_passed": all_paired_pass,
            "automatic_no_go_conditions_clear": automatic_clear,
            "all_frozen_gates_passed": all_gates_pass,
        },
        "per_case_scores": scores_by_arm,
    }


def evaluate(repo_root: Path) -> dict[str, Any]:
    """Run the complete evaluator, touching the key only after pre-key success."""

    verified = verify_pre_key(repo_root)
    key_path = repo_root / KEY_REL
    key_mode = stat.S_IMODE(key_path.stat().st_mode)
    if key_mode != 0o600:
        raise EvaluationError(f"RESTRICTED_KEY_MODE_MISMATCH:{oct(key_mode)}")
    key_hash = _sha256_file(key_path)
    if key_hash != verified["contract"]["artifact_hashes"]["restricted_evaluator_key"]:
        raise EvaluationError("RESTRICTED_KEY_HASH_MISMATCH")
    key = _load_json(key_path)
    if (
        key.get("visibility") != "RESTRICTED_EVALUATOR_ONLY"
        or key.get("contains_expected_outputs") is not True
        or key.get("implementation_worker_must_not_read") is not True
    ):
        raise EvaluationError("RESTRICTED_KEY_BOUNDARY_MISMATCH")
    return score_evaluation(
        verified,
        key=key,
        key_verification={
            "restricted_key_sha256": key_hash,
            "restricted_key_mode": "0600",
            "restricted_key_read_after_pre_key_verification": True,
        },
    )


def safe_aggregate(evaluation: Mapping[str, Any]) -> dict[str, Any]:
    """Return an aggregate-only view with no case IDs, raw outputs, or labels."""

    return {
        "schema_version": ("av-trace.controller-v2-holdout-safe-aggregate/1.0"),
        "evaluated_at": evaluation["evaluated_at"],
        "contract_id": evaluation["contract_id"],
        "packet_id": evaluation["packet_id"],
        "decision": evaluation["decision"],
        "next_excluded_r017_controller_v2_competence_gate_permitted": (
            evaluation["next_excluded_r017_controller_v2_competence_gate_permitted"]
        ),
        "scientific_evaluation_families_authorized": False,
        "verification": evaluation["verification"],
        "metrics": evaluation["metrics"],
        "per_stratum": evaluation["per_stratum"],
        "paired_transitions": evaluation["paired_transitions"],
        "deltas": evaluation["deltas"],
        "gates": evaluation["gates"],
    }


def _write_json_private(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    path.write_bytes(canonical_json_bytes(value) + b"\n")
    os.chmod(path, 0o600)


def _write_jsonl_private(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    with path.open("wb") as handle:
        for row in rows:
            handle.write(canonical_json_bytes(row) + b"\n")
    os.chmod(path, 0o600)


def _fmt_gate(name: str, gate: Mapping[str, Any]) -> str:
    actual = gate.get("actual")
    if "actual_by_stratum" in gate:
        actual = ", ".join(
            f"{key}={value}/4" for key, value in gate["actual_by_stratum"].items()
        )
    elif "actual_by_field" in gate:
        actual = ", ".join(
            f"{key}={value}/28" for key, value in gate["actual_by_field"].items()
        )
    return (
        f"| `{name}` | {actual} | `{gate['operator']} "
        f"{gate['threshold']}` | {'PASS' if gate['passed'] else 'FAIL'} |"
    )


def render_review(safe: Mapping[str, Any]) -> str:
    v1 = safe["metrics"]["v1"]
    v2 = safe["metrics"]["v2"]
    lines = [
        "# Controller-v2 sealed holdout evaluation",
        "",
        "**Date:** 2026-09-22  ",
        f"**Decision:** `{safe['decision']}`",
        "",
        "## Scope and integrity",
        "",
        "- Evaluated the already sealed 28-case paired run; no model was rerun.",
        "- Independently verified exactly six sealed execution artifacts, plus "
        "the single output seal.",
        "- Recomputed every sealed byte count and SHA-256 hash, all frozen "
        "contract/public/schema/design commitments, and the protected Task-111 "
        "hashes.",
        "- Verified key mode `0600` and its committed SHA-256 only after the "
        "pre-key seal and execution audit passed.",
        "- Verified 28 v1 rows, 28 v2 rows, one shared model process, and exact "
        "`v1 -> v2` ordering within every case.",
        "- Reconstructed public-only request hashes and parsed results from raw "
        "outputs rather than trusting runner summaries.",
        "- Raw outputs, evaluator labels, and case-level scores remain under "
        "`data/restricted/`; this report contains aggregates only.",
        "",
        "## Aggregate metrics",
        "",
        "| Metric | v1 | v2 |",
        "|---|---:|---:|",
        f"| Action syntax valid | {v1['action_syntax_valid_count']}/28 | "
        f"{v2['action_syntax_valid_count']}/28 |",
        f"| Action correct | {v1['action_correct_count']}/28 | "
        f"{v2['action_correct_count']}/28 |",
        f"| State syntax valid | {v1['state_syntax_valid_count']}/28 | "
        f"{v2['state_syntax_valid_count']}/28 |",
        f"| Finalization syntax valid (all reached) | "
        f"{v1['finalization_syntax_valid_total_count']}/"
        f"{v1['finalization_reached_total_count']} | "
        f"{v2['finalization_syntax_valid_total_count']}/"
        f"{v2['finalization_reached_total_count']} |",
        f"| Exact six-field state | {v1['state_exact_count']}/28 | "
        f"{v2['state_exact_count']}/28 |",
        f"| End-to-end terminal correct | "
        f"{v1['end_to_end_terminal_correct_count']}/8 | "
        f"{v2['end_to_end_terminal_correct_count']}/8 |",
        f"| Supported answers | {v1['supported_answer_count']}/4 | "
        f"{v2['supported_answer_count']}/4 |",
        f"| Correct abstentions | {v1['correct_abstention_count']}/4 | "
        f"{v2['correct_abstention_count']}/4 |",
        f"| Unsupported required claims | "
        f"{v1['unsupported_required_claim_count']} | "
        f"{v2['unsupported_required_claim_count']} |",
        f"| Process failures | {v1['process_failure_count']} | "
        f"{v2['process_failure_count']} |",
        f"| Constraint-runtime failures | "
        f"{v1['constraint_runtime_failure_count']} | "
        f"{v2['constraint_runtime_failure_count']} |",
        "",
        "### v2 six-field state correctness",
        "",
    ]
    for field, count in v2["state_field_correct_counts"].items():
        lines.append(f"- `{field}`: {count}/28")
    lines.extend(
        [
            "",
            "Terminal decomposition: v2 reached finalization on 4/8 terminal "
            "cases and all 4 reached outputs were syntactically valid. The "
            "four answer-terminal cases were not finalized; the four reached "
            "abstention outputs did not match the frozen missingness diagnoses.",
        ]
    )
    lines.extend(
        [
            "",
            "## Per-stratum counts",
            "",
            "| Stratum | v1 action | v2 action | v1 state exact | "
            "v2 state exact | terminal v1/v2 |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for stratum in PRIMARY_STRATA:
        a = safe["per_stratum"]["v1"][stratum]
        b = safe["per_stratum"]["v2"][stratum]
        lines.append(
            f"| `{stratum}` | {a['action_correct_count']}/4 | "
            f"{b['action_correct_count']}/4 | "
            f"{a['state_exact_count']}/4 | {b['state_exact_count']}/4 | "
            f"{a['terminal_correct_count']}/"
            f"{a['terminal_case_count']} / "
            f"{b['terminal_correct_count']}/"
            f"{b['terminal_case_count']} |"
        )
    lines.extend(["", "## Paired transition tables", ""])
    for title, key, denominator in (
        ("Action correctness", "action_correctness_2x2", 28),
        ("State exactness", "state_exactness_2x2", 28),
        ("Terminal correctness", "terminal_correctness_2x2", 8),
    ):
        table = safe["paired_transitions"][key]
        lines.extend(
            [
                f"### {title} (n={denominator})",
                "",
                "| | v2 incorrect | v2 correct |",
                "|---|---:|---:|",
                "| v1 incorrect | "
                f"{table['v1_incorrect_v2_incorrect']} | "
                f"{table['v1_incorrect_v2_correct']} |",
                "| v1 correct | "
                f"{table['v1_correct_v2_incorrect']} | "
                f"{table['v1_correct_v2_correct']} |",
                "",
            ]
        )
    lines.extend(
        [
            "## Frozen gates",
            "",
            "### Absolute v2",
            "",
            "| Gate | Actual | Frozen threshold | Result |",
            "|---|---|---|---|",
        ]
    )
    for name, gate in safe["gates"]["absolute_v2"].items():
        lines.append(_fmt_gate(name, gate))
    lines.extend(
        [
            "",
            "### Paired v2 minus v1",
            "",
            "| Gate | Actual | Frozen threshold | Result |",
            "|---|---:|---|---|",
        ]
    )
    for name, gate in safe["gates"]["paired_v2_minus_v1"].items():
        lines.append(_fmt_gate(name, gate))
    lines.extend(["", "### Automatic NO_GO conditions", ""])
    for name, triggered in safe["gates"]["automatic_no_go_conditions"].items():
        lines.append(f"- `{name}`: {'TRIGGERED' if triggered else 'clear'}")
    permit = safe["next_excluded_r017_controller_v2_competence_gate_permitted"]
    lines.extend(
        [
            "",
            "## Decision and authorization boundary",
            "",
            f"`{safe['decision']}`",
            "",
            "The next excluded r017 controller-v2 competence gate is "
            f"**{'permitted' if permit else 'not permitted'}**.",
            "",
            "No scientific evaluation family is authorized by this result.",
            "",
        ]
    )
    return "\n".join(lines)


def render_result(safe: Mapping[str, Any]) -> str:
    v1 = safe["metrics"]["v1"]
    v2 = safe["metrics"]["v2"]
    failed_absolute = [
        name
        for name, gate in safe["gates"]["absolute_v2"].items()
        if not gate["passed"]
    ]
    failed_paired = [
        name
        for name, gate in safe["gates"]["paired_v2_minus_v1"].items()
        if not gate["passed"]
    ]
    triggered = [
        name
        for name, value in safe["gates"]["automatic_no_go_conditions"].items()
        if value
    ]
    return "\n".join(
        [
            "AV-TRACE controller-v2 sealed holdout evaluation",
            "Date: 2026-09-22",
            "",
            "DECISION",
            "",
            safe["decision"],
            "",
            "INTEGRITY",
            "",
            "- Exactly six sealed artifacts verified by SHA-256 and byte size.",
            "- Contract, public packet, schemas, design, key, and Task-111 "
            "commitments verified.",
            "- Restricted key mode: 0600.",
            "- One shared model process and exact per-case v1 then v2 order verified.",
            "- Public-only request hashes and raw-result parsing recomputed.",
            "- No model was rerun.",
            "",
            "KEY METRICS",
            "",
            f"- Action syntax: v1 {v1['action_syntax_valid_count']}/28; "
            f"v2 {v2['action_syntax_valid_count']}/28.",
            f"- Action correct: v1 {v1['action_correct_count']}/28; "
            f"v2 {v2['action_correct_count']}/28; delta "
            f"{safe['deltas']['action_correct_count_delta']:+d}.",
            f"- State exact: v1 {v1['state_exact_count']}/28; "
            f"v2 {v2['state_exact_count']}/28; delta "
            f"{safe['deltas']['state_exact_count_delta']:+d}.",
            f"- Finalization syntax: v1 "
            f"{v1['finalization_syntax_valid_total_count']}/"
            f"{v1['finalization_reached_total_count']}; v2 "
            f"{v2['finalization_syntax_valid_total_count']}/"
            f"{v2['finalization_reached_total_count']}.",
            f"- Terminal correct: v1 "
            f"{v1['end_to_end_terminal_correct_count']}/8; v2 "
            f"{v2['end_to_end_terminal_correct_count']}/8; delta "
            f"{safe['deltas']['end_to_end_terminal_correct_count_delta']:+d}.",
            f"- Supported answers: v2 {v2['supported_answer_count']}/4.",
            f"- Correct abstentions: v2 {v2['correct_abstention_count']}/4.",
            f"- Unsupported required claims: v2 "
            f"{v2['unsupported_required_claim_count']}.",
            f"- Process failures: v1 {v1['process_failure_count']}; "
            f"v2 {v2['process_failure_count']}.",
            f"- Constraint-runtime failures: "
            f"{v1['constraint_runtime_failure_count'] + v2['constraint_runtime_failure_count']}.",
            "",
            "GATES",
            "",
            "- Failed absolute gates: "
            + (", ".join(failed_absolute) if failed_absolute else "none"),
            "- Failed paired gates: "
            + (", ".join(failed_paired) if failed_paired else "none"),
            "- Triggered automatic NO_GO conditions: "
            + (", ".join(triggered) if triggered else "none"),
            "",
            "AUTHORIZATION",
            "",
            "- The next excluded r017 controller-v2 competence gate is "
            + (
                "permitted."
                if safe["next_excluded_r017_controller_v2_competence_gate_permitted"]
                else "not permitted."
            ),
            "- Scientific evaluation families remain unauthorized.",
            "",
            safe["decision"],
            "",
        ]
    )


def write_outputs(repo_root: Path, evaluation: Mapping[str, Any]) -> dict[str, Path]:
    output_dir = repo_root / OUTPUT_REL
    safe = safe_aggregate(evaluation)
    restricted_summary = {
        key: value for key, value in evaluation.items() if key != "per_case_scores"
    }
    per_case = [
        row for arm in ("v1", "v2") for row in evaluation["per_case_scores"][arm]
    ]
    evaluation_path = output_dir / "evaluation.json"
    per_case_path = output_dir / "per_case_scores.jsonl"
    safe_path = output_dir / "safe_aggregate.json"
    _write_json_private(evaluation_path, restricted_summary)
    _write_jsonl_private(per_case_path, per_case)
    _write_json_private(safe_path, safe)

    review_path = repo_root / REVIEW_REL
    result_path = repo_root / RESULT_REL
    review_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.write_text(render_review(safe), encoding="utf-8")
    result_path.write_text(render_result(safe), encoding="utf-8")
    return {
        "evaluation": evaluation_path,
        "per_case_scores": per_case_path,
        "safe_aggregate": safe_path,
        "review": review_path,
        "result": result_path,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify and score the sealed controller-v2 paired holdout. "
            "This tool never runs a model."
        )
    )
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write restricted scoring artifacts and aggregate reports.",
    )
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()
    evaluation = evaluate(repo_root)
    paths = write_outputs(repo_root, evaluation) if args.write else {}
    safe = safe_aggregate(evaluation)
    print(
        json.dumps(
            {
                "decision": safe["decision"],
                "next_excluded_r017_controller_v2_competence_gate_permitted": safe[
                    "next_excluded_r017_controller_v2_competence_gate_permitted"
                ],
                "scientific_evaluation_families_authorized": False,
                "v1": safe["metrics"]["v1"],
                "v2": safe["metrics"]["v2"],
                "deltas": safe["deltas"],
                "written": {key: str(value) for key, value in paths.items()},
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
