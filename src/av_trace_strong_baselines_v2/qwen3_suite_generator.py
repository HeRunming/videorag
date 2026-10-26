"""Prospective Qwen3-bound adapter-v2 fictional competence-suite generator.

This module reuses the frozen factorized adapter-v2 contracts, but it does
not load a model or import a model runtime.  It creates one source-free
public/private suite split and seals it before any possible execution.
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
    FALLBACK_BINDINGS,
    CommonBudget,
    canonical_json_bytes,
    sha256_json,
)
from av_trace_strong_baselines.errors import StrongBaselineError
from av_trace_strong_baselines.security import assert_public_surface

from .contracts import ADAPTER_SCHEMA_VERSION

GENERATOR_SCHEMA_VERSION = "av-trace.qwen3-adapter-v2-suite-generator/1.0"
PUBLIC_SUITE_SCHEMA_VERSION = "av-trace.qwen3-adapter-v2-public-suite/1.0"
PRIVATE_LABEL_SCHEMA_VERSION = (
    "av-trace.qwen3-adapter-v2-private-labels/1.0"
)
SEAL_SCHEMA_VERSION = "av-trace.qwen3-adapter-v2-suite-seal/1.0"
EXPECTED_GENERATED_DATE = "2026-10-08"
CONSUMED_DEVELOPMENT_SEEDS = frozenset(
    {
        15820260924,
        78196802424380082776318973058337920883482433466228251028861878547570995846291,
    }
)

MATERIALS = (
    "basalt",
    "nickel",
    "linen",
    "quartz",
    "cobalt",
    "willow",
    "slate",
    "bronze",
)
MOTIFS = (
    "forked ray",
    "nested arch",
    "split vane",
    "braided loop",
    "offset crown",
    "twin pennant",
    "stepped fan",
    "hollow knot",
)
WATCHWORDS = (
    "north ember",
    "silent rook",
    "winter quay",
    "velvet orbit",
    "hidden anvil",
    "silver wicket",
    "quiet beacon",
    "raven ford",
)
ACOUSTICS = (
    "a double reed click",
    "one muted bell",
    "a dry gear trill",
    "three cork knocks",
    "a brief wire hum",
    "two hollow clacks",
    "a soft latch buzz",
    "one descending thrum",
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
    "Treat each record as a closed-world synthetic control decision. Read "
    "only the displayed public record. Select one listed operation through "
    "its corresponding zero-argument native tool call; never recreate the "
    "operation payload. Separately report all six diagnostic state heads "
    "using the record-local claim handles and allowed enums. An unseen known "
    "interval is inspected, a previously unavailable required channel is "
    "checked, and a matching route is reacquired only after the explicit "
    "recovery checkpoint. If no route exists, terminate with abstention; if "
    "the observations cover the request, terminate with an answer. Otherwise "
    "route by the unresolved visual, spoken, or nonverbal requirement. Do "
    "not infer hidden facts. Consistency projection rejects authored content "
    "but never edits it."
)

FINALIZER_PROMPT_POLICY = (
    "Resolve the closed-world synthetic record from its visible question, "
    "claim handles, and observations alone. Produce disposition, answer "
    "wording, claim drafts, citation choices, and missingness diagnosis as "
    "independent schema-bound factors. A supported answer must state only "
    "payload facts and cite only listed observation identifiers. An "
    "incomplete record must abstain with blank answer, claims, and citations "
    "while identifying the requested missing channel and reasoning hop. Do "
    "not create facts or evidence. Assembly may copy exact public interval "
    "and modality metadata for selected citations, but cannot choose, fill, "
    "translate, reconcile, or semantically repair model-authored content."
)

PROMPT_POLICY = {
    "schema_version": "av-trace.qwen3-adapter-v2-prompt-policy/1.0",
    "controller": CONTROLLER_PROMPT_POLICY,
    "finalizer": FINALIZER_PROMPT_POLICY,
    "public_projection_only": True,
    "factor_schema_embedded_by_adapter": True,
    "private_labels_exposed": False,
    "native_tool_transport": "qwen_chat_template_tool_call",
    "enable_thinking": False,
    "decoding": "greedy",
    "semantic_retries": 0,
    "cross_factor_retries": 0,
    "maximum_schema_only_retries_per_factor": 1,
}
PROMPT_POLICY_SHA256 = sha256_json(PROMPT_POLICY)


@dataclass(frozen=True)
class Qwen3FutureSuiteBundle:
    """In-memory public/private split prior to writing the immutable seal."""

    public_suite: dict[str, Any]
    private_labels: dict[str, Any]
    generation_manifest: dict[str, Any]


def validate_future_seed(seed: int) -> int:
    """Require a fresh high-entropy seed and reject known consumed seeds."""

    if (
        isinstance(seed, bool)
        or not isinstance(seed, int)
        or seed.bit_length() < 256
        or seed in CONSUMED_DEVELOPMENT_SEEDS
    ):
        raise StrongBaselineError("QWEN3_FUTURE_SUITE_SEED_NOT_NEW")
    return seed


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


def _token(rng: random.Random, namespace: str, cycle: int) -> str:
    return f"{namespace}.{cycle}.{rng.getrandbits(40):010x}"


def _aggregate_private_labels(
    labels: dict[str, Any],
    public_cases: list[dict[str, Any]],
) -> dict[str, Any]:
    """Emit composition counts without copying any case-level target."""

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
    terminal: Counter[str] = Counter()
    restoration: Counter[str] = Counter()
    no_trigger: Counter[str] = Counter()
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
            terminal[str(label["terminal"]).lower()] += 1
            restoration[str(label["restoration_reacquisition"]).lower()] += 1
            no_trigger[str(label["no_trigger_control"]).lower()] += 1
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
            restoration[str(label["restoration_reacquisition"]).lower()] += 1
        else:
            runtime_statuses[label["expected_inference_status"]] += 1
            runtime_called[str(label["expected_model_called"]).lower()] += 1
    return {
        "controller_expected_tools": dict(sorted(controller_tools.items())),
        "controller_state_heads": {
            key: dict(sorted(value.items()))
            for key, value in state_heads.items()
        },
        "controller_terminal": dict(sorted(terminal.items())),
        "restoration_reacquisition": dict(sorted(restoration.items())),
        "no_trigger_control": dict(sorted(no_trigger.items())),
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


class Qwen3FutureSealedSuiteGenerator:
    """Create a fresh Qwen3-bound public/private fixture pair and seal."""

    def __init__(
        self,
        *,
        seed: int,
        seed_recorded_at: str,
        suite_id: str,
        freeze_label: str,
        generated_date: str = EXPECTED_GENERATED_DATE,
    ) -> None:
        self.seed = validate_future_seed(seed)
        if not seed_recorded_at.endswith("+08:00"):
            raise StrongBaselineError("QWEN3_SEED_RECORD_TIMEZONE_INVALID")
        if not suite_id.startswith("qwen3-v2-fictional-"):
            raise StrongBaselineError("QWEN3_FUTURE_SUITE_ID_INVALID")
        if not freeze_label.startswith("QWEN3_ADAPTER_V2_"):
            raise StrongBaselineError("QWEN3_FUTURE_SUITE_FREEZE_LABEL_INVALID")
        if generated_date != EXPECTED_GENERATED_DATE:
            raise StrongBaselineError("QWEN3_FUTURE_SUITE_DATE_INVALID")
        self.seed_recorded_at = seed_recorded_at
        self.suite_id = suite_id
        self.freeze_label = freeze_label
        self.generated_date = generated_date

    def _controller_cases(
        self,
        rng: random.Random,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        public_cases: list[dict[str, Any]] = []
        labels: dict[str, Any] = {}
        for cycle in range(1, 4):
            visual_token = _token(rng, "depot", cycle)
            speech_token = _token(rng, "berth", cycle)
            ambient_token = _token(rng, "bay", cycle)
            pointer_token = _token(rng, "panel", cycle)
            blocked_token = _token(rng, "booth", cycle)
            restored_token = _token(rng, "switch", cycle)
            guard_token = _token(rng, "ledger", cycle)
            ready_value = f"{rng.choice(MATERIALS)} {rng.choice(MOTIFS)}"
            specs: tuple[dict[str, Any], ...] = (
                {
                    "stratum": "route_vision",
                    "question": (
                        "Consult the make-believe depot register: which etched "
                        f"insignia identifies locator {visual_token}?"
                    ),
                    "description": "Etched locator insignia in a dummy depot.",
                    "menu": [
                        _search(
                            "search_speech",
                            f"dispatch words associated with {visual_token}",
                        ),
                        _search(
                            "search_visual",
                            f"etched locator insignia for {visual_token}",
                        ),
                        _search(
                            "search_ambient_audio",
                            f"mechanical noise beside {visual_token}",
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
                        "Within the fabricated dispatch roll, which spoken "
                        f"watchword identifies berth {speech_token}?"
                    ),
                    "description": "Spoken watchword for a dummy berth.",
                    "menu": [
                        _search(
                            "search_visual",
                            f"painted sign attached to {speech_token}",
                        ),
                        _search(
                            "search_speech",
                            f"spoken watchword naming {speech_token}",
                        ),
                        _search(
                            "search_ambient_audio",
                            f"nonverbal machinery at {speech_token}",
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
                        f"For imaginary bay {ambient_token}, what nonverbal "
                        "acoustic signature follows its latch event?"
                    ),
                    "description": "Nonverbal signature after a dummy latch.",
                    "menu": [
                        _search(
                            "search_visual",
                            f"latch movement at {ambient_token}",
                        ),
                        _search(
                            "search_speech",
                            f"narration mentioning {ambient_token}",
                        ),
                        _search(
                            "search_ambient_audio",
                            f"acoustic signature after latch {ambient_token}",
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
                        "At the supplied unviewed interval for dummy panel "
                        f"{pointer_token}, which indicator motif is visible?"
                    ),
                    "description": "Indicator motif at a supplied interval.",
                    "menu": [
                        _inspect(47.0 + cycle * 4.0),
                        _search(
                            "search_visual",
                            f"distant panel references for {pointer_token}",
                        ),
                        _finalize(),
                    ],
                    "expected_tool": "inspect_clip",
                    "pointers": [
                        {
                            "pointer_id": f"public.pointer.q3.{cycle}",
                            "interval": {
                                "start_s": 47.0 + cycle * 4.0,
                                "end_s": 48.0 + cycle * 4.0,
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
                        "Which spoken watchword belongs to mock booth "
                        f"{blocked_token} when its transcript route has just "
                        "reported unavailable?"
                    ),
                    "description": "Watchword behind an unavailable route.",
                    "menu": [
                        _search(
                            "search_speech",
                            f"alternate transcript path for {blocked_token}",
                        ),
                        _status("speech"),
                        _finalize(),
                    ],
                    "expected_tool": "get_channel_status",
                    "history": [
                        {
                            "action": _search(
                                "search_speech",
                                f"watchword assigned to {blocked_token}",
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
                        "After the declared recovery checkpoint, what coded "
                        f"phrase can be retrieved for switch {restored_token}?"
                    ),
                    "description": "Coded phrase on a recovered speech route.",
                    "menu": [
                        _search(
                            "search_speech",
                            f"reacquire recovered switch phrase {restored_token}",
                        ),
                        _status("speech"),
                        _finalize(),
                    ],
                    "expected_tool": "search_speech",
                    "history": [
                        {
                            "event_type": "protocol_checkpoint",
                            "event_version": "2.0.0",
                            "message": (
                                "The scheduled recovery checkpoint is complete."
                            ),
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
                        "In the fabricated ledger sequence, which mark came "
                        f"before guard entry {guard_token}?"
                    ),
                    "description": "Earlier mark in an unavailable sequence.",
                    "menu": [_finalize()],
                    "expected_tool": "finalize",
                    "history": [
                        {
                            "event_type": "protocol_checkpoint",
                            "event_version": "2.0.0",
                            "message": (
                                "The scheduled recovery checkpoint is complete."
                            ),
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
                        "What registry emblem is already certified for "
                        f"completed dummy docket {cycle}?"
                    ),
                    "description": "Certified emblem in a completed docket.",
                    "menu": [
                        _search(
                            "search_visual",
                            f"redundant docket view for cycle {cycle}",
                        ),
                        _finalize(),
                    ],
                    "expected_tool": "finalize",
                    "observations": [
                        {
                            "observation_id": f"public.obs.q3.ready.{cycle}",
                            "interval": {
                                "start_s": float(5 * cycle),
                                "end_s": float(5 * cycle + 1),
                            },
                            "modalities": ["vision"],
                            "payload": {
                                "text": (
                                    f"The completed dummy docket certifies "
                                    f"the registry emblem {ready_value}."
                                )
                            },
                        }
                    ],
                    "state": _state(
                        cause="not_missing",
                        intent="finalize_answer",
                        sufficient=1.0,
                    ),
                },
            )
            for spec in specs:
                case_number = len(public_cases) + 1
                case_id = f"q3v2-controller-{case_number:03d}"
                handle = f"public.slot.q3.controller.{case_number:03d}"
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
                    "task": "select_closed_world_operation_v2",
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
        facts = list(
            zip(MATERIALS, MOTIFS, WATCHWORDS, ACOUSTICS, strict=True)
        )
        rng.shuffle(facts)
        public_cases: list[dict[str, Any]] = []
        labels: dict[str, Any] = {}
        modalities = ("vision", "speech", "ambient")
        for index in range(12):
            material, motif, watchword, acoustic = facts[index % len(facts)]
            modality = modalities[index % 3]
            term = {
                "vision": f"{material} {motif}",
                "speech": watchword,
                "ambient": acoustic,
            }[modality]
            condition = (
                "oracle_complete" if index < 8 else "restoration_complete"
            )
            case_id = f"q3v2-finalizer-{index + 1:03d}"
            handle = f"public.slot.q3.final.{index + 1:03d}"
            observation_id = f"public.obs.q3.final.{index + 1:03d}"
            field_name = {
                "vision": "inspection emblem",
                "speech": "dispatch watchword",
                "ambient": "mechanical signature",
            }[modality]
            public_input = {
                "task": "resolve_closed_world_record_v2",
                "condition": condition,
                "question": (
                    f"Report the archived {field_name} for imaginary register "
                    f"{index + 1}."
                ),
                "public_claim_slots": [
                    {
                        "claim_handle": handle,
                        "description": (
                            f"Archived {field_name} in this dummy register."
                        ),
                    }
                ],
                "observed_evidence": [
                    {
                        "observation_id": observation_id,
                        "interval": {
                            "start_s": float(3 * index),
                            "end_s": float(3 * index + 1),
                        },
                        "modalities": [modality],
                        "payload": {
                            "text": (
                                f"Imaginary register {index + 1} certifies "
                                f"its archived {field_name} as {term}."
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
            ("speech", "speech_content", "unheard dispatch watchword"),
            ("vision", "event_detection", "unseen inspection emblem"),
            ("ambient", "ambient_event", "unheard mechanical signature"),
            ("vision", "temporal_order", "unseen ordering mark"),
        )
        for modality, hop, phrase in partials:
            item = len(public_cases) + 1
            case_id = f"q3v2-finalizer-{item:03d}"
            handle = f"public.slot.q3.final.{item:03d}"
            public_input = {
                "task": "resolve_closed_world_record_v2",
                "condition": "partial_evidence",
                "question": (
                    f"Supply the {phrase} needed to close imaginary register "
                    f"{item}."
                ),
                "public_claim_slots": [
                    {
                        "claim_handle": handle,
                        "description": f"Unavailable {phrase}.",
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
            case_id = f"q3v2-runtime-{index:03d}"
            public_input = {
                "task": "qwen3_v2_fail_closed_harness",
                "question": (
                    "Close the dummy dispatch safely for injected harness "
                    f"condition R{index:02d}."
                ),
                "public_claim_slots": [
                    {
                        "claim_handle": f"public.slot.q3.failure.{index}",
                        "description": "A fictional dispatch completion value.",
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

    def generate_bundle(self) -> Qwen3FutureSuiteBundle:
        """Instantiate one fresh Qwen3-bound public/private suite bundle."""

        rng = random.Random(self.seed)
        controller, controller_labels = self._controller_cases(rng)
        finalizer, finalizer_labels = self._finalizer_cases(rng)
        runtime, runtime_labels = self._runtime_cases()
        cases = [*controller, *finalizer, *runtime]
        thresholds = dict(CONTROLLER_FINALIZER_THRESHOLDS)
        binding = {
            "controller": FALLBACK_BINDINGS["controller"].to_dict(),
            "finalizer": FALLBACK_BINDINGS["finalizer"].to_dict(),
            "same_exact_snapshot_required": True,
        }
        public_suite = {
            "schema_version": PUBLIC_SUITE_SCHEMA_VERSION,
            "suite_id": self.suite_id,
            "freeze_label": self.freeze_label,
            "generated_date": self.generated_date,
            "adapter_schema_version": ADAPTER_SCHEMA_VERSION,
            "adapter_profile": "qwen3-native-transport-factorized-v2",
            "binding": binding,
            "prompt_policy": {
                "schema_version": PROMPT_POLICY["schema_version"],
                "sha256": PROMPT_POLICY_SHA256,
                "public_projection_only": True,
                "private_labels_exposed": False,
                "native_tool_transport": (
                    PROMPT_POLICY["native_tool_transport"]
                ),
                "enable_thinking": False,
                "decoding": "greedy",
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
            "coverage_families": {
                "routing_controller_cases": 15,
                "state_controller_cases": 24,
                "terminal_controller_cases": 6,
                "restoration_cases": 7,
                "no_trigger_cases": 3,
                "oracle_finalizer_cases": 8,
                "partial_finalizer_cases": 4,
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
            "algorithm": "python-stdlib-random-qwen3-v2-fixed-order",
            "seed_generation": {
                "method": "secrets.randbits(256)_with_high_bit_set",
                "minimum_entropy_bits": 256,
                "generated_at": self.seed_recorded_at,
                "recorded_before_suite_generation": True,
                "seed_recorded_in_private_labels": True,
                "seed_exposed_in_public_suite": False,
            },
            "public_suite_sha256": sha256_json(public_suite),
            "private_labels_sha256": sha256_json(private_labels),
            "prompt_policy_sha256": PROMPT_POLICY_SHA256,
            "gate_c_thresholds_sha256": sha256_json(thresholds),
            "model_binding_sha256": sha256_json(binding),
            "aggregate_composition": aggregate_composition,
            "model_used": False,
            "scientific_source_used": False,
            "real_source_content_used": False,
            "consumed_private_labels_used": False,
            "consumed_public_prompts_used_for_generation": False,
            "private_target_manual_inspection": False,
        }
        return Qwen3FutureSuiteBundle(
            public_suite=public_suite,
            private_labels=private_labels,
            generation_manifest=manifest,
        )

    def seal_to(self, output_dir: str | Path) -> dict[str, Any]:
        """Write one immutable suite directory and seal it before model use."""

        destination = Path(output_dir)
        if destination.exists():
            raise StrongBaselineError("QWEN3_FUTURE_SUITE_OUTPUT_ALREADY_EXISTS")
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
                "model_binding": sha256_json(
                    bundle.public_suite["binding"]
                ),
                "gate_c_thresholds": sha256_json(
                    bundle.public_suite["thresholds"]
                ),
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
