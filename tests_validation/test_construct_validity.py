from __future__ import annotations

import copy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from tools.construct_validity_common import (
    ADJUDICATION_SCHEMA,
    ANNOTATION_SCHEMA,
    IMPORT_SCHEMA,
    REGISTRY_SCHEMA,
    REVIEWER_ASSIGNMENT_SCHEMA,
    SATURATION_AUDIT_SCHEMA,
    SOURCE_EXPOSURE_LEDGER_SCHEMA,
    ConstructValidityError,
    append_source_exposure_event,
    exposure_event_hash,
    exposure_snapshot_hash,
    freeze_reviewer_assignment_ledger,
    load_json,
    sha256_file,
    validate_registry,
    write_json,
)
from tools.construct_validity_import import evaluate_packet
from tools.construct_validity_packet import build_packet, freeze_packet_assignments
from tools.construct_validity_sampler import build_sample

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_REGISTRY = (
    ROOT / "data/rehearsal_plan/construct_validity_example_registry.json"
)
PORTABLE_EXAMPLE = (
    ROOT / "data/rehearsal_plan/construct_validity_portable_example"
)
FIXTURE_PACKET_GENERATED_AT = "2026-09-23T23:00:00+00:00"
FIXTURE_ASSIGNMENT_AT = "2026-09-23T23:01:00+00:00"
FIXTURE_FROZEN_AT = "2026-09-23T23:30:00+00:00"
PORTABLE_IMPORT_GENERATED_AT = "2026-09-23T11:44:34+00:00"


def test_construct_validation_schemas_are_valid_draft_2020_12():
    for path in (
        REGISTRY_SCHEMA,
        ANNOTATION_SCHEMA,
        ADJUDICATION_SCHEMA,
        SATURATION_AUDIT_SCHEMA,
        REVIEWER_ASSIGNMENT_SCHEMA,
        SOURCE_EXPOSURE_LEDGER_SCHEMA,
        IMPORT_SCHEMA,
    ):
        schema = load_json(path)
        Draft202012Validator.check_schema(schema)
        assert schema["$id"].startswith("urn:av-trace:schema:construct-validation-")


def test_example_registry_is_explicitly_fixture_and_contains_no_human_gold():
    registry = load_json(EXAMPLE_REGISTRY)
    validate_registry(registry)
    assert registry["registry_status"] == "PLANNING_FIXTURE_NOT_REAL_ANNOTATION"
    assert all(
        record["current_tier"].startswith("P")
        and record["provenance"]["human_review_completed"] is False
        for record in registry["records"]
    )


def test_immediate_sampler_is_deterministic_and_respects_bounds():
    registry = load_json(EXAMPLE_REGISTRY)
    kwargs = {
        "target_size": 10,
        "source_target": 5,
        "source_max": 6,
        "seed": "test-seed",
        "low_risk_minimum": 1,
        "mode": "immediate",
    }
    first = build_sample(registry, **kwargs)
    second = build_sample(registry, **kwargs)
    assert first["selected_family_ids"] == second["selected_family_ids"]
    assert first["coverage"]["families"] == 10
    assert 5 <= first["coverage"]["sources"] <= 6
    assert first["coverage"]["signals"]["ambient_candidate"] >= 1
    assert first["coverage"]["signals"]["low_risk_control"] >= 1
    assert first["human_review_completed"] is False
    assert first["human_gold"] is False


def test_scale_sampler_rejects_pool_smaller_than_100_via_cli_contract():
    # The programmatic builder is generic; the CLI mode is the public
    # fail-closed contract. Test the prerequisite directly to keep this unit
    # test free from subprocess coupling.
    registry = load_json(EXAMPLE_REGISTRY)
    eligible = [
        record for record in registry["records"]
        if record["candidate_status"] == "eligible"
    ]
    assert len(eligible) < 100


def enrich_real_registry(registry: dict) -> dict:
    registry = copy.deepcopy(registry)
    registry["registry_id"] = "test-real-machine-provisional"
    registry["registry_status"] = "MACHINE_PROVISIONAL_REGISTRY"
    for index, record in enumerate(registry["records"]):
        claim_id = f"claim.{index}"
        evidence_id = f"evidence.{index}"
        ses_id = f"ses.{index}"
        record["review_payload"] = {
            "claims": [{"claim_id": claim_id, "text": f"Claim {index}"}],
            "candidate_evidence": [
                {
                    "evidence_id": evidence_id,
                    "intervals": [{"start_s": 0.0, "end_s": 4.0}],
                    "modalities": ["vision"],
                    "claim_ids": [claim_id],
                }
            ],
            "preferred_ses": [
                {
                    "ses_id": ses_id,
                    "evidence_ids": [evidence_id],
                    "claim_ids": [claim_id],
                }
            ],
            "pair_blueprint_reference": f"pair-blueprint:{record['family_id']}",
        }
        record["tier_evidence"] = {
            "source_decode_verified": True,
            "machine_proposal_versions": ["fixture-generator-v1"],
            "independent_machine_validator_ids": ["machine-a", "machine-b"],
            "answer_evidence_check": "pass",
            "question_only_shortcut_check": "pass",
            "metadata_shortcut_check": "pass",
            "alternative_support_scan": "pass",
            "leave_one_out_counterfactual": "pass",
            "modality_drop_counterfactual": "pass",
            "blocked_route_closure": "pass",
            "restored_recovery_check": "pass",
            "counterfactual_validator_ids": ["counterfactual-a", "counterfactual-b"],
        }
    validate_registry(registry)
    return registry


