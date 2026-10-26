"""Fail-closed, interval-bounded PyAV media decoding."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable

import av
import numpy as np

from .types import DecodedAudio, DecodedMedia, DecodedVideoFrame, TimeInterval


READER_VERSION = "pyav-interval-reader/1.0.0"


class MediaReadError(RuntimeError):
    """Base class for a media registration or decode failure."""


class MediaIntegrityError(MediaReadError):
    """The media bytes do not match the registered hash."""


class MediaDecodeError(MediaReadError):
    """The requested media channels could not be decoded completely."""


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _merge_coverage(
    intervals: Iterable[TimeInterval],
    *,
    tolerance_s: float,
) -> tuple[TimeInterval, ...]:
    merged: list[TimeInterval] = []
    for item in sorted(intervals):
        if merged and item.start_s <= merged[-1].end_s + tolerance_s:
            merged[-1] = TimeInterval(merged[-1].start_s, max(merged[-1].end_s, item.end_s))
        else:
            merged.append(item)
    return tuple(merged)


def _assert_complete(
    coverage: tuple[TimeInterval, ...],
    requested: TimeInterval,
    *,
    tolerance_s: float,
    channel: str,
) -> None:
    if not coverage:
        raise MediaDecodeError(f"{channel} produced no decoded coverage")
    if coverage[0].start_s > requested.start_s + tolerance_s:
        raise MediaDecodeError(f"{channel} decode starts after the requested interval")
    if coverage[-1].end_s < requested.end_s - tolerance_s:
        raise MediaDecodeError(f"{channel} decode ends before the requested interval")
    for left, right in zip(coverage, coverage[1:]):
        if right.start_s > left.end_s + tolerance_s:
            raise MediaDecodeError(f"{channel} decode has an uncovered gap")


class PyAVMediaReader:
    """Read only a requested source-time interval from registered media.

    Seeking can require codec keyframe pre-roll, but pre-roll frames/samples are
    never returned.  Coverage records are the exact clipped source-time spans
    represented by returned decoded frames and samples.
    """

    version = READER_VERSION

    def __init__(self, media_path: str | Path, registered_hash: str) -> None:
        self.path = Path(media_path)
        self.registered_hash = registered_hash
        if not registered_hash.startswith("sha256:") or len(registered_hash) != 71:
            raise MediaIntegrityError("registered media hash must be a sha256: digest")

    def validate_hash(self) -> str:
        if not self.path.is_file():
            raise MediaIntegrityError(f"registered media is missing: {self.path}")
        actual = sha256_file(self.path)
        if actual != self.registered_hash:
            raise MediaIntegrityError(
                f"registered media hash mismatch: expected {self.registered_hash}, got {actual}"
            )
        return actual

    def read(
        self,
        interval: TimeInterval,
        *,
        include_video: bool,
        include_audio: bool,
    ) -> DecodedMedia:
        if not include_video and not include_audio:
            raise ValueError("at least one media channel must be requested")
        media_hash = self.validate_hash()
        video_frames: list[DecodedVideoFrame] = []
        video_spans: list[TimeInterval] = []
        audio_parts: list[np.ndarray] = []
        audio_spans: list[TimeInterval] = []
        audio_source_frames: list[TimeInterval] = []
        sample_rate: int | None = None

        if include_video:
            video_frames, video_spans = self._read_video(interval)
        if include_audio:
            audio_parts, audio_spans, audio_source_frames, sample_rate = self._read_audio(interval)

        video_coverage = _merge_coverage(video_spans, tolerance_s=1e-6)
        audio_tolerance = 1.0 / sample_rate if sample_rate else 1e-6
        audio_coverage = _merge_coverage(audio_spans, tolerance_s=audio_tolerance)
        if include_video:
            _assert_complete(video_coverage, interval, tolerance_s=1e-6, channel="video")
        if include_audio:
            _assert_complete(audio_coverage, interval, tolerance_s=audio_tolerance, channel="audio")

        decoded_audio = None
        if include_audio and sample_rate is not None:
            samples = np.concatenate(audio_parts).astype(np.float32, copy=False)
            if samples.size == 0:
                raise MediaDecodeError("audio produced no samples")
            decoded_audio = DecodedAudio(
                interval=TimeInterval(audio_coverage[0].start_s, audio_coverage[-1].end_s),
                sample_rate=sample_rate,
                samples=samples,
                source_frame_intervals=tuple(audio_source_frames),
            )

        return DecodedMedia(
            media_path=str(self.path),
            media_hash=media_hash,
            requested_interval=interval,
            video_coverage=video_coverage,
            audio_coverage=audio_coverage,
            video_frames=tuple(video_frames),
            audio=decoded_audio,
        )

    def _read_video(
        self,
        interval: TimeInterval,
    ) -> tuple[list[DecodedVideoFrame], list[TimeInterval]]:
        frames: list[DecodedVideoFrame] = []
        spans: list[TimeInterval] = []
        try:
            with av.open(str(self.path), mode="r") as container:
                video = next((s for s in container.streams if s.type == "video"), None)
                if video is None:
                    raise MediaDecodeError("registered media has no video stream")
                self._decode_video(container, video, interval, frames, spans)
        except MediaReadError:
            raise
        except (EOFError, OSError, ValueError) as exc:
            raise MediaDecodeError(f"PyAV could not decode registered media: {exc}") from exc
        except Exception as exc:
            # PyAV's exception hierarchy has changed across supported releases;
            # convert any library decode exception to the stable fail-closed
            # public error rather than exposing partial observations.
            raise MediaDecodeError(f"PyAV could not decode registered media: {exc}") from exc
        return frames, spans

    def _read_audio(
        self,
        interval: TimeInterval,
    ) -> tuple[list[np.ndarray], list[TimeInterval], list[TimeInterval], int]:
        parts: list[np.ndarray] = []
        spans: list[TimeInterval] = []
        source_frames: list[TimeInterval] = []
        try:
            with av.open(str(self.path), mode="r") as container:
                audio = next((s for s in container.streams if s.type == "audio"), None)
                if audio is None:
                    raise MediaDecodeError("registered media has no audio stream")
                rate = self._decode_audio(container, audio, interval, parts, spans, source_frames)
        except MediaReadError:
            raise
        except (EOFError, OSError, ValueError) as exc:
            raise MediaDecodeError(f"PyAV could not decode registered media: {exc}") from exc
        except Exception as exc:
            raise MediaDecodeError(f"PyAV could not decode registered media: {exc}") from exc
        return parts, spans, source_frames, rate

    @staticmethod
    def _seek(container: av.container.InputContainer, stream: av.stream.Stream, start_s: float) -> None:
        # One second of bounded pre-roll handles AAC priming and ordinary GOPs.
        target_s = max(0.0, start_s - 1.0)
        target = int(target_s / float(stream.time_base))
        container.seek(target, stream=stream, backward=True, any_frame=False)

    def _decode_video(
        self,
        container: av.container.InputContainer,
        stream: av.video.stream.VideoStream,
        requested: TimeInterval,
        output: list[DecodedVideoFrame],
        spans: list[TimeInterval],
    ) -> None:
        self._seek(container, stream, requested.start_s)
        default_duration = (
            1.0 / float(stream.average_rate)
            if stream.average_rate is not None and float(stream.average_rate) > 0
            else None
        )
        for frame in container.decode(stream):
            if frame.pts is None:
                raise MediaDecodeError("video frame is missing PTS")
            start = float(frame.pts * frame.time_base)
            duration = (
                float(frame.duration * frame.time_base)
                if frame.duration is not None and frame.duration > 0
                else default_duration
            )
            if duration is None or duration <= 0:
                raise MediaDecodeError("video frame duration is unavailable")
            end = start + duration
            if start >= requested.end_s:
                break
            clipped = TimeInterval(max(start, requested.start_s), min(end, requested.end_s)) if end > requested.start_s else None
            if clipped is None:
                continue
            rgb = frame.to_ndarray(format="rgb24")
            output.append(
                DecodedVideoFrame(
                    interval=clipped,
                    pts=int(frame.pts),
                    time_base=str(frame.time_base),
                    rgb=rgb,
                )
            )
            spans.append(clipped)

    def _decode_audio(
        self,
        container: av.container.InputContainer,
        stream: av.audio.stream.AudioStream,
        requested: TimeInterval,
        output: list[np.ndarray],
        spans: list[TimeInterval],
        source_frames: list[TimeInterval],
    ) -> int:
        self._seek(container, stream, requested.start_s)
        rate: int | None = None
        for frame in container.decode(stream):
            if frame.pts is None or not frame.sample_rate:
                raise MediaDecodeError("audio frame is missing timing metadata")
            frame_rate = int(frame.sample_rate)
            if rate is None:
                rate = frame_rate
            elif rate != frame_rate:
                raise MediaDecodeError("audio sample rate changes inside the request")
            start = float(frame.pts * frame.time_base)
            array = frame.to_ndarray()
            if array.ndim == 2:
                array = array.astype(np.float64).mean(axis=0)
            else:
                array = array.astype(np.float64).reshape(-1)
            if np.issubdtype(frame.to_ndarray().dtype, np.integer):
                bits = frame.to_ndarray().dtype.itemsize * 8
                array /= float(1 << (bits - 1))
            frame_end = start + array.size / frame_rate
            if start >= requested.end_s:
                break
            if frame_end <= requested.start_s:
                continue
            first = max(0, int(np.ceil((requested.start_s - start) * frame_rate - 1e-9)))
            last = min(array.size, int(np.ceil((requested.end_s - start) * frame_rate - 1e-9)))
            if last <= first:
                continue
            selected_start = start + first / frame_rate
            selected_end = start + last / frame_rate
            clipped = TimeInterval(selected_start, selected_end)
            output.append(array[first:last])
            spans.append(clipped)
            source_frames.append(TimeInterval(start, frame_end))
        if rate is None:
            raise MediaDecodeError("audio produced no decodable frames")
        return rate
