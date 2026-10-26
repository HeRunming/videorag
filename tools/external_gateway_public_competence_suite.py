"""Freeze and evaluate a public-fictional external-gateway competence suite.

This module intentionally contains no gateway client, subprocess invocation,
model binding, or execution command.  It creates a deterministic prospective
suite and provides a fail-closed, post-run evaluator for factorized v2
controller/finalizer outputs.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from av_trace_strong_baselines.contracts import canonical_json_bytes
from av_trace_strong_baselines.errors import SchemaViolation
from av_trace_strong_baselines.schemas import EVIDENCE_STATE_FIELDS
from av_trace_strong_baselines.security import assert_public_surface
from av_trace_strong_baselines_v2 import (
    ADAPTER_SCHEMA_VERSION,
    AttemptKind,
    FactorStatus,
    ProjectionStatus,
    RawFactorAttempt,
    parse_controller_factors,
    parse_finalizer_factors,
)

ARTIFACT_PATH = Path(
    "data/rehearsal_plan/external_gateway_public_competence_suite_v1.json"
)
GRANITE_PUBLIC_PATH = Path(
    "data/rehearsal_plan/granite_adapter_v2_holdout_public.json"
)
QWEN_PUBLIC_PATH = Path(
    "data/rehearsal_plan/qwen3_adapter_v2_holdout_public.json"
)

SCHEMA_VERSION = "av-trace.external-gateway-public-competence-freeze/1.0"
PUBLIC_SUITE_SCHEMA = (
    "av-trace.external-gateway-public-competence-public-suite/1.0"
)
PACKET_SCHEMA = "av-trace.external-gateway-public-competence-packet/1.0"
PRIVATE_SCHEMA = (
    "av-trace.external-gateway-public-competence-private-evaluator/1.0"
)
MANIFEST_SCHEMA = (
    "av-trace.external-gateway-public-competence-manifest/1.0"
)
SUBMISSION_SCHEMA = (
    "av-trace.external-gateway-public-competence-submission/1.0"
)
REPORT_SCHEMA = "av-trace.external-gateway-public-competence-report/1.0"

SUITE_ID = "external-gateway-public-fictional-competence-20261012"
FREEZE_LABEL = "EXTERNAL_GATEWAY_PUBLIC_COMPETENCE_SUITE_2026-10-12"
FREEZE_DATE = "2026-10-12"
FROZEN_NOT_RUN = "EXTERNAL_GATEWAY_PUBLIC_COMPETENCE_SUITE_FROZEN_NOT_RUN"

CONTROLLER_STRATA = (
    "route_vision",
    "route_speech",
    "route_ambient",
    "blocked_status",
    "restoration_recovery",
    "finalize_ready",
    "premature_stop_guard",
    "no_route_abstain",
)
FINALIZER_STRATA = (
    "supported_single",
    "supported_dual",
    "restored_support",
    "blocked_abstention",
)
EXPECTED_COUNTS = {"controller": 24, "finalizer": 16}
FACTOR_NAMES = {
    "controller": ("action_choice", "evidence_state"),
    "finalizer": (
        "disposition",
        "answer_text",
        "claim_drafts",
        "citation_selections",
        "diagnosis",
    ),
}

THRESHOLDS = {
    "minimum_cases": 40,
    "complete_case_set_required": True,
    "valid_structured_model_calls_min": 0.95,
    "correct_first_actions_overall_min": 0.875,
    "correct_first_actions_each_stratum_min": 2 / 3,
    "exact_six_field_state_min": 0.80,
    "each_state_component_min": 0.875,
    "blocked_correct_abstention_min": 0.75,
    "restoration_recovery_min": 6 / 7,
    "supported_finalization_min": 10 / 12,
    "exact_citation_selection_min": 11 / 12,
    "premature_stop_prevention_min": 1.0,
    "unsupported_required_claims_max": 0,
    "unobserved_citation_selections_max": 0,
    "private_label_exposures_max": 0,
    "deterministic_answer_substitutions_max": 0,
}

PROMPT_POLICY = {
    "schema_version": (
        "av-trace.external-gateway-public-competence-prompt-policy/1.0"
    ),
    "adapter_semantics": "factorized_controller_and_finalizer_v2",
    "public_projection_only": True,
    "private_labels_exposed": False,
    "maximum_schema_only_retries_per_factor": 1,
    "semantic_retries": 0,
    "cross_factor_retries": 0,
    "best_of_n": 1,
    "answer_substitution": False,
    "controller_instruction": (
        "Use only this public fictional source-free packet and its exact "
        "action menu. Select one menu action and independently author all six "
        "evidence-state fields. Do not infer an answer from an unobserved "
        "route. Continue recovery when a useful route exists; finalize an "
        "answer only from sufficient observed text; otherwise finalize an "
        "abstention only when no useful route remains."
    ),
    "finalizer_instruction": (
        "Use only the public fictional source-free question, claim slots, and "
        "observed textual evidence. Author disposition, answer text, claims, "
        "citation selections, and diagnosis independently. Every answered "
        "claim must be directly supported by selected observed IDs. If the "
        "required evidence is absent, abstain with empty answer, claims, and "
        "citations and diagnose the missing modality and reasoning hop."
    ),
}

PROHIBITED_PROMPT_KEYS = frozenset(
    {
        "accepted_support",
        "answer_terms",
        "evaluator_private",
        "expected_action_index",
        "expected_answer",
        "expected_citations",
        "expected_evidence_state",
        "labels",
        "private_canary",
        "private_labels",
        "required_missing_hop",
        "required_missing_modality",
        "required_terms_by_claim",
        "restoration_case",
        "scoring_target",
    }
)
PROHIBITED_PROMPT_PATTERNS = (
    re.compile(r"\bH1\b", re.IGNORECASE),
    re.compile(r"\bH2\b", re.IGNORECASE),
    re.compile(r"\bSES(?:es)?\b", re.IGNORECASE),
    re.compile(
        r"\b(?:NOAA|EPIC[- ]?KITCHENS|VideoMME|CaptainCook4D)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:scientific|restricted)[_ -](?:trigger|source)\b",
        re.IGNORECASE,
    ),
)
PROHIBITED_URI_PREFIXES = ("data:", "file:", "http:", "https:")
PROHIBITED_MEDIA_SUFFIXES = (
    ".aac",
    ".avi",
    ".flac",
    ".jpeg",
    ".jpg",
    ".m4a",
    ".mkv",
    ".mov",
    ".mp3",
    ".mp4",
    ".ogg",
    ".png",
    ".wav",
    ".webm",
    ".webp",
)
REFERENCE_SMOKE_IDS = frozenset(
    {
        'PUBLIC_REDACTED_IDENTIFIER',
        'PUBLIC_REDACTED_IDENTIFIER',
    }
)


class CompetenceSuiteError(RuntimeError):
    """Typed fail-closed suite, submission, or evaluator error."""


def sha256_json(value: Any) -> str:
    """Return a stable SHA-256 over canonical JSON."""

    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CompetenceSuiteError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def _search_action(
    modality: str,
    query: str,
    *,
    excluded: Sequence[str] = (),
) -> dict[str, Any]:
    tool = {
        "vision": "search_visual",
        "speech": "search_speech",
        "ambient": "search_ambient_audio",
    }[modality]
    arguments: dict[str, Any] = {
        "query": query,
        "top_k": 5,
        "time_range": {"start_s": 0.0, "end_s": 64.0},
        "exclude_result_ids": list(excluded),
    }
    if modality == "speech":
        arguments["speaker_hint"] = None
    return {"tool": tool, "arguments": arguments}


def _finalize_action() -> dict[str, Any]:
    return {"tool": "finalize", "arguments": {}}


def _status_action(modality: str) -> dict[str, Any]:
    channel = "visual" if modality == "vision" else modality
    return {
        "tool": "get_channel_status",
        "arguments": {"channels": [channel]},
    }


def _claim(handle: str, description: str) -> dict[str, str]:
    return {"claim_handle": handle, "description": description}


def _observation(
    observation_id: str,
    modality: str,
    text: str,
    offset: int,
) -> dict[str, Any]:
    return {
        "observation_id": observation_id,
        "interval": {
            "start_s": float(offset),
            "end_s": float(offset + 1),
        },
        "modalities": [modality],
        "payload": {"text": text},
    }


def _state(
    *,
    covered: Sequence[str],
    missing_modality: str | None,
    missing_hop: str | None,
    cause: str,
    intent: str,
    sufficient: float,
) -> dict[str, Any]:
    return {
        "p_sufficient": sufficient,
        "covered_claim_handles": list(covered),
        "missing_modalities": (
            [] if missing_modality is None else [missing_modality]
        ),
        "missing_hops": [] if missing_hop is None else [missing_hop],
        "missingness_cause": cause,
        "recovery_intent": intent,
    }


def _packet(
    *,
    case_id: str,
    case_type: str,
    stratum: str,
    public_input: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": PACKET_SCHEMA,
        "case_id": case_id,
        "case_type": case_type,
        "stratum": stratum,
        "public_fictional": True,
        "source_free": True,
        "prospective_unseen": True,
        "packet_notice": (
            "This is a wholly fictional, synthetic, source-free closed-world "
            "competence packet. It contains no real source material or media."
        ),
        "public_input": copy.deepcopy(dict(public_input)),
    }


def _controller_cases() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    packets: list[dict[str, Any]] = []
    labels: dict[str, Any] = {}
    modality_hops = {
        "vision": "entity_identity",
        "speech": "speech_content",
        "ambient": "ambient_event",
    }
    intent_by_modality = {
        "vision": "search_vision",
        "speech": "search_speech",
        "ambient": "search_ambient",
    }
    nouns = (
        ("mirthquartz seal", "ink color"),
        ("vellichor dial", "call sign"),
        ("tessera cradle", "closing sound"),
    )

    def add(
        stratum: str,
        index: int,
        public_input: Mapping[str, Any],
        *,
        expected_action_index: int,
        expected_state: Mapping[str, Any],
        restoration_case: bool = False,
        premature_stop_case: bool = False,
    ) -> None:
        ordinal = len(packets) + 1
        case_id = f"egpc-controller-{ordinal:03d}"
        packets.append(
            _packet(
                case_id=case_id,
                case_type="controller",
                stratum=stratum,
                public_input=public_input,
            )
        )
        labels[case_id] = {
            "expected_action_index": expected_action_index,
            "expected_evidence_state": copy.deepcopy(dict(expected_state)),
            "restoration_case": restoration_case,
            "premature_stop_case": premature_stop_case,
            "variant": index + 1,
        }

    for index, (entity, attribute) in enumerate(nouns):
        modality = "vision"
        handle = f"egpc.slot.route.visual.{index + 1}"
        add(
            "route_vision",
            index,
            {
                "task": "choose_next_action",
                "policy": "evidence_sufficiency",
                "question": (
                    f"What is the fictional {attribute} of {entity} "
                    f"variant {index + 1}?"
                ),
                "public_claim_slots": [_claim(handle, "Unobserved visual fact.")],
                "observed_evidence": [],
                "known_pointers": [],
                "recent_public_history": [],
                "remaining_budget": {
                    "actions_remaining": 5,
                    "cost_remaining": 7.0,
                },
                "action_menu": [
                    _search_action(
                        modality,
                        f"fictional {entity} {attribute} variant {index + 1}",
                    ),
                    _search_action(
                        "speech",
                        f"unrelated spoken ledger variant {index + 1}",
                    ),
                    _finalize_action(),
                ],
            },
            expected_action_index=0,
            expected_state=_state(
                covered=[],
                missing_modality=modality,
                missing_hop=modality_hops[modality],
                cause="evidence_accessible_but_not_found",
                intent=intent_by_modality[modality],
                sufficient=0.0,
            ),
        )

    for index in range(3):
        modality = "speech"
        handle = f"egpc.slot.route.speech.{index + 1}"
        add(
            "route_speech",
            index,
            {
                "task": "choose_next_action",
                "policy": "evidence_sufficiency",
                "question": (
                    "Which invented passphrase does the fictional "
                    f"quillkeeper utter in variant {index + 1}?"
                ),
                "public_claim_slots": [_claim(handle, "Unheard fictional phrase.")],
                "observed_evidence": [],
                "known_pointers": [],
                "recent_public_history": [],
                "remaining_budget": {
                    "actions_remaining": 5,
                    "cost_remaining": 7.0,
                },
                "action_menu": [
                    _search_action(
                        "vision",
                        f"fictional quillkeeper garment variant {index + 1}",
                    ),
                    _search_action(
                        modality,
                        f"fictional quillkeeper passphrase variant {index + 1}",
                    ),
                    _finalize_action(),
                ],
            },
            expected_action_index=1,
            expected_state=_state(
                covered=[],
                missing_modality=modality,
                missing_hop=modality_hops[modality],
                cause="evidence_accessible_but_not_found",
                intent=intent_by_modality[modality],
                sufficient=0.0,
            ),
        )

    for index in range(3):
        modality = "ambient"
        handle = f"egpc.slot.route.ambient.{index + 1}"
        add(
            "route_ambient",
            index,
            {
                "task": "choose_next_action",
                "policy": "evidence_sufficiency",
                "question": (
                    "Which invented non-speech sound follows the fictional "
                    f"rune latch in variant {index + 1}?"
                ),
                "public_claim_slots": [_claim(handle, "Unheard ambient event.")],
                "observed_evidence": [],
                "known_pointers": [],
                "recent_public_history": [],
                "remaining_budget": {
                    "actions_remaining": 5,
                    "cost_remaining": 7.0,
                },
                "action_menu": [
                    _finalize_action(),
                    _search_action(
                        modality,
                        f"fictional rune latch sound variant {index + 1}",
                    ),
                    _search_action(
                        "speech",
                        f"unrelated narration variant {index + 1}",
                    ),
                ],
            },
            expected_action_index=1,
            expected_state=_state(
                covered=[],
                missing_modality=modality,
                missing_hop=modality_hops[modality],
                cause="evidence_accessible_but_not_found",
                intent=intent_by_modality[modality],
                sufficient=0.0,
            ),
        )

    for index, modality in enumerate(("speech", "ambient", "vision")):
        handle = f"egpc.slot.blocked.{index + 1}"
        add(
            "blocked_status",
            index,
            {
                "task": "choose_next_action",
                "policy": "evidence_sufficiency",
                "question": (
                    "Resolve the unavailable fictional route fact for "
                    f"clockwork alcove variant {index + 1}."
                ),
                "public_claim_slots": [_claim(handle, "Unavailable route fact.")],
                "observed_evidence": [],
                "known_pointers": [],
                "recent_public_history": [
                    {
                        "action": _search_action(
                            modality,
                            f"fictional alcove fact variant {index + 1}",
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
                "remaining_budget": {
                    "actions_remaining": 4,
                    "cost_remaining": 6.0,
                },
                "action_menu": [
                    _finalize_action(),
                    _status_action(modality),
                    _search_action(
                        modality,
                        f"repeat fictional alcove fact variant {index + 1}",
                    ),
                ],
            },
            expected_action_index=1,
            expected_state=_state(
                covered=[],
                missing_modality=modality,
                missing_hop=modality_hops[modality],
                cause="evidence_in_source_but_inaccessible",
                intent="check_channel_status",
                sufficient=0.0,
            ),
        )

    for index, modality in enumerate(("vision", "speech", "ambient")):
        handle = f"egpc.slot.restored.{index + 1}"
        add(
            "restoration_recovery",
            index,
            {
                "task": "choose_next_action",
                "policy": "evidence_sufficiency",
                "question": (
                    "Recover the fictional fact after route restoration for "
                    f"opalwork bay variant {index + 1}."
                ),
                "public_claim_slots": [_claim(handle, "Recoverable fictional fact.")],
                "observed_evidence": [],
                "known_pointers": [],
                "recent_public_history": [
                    {
                        "event_type": "public_route_status",
                        "route": modality,
                        "status": "restored",
                        "message": (
                            "The fictional route is now available; no fact "
                            "content is included in this status."
                        ),
                    }
                ],
                "remaining_budget": {
                    "actions_remaining": 4,
                    "cost_remaining": 6.0,
                },
                "action_menu": [
                    _status_action(modality),
                    _search_action(
                        modality,
                        f"restored fictional opalwork fact variant {index + 1}",
                    ),
                    _finalize_action(),
                ],
            },
            expected_action_index=1,
            expected_state=_state(
                covered=[],
                missing_modality=modality,
                missing_hop=modality_hops[modality],
                cause="evidence_in_source_but_inaccessible",
                intent="retry_restored_route",
                sufficient=0.0,
            ),
            restoration_case=True,
        )

    ready_facts = (
        ("vision", "the crest is saffron fork", "entity_identity"),
        ("speech", "the watchphrase is willow ember", "speech_content"),
        ("ambient", "the latch makes two felt knocks", "ambient_event"),
    )
    for index, (modality, fact, _) in enumerate(ready_facts):
        handle = f"egpc.slot.ready.{index + 1}"
        observation_id = f"egpc.obs.ready.{index + 1}"
        add(
            "finalize_ready",
            index,
            {
                "task": "choose_next_action",
                "policy": "evidence_sufficiency",
                "question": (
                    f"What completed fictional fact is recorded in variant "
                    f"{index + 1}?"
                ),
                "public_claim_slots": [_claim(handle, "Observed fictional fact.")],
                "observed_evidence": [
                    _observation(
                        observation_id,
                        modality,
                        f"In this fictional packet, {fact}.",
                        20 + index,
                    )
                ],
                "known_pointers": [],
                "recent_public_history": [],
                "remaining_budget": {
                    "actions_remaining": 3,
                    "cost_remaining": 5.0,
                },
                "action_menu": [
                    _search_action(
                        modality,
                        f"redundant fictional fact variant {index + 1}",
                        excluded=[observation_id],
                    ),
                    _finalize_action(),
                ],
            },
            expected_action_index=1,
            expected_state=_state(
                covered=[handle],
                missing_modality=None,
                missing_hop=None,
                cause="not_missing",
                intent="finalize_answer",
                sufficient=1.0,
            ),
        )

    for index, modality in enumerate(("ambient", "vision", "speech")):
        handle = f"egpc.slot.continue.{index + 1}"
        add(
            "premature_stop_guard",
            index,
            {
                "task": "choose_next_action",
                "policy": "evidence_sufficiency",
                "question": (
                    "Do not stop before finding the fictional missing fact "
                    f"for heliotrope cabinet variant {index + 1}."
                ),
                "public_claim_slots": [_claim(handle, "Still-unobserved fact.")],
                "observed_evidence": [],
                "known_pointers": [],
                "recent_public_history": [],
                "remaining_budget": {
                    "actions_remaining": 3,
                    "cost_remaining": 5.0,
                },
                "action_menu": [
                    _finalize_action(),
                    _search_action(
                        modality,
                        f"fictional heliotrope cabinet fact variant {index + 1}",
                    ),
                ],
            },
            expected_action_index=1,
            expected_state=_state(
                covered=[],
                missing_modality=modality,
                missing_hop=modality_hops[modality],
                cause="evidence_accessible_but_not_found",
                intent=intent_by_modality[modality],
                sufficient=0.0,
            ),
            premature_stop_case=True,
        )

    for index, modality in enumerate(("vision", "speech", "ambient")):
        handle = f"egpc.slot.no.route.{index + 1}"
        add(
            "no_route_abstain",
            index,
            {
                "task": "choose_next_action",
                "policy": "evidence_sufficiency",
                "question": (
                    "Safely close the fictional unsupplied fact request for "
                    f"lacquer moonbox variant {index + 1}."
                ),
                "public_claim_slots": [_claim(handle, "Absent fictional fact.")],
                "observed_evidence": [],
                "known_pointers": [],
                "recent_public_history": [
                    {
                        "event_type": "public_route_status",
                        "route": modality,
                        "status": "not_provided",
                        "message": (
                            "This source-free packet provides no acquisition "
                            "route for the requested fictional fact."
                        ),
                    }
                ],
                "remaining_budget": {
                    "actions_remaining": 1,
                    "cost_remaining": 1.0,
                },
                "action_menu": [_finalize_action()],
            },
            expected_action_index=0,
            expected_state=_state(
                covered=[],
                missing_modality=modality,
                missing_hop=modality_hops[modality],
                cause="source_evidence_absent",
                intent="finalize_abstain",
                sufficient=0.0,
            ),
        )

    return packets, labels


def _finalizer_cases() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    packets: list[dict[str, Any]] = []
    labels: dict[str, Any] = {}
    facts = (
        ("vision", "copper kite", "entity_identity"),
        ("speech", "juniper ferry", "speech_content"),
        ("ambient", "three velvet ticks", "ambient_event"),
        ("vision", "lilac chevron", "entity_identity"),
    )

    def add(
        stratum: str,
        public_input: Mapping[str, Any],
        label: Mapping[str, Any],
    ) -> None:
        ordinal = len(packets) + 1
        case_id = f"egpc-finalizer-{ordinal:03d}"
        packets.append(
            _packet(
                case_id=case_id,
                case_type="finalizer",
                stratum=stratum,
                public_input=public_input,
            )
        )
        labels[case_id] = copy.deepcopy(dict(label))

    for index, (modality, value, _) in enumerate(facts):
        handle = f"egpc.slot.final.single.{index + 1}"
        observation_id = f"egpc.obs.final.single.{index + 1}"
        subject = f"fictional palimpsest pod {index + 1}"
        add(
            "supported_single",
            {
                "task": "grounded_finalization",
                "condition": "public_fictional_complete",
                "question": f"What archived mark belongs to {subject}?",
                "public_claim_slots": [_claim(handle, "Archived fictional mark.")],
                "observed_evidence": [
                    _observation(
                        observation_id,
                        modality,
                        f"The {subject} records its archived mark as {value}.",
                        40 + index,
                    )
                ],
            },
            {
                "answer_mode": "answer",
                "answer_terms": [value],
                "required_terms_by_claim": {handle: [value]},
                "expected_citations": {handle: [observation_id]},
                "restoration_case": False,
            },
        )

    dual_values = (
        (("umber spindle", "four reed taps"), ("vision", "ambient")),
        (("pearl ladder", "moss lantern"), ("vision", "speech")),
        (("azure notch", "two hushed chimes"), ("vision", "ambient")),
        (("coral wicket", "bracken key"), ("vision", "speech")),
    )
    for index, (values, modalities) in enumerate(dual_values):
        first_handle = f"egpc.slot.final.dual.{index + 1}.a"
        second_handle = f"egpc.slot.final.dual.{index + 1}.b"
        first_observation = f"egpc.obs.final.dual.{index + 1}.a"
        second_observation = f"egpc.obs.final.dual.{index + 1}.b"
        subject = f"fictional cadenza drawer {index + 1}"
        add(
            "supported_dual",
            {
                "task": "grounded_finalization",
                "condition": "public_fictional_complete",
                "question": (
                    f"Report both archived attributes of {subject} in the "
                    "order requested."
                ),
                "public_claim_slots": [
                    _claim(first_handle, "First archived fictional attribute."),
                    _claim(second_handle, "Second archived fictional attribute."),
                ],
                "observed_evidence": [
                    _observation(
                        first_observation,
                        modalities[0],
                        f"The first attribute of {subject} is {values[0]}.",
                        50 + index * 2,
                    ),
                    _observation(
                        second_observation,
                        modalities[1],
                        f"The second attribute of {subject} is {values[1]}.",
                        51 + index * 2,
                    ),
                ],
            },
            {
                "answer_mode": "answer",
                "answer_terms": list(values),
                "required_terms_by_claim": {
                    first_handle: [values[0]],
                    second_handle: [values[1]],
                },
                "expected_citations": {
                    first_handle: [first_observation],
                    second_handle: [second_observation],
                },
                "restoration_case": False,
            },
        )

    recovered_values = (
        ("vision", "silver trefoil"),
        ("speech", "orchard comet"),
        ("ambient", "one cork flutter"),
        ("speech", "violet causeway"),
    )
    for index, (modality, value) in enumerate(recovered_values):
        handle = f"egpc.slot.final.restored.{index + 1}"
        observation_id = f"egpc.obs.final.restored.{index + 1}"
        subject = f"fictional meridian folio {index + 1}"
        add(
            "restored_support",
            {
                "task": "grounded_finalization",
                "condition": "public_fictional_route_recovered",
                "question": (
                    f"What recovered archived value belongs to {subject}?"
                ),
                "public_claim_slots": [
                    _claim(handle, "Recovered archived fictional value.")
                ],
                "observed_evidence": [
                    _observation(
                        observation_id,
                        modality,
                        (
                            "After the public fictional route recovered, "
                            f"{subject} yielded the value {value}."
                        ),
                        70 + index,
                    )
                ],
            },
            {
                "answer_mode": "answer",
                "answer_terms": [value],
                "required_terms_by_claim": {handle: [value]},
                "expected_citations": {handle: [observation_id]},
                "restoration_case": True,
            },
        )

    blocked_specs = (
        ("vision", "entity_identity"),
        ("speech", "speech_content"),
        ("ambient", "ambient_event"),
        ("vision", "temporal_order"),
    )
    for index, (modality, hop) in enumerate(blocked_specs):
        handle = f"egpc.slot.final.blocked.{index + 1}"
        add(
            "blocked_abstention",
            {
                "task": "grounded_finalization",
                "condition": "public_fictional_incomplete",
                "question": (
                    "Supply the deliberately absent fictional value for "
                    f"kinetic vellum cell {index + 1}."
                ),
                "public_claim_slots": [
                    _claim(handle, "Deliberately absent fictional value.")
                ],
                "observed_evidence": [],
            },
            {
                "answer_mode": "abstain",
                "answer_terms": [],
                "required_terms_by_claim": {},
                "expected_citations": {},
                "required_missing_modality": modality,
                "required_missing_hop": hop,
                "restoration_case": False,
            },
        )

    return packets, labels


def _walk(value: Any, path: str = "$") -> list[tuple[str, str, Any]]:
    rows: list[tuple[str, str, Any]] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            rows.append((child_path, str(key), child))
            rows.extend(_walk(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            rows.extend(_walk(child, f"{path}[{index}]"))
    return rows


def validate_prompt_packet(packet: Mapping[str, Any]) -> None:
    """Enforce the model-facing public-fictional and source-free boundary."""

    required = {
        "schema_version",
        "case_id",
        "case_type",
        "stratum",
        "public_fictional",
        "source_free",
        "prospective_unseen",
        "packet_notice",
        "public_input",
    }
    if set(packet) != required:
        raise CompetenceSuiteError("PROMPT_PACKET_FIELD_SET_MISMATCH")
    if packet.get("schema_version") != PACKET_SCHEMA:
        raise CompetenceSuiteError("PROMPT_PACKET_SCHEMA_MISMATCH")
    if packet.get("case_type") not in FACTOR_NAMES:
        raise CompetenceSuiteError("PROMPT_PACKET_CASE_TYPE_INVALID")
    for key in ("public_fictional", "source_free", "prospective_unseen"):
        if packet.get(key) is not True:
            raise CompetenceSuiteError(f"PROMPT_PACKET_FLAG_REQUIRED:{key}")
    notice = str(packet.get("packet_notice", "")).casefold()
    if "fictional" not in notice or "source-free" not in notice:
        raise CompetenceSuiteError("PROMPT_PACKET_NOTICE_INVALID")
    try:
        assert_public_surface(packet)
    except SchemaViolation as exc:
        raise CompetenceSuiteError(exc.code) from exc
    serialized = json.dumps(packet, sort_keys=True, ensure_ascii=False)
    for pattern in PROHIBITED_PROMPT_PATTERNS:
        if pattern.search(serialized):
            raise CompetenceSuiteError("PROMPT_PACKET_PROHIBITED_TERM")
    for path, key, child in _walk(packet):
        if key.casefold() in PROHIBITED_PROMPT_KEYS:
            raise CompetenceSuiteError(f"PROMPT_PRIVATE_KEY_EXPOSED:{path}")
        if isinstance(child, str):
            folded = child.casefold()
            if folded.startswith(PROHIBITED_URI_PREFIXES):
                raise CompetenceSuiteError(f"PROMPT_URI_FORBIDDEN:{path}")
            if folded.endswith(PROHIBITED_MEDIA_SUFFIXES):
                raise CompetenceSuiteError(f"PROMPT_MEDIA_PATH_FORBIDDEN:{path}")


def public_packet_projection(
    artifact: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Return the only packet projection authorized for model prompts."""

    public_suite = artifact.get("public_suite")
    if not isinstance(public_suite, Mapping):
        raise CompetenceSuiteError("PUBLIC_SUITE_MISSING")
    packets = public_suite.get("packets")
    if not isinstance(packets, list):
        raise CompetenceSuiteError("PUBLIC_PACKETS_NOT_LIST")
    projected = [copy.deepcopy(packet) for packet in packets]
    for packet in projected:
        validate_prompt_packet(packet)
    return projected