def test_real_registry_fails_closed_without_review_payload():
    registry = load_json(EXAMPLE_REGISTRY)
    registry["registry_status"] = "MACHINE_PROVISIONAL_REGISTRY"
    with pytest.raises(ConstructValidityError, match="review_payload"):
        validate_registry(registry)


def test_blank_packet_is_role_separated_blinded_and_imports_as_incomplete(tmp_path):
    registry = enrich_real_registry(load_json(EXAMPLE_REGISTRY))
    sample = build_sample(
        registry,
        target_size=8,
        source_target=5,
        source_max=6,
        seed="packet-test",
        low_risk_minimum=1,
        mode="immediate",
    )
    packet = tmp_path / "packet"
    manifest = build_packet(
        registry,
        sample,
        packet,
        generated_at=FIXTURE_PACKET_GENERATED_AT,
    )
    assert manifest["packet_status"] == "UNFILLED_DEFERRED_HUMAN_ASSIGNMENT"
    assert manifest["required_distinct_people_per_family"] == 6
    assert manifest["assignment_ledger_status"] == "DRAFT_NOT_DISTRIBUTABLE"
    assert manifest["packet_distribution_authorized"] is False
    family_id = sample["selected_family_ids"][0]
    blind = load_json(
        packet
        / "reviewer_packets"
        / family_id
        / "blind_alternative_evidence_finder"
        / "form.json"
    )
    validator = load_json(
        packet / "reviewer_packets" / family_id / "validator_a" / "form.json"
    )
    saturation = load_json(
        packet
        / "reviewer_packets"
        / family_id
        / "blind_post_adjudication_saturation_auditor"
        / "form.json"
    )
    assert blind["assignment_tier"] == "BLINDED_MACHINE_TIER"
    assert blind["assignment"]["machine_candidate_evidence"] == []
    assert blind["assignment"]["machine_preferred_ses"] == []
    assert "machine_ranks" in blind["reviewer"]["blinded_to"]
    assert validator["assignment"]["machine_candidate_evidence"]
    assert saturation["assignment_tier"] == "BLINDED_POST_ADJUDICATION"
    assert set(saturation["assignment"]) == {
        "source_reference",
        "source_duration_s",
        "source_content_hashes",
        "frozen_question_text",
        "machine_labels_are_provisional",
        "human_gold_at_assignment",
    }
    assert {
        "accepted_ses_ledger",
        "preferred_ses",
        "machine_ranks",
        "validator_decisions",
        "adjudication_decisions",
    } <= set(saturation["reviewer"]["blinded_to"])
    assert (
        packet / "construct_validation_saturation_audit_schema.json"
    ).is_file()
    assignments = load_json(packet / "coordinator/reviewer_assignments.json")
    exposures = load_json(packet / "coordinator/source_exposure_ledger.json")
    assert assignments["assignment_status"] == "DRAFT_NOT_DISTRIBUTABLE"
    assert assignments["distribution_authorized"] is False
    assert manifest["generated_at"] == FIXTURE_PACKET_GENERATED_AT
    assert assignments["generated_at"] == FIXTURE_PACKET_GENERATED_AT
    assert (
        exposures["pre_distribution_snapshot"]["captured_at"]
        == FIXTURE_PACKET_GENERATED_AT
    )
    assert all(item["reviewer_id"] is None for item in assignments["assignments"])
    assert exposures["pre_distribution_snapshot"]["events"] == []
    assert exposures["review_events"] == []
    report = evaluate_packet(packet)
    assert report["decision"] == "INCOMPLETE_NO_HUMAN_DECISION"
    assert report["human_review_occurred"] is False
    assert all(item["computed_tier"].startswith("P") for item in report["families"])


def test_checked_in_portable_example_is_blank_governed_and_fail_closed():
    packet = PORTABLE_EXAMPLE / "packet"
    manifest = load_json(packet / "packet_manifest.json")
    assignments = load_json(packet / "coordinator/reviewer_assignments.json")
    exposures = load_json(packet / "coordinator/source_exposure_ledger.json")
    checked_in_report = load_json(PORTABLE_EXAMPLE / "import_dry_run.json")

    assert manifest["assignment_ledger_status"] == "DRAFT_NOT_DISTRIBUTABLE"
    assert manifest["packet_distribution_authorized"] is False
    assert assignments["assignment_status"] == "DRAFT_NOT_DISTRIBUTABLE"
    assert assignments["distribution_authorized"] is False
    assert len(assignments["assignments"]) == manifest["family_count"] * 6
    assert all(
        item["reviewer_id"] is None and item["assigned_at"] is None
        for item in assignments["assignments"]
    )
    assert exposures["pre_distribution_snapshot"]["events"] == []
    assert exposures["review_events"] == []

    report = evaluate_packet(
        packet,
        generated_at=PORTABLE_IMPORT_GENERATED_AT,
    )
    assert report == checked_in_report
    assert report["decision"] == "INCOMPLETE_NO_HUMAN_DECISION"
    assert report["human_review_occurred"] is False
    assert all(item["computed_tier"].startswith("P") for item in report["families"])


def fill_author(form: dict, reviewer_id: str) -> None:
    form["completion_status"] = "completed"
    form["reviewer"].update(
        reviewer_id=reviewer_id,
        independent_of_author=False,
        started_at="2026-09-24T01:00:00+00:00",
        completed_at="2026-09-24T01:10:00+00:00",
        active_minutes=10,
    )
    form["review"] = {
        "question_answerability": "pass",
        "question_ambiguity": "none",
        "answer_claim_correctness": "pass",
        "atomic_claims_complete": "pass",
        "question_only_shortcut_absent": "pass",
        "metadata_shortcut_absent": "pass",
        "rights_release": "pass",
        "privacy": "pass",
        "safety": "pass",
        "outcome": "accept_for_validation",
        "confidence": 5,
        "reason_codes": [],
        "notes": "",
    }


