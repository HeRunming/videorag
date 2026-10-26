"""Bounded raw-media inspection assistance for provisional authoring."""

from __future__ import annotations

import math
from collections.abc import Mapping
from itertools import pairwise
from pathlib import Path
from typing import Any

import av
import numpy as np

FRAME_WINDOW_MAX_SECONDS = 32.0
AUDIO_WINDOW_MAX_SECONDS = 32.0
MAX_FRAME_SAMPLES = 12


def _intervals(lead: Mapping[str, Any]) -> list[dict[str, float]]:
    composition = lead.get("hop_structure", {}).get("composition")
    if isinstance(composition, Mapping):
        return [dict(item["interval"]) for item in composition["components"]]
    return [dict(lead["primary_interval"])]


def _routing_components(lead: Mapping[str, Any]) -> list[dict[str, Any]]:
    composition = lead.get("hop_structure", {}).get("composition")
    if isinstance(composition, Mapping):
        return [
            dict(item.get("routing_hypothesis", {}))
            for item in composition["components"]
        ]
    summary = lead.get("routing_observation_summary", {})
    return [
        {
            "visual": summary.get(
                "best_dynamic_visual_prompt",
                "a dynamic non-text procedure action",
            ),
            "visual_classification": summary.get(
                "visual_classification", "unknown"
            ),
            "non_speech_ast": [
                str(item.get("class_name"))
                for item in summary.get("top_machine_ast_observations", ())
            ],
        }
    ]


def _bounded(interval: Mapping[str, Any], maximum: float) -> tuple[float, float]:
    start = max(0.0, float(interval["start_s"]))
    end = max(start, float(interval["end_s"]))
    if end - start > maximum:
        midpoint = (start + end) / 2
        start = max(0.0, midpoint - maximum / 2)
        end = start + maximum
    return start, end


def _frame_times(start: float, end: float) -> list[float]:
    duration = max(0.0, end - start)
    count = max(3, min(MAX_FRAME_SAMPLES, math.ceil(duration / 2) + 1))
    if count == 1:
        return [start]
    return [
        start + index * duration / (count - 1)
        for index in range(count)
    ]


def _decode_nearest_frame(container: av.container.InputContainer, timestamp: float):
    stream = container.streams.video[0]
    seek = max(0, int(timestamp / float(stream.time_base)))
    container.seek(seek, stream=stream, backward=True, any_frame=False)
    best = None
    best_delta = float("inf")
    for frame in container.decode(stream):
        if frame.time is None:
            continue
        delta = abs(float(frame.time) - timestamp)
        if delta < best_delta:
            best = frame
            best_delta = delta
        if float(frame.time) >= timestamp and best is not None:
            break
    return best, best_delta


def _frame_metrics(frame) -> dict[str, Any]:
    array = frame.to_ndarray(format="rgb24").astype(np.float32)
    gray = array.mean(axis=2)
    vertical = float(np.abs(np.diff(gray, axis=0)).mean()) if gray.shape[0] > 1 else 0.0
    horizontal = (
        float(np.abs(np.diff(gray, axis=1)).mean()) if gray.shape[1] > 1 else 0.0
    )
    edge_proxy = (vertical + horizontal) / 510.0
    channel_spread = float(np.std(array.mean(axis=(0, 1))) / 255.0)
    return {
        "timestamp_s": round(float(frame.time or 0.0), 6),
        "mean_luma": round(float(gray.mean() / 255.0), 8),
        "luma_std": round(float(gray.std() / 255.0), 8),
        "edge_proxy": round(edge_proxy, 8),
        "channel_mean_spread": round(channel_spread, 8),
    }


