"""Granite-native, factorized controller and finalizer adapter v2.

The model chooses a frozen action-menu entry through a native no-argument
function call. Evidence-state heads are authored separately. Final answers
are authored as disposition, answer text, claim drafts, citation selections,
and diagnosis factors, then serialized mechanically.

No routine in this module substitutes answer text, claims, citations, state
heads, or diagnoses. Cross-factor projection can only accept or reject.
"""

from __future__ import annotations

import copy
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from av_trace_strong_baselines.errors import SchemaViolation, StrongBaselineError
from av_trace_strong_baselines.schemas import (
    CAUSES,
    EVIDENCE_STATE_FIELDS,
    HOPS,
    MODALITIES,
    RECOVERY_INTENTS,
    parse_strict_json,
    validate_evidence_state,
    validate_final_answer_envelope,
    validate_tool_action,
)
from av_trace_strong_baselines.security import (
    ObservedEvidenceLock,
    OutputProvenance,
    assert_public_surface,
)

from .contracts import (
    ADAPTER_SCHEMA_VERSION,
    ControllerFactorResult,
    FactorOutcome,
    FactorSpec,
    FactorStatus,
    FinalizerFactorResult,
    NativeActionChoice,
    ProjectionStatus,
    RawFactorAttempt,
    StateProjection,
    fingerprint_public_contract,
    require_attempt_sequence,
)

P_SUFFICIENT_VALUES = (0.0, 0.25, 0.5, 0.75, 1.0)
FINAL_HOPS = (
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
    "other_registered",
)
VERDICTS = ("sufficient", "insufficient", "uncertain")
ANSWER_MODES = ("answer", "partial_answer", "abstain")
TERMINATION_REASONS = (
    "sufficient_evidence",
    "no_recovery_route",
    "budget_guard",
    "uncertain_best_effort",
    "forced_finalization",
)
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")

STRUCTURAL_FACTOR_ERRORS = frozenset(
    {
        "MODEL_OUTPUT_EMPTY",
        "MODEL_OUTPUT_INVALID_UTF8",
        "MODEL_OUTPUT_MALFORMED_JSON",
        "MODEL_OUTPUT_DUPLICATE_KEY",
        "MODEL_OUTPUT_TRAILING_CONTENT",
        "MODEL_OUTPUT_TOO_LARGE",
        "FACTOR_NOT_OBJECT",
        "FACTOR_FIELD_SET_MISMATCH",
        "FACTOR_VALUE_TYPE",
        "FACTOR_VALUES_TYPE",
        "FACTOR_VALUES_DUPLICATE",
        "FACTOR_VALUES_NONCANONICAL_ORDER",
        "NATIVE_ARGUMENTS_NOT_EMPTY_OBJECT",
        "CLAIM_DRAFTS_TYPE",
        "CLAIM_DRAFT_FIELD_SET",
        "CITATION_SELECTIONS_TYPE",
        "CITATION_SELECTION_FIELD_SET",
        "DIAGNOSIS_FIELD_SET",
        "PROBABILITY_MAP_FIELD_SET",
        "PROBABILITY_VALUE_TYPE",
        "BOOLEAN_VALUE_TYPE",
        "TEXT_VALUE_TYPE",
    }
)


def _exact_keys(
    value: Mapping[str, Any],
    keys: set[str],
    *,
    code: str = "FACTOR_FIELD_SET_MISMATCH",
) -> None:
    if set(value) != keys:
        raise SchemaViolation(
            code,
            details={"actual": sorted(value), "required": sorted(keys)},
        )


