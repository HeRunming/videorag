"""Fail-closed acquisition/annotation/release gate checks."""

from __future__ import annotations

from enum import Enum
from typing import Any

from .errors import ValidationIssue, ValidationReport, make_report
from .schemas import SchemaRegistry
from .util import safe_sha256_json


class GateProfile(str, Enum):
    ACQUISITION = "acquisition"
    ANNOTATION = "annotation"
    PUBLIC_CORE_RELEASE = "public_core_release"
    EXTERNAL_COMPATIBILITY_UNPOOLED = "external_compatibility_unpooled"
    # Backward-compatible spelling retained for callers of the original API.
    PUBLIC_RELEASE = "public_release"


_GATE_STATUS = {
    GateProfile.ACQUISITION: {"acquisition_approved", "annotation_approved", "public_release_approved"},
    GateProfile.ANNOTATION: {"annotation_approved", "public_release_approved"},
    GateProfile.PUBLIC_CORE_RELEASE: {"public_release_approved"},
    GateProfile.EXTERNAL_COMPATIBILITY_UNPOOLED: {
        "annotation_approved",
        "public_release_approved",
    },
    GateProfile.PUBLIC_RELEASE: {"public_release_approved"},
}

_REQUIRED_DECISIONS = {
    GateProfile.ACQUISITION: {"acquisition", "processing"},
    GateProfile.ANNOTATION: {
        "acquisition",
        "processing",
        "derivative_release",
        "annotation_release",
        "transcript_release",
        "raw_media_release",
    },
    GateProfile.PUBLIC_CORE_RELEASE: {
        "acquisition",
        "processing",
        "derivative_release",
        "annotation_release",
        "transcript_release",
        "raw_media_release",
    },
    GateProfile.EXTERNAL_COMPATIBILITY_UNPOOLED: {
        "acquisition",
        "processing",
        "derivative_release",
        "annotation_release",
        "transcript_release",
        "raw_media_release",
    },
    GateProfile.PUBLIC_RELEASE: {
        "acquisition",
        "processing",
        "derivative_release",
        "annotation_release",
        "transcript_release",
        "raw_media_release",
    },
}

_PUBLIC_CORE_GATES = {
    GateProfile.PUBLIC_CORE_RELEASE,
    GateProfile.PUBLIC_RELEASE,
}