def _inspect_frames(media_path: Path, intervals: list[dict[str, float]]) -> dict[str, Any]:
    samples = []
    with av.open(str(media_path)) as container:
        if not container.streams.video:
            raise ValueError("DIRECT_INSPECTION_VIDEO_STREAM_MISSING")
        for component_index, interval in enumerate(intervals, 1):
            start, end = _bounded(interval, FRAME_WINDOW_MAX_SECONDS)
            for requested in _frame_times(start, end):
                frame, delta = _decode_nearest_frame(container, requested)
                if frame is None:
                    continue
                samples.append(
                    {
                        "component_index": component_index,
                        "requested_timestamp_s": round(requested, 6),
                        "decode_delta_s": round(delta, 6),
                        **_frame_metrics(frame),
                    }
                )
    changes = []
    for left, right in pairwise(samples):
        if left["component_index"] != right["component_index"]:
            continue
        changes.append(
            abs(float(right["mean_luma"]) - float(left["mean_luma"]))
            + abs(float(right["edge_proxy"]) - float(left["edge_proxy"]))
        )
    return {
        "frame_sample_count": len(samples),
        "frame_samples": samples,
        "mean_adjacent_change_proxy": round(
            sum(changes) / len(changes) if changes else 0.0, 8
        ),
        "semantic_visual_description_generated": False,
        "frame_pixels_persisted": False,
    }


def _audio_array(frame) -> np.ndarray:
    raw = frame.to_ndarray()
    array = np.asarray(raw, dtype=np.float32)
    if array.ndim == 1:
        output = array
    else:
        output = array.mean(axis=0)
    if np.issubdtype(raw.dtype, np.integer):
        dtype = raw.dtype
        scale = float(max(abs(np.iinfo(dtype).min), np.iinfo(dtype).max))
        if scale:
            output = output / scale
    return output


def _inspect_audio(media_path: Path, intervals: list[dict[str, float]]) -> dict[str, Any]:
    results = []
    with av.open(str(media_path)) as container:
        if not container.streams.audio:
            return {
                "audio_stream_present": False,
                "interval_metrics": [],
                "human_listening_performed": False,
                "audio_samples_persisted": False,
            }
        stream = container.streams.audio[0]
        for component_index, interval in enumerate(intervals, 1):
            start, end = _bounded(interval, AUDIO_WINDOW_MAX_SECONDS)
            seek = max(0, int(start / float(stream.time_base)))
            container.seek(seek, stream=stream, backward=True, any_frame=False)
            arrays = []
            sample_rate = int(stream.rate or 0)
            for frame in container.decode(stream):
                frame_start = float(frame.time or 0.0)
                if frame_start > end:
                    break
                frame_end = frame_start + (
                    float(frame.samples) / float(frame.sample_rate or sample_rate or 1)
                )
                if frame_end < start:
                    continue
                arrays.append(_audio_array(frame))
            if arrays:
                data = np.concatenate(arrays)
                peak = float(np.max(np.abs(data)))
                rms = float(np.sqrt(np.mean(np.square(data))))
                if len(data) > 1:
                    transient = float(np.percentile(np.abs(np.diff(data)), 95))
                    zero_crossing = float(np.mean(np.signbit(data[1:]) != np.signbit(data[:-1])))
                else:
                    transient = 0.0
                    zero_crossing = 0.0
            else:
                peak = rms = transient = zero_crossing = 0.0
            results.append(
                {
                    "component_index": component_index,
                    "interval": {
                        "start_s": round(start, 6),
                        "end_s": round(end, 6),
                    },
                    "decoded_sample_count": sum(len(item) for item in arrays),
                    "sample_rate_hz": sample_rate,
                    "rms": round(rms, 8),
                    "peak": round(peak, 8),
                    "transient_p95": round(transient, 8),
                    "zero_crossing_rate": round(zero_crossing, 8),
                }
            )
    return {
        "audio_stream_present": True,
        "interval_metrics": results,
        "human_listening_performed": False,
        "semantic_sound_identity_generated": False,
        "audio_samples_persisted": False,
    }


