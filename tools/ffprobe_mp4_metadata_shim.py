#!/usr/bin/env python3
"""Metadata-only ffprobe shim for local, non-fragmented MP4/MOV files.

The shim intentionally implements only the command-line and ISO-BMFF subset
needed by the EPIC P23_102 exact-asset validator.  It never reads ``mdat``
payload bytes and never decodes media samples.
"""

from __future__ import annotations

import json
import os
import stat
import struct
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

MAX_BOX_COUNT = 100_000
MAX_DEPTH = 12
MAX_METADATA_BOX_BYTES = 16 * 1024 * 1024
MAX_READ_CALLS = 200_000


class ProbeError(RuntimeError):
    """A malformed input, unsupported container feature, or CLI error."""


@dataclass(frozen=True)
class Box:
    offset: int
    size: int
    type: bytes
    header_size: int

    @property
    def payload_start(self) -> int:
        return self.offset + self.header_size

    @property
    def end(self) -> int:
        return self.offset + self.size

    def type_string(self) -> str:
        return self.type.decode("latin1")


@dataclass(frozen=True)
class ProbeResult:
    report: dict[str, Any]
    top_level_boxes: tuple[Box, ...]
    bytes_read: int
    largest_read: int
    read_ranges: tuple[tuple[int, int], ...]


class FileReader:
    """Bounded random-access reader with observable metadata-read accounting."""

    def __init__(self, path: Path) -> None:
        self.path = path
        try:
            self._fd = os.open(path, os.O_RDONLY)
        except OSError as exc:
            raise ProbeError(f"cannot open input: {exc.strerror}") from exc
        try:
            info = os.fstat(self._fd)
            if not stat.S_ISREG(info.st_mode):
                raise ProbeError("input is not a regular file")
            if info.st_size < 8:
                raise ProbeError("input is too small to be an ISO-BMFF file")
            self.size = info.st_size
        except BaseException:
            os.close(self._fd)
            raise
        self.bytes_read = 0
        self.largest_read = 0
        self.read_ranges: list[tuple[int, int]] = []

    def close(self) -> None:
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def read(self, offset: int, length: int) -> bytes:
        if self._fd < 0:
            raise ProbeError("input reader is closed")
        if length <= 0:
            raise ProbeError("invalid zero-length metadata read")
        if length > MAX_METADATA_BOX_BYTES:
            raise ProbeError("metadata read exceeds bounded read cap")
        if offset < 0 or offset + length > self.size:
            raise ProbeError("metadata read falls outside the input file")
        if len(self.read_ranges) >= MAX_READ_CALLS:
            raise ProbeError("metadata read-count cap exceeded")
        try:
            data = os.pread(self._fd, length, offset)
        except OSError as exc:
            raise ProbeError(f"input read failed: {exc.strerror}") from exc
        if len(data) != length:
            raise ProbeError("truncated metadata read")
        self.bytes_read += length
        self.largest_read = max(self.largest_read, length)
        self.read_ranges.append((offset, offset + length))
        return data


class BoxIndex:
    def __init__(self, reader: FileReader) -> None:
        self.reader = reader
        self.box_count = 0

    def header(self, offset: int, parent_end: int) -> Box:
        if offset < 0 or parent_end > self.reader.size:
            raise ProbeError("box boundary falls outside the input file")
        if offset + 8 > parent_end:
            raise ProbeError("truncated box header")
        prefix = self.reader.read(offset, 8)
        size32, box_type = struct.unpack(">I4s", prefix)
        header_size = 8
        if size32 == 1:
            if offset + 16 > parent_end:
                raise ProbeError("truncated 64-bit box header")
            size = struct.unpack(">Q", self.reader.read(offset + 8, 8))[0]
            header_size = 16
        elif size32 == 0:
            size = parent_end - offset
        else:
            size = size32
        if box_type == b"uuid":
            header_size += 16
        if size < header_size:
            raise ProbeError("box size is smaller than its header")
        if offset + size > parent_end:
            raise ProbeError("box extends beyond its parent")
        return Box(offset, size, box_type, header_size)

    def children(
        self,
        start: int,
        end: int,
        *,
        depth: int,
    ) -> list[Box]:
        if depth > MAX_DEPTH:
            raise ProbeError("maximum ISO-BMFF nesting depth exceeded")
        boxes: list[Box] = []
        cursor = start
        while cursor < end:
            self.box_count += 1
            if self.box_count > MAX_BOX_COUNT:
                raise ProbeError("maximum ISO-BMFF box count exceeded")
            box = self.header(cursor, end)
            boxes.append(box)
            if box.end <= cursor:
                raise ProbeError("non-advancing ISO-BMFF box")
            cursor = box.end
        if cursor != end:
            raise ProbeError("child boxes do not exactly fill their parent")
        return boxes


