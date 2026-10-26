"""Provisional authoring assistance and inert Task145 templates."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .adapters import (
    CaptainCook4DIndexInputs,
    PrescreenBundle,
    PrescreenSourceGate,
)
from .contracts import (
    ARTIFACT_CLASS,
    SCHEMA_VERSION,
    json_hash,
    validate_candidate_registry,
)
from .inspection import (
    direct_inspection_assistance,
    unexecuted_inspection_scaffold,
)


def task145_cbrn_template() -> dict[str, Any]:
    """Return the inert Task145 v2 C/B/R/N structure."""
    return {
        "protocol_version": "exogenous-restoration-protocol-v2",
        "template_only_not_executed": True,
        "active_intervention": False,
        "intervention_executed": False,
        "scientific_execution_authorized": False,
        "mechanism_selection_status": (
            "UNASSIGNED_REQUIRES_LATER_HUMAN_CONSTRUCT_REVIEW"
        ),
        "states": ("CLEAN", "BLOCKED", "RESTORED", "NO_TRIGGER"),
        "primary_schedule": {
            "trigger_class": "fixed_action_index",
            "index_base": "zero",
            "action_index": 4,
            "delivery_boundary": (
                "after_four_completed_action_response_cycles_before_next_"
                "model_decision"
            ),
            "depends_on_system_identity": False,
            "depends_on_action_identity": False,
            "depends_on_output_or_correctness": False,
            "depends_on_get_channel_status": False,
        },
        "paired_prefix": {
            "single_blocked_prefix_replayed_into_fresh_r_n": True,
            "public_transcript_identical_through_event": True,
            "r_n_public_checkpoint_bytes_identical": True,
        },
        "analysis_boundary": {
            "primary_contrast": "RESTORED_minus_NO_TRIGGER",
            "population": "intention_to_treat",
            "mechanism_specific_only": True,
            "pooled_primary_allowed": False,
            "restored_minus_blocked_secondary_only": True,
            "get_channel_status_role": (
                "SECONDARY_PER_PROTOCOL_ACTION_CONTINGENT"
            ),
        },
    }


def _overlap(
    interval: Mapping[str, Any], start_us: int, end_us: int
) -> bool:
    left = round(float(interval["start_s"]) * 1_000_000)
    right = round(float(interval["end_s"]) * 1_000_000)
    return max(left, start_us) < min(right, end_us)


def _prescreen_links(
    lead: Mapping[str, Any], gate: PrescreenSourceGate | None
) -> dict[str, Any]:
    if gate is None:
        return {
            "human_complete_source_prescreen": False,
            "source_dynamic_visual_event_count": 0,
            "source_non_speech_event_count": 0,
            "overlapping_observation_ids": [],
            "candidate_facts": [],
            "recurrence_groups": [],
            "authoring_constraints": [],
        }
    composition = lead.get("hop_structure", {}).get("composition")
    intervals = (
        [item["interval"] for item in composition["components"]]
        if isinstance(composition, Mapping)
        else [lead["primary_interval"]]
    )
    matched = [
        item
        for item in gate.observations
        if any(_overlap(interval, item.start_us, item.end_us) for interval in intervals)
    ]
    fact_ids = {
        fact_id
        for item in matched
        for fact_id in item.candidate_fact_ids
    }
    return {
        "human_complete_source_prescreen": True,
        "source_dynamic_visual_event_count": sum(
            item.modality == "dynamic_nontext_visual"
            for item in gate.observations
        ),
        "source_non_speech_event_count": sum(
            item.modality == "non_speech" for item in gate.observations
        ),
        "overlapping_observation_ids": sorted(
            item.observation_id for item in matched
        ),
        "candidate_facts": [
            dict(item)
            for item in gate.candidate_facts
            if str(item.get("fact_id")) in fact_ids
        ],
        "recurrence_groups": [dict(item) for item in gate.recurrence_groups],
        "authoring_constraints": list(gate.authoring_constraints),
    }


def _authoring_gate(
    lead: Mapping[str, Any],
    *,
    mode: str,
    links: Mapping[str, Any],
) -> dict[str, Any]:
    blockers = []
    if mode == "development_only":
        blockers.append("DEVELOPMENT_ONLY_OUTPUT_CANNOT_ENTER_GATE_A")
    if not links["human_complete_source_prescreen"]:
        blockers.append("TASK153_HUMAN_PRESCREEN_REQUIRED_FOR_GATE_A")
    hypotheses = lead["observation_hypotheses"]
    if (
        hypotheses["dynamic_nontext_visual"]["status"] == "MACHINE_HYPOTHESIS"
        and not links["source_dynamic_visual_event_count"]
    ):
        blockers.append("DYNAMIC_VISUAL_REQUIRES_POSITIVE_TASK153_EVENT")
    if (
        hypotheses["non_speech"]["status"] == "MACHINE_AST_HYPOTHESIS"
        and not links["source_non_speech_event_count"]
    ):
        blockers.append("NON_SPEECH_REQUIRES_POSITIVE_TASK153_EVENT")
    return {
        "eligible_for_gate_a_input_review": (
            mode == "gate_a_candidate_input" and not blockers
        ),
        "gate_a_decision_asserted": False,
        "blockers": blockers,
        "development_authoring_assistance_available": mode == "development_only",
    }


def _attach_authoring(
    lead: Mapping[str, Any],
    *,
    mode: str,
    gate: PrescreenSourceGate | None,
    media_path: Path,
    run_direct_inspection: bool,
) -> dict[str, Any]:
    output = dict(lead)
    links = _prescreen_links(output, gate)
    inspection = (
        direct_inspection_assistance(media_path, output)
        if run_direct_inspection
        else unexecuted_inspection_scaffold(output)
    )
    output["authoring_assistance"] = {
        "semantic_status": ARTIFACT_CLASS,
        "bounded_direct_inspection": inspection,
        "task153_prescreen_links": links,
        "authoring_gate": _authoring_gate(output, mode=mode, links=links),
        "required_human_actions": [
            "complete Task153 trained-human source prescreen before Gate-A mode",
            "inspect every cited frame interval directly",
            "listen to every audio-bearing hypothesis before naming the sound",
            "close speech ASR caption OCR label and narration substitutes",
            "search the complete source for recurrence and near duplicates",
            "challenge person and environment identity leakage",
            "reject multi-hop unless all components support one composed claim",
            "do not consult CaptainCook4D action step task-graph recipe or error annotations",
        ],
    }
    output["task145_cbrn_template"] = task145_cbrn_template()
    output["candidate_hash"] = json_hash(output)
    return output


def build_candidate_registry(
    inputs: CaptainCook4DIndexInputs,
    machine_leads: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    mode: str,
    prescreen: PrescreenBundle | None,
    created_date: str,
    run_direct_inspection: bool,
) -> dict[str, Any]:
    """Attach bounded authoring assistance after machine-only mining."""
    if mode == "gate_a_candidate_input" and prescreen is None:
        raise ValueError("TASK153_HUMAN_PRESCREEN_REQUIRED_FOR_GATE_A")
    sources = []
    all_leads = []
    for source_id in sorted(inputs.source_hashes):
        leads = list(machine_leads.get(source_id, ()))
        if len(leads) != 2:
            raise ValueError(f"EXACTLY_TWO_MACHINE_LEADS_REQUIRED:{source_id}")
        gate = prescreen.sources[source_id] if prescreen is not None else None
        attached = [
            _attach_authoring(
                item,
                mode=mode,
                gate=gate,
                media_path=inputs.source_media_paths[source_id],
                run_direct_inspection=run_direct_inspection,
            )
            for item in leads
        ]
        sources.append(
            {
                "source_id": source_id,
                "source_group_id": inputs.source_groups[source_id],
                "person_and_environment_blocked_split_required": True,
                "candidate_lead_count": 2,
                "candidate_leads": attached,
            }
        )
        all_leads.extend(attached)
    gate_eligible = (
        mode == "gate_a_candidate_input"
        and all(
            item["authoring_assistance"]["authoring_gate"][
                "eligible_for_gate_a_input_review"
            ]
            for item in all_leads
        )
    )
    registry = {
        "schema_version": SCHEMA_VERSION,
        "registry_id": "captaincook4d-wave0-family-candidate-leads-v1",
        "registry_kind": (
            "MACHINE_EXPERT_PROVISIONAL_CAPTAINCOOK4D_EVENT_LEADS"
        ),
        "artifact_classification": ARTIFACT_CLASS,
        "created_date": created_date,
        "mode": mode,
        "status": "PROVISIONAL_NOT_HUMAN_VALIDATED_NOT_ACCEPTED",
        "human_task153_prescreen_complete": prescreen is not None,
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
                "OpenCV visual change and routing observations",
                "CLIP visual embeddings",
                "Whisper ASR observations",
                "AST AudioSet observations",
            ],
            "direct_authoring_input_classes": [
                "bounded raw local source frames",
                "bounded raw local source audio waveform metrics",
            ],
            "captaincook_semantic_annotations_used": False,
            "task_graphs_used": False,
            "error_labels_used": False,
        },
        "sources": sources,
        "summary": {
            "source_count": 3,
            "candidate_lead_count": 6,
            "exactly_two_leads_per_source": True,
            "p_tier_only": True,
            "h_tier_count": 0,
            "active_intervention_count": 0,
            "direct_inspection_run": run_direct_inspection,
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
            "necessity_or_minimality_claim": True,
            "active_intervention_execution": True,
            "captaincook_semantic_annotation_use": True,
            "task_graph_or_error_label_use": True,
            "one_hop_far": True,
            "multi_hop_by_interval_count_only": True,
            "machine_scores_as_semantic_evidence": True,
        },
    }
    registry["registry_hash"] = json_hash(registry)
    validate_candidate_registry(registry)
    return registry


__all__ = ["build_candidate_registry", "task145_cbrn_template"]
