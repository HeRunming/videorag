"""Consumed development suite and competence evaluation for controller v3."""

from __future__ import annotations

import hashlib
import json
import os
import random
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from av_trace_scale1b_agent.competence import synthetic_competence_contract

from .controller import STATE_HEADS, ControllerV3Config, execute_v3_case
from .process import ConstrainedQwenProcess, ProcessConfig
from .prompts import ACTION_SYSTEM_PROMPT, STATE_SYSTEM_PROMPTS
from .schemas import canonical_json_bytes

SCHEMA_VERSION = "av-trace.controller-v3-development/3.0"
OUTPUT_DIR = Path("data/restricted/scale1b/controller_v3_dev")
DESIGN_PATH = Path("docs/design/controller_v3_factorized_state.md")
ORCHESTRATION_REPORT = Path(
    "orchestration/results/121_controller_v3_development.txt"
)
MODEL_REPO_ID = "Qwen/Qwen2.5-7B-Instruct"
MODEL_REVISION = "a09a35458c702b33eeacc393d103063234e8bc28"
MODEL_SNAPSHOT = Path(
    "data/restricted/scale1b/models/"
    "Qwen--Qwen2.5-7B-Instruct--a09a35458c70"
)
MODEL_MANIFEST = Path(
    "data/restricted/scale1b/manifests/"
    "strong_controller_model_acquisition.json"
)
TASK111_CONTRACT_HASH = (
    "sha256:b0f280487b936d82e14b118c16eb07ab1f4e189a74efe1000177487221002091"
)
GATES = {
    "all_head_syntax": 1.0,
    "action_accuracy": 0.80,
    "each_state_head_accuracy": 0.75,
    "joint_state_accuracy": 0.50,
    "terminal_accuracy": 0.75,
    "unsupported_required_claims": 0,
}
P_CHOICES: list[Any] = [0.0, 0.25, 0.5, 0.75, 1.0]
CAUSE_CHOICES: list[Any] = [
    "source_evidence_absent",
    "evidence_in_source_but_inaccessible",
    "evidence_accessible_but_not_found",
    "not_missing",
    "uncertain",
]
RECOVERY_CHOICES: list[Any] = [
    "none",
    "search_vision",
    "search_speech",
    "search_ambient",
    "observe_pointer",
    "check_channel_status",
    "retry_restored_route",
    "finalize_answer",
    "finalize_abstain",
]
MODALITY_CHOICES: list[Any] = [
    [],
    ["vision"],
    ["speech"],
    ["ambient"],
    ["vision", "speech"],
    ["vision", "ambient"],
    ["speech", "ambient"],
    ["vision", "speech", "ambient"],
]
HOP_NAMES = [
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
]
HOP_CHOICES: list[Any] = [[], *[[name] for name in HOP_NAMES]]
TOOL_COSTS = {
    "search_visual": 1.0,
    "search_speech": 1.0,
    "search_ambient_audio": 1.0,
    "inspect_clip": 2.0,
    "read_transcript": 1.0,
    "get_channel_status": 0.25,
    "finalize": 0.0,
}


def _semantic_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _budget(steps: int = 5, cost: float = 5.0) -> dict[str, Any]:
    return {"steps": steps, "cost": cost, "tool_costs": dict(TOOL_COSTS)}


def _shuffled(values: Sequence[Any], *, case_id: str, head: str) -> list[Any]:
    copied = json.loads(json.dumps(list(values)))
    seed_bytes = hashlib.sha256(f"{case_id}:{head}:v3".encode()).digest()[:8]
    random.Random(int.from_bytes(seed_bytes)).shuffle(copied)
    return copied


def _covered_choices(handles: list[str]) -> list[Any]:
    choices: list[list[str]] = [[]]
    for handle in handles:
        choices.extend([existing + [handle] for existing in list(choices)])
    return choices


