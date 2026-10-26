"""Isolated EPIC Wave-1 full-timeline indexing built on the frozen index engine."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from av_trace_mini_pilot_index import core as engine

from .sources import EpicWave1Plan, load_source_plan

SCHEMA_VERSION = "av-trace.epic-wave1-index/1.0"
INDEX_VERSION = "epic-wave1-full-timeline-index/1.0"
STAGE = "RESTRICTED_EPIC_WAVE1_SOURCE_DERIVED_INDEX"
DEFAULT_OUTPUT_DIR = Path("data/restricted/epic_wave1_index_v1")
TOP_LEVEL_ARTIFACTS = engine.TOP_LEVEL_ARTIFACTS
FORBIDDEN_SEARCH_KEYS = engine.FORBIDDEN_SEARCH_KEYS
PROHIBITED_ARTIFACT_TERMS = engine.PROHIBITED_ARTIFACT_TERMS

IndexConfig = engine.IndexConfig
LocalFrozenModels = engine.LocalFrozenModels
MediaBackend = engine.MediaBackend
ModelBackend = engine.ModelBackend
PyAVMediaBackend = engine.PyAVMediaBackend
search_speech = engine.search_speech
search_ambient = engine.search_ambient
search_visual = engine.search_visual
search_fused = engine.search_fused


class EpicWave1IndexError(RuntimeError):
    """Fail-closed EPIC Wave-1 indexing error."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _json_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _sha256(path: Path, *, prefixed: bool = False) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    value = digest.hexdigest()
    return f"sha256:{value}" if prefixed else value


def _atomic_dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _sources(plan: EpicWave1Plan) -> list[dict[str, Any]]:
    return [
        {
            "source_ref": source.source_id,
            "media_path": _relative(plan.repo_root, source.media_path),
            "source_manifest_path": _relative(
                plan.repo_root, source.source_manifest_path
            ),
            "duration_s": source.duration_seconds,
            "size_bytes": source.media_bytes,
            "sha256": source.media_sha256,
            "restricted_processing_status": "AUTHORIZED_BY_TASK162",
            "expected_counts": dict(source.expected_counts),
        }
        for source in plan.sources
    ]


def config_from_plan(
    plan: EpicWave1Plan,
    *,
    output_root: str | Path | None = None,
    threads: int = 8,
) -> IndexConfig:
    snapshots = plan.model_snapshots
    output = output_root if output_root is not None else plan.output_root
    return IndexConfig(
        source_manifest_paths=(plan.acquisition_manifest_path,),
        output_dir=output,
        clip_model_path=snapshots["vision_semantic"]["snapshot_path"],
        whisper_model_path=snapshots["speech"]["snapshot_path"],
        ast_model_path=snapshots["ambient"]["snapshot_path"],
        haar_model_path=snapshots["vision_routing"]["haar_snapshot_path"],
        expected_source_count=2,
        threads=threads,
        derived_artifacts_hard_fail_cap_mib=plan.raw["storage_caps"][
            "derived_artifacts_hard_fail_cap_mib"
        ],
    )


def _epic_document(document: dict[str, Any], *, kind: str) -> dict[str, Any]:
    output = dict(document)
    output["schema_version"] = SCHEMA_VERSION
    output["stage"] = STAGE
    if kind == "index":
        output["index_version"] = INDEX_VERSION
    hash_key = {
        "segment": "segment_manifest_hash",
        "resource": "resource_manifest_hash",
        "observation": "observation_manifest_hash",
        "index": "index_hash",
    }[kind]
    output.pop(hash_key, None)
    output[hash_key] = _json_hash(output)
    return output


def _artifact_record(root: Path, path: Path) -> dict[str, Any]:
    return {
        "path": _relative(root, path),
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path, prefixed=True),
    }


def _assert_output_boundary(root: Path, output: Path) -> None:
    media_suffixes = {
        ".aac",
        ".avi",
        ".flac",
        ".gif",
        ".jpeg",
        ".jpg",
        ".m4a",
        ".m4v",
        ".mkv",
        ".mov",
        ".mp3",
        ".mp4",
        ".ogg",
        ".png",
        ".wav",
        ".webm",
    }
    if output.exists() and output.is_symlink():
        raise EpicWave1IndexError("OUTPUT_ROOT_IS_SYMLINK")
    for path in output.rglob("*") if output.exists() else ():
        if not path.is_file():
            continue
        relative = _relative(root, path)
        if path.suffix.casefold() in media_suffixes:
            raise EpicWave1IndexError(f"PERSISTED_MEDIA_DERIVATIVE:{relative}")
        if any(term in path.name.casefold() for term in PROHIBITED_ARTIFACT_TERMS):
            raise EpicWave1IndexError(f"DOWNSTREAM_ARTIFACT_PRESENT:{relative}")


