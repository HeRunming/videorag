#!/usr/bin/env python3
"""Build and fail-closed validate unified Task199 pilot-v4 human packets."""

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
        exposure_snapshot_hash,
        validate_reviewer_assignment_ledger,
        validate_source_exposure_ledger,
    )
    from .semantic_av_source_prescreen_common import (
        REPAIR as TASK153_REPAIR,
    )
    from .semantic_av_source_prescreen_common import (
        sha256_file as task153_sha256_file,
    )
    from .semantic_av_source_prescreen_common import (
        validate_annotation as validate_task153_annotation,
    )
    from .semantic_av_source_prescreen_common import (
        validate_exposure_ledger as validate_task153_exposure,
    )
    from .semantic_av_source_prescreen_common import (
        validate_inventory as validate_task153_inventory,
    )
    from .semantic_av_source_prescreen_common import (
        validate_plan as validate_task153_plan,
    )
    from .semantic_av_source_prescreen_import import evaluate as evaluate_task153
    from .semantic_av_source_prescreen_plan import (
        build_blank_annotation,
        build_plan,
    )
except ImportError:
    from construct_validity_common import (
        exposure_snapshot_hash,
        validate_reviewer_assignment_ledger,
        validate_source_exposure_ledger,
    )
    from semantic_av_source_prescreen_common import REPAIR as TASK153_REPAIR
    from semantic_av_source_prescreen_common import (
        sha256_file as task153_sha256_file,
    )
    from semantic_av_source_prescreen_common import (
        validate_annotation as validate_task153_annotation,
    )
    from semantic_av_source_prescreen_common import (
        validate_exposure_ledger as validate_task153_exposure,
    )
    from semantic_av_source_prescreen_common import (
        validate_inventory as validate_task153_inventory,
    )
    from semantic_av_source_prescreen_common import (
        validate_plan as validate_task153_plan,
    )
    from semantic_av_source_prescreen_import import evaluate as evaluate_task153
    from semantic_av_source_prescreen_plan import (
        build_blank_annotation,
        build_plan,
    )

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data/rehearsal_plan/pilot_v4_human_packets"
MATRIX_PATH = ROOT / "data/rehearsal_plan/pilot_v4_candidate_matrix.json"
TASK194_ROOT = ROOT / "data/rehearsal_plan/audio_candidate_prescreen_packets_v1"
REGISTRY_SCHEMA = ROOT / "docs/spec/pilot_v4_human_packet_registry_schema.json"
AUTHOR_FORM_SCHEMA = ROOT / "docs/spec/pilot_v4_author_verifier_form_schema.json"
IMPORT_SCHEMA = ROOT / "docs/spec/pilot_v4_human_packet_import_schema.json"
CALIBRATION_SCHEMA = ROOT / "docs/spec/pilot_v4_excluded_calibration_schema.json"
TASK194_PACKET_SCHEMA = ROOT / "docs/spec/audio_candidate_prescreen_packet_schema.json"
TASK194_FORM_SCHEMA = ROOT / "docs/spec/audio_candidate_prescreen_form_schema.json"
TASK194_IMPORT_SCHEMA = ROOT / "docs/spec/audio_candidate_prescreen_import_schema.json"

READY = "PILOT_V4_HUMAN_PACKETS_READY"
REPAIR = "PILOT_V4_HUMAN_PACKETS_REPAIR"
NO_GO = "PILOT_V4_HUMAN_PACKETS_NO_GO"
PACKET_ID = "pilot-v4-human-packets-task199"
CREATED_AT = "2026-10-10T00:00:00+08:00"
CREATED_DATE = "2026-10-10"
PACKET_CLASS = "PRE_DISTRIBUTION_HUMAN_PACKET_PREPARATION_ONLY"
ROLES = (
    "question_claim_author_or_verifier",
    "blind_alternative_evidence_finder",
    "validator_a",
    "validator_b",
    "adjudicator",
    "blind_post_adjudication_saturation_auditor",
)
BLIND_ROLES = (
    "blind_alternative_evidence_finder",
    "blind_post_adjudication_saturation_auditor",
)
AUDIO_ORDER = (
    "audio_only_focal",
    "synchronized_av_focal",
    "audio_only_recurrence_probes",
)

SOURCE_ADAPTERS = {
    "P27_101": "local-file-adapter://data/restricted/epic_wave1_sources_v1/media/P27/P27_101.MP4",
    "P28_103": "local-file-adapter://data/restricted/epic_wave1_sources_v1/media/P28/P28_103.MP4",
    "16_20": "restricted-file://data/restricted/captaincook4d_wave0_sources_v3/16_20_360p.mp4",
    "15_29": "restricted-file://data/restricted/captaincook4d_wave0_sources_v3/15_29_360p.mp4",
    "26_22": "restricted-file://data/restricted/captaincook4d_wave0_sources_v3/26_22_360p.mp4",
    "cand-052": "restricted-file://data/restricted/noaa01/raw/08_climatealive_archive_1001_smc.mp4",
}


class PilotV4PacketError(ValueError):
    """Raised when the Task199 packet set is inconsistent or unsafe."""


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
        raise PilotV4PacketError(f"cannot read JSON {path}: {exc}") from exc


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))
    os.chmod(path, 0o600)


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    os.chmod(path, 0o600)


def secure_tree(root: Path) -> None:
    for directory, _, files in os.walk(root):
        os.chmod(directory, 0o700)
        for name in files:
            os.chmod(Path(directory) / name, 0o600)


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
        raise PilotV4PacketError(
            f"{label} failed schema validation: " + "; ".join(rendered)
        )


def source_records(matrix: dict[str, Any]) -> list[dict[str, Any]]:
    records = copy.deepcopy(matrix["source_selection"]["sources"])
    if len(records) != 6:
        raise PilotV4PacketError("pilot-v4 matrix must contain exactly six sources")
    for source in records:
        if source["source_id"] not in SOURCE_ADAPTERS:
            raise PilotV4PacketError(
                f"missing restricted adapter for {source['source_id']}"
            )
        if len(source["candidate_slots"]) != 2:
            raise PilotV4PacketError(
                f"source must have exactly two slots: {source['source_id']}"
            )
    return records


