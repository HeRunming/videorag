#!/usr/bin/env python3
"""Deterministic restricted content reconnaissance for the exact NOAA-01 media.

Decoded audio and video exist only in child-process memory.  The parent writes
metadata JSON/JSONL, a redaction-safe review, and a result note.  It does not
write frames, audio, clips, contact sheets, waveforms, or transcripts.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import importlib.metadata
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SCHEMA_VERSION = "1.0"
RECON_ID = "NOAA-01-RESTRICTED-CONTENT-RECON"
RUN_DATE = "2026-09-09"
PLAN_REL = Path("data/acquisition_plan/noaa01_exact_asset_plan.json")
ACQUISITION_MANIFEST_REL = Path(
    "data/restricted/noaa01/manifests/noaa01_acquisition_manifest.json"
)
MEDIA_AUDIT_REL = Path("data/restricted/noaa01/manifests/noaa01_media_audit.json")
AUTHORIZATION_REL = Path("data/access_review/noaa01_content_recon_authorization.json")
RESTRICTED_ROOT_REL = Path("data/restricted/noaa01")
MEASUREMENTS_REL = RESTRICTED_ROOT_REL / "recon/noaa01_window_measurements.jsonl"
CANDIDATES_REL = RESTRICTED_ROOT_REL / "recon/noaa01_candidate_windows.json"
MANIFEST_REL = RESTRICTED_ROOT_REL / "recon/noaa01_content_recon_manifest.json"
REVIEW_REL = Path("docs/review/noaa01_content_recon.md")
RESULT_REL = Path("orchestration/results/80_noaa_content_recon.txt")

EXPECTED_CANDIDATES = ("cand-045", "cand-047", "cand-049", "cand-051", "cand-052")
EXPECTED_PAYLOAD_BYTES = 1_955_298_193
EXPECTED_PLAN_SHA256 = "241a476b503a198eafe208485206385f755cd57756f924e769ce8a37d1d1f6fd"
EXPECTED_ACQUISITION_MANIFEST_SHA256 = (
    "92b7a1ff740d79a4253071018dc18cc3cb41570ccc62dfb08ff2a9c1c48fe2a1"
)
EXPECTED_MEDIA_AUDIT_SHA256 = (
    "b8c743f48ad328cda46be2ea2569759da95262b404e3f3647eef2d9c2e2efde9"
)

WINDOW_SECONDS = 8.0
COARSE_WINDOWS_PER_ASSET = 18
MAX_ADAPTIVE_WINDOWS_PER_ASSET = 6
MAX_CANDIDATES_PER_ASSET = 6
TARGET_CANDIDATE_COUNT = 30
CHILD_TIMEOUT_SECONDS = 180
MAX_VIDEO_FRAMES = 9
AUDIO_TARGET_RATE = 16_000
AUDIO_FRAME_SECONDS = 0.02

# Thresholds are fixed before observing the corpus.  They are intentionally
# conservative candidate signals, not semantic or gold-label criteria.
SILENCE_FRAME_RMS = 0.003
ACTIVE_RMS = 0.008
ACTIVE_PEAK = 0.04
SPEECH_SCORE_THRESHOLD = 0.55
SPEECH_SCORE_STRONG = 0.68
NON_SPEECH_SCORE_THRESHOLD = 0.58
VISUAL_CHANGE_THRESHOLD = 0.025
VISUAL_STRONG_THRESHOLD = 0.055
SCENE_CUT_THRESHOLD = 0.12

ASR_MODEL_ID = "openai/whisper-tiny.en"
ASR_MODEL_REVISION = "87c7102498dcde7456f24cfd30239ca606ed9063"
ASR_LOCAL_REL = RESTRICTED_ROOT_REL / "models/whisper-tiny.en-87c7102"
MODEL_DOWNLOAD_MARKER_REL = RESTRICTED_ROOT_REL / "models/download_attempt.json"


class ReconError(RuntimeError):
    """Fail-closed reconnaissance error."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReconError(f"INVALID_JSON:{path.as_posix()}") from exc


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def atomic_write(path: Path, payload: bytes, *, restricted: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary)
    try:
        os.fchmod(descriptor, 0o600 if restricted else 0o644)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        path.chmod(0o600 if restricted else 0o644)
    finally:
        temporary_path.unlink(missing_ok=True)


def atomic_write_json(path: Path, value: Any, *, restricted: bool = True) -> None:
    atomic_write(path, canonical_json_bytes(value), restricted=restricted)


def atomic_write_jsonl(
    path: Path, values: Iterable[Mapping[str, Any]], *, restricted: bool = True
) -> None:
    payload = b"".join(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode() + b"\n"
        for value in values
    )
    atomic_write(path, payload, restricted=restricted)


def sha256_file(path: Path, *, chunk_size: int = 4 * 1024 * 1024) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while block := handle.read(chunk_size):
            size += len(block)
            digest.update(block)
    return size, digest.hexdigest()


def file_identity(path: Path, repo_root: Path) -> dict[str, Any]:
    size, digest = sha256_file(path)
    return {
        "path": path.relative_to(repo_root).as_posix(),
        "size_bytes": size,
        "sha256": digest,
    }


def round_float(value: float | None, digits: int = 8) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ReconError(f"MALFORMED_{label}")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ReconError(f"MALFORMED_{label}")
    return value


