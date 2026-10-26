#!/usr/bin/env python3
"""Validate completed offline forms and derive human tiers fail-closed."""

from __future__ import annotations

import argparse
import hashlib
import math
from collections import Counter
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from .construct_validity_common import (
        CRITICAL_PAIR_FIELDS,
        CRITICAL_VALIDATOR_FIELDS,
        IMPORT_SCHEMA,
        ROLES,
        SATURATION_AUDITOR_ROLE,
        ConstructValidityError,
        exposure_event_hash,
        load_json,
        now_utc,
        sha256_file,
        source_level_assignment_conflicts,
        validate_adjudication,
        validate_annotation,
        validate_instance,
        validate_registry,
        validate_reviewer_assignment_ledger,
        validate_saturation_audit,
        validate_source_exposure_ledger,
        write_json,
    )
except ImportError:
    from construct_validity_common import (
        CRITICAL_PAIR_FIELDS,
        CRITICAL_VALIDATOR_FIELDS,
        IMPORT_SCHEMA,
        ROLES,
        SATURATION_AUDITOR_ROLE,
        ConstructValidityError,
        exposure_event_hash,
        load_json,
        now_utc,
        sha256_file,
        source_level_assignment_conflicts,
        validate_adjudication,
        validate_annotation,
        validate_instance,
        validate_registry,
        validate_reviewer_assignment_ledger,
        validate_saturation_audit,
        validate_source_exposure_ledger,
        write_json,
    )


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> list[float] | None:
    if total == 0:
        return None
    p = successes / total
    denom = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denom
    half = (
        z
        * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total)
        / denom
    )
    return [max(0.0, center - half), min(1.0, center + half)]


def cohens_kappa(pairs: Iterable[tuple[str, str]]) -> float | None:
    pairs = list(pairs)
    if not pairs:
        return None
    labels = sorted({value for pair in pairs for value in pair})
    observed = sum(a == b for a, b in pairs) / len(pairs)
    counts_a = Counter(a for a, _ in pairs)
    counts_b = Counter(b for _, b in pairs)
    expected = sum(
        (counts_a[label] / len(pairs)) * (counts_b[label] / len(pairs))
        for label in labels
    )
    if math.isclose(expected, 1.0):
        return 1.0 if math.isclose(observed, 1.0) else None
    return (observed - expected) / (1 - expected)


def family_forms(
    packet_dir: Path, family_id: str, *, packet_id: str, source_id: str
) -> tuple[dict[str, dict], dict, dict]:
    family_dir = packet_dir / "reviewer_packets" / family_id
    forms = {}
    for role in ROLES:
        path = family_dir / role / "form.json"
        if not path.is_file():
            raise ConstructValidityError(f"missing form: {path}")
        form = load_json(path)
        validate_annotation(form)
        if (
            form["packet_id"] != packet_id
            or form["family_id"] != family_id
            or form["source_id"] != source_id
            or form["role"] != role
            or form["form_id"] != f"{packet_id}.{family_id}.{role}"
        ):
            raise ConstructValidityError(f"form identity/path mismatch: {path}")
        forms[role] = form
    adjudication_path = family_dir / "adjudicator" / "form.json"
    if not adjudication_path.is_file():
        raise ConstructValidityError(f"missing form: {adjudication_path}")
    adjudication = load_json(adjudication_path)
    validate_adjudication(adjudication)
    if (
        adjudication["packet_id"] != packet_id
        or adjudication["family_id"] != family_id
        or adjudication["source_id"] != source_id
        or adjudication["form_id"] != f"{packet_id}.{family_id}.adjudicator"
    ):
        raise ConstructValidityError(
            f"adjudication identity/path mismatch: {adjudication_path}"
        )
    saturation_path = family_dir / SATURATION_AUDITOR_ROLE / "form.json"
    if not saturation_path.is_file():
        raise ConstructValidityError(f"missing form: {saturation_path}")
    saturation_audit = load_json(saturation_path)
    validate_saturation_audit(saturation_audit)
    if (
        saturation_audit["packet_id"] != packet_id
        or saturation_audit["family_id"] != family_id
        or saturation_audit["source_id"] != source_id
        or saturation_audit["role"] != SATURATION_AUDITOR_ROLE
        or saturation_audit["form_id"]
        != f"{packet_id}.{family_id}.{SATURATION_AUDITOR_ROLE}"
        or saturation_audit["post_adjudication"]["adjudication_form_id"]
        != adjudication["form_id"]
    ):
        raise ConstructValidityError(
            f"saturation audit identity/path mismatch: {saturation_path}"
        )
    return forms, adjudication, saturation_audit


def verify_packet_immutable_artifacts(packet_dir: Path) -> None:
    manifest = load_json(packet_dir / "packet_manifest.json")
    if manifest.get("packet_status") != "UNFILLED_DEFERRED_HUMAN_ASSIGNMENT":
        raise ConstructValidityError("unexpected packet status")
    for artifact in manifest.get("artifacts", []):
        relative = artifact["path"]
        if artifact.get("mutable_completed_form") is True:
            continue
        path = packet_dir / relative
        if not path.is_file():
            raise ConstructValidityError(f"missing immutable packet artifact: {relative}")
        digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        if path.stat().st_size != artifact["bytes"] or digest != artifact["sha256"]:
            raise ConstructValidityError(
                f"immutable packet artifact changed: {relative}"
            )


def intervals_cover_source(
    coverage_log: list[dict[str, Any]], duration_s: float, tolerance_s: float = 1.0
) -> bool:
    intervals = sorted(
        (max(0.0, item["start_s"]), min(duration_s, item["end_s"]))
        for item in coverage_log
        if item["reviewed"] and item["end_s"] > item["start_s"]
    )
    if not intervals or intervals[0][0] > tolerance_s:
        return False
    cursor = intervals[0][1]
    for start, end in intervals[1:]:
        if start > cursor + tolerance_s:
            return False
        cursor = max(cursor, end)
    return cursor >= duration_s - tolerance_s


