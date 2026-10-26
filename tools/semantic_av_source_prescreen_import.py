#!/usr/bin/env python3
"""Validate semantic source prescreens and emit source-level exposure records."""

from __future__ import annotations

import argparse
import copy
import hashlib
from pathlib import Path
from typing import Any

try:
    from .construct_validity_common import (
        exposure_event_hash,
        exposure_snapshot_hash,
        validate_reviewer_assignment_ledger,
        validate_source_exposure_ledger,
    )
    from .semantic_av_source_prescreen_common import (
        BLIND_ROLE_EXCLUSIONS,
        IMPORT_SCHEMA,
        NO_GO,
        READY,
        REPAIR,
        SemanticPrescreenError,
        exposure_ledger_hash,
        load_json,
        parse_datetime,
        validate_annotation,
        validate_exposure_ledger,
        validate_instance,
        validate_plan,
        write_json,
    )
except ImportError:
    from construct_validity_common import (
        exposure_event_hash,
        exposure_snapshot_hash,
        validate_reviewer_assignment_ledger,
        validate_source_exposure_ledger,
    )
    from semantic_av_source_prescreen_common import (
        BLIND_ROLE_EXCLUSIONS,
        IMPORT_SCHEMA,
        NO_GO,
        READY,
        REPAIR,
        SemanticPrescreenError,
        exposure_ledger_hash,
        load_json,
        parse_datetime,
        validate_annotation,
        validate_exposure_ledger,
        validate_instance,
        validate_plan,
        write_json,
    )


def token_for(decision: str) -> str:
    return {"pass": READY, "no_go": NO_GO}.get(decision, REPAIR)


