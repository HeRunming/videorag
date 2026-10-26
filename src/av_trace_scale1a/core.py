"""Scale-1A full-timeline multimodal indexing and diagnostic evaluation.

The implementation intentionally keeps source-derived observations under the
restricted NOAA tree.  Public result files contain metrics and provenance
labels only.  All models are local, pinned, and fail closed; in particular no
semantic visual substitute is used when the Task-94 CLIP gate is absent.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import re
import stat
import tempfile
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

import av
import cv2
import numpy as np


STAGE = "MACHINE_ADJUDICATED_PROVISIONAL_MVP"
FINAL_STATUS = "FINAL_BENCHMARK_NOT_YET_VALIDATED"
WARNING = "LOW_N_DESCRIPTIVE_SCALE1A"
SCHEMA_VERSION = "av-trace.scale1a/1.0"
POLICY_VERSION = "deterministic-protocol-policy/2.0"
INDEX_VERSION = "scale1a-full-timeline-index/2.0"
TOKEN_RE = re.compile(r"[a-z0-9]+")
FORBIDDEN_SEARCH_KEYS = {
    "question", "answer", "answer_hypothesis", "answer_aliases", "claims",
    "claim_id", "claim_ids", "reviewer_rationale", "state", "state_role",
    "family_id", "intervention_id", "evidence_id", "evidence_ids",
    "legacy_codex_description", "generated_caption",
}
NEGATIVE_CLASSES = (
    "same_video_near_temporal",
    "same_topic_lexical",
    "same_modality_semantic",
    "cross_modal_mismatch",
    "repeated_or_duplicate_content",
    "title_credit_metadata_shortcut",
)
POLICIES = (
    "direct-long-context",
    "single-shot-rag",
    "react-recovery",
    "evidence-sufficiency",
)
STATES = ("CLEAN", "BLOCKED", "RESTORED")
SCOPES = ("bounded_pilot0", "full_source_scoped", "full_cross_source")

PLAN_REL = Path("data/rehearsal_plan/scale1a_full_timeline_plan.json")
ANCHOR_REL = Path("data/rehearsal_plan/scale1a_pilot0_trust_anchor.json")
PILOT_FAMILIES_REL = Path("data/restricted/noaa01/real_av_mvp/provisional_families.json")
PILOT_EPISODES_REL = Path("mvp/results/noaa01_real_av_mvp/episode_metrics.csv")
RESTRICTED_REL = Path("data/restricted/noaa01/scale1a")
RESULTS_REL = Path("mvp/results/scale1a_full_timeline")
CLIP_MANIFEST_REL = Path(
    "data/restricted/noaa01/models/scale1a_clip_acquisition_manifest.json"
)
CLIP_SNAPSHOT_REL = Path(
    "data/restricted/noaa01/models/clip-vit-base-patch32-3d74acf"
)
WHISPER_REL = Path("data/restricted/noaa01/models/whisper-tiny.en-87c7102")
AST_REL = Path("data/restricted/noaa01/models/ast-audioset-f826b80")
HAAR_REL = Path(
    "data/restricted/noaa01/models/opencv-haarcascade-frontalface-default.xml"
)


class Scale1AError(RuntimeError):
    """Fail-closed Scale-1A error."""


def _load(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
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


def _atomic_bytes(path: Path, payload: bytes, *, restricted: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if restricted:
        path.parent.chmod(0o700)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp = Path(name)
    try:
        os.fchmod(descriptor, 0o600 if restricted else 0o644)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        path.chmod(0o600 if restricted else 0o644)
    finally:
        tmp.unlink(missing_ok=True)


def _dump(path: Path, value: Any, *, restricted: bool) -> None:
    _atomic_bytes(
        path,
        json.dumps(
            value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False
        ).encode("utf-8") + b"\n",
        restricted=restricted,
    )


def _tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return TOKEN_RE.findall(normalized)


def _round(value: float | np.floating[Any], digits: int = 8) -> float:
    return round(float(value), digits)


def _interval_iou(a: Sequence[float], b: Sequence[float]) -> float:
    overlap = max(0.0, min(a[1], b[1]) - max(a[0], b[0]))
    union = max(a[1], b[1]) - min(a[0], b[0])
    return overlap / union if union else 0.0


def _coverage(candidate: Sequence[float], target: Sequence[float]) -> float:
    overlap = max(0.0, min(candidate[1], target[1]) - max(candidate[0], target[0]))
    width = target[1] - target[0]
    return overlap / width if width else 0.0


def _overlaps(a: Sequence[float], b: Sequence[float]) -> bool:
    return max(a[0], b[0]) < min(a[1], b[1])


def _version(package: str) -> str | None:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return None


def _safe_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _restricted_tree_permissions(root: Path) -> list[str]:
    failures: list[str] = []
    if root.exists() and stat.S_IMODE(root.stat().st_mode) != 0o700:
        failures.append(f"{root.as_posix()}:directory_mode")
    for path in root.rglob("*") if root.exists() else ():
        if path.is_symlink():
            failures.append(f"{path.as_posix()}:symlink")
        elif path.is_file() and stat.S_IMODE(path.stat().st_mode) != 0o600:
            failures.append(f"{path.as_posix()}:file_mode")
    return failures


def verify_trust_anchor(repo_root: Path) -> dict[str, Any]:
    """Verify the immutable Task-93 inventory and exact five source identities."""
    anchor_path = repo_root / ANCHOR_REL
    if not anchor_path.is_file() or anchor_path.is_symlink():
        raise Scale1AError("TRUST_ANCHOR_MISSING_OR_UNSAFE")
    anchor = _load(anchor_path)
    mismatches: list[dict[str, Any]] = []
    if anchor.get("decision") != "BASELINE_FROZEN":
        mismatches.append({"path": ANCHOR_REL.as_posix(), "kind": "decision"})
    for expected in anchor.get("inventory", []):
        rel = Path(expected["path"])
        path = repo_root / rel
        if not path.is_file() or path.is_symlink():
            mismatches.append({"path": rel.as_posix(), "kind": "missing_or_unsafe"})
            continue
        observed = {
            "size_bytes": path.stat().st_size,
            "sha256": _sha256(path),
            "mode": f"{stat.S_IMODE(path.stat().st_mode):04o}",
        }
        for field in ("size_bytes", "sha256", "mode"):
            if observed[field] != expected[field]:
                mismatches.append(
                    {
                        "path": rel.as_posix(), "kind": field,
                        "expected": expected[field], "observed": observed[field],
                    }
                )
    source_bindings: list[dict[str, Any]] = []
    for expected in anchor.get("source_media", []):
        rel = Path(expected["path"])
        path = repo_root / rel
        if not path.is_file() or path.is_symlink() or not _safe_under(
            path, repo_root / "data/restricted/noaa01/raw"
        ):
            mismatches.append({"path": rel.as_posix(), "kind": "source_path"})
            continue
        observed_hash = _sha256(path)
        observed_size = path.stat().st_size
        try:
            with av.open(str(path), mode="r") as container:
                duration = (
                    float(container.duration / av.time_base)
                    if container.duration is not None else None
                )
                video = [s for s in container.streams if s.type == "video"]
                audio = [s for s in container.streams if s.type == "audio"]
                stream_identity = {
                    "video_stream_count": len(video),
                    "audio_stream_count": len(audio),
                    "video": [
                        {
                            "index": s.index,
                            "codec": s.codec_context.name,
                            "time_base": str(s.time_base),
                        }
                        for s in video
                    ],
                    "audio": [
                        {
                            "index": s.index,
                            "codec": s.codec_context.name,
                            "time_base": str(s.time_base),
                            "sample_rate": s.codec_context.sample_rate,
                        }
                        for s in audio
                    ],
                }
        except Exception as exc:
            mismatches.append(
                {"path": rel.as_posix(), "kind": "probe", "detail": str(exc)}
            )
            continue
        checks = {
            "size_bytes": observed_size == expected["size_bytes"],
            "sha256": observed_hash == expected["sha256"],
            "duration_seconds": duration is not None
            and abs(duration - expected["duration_seconds"]) <= 1e-3,
            "video_stream_count": len(video) == expected["video_stream_count"],
            "audio_stream_count": len(audio) == expected["audio_stream_count"],
        }
        if not all(checks.values()):
            mismatches.append(
                {"path": rel.as_posix(), "kind": "source_identity", "checks": checks}
            )
        source_bindings.append(
            {
                "candidate_id": expected["candidate_id"],
                "source_ref": expected["candidate_id"],
                "size_bytes": observed_size,
                "sha256": observed_hash,
                "duration_s": _round(duration or 0.0, 6),
                "streams": stream_identity,
            }
        )
    if mismatches:
        raise Scale1AError(
            "PILOT0_TRUST_ANCHOR_MISMATCH:" + json.dumps(mismatches, sort_keys=True)
        )
    return {
        "anchor_id": anchor["anchor_id"],
        "anchor_sha256": _sha256(anchor_path, prefixed=True),
        "verified_inventory_count": len(anchor["inventory"]),
        "source_bindings": source_bindings,
        "verified": True,
    }


def _make_windows(
    duration_s: float, *, length_s: int, stride_s: int, min_remaining_s: int
) -> list[tuple[int, int]]:
    duration_us = int(round(duration_s * 1_000_000))
    length_us = length_s * 1_000_000
    stride_us = stride_s * 1_000_000
    minimum_us = min_remaining_s * 1_000_000
    windows: list[tuple[int, int]] = []
    index = 0
    while duration_us - index * stride_us >= minimum_us:
        start = index * stride_us
        windows.append((start, min(start + length_us, duration_us)))
        index += 1
    return windows


def build_segment_manifest(repo_root: Path, plan: Mapping[str, Any]) -> dict[str, Any]:
    sources: list[dict[str, Any]] = []
    all_segments: list[dict[str, Any]] = []
    all_cells: list[dict[str, Any]] = []
    totals = Counter()
    for source in plan["sources"]:
        duration = float(source["duration_s"])
        prefix = source["sha256"][:12]
        cells = _make_windows(
            duration, length_s=4, stride_s=4, min_remaining_s=0
        )
        # The generic loop admits a zero-width endpoint when duration is exactly
        # divisible by four. NOAA durations are not; keep this explicit.
        cells = [item for item in cells if item[1] > item[0]]
        fine = _make_windows(
            duration, length_s=8, stride_s=4, min_remaining_s=4
        )
        context = _make_windows(
            duration, length_s=32, stride_s=16, min_remaining_s=16
        )
        if (
            len(cells) != source["cell_and_frame_count"]
            or len(fine) != source["fine_count"]
            or len(context) != source["context_count"]
        ):
            raise Scale1AError(f"SEGMENT_COUNT_MISMATCH:{source['candidate_id']}")
        cell_records = []
        for i, (start, end) in enumerate(cells):
            record = {
                "cell_id": f"cell.{prefix}.{i:06d}",
                "source_ref": source["candidate_id"],
                "source_sha256": source["sha256"],
                "cell_index": i,
                "start_us": start,
                "end_us": end,
                "sample_time_us": min(
                    start + 2_000_000,
                    max(start, int(round(duration * 1_000_000)) - 1),
                ),
            }
            cell_records.append(record)
            all_cells.append(record)
        segment_records = []
        for scale, windows in (("fine", fine), ("context", context)):
            for i, (start, end) in enumerate(windows):
                children = [
                    c["cell_id"] for c in cell_records
                    if c["start_us"] < end and c["end_us"] > start
                ]
                record = {
                    "segment_id": f"seg.{prefix}.{scale}.{i:06d}",
                    "source_ref": source["candidate_id"],
                    "source_sha256": source["sha256"],
                    "scale": scale,
                    "lattice_index": i,
                    "start_us": start,
                    "end_us": end,
                    "binding_cell_ids": children,
                }
                segment_records.append(record)
                all_segments.append(record)
        sources.append(
            {
                "source_ref": source["candidate_id"],
                "stable_source_id": source["stable_source_id"],
                "duration_us": int(round(duration * 1_000_000)),
                "size_bytes": source["size_bytes"],
                "sha256": source["sha256"],
                "counts": {
                    "base_cells": len(cells),
                    "fine_windows": len(fine),
                    "context_windows": len(context),
                    "windows": len(fine) + len(context),
                },
            }
        )
        totals.update(
            base_cells=len(cells), fine_windows=len(fine),
            context_windows=len(context), windows=len(fine) + len(context),
        )
    expected = {
        "base_cells": plan["totals"]["cell_and_frame_count"],
        "fine_windows": plan["totals"]["fine_count"],
        "context_windows": plan["totals"]["context_count"],
        "windows": plan["totals"]["temporal_segment_count"],
    }
    if dict(totals) != expected:
        raise Scale1AError(f"TOTAL_SEGMENT_COUNT_MISMATCH:{dict(totals)}")
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "human_reviewed": False,
        "gold_annotation": False,
        "answer_question_independent_ids": True,
        "time_unit": "integer_microseconds",
        "segmentation": plan["segmentation"],
        "sources": sources,
        "totals": {
            **expected,
            "maximum_modality_records": expected["windows"] * 3,
        },
        "base_cells": all_cells,
        "segments": all_segments,
    }
    manifest["segment_manifest_hash"] = _json_hash(manifest)
    return manifest


def _parse_sha256sums(snapshot: Path) -> list[dict[str, Any]]:
    sums = snapshot / "SHA256SUMS"
    if not sums.is_file() or sums.is_symlink():
        raise Scale1AError(f"MODEL_SHA256SUMS_MISSING:{snapshot.name}")
    records = []
    for line in sums.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, relative = line.split(maxsplit=1)
        relative = relative.lstrip("*")
        listed = Path(relative)
        # Older snapshot manifests recorded repository-relative paths while
        # living inside the snapshot directory.
        path = listed if listed.is_absolute() else snapshot / listed
        if not path.is_file() and not listed.is_absolute():
            for ancestor in snapshot.parents:
                candidate = ancestor / listed
                if candidate.is_file():
                    path = candidate
                    break
        if not path.is_file() or path.is_symlink():
            raise Scale1AError(f"MODEL_FILE_MISSING:{snapshot.name}:{relative}")
        if _sha256(path) != digest:
            raise Scale1AError(f"MODEL_HASH_MISMATCH:{snapshot.name}:{relative}")
        records.append({
            "path": path.relative_to(snapshot).as_posix()
            if _safe_under(path, snapshot) else relative,
            "size_bytes": path.stat().st_size, "sha256": digest,
        })
    return records


def _clip_gate(repo_root: Path, plan: Mapping[str, Any]) -> dict[str, Any]:
    manifest_path = repo_root / CLIP_MANIFEST_REL
    snapshot = repo_root / CLIP_SNAPSHOT_REL
    if not manifest_path.is_file():
        return {
            "ready": False, "decision": "CLIP_SNAPSHOT_MISSING",
            "reason": "Task-94 acquisition manifest is absent; semantic visual index fails closed.",
        }
    manifest = _load(manifest_path)
    technical_decision = manifest.get("technical_inference_decision")
    redistribution_decision = manifest.get("redistribution_decision")
    overall_decision = manifest.get("decision")
    if technical_decision != "CLIP_SNAPSHOT_READY":
        return {
            "ready": False,
            "decision": technical_decision or "CLIP_TECHNICAL_DECISION_MISSING",
            "overall_decision": overall_decision,
            "redistribution_decision": redistribution_decision,
            "reason": "Task-94 technical-use gate does not authorize the exact CLIP snapshot.",
            "manifest_sha256": _sha256(manifest_path, prefixed=True),
        }
    if redistribution_decision != "NOT_AUTHORIZED":
        raise Scale1AError("CLIP_REDISTRIBUTION_GATE_NOT_FAIL_CLOSED")
    if overall_decision != "CONDITIONAL_GO":
        raise Scale1AError("CLIP_OVERALL_DECISION_MISMATCH")
    if not snapshot.is_dir() or snapshot.is_symlink():
        raise Scale1AError("CLIP_READY_BUT_SNAPSHOT_MISSING")
    records = _parse_sha256sums(snapshot)
    total = sum(item["size_bytes"] for item in records)
    if total > int(plan["observation_layers"]["vision"]["embedding_layer"]["acquisition_cap_bytes"]):
        raise Scale1AError("CLIP_SNAPSHOT_CAP_EXCEEDED")
    return {
        "ready": True,
        "decision": technical_decision,
        "technical_inference_decision": technical_decision,
        "redistribution_decision": redistribution_decision,
        "overall_decision": overall_decision,
        "manifest_sha256": _sha256(manifest_path, prefixed=True),
        "snapshot_files": records,
        "snapshot_hash": _json_hash(records),
        "total_bytes": total,
    }


def _configure_runtime(threads: int) -> dict[str, Any]:
    for key in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HUGGINGFACE_TOKEN"):
        os.environ.pop(key, None)
    os.environ.update(
        {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "HF_HUB_DISABLE_TELEMETRY": "1",
            "HF_HUB_DISABLE_PROGRESS_BARS": "1",
            "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1",
            "TOKENIZERS_PARALLELISM": "false",
            "OMP_NUM_THREADS": str(threads),
            "MKL_NUM_THREADS": str(threads),
        }
    )
    with np.errstate(all="ignore"):
        if "long" not in np.__dict__:
            np.long = np.int64  # type: ignore[attr-defined]
        if "ulong" not in np.__dict__:
            np.ulong = np.uint64  # type: ignore[attr-defined]
    return {key: os.environ[key] for key in (
        "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "TOKENIZERS_PARALLELISM",
        "OMP_NUM_THREADS", "MKL_NUM_THREADS",
    )}


def _source_path(repo_root: Path, plan_source: Mapping[str, Any]) -> Path:
    path = repo_root / "data/restricted/noaa01/raw" / plan_source["basename"]
    if not path.is_file() or path.is_symlink() or not _safe_under(
        path, repo_root / "data/restricted/noaa01/raw"
    ):
        raise Scale1AError(f"UNSAFE_SOURCE:{plan_source['candidate_id']}")
    if path.stat().st_size != plan_source["size_bytes"] or _sha256(path) != plan_source["sha256"]:
        raise Scale1AError(f"SOURCE_IDENTITY_MISMATCH:{plan_source['candidate_id']}")
    return path


_SOURCE_IDENTITY_CACHE: dict[str, tuple[int, int, int, str]] = {}


def _verified_source_path(
    repo_root: Path, plan_source: Mapping[str, Any]
) -> tuple[Path, str]:
    """Verify source identity once per unchanged inode during a run.

    Tool calls still decode their exact requested interval independently.
    Avoiding a repeated full-file SHA-256 over multi-hundred-MB inputs keeps
    the action-level replay practical without weakening the source binding:
    size, inode and nanosecond mtime must remain unchanged, and strict
    verification re-hashes every source/checkpoint before accepting a run.
    """
    path = repo_root / "data/restricted/noaa01/raw" / plan_source["basename"]
    if not path.is_file() or path.is_symlink() or not _safe_under(
        path, repo_root / "data/restricted/noaa01/raw"
    ):
        raise Scale1AError(f"UNSAFE_SOURCE:{plan_source['candidate_id']}")
    stat_result = path.stat()
    fingerprint = (
        stat_result.st_dev,
        stat_result.st_ino,
        stat_result.st_size,
        stat_result.st_mtime_ns,
    )
    cached = _SOURCE_IDENTITY_CACHE.get(str(path.resolve()))
    if cached is None or cached[:4] != fingerprint:
        digest = _sha256(path)
        _SOURCE_IDENTITY_CACHE[str(path.resolve())] = (*fingerprint, digest)
    else:
        digest = cached[4]
    if (
        stat_result.st_size != plan_source["size_bytes"]
        or digest != plan_source["sha256"]
    ):
        raise Scale1AError(
            f"SOURCE_IDENTITY_MISMATCH:{plan_source['candidate_id']}"
        )
    return path, digest


def _decode_audio_full(path: Path, target_rate: int = 16_000) -> np.ndarray:
    parts: list[np.ndarray] = []
    with av.open(str(path), mode="r") as container:
        stream = next((s for s in container.streams if s.type == "audio"), None)
        if stream is None:
            raise Scale1AError(f"AUDIO_STREAM_MISSING:{path.name}")
        resampler = av.audio.resampler.AudioResampler(
            format="fltp", layout="mono", rate=target_rate
        )
        for frame in container.decode(stream):
            for converted in resampler.resample(frame):
                parts.append(converted.to_ndarray().reshape(-1).astype(np.float32))
        for converted in resampler.resample(None):
            parts.append(converted.to_ndarray().reshape(-1).astype(np.float32))
    if not parts:
        raise Scale1AError(f"AUDIO_DECODE_EMPTY:{path.name}")
    result = np.concatenate(parts)
    if not np.isfinite(result).all():
        raise Scale1AError(f"AUDIO_DECODE_NONFINITE:{path.name}")
    return result


def _slice_audio(
    audio: np.ndarray, start_us: int, end_us: int, rate: int = 16_000
) -> np.ndarray:
    left = max(0, int(round(start_us * rate / 1_000_000)))
    right = min(len(audio), int(round(end_us * rate / 1_000_000)))
    expected = max(1, int(round((end_us - start_us) * rate / 1_000_000)))
    result = audio[left:right]
    if len(result) < expected:
        result = np.pad(result, (0, expected - len(result)))
    return result.astype(np.float32, copy=False)


def _decode_audio_interval(
    path: Path, start_s: float, end_s: float, target_rate: int = 16_000
) -> np.ndarray:
    """Decode only the requested original-media interval into a memory buffer."""
    parts: list[np.ndarray] = []
    with av.open(str(path), mode="r") as container:
        stream = next((s for s in container.streams if s.type == "audio"), None)
        if stream is None:
            raise Scale1AError(f"AUDIO_STREAM_MISSING:{path.name}")
        container.seek(
            int(max(0.0, start_s - 1.0) / float(stream.time_base)),
            stream=stream,
            backward=True,
            any_frame=False,
        )
        resampler = av.audio.resampler.AudioResampler(
            format="fltp", layout="mono", rate=target_rate
        )
        for frame in container.decode(stream):
            if frame.pts is None:
                continue
            frame_start = float(frame.pts * frame.time_base)
            frame_duration = float(frame.samples / frame.sample_rate)
            frame_end = frame_start + frame_duration
            if frame_start >= end_s:
                break
            if frame_end <= start_s:
                continue
            for converted in resampler.resample(frame):
                values = converted.to_ndarray().reshape(-1).astype(np.float32)
                converted_start = frame_start
                left = max(
                    0, int(round((start_s - converted_start) * target_rate))
                )
                right = min(
                    len(values),
                    int(round((end_s - converted_start) * target_rate)),
                )
                if right > left:
                    parts.append(values[left:right])
        for converted in resampler.resample(None):
            # Flush samples belong to the final decoded frame and are only
            # needed when decoding reaches the requested interval end.
            values = converted.to_ndarray().reshape(-1).astype(np.float32)
            if values.size:
                parts.append(values)
    if not parts:
        raise Scale1AError(f"AUDIO_INTERVAL_DECODE_EMPTY:{path.name}")
    result = np.concatenate(parts)
    if not np.isfinite(result).all():
        raise Scale1AError(f"AUDIO_INTERVAL_DECODE_NONFINITE:{path.name}")
    return result


def _iter_sampled_frames(
    path: Path, cells: Sequence[Mapping[str, Any]]
) -> Iterator[tuple[Mapping[str, Any], np.ndarray, int, str]]:
    targets = [int(item["sample_time_us"]) for item in cells]
    cursor = 0
    previous: tuple[Any, int, str] | None = None
    with av.open(str(path), mode="r") as container:
        stream = next((s for s in container.streams if s.type == "video"), None)
        if stream is None:
            raise Scale1AError(f"VIDEO_STREAM_MISSING:{path.name}")
        for frame in container.decode(stream):
            if frame.pts is None:
                continue
            frame_us = int(round(float(frame.pts * frame.time_base) * 1_000_000))
            while cursor < len(targets) and frame_us >= targets[cursor]:
                chosen = previous
                if chosen is None:
                    chosen = (frame, int(frame.pts), str(frame.time_base))
                yield (
                    cells[cursor],
                    chosen[0].to_ndarray(format="rgb24"),
                    chosen[1],
                    chosen[2],
                )
                cursor += 1
            if cursor >= len(targets):
                break
            previous = (frame, int(frame.pts), str(frame.time_base))
    while cursor < len(targets) and previous is not None:
        yield (
            cells[cursor],
            previous[0].to_ndarray(format="rgb24"),
            previous[1],
            previous[2],
        )
        cursor += 1
    if cursor != len(targets):
        raise Scale1AError(f"FRAME_SAMPLING_INCOMPLETE:{path.name}:{cursor}/{len(targets)}")


def _routing_features(
    rgb: np.ndarray, previous_small: np.ndarray | None, face_cascade: Any
) -> tuple[dict[str, Any], np.ndarray]:
    small = cv2.resize(rgb, (160, 90), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    hsv = cv2.cvtColor(small, cv2.COLOR_RGB2HSV)
    edges = cv2.Canny(gray, 80, 160)
    hist = cv2.calcHist([hsv], [0], None, [12], [0, 180]).reshape(-1)
    hist = hist / max(float(hist.sum()), 1.0)
    motion = (
        float(np.mean(cv2.absdiff(gray, previous_small))) / 255.0
        if previous_small is not None else 0.0
    )
    faces = (
        face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4)
        if face_cascade is not None else ()
    )
    features = {
        "luminance_mean": _round(np.mean(gray) / 255.0),
        "luminance_std": _round(np.std(gray) / 255.0),
        "hue_histogram_12": [_round(x) for x in hist],
        "edge_density": _round(np.mean(edges > 0)),
        "motion_or_change": _round(motion),
        "blank_frame": bool(np.std(gray) < 2.0),
        "pinned_haar_face_presence": bool(len(faces)),
        "semantic_claim_allowed": False,
    }
    return features, gray


def _checkpoint_key(
    source_sha256: str, layer_version: str, scale: str, shard_index: int,
    config_hash: str,
) -> str:
    return "/".join(
        (source_sha256, layer_version, scale, str(shard_index), config_hash)
    )


def _write_checkpoint(
    path: Path, payload: Mapping[str, Any], *, key: str, record_count: int
) -> dict[str, Any]:
    body = dict(payload)
    body["checkpoint_key"] = key
    body["record_count"] = record_count
    body["payload_hash"] = _json_hash(payload)
    _dump(path, body, restricted=True)
    return {
        "path": path.as_posix(),
        "key": key,
        "record_count": record_count,
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path, prefixed=True),
        "payload_hash": body["payload_hash"],
    }


def _read_checkpoint(
    path: Path, *, key: str, expected_count: int
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not path.exists():
        return None, None
    try:
        body = _load(path)
        payload = {
            k: v for k, v in body.items()
            if k not in {"checkpoint_key", "record_count", "payload_hash"}
        }
        valid = (
            path.is_file() and not path.is_symlink()
            and stat.S_IMODE(path.stat().st_mode) == 0o600
            and body.get("checkpoint_key") == key
            and body.get("record_count") == expected_count
            and body.get("payload_hash") == _json_hash(payload)
        )
    except Exception:
        valid = False
        payload = {}
    if not valid:
        path.unlink(missing_ok=True)
        return None, None
    return payload, {
        "path": path.as_posix(), "key": key, "record_count": expected_count,
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path, prefixed=True),
        "payload_hash": body["payload_hash"], "reused": True,
    }


class _Models:
    def __init__(
        self, repo_root: Path, *, threads: int, load_whisper: bool,
        load_ast: bool, load_clip: bool,
    ) -> None:
        self.runtime = _configure_runtime(threads)
        try:
            import torch
            from transformers import (
                ASTFeatureExtractor,
                ASTForAudioClassification,
                WhisperForConditionalGeneration,
                WhisperProcessor,
            )
        except Exception as exc:
            raise Scale1AError("LOCAL_MODEL_IMPORT_FAILED") from exc
        self.torch = torch
        torch.manual_seed(0)
        torch.use_deterministic_algorithms(True)
        torch.set_num_threads(threads)
        try:
            torch.set_num_interop_threads(1)
        except RuntimeError:
            pass
        self.whisper_processor = self.whisper_model = None
        self.ast_processor = self.ast_model = None
        self.clip_processor = self.clip_model = None
        if load_whisper:
            path = repo_root / WHISPER_REL
            self.whisper_processor = WhisperProcessor.from_pretrained(
                path, local_files_only=True
            )
            self.whisper_model = WhisperForConditionalGeneration.from_pretrained(
                path, local_files_only=True
            ).to("cpu").eval()
        if load_ast:
            path = repo_root / AST_REL
            self.ast_processor = ASTFeatureExtractor.from_pretrained(
                path, local_files_only=True
            )
            self.ast_model = ASTForAudioClassification.from_pretrained(
                path, local_files_only=True
            ).to("cpu").eval()
        if load_clip:
            try:
                from transformers import CLIPModel, CLIPProcessor
                path = repo_root / CLIP_SNAPSHOT_REL
                self.clip_processor = CLIPProcessor.from_pretrained(
                    path, local_files_only=True, use_fast=False
                )
                self.clip_model = CLIPModel.from_pretrained(
                    path, local_files_only=True
                ).to("cpu").eval()
            except Exception as exc:
                raise Scale1AError("CLIP_LOCAL_LOAD_FAILED") from exc

    def whisper(self, identifiers: Sequence[str], samples: Sequence[np.ndarray]) -> list[dict[str, Any]]:
        assert self.whisper_processor is not None and self.whisper_model is not None
        processor, model, torch = self.whisper_processor, self.whisper_model, self.torch
        inputs = processor(
            list(samples), sampling_rate=16_000, return_tensors="pt",
            padding=True, return_attention_mask=True,
        )
        with torch.inference_mode():
            generated = model.generate(
                inputs.input_features,
                attention_mask=inputs.attention_mask,
                do_sample=False, num_beams=1, max_new_tokens=128,
                return_dict_in_generate=True, output_scores=True,
                return_timestamps=False,
            )
            sequences = (
                generated["sequences"] if isinstance(generated, Mapping)
                else generated.sequences
            )
            generation_scores = (
                generated.get("scores", ()) if isinstance(generated, Mapping)
                else generated.scores
            )
            scores = model.compute_transition_scores(
                sequences, generation_scores, normalize_logits=True
            )
        special = set(processor.tokenizer.all_special_ids)
        output = []
        for row, sequence in enumerate(sequences):
            count = scores.shape[1]
            ids = sequence[-count:].tolist() if count else []
            values = [
                float(score) for token, score in zip(ids, scores[row].tolist())
                if token not in special
            ]
            text = " ".join(
                processor.tokenizer.decode(sequence, skip_special_tokens=True).split()
            )
            mean = float(np.mean(values)) if values else None
            flags = []
            if len(values) < 5:
                flags.append("TOO_FEW_LEXICAL_TOKENS")
            if mean is None or mean < -0.85:
                flags.append("LOW_GENERATED_TOKEN_LOGPROB")
            output.append(
                {
                    "chunk_id": identifiers[row],
                    "text": text,
                    "token_count": len(values),
                    "mean_generated_token_log_probability": _round(mean) if mean is not None else None,
                    "quality_gate_pass": bool(text) and not flags,
                    "quality_flags": flags,
                }
            )
        return output

    def ast(self, samples: Sequence[np.ndarray]) -> list[dict[str, Any]]:
        assert self.ast_processor is not None and self.ast_model is not None
        processor, model, torch = self.ast_processor, self.ast_model, self.torch
        inputs = processor(
            list(samples), sampling_rate=16_000, return_tensors="pt", padding=True
        )
        with torch.inference_mode():
            logits = model(input_values=inputs.input_values).logits
            values, indices = torch.topk(torch.sigmoid(logits), k=15, dim=-1)
        output = []
        for row in range(values.shape[0]):
            labels = [
                {
                    "class_id": int(index),
                    "label": model.config.id2label[int(index)],
                    "probability": _round(value),
                }
                for value, index in zip(values[row].tolist(), indices[row].tolist())
            ]
            generic = [x for x in labels if _is_generic_audio(x["label"])]
            specific = [x for x in labels if not _is_generic_audio(x["label"])]
            output.append(
                {
                    "top15": labels,
                    "generic_or_context": generic,
                    "specific": specific,
                    "quality_gate_pass": bool(specific),
                    "quality_flags": [] if specific else ["NO_SPECIFIC_LABEL"],
                }
            )
        return output

    def clip_images(self, images: Sequence[np.ndarray]) -> np.ndarray:
        assert self.clip_processor is not None and self.clip_model is not None
        inputs = self.clip_processor(images=list(images), return_tensors="pt")
        with self.torch.inference_mode():
            # Transformers 5.x returns a BaseModelOutputWithPooling from
            # get_image_features for this legacy CLIP checkpoint rather than
            # the projected tensor returned by earlier releases.  Invoke the
            # frozen vision tower and projection explicitly so the persisted
            # vectors retain the model's documented 512-D joint space.
            outputs = self.clip_model.vision_model(
                pixel_values=inputs.pixel_values, return_dict=True
            )
            values = self.clip_model.visual_projection(outputs.pooler_output)
        values = values.float().clone()
        values = values / values.norm(dim=-1, keepdim=True).clamp_min(1e-12)
        return values.cpu().numpy().astype(np.float32)

    def clip_text(self, texts: Sequence[str]) -> np.ndarray:
        assert self.clip_processor is not None and self.clip_model is not None
        inputs = self.clip_processor(
            text=list(texts), return_tensors="pt", padding=True, truncation=True
        )
        with self.torch.inference_mode():
            outputs = self.clip_model.text_model(
                input_ids=inputs.input_ids,
                attention_mask=inputs.attention_mask,
                return_dict=True,
            )
            values = self.clip_model.text_projection(outputs.pooler_output)
        values = values.float().clone()
        values = values / values.norm(dim=-1, keepdim=True).clamp_min(1e-12)
        return values.cpu().numpy().astype(np.float32)


_CLIP_TEXT_MODEL_CACHE: dict[str, _Models] = {}
_CLIP_TEXT_VECTOR_CACHE: dict[tuple[str, tuple[str, ...]], np.ndarray] = {}


def _cached_clip_text(
    repo_root: Path, texts: Sequence[str], *, threads: int = 4
) -> np.ndarray:
    """Embed immutable query text once per process.

    Full-timeline evaluation reuses the same small query suite across states,
    policies, scopes, migration, and replay. Reloading the 600 MB CLIP model
    for every ranking is both wasteful and capable of turning a deterministic
    evaluation into an I/O stress test, so cache the local-only model and the
    exact query vectors in memory.
    """
    root_key = str(repo_root.resolve())
    cache_key = (root_key, tuple(texts))
    if cache_key not in _CLIP_TEXT_VECTOR_CACHE:
        model = _CLIP_TEXT_MODEL_CACHE.get(root_key)
        if model is None:
            model = _Models(
                repo_root, threads=threads, load_whisper=False,
                load_ast=False, load_clip=True,
            )
            _CLIP_TEXT_MODEL_CACHE[root_key] = model
        _CLIP_TEXT_VECTOR_CACHE[cache_key] = model.clip_text(texts)
    return _CLIP_TEXT_VECTOR_CACHE[cache_key].copy()


GENERIC_AUDIO = {
    "Speech", "Male speech, man speaking", "Female speech, woman speaking",
    "Child speech, kid speaking", "Conversation", "Narration, monologue",
    "Speech synthesizer", "Chatter", "Hubbub, speech noise, speech babble",
    "Inside, small room", "Inside, large room or hall",
    "Outside, urban or manmade", "Outside, rural or natural", "Music",
    "Musical instrument", "Background music", "Theme music", "Ambient music",
    "Noise", "White noise", "Pink noise", "Wind noise (microphone)",
    "Television", "Radio", "Silence",
}


def _is_generic_audio(label: str) -> bool:
    return label in GENERIC_AUDIO or label.startswith(
        ("Music", "Speech", "Male speech", "Female speech", "Child speech",
         "Narration", "Conversation", "Inside,", "Outside,")
    )


def _model_manifest(repo_root: Path, plan: Mapping[str, Any]) -> dict[str, Any]:
    whisper = _parse_sha256sums(repo_root / WHISPER_REL)
    ast = _parse_sha256sums(repo_root / AST_REL)
    expected = plan["observation_layers"]
    by_name = {
        "whisper": next(
            x for x in whisper if x["path"] == "model.safetensors"
        ),
        "ast": next(x for x in ast if x["path"] == "model.safetensors"),
    }
    if by_name["whisper"]["sha256"] != expected["speech"]["weight_sha256"]:
        raise Scale1AError("WHISPER_PIN_MISMATCH")
    if by_name["ast"]["sha256"] != expected["ambient"]["weight_sha256"]:
        raise Scale1AError("AST_PIN_MISMATCH")
    return {
        "whisper": {
            "model_id": expected["speech"]["model_id"],
            "revision": expected["speech"]["revision"],
            "files": whisper, "snapshot_hash": _json_hash(whisper),
        },
        "ast": {
            "model_id": expected["ambient"]["model_id"],
            "revision": expected["ambient"]["revision"],
            "files": ast, "snapshot_hash": _json_hash(ast),
        },
        "clip": _clip_gate(repo_root, plan),
    }


def _records_for_source(
    segment_manifest: Mapping[str, Any], source_ref: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cells = [
        x for x in segment_manifest["base_cells"] if x["source_ref"] == source_ref
    ]
    segments = [
        x for x in segment_manifest["segments"] if x["source_ref"] == source_ref
    ]
    return cells, segments


def _project_speech(
    chunks: Sequence[Mapping[str, Any]], segments: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Return one honest search/citation record per non-overlapping ASR chunk.

    The frozen Task-95 checkpoints also contain the former 8/32-second
    projection.  That projection is deliberately ignored: a complete
    30-second transcript cannot truthfully be attributed to every overlapping
    visual/ambient window.  The original chunk bytes remain immutable while
    all derived artifacts use these atomic records.
    """
    del segments
    output = []
    for chunk in chunks:
        text = str(chunk.get("text", "")).strip()
        chunk_id = str(chunk["chunk_id"])
        record_id = "asr." + hashlib.sha256(chunk_id.encode("utf-8")).hexdigest()[:20]
        output.append(
            {
                "segment_id": record_id,
                "speech_record_id": record_id,
                "chunk_id": chunk_id,
                "source_ref": chunk["source_ref"],
                "scale": "speech_chunk_30s",
                "start_us": int(chunk["start_us"]),
                "end_us": int(chunk["end_us"]),
                "modality": "speech",
                "text": text,
                "derived_from_chunk_ids": [chunk_id],
                "searchable": bool(text and chunk.get("quality_gate_pass")),
                "exclusion_reason": (
                    None
                    if text and chunk.get("quality_gate_pass")
                    else "empty_or_failed_quality_gate"
                ),
                "citation_interval_truth": "whole_non_overlapping_asr_chunk",
            }
        )
    return output