def validate_authoritative_inputs(
    repo_root: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    paths = {
        "plan": repo_root / PLAN_REL,
        "acquisition_manifest": repo_root / ACQUISITION_MANIFEST_REL,
        "media_audit": repo_root / MEDIA_AUDIT_REL,
        "authorization": repo_root / AUTHORIZATION_REL,
    }
    for label, path in paths.items():
        if not path.is_file() or path.is_symlink():
            raise ReconError(f"MISSING_OR_UNSAFE_{label.upper()}")

    identities = {label: file_identity(path, repo_root) for label, path in paths.items()}
    if identities["plan"]["sha256"] != EXPECTED_PLAN_SHA256:
        raise ReconError("FROZEN_PLAN_SHA256_MISMATCH")
    if (
        identities["acquisition_manifest"]["sha256"]
        != EXPECTED_ACQUISITION_MANIFEST_SHA256
    ):
        raise ReconError("ACQUISITION_MANIFEST_SHA256_MISMATCH")
    if identities["media_audit"]["sha256"] != EXPECTED_MEDIA_AUDIT_SHA256:
        raise ReconError("MEDIA_AUDIT_SHA256_MISMATCH")

    plan = _require_mapping(load_json(paths["plan"]), "PLAN")
    acquisition = _require_mapping(
        load_json(paths["acquisition_manifest"]), "ACQUISITION_MANIFEST"
    )
    audit = _require_mapping(load_json(paths["media_audit"]), "MEDIA_AUDIT")
    authorization = _require_mapping(load_json(paths["authorization"]), "AUTHORIZATION")

    plan_assets = _require_list(plan.get("assets"), "PLAN_ASSETS")
    acquisition_assets = _require_list(acquisition.get("assets"), "ACQUISITION_ASSETS")
    audit_media = _require_list(audit.get("media"), "AUDIT_MEDIA")
    authorized_ids = tuple(
        _require_mapping(authorization.get("authorized_scope"), "AUTHORIZED_SCOPE").get(
            "candidate_ids", []
        )
    )
    plan_ids = tuple(str(item.get("candidate_id")) for item in plan_assets)
    if plan_ids != EXPECTED_CANDIDATES or authorized_ids != EXPECTED_CANDIDATES:
        raise ReconError("EXACT_CANDIDATE_SET_MISMATCH")
    if acquisition.get("verified_total_payload_bytes") != EXPECTED_PAYLOAD_BYTES:
        raise ReconError("ACQUISITION_AGGREGATE_MISMATCH")
    if audit.get("decision") not in {"GO", "CONDITIONAL_GO"}:
        raise ReconError("MEDIA_AUDIT_NOT_PASSING")
    if not audit.get("restricted_tree_unchanged_during_media_inspection"):
        raise ReconError("MEDIA_AUDIT_TREE_SAFETY_FAILED")
    aggregate = _require_mapping(
        _require_mapping(audit.get("integrity_and_provenance"), "AUDIT_INTEGRITY").get(
            "aggregate"
        ),
        "AUDIT_AGGREGATE",
    )
    if (
        aggregate.get("actual_payload_bytes") != EXPECTED_PAYLOAD_BYTES
        or aggregate.get("payload_count") != 5
        or aggregate.get("exact_match") is not True
    ):
        raise ReconError("MEDIA_AUDIT_AGGREGATE_INCONSISTENT")

    acquisition_by_id = {
        str(item.get("candidate_id")): _require_mapping(item, "ACQUISITION_ASSET")
        for item in acquisition_assets
    }
    audit_by_id = {
        str(item.get("candidate_id")): _require_mapping(item, "AUDIT_MEDIA_ITEM")
        for item in audit_media
    }
    exact_assets = set(
        _require_mapping(authorization.get("authorized_scope"), "AUTHORIZED_SCOPE").get(
            "exact_assets", []
        )
    )
    assets: list[dict[str, Any]] = []
    for plan_asset_raw in plan_assets:
        plan_asset = _require_mapping(plan_asset_raw, "PLAN_ASSET")
        candidate_id = str(plan_asset.get("candidate_id"))
        acquisition_asset = acquisition_by_id.get(candidate_id)
        audited = audit_by_id.get(candidate_id)
        if acquisition_asset is None or audited is None:
            raise ReconError(f"AUTHORITATIVE_ASSET_MISSING:{candidate_id}")
        if not all(
            audited.get(key) is True
            for key in (
                "technical_audit_pass",
                "actual_decode_pass",
                "declared_audiovisual_pass",
                "timeline_plausibility_pass",
            )
        ):
            raise ReconError(f"MEDIA_AUDIT_ASSET_FAILED:{candidate_id}")
        path = repo_root / RESTRICTED_ROOT_REL / str(plan_asset.get("destination"))
        rel_path = path.relative_to(repo_root).as_posix()
        if rel_path not in exact_assets or path.is_symlink() or not path.is_file():
            raise ReconError(f"UNAUTHORIZED_OR_UNSAFE_ASSET:{candidate_id}")
        size, actual_sha256 = sha256_file(path)
        if (
            size != int(plan_asset.get("size_bytes", -1))
            or size != int(acquisition_asset.get("size_bytes", -2))
            or actual_sha256 != str(acquisition_asset.get("sha256"))
            or audited.get("path") != rel_path
        ):
            raise ReconError(f"ASSET_IDENTITY_MISMATCH:{candidate_id}")
        duration = float(
            _require_mapping(audited.get("container"), "AUDIT_CONTAINER").get(
                "duration_seconds"
            )
        )
        if not math.isfinite(duration) or duration <= WINDOW_SECONDS:
            raise ReconError(f"INVALID_ASSET_DURATION:{candidate_id}")
        assets.append(
            {
                "candidate_id": candidate_id,
                "basename": str(plan_asset.get("basename")),
                "title": str(plan_asset.get("title")),
                "selection_role": str(plan_asset.get("selection_role")),
                "path": rel_path,
                "absolute_path": str(path),
                "size_bytes": size,
                "sha256": actual_sha256,
                "duration_seconds": duration,
            }
        )

    prohibitions = _require_mapping(
        authorization.get("continuing_prohibitions"), "PROHIBITIONS"
    )
    if not prohibitions or not all(value is True for value in prohibitions.values()):
        raise ReconError("AUTHORIZATION_PROHIBITIONS_NOT_ACTIVE")
    if authorization.get("authorization_status") != (
        "ACTIVE_FOR_RESTRICTED_CONTENT_RECONNAISSANCE_ONLY"
    ):
        raise ReconError("CONTENT_RECON_AUTHORIZATION_INACTIVE")
    return assets, identities


def capability_audit(repo_root: Path) -> dict[str, Any]:
    packages: dict[str, dict[str, Any]] = {}
    distribution_names = {
        "av": ("av",),
        "numpy": ("numpy",),
        "scipy": ("scipy",),
        "torch": ("torch",),
        "torchaudio": ("torchaudio",),
        "transformers": ("transformers",),
        "cv2": ("opencv-python", "opencv-python-headless"),
    }
    for name in ("av", "numpy", "scipy", "torch", "torchaudio", "transformers", "cv2"):
        spec = importlib.util.find_spec(name)
        version = None
        status = "absent"
        if spec is not None:
            status = "available"
            for distribution_name in distribution_names[name]:
                try:
                    version = importlib.metadata.version(distribution_name)
                    break
                except importlib.metadata.PackageNotFoundError:
                    pass
        packages[name] = {"status": status, "version": version}

    model_dir = repo_root / ASR_LOCAL_REL
    model_files = (
        sorted(path for path in model_dir.rglob("*") if path.is_file())
        if model_dir.is_dir()
        else []
    )
    model_ready = bool(
        model_files
        and any(path.name in {"model.safetensors", "pytorch_model.bin"} for path in model_files)
        and (model_dir / "config.json").is_file()
    )
    marker_path = repo_root / MODEL_DOWNLOAD_MARKER_REL
    marker = load_json(marker_path) if marker_path.is_file() else None
    return {
        "packages": packages,
        "executables": {
            name: bool(shutil.which(name))
            for name in ("ffprobe", "ffmpeg", "tesseract", "sox")
        },
        "asr_model": {
            "model_id": ASR_MODEL_ID,
            "revision": ASR_MODEL_REVISION,
            "local_path": ASR_LOCAL_REL.as_posix(),
            "locally_ready": model_ready,
            "local_file_count": len(model_files),
            "network_download_attempted_before_run": bool(marker),
            "network_download_result": (
                marker.get("result")
                if isinstance(marker, Mapping)
                else "NOT_ATTEMPTED_BY_TOOL"
            ),
            "hf_tokens_read_or_disclosed": False,
            "executed": False,
        },
        "selected_reconnaissance_backend": "deterministic_signal_proxy",
        "backend_limit": (
            "This implementation does not execute ASR. Local-weight availability "
            "alone is not ASR evidence; speech status uses acoustic proxy features "
            "and requires human review."
        ),
    }


def regular_grid(duration_seconds: float, count: int = COARSE_WINDOWS_PER_ASSET) -> list[float]:
    """Frozen grid with explicit beginning and near-end coverage."""
    latest = max(0.0, duration_seconds - WINDOW_SECONDS)
    if count <= 1 or latest == 0:
        return [0.0]
    return [round(latest * index / (count - 1), 3) for index in range(count)]


def build_adaptive_starts(
    coarse: Sequence[Mapping[str, Any]],
    duration_seconds: float,
    *,
    max_windows: int = MAX_ADAPTIVE_WINDOWS_PER_ASSET,
) -> list[dict[str, Any]]:
    if len(coarse) < 2 or max_windows <= 0:
        return []
    latest = max(0.0, duration_seconds - WINDOW_SECONDS)
    proposals: list[tuple[float, float, str]] = []
    for left, right in zip(coarse, coarse[1:]):
        midpoint = (float(left["start_seconds"]) + float(right["start_seconds"])) / 2
        speech_delta = abs(
            float(left["inferences"]["speech_score"])
            - float(right["inferences"]["speech_score"])
        )
        motion_delta = abs(
            float(left["visual"]["mean_frame_difference"])
            - float(right["visual"]["mean_frame_difference"])
        )
        activity_delta = abs(
            float(left["audio"]["active_frame_ratio"])
            - float(right["audio"]["active_frame_ratio"])
        )
        transition_score = speech_delta + 2.0 * motion_delta + 0.5 * activity_delta
        proposals.append((transition_score, midpoint, "coarse_transition_midpoint"))
    for item in coarse:
        inferred = _require_mapping(item["inferences"], "INFERENCES")
        if (
            inferred["non_speech_audio_score"] >= NON_SPEECH_SCORE_THRESHOLD
            or item["visual"]["max_frame_difference"] >= SCENE_CUT_THRESHOLD
        ):
            for offset in (-WINDOW_SECONDS, WINDOW_SECONDS):
                proposals.append(
                    (
                        float(inferred["non_speech_audio_score"])
                        + float(item["visual"]["max_frame_difference"]),
                        float(item["start_seconds"]) + offset,
                        "neighbor_of_low_speech_audio_or_visual_change",
                    )
                )
    existing = {round(float(item["start_seconds"]), 3) for item in coarse}
    selected: list[dict[str, Any]] = []
    selected_starts: set[float] = set()
    for score, start, rationale in sorted(
        proposals, key=lambda value: (-value[0], value[1], value[2])
    ):
        bounded = round(min(max(0.0, start), latest), 3)
        if bounded in existing or bounded in selected_starts:
            continue
        if any(abs(bounded - other) < WINDOW_SECONDS / 2 for other in selected_starts):
            continue
        selected.append(
            {
                "start_seconds": bounded,
                "retrieval_rationale": rationale,
                "priority_score": round_float(score, 6),
            }
        )
        selected_starts.add(bounded)
        if len(selected) >= max_windows:
            break
    return sorted(selected, key=lambda item: item["start_seconds"])


def infer_window(audio: Mapping[str, Any], visual: Mapping[str, Any]) -> dict[str, Any]:
    rms = float(audio["rms_full_scale"])
    peak = float(audio["peak_absolute_full_scale"])
    active_ratio = float(audio["active_frame_ratio"])
    silence_ratio = float(audio["silence_ratio"])
    zcr = float(audio["zero_crossing_rate"])
    flatness = float(audio["spectral_flatness"])
    voiced_ratio = float(audio["voiced_proxy_ratio"])
    harmonicity = float(audio["harmonicity_proxy"])

    speech_score = (
        0.30 * voiced_ratio
        + 0.25 * harmonicity
        + 0.15 * max(0.0, 1.0 - abs(zcr - 0.09) / 0.12)
        + 0.15 * max(0.0, 1.0 - flatness / 0.55)
        + 0.15 * active_ratio
    )
    non_speech_score = (
        0.30 * active_ratio
        + 0.25 * min(1.0, flatness / 0.50)
        + 0.15 * min(1.0, zcr / 0.20)
        + 0.15 * (1.0 - harmonicity)
        + 0.15 * (1.0 - voiced_ratio)
    )
    visual_score = min(
        1.0,
        float(visual["mean_frame_difference"]) / VISUAL_STRONG_THRESHOLD * 0.65
        + min(1.0, float(visual["max_frame_difference"]) / SCENE_CUT_THRESHOLD) * 0.35,
    )
    acoustically_active = rms >= ACTIVE_RMS or peak >= ACTIVE_PEAK or active_ratio >= 0.35
    speech_status = (
        "strong_speech_proxy"
        if acoustically_active and speech_score >= SPEECH_SCORE_STRONG
        else "speech_proxy_candidate"
        if acoustically_active and speech_score >= SPEECH_SCORE_THRESHOLD
        else "below_speech_proxy_threshold"
    )
    non_speech_status = (
        "non_speech_priority_candidate"
        if acoustically_active
        and non_speech_score >= NON_SPEECH_SCORE_THRESHOLD
        and speech_score < SPEECH_SCORE_STRONG
        else "possible_mixture"
        if acoustically_active and non_speech_score >= 0.48
        else "not_indicated"
    )
    visual_status = (
        "strong_change"
        if visual_score >= 0.70
        else "meaningful_change"
        if visual_score >= 0.42
        else "mostly_static_or_low_change"
    )
    return {
        "acoustically_active": acoustically_active,
        "speech_score": round_float(speech_score),
        "speech_status": speech_status,
        "speech_basis": "deterministic_signal_proxy_no_asr_model",
        "non_speech_audio_score": round_float(non_speech_score),
        "non_speech_audio_status": non_speech_status,
        "visual_change_score": round_float(visual_score),
        "visual_content_status": visual_status,
        "silence_dominant": silence_ratio >= 0.80,
    }


def modality_families(item: Mapping[str, Any]) -> list[str]:
    inferred = _require_mapping(item["inferences"], "INFERENCES")
    speech = inferred["speech_status"] in {
        "strong_speech_proxy",
        "speech_proxy_candidate",
    }
    non_speech = (
        inferred["non_speech_audio_status"] == "non_speech_priority_candidate"
    )
    visual = inferred["visual_content_status"] in {"strong_change", "meaningful_change"}
    families: list[str] = []
    if visual:
        families.append("V")
    if speech:
        families.append("S")
    if non_speech:
        families.append("A")
    if visual and speech:
        families.append("V+S")
    if visual and non_speech:
        families.append("V+A")
    if visual and speech and non_speech:
        families.append("V+S+A")
    return families or ["NONE_STRONG_AT_RECON_THRESHOLDS"]


def candidate_priority(item: Mapping[str, Any]) -> float:
    inferred = item["inferences"]
    family_bonus = 0.08 * len(
        [family for family in modality_families(item) if "+" in family]
    )
    adaptive_bonus = 0.08 if item["sampling_stage"] == "adaptive" else 0.0
    return (
        0.38 * float(inferred["speech_score"])
        + 0.32 * float(inferred["non_speech_audio_score"])
        + 0.30 * float(inferred["visual_change_score"])
        + family_bonus
        + adaptive_bonus
    )


def select_candidates(
    measurements: Sequence[Mapping[str, Any]],
    *,
    target_count: int = TARGET_CANDIDATE_COUNT,
    max_per_asset: int = MAX_CANDIDATES_PER_ASSET,
) -> list[dict[str, Any]]:
    by_asset: dict[str, list[Mapping[str, Any]]] = {}
    for item in measurements:
        by_asset.setdefault(str(item["candidate_id"]), []).append(item)
    selected: list[Mapping[str, Any]] = []
    selected_ids: set[str] = set()
    for candidate_id in EXPECTED_CANDIDATES:
        pool = by_asset.get(candidate_id, [])
        ranked = sorted(pool, key=lambda item: (-candidate_priority(item), item["start_seconds"]))
        chosen: list[Mapping[str, Any]] = []
        # First cover routing signals where available. These are not semantic
        # labels and do not assert that a modality is necessary.
        predicates = (
            lambda x: x["inferences"]["speech_status"]
            in {"strong_speech_proxy", "speech_proxy_candidate"},
            lambda x: x["inferences"]["non_speech_audio_status"]
            == "non_speech_priority_candidate",
            lambda x: x["inferences"]["visual_content_status"]
            in {"strong_change", "meaningful_change"},
        )
        for predicate in predicates:
            for item in ranked:
                if (
                    predicate(item)
                    and item["measurement_id"] not in selected_ids
                    and all(
                        abs(float(item["start_seconds"]) - float(prior["start_seconds"]))
                        >= WINDOW_SECONDS
                        for prior in chosen
                    )
                ):
                    chosen.append(item)
                    selected_ids.add(str(item["measurement_id"]))
                    break
        for item in ranked:
            if len(chosen) >= max_per_asset:
                break
            if item["measurement_id"] in selected_ids:
                continue
            if any(
                abs(float(item["start_seconds"]) - float(prior["start_seconds"]))
                < WINDOW_SECONDS
                for prior in chosen
            ):
                continue
            chosen.append(item)
            selected_ids.add(str(item["measurement_id"]))
        selected.extend(chosen)

    if len(selected) > target_count:
        selected = sorted(
            selected, key=lambda item: (-candidate_priority(item), item["measurement_id"])
        )[:target_count]
    selected = sorted(selected, key=lambda item: (item["candidate_id"], item["start_seconds"]))
    output: list[dict[str, Any]] = []
    for index, item in enumerate(selected, 1):
        inferred = item["inferences"]
        score = candidate_priority(item)
        confidence = (
            "moderate"
            if max(
                inferred["speech_score"],
                inferred["non_speech_audio_score"],
                inferred["visual_change_score"],
            )
            >= 0.70
            else "low_to_moderate"
        )
        output.append(
            {
                "candidate_window_id": f"noaa01-window-{index:03d}",
                "video_id": item["candidate_id"],
                "basename": item["basename"],
                "start_seconds": item["start_seconds"],
                "end_seconds": item["end_seconds"],
                "sampling_stage": item["sampling_stage"],
                "sampling_retrieval_rationale": item["sampling_retrieval_rationale"],
                "measured_audio_statistics": item["audio"],
                "measured_visual_change_statistics": item["visual"],
                "provisional_speech_status": inferred["speech_status"],
                "provisional_speech_score": inferred["speech_score"],
                "provisional_non_speech_audio_status": inferred[
                    "non_speech_audio_status"
                ],
                "provisional_non_speech_audio_score": inferred[
                    "non_speech_audio_score"
                ],
                "provisional_visual_content_status": inferred["visual_content_status"],
                "provisional_visual_change_score": inferred["visual_change_score"],
                "candidate_modality_families": modality_families(item),
                "candidate_modality_family_semantics": (
                    "review-routing hypotheses only; not modality-presence, "
                    "evidence-relevance, or modality-necessity labels"
                ),
                "candidate_priority_score": round_float(score),
                "confidence": confidence,
                "uncertainty": (
                    "No ASR or audio-event model was locally available. Speech and "
                    "non-speech routing use overlapping acoustic proxies; neither "
                    "establishes intelligibility or sound identity. Visual change does "
                    "not establish semantic relevance or modality necessity."
                ),
                "human_review_required": True,
                "not_gold_label_reason": (
                    "Machine-generated bounded reconnaissance only; not a gold label "
                    "because there is no human content validation, evidence "
                    "adjudication, or minimal-modality test."
                ),
            }
        )
    return output


PYAV_RECON_CHILD = r"""
import json, math, sys
import av
import cv2
import numpy as np

path = sys.argv[1]
start = float(sys.argv[2])
duration = float(sys.argv[3])
target_rate = int(sys.argv[4])
max_video_frames = int(sys.argv[5])
silence_frame_rms = float(sys.argv[6])
audio_frame_seconds = float(sys.argv[7])
scene_cut_threshold = float(sys.argv[8])
result = {"errors": [], "persistent_outputs_created": False}

def sec(value, time_base):
    if value is None or time_base is None:
        return None
    return float(value * time_base)

def mono_float(frame):
    array = frame.to_ndarray()
    if np.issubdtype(array.dtype, np.integer):
        scale = float(max(abs(np.iinfo(array.dtype).min), np.iinfo(array.dtype).max))
        array = array.astype(np.float32) / scale
    else:
        array = array.astype(np.float32, copy=False)
    if array.ndim == 2:
        if getattr(frame.format, "is_planar", False):
            array = np.mean(array, axis=0)
        else:
            channels = max(1, len(frame.layout.channels))
            array = array.reshape(-1, channels).mean(axis=1)
    return np.ravel(array)

def spectral_features(samples, rate, silence_rms):
    if len(samples) < 256:
        return 0.0, 0.0, 0.0, 0.0
    n_fft = 512
    hop = 256
    centroids, flatnesses, voiced, harmonicity = [], [], [], []
    window = np.hanning(n_fft).astype(np.float32)
    for offset in range(0, len(samples) - n_fft + 1, hop):
        chunk = samples[offset:offset+n_fft].astype(np.float64)
        if float(np.sqrt(np.mean(chunk**2))) < silence_rms:
            continue
        chunk = chunk - np.mean(chunk)
        spectrum = np.abs(np.fft.rfft(chunk * window)).astype(np.float64) + 1e-12
        freqs = np.fft.rfftfreq(n_fft, 1.0/rate)
        centroids.append(float(np.sum(freqs*spectrum)/np.sum(spectrum)))
        flatnesses.append(float(np.exp(np.mean(np.log(spectrum)))/np.mean(spectrum)))
        ac = np.correlate(chunk, chunk, mode="full")[n_fft-1:]
        lo, hi = max(1, int(rate/400)), min(len(ac), int(rate/70))
        if hi > lo and ac[0] > 1e-12:
            segment = ac[lo:hi]
            ratio = float(np.max(segment) / ac[0])
            harmonicity.append(max(0.0, min(1.0, ratio)))
            voiced.append(1.0 if ratio >= 0.28 else 0.0)
        else:
            harmonicity.append(0.0)
            voiced.append(0.0)
    return (
        float(np.mean(centroids)) if centroids else 0.0,
        float(np.mean(flatnesses)) if flatnesses else 0.0,
        float(np.mean(voiced)) if voiced else 0.0,
        float(np.mean(harmonicity)) if harmonicity else 0.0,
    )

try:
    with av.open(path, metadata_errors="ignore") as container:
        streams = list(container.streams.audio)
        if not streams:
            raise RuntimeError("NO_AUDIO_STREAM")
        stream = streams[0]
        container.seek(max(0, int(start * av.time_base)), backward=True, any_frame=False)
        resampler = av.AudioResampler(format="fltp", layout="mono", rate=target_rate)
        segments = []
        decoded_frames = 0
        decoded_start = None
        decoded_end = None
        for packet in container.demux(stream):
            for frame in packet.decode():
                frame_start = sec(frame.pts, frame.time_base)
                frame_end = None if frame_start is None else frame_start + frame.samples/frame.sample_rate
                if frame_end is not None and frame_end <= start:
                    continue
                for converted in resampler.resample(frame):
                    values = mono_float(converted)
                    if values.size:
                        converted_start = sec(converted.pts, converted.time_base)
                        if converted_start is None:
                            raise RuntimeError("AUDIO_TIMESTAMP_MISSING")
                        segments.append((converted_start, values))
                decoded_frames += 1
                if decoded_start is None:
                    decoded_start = frame_start
                decoded_end = frame_end
                if frame_end is None or frame_end >= start + duration:
                    break
            if decoded_frames and (decoded_end is None or decoded_end >= start + duration):
                break
        for converted in resampler.resample(None):
            values = mono_float(converted)
            if values.size:
                converted_start = sec(converted.pts, converted.time_base)
                if converted_start is None:
                    raise RuntimeError("AUDIO_TIMESTAMP_MISSING")
                segments.append((converted_start, values))
        wanted = int(round(duration * target_rate))
        samples = np.zeros(wanted, dtype=np.float32)
        coverage = np.zeros(wanted, dtype=np.bool_)
        decoded_sample_count = 0
        for segment_start, values in segments:
            destination_start = int(round((segment_start - start) * target_rate))
            source_start = max(0, -destination_start)
            destination_start = max(0, destination_start)
            count = min(values.size - source_start, wanted - destination_start)
            if count <= 0:
                continue
            samples[destination_start:destination_start+count] = values[source_start:source_start+count]
            coverage[destination_start:destination_start+count] = True
            decoded_sample_count += count
        if not np.any(coverage) or not np.isfinite(samples).all():
            raise RuntimeError("NO_FINITE_AUDIO_SAMPLES")
        peak = float(np.max(np.abs(samples)))
        rms = float(np.sqrt(np.mean(samples.astype(np.float64)**2)))
        zcr = float(np.mean(samples[:-1] * samples[1:] < 0)) if len(samples) > 1 else 0.0
        frame_len = max(1, int(round(target_rate * audio_frame_seconds)))
        usable = len(samples) // frame_len * frame_len
        framed = samples[:usable].reshape(-1, frame_len) if usable else samples.reshape(1, -1)
        frame_rms = np.sqrt(np.mean(framed.astype(np.float64)**2, axis=1))
        silence_ratio = float(np.mean(frame_rms < silence_frame_rms))
        active_ratio = 1.0 - silence_ratio
        centroid, flatness, voiced_ratio, harmonicity = spectral_features(
            samples, target_rate, silence_frame_rms
        )
        result["audio"] = {
            "decoded": True,
            "decoded_frame_count": decoded_frames,
            "sample_rate_hz": target_rate,
            "sample_count": int(samples.size),
            "decoded_sample_count": int(decoded_sample_count),
            "timeline_covered_sample_count": int(np.sum(coverage)),
            "timeline_coverage_ratio": float(np.mean(coverage)),
            "decoded_start_seconds": decoded_start,
            "decoded_end_seconds": decoded_end,
            "peak_absolute_full_scale": peak,
            "rms_full_scale": rms,
            "silence_ratio": silence_ratio,
            "active_frame_ratio": active_ratio,
            "zero_crossing_rate": zcr,
            "spectral_centroid_hz": centroid,
            "spectral_flatness": flatness,
            "voiced_proxy_ratio": voiced_ratio,
            "harmonicity_proxy": harmonicity,
        }

    with av.open(path, metadata_errors="ignore") as container:
        streams = list(container.streams.video)
        if not streams:
            raise RuntimeError("NO_VIDEO_STREAM")
        stream = streams[0]
        container.seek(max(0, int(start * av.time_base)), backward=True, any_frame=False)
        targets = np.linspace(start, start + duration, max_video_frames)
        selected = []
        target_index = 0
        examined = 0
        for packet in container.demux(stream):
            for frame in packet.decode():
                examined += 1
                timestamp = sec(frame.pts, frame.time_base)
                if timestamp is None or timestamp < targets[target_index] - 0.05:
                    if examined >= 10000:
                        break
                    continue
                gray = frame.to_ndarray(format="gray")
                h, w = gray.shape
                scale = min(1.0, 192.0/max(h, w))
                if scale < 1.0:
                    gray = cv2.resize(gray, (max(1,int(w*scale)), max(1,int(h*scale))), interpolation=cv2.INTER_AREA)
                selected.append((timestamp, gray))
                target_index += 1
                if target_index >= len(targets):
                    break
            if target_index >= len(targets) or examined >= 10000:
                break
        if len(selected) < 2:
            raise RuntimeError("INSUFFICIENT_VIDEO_FRAMES")
        diffs, edges, entropies, brightness = [], [], [], []
        for _, gray in selected:
            histogram = np.bincount(gray.ravel(), minlength=256).astype(np.float64)
            probability = histogram[histogram > 0] / gray.size
            entropies.append(float(-np.sum(probability*np.log2(probability))))
            edges.append(float(np.mean(cv2.Canny(gray, 100, 200) > 0)))
            brightness.append(float(np.mean(gray)/255.0))
        for (_, left), (_, right) in zip(selected, selected[1:]):
            diffs.append(float(np.mean(np.abs(right.astype(np.float32)-left.astype(np.float32)))/255.0))
        result["visual"] = {
            "decoded": True,
            "sampled_frame_count": len(selected),
            "frames_examined": examined,
            "frame_timestamps_seconds": [float(item[0]) for item in selected],
            "mean_frame_difference": float(np.mean(diffs)),
            "max_frame_difference": float(np.max(diffs)),
            "scene_cut_count": int(np.sum(np.asarray(diffs) >= scene_cut_threshold)),
            "mean_entropy_bits": float(np.mean(entropies)),
            "mean_edge_density": float(np.mean(edges)),
            "mean_brightness_normalized": float(np.mean(brightness)),
        }
except Exception as exc:
    result["errors"].append(type(exc).__name__ + ":" + str(exc)[:120])
print(json.dumps(result, sort_keys=True, allow_nan=False))
"""


def run_measurement_child(
    path: Path,
    start_seconds: float,
    *,
    timeout_seconds: int = CHILD_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    command = [
        sys.executable,
        "-c",
        PYAV_RECON_CHILD,
        str(path),
        str(start_seconds),
        str(WINDOW_SECONDS),
        str(AUDIO_TARGET_RATE),
        str(MAX_VIDEO_FRAMES),
        str(SILENCE_FRAME_RMS),
        str(AUDIO_FRAME_SECONDS),
        str(SCENE_CUT_THRESHOLD),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            cwd=path.parent,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
    except subprocess.TimeoutExpired as exc:
        raise ReconError(f"MEASUREMENT_TIMEOUT:{path.name}:{start_seconds}") from exc
    if completed.returncode != 0:
        raise ReconError(
            f"MEASUREMENT_CHILD_EXIT_{completed.returncode}:{path.name}:{start_seconds}"
        )
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ReconError(f"MEASUREMENT_INVALID_JSON:{path.name}:{start_seconds}") from exc
    if result.get("errors") or not result.get("audio", {}).get("decoded") or not result.get(
        "visual", {}
    ).get("decoded"):
        raise ReconError(f"MEASUREMENT_DECODE_FAILED:{path.name}:{start_seconds}")
    return result


def normalize_measurement(
    asset: Mapping[str, Any],
    child: Mapping[str, Any],
    *,
    start_seconds: float,
    stage: str,
    rationale: str,
    sequence: int,
) -> dict[str, Any]:
    audio = {
        key: round_float(value)
        if isinstance(value, float)
        else value
        for key, value in child["audio"].items()
    }
    visual = {
        key: [round_float(value, 6) for value in value]
        if key == "frame_timestamps_seconds"
        else round_float(value)
        if isinstance(value, float)
        else value
        for key, value in child["visual"].items()
    }
    inferred = infer_window(audio, visual)
    return {
        "schema_version": SCHEMA_VERSION,
        "measurement_id": f"{asset['candidate_id']}-{stage}-{sequence:03d}",
        "candidate_id": asset["candidate_id"],
        "basename": asset["basename"],
        "start_seconds": round_float(start_seconds, 3),
        "end_seconds": round_float(
            min(float(asset["duration_seconds"]), start_seconds + WINDOW_SECONDS), 3
        ),
        "window_seconds": WINDOW_SECONDS,
        "sampling_stage": stage,
        "sampling_retrieval_rationale": rationale,
        "audio": audio,
        "visual": visual,
        "speech_model": {
            "backend": "deterministic_signal_proxy",
            "asr_token_presence": None,
            "asr_confidence": None,
            "provisional_asr_snippet": None,
            "limitation": "No local model weights; bounded download unavailable.",
        },
        "ocr": {
            "available": False,
            "text_count_signal": None,
            "reason": "No local tesseract executable or pytesseract package.",
        },
        "inferences": inferred,
        "candidate_modality_families": modality_families({"inferences": inferred}),
        "persistent_media_derivatives_created": False,
    }


def assess_feasibility(
    measurements: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    *,
    asr_model_available: bool = False,
) -> dict[str, Any]:
    by_asset: dict[str, list[Mapping[str, Any]]] = {
        candidate_id: [] for candidate_id in EXPECTED_CANDIDATES
    }
    for item in measurements:
        by_asset[str(item["candidate_id"])].append(item)

    def asset_has(candidate_id: str, predicate: Any) -> bool:
        return any(predicate(item) for item in by_asset[candidate_id])

    speech_assets = [
        candidate_id
        for candidate_id in EXPECTED_CANDIDATES
        if asset_has(
            candidate_id,
            lambda item: item["inferences"]["speech_status"]
            in {"strong_speech_proxy", "speech_proxy_candidate"},
        )
    ]
    non_speech_assets = [
        candidate_id
        for candidate_id in EXPECTED_CANDIDATES
        if asset_has(
            candidate_id,
            lambda item: item["inferences"]["non_speech_audio_status"]
            == "non_speech_priority_candidate",
        )
    ]
    visual_assets = [
        candidate_id
        for candidate_id in EXPECTED_CANDIDATES
        if asset_has(
            candidate_id,
            lambda item: item["inferences"]["visual_content_status"]
            in {"strong_change", "meaningful_change"},
        )
    ]
    family_counts = Counter(
        family for item in candidates for family in item["candidate_modality_families"]
    )
    separated_assets = []
    for candidate_id, items in by_asset.items():
        interesting = sorted(
            float(item["start_seconds"])
            for item in items
            if item["candidate_modality_families"]
            != ["NONE_STRONG_AT_RECON_THRESHOLDS"]
        )
        if interesting and max(interesting) - min(interesting) >= 120:
            separated_assets.append(candidate_id)

    per_asset_scores = []
    for candidate_id, items in by_asset.items():
        speech = max(float(item["inferences"]["speech_score"]) for item in items)
        non_speech = max(
            float(item["inferences"]["non_speech_audio_score"]) for item in items
        )
        visual = max(float(item["inferences"]["visual_change_score"]) for item in items)
        diversity = (
            len(
                {
                    family
                    for item in items
                    for family in item["candidate_modality_families"]
                    if family != "NONE_STRONG_AT_RECON_THRESHOLDS"
                }
            )
            / 6.0
        )
        per_asset_scores.append(
            {
                "candidate_id": candidate_id,
                "pilot_score": round_float(
                    0.35 * speech + 0.30 * non_speech + 0.25 * visual + 0.10 * diversity
                ),
            }
        )
    pilot = [
        item["candidate_id"]
        for item in sorted(
            per_asset_scores, key=lambda item: (-item["pilot_score"], item["candidate_id"])
        )[:3]
    ]
    all_have_speech = len(speech_assets) == len(EXPECTED_CANDIDATES)
    strong_combo = family_counts["V+S"] > 0 and (
        family_counts["V+A"] > 0 or family_counts["V+S+A"] > 0
    )
    if all_have_speech and len(visual_assets) >= 4 and strong_combo and asr_model_available:
        decision = "GO_REAL_AV_MVP_CONSTRUCTION"
    elif len(speech_assets) >= 4 and len(visual_assets) >= 3:
        decision = "CONDITIONAL_GO"
    else:
        decision = "NO_GO"
    ambient = (
        "headline_dimension_candidate"
        if asr_model_available
        and len(non_speech_assets) >= 4
        and family_counts["A"] + family_counts["V+A"] >= 8
        else "smaller_diagnostic_slice"
    )
    return {
        "decision": decision,
        "all_five_assets_contain_speech_like_candidates": all_have_speech,
        "all_five_assets_contain_intelligible_speech_candidates": (
            True if all_have_speech and asr_model_available else "NOT_MACHINE_VERIFIED"
        ),
        "speech_intelligibility_verification": (
            "SMALL_ASR_MODEL_SIGNAL_AVAILABLE"
            if asr_model_available
            else "REQUIRES_HUMAN_REVIEW_NO_ASR_MODEL"
        ),
        "speech_candidate_asset_count": len(speech_assets),
        "speech_candidate_assets": speech_assets,
        "non_speech_priority_candidate_asset_count": len(non_speech_assets),
        "non_speech_priority_candidate_assets": non_speech_assets,
        "meaningful_visual_change_asset_count": len(visual_assets),
        "meaningful_visual_change_assets": visual_assets,
        "selected_review_routing_hypotheses": {
            "V+S": family_counts["V+S"],
            "V+A": family_counts["V+A"],
            "V+S+A": family_counts["V+S+A"],
        },
        "temporally_separated_routing_signal_asset_count": len(separated_assets),
        "temporally_separated_routing_signal_assets": separated_assets,
        "ambient_non_speech_audio_recommendation": ambient,
        "first_manual_pilot_assets": pilot,
        "pilot_ranking": sorted(
            per_asset_scores, key=lambda item: (-item["pilot_score"], item["candidate_id"])
        ),
        "interpretive_limit": (
            "No intelligibility or non-speech identity is machine verified because "
            "no ASR or audio-event model was available. All labels are provisional "
            "review-routing hypotheses and require human review."
        ),
    }


def policy_record() -> dict[str, Any]:
    return {
        "policy_id": "NOAA01-RECON-POLICY-V1",
        "window_seconds": WINDOW_SECONDS,
        "coarse_windows_per_asset": COARSE_WINDOWS_PER_ASSET,
        "coarse_grid": (
            "18 inclusive regular start positions from 0 to duration-window"
        ),
        "adaptive_max_windows_per_asset": MAX_ADAPTIVE_WINDOWS_PER_ASSET,
        "adaptive_strategy": (
            "rank adjacent coarse transition midpoints plus neighbors of "
            "non-speech-priority or scene-cut windows"
        ),
        "audio_target_rate_hz": AUDIO_TARGET_RATE,
        "audio_frame_seconds": AUDIO_FRAME_SECONDS,
        "audio_amplitude_units": (
            "floating full-scale after PyAV decode/resampling; values are not "
            "per-window normalized and rare peaks may exceed 1.0"
        ),
        "audio_window_alignment": (
            "timestamp-aligned to the requested interval; uncovered timeline "
            "samples are zero-filled and coverage is recorded"
        ),
        "spectral_method": (
            "512-sample Hann-window magnitude spectrum at 16 kHz with 256-sample "
            "hop; spectral centroid and flatness average only frames above the "
            "silence RMS threshold; voiced/harmonicity are normalized "
            "autocorrelation proxies over 70-400 Hz lags"
        ),
        "video_frames_per_window_max": MAX_VIDEO_FRAMES,
        "video_frame_selection": (
            "nine inclusive target timestamps from start through start+8 seconds; "
            "select the first decoded frame no earlier than target-0.05 seconds"
        ),
        "visual_difference_units": (
            "mean absolute grayscale pixel difference divided by 255 after "
            "aspect-preserving downscale to maximum dimension 192 pixels"
        ),
        "thresholds": {
            "silence_frame_rms": SILENCE_FRAME_RMS,
            "active_rms": ACTIVE_RMS,
            "active_peak": ACTIVE_PEAK,
            "speech_score_candidate": SPEECH_SCORE_THRESHOLD,
            "speech_score_strong": SPEECH_SCORE_STRONG,
            "non_speech_score_candidate": NON_SPEECH_SCORE_THRESHOLD,
            "visual_change_mean": VISUAL_CHANGE_THRESHOLD,
            "visual_change_strong_mean": VISUAL_STRONG_THRESHOLD,
            "scene_cut_frame_difference": SCENE_CUT_THRESHOLD,
        },
        "candidate_target": TARGET_CANDIDATE_COUNT,
        "candidate_max_per_asset": MAX_CANDIDATES_PER_ASSET,
        "determinism": {
            "random_sampling": False,
            "fixed_asset_order": list(EXPECTED_CANDIDATES),
            "adaptive_tie_break": "descending priority then start_seconds then rationale",
            "candidate_tie_break": "descending priority then start_seconds within asset",
            "output_order": "candidate_id then start_seconds",
            "model_sampling": False,
        },
        "label_semantics": {
            "speech_score": (
                "handcrafted acoustic review-routing proxy; not speech detection "
                "or intelligibility evidence"
            ),
            "non_speech_audio_score": (
                "handcrafted non-speech-priority review-routing proxy; not "
                "audio-event recognition or sound identity"
            ),
            "candidate_modality_families": (
                "routing hypotheses only; not modality presence, evidence relevance, "
                "or necessity"
            ),
            "selected_shortlist_counts": (
                "selection-policy enriched and not prevalence estimates"
            ),
        },
    }


def public_review(
    feasibility: Mapping[str, Any],
    measurements: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    capabilities: Mapping[str, Any],
) -> str:
    stage_counts = Counter(item["sampling_stage"] for item in measurements)
    family_counts = Counter(
        family for item in candidates for family in item["candidate_modality_families"]
    )
    pilot = ", ".join(f"`{item}`" for item in feasibility["first_manual_pilot_assets"])
    return f"""# NOAA-01 restricted audiovisual content reconnaissance

**Reconnaissance date:** 2026-09-09  
**Decision:** **{feasibility["decision"]}**

## Executive finding

The exact five authorized NOAA-01 assets passed the fail-closed input gate and
were sampled with a frozen deterministic policy. The run produced
**{len(measurements)}** bounded in-memory measurements
({stage_counts["coarse"]} coarse and {stage_counts["adaptive"]} adaptive) and
selected **{len(candidates)}** restricted candidate windows. No extracted frame,
audio, clip, contact sheet, waveform, or transcript was persisted.

The reconnaissance found provisional speech-proxy routing candidates in
**{feasibility["speech_candidate_asset_count"]}/5** assets, non-speech-priority
routing candidates in
**{feasibility["non_speech_priority_candidate_asset_count"]}/5**, and meaningful
visual-change routing candidates in
**{feasibility["meaningful_visual_change_asset_count"]}/5**. Candidate-table
counts include **{family_counts["V+S"]}** `V+S`,
**{family_counts["V+A"]}** `V+A`, and
**{family_counts["V+S+A"]}** `V+S+A` routing hypotheses. These selected-shortlist
counts are intentionally enriched by the selection policy and are not corpus
prevalence estimates.

## Capability and important limitation

PyAV, NumPy, SciPy, Torch, torchaudio, transformers, and OpenCV were locally
available. External `ffprobe`, `ffmpeg`, OCR tooling, and local speech-model
weights were absent. A bounded attempt to obtain the pinned
`openai/whisper-tiny.en` revision could not resolve the approved proxy, and no
model artifact was retained. The completed scan used deterministic acoustic
proxies; this implementation did not execute ASR and generated no transcript or
textual ASR snippet.

Consequently, the handcrafted score supports only review routing. It does not
establish speech presence or intelligibility. The overlapping non-speech score
does not identify an audio event. Human listening is required before annotation
or benchmark construction.

## Frozen sampling and measurements

- Window length: **{WINDOW_SECONDS:.0f} seconds**
- Coarse grid: **{COARSE_WINDOWS_PER_ASSET} windows per asset**, inclusive of
  beginning and near-end coverage
- Adaptive expansion: at most **{MAX_ADAPTIVE_WINDOWS_PER_ASSET} windows per
  asset** around the highest coarse transitions and neighboring active-audio or
  visual-change signals
- Audio: mono 16 kHz in memory, aligned to the requested window with coverage
  recorded; floating full-scale RMS/peak (not per-window normalized), 20 ms
  silence ratio, zero-crossing rate, spectral centroid/flatness, and
  autocorrelation-based voiced/harmonicity proxies computed on active frames
- Video: at most **{MAX_VIDEO_FRAMES}** in-memory grayscale frames per window;
  consecutive-frame difference, scene-cut count, entropy, edge density, and
  brightness
- OCR: unavailable and not used
- Randomness: none

Observed measurements are stored separately from inferred candidate statuses.
Thresholds and the full policy are recorded in the restricted manifest.

## Feasibility answers

- All five assets contain intelligible speech:
  **not machine-verified**. Speech-proxy candidates occur in
  **{feasibility["speech_candidate_asset_count"]}/5**, but intelligibility
  requires human listening because no ASR model was available.
- Assets with non-speech-priority routing candidates:
  **{feasibility["non_speech_priority_candidate_asset_count"]}/5**
- Assets with meaningful visual-change routing candidates:
  **{feasibility["meaningful_visual_change_asset_count"]}/5**
- Selected `V+S` routing hypotheses: **{family_counts["V+S"]}**
- Selected `V+A` routing hypotheses: **{family_counts["V+A"]}**
- Selected `V+S+A` routing hypotheses: **{family_counts["V+S+A"]}**
- Assets with routing signals separated by at least two minutes:
  **{feasibility["temporally_separated_routing_signal_asset_count"]}/5**
- Ambient/non-speech recommendation:
  **{feasibility["ambient_non_speech_audio_recommendation"]}**
- First manual pilot: {pilot}

## Decision and boundary

**{feasibility["decision"]}**

This is a candidate-reconnaissance layer only. It does not make a gold evidence
label, final benchmark annotation, transcript publication, or minimal modality
necessity claim. `V`, `S`, `A`, and their combinations are review-routing
hypotheses only: they mean that fixed proxy signals crossed provisional
thresholds, not that those modalities are present, relevant, jointly required,
or minimally necessary. Human review must verify content, speech
intelligibility, non-speech sound identity, evidence relevance, temporal
boundaries, and whether any modality is actually necessary.

Detailed timestamps, hashes, and window-level metadata remain under
`data/restricted/noaa01/recon/`.
"""


def result_note(
    feasibility: Mapping[str, Any],
    measurements: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
) -> str:
    stages = Counter(item["sampling_stage"] for item in measurements)
    families = Counter(
        family for item in candidates for family in item["candidate_modality_families"]
    )
    return f"""## Task 80 complete

**Decision: `{feasibility["decision"]}`**

### Exact results

- Assets scanned: **5/5**
- Measurement windows: **{len(measurements)}**
  - coarse: **{stages["coarse"]}**
  - adaptive: **{stages["adaptive"]}**
- Restricted candidate shortlist: **{len(candidates)}**
- Provisional speech-candidate assets:
  **{feasibility["speech_candidate_asset_count"]}/5**
- Intelligible speech in all five:
  **not machine-verified; human review required**
- Non-speech-priority routing candidate assets:
  **{feasibility["non_speech_priority_candidate_asset_count"]}/5**
- Meaningful visual-change routing candidate assets:
  **{feasibility["meaningful_visual_change_asset_count"]}/5**
- Selected routing hypotheses (selection-biased, not prevalence):
  `V+S` **{families["V+S"]}**, `V+A` **{families["V+A"]}**,
  `V+S+A` **{families["V+S+A"]}**
- First manual pilot: {", ".join(feasibility["first_manual_pilot_assets"])}

### Important limitation

No local ASR model weights were present. The bounded pinned small-model download
attempt failed at approved-proxy DNS resolution, so the run used deterministic
acoustic proxies and generated no transcript snippets. These proxies support
review routing only; speech presence/intelligibility, non-speech identity, and
all modality/evidence judgments require human validation.

### Safety

No source media was modified. No frame, audio, clip, contact sheet, waveform, or
transcript was persisted. Detailed timestamps, hashes, and measurements remain
restricted; the review summary is redaction-safe.

### Validation

This generated note does not hard-code test totals. See the contemporaneous
Task 81 red-team result for validation performed after the latest rerun.
"""


def run(repo_root: Path) -> dict[str, Any]:
    assets, input_identities = validate_authoritative_inputs(repo_root)
    capabilities = capability_audit(repo_root)
    if capabilities["packages"]["av"]["status"] != "available":
        raise ReconError("PYAV_REQUIRED")
    if capabilities["packages"]["numpy"]["status"] != "available":
        raise ReconError("NUMPY_REQUIRED")
    if capabilities["packages"]["cv2"]["status"] != "available":
        raise ReconError("OPENCV_REQUIRED")

    measurements: list[dict[str, Any]] = []
    per_asset_counts: dict[str, dict[str, int]] = {}
    for asset in assets:
        path = Path(str(asset["absolute_path"]))
        coarse: list[dict[str, Any]] = []
        for sequence, start in enumerate(
            regular_grid(float(asset["duration_seconds"])), 1
        ):
            child = run_measurement_child(path, start)
            item = normalize_measurement(
                asset,
                child,
                start_seconds=start,
                stage="coarse",
                rationale="frozen_regular_grid_with_beginning_and_near_end_coverage",
                sequence=sequence,
            )
            coarse.append(item)
            measurements.append(item)
        adaptive_specs = build_adaptive_starts(coarse, float(asset["duration_seconds"]))
        for sequence, spec in enumerate(adaptive_specs, 1):
            child = run_measurement_child(path, float(spec["start_seconds"]))
            item = normalize_measurement(
                asset,
                child,
                start_seconds=float(spec["start_seconds"]),
                stage="adaptive",
                rationale=str(spec["retrieval_rationale"]),
                sequence=sequence,
            )
            item["adaptive_priority_score"] = spec["priority_score"]
            measurements.append(item)
        per_asset_counts[str(asset["candidate_id"])] = {
            "coarse": len(coarse),
            "adaptive": len(adaptive_specs),
            "total": len(coarse) + len(adaptive_specs),
        }

    candidates = select_candidates(measurements)
    feasibility = assess_feasibility(
        measurements,
        candidates,
        asr_model_available=capabilities["asr_model"]["executed"],
    )
    candidate_document = {
        "schema_version": SCHEMA_VERSION,
        "recon_id": RECON_ID,
        "generated_date": RUN_DATE,
        "status": "RESTRICTED_PROVISIONAL_CANDIDATE_RECONNAISSANCE",
        "candidate_count": len(candidates),
        "candidates": candidates,
        "feasibility": feasibility,
        "boundary": {
            "gold_labels_created": False,
            "minimal_modality_necessity_claimed": False,
            "human_review_required_for_all_candidates": True,
            "public_release_authorized": False,
        },
    }

    measurement_path = repo_root / MEASUREMENTS_REL
    candidate_path = repo_root / CANDIDATES_REL
    manifest_path = repo_root / MANIFEST_REL
    atomic_write_jsonl(measurement_path, measurements)
    atomic_write_json(candidate_path, candidate_document)

    output_identities = {
        "measurements": file_identity(measurement_path, repo_root),
        "candidates": file_identity(candidate_path, repo_root),
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "recon_id": RECON_ID,
        "generated_date": RUN_DATE,
        "decision": feasibility["decision"],
        "input_gate": {
            "passed": True,
            "expected_asset_count": 5,
            "expected_total_payload_bytes": EXPECTED_PAYLOAD_BYTES,
            "authoritative_inputs": input_identities,
        },
        "capability_audit": capabilities,
        "sampling_policy": policy_record(),
        "execution": {
            "asset_count": len(assets),
            "measurement_count": len(measurements),
            "candidate_count": len(candidates),
            "per_asset_measurement_counts": per_asset_counts,
            "child_timeout_seconds": CHILD_TIMEOUT_SECONDS,
            "decode_subprocess_count": len(measurements),
            "decode_timeouts": 0,
            "decode_failures": 0,
        },
        "outputs": output_identities,
        "feasibility": feasibility,
        "safety": {
            "source_media_modified": False,
            "unlisted_media_accessed": False,
            "persistent_extracted_media_created": False,
            "transcript_published": False,
            "provisional_asr_snippet_count": 0,
            "gold_labels_created": False,
            "minimal_modality_necessity_claimed": False,
        },
    }
    atomic_write_json(manifest_path, manifest)
    atomic_write(
        repo_root / REVIEW_REL,
        public_review(feasibility, measurements, candidates, capabilities).encode(),
        restricted=False,
    )
    atomic_write(
        repo_root / RESULT_REL,
        result_note(feasibility, measurements, candidates).encode(),
        restricted=False,
    )
    for asset in assets:
        path = Path(str(asset["absolute_path"]))
        size, digest = sha256_file(path)
        if size != asset["size_bytes"] or digest != asset["sha256"]:
            raise ReconError(f"SOURCE_MEDIA_CHANGED_DURING_RECON:{asset['candidate_id']}")
    return manifest


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root containing the frozen NOAA-01 inputs.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        manifest = run(args.repo_root.resolve())
    except ReconError as exc:
        print(f"NOAA content reconnaissance failed closed: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "decision": manifest["decision"],
                "asset_count": manifest["execution"]["asset_count"],
                "measurement_count": manifest["execution"]["measurement_count"],
                "candidate_count": manifest["execution"]["candidate_count"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
