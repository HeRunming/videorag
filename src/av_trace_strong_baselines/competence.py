"""Fictional strong-baseline competence-suite generation and evaluation."""

from __future__ import annotations

import copy
import json
import random
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .contracts import (
    FALLBACK_BINDINGS,
    PRIMARY_BINDINGS,
    InferenceStatus,
    LoadStatus,
    ModelBinding,
    sha256_json,
)
from .errors import EvaluationViolation, IsolationViolation, SchemaViolation
from .schemas import (
    EVIDENCE_STATE_FIELDS,
    parse_strict_json,
    validate_evidence_state,
    validate_final_answer_envelope,
)
from .security import (
    IsolationAttestation,
    ObservedEvidenceLock,
    OutputProvenance,
    assert_isolated,
    assert_public_surface,
)

SUITE_SCHEMA = "av-trace.strong-baseline-competence-suite/1.0"
SUITE_ID = "strong-baseline-fictional-public-v1"
GENERATOR_SEED = 15820260924

CONTROLLER_FINALIZER_THRESHOLDS = {
    "minimum_cases": 48,
    "deterministic_parser_schema_failure_fixtures": 1.0,
    "valid_structured_model_calls_min": 0.90,
    "correct_first_actions_overall_min": 0.85,
    "correct_first_actions_each_stratum_min": 0.75,
    "exact_six_field_state_min": 0.75,
    "each_state_component_min": 0.80,
    "oracle_supported_answer_min": 0.80,
    "blocked_partial_correct_abstention_min": 0.80,
    "restoration_reacquisition_min": 0.80,
    "unsupported_required_claims_max": 0,
    "private_field_exposures_max": 0,
    "deterministic_answer_substitutions_max": 0,
    "identity_and_injected_failure_fail_closed": 1.0,
}

DIRECT_AV_THRESHOLDS = {
    "minimum_cases": 24,
    "processor_manifest_failure_fixtures": 1.0,
    "valid_final_outputs_min": 0.90,
    "complete_evidence_supported_answer_min": 0.80,
    "each_modality_stratum_supported_answer_min": 0.75,
    "partial_masked_correct_abstention_min": 0.80,
    "unsupported_required_claims_max": 0,
    "out_of_exposure_citations_max": 0,
    "observed_evidence_lock": 1.0,
    "required_modality_drop_counterfactuals": 1.0,
    "deterministic_local_replay_parsed_output": 1.0,
}


def _slot(handle: str, description: str) -> dict[str, str]:
    return {"claim_handle": handle, "description": description}


def _observation(
    observation_id: str,
    modality: str,
    text: str,
    *,
    start_s: float = 0.0,
    end_s: float = 1.0,
) -> dict[str, Any]:
    return {
        "observation_id": observation_id,
        "interval": {"start_s": start_s, "end_s": end_s},
        "modalities": [modality],
        "payload": {"text": text},
    }


def _search(tool: str, query: str) -> dict[str, Any]:
    value: dict[str, Any] = {
        "tool": tool,
        "arguments": {
            "query": query,
            "top_k": 5,
            "time_range": {"start_s": 0.0, "end_s": 120.0},
            "exclude_result_ids": [],
        },
    }
    if tool == "search_speech":
        value["arguments"]["speaker_hint"] = None
    return value


def _inspect(start_s: float, end_s: float) -> dict[str, Any]:
    return {
        "tool": "inspect_clip",
        "arguments": {
            "interval": {"start_s": start_s, "end_s": end_s},
            "include_video": True,
            "include_audio": False,
        },
    }


def _status(channel: str) -> dict[str, Any]:
    return {
        "tool": "get_channel_status",
        "arguments": {"channels": [channel]},
    }


def _finalize_marker() -> dict[str, Any]:
    return {"tool": "finalize", "arguments": {}}


def _state(
    *,
    covered: Sequence[str] = (),
    missing_modalities: Sequence[str] = (),
    missing_hops: Sequence[str] = (),
    cause: str,
    intent: str,
    p_sufficient: float,
) -> dict[str, Any]:
    return {
        "p_sufficient": p_sufficient,
        "covered_claim_handles": list(covered),
        "missing_modalities": list(missing_modalities),
        "missing_hops": list(missing_hops),
        "missingness_cause": cause,
        "recovery_intent": intent,
    }


def _shuffled_menu(
    rng: random.Random,
    actions: Sequence[Mapping[str, Any]],
    *,
    expected_tool: str,
) -> tuple[list[dict[str, Any]], int]:
    menu = [copy.deepcopy(dict(item)) for item in actions]
    rng.shuffle(menu)
    expected = next(
        index for index, action in enumerate(menu) if action["tool"] == expected_tool
    )
    return menu, expected


