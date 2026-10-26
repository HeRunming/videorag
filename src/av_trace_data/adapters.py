"""Metadata-only adapters for local release snapshots."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse

from .configs import ACCESS_GATES, PAYLOAD_STATES, AdapterConfig, access_crosswalk
from .errors import FixtureError
from .io import load_json, sha256_file
from .models import (
    IDENTITY_RESOLUTION_STATUSES,
    LICENSE_RESOLUTION_STATUSES,
    LINEAGE_RELATIONS,
    MEDIA_RIGHTS_STATUSES,
    InspectionResult,
    LicenseEvidence,
    NormalizedCandidate,
)

_MISSING = object()


class SourceAdapter(ABC):
    """Provider adapter boundary; implementations inspect metadata, never media."""

    provider: str

    def __init__(self, config: AdapterConfig):
        if config.provider != self.provider:
            raise ValueError(
                f"adapter provider {self.provider!r} does not match config "
                f"{config.provider!r}"
            )
        self.config = config

    @abstractmethod
    def inspect_fixture(self, path: str | Path) -> InspectionResult:
        """Inspect one local JSON snapshot without network access."""


def _first(mapping: Mapping[str, Any], names: Iterable[str], default: Any = _MISSING) -> Any:
    for name in names:
        if name in mapping and mapping[name] is not None:
            return mapping[name]
    if default is _MISSING:
        raise KeyError(next(iter(names), "field"))
    return default


def _required_text(mapping: Mapping[str, Any], names: tuple[str, ...], label: str) -> str:
    try:
        value = _first(mapping, names)
    except KeyError as exc:
        raise FixtureError(f"missing {label}") from exc
    text = str(value).strip()
    if not text:
        raise FixtureError(f"empty {label}")
    return text


def _optional_text(mapping: Mapping[str, Any], names: tuple[str, ...]) -> str | None:
    value = _first(mapping, names, None)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _bool(mapping: Mapping[str, Any], names: tuple[str, ...], default: bool | None) -> bool | None:
    value = _first(mapping, names, default)
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1", "available", "present", "verified_present"}:
            return True
        if normalized in {"false", "no", "0", "unavailable", "absent", "verified_absent"}:
            return False
        if normalized in {"unknown", "unverified", "unresolved", "not_checked"}:
            return None
    raise FixtureError(f"invalid boolean/unknown value {value!r} for {names[0]}")


def _duration_s(row: Mapping[str, Any]) -> float:
    if row.get("duration_s") is not None:
        value = row["duration_s"]
    elif row.get("duration_seconds") is not None:
        value = row["duration_seconds"]
    elif row.get("duration_minutes") is not None:
        value = float(row["duration_minutes"]) * 60.0
    elif row.get("duration_ms") is not None:
        value = float(row["duration_ms"]) / 1000.0
    else:
        raise FixtureError("candidate row is missing duration")
    if isinstance(value, bool):
        raise FixtureError("duration must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise FixtureError(f"invalid duration {value!r}") from exc
    if not math.isfinite(result) or result <= 0:
        raise FixtureError(f"duration must be finite and positive; found {value!r}")
    return result


def _uri(value: str, label: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise FixtureError(f"{label} must be an absolute HTTP(S) URL")
    return value


def _checksum(row: Mapping[str, Any]) -> str | None:
    value = _optional_text(row, ("checksum", "sha256", "content_sha256"))
    if value is None:
        return None
    if not value.startswith("sha256:") and len(value) == 64:
        value = "sha256:" + value.lower()
    if len(value) != 71 or not value.startswith("sha256:"):
        raise FixtureError(f"unsupported checksum format: {value!r}")
    try:
        int(value[7:], 16)
    except ValueError as exc:
        raise FixtureError(f"invalid SHA-256 checksum: {value!r}") from exc
    return value.lower()


def _list_of_dicts(value: Any, label: str) -> tuple[dict[str, Any], ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise FixtureError(f"{label} must be an array of objects")
    return tuple(dict(item) for item in value)


def _license_record(raw: Mapping[str, Any], source: str) -> LicenseEvidence:
    artifact_class = _optional_text(
        raw, ("artifact_class", "applies_to_class", "artifact_type")
    ) or "release_unspecified"
    url = _optional_text(raw, ("url", "uri"))
    if url is not None:
        url = _uri(url, "license evidence URL")
    return LicenseEvidence(
        source=source,
        artifact_class=artifact_class,
        name=_optional_text(raw, ("name", "spdx_id", "id")),
        version=_optional_text(raw, ("version", "revision")),
        url=url,
        scope=_optional_text(raw, ("scope", "applies_to")),
        observed_revision=_optional_text(
            raw, ("observed_revision", "evidence_revision")
        ),
    )


def _license_evidence(
    repository: Mapping[str, Any], card: Mapping[str, Any]
) -> tuple[tuple[LicenseEvidence, ...], str]:
    records: list[LicenseEvidence] = []
    explicit = repository.get("license_evidence")
    if explicit is not None:
        for item in _list_of_dicts(explicit, "repository.license_evidence"):
            source = _required_text(item, ("source",), "license evidence source")
            records.append(_license_record(item, source))
    else:
        # Safe legacy reading: preserve repository and card statements
        # separately instead of selecting one as authoritative.
        for container_name, container in (("repository", repository), ("card", card)):
            raw = container.get("license")
            if isinstance(raw, str):
                raw = {"name": raw}
            if isinstance(raw, Mapping):
                records.append(_license_record(raw, container_name))

    explicit_status = _optional_text(
        repository, ("license_resolution_status", "license_status")
    )
    if explicit_status is not None:
        status = explicit_status.lower()
        if status not in LICENSE_RESOLUTION_STATUSES:
            raise FixtureError(f"invalid license resolution status: {status!r}")
    elif not records:
        status = "unresolved"
    elif len(records) == 1:
        # One observed statement does not establish that conflicts were checked.
        status = "unresolved"
    else:
        normalized = {
            (
                item.name,
                item.version,
                item.url,
                item.scope,
                item.artifact_class,
            )
            for item in records
        }
        status = "consistent" if len(normalized) == 1 else "conflicting"
    normalized = {
        (
            item.name,
            item.version,
            item.url,
            item.scope,
            item.artifact_class,
        )
        for item in records
    }
    if status == "consistent":
        if not records:
            raise FixtureError("consistent license status requires evidence records")
        if len(normalized) != 1:
            raise FixtureError(
                "consistent license status contradicts differing evidence records"
            )
    if status == "conflicting":
        if len(records) < 2:
            raise FixtureError(
                "conflicting license status requires at least two records"
            )
        if len(normalized) < 2:
            raise FixtureError(
                "conflicting license status requires differing evidence records"
            )
    return tuple(records), status


def _access_state(
    repository: Mapping[str, Any], config: AdapterConfig
) -> tuple[str, str, str, str]:
    status = _optional_text(
        repository, ("technical_access_status", "access_status")
    )
    legacy_mode = _optional_text(repository, ("access_mode",))
    if status is None:
        if legacy_mode is not None:
            raise FixtureError(
                "legacy access_mode is ambiguous; technical_access_status is required"
            )
        status = config.technical_access_status
    try:
        mapped = access_crosswalk(status)
    except ValueError as exc:
        raise FixtureError(str(exc)) from exc
    access_gate_override = _optional_text(repository, ("access_gate",))
    payload_state_override = _optional_text(repository, ("payload_state",))
    if access_gate_override is not None and access_gate_override != mapped.access_gate:
        raise FixtureError(
            "access_gate conflicts with the audited technical-access crosswalk"
        )
    if (
        payload_state_override is not None
        and payload_state_override != mapped.payload_state
    ):
        raise FixtureError(
            "payload_state conflicts with the audited technical-access crosswalk"
        )
    access_gate = mapped.access_gate
    payload_state = mapped.payload_state
    if access_gate not in ACCESS_GATES:
        raise FixtureError(f"invalid access gate: {access_gate!r}")
    if payload_state not in PAYLOAD_STATES:
        raise FixtureError(f"invalid payload state: {payload_state!r}")
    rights = (
        _optional_text(repository, ("media_rights_status",))
        or config.media_rights_status
    )
    if rights not in MEDIA_RIGHTS_STATUSES:
        raise FixtureError(f"invalid media rights status: {rights!r}")
    return status, access_gate, payload_state, rights


def _identity(
    row: Mapping[str, Any],
) -> tuple[str | None, str | None, str, str | None, str | None, str | None, str | None]:
    namespace = _optional_text(
        row, ("upstream_namespace", "source_namespace", "canonical_namespace")
    )
    asset_id = _optional_text(
        row, ("upstream_asset_id", "original_video_id", "source_video_id")
    )
    status = _optional_text(
        row, ("identity_resolution_status", "identity_status")
    )
    if status is None:
        status = "resolved" if namespace and asset_id else "unresolved"
    status = status.lower()
    if status not in IDENTITY_RESOLUTION_STATUSES:
        raise FixtureError(f"invalid identity resolution status: {status!r}")
    if status == "resolved" and not (namespace and asset_id):
        raise FixtureError(
            "resolved identity requires upstream_namespace and upstream_asset_id"
        )

    parent_dataset_id = _optional_text(
        row, ("parent_dataset_id", "parent_dataset")
    )
    parent_namespace = _optional_text(
        row, ("parent_upstream_namespace", "parent_namespace")
    )
    parent_asset_id = _optional_text(
        row, ("parent_upstream_asset_id", "parent_asset_id")
    )
    relation = _optional_text(row, ("lineage_relation", "parent_relation"))
    if any((parent_namespace, parent_asset_id)) and not all(
        (parent_namespace, parent_asset_id)
    ):
        raise FixtureError("parent upstream namespace and asset ID must be paired")
    if relation is not None and relation not in LINEAGE_RELATIONS:
        raise FixtureError(f"invalid lineage relation: {relation!r}")
    if relation is not None and not (parent_namespace and parent_asset_id):
        raise FixtureError("lineage relation requires a complete parent identity")
    if parent_namespace and parent_asset_id and relation is None:
        raise FixtureError("parent identity requires lineage_relation")
    return (
        namespace,
        asset_id,
        status,
        parent_dataset_id,
        parent_namespace,
        parent_asset_id,
        relation,
    )


class _JSONSnapshotAdapter(SourceAdapter):
    """Shared normalization for repository snapshots with explicit row metadata."""

    def inspect_fixture(self, path: str | Path) -> InspectionResult:
        fixture_path = Path(path)
        payload = load_json(fixture_path)
        if not isinstance(payload, dict):
            raise FixtureError("snapshot root must be an object")
        provider = _required_text(payload, ("provider",), "provider")
        if provider != self.provider:
            raise FixtureError(f"expected provider {self.provider!r}; found {provider!r}")
        repository = payload.get("repository")
        if not isinstance(repository, dict):
            raise FixtureError("snapshot.repository must be an object")
        repository_id = _required_text(
            repository, ("id", "repo_id", "full_name"), "repository ID"
        )
        if repository_id != self.config.repository_id:
            raise FixtureError(
                f"snapshot repository {repository_id!r} does not match configured "
                f"{self.config.repository_id!r}"
            )
        revision = _required_text(
            repository, ("revision", "commit", "sha"), "pinned repository revision"
        )
        if revision.lower() in {"main", "master", "head", "latest"}:
            raise FixtureError(f"repository revision is mutable, not pinned: {revision!r}")
        canonical_repository_url = _uri(
            _required_text(repository, ("url", "canonical_url"), "repository URL"),
            "repository URL",
        )
        card = payload.get("card") or {}
        if not isinstance(card, dict):
            raise FixtureError("snapshot.card must be an object")
        license_evidence, license_status = _license_evidence(repository, card)
        (
            technical_access_status,
            access_gate,
            payload_state,
            media_rights_status,
        ) = _access_state(repository, self.config)
        publisher = str(repository.get("publisher") or self.config.publisher).strip()
        if not publisher:
            raise FixtureError("missing publisher")
        configs = _list_of_dicts(payload.get("configs"), "configs")
        files = _list_of_dicts(payload.get("files"), "files")
        rows = payload.get("rows")
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise FixtureError("snapshot.rows must be an array of objects")
        if self.config.adapter_state != "active" and rows:
            raise FixtureError(
                f"adapter {self.config.adapter_id!r} is {self.config.adapter_state}; "
                "candidate rows require a dedicated reviewed normalizer"
            )

        warnings: list[str] = [
            "License/terms evidence is informational only and does not approve "
            "acquisition, processing, or release of any asset."
        ]
        if license_status != "consistent":
            warnings.append(f"License evidence is {license_status}; rights remain held.")
        candidates: list[NormalizedCandidate] = []
        seen_source_ids: set[str] = set()
        for index, row in enumerate(rows):
            try:
                candidate = self._normalize_row(
                    row=row,
                    repository_id=repository_id,
                    repository_revision=revision,
                    repository_url=canonical_repository_url,
                    license_evidence=license_evidence,
                    license_resolution_status=license_status,
                    technical_access_status=technical_access_status,
                    access_gate=access_gate,
                    payload_state=payload_state,
                    media_rights_status=media_rights_status,
                    publisher=publisher,
                )
            except (FixtureError, ValueError) as exc:
                raise FixtureError(f"row {index}: {exc}") from exc
            identity = f"{candidate.dataset_id}:{candidate.source_id}"
            if identity in seen_source_ids:
                raise FixtureError(f"row {index}: duplicate source identity {identity!r}")
            seen_source_ids.add(identity)
            candidates.append(candidate)

        candidates.sort(
            key=lambda item: (
                item.dataset_id,
                item.split,
                item.canonical_identity or "",
                item.source_id,
            )
        )
        return InspectionResult(
            inspection_version="2.0",
            adapter_id=self.config.adapter_id,
            provider=self.provider,
            repository_id=repository_id,
            revision=revision,
            snapshot_sha256=sha256_file(fixture_path),
            card=dict(card),
            configs=configs,
            files=files,
            candidates=tuple(candidates),
            warnings=tuple(warnings),
        )

    def _normalize_row(
        self,
        *,
        row: Mapping[str, Any],
        repository_id: str,
        repository_revision: str,
        repository_url: str,
        license_evidence: tuple[LicenseEvidence, ...],
        license_resolution_status: str,
        technical_access_status: str,
        access_gate: str,
        payload_state: str,
        media_rights_status: str,
        publisher: str,
    ) -> NormalizedCandidate:
        source_id = _required_text(
            row, ("source_id", "id", "video_id", "asset_id"), "source ID"
        )
        (
            upstream_namespace,
            upstream_asset_id,
            identity_resolution_status,
            parent_dataset_id,
            parent_upstream_namespace,
            parent_upstream_asset_id,
            lineage_relation,
        ) = _identity(row)
        split = _required_text(row, ("split", "partition"), "split")
        canonical_url = _uri(
            _required_text(
                row, ("canonical_url", "source_url", "page_url"), "canonical source URL"
            ),
            "canonical source URL",
        )
        media_url_text = _optional_text(
            row, ("media_url", "download_url", "file_url", "url")
        )
        media_url = _uri(media_url_text, "media URL") if media_url_text else None
        revision = str(row.get("revision") or repository_revision).strip()
        if not revision or revision.lower() in {"main", "master", "head", "latest"}:
            raise FixtureError("missing or mutable row revision")
        byte_size_raw = _first(row, ("byte_size", "size_bytes"), None)
        byte_size = None
        if byte_size_raw is not None:
            if isinstance(byte_size_raw, bool):
                raise FixtureError("byte size must be an integer")
            try:
                byte_size = int(byte_size_raw)
            except (TypeError, ValueError) as exc:
                raise FixtureError("byte size must be an integer") from exc
            if byte_size <= 0:
                raise FixtureError("byte size must be positive")
        retrieval = row.get("retrieval") or {}
        if not isinstance(retrieval, dict):
            raise FixtureError("retrieval must be an object")
        source_metadata = row.get("source_metadata") or {}
        if not isinstance(source_metadata, dict):
            raise FixtureError("source_metadata must be an object")
        source_metadata = {
            **source_metadata,
            "repository_url": repository_url,
            "license_evidence_is_not_rights_approval": True,
            "adapter_state": self.config.adapter_state,
            "identity_policy": self.config.identity_policy,
        }
        return NormalizedCandidate(
            dataset_id=self.config.dataset_id,
            adapter_id=self.config.adapter_id,
            provider=self.provider,
            repository_id=repository_id,
            source_id=source_id,
            split=split,
            duration_s=_duration_s(row),
            canonical_url=canonical_url,
            media_url=media_url,
            has_video=_bool(row, ("has_video", "video_available"), None),
            has_audio=_bool(row, ("has_audio", "audio_available"), None),
            has_speech=_bool(row, ("has_speech", "speech_available"), None),
            has_ambient_audio=_bool(
                row, ("has_ambient_audio", "ambient_audio_available"), None
            ),
            transcript_available=bool(
                _bool(
                    row,
                    ("transcript_available", "has_transcript", "subtitles_available"),
                    False,
                )
            ),
            evidence_available=bool(
                _bool(
                    row,
                    ("evidence_available", "has_evidence", "temporal_evidence_available"),
                    False,
                )
            ),
            revision=revision,
            license_evidence=license_evidence,
            license_resolution_status=license_resolution_status,
            technical_access_status=technical_access_status,
            access_gate=access_gate,
            payload_state=payload_state,
            media_rights_status=media_rights_status,
            source_family=self.config.source_family,
            publisher=publisher,
            rightsholder_or_status=str(
                row.get("rightsholder_or_status") or "unknown_hold"
            ),
            upstream_namespace=upstream_namespace,
            upstream_asset_id=upstream_asset_id,
            identity_resolution_status=identity_resolution_status,
            parent_dataset_id=parent_dataset_id,
            parent_upstream_namespace=parent_upstream_namespace,
            parent_upstream_asset_id=parent_upstream_asset_id,
            lineage_relation=lineage_relation,
            episode_access_class=_optional_text(row, ("episode_access_class",)),
            byte_size=byte_size,
            checksum=_checksum(row),
            fingerprint=_optional_text(
                row, ("fingerprint", "perceptual_hash", "media_fingerprint")
            ),
            config=_optional_text(row, ("config", "config_name", "subset")),
            title=_optional_text(row, ("title", "name")),
            retrieval=dict(retrieval),
            source_metadata=source_metadata,
        )


class HFDatasetAdapter(_JSONSnapshotAdapter):
    """Adapter for exported Hugging Face dataset repository metadata."""

    provider = "huggingface"


class GitHubManifestAdapter(_JSONSnapshotAdapter):
    """Adapter for exported official GitHub repository manifests."""

    provider = "github"


def adapter_for_config(config: AdapterConfig) -> SourceAdapter:
    if config.adapter_state != "active":
        raise ValueError(
            f"adapter {config.adapter_id!r} is {config.adapter_state}; "
            "use its documented manual/protocol workflow"
        )
    if config.provider == "huggingface":
        return HFDatasetAdapter(config)
    if config.provider == "github":
        return GitHubManifestAdapter(config)
    raise ValueError(f"unsupported provider: {config.provider}")
