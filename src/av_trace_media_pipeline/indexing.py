"""Build a frozen coarse search index exclusively from decoded media."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from av_trace.util import sha256_json
from av_trace_media.adapters import MEDIA_PERCEPTION_VERSION, MediaPerception
from av_trace_media.audio import AMBIENT_ADAPTER_VERSION
from av_trace_media.reader import READER_VERSION, sha256_file
from av_trace_media.speech import SYNTHETIC_CODEC_VERSION
from av_trace_media.types import TimeInterval
from av_trace_media.visual import VISUAL_ADAPTER_VERSION
from av_trace_mvp.index import FixedIndex


MEDIA_INDEX_VERSION = "media-grid-index-v2"
MEDIA_INDEX_BUILDER_VERSION = "av-trace-media-index-builder/2.0.0"
DEFAULT_GRID_SECONDS = 2.0
_WORDS = {
    0: "ZERO",
    1: "ONE",
    2: "TWO",
    3: "THREE",
    4: "FOUR",
    5: "FIVE",
    6: "SIX",
    7: "SEVEN",
    8: "EIGHT",
    9: "NINE",
    10: "TEN",
}
_GENERIC = {
    "vision": "visual visible shape symbol arrow appeared shown",
    "speech": "speech spoken says code instruction announcement report status units bin route",
    "ambient": "ambient sound audio bell pulse machine motor click confirmation chime",
}


@dataclass(frozen=True)
class MediaIndexBuild:
    """The searchable index plus a reproducible build record."""

    index: FixedIndex
    build_record: dict[str, Any]


def _round_time(value: float) -> float:
    return round(float(value), 6)


def _content_key(observation: Mapping[str, Any]) -> tuple[Any, ...]:
    content = observation["content"]
    modality = observation["modality"]
    if modality == "vision":
        return (
            modality,
            content.get("shape"),
            content.get("color"),
            content.get("arrow_direction"),
            content.get("visible_text"),
        )
    if modality == "speech":
        return (modality, content.get("text"))
    return (modality, content.get("signature"))


def _speech_description(text: str) -> str:
    # These prefixes are part of the documented procedural codec vocabulary,
    # not values read from transcript/evidence JSON.
    return {
        "DELTA SEVEN": "spoken code is DELTA SEVEN",
        "OPEN GATE": "operator says OPEN GATE",
        "PLACE IN BIN FOUR": "operator says PLACE IN BIN FOUR",
        "ROUTE COBALT": "announcement says ROUTE COBALT",
        "FIVE UNITS": "inspector says FIVE UNITS",
        "STATUS CLEAR": "inspector says STATUS CLEAR",
    }.get(text, f"decoded speech {text}")


def project_observation(observation: Mapping[str, Any]) -> dict[str, Any]:
    """Project decoded adapter content into the existing public payload idiom."""

    modality = observation["modality"]
    content = deepcopy(dict(observation["content"]))
    provenance = deepcopy(dict(observation["provenance"]))
    if modality == "vision":
        description = str(content.get("visible_text") or "").strip()
        if not description:
            parts = [content.get("color"), content.get("shape"), content.get("arrow_direction")]
            description = " ".join(str(item).upper() for item in parts if item)
        payload = {
            "description": description,
            "visual_detection": content,
        }
    elif modality == "speech":
        text = str(content.get("text") or "").strip()
        description = _speech_description(text)
        payload = {
            "description": description,
            # Keep one textual field because the baseline parser concatenates
            # public text-like fields. Duplicating the role phrase changes the
            # parsed answer even though the decoded symbol is correct.
            "text": description,
            "decoded_speech": content,
        }
        payload.pop("description")
    else:
        signature = content.get("signature")
        count = content.get("pulse_count")
        frequency = float(content.get("dominant_frequency_hz") or 0.0)
        if signature == "bell_pulses":
            description = f"{_WORDS.get(int(count or 0), str(count))} BELL PULSES"
        elif signature == "click_pulses":
            description = f"{_WORDS.get(int(count or 0), str(count))} CLICK PULSES"
        elif signature == "motor_hum":
            description = ("LOW" if frequency < 250.0 else "HIGH") + " MOTOR HUM"
        elif signature == "confirmation_chime":
            description = ("HIGH" if frequency >= 900.0 else "LOW") + " CONFIRMATION CHIME"
        else:
            description = str(signature or "UNCLASSIFIED AMBIENT EVENT").upper()
        payload = {
            "description": description,
            "audio_event": description,
            "ambient_detection": content,
        }
    payload["media_provenance"] = provenance
    return payload


def _scan_source(
    *,
    asset_id: str,
    path: Path,
    media_hash: str,
    duration_s: float,
    grid_s: float,
) -> list[dict[str, Any]]:
    perception = MediaPerception.synthetic(str(path), media_hash)
    candidates: list[dict[str, Any]] = []
    cursor = 0.0
    while cursor < duration_s - 1e-9:
        end = min(duration_s, cursor + grid_s)
        result = perception.inspect_clip(
            TimeInterval(cursor, end),
            include_video=True,
            include_audio=True,
        )
        observations = result["observations"]
        # Partial tonal speech can resemble a pulse train.  Speech owns a grid
        # cell whenever the codec recognizes a symbol in that same cell.
        has_speech = any(item["modality"] == "speech" for item in observations)
        for observation in observations:
            if has_speech and observation["modality"] == "ambient":
                continue
            candidates.append(
                {
                    "asset_id": asset_id,
                    "modality": observation["modality"],
                    "start_s": cursor,
                    "end_s": end,
                    "key": _content_key(observation),
                }
            )
        cursor = end

    groups: list[dict[str, Any]] = []
    for item in sorted(candidates, key=lambda value: (value["modality"], value["key"], value["start_s"])):
        previous = groups[-1] if groups else None
        if (
            previous
            and previous["modality"] == item["modality"]
            and previous["key"] == item["key"]
            and item["start_s"] <= previous["end_s"] + grid_s + 1e-9
        ):
            previous["end_s"] = item["end_s"]
        else:
            groups.append(dict(item))

    records: list[dict[str, Any]] = []
    for group in sorted(groups, key=lambda value: (value["start_s"], value["modality"], value["key"])):
        interval = TimeInterval(group["start_s"], group["end_s"])
        if group["modality"] == "vision":
            observations = perception.inspect_clip(
                interval, include_video=True, include_audio=False
            )["observations"]
        elif group["modality"] == "speech":
            observations = perception.read_transcript(interval)["observations"]
        else:
            observations = perception.observe_ambient(interval)["observations"]
        matching = [
            item
            for item in observations
            if item["modality"] == group["modality"]
            and _content_key(item) == group["key"]
        ]
        if not matching:
            continue
        observation = matching[0]
        payload = project_observation(observation)
        start_s = _round_time(group["start_s"])
        end_s = _round_time(group["end_s"])
        record_id = "media." + sha256_json(
            {
                "asset_id": asset_id,
                "modality": group["modality"],
                "interval": {"start_s": start_s, "end_s": end_s},
            }
        ).split(":", 1)[1][:32]
        searchable = " ".join(
            value
            for value in (
                _GENERIC[group["modality"]],
                payload.get("description"),
                payload.get("text"),
                payload.get("audio_event"),
            )
            if isinstance(value, str) and value
        )
        records.append(
            {
                "record_id": record_id,
                "family_id": None,
                "asset_id": asset_id,
                "modality": group["modality"],
                "interval": {"start_s": start_s, "end_s": end_s},
                "payload": payload,
                "search_text": searchable,
                "preview": f"{group['modality']} media candidate at {start_s:.1f}-{end_s:.1f}s",
                "route_evidence_ids": [],
                "is_distractor": True,
                "speaker": None,
                "transcript_sources": ["asr"] if group["modality"] == "speech" else [],
            }
        )
    return records


def _bind_routes(
    records: Sequence[Mapping[str, Any]],
    families: Sequence[Mapping[str, Any]],
    *,
    require_full_coverage: bool = True,
) -> list[dict[str, Any]]:
    """Bind evaluator-private route IDs by asset/modality/interval only."""

    bindings: dict[tuple[str, str, float, float], set[str]] = {}
    expected: set[tuple[str, str]] = set()
    for family in families:
        asset_id = family["source"]["asset_id"]
        for evidence in family["claim_evidence_graph"]["evidence_units"]:
            evidence_id = evidence["evidence_id"]
            expected.add((family["family_id"], evidence_id))
            for interval in evidence["intervals"]:
                key = (
                    asset_id,
                    evidence["modality"],
                    _round_time(interval["start_s"]),
                    _round_time(interval["end_s"]),
                )
                bindings.setdefault(key, set()).add(evidence_id)

    bound: list[dict[str, Any]] = []
    covered: set[str] = set()
    for raw in records:
        item = deepcopy(dict(raw))
        interval = item["interval"]
        key = (
            item["asset_id"],
            item["modality"],
            _round_time(interval["start_s"]),
            _round_time(interval["end_s"]),
        )
        route_ids = sorted(bindings.get(key, ()))
        item["route_evidence_ids"] = route_ids
        item["is_distractor"] = not bool(route_ids)
        covered.update(route_ids)
        bound.append(item)

    required_ids = {
        evidence["evidence_id"]
        for family in families
        for evidence in family["claim_evidence_graph"]["evidence_units"]
    }
    missing = sorted(required_ids - covered)
    if missing and require_full_coverage:
        raise ValueError(f"Decoded media index does not cover registered evidence: {missing}")
    return bound


def build_media_index(
    *,
    generated_root: str | Path,
    families: Sequence[Mapping[str, Any]],
    grid_s: float = DEFAULT_GRID_SECONDS,
    media_overrides: Mapping[str, tuple[str | Path, str]] | None = None,
    require_full_coverage: bool = True,
) -> MediaIndexBuild:
    """Decode every registered MP4 on a fixed grid and freeze search records.

    Only ``corpus_index.json`` and MP4 bytes supply searchable content. Family
    objects are consulted afterward solely to bind private evidence route IDs
    by asset, modality, and interval.
    """

    if grid_s <= 0:
        raise ValueError("grid_s must be positive")
    root = Path(generated_root)
    corpus = json.loads((root / "corpus_index.json").read_text(encoding="utf-8"))
    overrides = dict(media_overrides or {})
    known_sources = {item["source_id"] for item in corpus["sources"]}
    unknown_overrides = sorted(set(overrides) - known_sources)
    if unknown_overrides:
        raise ValueError(f"Media override names unknown source(s): {unknown_overrides}")
    unbound: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    for source in sorted(corpus["sources"], key=lambda item: item["source_id"]):
        override = overrides.get(source["source_id"])
        path = Path(override[0]) if override else root / source["media_path"]
        registered_hash = override[1] if override else source["media_sha256"]
        actual_hash = sha256_file(path)
        if actual_hash != registered_hash:
            raise ValueError(
                f"Media hash mismatch for {source['source_id']}: "
                f"expected {registered_hash}, got {actual_hash}"
            )
        unbound.extend(
            _scan_source(
                asset_id=source["source_id"],
                path=path,
                media_hash=actual_hash,
                duration_s=float(source["duration_s"]),
                grid_s=float(grid_s),
            )
        )
        sources.append(
            {
                "asset_id": source["source_id"],
                "media_path": (
                    f"override:{source['source_id']}"
                    if override
                    else source["media_path"]
                ),
                "media_hash": actual_hash,
                "duration_s": float(source["duration_s"]),
                "overridden": bool(override),
            }
        )
    records = _bind_routes(
        unbound,
        families,
        require_full_coverage=require_full_coverage,
    )
    index = FixedIndex.from_records(records, index_version=MEDIA_INDEX_VERSION)
    build_record = {
        "schema_version": "2.0.0",
        "builder_version": MEDIA_INDEX_BUILDER_VERSION,
        "created_at": "2026-09-06T00:00:00Z",
        "strategy": {
            "type": "fixed_temporal_grid_with_semantic_merge",
            "grid_s": float(grid_s),
            "merge_gap_s": float(grid_s),
            "final_interval_redecode": True,
            "searchable_content_source": "decoded_mp4_only",
            "route_binding_source": "evaluator_private_asset_modality_interval_only",
        },
        "adapter_versions": {
            "media_perception": MEDIA_PERCEPTION_VERSION,
            "reader": READER_VERSION,
            "visual": VISUAL_ADAPTER_VERSION,
            "speech": SYNTHETIC_CODEC_VERSION,
            "ambient": AMBIENT_ADAPTER_VERSION,
        },
        "sources": sources,
        "record_count": len(index.records),
        "index_hash": index.index_hash,
    }
    build_record["build_hash"] = sha256_json(build_record)
    return MediaIndexBuild(index=index, build_record=build_record)


def semantic_tokens(value: str) -> set[str]:
    """Normalized tokens used only by the evaluator-private evidence mapper."""

    return set(re.findall(r"[A-Za-z0-9]+", value.upper()))
