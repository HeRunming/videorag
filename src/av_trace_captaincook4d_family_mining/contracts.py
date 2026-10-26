"""Contracts for CaptainCook4D machine-expert-provisional family mining."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from typing import Any

SCHEMA_VERSION = "av-trace.captaincook4d-family-mining/1.0"
ARTIFACT_CLASS = "MACHINE_EXPERT_PROVISIONAL"
EXPECTED_SOURCE_IDS = ("15_29", "16_20", "26_22")
EXPECTED_SOURCE_GROUPS = {
    "15_29": "cc4d_p02_e02",
    "16_20": "cc4d_p01_e08",
    "26_22": "cc4d_p03_e03",
}
P_TIERS = (
    "P0_MACHINE_CANDIDATE",
    "P1_MACHINE_CROSS_VALIDATED",
    "P2_MACHINE_COUNTERFACTUAL_VALIDATED",
)
HUMAN_TIER_MARKERS = (
    "H1_HUMAN_VALIDATED",
    "H2_HUMAN_ADJUDICATED_GOLD",
    "H2_HUMAN_ADJUDICATED_SATURATION_AUDITED",
)
OBSERVATION_CLASSES = (
    "dynamic_nontext_visual",
    "board_ocr_static_overlay",
    "speech",
    "non_speech",
)
ALLOWED_COMPOSITION_OPERATORS = (
    "setup_or_preparation_then_execution",
    "tool_or_ingredient_selection_then_transformation",
    "visible_action_then_resulting_state",
    "audible_process_then_visible_state_change",
    "earlier_action_then_later_consequence",
)
ALLOWED_MODES = ("gate_a_candidate_input", "development_only")


def canonical_bytes(value: Any) -> bytes:
    """Return deterministic JSON bytes."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def json_hash(value: Any) -> str:
    """Return a prefixed deterministic SHA-256."""
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def _walk(value: Any, location: str = "root"):
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_location = f"{location}.{key}"
            yield str(key), child, child_location
            yield from _walk(child, child_location)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, f"{location}[{index}]")


def assert_machine_expert_provisional_only(value: Any) -> None:
    """Reject human acceptance, necessity, or execution claims."""
    forbidden_true = {
        "human_reviewed",
        "human_validated",
        "human_gold",
        "h1_assigned",
        "h2_assigned",
        "human_minimality_asserted",
        "human_necessity_asserted",
        "necessity_claimed",
        "minimality_claimed",
        "final_accepted",
        "accepted_family",
        "accepted_ses",
        "active_intervention",
        "intervention_executed",
        "scientific_execution_authorized",
    }
    for key, child, location in _walk(value):
        if key in forbidden_true and child is not False:
            raise ValueError(f"FORBIDDEN_AFFIRMATIVE_STATUS:{location}")
        if isinstance(child, str) and child in HUMAN_TIER_MARKERS:
            raise ValueError(f"HUMAN_TIER_FORBIDDEN:{location}:{child}")


def validate_hop_structure(hop: Mapping[str, Any]) -> None:
    """Require near one-hop records and coherent compositional multi-hop."""
    stratum = hop.get("hop_stratum")
    temporal = hop.get("temporal_stratum")
    composition = hop.get("composition")
    if stratum == "one_hop":
        if temporal != "near_local":
            raise ValueError("ONE_HOP_MUST_BE_NEAR_LOCAL")
        if composition is not None:
            raise ValueError("ONE_HOP_MUST_NOT_HAVE_COMPOSITION")
        if hop.get("one_hop_implies_near") is not True:
            raise ValueError("ONE_HOP_NEAR_ASSERTION_REQUIRED")
        return
    if stratum != "multi_hop":
        raise ValueError(f"INVALID_HOP_STRATUM:{stratum}")
    if temporal not in {"near_local", "far_separated"}:
        raise ValueError("MULTI_HOP_TEMPORAL_STRATUM_INVALID")
    if not isinstance(composition, Mapping):
        raise TypeError("MULTI_HOP_REQUIRES_COMPOSITION")
    if composition.get("operator") not in ALLOWED_COMPOSITION_OPERATORS:
        raise ValueError("MULTI_HOP_OPERATOR_INVALID")
    components = composition.get("components")
    if not isinstance(components, list) or len(components) < 2:
        raise ValueError("MULTI_HOP_REQUIRES_TWO_COMPONENTS")
    if any(
        not str(item.get("claim_hypothesis", "")).strip()
        or not isinstance(item.get("interval"), Mapping)
        for item in components
    ):
        raise ValueError("MULTI_HOP_COMPONENT_CLAIMS_REQUIRED")
    if not str(composition.get("composed_claim_hypothesis", "")).strip():
        raise ValueError("MULTI_HOP_COMPOSED_CLAIM_REQUIRED")
    if composition.get("coherence_basis") not in {
        "same_object_or_material",
        "same_tool_or_appliance",
        "same_procedure_stage_chain",
        "same_result_state",
        "audio_visual_process_result",
    }:
        raise ValueError("MULTI_HOP_COHERENCE_BASIS_INVALID")
    if composition.get("arbitrary_interval_pairing_forbidden") is not True:
        raise ValueError("MULTI_HOP_ARBITRARY_PAIRING_PROHIBITION_REQUIRED")
    if composition.get("each_component_required_human_validated") is not False:
        raise ValueError("MULTI_HOP_MUST_REMAIN_HUMAN_UNVALIDATED")


