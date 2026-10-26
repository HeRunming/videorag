#!/usr/bin/env python3
"""Independent deterministic audit for the CaptainCook4D Wave-0 index."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from av_trace_captaincook4d_wave0_index.sources import (
    PLAN_RELATIVE_PATH,
    computed_counts,
    load_source_plan,
)

TOP_LEVEL = (
    "segment_manifest.json",
    "observation_manifest.json",
    "full_timeline_index.json",
    "resource_manifest.json",
    "build_manifest.json",
)
CHECKPOINTS = (
    "ambient.json",
    "speech.json",
    "vision_clip.json",
    "vision_routing.json",
)
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
PROHIBITED_NAME_TERMS = (
    "annotation",
    "famil",
    "negative",
    "intervention",
    "trajectory",
    "controller",
    "agent_run",
    "evaluation",
    "metric",
)
FORBIDDEN_SEARCH_KEYS = {
    "answer",
    "answer_aliases",
    "answer_hypothesis",
    "attribution",
    "claim_id",
    "claim_ids",
    "claims",
    "commercial_use",
    "evaluation",
    "evidence_id",
    "evidence_ids",
    "family",
    "family_id",
    "filename",
    "generated_caption",
    "gold",
    "intervention",
    "intervention_id",
    "label",
    "license",
    "license_attribution_boundary",
    "license_url",
    "path",
    "privacy",
    "question",
    "review_id",
    "reviewer_rationale",
    "rights",
    "rights_flags",
    "source_url",
    "state",
    "state_role",
    "title",
    "url",
}


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
    ).encode()


def _json_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _sha256(path: Path, *, prefixed: bool = False) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    value = digest.hexdigest()
    return f"sha256:{value}" if prefixed else value


def _mode(path: Path, expected: int) -> bool:
    return not path.is_symlink() and stat.S_IMODE(path.stat().st_mode) == expected


def _repo_path(root: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"INVALID_PATH:{value!r}")
    pure = PurePosixPath(value)
    if (
        pure.is_absolute()
        or ".." in pure.parts
        or ".staging" in pure.parts
        or pure.as_posix() != value
    ):
        raise ValueError(f"INVALID_PATH:{value}")
    path = root.joinpath(*pure.parts)
    path.resolve(strict=False).relative_to(root)
    return path


def _self_hash(document: Mapping[str, Any], key: str) -> bool:
    copy = dict(document)
    observed = copy.pop(key, None)
    return observed == _json_hash(copy)


def _walk(value: Any):
    if isinstance(value, Mapping):
        for key, child in value.items():
            yield key, child
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _window_records(
    duration_seconds: float,
    *,
    length_seconds: int,
    stride_seconds: int,
    minimum_remaining_seconds: int,
) -> list[tuple[int, int]]:
    duration_us = round(duration_seconds * 1_000_000)
    length_us = length_seconds * 1_000_000
    stride_us = stride_seconds * 1_000_000
    minimum_us = minimum_remaining_seconds * 1_000_000
    output = []
    index = 0
    while duration_us - index * stride_us >= minimum_us:
        start = index * stride_us
        end = min(start + length_us, duration_us)
        if end > start:
            output.append((start, end))
        index += 1
    return output


def _file_snapshot(root: Path) -> dict[str, dict[str, int | str]]:
    return {
        path.relative_to(root).as_posix(): {
            "sha256": _sha256(path),
            "size_bytes": path.stat().st_size,
            "mtime_ns": path.stat().st_mtime_ns,
        }
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def audit_index(
    repo_root: str | Path,
    *,
    plan_path: str | Path = PLAN_RELATIVE_PATH,
    output_root: str | Path | None = None,
    before_snapshot: str | Path | None = None,
) -> dict[str, Any]:
    """Recompute source, lattice, checkpoint, index, and resume invariants."""
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
    except Exception as exc:  # noqa: BLE001 - independent audit records errors.
        return {
            "verified": False,
            "decision": "CAPTAINCOOK4D_WAVE0_FULL_TIMELINE_NO_GO",
            "check_count": 1,
            "failure_count": 1,
            "failures": [f"source_plan:{exc}"],
        }
    output = Path(output_root) if output_root is not None else plan.output_root
    output = output if output.is_absolute() else root / output
    try:
        output.resolve(strict=False).relative_to(root)
    except ValueError:
        return {
            "verified": False,
            "decision": "CAPTAINCOOK4D_WAVE0_FULL_TIMELINE_NO_GO",
            "check_count": 1,
            "failure_count": 1,
            "failures": ["output_root_outside_repository"],
        }
    check(output.is_dir() and _mode(output, 0o700), "output_root")
    documents = {}
    for name in TOP_LEVEL:
        path = output / name
        check(path.is_file() and _mode(path, 0o600), f"top_level:{name}")
        if path.is_file():
            documents[name] = _load(path)
    if len(documents) != len(TOP_LEVEL):
        return {
            "verified": False,
            "decision": "CAPTAINCOOK4D_WAVE0_FULL_TIMELINE_NO_GO",
            "check_count": checks,
            "failure_count": len(failures),
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
        check(_self_hash(document, key), f"self_hash:{key}")
    check(build.get("status") == "COMPLETE", "build_status")
    check(build.get("mode") == "full", "build_mode")
    check(build.get("smoke_seconds") is None, "build_smoke_seconds")
    check(build.get("plan_sha256") == _sha256(plan.plan_path), "plan_hash")
    check(
        build.get("acquisition_manifest_sha256")
        == plan.acquisition_manifest_sha256,
        "acquisition_hash",
    )
    check(build.get("checkpoint_count") == 12, "checkpoint_count")
    expected_source_hashes = {
        source.source_id: source.media_sha256 for source in plan.sources
    }
    check(build.get("source_sha256") == expected_source_hashes, "source_hashes")
    check(index.get("source_hashes") == expected_source_hashes, "index_hashes")
    expected_manifest_hashes = {
        source.source_id: _sha256(source.source_manifest_path)
        for source in plan.sources
    }
    check(
        build.get("source_manifest_sha256") == expected_manifest_hashes,
        "source_manifest_hashes",
    )
    for source in plan.sources:
        check(_sha256(source.media_path) == source.media_sha256, f"media_sha:{source.source_id}")
        check(source.media_path.stat().st_size == source.media_bytes, f"media_size:{source.source_id}")
        check(_mode(source.media_path, 0o600), f"media_mode:{source.source_id}")
        check(_mode(source.source_manifest_path, 0o600), f"manifest_mode:{source.source_id}")
        check(_mode(source.source_directory, 0o700), f"source_dir_mode:{source.source_id}")

    source_records = {
        item["source_ref"]: item for item in segment.get("sources", [])
    }
    expected_cells: dict[str, list[tuple[int, int]]] = {}
    expected_segments: dict[str, dict[str, list[tuple[int, int]]]] = {}
    for source in plan.sources:
        counts = computed_counts(source.duration_seconds)
        cells = _window_records(
            source.duration_seconds,
            length_seconds=4,
            stride_seconds=4,
            minimum_remaining_seconds=0,
        )
        fine = _window_records(
            source.duration_seconds,
            length_seconds=8,
            stride_seconds=4,
            minimum_remaining_seconds=4,
        )
        context = _window_records(
            source.duration_seconds,
            length_seconds=32,
            stride_seconds=16,
            minimum_remaining_seconds=16,
        )
        expected_cells[source.source_id] = cells
        expected_segments[source.source_id] = {
            "fine": fine,
            "context": context,
        }
        record = source_records.get(source.source_id, {})
        check(
            record.get("counts")
            == {
                "base_cells": counts["base_cells"],
                "fine_windows": counts["fine_windows"],
                "context_windows": counts["context_windows"],
                "windows": counts["temporal_segments"],
            },
            f"source_counts:{source.source_id}",
        )
    observed_cells = {
        source_id: [
            item
            for item in segment.get("base_cells", [])
            if item.get("source_ref") == source_id
        ]
        for source_id in expected_cells
    }
    for source_id, intervals in expected_cells.items():
        records = observed_cells[source_id]
        check(len(records) == len(intervals), f"cell_count:{source_id}")
        for position, ((start, end), record) in enumerate(
            zip(intervals, records)
        ):
            check(record.get("cell_index") == position, f"cell_index:{source_id}:{position}")
            check(record.get("start_us") == start, f"cell_start:{source_id}:{position}")
            check(record.get("end_us") == end, f"cell_end:{source_id}:{position}")
            expected_sample = min(
                start + 2_000_000,
                max(start, round(plan.sources[
                    [item.source_id for item in plan.sources].index(source_id)
                ].duration_seconds * 1_000_000) - 1),
            )
            check(
                record.get("sample_time_us") == expected_sample,
                f"cell_sample:{source_id}:{position}",
            )
    segment_records = segment.get("segments", [])
    for source_id, scales in expected_segments.items():
        for scale, intervals in scales.items():
            records = [
                item
                for item in segment_records
                if item.get("source_ref") == source_id
                and item.get("scale") == scale
            ]
            check(
                len(records) == len(intervals),
                f"segment_count:{source_id}:{scale}",
            )
            for position, ((start, end), record) in enumerate(
                zip(intervals, records)
            ):
                check(
                    record.get("lattice_index") == position,
                    f"segment_index:{source_id}:{scale}:{position}",
                )
                check(
                    record.get("start_us") == start,
                    f"segment_start:{source_id}:{scale}:{position}",
                )
                check(
                    record.get("end_us") == end,
                    f"segment_end:{source_id}:{scale}:{position}",
                )
                expected_binding_count = sum(
                    cell_start < end and cell_end > start
                    for cell_start, cell_end in expected_cells[source_id]
                )
                check(
                    len(record.get("binding_cell_ids", []))
                    == expected_binding_count,
                    f"segment_bindings:{source_id}:{scale}:{position}",
                )

    expected_totals = plan.totals
    check(
        segment.get("totals", {}).get("base_cells")
        == expected_totals["base_cells"],
        "total_cells",
    )
    check(
        segment.get("totals", {}).get("fine_windows")
        == expected_totals["fine_windows"],
        "total_fine",
    )
    check(
        segment.get("totals", {}).get("context_windows")
        == expected_totals["context_windows"],
        "total_context",
    )
    check(
        segment.get("totals", {}).get("windows")
        == expected_totals["temporal_segments"],
        "total_segments",
    )
    expected_observation_counts = {
        "ambient_records": expected_totals["temporal_segments"],
        "ast_fine_calls": expected_totals["fine_windows"],
        "clip_cells": expected_totals["base_cells"],
        "routing_cells": expected_totals["base_cells"],
        "speech_records": expected_totals["whisper_chunks"],
        "vision_records": expected_totals["temporal_segments"],
        "whisper_chunks": expected_totals["whisper_chunks"],
    }
    check(
        observation.get("counts") == expected_observation_counts,
        "observation_counts",
    )
    config = observation.get("config", {})
    check(observation.get("config_hash") == _json_hash(config), "config_hash")
    check(config.get("threads") == 8, "config_threads")
    check(config.get("device") == "cpu", "config_device")
    check(config.get("offline_local_only") is True, "config_offline")
    check(
        config.get("segment_manifest_hash")
        == segment.get("segment_manifest_hash"),
        "config_segment_hash",
    )
    checkpoints = observation.get("checkpoints", [])
    expected_checkpoint_paths = {
        (output / "checkpoints" / source.source_id / name)
        .relative_to(root)
        .as_posix()
        for source in plan.sources
        for name in CHECKPOINTS
    }
    check(
        {item.get("path") for item in checkpoints}
        == expected_checkpoint_paths,
        "checkpoint_inventory",
    )
    source_counts = {
        source.source_id: source.expected_counts for source in plan.sources
    }
    for checkpoint in checkpoints:
        try:
            path = _repo_path(root, checkpoint.get("path"))
        except ValueError as exc:
            failures.append(f"checkpoint_path:{exc}")
            continue
        source_id = path.parent.name
        name = path.name
        check(path.is_file() and _mode(path, 0o600), f"checkpoint_file:{checkpoint.get('path')}")
        check(checkpoint.get("sha256") == _sha256(path, prefixed=True), f"checkpoint_hash:{checkpoint.get('path')}")
        check(checkpoint.get("size_bytes") == path.stat().st_size, f"checkpoint_size:{checkpoint.get('path')}")
        body = _load(path)
        payload = {
            key: value
            for key, value in body.items()
            if key not in {"checkpoint_key", "record_count", "payload_hash"}
        }
        check(body.get("checkpoint_key") == checkpoint.get("key"), f"checkpoint_key:{checkpoint.get('path')}")
        check(body.get("record_count") == checkpoint.get("record_count"), f"checkpoint_count_meta:{checkpoint.get('path')}")
        check(body.get("payload_hash") == checkpoint.get("payload_hash"), f"checkpoint_payload_meta:{checkpoint.get('path')}")
        check(body.get("payload_hash") == _json_hash(payload), f"checkpoint_payload_hash:{checkpoint.get('path')}")
        if name == "speech.json":
            expected_count = source_counts[source_id]["whisper_chunks"]
            records = [*payload.get("chunks", []), *payload.get("records", [])]
            check(len(payload.get("chunks", [])) == expected_count, f"speech_chunks:{source_id}")
            check(len(payload.get("records", [])) == expected_count, f"speech_records:{source_id}")
        elif name == "ambient.json":
            expected_count = source_counts[source_id]["fine_windows"]
            records = payload.get("records", [])
            check(
                len(records) == source_counts[source_id]["temporal_segments"],
                f"ambient_records:{source_id}",
            )
        elif name == "vision_routing.json":
            expected_count = source_counts[source_id]["base_cells"]
            records = payload.get("records", [])
            check(len(records) == expected_count, f"routing_records:{source_id}")
        else:
            expected_count = source_counts[source_id]["base_cells"]
            records = payload.get("segment_records", [])
            check(len(payload.get("cell_vectors", [])) == expected_count, f"clip_cells:{source_id}")
            check(
                len(records) == source_counts[source_id]["temporal_segments"],
                f"clip_records:{source_id}",
            )
        check(body.get("record_count") == expected_count, f"checkpoint_expected_count:{source_id}:{name}")
        check(
            all(
                not isinstance(item, Mapping)
                or item.get("source_ref", source_id) == source_id
                for item in records
            ),
            f"checkpoint_source:{source_id}:{name}",
        )

    modalities = index.get("modalities", {})
    check(
        len(modalities.get("speech", {}).get("documents", []))
        == expected_totals["whisper_chunks"],
        "index_speech_count",
    )
    check(
        len(modalities.get("ambient", {}).get("documents", []))
        == expected_totals["temporal_segments"],
        "index_ambient_count",
    )
    check(
        len(modalities.get("vision", {}).get("documents", []))
        == expected_totals["temporal_segments"],
        "index_vision_count",
    )
    for modality_name, modality in modalities.items():
        for position, document in enumerate(modality.get("documents", [])):
            check(
                document.get("source_ref") in expected_source_hashes,
                f"index_source:{modality_name}:{position}",
            )
            check(
                document.get("source_sha256")
                == expected_source_hashes.get(document.get("source_ref")),
                f"index_source_hash:{modality_name}:{position}",
            )
            check(
                int(document.get("start_us", -1))
                < int(document.get("end_us", -1)),
                f"index_interval:{modality_name}:{position}",
            )
            stack = [(document, None)]
            while stack:
                value, parent = stack.pop()
                if isinstance(value, Mapping):
                    for key, child in value.items():
                        check(
                            parent in {"term_frequency", "document_frequency"}
                            or key not in FORBIDDEN_SEARCH_KEYS,
                            f"forbidden_search_key:{modality_name}:{position}:{key}",
                        )
                        stack.append((child, str(key)))
                elif isinstance(value, list):
                    stack.extend((child, parent) for child in value)

    expected_files = expected_checkpoint_paths | {
        (output / name).relative_to(root).as_posix() for name in TOP_LEVEL
    }
    observed_files = {
        path.relative_to(root).as_posix()
        for path in output.rglob("*")
        if path.is_file()
    }
    check(observed_files == expected_files, "output_file_inventory")
    expected_dirs = {
        output.relative_to(root).as_posix(),
        (output / "checkpoints").relative_to(root).as_posix(),
        *{
            (output / "checkpoints" / source.source_id)
            .relative_to(root)
            .as_posix()
            for source in plan.sources
        },
    }
    observed_dirs = {
        output.relative_to(root).as_posix(),
        *{
            path.relative_to(root).as_posix()
            for path in output.rglob("*")
            if path.is_dir()
        },
    }
    check(observed_dirs == expected_dirs, "output_directory_inventory")
    for path in output.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            check(_mode(path, 0o700), f"dir_mode:{relative}")
        elif path.is_file():
            check(_mode(path, 0o600), f"file_mode:{relative}")
            check(path.suffix.casefold() not in MEDIA_SUFFIXES, f"media_derivative:{relative}")
            check(
                not any(term in path.name.casefold() for term in PROHIBITED_NAME_TERMS),
                f"prohibited_artifact:{relative}",
            )
    for document in documents.values():
        for key, value in _walk(document):
            if isinstance(value, str):
                check(
                    not (
                        value.startswith(("/", "file://"))
                        or "/jizhicfs/" in value
                        or "/.staging/" in value
                    ),
                    f"path_leak:{key}",
                )
    derived_bytes = sum(
        path.stat().st_size
        for path in output.rglob("*")
        if path.is_file() and path.name != "build_manifest.json"
    )
    check(
        build.get("derived_artifact_bytes_before_build_manifest")
        == derived_bytes,
        "derived_bytes",
    )
    hard_cap = int(build.get("derived_artifact_hard_cap_mib", 0))
    check(
        hard_cap > 0 and derived_bytes <= hard_cap * 1024 * 1024,
        "hard_cap",
    )
    resume = None
    if before_snapshot is not None:
        before = _load(Path(before_snapshot))
        after_files = _file_snapshot(output)
        before_files = before.get("files", {})
        checkpoint_mtimes = before.get("checkpoint_mtimes_ns", {})
        inventory_equal = set(before_files) == set(after_files)
        hashes_equal = inventory_equal and all(
            after_files[name]["sha256"] == record["sha256"]
            and after_files[name]["size_bytes"] == record["size_bytes"]
            for name, record in before_files.items()
        )
        mtimes_equal = all(
            name in after_files and after_files[name]["mtime_ns"] == mtime
            for name, mtime in checkpoint_mtimes.items()
        )
        check(inventory_equal, "resume_inventory")
        check(hashes_equal, "resume_hashes")
        check(mtimes_equal, "resume_checkpoint_mtimes")
        lines = [
            f"{name} {after_files[name]['sha256']}"
            for name in sorted(after_files)
        ]
        resume = {
            "before_file_count": len(before_files),
            "after_file_count": len(after_files),
            "checkpoint_count": len(checkpoint_mtimes),
            "file_inventory_equal": inventory_equal,
            "all_file_hashes_and_sizes_equal": hashes_equal,
            "all_checkpoint_mtimes_equal": mtimes_equal,
            "sorted_file_hash_list_sha256": hashlib.sha256(
                ("\n".join(lines) + "\n").encode()
            ).hexdigest(),
        }
    return {
        "verified": not failures,
        "decision": (
            "CAPTAINCOOK4D_WAVE0_FULL_TIMELINE_READY"
            if not failures
            else "CAPTAINCOOK4D_WAVE0_FULL_TIMELINE_NO_GO"
        ),
        "check_count": checks,
        "failure_count": len(failures),
        "failures": failures,
        "output_root": output.relative_to(root).as_posix(),
        "resume": resume,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--plan", default=str(PLAN_RELATIVE_PATH))
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--before-snapshot", default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = audit_index(
        args.repo_root,
        plan_path=args.plan,
        output_root=args.output_root,
        before_snapshot=args.before_snapshot,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
