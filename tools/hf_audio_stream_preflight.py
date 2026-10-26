#!/usr/bin/env python3
"""Bounded stream/container preflight for five pinned Hugging Face MP4 objects.

The program has no full-object download mode.  It keeps all response bodies in
memory, accepts only validated HTTP range responses for media objects, and
writes only a JSON report containing container metadata and safe request
diagnostics.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import struct
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

try:
    import httpx
except ImportError:  # pragma: no cover - checked by the live CLI
    httpx = None  # type: ignore[assignment]


SCHEMA_VERSION = "1.0.0"
MIN_DURATION_SECONDS = 1_200.0
MAX_DURATION_SECONDS = 5_400.0
DEFAULT_WINDOW_BYTES = 1024 * 1024
DEFAULT_MAX_RESPONSE_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_TOTAL_BYTES = 64 * 1024 * 1024
DEFAULT_MAX_CANDIDATE_BYTES = 12 * 1024 * 1024
MAX_REDIRECTS = 8
MAX_RANGE_REQUESTS_PER_CANDIDATE = 256
MAX_TOP_LEVEL_BOXES = 1024
MAX_BOX_COUNT = 20_000
MAX_BOX_DEPTH = 12
MAX_MOOV_BYTES = 8 * 1024 * 1024

PLAN_PATH = Path("data/acquisition_preflight/hf_audio_stream_preflight_plan.json")
RESULT_PATH = Path("data/acquisition_preflight/hf_audio_stream_preflight_result.json")
SOURCE_CSV_PATH = Path("data/rehearsal_plan/audio_asset_recon_candidates.csv")

ALLOWED_REDIRECT_HOST_SUFFIXES = (
    "huggingface.co",
    ".huggingface.co",
    ".hf.co",
    ".xethub.hf.co",
)
REDIRECT_CODES = {301, 302, 303, 307, 308}
RETRYABLE_ROUTE_STATUSES = {401, 403, 407, 502, 503, 504}
CONTENT_RANGE_RE = re.compile(r"^bytes (\d+)-(\d+)/(\d+)$")
HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")

DECISION_GO = "GO_STREAM_DECLARED_AUDIO_AND_DURATION_PASS"
DECISION_NO_AUDIO = "NO_GO_NO_AUDIO_TRACK"
DECISION_DURATION = "NO_GO_DURATION_OUT_OF_RANGE"
DECISION_CONTAINER = "NO_GO_UNSUPPORTED_OR_INCOMPLETE_CONTAINER"
DECISION_IDENTITY = "NO_GO_IDENTITY_OR_TRANSFER_VALIDATION"

# This closed allowlist is deliberately duplicated in code.  A modified plan
# cannot broaden live access without a corresponding reviewed code change.
EXACT_CANDIDATES: tuple[dict[str, Any], ...] = (
    {
        "candidate_id": "ccp-005",
        "repo_id": "AnonymousFLARE/FLARE_demo",
        "revision": "a7e85c038a16b86afe1109b33cd131ec80d67cb3",
        "path": "sample_0/K759eXmaMTY.mp4",
        "size_bytes": 59_708_138,
        "hash_algorithm": "sha256",
        "hash": "40737590a6b572791746bea7a87ac80c270cdd0750e9aae65b1eeed08232c7c1",
        "blob_id": "111fedd3c829f22e4cf4ab5e6f3183b661751973",
    },
    {
        "candidate_id": "ccp-006",
        "repo_id": "AnonymousFLARE/FLARE_demo",
        "revision": "a7e85c038a16b86afe1109b33cd131ec80d67cb3",
        "path": "sample_1/3uV8XZcIBbk.mp4",
        "size_bytes": 138_115_547,
        "hash_algorithm": "sha256",
        "hash": "84c273cb485ac870515ad3d67e9734677e2ef912124a65fb54e8c641239293ae",
        "blob_id": "0fe28e569407bb7c118632f3d708a0760ccbb38b",
    },
    {
        "candidate_id": "omni-video_284",
        "repo_id": "NJU-LINK/OmniVideoBench",
        "revision": "1b1aa0899fca5aa92e4fe5dcd3b60be58efff6ca",
        "path": "videos/video_284.mp4",
        "size_bytes": 190_135_475,
        "hash_algorithm": "sha256",
        "hash": "3dc86a78b36ed6bd920b6e31fe4da1e094522fe3345b6580a1e88fd758461614",
        "blob_id": "aea0ef1a3e924e2ad35fde07df2a9aec5518b226",
    },
    {
        "candidate_id": "omni-video_617",
        "repo_id": "NJU-LINK/OmniVideoBench",
        "revision": "1b1aa0899fca5aa92e4fe5dcd3b60be58efff6ca",
        "path": "videos/video_617.mp4",
        "size_bytes": 61_884_190,
        "hash_algorithm": "sha256",
        "hash": "772b34bd3d3ae5d6fb9b16fbab4d1daf938d78b507caf2656d4fccb68f06541e",
        "blob_id": "834affb998614177592c112f6ea98767401e47b0",
    },
    {
        "candidate_id": "omni-video_611",
        "repo_id": "NJU-LINK/OmniVideoBench",
        "revision": "1b1aa0899fca5aa92e4fe5dcd3b60be58efff6ca",
        "path": "videos/video_611.mp4",
        "size_bytes": 95_163_435,
        "hash_algorithm": "sha256",
        "hash": "8a95a8873fbef1989ac972cb22ff2db7967f533260b430dda86ea9b7c5b11e04",
        "blob_id": "38c2d1b3e83b3af43022f1df114c14e2659a28b2",
    },
)


class PreflightError(RuntimeError):
    """Credential-free, stable failure code."""


class ConfigurationError(PreflightError):
    pass


class TransferValidationError(PreflightError):
    pass


class ContainerError(PreflightError):
    pass


class UnsupportedContainerError(ContainerError):
    pass


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
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
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def strip_url_secrets(url: str) -> str:
    """Retain only scheme, host, port, and path; reject embedded credentials."""
    parsed = urlsplit(url)
    if parsed.username is not None or parsed.password is not None:
        raise TransferValidationError("URL_USERINFO_PROHIBITED")
    host = parsed.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    netloc = host if parsed.port is None else f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


def proxy_label(proxy_url: str | None) -> str:
    if proxy_url is None:
        return "environment-or-direct"
    parsed = urlsplit(proxy_url)
    host = parsed.hostname or "configured-proxy"
    return f"{host}:{parsed.port}" if parsed.port else host


def validate_proxy_url(proxy_url: str) -> None:
    parsed = urlsplit(proxy_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ConfigurationError("INVALID_PROXY_CONFIGURATION")


def load_hf_token() -> str | None:
    """Load the existing Hugging Face login in memory without logging it."""
    try:
        from huggingface_hub import get_token
    except ImportError:
        return os.environ.get("HF_TOKEN")
    return get_token() or os.environ.get("HF_TOKEN")


def canonical_url(candidate: "Candidate") -> str:
    return (
        "https://huggingface.co/datasets/"
        f"{quote(candidate.repo_id, safe='/')}/resolve/"
        f"{quote(candidate.revision, safe='')}/{quote(candidate.path, safe='/')}"
    )


def host_allowed(host: str) -> bool:
    normalized = host.lower().rstrip(".")
    return any(
        normalized == suffix.lstrip(".")
        or (suffix.startswith(".") and normalized.endswith(suffix))
        for suffix in ALLOWED_REDIRECT_HOST_SUFFIXES
    )


def normalize_etag(value: str | None) -> str | None:
    if value is None:
        return None
    result = value.strip()
    if result.startswith("W/"):
        result = result[2:].strip()
    return result.strip('"').removeprefix("sha256:").lower()


def parse_content_range(value: str) -> tuple[int, int, int]:
    match = CONTENT_RANGE_RE.fullmatch(value.strip())
    if not match:
        raise TransferValidationError("INVALID_CONTENT_RANGE")
    return tuple(int(item) for item in match.groups())  # type: ignore[return-value]


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    repo_id: str
    revision: str
    path: str
    size_bytes: int
    hash_algorithm: str
    hash: str
    blob_id: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "Candidate":
        candidate = cls(
            candidate_id=str(value["candidate_id"]),
            repo_id=str(value["repo_id"]),
            revision=str(value["revision"]),
            path=str(value["path"]),
            size_bytes=int(value["size_bytes"]),
            hash_algorithm=str(value["hash_algorithm"]),
            hash=str(value["hash"]).lower(),
            blob_id=str(value["blob_id"]).lower(),
        )
        candidate.validate()
        return candidate

    def validate(self) -> None:
        if not self.candidate_id or "/" in self.candidate_id:
            raise ConfigurationError("INVALID_CANDIDATE_ID")
        if self.repo_id.count("/") != 1:
            raise ConfigurationError("INVALID_REPO_ID")
        posix = PurePosixPath(self.path)
        if posix.is_absolute() or ".." in posix.parts or str(posix) != self.path:
            raise ConfigurationError("INVALID_OBJECT_PATH")
        if not self.path.lower().endswith(".mp4"):
            raise ConfigurationError("NON_MP4_OBJECT_PROHIBITED")
        if not HEX40_RE.fullmatch(self.revision):
            raise ConfigurationError("INVALID_PINNED_REVISION")
        if self.size_bytes <= 0:
            raise ConfigurationError("INVALID_PINNED_SIZE")
        if self.hash_algorithm != "sha256" or not HEX64_RE.fullmatch(self.hash):
            raise ConfigurationError("INVALID_PINNED_HASH")
        if not HEX40_RE.fullmatch(self.blob_id):
            raise ConfigurationError("INVALID_PINNED_BLOB_ID")

    def identity_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "repo_id": self.repo_id,
            "revision": self.revision,
            "path": self.path,
            "size_bytes": self.size_bytes,
            "hash_algorithm": self.hash_algorithm,
            "hash": self.hash,
            "blob_id": self.blob_id,
        }


def load_plan(path: Path = PLAN_PATH) -> tuple[dict[str, Any], list[Candidate]]:
    with path.open(encoding="utf-8") as handle:
        plan = json.load(handle)
    raw = plan.get("candidates")
    if not isinstance(raw, list):
        raise ConfigurationError("PLAN_CANDIDATES_NOT_LIST")
    candidates = [Candidate.from_mapping(item) for item in raw]
    expected = [Candidate.from_mapping(item) for item in EXACT_CANDIDATES]
    if candidates != expected:
        raise ConfigurationError("PLAN_DOES_NOT_MATCH_EXACT_ALLOWLIST")
    return plan, candidates


def validate_source_csv(candidates: Sequence[Candidate], path: Path = SOURCE_CSV_PATH) -> None:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = {row["candidate_id"]: row for row in csv.DictReader(handle)}
    for candidate in candidates:
        row = rows.get(candidate.candidate_id)
        if row is None:
            raise ConfigurationError("CANDIDATE_MISSING_FROM_SOURCE_CSV")
        actual = {
            "repo_id": row["release_id"],
            "revision": row["release_revision"],
            "path": row["object_path"],
            "size_bytes": int(row["object_size_bytes"]),
            "hash_algorithm": row["object_hash_algorithm"],
            "hash": row["object_hash"].lower(),
            "blob_id": row["object_blob_id"].lower(),
        }
        expected = candidate.identity_dict().copy()
        expected.pop("candidate_id")
        if actual != expected:
            raise ConfigurationError("SOURCE_CSV_IDENTITY_MISMATCH")


@dataclass
class Budget:
    maximum_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES
    maximum_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES
    total_bytes: int = 0
    maximum_observed_response: int = 0

    def check_request(self, count: int) -> None:
        if count <= 0:
            raise TransferValidationError("INVALID_REQUEST_BODY_SIZE")
        if count > self.maximum_response_bytes:
            raise TransferValidationError("REQUEST_EXCEEDS_BODY_LIMIT")
        if self.total_bytes + count > self.maximum_total_bytes:
            raise TransferValidationError("AGGREGATE_BODY_LIMIT_EXCEEDED")

    def account(self, count: int) -> None:
        self.check_request(count)
        self.total_bytes += count
        self.maximum_observed_response = max(self.maximum_observed_response, count)


@dataclass
class RequestRecord:
    candidate_id: str
    method: str
    requested_range: str | None
    purpose: str
    canonical_url: str
    proxy_attempts: list[str] = field(default_factory=list)
    redirect_chain: list[dict[str, Any]] = field(default_factory=list)
    response_status: int | None = None
    content_length: int | None = None
    content_range: str | None = None
    effective_host: str | None = None
    effective_url: str | None = None
    bytes_received: int = 0
    body_sha256: str | None = None
    error_code: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class HeadIdentity:
    size_match: bool
    revision_match: bool
    sha256_match: bool
    observed_revision: str | None
    observed_sha256: str | None
    observed_linked_size: int | None

    @property
    def matches(self) -> bool:
        return self.size_match and self.revision_match and self.sha256_match

    def as_dict(self) -> dict[str, Any]:
        return {
            "size_match": self.size_match,
            "revision_match": self.revision_match,
            "sha256_match": self.sha256_match,
            "observed_revision": self.observed_revision,
            "observed_sha256": self.observed_sha256,
            "observed_linked_size": self.observed_linked_size,
        }


@dataclass(frozen=True)
class DirectURLCandidate:
    """Exact direct HTTPS object identity for non-Hugging-Face adapters."""

    candidate_id: str
    url: str
    size_bytes: int
    etag: str
    last_modified: str
    content_type: str
    accept_ranges: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "DirectURLCandidate":
        candidate = cls(
            candidate_id=str(value["candidate_id"]),
            url=str(value["url"]),
            size_bytes=int(value["size_bytes"]),
            etag=str(value["etag"]),
            last_modified=str(value["last_modified"]),
            content_type=str(value["content_type"]),
            accept_ranges=str(value["accept_ranges"]),
        )
        candidate.validate()
        return candidate

    def validate(self) -> None:
        if not self.candidate_id or "/" in self.candidate_id:
            raise ConfigurationError("INVALID_CANDIDATE_ID")
        parsed = urlsplit(self.url)
        if (
            parsed.scheme.lower() != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or not parsed.path.lower().endswith(".mp4")
        ):
            raise ConfigurationError("INVALID_DIRECT_MP4_URL")
        if self.size_bytes <= 0:
            raise ConfigurationError("INVALID_PINNED_SIZE")
        if not self.etag.strip():
            raise ConfigurationError("MISSING_PINNED_ETAG")
        if not self.last_modified.strip():
            raise ConfigurationError("MISSING_PINNED_LAST_MODIFIED")
        if self.content_type.split(";", 1)[0].strip().lower() != "video/mp4":
            raise ConfigurationError("INVALID_PINNED_CONTENT_TYPE")
        if self.accept_ranges.strip().lower() != "bytes":
            raise ConfigurationError("PINNED_OBJECT_NOT_BYTE_RANGE_CAPABLE")

    def identity_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "url": self.url,
            "size_bytes": self.size_bytes,
            "etag": self.etag,
            "last_modified": self.last_modified,
            "content_type": self.content_type,
            "accept_ranges": self.accept_ranges,
        }


@dataclass(frozen=True)
class DirectHeadIdentity:
    size_match: bool
    etag_match: bool
    last_modified_match: bool
    content_type_match: bool
    accept_ranges_match: bool
    effective_url_match: bool
    observed_size_bytes: int | None
    observed_etag: str | None
    observed_last_modified: str | None
    observed_content_type: str | None
    observed_accept_ranges: str | None
    observed_effective_url: str | None

    @property
    def matches(self) -> bool:
        return all(
            (
                self.size_match,
                self.etag_match,
                self.last_modified_match,
                self.content_type_match,
                self.accept_ranges_match,
                self.effective_url_match,
            )
        )

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


class SafeHFRangeClient:
    """Manual-redirect, failover-capable, media-range-only HTTP client."""

    def __init__(
        self,
        token: str | None,
        *,
        proxies: Sequence[str] = (),
        budget: Budget | None = None,
        maximum_candidate_bytes: int = DEFAULT_MAX_CANDIDATE_BYTES,
        clients: Sequence[Any] | None = None,
        url_for: Callable[[Any], str] = canonical_url,
        allowed_host: Callable[[str], bool] = host_allowed,
        send_bearer_token: bool = True,
        user_agent: str = "AV-TRACE-hf-stream-preflight/1.0",
    ) -> None:
        if send_bearer_token and not token:
            raise ConfigurationError("HF_TOKEN_NOT_AVAILABLE")
        if httpx is None:
            raise ConfigurationError("HTTPX_NOT_INSTALLED")
        for proxy in proxies:
            validate_proxy_url(proxy)
        if clients is not None and proxies:
            raise ConfigurationError("CLIENTS_AND_PROXIES_ARE_MUTUALLY_EXCLUSIVE")
        if (
            maximum_candidate_bytes <= 0
            or maximum_candidate_bytes > DEFAULT_MAX_CANDIDATE_BYTES
        ):
            raise ConfigurationError("INVALID_CANDIDATE_BODY_LIMIT")
        self._token = token or ""
        self._url_for = url_for
        self._allowed_host = allowed_host
        self._send_bearer_token = send_bearer_token
        self.budget = budget or Budget()
        self.maximum_candidate_bytes = maximum_candidate_bytes
        self.records: list[RequestRecord] = []
        self._range_cache: dict[tuple[str, int, int], bytes] = {}
        self._candidate_bytes: dict[str, int] = {}
        self._effective_url_cache: dict[tuple[int, str], str] = {}
        self._owns_clients = clients is None
        if clients is not None:
            self._routes = [(None, client) for client in clients]
        else:
            route_urls: list[str | None] = list(proxies) if proxies else [None]
            self._routes = []
            for proxy in route_urls:
                kwargs: dict[str, Any] = {
                    "follow_redirects": False,
                    "timeout": httpx.Timeout(60.0, connect=30.0),
                    "headers": {"User-Agent": user_agent},
                }
                if proxy is None:
                    kwargs["trust_env"] = True
                else:
                    kwargs["trust_env"] = False
                    kwargs["proxy"] = proxy
                self._routes.append((proxy, httpx.Client(**kwargs)))

    def close(self) -> None:
        self._token = ""
        self._effective_url_cache.clear()
        self._range_cache.clear()
        if self._owns_clients:
            for _, client in self._routes:
                client.close()

    def __enter__(self) -> "SafeHFRangeClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def _origin(parsed: Any) -> tuple[str, str, int]:
        return (
            parsed.scheme.lower(),
            (parsed.hostname or "").lower().rstrip("."),
            parsed.port or 443,
        )

    def _validated_url(self, url: str) -> Any:
        parsed = urlsplit(url)
        if parsed.scheme.lower() != "https":
            raise TransferValidationError("NON_HTTPS_REQUEST_OR_REDIRECT")
        if parsed.username is not None or parsed.password is not None:
            raise TransferValidationError("URL_USERINFO_PROHIBITED")
        try:
            port = parsed.port
        except ValueError:
            raise TransferValidationError("INVALID_URL_PORT") from None
        if not parsed.hostname or not self._allowed_host(parsed.hostname):
            raise TransferValidationError("REDIRECT_HOST_NOT_ALLOWED")
        if port is not None and not 1 <= port <= 65535:
            raise TransferValidationError("INVALID_URL_PORT")
        return parsed

    def _single_route(
        self,
        route_index: int,
        client: Any,
        candidate: Candidate,
        method: str,
        requested_range: tuple[int, int] | None,
        record: RequestRecord,
    ) -> tuple[bytes, Mapping[str, str], list[Mapping[str, str]], int]:
        initial_url = self._url_for(candidate)
        canonical_origin = self._origin(self._validated_url(initial_url))
        cache_key = (route_index, initial_url)
        url = (
            self._effective_url_cache.get(cache_key, initial_url)
            if requested_range is not None
            else initial_url
        )
        canonical_resolution = url == initial_url
        refreshed = False
        redirects = 0
        identity_header_sets: list[Mapping[str, str]] = []
        while True:
            parsed = self._validated_url(url)
            headers = {"Accept-Encoding": "identity"}
            if (
                self._send_bearer_token
                and canonical_resolution
                and self._origin(parsed) == canonical_origin
            ):
                headers["Authorization"] = f"Bearer {self._token}"
            if requested_range is not None:
                headers["Range"] = (
                    f"bytes={requested_range[0]}-{requested_range[1]}"
                )
            with client.stream(method, url, headers=headers) as response:
                identity_header_sets.append(dict(response.headers))
                if response.status_code in REDIRECT_CODES:
                    location = response.headers.get("location")
                    if not location:
                        raise TransferValidationError("REDIRECT_WITHOUT_LOCATION")
                    next_url = urljoin(url, location)
                    next_parsed = self._validated_url(next_url)
                    record.redirect_chain.append(
                        {
                            "status_code": response.status_code,
                            "from_host": (parsed.hostname or "").lower(),
                            "to_host": (next_parsed.hostname or "").lower(),
                            "location": strip_url_secrets(next_url),
                        }
                    )
                    redirects += 1
                    if redirects > MAX_REDIRECTS:
                        raise TransferValidationError("TOO_MANY_REDIRECTS")
                    canonical_resolution = (
                        canonical_resolution
                        and self._origin(parsed) == canonical_origin
                        and self._origin(next_parsed) == canonical_origin
                    )
                    url = next_url
                    continue
                if (
                    requested_range is not None
                    and url != initial_url
                    and not refreshed
                    and response.status_code in {400, 401, 403}
                ):
                    self._effective_url_cache.pop(cache_key, None)
                    refreshed = True
                    canonical_resolution = True
                    url = initial_url
                    continue
                status = response.status_code
                if status in RETRYABLE_ROUTE_STATUSES:
                    return b"", response.headers, identity_header_sets, status
                record.response_status = status
                record.effective_host = (parsed.hostname or "").lower()
                record.effective_url = strip_url_secrets(url)
                raw_length = response.headers.get("content-length")
                if raw_length is None or not raw_length.isdigit():
                    raise TransferValidationError(
                        "MISSING_OR_INVALID_CONTENT_LENGTH"
                    )
                content_length = int(raw_length)
                record.content_length = content_length
                encoding = response.headers.get("content-encoding", "identity")
                if encoding.lower() != "identity":
                    raise TransferValidationError(
                        "UNEXPECTED_CONTENT_ENCODING"
                    )

                if requested_range is None:
                    if status != 200:
                        raise TransferValidationError("UNEXPECTED_HEAD_STATUS")
                    if content_length != candidate.size_bytes:
                        raise TransferValidationError(
                            "UNEXPECTED_HEAD_CONTENT_LENGTH"
                        )
                    return b"", response.headers, identity_header_sets, status

                start, end = requested_range
                expected_length = end - start + 1
                if status == 200:
                    raise TransferValidationError(
                        "RANGE_IGNORED_FULL_OBJECT_200"
                    )
                if status != 206:
                    raise TransferValidationError("UNEXPECTED_RANGE_STATUS")
                if content_length != expected_length:
                    raise TransferValidationError(
                        "UNEXPECTED_RANGE_CONTENT_LENGTH"
                    )
                raw_content_range = response.headers.get("content-range")
                record.content_range = raw_content_range
                if raw_content_range is None:
                    raise TransferValidationError("MISSING_CONTENT_RANGE")
                if parse_content_range(raw_content_range) != (
                    start,
                    end,
                    candidate.size_bytes,
                ):
                    raise TransferValidationError("MISMATCHED_CONTENT_RANGE")
                self.budget.check_request(expected_length)
                if (
                    self._candidate_bytes.get(candidate.candidate_id, 0)
                    + expected_length
                    > self.maximum_candidate_bytes
                ):
                    raise TransferValidationError(
                        "CANDIDATE_BODY_LIMIT_EXCEEDED"
                    )
                body = bytearray()
                # Content-Encoding was required to be identity, so iter_bytes()
                # is byte-for-byte equivalent and works with MockTransport too.
                for chunk in response.iter_bytes():
                    if len(body) + len(chunk) > expected_length:
                        raise TransferValidationError(
                            "RANGE_RESPONSE_EXCESS_BYTES"
                        )
                    if (
                        len(body) + len(chunk)
                        > self.budget.maximum_response_bytes
                    ):
                        raise TransferValidationError(
                            "RESPONSE_BODY_LIMIT_EXCEEDED"
                        )
                    body.extend(chunk)
                if len(body) != expected_length:
                    raise TransferValidationError("RANGE_RESPONSE_TRUNCATED")
                self.budget.account(len(body))
                self._candidate_bytes[candidate.candidate_id] = (
                    self._candidate_bytes.get(candidate.candidate_id, 0)
                    + len(body)
                )
                if url != initial_url:
                    self._effective_url_cache[cache_key] = url
                return bytes(body), response.headers, identity_header_sets, status

    def _request(
        self,
        candidate: Candidate,
        method: str,
        purpose: str,
        requested_range: tuple[int, int] | None,
    ) -> tuple[bytes, list[Mapping[str, str]]]:
        range_text = (
            None
            if requested_range is None
            else f"bytes={requested_range[0]}-{requested_range[1]}"
        )
        record = RequestRecord(
            candidate_id=candidate.candidate_id,
            method=method,
            requested_range=range_text,
            purpose=purpose,
            canonical_url=self._url_for(candidate),
        )
        if method == "GET" and sum(
            item.candidate_id == candidate.candidate_id
            and item.method == "GET"
            for item in self.records
        ) >= MAX_RANGE_REQUESTS_PER_CANDIDATE:
            raise TransferValidationError(
                "CANDIDATE_RANGE_REQUEST_LIMIT_EXCEEDED"
            )
        self.records.append(record)
        last_transport_code = "NO_PROXY_ROUTE_SUCCEEDED"
        try:
            for index, (proxy, client) in enumerate(self._routes):
                record.proxy_attempts.append(proxy_label(proxy))
                try:
                    body, _, identity_headers, status = self._single_route(
                        index,
                        client,
                        candidate,
                        method,
                        requested_range,
                        record,
                    )
                except (
                    httpx.TransportError,
                    httpx.TimeoutException,
                ) as exc:
                    last_transport_code = (
                        f"HTTP_TRANSPORT_{type(exc).__name__.upper()}"
                    )
                    continue
                if status in RETRYABLE_ROUTE_STATUSES:
                    last_transport_code = f"HTTP_STATUS_{status}"
                    continue
                record.bytes_received = len(body)
                if body:
                    record.body_sha256 = hashlib.sha256(body).hexdigest()
                return body, identity_headers
            raise TransferValidationError(last_transport_code)
        except PreflightError as exc:
            record.error_code = str(exc)
            raise
        except Exception as exc:
            # Never retain exception text: it can contain bearer or signed URL data.
            code = f"HTTP_FAILURE_{type(exc).__name__.upper()}"
            record.error_code = code
            raise TransferValidationError(code) from None

    def head(self, candidate: Candidate, purpose: str = "identity-head") -> HeadIdentity:
        _, header_sets = self._request(candidate, "HEAD", purpose, None)
        revisions: list[str] = []
        digests: list[str] = []
        linked_sizes: list[int] = []
        for headers in header_sets:
            revision = headers.get("x-repo-commit")
            if revision:
                revisions.append(revision.lower())
            for name in ("x-linked-etag", "etag"):
                digest = normalize_etag(headers.get(name))
                if digest and HEX64_RE.fullmatch(digest):
                    digests.append(digest)
            linked_size = headers.get("x-linked-size")
            if linked_size and linked_size.isdigit():
                linked_sizes.append(int(linked_size))
        # A pinned resolver plus exact final length is necessary but not enough:
        # require HF's linked-object digest header to bind the LFS SHA-256.
        revision_match = not revisions or all(
            item == candidate.revision for item in revisions
        )
        size_match = not linked_sizes or all(
            item == candidate.size_bytes for item in linked_sizes
        )
        digest_match = candidate.hash in digests
        return HeadIdentity(
            size_match=size_match,
            revision_match=revision_match,
            sha256_match=digest_match,
            observed_revision=revisions[-1] if revisions else None,
            observed_sha256=candidate.hash if digest_match else (
                digests[-1] if digests else None
            ),
            observed_linked_size=linked_sizes[-1] if linked_sizes else None,
        )

    def fetch_range(
        self, candidate: Candidate, start: int, end: int, purpose: str
    ) -> bytes:
        if start < 0 or end < start or end >= candidate.size_bytes:
            raise TransferValidationError("RANGE_OUTSIDE_PINNED_OBJECT")
        if start == 0 and end == candidate.size_bytes - 1:
            raise TransferValidationError("COMPLETE_OBJECT_RANGE_PROHIBITED")
        length = end - start + 1
        self.budget.check_request(length)
        key = (candidate.candidate_id, start, end)
        cached = self._range_cache.get(key)
        if cached is None:
            cached, _ = self._request(
                candidate, "GET", purpose, (start, end)
            )
            self._range_cache[key] = cached
        return cached

    def release_candidate_bytes(self, candidate_id: str) -> None:
        """Drop in-memory media windows after one candidate is classified."""
        for key in [
            key for key in self._range_cache if key[0] == candidate_id
        ]:
            del self._range_cache[key]


class SafeDirectURLRangeClient(SafeHFRangeClient):
    """Shared bounded range client for exact direct HTTPS MP4 URLs.

    It deliberately disables bearer authentication and validates every
    redirect with the adapter-provided closed host predicate.
    """

    def __init__(
        self,
        *,
        allowed_host: Callable[[str], bool],
        proxies: Sequence[str] = (),
        budget: Budget | None = None,
        maximum_candidate_bytes: int = DEFAULT_MAX_CANDIDATE_BYTES,
        clients: Sequence[Any] | None = None,
        user_agent: str = "AV-TRACE-direct-stream-preflight/1.0",
    ) -> None:
        super().__init__(
            None,
            proxies=proxies,
            budget=budget,
            maximum_candidate_bytes=maximum_candidate_bytes,
            clients=clients,
            url_for=lambda candidate: candidate.url,
            allowed_host=allowed_host,
            send_bearer_token=False,
            user_agent=user_agent,
        )

    def head(
        self,
        candidate: DirectURLCandidate,
        purpose: str = "identity-head",
    ) -> DirectHeadIdentity:
        _, header_sets = self._request(candidate, "HEAD", purpose, None)
        headers = header_sets[-1]
        record = self.records[-1]
        raw_size = headers.get("content-length")
        observed_size = (
            int(raw_size) if raw_size is not None and raw_size.isdigit() else None
        )
        observed_etag = headers.get("etag")
        observed_last_modified = headers.get("last-modified")
        observed_content_type = headers.get("content-type")
        observed_accept_ranges = headers.get("accept-ranges")
        observed_effective_url = record.effective_url
        normalized_content_type = (
            observed_content_type.split(";", 1)[0].strip().lower()
            if observed_content_type
            else None
        )
        return DirectHeadIdentity(
            size_match=observed_size == candidate.size_bytes,
            etag_match=observed_etag == candidate.etag,
            last_modified_match=(
                observed_last_modified == candidate.last_modified
            ),
            content_type_match=(
                normalized_content_type
                == candidate.content_type.split(";", 1)[0].strip().lower()
            ),
            accept_ranges_match=(
                (observed_accept_ranges or "").strip().lower()
                == candidate.accept_ranges.strip().lower()
            ),
            effective_url_match=observed_effective_url == candidate.url,
            observed_size_bytes=observed_size,
            observed_etag=observed_etag,
            observed_last_modified=observed_last_modified,
            observed_content_type=observed_content_type,
            observed_accept_ranges=observed_accept_ranges,
            observed_effective_url=observed_effective_url,
        )


@dataclass(frozen=True)
class BoxHeader:
    offset: int
    size: int
    type: bytes
    header_size: int

    @property
    def end(self) -> int:
        return self.offset + self.size


def parse_box_header(
    data: bytes, offset: int, limit: int, *, absolute_base: int = 0
) -> BoxHeader:
    if offset < 0 or limit > len(data) or offset + 8 > limit:
        raise ContainerError("TRUNCATED_BOX_HEADER")
    size32, box_type = struct.unpack_from(">I4s", data, offset)
    header_size = 8
    if size32 == 1:
        if offset + 16 > limit:
            raise ContainerError("TRUNCATED_EXTENDED_BOX_HEADER")
        size = struct.unpack_from(">Q", data, offset + 8)[0]
        header_size = 16
    elif size32 == 0:
        size = limit - offset
    else:
        size = size32
    if box_type == b"uuid":
        header_size += 16
        if offset + header_size > limit:
            raise ContainerError("TRUNCATED_UUID_BOX_HEADER")
    if size < header_size:
        raise ContainerError("BOX_SIZE_SMALLER_THAN_HEADER")
    if offset + size > limit:
        raise ContainerError("BOX_EXTENDS_PAST_PARENT")
    return BoxHeader(
        offset=absolute_base + offset,
        size=size,
        type=box_type,
        header_size=header_size,
    )


def parse_header_prefix(prefix: bytes, offset: int, total_size: int) -> BoxHeader:
    if len(prefix) < 8:
        raise ContainerError("TRUNCATED_TOP_LEVEL_HEADER")
    size32, box_type = struct.unpack_from(">I4s", prefix, 0)
    header_size = 8
    if size32 == 1:
        if len(prefix) < 16:
            raise ContainerError("TRUNCATED_EXTENDED_TOP_LEVEL_HEADER")
        size = struct.unpack_from(">Q", prefix, 8)[0]
        header_size = 16
    elif size32 == 0:
        size = total_size - offset
    else:
        size = size32
    if box_type == b"uuid":
        header_size += 16
    if size < header_size:
        raise ContainerError("TOP_LEVEL_SIZE_SMALLER_THAN_HEADER")
    if offset + size > total_size:
        raise ContainerError("TOP_LEVEL_BOX_PAST_EOF")
    return BoxHeader(offset=offset, size=size, type=box_type, header_size=header_size)


@dataclass
class SparseBytes:
    candidate: Candidate
    client: SafeHFRangeClient
    spans: list[tuple[int, bytes]] = field(default_factory=list)

    def add(self, start: int, body: bytes) -> None:
        if not body:
            return
        self.spans.append((start, body))
        self.spans.sort(key=lambda item: item[0])
        merged: list[tuple[int, bytes]] = []
        for span_start, span_body in self.spans:
            if not merged:
                merged.append((span_start, span_body))
                continue
            previous_start, previous_body = merged[-1]
            previous_end = previous_start + len(previous_body)
            if span_start > previous_end:
                merged.append((span_start, span_body))
                continue
            overlap = previous_end - span_start
            if overlap < len(span_body):
                merged[-1] = (
                    previous_start,
                    previous_body + span_body[max(0, overlap) :],
                )
        self.spans = merged

    def available(self, start: int, length: int) -> bytes | None:
        end = start + length
        for span_start, body in self.spans:
            span_end = span_start + len(body)
            if span_start <= start and end <= span_end:
                relative = start - span_start
                return body[relative : relative + length]
        return None

    def read(self, start: int, length: int, purpose: str) -> bytes:
        if start < 0 or length <= 0 or start + length > self.candidate.size_bytes:
            raise TransferValidationError("SPARSE_READ_OUTSIDE_OBJECT")
        present = self.available(start, length)
        if present is not None:
            return present
        end = start + length
        cursor = start
        chunks: list[bytes] = []
        while cursor < end:
            present_span = next(
                (
                    (span_start, body)
                    for span_start, body in self.spans
                    if span_start <= cursor < span_start + len(body)
                ),
                None,
            )
            if present_span:
                span_start, body = present_span
                take = min(end, span_start + len(body)) - cursor
                relative = cursor - span_start
                chunks.append(body[relative : relative + take])
                cursor += take
                continue
            next_start = min(
                (
                    span_start
                    for span_start, _ in self.spans
                    if span_start > cursor
                ),
                default=end,
            )
            fetch_end = min(
                end,
                next_start,
                cursor + self.client.budget.maximum_response_bytes,
            )
            body = self.client.fetch_range(
                self.candidate, cursor, fetch_end - 1, purpose
            )
            self.add(cursor, body)
            chunks.append(body)
            cursor = fetch_end
        result = b"".join(chunks)
        if len(result) != length:
            raise TransferValidationError("SPARSE_READ_LENGTH_MISMATCH")
        return result


@dataclass(frozen=True)
class TrackInfo:
    handler_type: str
    media_timescale: int
    media_duration_units: int
    media_duration_seconds: float
    movie_duration_units: int | None
    movie_duration_seconds: float | None

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class ContainerInfo:
    major_brand: str
    compatible_brands: tuple[str, ...]
    duration_seconds: float
    movie_timescale: int
    movie_duration_units: int
    tracks: tuple[TrackInfo, ...]
    video_track_count: int
    audio_track_count: int
    av_timeline_relation: str


class BoxWalker:
    def __init__(self, data: bytes, *, absolute_base: int = 0) -> None:
        self.data = data
        self.absolute_base = absolute_base
        self.box_count = 0

    def children(
        self, start: int, end: int, *, depth: int
    ) -> Iterable[tuple[BoxHeader, int, int]]:
        if depth > MAX_BOX_DEPTH:
            raise ContainerError("MAXIMUM_BOX_DEPTH_EXCEEDED")
        cursor = start
        while cursor < end:
            self.box_count += 1
            if self.box_count > MAX_BOX_COUNT:
                raise ContainerError("MAXIMUM_BOX_COUNT_EXCEEDED")
            header = parse_box_header(
                self.data,
                cursor,
                end,
                absolute_base=self.absolute_base,
            )
            local_payload = cursor + header.header_size
            local_end = cursor + header.size
            yield header, local_payload, local_end
            if local_end <= cursor:
                raise ContainerError("NON_ADVANCING_BOX")
            cursor = local_end
        if cursor != end:
            raise ContainerError("BOX_CHILDREN_DO_NOT_FILL_PARENT")


def _one_box(
    boxes: Sequence[tuple[BoxHeader, int, int]],
    box_type: bytes,
    *,
    required: bool,
) -> tuple[BoxHeader, int, int] | None:
    matches = [item for item in boxes if item[0].type == box_type]
    if len(matches) > 1:
        raise ContainerError(f"DUPLICATE_{box_type.decode('latin1')}_BOX")
    if required and not matches:
        raise ContainerError(f"MISSING_{box_type.decode('latin1')}_BOX")
    return matches[0] if matches else None


def _parse_full_box_duration(
    data: bytes, payload_start: int, payload_end: int, box_name: str
) -> tuple[int, int]:
    payload = data[payload_start:payload_end]
    if len(payload) < 20:
        raise ContainerError(f"TRUNCATED_{box_name.upper()}_BOX")
    version = payload[0]
    if version == 0:
        if len(payload) < 20:
            raise ContainerError(f"TRUNCATED_{box_name.upper()}_V0")
        timescale = struct.unpack_from(">I", payload, 12)[0]
        duration = struct.unpack_from(">I", payload, 16)[0]
        unknown = 0xFFFFFFFF
    elif version == 1:
        if len(payload) < 32:
            raise ContainerError(f"TRUNCATED_{box_name.upper()}_V1")
        timescale = struct.unpack_from(">I", payload, 20)[0]
        duration = struct.unpack_from(">Q", payload, 24)[0]
        unknown = 0xFFFFFFFFFFFFFFFF
    else:
        raise UnsupportedContainerError(
            f"UNSUPPORTED_{box_name.upper()}_VERSION"
        )
    if timescale == 0:
        raise ContainerError(f"ZERO_{box_name.upper()}_TIMESCALE")
    if duration in {0, unknown}:
        raise UnsupportedContainerError(
            f"UNKNOWN_OR_ZERO_{box_name.upper()}_DURATION"
        )
    return timescale, duration


def _parse_tkhd_duration(
    data: bytes, payload_start: int, payload_end: int
) -> int | None:
    payload = data[payload_start:payload_end]
    if len(payload) < 24:
        raise ContainerError("TRUNCATED_TKHD_BOX")
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
        raise UnsupportedContainerError("UNSUPPORTED_TKHD_VERSION")
    return None if duration in {0, unknown} else duration


def _parse_handler(data: bytes, payload_start: int, payload_end: int) -> str:
    payload = data[payload_start:payload_end]
    if len(payload) < 12:
        raise ContainerError("TRUNCATED_HDLR_BOX")
    raw = payload[8:12]
    try:
        return raw.decode("ascii")
    except UnicodeDecodeError:
        return raw.hex()


def parse_ftyp(box: bytes) -> tuple[str, tuple[str, ...]]:
    header = parse_box_header(box, 0, len(box))
    if header.type != b"ftyp" or header.size != len(box):
        raise ContainerError("INVALID_FTYP_BOX")
    payload = box[header.header_size :]
    if len(payload) < 8 or len(payload) % 4:
        raise ContainerError("MALFORMED_FTYP_PAYLOAD")
    major = payload[:4].decode("latin1")
    compatible = tuple(
        payload[index : index + 4].decode("latin1")
        for index in range(8, len(payload), 4)
    )
    return major, compatible


def timeline_relation(
    tracks: Sequence[TrackInfo], container_duration: float
) -> str:
    audio = [track for track in tracks if track.handler_type == "soun"]
    video = [track for track in tracks if track.handler_type == "vide"]
    if not audio or not video:
        return "NOT_APPLICABLE_MISSING_AUDIO_OR_VIDEO"
    durations: list[float] = []
    for track in (*audio, *video):
        durations.append(track.media_duration_seconds)
        if track.movie_duration_seconds is not None:
            durations.append(track.movie_duration_seconds)
    if any(value <= 0 for value in durations):
        return "INDETERMINATE_INVALID_TRACK_DURATION"
    tolerance = max(2.0, container_duration * 0.005)
    if (
        max(durations) - min(durations) <= tolerance
        and all(abs(value - container_duration) <= tolerance for value in durations)
    ):
        return "PLAUSIBLY_SYNCHRONIZED"
    return "NOT_PLAUSIBLY_SYNCHRONIZED"


def parse_moov(ftyp_box: bytes, moov_box: bytes) -> ContainerInfo:
    major_brand, compatible_brands = parse_ftyp(ftyp_box)
    moov_header = parse_box_header(moov_box, 0, len(moov_box))
    if moov_header.type != b"moov" or moov_header.size != len(moov_box):
        raise ContainerError("INVALID_MOOV_BOX")
    walker = BoxWalker(moov_box)
    top = list(
        walker.children(
            moov_header.header_size, moov_header.size, depth=1
        )
    )
    if any(item[0].type == b"mvex" for item in top):
        raise UnsupportedContainerError("FRAGMENTED_MP4_MVEX_UNSUPPORTED")
    mvhd = _one_box(top, b"mvhd", required=True)
    assert mvhd is not None
    movie_timescale, movie_duration_units = _parse_full_box_duration(
        moov_box, mvhd[1], mvhd[2], "mvhd"
    )
    duration_seconds = movie_duration_units / movie_timescale
    if not (0 < duration_seconds < 10_000_000):
        raise ContainerError("IMPLAUSIBLE_CONTAINER_DURATION")

    tracks: list[TrackInfo] = []
    trak_boxes = [item for item in top if item[0].type == b"trak"]
    if not trak_boxes:
        raise ContainerError("NO_TRACK_BOXES")
    for _, trak_payload, trak_end in trak_boxes:
        trak_children = list(
            walker.children(trak_payload, trak_end, depth=2)
        )
        tkhd = _one_box(trak_children, b"tkhd", required=False)
        movie_track_units = (
            _parse_tkhd_duration(moov_box, tkhd[1], tkhd[2])
            if tkhd is not None
            else None
        )
        mdia = _one_box(trak_children, b"mdia", required=True)
        assert mdia is not None
        mdia_children = list(
            walker.children(mdia[1], mdia[2], depth=3)
        )
        mdhd = _one_box(mdia_children, b"mdhd", required=True)
        hdlr = _one_box(mdia_children, b"hdlr", required=True)
        assert mdhd is not None and hdlr is not None
        media_timescale, media_duration_units = _parse_full_box_duration(
            moov_box, mdhd[1], mdhd[2], "mdhd"
        )
        handler = _parse_handler(moov_box, hdlr[1], hdlr[2])
        tracks.append(
            TrackInfo(
                handler_type=handler,
                media_timescale=media_timescale,
                media_duration_units=media_duration_units,
                media_duration_seconds=media_duration_units
                / media_timescale,
                movie_duration_units=movie_track_units,
                movie_duration_seconds=(
                    movie_track_units / movie_timescale
                    if movie_track_units is not None
                    else None
                ),
            )
        )
    video_count = sum(track.handler_type == "vide" for track in tracks)
    audio_count = sum(track.handler_type == "soun" for track in tracks)
    return ContainerInfo(
        major_brand=major_brand,
        compatible_brands=compatible_brands,
        duration_seconds=duration_seconds,
        movie_timescale=movie_timescale,
        movie_duration_units=movie_duration_units,
        tracks=tuple(tracks),
        video_track_count=video_count,
        audio_track_count=audio_count,
        av_timeline_relation=timeline_relation(tracks, duration_seconds),
    )


def locate_and_parse(
    candidate: Candidate,
    client: SafeHFRangeClient,
    *,
    window_bytes: int = DEFAULT_WINDOW_BYTES,
) -> ContainerInfo:
    if window_bytes <= 0 or window_bytes > client.budget.maximum_response_bytes:
        raise ConfigurationError("INVALID_INITIAL_WINDOW_SIZE")
    if candidate.size_bytes <= 2 * window_bytes:
        # The allowlisted objects are much larger.  Keep this generic guard so
        # two initial probes can never combine into a complete object transfer.
        raise TransferValidationError("OBJECT_TOO_SMALL_FOR_DISJOINT_WINDOWS")
    sparse = SparseBytes(candidate, client)
    sparse.add(
        0,
        client.fetch_range(
            candidate, 0, window_bytes - 1, "initial-head-window"
        ),
    )
    tail_start = candidate.size_bytes - window_bytes
    sparse.add(
        tail_start,
        client.fetch_range(
            candidate,
            tail_start,
            candidate.size_bytes - 1,
            "initial-tail-window",
        ),
    )

    offset = 0
    ftyp_box: bytes | None = None
    moov_box: bytes | None = None
    saw_moof = False
    top_count = 0
    while offset < candidate.size_bytes:
        top_count += 1
        if top_count > MAX_TOP_LEVEL_BOXES:
            raise ContainerError("MAXIMUM_TOP_LEVEL_BOX_COUNT_EXCEEDED")
        prefix_length = min(32, candidate.size_bytes - offset)
        prefix = sparse.read(offset, prefix_length, "top-level-box-header")
        header = parse_header_prefix(prefix, offset, candidate.size_bytes)
        if header.type == b"ftyp":
            if ftyp_box is not None:
                raise ContainerError("DUPLICATE_FTYP_BOX")
            if header.size > 1024 * 1024:
                raise ContainerError("FTYP_BOX_UNREASONABLY_LARGE")
            ftyp_box = sparse.read(
                header.offset, header.size, "read-complete-ftyp"
            )
        elif header.type == b"moov":
            if moov_box is not None:
                raise ContainerError("DUPLICATE_MOOV_BOX")
            if header.size > MAX_MOOV_BYTES:
                raise UnsupportedContainerError(
                    "MOOV_EXCEEDS_CONSERVATIVE_LIMIT"
                )
            moov_box = sparse.read(
                header.offset, header.size, "read-complete-moov"
            )
        elif header.type == b"moof":
            saw_moof = True
        if header.size == 0 or header.end <= offset:
            raise ContainerError("NON_ADVANCING_TOP_LEVEL_BOX")
        offset = header.end
    if offset != candidate.size_bytes:
        raise ContainerError("TOP_LEVEL_BOXES_DO_NOT_FILL_OBJECT")
    if saw_moof:
        raise UnsupportedContainerError("FRAGMENTED_MP4_MOOF_UNSUPPORTED")
    if ftyp_box is None:
        raise ContainerError("MISSING_FTYP_BOX")
    if moov_box is None:
        raise UnsupportedContainerError("MISSING_MOOV_BOX")
    return parse_moov(ftyp_box, moov_box)


def inspect_mp4_bytes(data: bytes) -> ContainerInfo:
    """Test helper that applies the same strict parser to an in-memory file."""
    offset = 0
    count = 0
    ftyp: bytes | None = None
    moov: bytes | None = None
    saw_moof = False
    while offset < len(data):
        count += 1
        if count > MAX_TOP_LEVEL_BOXES:
            raise ContainerError("MAXIMUM_TOP_LEVEL_BOX_COUNT_EXCEEDED")
        header = parse_box_header(data, offset, len(data))
        local_end = offset + header.size
        if header.type == b"ftyp":
            if ftyp is not None:
                raise ContainerError("DUPLICATE_FTYP_BOX")
            ftyp = data[offset:local_end]
        elif header.type == b"moov":
            if moov is not None:
                raise ContainerError("DUPLICATE_MOOV_BOX")
            moov = data[offset:local_end]
        elif header.type == b"moof":
            saw_moof = True
        offset = local_end
    if saw_moof:
        raise UnsupportedContainerError("FRAGMENTED_MP4_MOOF_UNSUPPORTED")
    if ftyp is None:
        raise ContainerError("MISSING_FTYP_BOX")
    if moov is None:
        raise UnsupportedContainerError("MISSING_MOOV_BOX")
    return parse_moov(ftyp, moov)


def duration_gate(duration: float | None) -> str:
    if duration is None:
        return "UNRESOLVED"
    return (
        "PASS"
        if MIN_DURATION_SECONDS <= duration <= MAX_DURATION_SECONDS
        else "FAIL"
    )


def base_candidate_result(candidate: Candidate) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "identity": candidate.identity_dict(),
        "identity_match": False,
        "container_parse_status": "NOT_ATTEMPTED",
        "duration_seconds": None,
        "duration_gate": "UNRESOLVED",
        "video_track_count": 0,
        "audio_track_count": 0,
        "av_timeline_relation": "UNRESOLVED",
        "range_request_count": 0,
        "response_body_bytes": 0,
        "decision": DECISION_IDENTITY,
        "limitations": [],
    }


def decide(info: ContainerInfo) -> str:
    if info.video_track_count < 1:
        return DECISION_CONTAINER
    if info.audio_track_count < 1:
        return DECISION_NO_AUDIO
    if duration_gate(info.duration_seconds) != "PASS":
        return DECISION_DURATION
    if info.av_timeline_relation != "PLAUSIBLY_SYNCHRONIZED":
        return DECISION_CONTAINER
    return DECISION_GO


def run_candidate(
    candidate: Candidate | DirectURLCandidate,
    client: SafeHFRangeClient,
    *,
    window_bytes: int,
) -> dict[str, Any]:
    result = base_candidate_result(candidate)
    first_record = len(client.records)
    first_bytes = client.budget.total_bytes
    try:
        head = client.head(candidate)
        result["head_identity"] = head.as_dict()
        if not head.matches:
            raise TransferValidationError("HEAD_IDENTITY_MISMATCH")
        result["identity_match"] = True
        info = locate_and_parse(
            candidate, client, window_bytes=window_bytes
        )
        result.update(
            {
                "container_parse_status": "PARSED_ISO_BMFF",
                "duration_seconds": info.duration_seconds,
                "duration_gate": duration_gate(info.duration_seconds),
                "movie_timescale": info.movie_timescale,
                "movie_duration_units": info.movie_duration_units,
                "major_brand": info.major_brand,
                "compatible_brands": list(info.compatible_brands),
                "video_track_count": info.video_track_count,
                "audio_track_count": info.audio_track_count,
                "av_timeline_relation": info.av_timeline_relation,
                "tracks": [track.as_dict() for track in info.tracks],
                "decision": decide(info),
            }
        )
        result["limitations"] = [
            "Container and declared-track metadata only; no sample payload was decoded.",
            "The pinned full-object SHA-256 was matched to HF linked-object headers, not recomputed from the bounded byte windows.",
            "No claim is made about audible content, speech, ambient sound, semantic modality roles, decode quality, or scientific suitability.",
        ]
    except TransferValidationError as exc:
        result["container_parse_status"] = "NOT_RELIABLY_INSPECTED"
        result["decision"] = DECISION_IDENTITY
        result["limitations"] = [str(exc)]
    except UnsupportedContainerError as exc:
        result["container_parse_status"] = "UNSUPPORTED_OR_INCOMPLETE"
        result["decision"] = DECISION_CONTAINER
        result["limitations"] = [str(exc)]
    except ContainerError as exc:
        result["container_parse_status"] = "MALFORMED_OR_UNPARSEABLE"
        result["decision"] = DECISION_CONTAINER
        result["limitations"] = [str(exc)]
    finally:
        candidate_records = client.records[first_record:]
        result["range_request_count"] = sum(
            record.method == "GET" for record in candidate_records
        )
        result["response_body_bytes"] = (
            client.budget.total_bytes - first_bytes
        )
        result["requests"] = [record.as_dict() for record in candidate_records]
        client.release_candidate_bytes(candidate.candidate_id)
    return result


def run_preflight(
    candidates: Sequence[Candidate],
    client: SafeHFRangeClient,
    *,
    window_bytes: int = DEFAULT_WINDOW_BYTES,
) -> dict[str, Any]:
    results = [
        run_candidate(candidate, client, window_bytes=window_bytes)
        for candidate in candidates
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "mode": "live_bounded_metadata_and_stream_headers",
        "candidate_count": len(results),
        "limits": {
            "per_request_body_bytes": client.budget.maximum_response_bytes,
            "aggregate_body_bytes": client.budget.maximum_total_bytes,
            "per_candidate_body_bytes": client.maximum_candidate_bytes,
            "per_candidate_range_request_count": (
                MAX_RANGE_REQUESTS_PER_CANDIDATE
            ),
            "initial_head_window_bytes": window_bytes,
            "initial_tail_window_bytes": window_bytes,
            "complete_object_range_prohibited": True,
            "full_media_persistence_prohibited": True,
        },
        "aggregate": {
            "request_count": len(client.records),
            "range_request_count": sum(
                record.method == "GET" for record in client.records
            ),
            "response_body_bytes": client.budget.total_bytes,
            "maximum_observed_response_bytes": (
                client.budget.maximum_observed_response
            ),
            "decision_counts": {
                decision: sum(
                    result["decision"] == decision for result in results
                )
                for decision in (
                    DECISION_GO,
                    DECISION_NO_AUDIO,
                    DECISION_DURATION,
                    DECISION_CONTAINER,
                    DECISION_IDENTITY,
                )
            },
        },
        "candidates": results,
        "global_limitations": [
            "This is a stream/container declaration preflight, not content verification.",
            "No media samples, audio, frames, thumbnails, or signed URLs are persisted.",
            "A GO decision does not authorize acquisition, decoding, annotation, redistribution, or scientific use.",
        ],
    }


def validate_plan_only(plan_path: Path, source_csv: Path) -> dict[str, Any]:
    plan, candidates = load_plan(plan_path)
    validate_source_csv(candidates, source_csv)
    return {
        "status": "PASS",
        "schema_version": plan.get("schema_version"),
        "candidate_count": len(candidates),
        "candidate_ids": [candidate.candidate_id for candidate in candidates],
        "exact_allowlist_match": True,
        "source_csv_identity_match": True,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=PLAN_PATH)
    parser.add_argument("--source-csv", type=Path, default=SOURCE_CSV_PATH)
    parser.add_argument("--output", type=Path, default=RESULT_PATH)
    parser.add_argument(
        "--proxy",
        action="append",
        default=[],
        help="Ordered explicit proxy route; repeat for failover.",
    )
    parser.add_argument(
        "--window-bytes", type=int, default=DEFAULT_WINDOW_BYTES
    )
    parser.add_argument(
        "--max-response-bytes",
        type=int,
        default=DEFAULT_MAX_RESPONSE_BYTES,
    )
    parser.add_argument(
        "--max-total-bytes", type=int, default=DEFAULT_MAX_TOTAL_BYTES
    )
    parser.add_argument(
        "--validate-plan-only",
        action="store_true",
        help="Validate the closed plan and CSV identities without network.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        plan, candidates = load_plan(args.plan)
        validate_source_csv(candidates, args.source_csv)
        if args.validate_plan_only:
            print(
                json.dumps(
                    validate_plan_only(args.plan, args.source_csv),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.max_response_bytes <= 0 or args.max_total_bytes <= 0:
            raise ConfigurationError("INVALID_TRANSFER_LIMIT")
        if args.max_response_bytes > DEFAULT_MAX_RESPONSE_BYTES:
            raise ConfigurationError("PER_REQUEST_LIMIT_MAY_NOT_BE_RAISED")
        if args.max_total_bytes > DEFAULT_MAX_TOTAL_BYTES:
            raise ConfigurationError("AGGREGATE_LIMIT_MAY_NOT_BE_RAISED")
        token = load_hf_token()
        if not token:
            raise ConfigurationError("HF_TOKEN_NOT_AVAILABLE")
        budget = Budget(
            maximum_response_bytes=args.max_response_bytes,
            maximum_total_bytes=args.max_total_bytes,
        )
        with SafeHFRangeClient(
            token, proxies=args.proxy, budget=budget
        ) as client:
            result = run_preflight(
                candidates, client, window_bytes=args.window_bytes
            )
        result["plan_schema_version"] = plan.get("schema_version")
        atomic_write_json(args.output, result)
        print(
            json.dumps(
                {
                    "status": "COMPLETE",
                    "output": str(args.output),
                    "candidate_count": len(candidates),
                    "response_body_bytes": budget.total_bytes,
                    "decision_counts": result["aggregate"][
                        "decision_counts"
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except PreflightError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(
            f"ERROR: INPUT_OR_OUTPUT_{type(exc).__name__.upper()}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
