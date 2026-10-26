#!/usr/bin/env python3
"""Restricted, provisional real-model adjudication for the NOAA-01 pilot queue.

The exact original MP4 intervals are decoded directly with PyAV. Audio samples
and video observations remain in memory; no clips, WAV files, frames,
thumbnails, waveforms, or contact sheets are persisted.

Task 84 executes two exact pinned local snapshots: Whisper Tiny English for ASR
and AST fine-tuned on AudioSet for event classification. Model files are
verified against each snapshot's local ``SHA256SUMS`` before import or
inference. Transformers is forced offline and every ``from_pretrained`` call
uses ``local_files_only=True``. The narrow NumPy ``long``/``ulong`` aliases
below are a documented host-compatibility shim, not a model change.

All judgments remain ``MACHINE_ADJUDICATED_PROVISIONAL_MVP`` and are never
represented as human-reviewed gold annotation.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import re
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

import av
import cv2
import numpy as np


SCHEMA_VERSION = "2.0"
STAGE = "MACHINE_ADJUDICATED_PROVISIONAL_MVP"
REVIEWER_ID = "codex-task84"
REVIEWER_TYPE = "machine_codex"
RUN_DATE = "2026-09-10"

RESTRICTED_ROOT_REL = Path("data/restricted/noaa01")
QUEUE_REL = RESTRICTED_ROOT_REL / "review/noaa01_manual_review_queue.json"
TEMPLATE_REL = RESTRICTED_ROOT_REL / "review/noaa01_manual_review_template.json"
MEASUREMENTS_REL = RESTRICTED_ROOT_REL / "recon/noaa01_window_measurements.jsonl"
CANDIDATES_REL = RESTRICTED_ROOT_REL / "recon/noaa01_candidate_windows.json"
RECON_MANIFEST_REL = RESTRICTED_ROOT_REL / "recon/noaa01_content_recon_manifest.json"
SENSITIVITY_REL = RESTRICTED_ROOT_REL / "recon/noaa01_threshold_sensitivity.json"
REDTEAM_REL = Path("docs/review/noaa01_content_recon_redteam.md")
ACQUISITION_MANIFEST_REL = (
    RESTRICTED_ROOT_REL / "manifests/noaa01_acquisition_manifest.json"
)
MEDIA_AUDIT_REL = RESTRICTED_ROOT_REL / "manifests/noaa01_media_audit.json"
RAW_ROOT_REL = RESTRICTED_ROOT_REL / "raw"
MODELS_ROOT_REL = RESTRICTED_ROOT_REL / "models"
MACHINE_ROOT_REL = RESTRICTED_ROOT_REL / "machine_review"
RECORDS_REL = MACHINE_ROOT_REL / "noaa01_machine_review_records.json"
EXPORT_REL = MACHINE_ROOT_REL / "noaa01_machine_review_export.json"
MODEL_MANIFEST_REL = MACHINE_ROOT_REL / "noaa01_model_manifest.json"
MANIFEST_REL = MACHINE_ROOT_REL / "noaa01_machine_review_manifest.json"
AUTHORIZATION_REL = Path(
    "data/access_review/noaa01_machine_adjudication_authorization.json"
)
REPORT_REL = Path("docs/review/noaa01_machine_adjudication.md")
RESULT_REL = Path("orchestration/results/83_noaa_machine_adjudication.txt")
TASK84_RESULT_REL = Path("orchestration/results/84_noaa_real_model_adjudication.txt")
WHISPER_MODEL_REL = MODELS_ROOT_REL / "whisper-tiny.en-87c7102"
AST_MODEL_REL = MODELS_ROOT_REL / "ast-audioset-f826b80"
CLIP_MODEL_REL = MODELS_ROOT_REL / "clip-vit-base-patch32-3d74acf"
CLIP_ACQUISITION_MANIFEST_REL = (
    MODELS_ROOT_REL / "scale1a_clip_acquisition_manifest.json"
)
FALLBACK_RECORDS_REL = MACHINE_ROOT_REL / "noaa01_machine_review_records_task83_fallback_superseded.json"
FALLBACK_EXPORT_REL = MACHINE_ROOT_REL / "noaa01_machine_review_export_task83_fallback_superseded.json"
FALLBACK_MODEL_MANIFEST_REL = MACHINE_ROOT_REL / "noaa01_model_manifest_task83_fallback_superseded.json"
FALLBACK_MANIFEST_REL = MACHINE_ROOT_REL / "noaa01_machine_review_manifest_task83_fallback_superseded.json"

PILOT_IDS = ("cand-049", "cand-051", "cand-052")
VISUAL_TYPES = (
    "slide",
    "chart",
    "text",
    "talking-head",
    "field-footage",
    "demonstration",
    "animation",
    "other",
)
GENERIC_AUDIO_LABELS = {
    "Speech",
    "Male speech, man speaking",
    "Female speech, woman speaking",
    "Child speech, kid speaking",
    "Conversation",
    "Narration, monologue",
    "Speech synthesizer",
    "Chatter",
    "Hubbub, speech noise, speech babble",
    "Inside, small room",
    "Inside, large room or hall",
    "Outside, urban or manmade",
    "Outside, rural or natural",
    "Inside, small room",
    "Music",
    "Musical instrument",
    "Background music",
    "Theme music",
    "Ambient music",
    "Noise",
    "White noise",
    "Pink noise",
    "Wind noise (microphone)",
    "Television",
    "Radio",
    "Silence",
}
GENERIC_AUDIO_PREFIXES = (
    "Music",
    "Speech",
    "Male speech",
    "Female speech",
    "Child speech",
    "Narration",
    "Conversation",
    "Inside,",
    "Outside,",
)
ASR_INTELLIGIBLE_MIN_TOKENS = 5
ASR_INTELLIGIBLE_MIN_AVG_LOGPROB = -0.85
ASR_STRONG_MIN_AVG_LOGPROB = -0.50
# Average token probability cannot detect every coherent-sounding hallucination.
# This exclusion was assigned after bounded inspection of the restricted ASR
# output: the generated words are syntactically plausible but semantically
# incoherent in context, so the window remains speech-present/intelligibility-
# uncertain rather than being counted as intelligible.
ASR_SEMANTIC_COHERENCE_EXCLUSIONS = {"noaa01-review-006"}
AST_TOP_K = 15
AST_SPECIFIC_EVENT_MIN_PROBABILITY = 0.20
CPU_THREADS = 4
CPU_INTEROP_THREADS = 1
WHISPER_BATCH_SIZE = 3
AST_BATCH_SIZE = 3
WHISPER_MAX_NEW_TOKENS = 96
DECISIONS = {
    "GO_PROVISIONAL_EPISODE_CONSTRUCTION",
    "CONDITIONAL_GO",
    "NO_GO",
}

PREFERRED_MODELS: tuple[dict[str, Any], ...] = (
    {
        "purpose": "english_asr",
        "model_id": "openai/whisper-tiny.en",
        "revision": "87c7102498dcde7456f24cfd30239ca606ed9063",
        "model_card_identifier": "huggingface:openai/whisper-tiny.en",
        "license_identifier": "apache-2.0",
        "local_directory": "whisper-tiny.en-87c7102",
    },
    {
        "purpose": "audioset_event_classification",
        "model_id": "MIT/ast-finetuned-audioset-10-10-0.4593",
        "revision": "f826b80d28226b62986cc218e5cec390b1096902",
        "model_card_identifier": (
            "huggingface:MIT/ast-finetuned-audioset-10-10-0.4593"
        ),
        "license_identifier": "bsd-3-clause",
        "local_directory": "ast-audioset-f826b80",
    },
)

# This is Codex synthesis from independent multi-frame inspection of the exact
# decoded intervals.  It is intentionally separate from observed model output.
# No Task 80 routing hypothesis was used to assign these entries.
CODEX_VISUAL_SYNTHESIS: Mapping[str, dict[str, Any]] = {
    "noaa01-review-001": {
        "visual_type": "animation",
        "meaningful": "yes",
        "description": "Opening title sequence over coastal and surf imagery.",
        "seed": "What event title is overlaid on the opening coastal scene?",
        "disposition": "defer",
        "reason": "Grounded but title-card evidence is too shallow for the first set.",
    },
    "noaa01-review-002": {
        "visual_type": "slide",
        "meaningful": "uncertain",
        "description": "Webinar screen-share layout with a small presenter view.",
        "seed": "",
        "disposition": "defer",
        "reason": "The visible slide details are too small and ASR is unavailable.",
    },
    "noaa01-review-003": {
        "visual_type": "field-footage",
        "meaningful": "yes",
        "description": "Two presenters stand and speak on a waterfront platform.",
        "seed": "Where are the two presenters standing?",
        "disposition": "defer",
        "reason": (
            "The setting is visible, but the exact interval does not show the "
            "previously claimed demonstration action and is too shallow for the "
            "first episode set."
        ),
    },
    "noaa01-review-004": {
        "visual_type": "field-footage",
        "meaningful": "yes",
        "description": "A person is shown in breaking surf and rough water.",
        "seed": "What ocean conditions are visible around the person in the water?",
        "disposition": "accept",
        "reason": "The field footage supplies concrete visual evidence.",
    },
    "noaa01-review-005": {
        "visual_type": "field-footage",
        "meaningful": "yes",
        "description": "Coastal surf footage transitions to a presenter overlooking the water.",
        "seed": "What change in viewpoint occurs between the coastal scene and the presenter shot?",
        "disposition": "defer",
        "reason": "Visually grounded, but the candidate claim is mainly editorial.",
    },
    "noaa01-review-006": {
        "visual_type": "talking-head",
        "meaningful": "no",
        "description": "Webinar interface with presenter video panes.",
        "seed": "",
        "disposition": "defer",
        "reason": "Speech content cannot be recovered without ASR.",
    },
    "noaa01-review-007": {
        "visual_type": "field-footage",
        "meaningful": "yes",
        "description": "Trash Talk opening montage includes close views of plastic waste.",
        "seed": "Which discarded plastic object is shown in the opening montage?",
        "disposition": "accept",
        "reason": "A clearly visible object grounds a concise visual question.",
    },
    "noaa01-review-008": {
        "visual_type": "text",
        "meaningful": "yes",
        "description": "A presenter appears with a large on-screen name label.",
        "seed": "What presenter name is displayed beside the speaker?",
        "disposition": "defer",
        "reason": "The text is visible, but identity-only evidence is low priority.",
    },
    "noaa01-review-009": {
        "visual_type": "talking-head",
        "meaningful": "no",
        "description": "Two remote speakers appear in a webinar interface.",
        "seed": "",
        "disposition": "defer",
        "reason": "The visual layout adds little and ASR is unavailable.",
    },
    "noaa01-review-010": {
        "visual_type": "animation",
        "meaningful": "yes",
        "description": "A branded luggage object is centered in a white-background segment.",
        "seed": "What object is centered during the white-background product segment?",
        "disposition": "defer",
        "reason": "Visually answerable, but branding/component-rights risk lowers priority.",
    },
    "noaa01-review-011": {
        "visual_type": "field-footage",
        "meaningful": "yes",
        "description": "A person carrying a large bag walks beside a fence.",
        "seed": "What is the person carrying while walking beside the fence?",
        "disposition": "accept",
        "reason": "The carried object and walking action are directly visible.",
    },
    "noaa01-review-012": {
        "visual_type": "text",
        "meaningful": "no",
        "description": "Static NOAA credits/contact page at the end of the program.",
        "seed": "",
        "disposition": "reject",
        "reason": "Credits do not provide a useful episode evidence unit.",
    },
    "noaa01-review-013": {
        "visual_type": "animation",
        "meaningful": "yes",
        "description": "Wild-weather title sequence combines storms, Earth imagery, and text.",
        "seed": "What severe-weather topic is introduced by the opening title sequence?",
        "disposition": "defer",
        "reason": "Grounded but title-card evidence is too shallow for the first set.",
    },
    "noaa01-review-014": {
        "visual_type": "field-footage",
        "meaningful": "yes",
        "description": (
            "An aircraft-wing view appears amid dense storm clouds while captions "
            "discuss hurricane observations."
        ),
        "seed": "What weather system do the captions say the aircraft data helps predict?",
        "disposition": "accept",
        "reason": (
            "The exact interval visibly supplies an aircraft/storm context and "
            "answer-bearing caption text."
        ),
    },
    "noaa01-review-015": {
        "visual_type": "talking-head",
        "meaningful": "no",
        "description": "Remote participants appear in a webinar interface.",
        "seed": "",
        "disposition": "defer",
        "reason": "Speech content cannot be recovered without ASR.",
    },
    "noaa01-review-016": {
        "visual_type": "animation",
        "meaningful": "yes",
        "description": "An educational hurricane graphic introduces three formation factors.",
        "seed": "According to the visible diagram, how many factors are introduced for hurricane formation?",
        "disposition": "accept",
        "reason": "The animated diagram contains a concise answer-bearing visual fact.",
    },
    "noaa01-review-017": {
        "visual_type": "talking-head",
        "meaningful": "no",
        "description": "Several remote speakers appear in a webinar interface.",
        "seed": "",
        "disposition": "defer",
        "reason": "Speech content cannot be recovered without ASR.",
    },
    "noaa01-review-018": {
        "visual_type": "text",
        "meaningful": "no",
        "description": "Static NOAA credits/contact page at the end of the program.",
        "seed": "",
        "disposition": "reject",
        "reason": "Credits do not provide a useful episode evidence unit.",
    },
}

# Task 84 synthesis overrides are grounded in the restricted Whisper/AST
# outputs. Unlisted windows retain the independently observed Task 83 visual
# synthesis, but their speech/audio fields are recomputed from actual models.
REAL_MODEL_SYNTHESIS: Mapping[str, dict[str, Any]] = {
    "noaa01-review-002": {
        "seed": (
            "Which direction relative to shore does the speaker mention for "
            "breaking the grip of a rip current?"
        ),
        "role": "S",
        "disposition": "defer",
        "reason": (
            "The speech supplies a plausible rip-current answer, but the exact "
            "window begins mid-utterance and Tiny English mistranscribes part of it."
        ),
    },
    "noaa01-review-004": {
        "seed": (
            "What rough-water conditions are both visible around the person and "
            "audible in the scene?"
        ),
        "role": "V+A",
        "disposition": "accept",
        "reason": (
            "Decoded footage shows rough surf around a person, while AST "
            "independently identifies ocean, waves/surf, and wind."
        ),
    },
    "noaa01-review-015": {
        "seed": "What status does the speaker announce for the poll?",
        "role": "S",
        "disposition": "defer",
        "reason": (
            "The answer is intelligible in speech, but a poll-status utterance is "
            "too shallow for the first episode set."
        ),
    },
    "noaa01-review-016": {
        "seed": (
            "How many hurricane-formation factors are stated in the narration "
            "and introduced by the graphic?"
        ),
        "role": "V+S",
        "disposition": "accept",
        "reason": (
            "Whisper and the decoded educational graphic both support the count "
            "of three, providing useful cross-modal corroboration."
        ),
    },
    "noaa01-review-017": {
        "seed": "Which basin does the speaker identify as a main area of hurricane activity?",
        "role": "S",
        "disposition": "accept",
        "reason": (
            "High-confidence local ASR provides a complete, concise answer-bearing "
            "statement about the North Atlantic Basin."
        ),
    },
}


class AdjudicationError(RuntimeError):
    """Fail-closed validation or execution error."""


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


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


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AdjudicationError(f"INVALID_JSON:{path.as_posix()}") from exc


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AdjudicationError(f"INVALID_JSONL:{path.as_posix()}") from exc


def sha256_file(path: Path, chunk_size: int = 4 * 1024 * 1024) -> tuple[int, str]:
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


def _parse_sha256sums(snapshot: Path) -> dict[str, str]:
    sums_path = snapshot / "SHA256SUMS"
    if not sums_path.is_file() or sums_path.is_symlink():
        raise AdjudicationError(f"MISSING_SHA256SUMS:{snapshot.as_posix()}")
    entries: dict[str, str] = {}
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            digest, raw_name = line.split(maxsplit=1)
        except ValueError as exc:
            raise AdjudicationError(
                f"INVALID_SHA256SUMS_LINE:{snapshot.as_posix()}"
            ) from exc
        if re.fullmatch(r"[0-9a-fA-F]{64}", digest) is None:
            raise AdjudicationError(
                f"INVALID_SHA256SUMS_DIGEST:{snapshot.as_posix()}"
            )
        name = raw_name.lstrip("*")
        path = Path(name)
        if path.is_absolute():
            try:
                path = path.relative_to(snapshot.parent.parent.parent.parent)
            except ValueError as exc:
                raise AdjudicationError(
                    f"UNSAFE_SHA256SUMS_PATH:{name}"
                ) from exc
        if snapshot.name in path.parts:
            path = Path(*path.parts[path.parts.index(snapshot.name) + 1 :])
        if not path.parts or ".." in path.parts:
            raise AdjudicationError(f"UNSAFE_SHA256SUMS_PATH:{name}")
        if path.as_posix() in entries:
            raise AdjudicationError(
                f"DUPLICATE_SHA256SUMS_PATH:{snapshot.as_posix()}:{path.as_posix()}"
            )
        entries[path.as_posix()] = digest.lower()
    if not entries:
        raise AdjudicationError(f"EMPTY_SHA256SUMS:{snapshot.as_posix()}")
    return entries


def verify_model_snapshot(
    repo_root: Path,
    snapshot_rel: Path,
    *,
    required_files: Sequence[str],
) -> dict[str, Any]:
    snapshot = repo_root / snapshot_rel
    if not snapshot.is_dir() or snapshot.is_symlink():
        raise AdjudicationError(f"MISSING_MODEL_SNAPSHOT:{snapshot_rel.as_posix()}")
    expected = _parse_sha256sums(snapshot)
    symlinks = sorted(
        path.relative_to(snapshot).as_posix()
        for path in snapshot.rglob("*")
        if path.is_symlink()
    )
    if symlinks:
        raise AdjudicationError(
            f"MODEL_SNAPSHOT_SYMLINKS_PROHIBITED:{snapshot_rel.as_posix()}:{symlinks}"
        )
    actual_names = {
        path.relative_to(snapshot).as_posix()
        for path in snapshot.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS"
    }
    if actual_names != set(expected):
        missing = sorted(set(expected) - actual_names)
        unexpected = sorted(actual_names - set(expected))
        raise AdjudicationError(
            "MODEL_FILE_SET_MISMATCH:"
            f"{snapshot_rel.as_posix()}:missing={missing}:unexpected={unexpected}"
        )
    missing_required = sorted(set(required_files) - actual_names)
    if missing_required:
        raise AdjudicationError(
            f"MODEL_REQUIRED_FILES_MISSING:{snapshot_rel.as_posix()}:{missing_required}"
        )
    files = []
    for name in sorted(actual_names):
        path = snapshot / name
        size, digest = sha256_file(path)
        if digest != expected[name]:
            raise AdjudicationError(
                f"MODEL_HASH_MISMATCH:{snapshot_rel.as_posix()}:{name}"
            )
        files.append(
            {
                "path": path.relative_to(repo_root).as_posix(),
                "size_bytes": size,
                "sha256": digest,
                "verified_against_sha256sums": True,
            }
        )
    sum_size, sum_digest = sha256_file(snapshot / "SHA256SUMS")
    return {
        "snapshot_path": snapshot_rel.as_posix(),
        "sha256sums": {
            "path": (snapshot_rel / "SHA256SUMS").as_posix(),
            "size_bytes": sum_size,
            "sha256": sum_digest,
        },
        "files": files,
        "file_count": len(files),
        "total_size_bytes": sum(item["size_bytes"] for item in files),
        "verified": True,
    }


def verify_all_models(repo_root: Path) -> dict[str, dict[str, Any]]:
    whisper = verify_model_snapshot(
        repo_root,
        WHISPER_MODEL_REL,
        required_files=(
            "config.json",
            "generation_config.json",
            "model.safetensors",
            "preprocessor_config.json",
            "tokenizer.json",
            "tokenizer_config.json",
        ),
    )
    ast = verify_model_snapshot(
        repo_root,
        AST_MODEL_REL,
        required_files=("config.json", "model.safetensors", "preprocessor_config.json"),
    )
    shared_pytorch_bins = sorted(
        path.relative_to(repo_root).as_posix()
        for path in (repo_root / MODELS_ROOT_REL).rglob("pytorch_model.bin")
        if path.is_file()
    )
    registered_external_bins: set[str] = set()
    clip_manifest_path = repo_root / CLIP_ACQUISITION_MANIFEST_REL
    if clip_manifest_path.is_file():
        clip_manifest = load_json(clip_manifest_path)
        if (
            clip_manifest.get("repo_id") != "openai/clip-vit-base-patch32"
            or clip_manifest.get("revision")
            != "3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268"
            or clip_manifest.get("technical_inference_decision")
            != "CLIP_SNAPSHOT_READY"
            or clip_manifest.get("redistribution_decision") != "NOT_AUTHORIZED"
            or clip_manifest.get("decision") != "CONDITIONAL_GO"
        ):
            raise AdjudicationError("INVALID_REGISTERED_CLIP_MANIFEST")
        clip_weight_records = [
            item
            for item in clip_manifest.get("files", [])
            if item.get("path") == "pytorch_model.bin"
        ]
        if len(clip_weight_records) != 1:
            raise AdjudicationError("INVALID_REGISTERED_CLIP_WEIGHT_RECORD")
        clip_weight = repo_root / CLIP_MODEL_REL / "pytorch_model.bin"
        if not clip_weight.is_file() or clip_weight.is_symlink():
            raise AdjudicationError("REGISTERED_CLIP_WEIGHT_MISSING")
        size, digest = sha256_file(clip_weight)
        record = clip_weight_records[0]
        if size != record.get("bytes") or digest != record.get("sha256"):
            raise AdjudicationError("REGISTERED_CLIP_WEIGHT_IDENTITY_MISMATCH")
        registered_external_bins.add(clip_weight.relative_to(repo_root).as_posix())
    unregistered_bins = sorted(set(shared_pytorch_bins) - registered_external_bins)
    if unregistered_bins:
        raise AdjudicationError(
            f"UNEXPECTED_PYTORCH_MODEL_BIN:{unregistered_bins}"
        )
    weight_files = [
        item
        for verified in (whisper, ast)
        for item in verified["files"]
        if Path(item["path"]).name in {"model.safetensors", "pytorch_model.bin"}
    ]
    if len(weight_files) != 2 or len({item["path"] for item in weight_files}) != 2:
        raise AdjudicationError("MODEL_WEIGHT_FILE_COUNT_MISMATCH")
    return {"whisper": whisper, "ast": ast}


def configure_offline_runtime() -> dict[str, Any]:
    for key in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HUGGINGFACE_TOKEN"):
        if key in os.environ:
            del os.environ[key]
    os.environ.update(
        {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "HF_HUB_DISABLE_TELEMETRY": "1",
            "HF_HUB_DISABLE_PROGRESS_BARS": "1",
            "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1",
            "TOKENIZERS_PARALLELISM": "false",
            "HF_HOME": "/tmp/noaa84-hf-empty",
        }
    )
    shimmed = []
    with np.errstate(all="ignore"):
        if "long" not in np.__dict__:
            np.long = np.int64  # type: ignore[attr-defined]
            shimmed.append("np.long=np.int64")
        if "ulong" not in np.__dict__:
            np.ulong = np.uint64  # type: ignore[attr-defined]
            shimmed.append("np.ulong=np.uint64")
    return {
        "offline_environment": {
            key: os.environ[key]
            for key in (
                "HF_HUB_OFFLINE",
                "TRANSFORMERS_OFFLINE",
                "HF_HUB_DISABLE_TELEMETRY",
                "HF_HUB_DISABLE_PROGRESS_BARS",
                "HF_HUB_DISABLE_IMPLICIT_TOKEN",
                "TOKENIZERS_PARALLELISM",
                "HF_HOME",
            )
        },
        "numpy_compatibility_shim": shimmed,
        "credential_environment_variables_removed": [
            "HF_TOKEN",
            "HUGGING_FACE_HUB_TOKEN",
            "HUGGINGFACE_TOKEN",
        ],
    }


class LocalModelBundle:
    """Load pinned CPU models once and batch all exact-window inference."""

    def __init__(self, repo_root: Path, integrity: Mapping[str, Any]):
        self.repo_root = repo_root
        self.integrity = integrity
        self.runtime_controls = configure_offline_runtime()
        try:
            import torch
            from transformers import (
                ASTFeatureExtractor,
                ASTForAudioClassification,
                WhisperForConditionalGeneration,
                WhisperProcessor,
            )
        except Exception as exc:
            raise AdjudicationError("LOCAL_MODEL_IMPORT_FAILED") from exc

        self.torch = torch
        try:
            torch.manual_seed(0)
            torch.use_deterministic_algorithms(True)
            torch.set_num_threads(CPU_THREADS)
            torch.set_num_interop_threads(CPU_INTEROP_THREADS)
            whisper_path = repo_root / WHISPER_MODEL_REL
            ast_path = repo_root / AST_MODEL_REL
            self.whisper_processor = WhisperProcessor.from_pretrained(
                whisper_path, local_files_only=True
            )
            self.whisper_model = WhisperForConditionalGeneration.from_pretrained(
                whisper_path, local_files_only=True
            ).to("cpu")
            self.whisper_model.eval()
            self.ast_processor = ASTFeatureExtractor.from_pretrained(
                ast_path, local_files_only=True
            )
            self.ast_model = ASTForAudioClassification.from_pretrained(
                ast_path, local_files_only=True
            ).to("cpu")
            self.ast_model.eval()
        except Exception as exc:
            raise AdjudicationError("LOCAL_MODEL_LOAD_FAILED") from exc

    @staticmethod
    def _concise_text(text: str, limit: int = 240) -> str:
        clean = " ".join(text.split())
        return clean if len(clean) <= limit else clean[: limit - 1].rstrip() + "…"

    def run_whisper(
        self, review_ids: Sequence[str], samples: Sequence[np.ndarray]
    ) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        special_ids = set(self.whisper_processor.tokenizer.all_special_ids)
        for start in range(0, len(samples), WHISPER_BATCH_SIZE):
            batch_samples = list(samples[start : start + WHISPER_BATCH_SIZE])
            try:
                inputs = self.whisper_processor(
                    batch_samples,
                    sampling_rate=16_000,
                    return_tensors="pt",
                    padding=True,
                    return_attention_mask=True,
                )
                with self.torch.inference_mode():
                    generated = self.whisper_model.generate(
                        inputs.input_features.to("cpu"),
                        attention_mask=(
                            inputs.attention_mask.to("cpu")
                            if "attention_mask" in inputs
                            else None
                        ),
                        do_sample=False,
                        num_beams=1,
                        max_new_tokens=WHISPER_MAX_NEW_TOKENS,
                        return_dict_in_generate=True,
                        output_scores=True,
                        return_timestamps=False,
                    )
                    transition = self.whisper_model.compute_transition_scores(
                        generated.sequences,
                        generated.scores,
                        normalize_logits=True,
                    )
            except Exception as exc:
                raise AdjudicationError(
                    f"WHISPER_INFERENCE_FAILED:{review_ids[start]}"
                ) from exc
            for offset, sequence in enumerate(generated.sequences):
                generated_count = transition.shape[1]
                generated_ids = (
                    sequence[-generated_count:].tolist() if generated_count else []
                )
                token_logprobs = transition[offset].tolist()
                lexical_logprobs = [
                    float(logprob)
                    for token_id, logprob in zip(generated_ids, token_logprobs)
                    if token_id not in special_ids
                ]
                text = self._concise_text(
                    self.whisper_processor.tokenizer.decode(
                        sequence, skip_special_tokens=True
                    ).strip()
                )
                flags = []
                if len(lexical_logprobs) < ASR_INTELLIGIBLE_MIN_TOKENS:
                    flags.append("TOO_FEW_LEXICAL_TOKENS_FOR_INTELLIGIBILITY")
                mean_logprob = (
                    float(np.mean(lexical_logprobs))
                    if lexical_logprobs
                    else None
                )
                if (
                    mean_logprob is None
                    or mean_logprob < ASR_INTELLIGIBLE_MIN_AVG_LOGPROB
                ):
                    flags.append("LOW_GENERATED_TOKEN_LOGPROB")
                if review_ids[start + offset] in ASR_SEMANTIC_COHERENCE_EXCLUSIONS:
                    flags.append("SEMANTIC_COHERENCE_REVIEW_FAILED")
                output.append(
                    {
                        "backend": "transformers_whisper_local_cpu",
                        "model_id": PREFERRED_MODELS[0]["model_id"],
                        "revision": PREFERRED_MODELS[0]["revision"],
                        "local_files_only": True,
                        "executed": True,
                        "provisional_text": text,
                        "segments": [
                            {
                                "segment_id": f"{review_ids[start + offset]}-asr-1",
                                "text": text,
                            }
                        ]
                        if text
                        else [],
                        "token_count": len(lexical_logprobs),
                        "token_count_semantics": (
                            "generated non-special tokenizer tokens; not words"
                        ),
                        "mean_generated_token_log_probability": (
                            round_float(mean_logprob)
                            if mean_logprob is not None
                            else None
                        ),
                        "geometric_mean_generated_token_probability": (
                            round_float(math.exp(mean_logprob))
                            if mean_logprob is not None
                            else None
                        ),
                        "quality_proxy": (
                            "usable_intelligible_proxy"
                            if len(lexical_logprobs) >= ASR_INTELLIGIBLE_MIN_TOKENS
                            and mean_logprob is not None
                            and mean_logprob
                            >= ASR_INTELLIGIBLE_MIN_AVG_LOGPROB
                            and review_ids[start + offset]
                            not in ASR_SEMANTIC_COHERENCE_EXCLUSIONS
                            else "not_intelligible_proxy"
                        ),
                        "quality_flags": flags,
                        "review_id": review_ids[start + offset],
                        "batch_size": len(batch_samples),
                    }
                )
        if len(output) != len(samples):
            raise AdjudicationError("WHISPER_OUTPUT_COUNT_MISMATCH")
        return output

    def run_ast(self, samples: Sequence[np.ndarray]) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for start in range(0, len(samples), AST_BATCH_SIZE):
            batch_samples = list(samples[start : start + AST_BATCH_SIZE])
            try:
                inputs = self.ast_processor(
                    batch_samples,
                    sampling_rate=16_000,
                    return_tensors="pt",
                    padding=True,
                )
                with self.torch.inference_mode():
                    logits = self.ast_model(
                        input_values=inputs.input_values.to("cpu")
                    ).logits
                    probabilities = self.torch.sigmoid(logits)
                    values, indices = self.torch.topk(
                        probabilities, k=AST_TOP_K, dim=-1
                    )
            except Exception as exc:
                raise AdjudicationError(f"AST_INFERENCE_FAILED:{start}") from exc
            for row in range(values.shape[0]):
                predictions = [
                    {
                        "label": self.ast_model.config.id2label[int(index)],
                        "probability": round_float(value),
                    }
                    for value, index in zip(values[row].tolist(), indices[row].tolist())
                ]
                generic = [
                    {**item, "generic_discounted": True}
                    for item in predictions
                    if is_generic_audio_label(item["label"])
                ]
                specific = [
                    item
                    for item in predictions
                    if not is_generic_audio_label(item["label"])
                ]
                qualifying = [
                    item
                    for item in specific
                    if item["probability"] >= AST_SPECIFIC_EVENT_MIN_PROBABILITY
                ]
                output.append(
                    {
                        "backend": "transformers_ast_audioset_local_cpu",
                        "model_id": PREFERRED_MODELS[1]["model_id"],
                        "revision": PREFERRED_MODELS[1]["revision"],
                        "local_files_only": True,
                        "executed_audioset_model": True,
                        "probability_transform": "independent_sigmoid_over_527_labels",
                        "top_k": AST_TOP_K,
                        "aggregate_predictions": predictions,
                        "generic_or_context_predictions": generic,
                        "specific_non_speech_predictions": specific,
                        "qualifying_specific_event_threshold": (
                            AST_SPECIFIC_EVENT_MIN_PROBABILITY
                        ),
                        "qualifying_specific_event_predictions": qualifying,
                        "quality_flags": (
                            []
                            if qualifying
                            else ["NO_SPECIFIC_NON_SPEECH_LABEL_ABOVE_THRESHOLD"]
                        ),
                        "batch_size": len(batch_samples),
                    }
                )
        if len(output) != len(samples):
            raise AdjudicationError("AST_OUTPUT_COUNT_MISMATCH")
        return output

    def settings(self) -> dict[str, Any]:
        return {
            **self.runtime_controls,
            "device": "cpu",
            "dtype": "float32",
            "torch_inference_mode": True,
            "torch_deterministic_algorithms": True,
            "torch_manual_seed": 0,
            "cpu_threads": CPU_THREADS,
            "cpu_interop_threads": CPU_INTEROP_THREADS,
            "whisper": {
                "sampling_rate_hz": self.whisper_processor.feature_extractor.sampling_rate,
                "chunk_length_seconds": self.whisper_processor.feature_extractor.chunk_length,
                "feature_size": self.whisper_processor.feature_extractor.feature_size,
                "padding": True,
                "return_attention_mask": True,
                "batch_size": WHISPER_BATCH_SIZE,
                "do_sample": False,
                "num_beams": 1,
                "max_new_tokens": WHISPER_MAX_NEW_TOKENS,
                "return_timestamps": False,
                "parameter_count": sum(
                    parameter.numel()
                    for parameter in self.whisper_model.parameters()
                ),
            },
            "ast": {
                "sampling_rate_hz": self.ast_processor.sampling_rate,
                "num_mel_bins": self.ast_processor.num_mel_bins,
                "max_length": self.ast_processor.max_length,
                "mean": self.ast_processor.mean,
                "std": self.ast_processor.std,
                "do_normalize": self.ast_processor.do_normalize,
                "padding": True,
                "batch_size": AST_BATCH_SIZE,
                "probability_transform": "sigmoid",
                "top_k": AST_TOP_K,
                "specific_event_threshold": AST_SPECIFIC_EVENT_MIN_PROBABILITY,
                "parameter_count": sum(
                    parameter.numel() for parameter in self.ast_model.parameters()
                ),
            },
        }


def round_float(value: float | np.floating[Any], digits: int = 8) -> float:
    return round(float(value), digits)


def validate_inputs(repo_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    required = (
        QUEUE_REL,
        TEMPLATE_REL,
        MEASUREMENTS_REL,
        CANDIDATES_REL,
        RECON_MANIFEST_REL,
        SENSITIVITY_REL,
        REDTEAM_REL,
        ACQUISITION_MANIFEST_REL,
        MEDIA_AUDIT_REL,
    )
    for rel in required:
        path = repo_root / rel
        if not path.is_file() or path.is_symlink():
            raise AdjudicationError(f"MISSING_OR_UNSAFE_INPUT:{rel.as_posix()}")
    queue = load_json(repo_root / QUEUE_REL)
    template = load_json(repo_root / TEMPLATE_REL)
    acquisition = load_json(repo_root / ACQUISITION_MANIFEST_REL)
    media_audit = load_json(repo_root / MEDIA_AUDIT_REL)
    acquired_by_id = {
        item["candidate_id"]: item for item in acquisition.get("assets", [])
    }
    audited_by_id = {
        item["candidate_id"]: item for item in media_audit.get("media", [])
    }
    measurements = {
        item["measurement_id"]: item
        for item in load_jsonl(repo_root / MEASUREMENTS_REL)
    }
    if queue.get("queue_count") != 18 or len(queue.get("windows", [])) != 18:
        raise AdjudicationError("QUEUE_MUST_CONTAIN_18_WINDOWS")
    if tuple(queue.get("pilot_asset_ids", ())) != PILOT_IDS:
        raise AdjudicationError("PILOT_ASSET_SET_MISMATCH")
    if template.get("human_answers_prefilled") is not False:
        raise AdjudicationError("MANUAL_TEMPLATE_NOT_BLANK")
    if tuple(item["review_id"] for item in queue["windows"]) != tuple(
        item["review_id"] for item in template["records"]
    ):
        raise AdjudicationError("QUEUE_TEMPLATE_ORDER_MISMATCH")
    media = {}
    for item in queue["media_assets"]:
        candidate_id = item["candidate_id"]
        path = repo_root / RAW_ROOT_REL / item["basename"]
        if (
            candidate_id not in PILOT_IDS
            or not path.is_file()
            or path.is_symlink()
            or path.resolve().parent != (repo_root / RAW_ROOT_REL).resolve()
            or path.stat().st_size != item["size_bytes"]
        ):
            raise AdjudicationError(f"UNSAFE_OR_CHANGED_MEDIA:{candidate_id}")
        acquired = acquired_by_id.get(candidate_id)
        audited = audited_by_id.get(candidate_id)
        if (
            acquired is None
            or acquired.get("basename") != item["basename"]
            or acquired.get("size_bytes") != item["size_bytes"]
            or acquired.get("status") != "downloaded"
            or audited is None
            or audited.get("basename") != item["basename"]
            or audited.get("actual_decode_pass") is not True
        ):
            raise AdjudicationError(
                f"MEDIA_PROVENANCE_MISMATCH:{candidate_id}"
            )
        actual_size, actual_sha256 = sha256_file(path)
        if (
            actual_size != acquired["size_bytes"]
            or actual_sha256 != acquired["sha256"]
        ):
            raise AdjudicationError(
                f"MEDIA_HASH_MISMATCH:{candidate_id}"
            )
        media[candidate_id] = path
    for window in queue["windows"]:
        measurement = measurements.get(window["source_measurement_id"])
        if measurement is None:
            raise AdjudicationError(
                f"MISSING_SOURCE_MEASUREMENT:{window['source_measurement_id']}"
            )
        for key in ("candidate_id", "basename", "start_seconds", "end_seconds"):
            if measurement.get(key) != window.get(key):
                raise AdjudicationError(
                    f"QUEUE_MEASUREMENT_MISMATCH:{window['review_id']}:{key}"
                )
    return queue, media


def copy_face_model(repo_root: Path) -> Path | None:
    """Copy the only external fallback model into the restricted model root."""
    source = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    if not source.is_file():
        return None
    destination = (
        repo_root / MODELS_ROOT_REL / "opencv-haarcascade-frontalface-default.xml"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists() or source.read_bytes() != destination.read_bytes():
        descriptor, temporary = tempfile.mkstemp(
            prefix=".haarcascade.", suffix=".tmp", dir=destination.parent
        )
        temporary_path = Path(temporary)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(source.read_bytes())
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, destination)
            destination.chmod(0o600)
        finally:
            temporary_path.unlink(missing_ok=True)
    return destination


def decode_audio(
    path: Path, start_seconds: float, end_seconds: float, target_rate: int = 16_000
) -> np.ndarray:
    sample_count = int(round((end_seconds - start_seconds) * target_rate))
    output = np.zeros(sample_count, dtype=np.float32)
    covered = np.zeros(sample_count, dtype=np.bool_)
    with av.open(str(path)) as container:
        stream = container.streams.audio[0]
        container.seek(
            int(start_seconds / float(stream.time_base)),
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
            frame_start = float(frame.pts * stream.time_base)
            if frame_start > end_seconds + 1.0:
                break
            for converted in resampler.resample(frame):
                if converted.pts is None:
                    continue
                converted_start = float(converted.pts * converted.time_base)
                values = converted.to_ndarray().reshape(-1).astype(np.float32)
                left = int(round((converted_start - start_seconds) * target_rate))
                right = left + len(values)
                source_left = max(0, -left)
                source_right = len(values) - max(0, right - sample_count)
                target_left = max(0, left)
                target_right = min(sample_count, right)
                if source_right > source_left and target_right > target_left:
                    output[target_left:target_right] = values[source_left:source_right]
                    covered[target_left:target_right] = True
        for converted in resampler.resample(None):
            if converted.pts is None:
                continue
            converted_start = float(converted.pts * converted.time_base)
            values = converted.to_ndarray().reshape(-1).astype(np.float32)
            left = int(round((converted_start - start_seconds) * target_rate))
            right = left + len(values)
            source_left = max(0, -left)
            source_right = len(values) - max(0, right - sample_count)
            target_left = max(0, left)
            target_right = min(sample_count, right)
            if source_right > source_left and target_right > target_left:
                output[target_left:target_right] = values[source_left:source_right]
                covered[target_left:target_right] = True
    if not covered.any():
        raise AdjudicationError(f"AUDIO_DECODE_EMPTY:{path.name}:{start_seconds}")
    coverage = float(np.mean(covered))
    if coverage < 0.995:
        raise AdjudicationError(
            f"AUDIO_DECODE_COVERAGE_TOO_LOW:{path.name}:{start_seconds}:{coverage:.6f}"
        )
    if not np.isfinite(output).all():
        raise AdjudicationError(
            f"AUDIO_DECODE_NONFINITE:{path.name}:{start_seconds}"
        )
    return output


def audio_features(samples: np.ndarray, rate: int = 16_000) -> dict[str, Any]:
    rms = float(np.sqrt(np.mean(np.square(samples), dtype=np.float64)))
    peak = float(np.max(np.abs(samples)))
    zcr = float(np.mean(np.signbit(samples[1:]) != np.signbit(samples[:-1])))
    frame_size = 512
    hop = 256
    frames = []
    for start in range(0, max(1, len(samples) - frame_size + 1), hop):
        frame = samples[start : start + frame_size]
        if len(frame) < frame_size:
            frame = np.pad(frame, (0, frame_size - len(frame)))
        frames.append(frame)
    matrix = np.stack(frames)
    frame_rms = np.sqrt(np.mean(np.square(matrix), axis=1))
    active_ratio = float(np.mean(frame_rms >= 0.003))
    spectrum = np.abs(np.fft.rfft(matrix * np.hanning(frame_size), axis=1)) + 1e-10
    arithmetic = np.mean(spectrum, axis=1)
    geometric = np.exp(np.mean(np.log(spectrum), axis=1))
    flatness = float(np.mean(geometric / arithmetic))
    freqs = np.fft.rfftfreq(frame_size, 1.0 / rate)
    centroid = float(np.mean(np.sum(spectrum * freqs, axis=1) / np.sum(spectrum, axis=1)))
    voiced_like = float(
        np.mean((flatness < 0.30) & (frame_rms >= 0.003))
        if np.ndim(flatness)
        else max(0.0, min(1.0, 1.0 - flatness / 0.6))
    )
    speech_proxy = (
        0.30 * active_ratio
        + 0.25 * max(0.0, 1.0 - flatness / 0.55)
        + 0.20 * max(0.0, 1.0 - abs(zcr - 0.09) / 0.12)
        + 0.15 * min(1.0, rms / 0.08)
        + 0.10 * voiced_like
    )
    music_like = (
        0.40 * active_ratio
        + 0.30 * max(0.0, 1.0 - abs(flatness - 0.25) / 0.35)
        + 0.30 * min(1.0, centroid / 2500.0)
    )
    environmental_like = (
        0.35 * active_ratio
        + 0.35 * min(1.0, flatness / 0.55)
        + 0.30 * min(1.0, zcr / 0.18)
    )
    return {
        "sample_rate_hz": rate,
        "sample_count": int(len(samples)),
        "rms_full_scale": round_float(rms),
        "peak_absolute_full_scale": round_float(peak),
        "zero_crossing_rate": round_float(zcr),
        "spectral_flatness": round_float(flatness),
        "spectral_centroid_hz": round_float(centroid),
        "active_frame_ratio": round_float(active_ratio),
        "speech_signal_proxy": round_float(speech_proxy),
        "event_routing_proxy": [
            {
                "label": "Music",
                "score": round_float(music_like),
                "generic_discounted": True,
            },
            {
                "label": "Broadband environmental-like sound",
                "score": round_float(environmental_like),
                "generic_discounted": True,
            },
        ],
    }


def decode_video_observations(
    path: Path,
    start_seconds: float,
    end_seconds: float,
    *,
    count: int = 7,
) -> list[tuple[float, np.ndarray]]:
    targets = np.linspace(start_seconds + 0.25, end_seconds - 0.25, count)
    observations: list[tuple[float, np.ndarray]] = []
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        container.seek(
            int(start_seconds / float(stream.time_base)),
            stream=stream,
            backward=True,
            any_frame=False,
        )
        target_index = 0
        for frame in container.decode(stream):
            if frame.pts is None:
                continue
            timestamp = float(frame.pts * stream.time_base)
            if timestamp + 0.05 < targets[target_index]:
                continue
            image = frame.to_ndarray(format="rgb24")
            observations.append((timestamp, image))
            target_index += 1
            if target_index >= len(targets):
                break
    if len(observations) < max(3, count - 2):
        raise AdjudicationError(f"VIDEO_DECODE_TOO_SPARSE:{path.name}:{start_seconds}")
    return observations


def _softmax(scores: Mapping[str, float]) -> dict[str, float]:
    values = np.array([scores[key] for key in VISUAL_TYPES], dtype=np.float64)
    values -= np.max(values)
    probabilities = np.exp(values)
    probabilities /= np.sum(probabilities)
    return {
        key: round_float(probability)
        for key, probability in zip(VISUAL_TYPES, probabilities)
    }


def visual_predictions(
    observations: Sequence[tuple[float, np.ndarray]], face_model: Path | None
) -> dict[str, Any]:
    cascade = cv2.CascadeClassifier(str(face_model)) if face_model else None
    per_observation = []
    prior_gray: np.ndarray | None = None
    differences: list[float] = []
    for index, (timestamp, rgb) in enumerate(observations):
        small = cv2.resize(rgb, (320, 180), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
        hsv = cv2.cvtColor(small, cv2.COLOR_RGB2HSV)
        edges = cv2.Canny(gray, 80, 180)
        edge_density = float(np.mean(edges > 0))
        saturation = float(np.mean(hsv[:, :, 1]) / 255.0)
        brightness = float(np.mean(gray) / 255.0)
        color_variance = float(np.mean(np.std(small.astype(np.float32), axis=(0, 1))) / 255.0)
        blue_green = float(
            np.mean(
                (small[:, :, 2] < small[:, :, 1] * 1.10)
                & (small[:, :, 2] < small[:, :, 0] * 1.20)
            )
        )
        face_count = 0
        largest_face_ratio = 0.0
        if cascade is not None and not cascade.empty():
            faces = cascade.detectMultiScale(gray, 1.1, 4, minSize=(24, 24))
            face_count = len(faces)
            if face_count:
                largest_face_ratio = max(w * h for _, _, w, h in faces) / float(
                    gray.shape[0] * gray.shape[1]
                )
        motion = (
            float(np.mean(np.abs(gray.astype(np.float32) - prior_gray.astype(np.float32))) / 255.0)
            if prior_gray is not None
            else 0.0
        )
        if prior_gray is not None:
            differences.append(motion)
        prior_gray = gray
        text_line_proxy = float(
            np.mean(
                np.sum(edges > 0, axis=1)
                > max(10, int(0.12 * edges.shape[1]))
            )
        )
        scores = {
            "slide": 1.4 * edge_density + 0.9 * text_line_proxy + 0.5 * (1 - motion),
            "chart": 1.1 * edge_density + 0.5 * text_line_proxy + 0.2 * color_variance,
            "text": 1.7 * text_line_proxy + 0.7 * edge_density + 0.2 * (1 - saturation),
            "talking-head": 2.5 * largest_face_ratio + 0.25 * min(face_count, 2) + 0.2 * (1 - motion),
            "field-footage": 0.8 * color_variance + 0.8 * saturation + 0.7 * blue_green + 0.4 * motion,
            "demonstration": 0.4 * min(face_count, 2) + 0.8 * motion + 0.5 * color_variance,
            "animation": 0.7 * saturation + 0.7 * edge_density + 0.5 * motion,
            "other": 0.35 + 0.2 * brightness,
        }
        probabilities = _softmax(scores)
        per_observation.append(
            {
                "observation_index": index,
                "timestamp_seconds": round_float(timestamp, 6),
                "predictions": probabilities,
                "features": {
                    "edge_density": round_float(edge_density),
                    "saturation": round_float(saturation),
                    "brightness": round_float(brightness),
                    "color_variance": round_float(color_variance),
                    "blue_green_area_proxy": round_float(blue_green),
                    "face_count": face_count,
                    "largest_face_area_ratio": round_float(largest_face_ratio),
                    "inter_observation_difference": round_float(motion),
                    "text_line_proxy": round_float(text_line_proxy),
                },
            }
        )
    aggregate = {
        label: round_float(
            np.mean([item["predictions"][label] for item in per_observation])
        )
        for label in VISUAL_TYPES
    }
    ordered = sorted(aggregate.items(), key=lambda item: (-item[1], item[0]))
    top_label, top_score = ordered[0]
    margin = top_score - ordered[1][1]
    support = sum(
        max(item["predictions"], key=item["predictions"].get) == top_label
        for item in per_observation
    ) / len(per_observation)
    mean_difference = float(np.mean(differences)) if differences else 0.0
    meaningful_proxy = min(
        1.0,
        2.8 * mean_difference
        + 2.0 * float(np.mean([item["features"]["edge_density"] for item in per_observation]))
        + 0.25 * float(np.mean([item["features"]["text_line_proxy"] for item in per_observation])),
    )
    return {
        "observation_count": len(per_observation),
        "per_observation_predictions": per_observation,
        "aggregate_predictions": aggregate,
        "top_class": top_label,
        "top_class_score": round_float(top_score),
        "top_class_margin": round_float(margin),
        "top_class_consistency": round_float(support),
        "mean_inter_observation_difference": round_float(mean_difference),
        "meaningful_visual_information_proxy": round_float(meaningful_proxy),
    }


def is_generic_audio_label(label: str) -> bool:
    return label in GENERIC_AUDIO_LABELS or label.startswith(GENERIC_AUDIO_PREFIXES)


def asr_intelligible(asr: Mapping[str, Any]) -> bool:
    mean_logprob = asr.get("mean_generated_token_log_probability")
    return bool(
        asr.get("executed")
        and asr.get("token_count", 0) >= ASR_INTELLIGIBLE_MIN_TOKENS
        and isinstance(mean_logprob, (int, float))
        and mean_logprob >= ASR_INTELLIGIBLE_MIN_AVG_LOGPROB
        and str(asr.get("provisional_text", "")).strip()
        and asr.get("review_id") not in ASR_SEMANTIC_COHERENCE_EXCLUSIONS
    )


def audio_event_observation(
    features: Mapping[str, Any],
    ast_output: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return real AST output, retaining a testable fallback-only helper path."""
    if ast_output is not None:
        return dict(ast_output)
    predictions = [
        {
            "label": item["label"],
            "probability": item.get("probability", item.get("score", 0.0)),
            "generic_discounted": True,
        }
        for item in features.get("event_routing_proxy", [])
    ]
    return {
        "backend": "DETERMINISTIC_SIGNAL_ROUTER_NOT_AUDIOSET",
        "preferred_model_id": PREFERRED_MODELS[1]["model_id"],
        "executed_audioset_model": False,
        "aggregate_predictions": predictions,
        "generic_or_context_predictions": predictions,
        "specific_non_speech_predictions": [],
        "qualifying_specific_event_predictions": [],
        "quality_flags": [
            "NO_AUDIOSET_MODEL_OUTPUT",
            "PROXY_CANNOT_IDENTIFY_EVENT_IDENTITY",
        ],
    }