def _state_choices(case_id: str, handles: list[str]) -> dict[str, list[Any]]:
    values = {
        "p_sufficient": P_CHOICES,
        "covered_claim_handles": _covered_choices(handles),
        "missing_modalities": MODALITY_CHOICES,
        "missing_hops": HOP_CHOICES,
        "missingness_cause": CAUSE_CHOICES,
        "recovery_intent": RECOVERY_CHOICES,
    }
    return {
        head: _shuffled(options, case_id=case_id, head=head)
        for head, options in values.items()
    }


def _action_index(
    menu: Sequence[Mapping[str, Any]], expected: Mapping[str, Any]
) -> int:
    matches = []
    for index, action in enumerate(menu):
        if action.get("type") != expected["action_type"]:
            continue
        if all(
            action.get(key) == expected[key]
            for key in ("modality", "pointer_id", "modalities")
            if key in expected
        ):
            matches.append(index)
    if len(matches) != 1:
        raise RuntimeError(f"AMBIGUOUS_EXPECTED_ACTION:{matches}")
    return matches[0]


def _controller_state_labels() -> dict[str, dict[str, Any]]:
    return {
        "dev-route-speech": {
            "p_sufficient": 0.0,
            "covered_claim_handles": [],
            "missing_modalities": ["speech"],
            "missing_hops": ["speech_content"],
            "missingness_cause": "evidence_accessible_but_not_found",
            "recovery_intent": "search_speech",
        },
        "dev-route-vision": {
            "p_sufficient": 0.0,
            "covered_claim_handles": [],
            "missing_modalities": ["vision"],
            "missing_hops": ["entity_identity"],
            "missingness_cause": "evidence_accessible_but_not_found",
            "recovery_intent": "search_vision",
        },
        "dev-route-ambient": {
            "p_sufficient": 0.0,
            "covered_claim_handles": [],
            "missing_modalities": ["ambient"],
            "missing_hops": ["ambient_event"],
            "missingness_cause": "evidence_accessible_but_not_found",
            "recovery_intent": "search_ambient",
        },
        "dev-inspect-visual-pointer": {
            "p_sufficient": 0.0,
            "covered_claim_handles": [],
            "missing_modalities": ["vision"],
            "missing_hops": ["entity_identity"],
            "missingness_cause": "evidence_accessible_but_not_found",
            "recovery_intent": "observe_pointer",
        },
        "dev-read-speech-pointer": {
            "p_sufficient": 0.0,
            "covered_claim_handles": [],
            "missing_modalities": ["speech"],
            "missing_hops": ["speech_content"],
            "missingness_cause": "evidence_accessible_but_not_found",
            "recovery_intent": "observe_pointer",
        },
        "dev-claim-coverage-finalize": {
            "p_sufficient": 1.0,
            "covered_claim_handles": ["devslot.color", "devslot.code"],
            "missing_modalities": [],
            "missing_hops": [],
            "missingness_cause": "not_missing",
            "recovery_intent": "finalize_answer",
        },
        "dev-no-progress-repeat-guard": {
            "p_sufficient": 0.0,
            "covered_claim_handles": [],
            "missing_modalities": ["vision"],
            "missing_hops": ["entity_identity"],
            "missingness_cause": "evidence_accessible_but_not_found",
            "recovery_intent": "observe_pointer",
        },
        "dev-missing-hop-diagnosis": {
            "p_sufficient": 0.0,
            "covered_claim_handles": [],
            "missing_modalities": [],
            "missing_hops": ["temporal_order"],
            "missingness_cause": "uncertain",
            "recovery_intent": "finalize_abstain",
        },
        "dev-blocked-route-status": {
            "p_sufficient": 0.0,
            "covered_claim_handles": [],
            "missing_modalities": ["speech"],
            "missing_hops": ["speech_content"],
            "missingness_cause": "evidence_in_source_but_inaccessible",
            "recovery_intent": "check_channel_status",
        },
        "dev-restored-route-search": {
            "p_sufficient": 0.0,
            "covered_claim_handles": [],
            "missing_modalities": ["speech"],
            "missing_hops": ["speech_content"],
            "missingness_cause": "evidence_accessible_but_not_found",
            "recovery_intent": "retry_restored_route",
        },
    }