def _object(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SchemaViolation("FACTOR_NOT_OBJECT")
    return value


def _number_enum(value: Any, allowed: Sequence[float]) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SchemaViolation("FACTOR_VALUE_TYPE")
    normalized = float(value)
    if normalized not in allowed:
        raise SchemaViolation("FACTOR_VALUE_ENUM")
    return normalized


def _probability(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SchemaViolation("PROBABILITY_VALUE_TYPE")
    normalized = float(value)
    if not 0.0 <= normalized <= 1.0:
        raise SchemaViolation("FACTOR_VALUE_RANGE")
    return normalized


def _string_enum(value: Any, allowed: Sequence[str]) -> str:
    if not isinstance(value, str):
        raise SchemaViolation("FACTOR_VALUE_TYPE")
    if value not in allowed:
        raise SchemaViolation("FACTOR_VALUE_ENUM")
    return value


def _canonical_enum_list(value: Any, allowed: Sequence[str]) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise SchemaViolation("FACTOR_VALUES_TYPE")
    if len(set(value)) != len(value):
        raise SchemaViolation("FACTOR_VALUES_DUPLICATE")
    if any(item not in allowed for item in value):
        raise SchemaViolation("FACTOR_VALUE_ENUM")
    selected = set(value)
    if value != [item for item in allowed if item in selected]:
        raise SchemaViolation("FACTOR_VALUES_NONCANONICAL_ORDER")
    return list(value)


def _semantic_scalar_multiset(value: Any) -> Counter[tuple[str, str]]:
    """Return scalar content independent of wrappers and array/object shape."""

    scalars: Counter[tuple[str, str]] = Counter()

    def visit(item: Any) -> None:
        if isinstance(item, Mapping):
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)
        elif item is None:
            scalars[("null", "null")] += 1
        elif isinstance(item, bool):
            scalars[("bool", str(item).lower())] += 1
        elif isinstance(item, (int, float)):
            scalars[("number", repr(float(item)))] += 1
        elif isinstance(item, str):
            scalars[("string", item)] += 1

    visit(value)
    return scalars


def _schema_retry_preserves_content(before: bytes, after: bytes) -> bool:
    """Allow wrapper/type repair only when parseable scalar content is unchanged."""

    try:
        before_value = parse_strict_json(before, maximum_bytes=64_000)
    except SchemaViolation:
        return True
    try:
        after_value = parse_strict_json(after, maximum_bytes=64_000)
    except SchemaViolation:
        return True
    return _semantic_scalar_multiset(before_value) == _semantic_scalar_multiset(
        after_value
    )


def parse_factor_attempts(
    spec: FactorSpec,
    attempts: Sequence[RawFactorAttempt],
    validator: Any,
) -> FactorOutcome:
    """Parse one factor with no more than one content-preserving schema retry."""

    normalized = require_attempt_sequence(attempts)
    first_error: str | None = None
    for index, attempt in enumerate(normalized):
        try:
            parsed = parse_strict_json(
                attempt.raw_output,
                maximum_bytes=spec.maximum_bytes,
            )
            value = validator(parsed)
        except SchemaViolation as exc:
            if index == 0:
                first_error = exc.code
                continue
            return FactorOutcome(
                factor_id=spec.factor_id,
                status=FactorStatus.INVALID_OUTPUT,
                value=None,
                error_code=exc.code,
                attempts=normalized,
            )
        if index == 0 and len(normalized) == 2:
            return FactorOutcome(
                factor_id=spec.factor_id,
                status=FactorStatus.INVALID_OUTPUT,
                value=None,
                error_code="UNNEEDED_SCHEMA_RETRY",
                attempts=normalized,
            )
        if index == 1:
            if first_error not in spec.repairable_error_codes:
                return FactorOutcome(
                    factor_id=spec.factor_id,
                    status=FactorStatus.INVALID_OUTPUT,
                    value=None,
                    error_code="SEMANTIC_RETRY_FORBIDDEN",
                    attempts=normalized,
                )
            if not _schema_retry_preserves_content(
                normalized[0].raw_output,
                normalized[1].raw_output,
            ):
                return FactorOutcome(
                    factor_id=spec.factor_id,
                    status=FactorStatus.INVALID_OUTPUT,
                    value=None,
                    error_code="SCHEMA_RETRY_CHANGED_CONTENT",
                    attempts=normalized,
                )
        return FactorOutcome(
            factor_id=spec.factor_id,
            status=FactorStatus.VALID,
            value=value,
            error_code=None,
            attempts=normalized,
        )
    return FactorOutcome(
        factor_id=spec.factor_id,
        status=FactorStatus.INVALID_OUTPUT,
        value=None,
        error_code=first_error or "INVALID_OUTPUT",
        attempts=normalized,
    )


@dataclass(frozen=True)
class NativeActionPlan:
    """Public Granite function declarations for a frozen action menu."""

    action_menu: tuple[Mapping[str, Any], ...]
    tools: tuple[Mapping[str, Any], ...]
    function_names: tuple[str, ...]
    fingerprint: str

    def function_name_for_index(self, action_index: int) -> str:
        return self.function_names[action_index]


def build_native_action_plan(
    action_menu: Sequence[Mapping[str, Any]],
) -> NativeActionPlan:
    """Expose every complete menu action as one no-argument native function."""

    if not action_menu:
        raise SchemaViolation("ACTION_MENU_EMPTY")
    normalized: list[dict[str, Any]] = []
    tools: list[dict[str, Any]] = []
    names: list[str] = []
    for index, item in enumerate(action_menu):
        action = validate_tool_action(item)
        name = f"select_action_{index:02d}"
        normalized.append(action)
        names.append(name)
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": (
                        "Select this exact frozen menu action: "
                        + json.dumps(
                            action,
                            sort_keys=True,
                            separators=(",", ":"),
                            ensure_ascii=False,
                        )
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                },
            }
        )
    public = {
        "adapter_schema_version": ADAPTER_SCHEMA_VERSION,
        "action_menu": normalized,
        "tools": tools,
    }
    assert_public_surface(public)
    return NativeActionPlan(
        action_menu=tuple(normalized),
        tools=tuple(tools),
        function_names=tuple(names),
        fingerprint=fingerprint_public_contract(public),
    )


