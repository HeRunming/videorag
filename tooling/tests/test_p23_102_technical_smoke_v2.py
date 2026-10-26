from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PLAN_PATH = ROOT / "data/rehearsal_plan/p23_102_technical_smoke_v2.json"
ATTESTATION_PATH = (
    ROOT
    / "data/restricted/p23_102_technical_smoke_v2/adapter_attestation.json"
)
DESIGN_PATH = ROOT / "docs/design/p23_102_technical_smoke_v2.md"
TOKEN = "P23_102_TECHNICAL_SMOKE_V2_FROZEN_NOT_AUTHORIZED"
SYSTEMS = [
    "single_shot_rag",
    "learned_react",
    "learned_evidence_sufficiency",
]
MECHANISMS = ["SILENT_ROUTE_WITHHOLDING", "EXPLICIT_CHANNEL_OUTAGE"]
ARMS = ["C", "B", "R", "N"]
CHECKPOINT_HASH = (
    "sha256:c580c16af6401b4d12df1d39085bbddee6f63e6d81772f6b3186a0fcc84c996c"
)


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def semantic_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical(value)).hexdigest()


def file_hash(relative: str) -> str:
    return "sha256:" + hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


def test_freeze_is_smoke_only_not_authorized_and_not_640_run() -> None:
    plan = load(PLAN_PATH)
    att = load(ATTESTATION_PATH)
    assert plan["schema_version"] == "av-trace.p23-102-technical-smoke/2.0"
    assert plan["frozen_date"] == "2026-10-14"
    assert plan["decision_token"] == TOKEN
    assert att["decision_token"] == TOKEN
    assert plan["status"] == "TECHNICAL_SMOKE_ONLY_FROZEN_NOT_AUTHORIZED"
    assert plan["scope"]["mode"] == "TECHNICAL_SMOKE_ONLY"
    assert plan["supersession"]["not_the_640_assignment_run"] is True
    assert plan["supersession"]["scientific_protocol_replacement"] is False
    assert plan["scope"]["execution_authorized"] is False
    assert plan["authorization"]["execution_authorized"] is False
    assert att["execution_authorized"] is False
    assert not plan["authorization"]["live_wiring_authorization_present"]
    assert not plan["authorization"]["redteam_authorization_present"]
    assert not att["live_wiring_authorization_present"]
    assert not att["redteam_authorization_present"]
    assert plan["authorization"]["models_must_not_run_under_this_freeze_alone"]
    assert plan["results_boundary"] == {
        "configuration_only": True,
        "model_runs_performed": False,
        "scientific_episodes_performed": False,
        "answer_results_present": False,
        "claims_present": False,
    }


def test_exact_two_diverse_repair_va_families_and_mechanisms() -> None:
    plan = load(PLAN_PATH)
    selection = plan["selection"]
    families = selection["families"]
    assert selection["exact_family_count"] == len(families) == 2
    assert [row["selection_id"] for row in families] == [
        "P23S2-LOCAL-VA-01",
        "P23S2-FAR-VA-01",
    ]
    assert [row["family_id"] for row in families] == [
        "mpf.5814848825c9fad469ad",
        "mpf.bfda23807de4cb85f04b",
    ]
    assert {row["distance_class"] for row in families} == {
        "LOCAL_NEAR_ONE_HOP",
        "FAR_SEPARATED_MULTI_HOP",
    }
    assert {row["candidate_kind"] for row in families} == {
        "near_local",
        "coherent_far_multi_hop",
    }
    for row in families:
        assert row["profile_hypothesis"] == "V+A"
        assert row["machine_provisional_status"] == "REPAIR"
        assert row["accepted_family"] is False
        assert row["accepted_ses"] is False
        assert row["human_validated"] is False
        assert row["structurally_valid_for_smoke"] is True
        assert set(row["interventions"]) == set(MECHANISMS)
        for mechanism in MECHANISMS:
            intervention = row["interventions"][mechanism]
            assert set(intervention["surface_ids"]) == set(ARMS)
            if mechanism == "EXPLICIT_CHANNEL_OUTAGE":
                assert intervention["typed_error_code"] == (
                    "REGISTERED_ROUTE_CHANNEL_UNAVAILABLE"
                )
                assert intervention["response_shape_hash"].startswith("sha256:")
            else:
                assert intervention["typed_error_code"] is None
                assert intervention["response_shape_hash"] is None


