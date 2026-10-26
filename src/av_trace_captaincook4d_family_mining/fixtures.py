"""Deterministic Task190 implementation plan."""

from __future__ import annotations

from .contracts import EXPECTED_SOURCE_GROUPS, EXPECTED_SOURCE_IDS, json_hash


def build_rehearsal_plan() -> dict:
    """Return the committed, not-executed Task190 plan."""
    slots = []
    for source_id in EXPECTED_SOURCE_IDS:
        for ordinal, role in (
            (1, "strongest_dynamic_procedure_event"),
            (
                2,
                "coherent_compositional_multihop_or_distinct_local_fallback",
            ),
        ):
            slots.append(
                {
                    "source_id": source_id,
                    "source_group_id": EXPECTED_SOURCE_GROUPS[source_id],
                    "lead_ordinal": ordinal,
                    "selection_role": role,
                    "candidate_generated": False,
                    "h_tier_allowed": False,
                    "active_intervention_allowed": False,
                }
            )
    plan = {
        "schema_version": "av-trace.captaincook4d-family-mining-plan/1.0",
        "plan_id": "AV-TRACE-CAPTAINCOOK4D-FAMILY-MINING-V1",
        "created_date": "2026-10-10",
        "task_id": 190,
        "plan_kind": "IMPLEMENTATION_REHEARSAL_NOT_EXECUTED",
        "authoritative_inputs": [
            "orchestration/results/144_mini_pilot_candidate_scientific_audit.txt",
            "orchestration/results/145_exogenous_restoration_protocol.txt",
            "orchestration/results/149_cvpr_pivot_v2_addendum.txt",
            "orchestration/results/153_semantic_av_source_prescreen_tooling.txt",
            "orchestration/results/165_epic_family_mining_implementation.txt",
            "orchestration/results/166_epic_family_candidates_dev_execution.txt",
            "orchestration/results/167_epic_substantive_authoring_dev.txt",
            "orchestration/results/188_captaincook4d_wave0_acquisition_v3.txt",
            "Task189 canonical CaptainCook4D Wave-0 full-timeline result and index",
        ],
        "canonical_input": {
            "task189_ready_token_required": (
                "CAPTAINCOOK4D_WAVE0_FULL_TIMELINE_READY"
            ),
            "task189_result_path": (
                "orchestration/results/"
                "189_captaincook4d_wave0_full_timeline.txt"
            ),
            "index_root": "data/restricted/captaincook4d_wave0_index_v1",
            "index_plan": (
                "data/rehearsal_plan/"
                "captaincook4d_wave0_full_timeline_index_v1.json"
            ),
            "required_mode": "full",
            "smoke_forbidden": True,
            "required_source_ids": list(EXPECTED_SOURCE_IDS),
            "required_checkpoint_count": 12,
            "complete_before_mining": True,
        },
        "execution_status": {
            "task189_ready_at_task190_implementation_time": False,
            "mining_executed_by_task190": False,
            "candidate_artifact_written_by_task190": False,
            "active_index_output_or_checkpoints_touched": False,
            "raw_media_inspection_run_by_task190": False,
        },
        "initial_mining": {
            "allowed_observations": [
                "canonical OpenCV visual routing/change observations",
                "canonical frozen CLIP embeddings with generic procedure prompts",
                "canonical frozen Whisper ASR observations",
                "canonical frozen AST AudioSet observations",
            ],
            "allowed_direct_authoring_inputs_after_lead_selection": [
                "bounded frames decoded directly from exact local source media",
                "bounded audio decoded directly from exact local source media",
                "nonsemantic waveform and frame-change metrics",
            ],
            "forbidden_inputs": [
                "CaptainCook4D semantic action annotations",
                "step annotations",
                "task or procedure graphs",
                "error or mistake labels",
                "recipe labels",
                "benchmark splits outcomes prior QA or label-derived features",
                "Task153 human forms during initial machine mining",
            ],
            "machine_scores_are_semantic_evidence": False,
            "dynamic_nontext_visual_is_primary_emphasis": True,
            "meaningful_non_speech_audio_is_primary_emphasis": True,
        },
        "lead_structure": {
            "source_count": 3,
            "candidate_leads_per_source": 2,
            "total_candidate_leads": 6,
            "exactly_two_per_source": True,
            "one_hop_implies_near_local": True,
            "multi_hop_requires_coherent_compositional_claim": True,
            "far_requires_multi_hop": True,
            "quota_forcing_forbidden": True,
            "slots": slots,
        },
        "bounded_direct_inspection": {
            "frame_window_max_seconds": 32,
            "audio_window_max_seconds": 32,
            "maximum_frame_samples": 12,
            "repository_media_derivatives_persisted": False,
            "human_listening_claimed": False,
            "outputs": [
                "source-world question hypothesis",
                "source-world answer hypothesis",
                "atomic claim hypotheses",
                "evidence interval hypotheses",
            ],
            "artifact_classification": "MACHINE_EXPERT_PROVISIONAL",
        },
        "human_prescreen_gate": {
            "gate_a_mode_fails_closed_without_task153_complete_pass": True,
            "development_only_mode_available": True,
            "development_output_gate_a_eligible": False,
            "development_output_future_test_eligible": False,
            "prescreen_assigns_necessity_or_h_tier": False,
        },
        "risk_flags_required": [
            "recurrence and near duplicates",
            "person identity leakage",
            "environment or kitchen identity leakage",
            "speech or ASR substitute",
            "caption OCR package label or text substitute",
        ],
        "task145_template": {
            "states": ["CLEAN", "BLOCKED", "RESTORED", "NO_TRIGGER"],
            "fixed_zero_based_action_index": 4,
            "primary_contrast": "RESTORED_minus_NO_TRIGGER",
            "r_n_public_checkpoint_bytes_identical": True,
            "active_interventions": False,
            "template_only_not_executed": True,
        },
        "output_boundary": {
            "artifact_classification": "MACHINE_EXPERT_PROVISIONAL",
            "default_gate_a_root": (
                "data/restricted/captaincook4d_family_candidates_v1"
            ),
            "default_development_root": (
                "data/restricted/captaincook4d_family_candidates_v1_dev"
            ),
            "tiers": [
                "P0_MACHINE_CANDIDATE",
                "P1_MACHINE_CROSS_VALIDATED",
                "P2_MACHINE_COUNTERFACTUAL_VALIDATED",
            ],
            "H_tiers": False,
            "accepted_families": False,
            "necessity_or_minimality_claims": False,
            "scientific_execution_authorized": False,
        },
    }
    plan["plan_hash"] = json_hash(plan)
    return plan


__all__ = ["build_rehearsal_plan"]
