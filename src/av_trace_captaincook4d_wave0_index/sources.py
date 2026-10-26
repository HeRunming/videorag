"""Fail-closed Task188 source loader for CaptainCook4D Wave-0 indexing."""

from __future__ import annotations

import hashlib
import json
import math
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

PLAN_RELATIVE_PATH = Path(
    "data/rehearsal_plan/captaincook4d_wave0_full_timeline_index_v1.json"
)
EXPECTED_SCHEMA_VERSION = (
    "av-trace.captaincook4d-wave0-full-timeline-index-plan/1.0"
)
EXPECTED_PLAN_ID = "AV-TRACE-CAPTAINCOOK4D-WAVE0-FULL-TIMELINE-INDEX-V1"
EXPECTED_SOURCE_IDS = ("16_20", "15_29", "26_22")
EXPECTED_SOURCE_ROOT = "data/restricted/captaincook4d_wave0_sources_v3"
EXPECTED_ACQUISITION_MANIFEST = (
    "data/restricted/captaincook4d_wave0_sources_v3/manifests/"
    "captaincook4d_wave0_acquisition_manifest.json"
)
EXPECTED_OUTPUT_ROOT = "data/restricted/captaincook4d_wave0_index_v1"
REQUIRED_ACQUISITION_DECISION = "CAPTAINCOOK4D_WAVE0_ACQUISITION_READY"
EXPECTED_LAYERS = ("speech", "ambient", "vision_routing", "vision_clip")


class CaptainCook4DWave0SourceError(ValueError):
    """Raised when the frozen plan or a Task188 source fails closed."""

    @property
    def code(self) -> str:
        return str(self).split(":", 1)[0]


@dataclass(frozen=True)
class CaptainCook4DSourceSpec:
    """Verified final-media identity and deterministic lattice counts."""

    source_id: str
    source_group_id: str
    person_id: int
    environment_id: int
    source_manifest_path: Path
    source_directory: Path
    media_path: Path
    media_bytes: int
    media_sha256: str
    media_md5: str
    duration_seconds: float
    duration_tolerance_seconds: float
    expected_counts: Mapping[str, int]


@dataclass(frozen=True)
class CaptainCook4DWave0Plan:
    """Verified CaptainCook4D Wave-0 indexing plan and Task188 gate."""

    repo_root: Path
    plan_path: Path
    output_root: Path
    allowed_restricted_source_root: Path
    acquisition_manifest_path: Path
    acquisition_manifest_sha256: str
    sources: tuple[CaptainCook4DSourceSpec, ...]
    totals: Mapping[str, int | float]
    model_snapshots: Mapping[str, Any]
    index_policy: Mapping[str, Any]
    raw: Mapping[str, Any]


def _fail(code: str, detail: str = "") -> None:
    raise CaptainCook4DWave0SourceError(
        f"{code}:{detail}" if detail else code
    )