def _controller_cases(rng: random.Random) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    colors = ("ultraviolet", "copper", "teal")
    spoken = ("kepler", "mistral", "saffron")
    sounds = ("glass ping", "two drum taps", "paper flutter")
    for index in range(3):
        specs = [
            {
                "stratum": "route_vision",
                "question": (
                    f"What color is the fictional prism marked P{index + 1}?"
                ),
                "slot": _slot(
                    f"v1slot.vision_{index}", "Visible prism color."
                ),
                "menu": [
                    _search("search_speech", "spoken prism color"),
                    _search("search_visual", "fictional prism visible color"),
                    _search("search_ambient_audio", "prism sound"),
                ],
                "expected_tool": "search_visual",
                "state": _state(
                    missing_modalities=("vision",),
                    missing_hops=("entity_identity",),
                    cause="evidence_accessible_but_not_found",
                    intent="search_vision",
                    p_sufficient=0.0,
                ),
            },
            {
                "stratum": "route_speech",
                "question": (
                    f"What code word does the fictional navigator say in trial {index + 1}?"
                ),
                "slot": _slot(
                    f"v1slot.speech_{index}", "Spoken navigation code."
                ),
                "menu": [
                    _search("search_visual", "navigator mouth movement"),
                    _search("search_speech", "fictional navigator code word"),
                    _search("search_ambient_audio", "navigation chime"),
                ],
                "expected_tool": "search_speech",
                "state": _state(
                    missing_modalities=("speech",),
                    missing_hops=("speech_content",),
                    cause="evidence_accessible_but_not_found",
                    intent="search_speech",
                    p_sufficient=0.0,
                ),
            },
            {
                "stratum": "route_ambient",
                "question": (
                    f"Which non-speech sound follows the fictional hatch closure in trial {index + 1}?"
                ),
                "slot": _slot(
                    f"v1slot.ambient_{index}", "Ambient post-closure sound."
                ),
                "menu": [
                    _search("search_visual", "hatch closure"),
                    _search("search_speech", "description of hatch sound"),
                    _search(
                        "search_ambient_audio",
                        "non-speech sound after fictional hatch closes",
                    ),
                ],
                "expected_tool": "search_ambient_audio",
                "state": _state(
                    missing_modalities=("ambient",),
                    missing_hops=("ambient_event",),
                    cause="evidence_accessible_but_not_found",
                    intent="search_ambient",
                    p_sufficient=0.0,
                ),
            },
            {
                "stratum": "observe_pointer",
                "question": (
                    f"What symbol appears on fictional panel Q{index + 1}?"
                ),
                "slot": _slot(
                    f"v1slot.pointer_{index}", "Visible panel symbol."
                ),
                "menu": [
                    _search("search_visual", "panel symbol"),
                    _inspect(10.0 + index, 11.0 + index),
                    _finalize_marker(),
                ],
                "expected_tool": "inspect_clip",
                "state": _state(
                    missing_modalities=("vision",),
                    missing_hops=("event_detection",),
                    cause="evidence_accessible_but_not_found",
                    intent="observe_pointer",
                    p_sufficient=0.0,
                ),
                "known_pointers": [
                    {
                        "pointer_id": f"ptr.public.panel.{index}",
                        "interval": {
                            "start_s": 10.0 + index,
                            "end_s": 11.0 + index,
                        },
                        "modality": "vision",
                        "citable": False,
                    }
                ],
            },
            {
                "stratum": "blocked_status",
                "question": (
                    f"What phrase is spoken by the fictional archivist in trial {index + 1}?"
                ),
                "slot": _slot(
                    f"v1slot.blocked_{index}", "Spoken archivist phrase."
                ),
                "menu": [
                    _search("search_speech", "archivist phrase alternate"),
                    _status("speech"),
                    _finalize_marker(),
                ],
                "expected_tool": "get_channel_status",
                "state": _state(
                    missing_modalities=("speech",),
                    missing_hops=("speech_content",),
                    cause="evidence_in_source_but_inaccessible",
                    intent="check_channel_status",
                    p_sufficient=0.0,
                ),
                "history": [
                    {
                        "action": _search(
                            "search_speech", "fictional archivist phrase"
                        ),
                        "response": {
                            "status": "channel_unavailable",
                            "error": {
                                "code": "CHANNEL_UNAVAILABLE",
                                "retryable": True,
                            },
                        },
                    }
                ],
            },
            {
                "stratum": "restoration_reacquire",
                "question": (
                    f"What code word does the fictional navigator say in restored trial {index + 1}?"
                ),
                "slot": _slot(
                    f"v1slot.restored_{index}", "Restored spoken code."
                ),
                "menu": [
                    _finalize_marker(),
                    _search(
                        "search_speech", "retry fictional navigator code route"
                    ),
                    _status("speech"),
                ],
                "expected_tool": "search_speech",
                "state": _state(
                    missing_modalities=("speech",),
                    missing_hops=("speech_content",),
                    cause="evidence_in_source_but_inaccessible",
                    intent="retry_restored_route",
                    p_sufficient=0.0,
                ),
                "history": [
                    {
                        "event_type": "protocol_checkpoint",
                        "event_version": "2.0.0",
                        "message": "Scheduled protocol checkpoint completed.",
                        "cost": 0.0,
                    }
                ],
                "restoration_pair_id": f"restore-{index}",
            },
            {
                "stratum": "no_progress_guard",
                "question": (
                    f"Which event occurs first in fictional sequence {index + 1}?"
                ),
                "slot": _slot(
                    f"v1slot.order_{index}", "Temporal event order."
                ),
                "menu": [_finalize_marker()],
                "expected_tool": "finalize",
                "state": _state(
                    missing_modalities=("vision",),
                    missing_hops=("temporal_order",),
                    cause="evidence_accessible_but_not_found",
                    intent="finalize_abstain",
                    p_sufficient=0.0,
                ),
            },
            {
                "stratum": "finalize_ready",
                "question": (
                    f"What is the fictional token label in completed trial {index + 1}?"
                ),
                "slot": _slot(
                    f"v1slot.ready_{index}", "Observed token label."
                ),
                "menu": [
                    _search("search_visual", "more token views"),
                    _finalize_marker(),
                ],
                "expected_tool": "finalize",
                "state": _state(
                    covered=(f"v1slot.ready_{index}",),
                    cause="not_missing",
                    intent="finalize_answer",
                    p_sufficient=1.0,
                ),
                "observations": [
                    _observation(
                        f"obs.public.ready.{index}",
                        "vision",
                        f"The token label is {colors[index]}.",
                    )
                ],
            },
        ]
        for spec in specs:
            if spec["stratum"] == "no_progress_guard" and index == 2:
                spec["stratum"] = "no_trigger"
                spec["history"] = [
                    {
                        "event_type": "protocol_checkpoint",
                        "event_version": "2.0.0",
                        "message": "Scheduled protocol checkpoint completed.",
                        "cost": 0.0,
                    }
                ]
            menu, expected_index = _shuffled_menu(
                rng, spec["menu"], expected_tool=spec["expected_tool"]
            )
            case_id = f"sbc-controller-{len(cases) + 1:03d}"
            public_input = {
                "task": "choose_next_action",
                "policy": (
                    "evidence_sufficiency"
                    if len(cases) % 2
                    else "react"
                ),
                "question": spec["question"],
                "public_claim_slots": [spec["slot"]],
                "known_pointers": spec.get("known_pointers", []),
                "observed_evidence": spec.get("observations", []),
                "recent_public_history": spec.get("history", []),
                "action_menu": menu,
                "remaining_budget": {
                    "actions_remaining": 6,
                    "cost_remaining": 8.0,
                },
            }
            cases.append(
                {
                    "case_id": case_id,
                    "case_type": "controller",
                    "stratum": spec["stratum"],
                    "public_input": public_input,
                    "scoring_target": {
                        "expected_action_index": expected_index,
                        "expected_evidence_state": spec["state"],
                        "restoration_reacquisition": (
                            spec["stratum"] == "restoration_reacquire"
                        ),
                        "fictional_answer_tokens": [
                            colors[index],
                            spoken[index],
                            sounds[index],
                        ],
                    },
                }
            )
    return cases