def chronological_coverage_complete(
    coverage_log: list[dict[str, Any]],
    duration_s: float,
    tolerance_s: float = 1.0,
) -> bool:
    if [item["sequence"] for item in coverage_log] != list(
        range(1, len(coverage_log) + 1)
    ):
        return False
    if any(
        item["end_s"] <= item["start_s"]
        or item["start_s"] > duration_s
        or item["end_s"] > duration_s + tolerance_s
        for item in coverage_log
    ):
        return False
    if any(
        coverage_log[index]["start_s"] < coverage_log[index - 1]["start_s"]
        for index in range(1, len(coverage_log))
    ):
        return False
    return intervals_cover_source(coverage_log, duration_s, tolerance_s)


def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


ROLE_EXPOSURE_REQUIREMENTS = {
    "question_claim_author_or_verifier": {
        "source_content",
        "frozen_question",
        "preferred_evidence",
        "machine_ranks_or_confidence",
    },
    "blind_alternative_evidence_finder": {
        "source_content",
        "frozen_question",
    },
    "validator_a": {
        "source_content",
        "frozen_question",
        "preferred_evidence",
        "machine_ranks_or_confidence",
    },
    "validator_b": {
        "source_content",
        "frozen_question",
        "preferred_evidence",
        "machine_ranks_or_confidence",
    },
    "adjudicator": {
        "source_content",
        "frozen_question",
        "preferred_evidence",
        "machine_ranks_or_confidence",
        "validator_decisions",
        "adjudication_decisions",
        "accepted_ses",
    },
    SATURATION_AUDITOR_ROLE: {
        "source_content",
        "frozen_question",
    },
}

def reviewer_governance(
    packet_dir: Path,
    *,
    packet_id: str,
    packet_manifest: dict[str, Any],
    records: dict[str, dict[str, Any]],
    loaded_forms: dict[str, tuple[dict[str, dict], dict, dict]],
) -> dict[str, Any]:
    assignment_path = packet_dir / "coordinator/reviewer_assignments.json"
    exposure_path = packet_dir / "coordinator/source_exposure_ledger.json"
    if not assignment_path.is_file():
        raise ConstructValidityError(f"missing reviewer assignment ledger: {assignment_path}")
    if not exposure_path.is_file():
        raise ConstructValidityError(f"missing source exposure ledger: {exposure_path}")
    assignments = load_json(assignment_path)
    exposures = load_json(exposure_path)
    validate_reviewer_assignment_ledger(assignments)
    validate_source_exposure_ledger(exposures)
    if assignments["packet_id"] != packet_id or exposures["packet_id"] != packet_id:
        raise ConstructValidityError("reviewer governance packet_id mismatch")
    if assignments["source_groups"] != exposures["source_groups"]:
        raise ConstructValidityError(
            "assignment and exposure source-group maps must be identical"
        )
    if (
        assignments["pre_distribution_exposure_snapshot_sha256"]
        != exposures["pre_distribution_snapshot_sha256"]
    ):
        raise ConstructValidityError(
            "assignment ledger is not bound to the exposure snapshot"
        )
    mapped_families = {
        family_id
        for group in assignments["source_groups"]
        for family_id in group["family_ids"]
    }
    if mapped_families != set(records):
        raise ConstructValidityError(
            "source-group governance map must cover exactly the packet families"
        )
    source_ids_by_family = {
        family_id: {
            source_id
            for group in assignments["source_groups"]
            if family_id in group["family_ids"]
            for source_id in group["source_ids"]
        }
        for family_id in mapped_families
    }
    for family_id, record in records.items():
        if record["source_id"] not in source_ids_by_family[family_id]:
            raise ConstructValidityError(
                f"source-group map omits source_id for {family_id}"
            )

    completed: list[tuple[str, str, dict[str, Any]]] = []
    for family_id, (forms, adjudication, saturation) in loaded_forms.items():
        for role, form in forms.items():
            if form["completion_status"] == "completed":
                completed.append((family_id, role, form))
        if adjudication["completion_status"] == "completed":
            completed.append((family_id, "adjudicator", adjudication))
        if saturation["completion_status"] == "completed":
            completed.append((family_id, SATURATION_AUDITOR_ROLE, saturation))
    human_review_occurred = bool(completed)
    if human_review_occurred and (
        assignments["assignment_status"] != "FROZEN_BEFORE_DISTRIBUTION"
        or assignments["distribution_authorized"] is not True
        or packet_manifest.get("assignment_ledger_status")
        != "FROZEN_BEFORE_DISTRIBUTION"
        or packet_manifest.get("packet_distribution_authorized") is not True
        or packet_manifest.get("assignment_freeze_sha256")
        != assignments["assignment_freeze_sha256"]
    ):
        raise ConstructValidityError(
            "human work exists but reviewer assignments were not frozen before distribution"
        )

    assignment_by_key = {
        (item["family_id"], item["role"]): item
        for item in assignments["assignments"]
    }
    family_failures: dict[str, set[str]] = {
        family_id: set() for family_id in records
    }
    freeze_pass = not human_review_occurred
    if human_review_occurred:
        frozen_at = parse_datetime(assignments["frozen_at"])
        snapshot_at = parse_datetime(
            exposures["pre_distribution_snapshot"]["captured_at"]
        )
        freeze_pass = snapshot_at <= frozen_at
        for assignment in assignments["assignments"]:
            assigned_at = parse_datetime(assignment["assigned_at"])
            freeze_pass = (
                freeze_pass
                and snapshot_at <= assigned_at
                and assigned_at <= frozen_at
            )
        if any(
            parse_datetime(event["exposed_at"]) < frozen_at
            for event in exposures["review_events"]
        ):
            freeze_pass = False
        for family_id, role, form in completed:
            assignment = assignment_by_key[(family_id, role)]
            reviewer_id = form["reviewer"]["reviewer_id"]
            if assignment["reviewer_id"] != reviewer_id:
                raise ConstructValidityError(
                    f"completed form reviewer differs from frozen assignment: "
                    f"{family_id}/{role}"
                )
            if parse_datetime(form["reviewer"]["started_at"]) < frozen_at:
                freeze_pass = False
                family_failures[family_id].add(
                    "ASSIGNMENTS_NOT_FROZEN_BEFORE_DISTRIBUTION"
                )
        if not freeze_pass:
            for failure_codes in family_failures.values():
                failure_codes.add(
                    "ASSIGNMENTS_NOT_FROZEN_BEFORE_DISTRIBUTION"
                )

    all_events = (
        exposures["pre_distribution_snapshot"]["events"]
        + exposures["review_events"]
    )
    event_categories: dict[tuple[str, str, str], set[str]] = {}
    for event in all_events:
        if parse_datetime(event["recorded_at"]) < parse_datetime(event["exposed_at"]):
            raise ConstructValidityError(
                f"exposure recorded before it occurred: {event['event_id']}"
            )
        if event["event_sha256"] != exposure_event_hash(event):
            raise ConstructValidityError(
                f"source exposure event hash mismatch: {event['event_id']}"
            )
        if event["family_id"] is not None:
            key = (event["family_id"], event["role"], event["reviewer_id"])
            event_categories.setdefault(key, set()).update(
                event["exposure_categories"]
            )

    exposure_ledger_pass = True
    for family_id, role, form in completed:
        reviewer_id = form["reviewer"]["reviewer_id"]
        categories = event_categories.get((family_id, role, reviewer_id), set())
        if not ROLE_EXPOSURE_REQUIREMENTS[role] <= categories:
            exposure_ledger_pass = False
            family_failures[family_id].add("SOURCE_EXPOSURE_LEDGER_INCOMPLETE")

    source_blindness_pass = True
    frozen_assignments = assignments["assignment_status"] == "FROZEN_BEFORE_DISTRIBUTION"
    if frozen_assignments:
        conflicts = source_level_assignment_conflicts(assignments, exposures)
        for family_id, reason_codes in conflicts.items():
            family_failures[family_id].update(reason_codes)
        source_blindness_pass = not any(conflicts.values())

    return {
        "assignment_status": assignments["assignment_status"],
        "assignment_freeze_pass": freeze_pass,
        "exposure_ledger_pass": exposure_ledger_pass,
        "source_blindness_pass": source_blindness_pass,
        "source_group_count": len(assignments["source_groups"]),
        "exposure_event_count": len(all_events),
        "family_failures": family_failures,
    }