def _validate_inspection(lead: Mapping[str, Any], *, mode: str) -> None:
    assistance = lead.get("authoring_assistance")
    if not isinstance(assistance, Mapping):
        raise TypeError("AUTHORING_ASSISTANCE_REQUIRED")
    inspection = assistance.get("bounded_direct_inspection")
    if not isinstance(inspection, Mapping):
        raise TypeError("BOUNDED_DIRECT_INSPECTION_REQUIRED")
    if inspection.get("raw_local_media_only") is not True:
        raise ValueError("DIRECT_INSPECTION_MUST_USE_RAW_LOCAL_MEDIA")
    if inspection.get("repository_media_derivatives_persisted") is not False:
        raise ValueError("PERSISTED_MEDIA_DERIVATIVES_FORBIDDEN")
    limits = inspection.get("limits")
    if not isinstance(limits, Mapping):
        raise TypeError("DIRECT_INSPECTION_LIMITS_REQUIRED")
    if not 0 < float(limits.get("frame_window_max_seconds", 0)) <= 32:
        raise ValueError("FRAME_INSPECTION_BOUND_INVALID")
    if not 0 < float(limits.get("audio_window_max_seconds", 0)) <= 32:
        raise ValueError("AUDIO_INSPECTION_BOUND_INVALID")
    if not 1 <= int(limits.get("maximum_frame_samples", 0)) <= 24:
        raise ValueError("FRAME_SAMPLE_BOUND_INVALID")
    hypotheses = inspection.get("source_world_hypotheses")
    if not isinstance(hypotheses, Mapping):
        raise TypeError("SOURCE_WORLD_HYPOTHESES_REQUIRED")
    required = (
        "question_hypothesis",
        "answer_hypothesis",
        "claim_hypotheses",
        "evidence_hypotheses",
    )
    if any(key not in hypotheses for key in required):
        raise ValueError("SOURCE_WORLD_HYPOTHESIS_FIELDS_MISSING")
    if hypotheses.get("artifact_classification") != ARTIFACT_CLASS:
        raise ValueError("MACHINE_EXPERT_PROVISIONAL_CLASS_REQUIRED")
    if hypotheses.get("human_semantic_validation_status") != "NOT_PERFORMED":
        raise ValueError("HUMAN_VALIDATION_MUST_REMAIN_NOT_PERFORMED")
    if mode == "development_only":
        if not str(hypotheses.get("question_hypothesis", "")).strip():
            raise ValueError("DEV_QUESTION_HYPOTHESIS_REQUIRED")
        if not str(hypotheses.get("answer_hypothesis", "")).strip():
            raise ValueError("DEV_ANSWER_HYPOTHESIS_REQUIRED")
        if not hypotheses.get("claim_hypotheses"):
            raise ValueError("DEV_CLAIM_HYPOTHESES_REQUIRED")
        if not hypotheses.get("evidence_hypotheses"):
            raise ValueError("DEV_EVIDENCE_HYPOTHESES_REQUIRED")