def _exactly_one(boxes: Sequence[Box], box_type: bytes) -> Box:
    matches = [box for box in boxes if box.type == box_type]
    if len(matches) != 1:
        label = box_type.decode("latin1")
        raise ProbeError(f"expected exactly one {label} box")
    return matches[0]


def _optional_one(boxes: Sequence[Box], box_type: bytes) -> Box | None:
    matches = [box for box in boxes if box.type == box_type]
    if len(matches) > 1:
        label = box_type.decode("latin1")
        raise ProbeError(f"duplicate {label} box")
    return matches[0] if matches else None


def _read_box(reader: FileReader, box: Box) -> bytes:
    if box.size > MAX_METADATA_BOX_BYTES:
        raise ProbeError(
            f"{box.type_string()} metadata box exceeds bounded read cap"
        )
    return reader.read(box.offset, box.size)


def _full_box_duration(
    reader: FileReader,
    box: Box,
    label: str,
) -> tuple[int, int]:
    data = _read_box(reader, box)
    payload = data[box.header_size :]
    if len(payload) < 20:
        raise ProbeError(f"truncated {label} box")
    version = payload[0]
    if version == 0:
        timescale = struct.unpack_from(">I", payload, 12)[0]
        duration = struct.unpack_from(">I", payload, 16)[0]
        unknown_duration = 0xFFFFFFFF
    elif version == 1:
        if len(payload) < 32:
            raise ProbeError(f"truncated version-1 {label} box")
        timescale = struct.unpack_from(">I", payload, 20)[0]
        duration = struct.unpack_from(">Q", payload, 24)[0]
        unknown_duration = 0xFFFFFFFFFFFFFFFF
    else:
        raise ProbeError(f"unsupported {label} version {version}")
    if timescale == 0:
        raise ProbeError(f"{label} has a zero timescale")
    if duration in {0, unknown_duration}:
        raise ProbeError(f"{label} has no finite positive duration")
    return timescale, duration


def _parse_tkhd(reader: FileReader, box: Box) -> tuple[int, int, int]:
    data = _read_box(reader, box)
    payload = data[box.header_size :]
    if len(payload) < 84:
        raise ProbeError("truncated tkhd box")
    version = payload[0]
    if version == 0:
        track_id = struct.unpack_from(">I", payload, 12)[0]
    elif version == 1:
        if len(payload) < 96:
            raise ProbeError("truncated version-1 tkhd box")
        track_id = struct.unpack_from(">I", payload, 20)[0]
    else:
        raise ProbeError(f"unsupported tkhd version {version}")
    width_fixed, height_fixed = struct.unpack_from(">II", payload, len(payload) - 8)
    if track_id == 0:
        raise ProbeError("tkhd has a zero track id")
    return track_id, width_fixed >> 16, height_fixed >> 16


def _parse_handler(reader: FileReader, box: Box) -> str:
    data = _read_box(reader, box)
    payload = data[box.header_size :]
    if len(payload) < 12:
        raise ProbeError("truncated hdlr box")
    return payload[8:12].decode("latin1")


