#!/usr/bin/env python3
"""Fail-closed downloader for the ten audited LongVideoBench members.

The downloader never requests a complete archive object or archive part.  It
revalidates each target's tar header and then transfers only the frozen payload
interval in responses no larger than 8 MiB.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Protocol, Sequence, TextIO
from urllib.parse import quote, urljoin, urlsplit

try:
    import httpx
except ImportError:  # pragma: no cover - checked when execute mode starts
    httpx = None  # type: ignore[assignment]


REPOSITORY = "longvideobench/LongVideoBench"
REVISION = "60d1c89c1919a198b73be39c2babb213b29d6a5c"
BLOCK_SIZE = 512
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
EXPECTED_VIDEO_BYTES = 580_719_669
EXPECTED_SUBTITLE_BYTES = 409_387
EXPECTED_PAYLOAD_BYTES = 581_129_056
EXPECTED_HEADER_BYTES = 10 * BLOCK_SIZE
MAX_REDIRECTS = 8

VIDEO_CSV_REL = Path("data/acquisition_preflight/lvb_five_member_ranges.csv")
SUBTITLE_CSV_REL = Path("data/acquisition_preflight/lvb_subtitle_ranges.csv")
AUDIT_REL = Path("data/acquisition_preflight/lvb_live_index_audit.json")
PLAN_REL = Path("data/acquisition_plan/lvb01_exact_asset_plan.json")
AUTHORIZATION_REL = Path("data/access_review/lvb01_acquisition_authorization.json")
STAGING_REL = Path("data/restricted/lvb01")
VIDEO_DEST_REL = Path("raw/videos")
SUBTITLE_DEST_REL = Path("raw/subtitles")
MANIFEST_DEST_REL = Path("manifests/lvb01_acquisition_manifest.json")
LOCK_DEST_REL = Path("manifests/.lvb_exact_asset_downloader.lock")

VIDEO_ALLOWLIST = (
    "-PgbM2MhcYQ.mp4",
    "-eRimFrm6kQ.mp4",
    "-7wwfGJXEZg.mp4",
    "H5vpBCLo74U.mp4",
    "TMe7oXMJoSM.mp4",
)
SUBTITLE_ALLOWLIST = (
    "-PgbM2MhcYQ_en.json",
    "-eRimFrm6kQ_en.json",
    "-7wwfGJXEZg_en.json",
    "H5vpBCLo74U_en.json",
    "TMe7oXMJoSM_en.json",
)
ALLOWLIST = VIDEO_ALLOWLIST + SUBTITLE_ALLOWLIST

ALLOWED_REDIRECT_HOST_SUFFIXES = (
    "huggingface.co",
    ".huggingface.co",
    ".hf.co",
    ".xethub.hf.co",
)
REDIRECT_CODES = {301, 302, 303, 307, 308}
SIGNED_URL_REFRESH_STATUSES = {400, 401, 403}
CONTENT_RANGE_RE = re.compile(r"^bytes (\d+)-(\d+)/(\d+)$")


class DownloaderError(RuntimeError):
    """Credential-free, fixed-code downloader failure."""


class ConfigurationError(DownloaderError):
    pass


class SafetyError(DownloaderError):
    pass


class TarHeaderError(DownloaderError):
    pass


class ContentValidationError(DownloaderError):
    pass


@dataclass
class WireBudget:
    maximum_response_bytes: int = MAX_RESPONSE_BYTES
    maximum_total_bytes: int = EXPECTED_PAYLOAD_BYTES + EXPECTED_HEADER_BYTES
    total_bytes: int = 0
    maximum_observed: int = 0

    def preflight(self, count: int) -> None:
        if count < 0:
            raise SafetyError("NEGATIVE_RESPONSE_SIZE")
        if count > self.maximum_response_bytes:
            raise SafetyError("RESPONSE_BODY_LIMIT_EXCEEDED")
        if self.total_bytes + count > self.maximum_total_bytes:
            raise SafetyError("WIRE_TRANSFER_BUDGET_EXCEEDED")

    def account(self, count: int) -> None:
        self.preflight(count)
        self.total_bytes += count
        self.maximum_observed = max(self.maximum_observed, count)


class RangeFetcher(Protocol):
    def fetch_range(
        self,
        filename: str,
        start: int,
        end: int,
        expected_object_size: int,
        purpose: str,
    ) -> bytes: ...


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> tuple[int, str]:
    digest = hashlib.sha256()
    count = 0
    with path.open("rb") as handle:
        while True:
            block = handle.read(chunk_size)
            if not block:
                break
            count += len(block)
            digest.update(block)
    return count, digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ConfigurationError(f"INVALID_JSON_{path.name.upper().replace('.', '_')}") from None


def parse_bool(value: str, error: str) -> bool:
    if value == "true":
        return True
    if value == "false":
        return False
    raise ConfigurationError(error)


def parse_int(value: Any, error: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise ConfigurationError(error) from None
    if result < 0:
        raise ConfigurationError(error)
    return result


def read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    except (OSError, UnicodeError, csv.Error):
        raise ConfigurationError(f"INVALID_CSV_{path.name.upper().replace('.', '_')}") from None
    if not rows:
        raise ConfigurationError("EMPTY_AUDITED_RANGE_CSV")
    return rows


def _exact_input_integrity(repo_root: Path, audit: Mapping[str, Any], relative: Path) -> dict[str, Any]:
    path = repo_root / relative
    raw = path.read_bytes()
    actual = {"bytes": len(raw), "sha256": sha256_bytes(raw)}
    expected = audit.get("offline_audit", {}).get("input_integrity", {}).get(relative.as_posix())
    if expected != actual:
        raise ConfigurationError("AUDITED_INPUT_INTEGRITY_MISMATCH")
    return actual


def _parse_single_range(raw: str) -> dict[str, Any]:
    try:
        ranges = json.loads(raw)
    except json.JSONDecodeError:
        raise ConfigurationError("INVALID_PART_RANGES_JSON") from None
    if not isinstance(ranges, list) or len(ranges) != 1 or not isinstance(ranges[0], dict):
        raise ConfigurationError("TARGET_MUST_HAVE_ONE_AUDITED_SOURCE_INTERVAL")
    item = ranges[0]
    start = parse_int(item.get("part_start", item.get("global_start")), "INVALID_RANGE_START")
    end = parse_int(item.get("part_end_inclusive", item.get("global_end_inclusive")), "INVALID_RANGE_END")
    length = parse_int(item.get("length"), "INVALID_RANGE_LENGTH")
    if end < start or end - start + 1 != length:
        raise ConfigurationError("AUDITED_RANGE_LENGTH_MISMATCH")
    if item.get("http_range") != f"bytes={start}-{end}":
        raise ConfigurationError("AUDITED_HTTP_RANGE_MISMATCH")
    return {"start": start, "end_inclusive": end, "length": length}


def _audit_archive_objects(audit: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    geometry = audit.get("offline_audit", {}).get("archive_geometry", {})
    result: dict[str, dict[str, Any]] = {}
    for part in geometry.get("video_parts", []):
        result[str(part["name"])] = {
            "size": parse_int(part["size"], "INVALID_AUDIT_PART_SIZE"),
            "sha256": str(part["lfs_sha256"]),
        }
    subtitles = geometry.get("subtitles_tar", {})
    result["subtitles.tar"] = {
        "size": parse_int(subtitles.get("size"), "INVALID_AUDIT_SUBTITLE_SIZE"),
        "sha256": str(subtitles.get("lfs_sha256")),
    }
    return result


def derive_frozen_plan(repo_root: Path) -> dict[str, Any]:
    """Derive the complete deterministic plan from the two audited range CSVs."""
    audit_path = repo_root / AUDIT_REL
    audit = load_json(audit_path)
    if audit.get("repository") != REPOSITORY or audit.get("pinned_revision") != REVISION:
        raise ConfigurationError("AUDIT_REPOSITORY_OR_REVISION_MISMATCH")
    if (
        audit.get("offline_audit", {}).get("status") != "PASS"
        or audit.get("live_spot_check", {}).get("status") != "PASS"
        or audit.get("target_media_acquisition_decision") != "PASS_INDEPENDENT_AUDIT"
    ):
        raise ConfigurationError("INDEPENDENT_AUDIT_NOT_PASS")

    video_integrity = _exact_input_integrity(repo_root, audit, VIDEO_CSV_REL)
    subtitle_integrity = _exact_input_integrity(repo_root, audit, SUBTITLE_CSV_REL)
    archive_objects = _audit_archive_objects(audit)
    video_rows = read_csv(repo_root / VIDEO_CSV_REL)
    subtitle_rows = read_csv(repo_root / SUBTITLE_CSV_REL)
    if len(video_rows) != 5 or len(subtitle_rows) != 5:
        raise ConfigurationError("EXACTLY_FIVE_ROWS_PER_MEDIA_CLASS_REQUIRED")

    targets: list[dict[str, Any]] = []
    observed: list[str] = []
    for kind, rows, allowlist in (
        ("video", video_rows, VIDEO_ALLOWLIST),
        ("subtitle", subtitle_rows, SUBTITLE_ALLOWLIST),
    ):
        by_basename: dict[str, dict[str, str]] = {}
        for row in rows:
            basename = PurePosixPath(row.get("member_path", "")).name
            if basename in by_basename:
                raise ConfigurationError("DUPLICATE_AUDITED_BASENAME")
            by_basename[basename] = row
        if set(by_basename) != set(allowlist):
            raise ConfigurationError("AUDITED_ALLOWLIST_MISMATCH")

        for basename in allowlist:
            row = by_basename[basename]
            member_path = row["member_path"]
            expected_prefix = "videos/" if kind == "video" else "subtitles/"
            if member_path != expected_prefix + basename:
                raise ConfigurationError("AUDITED_MEMBER_PATH_MISMATCH")
            if row.get("header_checksum_status") != "VALID":
                raise ConfigurationError("AUDITED_HEADER_CHECKSUM_NOT_VALID")
            if not parse_bool(row.get("range_extraction_feasible", ""), "INVALID_RANGE_FEASIBILITY"):
                raise ConfigurationError("AUDITED_RANGE_NOT_FEASIBLE")
            if row.get("status") != "LOCATED_HEADER_ONLY":
                raise ConfigurationError("AUDITED_RANGE_STATUS_MISMATCH")

            payload = _parse_single_range(row["part_ranges_json"])
            size = parse_int(row["member_size"], "INVALID_MEMBER_SIZE")
            if payload["length"] != size:
                raise ConfigurationError("MEMBER_AND_RANGE_SIZE_MISMATCH")

            if kind == "video":
                source_object = row["first_part"]
                if source_object != row["last_part"]:
                    raise ConfigurationError("MULTI_OBJECT_TARGET_NOT_AUTHORIZED")
                global_header = parse_int(row["tar_header_global_offset"], "INVALID_HEADER_OFFSET")
                global_data = parse_int(row["tar_data_global_offset"], "INVALID_DATA_OFFSET")
                global_end = parse_int(row["tar_end_global_offset"], "INVALID_END_OFFSET")
                if global_data != global_header + BLOCK_SIZE or global_end != global_data + size:
                    raise ConfigurationError("AUDITED_GLOBAL_GEOMETRY_MISMATCH")
                range_json = json.loads(row["part_ranges_json"])[0]
                global_range_start = parse_int(range_json["global_start"], "INVALID_GLOBAL_RANGE")
                if global_range_start != global_data:
                    raise ConfigurationError("AUDITED_GLOBAL_DATA_RANGE_MISMATCH")
                header_start = payload["start"] - BLOCK_SIZE
            else:
                source_object = row["requested_archive"]
                header_start = parse_int(row["tar_header_offset"], "INVALID_HEADER_OFFSET")
                data_start = parse_int(row["tar_data_offset"], "INVALID_DATA_OFFSET")
                end_offset = parse_int(row["tar_end_offset"], "INVALID_END_OFFSET")
                if data_start != header_start + BLOCK_SIZE or end_offset != data_start + size:
                    raise ConfigurationError("AUDITED_SUBTITLE_GEOMETRY_MISMATCH")
                if payload["start"] != data_start:
                    raise ConfigurationError("AUDITED_SUBTITLE_DATA_RANGE_MISMATCH")

            if source_object not in archive_objects:
                raise ConfigurationError("SOURCE_OBJECT_NOT_IN_AUDIT")
            object_info = archive_objects[source_object]
            object_size = object_info["size"]
            if header_start < 0 or payload["end_inclusive"] >= object_size:
                raise ConfigurationError("AUDITED_INTERVAL_OUTSIDE_SOURCE_OBJECT")
            if header_start + BLOCK_SIZE != payload["start"]:
                raise ConfigurationError("HEADER_DATA_OFFSET_MISMATCH")
            if header_start == 0 and payload["end_inclusive"] == object_size - 1:
                raise ConfigurationError("COMPLETE_SOURCE_OBJECT_TARGET_PROHIBITED")

            destination = (
                (VIDEO_DEST_REL if kind == "video" else SUBTITLE_DEST_REL) / basename
            ).as_posix()
            targets.append(
                {
                    "kind": kind,
                    "candidate_id": row["candidate_id"],
                    "video_id": row["video_id"],
                    "basename": basename,
                    "member_path": member_path,
                    "size": size,
                    "destination": destination,
                    "source_object": source_object,
                    "source_object_size": object_size,
                    "source_object_lfs_sha256": object_info["sha256"],
                    "header_range": {
                        "start": header_start,
                        "end_inclusive": header_start + BLOCK_SIZE - 1,
                        "length": BLOCK_SIZE,
                    },
                    "payload_intervals": [payload],
                }
            )
            observed.append(basename)

    video_total = sum(target["size"] for target in targets if target["kind"] == "video")
    subtitle_total = sum(target["size"] for target in targets if target["kind"] == "subtitle")
    total = video_total + subtitle_total
    if (
        tuple(observed) != ALLOWLIST
        or video_total != EXPECTED_VIDEO_BYTES
        or subtitle_total != EXPECTED_SUBTITLE_BYTES
        or total != EXPECTED_PAYLOAD_BYTES
    ):
        raise ConfigurationError("FROZEN_EXPECTED_TOTAL_MISMATCH")

    return {
        "schema_version": "1.0",
        "plan_id": "LVB-01-EXACT-FIVE-ASSET-ACQUISITION",
        "repository": REPOSITORY,
        "pinned_revision": REVISION,
        "audit": {
            "path": AUDIT_REL.as_posix(),
            "sha256": sha256_bytes(audit_path.read_bytes()),
            "offline_status": "PASS",
            "live_status": "PASS",
            "decision": "PASS_INDEPENDENT_AUDIT",
            "live_audit_bytes": audit["live_spot_check"]["response_body_bytes"],
        },
        "audited_range_inputs": {
            VIDEO_CSV_REL.as_posix(): video_integrity,
            SUBTITLE_CSV_REL.as_posix(): subtitle_integrity,
        },
        "allowlist": list(ALLOWLIST),
        "limits": {
            "maximum_response_body_bytes": MAX_RESPONSE_BYTES,
            "chunk_bytes": MAX_RESPONSE_BYTES,
            "expected_video_payload_bytes": EXPECTED_VIDEO_BYTES,
            "expected_subtitle_payload_bytes": EXPECTED_SUBTITLE_BYTES,
            "expected_total_payload_bytes": EXPECTED_PAYLOAD_BYTES,
            "expected_header_validation_bytes": EXPECTED_HEADER_BYTES,
            "complete_archive_or_part_requests_prohibited": True,
        },
        "staging_root": STAGING_REL.as_posix(),
        "targets": targets,
    }


def validate_frozen_plan(repo_root: Path) -> tuple[dict[str, Any], str]:
    path = repo_root / PLAN_REL
    raw = path.read_bytes()
    persisted = load_json(path)
    expected = derive_frozen_plan(repo_root)
    if persisted != expected or raw != canonical_json_bytes(expected):
        raise ConfigurationError("FROZEN_PLAN_DOES_NOT_MATCH_AUDITED_RANGES")
    return expected, sha256_bytes(raw)


def validate_authorization(repo_root: Path, plan: Mapping[str, Any], plan_sha256: str) -> dict[str, Any]:
    authorization = load_json(repo_root / AUTHORIZATION_REL)
    scope = authorization.get("authorized_scope", {})
    audit = authorization.get("independent_audit", {})
    if authorization.get("authorization_status") != "AUTHORIZED_EXACT_FIVE_ASSET_ACQUISITION":
        raise ConfigurationError("ACQUISITION_NOT_AUTHORIZED")
    if scope.get("repository") != REPOSITORY or scope.get("pinned_revision") != REVISION:
        raise ConfigurationError("AUTHORIZATION_REPOSITORY_OR_REVISION_MISMATCH")
    if scope.get("allowlist") != list(ALLOWLIST):
        raise ConfigurationError("AUTHORIZATION_ALLOWLIST_MISMATCH")
    if scope.get("expected_total_payload_bytes") != EXPECTED_PAYLOAD_BYTES:
        raise ConfigurationError("AUTHORIZATION_TRANSFER_BUDGET_MISMATCH")
    if scope.get("plan_sha256") != plan_sha256:
        raise ConfigurationError("AUTHORIZATION_PLAN_HASH_MISMATCH")
    if (
        audit.get("offline_status") != "PASS"
        or audit.get("live_status") != "PASS"
        or audit.get("decision") != "PASS_INDEPENDENT_AUDIT"
    ):
        raise ConfigurationError("AUTHORIZATION_AUDIT_MISMATCH")
    prohibited = authorization.get("not_authorized", {})
    if not (
        prohibited.get("full_archive_download")
        and prohibited.get("complete_tar_part_download")
        and prohibited.get("arbitrary_tar_extraction")
        and prohibited.get("benchmark_annotation")
    ):
        raise ConfigurationError("AUTHORIZATION_PROHIBITIONS_INCOMPLETE")
    if plan["allowlist"] != scope["allowlist"]:
        raise ConfigurationError("PLAN_AUTHORIZATION_SCOPE_MISMATCH")
    return authorization


def host_allowed(host: str) -> bool:
    normalized = host.lower().rstrip(".")
    return any(
        normalized == suffix.lstrip(".") or (suffix.startswith(".") and normalized.endswith(suffix))
        for suffix in ALLOWED_REDIRECT_HOST_SUFFIXES
    )


def canonical_url(filename: str) -> str:
    if not filename or filename != PurePosixPath(filename).name:
        raise ConfigurationError("INVALID_REPOSITORY_OBJECT_NAME")
    return (
        "https://huggingface.co/datasets/"
        f"{REPOSITORY}/resolve/{REVISION}/{quote(filename, safe='')}"
    )


class SafeRangeClient:
    """Persistent strict Range client with process-local signed URL caching."""

    def __init__(self, token: str, *, client: Any | None = None, budget: WireBudget | None = None) -> None:
        if not token:
            raise ConfigurationError("HF_TOKEN_NOT_AVAILABLE")
        if httpx is None:
            raise ConfigurationError("HTTPX_NOT_INSTALLED")
        self._token = token
        self._owns_client = client is None
        self._client = client or httpx.Client(
            follow_redirects=False,
            trust_env=True,
            timeout=httpx.Timeout(120.0, connect=30.0),
            headers={"User-Agent": "AV-TRACE-lvb-exact-asset-downloader/1.0"},
        )
        self.budget = budget or WireBudget()
        self._effective_url_cache: dict[tuple[str, int], str] = {}

    def close(self) -> None:
        self._token = ""
        self._effective_url_cache.clear()
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "SafeRangeClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def _origin(parsed: Any) -> tuple[str, str, int]:
        return parsed.scheme.lower(), (parsed.hostname or "").lower().rstrip("."), parsed.port or 443

    def _validate_url(self, url: str) -> Any:
        parsed = urlsplit(url)
        if parsed.scheme.lower() != "https":
            raise SafetyError("NON_HTTPS_REQUEST_OR_REDIRECT")
        if parsed.username is not None or parsed.password is not None:
            raise SafetyError("URL_USERINFO_PROHIBITED")
        try:
            port = parsed.port
        except ValueError:
            raise SafetyError("INVALID_URL_PORT") from None
        if not parsed.hostname or not host_allowed(parsed.hostname):
            raise SafetyError("REDIRECT_HOST_NOT_ALLOWED")
        if port is not None and not 1 <= port <= 65535:
            raise SafetyError("INVALID_URL_PORT")
        return parsed

    def fetch_range(
        self,
        filename: str,
        start: int,
        end: int,
        expected_object_size: int,
        purpose: str,
    ) -> bytes:
        del purpose  # Never persisted or sent; retained for testable call intent.
        if start < 0 or end < start or end >= expected_object_size:
            raise SafetyError("RANGE_OUTSIDE_FROZEN_SOURCE_OBJECT")
        expected_body = end - start + 1
        if expected_body > MAX_RESPONSE_BYTES:
            raise SafetyError("REQUEST_EXCEEDS_8_MIB")
        if start == 0 and end == expected_object_size - 1:
            raise SafetyError("COMPLETE_ARCHIVE_OBJECT_OR_PART_REQUEST_PROHIBITED")
        self.budget.preflight(expected_body)

        initial_url = canonical_url(filename)
        canonical_origin = self._origin(self._validate_url(initial_url))
        cache_key = (initial_url, expected_object_size)
        cached = self._effective_url_cache.get(cache_key)
        url = cached or initial_url
        using_cached = cached is not None
        canonical_resolution = not using_cached
        refreshed = False
        redirects = 0
        requested_range = f"bytes={start}-{end}"
        try:
            while True:
                parsed = self._validate_url(url)
                headers = {"Range": requested_range, "Accept-Encoding": "identity"}
                if canonical_resolution and self._origin(parsed) == canonical_origin:
                    headers["Authorization"] = f"Bearer {self._token}"
                with self._client.stream("GET", url, headers=headers) as response:
                    if response.status_code in REDIRECT_CODES:
                        location = response.headers.get("location")
                        if not location:
                            raise SafetyError("REDIRECT_WITHOUT_LOCATION")
                        next_url = urljoin(url, location)
                        next_parsed = self._validate_url(next_url)
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
                    if using_cached and not refreshed and response.status_code in SIGNED_URL_REFRESH_STATUSES:
                        self._effective_url_cache.pop(cache_key, None)
                        using_cached = False
                        refreshed = True
                        canonical_resolution = True
                        url = initial_url
                        continue
                    if response.status_code == 200:
                        raise SafetyError("RANGE_IGNORED_FULL_OBJECT_200")
                    if response.status_code != 206:
                        raise SafetyError("UNEXPECTED_RANGE_STATUS")
                    content_encoding = response.headers.get("content-encoding", "identity").lower()
                    if content_encoding != "identity":
                        raise SafetyError("UNEXPECTED_RANGE_CONTENT_ENCODING")
                    content_length = response.headers.get("content-length")
                    if content_length is None or not content_length.isdigit():
                        raise SafetyError("MISSING_OR_INVALID_CONTENT_LENGTH")
                    if int(content_length) != expected_body:
                        raise SafetyError("MISMATCHED_CONTENT_LENGTH")
                    content_range = response.headers.get("content-range", "")
                    match = CONTENT_RANGE_RE.fullmatch(content_range.strip())
                    if not match:
                        raise SafetyError("INVALID_CONTENT_RANGE")
                    actual = tuple(int(group) for group in match.groups())
                    if actual != (start, end, expected_object_size):
                        raise SafetyError("MISMATCHED_CONTENT_RANGE")

                    body = bytearray()
                    for block in response.iter_bytes():
                        if len(body) + len(block) > expected_body:
                            raise SafetyError("RANGE_RESPONSE_EXCESS_BYTES")
                        body.extend(block)
                    if len(body) != expected_body:
                        raise SafetyError("RANGE_RESPONSE_TRUNCATED")
                    self.budget.account(len(body))
                    if self._origin(parsed) == canonical_origin:
                        self._effective_url_cache.pop(cache_key, None)
                    else:
                        self._effective_url_cache[cache_key] = url
                    return bytes(body)
        except DownloaderError:
            raise
        except Exception as exc:
            raise DownloaderError(f"HTTP_TRANSPORT_{type(exc).__name__.upper()}") from None


def _parse_tar_octal(field: bytes, error: str) -> int:
    if field and field[0] & 0x80:
        raise TarHeaderError("BASE256_TAR_NUMBER_NOT_AUTHORIZED")
    cleaned = field.rstrip(b"\0 ").lstrip(b" ")
    if not cleaned:
        return 0
    if any(byte not in b"01234567" for byte in cleaned):
        raise TarHeaderError(error)
    return int(cleaned, 8)


def validate_tar_header(header: bytes, target: Mapping[str, Any]) -> dict[str, Any]:
    if len(header) != BLOCK_SIZE:
        raise TarHeaderError("TAR_HEADER_NOT_512_BYTES")
    if header == b"\0" * BLOCK_SIZE:
        raise TarHeaderError("UNEXPECTED_TAR_END_MARKER")
    stored = _parse_tar_octal(header[148:156], "INVALID_TAR_CHECKSUM_FIELD")
    checksum_header = bytearray(header)
    checksum_header[148:156] = b" " * 8
    unsigned = sum(checksum_header)
    signed = sum(byte if byte < 128 else byte - 256 for byte in checksum_header)
    if stored not in (unsigned, signed):
        raise TarHeaderError("TAR_CHECKSUM_MISMATCH")

    try:
        name = header[0:100].split(b"\0", 1)[0].decode("utf-8", "strict")
        prefix = header[345:500].split(b"\0", 1)[0].decode("utf-8", "strict")
    except UnicodeDecodeError:
        raise TarHeaderError("TAR_PATH_NOT_UTF8") from None
    path = f"{prefix}/{name}" if prefix else name
    if path != target["member_path"]:
        raise TarHeaderError("TAR_MEMBER_PATH_MISMATCH")
    if PurePosixPath(path).name != target["basename"]:
        raise TarHeaderError("TAR_MEMBER_BASENAME_MISMATCH")
    typeflag_byte = header[156:157]
    if typeflag_byte not in (b"\0", b"0"):
        raise TarHeaderError("TAR_MEMBER_NOT_REGULAR_FILE")
    declared_size = _parse_tar_octal(header[124:136], "INVALID_TAR_SIZE_FIELD")
    if declared_size != target["size"]:
        raise TarHeaderError("TAR_DECLARED_SIZE_MISMATCH")
    header_range = target["header_range"]
    payload = target["payload_intervals"][0]
    if (
        header_range["length"] != BLOCK_SIZE
        or header_range["end_inclusive"] - header_range["start"] + 1 != BLOCK_SIZE
        or header_range["start"] + BLOCK_SIZE != payload["start"]
    ):
        raise TarHeaderError("TAR_DATA_OFFSET_MISMATCH")
    return {
        "path": path,
        "basename": PurePosixPath(path).name,
        "typeflag": "0" if typeflag_byte == b"0" else "NUL",
        "declared_size": declared_size,
        "checksum_valid": True,
        "header_sha256": sha256_bytes(header),
        "data_offset": payload["start"],
    }


def validate_mp4(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        prefix = handle.read(4096)
    if len(prefix) < 16:
        raise ContentValidationError("MP4_PREFIX_TOO_SHORT")
    box_size = int.from_bytes(prefix[0:4], "big")
    box_type = prefix[4:8]
    if box_type != b"ftyp" or box_size < 16 or box_size > len(prefix) or box_size % 4:
        raise ContentValidationError("MP4_FTYP_PREFIX_INVALID")
    major_brand = prefix[8:12]
    compatible = [prefix[index : index + 4] for index in range(16, box_size, 4)]
    if not all(len(brand) == 4 and all(32 <= byte <= 126 for byte in brand) for brand in [major_brand, *compatible]):
        raise ContentValidationError("MP4_BRAND_BYTES_INVALID")
    return {
        "compatible": True,
        "first_box_type": "ftyp",
        "first_box_size": box_size,
        "major_brand": major_brand.decode("ascii"),
        "compatible_brands": [brand.decode("ascii") for brand in compatible],
    }


def validate_subtitle_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ContentValidationError("SUBTITLE_NOT_UTF8") from None
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        raise ContentValidationError("SUBTITLE_INVALID_JSON") from None
    summary: dict[str, Any] = {"encoding": "utf-8-bom" if bom else "utf-8"}
    if isinstance(value, list):
        summary.update({"top_level_type": "array", "item_count": len(value)})
        if value:
            summary["first_item_type"] = type(value[0]).__name__
            if isinstance(value[0], dict):
                summary["first_item_keys"] = sorted(str(key) for key in value[0].keys())
    elif isinstance(value, dict):
        summary.update({"top_level_type": "object", "top_level_keys": sorted(str(key) for key in value)})
    else:
        summary["top_level_type"] = type(value).__name__
    return summary


def ffprobe_summary(path: Path) -> dict[str, Any]:
    executable = shutil.which("ffprobe")
    if not executable:
        return {"available": False, "invoked": False}
    command = [
        executable,
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-of",
        "json",
        str(path),
    ]
    try:
        result = subprocess.run(command, capture_output=True, timeout=120, check=False)
    except subprocess.TimeoutExpired:
        return {"available": True, "invoked": True, "error": "FFPROBE_TIMEOUT"}
    except OSError:
        return {"available": True, "invoked": True, "error": "FFPROBE_EXECUTION_ERROR"}
    if result.returncode != 0:
        return {
            "available": True,
            "invoked": True,
            "error": f"FFPROBE_EXIT_{result.returncode}",
        }
    try:
        parsed = json.loads(result.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"available": True, "invoked": True, "error": "FFPROBE_INVALID_JSON"}
    format_info = parsed.get("format", {})
    streams = []
    for stream in parsed.get("streams", []):
        streams.append(
            {
                key: stream[key]
                for key in (
                    "index",
                    "codec_name",
                    "codec_type",
                    "width",
                    "height",
                    "sample_rate",
                    "channels",
                    "duration",
                )
                if key in stream
            }
        )
    return {
        "available": True,
        "invoked": True,
        "format_name": format_info.get("format_name"),
        "duration": format_info.get("duration"),
        "streams": streams,
        "errors": [],
    }


def ensure_restricted_directory(path: Path) -> None:
    if path.exists():
        if path.is_symlink() or not path.is_dir():
            raise SafetyError("STAGING_PATH_NOT_SAFE_DIRECTORY")
    else:
        path.mkdir(mode=0o700, parents=True, exist_ok=False)
    path.chmod(0o700)


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write_json(path: Path, value: Any, *, replace: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = canonical_json_bytes(value)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if not replace and path.exists():
            raise SafetyError("REFUSING_TO_OVERWRITE_EXISTING_METADATA")
        os.replace(temporary, path)
        fsync_directory(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def _safe_existing(path: Path) -> bool:
    if path.is_symlink():
        raise SafetyError("SYMLINK_IN_STAGING_PROHIBITED")
    return path.exists()


def _target_binding(target: Mapping[str, Any], plan_sha256: str, chunk_bytes: int) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "repository": REPOSITORY,
        "pinned_revision": REVISION,
        "plan_sha256": plan_sha256,
        "basename": target["basename"],
        "member_path": target["member_path"],
        "kind": target["kind"],
        "size": target["size"],
        "source_object": target["source_object"],
        "source_object_size": target["source_object_size"],
        "header_range": target["header_range"],
        "payload_intervals": target["payload_intervals"],
        "chunk_bytes": chunk_bytes,
    }


def _completed_static_metadata(
    target: Mapping[str, Any], plan_sha256: str, chunk_bytes: int
) -> dict[str, Any]:
    binding = _target_binding(target, plan_sha256, chunk_bytes)
    binding.pop("chunk_bytes")
    return binding


class Acquirer:
    def __init__(
        self,
        repo_root: Path,
        plan: Mapping[str, Any],
        plan_sha256: str,
        fetcher: RangeFetcher,
        *,
        progress_stream: TextIO | None = None,
        chunk_bytes: int | None = None,
        ffprobe: Callable[[Path], dict[str, Any]] = ffprobe_summary,
    ) -> None:
        self.repo_root = repo_root
        self.plan = plan
        self.plan_sha256 = plan_sha256
        self.fetcher = fetcher
        self.progress_stream = progress_stream or sys.stderr
        self.chunk_bytes = chunk_bytes or int(plan["limits"]["chunk_bytes"])
        if self.chunk_bytes <= 0 or self.chunk_bytes > MAX_RESPONSE_BYTES:
            raise ConfigurationError("INVALID_CHUNK_SIZE")
        self.ffprobe = ffprobe
        self.staging_root = repo_root / str(plan["staging_root"])
        self.payload_bytes_received = 0

    def _paths(self, target: Mapping[str, Any]) -> tuple[Path, Path, Path, Path]:
        destination = self.staging_root / str(target["destination"])
        expected_parent = self.staging_root / (
            VIDEO_DEST_REL if target["kind"] == "video" else SUBTITLE_DEST_REL
        )
        if destination.parent != expected_parent or destination.name != target["basename"]:
            raise SafetyError("DESTINATION_NOT_EXACT_ALLOWLIST_PATH")
        return (
            destination,
            destination.with_name(destination.name + ".partial"),
            destination.with_name(destination.name + ".partial.json"),
            destination.with_name(destination.name + ".metadata.json"),
        )

    def _verify_completed(
        self, target: Mapping[str, Any], destination: Path, metadata_path: Path
    ) -> dict[str, Any]:
        if not _safe_existing(metadata_path):
            raise SafetyError("EXISTING_TARGET_WITHOUT_METADATA")
        metadata = load_json(metadata_path)
        expected_static = _completed_static_metadata(target, self.plan_sha256, self.chunk_bytes)
        if any(metadata.get(key) != value for key, value in expected_static.items()):
            raise SafetyError("COMPLETED_METADATA_BINDING_MISMATCH")
        size, digest = sha256_file(destination)
        if size != target["size"] or metadata.get("size") != size or metadata.get("sha256") != digest:
            raise SafetyError("COMPLETED_TARGET_SIZE_OR_HASH_MISMATCH")
        return {"status": "skipped_verified", "size": size, "sha256": digest, "metadata": metadata}

    def _load_or_create_partial(
        self, target: Mapping[str, Any], partial: Path, state_path: Path
    ) -> tuple[int, hashlib._Hash]:
        partial_exists = _safe_existing(partial)
        state_exists = _safe_existing(state_path)
        binding = _target_binding(target, self.plan_sha256, self.chunk_bytes)
        if partial_exists != state_exists:
            raise SafetyError("PARTIAL_AND_STATE_MUST_EXIST_TOGETHER")
        if not partial_exists:
            descriptor = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(descriptor)
            initial = dict(binding)
            initial.update({"completed_bytes": 0, "prefix_sha256": hashlib.sha256().hexdigest()})
            atomic_write_json(state_path, initial, replace=False)
            return 0, hashlib.sha256()

        state = load_json(state_path)
        if any(state.get(key) != value for key, value in binding.items()):
            raise SafetyError("PARTIAL_STATE_BINDING_MISMATCH")
        size, digest = sha256_file(partial)
        if size > target["size"]:
            raise SafetyError("PARTIAL_LARGER_THAN_TARGET")
        if size != target["size"] and size % self.chunk_bytes != 0:
            raise SafetyError("PARTIAL_NOT_ON_EXACT_CHUNK_BOUNDARY")
        if state.get("completed_bytes") != size or state.get("prefix_sha256") != digest:
            raise SafetyError("PARTIAL_STATE_SIZE_OR_HASH_MISMATCH")
        hasher = hashlib.sha256()
        with partial.open("rb") as handle:
            while block := handle.read(1024 * 1024):
                hasher.update(block)
        return size, hasher

    def _validate_header(self, target: Mapping[str, Any]) -> dict[str, Any]:
        header_range = target["header_range"]
        if (
            header_range["length"] != BLOCK_SIZE
            or header_range["end_inclusive"] - header_range["start"] + 1 != BLOCK_SIZE
        ):
            raise SafetyError("FROZEN_HEADER_RANGE_INVALID")
        header = self.fetcher.fetch_range(
            target["source_object"],
            header_range["start"],
            header_range["end_inclusive"],
            target["source_object_size"],
            f"tar-header:{target['basename']}",
        )
        return validate_tar_header(header, target)

    def _source_range_for_chunk(self, target: Mapping[str, Any], offset: int) -> tuple[int, int]:
        intervals = target["payload_intervals"]
        if len(intervals) != 1:
            raise SafetyError("ONLY_FROZEN_SINGLE_INTERVAL_TARGETS_SUPPORTED")
        interval = intervals[0]
        if interval["length"] != target["size"]:
            raise SafetyError("FROZEN_PAYLOAD_INTERVAL_SIZE_MISMATCH")
        remaining = target["size"] - offset
        length = min(self.chunk_bytes, remaining)
        start = interval["start"] + offset
        end = start + length - 1
        if start < interval["start"] or end > interval["end_inclusive"]:
            raise SafetyError("REQUEST_OUTSIDE_AUDITED_PAYLOAD_INTERVAL")
        if start == 0 and end == target["source_object_size"] - 1:
            raise SafetyError("COMPLETE_ARCHIVE_OBJECT_OR_PART_REQUEST_PROHIBITED")
        return start, end

    def acquire_target(self, target: Mapping[str, Any], index: int, total_targets: int) -> dict[str, Any]:
        if target["basename"] not in ALLOWLIST:
            raise SafetyError("UNLISTED_TARGET")
        destination, partial, state_path, metadata_path = self._paths(target)
        ensure_restricted_directory(destination.parent)
        for path in (destination, partial, state_path, metadata_path):
            if path.is_symlink():
                raise SafetyError("SYMLINK_IN_STAGING_PROHIBITED")
        if destination.exists():
            if partial.exists() or state_path.exists():
                raise SafetyError("COMPLETED_AND_PARTIAL_TARGET_CONFLICT")
            result = self._verify_completed(target, destination, metadata_path)
            print(
                f"[{index}/{total_targets}] verified existing {target['basename']} "
                f"bytes={target['size']}",
                file=self.progress_stream,
                flush=True,
            )
            return result
        if metadata_path.exists():
            raise SafetyError("METADATA_WITHOUT_COMPLETED_TARGET")

        completed, hasher = self._load_or_create_partial(target, partial, state_path)
        header_validation: dict[str, Any] | None = None
        if completed < target["size"]:
            print(
                f"[{index}/{total_targets}] validating header {target['basename']} "
                f"resume_bytes={completed}",
                file=self.progress_stream,
                flush=True,
            )
            header_validation = self._validate_header(target)
            binding = _target_binding(target, self.plan_sha256, self.chunk_bytes)
            with partial.open("r+b", buffering=0) as handle:
                handle.seek(completed)
                while completed < target["size"]:
                    start, end = self._source_range_for_chunk(target, completed)
                    body = self.fetcher.fetch_range(
                        target["source_object"],
                        start,
                        end,
                        target["source_object_size"],
                        f"payload:{target['basename']}",
                    )
                    expected = end - start + 1
                    if len(body) != expected:
                        raise SafetyError("FETCHER_RETURNED_UNEXPECTED_BYTE_COUNT")
                    if self.payload_bytes_received + len(body) > EXPECTED_PAYLOAD_BYTES:
                        raise SafetyError("AGGREGATE_TARGET_BYTES_ABOVE_FROZEN_TOTAL")
                    view = memoryview(body)
                    while view:
                        written = handle.write(view)
                        if not written:
                            raise SafetyError("PARTIAL_WRITE_FAILED")
                        view = view[written:]
                    handle.flush()
                    os.fsync(handle.fileno())
                    hasher.update(body)
                    completed += len(body)
                    self.payload_bytes_received += len(body)
                    state = dict(binding)
                    state.update({"completed_bytes": completed, "prefix_sha256": hasher.hexdigest()})
                    atomic_write_json(state_path, state)
                    print(
                        f"[{index}/{total_targets}] {target['basename']} "
                        f"bytes={completed}/{target['size']} "
                        f"run_payload_bytes={self.payload_bytes_received}/{EXPECTED_PAYLOAD_BYTES}",
                        file=self.progress_stream,
                        flush=True,
                    )

        size = partial.stat().st_size
        digest = hasher.hexdigest()
        if size != target["size"]:
            raise SafetyError("FINAL_PARTIAL_SIZE_MISMATCH")
        recomputed_size, recomputed_digest = sha256_file(partial)
        if recomputed_size != size or recomputed_digest != digest:
            raise SafetyError("FINAL_PARTIAL_HASH_RECOMPUTE_MISMATCH")
        if target["kind"] == "video":
            content_validation = validate_mp4(partial)
            probe = self.ffprobe(partial)
        else:
            content_validation = validate_subtitle_json(partial)
            probe = None

        with partial.open("rb") as handle:
            os.fsync(handle.fileno())
        metadata = _completed_static_metadata(target, self.plan_sha256, self.chunk_bytes)
        metadata.update(
            {
                "sha256": digest,
                "content_validation": content_validation,
                "ffprobe": probe,
                "tar_header_validation": header_validation,
                "completed_at_utc": utc_now(),
            }
        )
        metadata_temporary = metadata_path.with_name(metadata_path.name + ".partial")
        if metadata_temporary.exists():
            raise SafetyError("METADATA_TEMPORARY_ALREADY_EXISTS")
        atomic_write_json(metadata_temporary, metadata, replace=False)
        if destination.exists() or metadata_path.exists():
            raise SafetyError("REFUSING_TO_OVERWRITE_COMPLETED_TARGET")
        os.replace(partial, destination)
        fsync_directory(destination.parent)
        os.replace(metadata_temporary, metadata_path)
        fsync_directory(destination.parent)
        state_path.unlink()
        fsync_directory(destination.parent)
        return {"status": "downloaded", "size": size, "sha256": digest, "metadata": metadata}

    def run(self) -> dict[str, Any]:
        targets = list(self.plan["targets"])
        if [target["basename"] for target in targets] != list(ALLOWLIST):
            raise SafetyError("PLAN_TARGET_ORDER_OR_ALLOWLIST_MISMATCH")
        results = []
        for index, target in enumerate(targets, 1):
            results.append(self.acquire_target(target, index, len(targets)))
        verified_total = sum(result["size"] for result in results)
        if verified_total != EXPECTED_PAYLOAD_BYTES:
            raise SafetyError("VERIFIED_AGGREGATE_SIZE_MISMATCH")
        return {
            "schema_version": "1.0",
            "plan_id": self.plan["plan_id"],
            "plan_sha256": self.plan_sha256,
            "repository": REPOSITORY,
            "pinned_revision": REVISION,
            "completed_at_utc": utc_now(),
            "expected_total_payload_bytes": EXPECTED_PAYLOAD_BYTES,
            "verified_total_payload_bytes": verified_total,
            "payload_bytes_received_this_run": self.payload_bytes_received,
            "targets": [
                {
                    "basename": target["basename"],
                    "kind": target["kind"],
                    "size": result["size"],
                    "sha256": result["sha256"],
                    "status": result["status"],
                    "metadata_path": (
                        Path(target["destination"]).with_name(
                            Path(target["destination"]).name + ".metadata.json"
                        )
                    ).as_posix(),
                }
                for target, result in zip(targets, results, strict=True)
            ],
        }


def validate_local_configuration(repo_root: Path) -> tuple[dict[str, Any], str, dict[str, Any]]:
    plan, plan_sha256 = validate_frozen_plan(repo_root)
    authorization = validate_authorization(repo_root, plan, plan_sha256)
    return plan, plan_sha256, authorization


def dry_run(repo_root: Path) -> dict[str, Any]:
    plan, plan_sha256, _ = validate_local_configuration(repo_root)
    return {
        "mode": "dry-run",
        "repository": REPOSITORY,
        "pinned_revision": REVISION,
        "plan": PLAN_REL.as_posix(),
        "plan_sha256": plan_sha256,
        "authorization": AUTHORIZATION_REL.as_posix(),
        "target_count": len(plan["targets"]),
        "expected_video_payload_bytes": EXPECTED_VIDEO_BYTES,
        "expected_subtitle_payload_bytes": EXPECTED_SUBTITLE_BYTES,
        "expected_total_payload_bytes": EXPECTED_PAYLOAD_BYTES,
        "maximum_response_body_bytes": MAX_RESPONSE_BYTES,
        "network_attempted": False,
        "credentials_read": False,
        "outputs_written": False,
        "status": "READY_FOR_EXACT_ACQUISITION",
    }


def _acquire_lock(staging_root: Path) -> tuple[int, Path]:
    lock_path = staging_root / LOCK_DEST_REL
    ensure_restricted_directory(lock_path.parent)
    try:
        descriptor = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise SafetyError("ACQUISITION_LOCK_ALREADY_EXISTS") from None
    os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
    os.fsync(descriptor)
    return descriptor, lock_path


def run_execute(
    repo_root: Path,
    *,
    client_factory: Callable[[str], RangeFetcher] | None = None,
    progress_stream: TextIO | None = None,
) -> dict[str, Any]:
    plan, plan_sha256, _ = validate_local_configuration(repo_root)
    try:
        from huggingface_hub import get_token
    except ImportError:
        raise ConfigurationError("HUGGINGFACE_HUB_NOT_INSTALLED") from None
    token = get_token()
    if not token:
        raise ConfigurationError("HF_TOKEN_NOT_AVAILABLE")

    staging_root = repo_root / STAGING_REL
    ensure_restricted_directory(staging_root)
    ensure_restricted_directory(staging_root / VIDEO_DEST_REL)
    ensure_restricted_directory(staging_root / SUBTITLE_DEST_REL)
    ensure_restricted_directory((staging_root / MANIFEST_DEST_REL).parent)
    lock_fd, lock_path = _acquire_lock(staging_root)
    fetcher: RangeFetcher | None = None
    try:
        fetcher = client_factory(token) if client_factory else SafeRangeClient(token)
        result = Acquirer(
            repo_root,
            plan,
            plan_sha256,
            fetcher,
            progress_stream=progress_stream,
        ).run()
        if isinstance(fetcher, SafeRangeClient):
            result["wire_response_bytes_this_run"] = fetcher.budget.total_bytes
            result["maximum_response_body_observed"] = fetcher.budget.maximum_observed
        manifest_path = staging_root / MANIFEST_DEST_REL
        atomic_write_json(manifest_path, result)
        return {
            "mode": "execute",
            "status": "COMPLETE",
            "manifest": manifest_path.relative_to(repo_root).as_posix(),
            "expected_total_payload_bytes": EXPECTED_PAYLOAD_BYTES,
            "payload_bytes_received_this_run": result["payload_bytes_received_this_run"],
            "target_count": len(result["targets"]),
        }
    finally:
        token = None
        close = getattr(fetcher, "close", None) if fetcher is not None else None
        if callable(close):
            close()
        os.close(lock_fd)
        if lock_path.exists():
            lock_path.unlink()
            fsync_directory(lock_path.parent)


def find_repo_root(script_path: Path) -> Path:
    root = script_path.resolve().parents[1]
    if not (root / "pyproject.toml").is_file():
        raise ConfigurationError("REPOSITORY_ROOT_NOT_FOUND")
    return root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download exactly five audited LongVideoBench MP4s and five audited subtitle JSON files."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="validate frozen inputs without token, network, or writes")
    mode.add_argument("--execute", action="store_true", help="perform the authorized exact bounded acquisition")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        repo_root = find_repo_root(Path(__file__))
        result = dry_run(repo_root) if args.dry_run else run_execute(repo_root)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except DownloaderError as exc:
        print(f"lvb exact asset downloader failed: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # Never expose exception text that may include a signed URL.
        print(
            f"lvb exact asset downloader failed: INTERNAL_{type(exc).__name__.upper()}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