def action_choice_spec(plan: NativeActionPlan) -> FactorSpec:
    return FactorSpec(
        factor_id="controller.action_choice",
        role="granite_native_tool_choice",
        output_schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["function_name", "arguments"],
            "properties": {
                "function_name": {"enum": list(plan.function_names)},
                "arguments": {
                    "type": "object",
                    "maxProperties": 0,
                    "additionalProperties": False,
                },
            },
        },
        repairable_error_codes=STRUCTURAL_FACTOR_ERRORS,
        maximum_bytes=2_048,
    )


def evidence_state_spec(claim_handles: Sequence[str]) -> FactorSpec:
    return FactorSpec(
        factor_id="controller.evidence_state_heads",
        role="evidence_state_heads",
        output_schema={
            "type": "object",
            "additionalProperties": False,
            "required": list(EVIDENCE_STATE_FIELDS),
            "properties": {
                "p_sufficient": {"enum": list(P_SUFFICIENT_VALUES)},
                "covered_claim_handles": {
                    "type": "array",
                    "items": {"enum": list(claim_handles)},
                    "uniqueItems": True,
                },
                "missing_modalities": {
                    "type": "array",
                    "items": {"enum": list(MODALITIES)},
                    "uniqueItems": True,
                },
                "missing_hops": {
                    "type": "array",
                    "items": {"enum": list(HOPS)},
                    "uniqueItems": True,
                },
                "missingness_cause": {"enum": list(CAUSES)},
                "recovery_intent": {"enum": list(RECOVERY_INTENTS)},
            },
        },
        repairable_error_codes=STRUCTURAL_FACTOR_ERRORS,
        maximum_bytes=8_192,
    )


def controller_factor_contracts(
    *,
    action_menu: Sequence[Mapping[str, Any]],
    claim_handles: Sequence[str],
) -> dict[str, Any]:
    """Return the public two-call Granite controller interface."""

    plan = build_native_action_plan(action_menu)
    state = evidence_state_spec(claim_handles)
    value = {
        "adapter_schema_version": ADAPTER_SCHEMA_VERSION,
        "factors": [
            {
                "factor_id": "controller.action_choice",
                "transport": "granite_native_function_call",
                "tool_choice": "required",
                "parallel_tool_calls": False,
                "tools": [copy.deepcopy(dict(item)) for item in plan.tools],
                "output_schema": copy.deepcopy(dict(action_choice_spec(plan).output_schema)),
            },
            {
                "factor_id": state.factor_id,
                "transport": "strict_constrained_json",
                "output_schema": copy.deepcopy(dict(state.output_schema)),
            },
        ],
        "retry_policy": {
            "maximum_schema_only_retries_per_factor": 1,
            "semantic_retry": False,
            "cross_factor_retry": False,
        },
        "assembly": "reject_or_mechanically_serialize_without_field_fill",
    }
    assert_public_surface(value)
    return value


def _parse_action_choice(
    value: Any,
    *,
    plan: NativeActionPlan,
) -> NativeActionChoice:
    value = _object(value)
    _exact_keys(value, {"function_name", "arguments"})
    name = _string_enum(value["function_name"], plan.function_names)
    arguments = value["arguments"]
    if not isinstance(arguments, Mapping) or arguments:
        raise SchemaViolation("NATIVE_ARGUMENTS_NOT_EMPTY_OBJECT")
    index = plan.function_names.index(name)
    return NativeActionChoice(
        function_name=name,
        action_index=index,
        action=copy.deepcopy(plan.action_menu[index]),
    )


def _parse_evidence_state(
    value: Any,
    *,
    claim_handles: Sequence[str],
) -> dict[str, Any]:
    value = _object(value)
    _exact_keys(value, set(EVIDENCE_STATE_FIELDS))
    return {
        "p_sufficient": _number_enum(
            value["p_sufficient"], P_SUFFICIENT_VALUES
        ),
        "covered_claim_handles": _canonical_enum_list(
            value["covered_claim_handles"], claim_handles
        ),
        "missing_modalities": _canonical_enum_list(
            value["missing_modalities"], MODALITIES
        ),
        "missing_hops": _canonical_enum_list(value["missing_hops"], HOPS),
        "missingness_cause": _string_enum(
            value["missingness_cause"], CAUSES
        ),
        "recovery_intent": _string_enum(
            value["recovery_intent"], RECOVERY_INTENTS
        ),
    }


