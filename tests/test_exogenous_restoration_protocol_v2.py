from __future__ import annotations

import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = (
    ROOT / "docs/spec/exogenous_restoration_execution_plan_schema_v2.json"
)
PLAN_PATH = ROOT / "data/rehearsal_plan/exogenous_restoration_protocol_v2.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validation_errors(plan: dict) -> list:
    schema = load_json(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    return sorted(
        Draft202012Validator(schema).iter_errors(plan),
        key=lambda error: (tuple(str(part) for part in error.absolute_path), error.message),
    )


def test_frozen_exogenous_restoration_plan_validates() -> None:
    plan = load_json(PLAN_PATH)
    assert validation_errors(plan) == []
    assert plan["decision_token"] == "CAUSAL_INTERVENTION_V2_READY"
    assert plan["results_boundary"] == {
        "scientific_episodes_executed": False,
        "human_labels_created": False,
        "model_results_claimed": False,
        "statement": (
            "This artifact freezes a prospective protocol only; it contains "
            "no invented result or human label."
        ),
    }


def test_primary_schedule_is_exogenous_and_shared() -> None:
    plan = load_json(PLAN_PATH)
    schedule = plan["primary_schedule"]
    assert schedule["trigger_class"] in {
        "fixed_action_index",
        "cost_budget_threshold",
    }
    assert schedule["shared_scope"] == "same_family_across_all_systems"
    assert schedule["action_index"] == 4
    assert schedule["freeze_timing"] == "before_model_execution"
    assert not schedule["depends_on_action_identity"]
    assert not schedule["depends_on_system_identity"]
    assert not schedule["depends_on_output_or_correctness"]
    assert not schedule["depends_on_get_channel_status"]

    mutated = copy.deepcopy(plan)
    mutated["primary_schedule"]["depends_on_get_channel_status"] = True
    assert validation_errors(mutated)


def test_no_trigger_has_identical_sham_and_prefix_contract() -> None:
    plan = load_json(PLAN_PATH)
    event = plan["primary_schedule"]["event"]
    assert event["public_bytes_identical_r_n"]
    assert not event["reveals_restoration"]
    assert plan["paired_prefix"]["public_transcript_identical_through_event"]
    assert plan["paired_prefix"]["fresh_continuation_sessions"]
    assert plan["states"][2]["scheduled_event"] == (
        "checkpoint_with_hidden_restoration"
    )
    assert plan["states"][3]["scheduled_event"] == (
        "byte_identical_checkpoint_without_restoration"
    )

    mutated = copy.deepcopy(plan)
    mutated["primary_schedule"]["event"]["message"] = "Restoration enabled."
    assert validation_errors(mutated)


def test_primary_estimands_are_mechanism_specific_r_n_itt() -> None:
    plan = load_json(PLAN_PATH)
    analysis = plan["analysis"]
    assert analysis["population"] == (
        "all_preregistered_assignments_intention_to_treat"
    )
    assert analysis["early_terminators_included"]
    assert analysis["invalid_runs_included_fail_closed"]
    assert not analysis["trigger_conditioning_primary_allowed"]
    assert not analysis["pooled_primary_estimand_allowed"]

    estimands = analysis["primary_estimands"]
    assert {item["mechanism"] for item in estimands} == {
        "SILENT_ROUTE_WITHHOLDING",
        "EXPLICIT_CHANNEL_OUTAGE",
    }
    assert {item["contrast"] for item in estimands} == {
        "RESTORED_minus_NO_TRIGGER"
    }
    assert {item["population"] for item in estimands} == {
        "all_preregistered_assignments_intention_to_treat"
    }
    assert all(not item["mechanism"].startswith("POOLED") for item in estimands)
    assert analysis["system_eligibility"] == {
        "primary_matrix_requires_staged_adapter": True,
        "ineligible_status": "STRUCTURALLY_INELIGIBLE_BEFORE_ASSIGNMENT",
        "eligibility_frozen_before_assignment": True,
        "synthetic_outcomes_allowed": False,
    }

    mutated = copy.deepcopy(plan)
    mutated["analysis"]["primary_estimands"][0]["contrast"] = (
        "RESTORED_minus_BLOCKED"
    )
    assert validation_errors(mutated)


def test_get_channel_status_is_secondary_per_protocol_only() -> None:
    plan = load_json(PLAN_PATH)
    condition = plan["analysis"]["action_contingent_condition"]
    assert condition == {
        "trigger": "get_channel_status",
        "role": "SECONDARY_PER_PROTOCOL_ACTION_CONTINGENT",
        "primary_causal_claim_allowed": False,
        "pooled_with_exogenous_allowed": False,
        "report_assigned_and_triggered_denominators": True,
    }

    mutated = copy.deepcopy(plan)
    mutated["analysis"]["action_contingent_condition"][
        "primary_causal_claim_allowed"
    ] = True
    assert validation_errors(mutated)


def test_state_surface_session_cache_and_order_invariants_are_frozen() -> None:
    plan = load_json(PLAN_PATH)
    surface = plan["state_surface"]
    isolation = plan["isolation"]
    order = plan["order_plan"]

    assert surface["r_n_prefix_hash_match_required"]
    assert surface["unaffected_result_order_invariant"]
    assert surface["latency_bucket_invariant"]
    assert surface["result_shape_invariant"]
    assert isolation["fresh_provider_session_per_state"]
    assert isolation["fresh_continuation_session_per_arm"]
    assert not isolation["model_kv_cache_shared"]
    assert not isolation["prompt_cache_shared"]
    assert not isolation["retrieval_cache_shared"]
    assert not isolation["tool_response_cache_shared"]
    assert not isolation["cross_state_memory_allowed"]
    assert order["sequences"] == [
        "C-B-N-R",
        "B-R-C-N",
        "R-N-B-C",
        "N-C-R-B",
    ]
    assert not order["post_outcome_change_allowed"]


def test_metadata_only_leakage_gate_is_fail_closed_and_unrun() -> None:
    plan = load_json(PLAN_PATH)
    gate = plan["leakage_gate"]
    assert gate["status"] == "NOT_RUN_BLOCKS_SCIENTIFIC_EXECUTION"
    assert not gate["uses_human_labels"]
    assert gate["feature_class"] == "non_semantic_public_surface_metadata_only"
    assert gate["cross_validation"] == "leave_one_source_group_out"
    assert gate["primary_task"] == "R_vs_N_through_checkpoint"
    assert gate["pass_criteria"][
        "balanced_accuracy_not_above_majority_baseline"
    ]
    assert gate["pass_criteria"]["source_group_blocked_permutation_p_min"] == 0.05
    assert not gate["pass_criteria"][
        "deterministic_single_feature_predictor_allowed"
    ]
    assert gate["pass_criteria"]["r_n_prefix_hashes_match"]
    assert not plan["execution_gate"]["scientific_execution_authorized"]


def test_ses_terminology_is_bounded_not_exhaustive() -> None:
    plan = load_json(PLAN_PATH)
    terminology = plan["terminology"]
    assert terminology["required_phrase"] == (
        "all accepted SESs discovered under the frozen saturation protocol"
    )
    assert "all possible SESs" in terminology["forbidden_phrases"]
    assert "exhaustive SESs" in terminology["forbidden_phrases"]