def validate_matrix(matrix: dict[str, Any]) -> None:
    if matrix.get("decision_token") != "PILOT_V4_CANDIDATE_MATRIX_REPAIR":
        raise PilotV4PacketError("unexpected pilot-v4 matrix decision")
    slots = matrix.get("candidate_slots")
    if not isinstance(slots, list) or len(slots) != 12:
        raise PilotV4PacketError("pilot-v4 matrix must contain exactly twelve slots")
    sources = source_records(matrix)
    expected_slots = {
        slot_id for source in sources for slot_id in source["candidate_slots"]
    }
    actual_slots = {slot["slot_id"] for slot in slots}
    if actual_slots != expected_slots or len(actual_slots) != 12:
        raise PilotV4PacketError("matrix source/slot composition mismatch")
    for slot in slots:
        boundary = slot["construct_boundary"]
        if any(boundary.values()):
            raise PilotV4PacketError(
                f"matrix slot already contains construct acceptance: {slot['slot_id']}"
            )
        if slot["current_tier"] != "P0_MACHINE_CANDIDATE":
            raise PilotV4PacketError(
                f"matrix slot is not P0: {slot['slot_id']}"
            )
        if slot["profile"]["necessity_claimed"] is not False:
            raise PilotV4PacketError(
                f"matrix slot claims necessity: {slot['slot_id']}"
            )


def build_inventory(source: dict[str, Any]) -> dict[str, Any]:
    inventory = {
        "schema_version": "1.0.0",
        "record_type": "semantic_av_source_prescreen_inventory",
        "inventory_id": f"task199-{source['source_id']}-task153-inventory",
        "inventory_status": "FROZEN_NONSEMANTIC_SOURCE_INVENTORY",
        "sources": [
            {
                "source_id": source["source_id"],
                "source_group_id": source["source_group_id"],
                "duration_s": source["duration_s"],
                "source_content_sha256": f"sha256:{source['source_sha256']}",
                "adapter_reference": SOURCE_ADAPTERS[source["source_id"]],
                "media_included": False,
                "semantic_metadata_included": False,
            }
        ],
        "notes": (
            "Task199 source-specific Task153 inventory. It exposes only source "
            "identity/binding, duration, content hash, and a non-executing adapter "
            "reference. Pilot candidate questions, answers, claims, profiles, "
            "preferred intervals, machine ranks, and sibling-slot hypotheses are "
            "not included in the prescreener packet."
        ),
    }
    validate_task153_inventory(inventory)
    return inventory


def build_source_prescreen(
    output: Path, source: dict[str, Any]
) -> dict[str, Any]:
    source_dir = output / "source_prescreen" / source["source_id"]
    inventory_path = source_dir / "inventory.json"
    inventory = build_inventory(source)
    write_json(inventory_path, inventory)
    plan = build_plan(
        inventory,
        inventory_sha256=task153_sha256_file(inventory_path),
        plan_id=f"task199-{source['source_id']}-task153-plan",
        created_at=CREATED_AT,
        seed=f"AVTRACE-TASK199-{source['source_id']}-SOURCE-PRESCREEN",
        sample_count=6,
        interval_duration_s=20.0,
    )
    form = build_blank_annotation(
        plan, form_id=f"task199-{source['source_id']}-task153-form"
    )
    report, exposure = evaluate_task153(plan, form)
    if report["readiness_token"] != TASK153_REPAIR:
        raise PilotV4PacketError("blank Task153 import did not fail closed")
    if report["completion_status"] != "incomplete" or exposure["events"]:
        raise PilotV4PacketError("blank Task153 packet fabricated review/exposure")
    validate_task153_plan(plan)
    validate_task153_annotation(form)
    validate_task153_exposure(exposure)
    plan_path = source_dir / "task153_plan.json"
    form_path = source_dir / "prescreener_form.json"
    import_path = source_dir / "blank_import.json"
    exposure_path = source_dir / "blank_exposure_ledger.json"
    write_json(plan_path, plan)
    write_json(form_path, form)
    write_json(import_path, report)
    write_json(exposure_path, exposure)
    write_text(
        source_dir / "README.md",
        "# Source-specific Task153 prescreener packet\n\n"
        "This packet is blank and not distributable. The prescreener may receive "
        "only this source binding, the six source-uniform intervals, and the "
        "blank Task153 form. The coordinator registry, all slot directories, "
        "candidate hypotheses, audio candidate meanings, and calibration packets "
        "must remain hidden. Any future exposure is source-group-wide and bars "
        "both blind source-search roles. No identity, observation, eligibility "
        "decision, necessity finding, accepted SES, H tier, release approval, or "
        "Gate A result is present.\n",
    )
    return {
        "source_id": source["source_id"],
        "source_group_id": source["source_group_id"],
        "inventory_path": str(inventory_path.relative_to(output)),
        "inventory_sha256": file_hash(inventory_path),
        "plan_path": str(plan_path.relative_to(output)),
        "plan_id": plan["plan_id"],
        "plan_sha256": plan["plan_sha256"],
        "form_path": str(form_path.relative_to(output)),
        "blank_import_path": str(import_path.relative_to(output)),
        "blank_import_token": report["readiness_token"],
        "blank_exposure_path": str(exposure_path.relative_to(output)),
        "sample_count": len(plan["samples"]),
        "candidate_hypotheses_visible": False,
        "sibling_slot_hypotheses_visible": False,
        "source_level_exposure_required": True,
        "excluded_future_roles": list(BLIND_ROLES),
    }


def candidate_binding_hash(slot: dict[str, Any]) -> str:
    return object_hash(slot)


