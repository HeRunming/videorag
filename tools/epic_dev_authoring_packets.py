#!/usr/bin/env python3
"""Build and fail-closed validate Task 171's EPIC rehearsal packets."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

try:
    from .construct_validity_common import (
        ConstructValidityError,
        assignment_freeze_hash,
        exposure_event_hash,
        exposure_snapshot_hash,
        source_level_assignment_conflicts,
        validate_reviewer_assignment_ledger,
        validate_source_exposure_ledger,
    )
    from .semantic_av_source_prescreen_common import (
        REPAIR as TASK153_REPAIR,
    )
    from .semantic_av_source_prescreen_common import (
        SemanticPrescreenError,
        validate_annotation,
        validate_exposure_ledger,
        validate_inventory,
        validate_plan,
    )
    from .semantic_av_source_prescreen_common import (
        sha256_file as task153_sha256_file,
    )
    from .semantic_av_source_prescreen_import import evaluate as evaluate_prescreen
    from .semantic_av_source_prescreen_plan import build_blank_annotation, build_plan
except ImportError:
    from construct_validity_common import (
        ConstructValidityError,
        assignment_freeze_hash,
        exposure_event_hash,
        exposure_snapshot_hash,
        source_level_assignment_conflicts,
        validate_reviewer_assignment_ledger,
        validate_source_exposure_ledger,
    )
    from semantic_av_source_prescreen_common import (
        REPAIR as TASK153_REPAIR,
    )
    from semantic_av_source_prescreen_common import (
        SemanticPrescreenError,
        validate_annotation,
        validate_exposure_ledger,
        validate_inventory,
        validate_plan,
    )
    from semantic_av_source_prescreen_common import (
        sha256_file as task153_sha256_file,
    )
    from semantic_av_source_prescreen_import import evaluate as evaluate_prescreen
    from semantic_av_source_prescreen_plan import build_blank_annotation, build_plan

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data/rehearsal_plan/epic_dev_authoring_packets_v1"
TASK167_REGISTRY = (
    ROOT / "data/restricted/epic_family_candidates_v2_dev/candidate_registry.json"
)
REGISTRY_SCHEMA = (
    ROOT / "docs/spec/epic_dev_authoring_packet_registry_schema.json"
)
ROLE_FORM_SCHEMA = (
    ROOT / "docs/spec/epic_dev_authoring_role_form_schema.json"
)
IMPORT_SCHEMA = ROOT / "docs/spec/epic_dev_authoring_import_schema.json"

READY = "EPIC_DEV_AUTHORING_PACKETS_READY"
REPAIR = "EPIC_DEV_AUTHORING_PACKETS_REPAIR"
NO_GO = "EPIC_DEV_AUTHORING_PACKETS_NO_GO"
TASK167_CLASS = "MACHINE_EXPERT_PROVISIONAL_DEVELOPMENT_ONLY"
PACKET_CLASS = "DEVELOPMENT_ONLY_NON_DISTRIBUTABLE_AUTHORING_REHEARSAL"
BLIND_ROLE_EXCLUSIONS = [
    "blind_alternative_evidence_finder",
    "blind_post_adjudication_saturation_auditor",
]


class EpicPacketError(ValueError):
    """Raised when a development packet is inconsistent or unsafe."""


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def object_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def task167_object_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EpicPacketError(f"cannot read JSON {path}: {exc}") from exc


def write_json(path: Path, value: Any, *, restricted: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))
    os.chmod(path, 0o600 if restricted else 0o644)


def validate_schema_instance(value: Any, schema_path: Path, label: str) -> None:
    schema = read_json(schema_path)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(value), key=lambda error: list(error.absolute_path)
    )
    if errors:
        rendered = []
        for error in errors[:20]:
            location = ".".join(str(part) for part in error.absolute_path) or "$"
            rendered.append(f"{location}: {error.message}")
        raise EpicPacketError(
            f"{label} failed schema validation: " + "; ".join(rendered)
        )


def validate_role_form(form: dict[str, Any]) -> None:
    validate_schema_instance(form, ROLE_FORM_SCHEMA, "author/verifier form")
    if form["immutable_assignment_sha256"] != object_hash(
        form["immutable_assignment"]
    ):
        raise EpicPacketError(
            f"immutable assignment hash mismatch: {form.get('form_id')}"
        )
    assignment = form["immutable_assignment"]
    if assignment["role"] != "question_claim_author_or_verifier":
        raise EpicPacketError("author/verifier role mismatch")
    if form["completion_status"] == "not_started":
        if any(
            (
                form["reviewer"]["reviewer_id"] is not None,
                form["reviewer"]["training_attested"] is not False,
                form["reviewer"]["started_at"] is not None,
                form["reviewer"]["completed_at"] is not None,
            )
        ):
            raise EpicPacketError("blank author/verifier form contains identity/work")
        checks = [
            form["review_fields"]["question_check"],
            form["review_fields"]["answer_check"],
            *form["review_fields"]["claim_checks"],
            *form["review_fields"]["evidence_checks"],
            *form["review_fields"]["alternative_route_checks"],
        ]
        if any(
            check["finding"] != "not_recorded" or check["notes"] != ""
            for check in checks
        ):
            raise EpicPacketError("blank author/verifier form contains findings")
        if any(
            (
                form["review_fields"]["full_source_recurrence_notes"],
                form["review_fields"]["ocr_transcript_caption_narration_notes"],
                form["review_fields"]["privacy_notes"],
                form["review_fields"]["safety_notes"],
                form["review_fields"]["proposed_repairs"],
                form["review_fields"]["general_notes"],
            )
        ):
            raise EpicPacketError("blank author/verifier form contains review text")


def assignment_hash(form: dict[str, Any]) -> str:
    return object_hash(form["immutable_assignment"])


def task167_payload_hash(registry: dict[str, Any]) -> str:
    copied = copy.deepcopy(registry)
    stored = copied.pop("registry_payload_sha256", None)
    actual = task167_object_hash(copied)
    if stored != actual:
        raise EpicPacketError("Task167 registry payload hash mismatch")
    return actual


def validate_task167_registry(registry: dict[str, Any]) -> None:
    if registry.get("schema_version") != "av-trace.epic-substantive-authoring-dev/1.0":
        raise EpicPacketError("unexpected Task167 schema")
    if registry.get("artifact_classification") != TASK167_CLASS:
        raise EpicPacketError("unexpected Task167 artifact class")
    task167_payload_hash(registry)
    proposals = registry.get("proposals")
    if not isinstance(proposals, list):
        raise EpicPacketError("Task167 proposals list required")
    keeps = [item for item in proposals if item.get("disposition") == "KEEP"]
    rejects = [item for item in proposals if item.get("disposition") == "REJECT"]
    if len(keeps) != 5 or len(rejects) != 2:
        raise EpicPacketError("Task167 must expose exactly five KEEP and two REJECT")
    for proposal in proposals:
        copied = copy.deepcopy(proposal)
        stored = copied.pop("proposal_payload_sha256", None)
        if stored != task167_object_hash(copied):
            raise EpicPacketError(
                f"Task167 proposal hash mismatch: {proposal.get('proposal_id')}"
            )
        for key in (
            "future_test_eligible",
            "eligible_to_enter_gate_a",
            "human_reviewed",
            "h1_assigned",
            "h2_assigned",
        ):
            if proposal.get(key) is not False:
                raise EpicPacketError(
                    f"Task167 boundary violation: {proposal['proposal_id']}:{key}"
                )


def source_inventory(
    registry: dict[str, Any], source_id: str, source_group_id: str
) -> dict[str, Any]:
    source = registry["input_bindings"]["raw_sources"][source_id]
    inventory = {
        "schema_version": "1.0.0",
        "record_type": "semantic_av_source_prescreen_inventory",
        "inventory_id": f"epic-dev-task171-{source_id}-inventory",
        "inventory_status": "FROZEN_NONSEMANTIC_SOURCE_INVENTORY",
        "sources": [
            {
                "source_id": source_id,
                "source_group_id": source_group_id,
                "duration_s": source["duration_s"],
                "source_content_sha256": f"sha256:{source['sha256']}",
                "adapter_reference": f"local-file-adapter://{source['path']}",
                "media_included": False,
                "semantic_metadata_included": False,
            }
        ],
        "notes": (
            "Task171 development-only Task153 inventory. The prescreener receives "
            "source-uniform intervals without proposal questions, answers, claims, "
            "preferred evidence, machine ranks, or calibration records."
        ),
    }
    validate_inventory(inventory)
    return inventory


def build_source_prescreen_artifacts(
    output_dir: Path,
    registry: dict[str, Any],
    *,
    source_id: str,
    source_group_id: str,
) -> dict[str, Any]:
    source_dir = output_dir / "prescreener_packets" / source_id
    inventory_path = source_dir / "inventory.json"
    inventory = source_inventory(registry, source_id, source_group_id)
    write_json(inventory_path, inventory, restricted=True)
    plan_id = f"epic-dev-task171-{source_id}-task153-plan"
    plan = build_plan(
        inventory,
        inventory_sha256=task153_sha256_file(inventory_path),
        plan_id=plan_id,
        created_at="2026-10-02T00:00:00+08:00",
        seed=f"AVTRACE-TASK171-{source_id}-SOURCE-PRESCREEN",
        sample_count=6,
        interval_duration_s=20.0,
    )
    form = build_blank_annotation(
        plan, form_id=f"epic-dev-task171-{source_id}-prescreener-form"
    )
    validate_plan(plan)
    validate_annotation(form)
    report, exposure = evaluate_prescreen(plan, form)
    if report["readiness_token"] != TASK153_REPAIR:
        raise EpicPacketError("blank Task153 prescreen did not fail closed to REPAIR")
    if report["completion_status"] != "incomplete" or exposure["events"]:
        raise EpicPacketError("blank Task153 prescreen fabricated review/exposure")
    plan_path = source_dir / "task153_plan.json"
    form_path = source_dir / "prescreener_form.json"
    import_path = source_dir / "blank_import.json"
    exposure_path = source_dir / "blank_exposure_ledger.json"
    write_json(plan_path, plan, restricted=True)
    write_json(form_path, form, restricted=True)
    write_json(import_path, report, restricted=True)
    write_json(exposure_path, exposure, restricted=True)
    readme = source_dir / "README.md"
    readme.write_text(
        "# Task153 source prescreener packet\n\n"
        "This is a blank, development-only, non-distributable rehearsal form. "
        "The prescreener may inspect only the source and the six source-uniform "
        "intervals in `task153_plan.json`; the five proposal packets and both "
        "rejection calibrations must remain hidden. Any future completed review "
        "would create source-level exposure and permanently bar that reviewer "
        "from `blind_alternative_evidence_finder` and "
        "`blind_post_adjudication_saturation_auditor` for this source group. "
        "No identity, observation, decision, H1, or H2 is present here.\n",
        encoding="utf-8",
    )
    os.chmod(readme, 0o600)
    return {
        "source_id": source_id,
        "source_group_id": source_group_id,
        "inventory_path": str(inventory_path.relative_to(output_dir)),
        "plan_path": str(plan_path.relative_to(output_dir)),
        "prescreener_form_path": str(form_path.relative_to(output_dir)),
        "blank_import_path": str(import_path.relative_to(output_dir)),
        "blank_exposure_path": str(exposure_path.relative_to(output_dir)),
        "plan_id": plan["plan_id"],
        "plan_sha256": plan["plan_sha256"],
        "sampling_algorithm": plan["algorithm"],
        "sample_intervals": [
            {
                "sample_id": sample["sample_id"],
                "start_s": sample["start_s"],
                "end_s": sample["end_s"],
            }
            for sample in plan["samples"]
        ],
        "proposal_semantics_visible_to_prescreener": False,
    }


def role_form(
    proposal: dict[str, Any],
    source_binding: dict[str, Any],
    source_content_sha256: str,
) -> dict[str, Any]:
    packet_id = f"task171.{proposal['proposal_id']}"
    assignment = {
        "role": "question_claim_author_or_verifier",
        "source_content_sha256": source_content_sha256,
        "task167_proposal_payload_sha256": proposal["proposal_payload_sha256"],
        "task153_plan_id": source_binding["plan_id"],
        "task153_plan_sha256": source_binding["plan_sha256"],
        "task153_sample_ids": [
            item["sample_id"] for item in source_binding["sample_intervals"]
        ],
        "prescreen_must_be_completed_before_authoring": True,
        "question_hypothesis": proposal["question"],
        "answer_hypothesis": proposal["answer"],
        "claim_hypotheses": [
            {
                "claim_id": item["claim_id"],
                "text": item["text"],
                "human_validated": False,
            }
            for item in proposal["atomic_claims"]
        ],
        "evidence_hypotheses": [
            {
                "evidence_id": item["evidence_id"],
                "interval": item["interval"],
                "modality": item["modality"],
                "carrier_class": item["carrier_class"],
                "hypothesis": item["observation"],
                "record_references": item["record_references"],
                "human_semantic_validation_status": "NOT_PERFORMED",
            }
            for item in proposal["evidence_graph"]["evidence_units"]
        ],
        "alternative_route_hypotheses": [
            {
                "route_id": item["route_id"],
                "route_type": item["route_type"],
                "description": item["description"],
                "machine_status": item["status"],
            }
            for item in proposal["alternative_route_ledger"]
        ],
    }
    form = {
        "schema_version": "1.0.0",
        "record_type": "epic_dev_author_verifier_form",
        "form_id": f"{packet_id}.author-verifier",
        "packet_id": packet_id,
        "proposal_id": proposal["proposal_id"],
        "source_id": proposal["source_id"],
        "source_group_id": proposal["source_group_id"],
        "packet_status": "DRAFT_NOT_DISTRIBUTABLE",
        "completion_status": "not_started",
        "reviewer": {
            "reviewer_id": None,
            "training_attested": False,
            "started_at": None,
            "completed_at": None,
        },
        "immutable_assignment": assignment,
        "immutable_assignment_sha256": object_hash(assignment),
        "review_fields": {
            "question_check": {"finding": "not_recorded", "notes": ""},
            "answer_check": {"finding": "not_recorded", "notes": ""},
            "claim_checks": [
                {
                    "item_id": item["claim_id"],
                    "finding": "not_recorded",
                    "notes": "",
                }
                for item in proposal["atomic_claims"]
            ],
            "evidence_checks": [
                {
                    "item_id": item["evidence_id"],
                    "finding": "not_recorded",
                    "notes": "",
                }
                for item in proposal["evidence_graph"]["evidence_units"]
            ],
            "alternative_route_checks": [
                {
                    "item_id": item["route_id"],
                    "finding": "not_recorded",
                    "notes": "",
                }
                for item in proposal["alternative_route_ledger"]
            ],
            "full_source_recurrence_notes": "",
            "ocr_transcript_caption_narration_notes": "",
            "privacy_notes": "",
            "safety_notes": "",
            "proposed_repairs": [],
            "general_notes": "",
        },
        "source_level_exposure_policy": {
            "exposure_must_be_recorded": True,
            "excluded_future_roles": BLIND_ROLE_EXCLUSIONS,
        },
        "prohibited_outcomes": {
            "future_test_eligible": False,
            "gate_a_eligible": False,
            "necessity_assigned": False,
            "minimality_assigned": False,
            "h1_assigned": False,
            "h2_assigned": False,
            "human_gold": False,
        },
    }
    validate_role_form(form)
    return form


def proposal_packet_record(
    proposal: dict[str, Any],
    source_binding: dict[str, Any],
    form_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    record = {
        "packet_id": f"task171.{proposal['proposal_id']}",
        "proposal_id": proposal["proposal_id"],
        "source_id": proposal["source_id"],
        "source_group_id": proposal["source_group_id"],
        "task167_proposal_payload_sha256": proposal["proposal_payload_sha256"],
        "question_hypothesis": proposal["question"],
        "answer_hypothesis": proposal["answer"],
        "claim_hypotheses": [
            {
                "claim_id": item["claim_id"],
                "text": item["text"],
                "human_validated": False,
            }
            for item in proposal["atomic_claims"]
        ],
        "evidence_hypotheses": [
            {
                "evidence_id": item["evidence_id"],
                "interval": item["interval"],
                "modality": item["modality"],
                "carrier_class": item["carrier_class"],
                "hypothesis": item["observation"],
                "record_references": item["record_references"],
                "human_semantic_validation_status": "NOT_PERFORMED",
            }
            for item in proposal["evidence_graph"]["evidence_units"]
        ],
        "task153_prescreen_binding": {
            "plan_id": source_binding["plan_id"],
            "plan_sha256": source_binding["plan_sha256"],
            "sample_ids": [
                item["sample_id"] for item in source_binding["sample_intervals"]
            ],
            "sample_intervals": copy.deepcopy(
                source_binding["sample_intervals"]
            ),
        },
        "author_verifier_form_path": str(form_path.relative_to(output_dir)),
        "role_exposure_policy": {
            "source_level_exposure": True,
            "excluded_future_roles": BLIND_ROLE_EXCLUSIONS,
        },
        "scope": {
            "future_test_eligible": False,
            "gate_a_eligible": False,
            "human_review_performed": False,
            "human_decision_recorded": False,
            "h1_assigned": False,
            "h2_assigned": False,
        },
        "packet_payload_sha256": "",
    }
    copied = copy.deepcopy(record)
    copied.pop("packet_payload_sha256")
    record["packet_payload_sha256"] = object_hash(copied)
    return record


def calibration_record(
    proposal: dict[str, Any], index: int, output_dir: Path
) -> dict[str, Any]:
    calibration_id = f"task171.calibration.reject-{index:02d}"
    path = output_dir / "calibrations" / f"reject_{index:02d}.json"
    record = {
        "calibration_id": calibration_id,
        "source_proposal_id": proposal["proposal_id"],
        "source_id": proposal["source_id"],
        "example_type": "TASK167_MACHINE_REJECTION_CALIBRATION",
        "inherited_machine_disposition": "REJECT",
        "not_a_human_decision": True,
        "question_hypothesis": proposal["question"],
        "answer_hypothesis": proposal["answer"],
        "rejection_signals": [
            proposal["disposition_rationale"],
            *[
                f"{item['route_type']}: {item['description']}"
                for item in proposal["alternative_route_ledger"]
            ],
        ],
        "calibration_lesson": (
            "Reject rather than force a development packet when recurrence, "
            "underspecification, or package/single-frame shortcuts prevent a "
            "distinct defensible authoring route. This inherits Task167's "
            "machine disposition and is not human review."
        ),
        "file_path": str(path.relative_to(output_dir)),
        "future_test_eligible": False,
        "gate_a_eligible": False,
    }
    write_json(path, record, restricted=True)
    return record


def governance_source_groups(
    proposal_packets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, set[str]]] = {}
    for packet in proposal_packets:
        group = grouped.setdefault(
            packet["source_group_id"],
            {"source_ids": set(), "family_ids": set()},
        )
        group["source_ids"].add(packet["source_id"])
        group["family_ids"].add(packet["proposal_id"])
    return [
        {
            "source_group_id": group_id,
            "source_ids": sorted(value["source_ids"]),
            "family_ids": sorted(value["family_ids"]),
        }
        for group_id, value in sorted(grouped.items())
    ]


def build_governance(
    output_dir: Path, proposal_packets: list[dict[str, Any]]
) -> None:
    packet_id = "epic-dev-authoring-packets-v1"
    source_groups = governance_source_groups(proposal_packets)
    captured_at = "2026-10-02T00:00:00+08:00"
    snapshot = {"captured_at": captured_at, "events": []}
    exposure = {
        "schema_version": "1.0.0",
        "record_type": "construct_validation_source_exposure_ledger",
        "packet_id": packet_id,
        "ledger_status": "OPEN_APPEND_ONLY",
        "source_groups": source_groups,
        "pre_distribution_snapshot": snapshot,
        "pre_distribution_snapshot_sha256": exposure_snapshot_hash(snapshot),
        "review_events": [],
        "notes": (
            "Task171 blank source-level exposure ledger. Before any later "
            "authorized rehearsal, add prescreener and author/verifier exposure "
            "as external_prior_work with preferred_evidence, then validate "
            "blind-role conflicts. No events are present in this task."
        ),
    }
    assignments = []
    for packet in sorted(proposal_packets, key=lambda item: item["proposal_id"]):
        for role in (
            "question_claim_author_or_verifier",
            "blind_alternative_evidence_finder",
            "blind_post_adjudication_saturation_auditor",
        ):
            assignments.append(
                {
                    "assignment_id": (
                        f"{packet_id}.{packet['proposal_id']}.{role}"
                    ),
                    "source_group_id": packet["source_group_id"],
                    "family_id": packet["proposal_id"],
                    "role": role,
                    "reviewer_id": None,
                    "assigned_at": None,
                }
            )
    role_matrix = {
        "schema_version": "1.0.0",
        "record_type": "epic_dev_authoring_role_matrix",
        "packet_id": packet_id,
        "assignment_status": "DRAFT_NOT_DISTRIBUTABLE",
        "distribution_authorized": False,
        "source_groups": source_groups,
        "assignments": assignments,
        "source_level_rules": [
            {
                "exposed_role": "semantic_av_source_prescreener",
                "exposure_scope": "source_group",
                "excluded_future_roles": BLIND_ROLE_EXCLUSIONS,
            },
            {
                "exposed_role": "question_claim_author_or_verifier",
                "exposure_scope": "source_group",
                "excluded_future_roles": BLIND_ROLE_EXCLUSIONS,
            },
        ],
        "notes": (
            "All reviewer IDs and assignment timestamps are null. This matrix is "
            "not a construct-validity six-role assignment ledger and may not be "
            "frozen or distributed. It documents Task171's source-level role "
            "separation only."
        ),
    }
    validate_source_exposure_ledger(exposure)
    write_json(
        output_dir / "coordinator/source_exposure_ledger.json",
        exposure,
        restricted=True,
    )
    write_json(
        output_dir / "coordinator/role_assignment_matrix.json",
        role_matrix,
        restricted=True,
    )


def build_registry(output_dir: Path, registry: dict[str, Any]) -> dict[str, Any]:
    keeps = [item for item in registry["proposals"] if item["disposition"] == "KEEP"]
    rejects = [
        item for item in registry["proposals"] if item["disposition"] == "REJECT"
    ]
    source_groups = {
        proposal["source_id"]: proposal["source_group_id"] for proposal in keeps
    }
    source_bindings = {}
    for source_id in sorted(source_groups):
        source_bindings[source_id] = build_source_prescreen_artifacts(
            output_dir,
            registry,
            source_id=source_id,
            source_group_id=source_groups[source_id],
        )
    proposal_packets = []
    for proposal in sorted(keeps, key=lambda item: item["proposal_id"]):
        packet_dir = output_dir / "author_verifier_packets" / proposal["proposal_id"]
        form_path = packet_dir / "author_verifier_form.json"
        source_sha = "sha256:" + registry["input_bindings"]["raw_sources"][
            proposal["source_id"]
        ]["sha256"]
        form = role_form(proposal, source_bindings[proposal["source_id"]], source_sha)
        write_json(form_path, form, restricted=True)
        (packet_dir / "README.md").write_text(
            "# Author/verifier rehearsal packet\n\n"
            "This blank form exposes the Task167 machine-provisional question, "
            "answer, claims, evidence hypotheses, and alternative-route "
            "hypotheses only after a separate Task153 source prescreen would be "
            "completed. It is not distributable and contains no identity or "
            "human finding. Exposure to this packet is source-level and bars "
            "the same person from both blind finder and blind saturation roles "
            "for the source group. The form cannot assign necessity, "
            "minimality, H1, H2, Gate-A eligibility, or future-test eligibility.\n",
            encoding="utf-8",
        )
        os.chmod(packet_dir / "README.md", 0o600)
        proposal_packets.append(
            proposal_packet_record(
                proposal,
                source_bindings[proposal["source_id"]],
                form_path,
                output_dir,
            )
        )
    calibrations = [
        calibration_record(proposal, index, output_dir)
        for index, proposal in enumerate(
            sorted(rejects, key=lambda item: item["proposal_id"]), start=1
        )
    ]
    packet_registry = {
        "schema_version": "1.0.0",
        "record_type": "epic_dev_authoring_packet_registry",
        "registry_id": "epic-dev-authoring-packets-v1",
        "created_date": "2026-10-02",
        "artifact_classification": PACKET_CLASS,
        "packet_status": "DRAFT_NOT_DISTRIBUTABLE",
        "source_registry_binding": {
            "path": str(TASK167_REGISTRY.relative_to(ROOT)),
            "file_sha256": file_hash(TASK167_REGISTRY),
            "registry_payload_sha256": registry["registry_payload_sha256"],
        },
        "scope": {
            "development_only": True,
            "distribution_authorized": False,
            "future_test_eligible": False,
            "gate_a_eligible": False,
            "human_review_performed": False,
            "human_decision_recorded": False,
            "h1_assigned": False,
            "h2_assigned": False,
            "necessity_claimed": False,
            "minimality_claimed": False,
        },
        "source_prescreen_bindings": [
            source_bindings[source_id] for source_id in sorted(source_bindings)
        ],
        "proposal_packets": proposal_packets,
        "calibration_rejection_examples": calibrations,
        "registry_payload_sha256": "",
    }
    copied = copy.deepcopy(packet_registry)
    copied.pop("registry_payload_sha256")
    packet_registry["registry_payload_sha256"] = object_hash(copied)
    validate_schema_instance(
        packet_registry, REGISTRY_SCHEMA, "Task171 packet registry"
    )
    write_json(
        output_dir / "coordinator/packet_registry.json",
        packet_registry,
        restricted=True,
    )
    build_governance(output_dir, proposal_packets)
    return packet_registry


def build_manifest(output_dir: Path) -> dict[str, Any]:
    excluded = {
        "coordinator/packet_manifest.json",
        "coordinator/blank_import_report.json",
    }
    artifacts = []
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = str(path.relative_to(output_dir))
        if relative in excluded:
            continue
        artifacts.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": file_hash(path),
            }
        )
    manifest = {
        "schema_version": "1.0.0",
        "record_type": "epic_dev_authoring_packet_manifest",
        "packet_id": "epic-dev-authoring-packets-v1",
        "generated_at": "2026-10-02T00:00:00+08:00",
        "packet_status": "DRAFT_NOT_DISTRIBUTABLE",
        "distribution_authorized": False,
        "development_only": True,
        "future_test_eligible": False,
        "gate_a_eligible": False,
        "human_review_occurred": False,
        "identity_count": 0,
        "human_decision_count": 0,
        "proposal_count": 5,
        "calibration_rejection_count": 2,
        "source_count": 2,
        "artifacts": artifacts,
    }
    write_json(
        output_dir / "coordinator/packet_manifest.json",
        manifest,
        restricted=True,
    )
    return manifest


def validate_manifest(output_dir: Path, manifest: dict[str, Any]) -> None:
    if manifest.get("packet_status") != "DRAFT_NOT_DISTRIBUTABLE":
        raise EpicPacketError("manifest packet status is distributable")
    if manifest.get("distribution_authorized") is not False:
        raise EpicPacketError("manifest distribution authorization forbidden")
    if any(
        manifest.get(key) is not False
        for key in (
            "future_test_eligible",
            "gate_a_eligible",
            "human_review_occurred",
        )
    ):
        raise EpicPacketError("manifest boundary flags invalid")
    expected_paths = set()
    for artifact in manifest["artifacts"]:
        relative = artifact["path"]
        if relative in expected_paths:
            raise EpicPacketError(f"duplicate manifest path: {relative}")
        expected_paths.add(relative)
        path = output_dir / relative
        if not path.is_file() or path.is_symlink():
            raise EpicPacketError(f"manifest artifact missing/unsafe: {relative}")
        if path.stat().st_size != artifact["bytes"]:
            raise EpicPacketError(f"manifest byte mismatch: {relative}")
        if file_hash(path) != artifact["sha256"]:
            raise EpicPacketError(f"manifest hash mismatch: {relative}")
    actual_paths = {
        str(path.relative_to(output_dir))
        for path in output_dir.rglob("*")
        if path.is_file()
        and str(path.relative_to(output_dir))
        not in {
            "coordinator/packet_manifest.json",
            "coordinator/blank_import_report.json",
        }
    }
    if actual_paths != expected_paths:
        raise EpicPacketError("manifest file set mismatch")


def validate_registry(
    output_dir: Path,
    packet_registry: dict[str, Any],
    task167: dict[str, Any],
) -> None:
    validate_schema_instance(
        packet_registry, REGISTRY_SCHEMA, "Task171 packet registry"
    )
    copied = copy.deepcopy(packet_registry)
    stored = copied.pop("registry_payload_sha256")
    if stored != object_hash(copied):
        raise EpicPacketError("Task171 registry payload hash mismatch")
    if packet_registry["source_registry_binding"]["file_sha256"] != file_hash(
        TASK167_REGISTRY
    ):
        raise EpicPacketError("Task167 file binding mismatch")
    if packet_registry["source_registry_binding"][
        "registry_payload_sha256"
    ] != task167_payload_hash(task167):
        raise EpicPacketError("Task167 payload binding mismatch")
    task167_by_id = {item["proposal_id"]: item for item in task167["proposals"]}
    if {
        item["proposal_id"] for item in packet_registry["proposal_packets"]
    } != {
        item["proposal_id"]
        for item in task167["proposals"]
        if item["disposition"] == "KEEP"
    }:
        raise EpicPacketError("Task171 proposal set is not exact Task167 KEEP set")
    source_bindings = {
        item["source_id"]: item
        for item in packet_registry["source_prescreen_bindings"]
    }
    for binding in source_bindings.values():
        plan = read_json(output_dir / binding["plan_path"])
        form = read_json(output_dir / binding["prescreener_form_path"])
        report = read_json(output_dir / binding["blank_import_path"])
        exposure = read_json(output_dir / binding["blank_exposure_path"])
        validate_plan(plan)
        validate_annotation(form)
        validate_exposure_ledger(exposure)
        rebuilt_report, rebuilt_exposure = evaluate_prescreen(plan, form)
        if report != rebuilt_report or exposure != rebuilt_exposure:
            raise EpicPacketError("Task153 blank import artifacts are stale")
        if report["readiness_token"] != TASK153_REPAIR:
            raise EpicPacketError("blank prescreen did not fail closed to REPAIR")
        if binding["proposal_semantics_visible_to_prescreener"] is not False:
            raise EpicPacketError("prescreener semantic firewall disabled")
        expected_intervals = [
            {
                "sample_id": item["sample_id"],
                "start_s": item["start_s"],
                "end_s": item["end_s"],
            }
            for item in plan["samples"]
        ]
        if binding["sample_intervals"] != expected_intervals:
            raise EpicPacketError("Task153 sample interval binding mismatch")
    for packet in packet_registry["proposal_packets"]:
        source = task167_by_id[packet["proposal_id"]]
        if source["disposition"] != "KEEP":
            raise EpicPacketError("non-KEEP proposal in substantive packet set")
        if packet["task167_proposal_payload_sha256"] != source[
            "proposal_payload_sha256"
        ]:
            raise EpicPacketError("proposal payload binding mismatch")
        if packet["question_hypothesis"] != source["question"]:
            raise EpicPacketError("question hypothesis differs from Task167")
        if packet["answer_hypothesis"] != source["answer"]:
            raise EpicPacketError("answer hypothesis differs from Task167")
        copied_packet = copy.deepcopy(packet)
        stored_packet_hash = copied_packet.pop("packet_payload_sha256")
        if stored_packet_hash != object_hash(copied_packet):
            raise EpicPacketError("packet payload hash mismatch")
        binding = source_bindings[packet["source_id"]]
        if packet["task153_prescreen_binding"]["plan_id"] != binding["plan_id"]:
            raise EpicPacketError("proposal Task153 plan binding mismatch")
        if packet["task153_prescreen_binding"]["sample_intervals"] != binding[
            "sample_intervals"
        ]:
            raise EpicPacketError("proposal Task153 intervals mismatch")
        form = read_json(output_dir / packet["author_verifier_form_path"])
        validate_role_form(form)
        if form["proposal_id"] != packet["proposal_id"]:
            raise EpicPacketError("author form proposal mismatch")
        if form["immutable_assignment"]["question_hypothesis"] != packet[
            "question_hypothesis"
        ]:
            raise EpicPacketError("author form question binding mismatch")
    calibration_ids = {
        item["source_proposal_id"]
        for item in packet_registry["calibration_rejection_examples"]
    }
    expected_rejects = {
        item["proposal_id"]
        for item in task167["proposals"]
        if item["disposition"] == "REJECT"
    }
    if calibration_ids != expected_rejects:
        raise EpicPacketError("calibration set is not exact Task167 REJECT set")
    for calibration in packet_registry["calibration_rejection_examples"]:
        if read_json(output_dir / calibration["file_path"]) != calibration:
            raise EpicPacketError("calibration file/registry mismatch")


def source_level_exposure_self_test(
    packet_registry: dict[str, Any],
) -> None:
    """Prove prescreener and author exposure block both blind roles."""
    records = packet_registry["proposal_packets"]
    source_groups = governance_source_groups(records)
    packet_id = "task171-conflict-self-test"
    prescreener_id = "task171-prescreener-exposure-self-test"
    author_id = "task171-author-exposure-self-test"
    events = []
    previous = None
    sequence = 1
    for reviewer_id, exposure_note in (
        (prescreener_id, "semantic source prescreener"),
        (author_id, "question/claim author or verifier"),
    ):
        event = {
            "event_id": f"task171-self-test-{sequence}",
            "sequence": sequence,
            "previous_event_sha256": previous,
            "reviewer_id": reviewer_id,
            "source_group_id": source_groups[0]["source_group_id"],
            "family_id": None,
            "role": "external_prior_work",
            "exposure_categories": ["source_content", "preferred_evidence"],
            "exposed_at": "2026-10-02T01:00:00+08:00",
            "recorded_at": "2026-10-02T01:00:00+08:00",
            "artifact_references": ["task171-source-level-exposure-self-test"],
            "notes": (
                f"Synthetic {exposure_note} validation event; not a human "
                "identity or review."
            ),
            "event_sha256": "",
        }
        event["event_sha256"] = exposure_event_hash(event)
        previous = event["event_sha256"]
        events.append(event)
        sequence += 1
    snapshot = {"captured_at": "2026-10-02T01:00:00+08:00", "events": events}
    exposure = {
        "schema_version": "1.0.0",
        "record_type": "construct_validation_source_exposure_ledger",
        "packet_id": packet_id,
        "ledger_status": "OPEN_APPEND_ONLY",
        "source_groups": source_groups,
        "pre_distribution_snapshot": snapshot,
        "pre_distribution_snapshot_sha256": exposure_snapshot_hash(snapshot),
        "review_events": [],
        "notes": "Synthetic conflict self-test only.",
    }
    roles = (
        "question_claim_author_or_verifier",
        "blind_alternative_evidence_finder",
        "validator_a",
        "validator_b",
        "adjudicator",
        "blind_post_adjudication_saturation_auditor",
    )
    assignments = []
    first_group_family_ids = source_groups[0]["family_ids"]
    blind_reuse = {
        (
            first_group_family_ids[0],
            "blind_alternative_evidence_finder",
            prescreener_id,
        ),
        (
            first_group_family_ids[1],
            "blind_post_adjudication_saturation_auditor",
            author_id,
        ),
    }
    for record in records:
        for role in roles:
            assignments.append(
                {
                    "assignment_id": f"{packet_id}.{record['proposal_id']}.{role}",
                    "source_group_id": record["source_group_id"],
                    "family_id": record["proposal_id"],
                    "role": role,
                    "reviewer_id": next(
                        (
                            identity
                            for family_id, blind_role, identity in blind_reuse
                            if family_id == record["proposal_id"]
                            and blind_role == role
                        ),
                        None,
                    ),
                    "assigned_at": None,
                }
            )
    assignments_ledger = {
        "schema_version": "1.0.0",
        "record_type": "construct_validation_reviewer_assignment_ledger",
        "packet_id": packet_id,
        "generated_at": "2026-10-02T00:00:00+08:00",
        "assignment_status": "DRAFT_NOT_DISTRIBUTABLE",
        "frozen_at": None,
        "distribution_authorized": False,
        "pre_distribution_exposure_snapshot_sha256": exposure[
            "pre_distribution_snapshot_sha256"
        ],
        "assignment_freeze_sha256": None,
        "source_groups": source_groups,
        "assignments": assignments,
        "notes": "Synthetic conflict self-test only.",
    }
    # Draft schema requires all identities null, so validate the structural
    # ledger first, then use a deep copy with synthetic blind identities solely
    # against the conflict function's already-validated shape by temporarily
    # freezing it with distinct placeholders.
    structural = copy.deepcopy(assignments_ledger)
    for item in structural["assignments"]:
        item["reviewer_id"] = None
    validate_reviewer_assignment_ledger(structural)
    validate_source_exposure_ledger(exposure)
    # Use a frozen, fully-populated ledger so the production conflict function
    # can be exercised without weakening its schema.
    frozen = copy.deepcopy(assignments_ledger)
    frozen["assignment_status"] = "FROZEN_BEFORE_DISTRIBUTION"
    frozen["frozen_at"] = "2026-10-02T02:00:00+08:00"
    frozen["distribution_authorized"] = True
    used_by_family: dict[str, set[str]] = {}
    for index, item in enumerate(frozen["assignments"], start=1):
        if item["reviewer_id"] is None:
            candidate = f"task171-self-test-{index:03d}"
            while candidate in used_by_family.setdefault(item["family_id"], set()):
                candidate += "x"
            item["reviewer_id"] = candidate
        used_by_family.setdefault(item["family_id"], set()).add(
            item["reviewer_id"]
        )
        item["assigned_at"] = "2026-10-02T01:30:00+08:00"
    # The two blind rows for the first source group deliberately reuse the
    # exposed synthetic reviewer; they belong to different families/roles and
    # remain distinct within each family.
    frozen["assignment_freeze_sha256"] = assignment_freeze_hash(frozen)
    validate_reviewer_assignment_ledger(frozen)
    conflicts = source_level_assignment_conflicts(frozen, exposure)
    affected = [
        item["family_id"]
        for item in frozen["assignments"]
        if item["reviewer_id"] in {prescreener_id, author_id}
        and item["role"] in BLIND_ROLE_EXCLUSIONS
    ]
    if len(affected) != 2 or any(
        "SOURCE_GROUP_BLIND_ROLE_EXPOSURE_CONFLICT" not in conflicts[family_id]
        for family_id in affected
    ):
        raise EpicPacketError("source-level blind-role exclusion self-test failed")


def evaluate_packet_dir(output_dir: Path) -> dict[str, Any]:
    try:
        task167 = read_json(TASK167_REGISTRY)
        validate_task167_registry(task167)
        registry_path = output_dir / "coordinator/packet_registry.json"
        manifest_path = output_dir / "coordinator/packet_manifest.json"
        packet_registry = read_json(registry_path)
        manifest = read_json(manifest_path)
        validate_registry(output_dir, packet_registry, task167)
        validate_manifest(output_dir, manifest)
        exposure = read_json(output_dir / "coordinator/source_exposure_ledger.json")
        validate_source_exposure_ledger(exposure)
        role_matrix = read_json(
            output_dir / "coordinator/role_assignment_matrix.json"
        )
        if role_matrix["assignment_status"] != "DRAFT_NOT_DISTRIBUTABLE":
            raise EpicPacketError("role matrix is not draft")
        if role_matrix["distribution_authorized"] is not False:
            raise EpicPacketError("role matrix authorizes distribution")
        if any(
            item["reviewer_id"] is not None or item["assigned_at"] is not None
            for item in role_matrix["assignments"]
        ):
            raise EpicPacketError("role matrix contains identities/assignments")
        source_level_exposure_self_test(packet_registry)
        prescreen_results = []
        for binding in packet_registry["source_prescreen_bindings"]:
            report = read_json(output_dir / binding["blank_import_path"])
            exposure_ledger = read_json(output_dir / binding["blank_exposure_path"])
            prescreen_results.append(
                {
                    "source_id": binding["source_id"],
                    "plan_id": binding["plan_id"],
                    "sample_count": len(binding["sample_intervals"]),
                    "completion_status": report["completion_status"],
                    "task153_readiness_token": report["readiness_token"],
                    "exposure_event_count": len(exposure_ledger["events"]),
                }
            )
        author_form_results = []
        for packet in packet_registry["proposal_packets"]:
            form = read_json(output_dir / packet["author_verifier_form_path"])
            author_form_results.append(
                {
                    "proposal_id": packet["proposal_id"],
                    "completion_status": form["completion_status"],
                    "reviewer_id_present": form["reviewer"]["reviewer_id"] is not None,
                    "human_findings_recorded": False,
                }
            )
        report = {
            "schema_version": "1.0.0",
            "record_type": "epic_dev_authoring_packet_import",
            "packet_id": "epic-dev-authoring-packets-v1",
            "packet_status": "DRAFT_NOT_DISTRIBUTABLE",
            "readiness_token": READY,
            "schema_validation_pass": True,
            "manifest_validation_pass": True,
            "semantic_firewall_pass": True,
            "source_level_blindness_enforced": True,
            "distribution_authorized": False,
            "human_review_occurred": False,
            "identity_count": 0,
            "human_decision_count": 0,
            "proposal_count": len(packet_registry["proposal_packets"]),
            "calibration_rejection_count": len(
                packet_registry["calibration_rejection_examples"]
            ),
            "source_count": len(packet_registry["source_prescreen_bindings"]),
            "prescreen_results": prescreen_results,
            "author_form_results": author_form_results,
            "future_test_eligible": False,
            "gate_a_eligible": False,
            "necessity_assigned": False,
            "minimality_assigned": False,
            "h1_assigned": False,
            "h2_assigned": False,
            "errors": [],
        }
        validate_schema_instance(report, IMPORT_SCHEMA, "Task171 import report")
        return report
    except (
        EpicPacketError,
        SemanticPrescreenError,
        ConstructValidityError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        report = {
            "schema_version": "1.0.0",
            "record_type": "epic_dev_authoring_packet_import",
            "packet_id": "epic-dev-authoring-packets-v1",
            "packet_status": "DRAFT_NOT_DISTRIBUTABLE",
            "readiness_token": REPAIR,
            "schema_validation_pass": False,
            "manifest_validation_pass": False,
            "semantic_firewall_pass": False,
            "source_level_blindness_enforced": True,
            "distribution_authorized": False,
            "human_review_occurred": False,
            "identity_count": 0,
            "human_decision_count": 0,
            "proposal_count": 5,
            "calibration_rejection_count": 2,
            "source_count": 2,
            "prescreen_results": [],
            "author_form_results": [],
            "future_test_eligible": False,
            "gate_a_eligible": False,
            "necessity_assigned": False,
            "minimality_assigned": False,
            "h1_assigned": False,
            "h2_assigned": False,
            "errors": [f"{type(exc).__name__}:{exc}"],
        }
        validate_schema_instance(report, IMPORT_SCHEMA, "Task171 failed import report")
        return report


def build(output_dir: Path) -> dict[str, Any]:
    task167 = read_json(TASK167_REGISTRY)
    validate_task167_registry(task167)
    if output_dir.exists():
        if output_dir.is_symlink():
            raise EpicPacketError("output directory may not be a symlink")
        shutil.rmtree(output_dir)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=".epic_dev_authoring_packets.", dir=output_dir.parent)
    )
    try:
        os.chmod(staging, 0o700)
        build_registry(staging, task167)
        readme = staging / "README.md"
        readme.write_text(
            "# EPIC development authoring packets v1\n\n"
            "Task171 converts Task167's five KEEP proposals into restricted, "
            "non-distributable rehearsal packets. Prescreener packets are "
            "semantic-firewalled and contain only Task153 source-uniform "
            "interval plans and blank forms. Author/verifier packets contain "
            "machine-provisional question, answer, claim, evidence, and route "
            "hypotheses, but no identity or human decision. Both exposed roles "
            "are source-level ineligible for future blind finder and blind "
            "post-adjudication saturation roles. Every artifact is permanently "
            "future-test-ineligible and Gate-A-ineligible.\n",
            encoding="utf-8",
        )
        os.chmod(readme, 0o600)
        build_manifest(staging)
        report = evaluate_packet_dir(staging)
        if report["readiness_token"] != READY:
            raise EpicPacketError(";".join(report["errors"]))
        write_json(
            staging / "coordinator/blank_import_report.json",
            report,
            restricted=True,
        )
        for directory in staging.rglob("*"):
            if directory.is_dir():
                os.chmod(directory, 0o700)
        os.replace(staging, output_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return evaluate_packet_dir(output_dir)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--verify-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = (
            evaluate_packet_dir(args.output_dir)
            if args.verify_only
            else build(args.output_dir)
        )
    except EpicPacketError as exc:
        print(f"{NO_GO}: {exc}")
        return 2
    print(report["readiness_token"])
    if report["errors"]:
        print("\n".join(report["errors"]))
    return 0 if report["readiness_token"] == READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