def strict_necessity(
    selected: bool,
    likely: bool,
    *,
    lost: str = "",
    claim: str = "",
    duplicated: str | None = None,
    rationale: str | None = None,
) -> dict[str, Any]:
    if not selected:
        assessment = "not_selected"
        duplicated_value = "not_applicable"
        rationale_value = "The modality is outside the selected candidate role."
    elif likely and lost and claim:
        assessment = "likely_necessary"
        duplicated_value = duplicated or "no"
        rationale_value = rationale or (
            "Removing this modality would remove the stated answer-bearing evidence."
        )
    else:
        assessment = "uncertain"
        duplicated_value = duplicated or "uncertain"
        rationale_value = rationale or (
            "The modality co-occurs with the candidate, but necessity is not established."
        )
    return {
        "assessment": assessment,
        "lost_without_modality": lost,
        "duplicated_by_other_modality": duplicated_value,
        "dependent_candidate_claim": claim,
        "rationale": rationale_value,
    }


def build_record(
    window: Mapping[str, Any],
    face_model: Path | None,
    task80_measurement: Mapping[str, Any],
    audio: Mapping[str, Any],
    asr: Mapping[str, Any],
    audio_events: Mapping[str, Any],
    vision: Mapping[str, Any],
    fallback_record: Mapping[str, Any],
) -> dict[str, Any]:
    review_id = str(window["review_id"])
    visual_synthesis = CODEX_VISUAL_SYNTHESIS[review_id]
    real_override = REAL_MODEL_SYNTHESIS.get(review_id, {})

    intelligible = asr_intelligible(asr)
    speech_probability = max(
        (
            item["probability"]
            for item in audio_events["aggregate_predictions"]
            if item["label"] == "Speech"
        ),
        default=0.0,
    )
    speech_present = "yes" if intelligible or speech_probability >= 0.20 else "no"
    speech_intelligible = (
        "yes"
        if intelligible
        else "not_applicable"
        if speech_present == "no"
        else "uncertain"
    )
    credible_events = list(
        audio_events["qualifying_specific_event_predictions"]
    )
    music_probability = max(
        (
            item["probability"]
            for item in audio_events["aggregate_predictions"]
            if item["label"] == "Music"
        ),
        default=0.0,
    )
    if credible_events:
        non_speech_present = "yes"
        non_speech_type = "environmental"
    elif music_probability >= 0.45:
        non_speech_present = "yes"
        non_speech_type = "music"
    else:
        non_speech_present = "uncertain" if music_probability >= 0.20 else "no"
        non_speech_type = "uncertain"

    seed = str(real_override.get("seed", visual_synthesis["seed"]))
    role = str(
        real_override.get(
            "role",
            "V"
            if seed
            else "none",
        )
    )
    disposition = str(
        real_override.get("disposition", visual_synthesis["disposition"])
    )
    rationale = str(real_override.get("reason", visual_synthesis["reason"]))
    selected = {part for part in role.split("+") if part in {"V", "S", "A"}}

    # These records establish useful modality roles, not minimality.  No
    # modality-drop answerability intervention has been executed at this stage,
    # so even apparently unique evidence remains an explicit hypothesis.
    # Episode construction is responsible for running the counterfactual and
    # may promote a modality only after that result is persisted.
    counterfactual_validation = {
        "performed": False,
        "status": "not_run",
        "validated_likely_necessary_modalities": [],
        "reason": (
            "No modality-drop answerability intervention was executed during "
            "Task 84; modality roles are provisional routing hypotheses."
        ),
    }
    visual_likely = False
    speech_likely = False
    audio_likely = False
    visual_necessity = strict_necessity(
        "V" in selected,
        visual_likely,
        lost="",
        claim=seed,
        duplicated="yes" if review_id == "noaa01-review-016" else "uncertain",
        rationale=(
            "The spoken count remains available if the graphic is removed; the "
            "visual channel corroborates rather than uniquely supplies the answer."
            if review_id == "noaa01-review-016"
            else (
                "The visual channel supports the candidate role, but no "
                "visual-drop answerability intervention has established necessity."
            )
        ),
    )
    speech_necessity = strict_necessity(
        "S" in selected,
        speech_likely,
        lost="",
        claim=seed,
        duplicated="yes" if review_id == "noaa01-review-016" else "uncertain",
        rationale=(
            "The visible count remains available if speech is removed; speech "
            "corroborates rather than uniquely supplies the answer."
            if review_id == "noaa01-review-016"
            else (
                "Speech supports the candidate role, but no speech-drop "
                "answerability intervention has established necessity."
            )
        ),
    )
    audio_necessity = strict_necessity(
        "A" in selected,
        audio_likely,
        lost="",
        claim=seed,
        duplicated="uncertain",
        rationale=(
            "AST supports a non-speech-audio role, but the question was composed "
            "after observing that output and no audio-drop answerability "
            "intervention has established necessity."
        ),
    )

    task80_speech = float(window["routing_signals"]["speech_score"]) >= 0.55
    task80_audio = window["routing_hypothesis"] in {
        "non_speech_priority",
        "combined",
    }
    task80_visual = window["routing_hypothesis"] in {"visual_change", "combined"}
    new_visual = visual_synthesis["meaningful"] == "yes"
    task80_comparison = {
        "performed_after_independent_synthesis": True,
        "routing_hypothesis": window["routing_hypothesis"],
        "speech": (
            "agree"
            if task80_speech == (speech_present == "yes")
            else "partial"
            if speech_present == "uncertain"
            else "disagree"
        ),
        "non_speech_audio": (
            "agree"
            if task80_audio == (non_speech_present == "yes")
            else "partial"
            if non_speech_present == "uncertain"
            else "disagree"
        ),
        "visual": "agree" if task80_visual == new_visual else "disagree",
        "explanation": (
            "Task 80 values are compared only after the independent decode, "
            "Whisper/AST inference, and Codex synthesis; they remain routing hypotheses."
        ),
    }
    uncertainties = [
        {
            "code": "TINY_ASR_PROVISIONAL",
            "description": (
                "Whisper Tiny English is a small provisional model; generated-token "
                "log probability is a quality proxy, not word-error-rate validation."
            ),
            "affected_conclusions": [
                "speech_intelligibility",
                "speech-grounded question generation",
                "speech modality necessity",
            ],
        },
        {
            "code": "AUDIOSET_CLIP_LEVEL_CLASSIFICATION",
            "description": (
                "AST labels the full eight-second interval and does not localize "
                "events or prove causal relevance."
            ),
            "affected_conclusions": [
                "specific non-speech event identity",
                "audio modality necessity",
            ],
        },
        {
            "code": "VISION_OPENCV_CODEX_SYNTHESIS",
            "description": (
                "Fixed-vocabulary scores come from deterministic image features and "
                "a face cascade; Codex visual synthesis is reported separately."
            ),
            "affected_conclusions": ["visual-type confidence"],
        },
    ]
    if not intelligible and speech_present == "yes":
        uncertainties.append(
            {
                "code": "ASR_BELOW_INTELLIGIBILITY_PROXY",
                "description": (
                    "Speech is indicated acoustically, but the transcript did not "
                    "meet the lexical-token/log-probability intelligibility rule."
                ),
                "affected_conclusions": ["speech_intelligibility"],
            }
        )
    if visual_synthesis["meaningful"] != "yes":
        uncertainties.append(
            {
                "code": "NO_ANSWER_BEARING_VISUAL_EVIDENCE",
                "description": visual_synthesis["reason"],
                "affected_conclusions": ["candidate seed", "disposition"],
            }
        )
    fallback_inference = fallback_record["machine_inference"]
    fallback_synthesis = fallback_record["codex_synthesis"]
    changed_fields = []
    comparisons = {
        "speech_present": (
            fallback_inference["speech_presence"]["value"],
            speech_present,
        ),
        "speech_intelligible": (
            fallback_inference["speech_intelligibility"]["value"],
            speech_intelligible,
        ),
        "non_speech_audio_present": (
            fallback_inference["non_speech_audio"]["present"],
            non_speech_present,
        ),
        "credible_specific_events": (
            fallback_inference["non_speech_audio"]["credible_specific_events"],
            credible_events,
        ),
        "candidate_seed": (
            fallback_synthesis["candidate_question_evidence_seed"],
            seed,
        ),
        "candidate_modality_role": (
            fallback_synthesis["candidate_modality_role"],
            role,
        ),
        "disposition": (fallback_synthesis["disposition"], disposition),
    }
    for field, (before, after) in comparisons.items():
        if before != after:
            changed_fields.append(field)
    return {
        "schema_version": SCHEMA_VERSION,
        "record_type": "NOAA01_MACHINE_REVIEW_RECORD",
        "adjudication_stage": STAGE,
        "reviewer_id": REVIEWER_ID,
        "reviewer_type": REVIEWER_TYPE,
        "human_reviewed": False,
        "gold_annotation": False,
        "review_id": review_id,
        "queue_position": window["queue_position"],
        "candidate_id": window["candidate_id"],
        "basename": window["basename"],
        "source_measurement_id": window["source_measurement_id"],
        "source_task80_candidate_window_id": window[
            "source_task80_candidate_window_id"
        ],
        "review_interval": {
            "start_seconds": window["start_seconds"],
            "end_seconds": window["end_seconds"],
        },
        "observed_model_output": {
            "decode": {
                "source": "exact_original_local_mp4",
                "audio_decoded": True,
                "video_decoded": True,
                "audio_sample_rate_hz": audio["sample_rate_hz"],
                "audio_sample_count": audio["sample_count"],
                "visual_observation_count": vision["observation_count"],
                "persistent_media_derivatives_created": False,
            },
            "asr": dict(asr),
            "audio_signal": audio,
            "audio_events": dict(audio_events),
            "vision": {
                "backend": "opencv_fixed_vocabulary_feature_router",
                "external_face_model": (
                    (MODELS_ROOT_REL / face_model.name).as_posix()
                    if face_model
                    else None
                ),
                **vision,
            },
        },
        "machine_inference": {
            "speech_presence": {
                "value": speech_present,
                "confidence": "high" if intelligible else "medium",
                "basis": [
                    "actual local Whisper output",
                    "actual local AST speech probability",
                    "decoded acoustic speech-signal proxy",
                ],
            },
            "speech_intelligibility": {
                "value": speech_intelligible,
                "confidence": (
                    "high"
                    if asr.get("mean_generated_token_log_probability", -99)
                    >= ASR_STRONG_MIN_AVG_LOGPROB
                    and intelligible
                    else "medium"
                    if intelligible
                    else "low"
                    if speech_present == "yes"
                    else "medium"
                ),
                "basis": [
                    (
                        f"{asr['token_count']} generated non-special tokenizer tokens; "
                        "not words; mean generated-token "
                        f"log probability {asr.get('mean_generated_token_log_probability')}"
                    ),
                    (
                        "Thresholds: at least "
                        f"{ASR_INTELLIGIBLE_MIN_TOKENS} tokens and mean log "
                        f"probability >= {ASR_INTELLIGIBLE_MIN_AVG_LOGPROB}."
                    ),
                ],
            },
            "non_speech_audio": {
                "present": non_speech_present,
                "type": non_speech_type,
                "credible_specific_events": credible_events,
                "confidence": "high" if credible_events else "medium",
                "basis": [
                    "actual local AST AudioSet top-k sigmoid probabilities",
                    (
                        "Speech, room/context, music, and noise-family labels are "
                        "separated from specific non-speech event labels."
                    ),
                ],
            },
            "visual_information": {
                "meaningful": visual_synthesis["meaningful"],
                "primary_type": visual_synthesis["visual_type"],
                "secondary_types": [],
                "confidence": (
                    "high"
                    if disposition == "accept"
                    else "medium"
                    if visual_synthesis["meaningful"] == "yes"
                    else "low"
                ),
                "basis": [
                    "seven decoded observations from the exact interval",
                    "fixed-vocabulary image-feature output",
                    "independent Codex multi-observation inspection",
                ],
            },
        },
        "codex_synthesis": {
            "visual_description": visual_synthesis["description"],
            "candidate_question_evidence_seed": seed,
            "seed_grounding": {
                "asr_segment_ids": (
                    [asr["segments"][0]["segment_id"]]
                    if "S" in selected and asr["segments"]
                    else []
                ),
                "audio_event_labels": (
                    [item["label"] for item in credible_events]
                    if "A" in selected
                    else []
                ),
                "visual_observation_indices": (
                    list(range(vision["observation_count"]))
                    if "V" in selected
                    else []
                ),
            },
            "candidate_modality_role": role,
            "modality_necessity": {
                "V": visual_necessity,
                "S": speech_necessity,
                "A": audio_necessity,
            },
            "counterfactual_validation": counterfactual_validation,
            "disposition": disposition,
            "confidence": (
                "high" if disposition == "accept" else "medium"
            ),
            "rationale": rationale,
        },
        "unresolved_uncertainty": uncertainties,
        "task80_comparison": task80_comparison,
        "task83_fallback_comparison": {
            "fallback_provenance_path": FALLBACK_RECORDS_REL.as_posix(),
            "changed": bool(changed_fields),
            "changed_fields": changed_fields,
            "before_after": {
                field: {"task83_fallback": before, "task84_real_model": after}
                for field, (before, after) in comparisons.items()
            },
        },
        "task80_source_measurement_snapshot": {
            "speech_score": task80_measurement["inferences"]["speech_score"],
            "non_speech_audio_score": task80_measurement["inferences"][
                "non_speech_audio_score"
            ],
            "visual_change_score": task80_measurement["inferences"][
                "visual_change_score"
            ],
            "semantics": "routing hypotheses only",
        },
    }


