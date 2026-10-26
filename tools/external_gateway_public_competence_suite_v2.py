"""Freeze and audit the v2 public-fictional external-gateway competence suite.

This module deliberately has no gateway invocation path.  It creates two
separate artifacts, validates their boundary, renders governed-runner prompts
for overlap auditing, scores already-recorded runner output, and provides
deterministic public-only adversarial baselines.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import random
import re
import tempfile
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from av_trace_strong_baselines.contracts import canonical_json_bytes
from av_trace_strong_baselines.errors import StrongBaselineError
from av_trace_strong_baselines_v2 import (
    AttemptKind,
    FactorStatus,
    RawFactorAttempt,
    parse_controller_factors,
    parse_finalizer_factors,
)

try:
    from tools import external_gateway_strong_agent as governed_runner
except ModuleNotFoundError:  # Direct ``python tools/...py`` execution.
    import external_gateway_strong_agent as governed_runner

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_PATH = Path(
    "data/rehearsal_plan/"
    "external_gateway_public_competence_suite_v2_public.json"
)
PRIVATE_PATH = Path(
    "data/restricted/"
    "external_gateway_public_competence_suite_v2_private.json"
)

PUBLIC_SCHEMA = (
    "av-trace.external-gateway-public-competence-v2-public/2.0"
)
PRIVATE_SCHEMA = (
    "av-trace.external-gateway-public-competence-v2-private/2.0"
)
SUBMISSION_SCHEMA = (
    "av-trace.external-gateway-public-competence-v2-submission/2.0"
)
REPORT_SCHEMA = "av-trace.external-gateway-public-competence-v2-report/2.0"
LEDGER_SCHEMA = "av-trace.external-gateway-public-competence-v2-ledger/2.0"
SUITE_ID = "external-gateway-public-fictional-technical-v2-20261012"
FROZEN_SEED = 202610120207
FROZEN_DATE = "2026-10-12"
CASE_COUNT = 48

GO_TOKEN = "PUBLIC_FICTIONAL_TECHNICAL_ROW_GO"
NO_GO_TOKEN = "PUBLIC_FICTIONAL_TECHNICAL_ROW_NO_GO"
FREEZE_STATUS = "REPAIR_NOT_AUTHORIZED"

CONTROLLER_FACTORS = ("action_choice", "evidence_state")
FINALIZER_FACTORS = (
    "disposition",
    "answer_text",
    "claim_drafts",
    "citation_selections",
    "diagnosis",
)
PROHIBITED_PUBLIC_KEYS = frozenset(
    {
        "accepted_semantic_forms",
        "answer_key",
        "answer_terms",
        "case_stratum",
        "evaluator",
        "evaluator_label",
        "evaluator_labels",
        "expected_action_index",
        "expected_citations",
        "expected_diagnosis",
        "expected_evidence_state",
        "forbidden_semantic_forms",
        "private_canary",
        "required_claims",
        "required_missing_hop",
        "required_missing_modality",
        "scoring_target",
        "strata",
        "stratum",
        "target",
        "target_action",
        "target_label",
    }
)
PROHIBITED_PUBLIC_TERMS = (
    re.compile(
        r"\b(?:answer|evaluator|scoring)[ _-]?key\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bexpected[ _-]?(?:action|answer|citation|state)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\btarget[ _-]?(?:action|answer|label)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bH2\b", re.IGNORECASE),
    re.compile(r"\bSES(?:es)?\b", re.IGNORECASE),
)
REFERENCE_PATHS = (
    Path("data/rehearsal_plan/granite_adapter_v2_dev_registry.json"),
    Path("data/rehearsal_plan/granite_adapter_v2_holdout_public.json"),
    Path("data/rehearsal_plan/qwen3_adapter_v2_holdout_public.json"),
    Path("data/rehearsal_plan/strong_baseline_competence_suite_v1.json"),
    Path("data/rehearsal_plan/external_gateway_public_competence_suite_v1.json"),
    Path("docs/design/granite_native_adapter_v2.md"),
    Path("docs/design/strong_baseline_adapter_v1.md"),
    Path("docs/design/external_gateway_public_competence_suite_v1.md"),
    Path("docs/design/external_gateway_strong_agent_v1.md"),
    Path("docs/review/granite33_competence_v1_audit.md"),
    Path("docs/review/granite_adapter_v2_development_audit.md"),
    Path("docs/review/granite_adapter_v2_holdout_freeze.md"),
    Path("docs/review/granite_adapter_v2_holdout_evaluation.md"),
    Path("docs/review/qwen3_adapter_v2_holdout_freeze.md"),
    Path("docs/review/qwen3_adapter_v2_holdout_evaluation.md"),
    Path("docs/review/qwen25_omni_direct_competence_v1.md"),
    Path("docs/review/external_gateway_strong_agent_smoke_audit.md"),
    Path("docs/review/external_gateway_runtime_binding_repair.md"),
    Path("orchestration/results/158_strong_baseline_adapter_implementation.txt"),
    Path("orchestration/results/172_granite33_competence_v1.txt"),
    Path("orchestration/results/175_granite_adapter_v2_development.txt"),
    Path("orchestration/results/176_granite_adapter_v2_holdout_freeze.txt"),
    Path("orchestration/results/177_granite_adapter_v2_holdout_evaluation.txt"),
    Path("orchestration/results/182_qwen3_adapter_v2_holdout_freeze.txt"),
    Path("orchestration/results/184_qwen3_adapter_v2_holdout_evaluation.txt"),
    Path("orchestration/results/198_qwen25_omni_direct_competence_v1.txt"),
    Path("orchestration/results/201_external_gateway_strong_agent_smoke.txt"),
    Path("orchestration/results/202_external_gateway_strong_agent_smoke_repair.txt"),
)
REFERENCE_GLOBS = (
    (
        "data/rehearsal_plan/"
        "external_gateway_strong_agent_smoke_run_v1/"
        "*/**/prompts/*.txt"
    ),
)
OVERLAP_THRESHOLDS = {
    "exact_normalized_text_matches_max": 0,
    "exact_object_hash_matches_max": 0,
    "rendered_prompt_hash_matches_max": 0,
    "near_question_token_jaccard_max": 0.72,
    "near_rendered_prompt_token_jaccard_max": 0.92,
}
THRESHOLDS = {
    "case_count": CASE_COUNT,
    "valid_case_projection_min": 0.94,
    "controller_action_accuracy_min": 0.86,
    "controller_exact_state_min": 0.80,
    "finalizer_exact_outcome_min": 0.80,
    "diagnosis_exact_min": 0.84,
    "cross_state_isolation_required": True,
    "unsupported_or_missing_claims_max": 0,
    "contradictory_claims_max": 0,
    "unobserved_citations_max": 0,
    "integrity_failures_max": 0,
}

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class CompetenceSuiteV2Error(RuntimeError):
    """Fail-closed v2 freeze/evaluation error."""


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CompetenceSuiteV2Error(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def _opaque(prefix: str, index: int) -> str:
    digest = hashlib.sha256(
        f"{FROZEN_SEED}:{prefix}:{index}".encode()
    ).hexdigest()[:14]
    return f"{prefix}_{digest}"


def _normalize_text(value: str) -> str:
    return " ".join(_TOKEN_RE.findall(value.casefold()))


def _tokens(value: str) -> frozenset[str]:
    return frozenset(_TOKEN_RE.findall(value.casefold()))


def _jaccard(left: str, right: str) -> float:
    a = _tokens(left)
    b = _tokens(right)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _walk(value: Any, path: str = "$") -> Iterable[tuple[str, str, Any]]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            yield child_path, str(key), child
            yield from _walk(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, f"{path}[{index}]")


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


def _search_action(modality: str, query: str) -> dict[str, Any]:
    tool = {
        "vision": "search_visual",
        "speech": "search_speech",
        "ambient": "search_ambient_audio",
    }[modality]
    arguments: dict[str, Any] = {
        "query": query,
        "top_k": 5,
        "time_range": {"start_s": 0.0, "end_s": 72.0},
        "exclude_result_ids": [],
    }
    if modality == "speech":
        arguments["speaker_hint"] = None
    return {"tool": tool, "arguments": arguments}


def _status_action(modality: str) -> dict[str, Any]:
    return {
        "tool": "get_channel_status",
        "arguments": {
            "channels": ["visual" if modality == "vision" else modality]
        },
    }


def _finalize_action() -> dict[str, Any]:
    return {"tool": "finalize", "arguments": {}}


def _state(
    *,
    covered: Sequence[str] = (),
    modality: str | None = None,
    hop: str | None = None,
    cause: str,
    intent: str,
    sufficient: float,
) -> dict[str, Any]:
    return {
        "p_sufficient": sufficient,
        "covered_claim_handles": list(covered),
        "missing_modalities": [] if modality is None else [modality],
        "missing_hops": [] if hop is None else [hop],
        "missingness_cause": cause,
        "recovery_intent": intent,
    }


def _diagnosis(
    *,
    modality: str | None,
    hop: str | None,
    cause: str,
    recovery: bool,
) -> dict[str, Any]:
    causes = {
        "source_evidence_absent": 0.0,
        "evidence_in_source_but_inaccessible": 0.0,
        "evidence_accessible_but_not_found": 0.0,
        "not_missing": 0.0,
        "uncertain": 0.0,
    }
    causes[cause] = 1.0
    return {
        "modality_probabilities": {
            name: 1.0 if name == modality else 0.0
            for name in ("vision", "speech", "ambient")
        },
        "hop_types": [] if hop is None else [hop],
        "cause_probabilities": causes,
        "recovery_route_declared": recovery,
    }


def _packet(
    *,
    case_id: str,
    case_type: str,
    public_input: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": governed_runner.PACKET_SCHEMA,
        "case_id": case_id,
        "case_type": case_type,
        "public_fictional": True,
        "source_free": True,
        "development_only": True,
        "prospective_unseen_at_freeze": True,
        "packet_notice": (
            "Wholly fictional closed-world text only. No external source, "
            "media, scientific record, hidden label, or real-world fact is "
            "part of this packet."
        ),
        "public_input": copy.deepcopy(dict(public_input)),
    }


def _shuffled_menu(
    rng: random.Random,
    actions: Sequence[dict[str, Any]],
    selected: dict[str, Any],
) -> tuple[list[dict[str, Any]], int]:
    rows = copy.deepcopy(list(actions))
    rng.shuffle(rows)
    matches = [index for index, row in enumerate(rows) if row == selected]
    if len(matches) != 1:
        raise AssertionError("selected action must occur exactly once")
    return rows, matches[0]


def _controller_cases(
    rng: random.Random,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    packets: list[dict[str, Any]] = []
    labels: dict[str, Any] = {}
    modalities = ("vision", "speech", "ambient")
    hop_for = {
        "vision": "entity_identity",
        "speech": "speech_content",
        "ambient": "ambient_event",
    }
    intent_for = {
        "vision": "search_vision",
        "speech": "search_speech",
        "ambient": "search_ambient",
    }
    entities = (
        "brindle astrolabe",
        "cobalt reliquary",
        "dappled orrery",
        "ember folio",
        "fallow armature",
        "gilded waybox",
        "hushed tessera",
        "indigo capstan",
        "jasper thimble",
        "kelpwood transit",
        "lunar spindle",
        "mauve turnstile",
        "nacre compass",
        "opal ratchet",
        "pewter arcade",
        "quartz wicket",
        "russet beacon",
        "sable cabinet",
        "tawny prism",
        "umber cradle",
        "verdant dial",
        "waxen lantern",
        "yellowglass seal",
        "zinnia latch",
    )
    strata = (
        "route",
        "blocked",
        "restored",
        "ready",
        "continue",
        "absent",
    )
    for index, entity in enumerate(entities):
        stratum = strata[index // 4]
        modality = modalities[index % len(modalities)]
        hop = hop_for[modality]
        case_id = _opaque("c", index)
        handle = _opaque("h", index)
        question = (
            f"For the fictional {entity}, determine the registered "
            f"{('mark', 'utterance', 'sound')[index % 3]}."
        )
        observations: list[dict[str, Any]] = []
        history: list[dict[str, Any]] = []
        if stratum == "route":
            selected = _search_action(
                modality, f"{entity} registered record {index + 11}"
            )
            actions = [
                selected,
                _search_action(
                    modalities[(index + 1) % 3],
                    f"adjacent ledger {index + 31}",
                ),
                _finalize_action(),
            ]
            expected_state = _state(
                modality=modality,
                hop=hop,
                cause="evidence_accessible_but_not_found",
                intent=intent_for[modality],
                sufficient=0.0,
            )
        elif stratum == "blocked":
            history = [
                {
                    "event_type": "route_result",
                    "route": modality,
                    "status": "channel_unavailable",
                    "content_observed": False,
                }
            ]
            selected = _status_action(modality)
            actions = [
                selected,
                _search_action(modality, f"{entity} retry record"),
                _finalize_action(),
            ]
            expected_state = _state(
                modality=modality,
                hop=hop,
                cause="evidence_in_source_but_inaccessible",
                intent="check_channel_status",
                sufficient=0.0,
            )
        elif stratum == "restored":
            history = [
                {
                    "event_type": "route_status",
                    "route": modality,
                    "status": "restored",
                    "content_observed": False,
                }
            ]
            selected = _search_action(
                modality, f"{entity} restored record {index + 19}"
            )
            actions = [
                selected,
                _status_action(modality),
                _finalize_action(),
            ]
            expected_state = _state(
                modality=modality,
                hop=hop,
                cause="evidence_in_source_but_inaccessible",
                intent="retry_restored_route",
                sufficient=0.0,
            )
        elif stratum == "ready":
            observation_id = _opaque("o", index)
            observations = [
                _observation(
                    observation_id,
                    modality,
                    f"The registered record for the fictional {entity} is "
                    f"{('silver lozenge', 'quiet marigold', 'four reed taps')[index % 3]}.",
                    index + 8,
                )
            ]
            selected = _finalize_action()
            actions = [
                selected,
                _search_action(modality, f"{entity} duplicate record"),
            ]
            expected_state = _state(
                covered=[handle],
                cause="not_missing",
                intent="finalize_answer",
                sufficient=1.0,
            )
        elif stratum == "continue":
            selected = _search_action(
                modality, f"{entity} remaining record {index + 43}"
            )
            actions = [selected, _finalize_action()]
            expected_state = _state(
                modality=modality,
                hop=hop,
                cause="evidence_accessible_but_not_found",
                intent=intent_for[modality],
                sufficient=0.0,
            )
        else:
            history = [
                {
                    "event_type": "route_status",
                    "route": modality,
                    "status": "not_provided",
                    "content_observed": False,
                }
            ]
            selected = _finalize_action()
            actions = [selected]
            expected_state = _state(
                modality=modality,
                hop=hop,
                cause="source_evidence_absent",
                intent="finalize_abstain",
                sufficient=0.0,
            )
        menu, expected_index = _shuffled_menu(rng, actions, selected)
        packet = _packet(
            case_id=case_id,
            case_type="controller",
            public_input={
                "task": "choose_next_action",
                "policy": "evidence_sufficiency",
                "question": question,
                "public_claim_slots": [
                    _claim(handle, "Registered fictional record.")
                ],
                "observed_evidence": observations,
                "known_pointers": [],
                "recent_public_history": history,
                "remaining_budget": {
                    "actions_remaining": 2 + index % 5,
                    "cost_remaining": float(3 + index % 6),
                },
                "action_menu": menu,
            },
        )
        packets.append(packet)
        labels[case_id] = {
            "case_stratum": f"controller_{stratum}",
            "expected_action_index": expected_index,
            "expected_evidence_state": expected_state,
            "required_claims": [],
            "expected_diagnosis": None,
        }
    return packets, labels


def _semantic_forms(text: str) -> list[str]:
    normalized = _normalize_text(text)
    return sorted(
        {
            normalized,
            _normalize_text(f"The registered fictional value is {text}."),
        }
    )


def _finalizer_cases(
    rng: random.Random,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    packets: list[dict[str, Any]] = []
    labels: dict[str, Any] = {}
    modalities = ("vision", "speech", "ambient")
    hop_for = {
        "vision": "entity_identity",
        "speech": "speech_content",
        "ambient": "ambient_event",
    }
    values = (
        "amber pennant",
        "birch comet",
        "cerulean knot",
        "dusk orchard",
        "elmward phrase",
        "frosted cadence",
        "garnet arch",
        "heather signal",
        "ivory ripple",
        "juniper token",
        "khaki spiral",
        "lilac refrain",
        "moss triangle",
        "navy whisper",
        "ochre chime",
        "pearl bracket",
        "quince marker",
        "rosewood answer",
        "slate rustle",
        "teal sigil",
        "umber response",
        "violet knock",
        "willow glyph",
        "xanthic murmur",
    )
    strata = (
        "supported_single",
        "supported_dual",
        "supported_distractor",
        "absent",
        "inaccessible",
        "not_found",
    )
    for local_index, value in enumerate(values):
        index = local_index + 24
        stratum = strata[local_index // 4]
        modality = modalities[local_index % 3]
        hop = hop_for[modality]
        case_id = _opaque("f", local_index)
        first_handle = _opaque("h", index)
        second_handle = _opaque("h", index + 100)
        first_observation = _opaque("o", index)
        second_observation = _opaque("o", index + 100)
        claims = [_claim(first_handle, "Registered fictional attribute.")]
        observations: list[dict[str, Any]] = []
        required: dict[str, Any] = {}
        if stratum.startswith("supported"):
            observations.append(
                _observation(
                    first_observation,
                    modality,
                    f"The fictional archive records {value}.",
                    local_index + 20,
                )
            )
            required[first_handle] = {
                "accepted_semantic_forms": _semantic_forms(value),
                "forbidden_semantic_forms": [
                    _normalize_text(f"not {value}"),
                    _normalize_text(f"{value} is false"),
                ],
                "expected_citations": [first_observation],
            }
            if stratum == "supported_dual":
                second_value = f"{value} beside copper fern"
                claims.append(
                    _claim(second_handle, "Second registered attribute.")
                )
                observations.append(
                    _observation(
                        second_observation,
                        modalities[(local_index + 1) % 3],
                        f"A separate fictional register records {second_value}.",
                        local_index + 41,
                    )
                )
                required[second_handle] = {
                    "accepted_semantic_forms": _semantic_forms(second_value),
                    "forbidden_semantic_forms": [
                        _normalize_text(f"not {second_value}")
                    ],
                    "expected_citations": [second_observation],
                }
            if stratum == "supported_distractor":
                observations.append(
                    _observation(
                        second_observation,
                        modalities[(local_index + 2) % 3],
                        (
                            "An unrelated fictional drawer records "
                            f"decoy {local_index + 70}."
                        ),
                        local_index + 54,
                    )
                )
            disposition = {
                "p_sufficient": 1.0,
                "verdict": "sufficient",
                "answer_mode": "answer",
                "termination_reason": "sufficient_evidence",
            }
            diagnosis = _diagnosis(
                modality=None,
                hop=None,
                cause="not_missing",
                recovery=False,
            )
        else:
            cause = {
                "absent": "source_evidence_absent",
                "inaccessible": "evidence_in_source_but_inaccessible",
                "not_found": "evidence_accessible_but_not_found",
            }[stratum]
            if stratum == "inaccessible":
                observations.append(
                    _observation(
                        second_observation,
                        modalities[(local_index + 1) % 3],
                        "The fictional route status contains no requested value.",
                        local_index + 62,
                    )
                )
            disposition = {
                "p_sufficient": 0.0,
                "verdict": "insufficient",
                "answer_mode": "abstain",
                "termination_reason": "no_recovery_route",
            }
            diagnosis = _diagnosis(
                modality=modality,
                hop=hop,
                cause=cause,
                recovery=False,
            )
        packet = _packet(
            case_id=case_id,
            case_type="finalizer",
            public_input={
                "task": "grounded_finalization",
                "condition": "closed_world_record",
                "question": (
                    f"What registered attribute belongs to fictional entry "
                    f"{_opaque('entry', local_index)}?"
                ),
                "public_claim_slots": claims,
                "observed_evidence": observations,
            },
        )
        packets.append(packet)
        labels[case_id] = {
            "case_stratum": f"finalizer_{stratum}",
            "expected_disposition": disposition,
            "required_claims": required,
            "expected_diagnosis": diagnosis,
        }
    rng.shuffle(packets)
    return packets, labels


def _parser_failure_fixtures() -> list[dict[str, Any]]:
    return [
        {
            "fixture_id": _opaque("fx", 0),
            "factor": "action_choice",
            "raw_output": '{"function_name":"select_action_00","arguments":[]}',
            "expected": "INVALID_OUTPUT",
        },
        {
            "fixture_id": _opaque("fx", 1),
            "factor": "diagnosis",
            "raw_output": '{"modality_probabilities":{"vision":1}}',
            "expected": "INVALID_OUTPUT",
        },
        {
            "fixture_id": _opaque("fx", 2),
            "factor": "claim_drafts",
            "raw_output": '{"claims":"forged"}',
            "expected": "INVALID_OUTPUT",
        },
        {
            "fixture_id": _opaque("fx", 3),
            "factor": "citation_selections",
            "raw_output": "not-json",
            "expected": "INVALID_OUTPUT",
        },
    ]


def _reference_files(root: Path) -> list[Path]:
    paths = [root / item for item in REFERENCE_PATHS]
    for pattern in REFERENCE_GLOBS:
        paths.extend(sorted(root.glob(pattern)))
    unique = sorted({path.resolve() for path in paths if path.is_file()})
    return unique


def _all_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for child in value.values():
            yield from _all_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _all_strings(child)


def _all_object_hashes(value: Any) -> Iterable[str]:
    if isinstance(value, (Mapping, list)):
        yield sha256_json(value)
    if isinstance(value, Mapping):
        for child in value.values():
            yield from _all_object_hashes(child)
    elif isinstance(value, list):
        for child in value:
            yield from _all_object_hashes(child)


def render_case_prompts(packet: Mapping[str, Any]) -> dict[str, str]:
    factors = (
        CONTROLLER_FACTORS
        if packet["case_type"] == "controller"
        else FINALIZER_FACTORS
    )
    return {
        factor: governed_runner.factor_prompt(packet, factor)
        for factor in factors
    }


def compute_overlap_audit(
    packets: Sequence[Mapping[str, Any]],
    *,
    root: Path = ROOT,
) -> dict[str, Any]:
    reference_files = _reference_files(root)
    reference_strings: list[str] = []
    reference_hashes: set[str] = set()
    reference_prompt_hashes: set[str] = set()
    file_hashes: dict[str, str] = {}
    for path in reference_files:
        relative = str(path.relative_to(root))
        file_hashes[relative] = sha256_file(path)
        raw = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix == ".json":
            try:
                value = json.loads(raw)
            except json.JSONDecodeError:
                value = raw
            reference_strings.extend(_all_strings(value))
            reference_hashes.update(_all_object_hashes(value))
        else:
            reference_strings.append(raw)
            reference_prompt_hashes.add(sha256_bytes(raw.encode()))
    normalized_references = {
        _normalize_text(item) for item in reference_strings if item.strip()
    }
    candidate_questions = [
        str(packet["public_input"]["question"]) for packet in packets
    ]
    candidate_prompts = [
        prompt
        for packet in packets
        for prompt in render_case_prompts(packet).values()
    ]
    exact_text = sorted(
        {
            question
            for question in candidate_questions
            if _normalize_text(question) in normalized_references
        }
    )
    object_matches = sorted(
        sha256_json(packet)
        for packet in packets
        if sha256_json(packet) in reference_hashes
    )
    prompt_matches = sorted(
        sha256_bytes(prompt.encode())
        for prompt in candidate_prompts
        if sha256_bytes(prompt.encode()) in reference_prompt_hashes
    )
    max_question = max(
        (
            _jaccard(question, reference)
            for question in candidate_questions
            for reference in reference_strings
            if reference.strip()
        ),
        default=0.0,
    )
    max_prompt = max(
        (
            _jaccard(prompt, reference)
            for prompt in candidate_prompts
            for reference in reference_strings
            if len(_tokens(reference)) >= 20
        ),
        default=0.0,
    )
    checks = {
        "exact_normalized_text": (
            len(exact_text)
            <= OVERLAP_THRESHOLDS["exact_normalized_text_matches_max"]
        ),
        "exact_object_hash": (
            len(object_matches)
            <= OVERLAP_THRESHOLDS["exact_object_hash_matches_max"]
        ),
        "rendered_prompt_hash": (
            len(prompt_matches)
            <= OVERLAP_THRESHOLDS["rendered_prompt_hash_matches_max"]
        ),
        "near_question": (
            max_question
            <= OVERLAP_THRESHOLDS["near_question_token_jaccard_max"]
        ),
        "near_rendered_prompt": (
            max_prompt
            <= OVERLAP_THRESHOLDS[
                "near_rendered_prompt_token_jaccard_max"
            ]
        ),
    }
    return {
        "schema_version": (
            "av-trace.external-gateway-public-competence-v2-overlap/2.0"
        ),
        "prospective_thresholds": copy.deepcopy(OVERLAP_THRESHOLDS),
        "reference_file_hashes": file_hashes,
        "reference_file_count": len(reference_files),
        "candidate_rendered_prompt_count": len(candidate_prompts),
        "exact_normalized_text_matches": exact_text,
        "exact_object_hash_matches": object_matches,
        "rendered_prompt_hash_matches": prompt_matches,
        "max_question_token_jaccard": round(max_question, 6),
        "max_rendered_prompt_token_jaccard": round(max_prompt, 6),
        "checks": checks,
        "status": "PASS" if all(checks.values()) else "FAIL",
    }


def _case_balance(labels: Mapping[str, Mapping[str, Any]]) -> dict[str, int]:
    return dict(
        sorted(
            Counter(str(label["case_stratum"]) for label in labels.values()).items()
        )
    )


def build_frozen_artifacts(
    *,
    root: Path = ROOT,
) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = random.Random(FROZEN_SEED)
    controller_packets, controller_labels = _controller_cases(rng)
    finalizer_packets, finalizer_labels = _finalizer_cases(rng)
    packets = controller_packets + finalizer_packets
    rng.shuffle(packets)
    labels = {**controller_labels, **finalizer_labels}
    if len(packets) != CASE_COUNT or len(labels) != CASE_COUNT:
        raise AssertionError("v2 case count drift")
    overlap = compute_overlap_audit(packets, root=root)
    public_core = {
        "schema_version": PUBLIC_SCHEMA,
        "suite_id": SUITE_ID,
        "frozen_date": FROZEN_DATE,
        "frozen_seed": FROZEN_SEED,
        "status": FREEZE_STATUS,
        "execution_authorized": False,
        "gateway_or_model_calls": 0,
        "scientific_competence_supported": False,
        "h2_supported": False,
        "scope": (
            "Public-fictional technical controller/finalizer sensitivity only."
        ),
        "runner_contract": {
            "runner_schema_version": governed_runner.RUNNER_SCHEMA,
            "attempt_schema_version": governed_runner.ATTEMPT_SCHEMA,
            "packet_schema_version": governed_runner.PACKET_SCHEMA,
            "factor_order": {
                "controller": list(CONTROLLER_FACTORS),
                "finalizer": list(FINALIZER_FACTORS),
            },
            "raw_prompt_hash_required": True,
            "raw_output_hash_required": True,
            "provider_model_runtime_identity_required": True,
            "model_substitution_forbidden": True,
            "semantic_substitution_forbidden": True,
            "schema_only_retry_maximum_per_factor": 1,
        },
        "one_shot_ledger_template": {
            "schema_version": LEDGER_SCHEMA,
            "state": "NOT_RUN",
            "maximum_full_suite_runs": 1,
            "full_suite_runs": 0,
            "partial_runs": 0,
            "atomic_transition_required": True,
            "evaluation_receipt_must_be_created_exclusively": True,
        },
        "private_boundary": {
            "private_artifact_path": str(PRIVATE_PATH),
            "required_mode": "0600",
            "cryptographic_sealing_available": False,
            "authorization_state": FREEZE_STATUS,
        },
        "packets": packets,
        "parser_failure_fixtures": _parser_failure_fixtures(),
        "overlap_audit": overlap,
        "thresholds": copy.deepcopy(THRESHOLDS),
    }
    public_hash = sha256_json(public_core)
    public = {
        **public_core,
        "freeze_manifest": {
            "public_payload_sha256": public_hash,
            "packet_hashes": {
                str(packet["case_id"]): sha256_json(packet)
                for packet in packets
            },
            "reference_file_hashes": overlap["reference_file_hashes"],
        },
    }
    private_core = {
        "schema_version": PRIVATE_SCHEMA,
        "suite_id": SUITE_ID,
        "frozen_date": FROZEN_DATE,
        "status": FREEZE_STATUS,
        "public_payload_sha256": public_hash,
        "private_canary": _opaque("private_canary", 0),
        "labels": labels,
        "case_balance": _case_balance(labels),
        "private_access": {
            "path": str(PRIVATE_PATH),
            "required_mode": "0600",
            "directory_required_mode": "0700_or_more_restrictive",
            "authorized_roles": [
                "independent_evaluator",
                "suite_custodian",
            ],
            "model_or_runner_access": False,
            "cryptographic_sealing_available": False,
            "execution_authorized": False,
        },
    }
    private = {
        **private_core,
        "freeze_manifest": {
            "private_payload_sha256": sha256_json(private_core),
            "label_hashes": {
                case_id: sha256_json(label)
                for case_id, label in labels.items()
            },
        },
    }
    return public, private


def validate_public_artifact(
    public: Mapping[str, Any],
    *,
    root: Path = ROOT,
) -> None:
    if public.get("schema_version") != PUBLIC_SCHEMA:
        raise CompetenceSuiteV2Error("PUBLIC_SCHEMA_MISMATCH")
    if public.get("suite_id") != SUITE_ID:
        raise CompetenceSuiteV2Error("PUBLIC_SUITE_ID_MISMATCH")
    if public.get("execution_authorized") is not False:
        raise CompetenceSuiteV2Error("EXECUTION_MUST_NOT_BE_AUTHORIZED")
    if public.get("status") != FREEZE_STATUS:
        raise CompetenceSuiteV2Error("FREEZE_STATUS_MISMATCH")
    packets = public.get("packets")
    if not isinstance(packets, list) or len(packets) != CASE_COUNT:
        raise CompetenceSuiteV2Error("PUBLIC_CASE_COUNT_MISMATCH")
    case_ids = [str(packet.get("case_id")) for packet in packets]
    if len(set(case_ids)) != CASE_COUNT:
        raise CompetenceSuiteV2Error("PUBLIC_CASE_IDS_NOT_UNIQUE")
    serialized = json.dumps(public, sort_keys=True, ensure_ascii=False)
    for pattern in PROHIBITED_PUBLIC_TERMS:
        if pattern.search(serialized):
            raise CompetenceSuiteV2Error("PUBLIC_TARGET_SIGNALING_TERM")
    for path, key, _ in _walk(public):
        if key.casefold() in PROHIBITED_PUBLIC_KEYS:
            raise CompetenceSuiteV2Error(f"PUBLIC_PRIVATE_KEY_LEAK:{path}")
    for packet in packets:
        try:
            governed_runner.validate_public_packet(packet)
        except governed_runner.ExternalGatewayError as exc:
            raise CompetenceSuiteV2Error(
                f"RUNNER_PACKET_INCOMPATIBLE:{exc}"
            ) from exc
    core = {key: copy.deepcopy(value) for key, value in public.items()}
    manifest = core.pop("freeze_manifest", None)
    if not isinstance(manifest, Mapping):
        raise CompetenceSuiteV2Error("PUBLIC_MANIFEST_MISSING")
    if manifest.get("public_payload_sha256") != sha256_json(core):
        raise CompetenceSuiteV2Error("PUBLIC_PAYLOAD_HASH_MISMATCH")
    expected_packets = {
        str(packet["case_id"]): sha256_json(packet) for packet in packets
    }
    if manifest.get("packet_hashes") != expected_packets:
        raise CompetenceSuiteV2Error("PUBLIC_PACKET_HASH_MISMATCH")
    overlap = compute_overlap_audit(packets, root=root)
    if overlap["status"] != "PASS" or public.get("overlap_audit") != overlap:
        raise CompetenceSuiteV2Error("PUBLIC_OVERLAP_AUDIT_FAILED")


def validate_private_artifact(
    public: Mapping[str, Any],
    private: Mapping[str, Any],
    *,
    private_path: Path | None = None,
) -> None:
    if private.get("schema_version") != PRIVATE_SCHEMA:
        raise CompetenceSuiteV2Error("PRIVATE_SCHEMA_MISMATCH")
    if private.get("suite_id") != SUITE_ID:
        raise CompetenceSuiteV2Error("PRIVATE_SUITE_ID_MISMATCH")
    public_core = {key: copy.deepcopy(value) for key, value in public.items()}
    public_core.pop("freeze_manifest", None)
    if private.get("public_payload_sha256") != sha256_json(public_core):
        raise CompetenceSuiteV2Error("PRIVATE_PUBLIC_BINDING_MISMATCH")
    labels = private.get("labels")
    if not isinstance(labels, Mapping):
        raise CompetenceSuiteV2Error("PRIVATE_LABELS_INVALID")
    case_ids = {str(packet["case_id"]) for packet in public["packets"]}
    if set(labels) != case_ids:
        raise CompetenceSuiteV2Error("PRIVATE_LABEL_CASE_SET_MISMATCH")
    if private.get("case_balance") != _case_balance(labels):
        raise CompetenceSuiteV2Error("PRIVATE_CASE_BALANCE_MISMATCH")
    projection = json.dumps(public, sort_keys=True)
    if str(private.get("private_canary")) in projection:
        raise CompetenceSuiteV2Error("PRIVATE_CANARY_LEAK")
    core = {key: copy.deepcopy(value) for key, value in private.items()}
    manifest = core.pop("freeze_manifest", None)
    if not isinstance(manifest, Mapping):
        raise CompetenceSuiteV2Error("PRIVATE_MANIFEST_MISSING")
    if manifest.get("private_payload_sha256") != sha256_json(core):
        raise CompetenceSuiteV2Error("PRIVATE_PAYLOAD_HASH_MISMATCH")
    expected_label_hashes = {
        str(case_id): sha256_json(label) for case_id, label in labels.items()
    }
    if manifest.get("label_hashes") != expected_label_hashes:
        raise CompetenceSuiteV2Error("PRIVATE_LABEL_HASH_MISMATCH")
    if (
        private_path is not None
        and private_path.exists()
        and private_path.stat().st_mode & 0o077
    ):
        raise CompetenceSuiteV2Error("PRIVATE_FILE_PERMISSIONS_TOO_OPEN")


def validate_frozen_pair(
    public: Mapping[str, Any],
    private: Mapping[str, Any],
    *,
    root: Path = ROOT,
    private_path: Path | None = None,
) -> None:
    validate_public_artifact(public, root=root)
    validate_private_artifact(public, private, private_path=private_path)
    rebuilt_public, rebuilt_private = build_frozen_artifacts(root=root)
    if public != rebuilt_public:
        raise CompetenceSuiteV2Error("PUBLIC_FREEZE_DRIFT")
    if private != rebuilt_private:
        raise CompetenceSuiteV2Error("PRIVATE_FREEZE_DRIFT")


def _attempts(
    records: Any,
    *,
    packet: Mapping[str, Any],
    factor_name: str,
    binding: Mapping[str, Any],
) -> tuple[RawFactorAttempt, ...]:
    if not isinstance(records, list) or not 1 <= len(records) <= 2:
        raise CompetenceSuiteV2Error("ATTEMPT_COUNT_INVALID")
    attempts: list[RawFactorAttempt] = []
    expected_prompt = render_case_prompts(packet)[factor_name]
    expected_prompt_hash = sha256_bytes(expected_prompt.encode())
    for index, record in enumerate(records, 1):
        if not isinstance(record, Mapping):
            raise CompetenceSuiteV2Error("ATTEMPT_RECORD_INVALID")
        if record.get("schema_version") != governed_runner.ATTEMPT_SCHEMA:
            raise CompetenceSuiteV2Error("ATTEMPT_SCHEMA_MISMATCH")
        if record.get("case_id") != packet["case_id"]:
            raise CompetenceSuiteV2Error("ATTEMPT_CASE_ID_MISMATCH")
        if record.get("case_type") != packet["case_type"]:
            raise CompetenceSuiteV2Error("ATTEMPT_CASE_TYPE_MISMATCH")
        if record.get("factor_name") != factor_name:
            raise CompetenceSuiteV2Error("ATTEMPT_FACTOR_MISMATCH")
        if record.get("attempt_id") != (
            f"{packet['case_id']}::{factor_name}::{index}"
        ):
            raise CompetenceSuiteV2Error("ATTEMPT_ID_MISMATCH")
        if record.get("attempt_index") != index:
            raise CompetenceSuiteV2Error("ATTEMPT_INDEX_MISMATCH")
        if record.get("attempt_kind") != (
            AttemptKind.INITIAL.value
            if index == 1
            else AttemptKind.SCHEMA_ONLY_RETRY.value
        ):
            raise CompetenceSuiteV2Error("ATTEMPT_KIND_MISMATCH")
        raw = record.get("raw_output")
        if not isinstance(raw, str):
            raise CompetenceSuiteV2Error("RAW_OUTPUT_REQUIRED")
        if record.get("raw_output_sha256") != sha256_bytes(raw.encode()):
            raise CompetenceSuiteV2Error("RAW_OUTPUT_HASH_MISMATCH")
        if record.get("prompt_sha256") != expected_prompt_hash:
            raise CompetenceSuiteV2Error("RAW_PROMPT_HASH_MISMATCH")
        if record.get("prompt_bytes") != len(expected_prompt.encode()):
            raise CompetenceSuiteV2Error("RAW_PROMPT_LENGTH_MISMATCH")
        if record.get("model_slug") != binding["model_slug"]:
            raise CompetenceSuiteV2Error("ATTEMPT_MODEL_SUBSTITUTION")
        for key in ("catalog_record_sha256", "catalog_file_sha256"):
            if record.get(key) != binding[key]:
                raise CompetenceSuiteV2Error(
                    f"ATTEMPT_PROVENANCE_MISMATCH:{key}"
                )
        runtime = record.get("runtime")
        if not isinstance(runtime, Mapping):
            raise CompetenceSuiteV2Error("ATTEMPT_RUNTIME_MISSING")
        for key in (
            "tcodex_version",
            "tcodex_commit",
            "upstream_codex_version",
            "tcodex_wrapper_sha256",
            "upstream_codex_binary_sha256",
        ):
            if runtime.get(key) != binding[key]:
                raise CompetenceSuiteV2Error(
                    f"ATTEMPT_RUNTIME_MISMATCH:{key}"
                )
        if record.get("gateway_success") is not True:
            raise CompetenceSuiteV2Error("ATTEMPT_GATEWAY_SUCCESS_REQUIRED")
        if record.get("model_output_accepted") is not True:
            raise CompetenceSuiteV2Error("ATTEMPT_MODEL_OUTPUT_NOT_ACCEPTED")
        if record.get("transport_failure") is not False:
            raise CompetenceSuiteV2Error("ATTEMPT_TRANSPORT_FAILURE")
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


def _required_factors(packet: Mapping[str, Any]) -> tuple[str, ...]:
    return (
        CONTROLLER_FACTORS
        if packet["case_type"] == "controller"
        else FINALIZER_FACTORS
    )


def _validate_runner_submission(
    public: Mapping[str, Any],
    submission: Mapping[str, Any],
) -> tuple[
    dict[str, Mapping[str, Any]],
    dict[str, dict[str, list[Mapping[str, Any]]]],
    Mapping[str, Any],
]:
    if submission.get("schema_version") != SUBMISSION_SCHEMA:
        raise CompetenceSuiteV2Error("SUBMISSION_SCHEMA_MISMATCH")
    if submission.get("suite_id") != SUITE_ID:
        raise CompetenceSuiteV2Error("SUBMISSION_SUITE_ID_MISMATCH")
    public_core = {key: copy.deepcopy(value) for key, value in public.items()}
    public_core.pop("freeze_manifest", None)
    if submission.get("public_payload_sha256") != sha256_json(public_core):
        raise CompetenceSuiteV2Error("SUBMISSION_PUBLIC_HASH_MISMATCH")
    report = submission.get("runner_report")
    if not isinstance(report, Mapping):
        raise CompetenceSuiteV2Error("RUNNER_REPORT_REQUIRED")
    if report.get("schema_version") != governed_runner.RUNNER_SCHEMA:
        raise CompetenceSuiteV2Error("RUNNER_SCHEMA_MISMATCH")
    binding = report.get("model_binding")
    required_binding = {
        "model_slug",
        "catalog_record_sha256",
        "catalog_file_sha256",
        "tcodex_version",
        "tcodex_commit",
        "upstream_codex_version",
        "tcodex_wrapper_sha256",
        "upstream_codex_binary_sha256",
        "wrapper_model_provider",
        "wrapper_provider_name",
        "wrapper_wire_api",
    }
    if not isinstance(binding, Mapping) or any(
        not binding.get(key) for key in required_binding
    ):
        raise CompetenceSuiteV2Error("MODEL_PROVIDER_RUNTIME_IDENTITY_MISSING")
    execution = report.get("execution")
    if not isinstance(execution, Mapping):
        raise CompetenceSuiteV2Error("RUNNER_EXECUTION_BLOCK_MISSING")
    required_execution = {
        "semantic_retries": 0,
        "semantic_repair": False,
        "semantic_substitution": False,
        "model_fallback_or_substitution": False,
        "raw_output_preserved": True,
        "schema_only_retry_maximum_per_factor": 1,
    }
    for key, expected in required_execution.items():
        if execution.get(key) != expected:
            raise CompetenceSuiteV2Error(f"RUNNER_NO_SUBSTITUTION_MISMATCH:{key}")
    report_cases = report.get("cases")
    if not isinstance(report_cases, list):
        raise CompetenceSuiteV2Error("RUNNER_CASES_INVALID")
    expected_ids = {str(packet["case_id"]) for packet in public["packets"]}
    rows: dict[str, Mapping[str, Any]] = {}
    for row in report_cases:
        if not isinstance(row, Mapping):
            raise CompetenceSuiteV2Error("RUNNER_CASE_ROW_INVALID")
        case_id = str(row.get("case_id"))
        if case_id in rows:
            raise CompetenceSuiteV2Error("RUNNER_CASE_DUPLICATE")
        rows[case_id] = row
    if set(rows) != expected_ids or report.get("case_count") != CASE_COUNT:
        raise CompetenceSuiteV2Error("RUNNER_CASE_SET_MISMATCH")
    raw_attempts = submission.get("raw_attempts")
    if not isinstance(raw_attempts, list):
        raise CompetenceSuiteV2Error("RAW_ATTEMPTS_REQUIRED")
    indexed: dict[str, dict[str, list[Mapping[str, Any]]]] = {
        case_id: {} for case_id in expected_ids
    }
    for record in raw_attempts:
        if not isinstance(record, Mapping):
            raise CompetenceSuiteV2Error("RAW_ATTEMPT_RECORD_INVALID")
        case_id = str(record.get("case_id"))
        factor_name = str(record.get("factor_name"))
        if case_id not in indexed:
            raise CompetenceSuiteV2Error("RAW_ATTEMPT_UNKNOWN_CASE")
        indexed[case_id].setdefault(factor_name, []).append(record)
    packet_by_id = {
        str(packet["case_id"]): packet for packet in public["packets"]
    }
    for case_id, factor_rows in indexed.items():
        packet = packet_by_id[case_id]
        required = set(_required_factors(packet))
        if set(factor_rows) != required:
            raise CompetenceSuiteV2Error("RAW_ATTEMPT_FACTOR_SET_MISMATCH")
        for factor_name, records in factor_rows.items():
            records.sort(key=lambda item: int(item.get("attempt_index", -1)))
            _attempts(
                records,
                packet=packet,
                factor_name=factor_name,
                binding=binding,
            )
    return rows, indexed, binding


def _semantic_claim_score(
    text: str,
    rule: Mapping[str, Any],
) -> tuple[bool, bool]:
    normalized = _normalize_text(text)
    accepted = normalized in set(rule["accepted_semantic_forms"])
    forbidden = any(
        form and form in normalized
        for form in rule["forbidden_semantic_forms"]
    )
    return accepted and not forbidden, forbidden


def _score_controller(
    packet: Mapping[str, Any],
    label: Mapping[str, Any],
    row: Mapping[str, Any],
    factor_records: Mapping[str, Sequence[Mapping[str, Any]]],
    binding: Mapping[str, Any],
) -> dict[str, Any]:
    factor_summary = row.get("factors")
    if not isinstance(factor_summary, Mapping) or set(factor_summary) != set(
        CONTROLLER_FACTORS
    ):
        return {
            "projection_valid": False,
            "action_correct": False,
            "state_exact": False,
            "missing_claims": 0,
            "contradictory_claims": 0,
            "unobserved_citations": 0,
            "diagnosis_exact": None,
        }
    try:
        result = parse_controller_factors(
            action_menu=packet["public_input"]["action_menu"],
            claim_handles=[
                item["claim_handle"]
                for item in packet["public_input"]["public_claim_slots"]
            ],
            observed_evidence=packet["public_input"]["observed_evidence"],
            action_attempts=_attempts(
                factor_records["action_choice"],
                packet=packet,
                factor_name="action_choice",
                binding=binding,
            ),
            evidence_state_attempts=_attempts(
                factor_records["evidence_state"],
                packet=packet,
                factor_name="evidence_state",
                binding=binding,
            ),
        )
    except (CompetenceSuiteV2Error, StrongBaselineError):
        return {
            "projection_valid": False,
            "action_correct": False,
            "state_exact": False,
            "missing_claims": 0,
            "contradictory_claims": 0,
            "unobserved_citations": 0,
            "diagnosis_exact": None,
        }
    action_correct = (
        result.action_factor.status is FactorStatus.VALID
        and result.native_action is not None
        and result.native_action.action_index
        == label["expected_action_index"]
    )
    state_exact = (
        result.evidence_state_factor.status is FactorStatus.VALID
        and result.evidence_state_factor.value
        == label["expected_evidence_state"]
    )
    return {
        "projection_valid": result.canonical_decision is not None,
        "action_correct": action_correct,
        "state_exact": state_exact,
        "missing_claims": 0,
        "contradictory_claims": 0,
        "unobserved_citations": 0,
        "diagnosis_exact": None,
    }


def _score_finalizer(
    packet: Mapping[str, Any],
    label: Mapping[str, Any],
    row: Mapping[str, Any],
    factor_records: Mapping[str, Sequence[Mapping[str, Any]]],
    binding: Mapping[str, Any],
) -> dict[str, Any]:
    required = label["required_claims"]
    factor_summary = row.get("factors")
    if not isinstance(factor_summary, Mapping) or set(factor_summary) != set(
        FINALIZER_FACTORS
    ):
        return {
            "projection_valid": False,
            "outcome_exact": False,
            "diagnosis_exact": False,
            "missing_claims": len(required),
            "contradictory_claims": 0,
            "unobserved_citations": 0,
        }
    try:
        result = parse_finalizer_factors(
            claim_handles=[
                item["claim_handle"]
                for item in packet["public_input"]["public_claim_slots"]
            ],
            observations=packet["public_input"]["observed_evidence"],
            attempts_by_factor={
                name: _attempts(
                    factor_records[name],
                    packet=packet,
                    factor_name=name,
                    binding=binding,
                )
                for name in FINALIZER_FACTORS
            },
        )
    except (CompetenceSuiteV2Error, StrongBaselineError):
        return {
            "projection_valid": False,
            "outcome_exact": False,
            "diagnosis_exact": False,
            "missing_claims": len(required),
            "contradictory_claims": 0,
            "unobserved_citations": 0,
        }
    if result.canonical_envelope is None:
        return {
            "projection_valid": False,
            "outcome_exact": False,
            "diagnosis_exact": False,
            "missing_claims": len(required),
            "contradictory_claims": 0,
            "unobserved_citations": 0,
        }
    envelope = result.canonical_envelope
    final = envelope["final_answer"]
    claims = {
        str(item["registered_claim_id"]): item
        for item in final["claims"]
    }
    citations = envelope["claim_to_citations"]
    missing = 0
    contradictory = 0
    unobserved = 0
    semantic_ok = True
    citations_ok = True
    for handle, rule in required.items():
        claim = claims.get(handle)
        if claim is None:
            missing += 1
            semantic_ok = False
            continue
        accepted, forbidden = _semantic_claim_score(str(claim["text"]), rule)
        if forbidden:
            contradictory += 1
        if not accepted:
            semantic_ok = False
        actual_ids = [str(item) for item in citations.get(handle, [])]
        if actual_ids != rule["expected_citations"]:
            citations_ok = False
            known = {
                item["observation_id"]
                for item in packet["public_input"]["observed_evidence"]
            }
            unobserved += sum(item not in known for item in actual_ids)
    extra_handles = set(claims) - set(required)
    if extra_handles:
        contradictory += len(extra_handles)
        semantic_ok = False
    expected_disposition = label["expected_disposition"]
    actual_disposition = {
        "p_sufficient": final["p_sufficient"],
        "verdict": final["verdict"],
        "answer_mode": final["answer_mode"],
        "termination_reason": final["termination_reason"],
    }
    outcome_exact = (
        actual_disposition == expected_disposition
        and semantic_ok
        and citations_ok
        and (
            (
                not required
                and final["natural_language_answer"] == ""
                and not claims
            )
            or (
                required
                and bool(final["natural_language_answer"].strip())
            )
        )
    )
    diagnosis = final["diagnosis"]
    expected_diagnosis = label["expected_diagnosis"]
    diagnosis_projection = {
        key: diagnosis[key]
        for key in (
            "modality_probabilities",
            "hop_types",
            "cause_probabilities",
            "recovery_route_declared",
        )
    }
    return {
        "projection_valid": True,
        "outcome_exact": outcome_exact,
        "diagnosis_exact": diagnosis_projection == expected_diagnosis,
        "missing_claims": missing,
        "contradictory_claims": contradictory,
        "unobserved_citations": unobserved,
    }


def _fraction(values: Sequence[bool]) -> float:
    return sum(values) / len(values) if values else 0.0


def apply_thresholds(metrics: Mapping[str, Any]) -> dict[str, Any]:
    checks = {
        "case_count": metrics.get("case_count") == THRESHOLDS["case_count"],
        "valid_case_projection": (
            metrics.get("valid_case_projection", -1)
            >= THRESHOLDS["valid_case_projection_min"]
        ),
        "controller_action_accuracy": (
            metrics.get("controller_action_accuracy", -1)
            >= THRESHOLDS["controller_action_accuracy_min"]
        ),
        "controller_exact_state": (
            metrics.get("controller_exact_state", -1)
            >= THRESHOLDS["controller_exact_state_min"]
        ),
        "finalizer_exact_outcome": (
            metrics.get("finalizer_exact_outcome", -1)
            >= THRESHOLDS["finalizer_exact_outcome_min"]
        ),
        "diagnosis_exact": (
            metrics.get("diagnosis_exact", -1)
            >= THRESHOLDS["diagnosis_exact_min"]
        ),
        "cross_state_isolation": (
            metrics.get("cross_state_isolation")
            is THRESHOLDS["cross_state_isolation_required"]
        ),
        "unsupported_or_missing_claims": (
            metrics.get("unsupported_or_missing_claims")
            == THRESHOLDS["unsupported_or_missing_claims_max"]
        ),
        "contradictory_claims": (
            metrics.get("contradictory_claims")
            == THRESHOLDS["contradictory_claims_max"]
        ),
        "unobserved_citations": (
            metrics.get("unobserved_citations")
            == THRESHOLDS["unobserved_citations_max"]
        ),
        "integrity_failures": (
            metrics.get("integrity_failures")
            == THRESHOLDS["integrity_failures_max"]
        ),
    }
    return {
        "gate_checks": checks,
        "decision_token": GO_TOKEN if all(checks.values()) else NO_GO_TOKEN,
    }


def score_submission(
    public: Mapping[str, Any],
    private: Mapping[str, Any],
    submission: Mapping[str, Any],
) -> dict[str, Any]:
    rows, raw_attempts, binding = _validate_runner_submission(
        public, submission
    )
    labels = private["labels"]
    scores: list[dict[str, Any]] = []
    for packet in public["packets"]:
        case_id = str(packet["case_id"])
        row = rows[case_id]
        expected_hash = public["freeze_manifest"]["packet_hashes"][case_id]
        if row.get("public_packet_sha256") != expected_hash:
            raise CompetenceSuiteV2Error("RUNNER_PUBLIC_PACKET_HASH_MISMATCH")
        score = (
            _score_controller(
                packet,
                labels[case_id],
                row,
                raw_attempts[case_id],
                binding,
            )
            if packet["case_type"] == "controller"
            else _score_finalizer(
                packet,
                labels[case_id],
                row,
                raw_attempts[case_id],
                binding,
            )
        )
        scores.append(
            {"case_id": case_id, "case_type": packet["case_type"], **score}
        )
    controllers = [row for row in scores if row["case_type"] == "controller"]
    finalizers = [row for row in scores if row["case_type"] == "finalizer"]
    metrics = {
        "case_count": len(scores),
        "valid_case_projection": _fraction(
            [bool(row["projection_valid"]) for row in scores]
        ),
        "controller_action_accuracy": _fraction(
            [bool(row["action_correct"]) for row in controllers]
        ),
        "controller_exact_state": _fraction(
            [bool(row["state_exact"]) for row in controllers]
        ),
        "finalizer_exact_outcome": _fraction(
            [bool(row["outcome_exact"]) for row in finalizers]
        ),
        "diagnosis_exact": _fraction(
            [bool(row["diagnosis_exact"]) for row in finalizers]
        ),
        "cross_state_isolation": len({row["case_id"] for row in scores})
        == len(scores),
        "unsupported_or_missing_claims": sum(
            int(row["missing_claims"]) for row in scores
        ),
        "contradictory_claims": sum(
            int(row["contradictory_claims"]) for row in scores
        ),
        "unobserved_citations": sum(
            int(row["unobserved_citations"]) for row in scores
        ),
        "integrity_failures": 0,
    }
    threshold_result = apply_thresholds(metrics)
    return {
        "schema_version": REPORT_SCHEMA,
        "suite_id": SUITE_ID,
        "run_id": submission.get("run_id"),
        "technical_only": True,
        "scientific_competence_supported": False,
        "h2_supported": False,
        "metrics": metrics,
        "case_scores": scores,
        "thresholds": copy.deepcopy(THRESHOLDS),
        **threshold_result,
    }


def consume_one_shot_ledger(
    ledger_path: Path,
    *,
    run_id: str,
    submission_sha256: str,
) -> None:
    ledger = load_json(ledger_path)
    if ledger.get("schema_version") != LEDGER_SCHEMA:
        raise CompetenceSuiteV2Error("LEDGER_SCHEMA_MISMATCH")
    if ledger.get("state") != "ARMED" or ledger.get("full_suite_runs") != 0:
        raise CompetenceSuiteV2Error("REPEATED_EVALUATION_FORBIDDEN")
    receipt = ledger_path.with_suffix(ledger_path.suffix + ".consumed")
    payload = json.dumps(
        {
            "schema_version": LEDGER_SCHEMA,
            "state": "EVALUATED",
            "run_id": run_id,
            "submission_sha256": submission_sha256,
            "full_suite_runs": 1,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    try:
        fd = os.open(receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise CompetenceSuiteV2Error(
            "REPEATED_EVALUATION_FORBIDDEN"
        ) from exc
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        receipt.unlink(missing_ok=True)
        raise


def evaluate_once(
    public: Mapping[str, Any],
    private: Mapping[str, Any],
    submission: Mapping[str, Any],
    *,
    ledger_path: Path,
) -> dict[str, Any]:
    report = score_submission(public, private, submission)
    consume_one_shot_ledger(
        ledger_path,
        run_id=str(submission.get("run_id")),
        submission_sha256=sha256_json(submission),
    )
    return report


def _raw_attempt(
    packet: Mapping[str, Any],
    factor: str,
    raw_value: Any,
) -> dict[str, Any]:
    prompt = render_case_prompts(packet)[factor]
    raw = (
        raw_value
        if isinstance(raw_value, str)
        else json.dumps(raw_value, sort_keys=True, separators=(",", ":"))
    )
    return {
        "schema_version": governed_runner.ATTEMPT_SCHEMA,
        "attempt_id": f"{packet['case_id']}::{factor}::1",
        "case_id": packet["case_id"],
        "case_type": packet["case_type"],
        "factor_name": factor,
        "attempt_index": 1,
        "attempt_kind": AttemptKind.INITIAL.value,
        "model_slug": "public-only-deterministic-baseline",
        "catalog_record_sha256": "sha256:baseline-record",
        "catalog_file_sha256": "sha256:baseline-catalog",
        "runtime": {
            "tcodex_version": "baseline",
            "tcodex_commit": "baseline",
            "upstream_codex_version": "baseline",
            "tcodex_wrapper_sha256": "sha256:baseline-wrapper",
            "upstream_codex_binary_sha256": "sha256:baseline-binary",
        },
        "prompt_sha256": sha256_bytes(prompt.encode()),
        "prompt_bytes": len(prompt.encode()),
        "raw_output": raw,
        "raw_output_sha256": sha256_bytes(raw.encode()),
        "gateway_success": True,
        "model_output_accepted": True,
        "transport_failure": False,
    }


def _runner_shell(
    public: Mapping[str, Any],
    rows: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
    *,
    run_id: str,
) -> dict[str, Any]:
    public_core = {key: copy.deepcopy(value) for key, value in public.items()}
    public_core.pop("freeze_manifest", None)
    return {
        "schema_version": SUBMISSION_SCHEMA,
        "suite_id": SUITE_ID,
        "run_id": run_id,
        "public_payload_sha256": sha256_json(public_core),
        "raw_attempts": attempts,
        "runner_report": {
            "schema_version": governed_runner.RUNNER_SCHEMA,
            "case_count": CASE_COUNT,
            "model_binding": {
                "model_slug": "public-only-deterministic-baseline",
                "catalog_record_sha256": "sha256:baseline-record",
                "catalog_file_sha256": "sha256:baseline-catalog",
                "tcodex_version": "baseline",
                "tcodex_commit": "baseline",
                "upstream_codex_version": "baseline",
                "tcodex_wrapper_sha256": "sha256:baseline-wrapper",
                "upstream_codex_binary_sha256": "sha256:baseline-binary",
                "wrapper_model_provider": "deterministic-local",
                "wrapper_provider_name": "Public baseline",
                "wrapper_wire_api": "none",
            },
            "execution": {
                "semantic_retries": 0,
                "semantic_repair": False,
                "semantic_substitution": False,
                "model_fallback_or_substitution": False,
                "raw_output_preserved": True,
                "schema_only_retry_maximum_per_factor": 1,
            },
            "cases": rows,
        },
    }


def build_public_only_baseline_submission(
    public: Mapping[str, Any],
    *,
    strategy: str,
) -> dict[str, Any]:
    if strategy not in {
        "first_action_empty_finalizer",
        "keyword_copy",
        "all_ones_diagnosis",
    }:
        raise CompetenceSuiteV2Error("BASELINE_STRATEGY_UNKNOWN")
    rows: list[dict[str, Any]] = []
    all_attempts: list[dict[str, Any]] = []
    for packet in public["packets"]:
        factor_summary: dict[str, Any] = {}
        handles = [
            item["claim_handle"]
            for item in packet["public_input"]["public_claim_slots"]
        ]
        if packet["case_type"] == "controller":
            action_attempt = _raw_attempt(
                packet,
                "action_choice",
                {"function_name": "select_action_00", "arguments": {}},
            )
            state_attempt = _raw_attempt(
                packet,
                "evidence_state",
                _state(
                    modality="vision",
                    hop="entity_identity",
                    cause="evidence_accessible_but_not_found",
                    intent="search_vision",
                    sufficient=0.0,
                ),
            )
            all_attempts.extend((action_attempt, state_attempt))
            factor_summary = {
                "action_choice": {
                    "status": "RECORDED",
                    "attempt_count": 1,
                },
                "evidence_state": {
                    "status": "RECORDED",
                    "attempt_count": 1,
                },
            }
        else:
            observations = packet["public_input"]["observed_evidence"]
            text = ""
            if strategy == "keyword_copy" and observations:
                text = str(observations[0]["payload"]["text"])
            claims = (
                []
                if not text
                else [
                    {
                        "claim_id": f"claim.{packet['case_id']}.1",
                        "registered_claim_id": handles[0],
                        "text": text,
                        "confidence": 1.0,
                    }
                ]
            )
            selections = (
                []
                if not claims
                else [
                    {
                        "registered_claim_id": handles[0],
                        "observation_ids": [
                            observations[0]["observation_id"]
                        ],
                    }
                ]
            )
            disposition_attempt = _raw_attempt(
                packet,
                "disposition",
                {
                    "p_sufficient": 1.0 if text else 0.0,
                    "verdict": "sufficient" if text else "insufficient",
                    "answer_mode": "answer" if text else "abstain",
                    "termination_reason": (
                        "sufficient_evidence"
                        if text
                        else "no_recovery_route"
                    ),
                },
            )
            answer_attempt = _raw_attempt(
                packet, "answer_text", {"text": text}
            )
            claims_attempt = _raw_attempt(
                packet, "claim_drafts", {"claims": claims}
            )
            citations_attempt = _raw_attempt(
                packet,
                "citation_selections",
                {"selections": selections},
            )
            diagnosis = _diagnosis(
                modality=None,
                hop=None,
                cause="not_missing" if text else "source_evidence_absent",
                recovery=False,
            )
            if strategy == "all_ones_diagnosis":
                diagnosis["modality_probabilities"] = {
                    name: 1.0 for name in ("vision", "speech", "ambient")
                }
                diagnosis["hop_types"] = [
                    "entity_identity",
                    "speech_content",
                    "ambient_event",
                ]
                diagnosis["cause_probabilities"] = {
                    name: 1.0
                    for name in (
                        "source_evidence_absent",
                        "evidence_in_source_but_inaccessible",
                        "evidence_accessible_but_not_found",
                        "not_missing",
                        "uncertain",
                    )
                }
            diagnosis["description"] = "Deterministic public-only baseline."
            diagnosis_attempt = _raw_attempt(
                packet, "diagnosis", diagnosis
            )
            all_attempts.extend(
                (
                    disposition_attempt,
                    answer_attempt,
                    claims_attempt,
                    citations_attempt,
                    diagnosis_attempt,
                )
            )
            factor_summary = {
                name: {"status": "RECORDED", "attempt_count": 1}
                for name in FINALIZER_FACTORS
            }
        rows.append(
            {
                "case_id": packet["case_id"],
                "public_packet_sha256": public["freeze_manifest"][
                    "packet_hashes"
                ][packet["case_id"]],
                "factors": factor_summary,
            }
        )
    return _runner_shell(
        public,
        rows,
        all_attempts,
        run_id=f"baseline-{strategy}",
    )


def run_public_baseline_suite(
    public: Mapping[str, Any],
    private: Mapping[str, Any],
) -> dict[str, Any]:
    reports = {}
    for strategy in (
        "first_action_empty_finalizer",
        "keyword_copy",
        "all_ones_diagnosis",
    ):
        report = score_submission(
            public,
            private,
            build_public_only_baseline_submission(public, strategy=strategy),
        )
        if report["decision_token"] != NO_GO_TOKEN:
            raise CompetenceSuiteV2Error("PUBLIC_BASELINE_UNEXPECTEDLY_PASSED")
        reports[strategy] = {
            "decision_token": report["decision_token"],
            "metrics": report["metrics"],
        }
    return {
        "schema_version": (
            "av-trace.external-gateway-public-competence-v2-baselines/2.0"
        ),
        "all_must_fail": True,
        "all_failed": True,
        "reports": reports,
    }


def _atomic_json(path: Path, value: Any, *, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(
                json.dumps(
                    value, indent=2, sort_keys=True, ensure_ascii=False
                ).encode()
                + b"\n"
            )
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def write_freeze(*, root: Path = ROOT) -> None:
    public, private = build_frozen_artifacts(root=root)
    _atomic_json(root / PUBLIC_PATH, public, mode=0o644)
    _atomic_json(root / PRIVATE_PATH, private, mode=0o600)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Freeze/validate v2 without any gateway or model call."
    )
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--write-freeze", action="store_true")
    modes.add_argument("--validate-freeze", action="store_true")
    modes.add_argument("--validate-baselines", action="store_true")
    args = parser.parse_args(argv)
    if args.write_freeze:
        write_freeze()
        print(NO_GO_TOKEN)
        return 0
    public = load_json(ROOT / PUBLIC_PATH)
    private = load_json(ROOT / PRIVATE_PATH)
    validate_frozen_pair(
        public,
        private,
        private_path=ROOT / PRIVATE_PATH,
    )
    if args.validate_baselines:
        print(
            json.dumps(
                run_public_baseline_suite(public, private),
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(NO_GO_TOKEN)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