def _read_json(path: Path, code: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        _fail(code, path.as_posix())
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CaptainCook4DWave0SourceError(
            f"{code}:{path.as_posix()}"
        ) from exc
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


def _verify_bound_file(
    root: Path,
    binding: Mapping[str, Any],
    *,
    code: str,
    allowed_root: Path | None = None,
) -> Path:
    path = _repo_path(
        root,
        binding.get("path"),
        code=f"{code}_PATH_INVALID",
        allowed_root=allowed_root,
    )
    expected = binding.get("sha256")
    if not _is_hex(expected, 64) or _sha256(path) != expected:
        _fail(f"{code}_HASH_MISMATCH", path.as_posix())
    return path


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
            expected_source_count=3,
        )
        resource = build_resource_manifest(root, config, [])
    except Exception as exc:
        raise CaptainCook4DWave0SourceError(
            f"MODEL_SNAPSHOT_INVALID:{exc}"
        ) from exc
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
    verify_bound_inputs: bool = True,
    verify_models: bool = True,
) -> tuple[Path, dict[str, Any], Path, Path, Path]:
    """Validate the static plan without decoding media or writing outputs."""
    root = Path(repo_root).resolve()
    candidate = Path(plan_path)
    if not candidate.is_absolute():
        candidate = _repo_path(
            root, candidate.as_posix(), code="PLAN_PATH_INVALID"
        )
    plan = _read_json(candidate, "PLAN_INVALID")
    if plan.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        _fail("PLAN_SCHEMA_MISMATCH")
    if plan.get("plan_id") != EXPECTED_PLAN_ID:
        _fail("PLAN_ID_MISMATCH")
    if plan.get("execution_authorization") != "TASK189_FULL_EXECUTION_AUTHORIZED":
        _fail("PLAN_EXECUTION_AUTHORIZATION_MISMATCH")
    scope = plan.get("scope")
    if not isinstance(scope, Mapping):
        _fail("PLAN_SCOPE_MISSING")
    if scope.get("source_count") != 3:
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
        if not _is_hex(source.get("media_sha256"), 64):
            _fail("PLAN_SHA256_INVALID", source_id)
        if not _is_hex(source.get("media_md5"), 32):
            _fail("PLAN_MD5_INVALID", source_id)
        expected = computed_counts(float(source["official_duration_seconds"]))
        if source.get("expected_counts") != expected:
            _fail("PLAN_LATTICE_COUNT_MISMATCH", source_id)
        media_path = _repo_path(
            root,
            source.get("media_path"),
            code="MEDIA_PATH_INVALID",
            allowed_root=source_root,
        )
        if media_path != source_root / f"{source_id}_360p.mp4":
            _fail("MEDIA_PATH_MISMATCH", source_id)
        manifest_path = _repo_path(
            root,
            source.get("source_manifest_path"),
            code="SOURCE_MANIFEST_PATH_INVALID",
            allowed_root=source_root,
        )
        if manifest_path != source_root / "manifests" / f"{source_id}.source_manifest.json":
            _fail("SOURCE_MANIFEST_PATH_MISMATCH", source_id)
    checkpointing = plan.get("checkpointing", {})
    if tuple(checkpointing.get("layers_per_source", ())) != EXPECTED_LAYERS:
        _fail("CHECKPOINT_LAYER_MISMATCH")
    if checkpointing.get("expected_checkpoint_count") != 12:
        _fail("CHECKPOINT_COUNT_MISMATCH")
    forbidden = set(scope.get("forbidden_downstream_stages", []))
    required_forbidden = {
        "semantic annotations",
        "candidate families",
        "interventions",
        "trajectories",
        "evaluation",
        "media derivatives",
    }
    if not required_forbidden <= forbidden:
        _fail("DOWNSTREAM_BOUNDARY_MISSING")
    if verify_bound_inputs:
        bindings = plan.get("authoritative_input_bindings")
        if not isinstance(bindings, Mapping):
            _fail("AUTHORITATIVE_INPUT_BINDINGS_MISSING")
        for name, binding in bindings.items():
            if not isinstance(binding, Mapping):
                _fail("AUTHORITATIVE_INPUT_BINDING_INVALID", str(name))
            _verify_bound_file(
                root,
                binding,
                code=f"BOUND_INPUT_{str(name).upper()}",
                allowed_root=source_root if binding.get("restricted") else None,
            )
    if verify_models:
        _verify_models(plan, root)
    return candidate, plan, source_root, acquisition_path, output_root