def direct_inspection_assistance(
    media_path: str | Path,
    lead: Mapping[str, Any],
) -> dict[str, Any]:
    """Decode bounded intervals and return nonsemantic authoring scaffolds."""
    path = Path(media_path)
    if not path.is_file() or path.is_symlink():
        raise ValueError("DIRECT_INSPECTION_MEDIA_INVALID")
    intervals = _intervals(lead)
    routing = _routing_components(lead)
    frames = _inspect_frames(path, intervals)
    audio = _inspect_audio(path, intervals)
    visual_hypothesis = lead["observation_hypotheses"][
        "dynamic_nontext_visual"
    ]["status"] == "MACHINE_HYPOTHESIS"
    audio_hypothesis = (
        lead["observation_hypotheses"]["non_speech"]["status"]
        == "MACHINE_AST_HYPOTHESIS"
    )
    multi = lead["hop_structure"]["hop_stratum"] == "multi_hop"
    if multi:
        first_visual = str(
            routing[0].get("visual", "a first procedure stage")
        )
        second_visual = str(
            routing[1].get("visual", "a later procedure stage")
        )
        question = (
            f"How does the procedure progress between {intervals[0]['start_s']}"
            f"–{intervals[0]['end_s']} seconds and "
            f"{intervals[1]['start_s']}–{intervals[1]['end_s']} seconds?"
        )
        answer = (
            "Machine-expert provisional source-world answer: the first "
            f"interval may show {first_visual}; the later interval may show "
            f"{second_visual}. Retain only if direct human review verifies one "
            "shared object, material, appliance, result, or procedure chain."
        )
        claims = [
            {
                "claim_id": f"{lead['candidate_lead_id']}.component.{index}",
                "text": (
                    f"{component['claim_hypothesis']} Machine routing suggests "
                    f"{routing[index - 1].get('visual', 'a procedure event')}."
                ),
                "human_validated": False,
            }
            for index, component in enumerate(
                lead["hop_structure"]["composition"]["components"], 1
            )
        ] + [
            {
                "claim_id": f"{lead['candidate_lead_id']}.composed",
                "text": lead["hop_structure"]["composition"][
                    "composed_claim_hypothesis"
                ],
                "human_validated": False,
            }
        ]
    else:
        visual_route = str(
            routing[0].get("visual", "a dynamic non-text procedure action")
        )
        ast_routes = [
            str(item) for item in routing[0].get("non_speech_ast", ())
        ]
        question = (
            f"What procedure action or state change most plausibly occurs "
            f"from {intervals[0]['start_s']} to {intervals[0]['end_s']} "
            "seconds, and is there a meaningful non-speech process sound?"
        )
        answer = (
            f"Machine-expert provisional source-world answer: {visual_route}."
            + (
                " Candidate sound routes for trained-human listening are "
                + ", ".join(ast_routes)
                + "."
                if ast_routes
                else " No concrete sound identity is proposed."
            )
        )
        claims = [
            {
                "claim_id": f"{lead['candidate_lead_id']}.event",
                "text": (
                    f"The interval may show {visual_route}, rather than a text, "
                    "static-scene, person-identity, or environment shortcut."
                ),
                "human_validated": False,
            }
        ]
        if ast_routes:
            claims.append(
                {
                    "claim_id": f"{lead['candidate_lead_id']}.sound",
                    "text": (
                        "The interval may contain a procedure-relevant "
                        f"non-speech sound routed as {', '.join(ast_routes)}; "
                        "AST names and waveform metrics are not semantic proof."
                    ),
                    "human_validated": False,
                }
            )
    evidence = [
        {
            "evidence_id": f"{lead['candidate_lead_id']}.visual.{index}",
            "modality": "vision",
            "carrier_class": "dynamic_nontext_visual",
            "interval": interval,
            "hypothesis": (
                "Bounded decoded frames may support the procedure claim; no "
                "semantic visual identity is assigned by this helper."
            ),
            "human_semantic_validation_status": "NOT_PERFORMED",
        }
        for index, interval in enumerate(intervals, 1)
    ]
    if audio_hypothesis:
        evidence.append(
            {
                "evidence_id": f"{lead['candidate_lead_id']}.audio",
                "modality": "audio",
                "carrier_class": "meaningful_non_speech_audio",
                "interval": intervals[-1],
                "hypothesis": (
                    "AST routing plus bounded waveform metrics may indicate a "
                    "procedure sound, but a trained human must listen and name it."
                ),
                "human_semantic_validation_status": "NOT_PERFORMED",
            }
        )
    return {
        "raw_local_media_only": True,
        "limits": {
            "frame_window_max_seconds": FRAME_WINDOW_MAX_SECONDS,
            "audio_window_max_seconds": AUDIO_WINDOW_MAX_SECONDS,
            "maximum_frame_samples": MAX_FRAME_SAMPLES,
        },
        "frame_inspection": frames,
        "audio_inspection": audio,
        "repository_media_derivatives_persisted": False,
        "source_world_hypotheses": {
            "artifact_classification": "MACHINE_EXPERT_PROVISIONAL",
            "question_hypothesis": question,
            "answer_hypothesis": answer,
            "claim_hypotheses": claims,
            "evidence_hypotheses": evidence,
            "visual_route_expected": visual_hypothesis,
            "non_speech_route_expected": audio_hypothesis,
            "human_semantic_validation_status": "NOT_PERFORMED",
            "accepted_family": False,
            "accepted_ses": False,
            "necessity_claimed": False,
            "minimality_claimed": False,
        },
    }