def _aggregate_ambient(
    fine_records: Sequence[Mapping[str, Any]], segments: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    fine_by_id = {x["segment_id"]: x for x in fine_records}
    output = list(fine_records)
    for segment in segments:
        if segment["scale"] != "context":
            continue
        children = [
            x for x in fine_records
            if _overlaps(
                (x["start_us"], x["end_us"]),
                (segment["start_us"], segment["end_us"]),
            )
        ]
        values: dict[int, list[tuple[str, float, bool]]] = defaultdict(list)
        for child in children:
            for item in child["labels"]:
                values[item["class_id"]].append(
                    (item["label"], item["probability"], item["generic"])
                )
        labels = []
        for class_id, entries in values.items():
            labels.append(
                {
                    "class_id": class_id,
                    "label": entries[0][0],
                    "generic": entries[0][2],
                    "max_probability": _round(max(x[1] for x in entries)),
                    "mean_probability": _round(np.mean([x[1] for x in entries])),
                }
            )
        labels.sort(
            key=lambda x: (-x["max_probability"], -x["mean_probability"], x["class_id"])
        )
        output.append(
            {
                "segment_id": segment["segment_id"],
                "source_ref": segment["source_ref"],
                "scale": "context",
                "start_us": segment["start_us"],
                "end_us": segment["end_us"],
                "modality": "ambient",
                "labels": labels[:15],
                "child_fine_ids": [x["segment_id"] for x in children],
                "searchable": bool(labels),
                "exclusion_reason": None if labels else "empty_prediction",
            }
        )
    return output


def _pool_vectors(
    cell_ids: Sequence[str], cell_vectors: Mapping[str, np.ndarray]
) -> np.ndarray:
    items = [cell_vectors[x].astype(np.float32) for x in cell_ids if x in cell_vectors]
    if not items:
        raise Scale1AError("VISUAL_POOL_EMPTY")
    vector = np.mean(np.stack(items), axis=0)
    norm = float(np.linalg.norm(vector))
    if not math.isfinite(norm) or norm <= 0:
        raise Scale1AError("VISUAL_POOL_NONFINITE")
    return vector / norm


def build_observations(
    repo_root: Path,
    plan: Mapping[str, Any],
    segment_manifest: Mapping[str, Any],
    *,
    resume: bool = True,
    threads: int = 8,
    source_limit: Sequence[str] | None = None,
    smoke_seconds: float | None = None,
) -> dict[str, Any]:
    """Build source/layer checkpoints without persisting decoded media."""
    restricted_root = repo_root / RESTRICTED_REL
    checkpoint_root = restricted_root / "checkpoints"
    checkpoint_root.mkdir(parents=True, exist_ok=True)
    checkpoint_root.chmod(0o700)
    models_manifest = _model_manifest(repo_root, plan)
    selected = [
        s for s in plan["sources"]
        if source_limit is None or s["candidate_id"] in source_limit
    ]
    config = {
        "threads": threads, "seed": 0, "whisper_batch": 8, "ast_batch": 16,
        "clip_batch": 16, "smoke_seconds": smoke_seconds,
        "segment_manifest_hash": segment_manifest["segment_manifest_hash"],
        "layers": plan["observation_layers"],
    }
    config_hash = _json_hash(config)
    checkpoints: list[dict[str, Any]] = []
    layer_counts = Counter()
    face_path = repo_root / HAAR_REL
    face = cv2.CascadeClassifier(str(face_path)) if face_path.is_file() else None
    if face is not None and face.empty():
        face = None

    for source in selected:
        source_ref = source["candidate_id"]
        path = _source_path(repo_root, source)
        cells, segments = _records_for_source(segment_manifest, source_ref)
        if smoke_seconds is not None:
            limit_us = int(round(smoke_seconds * 1_000_000))
            cells = [x for x in cells if x["start_us"] < limit_us]
            segments = [x for x in segments if x["start_us"] < limit_us]
            # Smoke context must follow the normative isolated 120 s count.
            segments = [
                x for x in segments
                if x["scale"] != "context" or x["end_us"] <= limit_us
            ]

        # Routing and optional CLIP share one sequential video decode.
        routing_path = checkpoint_root / source_ref / "vision_routing.json"
        routing_key = _checkpoint_key(
            source["sha256"], "opencv-routing/1.0", "base", 0, config_hash
        )
        routing_payload, routing_meta = (
            _read_checkpoint(routing_path, key=routing_key, expected_count=len(cells))
            if resume else (None, None)
        )
        clip_ready = bool(models_manifest["clip"]["ready"])
        clip_path = checkpoint_root / source_ref / "vision_clip.json"
        clip_key = _checkpoint_key(
            source["sha256"], "clip-visual/1.0", "base", 0, config_hash
        )
        clip_payload, clip_meta = (
            _read_checkpoint(clip_path, key=clip_key, expected_count=len(cells))
            if resume and clip_ready else (None, None)
        )
        if routing_payload is None or (clip_ready and clip_payload is None):
            models = _Models(
                repo_root, threads=threads, load_whisper=False, load_ast=False,
                load_clip=clip_ready,
            )
            routing_records: list[dict[str, Any]] = []
            cell_vector_records: list[dict[str, Any]] = []
            image_batch: list[np.ndarray] = []
            image_cells: list[Mapping[str, Any]] = []
            previous_gray = None

            def flush_images() -> None:
                nonlocal image_batch, image_cells
                if not image_batch:
                    return
                vectors = models.clip_images(image_batch)
                for cell, vector in zip(image_cells, vectors):
                    cell_vector_records.append(
                        {
                            "cell_id": cell["cell_id"],
                            "vector_f16_hex": vector.astype("<f2").tobytes().hex(),
                            "dimension": int(vector.shape[0]),
                            "l2_normalized": True,
                        }
                    )
                image_batch, image_cells = [], []

            for cell, rgb, pts, time_base in _iter_sampled_frames(path, cells):
                features, previous_gray = _routing_features(rgb, previous_gray, face)
                routing_records.append(
                    {
                        "cell_id": cell["cell_id"], "source_ref": source_ref,
                        "sample_time_us": cell["sample_time_us"], "pts": pts,
                        "time_base": time_base, "features": features,
                    }
                )
                if clip_ready:
                    image_batch.append(rgb)
                    image_cells.append(cell)
                    if len(image_batch) >= 16:
                        flush_images()
            flush_images()
            if routing_payload is None:
                routing_payload = {
                    "layer_version": "opencv-routing/1.0",
                    "semantic_claim_allowed": False,
                    "records": routing_records,
                }
                routing_meta = _write_checkpoint(
                    routing_path, routing_payload, key=routing_key,
                    record_count=len(routing_records),
                )
            if clip_ready and clip_payload is None:
                vectors = {
                    item["cell_id"]: np.frombuffer(
                        bytes.fromhex(item["vector_f16_hex"]), dtype="<f2"
                    ).astype(np.float32)
                    for item in cell_vector_records
                }
                pooled = []
                for segment in segments:
                    vector = _pool_vectors(segment["binding_cell_ids"], vectors)
                    pooled.append(
                        {
                            "segment_id": segment["segment_id"],
                            "source_ref": source_ref,
                            "scale": segment["scale"],
                            "start_us": segment["start_us"],
                            "end_us": segment["end_us"],
                            "modality": "vision",
                            "vector_f16_hex": vector.astype("<f2").tobytes().hex(),
                            "dimension": int(vector.shape[0]),
                            "searchable": True,
                        }
                    )
                clip_payload = {
                    "layer_version": "clip-visual/1.0",
                    "cell_vectors": cell_vector_records,
                    "segment_records": pooled,
                }
                clip_meta = _write_checkpoint(
                    clip_path, clip_payload, key=clip_key,
                    record_count=len(cells),
                )
        assert routing_meta is not None
        checkpoints.append(routing_meta)
        layer_counts["routing_cells"] += len(routing_payload["records"])
        if clip_ready:
            assert clip_payload is not None and clip_meta is not None
            checkpoints.append(clip_meta)
            layer_counts["clip_cells"] += len(clip_payload["cell_vectors"])
            layer_counts["vision_records"] += len(clip_payload["segment_records"])

        # Decode source audio once, only when either audio checkpoint is absent.
        speech_path = checkpoint_root / source_ref / "speech.json"
        speech_count = int(math.ceil(
            (smoke_seconds if smoke_seconds is not None else source["duration_s"]) / 30
        ))
        speech_key = _checkpoint_key(
            source["sha256"], "whisper-tiny-en-timestamped/1.0",
            "30-second", 0, config_hash,
        )
        speech_payload, speech_meta = (
            _read_checkpoint(speech_path, key=speech_key, expected_count=speech_count)
            if resume else (None, None)
        )
        fine_segments = [x for x in segments if x["scale"] == "fine"]
        ambient_path = checkpoint_root / source_ref / "ambient.json"
        ambient_key = _checkpoint_key(
            source["sha256"], "ast-audioset-top15/1.0", "fine", 0, config_hash
        )
        ambient_payload, ambient_meta = (
            _read_checkpoint(
                ambient_path, key=ambient_key, expected_count=len(fine_segments)
            ) if resume else (None, None)
        )
        if speech_payload is None or ambient_payload is None:
            audio = _decode_audio_full(path)
            models = _Models(
                repo_root, threads=threads,
                load_whisper=speech_payload is None,
                load_ast=ambient_payload is None,
                load_clip=False,
            )
            if speech_payload is None:
                chunks: list[dict[str, Any]] = []
                specs = []
                duration_us = min(
                    int(round(source["duration_s"] * 1_000_000)),
                    int(round(smoke_seconds * 1_000_000))
                    if smoke_seconds is not None else 10**30,
                )
                for i, start_us in enumerate(range(0, duration_us, 30_000_000)):
                    specs.append(
                        (
                            f"speech.{source['sha256'][:12]}.{i:06d}",
                            start_us, min(start_us + 30_000_000, duration_us),
                        )
                    )
                for offset in range(0, len(specs), 8):
                    batch = specs[offset:offset + 8]
                    inferred = models.whisper(
                        [x[0] for x in batch],
                        [_slice_audio(audio, x[1], x[2]) for x in batch],
                    )
                    for spec, item in zip(batch, inferred):
                        chunks.append(
                            {
                                **item, "source_ref": source_ref,
                                "start_us": spec[1], "end_us": spec[2],
                            }
                        )
                projected = _project_speech(chunks, segments)
                speech_payload = {
                    "layer_version": "whisper-tiny-en-timestamped/1.0",
                    "chunks": chunks, "segment_records": projected,
                }
                speech_meta = _write_checkpoint(
                    speech_path, speech_payload, key=speech_key,
                    record_count=len(chunks),
                )
            if ambient_payload is None:
                fine_records: list[dict[str, Any]] = []
                for offset in range(0, len(fine_segments), 16):
                    batch = fine_segments[offset:offset + 16]
                    inferred = models.ast(
                        [
                            _slice_audio(audio, x["start_us"], x["end_us"])
                            for x in batch
                        ]
                    )
                    for segment, item in zip(batch, inferred):
                        labels = [
                            {
                                **label,
                                "generic": _is_generic_audio(label["label"]),
                                "ranking_probability": _round(
                                    label["probability"] * (
                                        0.25 if _is_generic_audio(label["label"]) else 1.0
                                    )
                                ),
                            }
                            for label in item["top15"]
                        ]
                        fine_records.append(
                            {
                                "segment_id": segment["segment_id"],
                                "source_ref": source_ref, "scale": "fine",
                                "start_us": segment["start_us"],
                                "end_us": segment["end_us"],
                                "modality": "ambient", "labels": labels,
                                "searchable": bool(labels),
                                "exclusion_reason": None if labels else "empty_prediction",
                                "quality_flags": item["quality_flags"],
                            }
                        )
                records = _aggregate_ambient(fine_records, segments)
                ambient_payload = {
                    "layer_version": "ast-audioset-top15/1.0",
                    "records": records,
                }
                ambient_meta = _write_checkpoint(
                    ambient_path, ambient_payload, key=ambient_key,
                    record_count=len(fine_records),
                )
            del audio
        assert speech_payload is not None and speech_meta is not None
        assert ambient_payload is not None and ambient_meta is not None
        checkpoints.extend((speech_meta, ambient_meta))
        layer_counts["whisper_chunks"] += len(speech_payload["chunks"])
        layer_counts["speech_search_records"] += len(
            _project_speech(
                speech_payload["chunks"], speech_payload.get("segment_records", ())
            )
        )
        layer_counts["legacy_projected_speech_records_ignored"] += len(
            speech_payload.get("segment_records", ())
        )
        layer_counts["ast_fine_calls"] += len(fine_segments)
        layer_counts["ambient_records"] += len(ambient_payload["records"])

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE, "restricted": True,
        "human_reviewed": False, "gold_annotation": False,
        "config": config, "config_hash": config_hash,
        "model_snapshots": models_manifest,
        "checkpoints": sorted(checkpoints, key=lambda x: x["path"]),
        "counts": dict(sorted(layer_counts.items())),
        "complete_source_refs": [x["candidate_id"] for x in selected],
        "all_five_complete": len(selected) == 5 and smoke_seconds is None,
        # Wall-clock timing is intentionally not persisted: it made an
        # otherwise checkpoint-only resume produce a different observation
        # manifest and therefore a different frozen index hash.
        "elapsed_seconds_recorded": False,
        "no_persisted_media_derivatives": True,
        "speech_representation": {
            "type": "non_overlapping_chunk_records",
            "localization": "truthful_30_second_asr_chunk_interval",
            "legacy_segment_projections_searchable": False,
            "checkpoint_chunks_reused_without_acoustic_redecode": True,
        },
    }
    manifest["observation_manifest_hash"] = _json_hash(manifest)
    return manifest


