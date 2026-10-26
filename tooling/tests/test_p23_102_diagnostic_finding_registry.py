from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = (
    ROOT
    / "data/rehearsal_plan/p23_102_diagnostic_finding_registry_v1.json"
)
TEMPLATE_PATH = (
    ROOT / "docs/paper/p23_102_diagnostic_experiment_table_template.md"
)


def load_registry() -> dict[str, Any]:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


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


def test_top_level_schema_date_token_and_nonresult_boundary() -> None:
    registry = load_registry()
    assert registry["schema_version"] == (
        "av-trace.p23-102-diagnostic-finding-registry/1.0"
    )
    assert registry["registry_id"] == "P23_102_DIAGNOSTIC_FINDING_REGISTRY_V1"
    assert registry["frozen_date"] == "2026-10-14"
    assert registry["decision_token"] == (
        "P23_102_DIAGNOSTIC_FINDING_REGISTRY_READY"
    )
    assert registry["status"] == (
        "PREREGISTERED_DEVELOPMENT_ONLY_NOT_EXECUTED"
    )

    alignment = registry["paper_alignment"]
    assert alignment["position"] == (
        "benchmark_and_diagnostic_protocol_not_controller_method"
    )
    assert alignment["development_only"] is True
    assert alignment["future_primary_test_eligible"] is False
    assert alignment["scientific_execution_authorized"] is False
    assert alignment["model_execution_performed_by_this_registry"] is False
    assert alignment["results_present"] is False

    boundary = registry["results_boundary"]
    assert boundary["configuration_only"] is True
    assert boundary["scientific_episodes_executed"] is False
    assert boundary["model_results_claimed"] is False
    assert boundary["causal_effect_claimed"] is False
    assert boundary["fabricated_results_present"] is False


def test_exact_four_system_rows_and_eligibility() -> None:
    rows = load_registry()["exact_system_rows"]
    assert [row["ordinal"] for row in rows] == [1, 2, 3, 4]
    assert [row["system_id"] for row in rows] == [
        "direct_long_context",
        "single_shot_rag",
        "learned_react",
        "learned_evidence_sufficiency",
    ]
    assert [row["paper_label"] for row in rows] == [
        "Direct LC",
        "Single-shot RAG",
        "Learned ReAct",
        "Sufficiency agent",
    ]
    direct = rows[0]
    assert direct["acquire_metrics_eligible"] is False
    assert direct["ground_metrics_eligible"] is True
    assert direct["act_metrics_eligible"] is False
    assert direct["staged_event_capable"] is False
    assert direct["rn_primary_status"] == (
        "STRUCTURALLY_INELIGIBLE_BEFORE_ASSIGNMENT"
    )
    assert all(row["staged_event_capable"] for row in rows[1:])
    assert all(row["rn_primary_status"] == "ELIGIBLE" for row in rows[1:])


def test_c_b_r_n_arms_and_separate_silent_explicit_mechanisms() -> None:
    registry = load_registry()
    assert [(row["arm"], row["state"]) for row in registry["arms"]] == [
        ("C", "CLEAN"),
        ("B", "BLOCKED"),
        ("R", "RESTORED"),
        ("N", "NO_TRIGGER"),
    ]
    mechanisms = registry["mechanisms"]
    assert [row["mechanism_id"] for row in mechanisms] == [
        "SILENT_ROUTE_WITHHOLDING",
        "EXPLICIT_CHANNEL_OUTAGE",
    ]
    assert [row["primary_estimand_id"] for row in mechanisms] == [
        "P1_RN_SILENT_ROUTE_WITHHOLDING_ITT",
        "P2_RN_EXPLICIT_CHANNEL_OUTAGE_ITT",
    ]
    assert all(
        row["pool_with_other_mechanism_for_primary"] is False
        for row in mechanisms
    )

    schedule = registry["restoration_schedule"]
    assert schedule["index_base"] == "zero"
    assert schedule["action_index"] == 4
    assert schedule["paired_prefix_construction"] == (
        "single_blocked_prefix_then_fresh_replayed_fork"
    )
    assert schedule[
        "public_prefix_and_checkpoint_byte_identical_between_r_and_n"
    ]
    assert schedule["fresh_continuation_session_per_arm"]
    assert schedule["depends_on_get_channel_status"] is False
    assert schedule["trigger_conditioning_primary_allowed"] is False
    assert schedule["pooled_mechanism_primary_allowed"] is False