def validate_candidate_registry(registry: Mapping[str, Any]) -> None:
    """Validate the CaptainCook4D six-lead registry contract."""
    if registry.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("REGISTRY_SCHEMA_VERSION_INVALID")
    if registry.get("artifact_classification") != ARTIFACT_CLASS:
        raise ValueError("REGISTRY_ARTIFACT_CLASS_INVALID")
    mode = registry.get("mode")
    if mode not in ALLOWED_MODES:
        raise ValueError("REGISTRY_MODE_INVALID")
    if registry.get("registry_kind") != (
        "MACHINE_EXPERT_PROVISIONAL_CAPTAINCOOK4D_EVENT_LEADS"
    ):
        raise ValueError("REGISTRY_KIND_INVALID")
    sources = registry.get("sources")
    if not isinstance(sources, list) or len(sources) != 3:
        raise ValueError("REGISTRY_MUST_CONTAIN_THREE_SOURCES")
    source_ids = tuple(sorted(str(item.get("source_id")) for item in sources))
    if source_ids != EXPECTED_SOURCE_IDS:
        raise ValueError("CAPTAINCOOK4D_SOURCE_SET_INVALID")
    for source in sources:
        source_id = str(source["source_id"])
        if source.get("source_group_id") != EXPECTED_SOURCE_GROUPS[source_id]:
            raise ValueError("SOURCE_GROUP_BINDING_INVALID")
        leads = source.get("candidate_leads")
        if not isinstance(leads, list) or len(leads) != 2:
            raise ValueError(f"EXACTLY_TWO_LEADS_REQUIRED:{source_id}")
        if [item.get("lead_ordinal") for item in leads] != [1, 2]:
            raise ValueError("LEAD_ORDINALS_MUST_BE_ONE_AND_TWO")
        for lead in leads:
            if lead.get("source_id") != source_id:
                raise ValueError("LEAD_SOURCE_BINDING_INVALID")
            if lead.get("source_group_id") != source["source_group_id"]:
                raise ValueError("LEAD_SOURCE_GROUP_BINDING_INVALID")
            if lead.get("current_tier") not in P_TIERS:
                raise ValueError("INVALID_P_TIER")
            hypotheses = lead.get("observation_hypotheses")
            if not isinstance(hypotheses, Mapping):
                raise TypeError("OBSERVATION_HYPOTHESES_REQUIRED")
            if tuple(sorted(hypotheses)) != tuple(sorted(OBSERVATION_CLASSES)):
                raise ValueError("FOUR_WAY_OBSERVATION_CLASSIFICATION_REQUIRED")
            validate_hop_structure(lead.get("hop_structure", {}))
            risks = lead.get("risk_flags")
            if not isinstance(risks, Mapping):
                raise TypeError("RISK_FLAGS_REQUIRED")
            for key in (
                "recurrence",
                "people_leakage",
                "environment_leakage",
                "speech_asr_substitute",
                "caption_ocr_text_substitute",
            ):
                if key not in risks:
                    raise ValueError(f"RISK_FLAG_MISSING:{key}")
            template = lead.get("task145_cbrn_template")
            if not isinstance(template, Mapping):
                raise TypeError("TASK145_TEMPLATE_REQUIRED")
            if template.get("template_only_not_executed") is not True:
                raise ValueError("TASK145_TEMPLATE_MUST_BE_INERT")
            if template.get("active_intervention") is not False:
                raise ValueError("TASK145_ACTIVE_INTERVENTION_FORBIDDEN")
            if tuple(template.get("states", ())) != (
                "CLEAN",
                "BLOCKED",
                "RESTORED",
                "NO_TRIGGER",
            ):
                raise ValueError("TASK145_STATE_SET_INVALID")
            _validate_inspection(lead, mode=str(mode))
            copy = dict(lead)
            stored = copy.pop("candidate_hash", None)
            if stored != json_hash(copy):
                raise ValueError("CANDIDATE_HASH_INVALID")
    counts = Counter(
        str(lead["source_id"])
        for source in sources
        for lead in source["candidate_leads"]
    )
    if counts != Counter({source_id: 2 for source_id in EXPECTED_SOURCE_IDS}):
        raise ValueError("EXACTLY_SIX_LEADS_REQUIRED")
    gate = registry.get("gate_a_boundary")
    if not isinstance(gate, Mapping):
        raise TypeError("GATE_A_BOUNDARY_REQUIRED")
    if gate.get("gate_a_decision_asserted") is not False:
        raise ValueError("GATE_A_DECISION_MUST_NOT_BE_ASSERTED")
    if mode == "development_only":
        if gate.get("eligible_to_enter_gate_a") is not False:
            raise ValueError("DEVELOPMENT_OUTPUT_MUST_NOT_ENTER_GATE_A")
        if gate.get("development_only_outputs_permanently_ineligible") is not True:
            raise ValueError("DEVELOPMENT_PERMANENT_INELIGIBILITY_REQUIRED")
        if registry.get("human_task153_prescreen_complete") is not False:
            raise ValueError("DEVELOPMENT_PRESCREEN_STATUS_INVALID")
    else:
        if registry.get("human_task153_prescreen_complete") is not True:
            raise ValueError("GATE_A_MODE_REQUIRES_TASK153_PRESCREEN")
    copy = dict(registry)
    stored = copy.pop("registry_hash", None)
    if stored != json_hash(copy):
        raise ValueError("REGISTRY_HASH_INVALID")
    assert_machine_expert_provisional_only(registry)


__all__ = [
    "ALLOWED_COMPOSITION_OPERATORS",
    "ALLOWED_MODES",
    "ARTIFACT_CLASS",
    "EXPECTED_SOURCE_GROUPS",
    "EXPECTED_SOURCE_IDS",
    "OBSERVATION_CLASSES",
    "P_TIERS",
    "SCHEMA_VERSION",
    "assert_machine_expert_provisional_only",
    "canonical_bytes",
    "json_hash",
    "validate_candidate_registry",
    "validate_hop_structure",
]