def verdict_signature(review: dict[str, Any]) -> tuple[Any, ...]:
    pair = review["pair_review"]
    return (
        review["question_answerability"],
        review["answer_claim_correctness"],
        review["family_outcome"],
        *(pair[field] for field in CRITICAL_PAIR_FIELDS),
    )


def interval_iou(a: dict[str, float], b: dict[str, float]) -> float:
    intersection = max(0.0, min(a["end_s"], b["end_s"]) - max(a["start_s"], b["start_s"]))
    union = max(a["end_s"], b["end_s"]) - min(a["start_s"], b["start_s"])
    return intersection / union if union > 0 else 0.0


def validator_construct_agreement(
    a: dict[str, Any], b: dict[str, Any]
) -> bool:
    if verdict_signature(a) != verdict_signature(b):
        return False
    if {
        item["claim_id"]: (item["correct"], item["supported"])
        for item in a["claim_judgments"]
    } != {
        item["claim_id"]: (item["correct"], item["supported"])
        for item in b["claim_judgments"]
    }:
        return False
    evidence_a = {item["evidence_id"]: item for item in a["evidence_judgments"]}
    evidence_b = {item["evidence_id"]: item for item in b["evidence_judgments"]}
    if set(evidence_a) != set(evidence_b):
        return False
    for evidence_id, left in evidence_a.items():
        right = evidence_b[evidence_id]
        if (
            left["support_verdict"] != right["support_verdict"]
            or set(left["modalities"]) != set(right["modalities"])
            or set(left["supports_claim_ids"]) != set(right["supports_claim_ids"])
            or len(left["intervals"]) != len(right["intervals"])
        ):
            return False
        if any(
            interval_iou(ia, ib) < 0.5
            for ia, ib in zip(left["intervals"], right["intervals"])
        ):
            return False

    def ses_signature(review: dict[str, Any]) -> dict[str, Any]:
        return {
            item["ses_id"]: (
                tuple(sorted(item["evidence_ids"])),
                tuple(sorted(item["claim_ids"])),
                item["sufficient"],
                tuple(
                    sorted(
                        (
                            loo["removed_evidence_id"],
                            loo["target_claims_remain_supported"],
                        )
                        for loo in item["leave_one_out"]
                    )
                ),
            )
            for item in review["ses_results"]
        }

    def necessity_signature(review: dict[str, Any]) -> dict[str, Any]:
        return {
            item["group_id"]: (
                tuple(sorted(item["member_evidence_ids"])),
                item["intersects_every_accepted_ses"],
                item["group_removal_breaks_target_support"],
                item["verdict"],
            )
            for item in review["necessity_group_results"]
        }

    def counterfactual_signature(review: dict[str, Any]) -> dict[str, Any]:
        return {
            item["condition"]: (
                item["answerability_without"],
                tuple(sorted(item["target_claim_ids"])),
            )
            for item in review["counterfactuals"]
        }

    return (
        ses_signature(a) == ses_signature(b)
        and necessity_signature(a) == necessity_signature(b)
        and counterfactual_signature(a) == counterfactual_signature(b)
    )