def _normalized_question(packet: Mapping[str, Any]) -> str:
    question = str(packet["public_input"].get("question", ""))
    return " ".join(question.casefold().split())


def _reference_packets(root: Path) -> dict[str, list[dict[str, Any]]]:
    references: dict[str, list[dict[str, Any]]] = {}
    for name, relative in (
        ("granite_v2", GRANITE_PUBLIC_PATH),
        ("qwen3_v2", QWEN_PUBLIC_PATH),
    ):
        document = load_json(root / relative)
        cases = document.get("cases")
        if not isinstance(cases, list):
            raise CompetenceSuiteError(f"REFERENCE_CASES_INVALID:{relative}")
        references[name] = [dict(case) for case in cases]
    references["external_gateway_smoke"] = [
        {
            "case_id": 'PUBLIC_REDACTED_IDENTIFIER',
            "public_input": {
                "question": (
                    "In the fictional closed-world record, what color is "
                    "prism P1?"
                )
            },
        },
        {
            "case_id": 'PUBLIC_REDACTED_IDENTIFIER',
            "public_input": {
                "question": (
                    "What shape is the fictional closed-world badge B1?"
                )
            },
        },
    ]
    return references


def compute_non_overlap_audit(
    packets: Sequence[Mapping[str, Any]],
    *,
    root: Path = ROOT,
) -> dict[str, Any]:
    """Compare identifiers, questions, and complete public inputs."""

    candidate_ids = {str(packet["case_id"]) for packet in packets}
    candidate_questions = {_normalized_question(packet) for packet in packets}
    candidate_inputs = {
        sha256_json(packet["public_input"]) for packet in packets
    }
    references = _reference_packets(root)
    reports: dict[str, Any] = {}
    for name, rows in references.items():
        reference_ids = {str(row.get("case_id")) for row in rows}
        reference_questions = {
            " ".join(
                str(row.get("public_input", {}).get("question", ""))
                .casefold()
                .split()
            )
            for row in rows
        }
        reference_inputs = {
            sha256_json(row.get("public_input", {})) for row in rows
        }
        reports[name] = {
            "reference_case_count": len(rows),
            "case_id_overlap": sorted(candidate_ids & reference_ids),
            "normalized_question_overlap": sorted(
                candidate_questions & reference_questions
            ),
            "public_input_hash_overlap": sorted(
                candidate_inputs & reference_inputs
            ),
        }
    smoke_overlap = candidate_ids & REFERENCE_SMOKE_IDS
    passed = not smoke_overlap and all(
        not report["case_id_overlap"]
        and not report["normalized_question_overlap"]
        and not report["public_input_hash_overlap"]
        for report in reports.values()
    )
    return {
        "schema_version": (
            "av-trace.external-gateway-public-competence-overlap-audit/1.0"
        ),
        "comparators": reports,
        "smoke_fixture_case_id_overlap": sorted(smoke_overlap),
        "criteria": [
            "no_case_id_overlap",
            "no_normalized_question_overlap",
            "no_complete_public_input_hash_overlap",
        ],
        "status": "PASS" if passed else "FAIL",
    }


