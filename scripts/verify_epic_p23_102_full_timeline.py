#!/usr/bin/env python3
"""Independently verify an EPIC P23_102 full-timeline index."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np

PIPELINE_TOKEN = "EPIC_P23_102_FULL_TIMELINE_PIPELINE_READY"
SCHEMA_VERSION = "av-trace.epic-p23-102-full-timeline/1.0"
INDEX_VERSION = "epic-p23-102-full-timeline-index/1.0"
PLAN_RELATIVE_PATH = Path(
    "data/rehearsal_plan/epic_p23_102_full_timeline_index_v1.json"
)
TOP_LEVEL_ARTIFACTS = (
    "segment_manifest.json",
    "observation_manifest.json",
    "full_timeline_index.json",
    "resource_manifest.json",
    "checkpoint_manifest.json",
    "build_manifest.json",
)
EXPECTED_LAYERS = {
    "source_probe",
    "speech_asr",
    "siglip2_visual",
    "clap_audio",
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
FORBIDDEN_CLAIM_KEYS = {
    "human_gold",
    "human_decision",
    "ses_label",
    "h_tier",
    "gate_a_go",
    "necessity_label",
}
TOKEN_RE = re.compile(r"[a-z0-9]+")


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode()


def _json_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(16 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _self_hash(document: Mapping[str, Any], key: str) -> bool:
    copied = dict(document)
    stored = copied.pop(key, None)
    return stored == _json_hash(copied)


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _safe(root: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"INVALID_REPO_PATH:{value!r}")
    candidate = Path(value)
    if candidate.is_absolute():
        candidate.resolve(strict=False).relative_to(root)
        if ".staging" in candidate.parts:
            raise ValueError(f"INVALID_REPO_PATH:{value}")
        return candidate
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts or ".staging" in pure.parts:
        raise ValueError(f"INVALID_REPO_PATH:{value}")
    path = root.joinpath(*pure.parts)
    path.resolve(strict=False).relative_to(root)
    return path


def _windows(
    duration_us: int,
    length_us: int,
    stride_us: int,
    minimum_remaining_us: int,
) -> list[tuple[int, int]]:
    output = []
    start = 0
    while duration_us - start >= minimum_remaining_us:
        output.append((start, min(start + length_us, duration_us)))
        start += stride_us
    return output


def _counts(duration_us: int) -> dict[str, int]:
    base = len(_windows(duration_us, 4_000_000, 4_000_000, 1))
    fine = len(_windows(duration_us, 8_000_000, 4_000_000, 4_000_000))
    context = len(
        _windows(duration_us, 32_000_000, 16_000_000, 16_000_000)
    )
    speech = len(_windows(duration_us, 30_000_000, 30_000_000, 1))
    return {
        "base_cells": base,
        "fine_windows": fine,
        "context_windows": context,
        "temporal_segments": fine + context,
        "speech_chunks": speech,
        "checkpoints": 4,
    }


def _walk(value: Any):
    if isinstance(value, Mapping):
        for key, child in value.items():
            yield str(key), child
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _vector_ok(record: Mapping[str, Any]) -> bool:
    try:
        dimension = int(record["dimension"])
        vector = np.frombuffer(
            bytes.fromhex(record["vector_f16_hex"]), dtype="<f2"
        ).astype(np.float32)
    except (KeyError, TypeError, ValueError):
        return False
    norm = float(np.linalg.norm(vector))
    return (
        len(vector) == dimension
        and np.isfinite(vector).all()
        and abs(norm - 1.0) <= 0.01
    )


def verify_index(
    repo_root: str | Path,
    *,
    plan_path: str | Path = PLAN_RELATIVE_PATH,
    output_root: str | Path | None = None,
    smoke_seconds: float | None = None,
    rehash_source: bool = True,
    allow_synthetic_fixture: bool = False,
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
        plan_file = _safe(root, str(plan_path))
        plan = _load(plan_file)
        if plan.get("synthetic_fixture") is True and not allow_synthetic_fixture:
            raise ValueError("SYNTHETIC_FIXTURE_NOT_AUTHORIZED")
        source = plan["source"]
        output = _safe(
            root,
            str(
                output_root
                or (
                    plan["scope"]["smoke_output_root"]
                    if smoke_seconds is not None
                    else plan["scope"]["output_root"]
                )
            ),
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return {
            "verified": False,
            "decision": PIPELINE_TOKEN,
            "check_count": 1,
            "failures": [f"plan_or_path:{exc}"],
        }
    check(output.is_dir() and not output.is_symlink(), "output_root_missing")
    check(output.is_dir() and _mode(output) == 0o700, "output_root_mode")
    documents = {}
    for name in TOP_LEVEL_ARTIFACTS:
        path = output / name
        check(path.is_file() and not path.is_symlink(), f"artifact_missing:{name}")
        if path.is_file():
            check(_mode(path) == 0o600, f"artifact_mode:{name}")
            try:
                documents[name] = _load(path)
            except (OSError, json.JSONDecodeError) as exc:
                failures.append(f"artifact_json:{name}:{exc}")
    if len(documents) != len(TOP_LEVEL_ARTIFACTS):
        return {
            "verified": False,
            "decision": PIPELINE_TOKEN,
            "check_count": checks,
            "failures": failures,
        }
    segment = documents["segment_manifest.json"]
    observation = documents["observation_manifest.json"]
    index = documents["full_timeline_index.json"]
    resource = documents["resource_manifest.json"]
    checkpoint_manifest = documents["checkpoint_manifest.json"]
    build = documents["build_manifest.json"]
    for document, key in (
        (segment, "segment_manifest_hash"),
        (observation, "observation_manifest_hash"),
        (index, "index_hash"),
        (resource, "resource_manifest_hash"),
        (checkpoint_manifest, "checkpoint_manifest_hash"),
        (build, "build_manifest_hash"),
    ):
        check(_self_hash(document, key), f"self_hash:{key}")
        check(document.get("schema_version") == SCHEMA_VERSION, f"schema:{key}")
    check(index.get("index_version") == INDEX_VERSION, "index_version")
    check(build.get("index_version") == INDEX_VERSION, "build_index_version")
    check(build.get("decision") == PIPELINE_TOKEN, "build_decision")
    check(build.get("status") == "COMPLETE", "build_status")
    check(segment.get("source_ref") == "P23_102", "source_ref")

    duration_us = int(segment.get("duration_us", -1))
    expected_duration = round(
        min(
            float(source["official_duration_seconds"]),
            (
                float(smoke_seconds)
                if smoke_seconds is not None
                else float(source["official_duration_seconds"])
            ),
        )
        * 1_000_000
    )
    check(duration_us == expected_duration, "duration_us")
    frozen_counts = _counts(duration_us)
    check(segment.get("counts") == frozen_counts, "timeline_counts")
    check(
        len(segment.get("base_cells", [])) == frozen_counts["base_cells"],
        "base_cell_count",
    )
    check(
        len(segment.get("segments", []))
        == frozen_counts["temporal_segments"],
        "segment_count",
    )
    check(
        len(segment.get("speech_chunks", []))
        == frozen_counts["speech_chunks"],
        "speech_chunk_count",
    )
    expected_base = _windows(duration_us, 4_000_000, 4_000_000, 1)
    for item, interval in zip(segment["base_cells"], expected_base):
        check(
            (item["start_us"], item["end_us"]) == interval,
            f"base_interval:{item['cell_id']}",
        )
        check(
            item["sample_time_us"]
            == min(item["start_us"] + 2_000_000, duration_us - 1),
            f"base_sample:{item['cell_id']}",
        )
    cell_ids = {item["cell_id"] for item in segment["base_cells"]}
    for item in segment["segments"]:
        check(
            bool(item["binding_cell_ids"])
            and set(item["binding_cell_ids"]) <= cell_ids,
            f"segment_binding:{item['segment_id']}",
        )

    check(
        observation.get("segment_manifest_hash")
        == segment["segment_manifest_hash"],
        "observation_segment_binding",
    )
    check(
        index.get("segment_manifest_hash") == segment["segment_manifest_hash"],
        "index_segment_binding",
    )
    check(
        index.get("observation_manifest_hash")
        == observation["observation_manifest_hash"],
        "index_observation_binding",
    )
    check(
        checkpoint_manifest.get("config_hash")
        == observation.get("config_hash"),
        "checkpoint_config_binding",
    )
    checkpoints = checkpoint_manifest.get("checkpoints", [])
    check(len(checkpoints) == 4, "checkpoint_count")
    check(
        {item.get("layer") for item in checkpoints} == EXPECTED_LAYERS,
        "checkpoint_layers",
    )
    checkpoint_payloads = {}
    for item in checkpoints:
        try:
            path = _safe(root, item["path"])
            document = _load(path)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            failures.append(f"checkpoint_open:{item.get('layer')}:{exc}")
            continue
        check(path.is_file() and not path.is_symlink(), f"checkpoint_file:{path}")
        check(_mode(path) == 0o600, f"checkpoint_mode:{path}")
        check(path.stat().st_size == item["size_bytes"], f"checkpoint_size:{path}")
        check(
            "sha256:" + _sha256(path) == item["sha256"],
            f"checkpoint_hash:{path}",
        )
        check(
            document.get("checkpoint_key") == item["checkpoint_key"],
            f"checkpoint_key:{path}",
        )
        check(
            document.get("payload_hash") == item["payload_hash"],
            f"checkpoint_meta_payload_hash:{path}",
        )
        check(
            document.get("payload_hash") == _json_hash(document.get("payload")),
            f"checkpoint_payload_hash:{path}",
        )
        check(
            document.get("record_count") == item["record_count"],
            f"checkpoint_record_count:{path}",
        )
        checkpoint_payloads[item["layer"]] = document.get("payload", {})
    if set(checkpoint_payloads) == EXPECTED_LAYERS:
        speech = checkpoint_payloads["speech_asr"]["chunks"]
        vision = checkpoint_payloads["siglip2_visual"]
        clap = checkpoint_payloads["clap_audio"]["segment_vectors"]
        check(len(speech) == frozen_counts["speech_chunks"], "speech_payload_count")
        check(
            len(vision["cell_vectors"]) == frozen_counts["base_cells"],
            "vision_cell_count",
        )
        check(
            len(vision["segment_vectors"])
            == frozen_counts["temporal_segments"],
            "vision_segment_count",
        )
        check(len(clap) == frozen_counts["temporal_segments"], "clap_count")
        expected_checkpoint_counts = {
            "source_probe": 1,
            "speech_asr": frozen_counts["speech_chunks"],
            "siglip2_visual": (
                frozen_counts["base_cells"]
                + frozen_counts["temporal_segments"]
            ),
            "clap_audio": frozen_counts["temporal_segments"],
        }
        for item in checkpoints:
            check(
                item["record_count"]
                == expected_checkpoint_counts[item["layer"]],
                f"checkpoint_expected_count:{item['layer']}",
            )
        for record in vision["cell_vectors"] + vision["segment_vectors"] + clap:
            check(_vector_ok(record), f"vector:{record.get('segment_id') or record.get('cell_id')}")

    modalities = index.get("modalities", {})
    check(set(modalities) == {"speech", "siglip2_visual", "clap_audio"}, "modalities")
    check(
        len(modalities["siglip2_visual"]["documents"])
        == frozen_counts["temporal_segments"],
        "index_vision_count",
    )
    check(
        len(modalities["clap_audio"]["documents"])
        == frozen_counts["temporal_segments"],
        "index_clap_count",
    )
    speech_docs = modalities["speech"]["documents"]
    frequencies: Counter[str] = Counter()
    for record in speech_docs:
        tokens = TOKEN_RE.findall(str(record.get("text", "")).casefold())
        expected_tf = dict(sorted(Counter(tokens).items()))
        check(record.get("term_frequency") == expected_tf, "speech_tf")
        frequencies.update(expected_tf.keys())
        check(
            record.get("searchable")
            == (record.get("routing") == "bm25_searchable"),
            "speech_routing",
        )
    check(
        modalities["speech"].get("document_frequency")
        == dict(sorted(frequencies.items())),
        "speech_document_frequency",
    )

    for key, _ in _walk(index):
        check(key not in FORBIDDEN_CLAIM_KEYS, f"forbidden_claim_key:{key}")
    for document_name, document in documents.items():
        governance = document.get("governance")
        if governance is not None:
            check(governance.get("license_spdx") == "CC-BY-NC-4.0", f"license:{document_name}")
            check(governance.get("development_only") is True, f"development:{document_name}")
            check(governance.get("future_test_eligible") is False, f"future_test:{document_name}")
            check(governance.get("human_review_performed") is False, f"human:{document_name}")
            check(governance.get("ses_assigned") is False, f"ses:{document_name}")
            check(governance.get("h_tier_assigned") is False, f"h_tier:{document_name}")
            check(governance.get("gate_a_claimed") is False, f"gate_a:{document_name}")
            check(
                governance.get(
                    "semantic_annotations_used_during_source_selection"
                )
                is False,
                f"semantic_selection:{document_name}",
            )
    terminal = build.get("terminal_boundary", {})
    check(terminal.get("index_only") is True, "terminal_index_only")
    check(
        all(value is False for key, value in terminal.items() if key != "index_only"),
        "terminal_nonclaims",
    )

    for artifact in build.get("artifact_hashes", []):
        try:
            path = _safe(root, artifact["path"])
        except (ValueError, KeyError) as exc:
            failures.append(f"build_artifact_path:{exc}")
            continue
        check(path.stat().st_size == artifact["size_bytes"], f"artifact_size:{path}")
        check(
            "sha256:" + _sha256(path) == artifact["sha256"],
            f"artifact_hash:{path}",
        )
    persisted_media = [
        path.relative_to(output).as_posix()
        for path in output.rglob("*")
        if path.is_file() and path.suffix.casefold() in MEDIA_SUFFIXES
    ]
    check(not persisted_media, "persisted_media_derivative")
    derived = sum(
        path.stat().st_size
        for path in output.rglob("*")
        if path.is_file() and path.name != "build_manifest.json"
    )
    check(
        derived == build.get("derived_artifact_bytes_before_build_manifest"),
        "derived_bytes",
    )
    check(
        derived <= int(plan["storage"]["hard_cap_mib"]) * 1024 * 1024,
        "derived_hard_cap",
    )

    try:
        acquisition = _load(_safe(root, source["acquisition_manifest_path"]))
        media = acquisition["media"]
        media_path = _safe(root, media["path"])
        check(acquisition.get("status") == "COMPLETE_VERIFIED_READY", "acquisition_status")
        check(
            acquisition.get("source", {}).get("asset_id") == "P23_102",
            "acquisition_asset_id",
        )
        check(
            acquisition.get("source", {}).get("license") == "CC-BY-NC-4.0",
            "acquisition_license",
        )
        check(
            media["path"] == source["expected_final_media_path"],
            "acquisition_media_path",
        )
        check(
            media["bytes"] == source["official_content_length_bytes"],
            "acquisition_official_bytes",
        )
        check(media["md5"] == source["official_md5"], "acquisition_official_md5")
        technical = acquisition.get("technical_validation", {})
        video = technical.get("video", {})
        audio = technical.get("audio", {})
        required = source["native_stream_requirements"]
        check(technical.get("ffprobe_passed") is True, "acquisition_ffprobe")
        check(video.get("codec_name") == required["video_codec_name"], "video_codec")
        check(video.get("codec_tag_string") == required["video_codec_tag"], "video_tag")
        check(video.get("width") == required["video_width"], "video_width")
        check(video.get("height") == required["video_height"], "video_height")
        check(audio.get("codec_name") == required["audio_codec_name"], "audio_codec")
        check(audio.get("codec_tag_string") == required["audio_codec_tag"], "audio_tag")
        check(
            audio.get("sample_rate_hz") == required["audio_sample_rate_hz"],
            "audio_rate",
        )
        check(audio.get("channels") == required["audio_channels"], "audio_channels")
        check(audio.get("channel_layout") == required["audio_layout"], "audio_layout")
        check(media_path.is_file() and not media_path.is_symlink(), "source_media")
        check(media_path.stat().st_size == media["bytes"], "source_bytes")
        check(segment.get("source_sha256") == media["sha256"], "source_binding")
        if rehash_source:
            check(_sha256(media_path) == media["sha256"], "source_rehash")
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        failures.append(f"source_manifest:{exc}")

    return {
        "verified": not failures,
        "decision": PIPELINE_TOKEN,
        "check_count": checks,
        "failures": failures,
        "output_root": output.relative_to(root).as_posix(),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root", default=str(Path(__file__).resolve().parents[1])
    )
    parser.add_argument("--plan", default=str(PLAN_RELATIVE_PATH))
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--mode", choices=("smoke", "full"), default="full")
    parser.add_argument("--smoke-seconds", type=float, default=32.0)
    parser.add_argument(
        "--rehash-source",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = verify_index(
        args.repo_root,
        plan_path=args.plan,
        output_root=args.output_root,
        smoke_seconds=args.smoke_seconds if args.mode == "smoke" else None,
        rehash_source=args.rehash_source,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["verified"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