def validator_critical_pass(review: dict[str, Any]) -> bool:
    pair = review["pair_review"]
    return (
        all(review[field] == "pass" for field in CRITICAL_VALIDATOR_FIELDS)
        and review["question_ambiguity"] in {"none", "minor"}
        and all(item["correct"] == "pass" and item["supported"] == "pass"
                for item in review["claim_judgments"])
        and bool(review["claim_judgments"])
        and all(item["support_verdict"] == "pass"
                for item in review["evidence_judgments"])
        and bool(review["evidence_judgments"])
        and all(item["sufficient"] == "pass" for item in review["ses_results"])
        and bool(review["ses_results"])
        and all(
            all(
                leave_out["target_claims_remain_supported"] == "no"
                for leave_out in item["leave_one_out"]
            )
            and len(item["leave_one_out"]) == len(item["evidence_ids"])
            for item in review["ses_results"]
        )
        and all(item["verdict"] == "pass"
                for item in review["necessity_group_results"])
        and bool(review["necessity_group_results"])
        and {item["condition"] for item in review["counterfactuals"]}
        == {
            "drop_vision",
            "drop_speech",
            "drop_ambient",
            "question_only",
            "metadata_only",
        }
        and len(review["counterfactuals"]) == 5
        and all(
            item["answerability_without"] == "no"
            for item in review["counterfactuals"]
            if item["condition"] in {"question_only", "metadata_only"}
        )
        and all(pair[field] == "pass" for field in CRITICAL_PAIR_FIELDS)
        and review["family_outcome"] == "accept"
    )


def adjudication_critical_pass(form: dict[str, Any]) -> bool:
    review = form["adjudication"]
    required_passes = (
        "question_answerability",
        "answer_claim_correctness",
        "exact_evidence_support",
        "alternative_search_complete",
        "all_accepted_ses_minimal",
        "necessity_groups_valid",
        "modality_counterfactuals_valid",
        "shortcuts_absent",
        "pair_isolation",
        "recovery_feasibility",
        "rights_release",
        "privacy",
        "safety",
    )
    return (
        all(review[field] == "pass" for field in required_passes)
        and review["unresolved_critical_disagreements"] == 0
        and review["recommended_outcome"] == "accept_h2"
    )


