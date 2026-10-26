from __future__ import annotations

import copy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from tools.construct_validity_common import (
    blank_reviewer_assignment_ledger,
    blank_source_exposure_ledger,
    exposure_snapshot_hash,
    freeze_reviewer_assignment_ledger,
    source_level_assignment_conflicts,
    validate_reviewer_assignment_ledger,
    validate_source_exposure_ledger,
)
from tools.semantic_av_source_prescreen_common import (
    ANNOTATION_SCHEMA,
    EXPOSURE_SCHEMA,
    IMPORT_SCHEMA,
    INVENTORY_SCHEMA,
    NO_GO,
    PLAN_SCHEMA,
    READY,
    REPAIR,
    SemanticPrescreenError,
    load_json,
    sha256_file,
    validate_exposure_ledger,
    validate_inventory,
    validate_plan,
)
from tools.semantic_av_source_prescreen_import import (
    bridge_construct_ledgers,
    evaluate,
)
from tools.semantic_av_source_prescreen_plan import build_blank_annotation, build_plan

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = (
    ROOT
    / "data/rehearsal_plan/semantic_av_source_prescreen_portable_blank_inventory.json"
)
PORTABLE_PLAN = (
    ROOT / "data/rehearsal_plan/semantic_av_source_prescreen_portable_blank_plan.json"
)
PORTABLE_FORM = (
    ROOT / "data/rehearsal_plan/semantic_av_source_prescreen_portable_blank_form.json"
)
PORTABLE_IMPORT = (
    ROOT / "data/rehearsal_plan/semantic_av_source_prescreen_portable_blank_import.json"
)
PORTABLE_EXPOSURE = (
    ROOT
    / "data/rehearsal_plan/"
    "semantic_av_source_prescreen_portable_blank_exposure_ledger.json"
)


def make_plan() -> dict:
    inventory = load_json(INVENTORY)
    return build_plan(
        inventory,
        inventory_sha256=sha256_file(INVENTORY),
        plan_id="test-plan",
        created_at="2026-09-23T00:00:00+00:00",
        seed="test-seed",
        sample_count=6,
        interval_duration_s=12,
    )


def complete_form(
    plan: dict,
    *,
    decisions: tuple[str, str] = ("pass", "pass"),
) -> dict:
    form = build_blank_annotation(plan, form_id="test-form")
    form["completion_status"] = "completed"
    form["reviewer"].update(
        reviewer_id="trained-prescreener-1",
        training_attested=True,
        started_at="2026-09-23T01:00:00+00:00",
        completed_at="2026-09-23T02:00:00+00:00",
    )
    for source_index, review in enumerate(form["source_reviews"]):
        sample_ids = [item["sample_id"] for item in review["sample_reviews"]]
        first_sample = review["sample_reviews"][0]
        fact_id = f"fact-{source_index + 1}"
        visual_id = f"visual-{source_index + 1}"
        audio_id = f"audio-{source_index + 1}"
        for sample in review["sample_reviews"]:
            sample["review_status"] = "reviewed"
            sample["speech_presence"] = "absent"
            for risk in sample["substitution_risk"].values():
                risk.update(level="none", notes="No substituting text or narration.")
        first_sample["dynamic_non_text_visual_events"] = [
            {
                "observation_id": visual_id,
                "start_offset_s": 1.0,
                "end_offset_s": 4.0,
                "description": "A visible object changes state.",
                "dynamic": True,
                "non_text": True,
                "candidate_fact_ids": [fact_id],
            }
        ]
        first_sample["concrete_non_speech_audio_events"] = [
            {
                "observation_id": audio_id,
                "start_offset_s": 2.0,
                "end_offset_s": 3.0,
                "description": "A concrete impact sound occurs.",
                "concrete": True,
                "non_speech": True,
                "candidate_fact_ids": [fact_id],
            }
        ]
        review["candidate_facts"] = [
            {
                "fact_id": fact_id,
                "fact_statement": "The operation completes with a visible state change and impact.",
                "sample_ids": [sample_ids[0]],
                "carried_by": {
                    "vision": {
                        "carries_fact": True,
                        "observation_ids": [visual_id],
                        "notes": "Visible state change.",
                    },
                    "non_speech_audio": {
                        "carries_fact": True,
                        "observation_ids": [audio_id],
                        "notes": "Impact corroborates completion.",
                    },
                    "speech": {
                        "carries_fact": False,
                        "observation_ids": [],
                        "notes": "No speech.",
                    },
                },
                "substitution_resistant": True,
                "authoring_caution": "This is a candidate fact, not necessity evidence.",
            }
        ]
        review["temporal_recurrence"].update(
            assessment_status="complete",
            groups=[],
            notes="No recurrence detected in sampled intervals.",
        )
        review["privacy_review"].update(
            assessment_status="no_concern",
            notes="No privacy concern in sampled intervals.",
        )
        review["safety_review"].update(
            assessment_status="no_concern",
            notes="No safety concern in sampled intervals.",
        )
        review["authoring_eligibility"] = decisions[source_index]
        review["decision_rationale"] = "All required prescreen fields were reviewed."
        if decisions[source_index] == "repair":
            review["repair_actions"] = ["Resolve substitution risk before authoring."]
        if decisions[source_index] == "no_go":
            review["decision_rationale"] = "Source is not eligible for authoring."
    return form