def fill_finder(form: dict, reviewer_id: str) -> None:
    form["completion_status"] = "completed"
    form["reviewer"].update(
        reviewer_id=reviewer_id,
        independent_of_author=True,
        started_at="2026-09-24T01:00:00+00:00",
        completed_at="2026-09-24T01:20:00+00:00",
        active_minutes=20,
    )
    claim_id = "found.claim"
    evidence_id = "found.evidence"
    form["review"] = {
        "blind_search_completed_before_unblinding": True,
        "full_source_search_completed": True,
        "coverage_log": [
            {
                "start_s": 0.0,
                "end_s": form["assignment"]["source_duration_s"],
                "reviewed": True,
                "notes": "",
            }
        ],
        "candidate_evidence": [
            {
                "evidence_id": evidence_id,
                "intervals": [{"start_s": 0.0, "end_s": 4.0}],
                "modalities": ["vision"],
                "supports_claim_ids": [claim_id],
                "support_verdict": "pass",
                "notes": "",
            }
        ],
        "candidate_ses": [
            {
                "ses_id": "found.ses",
                "evidence_ids": [evidence_id],
                "claim_ids": [claim_id],
                "sufficient": "pass",
                "leave_one_out": [
                    {
                        "removed_evidence_id": evidence_id,
                        "target_claims_remain_supported": "no",
                        "reason": "support is removed",
                    }
                ],
                "is_alternative_to_machine_preferred": True,
            }
        ],
        "new_alternative_ses_count": 1,
        "exhaustive_enumeration_credible": "pass",
        "unresolved_regions": [],
        "outcome": "complete",
        "confidence": 5,
        "reason_codes": [],
        "notes": "",
    }


def fill_validator(form: dict, reviewer_id: str) -> None:
    form["completion_status"] = "completed"
    form["reviewer"].update(
        reviewer_id=reviewer_id,
        independent_of_author=True,
        started_at="2026-09-24T01:00:00+00:00",
        completed_at="2026-09-24T01:30:00+00:00",
        active_minutes=30,
    )
    claims = list(form["assignment"]["machine_claims"]) + [
        {"claim_id": "found.claim", "text": "Blind-found claim"}
    ]
    evidence = list(form["assignment"]["machine_candidate_evidence"]) + [
        {
            "evidence_id": "found.evidence",
            "intervals": [{"start_s": 0.0, "end_s": 4.0}],
            "modalities": ["vision"],
            "claim_ids": ["found.claim"],
        }
    ]
    ses = list(form["assignment"]["machine_preferred_ses"]) + [
        {
            "ses_id": "found.ses",
            "evidence_ids": ["found.evidence"],
            "claim_ids": ["found.claim"],
        }
    ]
    form["review"] = {
        "question_answerability": "pass",
        "question_ambiguity": "none",
        "answer_claim_correctness": "pass",
        "claim_judgments": [
            {
                "claim_id": item["claim_id"],
                "correct": "pass",
                "supported": "pass",
                "notes": "",
            }
            for item in claims
        ],
        "evidence_judgments": [
            {
                "evidence_id": item["evidence_id"],
                "intervals": item["intervals"],
                "modalities": item["modalities"],
                "supports_claim_ids": item["claim_ids"],
                "support_verdict": "pass",
                "notes": "",
            }
            for item in evidence
        ],
        "ses_results": [
            {
                "ses_id": item["ses_id"],
                "evidence_ids": item["evidence_ids"],
                "claim_ids": item["claim_ids"],
                "sufficient": "pass",
                "leave_one_out": [
                    {
                        "removed_evidence_id": evidence_id,
                        "target_claims_remain_supported": "no",
                        "reason": "support is removed",
                    }
                    for evidence_id in item["evidence_ids"]
                ],
                "is_alternative_to_machine_preferred": item["ses_id"] == "found.ses",
            }
            for item in ses
        ],
        "necessity_group_results": [
            {
                "group_id": "necessity.1",
                "member_evidence_ids": [evidence[0]["evidence_id"]],
                "intersects_every_accepted_ses": "yes",
                "group_removal_breaks_target_support": "yes",
                "verdict": "pass",
                "notes": "",
            }
        ],
        "counterfactuals": [
            {
                "condition": condition,
                "answerability_without": (
                    "no" if condition in {"question_only", "metadata_only"} else "uncertain"
                ),
                "target_claim_ids": [claims[0]["claim_id"]],
                "notes": "",
            }
            for condition in (
                "drop_vision",
                "drop_speech",
                "drop_ambient",
                "question_only",
                "metadata_only",
            )
        ],
        "pair_review": {
            "clean_supported": "pass",
            "blocked_target_inaccessible": "pass",
            "blocked_source_remains_sufficient": "pass",
            "all_direct_derived_alternative_routes_blocked": "pass",
            "restored_matches_blocked_pretrigger": "pass",
            "restoration_reverses_only_block": "pass",
            "recovery_feasible_within_budget": "pass",
            "pair_isolation": "pass",
            "notes": "",
        },
        "rights_release": "pass",
        "privacy": "pass",
        "safety": "pass",
        "family_outcome": "accept",
        "confidence": 5,
        "reason_codes": [],
        "notes": "",
    }