def evaluate_family(
    record: dict[str, Any],
    forms: dict[str, dict],
    adjudication: dict,
    saturation_audit: dict,
    *,
    adjudication_sha256: str,
) -> dict[str, Any]:
    reasons: list[str] = []
    pre_adjudication_complete = all(
        form["completion_status"] == "completed" for form in forms.values()
    )
    reviewers = {
        role: form["reviewer"]["reviewer_id"] for role, form in forms.items()
        if form["completion_status"] == "completed"
    }
    independence = False
    agreement: bool | None = None
    critical_pass = False
    adjudication_complete = adjudication["completion_status"] == "completed"
    saturation_audit_complete = (
        saturation_audit["completion_status"] == "completed"
    )
    saturation_pass = False
    new_sufficient_routes = 0

    if pre_adjudication_complete:
        independence = (
            len(set(reviewers.values())) == len(ROLES)
            and all(
                form["reviewer"]["independent_of_author"] is True
                for role, form in forms.items()
                if role != "question_claim_author_or_verifier"
            )
            and "preferred_ses"
            in forms["blind_alternative_evidence_finder"]["reviewer"]["blinded_to"]
            and "machine_tier_evidence"
            in forms["blind_alternative_evidence_finder"]["reviewer"]["blinded_to"]
            and "machine_ranks"
            in forms["blind_alternative_evidence_finder"]["reviewer"]["blinded_to"]
        )
        if not independence:
            reasons.append("ROLE_INDEPENDENCE_FAILURE")
        validator_a = forms["validator_a"]["review"]
        validator_b = forms["validator_b"]["review"]
        agreement = validator_construct_agreement(validator_a, validator_b)
        finder_review = forms["blind_alternative_evidence_finder"]["review"]
        finder_evidence_ids = {
            item["evidence_id"] for item in finder_review["candidate_evidence"]
        }
        finder_ses_ids = {item["ses_id"] for item in finder_review["candidate_ses"]}
        assigned_claim_ids = set(forms["validator_a"]["assignment"]["claim_ids"])
        assigned_evidence_ids = set(
            forms["validator_a"]["assignment"]["candidate_evidence_ids"]
        )
        assigned_ses_ids = {
            item["ses_id"]
            for item in forms["validator_a"]["assignment"]["machine_preferred_ses"]
        }
        validator_coverage = all(
            assigned_claim_ids
            <= {item["claim_id"] for item in form["review"]["claim_judgments"]}
            and assigned_evidence_ids | finder_evidence_ids
            <= {item["evidence_id"] for item in form["review"]["evidence_judgments"]}
            and assigned_ses_ids | finder_ses_ids
            <= {item["ses_id"] for item in form["review"]["ses_results"]}
            for role, form in forms.items()
            if role in {"validator_a", "validator_b"}
        )
        if not validator_coverage:
            reasons.append("VALIDATOR_DID_NOT_COVER_ASSIGNED_OR_ALTERNATIVE_EVIDENCE")
        critical_pass = (
            forms["question_claim_author_or_verifier"]["review"]["outcome"]
            == "accept_for_validation"
            and forms["blind_alternative_evidence_finder"]["review"]["outcome"] == "complete"
            and forms["blind_alternative_evidence_finder"]["review"][
                "exhaustive_enumeration_credible"
            ] == "pass"
            and not forms["blind_alternative_evidence_finder"]["review"][
                "unresolved_regions"
            ]
            and intervals_cover_source(
                forms["blind_alternative_evidence_finder"]["review"]["coverage_log"],
                record.get("source_duration_s") or 0,
            )
            and validator_coverage
            and validator_critical_pass(validator_a)
            and validator_critical_pass(validator_b)
        )
        if not agreement:
            reasons.append("VALIDATOR_DISAGREEMENT")
        if not critical_pass:
            reasons.append("CRITICAL_CONSTRUCT_FAILURE")
    else:
        reasons.append("REQUIRED_ROLE_INCOMPLETE")

    starting_tier = record["current_tier"]
    computed_tier = starting_tier
    outcome = "incomplete"
    if pre_adjudication_complete and independence and critical_pass and agreement:
        computed_tier = "H1_HUMAN_VALIDATED"
        outcome = "accept"
    elif pre_adjudication_complete:
        outcome = "repair"

    adjudication_pass = False
    if adjudication_complete:
        adjudicator_id = adjudication["reviewer"]["reviewer_id"]
        latest_input_completion = (
            max(
                parse_datetime(form["reviewer"]["completed_at"])
                for form in forms.values()
            )
            if pre_adjudication_complete
            else None
        )
        adjudication_started = parse_datetime(
            adjudication["reviewer"]["started_at"]
        )
        adjudication_completed = parse_datetime(
            adjudication["reviewer"]["completed_at"]
        )
        independence = (
            independence
            and adjudication["reviewer"]["independent_of_author_and_validators"] is True
            and adjudicator_id not in set(reviewers.values())
            and adjudication["inputs"]["all_required_roles_complete"] is True
            and adjudication["inputs"]["role_independence_verified"] is True
            and set(adjudication["inputs"]["annotation_form_ids"])
            == {form["form_id"] for form in forms.values()}
            and latest_input_completion is not None
            and adjudication_started >= latest_input_completion
            and adjudication_completed >= adjudication_started
        )
        if not independence:
            reasons.append("ADJUDICATOR_INDEPENDENCE_OR_INPUT_FAILURE")
        decision = adjudication["adjudication"]["recommended_outcome"]
        if (
            independence
            and pre_adjudication_complete
            and adjudication_critical_pass(adjudication)
        ):
            adjudication_pass = True
        elif decision == "reject":
            outcome = "reject"
            reasons.append("ADJUDICATED_REJECT")
        else:
            outcome = "repair"
            reasons.append("ADJUDICATION_DID_NOT_PASS_H2")

    if saturation_audit_complete:
        audit_reviewer_id = saturation_audit["reviewer"]["reviewer_id"]
        required_blinds = {
            "accepted_ses_ledger",
            "preferred_ses",
            "machine_ranks",
            "validator_decisions",
            "adjudication_decisions",
        }
        audit_review = saturation_audit["review"]
        audit_started = parse_datetime(saturation_audit["reviewer"]["started_at"])
        audit_completed = parse_datetime(
            saturation_audit["reviewer"]["completed_at"]
        )
        new_sufficient_routes = sum(
            route["sufficiency"] == "pass"
            for route in audit_review["new_routes"]
        )
        audit_independence = (
            adjudication_complete
            and saturation_audit["reviewer"][
                "independent_of_all_prior_reviewers"
            ]
            is True
            and audit_reviewer_id
            not in set(reviewers.values())
            | {adjudication["reviewer"]["reviewer_id"]}
            and required_blinds
            <= set(saturation_audit["reviewer"]["blinded_to"])
            and saturation_audit["post_adjudication"][
                "adjudication_was_frozen_before_start"
            ]
            is True
            and saturation_audit["post_adjudication"][
                "frozen_adjudication_sha256"
            ]
            == adjudication_sha256
            and audit_started
            >= parse_datetime(adjudication["reviewer"]["completed_at"])
            and audit_completed >= audit_started
        )
        if not audit_independence:
            independence = False
            reasons.append(
                "SATURATION_AUDITOR_INDEPENDENCE_BLINDING_OR_ORDER_FAILURE"
            )
        count_consistent = (
            audit_review["new_sufficient_route_count"]
            == new_sufficient_routes
        )
        if not count_consistent:
            reasons.append("SATURATION_NEW_ROUTE_COUNT_MISMATCH")
        coverage_complete = (
            audit_review["full_source_search_completed"] is True
            and not audit_review["unresolved_regions"]
            and chronological_coverage_complete(
                audit_review["coverage_log"],
                record.get("source_duration_s") or 0,
            )
        )
        if not coverage_complete:
            reasons.append("SATURATION_FULL_SOURCE_COVERAGE_FAILURE")
        route_ids = [route["route_id"] for route in audit_review["new_routes"]]
        route_findings_valid = (
            len(route_ids) == len(set(route_ids))
            and all(
                interval["end_s"] > interval["start_s"]
                and interval["end_s"]
                <= (record.get("source_duration_s") or 0) + 1.0
                for route in audit_review["new_routes"]
                for interval in route["evidence_intervals"]
            )
        )
        if not route_findings_valid:
            reasons.append("SATURATION_ROUTE_REPORT_INVALID")
        route_findings_resolved = all(
            route["sufficiency"] == "fail"
            for route in audit_review["new_routes"]
        )
        if not route_findings_resolved and not new_sufficient_routes:
            reasons.append("SATURATION_ROUTE_UNRESOLVED")
        saturation_pass = (
            audit_independence
            and count_consistent
            and coverage_complete
            and route_findings_valid
            and route_findings_resolved
            and audit_review["blind_search_completed_without_unblinding"] is True
            and audit_review["saturation_outcome"]
            == "saturated_no_new_sufficient_route"
            and new_sufficient_routes == 0
            and audit_review["reopen_required"] is False
        )
        if new_sufficient_routes:
            reasons.append("SATURATION_NEW_SUFFICIENT_ROUTE")
        elif not saturation_pass:
            reasons.append("SATURATION_AUDIT_DID_NOT_PASS")
    else:
        independence = False
        reasons.append("SATURATION_AUDIT_INCOMPLETE")

    all_six_roles_complete = (
        pre_adjudication_complete
        and adjudication_complete
        and saturation_audit_complete
    )

    pair_isolation_pass = False
    minimality_necessity_pass = False
    rights_privacy_safety_pass = False
    if pre_adjudication_complete:
        validator_reviews = [
            forms["validator_a"]["review"],
            forms["validator_b"]["review"],
        ]
        pair_isolation_pass = all(
            all(review["pair_review"][field] == "pass" for field in CRITICAL_PAIR_FIELDS)
            for review in validator_reviews
        )
        minimality_necessity_pass = all(
            review["ses_results"]
            and review["necessity_group_results"]
            and all(
                ses["sufficient"] == "pass"
                and len(ses["leave_one_out"]) == len(ses["evidence_ids"])
                and all(
                    item["target_claims_remain_supported"] == "no"
                    for item in ses["leave_one_out"]
                )
                for ses in review["ses_results"]
            )
            and all(
                group["verdict"] == "pass"
                for group in review["necessity_group_results"]
            )
            for review in validator_reviews
        )
        rights_privacy_safety_pass = all(
            all(review[field] == "pass" for field in ("rights_release", "privacy", "safety"))
            for review in validator_reviews
        )
    if adjudication_complete:
        adjudicated = adjudication["adjudication"]
        pair_isolation_pass = adjudicated["pair_isolation"] == "pass"
        minimality_necessity_pass = (
            adjudicated["all_accepted_ses_minimal"] == "pass"
            and adjudicated["necessity_groups_valid"] == "pass"
            and adjudicated["modality_counterfactuals_valid"] == "pass"
        )
        rights_privacy_safety_pass = all(
            adjudicated[field] == "pass"
            for field in ("rights_release", "privacy", "safety")
        )

    if adjudication_pass and saturation_pass:
        computed_tier = "H2_HUMAN_ADJUDICATED_GOLD"
        outcome = "accept"
        reasons = []
    elif new_sufficient_routes:
        computed_tier = starting_tier
        critical_pass = False
        pair_isolation_pass = False
        minimality_necessity_pass = False
        outcome = "repair"
    elif adjudication_pass and not saturation_pass:
        outcome = "repair" if saturation_audit_complete else "incomplete"

    return {
        "family_id": record["family_id"],
        "source_id": record["source_id"],
        "starting_tier": starting_tier,
        "computed_tier": computed_tier,
        "roles_complete": all_six_roles_complete,
        "pre_adjudication_roles_complete": pre_adjudication_complete,
        "independence_pass": independence,
        "validator_agreement": agreement,
        "critical_pass": critical_pass,
        "pair_isolation_pass": pair_isolation_pass,
        "minimality_necessity_pass": minimality_necessity_pass,
        "rights_privacy_safety_pass": rights_privacy_safety_pass,
        "adjudication_complete": adjudication_complete,
        "saturation_audit_complete": saturation_audit_complete,
        "saturation_pass": saturation_pass,
        "new_sufficient_routes": new_sufficient_routes,
        "outcome": outcome,
        "reason_codes": sorted(set(reasons)),
    }


