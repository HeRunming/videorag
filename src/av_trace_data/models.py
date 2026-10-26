"""Provider-neutral release and candidate records.

Reconnaissance records intentionally distinguish unknown facts from verified
absence.  They also keep technical access, media rights, and eventual episode
publication class separate: none of those fields implies another.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any

LEGACY_ACCESS_MODES = {
    "downloadable_redistributable_raw",
    "downloadable_annotation_only",
    "link_id_only",
    "gated_agreement",
    "unsuitable_too_risky",
}
# Retained as a public compatibility name.  New code should use
# ``technical_access_status`` plus the explicit access crosswalk in configs.py.
ACCESS_MODES = LEGACY_ACCESS_MODES

IDENTITY_RESOLUTION_STATUSES = {"resolved", "unresolved", "conflicting"}
LICENSE_RESOLUTION_STATUSES = {"consistent", "unresolved", "conflicting"}
MEDIA_RIGHTS_STATUSES = {"unknown_hold", "restricted", "asset_reviewed"}
EPISODE_ACCESS_CLASSES = {
    "public_core_redistributable",
    "restricted_compatibility",
}
LINEAGE_RELATIONS = {
    "same_asset",
    "derived_from",
    "segment_of",
    "reconstruction_of",
    "alternate_encode",
    "excerpt_of",
    "mapped_from",
}

_FULL_HEX_REVISION = re.compile(r"^[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?$")
_OBJECT_VERSION_REVISION = re.compile(
    r"^(?:versionId|generation):[A-Za-z0-9][A-Za-z0-9._~+/=-]{0,511}$"
)
_MUTABLE_REVISIONS = {"main", "master", "head", "latest"}
_UNRESOLVED_REVISION_TOKENS = {
    "",
    "unknown",
    "unresolved",
    "pending",
    "placeholder",
    "tbd",
    "todo",
    "none",
    "null",
    "n/a",
    "na",
}


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def immutable_revision(value: Any) -> str | None:
    """Return a normalized immutable source revision or ``None``.

    Promotion/freeze accepts full Git object IDs used by GitHub and Hugging
    Face (40- or 64-hex) plus explicitly typed immutable object-store
    version/generation IDs. Reconnaissance models deliberately do not call this
    validator, so unresolved observations can still be recorded.
    """

    if not isinstance(value, str):
        return None
    revision = value.strip()
    lowered = revision.lower()
    if (
        lowered in _MUTABLE_REVISIONS
        or lowered in _UNRESOLVED_REVISION_TOKENS
        or any(char.isspace() for char in revision)
    ):
        return None
    if _FULL_HEX_REVISION.fullmatch(revision):
        return revision.lower()
    if _OBJECT_VERSION_REVISION.fullmatch(revision):
        return revision
    return None


def is_immutable_revision(value: Any) -> bool:
    """Whether ``value`` is one supported, atomic immutable revision."""

    return immutable_revision(value) is not None


def require_immutable_revision(value: Any, *, label: str = "revision") -> str:
    """Normalize one immutable revision or raise a promotion/freeze error."""

    revision = immutable_revision(value)
    if revision is None:
        raise ValueError(
            f"{label} must be a full immutable Git/HF revision or a typed "
            "object-store versionId/generation"
        )
    return revision


@dataclass(frozen=True)
class LicenseEvidence:
    """One observed license/terms statement, never a rights decision.

    Fields other than ``source`` and ``artifact_class`` are nullable because a
    repository header, agreement notice, or card may expose only partial
    evidence during reconnaissance.
    """

    source: str
    artifact_class: str
    name: str | None = None
    version: str | None = None
    url: str | None = None
    scope: str | None = None
    observed_revision: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def is_complete(self) -> bool:
        return all((self.name, self.version, self.url, self.scope))

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "LicenseEvidence":
        if not isinstance(value, dict):
            raise TypeError("license evidence must be an object")
        source = _optional_string(value.get("source"))
        artifact_class = _optional_string(
            value.get("artifact_class") or value.get("applies_to_class")
        )
        if not source:
            raise ValueError("license evidence source is required")
        if not artifact_class:
            # Legacy records had free-text scope but no artifact class.  Treat
            # that as unresolved release-level evidence, never source media.
            artifact_class = "release_unspecified"
        return cls(
            source=source,
            artifact_class=artifact_class,
            name=_optional_string(value.get("name") or value.get("spdx_id") or value.get("id")),
            version=_optional_string(value.get("version") or value.get("revision")),
            url=_optional_string(value.get("url") or value.get("uri")),
            scope=_optional_string(value.get("scope") or value.get("applies_to")),
            observed_revision=_optional_string(value.get("observed_revision")),
        )


# Compatibility import for callers that used the old class name.  Its
# semantics are now evidence-only and its fields may be unknown.
LicenseMetadata = LicenseEvidence


@dataclass(frozen=True)
class NormalizedCandidate:
    dataset_id: str
    adapter_id: str
    provider: str
    repository_id: str
    source_id: str
    split: str
    duration_s: float
    canonical_url: str
    media_url: str | None
    has_video: bool | None
    has_audio: bool | None
    has_speech: bool | None
    has_ambient_audio: bool | None
    transcript_available: bool
    evidence_available: bool
    revision: str
    license_evidence: tuple[LicenseEvidence, ...]
    license_resolution_status: str
    technical_access_status: str
    access_gate: str
    payload_state: str
    media_rights_status: str
    source_family: str
    publisher: str
    rightsholder_or_status: str
    upstream_namespace: str | None
    upstream_asset_id: str | None
    identity_resolution_status: str
    parent_dataset_id: str | None = None
    parent_upstream_namespace: str | None = None
    parent_upstream_asset_id: str | None = None
    lineage_relation: str | None = None
    episode_access_class: str | None = None
    byte_size: int | None = None
    checksum: str | None = None
    fingerprint: str | None = None
    config: str | None = None
    title: str | None = None
    retrieval: dict[str, Any] = field(default_factory=dict)
    source_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("has_video", "has_audio", "has_speech", "has_ambient_audio"):
            if getattr(self, name) not in (True, False, None):
                raise ValueError(f"{name} must be true, false, or unknown")
        if self.identity_resolution_status not in IDENTITY_RESOLUTION_STATUSES:
            raise ValueError(
                f"invalid identity_resolution_status: {self.identity_resolution_status!r}"
            )
        if self.identity_resolution_status == "resolved" and not (
            self.upstream_namespace and self.upstream_asset_id
        ):
            raise ValueError(
                "resolved identity requires upstream_namespace and upstream_asset_id"
            )
        parent_values = (
            self.parent_upstream_namespace,
            self.parent_upstream_asset_id,
        )
        if any(parent_values) and not all(parent_values):
            raise ValueError(
                "parent_upstream_namespace and parent_upstream_asset_id must be paired"
            )
        if self.lineage_relation and self.lineage_relation not in LINEAGE_RELATIONS:
            raise ValueError(f"invalid lineage_relation: {self.lineage_relation!r}")
        if self.lineage_relation and not all(parent_values):
            raise ValueError("lineage_relation requires a complete parent identity")
        if all(parent_values) and not self.lineage_relation:
            raise ValueError("a parent identity requires lineage_relation")
        if self.license_resolution_status not in LICENSE_RESOLUTION_STATUSES:
            raise ValueError(
                f"invalid license_resolution_status: {self.license_resolution_status!r}"
            )
        if (
            self.license_resolution_status == "consistent"
            and not self.license_evidence
        ):
            raise ValueError("consistent license status requires evidence")
        if (
            self.license_resolution_status == "conflicting"
            and len(self.license_evidence) < 2
        ):
            raise ValueError("conflicting license status requires at least two records")
        if self.media_rights_status not in MEDIA_RIGHTS_STATUSES:
            raise ValueError(f"invalid media_rights_status: {self.media_rights_status!r}")
        if (
            self.episode_access_class is not None
            and self.episode_access_class not in EPISODE_ACCESS_CLASSES
        ):
            raise ValueError(f"invalid episode_access_class: {self.episode_access_class!r}")

    @property
    def canonical_identity(self) -> str | None:
        """Direct namespaced identity.

        Cross-release ancestry is represented separately and resolved by the
        selection lineage graph; this property never guesses a transitive root.
        """
        if self.identity_resolution_status != "resolved":
            return None
        if self.upstream_namespace and self.upstream_asset_id:
            return f"{self.upstream_namespace}:{self.upstream_asset_id}"
        return None

    @property
    def upstream_id(self) -> str | None:
        """Compatibility view, now always namespaced and never guessed."""

        return self.canonical_identity

    @property
    def access_mode(self) -> str:
        """Deprecated compatibility view of technical access only."""

        return self.technical_access_status

    @property
    def license(self) -> LicenseEvidence | None:
        """Compatibility view available only for one resolved evidence record."""

        if (
            self.license_resolution_status == "consistent"
            and len(self.license_evidence) == 1
        ):
            return self.license_evidence[0]
        return None

    def identity_keys(self) -> tuple[str, ...]:
        """All verified identity nodes used for lineage-aware deduplication."""

        if self.identity_resolution_status != "resolved":
            return ()
        keys: list[str] = []
        if self.upstream_namespace and self.upstream_asset_id:
            keys.append(f"{self.upstream_namespace}:{self.upstream_asset_id}")
        if self.parent_upstream_namespace and self.parent_upstream_asset_id:
            keys.append(
                f"{self.parent_upstream_namespace}:{self.parent_upstream_asset_id}"
            )
        return tuple(dict.fromkeys(keys))

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["license_evidence"] = [
            evidence.to_dict() for evidence in self.license_evidence
        ]
        # Keep a namespaced compatibility field for older plan readers.  It is
        # null when identity is unresolved; it never falls back to source_id.
        result["upstream_id"] = self.upstream_id
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "NormalizedCandidate":
        data = dict(value)
        evidence_raw = data.pop("license_evidence", None)
        legacy_license = data.pop("license", None)
        if evidence_raw is None:
            evidence_raw = [] if legacy_license is None else [legacy_license]
        if not isinstance(evidence_raw, (list, tuple)):
            raise TypeError("license_evidence must be an array")
        evidence: list[LicenseEvidence] = []
        for item in evidence_raw:
            if isinstance(item, LicenseEvidence):
                evidence.append(item)
            elif isinstance(item, dict):
                evidence.append(LicenseEvidence.from_dict(item))
            else:
                raise TypeError("license evidence entries must be objects")
        data["license_evidence"] = tuple(evidence)
        if "license_resolution_status" not in data:
            # A legacy singular license is evidence, not proof that conflicts
            # were checked or that asset rights were resolved.
            data["license_resolution_status"] = "unresolved"

        legacy_upstream_id = data.pop("upstream_id", None)
        if "upstream_asset_id" not in data:
            data["upstream_asset_id"] = _optional_string(legacy_upstream_id)
        if "upstream_namespace" not in data:
            data["upstream_namespace"] = None
        if "identity_resolution_status" not in data:
            # Reading remains possible, but an unnamespaced old identifier is
            # deliberately held as unresolved instead of being guessed.
            data["identity_resolution_status"] = "unresolved"

        legacy_access_mode = data.pop("access_mode", None)
        if "technical_access_status" not in data:
            data["technical_access_status"] = (
                f"legacy_unresolved:{legacy_access_mode}"
                if legacy_access_mode
                else "legacy_unresolved"
            )
        data.setdefault("access_gate", "unresolved")
        data.setdefault("payload_state", "unresolved")
        data.setdefault("media_rights_status", "unknown_hold")
        data.setdefault("episode_access_class", None)
        data.setdefault("parent_dataset_id", None)
        data.setdefault("parent_upstream_namespace", None)
        data.setdefault("parent_upstream_asset_id", None)
        data.setdefault("lineage_relation", None)
        return cls(**data)


@dataclass(frozen=True)
class InspectionResult:
    inspection_version: str
    adapter_id: str
    provider: str
    repository_id: str
    revision: str
    snapshot_sha256: str
    card: dict[str, Any]
    configs: tuple[dict[str, Any], ...]
    files: tuple[dict[str, Any], ...]
    candidates: tuple[NormalizedCandidate, ...]
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "inspection_version": self.inspection_version,
            "adapter_id": self.adapter_id,
            "provider": self.provider,
            "repository_id": self.repository_id,
            "revision": self.revision,
            "snapshot_sha256": self.snapshot_sha256,
            "card": self.card,
            "configs": list(self.configs),
            "files": list(self.files),
            "candidate_count": len(self.candidates),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "warnings": list(self.warnings),
        }