def _memory_box_header(data: bytes, offset: int, end: int) -> Box:
    if offset + 8 > end:
        raise ProbeError("truncated child box in sample entry")
    size32, box_type = struct.unpack_from(">I4s", data, offset)
    header_size = 8
    if size32 == 1:
        if offset + 16 > end:
            raise ProbeError("truncated 64-bit child box in sample entry")
        size = struct.unpack_from(">Q", data, offset + 8)[0]
        header_size = 16
    elif size32 == 0:
        size = end - offset
    else:
        size = size32
    if box_type == b"uuid":
        header_size += 16
    if size < header_size or offset + size > end:
        raise ProbeError("invalid child box size in sample entry")
    return Box(offset, size, box_type, header_size)


def _memory_children(data: bytes, start: int, end: int) -> list[Box]:
    boxes: list[Box] = []
    cursor = start
    while cursor < end:
        box = _memory_box_header(data, cursor, end)
        boxes.append(box)
        if box.end <= cursor:
            raise ProbeError("non-advancing child box in sample entry")
        cursor = box.end
    if cursor != end:
        raise ProbeError("sample-entry child boxes do not fill their parent")
    return boxes


def _descriptor_length(data: bytes, offset: int, end: int) -> tuple[int, int]:
    length = 0
    for _ in range(4):
        if offset >= end:
            raise ProbeError("truncated MPEG-4 descriptor length")
        value = data[offset]
        offset += 1
        length = (length << 7) | (value & 0x7F)
        if not value & 0x80:
            return length, offset
    raise ProbeError("overlong MPEG-4 descriptor length")


def _walk_descriptors(
    data: bytes,
    start: int,
    end: int,
    *,
    depth: int = 0,
) -> tuple[int | None, int | None]:
    if depth > 8:
        raise ProbeError("MPEG-4 descriptor nesting depth exceeded")
    object_type: int | None = None
    audio_object_type: int | None = None
    cursor = start
    while cursor < end:
        tag = data[cursor]
        cursor += 1
        length, body_start = _descriptor_length(data, cursor, end)
        body_end = body_start + length
        if body_end > end:
            raise ProbeError("MPEG-4 descriptor extends beyond its parent")
        nested_start: int | None = None
        if tag == 0x03:
            if length < 3:
                raise ProbeError("truncated ES_Descriptor")
            flags = data[body_start + 2]
            nested_start = body_start + 3
            if flags & 0x80:
                nested_start += 2
            if flags & 0x40:
                if nested_start >= body_end:
                    raise ProbeError("truncated ES_Descriptor URL")
                nested_start += 1 + data[nested_start]
            if flags & 0x20:
                nested_start += 2
            if nested_start > body_end:
                raise ProbeError("invalid ES_Descriptor flags")
        elif tag == 0x04:
            if length < 13:
                raise ProbeError("truncated DecoderConfigDescriptor")
            object_type = data[body_start]
            nested_start = body_start + 13
        elif tag == 0x05:
            if length < 2:
                raise ProbeError("truncated AudioSpecificConfig")
            base_type = data[body_start] >> 3
            if base_type == 31:
                audio_object_type = 32 + (
                    ((data[body_start] & 0x07) << 3)
                    | (data[body_start + 1] >> 5)
                )
            else:
                audio_object_type = base_type
        if nested_start is not None and nested_start < body_end:
            nested_object, nested_audio = _walk_descriptors(
                data,
                nested_start,
                body_end,
                depth=depth + 1,
            )
            if object_type is None:
                object_type = nested_object
            if audio_object_type is None:
                audio_object_type = nested_audio
        cursor = body_end
    if cursor != end:
        raise ProbeError("MPEG-4 descriptors do not fill their parent")
    return object_type, audio_object_type


def _parse_esds(entry: bytes, child: Box) -> tuple[int | None, int | None]:
    payload_start = child.payload_start
    if payload_start + 4 > child.end:
        raise ProbeError("truncated esds full-box header")
    return _walk_descriptors(entry, payload_start + 4, child.end)