def _finalizer_cases() -> list[dict[str, Any]]:
    facts = [
        ("vision", "octagonal", "badge shape"),
        ("speech", "northstar", "spoken code"),
        ("ambient", "copper chime", "ambient sound"),
        ("vision", "magenta", "lamp color"),
        ("speech", "riverglass", "spoken passphrase"),
        ("ambient", "three clicks", "ambient sequence"),
        ("vision", "crescent", "panel mark"),
        ("speech", "orbit seven", "spoken designation"),
        ("vision", "silver", "restored object color"),
        ("speech", "lantern", "restored spoken word"),
        ("ambient", "soft whistle", "restored sound"),
        ("vision", "hexagon", "restored panel shape"),
    ]
    cases: list[dict[str, Any]] = []
    for index, (modality, term, label) in enumerate(facts):
        handle = f"v1slot.final.{index}"
        observation_id = f"obs.public.final.{index}"
        condition = "restoration_complete" if index >= 8 else "oracle_complete"
        cases.append(
            {
                "case_id": f"sbc-finalizer-{index + 1:03d}",
                "case_type": "finalizer",
                "stratum": condition,
                "public_input": {
                    "task": "grounded_finalization",
                    "condition": condition,
                    "question": f"What is the fictional {label}?",
                    "public_claim_slots": [_slot(handle, f"The {label}.")],
                    "observed_evidence": [
                        _observation(
                            observation_id,
                            modality,
                            f"The fictional {label} is {term}.",
                        )
                    ],
                },
                "scoring_target": {
                    "answer_mode": "answer",
                    "required_terms_by_claim": {handle: term.split()},
                    "accepted_support": {handle: [observation_id]},
                    "oracle_complete": index < 8,
                    "restoration_reacquisition": index >= 8,
                },
            }
        )
    partial_specs = [
        ("speech", "speech_content"),
        ("vision", "event_detection"),
        ("ambient", "ambient_event"),
        ("vision", "temporal_order"),
    ]
    for index, (modality, hop) in enumerate(partial_specs):
        handle = f"v1slot.partial.{index}"
        cases.append(
            {
                "case_id": f"sbc-finalizer-{len(cases) + 1:03d}",
                "case_type": "finalizer",
                "stratum": "blocked_partial",
                "public_input": {
                    "task": "grounded_finalization",
                    "condition": "partial_evidence",
                    "question": (
                        f"What missing fictional {modality} fact completes item {index + 1}?"
                    ),
                    "public_claim_slots": [_slot(handle, "Missing fact.")],
                    "observed_evidence": [],
                },
                "scoring_target": {
                    "answer_mode": "abstain",
                    "required_missing_modality": modality,
                    "required_missing_hop": hop,
                    "required_terms_by_claim": {},
                    "accepted_support": {},
                    "oracle_complete": False,
                    "restoration_reacquisition": False,
                },
            }
        )
    return cases


def _failure_cases(prefix: str, *, direct: bool = False) -> list[dict[str, Any]]:
    fixtures = (
        ("malformed_output", InferenceStatus.INVALID_OUTPUT, True),
        ("malformed_output", InferenceStatus.INVALID_OUTPUT, True),
        ("wrong_snapshot", InferenceStatus.SNAPSHOT_MISMATCH, False),
        ("wrong_snapshot", InferenceStatus.SNAPSHOT_MISMATCH, False),
        ("provider_failure", InferenceStatus.PROVIDER_FAILURE, True),
        ("provider_failure", InferenceStatus.PROVIDER_FAILURE, True),
        ("timeout", InferenceStatus.TIMEOUT, True),
        ("timeout", InferenceStatus.TIMEOUT, True),
        ("process_failure", InferenceStatus.PROCESS_FAILURE, True),
        ("oom", InferenceStatus.OOM, True),
        ("budget_exhausted", InferenceStatus.BUDGET_EXHAUSTED, False),
    )
    if direct:
        fixtures = (
            ("malformed_manifest", InferenceStatus.INVALID_OUTPUT, False),
            ("malformed_manifest", InferenceStatus.INVALID_OUTPUT, False),
            ("wrong_snapshot", InferenceStatus.SNAPSHOT_MISMATCH, False),
            ("wrong_snapshot", InferenceStatus.SNAPSHOT_MISMATCH, False),
            ("provider_failure", InferenceStatus.PROVIDER_FAILURE, True),
            ("provider_failure", InferenceStatus.PROVIDER_FAILURE, True),
        )
    cases = []
    for index, (fixture, status, model_called) in enumerate(fixtures, 1):
        cases.append(
            {
                "case_id": f"{prefix}-{index:03d}",
                "case_type": "runtime_failure",
                "stratum": fixture,
                "public_input": {
                    "task": (
                        "direct_av_grounded_finalization"
                        if direct
                        else "failure_injection"
                    ),
                    "question": (
                        f"What is the fictional failure-fixture token {index}?"
                    ),
                    "public_claim_slots": [
                        _slot(f"v1slot.failure.{index}", "Fixture token.")
                    ],
                    "injected_public_fixture": fixture,
                },
                "scoring_target": {
                    "expected_inference_status": status,
                    "expected_model_called": model_called,
                },
            }
        )
    return cases


