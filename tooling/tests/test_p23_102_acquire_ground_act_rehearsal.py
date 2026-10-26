from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PLAN_PATH = (
    ROOT
    / "data/rehearsal_plan/p23_102_acquire_ground_act_rehearsal_v1.json"
)
DESIGN_PATH = (
    ROOT / "docs/design/p23_102_acquire_ground_act_rehearsal_v1.md"
)


def load_plan() -> dict[str, Any]:
    return json.loads(PLAN_PATH.read_text(encoding="utf-8"))


def canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_digest(relative_path: str) -> str:
    return hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest()


def test_top_level_schema_and_nonclaims() -> None:
    plan = load_plan()
    assert plan["schema_version"] == (
        "av-trace.p23-102-acquire-ground-act-rehearsal/1.0"
    )
    assert plan["frozen_date"] == "2026-10-13"
    assert plan["decision_token"] == (
        "P23_102_ACQUIRE_GROUND_ACT_REHEARSAL_READY"
    )
    assert plan["status"] == "PROSPECTIVE_DEVELOPMENT_ONLY_CONFIGURATION"
    assert plan["scope"]["development_only"] is True
    assert plan["scope"]["future_test_eligible"] is False
    assert plan["scope"]["scientific_execution_authorized"] is False
    assert plan["scope"]["h2_claimed"] is False
    assert plan["scope"]["human_review_performed"] is False
    assert plan["scope"]["model_or_media_execution_performed_by_this_artifact"] is False
    assert plan["results_boundary"]["scientific_episodes_executed"] is False
    assert plan["results_boundary"]["model_results_claimed"] is False
    assert plan["results_boundary"]["causal_effect_claimed"] is False


def test_source_disjoint_development_boundary_is_fail_closed() -> None:
    rule = load_plan()["scope"]["source_disjoint_rule"]
    assert rule["development_group"] == "P23"
    assert rule[
        "all_p23_media_annotations_indexes_clips_encodes_and_derivatives_share_one_group"
    ]
    assert rule["training_or_prompt_tuning_sources_must_exclude_p23"]
    assert rule["future_evaluation_sources_must_exclude_p23"]
    assert rule["p23_families_may_not_be_counted_as_source_disjoint_from_each_other"]
    assert rule["violation_status"] == "SOURCE_DISJOINTNESS_VIOLATION"


def test_existing_prerequisite_hashes_are_exact() -> None:
    plan = load_plan()
    for relative_path, expected in plan["frozen_input_hashes"].items():
        assert (ROOT / relative_path).is_file(), relative_path
        assert file_digest(relative_path) == expected, relative_path

    component_paths = [
        ("fixed_backend", "implementation_path", "implementation_sha256"),
        ("learned_retrieval", "implementation_path", "implementation_sha256"),
        ("grounded_generator", "implementation_path", "implementation_sha256"),
        ("grounded_generator", "schema_path", "schema_sha256"),
        ("evaluation", "implementation_path", "implementation_sha256"),
        ("evaluation", "metrics_protocol_path", "metrics_protocol_sha256"),
    ]
    frozen = plan["frozen_components"]
    observed_drift: list[tuple[str, str, str]] = []
    for section, path_key, hash_key in component_paths:
        relative_path = frozen[section][path_key]
        observed = file_digest(relative_path)
        expected = frozen[section][hash_key]
        if observed != expected:
            observed_drift.append((relative_path, expected, observed))

    # This v1 rehearsal freeze is intentionally immutable. The repaired
    # controller supersedes it, so hash drift must be detected rather than
    # "fixed" by rewriting the historical plan in place.
    assert observed_drift == [
        (
            "src/av_trace_scale1b_agent/controller.py",
            "18b5a4e78e3a88253ff8f8f6568418bccbabb1e22a99f2ee95727a9a044f1b6f",
            "e4f1acd34ce3af160e0e827eddeb3afd401d6a31ee141b811d28b1eac2feb773",
        )
    ]

    for controller in frozen["controllers"].values():
        relative_path = controller.get("prompt_path") or controller.get("path")
        assert relative_path
        assert file_digest(relative_path) == controller["prompt_sha256" if "prompt_sha256" in controller else "sha256"]


