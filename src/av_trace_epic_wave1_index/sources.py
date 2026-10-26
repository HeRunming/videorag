"""Fail-closed source-plan loader for the isolated EPIC Wave-1 index."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

PLAN_RELATIVE_PATH = Path(
    "data/rehearsal_plan/epic_wave1_full_timeline_index_v1.json"
)
EXPECTED_SCHEMA_VERSION = "av-trace.epic-wave1-full-timeline-index-plan/1.0"
EXPECTED_PLAN_ID = "AV-TRACE-EPIC-WAVE1-FULL-TIMELINE-INDEX-V1"
EXPECTED_SOURCE_IDS = ("P28_103", "P27_101")
EXPECTED_SOURCE_ROOT = "data/restricted/epic_wave1_sources_v1"
EXPECTED_ACQUISITION_MANIFEST = (
    "data/restricted/epic_wave1_sources_v1/manifests/"
    "epic_wave1_acquisition_manifest.json"
)
EXPECTED_OUTPUT_ROOT = "data/restricted/epic_wave1_index_v1"
REQUIRED_ACQUISITION_DECISION = "EPIC_WAVE1_ACQUISITION_READY"
EXPECTED_LAYERS = ("speech", "ambient", "vision_routing", "vision_clip")
PENDING_ACQUISITION_CODES = frozenset(
    {
        "ACQUISITION_MANIFEST_MISSING",
        "ACQUISITION_DECISION_MISMATCH",
        "ACQUISITION_SOURCE_COUNT_MISMATCH",
        "ACQUISITION_SOURCE_MISSING",
        "ACQUISITION_SOURCE_NOT_READY",
        "ACQUISITION_FAILURES_PRESENT",
        "ACQUISITION_INCOMPLETE_PRESENT",
        "EXACT_SHA256_MISSING",
        "OFFICIAL_MD5_MISSING",
        "MEDIA_MISSING",
        "MEDIA_SIZE_MISMATCH",
        "MEDIA_SHA256_MISMATCH",
        "MEDIA_MD5_MISMATCH",
        "MEDIA_MODE_MISMATCH",
        "SOURCE_DIRECTORY_MODE_MISMATCH",
        "DURATION_BINDING_MISSING",
        "DURATION_MISMATCH",
        "AUDIO_STREAM_NOT_VERIFIED",
        "VIDEO_STREAM_NOT_VERIFIED",
        "AV_SYNC_NOT_VERIFIED",
    }
)


class EpicWave1SourceError(ValueError):
    """Raised when the EPIC plan or acquired source fails closed."""

    @property
    def code(self) -> str:
        return str(self).split(":", 1)[0]

    @property
    def acquisition_pending(self) -> bool:
        return self.code in PENDING_ACQUISITION_CODES


@dataclass(frozen=True)
class EpicSourceSpec:
    """Verified final-media identity and deterministic lattice counts."""

    source_id: str
    source_group_id: str
    source_manifest_path: Path
    source_directory: Path
    media_path: Path
    media_bytes: int
    media_sha256: str
    official_md5: str
    duration_seconds: float
    duration_tolerance_seconds: float
    expected_counts: Mapping[str, int]


@dataclass(frozen=True)
class EpicWave1Plan:
    """Verified EPIC Wave-1 indexing plan and acquisition gate."""

    repo_root: Path
    plan_path: Path
    output_root: Path
    allowed_restricted_source_root: Path
    acquisition_manifest_path: Path
    acquisition_manifest_sha256: str
    sources: tuple[EpicSourceSpec, ...]
    totals: Mapping[str, int | float]
    model_snapshots: Mapping[str, Any]
    index_policy: Mapping[str, Any]
    raw: Mapping[str, Any]


def _fail(code: str, detail: str = "") -> None:
    raise EpicWave1SourceError(f"{code}:{detail}" if detail else code)


def _read_json(path: Path, code: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        _fail(code, path.as_posix())
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EpicWave1SourceError(f"{code}:{path.as_posix()}") from exc
    if not isinstance(value, dict):
        _fail(code, path.as_posix())
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _md5(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_hex(value: Any, length: int) -> bool:
    if not isinstance(value, str) or len(value) != length:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _repo_path(
    root: Path,
    value: Any,
    *,
    code: str,
    allowed_root: Path | None = None,
) -> Path:
    if not isinstance(value, str) or not value:
        _fail(code, repr(value))
    pure = PurePosixPath(value)
    if (
        pure.is_absolute()
        or ".." in pure.parts
        or ".staging" in pure.parts
        or pure.as_posix() != value
    ):
        _fail(code, value)
    candidate = root.joinpath(*pure.parts)
    try:
        candidate.resolve(strict=False).relative_to(root)
    except ValueError:
        _fail(code, value)
    if allowed_root is not None:
        try:
            candidate.resolve(strict=False).relative_to(allowed_root.resolve())
        except ValueError:
            _fail("SOURCE_OUTSIDE_ALLOWED_ROOT", value)
    return candidate


def _mode(path: Path, expected: int, code: str) -> None:
    if path.is_symlink() or stat.S_IMODE(path.stat().st_mode) != expected:
        _fail(code, path.as_posix())


def _count_windows(
    duration_seconds: float,
    *,
    length_seconds: int,
    stride_seconds: int,
    minimum_remaining_seconds: int,
) -> int:
    duration_us = round(duration_seconds * 1_000_000)
    length_us = length_seconds * 1_000_000
    stride_us = stride_seconds * 1_000_000
    minimum_us = minimum_remaining_seconds * 1_000_000
    count = 0
    index = 0
    while duration_us - index * stride_us >= minimum_us:
        start = index * stride_us
        if min(start + length_us, duration_us) > start:
            count += 1
        index += 1
    return count


def computed_counts(duration_seconds: float) -> dict[str, int]:
    """Return the frozen 4/8/32-second and 30-second lattice counts."""
    fine = _count_windows(
        duration_seconds,
        length_seconds=8,
        stride_seconds=4,
        minimum_remaining_seconds=4,
    )
    context = _count_windows(
        duration_seconds,
        length_seconds=32,
        stride_seconds=16,
        minimum_remaining_seconds=16,
    )
    return {
        "base_cells": _count_windows(
            duration_seconds,
            length_seconds=4,
            stride_seconds=4,
            minimum_remaining_seconds=0,
        ),
        "fine_windows": fine,
        "context_windows": context,
        "temporal_segments": fine + context,
        "whisper_chunks": math.ceil(duration_seconds / 30),
        "checkpoints": 4,
    }


def _first(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def _nested_first(mapping: Mapping[str, Any], paths: tuple[tuple[str, ...], ...]) -> Any:
    for path in paths:
        value: Any = mapping
        for key in path:
            if not isinstance(value, Mapping) or key not in value:
                break
            value = value[key]
        else:
            if value is not None:
                return value
    return None


def _source_id(record: Mapping[str, Any]) -> str:
    direct = _first(
        record,
        "source_id",
        "source_ref",
        "video_id",
        "stable_source_id",
        "candidate_id",
    )
    if direct:
        return str(direct)
    media = record.get("media")
    if isinstance(media, Mapping) and media.get("video_id"):
        return str(media["video_id"])
    return ""


def _media_record(record: Mapping[str, Any]) -> Mapping[str, Any]:
    media = record.get("media")
    if isinstance(media, Mapping):
        return media
    payloads = record.get("payload_files") or record.get("files") or []
    if isinstance(payloads, list):
        candidates = [
            item
            for item in payloads
            if isinstance(item, Mapping)
            and str(item.get("role", "")).casefold()
            in {"primary_video", "video", "source_video", "media"}
        ]
        if len(candidates) == 1:
            return candidates[0]
    return {}


def _nonzero_count(document: Mapping[str, Any], key: str) -> int:
    value = document.get(key)
    if isinstance(value, Mapping):
        raw = value.get("count", 0)
    else:
        raw = value or 0
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 1


def _stream_types(record: Mapping[str, Any]) -> set[str]:
    streams = _nested_first(
        record,
        (
            ("decode_facts", "streams"),
            ("technical_validation", "streams"),
            ("media", "streams"),
            ("media", "stream_facts"),
        ),
    )
    if not isinstance(streams, list):
        return set()
    return {
        str(item.get("type", item.get("kind", ""))).casefold()
        for item in streams
        if isinstance(item, Mapping)
    }


def _av_sync_verified(record: Mapping[str, Any]) -> bool:
    explicit = _nested_first(
        record,
        (
            ("decode_facts", "av_sync_verified"),
            ("decode_facts", "synchronization_verified"),
            ("technical_validation", "av_sync_verified"),
            ("media", "av_sync_verified"),
        ),
    )
    if explicit is not None:
        return explicit is True
    probes = _nested_first(
        record,
        (
            ("decode_facts", "beginning_middle_end_decode"),
            ("technical_validation", "beginning_middle_end_decode"),
        ),
    )
    if not isinstance(probes, Mapping):
        return False
    required = ("beginning", "middle", "end")
    return all(
        isinstance(probes.get(name), Mapping)
        and probes[name].get("timestamps_synchronized_within_1s") is True
        for name in required
    )


def _verify_official_metadata(plan: Mapping[str, Any], root: Path) -> None:
    bindings = plan.get("official_metadata_bindings")
    if not isinstance(bindings, Mapping):
        _fail("OFFICIAL_METADATA_BINDINGS_MISSING")
    video_spec = bindings.get("video_info_csv")
    md5_spec = bindings.get("md5_csv")
    if not isinstance(video_spec, Mapping) or not isinstance(md5_spec, Mapping):
        _fail("OFFICIAL_METADATA_BINDINGS_MISSING")
    video_path = _repo_path(root, video_spec.get("path"), code="VIDEO_INFO_PATH_INVALID")
    md5_path = _repo_path(root, md5_spec.get("path"), code="MD5_PATH_INVALID")
    for path, spec, code in (
        (video_path, video_spec, "VIDEO_INFO_HASH_MISMATCH"),
        (md5_path, md5_spec, "MD5_MANIFEST_HASH_MISMATCH"),
    ):
        if not path.is_file() or path.is_symlink():
            _fail(code, path.as_posix())
        expected = spec.get("sha256")
        if not _is_hex(expected, 64) or _sha256(path) != expected:
            _fail(code, path.as_posix())

    expected_sources = {
        item["source_id"]: item
        for item in plan.get("sources", [])
        if isinstance(item, Mapping) and isinstance(item.get("source_id"), str)
    }
    with video_path.open(newline="", encoding="utf-8") as handle:
        video_rows = {
            str(row.get("video_id", "")): row for row in csv.DictReader(handle)
        }
    with md5_path.open(newline="", encoding="utf-8") as handle:
        md5_rows = list(csv.DictReader(handle))
    for source_id in EXPECTED_SOURCE_IDS:
        source = expected_sources.get(source_id)
        if source is None:
            _fail("PLAN_SOURCE_MISSING", source_id)
        row = video_rows.get(source_id)
        if row is None:
            _fail("OFFICIAL_DURATION_ROW_MISSING", source_id)
        expected_duration = float(source["official_duration_seconds"])
        if not math.isclose(
            float(row["duration"]), expected_duration, rel_tol=0.0, abs_tol=1e-9
        ):
            _fail("OFFICIAL_DURATION_MISMATCH", source_id)
        if str(row["fps"]) != str(source["official_fps"]):
            _fail("OFFICIAL_FPS_MISMATCH", source_id)
        if str(row["resolution"]) != str(source["official_resolution"]):
            _fail("OFFICIAL_RESOLUTION_MISMATCH", source_id)
        expected_remote = str(source["official_remote_path"])
        matches = [
            item
            for item in md5_rows
            if item.get("file_remote_path") == expected_remote
            and str(item.get("version")) == str(source["official_media_version"])
        ]
        if len(matches) != 1 or matches[0].get("md5") != source["official_md5"]:
            _fail("OFFICIAL_MD5_MISMATCH", source_id)


def _verify_models(plan: Mapping[str, Any], root: Path) -> None:
    from av_trace_mini_pilot_index.core import IndexConfig, build_resource_manifest

    snapshots = plan.get("model_snapshots")
    if not isinstance(snapshots, Mapping):
        _fail("MODEL_SNAPSHOTS_MISSING")
    try:
        config = IndexConfig(
            output_dir=EXPECTED_OUTPUT_ROOT,
            clip_model_path=snapshots["vision_semantic"]["snapshot_path"],
            whisper_model_path=snapshots["speech"]["snapshot_path"],
            ast_model_path=snapshots["ambient"]["snapshot_path"],
            haar_model_path=snapshots["vision_routing"]["haar_snapshot_path"],
            expected_source_count=2,
        )
        resource = build_resource_manifest(root, config, [])
    except Exception as exc:
        raise EpicWave1SourceError(f"MODEL_SNAPSHOT_INVALID:{exc}") from exc
    names = {
        "speech": "whisper",
        "ambient": "ast",
        "vision_semantic": "clip",
        "vision_routing": "opencv_haar",
    }
    for layer, name in names.items():
        spec = snapshots[layer]
        actual = resource["models"][name]
        if layer == "vision_routing":
            if actual["files"][0]["sha256"] != spec["haar_sha256"]:
                _fail("MODEL_HASH_MISMATCH", layer)
        else:
            if actual["snapshot_hash"] != spec["snapshot_hash"]:
                _fail("MODEL_HASH_MISMATCH", layer)
            if not any(
                item["sha256"] == spec["weights_sha256"]
                for item in actual["files"]
            ):
                _fail("MODEL_WEIGHT_HASH_MISMATCH", layer)


def load_plan_definition(
    repo_root: str | Path,
    *,
    plan_path: str | Path = PLAN_RELATIVE_PATH,
    verify_official_metadata: bool = True,
    verify_models: bool = True,
) -> tuple[Path, dict[str, Any], Path, Path, Path]:
    """Validate the static plan without reading media or the staging tree."""
    root = Path(repo_root).resolve()
    candidate = Path(plan_path)
    if not candidate.is_absolute():
        candidate = _repo_path(root, candidate.as_posix(), code="PLAN_PATH_INVALID")
    plan = _read_json(candidate, "PLAN_INVALID")
    if plan.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        _fail("PLAN_SCHEMA_MISMATCH")
    if plan.get("plan_id") != EXPECTED_PLAN_ID:
        _fail("PLAN_ID_MISMATCH")
    if plan.get("implementation_decision") != "READY_FOR_GATED_EXECUTION":
        _fail("PLAN_IMPLEMENTATION_DECISION_MISMATCH")
    scope = plan.get("scope")
    if not isinstance(scope, Mapping):
        _fail("PLAN_SCOPE_MISSING")
    if scope.get("source_count") != 2:
        _fail("PLAN_SOURCE_COUNT_MISMATCH")
    if scope.get("acquisition_decision_required") != REQUIRED_ACQUISITION_DECISION:
        _fail("PLAN_ACQUISITION_TOKEN_MISMATCH")
    if scope.get("allowed_restricted_source_root") != EXPECTED_SOURCE_ROOT:
        _fail("SOURCE_ROOT_MISMATCH")
    if scope.get("acquisition_manifest_path") != EXPECTED_ACQUISITION_MANIFEST:
        _fail("ACQUISITION_MANIFEST_PATH_MISMATCH")
    if scope.get("output_root") != EXPECTED_OUTPUT_ROOT:
        _fail("OUTPUT_ROOT_MISMATCH")
    source_root = _repo_path(root, EXPECTED_SOURCE_ROOT, code="SOURCE_ROOT_INVALID")
    acquisition_path = _repo_path(
        root,
        EXPECTED_ACQUISITION_MANIFEST,
        code="ACQUISITION_MANIFEST_PATH_INVALID",
        allowed_root=source_root,
    )
    output_root = _repo_path(root, EXPECTED_OUTPUT_ROOT, code="OUTPUT_ROOT_INVALID")
    if source_root == output_root or source_root in output_root.parents:
        _fail("OUTPUT_ROOT_OVERLAPS_SOURCE_ROOT")
    sources = plan.get("sources")
    if not isinstance(sources, list) or tuple(
        item.get("source_id") for item in sources if isinstance(item, Mapping)
    ) != EXPECTED_SOURCE_IDS:
        _fail("PLAN_SOURCE_IDS_MISMATCH")
    for source in sources:
        source_id = source["source_id"]
        if not _is_hex(source.get("official_md5"), 32):
            _fail("PLAN_OFFICIAL_MD5_INVALID", source_id)
        expected = computed_counts(float(source["official_duration_seconds"]))
        if source.get("expected_counts") != expected:
            _fail("PLAN_LATTICE_COUNT_MISMATCH", source_id)
        media_path = _repo_path(
            root,
            source.get("expected_final_media_path"),
            code="MEDIA_PATH_INVALID",
            allowed_root=source_root,
        )
        expected_path = (
            source_root
            / "media"
            / source["source_group_id"]
            / f"{source_id}.MP4"
        )
        if media_path != expected_path:
            _fail("MEDIA_PATH_MISMATCH", source_id)
    if tuple(plan.get("checkpointing", {}).get("layers_per_source", ())) != EXPECTED_LAYERS:
        _fail("CHECKPOINT_LAYER_MISMATCH")
    if plan.get("checkpointing", {}).get("expected_checkpoint_count") != 8:
        _fail("CHECKPOINT_COUNT_MISMATCH")
    forbidden = set(scope.get("forbidden_downstream_stages", []))
    if not {
        "candidate-family generation",
        "intervention construction",
        "trajectory generation",
    } <= forbidden:
        _fail("DOWNSTREAM_BOUNDARY_MISSING")
    if verify_official_metadata:
        _verify_official_metadata(plan, root)
    if verify_models:
        _verify_models(plan, root)
    return candidate, plan, source_root, acquisition_path, output_root


def _verify_acquired_source(
    source_plan: Mapping[str, Any],
    acquisition_source: Mapping[str, Any],
    *,
    root: Path,
    source_root: Path,
    acquisition_path: Path,
    hash_files: bool,
) -> EpicSourceSpec:
    source_id = str(source_plan["source_id"])
    status = str(acquisition_source.get("status", "")).upper()
    if status and not any(word in status for word in ("COMPLETE", "READY", "VERIFIED")):
        _fail("ACQUISITION_SOURCE_NOT_READY", source_id)
    media = _media_record(acquisition_source)
    if not media:
        _fail("ACQUISITION_SOURCE_MISSING", source_id)
    group = str(
        _first(
            acquisition_source,
            "source_group_id",
            "participant_id",
        )
        or source_plan["source_group_id"]
    )
    if group != source_plan["source_group_id"]:
        _fail("SOURCE_GROUP_MISMATCH", source_id)
    path_value = _first(media, "path", "custodian_path", "repo_path")
    if not path_value:
        _fail("MEDIA_MISSING", source_id)
    media_path = _repo_path(
        root, path_value, code="MEDIA_PATH_INVALID", allowed_root=source_root
    )
    expected_path = _repo_path(
        root,
        source_plan["expected_final_media_path"],
        code="MEDIA_PATH_INVALID",
        allowed_root=source_root,
    )
    if media_path != expected_path:
        _fail("MEDIA_PATH_MISMATCH", source_id)
    sha256 = str(_first(media, "sha256", "sha_256") or "").removeprefix("sha256:")
    if not _is_hex(sha256, 64):
        _fail("EXACT_SHA256_MISSING", source_id)
    md5 = str(_first(media, "md5", "official_md5") or "").casefold()
    if not _is_hex(md5, 32):
        _fail("OFFICIAL_MD5_MISSING", source_id)
    if md5 != source_plan["official_md5"]:
        _fail("OFFICIAL_MD5_MISMATCH", source_id)
    media_version = str(
        _first(
            media,
            "version",
            "media_version",
            "manifest_version",
        )
        or _first(
            acquisition_source,
            "version",
            "media_version",
            "manifest_version",
        )
        or ""
    )
    if media_version != str(source_plan["official_media_version"]):
        _fail("MEDIA_VERSION_MISMATCH", source_id)
    try:
        media_bytes = int(_first(media, "bytes", "size_bytes", "content_length"))
    except (TypeError, ValueError):
        _fail("MEDIA_SIZE_MISMATCH", source_id)
    if media_bytes != int(source_plan["official_content_length_bytes"]):
        _fail("MEDIA_SIZE_MISMATCH", source_id)
    duration = _first(acquisition_source, "duration_seconds", "duration_s")
    if duration is None:
        duration = _nested_first(
            acquisition_source,
            (
                ("decode_facts", "duration_seconds"),
                ("technical_validation", "duration_seconds"),
                ("media", "duration_seconds"),
            ),
        )
    if duration is None:
        _fail("DURATION_BINDING_MISSING", source_id)
    expected_duration = float(source_plan["official_duration_seconds"])
    tolerance = float(source_plan["duration_tolerance_seconds"])
    if not math.isclose(
        float(duration), expected_duration, rel_tol=0.0, abs_tol=tolerance
    ):
        _fail("DURATION_MISMATCH", source_id)
    streams = _stream_types(acquisition_source)
    if "audio" not in streams:
        _fail("AUDIO_STREAM_NOT_VERIFIED", source_id)
    if "video" not in streams:
        _fail("VIDEO_STREAM_NOT_VERIFIED", source_id)
    if not _av_sync_verified(acquisition_source):
        _fail("AV_SYNC_NOT_VERIFIED", source_id)
    if not media_path.is_file() or media_path.is_symlink():
        _fail("MEDIA_MISSING", source_id)
    _mode(media_path.parent, 0o700, "SOURCE_DIRECTORY_MODE_MISMATCH")
    _mode(media_path, 0o600, "MEDIA_MODE_MISMATCH")
    if media_path.stat().st_size != media_bytes:
        _fail("MEDIA_SIZE_MISMATCH", source_id)
    if hash_files:
        if _sha256(media_path) != sha256:
            _fail("MEDIA_SHA256_MISMATCH", source_id)
        if _md5(media_path) != md5:
            _fail("MEDIA_MD5_MISMATCH", source_id)
    return EpicSourceSpec(
        source_id=source_id,
        source_group_id=group,
        source_manifest_path=acquisition_path,
        source_directory=media_path.parent,
        media_path=media_path,
        media_bytes=media_bytes,
        media_sha256=sha256,
        official_md5=md5,
        duration_seconds=expected_duration,
        duration_tolerance_seconds=tolerance,
        expected_counts=dict(source_plan["expected_counts"]),
    )


def load_source_plan(
    repo_root: str | Path,
    *,
    plan_path: str | Path = PLAN_RELATIVE_PATH,
    hash_files: bool = True,
    verify_models: bool = True,
) -> EpicWave1Plan:
    """Load the plan and require Task162's final acquisition decision and hashes."""
    root = Path(repo_root).resolve()
    (
        candidate,
        plan,
        source_root,
        acquisition_path,
        output_root,
    ) = load_plan_definition(
        root, plan_path=plan_path, verify_models=verify_models
    )
    if not acquisition_path.is_file() or acquisition_path.is_symlink():
        _fail("ACQUISITION_MANIFEST_MISSING", acquisition_path.as_posix())
    acquisition = _read_json(acquisition_path, "ACQUISITION_MANIFEST_INVALID")
    if acquisition.get("decision") != REQUIRED_ACQUISITION_DECISION:
        _fail(
            "ACQUISITION_DECISION_MISMATCH",
            str(acquisition.get("decision")),
        )
    if _nonzero_count(acquisition, "failed_transfer_accounting"):
        _fail("ACQUISITION_FAILURES_PRESENT")
    if _nonzero_count(acquisition, "incomplete_transfer_accounting"):
        _fail("ACQUISITION_INCOMPLETE_PRESENT")
    records = acquisition.get("sources")
    if not isinstance(records, list) or len(records) != 2:
        _fail("ACQUISITION_SOURCE_COUNT_MISMATCH")
    by_id = {
        _source_id(item): item for item in records if isinstance(item, Mapping)
    }
    sources: list[EpicSourceSpec] = []
    for source in plan["sources"]:
        record = by_id.get(source["source_id"])
        if record is None:
            _fail("ACQUISITION_SOURCE_MISSING", source["source_id"])
        sources.append(
            _verify_acquired_source(
                source,
                record,
                root=root,
                source_root=source_root,
                acquisition_path=acquisition_path,
                hash_files=hash_files,
            )
        )
    totals = plan["totals"]
    aggregate = {
        "duration_seconds": sum(item.duration_seconds for item in sources),
        "primary_media_bytes": sum(item.media_bytes for item in sources),
        "base_cells": sum(item.expected_counts["base_cells"] for item in sources),
        "fine_windows": sum(item.expected_counts["fine_windows"] for item in sources),
        "context_windows": sum(
            item.expected_counts["context_windows"] for item in sources
        ),
        "temporal_segments": sum(
            item.expected_counts["temporal_segments"] for item in sources
        ),
        "whisper_chunks": sum(
            item.expected_counts["whisper_chunks"] for item in sources
        ),
        "checkpoint_count": sum(
            item.expected_counts["checkpoints"] for item in sources
        ),
    }
    for key, observed in aggregate.items():
        expected = totals.get(key)
        if isinstance(observed, float):
            if not math.isclose(
                observed, float(expected), rel_tol=0.0, abs_tol=1e-9
            ):
                _fail("TOTAL_MISMATCH", key)
        elif observed != expected:
            _fail("TOTAL_MISMATCH", key)
    if output_root.exists() and output_root.is_symlink():
        _fail("OUTPUT_ROOT_IS_SYMLINK")
    return EpicWave1Plan(
        repo_root=root,
        plan_path=candidate,
        output_root=output_root,
        allowed_restricted_source_root=source_root,
        acquisition_manifest_path=acquisition_path,
        acquisition_manifest_sha256=_sha256(acquisition_path),
        sources=tuple(sources),
        totals=totals,
        model_snapshots=plan["model_snapshots"],
        index_policy=plan["index_policy"],
        raw=plan,
    )


__all__ = [
    "EXPECTED_ACQUISITION_MANIFEST",
    "EXPECTED_OUTPUT_ROOT",
    "EXPECTED_SOURCE_IDS",
    "PENDING_ACQUISITION_CODES",
    "PLAN_RELATIVE_PATH",
    "REQUIRED_ACQUISITION_DECISION",
    "EpicSourceSpec",
    "EpicWave1Plan",
    "EpicWave1SourceError",
    "computed_counts",
    "load_plan_definition",
    "load_source_plan",
]