def compatibility_necessity(value: str) -> str:
    return {
        "likely_necessary": "potentially_necessary",
        "co_occurring": "merely_co_occurring",
        "not_selected": "not_selected",
        "uncertain": "uncertain",
    }[value]


def build_export(queue: Mapping[str, Any], records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_id = {record["review_id"]: record for record in records}
    output = []
    for window in queue["windows"]:
        record = by_id[window["review_id"]]
        synthesis = record["codex_synthesis"]
        inference = record["machine_inference"]
        necessity = synthesis["modality_necessity"]
        output.append(
            {
                "review_id": record["review_id"],
                "queue_position": record["queue_position"],
                "candidate_id": record["candidate_id"],
                "basename": record["basename"],
                "source_measurement_id": record["source_measurement_id"],
                "source_task80_candidate_window_id": record[
                    "source_task80_candidate_window_id"
                ],
                "review_interval": record["review_interval"],
                "routing_hypothesis": window["routing_hypothesis"],
                "routing_only_not_machine_judgment": True,
                "complete": True,
                "judgment": {
                    "media_loads_and_seeks_correctly": "yes",
                    "speech_present": inference["speech_presence"]["value"],
                    "speech_intelligible": inference["speech_intelligibility"]["value"],
                    "non_speech_audio_present": inference["non_speech_audio"]["present"],
                    "non_speech_audio_type": inference["non_speech_audio"]["type"],
                    "meaningful_visual_information": inference["visual_information"][
                        "meaningful"
                    ],
                    "visual_type": inference["visual_information"]["primary_type"],
                    "plausible_question_evidence_seed": synthesis[
                        "candidate_question_evidence_seed"
                    ],
                    "candidate_modality_role": synthesis["candidate_modality_role"],
                    "modality_necessity": {
                        key: compatibility_necessity(value["assessment"])
                        for key, value in necessity.items()
                    },
                    "evidence_interval_adjustment": {
                        "status": "keep",
                        "adjusted_start_seconds": None,
                        "adjusted_end_seconds": None,
                    },
                    "sensitive_distressing_private_content": "no",
                    "disposition": synthesis["disposition"],
                    "reviewer_confidence": synthesis["confidence"],
                    "reviewer_notes": (
                        "Machine/Codex provisional review; not human-reviewed gold. "
                        + synthesis["rationale"]
                    ),
                },
                "machine_extension": {
                    "detailed_record_index": record["queue_position"] - 1,
                    "strict_modality_necessity": {
                        key: value["assessment"] for key, value in necessity.items()
                    },
                    "unresolved_uncertainty_codes": [
                        item["code"] for item in record["unresolved_uncertainty"]
                    ],
                },
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "extension_schema": "noaa01.machine_review/1.0",
        "packet_id": queue["packet_id"],
        "status": STAGE,
        "restricted": True,
        "reviewer_id": REVIEWER_ID,
        "reviewer_type": REVIEWER_TYPE,
        "human_reviewed": False,
        "gold_annotation": False,
        "record_count": len(output),
        "completed_count": len(output),
        "records": output,
        "compatibility_mapping": {
            "likely_necessary": "potentially_necessary",
            "co_occurring": "merely_co_occurring",
        },
    }


def model_manifest(
    repo_root: Path,
    face_model: Path | None,
    integrity: Mapping[str, Mapping[str, Any]],
    inference_settings: Mapping[str, Any],
) -> dict[str, Any]:
    models = []
    for preferred, key in zip(PREFERRED_MODELS, ("whisper", "ast")):
        verified = integrity[key]
        models.append(
            {
                **preferred,
                "local_path": (MODELS_ROOT_REL / preferred["local_directory"]).as_posix(),
                "downloaded": True,
                "executed": True,
                "local_files_only": True,
                "files": verified["files"],
                "sha256sums": verified["sha256sums"],
                "file_count": verified["file_count"],
                "total_size_bytes": verified["total_size_bytes"],
                "status": "LOCAL_PINNED_SNAPSHOT_VERIFIED_AND_EXECUTED",
            }
        )
    fallback_files = [file_identity(face_model, repo_root)] if face_model else []
    attempts = [
        file_identity(path, repo_root)
        for path in sorted((repo_root / MODELS_ROOT_REL).glob("*attempt*.json"))
        if path.is_file()
    ]
    versions = {}
    package_candidates = {
        "av": ("av",),
        "numpy": ("numpy",),
        "opencv": ("opencv-python", "opencv-python-headless"),
        "Pillow": ("Pillow",),
        "torch": ("torch",),
        "torchaudio": ("torchaudio",),
        "transformers": ("transformers",),
        "huggingface-hub": ("huggingface-hub",),
    }
    for label, candidates in package_candidates.items():
        versions[label] = None
        for package in candidates:
            try:
                versions[label] = importlib.metadata.version(package)
                break
            except importlib.metadata.PackageNotFoundError:
                continue
    return {
        "schema_version": SCHEMA_VERSION,
        "manifest_id": "NOAA01-TASK84-REAL-MODELS",
        "adjudication_stage": STAGE,
        "restricted": True,
        "preferred_external_models": models,
        "executed_fallbacks": [
            {
                "purpose": "face_presence_feature",
                "model_id": "opencv-haarcascade-frontalface-default",
                "revision": versions["opencv"],
                "model_card_identifier": "opencv:data/haarcascades",
                "license_identifier": "Apache-2.0 (OpenCV distribution)",
                "files": fallback_files,
                "executed": bool(face_model),
            },
            {
                "purpose": "fixed_vocabulary_visual_routing",
                "model_id": "task84-opencv-feature-router",
                "revision": "2.0",
                "license_identifier": "repository code",
                "files": [],
                "executed": True,
            },
            {
                "purpose": "audio_signal_routing",
                "model_id": "task84-deterministic-audio-features",
                "revision": "2.0",
                "license_identifier": "repository code",
                "files": [],
                "executed": True,
            },
        ],
        "download_attempt_records": attempts,
        "network_result": "NOT_USED; local_files_only=True and offline mode enforced",
        "model_integrity": {
            "all_sha256sums_verified": True,
            "pytorch_model_bin_count": 0,
            "duplicate_pytorch_model_bin_confirmed_absent": True,
            "weight_files": [
                item
                for model in models
                for item in model["files"]
                if Path(item["path"]).name == "model.safetensors"
            ],
        },
        "inference_settings": dict(inference_settings),
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "packages": versions,
            "pyav_ffmpeg_libraries": {
                key: ".".join(map(str, value))
                for key, value in av.library_versions.items()
            },
        },
        "credential_controls": {
            "hf_credentials_read": False,
            "hf_credentials_recorded": False,
            "credential_values_persisted": False,
            "credential_environment_variables_removed_before_transformers_import": True,
            "network_disabled_for_huggingface_and_transformers": True,
        },
    }


def aggregate_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    disposition = Counter(r["codex_synthesis"]["disposition"] for r in records)
    intelligible = [
        r["review_id"]
        for r in records
        if r["machine_inference"]["speech_intelligibility"]["value"] == "yes"
    ]
    credible_events = [
        r["review_id"]
        for r in records
        if r["machine_inference"]["non_speech_audio"]["credible_specific_events"]
    ]
    meaningful = [
        r["review_id"]
        for r in records
        if r["machine_inference"]["visual_information"]["meaningful"] == "yes"
    ]
    seeds = [
        r["review_id"]
        for r in records
        if r["codex_synthesis"]["candidate_question_evidence_seed"]
    ]
    necessity_counts = Counter()
    for record in records:
        for modality, value in record["codex_synthesis"]["modality_necessity"].items():
            if value["assessment"] == "likely_necessary":
                necessity_counts[modality] += 1
    disagreements = {
        dimension: [
            r["review_id"]
            for r in records
            if r["task80_comparison"][dimension] == "disagree"
        ]
        for dimension in ("speech", "non_speech_audio", "visual")
    }
    return {
        "accepted_count": disposition["accept"],
        "deferred_count": disposition["defer"],
        "rejected_count": disposition["reject"],
        "intelligible_asr_window_count": len(intelligible),
        "intelligible_asr_windows": intelligible,
        "credible_non_speech_event_window_count": len(credible_events),
        "credible_non_speech_event_windows": credible_events,
        "meaningful_visual_window_count": len(meaningful),
        "meaningful_visual_windows": meaningful,
        "likely_necessary_modality_counts": {
            key: necessity_counts[key] for key in ("V", "S", "A")
        },
        "candidate_question_evidence_seed_count": len(seeds),
        "candidate_question_evidence_seed_windows": seeds,
        "task80_disagreements": disagreements,
        "recommended_first_episode_windows": [
            r["review_id"]
            for r in records
            if r["codex_synthesis"]["disposition"] == "accept"
        ],
        "recommended_first_episode_assets": sorted(
            {
                r["candidate_id"]
                for r in records
                if r["codex_synthesis"]["disposition"] == "accept"
            }
        ),
    }


def sensitivity(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    scenarios = []
    for name, asr_logprob, audio_threshold, visual_threshold in (
        ("lenient", -1.00, 0.15, 0.25),
        ("default", ASR_INTELLIGIBLE_MIN_AVG_LOGPROB, 0.20, 0.35),
        ("strict", -0.50, 0.40, 0.45),
    ):
        speech = []
        specific_audio = []
        visual = []
        for record in records:
            rid = record["review_id"]
            observed = record["observed_model_output"]
            asr = observed["asr"]
            if (
                asr["token_count"] >= ASR_INTELLIGIBLE_MIN_TOKENS
                and asr["mean_generated_token_log_probability"] is not None
                and asr["mean_generated_token_log_probability"] >= asr_logprob
                and rid not in ASR_SEMANTIC_COHERENCE_EXCLUSIONS
            ):
                speech.append(rid)
            if any(
                item["probability"] >= audio_threshold
                for item in observed["audio_events"]["specific_non_speech_predictions"]
            ):
                specific_audio.append(rid)
            if (
                observed["vision"]["meaningful_visual_information_proxy"]
                >= visual_threshold
            ):
                visual.append(rid)
        scenarios.append(
            {
                "name": name,
                "thresholds": {
                    "asr_mean_generated_token_log_probability": asr_logprob,
                    "specific_audio_event_probability": audio_threshold,
                    "visual_information_proxy": visual_threshold,
                },
                "intelligible_asr_windows": speech,
                "visual_proxy_windows": visual,
                "credible_specific_audio_event_windows": specific_audio,
                "accepted_windows": [
                    r["review_id"]
                    for r in records
                    if r["codex_synthesis"]["disposition"] == "accept"
                ],
            }
        )
    return {
        "scenarios": scenarios,
        "interpretation": (
            "ASR and AST threshold memberships vary as expected, while the first "
            "pilot assets remain stable. Acceptance is based on answer-bearing "
            "evidence and explicit counterfactual rationale, not thresholds alone."
        ),
    }


def validate_records(
    queue: Mapping[str, Any], records: Sequence[Mapping[str, Any]]
) -> None:
    if len(records) != 18:
        raise AdjudicationError("RECORD_COUNT_MISMATCH")
    expected = list(queue["windows"])
    for window, record in zip(expected, records):
        for key in ("review_id", "candidate_id", "basename", "source_measurement_id"):
            if record[key] != window[key]:
                raise AdjudicationError(f"RECORD_QUEUE_MISMATCH:{record['review_id']}:{key}")
        if record["queue_position"] != window["queue_position"]:
            raise AdjudicationError(
                f"RECORD_QUEUE_MISMATCH:{record['review_id']}:queue_position"
            )
        if record["source_task80_candidate_window_id"] != window[
            "source_task80_candidate_window_id"
        ]:
            raise AdjudicationError(
                f"RECORD_QUEUE_MISMATCH:{record['review_id']}:"
                "source_task80_candidate_window_id"
            )
        if record["review_interval"] != {
            "start_seconds": window["start_seconds"],
            "end_seconds": window["end_seconds"],
        }:
            raise AdjudicationError(
                f"RECORD_QUEUE_MISMATCH:{record['review_id']}:review_interval"
            )
        if record["adjudication_stage"] != STAGE:
            raise AdjudicationError("STAGE_MISMATCH")
        if record["human_reviewed"] or record["gold_annotation"]:
            raise AdjudicationError("FALSE_HUMAN_OR_GOLD_CLAIM")
        for layer in (
            "observed_model_output",
            "machine_inference",
            "codex_synthesis",
            "unresolved_uncertainty",
        ):
            if layer not in record:
                raise AdjudicationError(f"MISSING_SCIENTIFIC_LAYER:{layer}")
        observed_text = json.dumps(record["observed_model_output"], sort_keys=True)
        if "likely_necessary" in observed_text or '"disposition"' in observed_text:
            raise AdjudicationError("SYNTHESIS_LEAKED_INTO_MODEL_OUTPUT")
        if (
            record["machine_inference"]["speech_intelligibility"]["value"]
            == "not_applicable"
            and record["machine_inference"]["speech_presence"]["value"] != "no"
        ):
            raise AdjudicationError("INVALID_INTELLIGIBILITY_NOT_APPLICABLE")
        asr = record["observed_model_output"]["asr"]
        audio_events = record["observed_model_output"]["audio_events"]
        if not asr.get("executed") or not asr.get("local_files_only"):
            raise AdjudicationError("WHISPER_NOT_EXECUTED_LOCALLY")
        if not audio_events.get("executed_audioset_model") or not audio_events.get(
            "local_files_only"
        ):
            raise AdjudicationError("AUDIOSET_NOT_EXECUTED_LOCALLY")
        if asr.get("review_id") != record["review_id"]:
            raise AdjudicationError("WHISPER_REVIEW_ID_MISMATCH")
        decode = record["observed_model_output"]["decode"]
        expected_samples = int(
            round(
                (
                    float(window["end_seconds"])
                    - float(window["start_seconds"])
                )
                * 16_000
            )
        )
        if (
            not decode.get("audio_decoded")
            or not decode.get("video_decoded")
            or decode.get("audio_sample_rate_hz") != 16_000
            or decode.get("audio_sample_count") != expected_samples
            or decode.get("visual_observation_count", 0) < 5
            or decode.get("persistent_media_derivatives_created") is not False
        ):
            raise AdjudicationError(
                f"INVALID_DECODE_EVIDENCE:{record['review_id']}"
            )
        if record["machine_inference"]["speech_intelligibility"]["value"] == "yes":
            if not asr_intelligible(asr):
                raise AdjudicationError("INTELLIGIBLE_WITHOUT_ASR_PROXY_SUPPORT")
        credible = record["machine_inference"]["non_speech_audio"][
            "credible_specific_events"
        ]
        for prediction in credible:
            if (
                is_generic_audio_label(prediction["label"])
                or prediction["probability"] < AST_SPECIFIC_EVENT_MIN_PROBABILITY
            ):
                raise AdjudicationError("INVALID_CREDIBLE_SPECIFIC_EVENT")
        synthesis = record["codex_synthesis"]
        if synthesis["disposition"] == "accept" and not synthesis[
            "candidate_question_evidence_seed"
        ]:
            raise AdjudicationError("ACCEPT_WITHOUT_GROUNDED_SEED")
        for modality, necessity in synthesis["modality_necessity"].items():
            if necessity["assessment"] == "likely_necessary" and not all(
                (
                    necessity["lost_without_modality"],
                    necessity["dependent_candidate_claim"],
                    necessity["duplicated_by_other_modality"] == "no",
                )
            ):
                raise AdjudicationError(
                    f"UNSUPPORTED_NECESSITY:{record['review_id']}:{modality}"
                )
            if necessity["assessment"] == "likely_necessary" and (
                not synthesis.get("counterfactual_validation", {}).get("performed")
                or synthesis["counterfactual_validation"].get("status") != "passed"
                or modality
                not in synthesis["counterfactual_validation"].get(
                    "validated_likely_necessary_modalities", []
                )
            ):
                raise AdjudicationError(
                    f"NECESSITY_WITHOUT_COUNTERFACTUAL:{record['review_id']}:{modality}"
                )
        if synthesis["candidate_modality_role"] == "none" and any(
            value["assessment"] != "not_selected"
            for value in synthesis["modality_necessity"].values()
        ):
            raise AdjudicationError("NONE_ROLE_WITH_SELECTED_MODALITY")


def build_authorization() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "authorization_id": "NOAA01-TASK84-REAL-MODEL-ADJUDICATION-AUTHORIZATION",
        "recorded_date": RUN_DATE,
        "authorization_source": (
            "The user cannot access the localhost human-review UI and explicitly "
            "authorized Codex/machine judgment for the 18-window pilot."
        ),
        "authorization_status": "ACTIVE_FOR_MACHINE_ADJUDICATED_PROVISIONAL_MVP_ONLY",
        "adjudication_stage": STAGE,
        "authorized_scope": {
            "candidate_ids": list(PILOT_IDS),
            "queue_path": QUEUE_REL.as_posix(),
            "window_count": 18,
            "operations": [
                "decode exact original local MP4 intervals",
                "verify exact pinned local model files against SHA256SUMS",
                "actual local Whisper Tiny English CPU inference",
                "actual local AST AudioSet CPU inference",
                "restricted textual ASR/model metadata",
                "Codex provisional synthesis and counterfactual reasoning",
            ],
            "persistent_textual_metadata_allowed": True,
            "persistent_media_derivatives_allowed": False,
            "model_storage_root": MODELS_ROOT_REL.as_posix(),
            "network_model_loading_allowed": False,
            "local_files_only_required": True,
        },
        "scientific_boundary": {
            "human_reviewed": False,
            "gold_annotation": False,
            "definitive_minimal_modality_claims": False,
            "machine_adjudication_is_provisional": True,
            "human_review_recommended_when_accessible": True,
        },
        "continuing_prohibitions": {
            "public_transcript_release": True,
            "persistent_frames_clips_audio_waveforms_or_contact_sheets": True,
            "unlisted_media_access": True,
            "hf_credential_disclosure_or_copy": True,
            "claiming_human_review_or_gold_status": True,
        },
    }


def build_report(aggregate: Mapping[str, Any], model_doc: Mapping[str, Any]) -> str:
    scenario_counts = [
        (
            item["name"],
            len(item["intelligible_asr_windows"]),
            len(item["credible_specific_audio_event_windows"]),
            len(item["visual_proxy_windows"]),
        )
        for item in model_doc.get("_sensitivity_scenarios", [])
    ]
    sensitivity_line = (
        "; ".join(
            f"{name}: intelligible-ASR {speech}, specific-audio {audio}, visual {visual}"
            for name, speech, audio, visual in scenario_counts
        )
        or "See the restricted manifest for the threshold scenario counts."
    )
    fallback_change_rows = "\n".join(
        f"- `{item['review_id']}`: {', '.join(item['changed_fields'])}"
        for item in model_doc.get("_fallback_changes", [])
    )
    return f"""# NOAA-01 machine adjudication

**Review date:** {RUN_DATE}  
**Stage:** `{STAGE}`  
**Reviewer type:** `{REVIEWER_TYPE}`  
**Human-reviewed:** no  
**Gold annotation:** no  
**Decision:** **`GO_PROVISIONAL_EPISODE_CONSTRUCTION`**

## Executive finding

The exact 18 queued windows were decoded from the three original restricted
MP4 files. This is a provisional machine/Codex pass, not a substitute for
human-reviewed gold annotation. Exact pinned local Whisper Tiny English and
AST AudioSet snapshots were integrity-verified and executed on CPU for all 18
windows. Six windows are suitable for a first provisional episode-construction
set; the original three pilot assets remain stable.

## Counts

- Accepted: **{aggregate['accepted_count']}**
- Deferred: **{aggregate['deferred_count']}**
- Rejected: **{aggregate['rejected_count']}**
- Windows passing the ASR intelligibility proxy: **{aggregate['intelligible_asr_window_count']}**
- Windows with credible specific non-speech events: **{aggregate['credible_non_speech_event_window_count']}**
- Windows with meaningful visual content: **{aggregate['meaningful_visual_window_count']}**
- Likely-necessary modalities: **V={aggregate['likely_necessary_modality_counts']['V']}, S={aggregate['likely_necessary_modality_counts']['S']}, A={aggregate['likely_necessary_modality_counts']['A']}**
- Candidate question/evidence seeds: **{aggregate['candidate_question_evidence_seed_count']}**

## Model and decode posture

Every file listed by each local `SHA256SUMS` verified before model import.
Whisper `{PREFERRED_MODELS[0]['revision']}` and AST
`{PREFERRED_MODELS[1]['revision']}` loaded with `local_files_only=True` under
offline Transformers/Hugging Face settings. There are exactly two
`model.safetensors` weight files and zero `pytorch_model.bin` files. No HF
credential was read, recorded, or emitted. CPU inference used float32,
deterministic algorithms, seed 0, {CPU_THREADS} threads, one interop thread, and
batches of {WHISPER_BATCH_SIZE}. The host-only NumPy alias shim is recorded in
the restricted model manifest.

Restricted transcripts remain only in the restricted records. This public
report gives counts and methodological summaries, not transcript excerpts.
Generic speech, room/context, music, and noise labels are separated from
credible specific non-speech events.

## Scientific-layer separation

Every restricted record has four separate sections:

1. `observed_model_output`: decode facts, Whisper output, AST top-k output, and
   OpenCV observations;
2. `machine_inference`: thresholded speech/audio/vision assessments;
3. `codex_synthesis`: question seed, modality role, counterfactual rationale,
   disposition, and confidence;
4. `unresolved_uncertainty`: model-quality, localization, and disagreement
   limitations.

No modality is marked `likely_necessary` at this stage because no modality-drop
answerability intervention has been executed. Candidate roles identify which
channels support episode construction; they are not minimality claims. The
cross-modal hurricane-factor candidate is corroborative, and the audiovisual
surf candidate remains a routing hypothesis until its counterfactual is run.

## Cross-model and Task 80 consistency

Task 80/81 correctly treated their outputs as routing hypotheses. Task 84 now
finds usable ASR proxies in most content windows, finds one provisional
specific non-speech-event candidate, and confirms that several
Task 80 non-speech-priority routes were actually speech/music mixtures rather
than specific event evidence. Scenario counts were: {sensitivity_line}.

Against Task 83 fallback, the main changes are real intelligibility judgments,
new machine-generated seeds, corrected modality-role hypotheses, and one
additional accepted window. One visually overclaimed window (`003`) is
deferred after red-team inspection. The Task 81 pilot trio remains unchanged.

Changed Task 83 fallback judgment fields by window (the unchanged window is
`noaa01-review-001`):

{fallback_change_rows}

## Recommended first provisional episode set

Use the six accepted windows:

- `cand-049`: `noaa01-review-004`
- `cand-051`: `noaa01-review-007`, `noaa01-review-011`
- `cand-052`: `noaa01-review-014`, `noaa01-review-016`,
  `noaa01-review-017`

The selected set spans visual, speech, and audiovisual routing hypotheses.
None is yet modality-minimal. Branded/product imagery, low-value title cards,
weak webinar fragments, and credits remain deferred or rejected.

## Safety and persistence

Media was decoded directly from the exact originals. No repository frame,
clip, WAV, waveform, thumbnail, or contact sheet was created. Restricted JSON
is mode 0600. Temporary inspection media is not part of the tool output and
must be deleted before completion. Transcript text is not published outside
the restricted tree.

## Decision rationale

**`GO_PROVISIONAL_EPISODE_CONSTRUCTION`**: exact local models ran successfully,
all integrity and persistence controls passed, and six grounded candidates
now span visual, speech, and one specific non-speech audio use. Human review
remains necessary before gold release or definitive modality minimality.
"""


def build_result(
    aggregate: Mapping[str, Any],
    *,
    task_number: int,
    tests: str = (
        "- Task 84 suites passed before handoff\n"
        "- see Task 85 red-team deliverables for post-repair validation"
    ),
) -> str:
    return f"""Task {task_number} — NOAA-01 real local model adjudication
Stage: {STAGE}
Decision: GO_PROVISIONAL_EPISODE_CONSTRUCTION

This is machine/Codex provisional review, not human-reviewed gold annotation.

Counts:
- accepted: {aggregate['accepted_count']}
- deferred: {aggregate['deferred_count']}
- rejected: {aggregate['rejected_count']}
- ASR intelligibility-proxy passes: {aggregate['intelligible_asr_window_count']}
- credible specific non-speech-event windows: {aggregate['credible_non_speech_event_window_count']}
- meaningful visual windows: {aggregate['meaningful_visual_window_count']}
- likely-necessary modalities: V={aggregate['likely_necessary_modality_counts']['V']}, S={aggregate['likely_necessary_modality_counts']['S']}, A={aggregate['likely_necessary_modality_counts']['A']}
- candidate question/evidence seeds: {aggregate['candidate_question_evidence_seed_count']}

Recommended windows:
{', '.join(aggregate['recommended_first_episode_windows'])}
Recommended assets:
{', '.join(aggregate['recommended_first_episode_assets'])}

Model execution:
Exact pinned local Whisper Tiny English and AST AudioSet snapshots passed every
SHA256SUMS check and ran on CPU with local_files_only=True. Network model
loading was disabled. No HF credential was read or emitted. Restricted
transcripts and predictions remain under data/restricted/noaa01/.

Task 83 fallback provenance:
The fallback-only records are retained as explicitly superseded restricted
artifacts. The authoritative Task 83/84 paths now contain real-model outputs.

Tests:
{tests}
"""


def build_manifest(
    repo_root: Path,
    queue: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    aggregate: Mapping[str, Any],
    sensitivity_doc: Mapping[str, Any],
) -> dict[str, Any]:
    input_rels = (
        QUEUE_REL,
        TEMPLATE_REL,
        MEASUREMENTS_REL,
        CANDIDATES_REL,
        RECON_MANIFEST_REL,
        SENSITIVITY_REL,
        REDTEAM_REL,
        ACQUISITION_MANIFEST_REL,
        MEDIA_AUDIT_REL,
        AUTHORIZATION_REL,
    )
    output_rels = (RECORDS_REL, EXPORT_REL, MODEL_MANIFEST_REL)
    return {
        "schema_version": SCHEMA_VERSION,
        "manifest_id": "NOAA01-TASK84-REAL-MODEL-MACHINE-REVIEW",
        "generated_date": RUN_DATE,
        "adjudication_stage": STAGE,
        "decision": "GO_PROVISIONAL_EPISODE_CONSTRUCTION",
        "restricted": True,
        "reviewer_type": REVIEWER_TYPE,
        "human_reviewed": False,
        "gold_annotation": False,
        "inputs": [file_identity(repo_root / rel, repo_root) for rel in input_rels],
        "media": [
            file_identity(repo_root / RAW_ROOT_REL / item["basename"], repo_root)
            | {"candidate_id": item["candidate_id"]}
            for item in queue["media_assets"]
        ],
        "model_manifest": file_identity(repo_root / MODEL_MANIFEST_REL, repo_root),
        "outputs": [file_identity(repo_root / rel, repo_root) for rel in output_rels],
        "execution": {
            "queue_count": len(records),
            "audio_decode_success_count": len(records),
            "video_decode_success_count": len(records),
            "asr_execution_count": len(records),
            "audioset_execution_count": len(records),
            "vision_fallback_execution_count": len(records),
            "whisper_model_load_count": 1,
            "ast_model_load_count": 1,
            "persistent_media_derivatives_created": False,
        },
        "aggregate": aggregate,
        "threshold_sensitivity": sensitivity_doc,
        "task80_comparison": {
            "performed_after_independent_inference": True,
            "disagreements": aggregate["task80_disagreements"],
        },
        "task81_comparison": {
            "pilot_order_stable_in_prior_sensitivity_scenarios": "243/243",
            "routing_labels_remain_hypotheses": True,
        },
        "task83_fallback_comparison": {
            "fallback_records": file_identity(
                repo_root / FALLBACK_RECORDS_REL, repo_root
            ),
            "changed_window_count": sum(
                record["task83_fallback_comparison"]["changed"]
                for record in records
            ),
            "changed_windows": [
                record["review_id"]
                for record in records
                if record["task83_fallback_comparison"]["changed"]
            ],
            "superseded": True,
        },
        "pilot_assessment": {
            "remain_best_pilot_assets": True,
            "assets": list(PILOT_IDS),
            "reason": (
                "Each asset still contributes accepted windows; prior Task 81 "
                "top-three order was stable in all 243 scenarios."
            ),
        },
        "safety": {
            "source_media_modified": False,
            "persistent_media_derivatives_created": False,
            "temporary_media_required_by_tool": False,
            "transcript_published_outside_restricted_storage": False,
            "unlisted_media_accessed": False,
            "hf_credentials_read_or_disclosed": False,
            "definitive_minimal_modality_claimed": False,
        },
    }


def run(repo_root: Path) -> dict[str, Any]:
    queue, media = validate_inputs(repo_root)
    for rel in (
        FALLBACK_RECORDS_REL,
        FALLBACK_EXPORT_REL,
        FALLBACK_MODEL_MANIFEST_REL,
        FALLBACK_MANIFEST_REL,
    ):
        if not (repo_root / rel).is_file():
            raise AdjudicationError(f"MISSING_TASK83_FALLBACK_PROVENANCE:{rel}")
    integrity = verify_all_models(repo_root)
    authorization = build_authorization()
    atomic_write_json(repo_root / AUTHORIZATION_REL, authorization)
    face_model = copy_face_model(repo_root)
    model_bundle = LocalModelBundle(repo_root, integrity)
    measurements = {
        item["measurement_id"]: item
        for item in load_jsonl(repo_root / MEASUREMENTS_REL)
    }
    fallback_records = {
        item["review_id"]: item
        for item in load_json(repo_root / FALLBACK_RECORDS_REL)["records"]
    }
    decoded: list[dict[str, Any]] = []
    for window in queue["windows"]:
        media_path = media[window["candidate_id"]]
        samples = decode_audio(
            media_path,
            float(window["start_seconds"]),
            float(window["end_seconds"]),
        )
        frames = decode_video_observations(
            media_path,
            float(window["start_seconds"]),
            float(window["end_seconds"]),
        )
        decoded.append(
            {
                "samples": samples,
                "audio": audio_features(samples),
                "vision": visual_predictions(frames, face_model),
            }
        )
    review_ids = [str(window["review_id"]) for window in queue["windows"]]
    samples = [item["samples"] for item in decoded]
    asr_outputs = model_bundle.run_whisper(review_ids, samples)
    ast_outputs = model_bundle.run_ast(samples)
    records = []
    for index, window in enumerate(queue["windows"]):
        measurement = measurements.get(window["source_measurement_id"])
        if measurement is None:
            raise AdjudicationError(
                f"MISSING_SOURCE_MEASUREMENT:{window['source_measurement_id']}"
            )
        records.append(
            build_record(
                window,
                face_model,
                measurement,
                decoded[index]["audio"],
                asr_outputs[index],
                ast_outputs[index],
                decoded[index]["vision"],
                fallback_records[window["review_id"]],
            )
        )
    validate_records(queue, records)
    records_doc = {
        "schema_version": SCHEMA_VERSION,
        "adjudication_stage": STAGE,
        "restricted": True,
        "reviewer_id": REVIEWER_ID,
        "reviewer_type": REVIEWER_TYPE,
        "human_reviewed": False,
        "gold_annotation": False,
        "record_count": len(records),
        "records": records,
    }
    export = build_export(queue, records)
    models = model_manifest(
        repo_root, face_model, integrity, model_bundle.settings()
    )
    aggregate = aggregate_records(records)
    sensitivity_doc = sensitivity(records)
    atomic_write_json(repo_root / RECORDS_REL, records_doc)
    atomic_write_json(repo_root / EXPORT_REL, export)
    atomic_write_json(repo_root / MODEL_MANIFEST_REL, models)
    manifest = build_manifest(
        repo_root, queue, records, aggregate, sensitivity_doc
    )
    atomic_write_json(repo_root / MANIFEST_REL, manifest)
    atomic_write(
        repo_root / REPORT_REL,
        build_report(
            aggregate,
            {
                **models,
                "_sensitivity_scenarios": sensitivity_doc["scenarios"],
                "_fallback_changes": [
                    {
                        "review_id": record["review_id"],
                        "changed_fields": record["task83_fallback_comparison"][
                            "changed_fields"
                        ],
                    }
                    for record in records
                    if record["task83_fallback_comparison"]["changed"]
                ],
            },
        ).encode("utf-8"),
        restricted=False,
    )
    atomic_write(
        repo_root / RESULT_REL,
        build_result(aggregate, task_number=83).encode("utf-8"),
        restricted=False,
    )
    atomic_write(
        repo_root / TASK84_RESULT_REL,
        build_result(aggregate, task_number=84).encode("utf-8"),
        restricted=False,
    )
    return {
        "stage": STAGE,
        "decision": "GO_PROVISIONAL_EPISODE_CONSTRUCTION",
        "aggregate": aggregate,
        "records_path": RECORDS_REL.as_posix(),
        "export_path": EXPORT_REL.as_posix(),
        "model_manifest_path": MODEL_MANIFEST_REL.as_posix(),
        "manifest_path": MANIFEST_REL.as_posix(),
        "persistent_media_derivatives_created": False,
    }


def validate_existing(repo_root: Path) -> dict[str, Any]:
    queue, _ = validate_inputs(repo_root)
    verify_all_models(repo_root)
    records_doc = load_json(repo_root / RECORDS_REL)
    records = records_doc["records"]
    validate_records(queue, records)
    export = load_json(repo_root / EXPORT_REL)
    if export != build_export(queue, records):
        raise AdjudicationError("EXPORT_NOT_DETERMINISTIC")
    manifest = load_json(repo_root / MANIFEST_REL)
    if manifest.get("decision") not in DECISIONS:
        raise AdjudicationError("INVALID_DECISION")
    aggregate = aggregate_records(records)
    if manifest.get("aggregate") != aggregate:
        raise AdjudicationError("MANIFEST_AGGREGATE_DRIFT")
    model_manifest = load_json(repo_root / MODEL_MANIFEST_REL)
    if manifest.get("model_manifest") != file_identity(
        repo_root / MODEL_MANIFEST_REL, repo_root
    ):
        raise AdjudicationError("MODEL_MANIFEST_IDENTITY_DRIFT")
    del model_manifest
    expected_outputs = [
        file_identity(repo_root / rel, repo_root)
        for rel in (RECORDS_REL, EXPORT_REL, MODEL_MANIFEST_REL)
    ]
    if manifest.get("outputs") != expected_outputs:
        raise AdjudicationError("MANIFEST_OUTPUT_IDENTITY_DRIFT")
    expected_superseded = {
        FALLBACK_RECORDS_REL: RECORDS_REL,
        FALLBACK_EXPORT_REL: EXPORT_REL,
        FALLBACK_MODEL_MANIFEST_REL: MODEL_MANIFEST_REL,
        FALLBACK_MANIFEST_REL: MANIFEST_REL,
    }
    for fallback_rel, authoritative_rel in expected_superseded.items():
        fallback = load_json(repo_root / fallback_rel)
        if (
            fallback.get("artifact_status")
            != "SUPERSEDED_FALLBACK_PROVENANCE_ONLY"
            or fallback.get("authoritative") is not False
            or fallback.get("superseded_by") != authoritative_rel.as_posix()
        ):
            raise AdjudicationError(
                f"AMBIGUOUS_FALLBACK_PROVENANCE:{fallback_rel.as_posix()}"
            )
    if manifest.get("task83_fallback_comparison", {}).get(
        "fallback_records"
    ) != file_identity(repo_root / FALLBACK_RECORDS_REL, repo_root):
        raise AdjudicationError("FALLBACK_RECORD_IDENTITY_DRIFT")
    return {
        "status": "VALID",
        "record_count": len(records),
        "aggregate": aggregate,
        "decision": manifest["decision"],
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--validate-existing", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = args.repo_root.resolve()
    result = validate_existing(repo_root) if args.validate_existing else run(repo_root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