def build_frozen_artifact(*, root: Path = ROOT) -> dict[str, Any]:
    """Build the byte-stable prospective freeze without model execution."""

    controller_packets, controller_labels = _controller_cases()
    finalizer_packets, finalizer_labels = _finalizer_cases()
    packets = controller_packets + finalizer_packets
    labels = {**controller_labels, **finalizer_labels}
    for packet in packets:
        validate_prompt_packet(packet)
    counts = Counter(str(packet["case_type"]) for packet in packets)
    if dict(counts) != EXPECTED_COUNTS:
        raise CompetenceSuiteError(f"CASE_COUNT_DRIFT:{dict(counts)}")
    if set(labels) != {str(packet["case_id"]) for packet in packets}:
        raise CompetenceSuiteError("PRIVATE_LABEL_CASE_SET_MISMATCH")

    public_suite = {
        "schema_version": PUBLIC_SUITE_SCHEMA,
        "suite_id": SUITE_ID,
        "freeze_label": FREEZE_LABEL,
        "execution_status": "NOT_RUN",
        "packets": packets,
    }
    evaluator_private = {
        "schema_version": PRIVATE_SCHEMA,
        "suite_id": SUITE_ID,
        "private_canary": (
            "egpc-private-canary-7f4dbd4b5ee5431aa8d21b8cc8c41e1d"
        ),
        "labels": labels,
    }
    overlap = compute_non_overlap_audit(packets, root=root)
    if overlap["status"] != "PASS":
        raise CompetenceSuiteError("NON_OVERLAP_AUDIT_FAILED")
    packet_hashes = {
        str(packet["case_id"]): sha256_json(packet) for packet in packets
    }
    component_hashes = {
        "public_suite": sha256_json(public_suite),
        "evaluator_private": sha256_json(evaluator_private),
        "prompt_policy": sha256_json(PROMPT_POLICY),
        "thresholds": sha256_json(THRESHOLDS),
        "overlap_audit": sha256_json(overlap),
    }
    reference_hashes = {
        str(GRANITE_PUBLIC_PATH): sha256_file(root / GRANITE_PUBLIC_PATH),
        str(QWEN_PUBLIC_PATH): sha256_file(root / QWEN_PUBLIC_PATH),
    }
    core = {
        "schema_version": SCHEMA_VERSION,
        "suite_id": SUITE_ID,
        "freeze_label": FREEZE_LABEL,
        "frozen_date": FREEZE_DATE,
        "status": FROZEN_NOT_RUN,
        "adapter_schema_version": ADAPTER_SCHEMA_VERSION,
        "gate_purpose": (
            "Prospective Gate C competence sensitivity for an external "
            "strong controller/finalizer; no scientific claim."
        ),
        "content_boundary": {
            "public_fictional": True,
            "source_free": True,
            "text_packets_only": True,
            "real_source_identifiers_present": False,
            "media_present": False,
            "scientific_content_present": False,
            "restricted_content_present": False,
            "private_labels_present_in_prompt_projection": False,
        },
        "case_balance": {
            "controller": 24,
            "controller_cases_per_stratum": 3,
            "controller_strata": list(CONTROLLER_STRATA),
            "finalizer": 16,
            "finalizer_cases_per_stratum": 4,
            "finalizer_strata": list(FINALIZER_STRATA),
            "total": 40,
        },
        "prompt_policy": copy.deepcopy(PROMPT_POLICY),
        "thresholds": copy.deepcopy(THRESHOLDS),
        "public_suite": public_suite,
        "evaluator_private": evaluator_private,
        "one_shot_state": {
            "state": "NOT_RUN",
            "gateway_calls": 0,
            "model_outputs_present": False,
            "partial_runs": 0,
            "full_suite_runs": 0,
            "maximum_full_suite_runs": 1,
            "execution_authorized_by_freeze": False,
            "separate_explicit_execution_authorization_required": True,
            "reruns_after_any_model_output": 0,
        },
        "non_overlap_audit": overlap,
    }
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "suite_id": SUITE_ID,
        "deterministic_generation": True,
        "randomness_used": False,
        "generated_at_runtime": False,
        "case_count": len(packets),
        "packet_hashes": packet_hashes,
        "component_hashes": component_hashes,
        "reference_file_hashes": reference_hashes,
        "freeze_payload_sha256": sha256_json(core),
    }
    artifact = {**core, "freeze_manifest": manifest}
    validate_frozen_artifact(artifact, root=root, compare_manifest=False)
    return artifact


