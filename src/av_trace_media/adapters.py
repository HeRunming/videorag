"""Media-backed tool-facing adapter composition."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .audio import SyntheticAmbientAdapter
from .reader import PyAVMediaReader
from .speech import SpeechAdapter, SyntheticSpeechCodec
from .types import Observation, TimeInterval
from .visual import SyntheticVisualAdapter


MEDIA_PERCEPTION_VERSION = "media-perception/1.0.0"


@dataclass
class MediaPerception:
    """Compose bounded decoding with independent deterministic adapters."""

    reader: PyAVMediaReader
    visual: SyntheticVisualAdapter
    ambient: SyntheticAmbientAdapter
    speech: SpeechAdapter
    version: str = MEDIA_PERCEPTION_VERSION

    @classmethod
    def synthetic(cls, media_path: str, registered_hash: str) -> "MediaPerception":
        return cls(
            reader=PyAVMediaReader(media_path, registered_hash),
            visual=SyntheticVisualAdapter(),
            ambient=SyntheticAmbientAdapter(),
            speech=SyntheticSpeechCodec(),
        )

    def inspect_clip(
        self,
        interval: TimeInterval,
        *,
        include_video: bool,
        include_audio: bool,
    ) -> dict[str, Any]:
        decoded = self.reader.read(
            interval,
            include_video=include_video,
            include_audio=include_audio,
        )
        observations: list[Observation] = []
        if include_video:
            observations.extend(self.visual.observe(decoded))
        if include_audio and decoded.audio is not None:
            observations.extend(self.ambient.observe(decoded))
            observations.extend(self.speech.transcribe(decoded.audio, media_hash=decoded.media_hash))
        observations.sort(key=lambda item: (item.interval.start_s, item.modality, item.adapter_name))
        return {
            "adapter": "media_perception",
            "adapter_version": self.version,
            "media_hash": decoded.media_hash,
            "requested_interval": interval.to_dict(),
            "decoded_coverage": decoded.exact_coverage(),
            "observations": [item.to_payload() for item in observations],
        }

    def read_transcript(self, interval: TimeInterval) -> dict[str, Any]:
        decoded = self.reader.read(interval, include_video=False, include_audio=True)
        assert decoded.audio is not None
        observations = self.speech.transcribe(decoded.audio, media_hash=decoded.media_hash)
        return {
            "source": getattr(self.speech, "adapter_kind", "unknown"),
            "adapter_version": self.speech.version,
            "media_hash": decoded.media_hash,
            "decoded_interval": decoded.audio.interval.to_dict(),
            "observations": [item.to_payload() for item in observations],
        }

    def observe_ambient(self, interval: TimeInterval) -> dict[str, Any]:
        decoded = self.reader.read(interval, include_video=False, include_audio=True)
        observations = self.ambient.observe(decoded)
        return {
            "adapter_version": self.ambient.version,
            "media_hash": decoded.media_hash,
            "decoded_interval": decoded.audio.interval.to_dict() if decoded.audio else None,
            "observations": [item.to_payload() for item in observations],
        }