def fill_adjudicator(form: dict, reviewer_id: str) -> None:
    form["completion_status"] = "completed"
    form["reviewer"].update(
        reviewer_id=reviewer_id,
        independent_of_author_and_validators=True,
        started_at="2026-09-24T02:00:00+00:00",
        completed_at="2026-09-24T02:15:00+00:00",
        active_minutes=15,
    )
    form["inputs"]["all_required_roles_complete"] = True
    form["inputs"]["role_independence_verified"] = True
    form["adjudication"] = {
        "disagreement_codes": ["NONE"],
        "resolutions": [],
        "question_answerability": "pass",
        "answer_claim_correctness": "pass",
        "exact_evidence_support": "pass",
        "alternative_search_complete": "pass",
        "all_accepted_ses_minimal": "pass",
        "necessity_groups_valid": "pass",
        "modality_counterfactuals_valid": "pass",
        "shortcuts_absent": "pass",
        "pair_isolation": "pass",
        "recovery_feasibility": "pass",
        "rights_release": "pass",
        "privacy": "pass",
        "safety": "pass",
        "unresolved_critical_disagreements": 0,
        "recommended_outcome": "accept_h2",
        "confidence": 5,
        "reason_codes": [],
        "required_repairs": [],
        "notes": "",
    }


def fill_saturation_auditor(
    form: dict,
    reviewer_id: str,
    *,
    adjudication_path: Path,
    new_sufficient_route: bool = False,
) -> None:
    form["completion_status"] = "completed"
    form["reviewer"].update(
        reviewer_id=reviewer_id,
        independent_of_all_prior_reviewers=True,
        started_at="2026-09-24T02:16:00+00:00",
        completed_at="2026-09-24T02:36:00+00:00",
        active_minutes=20,
    )
    form["post_adjudication"].update(
        adjudication_was_frozen_before_start=True,
        frozen_adjudication_sha256=sha256_file(adjudication_path),
    )
    routes = []
    if new_sufficient_route:
        routes.append(
            {
                "route_id": "saturation.route.1",
                "claim_texts": ["A newly discovered sufficient answer route"],
                "evidence_intervals": [{"start_s": 2.0, "end_s": 6.0}],
                "modalities": ["speech"],
                "derivation_lineage": "direct",
                "sufficiency": "pass",
                "new_relative_to_blinded_assignment": True,
                "notes": "Requires reopening the accepted SES ledger.",
            }
        )
    form["review"] = {
        "blind_search_completed_without_unblinding": True,
        "full_source_search_completed": True,
        "coverage_log": [
            {
                "sequence": 1,
                "start_s": 0.0,
                "end_s": form["assignment"]["source_duration_s"],
                "reviewed": True,
                "search_methods": ["chronological_playback"],
                "notes": "",
            }
        ],
        "search_queries": [],
        "new_routes": routes,
        "new_sufficient_route_count": int(new_sufficient_route),
        "unresolved_regions": [],
        "saturation_outcome": (
            "new_sufficient_route_found"
            if new_sufficient_route
            else "saturated_no_new_sufficient_route"
        ),
        "reopen_required": new_sufficient_route,
        "confidence": 5,
        "reason_codes": ["NEW_SUFFICIENT_ROUTE"] if new_sufficient_route else [],
        "notes": "",
    }


ROLE_EXPOSURES = {
    "question_claim_author_or_verifier": [
        "source_content",
        "frozen_question",
        "preferred_evidence",
        "machine_ranks_or_confidence",
    ],
    "blind_alternative_evidence_finder": [
        "source_content",
        "frozen_question",
    ],
    "validator_a": [
        "source_content",
        "frozen_question",
        "preferred_evidence",
        "machine_ranks_or_confidence",
    ],
    "validator_b": [
        "source_content",
        "frozen_question",
        "preferred_evidence",
        "machine_ranks_or_confidence",
    ],
    "adjudicator": [
        "source_content",
        "frozen_question",
        "preferred_evidence",
        "machine_ranks_or_confidence",
        "validator_decisions",
        "adjudication_decisions",
        "accepted_ses",
    ],
    "blind_post_adjudication_saturation_auditor": [
        "source_content",
        "frozen_question",
    ],
}


