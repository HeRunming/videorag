"""Human-gated authoring assistance and inert Task-145 templates."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .adapters import EpicIndexInputs, PrescreenBundle, PrescreenSourceGate
from .contracts import SCHEMA_VERSION, json_hash, validate_candidate_registry


def task145_cbrn_template() -> dict[str, Any]:
    """Return the frozen exogenous C/B/R/N planning template."""
    return {
        "protocol_version": "exogenous-restoration-protocol-v2",
        "template_only_not_executed": True,
        "active_intervention": False,
        "intervention_executed": False,
        "scientific_execution_authorized": False,
        "mechanism_selection_status": (
            "UNASSIGNED_REQUIRES_LATER_HUMAN_CONSTRUCT_REVIEW"
        ),
        "allowed_mechanisms": [
            {
                "mechanism": "SILENT_ROUTE_WITHHOLDING",
                "visibility": "no_explicit_outage_marker",
                "primary_estimand_id": (
                    "P1_RN_SILENT_ROUTE_WITHHOLDING_ITT"
                ),
            },
            {
                "mechanism": "EXPLICIT_CHANNEL_OUTAGE",
                "visibility": "frozen_typed_unavailable_response",
                "primary_estimand_id": (
                    "P2_RN_EXPLICIT_CHANNEL_OUTAGE_ITT"
                ),
            },
        ],
        "primary_schedule": {
            "trigger_class": "fixed_action_index",
            "index_base": "zero",
            "action_index": 4,
            "delivery_boundary": (
                "after_four_completed_action_response_cycles_before_next_"
                "model_decision"
            ),
            "depends_on_action_identity": False,
            "depends_on_system_identity": False,
            "depends_on_output_or_correctness": False,
            "depends_on_get_channel_status": False,
            "checkpoint_event": {
                "event_type": "protocol_checkpoint",
                "event_version": "2.0.0",
                "message": "Scheduled protocol checkpoint completed.",
                "cost": 0.0,
                "public_bytes_identical_r_n": True,
                "reveals_restoration": False,
            },
        },
        "states": ("CLEAN", "BLOCKED", "RESTORED", "NO_TRIGGER"),
        "state_templates": {
            "CLEAN": {
                "scheduled_event": "none",
                "route_state": "candidate_route_available",
            },
            "BLOCKED": {
                "scheduled_event": "none",
                "route_state": "candidate_route_inaccessible",
            },
            "RESTORED": {
                "scheduled_event": "checkpoint_with_hidden_restoration",
                "initial_access": "identical_to_blocked_prefix",
            },
            "NO_TRIGGER": {
                "scheduled_event": (
                    "byte_identical_checkpoint_without_restoration"
                ),
                "initial_access": "identical_to_restored_prefix",
            },
        },
        "paired_prefix": {
            "construction": "single_blocked_prefix_then_fresh_replayed_fork",
            "public_transcript_identical_through_event": True,
            "r_n_prefix_plus_event_hash_match_required": True,
            "fresh_continuation_sessions": True,
            "early_terminal_policy": (
                "retain_both_assignments_copy_terminal_prefix_no_post_"
                "terminal_event"
            ),
        },
        "analysis_boundary": {
            "primary_contrast": "RESTORED_minus_NO_TRIGGER",
            "population": "all_preregistered_assignments_intention_to_treat",
            "mechanism_specific_only": True,
            "pooled_primary_allowed": False,
            "restored_minus_blocked_role": (
                "secondary_mechanism_specific_state_contrast"
            ),
            "get_channel_status_role": (
                "SECONDARY_PER_PROTOCOL_ACTION_CONTINGENT"
            ),
        },
    }


def _overlap_us(
    interval: Mapping[str, Any], start_us: int, end_us: int
) -> bool:
    lead_start = round(float(interval["start_s"]) * 1_000_000)
    lead_end = round(float(interval["end_s"]) * 1_000_000)
    return max(lead_start, start_us) < min(lead_end, end_us)


def _prescreen_links(
    lead: Mapping[str, Any], gate: PrescreenSourceGate | None
) -> dict[str, Any]:
    if gate is None:
        return {
            "human_complete_source_prescreen": False,
            "source_dynamic_visual_event_count": 0,
            "source_non_speech_event_count": 0,
            "dynamic_visual_observation_ids": [],
            "non_speech_observation_ids": [],
            "candidate_fact_ids": [],
            "candidate_facts": [],
            "authoring_constraints": [],
        }
    intervals = [lead["primary_interval"]]
    composition = lead.get("hop_structure", {}).get("composition")
    if isinstance(composition, Mapping):
        intervals = [
            item["interval"]
            for item in composition.get("component_claim_placeholders", ())
        ]
    matched = [
        item
        for item in gate.observations
        if any(_overlap_us(interval, item.start_us, item.end_us) for interval in intervals)
    ]
    fact_ids = sorted(
        {
            fact_id
            for observation in matched
            for fact_id in observation.candidate_fact_ids
        }
    )
    facts = [
        dict(item)
        for item in gate.candidate_facts
        if str(item.get("fact_id")) in fact_ids
    ]
    return {
        "human_complete_source_prescreen": True,
        "source_dynamic_visual_event_count": sum(
            item.modality == "dynamic_nontext_visual"
            for item in gate.observations
        ),
        "source_non_speech_event_count": sum(
            item.modality == "non_speech" for item in gate.observations
        ),
        "dynamic_visual_observation_ids": sorted(
            item.observation_id
            for item in matched
            if item.modality == "dynamic_nontext_visual"
        ),
        "non_speech_observation_ids": sorted(
            item.observation_id
            for item in matched
            if item.modality == "non_speech"
        ),
        "candidate_fact_ids": fact_ids,
        "candidate_facts": facts,
        "authoring_constraints": list(gate.authoring_constraints),
    }


def _question_blueprints(
    lead: Mapping[str, Any], links: Mapping[str, Any]
) -> list[dict[str, Any]]:
    hypotheses = lead["observation_hypotheses"]
    blueprints = []
    if hypotheses["dynamic_nontext_visual"]["status"] == "MACHINE_HYPOTHESIS":
        dynamic_unlocked = bool(links["source_dynamic_visual_event_count"])
        blueprints.append(
            {
                "route": "dynamic_nontext_visual",
                "authoring_status": (
                    "AVAILABLE_AFTER_HUMAN_PRESCREEN"
                    if dynamic_unlocked
                    else "BLOCKED_PENDING_OVERLAPPING_HUMAN_PRESCREEN"
                ),
                "question_placeholder": (
                    (
                        "What visible state change occurs in [interval], and "
                        "what immediately observable manipulation produces it?"
                    )
                    if dynamic_unlocked
                    else None
                ),
                "answer_placeholder": (
                    (
                        "[Human author: describe the before/action/after event "
                        "without relying on readable text, overlays, or narration.]"
                    )
                    if dynamic_unlocked
                    else None
                ),
            }
        )
    if hypotheses["non_speech"]["status"] == "MACHINE_AST_HYPOTHESIS":
        ambient_unlocked = bool(links["source_non_speech_event_count"])
        blueprints.append(
            {
                "route": "non_speech",
                "authoring_status": (
                    "AVAILABLE_AFTER_HUMAN_PRESCREEN"
                    if ambient_unlocked
                    else "BLOCKED_PENDING_OVERLAPPING_HUMAN_PRESCREEN"
                ),
                "question_placeholder": (
                    (
                        "What concrete non-speech event is audible in [interval], "
                        "and what event context disambiguates it?"
                    )
                    if ambient_unlocked
                    else None
                ),
                "answer_placeholder": (
                    (
                        "[Human author: identify the sound only after listening; "
                        "AST class names are routing hints, not the answer.]"
                    )
                    if ambient_unlocked
                    else None
                ),
            }
        )
    if hypotheses["speech"]["status"] == "MACHINE_ASR_HYPOTHESIS":
        blueprints.append(
            {
                "route": "speech",
                "authoring_status": (
                    "AVAILABLE_PENDING_TRANSCRIPT_NARRATION_ROUTE_CLOSURE"
                ),
                "question_placeholder": (
                    "What event-relevant statement is spoken in [interval], "
                    "and which source event does it clarify?"
                ),
                "answer_placeholder": (
                    "[Human author: verify speech from audio and close ASR, "
                    "transcript, OCR, and narration substitutes.]"
                ),
            }
        )
    if not blueprints:
        blueprints.append(
            {
                "route": "unresolved",
                "authoring_status": "BLOCKED_PENDING_HUMAN_INSPECTION",
                "question_placeholder": (
                    "[Human author: inspect the interval and decide whether a "
                    "substantive event-centric question exists.]"
                ),
                "answer_placeholder": (
                    "[No semantic answer may be inferred from routing scores.]"
                ),
            }
        )
    return blueprints


def _human_fact_scaffolds(links: Mapping[str, Any]) -> list[dict[str, Any]]:
    output = []
    for fact in links["candidate_facts"]:
        carriers = [
            modality
            for modality, value in fact.get("carried_by", {}).items()
            if isinstance(value, Mapping) and value.get("carries_fact") is True
        ]
        output.append(
            {
                "fact_id": str(fact["fact_id"]),
                "human_prescreened_fact_statement": str(
                    fact["fact_statement"]
                ),
                "declared_carriers": sorted(carriers),
                "question_draft_status": (
                    "AUTHOR_MUST_DRAFT_AND_SHORTCUT_CHALLENGE"
                ),
                "suggested_question_shape": (
                    "Ask for the event relation or state transition that "
                    "supports this fact; do not copy the fact statement into "
                    "the question."
                ),
                "accepted_family_or_answer": False,
            }
        )
    return output


def _authoring_gate(
    lead: Mapping[str, Any],
    *,
    mode: str,
    links: Mapping[str, Any],
) -> dict[str, Any]:
    hypotheses = lead["observation_hypotheses"]
    requires_dynamic = (
        hypotheses["dynamic_nontext_visual"]["status"] == "MACHINE_HYPOTHESIS"
    )
    requires_ambient = (
        hypotheses["non_speech"]["status"] == "MACHINE_AST_HYPOTHESIS"
    )
    blockers = []
    if mode == "development_only":
        blockers.append("DEVELOPMENT_ONLY_OUTPUT_CANNOT_ENTER_GATE_A")
    if not links["human_complete_source_prescreen"]:
        blockers.append("HUMAN_COMPLETE_SEMANTIC_PRESCREEN_REQUIRED")
    if requires_dynamic and not links["source_dynamic_visual_event_count"]:
        blockers.append("DYNAMIC_VISUAL_REQUIRES_POSITIVE_HUMAN_PRESCREEN")
    if requires_ambient and not links["source_non_speech_event_count"]:
        blockers.append("AMBIENT_REQUIRES_POSITIVE_HUMAN_PRESCREEN")
    if hypotheses["board_ocr_static_overlay"]["status"] == (
        "MACHINE_SUBSTITUTE_RISK"
    ):
        blockers.append("BOARD_OCR_STATIC_OVERLAY_ROUTE_MUST_BE_CLOSED")
    return {
        "human_authoring_may_begin": not blockers,
        "eligible_for_gate_a_input_review": (
            mode == "gate_a_candidate_input" and not blockers
        ),
        "gate_a_decision_asserted": False,
        "blockers": blockers,
        "ambient_and_dynamic_visual_require_human_prescreen": True,
    }


def _attach_authoring(
    lead: Mapping[str, Any],
    *,
    mode: str,
    gate: PrescreenSourceGate | None,
) -> dict[str, Any]:
    output = dict(lead)
    links = _prescreen_links(output, gate)
    output["authoring_assistance"] = {
        "semantic_status": "PROPOSAL_NOT_ACCEPTED_FAMILY",
        "question_blueprints": _question_blueprints(output, links),
        "human_fact_scaffolds": _human_fact_scaffolds(links),
        "human_prescreen_links": links,
        "authoring_gate": _authoring_gate(output, mode=mode, links=links),
        "required_human_actions": [
            "inspect the source interval rather than trusting CLIP/AST/ASR labels",
            "classify dynamic non-text vision separately from board/OCR/static/overlay",
            "close transcript, OCR, caption, narration, and repeated-event routes",
            "verify participant and kitchen clues cannot leak the source group",
            "reject multi-hop unless every component is required by one composed claim",
            "do not consult the existing EPIC annotation vault during initial authoring",
        ],
    }
    output["task145_cbrn_template"] = task145_cbrn_template()
    output["candidate_hash"] = json_hash(output)
    return output


def build_candidate_registry(
    inputs: EpicIndexInputs,
    machine_leads: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    mode: str,
    prescreen: PrescreenBundle | None,
    created_date: str,
) -> dict[str, Any]:
    """Attach authoring assistance after initial machine-only mining."""
    if mode == "gate_a_candidate_input" and prescreen is None:
        raise ValueError("HUMAN_COMPLETE_PRESCREEN_REQUIRED")
    sources = []
    all_leads = []
    for source_id in sorted(inputs.source_hashes):
        leads = list(machine_leads.get(source_id, ()))
        if len(leads) != 2:
            raise ValueError(f"EXACTLY_TWO_MACHINE_LEADS_REQUIRED:{source_id}")
        gate = prescreen.sources[source_id] if prescreen is not None else None
        attached = [
            _attach_authoring(item, mode=mode, gate=gate) for item in leads
        ]
        all_leads.extend(attached)
        sources.append(
            {
                "source_id": source_id,
                "source_group_id": inputs.source_groups[source_id],
                "participant_blocked_split_required": True,
                "candidate_lead_count": 2,
                "candidate_leads": attached,
            }
        )
    gate_eligible = (
        mode == "gate_a_candidate_input"
        and all(
            lead["authoring_assistance"]["authoring_gate"][
                "eligible_for_gate_a_input_review"
            ]
            for lead in all_leads
        )
    )
    registry = {
        "schema_version": SCHEMA_VERSION,
        "registry_id": "epic-wave1-family-candidate-leads-v1",
        "registry_kind": "MACHINE_PROVISIONAL_EPIC_EVENT_LEADS",
        "created_date": created_date,
        "mode": mode,
        "status": "PROPOSALS_ONLY_NOT_HUMAN_VALIDATED_NOT_ACCEPTED",
        "input_provenance": {
            "canonical_index": dict(inputs.provenance),
            "human_prescreen": (
                dict(prescreen.provenance)
                if prescreen is not None
                else {
                    "human_complete": False,
                    "status": "NOT_SUPPLIED_DEVELOPMENT_ONLY",
                }
            ),
            "initial_mining_input_classes": [
                "OpenCV visual change/routing observations",
                "CLIP visual embeddings",
                "Whisper ASR observations",
                "AST AudioSet observations",
            ],
            "semantic_epic_action_narration_epic_sounds_labels_used": False,
            "existing_annotation_vault_accessed": False,
        },
        "sources": sources,
        "summary": {
            "source_count": 2,
            "candidate_lead_count": 4,
            "exactly_two_leads_per_source": True,
            "p_tier_only": True,
            "h_tier_count": 0,
            "active_intervention_count": 0,
            "human_prescreen_complete": prescreen is not None,
            "development_only": mode == "development_only",
        },
        "gate_a_boundary": {
            "eligible_to_enter_gate_a": gate_eligible,
            "gate_a_decision_asserted": False,
            "gate_a_authority_conferred": False,
            "development_only_outputs_permanently_ineligible": (
                mode == "development_only"
            ),
        },
        "prohibitions": {
            "H1_or_H2_assignment": True,
            "active_intervention_execution": True,
            "semantic_epic_annotation_use_during_initial_mining": True,
            "existing_annotation_vault_access": True,
            "one_hop_far": True,
            "multi_hop_by_distinct_interval_count_only": True,
            "machine_scores_as_semantic_evidence": True,
        },
    }
    registry["registry_hash"] = json_hash(registry)
    validate_candidate_registry(registry)
    return registry


__all__ = ["build_candidate_registry", "task145_cbrn_template"]