def _generator_state(case: Mapping[str, Any]) -> dict[str, Any]:
    handles = [slot["claim_handle"] for slot in case["claim_slots"]]
    if case["oracle_evidence"]:
        return {
            "p_sufficient": 1.0,
            "covered_claim_handles": handles,
            "missing_modalities": [],
            "missing_hops": [],
            "missingness_cause": "not_missing",
            "recovery_intent": "finalize_answer",
        }
    return {
        "p_sufficient": 0.0,
        "covered_claim_handles": [],
        "missing_modalities": (
            [case["expect_missing_modality"]]
            if case.get("expect_missing_modality")
            else []
        ),
        "missing_hops": (
            [case["expect_missing_hop"]]
            if case.get("expect_missing_hop")
            else []
        ),
        "missingness_cause": "uncertain",
        "recovery_intent": "finalize_abstain",
    }


def controller_v3_development_contract() -> dict[str, Any]:
    """Build the consumed suite solely from the original Task-111 suite."""

    source = synthetic_competence_contract()
    if source["contract_hash"] != TASK111_CONTRACT_HASH:
        raise RuntimeError("TASK111_CONTRACT_HASH_CHANGED")
    labels = _controller_state_labels()
    cases: list[dict[str, Any]] = []
    for original in source["controller_cases"]:
        case_id = original["case_id"]
        handles = [slot["claim_handle"] for slot in original["claim_slots"]]
        expected_action_index = _action_index(
            original["action_menu"], original["expect"]
        )
        terminal = (
            original["action_menu"][expected_action_index]["type"] == "finalize"
        )
        terminal_expectation = None
        if case_id == "dev-claim-coverage-finalize":
            terminal_expectation = {
                "kind": "answer",
                "allowed_verdicts": ["answer"],
                "oracle_support": {
                    "devslot.color": ["devobs.combo-A"],
                    "devslot.code": ["devobs.combo-A"],
                },
                "required_terms": {
                    "devslot.color": ["violet"],
                    "devslot.code": ["maple"],
                },
            }
        elif case_id == "dev-missing-hop-diagnosis":
            terminal_expectation = {
                "kind": "abstain",
                "allowed_verdicts": [
                    "insufficient",
                    "access_failure",
                    "abstain",
                ],
                "missing_modalities": [],
                "missing_hops": ["temporal_order"],
            }
        case = {
            "case_id": case_id,
            "source": "TASK_111_CONSUMED_DEVELOPMENT",
            "consumed": True,
            "capabilities": original["capabilities"],
            "policy": original["policy"],
            "question": original["question"],
            "public_claim_slots": original["claim_slots"],
            "known_pointers": original["known_pointers"],
            "citable_observations": original["citable_observations"],
            "recent_public_events": original["recent_public_events"],
            "no_progress_rounds": original["no_progress_rounds"],
            "remaining_budget": original.get("remaining_budget", _budget()),
            "action_menu": original["action_menu"],
            "state_choice_enums": _state_choices(case_id, handles),
            "development_labels": {
                "action_index": expected_action_index,
                "state": labels[case_id],
                "terminal": terminal_expectation,
            },
            "terminal_case": terminal,
        }
        cases.append(case)
    for original in source["generator_cases"]:
        case_id = original["case_id"]
        handles = [slot["claim_handle"] for slot in original["claim_slots"]]
        state = _generator_state(original)
        cases.append(
            {
                "case_id": case_id,
                "source": "TASK_111_CONSUMED_DEVELOPMENT",
                "consumed": True,
                "capabilities": original["capabilities"],
                "policy": "evidence_sufficiency",
                "question": original["question"],
                "public_claim_slots": original["claim_slots"],
                "known_pointers": [],
                "citable_observations": original["observations"],
                "recent_public_events": [],
                "no_progress_rounds": 2,
                "remaining_budget": _budget(1, 0.0),
                "action_menu": [{"type": "finalize"}],
                "state_choice_enums": _state_choices(case_id, handles),
                "development_labels": {
                    "action_index": 0,
                    "state": state,
                    "terminal": {
                        "kind": (
                            "answer"
                            if original["oracle_evidence"]
                            else "abstain"
                        ),
                        "allowed_verdicts": original["expect_verdicts"],
                        "oracle_support": original["oracle_support"],
                        "required_terms": original["required_terms"],
                        "missing_modalities": (
                            [original["expect_missing_modality"]]
                            if original.get("expect_missing_modality")
                            else []
                        ),
                        "missing_hops": (
                            [original["expect_missing_hop"]]
                            if original.get("expect_missing_hop")
                            else []
                        ),
                    },
                },
                "terminal_case": True,
            }
        )
    contract = {
        "schema_version": SCHEMA_VERSION,
        "development_only": True,
        "consumed": True,
        "scientific_evaluation_eligible": False,
        "source_suite": "Task-111 synthetic development suite",
        "source_contract_hash": source["contract_hash"],
        "v2_holdout_consumed_for_tuning": False,
        "v2_restricted_evaluator_key_read": False,
        "v2_per_case_labels_read": False,
        "evaluation_family_content": False,
        "noaa_content": False,
        "r017_content": False,
        "model_authorship": {
            "action": True,
            "state_heads": list(STATE_HEADS),
            "finalizer": True,
            "deterministic_semantic_filling": False,
            "answer_mapping": False,
        },
        "competence_gates": GATES,
        "model": {
            "repo_id": MODEL_REPO_ID,
            "revision": MODEL_REVISION,
            "snapshot_dir": str(MODEL_SNAPSHOT),
        },
        "cases": cases,
    }
    contract["contract_hash"] = _semantic_hash(contract)
    return contract