def test_exact_32_fixed_assignments_cover_required_minimal_matrix() -> None:
    plan = load(PLAN_PATH)
    assignment_plan = plan["assignment_plan"]
    rows = assignment_plan["assignments"]
    assert assignment_plan["assignment_count"] == len(rows) == 32
    assert assignment_plan["cap"] == 32
    assert assignment_plan["fixed_execution_order"] is True
    assert [row["ordinal"] for row in rows] == list(range(1, 33))
    assert len({row["assignment_id"] for row in rows}) == 32
    assert [row["system_id"] for row in rows if row["system_id"] not in SYSTEMS] == []
    assert plan["systems"]["required"] == SYSTEMS
    assert plan["systems"]["direct_long_context"]["included"] is False
    assert plan["systems"]["direct_long_context"]["permission"] == (
        "OPTIONAL_ENDPOINT_SANITY_ONLY"
    )

    by_cell: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for row in rows:
        by_cell[(row["family_id"], row["mechanism"], row["system_id"])].add(
            row["arm"]
        )
    assert len(by_cell) == 12
    assert all({"R", "N"} <= arms for arms in by_cell.values())

    arm_counts = Counter(row["arm"] for row in rows)
    assert arm_counts == Counter({"R": 12, "N": 12, "C": 4, "B": 4})
    for family_id in {row["family_id"] for row in rows}:
        family_rows = [row for row in rows if row["family_id"] == family_id]
        assert len(family_rows) == 16
        assert Counter(row["mechanism"] for row in family_rows) == Counter(
            {MECHANISMS[0]: 8, MECHANISMS[1]: 8}
        )
        assert Counter(row["arm"] for row in family_rows) == Counter(
            {"R": 6, "N": 6, "C": 2, "B": 2}
        )
    assert assignment_plan["coverage"] == {
        "r_n_pairs": 12,
        "r_n_assignments": 24,
        "c_assignments": 4,
        "b_assignments": 4,
        "systems": 3,
        "mechanisms": 2,
        "families": 2,
    }
    assert assignment_plan["assignment_ids_sha256"] == semantic_hash(
        [row["assignment_id"] for row in rows]
    )
    assert assignment_plan["assignments_sha256"] == semantic_hash(rows)


def test_assignment_ids_and_order_are_derived_deterministically() -> None:
    rows = load(PLAN_PATH)["assignment_plan"]["assignments"]
    for row in rows:
        expected = "p23s2." + hashlib.sha256(
            f'{row["cell_id"]}:{row["arm"]}'.encode()
        ).hexdigest()[:24]
        assert row["assignment_id"] == expected
        if row["arm"] in {"R", "N"}:
            expected_pair = "p23s2pair." + hashlib.sha256(
                row["cell_id"].encode("utf-8")
            ).hexdigest()[:20]
            assert row["pair_id"] == expected_pair
            assert row["session_policy"] == (
                "FRESH_CONTINUATION_FROM_BYTE_IDENTICAL_BLOCKED_PREFIX"
            )
        else:
            assert row["pair_id"] is None
            assert row["session_policy"] == "FRESH_INDEPENDENT_ENDPOINT_SESSION"

    expected_first_last = (
        "p23s2.12c89d29237630117365472e",
        "p23s2.67321e770409b6e3d4e56f01",
    )
    assert (rows[0]["assignment_id"], rows[-1]["assignment_id"]) == expected_first_last


def test_all_frozen_hash_bindings_match_current_files() -> None:
    plan = load(PLAN_PATH)
    att = load(ATTESTATION_PATH)
    assert len(plan["frozen_bindings"]) >= 30
    required_roles = {
        "repaired_current_runner",
        "backend",
        "controller",
        "isolated_model_process",
        "canonical_checkpoint_and_semantic_hash",
        "evaluation_and_metric_record_helpers",
        "public_action_and_final_output_validation",
        "learned_retrieval",
        "react_prompt",
        "evidence_sufficiency_prompt",
        "grounded_generator_prompt",
        "single_repair_prompt",
        "exact_source_manifest",
        "exact_full_timeline_index",
        "generator_and_controller_model_manifest",
        "retrieval_model_manifest",
        "restoration_protocol",
    }
    assert required_roles <= {row["role"] for row in plan["frozen_bindings"]}
    for row in plan["frozen_bindings"]:
        path = ROOT / row["path"]
        assert path.is_file(), row["path"]
        assert path.stat().st_size == row["bytes"]
        assert file_hash(row["path"]) == row["sha256"]
    for row in att["execution_critical_modules"] + att["bound_data_and_contracts"]:
        assert file_hash(row["path"]) == row["sha256"]
        assert (ROOT / row["path"]).stat().st_size == row["bytes"]
    assert {row["role"] for row in att["execution_critical_modules"]} >= {
        "repaired_current_runner",
        "backend",
        "controller",
        "isolated_model_process",
        "canonical_checkpoint_and_semantic_hash",
        "evaluation_and_metric_record_helpers",
        "public_action_and_final_output_validation",
        "learned_retrieval",
    }
    assert att["freeze"]["sha256"] == file_hash(
        "data/rehearsal_plan/p23_102_technical_smoke_v2.json"
    )
    assert att["freeze"]["bytes"] == PLAN_PATH.stat().st_size