def evaluate_packet(
    packet_dir: Path, *, generated_at: str | None = None
) -> dict[str, Any]:
    verify_packet_immutable_artifacts(packet_dir)
    registry = load_json(packet_dir / "coordinator/assignment_registry.json")
    validate_registry(registry)
    sample = load_json(packet_dir / "coordinator/sample.json")
    packet_manifest = load_json(packet_dir / "packet_manifest.json")
    packet_id = packet_manifest.get("packet_id")
    selected = sample["selected_family_ids"]
    records = {record["family_id"]: record for record in registry["records"]}
    if set(selected) != set(records):
        raise ConstructValidityError("sample and assignment registry do not match")

    loaded_forms = {
        family_id: family_forms(
            packet_dir,
            family_id,
            packet_id=packet_id,
            source_id=records[family_id]["source_id"],
        )
        for family_id in selected
    }
    governance = reviewer_governance(
        packet_dir,
        packet_id=packet_id,
        packet_manifest=packet_manifest,
        records=records,
        loaded_forms=loaded_forms,
    )

    family_results = []
    validator_pairs: list[tuple[str, str]] = []
    outcome_pairs: list[tuple[str, str]] = []
    total_minutes = 0.0
    alternative_ses = 0
    alternative_discovery_families = 0
    minimality_passes = 0
    minimality_total = 0
    necessity_passes = 0
    necessity_total = 0
    interval_ious: list[float] = []
    tier_complete: Counter[str] = Counter()
    tier_h1: Counter[str] = Counter()
    any_human_form_completed = False
    for family_id in selected:
        forms, adjudication, saturation_audit = loaded_forms[family_id]
        adjudication_path = (
            packet_dir
            / "reviewer_packets"
            / family_id
            / "adjudicator"
            / "form.json"
        )
        family_result = evaluate_family(
            records[family_id],
            forms,
            adjudication,
            saturation_audit,
            adjudication_sha256=sha256_file(adjudication_path),
        )
        governance_failures = governance["family_failures"][family_id]
        family_result["assignment_freeze_pass"] = (
            governance["assignment_freeze_pass"]
        )
        family_result["source_exposure_ledger_pass"] = (
            governance["exposure_ledger_pass"]
            and "SOURCE_EXPOSURE_LEDGER_INCOMPLETE" not in governance_failures
        )
        family_result["source_group_blindness_pass"] = not bool(
            {
                "SOURCE_GROUP_BLIND_ROLE_EXPOSURE_CONFLICT",
                "SOURCE_GROUP_ADJUDICATOR_AUTHOR_CONFLICT",
            }
            & governance_failures
        )
        if governance_failures:
            family_result["computed_tier"] = family_result["starting_tier"]
            family_result["independence_pass"] = False
            family_result["critical_pass"] = False
            family_result["saturation_pass"] = False
            family_result["outcome"] = "repair"
            family_result["reason_codes"] = sorted(
                set(family_result["reason_codes"]) | governance_failures
            )
        family_results.append(family_result)
        any_human_form_completed = any_human_form_completed or any(
            form["completion_status"] == "completed" for form in forms.values()
        )
        if family_result["pre_adjudication_roles_complete"]:
            tier_complete[records[family_id]["current_tier"]] += 1
            if family_result["computed_tier"] in {
                "H1_HUMAN_VALIDATED",
                "H2_HUMAN_ADJUDICATED_GOLD",
            }:
                tier_h1[records[family_id]["current_tier"]] += 1
        if all(forms[r]["completion_status"] == "completed"
               for r in ("validator_a", "validator_b")):
            a = forms["validator_a"]["review"]
            b = forms["validator_b"]["review"]
            validator_pairs.extend(
                (a[field], b[field]) for field in CRITICAL_VALIDATOR_FIELDS
            )
            validator_pairs.extend(
                (a["pair_review"][field], b["pair_review"][field])
                for field in CRITICAL_PAIR_FIELDS
            )
            outcome_pairs.append((a["family_outcome"], b["family_outcome"]))
            for review in (a, b):
                for ses in review["ses_results"]:
                    minimality_total += 1
                    if (
                        ses["sufficient"] == "pass"
                        and len(ses["leave_one_out"]) == len(ses["evidence_ids"])
                        and all(
                            item["target_claims_remain_supported"] == "no"
                            for item in ses["leave_one_out"]
                        )
                    ):
                        minimality_passes += 1
                for group in review["necessity_group_results"]:
                    necessity_total += 1
                    necessity_passes += group["verdict"] == "pass"
            a_evidence = {
                item["evidence_id"]: item
                for item in a["evidence_judgments"]
                if len(item["intervals"]) == 1
            }
            b_evidence = {
                item["evidence_id"]: item
                for item in b["evidence_judgments"]
                if len(item["intervals"]) == 1
            }
            for evidence_id in set(a_evidence) & set(b_evidence):
                ia = a_evidence[evidence_id]["intervals"][0]
                ib = b_evidence[evidence_id]["intervals"][0]
                intersection = max(
                    0.0, min(ia["end_s"], ib["end_s"]) - max(ia["start_s"], ib["start_s"])
                )
                union = max(ia["end_s"], ib["end_s"]) - min(
                    ia["start_s"], ib["start_s"]
                )
                interval_ious.append(intersection / union if union > 0 else 0.0)
        for form in forms.values():
            if form["completion_status"] == "completed":
                total_minutes += form["reviewer"]["active_minutes"]
                if form["role"] == "blind_alternative_evidence_finder":
                    alternative_ses += form["review"]["new_alternative_ses_count"]
                    alternative_discovery_families += (
                        form["review"]["new_alternative_ses_count"] > 0
                    )
        if adjudication["completion_status"] == "completed":
            total_minutes += adjudication["reviewer"]["active_minutes"]
        if saturation_audit["completion_status"] == "completed":
            total_minutes += saturation_audit["reviewer"]["active_minutes"]

    completed_count = sum(item["roles_complete"] for item in family_results)
    pre_adjudication_completed_count = sum(
        item["pre_adjudication_roles_complete"] for item in family_results
    )
    accepted_h1 = sum(
        item["computed_tier"] in {"H1_HUMAN_VALIDATED", "H2_HUMAN_ADJUDICATED_GOLD"}
        for item in family_results
    )
    accepted_h2 = sum(
        item["computed_tier"] == "H2_HUMAN_ADJUDICATED_GOLD"
        for item in family_results
    )
    repaired = sum(item["outcome"] == "repair" for item in family_results)
    rejected = sum(item["outcome"] == "reject" for item in family_results)
    pair_failures = sum(
        item["pre_adjudication_roles_complete"]
        and not item["pair_isolation_pass"]
        for item in family_results
    )
    construct_failures = sum(
        item["pre_adjudication_roles_complete"]
        and not item["minimality_necessity_pass"]
        for item in family_results
    )
    completed_adjudications = sum(
        item["adjudication_complete"] for item in family_results
    )
    completed_saturation_audits = sum(
        item["saturation_audit_complete"] for item in family_results
    )
    saturation_passes = sum(item["saturation_pass"] for item in family_results)
    saturation_new_routes = sum(
        item["new_sufficient_routes"] for item in family_results
    )
    h2_precision_denominator = sum(
        records[item["family_id"]]["current_tier"]
        == "P2_MACHINE_COUNTERFACTUAL_VALIDATED"
        and item["roles_complete"]
        for item in family_results
    )
    h2_precision_numerator = sum(
        records[item["family_id"]]["current_tier"]
        == "P2_MACHINE_COUNTERFACTUAL_VALIDATED"
        and item["computed_tier"] == "H2_HUMAN_ADJUDICATED_GOLD"
        for item in family_results
    )
    all_human_complete = completed_count == len(family_results)
    human_review_occurred = any_human_form_completed or any(
        item["adjudication_complete"] or item["saturation_audit_complete"]
        for item in family_results
    )
    if not human_review_occurred:
        decision = "INCOMPLETE_NO_HUMAN_DECISION"
    elif not all_human_complete:
        decision = "CONSTRUCT_VALIDITY_REPAIR"
    else:
        h1_rate = accepted_h1 / len(family_results)
        pair_failure_rate = pair_failures / len(family_results)
        rights_failures = sum(
            not item["rights_privacy_safety_pass"] for item in family_results
        )
        if (
            len(family_results) >= 8
            and len({item["source_id"] for item in family_results}) >= 5
            and h1_rate >= 0.75
            and pair_failure_rate <= 0.10
            and rights_failures == 0
            and construct_failures / len(family_results) <= 0.25
            and completed_adjudications == len(family_results)
            and completed_saturation_audits == len(family_results)
            and saturation_passes == len(family_results)
            and accepted_h2 >= math.ceil(0.60 * len(family_results))
        ):
            decision = "CONSTRUCT_VALIDITY_MINI_PILOT_GO"
        elif h1_rate >= 0.40 and rejected < math.ceil(0.50 * len(family_results)):
            decision = "CONSTRUCT_VALIDITY_REPAIR"
        else:
            decision = "CONSTRUCT_VALIDITY_NO_GO"

    statistics = {
        "low_n_warning": (
            "LOW_N_MINI_PILOT_DESCRIPTIVE_ONLY"
            if len(family_results) < 30
            else None
        ),
        "acceptance_funnel": {
            "sampled": len(family_results),
            "pre_adjudication_roles_complete": pre_adjudication_completed_count,
            "adjudicated": completed_adjudications,
            "saturation_audited": completed_saturation_audits,
            "all_roles_complete": completed_count,
            "h1_or_h2": accepted_h1,
            "h2": accepted_h2,
            "repair": repaired,
            "reject": rejected,
        },
        "agreement": {
            "critical_label_cohens_kappa": cohens_kappa(validator_pairs),
            "family_outcome_cohens_kappa": cohens_kappa(outcome_pairs),
            "critical_label_pair_count": len(validator_pairs),
            "family_pair_count": len(outcome_pairs),
        },
        "p2_acceptance_precision_estimate": {
            "numerator_h2": h2_precision_numerator,
            "denominator_reviewed_p2": h2_precision_denominator,
            "estimate": (
                h2_precision_numerator / h2_precision_denominator
                if h2_precision_denominator
                else None
            ),
            "wilson_95_ci": wilson_interval(
                h2_precision_numerator, h2_precision_denominator
            ),
        },
        "machine_tier_h1_precision_estimates": {
            tier: {
                "numerator_h1_or_h2": tier_h1[tier],
                "denominator_complete": tier_complete[tier],
                "estimate": (
                    tier_h1[tier] / tier_complete[tier]
                    if tier_complete[tier]
                    else None
                ),
                "wilson_95_ci": wilson_interval(tier_h1[tier], tier_complete[tier]),
            }
            for tier in (
                "P0_MACHINE_CANDIDATE",
                "P1_MACHINE_CROSS_VALIDATED",
                "P2_MACHINE_COUNTERFACTUAL_VALIDATED",
            )
        },
        "all_machine_tier_h1_precision_estimate": {
            "numerator_h1_or_h2": accepted_h1,
            "denominator_complete": pre_adjudication_completed_count,
            "estimate": (
                accepted_h1 / pre_adjudication_completed_count
                if pre_adjudication_completed_count
                else None
            ),
            "wilson_95_ci": wilson_interval(
                accepted_h1, pre_adjudication_completed_count
            ),
        },
        "alternative_ses_discovery": {
            "new_alternative_ses": alternative_ses,
            "families_with_new_alternative_ses": alternative_discovery_families,
            "family_discovery_rate": (
                alternative_discovery_families / pre_adjudication_completed_count
                if pre_adjudication_completed_count
                else None
            ),
            "wilson_95_ci": wilson_interval(
                alternative_discovery_families,
                pre_adjudication_completed_count,
            ),
            "per_completed_family": (
                alternative_ses / pre_adjudication_completed_count
                if pre_adjudication_completed_count
                else None
            ),
        },
        "saturation_audit": {
            "completed_families": completed_saturation_audits,
            "saturated_families": saturation_passes,
            "families_with_new_sufficient_routes": sum(
                item["new_sufficient_routes"] > 0 for item in family_results
            ),
            "new_sufficient_routes": saturation_new_routes,
        },
        "pair_isolation_failure": {
            "failures": pair_failures,
            "denominator_complete": pre_adjudication_completed_count,
            "rate": (
                pair_failures / pre_adjudication_completed_count
                if pre_adjudication_completed_count
                else None
            ),
            "wilson_95_ci": wilson_interval(
                pair_failures, pre_adjudication_completed_count
            ),
        },
        "minimality_pass": {
            "passes": minimality_passes,
            "denominator": minimality_total,
            "rate": (
                minimality_passes / minimality_total if minimality_total else None
            ),
            "wilson_95_ci": wilson_interval(minimality_passes, minimality_total),
        },
        "necessity_group_pass": {
            "passes": necessity_passes,
            "denominator": necessity_total,
            "rate": necessity_passes / necessity_total if necessity_total else None,
            "wilson_95_ci": wilson_interval(necessity_passes, necessity_total),
        },
        "construct_failure": {
            "families_failing_minimality_necessity_or_modality": construct_failures,
            "denominator_complete": pre_adjudication_completed_count,
            "rate": (
                construct_failures / pre_adjudication_completed_count
                if pre_adjudication_completed_count
                else None
            ),
            "wilson_95_ci": wilson_interval(
                construct_failures, pre_adjudication_completed_count
            ),
        },
        "temporal_interval_agreement": {
            "single_interval_pairs": len(interval_ious),
            "mean_temporal_iou": (
                sum(interval_ious) / len(interval_ious) if interval_ious else None
            ),
        },
        "labor": {
            "total_active_minutes": total_minutes,
            "minutes_per_complete_family": (
                total_minutes / completed_count if completed_count else None
            ),
        },
        "packet_declared_unfilled": (
            packet_manifest.get("packet_status")
            == "UNFILLED_DEFERRED_HUMAN_ASSIGNMENT"
        ),
        "reviewer_governance": {
            "assignment_status": governance["assignment_status"],
            "assignment_freeze_pass": governance["assignment_freeze_pass"],
            "source_exposure_ledger_pass": governance["exposure_ledger_pass"],
            "source_group_blindness_pass": governance["source_blindness_pass"],
            "source_group_count": governance["source_group_count"],
            "exposure_event_count": governance["exposure_event_count"],
        },
    }
    report = {
        "schema_version": "1.0.0",
        "record_type": "construct_validation_import_report",
        "generated_at": generated_at or now_utc(),
        "decision": decision,
        "human_review_occurred": human_review_occurred,
        "families": family_results,
        "statistics": statistics,
        "errors": [],
    }
    validate_instance(report, IMPORT_SCHEMA, "import report")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--generated-at",
        help="optional fixed report timestamp for deterministic fixture generation",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = evaluate_packet(args.packet_dir, generated_at=args.generated_at)
        write_json(args.output, report, restricted=True)
    except ConstructValidityError as exc:
        print(f"ERROR: {exc}")
        return 2
    print(
        f"{report['decision']}: human_review_occurred="
        f"{str(report['human_review_occurred']).lower()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
