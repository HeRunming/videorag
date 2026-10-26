from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PLAN_PATH = (
    ROOT / "data/rehearsal_plan/source_disjoint_scaleup_wave_v1.json"
)
DOC_PATH = ROOT / "docs/paper/source_disjoint_scaleup_wave_v1.md"


def load_plan() -> dict[str, Any]:
    return json.loads(PLAN_PATH.read_text(encoding="utf-8"))


def file_sha256(relative_path: str) -> str:
    return hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest()


def all_primary_rows(plan: dict[str, Any]) -> list[dict[str, Any]]:
    pools = plan["split_pools"]
    return (
        pools["train_development"]
        + pools["dev_calibration"]
        + pools["test_untouched"]
    )


def test_top_level_schema_date_token_and_nonresult_boundary() -> None:
    plan = load_plan()

    assert plan["schema_version"] == (
        "av-trace.source-disjoint-scaleup-wave/1.0"
    )
    assert plan["plan_id"] == "SOURCE_DISJOINT_SCALEUP_WAVE_V1"
    assert plan["created_date"] == "2026-10-14"
    assert plan["decision_token"] == (
        "SOURCE_DISJOINT_SCALEUP_WAVE_V1_READY"
    )
    assert plan["final_token"] == "SOURCE_DISJOINT_SCALEUP_WAVE_V1_READY"
    assert plan["current_decision"] == "REPAIR"

    scope = plan["scope"]
    assert scope["human_semantic_review_performed_by_this_plan"] is False
    assert scope["model_candidate_mining_performed_by_this_plan"] is False
    assert scope["new_media_acquired_by_this_plan"] is False
    assert scope["rights_authority_created_by_this_plan"] is False
    assert scope["h2_families_created_by_this_plan"] == 0
    assert scope["scientific_execution_authorized"] is False
    assert scope["causal_or_model_claim_authorized"] is False
    assert scope["public_release_authorized"] is False


def test_authoritative_input_hashes_are_pinned_and_current() -> None:
    inputs = load_plan()["authoritative_inputs"]
    assert len(inputs) >= 12
    paths = [row["path"] for row in inputs]
    assert len(paths) == len(set(paths))

    for row in inputs:
        assert file_sha256(row["path"]) == row["sha256"]


def test_preferred_and_fallback_scale_contract_matches_frozen_pivot() -> None:
    contract = load_plan()["frozen_scale_contract"]
    preferred = contract["preferred"]

    assert preferred["minimum_h2_families"] == 60
    assert preferred["minimum_source_groups"] == 30
    assert preferred["minimum_untouched_test_source_groups"] == 12
    assert preferred["source_split"] == {
        "train_development": 12,
        "dev_calibration": 6,
        "test_untouched": 12,
    }
    assert preferred["h2_target_split"] == {
        "train_development": 24,
        "dev_calibration": 12,
        "test_untouched": 24,
    }
    assert preferred["maximum_h2_families_per_source"] == 3
    assert (
        preferred[
            "minimum_untouched_test_sources_per_modality_mechanism_or_domain_claim"
        ]
        == 5
    )

    fallback = contract["descriptive_fallback"]
    assert fallback["minimum_h2_families"] == 60
    assert fallback["minimum_source_groups"] == 20
    assert fallback["minimum_untouched_test_source_groups"] == 8
    assert fallback["sufficient_for_causal_claims"] is False
    assert fallback["sufficient_for_controller_superiority_claims"] is False
    assert fallback["sufficient_for_population_ranking_claims"] is False
    assert (
        fallback["sufficient_for_broad_modality_mechanism_generalization"]
        is False
    )