VIDEO_CODECS = {
    "avc1": "h264",
    "avc3": "h264",
    "hvc1": "hevc",
    "hev1": "hevc",
    "mp4v": "mpeg4",
    "jpeg": "mjpeg",
    "png ": "png",
}

AUDIO_CODECS = {
    "ac-3": "ac3",
    "ec-3": "eac3",
    "alac": "alac",
    "Opus": "opus",
    "lpcm": "pcm_s16be",
    "sowt": "pcm_s16le",
    "twos": "pcm_s16be",
}


def _parse_video_entry(
    entry_type: str,
    entry: bytes,
    header_size: int,
) -> dict[str, Any]:
    codec_name = VIDEO_CODECS.get(entry_type)
    if codec_name is None:
        raise ProbeError(f"unsupported video sample entry {entry_type!r}")
    fixed_end = header_size + 78
    if len(entry) < fixed_end:
        raise ProbeError("truncated visual sample entry")
    width, height = struct.unpack_from(">HH", entry, header_size + 24)
    if width == 0 or height == 0:
        raise ProbeError("visual sample entry has zero dimensions")
    _memory_children(entry, fixed_end, len(entry))
    return {
        "codec_type": "video",
        "codec_name": codec_name,
        "codec_tag_string": entry_type,
        "width": width,
        "height": height,
    }


def _parse_audio_entry(
    entry_type: str,
    entry: bytes,
    header_size: int,
) -> dict[str, Any]:
    if len(entry) < header_size + 28:
        raise ProbeError("truncated audio sample entry")
    version = struct.unpack_from(">H", entry, header_size + 8)[0]
    child_start_by_version = {
        0: header_size + 28,
        1: header_size + 44,
        2: header_size + 64,
    }
    if version not in child_start_by_version:
        raise ProbeError(f"unsupported audio sample-entry version {version}")
    child_start = child_start_by_version[version]
    if len(entry) < child_start:
        raise ProbeError("truncated versioned audio sample entry")
    channels = struct.unpack_from(">H", entry, header_size + 16)[0]
    sample_rate_fixed = struct.unpack_from(">I", entry, header_size + 24)[0]
    if sample_rate_fixed & 0xFFFF:
        raise ProbeError("fractional audio sample rate is unsupported")
    sample_rate = sample_rate_fixed >> 16
    if channels == 0 or sample_rate == 0:
        raise ProbeError("audio sample entry has invalid channel/rate metadata")

    object_type: int | None = None
    audio_object_type: int | None = None
    for child in _memory_children(entry, child_start, len(entry)):
        if child.type == b"esds":
            if object_type is not None:
                raise ProbeError("duplicate esds box in audio sample entry")
            object_type, audio_object_type = _parse_esds(entry, child)

    if entry_type == "mp4a":
        if object_type == 0x40:
            codec_name = "aac"
            if audio_object_type not in {1, 2, 5, 29}:
                raise ProbeError(
                    f"unsupported MPEG-4 audio object type {audio_object_type}"
                )
        elif object_type in {0x69, 0x6B}:
            codec_name = "mp3"
        else:
            raise ProbeError(
                "unsupported or missing mp4a object type indication"
            )
    else:
        codec_name = AUDIO_CODECS.get(entry_type)
        if codec_name is None:
            raise ProbeError(f"unsupported audio sample entry {entry_type!r}")

    stream: dict[str, Any] = {
        "codec_type": "audio",
        "codec_name": codec_name,
        "codec_tag_string": entry_type,
        "sample_rate": str(sample_rate),
        "channels": channels,
    }
    if channels == 1:
        stream["channel_layout"] = "mono"
    elif channels == 2:
        stream["channel_layout"] = "stereo"
    return stream