def author_form(
    slot: dict[str, Any],
    source: dict[str, Any],
    prescreen: dict[str, Any],
) -> dict[str, Any]:
    task194 = slot["reviewer_packet_links"]["task194_candidate_prescreen"]
    audio_required = bool(slot["replacement"]["is_task193_audio_replacement"])
    if audio_required and task194.get("candidate_code") is None:
        raise PilotV4PacketError(
            f"audio replacement lacks Task194 candidate: {slot['slot_id']}"
        )
    claims = [
        {
            "claim_id": f"{slot['slot_id']}.claim-{index:02d}",
            "text": text,
            "human_validated": False,
        }
        for index, text in enumerate(slot["atomic_claims"], start=1)
    ]
    evidence = [
        {
            "evidence_id": item["evidence_id"],
            "interval": copy.deepcopy(item["interval"]),
            "modality": item["modality"],
            "carrier_class": item["carrier_class"],
            "hypothesis": item["hypothesis"],
            "human_semantic_validation_status": "NOT_PERFORMED",
        }
        for item in slot["evidence_hypotheses"]
    ]
    routes = [
        {
            "route_id": f"{slot['slot_id']}.risk-{index:02d}",
            "description": text,
            "status": "OPEN_REQUIRES_HUMAN_REVIEW",
        }
        for index, text in enumerate(slot["alternative_route_risks"], start=1)
    ]
    assignment = {
        "role": "question_claim_author_or_verifier",
        "candidate_matrix_path": str(MATRIX_PATH.relative_to(ROOT)),
        "candidate_matrix_file_sha256": file_hash(MATRIX_PATH),
        "candidate_slot_payload_sha256": candidate_binding_hash(slot),
        "source_content_sha256": f"sha256:{source['source_sha256']}",
        "task153_plan_id": prescreen["plan_id"],
        "task153_plan_sha256": prescreen["plan_sha256"],
        "prescreen_must_be_completed_before_authoring": True,
        "task194_audio_prescreen_required": audio_required,
        "task194_candidate_code": task194.get("candidate_code"),
        "task194_required_order": list(AUDIO_ORDER) if audio_required else [],
        "question_hypothesis": slot["question"],
        "answer_hypothesis": slot["answer_hypothesis"],
        "claim_hypotheses": claims,
        "evidence_hypotheses": evidence,
        "profile_hypothesis": {
            "label": slot["profile"]["label"],
            "status": slot["profile"]["status"],
            "necessity_claimed": False,
        },
        "alternative_route_hypotheses": routes,
        "rights_release_boundary": slot["rights_release_boundary"],
        "source_split_boundary": {
            "development_only": True,
            "future_test_eligible": False,
            "gate_a_eligible": False,
            "fresh_normal_mode_regeneration_required": True,
        },
    }
    form = {
        "schema_version": "1.0.0",
        "record_type": "pilot_v4_author_verifier_form",
        "form_id": f"task199.{slot['slot_id']}.author-verifier",
        "packet_id": PACKET_ID,
        "slot_id": slot["slot_id"],
        "source_id": slot["source_id"],
        "source_group_id": slot["source_group_id"],
        "packet_status": "DRAFT_NOT_DISTRIBUTABLE",
        "distribution_authorized": False,
        "completion_status": "not_started",
        "reviewer": {
            "reviewer_id": None,
            "training_attested": False,
            "started_at": None,
            "completed_at": None,
        },
        "visibility_contract": {
            "candidate_hypotheses_visible": True,
            "only_assigned_slot_hypotheses_visible": True,
            "sibling_source_slot_hypotheses_visible": False,
            "machine_ranks_or_confidence_visible": False,
            "validator_or_adjudication_decisions_visible": False,
            "accepted_ses_visible": False,
            "source_level_blindness_enforced": True,
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
                for item in claims
            ],
            "evidence_checks": [
                {
                    "item_id": item["evidence_id"],
                    "finding": "not_recorded",
                    "notes": "",
                }
                for item in evidence
            ],
            "alternative_route_checks": [
                {
                    "item_id": item["route_id"],
                    "finding": "not_recorded",
                    "notes": "",
                }
                for item in routes
            ],
            "full_source_recurrence_notes": "",
            "ocr_transcript_caption_narration_notes": "",
            "privacy_notes": "",
            "safety_notes": "",
            "rights_release_notes": "",
            "proposed_repairs": [],
            "general_notes": "",
        },
        "source_level_exposure_policy": {
            "exposure_must_be_recorded": True,
            "exposure_scope": "source_group",
            "excluded_future_roles": list(BLIND_ROLES),
        },
        "prohibited_outcomes": {
            "distribution_authorized": False,
            "human_decision_recorded": False,
            "accepted_ses_created": False,
            "necessity_assigned": False,
            "minimality_assigned": False,
            "h1_assigned": False,
            "h2_assigned": False,
            "gate_a_go": False,
            "future_test_eligible": False,
            "public_release_authorized": False,
            "human_gold": False,
        },
    }
    validate_schema_instance(form, AUTHOR_FORM_SCHEMA, "author/verifier form")
    return form


def blank_slot_import(form: dict[str, Any]) -> dict[str, Any]:
    report = {
        "schema_version": "1.0.0",
        "record_type": "pilot_v4_human_packet_import",
        "packet_id": PACKET_ID,
        "scope": "slot",
        "scope_id": form["slot_id"],
        "completion_status": "incomplete",
        "readiness_token": REPAIR,
        "schema_validation_pass": True,
        "binding_validation_pass": True,
        "identity_count": 0,
        "human_review_occurred": False,
        "human_decision_count": 0,
        "distribution_authorized": False,
        "accepted_ses_count": 0,
        "necessity_assigned": False,
        "minimality_assigned": False,
        "h1_assigned": False,
        "h2_assigned": False,
        "gate_a_go": False,
        "errors": ["FORM_NOT_COMPLETED"],
    }
    validate_schema_instance(report, IMPORT_SCHEMA, "blank slot import")
    return report