def construct_records(plan: dict) -> list[dict]:
    records = []
    seen = set()
    for sample in plan["samples"]:
        if sample["source_group_id"] in seen:
            continue
        seen.add(sample["source_group_id"])
        records.append(
            {
                "family_id": f"family-{len(records) + 1}",
                "source_id": sample["source_group_id"],
            }
        )
    return records


def test_prescreen_schemas_are_valid_draft_2020_12():
    for path in (
        INVENTORY_SCHEMA,
        PLAN_SCHEMA,
        ANNOTATION_SCHEMA,
        IMPORT_SCHEMA,
        EXPOSURE_SCHEMA,
    ):
        schema = load_json(path)
        Draft202012Validator.check_schema(schema)
        assert schema["$id"].startswith(
            "urn:av-trace:schema:semantic-av-source-prescreen-"
        )


def test_portable_inventory_and_plan_are_label_free_and_deterministic():
    inventory = load_json(INVENTORY)
    validate_inventory(inventory)
    plan = load_json(PORTABLE_PLAN)
    validate_plan(plan)
    rebuilt = build_plan(
        inventory,
        inventory_sha256=sha256_file(INVENTORY),
        plan_id=plan["plan_id"],
        created_at=plan["created_at"],
        seed=plan["seed"],
        sample_count=plan["sample_count"],
        interval_duration_s=plan["interval_duration_s"],
    )
    assert rebuilt == plan
    assert plan["semantic_labels_present"] is False
    assert {
        len([s for s in plan["samples"] if s["source_id"] == source_id])
        for source_id in ("portable-source-a", "portable-source-b")
    } == {3}
    assert all(
        sample["adapter_request"]["extract_media"] is False
        for sample in plan["samples"]
    )


def test_blank_portable_example_fails_closed_without_exposure_or_h_tiers():
    plan = load_json(PORTABLE_PLAN)
    form = load_json(PORTABLE_FORM)
    expected_report = load_json(PORTABLE_IMPORT)
    expected_exposure = load_json(PORTABLE_EXPOSURE)
    report, exposure = evaluate(plan, form)
    assert report == expected_report
    assert exposure == expected_exposure
    assert report["readiness_token"] == REPAIR
    assert report["completion_status"] == "incomplete"
    assert report["necessity_assigned"] is False
    assert report["h1_assigned"] is False
    assert report["h2_assigned"] is False
    assert exposure["events"] == []


def test_completed_pass_prescreen_is_ready_but_never_assigns_necessity_or_h():
    plan = make_plan()
    report, exposure = evaluate(plan, complete_form(plan))
    assert report["readiness_token"] == READY
    assert all(item["readiness_token"] == READY for item in report["source_results"])
    assert all(item["blind_finder_eligible"] is False for item in report["source_results"])
    assert all(item["saturation_auditor_eligible"] is False for item in report["source_results"])
    assert report["necessity_assigned"] is False
    assert report["h1_assigned"] is False
    assert report["h2_assigned"] is False
    assert len(exposure["events"]) == 2
    validate_exposure_ledger(exposure)


def test_mixed_source_decisions_yield_repair_and_all_no_go_yields_no_go():
    plan = make_plan()
    mixed, _ = evaluate(plan, complete_form(plan, decisions=("pass", "no_go")))
    assert mixed["readiness_token"] == REPAIR
    rejected, _ = evaluate(plan, complete_form(plan, decisions=("no_go", "no_go")))
    assert rejected["readiness_token"] == NO_GO


def test_pass_fails_closed_on_unknown_substitution_risk():
    plan = make_plan()
    form = complete_form(plan)
    form["source_reviews"][0]["sample_reviews"][0]["substitution_risk"][
        "caption"
    ]["level"] = "unknown"
    report, _ = evaluate(plan, form)
    first = report["source_results"][0]
    assert first["readiness_token"] == REPAIR
    assert "SUBSTITUTION_RISK_UNKNOWN" in first["errors"]