def project_evidence_state(
    state: Mapping[str, Any],
    *,
    claim_handles: Sequence[str],
    observed_evidence: Sequence[Mapping[str, Any]],
    native_action: NativeActionChoice | None,
) -> StateProjection:
    """Check consistency without changing or filling any model-authored head."""

    try:
        normalized = validate_evidence_state(
            state,
            allowed_claim_handles=claim_handles,
        )
        lock = ObservedEvidenceLock(observed_evidence)
        if normalized["covered_claim_handles"] and not lock.observation_ids:
            raise SchemaViolation("COVERED_CLAIMS_WITHOUT_OBSERVED_EVIDENCE")
        missing = bool(
            normalized["missing_modalities"] or normalized["missing_hops"]
        )
        if missing and normalized["missingness_cause"] == "not_missing":
            raise SchemaViolation("MISSING_REQUIREMENT_WITH_NOT_MISSING_CAUSE")
        if (
            not missing
            and normalized["missingness_cause"] != "not_missing"
            and normalized["covered_claim_handles"]
        ):
            raise SchemaViolation("COVERAGE_WITH_NONFINAL_MISSINGNESS_CAUSE")
        all_covered = (
            set(normalized["covered_claim_handles"]) == set(claim_handles)
            and bool(claim_handles)
        )
        if normalized["p_sufficient"] == 1.0 and (
            not all_covered
            or missing
            or normalized["missingness_cause"] != "not_missing"
        ):
            raise SchemaViolation("MAX_SUFFICIENCY_WITH_INCOMPLETE_STATE")
        intent = normalized["recovery_intent"]
        if intent == "finalize_answer" and (
            not all_covered
            or missing
            or normalized["p_sufficient"] < 0.5
            or normalized["missingness_cause"] != "not_missing"
        ):
            raise SchemaViolation("FINALIZE_ANSWER_STATE_INCONSISTENT")
        if intent == "finalize_abstain" and normalized["p_sufficient"] > 0.5:
            raise SchemaViolation("FINALIZE_ABSTAIN_STATE_INCONSISTENT")
        required_modality_by_intent = {
            "search_vision": "vision",
            "search_speech": "speech",
            "search_ambient": "ambient",
        }
        required_modality = required_modality_by_intent.get(intent)
        if (
            required_modality is not None
            and required_modality not in normalized["missing_modalities"]
        ):
            raise SchemaViolation("SEARCH_INTENT_MISSING_MODALITY_INCONSISTENT")
        if (
            intent in {"check_channel_status", "retry_restored_route"}
            and normalized["missingness_cause"]
            != "evidence_in_source_but_inaccessible"
        ):
            raise SchemaViolation("RECOVERY_INTENT_CAUSE_INCONSISTENT")
    except SchemaViolation as exc:
        return StateProjection(
            status=ProjectionStatus.REJECTED,
            evidence_state=None,
            error_code=exc.code,
        )
    return StateProjection(
        status=ProjectionStatus.ACCEPTED,
        evidence_state=copy.deepcopy(normalized),
        error_code=None,
    )


def serialize_controller_decision(
    native_action: NativeActionChoice,
    projection: StateProjection,
) -> dict[str, Any]:
    """Mechanically serialize accepted factors into the v2 decision record."""

    if (
        projection.status is not ProjectionStatus.ACCEPTED
        or projection.evidence_state is None
    ):
        raise SchemaViolation("STATE_PROJECTION_NOT_ACCEPTED")
    return {
        "adapter_schema_version": ADAPTER_SCHEMA_VERSION,
        "native_function_name": native_action.function_name,
        "action_index": native_action.action_index,
        "action": copy.deepcopy(dict(native_action.action)),
        "evidence_state": copy.deepcopy(dict(projection.evidence_state)),
    }


