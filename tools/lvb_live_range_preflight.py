#!/usr/bin/env python3
"""Live authenticated, bounded HTTP Range preflight for LongVideoBench.

This tool indexes tar headers only.  It deliberately has no media-download mode.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import io
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence, TextIO
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

try:
    import httpx
except ImportError:  # pragma: no cover - checked by CLI
    httpx = None  # type: ignore[assignment]

REPOSITORY = "longvideobench/LongVideoBench"
REVISION = "60d1c89c1919a198b73be39c2babb213b29d6a5c"
BLOCK_SIZE = 512
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_REDIRECTS = 8
DEFAULT_PROGRESS_EVERY = 1000
EVIDENCE_REL = Path(
    "data/access_review/evidence/"
    "lvb_LongVideoBench_api_2026-09-08_rev-"
    f"{REVISION}.json"
)
PARTS_REL = Path("data/acquisition_preflight/lvb_tar_parts.csv")
VIDEO_RANGES_REL = Path("data/acquisition_preflight/lvb_five_member_ranges.csv")
SUBTITLE_RANGES_REL = Path("data/acquisition_preflight/lvb_subtitle_ranges.csv")
MANIFEST_REL = Path("data/acquisition_preflight/lvb_range_probe_manifest.json")
REVIEW_REL = Path("docs/review/lvb_tar_range_preflight.md")

TARGETS: tuple[tuple[str, str], ...] = (
    ("ccp-008", "-PgbM2MhcYQ"),
    ("ccp-009", "-eRimFrm6kQ"),
    ("ccp-003", "-7wwfGJXEZg"),
    ("ccp-011", "H5vpBCLo74U"),
    ("ccp-012", "TMe7oXMJoSM"),
)

# Hugging Face's pinned resolver can redirect large LFS/Xet objects to these
# service families. Authorization is sent only within the canonical resolver's
# exact HTTPS origin, never to an effective/CDN host.
ALLOWED_REDIRECT_HOST_SUFFIXES = (
    "huggingface.co",
    ".huggingface.co",
    ".hf.co",
    ".xethub.hf.co",
)
REDIRECT_CODES = {301, 302, 303, 307, 308}
SIGNED_URL_REFRESH_STATUSES = {400, 401, 403}
CONTENT_RANGE_RE = re.compile(r"^bytes (\d+)-(\d+)/(\d+)$")


class PreflightError(RuntimeError):
    """A safe, credential-free preflight error."""


class ConfigurationError(PreflightError):
    pass


class SafetyError(PreflightError):
    pass


class TarFormatError(PreflightError):
    pass


@dataclass(frozen=True)
class Part:
    index: int
    name: str
    size: int
    start: int
    end_inclusive: int
    sha256: str
    metadata_source: str


@dataclass
class RequestRecord:
    request_id: str
    filename: str
    method: str
    requested_range: str | None
    purpose: str
    canonical_url: str
    response_status: int | None = None
    content_length: int | None = None
    content_range: str | None = None
    accept_ranges: str | None = None
    effective_host: str | None = None
    redirect_chain: list[dict[str, Any]] = field(default_factory=list)
    bytes_received: int = 0
    sha256: str | None = None
    error_code: str | None = None
    url_has_query: bool = False
    credentials_or_query_secrets_recorded: bool = False

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class Budget:
    maximum_response_bytes: int = MAX_RESPONSE_BYTES
    maximum_total_bytes: int = MAX_TOTAL_BYTES
    total_bytes: int = 0
    maximum_observed: int = 0

    def account(self, count: int) -> None:
        if count < 0:
            raise SafetyError("NEGATIVE_BYTE_ACCOUNTING")
        if count > self.maximum_response_bytes:
            raise SafetyError("RESPONSE_BODY_LIMIT_EXCEEDED")
        if self.total_bytes + count > self.maximum_total_bytes:
            raise SafetyError("TOTAL_RESPONSE_BODY_LIMIT_EXCEEDED")
        self.total_bytes += count
        self.maximum_observed = max(self.maximum_observed, count)


@dataclass(frozen=True)
class FetchResult:
    body: bytes
    record: RequestRecord


@dataclass(frozen=True)
class TarHeader:
    path: str
    linkpath: str
    size: int
    typeflag: str
    stored_checksum: int
    computed_checksum_unsigned: int
    computed_checksum_signed: int


@dataclass(frozen=True)
class LocatedMember:
    expected_name: str
    member_path: str
    size: int
    header_offset: int
    data_offset: int
    payload_end_exclusive: int
    next_header_offset: int
    typeflag: str
    checksum_status: str = "VALID"


@dataclass(frozen=True)
class ScanResult:
    found: Mapping[str, LocatedMember]
    headers_read: int
    metadata_bodies_read: int
    ended_at_eoa: bool
    stop_offset: int


class RangeReader(Protocol):
    total_size: int

    def read(self, start: int, length: int, purpose: str) -> bytes: ...


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def strip_url_query(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.username is not None or parsed.password is not None:
        raise SafetyError("URL_USERINFO_PROHIBITED")
    host = parsed.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    netloc = host if parsed.port is None else f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


def host_allowed(host: str, suffixes: Sequence[str] = ALLOWED_REDIRECT_HOST_SUFFIXES) -> bool:
    normalized = host.lower().rstrip(".")
    return any(
        normalized == suffix.lstrip(".") or (suffix.startswith(".") and normalized.endswith(suffix))
        for suffix in suffixes
    )


def canonical_url(filename: str) -> str:
    if not filename or filename != PurePosixPath(filename).name:
        raise ConfigurationError("INVALID_REPOSITORY_FILENAME")
    return (
        "https://huggingface.co/datasets/"
        f"{REPOSITORY}/resolve/{REVISION}/{quote(filename, safe='')}"
    )


def parse_content_range(value: str) -> tuple[int, int, int]:
    match = CONTENT_RANGE_RE.fullmatch(value.strip())
    if not match:
        raise SafetyError("INVALID_CONTENT_RANGE")
    return tuple(int(group) for group in match.groups())  # type: ignore[return-value]


class SafeRangeClient:
    """Strict manual-redirect HTTP client with bounded streaming reads.

    One persistent httpx.Client is shared by all requests. Validated effective
    URLs are cached only in memory and are never copied into request records.
    """

    def __init__(
        self,
        token: str,
        *,
        client: Any | None = None,
        budget: Budget | None = None,
        allowed_redirect_host_suffixes: Sequence[str] = ALLOWED_REDIRECT_HOST_SUFFIXES,
    ) -> None:
        if not token:
            raise ConfigurationError("HF_TOKEN_NOT_AVAILABLE")
        if httpx is None:
            raise ConfigurationError("HTTPX_NOT_INSTALLED")
        self._token = token
        self._owns_client = client is None
        self._client = client or httpx.Client(
            follow_redirects=False,
            trust_env=True,
            timeout=httpx.Timeout(60.0, connect=30.0),
            headers={"User-Agent": "AV-TRACE-lvb-range-preflight/1.0"},
        )
        self.budget = budget or Budget()
        self.allowed_redirect_host_suffixes = tuple(allowed_redirect_host_suffixes)
        self.records: list[RequestRecord] = []
        self._range_cache: dict[tuple[str, int, int, int], bytes] = {}
        self._effective_url_cache: dict[tuple[str, int], str] = {}
        self._request_counter = 0

    def close(self) -> None:
        self._token = ""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "SafeRangeClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _new_record(self, filename: str, method: str, requested_range: str | None, purpose: str) -> RequestRecord:
        self._request_counter += 1
        return RequestRecord(
            request_id=f"request-{self._request_counter:06d}",
            filename=filename,
            method=method,
            requested_range=requested_range,
            purpose=purpose,
            canonical_url=canonical_url(filename),
        )

    def _validate_request_url(self, url: str) -> Any:
        parsed = urlsplit(url)
        if parsed.scheme.lower() != "https":
            raise SafetyError("NON_HTTPS_REQUEST_OR_REDIRECT")
        if parsed.username is not None or parsed.password is not None:
            raise SafetyError("URL_USERINFO_PROHIBITED")
        try:
            parsed_port = parsed.port
        except ValueError:
            raise SafetyError("INVALID_URL_PORT") from None
        if not parsed.hostname or not host_allowed(parsed.hostname, self.allowed_redirect_host_suffixes):
            raise SafetyError("REDIRECT_HOST_NOT_ALLOWED")
        if parsed_port is not None and not (1 <= parsed_port <= 65535):
            raise SafetyError("INVALID_URL_PORT")
        return parsed

    @staticmethod
    def _origin(parsed: Any) -> tuple[str, str, int]:
        return (
            parsed.scheme.lower(),
            (parsed.hostname or "").lower().rstrip("."),
            parsed.port or 443,
        )

    def _remember_effective_url(self, cache_key: tuple[str, int], initial_url: str, final_url: str) -> None:
        # The complete signed URL remains process-local. Records retain only
        # the canonical URL, hosts, and query-stripped redirect locations.
        initial_parsed = self._validate_request_url(initial_url)
        final_parsed = self._validate_request_url(final_url)
        if self._origin(final_parsed) == self._origin(initial_parsed):
            self._effective_url_cache.pop(cache_key, None)
        else:
            self._effective_url_cache[cache_key] = final_url

    def _send(
        self,
        filename: str,
        method: str,
        expected_size: int,
        purpose: str,
        byte_range: tuple[int, int] | None,
    ) -> FetchResult:
        requested_range = None if byte_range is None else f"bytes={byte_range[0]}-{byte_range[1]}"
        record = self._new_record(filename, method, requested_range, purpose)
        self.records.append(record)
        initial_url = record.canonical_url
        canonical_parsed = self._validate_request_url(initial_url)
        canonical_origin = self._origin(canonical_parsed)
        effective_cache_key = (initial_url, expected_size)
        cached_url = self._effective_url_cache.get(effective_cache_key)
        url = cached_url or initial_url
        using_cached_route = cached_url is not None
        canonical_resolution = not using_cached_route
        refreshed_cached_route = False
        redirects = 0
        try:
            while True:
                parsed = self._validate_request_url(url)
                headers: dict[str, str] = {}
                # Same-origin relative redirects can still require authentication.
                # Never send the bearer credential to a CDN/subdomain/different port.
                if canonical_resolution and self._origin(parsed) == canonical_origin:
                    headers["Authorization"] = f"Bearer {self._token}"
                if requested_range is not None:
                    headers["Range"] = requested_range
                    headers["Accept-Encoding"] = "identity"
                with self._client.stream(method, url, headers=headers) as response:
                    if response.status_code in REDIRECT_CODES:
                        location = response.headers.get("location")
                        if not location:
                            raise SafetyError("REDIRECT_WITHOUT_LOCATION")
                        next_url = urljoin(url, location)
                        next_parsed = self._validate_request_url(next_url)
                        record.redirect_chain.append(
                            {
                                "status_code": response.status_code,
                                "from_host": parsed.hostname.lower(),
                                "to_host": next_parsed.hostname.lower(),
                                "location": strip_url_query(next_url),
                            }
                        )
                        redirects += 1
                        if redirects > MAX_REDIRECTS:
                            raise SafetyError("TOO_MANY_REDIRECTS")
                        canonical_resolution = (
                            canonical_resolution
                            and self._origin(parsed) == canonical_origin
                            and self._origin(next_parsed) == canonical_origin
                        )
                        url = next_url
                        continue

                    if (
                        using_cached_route
                        and not refreshed_cached_route
                        and response.status_code in SIGNED_URL_REFRESH_STATUSES
                    ):
                        # A stale/method-incompatible signed URL gets exactly one
                        # canonical re-resolution. The failed body is not consumed.
                        self._effective_url_cache.pop(effective_cache_key, None)
                        refreshed_cached_route = True
                        using_cached_route = False
                        canonical_resolution = True
                        url = initial_url
                        continue

                    record.response_status = response.status_code
                    record.effective_host = parsed.hostname.lower()
                    record.accept_ranges = response.headers.get("accept-ranges")
                    raw_length = response.headers.get("content-length")
                    if raw_length is None or not raw_length.isdigit():
                        raise SafetyError("MISSING_OR_INVALID_CONTENT_LENGTH")
                    record.content_length = int(raw_length)

                    if byte_range is None:
                        if response.status_code != 200:
                            raise SafetyError("UNEXPECTED_HEAD_STATUS")
                        if record.content_length != expected_size:
                            raise SafetyError("UNEXPECTED_HEAD_CONTENT_LENGTH")
                        self._remember_effective_url(effective_cache_key, initial_url, url)
                        return FetchResult(b"", record)

                    start, end = byte_range
                    expected_body = end - start + 1
                    if response.status_code == 200:
                        raise SafetyError("RANGE_IGNORED_FULL_OBJECT_200")
                    if response.status_code != 206:
                        raise SafetyError("UNEXPECTED_RANGE_STATUS")
                    if record.content_length != expected_body:
                        raise SafetyError("UNEXPECTED_RANGE_CONTENT_LENGTH")
                    content_encoding = response.headers.get("content-encoding", "identity").lower()
                    if content_encoding != "identity":
                        raise SafetyError("UNEXPECTED_RANGE_CONTENT_ENCODING")
                    content_range = response.headers.get("content-range")
                    record.content_range = content_range
                    if content_range is None:
                        raise SafetyError("MISSING_CONTENT_RANGE")
                    actual_start, actual_end, actual_total = parse_content_range(content_range)
                    if (actual_start, actual_end, actual_total) != (start, end, expected_size):
                        raise SafetyError("MISMATCHED_CONTENT_RANGE")
                    if expected_body > self.budget.maximum_response_bytes:
                        raise SafetyError("REQUEST_EXCEEDS_RESPONSE_BODY_LIMIT")
                    if self.budget.total_bytes + expected_body > self.budget.maximum_total_bytes:
                        raise SafetyError("TOTAL_RESPONSE_BODY_LIMIT_EXCEEDED")

                    body = bytearray()
                    # Content encoding is required to be identity, so iter_bytes()
                    # is byte-for-byte equivalent and also works with MockTransport.
                    for chunk in response.iter_bytes():
                        if len(body) + len(chunk) > expected_body:
                            raise SafetyError("RANGE_RESPONSE_EXCESS_BYTES")
                        if len(body) + len(chunk) > self.budget.maximum_response_bytes:
                            raise SafetyError("RESPONSE_BODY_LIMIT_EXCEEDED")
                        body.extend(chunk)
                    if len(body) != expected_body:
                        raise SafetyError("RANGE_RESPONSE_TRUNCATED")
                    self.budget.account(len(body))
                    result = bytes(body)
                    record.bytes_received = len(result)
                    record.sha256 = hashlib.sha256(result).hexdigest()
                    self._remember_effective_url(effective_cache_key, initial_url, url)
                    return FetchResult(result, record)
        except PreflightError as exc:
            record.error_code = str(exc)
            raise
        except Exception as exc:
            # Exception strings can contain signed redirect URLs. Persist only the class.
            record.error_code = f"HTTP_TRANSPORT_{type(exc).__name__.upper()}"
            raise PreflightError(record.error_code) from None

    def head(self, filename: str, expected_size: int, purpose: str) -> RequestRecord:
        return self._send(filename, "HEAD", expected_size, purpose, None).record

    def fetch_range(self, filename: str, start: int, end: int, expected_size: int, purpose: str) -> bytes:
        if start < 0 or end < start or end >= expected_size:
            raise SafetyError("RANGE_OUTSIDE_OFFICIAL_OBJECT_SIZE")
        if start == 0 and end == expected_size - 1:
            raise SafetyError("COMPLETE_OBJECT_RANGE_PROHIBITED")
        if end - start + 1 > self.budget.maximum_response_bytes:
            raise SafetyError("REQUEST_EXCEEDS_RESPONSE_BODY_LIMIT")
        object_url = canonical_url(filename)
        cache_key = (object_url, expected_size, start, end)
        cached = self._range_cache.get(cache_key)
        if cached is not None:
            return cached
        result = self._send(filename, "GET", expected_size, purpose, (start, end)).body
        self._range_cache[cache_key] = result
        return result


class MultipartRangeReader:
    def __init__(self, parts: Sequence[Part], fetch: Callable[[str, int, int, int, str], bytes]) -> None:
        if not parts:
            raise ConfigurationError("NO_MULTIPART_PARTS")
        self.parts = tuple(parts)
        self.starts = [part.start for part in self.parts]
        self.total_size = self.parts[-1].end_inclusive + 1
        self._fetch = fetch
        expected = 0
        for part in self.parts:
            if part.start != expected or part.end_inclusive != part.start + part.size - 1:
                raise ConfigurationError("NONCONTIGUOUS_MULTIPART_GEOMETRY")
            expected += part.size

    def read(self, start: int, length: int, purpose: str) -> bytes:
        if start < 0 or length < 0 or start + length > self.total_size:
            raise SafetyError("GLOBAL_RANGE_OUTSIDE_MULTIPART_STREAM")
        if length == 0:
            return b""
        output = bytearray()
        cursor = start
        remaining = length
        while remaining:
            index = bisect.bisect_right(self.starts, cursor) - 1
            if index < 0:
                raise SafetyError("MULTIPART_LOOKUP_FAILED")
            part = self.parts[index]
            local_start = cursor - part.start
            available = part.size - local_start
            segment_length = min(remaining, available, MAX_RESPONSE_BYTES)
            local_end = local_start + segment_length - 1
            output.extend(self._fetch(part.name, local_start, local_end, part.size, purpose))
            cursor += segment_length
            remaining -= segment_length
        return bytes(output)


class SingleObjectRangeReader:
    def __init__(self, filename: str, total_size: int, fetch: Callable[[str, int, int, int, str], bytes]) -> None:
        self.filename = filename
        self.total_size = total_size
        self._fetch = fetch

    def read(self, start: int, length: int, purpose: str) -> bytes:
        if start < 0 or length < 0 or start + length > self.total_size:
            raise SafetyError("RANGE_OUTSIDE_ARCHIVE")
        if length == 0:
            return b""
        output = bytearray()
        cursor = start
        remaining = length
        while remaining:
            segment_length = min(remaining, MAX_RESPONSE_BYTES)
            output.extend(
                self._fetch(
                    self.filename,
                    cursor,
                    cursor + segment_length - 1,
                    self.total_size,
                    purpose,
                )
            )
            cursor += segment_length
            remaining -= segment_length
        return bytes(output)


def _decode_string(field: bytes) -> str:
    return field.split(b"\0", 1)[0].decode("utf-8", errors="replace")


def parse_tar_number(field: bytes) -> int:
    if not field:
        return 0
    if field[0] & 0x80:
        raw = bytearray(field)
        negative = bool(raw[0] & 0x40)
        raw[0] &= 0x7F
        value = int.from_bytes(raw, "big", signed=False)
        if negative:
            bits = len(field) * 8 - 1
            value -= 1 << bits
        if value < 0:
            raise TarFormatError("NEGATIVE_TAR_NUMBER")
        return value
    stripped = field.rstrip(b"\0 ").lstrip(b" ")
    if not stripped:
        return 0
    if any(byte not in b"01234567" for byte in stripped):
        raise TarFormatError("INVALID_TAR_OCTAL_FIELD")
    return int(stripped, 8)


def validate_tar_checksum(block: bytes) -> tuple[int, int, int]:
    if len(block) != BLOCK_SIZE:
        raise TarFormatError("TAR_HEADER_NOT_512_BYTES")
    stored = parse_tar_number(block[148:156])
    unsigned = sum(block[:148]) + (8 * 32) + sum(block[156:])
    signed = sum((byte if byte < 128 else byte - 256) for byte in block[:148]) + (8 * 32) + sum(
        (byte if byte < 128 else byte - 256) for byte in block[156:]
    )
    if stored not in (unsigned, signed):
        raise TarFormatError("INVALID_TAR_HEADER_CHECKSUM")
    return stored, unsigned, signed


def parse_tar_header(block: bytes) -> TarHeader:
    stored, unsigned, signed = validate_tar_checksum(block)
    name = _decode_string(block[0:100])
    prefix = _decode_string(block[345:500])
    path = f"{prefix}/{name}" if prefix and name else (prefix or name)
    linkpath = _decode_string(block[157:257])
    type_byte = block[156]
    typeflag = "\0" if type_byte == 0 else chr(type_byte)
    return TarHeader(
        path=path,
        linkpath=linkpath,
        size=parse_tar_number(block[124:136]),
        typeflag=typeflag,
        stored_checksum=stored,
        computed_checksum_unsigned=unsigned,
        computed_checksum_signed=signed,
    )


def parse_pax_records(body: bytes) -> dict[str, str]:
    records: dict[str, str] = {}
    cursor = 0
    while cursor < len(body):
        space = body.find(b" ", cursor)
        if space < 0:
            raise TarFormatError("MALFORMED_PAX_RECORD_LENGTH")
        raw_length = body[cursor:space]
        if not raw_length.isdigit():
            raise TarFormatError("MALFORMED_PAX_RECORD_LENGTH")
        record_length = int(raw_length)
        if record_length <= space - cursor + 1 or cursor + record_length > len(body):
            raise TarFormatError("PAX_RECORD_OUTSIDE_BODY")
        record = body[space + 1 : cursor + record_length]
        if not record.endswith(b"\n") or b"=" not in record:
            raise TarFormatError("MALFORMED_PAX_RECORD")
        key_raw, value_raw = record[:-1].split(b"=", 1)
        key = key_raw.decode("utf-8", errors="strict")
        value = value_raw.decode("utf-8", errors="replace")
        if not key:
            raise TarFormatError("EMPTY_PAX_KEY")
        records[key] = value
        cursor += record_length
    return records


def round_up_block(value: int) -> int:
    return ((value + BLOCK_SIZE - 1) // BLOCK_SIZE) * BLOCK_SIZE


def exact_target_name(path: str, targets: set[str]) -> str | None:
    # Match an exact POSIX basename, never a substring or suffix approximation.
    # The full stored path is retained, and duplicate target basenames fail closed.
    name = PurePosixPath(path).name
    return name if name in targets else None


class SparseTarScanner:
    METADATA_TYPES = {"L", "K", "x", "g"}
    REGULAR_TYPES = {"\0", "0", "7"}

    def __init__(
        self,
        reader: RangeReader,
        target_names: Iterable[str],
        archive_label: str,
        *,
        progress_every: int = 0,
        progress_callback: Callable[[str, int, int, int, int], None] | None = None,
    ) -> None:
        self.reader = reader
        self.targets = set(target_names)
        self.archive_label = archive_label
        self.progress_every = progress_every
        self.progress_callback = progress_callback
        if not self.targets:
            raise ConfigurationError("NO_TAR_TARGETS")
        if progress_every < 0:
            raise ConfigurationError("INVALID_PROGRESS_INTERVAL")

    def _report_progress(self, headers_read: int, offset: int, found_count: int) -> None:
        if (
            self.progress_callback is not None
            and self.progress_every > 0
            and headers_read % self.progress_every == 0
        ):
            self.progress_callback(
                self.archive_label,
                headers_read,
                offset,
                found_count,
                len(self.targets),
            )

    def scan(self) -> ScanResult:
        offset = 0
        found: dict[str, LocatedMember] = {}
        global_pax: dict[str, str] = {}
        local_pax: dict[str, str] = {}
        pending_long_name: str | None = None
        pending_long_link: str | None = None
        headers_read = 0
        metadata_bodies_read = 0

        while offset + BLOCK_SIZE <= self.reader.total_size:
            block = self.reader.read(offset, BLOCK_SIZE, f"{self.archive_label}:tar-header")
            if block == bytes(BLOCK_SIZE):
                if offset + 2 * BLOCK_SIZE > self.reader.total_size:
                    raise TarFormatError("TRUNCATED_END_OF_ARCHIVE")
                second = self.reader.read(offset + BLOCK_SIZE, BLOCK_SIZE, f"{self.archive_label}:eoa-confirm")
                if second != bytes(BLOCK_SIZE):
                    raise TarFormatError("SINGLE_ZERO_TAR_BLOCK")
                return ScanResult(found, headers_read, metadata_bodies_read, True, offset + 2 * BLOCK_SIZE)

            header = parse_tar_header(block)
            headers_read += 1
            data_offset = offset + BLOCK_SIZE
            raw_size = header.size

            if header.typeflag in self.METADATA_TYPES:
                body = self.reader.read(
                    data_offset,
                    raw_size,
                    f"{self.archive_label}:metadata-{header.typeflag}",
                )
                metadata_bodies_read += len(body)
                if header.typeflag == "L":
                    pending_long_name = body.split(b"\0", 1)[0].rstrip(b"\n").decode(
                        "utf-8", errors="replace"
                    )
                elif header.typeflag == "K":
                    pending_long_link = body.split(b"\0", 1)[0].rstrip(b"\n").decode(
                        "utf-8", errors="replace"
                    )
                elif header.typeflag == "x":
                    local_pax.update(parse_pax_records(body))
                else:
                    global_pax.update(parse_pax_records(body))
                offset = data_offset + round_up_block(raw_size)
                self._report_progress(headers_read, offset, len(found))
                continue

            effective_pax = dict(global_pax)
            effective_pax.update(local_pax)
            path = effective_pax.get("path") or pending_long_name or header.path
            linkpath = effective_pax.get("linkpath") or pending_long_link or header.linkpath
            del linkpath  # parsed for GNU/PAX correctness; targets are regular files.
            effective_size = raw_size
            if "size" in effective_pax:
                try:
                    effective_size = int(effective_pax["size"], 10)
                except ValueError:
                    raise TarFormatError("INVALID_PAX_SIZE") from None
                if effective_size < 0:
                    raise TarFormatError("NEGATIVE_PAX_SIZE")

            next_header = data_offset + round_up_block(effective_size)
            if next_header > self.reader.total_size:
                raise TarFormatError("TAR_MEMBER_EXCEEDS_ARCHIVE")
            matched = exact_target_name(path, self.targets)
            if matched is not None:
                if header.typeflag not in self.REGULAR_TYPES:
                    raise TarFormatError("TARGET_NAME_IS_NOT_REGULAR_FILE")
                if matched in found:
                    raise TarFormatError("DUPLICATE_TARGET_MEMBER")
                found[matched] = LocatedMember(
                    expected_name=matched,
                    member_path=path,
                    size=effective_size,
                    header_offset=offset,
                    data_offset=data_offset,
                    payload_end_exclusive=data_offset + effective_size,
                    next_header_offset=next_header,
                    typeflag=header.typeflag,
                )

            local_pax.clear()
            pending_long_name = None
            pending_long_link = None
            offset = next_header
            self._report_progress(headers_read, offset, len(found))

        raise TarFormatError("TAR_ENDED_WITHOUT_END_MARKER_OR_ALL_TARGETS")


def load_official_inputs(repo_root: Path) -> tuple[list[Part], int, dict[str, Any]]:
    evidence_path = repo_root / EVIDENCE_REL
    parts_path = repo_root / PARTS_REL
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    if evidence.get("id") != REPOSITORY or evidence.get("sha") != REVISION:
        raise ConfigurationError("PINNED_EVIDENCE_ID_OR_REVISION_MISMATCH")
    siblings = {item["rfilename"]: item for item in evidence.get("siblings", [])}
    official_part_names = sorted(name for name in siblings if name.startswith("videos.tar.part."))
    subtitle = siblings.get("subtitles.tar")
    if not subtitle:
        raise ConfigurationError("SUBTITLES_NOT_LISTED_IN_PINNED_EVIDENCE")
    subtitle_size = int(subtitle["size"])

    parts: list[Part] = []
    with parts_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            name = row["part_name"]
            if not name.startswith("videos.tar.part.") or name not in siblings:
                raise ConfigurationError("PART_NOT_LISTED_IN_PINNED_EVIDENCE")
            size = int(row["content_length"])
            start = int(row["global_start_offset"])
            end = int(row["global_end_offset_inclusive"])
            official = siblings[name]
            if int(official["size"]) != size or official.get("lfs", {}).get("sha256") != row["lfs_sha256"]:
                raise ConfigurationError("PART_CSV_AND_PINNED_EVIDENCE_MISMATCH")
            if row["pinned_revision"] != REVISION:
                raise ConfigurationError("PART_CSV_REVISION_MISMATCH")
            parts.append(
                Part(
                    index=int(row["part_index"]),
                    name=name,
                    size=size,
                    start=start,
                    end_inclusive=end,
                    sha256=row["lfs_sha256"],
                    metadata_source=row["metadata_source"],
                )
            )
    parts.sort(key=lambda part: part.index)
    if [part.index for part in parts] != list(range(len(parts))):
        raise ConfigurationError("PART_INDEX_SEQUENCE_INVALID")
    if [part.name for part in parts] != official_part_names:
        raise ConfigurationError("PART_CSV_DOES_NOT_MATCH_COMPLETE_PINNED_PART_LIST")
    MultipartRangeReader(parts, lambda *_: b"")  # validate geometry without I/O
    return parts, subtitle_size, evidence


def compute_part_ranges(start: int, size: int, parts: Sequence[Part]) -> list[dict[str, Any]]:
    if size < 0:
        raise ValueError("size must be nonnegative")
    if size == 0:
        return []
    end = start + size - 1
    output: list[dict[str, Any]] = []
    for part in parts:
        overlap_start = max(start, part.start)
        overlap_end = min(end, part.end_inclusive)
        if overlap_start <= overlap_end:
            local_start = overlap_start - part.start
            local_end = overlap_end - part.start
            output.append(
                {
                    "part_index": part.index,
                    "part_name": part.name,
                    "global_start": overlap_start,
                    "global_end_inclusive": overlap_end,
                    "part_start": local_start,
                    "part_end_inclusive": local_end,
                    "http_range": f"bytes={local_start}-{local_end}",
                    "length": local_end - local_start + 1,
                }
            )
    if sum(item["length"] for item in output) != size:
        raise SafetyError("PAYLOAD_RANGE_NOT_COVERED_BY_PARTS")
    return output


def _request_stats(records: Sequence[RequestRecord], filename: str) -> dict[str, Any]:
    selected = [record for record in records if record.filename == filename]
    range_records = [record for record in selected if record.method == "GET" and record.response_status == 206]
    head_records = [record for record in selected if record.method == "HEAD" and record.response_status == 200]
    hosts = sorted({record.effective_host for record in selected if record.effective_host})
    redirect_hosts = sorted(
        {
            chain[side]
            for record in selected
            for chain in record.redirect_chain
            for side in ("from_host", "to_host")
        }
    )
    return {
        "head_verified": bool(head_records),
        "range_verified": bool(range_records),
        "accept_ranges_verified": any((record.accept_ranges or "").lower() == "bytes" for record in selected),
        "effective_hosts": hosts,
        "redirect_hosts": redirect_hosts,
        "range_request_count": len(range_records),
        "bytes_received": sum(record.bytes_received for record in selected),
    }


def _video_rows(found: Mapping[str, LocatedMember], parts: Sequence[Part]) -> list[dict[str, Any]]:
    rows = []
    for candidate_id, video_id in TARGETS:
        expected = f"{video_id}.mp4"
        member = found.get(expected)
        if member is None:
            rows.append(
                {
                    "candidate_id": candidate_id,
                    "video_id": video_id,
                    "member_path": expected,
                    "member_size": "",
                    "tar_header_global_offset": "",
                    "tar_data_global_offset": "",
                    "tar_end_global_offset": "",
                    "first_part": "",
                    "last_part": "",
                    "part_ranges_json": "[]",
                    "header_checksum_status": "NOT_FOUND_AFTER_SPARSE_SCAN",
                    "range_extraction_feasible": "false",
                    "status": "NOT_FOUND",
                    "blocker": "Exact target basename was not found before the tar end marker.",
                }
            )
            continue
        if member.size == 0:
            rows.append(
                {
                    "candidate_id": candidate_id,
                    "video_id": video_id,
                    "member_path": member.member_path,
                    "member_size": 0,
                    "tar_header_global_offset": member.header_offset,
                    "tar_data_global_offset": member.data_offset,
                    "tar_end_global_offset": member.payload_end_exclusive,
                    "first_part": "",
                    "last_part": "",
                    "part_ranges_json": "[]",
                    "header_checksum_status": member.checksum_status,
                    "range_extraction_feasible": "false",
                    "status": "INVALID_ZERO_LENGTH_TARGET",
                    "blocker": "A target MP4 member must have a positive payload size.",
                }
            )
            continue
        ranges = compute_part_ranges(member.data_offset, member.size, parts)
        rows.append(
            {
                "candidate_id": candidate_id,
                "video_id": video_id,
                "member_path": member.member_path,
                "member_size": member.size,
                "tar_header_global_offset": member.header_offset,
                "tar_data_global_offset": member.data_offset,
                "tar_end_global_offset": member.payload_end_exclusive,
                "first_part": ranges[0]["part_name"] if ranges else "",
                "last_part": ranges[-1]["part_name"] if ranges else "",
                "part_ranges_json": json.dumps(ranges, separators=(",", ":"), sort_keys=True),
                "header_checksum_status": member.checksum_status,
                "range_extraction_feasible": "true",
                "status": "LOCATED_HEADER_ONLY",
                "blocker": "",
            }
        )
    return rows


def _subtitle_rows(found: Mapping[str, LocatedMember], archive_size: int) -> list[dict[str, Any]]:
    rows = []
    for candidate_id, video_id in TARGETS:
        expected = f"{video_id}_en.json"
        member = found.get(expected)
        if member is None:
            rows.append(
                {
                    "candidate_id": candidate_id,
                    "video_id": video_id,
                    "member_path": expected,
                    "member_size": "",
                    "tar_header_offset": "",
                    "tar_data_offset": "",
                    "tar_end_offset": "",
                    "requested_archive": "subtitles.tar",
                    "archive_content_length": archive_size,
                    "part_ranges_json": "[]",
                    "header_checksum_status": "NOT_FOUND_AFTER_SPARSE_SCAN",
                    "range_extraction_feasible": "false",
                    "status": "NOT_FOUND",
                    "blocker": "Exact target basename was not found before the tar end marker.",
                }
            )
            continue
        if member.size == 0:
            rows.append(
                {
                    "candidate_id": candidate_id,
                    "video_id": video_id,
                    "member_path": member.member_path,
                    "member_size": 0,
                    "tar_header_offset": member.header_offset,
                    "tar_data_offset": member.data_offset,
                    "tar_end_offset": member.payload_end_exclusive,
                    "requested_archive": "subtitles.tar",
                    "archive_content_length": archive_size,
                    "part_ranges_json": "[]",
                    "header_checksum_status": member.checksum_status,
                    "range_extraction_feasible": "false",
                    "status": "INVALID_ZERO_LENGTH_TARGET",
                    "blocker": "A target subtitle member must have a positive payload size.",
                }
            )
            continue
        ranges = [] if member.size == 0 else [
            {
                "archive": "subtitles.tar",
                "global_start": member.data_offset,
                "global_end_inclusive": member.payload_end_exclusive - 1,
                "http_range": f"bytes={member.data_offset}-{member.payload_end_exclusive - 1}",
                "length": member.size,
            }
        ]
        rows.append(
            {
                "candidate_id": candidate_id,
                "video_id": video_id,
                "member_path": member.member_path,
                "member_size": member.size,
                "tar_header_offset": member.header_offset,
                "tar_data_offset": member.data_offset,
                "tar_end_offset": member.payload_end_exclusive,
                "requested_archive": "subtitles.tar",
                "archive_content_length": archive_size,
                "part_ranges_json": json.dumps(ranges, separators=(",", ":"), sort_keys=True),
                "header_checksum_status": member.checksum_status,
                "range_extraction_feasible": "true",
                "status": "LOCATED_HEADER_ONLY",
                "blocker": "",
            }
        )
    return rows


def _parts_rows(parts: Sequence[Part], records: Sequence[RequestRecord]) -> list[dict[str, Any]]:
    rows = []
    for part in parts:
        stats = _request_stats(records, part.name)
        touched = stats["head_verified"] or stats["range_verified"]
        rows.append(
            {
                "part_index": part.index,
                "part_name": part.name,
                "content_length": part.size,
                "global_start_offset": part.start,
                "global_end_offset_inclusive": part.end_inclusive,
                "tar_block_aligned_start": str(part.start % BLOCK_SIZE == 0).lower(),
                "tar_block_aligned_length": str(part.size % BLOCK_SIZE == 0).lower(),
                "lfs_sha256": part.sha256,
                "metadata_source": part.metadata_source,
                "pinned_revision": REVISION,
                "head_verified_live": str(stats["head_verified"]).lower(),
                "accept_ranges_verified_live": str(stats["accept_ranges_verified"]).lower(),
                "range_206_verified_live": str(stats["range_verified"]).lower(),
                "effective_host": ";".join(stats["effective_hosts"]),
                "status": "LIVE_RANGE_VERIFIED" if stats["range_verified"] else "NOT_TOUCHED_BY_SPARSE_SCAN",
                "blocker": "" if touched else "Sparse traversal completed before this part was needed.",
            }
        )
    return rows


def _csv_bytes(rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=False, ensure_ascii=True) + "\n").encode("utf-8")


def _markdown_bytes(
    outcome: str,
    generated: str,
    video_rows: Sequence[Mapping[str, Any]],
    subtitle_rows: Sequence[Mapping[str, Any]],
    video_scan: ScanResult,
    subtitle_scan: ScanResult,
    records: Sequence[RequestRecord],
    budget: Budget,
) -> bytes:
    located_videos = sum(row["status"] == "LOCATED_HEADER_ONLY" for row in video_rows)
    located_subtitles = sum(row["status"] == "LOCATED_HEADER_ONLY" for row in subtitle_rows)
    hosts = sorted({record.effective_host for record in records if record.effective_host})
    lines = [
        "# LongVideoBench five-member tar-range preflight",
        "",
        f"**Generated:** `{generated}`  ",
        f"**Repository:** `{REPOSITORY}`  ",
        f"**Pinned revision:** `{REVISION}`  ",
        f"**Decision:** **{outcome}**",
        "",
        "## Live result",
        "",
        f"- Exact video members located from validated tar headers: **{located_videos}/5**.",
        f"- Exact subtitle members located from validated tar headers: **{located_subtitles}/5**.",
        f"- Video tar headers read: **{video_scan.headers_read}**; metadata-body bytes read: **{video_scan.metadata_bodies_read}**.",
        f"- Subtitle tar headers read: **{subtitle_scan.headers_read}**; metadata-body bytes read: **{subtitle_scan.metadata_bodies_read}**.",
        f"- HTTP response-body bytes read: **{budget.total_bytes:,}** of **{budget.maximum_total_bytes:,}** allowed.",
        f"- Largest response body: **{budget.maximum_observed:,}** bytes of **{budget.maximum_response_bytes:,}** allowed.",
        f"- Effective hosts (query strings omitted): `{', '.join(hosts)}`.",
        "- No target MP4 payload, complete multipart part, complete subtitle archive, token, cookie, or Authorization header was written.",
        "",
        "`tar_end_global_offset` / `tar_end_offset` are exclusive payload endpoints. HTTP ranges in the CSV are inclusive.",
        "Targets are matched by exact POSIX basename (never substring/suffix); the full stored member path is retained.",
        "",
        "## Target videos",
        "",
        "| Candidate | Video ID | Stored member | Bytes | Header offset | Data offset | Status |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for row in video_rows:
        lines.append(
            f"| `{row['candidate_id']}` | `{row['video_id']}` | `{row['member_path']}` | "
            f"{row['member_size'] or '—'} | {row['tar_header_global_offset'] or '—'} | "
            f"{row['tar_data_global_offset'] or '—'} | `{row['status']}` |"
        )
    lines.extend(
        [
            "",
            "## Target subtitles",
            "",
            "| Candidate | Video ID | Stored member | Bytes | Header offset | Data offset | Status |",
            "|---|---|---|---:|---:|---:|---|",
        ]
    )
    for row in subtitle_rows:
        lines.append(
            f"| `{row['candidate_id']}` | `{row['video_id']}` | `{row['member_path']}` | "
            f"{row['member_size'] or '—'} | {row['tar_header_offset'] or '—'} | "
            f"{row['tar_data_offset'] or '—'} | `{row['status']}` |"
        )
    lines.extend(
        [
            "",
            "## Authorization boundary",
            "",
            "The parent session supplied that Hugging Face login is verified and the dataset gate has been passed. "
            "This run is limited to authenticated bounded metadata/header-only preflight. Full-corpus download remains "
            "prohibited. Target media acquisition, processing, annotation, and release remain separate later stages.",
            "",
        ]
    )
    return ("\n".join(lines)).encode("utf-8")


def _atomic_commit(repo_root: Path, outputs: Mapping[Path, bytes]) -> dict[str, dict[str, Any]]:
    for relative in outputs:
        destination = (repo_root / relative).resolve()
        try:
            destination.relative_to(repo_root.resolve())
        except ValueError:
            raise SafetyError("OUTPUT_PATH_OUTSIDE_REPOSITORY") from None
    hashes = {
        relative.as_posix(): {"bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
        for relative, content in outputs.items()
    }
    parent = repo_root / "data/acquisition_preflight"
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".lvb-preflight-", dir=parent) as temp_name:
        temp_root = Path(temp_name)
        staged: list[tuple[Path, Path]] = []
        for relative, content in outputs.items():
            staged_path = temp_root / relative
            staged_path.parent.mkdir(parents=True, exist_ok=True)
            staged_path.write_bytes(content)
            staged.append((staged_path, repo_root / relative))
        # Manifest is committed last so a successful manifest describes all prior outputs.
        staged.sort(key=lambda pair: pair[1] == repo_root / MANIFEST_REL)
        for staged_path, destination in staged:
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged_path, destination)
    return hashes


def make_progress_reporter(client: SafeRangeClient, stream: TextIO) -> Callable[[str, int, int, int, int], None]:
    def report(archive_label: str, headers: int, logical_offset: int, found: int, target_count: int) -> None:
        print(
            f"progress archive={archive_label} headers={headers} "
            f"logical_offset={logical_offset} response_bytes={client.budget.total_bytes} "
            f"targets_found={found}/{target_count}",
            file=stream,
            flush=True,
        )

    return report


def run_execute(
    repo_root: Path,
    *,
    client_factory: Callable[[str], SafeRangeClient] | None = None,
    progress_every: int = DEFAULT_PROGRESS_EVERY,
    progress_stream: TextIO | None = None,
) -> dict[str, Any]:
    if progress_every < 0:
        raise ConfigurationError("INVALID_PROGRESS_INTERVAL")
    parts, subtitle_size, evidence = load_official_inputs(repo_root)
    try:
        from huggingface_hub import get_token
    except ImportError:
        raise ConfigurationError("HUGGINGFACE_HUB_NOT_INSTALLED") from None
    token = get_token()
    if not token:
        raise ConfigurationError("HF_TOKEN_NOT_AVAILABLE")

    generated = utc_now()
    client = client_factory(token) if client_factory else SafeRangeClient(token)
    try:
        progress_callback = (
            make_progress_reporter(client, progress_stream or sys.stderr)
            if progress_every > 0
            else None
        )
        client.head(parts[0].name, parts[0].size, "mandatory-preflight-head")
        client.fetch_range(parts[0].name, 0, 511, parts[0].size, "mandatory-preflight-range")
        client.head("subtitles.tar", subtitle_size, "mandatory-preflight-head")
        client.fetch_range("subtitles.tar", 0, 511, subtitle_size, "mandatory-preflight-range")

        multipart = MultipartRangeReader(parts, client.fetch_range)
        subtitles = SingleObjectRangeReader("subtitles.tar", subtitle_size, client.fetch_range)
        video_targets = [f"{video_id}.mp4" for _, video_id in TARGETS]
        subtitle_targets = [f"{video_id}_en.json" for _, video_id in TARGETS]
        video_scan = SparseTarScanner(
            multipart,
            video_targets,
            "videos.tar",
            progress_every=progress_every,
            progress_callback=progress_callback,
        ).scan()
        subtitle_scan = SparseTarScanner(
            subtitles,
            subtitle_targets,
            "subtitles.tar",
            progress_every=progress_every,
            progress_callback=progress_callback,
        ).scan()

        video_rows = _video_rows(video_scan.found, parts)
        subtitle_rows = _subtitle_rows(subtitle_scan.found, subtitle_size)
        all_found = (
            len(video_scan.found) == len(video_targets)
            and len(subtitle_scan.found) == len(subtitle_targets)
            and all(member.size > 0 for member in video_scan.found.values())
            and all(member.size > 0 for member in subtitle_scan.found.values())
        )
        outcome = "GO_HEADER_INDEX_COMPLETE" if all_found else "NO_GO_TARGETS_NOT_FOUND"
        part_rows = _parts_rows(parts, client.records)

        video_fields = list(video_rows[0].keys())
        subtitle_fields = list(subtitle_rows[0].keys())
        part_fields = list(part_rows[0].keys())
        preliminary_outputs: dict[Path, bytes] = {
            PARTS_REL: _csv_bytes(part_rows, part_fields),
            VIDEO_RANGES_REL: _csv_bytes(video_rows, video_fields),
            SUBTITLE_RANGES_REL: _csv_bytes(subtitle_rows, subtitle_fields),
            REVIEW_REL: _markdown_bytes(
                outcome,
                generated,
                video_rows,
                subtitle_rows,
                video_scan,
                subtitle_scan,
                client.records,
                client.budget,
            ),
        }
        output_integrity = {
            relative.as_posix(): {"bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
            for relative, content in preliminary_outputs.items()
        }
        manifest = {
            "schema_version": "2.0",
            "task": "Task 58 — optimized live authenticated bounded Range preflight runner",
            "generated_at_utc": generated,
            "repository": REPOSITORY,
            "pinned_revision": REVISION,
            "mode": "execute",
            "authentication": {
                "credential_lookup": "huggingface_hub.get_token",
                "token_present": True,
                "parent_reported_hf_login_verified": True,
                "parent_reported_gate_acceptance_confirmed": True,
                "token_or_cookie_persisted": False,
                "authorization_headers_recorded": False,
            },
            "source_metadata_evidence": {
                "path": EVIDENCE_REL.as_posix(),
                "repository_id": evidence["id"],
                "reported_revision": evidence["sha"],
                "gated": evidence.get("gated"),
                "sha256": hashlib.sha256((repo_root / EVIDENCE_REL).read_bytes()).hexdigest(),
            },
            "limits": {
                "maximum_single_http_response_body_bytes": client.budget.maximum_response_bytes,
                "maximum_total_response_body_bytes": client.budget.maximum_total_bytes,
                "maximum_redirects_per_request": MAX_REDIRECTS,
                "progress_every_headers": progress_every,
            },
            "redirect_policy": {
                "https_only": True,
                "allowed_host_suffixes": list(client.allowed_redirect_host_suffixes),
                "authorization_retained_on_canonical_same_origin_redirects": True,
                "authorization_forwarded_to_cross_origin_redirects": False,
                "query_strings_persisted": False,
                "validated_effective_urls_cached_in_memory": True,
                "cached_effective_urls_persisted": False,
                "cached_auth_status_reresolution_attempts": 1,
            },
            "requests": [record.as_dict() for record in client.records],
            "accounting": {
                "request_count": len(client.records),
                "total_response_body_bytes": client.budget.total_bytes,
                "maximum_response_body_observed": client.budget.maximum_observed,
            },
            "scans": {
                "videos_tar": {
                    "logical_size": multipart.total_size,
                    "headers_read": video_scan.headers_read,
                    "metadata_body_bytes_read": video_scan.metadata_bodies_read,
                    "ended_at_eoa": video_scan.ended_at_eoa,
                    "stop_offset": video_scan.stop_offset,
                    "targets_found": sorted(video_scan.found),
                },
                "subtitles_tar": {
                    "logical_size": subtitle_size,
                    "headers_read": subtitle_scan.headers_read,
                    "metadata_body_bytes_read": subtitle_scan.metadata_bodies_read,
                    "ended_at_eoa": subtitle_scan.ended_at_eoa,
                    "stop_offset": subtitle_scan.stop_offset,
                    "targets_found": sorted(subtitle_scan.found),
                },
            },
            "safety": {
                "media_member_payload_downloaded": False,
                "complete_archive_part_downloaded": False,
                "complete_subtitles_archive_downloaded": False,
                "default_behavior": "PREFLIGHT_INDEX_ONLY",
                "target_payload_download_mode_available": False,
            },
            "output_integrity_excluding_manifest": output_integrity,
            "outcome": outcome,
            "conclusion": "GO" if all_found else "NO-GO",
        }
        preliminary_outputs[MANIFEST_REL] = _json_bytes(manifest)
        committed = _atomic_commit(repo_root, preliminary_outputs)
        return {
            "outcome": outcome,
            "conclusion": manifest["conclusion"],
            "requests": len(client.records),
            "bytes_received": client.budget.total_bytes,
            "outputs": committed,
        }
    finally:
        client.close()
        token = None


def dry_run(repo_root: Path) -> dict[str, Any]:
    parts, subtitle_size, _ = load_official_inputs(repo_root)
    return {
        "mode": "dry-run",
        "repository": REPOSITORY,
        "pinned_revision": REVISION,
        "video_parts": len(parts),
        "logical_video_tar_bytes": sum(part.size for part in parts),
        "subtitles_tar_bytes": subtitle_size,
        "target_video_members": [f"{video_id}.mp4" for _, video_id in TARGETS],
        "target_subtitle_members": [f"{video_id}_en.json" for _, video_id in TARGETS],
        "network_attempted": False,
        "credentials_read": False,
        "outputs_written": False,
    }


def find_repo_root(script_path: Path) -> Path:
    root = script_path.resolve().parents[1]
    if not (root / "pyproject.toml").is_file():
        raise ConfigurationError("REPOSITORY_ROOT_NOT_FOUND")
    return root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Index five LongVideoBench video/subtitle tar members using bounded authenticated ranges only."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="validate local pinned inputs; no token, network, or writes")
    mode.add_argument("--execute", action="store_true", help="perform the live bounded header-only preflight")
    parser.add_argument(
        "--progress-every",
        type=int,
        default=DEFAULT_PROGRESS_EVERY,
        metavar="N",
        help=f"report execute-mode progress to stderr every N tar headers (0 disables; default: {DEFAULT_PROGRESS_EVERY})",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.progress_every < 0:
            raise ConfigurationError("INVALID_PROGRESS_INTERVAL")
        repo_root = find_repo_root(Path(__file__))
        if args.dry_run:
            result = dry_run(repo_root)
        else:
            result = run_execute(repo_root, progress_every=args.progress_every)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("conclusion", "GO") != "NO-GO" else 2
    except PreflightError as exc:
        # Custom messages are fixed error codes and contain no URL/header/token data.
        print(f"lvb preflight failed: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # defensive: never print exception text, which may contain signed URLs
        print(f"lvb preflight failed: INTERNAL_{type(exc).__name__.upper()}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
