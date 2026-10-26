"""Versioned, fail-closed bridge from acquired assets to episode provenance.

The acquisition manifest intentionally does not contain probe-level stream and
transformation records.  This module binds those records to one exact manifest
revision and converts them to the frozen episode ``source`` shape only after
the manifest, rights profile, hashes, lineage, and source-time mappings pass.
"""

from __future__ import annotations

import math
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator

from av_trace.errors import ValidationIssue, ValidationReport, make_report
from av_trace.manifest import GateProfile, validate_manifest_gate
from av_trace.schemas import SchemaRegistry
from av_trace.util import safe_sha256_json
from .models import is_immutable_revision

VERIFIED_ASSET_VERSION = "1.0.0"

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA256 = re.compile(r"^sha256:[a-f0-9]{64}$")
_STREAM_KINDS = {"video", "audio", "subtitle", "transcript", "metadata"}
_STREAM_ROLES = {"acquired", "derived"}
_LINEAGE_RELATIONSHIPS = {"original", "derived"}
_PARENT_RELATIONS = {
    "segment_of",
    "excerpt_of",
    "transcode_of",
    "reconstruction_of",
    "alternate_encode_of",
    "derived_from",
}
_MANIFEST_RELATIONSHIPS = {"exact_acquired_bytes", "registered_derivative"}
_TECHNICAL_ACCESS = {
    "local_verified",
    "authorized_remote",
    "gated_authorized",
    "unavailable",
    "unknown",
    "conflicting",
}
_RIGHTS_STATUS = {
    "approved_for_acquisition",
    "approved_for_annotation",
    "approved_for_public_release",
    "approved_restricted_use",
    "prohibited",
    "unknown",
    "conflicting",
}
_ACCESS_CLASSES = {"public_core_redistributable", "restricted_compatibility"}


