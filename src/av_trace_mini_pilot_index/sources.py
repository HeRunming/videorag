"""Strict source-plan loader for the four-source mini-pilot index."""

from __future__ import annotations

import hashlib
import json
import math
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

PLAN_RELATIVE_PATH = Path("data/rehearsal_plan/mini_pilot_full_timeline_v1.json")
EXPECTED_SCHEMA_VERSION = "av-trace.mini-pilot-full-timeline-plan/1.0"
EXPECTED_SOURCE_COUNT = 4
EXPECTED_SOURCE_IDS = (
    "SG-OXFORD-QM-001",
    "SG-OXFORD-DHL-CONSCIOUSNESS",
    "SG-MIT-RES12-003-L01",
    "SG-YALE-PHYS200-L01",
)
EXPECTED_SOURCE_ROOT = "data/restricted/mini_pilot_sources_v1"
EXPECTED_ACQUISITION_MANIFEST = (
    "data/restricted/mini_pilot_sources_v1/acquisition_manifest.json"
)
EXPECTED_OUTPUT_ROOT = "data/restricted/mini_pilot_index_v1"
EXPECTED_TOTALS = {
    "base_cells": 3208,
    "fine_windows": 3204,
    "context_windows": 800,
    "temporal_segments": 4004,
    "whisper_chunks": 430,
    "ast_fine_calls": 3204,
    "clip_frame_forwards": 3208,
    "checkpoint_count": 16,
    "maximum_modality_segment_records": 12012,
}
EXPECTED_LAYERS = ("speech", "ambient", "vision_routing", "vision_clip")
EXPECTED_SEARCH_RECORD_ALLOWLIST = {
    "record_id",
    "source_ref",
    "source_sha256",
    "segment_id",
    "modality",
    "scale",
    "start_us",
    "end_us",
    "binding_cell_ids",
    "search_payload",
    "searchable",
    "exclusion_reason",
}
EXPECTED_MODELS = {
    "speech": {
        "model_id": "openai/whisper-tiny.en",
        "revision": "87c7102498dcde7456f24cfd30239ca606ed9063",
        "snapshot_path": "data/restricted/noaa01/models/whisper-tiny.en-87c7102",
        "snapshot_hash": (
            "sha256:1e098354f3cbd9f339ef8fbdcc0e82ff238786bffa25794493ebe32830f4518a"
        ),
        "weights_path": (
            "data/restricted/noaa01/models/whisper-tiny.en-87c7102/model.safetensors"
        ),
        "weights_sha256": (
            "db59695928ded6043adaef491a53ef4e12da9611184d77c53baa691a60b958ad"
        ),
    },
    "ambient": {
        "model_id": "MIT/ast-finetuned-audioset-10-10-0.4593",
        "revision": "f826b80d28226b62986cc218e5cec390b1096902",
        "snapshot_path": "data/restricted/noaa01/models/ast-audioset-f826b80",
        "snapshot_hash": (
            "sha256:acb9247d5f2548c121e7fd213347586e1b781fd8dc329e27505dd269a69cccbc"
        ),
        "weights_path": (
            "data/restricted/noaa01/models/ast-audioset-f826b80/model.safetensors"
        ),
        "weights_sha256": (
            "ae0c1e2ad4e1381d851fa9bf298ba13ebc9c5a914cdee2dbe427a6583869924d"
        ),
    },
    "vision_semantic": {
        "model_id": "openai/clip-vit-base-patch32",
        "revision": "3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268",
        "snapshot_path": (
            "data/restricted/noaa01/models/clip-vit-base-patch32-3d74acf"
        ),
        "snapshot_hash": (
            "sha256:2c29598276753a41d293ca65ef8fe60287ed62d8cd94b0ee77ec38ecb41a20f5"
        ),
        "weights_path": (
            "data/restricted/noaa01/models/clip-vit-base-patch32-3d74acf/"
            "pytorch_model.bin"
        ),
        "weights_sha256": (
            "a63082132ba4f97a80bea76823f544493bffa8082296d62d71581a4feff1576f"
        ),
    },
    "vision_routing": {
        "model_id": "opencv-routing/1.0",
        "revision": "2.0",
        "haar_snapshot_path": (
            "data/restricted/noaa01/models/opencv-haarcascade-frontalface-default.xml"
        ),
        "haar_sha256": (
            "0f7d4527844eb514d4a4948e822da90fbb16a34a0bbbbc6adc6498747a5aafb0"
        ),
    },
}

