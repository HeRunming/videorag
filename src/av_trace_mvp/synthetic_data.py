"""Deterministic synthetic audio-visual corpus generation for the AV-TRACE MVP.

The generator intentionally uses only local procedural graphics and audio.  Its
"speech" channel is a symbolic tonal track paired with an exact textual
transcript; it does not call a speech model or use downloaded assets.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import time
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable

import av
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from av_trace import GateProfile, SchemaRegistry, validate_family, validate_manifest_gate

FIXED_TIMESTAMP = "2026-09-05T00:00:00Z"
GENERATOR_VERSION = "1.0.0"
ALL_CHANNELS = ["visual", "speech", "ambient", "clip", "transcript"]
CHANNEL_MODALITIES = {
    "visual": {"vision"},
    "speech": {"speech"},
    "ambient": {"ambient"},
}
TOOL_COSTS = {
    "search_visual": 1.0,
    "search_speech": 1.0,
    "search_ambient_audio": 1.0,
    "inspect_clip": 2.0,
    "read_transcript": 1.0,
    "get_channel_status": 0.25,
    "finalize": 0.0,
}


@dataclass(frozen=True)
class GenerationResult:
    output_dir: Path
    source_count: int
    family_count: int
    episode_count: int
    total_bytes: int
    metadata_sha256: str
    elapsed_s: float
    mp4_hashes: dict[str, str]


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_json_bytes(value))


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _stable_hash(label: str) -> str:
    return _sha256_bytes(label.encode("utf-8"))


def _load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _event_index(source: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {event["event_id"]: event for event in source["events"]}


def _active_events(source: dict[str, Any], second: float) -> list[dict[str, Any]]:
    return [
        event
        for event in source["events"]
        if float(event["start_s"]) <= second < float(event["end_s"])
    ]


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _draw_centered(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, font: ImageFont.ImageFont, fill: str) -> None:
    box = draw.textbbox((0, 0), text, font=font)
    draw.text((xy[0] - (box[2] - box[0]) // 2, xy[1] - (box[3] - box[1]) // 2), text, font=font, fill=fill)


def _draw_shape(draw: ImageDraw.ImageDraw, shape: str, color: str, cx: int, cy: int, radius: int) -> None:
    if shape == "circle":
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=color, outline="white", width=3)
    elif shape == "square":
        draw.rectangle((cx - radius, cy - radius, cx + radius, cy + radius), fill=color, outline="white", width=3)
    elif shape == "triangle":
        draw.polygon([(cx, cy - radius), (cx - radius, cy + radius), (cx + radius, cy + radius)], fill=color, outline="white")
    elif shape == "hexagon":
        points = [
            (cx + int(radius * math.cos(math.pi * k / 3)), cy + int(radius * math.sin(math.pi * k / 3)))
            for k in range(6)
        ]
        draw.polygon(points, fill=color, outline="white")
    elif shape == "star":
        points = []
        for k in range(10):
            r = radius if k % 2 == 0 else radius // 2
            angle = -math.pi / 2 + k * math.pi / 5
            points.append((cx + int(r * math.cos(angle)), cy + int(r * math.sin(angle))))
        draw.polygon(points, fill=color, outline="white")
    elif shape == "arrow_right":
        points = [
            (cx - radius, cy - radius // 2),
            (cx + radius // 4, cy - radius // 2),
            (cx + radius // 4, cy - radius),
            (cx + radius, cy),
            (cx + radius // 4, cy + radius),
            (cx + radius // 4, cy + radius // 2),
            (cx - radius, cy + radius // 2),
        ]
        draw.polygon(points, fill=color, outline="white")


def _video_image(source: dict[str, Any], second: float, width: int, height: int) -> Image.Image:
    image = Image.new("RGB", (width, height), source["base_color"])
    draw = ImageDraw.Draw(image)
    title_font = _font(18)
    event_font = _font(17)
    small_font = _font(12)
    draw.rectangle((0, 0, width, 31), fill="#101010")
    draw.text((8, 6), f"{source['source_id']} | {source['title']}", font=small_font, fill="white")
    draw.text((width - 82, 6), f"{int(second):04d}s", font=small_font, fill="#d5d5d5")
    draw.rectangle((8, height - 25, width - 8, height - 8), outline="#667085", width=1)
    progress = min(1.0, second / float(source["duration_s"]))
    draw.rectangle((9, height - 24, 9 + int((width - 18) * progress), height - 9), fill="#5c7cfa")

    active = _active_events(source, second)
    visual = next((event for event in active if event["modality"] == "vision"), None)
    audio = next((event for event in active if event["modality"] in {"speech", "ambient"}), None)
    if visual:
        spec = visual["visual"]
        _draw_shape(draw, spec["shape"], spec["color"], width // 2, height // 2 - 4, 42)
        _draw_centered(draw, (width // 2, height - 43), visual["label"], event_font, "white")
    else:
        _draw_centered(draw, (width // 2, height // 2 - 5), "SYNTHETIC AV-TRACE", title_font, "#b8c0cc")
    if audio:
        # The content itself remains audio/transcript-only.  The video marks only
        # that a channel is active, avoiding a visual answer leak.
        marker = "SPEECH CHANNEL ACTIVE" if audio["modality"] == "speech" else "AMBIENT CHANNEL ACTIVE"
        draw.rectangle((42, 35, width - 42, 57), fill="#111111", outline="#dddddd")
        _draw_centered(draw, (width // 2, 46), marker, small_font, "#f8f9fa")
    return image


def _tone(samples: np.ndarray, t: np.ndarray, frequency: float, amplitude: float) -> None:
    samples += amplitude * np.sin(2.0 * math.pi * frequency * t)


def _audio_second(source: dict[str, Any], second: int, rate: int, seed: int) -> np.ndarray:
    t = np.arange(rate, dtype=np.float64) / rate
    samples = np.zeros(rate, dtype=np.float64)
    # A very quiet project-owned carrier ensures the audio stream is continuous.
    _tone(samples, t + second, 55.0, 0.008)
    for event in _active_events(source, second + 0.5):
        if event["modality"] not in {"speech", "ambient"}:
            continue
        audio = event["audio"]
        relative = second - int(event["start_s"])
        frequency = float(audio["frequency_hz"])
        kind = audio["kind"]
        if kind == "speech_token":
            # Two alternating tones make symbolic speech cues distinguishable.
            gate = ((np.floor(t * 6) + relative) % 2) == 0
            samples += gate * 0.20 * np.sin(2 * math.pi * frequency * t)
            samples += (~gate) * 0.14 * np.sin(2 * math.pi * frequency * 1.25 * t)
        elif kind == "bell_pulses":
            count = int(audio["pulse_count"])
            event_duration = float(event["end_s"] - event["start_s"])
            event_time = relative + t
            for pulse in range(count):
                center = (pulse + 0.5) * event_duration / count
                envelope = np.exp(-8.0 * np.maximum(0.0, event_time - center)) * (event_time >= center) * (event_time < center + 0.7)
                samples += 0.25 * envelope * np.sin(2 * math.pi * frequency * t)
        elif kind == "motor_hum":
            _tone(samples, t + relative, frequency, 0.18)
            _tone(samples, t + relative, frequency * 2, 0.08)
        elif kind == "confirmation_chime":
            _tone(samples, t + relative, frequency, 0.20)
            _tone(samples, t + relative, frequency * 1.5, 0.10)
        else:
            rng = np.random.default_rng(seed + second)
            samples += rng.normal(0.0, 0.08, size=rate)
    fade = np.minimum(np.arange(rate) / max(1, rate // 100), 1.0)
    fade *= np.minimum(np.arange(rate)[::-1] / max(1, rate // 100), 1.0)
    samples *= fade
    return np.clip(samples * 32767.0, -32768, 32767).astype(np.int16)


def _write_mp4(path: Path, source: dict[str, Any], media: dict[str, Any], seed: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    width, height = int(media["width"]), int(media["height"])
    fps, rate = int(media["fps"]), int(media["audio_rate"])
    container = av.open(str(path), mode="w")
    video_stream = container.add_stream(media["video_codec"], rate=fps)
    video_stream.width = width
    video_stream.height = height
    video_stream.pix_fmt = "yuv420p"
    video_stream.options = {
        "preset": "ultrafast",
        "crf": "34",
        "threads": "1",
        "x264-params": "scenecut=0:open-gop=0",
    }
    audio_stream = container.add_stream(media["audio_codec"], rate=rate)
    audio_stream.layout = "mono"
    audio_stream.bit_rate = 32000
    duration = int(source["duration_s"])
    try:
        for second in range(duration):
            for frame_offset in range(fps):
                timestamp = second + frame_offset / fps
                image = _video_image(source, timestamp, width, height)
                frame = av.VideoFrame.from_image(image)
                frame.pts = second * fps + frame_offset
                frame.time_base = Fraction(1, fps)
                for packet in video_stream.encode(frame):
                    container.mux(packet)
            audio_array = _audio_second(source, second, rate, seed)
            audio_frame = av.AudioFrame.from_ndarray(audio_array.reshape(1, -1), format="s16", layout="mono")
            audio_frame.sample_rate = rate
            audio_frame.pts = second * rate
            audio_frame.time_base = Fraction(1, rate)
            for packet in audio_stream.encode(audio_frame):
                container.mux(packet)
        for packet in video_stream.encode():
            container.mux(packet)
        for packet in audio_stream.encode():
            container.mux(packet)
    finally:
        container.close()


def _timeline(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "source_id": source["source_id"],
        "duration_s": source["duration_s"],
        "events": [
            {
                "event_id": event["event_id"],
                "start_s": event["start_s"],
                "end_s": event["end_s"],
                "modality": event["modality"],
                "label": event["label"],
            }
            for event in source["events"]
        ],
    }


def _transcript(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "source_id": source["source_id"],
        "track_type": "deterministic_symbolic_speech_with_exact_text",
        "segments": [
            {
                "segment_id": event["event_id"],
                "start_s": event["start_s"],
                "end_s": event["end_s"],
                "text": event["transcript"],
                "audio_encoding": "alternating_tonal_token",
            }
            for event in source["events"]
            if event["modality"] == "speech"
        ],
    }


def _audio_labels(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "source_id": source["source_id"],
        "events": [
            {
                "event_id": event["event_id"],
                "start_s": event["start_s"],
                "end_s": event["end_s"],
                "class": event["label"],
                "modality": event["modality"],
                "audio_parameters": event["audio"],
            }
            for event in source["events"]
            if event["modality"] in {"speech", "ambient"}
        ],
    }


def _evidence_records(source: dict[str, Any]) -> dict[str, Any]:
    uses: dict[str, list[str]] = {event["event_id"]: [] for event in source["events"]}
    for family in source["families"]:
        for event_id in family["evidence_event_ids"]:
            uses[event_id].append(family["family_id"])
    return {
        "schema_version": "1.0",
        "source_id": source["source_id"],
        "evidence": [
            {
                "evidence_id": event["event_id"],
                "intervals": [{"start_s": event["start_s"], "end_s": event["end_s"]}],
                "modality": event["modality"],
                "observation": event["label"],
                "used_by_family_ids": sorted(uses[event["event_id"]]),
            }
            for event in source["events"]
        ],
    }


def _artifact(
    *,
    artifact_id: str,
    artifact_type: str,
    source_id: str,
    relative_path: str,
    digest: str,
) -> dict[str, Any]:
    return {
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "source_asset_id": source_id,
        "uri": f"https://example.invalid/av-trace-synthetic/{relative_path}",
        "sha256": digest,
        "created_at": FIXED_TIMESTAMP,
        "tool_or_protocol": f"av_trace_mvp.synthetic_data/{GENERATOR_VERSION}",
        "rights_basis": {
            "license_or_grant_name": "synthetic_project_owned",
            "version": "1",
            "licensor_or_grantor": "AV-TRACE project",
            "uri": "https://example.invalid/av-trace-synthetic/rights",
            "scope": "Project-owned procedural media and all generated metadata.",
        },
        "release_decision": "allowed",
        "release_audience": "public",
        "evidence_snapshot_hash": _stable_hash("synthetic_project_owned:rights:v1"),
        "contains_personal_data": False,
        "substitution_risk_reviewed": True,
    }


def _manifest(
    source: dict[str, Any],
    mp4_path: Path,
    artifact_specs: list[tuple[str, str, Path, str]],
    output_dir: Path,
) -> dict[str, Any]:
    source_id = source["source_id"]
    return {
        "manifest_version": "0.2.0",
        "manifest_revision": "synthetic-v1",
        "asset_id": source_id,
        "dataset_id": "synthetic_project_owned",
        "source": {
            "canonical_url": f"https://example.invalid/av-trace-synthetic/{source_id}",
            "source_identifier": source_id,
            "source_revision": "procedural-v1",
            "publisher": "AV-TRACE project",
            "rightsholder_or_status": "synthetic_project_owned",
            "source_family": "DIRECT_GRANT",
        },
        "acquisition": {
            "status": "completed",
            "method": "rightsholder_delivery",
            "authority_basis": "synthetic_project_owned: generated locally by the AV-TRACE project",
            "authority_evidence_uri": "https://example.invalid/av-trace-synthetic/rights",
            "authority_evidence_hash": _stable_hash("synthetic_project_owned:rights:v1"),
            "planned_or_actual_at": FIXED_TIMESTAMP,
        },
        "integrity": {
            "content_hash_plan": "sha256_of_exact_acquired_bytes",
            "content_sha256": _sha256_file(mp4_path),
            "byte_size": mp4_path.stat().st_size,
            "probe_version": f"PyAV-{av.__version__}",
        },
        "media": {
            "duration_s": float(source["duration_s"]),
            "has_video": True,
            "has_audio": True,
            "has_speech": any(event["modality"] == "speech" for event in source["events"]),
            "has_ambient_audio": any(event["modality"] == "ambient" for event in source["events"]),
            "embedded_content_reviewed": True,
        },
        "rights": {
            "rights_decision_id": f"rights_{source_id}",
            "copyright_basis": "direct_permission",
            "acquisition_authority": "allowed",
            "local_processing_authority": "allowed",
            "license_or_grant": {
                "name": "synthetic_project_owned",
                "version": "1",
                "licensor_or_grantor": "AV-TRACE project",
                "uri": "https://example.invalid/av-trace-synthetic/rights",
                "agreement_id": f"project-owned-{source_id}",
                "scope": "Unrestricted project use and release of procedurally generated media and metadata.",
            },
            "evidence_snapshot": {
                "captured_at": FIXED_TIMESTAMP,
                "uri": "https://example.invalid/av-trace-synthetic/rights-snapshot",
                "sha256": _stable_hash("synthetic_project_owned:rights:v1"),
            },
            "decisions": {
                "acquisition": "allowed",
                "processing": "allowed",
                "derivative_release": "allowed",
                "annotation_release": "allowed",
                "transcript_release": "allowed",
                "raw_media_release": "allowed",
                "commercial_use": "allowed",
            },
            "embedded_components": {
                "music": "not_applicable",
                "subtitles": "not_applicable",
                "third_party_inserts": "not_applicable",
                "logos_and_marks": "not_applicable",
                "identifiable_people": "not_applicable",
                "minors": "not_applicable",
            },
            "review": {
                "reviewer_id": "synthetic_rights_reviewer",
                "reviewed_at": FIXED_TIMESTAMP,
                "jurisdiction": "project-owned synthetic fixture",
                "outcome": "approved",
                "notes": "No downloaded, third-party, copyrighted, or real-world media are present.",
            },
        },
        "privacy_safety": {
            "review_status": "approved",
            "reviewer_id": "synthetic_privacy_reviewer",
            "reviewed_at": FIXED_TIMESTAMP,
            "contains_identifiable_people": False,
            "contains_minors": False,
            "contains_sensitive_content": False,
            "mitigations": ["Procedural shapes, labels, tones, and noise only."],
        },
        "derived_artifacts": [
            _artifact(
                artifact_id=artifact_id,
                artifact_type=artifact_type,
                source_id=source_id,
                relative_path=str(path.relative_to(output_dir)).replace("\\", "/"),
                digest=digest,
            )
            for artifact_id, artifact_type, path, digest in artifact_specs
        ],
        "audit": {
            "record_created_at": FIXED_TIMESTAMP,
            "record_updated_at": FIXED_TIMESTAMP,
            "created_by": "synthetic_generator",
            "updated_by": "synthetic_generator",
            "gate_status": "public_release_approved",
            "change_log": [
                {
                    "changed_at": FIXED_TIMESTAMP,
                    "changed_by": "synthetic_generator",
                    "summary": "Generated deterministic synthetic_project_owned corpus asset.",
                }
            ],
        },
    }


def _graph_for_family(
    source: dict[str, Any],
    family_spec: dict[str, Any],
    stream_hashes: dict[str, str],
) -> tuple[dict[str, Any], dict[str, str]]:
    events = _event_index(source)
    family_id = family_spec["family_id"]
    claim_id = f"claim_{family_id}"
    evidence_ids = list(family_spec["evidence_event_ids"])
    evidence_units = []
    for event_id in evidence_ids:
        event = events[event_id]
        stream_kind = "video" if event["modality"] == "vision" else "audio"
        evidence_units.append(
            {
                "evidence_id": event_id,
                "intervals": [{"start_s": float(event["start_s"]), "end_s": float(event["end_s"])}],
                "modality": event["modality"],
                "stream_id": f"{source['source_id']}_{stream_kind}",
                "observation": event["label"],
                "provenance": {
                    "asset_id": source["source_id"],
                    "stream_hash": stream_hashes[stream_kind],
                    "transformation_ids": ["exact_transcript_v1"] if event["modality"] == "speech" else [],
                },
            }
        )

    hops = []
    edges = []
    extract_hops: dict[str, str] = {}
    for event_id in evidence_ids:
        event = events[event_id]
        hop_id = f"hop_extract_{event_id}"
        extract_hops[event_id] = hop_id
        hop_type = {
            "vision": "event_detection",
            "speech": "speech_content",
            "ambient": "ambient_event",
        }[event["modality"]]
        hops.append(
            {
                "hop_id": hop_id,
                "hop_type": hop_type,
                "description": f"Extract the registered {event['modality']} observation: {event['label']}.",
                "input_evidence_ids": [event_id],
                "input_hop_ids": [],
            }
        )
        edges.append(
            {
                "edge_id": f"edge_{event_id}_extract",
                "relation": "supports_hop",
                "from_ids": [event_id],
                "to_id": hop_id,
            }
        )

    accepted_sets = []
    for route_index, route in enumerate(family_spec["accepted_ses"], start=1):
        route_hop = f"hop_{family_id}_route_{route_index}"
        route_modalities = {events[event_id]["modality"] for event_id in route}
        hops.append(
            {
                "hop_id": route_hop,
                "hop_type": "cross_modal_binding" if len(route_modalities) > 1 else "temporal_order",
                "description": f"Combine temporally registered evidence for accepted route {route_index}.",
                "input_evidence_ids": [],
                "input_hop_ids": [extract_hops[event_id] for event_id in route],
            }
        )
        edges.append(
            {
                "edge_id": f"edge_{family_id}_route_{route_index}",
                "relation": "supports_hop",
                "from_ids": [extract_hops[event_id] for event_id in route],
                "to_id": route_hop,
            }
        )
        edges.append(
            {
                "edge_id": f"edge_{family_id}_claim_{route_index}",
                "relation": "hop_supports_claim",
                "from_ids": [route_hop],
                "to_id": claim_id,
            }
        )
        accepted_sets.append(
            {
                "set_id": f"ses_{family_id}_{route_index}",
                "claim_ids": [claim_id],
                "evidence_ids": list(route),
                "hop_ids": [extract_hops[event_id] for event_id in route] + [route_hop],
                "satisfiability_validated": True,
                "minimality_validated": True,
                "validator_ids": ["synthetic_validator_a", "synthetic_validator_b"],
            }
        )

    if family_spec["mechanism"] == "necessity_group_withholding":
        blocked_ids = list(family_spec["blocked_event_ids"])
    else:
        blocked_ids = [
            event_id
            for event_id in evidence_ids
            if events[event_id]["modality"] in CHANNEL_MODALITIES[family_spec["blocked_channel"]]
        ]
    blocked_set = set(blocked_ids)
    all_hop_ids = {hop["hop_id"] for hop in hops}

    def available_hops(available_evidence: set[str]) -> set[str]:
        available: set[str] = set()
        changed = True
        while changed:
            changed = False
            for hop in hops:
                hop_id = hop["hop_id"]
                if hop_id in available:
                    continue
                if set(hop["input_evidence_ids"]) <= available_evidence and set(hop["input_hop_ids"]) <= available:
                    available.add(hop_id)
                    changed = True
        return available

    broken_hops = all_hop_ids - available_hops(set(evidence_ids) - blocked_set)
    group_id = f"ng_{family_id}"
    graph = {
        "claims": [
            {
                "claim_id": claim_id,
                "proposition": family_spec["answer"],
                "requirement": "required",
                "answer_value": family_spec["claim"],
                "accepted_aliases": [family_spec["answer"]],
                "contradiction_claim_ids": [],
            }
        ],
        "evidence_units": evidence_units,
        "hops": hops,
        "support_edges": edges,
        "accepted_sufficient_sets": accepted_sets,
        "necessity_groups": [
            {
                "group_id": group_id,
                "claim_ids": [claim_id],
                "member_evidence_ids": blocked_ids,
                "required_modalities": sorted({events[event_id]["modality"] for event_id in blocked_ids}),
                "required_hop_ids": sorted(broken_hops),
                "intersects_all_accepted_sets": True,
                "removal_validated": True,
            }
        ],
    }
    return graph, {"claim_id": claim_id, "group_id": group_id}


def _family(
    source: dict[str, Any],
    family_spec: dict[str, Any],
    manifest: dict[str, Any],
    seed: int,
) -> dict[str, Any]:
    source_id = source["source_id"]
    family_id = family_spec["family_id"]
    stream_hashes = {
        "video": _stable_hash(f"{source_id}:video_stream:procedural-v1"),
        "audio": _stable_hash(f"{source_id}:audio_stream:procedural-v1"),
    }
    graph, ids = _graph_for_family(source, family_spec, stream_hashes)
    all_evidence = list(family_spec["evidence_event_ids"])
    event_by_id = _event_index(source)
    if family_spec["mechanism"] == "necessity_group_withholding":
        affected = list(family_spec["blocked_event_ids"])
        affected_group: str | None = ids["group_id"]
        affected_channel: str | None = None
    else:
        affected_channel = family_spec["blocked_channel"]
        affected = [
            event_id
            for event_id in all_evidence
            if event_by_id[event_id]["modality"] in CHANNEL_MODALITIES[affected_channel]
        ]
        affected_group = None
    blocked_access = [event_id for event_id in all_evidence if event_id not in set(affected)]
    blocked_channels = [channel for channel in ALL_CHANNELS if channel != affected_channel]
    missing_hops = sorted(set(graph["necessity_groups"][0]["required_hop_ids"]))
    hop_types = sorted(
        {
            hop["hop_type"]
            for hop in graph["hops"]
            if hop["hop_id"] in set(missing_hops)
        }
    )
    missing_modalities = sorted({event_by_id[event_id]["modality"] for event_id in affected})
    ses_ids = [item["set_id"] for item in graph["accepted_sufficient_sets"]]
    intervention_family_id = f"if_{family_id}"
    block = {
        "intervention_id": f"block_{family_id}",
        "mechanism": family_spec["mechanism"],
        "phase": "blocked",
        "affected_necessity_group_id": affected_group,
        "affected_evidence_ids": affected,
        "affected_channel": affected_channel,
        "activation": {"hook": "episode_start", "call_index": None},
        "restoration": {
            "enabled": False,
            "trigger_type": "none",
            "trigger_value": None,
            "restores_intervention_id": None,
        },
    }
    restore = {
        **block,
        "intervention_id": f"restore_{family_id}",
        "phase": "restoration",
        "activation": {"hook": "on_restore", "call_index": None},
        "restoration": {
            "enabled": True,
            "trigger_type": "get_channel_status",
            "trigger_value": None,
            "restores_intervention_id": block["intervention_id"],
        },
    }
    backend = {
        # Current semantic validation reserves PUBLIC_CORE for 20–90 minute
        # assets.  These deliberately tiny 4–8 minute engineering fixtures use
        # the schema-supported unpooled compatibility track.
        "track": "EXTERNAL_COMPATIBILITY_UNPOOLED",
        "backend_version": "synthetic-fixed-v1",
        "tool_api_version": "0.2.0",
        "index_hash": _stable_hash(f"{source_id}:synthetic-index-v1"),
    }
    budget = {"cost_limit": 12.0, "max_steps": 10, "tool_costs": TOOL_COSTS}
    replay = {
        "seed": seed,
        "manifest_hash": _stable_hash(f"{family_id}:backend-manifest:{seed}"),
        "deterministic": True,
    }
    common_oracle = {
        "source_sufficient": True,
        "gold_missing_necessity_group_ids": [ids["group_id"]],
        "gold_missing_modality_sets": [missing_modalities],
        "gold_missing_hop_ids": missing_hops,
        "gold_missing_hop_types": hop_types,
    }
    clean_id = f"{family_id}.clean"
    episodes = [
        {
            "episode_id": clean_id,
            "state_role": "CLEAN",
            "anchor_episode_id": None,
            "intervention_family_id": intervention_family_id,
            "backend": backend,
            "budget": budget,
            "initial_state": {"enabled_channels": ALL_CHANNELS, "accessible_evidence_ids": all_evidence},
            "interventions": [],
            "oracle": {
                "source_sufficient": True,
                "initial_accessible_sufficient": True,
                "expected_final_sufficiency": "sufficient",
                "gold_missing_necessity_group_ids": [],
                "gold_missing_modality_sets": [],
                "gold_missing_hop_ids": [],
                "gold_missing_hop_types": [],
                "missingness_cause": "not_missing",
                "accepted_final_set_ids": ses_ids,
            },
            "replay": replay,
        },
        {
            "episode_id": f"{family_id}.blocked",
            "state_role": "BLOCKED",
            "anchor_episode_id": clean_id,
            "intervention_family_id": intervention_family_id,
            "backend": backend,
            "budget": budget,
            "initial_state": {"enabled_channels": blocked_channels, "accessible_evidence_ids": blocked_access},
            "interventions": [block],
            "oracle": {
                **common_oracle,
                "initial_accessible_sufficient": False,
                "expected_final_sufficiency": "insufficient",
                "missingness_cause": "evidence_in_source_but_inaccessible",
                "accepted_final_set_ids": [],
            },
            "replay": replay,
        },
        {
            "episode_id": f"{family_id}.restored",
            "state_role": "RESTORED",
            "anchor_episode_id": clean_id,
            "intervention_family_id": intervention_family_id,
            "backend": backend,
            "budget": budget,
            "initial_state": {"enabled_channels": blocked_channels, "accessible_evidence_ids": blocked_access},
            "interventions": [block, restore],
            "oracle": {
                **common_oracle,
                "initial_accessible_sufficient": False,
                "expected_final_sufficiency": "sufficient",
                "missingness_cause": "evidence_in_source_but_inaccessible",
                "accepted_final_set_ids": ses_ids,
            },
            "replay": replay,
        },
    ]
    return {
        "schema_version": "0.2.0",
        "family_id": family_id,
        "intervention_family_id": intervention_family_id,
        "intervention_mechanism": family_spec["mechanism"],
        "split": "development",
        "source": {
            "asset_id": source_id,
            "manifest_asset_id": source_id,
            "manifest_revision": manifest["manifest_revision"],
            "rights_decision_id": manifest["rights"]["rights_decision_id"],
            "duration_s": float(source["duration_s"]),
            "content_hash": manifest["integrity"]["content_sha256"],
            "streams": [
                {"stream_id": f"{source_id}_video", "kind": "video", "language": None, "hash": stream_hashes["video"]},
                {"stream_id": f"{source_id}_audio", "kind": "audio", "language": "en-x-synthetic", "hash": stream_hashes["audio"]},
            ],
            "access_class": "restricted_compatibility",
        },
        "question": {
            "text": family_spec["question"],
            "answer_type": "structured_claims",
            "requested_granularity": "Return the exact registered values for both linked observations.",
            "question_only_risk": "low",
        },
        "answer_spec": {
            "required_claim_ids": [ids["claim_id"]],
            "optional_claim_ids": [],
            "forbidden_claim_ids": [],
            "display_answer": family_spec["answer"],
        },
        "claim_evidence_graph": graph,
        "episodes": episodes,
        "annotation": {
            "status": "accepted",
            "version": "synthetic-v1",
            "authors": ["synthetic_author"],
            "alternative_evidence_finder": "synthetic_alternative_finder",
            "validators": ["synthetic_validator_a", "synthetic_validator_b"],
            "adjudicator": "synthetic_adjudicator",
            "alternative_search_completed": True,
            "shortcut_audits": [
                {"audit_type": "question_only", "status": "pass", "notes": "Answers are arbitrary registered tokens."},
                {"audit_type": "intervention_artifact", "status": "pass", "notes": "No condition marker is embedded in source media."},
            ],
        },
    }


def _validate_config(config: dict[str, Any]) -> None:
    source_ids: set[str] = set()
    family_ids: set[str] = set()
    for source in config["sources"]:
        source_id = source["source_id"]
        if source_id in source_ids:
            raise ValueError(f"duplicate source_id: {source_id}")
        source_ids.add(source_id)
        if not 240 <= int(source["duration_s"]) <= 480:
            raise ValueError(f"{source_id} duration must be 4–8 minutes")
        events = _event_index(source)
        if len(events) != len(source["events"]):
            raise ValueError(f"{source_id} has duplicate event IDs")
        for event in source["events"]:
            if not 0 <= event["start_s"] < event["end_s"] <= source["duration_s"]:
                raise ValueError(f"invalid event interval: {event['event_id']}")
        for family in source["families"]:
            family_id = family["family_id"]
            if family_id in family_ids:
                raise ValueError(f"duplicate family_id: {family_id}")
            family_ids.add(family_id)
            if not set(family["evidence_event_ids"]) <= set(events):
                raise ValueError(f"{family_id} references an unknown event")
            for route in family["accepted_ses"]:
                if not route or not set(route) <= set(family["evidence_event_ids"]):
                    raise ValueError(f"{family_id} has an invalid accepted SES")
            if family["mechanism"] == "necessity_group_withholding":
                blocked = set(family["blocked_event_ids"])
            else:
                blocked = {
                    event_id
                    for event_id in family["evidence_event_ids"]
                    if events[event_id]["modality"] in CHANNEL_MODALITIES[family["blocked_channel"]]
                }
            if not blocked or any(not blocked.intersection(route) for route in family["accepted_ses"]):
                raise ValueError(f"{family_id} block does not hit every accepted SES")


def _selected_sources(config: dict[str, Any], mode: str) -> list[dict[str, Any]]:
    if mode == "quick":
        return config["sources"][:1]
    if mode == "full":
        return config["sources"]
    raise ValueError(f"unknown generation mode: {mode}")


def _metadata_digest(paths: Iterable[Path], root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: str(item.relative_to(root))):
        relative = str(path.relative_to(root)).replace("\\", "/")
        digest.update(relative.encode("utf-8") + b"\0")
        digest.update(path.read_bytes())
    return "sha256:" + digest.hexdigest()


def generate_corpus(
    *,
    config_path: str | Path,
    output_dir: str | Path,
    mode: str = "full",
    seed: int = 20260905,
    clean: bool = True,
    repository_root: str | Path | None = None,
) -> GenerationResult:
    """Generate and validate a deterministic quick or full synthetic corpus."""

    started = time.perf_counter()
    config_path = Path(config_path)
    output_dir = Path(output_dir)
    config = _load_config(config_path)
    _validate_config(config)
    sources = _selected_sources(config, mode)
    if clean and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    registry = SchemaRegistry(repository_root)
    metadata_paths: list[Path] = []
    mp4_hashes: dict[str, str] = {}
    family_count = 0
    episode_count = 0
    family_summaries = []

    for source_index, source in enumerate(sources):
        source_id = source["source_id"]
        media_path = output_dir / "media" / f"{source_id}.mp4"
        _write_mp4(media_path, source, config["media"], seed + source_index * 1000)
        mp4_hashes[source_id] = _sha256_file(media_path)

        records = [
            ("timeline", "annotation", output_dir / "timelines" / f"{source_id}.json", _timeline(source)),
            ("transcript", "transcript", output_dir / "transcripts" / f"{source_id}.json", _transcript(source)),
            ("audio_events", "annotation", output_dir / "audio_events" / f"{source_id}.json", _audio_labels(source)),
            ("evidence", "annotation", output_dir / "evidence" / f"{source_id}.json", _evidence_records(source)),
        ]
        artifact_specs: list[tuple[str, str, Path, str]] = []
        for label, artifact_type, path, value in records:
            _write_json(path, value)
            metadata_paths.append(path)
            artifact_specs.append((f"{label}_{source_id}", artifact_type, path, _sha256_file(path)))

        manifest = _manifest(source, media_path, artifact_specs, output_dir)
        manifest_report = validate_manifest_gate(manifest, GateProfile.PUBLIC_RELEASE, registry)
        if not manifest_report.ok:
            raise ValueError(f"manifest validation failed for {source_id}: {manifest_report.to_dict()}")
        manifest_path = output_dir / "manifests" / f"{source_id}.json"
        _write_json(manifest_path, manifest)
        metadata_paths.append(manifest_path)

        for family_spec in source["families"]:
            family = _family(source, family_spec, manifest, seed)
            report = validate_family(family, manifest, registry)
            if not report.ok:
                raise ValueError(f"family validation failed for {family_spec['family_id']}: {report.to_dict()}")
            family_path = output_dir / "families" / f"{family_spec['family_id']}.json"
            _write_json(family_path, family)
            metadata_paths.append(family_path)
            family_count += 1
            episode_count += len(family["episodes"])
            modalities = sorted(
                {unit["modality"] for unit in family["claim_evidence_graph"]["evidence_units"]}
            )
            family_summaries.append(
                {
                    "family_id": family["family_id"],
                    "source_id": source_id,
                    "mechanism": family["intervention_mechanism"],
                    "modalities": modalities,
                    "cross_modal": len(modalities) > 1,
                    "accepted_ses_count": len(family["claim_evidence_graph"]["accepted_sufficient_sets"]),
                    "episode_ids": [episode["episode_id"] for episode in family["episodes"]],
                    "path": str(family_path.relative_to(output_dir)).replace("\\", "/"),
                }
            )

    corpus_index = {
        "schema_version": "1.0",
        "generator_version": GENERATOR_VERSION,
        "mode": mode,
        "seed": seed,
        "created_at": FIXED_TIMESTAMP,
        "ownership": "synthetic_project_owned",
        "mp4_byte_identity_guarantee": "same pinned PyAV/FFmpeg/codec build only; not guaranteed across encoder builds",
        "schema_hashes": {
            name: registry.schema_hash(name)
            for name in ("episode-family", "acquisition-manifest")
        },
        "counts": {
            "sources": len(sources),
            "families": family_count,
            "episodes": episode_count,
            "cross_modal_families": sum(item["cross_modal"] for item in family_summaries),
        },
        "sources": [
            {
                "source_id": source["source_id"],
                "duration_s": source["duration_s"],
                "media_path": f"media/{source['source_id']}.mp4",
                "media_sha256": mp4_hashes[source["source_id"]],
                "manifest_path": f"manifests/{source['source_id']}.json",
            }
            for source in sources
        ],
        "families": family_summaries,
    }
    index_path = output_dir / "corpus_index.json"
    _write_json(index_path, corpus_index)
    metadata_paths.append(index_path)
    metadata_sha256 = _metadata_digest(metadata_paths, output_dir)
    report = {
        "schema_version": "1.0",
        "generator_version": GENERATOR_VERSION,
        "mode": mode,
        "seed": seed,
        "metadata_sha256": metadata_sha256,
        "schema_hashes": corpus_index["schema_hashes"],
        "counts": corpus_index["counts"],
        "validation": {
            "manifests": "PASS",
            "episode_families": "PASS",
            "validator_api": "av_trace.validate_manifest_gate + av_trace.validate_family",
        },
    }
    report_path = output_dir / "generation_report.json"
    _write_json(report_path, report)
    total_bytes = sum(path.stat().st_size for path in output_dir.rglob("*") if path.is_file())
    return GenerationResult(
        output_dir=output_dir,
        source_count=len(sources),
        family_count=family_count,
        episode_count=episode_count,
        total_bytes=total_bytes,
        metadata_sha256=metadata_sha256,
        elapsed_s=time.perf_counter() - started,
        mp4_hashes=mp4_hashes,
    )


def probe_mp4(path: str | Path) -> dict[str, Any]:
    """Return a small playability probe used by tests and the CLI."""

    path = Path(path)
    with av.open(str(path)) as container:
        video = next((stream for stream in container.streams if stream.type == "video"), None)
        audio = next((stream for stream in container.streams if stream.type == "audio"), None)
        if video is None or audio is None:
            raise ValueError(f"{path} must contain both video and audio streams")
        video_frames = 0
        audio_frames = 0
        for packet in container.demux(video, audio):
            for frame in packet.decode():
                if isinstance(frame, av.VideoFrame):
                    video_frames += 1
                elif isinstance(frame, av.AudioFrame):
                    audio_frames += 1
                if video_frames and audio_frames:
                    break
            if video_frames and audio_frames:
                break
        if not video_frames or not audio_frames:
            raise ValueError(f"{path} did not decode both stream types")
        duration_s = float(container.duration / av.time_base) if container.duration is not None else None
        return {
            "path": str(path),
            "duration_s": duration_s,
            "has_video": True,
            "has_audio": True,
            "video_codec": video.codec_context.name,
            "audio_codec": audio.codec_context.name,
        }