def _terminal_score(
    expected: Mapping[str, Any], final: Mapping[str, Any] | None
) -> tuple[bool, int, list[str]]:
    if final is None:
        return False, 0, ["FINALIZER_NOT_VALID"]
    errors: list[str] = []
    unsupported = 0
    if final.get("verdict") not in expected["allowed_verdicts"]:
        errors.append("WRONG_VERDICT")
    if expected["kind"] == "answer":
        assertions = {
            row.get("claim_handle"): row
            for row in final.get("asserted_claims", [])
            if isinstance(row, Mapping)
        }
        for handle, allowed in expected["oracle_support"].items():
            assertion = assertions.get(handle)
            if assertion is None:
                errors.append(f"MISSING_REQUIRED_CLAIM:{handle}")
                continue
            citations = assertion.get("citations", [])
            if not citations or not set(citations) <= set(allowed):
                unsupported += 1
                errors.append(f"UNSUPPORTED_REQUIRED_CLAIM:{handle}")
            content = (
                str(assertion.get("text", ""))
                + " "
                + str(final.get("answer_text", ""))
            ).casefold()
            if not any(
                term.casefold() in content
                for term in expected["required_terms"].get(handle, [])
            ):
                errors.append(f"REQUIRED_CONTENT_MISSING:{handle}")
    else:
        assertions = final.get("asserted_claims", [])
        if assertions:
            unsupported += len(assertions)
            errors.append("NONANSWER_ASSERTED_CLAIMS")
        if final.get("answer_text"):
            errors.append("NONANSWER_HAS_ANSWER_TEXT")
        for field in ("missing_modalities", "missing_hops"):
            if set(final.get(field, [])) != set(expected.get(field, [])):
                errors.append(f"WRONG_{field.upper()}")
    return not errors, unsupported, errors