def parse_controller_factors(
    *,
    action_menu: Sequence[Mapping[str, Any]],
    claim_handles: Sequence[str],
    observed_evidence: Sequence[Mapping[str, Any]],
    action_attempts: Sequence[RawFactorAttempt],
    evidence_state_attempts: Sequence[RawFactorAttempt],
) -> ControllerFactorResult:
    """Parse action and state independently, retaining a valid action on reject."""

    plan = build_native_action_plan(action_menu)
    action = parse_factor_attempts(
        action_choice_spec(plan),
        action_attempts,
        lambda value: _parse_action_choice(value, plan=plan),
    )
    state = parse_factor_attempts(
        evidence_state_spec(claim_handles),
        evidence_state_attempts,
        lambda value: _parse_evidence_state(
            value,
            claim_handles=claim_handles,
        ),
    )
    native_action = (
        action.value
        if action.status is FactorStatus.VALID
        and isinstance(action.value, NativeActionChoice)
        else None
    )
    if state.status is FactorStatus.VALID and isinstance(state.value, Mapping):
        projection = project_evidence_state(
            state.value,
            claim_handles=claim_handles,
            observed_evidence=observed_evidence,
            native_action=native_action,
        )
    else:
        projection = StateProjection(
            status=ProjectionStatus.NOT_RUN,
            evidence_state=None,
            error_code="EVIDENCE_STATE_FACTOR_INVALID",
        )
    canonical = None
    if native_action is not None and projection.status is ProjectionStatus.ACCEPTED:
        canonical = serialize_controller_decision(native_action, projection)
    return ControllerFactorResult(
        action_factor=action,
        evidence_state_factor=state,
        native_action=native_action,
        state_projection=projection,
        canonical_decision=canonical,
    )


def finalizer_factor_specs(
    *,
    claim_handles: Sequence[str],
    observation_ids: Sequence[str],
) -> dict[str, FactorSpec]:
    probability = {"type": "number", "minimum": 0.0, "maximum": 1.0}
    return {
        "disposition": FactorSpec(
            factor_id="finalizer.disposition",
            role="final_disposition",
            output_schema={
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "p_sufficient",
                    "verdict",
                    "answer_mode",
                    "termination_reason",
                ],
                "properties": {
                    "p_sufficient": probability,
                    "verdict": {"enum": list(VERDICTS)},
                    "answer_mode": {"enum": list(ANSWER_MODES)},
                    "termination_reason": {
                        "enum": list(TERMINATION_REASONS)
                    },
                },
            },
            repairable_error_codes=STRUCTURAL_FACTOR_ERRORS,
            maximum_bytes=2_048,
        ),
        "answer_text": FactorSpec(
            factor_id="finalizer.answer_text",
            role="natural_language_answer",
            output_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["text"],
                "properties": {"text": {"type": "string", "maxLength": 1000}},
            },
            repairable_error_codes=STRUCTURAL_FACTOR_ERRORS,
            maximum_bytes=4_096,
        ),
        "claim_drafts": FactorSpec(
            factor_id="finalizer.claim_drafts",
            role="claim_drafting",
            output_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["claims"],
                "properties": {
                    "claims": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": [
                                "claim_id",
                                "registered_claim_id",
                                "text",
                                "confidence",
                            ],
                            "properties": {
                                "claim_id": {"type": "string"},
                                "registered_claim_id": {
                                    "enum": list(claim_handles)
                                },
                                "text": {"type": "string"},
                                "confidence": probability,
                            },
                        },
                    }
                },
            },
            repairable_error_codes=STRUCTURAL_FACTOR_ERRORS,
            maximum_bytes=16_384,
        ),
        "citation_selections": FactorSpec(
            factor_id="finalizer.citation_selections",
            role="citation_selection",
            output_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["selections"],
                "properties": {
                    "selections": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": [
                                "registered_claim_id",
                                "observation_ids",
                            ],
                            "properties": {
                                "registered_claim_id": {
                                    "enum": list(claim_handles)
                                },
                                "observation_ids": {
                                    "type": "array",
                                    "items": {"enum": list(observation_ids)},
                                    "uniqueItems": True,
                                },
                            },
                        },
                    }
                },
            },
            repairable_error_codes=STRUCTURAL_FACTOR_ERRORS,
            maximum_bytes=16_384,
        ),
        "diagnosis": FactorSpec(
            factor_id="finalizer.diagnosis",
            role="diagnosis_fields",
            output_schema={
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "modality_probabilities",
                    "hop_types",
                    "cause_probabilities",
                    "recovery_route_declared",
                    "description",
                ],
                "properties": {
                    "modality_probabilities": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": list(MODALITIES),
                        "properties": {
                            name: probability for name in MODALITIES
                        },
                    },
                    "hop_types": {
                        "type": "array",
                        "items": {"enum": list(FINAL_HOPS)},
                        "uniqueItems": True,
                    },
                    "cause_probabilities": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": list(CAUSES),
                        "properties": {name: probability for name in CAUSES},
                    },
                    "recovery_route_declared": {"type": "boolean"},
                    "description": {"type": "string", "maxLength": 500},
                },
            },
            repairable_error_codes=STRUCTURAL_FACTOR_ERRORS,
            maximum_bytes=16_384,
        ),
    }