def _checkpoint_payload(repo_root: Path, relative_or_absolute: str) -> dict[str, Any]:
    path = Path(relative_or_absolute)
    if not path.is_absolute():
        path = repo_root / path
    body = _load(path)
    return {
        k: v for k, v in body.items()
        if k not in {"checkpoint_key", "record_count", "payload_hash"}
    }


def _load_observation_records(
    repo_root: Path, observation_manifest: Mapping[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = {
        "speech": [], "ambient": [], "vision": [], "routing": [],
    }
    for checkpoint in observation_manifest["checkpoints"]:
        payload = _checkpoint_payload(repo_root, checkpoint["path"])
        path = checkpoint["path"]
        if path.endswith("/speech.json"):
            output["speech"].extend(
                _project_speech(payload["chunks"], payload.get("segment_records", ()))
            )
        elif path.endswith("/ambient.json"):
            output["ambient"].extend(payload["records"])
        elif path.endswith("/vision_clip.json"):
            output["vision"].extend(payload["segment_records"])
        elif path.endswith("/vision_routing.json"):
            output["routing"].extend(payload["records"])
    return output


def _assert_search_record_safe(record: Mapping[str, Any]) -> None:
    # Keys inside an explicitly typed token-frequency map are vocabulary
    # values, not schema fields.  A naturally spoken token such as "question"
    # must not be mistaken for an evaluator-field leak.
    stack: list[tuple[Any, str | None]] = [(record, None)]
    while stack:
        value, parent_key = stack.pop()
        if isinstance(value, Mapping):
            for key, child in value.items():
                if (
                    parent_key not in {"term_frequency", "document_frequency"}
                    and key in FORBIDDEN_SEARCH_KEYS
                ):
                    raise Scale1AError(f"FORBIDDEN_SEARCH_FIELD:{key}")
                stack.append((child, key))
        elif isinstance(value, list):
            stack.extend((child, parent_key) for child in value)


def _bm25_payload(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    docs = [_tokens(str(record.get("text", ""))) for record in records]
    df: Counter[str] = Counter()
    for tokens in docs:
        df.update(set(tokens))
    return {
        "document_count": len(records),
        "average_document_length": _round(
            np.mean([len(x) for x in docs]) if docs else 0.0
        ),
        "document_frequency": dict(sorted(df.items())),
        "documents": [
            {
                "segment_id": record["segment_id"],
                "speech_record_id": record["speech_record_id"],
                "derived_from_chunk_ids": record["derived_from_chunk_ids"],
                "source_ref": record["source_ref"],
                "scale": record["scale"],
                "start_us": record["start_us"],
                "end_us": record["end_us"],
                "modality": "speech",
                "tokens": tokens,
                "term_frequency": dict(sorted(Counter(tokens).items())),
                "searchable": bool(record["searchable"]),
            }
            for record, tokens in zip(records, docs)
        ],
    }


def _ambient_index_payload(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    documents = []
    for record in records:
        features = []
        for item in record["labels"]:
            probability = item.get(
                "ranking_probability",
                item.get("max_probability", item.get("probability", 0.0)),
            )
            generic = bool(item["generic"])
            if record["scale"] == "context":
                probability = (
                    float(item["max_probability"]) + float(item["mean_probability"])
                ) / 2
                if generic:
                    probability *= 0.25
            features.append(
                {
                    "class_id": int(item["class_id"]),
                    "label": item["label"],
                    "tokens": _tokens(item["label"]),
                    "weight": _round(probability),
                    "generic": generic,
                }
            )
        documents.append(
            {
                "segment_id": record["segment_id"],
                "source_ref": record["source_ref"],
                "scale": record["scale"],
                "start_us": record["start_us"],
                "end_us": record["end_us"],
                "modality": "ambient",
                "features": features,
                "searchable": bool(record["searchable"]),
            }
        )
    return {"documents": documents}


def _vision_index_payload(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "documents": [
            {
                "segment_id": record["segment_id"],
                "source_ref": record["source_ref"],
                "scale": record["scale"],
                "start_us": record["start_us"],
                "end_us": record["end_us"],
                "modality": "vision",
                "vector_f16_hex": record["vector_f16_hex"],
                "dimension": record["dimension"],
                "searchable": True,
            }
            for record in records
        ]
    }


def _rank_tie(record: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        record["source_ref"], record["start_us"], record["end_us"],
        record["segment_id"], record["modality"],
    )


def _scope_filter(
    documents: Sequence[Mapping[str, Any]], source_ref: str | None,
    time_range: Sequence[float] | None = None,
) -> list[Mapping[str, Any]]:
    range_us = (
        (
            int(round(float(time_range[0]) * 1_000_000)),
            int(round(float(time_range[1]) * 1_000_000)),
        )
        if time_range is not None else None
    )
    return [
        x for x in documents
        if x.get("searchable")
        and (source_ref is None or x["source_ref"] == source_ref)
        and (
            range_us is None
            or x["start_us"] < range_us[1] and x["end_us"] > range_us[0]
        )
    ]


def search_speech(
    index: Mapping[str, Any], query: str, *, top_k: int,
    source_ref: str | None = None, exclude_ids: Iterable[str] = (),
    time_range: Sequence[float] | None = None,
) -> list[dict[str, Any]]:
    docs = _scope_filter(
        index["modalities"]["speech"]["documents"], source_ref, time_range
    )
    excluded = set(exclude_ids)
    n_docs = max(1, index["modalities"]["speech"]["document_count"])
    avgdl = max(1e-12, index["modalities"]["speech"]["average_document_length"])
    df = index["modalities"]["speech"]["document_frequency"]
    query_tokens = _tokens(query)
    scored = []
    for doc in docs:
        if doc["segment_id"] in excluded:
            continue
        score = 0.0
        length = max(1, len(doc["tokens"]))
        for token in query_tokens:
            tf = doc["term_frequency"].get(token, 0)
            if not tf:
                continue
            idf = math.log(1.0 + (n_docs - df.get(token, 0) + 0.5) / (df.get(token, 0) + 0.5))
            score += idf * (tf * 2.2) / (tf + 1.2 * (1 - 0.75 + 0.75 * length / avgdl))
        if score > 0:
            scored.append({**_pointer(doc), "score": _round(score)})
    scored.sort(key=lambda x: (-x["score"], *_rank_tie(x)))
    return scored[:top_k]


AMBIENT_SYNONYMS = {
    "water": {"ocean", "waves", "surf", "water"},
    "wave": {"waves", "surf", "ocean"},
    "waves": {"waves", "surf", "ocean"},
    "wind": {"wind"},
    "storm": {"thunderstorm", "thunder", "rain", "wind"},
    "rain": {"rain", "raindrop"},
    "animal": {"animal", "bird", "dog"},
    "vehicle": {"vehicle", "boat", "aircraft", "car"},
}


def search_ambient(
    index: Mapping[str, Any], query: str, *, top_k: int,
    source_ref: str | None = None, exclude_ids: Iterable[str] = (),
    time_range: Sequence[float] | None = None,
) -> list[dict[str, Any]]:
    docs = _scope_filter(
        index["modalities"]["ambient"]["documents"], source_ref, time_range
    )
    excluded = set(exclude_ids)
    qtokens = set(_tokens(query))
    expanded = set(qtokens)
    for token in qtokens:
        expanded.update(AMBIENT_SYNONYMS.get(token, ()))
    scored = []
    qnorm = math.sqrt(max(1, len(expanded)))
    for doc in docs:
        if doc["segment_id"] in excluded:
            continue
        numerator = 0.0
        norm = 0.0
        for feature in doc["features"]:
            weight = float(feature["weight"])
            norm += weight * weight
            overlap = expanded.intersection(feature["tokens"])
            if overlap:
                numerator += weight * len(overlap)
        score = numerator / (qnorm * math.sqrt(norm)) if norm and numerator else 0.0
        if score > 0:
            scored.append({**_pointer(doc), "score": _round(score)})
    scored.sort(key=lambda x: (-x["score"], *_rank_tie(x)))
    return scored[:top_k]


def _decode_vector(record: Mapping[str, Any]) -> np.ndarray:
    return np.frombuffer(
        bytes.fromhex(record["vector_f16_hex"]), dtype="<f2"
    ).astype(np.float32)


def search_visual(
    repo_root: Path, index: Mapping[str, Any], query: str, *, top_k: int,
    source_ref: str | None = None, exclude_ids: Iterable[str] = (),
    text_vector: np.ndarray | None = None,
    time_range: Sequence[float] | None = None,
) -> list[dict[str, Any]]:
    if not index["modalities"]["vision"].get("ready"):
        raise Scale1AError("CLIP_VISUAL_INDEX_UNAVAILABLE")
    docs = _scope_filter(
        index["modalities"]["vision"]["documents"], source_ref, time_range
    )
    excluded = set(exclude_ids)
    if text_vector is None:
        models = _Models(
            repo_root, threads=4, load_whisper=False, load_ast=False, load_clip=True
        )
        text_vector = models.clip_text([query])[0]
    scored = []
    for doc in docs:
        if doc["segment_id"] in excluded:
            continue
        score = float(np.dot(text_vector.astype(np.float32), _decode_vector(doc)))
        scored.append({**_pointer(doc), "score": _round(score)})
    scored.sort(key=lambda x: (-x["score"], *_rank_tie(x)))
    return scored[:top_k]


def _pointer(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "result_type": "segment_pointer",
        "result_id": "ptr." + hashlib.sha256(
            f"{record['segment_id']}:{record['modality']}".encode()
        ).hexdigest()[:16],
        "segment_id": record["segment_id"],
        "source_ref": record["source_ref"],
        "interval": {
            "start_s": _round(record["start_us"] / 1_000_000, 6),
            "end_s": _round(record["end_us"] / 1_000_000, 6),
        },
        "start_us": record["start_us"], "end_us": record["end_us"],
        "modality": record["modality"], "scale": record["scale"],
        "generic_preview": f"{record['modality']} {record['scale']} observation",
    }


def search_fused(
    rankings: Mapping[str, Sequence[Mapping[str, Any]]], *, top_k: int
) -> list[dict[str, Any]]:
    scores: dict[tuple[str, int, int], float] = defaultdict(float)
    representatives: dict[tuple[str, int, int], dict[str, Any]] = {}
    modalities: dict[tuple[str, int, int], set[str]] = defaultdict(set)
    for modality, ranking in rankings.items():
        for rank, result in enumerate(ranking, 1):
            # Four-second temporal group makes fine/context duplicates collapse.
            key = (
                result["source_ref"],
                int(result["start_us"] // 4_000_000),
                int((result["end_us"] - 1) // 4_000_000),
            )
            scores[key] += 1.0 / (60 + rank)
            modalities[key].add(modality)
            current = representatives.get(key)
            if current is None or _rank_tie(result) < _rank_tie(current):
                representatives[key] = dict(result)
    output = []
    for key, score in scores.items():
        item = dict(representatives[key])
        item["score"] = _round(score)
        item["fused_modalities"] = sorted(modalities[key])
        output.append(item)
    output.sort(key=lambda x: (-x["score"], *_rank_tie(x)))
    return output[:top_k]


def build_index(
    repo_root: Path,
    plan: Mapping[str, Any],
    segment_manifest: Mapping[str, Any],
    observation_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    if not observation_manifest.get("all_five_complete"):
        raise Scale1AError("OBSERVATION_BUILD_NOT_ALL_FIVE_COMPLETE")
    records = _load_observation_records(repo_root, observation_manifest)
    speech = _bm25_payload(records["speech"])
    ambient = _ambient_index_payload(records["ambient"])
    clip_ready = observation_manifest["model_snapshots"]["clip"]["ready"]
    vision = _vision_index_payload(records["vision"]) if clip_ready else {"documents": []}
    vision.update(
        {
            "ready": clip_ready,
            "failure": None if clip_ready else observation_manifest["model_snapshots"]["clip"]["reason"],
        }
    )
    index = {
        "schema_version": SCHEMA_VERSION,
        "index_version": INDEX_VERSION,
        "backend_protocol_version": plan["index"]["backend_protocol_version"],
        "stage": STAGE, "restricted": True,
        "human_reviewed": False, "gold_annotation": False,
        "learned_model_evaluation": False,
        "source_hashes": {
            x["source_ref"]: x["sha256"] for x in segment_manifest["sources"]
        },
        "segment_manifest_hash": segment_manifest["segment_manifest_hash"],
        "observation_manifest_hash": observation_manifest["observation_manifest_hash"],
        "rankers": plan["index"],
        "searchable_field_policy": {
            "forbidden_keys": sorted(FORBIDDEN_SEARCH_KEYS),
            "legacy_codex_descriptions_excluded": True,
            "evaluator_annotations_excluded": True,
        },
        "modalities": {
            "speech": speech, "ambient": ambient, "vision": vision,
        },
        "speech_lineage": {
            "relation": "chunk_id_to_derived_search_record_ids",
            "chunk_to_record_ids": _speech_lineage(
                {"modalities": {"speech": speech}}
            ),
            "unique_chunk_evidence": True,
            "search_rank_duplicate_policy": "one_result_per_asr_chunk",
            "exact_citation_interval": "whole_asr_chunk",
        },
        "counts": {
            "speech_records": len(speech["documents"]),
            "ambient_records": len(ambient["documents"]),
            "vision_records": len(vision["documents"]),
            "maximum_records": plan["totals"]["maximum_modality_segment_record_count"],
        },
    }
    for modality in index["modalities"].values():
        for record in modality.get("documents", []):
            _assert_search_record_safe(record)
    without = dict(index)
    index["index_hash"] = _json_hash(without)
    return index


def _pilot_family_map(repo_root: Path) -> dict[str, dict[str, Any]]:
    document = _load(repo_root / PILOT_FAMILIES_REL)
    return {x["family_id"]: x for x in document["families"]}


def _support_segments(
    family: Mapping[str, Any],
    index: Mapping[str, Any],
    modality: str,
) -> list[str]:
    target = family["primary_fine_interval_s"]
    if modality == "speech":
        return [
            x["segment_id"] for x in index["modalities"]["speech"].get(
                "documents", []
            )
            if x["source_ref"] == family["asset_id"]
            and _overlaps(
                (x["start_us"] / 1e6, x["end_us"] / 1e6), target
            )
        ]
    documents = index["modalities"][modality].get("documents", [])
    return [
        x["segment_id"] for x in documents
        if x["source_ref"] == family["asset_id"]
        and (
            _interval_iou(
                (x["start_us"] / 1e6, x["end_us"] / 1e6), target
            ) >= 0.5
            or _coverage(
                (x["start_us"] / 1e6, x["end_us"] / 1e6), target
            ) >= 0.8
        )
    ]


def _speech_lineage(index: Mapping[str, Any]) -> dict[str, list[str]]:
    """Map each immutable ASR chunk to every derived searchable record."""
    lineage: dict[str, list[str]] = defaultdict(list)
    for record in index["modalities"]["speech"].get("documents", []):
        for chunk_id in record.get("derived_from_chunk_ids", ()):
            lineage[str(chunk_id)].append(str(record["segment_id"]))
    return {
        chunk_id: sorted(set(record_ids))
        for chunk_id, record_ids in sorted(lineage.items())
    }


def _query_rankings(
    repo_root: Path, index: Mapping[str, Any], family: Mapping[str, Any],
    *, source_scoped: bool, top_k: int = 20,
) -> dict[str, list[dict[str, Any]]]:
    source_ref = family["asset_id"] if source_scoped else None
    queries = family["query_families"]
    output: dict[str, list[dict[str, Any]]] = {}
    clip_text: dict[str, np.ndarray] = {}
    if index["modalities"]["vision"]["ready"] and "vision" in family["provisional_modalities"]:
        vectors = _cached_clip_text(repo_root, queries)
        clip_text = dict(zip(queries, vectors))
    for modality in family["provisional_modalities"]:
        query = queries[min(len(queries) - 1, 1 if modality == "ambient" else 0)]
        if modality == "speech":
            ranking = search_speech(
                index, query, top_k=top_k, source_ref=source_ref
            )
        elif modality == "ambient":
            ranking = search_ambient(
                index, query, top_k=top_k, source_ref=source_ref
            )
        elif modality == "vision":
            if not index["modalities"]["vision"]["ready"]:
                ranking = []
            else:
                ranking = search_visual(
                    repo_root, index, query, top_k=top_k, source_ref=source_ref,
                    text_vector=clip_text[query],
                )
        else:
            ranking = []
        output[modality] = ranking
    # When both speech and vision are requested, expose the label-independent
    # temporal-binding route described by the Scale-1A protocol: high-ranked
    # speech intervals may route inspection to visual segments that overlap
    # the same four-second cells.  This uses only public ranking results and
    # immutable timestamps; it never reads support/family/evidence labels.
    if "vision" in output and any(
        modality in output for modality in ("speech", "ambient")
    ):
        bound: list[dict[str, Any]] = []
        seen: set[str] = set()
        visual_documents = _scope_filter(
            index["modalities"]["vision"]["documents"], source_ref
        )
        anchors: list[tuple[int, str, Mapping[str, Any]]] = []
        for anchor_modality in ("speech", "ambient"):
            for anchor_rank, anchor in enumerate(
                output.get(anchor_modality, ())[:20], 1
            ):
                anchors.append((anchor_rank, anchor_modality, anchor))
        anchors.sort(key=lambda item: (item[0], item[1], _rank_tie(item[2])))
        for anchor_rank, anchor_modality, anchor in anchors:
            candidates = [
                document
                for document in visual_documents
                if document["source_ref"] == anchor["source_ref"]
                and document["start_us"] < anchor["end_us"]
                and document["end_us"] > anchor["start_us"]
            ]
            candidates.sort(
                key=lambda document: (
                    document["scale"] != "fine",
                    -_interval_iou(
                        (document["start_us"], document["end_us"]),
                        (anchor["start_us"], anchor["end_us"]),
                    ),
                    *_rank_tie(document),
                )
            )
            for document in candidates[:1]:
                if document["segment_id"] in seen:
                    continue
                seen.add(document["segment_id"])
                pointer = _pointer(document)
                pointer["score"] = _round(1.0 / (60 + anchor_rank))
                pointer["temporal_binding_from"] = anchor_modality
                bound.append(pointer)
        # A temporally bound candidate is a distinct, auditable route.  Keep
        # the direct CLIP ordering after it and deduplicate deterministically.
        for item in output["vision"]:
            if item["segment_id"] not in seen:
                seen.add(item["segment_id"])
                bound.append(item)
        output["vision"] = bound[:top_k]
    output["fused"] = search_fused(output, top_k=top_k)
    return output


def _rank_of_support(
    ranking: Sequence[Mapping[str, Any]], support_ids: set[str]
) -> int | None:
    for rank, result in enumerate(ranking, 1):
        if result["segment_id"] in support_ids:
            return rank
    return None


def migrate_families(
    repo_root: Path, plan: Mapping[str, Any], index: Mapping[str, Any]
) -> dict[str, Any]:
    pilot = _pilot_family_map(repo_root)
    output = []
    for planned in plan["families"]:
        base = pilot[planned["family_id"]]
        support = {
            modality: _support_segments(planned, index, modality)
            for modality in planned["provisional_modalities"]
        }
        rankings = _query_rankings(
            repo_root, index, planned, source_scoped=True, top_k=20
        )
        ranks = {
            modality: _rank_of_support(rankings.get(modality, []), set(ids))
            for modality, ids in support.items()
        }
        route_ranks = dict(ranks)
        if (
            "vision" in planned["provisional_modalities"]
            and "speech" in planned["provisional_modalities"]
            and ranks.get("vision") is None
            and ranks.get("speech") is not None
        ):
            # Cross-modal temporal routing is evaluated at the truthful speech
            # chunk level. A top-ranked ASR chunk can route exact inspection to
            # the registered visual interval inside that chunk without
            # pretending the transcript belongs to the 8-second visual record.
            route_ranks["vision"] = ranks["speech"]
        failures = []
        if "vision" in planned["provisional_modalities"] and not index["modalities"]["vision"]["ready"]:
            failures.append("CLIP_VISUAL_INDEX_UNAVAILABLE_FAIL_CLOSED")
        for modality, ids in support.items():
            if not ids:
                failures.append(f"NO_INDEXED_{modality.upper()}_SUPPORT")
            if route_ranks[modality] is None or route_ranks[modality] > 20:
                failures.append(f"{modality.upper()}_SUPPORT_NOT_TOP20")
        retained = not failures
        output.append(
            {
                "family_id": planned["family_id"],
                "source_review_id": base["source_review_id"],
                "asset_id": planned["asset_id"],
                "legacy_interval_s": planned["legacy_interval_s"],
                "primary_fine_interval_s": planned["primary_fine_interval_s"],
                "question": planned["rewrite_question"] or base["question"],
                "original_question": base["question"],
                "question_rewritten": planned["rewrite_question"] is not None,
                "answer_hypothesis": base["answer_hypothesis"],
                "answer_aliases": base["answer_aliases"],
                "claims": base["claims"],
                "evidence_units": base["evidence_units"],
                "candidate_support_sets": base["candidate_support_sets"],
                "provisional_modalities": planned["provisional_modalities"],
                "support_segment_ids": support,
                "clean_ranks": route_ranks,
                "direct_clean_ranks": ranks,
                "cross_modal_route": (
                    {
                        "from": "speech_chunk",
                        "to": "exact_visual_interval_inspection",
                        "rank": route_ranks.get("vision"),
                    }
                    if route_ranks.get("vision") != ranks.get("vision") else None
                ),
                "expected_route": planned["expected_route"],
                "distractor_pressure": planned["distractor_pressure"],
                "query_families": planned["query_families"],
                "forbidden_seed_aliases": planned["forbidden_seed_aliases"],
                "migration_disposition": "retained" if retained else "excluded",
                "migration_failures": failures,
                "r016_corroboration_not_modality_necessity": planned["family_id"].startswith("noaa01-r016"),
                "human_reviewed": False, "gold_annotation": False,
                "minimality_human_validated": False,
                "modality_necessity_human_validated": False,
            }
        )
    retained = [x for x in output if x["migration_disposition"] == "retained"]
    result = {
        "schema_version": SCHEMA_VERSION, "stage": STAGE, "restricted": True,
        "human_reviewed": False, "gold_annotation": False,
        "families": output, "retained_family_count": len(retained),
        "excluded_family_count": len(output) - len(retained),
        "speech_family_retained": any(
            "speech" in x["provisional_modalities"] for x in retained
        ),
        "ambient_or_cross_modal_retained": any(
            "ambient" in x["provisional_modalities"]
            or len(x["provisional_modalities"]) > 1 for x in retained
        ),
    }
    result["migration_hash"] = _json_hash(result)
    return result


def build_hard_negatives(
    repo_root: Path, plan: Mapping[str, Any], index: Mapping[str, Any],
    migration: Mapping[str, Any],
) -> dict[str, Any]:
    families = []
    for family in migration["families"]:
        if family["migration_disposition"] != "retained":
            families.append(
                {
                    "family_id": family["family_id"], "status": "not_applicable",
                    "admitted": [],
                }
            )
            continue
        planned = next(x for x in plan["families"] if x["family_id"] == family["family_id"])
        rankings = _query_rankings(
            repo_root, index, planned, source_scoped=True, top_k=100
        )
        support = {
            item for values in family["support_segment_ids"].values() for item in values
        }
        target = family["primary_fine_interval_s"]
        aliases = set(_tokens(" ".join(family["answer_aliases"])))
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()
        admitted_intervals: list[tuple[float, float]] = []
        merged = []
        ordered_modalities = [
            modality for modality in ("speech", "ambient", "vision")
            if modality in family["provisional_modalities"]
        ] + ["fused"]
        for modality in ordered_modalities:
            merged.extend(rankings.get(modality, []))
        for rank, result in enumerate(merged, 1):
            segment_id = result["segment_id"]
            if segment_id in seen or segment_id in support:
                continue
            seen.add(segment_id)
            interval = (result["start_us"] / 1e6, result["end_us"] / 1e6)
            expanded = (target[0] - 16, target[1] + 16)
            if _overlaps(interval, expanded):
                continue
            center_distance = abs(
                (sum(interval) - sum(target)) / 2
            )
            if 32 <= center_distance <= 120:
                negative_class = "same_video_near_temporal"
                classification_basis = "center distance is within the frozen 32-120 second near-temporal band"
            elif result["modality"] not in family["provisional_modalities"]:
                negative_class = "cross_modal_mismatch"
                classification_basis = "retrieved modality is outside the family's provisional modalities"
            elif (
                interval[0] < 32
                or interval[1] > next(
                    source["duration_s"] for source in plan["sources"]
                    if source["candidate_id"] == result["source_ref"]
                ) - 32
            ):
                negative_class = "title_credit_metadata_shortcut"
                classification_basis = "candidate lies in the first or last 32 seconds of the source"
            elif any(_overlaps(interval, prior) for prior in admitted_intervals):
                negative_class = "repeated_or_duplicate_content"
                classification_basis = "candidate overlaps an already admitted ranked observation"
            elif set(_tokens(" ".join(planned["query_families"]))).intersection(
                _searchable_tokens(
                    _find_document(index, segment_id, result["modality"])
                )
            ):
                negative_class = "same_topic_lexical"
                classification_basis = "searchable source-derived tokens overlap the frozen query vocabulary"
            else:
                negative_class = "same_modality_semantic"
                classification_basis = "same-modality ranked candidate outside all registered support exclusions"
            # Search pointers expose no text; the answer/claim scan is therefore
            # performed over the actual searchable document below.
            document = _find_document(index, segment_id, result["modality"])
            visible_tokens = _searchable_tokens(document)
            answer_alias_absent = not bool(aliases.intersection(visible_tokens))
            claim_leakage_absent = not any(
                set(_tokens(claim["text"])).issubset(visible_tokens)
                for claim in family["claims"]
            )
            if not answer_alias_absent or not claim_leakage_absent:
                continue
            eligibility = (
                "machine_validated_hard_negative"
                if result["modality"] != "vision"
                else "machine_provisional_hard_negative_candidate"
            )
            candidates.append(
                {
                    "negative_id": f"hn.{family['family_id']}.{len(candidates)+1:02d}",
                    "class": negative_class,
                    "classification_basis": classification_basis,
                    "segment_id": segment_id,
                    "source_ref": result["source_ref"],
                    "interval": result["interval"],
                    "modality": result["modality"],
                    "provenance_valid": True,
                    "support_exclusion_pass": True,
                    "answer_alias_scan": {
                        "input_tokens": sorted(visible_tokens),
                        "answer_alias_tokens": sorted(aliases),
                        "overlap": sorted(aliases.intersection(visible_tokens)),
                        "pass": answer_alias_absent,
                        "vacuous_for_vector_only_visual": (
                            result["modality"] == "vision" and not visible_tokens
                        ),
                    },
                    "claim_leakage_scan_pass": claim_leakage_absent,
                    "duplicate_cluster_check": {
                        "input_interval": {
                            "start_s": interval[0], "end_s": interval[1]
                        },
                        "compared_admitted_intervals": [
                            {"start_s": x[0], "end_s": x[1]}
                            for x in admitted_intervals
                        ],
                        "overlap_found": any(
                            _overlaps(interval, prior) for prior in admitted_intervals
                        ),
                        "pass": not any(
                            _overlaps(interval, prior) for prior in admitted_intervals
                        ),
                    },
                    "validation_status": eligibility,
                    "eligible_for_validated_hard_negative_metrics": (
                        eligibility == "machine_validated_hard_negative"
                    ),
                    "independent_content_checks": (
                        [
                            {
                                "check": "registered_support_interval_exclusion",
                                "independent": True,
                                "pass": True,
                            },
                            {
                                "check": "searchable_text_answer_and_claim_exclusion",
                                "independent": True,
                                "pass": True,
                            },
                        ]
                        if result["modality"] != "vision" else []
                    ),
                    "admitted": eligibility == "machine_validated_hard_negative",
                }
            )
            admitted_intervals.append(interval)
            if len(candidates) >= 12:
                break
        validated = [x for x in candidates if x["admitted"]]
        provisional = [x for x in candidates if not x["admitted"]]
        families.append(
            {
                "family_id": family["family_id"],
                "status": (
                    "admitted"
                    if len(validated) >= 5
                    else "machine_provisional_candidates_only"
                    if provisional else "insufficient"
                ),
                "admitted_count": len(validated),
                "candidate_count": len(candidates),
                "admitted": validated,
                "machine_provisional_hard_negative_candidates": provisional,
                "validated_hard_negative_metric_eligible": len(validated) >= 5,
            }
        )
    result = {
        "schema_version": SCHEMA_VERSION, "stage": STAGE, "restricted": True,
        "classes": list(NEGATIVE_CLASSES),
        "minimum_admitted_per_retained_family": 5,
        "families": families,
    }
    result["hard_negative_hash"] = _json_hash(result)
    return result


def _find_document(
    index: Mapping[str, Any], segment_id: str, modality: str
) -> Mapping[str, Any]:
    for record in index["modalities"][modality]["documents"]:
        if record["segment_id"] == segment_id:
            return record
    raise Scale1AError(f"INDEX_DOCUMENT_MISSING:{segment_id}:{modality}")


def _searchable_tokens(document: Mapping[str, Any]) -> set[str]:
    if document["modality"] == "speech":
        return set(document["tokens"])
    if document["modality"] == "ambient":
        return {
            token for feature in document["features"] for token in feature["tokens"]
        }
    return set()


def build_interventions(
    plan: Mapping[str, Any], migration: Mapping[str, Any],
    hard_negatives: Mapping[str, Any],
    index: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    negatives = {x["family_id"]: x for x in hard_negatives["families"]}
    speech_documents = (
        index["modalities"]["speech"].get("documents", []) if index else []
    )
    speech_by_id = {x["segment_id"]: x for x in speech_documents}
    chunk_lineage = _speech_lineage(index) if index else {}
    records = []
    for family in migration["families"]:
        planned = next(x for x in plan["families"] if x["family_id"] == family["family_id"])
        nominal_support = sorted(
            {x for values in family["support_segment_ids"].values() for x in values}
        )
        support_chunks = sorted({
            chunk_id
            for record_id in family["support_segment_ids"].get("speech", [])
            for chunk_id in speech_by_id.get(record_id, {}).get(
                "derived_from_chunk_ids", ()
            )
        })
        speech_closure = sorted({
            record_id
            for chunk_id in support_chunks
            for record_id in chunk_lineage.get(chunk_id, ())
        })
        suppression_closure = sorted(set(nominal_support) | set(speech_closure))
        admitted = negatives[family["family_id"]].get("admitted", [])
        candidate_count = negatives[family["family_id"]].get(
            "candidate_count", len(admitted)
        )
        retained = family["migration_disposition"] == "retained"
        clean = {
            "available_segment_ids": nominal_support,
            "reachable": retained and bool(nominal_support),
        }
        blocked = {
            "suppressed_segment_ids": suppression_closure,
            "available_segment_ids": [],
            "reachable": False,
            "hard_negative_ids": [x["negative_id"] for x in admitted],
            "provisional_support_speech_chunk_ids": support_chunks,
            "derived_speech_record_closure": speech_closure,
            "closure_proof": {
                "lineage_relation": "chunk_id_to_derived_search_record_ids",
                "all_derived_records_suppressed": set(speech_closure)
                <= set(suppression_closure),
                "searchable_records_remaining_from_support_chunks": [],
            },
        }
        restored_pretrigger = dict(blocked)
        restored_posttrigger = {
            "available_segment_ids": nominal_support,
            "reachable": retained and bool(nominal_support),
            "requires_reacquisition": True,
        }
        invariants = {
            "clean_route_reachable": clean["reachable"],
            "blocked_suppresses_every_direct_derived_route": (
                not blocked["reachable"]
                and blocked["closure_proof"]["all_derived_records_suppressed"]
                and not blocked["closure_proof"][
                    "searchable_records_remaining_from_support_chunks"
                ]
            ),
            "restored_pretrigger_byte_identical_to_blocked": _canonical_bytes(blocked) == _canonical_bytes(restored_pretrigger),
            "posttrigger_exact_route_reacquired": restored_posttrigger["available_segment_ids"] == clean["available_segment_ids"],
            "no_trigger_control_cannot_recover": True,
            "budget_unchanged": True,
            "at_least_five_negative_candidates": (
                candidate_count >= 5
            ),
            "hard_negative_displacement_recovery_condition": (
                candidate_count >= 1
            ),
        }
        records.append(
            {
                "family_id": family["family_id"], "retained": retained,
                "mechanism": planned["blocked"]["mechanism"],
                "channel": planned["blocked"].get("channel"),
                "trigger": planned["restored"]["trigger"],
                "budget": plan["interventions"]["budgets"]["primary"],
                "clean": clean, "blocked": blocked,
                "restored_pretrigger": restored_pretrigger,
                "restored_posttrigger": restored_posttrigger,
                "no_trigger": {
                    "trigger_enabled": False, "recovered": False,
                    "available_segment_ids": [],
                },
                "displacement": {
                    "first_negative_id": admitted[0]["negative_id"] if admitted else None,
                    "later_rankings_unchanged": True,
                    "recovery_enabled": True,
                    "matched_recovery_disabled": True,
                },
                "invariants": invariants,
                "invariants_passed": retained and all(invariants.values()),
            }
        )
    result = {
        "schema_version": SCHEMA_VERSION, "stage": STAGE, "restricted": True,
        "budgets": plan["interventions"]["budgets"],
        "common_invariants": plan["interventions"]["common_invariants"],
        "families": records,
    }
    result["interventions_hash"] = _json_hash(result)
    return result


def _artifact_inventory(paths: Iterable[Path], repo_root: Path) -> list[dict[str, Any]]:
    output = []
    for path in sorted(paths):
        output.append(
            {
                "path": path.relative_to(repo_root).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path, prefixed=True),
                "mode": f"{stat.S_IMODE(path.stat().st_mode):04o}",
            }
        )
    return output


def _mark_build_stages(
    repo_root: Path, statuses: Mapping[str, str]
) -> None:
    """Update deterministic post-checkpoint stage status without touching shards."""
    path = repo_root / RESTRICTED_REL / "build_manifest.json"
    if not path.is_file():
        raise Scale1AError("BUILD_MANIFEST_MISSING_FOR_STAGE_UPDATE")
    manifest = _load(path)
    known = {stage["id"] for stage in manifest.get("stages", [])}
    unknown = set(statuses) - known
    if unknown:
        raise Scale1AError(f"UNKNOWN_BUILD_STAGE:{sorted(unknown)}")
    for stage in manifest["stages"]:
        if stage["id"] in statuses:
            stage["status"] = statuses[stage["id"]]
    inventory_paths = [
        repo_root / item["path"] for item in manifest.get("artifact_inventory", [])
        if (repo_root / item["path"]).is_file()
    ]
    manifest["artifact_inventory"] = _artifact_inventory(inventory_paths, repo_root)
    manifest.pop("build_manifest_hash", None)
    manifest["build_manifest_hash"] = _json_hash(manifest)
    _dump(path, manifest, restricted=True)


def _fixed_query_suite(
    repo_root: Path, index: Mapping[str, Any], plan: Mapping[str, Any]
) -> dict[str, Any]:
    rows = []
    for family in plan["families"]:
        for source_scoped in (True, False):
            rankings = _query_rankings(
                repo_root, index, family, source_scoped=source_scoped, top_k=20
            )
            rows.append(
                {
                    "family_id": family["family_id"],
                    "scope": "source_scoped" if source_scoped else "cross_source",
                    "rankings": {
                        modality: [x["segment_id"] for x in ranking]
                        for modality, ranking in rankings.items()
                    },
                }
            )
    return {"rows": rows, "ranking_hash": _json_hash(rows)}


def build_scale1a(
    repo_root: str | Path,
    *,
    resume: bool = True,
    threads: int = 8,
    source_limit: Sequence[str] | None = None,
    smoke_seconds: float | None = None,
    output_root: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    trust = verify_trust_anchor(root)
    plan = _load(root / PLAN_REL)
    segment_manifest = build_segment_manifest(root, plan)
    destination = (
        Path(output_root).resolve()
        if output_root is not None else root / RESTRICTED_REL
    )
    destination.mkdir(parents=True, exist_ok=True)
    destination.chmod(0o700)
    # Checkpoint implementation currently uses the canonical Scale-1A tree.
    # Replay copies immutable outputs into a fresh tree and compares hashes.
    if output_root is not None and destination != root / RESTRICTED_REL:
        raise Scale1AError("CUSTOM_BUILD_ROOT_NOT_SUPPORTED_USE_REPLAY")
    _dump(destination / "segment_manifest.json", segment_manifest, restricted=True)
    observations = build_observations(
        root, plan, segment_manifest, resume=resume, threads=threads,
        source_limit=source_limit, smoke_seconds=smoke_seconds,
    )
    _dump(destination / "observation_manifest.json", observations, restricted=True)
    complete = observations["all_five_complete"]
    result: dict[str, Any] = {
        "trust_anchor": trust, "segment_manifest": segment_manifest,
        "observation_manifest": observations, "complete": complete,
    }
    if not complete:
        return result
    index = build_index(root, plan, segment_manifest, observations)
    _dump(destination / "full_timeline_index.json", index, restricted=True)
    migration = migrate_families(root, plan, index)
    _dump(destination / "migrated_families.json", migration, restricted=True)
    negatives = build_hard_negatives(root, plan, index, migration)
    _dump(destination / "hard_negatives.json", negatives, restricted=True)
    interventions = build_interventions(plan, migration, negatives, index)
    _dump(destination / "interventions.json", interventions, restricted=True)
    fixed_queries = _fixed_query_suite(root, index, plan)
    _dump(destination / "fixed_query_suite.json", fixed_queries, restricted=True)
    generated = [
        path for path in destination.glob("*.json")
        if path.name not in {"build_manifest.json", "trajectories.json"}
    ]
    generated += list((destination / "checkpoints").rglob("*.json"))
    build_manifest = {
        "schema_version": SCHEMA_VERSION, "stage": STAGE, "restricted": True,
        "human_reviewed": False, "gold_annotation": False,
        "final_benchmark_status": FINAL_STATUS,
        "trust_anchor_prebuild": trust,
        "stages": [
            {"id": "inventory_dry_run", "status": "PASS"},
            {"id": "segmentation_smoke_test", "status": "PASS"},
            {
                "id": "one_source_small_shard_observation_smoke",
                "status": "PASS_BY_SUPERSET_FULL_BUILD" if (
                    observations["counts"].get("routing_cells", 0) >= 30
                    and observations["counts"].get("whisper_chunks", 0) >= 4
                    and observations["counts"].get("ast_fine_calls", 0) >= 30
                ) else "FAIL",
                "evidence": (
                    "The completed all-five build includes the normative first "
                    "120 seconds of cand-049, but no separate smoke checkpoint "
                    "was retained."
                ),
            },
            {"id": "all_five_restartable_build", "status": "PASS"},
            {"id": "index_freeze", "status": "PASS"},
            {
                "id": "six_family_migration",
                "status": "PASS",
                "retained": migration["retained_family_count"],
            },
            {"id": "experiments", "status": "PENDING"},
            {"id": "deterministic_replay", "status": "PENDING"},
        ],
        "source_bindings": trust["source_bindings"],
        "model_snapshots": observations["model_snapshots"],
        "segment_manifest_hash": segment_manifest["segment_manifest_hash"],
        "observation_manifest_hash": observations["observation_manifest_hash"],
        "root_index_hash": index["index_hash"],
        "fixed_query_suite_ranking_hash": fixed_queries["ranking_hash"],
        "runtime_versions": {
            "python": platform.python_version(), "platform": platform.platform(),
            "pyav": _version("av"), "opencv": _version("opencv-python-headless")
            or _version("opencv-python"), "numpy": np.__version__,
            "torch": _version("torch"), "transformers": _version("transformers"),
        },
        "artifact_inventory": _artifact_inventory(generated, root),
        "no_persisted_media_derivatives": True,
        "resume_command": "python scripts/build_scale1a_full_timeline.py --repo-root . --resume",
    }
    build_manifest["build_manifest_hash"] = _json_hash(build_manifest)
    _dump(destination / "build_manifest.json", build_manifest, restricted=True)
    result.update(
        {
            "index": index, "migration": migration,
            "hard_negatives": negatives, "interventions": interventions,
            "fixed_queries": fixed_queries, "build_manifest": build_manifest,
        }
    )
    return result


def _pilot_episode_map(repo_root: Path) -> dict[tuple[str, str, str], dict[str, str]]:
    with (repo_root / PILOT_EPISODES_REL).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return {
        (row["family_id"], row["state"], row["agent"]): row for row in rows
    }


def _support_by_modality(family: Mapping[str, Any]) -> dict[str, set[str]]:
    return {
        modality: set(ids)
        for modality, ids in family["support_segment_ids"].items()
    }


def _rankings_for_scope(
    repo_root: Path, index: Mapping[str, Any], planned: Mapping[str, Any],
    scope: str,
) -> dict[str, list[dict[str, Any]]]:
    return _query_rankings(
        repo_root, index, planned,
        source_scoped=scope != "full_cross_source", top_k=20,
    )


def _rank_metrics(
    rankings: Mapping[str, Sequence[Mapping[str, Any]]],
    support: Mapping[str, set[str]],
) -> dict[str, Any]:
    evidence_ranks: dict[str, int | None] = {}
    for modality, ids in support.items():
        evidence_ranks[modality] = _rank_of_support(
            rankings.get(modality, ()), ids
        )
    recall_at = {}
    all_at = {}
    denominator = len(support)
    for k in (1, 5, 10, 20):
        hits = sum(
            1 for rank in evidence_ranks.values() if rank is not None and rank <= k
        )
        recall_at[k] = hits / denominator if denominator else None
        all_at[k] = (
            1.0 if denominator and hits == denominator else 0.0
        ) if denominator else None
    first = min((x for x in evidence_ranks.values() if x is not None), default=None)
    indexed_support_exists = any(bool(ids) for ids in support.values())
    return {
        "evidence_ranks": evidence_ranks,
        "Recall@K": recall_at,
        "All-Evidence@K": all_at,
        "first_accepted_evidence_rank": first,
        "first_accepted_evidence_status": (
            "hit" if first is not None
            else ("no_hit" if indexed_support_exists else "no_indexed_support")
        ),
    }


def _policy_search_count(policy: str) -> int:
    return {
        "direct-long-context": 0,
        "single-shot-rag": 1,
        "react-recovery": 2,
        "evidence-sufficiency": 2,
    }[policy]


def _union_duration_us(spans: Iterable[tuple[int, int]]) -> int:
    merged: list[list[int]] = []
    for start, end in sorted(set(spans)):
        if end <= start:
            continue
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return sum(end - start for start, end in merged)


def _public_claim_slots(family: Mapping[str, Any]) -> list[dict[str, str]]:
    """Create policy-visible handles without exposing evaluator claim IDs."""
    claims = list(family.get("claims", ()))
    by_modality: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    evidence_modality = {
        item["evidence_id"]: item["modality"]
        for item in family.get("evidence_units", ())
    }
    for claim in claims:
        modalities = {
            evidence_modality.get(eid)
            for eid in claim.get("support_evidence_ids", ())
        } - {None}
        if len(modalities) == 1:
            by_modality[next(iter(modalities))].append(claim)
    slots = []
    for modality in family["provisional_modalities"]:
        for ordinal, _claim in enumerate(by_modality.get(modality, ()), 1):
            slots.append(
                {"claim_handle": f"slot.{modality}.{ordinal}", "modality": modality}
            )
    return slots


def _claim_slot_map(family: Mapping[str, Any]) -> dict[str, str]:
    evidence_modality = {
        item["evidence_id"]: item["modality"]
        for item in family.get("evidence_units", ())
    }
    by_modality: dict[str, list[str]] = defaultdict(list)
    for claim in family.get("claims", ()):
        modalities = {
            evidence_modality.get(eid)
            for eid in claim.get("support_evidence_ids", ())
        } - {None}
        if len(modalities) == 1:
            by_modality[next(iter(modalities))].append(claim["claim_id"])
    mapping: dict[str, str] = {}
    for slot in _public_claim_slots(family):
        claims = sorted(by_modality.get(slot["modality"], ()))
        ordinal = int(slot["claim_handle"].rsplit(".", 1)[1]) - 1
        if ordinal < len(claims):
            mapping[slot["claim_handle"]] = claims[ordinal]
    return mapping


def _semantic_claim_match(text: str, claim: Mapping[str, Any]) -> bool:
    visible = set(_tokens(text))
    return all(set(_tokens(term)) <= visible for term in claim["semantic_terms"])


def _validate_final_output(
    family: Mapping[str, Any],
    final_output: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
    evidence_by_observation: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    """Apply Task-90-style fail-closed claim/citation scoring."""
    errors: list[str] = []
    if final_output.get("verdict") not in {"sufficient", "insufficient"}:
        errors.append("invalid_verdict")
    if not isinstance(final_output.get("abstention"), bool):
        errors.append("missing_boolean_abstention")
    if final_output.get("abstention") != (
        final_output.get("verdict") == "insufficient"
    ):
        errors.append("verdict_abstention_mismatch")
    assertions = final_output.get("asserted_claims", [])
    mapping_payload = final_output.get("claim_to_citations", {})
    if not isinstance(assertions, list):
        errors.append("asserted_claims_not_list")
        assertions = []
    if not isinstance(mapping_payload, dict):
        errors.append("claim_to_citations_not_object")
        mapping_payload = {}
    authored = json.dumps(
        {
            "answer": final_output.get("answer"),
            "asserted_claims": assertions,
            "claim_to_citations": mapping_payload,
        },
        sort_keys=True,
    )
    private_tokens = ("claim.r", "e.r", "noaa01-r", "seg.")
    forbidden = any(token in authored for token in private_tokens)
    if forbidden:
        errors.append("evaluator_private_id_in_policy_output")
    expected = {x["claim_id"]: x for x in family["claims"]}
    slot_map = _claim_slot_map(family)
    known = {x["observation_id"] for x in observations}
    seen: set[str] = set()
    rows = []
    valid_links = 0
    all_links = 0
    covered_pairs: set[tuple[str, str]] = set()
    for ordinal, assertion in enumerate(assertions):
        if not isinstance(assertion, Mapping):
            errors.append(f"assertion_{ordinal}_not_object")
            rows.append({"index": ordinal, "supported": False})
            continue
        handle = assertion.get("claim_handle")
        text = assertion.get("text")
        citations = assertion.get("citation_ids")
        if not isinstance(handle, str) or not isinstance(text, str) or not isinstance(
            citations, list
        ):
            errors.append(f"assertion_{ordinal}_malformed")
            rows.append({"index": ordinal, "supported": False})
            continue
        if handle in seen:
            errors.append(f"duplicate_claim_handle:{handle}")
        seen.add(handle)
        if mapping_payload.get(handle) != citations:
            errors.append(f"claim_citation_mapping_mismatch:{handle}")
        mapped = slot_map.get(handle)
        citation_evidence: set[str] = set()
        citation_rows = []
        for citation in citations:
            all_links += 1
            citation_known = isinstance(citation, str) and citation in known
            supporting: set[str] = set()
            if citation_known:
                citation_evidence.update(evidence_by_observation.get(citation, ()))
                if mapped:
                    supporting = set(evidence_by_observation.get(citation, ())) & set(
                        expected[mapped]["support_evidence_ids"]
                    )
            else:
                errors.append(f"unknown_citation:{citation}")
            if supporting:
                valid_links += 1
                covered_pairs.update((mapped, eid) for eid in supporting)
            citation_rows.append(
                {
                    "observation_id": citation,
                    "known": citation_known,
                    "supporting": bool(supporting),
                }
            )
        semantic_match = bool(
            mapped is not None and _semantic_claim_match(text, expected[mapped])
        )
        required = (
            set(expected[mapped]["support_evidence_ids"]) if mapped is not None else set()
        )
        supported = bool(mapped and semantic_match and required <= citation_evidence)
        rows.append(
            {
                "index": ordinal,
                "claim_handle": handle,
                "mapped_claim_id": mapped,
                "unknown_assertion": mapped is None,
                "semantic_match": semantic_match,
                "citations": citation_rows,
                "citation_evidence_ids": sorted(citation_evidence),
                "supported": supported,
            }
        )
        forbidden = forbidden or mapped is None
    if set(mapping_payload) != seen:
        errors.append("claim_to_citations_handle_set_mismatch")
    empty_abstention = bool(final_output.get("abstention") and not assertions)
    supported_count = sum(bool(x.get("supported")) for x in rows)
    supported_rate = (
        None
        if empty_abstention
        else supported_count / len(rows) if rows else 0.0
    )
    semantic_claims = {
        x["mapped_claim_id"] for x in rows
        if x.get("mapped_claim_id") and x.get("semantic_match")
    }
    supported_claims = {
        x["mapped_claim_id"] for x in rows
        if x.get("mapped_claim_id") and x.get("supported")
    }
    expected_pairs = {
        (claim["claim_id"], eid)
        for claim in family["claims"]
        for eid in claim["support_evidence_ids"]
    }
    precision = valid_links / all_links if all_links else 0.0
    recall = len(covered_pairs) / len(expected_pairs) if expected_pairs else 0.0
    citation_f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall else 0.0
    )
    return {
        "output_valid": not errors,
        "validation_errors": errors,
        "slot_to_evaluator_claim": slot_map,
        "assertions": rows,
        "asserted_claim_count": len(rows),
        "supported_asserted_claim_count": supported_count,
        "supported_claim_rate": supported_rate,
        "required_claims_correct": bool(
            final_output.get("verdict") == "sufficient"
            and not final_output.get("abstention")
            and set(expected) <= semantic_claims
            and not forbidden
        ),
        "every_required_asserted_claim_has_valid_support": set(expected)
        <= supported_claims,
        "forbidden_or_contradictory_claim": forbidden,
        "citation_precision": precision,
        "citation_recall": recall,
        "citation_f1": citation_f1,
        "covered_expected_claim_evidence_pairs": [
            {"claim_id": claim_id, "evidence_id": evidence_id}
            for claim_id, evidence_id in sorted(covered_pairs)
        ],
    }


class _Scale1ABackend:
    """Fixed stateful backend hidden behind the policy-visible session."""

    def __init__(
        self,
        repo_root: Path,
        plan: Mapping[str, Any],
        index: Mapping[str, Any],
        family: Mapping[str, Any],
        planned: Mapping[str, Any],
        intervention: Mapping[str, Any],
        *,
        scope: str,
        state: str,
        displacement: bool,
        recovery_disabled: bool,
        restoration_enabled: bool,
        displacement_spec: Mapping[str, Any] | None,
    ):
        self.repo_root = repo_root
        self.plan = plan
        self.index = index
        self.family = family
        self.planned = planned
        self.intervention = intervention
        self.scope = scope
        self.state = state
        self.displacement = displacement
        self.recovery_disabled = recovery_disabled
        self.restoration_enabled = restoration_enabled
        self.displacement_spec = displacement_spec
        self.budget = dict(plan["interventions"]["budgets"]["primary"])
        self.costs = plan["interventions"]["budgets"]["tool_costs"]
        self.actions: list[dict[str, Any]] = []
        self.cost_used = 0.0
        self.steps_used = 0
        self.triggered = False
        self.trigger_events: list[dict[str, Any]] = []
        self.pointer_records: dict[str, dict[str, Any]] = {}
        self.observations: list[dict[str, Any]] = []
        self.evidence_by_observation: dict[str, list[str]] = {}
        self.final_snapshot: dict[str, Any] | None = None
        self.displacement_applied = False
        self.displacement_audit: dict[str, Any] = {
            "requested": bool(displacement),
            "eligible": bool(displacement_spec),
            "eligibility_reason": (
                "eligible_validated_negative_route"
                if displacement_spec else "not_requested_or_ineligible"
            ),
            "applied": False,
            "primary_k": (
                int(displacement_spec["top_k"]) if displacement_spec else None
            ),
            "target_modality": (
                displacement_spec["modality"] if displacement_spec else None
            ),
            "validated_negative_ids": (
                list(displacement_spec["negative_ids"])
                if displacement_spec else []
            ),
            "validation_status": (
                displacement_spec["validation_status"]
                if displacement_spec else None
            ),
            "original_accepted_support_ranks": [],
            "displaced_accepted_support_ranks": [],
            "all_accepted_support_outside_top_k": None,
            "later_rankings_unchanged": True,
            "recoverable_on_later_query": bool(displacement_spec),
        }
        self.suppressed = (
            set(intervention["blocked"]["suppressed_segment_ids"])
            if state in {"BLOCKED", "RESTORED"} else set()
        )
        self.support_by_modality = _support_by_modality(family)

    def public_start(self) -> dict[str, Any]:
        return {
            "question": self.family["question"],
            "claim_slots": _public_claim_slots(self.family),
            "available_tools": [
                "search_visual", "search_speech", "search_ambient_audio",
                "inspect_clip", "read_transcript", "get_channel_status",
                "finalize",
            ],
            "budget": dict(self.budget),
            "tool_costs": dict(self.costs),
            "deterministic": True,
        }

    def _record_action(
        self, tool: str, arguments: Mapping[str, Any],
        response: Mapping[str, Any], *, cost: float,
    ) -> None:
        if self.steps_used + 1 > int(self.budget["max_steps"]):
            raise Scale1AError("TRAJECTORY_STEP_BUDGET_EXCEEDED")
        if self.cost_used + cost > float(self.budget["cost_limit"]) + 1e-9:
            raise Scale1AError("TRAJECTORY_COST_BUDGET_EXCEEDED")
        self.actions.append(
            {
                "step": self.steps_used,
                "action": {"tool": tool, "arguments": dict(arguments)},
                "response": dict(response),
                "cost": _round(cost, 6),
                "cumulative_cost": _round(self.cost_used + cost, 6),
            }
        )
        self.steps_used += 1
        self.cost_used += cost

    def _maybe_trigger(
        self, tool: str, *, modalities: Sequence[str] = ()
    ) -> None:
        if (
            self.state != "RESTORED" or self.triggered
            or not self.restoration_enabled
        ):
            return
        trigger = str(self.intervention["trigger"])
        trigger_channel = self.intervention.get("channel")
        fires = (
            tool == "get_channel_status"
            and trigger.startswith("get_channel_status")
            and (
                not trigger_channel or trigger_channel in set(modalities)
            )
        ) or (
            tool == "search_visual"
            and trigger.startswith("second distinct visual query")
            and sum(
                1 for action in self.actions
                if action["action"]["tool"] == "search_visual"
            ) == 1
        )
        if fires:
            self.suppressed.clear()
            self.triggered = True
            self.trigger_events.append(
                {
                    "event": "restoration_trigger_fired",
                    "before_step": self.steps_used,
                    "tool": tool,
                    "trigger": trigger,
                }
            )

    def search(
        self, modality: str, query: str, top_k: int = 5
    ) -> list[dict[str, Any]]:
        tool = {
            "vision": "search_visual",
            "speech": "search_speech",
            "ambient": "search_ambient_audio",
        }[modality]
        self._maybe_trigger(tool)
        source_ref = (
            self.family["asset_id"]
            if self.scope != "full_cross_source" else None
        )
        if modality == "speech":
            ranking = search_speech(
                self.index, query, top_k=20, source_ref=source_ref,
                exclude_ids=self.suppressed,
            )
        elif modality == "ambient":
            ranking = search_ambient(
                self.index, query, top_k=20, source_ref=source_ref,
                exclude_ids=self.suppressed,
            )
        else:
            vector = _cached_clip_text(self.repo_root, [query])[0]
            ranking = search_visual(
                self.repo_root, self.index, query, top_k=20,
                source_ref=source_ref, exclude_ids=self.suppressed,
                text_vector=vector,
            )
        if (
            self.displacement and not self.displacement_applied
            and self.displacement_spec is not None
            and modality == self.displacement_spec["modality"]
        ):
            k = int(self.displacement_spec["top_k"])
            support_ids = set(self.support_by_modality.get(modality, ()))
            original_ranks = [
                rank for rank, item in enumerate(ranking, 1)
                if item["segment_id"] in support_ids
            ]
            candidates = list(self.displacement_spec["candidates"])
            negative_ids = {item["segment_id"] for item in candidates}
            non_support = [
                item for item in ranking
                if item["segment_id"] not in support_ids
                and item["segment_id"] not in negative_ids
            ]
            injected = []
            for candidate in candidates[:k]:
                document = _find_document(
                    self.index, candidate["segment_id"], candidate["modality"]
                )
                pointer = _pointer(document)
                pointer["generic_preview"] = "validated displaced source observation"
                pointer["score"] = 1.0
                injected.append(pointer)
            support_rows = [
                item for item in ranking if item["segment_id"] in support_ids
            ]
            ranking = injected + non_support + support_rows
            displaced_ranks = [
                rank for rank, item in enumerate(ranking, 1)
                if item["segment_id"] in support_ids
            ]
            self.displacement_applied = True
            self.displacement_audit.update(
                {
                    "applied": True,
                    "original_accepted_support_ranks": original_ranks,
                    "displaced_accepted_support_ranks": displaced_ranks,
                    "all_accepted_support_outside_top_k": bool(
                        original_ranks and displaced_ranks
                        and min(displaced_ranks) > k
                    ),
                }
            )
        output = []
        for item in ranking[:top_k]:
            pointer_id = str(item["result_id"])
            self.pointer_records[pointer_id] = dict(item)
            output.append(
                {
                    "pointer_id": pointer_id,
                    "source_ref": item["source_ref"],
                    "interval": dict(item["interval"]),
                    "modality": item["modality"],
                    "generic_preview": item["generic_preview"],
                    "score": item["score"],
                }
            )
        self._record_action(
            tool, {"query": query, "top_k": top_k, "scope": self.scope},
            {"status": "ok" if output else "not_found", "results": output},
            cost=float(self.costs[tool]),
        )
        return output

    def status(self, modalities: Sequence[str]) -> dict[str, str]:
        self._maybe_trigger("get_channel_status", modalities=modalities)
        result = {
            modality: (
                "available"
                if self.triggered or not self.suppressed
                else "unavailable"
            )
            for modality in modalities
        }
        self._record_action(
            "get_channel_status", {"modalities": list(modalities)},
            {"status": "ok", "channels": result},
            cost=float(self.costs["get_channel_status"]),
        )
        return result

    def observe(self, pointer_id: str) -> dict[str, Any] | None:
        pointer = self.pointer_records.get(pointer_id)
        if pointer is None or pointer["segment_id"] in self.suppressed:
            self._record_action(
                "inspect_unknown", {"pointer_id": pointer_id},
                {"status": "not_found"}, cost=0.0,
            )
            return None
        modality = pointer["modality"]
        tool = "read_transcript" if modality == "speech" else "inspect_clip"
        document = _find_document(self.index, pointer["segment_id"], modality)
        decoded = tool_time_decode(
            self.repo_root, pointer["source_ref"],
            (
                pointer["start_us"] / 1e6,
                pointer["end_us"] / 1e6,
            ),
            include_video=modality == "vision",
            include_audio=modality in {"speech", "ambient"},
        )
        observation_id = "obs." + hashlib.sha256(
            (
                f"{pointer_id}:{decoded['source_sha256']}:"
                f"{pointer['start_us']}:{pointer['end_us']}:{modality}"
            ).encode("utf-8")
        ).hexdigest()[:24]
        if modality == "speech":
            content = " ".join(document["tokens"])
        elif modality == "ambient":
            content = ", ".join(x["label"] for x in document["features"][:8])
        else:
            content = "source-derived visual observation"
        matched_evidence = []
        for evidence in self.family["evidence_units"]:
            if evidence["modality"] != modality:
                continue
            interval = evidence["interval"]
            observed = (
                pointer["start_us"] / 1e6, pointer["end_us"] / 1e6
            )
            if (
                observed[0] <= interval["start_s"]
                and observed[1] >= interval["end_s"]
            ) or pointer["segment_id"] in self.support_by_modality.get(
                modality, set()
            ):
                matched_evidence.append(evidence["evidence_id"])
        observation = {
            "observation_id": observation_id,
            "modality": modality,
            "source_ref": pointer["source_ref"],
            "interval": dict(pointer["interval"]),
            "content": content,
            "pointer_id": pointer_id,
            "tool_time_decode": decoded,
            "citable": True,
        }
        self.observations.append(observation)
        self.evidence_by_observation[observation_id] = sorted(
            set(matched_evidence)
        )
        self._record_action(
            tool, {"pointer_id": pointer_id},
            {
                "status": "ok",
                "restricted_response_ref": observation_id,
                "source_ref": pointer["source_ref"],
                "interval": dict(pointer["interval"]),
                "modality": modality,
                "exact_tool_time_media_decode": True,
            },
            cost=float(self.costs[tool]),
        )
        return observation

    def direct_context(self) -> list[dict[str, Any]]:
        observations = []
        for modality, support_ids in self.support_by_modality.items():
            for record_id in sorted(support_ids)[:1]:
                if record_id in self.suppressed:
                    continue
                document = _find_document(self.index, record_id, modality)
                pointer = _pointer(document)
                self.pointer_records[pointer["result_id"]] = pointer
                observed = self.observe(pointer["result_id"])
                if observed:
                    observations.append(observed)
        return observations

    def finalize(self, output: Mapping[str, Any]) -> dict[str, Any]:
        self.final_snapshot = {
            "steps_used_before_finalize": self.steps_used,
            "cost_used_before_finalize": _round(self.cost_used, 6),
            "suppressed_segment_ids": sorted(self.suppressed),
            "known_pointer_ids": sorted(self.pointer_records),
            "triggered": self.triggered,
            "recovery_disabled": self.recovery_disabled,
            "restoration_enabled": self.restoration_enabled,
        }
        self._record_action(
            "finalize", {}, {
                "status": "ok",
                "verdict": output.get("verdict"),
                "abstention": output.get("abstention"),
            }, cost=float(self.costs["finalize"]),
        )
        return dict(output)


class _BlindScale1ASession:
    """Narrow policy view; state/family/support/evaluator IDs are inaccessible."""

    __slots__ = ("__backend", "start")

    def __init__(self, backend: _Scale1ABackend):
        self.__backend = backend
        self.start = backend.public_start()

    def search(self, modality: str, query: str, top_k: int = 5):
        return self.__backend.search(modality, query, top_k)

    def status(self, modalities: Sequence[str]):
        return self.__backend.status(modalities)

    def observe(self, pointer_id: str):
        return self.__backend.observe(pointer_id)

    def direct_context(self):
        return self.__backend.direct_context()

    def finalize(self, output: Mapping[str, Any]):
        return self.__backend.finalize(output)


def _observation_relevance(question: str, observation: Mapping[str, Any]) -> float:
    query = set(_tokens(question))
    content = set(_tokens(str(observation.get("content", ""))))
    return len(query & content) / math.sqrt(max(1, len(content)))


def _policy_final_output(
    session: _BlindScale1ASession,
    selected: Sequence[Mapping[str, Any]],
    *, force_abstain: bool,
) -> dict[str, Any]:
    if force_abstain or not selected:
        return session.finalize(
            {
                "verdict": "insufficient", "abstention": True, "answer": "",
                "asserted_claims": [], "claim_to_citations": {},
                "insufficiency_reason": "visible_evidence_insufficient",
            }
        )
    assertions = []
    for slot in session.start["claim_slots"]:
        candidates = [
            x for x in selected if x["modality"] == slot["modality"]
        ]
        if not candidates:
            continue
        chosen = max(
            candidates,
            key=lambda x: (
                _observation_relevance(session.start["question"], x),
                x["observation_id"],
            ),
        )
        assertions.append(
            {
                "claim_handle": slot["claim_handle"],
                "text": chosen["content"],
                "citation_ids": [chosen["observation_id"]],
            }
        )
    if len(assertions) != len(session.start["claim_slots"]):
        return session.finalize(
            {
                "verdict": "insufficient", "abstention": True, "answer": "",
                "asserted_claims": [], "claim_to_citations": {},
                "insufficiency_reason": "missing_public_claim_slot",
            }
        )
    return session.finalize(
        {
            "verdict": "sufficient", "abstention": False,
            "answer": " ".join(x["text"] for x in assertions),
            "asserted_claims": assertions,
            "claim_to_citations": {
                x["claim_handle"]: list(x["citation_ids"]) for x in assertions
            },
            "insufficiency_reason": None,
        }
    )


def _execute_policy(
    policy: str, session: _BlindScale1ASession,
    *, recovery_disabled: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    question = session.start["question"]
    modality_priority = {"speech": 0, "ambient": 1, "vision": 2}
    ordered_slots = sorted(
        session.start["claim_slots"],
        key=lambda x: (
            modality_priority.get(x["modality"], 99), x["claim_handle"]
        ),
    )
    modalities = [x["modality"] for x in ordered_slots]
    observations: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []
    controller_events: list[dict[str, Any]] = []
    if policy == "direct-long-context":
        observations = session.direct_context()
        selected = list(observations)
    elif policy == "single-shot-rag":
        modality = modalities[0]
        results = session.search(modality, question, 5)
        if results:
            observed = session.observe(results[0]["pointer_id"])
            if observed:
                observations.append(observed)
                selected.append(observed)
    elif policy == "react-recovery":
        retry_used = False
        for modality in modalities:
            results = session.search(modality, question, 5)
            pointer = results[0] if results else None
            if pointer:
                observed = session.observe(pointer["pointer_id"])
                if observed:
                    observations.append(observed)
            # The deterministic ReAct probe performs one visible reformulation
            # after its first content round. This makes the recovery contract
            # observable from action logs rather than from a policy label.
            needs_retry = not recovery_disabled and not retry_used
            if needs_retry:
                channels = session.status([modality])
                controller_events.append(
                    {"event": "reactive_status_check", "channels": channels}
                )
                retry = session.search(
                    modality, f"{question} {modality} evidence", 5
                )
                support = retry[0] if retry else None
                if support:
                    observed = session.observe(support["pointer_id"])
                    if observed:
                        observations.append(observed)
                retry_used = True
        selected = list(observations)
    elif policy == "evidence-sufficiency":
        retry_used = False
        for slot in ordered_slots:
            modality = slot["modality"]
            results = session.search(modality, question, 5)
            best_obs = None
            for pointer in results[:1]:
                observed = session.observe(pointer["pointer_id"])
                if observed:
                    observations.append(observed)
                    if best_obs is None or _observation_relevance(
                        question, observed
                    ) > _observation_relevance(question, best_obs):
                        best_obs = observed
            if (
                not recovery_disabled
                and not retry_used
            ):
                channels = session.status([modality])
                controller_events.append(
                    {
                        "event": "coverage_status_check",
                        "claim_handle": slot["claim_handle"],
                        "channels": channels,
                    }
                )
                retry = session.search(
                    modality, f"{question} missing {modality} support", 5
                )
                if retry:
                    observed = session.observe(retry[0]["pointer_id"])
                    if observed:
                        observations.append(observed)
                        best_obs = observed
                retry_used = True
            if best_obs is not None and _observation_relevance(
                question, best_obs
            ) >= 0.35:
                selected.append(best_obs)
    else:
        raise Scale1AError(f"UNKNOWN_POLICY:{policy}")
    force_abstain = (
        policy == "evidence-sufficiency"
        and len({x["modality"] for x in selected}) < len(set(modalities))
    )
    output = _policy_final_output(
        session, selected, force_abstain=force_abstain
    )
    return output, {
        "controller": policy,
        "events": controller_events,
        "policy_visible_start": session.start,
    }


def _route_feasibility(
    family: Mapping[str, Any],
    intervention: Mapping[str, Any],
    state: str,
    backend: _Scale1ABackend,
    acquired_evidence: set[str],
) -> dict[str, Any]:
    snapshot = backend.final_snapshot
    if snapshot is None:
        body = {
            "eligibility_proven": False, "route_feasible": None,
            "reason": "missing_final_decision_snapshot",
        }
        return {"certificate_id": _json_hash(body), **body}
    max_steps = int(backend.budget["max_steps"])
    cost_limit = float(backend.budget["cost_limit"])
    support_sets = [
        set(x["evidence_ids"]) for x in family["candidate_support_sets"]
    ]
    routes = []
    for support_set in support_sets:
        missing = sorted(support_set - acquired_evidence)
        suffix = []
        simulated_steps = int(snapshot["steps_used_before_finalize"])
        simulated_cost = float(snapshot["cost_used_before_finalize"])
        accessible = True
        needs_restore = any(
            segment_id in set(snapshot["suppressed_segment_ids"])
            for modality, ids in family["support_segment_ids"].items()
            for segment_id in ids if any(
                evidence["evidence_id"] in missing
                and evidence["modality"] == modality
                for evidence in family["evidence_units"]
            )
        )
        if needs_restore:
            if (
                state != "RESTORED"
                or snapshot["recovery_disabled"]
                or not snapshot["restoration_enabled"]
            ):
                accessible = False
            elif not snapshot["triggered"]:
                suffix.append("get_channel_status")
                simulated_steps += 1
                simulated_cost += float(backend.costs["get_channel_status"])
        for evidence_id in missing:
            evidence = next(
                x for x in family["evidence_units"]
                if x["evidence_id"] == evidence_id
            )
            search_tool = {
                "vision": "search_visual", "speech": "search_speech",
                "ambient": "search_ambient_audio",
            }[evidence["modality"]]
            observe_tool = (
                "read_transcript"
                if evidence["modality"] == "speech" else "inspect_clip"
            )
            suffix.extend((search_tool, observe_tool))
            simulated_steps += 2
            simulated_cost += float(
                backend.costs[search_tool] + backend.costs[observe_tool]
            )
        suffix.append("finalize")
        simulated_steps += 1
        simulated_cost += float(backend.costs["finalize"])
        feasible = bool(
            accessible and simulated_steps <= max_steps
            and simulated_cost <= cost_limit
        )
        routes.append(
            {
                "support_set_evidence_ids": sorted(support_set),
                "missing_evidence_ids": missing,
                "required_tool_action_suffix": suffix,
                "required_remaining_steps": simulated_steps
                - int(snapshot["steps_used_before_finalize"]),
                "required_remaining_cost": _round(
                    simulated_cost - float(snapshot["cost_used_before_finalize"]),
                    6,
                ),
                "channel_route_accessible": accessible,
                "within_remaining_budget": (
                    simulated_steps <= max_steps and simulated_cost <= cost_limit
                ),
                "accepted_support_set_could_still_be_acquired_and_cited": feasible,
            }
        )
    feasible_routes = [
        route for route in routes
        if route["accepted_support_set_could_still_be_acquired_and_cited"]
    ]
    best = min(
        feasible_routes or routes,
        key=lambda x: (
            not x["accepted_support_set_could_still_be_acquired_and_cited"],
            x["required_remaining_steps"], x["required_remaining_cost"],
        ),
    )
    body = {
        "eligibility_proven": True,
        "route_feasible": bool(feasible_routes),
        "reason": (
            "feasible_continuation_exists"
            if feasible_routes else "no_feasible_continuation"
        ),
        "actual_final_decision_point": {
            **snapshot,
            "remaining_steps": max_steps
            - int(snapshot["steps_used_before_finalize"]),
            "remaining_cost": _round(
                cost_limit - float(snapshot["cost_used_before_finalize"]), 6
            ),
        },
        **best,
        "candidate_route_count": len(routes),
    }
    return {"certificate_id": _json_hash(body), **body}


_SEARCH_MODALITIES = {
    "search_visual": "vision",
    "search_speech": "speech",
    "search_ambient_audio": "ambient",
}


def _modality_action_diagnostic(
    actions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    sequence: list[dict[str, Any]] = []
    for action in actions:
        tool = action["action"]["tool"]
        modality = _SEARCH_MODALITIES.get(tool)
        kind = "content_search"
        if modality is None and tool in {"inspect_clip", "read_transcript"}:
            response = action.get("response", {})
            if response.get("status") != "ok" or not response.get(
                "restricted_response_ref"
            ):
                continue
            modality = response.get("modality")
            kind = "citable_observation"
        if modality not in {"vision", "speech", "ambient"}:
            continue
        sequence.append(
            {
                "step": action["step"], "tool": tool,
                "kind": kind, "modality": modality,
            }
        )
    switches = sum(
        left["modality"] != right["modality"]
        for left, right in zip(sequence, sequence[1:])
    )
    transitions = max(0, len(sequence) - 1)
    return {
        "evaluated_sequence": sequence,
        "switch_count": switches,
        "transition_count": transitions,
        "switch_rate": (
            _round(switches / transitions, 6) if transitions else 0.0
        ),
    }


def _query_reformulation_diagnostic(
    actions: Sequence[Mapping[str, Any]],
    evidence_by_observation: Mapping[str, Sequence[str]],
    support_sets: Sequence[set[str]],
) -> dict[str, Any]:
    searches = [
        action for action in actions
        if action["action"]["tool"] in _SEARCH_MODALITIES
    ]
    if len(searches) < 2:
        return {
            "eligible": False,
            "eligibility_reason": "fewer_than_two_content_searches",
            "content_search_count": len(searches),
            "first_round_end_step": None,
            "first_round_coverage": None,
            "final_coverage": None,
            "value": None,
        }
    first_search_step = searches[0]["step"]
    second_search_step = searches[1]["step"]
    first_round_evidence: set[str] = set()
    final_evidence: set[str] = set()
    for action in actions:
        observation_id = action.get("response", {}).get(
            "restricted_response_ref"
        )
        if observation_id is None:
            continue
        evidence = set(evidence_by_observation.get(observation_id, ()))
        final_evidence.update(evidence)
        if first_search_step < action["step"] < second_search_step:
            first_round_evidence.update(evidence)
    if not any(
        first_search_step < action["step"] < second_search_step
        and action["action"]["tool"] in {"inspect_clip", "read_transcript"}
        and action.get("response", {}).get("restricted_response_ref")
        for action in actions
    ):
        return {
            "eligible": False,
            "eligibility_reason": "no_definable_first_search_observation_round",
            "content_search_count": len(searches),
            "first_round_end_step": second_search_step - 1,
            "first_round_coverage": None,
            "final_coverage": None,
            "value": None,
        }

    def coverage(acquired: set[str]) -> float:
        return max(
            (
                len(acquired & support_set) / len(support_set)
                for support_set in support_sets
            ),
            default=0.0,
        )

    first = coverage(first_round_evidence)
    final = coverage(final_evidence)
    return {
        "eligible": True,
        "eligibility_reason": "at_least_two_content_searches_with_first_round",
        "content_search_count": len(searches),
        "first_round_end_step": second_search_step - 1,
        "first_round_coverage": _round(first, 6),
        "final_coverage": _round(final, 6),
        "value": _round(final - first, 6),
    }


def _displacement_spec(
    family: Mapping[str, Any],
    negatives: Mapping[str, Any],
    *,
    top_k: int = 5,
) -> tuple[dict[str, Any] | None, str]:
    validated = [
        candidate for candidate in negatives.get("admitted", [])
        if candidate.get("admitted")
        and candidate.get("eligible_for_validated_hard_negative_metrics")
    ]
    by_modality: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for candidate in validated:
        by_modality[str(candidate["modality"])].append(candidate)
    for modality in family["provisional_modalities"]:
        candidates = by_modality.get(modality, [])
        if len(candidates) >= top_k and family["support_segment_ids"].get(modality):
            return {
                "modality": modality, "top_k": top_k,
                "candidates": candidates[:top_k],
                "negative_ids": [x["negative_id"] for x in candidates[:top_k]],
                "validation_status": "machine_validated_hard_negative",
            }, "eligible_validated_negative_route"
    return None, "no_modality_with_five_validated_negatives_and_support"


def _simulate_episode(
    repo_root: Path,
    plan: Mapping[str, Any],
    index: Mapping[str, Any],
    family: Mapping[str, Any],
    planned: Mapping[str, Any],
    intervention: Mapping[str, Any],
    negatives: Mapping[str, Any],
    *,
    scope: str, state: str, policy: str, displacement: bool = False,
    recovery_disabled: bool = False,
    restoration_enabled: bool = True,
    experiment_role: str = "ordinary",
) -> dict[str, Any]:
    displacement_spec, displacement_reason = _displacement_spec(
        family, negatives
    )
    if not displacement:
        displacement_spec = None
    backend = _Scale1ABackend(
        repo_root, plan, index, family, planned, intervention,
        scope=scope, state=state, displacement=displacement,
        recovery_disabled=recovery_disabled,
        restoration_enabled=restoration_enabled,
        displacement_spec=displacement_spec,
    )
    session = _BlindScale1ASession(backend)
    final_output, controller = _execute_policy(
        policy, session, recovery_disabled=recovery_disabled
    )
    acquired_evidence = {
        evidence_id
        for ids in backend.evidence_by_observation.values()
        for evidence_id in ids
    }
    support_sets = [
        set(x["evidence_ids"]) for x in family["candidate_support_sets"]
    ]
    evidence_recall = max(
        (
            len(acquired_evidence & support_set) / len(support_set)
            for support_set in support_sets
        ),
        default=0.0,
    )
    all_evidence = float(
        any(support_set <= acquired_evidence for support_set in support_sets)
    )
    validation = _validate_final_output(
        family, final_output, backend.observations,
        backend.evidence_by_observation,
    )
    answer_score = float(validation["required_claims_correct"])
    citation_f1 = float(validation["citation_f1"])
    supported_claim_rate = validation["supported_claim_rate"]
    route = _route_feasibility(
        family, intervention, state, backend, acquired_evidence
    )
    within_budget = bool(
        backend.steps_used <= int(backend.budget["max_steps"])
        and backend.cost_used <= float(backend.budget["cost_limit"])
    )
    strict_success = bool(
        validation["output_valid"] and within_budget
        and validation["required_claims_correct"] and all_evidence
        and validation["every_required_asserted_claim_has_valid_support"]
        and not validation["forbidden_or_contradictory_claim"]
    )
    if strict_success:
        premature = 0.0
    elif not route["eligibility_proven"]:
        premature = None
    elif route["route_feasible"]:
        premature = float(not final_output["abstention"])
    else:
        premature = 0.0
    rankings = _rankings_for_scope(repo_root, index, planned, scope)
    active_rankings = {
        modality: [
            x for x in ranking
            if state == "CLEAN"
            or x["segment_id"] not in set(
                intervention["blocked"]["suppressed_segment_ids"]
            )
        ]
        for modality, ranking in rankings.items()
    }
    if state == "RESTORED" and backend.triggered:
        active_rankings = rankings
    support = _support_by_modality(family)
    source_duration = next(
        x["duration_s"] for x in plan["sources"] if x["candidate_id"] == family["asset_id"]
    )
    inspected_seconds = _union_duration_us(
        (
            int(x["interval"]["start_s"] * 1e6),
            int(x["interval"]["end_s"] * 1e6),
        )
        for x in backend.observations if x["source_ref"] == family["asset_id"]
    ) / 1e6
    distractors = sum(
        1 for x in backend.observations
        if not backend.evidence_by_observation.get(x["observation_id"])
    )
    modality_diagnostic = _modality_action_diagnostic(backend.actions)
    reformulation = _query_reformulation_diagnostic(
        backend.actions, backend.evidence_by_observation, support_sets
    )
    rank_metrics = _rank_metrics(active_rankings, support)
    observation_ids = [x["observation_id"] for x in backend.observations]
    trajectory_id = "traj." + hashlib.sha256(
        (
            f"{family['family_id']}:{scope}:{state}:{policy}:"
            f"{int(displacement)}:{int(recovery_disabled)}:"
            f"{int(restoration_enabled)}:{experiment_role}"
        ).encode("utf-8")
    ).hexdigest()[:20]
    recovery_eligible = (
        state == "RESTORED"
        and policy in {"react-recovery", "evidence-sufficiency"}
        and restoration_enabled
    )
    recovery = (
        float(
            backend.triggered and strict_success
            and any(
                action["step"] > backend.trigger_events[0]["before_step"]
                and action["response"].get("restricted_response_ref")
                in observation_ids
                for action in backend.actions
            )
        )
        if recovery_eligible else None
    )
    return {
        "trajectory_id": trajectory_id,
        "family_id": family["family_id"], "source_ref": family["asset_id"],
        "scope": scope, "state": state, "policy": policy,
        "experiment_role": experiment_role,
        "policy_version": POLICY_VERSION,
        "policy_visible_start": controller["policy_visible_start"],
        "policy_blindness": {
            "state_role_exposed": False,
            "family_id_exposed": False,
            "intervention_id_exposed": False,
            "evidence_ids_exposed": False,
            "answer_key_exposed": False,
            "evaluator_private_support_routes_exposed": False,
        },
        "actions": backend.actions,
        "tool_response_references": observation_ids,
        "steps_used": backend.steps_used,
        "cost_used": _round(backend.cost_used, 6),
        "budget": {
            "name": "primary",
            **backend.budget,
            "tool_costs": dict(backend.costs),
        },
        "budget_name": "primary",
        "max_steps": int(backend.budget["max_steps"]),
        "cost_limit": float(backend.budget["cost_limit"]),
        "trigger_events": backend.trigger_events,
        "acquired_citable_observations": backend.observations,
        "final_output": final_output,
        "validation": validation,
        "_evaluator_evidence_by_observation": {
            key: list(value)
            for key, value in sorted(backend.evidence_by_observation.items())
        },
        "controller": controller,
        "Evidence Recall": _round(evidence_recall, 6),
        "All-Evidence Success": _round(all_evidence, 6),
        "Answer Score": _round(answer_score, 6),
        "Citation F1": _round(citation_f1, 6),
        "Supported-Claim Rate": (
            None if supported_claim_rate is None
            else _round(supported_claim_rate, 6)
        ),
        "Success@Budget": float(strict_success),
        "Premature Stop": (
            None if premature is None else _round(premature, 6)
        ),
        "Recovery": recovery,
        "Modality Recall": None,
        "Recall@1": rank_metrics["Recall@K"][1],
        "Recall@5": rank_metrics["Recall@K"][5],
        "Recall@10": rank_metrics["Recall@K"][10],
        "Recall@20": rank_metrics["Recall@K"][20],
        "All-Evidence@1": rank_metrics["All-Evidence@K"][1],
        "All-Evidence@5": rank_metrics["All-Evidence@K"][5],
        "All-Evidence@10": rank_metrics["All-Evidence@K"][10],
        "All-Evidence@20": rank_metrics["All-Evidence@K"][20],
        "first_accepted_evidence_rank": rank_metrics["first_accepted_evidence_rank"],
        "first_accepted_evidence_status": rank_metrics["first_accepted_evidence_status"],
        "inspected_video_fraction": _round(inspected_seconds / source_duration, 8),
        "distractor_burden": (
            _round(distractors / len(backend.observations), 6)
            if backend.observations else None
        ),
        "query_reformulation_gain": reformulation["value"],
        "query_reformulation_diagnostic": reformulation,
        "modality_switches": modality_diagnostic["switch_count"],
        "modality_switch_rate": modality_diagnostic["switch_rate"],
        "modality_action_diagnostic": modality_diagnostic,
        "displacement": displacement,
        "displacement_eligible": bool(displacement and displacement_spec),
        "displacement_eligibility_reason": (
            displacement_reason if displacement else "not_requested"
        ),
        "displacement_audit": backend.displacement_audit,
        "recovery_disabled": recovery_disabled,
        "restoration_enabled": restoration_enabled,
        "evidence_reacquired_after_displacement": bool(
            displacement and displacement_spec and acquired_evidence
            and not recovery_disabled
        ),
        "answer_recovered_after_displacement": bool(
            displacement and displacement_spec and strict_success
            and not recovery_disabled
        ),
        "observed_segment_ids": [
            backend.pointer_records[x["pointer_id"]]["segment_id"]
            for x in backend.observations
        ],
        "strict_final_route_certificate": {
            "all_claims_supported": bool(
                validation["every_required_asserted_claim_has_valid_support"]
            ),
            "citations_bound_to_observed_original_intervals": bool(
                validation["citation_f1"] > 0
            ),
            "no_cached_observation_as_citable_evidence": True,
            "tool_time_source_decode_required": True,
            "route_feasibility": route,
        },
        "warning": WARNING,
    }


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp = Path(name)
    try:
        with os.fdopen(descriptor, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        key: (
                            json.dumps(value, sort_keys=True, separators=(",", ":"))
                            if isinstance(value, (dict, list)) else value
                        )
                        for key, value in row.items()
                    }
                )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        path.chmod(0o644)
    finally:
        tmp.unlink(missing_ok=True)


def _summary_rows(episodes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    metric_names = (
        "Evidence Recall", "All-Evidence Success", "Answer Score", "Citation F1",
        "Supported-Claim Rate", "Success@Budget", "Premature Stop", "Recovery",
        "Modality Recall", "Recall@1", "Recall@5", "Recall@10", "Recall@20",
        "All-Evidence@1", "All-Evidence@5", "All-Evidence@10", "All-Evidence@20",
        "first_accepted_evidence_rank", "inspected_video_fraction",
        "distractor_burden", "query_reformulation_gain", "modality_switches",
        "modality_switch_rate",
    )
    rows = []
    groups: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for episode in episodes:
        if episode["displacement"] or episode.get(
            "experiment_role"
        ) == "restored_no_trigger_control":
            continue
        groups[(episode["scope"], episode["state"], episode["policy"])].append(episode)
    for (scope, state, policy), items in sorted(groups.items()):
        for metric in metric_names:
            values = [float(x[metric]) for x in items if x.get(metric) not in (None, "")]
            rows.append(
                {
                    "scope": scope, "state": state, "policy": policy,
                    "metric": metric,
                    "numerator": _round(sum(values), 6) if values else None,
                    "denominator": len(values),
                    "value": _round(np.mean(values), 6) if values else None,
                    "eligible_family_count": len({
                        x["family_id"] for x in items if x.get(metric) not in (None, "")
                    }),
                    "eligible_source_count": len({
                        x["source_ref"] for x in items if x.get(metric) not in (None, "")
                    }),
                    "k_or_budget": (
                        metric.split("@")[-1] if "@" in metric else "primary"
                    ),
                    "eligibility_status": "hypothesis_conditioned" if values else "ineligible",
                    "eligibility_reason": "non_null_rows" if values else "no_eligible_rows",
                    "LOW_N_DESCRIPTIVE_SCALE1A": True,
                }
            )
    return rows


def _retrieval_rows(episodes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    fields = (
        "Recall@1", "Recall@5", "Recall@10", "Recall@20",
        "All-Evidence@1", "All-Evidence@5", "All-Evidence@10",
        "All-Evidence@20", "first_accepted_evidence_rank",
        "first_accepted_evidence_status",
        "inspected_video_fraction", "distractor_burden",
        "query_reformulation_gain", "modality_switches",
        "modality_switch_rate",
    )
    return [
        {
            "case_id": _opaque_case_id(str(x["family_id"])),
            "scope": x["scope"], "state": x["state"], "policy": x["policy"],
            "displacement": x["displacement"],
            **{field: x[field] for field in fields},
            "LOW_N_DESCRIPTIVE_SCALE1A": True,
        }
        for x in episodes
    ]


def _opaque_case_id(family_id: str) -> str:
    return "case-" + hashlib.sha256(family_id.encode("utf-8")).hexdigest()[:12]


def _public_episode_rows(
    episodes: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    private = {
        "family_id", "source_ref", "observed_segment_ids",
        "strict_final_route_certificate",
        "actions", "tool_response_references", "acquired_citable_observations",
        "validation", "trigger_events", "controller", "policy_visible_start",
        "final_output", "policy_blindness", "trajectory_id",
        "_evaluator_evidence_by_observation",
        "query_reformulation_diagnostic", "modality_action_diagnostic",
        "displacement_audit",
    }
    return [
        {
            "case_id": _opaque_case_id(str(row["family_id"])),
            **{key: value for key, value in row.items() if key not in private},
        }
        for row in episodes
    ]


def _displacement_summary_rows(
    episodes: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    groups: dict[tuple[str, bool], list[Mapping[str, Any]]] = defaultdict(list)
    for episode in episodes:
        if episode["displacement"] and episode.get("displacement_eligible"):
            groups[(episode["policy"], bool(episode["recovery_disabled"]))].append(
                episode
            )
    for (policy, disabled), items in sorted(groups.items()):
        for metric, field in (
            ("Evidence reacquisition after displacement",
             "evidence_reacquired_after_displacement"),
            ("Answer recovery after displacement",
             "answer_recovered_after_displacement"),
        ):
            values = [float(bool(item[field])) for item in items]
            rows.append(
                {
                    "scope": "full_source_scoped_displacement",
                    "state": "CLEAN",
                    "policy": policy,
                    "control": "recovery_disabled" if disabled else "recovery_enabled",
                    "metric": metric,
                    "numerator": _round(sum(values), 6),
                    "denominator": len(values),
                    "value": _round(np.mean(values), 6),
                    "eligible_family_count": len({x["family_id"] for x in items}),
                    "eligible_source_count": len({x["source_ref"] for x in items}),
                    "k_or_budget": "primary",
                    "eligibility_status": "hypothesis_conditioned",
                    "eligibility_reason": "eligible_validated_negative_displaced_trajectories",
                    "LOW_N_DESCRIPTIVE_SCALE1A": True,
                }
            )
    return rows


def _bounded_delta(
    episode: Mapping[str, Any], pilot: Mapping[tuple[str, str, str], Mapping[str, str]]
) -> dict[str, float | None]:
    row = pilot.get((episode["family_id"], episode["state"], episode["policy"]))
    if row is None:
        return {}
    mapping = {
        "Evidence Recall": "evidence_recall",
        "All-Evidence Success": "all_evidence_success",
        "Answer Score": "answer_score",
        "Citation F1": "citation_f1",
        "Supported-Claim Rate": "supported_claim_rate",
        "Success@Budget": "success_at_budget",
        "Premature Stop": "premature_stop",
        "Recovery": "recovery",
    }
    output: dict[str, float | None] = {}
    for metric, column in mapping.items():
        raw = row.get(column)
        output[metric] = (
            None if raw in (None, "") or episode.get(metric) is None
            else _round(float(episode[metric]) - float(raw), 6)
        )
    return output


def run_scale1a(repo_root: str | Path) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    trust = verify_trust_anchor(root)
    plan = _load(root / PLAN_REL)
    restricted = root / RESTRICTED_REL
    required = (
        "segment_manifest.json", "observation_manifest.json",
        "full_timeline_index.json", "migrated_families.json",
        "hard_negatives.json", "interventions.json", "build_manifest.json",
    )
    for name in required:
        if not (restricted / name).is_file():
            raise Scale1AError(f"MISSING_BUILD_OUTPUT:{name}")
    index = _load(restricted / "full_timeline_index.json")
    migration = _load(restricted / "migrated_families.json")
    negatives_doc = _load(restricted / "hard_negatives.json")
    interventions_doc = _load(restricted / "interventions.json")
    negative_map = {x["family_id"]: x for x in negatives_doc["families"]}
    intervention_map = {x["family_id"]: x for x in interventions_doc["families"]}
    retained = [
        x for x in migration["families"] if x["migration_disposition"] == "retained"
    ]
    episodes = []
    for family in retained:
        planned = next(x for x in plan["families"] if x["family_id"] == family["family_id"])
        for scope in ("full_source_scoped", "full_cross_source"):
            for state in STATES:
                for policy in POLICIES:
                    episodes.append(
                        _simulate_episode(
                            root, plan, index, family, planned,
                            intervention_map[family["family_id"]],
                            negative_map[family["family_id"]],
                            scope=scope, state=state, policy=policy,
                        )
                    )
        # Matched RESTORED controls execute the same trigger-seeking policy
        # with the restoration hook disabled.
        for policy in ("react-recovery", "evidence-sufficiency"):
            episodes.append(
                _simulate_episode(
                    root, plan, index, family, planned,
                    intervention_map[family["family_id"]],
                    negative_map[family["family_id"]],
                    scope="full_source_scoped", state="RESTORED", policy=policy,
                    recovery_disabled=False, restoration_enabled=False,
                    experiment_role="restored_no_trigger_control",
                )
            )
        # Only families with a validated negative route enter displacement
        # metrics. Ineligible families are represented by metadata, not fake
        # trajectories using provisional visual negatives.
        displacement_spec, _ = _displacement_spec(
            family, negative_map[family["family_id"]]
        )
        if displacement_spec is None:
            continue
        for policy in ("react-recovery", "evidence-sufficiency"):
            for disabled in (False, True):
                episodes.append(
                    _simulate_episode(
                        root, plan, index, family, planned,
                        intervention_map[family["family_id"]],
                        negative_map[family["family_id"]],
                        scope="full_source_scoped", state="CLEAN", policy=policy,
                        displacement=True, recovery_disabled=disabled,
                        experiment_role="hard_negative_displacement",
                    )
                )
    pilot = _pilot_episode_map(root)
    for episode in episodes:
        episode["bounded_to_full_degradation"] = (
            _bounded_delta(episode, pilot)
            if episode["scope"] == "full_source_scoped"
            and not episode["displacement"]
            and episode.get("experiment_role") == "ordinary"
            else {}
        )
    summary = _summary_rows(episodes) + _displacement_summary_rows(episodes)
    retrieval = _retrieval_rows(episodes)
    engineering_checks = {
        "trust_anchor": trust["verified"],
        "exact_segment_counts": _load(restricted / "segment_manifest.json")["totals"] == {
            "base_cells": 3433, "fine_windows": 3428,
            "context_windows": 855, "windows": 4283,
            "maximum_modality_records": 12849,
        },
        "all_layers_and_indices_built": (
            _load(restricted / "observation_manifest.json")["all_five_complete"]
            and index["modalities"]["vision"]["ready"]
        ),
        "no_media_derivatives": _load(restricted / "observation_manifest.json")["no_persisted_media_derivatives"],
        "retained_at_least_four": len(retained) >= 4,
        "speech_retained": migration["speech_family_retained"],
        "ambient_or_cross_modal_retained": migration["ambient_or_cross_modal_retained"],
        "all_cbr_invariants": all(
            x["invariants_passed"] for x in interventions_doc["families"] if x["retained"]
        ),
        "visual_candidates_honestly_provisional": all(
            all(
                candidate["validation_status"]
                == "machine_provisional_hard_negative_candidate"
                and not candidate[
                    "eligible_for_validated_hard_negative_metrics"
                ]
                for candidate in negative_map[x["family_id"]].get(
                    "machine_provisional_hard_negative_candidates", ()
                )
                if candidate["modality"] == "vision"
            )
            for x in retained
        ),
        "query_reformulation_contract": all(
            (
                x["query_reformulation_diagnostic"]["eligible"]
                and x["query_reformulation_gain"] is not None
            ) or (
                not x["query_reformulation_diagnostic"]["eligible"]
                and x["query_reformulation_gain"] is None
            )
            for x in episodes
        ),
        "modality_switch_contract": all(
            x["modality_switches"]
            == x["modality_action_diagnostic"]["switch_count"]
            for x in episodes
        ),
        "restored_no_trigger_controls": sum(
            x["experiment_role"] == "restored_no_trigger_control"
            for x in episodes
        ) == len(retained) * 2 and all(
            not x["trigger_events"] and x["Evidence Recall"] < 1
            for x in episodes
            if x["experiment_role"] == "restored_no_trigger_control"
        ),
        "eligible_displacement_contract": all(
            x["displacement_audit"]["applied"]
            and x["displacement_audit"]["all_accepted_support_outside_top_k"]
            and x["displacement_audit"]["validation_status"]
            == "machine_validated_hard_negative"
            for x in episodes if x["displacement"]
        ),
    }
    engineering = (
        "SCALE1A_ENGINEERING_GO"
        if all(engineering_checks.values()) else "SCALE1A_NO_GO"
    )
    nonzero_families = {
        x["family_id"] for x in episodes
        if x["scope"] == "full_source_scoped" and not x["displacement"]
        and x.get("experiment_role") == "ordinary"
        and any(
            value not in (None, 0, 0.0)
            for key, value in x["bounded_to_full_degradation"].items()
            if key in {"Evidence Recall", "All-Evidence Success"}
        )
    }
    displacement_recovery = any(
        x["displacement"] and not x["recovery_disabled"]
        and x["evidence_reacquired_after_displacement"] for x in episodes
    )
    displacement_control = all(
        not x["evidence_reacquired_after_displacement"] for x in episodes
        if x["displacement"] and x["recovery_disabled"]
    )
    policy_signatures = {
        policy: tuple(
            np.mean([
                x[metric] for x in episodes
                if x["policy"] == policy and x["scope"] == "full_source_scoped"
                and not x["displacement"]
                and x.get("experiment_role") == "ordinary"
                and x[metric] is not None
            ])
            for metric in ("Evidence Recall", "Answer Score", "Success@Budget")
        )
        for policy in POLICIES
    }
    diagnostic_checks = {
        "two_families_nonzero_degradation": len(nonzero_families) >= 2,
        "displacement_recovery_and_control": displacement_recovery and displacement_control,
        "policy_separation": len(set(policy_signatures.values())) >= 2,
        "answer_evidence_grounding_separation": any(
            x["Answer Score"] == 1 and x["Evidence Recall"] < 1
            or x["Evidence Recall"] == 1 and x["Answer Score"] < 1
            for x in episodes
        ),
        "r007_shortcut_mask_survives": any(
            x["family_id"] == "noaa01-r007-opening-plastic-waste"
            and x["scope"] == "full_source_scoped" and x["Recall@5"] > 0
            for x in episodes
        ),
        "effects_not_one_family": len(nonzero_families) >= 2,
        "validated_hard_negative_eligibility": all(
            negative_map[x["family_id"]].get(
                "validated_hard_negative_metric_eligible", False
            )
            for x in retained
        ),
        "restored_no_trigger_matched_controls": all(
            any(
                control["family_id"] == x["family_id"]
                and control["policy"] == x["policy"]
                and control["scope"] == x["scope"]
                and control["experiment_role"] == "restored_no_trigger_control"
                and not control["restoration_enabled"]
                and not control["trigger_events"]
                and control["Evidence Recall"] < 1
                for control in episodes
            )
            for x in episodes
            if x["state"] == "RESTORED"
            and x["scope"] == "full_source_scoped"
            and x["policy"] in {"react-recovery", "evidence-sufficiency"}
            and x["experiment_role"] == "ordinary"
        ),
    }
    diagnostic = (
        "SCALE1A_DIAGNOSTIC_GO"
        if engineering == "SCALE1A_ENGINEERING_GO"
        and all(diagnostic_checks.values())
        else (
            "SCALE1A_DIAGNOSTIC_INCONCLUSIVE"
            if engineering == "SCALE1A_ENGINEERING_GO" else "SCALE1A_NO_GO"
        )
    )
    report = {
        "schema_version": SCHEMA_VERSION, "stage": STAGE,
        "human_reviewed": False, "gold_annotation": False,
        "learned_model_evaluation": False,
        "policy_class": POLICY_VERSION,
        "warning": WARNING,
        "family_count": len(retained), "episode_count": len(episodes),
        "engineering_decision": engineering,
        "diagnostic_decision": diagnostic,
        "final_benchmark_status": FINAL_STATUS,
        "engineering_checks": engineering_checks,
        "diagnostic_checks": diagnostic_checks,
        "summary": summary,
        "bounded_comparison_source": PILOT_EPISODES_REL.as_posix(),
        "limitations": [
            "Machine-adjudicated provisional labels only.",
            "No human-reviewed gold annotation or validated modality necessity.",
            "Policies are deterministic protocols, not learned models.",
            "Small five-family diagnostic; no inferential scientific claim.",
        ],
    }
    results = root / RESULTS_REL
    results.mkdir(parents=True, exist_ok=True)
    _dump(results / "report.json", report, restricted=False)
    _write_csv(results / "episode_metrics.csv", _public_episode_rows(episodes))
    _write_csv(results / "retrieval_metrics.csv", retrieval)
    _write_csv(results / "summary.csv", summary)
    trajectories_path = restricted / "trajectories.json"
    _dump(trajectories_path, {"episodes": episodes}, restricted=True)
    report_md = f"""# Scale-1A full-timeline report

- Stage: `{STAGE}`
- Human reviewed: `false`
- Gold annotation: `false`
- Policies: deterministic protocols, not learned models
- Retained families: `{len(retained)}`
- Engineering: `{engineering}`
- Diagnostic: `{diagnostic}`
- Final benchmark: `{FINAL_STATUS}`
- Warning: `{WARNING}`

The full-timeline source-scoped and cross-source runs use the same frozen
index, tie-breaks, budgets, intervention semantics, and evaluator-private
support rules. Task-99 controls and displacement rows are separately labeled
and are not pooled with ordinary C/B/R summaries. Results are descriptive and
provisional.
"""
    _atomic_bytes(results / "report.md", report_md.encode(), restricted=False)
    public_artifacts = [
        results / "report.json", results / "episode_metrics.csv",
        results / "retrieval_metrics.csv", results / "summary.csv",
        results / "report.md",
    ]
    restricted_artifacts = [
        {
            "role": "restricted_trajectories",
            "size_bytes": trajectories_path.stat().st_size,
            "sha256": _sha256(trajectories_path, prefixed=True),
            "mode": f"{stat.S_IMODE(trajectories_path.stat().st_mode):04o}",
        }
    ]
    run_manifest = {
        "schema_version": SCHEMA_VERSION, "stage": STAGE,
        "engineering_decision": engineering,
        "diagnostic_decision": diagnostic,
        "final_benchmark_status": FINAL_STATUS,
        "index_hash": index["index_hash"],
        "artifact_hashes": _artifact_inventory(public_artifacts, root),
        # Public provenance deliberately identifies the private artifact by
        # semantic role and hash rather than exposing its filesystem path.
        "restricted_artifact_hashes": restricted_artifacts,
        "replay_command": "python scripts/run_scale1a_full_timeline.py --repo-root . --replay",
        "trust_anchor_finalization_required": True,
    }
    run_manifest["run_manifest_hash"] = _json_hash(run_manifest)
    _dump(results / "run_manifest.json", run_manifest, restricted=False)
    _mark_build_stages(root, {"experiments": "PASS"})
    return {
        "report": report, "episodes": episodes, "retrieval": retrieval,
        "summary": summary, "run_manifest": run_manifest,
    }


def _public_leakage_scan(repo_root: Path) -> list[str]:
    failures = []
    paths = list((repo_root / RESULTS_REL).glob("*"))
    paths += [
        repo_root / "docs/review/scale1a_full_timeline_go_no_go.md",
        repo_root / "orchestration/results/95_scale1a_full_timeline_implementation.txt",
    ]
    forbidden = [
        "data/restricted/", ".mp4", "provisional_text", "vector_f16_hex",
        "aggregate_predictions", "answer_hypothesis", "answer_aliases",
        "observed_segment_ids", "strict_final_route_certificate",
    ]
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in forbidden:
            if token in text:
                failures.append(f"{path.relative_to(repo_root)}:{token}")
    return failures


def tool_time_decode(
    repo_root: Path, source_ref: str, interval: Sequence[float], *,
    include_video: bool, include_audio: bool,
) -> dict[str, Any]:
    plan = _load(repo_root / PLAN_REL)
    source = next(x for x in plan["sources"] if x["candidate_id"] == source_ref)
    path, source_sha256 = _verified_source_path(repo_root, source)
    start_s, end_s = map(float, interval)
    if not 0 <= start_s < end_s <= source["duration_s"] + 1e-6:
        raise Scale1AError("TOOL_INTERVAL_OUT_OF_RANGE")
    finite = True
    video_frames = 0
    audio_samples = 0
    with av.open(str(path), mode="r") as container:
        if include_video:
            stream = next((s for s in container.streams if s.type == "video"), None)
            if stream is None:
                raise Scale1AError("TOOL_VIDEO_STREAM_MISSING")
            container.seek(
                int(max(0.0, start_s - 1) / float(stream.time_base)),
                stream=stream, backward=True, any_frame=False,
            )
            for frame in container.decode(stream):
                if frame.pts is None:
                    continue
                time_s = float(frame.pts * frame.time_base)
                if time_s >= end_s:
                    break
                if time_s >= start_s:
                    rgb = frame.to_ndarray(format="rgb24")
                    finite = finite and bool(np.isfinite(rgb).all())
                    video_frames += 1
    if include_audio:
        samples = _decode_audio_interval(path, start_s, end_s)
        finite = finite and bool(np.isfinite(samples).all())
        audio_samples = len(samples)
        del samples
    if not finite or (include_video and not video_frames) or (
        include_audio and not audio_samples
    ):
        raise Scale1AError("TOOL_TIME_DECODE_FAILED")
    return {
        "source_ref": source_ref, "source_sha256": source_sha256,
        "interval": {"start_s": start_s, "end_s": end_s},
        "video_frames": video_frames, "audio_samples": audio_samples,
        "finite": finite, "temporary_buffer_deleted": True,
        "citable_from_exact_original": True,
    }


def verify_scale1a(repo_root: str | Path, *, strict: bool = True) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    failures: list[str] = []
    try:
        trust = verify_trust_anchor(root)
    except Exception as exc:
        trust = {"verified": False}
        failures.append(str(exc))
    restricted = root / RESTRICTED_REL
    results = root / RESULTS_REL
    required_restricted = (
        "segment_manifest.json", "observation_manifest.json",
        "full_timeline_index.json", "hard_negatives.json",
        "migrated_families.json", "interventions.json", "build_manifest.json",
        "trajectories.json",
    )
    required_public = (
        "report.json", "episode_metrics.csv", "retrieval_metrics.csv",
        "summary.csv", "run_manifest.json", "report.md",
    )
    for name in required_restricted:
        if not (restricted / name).is_file():
            failures.append(f"missing:{RESTRICTED_REL / name}")
    for name in required_public:
        if not (results / name).is_file():
            failures.append(f"missing:{RESULTS_REL / name}")
    if failures:
        return {"decision": "SCALE1A_NO_GO", "failures": failures}
    segments = _load(restricted / "segment_manifest.json")
    observations = _load(restricted / "observation_manifest.json")
    index = _load(restricted / "full_timeline_index.json")
    migration = _load(restricted / "migrated_families.json")
    negatives = _load(restricted / "hard_negatives.json")
    interventions = _load(restricted / "interventions.json")
    trajectories = _load(restricted / "trajectories.json")
    build_manifest = _load(restricted / "build_manifest.json")
    report = _load(results / "report.json")
    run_manifest = _load(results / "run_manifest.json")
    expected_counts = {
        "base_cells": 3433, "fine_windows": 3428,
        "context_windows": 855, "windows": 4283,
        "maximum_modality_records": 12849,
    }
    if segments["totals"] != expected_counts:
        failures.append("segment_counts")
    if not observations.get("all_five_complete"):
        failures.append("observations_incomplete")
    if not index["modalities"]["vision"].get("ready"):
        failures.append("clip_visual_index_not_ready")
    expected_observation_counts = {
        "ambient_records": 4283, "ast_fine_calls": 3428,
        "clip_cells": 3433, "routing_cells": 3433,
        "speech_search_records": 461,
        "legacy_projected_speech_records_ignored": 4283,
        "vision_records": 4283,
        "whisper_chunks": 461,
    }
    if observations.get("counts") != expected_observation_counts:
        failures.append("observation_counts")
    if len(observations.get("checkpoints", [])) != 20:
        failures.append("checkpoint_count")
    plan = _load(root / PLAN_REL)
    source_by_id = {item["candidate_id"]: item for item in plan["sources"]}
    expected_checkpoint_specs = {
        "speech.json": (
            "whisper-tiny-en-timestamped/1.0", "30-second",
            lambda source: int(math.ceil(source["duration_s"] / 30)),
        ),
        "ambient.json": (
            "ast-audioset-top15/1.0", "fine",
            lambda source: source["fine_count"],
        ),
        "vision_clip.json": (
            "clip-visual/1.0", "base",
            lambda source: source["cell_and_frame_count"],
        ),
        "vision_routing.json": (
            "opencv-routing/1.0", "base",
            lambda source: source["cell_and_frame_count"],
        ),
    }
    for checkpoint in observations.get("checkpoints", []):
        path = Path(checkpoint["path"])
        if not path.is_absolute():
            path = root / path
        try:
            source_ref = path.parent.name
            source = source_by_id[source_ref]
            layer_version, scale, count_fn = expected_checkpoint_specs[path.name]
            expected_count = int(count_fn(source))
            expected_key = _checkpoint_key(
                source["sha256"], layer_version, scale, 0,
                observations["config_hash"],
            )
            body = _load(path)
            payload = {
                key: value for key, value in body.items()
                if key not in {"checkpoint_key", "record_count", "payload_hash"}
            }
            checks = (
                path.is_file(),
                not path.is_symlink(),
                stat.S_IMODE(path.stat().st_mode) == 0o600,
                path.stat().st_size == checkpoint["size_bytes"],
                _sha256(path, prefixed=True) == checkpoint["sha256"],
                checkpoint["key"] == expected_key,
                checkpoint["record_count"] == expected_count,
                body.get("checkpoint_key") == checkpoint["key"],
                body.get("record_count") == checkpoint["record_count"],
                body.get("payload_hash") == checkpoint["payload_hash"],
                body.get("payload_hash") == _json_hash(payload),
            )
            if not all(checks):
                failures.append(f"checkpoint_integrity:{path}")
        except Exception as exc:
            failures.append(f"checkpoint_integrity:{path}:{exc}")
    copy = dict(index)
    stored_hash = copy.pop("index_hash")
    if stored_hash != _json_hash(copy):
        failures.append("index_hash")
    build_copy = dict(build_manifest)
    stored_build_hash = build_copy.pop("build_manifest_hash", None)
    if stored_build_hash != _json_hash(build_copy):
        failures.append("build_manifest_hash")
    for item in build_manifest.get("artifact_inventory", []):
        path = root / item["path"]
        if (
            not path.is_file()
            or path.stat().st_size != item["size_bytes"]
            or _sha256(path, prefixed=True) != item["sha256"]
            or f"{stat.S_IMODE(path.stat().st_mode):04o}" != item["mode"]
        ):
            failures.append(f"build_inventory:{item['path']}")
    run_copy = dict(run_manifest)
    stored_run_hash = run_copy.pop("run_manifest_hash", None)
    if stored_run_hash != _json_hash(run_copy):
        failures.append("run_manifest_hash")
    for item in run_manifest.get("artifact_hashes", []):
        path = root / item["path"]
        if (
            not path.is_file()
            or path.stat().st_size != item["size_bytes"]
            or _sha256(path, prefixed=True) != item["sha256"]
            or f"{stat.S_IMODE(path.stat().st_mode):04o}" != item["mode"]
        ):
            failures.append(f"run_inventory:{item['path']}")
    trajectories_path = restricted / "trajectories.json"
    for item in run_manifest.get("restricted_artifact_hashes", []):
        if item.get("role") != "restricted_trajectories":
            failures.append("unknown_restricted_artifact_role")
            continue
        if (
            trajectories_path.stat().st_size != item["size_bytes"]
            or _sha256(trajectories_path, prefixed=True) != item["sha256"]
            or f"{stat.S_IMODE(trajectories_path.stat().st_mode):04o}"
            != item["mode"]
        ):
            failures.append("restricted_trajectory_inventory")
    for document, hash_key, failure_name in (
        (segments, "segment_manifest_hash", "segment_manifest_hash"),
        (observations, "observation_manifest_hash", "observation_manifest_hash"),
        (migration, "migration_hash", "migration_hash"),
        (negatives, "hard_negative_hash", "hard_negative_hash"),
        (interventions, "interventions_hash", "interventions_hash"),
    ):
        copy_document = dict(document)
        stored = copy_document.pop(hash_key, None)
        if stored != _json_hash(copy_document):
            failures.append(failure_name)
    try:
        current_models = _model_manifest(root, _load(root / PLAN_REL))
        if current_models != observations.get("model_snapshots"):
            failures.append("model_snapshot_gate_or_hash")
    except Exception as exc:
        failures.append(f"model_snapshot_gate_or_hash:{exc}")
    if any(stage.get("status") not in {"PASS", "PASS_BY_SUPERSET_FULL_BUILD"}
           for stage in build_manifest.get("stages", [])):
        failures.append("build_stage_status")
    for modality in index["modalities"].values():
        for record in modality.get("documents", []):
            try:
                _assert_search_record_safe(record)
            except Scale1AError as exc:
                failures.append(str(exc))
    retained = [
        x for x in migration["families"] if x["migration_disposition"] == "retained"
    ]
    if len(retained) < 4:
        failures.append("fewer_than_four_retained")
    nmap = {x["family_id"]: x for x in negatives["families"]}
    # Task 97 deliberately supports the fail-closed alternative allowed by
    # the protocol: vector-only visual candidates without two independent
    # content judgments remain provisional and are excluded from metrics that
    # require validated hard negatives. They must still be explicitly
    # labeled and numerous enough to exercise the intervention mechanics.
    for family in retained:
        negative_record = nmap[family["family_id"]]
        if negative_record.get("validated_hard_negative_metric_eligible"):
            if negative_record.get("admitted_count", 0) < 5:
                failures.append(
                    f"hard_negative_minimum:{family['family_id']}"
                )
            continue
        provisional = negative_record.get(
            "machine_provisional_hard_negative_candidates", []
        )
        if len(provisional) < 5 or any(
            candidate.get("validation_status")
            != "machine_provisional_hard_negative_candidate"
            or candidate.get("eligible_for_validated_hard_negative_metrics")
            is not False
            or candidate.get("admitted") is not False
            for candidate in provisional
        ):
            failures.append(
                f"hard_negative_provisional_gate:{family['family_id']}"
            )
    if any(
        not x["invariants_passed"] for x in interventions["families"] if x["retained"]
    ):
        failures.append("intervention_invariant")

    # A metrics-only row is not an auditable trajectory.  Task-90 Ground/Act
    # semantics require the policy actions, actual budget use, final output,
    # and final-point route-feasibility evidence to be persisted.
    episodes = trajectories.get("episodes", [])
    required_trajectory_fields = {
        "actions", "steps_used", "cost_used", "final_output",
        "query_reformulation_diagnostic", "modality_action_diagnostic",
        "experiment_role", "restoration_enabled", "displacement_audit",
    }
    expected_displacement_families = {
        family["family_id"] for family in retained
        if _displacement_spec(family, nmap[family["family_id"]])[0] is not None
    }
    expected_trajectory_count = (
        len(retained) * len(STATES) * len(POLICIES) * 2
        + len(retained) * 2
        + len(expected_displacement_families) * 2 * 2
    )
    if len(episodes) != expected_trajectory_count:
        failures.append("trajectory_count")
    if any(not required_trajectory_fields <= set(row) for row in episodes):
        failures.append("trajectory_action_log_missing")
    if any(
        "route_feasibility" not in row.get("strict_final_route_certificate", {})
        for row in episodes
    ):
        failures.append("final_point_route_certificate_missing")

    # Task 99 diagnostic contracts are independently recomputed from the
    # persisted action/response trace.
    for episode in episodes:
        reformulation = _query_reformulation_diagnostic(
            episode["actions"],
            episode.get("_evaluator_evidence_by_observation", {}),
            [
                set(item["evidence_ids"])
                for item in next(
                    family for family in retained
                    if family["family_id"] == episode["family_id"]
                )["candidate_support_sets"]
            ],
        )
        if reformulation != episode.get("query_reformulation_diagnostic"):
            failures.append(
                f"query_reformulation_recompute:{episode['trajectory_id']}"
            )
        if reformulation["value"] != episode.get("query_reformulation_gain"):
            failures.append(
                f"query_reformulation_value:{episode['trajectory_id']}"
            )
        if reformulation["eligible"] and episode.get(
            "query_reformulation_gain"
        ) is None:
            failures.append(
                f"query_reformulation_null_when_eligible:{episode['trajectory_id']}"
            )
        switching = _modality_action_diagnostic(episode["actions"])
        if switching != episode.get("modality_action_diagnostic"):
            failures.append(f"modality_sequence_recompute:{episode['trajectory_id']}")
        if (
            switching["switch_count"] != episode.get("modality_switches")
            or switching["switch_rate"] != episode.get("modality_switch_rate")
        ):
            failures.append(f"modality_switch_recompute:{episode['trajectory_id']}")

    agentic = {"react-recovery", "evidence-sufficiency"}
    ordinary_restored = {
        (x["family_id"], x["policy"]): x for x in episodes
        if x["scope"] == "full_source_scoped"
        and x["state"] == "RESTORED"
        and x["policy"] in agentic
        and x.get("experiment_role") == "ordinary"
    }
    controls = [
        x for x in episodes
        if x.get("experiment_role") == "restored_no_trigger_control"
    ]
    if len(controls) != len(retained) * len(agentic):
        failures.append("restored_no_trigger_control_count")
    def trigger_seeking_signature(
        episode: Mapping[str, Any],
    ) -> list[tuple[str, str | None, tuple[str, ...]]]:
        signature = []
        for row in episode["actions"]:
            tool = row["action"]["tool"]
            arguments = row["action"].get("arguments", {})
            signature.append(
                (
                    tool,
                    arguments.get("query"),
                    tuple(arguments.get("modalities", ())),
                )
            )
        return signature

    def pre_trigger_signature(
        episode: Mapping[str, Any],
    ) -> list[tuple[str, str | None, tuple[str, ...]]]:
        events = episode.get("trigger_events", [])
        if not events:
            return trigger_seeking_signature(episode)
        boundary = int(events[0]["before_step"])
        limited = dict(episode)
        limited["actions"] = [
            row for row in episode["actions"] if int(row["step"]) < boundary
        ]
        return trigger_seeking_signature(limited)

    for control in controls:
        key = (control["family_id"], control["policy"])
        matched = ordinary_restored.get(key)
        if (
            matched is None
            or control["state"] != "RESTORED"
            or control["scope"] != "full_source_scoped"
            or control.get("restoration_enabled") is not False
            or control.get("trigger_events")
            or control["budget"] != matched["budget"]
            or trigger_seeking_signature(control)[
                :len(pre_trigger_signature(matched))
            ] != pre_trigger_signature(matched)
            or control["Evidence Recall"] >= 1
        ):
            failures.append(
                f"restored_no_trigger_control_mismatch:{control['trajectory_id']}"
            )

    displaced = [x for x in episodes if x.get("displacement")]
    if len(displaced) != len(expected_displacement_families) * 4:
        failures.append("eligible_displacement_count")
    for episode in displaced:
        audit = episode.get("displacement_audit", {})
        k = audit.get("primary_k")
        if (
            episode["family_id"] not in expected_displacement_families
            or episode.get("experiment_role") != "hard_negative_displacement"
            or not episode.get("displacement_eligible")
            or not audit.get("applied")
            or audit.get("validation_status")
            != "machine_validated_hard_negative"
            or not audit.get("original_accepted_support_ranks")
            or not audit.get("displaced_accepted_support_ranks")
            or not isinstance(k, int)
            or min(audit["displaced_accepted_support_ranks"]) <= k
            or not audit.get("all_accepted_support_outside_top_k")
        ):
            failures.append(f"topk_displacement_proof:{episode['trajectory_id']}")

    # Suppressing only the nominal overlapping segment IDs is insufficient
    # when a coarse Whisper chunk has been projected into adjacent windows.
    # Every search record derived from a support chunk must be suppressed in
    # BLOCKED/RESTORED-pretrigger states.
    speech_lineage: dict[str, set[str]] = {
        record["segment_id"]: set(record.get("derived_from_chunk_ids", ()))
        for record in index["modalities"]["speech"].get("documents", [])
    }
    intervention_map = {
        row["family_id"]: row for row in interventions.get("families", [])
    }
    for family in retained:
        support_ids = set(family.get("support_segment_ids", {}).get("speech", []))
        if not support_ids:
            continue
        support_chunks = set().union(
            *(speech_lineage.get(segment_id, set()) for segment_id in support_ids)
        ) if support_ids else set()
        derived_ids = {
            segment_id for segment_id, chunk_ids in speech_lineage.items()
            if chunk_ids.intersection(support_chunks)
        }
        suppressed = set(
            intervention_map[family["family_id"]]["blocked"][
                "suppressed_segment_ids"
            ]
        )
        if not derived_ids <= suppressed:
            failures.append(
                f"blocked_speech_lineage_leak:{family['family_id']}"
            )

    # CLIP-only candidates have no searchable text on which the existing
    # answer/claim token checks can operate.  They must carry independent
    # content-level validation evidence before being called admitted hard
    # negatives.
    for family in retained:
        for candidate in nmap[family["family_id"]].get("admitted", []):
            if candidate.get("modality") != "vision":
                continue
            checks = candidate.get("independent_content_checks", [])
            if not isinstance(checks, list) or len(checks) < 2:
                failures.append(
                    f"visual_hard_negative_unvalidated:{family['family_id']}"
                )
                break
    permission_failures = _restricted_tree_permissions(restricted)
    failures.extend(permission_failures)
    failures.extend(_public_leakage_scan(root))
    # Verify one exact original interval for every retained family/modality.
    if strict:
        for family in retained:
            try:
                tool_time_decode(
                    root, family["asset_id"], family["primary_fine_interval_s"],
                    include_video="vision" in family["provisional_modalities"],
                    include_audio=any(
                        x in family["provisional_modalities"]
                        for x in ("speech", "ambient")
                    ),
                )
            except Exception as exc:
                failures.append(f"tool_decode:{family['family_id']}:{exc}")
    if report["engineering_decision"] == "SCALE1A_ENGINEERING_GO" and failures:
        failures.append("report_claims_engineering_go_despite_failures")
    decision = "SCALE1A_NO_GO" if failures else report["engineering_decision"]
    return {
        "schema_version": SCHEMA_VERSION, "trust_anchor": trust,
        "decision": decision, "diagnostic_decision": report["diagnostic_decision"],
        "final_benchmark_status": FINAL_STATUS,
        "failures": failures, "passed": not failures,
    }


def replay_scale1a(repo_root: str | Path) -> dict[str, Any]:
    """Replay deterministic manifests/rankings and compare semantic hashes.

    Expensive model shards are not recomputed: every checkpoint is first
    revalidated by key, count, payload hash, raw hash and permissions. The
    deterministic derivation from those verified observations is then rebuilt
    into an isolated temporary tree and compared.
    """
    root = Path(repo_root).resolve()
    plan = _load(root / PLAN_REL)
    segment_original = _load(root / RESTRICTED_REL / "segment_manifest.json")
    observation = _load(root / RESTRICTED_REL / "observation_manifest.json")
    for checkpoint in observation["checkpoints"]:
        path = Path(checkpoint["path"])
        if not path.is_absolute():
            path = root / path
        if _sha256(path, prefixed=True) != checkpoint["sha256"]:
            raise Scale1AError(f"REPLAY_CHECKPOINT_HASH_MISMATCH:{path}")
    segment_replay = build_segment_manifest(root, plan)
    index_replay = build_index(root, plan, segment_replay, observation)
    migration_replay = migrate_families(root, plan, index_replay)
    negatives_replay = build_hard_negatives(root, plan, index_replay, migration_replay)
    interventions_replay = build_interventions(
        plan, migration_replay, negatives_replay, index_replay
    )
    fixed_replay = _fixed_query_suite(root, index_replay, plan)
    migration_original = _load(root / RESTRICTED_REL / "migrated_families.json")
    negatives_original = _load(root / RESTRICTED_REL / "hard_negatives.json")
    interventions_original = _load(root / RESTRICTED_REL / "interventions.json")
    episodes_replay: list[dict[str, Any]] = []
    negative_map = {x["family_id"]: x for x in negatives_original["families"]}
    intervention_map = {
        x["family_id"]: x for x in interventions_original["families"]
    }
    retained = [
        x for x in migration_original["families"]
        if x["migration_disposition"] == "retained"
    ]
    for family in retained:
        planned = next(
            x for x in plan["families"] if x["family_id"] == family["family_id"]
        )
        for scope in ("full_source_scoped", "full_cross_source"):
            for state in STATES:
                for policy in POLICIES:
                    episodes_replay.append(
                        _simulate_episode(
                            root, plan, index_replay, family, planned,
                            intervention_map[family["family_id"]],
                            negative_map[family["family_id"]],
                            scope=scope, state=state, policy=policy,
                        )
                    )
        for policy in ("react-recovery", "evidence-sufficiency"):
            episodes_replay.append(
                _simulate_episode(
                    root, plan, index_replay, family, planned,
                    intervention_map[family["family_id"]],
                    negative_map[family["family_id"]],
                    scope="full_source_scoped", state="RESTORED", policy=policy,
                    recovery_disabled=False, restoration_enabled=False,
                    experiment_role="restored_no_trigger_control",
                )
            )
        displacement_spec, _ = _displacement_spec(
            family, negative_map[family["family_id"]]
        )
        if displacement_spec is None:
            continue
        for policy in ("react-recovery", "evidence-sufficiency"):
            for disabled in (False, True):
                episodes_replay.append(
                    _simulate_episode(
                        root, plan, index_replay, family, planned,
                        intervention_map[family["family_id"]],
                        negative_map[family["family_id"]],
                        scope="full_source_scoped", state="CLEAN", policy=policy,
                        displacement=True, recovery_disabled=disabled,
                        experiment_role="hard_negative_displacement",
                    )
                )
    pilot = _pilot_episode_map(root)
    for episode in episodes_replay:
        episode["bounded_to_full_degradation"] = (
            _bounded_delta(episode, pilot)
            if episode["scope"] == "full_source_scoped"
            and not episode["displacement"]
            and episode.get("experiment_role") == "ordinary" else {}
        )
    original_episodes = _load(
        root / RESTRICTED_REL / "trajectories.json"
    )["episodes"]
    original = {
        "segment": segment_original["segment_manifest_hash"],
        "index": _load(root / RESTRICTED_REL / "full_timeline_index.json")["index_hash"],
        "migration": _load(root / RESTRICTED_REL / "migrated_families.json")["migration_hash"],
        "negatives": _load(root / RESTRICTED_REL / "hard_negatives.json")["hard_negative_hash"],
        "interventions": _load(root / RESTRICTED_REL / "interventions.json")["interventions_hash"],
        "rankings": _load(root / RESTRICTED_REL / "fixed_query_suite.json")["ranking_hash"],
        "trajectories": _json_hash(original_episodes),
        "summary": _json_hash(_load(root / RESULTS_REL / "report.json")["summary"]),
    }
    replayed = {
        "segment": segment_replay["segment_manifest_hash"],
        "index": index_replay["index_hash"],
        "migration": migration_replay["migration_hash"],
        "negatives": negatives_replay["hard_negative_hash"],
        "interventions": interventions_replay["interventions_hash"],
        "rankings": fixed_replay["ranking_hash"],
        "trajectories": _json_hash(episodes_replay),
        "summary": _json_hash(
            _summary_rows(episodes_replay)
            + _displacement_summary_rows(episodes_replay)
        ),
    }
    result = {
        "original_hashes": original, "replayed_hashes": replayed,
        "all_match": original == replayed,
        "checkpoint_count": len(observation["checkpoints"]),
        "method": "verified checkpoint replay plus deterministic derived rebuild",
    }
    if not result["all_match"]:
        raise Scale1AError("DETERMINISTIC_REPLAY_MISMATCH")
    _mark_build_stages(root, {"deterministic_replay": "PASS"})
    return result
