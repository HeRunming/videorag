"""Fixed-backend adapter whose citable content is decoded from MP4 bytes."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from av_trace.util import sha256_json
from av_trace_media.adapters import MediaPerception
from av_trace_media.types import TimeInterval
from av_trace_mvp.backend import FixedBackend
from av_trace_mvp.index import BackendManifest, FixedIndex, IndexRecord

from .indexing import project_observation, semantic_tokens


@dataclass(frozen=True)
class MediaRegistration:
    asset_id: str
    path: Path
    media_hash: str


class MediaBackedBackend(FixedBackend):
    """Preserve fixed control semantics while replacing content tools with decode."""

    def __init__(
        self,
        family: dict[str, Any],
        state_role: str,
        certified_index: FixedIndex,
        manifest: BackendManifest,
        *,
        media_index: FixedIndex,
        media: MediaRegistration,
        registry: Any | None = None,
    ) -> None:
        super().__init__(family, state_role, certified_index, manifest, registry)
        if media.asset_id != family["source"]["asset_id"]:
            raise ValueError("Media registration asset does not match family source.")
        self.media_index = media_index
        self.media = media
        self.perception = MediaPerception.synthetic(str(media.path), media.media_hash)
        self._media_records = media_index.for_asset(media.asset_id)
        if not self._media_records:
            raise ValueError(f"No media-derived index records for {media.asset_id}.")

    def _search(
        self,
        tool: str,
        channel: str,
        modality: str,
        arguments: dict[str, Any],
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any] | None]:
        if not self.interventions.channel_available(channel):
            return self._unavailable(channel)
        ranked = self.media_index.search(
            records=self.interventions.visible_records(self._media_records),
            modality=modality,
            query=arguments["query"],
            interval=arguments["time_range"],
            top_k=arguments["top_k"],
            excluded_result_ids=arguments["exclude_result_ids"],
            speaker_hint=arguments.get("speaker_hint"),
        )
        results = [
            {
                "result_type": "search_pointer",
                "result_id": record.result_id,
                "interval": deepcopy(record.interval),
                "score": score,
                "preview": record.preview,
            }
            for record, score in ranked
        ]
        if not results:
            return "not_found", [], self._error(
                "NO_RESULTS", False, "No accessible media-derived result matched."
            )
        return "ok", results, None

    def _evidence_matches(
        self,
        modality: str,
        interval: Mapping[str, float],
        payload: Mapping[str, Any],
    ) -> list[str]:
        observed_tokens = semantic_tokens(
            " ".join(
                str(payload.get(key, ""))
                for key in ("description", "text", "audio_event")
            )
        )
        matches: list[str] = []
        for evidence in self.family["claim_evidence_graph"]["evidence_units"]:
            if evidence["modality"] != modality:
                continue
            covers = any(
                interval["start_s"] <= target["start_s"] + 1e-6
                and interval["end_s"] >= target["end_s"] - 1e-6
                for target in evidence["intervals"]
            )
            expected_tokens = semantic_tokens(evidence["observation"])
            # This comparison is evaluator-private. It may reject a decoded
            # observation that no longer agrees with the registered evidence,
            # but it never supplies or rewrites public observation content.
            if covers and observed_tokens and observed_tokens <= expected_tokens:
                matches.append(evidence["evidence_id"])
        return matches

    def _route_visible(self, evidence_ids: list[str]) -> bool:
        if not evidence_ids:
            return True
        visible = {
            evidence_id
            for record in self.interventions.visible_records(self._media_records)
            for evidence_id in record.route_evidence_ids
        }
        return set(evidence_ids) <= visible

    def _media_observation(self, raw: Mapping[str, Any], *, prefix: str) -> dict[str, Any] | None:
        modality = raw["modality"]
        interval = {
            "start_s": round(float(raw["interval"]["start_s"]), 6),
            "end_s": round(float(raw["interval"]["end_s"]), 6),
        }
        payload = project_observation(raw)
        evidence_ids = self._evidence_matches(modality, interval, payload)
        if not self._route_visible(evidence_ids):
            return None
        payload["_route_refs"] = [
            sha256_json({"evidence_id": evidence_id})
            for evidence_id in sorted(evidence_ids)
        ]
        identity = sha256_json(
            {
                "prefix": prefix,
                "asset_id": self.media.asset_id,
                "media_hash": self.media.media_hash,
                "modality": modality,
                "interval": interval,
                "payload": payload,
            }
        ).split(":", 1)[1]
        return {
            "result_type": "observation",
            "observation_id": f"obs.{prefix}.{identity}",
            "interval": interval,
            "modalities": [modality],
            "payload": payload,
            "payload_hash": sha256_json(payload),
        }

    def _read_transcript(
        self, arguments: dict[str, Any]
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any] | None]:
        raw = self.perception.read_transcript(
            TimeInterval(arguments["interval"]["start_s"], arguments["interval"]["end_s"])
        )
        results = [
            converted
            for item in raw["observations"]
            if (converted := self._media_observation(item, prefix="media.transcript")) is not None
        ]
        if not results:
            return "not_found", [], self._error(
                "NO_RESULTS", False, "Decoded audio produced no matching speech observation."
            )
        return "ok", results, None

    def _inspect_clip(
        self, arguments: dict[str, Any]
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any] | None]:
        if not self.interventions.channel_available("clip"):
            return self._unavailable("clip")
        include_video = bool(arguments["include_video"])
        include_audio = bool(arguments["include_audio"])
        enabled_video = include_video and self.interventions.channel_available("visual")
        speech_present = any(record.modality == "speech" for record in self._media_records)
        ambient_present = any(record.modality == "ambient" for record in self._media_records)
        enabled_speech = include_audio and speech_present and self.interventions.channel_available("speech")
        enabled_ambient = include_audio and ambient_present and self.interventions.channel_available("ambient")
        unavailable = (
            (include_video and not enabled_video)
            or (include_audio and speech_present and not enabled_speech)
            or (include_audio and ambient_present and not enabled_ambient)
        )
        if not enabled_video and not enabled_speech and not enabled_ambient:
            return self._unavailable("visual" if include_video else "speech")

        interval = TimeInterval(
            arguments["interval"]["start_s"], arguments["interval"]["end_s"]
        )
        inspected = round(interval.duration_s, 6)
        self._inspected_duration_s = round(self._inspected_duration_s + inspected, 6)
        raw = self.perception.inspect_clip(
            interval,
            include_video=enabled_video,
            include_audio=enabled_speech or enabled_ambient,
        )
        allowed = set()
        if enabled_video:
            allowed.add("vision")
        if enabled_speech:
            allowed.add("speech")
        if enabled_ambient:
            allowed.add("ambient")
        results = []
        for item in raw["observations"]:
            if item["modality"] not in allowed:
                continue
            converted = self._media_observation(item, prefix="media.clip")
            if converted is not None:
                converted["payload"]["inspection"] = {
                    "requested_interval": arguments["interval"],
                    "include_video": include_video,
                    "include_audio": include_audio,
                    "inspected_duration_s": inspected,
                }
                converted["payload_hash"] = sha256_json(converted["payload"])
                results.append(converted)
        results.sort(
            key=lambda item: (
                item["interval"]["start_s"],
                item["modalities"],
                item["observation_id"],
            )
        )
        if not results:
            return "not_found", [], self._error(
                "NO_RESULTS", False, "Decoded media produced no accessible observation."
            )
        return ("partial" if unavailable else "ok"), results, None