def copy_audio_prescreen(
    output: Path, slot: dict[str, Any]
) -> dict[str, Any] | None:
    task194 = slot["reviewer_packet_links"]["task194_candidate_prescreen"]
    code = task194.get("candidate_code")
    if code is None:
        return None
    source_dir = TASK194_ROOT / "candidates" / code
    packet = read_json(source_dir / "candidate_packet.json")
    form = read_json(source_dir / "reviewer_form.json")
    report = read_json(source_dir / "blank_import.json")
    validate_schema_instance(packet, TASK194_PACKET_SCHEMA, f"Task194 {code} packet")
    validate_schema_instance(form, TASK194_FORM_SCHEMA, f"Task194 {code} form")
    validate_schema_instance(report, TASK194_IMPORT_SCHEMA, f"Task194 {code} import")
    if tuple(packet["inspection_order"]) != AUDIO_ORDER:
        raise PilotV4PacketError(f"Task194 order mismatch for {code}")
    if tuple(form["inspection_protocol"]["required_order"]) != AUDIO_ORDER:
        raise PilotV4PacketError(f"Task194 form order mismatch for {code}")
    if report["readiness_token"] != "AUDIO_CANDIDATE_PRESCREEN_PACKETS_REPAIR":
        raise PilotV4PacketError(f"Task194 blank import did not fail closed: {code}")
    if packet["scope"]["human_review_performed"] is not False:
        raise PilotV4PacketError(f"Task194 packet contains human review: {code}")
    target = output / "slots" / slot["slot_id"] / "audio_prescreen"
    write_json(target / "candidate_packet.json", packet)
    write_json(target / "reviewer_form.json", form)
    write_json(target / "blank_import.json", report)
    write_text(
        target / "README.md",
        "# Task194 blinded listening prerequisite\n\n"
        "Complete this blind packet before opening the slot's author/verifier "
        "form. The mandatory order is audio-only focal, synchronized A/V focal, "
        "then bounded audio-only recurrence probes. Candidate question, answer, "
        "profile, event identity/count hypothesis, machine labels, and machine "
        "scores are absent. This copied binding remains blank, non-distributable, "
        "and fail-closed to REPAIR.\n",
    )
    return {
        "candidate_code": code,
        "packet_path": str(
            (target / "candidate_packet.json").relative_to(output)
        ),
        "form_path": str((target / "reviewer_form.json").relative_to(output)),
        "blank_import_path": str(
            (target / "blank_import.json").relative_to(output)
        ),
        "inspection_order": list(AUDIO_ORDER),
        "candidate_hypotheses_visible": False,
        "human_review_occurred": False,
        "human_decision_count": 0,
        "blank_import_token": report["readiness_token"],
    }


def build_slot_packet(
    output: Path,
    slot: dict[str, Any],
    source: dict[str, Any],
    prescreen: dict[str, Any],
) -> dict[str, Any]:
    slot_dir = output / "slots" / slot["slot_id"]
    audio_binding = copy_audio_prescreen(output, slot)
    form = author_form(slot, source, prescreen)
    form_path = slot_dir / "author_verifier_form.json"
    import_path = slot_dir / "blank_import.json"
    write_json(form_path, form)
    write_json(import_path, blank_slot_import(form))
    write_text(
        slot_dir / "README.md",
        "# Pilot-v4 author/verifier packet\n\n"
        "This directory is a pre-distribution draft for one assigned slot. The "
        "author/verifier form exposes only this slot's machine-provisional "
        "candidate hypotheses. It does not expose the sibling slot from the same "
        "source, machine ranks/confidence, validator/adjudication decisions, or "
        "accepted SESs. Source-level exposure must be recorded and excludes the "
        "reviewer from both blind source-search roles for this source group. "
        "Task153 must be completed before authoring. If `audio_prescreen/` is "
        "present, its Task194 blind order must be completed before this form is "
        "opened. No distribution, human decision, H tier, or Gate A GO exists.\n",
    )
    return {
        "slot_id": slot["slot_id"],
        "source_id": slot["source_id"],
        "source_group_id": slot["source_group_id"],
        "candidate_slot_payload_sha256": candidate_binding_hash(slot),
        "author_verifier_form_path": str(form_path.relative_to(output)),
        "author_verifier_form_sha256": file_hash(form_path),
        "blank_import_path": str(import_path.relative_to(output)),
        "blank_import_token": REPAIR,
        "task153_plan_id": prescreen["plan_id"],
        "task153_plan_sha256": prescreen["plan_sha256"],
        "audio_prescreen": audio_binding,
        "source_split": "DEVELOPMENT_ONLY",
        "future_test_eligible": False,
        "distribution_authorized": False,
        "human_review_performed": False,
        "human_decision_recorded": False,
        "accepted_ses_count": 0,
        "h1_assigned": False,
        "h2_assigned": False,
        "gate_a_go": False,
    }


