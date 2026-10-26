#!/usr/bin/env python3
"""Task193: isolated learned semantic-audio discovery over five kitchen sources.

The build reads only frozen source/timeline manifests, exact source MP4 files,
the frozen Wave-R CLAP acquisition manifest, and the exact local CLAP snapshot.
It never reads EPIC/CaptainCook semantic annotations or candidate registries.
Decoded 8-second waveform windows are in-memory only. Persisted outputs contain
only metadata, numeric statistics, learned vectors, and rankings.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import av
import numpy as np


TASK_DATE = "2026-10-10"
SCHEMA_VERSION = "av-trace.semantic-audio-discovery/1.0"
MODEL_REPO = "laion/clap-htsat-unfused"
MODEL_REVISION = "8fa0f1c6d0433df6e97c127f64b2a1d6c0dcda8a"
MODEL_REL = (
    "data/restricted/scale1b/models/"
    "laion--clap-htsat-unfused--8fa0f1c6d043"
)
MODEL_MANIFEST_REL = "data/restricted/scale1b/manifests/wave_r_model_acquisition.json"
OUTPUT_REL = "data/restricted/semantic_audio_discovery_v1"
SAMPLE_RATE = 48_000
WINDOW_SECONDS = 8
WINDOW_SAMPLES = SAMPLE_RATE * WINDOW_SECONDS

SOURCE_ORDER = ("P27_101", "P28_103", "16_20", "15_29", "26_22")
TIMELINE_MANIFESTS = (
    "data/restricted/epic_wave1_index_v1/segment_manifest.json",
    "data/restricted/captaincook4d_wave0_index_v1/segment_manifest.json",
)

# Frozen before any source audio inference. Each concept has one stable ID and
# three prompt formulations whose normalized text embeddings are mean-pooled.
VOCABULARY: tuple[dict[str, Any], ...] = (
    {
        "concept_id": "running_water",
        "category": "target",
        "label": "running water",
        "prompts": [
            "running water from a kitchen faucet",
            "water flowing into a sink",
            "a kitchen tap running",
        ],
    },
    {
        "concept_id": "chopping",
        "category": "target",
        "label": "chopping with a knife",
        "prompts": [
            "rapid chopping food with a kitchen knife",
            "a knife repeatedly chopping on a cutting board",
            "the sound of chopping vegetables",
        ],
    },
    {
        "concept_id": "peeling_scraping",
        "category": "target",
        "label": "peeling or scraping food",
        "prompts": [
            "scraping while peeling a vegetable",
            "a handheld peeler scraping food",
            "repeated food peeling sounds",
        ],
    },
    {
        "concept_id": "wrapper_tearing",
        "category": "target",
        "label": "wrapper tearing or crinkling",
        "prompts": [
            "tearing open a plastic food wrapper",
            "loud plastic wrapper crinkling",
            "a food package being unwrapped",
        ],
    },
    {
        "concept_id": "plastic_bag_rustling",
        "category": "target",
        "label": "plastic bag rustling",
        "prompts": [
            "a plastic bag rustling in a kitchen",
            "handling a crinkly plastic bag",
            "soft repeated plastic rustling",
        ],
    },
    {
        "concept_id": "container_opening",
        "category": "target",
        "label": "container opening",
        "prompts": [
            "opening a food container",
            "a container lid being opened",
            "removing the lid from a kitchen container",
        ],
    },
    {
        "concept_id": "jar_bottle_opening",
        "category": "target",
        "label": "jar or bottle opening",
        "prompts": [
            "twisting open a jar or bottle",
            "a bottle cap being opened",
            "opening a sealed jar in a kitchen",
        ],
    },
    {
        "concept_id": "can_opening",
        "category": "target",
        "label": "can opening",
        "prompts": [
            "opening a metal food can",
            "a can opener cutting a can lid",
            "the metallic sound of a can being opened",
        ],
    },
    {
        "concept_id": "pouring_liquid",
        "category": "target",
        "label": "pouring liquid",
        "prompts": [
            "pouring liquid into a kitchen container",
            "water or another liquid being poured",
            "a steady liquid pour",
        ],
    },
    {
        "concept_id": "pouring_dry_food",
        "category": "target",
        "label": "pouring dry food",
        "prompts": [
            "pouring dry ingredients into a bowl",
            "small pieces of food being tipped into a pan",
            "dry food rattling while being poured",
        ],
    },
    {
        "concept_id": "sizzling_frying",
        "category": "target",
        "label": "sizzling or frying",
        "prompts": [
            "food sizzling in a frying pan",
            "the sustained sound of frying",
            "hot oil and food sizzling on a stove",
        ],
    },
    {
        "concept_id": "boiling_kettle",
        "category": "target",
        "label": "boiling or electric kettle",
        "prompts": [
            "water boiling in a kitchen",
            "an electric kettle heating water",
            "a kettle boiling and bubbling",
        ],
    },
    {
        "concept_id": "stirring",
        "category": "target",
        "label": "stirring in a bowl or pan",
        "prompts": [
            "stirring food in a bowl or saucepan",
            "a spoon repeatedly stirring a mixture",
            "circular utensil sounds from stirring",
        ],
    },
    {
        "concept_id": "whisking_mixing",
        "category": "target",
        "label": "whisking or vigorous mixing",
        "prompts": [
            "rapid whisking in a kitchen bowl",
            "vigorous mixing with a utensil",
            "a whisk repeatedly striking a bowl",
        ],
    },
    {
        "concept_id": "utensil_impacts",
        "category": "target",
        "label": "utensil or dish impacts",
        "prompts": [
            "metal utensils clinking against dishes",
            "kitchen cutlery and dish impacts",
            "a spoon tapping a bowl or pan",
        ],
    },
    {
        "concept_id": "pot_lid_impacts",
        "category": "target",
        "label": "pot or lid impacts",
        "prompts": [
            "a metal pot lid being set down",
            "pots and pans clattering",
            "a cookware lid striking a counter or pan",
        ],
    },
    {
        "concept_id": "dish_washing",
        "category": "target",
        "label": "washing or rinsing dishes",
        "prompts": [
            "washing dishes under running water",
            "rinsing a utensil in a kitchen sink",
            "water and dishes moving in a sink",
        ],
    },
    {
        "concept_id": "appliance_beep",
        "category": "target",
        "label": "appliance beep",
        "prompts": [
            "a kitchen appliance beeping",
            "a microwave or oven timer beep",
            "short electronic beeps in a kitchen",
        ],
    },
    {
        "concept_id": "microwave_operation",
        "category": "target",
        "label": "microwave operation",
        "prompts": [
            "a microwave oven running",
            "the hum and beep of a microwave",
            "a microwave door and electronic controls",
        ],
    },
    {
        "concept_id": "blender_processor",
        "category": "target",
        "label": "blender or food processor",
        "prompts": [
            "a blender running in a kitchen",
            "an electric food processor operating",
            "a loud kitchen blender motor",
        ],
    },
    {
        "concept_id": "cupboard_door",
        "category": "target",
        "label": "cupboard or cabinet door",
        "prompts": [
            "a kitchen cupboard door opening or closing",
            "opening and shutting a cabinet",
            "a wooden cupboard door impact",
        ],
    },
    {
        "concept_id": "fridge_freezer_door",
        "category": "target",
        "label": "refrigerator or freezer door",
        "prompts": [
            "a refrigerator or freezer door opening",
            "closing a fridge door in a kitchen",
            "the seal and impact of a freezer door",
        ],
    },
    {
        "concept_id": "drawer_open_close",
        "category": "target",
        "label": "drawer opening or closing",
        "prompts": [
            "a kitchen drawer sliding open or shut",
            "cutlery drawer opening",
            "a drawer closing with a small impact",
        ],
    },
    {
        "concept_id": "footsteps",
        "category": "target",
        "label": "footsteps or walking",
        "prompts": [
            "footsteps walking across a kitchen",
            "a person walking indoors",
            "repeated indoor footstep sounds",
        ],
    },
    {
        "concept_id": "spray_bottle",
        "category": "target",
        "label": "spray bottle",
        "prompts": [
            "a hand trigger spray bottle",
            "cleaning liquid being sprayed",
            "repeated short spray bottle bursts",
        ],
    },
    {
        "concept_id": "grating",
        "category": "target",
        "label": "grating food",
        "prompts": [
            "grating food on a kitchen grater",
            "repeated scraping against a metal grater",
            "cheese or vegetables being grated",
        ],
    },
    {
        "concept_id": "egg_cracking",
        "category": "target",
        "label": "cracking an egg",
        "prompts": [
            "cracking an egg into a bowl",
            "an eggshell tapped and broken",
            "the small impact and crack of an egg",
        ],
    },
    {
        "concept_id": "knife_sharpening",
        "category": "target",
        "label": "knife sharpening",
        "prompts": [
            "sharpening a kitchen knife",
            "a knife scraping against a sharpening tool",
            "repeated metallic knife sharpening",
        ],
    },
    {
        "concept_id": "speech",
        "category": "generic",
        "label": "speech or conversation",
        "prompts": [
            "people speaking or conversing",
            "human speech in the foreground",
            "a person talking",
        ],
    },
    {
        "concept_id": "music",
        "category": "generic",
        "label": "music",
        "prompts": [
            "background music",
            "recorded music playing",
            "musical audio",
        ],
    },
    {
        "concept_id": "room_tone",
        "category": "generic",
        "label": "quiet indoor room tone",
        "prompts": [
            "quiet indoor room ambience",
            "steady low-level background room noise",
            "a calm room with no distinct event",
        ],
    },
    {
        "concept_id": "silence",
        "category": "generic",
        "label": "silence",
        "prompts": [
            "silence with almost no sound",
            "a nearly silent audio recording",
            "no audible event",
        ],
    },
    {
        "concept_id": "generic_kitchen",
        "category": "generic",
        "label": "generic kitchen activity",
        "prompts": [
            "ordinary kitchen activity",
            "general cooking noises",
            "mixed background sounds in a kitchen",
        ],
    },
    {
        "concept_id": "handling_noise",
        "category": "generic",
        "label": "microphone or camera handling noise",
        "prompts": [
            "microphone handling and rubbing noise",
            "camera handling bumps",
            "close contact noise on a wearable microphone",
        ],
    },
    {
        "concept_id": "background_hum",
        "category": "generic",
        "label": "steady appliance or ventilation hum",
        "prompts": [
            "steady electrical appliance hum",
            "ventilation or fan background noise",
            "a continuous low mechanical hum",
        ],
    },
    {
        "concept_id": "dog",
        "category": "distractor",
        "label": "dog sounds",
        "prompts": [
            "a dog barking or whining",
            "pet dog sounds",
            "a barking dog",
        ],
    },
    {
        "concept_id": "birds",
        "category": "distractor",
        "label": "bird calls",
        "prompts": [
            "birds chirping",
            "bird calls outdoors",
            "a singing bird",
        ],
    },
    {
        "concept_id": "traffic",
        "category": "distractor",
        "label": "road traffic",
        "prompts": [
            "road traffic and cars",
            "vehicles passing outdoors",
            "urban traffic noise",
        ],
    },
    {
        "concept_id": "rain",
        "category": "distractor",
        "label": "rain",
        "prompts": [
            "rain falling",
            "steady rainfall",
            "rain hitting a roof or window",
        ],
    },
    {
        "concept_id": "wind",
        "category": "distractor",
        "label": "wind noise",
        "prompts": [
            "wind blowing",
            "strong wind noise on a microphone",
            "outdoor gusts of wind",
        ],
    },
    {
        "concept_id": "keyboard",
        "category": "distractor",
        "label": "computer keyboard typing",
        "prompts": [
            "typing on a computer keyboard",
            "computer keys clicking",
            "rapid keyboard typing",
        ],
    },
    {
        "concept_id": "applause",
        "category": "distractor",
        "label": "applause",
        "prompts": [
            "a crowd applauding",
            "people clapping",
            "audience applause",
        ],
    },
    {
        "concept_id": "power_tools",
        "category": "distractor",
        "label": "power tools",
        "prompts": [
            "an electric drill or power tool",
            "construction power tools",
            "a loud motorized tool",
        ],
    },
)


class DiscoveryError(RuntimeError):
    """Fail-closed Task193 error."""


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    payload = _json_bytes(value)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def _atomic_npz(path: Path, **arrays: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("wb") as handle:
        np.savez_compressed(handle, **arrays)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def _normalize(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float32)
    norms = np.linalg.norm(values, axis=-1, keepdims=True)
    return values / np.maximum(norms, 1e-12)


def _self_hashed(value: dict[str, Any], field: str) -> dict[str, Any]:
    result = dict(value)
    result.pop(field, None)
    result[field] = "sha256:" + _sha256_bytes(_json_bytes(result))
    return result


def _vocabulary_document() -> dict[str, Any]:
    return _self_hashed(
        {
            "schema_version": SCHEMA_VERSION,
            "task": 193,
            "frozen_date": TASK_DATE,
            "freeze_boundary": (
                "This complete vocabulary and all prompt formulations are "
                "written before loading source audio or computing any source "
                "audio embedding."
            ),
            "selection_basis": (
                "Prospective concrete sounds expected in kitchens and manual "
                "procedures, plus generic controls and unrelated distractors."
            ),
            "source_semantic_annotations_used": False,
            "model_repo": MODEL_REPO,
            "model_revision": MODEL_REVISION,
            "concept_count": len(VOCABULARY),
            "categories": {
                category: sum(x["category"] == category for x in VOCABULARY)
                for category in ("target", "generic", "distractor")
            },
            "concepts": list(VOCABULARY),
        },
        "vocabulary_hash",
    )


def _source_records(root: Path) -> list[dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for relative in TIMELINE_MANIFESTS:
        manifest_path = root / relative
        manifest = _load(manifest_path)
        if manifest.get("time_unit") != "integer_microseconds":
            raise DiscoveryError(f"TIMELINE_TIME_UNIT_INVALID:{relative}")
        for source in manifest.get("sources", []):
            source_ref = source.get("source_ref")
            if source_ref not in SOURCE_ORDER:
                continue
            fine = [
                segment
                for segment in manifest.get("segments", [])
                if segment.get("source_ref") == source_ref
                and segment.get("scale") == "fine"
            ]
            fine.sort(key=lambda x: (int(x["start_us"]), str(x["segment_id"])))
            if not fine:
                raise DiscoveryError(f"FINE_WINDOWS_MISSING:{source_ref}")
            expected_starts = list(range(0, len(fine) * 4_000_000, 4_000_000))
            actual_starts = [int(x["start_us"]) for x in fine]
            if actual_starts != expected_starts:
                raise DiscoveryError(f"FINE_LATTICE_INVALID:{source_ref}")
            found[source_ref] = {
                "source_ref": source_ref,
                "source_sha256": source["sha256"],
                "size_bytes": int(source["size_bytes"]),
                "duration_us": int(source["duration_us"]),
                "media_path": source["media_path"],
                "timeline_manifest_path": relative,
                "timeline_manifest_sha256": _sha256_file(manifest_path),
                "segment_manifest_hash": manifest["segment_manifest_hash"],
                "fine_windows": fine,
            }
    if set(found) != set(SOURCE_ORDER):
        raise DiscoveryError(
            "SOURCE_SET_MISMATCH:"
            + ",".join(sorted(set(SOURCE_ORDER).symmetric_difference(found)))
        )
    return [found[source_ref] for source_ref in SOURCE_ORDER]


def _verify_model(root: Path) -> tuple[Path, dict[str, Any]]:
    manifest_path = root / MODEL_MANIFEST_REL
    manifest = _load(manifest_path)
    clap = manifest.get("models", {}).get("clap", {})
    if (
        manifest.get("clap_decision") != "CLAP_SNAPSHOT_READY"
        or manifest.get("technical_internal_use_authorized") is not True
        or clap.get("repo_id") != MODEL_REPO
        or clap.get("revision") != MODEL_REVISION
    ):
        raise DiscoveryError("EXACT_CLAP_GATE_NOT_READY")
    model_path = root / MODEL_REL
    if not model_path.is_dir() or model_path.is_symlink():
        raise DiscoveryError("EXACT_CLAP_SNAPSHOT_MISSING")
    expected = {item["path"]: item for item in clap.get("files", [])}
    actual = {
        item.relative_to(model_path).as_posix()
        for item in model_path.iterdir()
        if item.is_file() and item.name != "SHA256SUMS"
    }
    if actual != set(expected):
        raise DiscoveryError("EXACT_CLAP_FILE_INVENTORY_MISMATCH")
    file_checks: list[dict[str, Any]] = []
    for relative, record in sorted(expected.items()):
        path = model_path / relative
        size = path.stat().st_size
        digest = _sha256_file(path)
        if size != int(record["bytes"]) or digest != record["sha256"]:
            raise DiscoveryError(f"EXACT_CLAP_FILE_MISMATCH:{relative}")
        file_checks.append({"path": relative, "bytes": size, "sha256": digest})
    return model_path, {
        "manifest_path": MODEL_MANIFEST_REL,
        "manifest_sha256": _sha256_file(manifest_path),
        "repo_id": MODEL_REPO,
        "revision": MODEL_REVISION,
        "snapshot_path": MODEL_REL,
        "files": file_checks,
        "redistribution_authorized": bool(manifest.get("redistribution_authorized")),
        "technical_internal_use_authorized": True,
    }


def _decode_audio(path: Path, rate: int = SAMPLE_RATE) -> np.ndarray:
    parts: list[np.ndarray] = []
    with av.open(str(path), mode="r") as container:
        stream = next((stream for stream in container.streams if stream.type == "audio"), None)
        if stream is None:
            raise DiscoveryError(f"AUDIO_STREAM_MISSING:{path.name}")
        resampler = av.audio.resampler.AudioResampler(
            format="fltp", layout="mono", rate=rate
        )
        for frame in container.decode(stream):
            for converted in resampler.resample(frame):
                parts.append(converted.to_ndarray().reshape(-1).astype(np.float32))
        for converted in resampler.resample(None):
            parts.append(converted.to_ndarray().reshape(-1).astype(np.float32))
    if not parts:
        raise DiscoveryError(f"AUDIO_DECODE_EMPTY:{path.name}")
    values = np.concatenate(parts)
    if not np.isfinite(values).all():
        raise DiscoveryError(f"AUDIO_DECODE_NONFINITE:{path.name}")
    return values


def _window(values: np.ndarray, start_us: int) -> tuple[np.ndarray, int]:
    left = max(0, round(start_us * SAMPLE_RATE / 1_000_000))
    right = min(len(values), left + WINDOW_SAMPLES)
    available = max(0, right - left)
    result = values[left:right]
    if len(result) < WINDOW_SAMPLES:
        result = np.pad(result, (0, WINDOW_SAMPLES - len(result)))
    return result.astype(np.float32, copy=False), available


def _spectral_statistics(values: np.ndarray, available: int) -> dict[str, Any]:
    if available <= 0:
        return {
            "rms_dbfs": -120.0,
            "peak_dbfs": -120.0,
            "crest_factor_db": 0.0,
            "zero_crossing_rate": 0.0,
            "silence_fraction": 1.0,
            "frame_rms_p10_dbfs": -120.0,
            "frame_rms_p50_dbfs": -120.0,
            "frame_rms_p90_dbfs": -120.0,
            "transient_index": 0.0,
            "spectral_centroid_hz": 0.0,
            "spectral_flatness": 0.0,
            "low_band_fraction": 0.0,
            "mid_band_fraction": 0.0,
            "high_band_fraction": 0.0,
        }
    audio = np.asarray(values[:available], dtype=np.float32)
    eps = 1e-12
    rms = float(np.sqrt(np.mean(np.square(audio), dtype=np.float64)))
    peak = float(np.max(np.abs(audio)))
    zero_crossing = float(np.mean(np.signbit(audio[1:]) != np.signbit(audio[:-1])))

    # Downsample exactly by 3 from 48 kHz to 16 kHz for bounded statistics.
    down = audio[::3]
    frame_length = 1600  # 100 ms
    hop = 800  # 50 ms
    frame_rms: list[float] = []
    power_accumulator: np.ndarray | None = None
    if len(down) < frame_length:
        down = np.pad(down, (0, frame_length - len(down)))
    window = np.hanning(frame_length).astype(np.float32)
    for offset in range(0, max(1, len(down) - frame_length + 1), hop):
        frame = down[offset : offset + frame_length]
        if len(frame) < frame_length:
            frame = np.pad(frame, (0, frame_length - len(frame)))
        frame_rms.append(float(np.sqrt(np.mean(np.square(frame), dtype=np.float64))))
        spectrum = np.fft.rfft(frame * window)
        power = np.square(np.abs(spectrum), dtype=np.float64)
        power_accumulator = power if power_accumulator is None else power_accumulator + power
    frame_rms_array = np.asarray(frame_rms, dtype=np.float64)
    rms_db = 20.0 * math.log10(max(rms, eps))
    peak_db = 20.0 * math.log10(max(peak, eps))
    frame_db = 20.0 * np.log10(np.maximum(frame_rms_array, eps))
    differences = np.abs(np.diff(frame_rms_array))
    transient_index = float(
        np.percentile(differences, 95)
        / max(float(np.median(frame_rms_array)), eps)
    ) if len(differences) else 0.0
    silence_threshold = max(10 ** (-55.0 / 20.0), rms * 0.08)
    silence_fraction = float(np.mean(frame_rms_array < silence_threshold))

    assert power_accumulator is not None
    power = power_accumulator / max(1, len(frame_rms))
    frequencies = np.fft.rfftfreq(frame_length, d=1 / 16_000)
    total_power = float(np.sum(power)) + eps
    centroid = float(np.sum(frequencies * power) / total_power)
    flatness = float(
        np.exp(np.mean(np.log(power + eps))) / (np.mean(power + eps))
    )

    def band_fraction(low: float, high: float) -> float:
        mask = (frequencies >= low) & (frequencies < high)
        return float(np.sum(power[mask]) / total_power)

    return {
        "rms_dbfs": round(rms_db, 6),
        "peak_dbfs": round(peak_db, 6),
        "crest_factor_db": round(peak_db - rms_db, 6),
        "zero_crossing_rate": round(zero_crossing, 8),
        "silence_fraction": round(silence_fraction, 8),
        "frame_rms_p10_dbfs": round(float(np.percentile(frame_db, 10)), 6),
        "frame_rms_p50_dbfs": round(float(np.percentile(frame_db, 50)), 6),
        "frame_rms_p90_dbfs": round(float(np.percentile(frame_db, 90)), 6),
        "transient_index": round(transient_index, 8),
        "spectral_centroid_hz": round(centroid, 6),
        "spectral_flatness": round(flatness, 8),
        "low_band_fraction": round(band_fraction(0, 500), 8),
        "mid_band_fraction": round(band_fraction(500, 3000), 8),
        "high_band_fraction": round(band_fraction(3000, 8001), 8),
    }


class ClapRuntime:
    def __init__(self, model_path: Path, threads: int):
        if "long" not in np.__dict__:
            np.long = np.int64  # type: ignore[attr-defined]
        if "ulong" not in np.__dict__:
            np.ulong = np.uint64  # type: ignore[attr-defined]
        os.environ.update(
            {
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
                "HF_DATASETS_OFFLINE": "1",
                "HF_HUB_DISABLE_TELEMETRY": "1",
                "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1",
                "TOKENIZERS_PARALLELISM": "false",
            }
        )
        import torch
        from transformers import ClapModel, ClapProcessor

        torch.manual_seed(0)
        torch.use_deterministic_algorithms(True)
        torch.set_num_threads(max(1, threads))
        self.torch = torch
        self.processor = ClapProcessor.from_pretrained(
            model_path, local_files_only=True
        )
        self.model = ClapModel.from_pretrained(
            model_path, local_files_only=True
        ).eval()

    def audio(self, waveforms: Sequence[np.ndarray]) -> np.ndarray:
        inputs = self.processor(
            audio=list(waveforms),
            sampling_rate=SAMPLE_RATE,
            padding=True,
            return_tensors="pt",
        )
        kwargs: dict[str, Any] = {"input_features": inputs.input_features}
        for name in ("is_longer", "attention_mask"):
            value = getattr(inputs, name, None)
            if value is not None:
                kwargs[name] = value
        with self.torch.inference_mode():
            values = self.model.get_audio_features(**kwargs)
        if hasattr(values, "pooler_output"):
            values = values.pooler_output
        return _normalize(values.float().cpu().numpy())

    def text(self, texts: Sequence[str]) -> np.ndarray:
        inputs = self.processor(
            text=list(texts), padding=True, truncation=True, return_tensors="pt"
        )
        kwargs: dict[str, Any] = {"input_ids": inputs.input_ids}
        attention_mask = getattr(inputs, "attention_mask", None)
        if attention_mask is not None:
            kwargs["attention_mask"] = attention_mask
        with self.torch.inference_mode():
            values = self.model.get_text_features(**kwargs)
        if hasattr(values, "pooler_output"):
            values = values.pooler_output
        return _normalize(values.float().cpu().numpy())


def _chunks(values: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for offset in range(0, len(values), size):
        yield values[offset : offset + size]


def _text_embeddings(
    runtime: ClapRuntime, vocabulary: Sequence[Mapping[str, Any]]
) -> np.ndarray:
    flattened: list[str] = []
    spans: list[tuple[int, int]] = []
    for concept in vocabulary:
        start = len(flattened)
        flattened.extend(str(item) for item in concept["prompts"])
        spans.append((start, len(flattened)))
    prompt_vectors = runtime.text(flattened)
    pooled = [
        _normalize(np.mean(prompt_vectors[start:end], axis=0, keepdims=True))[0]
        for start, end in spans
    ]
    return np.stack(pooled).astype(np.float32)


def _round_score(value: float) -> float:
    return round(float(value), 8)


def _build_rankings(
    windows: list[dict[str, Any]],
    embeddings: np.ndarray,
    text_embeddings: np.ndarray,
    vocabulary: Sequence[Mapping[str, Any]],
    top_k: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    scores = np.matmul(embeddings.astype(np.float32), text_embeddings.T)
    source_indices = {
        source_ref: np.asarray(
            [index for index, item in enumerate(windows) if item["source_ref"] == source_ref],
            dtype=np.int64,
        )
        for source_ref in SOURCE_ORDER
    }
    generic_columns = np.asarray(
        [
            index
            for index, concept in enumerate(vocabulary)
            if concept["category"] == "generic"
        ],
        dtype=np.int64,
    )
    distractor_columns = np.asarray(
        [
            index
            for index, concept in enumerate(vocabulary)
            if concept["category"] == "distractor"
        ],
        dtype=np.int64,
    )

    enriched: list[dict[str, Any]] = []
    for row_index, window in enumerate(windows):
        row = scores[row_index]
        target_order = sorted(
            (
                index
                for index, concept in enumerate(vocabulary)
                if concept["category"] == "target"
            ),
            key=lambda index: (-float(row[index]), str(vocabulary[index]["concept_id"])),
        )
        item = dict(window)
        item["top_target_concepts"] = [
            {
                "concept_id": vocabulary[index]["concept_id"],
                "label": vocabulary[index]["label"],
                "similarity": _round_score(row[index]),
            }
            for index in target_order[:5]
        ]
        item["generic_max_similarity"] = _round_score(np.max(row[generic_columns]))
        item["distractor_max_similarity"] = _round_score(
            np.max(row[distractor_columns])
        )
        item["top_target_margin_over_generic"] = _round_score(
            row[target_order[0]] - np.max(row[generic_columns])
        )
        enriched.append(item)

    concept_rankings: list[dict[str, Any]] = []
    for column, concept in enumerate(vocabulary):
        per_source: dict[str, list[dict[str, Any]]] = {}
        for source_ref, indices in source_indices.items():
            local = scores[indices, column]
            mean = float(np.mean(local))
            standard_deviation = max(float(np.std(local)), 1e-8)
            ranked = sorted(
                (
                    (
                        float(local[position]),
                        int(indices[position]),
                        (float(local[position]) - mean) / standard_deviation,
                    )
                    for position in range(len(indices))
                ),
                key=lambda item: (-item[0], windows[item[1]]["start_us"]),
            )
            records: list[dict[str, Any]] = []
            for rank, (score, global_index, z_score) in enumerate(
                ranked[:top_k], start=1
            ):
                row = scores[global_index]
                generic_max = float(np.max(row[generic_columns]))
                records.append(
                    {
                        "rank": rank,
                        "window_id": windows[global_index]["window_id"],
                        "segment_id": windows[global_index]["segment_id"],
                        "start_s": windows[global_index]["start_us"] / 1_000_000,
                        "end_s": windows[global_index]["end_us"] / 1_000_000,
                        "similarity": _round_score(score),
                        "source_z_score": round(float(z_score), 6),
                        "margin_over_generic_max": _round_score(score - generic_max),
                        "rms_dbfs": windows[global_index]["statistics"]["rms_dbfs"],
                        "spectral_centroid_hz": windows[global_index]["statistics"][
                            "spectral_centroid_hz"
                        ],
                        "transient_index": windows[global_index]["statistics"][
                            "transient_index"
                        ],
                    }
                )
            per_source[source_ref] = records
        global_order = sorted(
            range(len(windows)),
            key=lambda index: (-float(scores[index, column]), windows[index]["window_id"]),
        )
        concept_rankings.append(
            {
                "concept_id": concept["concept_id"],
                "category": concept["category"],
                "label": concept["label"],
                "per_source_top": per_source,
                "global_top": [
                    {
                        "rank": rank,
                        "source_ref": windows[index]["source_ref"],
                        "window_id": windows[index]["window_id"],
                        "segment_id": windows[index]["segment_id"],
                        "start_s": windows[index]["start_us"] / 1_000_000,
                        "end_s": windows[index]["end_us"] / 1_000_000,
                        "similarity": _round_score(scores[index, column]),
                    }
                    for rank, index in enumerate(global_order[:top_k], start=1)
                ],
            }
        )
    rankings = _self_hashed(
        {
            "schema_version": SCHEMA_VERSION,
            "task": 193,
            "created_date": TASK_DATE,
            "scoring": {
                "audio_vectors": "float32 L2-normalized for scoring",
                "text_vectors": (
                    "mean of three individually normalized prompt vectors, "
                    "then L2-normalized"
                ),
                "similarity": "cosine via float32 dot product",
                "scope": "source-scoped primary plus global diagnostic",
                "top_k": top_k,
                "source_z_score": "within-source, within-concept descriptive z score",
                "margin_over_generic_max": (
                    "concept similarity minus maximum generic-label similarity "
                    "for the same window"
                ),
                "threshold_selected_from_semantic_annotations": False,
            },
            "concept_rankings": concept_rankings,
        },
        "rankings_hash",
    )
    return rankings, enriched


def _scan_persisted_media_derivatives(output: Path) -> list[str]:
    forbidden = {
        ".wav",
        ".flac",
        ".mp3",
        ".m4a",
        ".aac",
        ".ogg",
        ".mp4",
        ".mov",
        ".avi",
        ".mkv",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
    }
    return sorted(
        path.relative_to(output).as_posix()
        for path in output.rglob("*")
        if path.is_file() and path.suffix.lower() in forbidden
    )


def build(
    repo_root: Path,
    *,
    threads: int,
    batch_size: int,
    top_k: int,
    verify_source_hashes: bool,
) -> dict[str, Any]:
    started = time.perf_counter()
    root = repo_root.resolve()
    output = root / OUTPUT_REL
    output.mkdir(parents=True, exist_ok=True)
    os.chmod(output, 0o700)

    # Prospective declaration is materially written before model load and before
    # any source waveform is decoded.
    vocabulary_document = _vocabulary_document()
    vocabulary_path = output / "vocabulary.json"
    _atomic_json(vocabulary_path, vocabulary_document)
    vocabulary_frozen_at = time.time()

    model_path, model_binding = _verify_model(root)
    sources = _source_records(root)
    source_bindings: list[dict[str, Any]] = []
    for source in sources:
        media = root / source["media_path"]
        if not media.is_file() or media.is_symlink():
            raise DiscoveryError(f"SOURCE_MEDIA_MISSING:{source['source_ref']}")
        actual_size = media.stat().st_size
        if actual_size != source["size_bytes"]:
            raise DiscoveryError(f"SOURCE_SIZE_MISMATCH:{source['source_ref']}")
        actual_hash = (
            _sha256_file(media) if verify_source_hashes else source["source_sha256"]
        )
        if actual_hash != source["source_sha256"]:
            raise DiscoveryError(f"SOURCE_HASH_MISMATCH:{source['source_ref']}")
        source_bindings.append(
            {
                key: source[key]
                for key in (
                    "source_ref",
                    "source_sha256",
                    "size_bytes",
                    "duration_us",
                    "media_path",
                    "timeline_manifest_path",
                    "timeline_manifest_sha256",
                    "segment_manifest_hash",
                )
            }
            | {
                "fine_window_count": len(source["fine_windows"]),
                "source_sha256_recomputed": verify_source_hashes,
            }
        )

    runtime = ClapRuntime(model_path, threads=threads)
    text_vectors = _text_embeddings(runtime, VOCABULARY)
    if text_vectors.shape != (len(VOCABULARY), 512):
        raise DiscoveryError(f"TEXT_VECTOR_SHAPE_INVALID:{text_vectors.shape}")

    windows: list[dict[str, Any]] = []
    source_embedding_arrays: dict[str, np.ndarray] = {}
    source_elapsed: dict[str, float] = {}
    temporary_root_path: str | None = None
    cleanup_verified = False
    with tempfile.TemporaryDirectory(prefix="task193-semantic-audio-", dir="/tmp") as temporary:
        temporary_root_path = temporary
        if list(Path(temporary).iterdir()):
            raise DiscoveryError("TEMPORARY_DIRECTORY_NOT_EMPTY_AT_START")
        for source in sources:
            source_started = time.perf_counter()
            media = root / source["media_path"]
            waveform = _decode_audio(media, SAMPLE_RATE)
            source_duration_samples = round(
                source["duration_us"] * SAMPLE_RATE / 1_000_000
            )
            duration_delta = len(waveform) - source_duration_samples
            source_windows: list[np.ndarray] = []
            source_records: list[dict[str, Any]] = []
            for segment in source["fine_windows"]:
                window, available = _window(waveform, int(segment["start_us"]))
                source_windows.append(window)
                source_records.append(
                    {
                        "window_id": (
                            f"audio.{source['source_ref']}."
                            f"{int(segment['lattice_index']):06d}"
                        ),
                        "source_ref": source["source_ref"],
                        "source_sha256": source["source_sha256"],
                        "segment_id": segment["segment_id"],
                        "lattice_index": int(segment["lattice_index"]),
                        "start_us": int(segment["start_us"]),
                        "end_us": min(
                            int(segment["start_us"]) + WINDOW_SECONDS * 1_000_000,
                            source["duration_us"],
                        ),
                        "requested_duration_s": WINDOW_SECONDS,
                        "available_audio_samples": available,
                        "zero_padding_samples": WINDOW_SAMPLES - available,
                        "statistics": _spectral_statistics(window, available),
                    }
                )
            embedded_batches: list[np.ndarray] = []
            for batch in _chunks(source_windows, batch_size):
                embedded_batches.append(runtime.audio(batch))
            source_vectors = np.concatenate(embedded_batches, axis=0)
            if source_vectors.shape != (len(source_windows), 512):
                raise DiscoveryError(
                    f"AUDIO_VECTOR_SHAPE_INVALID:{source['source_ref']}:"
                    f"{source_vectors.shape}"
                )
            if not np.isfinite(source_vectors).all():
                raise DiscoveryError(f"AUDIO_VECTOR_NONFINITE:{source['source_ref']}")
            norms = np.linalg.norm(source_vectors, axis=1)
            if float(np.max(np.abs(norms - 1.0))) > 1e-4:
                raise DiscoveryError(f"AUDIO_VECTOR_NOT_NORMALIZED:{source['source_ref']}")
            for record in source_records:
                record["decoded_source_samples"] = len(waveform)
                record["duration_sample_delta"] = duration_delta
            source_embedding_arrays[source["source_ref"]] = source_vectors.astype(
                np.float16
            )
            windows.extend(source_records)
            source_elapsed[source["source_ref"]] = round(
                time.perf_counter() - source_started, 6
            )
            del waveform, source_windows, source_vectors, embedded_batches
        if list(Path(temporary).iterdir()):
            raise DiscoveryError("TEMPORARY_MEDIA_WAS_WRITTEN")
    cleanup_verified = bool(
        temporary_root_path is not None and not Path(temporary_root_path).exists()
    )

    embeddings = np.concatenate(
        [source_embedding_arrays[source_ref].astype(np.float32) for source_ref in SOURCE_ORDER],
        axis=0,
    )
    # Re-normalize after float16 round-trip so persisted-vector ranking replay is exact.
    embeddings = _normalize(embeddings)
    rankings, enriched_windows = _build_rankings(
        windows, embeddings, text_vectors, VOCABULARY, top_k
    )

    source_document = _self_hashed(
        {
            "schema_version": SCHEMA_VERSION,
            "task": 193,
            "created_date": TASK_DATE,
            "source_order": list(SOURCE_ORDER),
            "sources": source_bindings,
            "totals": {
                "sources": len(source_bindings),
                "duration_seconds": round(
                    sum(x["duration_us"] for x in source_bindings) / 1_000_000, 6
                ),
                "eight_second_windows": len(windows),
            },
            "semantic_annotation_inputs": [],
            "input_allowlist": [
                *TIMELINE_MANIFESTS,
                MODEL_MANIFEST_REL,
                MODEL_REL + "/*",
                *[item["media_path"] for item in source_bindings],
            ],
        },
        "source_bindings_hash",
    )
    window_document = _self_hashed(
        {
            "schema_version": SCHEMA_VERSION,
            "task": 193,
            "windowing": {
                "duration_seconds": WINDOW_SECONDS,
                "stride_seconds": 4,
                "sample_rate_hz": SAMPLE_RATE,
                "terminal_policy": "zero-pad to exactly 8 seconds",
                "decode": "PyAV source decode to mono float32; windows in memory only",
            },
            "window_count": len(enriched_windows),
            "windows": enriched_windows,
        },
        "window_index_hash",
    )

    _atomic_json(output / "source_bindings.json", source_document)
    _atomic_json(output / "window_index.json", window_document)
    _atomic_json(output / "rankings.json", rankings)
    _atomic_npz(
        output / "clap_embeddings.npz",
        audio_embeddings_f16=np.concatenate(
            [source_embedding_arrays[source_ref] for source_ref in SOURCE_ORDER],
            axis=0,
        ),
        text_embeddings_f16=text_vectors.astype(np.float16),
        source_offsets=np.asarray(
            [
                sum(
                    len(source_embedding_arrays[earlier])
                    for earlier in SOURCE_ORDER[:index]
                )
                for index in range(len(SOURCE_ORDER) + 1)
            ],
            dtype=np.int64,
        ),
    )

    media_derivatives = _scan_persisted_media_derivatives(output)
    if media_derivatives:
        raise DiscoveryError("PERSISTED_MEDIA_DERIVATIVE:" + ",".join(media_derivatives))
    import torch
    import transformers

    manifest = _self_hashed(
        {
            "schema_version": SCHEMA_VERSION,
            "task": 193,
            "created_date": TASK_DATE,
            "status": "CLAP_FULL_TIMELINE_DISCOVERY_COMPLETE",
            "model": model_binding,
            "vocabulary_path": f"{OUTPUT_REL}/vocabulary.json",
            "vocabulary_hash": vocabulary_document["vocabulary_hash"],
            "vocabulary_frozen_before_source_inference": True,
            "vocabulary_file_mtime_epoch": vocabulary_frozen_at,
            "source_bindings_path": f"{OUTPUT_REL}/source_bindings.json",
            "window_index_path": f"{OUTPUT_REL}/window_index.json",
            "rankings_path": f"{OUTPUT_REL}/rankings.json",
            "embeddings_path": f"{OUTPUT_REL}/clap_embeddings.npz",
            "counts": {
                "sources": len(SOURCE_ORDER),
                "windows": len(windows),
                "audio_embedding_dimension": 512,
                "text_concepts": len(VOCABULARY),
                "target_concepts": sum(x["category"] == "target" for x in VOCABULARY),
                "generic_concepts": sum(x["category"] == "generic" for x in VOCABULARY),
                "distractor_concepts": sum(
                    x["category"] == "distractor" for x in VOCABULARY
                ),
            },
            "runtime": {
                "python": platform.python_version(),
                "numpy": np.__version__,
                "pyav": av.__version__,
                "torch": torch.__version__,
                "transformers": transformers.__version__,
                "device": "cpu",
                "threads": threads,
                "batch_size": batch_size,
                "source_elapsed_seconds": source_elapsed,
                "total_elapsed_seconds": round(time.perf_counter() - started, 6),
            },
            "isolation": {
                "network_used": False,
                "local_files_only": True,
                "source_semantic_annotations_used": False,
                "epic_semantic_annotations_used": False,
                "captaincook_semantic_annotations_used": False,
                "questions_answers_or_candidate_labels_used_for_retrieval": False,
            },
            "media_derivative_policy": {
                "audio_windows": "in-memory numpy arrays only",
                "temporary_directory": temporary_root_path,
                "temporary_directory_cleanup_verified": cleanup_verified,
                "persisted_audio_clips": 0,
                "persisted_frames": 0,
                "persisted_spectrogram_images": 0,
                "persisted_media_derivative_scan": media_derivatives,
            },
            "artifact_hashes": {
                "vocabulary.json": _sha256_file(output / "vocabulary.json"),
                "source_bindings.json": _sha256_file(output / "source_bindings.json"),
                "window_index.json": _sha256_file(output / "window_index.json"),
                "rankings.json": _sha256_file(output / "rankings.json"),
                "clap_embeddings.npz": _sha256_file(output / "clap_embeddings.npz"),
            },
            "implementation": {
                "path": "scripts/build_semantic_audio_discovery_v1.py",
                "sha256": _sha256_file(
                    root / "scripts/build_semantic_audio_discovery_v1.py"
                ),
            },
            "boundary": {
                "learned_retrieval_not_semantic_gold": True,
                "human_listening_performed": False,
                "machine_expert_review_required_before_audio_facts": True,
                "h_tiers_assigned": False,
                "necessity_claimed": False,
            },
        },
        "build_manifest_hash",
    )
    _atomic_json(output / "build_manifest.json", manifest)

    for path in output.rglob("*"):
        if path.is_dir():
            os.chmod(path, 0o700)
        elif path.is_file():
            os.chmod(path, 0o600)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--top-k", type=int, default=15)
    parser.add_argument(
        "--skip-source-hashes",
        action="store_true",
        help="Trust source hashes already bound by the frozen timeline manifests.",
    )
    args = parser.parse_args()
    result = build(
        Path(args.repo_root),
        threads=args.threads,
        batch_size=args.batch_size,
        top_k=args.top_k,
        verify_source_hashes=not args.skip_source_hashes,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