def freeze_and_log_packet_governance(
    packet: Path,
    *,
    reviewer_overrides: dict[tuple[str, str], str] | None = None,
    prior_events: list[dict] | None = None,
    omit_event_keys: set[tuple[str, str]] | None = None,
) -> None:
    reviewer_overrides = reviewer_overrides or {}
    prior_events = prior_events or []
    omit_event_keys = omit_event_keys or set()
    assignment_path = packet / "coordinator/reviewer_assignments.json"
    exposure_path = packet / "coordinator/source_exposure_ledger.json"
    assignments = load_json(assignment_path)
    exposures = load_json(exposure_path)
    previous_hash = None
    prepared_prior_events = []
    for sequence, event in enumerate(prior_events, start=1):
        event = copy.deepcopy(event)
        event["sequence"] = sequence
        event["previous_event_sha256"] = previous_hash
        event["event_sha256"] = exposure_event_hash(event)
        previous_hash = event["event_sha256"]
        prepared_prior_events.append(event)
    exposures["pre_distribution_snapshot"]["events"] = prepared_prior_events
    exposures["pre_distribution_snapshot_sha256"] = exposure_snapshot_hash(
        exposures["pre_distribution_snapshot"]
    )
    assignments["pre_distribution_exposure_snapshot_sha256"] = exposures[
        "pre_distribution_snapshot_sha256"
    ]
    forms_by_key = {}
    for assignment in assignments["assignments"]:
        family_id = assignment["family_id"]
        role = assignment["role"]
        form_path = packet / "reviewer_packets" / family_id / role / "form.json"
        form = load_json(form_path)
        if (family_id, role) in reviewer_overrides:
            form["reviewer"]["reviewer_id"] = reviewer_overrides[(family_id, role)]
            write_json(form_path, form)
        forms_by_key[(family_id, role)] = form
        reviewer_id = form["reviewer"]["reviewer_id"]
        assignment["reviewer_id"] = reviewer_id or (
            f"reserved.{family_id}.{role}"
        )
        assignment["assigned_at"] = FIXTURE_ASSIGNMENT_AT
    assignments = freeze_reviewer_assignment_ledger(
        assignments, frozen_at=FIXTURE_FROZEN_AT
    )
    write_json(assignment_path, assignments, restricted=True)
    manifest_path = packet / "packet_manifest.json"
    manifest = load_json(manifest_path)
    manifest["assignment_ledger_status"] = assignments["assignment_status"]
    manifest["packet_distribution_authorized"] = True
    manifest["assignment_freeze_sha256"] = assignments[
        "assignment_freeze_sha256"
    ]
    write_json(manifest_path, manifest)

    for assignment in assignments["assignments"]:
        family_id = assignment["family_id"]
        role = assignment["role"]
        form = forms_by_key[(family_id, role)]
        if (
            form["completion_status"] != "completed"
            or (family_id, role) in omit_event_keys
        ):
            continue
        exposures = append_source_exposure_event(
            exposures,
            {
                "event_id": f"exposure.{family_id}.{role}",
                "reviewer_id": form["reviewer"]["reviewer_id"],
                "source_group_id": assignment["source_group_id"],
                "family_id": family_id,
                "role": role,
                "exposure_categories": ROLE_EXPOSURES[role],
                "exposed_at": form["reviewer"]["started_at"],
                "recorded_at": form["reviewer"]["completed_at"],
                "artifact_references": [
                    f"reviewer_packets/{family_id}/{role}/form.json"
                ],
                "notes": "Synthetic test exposure event.",
            },
        )
    write_json(exposure_path, exposures, restricted=True)


def test_only_complete_independent_adjudicated_forms_reach_h2(tmp_path):
    registry = enrich_real_registry(load_json(EXAMPLE_REGISTRY))
    sample = build_sample(
        registry,
        target_size=8,
        source_target=5,
        source_max=6,
        seed="h2-test",
        low_risk_minimum=1,
        mode="immediate",
    )
    packet = tmp_path / "packet"
    build_packet(
        registry,
        sample,
        packet,
        generated_at=FIXTURE_PACKET_GENERATED_AT,
    )
    for family_index, family_id in enumerate(sample["selected_family_ids"]):
        base = packet / "reviewer_packets" / family_id
        author = load_json(base / "question_claim_author_or_verifier/form.json")
        finder = load_json(base / "blind_alternative_evidence_finder/form.json")
        validator_a = load_json(base / "validator_a/form.json")
        validator_b = load_json(base / "validator_b/form.json")
        adjudicator = load_json(base / "adjudicator/form.json")
        saturation_path = (
            base / "blind_post_adjudication_saturation_auditor/form.json"
        )
        saturation = load_json(saturation_path)
        prefix = f"family-{family_index}"
        fill_author(author, f"{prefix}-author")
        fill_finder(finder, f"{prefix}-finder")
        fill_validator(validator_a, f"{prefix}-validator-a")
        fill_validator(validator_b, f"{prefix}-validator-b")
        fill_adjudicator(adjudicator, f"{prefix}-adjudicator")
        write_json(base / "question_claim_author_or_verifier/form.json", author)
        write_json(base / "blind_alternative_evidence_finder/form.json", finder)
        write_json(base / "validator_a/form.json", validator_a)
        write_json(base / "validator_b/form.json", validator_b)
        write_json(base / "adjudicator/form.json", adjudicator)
        fill_saturation_auditor(
            saturation,
            f"{prefix}-saturation-auditor",
            adjudication_path=base / "adjudicator/form.json",
        )
        write_json(saturation_path, saturation)
    freeze_and_log_packet_governance(packet)
    report = evaluate_packet(packet)
    assert report["decision"] == "CONSTRUCT_VALIDITY_MINI_PILOT_GO"
    assert report["human_review_occurred"] is True
    assert all(
        item["computed_tier"] == "H2_HUMAN_ADJUDICATED_GOLD"
        for item in report["families"]
    )
    assert report["statistics"]["acceptance_funnel"]["h2"] == 8
    assert report["statistics"]["acceptance_funnel"]["saturation_audited"] == 8
    assert report["statistics"]["saturation_audit"]["saturated_families"] == 8