def test_acquire_ground_act_metric_catalog_and_structural_nulls() -> None:
    metrics = load_registry()["metric_catalog"]
    assert [row["metric_id"] for row in metrics["Acquire"]["primary"]] == [
        "evidence_recall",
        "all_evidence_success",
    ]
    assert metrics["Acquire"]["direct_long_context_value"] is None
    assert [row["metric_id"] for row in metrics["Ground"]["primary"]] == [
        "answer_score",
        "citation_f1",
        "supported_claim_rate",
        "supported_answer_endpoint",
    ]
    assert [row["metric_id"] for row in metrics["Act"]["primary"]] == [
        "success_at_budget",
        "premature_stop",
        "recovery",
    ]
    assert metrics["Act"]["direct_long_context_value"] is None
    assert "modality_switch_opportunity" in metrics["Act"]["secondary"]
    assert "cost_per_supported_answer" in metrics["cost"]["metrics"]
    assert metrics["structural_null_policy"] == (
        "Structurally ineligible metrics are null with a reason code, never zero."
    )


def test_all_requested_findings_have_fixed_ids_and_objective_rules() -> None:
    findings = load_registry()["findings"]
    assert [row["finding_id"] for row in findings] == [
        "P23F-01-RANKING-INVERSION",
        "P23F-02-RK-GAIN-GROUND-LOSS",
        "P23F-03-PREMATURE-STOP-PARTIAL",
        "P23F-04-MODALITY-SWITCH-FAILURE",
        "P23F-05-RN-RESTORATION-ITT",
        "P23F-06-COMPLETE-VS-PARTIAL",
        "P23F-07-COST-BENEFIT-HOP-MODALITY",
    ]
    for finding in findings:
        assert finding["objective_decision_rule"]
        assert finding["required_outputs"]
        assert finding["permitted_wording"]
        assert finding["prohibited_wording"]

    by_id = {row["finding_id"]: row for row in findings}
    inversion = by_id["P23F-01-RANKING-INVERSION"]
    assert "answer_difference * evidence_completeness_difference < 0" in (
        inversion["objective_decision_rule"]["OBSERVED_DESCRIPTIVE"]
    )

    retrieval = by_id["P23F-02-RK-GAIN-GROUND-LOSS"]
    assert retrieval["retrieval_depths"] == [5, 20]
    assert "recall_gain_at_k > 0" in (
        retrieval["objective_decision_rule"]["OBSERVED_DESCRIPTIVE"]
    )
    assert "grounded_generation_change < 0" in (
        retrieval["objective_decision_rule"]["OBSERVED_DESCRIPTIVE"]
    )

    premature = by_id["P23F-03-PREMATURE-STOP-PARTIAL"]
    assert "no_complete_accepted_SES_acquired" in (
        premature["event_definition"]["partial_evidence_acquired"]
    )
    assert "legal_within_remaining_budget_action_sequence" in (
        premature["event_definition"]["feasible_continuation"]
    )

    switch = by_id["P23F-04-MODALITY-SWITCH-FAILURE"]
    assert {
        "initial_modality",
        "target_modality",
        "mechanism",
        "system_id",
    } == set(switch["required_strata"])

    recovery = by_id["P23F-05-RN-RESTORATION-ITT"]
    assert recovery["estimands"] == [
        "P1_RN_SILENT_ROUTE_WITHHOLDING_ITT",
        "P2_RN_EXPLICIT_CHANNEL_OUTAGE_ITT",
    ]
    assert recovery["estimand_formula"] == (
        "mean_paired(supported_answer_endpoint_R - supported_answer_endpoint_N)"
    )

    evidence = by_id["P23F-06-COMPLETE-VS-PARTIAL"]
    assert "COMPLETE_MACHINE_PROVISIONAL_SES" in evidence["eligible_records"]
    assert "PROPER_PARTIAL_BREAKS_REQUIRED_CLAIM" in evidence[
        "eligible_records"
    ]

    cost = by_id["P23F-07-COST-BENEFIT-HOP-MODALITY"]
    assert cost["required_strata"]["hop_count"] == [
        "ONE_HOP",
        "MULTI_HOP",
    ]
    assert cost["required_strata"]["required_modality_set"] == [
        "V",
        "S",
        "A",
        "V+S",
        "V+A",
        "S+A",
        "V+S+A",
    ]
    assert set(cost["objective_classification"]) == {
        "STRICT_DOMINANCE",
        "BENEFICIAL_TRADEOFF",
        "STRICTLY_DOMINATED",
        "COST_SAVING_WITH_SUCCESS_LOSS",
        "COST_INCREASE_NO_SUCCESS_GAIN",
        "COST_SAVING_NO_SUCCESS_CHANGE",
        "NO_DIRECTIONAL_DIFFERENCE",
    }


