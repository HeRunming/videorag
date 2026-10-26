"""Deterministic rehearsal-plan construction."""

from __future__ import annotations

from typing import Any

from .contracts import SCHEMA_VERSION, json_hash
from .mining import DYNAMIC_VISUAL_PROMPTS, STATIC_TEXT_VISUAL_PROMPTS


def build_rehearsal_plan() -> dict[str, Any]:
    """Return the committed, non-executing EPIC mining plan."""
    sources = [
        {"source_id": "P27_101", "source_group_id": "P27"},
        {"source_id": "P28_103", "source_group_id": "P28"},
    ]
    slots = []
    for source in sources:
        for ordinal, role in (
            (1, "highest_scoring_local_event"),
            (2, "compositional_event_sequence_or_local_fallback"),
        ):
            slots.append(
                {
                    **source,
                    "lead_ordinal": ordinal,
                    "selection_role": role,
                    "candidate_generated": False,
                    "h_tier_allowed": False,
                    "active_intervention_allowed": False,
                }
            )
    plan = {
        "schema_version": SCHEMA_VERSION,
        "plan_id": "AV-TRACE-EPIC-FAMILY-MINING-V1",
        "created_date": "2026-09-28",
        "plan_kind": "IMPLEMENTATION_REHEARSAL_NOT_EXECUTED",
        "execution_status": {
            "canonical_index_complete_at_implementation_time": False,
            "mining_executed_by_task165": False,
            "candidate_artifact_written_by_task165": False,
            "active_index_output_or_checkpoints_touched": False,
        },
        "authoritative_inputs": [
            "orchestration/results/144_mini_pilot_candidate_scientific_audit.txt",
            "orchestration/results/145_exogenous_restoration_protocol.txt",
            "orchestration/results/149_cvpr_pivot_v2_addendum.txt",
            "orchestration/results/153_semantic_av_source_prescreen_tooling.txt",
            "orchestration/results/159_development_family_authoring_rehearsal.txt",
            "orchestration/results/161_assembly_epic_access_preflight_v2.txt",
            "orchestration/results/162_epic_wave1_exact_acquisition.txt",
            "orchestration/results/163_epic_wave1_index_implementation.txt",
            "Task 164 active index execution; result not available during implementation",
            "src/av_trace_mini_pilot_families/",
        ],
        "canonical_input": {
            "index_root": "data/restricted/epic_wave1_index_v1",
            "required_artifacts": [
                "segment_manifest.json",
                "observation_manifest.json",
                "full_timeline_index.json",
                "resource_manifest.json",
                "build_manifest.json",
            ],
            "required_build_status": "COMPLETE",
            "required_mode": "full",
            "smoke_forbidden": True,
            "required_source_ids": ["P27_101", "P28_103"],
            "required_checkpoint_count": 8,
            "complete_before_mining": True,
        },
        "initial_mining": {
            "allowed_observations": [
                "OpenCV motion/change and nonsemantic routing features",
                "frozen CLIP embeddings queried with generic event prompts",
                "frozen Whisper ASR observations",
                "frozen AST AudioSet observations",
            ],
            "forbidden_inputs": [
                "EPIC action segments and verb/noun labels",
                "EPIC narrations and narration timestamps",
                "EPIC-SOUNDS classes descriptions and timestamps",
                "benchmark splits prior questions features and outcomes",
                "any existing-annotation vault",
            ],
            "visual_dynamic_prompts": list(DYNAMIC_VISUAL_PROMPTS),
            "visual_static_text_prompts": list(STATIC_TEXT_VISUAL_PROMPTS),
            "machine_scores_are_semantic_evidence": False,
        },
        "observation_classes": [
            "dynamic_nontext_visual",
            "board_ocr_static_overlay",
            "speech",
            "non_speech",
        ],
        "lead_structure": {
            "source_count": 2,
            "candidate_leads_per_source": 2,
            "total_candidate_leads": 4,
            "slots": slots,
            "one_hop_implies_near_local": True,
            "multi_hop_requires_compositional_claim_placeholders": True,
            "arbitrary_distinct_interval_counting_forbidden": True,
            "quota_forcing_forbidden": True,
        },
        "human_prescreen_gate": {
            "normal_mode_requires": [
                "Task-153 plan with semantic_labels_present=false",
                "completed trained-human annotation form",
                "valid READY import report",
                "source-level pass and exposure_recorded=true",
            ],
            "dynamic_visual_authoring_requires_positive_human_source_event": True,
            "ambient_authoring_requires_positive_human_source_event": True,
            "candidate_interval_overlap_strengthens_scaffolding_but_is_not_validation": True,
            "prescreen_assigns_necessity_or_h_tier": False,
        },
        "modes": {
            "gate_a_candidate_input": {
                "complete_index_required": True,
                "human_complete_prescreen_required": True,
                "gate_a_decision_conferred": False,
            },
            "development_only": {
                "complete_index_required": True,
                "human_complete_prescreen_required": False,
                "proposals_may_be_emitted": True,
                "eligible_to_enter_gate_a": False,
                "future_test_eligible": False,
            },
        },
        "risk_flags_required": [
            "repeated events and near duplicates",
            "participant lineage leakage",
            "kitchen identity leakage",
            "transcript substitute",
            "OCR/static/overlay substitute",
            "narration substitute",
            "existing-annotation vault prohibition",
        ],
        "task145_template": {
            "states": ["CLEAN", "BLOCKED", "RESTORED", "NO_TRIGGER"],
            "fixed_zero_based_action_index": 4,
            "r_n_public_checkpoint_bytes_identical": True,
            "primary_contrast": "RESTORED_minus_NO_TRIGGER",
            "template_only_not_executed": True,
            "active_interventions": False,
        },
        "output_boundary": {
            "tiers": [
                "P0_MACHINE_CANDIDATE",
                "P1_MACHINE_CROSS_VALIDATED",
                "P2_MACHINE_COUNTERFACTUAL_VALIDATED",
            ],
            "H_tiers": False,
            "accepted_families": False,
            "scientific_execution_authorized": False,
            "default_output_root": (
                "data/restricted/epic_family_candidates_v1"
            ),
        },
    }
    plan["plan_hash"] = json_hash(plan)
    return plan


__all__ = ["build_rehearsal_plan"]
