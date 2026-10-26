"""Versioned speech-adapter interface and synthetic waveform codec."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np

from .audio import spectral_peaks
from .types import DecodedAudio, Observation


SPEECH_INTERFACE_VERSION = "speech-adapter/1.0"
SYNTHETIC_CODEC_VERSION = "synthetic_codec/1.0.0"


@runtime_checkable
class SpeechAdapter(Protocol):
    """Stable interface for synthetic, subtitle, or frozen-ASR implementations."""

    name: str
    version: str
    adapter_kind: str

    def transcribe(self, audio: DecodedAudio, *, media_hash: str) -> list[Observation]:
        """Return speech observations derived from the supplied bounded audio."""


@dataclass(frozen=True)
class SyntheticSymbol:
    frequency_hz: float
    text: str


SYNTHETIC_CODEBOOK = (
    SyntheticSymbol(494.0, "ROUTE COBALT"),
    SyntheticSymbol(523.0, "DELTA SEVEN"),
    SyntheticSymbol(587.0, "PLACE IN BIN FOUR"),
    SyntheticSymbol(622.0, "STATUS CLEAR"),
    SyntheticSymbol(659.0, "OPEN GATE"),
    SyntheticSymbol(784.0, "FIVE UNITS"),
)


class SyntheticSpeechCodec:
    """Decode symbolic tonal speech from waveform.

    This is explicitly a ``synthetic_codec`` and is not represented as ASR.
    The semantic codebook is part of the procedural media format.  A future
    subtitle or frozen-ASR adapter can implement :class:`SpeechAdapter` without
    changing callers or observation provenance.
    """

    name = "synthetic_speech_codec"
    version = SYNTHETIC_CODEC_VERSION
    adapter_kind = "synthetic_codec"
    interface_version = SPEECH_INTERFACE_VERSION

    def transcribe(self, audio: DecodedAudio, *, media_hash: str) -> list[Observation]:
        samples = audio.samples
        rms = float(np.sqrt(np.mean(samples * samples))) if samples.size else 0.0
        if rms < 0.025:
            return []
        peaks = spectral_peaks(samples, audio.sample_rate, count=24)
        if not peaks:
            return []
        max_strength = max(strength for _, strength in peaks) or 1.0
        candidates: list[tuple[SyntheticSymbol, float, float]] = []
        for symbol in SYNTHETIC_CODEBOOK:
            base = max(
                ((strength, frequency) for frequency, strength in peaks if abs(frequency - symbol.frequency_hz) <= 12.0),
                default=(0.0, 0.0),
            )
            alternate = max(
                (
                    (strength, frequency)
                    for frequency, strength in peaks
                    if abs(frequency - symbol.frequency_hz * 1.25) <= 16.0
                ),
                default=(0.0, 0.0),
            )
            score = min(base[0] / max_strength, alternate[0] / max_strength * 1.3)
            candidates.append((symbol, score, base[1]))
        symbol, score, measured = max(candidates, key=lambda item: item[1])
        if score < 0.30:
            return []
        confidence = min(0.99, 0.70 + score * 0.28)
        return [
            Observation(
                modality="speech",
                interval=audio.interval,
                confidence=confidence,
                adapter_name=self.name,
                adapter_version=self.version,
                media_hash=media_hash,
                decoded_interval=audio.interval,
                content={
                    "text": symbol.text,
                    "source": "synthetic_codec",
                    "symbol_frequency_hz": symbol.frequency_hz,
                    "measured_frequency_hz": round(measured, 3),
                    "interface_version": self.interface_version,
                },
            )
        ]