def _parse_stsd(
    reader: FileReader,
    box: Box,
    handler: str,
) -> dict[str, Any]:
    data = _read_box(reader, box)
    payload = data[box.header_size :]
    if len(payload) < 16:
        raise ProbeError("truncated stsd box")
    entry_count = struct.unpack_from(">I", payload, 4)[0]
    if entry_count != 1:
        raise ProbeError("only one sample description per track is supported")
    entry_box = _memory_box_header(payload, 8, len(payload))
    if entry_box.end != len(payload):
        raise ProbeError("stsd sample entry does not fill the stsd box")
    entry = payload[entry_box.offset : entry_box.end]
    entry_type = entry_box.type_string()
    if handler == "vide":
        return _parse_video_entry(entry_type, entry, entry_box.header_size)
    if handler == "soun":
        return _parse_audio_entry(entry_type, entry, entry_box.header_size)
    if handler in {"meta", "tmcd"}:
        return {
            "codec_type": "data",
            "codec_name": "bin_data",
            "codec_tag_string": entry_type,
        }
    raise ProbeError(f"unsupported track handler {handler!r}")


def _format_duration(duration: int, timescale: int) -> str:
    return f"{duration / timescale:.6f}"


def _parse_ftyp(reader: FileReader, box: Box | None) -> dict[str, Any]:
    if box is None:
        return {}
    data = _read_box(reader, box)
    payload = data[box.header_size :]
    if len(payload) < 8 or len(payload) % 4:
        raise ProbeError("malformed ftyp box")
    major_brand = payload[:4].decode("latin1")
    minor_version = struct.unpack_from(">I", payload, 4)[0]
    compatible = "".join(
        payload[offset : offset + 4].decode("latin1")
        for offset in range(8, len(payload), 4)
    )
    return {
        "major_brand": major_brand,
        "minor_version": str(minor_version),
        "compatible_brands": compatible,
    }


def _parse_track(
    reader: FileReader,
    index: BoxIndex,
    trak: Box,
    stream_index: int,
) -> dict[str, Any]:
    trak_children = index.children(
        trak.payload_start,
        trak.end,
        depth=3,
    )
    track_id, tkhd_width, tkhd_height = _parse_tkhd(
        reader,
        _exactly_one(trak_children, b"tkhd"),
    )
    mdia = _exactly_one(trak_children, b"mdia")
    mdia_children = index.children(
        mdia.payload_start,
        mdia.end,
        depth=4,
    )
    timescale, duration = _full_box_duration(
        reader,
        _exactly_one(mdia_children, b"mdhd"),
        "mdhd",
    )
    handler = _parse_handler(
        reader,
        _exactly_one(mdia_children, b"hdlr"),
    )
    minf = _exactly_one(mdia_children, b"minf")
    minf_children = index.children(
        minf.payload_start,
        minf.end,
        depth=5,
    )
    stbl = _exactly_one(minf_children, b"stbl")
    stbl_children = index.children(
        stbl.payload_start,
        stbl.end,
        depth=6,
    )
    stream = _parse_stsd(
        reader,
        _exactly_one(stbl_children, b"stsd"),
        handler,
    )
    if stream["codec_type"] == "video":
        if tkhd_width not in {0, stream["width"]}:
            raise ProbeError("tkhd and stsd video widths disagree")
        if tkhd_height not in {0, stream["height"]}:
            raise ProbeError("tkhd and stsd video heights disagree")
    stream.update(
        {
            "index": stream_index,
            "id": f"0x{track_id:x}",
            "time_base": f"1/{timescale}",
            "duration_ts": duration,
            "duration": _format_duration(duration, timescale),
        }
    )
    return stream