def validate_frozen_artifact(
    artifact: Mapping[str, Any],
    *,
    root: Path = ROOT,
    compare_manifest: bool = True,
) -> None:
    """Fail closed on any schema, privacy, balance, overlap, or hash drift."""

    if artifact.get("schema_version") != SCHEMA_VERSION:
        raise CompetenceSuiteError("FREEZE_SCHEMA_MISMATCH")
    if artifact.get("suite_id") != SUITE_ID:
        raise CompetenceSuiteError("FREEZE_SUITE_ID_MISMATCH")
    if artifact.get("freeze_label") != FREEZE_LABEL:
        raise CompetenceSuiteError("FREEZE_LABEL_MISMATCH")
    if artifact.get("status") != FROZEN_NOT_RUN:
        raise CompetenceSuiteError("FREEZE_STATUS_MISMATCH")
    if artifact.get("adapter_schema_version") != ADAPTER_SCHEMA_VERSION:
        raise CompetenceSuiteError("ADAPTER_SCHEMA_MISMATCH")
    one_shot = artifact.get("one_shot_state")
    if not isinstance(one_shot, Mapping) or one_shot != {
        "state": "NOT_RUN",
        "gateway_calls": 0,
        "model_outputs_present": False,
        "partial_runs": 0,
        "full_suite_runs": 0,
        "maximum_full_suite_runs": 1,
        "execution_authorized_by_freeze": False,
        "separate_explicit_execution_authorization_required": True,
        "reruns_after_any_model_output": 0,
    }:
        raise CompetenceSuiteError("ONE_SHOT_NOT_RUN_STATE_INVALID")
    packets = public_packet_projection(artifact)
    counts = Counter(str(packet["case_type"]) for packet in packets)
    if dict(counts) != EXPECTED_COUNTS:
        raise CompetenceSuiteError("FREEZE_CASE_COUNTS_MISMATCH")
    strata = Counter(str(packet["stratum"]) for packet in packets)
    if any(strata[name] != 3 for name in CONTROLLER_STRATA):
        raise CompetenceSuiteError("CONTROLLER_STRATUM_BALANCE_MISMATCH")
    if any(strata[name] != 4 for name in FINALIZER_STRATA):
        raise CompetenceSuiteError("FINALIZER_STRATUM_BALANCE_MISMATCH")
    private = artifact.get("evaluator_private")
    if not isinstance(private, Mapping):
        raise CompetenceSuiteError("PRIVATE_EVALUATOR_MISSING")
    labels = private.get("labels")
    if not isinstance(labels, Mapping):
        raise CompetenceSuiteError("PRIVATE_LABELS_INVALID")
    if set(labels) != {str(packet["case_id"]) for packet in packets}:
        raise CompetenceSuiteError("PRIVATE_LABEL_CASE_SET_MISMATCH")
    projection_text = json.dumps(packets, sort_keys=True)
    if str(private.get("private_canary")) in projection_text:
        raise CompetenceSuiteError("PRIVATE_CANARY_EXPOSED")
    overlap = compute_non_overlap_audit(packets, root=root)
    if overlap["status"] != "PASS":
        raise CompetenceSuiteError("NON_OVERLAP_AUDIT_FAILED")
    if artifact.get("non_overlap_audit") != overlap:
        raise CompetenceSuiteError("NON_OVERLAP_AUDIT_DRIFT")
    if artifact.get("thresholds") != THRESHOLDS:
        raise CompetenceSuiteError("THRESHOLD_DRIFT")
    if artifact.get("prompt_policy") != PROMPT_POLICY:
        raise CompetenceSuiteError("PROMPT_POLICY_DRIFT")
    if not compare_manifest:
        return
    manifest = artifact.get("freeze_manifest")
    if not isinstance(manifest, Mapping):
        raise CompetenceSuiteError("FREEZE_MANIFEST_MISSING")
    core = {key: value for key, value in artifact.items() if key != "freeze_manifest"}
    expected_components = {
        "public_suite": sha256_json(artifact["public_suite"]),
        "evaluator_private": sha256_json(artifact["evaluator_private"]),
        "prompt_policy": sha256_json(artifact["prompt_policy"]),
        "thresholds": sha256_json(artifact["thresholds"]),
        "overlap_audit": sha256_json(artifact["non_overlap_audit"]),
    }
    if manifest.get("component_hashes") != expected_components:
        raise CompetenceSuiteError("COMPONENT_HASH_MISMATCH")
    expected_packet_hashes = {
        str(packet["case_id"]): sha256_json(packet) for packet in packets
    }
    if manifest.get("packet_hashes") != expected_packet_hashes:
        raise CompetenceSuiteError("PACKET_HASH_MISMATCH")
    if manifest.get("freeze_payload_sha256") != sha256_json(core):
        raise CompetenceSuiteError("FREEZE_PAYLOAD_HASH_MISMATCH")
    reference_hashes = {
        str(GRANITE_PUBLIC_PATH): sha256_file(root / GRANITE_PUBLIC_PATH),
        str(QWEN_PUBLIC_PATH): sha256_file(root / QWEN_PUBLIC_PATH),
    }
    if manifest.get("reference_file_hashes") != reference_hashes:
        raise CompetenceSuiteError("REFERENCE_FILE_HASH_MISMATCH")
    if compare_manifest:
        rebuilt = build_frozen_artifact(root=root)
        if dict(artifact) != rebuilt:
            raise CompetenceSuiteError("DETERMINISTIC_REBUILD_MISMATCH")