def test_observation_outside_sample_interval_fails_closed():
    plan = make_plan()
    form = complete_form(plan)
    form["source_reviews"][0]["sample_reviews"][0][
        "dynamic_non_text_visual_events"
    ][0]["end_offset_s"] = 13.0
    report, _ = evaluate(plan, form)
    first = report["source_results"][0]
    assert first["readiness_token"] == REPAIR
    assert "OBSERVATION_OUTSIDE_SAMPLE_INTERVAL" in first["errors"]


def test_plan_rejects_nonuniform_impossible_allocation():
    inventory = load_json(INVENTORY)
    with pytest.raises(SemanticPrescreenError, match="at least the number"):
        build_plan(
            inventory,
            inventory_sha256=sha256_file(INVENTORY),
            plan_id="bad-plan",
            created_at="2026-09-23T00:00:00+00:00",
            seed="test-seed",
            sample_count=1,
            interval_duration_s=12,
        )


def test_prescreener_is_bridged_into_construct_source_ledger_and_conflicts():
    plan = make_plan()
    _, prescreen_exposure = evaluate(plan, complete_form(plan))
    records = construct_records(plan)
    construct_exposure = blank_source_exposure_ledger(
        packet_id="construct-packet", records=records
    )
    assignments = blank_reviewer_assignment_ledger(
        packet_id="construct-packet",
        records=records,
        pre_distribution_exposure_snapshot_sha256=construct_exposure[
            "pre_distribution_snapshot_sha256"
        ],
    )
    bridged_exposure, bridged_assignments = bridge_construct_ledgers(
        prescreen_exposure,
        construct_exposure,
        assignments,
        artifact_reference="prescreen-exposure.json",
    )
    validate_source_exposure_ledger(bridged_exposure)
    validate_reviewer_assignment_ledger(bridged_assignments)
    assert len(bridged_exposure["pre_distribution_snapshot"]["events"]) == 2
    assert bridged_assignments[
        "pre_distribution_exposure_snapshot_sha256"
    ] == exposure_snapshot_hash(bridged_exposure["pre_distribution_snapshot"])

    for assignment in bridged_assignments["assignments"]:
        assignment["reviewer_id"] = f"reviewer-{assignment['assignment_id']}"
        assignment["assigned_at"] = "2026-09-23T02:30:00+00:00"
    target_group = records[0]["source_id"]
    for assignment in bridged_assignments["assignments"]:
        if (
            assignment["source_group_id"] == target_group
            and assignment["role"] == "blind_alternative_evidence_finder"
        ):
            assignment["reviewer_id"] = "trained-prescreener-1"
    frozen = freeze_reviewer_assignment_ledger(
        bridged_assignments, frozen_at="2026-09-23T03:00:00+00:00"
    )
    conflicts = source_level_assignment_conflicts(frozen, bridged_exposure)
    target_family = next(
        record["family_id"]
        for record in records
        if record["source_id"] == target_group
    )
    assert "SOURCE_GROUP_BLIND_ROLE_EXPOSURE_CONFLICT" in conflicts[target_family]


def test_bridge_rejects_after_construct_assignment_freeze():
    plan = make_plan()
    _, prescreen_exposure = evaluate(plan, complete_form(plan))
    records = construct_records(plan)
    construct_exposure = blank_source_exposure_ledger(
        packet_id="construct-packet", records=records
    )
    assignments = blank_reviewer_assignment_ledger(
        packet_id="construct-packet",
        records=records,
        pre_distribution_exposure_snapshot_sha256=construct_exposure[
            "pre_distribution_snapshot_sha256"
        ],
    )
    for assignment in assignments["assignments"]:
        assignment["reviewer_id"] = f"reviewer-{assignment['assignment_id']}"
        assignment["assigned_at"] = "2026-09-23T02:30:00+00:00"
    assignments = freeze_reviewer_assignment_ledger(
        assignments, frozen_at="2026-09-23T03:00:00+00:00"
    )
    with pytest.raises(SemanticPrescreenError, match="before assignment freeze"):
        bridge_construct_ledgers(
            prescreen_exposure,
            construct_exposure,
            assignments,
            artifact_reference="prescreen-exposure.json",
        )


def test_plan_hash_tampering_is_rejected():
    plan = copy.deepcopy(make_plan())
    plan["samples"][0]["start_s"] += 1
    with pytest.raises(SemanticPrescreenError, match="plan_sha256 mismatch"):
        validate_plan(plan)