def build_calibrations(output: Path) -> list[dict[str, Any]]:
    calibrations = [
        {
            "schema_version": "1.0.0",
            "record_type": "pilot_v4_excluded_calibration_packet",
            "calibration_id": "task199.excluded-calibration.01",
            "packet_status": "DRAFT_NOT_DISTRIBUTABLE",
            "excluded_from_pilot_denominator": True,
            "excluded_from_source_and_slot_counts": True,
            "synthetic_text_only": True,
            "source_id": None,
            "source_group_id": None,
            "reviewer": {
                "reviewer_id": None,
                "training_attested": False,
                "started_at": None,
                "completed_at": None,
            },
            "scenario": (
                "A candidate can be answered from one distinctive object frame, "
                "while the proposed temporal action recurs elsewhere and the "
                "object identity is underspecified."
            ),
            "review_prompts": [
                "Identify the single-frame and recurrence shortcuts.",
                "State what evidence would be needed to repair the wording.",
                "Do not force a family to satisfy a matrix quota.",
            ],
            "response": {
                "completion_status": "not_started",
                "finding": "not_recorded",
                "rationale": "",
                "repair_actions": [],
            },
            "expected_decision_visible": False,
            "not_a_human_decision": True,
            "distribution_authorized": False,
            "accepted_ses_created": False,
            "h1_assigned": False,
            "h2_assigned": False,
            "gate_a_go": False,
        },
        {
            "schema_version": "1.0.0",
            "record_type": "pilot_v4_excluded_calibration_packet",
            "calibration_id": "task199.excluded-calibration.02",
            "packet_status": "DRAFT_NOT_DISTRIBUTABLE",
            "excluded_from_pilot_denominator": True,
            "excluded_from_source_and_slot_counts": True,
            "synthetic_text_only": True,
            "source_id": None,
            "source_group_id": None,
            "reviewer": {
                "reviewer_id": None,
                "training_attested": False,
                "started_at": None,
                "completed_at": None,
            },
            "scenario": (
                "An interval is dominated by intelligible speech while a faint "
                "generic click or hum is audible in the background."
            ),
            "review_prompts": [
                "Apply the Task194 audio-only-before-A/V reasoning order.",
                "Assess speech dominance and transcriptive substitution risk.",
                "Do not count generic background sound as answer-bearing audio.",
            ],
            "response": {
                "completion_status": "not_started",
                "finding": "not_recorded",
                "rationale": "",
                "repair_actions": [],
            },
            "expected_decision_visible": False,
            "not_a_human_decision": True,
            "distribution_authorized": False,
            "accepted_ses_created": False,
            "h1_assigned": False,
            "h2_assigned": False,
            "gate_a_go": False,
        },
    ]
    records = []
    for index, calibration in enumerate(calibrations, start=1):
        validate_schema_instance(
            calibration, CALIBRATION_SCHEMA, f"excluded calibration {index}"
        )
        path = output / "calibrations" / f"excluded_{index:02d}.json"
        write_json(path, calibration)
        records.append(
            {
                "calibration_id": calibration["calibration_id"],
                "path": str(path.relative_to(output)),
                "sha256": file_hash(path),
                "excluded_from_pilot_denominator": True,
                "human_decision_recorded": False,
            }
        )
    return records


def governance_source_groups(
    sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "source_group_id": source["source_group_id"],
            "source_ids": [source["source_id"]],
            "family_ids": sorted(source["candidate_slots"]),
        }
        for source in sorted(sources, key=lambda item: item["source_group_id"])
    ]


def build_governance(
    output: Path, sources: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any]]:
    source_groups = governance_source_groups(sources)
    snapshot = {"captured_at": CREATED_AT, "events": []}
    exposure = {
        "schema_version": "1.0.0",
        "record_type": "construct_validation_source_exposure_ledger",
        "packet_id": PACKET_ID,
        "ledger_status": "OPEN_APPEND_ONLY",
        "source_groups": source_groups,
        "pre_distribution_snapshot": snapshot,
        "pre_distribution_snapshot_sha256": exposure_snapshot_hash(snapshot),
        "review_events": [],
        "notes": (
            "Task199 blank source-level exposure ledger. Before assignment "
            "freeze, bridge every Task153/Task194 prescreener and author/verifier "
            "exposure as external_prior_work. Prescreeners and authors are barred "
            "source-wide from both blind source-search roles. No events exist."
        ),
    }
    assignments = []
    for source in sorted(sources, key=lambda item: item["source_group_id"]):
        for slot_id in sorted(source["candidate_slots"]):
            for role in ROLES:
                assignments.append(
                    {
                        "assignment_id": f"{PACKET_ID}.{slot_id}.{role}",
                        "source_group_id": source["source_group_id"],
                        "family_id": slot_id,
                        "role": role,
                        "reviewer_id": None,
                        "assigned_at": None,
                    }
                )
    assignment = {
        "schema_version": "1.0.0",
        "record_type": "construct_validation_reviewer_assignment_ledger",
        "packet_id": PACKET_ID,
        "generated_at": CREATED_AT,
        "assignment_status": "DRAFT_NOT_DISTRIBUTABLE",
        "frozen_at": None,
        "distribution_authorized": False,
        "pre_distribution_exposure_snapshot_sha256": exposure[
            "pre_distribution_snapshot_sha256"
        ],
        "assignment_freeze_sha256": None,
        "source_groups": source_groups,
        "assignments": assignments,
        "notes": (
            "Blank six-role ledger: 12 slots x 6 roles. All identities and "
            "timestamps are null. Distribution remains unauthorized. Source-level "
            "prescreener and author exposures must be recorded before a later "
            "assignment freeze; no freeze is performed by Task199."
        ),
    }
    validate_source_exposure_ledger(exposure)
    validate_reviewer_assignment_ledger(assignment)
    write_json(output / "coordinator/source_exposure_ledger.json", exposure)
    write_json(output / "coordinator/reviewer_assignments.json", assignment)
    return exposure, assignment


def authoritative_inputs() -> list[dict[str, str]]:
    paths = [
        "orchestration/results/146_construct_validity_source_blindness.txt",
        "orchestration/results/149_cvpr_pivot_v2_addendum.txt",
        "orchestration/results/153_semantic_av_source_prescreen_tooling.txt",
        "orchestration/results/171_epic_dev_authoring_packets.txt",
        "orchestration/results/192_pilot_v3_candidate_integration.txt",
        "orchestration/results/193_semantic_audio_discovery.txt",
        "orchestration/results/194_audio_candidate_prescreen_packets.txt",
        "orchestration/results/195_pilot_v4_candidate_integration.txt",
        "data/rehearsal_plan/pilot_v4_candidate_matrix.json",
        "data/rehearsal_plan/audio_candidate_prescreen_packets_v1/coordinator/packet_manifest.json",
        "data/restricted/epic_family_candidates_v2_dev/candidate_registry.json",
        "data/restricted/captaincook4d_family_candidates_v1_dev/candidate_registry.json",
        "data/restricted/mini_pilot_family_candidates_v2_dev/candidate_registry.json",
        "data/candidates/source_candidates.csv",
    ]
    return [
        {"path": path, "sha256": file_hash(ROOT / path)}
        for path in paths
    ]