def _verify_source_manifest(
    root: Path,
    source_root: Path,
    source_plan: Mapping[str, Any],
    manifest_binding: Mapping[str, Any],
) -> dict[str, Any]:
    source_id = str(source_plan["source_id"])
    expected_path = _repo_path(
        root,
        source_plan["source_manifest_path"],
        code="SOURCE_MANIFEST_PATH_INVALID",
        allowed_root=source_root,
    )
    bound_path = _repo_path(
        root,
        manifest_binding.get("path"),
        code="SOURCE_MANIFEST_PATH_INVALID",
        allowed_root=source_root,
    )
    if expected_path != bound_path or manifest_binding.get("recording_id") != source_id:
        _fail("SOURCE_MANIFEST_BINDING_MISMATCH", source_id)
    expected_hash = source_plan["source_manifest_sha256"]
    if (
        manifest_binding.get("sha256") != expected_hash
        or _sha256(expected_path) != expected_hash
    ):
        _fail("SOURCE_MANIFEST_HASH_MISMATCH", source_id)
    manifest = _read_json(expected_path, "SOURCE_MANIFEST_INVALID")
    exact = {
        "source_id": source_id,
        "source_group_id": source_plan["source_group_id"],
        "person_id": source_plan["person_id"],
        "environment_id": source_plan["environment_id"],
        "stream": "gopro_360p",
        "task_id": 188,
        "dataset": "CaptainCook4D",
    }
    for key, value in exact.items():
        if manifest.get(key) != value:
            _fail("SOURCE_MANIFEST_FIELD_MISMATCH", f"{source_id}:{key}")
    if (
        manifest.get("annotations_accessed_or_produced") is not False
        or manifest.get("human_semantic_review_performed") is not False
        or manifest.get("h_tiers_assigned") is not False
    ):
        _fail("SOURCE_MANIFEST_SEMANTIC_BOUNDARY_MISMATCH", source_id)
    if manifest.get("public_release_or_redistribution") != "NOT_AUTHORIZED":
        _fail("SOURCE_MANIFEST_RIGHTS_BOUNDARY_MISMATCH", source_id)
    media = manifest.get("media")
    if not isinstance(media, Mapping):
        _fail("SOURCE_MANIFEST_MEDIA_MISSING", source_id)
    expected_media = {
        "path": source_plan["media_path"],
        "bytes": source_plan["media_bytes"],
        "sha256": source_plan["media_sha256"],
        "md5": source_plan["media_md5"],
        "mode": "0o600",
    }
    if any(media.get(key) != value for key, value in expected_media.items()):
        _fail("SOURCE_MANIFEST_MEDIA_MISMATCH", source_id)
    if not math.isclose(
        float(manifest.get("official_metadata_duration_seconds", -1)),
        float(source_plan["official_duration_seconds"]),
        rel_tol=0.0,
        abs_tol=1e-9,
    ):
        _fail("SOURCE_MANIFEST_DURATION_MISMATCH", source_id)
    technical = manifest.get("technical_validation")
    if not isinstance(technical, Mapping) or technical.get("technical_audit_passed") is not True:
        _fail("TECHNICAL_AUDIT_NOT_PASSED", source_id)
    checks = technical.get("checks")
    if not isinstance(checks, Mapping) or not checks or not all(
        value is True for value in checks.values()
    ):
        _fail("TECHNICAL_CHECK_FAILED", source_id)
    streams = technical.get("streams")
    stream_types = {
        str(item.get("type", "")).casefold()
        for item in streams
        if isinstance(streams, list) and isinstance(item, Mapping)
    }
    if not {"audio", "video"} <= stream_types:
        _fail("STREAM_EVIDENCE_MISSING", source_id)
    probes = technical.get("beginning_middle_end_decode_and_sync")
    if not isinstance(probes, Mapping) or not all(
        isinstance(probes.get(position), Mapping)
        and probes[position].get("audio_decoded") is True
        and probes[position].get("video_decoded") is True
        and probes[position].get("timestamps_synchronized_within_0_25s") is True
        for position in ("beginning", "middle", "end")
    ):
        _fail("AV_SYNC_NOT_VERIFIED", source_id)
    full_pyav = technical.get("full_pyav_decode", {})
    full_opencv = technical.get("opencv_full_decode", {})
    if (
        full_pyav.get("all_streams_no_truncation_verified") is not True
        or full_pyav.get("eof_reached") is not True
        or full_opencv.get("no_truncation_verified") is not True
        or full_opencv.get("eof_confirmed") is not True
    ):
        _fail("EOF_NOT_VERIFIED", source_id)
    return manifest