def test_exact_30_group_split_is_unique_and_source_disjoint() -> None:
    plan = load_plan()
    pools = plan["split_pools"]

    assert len(pools["train_development"]) == 12
    assert len(pools["dev_calibration"]) == 6
    assert len(pools["test_untouched"]) == 12

    rows = all_primary_rows(plan)
    assert len(rows) == 30
    source_ids = [row["source_group_id"] for row in rows]
    participant_ids = [row["participant_block_id"] for row in rows]
    production_ids = [row["production_lineage_id"] for row in rows]

    assert len(source_ids) == len(set(source_ids))
    assert len(participant_ids) == len(set(participant_ids))
    assert len(production_ids) == len(set(production_ids))

    split_sources = {
        split: {row["source_group_id"] for row in split_rows}
        for split, split_rows in pools.items()
    }
    assert split_sources["train_development"].isdisjoint(
        split_sources["dev_calibration"]
    )
    assert split_sources["train_development"].isdisjoint(
        split_sources["test_untouched"]
    )
    assert split_sources["dev_calibration"].isdisjoint(
        split_sources["test_untouched"]
    )


def test_p23_is_development_only_and_never_test_eligible() -> None:
    pools = load_plan()["split_pools"]
    p23 = next(
        row
        for row in pools["train_development"]
        if row["source_group_id"] == "P23"
    )

    assert p23["exact_object_or_session_id"] == "P23_102"
    assert p23["local_media_state"] == "COMPLETE_VERIFIED_READY"
    assert p23["test_eligible"] is False
    assert all(
        row["source_group_id"] != "P23"
        for row in pools["test_untouched"]
    )


def test_test_pool_is_exact_and_semantically_locked() -> None:
    test_rows = load_plan()["split_pools"]["test_untouched"]
    assert [row["slot"] for row in test_rows] == [
        "TS-01",
        "TS-02",
        "TS-03",
        "TS-04",
        "TS-05",
        "TS-06",
        "TS-07",
        "TS-08",
        "TS-09",
        "TS-10",
        "TS-11",
        "TS-12",
    ]
    assert [row["source_group_id"] for row in test_rows] == [
        "P01",
        "P02",
        "P04",
        "cc4d_p04_e05",
        "cc4d_p06_e02",
        "cc4d_p07_e02",
        "assembly101_p9056",
        "assembly101_p9083",
        "assembly101_p9055",
        "EC-USGS-SHIFT-CURVES",
        "EC-NASA-TO-THE-RESCUE",
        "EC-NARA-CITY-UNDER-ICE",
    ]
    assert all(
        row["semantic_exposure_allowed_now"] is False for row in test_rows
    )
    assert all(
        row["current_state"].startswith("RESERVED_UNTOUCHED")
        for row in test_rows
    )

    policy = load_plan()["untouched_test_policy"]
    forbidden = " ".join(policy["forbidden_before_test_unlock"]).lower()
    assert "model-guided candidate mining" in forbidden
    assert "human semantic prescreen" in forbidden
    assert "question, answer, claim" in forbidden
    assert policy["development_staff_may_review_test_sources"] is False
    assert (
        policy[
            "test_staff_may_have_prior_semantic_exposure_to_train_or_dev_sources"
        ]
        is False
    )


def test_exact_authoring_h2_profile_and_structural_counts() -> None:
    design = load_plan()["preferred_authoring_design"]
    assert design["source_groups"] == 30
    assert design["candidate_families_authored"] == 90
    assert design["candidates_per_source"] == 3
    assert design["h2_target"] == 60
    assert design["h2_target_per_source"] == 2
    assert design["maximum_h2_per_source"] == 3

    split_counts = design["split_counts"]
    assert sum(row["source_groups"] for row in split_counts.values()) == 30
    assert (
        sum(row["candidate_families"] for row in split_counts.values()) == 90
    )
    assert sum(row["h2_target"] for row in split_counts.values()) == 60

    candidate_profiles = design["candidate_profile_targets"]
    h2_profiles = design["h2_profile_targets"]
    assert sum(
        sum(profile.values()) for profile in candidate_profiles.values()
    ) == 90
    assert sum(sum(profile.values()) for profile in h2_profiles.values()) == 60
    assert design["structural_targets"] == {
        "candidate_multi_hop": 45,
        "candidate_far_or_separated": 45,
        "h2_multi_hop": 30,
        "h2_far_or_separated": 30,
        "h2_silent_route_withholding": 30,
        "h2_explicit_channel_outage": 30,
    }
    assert design["targets_are_forced_labels"] is False
    assert "Never force" in design["failed_target_policy"]