def build_registry(
    output: Path,
    matrix: dict[str, Any],
    sources: list[dict[str, Any]],
    prescreens: list[dict[str, Any]],
    slots: list[dict[str, Any]],
    calibrations: list[dict[str, Any]],
) -> dict[str, Any]:
    rights = []
    for source in sources:
        rights.append(
            {
                "source_id": source["source_id"],
                "source_group_id": source["source_group_id"],
                "boundary": copy.deepcopy(source["rights_release_boundary"]),
                "human_annotation_authority_complete": False,
                "public_release_authorized": False,
                "distribution_authorized": False,
            }
        )
    registry = {
        "schema_version": "1.0.0",
        "record_type": "pilot_v4_human_packet_registry",
        "registry_id": PACKET_ID,
        "created_date": CREATED_DATE,
        "artifact_classification": PACKET_CLASS,
        "packet_status": "DRAFT_NOT_DISTRIBUTABLE",
        "distribution_authorized": False,
        "authoritative_inputs": authoritative_inputs(),
        "matrix_binding": {
            "path": str(MATRIX_PATH.relative_to(ROOT)),
            "file_sha256": file_hash(MATRIX_PATH),
            "matrix_id": matrix["matrix_id"],
            "matrix_decision_token": matrix["decision_token"],
        },
        "scope": {
            "source_count": 6,
            "slot_count": 12,
            "slots_per_source": 2,
            "task153_source_packet_count": 6,
            "author_verifier_form_count": 12,
            "task194_audio_slot_count": 4,
            "excluded_calibration_count": 2,
            "null_role_assignment_count": 72,
            "human_identity_count": 0,
            "human_review_count": 0,
            "human_decision_count": 0,
            "accepted_ses_count": 0,
            "h1_count": 0,
            "h2_count": 0,
            "gate_a_go_asserted": False,
        },
        "blindness_contract": {
            "prescreener_candidate_hypotheses_visible": False,
            "prescreener_sibling_slot_hypotheses_visible": False,
            "author_only_assigned_slot_hypotheses_visible": True,
            "author_sibling_slot_hypotheses_visible": False,
            "source_level_exposure_required": True,
            "source_level_blind_role_exclusions": list(BLIND_ROLES),
            "audio_prescreen_hypotheses_visible": False,
            "audio_inspection_order": list(AUDIO_ORDER),
        },
        "source_prescreen_packets": prescreens,
        "slot_packets": slots,
        "excluded_calibration_packets": calibrations,
        "rights_release_boundaries": rights,
        "source_split_boundary": {
            "all_slots_development_only": True,
            "future_test_eligible_count": 0,
            "source_groups_may_not_be_split_across_roles_or_splits": True,
            "parent_development_artifacts_promoted": False,
            "fresh_normal_mode_regeneration_still_required": True,
        },
        "construct_boundary": {
            "necessity_assigned": False,
            "minimality_assigned": False,
            "accepted_ses_count": 0,
            "h1_assigned": False,
            "h2_assigned": False,
            "human_gold": False,
            "gate_a_go": False,
            "scientific_execution_authorized": False,
            "public_release_authorized": False,
        },
        "registry_payload_sha256": "",
    }
    payload = copy.deepcopy(registry)
    payload.pop("registry_payload_sha256")
    registry["registry_payload_sha256"] = object_hash(payload)
    validate_schema_instance(registry, REGISTRY_SCHEMA, "packet registry")
    return registry


def build_blank_coordinator_import() -> dict[str, Any]:
    report = {
        "schema_version": "1.0.0",
        "record_type": "pilot_v4_human_packet_import",
        "packet_id": PACKET_ID,
        "scope": "packet_set",
        "scope_id": PACKET_ID,
        "completion_status": "incomplete",
        "readiness_token": REPAIR,
        "schema_validation_pass": True,
        "binding_validation_pass": True,
        "identity_count": 0,
        "human_review_occurred": False,
        "human_decision_count": 0,
        "distribution_authorized": False,
        "accepted_ses_count": 0,
        "necessity_assigned": False,
        "minimality_assigned": False,
        "h1_assigned": False,
        "h2_assigned": False,
        "gate_a_go": False,
        "errors": [
            "TASK153_HUMAN_PRESCREENS_INCOMPLETE",
            "TASK194_HUMAN_LISTENING_INCOMPLETE",
            "AUTHOR_VERIFIER_FORMS_INCOMPLETE",
            "REVIEWER_IDENTITIES_AND_ASSIGNMENTS_ABSENT",
            "ASSIGNMENTS_NOT_FROZEN",
            "DISTRIBUTION_NOT_AUTHORIZED",
            "RIGHTS_ANNOTATION_RELEASE_HOLDS_OPEN",
            "GATE_A_REMAINS_REPAIR",
        ],
    }
    validate_schema_instance(report, IMPORT_SCHEMA, "blank coordinator import")
    return report