def _verify_acquired_source(
    source_plan: Mapping[str, Any],
    acquisition_source: Mapping[str, Any],
    source_manifest_binding: Mapping[str, Any],
    *,
    root: Path,
    source_root: Path,
    hash_files: bool,
) -> CaptainCook4DSourceSpec:
    source_id = str(source_plan["source_id"])
    exact = {
        "source_id": source_id,
        "source_group_id": source_plan["source_group_id"],
        "person_id": source_plan["person_id"],
        "environment_id": source_plan["environment_id"],
        "official_duration_seconds": source_plan["official_duration_seconds"],
        "declared_total_bytes_from_content_range": source_plan["media_bytes"],
        "technical_audit_passed": True,
    }
    for key, value in exact.items():
        if acquisition_source.get(key) != value:
            _fail("ACQUISITION_SOURCE_FIELD_MISMATCH", f"{source_id}:{key}")
    media = acquisition_source.get("media")
    if not isinstance(media, Mapping):
        _fail("ACQUISITION_MEDIA_MISSING", source_id)
    expected_media = {
        "path": source_plan["media_path"],
        "bytes": source_plan["media_bytes"],
        "sha256": source_plan["media_sha256"],
        "md5": source_plan["media_md5"],
        "recording_id": source_id,
    }
    if any(media.get(key) != value for key, value in expected_media.items()):
        _fail("ACQUISITION_MEDIA_MISMATCH", source_id)
    _verify_source_manifest(
        root, source_root, source_plan, source_manifest_binding
    )
    media_path = _repo_path(
        root,
        source_plan["media_path"],
        code="MEDIA_PATH_INVALID",
        allowed_root=source_root,
    )
    if not media_path.is_file() or media_path.is_symlink():
        _fail("MEDIA_MISSING", source_id)
    _mode(source_root, 0o700, "SOURCE_DIRECTORY_MODE_MISMATCH")
    _mode(media_path, 0o600, "MEDIA_MODE_MISMATCH")
    if media_path.stat().st_size != int(source_plan["media_bytes"]):
        _fail("MEDIA_SIZE_MISMATCH", source_id)
    if hash_files:
        if _sha256(media_path) != source_plan["media_sha256"]:
            _fail("MEDIA_SHA256_MISMATCH", source_id)
        if _md5(media_path) != source_plan["media_md5"]:
            _fail("MEDIA_MD5_MISMATCH", source_id)
    manifest_path = _repo_path(
        root,
        source_plan["source_manifest_path"],
        code="SOURCE_MANIFEST_PATH_INVALID",
        allowed_root=source_root,
    )
    return CaptainCook4DSourceSpec(
        source_id=source_id,
        source_group_id=str(source_plan["source_group_id"]),
        person_id=int(source_plan["person_id"]),
        environment_id=int(source_plan["environment_id"]),
        source_manifest_path=manifest_path,
        source_directory=source_root,
        media_path=media_path,
        media_bytes=int(source_plan["media_bytes"]),
        media_sha256=str(source_plan["media_sha256"]),
        media_md5=str(source_plan["media_md5"]),
        duration_seconds=float(source_plan["official_duration_seconds"]),
        duration_tolerance_seconds=float(
            source_plan["duration_tolerance_seconds"]
        ),
        expected_counts=dict(source_plan["expected_counts"]),
    )