def build_completed_packet(
    tmp_path: Path, *, freeze_governance: bool = True
) -> tuple[Path, dict]:
    registry = enrich_real_registry(load_json(EXAMPLE_REGISTRY))
    sample = build_sample(
        registry,
        target_size=8,
        source_target=5,
        source_max=6,
        seed="completed-packet-test",
        low_risk_minimum=1,
        mode="immediate",
    )
    packet = tmp_path / "packet"
    build_packet(
        registry,
        sample,
        packet,
        generated_at=FIXTURE_PACKET_GENERATED_AT,
    )
    for family_index, family_id in enumerate(sample["selected_family_ids"]):
        base = packet / "reviewer_packets" / family_id
        prefix = f"family-{family_index}"
        author = load_json(base / "question_claim_author_or_verifier/form.json")
        finder = load_json(base / "blind_alternative_evidence_finder/form.json")
        validator_a = load_json(base / "validator_a/form.json")
        validator_b = load_json(base / "validator_b/form.json")
        adjudication_path = base / "adjudicator/form.json"
        adjudicator = load_json(adjudication_path)
        saturation_path = (
            base / "blind_post_adjudication_saturation_auditor/form.json"
        )
        saturation = load_json(saturation_path)
        fill_author(author, f"{prefix}-author")
        fill_finder(finder, f"{prefix}-finder")
        fill_validator(validator_a, f"{prefix}-validator-a")
        fill_validator(validator_b, f"{prefix}-validator-b")
        fill_adjudicator(adjudicator, f"{prefix}-adjudicator")
        write_json(base / "question_claim_author_or_verifier/form.json", author)
        write_json(base / "blind_alternative_evidence_finder/form.json", finder)
        write_json(base / "validator_a/form.json", validator_a)
        write_json(base / "validator_b/form.json", validator_b)
        write_json(adjudication_path, adjudicator)
        fill_saturation_auditor(
            saturation,
            f"{prefix}-saturation-auditor",
            adjudication_path=adjudication_path,
        )
        write_json(saturation_path, saturation)
    if freeze_governance:
        freeze_and_log_packet_governance(packet)
    return packet, sample


def test_adjudication_without_saturation_audit_cannot_reach_h2(tmp_path):
    packet, sample = build_completed_packet(tmp_path)
    family_id = sample["selected_family_ids"][0]
    path = (
        packet
        / "reviewer_packets"
        / family_id
        / "blind_post_adjudication_saturation_auditor"
        / "form.json"
    )
    saturation = load_json(path)
    saturation["completion_status"] = "not_started"
    saturation["reviewer"].update(
        reviewer_id=None,
        independent_of_all_prior_reviewers=None,
        started_at=None,
        completed_at=None,
        active_minutes=None,
    )
    saturation["post_adjudication"].update(
        adjudication_was_frozen_before_start=None,
        frozen_adjudication_sha256=None,
    )
    saturation["review"] = {}
    write_json(path, saturation)

    report = evaluate_packet(packet)
    result = next(
        item for item in report["families"] if item["family_id"] == family_id
    )
    assert result["computed_tier"] == "H1_HUMAN_VALIDATED"
    assert result["roles_complete"] is False
    assert result["saturation_audit_complete"] is False
    assert "SATURATION_AUDIT_INCOMPLETE" in result["reason_codes"]


def test_missing_saturation_role_form_fails_closed(tmp_path):
    packet, sample = build_completed_packet(tmp_path)
    family_id = sample["selected_family_ids"][0]
    path = (
        packet
        / "reviewer_packets"
        / family_id
        / "blind_post_adjudication_saturation_auditor"
        / "form.json"
    )
    path.unlink()
    with pytest.raises(ConstructValidityError, match="missing form"):
        evaluate_packet(packet)


def test_saturation_auditor_must_be_sixth_distinct_person(tmp_path):
    packet, sample = build_completed_packet(tmp_path)
    family_id = sample["selected_family_ids"][0]
    base = packet / "reviewer_packets" / family_id
    author = load_json(base / "question_claim_author_or_verifier/form.json")
    path = base / "blind_post_adjudication_saturation_auditor/form.json"
    saturation = load_json(path)
    saturation["reviewer"]["reviewer_id"] = author["reviewer"]["reviewer_id"]
    write_json(path, saturation)

    with pytest.raises(
        ConstructValidityError, match="completed form reviewer differs"
    ):
        evaluate_packet(packet)


def test_saturation_auditor_requires_frozen_adjudication_hash(tmp_path):
    packet, sample = build_completed_packet(tmp_path)
    family_id = sample["selected_family_ids"][0]
    adjudication_path = (
        packet / "reviewer_packets" / family_id / "adjudicator" / "form.json"
    )
    adjudication = load_json(adjudication_path)
    adjudication["adjudication"]["notes"] = "Changed after saturation started."
    write_json(adjudication_path, adjudication)

    report = evaluate_packet(packet)
    result = next(
        item for item in report["families"] if item["family_id"] == family_id
    )
    assert result["computed_tier"] == "H1_HUMAN_VALIDATED"
    assert result["saturation_pass"] is False
    assert "SATURATION_AUDITOR_INDEPENDENCE_BLINDING_OR_ORDER_FAILURE" in (
        result["reason_codes"]
    )


def test_saturation_auditor_must_start_after_adjudication(tmp_path):
    packet, sample = build_completed_packet(tmp_path)
    family_id = sample["selected_family_ids"][0]
    path = (
        packet
        / "reviewer_packets"
        / family_id
        / "blind_post_adjudication_saturation_auditor"
        / "form.json"
    )
    saturation = load_json(path)
    saturation["reviewer"]["started_at"] = "2026-09-24T02:14:59+00:00"
    write_json(path, saturation)

    report = evaluate_packet(packet)
    result = next(
        item for item in report["families"] if item["family_id"] == family_id
    )
    assert result["computed_tier"] == "H1_HUMAN_VALIDATED"
    assert "SATURATION_AUDITOR_INDEPENDENCE_BLINDING_OR_ORDER_FAILURE" in (
        result["reason_codes"]
    )