def unexecuted_inspection_scaffold(
    lead: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the same contract without reading media."""
    intervals = _intervals(lead)
    multi = lead["hop_structure"]["hop_stratum"] == "multi_hop"
    claims = []
    if multi:
        for index, component in enumerate(
            lead["hop_structure"]["composition"]["components"], 1
        ):
            claims.append(
                {
                    "claim_id": f"{lead['candidate_lead_id']}.component.{index}",
                    "text": component["claim_hypothesis"],
                    "human_validated": False,
                }
            )
    else:
        claims.append(
            {
                "claim_id": f"{lead['candidate_lead_id']}.event",
                "text": (
                    "The interval may contain a substantive dynamic procedure "
                    "event; bounded direct inspection has not yet run."
                ),
                "human_validated": False,
            }
        )
    return {
        "raw_local_media_only": True,
        "limits": {
            "frame_window_max_seconds": FRAME_WINDOW_MAX_SECONDS,
            "audio_window_max_seconds": AUDIO_WINDOW_MAX_SECONDS,
            "maximum_frame_samples": MAX_FRAME_SAMPLES,
        },
        "frame_inspection": {
            "status": "NOT_RUN",
            "frame_sample_count": 0,
            "frame_samples": [],
            "semantic_visual_description_generated": False,
            "frame_pixels_persisted": False,
        },
        "audio_inspection": {
            "status": "NOT_RUN",
            "interval_metrics": [],
            "human_listening_performed": False,
            "semantic_sound_identity_generated": False,
            "audio_samples_persisted": False,
        },
        "repository_media_derivatives_persisted": False,
        "source_world_hypotheses": {
            "artifact_classification": "MACHINE_EXPERT_PROVISIONAL",
            "question_hypothesis": (
                "What source-world procedure event or coherent relation should "
                "a trained author test in the bounded interval(s)?"
            ),
            "answer_hypothesis": (
                "A provisional event answer must be created by bounded direct "
                "inspection without consulting semantic annotations."
            ),
            "claim_hypotheses": claims,
            "evidence_hypotheses": [
                {
                    "evidence_id": f"{lead['candidate_lead_id']}.pending.{index}",
                    "modality": "audiovisual",
                    "carrier_class": "pending_bounded_direct_inspection",
                    "interval": interval,
                    "hypothesis": (
                        "This interval is queued for direct bounded frame and "
                        "audio inspection."
                    ),
                    "human_semantic_validation_status": "NOT_PERFORMED",
                }
                for index, interval in enumerate(intervals, 1)
            ],
            "human_semantic_validation_status": "NOT_PERFORMED",
            "accepted_family": False,
            "accepted_ses": False,
            "necessity_claimed": False,
            "minimality_claimed": False,
        },
    }


__all__ = [
    "AUDIO_WINDOW_MAX_SECONDS",
    "FRAME_WINDOW_MAX_SECONDS",
    "MAX_FRAME_SAMPLES",
    "direct_inspection_assistance",
    "unexecuted_inspection_scaffold",
]