def test_one_canonical_checkpoint_serialization_and_hash_everywhere() -> None:
    plan = load(PLAN_PATH)
    att = load(ATTESTATION_PATH)
    contract = plan["checkpoint_contract"]
    event = {
        "event_type": "protocol_checkpoint",
        "event_version": "2.0.0",
        "message": "Scheduled protocol checkpoint completed.",
        "cost": 0.0,
    }
    assert contract["event"] == event
    assert contract["event_canonical_bytes_utf8"].encode("utf-8") == canonical(event)
    assert semantic_hash(event) == CHECKPOINT_HASH
    assert contract["event_canonical_sha256"] == CHECKPOINT_HASH
    assert att["checkpoint_attestation"]["event_canonical_sha256"] == CHECKPOINT_HASH
    assert att["checkpoint_attestation"]["event_canonical_bytes_utf8"] == (
        contract["event_canonical_bytes_utf8"]
    )
    assert contract["fixed_action_index"] == 4
    assert contract["index_base"] == "zero"
    assert contract["r_n_public_prefix_byte_identical_required"]
    assert contract["fresh_continuation_session_per_arm"]
    assert contract["fresh_provider_session_per_assignment"]
    assert contract["get_channel_status_cannot_trigger_restoration"]
    assert att["checkpoint_attestation"]["single_hash_used_everywhere"]
    assert att["checkpoint_attestation"][
        "alternate_known_bundle_hashes_are_not_authoritative_for_this_smoke"
    ]


def test_budgets_abort_thresholds_and_non_evaluable_retention() -> None:
    plan = load(PLAN_PATH)
    budget = plan["budgets"]
    assert budget["tool_budget"] == {
        "max_steps": 10,
        "cost_limit": 12.0,
        "tool_costs": {
            "search_visual": 1.0,
            "search_speech": 1.0,
            "search_ambient_audio": 1.0,
            "inspect_clip": 2.0,
            "read_transcript": 1.0,
            "get_channel_status": 0.25,
            "finalize": 0.0,
        },
    }
    assert budget["generation"] == {
        "input_context_token_cap": 24576,
        "max_new_tokens": 512,
        "repair_attempts": 1,
        "repair_max_new_tokens": 512,
        "do_sample": False,
    }
    invocations = budget["model_invocation_budget"]
    assert invocations["per_assignment_max_provider_invocations"] == 11
    assert invocations["global_max_provider_invocations"] == 352
    assert invocations["global_max_provider_invocations"] == (
        32 * invocations["per_assignment_max_provider_invocations"]
    )
    assert invocations["no_retry_beyond_single_schema_repair"]
    assert "HASH_BINDING_MISMATCH" in plan["abort_thresholds"]["immediate_abort_codes"]
    assert "INVALID_RN_PREFIX_MISMATCH" in plan["abort_thresholds"]["immediate_abort_codes"]
    assert plan["abort_thresholds"]["count_thresholds"]["missing_terminal_ledger_row"] == 1
    non_eval = plan["non_evaluable_outputs"]
    assert non_eval["answer_quality_scoring"] == "PROHIBITED"
    assert non_eval["positive_or_negative_scientific_endpoint_assignment"] == (
        "PROHIBITED"
    )
    assert "MALFORMED_AFTER_REPAIR" in non_eval["codes"]
    assert "MODEL_PROCESS_CRASH" in non_eval["codes"]
    assert "raw attempts" in non_eval["retention"]