def test_future_prerequisite_paths_are_explicit_and_currently_nonclaims() -> None:
    plan = load_plan()
    future = {
        row["path"]
        for row in plan["prerequisites"][
            "future_required_for_development_rehearsal"
        ]
    }
    assert {
        "data/restricted/epic_p23_102_source_v1/manifests/epic_p23_102_exact_manifest.json",
        "data/restricted/epic_p23_102_source_v1/media/P23/P23_102.MP4",
        "data/restricted/epic_p23_102_full_timeline_index_v1/build_manifest.json",
        "data/restricted/epic_p23_102_full_timeline_index_v1/full_timeline_index.json",
        "data/restricted/epic_p23_102_machine_provisional_families_v1/family_registry.json",
        "data/restricted/epic_p23_102_machine_provisional_families_v1/evidence_registry.json",
        "data/restricted/epic_p23_102_machine_provisional_families_v1/intervention_manifest.json",
        "data/restricted/epic_p23_102_machine_provisional_families_v1/state_surface_manifest.json",
        "data/restricted/epic_p23_102_machine_provisional_families_v1/source_split_manifest.json",
        "data/restricted/epic_p23_102_machine_provisional_families_v1/leakage_gate.json",
        "data/restricted/p23_102_acquire_ground_act_rehearsal_v1/adapter_attestation.json",
        "scripts/run_p23_102_acquire_ground_act_rehearsal.py",
    } <= future
    assert plan["prerequisites"]["fail_closed_if_missing"]
    assert plan["execution"]["runner_exists_at_freeze"] is False
    assert plan["execution"]["models_or_media_may_run_during_schema_validation"] is False


def test_restoration_v2_fixed_action_four_and_rn_sham() -> None:
    restoration = load_plan()["restoration_v2"]
    assert restoration["index_base"] == "zero"
    assert restoration["fixed_action_index"] == 4
    assert restoration["delivery_boundary"] == (
        "after_four_completed_action_response_cycles_before_fifth_model_decision"
    )
    assert restoration["depends_on_action_identity"] is False
    assert restoration["depends_on_system_identity"] is False
    assert restoration["depends_on_output_or_correctness"] is False
    assert restoration["depends_on_get_channel_status"] is False
    assert restoration["checkpoint_event"]["cost"] == 0.0
    assert restoration["paired_prefix"][
        "r_n_public_transcript_identical_through_event"
    ]
    assert restoration["paired_prefix"]["fresh_continuation_session_per_arm"]
    legacy = restoration["legacy_get_channel_status_restoration"]
    assert legacy["enabled_in_primary_matrix"] is False
    assert legacy["allowed_only_as"] == (
        "SECONDARY_PER_PROTOCOL_ACTION_CONTINGENT"
    )


def test_c_b_r_n_arms_and_mechanisms_are_separate() -> None:
    plan = load_plan()
    assert [(row["arm"], row["state"]) for row in plan["arms"]] == [
        ("C", "CLEAN"),
        ("B", "BLOCKED"),
        ("R", "RESTORED"),
        ("N", "NO_TRIGGER"),
    ]
    mechanisms = plan["mechanisms"]
    assert [row["mechanism"] for row in mechanisms] == [
        "SILENT_ROUTE_WITHHOLDING",
        "EXPLICIT_CHANNEL_OUTAGE",
    ]
    assert all(not row["primary_pooling_with_other_mechanism"] for row in mechanisms)
    assert {row["primary_estimand_id"] for row in mechanisms} == {
        "P1_RN_SILENT_ROUTE_WITHHOLDING_ITT",
        "P2_RN_EXPLICIT_CHANNEL_OUTAGE_ITT",
    }
    assert plan["analysis"]["mechanisms_pooled_for_primary"] is False


