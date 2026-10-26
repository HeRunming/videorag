#!/usr/bin/env python3
"""Build the fail-closed P23_102 MACHINE-PROVISIONAL bundle.

This tool consumes only the repaired machine candidate registry and the
already-built verified timeline index.  It does not open media, load models,
use a network, or consult semantic annotation files.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

READY = "P23_102_MACHINE_PROVISIONAL_BUNDLE_READY"
REPAIR = "P23_102_MACHINE_PROVISIONAL_BUNDLE_REPAIR"
CREATED_DATE = "2026-10-14"
SOURCE_ID = "P23_102"
SOURCE_GROUP_ID = "P23"

REGISTRY_PATH = Path(
    "data/restricted/epic_p23_102_family_mining_v1_dev/"
    "candidate_registry.json"
)
INDEX_ROOT = Path(
    "data/restricted/epic_p23_102_full_timeline_index_v1"
)
OUTPUT_ROOT = Path(
    "data/restricted/epic_p23_102_machine_provisional_families_v1"
)
PROTOCOL_PATH = Path(
    "data/rehearsal_plan/exogenous_restoration_protocol_v2.json"
)
REHEARSAL_PATH = Path(
    "data/rehearsal_plan/p23_102_acquire_ground_act_rehearsal_v1.json"
)

OUTPUT_NAMES = (
    "family_registry.json",
    "evidence_registry.json",
    "intervention_manifest.json",
    "state_surface_manifest.json",
    "source_split_manifest.json",
    "leakage_gate.json",
)
INDEX_FILES = (
    "segment_manifest.json",
    "observation_manifest.json",
    "full_timeline_index.json",
    "resource_manifest.json",
    "checkpoint_manifest.json",
    "build_manifest.json",
)
ARMS = ("C", "B", "R", "N")
MECHANISMS = (
    "SILENT_ROUTE_WITHHOLDING",
    "EXPLICIT_CHANNEL_OUTAGE",
)
CHECKPOINT_EVENT = {
    "event_type": "protocol_checkpoint",
    "event_version": "2.0.0",
    "message": "Scheduled protocol checkpoint completed.",
    "cost": 0.0,
}
REQUIRED_EVIDENCE_PHRASE = (
    "all accepted SESs discovered under the frozen saturation protocol"
)


class BundleError(RuntimeError):
    """Fail-closed bundle construction or validation error."""


def repo_root_default() -> Path:
    return Path(__file__).resolve().parents[1]


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def object_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _without(value: Mapping[str, Any], field: str) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key != field}


def seal(value: dict[str, Any]) -> dict[str, Any]:
    value["payload_sha256"] = object_hash(value)
    return value


def verify_seal(value: Mapping[str, Any], *, label: str) -> None:
    expected = object_hash(_without(value, "payload_sha256"))
    if value.get("payload_sha256") != expected:
        raise BundleError(f"{label}_PAYLOAD_HASH_MISMATCH")


def _verify_foreign_self_hash(
    value: Mapping[str, Any],
    *,
    field: str,
    label: str,
) -> None:
    expected = object_hash(_without(value, field))
    if value.get(field) != expected:
        raise BundleError(f"{label}_HASH_MISMATCH")


def _safe_path(root: Path, value: str | Path, *, label: str) -> Path:
    raw = Path(value)
    if raw.is_absolute():
        path = raw
    else:
        pure = PurePosixPath(str(raw))
        if ".." in pure.parts or ".staging" in pure.parts:
            raise BundleError(f"{label}_UNSAFE:{value}")
        path = root.joinpath(*pure.parts)
    try:
        path.resolve(strict=False).relative_to(root.resolve())
    except ValueError as exc:
        raise BundleError(f"{label}_OUTSIDE_REPOSITORY:{value}") from exc
    if path.is_symlink() or ".staging" in path.parts:
        raise BundleError(f"{label}_UNSAFE:{value}")
    return path


def _relative(root: Path, path: Path) -> str:
    return path.resolve(strict=False).relative_to(root.resolve()).as_posix()


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(canonical_bytes(value))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _stable_id(prefix: str, *parts: str) -> str:
    payload = "\x1f".join(parts).encode("utf-8")
    suffix = hashlib.sha256(payload).hexdigest()[:20]
    return f"{prefix}.{suffix}"


def _seconds(value_us: int) -> float:
    return round(value_us / 1_000_000.0, 6)


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise BundleError(code)


def load_inputs(
    repo_root: Path,
    *,
    registry_path: Path = REGISTRY_PATH,
    index_root: Path = INDEX_ROOT,
    protocol_path: Path = PROTOCOL_PATH,
    rehearsal_path: Path = REHEARSAL_PATH,
) -> dict[str, Any]:
    """Load and cryptographically bind only the authorized inputs."""
    registry_file = _safe_path(
        repo_root, registry_path, label="REGISTRY_PATH"
    )
    index_dir = _safe_path(repo_root, index_root, label="INDEX_ROOT")
    protocol_file = _safe_path(
        repo_root, protocol_path, label="PROTOCOL_PATH"
    )
    rehearsal_file = _safe_path(
        repo_root, rehearsal_path, label="REHEARSAL_PATH"
    )
    required = [registry_file, protocol_file, rehearsal_file]
    required.extend(index_dir / name for name in INDEX_FILES)
    for path in required:
        if not path.is_file():
            raise BundleError(f"REQUIRED_INPUT_MISSING:{_relative(repo_root, path)}")

    inputs = {
        "registry": _load_json(registry_file),
        "segment_manifest": _load_json(index_dir / "segment_manifest.json"),
        "observation_manifest": _load_json(
            index_dir / "observation_manifest.json"
        ),
        "index": _load_json(index_dir / "full_timeline_index.json"),
        "resource_manifest": _load_json(
            index_dir / "resource_manifest.json"
        ),
        "checkpoint_manifest": _load_json(
            index_dir / "checkpoint_manifest.json"
        ),
        "build_manifest": _load_json(index_dir / "build_manifest.json"),
        "protocol": _load_json(protocol_file),
        "rehearsal": _load_json(rehearsal_file),
        "input_files": {
            _relative(repo_root, path): file_hash(path) for path in required
        },
    }
    validate_inputs(inputs)
    return inputs


def _index_documents(
    index: Mapping[str, Any],
) -> dict[str, dict[str, Mapping[str, Any]]]:
    modalities = index["modalities"]
    return {
        "vision": {
            str(row["segment_id"]): row
            for row in modalities["siglip2_visual"]["documents"]
        },
        "ambient_audio": {
            str(row["segment_id"]): row
            for row in modalities["clap_audio"]["documents"]
        },
        "speech": {
            str(row["chunk_id"]): row
            for row in modalities["speech"]["documents"]
        },
    }


def validate_inputs(inputs: Mapping[str, Any]) -> None:
    """Reject any source that weakens the machine-provisional boundary."""
    registry = inputs["registry"]
    index = inputs["index"]
    segment_manifest = inputs["segment_manifest"]
    observation_manifest = inputs["observation_manifest"]
    build_manifest = inputs["build_manifest"]

    _require(
        registry.get("decision")
        == "EPIC_P23_102_FAMILY_MINING_MACHINE_PROVISIONAL_COMPLETE",
        "SOURCE_REGISTRY_DECISION_INVALID",
    )
    _require(
        registry.get("repair_completion_token")
        == "EPIC_P23_102_FAMILY_MINING_REPAIR_READY",
        "SOURCE_REGISTRY_REPAIR_TOKEN_INVALID",
    )
    _require(
        registry.get("artifact_classification")
        == "DEVELOPMENT_ONLY_MACHINE_EXPERT_PROVISIONAL",
        "SOURCE_REGISTRY_CLASSIFICATION_INVALID",
    )
    _require(registry.get("source_id") == SOURCE_ID, "SOURCE_ID_INVALID")
    _require(
        registry.get("source_group_id") == SOURCE_GROUP_ID,
        "SOURCE_GROUP_ID_INVALID",
    )
    _verify_foreign_self_hash(
        registry,
        field="registry_payload_sha256",
        label="SOURCE_REGISTRY",
    )

    boundary = registry.get("acceptance_boundary", {})
    summary = registry.get("summary", {})
    prescreen = registry.get("source_uniform_human_prescreen_gate", {})
    _require(
        boundary.get("accepted_families") == []
        and boundary.get("accepted_ses") == []
        and boundary.get("h_tiers") == []
        and boundary.get("gate_a_asserted") is False
        and boundary.get("future_test_eligible") is False,
        "SOURCE_ACCEPTANCE_BOUNDARY_INVALID",
    )
    _require(
        summary.get("accepted_family_count") == 0
        and summary.get("accepted_ses_count") == 0
        and summary.get("h_tier_count") == 0
        and summary.get("gate_a_credit_count") == 0,
        "SOURCE_ACCEPTED_COUNTS_NONZERO",
    )
    _require(
        prescreen.get("status") == "NOT_PROVIDED"
        and prescreen.get("protocol_scope")
        == "SOURCE_UNIFORM_ALL_MACHINE_LEADS",
        "SOURCE_UNIFORM_PRESCREEN_BOUNDARY_INVALID",
    )

    _require(
        index.get("source_ref") == SOURCE_ID,
        "VERIFIED_INDEX_SOURCE_INVALID",
    )
    _require(
        index.get("index_hash")
        == registry["index_bindings"]["index_hash"],
        "VERIFIED_INDEX_HASH_BINDING_INVALID",
    )
    _require(
        index.get("segment_manifest_hash")
        == registry["index_bindings"]["segment_manifest_hash"],
        "SEGMENT_MANIFEST_BINDING_INVALID",
    )
    _require(
        index.get("observation_manifest_hash")
        == registry["index_bindings"]["observation_manifest_hash"],
        "OBSERVATION_MANIFEST_BINDING_INVALID",
    )
    _require(
        build_manifest.get("build_manifest_hash")
        == registry["index_bindings"]["build_manifest_hash"],
        "BUILD_MANIFEST_BINDING_INVALID",
    )
    _require(
        segment_manifest.get("segment_manifest_hash")
        == index.get("segment_manifest_hash"),
        "SEGMENT_MANIFEST_INTERNAL_HASH_INVALID",
    )
    _require(
        observation_manifest.get("observation_manifest_hash")
        == index.get("observation_manifest_hash"),
        "OBSERVATION_MANIFEST_INTERNAL_HASH_INVALID",
    )
    for governance in (
        index.get("governance", {}),
        segment_manifest.get("governance", {}),
        observation_manifest.get("governance", {}),
        build_manifest.get("governance", {}),
    ):
        _require(
            governance.get("development_only") is True
            and governance.get("future_test_eligible") is False
            and governance.get("human_review_performed") is False
            and governance.get("semantic_annotations_opened_by_this_pipeline")
            is False
            and governance.get(
                "semantic_annotations_used_during_source_selection"
            )
            is False
            and governance.get("ses_assigned") is False
            and governance.get("h_tier_assigned") is False
            and governance.get("gate_a_claimed") is False,
            "VERIFIED_INDEX_GOVERNANCE_INVALID",
        )

    expected_input_hashes = {
        row["path"]: row["sha256"] for row in registry["input_bindings"]
    }
    for path, expected in expected_input_hashes.items():
        actual = inputs["input_files"].get(path)
        _require(actual == expected, f"PINNED_INPUT_HASH_MISMATCH:{path}")

    rehearsal = inputs["rehearsal"]
    restoration = rehearsal.get("restoration_v2", {})
    _require(
        restoration.get("fixed_action_index") == 4
        and restoration.get("index_base") == "zero"
        and restoration.get("checkpoint_event") == CHECKPOINT_EVENT,
        "REHEARSAL_RESTORATION_V2_INVALID",
    )
    protocol = inputs["protocol"]
    _require(
        {row.get("mechanism") for row in protocol.get("mechanisms", [])}
        == set(MECHANISMS),
        "RESTORATION_PROTOCOL_MECHANISMS_INVALID",
    )
    protocol_schedule = protocol.get("primary_schedule", {})
    protocol_event = copy.deepcopy(protocol_schedule.get("event", {}))
    protocol_event.pop("public_bytes_identical_r_n", None)
    protocol_event.pop("reveals_restoration", None)
    _require(
        protocol_schedule.get("action_index") == 4
        and protocol_schedule.get("index_base") == "zero"
        and protocol_event == CHECKPOINT_EVENT,
        "RESTORATION_PROTOCOL_SCHEDULE_INVALID",
    )

    documents = _index_documents(index)
    duration_us = int(segment_manifest["duration_us"])
    candidates = registry.get("candidates")
    _require(isinstance(candidates, list) and candidates, "NO_CANDIDATES")
    _require(
        [row.get("rank") for row in candidates]
        == list(range(1, len(candidates) + 1)),
        "CANDIDATE_RANKS_INVALID",
    )
    candidate_ids: set[str] = set()
    evidence_ids: set[str] = set()
    for candidate in candidates:
        _verify_foreign_self_hash(
            candidate,
            field="candidate_payload_sha256",
            label="CANDIDATE",
        )
        candidate_id = str(candidate.get("candidate_id"))
        _require(candidate_id not in candidate_ids, "DUPLICATE_CANDIDATE_ID")
        candidate_ids.add(candidate_id)
        _require(
            candidate.get("machine_provisional_status") == "REPAIR",
            "CANDIDATE_STATUS_NOT_REPAIR",
        )
        _require(
            candidate.get("profile_hypothesis") == "V+A"
            and candidate.get("profile_status")
            == "HYPOTHESIS_NOT_MODALITY_NECESSITY",
            "CANDIDATE_PROFILE_NOT_PROVISIONAL_VA",
        )
        _require(
            candidate.get("accepted_family") is False
            and candidate.get("accepted_ses") is False
            and candidate.get("h_tier") is None
            and candidate.get("gate_a_credit") is False
            and candidate.get("human_prescreen") == "NOT_PERFORMED",
            "CANDIDATE_ACCEPTANCE_BOUNDARY_INVALID",
        )
        _require(
            bool(candidate.get("question_template"))
            and bool(candidate.get("answer_template"))
            and bool(candidate.get("atomic_claim_templates"))
            and bool(candidate.get("substitution_risks")),
            "CANDIDATE_TEMPLATES_OR_RISKS_MISSING",
        )
        recurrence = candidate.get("recurrence_checks", {})
        firewall = candidate.get("semantic_annotation_firewall", {})
        _require(
            recurrence.get("human_full_source_recurrence_review_required")
            is True
            and recurrence.get("machine_recurrence_is_not_adjudication")
            is True,
            "CANDIDATE_RECURRENCE_BOUNDARY_INVALID",
        )
        _require(
            firewall.get("epic_semantic_labels_accessed") is False
            and firewall.get("human_labels_used_for_generation_or_ranking")
            is False
            and firewall.get("retrieval_observations_are_not_gold") is True,
            "CANDIDATE_SEMANTIC_FIREWALL_INVALID",
        )
        temporal = candidate.get("temporal_structure", {})
        if candidate.get("candidate_kind") == "coherent_far_multi_hop":
            _require(
                temporal.get("temporal_hypothesis") == "far_separated"
                and temporal.get("hop_hypothesis") == "multi_hop"
                and float(
                    temporal.get("evidence_center_separation_seconds", 0)
                )
                >= 120.0
                and temporal.get("far_coherence", {}).get(
                    "distance_alone_is_not_credited"
                )
                is True,
                "FAR_LEAD_STRUCTURE_INVALID",
            )
        elif candidate.get("candidate_kind") == "near_local":
            _require(
                temporal.get("temporal_hypothesis") == "near_local"
                and temporal.get("hop_hypothesis") == "one_hop",
                "LOCAL_LEAD_STRUCTURE_INVALID",
            )
        else:
            raise BundleError("UNKNOWN_CANDIDATE_KIND")

        seen_modalities: set[str] = set()
        handles = candidate.get("evidence_handles")
        _require(isinstance(handles, list) and handles, "EVIDENCE_MISSING")
        for handle in handles:
            handle_id = str(handle.get("evidence_handle_id"))
            _require(handle_id not in evidence_ids, "DUPLICATE_EVIDENCE_ID")
            evidence_ids.add(handle_id)
            modality = str(handle.get("modality"))
            seen_modalities.add(modality)
            _require(
                modality in {"vision", "ambient_audio"},
                "V_A_HANDLE_MODALITY_INVALID",
            )
            record = documents[modality].get(str(handle.get("record_id")))
            _require(record is not None, "UNKNOWN_EXACT_INDEX_HANDLE")
            start_us = handle.get("start_us")
            end_us = handle.get("end_us")
            _require(
                isinstance(start_us, int)
                and isinstance(end_us, int)
                and 0 <= start_us < end_us <= duration_us,
                "EVIDENCE_TEMPORAL_RANGE_INVALID",
            )
            _require(
                int(record["start_us"]) == start_us
                and int(record["end_us"]) == end_us
                and bool(record.get("searchable")) is True,
                "EXACT_INDEX_HANDLE_MISMATCH",
            )
            _require(
                handle.get("start_seconds") == _seconds(start_us)
                and handle.get("end_seconds") == _seconds(end_us)
                and handle.get("source_id") == SOURCE_ID
                and handle.get("source_sha256")
                == registry.get("source_sha256")
                and handle.get("human_semantic_validation")
                == "NOT_PERFORMED",
                "EVIDENCE_HANDLE_METADATA_INVALID",
            )
        _require(
            seen_modalities == {"vision", "ambient_audio"},
            "V_A_MODALITY_SET_INVALID",
        )

    accounting = registry.get("profile_accounting", {})
    _require(
        accounting.get("V+A", {}).get("machine_lead_count")
        == len(candidates)
        and accounting.get("V+A", {}).get("validated_or_accepted") == 0,
        "VA_ACCOUNTING_INVALID",
    )
    for profile in ("V+S", "V+S+A"):
        row = accounting.get(profile, {})
        _require(
            row.get("machine_lead_count") == 0
            and row.get("validated_or_accepted") == 0
            and row.get("honest_zero") is True
            and bool(row.get("zero_reason")),
            f"{profile}_HONEST_ZERO_INVALID",
        )


def _input_bindings(inputs: Mapping[str, Any]) -> list[dict[str, str]]:
    return [
        {"path": path, "sha256": digest}
        for path, digest in sorted(inputs["input_files"].items())
    ]


def _base_metadata(inputs: Mapping[str, Any]) -> dict[str, Any]:
    registry = inputs["registry"]
    return {
        "created_date": CREATED_DATE,
        "artifact_classification": (
            "DEVELOPMENT_ONLY_MACHINE_PROVISIONAL_NOT_HUMAN_VALIDATED"
        ),
        "source_id": SOURCE_ID,
        "source_group_id": SOURCE_GROUP_ID,
        "source_sha256": registry["source_sha256"],
        "input_bindings": _input_bindings(inputs),
        "index_bindings": copy.deepcopy(registry["index_bindings"]),
    }


def _family_and_evidence(
    inputs: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    registry = inputs["registry"]
    families: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    routes: list[dict[str, Any]] = []

    for candidate in registry["candidates"]:
        candidate_id = candidate["candidate_id"]
        family_id = _stable_id("mpf", candidate_id)
        route_group_id = _stable_id("mpr", candidate_id, "route")
        claim_templates = []
        for claim in candidate["atomic_claim_templates"]:
            claim_templates.append(
                {
                    "claim_id": claim["claim_id"],
                    "public_claim_handle": _stable_id(
                        "mpc", candidate_id, claim["claim_id"]
                    ),
                    "status": claim["status"],
                    "template": claim["template"],
                    "answer_semantics": (
                        "PROVISIONAL_TEMPLATE_NOT_HUMAN_VALIDATED"
                    ),
                    "support_semantics": (
                        "PROVISIONAL_ROUTE_HYPOTHESIS_NOT_ACCEPTED_SES"
                    ),
                    "necessity_semantics": (
                        "NOT_ESTABLISHED_AND_NOT_HUMAN_VALIDATED"
                    ),
                }
            )
        evidence_ids = [
            row["evidence_handle_id"] for row in candidate["evidence_handles"]
        ]
        families.append(
            {
                "family_id": family_id,
                "source_candidate_id": candidate_id,
                "source_candidate_payload_sha256": candidate[
                    "candidate_payload_sha256"
                ],
                "rank": candidate["rank"],
                "machine_provisional_status": "REPAIR",
                "accepted_family": False,
                "accepted_ses": False,
                "h_tier": None,
                "gate_a_credit": False,
                "human_prescreen": "NOT_PERFORMED",
                "source_uniform_human_prescreen_required": True,
                "profile_hypothesis": candidate["profile_hypothesis"],
                "profile_status": candidate["profile_status"],
                "modality_work_hypotheses": copy.deepcopy(
                    candidate["modality_work_hypotheses"]
                ),
                "candidate_kind": candidate["candidate_kind"],
                "temporal_structure": copy.deepcopy(
                    candidate["temporal_structure"]
                ),
                "question_template": candidate["question_template"],
                "answer_template": candidate["answer_template"],
                "atomic_claim_templates": claim_templates,
                "route_group_id": route_group_id,
                "evidence_handle_ids": evidence_ids,
                "alternative_evidence_routes": copy.deepcopy(
                    candidate["alternative_evidence_routes"]
                ),
                "recurrence_checks": copy.deepcopy(
                    candidate["recurrence_checks"]
                ),
                "substitution_risks": copy.deepcopy(
                    candidate["substitution_risks"]
                ),
                "structural_scores": copy.deepcopy(
                    candidate["structural_scores"]
                ),
                "status_rationale": candidate["status_rationale"],
                "semantic_annotation_firewall": copy.deepcopy(
                    candidate["semantic_annotation_firewall"]
                ),
                "answer_support_and_necessity_boundary": {
                    "answer_is_provisional_template_only": True,
                    "support_is_machine_route_hypothesis_only": True,
                    "necessity_is_not_established": True,
                    "human_validated": False,
                    "accepted_ses": False,
                },
            }
        )
        for handle in candidate["evidence_handles"]:
            evidence.append(
                {
                    **copy.deepcopy(handle),
                    "family_id": family_id,
                    "route_group_id": route_group_id,
                    "source_candidate_id": candidate_id,
                    "exact_index_binding_verified": True,
                    "citable_only_after_public_observation_acquisition": True,
                    "semantic_content_asserted": False,
                    "human_validated": False,
                }
            )
        routes.append(
            {
                "route_group_id": route_group_id,
                "family_id": family_id,
                "source_candidate_id": candidate_id,
                "machine_provisional_status": "REPAIR",
                "evidence_handle_ids": evidence_ids,
                "record_ids": sorted(
                    {
                        row["record_id"]
                        for row in candidate["evidence_handles"]
                    }
                ),
                "modalities": ["ambient_audio", "vision"],
                "profile_hypothesis": "V+A",
                "support_semantics": (
                    "MACHINE_PROVISIONAL_NOT_ACCEPTED_SES"
                ),
                "route_completeness_semantics": (
                    "PROVISIONAL_FOR_DEVELOPMENT_SURFACE_CONSTRUCTION_ONLY"
                ),
                "answer_validated": False,
                "support_validated": False,
                "necessity_validated": False,
                "human_validated": False,
            }
        )

    family_registry = {
        "schema_version": (
            "av-trace.p23-102-machine-provisional-family-registry/1.0"
        ),
        "registry_id": "AV-TRACE-P23-102-MACHINE-PROVISIONAL-FAMILIES-V1",
        "status": "MACHINE_PROVISIONAL_FROZEN",
        "decision": READY,
        **_base_metadata(inputs),
        "source_registry_payload_sha256": registry[
            "registry_payload_sha256"
        ],
        "conversion_policy": {
            "only_structurally_valid_repair_leads_converted": True,
            "source_status_preserved": "REPAIR",
            "semantic_completion_performed": False,
            "candidate_reordering_performed": False,
            "candidate_filtering_after_validation_performed": False,
        },
        "source_uniform_human_prescreen_gate": copy.deepcopy(
            registry["source_uniform_human_prescreen_gate"]
        ),
        "acceptance_boundary": {
            "accepted_family_count": 0,
            "accepted_ses_count": 0,
            "h_tier_count": 0,
            "gate_a_credit_count": 0,
            "future_test_eligible": False,
            "required_before_any_future_acceptance": registry[
                "acceptance_boundary"
            ]["required_before_any_future_acceptance"],
        },
        "profile_accounting": copy.deepcopy(
            registry["profile_accounting"]
        ),
        "family_count": len(families),
        "families": families,
    }
    evidence_registry = {
        "schema_version": (
            "av-trace.p23-102-machine-provisional-evidence-registry/1.0"
        ),
        "registry_id": "AV-TRACE-P23-102-MACHINE-PROVISIONAL-EVIDENCE-V1",
        "status": "MACHINE_PROVISIONAL_EVIDENCE_FROZEN",
        "decision": READY,
        **_base_metadata(inputs),
        "coverage_phrase_compatibility": {
            "required_phrase": REQUIRED_EVIDENCE_PHRASE,
            "asserted": False,
            "reason": (
                "There are zero accepted SESs. Exact evidence is frozen only "
                "for REPAIR-status machine leads; no saturation or accepted-"
                "SES coverage claim is made."
            ),
        },
        "evidence_exposure_boundary": {
            "search_pointers_are_not_citations": True,
            "only_acquired_public_observations_are_citable": True,
            "private_route_ids_never_model_visible": True,
            "answer_keys_never_model_visible": True,
            "accepted_support_labels_never_model_visible": True,
            "semantic_annotations_never_model_visible": True,
        },
        "honest_zero_profiles": {
            profile: copy.deepcopy(registry["profile_accounting"][profile])
            for profile in ("V+S", "V+S+A")
        },
        "evidence_count": len(evidence),
        "route_group_count": len(routes),
        "evidence": evidence,
        "route_groups": routes,
    }
    return seal(family_registry), seal(evidence_registry)


def _interventions(
    inputs: Mapping[str, Any],
    family_registry: Mapping[str, Any],
    evidence_registry: Mapping[str, Any],
) -> dict[str, Any]:
    evidence_by_id = {
        row["evidence_handle_id"]: row
        for row in evidence_registry["evidence"]
    }
    route_by_id = {
        row["route_group_id"]: row
        for row in evidence_registry["route_groups"]
    }
    interventions: list[dict[str, Any]] = []
    standard_error = {
        "status": "unavailable",
        "error_code": "REGISTERED_ROUTE_CHANNEL_UNAVAILABLE",
        "message": "The registered evidence route is currently unavailable.",
        "retryable": True,
    }
    response_shape = {
        key: type(value).__name__ for key, value in standard_error.items()
    }
    for family in family_registry["families"]:
        route = route_by_id[family["route_group_id"]]
        handle_ids = list(route["evidence_handle_ids"])
        record_ids = sorted(
            {evidence_by_id[item]["record_id"] for item in handle_ids}
        )
        for mechanism in MECHANISMS:
            intervention_id = _stable_id(
                "mpi", family["family_id"], mechanism
            )
            necessity_group_id = _stable_id(
                "mpn", family["family_id"], mechanism
            )
            row = {
                "intervention_id": intervention_id,
                "family_id": family["family_id"],
                "route_group_id": route["route_group_id"],
                "mechanism": mechanism,
                "machine_provisional_status": "REPAIR",
                "necessity_group_id": necessity_group_id,
                "necessity_group_semantics": (
                    "PROVISIONAL_INTERVENTION_GROUP_NOT_CAUSAL_NECESSITY"
                ),
                "necessity_validated": False,
                "human_validated": False,
                "accepted_ses": False,
                "suppressed_evidence_handle_ids": handle_ids,
                "suppressed_segment_ids": record_ids,
                "affected_modalities": ["ambient_audio", "vision"],
                "derived_leak_closure": {
                    "suppress_search_pointers_to_registered_records": True,
                    "suppress_inspection_by_registered_record_id": True,
                    "suppress_route_summaries_and_claim_derivatives": True,
                    "suppress_deterministic_visual_or_audio_derivatives": True,
                    "suppress_cross_modal_fused_pointers": True,
                    "closure_human_validated": False,
                },
                "unaffected_result_order_attestation": {
                    "relative_order_preserved": True,
                    "payloads_byte_preserved": True,
                    "latency_bucket_preserved": True,
                    "only_registered_route_and_derivatives_affected": True,
                },
                "restoration_v2": {
                    "template_id": "task145-exogenous-restoration-v2",
                    "template_version": "2.0",
                    "index_base": "zero",
                    "fixed_action_index": 4,
                    "delivery_boundary": (
                        "after_four_completed_action_response_cycles_"
                        "before_fifth_model_decision"
                    ),
                    "checkpoint_event": copy.deepcopy(CHECKPOINT_EVENT),
                    "checkpoint_event_canonical_sha256": object_hash(
                        CHECKPOINT_EVENT
                    ),
                    "depends_on_action_identity": False,
                    "depends_on_system_identity": False,
                    "depends_on_output_or_correctness": False,
                    "depends_on_get_channel_status": False,
                },
            }
            if mechanism == "SILENT_ROUTE_WITHHOLDING":
                row["visibility"] = "no_explicit_outage_marker"
                row["block_behavior"] = (
                    "Omit registered route pointers and close deterministic "
                    "derivatives without disclosing the withholding."
                )
            else:
                row["visibility"] = (
                    "standardized_typed_unavailable_response"
                )
                row["channel"] = "registered_visual_ambient_route"
                row["typed_error_code"] = standard_error["error_code"]
                row["typed_error_message"] = standard_error["message"]
                row["typed_error_response"] = copy.deepcopy(standard_error)
                row["response_shape_hash"] = object_hash(response_shape)
                row["block_behavior"] = (
                    "Return the frozen typed unavailable response for access "
                    "to any registered route record or closed derivative."
                )
            interventions.append(row)
    manifest = {
        "schema_version": (
            "av-trace.p23-102-machine-provisional-interventions/1.0"
        ),
        "manifest_id": (
            "AV-TRACE-P23-102-MACHINE-PROVISIONAL-INTERVENTIONS-V1"
        ),
        "status": "MECHANISM_SPECIFIC_FROZEN",
        "decision": READY,
        **_base_metadata(inputs),
        "family_registry_payload_sha256": family_registry["payload_sha256"],
        "evidence_registry_payload_sha256": evidence_registry[
            "payload_sha256"
        ],
        "mechanisms": list(MECHANISMS),
        "intervention_count": len(interventions),
        "interventions": interventions,
        "semantics_boundary": {
            "answer_semantics": "PROVISIONAL_NOT_HUMAN_VALIDATED",
            "support_semantics": "PROVISIONAL_NOT_HUMAN_VALIDATED",
            "necessity_semantics": "PROVISIONAL_NOT_HUMAN_VALIDATED",
            "mechanism_specific_route_closure_human_validated": False,
            "scientific_execution_authorized": False,
        },
    }
    return seal(manifest)


def _state_surfaces(
    inputs: Mapping[str, Any],
    family_registry: Mapping[str, Any],
    evidence_registry: Mapping[str, Any],
    intervention_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    family_by_id = {
        row["family_id"]: row for row in family_registry["families"]
    }
    surfaces: list[dict[str, Any]] = []
    for intervention in intervention_manifest["interventions"]:
        family = family_by_id[intervention["family_id"]]
        all_handles = list(intervention["suppressed_evidence_handle_ids"])
        for arm in ARMS:
            surface = {
                "surface_id": _stable_id(
                    "mps", intervention["intervention_id"], arm
                ),
                "intervention_id": intervention["intervention_id"],
                "family_id": intervention["family_id"],
                "route_group_id": intervention["route_group_id"],
                "mechanism": intervention["mechanism"],
                "arm": arm,
                "machine_provisional_status": "REPAIR",
                "question_template": family["question_template"],
                "answer_template": family["answer_template"],
                "public_claim_handles": [
                    row["public_claim_handle"]
                    for row in family["atomic_claim_templates"]
                ],
                "answer_support_and_necessity_semantics": (
                    "PROVISIONAL_NOT_HUMAN_VALIDATED"
                ),
                "human_validated": False,
                "private_fields_model_visible": False,
                "private_fields": [
                    "family_id",
                    "route_group_id",
                    "intervention_id",
                    "necessity_group_id",
                    "support_mapping",
                    "arm",
                    "restoration_applied",
                ],
                "public_invariants": {
                    "question_and_claims_invariant": True,
                    "tool_menu_and_order_invariant": True,
                    "budgets_and_costs_invariant": True,
                    "unaffected_result_order_and_payload_invariant": True,
                    "result_shape_and_latency_bucket_invariant": True,
                },
            }
            if arm == "C":
                surface.update(
                    {
                        "state": "CLEAN",
                        "initial_access": (
                            "registered_machine_provisional_route_reachable"
                        ),
                        "scheduled_event": "none",
                        "available_evidence_handle_ids_initial": all_handles,
                        "suppressed_evidence_handle_ids_initial": [],
                        "available_evidence_handle_ids_after_checkpoint": (
                            all_handles
                        ),
                        "restoration_applied": False,
                    }
                )
            elif arm == "B":
                surface.update(
                    {
                        "state": "BLOCKED",
                        "initial_access": "registered_route_inaccessible",
                        "scheduled_event": "none",
                        "available_evidence_handle_ids_initial": [],
                        "suppressed_evidence_handle_ids_initial": all_handles,
                        "available_evidence_handle_ids_after_checkpoint": [],
                        "restoration_applied": False,
                    }
                )
            elif arm == "R":
                surface.update(
                    {
                        "state": "RESTORED",
                        "initial_access": (
                            "identical_to_blocked_prefix_through_checkpoint"
                        ),
                        "scheduled_event": (
                            "byte_identical_checkpoint_plus_hidden_restoration"
                        ),
                        "available_evidence_handle_ids_initial": [],
                        "suppressed_evidence_handle_ids_initial": all_handles,
                        "available_evidence_handle_ids_after_checkpoint": (
                            all_handles
                        ),
                        "restoration_applied": True,
                    }
                )
            else:
                surface.update(
                    {
                        "state": "NO_TRIGGER",
                        "initial_access": (
                            "identical_to_restored_prefix_through_checkpoint"
                        ),
                        "scheduled_event": (
                            "byte_identical_checkpoint_without_restoration"
                        ),
                        "available_evidence_handle_ids_initial": [],
                        "suppressed_evidence_handle_ids_initial": all_handles,
                        "available_evidence_handle_ids_after_checkpoint": [],
                        "restoration_applied": False,
                    }
                )
            if arm in {"R", "N"}:
                surface["checkpoint"] = {
                    "index_base": "zero",
                    "action_index": 4,
                    "delivery_boundary": (
                        "after_four_completed_action_response_cycles_"
                        "before_fifth_model_decision"
                    ),
                    "event": copy.deepcopy(CHECKPOINT_EVENT),
                    "event_canonical_sha256": object_hash(
                        CHECKPOINT_EVENT
                    ),
                    "public_bytes_identical_r_n": True,
                    "reveals_restoration": False,
                }
                surface["paired_prefix"] = {
                    "construction": (
                        "single_blocked_prefix_then_fresh_replayed_fork"
                    ),
                    "public_transcript_identical_through_event": True,
                    "fresh_continuation_session": True,
                    "early_terminal_policy": (
                        "copy_terminal_prefix_to_both_assignments_and_keep_"
                        "both_in_itt"
                    ),
                }
            surfaces.append(surface)
    manifest = {
        "schema_version": (
            "av-trace.p23-102-machine-provisional-state-surfaces/1.0"
        ),
        "manifest_id": (
            "AV-TRACE-P23-102-MACHINE-PROVISIONAL-STATE-SURFACES-V1"
        ),
        "status": "FROZEN",
        "decision": READY,
        **_base_metadata(inputs),
        "family_registry_payload_sha256": family_registry["payload_sha256"],
        "evidence_registry_payload_sha256": evidence_registry[
            "payload_sha256"
        ],
        "intervention_manifest_payload_sha256": intervention_manifest[
            "payload_sha256"
        ],
        "arms": list(ARMS),
        "surface_count": len(surfaces),
        "surfaces": surfaces,
        "exposure_constraints": {
            "C": "all registered provisional route evidence reachable",
            "B": "all registered provisional route evidence inaccessible",
            "R": (
                "blocked through the neutral action-index-4 checkpoint; "
                "registered route restored only after the checkpoint"
            ),
            "N": (
                "blocked through and after the byte-identical action-index-4 "
                "checkpoint"
            ),
            "search_pointer_is_not_citation": True,
            "observation_acquisition_required_for_citation": True,
            "cross_state_cache_or_memory_sharing_forbidden": True,
        },
    }
    return seal(manifest)


def _source_split(inputs: Mapping[str, Any]) -> dict[str, Any]:
    manifest = {
        "schema_version": (
            "av-trace.p23-102-machine-provisional-source-split/1.0"
        ),
        "manifest_id": (
            "AV-TRACE-P23-102-MACHINE-PROVISIONAL-SOURCE-SPLIT-V1"
        ),
        "status": "P23_DEVELOPMENT_ONLY_SOURCE_DISJOINT_FROM_EVALUATION",
        "decision": READY,
        **_base_metadata(inputs),
        "source_assignments": [
            {
                "source_group_id": SOURCE_GROUP_ID,
                "source_id": SOURCE_ID,
                "split": "DEVELOPMENT_ONLY",
                "development_rehearsal_eligible": True,
                "evaluation_eligible": False,
                "future_test_eligible": False,
                "fresh_normal_mode_regeneration_required_for_any_future_test": (
                    True
                ),
            }
        ],
        "split_boundary": {
            "P23_102_development_only": True,
            "P23_102_future_test_ineligible": True,
            "evaluation_source_ids": [],
            "source_disjoint_evaluation_claim_scope": (
                "P23_102 is excluded from evaluation; no evaluation source "
                "set is created by this bundle."
            ),
            "source_generalization_claim_allowed": False,
        },
    }
    return seal(manifest)


def _leakage_gate(
    inputs: Mapping[str, Any],
    artifacts: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    content_hashes = {
        name: artifact["payload_sha256"]
        for name, artifact in sorted(artifacts.items())
    }
    gate = {
        "schema_version": (
            "av-trace.p23-102-machine-provisional-leakage-gate/1.0"
        ),
        "gate_id": "AV-TRACE-P23-102-MACHINE-PROVISIONAL-LEAKAGE-GATE-V1",
        "status": "PASS",
        "decision": READY,
        **_base_metadata(inputs),
        "bundle_content_sha256": object_hash(content_hashes),
        "artifact_payload_hashes": content_hashes,
        "allowed_inputs": [
            "repaired machine candidate registry",
            "verified source-derived full timeline index and manifests",
            "public exogenous restoration-v2 protocol",
            "public P23_102 rehearsal configuration",
        ],
        "forbidden_inputs": [
            "EPIC semantic annotations",
            "private human labels",
            "human answer keys",
            "accepted SES labels",
            "H-tier labels",
            "Gate-A adjudications",
            "evaluation outcomes",
            "model trajectories",
            "raw media",
        ],
        "checks": {
            "semantic_annotations_entered": False,
            "private_human_labels_entered": False,
            "human_prescreen_entered": False,
            "accepted_family_labels_entered": False,
            "accepted_ses_labels_entered": False,
            "h_tier_labels_entered": False,
            "gate_a_claims_entered": False,
            "answer_keys_entered": False,
            "evaluation_outcomes_entered": False,
            "raw_media_opened": False,
            "models_loaded": False,
            "network_used": False,
            "machine_templates_preserved_without_semantic_completion": True,
        },
        "model_visible_firewall": {
            "private_family_ids_visible": False,
            "private_route_ids_visible": False,
            "arm_or_intervention_ids_visible": False,
            "support_mapping_visible": False,
            "restoration_notice_visible": False,
            "answer_key_visible": False,
            "accepted_support_label_visible": False,
        },
        "claim_firewall": {
            "accepted_families": 0,
            "accepted_ses": 0,
            "h_tiers": 0,
            "gate_a_claims": 0,
            "validated_answer_semantics": 0,
            "validated_support_semantics": 0,
            "validated_necessity_semantics": 0,
            "V+S_machine_leads": 0,
            "V+S+A_machine_leads": 0,
        },
    }
    return seal(gate)


def build_bundle(inputs: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Build all six deterministic artifacts and validate the result."""
    validate_inputs(inputs)
    family_registry, evidence_registry = _family_and_evidence(inputs)
    intervention_manifest = _interventions(
        inputs, family_registry, evidence_registry
    )
    state_surface_manifest = _state_surfaces(
        inputs,
        family_registry,
        evidence_registry,
        intervention_manifest,
    )
    source_split_manifest = _source_split(inputs)
    artifacts: dict[str, dict[str, Any]] = {
        "family_registry.json": family_registry,
        "evidence_registry.json": evidence_registry,
        "intervention_manifest.json": intervention_manifest,
        "state_surface_manifest.json": state_surface_manifest,
        "source_split_manifest.json": source_split_manifest,
    }
    artifacts["leakage_gate.json"] = _leakage_gate(inputs, artifacts)
    validate_bundle(artifacts, inputs=inputs)
    return artifacts