def test_output_citation_metrics_and_plumbing_success_contract() -> None:
    plan = load(PLAN_PATH)
    output = plan["output_contract"]
    assert {
        "run_manifest.json",
        "assignments.jsonl",
        "raw_trajectories.jsonl",
        "raw_model_calls.jsonl",
        "factor_model_raw_outputs.jsonl",
        "citation_outputs.jsonl",
        "r_n_prefix_pairs.jsonl",
        "episode_metrics.jsonl",
        "metric_ready_records.jsonl",
        "failure_ledger.jsonl",
        "aggregate_metrics.json",
        "replay_manifest.json",
        "file_inventory.json",
    } == set(output["required_files"])
    assert output["raw_failure_retention_required"]
    assert output["raw_model_text_or_bytes_hash_required_for_malformed_or_process_failures"]
    assert output["citations_must_reference_acquired_observation_ids"]
    assert output["search_pointers_are_not_citations"]
    assert output["missing_citations_are_recorded_not_repaired_by_evaluator"]
    assert output["directory_mode"] == "0700"
    assert output["file_mode"] == "0600"
    success = plan["smoke_success_criteria"]
    assert success["basis"] == "PLUMBING_ONLY_NOT_ANSWER_QUALITY"
    assert "runtime leakage classifier reported as NOT_ESTIMABLE_SINGLE_SOURCE" in success[
        "required"
    ]
    assert "unsupported answers" in success["allowed_without_failure"]
    assert "answer quality passed" in success["forbidden_success_interpretations"]
    assert "model competent" in success["forbidden_success_interpretations"]


def test_claim_firewall_and_runtime_leakage_not_estimable() -> None:
    plan = load(PLAN_PATH)
    att = load(ATTESTATION_PATH)
    forbidden = set(plan["claim_firewall"]["forbidden_claims"])
    assert {
        "answer_quality",
        "model_competence",
        "model_performance",
        "causal_effect",
        "causal_identification",
        "H2",
        "Gate_A",
        "human_family_validity",
        "accepted_SES",
    } <= forbidden
    assert plan["scope"]["machine_provisional_or_weak_model_permitted_for_smoke_only"]
    assert att["model_boundary"]["machine_provisional_or_weak_model_allowed_for_smoke_only"]
    assert att["model_boundary"]["competence_or_performance_inference_forbidden"]
    runtime = plan["claim_firewall"]["runtime_leakage_classifier"]
    assert runtime["status"] == "NOT_ESTIMABLE_SINGLE_SOURCE"
    assert runtime["pass_allowed"] is False
    assert att["runtime_leakage_classifier"] == {
        "status": "NOT_ESTIMABLE_SINGLE_SOURCE",
        "pass_allowed": False,
        "prefix_integrity_is_not_classifier_pass": True,
    }


def test_deterministic_hash_fields_recompute() -> None:
    plan = load(PLAN_PATH)
    hashes = plan["deterministic_hashes"]
    assert hashes["frozen_bindings_sha256"] == semantic_hash(plan["frozen_bindings"])
    assert hashes["selected_families_sha256"] == semantic_hash(
        plan["selection"]["families"]
    )
    assert hashes["assignments_sha256"] == semantic_hash(
        plan["assignment_plan"]["assignments"]
    )
    assert hashes["smoke_success_criteria_sha256"] == semantic_hash(
        plan["smoke_success_criteria"]
    )
    without = dict(plan)
    without.pop("deterministic_hashes")
    assert hashes["plan_sha256_excluding_this_field"] == semantic_hash(without)

    att = load(ATTESTATION_PATH)
    att_hashes = att["deterministic_hashes"]
    assert att_hashes["execution_critical_modules_sha256"] == semantic_hash(
        att["execution_critical_modules"]
    )
    assert att_hashes["bound_data_and_contracts_sha256"] == semantic_hash(
        att["bound_data_and_contracts"]
    )
    att_without = dict(att)
    att_without.pop("deterministic_hashes")
    assert att_hashes["attestation_sha256_excluding_this_field"] == semantic_hash(
        att_without
    )


def test_design_document_contains_required_freeze_boundaries() -> None:
    text = DESIGN_PATH.read_text(encoding="utf-8")
    for phrase in (
        TOKEN,
        "not the 640-assignment run",
        "exactly **32 assignments**",
        "single_shot_rag",
        "learned_react",
        "learned_evidence_sufficiency",
        "SILENT_ROUTE_WITHHOLDING",
        "EXPLICIT_CHANNEL_OUTAGE",
        CHECKPOINT_HASH,
        "NOT_ESTIMABLE_SINGLE_SOURCE",
        "execution_authorized = false",
        "live-wiring",
        "red-team",
        "Plumbing-only success",
    ):
        assert phrase in text