def test_four_system_rows_have_full_arm_and_mechanism_matrix() -> None:
    plan = load_plan()
    matrix = plan["matrix"]
    rows = matrix["system_rows"]
    assert [row["system_id"] for row in rows] == [
        "direct_long_context",
        "single_shot_rag",
        "learned_react",
        "learned_evidence_sufficiency",
    ]
    for row in rows:
        assert row["state_arms"] == ["C", "B", "R", "N"]
        assert row["mechanism_arms"] == [
            "SILENT_ROUTE_WITHHOLDING",
            "EXPLICIT_CHANNEL_OUTAGE",
        ]
        assert row["ground_metrics_eligible"] is True
    assert matrix["planned_row_slots_per_family_if_both_mechanisms_are_eligible"] == (
        len(rows) * len(plan["arms"]) * len(plan["mechanisms"])
    )
    direct = rows[0]
    assert direct["staged_event_capable"] is False
    assert direct["r_n_primary_status"] == (
        "STRUCTURALLY_INELIGIBLE_BEFORE_ASSIGNMENT"
    )
    assert direct["acquire_metrics_eligible"] is False
    assert direct["act_metrics_eligible"] is False
    assert all(row["staged_event_capable"] for row in rows[1:])
    assert all(row["r_n_primary_status"] == "ELIGIBLE" for row in rows[1:])


def test_budgets_match_existing_fixed_backend_contract() -> None:
    plan = load_plan()
    budget = plan["budgets"]["agentic_and_rag"]
    assert budget["max_steps"] == 10
    assert budget["cost_limit"] == 12.0
    assert budget["tool_costs"] == {
        "search_visual": 1.0,
        "search_speech": 1.0,
        "search_ambient_audio": 1.0,
        "inspect_clip": 2.0,
        "read_transcript": 1.0,
        "get_channel_status": 0.25,
        "finalize": 0.0,
    }
    generation = plan["budgets"]["generation"]
    assert generation == {
        "input_context_token_cap": 24576,
        "max_new_tokens": 512,
        "repair_attempts": 1,
        "repair_max_new_tokens": 512,
        "do_sample": False,
    }
    assert plan["budgets"]["budget_pairing"] == (
        "identical_within_family_mechanism_system_across_C_B_R_N"
    )


def test_tool_schemas_and_citation_boundary_are_exact() -> None:
    contract = load_plan()["tool_contract"]
    for key in (
        "action_schema",
        "response_schema",
        "final_answer_schema",
        "trajectory_schema",
    ):
        entry = contract[key]
        assert file_digest(entry["path"]) == entry["sha256"]
    assert [row["tool"] for row in contract["tools"]] == [
        "search_visual",
        "search_speech",
        "search_ambient_audio",
        "inspect_clip",
        "read_transcript",
        "get_channel_status",
        "finalize",
    ]
    assert contract["search_results_are_non_citable_pointers"]
    assert contract["citations_must_reference_acquired_observation_ids"]
    assert contract["protocol_checkpoint_is_runner_event_not_model_action"]
    status = next(
        row for row in contract["tools"] if row["tool"] == "get_channel_status"
    )
    assert status["cannot_trigger_primary_restoration"]


def test_raw_trajectory_and_citation_outputs_are_required() -> None:
    output = load_plan()["raw_output_contract"]
    paths = {row["path"] for row in output["required_files"]}
    assert {
        "raw_trajectories.jsonl",
        "raw_model_calls.jsonl",
        "citation_outputs.jsonl",
        "r_n_prefix_pairs.jsonl",
        "episode_metrics.jsonl",
        "failure_ledger.jsonl",
        "aggregate_metrics.json",
        "replay_manifest.json",
        "file_inventory.json",
    } <= paths
    assert {
        "events",
        "checkpoint",
        "final_output",
        "completion",
        "replay",
    } <= set(output["raw_trajectory_required_fields"])
    assert {
        "asserted_claims",
        "claim_to_citations",
        "observation_catalog",
        "citation_validation",
        "output_schema_valid",
    } <= set(output["citation_output_required_fields"])
    assert output["directory_mode"] == "0700"
    assert output["file_mode"] == "0600"
    assert output["no_overwrite_completed_run"]