def load_source_plan(
    repo_root: str | Path,
    *,
    plan_path: str | Path = PLAN_RELATIVE_PATH,
    hash_files: bool = True,
    verify_models: bool = True,
) -> CaptainCook4DWave0Plan:
    """Load the plan and require the exact Task188 READY acquisition state."""
    root = Path(repo_root).resolve()
    candidate, plan, source_root, acquisition_path, output_root = (
        load_plan_definition(
            root, plan_path=plan_path, verify_models=verify_models
        )
    )
    acquisition = _read_json(
        acquisition_path, "ACQUISITION_MANIFEST_INVALID"
    )
    expected_acquisition_hash = plan["scope"]["acquisition_manifest_sha256"]
    observed_acquisition_hash = _sha256(acquisition_path)
    if observed_acquisition_hash != expected_acquisition_hash:
        _fail("ACQUISITION_MANIFEST_HASH_MISMATCH")
    if acquisition.get("decision") != REQUIRED_ACQUISITION_DECISION:
        _fail(
            "ACQUISITION_DECISION_MISMATCH",
            str(acquisition.get("decision")),
        )
    if acquisition.get("source_count") != 3:
        _fail("ACQUISITION_SOURCE_COUNT_MISMATCH")
    if tuple(acquisition.get("selected_recording_ids", ())) != EXPECTED_SOURCE_IDS:
        _fail("ACQUISITION_SOURCE_IDS_MISMATCH")
    if acquisition.get("replacement_events") != []:
        _fail("ACQUISITION_REPLACEMENT_EVENTS_PRESENT")
    checks = acquisition.get("readiness_checks")
    if not isinstance(checks, Mapping) or not checks or not all(
        value is True for value in checks.values()
    ):
        _fail("ACQUISITION_READINESS_CHECK_FAILED")
    if acquisition.get("explicit_non_claims") != plan["scope"]["required_non_claims"]:
        _fail("ACQUISITION_NON_CLAIMS_MISMATCH")
    records = acquisition.get("sources")
    manifest_bindings = acquisition.get("source_manifests")
    if (
        not isinstance(records, list)
        or len(records) != 3
        or not isinstance(manifest_bindings, list)
        or len(manifest_bindings) != 3
    ):
        _fail("ACQUISITION_SOURCE_COUNT_MISMATCH")
    by_id = {
        str(item.get("source_id")): item
        for item in records
        if isinstance(item, Mapping)
    }
    manifest_by_id = {
        str(item.get("recording_id")): item
        for item in manifest_bindings
        if isinstance(item, Mapping)
    }
    sources: list[CaptainCook4DSourceSpec] = []
    for source in plan["sources"]:
        source_id = source["source_id"]
        if source_id not in by_id or source_id not in manifest_by_id:
            _fail("ACQUISITION_SOURCE_MISSING", source_id)
        sources.append(
            _verify_acquired_source(
                source,
                by_id[source_id],
                manifest_by_id[source_id],
                root=root,
                source_root=source_root,
                hash_files=hash_files,
            )
        )
    if len({item.person_id for item in sources}) != 3:
        _fail("PERSON_DISTINCTNESS_MISMATCH")
    if len({item.environment_id for item in sources}) != 3:
        _fail("ENVIRONMENT_DISTINCTNESS_MISMATCH")
    totals = plan["totals"]
    aggregate: dict[str, int | float] = {
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
    if acquisition.get("aggregate_media_bytes") != totals["primary_media_bytes"]:
        _fail("ACQUISITION_AGGREGATE_BYTES_MISMATCH")
    if not math.isclose(
        float(acquisition.get("aggregate_official_duration_seconds", -1)),
        float(totals["duration_seconds"]),
        rel_tol=0.0,
        abs_tol=1e-9,
    ):
        _fail("ACQUISITION_AGGREGATE_DURATION_MISMATCH")
    if output_root.exists() and output_root.is_symlink():
        _fail("OUTPUT_ROOT_IS_SYMLINK")
    return CaptainCook4DWave0Plan(
        repo_root=root,
        plan_path=candidate,
        output_root=output_root,
        allowed_restricted_source_root=source_root,
        acquisition_manifest_path=acquisition_path,
        acquisition_manifest_sha256=observed_acquisition_hash,
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
    "PLAN_RELATIVE_PATH",
    "REQUIRED_ACQUISITION_DECISION",
    "CaptainCook4DSourceSpec",
    "CaptainCook4DWave0Plan",
    "CaptainCook4DWave0SourceError",
    "computed_counts",
    "load_plan_definition",
    "load_source_plan",
]
