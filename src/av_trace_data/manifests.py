"""Fail-closed draft acquisition manifests derived from metadata only."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from .errors import ManifestDraftError
from .io import sha256_json
from .models import NormalizedCandidate

_SAFE_ID = re.compile(r"[^A-Za-z0-9._:-]+")
_HOLD = "unknown_hold"


def _id(value: str) -> str:
    result = _SAFE_ID.sub("-", value).strip("-._:")
    if not result:
        raise ManifestDraftError("source identity cannot be converted to a manifest ID")
    return result[:128]


def _evidence_uri(candidate: NormalizedCandidate) -> str:
    for item in candidate.license_evidence:
        if item.url:
            return item.url
    repository_url = candidate.source_metadata.get("repository_url")
    if isinstance(repository_url, str) and repository_url:
        return repository_url
    return candidate.canonical_url


def draft_acquisition_manifest(
    candidate: NormalizedCandidate,
    *,
    created_by: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Create a schema-shaped metadata-only draft.

    Reconnaissance license/terms records are hashed into supporting evidence,
    but are not copied into a purported asset-level grant.  Every legal
    decision remains ``unknown_hold``.
    """

    if not candidate.source_id:
        raise ManifestDraftError("dataset-local source identity is required")
    if (
        candidate.identity_resolution_status != "resolved"
        or not candidate.canonical_identity
    ):
        raise ManifestDraftError("a resolved namespaced upstream identity is required")
    if not candidate.revision:
        raise ManifestDraftError("a pinned source revision is required")
    unknown_streams = [
        name
        for name in ("has_video", "has_audio", "has_speech", "has_ambient_audio")
        if getattr(candidate, name) is None
    ]
    if unknown_streams:
        raise ManifestDraftError(
            "cannot assert verified media fields from unknown metadata: "
            + ", ".join(unknown_streams)
        )
    if candidate.has_video is not True or candidate.has_audio is not True:
        raise ManifestDraftError("draft manifests require verified video and audio")
    timestamp = created_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    asset_id = _id(f"{candidate.dataset_id}:{candidate.source_id}")
    dataset_id = _id(candidate.dataset_id)
    actor = _id(created_by)
    evidence = {
        "candidate": candidate.to_dict(),
        "notice": (
            "Release-level license/terms evidence is not asset-level rights "
            "approval. All decisions remain unknown_hold pending human review."
        ),
    }
    evidence_hash = sha256_json(evidence)
    evidence_uri = _evidence_uri(candidate)
    evidence_count = len(candidate.license_evidence)
    evidence_summary = (
        f"{evidence_count} reconnaissance license/terms record(s); resolution "
        f"status={candidate.license_resolution_status}; media rights "
        f"status={candidate.media_rights_status}. Not an asset-level grant."
    )
    source_revision = candidate.revision
    return {
        "manifest_version": "0.2.0",
        "manifest_revision": f"metadata-draft-{source_revision}",
        "asset_id": asset_id,
        "dataset_id": dataset_id,
        "source": {
            "canonical_url": candidate.canonical_url,
            "source_identifier": candidate.canonical_identity,
            "source_revision": source_revision,
            "publisher": candidate.publisher,
            "rightsholder_or_status": candidate.rightsholder_or_status or _HOLD,
            "source_family": candidate.source_family,
        },
        "acquisition": {
            "status": _HOLD,
            "method": "none",
            "authority_basis": (
                "Metadata discovery only. No reconnaissance evidence was treated "
                "as asset-level acquisition authority."
            ),
            "authority_evidence_uri": evidence_uri,
            "authority_evidence_hash": evidence_hash,
            "planned_or_actual_at": timestamp,
        },
        "integrity": {
            "content_hash_plan": "sha256_of_exact_acquired_bytes",
            "content_sha256": None,
            "byte_size": None,
            "probe_version": "not_run_metadata_only",
        },
        "media": {
            "duration_s": candidate.duration_s,
            "has_video": candidate.has_video,
            "has_audio": candidate.has_audio,
            "has_speech": candidate.has_speech,
            "has_ambient_audio": candidate.has_ambient_audio,
            "embedded_content_reviewed": False,
        },
        "rights": {
            "rights_decision_id": _id(f"rights:{asset_id}:draft"),
            "copyright_basis": _HOLD,
            "acquisition_authority": _HOLD,
            "local_processing_authority": _HOLD,
            "license_or_grant": {
                "name": "UNRESOLVED_RECONNAISSANCE_EVIDENCE",
                "version": "not_asset_reviewed",
                "licensor_or_grantor": "unresolved",
                "uri": evidence_uri,
                "agreement_id": None,
                "scope": evidence_summary,
            },
            "evidence_snapshot": {
                "captured_at": timestamp,
                "uri": evidence_uri,
                "sha256": evidence_hash,
            },
            "decisions": {
                "acquisition": _HOLD,
                "processing": _HOLD,
                "derivative_release": _HOLD,
                "annotation_release": _HOLD,
                "transcript_release": _HOLD,
                "raw_media_release": _HOLD,
                "commercial_use": _HOLD,
            },
            "embedded_components": {
                "music": _HOLD,
                "subtitles": _HOLD,
                "third_party_inserts": _HOLD,
                "logos_and_marks": _HOLD,
                "identifiable_people": _HOLD,
                "minors": _HOLD,
            },
            "review": {
                "reviewer_id": actor,
                "reviewed_at": timestamp,
                "jurisdiction": "not_reviewed",
                "outcome": _HOLD,
                "notes": (
                    "Automated metadata-only draft. Human asset-level rights review "
                    "and authority evidence are required."
                ),
            },
        },
        "privacy_safety": {
            "review_status": _HOLD,
            "reviewer_id": actor,
            "reviewed_at": timestamp,
            "contains_identifiable_people": False,
            "contains_minors": False,
            "contains_sensitive_content": False,
            "mitigations": ["Human privacy/safety review required before acquisition."],
        },
        "derived_artifacts": [],
        "audit": {
            "record_created_at": timestamp,
            "record_updated_at": timestamp,
            "created_by": actor,
            "updated_by": actor,
            "gate_status": "metadata_only",
            "change_log": [
                {
                    "changed_at": timestamp,
                    "changed_by": actor,
                    "summary": (
                        "Created fail-closed metadata-only draft from a pinned "
                        "snapshot and resolved namespaced identity; no acquisition "
                        "approval inferred."
                    ),
                }
            ],
        },
    }