def manifest_files(output: Path) -> list[dict[str, Any]]:
    records = []
    for path in sorted(output.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(output)
        if relative.as_posix() == "coordinator/packet_manifest.json":
            continue
        records.append(
            {
                "path": relative.as_posix(),
                "bytes": path.stat().st_size,
                "sha256": file_hash(path),
                "mode": f"{path.stat().st_mode & 0o777:04o}",
            }
        )
    return records


def build_manifest(output: Path, registry: dict[str, Any]) -> dict[str, Any]:
    manifest = {
        "schema_version": "1.0.0",
        "record_type": "pilot_v4_human_packet_manifest",
        "packet_id": PACKET_ID,
        "generated_at": CREATED_AT,
        "packet_status": "DRAFT_NOT_DISTRIBUTABLE",
        "distribution_authorized": False,
        "preparation_readiness_token": READY,
        "blank_human_import_token": REPAIR,
        "registry_path": "coordinator/packet_registry.json",
        "registry_payload_sha256": registry["registry_payload_sha256"],
        "source_count": 6,
        "slot_count": 12,
        "audio_slot_count": 4,
        "excluded_calibration_count": 2,
        "identity_count": 0,
        "human_decision_count": 0,
        "accepted_ses_count": 0,
        "h_tier_count": 0,
        "gate_a_go_asserted": False,
        "files": manifest_files(output),
        "manifest_sha256": "",
    }
    payload = copy.deepcopy(manifest)
    payload.pop("manifest_sha256")
    manifest["manifest_sha256"] = object_hash(payload)
    return manifest


def validate_author_form(form: dict[str, Any], slot: dict[str, Any]) -> None:
    validate_schema_instance(form, AUTHOR_FORM_SCHEMA, "author/verifier form")
    if form["immutable_assignment_sha256"] != object_hash(
        form["immutable_assignment"]
    ):
        raise PilotV4PacketError("author/verifier immutable assignment hash mismatch")
    if (
        form["immutable_assignment"]["candidate_slot_payload_sha256"]
        != candidate_binding_hash(slot)
    ):
        raise PilotV4PacketError("author/verifier candidate binding mismatch")
    if form["completion_status"] != "not_started":
        raise PilotV4PacketError("checked-in author/verifier form is completed")
    if any(value is not None for key, value in form["reviewer"].items() if key != "training_attested"):
        raise PilotV4PacketError("checked-in author/verifier form contains identity/time")
    if form["reviewer"]["training_attested"] is not False:
        raise PilotV4PacketError("checked-in author/verifier form contains training")


def verify_packet(output: Path) -> dict[str, Any]:
    matrix = read_json(MATRIX_PATH)
    validate_matrix(matrix)
    registry = read_json(output / "coordinator/packet_registry.json")
    validate_schema_instance(registry, REGISTRY_SCHEMA, "packet registry")
    copied = copy.deepcopy(registry)
    stored_registry_hash = copied.pop("registry_payload_sha256")
    if stored_registry_hash != object_hash(copied):
        raise PilotV4PacketError("registry payload hash mismatch")
    if registry["matrix_binding"]["file_sha256"] != file_hash(MATRIX_PATH):
        raise PilotV4PacketError("candidate matrix file binding mismatch")
    slots_by_id = {slot["slot_id"]: slot for slot in matrix["candidate_slots"]}
    if len(registry["slot_packets"]) != 12:
        raise PilotV4PacketError("registry does not contain twelve slots")
    for record in registry["slot_packets"]:
        form = read_json(output / record["author_verifier_form_path"])
        validate_author_form(form, slots_by_id[record["slot_id"]])
        report = read_json(output / record["blank_import_path"])
        validate_schema_instance(report, IMPORT_SCHEMA, "slot blank import")
        if report["readiness_token"] != REPAIR:
            raise PilotV4PacketError("blank slot import did not fail closed")
        audio = record["audio_prescreen"]
        expected_audio = slots_by_id[record["slot_id"]]["replacement"][
            "is_task193_audio_replacement"
        ]
        if expected_audio != (audio is not None):
            raise PilotV4PacketError("audio slot binding mismatch")
        if audio is not None:
            packet = read_json(output / audio["packet_path"])
            task194_form = read_json(output / audio["form_path"])
            task194_import = read_json(output / audio["blank_import_path"])
            validate_schema_instance(packet, TASK194_PACKET_SCHEMA, "Task194 packet")
            validate_schema_instance(task194_form, TASK194_FORM_SCHEMA, "Task194 form")
            validate_schema_instance(
                task194_import, TASK194_IMPORT_SCHEMA, "Task194 import"
            )
            if tuple(packet["inspection_order"]) != AUDIO_ORDER:
                raise PilotV4PacketError("audio packet order changed")
            if (
                task194_import["readiness_token"]
                != "AUDIO_CANDIDATE_PRESCREEN_PACKETS_REPAIR"
            ):
                raise PilotV4PacketError("audio blank import did not fail closed")
    if len(registry["source_prescreen_packets"]) != 6:
        raise PilotV4PacketError("registry does not contain six source prescreens")
    for record in registry["source_prescreen_packets"]:
        inventory = read_json(output / record["inventory_path"])
        plan = read_json(output / record["plan_path"])
        form = read_json(output / record["form_path"])
        report = read_json(output / record["blank_import_path"])
        exposure = read_json(output / record["blank_exposure_path"])
        validate_task153_inventory(inventory)
        validate_task153_plan(plan)
        validate_task153_annotation(form)
        validate_task153_exposure(exposure)
        regenerated, regenerated_exposure = evaluate_task153(plan, form)
        if regenerated != report or regenerated_exposure != exposure:
            raise PilotV4PacketError("Task153 checked-in blank import mismatch")
        if report["readiness_token"] != TASK153_REPAIR:
            raise PilotV4PacketError("Task153 blank import did not fail closed")
    for record in registry["excluded_calibration_packets"]:
        calibration = read_json(output / record["path"])
        validate_schema_instance(
            calibration, CALIBRATION_SCHEMA, "excluded calibration"
        )
    exposure = read_json(output / "coordinator/source_exposure_ledger.json")
    assignments = read_json(output / "coordinator/reviewer_assignments.json")
    validate_source_exposure_ledger(exposure)
    validate_reviewer_assignment_ledger(assignments)
    if len(assignments["assignments"]) != 72:
        raise PilotV4PacketError("null assignment ledger must contain 72 rows")
    if any(
        item["reviewer_id"] is not None or item["assigned_at"] is not None
        for item in assignments["assignments"]
    ):
        raise PilotV4PacketError("assignment ledger contains identities/assignments")
    if assignments["distribution_authorized"] is not False:
        raise PilotV4PacketError("assignment ledger authorizes distribution")
    if exposure["pre_distribution_snapshot"]["events"] or exposure["review_events"]:
        raise PilotV4PacketError("source exposure ledger contains events")
    coordinator_import = read_json(output / "coordinator/blank_import_report.json")
    validate_schema_instance(
        coordinator_import, IMPORT_SCHEMA, "coordinator blank import"
    )
    if coordinator_import["readiness_token"] != REPAIR:
        raise PilotV4PacketError("coordinator import did not fail closed")
    manifest = read_json(output / "coordinator/packet_manifest.json")
    stored_manifest_hash = manifest["manifest_sha256"]
    payload = copy.deepcopy(manifest)
    payload.pop("manifest_sha256")
    if stored_manifest_hash != object_hash(payload):
        raise PilotV4PacketError("manifest hash mismatch")
    actual_files = manifest_files(output)
    if actual_files != manifest["files"]:
        raise PilotV4PacketError("manifest file inventory mismatch")
    for path in output.rglob("*"):
        mode = path.stat().st_mode & 0o777
        expected = 0o700 if path.is_dir() else 0o600
        if mode != expected:
            raise PilotV4PacketError(
                f"permission mismatch {path.relative_to(output)}: {mode:04o}"
            )
    return {
        "readiness_token": READY,
        "source_count": 6,
        "slot_count": 12,
        "audio_slot_count": 4,
        "excluded_calibration_count": 2,
        "assignment_count": 72,
        "identity_count": 0,
        "human_decision_count": 0,
        "accepted_ses_count": 0,
        "h_tier_count": 0,
        "distribution_authorized": False,
        "gate_a_go_asserted": False,
        "blank_import_token": REPAIR,
    }


def build(output: Path) -> dict[str, Any]:
    matrix = read_json(MATRIX_PATH)
    validate_matrix(matrix)
    sources = source_records(matrix)
    slots_by_source = {
        source["source_id"]: [
            slot
            for slot in matrix["candidate_slots"]
            if slot["source_id"] == source["source_id"]
        ]
        for source in sources
    }
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, mode=0o700)
    prescreens = [
        build_source_prescreen(output, source)
        for source in sorted(sources, key=lambda item: item["source_id"])
    ]
    prescreen_by_source = {item["source_id"]: item for item in prescreens}
    source_by_id = {item["source_id"]: item for item in sources}
    slot_records = []
    for source_id in sorted(slots_by_source):
        for slot in sorted(
            slots_by_source[source_id], key=lambda item: item["slot_id"]
        ):
            slot_records.append(
                build_slot_packet(
                    output,
                    slot,
                    source_by_id[source_id],
                    prescreen_by_source[source_id],
                )
            )
    calibrations = build_calibrations(output)
    build_governance(output, sources)
    registry = build_registry(
        output, matrix, sources, prescreens, slot_records, calibrations
    )
    write_json(output / "coordinator/packet_registry.json", registry)
    write_json(
        output / "coordinator/blank_import_report.json",
        build_blank_coordinator_import(),
    )
    write_text(
        output / "README.md",
        "# Unified pilot-v4 pre-distribution human packets\n\n"
        "Task199 preparation artifact for 12 slots across six source groups. "
        "Nothing here is authorized for distribution. Prescreener directories "
        "are semantically firewalled from candidate hypotheses. Each author/"
        "verifier receives only one slot and not its same-source sibling. Four "
        "audio-bearing slots carry Task194's mandatory audio-only, synchronized "
        "A/V, recurrence-probe order. Two synthetic calibration packets are "
        "excluded from all pilot source/slot denominators. Coordinator ledgers "
        "contain 72 null six-role assignments and zero exposure events. Blank "
        "human imports fail closed to PILOT_V4_HUMAN_PACKETS_REPAIR. Packet "
        "preparation readiness does not assert Gate A GO, rights/release "
        "clearance, a human decision, accepted SES, necessity, or an H tier.\n",
    )
    secure_tree(output)
    manifest = build_manifest(output, registry)
    write_json(output / "coordinator/packet_manifest.json", manifest)
    secure_tree(output)
    return verify_packet(output)


