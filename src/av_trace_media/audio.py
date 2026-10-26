"""Deterministic ambient-event perception from decoded waveform samples."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .types import DecodedMedia, Observation, TimeInterval


AMBIENT_ADAPTER_VERSION = "synthetic-waveform-ambient/1.0.0"


def spectral_peaks(samples: np.ndarray, rate: int, count: int = 8) -> list[tuple[float, float]]:
    if samples.size < 16:
        return []
    size = 1 << int(np.ceil(np.log2(samples.size)))
    spectrum = np.abs(np.fft.rfft(samples * np.hanning(samples.size), n=size))
    frequencies = np.fft.rfftfreq(size, d=1.0 / rate)
    spectrum[frequencies < 80.0] = 0.0  # discard the continuous 55 Hz carrier
    indexes = np.argpartition(spectrum, -min(count, spectrum.size))[-min(count, spectrum.size) :]
    indexes = indexes[np.argsort(spectrum[indexes])[::-1]]
    return [(float(frequencies[index]), float(spectrum[index])) for index in indexes]


def dominant_frequency_bands(samples: np.ndarray, rate: int) -> list[dict[str, float | str]]:
    if samples.size < 16:
        return []
    spectrum = np.abs(np.fft.rfft(samples * np.hanning(samples.size))) ** 2
    frequencies = np.fft.rfftfreq(samples.size, d=1.0 / rate)
    definitions = (("low", 80.0, 250.0), ("mid", 250.0, 1000.0), ("high", 1000.0, rate / 2))
    total = float(spectrum[frequencies >= 80.0].sum()) or 1.0
    result = []
    for name, low, high in definitions:
        selected = (frequencies >= low) & (frequencies < high)
        share = float(spectrum[selected].sum() / total)
        if share >= 0.01:
            result.append({"band": name, "low_hz": low, "high_hz": high, "energy_share": round(share, 6)})
    return result


def _window_energy(samples: np.ndarray, rate: int, seconds: float = 0.05) -> tuple[np.ndarray, float]:
    width = max(1, int(round(seconds * rate)))
    count = samples.size // width
    if count == 0:
        return np.empty(0), width / rate
    windows = samples[: count * width].reshape(count, width)
    return np.sqrt(np.mean(windows * windows, axis=1)), width / rate


def _pulse_count(samples: np.ndarray, rate: int) -> tuple[int, float]:
    energy, step = _window_energy(samples, rate)
    if not energy.size:
        return 0, 0.0
    baseline = float(np.percentile(energy, 30))
    active = energy > max(0.025, baseline * 3.0)
    # Close very short compression gaps, then count pulse onsets.
    for index in range(1, active.size - 1):
        if not active[index] and active[index - 1] and active[index + 1]:
            active[index] = True
    onsets = np.flatnonzero(active & np.concatenate(([True], ~active[:-1])))
    return int(onsets.size), float(active.mean())


def _ratio_peak(peaks: list[tuple[float, float]], base: float, ratio: float, tolerance_hz: float = 18.0) -> float:
    target = base * ratio
    candidates = [strength for frequency, strength in peaks if abs(frequency - target) <= tolerance_hz]
    return max(candidates, default=0.0)


@dataclass(frozen=True)
class AmbientDetection:
    signature: str
    pulse_count: int | None
    dominant_frequency_hz: float
    confidence: float


class SyntheticAmbientAdapter:
    """Classify the generator's non-speech acoustic signatures."""

    name = "synthetic_waveform_ambient"
    version = AMBIENT_ADAPTER_VERSION

    def detect(self, samples: np.ndarray, rate: int) -> AmbientDetection | None:
        rms = float(np.sqrt(np.mean(samples * samples))) if samples.size else 0.0
        if rms < 0.012:
            return None
        peaks = spectral_peaks(samples, rate)
        if not peaks:
            return None
        dominant, strength = peaks[0]
        second = peaks[1][1] if len(peaks) > 1 else 0.0
        pulse_count, active_fraction = _pulse_count(samples, rate)

        # Alternating 1.25x tones are reserved for the synthetic speech codec
        # and must not leak into ambient observations.
        if _ratio_peak(peaks, dominant, 1.25) >= strength * 0.35 and 0.35 <= active_fraction <= 1.0:
            return None
        if pulse_count >= 1 and active_fraction < 0.55:
            signature = "bell_pulses" if dominant >= 800.0 else "click_pulses"
            confidence = min(0.99, 0.75 + min(pulse_count, 4) * 0.04 + (1.0 - active_fraction) * 0.1)
            return AmbientDetection(signature, pulse_count, dominant, confidence)
        if dominant < 300.0 and _ratio_peak(peaks, dominant, 2.0) >= strength * 0.20:
            return AmbientDetection("motor_hum", None, dominant, 0.97)
        if dominant >= 900.0 and _ratio_peak(peaks, dominant, 1.5) >= strength * 0.20:
            return AmbientDetection("confirmation_chime", None, dominant, 0.97)
        return None

    def observe(self, decoded: DecodedMedia) -> list[Observation]:
        if decoded.audio is None:
            return []
        detection = self.detect(decoded.audio.samples, decoded.audio.sample_rate)
        if detection is None:
            return []
        return [
            Observation(
                modality="ambient",
                interval=decoded.audio.interval,
                confidence=detection.confidence,
                adapter_name=self.name,
                adapter_version=self.version,
                media_hash=decoded.media_hash,
                decoded_interval=decoded.requested_interval,
                content={
                    "signature": detection.signature,
                    "pulse_count": detection.pulse_count,
                    "dominant_frequency_hz": round(detection.dominant_frequency_hz, 3),
                    "dominant_frequency_bands": dominant_frequency_bands(
                        decoded.audio.samples, decoded.audio.sample_rate
                    ),
                },
            )
        ]