_PRIVATE_KEYS = {
    "answer",
    "answers",
    "claim",
    "claim_id",
    "evaluation",
    "evaluation_label",
    "evaluator",
    "evaluator_private",
    "evidence",
    "evidence_id",
    "family",
    "family_id",
    "gold",
    "gold_annotation",
    "intervention",
    "intervention_id",
    "label",
    "labels",
    "question",
    "review_id",
    "state",
    "state_role",
    "support_set",
    "support_sets",
}
REQUIRED_SEARCH_RECORD_FORBIDDEN_FIELDS = {
    "title",
    "filename",
    "path",
    "url",
    "source_url",
    "license",
    "rights",
    "rights_flags",
    "attribution",
    "commercial_use",
    "privacy",
    "question",
    "answer",
    "family_id",
    "review_id",
    "evidence_id",
    "claim_id",
    "state",
    "state_role",
    "intervention",
    "intervention_id",
    "evaluation",
    "label",
    "gold",
}


class SourcePlanError(ValueError):
    """Raised when the source plan or an acquired source fails closed."""


@dataclass(frozen=True)
class StreamExpectation:
    """Frozen stream identity needed by the future index builder."""

    kind: str
    index: int
    codec: str
    sample_rate_hz: int | None = None
    channels: int | None = None
    width: int | None = None
    height: int | None = None
    average_rate: str | None = None


@dataclass(frozen=True)
class TranscriptSidecar:
    """An official sidecar retained for verification, never search seeding."""

    role: str
    format: str
    path: Path
    bytes: int
    sha256: str
    timing: str
    index_use: str


@dataclass(frozen=True)
class SourceSpec:
    """Verified source identity and deterministic lattice counts."""

    source_id: str
    source_manifest_path: Path
    source_directory: Path
    media_path: Path
    media_bytes: int
    media_sha256: str
    duration_seconds: float
    duration_tolerance_seconds: float
    streams: tuple[StreamExpectation, ...]
    transcript_sidecars: tuple[TranscriptSidecar, ...]
    expected_counts: Mapping[str, int]


@dataclass(frozen=True)
class SourcePlan:
    """Verified Workstream-A source plan."""

    repo_root: Path
    plan_path: Path
    output_root: Path
    allowed_restricted_source_root: Path
    acquisition_manifest_path: Path
    sources: tuple[SourceSpec, ...]
    totals: Mapping[str, int | float]
    model_snapshots: Mapping[str, Any]
    index_policy: Mapping[str, Any]
    official_transcript_sidecar_policy: Mapping[str, Any]
    raw: Mapping[str, Any]


def _fail(code: str, detail: str = "") -> None:
    suffix = f":{detail}" if detail else ""
    raise SourcePlanError(f"{code}{suffix}")