def test_ranked_reserve_pools_are_exact_and_fail_closed() -> None:
    reserves = load_plan()["reserve_pools"]
    assert [
        reserves[key]["rank"]
        for key in (
            "epic_participants",
            "captaincook4d_participant_groups",
            "assembly101_participant_groups",
            "independent_public_or_rights_ready_lineages",
        )
    ] == [1, 2, 3, 4]

    assert [
        row["source_group_id"]
        for row in reserves["epic_participants"]["same_split_replacements"]
    ] == ["P35", "P33", "P22", "P03"]
    assert reserves["captaincook4d_participant_groups"][
        "same_split_replacements"
    ][0]["participant_block_id"] == "CC4D:P08"
    assert [
        row["source_group_id"]
        for row in reserves["assembly101_participant_groups"][
            "same_split_replacements"
        ]
    ] == [
        "assembly101_p9044",
        "assembly101_p9081",
        "assembly101_p9043",
        "assembly101_p9066",
        "assembly101_p9024",
    ]
    independent = reserves["independent_public_or_rights_ready_lineages"]
    assert independent["current_rights_ready_count"] == 0
    assert independent["status"] == "REPAIR_CRITICAL_DIVERSITY_GAP"


def test_admission_gates_cover_identity_rights_duration_audio_and_humans() -> None:
    gates = load_plan()["admission_gates"]
    assert set(gates) == {
        "acquisition_identity",
        "rights_privacy",
        "duration",
        "audio_video",
        "human_semantic_eligibility",
    }
    assert gates["duration"]["preferred_inclusive_seconds"] == [1200, 5400]
    audio = " ".join(gates["audio_video"]["requirements"])
    assert "native synchronized audio" in audio
    assert "0.25 seconds" in audio
    assert gates["audio_video"]["subtitles_or_transcripts_prove_audio"] is False
    semantic = " ".join(gates["human_semantic_eligibility"]["requirements"])
    assert "multi-hop coherent" in semantic
    assert "music, score, applause" in semantic


def test_six_role_review_counts_blindness_and_rosters() -> None:
    review = load_plan()["human_review_contract"]
    assert review["candidate_families_receiving_six_role_review"] == 90
    assert review["roles_per_family"] == 6
    assert review["distinct_people_per_family"] == 6
    assert review["total_role_assignments"] == 540
    assert review["roles"] == [
        "question_claim_author_or_independent_verifier",
        "blind_full_source_alternative_evidence_finder",
        "validator_a",
        "validator_b",
        "independent_adjudicator",
        "blind_post_adjudication_saturation_auditor",
    ]
    roster = review["reviewer_roster"]
    assert roster["train_and_dev_unique_reviewers"] == 18
    assert roster["test_only_unique_reviewers"] == 12
    assert roster["total_unique_reviewers"] == 30
    blindness = " ".join(review["source_level_blindness"]).lower()
    assert "at most one family" in blindness
    assert "invalidates affected packets" in blindness


def test_narrowing_is_prospective_and_never_forces_labels() -> None:
    triggers = load_plan()["prospective_narrowing_triggers"]
    assert [row["trigger_id"] for row in triggers] == [
        "NARROW-01-VSA",
        "NARROW-02-FAR",
        "NARROW-03-YIELD",
        "NARROW-04-TEST-POOL",
        "NARROW-05-CLAIM-SUPPORT",
    ]
    joined = " ".join(
        row["required_action"] + " " + row["prohibited_action"]
        for row in triggers
    ).lower()
    assert "before test authoring" in joined
    assert "do not force a" in joined
    assert "do not mine the untouched test pool" in joined
    assert "fewer than five untouched test source groups" in triggers[-1][
        "trigger"
    ].lower()


