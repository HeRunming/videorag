"""Offline human-reviewed conversion of reconnaissance records to candidates.

The snapshot importer deliberately does not emit ``NormalizedCandidate``
records.  This module is the explicit, signed review boundary between that
non-selectable reconnaissance artifact and a candidate inspection.  It has no
network, media, acquisition, annotation, or release side effects.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, fields
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import re
from typing import Any, Mapping, Sequence

from .io import canonical_json, sha256_json
from .models import NormalizedCandidate, immutable_revision

REVIEWER_DECISION_VERSION = "1.0"
REVIEWED_CANDIDATE_INSPECTION_VERSION = "1.0"
REVIEWER_REGISTRY_VERSION = "1.0"
REQUIRED_REVIEWER_ATTESTATION = (
    "I attest that every candidate claim is supported by the cited evidence "
    "and that this decision grants no acquisition, annotation, or release approval."
)

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_HMAC_RE = re.compile(r"^hmac-sha256:[0-9a-f]{64}$")
_NORMALIZED_FIELDS = {item.name for item in fields(NormalizedCandidate)}
_ROOT_KEYS = {
    "decision_version",
    "artifact_class",
    "imported_inspection_sha256",
    "output_mode",
    "selected_source_record_ids",
    "reviewer_evidence",
    "candidate_decisions",
    "reviewer",
    "decision_expires_at",
    "signature",
}
_CANDIDATE_DECISION_KEYS = {
    "source_record_ids",
    "candidate",
    "claim_evidence",
    "duration_provenance",
}
_REVIEWER_KEYS = {"reviewer_id", "role", "reviewed_at", "attestation"}
_SIGNATURE_KEYS = {"algorithm", "key_id", "value"}
_IMPORTER_ROOT_KEYS = {
    "inspection_version",
    "artifact_class",
    "promotion_status",
    "network_access_performed",
    "contains_media",
    "acquisition_authorization",
    "rights_policy",
    "limits",
    "source_files",
    "repositories",
    "license_evidence",
    "records",
    "source_lineage_joins",
    "summary",
    "inspection_sha256",
}


class ReviewedConversionError(ValueError):
    """A reviewed decision or its bound importer artifact is invalid."""


@dataclass(frozen=True)
class ReviewerIdentity:
    reviewer_id: str
    role: str
    reviewed_at: str
    attestation: str
    extensions: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReviewerEvidence:
    evidence_id: str
    evidence_type: str
    source: str
    observed_at: str
    claims: dict[str, Any]
    evidence_sha256: str | None = None
    extensions: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReviewedCandidateDecision:
    source_record_ids: tuple[str, ...]
    candidate: dict[str, Any]
    claim_evidence: dict[str, tuple[dict[str, Any], ...]]
    duration_provenance: dict[str, Any]
    extensions: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReviewerDecision:
    decision_version: str
    imported_inspection_sha256: str
    output_mode: str
    selected_source_record_ids: tuple[str, ...]
    reviewer_evidence: tuple[ReviewerEvidence, ...]
    candidate_decisions: tuple[ReviewedCandidateDecision, ...]
    reviewer: ReviewerIdentity
    decision_expires_at: str
    signature: dict[str, str]
    extensions: dict[str, Any] = field(default_factory=dict)


# Published as a Python object so callers can validate/describe the file
# format without adding a package-data or normative-schema dependency.
REVIEWER_DECISION_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "av-trace://reviewer-decision/1.0",
    "title": "AV-TRACE reviewed candidate decision",
    "type": "object",
    "required": [
        "decision_version",
        "artifact_class",
        "imported_inspection_sha256",
        "output_mode",
        "selected_source_record_ids",
        "reviewer_evidence",
        "candidate_decisions",
        "reviewer",
        "decision_expires_at",
        "signature",
    ],
    "properties": {
        "decision_version": {"const": REVIEWER_DECISION_VERSION},
        "artifact_class": {"const": "reviewed_candidate_decision"},
        "imported_inspection_sha256": {
            "type": "string",
            "pattern": r"^sha256:[0-9a-f]{64}$",
        },
        "output_mode": {"enum": ["exploratory", "freeze_ready"]},
        "selected_source_record_ids": {
            "type": "array",
            "minItems": 1,
            "uniqueItems": True,
            "items": {"type": "string", "minLength": 1},
        },
        "reviewer_evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "evidence_id",
                    "evidence_type",
                    "source",
                    "observed_at",
                    "claims",
                ],
                "properties": {
                    "evidence_id": {"type": "string", "minLength": 1},
                    "evidence_type": {"type": "string", "minLength": 1},
                    "source": {"type": "string", "minLength": 1},
                    "observed_at": {"type": "string", "minLength": 1},
                    "claims": {"type": "object"},
                    "evidence_sha256": {
                        "type": "string",
                        "pattern": r"^sha256:[0-9a-f]{64}$",
                    },
                },
            },
        },
        "candidate_decisions": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": [
                    "source_record_ids",
                    "candidate",
                    "claim_evidence",
                    "duration_provenance",
                ],
                "properties": {
                    "source_record_ids": {
                        "type": "array",
                        "minItems": 1,
                        "uniqueItems": True,
                        "items": {"type": "string", "minLength": 1},
                    },
                    "candidate": {
                        "type": "object",
                        "required": [
                            "dataset_id",
                            "adapter_id",
                            "provider",
                            "repository_id",
                            "source_id",
                            "split",
                            "duration_s",
                            "canonical_url",
                            "media_url",
                            "has_video",
                            "has_audio",
                            "has_speech",
                            "has_ambient_audio",
                            "transcript_available",
                            "evidence_available",
                            "revision",
                            "license_evidence",
                            "license_resolution_status",
                            "technical_access_status",
                            "access_gate",
                            "payload_state",
                            "media_rights_status",
                            "source_family",
                            "publisher",
                            "rightsholder_or_status",
                            "upstream_namespace",
                            "upstream_asset_id",
                            "identity_resolution_status",
                            "parent_dataset_id",
                            "parent_upstream_namespace",
                            "parent_upstream_asset_id",
                            "lineage_relation",
                        ],
                        "properties": {
                            "dataset_id": {"type": "string", "minLength": 1},
                            "adapter_id": {"type": "string", "minLength": 1},
                            "provider": {"type": "string", "minLength": 1},
                            "repository_id": {"type": "string", "minLength": 1},
                            "source_id": {"type": "string", "minLength": 1},
                            "split": {"type": "string", "minLength": 1},
                            "duration_s": {
                                "type": "number",
                                "exclusiveMinimum": 0,
                            },
                            "canonical_url": {"type": "string", "minLength": 1},
                            "media_url": {"type": ["string", "null"]},
                            "has_video": {"type": ["boolean", "null"]},
                            "has_audio": {"type": ["boolean", "null"]},
                            "has_speech": {"type": ["boolean", "null"]},
                            "has_ambient_audio": {"type": ["boolean", "null"]},
                            "transcript_available": {"type": "boolean"},
                            "evidence_available": {"type": "boolean"},
                            "revision": {"type": "string", "minLength": 1},
                            "license_evidence": {
                                "type": "array",
                                "items": {"type": "object"},
                            },
                            "license_resolution_status": {
                                "enum": ["consistent", "unresolved", "conflicting"]
                            },
                            "technical_access_status": {
                                "type": "string",
                                "minLength": 1,
                            },
                            "access_gate": {"type": "string", "minLength": 1},
                            "payload_state": {"type": "string", "minLength": 1},
                            "media_rights_status": {
                                "enum": [
                                    "unknown_hold",
                                    "restricted",
                                    "asset_reviewed",
                                ]
                            },
                            "source_family": {"type": "string", "minLength": 1},
                            "publisher": {"type": "string", "minLength": 1},
                            "rightsholder_or_status": {
                                "type": "string",
                                "minLength": 1,
                            },
                            "upstream_namespace": {"type": ["string", "null"]},
                            "upstream_asset_id": {"type": ["string", "null"]},
                            "identity_resolution_status": {
                                "enum": ["resolved", "unresolved", "conflicting"]
                            },
                            "parent_dataset_id": {"type": ["string", "null"]},
                            "parent_upstream_namespace": {
                                "type": ["string", "null"]
                            },
                            "parent_upstream_asset_id": {
                                "type": ["string", "null"]
                            },
                            "lineage_relation": {"type": ["string", "null"]},
                        },
                    },
                    "claim_evidence": {
                        "type": "object",
                        "additionalProperties": {
                            "type": "array",
                            "minItems": 1,
                            "items": {
                                "oneOf": [
                                    {
                                        "type": "object",
                                        "required": [
                                            "kind",
                                            "record_id",
                                            "pointer",
                                        ],
                                        "properties": {
                                            "kind": {"const": "imported_record"},
                                            "record_id": {
                                                "type": "string",
                                                "minLength": 1,
                                            },
                                            "pointer": {"type": "string"},
                                        },
                                    },
                                    {
                                        "type": "object",
                                        "required": [
                                            "kind",
                                            "evidence_id",
                                            "claim_path",
                                        ],
                                        "properties": {
                                            "kind": {"const": "reviewer_evidence"},
                                            "evidence_id": {
                                                "type": "string",
                                                "minLength": 1,
                                            },
                                            "claim_path": {"type": "string"},
                                        },
                                    },
                                ]
                            },
                        },
                    },
                    "duration_provenance": {
                        "type": "object",
                        "required": ["method", "source_description"],
                        "properties": {
                            "method": {"type": "string", "minLength": 1},
                            "source_description": {
                                "type": "string",
                                "minLength": 1,
                            },
                        },
                    },
                },
            },
        },
        "reviewer": {
            "type": "object",
            "required": ["reviewer_id", "role", "reviewed_at", "attestation"],
            "properties": {
                "reviewer_id": {"type": "string", "minLength": 1},
                "role": {"type": "string", "minLength": 1},
                "reviewed_at": {"type": "string", "minLength": 1},
                "attestation": {"const": REQUIRED_REVIEWER_ATTESTATION},
            },
        },
        "decision_expires_at": {"type": "string"},
        "signature": {
            "type": "object",
            "required": ["algorithm", "key_id", "value"],
            "properties": {
                "algorithm": {"const": "hmac-sha256"},
                "key_id": {"type": "string", "minLength": 1},
                "value": {
                    "type": "string",
                    "pattern": r"^hmac-sha256:[0-9a-f]{64}$",
                },
            },
        },
    },
}


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReviewedConversionError(f"{label} must be an object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ReviewedConversionError(f"{label} must be an array")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReviewedConversionError(f"{label} must be a non-empty string")
    return value.strip()


def _unique_texts(value: Any, label: str, *, nonempty: bool = True) -> tuple[str, ...]:
    values = tuple(_text(item, f"{label} item") for item in _array(value, label))
    if nonempty and not values:
        raise ReviewedConversionError(f"{label} must not be empty")
    if len(values) != len(set(values)):
        raise ReviewedConversionError(f"{label} contains duplicate record IDs")
    return values


def _parse_timestamp(value: Any, label: str) -> datetime:
    text = _text(value, label)
    if not text.endswith("Z"):
        raise ReviewedConversionError(f"{label} must be UTC RFC3339 ending in Z")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise ReviewedConversionError(f"{label} is not valid RFC3339") from exc
    if parsed.tzinfo is None:
        raise ReviewedConversionError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _json_pointer(value: Any, pointer: str, label: str) -> Any:
    if pointer == "":
        return value
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ReviewedConversionError(f"{label} must be a JSON pointer")
    current = value
    for raw_token in pointer[1:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping):
            if token not in current:
                raise ReviewedConversionError(f"{label} does not exist: {pointer}")
            current = current[token]
        elif isinstance(current, list):
            try:
                index = int(token)
                current = current[index]
            except (ValueError, IndexError) as exc:
                raise ReviewedConversionError(
                    f"{label} does not exist: {pointer}"
                ) from exc
        else:
            raise ReviewedConversionError(f"{label} does not exist: {pointer}")
    return current


def _without_key(value: Mapping[str, Any], key: str) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result.pop(key, None)
    return result


def reviewer_evidence_sha256(evidence: Mapping[str, Any]) -> str:
    """Hash one complete reviewer evidence entry, excluding its self-hash."""

    return sha256_json(_without_key(evidence, "evidence_sha256"))


def reviewer_decision_signature(
    decision: Mapping[str, Any], *, secret: str
) -> str:
    """Return the local HMAC over the decision excluding only signature value."""

    if not isinstance(secret, str) or not secret:
        raise ReviewedConversionError("reviewer signing secret must be non-empty")
    payload = copy.deepcopy(dict(decision))
    signature = payload.get("signature")
    if isinstance(signature, dict):
        signature.pop("value", None)
    digest = hmac.new(
        secret.encode("utf-8"),
        canonical_json(payload),
        hashlib.sha256,
    ).hexdigest()
    return f"hmac-sha256:{digest}"


def _reject_authorization_claims(value: Any, path: str = "$") -> None:
    forbidden = {
        "acquisition_approval",
        "acquisition_authorization",
        "annotation_approval",
        "annotation_authorization",
        "release_approval",
        "release_authorization",
    }
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key.lower() in forbidden and item not in (None, False, "none"):
                raise ReviewedConversionError(
                    f"reviewer decision may not grant authorization at {path}.{key}"
                )
            _reject_authorization_claims(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_authorization_claims(item, f"{path}[{index}]")


def parse_reviewer_decision(value: Any) -> ReviewerDecision:
    """Parse the versioned decision object while retaining extension fields."""

    root = _object(value, "reviewer decision")
    try:
        from jsonschema import Draft202012Validator

        errors = sorted(
            Draft202012Validator(REVIEWER_DECISION_SCHEMA).iter_errors(root),
            key=lambda error: tuple(str(part) for part in error.absolute_path),
        )
    except ImportError:
        errors = []
    if errors:
        error = errors[0]
        location = "/" + "/".join(str(part) for part in error.absolute_path)
        raise ReviewedConversionError(
            f"reviewer decision schema violation at {location or '/'}: "
            f"{error.message}"
        )
    _reject_authorization_claims(root)
    if root.get("decision_version") != REVIEWER_DECISION_VERSION:
        raise ReviewedConversionError(
            f"unsupported reviewer decision version: {root.get('decision_version')!r}"
        )
    if root.get("artifact_class") != "reviewed_candidate_decision":
        raise ReviewedConversionError(
            "reviewer decision artifact_class must be reviewed_candidate_decision"
        )
    imported_hash = _text(
        root.get("imported_inspection_sha256"), "imported_inspection_sha256"
    ).lower()
    if not _SHA256_RE.fullmatch(imported_hash):
        raise ReviewedConversionError(
            "imported_inspection_sha256 must be a SHA-256 digest"
        )
    output_mode = _text(root.get("output_mode"), "output_mode")
    if output_mode not in {"exploratory", "freeze_ready"}:
        raise ReviewedConversionError(
            "output_mode must be exploratory or freeze_ready"
        )
    selected_ids = _unique_texts(
        root.get("selected_source_record_ids"), "selected_source_record_ids"
    )

    evidence: list[ReviewerEvidence] = []
    evidence_ids: set[str] = set()
    for index, raw in enumerate(
        _array(root.get("reviewer_evidence"), "reviewer_evidence")
    ):
        item = _object(raw, f"reviewer_evidence[{index}]")
        evidence_id = _text(item.get("evidence_id"), "reviewer evidence ID")
        if evidence_id in evidence_ids:
            raise ReviewedConversionError(
                f"duplicate reviewer evidence ID: {evidence_id}"
            )
        evidence_ids.add(evidence_id)
        claims = _object(item.get("claims"), f"reviewer evidence {evidence_id} claims")
        evidence.append(
            ReviewerEvidence(
                evidence_id=evidence_id,
                evidence_type=_text(
                    item.get("evidence_type"), "reviewer evidence type"
                ),
                source=_text(item.get("source"), "reviewer evidence source"),
                observed_at=_text(
                    item.get("observed_at"), "reviewer evidence observed_at"
                ),
                claims=copy.deepcopy(claims),
                evidence_sha256=(
                    _text(item["evidence_sha256"], "reviewer evidence SHA-256").lower()
                    if item.get("evidence_sha256") is not None
                    else None
                ),
                extensions={
                    key: copy.deepcopy(item[key])
                    for key in item
                    if key
                    not in {
                        "evidence_id",
                        "evidence_type",
                        "source",
                        "observed_at",
                        "claims",
                        "evidence_sha256",
                    }
                },
            )
        )

    candidates: list[ReviewedCandidateDecision] = []
    for index, raw in enumerate(
        _array(root.get("candidate_decisions"), "candidate_decisions")
    ):
        item = _object(raw, f"candidate_decisions[{index}]")
        source_ids = _unique_texts(
            item.get("source_record_ids"),
            f"candidate_decisions[{index}].source_record_ids",
        )
        candidate = copy.deepcopy(
            _object(item.get("candidate"), f"candidate_decisions[{index}].candidate")
        )
        raw_claims = _object(
            item.get("claim_evidence"),
            f"candidate_decisions[{index}].claim_evidence",
        )
        claim_evidence: dict[str, tuple[dict[str, Any], ...]] = {}
        for pointer, refs in raw_claims.items():
            if not isinstance(pointer, str) or not pointer.startswith("/"):
                raise ReviewedConversionError(
                    f"candidate_decisions[{index}] claim path must be a JSON pointer"
                )
            claim_evidence[pointer] = tuple(
                copy.deepcopy(
                    _object(ref, f"claim evidence reference for {pointer}")
                )
                for ref in _array(refs, f"claim evidence references for {pointer}")
            )
        duration_provenance = copy.deepcopy(
            _object(
                item.get("duration_provenance"),
                f"candidate_decisions[{index}].duration_provenance",
            )
        )
        _text(
            duration_provenance.get("method"),
            f"candidate_decisions[{index}].duration_provenance.method",
        )
        _text(
            duration_provenance.get("source_description"),
            f"candidate_decisions[{index}].duration_provenance.source_description",
        )
        candidates.append(
            ReviewedCandidateDecision(
                source_record_ids=source_ids,
                candidate=candidate,
                claim_evidence=claim_evidence,
                duration_provenance=duration_provenance,
                extensions={
                    key: copy.deepcopy(item[key])
                    for key in item
                    if key not in _CANDIDATE_DECISION_KEYS
                },
            )
        )
    if not candidates:
        raise ReviewedConversionError("candidate_decisions must not be empty")

    reviewer_raw = _object(root.get("reviewer"), "reviewer")
    reviewer = ReviewerIdentity(
        reviewer_id=_text(reviewer_raw.get("reviewer_id"), "reviewer_id"),
        role=_text(reviewer_raw.get("role"), "reviewer role"),
        reviewed_at=_text(reviewer_raw.get("reviewed_at"), "reviewed_at"),
        attestation=_text(reviewer_raw.get("attestation"), "reviewer attestation"),
        extensions={
            key: copy.deepcopy(reviewer_raw[key])
            for key in reviewer_raw
            if key not in _REVIEWER_KEYS
        },
    )
    signature_raw = _object(root.get("signature"), "signature")
    signature = {
        "algorithm": _text(signature_raw.get("algorithm"), "signature algorithm"),
        "key_id": _text(signature_raw.get("key_id"), "signature key_id"),
        "value": _text(signature_raw.get("value"), "signature value").lower(),
    }
    return ReviewerDecision(
        decision_version=REVIEWER_DECISION_VERSION,
        imported_inspection_sha256=imported_hash,
        output_mode=output_mode,
        selected_source_record_ids=selected_ids,
        reviewer_evidence=tuple(evidence),
        candidate_decisions=tuple(candidates),
        reviewer=reviewer,
        decision_expires_at=_text(
            root.get("decision_expires_at"), "decision_expires_at"
        ),
        signature=signature,
        extensions={
            key: copy.deepcopy(root[key]) for key in root if key not in _ROOT_KEYS
        },
    )


def _registry_key(
    registry: Any, *, reviewer_id: str, role: str, key_id: str
) -> str:
    root = _object(registry, "reviewer registry")
    if root.get("registry_version") != REVIEWER_REGISTRY_VERSION:
        raise ReviewedConversionError("unsupported reviewer registry version")
    reviewers = _array(root.get("reviewers"), "reviewer registry reviewers")
    matches = [
        _object(item, "reviewer registry entry")
        for item in reviewers
        if isinstance(item, dict) and item.get("reviewer_id") == reviewer_id
    ]
    if len(matches) != 1:
        raise ReviewedConversionError(
            f"reviewer is not uniquely recognized: {reviewer_id}"
        )
    reviewer = matches[0]
    roles = _array(reviewer.get("roles"), f"roles for reviewer {reviewer_id}")
    if role not in roles:
        raise ReviewedConversionError(
            f"reviewer {reviewer_id} is not authorized for role {role}"
        )
    keys = [
        _object(item, "reviewer key")
        for item in _array(reviewer.get("keys"), f"keys for reviewer {reviewer_id}")
        if isinstance(item, dict) and item.get("key_id") == key_id
    ]
    if len(keys) != 1:
        raise ReviewedConversionError(
            f"reviewer signing key is not recognized: {key_id}"
        )
    key = keys[0]
    if key.get("algorithm") != "hmac-sha256":
        raise ReviewedConversionError("reviewer key algorithm must be hmac-sha256")
    return _text(key.get("secret"), "reviewer signing secret")


def _verify_signature(
    raw_decision: Mapping[str, Any],
    parsed: ReviewerDecision,
    reviewer_registry: Any,
) -> None:
    if parsed.signature["algorithm"] != "hmac-sha256":
        raise ReviewedConversionError("decision signature algorithm must be hmac-sha256")
    if not _HMAC_RE.fullmatch(parsed.signature["value"]):
        raise ReviewedConversionError("decision is unsigned or has a malformed signature")
    secret = _registry_key(
        reviewer_registry,
        reviewer_id=parsed.reviewer.reviewer_id,
        role=parsed.reviewer.role,
        key_id=parsed.signature["key_id"],
    )
    expected = reviewer_decision_signature(raw_decision, secret=secret)
    if not hmac.compare_digest(expected, parsed.signature["value"]):
        raise ReviewedConversionError("reviewer decision signature verification failed")


def _verify_importer_artifact(imported: Any, expected_hash: str) -> dict[str, Any]:
    artifact = _object(imported, "imported inspection")
    if artifact.get("artifact_class") != "metadata_reconnaissance_inspection":
        raise ReviewedConversionError(
            "input is not a metadata_reconnaissance_inspection"
        )
    claimed = artifact.get("inspection_sha256")
    if not isinstance(claimed, str) or not _SHA256_RE.fullmatch(claimed.lower()):
        raise ReviewedConversionError("importer artifact has no valid inspection_sha256")
    computed = sha256_json(_without_key(artifact, "inspection_sha256"))
    if not hmac.compare_digest(computed, claimed.lower()):
        raise ReviewedConversionError(
            "importer artifact hash verification failed; artifact is tampered"
        )
    if not hmac.compare_digest(computed, expected_hash):
        raise ReviewedConversionError(
            "reviewer decision does not bind this exact importer artifact hash"
        )
    if artifact.get("network_access_performed") is not False:
        raise ReviewedConversionError(
            "importer artifact must attest network_access_performed=false"
        )
    if artifact.get("contains_media") is not False:
        raise ReviewedConversionError("importer artifact must contain no media")
    if artifact.get("acquisition_authorization") != "none":
        raise ReviewedConversionError(
            "importer artifact must grant no acquisition authorization"
        )
    return artifact


def _record_indexes(
    artifact: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    records: dict[str, dict[str, Any]] = {}
    for raw in _array(artifact.get("records"), "imported records"):
        record = _object(raw, "imported record")
        record_id = _text(record.get("record_id"), "imported record_id")
        if record_id in records:
            raise ReviewedConversionError(
                f"importer artifact contains duplicate record ID: {record_id}"
            )
        records[record_id] = record
    source_files: dict[str, dict[str, Any]] = {}
    for raw in _array(artifact.get("source_files"), "imported source_files"):
        source = _object(raw, "imported source file")
        source_id = _text(source.get("source_file_id"), "source_file_id")
        if source_id in source_files:
            raise ReviewedConversionError(
                f"importer artifact contains duplicate source file ID: {source_id}"
            )
        source_files[source_id] = source
    return records, source_files


def _verify_reviewer_evidence(
    raw_decision: Mapping[str, Any],
    parsed: ReviewerDecision,
    *,
    freeze_ready: bool,
    reviewed_at: datetime,
) -> dict[str, dict[str, Any]]:
    raw_items = _array(raw_decision.get("reviewer_evidence"), "reviewer_evidence")
    by_id: dict[str, dict[str, Any]] = {}
    for raw, item in zip(raw_items, parsed.reviewer_evidence, strict=True):
        raw_item = _object(raw, f"reviewer evidence {item.evidence_id}")
        observed_at = _parse_timestamp(
            item.observed_at, f"reviewer evidence {item.evidence_id} observed_at"
        )
        if observed_at > reviewed_at:
            raise ReviewedConversionError(
                f"reviewer evidence postdates the review: {item.evidence_id}"
            )
        if item.evidence_sha256 is not None:
            if not _SHA256_RE.fullmatch(item.evidence_sha256):
                raise ReviewedConversionError(
                    f"invalid reviewer evidence hash: {item.evidence_id}"
                )
            expected = reviewer_evidence_sha256(raw_item)
            if not hmac.compare_digest(expected, item.evidence_sha256):
                raise ReviewedConversionError(
                    f"reviewer evidence hash mismatch: {item.evidence_id}"
                )
        elif freeze_ready:
            raise ReviewedConversionError(
                f"freeze-ready output requires immutable reviewer evidence: "
                f"{item.evidence_id}"
            )
        by_id[item.evidence_id] = raw_item
    return by_id


def _verify_claims(
    decision: ReviewedCandidateDecision,
    records: Mapping[str, dict[str, Any]],
    evidence: Mapping[str, dict[str, Any]],
) -> None:
    candidate = decision.candidate
    required_paths = {f"/{key}" for key in candidate}
    required_paths.add("/duration_provenance")
    supplied_paths = set(decision.claim_evidence)
    missing = sorted(required_paths - supplied_paths)
    extra = sorted(supplied_paths - required_paths)
    if missing:
        raise ReviewedConversionError(
            "candidate has claims without evidence references: " + ", ".join(missing)
        )
    if extra:
        raise ReviewedConversionError(
            "claim_evidence contains unrecognized candidate paths: "
            + ", ".join(extra)
        )
    claim_document = {
        **candidate,
        "duration_provenance": decision.duration_provenance,
    }
    for pointer in sorted(required_paths):
        expected_value = _json_pointer(
            claim_document, pointer, f"candidate claim {pointer}"
        )
        refs = decision.claim_evidence[pointer]
        if not refs:
            raise ReviewedConversionError(
                f"candidate claim has no evidence references: {pointer}"
            )
        for ref in refs:
            kind = _text(ref.get("kind"), f"evidence kind for {pointer}")
            if kind == "imported_record":
                record_id = _text(
                    ref.get("record_id"), f"imported record reference for {pointer}"
                )
                if record_id not in decision.source_record_ids:
                    raise ReviewedConversionError(
                        f"claim {pointer} cites an unselected imported record: "
                        f"{record_id}"
                    )
                source = records.get(record_id)
                if source is None:
                    raise ReviewedConversionError(
                        f"claim {pointer} cites unrecognized record ID: {record_id}"
                    )
                actual = _json_pointer(
                    source,
                    _text(ref.get("pointer"), f"imported pointer for {pointer}"),
                    f"imported evidence for {pointer}",
                )
            elif kind == "reviewer_evidence":
                evidence_id = _text(
                    ref.get("evidence_id"), f"reviewer evidence ID for {pointer}"
                )
                source = evidence.get(evidence_id)
                if source is None:
                    raise ReviewedConversionError(
                        f"claim {pointer} cites unrecognized reviewer evidence: "
                        f"{evidence_id}"
                    )
                claim_path = ref.get("claim_path", pointer)
                actual = _json_pointer(
                    _object(source.get("claims"), "reviewer evidence claims"),
                    _text(claim_path, f"reviewer claim path for {pointer}"),
                    f"reviewer evidence {evidence_id}",
                )
            else:
                raise ReviewedConversionError(
                    f"claim {pointer} has unsupported evidence kind: {kind}"
                )
            if actual != expected_value:
                raise ReviewedConversionError(
                    f"evidence does not support candidate claim {pointer}"
                )


def _source_identity_for_record(
    record: Mapping[str, Any],
    source_files: Mapping[str, dict[str, Any]],
) -> tuple[str, str, str]:
    source = _object(record.get("source"), "record source")
    source_file_id = _text(source.get("source_file_id"), "record source_file_id")
    source_file = source_files.get(source_file_id)
    if source_file is None:
        raise ReviewedConversionError(
            f"record cites missing source file ID: {source_file_id}"
        )
    repository = _object(source_file.get("repository"), "source repository")
    revision = _object(
        source_file.get("repository_revision"), "source repository revision"
    )
    return (
        _text(repository.get("provider"), "source repository provider"),
        _text(repository.get("repository_id"), "source repository ID"),
        _text(revision.get("value"), "source repository revision value"),
    )


def _check_license_resolution(candidate: Mapping[str, Any]) -> None:
    state = candidate.get("license_resolution_status")
    evidence = candidate.get("license_evidence")
    if not isinstance(evidence, list):
        raise ReviewedConversionError("candidate license_evidence must be an array")
    signatures = {
        (
            item.get("artifact_class"),
            item.get("name"),
            item.get("version"),
            item.get("url"),
            item.get("scope"),
        )
        for item in evidence
        if isinstance(item, dict)
    }
    if len(signatures) != len(evidence):
        raise ReviewedConversionError("candidate license evidence entries must be objects")
    if state == "consistent" and len(signatures) != 1:
        raise ReviewedConversionError(
            "consistent license resolution conflicts with cited license evidence"
        )
    if state == "conflicting" and len(signatures) < 2:
        raise ReviewedConversionError(
            "conflicting license resolution requires distinct license evidence"
        )


def _freeze_reasons(
    artifact: Mapping[str, Any],
    candidates: Sequence[NormalizedCandidate],
) -> list[str]:
    reasons: set[str] = set()
    if artifact.get("promotion_status") != "promoted":
        reasons.add("importer_artifact_not_promoted")
    for candidate in candidates:
        if immutable_revision(candidate.revision) is None:
            reasons.add("mutable_or_unresolved_revision")
        if candidate.identity_resolution_status != "resolved":
            reasons.add("source_identity_not_resolved")
        if any(
            value is None
            for value in (
                candidate.has_video,
                candidate.has_audio,
                candidate.has_speech,
                candidate.has_ambient_audio,
            )
        ):
            reasons.add("media_facts_incomplete")
        if candidate.duration_s <= 0:
            reasons.add("duration_not_positive")
        if candidate.license_resolution_status != "consistent":
            reasons.add("license_evidence_not_consistently_resolved")
        elif any(
            not evidence.is_complete
            or immutable_revision(evidence.observed_revision) is None
            for evidence in candidate.license_evidence
        ):
            reasons.add("license_evidence_not_complete_or_immutable")
        if candidate.media_rights_status == "unknown_hold":
            reasons.add("media_rights_unknown")
        if any(
            not value or "unknown" in value.lower() or "unresolved" in value.lower()
            for value in (
                candidate.technical_access_status,
                candidate.access_gate,
                candidate.payload_state,
            )
        ):
            reasons.add("technical_access_incomplete")
    return sorted(reasons)


def convert_reviewed_candidates(
    imported_inspection: Any,
    reviewer_decision: Any,
    reviewer_registry: Any,
    *,
    as_of: datetime | None = None,
    max_decision_age: timedelta = timedelta(days=30),
) -> dict[str, Any]:
    """Convert one exact importer artifact under a signed local decision."""

    if max_decision_age <= timedelta(0):
        raise ReviewedConversionError("max_decision_age must be positive")
    raw_decision = _object(reviewer_decision, "reviewer decision")
    parsed = parse_reviewer_decision(raw_decision)
    _verify_signature(raw_decision, parsed, reviewer_registry)
    artifact = _verify_importer_artifact(
        imported_inspection, parsed.imported_inspection_sha256
    )

    now = (as_of or datetime.now(timezone.utc)).astimezone(timezone.utc)
    reviewed_at = _parse_timestamp(parsed.reviewer.reviewed_at, "reviewed_at")
    expires_at = _parse_timestamp(parsed.decision_expires_at, "decision_expires_at")
    if reviewed_at > now:
        raise ReviewedConversionError("reviewer decision timestamp is in the future")
    if expires_at <= reviewed_at:
        raise ReviewedConversionError("decision_expires_at must follow reviewed_at")
    if now >= expires_at or now - reviewed_at > max_decision_age:
        raise ReviewedConversionError("reviewer decision is stale")
    if parsed.reviewer.attestation != REQUIRED_REVIEWER_ATTESTATION:
        raise ReviewedConversionError("reviewer attestation is missing or not exact")

    records, source_files = _record_indexes(artifact)
    unknown_selected = sorted(set(parsed.selected_source_record_ids) - set(records))
    if unknown_selected:
        raise ReviewedConversionError(
            "selected source record IDs are unrecognized: "
            + ", ".join(unknown_selected)
        )
    used_ids = [
        record_id
        for candidate in parsed.candidate_decisions
        for record_id in candidate.source_record_ids
    ]
    if len(used_ids) != len(set(used_ids)):
        raise ReviewedConversionError(
            "source record IDs may not be duplicated across candidate decisions"
        )
    selected_set = set(parsed.selected_source_record_ids)
    used_set = set(used_ids)
    if used_set != selected_set:
        missing = sorted(selected_set - used_set)
        extra = sorted(used_set - selected_set)
        detail = []
        if missing:
            detail.append("missing from candidate decisions: " + ", ".join(missing))
        if extra:
            detail.append("not selected: " + ", ".join(extra))
        raise ReviewedConversionError(
            "selected source record IDs are not exact (" + "; ".join(detail) + ")"
        )

    freeze_requested = parsed.output_mode == "freeze_ready"
    evidence = _verify_reviewer_evidence(
        raw_decision,
        parsed,
        freeze_ready=freeze_requested,
        reviewed_at=reviewed_at,
    )
    normalized: list[NormalizedCandidate] = []
    source_identities: set[tuple[str, str, str]] = set()
    raw_candidate_items = _array(
        raw_decision.get("candidate_decisions"), "candidate_decisions"
    )
    for index, (item, raw_item) in enumerate(
        zip(parsed.candidate_decisions, raw_candidate_items, strict=True)
    ):
        _verify_claims(item, records, evidence)
        _check_license_resolution(item.candidate)
        known_candidate = {
            key: copy.deepcopy(value)
            for key, value in item.candidate.items()
            if key in _NORMALIZED_FIELDS
        }
        unknown_candidate = {
            key: copy.deepcopy(value)
            for key, value in item.candidate.items()
            if key not in _NORMALIZED_FIELDS
        }
        if known_candidate.get("episode_access_class") is not None:
            raise ReviewedConversionError(
                "reviewed conversion cannot assign an episode release access class"
            )
        try:
            candidate = NormalizedCandidate.from_dict(known_candidate)
        except (TypeError, ValueError, KeyError) as exc:
            raise ReviewedConversionError(
                f"candidate_decisions[{index}] is not a NormalizedCandidate: {exc}"
            ) from exc
        identities = {
            _source_identity_for_record(records[record_id], source_files)
            for record_id in item.source_record_ids
        }
        expected_identity = (
            candidate.provider,
            candidate.repository_id,
            candidate.revision,
        )
        if identities != {expected_identity}:
            raise ReviewedConversionError(
                f"candidate {candidate.source_id} repository/revision does not "
                "match every selected imported record"
            )
        source_identities.add(expected_identity)
        if freeze_requested and immutable_revision(candidate.revision) is None:
            raise ReviewedConversionError(
                f"freeze-ready candidate has mutable revision: {candidate.revision}"
            )

        source_metadata = copy.deepcopy(candidate.source_metadata)
        selected_source_file_ids = sorted(
            {
                _text(
                    _object(records[record_id].get("source"), "record source").get(
                        "source_file_id"
                    ),
                    "record source_file_id",
                )
                for record_id in item.source_record_ids
            }
        )
        source_metadata["reviewed_conversion"] = {
            "source_record_ids": list(item.source_record_ids),
            "imported_records": [
                copy.deepcopy(records[record_id])
                for record_id in item.source_record_ids
            ],
            "imported_source_files": [
                copy.deepcopy(source_files[source_file_id])
                for source_file_id in selected_source_file_ids
            ],
            "duration_provenance": copy.deepcopy(item.duration_provenance),
            "reviewer_evidence_ids": sorted(
                {
                    ref["evidence_id"]
                    for refs in item.claim_evidence.values()
                    for ref in refs
                    if ref.get("kind") == "reviewer_evidence"
                    and isinstance(ref.get("evidence_id"), str)
                }
            ),
            "candidate_unknown_fields": unknown_candidate,
            "candidate_decision_extensions": copy.deepcopy(item.extensions),
            "raw_candidate_decision": copy.deepcopy(raw_item),
        }
        candidate_data = candidate.to_dict()
        candidate_data.pop("upstream_id", None)
        candidate_data["source_metadata"] = source_metadata
        normalized.append(NormalizedCandidate.from_dict(candidate_data))

    if len(source_identities) != 1:
        raise ReviewedConversionError(
            "one candidate inspection may bind only one provider/repository/revision"
        )
    provider, repository_id, revision = next(iter(source_identities))
    reasons = _freeze_reasons(artifact, normalized)
    if freeze_requested and reasons:
        raise ReviewedConversionError(
            "freeze-ready output lacks complete immutable evidence: "
            + ", ".join(reasons)
        )
    freeze_ready = freeze_requested and not reasons
    if not freeze_requested:
        reasons = sorted(set(reasons) | {"exploratory_mode_requested"})

    raw_evidence = copy.deepcopy(
        _array(raw_decision.get("reviewer_evidence"), "reviewer_evidence")
    )
    decision_hash = sha256_json(raw_decision)
    output: dict[str, Any] = {
        "inspection_version": REVIEWED_CANDIDATE_INSPECTION_VERSION,
        "artifact_class": "reviewed_candidate_inspection",
        "conversion_version": REVIEWED_CANDIDATE_INSPECTION_VERSION,
        "provider": provider,
        "repository_id": repository_id,
        "revision": revision,
        # Selection binds this exact complete reconnaissance artifact, not an
        # individual row or an unverified upstream URL.
        "snapshot_sha256": parsed.imported_inspection_sha256,
        "imported_inspection": {
            "artifact_class": artifact["artifact_class"],
            "inspection_version": artifact.get("inspection_version"),
            "inspection_sha256": parsed.imported_inspection_sha256,
        },
        "reviewer_decision": {
            "decision_version": parsed.decision_version,
            "decision_sha256": decision_hash,
            "reviewer_id": parsed.reviewer.reviewer_id,
            "role": parsed.reviewer.role,
            "reviewed_at": parsed.reviewer.reviewed_at,
            "decision_expires_at": parsed.decision_expires_at,
            "attestation": parsed.reviewer.attestation,
            "signature": copy.deepcopy(parsed.signature),
        },
        "reviewer_evidence": raw_evidence,
        "selected_source_record_ids": list(parsed.selected_source_record_ids),
        "candidate_count": len(normalized),
        "candidates": [candidate.to_dict() for candidate in normalized],
        "freeze_ready": freeze_ready,
        "freeze_readiness": {
            "state": "freeze_ready" if freeze_ready else "exploratory_non_freezeable",
            "reasons": reasons,
        },
        "network_access_performed": False,
        "contains_media": False,
        "acquisition_authorization": "none",
        "annotation_authorization": "none",
        "release_authorization": "none",
        "preserved_unknown_fields": {
            "reviewer_decision": copy.deepcopy(parsed.extensions),
            "reviewer": copy.deepcopy(parsed.reviewer.extensions),
            "signature": {
                key: copy.deepcopy(value)
                for key, value in _object(
                    raw_decision.get("signature"), "signature"
                ).items()
                if key not in _SIGNATURE_KEYS
            },
            "imported_inspection": {
                key: copy.deepcopy(artifact[key])
                for key in artifact
                if key not in _IMPORTER_ROOT_KEYS
            },
        },
    }
    output["conversion_sha256"] = sha256_json(output)
    return output
