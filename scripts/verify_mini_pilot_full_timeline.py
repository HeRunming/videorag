#!/usr/bin/env python3
"""Verify the restricted four-source mini-pilot full-timeline index."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import stat
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from av_trace_mini_pilot_index.core import FORBIDDEN_SEARCH_KEYS
from av_trace_mini_pilot_index.sources import PLAN_RELATIVE_PATH, load_source_plan

TOP_LEVEL_ARTIFACTS = (
    "segment_manifest.json",
    "observation_manifest.json",
    "full_timeline_index.json",
    "resource_manifest.json",
    "build_manifest.json",
)
CHECKPOINT_LAYERS = {
    "speech.json": ("whisper-tiny-en-frozen/1.0", "30-second", "whisper_chunks"),
    "ambient.json": ("ast-audioset-frozen/1.0", "fine", "fine_windows"),
    "vision_routing.json": ("opencv-routing/1.0", "base", "base_cells"),
    "vision_clip.json": ("clip-visual/1.0", "base", "base_cells"),
}
MODEL_PLAN_NAMES = {
    "clip": "vision_semantic",
    "whisper": "speech",
    "ast": "ambient",
    "opencv_haar": "vision_routing",
}
MEDIA_SUFFIXES = {
    ".aac", ".avi", ".flac", ".gif", ".jpeg", ".jpg", ".m4a", ".m4v",
    ".mkv", ".mov", ".mp3", ".mp4", ".ogg", ".png", ".wav", ".webm",
}
DOWNSTREAM_TERMS = (
    "famil", "negative", "intervention", "trajectory", "evaluation", "metric",
    "controller", "agent_run",
)
PATH_KEYS = {
    "path", "media_path", "source_manifest_path", "output_dir", "output_root",
    "snapshot_path", "weights_path", "haar_snapshot_path",
}


def _load(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _json_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _sha256(path: Path, *, prefixed: bool = True) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    value = digest.hexdigest()
    return f"sha256:{value}" if prefixed else value


def _self_hash(document: Mapping[str, Any], key: str) -> bool:
    copy = dict(document)
    stored = copy.pop(key, None)
    return stored == _json_hash(copy)


def _repo_path(root: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"INVALID_REPO_RELATIVE_PATH:{value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts or pure.as_posix() != value:
        raise ValueError(f"INVALID_REPO_RELATIVE_PATH:{value}")
    candidate = root.joinpath(*pure.parts)
    candidate.resolve(strict=False).relative_to(root)
    return candidate


def _walk(value: Any, location: str = "root"):
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_location = f"{location}.{key}"
            yield key, child, child_location
            yield from _walk(child, child_location)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, f"{location}[{index}]")


def _check_repo_relative_paths(document: Mapping[str, Any], root: Path) -> list[str]:
    failures: list[str] = []
    for key, value, location in _walk(document):
        if not isinstance(value, str):
            continue
        if key in PATH_KEYS or key.endswith("_path"):
            try:
                _repo_path(root, value)
            except (TypeError, ValueError):
                failures.append(f"repo_relative_path:{location}:{value}")
        elif value.startswith(("/", "file://")) or "/jizhicfs/" in value:
            failures.append(f"absolute_path_leak:{location}")
    return failures


def _check_mode(path: Path, expected: int) -> bool:
    return not path.is_symlink() and stat.S_IMODE(path.stat().st_mode) == expected


def _expected_segment_totals(plan: Any) -> dict[str, int]:
    return {
        "base_cells": int(plan.totals["base_cells"]),
        "fine_windows": int(plan.totals["fine_windows"]),
        "context_windows": int(plan.totals["context_windows"]),
        "windows": int(plan.totals["temporal_segments"]),
        "maximum_modality_records": int(plan.totals["maximum_modality_segment_records"]),
    }


def _window_count(
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
        start_us = index * stride_us
        if min(start_us + length_us, duration_us) > start_us:
            count += 1
        index += 1
    return count


def _smoke_expectations(
    plan: Any, smoke_seconds: float
) -> tuple[dict[str, dict[str, int | float]], dict[str, int], dict[str, int]]:
    if not math.isfinite(smoke_seconds) or smoke_seconds <= 0:
        raise ValueError("SMOKE_SECONDS_MUST_BE_POSITIVE_AND_FINITE")
    per_source: dict[str, dict[str, int | float]] = {}
    totals: Counter[str] = Counter()
    for source in plan.sources:
        duration_seconds = min(float(source.duration_seconds), smoke_seconds)
        base_cells = _window_count(
            duration_seconds,
            length_seconds=4,
            stride_seconds=4,
            minimum_remaining_seconds=0,
        )
        fine_windows = _window_count(
            duration_seconds,
            length_seconds=8,
            stride_seconds=4,
            minimum_remaining_seconds=4,
        )
        context_windows = _window_count(
            duration_seconds,
            length_seconds=32,
            stride_seconds=16,
            minimum_remaining_seconds=16,
        )
        temporal_segments = fine_windows + context_windows
        whisper_chunks = math.ceil(duration_seconds / 30)
        counts: dict[str, int | float] = {
            "duration_seconds": duration_seconds,
            "base_cells": base_cells,
            "fine_windows": fine_windows,
            "context_windows": context_windows,
            "temporal_segments": temporal_segments,
            "whisper_chunks": whisper_chunks,
        }
        per_source[source.source_id] = counts
        totals.update(
            {
                "base_cells": base_cells,
                "fine_windows": fine_windows,
                "context_windows": context_windows,
                "windows": temporal_segments,
                "whisper_chunks": whisper_chunks,
            }
        )
    segment_totals = {
        "base_cells": totals["base_cells"],
        "fine_windows": totals["fine_windows"],
        "context_windows": totals["context_windows"],
        "windows": totals["windows"],
        "maximum_modality_records": totals["windows"] * 3,
    }
    observation_counts = {
        "routing_cells": totals["base_cells"],
        "clip_cells": totals["base_cells"],
        "vision_records": totals["windows"],
        "whisper_chunks": totals["whisper_chunks"],
        "speech_records": totals["whisper_chunks"],
        "ast_fine_calls": totals["fine_windows"],
        "ambient_records": totals["windows"],
    }
    return per_source, segment_totals, observation_counts


def _check_search_leakage(index: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    vocabulary_maps = {"term_frequency", "document_frequency"}
    for modality_name, modality in index.get("modalities", {}).items():
        for record_index, record in enumerate(modality.get("documents", [])):
            stack: list[tuple[Any, str | None, str]] = [
                (record, None, f"{modality_name}[{record_index}]")
            ]
            while stack:
                value, parent, location = stack.pop()
                if isinstance(value, Mapping):
                    for key, child in value.items():
                        if parent not in vocabulary_maps and key in FORBIDDEN_SEARCH_KEYS:
                            failures.append(f"index_leakage:{location}.{key}")
                        stack.append((child, str(key), f"{location}.{key}"))
                elif isinstance(value, list):
                    for position, child in enumerate(value):
                        stack.append((child, parent, f"{location}[{position}]") )
    return failures


def verify_index(
    repo_root: str | Path,
    *,
    plan_path: str | Path = PLAN_RELATIVE_PATH,
    output_root: str | Path | None = None,
    smoke_seconds: float | None = None,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    failures: list[str] = []
    checks = 0

    def check(condition: bool, name: str) -> None:
        nonlocal checks
        checks += 1
        if not condition:
            failures.append(name)

    try:
        plan = load_source_plan(root, plan_path=plan_path)
    except Exception as exc:  # noqa: BLE001 - verifier must report malformed inputs.
        return {
            "verified": False,
            "decision": "MINI_PILOT_INDEX_NO_GO",
            "check_count": 1,
            "failures": [f"source_plan:{exc}"],
        }
    output = Path(output_root) if output_root is not None else plan.output_root
    output = output if output.is_absolute() else root / output
    try:
        output.resolve(strict=False).relative_to(root)
    except ValueError:
        return {
            "verified": False,
            "decision": "MINI_PILOT_INDEX_NO_GO",
            "check_count": 1,
            "failures": ["output_root_outside_repository"],
        }

    check(output.is_dir() and _check_mode(output, 0o700), "output_root_mode_or_missing")
    documents: dict[str, Any] = {}
    for name in TOP_LEVEL_ARTIFACTS:
        path = output / name
        check(path.is_file() and _check_mode(path, 0o600), f"artifact_mode_or_missing:{name}")
        if path.is_file():
            try:
                documents[name] = _load(path)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                failures.append(f"artifact_json:{name}:{exc}")
    if len(documents) != len(TOP_LEVEL_ARTIFACTS):
        return {
            "verified": False,
            "decision": "MINI_PILOT_INDEX_NO_GO",
            "check_count": checks,
            "failures": failures,
        }

    segment = documents["segment_manifest.json"]
    observation = documents["observation_manifest.json"]
    index = documents["full_timeline_index.json"]
    resource = documents["resource_manifest.json"]
    build = documents["build_manifest.json"]
    if smoke_seconds is None:
        expected_per_source = {
            source.source_id: {
                "duration_seconds": float(source.duration_seconds),
                "base_cells": int(source.expected_counts["base_cells"]),
                "fine_windows": int(source.expected_counts["fine_windows"]),
                "context_windows": int(source.expected_counts["context_windows"]),
                "temporal_segments": int(source.expected_counts["temporal_segments"]),
                "whisper_chunks": int(source.expected_counts["whisper_chunks"]),
            }
            for source in plan.sources
        }
        expected_segment_totals = _expected_segment_totals(plan)
        expected_observation_counts = {
            "routing_cells": int(plan.totals["base_cells"]),
            "clip_cells": int(plan.totals["clip_frame_forwards"]),
            "vision_records": int(plan.totals["temporal_segments"]),
            "whisper_chunks": int(plan.totals["whisper_chunks"]),
            "speech_records": int(plan.totals["whisper_chunks"]),
            "ast_fine_calls": int(plan.totals["ast_fine_calls"]),
            "ambient_records": int(plan.totals["temporal_segments"]),
        }
        check(build.get("smoke_seconds") is None, "unexpected_smoke_build")
        verification_mode = "full_build"
    else:
        try:
            (
                expected_per_source,
                expected_segment_totals,
                expected_observation_counts,
            ) = _smoke_expectations(plan, smoke_seconds)
        except ValueError as exc:
            return {
                "verified": False,
                "decision": "MINI_PILOT_INDEX_NO_GO",
                "check_count": checks + 1,
                "failures": [str(exc)],
            }
        observed_smoke = build.get("smoke_seconds")
        check(
            isinstance(observed_smoke, (int, float))
            and math.isclose(
                float(observed_smoke), smoke_seconds, rel_tol=0.0, abs_tol=1e-9
            ),
            "smoke_seconds_binding",
        )
        verification_mode = "bounded_smoke"

    for document, key, name in (
        (segment, "segment_manifest_hash", "segment_manifest_hash"),
        (observation, "observation_manifest_hash", "observation_manifest_hash"),
        (index, "index_hash", "index_hash"),
        (resource, "resource_manifest_hash", "resource_manifest_hash"),
        (build, "build_manifest_hash", "build_manifest_hash"),
    ):
        check(_self_hash(document, key), name)

    expected_sources = {source.source_id: source for source in plan.sources}
    check(segment.get("source_count") == 4, "segment_source_count")
    check(observation.get("source_count") == 4, "observation_source_count")
    check(observation.get("expected_source_count") == 4, "observation_expected_source_count")
    check(observation.get("all_sources_complete") is True, "observations_incomplete")
    check(index.get("source_count") == 4, "index_source_count")
    check(build.get("source_count") == 4, "build_source_count")
    check(resource.get("sources") and len(resource["sources"]) == 4, "resource_source_count")
    check(segment.get("totals") == expected_segment_totals, "segment_counts")
    check(
        {item.get("source_ref") for item in segment.get("sources", [])}
        == set(expected_sources),
        "segment_source_ids",
    )
    check(index.get("source_hashes") == {
        source.source_id: source.media_sha256 for source in plan.sources
    }, "index_source_hashes")
    for item in segment.get("sources", []):
        expected = expected_sources.get(item.get("source_ref"))
        if expected is None:
            continue
        check(item.get("sha256") == expected.media_sha256, f"source_hash:{expected.source_id}")
        check(item.get("size_bytes") == expected.media_bytes, f"source_bytes:{expected.source_id}")
        expected_counts = expected_per_source[expected.source_id]
        check(
            item.get("duration_us")
            == round(float(expected_counts["duration_seconds"]) * 1_000_000),
            f"source_duration:{expected.source_id}",
        )
        check(item.get("counts") == {
            "base_cells": expected_counts["base_cells"],
            "fine_windows": expected_counts["fine_windows"],
            "context_windows": expected_counts["context_windows"],
            "windows": expected_counts["temporal_segments"],
        }, f"source_counts:{expected.source_id}")

    check(observation.get("counts") == expected_observation_counts, "observation_counts")
    check(len(observation.get("checkpoints", [])) == 16, "checkpoint_count")
    check(observation.get("no_persisted_media_derivatives") is True, "observation_media_boundary")
    check(observation.get("config", {}).get("device") == "cpu", "observation_device")
    check(observation.get("config", {}).get("offline_local_only") is True, "observation_offline")

    checkpoint_root = output / "checkpoints"
    check(
        checkpoint_root.is_dir() and _check_mode(checkpoint_root, 0o700),
        "checkpoint_root_mode_or_missing",
    )
    checkpoint_names: Counter[tuple[str, str]] = Counter()
    for meta in observation.get("checkpoints", []):
        try:
            path = _repo_path(root, meta["path"])
            check(path.is_relative_to(output), f"checkpoint_outside_output:{meta['path']}")
            check(
                path.parent.is_dir() and _check_mode(path.parent, 0o700),
                f"checkpoint_directory_mode:{path.parent.name}",
            )
            check(path.is_file() and _check_mode(path, 0o600), f"checkpoint_mode_or_missing:{meta['path']}")
            source_id = path.parent.name
            layer_name = path.name
            checkpoint_names[(source_id, layer_name)] += 1
            expected_source = expected_sources[source_id]
            layer_version, scale, count_key = CHECKPOINT_LAYERS[layer_name]
            expected_count = int(expected_per_source[source_id][count_key])
            expected_key = "/".join((
                expected_source.media_sha256,
                layer_version,
                scale,
                "0",
                observation["config_hash"],
            ))
            body = _load(path)
            payload = {
                key: value for key, value in body.items()
                if key not in {"checkpoint_key", "record_count", "payload_hash"}
            }
            check(meta.get("record_count") == expected_count, f"checkpoint_count:{source_id}:{layer_name}")
            check(meta.get("key") == expected_key, f"checkpoint_key:{source_id}:{layer_name}")
            check(body.get("checkpoint_key") == expected_key, f"checkpoint_body_key:{source_id}:{layer_name}")
            check(body.get("record_count") == expected_count, f"checkpoint_body_count:{source_id}:{layer_name}")
            check(body.get("payload_hash") == _json_hash(payload), f"checkpoint_payload_hash:{source_id}:{layer_name}")
            check(meta.get("payload_hash") == body.get("payload_hash"), f"checkpoint_meta_payload_hash:{source_id}:{layer_name}")
            check(meta.get("size_bytes") == path.stat().st_size, f"checkpoint_bytes:{source_id}:{layer_name}")
            check(meta.get("sha256") == _sha256(path), f"checkpoint_sha256:{source_id}:{layer_name}")
            if layer_name == "speech.json":
                chunks = body.get("chunks", [])
                check(len(chunks) == expected_count, f"whisper_chunk_payload:{source_id}")
                check(
                    all(
                        isinstance(item.get("text"), str)
                        and isinstance(item.get("token_count"), int)
                        and item.get("source_ref") == source_id
                        and isinstance(item.get("quality_gate_pass"), bool)
                        and isinstance(item.get("quality_flags"), list)
                        for item in chunks
                    ),
                    f"whisper_inference_payload:{source_id}",
                )
            elif layer_name == "ambient.json":
                records = body.get("records", [])
                fine_records = [
                    item for item in records if item.get("scale") == "fine"
                ]
                check(
                    len(fine_records) == expected_count,
                    f"ast_fine_payload:{source_id}",
                )
                check(
                    all(
                        len(item.get("labels", [])) == 15
                        and all(
                            isinstance(label.get("class_id"), int)
                            and isinstance(label.get("label"), str)
                            and isinstance(label.get("probability"), (int, float))
                            and 0.0 <= float(label["probability"]) <= 1.0
                            for label in item["labels"]
                        )
                        for item in fine_records
                    ),
                    f"ast_inference_payload:{source_id}",
                )
            elif layer_name == "vision_clip.json":
                vectors = body.get("cell_vectors", [])
                check(len(vectors) == expected_count, f"clip_cell_payload:{source_id}")
                check(
                    all(
                        item.get("dimension") == 512
                        and item.get("l2_normalized") is True
                        and isinstance(item.get("vector_f16_hex"), str)
                        and len(item["vector_f16_hex"]) == 512 * 2 * 2
                        and any(
                            character != "0"
                            for character in item["vector_f16_hex"]
                        )
                        for item in vectors
                    ),
                    f"clip_inference_payload:{source_id}",
                )
            elif layer_name == "vision_routing.json":
                records = body.get("records", [])
                check(
                    len(records) == expected_count,
                    f"routing_record_payload:{source_id}",
                )
                check(
                    all(
                        item.get("source_ref") == source_id
                        and isinstance(item.get("pts"), int)
                        and isinstance(item.get("time_base"), str)
                        and item.get("features", {}).get(
                            "semantic_claim_allowed"
                        )
                        is False
                        for item in records
                    ),
                    f"routing_inference_payload:{source_id}",
                )
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            failures.append(f"checkpoint_integrity:{meta.get('path')}:{exc}")
    expected_checkpoint_names = {
        (source_id, layer_name) for source_id in expected_sources for layer_name in CHECKPOINT_LAYERS
    }
    check(set(checkpoint_names) == expected_checkpoint_names, "checkpoint_source_layer_matrix")
    check(all(value == 1 for value in checkpoint_names.values()), "duplicate_checkpoints")

    check(index.get("segment_manifest_hash") == segment.get("segment_manifest_hash"), "index_segment_binding")
    check(index.get("observation_manifest_hash") == observation.get("observation_manifest_hash"), "index_observation_binding")
    expected_index_counts = {
        key: expected_observation_counts[key]
        for key in ("speech_records", "ambient_records", "vision_records")
    }
    check(index.get("counts") == expected_index_counts, "index_counts")
    failures.extend(_check_search_leakage(index))

    expected_models = plan.model_snapshots
    models = resource.get("models", {})
    check(set(models) == set(MODEL_PLAN_NAMES), "model_set")
    for resource_name, plan_name in MODEL_PLAN_NAMES.items():
        expected = expected_models[plan_name]
        actual = models.get(resource_name, {})
        check(actual.get("frozen") is True, f"model_frozen:{resource_name}")
        check(actual.get("local_files_only") is True, f"model_offline:{resource_name}")
        check(actual.get("device") == "cpu", f"model_device:{resource_name}")
        expected_path = expected.get("haar_snapshot_path", expected.get("snapshot_path"))
        check(actual.get("path") == expected_path, f"model_path:{resource_name}")
        if resource_name == "opencv_haar":
            observed = actual.get("files", [{}])[0].get("sha256")
            check(observed == expected["haar_sha256"], "model_hash:opencv_haar")
        else:
            check(actual.get("snapshot_hash") == expected["snapshot_hash"], f"model_snapshot_hash:{resource_name}")
            check(any(item.get("sha256") == expected["weights_sha256"] for item in actual.get("files", [])), f"model_weight_hash:{resource_name}")
        for item in actual.get("files", []):
            try:
                path = _repo_path(root, item["path"])
                check(path.is_file() and not path.is_symlink(), f"model_file:{item['path']}")
                check(path.stat().st_size == item.get("size_bytes"), f"model_file_bytes:{item['path']}")
                check(_sha256(path, prefixed=False) == item.get("sha256"), f"model_file_hash:{item['path']}")
            except (KeyError, OSError, TypeError, ValueError) as exc:
                failures.append(f"model_file:{item.get('path')}:{exc}")

    check(resource.get("runtime", {}).get("device") == "cpu", "resource_device")
    check(resource.get("runtime", {}).get("network_access") == "disabled", "resource_offline")
    check(
        resource.get("runtime", {}).get("HF_HUB_OFFLINE") == "1",
        "resource_hf_offline",
    )
    check(
        resource.get("runtime", {}).get("TRANSFORMERS_OFFLINE") == "1",
        "resource_transformers_offline",
    )
    check(
        observation.get("config", {}).get("model_snapshot_hashes")
        == {
            name: item.get("snapshot_hash")
            for name, item in resource.get("models", {}).items()
        },
        "observation_model_snapshot_binding",
    )
    check(resource.get("rights_policy", {}).get("rights_metadata_searchable") is False, "rights_not_searchable")
    check(resource.get("rights_policy", {}).get("redistribution_authorized") is False, "redistribution_gate")
    check(all(value is False for value in resource.get("media_derivatives", {}).values()), "resource_media_boundary")

    boundary = build.get("terminal_boundary", {})
    check(build.get("status") == "COMPLETE", "build_status")
    check(build.get("checkpoint_count") == 16, "build_checkpoint_count")
    check(build.get("no_persisted_media_derivatives") is True, "build_media_boundary")
    expected_hard_cap_mib = int(
        plan.raw["storage_caps"]["derived_artifacts_hard_fail_cap_mib"]
    )
    check(
        build.get("derived_artifact_hard_cap_mib") == expected_hard_cap_mib,
        "build_derived_storage_hard_cap_binding",
    )
    check(boundary.get("last_allowed_stage") == "resource_manifest", "terminal_stage")
    check(all(boundary.get(key) is False for key in (
        "families_generated", "negatives_generated", "interventions_generated",
        "trajectories_generated", "evaluation_generated",
    )), "downstream_boundary")
    check(set(build.get("completed_stages", [])) == {
        "segment_manifest", "observation_manifest", "full_timeline_index", "resource_manifest"
    }, "completed_stage_set")
    inventory_paths = set()
    for artifact in build.get("artifacts", []):
        try:
            path = _repo_path(root, artifact["path"])
            inventory_paths.add(path.name)
            check(path.is_relative_to(output), f"artifact_outside_output:{artifact['path']}")
            check(path.is_file() and _check_mode(path, 0o600), f"artifact_inventory_mode:{artifact['path']}")
            check(path.stat().st_size == artifact.get("size_bytes"), f"artifact_inventory_bytes:{artifact['path']}")
            check(_sha256(path) == artifact.get("sha256"), f"artifact_inventory_hash:{artifact['path']}")
        except (KeyError, OSError, TypeError, ValueError) as exc:
            failures.append(f"artifact_inventory:{artifact.get('path')}:{exc}")
    check(inventory_paths == set(TOP_LEVEL_ARTIFACTS) - {"build_manifest.json"}, "artifact_inventory_set")

    for name, document in documents.items():
        failures.extend(f"{name}:{failure}" for failure in _check_repo_relative_paths(document, root))

    derivative_paths: list[str] = []
    downstream_paths: list[str] = []
    derived_bytes = 0
    for path in output.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        derived_bytes += path.stat().st_size
        if path.suffix.casefold() in MEDIA_SUFFIXES:
            derivative_paths.append(relative)
        if any(term in path.name.casefold() for term in DOWNSTREAM_TERMS):
            downstream_paths.append(relative)
    check(not derivative_paths, "persisted_media_derivatives:" + ",".join(derivative_paths))
    check(not downstream_paths, "downstream_artifacts:" + ",".join(downstream_paths))
    check(
        build.get("derived_artifact_bytes_before_build_manifest")
        == derived_bytes - (output / "build_manifest.json").stat().st_size,
        "build_derived_bytes_binding",
    )
    check(
        derived_bytes <= expected_hard_cap_mib * 1024 * 1024,
        "derived_storage_hard_cap",
    )

    return {
        "verified": not failures,
        "decision": (
            "MINI_PILOT_INDEX_SMOKE_VERIFIED"
            if not failures and verification_mode == "bounded_smoke"
            else "MINI_PILOT_INDEX_VERIFIED"
            if not failures
            else "MINI_PILOT_INDEX_NO_GO"
        ),
        "verification_mode": verification_mode,
        "smoke_seconds": smoke_seconds,
        "check_count": checks,
        "failures": failures,
        "counts": {
            "sources": segment.get("source_count"),
            "checkpoints": len(observation.get("checkpoints", [])),
            "base_cells": segment.get("totals", {}).get("base_cells"),
            "temporal_segments": segment.get("totals", {}).get("windows"),
            "derived_bytes": derived_bytes,
        },
        "boundaries": {
            "repo_relative_paths": not any("path" in item for item in failures),
            "index_leakage_absent": not any(item.startswith("index_leakage") for item in failures),
            "persisted_media_derivatives": False,
            "downstream_artifacts": False,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--plan", default=str(PLAN_RELATIVE_PATH))
    parser.add_argument("--output-root", default=None)
    parser.add_argument(
        "--smoke-seconds",
        type=float,
        default=None,
        help="Verify a bounded smoke and derive exact counts from this duration.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = verify_index(
            args.repo_root,
            plan_path=args.plan,
            output_root=args.output_root,
            smoke_seconds=args.smoke_seconds,
        )
    except Exception as exc:  # noqa: BLE001 - CLI converts fail-closed errors to JSON.
        result = {
            "verified": False,
            "decision": "MINI_PILOT_INDEX_NO_GO",
            "failures": [str(exc)],
        }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("verified") else 2


if __name__ == "__main__":
    raise SystemExit(main())