def _direct_cases() -> list[dict[str, Any]]:
    modalities = (
        ("vision", ["vision"], "emerald"),
        ("speech", ["speech"], "solstice"),
        ("ambient", ["ambient"], "wooden knock"),
        ("joint_av", ["vision", "ambient"], "blue flare"),
    )
    cases: list[dict[str, Any]] = []
    for pair in range(8):
        stratum, present, term = modalities[pair % len(modalities)]
        for replay_index in range(2):
            case_index = len(cases) + 1
            handle = f"v1slot.direct.{pair}"
            exposure_id = f"exposure.public.direct.{pair}"
            cases.append(
                {
                    "case_id": f"sbc-direct-{case_index:03d}",
                    "case_type": "direct_av",
                    "stratum": stratum,
                    "public_input": {
                        "task": "direct_av_grounded_finalization",
                        "question": (
                            f"What fictional signal appears in replay group {pair + 1}?"
                        ),
                        "public_claim_slots": [
                            _slot(handle, "Observed fictional signal.")
                        ],
                        "media_exposure_manifest": [
                            {
                                "exposure_id": exposure_id,
                                "source_ordinal": 0,
                                "interval": {
                                    "start_s": float(pair),
                                    "end_s": float(pair + 1),
                                },
                                "modalities": present,
                                "asset_locator": (
                                    f"generated://strong-baseline-v1/{pair}"
                                ),
                            }
                        ],
                        "fictional_media_recipe": {
                            "visual": (
                                "solid geometric cards and lights"
                                if "vision" in present
                                else "blank frame"
                            ),
                            "audio": (
                                "synthetic speech or tones"
                                if any(
                                    item in present
                                    for item in ("speech", "ambient")
                                )
                                else "silence"
                            ),
                        },
                    },
                    "scoring_target": {
                        "answer_mode": "answer",
                        "required_terms_by_claim": {handle: term.split()},
                        "accepted_support": {handle: [exposure_id]},
                        "required_modality_stratum": stratum,
                        "replay_group": f"direct-replay-{pair}",
                        "counterfactual_drop": None,
                    },
                }
            )
    drops = (
        ("audio_drop", "speech", "speech_content"),
        ("audio_drop", "ambient", "ambient_event"),
        ("audio_drop", "speech", "speech_content"),
        ("audio_drop", "ambient", "ambient_event"),
        ("visual_drop", "vision", "event_detection"),
        ("visual_drop", "vision", "entity_identity"),
        ("visual_drop", "vision", "state_change"),
        ("visual_drop", "vision", "temporal_order"),
    )
    for drop, modality, hop in drops:
        index = len(cases) + 1
        handle = f"v1slot.direct.partial.{index}"
        cases.append(
            {
                "case_id": f"sbc-direct-{index:03d}",
                "case_type": "direct_av",
                "stratum": "partial_masked",
                "public_input": {
                    "task": "direct_av_grounded_finalization",
                    "question": (
                        f"What fictional fact is hidden by {drop} fixture {index}?"
                    ),
                    "public_claim_slots": [_slot(handle, "Masked fact.")],
                    "media_exposure_manifest": [],
                    "counterfactual_drop": drop,
                },
                "scoring_target": {
                    "answer_mode": "abstain",
                    "required_missing_modality": modality,
                    "required_missing_hop": hop,
                    "required_terms_by_claim": {},
                    "accepted_support": {},
                    "required_modality_stratum": "partial_masked",
                    "replay_group": None,
                    "counterfactual_drop": drop,
                },
            }
        )
    cases.extend(_failure_cases("sbc-direct-failure", direct=True))
    return cases


def generate_competence_suite() -> dict[str, Any]:
    """Generate the frozen, source-free public fictional suite."""

    rng = random.Random(GENERATOR_SEED)
    controller_finalizer = [
        *_controller_cases(rng),
        *_finalizer_cases(),
        *_failure_cases("sbc-runtime"),
    ]
    direct = _direct_cases()
    if len(controller_finalizer) != 51 or len(direct) != 30:
        raise AssertionError("frozen suite cardinality changed")
    suite: dict[str, Any] = {
        "schema_version": SUITE_SCHEMA,
        "suite_id": SUITE_ID,
        "generated_date": "2026-09-24",
        "generator": {
            "seed": GENERATOR_SEED,
            "algorithm": "stdlib-random-v1-fixed-order",
            "new_unseen_fixture_family": True,
            "frozen_before_model_execution": True,
            "model_used": False,
            "scientific_source_used": False,
            "evaluator_private_key_used": False,
        },
        "content_boundary": {
            "fictional_generated_primitives_only": True,
            "public_cases_only": True,
            "contains_scientific_family_content": False,
            "contains_real_benchmark_ground_truth": False,
            "contains_evaluator_private_benchmark_fields": False,
            "model_inputs_are_allowlisted_from_public_input_only": True,
        },
        "bindings": {
            "primary_controller": PRIMARY_BINDINGS["controller"].to_dict(),
            "primary_finalizer": PRIMARY_BINDINGS["finalizer"].to_dict(),
            "primary_direct": PRIMARY_BINDINGS["direct_av"].to_dict(),
            "fallback_controller": FALLBACK_BINDINGS["controller"].to_dict(),
            "fallback_finalizer": FALLBACK_BINDINGS["finalizer"].to_dict(),
            "fallback_direct": FALLBACK_BINDINGS["direct_av"].to_dict(),
        },
        "thresholds": {
            "controller_finalizer": CONTROLLER_FINALIZER_THRESHOLDS,
            "direct_av": DIRECT_AV_THRESHOLDS,
        },
        "cases": {
            "controller_finalizer": controller_finalizer,
            "direct_av": direct,
        },
        "execution_status": "NOT_RUN",
        "model_results_present": False,
    }
    for group in suite["cases"].values():
        for case in group:
            assert_public_surface(case["public_input"])
    suite["suite_hash"] = sha256_json(suite)
    return suite