def source_errors(
    review: dict[str, Any],
    expected_samples: dict[str, float],
    *,
    completed: bool,
) -> list[str]:
    errors = []
    sample_reviews = review["sample_reviews"]
    actual_ids = [item["sample_id"] for item in sample_reviews]
    expected_sample_ids = list(expected_samples)
    if actual_ids != expected_sample_ids:
        errors.append("SAMPLE_SET_OR_ORDER_MISMATCH")
    if not completed:
        return errors + ["FORM_NOT_COMPLETED"]
    if any(item["review_status"] != "reviewed" for item in sample_reviews):
        errors.append("UNREVIEWED_INTERVAL")
    if any(item["speech_presence"] == "unknown" for item in sample_reviews):
        errors.append("SPEECH_PRESENCE_UNKNOWN")
    if any(
        risk["level"] == "unknown"
        for item in sample_reviews
        for risk in item["substitution_risk"].values()
    ):
        errors.append("SUBSTITUTION_RISK_UNKNOWN")
    if review["temporal_recurrence"]["assessment_status"] != "complete":
        errors.append("RECURRENCE_NOT_ASSESSED")
    if review["privacy_review"]["assessment_status"] == "not_assessed":
        errors.append("PRIVACY_NOT_ASSESSED")
    if review["safety_review"]["assessment_status"] == "not_assessed":
        errors.append("SAFETY_NOT_ASSESSED")
    if review["authoring_eligibility"] == "undecided":
        errors.append("AUTHORING_ELIGIBILITY_UNDECIDED")
    if not review["decision_rationale"].strip():
        errors.append("DECISION_RATIONALE_MISSING")

    observation_modalities: dict[str, str] = {}
    observation_fact_links: dict[str, set[str]] = {}
    fact_links: dict[str, set[str]] = {}
    sample_id_set = set(expected_sample_ids)
    for sample in sample_reviews:
        for field, modality in (
            ("dynamic_non_text_visual_events", "vision"),
            ("concrete_non_speech_audio_events", "non_speech_audio"),
        ):
            for event in sample[field]:
                observation_id = event["observation_id"]
                if observation_id in observation_modalities:
                    errors.append("DUPLICATE_OBSERVATION_ID")
                observation_modalities[observation_id] = modality
                if event["end_offset_s"] <= event["start_offset_s"]:
                    errors.append("INVALID_OBSERVATION_INTERVAL")
                if event["end_offset_s"] > expected_samples.get(
                    sample["sample_id"], 0.0
                ):
                    errors.append("OBSERVATION_OUTSIDE_SAMPLE_INTERVAL")
                observation_fact_links[observation_id] = set(
                    event["candidate_fact_ids"]
                )
                for fact_id in event["candidate_fact_ids"]:
                    fact_links.setdefault(fact_id, set()).add(observation_id)

    fact_ids = [fact["fact_id"] for fact in review["candidate_facts"]]
    if len(fact_ids) != len(set(fact_ids)):
        errors.append("DUPLICATE_FACT_ID")
    fact_id_set = set(fact_ids)
    if set(fact_links) - fact_id_set:
        errors.append("OBSERVATION_REFERENCES_UNKNOWN_FACT")
    for fact in review["candidate_facts"]:
        if not set(fact["sample_ids"]) <= sample_id_set:
            errors.append("FACT_REFERENCES_UNKNOWN_SAMPLE")
        if not any(
            carrier["carries_fact"] for carrier in fact["carried_by"].values()
        ):
            errors.append("FACT_HAS_NO_CARRYING_MODALITY")
        for modality, carrier in fact["carried_by"].items():
            observation_ids = carrier["observation_ids"]
            if carrier["carries_fact"] is not bool(observation_ids):
                errors.append("FACT_CARRIER_BOOLEAN_REFERENCE_MISMATCH")
            if modality in {"vision", "non_speech_audio"} and any(
                observation_modalities.get(observation_id) != modality
                for observation_id in observation_ids
            ):
                errors.append("FACT_CARRIER_MODALITY_MISMATCH")
            if modality in {"vision", "non_speech_audio"} and any(
                fact["fact_id"]
                not in observation_fact_links.get(observation_id, set())
                for observation_id in observation_ids
            ):
                errors.append("FACT_OBSERVATION_LINK_NOT_BIDIRECTIONAL")
            if modality == "speech" and any(
                observation_id not in sample_id_set for observation_id in observation_ids
            ):
                errors.append("SPEECH_FACT_MUST_REFERENCE_SAMPLE_ID")
            if modality == "speech" and any(
                next(
                    (
                        sample["speech_presence"]
                        for sample in sample_reviews
                        if sample["sample_id"] == observation_id
                    ),
                    "unknown",
                )
                not in {"possible", "present"}
                for observation_id in observation_ids
            ):
                errors.append("SPEECH_FACT_REFERENCES_NON_SPEECH_SAMPLE")
    for group in review["temporal_recurrence"]["groups"]:
        if not set(group["sample_ids"]) <= sample_id_set:
            errors.append("RECURRENCE_REFERENCES_UNKNOWN_SAMPLE")

    unresolved = [
        concern
        for field in ("privacy_review", "safety_review")
        for concern in review[field]["concerns"]
        if concern["severity"] in {"high", "critical"}
        and concern["mitigation_status"] == "unresolved"
    ]
    for field, prefix in (
        ("privacy_review", "PRIVACY"),
        ("safety_review", "SAFETY"),
    ):
        assessment = review[field]
        if (
            assessment["assessment_status"] == "concern_present"
            and not assessment["concerns"]
        ):
            errors.append(f"{prefix}_CONCERN_STATUS_WITHOUT_CONCERN")
        if (
            assessment["assessment_status"] == "no_concern"
            and assessment["concerns"]
        ):
            errors.append(f"{prefix}_NO_CONCERN_STATUS_WITH_CONCERNS")
    if review["authoring_eligibility"] == "pass":
        if not review["candidate_facts"]:
            errors.append("PASS_REQUIRES_CANDIDATE_FACT")
        if unresolved:
            errors.append("PASS_WITH_UNRESOLVED_HIGH_CONCERN")
        if any(
            risk["level"] == "high"
            for item in sample_reviews
            for risk in item["substitution_risk"].values()
        ) and not review["authoring_constraints"]:
            errors.append("PASS_HIGH_SUBSTITUTION_RISK_REQUIRES_CONSTRAINT")
    if review["authoring_eligibility"] == "repair" and not review["repair_actions"]:
        errors.append("REPAIR_REQUIRES_ACTION")
    return sorted(set(errors))


def build_exposure_ledger(
    plan: dict[str, Any], annotation: dict[str, Any]
) -> dict[str, Any]:
    events = []
    if annotation["completion_status"] == "completed":
        reviewer = annotation["reviewer"]
        for review in annotation["source_reviews"]:
            sample_ids = [
                item["sample_id"] for item in review["sample_reviews"]
            ]
            events.append(
                {
                    "event_id": (
                        f"{annotation['form_id']}.{review['source_id']}."
                        "semantic-prescreen"
                    ),
                    "reviewer_id": reviewer["reviewer_id"],
                    "source_id": review["source_id"],
                    "source_group_id": review["source_group_id"],
                    "sample_ids": sample_ids,
                    "exposure_categories": [
                        "source_content",
                        "candidate_semantic_facts",
                    ],
                    "started_at": reviewer["started_at"],
                    "completed_at": reviewer["completed_at"],
                    "blind_role_exclusions": BLIND_ROLE_EXCLUSIONS,
                }
            )
    ledger = {
        "schema_version": "1.0.0",
        "record_type": "semantic_av_source_prescreen_exposure_ledger",
        "plan_id": plan["plan_id"],
        "form_id": annotation["form_id"],
        "ledger_status": "SOURCE_LEVEL_BLIND_ROLE_EXCLUSIONS",
        "events": events,
        "ledger_sha256": "",
    }
    ledger["ledger_sha256"] = exposure_ledger_hash(ledger)
    validate_exposure_ledger(ledger)
    return ledger