@dataclass(frozen=True)
class VerifiedAssetRecord:
    """Immutable Python wrapper for the versioned verified-asset JSON record."""

    bridge_version: str
    record_id: str
    canonical_upstream: Mapping[str, Any]
    lineage: Mapping[str, Any]
    manifest: Mapping[str, Any]
    acquired_asset: Mapping[str, Any]
    streams: tuple[Mapping[str, Any], ...]
    transformations: tuple[Mapping[str, Any], ...]
    access: Mapping[str, Any]

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "VerifiedAssetRecord":
        return cls(
            bridge_version=str(value.get("bridge_version", "")),
            record_id=str(value.get("record_id", "")),
            canonical_upstream=deepcopy(value.get("canonical_upstream", {})),
            lineage=deepcopy(value.get("lineage", {})),
            manifest=deepcopy(value.get("manifest", {})),
            acquired_asset=deepcopy(value.get("acquired_asset", {})),
            streams=tuple(deepcopy(value.get("streams", ()))),
            transformations=tuple(deepcopy(value.get("transformations", ()))),
            access=deepcopy(value.get("access", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "bridge_version": self.bridge_version,
            "record_id": self.record_id,
            "canonical_upstream": deepcopy(dict(self.canonical_upstream)),
            "lineage": deepcopy(dict(self.lineage)),
            "manifest": deepcopy(dict(self.manifest)),
            "acquired_asset": deepcopy(dict(self.acquired_asset)),
            "streams": deepcopy([dict(item) for item in self.streams]),
            "transformations": deepcopy(
                [dict(item) for item in self.transformations]
            ),
            "access": deepcopy(dict(self.access)),
        }


class ProvenanceBridgeError(ValueError):
    """Raised when fail-closed conversion to an episode source is refused."""

    def __init__(self, report: ValidationReport):
        self.report = report
        codes = ", ".join(sorted({issue.code for issue in report.issues}))
        super().__init__(f"verified-asset bridge validation failed: {codes}")


def _as_dict(record: VerifiedAssetRecord | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(record, VerifiedAssetRecord):
        return record.to_dict()
    if isinstance(record, Mapping):
        return deepcopy(dict(record))
    return {}


def _issue(
    issues: list[ValidationIssue],
    code: str,
    pointer: str,
    message: str,
    *ids: str,
) -> None:
    issues.append(ValidationIssue(code, pointer, message, tuple(ids)))


def _is_id(value: Any) -> bool:
    return isinstance(value, str) and bool(_ID.fullmatch(value))


def _is_hash(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA256.fullmatch(value))


def _is_positive_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0
    )


def _strict_object(
    value: Any,
    pointer: str,
    required: set[str],
    issues: list[ValidationIssue],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        _issue(issues, "BRIDGE-001", pointer, "Expected an object.")
        return {}
    missing = sorted(required - set(value))
    extra = sorted(set(value) - required)
    for name in missing:
        _issue(
            issues,
            "BRIDGE-001",
            f"{pointer}/{name}",
            "Required verified-asset field is missing.",
        )
    for name in extra:
        _issue(
            issues,
            "BRIDGE-001",
            f"{pointer}/{name}",
            "Unknown verified-asset field is not permitted.",
        )
    return value


def _mapping_segments(
    mapping: Any,
    pointer: str,
    issues: list[ValidationIssue],
    *,
    require_source_stream: bool,
) -> list[dict[str, Any]]:
    required = {"mapping_type", "segments"}
    if require_source_stream:
        required.add("source_stream_id")
    value = _strict_object(mapping, pointer, required, issues)
    if value.get("mapping_type") not in {"identity", "piecewise_linear"}:
        _issue(
            issues,
            "BRIDGE-006",
            f"{pointer}/mapping_type",
            "Source-time mapping type must be identity or piecewise_linear.",
        )
    if require_source_stream and not _is_id(value.get("source_stream_id")):
        _issue(
            issues,
            "BRIDGE-006",
            f"{pointer}/source_stream_id",
            "Source-time mapping requires a valid source stream ID.",
        )
    raw_segments = value.get("segments")
    if not isinstance(raw_segments, list) or not raw_segments:
        _issue(
            issues,
            "BRIDGE-006",
            f"{pointer}/segments",
            "At least one auditable source-time mapping segment is required.",
        )
        return []
    segments: list[dict[str, Any]] = []
    previous_derived_end = -math.inf
    for index, raw in enumerate(raw_segments):
        segment_pointer = f"{pointer}/segments/{index}"
        segment = _strict_object(
            raw,
            segment_pointer,
            {
                "derived_start_s",
                "derived_end_s",
                "source_start_s",
                "source_end_s",
            },
            issues,
        )
        values = [
            segment.get("derived_start_s"),
            segment.get("derived_end_s"),
            segment.get("source_start_s"),
            segment.get("source_end_s"),
        ]
        if not all(
            isinstance(item, (int, float))
            and not isinstance(item, bool)
            and math.isfinite(item)
            for item in values
        ):
            _issue(
                issues,
                "BRIDGE-006",
                segment_pointer,
                "Mapping endpoints must be finite numbers.",
            )
            continue
        derived_start, derived_end, source_start, source_end = values
        if (
            derived_start < 0
            or source_start < 0
            or derived_end <= derived_start
            or source_end <= source_start
        ):
            _issue(
                issues,
                "BRIDGE-006",
                segment_pointer,
                "Mapping intervals must be non-negative and strictly increasing.",
            )
        if derived_start < previous_derived_end:
            _issue(
                issues,
                "BRIDGE-006",
                segment_pointer,
                "Mapping segments must be ordered and non-overlapping.",
            )
        if (
            value.get("mapping_type") == "identity"
            and (
                not math.isclose(derived_start, source_start)
                or not math.isclose(derived_end, source_end)
            )
        ):
            _issue(
                issues,
                "BRIDGE-006",
                segment_pointer,
                "Identity mappings must preserve interval endpoints.",
            )
        previous_derived_end = derived_end
        segments.append(segment)
    return segments


def _interval_covered(
    start: float,
    end: float,
    segments: Sequence[Mapping[str, Any]],
    *,
    coordinate: str,
) -> bool:
    start_key = f"{coordinate}_start_s"
    end_key = f"{coordinate}_end_s"
    return any(
        isinstance(segment.get(start_key), (int, float))
        and isinstance(segment.get(end_key), (int, float))
        and segment[start_key] <= start
        and end <= segment[end_key]
        for segment in segments
    )


def gate_profile_for_access_class(access_class: str) -> GateProfile:
    """Return the only release profile compatible with an episode access class."""

    if access_class == "public_core_redistributable":
        return GateProfile.PUBLIC_CORE_RELEASE
    if access_class == "restricted_compatibility":
        return GateProfile.EXTERNAL_COMPATIBILITY_UNPOOLED
    raise ValueError(f"unknown episode access class: {access_class!r}")


def validate_verified_asset_record(
    record: VerifiedAssetRecord | Mapping[str, Any],
    manifest: Mapping[str, Any],
    gate: GateProfile | str | None = None,
    registry: SchemaRegistry | None = None,
) -> ValidationReport:
    """Validate one bridge record against the exact frozen acquisition manifest."""

    data = _as_dict(record)
    manifest_dict = dict(manifest) if isinstance(manifest, Mapping) else {}
    registry = registry or SchemaRegistry()
    issues: list[ValidationIssue] = []

    top = _strict_object(
        data,
        "",
        {
            "bridge_version",
            "record_id",
            "canonical_upstream",
            "lineage",
            "manifest",
            "acquired_asset",
            "streams",
            "transformations",
            "access",
        },
        issues,
    )
    if top.get("bridge_version") != VERIFIED_ASSET_VERSION:
        _issue(
            issues,
            "BRIDGE-001",
            "/bridge_version",
            f"Only verified-asset bridge version {VERIFIED_ASSET_VERSION} is supported.",
        )
    if not _is_id(top.get("record_id")):
        _issue(issues, "BRIDGE-001", "/record_id", "A valid record ID is required.")

    canonical = _strict_object(
        top.get("canonical_upstream"),
        "/canonical_upstream",
        {"namespace", "asset_id", "revision"},
        issues,
    )
    for name in ("namespace", "asset_id", "revision"):
        if not isinstance(canonical.get(name), str) or not canonical.get(name):
            _issue(
                issues,
                "BRIDGE-002",
                f"/canonical_upstream/{name}",
                "Canonical upstream identity fields must be non-empty strings.",
            )
    if not is_immutable_revision(canonical.get("revision")):
        _issue(
            issues,
            "BRIDGE-002",
            "/canonical_upstream/revision",
            "Canonical source revision must be one full immutable revision.",
        )

    manifest_ref = _strict_object(
        top.get("manifest"),
        "/manifest",
        {"asset_id", "revision", "sha256"},
        issues,
    )
    if not _is_id(manifest_ref.get("asset_id")):
        _issue(
            issues,
            "BRIDGE-002",
            "/manifest/asset_id",
            "Manifest asset ID is missing or invalid.",
        )
    if not is_immutable_revision(manifest_ref.get("revision")):
        _issue(
            issues,
            "BRIDGE-002",
            "/manifest/revision",
            "Manifest revision must be one full immutable revision.",
        )
    if not _is_hash(manifest_ref.get("sha256")):
        _issue(
            issues,
            "BRIDGE-002",
            "/manifest/sha256",
            "The exact frozen manifest SHA-256 is required.",
        )

    acquired = _strict_object(
        top.get("acquired_asset"),
        "/acquired_asset",
        {
            "asset_id",
            "relationship_to_manifest",
            "manifest_artifact_id",
            "content_sha256",
            "duration_s",
        },
        issues,
    )
    if not _is_id(acquired.get("asset_id")):
        _issue(
            issues,
            "BRIDGE-003",
            "/acquired_asset/asset_id",
            "Acquired asset ID is missing or invalid.",
        )
    if acquired.get("relationship_to_manifest") not in _MANIFEST_RELATIONSHIPS:
        _issue(
            issues,
            "BRIDGE-003",
            "/acquired_asset/relationship_to_manifest",
            "Acquired bytes must be exact manifest bytes or a registered derivative.",
        )
    if not _is_hash(acquired.get("content_sha256")):
        _issue(
            issues,
            "BRIDGE-003",
            "/acquired_asset/content_sha256",
            "Acquired content hash is required.",
        )
    if not _is_positive_number(acquired.get("duration_s")):
        _issue(
            issues,
            "BRIDGE-003",
            "/acquired_asset/duration_s",
            "A finite positive acquired duration is required.",
        )

    lineage = _strict_object(
        top.get("lineage"),
        "/lineage",
        {"relationship", "parents"},
        issues,
    )
    relationship = lineage.get("relationship")
    if relationship not in _LINEAGE_RELATIONSHIPS:
        _issue(
            issues,
            "BRIDGE-006",
            "/lineage/relationship",
            "Lineage relationship must be original or derived.",
        )
    raw_parents = lineage.get("parents")
    if not isinstance(raw_parents, list):
        _issue(issues, "BRIDGE-006", "/lineage/parents", "Lineage parents must be an array.")
        raw_parents = []
    if relationship == "original" and raw_parents:
        _issue(
            issues,
            "BRIDGE-006",
            "/lineage/parents",
            "An original asset cannot declare parent assets.",
        )
    if relationship == "derived" and not raw_parents:
        _issue(
            issues,
            "BRIDGE-006",
            "/lineage/parents",
            "A derived asset requires at least one parent and source-time mapping.",
        )
    lineage_mappings: list[list[dict[str, Any]]] = []
    for index, raw_parent in enumerate(raw_parents):
        pointer = f"/lineage/parents/{index}"
        parent = _strict_object(
            raw_parent,
            pointer,
            {
                "namespace",
                "asset_id",
                "revision",
                "relation",
                "content_sha256",
                "source_time_mapping",
            },
            issues,
        )
        if not all(
            isinstance(parent.get(name), str) and parent.get(name)
            for name in ("namespace", "asset_id", "revision")
        ):
            _issue(
                issues,
                "BRIDGE-006",
                pointer,
                "Each lineage parent requires a complete namespaced identity.",
            )
        if not is_immutable_revision(parent.get("revision")):
            _issue(
                issues,
                "BRIDGE-006",
                f"{pointer}/revision",
                "Lineage parent revision must be one full immutable revision.",
            )
        if parent.get("relation") not in _PARENT_RELATIONS:
            _issue(
                issues,
                "BRIDGE-006",
                f"{pointer}/relation",
                "Unknown parent/derived lineage relation.",
            )
        if not _is_hash(parent.get("content_sha256")):
            _issue(
                issues,
                "BRIDGE-006",
                f"{pointer}/content_sha256",
                "Parent content hash is required.",
            )
        lineage_mappings.append(
            _mapping_segments(
                parent.get("source_time_mapping"),
                f"{pointer}/source_time_mapping",
                issues,
                require_source_stream=False,
            )
        )

    raw_streams = top.get("streams")
    if not isinstance(raw_streams, list):
        _issue(issues, "BRIDGE-004", "/streams", "Verified streams must be an array.")
        raw_streams = []
    stream_by_id: dict[str, dict[str, Any]] = {}
    for index, raw_stream in enumerate(raw_streams):
        pointer = f"/streams/{index}"
        stream = _strict_object(
            raw_stream,
            pointer,
            {
                "stream_id",
                "kind",
                "language",
                "sha256",
                "duration_s",
                "role",
                "parent_stream_ids",
                "transformation_ids",
            },
            issues,
        )
        stream_id = stream.get("stream_id")
        if not _is_id(stream_id):
            _issue(issues, "BRIDGE-004", f"{pointer}/stream_id", "Invalid stream ID.")
        elif stream_id in stream_by_id:
            _issue(
                issues,
                "BRIDGE-004",
                f"{pointer}/stream_id",
                "Stream IDs must be unique.",
                stream_id,
            )
        else:
            stream_by_id[stream_id] = stream
        if stream.get("kind") not in _STREAM_KINDS:
            _issue(issues, "BRIDGE-004", f"{pointer}/kind", "Unknown stream kind.")
        if stream.get("language") is not None and not isinstance(
            stream.get("language"), str
        ):
            _issue(
                issues,
                "BRIDGE-004",
                f"{pointer}/language",
                "Stream language must be a string or null.",
            )
        if not _is_hash(stream.get("sha256")):
            _issue(
                issues,
                "BRIDGE-004",
                f"{pointer}/sha256",
                "Every verified stream requires a SHA-256 hash.",
            )
        if not _is_positive_number(stream.get("duration_s")):
            _issue(
                issues,
                "BRIDGE-004",
                f"{pointer}/duration_s",
                "Every verified stream requires a finite positive duration.",
            )
        if stream.get("role") not in _STREAM_ROLES:
            _issue(issues, "BRIDGE-004", f"{pointer}/role", "Unknown stream role.")
        for list_name in ("parent_stream_ids", "transformation_ids"):
            values = stream.get(list_name)
            if (
                not isinstance(values, list)
                or not all(_is_id(item) for item in values)
                or len(values) != len(set(values))
            ):
                _issue(
                    issues,
                    "BRIDGE-004",
                    f"{pointer}/{list_name}",
                    "Stream references must be a unique array of valid IDs.",
                )
        if stream.get("role") == "acquired" and (
            stream.get("parent_stream_ids") or stream.get("transformation_ids")
        ):
            _issue(
                issues,
                "BRIDGE-004",
                pointer,
                "An acquired stream cannot claim derived-stream lineage.",
            )
        if stream.get("role") == "derived" and (
            not stream.get("parent_stream_ids") or not stream.get("transformation_ids")
        ):
            _issue(
                issues,
                "BRIDGE-004",
                pointer,
                "A derived stream requires parent streams and transformations.",
            )
    kinds = {stream.get("kind") for stream in stream_by_id.values()}
    if not {"video", "audio"} <= kinds:
        _issue(
            issues,
            "BRIDGE-004",
            "/streams",
            "Verified video and audio streams are both required.",
        )

    raw_transformations = top.get("transformations")
    if not isinstance(raw_transformations, list):
        _issue(
            issues,
            "BRIDGE-005",
            "/transformations",
            "Transformations must be an array.",
        )
        raw_transformations = []
    transformation_by_id: dict[str, dict[str, Any]] = {}
    transformation_mappings: dict[str, list[dict[str, Any]]] = {}
    for index, raw_transformation in enumerate(raw_transformations):
        pointer = f"/transformations/{index}"
        transformation = _strict_object(
            raw_transformation,
            pointer,
            {
                "transformation_id",
                "kind",
                "input_stream_ids",
                "output_stream_ids",
                "tool",
                "tool_version",
                "parameters_sha256",
                "source_time_mapping",
            },
            issues,
        )
        transformation_id = transformation.get("transformation_id")
        if not _is_id(transformation_id):
            _issue(
                issues,
                "BRIDGE-005",
                f"{pointer}/transformation_id",
                "Invalid transformation ID.",
            )
        elif transformation_id in transformation_by_id:
            _issue(
                issues,
                "BRIDGE-005",
                f"{pointer}/transformation_id",
                "Transformation IDs must be unique.",
                transformation_id,
            )
        else:
            transformation_by_id[transformation_id] = transformation
        if not isinstance(transformation.get("kind"), str) or not transformation.get(
            "kind"
        ):
            _issue(
                issues,
                "BRIDGE-005",
                f"{pointer}/kind",
                "Transformation kind is required.",
            )
        for list_name in ("input_stream_ids", "output_stream_ids"):
            values = transformation.get(list_name)
            if (
                not isinstance(values, list)
                or not all(_is_id(item) for item in values)
                or len(values) != len(set(values))
            ):
                _issue(
                    issues,
                    "BRIDGE-005",
                    f"{pointer}/{list_name}",
                    "Transformation stream references must be unique valid IDs.",
                )
            elif list_name == "input_stream_ids" and not values:
                _issue(
                    issues,
                    "BRIDGE-005",
                    f"{pointer}/{list_name}",
                    "A transformation requires at least one input stream.",
                )
            else:
                for stream_id in values:
                    if stream_id not in stream_by_id:
                        _issue(
                            issues,
                            "BRIDGE-005",
                            f"{pointer}/{list_name}",
                            f"Unknown transformation stream ID {stream_id}.",
                            str(transformation_id or ""),
                            stream_id,
                        )
        for name in ("tool", "tool_version"):
            if not isinstance(transformation.get(name), str) or not transformation.get(
                name
            ):
                _issue(
                    issues,
                    "BRIDGE-005",
                    f"{pointer}/{name}",
                    "Transformation tool identity and version are required.",
                )
        if not _is_hash(transformation.get("parameters_sha256")):
            _issue(
                issues,
                "BRIDGE-005",
                f"{pointer}/parameters_sha256",
                "Transformation parameters hash is required.",
            )
        segments = _mapping_segments(
            transformation.get("source_time_mapping"),
            f"{pointer}/source_time_mapping",
            issues,
            require_source_stream=True,
        )
        if _is_id(transformation_id):
            transformation_mappings[transformation_id] = segments
        mapping = transformation.get("source_time_mapping")
        source_stream_id = (
            mapping.get("source_stream_id") if isinstance(mapping, dict) else None
        )
        if source_stream_id not in transformation.get("input_stream_ids", []):
            _issue(
                issues,
                "BRIDGE-005",
                f"{pointer}/source_time_mapping/source_stream_id",
                "Mapping source stream must be one of the transformation inputs.",
            )

    for stream_id, stream in stream_by_id.items():
        for parent_id in stream.get("parent_stream_ids", []):
            if parent_id not in stream_by_id:
                _issue(
                    issues,
                    "BRIDGE-004",
                    "/streams",
                    f"Derived stream {stream_id} references unknown parent {parent_id}.",
                    stream_id,
                    parent_id,
                )
        for transformation_id in stream.get("transformation_ids", []):
            transformation = transformation_by_id.get(transformation_id)
            if transformation is None:
                _issue(
                    issues,
                    "BRIDGE-005",
                    "/streams",
                    f"Stream {stream_id} references unknown transformation {transformation_id}.",
                    stream_id,
                    transformation_id,
                )
            elif stream_id not in transformation.get("output_stream_ids", []):
                _issue(
                    issues,
                    "BRIDGE-005",
                    "/streams",
                    f"Derived stream {stream_id} is not an output of transformation {transformation_id}.",
                    stream_id,
                    transformation_id,
                )

    access = _strict_object(
        top.get("access"),
        "/access",
        {"technical_access", "rights_status", "episode_access_class"},
        issues,
    )
    technical = _strict_object(
        access.get("technical_access"),
        "/access/technical_access",
        {"status", "mechanism"},
        issues,
    )
    rights_status = _strict_object(
        access.get("rights_status"),
        "/access/rights_status",
        {"status", "rights_decision_id"},
        issues,
    )
    if technical.get("status") not in _TECHNICAL_ACCESS:
        _issue(
            issues,
            "BRIDGE-007",
            "/access/technical_access/status",
            "Unknown technical-access status.",
        )
    if technical.get("status") in {"unknown", "conflicting", "unavailable"}:
        _issue(
            issues,
            "BRIDGE-007",
            "/access/technical_access/status",
            "Unknown, conflicting, or unavailable technical access fails closed.",
        )
    if not isinstance(technical.get("mechanism"), str) or not technical.get(
        "mechanism"
    ):
        _issue(
            issues,
            "BRIDGE-007",
            "/access/technical_access/mechanism",
            "Technical access mechanism is required and is not a rights decision.",
        )
    if rights_status.get("status") not in _RIGHTS_STATUS:
        _issue(
            issues,
            "BRIDGE-007",
            "/access/rights_status/status",
            "Unknown rights status.",
        )
    if rights_status.get("status") in {"unknown", "conflicting", "prohibited"}:
        _issue(
            issues,
            "BRIDGE-007",
            "/access/rights_status/status",
            "Unknown, conflicting, or prohibited rights status fails closed.",
        )
    if not _is_id(rights_status.get("rights_decision_id")):
        _issue(
            issues,
            "BRIDGE-007",
            "/access/rights_status/rights_decision_id",
            "A valid rights decision ID is required.",
        )
    access_class = access.get("episode_access_class")
    if access_class not in _ACCESS_CLASSES:
        _issue(
            issues,
            "BRIDGE-007",
            "/access/episode_access_class",
            "Unknown episode access class.",
        )

    selected_gate: GateProfile | None
    try:
        selected_gate = (
            GateProfile(gate)
            if gate is not None
            else gate_profile_for_access_class(str(access_class))
        )
    except ValueError:
        selected_gate = None
        _issue(
            issues,
            "BRIDGE-007",
            "/access/episode_access_class",
            "No valid gate profile resolves for this access class.",
        )
    if selected_gate in {
        GateProfile.PUBLIC_CORE_RELEASE,
        GateProfile.PUBLIC_RELEASE,
    } and access_class != "public_core_redistributable":
        _issue(
            issues,
            "BRIDGE-007",
            "/access/episode_access_class",
            "Public-core release requires public_core_redistributable.",
        )
    if (
        selected_gate is GateProfile.EXTERNAL_COMPATIBILITY_UNPOOLED
        and access_class != "restricted_compatibility"
    ):
        _issue(
            issues,
            "BRIDGE-007",
            "/access/episode_access_class",
            "External compatibility requires restricted_compatibility.",
        )
    if selected_gate in {
        GateProfile.ANNOTATION,
        GateProfile.PUBLIC_CORE_RELEASE,
        GateProfile.PUBLIC_RELEASE,
        GateProfile.EXTERNAL_COMPATIBILITY_UNPOOLED,
    } and technical.get("status") != "local_verified":
        _issue(
            issues,
            "BRIDGE-007",
            "/access/technical_access/status",
            f"The {selected_gate.value} gate requires locally verified bytes.",
        )

    manifest_report = (
        validate_manifest_gate(manifest_dict, selected_gate, registry)
        if selected_gate is not None
        else registry.validate("acquisition-manifest", manifest_dict)
    )
    issues.extend(manifest_report.issues)

    manifest_source = manifest_dict.get("source", {})
    manifest_rights = manifest_dict.get("rights", {})
    manifest_integrity = manifest_dict.get("integrity", {})
    manifest_media = manifest_dict.get("media", {})
    if not isinstance(manifest_source, dict):
        manifest_source = {}
    if not isinstance(manifest_rights, dict):
        manifest_rights = {}
    if not isinstance(manifest_integrity, dict):
        manifest_integrity = {}
    if not isinstance(manifest_media, dict):
        manifest_media = {}
    if not is_immutable_revision(manifest_source.get("source_revision")):
        _issue(
            issues,
            "BRIDGE-002",
            "/manifest/source/source_revision",
            "Frozen manifest source revision must be one full immutable revision.",
        )
    if not is_immutable_revision(manifest_dict.get("manifest_revision")):
        _issue(
            issues,
            "BRIDGE-002",
            "/manifest/manifest_revision",
            "Frozen manifest revision must be one full immutable revision.",
        )
    expected_manifest_hash = safe_sha256_json(manifest_dict)
    upstream_namespace = canonical.get("namespace")
    upstream_asset_id = canonical.get("asset_id")
    source_identifier = manifest_source.get("source_identifier")
    namespaced_source_identifier = (
        f"{upstream_namespace}:{upstream_asset_id}"
        if isinstance(upstream_namespace, str)
        and upstream_namespace
        and isinstance(upstream_asset_id, str)
        and upstream_asset_id
        else None
    )
    # Adapter-created manifests use one explicit namespaced source identifier.
    # Retain the old schema-compatible representation only when dataset_id
    # supplies the exact namespace and source_identifier supplies the exact
    # asset ID; never infer a namespace from an unrelated local dataset ID.
    legacy_split_identity = (
        manifest_dict.get("dataset_id") == upstream_namespace
        and source_identifier == upstream_asset_id
    )
    if (
        source_identifier != namespaced_source_identifier
        and not legacy_split_identity
    ):
        _issue(
            issues,
            "BRIDGE-002",
            "/canonical_upstream",
            "Canonical upstream namespace and asset ID do not match the manifest source identifier.",
        )
    identity_pairs = (
        (
            "/canonical_upstream/revision",
            canonical.get("revision"),
            manifest_source.get("source_revision"),
        ),
        (
            "/manifest/asset_id",
            manifest_ref.get("asset_id"),
            manifest_dict.get("asset_id"),
        ),
        (
            "/manifest/revision",
            manifest_ref.get("revision"),
            manifest_dict.get("manifest_revision"),
        ),
        (
            "/manifest/sha256",
            manifest_ref.get("sha256"),
            expected_manifest_hash,
        ),
        (
            "/access/rights_status/rights_decision_id",
            rights_status.get("rights_decision_id"),
            manifest_rights.get("rights_decision_id"),
        ),
    )
    for pointer, actual, expected in identity_pairs:
        if actual != expected:
            _issue(
                issues,
                "BRIDGE-002",
                pointer,
                "Verified-asset identity does not resolve to the exact frozen manifest.",
            )

    manifest_gate_status = (
        manifest_dict.get("audit", {}).get("gate_status")
        if isinstance(manifest_dict.get("audit"), dict)
        else None
    )
    allowed_rights_statuses = {
        GateProfile.ACQUISITION: {
            "approved_for_acquisition",
            "approved_for_annotation",
            "approved_for_public_release",
            "approved_restricted_use",
        },
        GateProfile.ANNOTATION: {
            "approved_for_annotation",
            "approved_for_public_release",
            "approved_restricted_use",
        },
        GateProfile.PUBLIC_CORE_RELEASE: {"approved_for_public_release"},
        GateProfile.PUBLIC_RELEASE: {"approved_for_public_release"},
        GateProfile.EXTERNAL_COMPATIBILITY_UNPOOLED: {
            "approved_for_annotation",
            "approved_restricted_use",
        },
    }
    if (
        selected_gate is not None
        and rights_status.get("status") not in allowed_rights_statuses[selected_gate]
    ):
        _issue(
            issues,
            "BRIDGE-007",
            "/access/rights_status/status",
            f"Rights status is insufficient for the {selected_gate.value} gate.",
        )
    if (
        rights_status.get("status") == "approved_for_public_release"
        and manifest_gate_status != "public_release_approved"
    ):
        _issue(
            issues,
            "BRIDGE-007",
            "/access/rights_status/status",
            "Public-release rights status conflicts with the manifest gate status.",
        )

    relationship_to_manifest = acquired.get("relationship_to_manifest")
    if relationship_to_manifest == "exact_acquired_bytes":
        if acquired.get("asset_id") != manifest_dict.get("asset_id"):
            _issue(
                issues,
                "BRIDGE-003",
                "/acquired_asset/asset_id",
                "Exact acquired bytes must use the manifest asset ID.",
            )
        if acquired.get("manifest_artifact_id") is not None:
            _issue(
                issues,
                "BRIDGE-003",
                "/acquired_asset/manifest_artifact_id",
                "Exact acquired bytes cannot name a derived artifact.",
            )
        if acquired.get("content_sha256") != manifest_integrity.get("content_sha256"):
            _issue(
                issues,
                "BRIDGE-003",
                "/acquired_asset/content_sha256",
                "Acquired content hash does not match the frozen manifest.",
            )
        if acquired.get("duration_s") != manifest_media.get("duration_s"):
            _issue(
                issues,
                "BRIDGE-003",
                "/acquired_asset/duration_s",
                "Acquired duration does not match the frozen manifest.",
            )
    elif relationship_to_manifest == "registered_derivative":
        artifact_id = acquired.get("manifest_artifact_id")
        artifacts = manifest_dict.get("derived_artifacts", [])
        if not isinstance(artifacts, list):
            artifacts = []
        artifact = next(
            (
                item
                for item in artifacts
                if isinstance(item, dict) and item.get("artifact_id") == artifact_id
            ),
            None,
        )
        if artifact is None:
            _issue(
                issues,
                "BRIDGE-003",
                "/acquired_asset/manifest_artifact_id",
                "Registered derivative does not resolve in the frozen manifest.",
            )
        elif (
            acquired.get("asset_id") != artifact.get("artifact_id")
            or acquired.get("content_sha256") != artifact.get("sha256")
            or artifact.get("source_asset_id") != manifest_dict.get("asset_id")
        ):
            _issue(
                issues,
                "BRIDGE-003",
                "/acquired_asset",
                "Registered derivative identity, hash, or parent manifest asset does not match.",
            )

    if access_class == "public_core_redistributable" and rights_status.get(
        "status"
    ) != "approved_for_public_release":
        _issue(
            issues,
            "BRIDGE-007",
            "/access/rights_status/status",
            "Public-core classification requires an explicit public-release rights approval.",
        )
    if access_class == "restricted_compatibility" and rights_status.get(
        "status"
    ) == "approved_for_public_release":
        _issue(
            issues,
            "BRIDGE-007",
            "/access",
            "Conflicting restricted access class and public-release rights status.",
        )

    return make_report(
        issues,
        bridge_version=top.get("bridge_version"),
        bridge_hash=safe_sha256_json(data),
        manifest_hash=expected_manifest_hash,
        gate=selected_gate.value if selected_gate is not None else None,
    )


def episode_source_from_verified_asset(
    record: VerifiedAssetRecord | Mapping[str, Any],
    manifest: Mapping[str, Any],
    *,
    registry: SchemaRegistry | None = None,
) -> dict[str, Any]:
    """Convert a verified record to the frozen episode source object.

    The access class chooses the gate.  Consequently an
    ``acquisition_approved`` manifest can never be converted into a public-core
    source merely because acquisition was authorized.
    """

    data = _as_dict(record)
    registry = registry or SchemaRegistry()
    report = validate_verified_asset_record(data, manifest, None, registry)
    if not report.ok:
        raise ProvenanceBridgeError(report)
    acquired = data["acquired_asset"]
    access = data["access"]
    source = {
        "asset_id": acquired["asset_id"],
        "manifest_asset_id": data["manifest"]["asset_id"],
        "manifest_revision": data["manifest"]["revision"],
        "rights_decision_id": access["rights_status"]["rights_decision_id"],
        "duration_s": acquired["duration_s"],
        "content_hash": acquired["content_sha256"],
        "streams": [
            {
                "stream_id": stream["stream_id"],
                "kind": stream["kind"],
                "language": stream["language"],
                "hash": stream["sha256"],
            }
            for stream in data["streams"]
        ],
        "access_class": access["episode_access_class"],
    }

    episode_schema = registry.schemas["episode-family"]
    source_schema = deepcopy(episode_schema["$defs"]["source"])
    source_schema["$defs"] = episode_schema["$defs"]
    schema_errors = sorted(
        Draft202012Validator(source_schema).iter_errors(source),
        key=lambda error: (tuple(str(part) for part in error.absolute_path), error.message),
    )
    if schema_errors:
        source_issues = [
            ValidationIssue(
                "BRIDGE-008",
                "/" + "/".join(str(part) for part in error.absolute_path),
                f"Generated episode source violates the frozen schema: {error.message}",
            )
            for error in schema_errors
        ]
        raise ProvenanceBridgeError(make_report(source_issues))
    return source


def validate_episode_provenance(
    family: Mapping[str, Any],
    manifest: Mapping[str, Any],
    record: VerifiedAssetRecord | Mapping[str, Any],
    *,
    registry: SchemaRegistry | None = None,
) -> ValidationReport:
    """Validate episode source/evidence references through the frozen bridge."""

    data = _as_dict(record)
    registry = registry or SchemaRegistry()
    issues: list[ValidationIssue] = []
    source = family.get("source") if isinstance(family, Mapping) else None
    if not isinstance(source, dict):
        return make_report(
            [ValidationIssue("PROV-000", "/source", "Episode family source is missing.")],
            bridge_hash=safe_sha256_json(data),
        )
    try:
        expected_source = episode_source_from_verified_asset(
            data, manifest, registry=registry
        )
    except ProvenanceBridgeError as exc:
        issues.extend(exc.report.issues)
        expected_source = None
    if expected_source is not None:
        identity_fields = (
            "asset_id",
            "manifest_asset_id",
            "manifest_revision",
            "rights_decision_id",
            "access_class",
        )
        if any(source.get(name) != expected_source[name] for name in identity_fields):
            _issue(
                issues,
                "PROV-001",
                "/source",
                "Episode source identity, manifest revision, rights decision, or access class does not match the verified asset.",
            )
        if (
            source.get("content_hash") != expected_source["content_hash"]
            or source.get("duration_s") != expected_source["duration_s"]
        ):
            _issue(
                issues,
                "PROV-002",
                "/source",
                "Episode content hash or duration does not match the verified asset.",
            )
        expected_streams = {
            item["stream_id"]: item for item in expected_source["streams"]
        }
        actual_streams = source.get("streams")
        if not isinstance(actual_streams, list):
            actual_streams = []
        actual_by_id = {
            item.get("stream_id"): item
            for item in actual_streams
            if isinstance(item, dict)
        }
        if set(actual_by_id) != set(expected_streams):
            _issue(
                issues,
                "PROV-002",
                "/source/streams",
                "Episode stream IDs do not exactly match the verified stream set.",
            )
        for stream_id, expected in expected_streams.items():
            actual = actual_by_id.get(stream_id, {})
            if any(
                actual.get(name) != expected.get(name)
                for name in ("kind", "language", "hash")
            ):
                _issue(
                    issues,
                    "PROV-002",
                    "/source/streams",
                    f"Episode stream {stream_id} metadata or hash is tampered.",
                    stream_id,
                )

    raw_stream_records = data.get("streams", [])
    if not isinstance(raw_stream_records, list):
        raw_stream_records = []
    stream_records = {
        item.get("stream_id"): item
        for item in raw_stream_records
        if isinstance(item, dict) and isinstance(item.get("stream_id"), str)
    }
    raw_transformations = data.get("transformations", [])
    if not isinstance(raw_transformations, list):
        raw_transformations = []
    transformations = {
        item.get("transformation_id"): item
        for item in raw_transformations
        if isinstance(item, dict) and isinstance(item.get("transformation_id"), str)
    }
    lineage = data.get("lineage", {})
    lineage_is_derived = (
        isinstance(lineage, dict) and lineage.get("relationship") == "derived"
    )
    lineage_segments = []
    if lineage_is_derived:
        for parent in lineage.get("parents", []):
            if isinstance(parent, dict):
                mapping = parent.get("source_time_mapping", {})
                if isinstance(mapping, dict) and isinstance(mapping.get("segments"), list):
                    lineage_segments.extend(mapping["segments"])

    graph = family.get("claim_evidence_graph", {})
    evidence_units = (
        graph.get("evidence_units", []) if isinstance(graph, dict) else []
    )
    duration = source.get("duration_s")
    for index, unit in enumerate(evidence_units):
        if not isinstance(unit, dict):
            continue
        pointer = f"/claim_evidence_graph/evidence_units/{index}"
        stream_id = unit.get("stream_id")
        stream = stream_records.get(stream_id)
        if stream is None:
            _issue(
                issues,
                "PROV-004",
                f"{pointer}/stream_id",
                f"Evidence stream {stream_id!r} does not resolve in the verified asset.",
            )
        provenance = unit.get("provenance", {})
        if not isinstance(provenance, dict):
            provenance = {}
        if stream is not None and provenance.get("stream_hash") != stream.get("sha256"):
            _issue(
                issues,
                "PROV-002",
                f"{pointer}/provenance/stream_hash",
                "Evidence stream hash does not match the verified stream.",
                str(unit.get("evidence_id", "")),
                str(stream_id or ""),
            )
        acquired_asset = data.get("acquired_asset", {})
        if not isinstance(acquired_asset, dict):
            acquired_asset = {}
        if provenance.get("asset_id") != acquired_asset.get("asset_id"):
            _issue(
                issues,
                "PROV-001",
                f"{pointer}/provenance/asset_id",
                "Evidence asset ID does not match the verified acquired asset.",
            )
        transformation_ids = provenance.get("transformation_ids")
        if not isinstance(transformation_ids, list):
            transformation_ids = []
        resolved_transformations: list[dict[str, Any]] = []
        for transformation_id in transformation_ids:
            transformation = transformations.get(transformation_id)
            if transformation is None:
                _issue(
                    issues,
                    "PROV-004",
                    f"{pointer}/provenance/transformation_ids",
                    f"Unknown transformation ID {transformation_id}.",
                    str(unit.get("evidence_id", "")),
                    str(transformation_id),
                )
                continue
            involved_streams = set(transformation.get("input_stream_ids", [])) | set(
                transformation.get("output_stream_ids", [])
            )
            if stream_id not in involved_streams:
                _issue(
                    issues,
                    "PROV-004",
                    f"{pointer}/provenance/transformation_ids",
                    f"Transformation {transformation_id} is unrelated to stream {stream_id}.",
                    str(unit.get("evidence_id", "")),
                    str(transformation_id),
                )
            resolved_transformations.append(transformation)
        if stream is not None and stream.get("role") == "derived":
            declared = set(transformation_ids)
            required = set(stream.get("transformation_ids", []))
            if not required or not required <= declared:
                _issue(
                    issues,
                    "PROV-004",
                    f"{pointer}/provenance/transformation_ids",
                    "Evidence on a derived stream must declare its stream transformations.",
                )

        intervals = unit.get("intervals")
        if not isinstance(intervals, list):
            intervals = []
        for interval_index, interval in enumerate(intervals):
            interval_pointer = f"{pointer}/intervals/{interval_index}"
            if not isinstance(interval, dict):
                continue
            start, end = interval.get("start_s"), interval.get("end_s")
            if not (
                isinstance(start, (int, float))
                and not isinstance(start, bool)
                and math.isfinite(start)
                and isinstance(end, (int, float))
                and not isinstance(end, bool)
                and math.isfinite(end)
                and end > start
            ):
                _issue(
                    issues,
                    "TIME-001",
                    interval_pointer,
                    "Evidence interval must be finite and strictly increasing.",
                )
                continue
            stream_duration = stream.get("duration_s") if stream is not None else None
            if (
                start < 0
                or not isinstance(duration, (int, float))
                or end > duration
                or not isinstance(stream_duration, (int, float))
                or end > stream_duration
            ):
                _issue(
                    issues,
                    "TIME-002",
                    interval_pointer,
                    "Evidence interval exceeds the verified asset or stream duration.",
                )
            if lineage_is_derived and not _interval_covered(
                start, end, lineage_segments, coordinate="derived"
            ):
                _issue(
                    issues,
                    "TIME-004",
                    interval_pointer,
                    "Derived-asset evidence interval lacks an auditable parent source-time mapping.",
                )
            for transformation in resolved_transformations:
                mapping = transformation.get("source_time_mapping", {})
                segments = (
                    mapping.get("segments", []) if isinstance(mapping, dict) else []
                )
                if not _interval_covered(
                    start, end, segments, coordinate="derived"
                ):
                    _issue(
                        issues,
                        "TIME-004",
                        interval_pointer,
                        f"Evidence interval is not covered by transformation {transformation.get('transformation_id')} source-time mapping.",
                        str(unit.get("evidence_id", "")),
                        str(transformation.get("transformation_id", "")),
                    )

    return make_report(
        issues,
        bridge_version=data.get("bridge_version"),
        bridge_hash=safe_sha256_json(data),
        manifest_hash=safe_sha256_json(dict(manifest))
        if isinstance(manifest, Mapping)
        else None,
    )
