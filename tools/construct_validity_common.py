#!/usr/bin/env python3
"""Shared fail-closed helpers for deferred construct-validity tooling."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SPEC_ROOT = ROOT / "docs/spec"
REGISTRY_SCHEMA = SPEC_ROOT / "construct_validation_registry_schema.json"
ANNOTATION_SCHEMA = SPEC_ROOT / "construct_validation_annotation_schema.json"
ADJUDICATION_SCHEMA = SPEC_ROOT / "construct_validation_adjudication_schema.json"
SATURATION_AUDIT_SCHEMA = (
    SPEC_ROOT / "construct_validation_saturation_audit_schema.json"
)
REVIEWER_ASSIGNMENT_SCHEMA = (
    SPEC_ROOT / "construct_validation_reviewer_assignment_schema.json"
)
SOURCE_EXPOSURE_LEDGER_SCHEMA = (
    SPEC_ROOT / "construct_validation_source_exposure_ledger_schema.json"
)
IMPORT_SCHEMA = SPEC_ROOT / "construct_validation_import_schema.json"

MACHINE_TIERS = (
    "P0_MACHINE_CANDIDATE",
    "P1_MACHINE_CROSS_VALIDATED",
    "P2_MACHINE_COUNTERFACTUAL_VALIDATED",
)
HUMAN_TIERS = ("H1_HUMAN_VALIDATED", "H2_HUMAN_ADJUDICATED_GOLD")
ALL_TIERS = MACHINE_TIERS + HUMAN_TIERS
ROLES = (
    "question_claim_author_or_verifier",
    "blind_alternative_evidence_finder",
    "validator_a",
    "validator_b",
)
SATURATION_AUDITOR_ROLE = "blind_post_adjudication_saturation_auditor"
ADJUDICATOR_ROLE = "adjudicator"
ALL_HUMAN_ROLES = ROLES + (ADJUDICATOR_ROLE, SATURATION_AUDITOR_ROLE)
BLIND_SOURCE_ROLES = (
    "blind_alternative_evidence_finder",
    SATURATION_AUDITOR_ROLE,
)
SOURCE_BLINDNESS_PROHIBITED_EXPOSURES = frozenset(
    {
        "preferred_evidence",
        "machine_ranks_or_confidence",
        "validator_decisions",
        "adjudication_decisions",
        "accepted_ses",
    }
)
CRITICAL_VALIDATOR_FIELDS = (
    "question_answerability",
    "answer_claim_correctness",
    "rights_release",
    "privacy",
    "safety",
)
CRITICAL_PAIR_FIELDS = (
    "clean_supported",
    "blocked_target_inaccessible",
    "blocked_source_remains_sufficient",
    "all_direct_derived_alternative_routes_blocked",
    "restored_matches_blocked_pretrigger",
    "restoration_reverses_only_block",
    "recovery_feasible_within_budget",
    "pair_isolation",
)


class ConstructValidityError(ValueError):
    """Raised when a construct-validation artifact fails closed."""


def now_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConstructValidityError(f"cannot read JSON {path}: {exc}") from exc


def write_json(path: Path, value: Any, *, restricted: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value))
    os.chmod(path, 0o600 if restricted else 0o644)


def validator_for(schema_path: Path) -> Draft202012Validator:
    schema = load_json(schema_path)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate_instance(instance: Any, schema_path: Path, label: str) -> None:
    errors = sorted(
        validator_for(schema_path).iter_errors(instance),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        rendered = []
        for error in errors[:20]:
            location = ".".join(str(part) for part in error.absolute_path) or "$"
            rendered.append(f"{location}: {error.message}")
        raise ConstructValidityError(
            f"{label} failed schema validation: " + "; ".join(rendered)
        )


def validate_registry(registry: Any) -> None:
    validate_instance(registry, REGISTRY_SCHEMA, "registry")
    ids = [record["family_id"] for record in registry["records"]]
    if len(ids) != len(set(ids)):
        raise ConstructValidityError("registry family_id values must be unique")
    if any(
        record["candidate_status"] == "eligible"
        and record["current_tier"] not in MACHINE_TIERS
        for record in registry["records"]
    ):
        raise ConstructValidityError("eligible registry records must start at a P tier")
    if registry["registry_status"] == "MACHINE_PROVISIONAL_REGISTRY":
        for record in registry["records"]:
            if record["candidate_status"] != "eligible":
                continue
            payload = record.get("review_payload")
            if (
                not payload
                or not payload["claims"]
                or not payload["candidate_evidence"]
                or not payload["preferred_ses"]
            ):
                raise ConstructValidityError(
                    f"eligible real registry record {record['family_id']} lacks "
                    "review_payload claims/evidence/SES"
                )
            if not record.get("source_reference"):
                raise ConstructValidityError(
                    f"eligible real registry record {record['family_id']} lacks source"
                )
            tier_evidence = record.get("tier_evidence")
            if not tier_evidence:
                raise ConstructValidityError(
                    f"eligible real registry record {record['family_id']} lacks "
                    "tier_evidence"
                )
            if (
                tier_evidence["source_decode_verified"] is not True
                or not tier_evidence["machine_proposal_versions"]
            ):
                raise ConstructValidityError(
                    f"{record['family_id']} does not meet P0 provenance gate"
                )
            if record["current_tier"] in {
                "P1_MACHINE_CROSS_VALIDATED",
                "P2_MACHINE_COUNTERFACTUAL_VALIDATED",
            }:
                p1_checks = (
                    "answer_evidence_check",
                    "question_only_shortcut_check",
                    "metadata_shortcut_check",
                    "alternative_support_scan",
                )
                if (
                    len(tier_evidence["independent_machine_validator_ids"]) < 2
                    or any(tier_evidence[field] != "pass" for field in p1_checks)
                ):
                    raise ConstructValidityError(
                        f"{record['family_id']} does not meet P1 cross-validation gate"
                    )
            if record["current_tier"] == "P2_MACHINE_COUNTERFACTUAL_VALIDATED":
                p2_checks = (
                    "leave_one_out_counterfactual",
                    "modality_drop_counterfactual",
                    "blocked_route_closure",
                    "restored_recovery_check",
                )
                if (
                    len(tier_evidence["counterfactual_validator_ids"]) < 2
                    or any(tier_evidence[field] != "pass" for field in p2_checks)
                ):
                    raise ConstructValidityError(
                        f"{record['family_id']} does not meet P2 counterfactual gate"
                    )


def validate_annotation(form: Any) -> None:
    validate_instance(form, ANNOTATION_SCHEMA, "annotation form")
    if form["reviewer"]["declared_role"] != form["role"]:
        raise ConstructValidityError("declared_role must equal form role")
    if form["assignment_hash"] != annotation_assignment_hash(form):
        raise ConstructValidityError("annotation assignment_hash mismatch")


def validate_adjudication(form: Any) -> None:
    validate_instance(form, ADJUDICATION_SCHEMA, "adjudication form")


def validate_saturation_audit(form: Any) -> None:
    validate_instance(form, SATURATION_AUDIT_SCHEMA, "saturation audit form")
    if form["reviewer"]["declared_role"] != SATURATION_AUDITOR_ROLE:
        raise ConstructValidityError(
            "saturation auditor declared_role must match the sixth role"
        )
    if form["assignment_hash"] != saturation_assignment_hash(form):
        raise ConstructValidityError("saturation audit assignment_hash mismatch")


def assignment_freeze_hash(ledger: dict[str, Any]) -> str:
    envelope = {
        "schema_version": ledger["schema_version"],
        "record_type": ledger["record_type"],
        "packet_id": ledger["packet_id"],
        "generated_at": ledger["generated_at"],
        "assignment_status": ledger["assignment_status"],
        "frozen_at": ledger["frozen_at"],
        "distribution_authorized": ledger["distribution_authorized"],
        "pre_distribution_exposure_snapshot_sha256": ledger[
            "pre_distribution_exposure_snapshot_sha256"
        ],
        "source_groups": ledger["source_groups"],
        "assignments": ledger["assignments"],
        "notes": ledger["notes"],
    }
    return sha256_bytes(canonical_json_bytes(envelope))


def exposure_event_hash(event: dict[str, Any]) -> str:
    envelope = {key: value for key, value in event.items() if key != "event_sha256"}
    return sha256_bytes(canonical_json_bytes(envelope))


def exposure_snapshot_hash(snapshot: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(snapshot))


def validate_reviewer_assignment_ledger(ledger: Any) -> None:
    validate_instance(
        ledger, REVIEWER_ASSIGNMENT_SCHEMA, "reviewer assignment ledger"
    )
    source_groups = ledger["source_groups"]
    source_group_ids = [item["source_group_id"] for item in source_groups]
    if len(source_group_ids) != len(set(source_group_ids)):
        raise ConstructValidityError(
            "reviewer assignment source_group_id values must be unique"
        )
    family_to_group: dict[str, str] = {}
    for group in source_groups:
        for family_id in group["family_ids"]:
            if family_id in family_to_group:
                raise ConstructValidityError(
                    f"family {family_id} occurs in multiple source groups"
                )
            family_to_group[family_id] = group["source_group_id"]
    assignments = ledger["assignments"]
    assignment_ids = [item["assignment_id"] for item in assignments]
    if len(assignment_ids) != len(set(assignment_ids)):
        raise ConstructValidityError("assignment_id values must be unique")
    family_roles: dict[str, set[str]] = {}
    family_reviewers: dict[str, list[str]] = {}
    for assignment in assignments:
        family_id = assignment["family_id"]
        source_group_id = assignment["source_group_id"]
        if family_to_group.get(family_id) != source_group_id:
            raise ConstructValidityError(
                f"assignment source group mismatch for {family_id}"
            )
        family_roles.setdefault(family_id, set()).add(assignment["role"])
        reviewer_id = assignment["reviewer_id"]
        if reviewer_id is not None:
            family_reviewers.setdefault(family_id, []).append(reviewer_id)
    for family_id, source_group_id in family_to_group.items():
        if family_roles.get(family_id, set()) != set(ALL_HUMAN_ROLES):
            raise ConstructValidityError(
                f"{family_id} must have exactly the six required role assignments"
            )
    expected_count = len(family_to_group) * len(ALL_HUMAN_ROLES)
    if len(assignments) != expected_count:
        raise ConstructValidityError(
            "reviewer assignment ledger must contain one row per family and role"
        )
    if ledger["assignment_status"] == "FROZEN_BEFORE_DISTRIBUTION":
        for family_id, reviewer_ids in family_reviewers.items():
            if len(reviewer_ids) != len(ALL_HUMAN_ROLES) or len(
                set(reviewer_ids)
            ) != len(ALL_HUMAN_ROLES):
                raise ConstructValidityError(
                    f"{family_id} must retain six distinct reviewer identities"
                )
        if ledger["assignment_freeze_sha256"] != assignment_freeze_hash(ledger):
            raise ConstructValidityError("assignment_freeze_sha256 mismatch")


def validate_source_exposure_ledger(ledger: Any) -> None:
    validate_instance(
        ledger, SOURCE_EXPOSURE_LEDGER_SCHEMA, "source exposure ledger"
    )
    source_groups = ledger["source_groups"]
    source_group_ids = [item["source_group_id"] for item in source_groups]
    if len(source_group_ids) != len(set(source_group_ids)):
        raise ConstructValidityError(
            "source exposure source_group_id values must be unique"
        )
    family_to_group: dict[str, str] = {}
    for group in source_groups:
        for family_id in group["family_ids"]:
            if family_id in family_to_group:
                raise ConstructValidityError(
                    f"family {family_id} occurs in multiple exposure groups"
                )
            family_to_group[family_id] = group["source_group_id"]
    snapshot = ledger["pre_distribution_snapshot"]
    if ledger["pre_distribution_snapshot_sha256"] != exposure_snapshot_hash(
        snapshot
    ):
        raise ConstructValidityError("pre-distribution exposure snapshot hash mismatch")
    snapshot_captured_at = datetime.fromisoformat(snapshot["captured_at"])
    all_events = snapshot["events"] + ledger["review_events"]
    event_ids = [event["event_id"] for event in all_events]
    if len(event_ids) != len(set(event_ids)):
        raise ConstructValidityError("source exposure event_id values must be unique")
    previous_hash = None
    for expected_sequence, event in enumerate(all_events, start=1):
        if event["sequence"] != expected_sequence:
            raise ConstructValidityError(
                "source exposure events must use contiguous global sequence numbers"
            )
        if event["previous_event_sha256"] != previous_hash:
            raise ConstructValidityError(
                f"source exposure chain mismatch: {event['event_id']}"
            )
        family_id = event["family_id"]
        if (
            family_id is not None
            and family_to_group.get(family_id) != event["source_group_id"]
        ):
            raise ConstructValidityError(
                f"exposure event source group mismatch for {family_id}"
            )
        if event["source_group_id"] not in set(source_group_ids):
            raise ConstructValidityError(
                f"unknown exposure source group {event['source_group_id']}"
            )
        if event["event_sha256"] != exposure_event_hash(event):
            raise ConstructValidityError(
                f"source exposure event hash mismatch: {event['event_id']}"
            )
        previous_hash = event["event_sha256"]
    if any(
        datetime.fromisoformat(event["recorded_at"]) > snapshot_captured_at
        for event in snapshot["events"]
    ):
        raise ConstructValidityError(
            "pre-distribution snapshot contains an event recorded after capture"
        )


def source_group_records(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, set[str]]] = {}
    for record in records:
        group_id = record["source_id"]
        entry = grouped.setdefault(
            group_id, {"source_ids": set(), "family_ids": set()}
        )
        entry["source_ids"].add(record["source_id"])
        entry["family_ids"].add(record["family_id"])
    return [
        {
            "source_group_id": source_group_id,
            "source_ids": sorted(values["source_ids"]),
            "family_ids": sorted(values["family_ids"]),
        }
        for source_group_id, values in sorted(grouped.items())
    ]


def blank_source_exposure_ledger(
    *,
    packet_id: str,
    records: list[dict[str, Any]],
    generated_at: str | None = None,
) -> dict[str, Any]:
    captured_at = generated_at or now_utc()
    snapshot = {"captured_at": captured_at, "events": []}
    return {
        "schema_version": "1.0.0",
        "record_type": "construct_validation_source_exposure_ledger",
        "packet_id": packet_id,
        "ledger_status": "OPEN_APPEND_ONLY",
        "source_groups": source_group_records(records),
        "pre_distribution_snapshot": snapshot,
        "pre_distribution_snapshot_sha256": exposure_snapshot_hash(snapshot),
        "review_events": [],
        "notes": (
            "Blank portable ledger. Record all known pre-existing exposures "
            "before freezing assignments, then append every packet exposure."
        ),
    }


def blank_reviewer_assignment_ledger(
    *,
    packet_id: str,
    records: list[dict[str, Any]],
    pre_distribution_exposure_snapshot_sha256: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    assignments = []
    for record in sorted(records, key=lambda item: item["family_id"]):
        for role in ALL_HUMAN_ROLES:
            assignments.append(
                {
                    "assignment_id": f"{packet_id}.{record['family_id']}.{role}",
                    "source_group_id": record["source_id"],
                    "family_id": record["family_id"],
                    "role": role,
                    "reviewer_id": None,
                    "assigned_at": None,
                }
            )
    return {
        "schema_version": "1.0.0",
        "record_type": "construct_validation_reviewer_assignment_ledger",
        "packet_id": packet_id,
        "generated_at": generated_at or now_utc(),
        "assignment_status": "DRAFT_NOT_DISTRIBUTABLE",
        "frozen_at": None,
        "distribution_authorized": False,
        "pre_distribution_exposure_snapshot_sha256": (
            pre_distribution_exposure_snapshot_sha256
        ),
        "assignment_freeze_sha256": None,
        "source_groups": source_group_records(records),
        "assignments": assignments,
        "notes": (
            "Blank portable assignment template. Insert real pseudonymous "
            "reviewer IDs, validate source-level blindness, then freeze before "
            "any reviewer packet is distributed."
        ),
    }


def freeze_reviewer_assignment_ledger(
    ledger: dict[str, Any], *, frozen_at: str
) -> dict[str, Any]:
    """Freeze a fully populated assignment ledger without inventing reviewers."""
    if ledger.get("assignment_status") != "DRAFT_NOT_DISTRIBUTABLE":
        raise ConstructValidityError("only a draft assignment ledger can be frozen")
    if any(
        assignment.get("reviewer_id") is None
        or assignment.get("assigned_at") is None
        for assignment in ledger.get("assignments", [])
    ):
        raise ConstructValidityError(
            "all reviewer IDs and assignment timestamps are required before freeze"
        )
    frozen = json.loads(json.dumps(ledger))
    frozen["assignment_status"] = "FROZEN_BEFORE_DISTRIBUTION"
    frozen["frozen_at"] = frozen_at
    frozen["distribution_authorized"] = True
    frozen["assignment_freeze_sha256"] = assignment_freeze_hash(frozen)
    validate_reviewer_assignment_ledger(frozen)
    return frozen


def append_source_exposure_event(
    ledger: dict[str, Any], event: dict[str, Any]
) -> dict[str, Any]:
    """Append one hash-chained exposure event to an exposure ledger."""
    updated = json.loads(json.dumps(ledger))
    all_events = (
        updated["pre_distribution_snapshot"]["events"]
        + updated["review_events"]
    )
    next_event = json.loads(json.dumps(event))
    next_event["sequence"] = len(all_events) + 1
    next_event["previous_event_sha256"] = (
        all_events[-1]["event_sha256"] if all_events else None
    )
    next_event["event_sha256"] = exposure_event_hash(next_event)
    updated["review_events"].append(next_event)
    validate_source_exposure_ledger(updated)
    return updated


def source_level_assignment_conflicts(
    assignments: dict[str, Any], exposures: dict[str, Any]
) -> dict[str, set[str]]:
    """Return source-group assignment/exposure conflicts keyed by family."""
    validate_reviewer_assignment_ledger(assignments)
    validate_source_exposure_ledger(exposures)
    if assignments["packet_id"] != exposures["packet_id"]:
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
    conflicts = {
        family_id: set()
        for group in assignments["source_groups"]
        for family_id in group["family_ids"]
    }
    all_events = (
        exposures["pre_distribution_snapshot"]["events"]
        + exposures["review_events"]
    )
    contaminating_roles = {
        "question_claim_author_or_verifier",
        "validator_a",
        "validator_b",
        ADJUDICATOR_ROLE,
    }
    for blind_assignment in assignments["assignments"]:
        if blind_assignment["role"] not in BLIND_SOURCE_ROLES:
            continue
        reviewer_id = blind_assignment["reviewer_id"]
        if reviewer_id is None:
            continue
        group_id = blind_assignment["source_group_id"]
        family_id = blind_assignment["family_id"]
        contaminated_by_assignment = any(
            other["reviewer_id"] == reviewer_id
            and other["source_group_id"] == group_id
            and other["family_id"] != family_id
            and other["role"] in contaminating_roles
            for other in assignments["assignments"]
        )
        contaminated_by_ledger = any(
            event["reviewer_id"] == reviewer_id
            and event["source_group_id"] == group_id
            and (
                event["family_id"] != family_id
                or event["role"] == "external_prior_work"
            )
            and bool(
                SOURCE_BLINDNESS_PROHIBITED_EXPOSURES
                & set(event["exposure_categories"])
            )
            for event in all_events
        )
        if contaminated_by_assignment or contaminated_by_ledger:
            conflicts[family_id].add(
                "SOURCE_GROUP_BLIND_ROLE_EXPOSURE_CONFLICT"
            )

    for adjudicator in assignments["assignments"]:
        if adjudicator["role"] != ADJUDICATOR_ROLE:
            continue
        for author in assignments["assignments"]:
            if (
                author["role"] == "question_claim_author_or_verifier"
                and author["reviewer_id"] is not None
                and author["reviewer_id"] == adjudicator["reviewer_id"]
                and author["source_group_id"] == adjudicator["source_group_id"]
                and author["family_id"] != adjudicator["family_id"]
            ):
                conflicts[adjudicator["family_id"]].add(
                    "SOURCE_GROUP_ADJUDICATOR_AUTHOR_CONFLICT"
                )
                conflicts[author["family_id"]].add(
                    "SOURCE_GROUP_ADJUDICATOR_AUTHOR_CONFLICT"
                )
    adjudicator_events = [
        event for event in all_events if event["role"] == ADJUDICATOR_ROLE
    ]
    author_events = [
        event
        for event in all_events
        if event["role"] == "question_claim_author_or_verifier"
    ]
    for adjudicator_event in adjudicator_events:
        for author_event in author_events:
            if (
                adjudicator_event["reviewer_id"] == author_event["reviewer_id"]
                and adjudicator_event["source_group_id"]
                == author_event["source_group_id"]
                and adjudicator_event["family_id"] != author_event["family_id"]
            ):
                for family_id in (
                    adjudicator_event["family_id"],
                    author_event["family_id"],
                ):
                    if family_id is not None and family_id in conflicts:
                        conflicts[family_id].add(
                            "SOURCE_GROUP_ADJUDICATOR_AUTHOR_CONFLICT"
                        )
    return conflicts


def public_assignment(record: dict[str, Any], *, blind: bool = False) -> dict[str, Any]:
    """Return only fields safe and useful in a reviewer assignment."""
    payload = record.get("review_payload", {})
    claims = list(payload.get("claims", []))
    evidence = [] if blind else list(payload.get("candidate_evidence", []))
    preferred_ses = [] if blind else list(payload.get("preferred_ses", []))
    return {
        "source_reference": record.get("source_reference")
        or f"UNRESOLVED_SOURCE_REFERENCE:{record['source_id']}",
        "source_duration_s": record.get("source_duration_s") or 1.0,
        "source_content_hashes": list(record["provenance"]["content_hashes"]),
        "question_text": record.get("machine_question")
        or "MACHINE QUESTION NOT YET MATERIALIZED",
        "machine_claims": claims,
        "claim_ids": [item["claim_id"] for item in claims],
        "machine_candidate_evidence": evidence,
        "candidate_evidence_ids": [item["evidence_id"] for item in evidence],
        "machine_preferred_ses": preferred_ses,
        "pair_blueprint_reference": (
            None if blind else payload.get("pair_blueprint_reference")
        ),
        "machine_labels_are_provisional": True,
        "human_gold_at_assignment": False,
    }


def blank_annotation(
    *,
    packet_id: str,
    record: dict[str, Any],
    role: str,
) -> dict[str, Any]:
    if role not in ROLES:
        raise ConstructValidityError(f"unknown role: {role}")
    assignment = public_assignment(
        record, blind=role == "blind_alternative_evidence_finder"
    )
    envelope = {
        "packet_id": packet_id,
        "family_id": record["family_id"],
        "source_id": record["source_id"],
        "role": role,
        "assignment_tier": (
            "BLINDED_MACHINE_TIER"
            if role == "blind_alternative_evidence_finder"
            else record["current_tier"]
        ),
        "assignment": assignment,
    }
    return {
        "schema_version": "1.0.0",
        "record_type": "construct_validation_annotation",
        "form_id": f"{packet_id}.{record['family_id']}.{role}",
        "packet_id": packet_id,
        "family_id": record["family_id"],
        "source_id": record["source_id"],
        "role": role,
        "assignment_tier": envelope["assignment_tier"],
        "assignment_hash": sha256_bytes(canonical_json_bytes(envelope)),
        "completion_status": "not_started",
        "reviewer": {
            "reviewer_id": None,
            "declared_role": role,
            "independent_of_author": None,
            "blinded_to": (
                [
                    "preferred_ses",
                    "machine_confidence",
                    "machine_tier_evidence",
                    "machine_ranks",
                    "other_validator_decision",
                    "adjudicator_decision",
                ]
                if role == "blind_alternative_evidence_finder"
                else ["other_validator_decision", "adjudicator_decision"]
            ),
            "started_at": None,
            "completed_at": None,
            "active_minutes": None,
        },
        "assignment": assignment,
        "review": {},
    }


def annotation_assignment_hash(form: dict[str, Any]) -> str:
    envelope = {
        "packet_id": form["packet_id"],
        "family_id": form["family_id"],
        "source_id": form["source_id"],
        "role": form["role"],
        "assignment_tier": form["assignment_tier"],
        "assignment": form["assignment"],
    }
    return sha256_bytes(canonical_json_bytes(envelope))


def saturation_assignment(record: dict[str, Any]) -> dict[str, Any]:
    """Return the minimal assignment visible to the blind sixth reviewer."""
    return {
        "source_reference": record.get("source_reference")
        or f"UNRESOLVED_SOURCE_REFERENCE:{record['source_id']}",
        "source_duration_s": record.get("source_duration_s") or 1.0,
        "source_content_hashes": list(record["provenance"]["content_hashes"]),
        "frozen_question_text": record.get("machine_question")
        or "MACHINE QUESTION NOT YET MATERIALIZED",
        "machine_labels_are_provisional": True,
        "human_gold_at_assignment": False,
    }


def saturation_assignment_hash(form: dict[str, Any]) -> str:
    envelope = {
        "packet_id": form["packet_id"],
        "family_id": form["family_id"],
        "source_id": form["source_id"],
        "role": form["role"],
        "assignment_tier": form["assignment_tier"],
        "assignment": form["assignment"],
        "post_adjudication": {
            "adjudication_form_id": form["post_adjudication"][
                "adjudication_form_id"
            ]
        },
    }
    return sha256_bytes(canonical_json_bytes(envelope))


def blank_saturation_audit(
    *, packet_id: str, record: dict[str, Any]
) -> dict[str, Any]:
    assignment = saturation_assignment(record)
    form = {
        "schema_version": "1.0.0",
        "record_type": "construct_validation_saturation_audit",
        "form_id": (
            f"{packet_id}.{record['family_id']}.{SATURATION_AUDITOR_ROLE}"
        ),
        "packet_id": packet_id,
        "family_id": record["family_id"],
        "source_id": record["source_id"],
        "role": SATURATION_AUDITOR_ROLE,
        "assignment_tier": "BLINDED_POST_ADJUDICATION",
        "assignment_hash": "",
        "completion_status": "not_started",
        "reviewer": {
            "reviewer_id": None,
            "declared_role": SATURATION_AUDITOR_ROLE,
            "independent_of_all_prior_reviewers": None,
            "blinded_to": [
                "accepted_ses_ledger",
                "preferred_ses",
                "machine_ranks",
                "machine_confidence",
                "machine_tier_evidence",
                "validator_decisions",
                "adjudication_decisions",
            ],
            "started_at": None,
            "completed_at": None,
            "active_minutes": None,
        },
        "assignment": assignment,
        "post_adjudication": {
            "adjudication_form_id": (
                f"{packet_id}.{record['family_id']}.adjudicator"
            ),
            "adjudication_was_frozen_before_start": None,
            "frozen_adjudication_sha256": None,
        },
        "review": {},
    }
    form["assignment_hash"] = saturation_assignment_hash(form)
    return form


def blank_adjudication(
    *, packet_id: str, record: dict[str, Any]
) -> dict[str, Any]:
    form_ids = [
        f"{packet_id}.{record['family_id']}.{role}" for role in ROLES
    ]
    return {
        "schema_version": "1.0.0",
        "record_type": "construct_validation_adjudication",
        "form_id": f"{packet_id}.{record['family_id']}.adjudicator",
        "packet_id": packet_id,
        "family_id": record["family_id"],
        "source_id": record["source_id"],
        "completion_status": "not_started",
        "reviewer": {
            "reviewer_id": None,
            "declared_role": "adjudicator",
            "independent_of_author_and_validators": None,
            "started_at": None,
            "completed_at": None,
            "active_minutes": None,
        },
        "inputs": {
            "annotation_form_ids": form_ids,
            "all_required_roles_complete": None,
            "role_independence_verified": None,
        },
        "adjudication": {},
    }