def _fraction(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def _attempts(value: Any) -> tuple[RawFactorAttempt, ...]:
    if not isinstance(value, list) or not value or len(value) > 2:
        raise CompetenceSuiteError("FACTOR_ATTEMPTS_INVALID")
    attempts: list[RawFactorAttempt] = []
    for index, row in enumerate(value, 1):
        if not isinstance(row, Mapping):
            raise CompetenceSuiteError("FACTOR_ATTEMPT_NOT_OBJECT")
        if set(row) != {"attempt_index", "kind", "raw_output"}:
            raise CompetenceSuiteError("FACTOR_ATTEMPT_FIELD_SET_MISMATCH")
        if row["attempt_index"] != index:
            raise CompetenceSuiteError("FACTOR_ATTEMPT_INDEX_MISMATCH")
        expected_kind = "initial" if index == 1 else "schema_only_retry"
        if row["kind"] != expected_kind:
            raise CompetenceSuiteError("FACTOR_ATTEMPT_KIND_MISMATCH")
        raw = row["raw_output"]
        if not isinstance(raw, str):
            raise CompetenceSuiteError("FACTOR_RAW_OUTPUT_NOT_TEXT")
        attempts.append(
            RawFactorAttempt.from_text(
                raw,
                attempt_index=index,
                kind=(
                    AttemptKind.INITIAL
                    if index == 1
                    else AttemptKind.SCHEMA_ONLY_RETRY
                ),
            )
        )
    return tuple(attempts)


def _case_attempts(
    row: Mapping[str, Any],
    case_type: str,
) -> dict[str, tuple[RawFactorAttempt, ...]]:
    factor_attempts = row.get("factor_attempts")
    if not isinstance(factor_attempts, Mapping):
        raise CompetenceSuiteError("CASE_FACTOR_ATTEMPTS_INVALID")
    required = set(FACTOR_NAMES[case_type])
    if set(factor_attempts) != required:
        raise CompetenceSuiteError("CASE_FACTOR_SET_MISMATCH")
    return {name: _attempts(factor_attempts[name]) for name in required}


def _raw_private_exposure(
    attempts: Mapping[str, Sequence[RawFactorAttempt]],
    private_canary: str,
) -> bool:
    prohibited_names = (
        "expected_action_index",
        "expected_evidence_state",
        "required_terms_by_claim",
        "expected_citations",
        "private_canary",
    )
    for rows in attempts.values():
        for attempt in rows:
            text = attempt.raw_output.decode("utf-8", errors="replace")
            folded = text.casefold()
            if private_canary in text or any(
                name in folded for name in prohibited_names
            ):
                return True
    return False


def _score_finalizer(
    packet: Mapping[str, Any],
    label: Mapping[str, Any],
    result: Any,
) -> dict[str, Any]:
    if (
        result.projection_status is not ProjectionStatus.ACCEPTED
        or result.canonical_envelope is None
    ):
        return {
            "structured_valid": False,
            "semantic_success": False,
            "supported_finalization_success": False,
            "blocked_abstention_success": False,
            "exact_citation_selection": False,
            "unsupported_claims": 0,
            "unobserved_citation_selections": 0,
            "error_code": result.projection_error_code,
        }
    final = result.canonical_envelope["final_answer"]
    citation_map = result.canonical_envelope["claim_to_citations"]
    observed_ids = {
        str(item["observation_id"])
        for item in packet["public_input"]["observed_evidence"]
    }
    selected_ids = {
        str(observation_id)
        for values in citation_map.values()
        for observation_id in values
    }
    unobserved = len(selected_ids - observed_ids)
    exact_citations = citation_map == label["expected_citations"]
    if label["answer_mode"] == "abstain":
        diagnosis = final["diagnosis"]
        missing_modalities = {
            modality
            for modality, probability in diagnosis[
                "modality_probabilities"
            ].items()
            if probability >= 0.5
        }
        semantic = bool(
            final["answer_mode"] == "abstain"
            and label["required_missing_modality"] in missing_modalities
            and label["required_missing_hop"] in diagnosis["hop_types"]
            and exact_citations
        )
        return {
            "structured_valid": True,
            "semantic_success": semantic,
            "supported_finalization_success": False,
            "blocked_abstention_success": semantic,
            "exact_citation_selection": exact_citations,
            "unsupported_claims": 0,
            "unobserved_citation_selections": unobserved,
            "error_code": None if semantic else "ABSTENTION_SEMANTICS_FAILED",
        }

    answer_text = final["natural_language_answer"].casefold()
    answer_terms_present = all(
        str(term).casefold() in answer_text for term in label["answer_terms"]
    )
    claims = {
        str(claim["registered_claim_id"]): claim for claim in final["claims"]
    }
    unsupported = 0
    for handle, terms in label["required_terms_by_claim"].items():
        claim = claims.get(handle)
        if claim is None:
            unsupported += 1
            continue
        claim_text = str(claim["text"]).casefold()
        if any(str(term).casefold() not in claim_text for term in terms):
            unsupported += 1
        selected = citation_map.get(handle, [])
        if selected != label["expected_citations"][handle]:
            unsupported += 1
    semantic = bool(
        final["answer_mode"] == "answer"
        and answer_terms_present
        and unsupported == 0
        and exact_citations
        and unobserved == 0
    )
    return {
        "structured_valid": True,
        "semantic_success": semantic,
        "supported_finalization_success": semantic,
        "blocked_abstention_success": False,
        "exact_citation_selection": exact_citations,
        "unsupported_claims": unsupported,
        "unobserved_citation_selections": unobserved,
        "error_code": None if semantic else "SUPPORTED_FINALIZATION_FAILED",
    }


def apply_thresholds(
    metrics: Mapping[str, Any],
    thresholds: Mapping[str, Any] = THRESHOLDS,
) -> dict[str, Any]:
    """Apply frozen Gate C mechanics; absent/malformed metrics fail closed."""

    by_stratum = metrics.get("correct_first_actions_by_stratum")
    state_components = metrics.get("state_component_accuracy")
    required_action_strata = set(CONTROLLER_STRATA)
    required_state_fields = set(EVIDENCE_STATE_FIELDS)
    checks = {
        "minimum_cases": (
            isinstance(metrics.get("case_count"), int)
            and metrics["case_count"] >= thresholds["minimum_cases"]
        ),
        "complete_case_set": (
            metrics.get("complete_case_set")
            is thresholds["complete_case_set_required"]
        ),
        "valid_structured": (
            isinstance(metrics.get("valid_structured_model_calls"), float)
            and metrics["valid_structured_model_calls"]
            >= thresholds["valid_structured_model_calls_min"]
        ),
        "actions_overall": (
            isinstance(metrics.get("correct_first_actions_overall"), float)
            and metrics["correct_first_actions_overall"]
            >= thresholds["correct_first_actions_overall_min"]
        ),
        "actions_each_stratum": (
            isinstance(by_stratum, Mapping)
            and set(by_stratum) == required_action_strata
            and all(
                isinstance(value, float)
                and value
                >= thresholds["correct_first_actions_each_stratum_min"]
                for value in by_stratum.values()
            )
        ),
        "joint_state": (
            isinstance(metrics.get("exact_six_field_state"), float)
            and metrics["exact_six_field_state"]
            >= thresholds["exact_six_field_state_min"]
        ),
        "state_components": (
            isinstance(state_components, Mapping)
            and set(state_components) == required_state_fields
            and all(
                isinstance(value, float)
                and value >= thresholds["each_state_component_min"]
                for value in state_components.values()
            )
        ),
        "blocked_abstention": (
            isinstance(metrics.get("blocked_correct_abstention"), float)
            and metrics["blocked_correct_abstention"]
            >= thresholds["blocked_correct_abstention_min"]
        ),
        "restoration_recovery": (
            isinstance(metrics.get("restoration_recovery"), float)
            and metrics["restoration_recovery"]
            >= thresholds["restoration_recovery_min"]
        ),
        "supported_finalization": (
            isinstance(metrics.get("supported_finalization"), float)
            and metrics["supported_finalization"]
            >= thresholds["supported_finalization_min"]
        ),
        "citations": (
            isinstance(metrics.get("exact_citation_selection"), float)
            and metrics["exact_citation_selection"]
            >= thresholds["exact_citation_selection_min"]
        ),
        "premature_stop": (
            isinstance(metrics.get("premature_stop_prevention"), float)
            and metrics["premature_stop_prevention"]
            >= thresholds["premature_stop_prevention_min"]
        ),
        "unsupported_claims": (
            metrics.get("unsupported_required_claims")
            == thresholds["unsupported_required_claims_max"]
        ),
        "unobserved_citations": (
            metrics.get("unobserved_citation_selections")
            == thresholds["unobserved_citation_selections_max"]
        ),
        "private_exposure": (
            metrics.get("private_label_exposures")
            == thresholds["private_label_exposures_max"]
        ),
        "no_substitution": (
            metrics.get("deterministic_answer_substitutions")
            == thresholds["deterministic_answer_substitutions_max"]
        ),
    }
    integrity_names = {
        "minimum_cases",
        "complete_case_set",
        "unsupported_claims",
        "unobserved_citations",
        "private_exposure",
        "no_substitution",
    }
    competence_names = set(checks) - integrity_names
    if all(checks.values()):
        disposition = "GO"
    elif any(not checks[name] for name in integrity_names):
        disposition = "NO_GO"
    elif sum(not checks[name] for name in competence_names) == 1:
        disposition = "REPAIR"
    else:
        disposition = "NO_GO"
    return {
        "gate_checks": checks,
        "decision": f"EXTERNAL_GATEWAY_PUBLIC_COMPETENCE_GATE_C_{disposition}",
    }


def evaluate_submission(
    artifact: Mapping[str, Any],
    submission: Mapping[str, Any],
    *,
    root: Path = ROOT,
) -> dict[str, Any]:
    """Replay v2 factors and evaluate once; never performs model inference."""

    validate_frozen_artifact(artifact, root=root)
    if submission.get("schema_version") != SUBMISSION_SCHEMA:
        raise CompetenceSuiteError("SUBMISSION_SCHEMA_MISMATCH")
    if submission.get("suite_id") != SUITE_ID:
        raise CompetenceSuiteError("SUBMISSION_SUITE_ID_MISMATCH")
    if submission.get("execution_state") != "COMPLETE_UNEVALUATED":
        raise CompetenceSuiteError("SUBMISSION_EXECUTION_STATE_INVALID")
    if submission.get("public_suite_sha256") != artifact["freeze_manifest"][
        "component_hashes"
    ]["public_suite"]:
        raise CompetenceSuiteError("SUBMISSION_PUBLIC_SUITE_HASH_MISMATCH")
    if submission.get("private_fields_supplied_to_model") is not False:
        raise CompetenceSuiteError("SUBMISSION_PRIVATE_EXPOSURE_ATTESTATION_FAILED")
    substitutions = submission.get("deterministic_answer_substitutions")
    if not isinstance(substitutions, int) or substitutions < 0:
        raise CompetenceSuiteError("SUBMISSION_SUBSTITUTION_COUNT_INVALID")
    rows = submission.get("cases")
    if not isinstance(rows, list):
        raise CompetenceSuiteError("SUBMISSION_CASES_NOT_LIST")
    packets = public_packet_projection(artifact)
    packet_by_id = {str(packet["case_id"]): packet for packet in packets}
    by_id = {
        str(row.get("case_id")): row
        for row in rows
        if isinstance(row, Mapping)
    }
    complete_case_set = (
        len(by_id) == len(rows)
        and set(by_id) == set(packet_by_id)
        and len(rows) == len(packets)
    )
    if not complete_case_set:
        raise CompetenceSuiteError("SUBMISSION_CASE_SET_MISMATCH")
    labels = artifact["evaluator_private"]["labels"]
    private_canary = str(artifact["evaluator_private"]["private_canary"])

    scores: list[dict[str, Any]] = []
    private_exposures = 0
    for packet in packets:
        case_id = str(packet["case_id"])
        case_type = str(packet["case_type"])
        row = by_id[case_id]
        attempts = _case_attempts(row, case_type)
        exposure = _raw_private_exposure(attempts, private_canary)
        private_exposures += int(exposure)
        label = labels[case_id]
        public_input = packet["public_input"]
        handles = [
            str(item["claim_handle"])
            for item in public_input["public_claim_slots"]
        ]
        if case_type == "controller":
            replay = parse_controller_factors(
                action_menu=public_input["action_menu"],
                claim_handles=handles,
                observed_evidence=public_input["observed_evidence"],
                action_attempts=attempts["action_choice"],
                evidence_state_attempts=attempts["evidence_state"],
            )
            action_correct = bool(
                replay.native_action is not None
                and replay.native_action.action_index
                == label["expected_action_index"]
            )
            state_valid = bool(
                replay.evidence_state_factor.status is FactorStatus.VALID
                and isinstance(replay.evidence_state_factor.value, Mapping)
            )
            state_components = {
                field: bool(
                    state_valid
                    and replay.evidence_state_factor.value[field]
                    == label["expected_evidence_state"][field]
                )
                for field in EVIDENCE_STATE_FIELDS
            }
            structured = bool(
                replay.action_factor.status is FactorStatus.VALID
                and state_valid
                and replay.state_projection.status is ProjectionStatus.ACCEPTED
                and replay.canonical_decision is not None
            )
            premature_success = (
                action_correct
                and replay.native_action is not None
                and replay.native_action.action["tool"] != "finalize"
                if label["premature_stop_case"]
                else None
            )
            score = {
                "case_id": case_id,
                "case_type": case_type,
                "stratum": packet["stratum"],
                "structured_valid": structured,
                "action_correct": action_correct,
                "state_component_correct": state_components,
                "exact_six_field_state": all(state_components.values()),
                "restoration_success": (
                    action_correct if label["restoration_case"] else None
                ),
                "premature_stop_prevented": premature_success,
                "private_exposure": exposure,
                "unsupported_claims": 0,
                "unobserved_citation_selections": 0,
            }
        else:
            replay = parse_finalizer_factors(
                claim_handles=handles,
                observations=public_input["observed_evidence"],
                attempts_by_factor=attempts,
            )
            finalizer_score = _score_finalizer(packet, label, replay)
            score = {
                "case_id": case_id,
                "case_type": case_type,
                "stratum": packet["stratum"],
                "restoration_success": (
                    finalizer_score["semantic_success"]
                    if label["restoration_case"]
                    else None
                ),
                "private_exposure": exposure,
                **finalizer_score,
            }
        scores.append(score)

    controllers = [row for row in scores if row["case_type"] == "controller"]
    finalizers = [row for row in scores if row["case_type"] == "finalizer"]
    supported = [
        row for row in finalizers if row["stratum"] != "blocked_abstention"
    ]
    blocked = [
        row for row in finalizers if row["stratum"] == "blocked_abstention"
    ]
    restoration = [
        row for row in scores if row.get("restoration_success") is not None
    ]
    premature = [
        row for row in controllers
        if row.get("premature_stop_prevented") is not None
    ]
    by_stratum: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in controllers:
        by_stratum[str(row["stratum"])].append(row)
    state_components = {
        field: _fraction(
            sum(bool(row["state_component_correct"][field]) for row in controllers),
            len(controllers),
        )
        for field in EVIDENCE_STATE_FIELDS
    }
    metrics = {
        "case_count": len(scores),
        "complete_case_set": complete_case_set,
        "valid_structured_model_calls": _fraction(
            sum(bool(row["structured_valid"]) for row in scores),
            len(scores),
        ),
        "correct_first_actions_overall": _fraction(
            sum(bool(row["action_correct"]) for row in controllers),
            len(controllers),
        ),
        "correct_first_actions_by_stratum": {
            stratum: _fraction(
                sum(bool(row["action_correct"]) for row in stratum_rows),
                len(stratum_rows),
            )
            for stratum, stratum_rows in sorted(by_stratum.items())
        },
        "exact_six_field_state": _fraction(
            sum(bool(row["exact_six_field_state"]) for row in controllers),
            len(controllers),
        ),
        "state_component_accuracy": state_components,
        "blocked_correct_abstention": _fraction(
            sum(bool(row["blocked_abstention_success"]) for row in blocked),
            len(blocked),
        ),
        "restoration_recovery": _fraction(
            sum(bool(row["restoration_success"]) for row in restoration),
            len(restoration),
        ),
        "supported_finalization": _fraction(
            sum(bool(row["supported_finalization_success"]) for row in supported),
            len(supported),
        ),
        "exact_citation_selection": _fraction(
            sum(bool(row["exact_citation_selection"]) for row in supported),
            len(supported),
        ),
        "premature_stop_prevention": _fraction(
            sum(bool(row["premature_stop_prevented"]) for row in premature),
            len(premature),
        ),
        "unsupported_required_claims": sum(
            int(row.get("unsupported_claims", 0)) for row in finalizers
        ),
        "unobserved_citation_selections": sum(
            int(row.get("unobserved_citation_selections", 0))
            for row in finalizers
        ),
        "private_label_exposures": private_exposures,
        "deterministic_answer_substitutions": substitutions,
    }
    threshold_result = apply_thresholds(metrics, artifact["thresholds"])
    return {
        "schema_version": REPORT_SCHEMA,
        "suite_id": SUITE_ID,
        "freeze_label": FREEZE_LABEL,
        "run_id": submission.get("run_id"),
        "model_inference_executed_by_evaluator": False,
        "private_labels_loaded_only_by_evaluator": True,
        "metrics": metrics,
        "thresholds": copy.deepcopy(artifact["thresholds"]),
        "case_scores": scores,
        **threshold_result,
    }


def _write_artifact(path: Path, artifact: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(artifact, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )
    path.write_text(payload, encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-freeze",
        action="store_true",
        help="Deterministically write the prospective NOT_RUN artifact.",
    )
    parser.add_argument(
        "--validate-freeze",
        action="store_true",
        help="Validate the committed artifact and deterministic rebuild.",
    )
    parser.add_argument(
        "--print-public-packets",
        action="store_true",
        help="Print only the prompt-authorized public packet projection.",
    )
    parser.add_argument(
        "--evaluate-submission",
        type=Path,
        help="Evaluate a completed sealed submission; performs no inference.",
    )
    args = parser.parse_args(argv)
    artifact_path = ROOT / ARTIFACT_PATH
    if args.write_freeze:
        artifact = build_frozen_artifact()
        _write_artifact(artifact_path, artifact)
        print(FROZEN_NOT_RUN)
        return 0
    artifact = load_json(artifact_path)
    validate_frozen_artifact(artifact)
    if args.print_public_packets:
        print(
            json.dumps(
                public_packet_projection(artifact),
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
        )
    if args.evaluate_submission is not None:
        submission = load_json(args.evaluate_submission)
        print(
            json.dumps(
                evaluate_submission(artifact, submission),
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
        )
    if args.validate_freeze or (
        not args.print_public_packets and args.evaluate_submission is None
    ):
        print(FROZEN_NOT_RUN)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