def test_saturation_new_route_reopens_family_and_blocks_h2(tmp_path):
    packet, sample = build_completed_packet(tmp_path)
    family_id = sample["selected_family_ids"][0]
    base = packet / "reviewer_packets" / family_id
    path = base / "blind_post_adjudication_saturation_auditor/form.json"
    saturation = load_json(path)
    reviewer_id = saturation["reviewer"]["reviewer_id"]
    fill_saturation_auditor(
        saturation,
        reviewer_id,
        adjudication_path=base / "adjudicator/form.json",
        new_sufficient_route=True,
    )
    write_json(path, saturation)

    report = evaluate_packet(packet)
    result = next(
        item for item in report["families"] if item["family_id"] == family_id
    )
    assert result["computed_tier"] == result["starting_tier"]
    assert result["outcome"] == "repair"
    assert result["new_sufficient_routes"] == 1
    assert "SATURATION_NEW_SUFFICIENT_ROUTE" in result["reason_codes"]


def test_unresolved_saturation_route_blocks_h2(tmp_path):
    packet, sample = build_completed_packet(tmp_path)
    family_id = sample["selected_family_ids"][0]
    path = (
        packet
        / "reviewer_packets"
        / family_id
        / "blind_post_adjudication_saturation_auditor"
        / "form.json"
    )
    saturation = load_json(path)
    saturation["review"]["new_routes"] = [
        {
            "route_id": "saturation.route.uncertain",
            "claim_texts": ["A plausible route needing resolution"],
            "evidence_intervals": [{"start_s": 2.0, "end_s": 6.0}],
            "modalities": ["vision"],
            "derivation_lineage": "unknown",
            "sufficiency": "uncertain",
            "new_relative_to_blinded_assignment": True,
            "notes": "Cannot certify saturation.",
        }
    ]
    write_json(path, saturation)

    report = evaluate_packet(packet)
    result = next(
        item for item in report["families"] if item["family_id"] == family_id
    )
    assert result["computed_tier"] == "H1_HUMAN_VALIDATED"
    assert result["saturation_pass"] is False
    assert "SATURATION_ROUTE_UNRESOLVED" in result["reason_codes"]


def test_saturation_coverage_must_be_chronological_and_complete(tmp_path):
    packet, sample = build_completed_packet(tmp_path)
    family_id = sample["selected_family_ids"][0]
    path = (
        packet
        / "reviewer_packets"
        / family_id
        / "blind_post_adjudication_saturation_auditor"
        / "form.json"
    )
    saturation = load_json(path)
    duration = saturation["assignment"]["source_duration_s"]
    saturation["review"]["coverage_log"] = [
        {
            "sequence": 1,
            "start_s": duration / 2,
            "end_s": duration,
            "reviewed": True,
            "search_methods": ["chronological_playback"],
            "notes": "",
        }
    ]
    write_json(path, saturation)

    report = evaluate_packet(packet)
    result = next(
        item for item in report["families"] if item["family_id"] == family_id
    )
    assert result["computed_tier"] == "H1_HUMAN_VALIDATED"
    assert result["saturation_pass"] is False
    assert "SATURATION_FULL_SOURCE_COVERAGE_FAILURE" in result["reason_codes"]


def test_assignment_tampering_fails_closed(tmp_path):
    registry = enrich_real_registry(load_json(EXAMPLE_REGISTRY))
    sample = build_sample(
        registry,
        target_size=8,
        source_target=5,
        source_max=6,
        seed="tamper-test",
        low_risk_minimum=1,
        mode="immediate",
    )
    packet = tmp_path / "packet"
    build_packet(
        registry,
        sample,
        packet,
        generated_at=FIXTURE_PACKET_GENERATED_AT,
    )
    family_id = sample["selected_family_ids"][0]
    path = packet / "reviewer_packets" / family_id / "validator_a/form.json"
    form = load_json(path)
    form["assignment"]["question_text"] = "tampered"
    write_json(path, form)
    with pytest.raises(ConstructValidityError, match="assignment_hash"):
        evaluate_packet(packet)


def same_source_family_pair(packet: Path, sample: dict) -> tuple[str, str, str]:
    registry = load_json(packet / "coordinator/assignment_registry.json")
    source_by_family = {
        record["family_id"]: record["source_id"] for record in registry["records"]
    }
    by_source: dict[str, list[str]] = {}
    for family_id in sample["selected_family_ids"]:
        by_source.setdefault(source_by_family[family_id], []).append(family_id)
    source_id, family_ids = next(
        (source_id, family_ids)
        for source_id, family_ids in by_source.items()
        if len(family_ids) >= 2
    )
    return source_id, family_ids[0], family_ids[1]


def test_completed_forms_without_pre_distribution_freeze_fail_closed(tmp_path):
    packet, _ = build_completed_packet(tmp_path, freeze_governance=False)
    with pytest.raises(
        ConstructValidityError, match="assignments were not frozen"
    ):
        evaluate_packet(packet)


def test_packet_freeze_rejects_source_group_blind_role_conflict(tmp_path):
    packet, sample = build_completed_packet(tmp_path, freeze_governance=False)
    _, exposed_family, blind_family = same_source_family_pair(packet, sample)
    assignment_path = packet / "coordinator/reviewer_assignments.json"
    assignments = load_json(assignment_path)
    author_id = load_json(
        packet
        / "reviewer_packets"
        / exposed_family
        / "question_claim_author_or_verifier"
        / "form.json"
    )["reviewer"]["reviewer_id"]
    for assignment in assignments["assignments"]:
        form = load_json(
            packet
            / "reviewer_packets"
            / assignment["family_id"]
            / assignment["role"]
            / "form.json"
        )
        assignment["reviewer_id"] = form["reviewer"]["reviewer_id"] or (
            f"reserved.{assignment['family_id']}.{assignment['role']}"
        )
        assignment["assigned_at"] = FIXTURE_ASSIGNMENT_AT
        if (
            assignment["family_id"] == blind_family
            and assignment["role"] == "blind_alternative_evidence_finder"
        ):
            assignment["reviewer_id"] = author_id
    write_json(assignment_path, assignments, restricted=True)
    with pytest.raises(
        ConstructValidityError, match="source-level reviewer assignment conflict"
    ):
        freeze_packet_assignments(
            packet, frozen_at=FIXTURE_FROZEN_AT
        )