def test_acquire_ground_act_metrics_itt_and_no_trigger_estimands() -> None:
    plan = load_plan()
    metrics = plan["metrics"]
    assert metrics["Acquire"]["primary"] == [
        "evidence_recall",
        "all_evidence_success",
    ]
    assert metrics["Acquire"]["direct_long_context_values"] is None
    assert metrics["Ground"]["primary"] == [
        "answer_score",
        "citation_f1",
        "supported_claim_rate",
    ]
    assert metrics["Act"]["primary"] == [
        "success_at_budget",
        "premature_stop",
        "recovery",
    ]
    assert metrics["null_policy"] == (
        "structurally_ineligible_metrics_are_null_not_zero"
    )

    analysis = plan["analysis"]
    assert analysis["population"] == (
        "all_preregistered_assignments_intention_to_treat"
    )
    assert analysis["trigger_conditioning_primary_allowed"] is False
    assert analysis["early_terminators_included"] is True
    assert analysis["invalid_runs_included_fail_closed"] is True
    assert analysis["missing_pairs_dropped"] is False
    assert analysis["positive_endpoint_for_invalid_run"] == 0.0
    assert analysis["r_n_early_terminal_pair_difference"] == 0.0
    assert [row["estimand_id"] for row in analysis["no_trigger_estimands"]] == [
        "N_FALSE_RECOVERY_RATE",
        "RN_PREFIX_INTEGRITY_RATE",
        "RN_REACQUISITION_DIFFERENCE",
    ]


def test_failure_statuses_cover_preassignment_protocol_and_runtime() -> None:
    failures = load_plan()["failure_statuses"]
    all_statuses = {
        status
        for group, values in failures.items()
        if group != "itt_rule"
        for status in values
    }
    assert {
        "STRUCTURALLY_INELIGIBLE_BEFORE_ASSIGNMENT",
        "SOURCE_NOT_READY",
        "INDEX_NOT_READY",
        "LEAKAGE_GATE_NOT_RUN",
        "INVALID_CROSS_STATE_CONTAMINATION",
        "INVALID_RN_PREFIX_MISMATCH",
        "INVALID_CHECKPOINT_EVENT_MISMATCH",
        "INVALID_RESTORATION_SCHEDULE",
        "MALFORMED_AFTER_REPAIR",
        "MODEL_TIMEOUT",
        "MODEL_OOM",
        "OVER_BUDGET_STEPS",
        "OVER_BUDGET_COST",
        "NO_FINALIZATION_WITHIN_STEP_LIMIT",
        "NONDETERMINISTIC_REPLAY",
        "MISSING_CITATION_OUTPUT",
    } <= all_statuses
    assert "primary denominator" in failures["itt_rule"]
    assert "no synthetic outcome" in failures["itt_rule"]


def test_deterministic_hashes_recompute() -> None:
    plan = load_plan()
    hashes = plan["deterministic_hashes"]
    event = plan["restoration_v2"]["checkpoint_event"]
    assert digest(event) == hashes["checkpoint_event_sha256"]
    assert digest(event) == plan["restoration_v2"][
        "checkpoint_event_canonical_sha256"
    ]
    assert digest(plan["frozen_input_hashes"]) == hashes[
        "frozen_input_bundle_sha256"
    ]
    schema_bundle = {
        key: plan["tool_contract"][key]
        for key in (
            "action_schema",
            "response_schema",
            "final_answer_schema",
            "trajectory_schema",
        )
    }
    assert digest(schema_bundle) == hashes["tool_schema_bundle_sha256"]
    assert digest(plan["matrix"]) == hashes["matrix_sha256"]

    self_payload = copy.deepcopy(plan)
    self_payload["deterministic_hashes"][
        "config_sha256_excluding_this_field"
    ] = None
    assert digest(self_payload) == hashes["config_sha256_excluding_this_field"]


def test_design_document_has_required_completion_and_nonclaim_language() -> None:
    text = DESIGN_PATH.read_text(encoding="utf-8")
    for required in (
        "Direct long-context",
        "Single-shot learned RAG",
        "Learned ReAct",
        "Learned evidence-sufficiency agent",
        "`C`",
        "`B`",
        "`R`",
        "`N`",
        "SILENT_ROUTE_WITHHOLDING",
        "EXPLICIT_CHANNEL_OUTAGE",
        "intention-to-treat",
        "H2 has not been claimed",
        "P23_102_ACQUIRE_GROUND_ACT_REHEARSAL_READY",
    ):
        assert required in text
