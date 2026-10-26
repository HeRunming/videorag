#!/usr/bin/env python3
"""Verify the isolated EPIC Wave-1 full-timeline index."""

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

from av_trace_epic_wave1_index.core import (
    FORBIDDEN_SEARCH_KEYS,
    INDEX_VERSION,
    SCHEMA_VERSION,
    STAGE,
    TOP_LEVEL_ARTIFACTS,
)
from av_trace_epic_wave1_index.sources import PLAN_RELATIVE_PATH, load_source_plan

CHECKPOINTS = {
    "speech.json": {
        "layer_version": "whisper-tiny-en-frozen/1.0",
        "scale": "30-second",
        "count_key": "whisper_chunks",
    },
    "ambient.json": {
        "layer_version": "ast-audioset-frozen/1.0",
        "scale": "fine",
        "count_key": "fine_windows",
    },
    "vision_routing.json": {
        "layer_version": "opencv-routing/1.0",
        "scale": "base",
        "count_key": "base_cells",
    },
    "vision_clip.json": {
        "layer_version": "clip-visual/1.0",
        "scale": "base",
        "count_key": "base_cells",
    },
}
MEDIA_SUFFIXES = {
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
DOWNSTREAM_TERMS = (
    "famil",
    "intervention",
    "trajectory",
    "evaluation",
    "metric",
    "controller",
    "agent_run",
)


def _load(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


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


def _checkpoint_payload(
    path: Path, checkpoint: Mapping[str, Any]
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    body = _load(path)
    if not isinstance(body, Mapping):
        raise TypeError("CHECKPOINT_BODY_NOT_MAPPING")
    payload = {
        key: value
        for key, value in body.items()
        if key not in {"checkpoint_key", "record_count", "payload_hash"}
    }
    if body.get("checkpoint_key") != checkpoint.get("key"):
        raise ValueError("CHECKPOINT_KEY_MISMATCH")
    if body.get("record_count") != checkpoint.get("record_count"):
        raise ValueError("CHECKPOINT_RECORD_COUNT_MISMATCH")
    if body.get("payload_hash") != checkpoint.get("payload_hash"):
        raise ValueError("CHECKPOINT_PAYLOAD_META_MISMATCH")
    if body.get("payload_hash") != _json_hash(payload):
        raise ValueError("CHECKPOINT_PAYLOAD_HASH_MISMATCH")
    return body, payload


def _mode(path: Path, expected: int) -> bool:
    return not path.is_symlink() and stat.S_IMODE(path.stat().st_mode) == expected


def _repo_path(root: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"INVALID_REPO_PATH:{value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts or ".staging" in pure.parts:
        raise ValueError(f"INVALID_REPO_PATH:{value}")
    candidate = root.joinpath(*pure.parts)
    candidate.resolve(strict=False).relative_to(root)
    return candidate


def _walk(value: Any):
    if isinstance(value, Mapping):
        for key, child in value.items():
            yield key, child
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _search_leakage(index: Mapping[str, Any]) -> list[str]:
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
                        stack.append((child, parent, f"{location}[{position}]"))
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
    except Exception as exc:  # noqa: BLE001 - verifier reports malformed inputs.
        return {
            "verified": False,
            "decision": "EPIC_WAVE1_INDEX_IMPLEMENTATION_REPAIR",
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
            "decision": "EPIC_WAVE1_INDEX_IMPLEMENTATION_NO_GO",
            "check_count": 1,
            "failures": ["output_root_outside_repository"],
        }
    check(output.is_dir() and _mode(output, 0o700), "output_root_mode_or_missing")
    documents: dict[str, Any] = {}
    for name in TOP_LEVEL_ARTIFACTS:
        path = output / name
        check(path.is_file() and _mode(path, 0o600), f"artifact_mode_or_missing:{name}")
        if path.is_file():
            try:
                documents[name] = _load(path)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                failures.append(f"artifact_json:{name}:{exc}")
    if len(documents) != len(TOP_LEVEL_ARTIFACTS):
        return {
            "verified": False,
            "decision": "EPIC_WAVE1_INDEX_IMPLEMENTATION_REPAIR",
            "check_count": checks,
            "failures": failures,
        }

    segment = documents["segment_manifest.json"]
    observation = documents["observation_manifest.json"]
    index = documents["full_timeline_index.json"]
    resource = documents["resource_manifest.json"]
    build = documents["build_manifest.json"]
    for document, key in (
        (segment, "segment_manifest_hash"),
        (observation, "observation_manifest_hash"),
        (index, "index_hash"),
        (resource, "resource_manifest_hash"),
        (build, "build_manifest_hash"),
    ):
        check(_self_hash(document, key), key)
        check(document.get("schema_version") == SCHEMA_VERSION, f"{key}:schema")
        check(document.get("stage") == STAGE, f"{key}:stage")
    check(index.get("index_version") == INDEX_VERSION, "index_version")
    check(build.get("index_version") == INDEX_VERSION, "build_index_version")

    source_ids = [source.source_id for source in plan.sources]
    check(segment.get("source_count") == 2, "segment_source_count")
    check(observation.get("source_count") == 2, "observation_source_count")
    check(index.get("source_count") == 2, "index_source_count")
    check(build.get("source_count") == 2, "build_source_count")
    check(
        [item.get("source_ref") for item in segment.get("sources", [])] == sorted(source_ids),
        "segment_source_ids",
    )
    expected_hashes = {
        source.source_id: source.media_sha256 for source in plan.sources
    }
    check(index.get("source_hashes") == expected_hashes, "index_source_hashes")
    check(build.get("source_sha256") == expected_hashes, "build_source_hashes")
    check(
        build.get("acquisition_manifest_sha256")
        == plan.acquisition_manifest_sha256,
        "acquisition_manifest_hash_binding",
    )
    check(
        build.get("acquisition_decision") == "EPIC_WAVE1_ACQUISITION_READY",
        "acquisition_decision_binding",
    )
    check(
        resource.get("acquisition_gate", {}).get("manifest_sha256")
        == plan.acquisition_manifest_sha256,
        "resource_acquisition_manifest_hash_binding",
    )
    check(
        resource.get("acquisition_gate", {}).get("passed") is True,
        "resource_acquisition_gate",
    )
    expected_resource_sources = {
        source.source_id: {
            "media_path": source.media_path.relative_to(root).as_posix(),
            "source_manifest_path": source.source_manifest_path.relative_to(
                root
            ).as_posix(),
            "sha256": source.media_sha256,
            "size_bytes": source.media_bytes,
        }
        for source in plan.sources
    }
    observed_resource_sources = {
        item.get("source_ref"): {
            key: item.get(key)
            for key in (
                "media_path",
                "source_manifest_path",
                "sha256",
                "size_bytes",
            )
        }
        for item in resource.get("sources", [])
        if isinstance(item, Mapping)
    }
    check(
        observed_resource_sources == expected_resource_sources,
        "resource_source_bindings",
    )

    config = observation.get("config", {})
    config_hash = observation.get("config_hash")
    check(
        isinstance(config, Mapping) and config_hash == _json_hash(config),
        "observation_config_hash",
    )
    check(
        config.get("segment_manifest_hash")
        == segment.get("segment_manifest_hash"),
        "observation_segment_binding",
    )
    check(config.get("threads") == 8, "observation_threads")
    check(config.get("device") == "cpu", "observation_device")
    for runtime_name, runtime in (
        ("resource", resource.get("runtime", {})),
        ("observation", observation.get("runtime", {})),
    ):
        check(runtime.get("device") == "cpu", f"{runtime_name}_runtime_device")
        check(
            runtime.get("network_access") == "disabled",
            f"{runtime_name}_runtime_network",
        )
        check(
            runtime.get("HF_HUB_OFFLINE") == "1",
            f"{runtime_name}_runtime_hf_offline",
        )
        check(
            runtime.get("TRANSFORMERS_OFFLINE") == "1",
            f"{runtime_name}_runtime_transformers_offline",
        )

    model_plan_names = {
        "whisper": "speech",
        "ast": "ambient",
        "clip": "vision_semantic",
        "opencv_haar": "vision_routing",
    }
    observed_model_snapshot_hashes: dict[str, Any] = {}
    for model_name, plan_name in model_plan_names.items():
        model = resource.get("models", {}).get(model_name, {})
        spec = plan.model_snapshots[plan_name]
        observed_model_snapshot_hashes[model_name] = model.get("snapshot_hash")
        check(model.get("frozen") is True, f"model_frozen:{model_name}")
        check(
            model.get("local_files_only") is True,
            f"model_local_only:{model_name}",
        )
        check(model.get("device") == "cpu", f"model_device:{model_name}")
        expected_path = (
            spec["haar_snapshot_path"]
            if model_name == "opencv_haar"
            else spec["snapshot_path"]
        )
        check(model.get("path") == expected_path, f"model_path:{model_name}")
        try:
            model_base = _repo_path(root, expected_path)
        except ValueError:
            failures.append(f"model_path_invalid:{model_name}:{expected_path}")
            continue
        model_files = model.get("files", [])
        check(
            isinstance(model_files, list) and bool(model_files),
            f"model_files:{model_name}",
        )
        snapshot_records: list[dict[str, Any]] = []
        observed_model_paths: set[str] = set()
        for file_record in model_files if isinstance(model_files, list) else []:
            try:
                model_file = _repo_path(root, file_record.get("path"))
            except ValueError:
                failures.append(
                    f"model_file_path:{model_name}:{file_record.get('path')}"
                )
                continue
            try:
                snapshot_path = (
                    model_file.name
                    if model_file == model_base
                    else model_file.relative_to(model_base).as_posix()
                )
            except ValueError:
                failures.append(
                    f"model_file_outside_snapshot:{model_name}:"
                    f"{file_record.get('path')}"
                )
                continue
            observed_model_paths.add(model_file.relative_to(root).as_posix())
            check(
                model_file.is_file() and _mode(model_file, 0o600),
                f"model_file_mode:{model_name}:{file_record.get('path')}",
            )
            if model_file.is_file():
                check(
                    model_file.stat().st_size == file_record.get("size_bytes"),
                    f"model_file_size:{model_name}:{file_record.get('path')}",
                )
                check(
                    _sha256(model_file, prefixed=False)
                    == file_record.get("sha256"),
                    f"model_file_hash:{model_name}:{file_record.get('path')}",
                )
            snapshot_records.append(
                {
                    "path": snapshot_path,
                    "size_bytes": file_record.get("size_bytes"),
                    "sha256": file_record.get("sha256"),
                }
            )
        actual_model_paths = (
            {model_base.relative_to(root).as_posix()}
            if model_base.is_file()
            else {
                path.relative_to(root).as_posix()
                for path in model_base.rglob("*")
                if path.is_file() and path.name != "SHA256SUMS"
            }
        )
        check(
            observed_model_paths == actual_model_paths,
            f"model_file_inventory:{model_name}",
        )
        check(
            model.get("snapshot_hash") == _json_hash(snapshot_records),
            f"model_snapshot_recomputed:{model_name}",
        )
        if model_name == "opencv_haar":
            check(
                len(model_files) == 1
                and model_files[0].get("sha256") == spec["haar_sha256"],
                "model_pin:opencv_haar",
            )
        else:
            check(
                model.get("snapshot_hash") == spec["snapshot_hash"],
                f"model_snapshot_pin:{model_name}",
            )
            check(
                any(
                    item.get("sha256") == spec["weights_sha256"]
                    for item in model_files
                ),
                f"model_weight_pin:{model_name}",
            )
    check(
        config.get("model_snapshot_hashes") == observed_model_snapshot_hashes,
        "checkpoint_model_snapshot_binding",
    )

    if smoke_seconds is None:
        expected = plan.totals
        expected_source_counts = {
            source.source_id: source.expected_counts for source in plan.sources
        }
        check(build.get("mode") == "full", "build_mode")
        check(build.get("smoke_seconds") is None, "unexpected_smoke_seconds")
    else:
        if not math.isfinite(smoke_seconds) or smoke_seconds <= 0:
            return {
                "verified": False,
                "decision": "EPIC_WAVE1_INDEX_IMPLEMENTATION_NO_GO",
                "check_count": checks + 1,
                "failures": ["SMOKE_SECONDS_INVALID"],
            }
        expected_source_counts = {}
        totals: Counter[str] = Counter()
        from av_trace_epic_wave1_index.sources import computed_counts

        for source in plan.sources:
            counts = computed_counts(min(source.duration_seconds, smoke_seconds))
            expected_source_counts[source.source_id] = counts
            totals.update(counts)
        expected = {
            "base_cells": totals["base_cells"],
            "fine_windows": totals["fine_windows"],
            "context_windows": totals["context_windows"],
            "temporal_segments": totals["temporal_segments"],
            "whisper_chunks": totals["whisper_chunks"],
            "checkpoint_count": totals["checkpoints"],
        }
        check(build.get("mode") == "smoke", "build_mode")
        check(
            math.isclose(
                float(build.get("smoke_seconds", -1)),
                smoke_seconds,
                rel_tol=0.0,
                abs_tol=1e-9,
            ),
            "smoke_seconds_binding",
        )
    observed_sources = {
        item["source_ref"]: item for item in segment.get("sources", [])
    }
    for source_id, counts in expected_source_counts.items():
        observed = observed_sources.get(source_id, {}).get("counts", {})
        check(observed.get("base_cells") == counts["base_cells"], f"{source_id}:base")
        check(observed.get("fine_windows") == counts["fine_windows"], f"{source_id}:fine")
        check(
            observed.get("context_windows") == counts["context_windows"],
            f"{source_id}:context",
        )
        check(
            observed.get("windows") == counts["temporal_segments"],
            f"{source_id}:segments",
        )
    segment_totals = segment.get("totals", {})
    check(segment_totals.get("base_cells") == expected["base_cells"], "total_base")
    check(segment_totals.get("fine_windows") == expected["fine_windows"], "total_fine")
    check(
        segment_totals.get("context_windows") == expected["context_windows"],
        "total_context",
    )
    check(
        segment_totals.get("windows") == expected["temporal_segments"],
        "total_segments",
    )
    check(
        observation.get("counts", {}).get("whisper_chunks")
        == expected["whisper_chunks"],
        "total_whisper",
    )
    check(
        len(observation.get("checkpoints", [])) == expected["checkpoint_count"],
        "checkpoint_count",
    )

    expected_checkpoint_paths = {
        (
            output
            / "checkpoints"
            / source_id
            / checkpoint_name
        ).relative_to(root).as_posix()
        for source_id in source_ids
        for checkpoint_name in CHECKPOINTS
    }
    observed_checkpoint_paths: list[str] = []
    for checkpoint in observation.get("checkpoints", []):
        path_value = checkpoint.get("path")
        observed_checkpoint_paths.append(str(path_value))
        try:
            path = _repo_path(root, path_value)
        except ValueError:
            failures.append(f"checkpoint_path:{path_value}")
            continue
        name = path.name
        check(name in CHECKPOINTS, f"checkpoint_name:{name}")
        try:
            relative_checkpoint = path.relative_to(output / "checkpoints")
        except ValueError:
            failures.append(f"checkpoint_outside_output:{path_value}")
            continue
        check(
            len(relative_checkpoint.parts) == 2,
            f"checkpoint_layout:{path_value}",
        )
        if len(relative_checkpoint.parts) != 2 or name not in CHECKPOINTS:
            continue
        source_id = relative_checkpoint.parts[0]
        check(source_id in expected_hashes, f"checkpoint_source:{path_value}")
        if source_id not in expected_hashes:
            continue
        checkpoint_spec = CHECKPOINTS[name]
        expected_count = expected_source_counts[source_id][
            checkpoint_spec["count_key"]
        ]
        expected_key = "/".join(
            (
                expected_hashes[source_id],
                checkpoint_spec["layer_version"],
                checkpoint_spec["scale"],
                "0",
                str(config_hash),
            )
        )
        check(
            checkpoint.get("key") == expected_key,
            f"checkpoint_key:{path_value}",
        )
        check(
            checkpoint.get("record_count") == expected_count,
            f"checkpoint_record_count:{path_value}",
        )
        check(path.is_file() and _mode(path, 0o600), f"checkpoint_mode:{path_value}")
        if not path.is_file():
            continue
        check(
            checkpoint.get("size_bytes") == path.stat().st_size,
            f"checkpoint_size:{path_value}",
        )
        check(
            checkpoint.get("sha256") == _sha256(path),
            f"checkpoint_hash:{path_value}",
        )
        try:
            body, payload = _checkpoint_payload(path, checkpoint)
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
        ) as exc:
            failures.append(f"checkpoint_payload:{path_value}:{exc}")
            continue
        check(
            payload.get("layer_version") == checkpoint_spec["layer_version"],
            f"checkpoint_layer:{path_value}",
        )
        if name == "speech.json":
            chunks = payload.get("chunks", [])
            records = payload.get("records", [])
            check(
                len(chunks) == expected_count,
                f"checkpoint_chunks:{path_value}",
            )
            check(
                len(records) == expected_count,
                f"checkpoint_speech_records:{path_value}",
            )
            source_records = [*chunks, *records]
        elif name == "ambient.json":
            records = payload.get("records", [])
            check(
                len(records)
                == expected_source_counts[source_id]["temporal_segments"],
                f"checkpoint_ambient_records:{path_value}",
            )
            source_records = records
        elif name == "vision_routing.json":
            records = payload.get("records", [])
            check(
                len(records) == expected_count,
                f"checkpoint_routing_records:{path_value}",
            )
            source_records = records
        else:
            cells = payload.get("cell_vectors", [])
            records = payload.get("segment_records", [])
            check(
                len(cells) == expected_count,
                f"checkpoint_clip_cells:{path_value}",
            )
            check(
                len(records)
                == expected_source_counts[source_id]["temporal_segments"],
                f"checkpoint_vision_records:{path_value}",
            )
            source_records = records
        check(
            all(
                not isinstance(item, Mapping)
                or item.get("source_ref", source_id) == source_id
                for item in source_records
            ),
            f"checkpoint_source_binding:{path_value}",
        )
        check(
            body.get("record_count") == expected_count,
            f"checkpoint_body_record_count:{path_value}",
        )
    check(
        sorted(observed_checkpoint_paths) == sorted(expected_checkpoint_paths),
        "checkpoint_path_inventory",
    )

    check(
        segment.get("segment_manifest_hash") == index.get("segment_manifest_hash"),
        "index_segment_binding",
    )
    check(
        observation.get("observation_manifest_hash")
        == index.get("observation_manifest_hash"),
        "index_observation_binding",
    )
    artifact_records = {
        item.get("path"): item for item in build.get("artifacts", [])
    }
    for name in TOP_LEVEL_ARTIFACTS[:-1]:
        path = output / name
        relative = path.relative_to(root).as_posix()
        record = artifact_records.get(relative, {})
        check(record.get("size_bytes") == path.stat().st_size, f"artifact_size:{name}")
        check(record.get("sha256") == _sha256(path), f"artifact_hash:{name}")
    check(build.get("no_persisted_media_derivatives") is True, "media_boundary")
    check(
        build.get("terminal_boundary")
        == {
            "last_allowed_stage": "resource_manifest",
            "families_generated": False,
            "interventions_generated": False,
            "trajectories_generated": False,
            "evaluation_generated": False,
        },
        "terminal_boundary",
    )
    for path in output.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        check(path.suffix.casefold() not in MEDIA_SUFFIXES, f"media_derivative:{relative}")
        check(
            not any(term in path.name.casefold() for term in DOWNSTREAM_TERMS),
            f"downstream_artifact:{relative}",
        )
        check(_mode(path, 0o600), f"file_mode:{relative}")
    for path in output.rglob("*"):
        if path.is_dir():
            check(_mode(path, 0o700), f"directory_mode:{path.relative_to(root)}")
    expected_output_files = expected_checkpoint_paths | {
        (output / name).relative_to(root).as_posix()
        for name in TOP_LEVEL_ARTIFACTS
    }
    observed_output_files = {
        path.relative_to(root).as_posix()
        for path in output.rglob("*")
        if path.is_file()
    }
    check(observed_output_files == expected_output_files, "output_file_inventory")
    expected_output_directories = {
        output.relative_to(root).as_posix(),
        (output / "checkpoints").relative_to(root).as_posix(),
        *{
            (output / "checkpoints" / source_id)
            .relative_to(root)
            .as_posix()
            for source_id in source_ids
        },
    }
    observed_output_directories = {
        output.relative_to(root).as_posix(),
        *{
            path.relative_to(root).as_posix()
            for path in output.rglob("*")
            if path.is_dir()
        },
    }
    check(
        observed_output_directories == expected_output_directories,
        "output_directory_inventory",
    )
    leakage = _search_leakage(index)
    failures.extend(leakage)
    checks += len(leakage)
    for document in documents.values():
        for key, value in _walk(document):
            if isinstance(value, str) and (
                value.startswith(("/", "file://"))
                or "/jizhicfs/" in value
                or "/.staging/" in value
            ):
                failures.append(f"path_leak:{key}")
                checks += 1
    hard_cap = int(build.get("derived_artifact_hard_cap_mib", 0))
    observed_bytes = sum(
        path.stat().st_size
        for path in output.rglob("*")
        if path.is_file() and path.name != "build_manifest.json"
    )
    check(
        build.get("derived_artifact_bytes_before_build_manifest") == observed_bytes,
        "derived_bytes_binding",
    )
    check(
        hard_cap > 0 and observed_bytes <= hard_cap * 1024 * 1024,
        "derived_hard_cap",
    )
    return {
        "verified": not failures,
        "decision": (
            "EPIC_WAVE1_INDEX_IMPLEMENTATION_READY"
            if not failures
            else "EPIC_WAVE1_INDEX_IMPLEMENTATION_NO_GO"
        ),
        "mode": "smoke" if smoke_seconds is not None else "full",
        "check_count": checks,
        "failure_count": len(failures),
        "failures": failures,
        "output_root": output.relative_to(root).as_posix(),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--plan", default=str(PLAN_RELATIVE_PATH))
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--mode", choices=("smoke", "full"), default="full")
    parser.add_argument("--smoke-seconds", type=float, default=32.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = verify_index(
        args.repo_root,
        plan_path=args.plan,
        output_root=args.output_root,
        smoke_seconds=args.smoke_seconds if args.mode == "smoke" else None,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