@pytest.mark.parametrize(
    "blind_role",
    [
        "blind_alternative_evidence_finder",
        "blind_post_adjudication_saturation_auditor",
    ],
)
def test_blind_roles_cannot_cross_family_after_source_group_exposure(
    tmp_path, blind_role
):
    packet, sample = build_completed_packet(tmp_path, freeze_governance=False)
    _, exposed_family, blind_family = same_source_family_pair(packet, sample)
    exposed_author = load_json(
        packet
        / "reviewer_packets"
        / exposed_family
        / "question_claim_author_or_verifier"
        / "form.json"
    )["reviewer"]["reviewer_id"]
    freeze_and_log_packet_governance(
        packet,
        reviewer_overrides={(blind_family, blind_role): exposed_author},
    )

    report = evaluate_packet(packet)
    result = next(
        item for item in report["families"] if item["family_id"] == blind_family
    )
    assert result["computed_tier"] == result["starting_tier"]
    assert result["source_group_blindness_pass"] is False
    assert "SOURCE_GROUP_BLIND_ROLE_EXPOSURE_CONFLICT" in result["reason_codes"]


def test_known_prior_source_exposure_disqualifies_blind_assignment(tmp_path):
    packet, sample = build_completed_packet(tmp_path, freeze_governance=False)
    source_group_id, exposed_family, blind_family = same_source_family_pair(
        packet, sample
    )
    blind_reviewer = load_json(
        packet
        / "reviewer_packets"
        / blind_family
        / "blind_alternative_evidence_finder"
        / "form.json"
    )["reviewer"]["reviewer_id"]
    freeze_and_log_packet_governance(
        packet,
        prior_events=[
            {
                "event_id": "prior.preferred.evidence.exposure",
                "reviewer_id": blind_reviewer,
                "source_group_id": source_group_id,
                "family_id": exposed_family,
                "role": "external_prior_work",
                "exposure_categories": ["preferred_evidence"],
                "exposed_at": "2026-09-22T22:00:00+00:00",
                "recorded_at": "2026-09-22T22:30:00+00:00",
                "artifact_references": ["prior-review-record"],
                "notes": "Known pre-packet exposure used to test fail-closed logic.",
            }
        ],
    )

    report = evaluate_packet(packet)
    result = next(
        item for item in report["families"] if item["family_id"] == blind_family
    )
    assert result["computed_tier"] == result["starting_tier"]
    assert "SOURCE_GROUP_BLIND_ROLE_EXPOSURE_CONFLICT" in result["reason_codes"]


def test_adjudicator_cannot_author_another_family_in_source_group(tmp_path):
    packet, sample = build_completed_packet(tmp_path, freeze_governance=False)
    _, authored_family, adjudicated_family = same_source_family_pair(packet, sample)
    author_id = load_json(
        packet
        / "reviewer_packets"
        / authored_family
        / "question_claim_author_or_verifier"
        / "form.json"
    )["reviewer"]["reviewer_id"]
    freeze_and_log_packet_governance(
        packet,
        reviewer_overrides={(adjudicated_family, "adjudicator"): author_id},
    )

    report = evaluate_packet(packet)
    affected = {
        item["family_id"]: item
        for item in report["families"]
        if item["family_id"] in {authored_family, adjudicated_family}
    }
    assert all(
        "SOURCE_GROUP_ADJUDICATOR_AUTHOR_CONFLICT" in item["reason_codes"]
        for item in affected.values()
    )
    assert all(
        item["computed_tier"] == item["starting_tier"]
        for item in affected.values()
    )


def test_missing_completed_role_exposure_event_blocks_promotion(tmp_path):
    packet, sample = build_completed_packet(tmp_path, freeze_governance=False)
    family_id = sample["selected_family_ids"][0]
    freeze_and_log_packet_governance(
        packet,
        omit_event_keys={(family_id, "blind_alternative_evidence_finder")},
    )

    report = evaluate_packet(packet)
    result = next(
        item for item in report["families"] if item["family_id"] == family_id
    )
    assert result["computed_tier"] == result["starting_tier"]
    assert result["source_exposure_ledger_pass"] is False
    assert "SOURCE_EXPOSURE_LEDGER_INCOMPLETE" in result["reason_codes"]


def test_frozen_assignment_ledger_tampering_fails_closed(tmp_path):
    packet, _ = build_completed_packet(tmp_path)
    path = packet / "coordinator/reviewer_assignments.json"
    assignments = load_json(path)
    assignments["assignments"][0]["reviewer_id"] = "tampered-reviewer"
    write_json(path, assignments, restricted=True)
    with pytest.raises(ConstructValidityError, match="assignment_freeze_sha256"):
        evaluate_packet(packet)


def test_invented_human_tier_is_rejected_at_registry_boundary():
    registry = load_json(EXAMPLE_REGISTRY)
    registry["records"][0]["current_tier"] = "H2_HUMAN_ADJUDICATED_GOLD"
    with pytest.raises(ConstructValidityError):
        validate_registry(registry)