def tamper_self_tests(output: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="pilot-v4-task199-") as temporary:
        temp_root = Path(temporary) / "packet"
        shutil.copytree(output, temp_root)
        form_path = (
            temp_root
            / "slots/PV4-P27-01/author_verifier_form.json"
        )
        form = read_json(form_path)
        form["reviewer"]["reviewer_id"] = "invented-reviewer"
        write_json(form_path, form)
        secure_tree(temp_root)
        try:
            verify_packet(temp_root)
        except PilotV4PacketError:
            pass
        else:
            raise PilotV4PacketError("identity injection did not fail closed")
    with tempfile.TemporaryDirectory(prefix="pilot-v4-task199-") as temporary:
        temp_root = Path(temporary) / "packet"
        shutil.copytree(output, temp_root)
        audio_path = (
            temp_root
            / "slots/PV4-CC15-01/audio_prescreen/candidate_packet.json"
        )
        audio = read_json(audio_path)
        audio["inspection_order"] = [
            "synchronized_av_focal",
            "audio_only_focal",
            "audio_only_recurrence_probes",
        ]
        write_json(audio_path, audio)
        secure_tree(temp_root)
        try:
            verify_packet(temp_root)
        except PilotV4PacketError:
            pass
        else:
            raise PilotV4PacketError("Task194 order tamper did not fail closed")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = verify_packet(args.output_dir) if args.verify_only else build(
            args.output_dir
        )
        if args.self_test:
            tamper_self_tests(args.output_dir)
    except (PilotV4PacketError, ValueError, OSError) as exc:
        print(f"{NO_GO}: {exc}")
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    print(READY)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