def test_estimands_bootstrap_units_clustering_and_minimum_sample_caveats() -> None:
    registry = load_registry()
    estimands = {row["estimand_id"]: row for row in registry["estimands"]}
    assert {
        "P1_RN_SILENT_ROUTE_WITHHOLDING_ITT",
        "P2_RN_EXPLICIT_CHANNEL_OUTAGE_ITT",
        "E_COMPLETE_PARTIAL_PAIRED",
        "E_COST_BENEFIT_STRATIFIED",
    } <= set(estimands)
    assert estimands["P1_RN_SILENT_ROUTE_WITHHOLDING_ITT"][
        "population"
    ] == "all_preregistered_assigned_R_N_pairs"
    assert estimands["P2_RN_EXPLICIT_CHANNEL_OUTAGE_ITT"][
        "population"
    ] == "all_preregistered_assigned_R_N_pairs"

    stats = registry["statistical_contract"]
    assert stats["source_cluster_key"] == "source_group_id"
    assert stats["family_cluster_key"] == "family_id"
    assert stats["p23_source_group_count"] == 1
    interval = stats["development_interval"]
    assert interval["method"] == "paired_family_cluster_percentile_bootstrap"
    assert interval["resamples_minimum"] >= 10000
    assert interval["seed"] == 2310220261014
    assert interval["confidence_level"] == 0.95
    assert interval["bootstrap_unit"] == "family_id"
    assert interval["individual_episode_or_action_bootstrap_prohibited"]
    assert interval["minimum_eligible_paired_families_for_interval"] == 5
    source_interval = stats["paper_source_cluster_interval"]
    assert source_interval["method"] == "paired_source_cluster_bootstrap"
    assert source_interval["available_for_P23_102"] is False
    assert source_interval["may_be_approximated_by_family_bootstrap"] is False
    minimums = stats["minimum_sample_caveats"]
    assert minimums["minimum_paired_families_for_an_observed_finding_label"] == 5
    assert minimums["minimum_source_groups_for_any_source_generalization"] == 20
    assert minimums["p23_can_satisfy_source_minimum"] is False
    assert stats["multiplicity"]["confirmatory_family_in_P23"] == "none"
    assert stats["multiplicity"]["p_values_planned"] is False


def test_missing_invalid_and_itt_policy_is_fail_closed() -> None:
    policy = load_registry()["missing_invalid_itt_policy"]
    assert policy["assigned_invalid_positive_success_endpoint"] == 0
    assert policy["early_terminal_rn_pair"] == (
        "retain_both_assignments_and_set_paired_difference_to_zero"
    )
    assert policy["event_opportunity_not_reached"] == (
        "retain_in_R_N_ITT_denominator"
    )
    assert policy["route_not_inspected"] == "retain_in_R_N_ITT_denominator"
    assert policy["complete_evidence_not_reacquired"] == (
        "retain_in_R_N_ITT_denominator"
    )
    assert policy["missing_pair_drop_allowed"] is False
    assert policy["available_case_pair_drop_allowed"] is False
    assert policy["silent_retry_selection_allowed"] is False
    assert policy["outcome_based_replacement_allowed"] is False
    assert "null" in policy["structural_ineligibility"]
    assert "100 percent" in policy["premature_stop_certificate_policy"]
    assert "all systems arms mechanisms and diagnostics" in (
        policy["evaluator_or_registry_defect"]
    )


def test_table_schemas_are_exact_and_cover_paper_outputs() -> None:
    tables = load_registry()["table_schemas"]
    assert [row["table_id"] for row in tables] == [
        "P23-A",
        "P23-B",
        "P23-C",
        "P23-D",
        "P23-E",
        "P23-F",
        "P23-G",
    ]
    by_id = {row["table_id"]: row for row in tables}
    assert by_id["P23-B"]["row_grain"] == (
        "stage_x_metric_id_x_system_id_x_mechanism_x_arm"
    )
    assert "R_minus_N_ITT:number" in by_id["P23-C"]["columns"]
    assert "finding_id:string" in by_id["P23-D"]["columns"]
    assert "unsupported_completion_rate:number" in by_id["P23-E"][
        "columns"
    ]
    assert "incremental_cost_per_supported_answer:number_string_or_null" in (
        by_id["P23-F"]["columns"]
    )
    assert "ITT_treatment:string" in by_id["P23-G"]["columns"]
    assert load_registry()["reporting_contract"]["required_table_ids"] == [
        row["table_id"] for row in tables
    ]


