#!/usr/bin/env python3
"""Create bounded machine-review packets for Task193 top audio candidates.

No media derivative is written. Waveform/spectral descriptors and sampled-frame
descriptors are persisted as numeric/text metadata only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping

import av
import numpy as np


SCHEMA_VERSION = "av-trace.semantic-audio-discovery/1.0"
TASK_DATE = "2026-10-10"
DISCOVERY_REL = "data/restricted/semantic_audio_discovery_v1"
SAMPLE_RATE = 48_000

# Declared after retrieval but before direct bounded decode. These are review
# candidates selected solely from source-scoped CLAP ranks, score margins,
# recurrence structure, and coverage of requested event classes.
REVIEW_INTERVALS: tuple[dict[str, Any], ...] = (
    {
        "review_id": "sad193.p27.wrapper.1292",
        "source_ref": "P27_101",
        "start_s": 1288.0,
        "end_s": 1304.0,
        "retrieval_concepts": ["wrapper_tearing", "plastic_bag_rustling"],
        "selection_reason": "exceptional isolated wrapper cluster; source ranks 1-3",
    },
    {
        "review_id": "sad193.p27.chop.1220",
        "source_ref": "P27_101",
        "start_s": 1216.0,
        "end_s": 1232.0,
        "retrieval_concepts": ["chopping"],
        "selection_reason": "source rank 1 chopping; high transient index",
    },
    {
        "review_id": "sad193.p27.sizzle.388",
        "source_ref": "P27_101",
        "start_s": 384.0,
        "end_s": 420.0,
        "retrieval_concepts": ["sizzling_frying", "stirring"],
        "selection_reason": "strong sustained cooking cluster across overlapping windows",
    },
    {
        "review_id": "sad193.p27.door.1264",
        "source_ref": "P27_101",
        "start_s": 1256.0,
        "end_s": 1272.0,
        "retrieval_concepts": ["cupboard_door"],
        "selection_reason": "top cupboard cluster and recurrent candidate region",
    },
    {
        "review_id": "sad193.p28.peel.216",
        "source_ref": "P28_103",
        "start_s": 196.0,
        "end_s": 232.0,
        "retrieval_concepts": ["peeling_scraping", "grating"],
        "selection_reason": "prospective scraping/peeling route near top grating rank",
    },
    {
        "review_id": "sad193.p28.chop.1120",
        "source_ref": "P28_103",
        "start_s": 1112.0,
        "end_s": 1136.0,
        "retrieval_concepts": ["chopping"],
        "selection_reason": "source ranks 1-3 chopping cluster",
    },
    {
        "review_id": "sad193.p28.addstir.980",
        "source_ref": "P28_103",
        "start_s": 936.0,
        "end_s": 996.0,
        "retrieval_concepts": [
            "pouring_dry_food",
            "stirring",
            "utensil_impacts",
            "pot_lid_impacts",
        ],
        "selection_reason": "coincident dry-pour/stir/impact retrieval cluster",
    },
    {
        "review_id": "sad193.p28.sizzle.1416",
        "source_ref": "P28_103",
        "start_s": 1408.0,
        "end_s": 1448.0,
        "retrieval_concepts": ["sizzling_frying"],
        "selection_reason": "top sustained sizzle cluster and known AST false-positive risk",
    },
    {
        "review_id": "sad193.p28.water.260",
        "source_ref": "P28_103",
        "start_s": 252.0,
        "end_s": 272.0,
        "retrieval_concepts": ["running_water", "dish_washing"],
        "selection_reason": "top running-water route with strong generic margin",
    },
    {
        "review_id": "sad193.cc16.water.92",
        "source_ref": "16_20",
        "start_s": 84.0,
        "end_s": 108.0,
        "retrieval_concepts": ["running_water", "dish_washing"],
        "selection_reason": "source rank 1 running water and top dish-washing cluster",
    },
    {
        "review_id": "sad193.cc16.stir.588",
        "source_ref": "16_20",
        "start_s": 576.0,
        "end_s": 612.0,
        "retrieval_concepts": [
            "stirring",
            "whisking_mixing",
            "utensil_impacts",
            "pouring_dry_food",
        ],
        "selection_reason": "dominant isolated stir/mix/utensil cluster",
    },
    {
        "review_id": "sad193.cc16.chop.512",
        "source_ref": "16_20",
        "start_s": 504.0,
        "end_s": 524.0,
        "retrieval_concepts": ["chopping"],
        "selection_reason": "source rank 2 chopping and very high transient index",
    },
    {
        "review_id": "sad193.cc16.chopstir.1092",
        "source_ref": "16_20",
        "start_s": 1088.0,
        "end_s": 1108.0,
        "retrieval_concepts": ["chopping", "grating", "stirring"],
        "selection_reason": "retrieval cluster overlapping onion-pan candidate",
    },
    {
        "review_id": "sad193.cc16.beep.676",
        "source_ref": "16_20",
        "start_s": 668.0,
        "end_s": 752.0,
        "retrieval_concepts": ["appliance_beep"],
        "selection_reason": "three separated source-top beep clusters in one prep span",
    },
    {
        "review_id": "sad193.cc16.blender.1372",
        "source_ref": "16_20",
        "start_s": 1364.0,
        "end_s": 1396.0,
        "retrieval_concepts": ["blender_processor"],
        "selection_reason": "sustained high blender similarity and generic margin",
    },
    {
        "review_id": "sad193.cc15.water.664",
        "source_ref": "15_29",
        "start_s": 656.0,
        "end_s": 676.0,
        "retrieval_concepts": ["running_water", "dish_washing"],
        "selection_reason": "source rank 1 water near tomato-board sequence",
    },
    {
        "review_id": "sad193.cc15.chop.888",
        "source_ref": "15_29",
        "start_s": 880.0,
        "end_s": 900.0,
        "retrieval_concepts": ["chopping", "grating", "peeling_scraping"],
        "selection_reason": "source rank 1 chopping and grating",
    },
    {
        "review_id": "sad193.cc15.blender.836",
        "source_ref": "15_29",
        "start_s": 828.0,
        "end_s": 880.0,
        "retrieval_concepts": ["blender_processor"],
        "selection_reason": "very high sustained motor cluster and generic margin",
    },
    {
        "review_id": "sad193.cc15.microwave.700",
        "source_ref": "15_29",
        "start_s": 684.0,
        "end_s": 712.0,
        "retrieval_concepts": ["microwave_operation", "appliance_beep"],
        "selection_reason": "source-top microwave cluster; beep ambiguity check",
    },
    {
        "review_id": "sad193.cc26.water.456",
        "source_ref": "26_22",
        "start_s": 452.0,
        "end_s": 472.0,
        "retrieval_concepts": ["running_water", "dish_washing", "pouring_liquid"],
        "selection_reason": "source-top water cluster overlapping red-spoon rinse",
    },
    {
        "review_id": "sad193.cc26.microwave.916",
        "source_ref": "26_22",
        "start_s": 908.0,
        "end_s": 932.0,
        "retrieval_concepts": ["microwave_operation", "appliance_beep"],
        "selection_reason": "source-top microwave operation around open/retrieve/stir event",
    },
    {
        "review_id": "sad193.cc26.beep.856",
        "source_ref": "26_22",
        "start_s": 848.0,
        "end_s": 868.0,
        "retrieval_concepts": ["appliance_beep", "microwave_operation"],
        "selection_reason": "source-top beep/microwave precursor cluster",
    },
    {
        "review_id": "sad193.cc26.stir.720",
        "source_ref": "26_22",
        "start_s": 704.0,
        "end_s": 736.0,
        "retrieval_concepts": ["stirring", "sizzling_frying"],
        "selection_reason": "source-top stirring/sizzle overlap",
    },
    {
        "review_id": "sad193.cc26.wrapper.1224",
        "source_ref": "26_22",
        "start_s": 1216.0,
        "end_s": 1240.0,
        "retrieval_concepts": ["wrapper_tearing", "plastic_bag_rustling"],
        "selection_reason": "source-top sustained wrapper/plastic cluster",
    },
)


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
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("wb") as handle:
        handle.write(_json_bytes(value))
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def _self_hashed(value: dict[str, Any], field: str) -> dict[str, Any]:
    result = dict(value)
    result.pop(field, None)
    result[field] = "sha256:" + _sha256_bytes(_json_bytes(result))
    return result


def _chunks(values: list[float], count: int) -> list[list[float]]:
    if not values:
        return [[] for _ in range(count)]
    boundaries = np.linspace(0, len(values), count + 1).round().astype(int)
    return [
        values[int(boundaries[index]) : int(boundaries[index + 1])]
        for index in range(count)
    ]


def _decode_audio(path: Path, start_s: float, end_s: float) -> np.ndarray:
    parts: list[np.ndarray] = []
    with av.open(str(path), mode="r") as container:
        stream = next((stream for stream in container.streams if stream.type == "audio"), None)
        if stream is None:
            raise RuntimeError(f"AUDIO_STREAM_MISSING:{path.name}")
        resampler = av.audio.resampler.AudioResampler(
            format="fltp", layout="mono", rate=SAMPLE_RATE
        )
        container.seek(
            max(0, int((start_s - 1.0) * av.time_base)),
            any_frame=False,
            backward=True,
        )
        for frame in container.decode(stream):
            if frame.pts is None:
                continue
            frame_start = float(frame.pts * frame.time_base)
            frame_end = frame_start + float(frame.samples / frame.sample_rate)
            if frame_end < start_s:
                continue
            if frame_start > end_s:
                break
            converted_frames = resampler.resample(frame)
            for converted in converted_frames:
                array = converted.to_ndarray().reshape(-1).astype(np.float32)
                converted_start = frame_start
                left = max(0, round((start_s - converted_start) * SAMPLE_RATE))
                right = min(len(array), round((end_s - converted_start) * SAMPLE_RATE))
                if right > left:
                    parts.append(array[left:right])
        for converted in resampler.resample(None):
            if parts:
                break
    if not parts:
        raise RuntimeError(f"AUDIO_INTERVAL_EMPTY:{path.name}:{start_s}")
    expected = round((end_s - start_s) * SAMPLE_RATE)
    result = np.concatenate(parts)
    if len(result) > expected:
        result = result[:expected]
    elif len(result) < expected:
        result = np.pad(result, (0, expected - len(result)))
    return result


def _audio_descriptor(values: np.ndarray) -> dict[str, Any]:
    eps = 1e-12
    duration_s = len(values) / SAMPLE_RATE
    frame_length = 2400  # 50 ms
    hop = 1200  # 25 ms
    window = np.hanning(frame_length).astype(np.float32)
    frequencies = np.fft.rfftfreq(frame_length, d=1 / SAMPLE_RATE)
    frame_rms: list[float] = []
    centroid: list[float] = []
    high_fraction: list[float] = []
    low_fraction: list[float] = []
    spectral_flux: list[float] = []
    previous: np.ndarray | None = None
    peak_events: list[tuple[float, float]] = []
    for offset in range(0, max(1, len(values) - frame_length + 1), hop):
        frame = values[offset : offset + frame_length]
        if len(frame) < frame_length:
            frame = np.pad(frame, (0, frame_length - len(frame)))
        rms = float(np.sqrt(np.mean(np.square(frame), dtype=np.float64)))
        spectrum = np.abs(np.fft.rfft(frame * window)).astype(np.float64)
        power = np.square(spectrum)
        total = float(np.sum(power)) + eps
        frame_rms.append(rms)
        centroid.append(float(np.sum(frequencies * power) / total))
        high_fraction.append(float(np.sum(power[frequencies >= 3000]) / total))
        low_fraction.append(float(np.sum(power[frequencies < 500]) / total))
        normalized = spectrum / max(float(np.linalg.norm(spectrum)), eps)
        if previous is not None:
            spectral_flux.append(
                float(np.sqrt(np.mean(np.square(np.maximum(0, normalized - previous)))))
            )
        else:
            spectral_flux.append(0.0)
        previous = normalized
        peak_events.append((offset / SAMPLE_RATE, rms))
    rms_array = np.asarray(frame_rms, dtype=np.float64)
    flux_array = np.asarray(spectral_flux, dtype=np.float64)
    peak_events.sort(key=lambda item: (-item[1], item[0]))
    selected_peaks: list[dict[str, float]] = []
    for time_s, rms in peak_events:
        if all(abs(time_s - existing["relative_time_s"]) >= 0.15 for existing in selected_peaks):
            selected_peaks.append(
                {
                    "relative_time_s": round(time_s, 4),
                    "rms_dbfs": round(20 * math.log10(max(rms, eps)), 4),
                }
            )
        if len(selected_peaks) == 12:
            break

    bin_count = max(8, min(24, round(duration_s)))
    envelope_bins = _chunks(
        [20 * math.log10(max(value, eps)) for value in frame_rms], bin_count
    )
    centroid_bins = _chunks(centroid, bin_count)
    high_bins = _chunks(high_fraction, bin_count)
    flux_bins = _chunks(spectral_flux, bin_count)
    return {
        "duration_s": round(duration_s, 4),
        "sample_rate_hz": SAMPLE_RATE,
        "rms_dbfs": round(
            20 * math.log10(max(float(np.sqrt(np.mean(np.square(values)))), eps)), 6
        ),
        "peak_dbfs": round(
            20 * math.log10(max(float(np.max(np.abs(values))), eps)), 6
        ),
        "zero_crossing_rate": round(
            float(np.mean(np.signbit(values[1:]) != np.signbit(values[:-1]))), 8
        ),
        "frame_rms_range_db": round(
            20
            * math.log10(
                max(float(np.percentile(rms_array, 90)), eps)
                / max(float(np.percentile(rms_array, 10)), eps)
            ),
            6,
        ),
        "spectral_centroid_median_hz": round(float(np.median(centroid)), 6),
        "spectral_centroid_p90_hz": round(float(np.percentile(centroid, 90)), 6),
        "low_band_fraction_median": round(float(np.median(low_fraction)), 8),
        "high_band_fraction_median": round(float(np.median(high_fraction)), 8),
        "spectral_flux_p90": round(float(np.percentile(flux_array, 90)), 8),
        "spectral_flux_p99": round(float(np.percentile(flux_array, 99)), 8),
        "peak_frame_events": sorted(selected_peaks, key=lambda item: item["relative_time_s"]),
        "spectrogram_summary_bins": [
            {
                "bin": index,
                "start_fraction": round(index / bin_count, 6),
                "end_fraction": round((index + 1) / bin_count, 6),
                "rms_dbfs": round(float(np.mean(envelope_bins[index])), 4),
                "centroid_hz": round(float(np.mean(centroid_bins[index])), 4),
                "high_band_fraction": round(float(np.mean(high_bins[index])), 6),
                "spectral_flux": round(float(np.mean(flux_bins[index])), 8),
            }
            for index in range(bin_count)
        ],
    }


def _frame_times(start_s: float, end_s: float) -> list[float]:
    duration = end_s - start_s
    if duration <= 24:
        step = 2.0
    elif duration <= 40:
        step = 3.0
    else:
        step = 4.0
    values = list(np.arange(start_s + 1.0, max(start_s + 1.0, end_s - 0.5), step))
    if not values:
        values = [(start_s + end_s) / 2]
    return [round(float(value), 3) for value in values]


def _decode_frames(path: Path, times: list[float]) -> list[tuple[float, np.ndarray]]:
    result: list[tuple[float, np.ndarray]] = []
    with av.open(str(path), mode="r") as container:
        stream = next((stream for stream in container.streams if stream.type == "video"), None)
        if stream is None:
            raise RuntimeError(f"VIDEO_STREAM_MISSING:{path.name}")
        for requested in times:
            container.seek(
                max(0, int((requested - 1.0) * av.time_base)),
                any_frame=False,
                backward=True,
            )
            chosen = None
            chosen_time = None
            for frame in container.decode(stream):
                if frame.pts is None:
                    continue
                actual = float(frame.pts * frame.time_base)
                chosen = frame
                chosen_time = actual
                if actual >= requested:
                    break
                if actual > requested + 2:
                    break
            if chosen is None or chosen_time is None:
                raise RuntimeError(f"FRAME_DECODE_EMPTY:{path.name}:{requested}")
            result.append((chosen_time, chosen.to_ndarray(format="rgb24")))
    return result


def _frame_descriptor(actual_time: float, frame: np.ndarray) -> dict[str, Any]:
    # Compact numeric image descriptor; no pixels are persisted.
    height, width, _ = frame.shape
    small = frame[
        np.linspace(0, height - 1, 12).round().astype(int)
    ][:, np.linspace(0, width - 1, 16).round().astype(int)]
    small = small.astype(np.float32)
    luminance = (
        0.2126 * small[:, :, 0]
        + 0.7152 * small[:, :, 1]
        + 0.0722 * small[:, :, 2]
    )
    horizontal = np.abs(np.diff(luminance, axis=1))
    vertical = np.abs(np.diff(luminance, axis=0))
    dominant_channel = np.argmax(np.mean(small, axis=(0, 1)))
    channel_names = ("red", "green", "blue")
    return {
        "actual_time_s": round(actual_time, 6),
        "source_frame_width": width,
        "source_frame_height": height,
        "sample_grid": "16x12",
        "mean_rgb": [round(float(x), 4) for x in np.mean(small, axis=(0, 1))],
        "std_rgb": [round(float(x), 4) for x in np.std(small, axis=(0, 1))],
        "luminance_mean": round(float(np.mean(luminance)), 4),
        "luminance_std": round(float(np.std(luminance)), 4),
        "edge_energy": round(
            float((np.mean(horizontal) + np.mean(vertical)) / 2), 6
        ),
        "dominant_mean_channel": channel_names[int(dominant_channel)],
    }


def _ranking_hits(
    rankings: Mapping[str, Any],
    source_ref: str,
    start_s: float,
    end_s: float,
    concepts: Iterable[str],
) -> list[dict[str, Any]]:
    by_concept = {
        item["concept_id"]: item for item in rankings["concept_rankings"]
    }
    hits: list[dict[str, Any]] = []
    for concept_id in concepts:
        concept = by_concept[concept_id]
        for hit in concept["per_source_top"][source_ref]:
            if hit["end_s"] <= start_s or hit["start_s"] >= end_s:
                continue
            hits.append(
                {
                    "concept_id": concept_id,
                    "concept_label": concept["label"],
                    **hit,
                }
            )
    return sorted(
        hits,
        key=lambda item: (item["concept_id"], item["rank"], item["start_s"]),
    )


def build(root: Path) -> dict[str, Any]:
    root = root.resolve()
    discovery = root / DISCOVERY_REL
    rankings_path = discovery / "rankings.json"
    source_path = discovery / "source_bindings.json"
    manifest_path = discovery / "build_manifest.json"
    rankings = _load(rankings_path)
    source_document = _load(source_path)
    build_manifest = _load(manifest_path)
    source_map = {item["source_ref"]: item for item in source_document["sources"]}
    records: list[dict[str, Any]] = []
    temporary_path: str | None = None
    with tempfile.TemporaryDirectory(prefix="task193-review-", dir="/tmp") as temporary:
        temporary_path = temporary
        for item in REVIEW_INTERVALS:
            source = source_map[item["source_ref"]]
            media = root / source["media_path"]
            audio = _decode_audio(media, item["start_s"], item["end_s"])
            requested_frame_times = _frame_times(item["start_s"], item["end_s"])
            frames = _decode_frames(media, requested_frame_times)
            records.append(
                {
                    **item,
                    "source_sha256": source["source_sha256"],
                    "retrieval_hits": _ranking_hits(
                        rankings,
                        item["source_ref"],
                        item["start_s"],
                        item["end_s"],
                        item["retrieval_concepts"],
                    ),
                    "waveform_and_spectrogram_statistics": _audio_descriptor(audio),
                    "bounded_frame_descriptors": [
                        {
                            "requested_time_s": requested,
                            **_frame_descriptor(actual, frame),
                        }
                        for requested, (actual, frame) in zip(
                            requested_frame_times, frames, strict=True
                        )
                    ],
                    "machine_review_boundary": {
                        "human_listening": False,
                        "audio_playback": False,
                        "waveform_statistics_inspected": True,
                        "spectrogram_statistics_inspected": True,
                        "bounded_frames_decoded_in_memory": True,
                        "frames_persisted": False,
                        "audio_persisted": False,
                    },
                }
            )
            del audio, frames
        if list(Path(temporary).iterdir()):
            raise RuntimeError("TEMPORARY_MEDIA_WAS_WRITTEN")
    cleanup_verified = bool(temporary_path and not Path(temporary_path).exists())
    result = _self_hashed(
        {
            "schema_version": SCHEMA_VERSION,
            "task": 193,
            "created_date": TASK_DATE,
            "review_class": "MACHINE_EXPERT_PROVISIONAL_BOUNDED_REVIEW",
            "selection_boundary": (
                "Intervals were selected after CLAP retrieval but before any "
                "direct interval decode, based only on rankings, generic "
                "margins, recurrence structure, and event-class coverage."
            ),
            "rankings_path": f"{DISCOVERY_REL}/rankings.json",
            "rankings_sha256": _sha256_file(rankings_path),
            "source_bindings_path": f"{DISCOVERY_REL}/source_bindings.json",
            "source_bindings_sha256": _sha256_file(source_path),
            "build_manifest_path": f"{DISCOVERY_REL}/build_manifest.json",
            "build_manifest_sha256": _sha256_file(manifest_path),
            "model_revision": build_manifest["model"]["revision"],
            "review_interval_count": len(records),
            "source_count": len({item["source_ref"] for item in records}),
            "records": records,
            "media_derivative_policy": {
                "temporary_directory": temporary_path,
                "temporary_directory_cleanup_verified": cleanup_verified,
                "persisted_audio_clips": 0,
                "persisted_frames": 0,
                "persisted_waveform_images": 0,
                "persisted_spectrogram_images": 0,
            },
            "semantic_firewall": {
                "epic_semantic_annotations_used": False,
                "captaincook_semantic_annotations_used": False,
                "candidate_registries_used_for_selection": False,
                "questions_or_answers_used_for_selection": False,
            },
        },
        "review_packet_hash",
    )
    output = discovery / "machine_review_packets.json"
    _atomic_json(output, result)
    os.chmod(output, 0o600)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()
    result = build(Path(args.repo_root))
    print(
        json.dumps(
            {
                "review_interval_count": result["review_interval_count"],
                "source_count": result["source_count"],
                "review_packet_hash": result["review_packet_hash"],
                "temporary_directory_cleanup_verified": result[
                    "media_derivative_policy"
                ]["temporary_directory_cleanup_verified"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