def evaluate(
    plan: dict[str, Any], annotation: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_plan(plan)
    validate_annotation(annotation)
    if annotation["plan_id"] != plan["plan_id"]:
        raise SemanticPrescreenError("annotation plan_id mismatch")
    if annotation["plan_sha256"] != plan["plan_sha256"]:
        raise SemanticPrescreenError("annotation plan_sha256 mismatch")
    completed = annotation["completion_status"] == "completed"
    reviewer = annotation["reviewer"]
    global_errors = []
    if completed:
        if not reviewer["reviewer_id"] or not reviewer["training_attested"]:
            global_errors.append("TRAINED_REVIEWER_REQUIRED")
        if not reviewer["started_at"] or not reviewer["completed_at"]:
            global_errors.append("REVIEW_TIMESTAMPS_REQUIRED")
        elif parse_datetime(reviewer["completed_at"]) < parse_datetime(
            reviewer["started_at"]
        ):
            global_errors.append("REVIEW_TIME_ORDER_INVALID")

    samples_by_source: dict[tuple[str, str], dict[str, float]] = {}
    for sample in plan["samples"]:
        key = (sample["source_id"], sample["source_group_id"])
        samples_by_source.setdefault(key, {})[sample["sample_id"]] = (
            sample["end_s"] - sample["start_s"]
        )
    review_keys = [
        (review["source_id"], review["source_group_id"])
        for review in annotation["source_reviews"]
    ]
    if set(review_keys) != set(samples_by_source) or len(review_keys) != len(
        set(review_keys)
    ):
        raise SemanticPrescreenError("annotation source review set mismatch")

    source_results = []
    for review in annotation["source_reviews"]:
        key = (review["source_id"], review["source_group_id"])
        errors = source_errors(review, samples_by_source[key], completed=completed)
        effective = review["authoring_eligibility"]
        token = token_for(effective)
        if global_errors or errors:
            effective = "repair" if effective != "no_go" else "no_go"
            token = REPAIR if effective == "repair" else NO_GO
        sample_reviews = review["sample_reviews"]
        source_results.append(
            {
                "source_id": review["source_id"],
                "source_group_id": review["source_group_id"],
                "authoring_eligibility": effective,
                "readiness_token": token,
                "sample_count": len(sample_reviews),
                "candidate_fact_count": len(review["candidate_facts"]),
                "dynamic_visual_event_count": sum(
                    len(item["dynamic_non_text_visual_events"])
                    for item in sample_reviews
                ),
                "concrete_non_speech_audio_event_count": sum(
                    len(item["concrete_non_speech_audio_events"])
                    for item in sample_reviews
                ),
                "speech_present_sample_count": sum(
                    item["speech_presence"] == "present" for item in sample_reviews
                ),
                "exposure_recorded": completed and not global_errors,
                "blind_finder_eligible": False,
                "saturation_auditor_eligible": False,
                "errors": sorted(set(global_errors + errors)),
            }
        )
    tokens = {item["readiness_token"] for item in source_results}
    if tokens == {READY}:
        overall = READY
    elif tokens == {NO_GO}:
        overall = NO_GO
    else:
        overall = REPAIR
    report = {
        "schema_version": "1.0.0",
        "record_type": "semantic_av_source_prescreen_import",
        "plan_id": plan["plan_id"],
        "form_id": annotation["form_id"],
        "completion_status": (
            "valid"
            if completed and not global_errors and all(not item["errors"] for item in source_results)
            else "incomplete"
        ),
        "readiness_token": overall,
        "source_results": source_results,
        "prescreener_exposure_required": True,
        "blind_role_exclusion_required": True,
        "necessity_assigned": False,
        "h1_assigned": False,
        "h2_assigned": False,
        "errors": sorted(set(global_errors)),
    }
    validate_instance(report, IMPORT_SCHEMA, "prescreen import report")
    ledger = build_exposure_ledger(plan, annotation)
    return report, ledger


def bridge_construct_ledgers(
    prescreen_ledger: dict[str, Any],
    construct_exposure: dict[str, Any],
    construct_assignments: dict[str, Any],
    *,
    artifact_reference: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Add prescreen exposures to the frozen pre-distribution snapshot."""
    validate_exposure_ledger(prescreen_ledger)
    validate_source_exposure_ledger(construct_exposure)
    validate_reviewer_assignment_ledger(construct_assignments)
    if construct_assignments["assignment_status"] != "DRAFT_NOT_DISTRIBUTABLE":
        raise SemanticPrescreenError(
            "prescreen exposures must be bridged before assignment freeze"
        )
    if construct_exposure["review_events"]:
        raise SemanticPrescreenError(
            "cannot rewrite a construct pre-distribution snapshot after review events"
        )
    if construct_assignments["source_groups"] != construct_exposure["source_groups"]:
        raise SemanticPrescreenError("construct ledger source-group maps differ")
    known_groups = {
        item["source_group_id"] for item in construct_exposure["source_groups"]
    }
    updated_exposure = copy.deepcopy(construct_exposure)
    snapshot = updated_exposure["pre_distribution_snapshot"]
    prior = snapshot["events"][-1]["event_sha256"] if snapshot["events"] else None
    sequence = len(snapshot["events"]) + 1
    for event in prescreen_ledger["events"]:
        if event["source_group_id"] not in known_groups:
            raise SemanticPrescreenError(
                f"construct ledger lacks source group {event['source_group_id']}"
            )
        event_suffix = hashlib.sha256(event["event_id"].encode("utf-8")).hexdigest()[
            :32
        ]
        bridged = {
            "event_id": f"semantic-prescreen:{event_suffix}",
            "sequence": sequence,
            "previous_event_sha256": prior,
            "reviewer_id": event["reviewer_id"],
            "source_group_id": event["source_group_id"],
            "family_id": None,
            "role": "external_prior_work",
            "exposure_categories": ["source_content", "preferred_evidence"],
            "exposed_at": event["started_at"],
            "recorded_at": event["completed_at"],
            "artifact_references": [artifact_reference],
            "notes": (
                "Human semantic source prescreen exposure; reviewer is excluded "
                "from both blind source-search roles for this source group."
            ),
            "event_sha256": "",
        }
        bridged["event_sha256"] = exposure_event_hash(bridged)
        snapshot["events"].append(bridged)
        prior = bridged["event_sha256"]
        sequence += 1
    if prescreen_ledger["events"]:
        latest = max(event["completed_at"] for event in prescreen_ledger["events"])
        if parse_datetime(latest) > parse_datetime(snapshot["captured_at"]):
            snapshot["captured_at"] = latest
    updated_exposure["pre_distribution_snapshot_sha256"] = exposure_snapshot_hash(
        snapshot
    )
    updated_assignments = copy.deepcopy(construct_assignments)
    updated_assignments["pre_distribution_exposure_snapshot_sha256"] = (
        updated_exposure["pre_distribution_snapshot_sha256"]
    )
    validate_source_exposure_ledger(updated_exposure)
    validate_reviewer_assignment_ledger(updated_assignments)
    return updated_exposure, updated_assignments


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--form", type=Path, required=True)
    parser.add_argument("--report-out", type=Path, required=True)
    parser.add_argument("--exposure-ledger-out", type=Path, required=True)
    parser.add_argument("--construct-exposure-in", type=Path)
    parser.add_argument("--construct-exposure-out", type=Path)
    parser.add_argument("--construct-assignments-in", type=Path)
    parser.add_argument("--construct-assignments-out", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        plan = load_json(args.plan)
        annotation = load_json(args.form)
        report, ledger = evaluate(plan, annotation)
        write_json(args.report_out, report)
        write_json(args.exposure_ledger_out, ledger)
        bridge_args = (
            args.construct_exposure_in,
            args.construct_exposure_out,
            args.construct_assignments_in,
            args.construct_assignments_out,
        )
        if any(bridge_args):
            if not all(bridge_args):
                raise SemanticPrescreenError(
                    "all four construct ledger bridge paths are required"
                )
            exposure, assignments = bridge_construct_ledgers(
                ledger,
                load_json(args.construct_exposure_in),
                load_json(args.construct_assignments_in),
                artifact_reference=str(args.exposure_ledger_out),
            )
            write_json(args.construct_exposure_out, exposure)
            write_json(args.construct_assignments_out, assignments)
    except SemanticPrescreenError as exc:
        print(f"ERROR: {exc}")
        return 2
    print(report["readiness_token"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
