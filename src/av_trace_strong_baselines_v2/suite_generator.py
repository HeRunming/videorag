"""GENERATOR for a future unseen, sealed, public-fictional v2 suite.

Task 175 installed the prospective generator without instantiating it.
Task 176 may instantiate it exactly once with a newly recorded random seed,
seal the public/private split before inference, and validate only public
content plus aggregate private-label composition.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import shutil
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from av_trace_strong_baselines.competence import (
    CONTROLLER_FINALIZER_THRESHOLDS,
)
from av_trace_strong_baselines.contracts import (
    PRIMARY_BINDINGS,
    CommonBudget,
    canonical_json_bytes,
    sha256_json,
)
from av_trace_strong_baselines.errors import StrongBaselineError
from av_trace_strong_baselines.security import assert_public_surface

from .contracts import ADAPTER_SCHEMA_VERSION

GENERATOR_SCHEMA_VERSION = "av-trace.granite-v2-suite-generator/2.0"
PUBLIC_SUITE_SCHEMA_VERSION = "av-trace.granite-v2-public-suite/2.0"
PRIVATE_LABEL_SCHEMA_VERSION = "av-trace.granite-v2-private-labels/2.0"
SEAL_SCHEMA_VERSION = "av-trace.granite-v2-suite-seal/2.0"
CONSUMED_DEVELOPMENT_SEEDS = frozenset({15820260924})

COLORS = (
    "cerulean",
    "umber",
    "violet",
    "amber",
    "jade",
    "coral",
    "indigo",
    "pearl",
)
SHAPES = (
    "heptagon",
    "spiral",
    "trapezoid",
    "crescent",
    "rhombus",
    "starburst",
    "chevron",
    "ring",
)
CODES = (
    "aurora nine",
    "cinder path",
    "delta moss",
    "echo lattice",
    "frost key",
    "glimmer arc",
    "harbor six",
    "ion meadow",
)
SOUNDS = (
    "four soft taps",
    "a ceramic chime",
    "two low pulses",
    "a paper rustle",
    "a short whistle",
    "three wooden knocks",
    "a glass ping",
    "one rising tone",
)

CONTROLLER_STRATA = (
    "route_vision",
    "route_speech",
    "route_ambient",
    "observe_pointer",
    "blocked_status",
    "restoration_reacquire",
    "no_trigger",
    "finalize_ready",
)
FINALIZER_STRATA = (
    "oracle_complete",
    "restoration_complete",
    "blocked_partial",
)
RUNTIME_FIXTURES = (
    ("malformed_action_factor", "INVALID_OUTPUT", True),
    ("malformed_state_factor", "INVALID_OUTPUT", True),
    ("malformed_claim_factor", "INVALID_OUTPUT", True),
    ("malformed_citation_factor", "INVALID_OUTPUT", True),
    ("wrong_snapshot", "SNAPSHOT_MISMATCH", False),
    ("provider_failure", "PROVIDER_FAILURE", True),
    ("timeout", "TIMEOUT", True),
    ("process_failure", "PROCESS_FAILURE", True),
    ("oom", "OOM", True),
    ("budget_exhausted", "BUDGET_EXHAUSTED", False),
    ("cross_factor_semantic_retry", "INVALID_OUTPUT", True),
)

CONTROLLER_PROMPT_POLICY = (
    "Use only the supplied public case and exact frozen action menu. "
    "Choose exactly one menu entry through its no-argument native function. "
    "Author the six evidence-state heads independently using only case-local "
    "enums. Never invent evidence or an answer. A known unobserved pointer "
    "requires inspect_clip. A prior channel_unavailable response requires "
    "get_channel_status. After the public protocol checkpoint, retry an "
    "available matching route only for restoration_reacquire; for no_trigger "
    "with no acquisition route, finalize an abstention. Directly sufficient "
    "observations require finalize_answer. Otherwise choose the route matching "
    "the missing modality and hop. Projection may reject but never repair."
)

FINALIZER_PROMPT_POLICY = (
    "Use only the supplied public question, claim slots, and observed "
    "evidence. Author disposition, answer text, claim drafts, citation "
    "selections, and diagnosis independently under their exact factor "
    "schemas. Never invent evidence, citations, or facts. Answer only when "
    "the observed payload directly supports every required claim. Cite only "
    "observed IDs. With incomplete evidence, abstain with empty answer, "
    "claims, and citations, and diagnose the requested missing modality and "
    "hop. Mechanical serialization may copy selected public citation metadata "
    "but may not substitute or rewrite semantic content."
)

PROMPT_POLICY = {
    "schema_version": "av-trace.granite-v2-prompt-policy/1.0",
    "controller": CONTROLLER_PROMPT_POLICY,
    "finalizer": FINALIZER_PROMPT_POLICY,
    "public_projection_only": True,
    "factor_schema_embedded_by_adapter": True,
    "private_labels_exposed": False,
    "semantic_retries": 0,
    "cross_factor_retries": 0,
    "maximum_schema_only_retries_per_factor": 1,
}
PROMPT_POLICY_SHA256 = sha256_json(PROMPT_POLICY)


@dataclass(frozen=True)
class FutureSuiteBundle:
    public_suite: dict[str, Any]
    private_labels: dict[str, Any]
    generation_manifest: dict[str, Any]


def generator_contract() -> dict[str, Any]:
    """Describe capabilities without instantiating a suite."""

    return {
        "schema_version": GENERATOR_SCHEMA_VERSION,
        "adapter_schema_version": ADAPTER_SCHEMA_VERSION,
        "requires_caller_supplied_new_seed": True,
        "consumed_seed_reuse_forbidden": True,
        "public_private_split": True,
        "seal_before_execution": True,
        "scientific_sources_used": False,
        "fixture_domain": "public_fictional_abstract_shapes_colors_codes_sounds",
        "planned_counts": {
            "controller": 24,
            "finalizer": 16,
            "runtime_failure": 11,
        },
        "controller_strata": list(CONTROLLER_STRATA),
        "finalizer_strata": {
            "oracle_complete": 8,
            "restoration_complete": 4,
            "blocked_partial": 4,
        },
        "prompt_policy_sha256": PROMPT_POLICY_SHA256,
        "gate_c_thresholds": dict(CONTROLLER_FINALIZER_THRESHOLDS),
        "task175_instantiated": False,
        "task175_evaluated": False,
    }


def validate_future_seed(seed: int) -> int:
    """Reject the consumed Task-158/172 seed and weak/non-positive values."""

    if (
        isinstance(seed, bool)
        or not isinstance(seed, int)
        or seed.bit_length() < 128
        or seed in CONSUMED_DEVELOPMENT_SEEDS
    ):
        raise StrongBaselineError("FUTURE_SUITE_SEED_NOT_NEW")
    return seed


def model_public_case(case: dict[str, Any]) -> dict[str, Any]:
    """Return only model-visible case type and public input."""

    value = {
        "case_type": case["case_type"],
        "public_input": case["public_input"],
    }
    assert_public_surface(value)
    return value


def _search(tool: str, query: str) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "query": query,
        "top_k": 5,
        "time_range": {"start_s": 0.0, "end_s": 120.0},
        "exclude_result_ids": [],
    }
    if tool == "search_speech":
        arguments["speaker_hint"] = None
    return {"tool": tool, "arguments": arguments}


def _finalize() -> dict[str, Any]:
    return {"tool": "finalize", "arguments": {}}


def _status(channel: str) -> dict[str, Any]:
    return {
        "tool": "get_channel_status",
        "arguments": {"channels": [channel]},
    }


def _inspect(start: float) -> dict[str, Any]:
    return {
        "tool": "inspect_clip",
        "arguments": {
            "interval": {"start_s": start, "end_s": start + 1.0},
            "include_video": True,
            "include_audio": False,
        },
    }


def _state(
    *,
    covered: list[str] | None = None,
    modalities: list[str] | None = None,
    hops: list[str] | None = None,
    cause: str,
    intent: str,
    sufficient: float = 0.0,
) -> dict[str, Any]:
    return {
        "p_sufficient": sufficient,
        "covered_claim_handles": covered or [],
        "missing_modalities": modalities or [],
        "missing_hops": hops or [],
        "missingness_cause": cause,
        "recovery_intent": intent,
    }


def _case_token(rng: random.Random, prefix: str, index: int) -> str:
    return f"{prefix}-{index:02d}-{rng.getrandbits(32):08x}"


def _aggregate_private_labels(
    labels: dict[str, Any],
    public_cases: list[dict[str, Any]],
) -> dict[str, Any]:
    by_id = {case["case_id"]: case for case in public_cases}
    controller_tools: Counter[str] = Counter()
    state_heads: dict[str, Counter[str]] = {
        "p_sufficient": Counter(),
        "covered_claim_count": Counter(),
        "missing_modalities": Counter(),
        "missing_hops": Counter(),
        "missingness_cause": Counter(),
        "recovery_intent": Counter(),
    }
    finalizer_modes: Counter[str] = Counter()
    finalizer_modalities: Counter[str] = Counter()
    finalizer_hops: Counter[str] = Counter()
    runtime_statuses: Counter[str] = Counter()
    runtime_called: Counter[str] = Counter()
    for case_id, label in labels.items():
        case = by_id[case_id]
        if case["case_type"] == "controller":
            action = case["public_input"]["action_menu"][
                label["expected_action_index"]
            ]
            controller_tools[action["tool"]] += 1
            state = label["expected_evidence_state"]
            state_heads["p_sufficient"][str(state["p_sufficient"])] += 1
            state_heads["covered_claim_count"][
                str(len(state["covered_claim_handles"]))
            ] += 1
            for value in state["missing_modalities"]:
                state_heads["missing_modalities"][value] += 1
            for value in state["missing_hops"]:
                state_heads["missing_hops"][value] += 1
            state_heads["missingness_cause"][state["missingness_cause"]] += 1
            state_heads["recovery_intent"][state["recovery_intent"]] += 1
        elif case["case_type"] == "finalizer":
            finalizer_modes[label["answer_mode"]] += 1
            modality = label.get("support_modality")
            if modality:
                finalizer_modalities[modality] += 1
            missing_modality = label.get("required_missing_modality")
            if missing_modality:
                finalizer_modalities[missing_modality] += 1
            missing_hop = label.get("required_missing_hop")
            if missing_hop:
                finalizer_hops[missing_hop] += 1
        else:
            runtime_statuses[label["expected_inference_status"]] += 1
            runtime_called[str(label["expected_model_called"]).lower()] += 1
    return {
        "controller_expected_tools": dict(sorted(controller_tools.items())),
        "controller_state_heads": {
            key: dict(sorted(value.items()))
            for key, value in state_heads.items()
        },
        "finalizer_answer_modes": dict(sorted(finalizer_modes.items())),
        "finalizer_required_modalities": dict(
            sorted(finalizer_modalities.items())
        ),
        "finalizer_required_missing_hops": dict(
            sorted(finalizer_hops.items())
        ),
        "runtime_expected_statuses": dict(sorted(runtime_statuses.items())),
        "runtime_expected_model_called": dict(sorted(runtime_called.items())),
    }


class FutureSealedSuiteGenerator:
    """Create a fresh public/private fixture pair and immutable seal."""

    def __init__(
        self,
        *,
        seed: int,
        suite_id: str,
        freeze_label: str,
        generated_date: str = "2026-10-02",
    ) -> None:
        seed = validate_future_seed(seed)
        if not suite_id.startswith("granite-v2-fictional-"):
            raise StrongBaselineError("FUTURE_SUITE_ID_INVALID")
        if not freeze_label.startswith("GRANITE_ADAPTER_V2_"):
            raise StrongBaselineError("FUTURE_SUITE_FREEZE_LABEL_INVALID")
        if generated_date != "2026-10-02":
            raise StrongBaselineError("FUTURE_SUITE_DATE_INVALID")
        self.seed = seed
        self.suite_id = suite_id
        self.freeze_label = freeze_label
        self.generated_date = generated_date

    def _controller_cases(
        self,
        rng: random.Random,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        public_cases: list[dict[str, Any]] = []
        labels: dict[str, Any] = {}
        for cycle in range(3):
            cycle_label = cycle + 1
            visual_token = _case_token(rng, "lumen", cycle_label)
            speech_token = _case_token(rng, "cipher", cycle_label)
            ambient_token = _case_token(rng, "echo", cycle_label)
            pointer_token = _case_token(rng, "glyph", cycle_label)
            blocked_token = _case_token(rng, "murmur", cycle_label)
            restored_token = _case_token(rng, "relay", cycle_label)
            guard_token = _case_token(rng, "cadence", cycle_label)
            ready_value = f"{rng.choice(COLORS)} {rng.choice(SHAPES)}"
            specs = (
                {
                    "stratum": "route_vision",
                    "question": (
                        f"Which visible emblem belongs to invented tile "
                        f"{visual_token}?"
                    ),
                    "description": "Visible emblem on an invented tile.",
                    "menu": [
                        _search(
                            "search_speech",
                            f"spoken alias for invented tile {visual_token}",
                        ),
                        _search(
                            "search_visual",
                            f"visible emblem on invented tile {visual_token}",
                        ),
                        _search(
                            "search_ambient_audio",
                            f"non-speech cue near invented tile {visual_token}",
                        ),
                    ],
                    "expected_tool": "search_visual",
                    "state": _state(
                        modalities=["vision"],
                        hops=["entity_identity"],
                        cause="evidence_accessible_but_not_found",
                        intent="search_vision",
                    ),
                },
                {
                    "stratum": "route_speech",
                    "question": (
                        f"Which invented call-sign is voiced for relay "
                        f"{speech_token}?"
                    ),
                    "description": "Voiced call-sign for an invented relay.",
                    "menu": [
                        _search(
                            "search_visual",
                            f"visible relay card {speech_token}",
                        ),
                        _search(
                            "search_speech",
                            f"voiced call-sign for invented relay {speech_token}",
                        ),
                        _search(
                            "search_ambient_audio",
                            f"background pulse by invented relay {speech_token}",
                        ),
                    ],
                    "expected_tool": "search_speech",
                    "state": _state(
                        modalities=["speech"],
                        hops=["speech_content"],
                        cause="evidence_accessible_but_not_found",
                        intent="search_speech",
                    ),
                },
                {
                    "stratum": "route_ambient",
                    "question": (
                        f"Which non-speech cue follows invented marker "
                        f"{ambient_token}?"
                    ),
                    "description": "Non-speech cue after an invented marker.",
                    "menu": [
                        _search(
                            "search_visual",
                            f"visible marker event {ambient_token}",
                        ),
                        _search(
                            "search_speech",
                            f"spoken description of cue {ambient_token}",
                        ),
                        _search(
                            "search_ambient_audio",
                            f"non-speech cue following marker {ambient_token}",
                        ),
                    ],
                    "expected_tool": "search_ambient_audio",
                    "state": _state(
                        modalities=["ambient"],
                        hops=["ambient_event"],
                        cause="evidence_accessible_but_not_found",
                        intent="search_ambient",
                    ),
                },
                {
                    "stratum": "observe_pointer",
                    "question": (
                        f"Which shape is drawn inside invented frame "
                        f"{pointer_token}?"
                    ),
                    "description": "Shape inside an invented frame.",
                    "menu": [
                        _inspect(33.0 + cycle * 3.0),
                        _search(
                            "search_visual",
                            f"alternate distant view of frame {pointer_token}",
                        ),
                        _finalize(),
                    ],
                    "expected_tool": "inspect_clip",
                    "pointers": [
                        {
                            "pointer_id": f"public.pointer.g2.{cycle_label}",
                            "interval": {
                                "start_s": 33.0 + cycle * 3.0,
                                "end_s": 34.0 + cycle * 3.0,
                            },
                            "modality": "vision",
                            "citable": False,
                        }
                    ],
                    "state": _state(
                        modalities=["vision"],
                        hops=["event_detection"],
                        cause="evidence_accessible_but_not_found",
                        intent="observe_pointer",
                    ),
                },
                {
                    "stratum": "blocked_status",
                    "question": (
                        f"Which invented motto is voiced in chamber "
                        f"{blocked_token}?"
                    ),
                    "description": "Voiced motto in an invented chamber.",
                    "menu": [
                        _search(
                            "search_speech",
                            f"alternate motto route {blocked_token}",
                        ),
                        _status("speech"),
                        _finalize(),
                    ],
                    "expected_tool": "get_channel_status",
                    "history": [
                        {
                            "action": _search(
                                "search_speech",
                                f"motto in invented chamber {blocked_token}",
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
                    "state": _state(
                        modalities=["speech"],
                        hops=["speech_content"],
                        cause="evidence_in_source_but_inaccessible",
                        intent="check_channel_status",
                    ),
                },
                {
                    "stratum": "restoration_reacquire",
                    "question": (
                        f"Which invented passcode becomes reachable after "
                        f"checkpoint {restored_token}?"
                    ),
                    "description": "Passcode on a restored invented route.",
                    "menu": [
                        _search(
                            "search_speech",
                            f"reacquire restored passcode {restored_token}",
                        ),
                        _status("speech"),
                        _finalize(),
                    ],
                    "expected_tool": "search_speech",
                    "history": [
                        {
                            "event_type": "protocol_checkpoint",
                            "event_version": "2.0.0",
                            "message": "Scheduled protocol checkpoint completed.",
                            "cost": 0.0,
                        }
                    ],
                    "state": _state(
                        modalities=["speech"],
                        hops=["speech_content"],
                        cause="evidence_in_source_but_inaccessible",
                        intent="retry_restored_route",
                    ),
                },
                {
                    "stratum": "no_trigger",
                    "question": (
                        f"Which invented cadence precedes marker "
                        f"{guard_token}?"
                    ),
                    "description": "Temporal order in an invented cadence.",
                    "menu": [_finalize()],
                    "expected_tool": "finalize",
                    "history": [
                        {
                            "event_type": "protocol_checkpoint",
                            "event_version": "2.0.0",
                            "message": "Scheduled protocol checkpoint completed.",
                            "cost": 0.0,
                        }
                    ],
                    "state": _state(
                        modalities=["vision"],
                        hops=["temporal_order"],
                        cause="evidence_accessible_but_not_found",
                        intent="finalize_abstain",
                    ),
                },
                {
                    "stratum": "finalize_ready",
                    "question": (
                        f"Which paired mark is stated for completed invented "
                        f"card {cycle_label}?"
                    ),
                    "description": "Paired mark on a completed invented card.",
                    "menu": [
                        _search(
                            "search_visual",
                            f"additional view of completed card {cycle_label}",
                        ),
                        _finalize(),
                    ],
                    "expected_tool": "finalize",
                    "observations": [
                        {
                            "observation_id": (
                                f"public.obs.g2.ready.{cycle_label}"
                            ),
                            "interval": {
                                "start_s": float(3 * cycle),
                                "end_s": float(3 * cycle + 1),
                            },
                            "modalities": ["vision"],
                            "payload": {
                                "text": (
                                    "The completed invented card states the "
                                    f"paired mark {ready_value}."
                                )
                            },
                        }
                    ],
                    "state": _state(
                        covered=[
                            (
                                "public.slot.controller."
                                f"{len(public_cases) + len(CONTROLLER_STRATA):03d}"
                            )
                        ],
                        cause="not_missing",
                        intent="finalize_answer",
                        sufficient=1.0,
                    ),
                },
            )
            for spec in specs:
                case_number = len(public_cases) + 1
                case_id = f"g2-controller-{case_number:03d}"
                handle = f"public.slot.controller.{case_number:03d}"
                if spec["stratum"] == "finalize_ready":
                    spec["state"]["covered_claim_handles"] = [handle]
                menu = [dict(action) for action in spec["menu"]]
                rng.shuffle(menu)
                expected_index = next(
                    index
                    for index, action in enumerate(menu)
                    if action["tool"] == spec["expected_tool"]
                )
                public_input = {
                    "task": "choose_next_action_v2",
                    "controller_policy": (
                        "react_v2" if case_number % 2 else "sufficiency_v2"
                    ),
                    "question": spec["question"],
                    "public_claim_slots": [
                        {
                            "claim_handle": handle,
                            "description": spec["description"],
                        }
                    ],
                    "known_pointers": spec.get("pointers", []),
                    "observed_evidence": spec.get("observations", []),
                    "recent_public_history": spec.get("history", []),
                    "action_menu": menu,
                    "remaining_budget": {
                        "actions_remaining": 6,
                        "cost_remaining": 8.0,
                    },
                }
                assert_public_surface(public_input)
                public_cases.append(
                    {
                        "case_id": case_id,
                        "case_type": "controller",
                        "stratum": spec["stratum"],
                        "public_input": public_input,
                    }
                )
                labels[case_id] = {
                    "expected_action_index": expected_index,
                    "expected_evidence_state": spec["state"],
                    "restoration_reacquisition": (
                        spec["stratum"] == "restoration_reacquire"
                    ),
                    "no_trigger_control": spec["stratum"] == "no_trigger",
                    "terminal": spec["stratum"]
                    in {"no_trigger", "finalize_ready"},
                }
        return public_cases, labels

    def _finalizer_cases(
        self,
        rng: random.Random,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        facts = list(zip(COLORS, SHAPES, CODES, SOUNDS, strict=True))
        rng.shuffle(facts)
        public_cases: list[dict[str, Any]] = []
        labels: dict[str, Any] = {}
        modalities = ("vision", "speech", "ambient")
        for index in range(12):
            color, shape, code, sound = facts[index % len(facts)]
            modality = modalities[index % 3]
            term = {
                "vision": f"{color} {shape}",
                "speech": code,
                "ambient": sound,
            }[modality]
            condition = (
                "oracle_complete" if index < 8 else "restoration_complete"
            )
            case_id = f"g2-finalizer-{index + 1:03d}"
            handle = f"public.slot.final.{index + 1:03d}"
            observation_id = f"public.obs.g2.final.{index + 1:03d}"
            noun = (
                "mosaic"
                if modality == "vision"
                else "call-sign"
                if modality == "speech"
                else "tone-pattern"
            )
            public_input = {
                "task": "grounded_finalization_v2",
                "condition": condition,
                "question": (
                    f"Which invented {noun} is recorded for sealed card "
                    f"{index + 1}?"
                ),
                "public_claim_slots": [
                    {
                        "claim_handle": handle,
                        "description": (
                            f"The recorded invented {noun} for this card."
                        ),
                    }
                ],
                "observed_evidence": [
                    {
                        "observation_id": observation_id,
                        "interval": {
                            "start_s": float(2 * index),
                            "end_s": float(2 * index + 1),
                        },
                        "modalities": [modality],
                        "payload": {
                            "text": (
                                f"The recorded invented {noun} for sealed "
                                f"card {index + 1} is {term}."
                            )
                        },
                    }
                ],
            }
            assert_public_surface(public_input)
            public_cases.append(
                {
                    "case_id": case_id,
                    "case_type": "finalizer",
                    "stratum": condition,
                    "public_input": public_input,
                }
            )
            labels[case_id] = {
                "answer_mode": "answer",
                "required_terms_by_claim": {handle: term.split()},
                "accepted_support": {handle: [observation_id]},
                "support_modality": modality,
                "oracle_complete": condition == "oracle_complete",
                "restoration_reacquisition": (
                    condition == "restoration_complete"
                ),
            }
        partials = (
            ("speech", "speech_content", "voiced call-sign"),
            ("vision", "event_detection", "visible marker event"),
            ("ambient", "ambient_event", "non-speech tone-pattern"),
            ("vision", "temporal_order", "visible marker order"),
        )
        for modality, hop, phrase in partials:
            case_id = f"g2-finalizer-{len(public_cases) + 1:03d}"
            handle = f"public.slot.final.{len(public_cases) + 1:03d}"
            public_input = {
                "task": "grounded_finalization_v2",
                "condition": "partial_evidence",
                "question": (
                    f"Which missing invented {phrase} completes sealed card "
                    f"{len(public_cases) + 1}?"
                ),
                "public_claim_slots": [
                    {
                        "claim_handle": handle,
                        "description": f"The missing invented {phrase}.",
                    }
                ],
                "observed_evidence": [],
            }
            assert_public_surface(public_input)
            public_cases.append(
                {
                    "case_id": case_id,
                    "case_type": "finalizer",
                    "stratum": "blocked_partial",
                    "public_input": public_input,
                }
            )
            labels[case_id] = {
                "answer_mode": "abstain",
                "required_missing_modality": modality,
                "required_missing_hop": hop,
                "required_terms_by_claim": {},
                "accepted_support": {},
                "oracle_complete": False,
                "restoration_reacquisition": False,
            }
        return public_cases, labels

    def _runtime_cases(
        self,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        public_cases: list[dict[str, Any]] = []
        labels: dict[str, Any] = {}
        for index, (fixture, status, called) in enumerate(
            RUNTIME_FIXTURES, 1
        ):
            case_id = f"g2-runtime-{index:03d}"
            public_input = {
                "task": "granite_v2_failure_injection",
                "question": (
                    f"Which invented sentinel belongs to runtime fixture "
                    f"{index}?"
                ),
                "public_claim_slots": [
                    {
                        "claim_handle": f"public.slot.failure.{index}",
                        "description": "An invented runtime sentinel.",
                    }
                ],
                "injected_public_fixture": fixture,
            }
            assert_public_surface(public_input)
            public_cases.append(
                {
                    "case_id": case_id,
                    "case_type": "runtime_failure",
                    "stratum": fixture,
                    "public_input": public_input,
                }
            )
            labels[case_id] = {
                "expected_inference_status": status,
                "expected_model_called": called,
                "expected_final_answer": None,
                "fail_closed": True,
            }
        return public_cases, labels

    def generate_bundle(self) -> FutureSuiteBundle:
        """Instantiate one fresh public/private suite bundle."""

        rng = random.Random(self.seed)
        controller, controller_labels = self._controller_cases(rng)
        finalizer, finalizer_labels = self._finalizer_cases(rng)
        runtime, runtime_labels = self._runtime_cases()
        cases = [*controller, *finalizer, *runtime]
        thresholds = dict(CONTROLLER_FINALIZER_THRESHOLDS)
        public_suite = {
            "schema_version": PUBLIC_SUITE_SCHEMA_VERSION,
            "suite_id": self.suite_id,
            "freeze_label": self.freeze_label,
            "generated_date": self.generated_date,
            "adapter_schema_version": ADAPTER_SCHEMA_VERSION,
            "binding": {
                "controller": PRIMARY_BINDINGS["controller"].to_dict(),
                "finalizer": PRIMARY_BINDINGS["finalizer"].to_dict(),
                "same_exact_snapshot_required": True,
            },
            "prompt_policy": {
                "schema_version": PROMPT_POLICY["schema_version"],
                "sha256": PROMPT_POLICY_SHA256,
                "public_projection_only": True,
                "private_labels_exposed": False,
                "maximum_schema_only_retries_per_factor": 1,
                "semantic_retries": 0,
                "cross_factor_retries": 0,
            },
            "budget": CommonBudget().to_dict(),
            "thresholds": thresholds,
            "content_boundary": {
                "fictional_generated_primitives_only": True,
                "scientific_family_content": False,
                "real_source_content": False,
                "model_results_present": False,
                "private_labels_present": False,
            },
            "cases": cases,
            "execution_status": "SEALED_NOT_RUN",
        }
        private_labels = {
            "schema_version": PRIVATE_LABEL_SCHEMA_VERSION,
            "suite_id": self.suite_id,
            "seed": self.seed,
            "seed_sha256": "sha256:"
            + hashlib.sha256(str(self.seed).encode("ascii")).hexdigest(),
            "labels": {
                **controller_labels,
                **finalizer_labels,
                **runtime_labels,
            },
        }
        aggregate_composition = {
            "case_types": dict(
                sorted(Counter(case["case_type"] for case in cases).items())
            ),
            "strata": {
                case_type: dict(
                    sorted(
                        Counter(
                            case["stratum"]
                            for case in cases
                            if case["case_type"] == case_type
                        ).items()
                    )
                )
                for case_type in (
                    "controller",
                    "finalizer",
                    "runtime_failure",
                )
            },
            "controller_policies": dict(
                sorted(
                    Counter(
                        case["public_input"]["controller_policy"]
                        for case in controller
                    ).items()
                )
            ),
            "private_label_aggregates": _aggregate_private_labels(
                private_labels["labels"],
                cases,
            ),
        }
        manifest = {
            "schema_version": GENERATOR_SCHEMA_VERSION,
            "suite_id": self.suite_id,
            "freeze_label": self.freeze_label,
            "generated_date": self.generated_date,
            "algorithm": "python-stdlib-random-v2-fixed-order",
            "seed_generation": {
                "method": "secrets.randbits(256)_with_high_bit_set",
                "minimum_entropy_bits": 256,
                "seed_recorded_in_private_labels": True,
                "seed_exposed_in_public_suite": False,
            },
            "public_suite_sha256": sha256_json(public_suite),
            "private_labels_sha256": sha256_json(private_labels),
            "prompt_policy_sha256": PROMPT_POLICY_SHA256,
            "gate_c_thresholds_sha256": sha256_json(thresholds),
            "aggregate_composition": aggregate_composition,
            "model_used": False,
            "scientific_source_used": False,
            "real_source_content_used": False,
            "consumed_task172_labels_used": False,
            "private_target_manual_inspection": False,
        }
        return FutureSuiteBundle(
            public_suite=public_suite,
            private_labels=private_labels,
            generation_manifest=manifest,
        )

    def seal_to(self, output_dir: str | Path) -> dict[str, Any]:
        """Create a fresh immutable suite directory and seal it before use."""

        destination = Path(output_dir)
        if destination.exists():
            raise StrongBaselineError("FUTURE_SUITE_OUTPUT_ALREADY_EXISTS")
        bundle = self.generate_bundle()
        staging = destination.with_name(
            f".{destination.name}.staging-{os.getpid()}"
        )
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True, mode=0o700)
        files = {
            "public_suite.json": bundle.public_suite,
            "private_labels.json": bundle.private_labels,
            "generation_manifest.json": bundle.generation_manifest,
            "prompt_policy.json": PROMPT_POLICY,
        }
        for name, value in files.items():
            path = staging / name
            path.write_text(
                json.dumps(value, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            os.chmod(path, 0o400)
        seal = {
            "schema_version": SEAL_SCHEMA_VERSION,
            "suite_id": self.suite_id,
            "freeze_label": self.freeze_label,
            "generated_date": self.generated_date,
            "state": "SEALED_BEFORE_MODEL_EXECUTION",
            "files": {
                name: {
                    "bytes": (staging / name).stat().st_size,
                    "sha256": "sha256:"
                    + hashlib.sha256((staging / name).read_bytes()).hexdigest(),
                }
                for name in files
            },
            "semantic_hashes": {
                "public_suite": "sha256:"
                + hashlib.sha256(
                    canonical_json_bytes(bundle.public_suite)
                ).hexdigest(),
                "private_labels": "sha256:"
                + hashlib.sha256(
                    canonical_json_bytes(bundle.private_labels)
                ).hexdigest(),
                "prompt_policy": PROMPT_POLICY_SHA256,
            },
        }
        seal_path = staging / "seal.json"
        seal_path.write_text(
            json.dumps(seal, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.chmod(seal_path, 0o400)
        os.rename(staging, destination)
        os.chmod(destination, 0o500)
        return seal