def write_competence_suite(path: str | Path) -> dict[str, Any]:
    suite = generate_competence_suite()
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(suite, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return suite


def validate_competence_suite(suite: Mapping[str, Any]) -> None:
    if suite.get("schema_version") != SUITE_SCHEMA:
        raise EvaluationViolation("SUITE_SCHEMA_VERSION_MISMATCH")
    supplied_hash = suite.get("suite_hash")
    unhashed = dict(suite)
    unhashed.pop("suite_hash", None)
    if supplied_hash != sha256_json(unhashed):
        raise EvaluationViolation("SUITE_HASH_MISMATCH")
    cases = suite.get("cases")
    if not isinstance(cases, Mapping):
        raise EvaluationViolation("SUITE_CASES_MISSING")
    controller_cases = cases.get("controller_finalizer")
    direct_cases = cases.get("direct_av")
    if (
        not isinstance(controller_cases, list)
        or len(controller_cases)
        < CONTROLLER_FINALIZER_THRESHOLDS["minimum_cases"]
    ):
        raise EvaluationViolation("CONTROLLER_SUITE_TOO_SMALL")
    if (
        not isinstance(direct_cases, list)
        or sum(case.get("case_type") == "direct_av" for case in direct_cases)
        < DIRECT_AV_THRESHOLDS["minimum_cases"]
    ):
        raise EvaluationViolation("DIRECT_SUITE_TOO_SMALL")
    identifiers = [
        case.get("case_id") for group in cases.values() for case in group
    ]
    if any(not isinstance(value, str) for value in identifiers):
        raise EvaluationViolation("SUITE_CASE_ID_INVALID")
    if len(set(identifiers)) != len(identifiers):
        raise EvaluationViolation("SUITE_CASE_ID_DUPLICATE")
    if suite.get("thresholds") != {
        "controller_finalizer": CONTROLLER_FINALIZER_THRESHOLDS,
        "direct_av": DIRECT_AV_THRESHOLDS,
    }:
        raise EvaluationViolation("SUITE_THRESHOLDS_CHANGED")
    for group in cases.values():
        for case in group:
            if set(case) != {
                "case_id",
                "case_type",
                "stratum",
                "public_input",
                "scoring_target",
            }:
                raise EvaluationViolation("SUITE_CASE_FIELD_SET")
            assert_public_surface(case["public_input"])


def model_public_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """Return exactly the allowlisted case material suitable for a model."""

    value = {
        "case_type": case["case_type"],
        "public_input": copy.deepcopy(case["public_input"]),
    }
    assert_public_surface(value)
    return value


def _fraction(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _binding_from_dict(value: Mapping[str, Any]) -> ModelBinding:
    return ModelBinding(
        repo_id=str(value["repo_id"]),
        revision=str(value["revision"]),
        role=str(value["role"]),
        processor_revision=str(value["processor_revision"]),
        tokenizer_revision=str(value["tokenizer_revision"]),
    )


def _provenance(result: Mapping[str, Any]) -> OutputProvenance:
    raw = result.get("output_provenance")
    if not isinstance(raw, Mapping):
        return OutputProvenance(model_authored_paths=frozenset())
    return OutputProvenance(
        model_authored_paths=frozenset(raw.get("model_authored_paths", [])),
        deterministic_paths=frozenset(raw.get("deterministic_paths", [])),
        copied_paths=frozenset(raw.get("copied_paths", [])),
    )


def _score_claim_support(
    envelope: Mapping[str, Any],
    target: Mapping[str, Any],
) -> tuple[bool, int]:
    required = target.get("required_terms_by_claim", {})
    support = target.get("accepted_support", {})
    claims = {
        claim["registered_claim_id"]: claim
        for claim in envelope["final_answer"]["claims"]
    }
    unsupported = 0
    for handle, terms in required.items():
        claim = claims.get(handle)
        if claim is None:
            unsupported += 1
            continue
        text = claim["text"].casefold()
        if any(str(term).casefold() not in text for term in terms):
            unsupported += 1
        citations = {
            item["observation_id"] for item in claim["citations"]
        }
        if not citations or not citations <= set(support.get(handle, [])):
            unsupported += 1
    return unsupported == 0, unsupported


def _score_final_result(
    case: Mapping[str, Any],
    result: Mapping[str, Any],
) -> dict[str, Any]:
    output = result.get("raw_output")
    if not isinstance(output, str):
        return {"structured_valid": False, "error_code": "RAW_OUTPUT_MISSING"}
    public = case["public_input"]
    try:
        value = parse_strict_json(output, maximum_bytes=64_000)
        envelope = validate_final_answer_envelope(
            value,
            claim_handles=[
                item["claim_handle"] for item in public["public_claim_slots"]
            ],
            evidence_lock=ObservedEvidenceLock(
                public.get("observed_evidence", [])
                or [
                    {
                        "observation_id": item["exposure_id"],
                        "interval": item["interval"],
                        "modalities": item["modalities"],
                        "payload": {"exposure": "direct_av"},
                    }
                    for item in public.get("media_exposure_manifest", [])
                ]
            ),
            provenance=_provenance(result),
        )
    except SchemaViolation as exc:
        return {
            "structured_valid": False,
            "error_code": exc.code,
            "private_exposure": exc.code
            in {"EVALUATOR_PRIVATE_FIELD_EXPOSED", "PRIVATE_IDENTIFIER_EXPOSED"},
            "out_of_exposure_citation": exc.code
            in {
                "CITATION_NOT_OBSERVED",
                "CITATION_INTERVAL_MISMATCH",
                "CITATION_MODALITY_MISMATCH",
            },
            "deterministic_answer_substitution": exc.code
            in {
                "DETERMINISTIC_ANSWER_SUBSTITUTION",
                "ANSWER_AUTHORSHIP_NOT_MODEL",
            },
        }
    target = case["scoring_target"]
    answer_mode_correct = (
        envelope["final_answer"]["answer_mode"] == target["answer_mode"]
    )
    if target["answer_mode"] == "abstain":
        diagnosis = envelope["final_answer"]["diagnosis"]
        semantic_success = (
            answer_mode_correct
            and target["required_missing_modality"]
            in {
                modality
                for modality, probability in diagnosis[
                    "modality_probabilities"
                ].items()
                if probability >= 0.5
            }
            and target["required_missing_hop"] in diagnosis["hop_types"]
        )
        unsupported = 0
    else:
        support_correct, unsupported = _score_claim_support(envelope, target)
        semantic_success = answer_mode_correct and support_correct
    return {
        "structured_valid": True,
        "semantic_success": semantic_success,
        "unsupported_claims": unsupported,
        "parsed_output_hash": sha256_json(envelope),
        "envelope": envelope,
        "private_exposure": False,
        "out_of_exposure_citation": False,
        "deterministic_answer_substitution": False,
        "observed_evidence_lock": True,
    }


def _score_controller_result(
    case: Mapping[str, Any],
    result: Mapping[str, Any],
) -> dict[str, Any]:
    output = result.get("raw_output")
    if not isinstance(output, str):
        return {"structured_valid": False, "error_code": "RAW_OUTPUT_MISSING"}
    try:
        value = parse_strict_json(output, maximum_bytes=8_192)
        if not isinstance(value, Mapping) or set(value) != {
            "evidence_state",
            "action_index",
        }:
            raise SchemaViolation("CONTROLLER_DECISION_FIELD_SET")
        action_index = value["action_index"]
        menu = case["public_input"]["action_menu"]
        if (
            isinstance(action_index, bool)
            or not isinstance(action_index, int)
            or not 0 <= action_index < len(menu)
        ):
            raise SchemaViolation("CONTROLLER_ACTION_INDEX_INVALID")
        state = validate_evidence_state(
            value["evidence_state"],
            allowed_claim_handles=[
                item["claim_handle"]
                for item in case["public_input"]["public_claim_slots"]
            ],
        )
    except SchemaViolation as exc:
        return {
            "structured_valid": False,
            "error_code": exc.code,
            "private_exposure": exc.code
            in {"EVALUATOR_PRIVATE_FIELD_EXPOSED", "PRIVATE_IDENTIFIER_EXPOSED"},
        }
    target = case["scoring_target"]
    expected_state = target["expected_evidence_state"]
    component_correct = {
        field: state[field] == expected_state[field]
        for field in EVIDENCE_STATE_FIELDS
    }
    return {
        "structured_valid": True,
        "action_correct": action_index == target["expected_action_index"],
        "state_component_correct": component_correct,
        "exact_six_field_state": all(component_correct.values()),
        "private_exposure": False,
        "restoration_reacquisition_success": (
            action_index == target["expected_action_index"]
            if target["restoration_reacquisition"]
            else None
        ),
    }


def _score_failure_result(
    case: Mapping[str, Any],
    result: Mapping[str, Any],
) -> dict[str, Any]:
    target = case["scoring_target"]
    expected_status = str(target["expected_inference_status"])
    actual_status = str(result.get("inference_status", ""))
    model_called = result.get("model_was_called")
    if case["stratum"] == "malformed_output":
        raw = result.get("raw_output")
        rejected = False
        if isinstance(raw, str):
            try:
                parse_strict_json(raw, maximum_bytes=64_000)
            except SchemaViolation:
                rejected = True
        fixture_pass = (
            actual_status == expected_status
            and model_called is True
            and rejected
            and result.get("final_answer") is None
        )
    elif case["stratum"] == "malformed_manifest":
        fixture_pass = (
            actual_status == expected_status
            and model_called is False
            and result.get("final_answer") is None
        )
    else:
        fixture_pass = (
            actual_status == expected_status
            and model_called is target["expected_model_called"]
            and result.get("final_answer") is None
        )
    return {
        "failure_fixture_pass": fixture_pass,
        "identity_or_injected_failure_pass": fixture_pass,
        "structured_valid": None,
    }


def _validate_result_execution_metadata(
    result: Mapping[str, Any],
) -> None:
    repairs = result.get("schema_repairs_used")
    calls = result.get("model_calls_used")
    model_called = result.get("model_was_called", True)
    if (
        isinstance(repairs, bool)
        or not isinstance(repairs, int)
        or repairs not in {0, 1}
    ):
        raise EvaluationViolation("RESULT_SCHEMA_REPAIR_COUNT_INVALID")
    if (
        isinstance(calls, bool)
        or not isinstance(calls, int)
        or calls < 0
        or calls > 2
    ):
        raise EvaluationViolation("RESULT_MODEL_CALL_COUNT_INVALID")
    if repairs == 1 and result.get("repair_kind") != "schema_only":
        raise EvaluationViolation("RESULT_SEMANTIC_REPAIR_FORBIDDEN")
    if repairs == 0 and result.get("repair_kind") not in {None, "none"}:
        raise EvaluationViolation("RESULT_REPAIR_KIND_INCONSISTENT")
    if model_called is False and calls != 0:
        raise EvaluationViolation("RESULT_CALL_COUNT_WITHOUT_MODEL_CALL")
    if model_called is True and calls < 1:
        raise EvaluationViolation("RESULT_MODEL_CALL_NOT_RECORDED")
    if repairs > calls:
        raise EvaluationViolation("RESULT_REPAIR_EXCEEDS_CALLS")


def _verify_submission_binding(
    suite: Mapping[str, Any], submission: Mapping[str, Any]
) -> None:
    group_name = submission.get("suite_group")
    key = submission.get("binding_key")
    bindings = suite["bindings"]
    allowed_keys = {
        "controller_finalizer": {
            "primary_controller",
            "fallback_controller",
        },
        "direct_av": {"primary_direct", "fallback_direct"},
    }
    if key not in allowed_keys.get(str(group_name), set()):
        raise EvaluationViolation("SUBMISSION_BINDING_KEY_UNKNOWN")
    if submission.get("load_status") != LoadStatus.LOADED_VERIFIED:
        raise EvaluationViolation("SUBMISSION_LOAD_NOT_VERIFIED")
    expected = _binding_from_dict(bindings[key])
    raw_observed = submission.get("observed_binding")
    if not isinstance(raw_observed, Mapping):
        raise EvaluationViolation("SUBMISSION_BINDING_MISSING")
    observed = _binding_from_dict(raw_observed)
    if expected.to_dict() != observed.to_dict():
        raise EvaluationViolation("SUBMISSION_SNAPSHOT_MISMATCH")
    if group_name == "controller_finalizer":
        expected_finalizer_key = (
            "primary_finalizer"
            if key == "primary_controller"
            else "fallback_finalizer"
        )
        if submission.get("finalizer_binding_key") != expected_finalizer_key:
            raise EvaluationViolation("SUBMISSION_FINALIZER_BINDING_KEY_MISMATCH")
        raw_finalizer = submission.get("observed_finalizer_binding")
        if not isinstance(raw_finalizer, Mapping):
            raise EvaluationViolation("SUBMISSION_FINALIZER_BINDING_MISSING")
        expected_finalizer = _binding_from_dict(bindings[expected_finalizer_key])
        observed_finalizer = _binding_from_dict(raw_finalizer)
        if expected_finalizer.to_dict() != observed_finalizer.to_dict():
            raise EvaluationViolation("SUBMISSION_FINALIZER_SNAPSHOT_MISMATCH")
        if (
            expected.repo_id,
            expected.revision,
            expected.resolved_processor_revision,
            expected.resolved_tokenizer_revision,
        ) != (
            expected_finalizer.repo_id,
            expected_finalizer.revision,
            expected_finalizer.resolved_processor_revision,
            expected_finalizer.resolved_tokenizer_revision,
        ):
            raise EvaluationViolation("SUITE_SAME_BACKBONE_BINDING_BROKEN")


def _validate_restoration_isolation(
    checks: Sequence[Mapping[str, Any]],
) -> int:
    if not checks:
        return 1
    failures = 0
    for check in checks:
        try:
            attestations = [
                IsolationAttestation(**check["restored"]["isolation_attestation"]),
                IsolationAttestation(
                    **check["no_trigger"]["isolation_attestation"]
                ),
            ]
            assert_isolated(attestations)
            hashes = {
                check["restored"].get("public_prefix_hash_through_checkpoint"),
                check["no_trigger"].get(
                    "public_prefix_hash_through_checkpoint"
                ),
            }
            if len(hashes) != 1 or None in hashes:
                failures += 1
        except (IsolationViolation, KeyError, TypeError):
            failures += 1
    return failures


def evaluate_competence_submission(
    suite: Mapping[str, Any],
    submission: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate recorded model outputs without invoking any model."""

    validate_competence_suite(suite)
    if submission.get("suite_hash") != suite["suite_hash"]:
        raise EvaluationViolation("SUBMISSION_SUITE_HASH_MISMATCH")
    group_name = submission.get("suite_group")
    if group_name not in {"controller_finalizer", "direct_av"}:
        raise EvaluationViolation("SUBMISSION_GROUP_INVALID")
    _verify_submission_binding(suite, submission)
    case_rows = suite["cases"][group_name]
    expected_ids = {case["case_id"] for case in case_rows}
    result_rows = submission.get("results")
    if not isinstance(result_rows, list):
        raise EvaluationViolation("SUBMISSION_RESULTS_NOT_LIST")
    by_id: dict[str, Mapping[str, Any]] = {}
    for row in result_rows:
        if not isinstance(row, Mapping):
            raise EvaluationViolation("SUBMISSION_RESULT_NOT_OBJECT")
        case_id = row.get("case_id")
        if case_id in by_id:
            raise EvaluationViolation("SUBMISSION_RESULT_DUPLICATE")
        _validate_result_execution_metadata(row)
        by_id[str(case_id)] = row
    if set(by_id) != expected_ids:
        raise EvaluationViolation("SUBMISSION_CASE_SET_MISMATCH")

    scored: list[dict[str, Any]] = []
    substitutions = 0
    for case in case_rows:
        result = by_id[case["case_id"]]
        if "fallback_output" in result or result.get(
            "deterministic_answer_substitution"
        ):
            substitutions += 1
        if case["case_type"] == "controller":
            score = _score_controller_result(case, result)
        elif case["case_type"] in {"finalizer", "direct_av"}:
            score = _score_final_result(case, result)
        else:
            score = _score_failure_result(case, result)
        scored.append(
            {
                "case_id": case["case_id"],
                "case_type": case["case_type"],
                "stratum": case["stratum"],
                **score,
            }
        )

    private_exposures = sum(bool(row.get("private_exposure")) for row in scored)
    unsupported_claims = sum(int(row.get("unsupported_claims", 0)) for row in scored)
    valid_rows = [row for row in scored if row["case_type"] != "runtime_failure"]
    structured = [row for row in valid_rows if row.get("structured_valid") is not None]
    failure_rows = [row for row in scored if row["case_type"] == "runtime_failure"]

    if group_name == "controller_finalizer":
        controller = [row for row in scored if row["case_type"] == "controller"]
        finalizer = [row for row in scored if row["case_type"] == "finalizer"]
        action_strata: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in controller:
            action_strata[row["stratum"]].append(row)
        state_components = {
            field: _fraction(
                sum(
                    bool(row.get("state_component_correct", {}).get(field))
                    for row in controller
                ),
                len(controller),
            )
            for field in EVIDENCE_STATE_FIELDS
        }
        oracle = [
            row
            for row, case in zip(scored, case_rows, strict=True)
            if case["case_type"] == "finalizer"
            and case["scoring_target"].get("oracle_complete")
        ]
        blocked = [
            row
            for row in finalizer
            if row["stratum"] == "blocked_partial"
        ]
        restoration = [
            row
            for row, case in zip(scored, case_rows, strict=True)
            if case["scoring_target"].get("restoration_reacquisition")
        ]
        metrics = {
            "case_count": len(scored),
            "deterministic_parser_schema_failure_fixtures": _fraction(
                sum(bool(row.get("failure_fixture_pass")) for row in failure_rows),
                len(failure_rows),
            ),
            "valid_structured_model_calls": _fraction(
                sum(bool(row.get("structured_valid")) for row in structured),
                len(structured),
            ),
            "correct_first_actions_overall": _fraction(
                sum(bool(row.get("action_correct")) for row in controller),
                len(controller),
            ),
            "correct_first_actions_by_stratum": {
                key: _fraction(
                    sum(bool(row.get("action_correct")) for row in rows),
                    len(rows),
                )
                for key, rows in sorted(action_strata.items())
            },
            "exact_six_field_state": _fraction(
                sum(bool(row.get("exact_six_field_state")) for row in controller),
                len(controller),
            ),
            "state_component_accuracy": state_components,
            "oracle_supported_answer": _fraction(
                sum(bool(row.get("semantic_success")) for row in oracle),
                len(oracle),
            ),
            "blocked_partial_correct_abstention": _fraction(
                sum(bool(row.get("semantic_success")) for row in blocked),
                len(blocked),
            ),
            "restoration_reacquisition": _fraction(
                sum(
                    bool(
                        row.get("semantic_success")
                        or row.get("restoration_reacquisition_success")
                    )
                    for row in restoration
                ),
                len(restoration),
            ),
            "unsupported_required_claims": unsupported_claims,
            "private_field_exposures": private_exposures,
            "deterministic_answer_substitutions": substitutions
            + sum(
                bool(row.get("deterministic_answer_substitution"))
                for row in scored
            ),
            "identity_and_injected_failure_fail_closed": _fraction(
                sum(
                    bool(row.get("identity_or_injected_failure_pass"))
                    for row in failure_rows
                ),
                len(failure_rows),
            ),
            "cross_state_isolation_failures": _validate_restoration_isolation(
                submission.get("restoration_isolation_checks", [])
            ),
        }
        thresholds = CONTROLLER_FINALIZER_THRESHOLDS
        checks = {
            "minimum_cases": metrics["case_count"] >= thresholds["minimum_cases"],
            "failure_fixtures": metrics[
                "deterministic_parser_schema_failure_fixtures"
            ]
            == thresholds["deterministic_parser_schema_failure_fixtures"],
            "valid_structured": metrics["valid_structured_model_calls"]
            is not None
            and metrics["valid_structured_model_calls"]
            >= thresholds["valid_structured_model_calls_min"],
            "actions_overall": metrics["correct_first_actions_overall"]
            is not None
            and metrics["correct_first_actions_overall"]
            >= thresholds["correct_first_actions_overall_min"],
            "actions_each_stratum": all(
                value is not None
                and value >= thresholds["correct_first_actions_each_stratum_min"]
                for value in metrics["correct_first_actions_by_stratum"].values()
            ),
            "joint_state": metrics["exact_six_field_state"] is not None
            and metrics["exact_six_field_state"]
            >= thresholds["exact_six_field_state_min"],
            "state_components": all(
                value is not None
                and value >= thresholds["each_state_component_min"]
                for value in state_components.values()
            ),
            "oracle": metrics["oracle_supported_answer"] is not None
            and metrics["oracle_supported_answer"]
            >= thresholds["oracle_supported_answer_min"],
            "blocked_partial": metrics["blocked_partial_correct_abstention"]
            is not None
            and metrics["blocked_partial_correct_abstention"]
            >= thresholds["blocked_partial_correct_abstention_min"],
            "restoration": metrics["restoration_reacquisition"] is not None
            and metrics["restoration_reacquisition"]
            >= thresholds["restoration_reacquisition_min"],
            "unsupported_claims": unsupported_claims
            <= thresholds["unsupported_required_claims_max"],
            "private_exposure": private_exposures
            <= thresholds["private_field_exposures_max"],
            "no_substitution": metrics["deterministic_answer_substitutions"]
            <= thresholds["deterministic_answer_substitutions_max"],
            "fail_closed": metrics[
                "identity_and_injected_failure_fail_closed"
            ]
            == thresholds["identity_and_injected_failure_fail_closed"],
            "cross_state_isolation": metrics[
                "cross_state_isolation_failures"
            ]
            == 0,
        }
    else:
        substantive = [row for row in scored if row["case_type"] == "direct_av"]
        complete = [
            row
            for row, case in zip(scored, case_rows, strict=True)
            if case["case_type"] == "direct_av"
            and case["scoring_target"]["answer_mode"] == "answer"
        ]
        partial = [
            row
            for row, case in zip(scored, case_rows, strict=True)
            if case["case_type"] == "direct_av"
            and case["scoring_target"]["answer_mode"] == "abstain"
        ]
        modality_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
        replay_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
        drop_rows: list[dict[str, Any]] = []
        for row, case in zip(scored, case_rows, strict=True):
            target = case["scoring_target"]
            if case["case_type"] != "direct_av":
                continue
            if target.get("answer_mode") == "answer":
                modality_rows[target["required_modality_stratum"]].append(row)
            if target.get("replay_group"):
                replay_rows[target["replay_group"]].append(row)
            if target.get("counterfactual_drop"):
                drop_rows.append(row)
        replay_passes = [
            len(rows) == 2
            and all(row.get("structured_valid") for row in rows)
            and len({row.get("parsed_output_hash") for row in rows}) == 1
            for rows in replay_rows.values()
        ]
        metrics = {
            "case_count": len(scored),
            "substantive_case_count": len(substantive),
            "processor_manifest_failure_fixtures": _fraction(
                sum(bool(row.get("failure_fixture_pass")) for row in failure_rows),
                len(failure_rows),
            ),
            "valid_final_outputs": _fraction(
                sum(bool(row.get("structured_valid")) for row in substantive),
                len(substantive),
            ),
            "complete_evidence_supported_answer": _fraction(
                sum(bool(row.get("semantic_success")) for row in complete),
                len(complete),
            ),
            "modality_stratum_supported_answer": {
                key: _fraction(
                    sum(bool(row.get("semantic_success")) for row in rows),
                    len(rows),
                )
                for key, rows in sorted(modality_rows.items())
            },
            "partial_masked_correct_abstention": _fraction(
                sum(bool(row.get("semantic_success")) for row in partial),
                len(partial),
            ),
            "unsupported_required_claims": unsupported_claims,
            "out_of_exposure_citations": sum(
                bool(row.get("out_of_exposure_citation")) for row in scored
            ),
            "observed_evidence_lock": _fraction(
                sum(bool(row.get("observed_evidence_lock")) for row in substantive),
                len(substantive),
            ),
            "required_modality_drop_counterfactuals": _fraction(
                sum(bool(row.get("semantic_success")) for row in drop_rows),
                len(drop_rows),
            ),
            "deterministic_local_replay_parsed_output": _fraction(
                sum(replay_passes), len(replay_passes)
            ),
            "deterministic_answer_substitutions": substitutions
            + sum(
                bool(row.get("deterministic_answer_substitution"))
                for row in scored
            ),
            "private_field_exposures": private_exposures,
        }
        thresholds = DIRECT_AV_THRESHOLDS
        checks = {
            "minimum_cases": metrics["substantive_case_count"]
            >= thresholds["minimum_cases"],
            "manifest_failures": metrics[
                "processor_manifest_failure_fixtures"
            ]
            == thresholds["processor_manifest_failure_fixtures"],
            "valid_outputs": metrics["valid_final_outputs"] is not None
            and metrics["valid_final_outputs"]
            >= thresholds["valid_final_outputs_min"],
            "complete": metrics["complete_evidence_supported_answer"] is not None
            and metrics["complete_evidence_supported_answer"]
            >= thresholds["complete_evidence_supported_answer_min"],
            "modality_strata": all(
                value is not None
                and value
                >= thresholds["each_modality_stratum_supported_answer_min"]
                for value in metrics[
                    "modality_stratum_supported_answer"
                ].values()
            ),
            "partial": metrics["partial_masked_correct_abstention"] is not None
            and metrics["partial_masked_correct_abstention"]
            >= thresholds["partial_masked_correct_abstention_min"],
            "unsupported": unsupported_claims
            <= thresholds["unsupported_required_claims_max"],
            "citations": metrics["out_of_exposure_citations"]
            <= thresholds["out_of_exposure_citations_max"],
            "evidence_lock": metrics["observed_evidence_lock"]
            == thresholds["observed_evidence_lock"],
            "modality_drops": metrics[
                "required_modality_drop_counterfactuals"
            ]
            == thresholds["required_modality_drop_counterfactuals"],
            "replay": metrics["deterministic_local_replay_parsed_output"]
            == thresholds["deterministic_local_replay_parsed_output"],
            "no_substitution": metrics["deterministic_answer_substitutions"] == 0,
            "private_exposure": metrics["private_field_exposures"] == 0,
        }
    return {
        "schema_version": "av-trace.strong-baseline-competence-report/1.0",
        "suite_id": suite["suite_id"],
        "suite_hash": suite["suite_hash"],
        "suite_group": group_name,
        "binding_key": submission["binding_key"],
        "metrics": metrics,
        "gate_checks": checks,
        "decision": (
            "STRONG_BASELINE_COMPETENCE_PASS"
            if all(checks.values())
            else "STRONG_BASELINE_COMPETENCE_REPAIR"
        ),
        "case_scores": scored,
        "model_inference_executed_by_evaluator": False,
    }


def load_suite(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise EvaluationViolation("SUITE_NOT_OBJECT")
    validate_competence_suite(value)
    return value


def load_submission(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise EvaluationViolation("SUBMISSION_NOT_OBJECT")
    return value


def failure_summary(report: Mapping[str, Any]) -> Counter[str]:
    """Return stable counts useful to a caller without changing the verdict."""

    return Counter(
        str(row.get("error_code"))
        for row in report.get("case_scores", [])
        if row.get("error_code")
    )