def finalizer_factor_contracts(
    *,
    claim_handles: Sequence[str],
    observation_ids: Sequence[str],
) -> dict[str, Any]:
    """Return the public five-call Granite finalizer interface."""

    specs = finalizer_factor_specs(
        claim_handles=claim_handles,
        observation_ids=observation_ids,
    )
    value = {
        "adapter_schema_version": ADAPTER_SCHEMA_VERSION,
        "factors": [
            {
                "factor_id": spec.factor_id,
                "role": spec.role,
                "transport": "strict_constrained_json",
                "output_schema": copy.deepcopy(dict(spec.output_schema)),
            }
            for spec in specs.values()
        ],
        "retry_policy": {
            "maximum_schema_only_retries_per_factor": 1,
            "semantic_retry": False,
            "cross_factor_retry": False,
        },
        "assembly": (
            "mechanical_citation_expansion_and_canonical_serialization"
        ),
        "answer_substitution": False,
    }
    assert_public_surface(value)
    return value


def _parse_disposition(value: Any) -> dict[str, Any]:
    value = _object(value)
    _exact_keys(
        value,
        {
            "p_sufficient",
            "verdict",
            "answer_mode",
            "termination_reason",
        },
    )
    return {
        "p_sufficient": _number_enum(
            value["p_sufficient"], P_SUFFICIENT_VALUES
        ),
        "verdict": _string_enum(value["verdict"], VERDICTS),
        "answer_mode": _string_enum(value["answer_mode"], ANSWER_MODES),
        "termination_reason": _string_enum(
            value["termination_reason"], TERMINATION_REASONS
        ),
    }


def _parse_answer_text(value: Any) -> str:
    value = _object(value)
    _exact_keys(value, {"text"})
    text = value["text"]
    if not isinstance(text, str) or len(text) > 1000:
        raise SchemaViolation("TEXT_VALUE_TYPE")
    return text


def _parse_claim_drafts(
    value: Any,
    *,
    claim_handles: Sequence[str],
) -> list[dict[str, Any]]:
    value = _object(value)
    _exact_keys(value, {"claims"})
    claims = value["claims"]
    if not isinstance(claims, list) or len(claims) > 32:
        raise SchemaViolation("CLAIM_DRAFTS_TYPE")
    normalized: list[dict[str, Any]] = []
    seen_claim_ids: set[str] = set()
    seen_handles: set[str] = set()
    for claim in claims:
        if not isinstance(claim, Mapping):
            raise SchemaViolation("CLAIM_DRAFTS_TYPE")
        _exact_keys(
            claim,
            {"claim_id", "registered_claim_id", "text", "confidence"},
            code="CLAIM_DRAFT_FIELD_SET",
        )
        claim_id = claim["claim_id"]
        handle = claim["registered_claim_id"]
        text = claim["text"]
        if not isinstance(claim_id, str) or not ID_PATTERN.fullmatch(claim_id):
            raise SchemaViolation("CLAIM_ID_INVALID")
        if claim_id in seen_claim_ids:
            raise SchemaViolation("CLAIM_ID_DUPLICATE")
        if not isinstance(handle, str) or handle not in claim_handles:
            raise SchemaViolation("CLAIM_HANDLE_ENUM")
        if handle in seen_handles:
            raise SchemaViolation("CLAIM_HANDLE_DUPLICATE")
        if not isinstance(text, str) or not text.strip() or len(text) > 500:
            raise SchemaViolation("CLAIM_TEXT_INVALID")
        seen_claim_ids.add(claim_id)
        seen_handles.add(handle)
        normalized.append(
            {
                "claim_id": claim_id,
                "registered_claim_id": handle,
                "text": text,
                "confidence": _probability(claim["confidence"]),
            }
        )
    return normalized


def _parse_citation_selections(
    value: Any,
    *,
    claim_handles: Sequence[str],
    observation_ids: Sequence[str],
) -> list[dict[str, Any]]:
    value = _object(value)
    _exact_keys(value, {"selections"})
    selections = value["selections"]
    if not isinstance(selections, list) or len(selections) > 32:
        raise SchemaViolation("CITATION_SELECTIONS_TYPE")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for selection in selections:
        if not isinstance(selection, Mapping):
            raise SchemaViolation("CITATION_SELECTIONS_TYPE")
        _exact_keys(
            selection,
            {"registered_claim_id", "observation_ids"},
            code="CITATION_SELECTION_FIELD_SET",
        )
        handle = selection["registered_claim_id"]
        if not isinstance(handle, str) or handle not in claim_handles:
            raise SchemaViolation("CLAIM_HANDLE_ENUM")
        if handle in seen:
            raise SchemaViolation("CLAIM_HANDLE_DUPLICATE")
        ids = _canonical_enum_list(
            selection["observation_ids"], observation_ids
        )
        seen.add(handle)
        normalized.append(
            {"registered_claim_id": handle, "observation_ids": ids}
        )
    return normalized