def validate_bundle(
    artifacts: Mapping[str, Mapping[str, Any]],
    *,
    inputs: Mapping[str, Any] | None = None,
) -> None:
    """Validate hashes, references, exposures, and all nonclaim boundaries."""
    _require(set(artifacts) == set(OUTPUT_NAMES), "OUTPUT_SET_INVALID")
    for name, artifact in artifacts.items():
        verify_seal(artifact, label=name.upper())
        _require(artifact.get("decision") == READY, "DECISION_INVALID")
        _require(
            artifact.get("source_id") == SOURCE_ID
            and artifact.get("source_group_id") == SOURCE_GROUP_ID,
            "ARTIFACT_SOURCE_INVALID",
        )

    families = artifacts["family_registry.json"]
    evidence = artifacts["evidence_registry.json"]
    interventions = artifacts["intervention_manifest.json"]
    surfaces = artifacts["state_surface_manifest.json"]
    split = artifacts["source_split_manifest.json"]
    leakage = artifacts["leakage_gate.json"]

    _require(
        families.get("status") == "MACHINE_PROVISIONAL_FROZEN",
        "FAMILY_REGISTRY_STATUS_INVALID",
    )
    boundary = families["acceptance_boundary"]
    _require(
        boundary["accepted_family_count"] == 0
        and boundary["accepted_ses_count"] == 0
        and boundary["h_tier_count"] == 0
        and boundary["gate_a_credit_count"] == 0
        and boundary["future_test_eligible"] is False,
        "FAMILY_ACCEPTANCE_BOUNDARY_VIOLATION",
    )
    family_rows = families["families"]
    family_by_id = {row["family_id"]: row for row in family_rows}
    _require(
        len(family_by_id) == families["family_count"] == len(family_rows),
        "FAMILY_COUNT_OR_ID_INVALID",
    )
    for row in family_rows:
        _require(
            row["machine_provisional_status"] == "REPAIR"
            and row["profile_hypothesis"] == "V+A"
            and row["accepted_family"] is False
            and row["accepted_ses"] is False
            and row["h_tier"] is None
            and row["gate_a_credit"] is False
            and row["human_prescreen"] == "NOT_PERFORMED",
            "FAMILY_NONCLAIM_BOUNDARY_INVALID",
        )
        _require(
            row["temporal_structure"]["temporal_hypothesis"]
            in {"near_local", "far_separated"}
            and row["temporal_structure"]["hop_hypothesis"]
            in {"one_hop", "multi_hop"},
            "FAMILY_TEMPORAL_LABEL_INVALID",
        )
        _require(
            row["recurrence_checks"][
                "human_full_source_recurrence_review_required"
            ]
            is True
            and bool(row["substitution_risks"])
            and bool(row["atomic_claim_templates"]),
            "FAMILY_REVIEW_FIELDS_INVALID",
        )
        for claim in row["atomic_claim_templates"]:
            _require(
                claim["status"] == "MACHINE_TEMPLATE_UNFILLED"
                and "NOT_HUMAN_VALIDATED"
                in claim["answer_semantics"]
                and "NOT_ESTABLISHED" in claim["necessity_semantics"],
                "CLAIM_TEMPLATE_SEMANTICS_INVALID",
            )

    _require(
        evidence.get("status") == "MACHINE_PROVISIONAL_EVIDENCE_FROZEN",
        "EVIDENCE_STATUS_INVALID",
    )
    coverage = evidence["coverage_phrase_compatibility"]
    _require(
        coverage["required_phrase"] == REQUIRED_EVIDENCE_PHRASE
        and coverage["asserted"] is False,
        "EVIDENCE_COVERAGE_CLAIM_INVALID",
    )
    evidence_rows = evidence["evidence"]
    evidence_by_id = {
        row["evidence_handle_id"]: row for row in evidence_rows
    }
    _require(
        len(evidence_by_id)
        == evidence["evidence_count"]
        == len(evidence_rows),
        "EVIDENCE_COUNT_OR_ID_INVALID",
    )
    route_rows = evidence["route_groups"]
    route_by_id = {row["route_group_id"]: row for row in route_rows}
    _require(
        len(route_by_id)
        == evidence["route_group_count"]
        == len(route_rows)
        == len(family_rows),
        "ROUTE_COUNT_OR_ID_INVALID",
    )
    for row in evidence_rows:
        _require(row["family_id"] in family_by_id, "EVIDENCE_FAMILY_DANGLING")
        _require(row["route_group_id"] in route_by_id, "EVIDENCE_ROUTE_DANGLING")
        _require(
            row["human_semantic_validation"] == "NOT_PERFORMED"
            and row["human_validated"] is False
            and row["semantic_content_asserted"] is False
            and row["modality"] in {"vision", "ambient_audio"}
            and 0 <= row["start_us"] < row["end_us"],
            "EVIDENCE_BOUNDARY_INVALID",
        )
    for row in route_rows:
        family = family_by_id.get(row["family_id"])
        _require(family is not None, "ROUTE_FAMILY_DANGLING")
        _require(
            row["route_group_id"] == family["route_group_id"],
            "ROUTE_FAMILY_BINDING_INVALID",
        )
        _require(
            set(row["evidence_handle_ids"])
            == set(family["evidence_handle_ids"])
            and set(row["evidence_handle_ids"]) <= set(evidence_by_id),
            "ROUTE_EVIDENCE_BINDING_INVALID",
        )
        _require(
            row["support_validated"] is False
            and row["necessity_validated"] is False
            and row["human_validated"] is False,
            "ROUTE_VALIDATION_CLAIM_INVALID",
        )

    _require(
        interventions.get("status") == "MECHANISM_SPECIFIC_FROZEN",
        "INTERVENTION_STATUS_INVALID",
    )
    intervention_rows = interventions["interventions"]
    intervention_by_id = {
        row["intervention_id"]: row for row in intervention_rows
    }
    _require(
        len(intervention_by_id)
        == interventions["intervention_count"]
        == len(family_rows) * len(MECHANISMS),
        "INTERVENTION_COUNT_OR_ID_INVALID",
    )
    family_mechanisms: dict[str, set[str]] = {
        family_id: set() for family_id in family_by_id
    }
    for row in intervention_rows:
        _require(
            row["family_id"] in family_by_id
            and row["route_group_id"] in route_by_id,
            "INTERVENTION_REFERENCE_DANGLING",
        )
        family_mechanisms[row["family_id"]].add(row["mechanism"])
        _require(
            row["machine_provisional_status"] == "REPAIR"
            and row["necessity_validated"] is False
            and row["human_validated"] is False
            and row["accepted_ses"] is False,
            "INTERVENTION_NONCLAIM_BOUNDARY_INVALID",
        )
        _require(
            set(row["suppressed_evidence_handle_ids"])
            == set(route_by_id[row["route_group_id"]]["evidence_handle_ids"])
            and row["restoration_v2"]["fixed_action_index"] == 4
            and row["restoration_v2"]["index_base"] == "zero"
            and row["restoration_v2"]["checkpoint_event"]
            == CHECKPOINT_EVENT,
            "INTERVENTION_ROUTE_OR_SCHEDULE_INVALID",
        )
        if row["mechanism"] == "SILENT_ROUTE_WITHHOLDING":
            _require(
                row["visibility"] == "no_explicit_outage_marker",
                "SILENT_INTERVENTION_INVALID",
            )
        elif row["mechanism"] == "EXPLICIT_CHANNEL_OUTAGE":
            _require(
                row["visibility"]
                == "standardized_typed_unavailable_response"
                and bool(row["channel"])
                and bool(row["typed_error_code"])
                and bool(row["typed_error_message"])
                and str(row["response_shape_hash"]).startswith("sha256:"),
                "EXPLICIT_INTERVENTION_INVALID",
            )
        else:
            raise BundleError("UNKNOWN_INTERVENTION_MECHANISM")
    _require(
        all(value == set(MECHANISMS) for value in family_mechanisms.values()),
        "FAMILY_MECHANISM_COVERAGE_INVALID",
    )

    _require(
        surfaces.get("status") == "FROZEN",
        "STATE_SURFACE_STATUS_INVALID",
    )
    surface_rows = surfaces["surfaces"]
    _require(
        surfaces["surface_count"]
        == len(surface_rows)
        == len(intervention_rows) * len(ARMS),
        "STATE_SURFACE_COUNT_INVALID",
    )
    per_intervention: dict[str, dict[str, Mapping[str, Any]]] = {
        key: {} for key in intervention_by_id
    }
    surface_ids: set[str] = set()
    for row in surface_rows:
        _require(
            row["surface_id"] not in surface_ids,
            "DUPLICATE_STATE_SURFACE_ID",
        )
        surface_ids.add(row["surface_id"])
        intervention = intervention_by_id.get(row["intervention_id"])
        _require(intervention is not None, "STATE_INTERVENTION_DANGLING")
        per_intervention[row["intervention_id"]][row["arm"]] = row
        all_handles = intervention["suppressed_evidence_handle_ids"]
        _require(
            row["private_fields_model_visible"] is False
            and row["human_validated"] is False
            and row["machine_provisional_status"] == "REPAIR",
            "STATE_PRIVATE_OR_VALIDATION_BOUNDARY_INVALID",
        )
        if row["arm"] == "C":
            _require(
                row["state"] == "CLEAN"
                and row["available_evidence_handle_ids_initial"]
                == all_handles
                and row["suppressed_evidence_handle_ids_initial"] == []
                and row["available_evidence_handle_ids_after_checkpoint"]
                == all_handles
                and row["scheduled_event"] == "none",
                "C_EXPOSURE_INVALID",
            )
        elif row["arm"] == "B":
            _require(
                row["state"] == "BLOCKED"
                and row["available_evidence_handle_ids_initial"] == []
                and row["suppressed_evidence_handle_ids_initial"]
                == all_handles
                and row["available_evidence_handle_ids_after_checkpoint"]
                == []
                and row["scheduled_event"] == "none",
                "B_EXPOSURE_INVALID",
            )
        elif row["arm"] == "R":
            _require(
                row["state"] == "RESTORED"
                and row["available_evidence_handle_ids_initial"] == []
                and row["suppressed_evidence_handle_ids_initial"]
                == all_handles
                and row["available_evidence_handle_ids_after_checkpoint"]
                == all_handles
                and row["restoration_applied"] is True,
                "R_EXPOSURE_INVALID",
            )
        elif row["arm"] == "N":
            _require(
                row["state"] == "NO_TRIGGER"
                and row["available_evidence_handle_ids_initial"] == []
                and row["suppressed_evidence_handle_ids_initial"]
                == all_handles
                and row["available_evidence_handle_ids_after_checkpoint"]
                == []
                and row["restoration_applied"] is False,
                "N_EXPOSURE_INVALID",
            )
        else:
            raise BundleError("UNKNOWN_STATE_ARM")
        if row["arm"] in {"R", "N"}:
            checkpoint = row["checkpoint"]
            _require(
                checkpoint["action_index"] == 4
                and checkpoint["index_base"] == "zero"
                and checkpoint["event"] == CHECKPOINT_EVENT
                and checkpoint["event_canonical_sha256"]
                == object_hash(CHECKPOINT_EVENT)
                and checkpoint["public_bytes_identical_r_n"] is True
                and checkpoint["reveals_restoration"] is False,
                "R_N_CHECKPOINT_INVALID",
            )
    for rows in per_intervention.values():
        _require(set(rows) == set(ARMS), "STATE_ARM_COVERAGE_INVALID")
        _require(
            rows["R"]["checkpoint"] == rows["N"]["checkpoint"],
            "R_N_CHECKPOINT_MISMATCH",
        )
        _require(
            rows["R"]["question_template"] == rows["N"]["question_template"]
            and rows["R"]["public_claim_handles"]
            == rows["N"]["public_claim_handles"],
            "R_N_PUBLIC_PREFIX_INPUT_MISMATCH",
        )

    _require(
        split.get("status")
        == "P23_DEVELOPMENT_ONLY_SOURCE_DISJOINT_FROM_EVALUATION"
        and split["split_boundary"]["P23_102_development_only"] is True
        and split["split_boundary"]["P23_102_future_test_ineligible"]
        is True
        and split["source_assignments"][0]["future_test_eligible"] is False,
        "SOURCE_SPLIT_INVALID",
    )
    _require(
        leakage.get("status") == "PASS"
        and leakage["checks"]["semantic_annotations_entered"] is False
        and leakage["checks"]["private_human_labels_entered"] is False
        and leakage["checks"]["raw_media_opened"] is False
        and leakage["checks"]["models_loaded"] is False
        and leakage["checks"]["network_used"] is False,
        "LEAKAGE_GATE_INVALID",
    )
    claim_firewall = leakage["claim_firewall"]
    _require(
        all(
            claim_firewall[key] == 0
            for key in (
                "accepted_families",
                "accepted_ses",
                "h_tiers",
                "gate_a_claims",
                "validated_answer_semantics",
                "validated_support_semantics",
                "validated_necessity_semantics",
                "V+S_machine_leads",
                "V+S+A_machine_leads",
            )
        ),
        "LEAKAGE_CLAIM_FIREWALL_INVALID",
    )
    non_leakage = {
        name: artifact["payload_sha256"]
        for name, artifact in sorted(artifacts.items())
        if name != "leakage_gate.json"
    }
    _require(
        leakage["artifact_payload_hashes"] == non_leakage
        and leakage["bundle_content_sha256"] == object_hash(non_leakage),
        "BUNDLE_HASH_INVALID",
    )

    if inputs is not None:
        validate_inputs(inputs)
        documents = _index_documents(inputs["index"])
        duration_us = int(inputs["segment_manifest"]["duration_us"])
        for row in evidence_rows:
            indexed = documents[row["modality"]].get(row["record_id"])
            _require(indexed is not None, "OUTPUT_INDEX_HANDLE_UNKNOWN")
            _require(
                int(indexed["start_us"]) == row["start_us"]
                and int(indexed["end_us"]) == row["end_us"]
                and row["end_us"] <= duration_us,
                "OUTPUT_INDEX_HANDLE_RANGE_MISMATCH",
            )


