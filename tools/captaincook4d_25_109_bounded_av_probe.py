#!/usr/bin/env python3
"""Bounded live A/V metadata probe for CaptainCook4D recording 25_109.

Only the exact official GoPro 360p MP4 is touched.  The probe uses explicit
Box proxies, accepts only HTTP 206 responses with exact Content-Range values,
and persists at most 16 MiB of response payload in a deleted sparse temporary
file.  It never opens annotations, decodes media content, or downloads the
complete object.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from fractions import Fraction
from io import UnsupportedOperation
from pathlib import Path
from typing import Any, BinaryIO
from urllib.parse import urlsplit

import requests

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "av-trace.captaincook4d-25-109-bounded-av-probe/1.0"
READY = "CAPTAINCOOK4D_25_109_BOUNDED_AV_PROBE_READY"
REPAIR = "CAPTAINCOOK4D_25_109_BOUNDED_AV_PROBE_REPAIR"
NO_GO = "CAPTAINCOOK4D_25_109_BOUNDED_AV_PROBE_NO_GO"

RECORDING_ID = "25_109"
SOURCE_GROUP_ID = "cc4d_p05_e07"
PERSON_ID = 5
ENVIRONMENT_ID = 7
STREAM = "gopro_360p"
OFFICIAL_DURATION_SECONDS = 2126.96
OFFICIAL_URL = (
    "https://utdallas.box.com/shared/static/"
    "qiu0plhm3ixqcfgu02qy9kmlp5tre6p2.mp4"
)
BOX_SHARED_STATIC_ID = "qiu0plhm3ixqcfgu02qy9kmlp5tre6p2"

PRIMARY_PROXY = "https://proxy.example.invalid:3128"
FALLBACK_PROXY = "https://proxy.example.invalid:3128"
PROXIES = (("https://proxy.example.invalid:3128", PRIMARY_PROXY), ("https://proxy.example.invalid:3128-fallback", FALLBACK_PROXY))
ALLOWED_REDIRECT_HOSTS = {
    "utdallas.box.com",
    "utdallas.app.box.com",
    "public.boxcloud.com",
}

MIB = 1024 * 1024
MAX_PERSISTED_RESPONSE_BYTES = 16 * MIB
HEAD_WINDOW_BYTES = 8 * MIB
TAIL_WINDOW_BYTES = 8 * MIB
CONNECT_TIMEOUT_SECONDS = 30
READ_TIMEOUT_SECONDS = 120
DURATION_TOLERANCE_SECONDS = 2.0
SYNC_START_TOLERANCE_SECONDS = 0.100
CONTENT_RANGE_RE = re.compile(
    r"^bytes\s+(\d+)-(\d+)/(\d+)$", re.IGNORECASE
)

LOCAL_INVENTORY = (
    ROOT
    / "data/source_recon/captaincook4d_access_v1/derived/"
    "recording_stream_inventory_v1.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "data/rehearsal_plan/"
    "captaincook4d_25_109_bounded_av_probe_v1.json"
)


class ProbeError(RuntimeError):
    """Repairable bounded-probe failure."""


class NoGoError(ProbeError):
    """Identity, range-safety, or internally inconsistent evidence failure."""


class RangeRejected(ProbeError):
    """A proxy route failed before any response body was accepted."""


class ProxySelectionFailed(ProbeError):
    """Neither permitted proxy established a bounded 206 exchange."""

    def __init__(self, attempts: list[dict[str, Any]]) -> None:
        super().__init__("NO_PROXY_ESTABLISHED_BOUNDED_206")
        self.attempts = attempts


@dataclass(frozen=True)
class Box:
    offset: int
    size: int
    type: str
    header_size: int

    @property
    def payload_offset(self) -> int:
        return self.offset + self.header_size

    @property
    def end(self) -> int:
        return self.offset + self.size


def utc_now() -> str:
    return (
        datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(MIB):
            digest.update(block)
    return digest.hexdigest()


def atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def validate_local_identity() -> dict[str, Any]:
    raw = LOCAL_INVENTORY.read_bytes()
    inventory = json.loads(raw)
    records = inventory.get("records")
    if not isinstance(records, list):
        raise NoGoError("LOCAL_INVENTORY_RECORDS_MISSING")
    record = next(
        (
            item
            for item in records
            if isinstance(item, Mapping)
            and item.get("recording_id") == RECORDING_ID
        ),
        None,
    )
    if record is None:
        raise NoGoError("LOCAL_RECORDING_NOT_FOUND")
    expected = {
        "source_group_id": SOURCE_GROUP_ID,
        "person_id": PERSON_ID,
        "environment_id": ENVIRONMENT_ID,
        "duration_seconds": OFFICIAL_DURATION_SECONDS,
        "gopro_360p_available": True,
    }
    for key, value in expected.items():
        if record.get(key) != value:
            raise NoGoError(f"LOCAL_IDENTITY_MISMATCH:{key}")
    urls = record.get("official_stream_urls")
    if not isinstance(urls, Mapping) or urls.get(STREAM) != OFFICIAL_URL:
        raise NoGoError("LOCAL_OFFICIAL_URL_MISMATCH")
    parsed = urlsplit(OFFICIAL_URL)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "utdallas.box.com"
        or parsed.path
        != f"/shared/static/{BOX_SHARED_STATIC_ID}.mp4"
        or parsed.query
        or parsed.fragment
    ):
        raise NoGoError("PINNED_OFFICIAL_URL_INVALID")
    return {
        "path": LOCAL_INVENTORY.relative_to(ROOT).as_posix(),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "record": {
            "recording_id": record["recording_id"],
            "source_group_id": record["source_group_id"],
            "person_id": record["person_id"],
            "environment_id": record["environment_id"],
            "duration_seconds": record["duration_seconds"],
            "stream": STREAM,
            "official_url": urls[STREAM],
        },
    }


def parse_content_range(value: str | None) -> tuple[int, int, int]:
    match = CONTENT_RANGE_RE.fullmatch((value or "").strip())
    if not match:
        raise RangeRejected(f"INVALID_CONTENT_RANGE:{value!r}")
    start, end, total = (int(item) for item in match.groups())
    if start < 0 or end < start or total <= end:
        raise RangeRejected(f"IMPOSSIBLE_CONTENT_RANGE:{value!r}")
    return start, end, total


def host_allowed(host: str | None) -> bool:
    if not host:
        return False
    return host in ALLOWED_REDIRECT_HOSTS or host.endswith(".boxcloud.com")


def exchange_summary(response: requests.Response) -> dict[str, Any]:
    chain = [*response.history, response]
    return {
        "redirect_count": len(response.history),
        "chain": [
            {
                "status_code": item.status_code,
                "host": urlsplit(item.url).hostname,
            }
            for item in chain
        ],
        "final": {
            "status_code": response.status_code,
            "host": urlsplit(response.url).hostname,
            "content_type": response.headers.get("Content-Type"),
            "content_length": response.headers.get("Content-Length"),
            "content_range": response.headers.get("Content-Range"),
            "accept_ranges": response.headers.get("Accept-Ranges"),
            "etag": response.headers.get("ETag"),
            "last_modified": response.headers.get("Last-Modified"),
        },
    }


def validate_range_headers(
    response: requests.Response,
    *,
    expected_start: int,
    expected_end: int,
    expected_total: int | None,
) -> tuple[int, int, int]:
    chain_hosts = [urlsplit(item.url).hostname for item in response.history]
    chain_hosts.append(urlsplit(response.url).hostname)
    if not all(host_allowed(host) for host in chain_hosts):
        raise NoGoError("UNEXPECTED_REDIRECT_HOST")
    if response.status_code != 206:
        # stream=True means no body is consumed before this fail-closed check.
        raise RangeRejected(f"RANGE_STATUS_NOT_206:{response.status_code}")
    content_type = (response.headers.get("Content-Type") or "").split(
        ";", 1
    )[0].lower()
    if content_type not in {"video/mp4", "application/octet-stream"}:
        raise NoGoError(f"UNEXPECTED_CONTENT_TYPE:{content_type}")
    start, end, total = parse_content_range(
        response.headers.get("Content-Range")
    )
    if (start, end) != (expected_start, expected_end):
        raise RangeRejected(
            f"CONTENT_RANGE_BOUNDS_MISMATCH:{start}-{end}!="
            f"{expected_start}-{expected_end}"
        )
    if expected_total is not None and total != expected_total:
        raise NoGoError(
            f"CONTENT_RANGE_TOTAL_CHANGED:{total}!={expected_total}"
        )
    declared_length = response.headers.get("Content-Length")
    if declared_length is not None and int(declared_length) != end - start + 1:
        raise RangeRejected("CONTENT_LENGTH_RANGE_MISMATCH")
    return start, end, total


def read_exact_response_body(
    response: requests.Response,
    *,
    expected_bytes: int,
) -> bytes:
    body = bytearray()
    for chunk in response.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        if len(body) + len(chunk) > expected_bytes:
            raise NoGoError("RANGE_BODY_EXCEEDED_DECLARED_BOUNDS")
        body.extend(chunk)
    if len(body) != expected_bytes:
        raise ProbeError(
            f"RANGE_BODY_LENGTH_MISMATCH:{len(body)}!={expected_bytes}"
        )
    return bytes(body)


def request_range(
    session: requests.Session,
    *,
    proxy: str,
    start: int,
    end: int,
    expected_total: int | None,
) -> tuple[bytes, dict[str, Any], int]:
    response: requests.Response | None = None
    try:
        response = session.get(
            OFFICIAL_URL,
            headers={
                "Accept-Encoding": "identity",
                "Range": f"bytes={start}-{end}",
            },
            allow_redirects=True,
            proxies={"http": proxy, "https": proxy},
            stream=True,
            timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
        )
        _, _, total = validate_range_headers(
            response,
            expected_start=start,
            expected_end=end,
            expected_total=expected_total,
        )
        summary = exchange_summary(response)
        body = read_exact_response_body(
            response, expected_bytes=end - start + 1
        )
        summary["body_bytes_accepted"] = len(body)
        summary["body_sha256"] = hashlib.sha256(body).hexdigest()
        return body, summary, total
    except requests.RequestException as exc:
        raise RangeRejected(
            f"REQUEST_ERROR:{type(exc).__name__}:{exc}"
        ) from exc
    finally:
        if response is not None:
            response.close()


def choose_proxy(
    session: requests.Session,
) -> tuple[str, str, bytes, int, list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    for proxy_name, proxy in PROXIES:
        try:
            body, exchange, total = request_range(
                session,
                proxy=proxy,
                start=0,
                end=0,
                expected_total=None,
            )
            attempts.append(
                {
                    "proxy_name": proxy_name,
                    "proxy": proxy,
                    "status": "SELECTED",
                    "range": "bytes=0-0",
                    "exchange": exchange,
                }
            )
            return proxy_name, proxy, body, total, attempts
        except RangeRejected as exc:
            attempts.append(
                {
                    "proxy_name": proxy_name,
                    "proxy": proxy,
                    "status": "REJECTED_WITHOUT_ACCEPTED_BODY",
                    "range": "bytes=0-0",
                    "error": str(exc),
                    "accepted_body_bytes": 0,
                }
            )
    raise ProxySelectionFailed(attempts)


def covered(
    offset: int, size: int, intervals: Iterable[tuple[int, int]]
) -> bool:
    end = offset + size
    return any(offset >= start and end <= stop for start, stop in intervals)


class SparseReader:
    def __init__(
        self,
        handle: BinaryIO,
        *,
        total: int,
        intervals: list[tuple[int, int]],
    ) -> None:
        self.handle = handle
        self.total = total
        self.intervals = intervals

    def read(self, offset: int, size: int) -> bytes:
        if size < 0 or offset < 0 or offset + size > self.total:
            raise ProbeError("ISO_READ_OUT_OF_BOUNDS")
        if not covered(offset, size, self.intervals):
            raise ProbeError(
                f"ISO_READ_OUTSIDE_PERSISTED_WINDOWS:{offset}+{size}"
            )
        self.handle.seek(offset)
        value = self.handle.read(size)
        if len(value) != size:
            raise ProbeError("ISO_SHORT_READ")
        return value


def read_box(reader: SparseReader, offset: int, parent_end: int) -> Box:
    header = reader.read(offset, 8)
    size32, type_raw = struct.unpack(">I4s", header)
    box_type = type_raw.decode("latin-1")
    header_size = 8
    if size32 == 1:
        size = struct.unpack(">Q", reader.read(offset + 8, 8))[0]
        header_size = 16
    elif size32 == 0:
        size = parent_end - offset
    else:
        size = size32
    if size < header_size or offset + size > parent_end:
        raise ProbeError(f"INVALID_ISO_BOX:{box_type}@{offset}:{size}")
    return Box(offset=offset, size=size, type=box_type, header_size=header_size)


def child_boxes(
    reader: SparseReader,
    parent: Box,
    *,
    prefix_bytes: int = 0,
) -> list[Box]:
    position = parent.payload_offset + prefix_bytes
    boxes: list[Box] = []
    while position < parent.end:
        box = read_box(reader, position, parent.end)
        boxes.append(box)
        position = box.end
    if position != parent.end:
        raise ProbeError(f"ISO_CHILD_ALIGNMENT_FAILED:{parent.type}")
    return boxes


def top_level_boxes(reader: SparseReader) -> list[Box]:
    boxes: list[Box] = []
    position = 0
    while position < reader.total:
        box = read_box(reader, position, reader.total)
        boxes.append(box)
        position = box.end
    return boxes


def one(boxes: Iterable[Box], box_type: str) -> Box:
    matches = [box for box in boxes if box.type == box_type]
    if len(matches) != 1:
        raise ProbeError(f"EXPECTED_ONE_{box_type.upper()}:{len(matches)}")
    return matches[0]


def u16(reader: SparseReader, offset: int) -> int:
    return struct.unpack(">H", reader.read(offset, 2))[0]


def u32(reader: SparseReader, offset: int) -> int:
    return struct.unpack(">I", reader.read(offset, 4))[0]


def i32(reader: SparseReader, offset: int) -> int:
    return struct.unpack(">i", reader.read(offset, 4))[0]


def u64(reader: SparseReader, offset: int) -> int:
    return struct.unpack(">Q", reader.read(offset, 8))[0]


def i64(reader: SparseReader, offset: int) -> int:
    return struct.unpack(">q", reader.read(offset, 8))[0]


def fullbox_version(reader: SparseReader, box: Box) -> int:
    return reader.read(box.payload_offset, 1)[0]


def parse_mvhd(reader: SparseReader, box: Box) -> dict[str, Any]:
    payload = box.payload_offset
    version = fullbox_version(reader, box)
    if version == 0:
        timescale = u32(reader, payload + 12)
        duration = u32(reader, payload + 16)
    elif version == 1:
        timescale = u32(reader, payload + 20)
        duration = u64(reader, payload + 24)
    else:
        raise ProbeError(f"MVHD_VERSION_UNSUPPORTED:{version}")
    if timescale <= 0:
        raise ProbeError("MVHD_TIMESCALE_INVALID")
    return {
        "version": version,
        "timescale": timescale,
        "duration_ticks": duration,
        "duration_seconds": float(Fraction(duration, timescale)),
    }


def parse_tkhd(reader: SparseReader, box: Box) -> dict[str, Any]:
    payload = box.payload_offset
    version = fullbox_version(reader, box)
    if version == 0:
        track_id = u32(reader, payload + 12)
        duration = u32(reader, payload + 20)
    elif version == 1:
        track_id = u32(reader, payload + 20)
        duration = u64(reader, payload + 28)
    else:
        raise ProbeError(f"TKHD_VERSION_UNSUPPORTED:{version}")
    width_fixed = u32(reader, box.end - 8)
    height_fixed = u32(reader, box.end - 4)
    return {
        "track_id": track_id,
        "duration_movie_ticks": duration,
        "display_width": width_fixed / 65536,
        "display_height": height_fixed / 65536,
    }


def parse_mdhd(reader: SparseReader, box: Box) -> dict[str, Any]:
    payload = box.payload_offset
    version = fullbox_version(reader, box)
    if version == 0:
        timescale = u32(reader, payload + 12)
        duration = u32(reader, payload + 16)
    elif version == 1:
        timescale = u32(reader, payload + 20)
        duration = u64(reader, payload + 24)
    else:
        raise ProbeError(f"MDHD_VERSION_UNSUPPORTED:{version}")
    if timescale <= 0:
        raise ProbeError("MDHD_TIMESCALE_INVALID")
    return {
        "timescale": timescale,
        "duration_ticks": duration,
        "duration_seconds": float(Fraction(duration, timescale)),
    }


def parse_handler(reader: SparseReader, box: Box) -> str:
    return reader.read(box.payload_offset + 8, 4).decode("latin-1")


def parse_elst(
    reader: SparseReader, box: Box, movie_timescale: int
) -> dict[str, Any]:
    payload = box.payload_offset
    version = fullbox_version(reader, box)
    entry_count = u32(reader, payload + 4)
    position = payload + 8
    entries = []
    for _ in range(entry_count):
        if version == 0:
            segment_duration = u32(reader, position)
            media_time = i32(reader, position + 4)
            position += 12
        elif version == 1:
            segment_duration = u64(reader, position)
            media_time = i64(reader, position + 8)
            position += 20
        else:
            raise ProbeError(f"ELST_VERSION_UNSUPPORTED:{version}")
        entries.append(
            {
                "segment_duration_movie_ticks": segment_duration,
                "segment_duration_seconds": float(
                    Fraction(segment_duration, movie_timescale)
                ),
                "media_time_ticks": media_time,
            }
        )
    empty_ticks = 0
    for entry in entries:
        if entry["media_time_ticks"] == -1:
            empty_ticks += entry["segment_duration_movie_ticks"]
        else:
            break
    return {
        "version": version,
        "entries": entries,
        "presentation_start_seconds": float(
            Fraction(empty_ticks, movie_timescale)
        ),
    }


def codec_name(sample_entry: str) -> str:
    return {
        "avc1": "h264",
        "avc3": "h264",
        "hvc1": "hevc",
        "hev1": "hevc",
        "mp4v": "mpeg4",
        "mp4a": "aac",
        "ac-3": "ac3",
        "ec-3": "eac3",
        "Opus": "opus",
    }.get(sample_entry, sample_entry)


def parse_stsd(
    reader: SparseReader, box: Box, handler: str
) -> dict[str, Any]:
    payload = box.payload_offset
    entry_count = u32(reader, payload + 4)
    entries_parent = Box(
        offset=box.offset,
        size=box.size,
        type=box.type,
        header_size=box.header_size + 8,
    )
    entries = child_boxes(reader, entries_parent)
    if entry_count != len(entries) or not entries:
        raise ProbeError("STSD_ENTRY_COUNT_MISMATCH")
    entry = entries[0]
    result: dict[str, Any] = {
        "sample_entry": entry.type,
        "codec": codec_name(entry.type),
    }
    if handler == "vide":
        result.update(
            {
                "width": u16(reader, entry.payload_offset + 24),
                "height": u16(reader, entry.payload_offset + 26),
            }
        )
    elif handler == "soun":
        sample_rate_fixed = u32(reader, entry.payload_offset + 24)
        result.update(
            {
                "channels": u16(reader, entry.payload_offset + 16),
                "sample_size_bits": u16(reader, entry.payload_offset + 18),
                "sample_rate_hz": sample_rate_fixed >> 16,
            }
        )
    return result


def parse_track(
    reader: SparseReader, trak: Box, movie_timescale: int
) -> dict[str, Any]:
    trak_children = child_boxes(reader, trak)
    tkhd = parse_tkhd(reader, one(trak_children, "tkhd"))
    mdia = one(trak_children, "mdia")
    mdia_children = child_boxes(reader, mdia)
    mdhd = parse_mdhd(reader, one(mdia_children, "mdhd"))
    handler = parse_handler(reader, one(mdia_children, "hdlr"))
    minf = one(mdia_children, "minf")
    stbl = one(child_boxes(reader, minf), "stbl")
    stsd = parse_stsd(reader, one(child_boxes(reader, stbl), "stsd"), handler)
    edts = [box for box in trak_children if box.type == "edts"]
    edit = None
    if edts:
        edit = parse_elst(
            reader, one(child_boxes(reader, edts[0]), "elst"), movie_timescale
        )
    presentation_start = (
        edit["presentation_start_seconds"] if edit is not None else 0.0
    )
    return {
        **tkhd,
        **mdhd,
        **stsd,
        "handler_type": handler,
        "track_duration_movie_seconds": float(
            Fraction(tkhd["duration_movie_ticks"], movie_timescale)
        ),
        "presentation_start_seconds": presentation_start,
        "edit_list": edit,
    }


def parse_iso_bmff(
    path: Path,
    *,
    total: int,
    intervals: list[tuple[int, int]],
) -> dict[str, Any]:
    with path.open("rb") as handle:
        reader = SparseReader(handle, total=total, intervals=intervals)
        top = top_level_boxes(reader)
        moov = one(top, "moov")
        if not covered(moov.offset, moov.size, intervals):
            raise ProbeError(
                f"MOOV_NOT_FULLY_IN_BOUNDED_WINDOWS:{moov.offset}+{moov.size}"
            )
        moov_children = child_boxes(reader, moov)
        movie = parse_mvhd(reader, one(moov_children, "mvhd"))
        tracks = [
            parse_track(reader, box, movie["timescale"])
            for box in moov_children
            if box.type == "trak"
        ]
    video_tracks = [item for item in tracks if item["handler_type"] == "vide"]
    audio_tracks = [item for item in tracks if item["handler_type"] == "soun"]
    if len(video_tracks) != 1 or len(audio_tracks) < 1:
        raise ProbeError(
            f"EXPECTED_VIDEO_AND_AUDIO_TRACKS:"
            f"{len(video_tracks)}:{len(audio_tracks)}"
        )
    video = video_tracks[0]
    audio = audio_tracks[0]
    start_delta = abs(
        video["presentation_start_seconds"]
        - audio["presentation_start_seconds"]
    )
    return {
        "parser": "direct_iso_bmff",
        "top_level_boxes": [
            {"type": box.type, "offset": box.offset, "size": box.size}
            for box in top
        ],
        "moov": {"offset": moov.offset, "size": moov.size},
        "movie": movie,
        "video": video,
        "audio": audio,
        "shared_timeline": {
            "same_moov_movie_timeline": True,
            "movie_timescale": movie["timescale"],
            "video_presentation_start_seconds": video[
                "presentation_start_seconds"
            ],
            "audio_presentation_start_seconds": audio[
                "presentation_start_seconds"
            ],
            "absolute_start_delta_seconds": start_delta,
            "start_aligned_within_tolerance": (
                start_delta <= SYNC_START_TOLERANCE_SECONDS
            ),
            "tolerance_seconds": SYNC_START_TOLERANCE_SECONDS,
        },
    }


def fraction_seconds(value: Any, time_base: Any) -> float | None:
    if value is None or time_base is None:
        return None
    return float(value * time_base)


def pyav_probe(path: Path) -> dict[str, Any]:
    try:
        import av

        with av.open(str(path), mode="r") as container:
            streams = []
            for stream in container.streams:
                context = stream.codec_context
                row: dict[str, Any] = {
                    "index": stream.index,
                    "type": stream.type,
                    "codec": context.name,
                    "time_base": str(stream.time_base),
                    "start_time_seconds": fraction_seconds(
                        stream.start_time, stream.time_base
                    ),
                    "duration_seconds": fraction_seconds(
                        stream.duration, stream.time_base
                    ),
                }
                if stream.type == "video":
                    row.update(
                        {
                            "width": context.width,
                            "height": context.height,
                            "average_rate": (
                                str(stream.average_rate)
                                if stream.average_rate is not None
                                else None
                            ),
                        }
                    )
                elif stream.type == "audio":
                    row.update(
                        {
                            "channels": context.channels,
                            "sample_rate_hz": context.sample_rate,
                            "layout": (
                                context.layout.name
                                if context.layout is not None
                                else None
                            ),
                        }
                    )
                streams.append(row)
            return {
                "status": "SUCCESS",
                "parser": "ffmpeg_libavformat_via_pyav",
                "format_name": container.format.name,
                "duration_seconds": (
                    container.duration / 1_000_000
                    if container.duration is not None
                    else None
                ),
                "streams": streams,
            }
    except (
        AttributeError,
        ImportError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        UnsupportedOperation,
    ) as exc:  # pragma: no cover - live library detail
        return {
            "status": "FAILED",
            "parser": "ffmpeg_libavformat_via_pyav",
            "error": f"{type(exc).__name__}:{exc}",
        }


def ffprobe(path: Path) -> dict[str, Any]:
    executable = shutil.which("ffprobe")
    if executable is None:
        return {"status": "UNAVAILABLE", "executable": None}
    command = [
        executable,
        "-v",
        "error",
        "-show_entries",
        (
            "format=format_name,duration:"
            "stream=index,codec_type,codec_name,time_base,start_time,duration,"
            "width,height,channels,sample_rate"
        ),
        "-of",
        "json",
        str(path),
    ]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0:
        return {
            "status": "FAILED",
            "returncode": completed.returncode,
            "stderr": completed.stderr.strip()[:1000],
        }
    return {"status": "SUCCESS", "result": json.loads(completed.stdout)}


def technical_gates(iso: Mapping[str, Any]) -> tuple[bool, list[str]]:
    blockers: list[str] = []
    movie_duration = float(iso["movie"]["duration_seconds"])
    if abs(movie_duration - OFFICIAL_DURATION_SECONDS) > DURATION_TOLERANCE_SECONDS:
        blockers.append(
            "Container duration differs from pinned official duration beyond "
            "the bounded technical tolerance."
        )
    audio = iso["audio"]
    if (
        not audio.get("codec")
        or not audio.get("channels")
        or not audio.get("sample_rate_hz")
    ):
        blockers.append("Native audio stream parameters are incomplete.")
    video = iso["video"]
    if (
        not video.get("codec")
        or not video.get("width")
        or not video.get("height")
    ):
        blockers.append("Native video stream parameters are incomplete.")
    if not iso["shared_timeline"]["start_aligned_within_tolerance"]:
        blockers.append(
            "Audio and video presentation starts are not aligned within the "
            "declared technical tolerance."
        )
    return not blockers, blockers


def base_report(local: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now(),
        "target": {
            "dataset": "CaptainCook4D",
            "recording_id": RECORDING_ID,
            "source_group_id": SOURCE_GROUP_ID,
            "person_id": PERSON_ID,
            "environment_id": ENVIRONMENT_ID,
            "stream": STREAM,
            "official_url": OFFICIAL_URL,
            "box_shared_static_id": BOX_SHARED_STATIC_ID,
            "official_duration_seconds": OFFICIAL_DURATION_SECONDS,
        },
        "local_identity": dict(local),
        "policy": {
            "primary_proxy": PRIMARY_PROXY,
            "fallback_proxy": FALLBACK_PROXY,
            "fallback_only_after_primary_rejected_without_accepted_body": True,
            "maximum_persisted_response_payload_bytes": (
                MAX_PERSISTED_RESPONSE_BYTES
            ),
            "full_download_permitted": False,
            "range_ignored_response_body_read": False,
            "semantic_annotations_opened": False,
            "content_inspected_or_decoded": False,
            "v_plus_s_plus_a_asserted": False,
        },
        "scope": {
            "network_requests": 0,
            "accepted_response_payload_bytes": 0,
            "persisted_response_payload_bytes": 0,
            "full_media_downloads": 0,
            "temporary_media_deleted": True,
            "semantic_annotation_files_opened": 0,
            "frames_decoded": 0,
            "audio_samples_decoded": 0,
        },
        "proxy_selection_attempts": [],
        "range_requests": [],
        "exact_object": None,
        "iso_bmff": None,
        "ffprobe": None,
        "pyav_libavformat": None,
        "blockers": [],
        "final_marker": REPAIR,
    }


def run_live(local: Mapping[str, Any]) -> dict[str, Any]:
    report = base_report(local)
    session = requests.Session()
    session.trust_env = False
    temporary_path: Path | None = None
    try:
        proxy_name, proxy, first_byte, total, attempts = choose_proxy(session)
        report["proxy_selection_attempts"] = attempts
        report["scope"]["network_requests"] = len(attempts)
        accepted = len(first_byte)
        if total <= MAX_PERSISTED_RESPONSE_BYTES:
            raise NoGoError(
                "OBJECT_TOO_SMALL_FOR_DISJOINT_BOUNDED_HEAD_TAIL_PROBE"
            )

        head_start = 1
        head_end = HEAD_WINDOW_BYTES - 1
        tail_start = total - TAIL_WINDOW_BYTES
        tail_end = total - 1
        if tail_start <= head_end:
            raise NoGoError("HEAD_TAIL_WINDOWS_OVERLAP")

        with tempfile.TemporaryDirectory(
            prefix="cc4d-25_109-bounded-", dir="/tmp"
        ) as temporary_directory:
            temporary_path = Path(temporary_directory) / "asset.sparse.mp4"
            with temporary_path.open("w+b") as sparse:
                sparse.truncate(total)
                sparse.seek(0)
                sparse.write(first_byte)

                for label, start, end in (
                    ("head_remainder", head_start, head_end),
                    ("tail", tail_start, tail_end),
                ):
                    body, exchange, observed_total = request_range(
                        session,
                        proxy=proxy,
                        start=start,
                        end=end,
                        expected_total=total,
                    )
                    accepted += len(body)
                    if accepted > MAX_PERSISTED_RESPONSE_BYTES:
                        raise NoGoError(
                            "PERSISTED_RESPONSE_PAYLOAD_BUDGET_EXCEEDED"
                        )
                    sparse.seek(start)
                    sparse.write(body)
                    sparse.flush()
                    report["range_requests"].append(
                        {
                            "label": label,
                            "range": f"bytes={start}-{end}",
                            "proxy_name": proxy_name,
                            "proxy": proxy,
                            "exchange": exchange,
                            "observed_total_bytes": observed_total,
                        }
                    )
                    report["scope"]["network_requests"] += 1

                sparse.flush()
                os.fsync(sparse.fileno())

            intervals = [
                (0, HEAD_WINDOW_BYTES),
                (tail_start, total),
            ]
            iso = parse_iso_bmff(
                temporary_path,
                total=total,
                intervals=intervals,
            )
            external_ffprobe = ffprobe(temporary_path)
            libavformat = pyav_probe(temporary_path)

        temporary_path = None
        report["scope"]["temporary_media_deleted"] = True
        report["scope"]["accepted_response_payload_bytes"] = accepted
        report["scope"]["persisted_response_payload_bytes"] = accepted
        report["exact_object"] = {
            "official_url": OFFICIAL_URL,
            "box_shared_static_id": BOX_SHARED_STATIC_ID,
            "total_bytes_from_content_range": total,
            "selected_proxy_name": proxy_name,
            "selected_proxy": proxy,
            "head_window": {
                "start": 0,
                "end": HEAD_WINDOW_BYTES - 1,
                "bytes": HEAD_WINDOW_BYTES,
            },
            "tail_window": {
                "start": tail_start,
                "end": tail_end,
                "bytes": TAIL_WINDOW_BYTES,
            },
            "complete_object_checksum_computed": False,
            "full_object_downloaded": False,
        }
        report["iso_bmff"] = iso
        report["ffprobe"] = external_ffprobe
        report["pyav_libavformat"] = libavformat
        passed, blockers = technical_gates(iso)
        report["blockers"] = blockers
        report["final_marker"] = READY if passed else REPAIR
        return report
    except NoGoError as exc:
        report["blockers"] = [str(exc)]
        report["final_marker"] = NO_GO
        return report
    except ProxySelectionFailed as exc:
        report["proxy_selection_attempts"] = exc.attempts
        report["scope"]["network_requests"] = len(exc.attempts)
        report["blockers"] = [
            (
                "Neither the required https://proxy.example.invalid:3128 nor the permitted https://proxy.example.invalid:3128 "
                "fallback established a bounded HTTP 206 exchange. No "
                "response payload byte was accepted by the completed, "
                "recorded probe."
            ),
            (
                "Native audio parameters and shared A/V timeline evidence "
                "were not obtained."
            ),
        ]
        report["final_marker"] = REPAIR
        return report
    except ProbeError as exc:
        report["blockers"] = [str(exc)]
        report["final_marker"] = REPAIR
        return report
    finally:
        session.close()
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass
        report["scope"]["temporary_media_deleted"] = (
            temporary_path is None or not temporary_path.exists()
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Perform the bounded live Box range probe.",
    )
    args = parser.parse_args()

    local = validate_local_identity()
    if args.live:
        report = run_live(local)
    else:
        report = base_report(local)
        report["blockers"] = [
            (
                "Live bounded range probe was not requested; no network "
                "access or media parsing was performed."
            )
        ]
    atomic_write_json(args.output, report)
    print(report["final_marker"])
    return 0 if report["final_marker"] == READY else 1


if __name__ == "__main__":
    raise SystemExit(main())
