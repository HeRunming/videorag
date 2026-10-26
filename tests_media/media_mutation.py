"""Helpers that mutate decoded media without consulting annotation files."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from typing import Callable

import av
import numpy as np


VideoMutation = Callable[[np.ndarray, float], np.ndarray]
AudioMutation = Callable[[np.ndarray, np.ndarray, int, np.ndarray], np.ndarray]


def rewrite_media(
    source: Path,
    destination: Path,
    *,
    interval: tuple[float, float],
    mutate_video: VideoMutation | None = None,
    mutate_audio: AudioMutation | None = None,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    start_s, end_s = interval
    with av.open(str(source)) as input_container, av.open(str(destination), "w") as output_container:
        input_video = input_container.streams.video[0]
        input_audio = input_container.streams.audio[0]
        output_video = output_container.add_stream("libx264", rate=input_video.average_rate or 1)
        output_video.width = input_video.width
        output_video.height = input_video.height
        output_video.pix_fmt = "yuv420p"
        output_video.options = {
            "preset": "ultrafast",
            "crf": "34",
            "threads": "1",
            "x264-params": "scenecut=0:open-gop=0",
        }
        output_audio = output_container.add_stream("aac", rate=input_audio.codec_context.sample_rate)
        output_audio.layout = "mono"
        output_audio.bit_rate = 32000

        for frame in input_container.decode(input_video):
            timestamp = float(frame.pts * frame.time_base)
            rgb = frame.to_ndarray(format="rgb24")
            if mutate_video is not None and start_s <= timestamp < end_s:
                rgb = mutate_video(rgb, timestamp)
            output = av.VideoFrame.from_ndarray(rgb, format="rgb24")
            output.pts = frame.pts
            output.time_base = frame.time_base
            for packet in output_video.encode(output):
                output_container.mux(packet)

        input_container.seek(0, stream=input_audio, backward=True)
        for frame in input_container.decode(input_audio):
            frame_start = float(frame.pts * frame.time_base)
            rate = int(frame.sample_rate)
            array = frame.to_ndarray()
            dtype = array.dtype
            mono = array.astype(np.float64).mean(axis=0) if array.ndim == 2 else array.astype(np.float64)
            if np.issubdtype(dtype, np.integer):
                mono /= float(1 << (dtype.itemsize * 8 - 1))
            times = frame_start + np.arange(mono.size) / rate
            selected = (times >= start_s) & (times < end_s)
            if mutate_audio is not None and selected.any():
                mono = mutate_audio(mono, selected, rate, times)
            integer = np.clip(mono * 32767.0, -32768, 32767).astype(np.int16)
            output = av.AudioFrame.from_ndarray(integer.reshape(1, -1), format="s16", layout="mono")
            output.sample_rate = rate
            output.pts = frame.pts
            output.time_base = Fraction(1, rate)
            for packet in output_audio.encode(output):
                output_container.mux(packet)
        for packet in output_video.encode():
            output_container.mux(packet)
        for packet in output_audio.encode():
            output_container.mux(packet)
    return destination


def blank_frame(rgb: np.ndarray, _timestamp: float) -> np.ndarray:
    return np.zeros_like(rgb)


def mute_audio(
    samples: np.ndarray,
    selected: np.ndarray,
    _rate: int,
    _times: np.ndarray,
) -> np.ndarray:
    result = samples.copy()
    result[selected] = 0.0
    return result


def speech_symbol(frequency_hz: float) -> AudioMutation:
    def mutate(
        samples: np.ndarray,
        selected: np.ndarray,
        rate: int,
        times: np.ndarray,
    ) -> np.ndarray:
        result = samples.copy()
        indexes = np.flatnonzero(selected)
        if not indexes.size:
            return result
        event_time = times[indexes]
        gate = (np.floor(event_time * 6) % 2) == 0
        replacement = gate * 0.20 * np.sin(2 * np.pi * frequency_hz * event_time)
        replacement += (~gate) * 0.14 * np.sin(2 * np.pi * frequency_hz * 1.25 * event_time)
        result[indexes] = replacement
        return result

    return mutate