def write_bundle(output_root: Path, artifacts: Mapping[str, Any]) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    output_root.chmod(0o700)
    for name in OUTPUT_NAMES:
        _write_json(output_root / name, artifacts[name])


def load_bundle(output_root: Path) -> dict[str, Any]:
    return {name: _load_json(output_root / name) for name in OUTPUT_NAMES}


def _summary(
    artifacts: Mapping[str, Mapping[str, Any]],
    *,
    output_root: Path,
    written: bool,
) -> dict[str, Any]:
    families = artifacts["family_registry.json"]
    evidence = artifacts["evidence_registry.json"]
    interventions = artifacts["intervention_manifest.json"]
    surfaces = artifacts["state_surface_manifest.json"]
    return {
        "decision": READY,
        "output_root": output_root.as_posix(),
        "written": written,
        "family_count": families["family_count"],
        "evidence_count": evidence["evidence_count"],
        "route_group_count": evidence["route_group_count"],
        "intervention_count": interventions["intervention_count"],
        "surface_count": surfaces["surface_count"],
        "accepted_family_count": 0,
        "accepted_ses_count": 0,
        "h_tier_count": 0,
        "gate_a_claim_count": 0,
        "V+S_machine_lead_count": 0,
        "V+S+A_machine_lead_count": 0,
        "bundle_content_sha256": artifacts["leakage_gate.json"][
            "bundle_content_sha256"
        ],
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=repo_root_default(),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=OUTPUT_ROOT,
    )
    parser.add_argument(
        "--mode",
        choices=("build", "write", "check"),
        default="build",
        help=(
            "build validates in memory; write atomically emits the bundle; "
            "check compares a committed bundle to a fresh deterministic build"
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = args.repo_root.resolve()
    output_root = _safe_path(
        repo_root, args.output_root, label="OUTPUT_ROOT"
    )
    try:
        inputs = load_inputs(repo_root)
        expected = build_bundle(inputs)
        if args.mode == "write":
            write_bundle(output_root, expected)
            actual = load_bundle(output_root)
            validate_bundle(actual, inputs=inputs)
            if canonical_bytes(actual) != canonical_bytes(expected):
                raise BundleError("WRITTEN_BUNDLE_NOT_DETERMINISTIC")
        elif args.mode == "check":
            actual = load_bundle(output_root)
            validate_bundle(actual, inputs=inputs)
            if canonical_bytes(actual) != canonical_bytes(expected):
                raise BundleError("COMMITTED_BUNDLE_DIFFERS_FROM_BUILD")
        print(
            json.dumps(
                _summary(
                    expected,
                    output_root=Path(
                        _relative(repo_root, output_root)
                    ),
                    written=args.mode == "write",
                ),
                sort_keys=True,
            )
        )
        return 0
    except (BundleError, FileNotFoundError, KeyError, TypeError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "decision": REPAIR,
                    "error": str(exc),
                },
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