def evaluate_results(
    contract: Mapping[str, Any], raw_results: Sequence[Mapping[str, Any]]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Score syntax, semantics, terminal behavior, and resource use."""

    case_by_id = {case["case_id"]: case for case in contract["cases"]}
    results: list[dict[str, Any]] = []
    head_syntax = {head: 0 for head in STATE_HEADS}
    head_semantic = {head: 0 for head in STATE_HEADS}
    action_syntax = 0
    action_correct = 0
    joint_state = 0
    terminal_correct = 0
    terminal_count = 0
    supported_answers = 0
    answer_count = 0
    correct_abstentions = 0
    abstain_count = 0
    unsupported = 0
    finalizer_reached = 0
    finalization_syntax_valid = 0
    calls = 0
    calls_by_phase: dict[str, int] = {}
    prompt_tokens = 0
    generated_tokens = 0
    latency_seconds = 0.0
    selected_tool_cost = 0.0
    for raw in raw_results:
        case = case_by_id[raw["case_id"]]
        expected = case["development_labels"]
        action_ok = (
            raw.get("selected_action_index") == expected["action_index"]
        )
        action_syntax += int(bool(raw.get("action_syntax_valid")))
        action_correct += int(action_ok)
        field_scores = {}
        for head in STATE_HEADS:
            actual = raw["state_heads"][head]
            syntax_ok = bool(actual["syntax_valid"])
            semantic_ok = syntax_ok and (
                actual["value"] == expected["state"][head]
            )
            head_syntax[head] += int(syntax_ok)
            head_semantic[head] += int(semantic_ok)
            field_scores[head] = semantic_ok
        joint_ok = all(field_scores.values())
        joint_state += int(joint_ok)
        terminal_ok = None
        terminal_errors: list[str] = []
        case_unsupported = 0
        if case["terminal_case"]:
            terminal_count += 1
            terminal_expected = expected["terminal"]
            if terminal_expected["kind"] == "answer":
                answer_count += 1
            else:
                abstain_count += 1
            if action_ok and raw.get("finalizer_called"):
                finalizer_reached += 1
                finalization_syntax_valid += int(raw.get("final") is not None)
                terminal_ok, case_unsupported, terminal_errors = _terminal_score(
                    terminal_expected, raw.get("final")
                )
            else:
                terminal_ok = False
                terminal_errors = ["EXPECTED_FINALIZE_NOT_SELECTED"]
            terminal_correct += int(terminal_ok)
            if terminal_expected["kind"] == "answer":
                supported_answers += int(terminal_ok)
            else:
                correct_abstentions += int(terminal_ok)
            unsupported += case_unsupported
        action = raw.get("dispatched_action") or {}
        kind = action.get("type")
        if kind == "search":
            tool = {
                "vision": "search_visual",
                "speech": "search_speech",
                "ambient": "search_ambient_audio",
            }.get(action.get("modality"))
        elif kind == "observe":
            pointers = {
                row["pointer_id"]: row for row in case["known_pointers"]
            }
            pointer = pointers.get(action.get("pointer_id"), {})
            tool = (
                "read_transcript"
                if pointer.get("modality") == "speech"
                else "inspect_clip"
            )
        elif kind == "status":
            tool = "get_channel_status"
        else:
            tool = "finalize"
        selected_tool_cost += TOOL_COSTS.get(tool, 0.0)
        for call in raw["model_calls"]:
            calls += 1
            phase = str(call.get("phase", "unknown"))
            calls_by_phase[phase] = calls_by_phase.get(phase, 0) + 1
            prompt_tokens += int(call.get("prompt_tokens") or 0)
            generated_tokens += int(call.get("generated_tokens") or 0)
            latency_seconds += float(call.get("latency_seconds") or 0.0)
        results.append(
            {
                **raw,
                "development_score": {
                    "action_correct": action_ok,
                    "state_head_correct": field_scores,
                    "joint_state_correct": joint_ok,
                    "terminal_correct": terminal_ok,
                    "terminal_errors": terminal_errors,
                    "unsupported_required_claims": case_unsupported,
                },
            }
        )
    count = len(contract["cases"])
    head_syntax_rates = {
        head: head_syntax[head] / count for head in STATE_HEADS
    }
    head_semantic_rates = {
        head: head_semantic[head] / count for head in STATE_HEADS
    }
    rates = {
        "action_syntax": action_syntax / count,
        "action_accuracy": action_correct / count,
        "joint_state_accuracy": joint_state / count,
        "terminal_accuracy": (
            terminal_correct / terminal_count if terminal_count else 0.0
        ),
    }
    gate_results = {
        "all_head_syntax": (
            rates["action_syntax"] == GATES["all_head_syntax"]
            and all(
                rate == GATES["all_head_syntax"]
                for rate in head_syntax_rates.values()
            )
        ),
        "action_accuracy": (
            rates["action_accuracy"] >= GATES["action_accuracy"]
        ),
        "each_state_head_accuracy": all(
            rate >= GATES["each_state_head_accuracy"]
            for rate in head_semantic_rates.values()
        ),
        "joint_state_accuracy": (
            rates["joint_state_accuracy"] >= GATES["joint_state_accuracy"]
        ),
        "terminal_accuracy": (
            rates["terminal_accuracy"] >= GATES["terminal_accuracy"]
        ),
        "unsupported_required_claims": (
            unsupported == GATES["unsupported_required_claims"]
        ),
    }
    metrics = {
        "case_count": count,
        "action_syntax_valid": {
            "count": action_syntax,
            "total": count,
            "rate": rates["action_syntax"],
        },
        "action_correct": {
            "count": action_correct,
            "total": count,
            "rate": rates["action_accuracy"],
        },
        "state_head_syntax": {
            head: {
                "count": head_syntax[head],
                "total": count,
                "rate": head_syntax_rates[head],
            }
            for head in STATE_HEADS
        },
        "state_head_semantic": {
            head: {
                "count": head_semantic[head],
                "total": count,
                "rate": head_semantic_rates[head],
            }
            for head in STATE_HEADS
        },
        "joint_state": {
            "count": joint_state,
            "total": count,
            "rate": rates["joint_state_accuracy"],
        },
        "terminal": {
            "finalizer_reached": finalizer_reached,
            "finalization_syntax_valid": finalization_syntax_valid,
            "correct": terminal_correct,
            "total": terminal_count,
            "rate": rates["terminal_accuracy"],
            "supported_answers": supported_answers,
            "answer_cases": answer_count,
            "correct_abstentions": correct_abstentions,
            "abstain_cases": abstain_count,
            "unsupported_required_claims": unsupported,
        },
        "cost_and_calls": {
            "model_calls": calls,
            "model_calls_by_phase": dict(sorted(calls_by_phase.items())),
            "prompt_tokens": prompt_tokens,
            "generated_tokens": generated_tokens,
            "total_tokens": prompt_tokens + generated_tokens,
            "summed_generation_latency_seconds": round(
                latency_seconds, 6
            ),
            "selected_public_tool_cost": selected_tool_cost,
        },
        "gates": gate_results,
        "decision": (
            "CONTROLLER_V3_DEV_READY"
            if all(gate_results.values())
            else "NO_GO"
        ),
    }
    return metrics, results


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    payload = json.dumps(
        value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False
    ).encode() + b"\n"
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(
                json.dumps(
                    row,
                    sort_keys=True,
                    ensure_ascii=False,
                    allow_nan=False,
                )
                + "\n"
            )
    os.chmod(path, 0o600)


def _verify_model(root: Path) -> Path:
    manifest = json.loads((root / MODEL_MANIFEST).read_text(encoding="utf-8"))
    candidate = manifest["candidate"]
    if (
        candidate.get("repo_id") != MODEL_REPO_ID
        or candidate.get("revision") != MODEL_REVISION
        or candidate.get("snapshot_dir") != str(MODEL_SNAPSHOT)
    ):
        raise RuntimeError("PINNED_QWEN_MANIFEST_MISMATCH")
    snapshot = root / MODEL_SNAPSHOT
    required = [
        "config.json",
        "tokenizer.json",
        "model.safetensors.index.json",
        "model-00001-of-00004.safetensors",
        "model-00002-of-00004.safetensors",
        "model-00003-of-00004.safetensors",
        "model-00004-of-00004.safetensors",
    ]
    if any(not (snapshot / name).is_file() for name in required):
        raise RuntimeError("PINNED_QWEN_SNAPSHOT_INCOMPLETE")
    return snapshot


def run_controller_v3_development(
    repo_root: str | Path = ".",
    *,
    startup_timeout_s: float = 240.0,
    generation_timeout_s: float = 180.0,
    threads: int = 8,
    prepare_only: bool = False,
) -> dict[str, Any]:
    """Run the consumed Task-111-derived v3 development competence suite."""

    root = Path(repo_root).resolve()
    contract = controller_v3_development_contract()
    output_dir = root / OUTPUT_DIR
    _write_json(output_dir / "suite_contract.json", contract)
    if prepare_only:
        return {"contract": contract, "prepared": True}
    snapshot = _verify_model(root)
    process_config = ProcessConfig(
        startup_timeout_s=startup_timeout_s,
        generation_timeout_s=generation_timeout_s,
        threads=threads,
        deny_network_namespace=True,
    )
    controller_config = ControllerV3Config()
    raw_results: list[dict[str, Any]] = []
    with ConstrainedQwenProcess(snapshot, config=process_config) as model:
        metadata = dict(model.metadata)
        if metadata.get("device") != "cpu":
            raise RuntimeError("QWEN_CONTROLLER_NOT_ON_CPU")
        if metadata.get("dtype") != "torch.bfloat16":
            raise RuntimeError("QWEN_CONTROLLER_NOT_BFLOAT16")
        if not metadata.get("network_namespace_denied"):
            raise RuntimeError("NETWORK_NAMESPACE_NOT_DENIED")
        for case in contract["cases"]:
            raw_results.append(
                execute_v3_case(model, case, config=controller_config)
            )
    metrics, results = evaluate_results(contract, raw_results)
    call_rows = [
        {
            "case_id": result["case_id"],
            **call,
        }
        for result in results
        for call in result["model_calls"]
    ]
    report = {
        "schema_version": SCHEMA_VERSION,
        "stage": "CONSUMED_SYNTHETIC_DEVELOPMENT_ONLY",
        "scientific_evaluation_eligible": False,
        "contract_hash": contract["contract_hash"],
        "source_contract_hash": TASK111_CONTRACT_HASH,
        "model": {
            "repo_id": MODEL_REPO_ID,
            "revision": MODEL_REVISION,
            "snapshot_dir": str(MODEL_SNAPSHOT),
            "offline": True,
            "local_files_only": True,
            "network_namespace_denied": True,
            "metadata": metadata,
        },
        "configuration": {
            "controller": asdict(controller_config),
            "process": asdict(process_config),
            "prompt_hashes": {
                "action": _semantic_hash(ACTION_SYSTEM_PROMPT),
                **{
                    head: _semantic_hash(prompt)
                    for head, prompt in STATE_SYSTEM_PROMPTS.items()
                },
            },
        },
        "integrity": {
            "v2_restricted_evaluator_key_read": False,
            "v2_per_case_evaluation_labels_read": False,
            "v2_holdout_tuned_on": False,
            "task111_source_only": True,
            "no_r017": True,
            "no_noaa": True,
            "no_evaluation_family": True,
            "deterministic_semantic_filling": False,
            "controller_output_mapped_into_answer": False,
            "strict_logging_boundary": True,
        },
        "safe_v2_aggregate_comparison": {
            "source": "docs/review/controller_v2_holdout_evaluation.md",
            "comparability": (
                "descriptive only: v3 uses consumed Task-111 development "
                "cases; v2 numbers are sealed unseen-holdout aggregates"
            ),
            "v2": {
                "action_syntax_valid": {"count": 28, "total": 28},
                "action_correct": {"count": 15, "total": 28},
                "state_syntax_valid": {"count": 28, "total": 28},
                "state_head_correct": {
                    "p_sufficient": {"count": 12, "total": 28},
                    "covered_claim_handles": {"count": 4, "total": 28},
                    "missing_modalities": {"count": 3, "total": 28},
                    "missing_hops": {"count": 3, "total": 28},
                    "missingness_cause": {"count": 2, "total": 28},
                    "recovery_intent": {"count": 9, "total": 28},
                },
                "joint_state": {"count": 0, "total": 28},
                "terminal": {"count": 0, "total": 8},
                "unsupported_required_claims": 0,
            },
        },
        "metrics": metrics,
        "results": results,
    }
    _write_json(output_dir / "results.json", report)
    _write_json(
        output_dir / "summary.json",
        {key: value for key, value in report.items() if key != "results"},
    )
    _write_jsonl(output_dir / "calls.jsonl", call_rows)
    return report