def _read_json(path: Path, code: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        _fail(code, path.as_posix())
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourcePlanError(f"{code}:{path.as_posix()}") from exc
    if not isinstance(value, dict):
        _fail(code, path.as_posix())
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_hex_sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _repo_relative_path(
    repo_root: Path,
    value: Any,
    *,
    code: str,
    allowed_root: Path | None = None,
) -> Path:
    if not isinstance(value, str) or not value:
        _fail(code, repr(value))
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts or pure.as_posix() != value:
        _fail(code, value)
    candidate = repo_root.joinpath(*pure.parts)
    try:
        candidate.resolve(strict=False).relative_to(repo_root)
    except ValueError:
        _fail(code, value)
    if allowed_root is not None:
        try:
            candidate.resolve(strict=False).relative_to(allowed_root.resolve())
        except ValueError:
            _fail("SOURCE_OUTSIDE_ALLOWED_ROOT", value)
    return candidate


def _verify_mode(path: Path, expected: int, code: str) -> None:
    observed = stat.S_IMODE(path.stat().st_mode)
    if observed != expected:
        _fail(code, f"{path.as_posix()}:{observed:04o}")


def _verify_file(
    path: Path,
    *,
    expected_bytes: Any,
    expected_sha256: Any,
    hash_files: bool,
) -> None:
    if not path.is_file() or path.is_symlink():
        _fail("SOURCE_FILE_MISSING_OR_UNSAFE", path.as_posix())
    _verify_mode(path, 0o600, "SOURCE_FILE_MODE_MISMATCH")
    if not isinstance(expected_bytes, int) or expected_bytes <= 0:
        _fail("INVALID_EXPECTED_BYTES", path.as_posix())
    if path.stat().st_size != expected_bytes:
        _fail("SOURCE_SIZE_MISMATCH", path.as_posix())
    if not _is_hex_sha256(expected_sha256):
        _fail("INVALID_EXPECTED_SHA256", path.as_posix())
    if hash_files and _sha256(path) != expected_sha256:
        _fail("SOURCE_HASH_MISMATCH", path.as_posix())


def _find_source(
    acquisition_manifest: Mapping[str, Any], source_id: str
) -> Mapping[str, Any]:
    matches = [
        item
        for item in acquisition_manifest.get("sources", [])
        if isinstance(item, dict) and item.get("source_group_id") == source_id
    ]
    if len(matches) != 1:
        _fail("ACQUISITION_SOURCE_CARDINALITY", source_id)
    return matches[0]


def _payload_by_path(
    source_manifest: Mapping[str, Any], path: str
) -> Mapping[str, Any]:
    matches = [
        item
        for item in source_manifest.get("files", [])
        if isinstance(item, dict) and item.get("custodian_path") == path
    ]
    if len(matches) != 1:
        _fail("SOURCE_MANIFEST_FILE_CARDINALITY", path)
    return matches[0]


def _aggregate_payload_by_path(
    source_record: Mapping[str, Any], path: str
) -> Mapping[str, Any]:
    matches = [
        item
        for item in source_record.get("payload_files", [])
        if isinstance(item, dict) and item.get("custodian_path") == path
    ]
    if len(matches) != 1:
        _fail("ACQUISITION_PAYLOAD_CARDINALITY", path)
    return matches[0]


def _normalize_manifest_role(role: Any) -> str:
    if role == "video":
        return "primary_video"
    if isinstance(role, str):
        return role
    _fail("INVALID_SOURCE_MANIFEST_ROLE", repr(role))
    raise AssertionError("unreachable")


def _stream_signature(stream: Mapping[str, Any]) -> dict[str, Any]:
    kind = stream.get("type")
    if kind == "audio":
        return {
            "index": stream.get("index"),
            "codec": stream.get("codec"),
            "sample_rate_hz": stream.get("sample_rate"),
            "channels": stream.get("channels"),
        }
    if kind == "video":
        return {
            "index": stream.get("index"),
            "codec": stream.get("codec"),
            "width": stream.get("width"),
            "height": stream.get("height"),
            "average_rate": stream.get("average_rate"),
        }
    _fail("UNEXPECTED_STREAM_TYPE", repr(kind))
    raise AssertionError("unreachable")


def _expected_streams(
    source_entry: Mapping[str, Any],
) -> tuple[StreamExpectation, ...]:
    stream_groups = source_entry["media"].get("stream_expectations")
    if not isinstance(stream_groups, dict):
        _fail("STREAM_EXPECTATIONS_MISSING", source_entry["source_id"])
    result: list[StreamExpectation] = []
    for kind in ("audio", "video"):
        values = stream_groups.get(kind)
        if not isinstance(values, list) or len(values) != 1:
            _fail("STREAM_EXPECTATION_CARDINALITY", source_entry["source_id"])
        item = values[0]
        if not isinstance(item, dict):
            _fail("INVALID_STREAM_EXPECTATION", source_entry["source_id"])
        result.append(StreamExpectation(kind=kind, **item))
    return tuple(result)


def _verify_streams(
    expected: tuple[StreamExpectation, ...],
    acquisition_source: Mapping[str, Any],
    source_manifest: Mapping[str, Any],
    source_id: str,
) -> None:
    aggregate_streams = acquisition_source.get("decode_facts", {}).get("streams")
    source_streams = source_manifest.get("video_validation", {}).get("streams")
    if not isinstance(aggregate_streams, list) or not isinstance(source_streams, list):
        _fail("STREAM_FACTS_MISSING", source_id)
    for observed_streams in (aggregate_streams, source_streams):
        if len(observed_streams) != 2:
            _fail("STREAM_COUNT_MISMATCH", source_id)
        observed = {
            item.get("type"): _stream_signature(item)
            for item in observed_streams
            if isinstance(item, dict)
        }
        if set(observed) != {"audio", "video"}:
            _fail("STREAM_TYPE_MISMATCH", source_id)
        for item in expected:
            expected_signature = {
                key: value
                for key, value in {
                    "index": item.index,
                    "codec": item.codec,
                    "sample_rate_hz": item.sample_rate_hz,
                    "channels": item.channels,
                    "width": item.width,
                    "height": item.height,
                    "average_rate": item.average_rate,
                }.items()
                if value is not None
            }
            if observed[item.kind] != expected_signature:
                _fail("STREAM_EXPECTATION_MISMATCH", source_id)


def _computed_counts(duration_seconds: float) -> dict[str, int]:
    return {
        "base_cells": math.ceil(duration_seconds / 4),
        "fine_windows": math.floor(duration_seconds / 4),
        "context_windows": math.floor(duration_seconds / 16),
        "temporal_segments": (
            math.floor(duration_seconds / 4) + math.floor(duration_seconds / 16)
        ),
        "whisper_chunks": math.ceil(duration_seconds / 30),
        "checkpoints": len(EXPECTED_LAYERS),
    }


def _reject_private_fields(value: Any, location: str = "plan") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in _PRIVATE_KEYS:
                _fail("EVALUATOR_PRIVATE_FIELD", f"{location}.{key}")
            _reject_private_fields(child, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_private_fields(child, f"{location}[{index}]")


def _verify_acquisition_manifest(
    plan: Mapping[str, Any],
    repo_root: Path,
    *,
    hash_files: bool,
) -> tuple[Path, dict[str, Any], Path]:
    scope = plan.get("scope")
    if not isinstance(scope, dict):
        _fail("SCOPE_MISSING")
    if scope.get("allowed_restricted_source_root") != EXPECTED_SOURCE_ROOT:
        _fail("ALLOWED_RESTRICTED_ROOT_MISMATCH")
    if scope.get("acquisition_manifest_path") != EXPECTED_ACQUISITION_MANIFEST:
        _fail("ACQUISITION_MANIFEST_PATH_MISMATCH")
    allowed_root = _repo_relative_path(
        repo_root,
        scope.get("allowed_restricted_source_root"),
        code="INVALID_ALLOWED_RESTRICTED_ROOT",
    )
    if not allowed_root.is_dir() or allowed_root.is_symlink():
        _fail("ALLOWED_RESTRICTED_ROOT_MISSING", allowed_root.as_posix())
    _verify_mode(allowed_root, 0o700, "ALLOWED_RESTRICTED_ROOT_MODE_MISMATCH")
    acquisition_path = _repo_relative_path(
        repo_root,
        scope.get("acquisition_manifest_path"),
        code="INVALID_ACQUISITION_MANIFEST_PATH",
        allowed_root=allowed_root,
    )
    acquisition = _read_json(acquisition_path, "ACQUISITION_MANIFEST_INVALID")
    _verify_mode(acquisition_path, 0o600, "ACQUISITION_MANIFEST_MODE_MISMATCH")
    expected_hash = scope.get("acquisition_manifest_sha256")
    if not _is_hex_sha256(expected_hash):
        _fail("INVALID_ACQUISITION_MANIFEST_SHA256")
    if hash_files and _sha256(acquisition_path) != expected_hash:
        _fail("ACQUISITION_MANIFEST_HASH_MISMATCH")
    if acquisition.get("decision") != scope.get("acquisition_decision_required"):
        _fail("ACQUISITION_DECISION_MISMATCH")
    if (
        acquisition.get("source_count") != EXPECTED_SOURCE_COUNT
        or acquisition.get("complete_source_count") != EXPECTED_SOURCE_COUNT
        or len(acquisition.get("sources", [])) != EXPECTED_SOURCE_COUNT
    ):
        _fail("ACQUISITION_SOURCE_COUNT_MISMATCH")
    for field in ("failed_transfer_accounting", "incomplete_transfer_accounting"):
        accounting = acquisition.get(field)
        if not isinstance(accounting, dict) or accounting.get("count") != 0:
            _fail("ACQUISITION_TRANSFER_FAILURE", field)
    incomplete = acquisition["incomplete_transfer_accounting"]
    if incomplete.get("retained_resumable_partials") != 0:
        _fail("ACQUISITION_PARTIALS_REMAIN")
    return acquisition_path, acquisition, allowed_root


def _verify_model_snapshots(
    plan: Mapping[str, Any], repo_root: Path, *, hash_files: bool
) -> None:
    models = plan.get("model_snapshots")
    if not isinstance(models, dict) or set(models) != set(EXPECTED_MODELS):
        _fail("MODEL_SNAPSHOT_SET_MISMATCH")
    for name, expected in EXPECTED_MODELS.items():
        model = models.get(name)
        if not isinstance(model, dict):
            _fail("MODEL_SNAPSHOT_INVALID", name)
        for key, expected_value in expected.items():
            if model.get(key) != expected_value:
                _fail("MODEL_SNAPSHOT_IDENTITY_MISMATCH", f"{name}:{key}")
        if name == "vision_routing":
            asset_path = _repo_relative_path(
                repo_root,
                model["haar_snapshot_path"],
                code="INVALID_MODEL_ASSET_PATH",
            )
            _verify_file(
                asset_path,
                expected_bytes=asset_path.stat().st_size,
                expected_sha256=model["haar_sha256"],
                hash_files=hash_files,
            )
            continue
        snapshot_path = _repo_relative_path(
            repo_root,
            model["snapshot_path"],
            code="INVALID_MODEL_SNAPSHOT_PATH",
        )
        if not snapshot_path.is_dir() or snapshot_path.is_symlink():
            _fail("MODEL_SNAPSHOT_MISSING_OR_UNSAFE", name)
        _verify_mode(snapshot_path, 0o700, "MODEL_SNAPSHOT_MODE_MISMATCH")
        weights_path = _repo_relative_path(
            repo_root,
            model["weights_path"],
            code="INVALID_MODEL_WEIGHTS_PATH",
            allowed_root=snapshot_path,
        )
        _verify_file(
            weights_path,
            expected_bytes=weights_path.stat().st_size,
            expected_sha256=model["weights_sha256"],
            hash_files=hash_files,
        )


def _verify_source(
    source_entry: Mapping[str, Any],
    acquisition_manifest: Mapping[str, Any],
    repo_root: Path,
    allowed_root: Path,
    *,
    hash_files: bool,
) -> SourceSpec:
    source_id = source_entry.get("source_id")
    if not isinstance(source_id, str) or not source_id:
        _fail("INVALID_SOURCE_ID")
    source_directory = _repo_relative_path(
        repo_root,
        source_entry.get("source_directory"),
        code="INVALID_SOURCE_DIRECTORY",
        allowed_root=allowed_root,
    )
    if not source_directory.is_dir() or source_directory.is_symlink():
        _fail("SOURCE_DIRECTORY_MISSING_OR_UNSAFE", source_id)
    _verify_mode(source_directory, 0o700, "SOURCE_DIRECTORY_MODE_MISMATCH")

    source_manifest_path = _repo_relative_path(
        repo_root,
        source_entry.get("source_manifest_path"),
        code="INVALID_SOURCE_MANIFEST_PATH",
        allowed_root=allowed_root,
    )
    if source_manifest_path.parent != source_directory:
        _fail("SOURCE_MANIFEST_DIRECTORY_MISMATCH", source_id)
    source_manifest = _read_json(source_manifest_path, "SOURCE_MANIFEST_INVALID")
    _verify_file(
        source_manifest_path,
        expected_bytes=source_manifest_path.stat().st_size,
        expected_sha256=source_entry.get("source_manifest_sha256"),
        hash_files=hash_files,
    )
    if source_manifest.get("source_group_id") != source_id:
        _fail("SOURCE_MANIFEST_ID_MISMATCH", source_id)
    if source_manifest.get("source_directory") != source_entry.get("source_directory"):
        _fail("SOURCE_MANIFEST_ROOT_MISMATCH", source_id)
    if source_manifest.get("status") != "COMPLETE_VALIDATED_PROMOTED":
        _fail("SOURCE_MANIFEST_STATUS_MISMATCH", source_id)

    acquisition_source = _find_source(acquisition_manifest, source_id)
    if acquisition_source.get("source_directory") != source_entry.get(
        "source_directory"
    ):
        _fail("ACQUISITION_SOURCE_ROOT_MISMATCH", source_id)
    if acquisition_source.get("status") != "COMPLETE_VALIDATED_PROMOTED":
        _fail("ACQUISITION_SOURCE_STATUS_MISMATCH", source_id)

    files = source_manifest.get("files")
    if not isinstance(files, list):
        _fail("SOURCE_MANIFEST_FILES_MISSING", source_id)
    video_roles = [
        item
        for item in files
        if isinstance(item, dict)
        and _normalize_manifest_role(item.get("role")) == "primary_video"
    ]
    if len(video_roles) != 1:
        _fail("PRIMARY_VIDEO_ROLE_CARDINALITY", source_id)
    aggregate_video_roles = [
        item
        for item in acquisition_source.get("payload_files", [])
        if isinstance(item, dict) and item.get("role") == "primary_video"
    ]
    if len(aggregate_video_roles) != 1:
        _fail("ACQUISITION_VIDEO_ROLE_CARDINALITY", source_id)

    media = source_entry.get("media")
    if not isinstance(media, dict) or media.get("role") != "primary_video":
        _fail("PLAN_VIDEO_ROLE_MISMATCH", source_id)
    media_path_text = media.get("path")
    media_path = _repo_relative_path(
        repo_root,
        media_path_text,
        code="INVALID_MEDIA_PATH",
        allowed_root=source_directory,
    )
    _verify_file(
        media_path,
        expected_bytes=media.get("bytes"),
        expected_sha256=media.get("sha256"),
        hash_files=hash_files,
    )
    source_media = _payload_by_path(source_manifest, media_path_text)
    aggregate_media = _aggregate_payload_by_path(acquisition_source, media_path_text)
    if _normalize_manifest_role(source_media.get("role")) != "primary_video":
        _fail("SOURCE_MANIFEST_VIDEO_ROLE_MISMATCH", source_id)
    if aggregate_media.get("role") != "primary_video":
        _fail("ACQUISITION_VIDEO_ROLE_MISMATCH", source_id)
    for record in (source_media, aggregate_media):
        if record.get("bytes") != media.get("bytes") or record.get(
            "sha256"
        ) != media.get("sha256"):
            _fail("MEDIA_IDENTITY_MANIFEST_MISMATCH", source_id)

    duration = media.get("duration_seconds")
    tolerance = media.get("duration_tolerance_seconds")
    if (
        not isinstance(duration, (int, float))
        or duration <= 0
        or not isinstance(tolerance, (int, float))
        or tolerance < 0
    ):
        _fail("INVALID_DURATION", source_id)
    aggregate_duration = acquisition_source.get("decode_facts", {}).get(
        "duration_seconds"
    )
    source_duration = source_manifest.get("video_validation", {}).get(
        "duration_seconds"
    )
    if any(
        not isinstance(value, (int, float))
        or abs(float(value) - float(duration)) > float(tolerance)
        for value in (aggregate_duration, source_duration)
    ):
        _fail("DURATION_MISMATCH", source_id)

    streams = _expected_streams(source_entry)
    _verify_streams(streams, acquisition_source, source_manifest, source_id)

    sidecars_value = source_entry.get("official_transcript_sidecars")
    if not isinstance(sidecars_value, list) or not sidecars_value:
        _fail("OFFICIAL_SIDECARS_MISSING", source_id)
    sidecars: list[TranscriptSidecar] = []
    planned_sidecar_paths: set[str] = set()
    for item in sidecars_value:
        if not isinstance(item, dict):
            _fail("INVALID_OFFICIAL_SIDECAR", source_id)
        sidecar_path_text = item.get("path")
        sidecar_path = _repo_relative_path(
            repo_root,
            sidecar_path_text,
            code="INVALID_SIDECAR_PATH",
            allowed_root=source_directory,
        )
        _verify_file(
            sidecar_path,
            expected_bytes=item.get("bytes"),
            expected_sha256=item.get("sha256"),
            hash_files=hash_files,
        )
        source_sidecar = _payload_by_path(source_manifest, sidecar_path_text)
        aggregate_sidecar = _aggregate_payload_by_path(
            acquisition_source, sidecar_path_text
        )
        for record in (source_sidecar, aggregate_sidecar):
            if (
                record.get("role") != item.get("role")
                or record.get("bytes") != item.get("bytes")
                or record.get("sha256") != item.get("sha256")
            ):
                _fail("SIDECAR_IDENTITY_MANIFEST_MISMATCH", source_id)
        if item.get("index_use") != "verification_only":
            _fail("SIDECAR_INDEX_POLICY_MISMATCH", source_id)
        planned_sidecar_paths.add(sidecar_path_text)
        sidecars.append(
            TranscriptSidecar(
                role=item["role"],
                format=item["format"],
                path=sidecar_path,
                bytes=item["bytes"],
                sha256=item["sha256"],
                timing=item["timing"],
                index_use=item["index_use"],
            )
        )
    manifest_sidecar_paths = {
        item["custodian_path"]
        for item in files
        if isinstance(item, dict) and item.get("role") in {"transcript", "captions"}
    }
    if planned_sidecar_paths != manifest_sidecar_paths:
        _fail("OFFICIAL_SIDECAR_SET_MISMATCH", source_id)

    expected_counts = source_entry.get("expected_counts")
    if not isinstance(expected_counts, dict):
        _fail("SOURCE_COUNTS_MISSING", source_id)
    computed_counts = _computed_counts(float(duration))
    if expected_counts != computed_counts:
        _fail("SOURCE_COUNT_MISMATCH", source_id)

    return SourceSpec(
        source_id=source_id,
        source_manifest_path=source_manifest_path,
        source_directory=source_directory,
        media_path=media_path,
        media_bytes=media["bytes"],
        media_sha256=media["sha256"],
        duration_seconds=float(duration),
        duration_tolerance_seconds=float(tolerance),
        streams=streams,
        transcript_sidecars=tuple(sidecars),
        expected_counts=dict(expected_counts),
    )


def _verify_totals(
    plan: Mapping[str, Any],
    sources: tuple[SourceSpec, ...],
    acquisition_manifest: Mapping[str, Any],
) -> Mapping[str, int | float]:
    totals = plan.get("totals")
    if not isinstance(totals, dict):
        _fail("TOTALS_MISSING")
    for key, expected in EXPECTED_TOTALS.items():
        if totals.get(key) != expected:
            _fail("FROZEN_TOTAL_MISMATCH", key)
    computed = {
        key: sum(source.expected_counts[source_key] for source in sources)
        for key, source_key in {
            "base_cells": "base_cells",
            "fine_windows": "fine_windows",
            "context_windows": "context_windows",
            "temporal_segments": "temporal_segments",
            "whisper_chunks": "whisper_chunks",
            "checkpoint_count": "checkpoints",
        }.items()
    }
    computed["ast_fine_calls"] = computed["fine_windows"]
    computed["clip_frame_forwards"] = computed["base_cells"]
    computed["maximum_modality_segment_records"] = computed["temporal_segments"] * 3
    if computed != EXPECTED_TOTALS:
        _fail("COMPUTED_TOTAL_MISMATCH", repr(computed))
    if totals.get("primary_media_bytes") != sum(
        source.media_bytes for source in sources
    ):
        _fail("PRIMARY_MEDIA_BYTE_TOTAL_MISMATCH")
    if totals.get("official_transcript_sidecar_bytes") != sum(
        sidecar.bytes for source in sources for sidecar in source.transcript_sidecars
    ):
        _fail("SIDECAR_BYTE_TOTAL_MISMATCH")
    duration = sum(source.duration_seconds for source in sources)
    if abs(float(totals.get("duration_seconds", -1)) - duration) > 0.000001:
        _fail("DURATION_TOTAL_MISMATCH")
    expected_payload_bytes = (
        totals["primary_media_bytes"] + totals["official_transcript_sidecar_bytes"]
    )
    if acquisition_manifest.get("aggregate_payload_bytes") != expected_payload_bytes:
        _fail("ACQUISITION_PAYLOAD_TOTAL_MISMATCH")
    return totals


def _verify_policy(plan: Mapping[str, Any]) -> None:
    policy = plan.get("official_transcript_sidecar_policy")
    if not isinstance(policy, dict):
        _fail("SIDECAR_POLICY_MISSING")
    if (
        policy.get("searchable") is not False
        or policy.get("citable") is not False
        or policy.get("training_label") is not False
        or policy.get("family_or_evaluation_input") is not False
    ):
        _fail("SIDECAR_POLICY_NOT_FAIL_CLOSED")
    scope = plan.get("scope", {})
    forbidden = scope.get("forbidden_downstream_stages")
    if not isinstance(forbidden, list) or not {
        "candidate-family generation",
        "evaluation",
    }.issubset(forbidden):
        _fail("DOWNSTREAM_STAGE_BOUNDARY_MISSING")
    checkpointing = plan.get("checkpointing")
    if (
        not isinstance(checkpointing, dict)
        or checkpointing.get("layers_per_source") != list(EXPECTED_LAYERS)
        or checkpointing.get("expected_checkpoint_count") != 16
    ):
        _fail("CHECKPOINT_CONTRACT_MISMATCH")
    index_policy = plan.get("index_policy")
    if not isinstance(index_policy, dict):
        _fail("INDEX_POLICY_MISSING")
    if set(index_policy.get("search_record_allowlist", ())) != (
        EXPECTED_SEARCH_RECORD_ALLOWLIST
    ):
        _fail("SEARCH_RECORD_ALLOWLIST_MISMATCH")
    forbidden_fields = index_policy.get("search_record_forbidden_fields")
    if not isinstance(forbidden_fields, list) or not (
        REQUIRED_SEARCH_RECORD_FORBIDDEN_FIELDS.issubset(forbidden_fields)
    ):
        _fail("SEARCH_RECORD_FORBIDDEN_FIELDS_MISSING")
    if (
        index_policy.get("speech", {}).get("source") != "Whisper only"
        or index_policy.get("speech", {}).get("official_sidecars_searchable")
        is not False
        or index_policy.get("vision", {}).get("generated_captions_searchable")
        is not False
    ):
        _fail("INDEX_POLICY_NOT_FAIL_CLOSED")


def load_source_plan(
    repo_root: str | Path,
    *,
    plan_path: str | Path = PLAN_RELATIVE_PATH,
    hash_files: bool = True,
) -> SourcePlan:
    """Load and strictly verify the four-source mini-pilot indexing plan.

    ``hash_files=False`` exists only for fast structural unit tests. Production
    callers must use the default and hash every acquisition manifest, source
    manifest, media object, and official transcript sidecar.
    """

    root = Path(repo_root).resolve()
    plan_candidate = Path(plan_path)
    if not plan_candidate.is_absolute():
        plan_candidate = _repo_relative_path(
            root, plan_candidate.as_posix(), code="INVALID_PLAN_PATH"
        )
    plan = _read_json(plan_candidate, "PLAN_INVALID")
    if plan.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        _fail("PLAN_SCHEMA_MISMATCH")
    if plan.get("decision") != "READY_FOR_INDEX_IMPLEMENTATION":
        _fail("PLAN_DECISION_MISMATCH")

    _reject_private_fields(plan)
    _verify_policy(plan)
    acquisition_path, acquisition, allowed_root = _verify_acquisition_manifest(
        plan, root, hash_files=hash_files
    )
    _verify_model_snapshots(plan, root, hash_files=hash_files)

    source_entries = plan.get("sources")
    if (
        not isinstance(source_entries, list)
        or len(source_entries) != EXPECTED_SOURCE_COUNT
    ):
        _fail("PLAN_SOURCE_COUNT_MISMATCH")
    source_ids = [
        entry.get("source_id") for entry in source_entries if isinstance(entry, dict)
    ]
    if tuple(source_ids) != EXPECTED_SOURCE_IDS:
        _fail("PLAN_SOURCE_IDS_MISMATCH")
    sources = tuple(
        _verify_source(
            entry,
            acquisition,
            root,
            allowed_root,
            hash_files=hash_files,
        )
        for entry in source_entries
    )
    totals = _verify_totals(plan, sources, acquisition)

    if plan["scope"].get("output_root") != EXPECTED_OUTPUT_ROOT:
        _fail("OUTPUT_ROOT_MISMATCH")
    output_root = _repo_relative_path(
        root,
        plan["scope"].get("output_root"),
        code="INVALID_OUTPUT_ROOT",
    )
    if output_root == allowed_root or allowed_root in output_root.parents:
        _fail("OUTPUT_ROOT_OVERLAPS_SOURCE_ROOT")
    if output_root.exists() and output_root.is_symlink():
        _fail("OUTPUT_ROOT_IS_SYMLINK")

    return SourcePlan(
        repo_root=root,
        plan_path=plan_candidate,
        output_root=output_root,
        allowed_restricted_source_root=allowed_root,
        acquisition_manifest_path=acquisition_path,
        sources=sources,
        totals=totals,
        model_snapshots=plan["model_snapshots"],
        index_policy=plan["index_policy"],
        official_transcript_sidecar_policy=plan["official_transcript_sidecar_policy"],
        raw=plan,
    )


__all__ = [
    "PLAN_RELATIVE_PATH",
    "SourcePlan",
    "SourcePlanError",
    "SourceSpec",
    "StreamExpectation",
    "TranscriptSidecar",
    "load_source_plan",
]
