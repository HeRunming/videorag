#!/usr/bin/env python3
"""Plan, validate, or build the exact EPIC P23_102 full-timeline index.

The default ``plan`` mode does not open media, load models, or write restricted
artifacts.  ``validate`` closes the acquisition and local-model gates without
running inference.  ``smoke`` and ``full`` are explicit execution modes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

import numpy as np

PIPELINE_TOKEN = "EPIC_P23_102_FULL_TIMELINE_PIPELINE_READY"
SCHEMA_VERSION = "av-trace.epic-p23-102-full-timeline/1.0"
INDEX_VERSION = "epic-p23-102-full-timeline-index/1.0"
STAGE = "RESTRICTED_DEVELOPMENT_ONLY_SOURCE_DERIVED_INDEX"
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
CHECKPOINT_LAYERS = (
    "source_probe",
    "speech_asr",
    "siglip2_visual",
    "clap_audio",
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
TOKEN_RE = re.compile(r"[a-z0-9]+")


class PipelineError(RuntimeError):
    """Fail-closed pipeline error."""


class AcquisitionPending(PipelineError):
    """The exact source has not passed its acquisition gate."""


class MediaBackend(Protocol):
    def probe(self, path: Path) -> Mapping[str, Any]: ...

    def iter_sampled_frames(
        self, path: Path, cells: Sequence[Mapping[str, Any]]
    ) -> Iterator[tuple[Mapping[str, Any], np.ndarray]]: ...

    def decode_audio(self, path: Path, target_rate: int) -> np.ndarray: ...


class ModelBackend(Protocol):
    def whisper(
        self, identifiers: Sequence[str], samples: Sequence[np.ndarray]
    ) -> Sequence[Mapping[str, Any]]: ...

    def siglip_images(self, images: Sequence[np.ndarray]) -> np.ndarray: ...

    def clap_audio(
        self, samples: Sequence[np.ndarray], rate: int
    ) -> np.ndarray: ...


def _repo_root_default() -> Path:
    return Path(__file__).resolve().parents[1]


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
    ).encode("utf-8")


def _json_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(16 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _md5(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(16 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(_canonical_bytes(value))
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _seal(document: dict[str, Any], key: str) -> dict[str, Any]:
    document[key] = _json_hash(document)
    return document


def _safe_path(root: Path, value: str | Path, *, label: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        try:
            candidate.resolve(strict=False).relative_to(root)
        except ValueError as exc:
            raise PipelineError(f"{label}_OUTSIDE_REPOSITORY:{value}") from exc
        if ".staging" in candidate.parts:
            raise PipelineError(f"{label}_UNSAFE:{value}")
        return candidate
    pure = PurePosixPath(str(candidate))
    if ".." in pure.parts or ".staging" in pure.parts:
        raise PipelineError(f"{label}_UNSAFE:{value}")
    path = root.joinpath(*pure.parts)
    try:
        path.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        raise PipelineError(f"{label}_OUTSIDE_REPOSITORY:{value}") from exc
    return path


def _relative(root: Path, path: Path) -> str:
    return path.resolve(strict=False).relative_to(root).as_posix()


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(text.casefold())


def _normalize(values: np.ndarray) -> np.ndarray:
    array = np.asarray(values, dtype=np.float32)
    if array.ndim == 1:
        array = array[None, :]
    norms = np.linalg.norm(array, axis=-1, keepdims=True)
    if not np.isfinite(array).all() or np.any(norms <= 1e-12):
        raise PipelineError("NONFINITE_OR_ZERO_EMBEDDING")
    return array / norms


def _f16_hex(vector: np.ndarray) -> str:
    return np.asarray(vector, dtype="<f2").tobytes().hex()


def _from_f16(value: str, dimension: int) -> np.ndarray:
    vector = np.frombuffer(bytes.fromhex(value), dtype="<f2").astype(np.float32)
    if len(vector) != dimension:
        raise PipelineError("VECTOR_DIMENSION_MISMATCH")
    return vector


def _pool(ids: Sequence[str], vectors: Mapping[str, np.ndarray]) -> np.ndarray:
    value = np.mean(np.stack([vectors[item] for item in ids]), axis=0)
    return _normalize(value)[0]


def expected_counts(duration_seconds: float) -> dict[str, int]:
    duration_us = round(duration_seconds * 1_000_000)
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
        "checkpoints": len(CHECKPOINT_LAYERS),
    }


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


def build_timeline(source_id: str, duration_seconds: float) -> dict[str, Any]:
    duration_us = round(duration_seconds * 1_000_000)
    base_cells = []
    for index, (start, end) in enumerate(
        _windows(duration_us, 4_000_000, 4_000_000, 1)
    ):
        base_cells.append(
            {
                "cell_id": f"{source_id}.base.{index:06d}",
                "source_ref": source_id,
                "start_us": start,
                "end_us": end,
                "sample_time_us": min(start + 2_000_000, duration_us - 1),
            }
        )
    segments = []
    for scale, length, stride, minimum in (
        ("fine", 8_000_000, 4_000_000, 4_000_000),
        ("context", 32_000_000, 16_000_000, 16_000_000),
    ):
        for index, (start, end) in enumerate(
            _windows(duration_us, length, stride, minimum)
        ):
            bound = [
                cell["cell_id"]
                for cell in base_cells
                if cell["start_us"] < end and cell["end_us"] > start
            ]
            segments.append(
                {
                    "segment_id": f"{source_id}.{scale}.{index:06d}",
                    "source_ref": source_id,
                    "scale": scale,
                    "start_us": start,
                    "end_us": end,
                    "binding_cell_ids": bound,
                }
            )
    speech_chunks = [
        {
            "chunk_id": f"{source_id}.speech.{index:06d}",
            "source_ref": source_id,
            "start_us": start,
            "end_us": end,
        }
        for index, (start, end) in enumerate(
            _windows(duration_us, 30_000_000, 30_000_000, 1)
        )
    ]
    return {
        "duration_us": duration_us,
        "base_cells": base_cells,
        "segments": segments,
        "speech_chunks": speech_chunks,
        "counts": expected_counts(duration_seconds),
    }


def _slice_audio(
    values: np.ndarray, start_us: int, end_us: int, rate: int
) -> np.ndarray:
    left = max(0, round(start_us * rate / 1_000_000))
    right = min(len(values), round(end_us * rate / 1_000_000))
    expected = max(1, round((end_us - start_us) * rate / 1_000_000))
    result = values[left:right]
    if len(result) < expected:
        result = np.pad(result, (0, expected - len(result)))
    result = result.astype(np.float32, copy=False)
    if not np.isfinite(result).all():
        raise PipelineError("AUDIO_SLICE_NONFINITE")
    return result


def load_plan(
    repo_root: str | Path,
    plan_path: str | Path = PLAN_RELATIVE_PATH,
    *,
    allow_synthetic_fixture: bool = False,
) -> tuple[Path, dict[str, Any]]:
    root = Path(repo_root).resolve()
    path = _safe_path(root, plan_path, label="PLAN_PATH")
    raw = _load(path)
    if raw.get("schema_version") != (
        "av-trace.epic-p23-102-full-timeline-index-plan/1.0"
    ):
        raise PipelineError("PLAN_SCHEMA_MISMATCH")
    if raw.get("source", {}).get("source_id") != "P23_102":
        raise PipelineError("PLAN_SOURCE_ID_MISMATCH")
    source = raw["source"]
    if source.get("expected_final_media_path") != (
        "data/restricted/epic_p23_102_source_v1/media/P23/P23_102.MP4"
    ):
        raise PipelineError("PLAN_MEDIA_PATH_MISMATCH")
    synthetic = raw.get("synthetic_fixture") is True
    if synthetic and not allow_synthetic_fixture:
        raise PipelineError("SYNTHETIC_FIXTURE_NOT_AUTHORIZED")
    if (
        not synthetic
        and source.get("official_md5") != "4698fcbf13782f6396029761eb3bd5f2"
    ):
        raise PipelineError("PLAN_OFFICIAL_MD5_MISMATCH")
    if raw.get("governance", {}).get("development_only") is not True:
        raise PipelineError("DEVELOPMENT_ONLY_BOUNDARY_MISSING")
    if raw["governance"].get("future_test_eligible") is not False:
        raise PipelineError("FUTURE_TEST_INELIGIBILITY_MISSING")
    if raw["governance"].get("license_spdx") != "CC-BY-NC-4.0":
        raise PipelineError("CC_BY_NC_BOUNDARY_MISSING")
    frozen = expected_counts(float(source["official_duration_seconds"]))
    if raw.get("totals") != frozen:
        raise PipelineError("PLAN_TIMELINE_COUNTS_MISMATCH")
    return path, raw


def _model_files(plan: Mapping[str, Any]) -> Iterator[tuple[str, Mapping[str, Any]]]:
    for model_name, model in sorted(plan["model_snapshots"].items()):
        for item in model["files"]:
            yield model_name, {"snapshot": model["snapshot_path"], **item}


def validate_models(
    root: Path, plan: Mapping[str, Any], *, hash_files: bool
) -> dict[str, Any]:
    binding = plan.get("model_acquisition_binding", {})
    binding_path = (
        _safe_path(
            root,
            binding["path"],
            label="MODEL_ACQUISITION_MANIFEST",
        )
        if binding.get("path")
        else None
    )
    binding_record = {
        "path": (
            _relative(root, binding_path) if binding_path is not None else None
        ),
        "present": bool(
            binding_path is not None
            and binding_path.is_file()
            and not binding_path.is_symlink()
        ),
        "verified": False,
    }
    if hash_files and plan.get("synthetic_fixture") is not True:
        if not binding_record["present"]:
            raise PipelineError("MODEL_ACQUISITION_MANIFEST_MISSING")
        if _sha256(binding_path) != binding.get("sha256"):
            raise PipelineError("MODEL_ACQUISITION_MANIFEST_HASH_MISMATCH")
        manifest = _load(binding_path)
        observed_decisions = {
            manifest.get("siglip2_decision"),
            manifest.get("clap_decision"),
            manifest.get("wave_r_decision"),
        }
        if not set(binding.get("required_decisions", [])) <= observed_decisions:
            raise PipelineError("MODEL_ACQUISITION_DECISION_MISMATCH")
        if manifest.get("technical_internal_use_authorized") is not True:
            raise PipelineError("MODEL_INTERNAL_USE_NOT_AUTHORIZED")
        if manifest.get("redistribution_authorized") is not False:
            raise PipelineError("MODEL_REDISTRIBUTION_BOUNDARY_MISMATCH")
        binding_record["verified"] = True
    records = []
    for model_name, item in _model_files(plan):
        path = _safe_path(
            root,
            Path(str(item["snapshot"])) / str(item["path"]),
            label=f"MODEL_{model_name.upper()}",
        )
        present = path.is_file() and not path.is_symlink()
        record = {
            "model": model_name,
            "path": _relative(root, path),
            "expected_bytes": int(item["bytes"]),
            "expected_sha256": str(item["sha256"]),
            "present": present,
            "verified": False,
        }
        if hash_files:
            if not present or path.stat().st_size != int(item["bytes"]):
                raise PipelineError(f"MODEL_FILE_IDENTITY:{model_name}:{path.name}")
            if _sha256(path) != item["sha256"]:
                raise PipelineError(f"MODEL_FILE_HASH:{model_name}:{path.name}")
            record["verified"] = True
        records.append(record)
    return {
        "acquisition_manifest": binding_record,
        "all_declared_files_present": all(item["present"] for item in records),
        "all_declared_files_hashed": hash_files
        and all(item["verified"] for item in records),
        "files": records,
    }


def load_source_binding(
    root: Path,
    plan: Mapping[str, Any],
    *,
    hash_media: bool,
    require_present: bool,
) -> dict[str, Any]:
    source = plan["source"]
    manifest_path = _safe_path(
        root, source["acquisition_manifest_path"], label="ACQUISITION_MANIFEST"
    )
    if not manifest_path.is_file():
        if require_present:
            raise AcquisitionPending("EXACT_ACQUISITION_MANIFEST_MISSING")
        return {
            "passed": False,
            "reason": "EXACT_ACQUISITION_MANIFEST_MISSING",
            "manifest_path": _relative(root, manifest_path),
        }
    manifest = _load(manifest_path)
    if manifest.get("status") != "COMPLETE_VERIFIED_READY":
        raise AcquisitionPending("EXACT_ACQUISITION_NOT_READY")
    if manifest.get("source", {}).get("asset_id") != source["source_id"]:
        raise PipelineError("ACQUISITION_ASSET_ID_MISMATCH")
    if manifest["source"].get("license") != "CC-BY-NC-4.0":
        raise PipelineError("ACQUISITION_LICENSE_MISMATCH")
    media = manifest.get("media", {})
    media_path = _safe_path(root, media.get("path", ""), label="MEDIA_PATH")
    expected_path = _safe_path(
        root, source["expected_final_media_path"], label="EXPECTED_MEDIA_PATH"
    )
    if media_path != expected_path:
        raise PipelineError("ACQUISITION_MEDIA_PATH_MISMATCH")
    expected = {
        "bytes": int(source["official_content_length_bytes"]),
        "md5": source["official_md5"],
    }
    if media.get("bytes") != expected["bytes"] or media.get("md5") != expected["md5"]:
        raise PipelineError("ACQUISITION_MEDIA_IDENTITY_MISMATCH")
    sha256 = str(media.get("sha256", ""))
    if not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise PipelineError("ACQUISITION_SHA256_MISSING")
    technical = manifest.get("technical_validation", {})
    if technical.get("ffprobe_passed") is not True:
        raise PipelineError("ACQUISITION_TECHNICAL_GATE_FAILED")
    if not technical.get("video") or not technical.get("audio"):
        raise PipelineError("ACQUISITION_NATIVE_AV_STREAMS_MISSING")
    required_streams = source["native_stream_requirements"]
    video = technical["video"]
    audio = technical["audio"]
    stream_checks = (
        video.get("codec_name") == required_streams["video_codec_name"],
        video.get("codec_tag_string") == required_streams["video_codec_tag"],
        video.get("width") == required_streams["video_width"],
        video.get("height") == required_streams["video_height"],
        audio.get("codec_name") == required_streams["audio_codec_name"],
        audio.get("codec_tag_string") == required_streams["audio_codec_tag"],
        audio.get("sample_rate_hz") == required_streams["audio_sample_rate_hz"],
        audio.get("channels") == required_streams["audio_channels"],
        audio.get("channel_layout") == required_streams["audio_layout"],
        float(technical.get("av_duration_delta_seconds", 0.0))
        <= float(required_streams["maximum_av_duration_delta_seconds"]),
    )
    if not all(stream_checks):
        raise PipelineError("ACQUISITION_STREAM_IDENTITY_MISMATCH")
    if manifest.get("scope", {}).get(
        "semantic_annotations_opened_or_used"
    ) is not False:
        raise PipelineError("SEMANTIC_ANNOTATION_BOUNDARY_VIOLATED")
    if hash_media:
        if not media_path.is_file() or media_path.is_symlink():
            raise AcquisitionPending("EXACT_FINAL_MEDIA_MISSING")
        if media_path.stat().st_size != expected["bytes"]:
            raise PipelineError("FINAL_MEDIA_BYTE_COUNT_MISMATCH")
        if _mode(media_path) != 0o600 or _mode(media_path.parent) != 0o700:
            raise PipelineError("FINAL_MEDIA_PERMISSION_MISMATCH")
        if _sha256(media_path) != sha256:
            raise PipelineError("FINAL_MEDIA_SHA256_MISMATCH")
        if _md5(media_path) != expected["md5"]:
            raise PipelineError("FINAL_MEDIA_MD5_MISMATCH")
    return {
        "passed": hash_media,
        "manifest_path": _relative(root, manifest_path),
        "manifest_sha256": _sha256(manifest_path),
        "media_path": _relative(root, media_path),
        "media_sha256": sha256,
        "media_md5": media["md5"],
        "media_bytes": media["bytes"],
        "technical_validation": technical,
        "license_and_usage_boundary": manifest.get(
            "license_and_usage_boundary", {}
        ),
    }


class PyAVMediaBackend:
    """Sequential decoder; frames and waveforms are never persisted."""

    def probe(self, path: Path) -> Mapping[str, Any]:
        try:
            import av
        except Exception as exc:  # pragma: no cover - environment dependent
            raise PipelineError("PYAV_IMPORT_FAILED") from exc
        with av.open(str(path), mode="r") as container:
            video = next((x for x in container.streams if x.type == "video"), None)
            audio = next((x for x in container.streams if x.type == "audio"), None)
            if video is None or audio is None:
                raise PipelineError("NATIVE_AV_STREAM_MISSING")
            return {
                "video_codec": video.codec_context.name,
                "audio_codec": audio.codec_context.name,
                "video_width": video.codec_context.width,
                "video_height": video.codec_context.height,
                "audio_rate_hz": audio.codec_context.sample_rate,
                "audio_channels": audio.codec_context.channels,
            }

    def iter_sampled_frames(
        self, path: Path, cells: Sequence[Mapping[str, Any]]
    ) -> Iterator[tuple[Mapping[str, Any], np.ndarray]]:
        import av

        targets = [int(item["sample_time_us"]) for item in cells]
        cursor = 0
        previous = None
        with av.open(str(path), mode="r") as container:
            stream = next((x for x in container.streams if x.type == "video"), None)
            if stream is None:
                raise PipelineError("VIDEO_STREAM_MISSING")
            for frame in container.decode(stream):
                if frame.pts is None:
                    continue
                frame_us = round(float(frame.pts * frame.time_base) * 1_000_000)
                while cursor < len(targets) and frame_us >= targets[cursor]:
                    chosen = previous or frame
                    yield cells[cursor], chosen.to_ndarray(format="rgb24")
                    cursor += 1
                if cursor == len(targets):
                    break
                previous = frame
        while cursor < len(targets) and previous is not None:
            yield cells[cursor], previous.to_ndarray(format="rgb24")
            cursor += 1
        if cursor != len(targets):
            raise PipelineError(f"FRAME_DECODE_INCOMPLETE:{cursor}/{len(targets)}")

    def decode_audio(self, path: Path, target_rate: int) -> np.ndarray:
        import av

        parts = []
        with av.open(str(path), mode="r") as container:
            stream = next((x for x in container.streams if x.type == "audio"), None)
            if stream is None:
                raise PipelineError("AUDIO_STREAM_MISSING")
            resampler = av.audio.resampler.AudioResampler(
                format="fltp", layout="mono", rate=target_rate
            )
            for frame in container.decode(stream):
                for converted in resampler.resample(frame):
                    parts.append(
                        converted.to_ndarray().reshape(-1).astype(np.float32)
                    )
            for converted in resampler.resample(None):
                parts.append(
                    converted.to_ndarray().reshape(-1).astype(np.float32)
                )
        if not parts:
            raise PipelineError("AUDIO_DECODE_EMPTY")
        values = np.concatenate(parts)
        if not np.isfinite(values).all():
            raise PipelineError("AUDIO_DECODE_NONFINITE")
        return values


class LocalFrozenModels:
    """Lazy CPU-only local model backend."""

    def __init__(self, root: Path, plan: Mapping[str, Any], *, threads: int) -> None:
        if "long" not in np.__dict__:
            np.long = np.int64  # type: ignore[attr-defined]
        if "ulong" not in np.__dict__:
            np.ulong = np.uint64  # type: ignore[attr-defined]
        os.environ.update(
            {
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
                "HF_DATASETS_OFFLINE": "1",
            }
        )
        os.environ.pop("HF_TOKEN", None)
        import torch

        torch.manual_seed(0)
        torch.use_deterministic_algorithms(True)
        torch.set_num_threads(max(1, threads))
        try:
            torch.set_num_interop_threads(1)
        except RuntimeError:
            pass
        self.root = root
        self.plan = plan
        self.torch = torch
        self._whisper = None
        self._siglip = None
        self._clap = None

    def _path(self, name: str) -> Path:
        return _safe_path(
            self.root,
            self.plan["model_snapshots"][name]["snapshot_path"],
            label=f"MODEL_{name.upper()}",
        )

    def whisper(
        self, identifiers: Sequence[str], samples: Sequence[np.ndarray]
    ) -> Sequence[Mapping[str, Any]]:
        if self._whisper is None:
            from transformers import (
                WhisperForConditionalGeneration,
                WhisperProcessor,
            )

            path = self._path("speech")
            processor = WhisperProcessor.from_pretrained(
                path, local_files_only=True
            )
            model = WhisperForConditionalGeneration.from_pretrained(
                path, local_files_only=True
            ).eval()
            self._whisper = (processor, model)
        processor, model = self._whisper
        inputs = processor(
            list(samples),
            sampling_rate=16_000,
            return_tensors="pt",
            padding=True,
            return_attention_mask=True,
        )
        with self.torch.inference_mode():
            generated = model.generate(
                inputs.input_features,
                attention_mask=inputs.attention_mask,
                do_sample=False,
                num_beams=1,
                max_new_tokens=128,
                return_dict_in_generate=True,
                output_scores=True,
                return_timestamps=False,
            )
            scores = model.compute_transition_scores(
                generated.sequences,
                generated.scores,
                normalize_logits=True,
            )
        special = set(processor.tokenizer.all_special_ids)
        output = []
        for row, sequence in enumerate(generated.sequences):
            count = scores.shape[1]
            token_ids = sequence[-count:].tolist() if count else []
            lexical = [
                float(score)
                for token, score in zip(token_ids, scores[row].tolist())
                if token not in special
            ]
            text = " ".join(
                processor.tokenizer.decode(
                    sequence, skip_special_tokens=True
                ).split()
            )
            mean = float(np.mean(lexical)) if lexical else None
            flags = []
            if len(lexical) < 5:
                flags.append("TOO_FEW_LEXICAL_TOKENS")
            if mean is None or mean < -0.85:
                flags.append("LOW_GENERATED_TOKEN_LOGPROB")
            output.append(
                {
                    "chunk_id": identifiers[row],
                    "text": text,
                    "token_count": len(lexical),
                    "mean_generated_token_log_probability": (
                        round(mean, 8) if mean is not None else None
                    ),
                    "quality_gate_pass": bool(text) and not flags,
                    "quality_flags": flags,
                }
            )
        return output

    def siglip_images(self, images: Sequence[np.ndarray]) -> np.ndarray:
        if self._siglip is None:
            from transformers import SiglipModel, SiglipProcessor

            path = self._path("vision")
            processor = SiglipProcessor.from_pretrained(
                path, local_files_only=True, use_fast=False
            )
            model = SiglipModel.from_pretrained(path, local_files_only=True).eval()
            self._siglip = (processor, model)
        processor, model = self._siglip
        inputs = processor(images=list(images), return_tensors="pt")
        with self.torch.inference_mode():
            values = model.get_image_features(**inputs)
        if hasattr(values, "pooler_output"):
            values = values.pooler_output
        return _normalize(values.float().cpu().numpy())

    def clap_audio(
        self, samples: Sequence[np.ndarray], rate: int
    ) -> np.ndarray:
        if self._clap is None:
            from transformers import ClapModel, ClapProcessor

            path = self._path("audio")
            processor = ClapProcessor.from_pretrained(path, local_files_only=True)
            model = ClapModel.from_pretrained(path, local_files_only=True).eval()
            self._clap = (processor, model)
        processor, model = self._clap
        inputs = processor(
            audio=list(samples),
            sampling_rate=rate,
            padding=True,
            return_tensors="pt",
        )
        with self.torch.inference_mode():
            values = model.get_audio_features(
                input_features=inputs.input_features,
                is_longer=getattr(inputs, "is_longer", None),
                attention_mask=getattr(inputs, "attention_mask", None),
            )
        if hasattr(values, "pooler_output"):
            values = values.pooler_output
        return _normalize(values.float().cpu().numpy())


def _checkpoint_key(
    *,
    source_sha256: str,
    layer: str,
    layer_version: str,
    config_hash: str,
) -> str:
    return _json_hash(
        {
            "source_sha256": source_sha256,
            "layer": layer,
            "layer_version": layer_version,
            "shard_index": 0,
            "config_hash": config_hash,
        }
    )


def _read_checkpoint(
    path: Path, *, key: str, record_count: int
) -> Mapping[str, Any] | None:
    if not path.is_file() or path.is_symlink() or _mode(path) != 0o600:
        return None
    try:
        document = _load(path)
        payload = document["payload"]
        valid = (
            document.get("schema_version") == SCHEMA_VERSION
            and document.get("checkpoint_key") == key
            and document.get("record_count") == record_count
            and document.get("payload_hash") == _json_hash(payload)
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        valid = False
    return document if valid else None


def _write_checkpoint(
    path: Path,
    *,
    layer: str,
    layer_version: str,
    source_sha256: str,
    config_hash: str,
    record_count: int,
    payload: Mapping[str, Any],
) -> Mapping[str, Any]:
    document = {
        "schema_version": SCHEMA_VERSION,
        "layer": layer,
        "layer_version": layer_version,
        "source_sha256": source_sha256,
        "config_hash": config_hash,
        "checkpoint_key": _checkpoint_key(
            source_sha256=source_sha256,
            layer=layer,
            layer_version=layer_version,
            config_hash=config_hash,
        ),
        "record_count": record_count,
        "payload": dict(payload),
        "payload_hash": _json_hash(payload),
    }
    _atomic_dump(path, document)
    return document


def _checkpoint(
    path: Path,
    *,
    resume: bool,
    layer: str,
    layer_version: str,
    source_sha256: str,
    config_hash: str,
    record_count: int,
    producer: Any,
) -> tuple[Mapping[str, Any], bool]:
    key = _checkpoint_key(
        source_sha256=source_sha256,
        layer=layer,
        layer_version=layer_version,
        config_hash=config_hash,
    )
    current = (
        _read_checkpoint(path, key=key, record_count=record_count)
        if resume
        else None
    )
    if current is not None:
        return current, True
    path.unlink(missing_ok=True)
    return (
        _write_checkpoint(
            path,
            layer=layer,
            layer_version=layer_version,
            source_sha256=source_sha256,
            config_hash=config_hash,
            record_count=record_count,
            payload=producer(),
        ),
        False,
    )


def _checkpoint_meta(root: Path, path: Path, document: Mapping[str, Any]) -> dict:
    return {
        "layer": document["layer"],
        "path": _relative(root, path),
        "checkpoint_key": document["checkpoint_key"],
        "record_count": document["record_count"],
        "payload_hash": document["payload_hash"],
        "size_bytes": path.stat().st_size,
        "sha256": "sha256:" + _sha256(path),
    }


def _speech_index(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    documents = []
    document_frequency: Counter[str] = Counter()
    total_length = 0
    for record in records:
        tokens = _tokens(str(record.get("text", "")))
        frequencies = Counter(tokens)
        document_frequency.update(frequencies.keys())
        total_length += len(tokens)
        documents.append(
            {
                **dict(record),
                "term_frequency": dict(sorted(frequencies.items())),
                "document_length": len(tokens),
            }
        )
    return {
        "ranker": "bm25-okapi/1.0",
        "documents": documents,
        "document_frequency": dict(sorted(document_frequency.items())),
        "average_document_length": (
            total_length / len(documents) if documents else 0.0
        ),
    }


def search_speech(
    index: Mapping[str, Any], query: str, *, top_k: int = 10
) -> list[dict[str, Any]]:
    modality = index["modalities"]["speech"]
    documents = modality["documents"]
    n = len(documents)
    average = float(modality["average_document_length"]) or 1.0
    output = []
    for document in documents:
        if not document.get("searchable"):
            continue
        score = 0.0
        for token in _tokens(query):
            frequency = document["term_frequency"].get(token, 0)
            if not frequency:
                continue
            df = modality["document_frequency"].get(token, 0)
            inverse = math.log(1 + (n - df + 0.5) / (df + 0.5))
            denominator = frequency + 1.2 * (
                0.25 + 0.75 * document["document_length"] / average
            )
            score += inverse * frequency * 2.2 / denominator
        if score:
            output.append(
                {
                    "chunk_id": document["chunk_id"],
                    "start_us": document["start_us"],
                    "end_us": document["end_us"],
                    "score": round(score, 8),
                }
            )
    output.sort(key=lambda item: (-item["score"], item["chunk_id"]))
    return output[:top_k]


def search_vector(
    index: Mapping[str, Any],
    modality: str,
    query_vector: Sequence[float],
    *,
    top_k: int = 10,
) -> list[dict[str, Any]]:
    query = _normalize(np.asarray(query_vector, dtype=np.float32))[0]
    output = []
    for document in index["modalities"][modality]["documents"]:
        vector = _from_f16(document["vector_f16_hex"], document["dimension"])
        if len(vector) != len(query):
            raise PipelineError("QUERY_VECTOR_DIMENSION_MISMATCH")
        score = float(np.dot(_normalize(vector)[0], query))
        output.append(
            {
                "segment_id": document["segment_id"],
                "start_us": document["start_us"],
                "end_us": document["end_us"],
                "score": round(score, 8),
            }
        )
    output.sort(key=lambda item: (-item["score"], item["segment_id"]))
    return output[:top_k]


def build_index(
    repo_root: str | Path,
    *,
    plan_path: str | Path = PLAN_RELATIVE_PATH,
    output_root: str | Path | None = None,
    smoke_seconds: float | None = None,
    resume: bool = True,
    threads: int = 8,
    media_backend: MediaBackend | None = None,
    model_backend: ModelBackend | None = None,
    validate_model_files: bool = True,
    allow_synthetic_fixture: bool = False,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    plan_file, plan = load_plan(
        root,
        plan_path,
        allow_synthetic_fixture=allow_synthetic_fixture,
    )
    if threads < 1:
        raise PipelineError("THREAD_COUNT_MUST_BE_POSITIVE")
    source_binding = load_source_binding(
        root, plan, hash_media=True, require_present=True
    )
    model_validation = validate_models(
        root, plan, hash_files=validate_model_files
    )
    if validate_model_files and not model_validation["all_declared_files_hashed"]:
        raise PipelineError("MODEL_VALIDATION_INCOMPLETE")
    source = plan["source"]
    duration = float(source["official_duration_seconds"])
    if smoke_seconds is not None:
        if smoke_seconds <= 0:
            raise PipelineError("SMOKE_SECONDS_MUST_BE_POSITIVE")
        duration = min(duration, smoke_seconds)
    default_output = (
        plan["scope"]["smoke_output_root"]
        if smoke_seconds is not None
        else plan["scope"]["output_root"]
    )
    output = _safe_path(
        root, output_root or default_output, label="OUTPUT_ROOT"
    )
    source_root = _safe_path(
        root, plan["scope"]["source_root"], label="SOURCE_ROOT"
    )
    if output == source_root or source_root in output.parents:
        raise PipelineError("OUTPUT_OVERLAPS_SOURCE_ROOT")
    output.mkdir(parents=True, exist_ok=True)
    output.chmod(0o700)
    media_path = _safe_path(
        root, source_binding["media_path"], label="MEDIA_PATH"
    )
    media = media_backend or PyAVMediaBackend()
    models = model_backend or LocalFrozenModels(root, plan, threads=threads)
    timeline = build_timeline(source["source_id"], duration)
    counts = timeline["counts"]
    plan_hash = _json_hash(plan)
    config = {
        "index_version": INDEX_VERSION,
        "plan_hash": plan_hash,
        "source_sha256": source_binding["media_sha256"],
        "duration_us": timeline["duration_us"],
        "smoke_seconds": smoke_seconds,
        "threads": threads,
        "deterministic_cpu_only": True,
        "segmentation": plan["segmentation"],
        "models": {
            name: {
                "model_id": item["model_id"],
                "revision": item["revision"],
                "dimension": item.get("dimension"),
            }
            for name, item in sorted(plan["model_snapshots"].items())
        },
    }
    config_hash = _json_hash(config)
    checkpoint_dir = output / "checkpoints" / source["source_id"]
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_dir.chmod(0o700)
    checkpoint_rows = []

    probe_path = checkpoint_dir / "source_probe.json"
    probe_doc, _ = _checkpoint(
        probe_path,
        resume=resume,
        layer="source_probe",
        layer_version="pyav-native-av-probe/1.0",
        source_sha256=source_binding["media_sha256"],
        config_hash=config_hash,
        record_count=1,
        producer=lambda: {
            "source_ref": source["source_id"],
            "probe": dict(media.probe(media_path)),
            "acquisition_technical_validation": source_binding[
                "technical_validation"
            ],
            "semantic_observation": False,
        },
    )
    checkpoint_rows.append(_checkpoint_meta(root, probe_path, probe_doc))

    speech_path = checkpoint_dir / "speech_asr.json"

    def produce_speech() -> dict[str, Any]:
        rate = int(plan["model_snapshots"]["speech"]["sample_rate_hz"])
        waveform = media.decode_audio(media_path, rate)
        records = []
        batch_size = int(plan["execution"]["speech_batch_size"])
        chunks = timeline["speech_chunks"]
        for offset in range(0, len(chunks), batch_size):
            batch = chunks[offset : offset + batch_size]
            samples = [
                _slice_audio(waveform, item["start_us"], item["end_us"], rate)
                for item in batch
            ]
            observed = models.whisper(
                [item["chunk_id"] for item in batch], samples
            )
            if len(observed) != len(batch):
                raise PipelineError("ASR_BATCH_CARDINALITY_MISMATCH")
            for spec, sample, result in zip(batch, samples, observed):
                text = " ".join(str(result.get("text", "")).split())
                quality = bool(result.get("quality_gate_pass", bool(text)))
                records.append(
                    {
                        **spec,
                        "text": text,
                        "searchable": quality and bool(text),
                        "routing": (
                            "bm25_searchable"
                            if quality and text
                            else "inventory_only"
                        ),
                        "quality_gate_pass": quality,
                        "quality_flags": list(result.get("quality_flags", [])),
                        "token_count": int(result.get("token_count", 0)),
                        "mean_generated_token_log_probability": result.get(
                            "mean_generated_token_log_probability"
                        ),
                        "audio_rms_full_scale": round(
                            float(
                                np.sqrt(
                                    np.mean(
                                        np.square(sample, dtype=np.float64)
                                    )
                                )
                            ),
                            10,
                        ),
                        "model_observation_not_human_annotation": True,
                    }
                )
        del waveform
        return {
            "sample_rate_hz": rate,
            "chunks": records,
            "no_persisted_audio": True,
        }

    speech_doc, _ = _checkpoint(
        speech_path,
        resume=resume,
        layer="speech_asr",
        layer_version=plan["model_snapshots"]["speech"]["layer_version"],
        source_sha256=source_binding["media_sha256"],
        config_hash=config_hash,
        record_count=counts["speech_chunks"],
        producer=produce_speech,
    )
    checkpoint_rows.append(_checkpoint_meta(root, speech_path, speech_doc))

    vision_path = checkpoint_dir / "siglip2_visual.json"

    def produce_vision() -> dict[str, Any]:
        cell_records = []
        batch_images: list[np.ndarray] = []
        batch_cells: list[Mapping[str, Any]] = []
        batch_size = int(plan["execution"]["vision_batch_size"])

        def flush() -> None:
            if not batch_images:
                return
            vectors = _normalize(models.siglip_images(batch_images))
            if len(vectors) != len(batch_images):
                raise PipelineError("SIGLIP2_BATCH_CARDINALITY_MISMATCH")
            for cell, vector in zip(batch_cells, vectors):
                cell_records.append(
                    {
                        "cell_id": cell["cell_id"],
                        "sample_time_us": cell["sample_time_us"],
                        "vector_f16_hex": _f16_hex(vector),
                        "dimension": len(vector),
                        "l2_normalized": True,
                    }
                )
            batch_images.clear()
            batch_cells.clear()

        for cell, image in media.iter_sampled_frames(
            media_path, timeline["base_cells"]
        ):
            batch_cells.append(cell)
            batch_images.append(image)
            if len(batch_images) >= batch_size:
                flush()
        flush()
        by_cell = {
            item["cell_id"]: _from_f16(
                item["vector_f16_hex"], item["dimension"]
            )
            for item in cell_records
        }
        segment_records = []
        for segment in timeline["segments"]:
            vector = _pool(segment["binding_cell_ids"], by_cell)
            segment_records.append(
                {
                    "segment_id": segment["segment_id"],
                    "source_ref": source["source_id"],
                    "scale": segment["scale"],
                    "start_us": segment["start_us"],
                    "end_us": segment["end_us"],
                    "vector_f16_hex": _f16_hex(vector),
                    "dimension": len(vector),
                    "l2_normalized": True,
                    "searchable": True,
                }
            )
        return {
            "cell_vectors": cell_records,
            "segment_vectors": segment_records,
            "no_persisted_frames": True,
        }

    vision_doc, _ = _checkpoint(
        vision_path,
        resume=resume,
        layer="siglip2_visual",
        layer_version=plan["model_snapshots"]["vision"]["layer_version"],
        source_sha256=source_binding["media_sha256"],
        config_hash=config_hash,
        record_count=counts["base_cells"] + counts["temporal_segments"],
        producer=produce_vision,
    )
    checkpoint_rows.append(_checkpoint_meta(root, vision_path, vision_doc))

    clap_path = checkpoint_dir / "clap_audio.json"

    def produce_clap() -> dict[str, Any]:
        rate = int(plan["model_snapshots"]["audio"]["sample_rate_hz"])
        waveform = media.decode_audio(media_path, rate)
        fine = [
            item for item in timeline["segments"] if item["scale"] == "fine"
        ]
        context = [
            item for item in timeline["segments"] if item["scale"] == "context"
        ]
        records = []
        batch_size = int(plan["execution"]["audio_batch_size"])
        for offset in range(0, len(fine), batch_size):
            batch = fine[offset : offset + batch_size]
            samples = [
                _slice_audio(waveform, item["start_us"], item["end_us"], rate)
                for item in batch
            ]
            vectors = _normalize(models.clap_audio(samples, rate))
            if len(vectors) != len(batch):
                raise PipelineError("CLAP_BATCH_CARDINALITY_MISMATCH")
            for spec, sample, vector in zip(batch, samples, vectors):
                rms = float(
                    np.sqrt(np.mean(np.square(sample, dtype=np.float64)))
                )
                records.append(
                    {
                        "segment_id": spec["segment_id"],
                        "source_ref": source["source_id"],
                        "scale": "fine",
                        "start_us": spec["start_us"],
                        "end_us": spec["end_us"],
                        "vector_f16_hex": _f16_hex(vector),
                        "dimension": len(vector),
                        "l2_normalized": True,
                        "searchable": True,
                        "audio_rms_full_scale": round(rms, 10),
                        "quality_flags": (
                            ["NEAR_SILENCE"] if rms < 1e-5 else []
                        ),
                    }
                )
        by_fine = {
            item["segment_id"]: _from_f16(
                item["vector_f16_hex"], item["dimension"]
            )
            for item in records
        }
        for segment in context:
            overlapping = [
                item["segment_id"]
                for item in fine
                if item["start_us"] < segment["end_us"]
                and item["end_us"] > segment["start_us"]
            ]
            vector = _pool(overlapping, by_fine)
            records.append(
                {
                    "segment_id": segment["segment_id"],
                    "source_ref": source["source_id"],
                    "scale": "context",
                    "start_us": segment["start_us"],
                    "end_us": segment["end_us"],
                    "vector_f16_hex": _f16_hex(vector),
                    "dimension": len(vector),
                    "l2_normalized": True,
                    "searchable": True,
                    "derived_from_fine_ids": overlapping,
                    "quality_flags": [],
                }
            )
        del waveform
        return {
            "sample_rate_hz": rate,
            "segment_vectors": records,
            "no_persisted_audio": True,
        }

    clap_doc, _ = _checkpoint(
        clap_path,
        resume=resume,
        layer="clap_audio",
        layer_version=plan["model_snapshots"]["audio"]["layer_version"],
        source_sha256=source_binding["media_sha256"],
        config_hash=config_hash,
        record_count=counts["temporal_segments"],
        producer=produce_clap,
    )
    checkpoint_rows.append(_checkpoint_meta(root, clap_path, clap_doc))

    governance = {
        **plan["governance"],
        "semantic_annotations_used_during_source_selection": False,
        "human_review_performed": False,
        "ses_assigned": False,
        "h_tier_assigned": False,
        "gate_a_claimed": False,
        "no_semantic_source_selection_claim": True,
    }
    segment_manifest = _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "stage": STAGE,
            "source_ref": source["source_id"],
            "source_sha256": source_binding["media_sha256"],
            "duration_us": timeline["duration_us"],
            "base_cells": timeline["base_cells"],
            "segments": timeline["segments"],
            "speech_chunks": timeline["speech_chunks"],
            "counts": counts,
            "governance": governance,
        },
        "segment_manifest_hash",
    )
    observation_manifest = _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "stage": STAGE,
            "segment_manifest_hash": segment_manifest["segment_manifest_hash"],
            "config": config,
            "config_hash": config_hash,
            "counts": {
                "speech_chunks": len(speech_doc["payload"]["chunks"]),
                "siglip2_cells": len(
                    vision_doc["payload"]["cell_vectors"]
                ),
                "siglip2_segments": len(
                    vision_doc["payload"]["segment_vectors"]
                ),
                "clap_segments": len(
                    clap_doc["payload"]["segment_vectors"]
                ),
            },
            "checkpoint_payload_hashes": {
                item["layer"]: item["payload_hash"] for item in checkpoint_rows
            },
            "no_persisted_media_derivatives": True,
            "governance": governance,
        },
        "observation_manifest_hash",
    )
    index = _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "index_version": INDEX_VERSION,
            "stage": STAGE,
            "source_ref": source["source_id"],
            "segment_manifest_hash": segment_manifest["segment_manifest_hash"],
            "observation_manifest_hash": observation_manifest[
                "observation_manifest_hash"
            ],
            "retrieval_hooks": {
                "speech": "search_speech(index, query, top_k=N)",
                "siglip2_visual": (
                    "encode query with pinned SigLIP2 text tower, then "
                    "search_vector(index, 'siglip2_visual', vector)"
                ),
                "clap_audio": (
                    "encode query with pinned CLAP text tower, then "
                    "search_vector(index, 'clap_audio', vector)"
                ),
            },
            "modalities": {
                "speech": _speech_index(speech_doc["payload"]["chunks"]),
                "siglip2_visual": {
                    "ranker": "siglip2-text-image-cosine/1.0",
                    "documents": vision_doc["payload"]["segment_vectors"],
                },
                "clap_audio": {
                    "ranker": "clap-text-audio-cosine/1.0",
                    "documents": clap_doc["payload"]["segment_vectors"],
                },
            },
            "governance": governance,
        },
        "index_hash",
    )
    resource_manifest = _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "stage": STAGE,
            "source": {
                key: source_binding[key]
                for key in (
                    "manifest_path",
                    "manifest_sha256",
                    "media_path",
                    "media_sha256",
                    "media_md5",
                    "media_bytes",
                )
            },
            "models": {
                name: {
                    "model_id": item["model_id"],
                    "revision": item["revision"],
                    "snapshot_path": item["snapshot_path"],
                    "dimension": item.get("dimension"),
                    "local_files_only": True,
                }
                for name, item in sorted(plan["model_snapshots"].items())
            },
            "model_files_verified": model_validation[
                "all_declared_files_hashed"
            ],
            "runtime": {
                "device": "cpu",
                "threads": threads,
                "network_access": "disabled",
                "deterministic_algorithms": True,
            },
            "resource_estimate": plan["resource_estimate"],
            "governance": governance,
        },
        "resource_manifest_hash",
    )
    checkpoint_manifest = _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "stage": STAGE,
            "config_hash": config_hash,
            "source_sha256": source_binding["media_sha256"],
            "checkpoints": checkpoint_rows,
            "checkpoint_count": len(checkpoint_rows),
            "resume_policy": (
                "reuse only exact source/layer/config key, record count, "
                "payload hash, file hash, mode, and path"
            ),
        },
        "checkpoint_manifest_hash",
    )
    documents = {
        "segment_manifest.json": segment_manifest,
        "observation_manifest.json": observation_manifest,
        "full_timeline_index.json": index,
        "resource_manifest.json": resource_manifest,
        "checkpoint_manifest.json": checkpoint_manifest,
    }
    for name, document in documents.items():
        _atomic_dump(output / name, document)
    artifacts = [
        {
            "path": _relative(root, output / name),
            "size_bytes": (output / name).stat().st_size,
            "sha256": "sha256:" + _sha256(output / name),
        }
        for name in documents
    ]
    build_manifest = {
        "schema_version": SCHEMA_VERSION,
        "index_version": INDEX_VERSION,
        "stage": STAGE,
        "status": "COMPLETE",
        "decision": PIPELINE_TOKEN,
        "output_dir": _relative(root, output),
        "plan_path": _relative(root, plan_file),
        "plan_hash": plan_hash,
        "config_hash": config_hash,
        "source_ref": source["source_id"],
        "source_sha256": source_binding["media_sha256"],
        "smoke_seconds": smoke_seconds,
        "checkpoint_count": len(checkpoint_rows),
        "artifact_hashes": artifacts,
        "terminal_boundary": {
            "index_only": True,
            "semantic_annotations_generated": False,
            "families_generated": False,
            "interventions_generated": False,
            "trajectories_generated": False,
            "evaluation_generated": False,
            "human_or_ses_or_h_or_gate_claim_generated": False,
        },
        "governance": governance,
    }
    derived_bytes = sum(
        path.stat().st_size
        for path in output.rglob("*")
        if path.is_file() and path.name != "build_manifest.json"
    )
    build_manifest["derived_artifact_bytes_before_build_manifest"] = derived_bytes
    hard_cap = int(plan["storage"]["hard_cap_mib"]) * 1024 * 1024
    if derived_bytes > hard_cap:
        raise PipelineError("DERIVED_ARTIFACT_HARD_CAP_EXCEEDED")
    _seal(build_manifest, "build_manifest_hash")
    _atomic_dump(output / "build_manifest.json", build_manifest)
    persisted_media = [
        _relative(root, path)
        for path in output.rglob("*")
        if path.is_file() and path.suffix.casefold() in MEDIA_SUFFIXES
    ]
    if persisted_media:
        raise PipelineError("PERSISTED_MEDIA_DERIVATIVE")
    return {
        "segment_manifest": segment_manifest,
        "observation_manifest": observation_manifest,
        "full_timeline_index": index,
        "resource_manifest": resource_manifest,
        "checkpoint_manifest": checkpoint_manifest,
        "build_manifest": build_manifest,
    }


def plan_or_validate(
    repo_root: str | Path,
    *,
    plan_path: str | Path = PLAN_RELATIVE_PATH,
    validate: bool,
    allow_synthetic_fixture: bool = False,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    path, plan = load_plan(
        root,
        plan_path,
        allow_synthetic_fixture=allow_synthetic_fixture,
    )
    acquisition = load_source_binding(
        root,
        plan,
        hash_media=validate,
        require_present=validate,
    )
    models = validate_models(root, plan, hash_files=validate)
    return {
        "decision": PIPELINE_TOKEN,
        "status": (
            "VALIDATED_READY_FOR_EXECUTION"
            if validate
            else (
                "PLANNED_READY_FOR_POST_ACQUISITION_EXECUTION"
                if acquisition["passed"]
                else "PLANNED_ACQUISITION_PENDING"
            )
        ),
        "mode": "validate" if validate else "plan",
        "plan": _relative(root, path),
        "source_ref": plan["source"]["source_id"],
        "expected_counts": plan["totals"],
        "acquisition_gate": acquisition,
        "model_gate": models,
        "media_decoded": False,
        "models_loaded": False,
        "artifacts_written": False,
        "network_access": "disabled",
        "governance": plan["governance"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(_repo_root_default()))
    parser.add_argument("--plan", default=str(PLAN_RELATIVE_PATH))
    parser.add_argument(
        "--mode",
        choices=("plan", "validate", "smoke", "full"),
        default="plan",
    )
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--smoke-seconds", type=float, default=32.0)
    parser.add_argument(
        "--resume", action=argparse.BooleanOptionalAction, default=True
    )
    parser.add_argument("--threads", type=int, default=8)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.mode in {"plan", "validate"}:
            result = plan_or_validate(
                args.repo_root,
                plan_path=args.plan,
                validate=args.mode == "validate",
            )
        else:
            built = build_index(
                args.repo_root,
                plan_path=args.plan,
                output_root=args.output_root,
                smoke_seconds=(
                    args.smoke_seconds if args.mode == "smoke" else None
                ),
                resume=args.resume,
                threads=args.threads,
            )
            result = {
                "decision": PIPELINE_TOKEN,
                "status": "COMPLETE",
                "mode": args.mode,
                "output_root": built["build_manifest"]["output_dir"],
                "build_manifest_hash": built["build_manifest"][
                    "build_manifest_hash"
                ],
                "checkpoint_count": built["build_manifest"][
                    "checkpoint_count"
                ],
            }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except AcquisitionPending as exc:
        print(
            json.dumps(
                {
                    "decision": PIPELINE_TOKEN,
                    "status": "BLOCKED_BY_ACQUISITION",
                    "error": str(exc),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 2
    except (OSError, PipelineError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "decision": PIPELINE_TOKEN,
                    "status": "FAILED_CLOSED",
                    "error": str(exc),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
