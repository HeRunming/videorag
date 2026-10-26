#!/usr/bin/env python3
"""Run a fail-closed, bounded ISO-BMFF probe of official EPIC P23_102.

The tool is deliberately restricted to one exact public HTTPS object.  It
performs a body-free HEAD followed by byte-range GETs, never requests the full
object, never persists response payload bytes, and never opens semantic
annotation data.  Container declarations are inspected without decoding media
samples.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import struct
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, Self
from urllib.parse import urlsplit

try:
    import httpx
except ImportError:  # pragma: no cover - checked by the live CLI
    httpx = None  # type: ignore[assignment]


SCHEMA_VERSION = "av-trace.epic-p23-102-bounded-av-probe/1.0"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    ROOT / "data/rehearsal_plan/epic_p23_102_bounded_av_probe_v1.json"
)
MD5_METADATA_PATH = (
    ROOT
    / "data/source_recon/assembly_epic_access_v2/metadata/epic/md5.csv"
)

VIDEO_ID = "P23_102"
OBJECT_PATH = "P23/videos/P23_102.MP4"
ASSET_URL = (
    "https://data.bris.ac.uk/datasets/"
    "2g1n6qdydwa9u22shpxqzp0t8m/P23/videos/P23_102.MP4"
)
EXPECTED_SIZE_BYTES = 10_814_161_307
EXPECTED_MD5 = "4698fcbf13782f6396029761eb3bd5f2"
EXPECTED_MD5_VERSION = "100"
EXPECTED_ETAG = '"5ea771bb-28493019b"'
EXPECTED_LAST_MODIFIED = "Mon, 27 Apr 2020 23:58:51 GMT"

DEFAULT_PROXIES = (
    "https://proxy.example.invalid:3128",
    "https://proxy.example.invalid:3128",
)
INITIAL_WINDOW_BYTES = 1024 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_RESPONSE_PAYLOAD_BYTES = 16 * 1024 * 1024
MAX_PERSISTED_RESPONSE_PAYLOAD_BYTES = 16 * 1024 * 1024
MAX_BOX_COUNT = 20_000
MAX_DEPTH = 12
MAX_METADATA_BOX_BYTES = 1024 * 1024
RETRYABLE_STATUSES = {401, 403, 407, 429, 502, 503, 504}

READY = "EPIC_P23_102_BOUNDED_AV_PROBE_READY"
REPAIR = "EPIC_P23_102_BOUNDED_AV_PROBE_REPAIR"
NO_GO = "EPIC_P23_102_BOUNDED_AV_PROBE_NO_GO"


class ProbeError(RuntimeError):
    """Stable failure code that does not retain transport exception text."""


class ConfigurationError(ProbeError):
    """Closed configuration or local-evidence failure."""


class TransferError(ProbeError):
    """Fail-closed HTTP or byte-accounting failure."""


class ContainerError(ProbeError):
    """Malformed or unsupported ISO-BMFF metadata."""


def utc_now() -> str:
    return (
        datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def load_official_md5_binding() -> dict[str, Any]:
    file_bytes = MD5_METADATA_PATH.read_bytes()
    rows = list(csv.DictReader(file_bytes.decode("utf-8").splitlines()))
    matches = [
        row
        for row in rows
        if row.get("file_remote_path") == OBJECT_PATH
        and row.get("version") == EXPECTED_MD5_VERSION
    ]
    if len(matches) != 1:
        raise ConfigurationError("OFFICIAL_MD5_EXACT_ROW_NOT_UNIQUE")
    row = matches[0]
    if row.get("md5") != EXPECTED_MD5:
        raise ConfigurationError("OFFICIAL_MD5_VALUE_MISMATCH")
    return {
        "metadata_path": str(MD5_METADATA_PATH.relative_to(ROOT)),
        "metadata_file_sha256": hashlib.sha256(file_bytes).hexdigest(),
        "object_path": row["file_remote_path"],
        "manifest_version": row["version"],
        "official_md5": row["md5"],
        "exact_row_match": True,
        "full_object_md5_recomputed": False,
        "claim": "OFFICIAL_METADATA_BOUND_NOT_FULL_FILE_VERIFIED",
    }


@dataclass(frozen=True)
class ExactAsset:
    url: str = ASSET_URL
    size_bytes: int = EXPECTED_SIZE_BYTES
    etag: str = EXPECTED_ETAG
    last_modified: str = EXPECTED_LAST_MODIFIED


@dataclass
class RequestRecord:
    method: str
    purpose: str
    proxy: str | None
    requested_range: str | None = None
    status: int | None = None
    content_length: int | None = None
    content_range: str | None = None
    response_payload_bytes_read: int = 0
    body_sha256: str | None = None
    outcome: str = "STARTED"

    def as_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "purpose": self.purpose,
            "proxy": self.proxy,
            "requested_range": self.requested_range,
            "status": self.status,
            "content_length": self.content_length,
            "content_range": self.content_range,
            "response_payload_bytes_read": self.response_payload_bytes_read,
            "body_sha256": self.body_sha256,
            "outcome": self.outcome,
        }


@dataclass
class ByteBudget:
    maximum_response_bytes: int = MAX_RESPONSE_BYTES
    maximum_total_bytes: int = MAX_RESPONSE_PAYLOAD_BYTES
    response_payload_bytes_read: int = 0
    maximum_observed_response_bytes: int = 0

    def preflight(self, requested: int) -> None:
        if requested <= 0:
            raise TransferError("INVALID_RANGE_LENGTH")
        if requested > self.maximum_response_bytes:
            raise TransferError("RANGE_EXCEEDS_PER_RESPONSE_CAP")
        if self.response_payload_bytes_read + requested > self.maximum_total_bytes:
            raise TransferError("RANGE_EXCEEDS_AGGREGATE_CAP")

    def consume(self, count: int, response_total: int) -> None:
        if count < 0:
            raise TransferError("NEGATIVE_BYTE_ACCOUNTING")
        if response_total > self.maximum_response_bytes:
            raise TransferError("RESPONSE_EXCEEDS_PER_RESPONSE_CAP")
        if self.response_payload_bytes_read + count > self.maximum_total_bytes:
            raise TransferError("AGGREGATE_RESPONSE_CAP_EXCEEDED")
        self.response_payload_bytes_read += count
        self.maximum_observed_response_bytes = max(
            self.maximum_observed_response_bytes, response_total
        )


def _proxy_label(proxy: str | None) -> str:
    if proxy is None:
        return "environment-or-direct"
    parsed = urlsplit(proxy)
    return (
        f"{parsed.hostname}:{parsed.port}"
        if parsed.hostname and parsed.port
        else "configured-proxy"
    )


def _validate_proxy(proxy: str) -> None:
    parsed = urlsplit(proxy)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise ConfigurationError("INVALID_PROXY")


class BoundedRangeClient:
    """Exact-object HEAD/range client with immediate Range-ignore abort."""

    def __init__(
        self,
        asset: ExactAsset,
        *,
        proxies: Sequence[str],
        budget: ByteBudget,
        clients: Sequence[Any] | None = None,
    ) -> None:
        if httpx is None:
            raise ConfigurationError("HTTPX_NOT_INSTALLED")
        parsed = urlsplit(asset.url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "data.bris.ac.uk"
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
        ):
            raise ConfigurationError("ASSET_URL_OUTSIDE_CLOSED_ALLOWLIST")
        for proxy in proxies:
            _validate_proxy(proxy)
        if clients is not None and proxies:
            raise ConfigurationError("CLIENTS_AND_PROXIES_MUTUALLY_EXCLUSIVE")
        self.asset = asset
        self.budget = budget
        self.records: list[RequestRecord] = []
        self._cache: list[tuple[int, bytes]] = []
        self._owns_clients = clients is None
        if clients is not None:
            self._routes = [(None, client) for client in clients]
        else:
            routes = list(proxies) if proxies else [None]
            self._routes: list[tuple[str | None, Any]] = []
            for proxy in routes:
                kwargs: dict[str, Any] = {
                    "follow_redirects": False,
                    "timeout": httpx.Timeout(45.0, connect=20.0),
                    "headers": {
                        "User-Agent": (
                            "AV-TRACE-EPIC-P23-102-Bounded-AV-Probe/1.0"
                        )
                    },
                }
                if proxy is None:
                    kwargs["trust_env"] = True
                else:
                    kwargs["trust_env"] = False
                    kwargs["proxy"] = proxy
                self._routes.append((proxy, httpx.Client(**kwargs)))

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self.release_payload_bytes()
        if self._owns_clients:
            for _, client in self._routes:
                client.close()

    def release_payload_bytes(self) -> None:
        self._cache.clear()

    @staticmethod
    def _integer_header(headers: Mapping[str, str], name: str) -> int:
        value = headers.get(name)
        if value is None or not value.isdigit():
            raise TransferError(f"MISSING_OR_INVALID_{name.upper().replace('-', '_')}")
        return int(value)

    def head(self) -> dict[str, Any]:
        last_code = "NO_PROXY_ROUTE_SUCCEEDED"
        for proxy, client in self._routes:
            record = RequestRecord(
                method="HEAD",
                purpose="exact-object-identity",
                proxy=_proxy_label(proxy),
            )
            self.records.append(record)
            try:
                with client.stream(
                    "HEAD",
                    self.asset.url,
                    headers={"Accept-Encoding": "identity"},
                ) as response:
                    record.status = response.status_code
                    if response.status_code in RETRYABLE_STATUSES:
                        record.outcome = f"RETRYABLE_HTTP_{response.status_code}"
                        last_code = record.outcome
                        continue
                    if response.status_code != 200:
                        raise TransferError("UNEXPECTED_HEAD_STATUS")
                    content_length = self._integer_header(
                        response.headers, "content-length"
                    )
                    record.content_length = content_length
                    observed = {
                        "status": response.status_code,
                        "content_length": content_length,
                        "etag": response.headers.get("etag"),
                        "last_modified": response.headers.get("last-modified"),
                        "content_type": response.headers.get("content-type"),
                        "accept_ranges": response.headers.get("accept-ranges"),
                        "proxy": _proxy_label(proxy),
                    }
                    checks = {
                        "size_match": content_length == self.asset.size_bytes,
                        "etag_match": observed["etag"] == self.asset.etag,
                        "last_modified_match": (
                            observed["last_modified"]
                            == self.asset.last_modified
                        ),
                        "content_type_mp4": (
                            str(observed["content_type"])
                            .split(";", 1)[0]
                            .strip()
                            .lower()
                            == "video/mp4"
                        ),
                        "accept_ranges_bytes": (
                            str(observed["accept_ranges"]).strip().lower()
                            == "bytes"
                        ),
                    }
                    record.outcome = "SUCCEEDED"
                    return {
                        "observed": observed,
                        "checks": checks,
                        "identity_match": all(checks.values()),
                    }
            except ProbeError as exc:
                record.outcome = str(exc)
                raise
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                record.outcome = (
                    f"HTTP_TRANSPORT_{type(exc).__name__.upper()}"
                )
                last_code = record.outcome
                continue
        raise TransferError(last_code)

    def fetch_range(self, start: int, end: int, purpose: str) -> bytes:
        if start < 0 or end < start or end >= self.asset.size_bytes:
            raise TransferError("RANGE_OUTSIDE_EXACT_OBJECT")
        if start == 0 and end == self.asset.size_bytes - 1:
            raise TransferError("FULL_OBJECT_RANGE_PROHIBITED")
        expected = end - start + 1
        self.budget.preflight(expected)
        last_code = "NO_PROXY_ROUTE_SUCCEEDED"
        for proxy, client in self._routes:
            record = RequestRecord(
                method="GET",
                purpose=purpose,
                proxy=_proxy_label(proxy),
                requested_range=f"bytes={start}-{end}",
            )
            self.records.append(record)
            try:
                with client.stream(
                    "GET",
                    self.asset.url,
                    headers={
                        "Accept-Encoding": "identity",
                        "Range": f"bytes={start}-{end}",
                    },
                ) as response:
                    record.status = response.status_code
                    if response.status_code in RETRYABLE_STATUSES:
                        record.outcome = f"RETRYABLE_HTTP_{response.status_code}"
                        last_code = record.outcome
                        continue
                    # This check occurs before iterating one body byte.
                    if response.status_code == 200:
                        record.outcome = "RANGE_IGNORED_FULL_TRANSFER_ABORTED"
                        raise TransferError(record.outcome)
                    if response.status_code != 206:
                        raise TransferError("UNEXPECTED_RANGE_STATUS")
                    content_length = self._integer_header(
                        response.headers, "content-length"
                    )
                    record.content_length = content_length
                    if content_length != expected:
                        raise TransferError("RANGE_CONTENT_LENGTH_MISMATCH")
                    expected_content_range = (
                        f"bytes {start}-{end}/{self.asset.size_bytes}"
                    )
                    record.content_range = response.headers.get("content-range")
                    if record.content_range != expected_content_range:
                        raise TransferError("CONTENT_RANGE_MISMATCH")
                    if (
                        response.headers.get("content-encoding", "identity").lower()
                        != "identity"
                    ):
                        raise TransferError("UNEXPECTED_CONTENT_ENCODING")
                    body = bytearray()
                    digest = hashlib.sha256()
                    for chunk in response.iter_bytes():
                        next_total = len(body) + len(chunk)
                        if next_total > expected:
                            raise TransferError("RANGE_RESPONSE_EXCESS_BYTES")
                        self.budget.consume(len(chunk), next_total)
                        record.response_payload_bytes_read += len(chunk)
                        digest.update(chunk)
                        body.extend(chunk)
                    if len(body) != expected:
                        raise TransferError("RANGE_RESPONSE_TRUNCATED")
                    record.body_sha256 = digest.hexdigest()
                    record.outcome = "SUCCEEDED"
                    result = bytes(body)
                    self._add_cache(start, result)
                    return result
            except ProbeError as exc:
                if record.outcome == "STARTED":
                    record.outcome = str(exc)
                raise
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                record.outcome = (
                    f"HTTP_TRANSPORT_{type(exc).__name__.upper()}"
                )
                last_code = record.outcome
                continue
        raise TransferError(last_code)

    def _add_cache(self, start: int, body: bytes) -> None:
        self._cache.append((start, body))
        self._cache.sort(key=lambda item: item[0])
        merged: list[tuple[int, bytes]] = []
        for span_start, span_body in self._cache:
            if not merged:
                merged.append((span_start, span_body))
                continue
            old_start, old_body = merged[-1]
            old_end = old_start + len(old_body)
            if span_start > old_end:
                merged.append((span_start, span_body))
                continue
            overlap = old_end - span_start
            if overlap < len(span_body):
                merged[-1] = (
                    old_start,
                    old_body + span_body[max(overlap, 0) :],
                )
        self._cache = merged

    def read(self, start: int, length: int, purpose: str) -> bytes:
        if length <= 0 or start < 0 or start + length > self.asset.size_bytes:
            raise TransferError("READ_OUTSIDE_EXACT_OBJECT")
        end = start + length
        cursor = start
        parts: list[bytes] = []
        while cursor < end:
            containing = next(
                (
                    (span_start, body)
                    for span_start, body in self._cache
                    if span_start <= cursor < span_start + len(body)
                ),
                None,
            )
            if containing is not None:
                span_start, body = containing
                take = min(end, span_start + len(body)) - cursor
                relative = cursor - span_start
                parts.append(body[relative : relative + take])
                cursor += take
                continue
            next_cached = min(
                (
                    span_start
                    for span_start, _ in self._cache
                    if span_start > cursor
                ),
                default=end,
            )
            fetch_end = min(
                end,
                next_cached,
                cursor + self.budget.maximum_response_bytes,
            )
            body = self.fetch_range(
                cursor, fetch_end - 1, f"{purpose}:fill"
            )
            parts.append(body)
            cursor = fetch_end
        result = b"".join(parts)
        if len(result) != length:
            raise TransferError("READ_LENGTH_ACCOUNTING_MISMATCH")
        return result


class ByteReader(Protocol):
    def read(self, start: int, length: int, purpose: str) -> bytes: ...


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

    def safe_type(self) -> str:
        try:
            return self.type.decode("ascii")
        except UnicodeDecodeError:
            return self.type.hex()


class BoxIndex:
    def __init__(self, reader: ByteReader, total_size: int) -> None:
        self.reader = reader
        self.total_size = total_size
        self.box_count = 0

    def header(self, offset: int, parent_end: int, purpose: str) -> Box:
        if offset < 0 or parent_end > self.total_size or offset + 8 > parent_end:
            raise ContainerError("TRUNCATED_BOX_HEADER")
        prefix = self.reader.read(offset, min(32, parent_end - offset), purpose)
        size32, box_type = struct.unpack_from(">I4s", prefix, 0)
        header_size = 8
        if size32 == 1:
            if len(prefix) < 16:
                raise ContainerError("TRUNCATED_EXTENDED_BOX_HEADER")
            size = struct.unpack_from(">Q", prefix, 8)[0]
            header_size = 16
        elif size32 == 0:
            size = parent_end - offset
        else:
            size = size32
        if box_type == b"uuid":
            header_size += 16
        if size < header_size or offset + size > parent_end:
            raise ContainerError("INVALID_BOX_SIZE")
        return Box(offset, size, box_type, header_size)

    def children(
        self, start: int, end: int, *, depth: int, purpose: str
    ) -> list[Box]:
        if depth > MAX_DEPTH:
            raise ContainerError("MAXIMUM_BOX_DEPTH_EXCEEDED")
        boxes: list[Box] = []
        cursor = start
        while cursor < end:
            self.box_count += 1
            if self.box_count > MAX_BOX_COUNT:
                raise ContainerError("MAXIMUM_BOX_COUNT_EXCEEDED")
            box = self.header(cursor, end, purpose)
            boxes.append(box)
            if box.end <= cursor:
                raise ContainerError("NON_ADVANCING_BOX")
            cursor = box.end
        if cursor != end:
            raise ContainerError("CHILD_BOXES_DO_NOT_FILL_PARENT")
        return boxes


def _exactly_one(boxes: Sequence[Box], box_type: bytes) -> Box:
    matches = [box for box in boxes if box.type == box_type]
    if len(matches) != 1:
        label = box_type.decode("latin1").upper()
        raise ContainerError(f"EXPECTED_ONE_{label}_BOX")
    return matches[0]


def _optional_one(boxes: Sequence[Box], box_type: bytes) -> Box | None:
    matches = [box for box in boxes if box.type == box_type]
    if len(matches) > 1:
        label = box_type.decode("latin1").upper()
        raise ContainerError(f"DUPLICATE_{label}_BOX")
    return matches[0] if matches else None


def _read_box(reader: ByteReader, box: Box, purpose: str) -> bytes:
    if box.size > MAX_METADATA_BOX_BYTES:
        raise ContainerError("METADATA_BOX_EXCEEDS_BOUNDED_READ_CAP")
    return reader.read(box.offset, box.size, purpose)


def _full_box_duration(data: bytes, box: Box, name: str) -> tuple[int, int]:
    payload = data[box.header_size :]
    if len(payload) < 20:
        raise ContainerError(f"TRUNCATED_{name}")
    version = payload[0]
    if version == 0:
        timescale = struct.unpack_from(">I", payload, 12)[0]
        duration = struct.unpack_from(">I", payload, 16)[0]
    elif version == 1:
        if len(payload) < 32:
            raise ContainerError(f"TRUNCATED_{name}_V1")
        timescale = struct.unpack_from(">I", payload, 20)[0]
        duration = struct.unpack_from(">Q", payload, 24)[0]
    else:
        raise ContainerError(f"UNSUPPORTED_{name}_VERSION")
    if timescale <= 0 or duration <= 0:
        raise ContainerError(f"INVALID_{name}_DURATION")
    return timescale, duration


def _tkhd(data: bytes, box: Box) -> tuple[bool, int | None]:
    payload = data[box.header_size :]
    if len(payload) < 24:
        raise ContainerError("TRUNCATED_TKHD")
    enabled = bool(int.from_bytes(payload[1:4], "big") & 1)
    version = payload[0]
    if version == 0:
        duration = struct.unpack_from(">I", payload, 20)[0]
        unknown = 0xFFFFFFFF
    elif version == 1:
        if len(payload) < 36:
            raise ContainerError("TRUNCATED_TKHD_V1")
        duration = struct.unpack_from(">Q", payload, 28)[0]
        unknown = 0xFFFFFFFFFFFFFFFF
    else:
        raise ContainerError("UNSUPPORTED_TKHD_VERSION")
    return enabled, None if duration in {0, unknown} else duration


def _handler(data: bytes, box: Box) -> str:
    payload = data[box.header_size :]
    if len(payload) < 12:
        raise ContainerError("TRUNCATED_HDLR")
    return payload[8:12].decode("latin1")


def _parse_descriptors(payload: bytes) -> tuple[int | None, int | None]:
    object_type: int | None = None
    audio_object_type: int | None = None
    index = 0
    while index + 2 <= len(payload):
        tag = payload[index]
        index += 1
        length = 0
        for _ in range(4):
            if index >= len(payload):
                return object_type, audio_object_type
            byte = payload[index]
            index += 1
            length = (length << 7) | (byte & 0x7F)
            if not byte & 0x80:
                break
        end = min(len(payload), index + length)
        body = payload[index:end]
        nested = body
        if tag == 0x03 and len(body) >= 3:
            flags = body[2]
            nested_offset = 3
            if flags & 0x80:
                nested_offset += 2
            if flags & 0x40:
                if nested_offset >= len(body):
                    return object_type, audio_object_type
                nested_offset += 1 + body[nested_offset]
            if flags & 0x20:
                nested_offset += 2
            nested = body[nested_offset:]
        elif tag == 0x04 and body:
            object_type = body[0]
            nested = body[13:] if len(body) >= 13 else b""
        elif tag == 0x05 and body:
            audio_object_type = (body[0] >> 3) & 0x1F
            nested = b""
        nested_object, nested_audio = _parse_descriptors(nested)
        object_type = object_type if object_type is not None else nested_object
        audio_object_type = (
            audio_object_type if audio_object_type is not None else nested_audio
        )
        index = end
    return object_type, audio_object_type


def _codec_label(
    sample_entry: str,
    object_type: int | None,
    audio_object_type: int | None,
) -> str:
    if sample_entry == "mp4a" and object_type == 0x40:
        names = {1: "AAC Main", 2: "AAC LC", 5: "HE-AAC"}
        return names.get(audio_object_type, "MPEG-4 Audio")
    return sample_entry


def _sample_entry(data: bytes, box: Box, handler: str) -> dict[str, Any]:
    payload = data[box.header_size :]
    if len(payload) < 8:
        raise ContainerError("TRUNCATED_STSD")
    entry_count = struct.unpack_from(">I", payload, 4)[0]
    if entry_count < 1:
        raise ContainerError("STSD_HAS_NO_SAMPLE_ENTRY")
    entry_offset = 8
    if entry_offset + 8 > len(payload):
        raise ContainerError("TRUNCATED_SAMPLE_ENTRY")
    entry_size, entry_type_raw = struct.unpack_from(">I4s", payload, entry_offset)
    if entry_size < 8 or entry_offset + entry_size > len(payload):
        raise ContainerError("INVALID_SAMPLE_ENTRY_SIZE")
    entry_type = entry_type_raw.decode("latin1")
    entry = payload[entry_offset : entry_offset + entry_size]
    result: dict[str, Any] = {
        "sample_entry": entry_type,
        "sample_entry_count": entry_count,
    }
    if handler == "soun":
        if len(entry) < 36:
            raise ContainerError("TRUNCATED_AUDIO_SAMPLE_ENTRY")
        version = struct.unpack_from(">H", entry, 16)[0]
        channels = struct.unpack_from(">H", entry, 24)[0]
        sample_size_bits = struct.unpack_from(">H", entry, 26)[0]
        sample_rate = struct.unpack_from(">I", entry, 32)[0] / 65536
        child_start = {0: 36, 1: 52, 2: 72}.get(version, 36)
        object_type: int | None = None
        audio_object_type: int | None = None
        cursor = child_start
        while cursor + 8 <= len(entry):
            child_size, child_type = struct.unpack_from(">I4s", entry, cursor)
            if child_size < 8 or cursor + child_size > len(entry):
                break
            if child_type == b"esds":
                descriptor_payload = entry[cursor + 12 : cursor + child_size]
                object_type, audio_object_type = _parse_descriptors(
                    descriptor_payload
                )
            cursor += child_size
        result.update(
            {
                "codec": _codec_label(
                    entry_type, object_type, audio_object_type
                ),
                "codec_object_type_indication": (
                    f"0x{object_type:02x}" if object_type is not None else None
                ),
                "audio_object_type": audio_object_type,
                "channels": channels,
                "sample_size_bits": sample_size_bits,
                "sample_rate_hz": int(sample_rate),
            }
        )
    elif handler == "vide":
        result["codec"] = entry_type
    return result


def _edit_list(
    data: bytes,
    box: Box,
    *,
    movie_timescale: int,
) -> dict[str, Any]:
    payload = data[box.header_size :]
    if len(payload) < 8:
        raise ContainerError("TRUNCATED_ELST")
    version = payload[0]
    count = struct.unpack_from(">I", payload, 4)[0]
    cursor = 8
    entries: list[dict[str, Any]] = []
    for _ in range(count):
        if version == 0:
            if cursor + 12 > len(payload):
                raise ContainerError("TRUNCATED_ELST_V0_ENTRY")
            segment_duration = struct.unpack_from(">I", payload, cursor)[0]
            media_time = struct.unpack_from(">i", payload, cursor + 4)[0]
            cursor += 12
        elif version == 1:
            if cursor + 20 > len(payload):
                raise ContainerError("TRUNCATED_ELST_V1_ENTRY")
            segment_duration = struct.unpack_from(">Q", payload, cursor)[0]
            media_time = struct.unpack_from(">q", payload, cursor + 8)[0]
            cursor += 20
        else:
            raise ContainerError("UNSUPPORTED_ELST_VERSION")
        entries.append(
            {
                "segment_duration_units": segment_duration,
                "segment_duration_seconds": (
                    segment_duration / movie_timescale
                ),
                "media_time_units": media_time,
            }
        )
    leading_empty = 0.0
    for entry in entries:
        if entry["media_time_units"] == -1:
            leading_empty += entry["segment_duration_seconds"]
        else:
            break
    return {
        "entry_count": count,
        "leading_empty_seconds": leading_empty,
        "presentation_duration_seconds": sum(
            entry["segment_duration_seconds"] for entry in entries
        ),
        "entries": entries,
    }


def inspect_iso_bmff(
    reader: ByteReader,
    total_size: int,
) -> dict[str, Any]:
    index = BoxIndex(reader, total_size)
    top = index.children(
        0, total_size, depth=1, purpose="top-level-box-header"
    )
    ftyp = _exactly_one(top, b"ftyp")
    moov = _exactly_one(top, b"moov")
    if any(box.type == b"moof" for box in top):
        raise ContainerError("FRAGMENTED_MP4_UNSUPPORTED")
    ftyp_data = _read_box(reader, ftyp, "read-ftyp")
    ftyp_payload = ftyp_data[ftyp.header_size :]
    if len(ftyp_payload) < 8 or len(ftyp_payload) % 4:
        raise ContainerError("MALFORMED_FTYP")
    major_brand = ftyp_payload[:4].decode("latin1")
    compatible_brands = [
        ftyp_payload[offset : offset + 4].decode("latin1")
        for offset in range(8, len(ftyp_payload), 4)
    ]

    moov_children = index.children(
        moov.payload_start,
        moov.end,
        depth=2,
        purpose="moov-child-header",
    )
    mvhd = _exactly_one(moov_children, b"mvhd")
    movie_timescale, movie_duration_units = _full_box_duration(
        _read_box(reader, mvhd, "read-mvhd"), mvhd, "MVHD"
    )
    movie_duration = movie_duration_units / movie_timescale

    tracks: list[dict[str, Any]] = []
    for track_number, trak in enumerate(
        (box for box in moov_children if box.type == b"trak"), start=1
    ):
        trak_children = index.children(
            trak.payload_start,
            trak.end,
            depth=3,
            purpose=f"trak-{track_number}-child-header",
        )
        tkhd = _exactly_one(trak_children, b"tkhd")
        enabled, tkhd_duration_units = _tkhd(
            _read_box(reader, tkhd, f"read-tkhd-{track_number}"), tkhd
        )
        mdia = _exactly_one(trak_children, b"mdia")
        mdia_children = index.children(
            mdia.payload_start,
            mdia.end,
            depth=4,
            purpose=f"mdia-{track_number}-child-header",
        )
        mdhd = _exactly_one(mdia_children, b"mdhd")
        media_timescale, media_duration_units = _full_box_duration(
            _read_box(reader, mdhd, f"read-mdhd-{track_number}"),
            mdhd,
            "MDHD",
        )
        hdlr = _exactly_one(mdia_children, b"hdlr")
        handler = _handler(
            _read_box(reader, hdlr, f"read-hdlr-{track_number}"), hdlr
        )
        minf = _exactly_one(mdia_children, b"minf")
        minf_children = index.children(
            minf.payload_start,
            minf.end,
            depth=5,
            purpose=f"minf-{track_number}-child-header",
        )
        stbl = _exactly_one(minf_children, b"stbl")
        stbl_children = index.children(
            stbl.payload_start,
            stbl.end,
            depth=6,
            purpose=f"stbl-{track_number}-child-header",
        )
        stsd = _exactly_one(stbl_children, b"stsd")
        sample_entry = _sample_entry(
            _read_box(reader, stsd, f"read-stsd-{track_number}"),
            stsd,
            handler,
        )

        edit: dict[str, Any] | None = None
        edts = _optional_one(trak_children, b"edts")
        if edts is not None:
            edts_children = index.children(
                edts.payload_start,
                edts.end,
                depth=4,
                purpose=f"edts-{track_number}-child-header",
            )
            elst = _optional_one(edts_children, b"elst")
            if elst is not None:
                edit = _edit_list(
                    _read_box(reader, elst, f"read-elst-{track_number}"),
                    elst,
                    movie_timescale=movie_timescale,
                )
        presentation_duration = (
            edit["presentation_duration_seconds"]
            if edit is not None
            else (
                tkhd_duration_units / movie_timescale
                if tkhd_duration_units is not None
                else media_duration_units / media_timescale
            )
        )
        tracks.append(
            {
                "track_number": track_number,
                "enabled": enabled,
                "handler_type": handler,
                "media_timescale": media_timescale,
                "media_duration_units": media_duration_units,
                "media_duration_seconds": (
                    media_duration_units / media_timescale
                ),
                "movie_duration_units": tkhd_duration_units,
                "movie_duration_seconds": (
                    tkhd_duration_units / movie_timescale
                    if tkhd_duration_units is not None
                    else None
                ),
                "presentation_start_seconds": (
                    edit["leading_empty_seconds"] if edit else 0.0
                ),
                "presentation_duration_seconds": presentation_duration,
                "edit_list": edit,
                **sample_entry,
            }
        )

    video_tracks = [
        track
        for track in tracks
        if track["handler_type"] == "vide" and track["enabled"]
    ]
    audio_tracks = [
        track
        for track in tracks
        if track["handler_type"] == "soun" and track["enabled"]
    ]
    timeline = timeline_assessment(
        movie_duration, video_tracks, audio_tracks
    )
    return {
        "container": "ISO_BASE_MEDIA_FILE_FORMAT",
        "major_brand": major_brand,
        "compatible_brands": compatible_brands,
        "top_level_boxes": [
            {
                "type": box.safe_type(),
                "offset": box.offset,
                "size": box.size,
            }
            for box in top
        ],
        "moov_offset": moov.offset,
        "moov_size": moov.size,
        "movie_timescale": movie_timescale,
        "movie_duration_units": movie_duration_units,
        "duration_seconds": movie_duration,
        "tracks": tracks,
        "video_track_count": len(video_tracks),
        "audio_track_count": len(audio_tracks),
        "timeline": timeline,
        "box_headers_inspected": index.box_count,
    }


def timeline_assessment(
    movie_duration: float,
    video_tracks: Sequence[Mapping[str, Any]],
    audio_tracks: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if not video_tracks or not audio_tracks:
        return {
            "status": "MISSING_AUDIO_OR_VIDEO",
            "shared_movie_timeline": False,
            "plausibly_synchronized": False,
        }
    selected = [video_tracks[0], audio_tracks[0]]
    starts = [float(track["presentation_start_seconds"]) for track in selected]
    durations = [
        float(track["presentation_duration_seconds"]) for track in selected
    ]
    tolerance = max(2.0, movie_duration * 0.005)
    start_delta = max(starts) - min(starts)
    duration_delta = max(durations) - min(durations)
    close_to_movie = all(
        abs((start + duration) - movie_duration) <= tolerance
        for start, duration in zip(starts, durations, strict=True)
    )
    synchronized = (
        start_delta <= 0.1
        and duration_delta <= tolerance
        and close_to_movie
    )
    return {
        "status": (
            "SHARED_MOVIE_TIMELINE_PLAUSIBLY_SYNCHRONIZED"
            if synchronized
            else "SHARED_MOVIE_TIMELINE_NOT_PLAUSIBLY_SYNCHRONIZED"
        ),
        "shared_movie_timeline": True,
        "plausibly_synchronized": synchronized,
        "start_delta_seconds": start_delta,
        "duration_delta_seconds": duration_delta,
        "tolerance_seconds": tolerance,
        "sample_level_sync_decoded_or_verified": False,
    }


def classify(
    *,
    identity_match: bool,
    range_verified: bool,
    container: Mapping[str, Any] | None,
    terminal_error: str | None,
) -> tuple[str, list[str]]:
    blockers: list[str] = []
    if not identity_match:
        blockers.append("Exact object HEAD identity did not match.")
    if not range_verified:
        blockers.append("Validated HTTP byte-range access was not established.")
    if container is None:
        blockers.append("Bounded ISO-BMFF metadata inspection did not complete.")
    else:
        if int(container.get("video_track_count", 0)) < 1:
            blockers.append("No enabled native video track was declared.")
        if int(container.get("audio_track_count", 0)) < 1:
            blockers.append("No enabled native audio track was declared.")
        timeline = container.get("timeline", {})
        if not isinstance(timeline, Mapping) or not timeline.get(
            "plausibly_synchronized"
        ):
            blockers.append(
                "A shared plausibly synchronized audio/video timeline "
                "was not established."
            )
    if not blockers:
        return READY, []
    terminal_codes = {
        "HEAD_IDENTITY_MISMATCH",
        "RANGE_IGNORED_FULL_TRANSFER_ABORTED",
        "NO_ENABLED_AUDIO_TRACK",
        "NO_ENABLED_VIDEO_TRACK",
        "TIMELINE_NOT_PLAUSIBLY_SYNCHRONIZED",
    }
    return (NO_GO if terminal_error in terminal_codes else REPAIR), blockers


def run_live(proxies: Sequence[str]) -> dict[str, Any]:
    asset = ExactAsset()
    md5_binding = load_official_md5_binding()
    budget = ByteBudget()
    head_result: dict[str, Any] | None = None
    container: dict[str, Any] | None = None
    terminal_error: str | None = None
    range_verified = False
    records: list[dict[str, Any]] = []
    payloads_released = False

    client = BoundedRangeClient(
        asset,
        proxies=proxies,
        budget=budget,
    )
    try:
        head_result = client.head()
        if not head_result["identity_match"]:
            terminal_error = "HEAD_IDENTITY_MISMATCH"
        else:
            client.fetch_range(
                0,
                INITIAL_WINDOW_BYTES - 1,
                "initial-head-window",
            )
            tail_start = asset.size_bytes - INITIAL_WINDOW_BYTES
            client.fetch_range(
                tail_start,
                asset.size_bytes - 1,
                "initial-tail-window",
            )
            range_verified = True
            container = inspect_iso_bmff(client, asset.size_bytes)
            if container["audio_track_count"] < 1:
                terminal_error = "NO_ENABLED_AUDIO_TRACK"
            elif container["video_track_count"] < 1:
                terminal_error = "NO_ENABLED_VIDEO_TRACK"
            elif not container["timeline"]["plausibly_synchronized"]:
                terminal_error = "TIMELINE_NOT_PLAUSIBLY_SYNCHRONIZED"
    except ProbeError as exc:
        terminal_error = str(exc)
    finally:
        records = [record.as_dict() for record in client.records]
        client.release_payload_bytes()
        payloads_released = True
        client.close()

    identity_match = bool(head_result and head_result["identity_match"])
    marker, blockers = classify(
        identity_match=identity_match,
        range_verified=range_verified,
        container=container,
        terminal_error=terminal_error,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "audit_date": "2026-10-12",
        "final_marker": marker,
        "scope": {
            "exact_asset_only": True,
            "live_probe": True,
            "full_download_performed": False,
            "media_samples_decoded": False,
            "media_content_reviewed": False,
            "semantic_labels_opened_or_used": False,
            "v_plus_s_plus_a_claimed": False,
        },
        "exact_asset": {
            "video_id": VIDEO_ID,
            "url": ASSET_URL,
            "object_path": OBJECT_PATH,
            "expected_total_size_bytes": EXPECTED_SIZE_BYTES,
            "official_md5_metadata": md5_binding,
        },
        "head_identity": head_result,
        "range_support": {
            "verified": range_verified,
            "basis": (
                "At least two 206 responses with exact Content-Range totals."
                if range_verified
                else "Not established."
            ),
            "server_ignore_range_fail_closed": True,
        },
        "container_probe": container,
        "byte_accounting": {
            "response_payload_bytes_read": (
                budget.response_payload_bytes_read
            ),
            "maximum_observed_response_bytes": (
                budget.maximum_observed_response_bytes
            ),
            "response_payload_cap_bytes": MAX_RESPONSE_PAYLOAD_BYTES,
            "persisted_response_payload_bytes": 0,
            "persisted_response_payload_cap_bytes": (
                MAX_PERSISTED_RESPONSE_PAYLOAD_BYTES
            ),
            "temporary_media_files_created": 0,
            "in_memory_payloads_released_after_inspection": payloads_released,
            "request_records": records,
        },
        "decision": {
            "marker": marker,
            "blockers": blockers,
            "terminal_error": terminal_error,
        },
        "claim_boundaries": [
            (
                "The official MD5 value is bound from exact official metadata; "
                "the 10.8 GB object was not downloaded or hashed in full."
            ),
            (
                "Track and timeline findings are ISO-BMFF declarations only; no "
                "audio or video sample was decoded, heard, viewed, or reviewed."
            ),
            (
                "Plausible synchronization means shared movie-time metadata and "
                "closely matched declared presentation intervals, not decoded "
                "sample-level synchronization."
            ),
            (
                "No semantic label, media-content, V+S+A, suitability, rights, "
                "privacy, annotation, or redistribution claim is made."
            ),
        ],
        "reproduction": {
            "command": (
                "python tools/epic_p23_102_bounded_av_probe.py --live "
                "--proxy https://proxy.example.invalid:3128 "
                "--proxy https://proxy.example.invalid:3128"
            ),
            "ordered_proxy_policy": [
                "https://proxy.example.invalid:3128",
                "https://proxy.example.invalid:3128",
            ],
        },
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        required=True,
        help="Required acknowledgement that this performs bounded live I/O.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--proxy",
        action="append",
        default=[],
        help="Ordered explicit proxy; repeat for failover.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    proxies = tuple(args.proxy) if args.proxy else DEFAULT_PROXIES
    try:
        report = run_live(proxies)
        atomic_write_json(args.output, report)
        print(report["final_marker"])
        return 0 if report["final_marker"] == READY else 2
    except (OSError, ValueError, csv.Error, json.JSONDecodeError) as exc:
        print(
            f"ERROR:LOCAL_{type(exc).__name__.upper()}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
