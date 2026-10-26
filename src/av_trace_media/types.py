"""Typed values shared by the media-backed perception adapters.

The types in this module deliberately contain no annotation identifiers.  A
perception request is registered with a byte hash and a source-time interval;
all observation content is subsequently derived from decoded media.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np


Modality = Literal["vision", "speech", "ambient"]


@dataclass(frozen=True, order=True)
class TimeInterval:
    """A finite half-open source-time interval."""

    start_s: float
    end_s: float

    def __post_init__(self) -> None:
        if not np.isfinite(self.start_s) or not np.isfinite(self.end_s):
            raise ValueError("interval endpoints must be finite")
        if self.start_s < 0 or self.end_s <= self.start_s:
            raise ValueError("interval must satisfy 0 <= start_s < end_s")

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s

    def intersect(self, other: "TimeInterval") -> "TimeInterval | None":
        start = max(self.start_s, other.start_s)
        end = min(self.end_s, other.end_s)
        return TimeInterval(start, end) if end > start else None

    def to_dict(self) -> dict[str, float]:
        return {"start_s": self.start_s, "end_s": self.end_s}


@dataclass(frozen=True)
class DecodedVideoFrame:
    """One decoded RGB frame and the source-time span represented by it."""

    interval: TimeInterval
    pts: int
    time_base: str
    rgb: np.ndarray = field(repr=False, compare=False)


@dataclass(frozen=True)
class DecodedAudio:
    """Contiguous decoded mono samples clipped to a requested interval."""

    interval: TimeInterval
    sample_rate: int
    samples: np.ndarray = field(repr=False, compare=False)
    source_frame_intervals: tuple[TimeInterval, ...] = ()

    @property
    def sample_count(self) -> int:
        return int(self.samples.shape[0])


@dataclass(frozen=True)
class DecodedMedia:
    """A hash-validated, bounded decode result."""

    media_path: str
    media_hash: str
    requested_interval: TimeInterval
    video_coverage: tuple[TimeInterval, ...]
    audio_coverage: tuple[TimeInterval, ...]
    video_frames: tuple[DecodedVideoFrame, ...] = ()
    audio: DecodedAudio | None = None

    def exact_coverage(self) -> dict[str, list[dict[str, float]]]:
        return {
            "video": [item.to_dict() for item in self.video_coverage],
            "audio": [item.to_dict() for item in self.audio_coverage],
        }


@dataclass(frozen=True)
class Observation:
    """A citable observation emitted by a deterministic adapter."""

    modality: Modality
    interval: TimeInterval
    confidence: float
    adapter_name: str
    adapter_version: str
    media_hash: str
    decoded_interval: TimeInterval
    content: dict[str, Any]

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("observation confidence must be in [0, 1]")

    def to_payload(self) -> dict[str, Any]:
        return {
            "modality": self.modality,
            "interval": self.interval.to_dict(),
            "content": self.content,
            "provenance": {
                "media_hash": self.media_hash,
                "decoded_interval": self.decoded_interval.to_dict(),
                "adapter": self.adapter_name,
                "adapter_version": self.adapter_version,
                "observation_confidence": round(self.confidence, 6),
            },
        }