def validate_manifest_gate(
    manifest: dict[str, Any],
    gate: GateProfile | str,
    registry: SchemaRegistry | None = None,
) -> ValidationReport:
    gate = GateProfile(gate)
    registry = registry or SchemaRegistry()
    structural = registry.validate("acquisition-manifest", manifest)
    issues = list(structural.issues)
    if not isinstance(manifest, dict):
        return make_report(issues, gate=gate.value, manifest_hash=safe_sha256_json(manifest))
    audit = manifest.get("audit", {})
    rights = manifest.get("rights", {})
    if not isinstance(audit, dict):
        audit = {}
    if not isinstance(rights, dict):
        rights = {}
    decisions = rights.get("decisions", {})
    if not isinstance(decisions, dict):
        decisions = {}
    embedded_components = rights.get("embedded_components", {})
    if not isinstance(embedded_components, dict):
        embedded_components = {}
    status = audit.get("gate_status")
    if status is not None:
        if status not in _GATE_STATUS[gate]:
            issues.append(ValidationIssue("GATE-001", "/audit/gate_status", f"Gate {gate.value} requires one of {sorted(_GATE_STATUS[gate])}; found {status}."))

    unknown_fields = {
        "/rights/copyright_basis": rights.get("copyright_basis"),
        "/rights/acquisition_authority": rights.get("acquisition_authority"),
        "/rights/local_processing_authority": rights.get("local_processing_authority"),
        "/rights/review/outcome": rights.get("review", {}).get("outcome")
        if isinstance(rights.get("review"), dict)
        else None,
        "/privacy_safety/review_status": manifest.get("privacy_safety", {}).get("review_status")
        if isinstance(manifest.get("privacy_safety"), dict)
        else None,
    }
    unknown_fields.update(
        (f"/rights/decisions/{name}", decisions.get(name))
        for name in sorted(_REQUIRED_DECISIONS[gate])
    )
    unknown_fields.update(
        (f"/rights/embedded_components/{name}", value)
        for name, value in sorted(embedded_components.items())
    )
    for path, value in unknown_fields.items():
        if value == "unknown_hold":
            issues.append(ValidationIssue("GATE-002", path, f"unknown_hold cannot pass the {gate.value} gate."))

    if structural.ok:
        for name in sorted(_REQUIRED_DECISIONS[gate]):
            value = decisions[name]
            required = (
                "allowed"
                if gate in _PUBLIC_CORE_GATES
                or name in {"acquisition", "processing"}
                or (
                    gate is GateProfile.EXTERNAL_COMPATIBILITY_UNPOOLED
                    and name == "annotation_release"
                )
                else None
            )
            if required and value != required:
                issues.append(ValidationIssue("GATE-003", f"/rights/decisions/{name}", f"Decision {name} must be allowed for the {gate.value} gate; found {value}."))

        if rights["acquisition_authority"] != "allowed":
            issues.append(ValidationIssue("GATE-003", "/rights/acquisition_authority", "Acquisition authority must be allowed."))
        if rights["local_processing_authority"] != "allowed":
            issues.append(ValidationIssue("GATE-003", "/rights/local_processing_authority", "Local processing authority must be allowed."))
        if rights["review"]["outcome"] != "approved":
            issues.append(ValidationIssue("GATE-004", "/rights/review/outcome", "Rights review outcome must be approved."))
        if manifest["privacy_safety"]["review_status"] != "approved":
            issues.append(ValidationIssue("GATE-005", "/privacy_safety/review_status", "Privacy/safety review must be approved."))
        if not manifest["media"]["embedded_content_reviewed"]:
            issues.append(ValidationIssue("GATE-006", "/media/embedded_content_reviewed", "Embedded content review must be complete."))
        acquisition_status = manifest["acquisition"]["status"]
        acquisition_method = manifest["acquisition"]["method"]
        if acquisition_status not in {"planned", "completed"}:
            issues.append(ValidationIssue("GATE-007", "/acquisition/status", "Acquisition status must be planned or completed."))
        if acquisition_method == "none":
            issues.append(ValidationIssue("GATE-007", "/acquisition/method", "An approved gate requires a concrete authorized acquisition method."))
        if gate is not GateProfile.ACQUISITION and acquisition_status != "completed":
            issues.append(ValidationIssue("GATE-007", "/acquisition/status", f"The {gate.value} gate requires completed acquisition."))
        if manifest["integrity"]["content_sha256"] is None or manifest["integrity"]["byte_size"] is None:
            issues.append(ValidationIssue("GATE-008", "/integrity", "Frozen content hash and byte size are required for an approved gate."))
        for name, value in sorted(embedded_components.items()):
            if gate in _PUBLIC_CORE_GATES and value == "prohibited":
                issues.append(ValidationIssue("GATE-009", f"/rights/embedded_components/{name}", "A prohibited embedded component cannot pass public release."))
        for index, artifact in enumerate(manifest["derived_artifacts"]):
            pointer = f"/derived_artifacts/{index}"
            if artifact["source_asset_id"] != manifest["asset_id"]:
                issues.append(ValidationIssue("GATE-010", pointer + "/source_asset_id", "Derived artifact must reference this manifest asset."))
            if gate is not GateProfile.ACQUISITION and not artifact["substitution_risk_reviewed"]:
                issues.append(ValidationIssue("GATE-010", pointer + "/substitution_risk_reviewed", "Derived artifact substitution risk must be reviewed."))
            public_or_released = gate in _PUBLIC_CORE_GATES or artifact["release_audience"] == "public"
            if public_or_released and artifact["release_decision"] != "allowed":
                issues.append(ValidationIssue("GATE-010", pointer + "/release_decision", "A released artifact requires an allowed release decision."))
    return make_report(issues, gate=gate.value, manifest_hash=safe_sha256_json(manifest))