def test_exact_artifact_dependencies_and_future_result_binding() -> None:
    dependencies = load_registry()["artifact_dependencies"]
    existing = dependencies["authoritative_existing"]
    assert len(existing) >= 12
    for row in existing:
        assert (ROOT / row["path"]).is_file(), row["path"]
        assert file_digest(row["path"]) == row["sha256"], row["path"]

    future = {
        row["path"]
        for row in dependencies["future_required_before_any_result_table"]
    }
    assert {
        "data/restricted/epic_p23_102_machine_provisional_families_v1/family_registry.json",
        "data/restricted/epic_p23_102_machine_provisional_families_v1/evidence_registry.json",
        "data/restricted/epic_p23_102_machine_provisional_families_v1/intervention_manifest.json",
        "data/restricted/epic_p23_102_machine_provisional_families_v1/state_surface_manifest.json",
        "data/restricted/epic_p23_102_machine_provisional_families_v1/leakage_gate.json",
        "data/restricted/p23_102_acquire_ground_act_rehearsal_v1/adapter_attestation.json",
        "data/restricted/p23_102_acquire_ground_act_rehearsal_v1/diagnostic_assignment_manifest.json",
        "scripts/run_p23_102_acquire_ground_act_rehearsal.py",
    } <= future
    assert {
        "raw_trajectories.jsonl",
        "citation_outputs.jsonl",
        "r_n_prefix_pairs.jsonl",
        "episode_metrics.jsonl",
        "failure_ledger.jsonl",
        "aggregate_metrics.json",
        "replay_manifest.json",
        "file_inventory.json",
        "diagnostic_findings.json",
        "paper_tables.json",
    } <= set(dependencies["future_required_run_artifacts"])
    assert dependencies["fail_closed_if_missing_or_hash_mismatched"]
    assert "Hand-entered result numbers are prohibited" in (
        dependencies["result_binding_rule"]
    )


def test_terminology_and_prohibited_claim_firewall() -> None:
    registry = load_registry()
    terminology = registry["terminology"]
    assert terminology["p23_complete_evidence_label"] == (
        "COMPLETE_MACHINE_PROVISIONAL_SES"
    )
    assert terminology["partial_evidence_label"] == (
        "PROPER_PARTIAL_BREAKS_REQUIRED_CLAIM"
    )
    assert "human gold" in terminology["forbidden_for_p23_without_later_h2"]
    assert "exhaustive SESs" in terminology[
        "forbidden_for_p23_without_later_h2"
    ]
    prohibited = set(registry["prohibited_actions"])
    assert {
        "fabricate_or_placeholder_numeric_results",
        "pool_silent_and_explicit_mechanisms_for_a_primary_effect",
        "replace_R_minus_NO_TRIGGER_ITT_with_trigger_conditioned_analysis",
        "drop_invalid_or_early_terminal_assignments_from_ITT",
        "claim_controller_superiority_or_source_generalization_from_P23_102",
        "treat_family_bootstrap_as_source_cluster_inference",
    } <= prohibited


def test_deterministic_hashes_recompute() -> None:
    registry = load_registry()
    hashes = registry["deterministic_hashes"]
    assert file_digest(hashes["paper_template_path"]) == hashes[
        "paper_template_sha256"
    ]
    for key in (
        "exact_system_rows",
        "arms",
        "mechanisms",
        "metric_catalog",
        "findings",
        "table_schemas",
        "artifact_dependencies",
    ):
        assert digest(registry[key]) == hashes[f"{key}_sha256"]

    self_payload = copy.deepcopy(registry)
    self_payload["deterministic_hashes"][
        "registry_sha256_excluding_this_field"
    ] = None
    assert digest(self_payload) == hashes[
        "registry_sha256_excluding_this_field"
    ]


def test_template_has_all_rows_findings_tables_and_completion_token() -> None:
    text = TEMPLATE_PATH.read_text(encoding="utf-8")
    for required in (
        "Direct LC",
        "Single-shot RAG",
        "Learned ReAct",
        "Sufficiency agent",
        "`C`",
        "`B`",
        "`R`",
        "`N`",
        "SILENT_ROUTE_WITHHOLDING",
        "EXPLICIT_CHANNEL_OUTAGE",
        "### Table P23-A",
        "### Table P23-B",
        "### Table P23-C",
        "### Table P23-D",
        "### Table P23-E",
        "### Table P23-F",
        "### Table P23-G",
        "P23F-01-RANKING-INVERSION",
        "P23F-02-RK-GAIN-GROUND-LOSS",
        "P23F-03-PREMATURE-STOP-PARTIAL",
        "P23F-04-MODALITY-SWITCH-FAILURE",
        "P23F-05-RN-RESTORATION-ITT",
        "P23F-06-COMPLETE-VS-PARTIAL",
        "P23F-07-COST-BENEFIT-HOP-MODALITY",
        "No fabricated results",
        "descriptive only",
        "P23_102_DIAGNOSTIC_FINDING_REGISTRY_READY",
    ):
        assert required in text