def build_epic_wave1_index(
    repo_root: str | Path,
    *,
    plan: EpicWave1Plan | None = None,
    plan_path: str | Path | None = None,
    output_root: str | Path | None = None,
    resume: bool = True,
    model_backend: ModelBackend | None = None,
    media_backend: MediaBackend | None = None,
    routing_extractor: Any | None = None,
    threads: int = 8,
    device: str = "cpu",
    smoke_seconds: float | None = None,
) -> dict[str, Any]:
    """Build only EPIC segment, observation, index, resource, and build manifests."""
    root = Path(repo_root).resolve()
    if device != "cpu":
        raise EpicWave1IndexError("DEVICE_NOT_SUPPORTED:cpu")
    if smoke_seconds is not None and smoke_seconds <= 0:
        raise EpicWave1IndexError("SMOKE_SECONDS_MUST_BE_POSITIVE")
    if plan is None:
        kwargs = {} if plan_path is None else {"plan_path": plan_path}
        plan = load_source_plan(root, **kwargs)
    output = Path(output_root) if output_root is not None else plan.output_root
    output = output if output.is_absolute() else root / output
    try:
        output.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        raise EpicWave1IndexError("OUTPUT_ROOT_OUTSIDE_REPOSITORY") from exc
    if plan.allowed_restricted_source_root == output or (
        plan.allowed_restricted_source_root in output.parents
    ):
        raise EpicWave1IndexError("OUTPUT_ROOT_OVERLAPS_SOURCE_ROOT")
    output.mkdir(parents=True, exist_ok=True)
    output.chmod(0o700)
    _assert_output_boundary(root, output)
    config = config_from_plan(plan, output_root=output, threads=threads)
    sources = _sources(plan)
    if smoke_seconds is not None:
        sources = [
            {
                **source,
                "duration_s": min(float(source["duration_s"]), smoke_seconds),
                "expected_counts": {},
            }
            for source in sources
        ]

    segment = _epic_document(
        engine.build_segment_manifest(root, sources), kind="segment"
    )
    segment_path = output / "segment_manifest.json"
    _atomic_dump(segment_path, segment)

    resource = _epic_document(
        engine.build_resource_manifest(root, config, sources), kind="resource"
    )
    resource["acquisition_gate"] = {
        "required_decision": "EPIC_WAVE1_ACQUISITION_READY",
        "manifest_path": _relative(root, plan.acquisition_manifest_path),
        "manifest_sha256": plan.acquisition_manifest_sha256,
        "exact_source_sha256_required": True,
        "passed": True,
    }
    resource.pop("resource_manifest_hash", None)
    resource["resource_manifest_hash"] = _json_hash(resource)
    resource_path = output / "resource_manifest.json"
    _atomic_dump(resource_path, resource)

    observation = engine.build_observation_manifest(
        root,
        config,
        sources,
        segment,
        resume=resume,
        model_backend=model_backend,
        media_backend=media_backend,
        routing_extractor=routing_extractor,
        resource_manifest=resource,
    )
    observation = _epic_document(observation, kind="observation")
    observation_path = output / "observation_manifest.json"
    _atomic_dump(observation_path, observation)

    index = _epic_document(
        engine.build_full_timeline_index(root, segment, observation), kind="index"
    )
    index_path = output / "full_timeline_index.json"
    _atomic_dump(index_path, index)

    artifact_paths = [segment_path, observation_path, index_path, resource_path]
    hard_cap = int(plan.raw["storage_caps"]["derived_artifacts_hard_fail_cap_mib"])
    build_path = output / "build_manifest.json"
    derived_bytes = sum(
        path.stat().st_size
        for path in output.rglob("*")
        if path.is_file() and path != build_path
    )
    if derived_bytes > hard_cap * 1024 * 1024:
        raise EpicWave1IndexError("DERIVED_ARTIFACT_HARD_CAP_EXCEEDED")
    build = {
        "schema_version": SCHEMA_VERSION,
        "index_version": INDEX_VERSION,
        "stage": STAGE,
        "status": "COMPLETE",
        "mode": "smoke" if smoke_seconds is not None else "full",
        "smoke_seconds": smoke_seconds,
        "source_count": len(sources),
        "expected_source_count": 2,
        "output_dir": _relative(root, output),
        "plan_path": _relative(root, plan.plan_path),
        "plan_sha256": _sha256(plan.plan_path),
        "acquisition_manifest_path": _relative(
            root, plan.acquisition_manifest_path
        ),
        "acquisition_manifest_sha256": plan.acquisition_manifest_sha256,
        "acquisition_decision": "EPIC_WAVE1_ACQUISITION_READY",
        "source_sha256": {
            source.source_id: source.media_sha256 for source in plan.sources
        },
        "completed_stages": [
            "segment_manifest",
            "observation_manifest",
            "full_timeline_index",
            "resource_manifest",
        ],
        "terminal_boundary": {
            "last_allowed_stage": "resource_manifest",
            "families_generated": False,
            "interventions_generated": False,
            "trajectories_generated": False,
            "evaluation_generated": False,
        },
        "artifacts": [_artifact_record(root, path) for path in artifact_paths],
        "checkpoint_count": len(observation["checkpoints"]),
        "resume_enabled": resume,
        "no_persisted_media_derivatives": True,
        "derived_artifact_bytes_before_build_manifest": derived_bytes,
        "derived_artifact_hard_cap_mib": hard_cap,
    }
    build["build_manifest_hash"] = _json_hash(build)
    _atomic_dump(build_path, build)
    _assert_output_boundary(root, output)
    for path in output.rglob("*"):
        if path.is_dir():
            path.chmod(0o700)
        elif path.is_file():
            path.chmod(0o600)
    return {
        "segment_manifest": segment,
        "observation_manifest": observation,
        "full_timeline_index": index,
        "resource_manifest": resource,
        "build_manifest": build,
    }


build_full_timeline_index = build_epic_wave1_index


__all__ = [
    "DEFAULT_OUTPUT_DIR",
    "FORBIDDEN_SEARCH_KEYS",
    "INDEX_VERSION",
    "SCHEMA_VERSION",
    "STAGE",
    "TOP_LEVEL_ARTIFACTS",
    "EpicWave1IndexError",
    "IndexConfig",
    "LocalFrozenModels",
    "MediaBackend",
    "ModelBackend",
    "PyAVMediaBackend",
    "build_epic_wave1_index",
    "build_full_timeline_index",
    "config_from_plan",
    "search_ambient",
    "search_fused",
    "search_speech",
    "search_visual",
]