def _build_report(
    reader: FileReader,
    path: Path,
) -> tuple[dict[str, Any], tuple[Box, ...]]:
    index = BoxIndex(reader)
    top = index.children(0, reader.size, depth=1)
    moov = _exactly_one(top, b"moov")
    ftyp = _optional_one(top, b"ftyp")
    if any(box.type == b"moof" for box in top):
        raise ProbeError("fragmented MP4/MOV files are unsupported")
    if not any(box.type == b"mdat" for box in top):
        raise ProbeError("input has no mdat box")

    moov_children = index.children(
        moov.payload_start,
        moov.end,
        depth=2,
    )
    if any(box.type == b"cmov" for box in moov_children):
        raise ProbeError("compressed moov metadata is unsupported")
    movie_timescale, movie_duration = _full_box_duration(
        reader,
        _exactly_one(moov_children, b"mvhd"),
        "mvhd",
    )
    traks = [box for box in moov_children if box.type == b"trak"]
    if not traks:
        raise ProbeError("moov contains no tracks")
    streams = [
        _parse_track(reader, index, trak, stream_index)
        for stream_index, trak in enumerate(traks)
    ]

    tags = _parse_ftyp(reader, ftyp)
    major_brand = tags.get("major_brand")
    is_mov = major_brand == "qt  "
    format_name = "mov" if is_mov else "mov,mp4,m4a,3gp,3g2,mj2"
    format_long_name = "QuickTime / MOV"
    duration_string = _format_duration(movie_duration, movie_timescale)
    duration_seconds = movie_duration / movie_timescale
    format_section: dict[str, Any] = {
        "filename": str(path),
        "nb_streams": len(streams),
        "nb_programs": 0,
        "format_name": format_name,
        "format_long_name": format_long_name,
        "duration": duration_string,
        "size": str(reader.size),
        "bit_rate": str(round(reader.size * 8 / duration_seconds)),
        "probe_score": 100,
    }
    if tags:
        format_section["tags"] = tags
    return {"streams": streams, "format": format_section}, tuple(top)


def probe_path(path: Path | str) -> ProbeResult:
    input_path = Path(path)
    with FileReader(input_path) as reader:
        report, top = _build_report(reader, input_path)
        return ProbeResult(
            report=report,
            top_level_boxes=top,
            bytes_read=reader.bytes_read,
            largest_read=reader.largest_read,
            read_ranges=tuple(reader.read_ranges),
        )


@dataclass(frozen=True)
class CliRequest:
    path: Path
    show_format: bool
    show_streams: bool


def _parse_cli(argv: Sequence[str]) -> CliRequest:
    show_format = False
    show_streams = False
    inputs: list[str] = []
    index = 0
    while index < len(argv):
        argument = argv[index]
        if argument in {"-v", "-loglevel"}:
            index += 1
            if index >= len(argv) or argv[index] not in {"error", "quiet"}:
                raise ProbeError("only '-v error' and '-v quiet' are supported")
        elif argument in {"-print_format", "-of"}:
            index += 1
            if index >= len(argv) or argv[index] != "json":
                raise ProbeError("only JSON output format is supported")
        elif argument in {"-show_format", "-show_format=1"}:
            show_format = True
        elif argument in {"-show_streams", "-show_streams=1"}:
            show_streams = True
        elif argument == "-hide_banner":
            pass
        elif argument == "--":
            inputs.extend(argv[index + 1 :])
            break
        elif argument.startswith("-"):
            raise ProbeError(f"unsupported ffprobe option {argument!r}")
        else:
            inputs.append(argument)
        index += 1
    if len(inputs) != 1:
        raise ProbeError("exactly one local input file is required")
    if not show_format and not show_streams:
        raise ProbeError("at least one of -show_format/-show_streams is required")
    return CliRequest(Path(inputs[0]), show_format, show_streams)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        request = _parse_cli(list(sys.argv[1:] if argv is None else argv))
        report = probe_path(request.path).report
        selected: dict[str, Any] = {}
        if request.show_streams:
            selected["streams"] = report["streams"]
        if request.show_format:
            selected["format"] = report["format"]
        json.dump(selected, sys.stdout, indent=4)
        sys.stdout.write("\n")
        return 0
    except (ProbeError, OSError, ValueError, struct.error) as exc:
        print(f"ffprobe_mp4_metadata_shim: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
