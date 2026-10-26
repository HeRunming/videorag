"""Contracts for EPIC machine-provisional candidate mining."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from typing import Any

SCHEMA_VERSION = "av-trace.epic-family-mining/1.0"
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
    "instruction_or_intent_then_visible_execution",
    "audible_event_then_visible_state_change",
    "visible_action_then_resulting_state",
)
ALLOWED_MODES = ("gate_a_candidate_input", "development_only")


def canonical_bytes(value: Any) -> bytes:
    """Return stable JSON bytes used for self-hashes."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def json_hash(value: Any) -> str:
    """Return a prefixed SHA-256 over stable JSON."""
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def _walk(value: Any, location: str = "root"):
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_location = f"{location}.{key}"
            yield key, child, child_location
            yield from _walk(child, child_location)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, f"{location}[{index}]")


def assert_machine_provisional_only(value: Any) -> None:
    """Reject H tiers, accepted-family claims, or active interventions."""
    forbidden_true = {
        "human_reviewed",
        "human_validated",
        "human_gold",
        "h1_assigned",
        "h2_assigned",
        "human_minimality_asserted",
        "human_necessity_asserted",
        "final_accepted",
        "accepted_family",
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
    """Enforce one-hop/local and explicit compositional multi-hop semantics."""
    stratum = hop.get("hop_stratum")
    temporal = hop.get("temporal_stratum")
    composition = hop.get("composition")
    if stratum == "one_hop":
        if temporal != "near_local":
            raise ValueError("ONE_HOP_MUST_BE_NEAR_LOCAL")
        if composition is not None:
            raise ValueError("ONE_HOP_MUST_NOT_HAVE_COMPOSITION")
        return
    if stratum != "multi_hop":
        raise ValueError(f"INVALID_HOP_STRATUM:{stratum}")
    if not isinstance(composition, Mapping):
        raise TypeError("MULTI_HOP_REQUIRES_COMPOSITION_PLACEHOLDER")
    if composition.get("operator") not in ALLOWED_COMPOSITION_OPERATORS:
        raise ValueError("MULTI_HOP_COMPOSITION_OPERATOR_INVALID")
    components = composition.get("component_claim_placeholders")
    if not isinstance(components, list) or len(components) < 2:
        raise ValueError("MULTI_HOP_REQUIRES_TWO_COMPONENT_PLACEHOLDERS")
    if not str(composition.get("composed_claim_placeholder", "")).strip():
        raise ValueError("MULTI_HOP_COMPOSED_CLAIM_PLACEHOLDER_REQUIRED")
    if composition.get("arbitrary_distinct_interval_counting_forbidden") is not True:
        raise ValueError("MULTI_HOP_ARBITRARY_INTERVAL_PROHIBITION_REQUIRED")
    if composition.get("semantic_relation_human_validated") is not False:
        raise ValueError("MULTI_HOP_RELATION_MUST_REMAIN_UNVALIDATED")


def validate_candidate_registry(registry: Mapping[str, Any]) -> None:
    """Validate EPIC-specific output invariants."""
    if registry.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("REGISTRY_SCHEMA_VERSION_INVALID")
    if registry.get("mode") not in ALLOWED_MODES:
        raise ValueError("REGISTRY_MODE_INVALID")
    if registry.get("registry_kind") != "MACHINE_PROVISIONAL_EPIC_EVENT_LEADS":
        raise ValueError("REGISTRY_KIND_INVALID")
    sources = registry.get("sources")
    if not isinstance(sources, list) or len(sources) != 2:
        raise ValueError("REGISTRY_MUST_CONTAIN_TWO_EPIC_SOURCES")
    source_ids = [str(item.get("source_id")) for item in sources]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("DUPLICATE_SOURCE_ID")
    if tuple(sorted(source_ids)) != ("P27_101", "P28_103"):
        raise ValueError("EPIC_SOURCE_SET_INVALID")
    for source in sources:
        expected_group = {"P27_101": "P27", "P28_103": "P28"}[
            str(source["source_id"])
        ]
        if source.get("source_group_id") != expected_group:
            raise ValueError("EPIC_SOURCE_GROUP_INVALID")
        leads = source.get("candidate_leads")
        if not isinstance(leads, list) or len(leads) != 2:
            raise ValueError(
                f"EXACTLY_TWO_LEADS_REQUIRED:{source.get('source_id')}"
            )
        if [item.get("lead_ordinal") for item in leads] != [1, 2]:
            raise ValueError("LEAD_ORDINALS_MUST_BE_ONE_AND_TWO")
        for lead in leads:
            if lead.get("source_id") != source.get("source_id"):
                raise ValueError("LEAD_SOURCE_BINDING_INVALID")
            if lead.get("source_group_id") != source.get("source_group_id"):
                raise ValueError("LEAD_SOURCE_GROUP_BINDING_INVALID")
            if lead.get("current_tier") not in P_TIERS:
                raise ValueError(f"INVALID_P_TIER:{lead.get('current_tier')}")
            hypotheses = lead.get("observation_hypotheses")
            if not isinstance(hypotheses, Mapping):
                raise TypeError("OBSERVATION_HYPOTHESES_REQUIRED")
            if tuple(sorted(hypotheses)) != tuple(sorted(OBSERVATION_CLASSES)):
                raise ValueError("FOUR_WAY_OBSERVATION_CLASSIFICATION_REQUIRED")
            validate_hop_structure(lead.get("hop_structure", {}))
            intervention = lead.get("task145_cbrn_template", {})
            if intervention.get("template_only_not_executed") is not True:
                raise ValueError("TASK145_TEMPLATE_MUST_BE_INERT")
            if intervention.get("active_intervention") is not False:
                raise ValueError("ACTIVE_INTERVENTION_FORBIDDEN")
            if tuple(intervention.get("states", ())) != (
                "CLEAN",
                "BLOCKED",
                "RESTORED",
                "NO_TRIGGER",
            ):
                raise ValueError("TASK145_CBRN_STATES_INVALID")
            copy = dict(lead)
            stored_candidate_hash = copy.pop("candidate_hash", None)
            if stored_candidate_hash != json_hash(copy):
                raise ValueError("CANDIDATE_HASH_INVALID")
    counts = Counter(
        str(lead["current_tier"])
        for source in sources
        for lead in source["candidate_leads"]
    )
    if sum(counts.values()) != 4:
        raise ValueError("TOTAL_LEAD_COUNT_MUST_BE_FOUR")
    gate = registry.get("gate_a_boundary", {})
    if gate.get("gate_a_decision_asserted") is not False:
        raise ValueError("GATE_A_DECISION_MUST_NOT_BE_ASSERTED")
    if (
        registry["mode"] == "development_only"
        and gate.get("eligible_to_enter_gate_a") is not False
    ):
        raise ValueError("DEVELOPMENT_OUTPUT_MUST_NOT_ENTER_GATE_A")
    if registry["mode"] == "development_only":
        if gate.get("development_only_outputs_permanently_ineligible") is not True:
            raise ValueError("DEVELOPMENT_OUTPUT_PERMANENT_INELIGIBILITY_REQUIRED")
        if gate.get("gate_a_authority_conferred") is not False:
            raise ValueError("DEVELOPMENT_OUTPUT_GATE_A_AUTHORITY_FORBIDDEN")
        summary = registry.get("summary", {})
        if summary.get("development_only") is not True:
            raise ValueError("DEVELOPMENT_OUTPUT_SUMMARY_MARKER_REQUIRED")
        if summary.get("human_prescreen_complete") is not False:
            raise ValueError("DEVELOPMENT_OUTPUT_HUMAN_PRESCREEN_MUST_BE_FALSE")
        prescreen = registry.get("input_provenance", {}).get(
            "human_prescreen", {}
        )
        if prescreen.get("human_complete") is not False:
            raise ValueError("DEVELOPMENT_OUTPUT_HUMAN_PRESCREEN_PROVENANCE_INVALID")
        for source in sources:
            for lead in source["candidate_leads"]:
                authoring_gate = lead.get("authoring_assistance", {}).get(
                    "authoring_gate", {}
                )
                if authoring_gate.get("eligible_for_gate_a_input_review") is not False:
                    raise ValueError("DEVELOPMENT_LEAD_GATE_A_REVIEW_FORBIDDEN")
                if "DEVELOPMENT_ONLY_OUTPUT_CANNOT_ENTER_GATE_A" not in (
                    authoring_gate.get("blockers") or ()
                ):
                    raise ValueError("DEVELOPMENT_LEAD_GATE_A_BLOCKER_REQUIRED")
    copy = dict(registry)
    stored_registry_hash = copy.pop("registry_hash", None)
    if stored_registry_hash != json_hash(copy):
        raise ValueError("REGISTRY_HASH_INVALID")
    assert_machine_provisional_only(registry)


__all__ = [
    "ALLOWED_COMPOSITION_OPERATORS",
    "ALLOWED_MODES",
    "HUMAN_TIER_MARKERS",
    "OBSERVATION_CLASSES",
    "P_TIERS",
    "SCHEMA_VERSION",
    "assert_machine_provisional_only",
    "canonical_bytes",
    "json_hash",
    "validate_candidate_registry",
    "validate_hop_structure",
]