def test_wave_order_keeps_model_execution_after_h2_freeze() -> None:
    waves = load_plan()["wave_sequence"]
    assert [row["wave"] for row in waves] == list(range(7))
    assert [row["name"] for row in waves] == [
        "SPLIT_AND_LEDGER_FREEZE",
        "RIGHTS_AND_TECHNICAL_ADMISSION",
        "TRAIN_DEVELOPMENT_AUTHORING",
        "DEV_CALIBRATION_AND_PROTOCOL_LOCK",
        "TEST_UNLOCK_AND_HUMAN_ONLY_AUTHORING",
        "PAPER_SCALE_GATE",
        "MODEL_EXECUTION_AFTER_H2_FREEZE",
    ]
    assert "No model execution occurs before this gate." in waves[5]["work"]
    assert waves[6]["entry"].startswith("Preferred GO")


def test_contamination_ledger_is_complete_and_fail_closed() -> None:
    ledger = load_plan()["contamination_ledger"]
    assert ledger["required"] is True
    assert set(ledger["required_fields"]) >= {
        "timestamp_utc",
        "person_or_system_id",
        "source_group_id",
        "participant_block_id",
        "production_lineage_id",
        "split",
        "artifact_or_tool",
        "exposure_class",
        "semantic_fields_visible",
        "packet_hash_before",
        "packet_hash_after",
        "disposition",
    }
    assert "MODEL_OR_EMBEDDING_EXPOSURE" in ledger["exposure_classes"]
    invalidation = " ".join(ledger["automatic_invalidation"]).lower()
    assert "pre-unlock semantic or model exposure" in invalidation
    assert "unlogged exposure fails closed" in invalidation


def test_budget_arithmetic_is_exact() -> None:
    budget = load_plan()["budget_estimate"]
    human = budget["human_semantic_labor"]
    assert human["six_role_hours_per_candidate_family"] == 9.25
    assert human["six_role_hours"] == 832.5
    assert human["total_hours"] == 1162.5
    assert human["cost"] == 52312.5

    computed_subtotal = (
        human["cost"]
        + budget["rights_privacy_and_component_review"]["cost"]
        + budget["engineering_acquisition_indexing_and_ledger"]["cost"]
        + budget["program_management_and_qc"]["cost"]
        + budget["storage_compute_and_secure_custody"]["cost"]
    )
    assert computed_subtotal == budget["subtotal"] == 121912.5
    assert budget["contingency"] == (
        budget["subtotal"] * budget["contingency_fraction"]
    )
    assert budget["total_cap"] == 146295


def test_go_repair_no_go_rules_preserve_claim_firewall() -> None:
    rules = load_plan()["decision_rules"]
    assert rules["current_classification"] == "REPAIR"
    preferred = " ".join(rules["GO_PREFERRED"]["all_required"])
    assert "At least 60" in preferred
    assert "At least 30" in preferred
    assert "At least 12" in preferred
    fallback = rules["GO_DESCRIPTIVE_FALLBACK"]["claim_scope"].lower()
    assert "descriptive" in fallback
    assert "insufficient" in fallback
    assert "causal/model-effect claims" in fallback
    no_go = " ".join(rules["NO_GO"]).lower()
    assert "60/20/8" in no_go
    assert "model-guided test mining" in no_go
    assert "six roles or saturation audit" in no_go


def test_markdown_matches_machine_contract_and_finishes_with_marker() -> None:
    text = DOC_PATH.read_text(encoding="utf-8")
    assert "at least **60**" in text
    assert "**30 source groups**" in text
    assert "**12 prospectively untouched test" in text
    assert "60/20/8 fallback" in text
    assert "descriptive and insufficient" in text
    assert "540 role assignments" in text
    assert "$146,295" in text
    assert "targets, **not forced labels**" in text
    assert "model-guided test authoring and candidate mining remain prohibited" in (
        text.replace("**", "").lower()
    )
    assert text.rstrip().endswith(
        "`SOURCE_DISJOINT_SCALEUP_WAVE_V1_READY`"
    )