def _probability_map(
    value: Any,
    names: Sequence[str],
) -> dict[str, float]:
    if not isinstance(value, Mapping):
        raise SchemaViolation("PROBABILITY_VALUE_TYPE")
    _exact_keys(value, set(names), code="PROBABILITY_MAP_FIELD_SET")
    return {
        name: _probability(value[name]) for name in names
    }


def _parse_diagnosis(value: Any) -> dict[str, Any]:
    value = _object(value)
    _exact_keys(
        value,
        {
            "modality_probabilities",
            "hop_types",
            "cause_probabilities",
            "recovery_route_declared",
            "description",
        },
        code="DIAGNOSIS_FIELD_SET",
    )
    recovery = value["recovery_route_declared"]
    if not isinstance(recovery, bool):
        raise SchemaViolation("BOOLEAN_VALUE_TYPE")
    description = value["description"]
    if not isinstance(description, str) or len(description) > 500:
        raise SchemaViolation("TEXT_VALUE_TYPE")
    return {
        "modality_probabilities": _probability_map(
            value["modality_probabilities"], MODALITIES
        ),
        "hop_types": _canonical_enum_list(
            value["hop_types"], FINAL_HOPS
        ),
        "cause_probabilities": _probability_map(
            value["cause_probabilities"], CAUSES
        ),
        "recovery_route_declared": recovery,
        "description": description,
    }


def _finalizer_projection_error(
    disposition: Mapping[str, Any],
    answer_text: str,
    claims: Sequence[Mapping[str, Any]],
    selections: Sequence[Mapping[str, Any]],
    *,
    claim_handles: Sequence[str],
) -> str | None:
    mode = disposition["answer_mode"]
    verdict = disposition["verdict"]
    p_sufficient = disposition["p_sufficient"]
    draft_handles = [str(claim["registered_claim_id"]) for claim in claims]
    selection_handles = [
        str(selection["registered_claim_id"]) for selection in selections
    ]
    if draft_handles != selection_handles:
        return "CLAIM_CITATION_HANDLE_ORDER_MISMATCH"
    if mode == "answer":
        if set(draft_handles) != set(claim_handles):
            return "ANSWER_MISSING_REQUIRED_CLAIMS"
        if not answer_text.strip():
            return "ANSWER_TEXT_EMPTY"
        if verdict != "sufficient" or p_sufficient < 0.5:
            return "ANSWER_SUFFICIENCY_INCONSISTENT"
        if any(not selection["observation_ids"] for selection in selections):
            return "ANSWER_CLAIM_WITHOUT_CITATION"
    elif mode == "abstain":
        if claims or selections or answer_text.strip():
            return "ABSTAIN_WITH_ANSWER_CONTENT"
        if verdict == "sufficient" or p_sufficient > 0.5:
            return "ABSTAIN_SUFFICIENCY_INCONSISTENT"
    else:
        if not claims or not answer_text.strip():
            return "PARTIAL_ANSWER_WITHOUT_CONTENT"
        if set(draft_handles) >= set(claim_handles):
            return "PARTIAL_ANSWER_HAS_FULL_COVERAGE"
        if any(not selection["observation_ids"] for selection in selections):
            return "ANSWER_CLAIM_WITHOUT_CITATION"
    if disposition["termination_reason"] == "sufficient_evidence" and mode != "answer":
        return "TERMINATION_MODE_INCONSISTENT"
    if mode == "answer" and disposition["termination_reason"] != "sufficient_evidence":
        return "TERMINATION_MODE_INCONSISTENT"
    return None


