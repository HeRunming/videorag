"""Deterministic, fail-closed audiovisual candidate filtering and ranking."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable

from .errors import SelectionError
from .io import sha256_json
from .models import NormalizedCandidate, immutable_revision

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class SelectionPolicy:
    min_duration_s: float = 20 * 60
    max_duration_s: float = 90 * 60
    target_duration_s: float = 40 * 60
    limit: int = 30
    max_item_bytes: int | None = None
    max_total_bytes: int | None = None
    require_known_size: bool = False
    require_media_url: bool = False
    require_video: bool = True
    require_audio: bool = True
    require_resolved_identity: bool = True
    allowed_splits: tuple[str, ...] = ()
    allowed_access_modes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.min_duration_s <= 0 or self.max_duration_s < self.min_duration_s:
            raise ValueError("invalid duration range")
        if self.limit <= 0:
            raise ValueError("limit must be positive")
        if self.max_item_bytes is not None and self.max_item_bytes <= 0:
            raise ValueError("max_item_bytes must be positive")
        if self.max_total_bytes is not None and self.max_total_bytes <= 0:
            raise ValueError("max_total_bytes must be positive")

    def to_dict(self) -> dict[str, Any]:
        return {
            "min_duration_s": self.min_duration_s,
            "max_duration_s": self.max_duration_s,
            "target_duration_s": self.target_duration_s,
            "limit": self.limit,
            "max_item_bytes": self.max_item_bytes,
            "max_total_bytes": self.max_total_bytes,
            "require_known_size": self.require_known_size,
            "require_media_url": self.require_media_url,
            "require_video": self.require_video,
            "require_audio": self.require_audio,
            "require_resolved_identity": self.require_resolved_identity,
            "allowed_splits": list(self.allowed_splits),
            # Compatibility name: values are now audited technical access
            # statuses, not inferred rights or episode access classes.
            "allowed_access_modes": list(self.allowed_access_modes),
        }


def _rank(candidate: NormalizedCandidate, policy: SelectionPolicy) -> tuple[Any, ...]:
    return (
        -int(candidate.evidence_available),
        -int(candidate.transcript_available),
        abs(candidate.duration_s - policy.target_duration_s),
        candidate.duration_s,
        candidate.dataset_id,
        candidate.canonical_identity or "",
        candidate.source_id,
    )


class _IdentityGraph:
    """Small union-find over explicitly resolved lineage nodes."""

    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def _add(self, item: str) -> None:
        self.parent.setdefault(item, item)

    def find(self, item: str) -> str:
        self._add(item)
        root = item
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[item] != item:
            next_item = self.parent[item]
            self.parent[item] = root
            item = next_item
        return root

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        # Lexical roots keep output deterministic independently of row order.
        low, high = sorted((left_root, right_root))
        self.parent[high] = low


def _identity_components(
    candidates: Iterable[NormalizedCandidate],
) -> dict[tuple[str, str], str]:
    graph = _IdentityGraph()
    keyed: list[tuple[NormalizedCandidate, tuple[str, ...]]] = []
    for candidate in candidates:
        keys = candidate.identity_keys()
        keyed.append((candidate, keys))
        for key in keys:
            graph._add(key)
        for key in keys[1:]:
            graph.union(keys[0], key)
    return {
        (candidate.dataset_id, candidate.source_id): graph.find(keys[0])
        for candidate, keys in keyed
        if keys
    }


def _rejection(candidate: NormalizedCandidate, reasons: list[str]) -> dict[str, Any]:
    return {
        "dataset_id": candidate.dataset_id,
        "source_id": candidate.source_id,
        "upstream_namespace": candidate.upstream_namespace,
        "upstream_asset_id": candidate.upstream_asset_id,
        "canonical_identity": candidate.canonical_identity,
        "identity_resolution_status": candidate.identity_resolution_status,
        "reasons": sorted(set(reasons)),
    }


def select_candidates(
    candidates: Iterable[NormalizedCandidate],
    policy: SelectionPolicy,
    *,
    source_snapshots: dict[str, str] | None = None,
) -> dict[str, Any]:
    normalized_snapshots: dict[str, str] = {}
    for source, digest in sorted((source_snapshots or {}).items()):
        source_name = str(source).strip()
        digest_value = str(digest).strip().lower()
        if not source_name:
            raise SelectionError("source snapshot identity cannot be empty")
        if not _SHA256_RE.fullmatch(digest_value):
            raise SelectionError(
                f"source snapshot hash for {source_name!r} must be a SHA-256 digest"
            )
        if ":" not in source_name or "@" not in source_name:
            raise SelectionError(
                "source snapshot identity must be provider:repository@revision"
            )
        source_prefix, source_revision = source_name.rsplit("@", 1)
        provider, repository_id = source_prefix.split(":", 1)
        if not provider.strip() or not repository_id.strip():
            raise SelectionError(
                "source snapshot identity must include provider and repository"
            )
        if immutable_revision(source_revision) is None:
            raise SelectionError(
                f"source snapshot revision for {source_name!r} is not immutable"
            )
        normalized_snapshots[source_name] = digest_value

    all_candidates = list(candidates)
    identity_components = _identity_components(all_candidates)
    rejected: list[dict[str, Any]] = []
    eligible: list[NormalizedCandidate] = []
    for candidate in all_candidates:
        reasons: list[str] = []
        if not candidate.source_id:
            reasons.append("missing_source_identity")
        if policy.require_resolved_identity:
            if candidate.identity_resolution_status == "conflicting":
                reasons.append("identity_conflicting")
            elif candidate.identity_resolution_status != "resolved":
                reasons.append("identity_unresolved")
            elif not candidate.canonical_identity:
                reasons.append("missing_namespaced_upstream_identity")
        if immutable_revision(candidate.revision) is None:
            reasons.append("revision_not_immutable")
        if policy.require_video:
            if candidate.has_video is None:
                reasons.append("video_unknown")
            elif candidate.has_video is False:
                reasons.append("video_unavailable")
        if policy.require_audio:
            if candidate.has_audio is None:
                reasons.append("audio_unknown")
            elif candidate.has_audio is False:
                reasons.append("audio_unavailable")
        if not policy.min_duration_s <= candidate.duration_s <= policy.max_duration_s:
            reasons.append("outside_duration_range")
        if policy.allowed_splits and candidate.split not in policy.allowed_splits:
            reasons.append("split_not_allowed")
        if (
            policy.allowed_access_modes
            and candidate.technical_access_status not in policy.allowed_access_modes
        ):
            reasons.append("technical_access_status_not_allowed")
        if policy.require_media_url and not candidate.media_url:
            reasons.append("media_url_missing")
        if policy.require_known_size and candidate.byte_size is None:
            reasons.append("byte_size_unknown")
        if (
            policy.max_item_bytes is not None
            and candidate.byte_size is not None
            and candidate.byte_size > policy.max_item_bytes
        ):
            reasons.append("item_size_cap_exceeded")
        if reasons:
            rejected.append(_rejection(candidate, reasons))
        else:
            eligible.append(candidate)

    eligible.sort(key=lambda item: _rank(item, policy))
    selected: list[NormalizedCandidate] = []
    selected_components: set[str] = set()
    selected_checksums: set[str] = set()
    selected_fingerprints: set[str] = set()
    total_known_bytes = 0
    for candidate in eligible:
        duplicate_reasons: list[str] = []
        component = identity_components.get((candidate.dataset_id, candidate.source_id))
        if component and component in selected_components:
            duplicate_reasons.append("duplicate_lineage_identity")
        if candidate.checksum and candidate.checksum in selected_checksums:
            duplicate_reasons.append("duplicate_checksum")
        fingerprint_is_verified = (
            candidate.source_metadata.get("fingerprint_identity_status")
            == "verified_same_asset"
        )
        if (
            fingerprint_is_verified
            and candidate.fingerprint
            and candidate.fingerprint in selected_fingerprints
        ):
            duplicate_reasons.append("duplicate_fingerprint")
        if duplicate_reasons:
            rejected.append(_rejection(candidate, duplicate_reasons))
            continue
        if len(selected) >= policy.limit:
            rejected.append(_rejection(candidate, ["selection_limit_reached"]))
            continue
        item_bytes = candidate.byte_size or 0
        if (
            policy.max_total_bytes is not None
            and total_known_bytes + item_bytes > policy.max_total_bytes
        ):
            rejected.append(_rejection(candidate, ["total_size_cap_exceeded"]))
            continue
        selected.append(candidate)
        if component:
            selected_components.add(component)
        if candidate.checksum:
            selected_checksums.add(candidate.checksum)
        if fingerprint_is_verified and candidate.fingerprint:
            selected_fingerprints.add(candidate.fingerprint)
        total_known_bytes += item_bytes

    if not selected:
        raise SelectionError("no candidates passed the fail-closed selection policy")
    required_snapshot_sources = {
        f"{candidate.provider}:{candidate.repository_id}@{candidate.revision}"
        for candidate in selected
    }
    missing_snapshot_sources = sorted(
        required_snapshot_sources - set(normalized_snapshots)
    )
    freezeable = bool(normalized_snapshots) and not missing_snapshot_sources
    selection_state = (
        "freeze_ready_candidate"
        if freezeable
        else "exploratory_non_freezeable_candidate"
    )
    body = {
        "selection_version": "2.0",
        "selection_state": selection_state,
        "freezeable": freezeable,
        "executable": freezeable,
        "non_freezeable_reasons": (
            []
            if freezeable
            else [
                (
                    "missing_source_snapshot_bindings"
                    if not normalized_snapshots
                    else "incomplete_source_snapshot_coverage"
                )
            ]
        ),
        "policy": policy.to_dict(),
        "source_snapshots": normalized_snapshots,
        "selected": [candidate.to_dict() for candidate in selected],
        "rejected": sorted(
            rejected,
            key=lambda item: (
                item["dataset_id"],
                item["canonical_identity"] or "",
                item["source_id"],
                item["reasons"],
            ),
        ),
        "summary": {
            "selected_count": len(selected),
            "rejected_count": len(rejected),
            "known_selected_bytes": total_known_bytes,
            "unknown_size_selected_count": sum(
                candidate.byte_size is None for candidate in selected
            ),
            "unresolved_identity_rejected_count": sum(
                "identity_unresolved" in item["reasons"] for item in rejected
            ),
            "unknown_audio_rejected_count": sum(
                "audio_unknown" in item["reasons"] for item in rejected
            ),
            "missing_source_snapshot_bindings": missing_snapshot_sources,
        },
    }
    body["selection_sha256"] = sha256_json(body)
    return body
