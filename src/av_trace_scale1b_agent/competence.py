"""Synthetic-only competence suite for learned controller development.

The cases are fictional and self-contained. They intentionally contain no
evaluation-family content, identifiers, answers, timestamps, evidence text, or
private mappings.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .controller import (
    GenerationConfig,
    LearnedCallFailure,
    prompt_hashes,
    run_controller_decision,
    run_grounded_generator,
)
from .process import ProcessConfig, QwenProcess

SCHEMA_VERSION = "av-trace.scale1b.controller-synthetic-competence/1.0"
OUTPUT_DIR = Path("data/restricted/scale1b/controller_dev")
DOC_REPORT = Path("docs/review/controller_synthetic_competence.md")
ORCHESTRATION_REPORT = Path(
    "orchestration/results/111_controller_synthetic_competence.txt"
)
QWEN7B_OUTPUT_DIR = Path("data/restricted/scale1b/controller_dev_qwen7b")
QWEN7B_DOC_REPORT = Path(
    "docs/review/controller_capacity_sensitivity_qwen7b.md"
)
QWEN7B_ORCHESTRATION_REPORT = Path(
    "orchestration/results/114_qwen7b_synthetic_competence.txt"
)
STRUCTURED_OUTPUT_FLOOR = 0.90
SUPPORTED_ANSWER_FLOOR = 0.80
MAX_REPAIRS = 1
TASK111_CONTRACT_HASH = (
    "sha256:b0f280487b936d82e14b118c16eb07ab1f4e189a74efe1000177487221002091"
)

MODEL_SPECS = {
    "qwen1.5b": {
        "repo_id": "Qwen/Qwen2.5-1.5B-Instruct",
        "revision": "989aa7980e4cf806f80c7fef2b1adb7bc71aa306",
        "snapshot_dir": (
            "data/restricted/scale1b/models/"
            "Qwen--Qwen2.5-1.5B-Instruct--989aa7980e4c"
        ),
        "manifest": "data/restricted/scale1b/manifests/ga_model_acquisition.json",
        "manifest_section": "model",
        "output_dir": OUTPUT_DIR,
        "doc_report": DOC_REPORT,
        "orchestration_report": ORCHESTRATION_REPORT,
        "decision_prefix": "CONTROLLER_SYNTHETIC_COMPETENCE",
    },
    "qwen7b": {
        "repo_id": "Qwen/Qwen2.5-7B-Instruct",
        "revision": "a09a35458c702b33eeacc393d103063234e8bc28",
        "snapshot_dir": (
            "data/restricted/scale1b/models/"
            "Qwen--Qwen2.5-7B-Instruct--a09a35458c70"
        ),
        "manifest": (
            "data/restricted/scale1b/manifests/"
            "strong_controller_model_acquisition.json"
        ),
        "manifest_section": "candidate",
        "output_dir": QWEN7B_OUTPUT_DIR,
        "doc_report": QWEN7B_DOC_REPORT,
        "orchestration_report": QWEN7B_ORCHESTRATION_REPORT,
        "decision_prefix": "QWEN7B_CONTROLLER_SYNTHETIC_COMPETENCE",
    },
}

TOOLS = [
    "search_visual",
    "search_speech",
    "search_ambient_audio",
    "inspect_clip",
    "read_transcript",
    "get_channel_status",
    "finalize",
]
TOOL_COSTS = {
    "search_visual": 1.0,
    "search_speech": 1.0,
    "search_ambient_audio": 1.0,
    "inspect_clip": 2.0,
    "read_transcript": 1.0,
    "get_channel_status": 0.25,
    "finalize": 0.0,
}


def _slot(handle: str, description: str) -> dict[str, str]:
    return {"claim_handle": handle, "description": description}


def _pointer(pointer_id: str, modality: str, preview: str) -> dict[str, Any]:
    return {
        "pointer_id": pointer_id,
        "modality": modality,
        "preview": preview,
    }


def _observation(
    observation_id: str,
    modality: str,
    content: str,
    *,
    pointer_id: str | None = None,
) -> dict[str, Any]:
    result = {
        "observation_id": observation_id,
        "modality": modality,
        "content": content,
        "citable": True,
    }
    if pointer_id is not None:
        result["source_pointer_id"] = pointer_id
    return result


def _budget(steps: int = 5, cost: float = 5.0) -> dict[str, Any]:
    return {"steps": steps, "cost": cost, "tool_costs": dict(TOOL_COSTS)}


def synthetic_competence_contract() -> dict[str, Any]:
    """Return the preregistered, synthetic-only competence contract."""

    controller_cases = [
        {
            "case_id": "dev-route-speech",
            "capabilities": ["initial_modality_routing"],
            "policy": "evidence_sufficiency",
            "question": "Which word does the narrator say?",
            "claim_slots": [_slot("devslot.word", "The spoken word.")],
            "known_pointers": [],
            "citable_observations": [],
            "recent_public_events": [],
            "no_progress_rounds": 0,
            "action_menu": [
                {"type": "search", "modality": "vision", "query": "visible word", "top_k": 3},
                {"type": "search", "modality": "speech", "query": "narrator word", "top_k": 3},
                {"type": "search", "modality": "ambient", "query": "background sound", "top_k": 3},
            ],
            "expect": {"action_type": "search", "modality": "speech"},
        },
        {
            "case_id": "dev-route-vision",
            "capabilities": ["initial_modality_routing"],
            "policy": "react",
            "question": "What color is the token shown in the tray?",
            "claim_slots": [_slot("devslot.color", "The visible token color.")],
            "known_pointers": [],
            "citable_observations": [],
            "recent_public_events": [],
            "no_progress_rounds": 0,
            "action_menu": [
                {"type": "search", "modality": "speech", "query": "spoken color", "top_k": 3},
                {"type": "search", "modality": "ambient", "query": "color sound", "top_k": 3},
                {"type": "search", "modality": "vision", "query": "token color tray", "top_k": 3},
            ],
            "expect": {"action_type": "search", "modality": "vision"},
        },
        {
            "case_id": "dev-route-ambient",
            "capabilities": ["initial_modality_routing"],
            "policy": "evidence_sufficiency",
            "question": "Which sound is heard after the lid closes?",
            "claim_slots": [_slot("devslot.sound", "The audible event.")],
            "known_pointers": [],
            "citable_observations": [],
            "recent_public_events": [],
            "no_progress_rounds": 0,
            "action_menu": [
                {"type": "search", "modality": "ambient", "query": "sound after lid closes", "top_k": 3},
                {"type": "search", "modality": "vision", "query": "lid closes", "top_k": 3},
                {"type": "search", "modality": "speech", "query": "description of sound", "top_k": 3},
            ],
            "expect": {"action_type": "search", "modality": "ambient"},
        },
        {
            "case_id": "dev-inspect-visual-pointer",
            "capabilities": ["inspect_read"],
            "policy": "react",
            "question": "What shape is shown?",
            "claim_slots": [_slot("devslot.shape", "The visible shape.")],
            "known_pointers": [
                _pointer("devptr.visual-1", "vision", "A candidate view of the object.")
            ],
            "citable_observations": [],
            "recent_public_events": [],
            "no_progress_rounds": 0,
            "action_menu": [
                {"type": "search", "modality": "vision", "query": "shape", "top_k": 3},
                {"type": "observe", "pointer_id": "devptr.visual-1"},
                {"type": "finalize"},
            ],
            "expect": {"action_type": "observe", "pointer_id": "devptr.visual-1"},
        },
        {
            "case_id": "dev-read-speech-pointer",
            "capabilities": ["inspect_read"],
            "policy": "evidence_sufficiency",
            "question": "What phrase is spoken?",
            "claim_slots": [_slot("devslot.phrase", "The spoken phrase.")],
            "known_pointers": [
                _pointer("devptr.speech-1", "speech", "A candidate transcript passage.")
            ],
            "citable_observations": [],
            "recent_public_events": [],
            "no_progress_rounds": 0,
            "action_menu": [
                {"type": "status", "modalities": ["speech"]},
                {"type": "observe", "pointer_id": "devptr.speech-1"},
                {"type": "search", "modality": "speech", "query": "spoken phrase", "top_k": 3},
            ],
            "expect": {"action_type": "observe", "pointer_id": "devptr.speech-1"},
        },
        {
            "case_id": "dev-claim-coverage-finalize",
            "capabilities": ["claim_slot_coverage", "finalization"],
            "policy": "evidence_sufficiency",
            "question": "Name the token color and the spoken code word.",
            "claim_slots": [
                _slot("devslot.color", "The visible token color."),
                _slot("devslot.code", "The spoken code word."),
            ],
            "known_pointers": [],
            "citable_observations": [
                _observation(
                    "devobs.combo-A",
                    "speech",
                    "The token is violet, and the speaker says the code word maple.",
                )
            ],
            "recent_public_events": [],
            "no_progress_rounds": 0,
            "action_menu": [
                {"type": "search", "modality": "vision", "query": "token color", "top_k": 3},
                {"type": "finalize"},
            ],
            "expect": {
                "action_type": "finalize",
                "covered_claim_handles": ["devslot.color", "devslot.code"],
            },
        },
        {
            "case_id": "dev-no-progress-repeat-guard",
            "capabilities": ["no_progress_repeated_action_handling"],
            "policy": "react",
            "question": "What symbol is visible?",
            "claim_slots": [_slot("devslot.symbol", "The visible symbol.")],
            "known_pointers": [
                _pointer("devptr.symbol-7", "vision", "Candidate symbol view.")
            ],
            "citable_observations": [],
            "recent_public_events": [
                {
                    "turn": 0,
                    "action": {
                        "type": "search",
                        "modality": "vision",
                        "query": "visible symbol",
                        "top_k": 3,
                    },
                    "response": {"status": "ok"},
                }
            ],
            "no_progress_rounds": 1,
            "action_menu": [
                {"type": "search", "modality": "vision", "query": "visible symbol", "top_k": 3},
                {"type": "observe", "pointer_id": "devptr.symbol-7"},
                {"type": "finalize"},
            ],
            "expect": {"action_type": "observe", "pointer_id": "devptr.symbol-7"},
        },
        {
            "case_id": "dev-missing-hop-diagnosis",
            "capabilities": ["missing_hop_diagnosis", "justified_abstention"],
            "policy": "evidence_sufficiency",
            "question": "Which event happens first?",
            "claim_slots": [_slot("devslot.order", "The temporal order.")],
            "known_pointers": [],
            "citable_observations": [],
            "recent_public_events": [],
            "no_progress_rounds": 2,
            "remaining_budget": _budget(1, 0.0),
            "action_menu": [{"type": "finalize"}],
            "expect": {
                "action_type": "finalize",
                "missing_hop": "temporal_order",
                "covered_claim_handles": [],
            },
        },
        {
            "case_id": "dev-blocked-route-status",
            "capabilities": ["missing_hop_diagnosis", "recovery_after_route_restoration"],
            "policy": "react",
            "question": "What does the speaker say?",
            "claim_slots": [_slot("devslot.utterance", "The spoken utterance.")],
            "known_pointers": [],
            "citable_observations": [],
            "recent_public_events": [
                {
                    "turn": 0,
                    "action": {
                        "type": "search",
                        "modality": "speech",
                        "query": "speaker utterance",
                        "top_k": 3,
                    },
                    "response": {
                        "status": "access_failure",
                        "error": {"code": "ROUTE_INACCESSIBLE", "retryable": True},
                    },
                }
            ],
            "no_progress_rounds": 1,
            "action_menu": [
                {"type": "search", "modality": "speech", "query": "speaker utterance alternate", "top_k": 3},
                {"type": "status", "modalities": ["speech"]},
                {"type": "finalize"},
            ],
            "expect": {"action_type": "status", "modalities": ["speech"]},
        },
        {
            "case_id": "dev-restored-route-search",
            "capabilities": ["recovery_after_route_restoration"],
            "policy": "evidence_sufficiency",
            "question": "What does the speaker say?",
            "claim_slots": [_slot("devslot.utterance", "The spoken utterance.")],
            "known_pointers": [],
            "citable_observations": [],
            "recent_public_events": [
                {
                    "turn": 0,
                    "action": {"type": "status", "modalities": ["speech"]},
                    "response": {
                        "status": "ok",
                        "channels": {
                            "speech": {
                                "status": "available",
                                "retryable": False,
                            }
                        },
                    },
                }
            ],
            "no_progress_rounds": 0,
            "action_menu": [
                {"type": "finalize"},
                {"type": "search", "modality": "speech", "query": "speaker utterance restored", "top_k": 3},
            ],
            "expect": {"action_type": "search", "modality": "speech"},
        },
    ]

    generator_cases = [
        {
            "case_id": "dev-finalize-visual",
            "capabilities": ["finalization", "exact_observation_id_citation_copy"],
            "question": "What color is the token?",
            "claim_slots": [_slot("devslot.color", "The visible token color.")],
            "observations": [
                _observation("devobs.V-91_copy", "vision", "The token is cerulean.")
            ],
            "oracle_evidence": True,
            "oracle_support": {"devslot.color": ["devobs.V-91_copy"]},
            "required_terms": {"devslot.color": ["cerulean"]},
            "expect_verdicts": ["answer"],
        },
        {
            "case_id": "dev-finalize-speech",
            "capabilities": ["finalization", "exact_observation_id_citation_copy"],
            "question": "What code word is spoken?",
            "claim_slots": [_slot("devslot.code", "The spoken code word.")],
            "observations": [
                _observation("devobs.S_4-Exact", "speech", "The speaker says the code word juniper.")
            ],
            "oracle_evidence": True,
            "oracle_support": {"devslot.code": ["devobs.S_4-Exact"]},
            "required_terms": {"devslot.code": ["juniper"]},
            "expect_verdicts": ["answer"],
        },
        {
            "case_id": "dev-finalize-two-claims",
            "capabilities": ["claim_slot_coverage", "finalization"],
            "question": "State the card shape and the sound.",
            "claim_slots": [
                _slot("devslot.shape", "The visible card shape."),
                _slot("devslot.sound", "The audible sound."),
            ],
            "observations": [
                _observation("devobs.shape-X", "vision", "The card is triangular."),
                _observation("devobs.sound-Y", "ambient", "A bell chime is audible."),
            ],
            "oracle_evidence": True,
            "oracle_support": {
                "devslot.shape": ["devobs.shape-X"],
                "devslot.sound": ["devobs.sound-Y"],
            },
            "required_terms": {
                "devslot.shape": ["triangular"],
                "devslot.sound": ["bell", "chime"],
            },
            "expect_verdicts": ["answer"],
        },
        {
            "case_id": "dev-finalize-shared-observation",
            "capabilities": ["claim_slot_coverage", "exact_observation_id_citation_copy"],
            "question": "Give the cube color and the spoken label.",
            "claim_slots": [
                _slot("devslot.cube", "The visible cube color."),
                _slot("devslot.label", "The spoken label."),
            ],
            "observations": [
                _observation(
                    "devobs.Shared_Z9",
                    "speech",
                    "The cube is amber, and the speaker calls it comet.",
                )
            ],
            "oracle_evidence": True,
            "oracle_support": {
                "devslot.cube": ["devobs.Shared_Z9"],
                "devslot.label": ["devobs.Shared_Z9"],
            },
            "required_terms": {
                "devslot.cube": ["amber"],
                "devslot.label": ["comet"],
            },
            "expect_verdicts": ["answer"],
        },
        {
            "case_id": "dev-abstain-missing-speech",
            "capabilities": ["justified_abstention", "missing_hop_diagnosis"],
            "question": "What sentence is spoken?",
            "claim_slots": [_slot("devslot.sentence", "The spoken sentence.")],
            "observations": [],
            "oracle_evidence": False,
            "oracle_support": {},
            "required_terms": {},
            "expect_verdicts": ["insufficient", "access_failure", "abstain"],
            "expect_missing_modality": "speech",
            "expect_missing_hop": "speech_content",
        },
        {
            "case_id": "dev-abstain-missing-order",
            "capabilities": ["justified_abstention", "missing_hop_diagnosis"],
            "question": "Which action occurs first?",
            "claim_slots": [_slot("devslot.order", "The temporal order.")],
            "observations": [
                _observation("devobs.partial-1", "vision", "A lever is visible.")
            ],
            "oracle_evidence": False,
            "oracle_support": {},
            "required_terms": {},
            "expect_verdicts": ["insufficient", "access_failure", "abstain"],
            "expect_missing_hop": "temporal_order",
        },
    ]
    contract = {
        "schema_version": SCHEMA_VERSION,
        "development_only": True,
        "scientific_evaluation_eligible": False,
        "contains_no_evaluation_family_content": True,
        "actual_model_authorship_required": True,
        "maximum_repairs_per_output": MAX_REPAIRS,
        "strict_fail_closed": True,
        "deterministic_answer_substitution": False,
        "preregistered_competence_floors": {
            "valid_structured_outputs_after_at_most_one_repair": STRUCTURED_OUTPUT_FLOOR,
            "supported_answer_success_on_oracle_evidence": SUPPORTED_ANSWER_FLOOR,
            "unsupported_required_claims": 0,
        },
        "controller_cases": controller_cases,
        "generator_cases": generator_cases,
        "prompt_hashes": prompt_hashes(),
    }
    contract["contract_hash"] = _semantic_hash(contract)
    return contract


def _semantic_hash(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _write_json(path: Path, value: Any, *, restricted: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if restricted:
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
        os.chmod(temporary, 0o600 if restricted else 0o644)
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


def _controller_success(
    case: Mapping[str, Any], decision: Mapping[str, Any]
) -> tuple[bool, list[str]]:
    errors: list[str] = []
    expected = case["expect"]
    action = decision["action"]
    if action["type"] != expected["action_type"]:
        errors.append("WRONG_ACTION_TYPE")
    for key in ("modality", "pointer_id", "modalities"):
        if key in expected and action.get(key) != expected[key]:
            errors.append(f"WRONG_{key.upper()}")
    state = decision["public_state"]
    if "covered_claim_handles" in expected and set(
        state["covered_claim_handles"]
    ) != set(expected["covered_claim_handles"]):
        errors.append("WRONG_CLAIM_COVERAGE")
    if (
        "missing_hop" in expected
        and expected["missing_hop"] not in state["missing_hops"]
    ):
        errors.append("MISSING_HOP_NOT_DIAGNOSED")
    return not errors, errors


def _generator_success(
    case: Mapping[str, Any], final: Mapping[str, Any]
) -> tuple[bool, int, list[str]]:
    errors: list[str] = []
    unsupported = 0
    if final["verdict"] not in case["expect_verdicts"]:
        errors.append("WRONG_VERDICT")
    if case["oracle_evidence"]:
        if final["verdict"] != "answer":
            errors.append("ORACLE_CASE_NOT_ANSWERED")
        assertions = {
            row["claim_handle"]: row for row in final["asserted_claims"]
        }
        for handle, allowed_citations in case["oracle_support"].items():
            assertion = assertions.get(handle)
            if assertion is None:
                errors.append(f"MISSING_REQUIRED_CLAIM:{handle}")
                continue
            citations = assertion["citations"]
            if not citations or not set(citations) <= set(allowed_citations):
                unsupported += 1
                errors.append(f"UNSUPPORTED_REQUIRED_CLAIM:{handle}")
            text = (
                assertion["text"] + " " + str(final["answer_text"])
            ).casefold()
            if not any(
                term.casefold() in text
                for term in case["required_terms"].get(handle, [])
            ):
                errors.append(f"REQUIRED_CONTENT_MISSING:{handle}")
    else:
        if final["asserted_claims"]:
            unsupported += len(final["asserted_claims"])
            errors.append("NONANSWER_ASSERTED_CLAIMS")
        modality = case.get("expect_missing_modality")
        if modality and modality not in final["missing_modalities"]:
            errors.append("EXPECTED_MISSING_MODALITY_NOT_DIAGNOSED")
        hop = case.get("expect_missing_hop")
        if hop and hop not in final["missing_hops"]:
            errors.append("EXPECTED_MISSING_HOP_NOT_DIAGNOSED")
    return not errors, unsupported, errors


def evaluate_competence_results(
    contract: Mapping[str, Any],
    results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    result_by_id = {row["case_id"]: row for row in results}
    expected_ids = {
        row["case_id"]
        for row in [
            *contract["controller_cases"],
            *contract["generator_cases"],
        ]
    }
    valid = sum(
        bool(result_by_id.get(case_id, {}).get("structured_valid"))
        for case_id in expected_ids
    )
    oracle_ids = {
        row["case_id"]
        for row in contract["generator_cases"]
        if row["oracle_evidence"]
    }
    supported = sum(
        bool(result_by_id.get(case_id, {}).get("semantic_success"))
        for case_id in oracle_ids
    )
    unsupported = sum(
        int(result_by_id.get(case_id, {}).get("unsupported_required_claims", 0))
        for case_id in expected_ids
    )
    structured_rate = valid / len(expected_ids) if expected_ids else 0.0
    supported_rate = supported / len(oracle_ids) if oracle_ids else 0.0
    floors = contract["preregistered_competence_floors"]
    gates = {
        "structured_output_floor_met": (
            structured_rate
            >= floors["valid_structured_outputs_after_at_most_one_repair"]
        ),
        "supported_answer_floor_met": (
            supported_rate
            >= floors["supported_answer_success_on_oracle_evidence"]
        ),
        "zero_unsupported_required_claims_met": (
            unsupported == floors["unsupported_required_claims"]
        ),
    }
    return {
        "case_count": len(expected_ids),
        "valid_structured_output_count": valid,
        "valid_structured_output_rate": structured_rate,
        "oracle_evidence_case_count": len(oracle_ids),
        "supported_answer_success_count": supported,
        "supported_answer_success_rate": supported_rate,
        "unsupported_required_claim_count": unsupported,
        "gates": gates,
        "decision": (
            "GO" if all(gates.values()) else "NO_GO"
        ),
    }


def _snapshot_from_manifest(
    root: Path, model_key: str
) -> tuple[Path, dict[str, Any]]:
    try:
        spec = MODEL_SPECS[model_key]
    except KeyError as exc:
        raise ValueError(f"unknown model key: {model_key}") from exc
    manifest_path = root / spec["manifest"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    model = manifest[spec["manifest_section"]]
    if (
        model.get("repo_id") != spec["repo_id"]
        or model.get("revision") != spec["revision"]
        or model.get("snapshot_dir") != spec["snapshot_dir"]
    ):
        raise RuntimeError("PINNED_QWEN_MANIFEST_MISMATCH")
    snapshot = root / model["snapshot_dir"]
    if not (snapshot / "config.json").is_file():
        raise RuntimeError("PINNED_QWEN_SNAPSHOT_MISSING")
    return snapshot, manifest


def run_synthetic_competence(
    repo_root: str | Path = ".",
    *,
    startup_timeout_s: float = 240.0,
    generation_timeout_s: float = 180.0,
    threads: int = 8,
    model_key: str = "qwen1.5b",
) -> dict[str, Any]:
    """Execute the preregistered synthetic suite with the pinned offline Qwen."""

    root = Path(repo_root).resolve()
    try:
        spec = MODEL_SPECS[model_key]
    except KeyError as exc:
        raise ValueError(f"unknown model key: {model_key}") from exc
    contract = synthetic_competence_contract()
    if contract["contract_hash"] != TASK111_CONTRACT_HASH:
        raise RuntimeError("TASK111_CONTRACT_HASH_CHANGED")
    task111_contract = json.loads(
        (root / OUTPUT_DIR / "suite_contract.json").read_text(encoding="utf-8")
    )
    if task111_contract != contract:
        raise RuntimeError("TASK111_CONTRACT_EXAMPLES_CHANGED")
    output_dir = root / spec["output_dir"]
    _write_json(output_dir / "suite_contract.json", contract, restricted=True)
    snapshot, _manifest = _snapshot_from_manifest(root, model_key)
    results: list[dict[str, Any]] = []
    call_rows: list[dict[str, Any]] = []
    process_config = ProcessConfig(
        startup_timeout_s=startup_timeout_s,
        generation_timeout_s=generation_timeout_s,
        threads=threads,
        deny_network_namespace=model_key == "qwen7b",
    )
    generation_config = GenerationConfig()
    with QwenProcess(snapshot, config=process_config) as model:
        model_metadata = dict(model.metadata)
        if model_metadata.get("device") != "cpu":
            raise RuntimeError("QWEN_CONTROLLER_NOT_ON_CPU")
        if model_metadata.get("dtype") != "torch.bfloat16":
            raise RuntimeError("QWEN_CONTROLLER_NOT_BFLOAT16")
        for case in contract["controller_cases"]:
            try:
                generated = run_controller_decision(
                    model,
                    policy=case["policy"],
                    turn=len(case["recent_public_events"]),
                    question=case["question"],
                    claim_slots=case["claim_slots"],
                    available_tools=TOOLS,
                    remaining_budget=case.get("remaining_budget", _budget()),
                    known_pointers=case["known_pointers"],
                    citable_observations=case["citable_observations"],
                    recent_public_events=case["recent_public_events"],
                    action_menu=case["action_menu"],
                    no_progress_rounds=case["no_progress_rounds"],
                    config=generation_config,
                )
                semantic_success, errors = _controller_success(
                    case, generated["decision"]
                )
                row = {
                    "case_id": case["case_id"],
                    "case_type": "controller",
                    "capabilities": case["capabilities"],
                    "actual_learned_model": True,
                    "structured_valid": True,
                    "semantic_success": semantic_success,
                    "unsupported_required_claims": 0,
                    "errors": errors,
                    "decision": generated["decision"],
                    "model_calls": generated["model_calls"],
                }
            except LearnedCallFailure as exc:
                row = {
                    "case_id": case["case_id"],
                    "case_type": "controller",
                    "capabilities": case["capabilities"],
                    "actual_learned_model": True,
                    "structured_valid": False,
                    "semantic_success": False,
                    "unsupported_required_claims": 0,
                    "errors": [exc.code],
                    "terminal_error": {"code": exc.code},
                    "model_calls": exc.details.get("attempts", []),
                }
            results.append(row)
            call_rows.extend(
                {
                    "case_id": case["case_id"],
                    "case_type": "controller",
                    **call,
                }
                for call in row["model_calls"]
            )
        for case in contract["generator_cases"]:
            try:
                generated = run_grounded_generator(
                    model,
                    question=case["question"],
                    claim_slots=case["claim_slots"],
                    observations=case["observations"],
                    condition="synthetic_controller_development",
                    config=generation_config,
                )
                semantic_success, unsupported, errors = _generator_success(
                    case, generated["final"]
                )
                row = {
                    "case_id": case["case_id"],
                    "case_type": "generator_finalization",
                    "capabilities": case["capabilities"],
                    "actual_learned_model": True,
                    "structured_valid": True,
                    "semantic_success": semantic_success,
                    "unsupported_required_claims": unsupported,
                    "errors": errors,
                    "final": generated["final"],
                    "model_calls": generated["model_calls"],
                }
            except LearnedCallFailure as exc:
                row = {
                    "case_id": case["case_id"],
                    "case_type": "generator_finalization",
                    "capabilities": case["capabilities"],
                    "actual_learned_model": True,
                    "structured_valid": False,
                    "semantic_success": False,
                    "unsupported_required_claims": 0,
                    "errors": [exc.code],
                    "terminal_error": {"code": exc.code},
                    "model_calls": exc.details.get("attempts", []),
                }
            results.append(row)
            call_rows.extend(
                {
                    "case_id": case["case_id"],
                    "case_type": "generator_finalization",
                    **call,
                }
                for call in row["model_calls"]
            )
    metrics = evaluate_competence_results(contract, results)
    prompt_config = {
        "prompt_hashes": contract["prompt_hashes"],
        "generation_config": asdict(generation_config),
        "process_config": asdict(process_config),
        "local_files_only": True,
        "offline_environment": True,
        "network_namespace_denied": process_config.deny_network_namespace,
        "deterministic_decoding": {"do_sample": False, "seed": 0},
        "maximum_repairs_per_output": MAX_REPAIRS,
    }
    prompt_config_hash = _semantic_hash(prompt_config)
    peak_rss_bytes = max(
        [
            int(model_metadata.get("peak_rss_bytes") or 0),
            *[
                int(call.get("peak_rss_bytes") or 0)
                for row in results
                for call in row["model_calls"]
            ],
        ]
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "stage": "SYNTHETIC_DEVELOPMENT_ONLY",
        "scientific_evaluation_eligible": False,
        "contract_hash": contract["contract_hash"],
        "task111_contract_preserved": True,
        "prompt_config": prompt_config,
        "prompt_config_hash": prompt_config_hash,
        "model": {
            "repo_id": spec["repo_id"],
            "revision": spec["revision"],
            "snapshot_dir": spec["snapshot_dir"],
            "offline": True,
            "local_files_only": True,
            "network_namespace_denied": process_config.deny_network_namespace,
            "do_sample": False,
            "metadata": model_metadata,
        },
        "peak_rss_bytes": peak_rss_bytes,
        "peak_rss_kib": peak_rss_bytes // 1024,
        "metrics": metrics,
        "results": results,
    }
    if model_key == "qwen7b":
        report["paired_comparison"] = paired_comparison(
            contract,
            json.loads(
                (root / OUTPUT_DIR / "results.json").read_text(encoding="utf-8")
            ),
            report,
        )
    _write_json(output_dir / "results.json", report, restricted=True)
    _write_jsonl(output_dir / "calls.jsonl", call_rows)
    _write_json(
        output_dir / "summary.json",
        {key: value for key, value in report.items() if key != "results"},
        restricted=True,
    )
    if model_key == "qwen7b":
        _write_json(
            output_dir / "paired_comparison.json",
            report["paired_comparison"],
            restricted=True,
        )
    write_reports(root, report, model_key=model_key)
    return report


def _percent(value: float) -> str:
    return f"{100.0 * value:.1f}%"


def paired_comparison(
    contract: Mapping[str, Any],
    baseline_report: Mapping[str, Any],
    qwen7b_report: Mapping[str, Any],
) -> dict[str, Any]:
    baseline_by_id = {
        row["case_id"]: row for row in baseline_report["results"]
    }
    qwen7b_by_id = {row["case_id"]: row for row in qwen7b_report["results"]}
    cases = []
    capabilities: dict[str, dict[str, int]] = {}
    for case in [
        *contract["controller_cases"],
        *contract["generator_cases"],
    ]:
        case_id = case["case_id"]
        baseline = baseline_by_id[case_id]
        qwen7b = qwen7b_by_id[case_id]
        cases.append(
            {
                "case_id": case_id,
                "case_type": baseline["case_type"],
                "capabilities": case["capabilities"],
                "qwen1_5b": {
                    "structured_valid": baseline["structured_valid"],
                    "semantic_success": baseline["semantic_success"],
                    "unsupported_required_claims": baseline[
                        "unsupported_required_claims"
                    ],
                    "errors": baseline["errors"],
                },
                "qwen7b": {
                    "structured_valid": qwen7b["structured_valid"],
                    "semantic_success": qwen7b["semantic_success"],
                    "unsupported_required_claims": qwen7b[
                        "unsupported_required_claims"
                    ],
                    "errors": qwen7b["errors"],
                },
                "semantic_delta": (
                    int(qwen7b["semantic_success"])
                    - int(baseline["semantic_success"])
                ),
            }
        )
        for capability in case["capabilities"]:
            counts = capabilities.setdefault(
                capability,
                {
                    "case_count": 0,
                    "qwen1_5b_success_count": 0,
                    "qwen7b_success_count": 0,
                },
            )
            counts["case_count"] += 1
            counts["qwen1_5b_success_count"] += int(
                baseline["semantic_success"]
            )
            counts["qwen7b_success_count"] += int(qwen7b["semantic_success"])
    capability_rows = []
    for capability, counts in sorted(capabilities.items()):
        count = counts["case_count"]
        capability_rows.append(
            {
                "capability": capability,
                **counts,
                "qwen1_5b_success_rate": (
                    counts["qwen1_5b_success_count"] / count
                ),
                "qwen7b_success_rate": counts["qwen7b_success_count"] / count,
                "success_count_delta": (
                    counts["qwen7b_success_count"]
                    - counts["qwen1_5b_success_count"]
                ),
            }
        )
    return {
        "baseline_contract_hash": baseline_report["contract_hash"],
        "qwen7b_contract_hash": qwen7b_report["contract_hash"],
        "same_frozen_contract": (
            baseline_report["contract_hash"] == qwen7b_report["contract_hash"]
        ),
        "aggregate": {
            "qwen1_5b": baseline_report["metrics"],
            "qwen7b": qwen7b_report["metrics"],
            "valid_structured_output_count_delta": (
                qwen7b_report["metrics"]["valid_structured_output_count"]
                - baseline_report["metrics"]["valid_structured_output_count"]
            ),
            "supported_answer_success_count_delta": (
                qwen7b_report["metrics"]["supported_answer_success_count"]
                - baseline_report["metrics"]["supported_answer_success_count"]
            ),
            "unsupported_required_claim_count_delta": (
                qwen7b_report["metrics"]["unsupported_required_claim_count"]
                - baseline_report["metrics"]["unsupported_required_claim_count"]
            ),
        },
        "cases": cases,
        "capabilities": capability_rows,
    }


def write_reports(
    root: Path, report: Mapping[str, Any], *, model_key: str = "qwen1.5b"
) -> None:
    spec = MODEL_SPECS[model_key]
    metrics = report["metrics"]
    failed = [
        row for row in report["results"] if not row["semantic_success"]
    ]
    failure_lines = (
        [
            f"- `{row['case_id']}`: {', '.join(row['errors'])}"
            for row in failed
        ]
        or ["- None."]
    )
    if model_key == "qwen7b":
        comparison = report["paired_comparison"]
        case_lines = [
            (
                f"| `{row['case_id']}` | "
                f"{'PASS' if row['qwen1_5b']['semantic_success'] else 'FAIL'} | "
                f"{'PASS' if row['qwen7b']['semantic_success'] else 'FAIL'} | "
                f"{row['semantic_delta']:+d} | "
                f"{', '.join(row['qwen7b']['errors']) or 'None'} |"
            )
            for row in comparison["cases"]
        ]
        capability_lines = [
            (
                f"| `{row['capability']}` | "
                f"{row['qwen1_5b_success_count']}/{row['case_count']} | "
                f"{row['qwen7b_success_count']}/{row['case_count']} | "
                f"{row['success_count_delta']:+d} |"
            )
            for row in comparison["capabilities"]
        ]
        title = "# Qwen2.5-7B controller capacity sensitivity"
        date = "**Date:** 2026-09-21  "
        model_sentence = (
            "The suite replaced only the frozen controller backbone with the "
            "exact Qwen2.5-7B-Instruct snapshot. Prompts, cases, action menu, "
            "schemas, repair budget, scoring, and frozen thresholds were unchanged."
        )
        comparison_section = [
            "",
            "## Paired comparison by case",
            "",
            "| Case | 1.5B semantic | 7B semantic | Delta | 7B errors |",
            "|---|---:|---:|---:|---|",
            *case_lines,
            "",
            "## Paired comparison by capability",
            "",
            "| Capability | 1.5B success | 7B success | Delta |",
            "|---|---:|---:|---:|",
            *capability_lines,
        ]
    else:
        title = "# Synthetic learned-controller competence"
        date = "**Date:** 2026-09-20  "
        model_sentence = (
            "The suite used the pinned Qwen2.5-1.5B-Instruct snapshot offline,"
        )
        comparison_section = []
    markdown = "\n".join(
        [
            title,
            "",
            date,
            "**Scope:** synthetic/development-only; not scientific evaluation",
            "",
            "## Decision",
            "",
            (
                f"```text\n{spec['decision_prefix']}_"
                f"{metrics['decision']}\n```"
            ),
            "",
            model_sentence,
            "preserved model authorship, allowed at most one repair per output,",
            "failed closed on invalid output, and used no deterministic answer",
            "substitution.",
            "",
            "## Preregistered floors and observed metrics",
            "",
            "| Gate | Floor | Observed | Pass |",
            "|---|---:|---:|---|",
            (
                "| Valid structured outputs after <=1 repair | >=90% | "
                f"{_percent(metrics['valid_structured_output_rate'])} "
                f"({metrics['valid_structured_output_count']}/"
                f"{metrics['case_count']}) | "
                f"{metrics['gates']['structured_output_floor_met']} |"
            ),
            (
                "| Supported-answer success on oracle-evidence cases | >=80% | "
                f"{_percent(metrics['supported_answer_success_rate'])} "
                f"({metrics['supported_answer_success_count']}/"
                f"{metrics['oracle_evidence_case_count']}) | "
                f"{metrics['gates']['supported_answer_floor_met']} |"
            ),
            (
                "| Unsupported required claims | 0 | "
                f"{metrics['unsupported_required_claim_count']} | "
            f"{metrics['gates']['zero_unsupported_required_claims_met']} |"
            ),
            *comparison_section,
            "",
            "## Covered capabilities",
            "",
            "- initial modality routing",
            "- inspect/read selection",
            "- claim-slot coverage",
            "- exact observation-ID citation copying",
            "- finalization",
            "- justified abstention",
            "- no-progress/repeated-action handling",
            "- missing-hop diagnosis",
            "- recovery after route restoration",
            "",
            "## Failed semantic probes",
            "",
            *failure_lines,
            "",
            "## Boundaries",
            "",
            "- No NOAA evaluation family was opened or executed.",
            "- No eligible-family annotations or results were changed.",
            "- The excluded r017 gate was not rerun.",
            "- This result is a development competence result, not a benchmark.",
            "- No redistribution claim is made.",
            (
                "- Reopening the excluded r017 competence gate is "
                + (
                    "permitted by this synthetic capacity gate."
                    if metrics["decision"] == "GO"
                    else "not permitted by this synthetic capacity gate."
                )
            ),
            "",
            "## Frozen provenance",
            "",
            f"- Contract hash: `{report['contract_hash']}`",
            f"- Prompt/config hash: `{report['prompt_config_hash']}`",
            f"- Peak RSS: {report['peak_rss_bytes']} bytes",
            "",
            "## Artifacts",
            "",
            f"- `{spec['output_dir']}/suite_contract.json`",
            f"- `{spec['output_dir']}/calls.jsonl`",
            f"- `{spec['output_dir']}/results.json`",
            f"- `{spec['output_dir']}/summary.json`",
            *(
                [f"- `{spec['output_dir']}/paired_comparison.json`"]
                if model_key == "qwen7b"
                else []
            ),
        ]
    ) + "\n"
    doc_path = root / spec["doc_report"]
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text(markdown, encoding="utf-8")
    os.chmod(doc_path, 0o644)
    orchestration = "\n".join(
        [
            (
                "Task 114 Qwen2.5-7B frozen synthetic controller competence "
                "completed."
                if model_key == "qwen7b"
                else "Task 111 synthetic controller competence completed."
            ),
            "",
            f"Decision: {spec['decision_prefix']}_{metrics['decision']}",
            "",
            (
                "Valid structured outputs after <=1 repair: "
                f"{metrics['valid_structured_output_count']}/"
                f"{metrics['case_count']} "
                f"({_percent(metrics['valid_structured_output_rate'])})"
            ),
            (
                "Supported-answer success on oracle evidence: "
                f"{metrics['supported_answer_success_count']}/"
                f"{metrics['oracle_evidence_case_count']} "
                f"({_percent(metrics['supported_answer_success_rate'])})"
            ),
            (
                "Unsupported required claims: "
                f"{metrics['unsupported_required_claim_count']}"
            ),
            f"Contract hash: {report['contract_hash']}",
            f"Prompt/config hash: {report['prompt_config_hash']}",
            f"Peak RSS: {report['peak_rss_bytes']} bytes",
            "",
            "The run was offline and synthetic-only. It did not rerun r017 and",
            "did not access r004, r007, r011, or r016 for development.",
            (
                "Reopening excluded r017 competence gate permitted: "
                + ("YES" if metrics["decision"] == "GO" else "NO")
            ),
        ]
    ) + "\n"
    orchestration_path = root / spec["orchestration_report"]
    orchestration_path.parent.mkdir(parents=True, exist_ok=True)
    orchestration_path.write_text(orchestration, encoding="utf-8")
    os.chmod(orchestration_path, 0o644)