def serialize_finalizer_factors(
    *,
    disposition: Mapping[str, Any],
    answer_text: str,
    claim_drafts: Sequence[Mapping[str, Any]],
    citation_selections: Sequence[Mapping[str, Any]],
    diagnosis: Mapping[str, Any],
    claim_handles: Sequence[str],
    observations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build the canonical envelope without generating or replacing semantics."""

    projection_error = _finalizer_projection_error(
        disposition,
        answer_text,
        claim_drafts,
        citation_selections,
        claim_handles=claim_handles,
    )
    if projection_error:
        raise SchemaViolation(projection_error)
    lock = ObservedEvidenceLock(observations)
    observation_map = {
        item["observation_id"]: item for item in lock.public_observations()
    }
    selection_map = {
        item["registered_claim_id"]: list(item["observation_ids"])
        for item in citation_selections
    }
    claims: list[dict[str, Any]] = []
    citation_map: dict[str, list[str]] = {}
    for draft in claim_drafts:
        handle = str(draft["registered_claim_id"])
        ids = selection_map[handle]
        citations = [
            {
                "observation_id": observation_id,
                "interval": copy.deepcopy(
                    observation_map[observation_id]["interval"]
                ),
                "modalities": list(
                    observation_map[observation_id]["modalities"]
                ),
            }
            for observation_id in ids
        ]
        claims.append(
            {
                "claim_id": draft["claim_id"],
                "registered_claim_id": handle,
                "text": draft["text"],
                "confidence": draft["confidence"],
                "citations": citations,
            }
        )
        citation_map[handle] = ids
    envelope = {
        "final_answer": {
            "p_sufficient": disposition["p_sufficient"],
            "verdict": disposition["verdict"],
            "answer_mode": disposition["answer_mode"],
            "claims": claims,
            "diagnosis": copy.deepcopy(dict(diagnosis)),
            "natural_language_answer": answer_text,
            "termination_reason": disposition["termination_reason"],
        },
        "claim_to_citations": citation_map,
    }
    return validate_final_answer_envelope(
        envelope,
        claim_handles=claim_handles,
        evidence_lock=lock,
        provenance=OutputProvenance(
            model_authored_paths=frozenset(
                {
                    "final_answer.p_sufficient",
                    "final_answer.verdict",
                    "final_answer.answer_mode",
                    "final_answer.claims",
                    "final_answer.diagnosis",
                    "final_answer.natural_language_answer",
                    "final_answer.termination_reason",
                }
            ),
            copied_paths=frozenset(
                {
                    "final_answer.claims.citations.interval",
                    "final_answer.claims.citations.modalities",
                    "claim_to_citations",
                }
            ),
        ),
    )


def parse_finalizer_factors(
    *,
    claim_handles: Sequence[str],
    observations: Sequence[Mapping[str, Any]],
    attempts_by_factor: Mapping[str, Sequence[RawFactorAttempt]],
) -> FinalizerFactorResult:
    """Parse five independent factors and mechanically serialize if consistent."""

    lock = ObservedEvidenceLock(observations)
    observation_ids = tuple(
        item["observation_id"] for item in lock.public_observations()
    )
    specs = finalizer_factor_specs(
        claim_handles=claim_handles,
        observation_ids=observation_ids,
    )
    expected = set(specs)
    if set(attempts_by_factor) != expected:
        raise StrongBaselineError(
            "FINALIZER_FACTOR_SET_MISMATCH",
            details={
                "actual": sorted(attempts_by_factor),
                "required": sorted(expected),
            },
        )
    validators = {
        "disposition": _parse_disposition,
        "answer_text": _parse_answer_text,
        "claim_drafts": lambda value: _parse_claim_drafts(
            value,
            claim_handles=claim_handles,
        ),
        "citation_selections": lambda value: _parse_citation_selections(
            value,
            claim_handles=claim_handles,
            observation_ids=observation_ids,
        ),
        "diagnosis": _parse_diagnosis,
    }
    outcomes = {
        name: parse_factor_attempts(
            specs[name],
            attempts_by_factor[name],
            validators[name],
        )
        for name in specs
    }
    invalid = [
        outcome
        for outcome in outcomes.values()
        if outcome.status is not FactorStatus.VALID
    ]
    if invalid:
        return FinalizerFactorResult(
            factors=outcomes,
            projection_status=ProjectionStatus.NOT_RUN,
            projection_error_code=invalid[0].error_code,
            canonical_envelope=None,
        )
    try:
        envelope = serialize_finalizer_factors(
            disposition=outcomes["disposition"].value,
            answer_text=outcomes["answer_text"].value,
            claim_drafts=outcomes["claim_drafts"].value,
            citation_selections=outcomes["citation_selections"].value,
            diagnosis=outcomes["diagnosis"].value,
            claim_handles=claim_handles,
            observations=observations,
        )
    except SchemaViolation as exc:
        return FinalizerFactorResult(
            factors=outcomes,
            projection_status=ProjectionStatus.REJECTED,
            projection_error_code=exc.code,
            canonical_envelope=None,
        )
    return FinalizerFactorResult(
        factors=outcomes,
        projection_status=ProjectionStatus.ACCEPTED,
        projection_error_code=None,
        canonical_envelope=envelope,
    )
