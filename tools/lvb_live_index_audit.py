#!/usr/bin/env python3
"""Independent, fail-closed audit of the LongVideoBench live tar index.

The offline audit validates the persisted Task 58 evidence and recomputes all
reported geometry.  The optional live audit retrieves only ten 512-byte tar
headers and at most 64 bytes from each end of the ten target payloads.

No mode can download a complete object or a target payload.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import quote, urljoin, urlsplit

try:
    import httpx
except ImportError:  # pragma: no cover - checked by live mode
    httpx = None  # type: ignore[assignment]


REPOSITORY = "longvideobench/LongVideoBench"
REVISION = "60d1c89c1919a198b73be39c2babb213b29d6a5c"
EXPECTED_VIDEO_TAR_SIZE = 161_564_180_480
EXPECTED_SUBTITLE_TAR_SIZE = 117_381_120
EXPECTED_MANIFEST_REQUESTS = 13_343
EXPECTED_MANIFEST_BODY_BYTES = 6_830_592
BLOCK_SIZE = 512
TASK58_SINGLE_BODY_LIMIT = 8 * 1024 * 1024
TASK58_TOTAL_BODY_LIMIT = 256 * 1024 * 1024
AUDIT_SINGLE_BODY_LIMIT = 512
AUDIT_TOTAL_BODY_LIMIT = 1 * 1024 * 1024
PRACTICAL_AUDIT_TARGET = 64 * 1024
MAX_REDIRECTS = 8

EVIDENCE_REL = Path(
    "data/access_review/evidence/"
    "lvb_LongVideoBench_api_2026-09-08_rev-"
    f"{REVISION}.json"
)
PARTS_REL = Path("data/acquisition_preflight/lvb_tar_parts.csv")
VIDEO_RANGES_REL = Path("data/acquisition_preflight/lvb_five_member_ranges.csv")
SUBTITLE_RANGES_REL = Path("data/acquisition_preflight/lvb_subtitle_ranges.csv")
MANIFEST_REL = Path("data/acquisition_preflight/lvb_range_probe_manifest.json")
AUDIT_REL = Path("data/acquisition_preflight/lvb_live_index_audit.json")

TARGETS: tuple[tuple[str, str], ...] = (
    ("ccp-008", "-PgbM2MhcYQ"),
    ("ccp-009", "-eRimFrm6kQ"),
    ("ccp-003", "-7wwfGJXEZg"),
    ("ccp-011", "H5vpBCLo74U"),
    ("ccp-012", "TMe7oXMJoSM"),
)

ALLOWED_HOST_SUFFIXES = (
    "huggingface.co",
    ".huggingface.co",
    ".hf.co",
    ".xethub.hf.co",
)
REDIRECT_CODES = {301, 302, 303, 307, 308}
REFRESH_STATUSES = {400, 401, 403}
CONTENT_RANGE_RE = re.compile(r"^bytes (\d+)-(\d+)/(\d+)$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REQUEST_RANGE_RE = re.compile(r"^bytes=(\d+)-(\d+)$")
TOKEN_PATTERNS = (
    re.compile(r"\bBearer\s+\S+", re.IGNORECASE),
    re.compile(r"\bhf_[A-Za-z0-9]{8,}\b"),
    re.compile(r"\b(?:authorization|proxy-authorization|cookie|set-cookie)\s*:", re.IGNORECASE),
    re.compile(
        r"(?:[?&]|\\u0026)(?:x-amz-(?:signature|credential|security-token)|"
        r"signature|policy|key-pair-id|token|access_token)=",
        re.IGNORECASE,
    ),
)


class AuditError(RuntimeError):
    """A fixed, credential-free audit error."""


@dataclass(frozen=True)
class Part:
    index: int
    name: str
    size: int
    start: int
    end_inclusive: int
    sha256: str


@dataclass(frozen=True)
class TarHeader:
    path: str
    size: int
    typeflag: str
    stored_checksum: int
    unsigned_checksum: int
    signed_checksum: int


class Checks:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    def add(self, check_id: str, passed: bool, evidence: Any = None) -> bool:
        item: dict[str, Any] = {"id": check_id, "status": "PASS" if passed else "FAIL"}
        if evidence is not None:
            item["evidence"] = evidence
        self.items.append(item)
        return passed

    @property
    def passed(self) -> bool:
        return all(item["status"] == "PASS" for item in self.items)

    @property
    def failures(self) -> list[str]:
        return [item["id"] for item in self.items if item["status"] != "PASS"]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def canonical_url(filename: str) -> str:
    if not filename or filename != PurePosixPath(filename).name:
        raise AuditError("INVALID_OBJECT_FILENAME")
    return (
        "https://huggingface.co/datasets/"
        f"{REPOSITORY}/resolve/{REVISION}/{quote(filename, safe='')}"
    )


def host_allowed(host: str) -> bool:
    normalized = host.lower().rstrip(".")
    return any(
        normalized == suffix.lstrip(".")
        or (suffix.startswith(".") and normalized.endswith(suffix))
        for suffix in ALLOWED_HOST_SUFFIXES
    )


def parse_url_safely(url: str) -> Any:
    parsed = urlsplit(url)
    if parsed.scheme.lower() != "https":
        raise AuditError("NON_HTTPS_URL")
    if parsed.username is not None or parsed.password is not None:
        raise AuditError("URL_USERINFO_PRESENT")
    try:
        port = parsed.port
    except ValueError:
        raise AuditError("INVALID_URL_PORT") from None
    if not parsed.hostname or not host_allowed(parsed.hostname):
        raise AuditError("URL_HOST_OUTSIDE_ALLOWED_FAMILY")
    if port is not None and not (1 <= port <= 65535):
        raise AuditError("INVALID_URL_PORT")
    return parsed


def parse_content_range(value: str) -> tuple[int, int, int]:
    match = CONTENT_RANGE_RE.fullmatch(value.strip())
    if not match:
        raise AuditError("INVALID_CONTENT_RANGE")
    return tuple(int(group) for group in match.groups())  # type: ignore[return-value]


def parse_requested_range(value: str) -> tuple[int, int]:
    match = REQUEST_RANGE_RE.fullmatch(value.strip())
    if not match:
        raise AuditError("INVALID_REQUEST_RANGE")
    return int(match.group(1)), int(match.group(2))


def parse_tar_number(field: bytes) -> int:
    if not field:
        return 0
    if field[0] & 0x80:
        raw = bytearray(field)
        negative = bool(raw[0] & 0x40)
        raw[0] &= 0x7F
        value = int.from_bytes(raw, "big", signed=False)
        if negative:
            value -= 1 << (len(field) * 8 - 1)
        if value < 0:
            raise AuditError("NEGATIVE_TAR_NUMBER")
        return value
    stripped = field.rstrip(b"\0 ").lstrip(b" ")
    if not stripped:
        return 0
    if any(byte not in b"01234567" for byte in stripped):
        raise AuditError("INVALID_TAR_OCTAL")
    return int(stripped, 8)


def parse_tar_header(block: bytes) -> TarHeader:
    if len(block) != BLOCK_SIZE:
        raise AuditError("TAR_HEADER_NOT_512_BYTES")
    stored = parse_tar_number(block[148:156])
    unsigned = sum(block[:148]) + 8 * 32 + sum(block[156:])
    signed = (
        sum(byte if byte < 128 else byte - 256 for byte in block[:148])
        + 8 * 32
        + sum(byte if byte < 128 else byte - 256 for byte in block[156:])
    )
    if stored not in (unsigned, signed):
        raise AuditError("INVALID_TAR_HEADER_CHECKSUM")
    name = block[0:100].split(b"\0", 1)[0].decode("utf-8", errors="strict")
    prefix = block[345:500].split(b"\0", 1)[0].decode("utf-8", errors="strict")
    path = f"{prefix}/{name}" if prefix and name else prefix or name
    type_byte = block[156]
    typeflag = "\0" if type_byte == 0 else chr(type_byte)
    return TarHeader(path, parse_tar_number(block[124:136]), typeflag, stored, unsigned, signed)


def round_up_block(value: int) -> int:
    return ((value + BLOCK_SIZE - 1) // BLOCK_SIZE) * BLOCK_SIZE


def recursive_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for key, child in value.items():
            yield str(key)
            yield from recursive_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from recursive_strings(child)


def find_secret_indicators(raw_text: str, parsed: Any) -> list[str]:
    findings: set[str] = set()
    for index, pattern in enumerate(TOKEN_PATTERNS, start=1):
        if pattern.search(raw_text):
            findings.add(f"secret-pattern-{index}")
    forbidden_keys = {
        "authorization",
        "cookie",
        "cookies",
        "effective_url",
        "password",
        "proxy_authorization",
        "proxy_credentials",
        "proxy_password",
        "proxy_url",
        "secret",
        "signed_url",
        "token",
    }

    def inspect_keys(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                if str(key).strip().lower().replace("-", "_") in forbidden_keys:
                    findings.add(f"forbidden-key:{str(key).lower()}")
                inspect_keys(child)
        elif isinstance(value, list):
            for child in value:
                inspect_keys(child)

    inspect_keys(parsed)
    for value in recursive_strings(parsed):
        if not value.lower().startswith(("http://", "https://")):
            continue
        parsed_url = urlsplit(value)
        if parsed_url.query:
            findings.add("url-query")
        if parsed_url.username is not None or parsed_url.password is not None:
            findings.add("url-userinfo")
        if parsed_url.scheme.lower() != "https":
            findings.add("non-https-url")
    return sorted(findings)


def official_objects(evidence: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        item["rfilename"]: item
        for item in evidence.get("siblings", [])
        if isinstance(item, Mapping) and isinstance(item.get("rfilename"), str)
    }


def load_parts(rows: Sequence[Mapping[str, str]]) -> list[Part]:
    parts = [
        Part(
            index=int(row["part_index"]),
            name=row["part_name"],
            size=int(row["content_length"]),
            start=int(row["global_start_offset"]),
            end_inclusive=int(row["global_end_offset_inclusive"]),
            sha256=row["lfs_sha256"],
        )
        for row in rows
    ]
    return sorted(parts, key=lambda item: item.index)


def compute_part_ranges(start: int, size: int, parts: Sequence[Part]) -> list[dict[str, Any]]:
    if size <= 0:
        return []
    end = start + size - 1
    result: list[dict[str, Any]] = []
    for part in parts:
        overlap_start = max(start, part.start)
        overlap_end = min(end, part.end_inclusive)
        if overlap_start > overlap_end:
            continue
        local_start = overlap_start - part.start
        local_end = overlap_end - part.start
        result.append(
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
    return result


def intervals_do_not_overlap(intervals: Sequence[tuple[str, int, int]]) -> bool:
    ordered = sorted(intervals, key=lambda item: (item[1], item[2], item[0]))
    return all(left[2] <= right[1] for left, right in zip(ordered, ordered[1:]))


def _audit_manifest(
    checks: Checks,
    manifest_path: Path,
    manifest: Mapping[str, Any],
    raw_manifest: str,
    object_sizes: Mapping[str, int],
) -> dict[str, Any]:
    requests = manifest.get("requests")
    checks.add(
        "A01_manifest_is_over_10_mib_and_parsed",
        manifest_path.stat().st_size > 10 * 1024 * 1024 and isinstance(requests, list),
        {"bytes": manifest_path.stat().st_size},
    )
    checks.add(
        "A02_manifest_repository_and_revision_are_exact",
        manifest.get("repository") == REPOSITORY and manifest.get("pinned_revision") == REVISION,
        {"repository": manifest.get("repository"), "revision": manifest.get("pinned_revision")},
    )
    secret_indicators = find_secret_indicators(raw_manifest, manifest)
    authentication = manifest.get("authentication", {})
    checks.add(
        "A03_no_credentials_or_signed_urls_persisted",
        not secret_indicators
        and authentication.get("token_or_cookie_persisted") is False
        and authentication.get("authorization_headers_recorded") is False,
        {"secret_indicators": secret_indicators},
    )
    if not isinstance(requests, list):
        checks.add("A04_request_records_are_well_formed", False)
        return {"request_count": 0, "range_count": 0, "body_bytes": 0, "hosts": []}

    request_ids: list[str] = []
    canonical_ok = True
    redirects_ok = True
    effective_hosts_ok = True
    range_records_ok = True
    no_complete_ranges = True
    body_sizes_ok = True
    no_errors = True
    observed_hosts: set[str] = set()
    body_sum = 0
    max_body = 0
    range_count = 0
    mandatory = {
        ("videos.tar.part.aa", "HEAD"): False,
        ("videos.tar.part.aa", "GET"): False,
        ("subtitles.tar", "HEAD"): False,
        ("subtitles.tar", "GET"): False,
    }

    for record in requests:
        if not isinstance(record, Mapping):
            range_records_ok = False
            continue
        request_ids.append(str(record.get("request_id")))
        filename = str(record.get("filename", ""))
        try:
            expected_canonical = canonical_url(filename)
        except AuditError:
            canonical_ok = False
            expected_canonical = ""
        canonical_ok &= record.get("canonical_url") == expected_canonical
        try:
            canonical_parsed = parse_url_safely(str(record.get("canonical_url", "")))
            canonical_ok &= canonical_parsed.query == "" and canonical_parsed.fragment == ""
        except AuditError:
            canonical_ok = False

        effective_host = str(record.get("effective_host") or "")
        if effective_host:
            observed_hosts.add(effective_host)
        effective_hosts_ok &= bool(effective_host) and host_allowed(effective_host)

        for hop in record.get("redirect_chain", []):
            try:
                location = str(hop["location"])
                parsed_location = parse_url_safely(location)
                redirects_ok &= parsed_location.query == "" and parsed_location.fragment == ""
                redirects_ok &= host_allowed(str(hop["from_host"])) and host_allowed(str(hop["to_host"]))
                redirects_ok &= parsed_location.hostname.lower().rstrip(".") == str(hop["to_host"]).lower().rstrip(".")
                redirects_ok &= int(hop["status_code"]) in REDIRECT_CODES
            except (AuditError, KeyError, TypeError, ValueError):
                redirects_ok = False

        method = record.get("method")
        requested_range = record.get("requested_range")
        bytes_received = record.get("bytes_received")
        try:
            body_count = int(bytes_received)
        except (TypeError, ValueError):
            body_count = -1
            body_sizes_ok = False
        if body_count >= 0:
            body_sum += body_count
            max_body = max(max_body, body_count)
        no_errors &= record.get("error_code") is None
        no_errors &= record.get("url_has_query") is False
        no_errors &= record.get("credentials_or_query_secrets_recorded") is False

        if method == "HEAD":
            range_records_ok &= requested_range is None
            range_records_ok &= record.get("response_status") == 200
            range_records_ok &= body_count == 0
            range_records_ok &= filename in object_sizes
            range_records_ok &= record.get("content_length") == object_sizes.get(filename)
            range_records_ok &= record.get("content_range") is None
            if (filename, "HEAD") in mandatory and record.get("purpose") == "mandatory-preflight-head":
                mandatory[(filename, "HEAD")] = True
        elif method == "GET":
            range_count += 1
            try:
                requested_start, requested_end = parse_requested_range(str(requested_range))
                actual_start, actual_end, actual_total = parse_content_range(
                    str(record.get("content_range"))
                )
                expected_length = requested_end - requested_start + 1
                range_records_ok &= record.get("response_status") == 206
                range_records_ok &= (requested_start, requested_end) == (actual_start, actual_end)
                range_records_ok &= actual_total == object_sizes.get(filename)
                range_records_ok &= record.get("content_length") == expected_length
                range_records_ok &= body_count == expected_length
                range_records_ok &= bool(SHA256_RE.fullmatch(str(record.get("sha256") or "")))
                no_complete_ranges &= not (
                    requested_start == 0 and requested_end == actual_total - 1
                )
                body_sizes_ok &= 0 < body_count <= TASK58_SINGLE_BODY_LIMIT
                if (
                    (filename, "GET") in mandatory
                    and record.get("purpose") == "mandatory-preflight-range"
                    and (requested_start, requested_end) == (0, 511)
                ):
                    mandatory[(filename, "GET")] = True
            except (AuditError, TypeError, ValueError):
                range_records_ok = False
        else:
            range_records_ok = False

    expected_ids = [f"request-{index:06d}" for index in range(1, len(requests) + 1)]
    checks.add(
        "A04_request_ids_and_count_are_complete",
        request_ids == expected_ids
        and len(requests) == EXPECTED_MANIFEST_REQUESTS
        and manifest.get("accounting", {}).get("request_count") == len(requests),
        {"request_count": len(requests)},
    )
    checks.add("A05_canonical_urls_are_exactly_pinned", canonical_ok)
    checks.add("A06_redirect_locations_are_https_query_stripped_and_allowed", redirects_ok)
    checks.add(
        "A07_effective_hosts_are_in_official_hf_delivery_family",
        effective_hosts_ok,
        {"hosts": sorted(observed_hosts)},
    )
    checks.add(
        "A08_all_range_responses_and_lengths_agree",
        range_records_ok and range_count == EXPECTED_MANIFEST_REQUESTS - 2,
        {"range_requests": range_count},
    )
    checks.add("A09_no_request_record_reports_an_error_or_secret_flag", no_errors)
    checks.add("A10_no_complete_object_range_was_requested", no_complete_ranges)
    checks.add(
        "A11_response_body_limits_and_aggregate_agree",
        body_sizes_ok
        and max_body <= TASK58_SINGLE_BODY_LIMIT
        and body_sum == EXPECTED_MANIFEST_BODY_BYTES
        and body_sum <= TASK58_TOTAL_BODY_LIMIT
        and manifest.get("limits", {}).get("maximum_single_http_response_body_bytes")
        == TASK58_SINGLE_BODY_LIMIT
        and manifest.get("limits", {}).get("maximum_total_response_body_bytes")
        == TASK58_TOTAL_BODY_LIMIT
        and manifest.get("accounting", {}).get("total_response_body_bytes") == body_sum
        and manifest.get("accounting", {}).get("maximum_response_body_observed") == max_body,
        {"total_bytes": body_sum, "maximum_body_bytes": max_body},
    )
    checks.add(
        "A12_mandatory_head_and_range_probes_exist_for_both_archives",
        all(mandatory.values()),
        {"probes": {f"{name}:{method}": found for (name, method), found in mandatory.items()}},
    )
    return {
        "request_count": len(requests),
        "range_request_count": range_count,
        "response_body_bytes": body_sum,
        "maximum_response_body_bytes": max_body,
        "effective_hosts": sorted(observed_hosts),
    }


def _audit_parts(
    checks: Checks,
    rows: Sequence[Mapping[str, str]],
    evidence: Mapping[str, Any],
) -> tuple[list[Part], dict[str, int], dict[str, Any]]:
    objects = official_objects(evidence)
    official_names = sorted(name for name in objects if name.startswith("videos.tar.part."))
    try:
        parts = load_parts(rows)
    except (KeyError, TypeError, ValueError):
        checks.add("B01_all_31_official_parts_are_present_once", False)
        return [], {}, {"parts": [], "concatenated_size": 0}
    names = [part.name for part in parts]
    checks.add(
        "B01_all_31_official_parts_are_present_once",
        len(parts) == 31
        and len(set(names)) == 31
        and names == official_names
        and [part.index for part in parts] == list(range(31)),
        {"part_count": len(parts)},
    )
    official_match = True
    contiguous = True
    expected_start = 0
    for part, row in zip(parts, sorted(rows, key=lambda item: int(item["part_index"]))):
        official = objects.get(part.name, {})
        official_lfs = official.get("lfs", {}) if isinstance(official, Mapping) else {}
        official_match &= (
            part.size == official.get("size")
            and part.size == official_lfs.get("size")
            and part.sha256 == official_lfs.get("sha256")
            and row.get("pinned_revision") == REVISION
            and row.get("metadata_source") == EVIDENCE_REL.as_posix()
            and bool(SHA256_RE.fullmatch(part.sha256))
        )
        contiguous &= (
            part.start == expected_start
            and part.end_inclusive == part.start + part.size - 1
            and part.start % BLOCK_SIZE == 0
            and part.size % BLOCK_SIZE == 0
        )
        expected_start += part.size
    checks.add("B02_part_sizes_and_hashes_match_pinned_official_evidence", official_match)
    checks.add(
        "B03_parts_are_contiguous_aligned_and_total_size_is_exact",
        contiguous and expected_start == EXPECTED_VIDEO_TAR_SIZE,
        {"concatenated_size": expected_start},
    )
    subtitle = objects.get("subtitles.tar", {})
    subtitle_lfs = subtitle.get("lfs", {}) if isinstance(subtitle, Mapping) else {}
    checks.add(
        "B04_subtitles_archive_matches_pinned_official_evidence",
        subtitle.get("size") == EXPECTED_SUBTITLE_TAR_SIZE
        and subtitle_lfs.get("size") == EXPECTED_SUBTITLE_TAR_SIZE
        and bool(SHA256_RE.fullmatch(str(subtitle_lfs.get("sha256") or ""))),
        {
            "size": subtitle.get("size"),
            "sha256": subtitle_lfs.get("sha256"),
        },
    )
    sizes = {part.name: part.size for part in parts}
    sizes["subtitles.tar"] = EXPECTED_SUBTITLE_TAR_SIZE
    return (
        parts,
        sizes,
        {
            "video_parts": [
                {
                    "index": part.index,
                    "name": part.name,
                    "size": part.size,
                    "global_start": part.start,
                    "global_end_inclusive": part.end_inclusive,
                    "lfs_sha256": part.sha256,
                }
                for part in parts
            ],
            "video_part_count": len(parts),
            "concatenated_video_tar_size": sum(part.size for part in parts),
            "subtitles_tar": {
                "size": subtitle.get("size"),
                "lfs_sha256": subtitle_lfs.get("sha256"),
            },
        },
    )


def _audit_target_geometry(
    checks: Checks,
    video_rows: Sequence[Mapping[str, str]],
    subtitle_rows: Sequence[Mapping[str, str]],
    parts: Sequence[Part],
) -> dict[str, Any]:
    expected_video = {
        candidate: (video_id, f"{video_id}.mp4") for candidate, video_id in TARGETS
    }
    expected_subtitle = {
        candidate: (video_id, f"{video_id}_en.json") for candidate, video_id in TARGETS
    }
    video_ok = len(video_rows) == 5
    subtitle_ok = len(subtitle_rows) == 5
    video_intervals: list[tuple[str, int, int]] = []
    subtitle_intervals: list[tuple[str, int, int]] = []
    basenames: list[str] = []
    recomputed_videos: list[dict[str, Any]] = []
    recomputed_subtitles: list[dict[str, Any]] = []

    for row in video_rows:
        try:
            candidate = row["candidate_id"]
            video_id, basename = expected_video[candidate]
            size = int(row["member_size"])
            header = int(row["tar_header_global_offset"])
            data = int(row["tar_data_global_offset"])
            end = int(row["tar_end_global_offset"])
            member_path = row["member_path"]
            ranges = json.loads(row["part_ranges_json"])
            expected_ranges = compute_part_ranges(data, size, parts)
            next_header = data + round_up_block(size)
            row_ok = (
                row["video_id"] == video_id
                and PurePosixPath(member_path).name == basename
                and size > 0
                and header % BLOCK_SIZE == 0
                and data == header + BLOCK_SIZE
                and end == data + size
                and end <= EXPECTED_VIDEO_TAR_SIZE
                and next_header <= EXPECTED_VIDEO_TAR_SIZE
                and ranges == expected_ranges
                and sum(item["length"] for item in ranges) == size
                and all(
                    item["global_end_inclusive"] - item["global_start"] + 1
                    == item["length"]
                    == item["part_end_inclusive"] - item["part_start"] + 1
                    and item["http_range"]
                    == f"bytes={item['part_start']}-{item['part_end_inclusive']}"
                    for item in ranges
                )
                and row["first_part"] == expected_ranges[0]["part_name"]
                and row["last_part"] == expected_ranges[-1]["part_name"]
                and row["header_checksum_status"] == "VALID"
                and row["range_extraction_feasible"] == "true"
                and row["status"] == "LOCATED_HEADER_ONLY"
                and not row["blocker"]
            )
            video_ok &= row_ok
            basenames.append(PurePosixPath(member_path).name)
            video_intervals.append((candidate, data, end))
            recomputed_videos.append(
                {
                    "candidate_id": candidate,
                    "basename": basename,
                    "header_offset": header,
                    "data_offset": data,
                    "end_offset_exclusive": end,
                    "next_header_offset": next_header,
                    "size": size,
                    "first_part": expected_ranges[0]["part_name"],
                    "last_part": expected_ranges[-1]["part_name"],
                    "range_count": len(expected_ranges),
                }
            )
        except (KeyError, TypeError, ValueError, IndexError, json.JSONDecodeError):
            video_ok = False

    for row in subtitle_rows:
        try:
            candidate = row["candidate_id"]
            video_id, basename = expected_subtitle[candidate]
            size = int(row["member_size"])
            header = int(row["tar_header_offset"])
            data = int(row["tar_data_offset"])
            end = int(row["tar_end_offset"])
            member_path = row["member_path"]
            ranges = json.loads(row["part_ranges_json"])
            expected_ranges = [
                {
                    "archive": "subtitles.tar",
                    "global_start": data,
                    "global_end_inclusive": end - 1,
                    "http_range": f"bytes={data}-{end - 1}",
                    "length": size,
                }
            ]
            next_header = data + round_up_block(size)
            row_ok = (
                row["video_id"] == video_id
                and PurePosixPath(member_path).name == basename
                and size > 0
                and header % BLOCK_SIZE == 0
                and data == header + BLOCK_SIZE
                and end == data + size
                and end <= EXPECTED_SUBTITLE_TAR_SIZE
                and next_header <= EXPECTED_SUBTITLE_TAR_SIZE
                and row["requested_archive"] == "subtitles.tar"
                and int(row["archive_content_length"]) == EXPECTED_SUBTITLE_TAR_SIZE
                and ranges == expected_ranges
                and row["header_checksum_status"] == "VALID"
                and row["range_extraction_feasible"] == "true"
                and row["status"] == "LOCATED_HEADER_ONLY"
                and not row["blocker"]
            )
            subtitle_ok &= row_ok
            basenames.append(PurePosixPath(member_path).name)
            subtitle_intervals.append((candidate, data, end))
            recomputed_subtitles.append(
                {
                    "candidate_id": candidate,
                    "basename": basename,
                    "header_offset": header,
                    "data_offset": data,
                    "end_offset_exclusive": end,
                    "next_header_offset": next_header,
                    "size": size,
                    "range_count": 1,
                }
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            subtitle_ok = False

    expected_basenames = {
        f"{video_id}.mp4" for _, video_id in TARGETS
    } | {f"{video_id}_en.json" for _, video_id in TARGETS}
    checks.add("B05_five_video_geometries_and_ranges_recompute_exactly", video_ok)
    checks.add("B06_five_subtitle_geometries_and_ranges_recompute_exactly", subtitle_ok)
    checks.add(
        "B07_all_ten_expected_basenames_are_present_and_unique",
        len(basenames) == 10 and len(set(basenames)) == 10 and set(basenames) == expected_basenames,
        {"basenames": sorted(basenames)},
    )
    checks.add(
        "B08_target_payload_intervals_do_not_overlap",
        intervals_do_not_overlap(video_intervals)
        and intervals_do_not_overlap(subtitle_intervals),
    )
    checks.add(
        "B09_all_reported_header_checksum_statuses_are_valid",
        all(row.get("header_checksum_status") == "VALID" for row in [*video_rows, *subtitle_rows]),
    )
    return {
        "videos": recomputed_videos,
        "subtitles": recomputed_subtitles,
        "video_intervals_nonoverlapping": intervals_do_not_overlap(video_intervals),
        "subtitle_intervals_nonoverlapping": intervals_do_not_overlap(subtitle_intervals),
    }


def _audit_target_header_request_coverage(
    checks: Checks,
    manifest: Mapping[str, Any],
    geometry: Mapping[str, Any],
    parts: Sequence[Part],
) -> None:
    observed: set[tuple[str, str, str]] = set()
    for record in manifest.get("requests", []):
        if (
            isinstance(record, Mapping)
            and record.get("method") == "GET"
            and record.get("response_status") == 206
        ):
            observed.add(
                (
                    str(record.get("filename")),
                    str(record.get("requested_range")),
                    str(record.get("purpose")),
                )
            )

    expected: list[dict[str, str]] = []
    covered = True
    for item in geometry.get("videos", []):
        header_offset = int(item["header_offset"])
        containing = [
            part
            for part in parts
            if part.start <= header_offset <= part.end_inclusive
        ]
        if len(containing) != 1:
            covered = False
            continue
        part = containing[0]
        local_start = header_offset - part.start
        key = (
            part.name,
            f"bytes={local_start}-{local_start + BLOCK_SIZE - 1}",
            "videos.tar:tar-header",
        )
        expected.append(
            {"filename": key[0], "range": key[1], "purpose": key[2]}
        )
        covered &= key in observed
    for item in geometry.get("subtitles", []):
        header_offset = int(item["header_offset"])
        key = (
            "subtitles.tar",
            f"bytes={header_offset}-{header_offset + BLOCK_SIZE - 1}",
            "subtitles.tar:tar-header",
        )
        expected.append(
            {"filename": key[0], "range": key[1], "purpose": key[2]}
        )
        covered &= key in observed
    checks.add(
        "B10_all_ten_target_header_offsets_have_exact_task58_range_records",
        covered and len(expected) == 10,
        {"expected_header_requests": expected},
    )


def offline_audit(repo_root: Path) -> dict[str, Any]:
    checks = Checks()
    paths = {
        "manifest": repo_root / MANIFEST_REL,
        "evidence": repo_root / EVIDENCE_REL,
        "parts": repo_root / PARTS_REL,
        "videos": repo_root / VIDEO_RANGES_REL,
        "subtitles": repo_root / SUBTITLE_RANGES_REL,
    }
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise AuditError("REQUIRED_INPUT_MISSING")

    raw_manifest = paths["manifest"].read_text(encoding="utf-8")
    manifest = json.loads(raw_manifest)
    evidence = json.loads(paths["evidence"].read_text(encoding="utf-8"))
    part_rows = read_csv(paths["parts"])
    video_rows = read_csv(paths["videos"])
    subtitle_rows = read_csv(paths["subtitles"])

    checks.add(
        "P01_pinned_evidence_identity_is_exact",
        evidence.get("id") == REPOSITORY and evidence.get("sha") == REVISION,
        {"repository": evidence.get("id"), "revision": evidence.get("sha")},
    )
    evidence_hash = sha256_file(paths["evidence"])
    checks.add(
        "P02_manifest_pins_the_exact_evidence_file_hash",
        manifest.get("source_metadata_evidence", {}).get("path") == EVIDENCE_REL.as_posix()
        and manifest.get("source_metadata_evidence", {}).get("sha256") == evidence_hash,
        {"evidence_sha256": evidence_hash},
    )
    parts, object_sizes, archive_geometry = _audit_parts(checks, part_rows, evidence)
    manifest_summary = _audit_manifest(
        checks, paths["manifest"], manifest, raw_manifest, object_sizes
    )
    geometry = _audit_target_geometry(checks, video_rows, subtitle_rows, parts)
    _audit_target_header_request_coverage(checks, manifest, geometry, parts)

    integrity = manifest.get("output_integrity_excluding_manifest", {})
    integrity_ok = True
    integrity_observed: dict[str, dict[str, Any]] = {}
    for relative in (PARTS_REL, VIDEO_RANGES_REL, SUBTITLE_RANGES_REL, Path("docs/review/lvb_tar_range_preflight.md")):
        path = repo_root / relative
        observed = {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
        integrity_observed[relative.as_posix()] = observed
        integrity_ok &= integrity.get(relative.as_posix()) == observed
    checks.add("P03_task58_output_hashes_and_sizes_match_manifest", integrity_ok)
    checks.add(
        "P04_task58_declared_success_and_header_only_boundary",
        manifest.get("outcome") == "GO_HEADER_INDEX_COMPLETE"
        and manifest.get("conclusion") == "GO"
        and manifest.get("safety", {}).get("media_member_payload_downloaded") is False
        and manifest.get("safety", {}).get("complete_archive_part_downloaded") is False
        and manifest.get("safety", {}).get("complete_subtitles_archive_downloaded") is False
        and manifest.get("safety", {}).get("target_payload_download_mode_available") is False,
    )
    return {
        "status": "PASS" if checks.passed else "FAIL",
        "checks": checks.items,
        "failures": checks.failures,
        "manifest": manifest_summary,
        "archive_geometry": archive_geometry,
        "geometry": geometry,
        "input_integrity": integrity_observed,
    }


class BoundedLiveClient:
    """Minimal independent HTTPS Range client with no persisted effective URLs."""

    def __init__(self, token: str, *, client: Any | None = None) -> None:
        if not token:
            raise AuditError("HF_TOKEN_NOT_AVAILABLE")
        if httpx is None:
            raise AuditError("HTTPX_NOT_INSTALLED")
        self._token = token
        self._owns_client = client is None
        self._client = client or httpx.Client(
            follow_redirects=False,
            trust_env=True,
            timeout=httpx.Timeout(60.0, connect=30.0),
            headers={"User-Agent": "AV-TRACE-lvb-independent-index-audit/1.0"},
        )
        self._effective_cache: dict[tuple[str, int], str] = {}
        self.total_bytes = 0
        self.request_count = 0
        self.hosts: set[str] = set()
        self.redirects: list[dict[str, Any]] = []

    def close(self) -> None:
        self._token = ""
        self._effective_cache.clear()
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "BoundedLiveClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def _origin(parsed: Any) -> tuple[str, str, int]:
        return parsed.scheme.lower(), parsed.hostname.lower().rstrip("."), parsed.port or 443

    def fetch(self, filename: str, start: int, end: int, object_size: int) -> bytes:
        if start < 0 or end < start or end >= object_size:
            raise AuditError("LIVE_RANGE_OUTSIDE_OBJECT")
        if start == 0 and end == object_size - 1:
            raise AuditError("LIVE_COMPLETE_OBJECT_RANGE_PROHIBITED")
        expected = end - start + 1
        if expected > AUDIT_SINGLE_BODY_LIMIT:
            raise AuditError("LIVE_SINGLE_BODY_LIMIT_EXCEEDED")
        if self.total_bytes + expected > AUDIT_TOTAL_BODY_LIMIT:
            raise AuditError("LIVE_TOTAL_BODY_LIMIT_EXCEEDED")

        canonical = canonical_url(filename)
        canonical_parsed = parse_url_safely(canonical)
        canonical_origin = self._origin(canonical_parsed)
        cache_key = (canonical, object_size)
        cached = self._effective_cache.get(cache_key)
        url = cached or canonical
        canonical_resolution = cached is None
        refreshed = False
        redirect_count = 0
        while True:
            parsed = parse_url_safely(url)
            headers = {"Range": f"bytes={start}-{end}", "Accept-Encoding": "identity"}
            if canonical_resolution and self._origin(parsed) == canonical_origin:
                headers["Authorization"] = f"Bearer {self._token}"
            try:
                with self._client.stream("GET", url, headers=headers) as response:
                    if response.status_code in REDIRECT_CODES:
                        location = response.headers.get("location")
                        if not location:
                            raise AuditError("LIVE_REDIRECT_WITHOUT_LOCATION")
                        next_url = urljoin(url, location)
                        next_parsed = parse_url_safely(next_url)
                        self.redirects.append(
                            {
                                "status_code": response.status_code,
                                "from_host": parsed.hostname.lower(),
                                "to_host": next_parsed.hostname.lower(),
                            }
                        )
                        redirect_count += 1
                        if redirect_count > MAX_REDIRECTS:
                            raise AuditError("LIVE_TOO_MANY_REDIRECTS")
                        canonical_resolution = (
                            canonical_resolution
                            and self._origin(parsed) == canonical_origin
                            and self._origin(next_parsed) == canonical_origin
                        )
                        url = next_url
                        continue
                    if cached is not None and not refreshed and response.status_code in REFRESH_STATUSES:
                        self._effective_cache.pop(cache_key, None)
                        cached = None
                        refreshed = True
                        canonical_resolution = True
                        url = canonical
                        continue
                    if response.status_code != 206:
                        raise AuditError("LIVE_RANGE_STATUS_NOT_206")
                    if response.headers.get("content-encoding", "identity").lower() != "identity":
                        raise AuditError("LIVE_CONTENT_ENCODING_NOT_IDENTITY")
                    raw_length = response.headers.get("content-length")
                    if raw_length is None or not raw_length.isdigit() or int(raw_length) != expected:
                        raise AuditError("LIVE_CONTENT_LENGTH_MISMATCH")
                    content_range = response.headers.get("content-range")
                    if content_range is None or parse_content_range(content_range) != (
                        start,
                        end,
                        object_size,
                    ):
                        raise AuditError("LIVE_CONTENT_RANGE_MISMATCH")
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        if len(body) + len(chunk) > expected:
                            raise AuditError("LIVE_RESPONSE_EXCESS_BYTES")
                        body.extend(chunk)
                    if len(body) != expected:
                        raise AuditError("LIVE_RESPONSE_TRUNCATED")
                    self.total_bytes += len(body)
                    self.request_count += 1
                    self.hosts.add(parsed.hostname.lower())
                    if self._origin(parsed) == canonical_origin:
                        self._effective_cache.pop(cache_key, None)
                    else:
                        self._effective_cache[cache_key] = url
                    return bytes(body)
            except AuditError:
                raise
            except Exception as exc:
                raise AuditError(f"LIVE_TRANSPORT_{type(exc).__name__.upper()}") from None


def mp4_prefix_result(prefix: bytes) -> dict[str, Any]:
    if len(prefix) < 8:
        return {"compatible": False, "reason": "prefix_too_short"}
    box_size = int.from_bytes(prefix[0:4], "big")
    box_type_bytes = prefix[4:8]
    printable = all(0x20 <= byte <= 0x7E for byte in box_type_bytes)
    box_type = box_type_bytes.decode("ascii", errors="replace")
    compatible_types = {"ftyp", "free", "skip", "wide", "uuid", "moov", "mdat"}
    compatible = printable and box_type in compatible_types and (box_size == 0 or box_size == 1 or box_size >= 8)
    return {
        "compatible": compatible,
        "first_box_type": box_type,
        "first_box_size": box_size,
    }


def json_prefix_result(prefix: bytes) -> dict[str, Any]:
    stripped = prefix.lstrip(b"\xef\xbb\xbf \t\r\n")
    marker = chr(stripped[0]) if stripped else ""
    return {"json_like": marker in {"{", "["}, "first_non_whitespace": marker}


def _multipart_fetch(
    client: BoundedLiveClient,
    parts: Sequence[Part],
    global_start: int,
    length: int,
) -> bytes:
    if length <= 0 or global_start < 0 or global_start + length > EXPECTED_VIDEO_TAR_SIZE:
        raise AuditError("LIVE_MULTIPART_RANGE_INVALID")
    output = bytearray()
    cursor = global_start
    remaining = length
    for part in parts:
        if not (part.start <= cursor <= part.end_inclusive):
            continue
        available = part.end_inclusive - cursor + 1
        count = min(remaining, available)
        local_start = cursor - part.start
        output.extend(
            client.fetch(part.name, local_start, local_start + count - 1, part.size)
        )
        cursor += count
        remaining -= count
        if remaining == 0:
            return bytes(output)
    raise AuditError("LIVE_MULTIPART_RANGE_NOT_COVERED")


def live_spot_check(
    repo_root: Path,
    offline_result: Mapping[str, Any],
    *,
    client_factory: Any | None = None,
) -> dict[str, Any]:
    if offline_result.get("status") != "PASS":
        raise AuditError("OFFLINE_AUDIT_MUST_PASS_BEFORE_LIVE")
    part_rows = read_csv(repo_root / PARTS_REL)
    parts = load_parts(part_rows)
    video_rows = read_csv(repo_root / VIDEO_RANGES_REL)
    subtitle_rows = read_csv(repo_root / SUBTITLE_RANGES_REL)
    try:
        from huggingface_hub import get_token
    except ImportError:
        raise AuditError("HUGGINGFACE_HUB_NOT_INSTALLED") from None
    token = get_token()
    if not token:
        raise AuditError("HF_TOKEN_NOT_AVAILABLE")

    predicted_bytes = 10 * BLOCK_SIZE + sum(
        min(64, int(row["member_size"])) + min(64, int(row["member_size"]))
        for row in [*video_rows, *subtitle_rows]
    )
    if predicted_bytes > PRACTICAL_AUDIT_TARGET:
        raise AuditError("PREDICTED_LIVE_TRANSFER_EXCEEDS_PRACTICAL_TARGET")

    client = client_factory(token) if client_factory else BoundedLiveClient(token)
    observations: list[dict[str, Any]] = []
    try:
        try:
            for archive, rows in (("videos.tar", video_rows), ("subtitles.tar", subtitle_rows)):
                for row in rows:
                    size = int(row["member_size"])
                    header_offset = int(
                        row[
                            "tar_header_global_offset"
                            if archive == "videos.tar"
                            else "tar_header_offset"
                        ]
                    )
                    data_offset = int(
                        row[
                            "tar_data_global_offset"
                            if archive == "videos.tar"
                            else "tar_data_offset"
                        ]
                    )
                    end_offset = int(
                        row[
                            "tar_end_global_offset"
                            if archive == "videos.tar"
                            else "tar_end_offset"
                        ]
                    )
                    if archive == "videos.tar":
                        header_block = _multipart_fetch(client, parts, header_offset, BLOCK_SIZE)
                        first = _multipart_fetch(client, parts, data_offset, min(64, size))
                        last = _multipart_fetch(
                            client, parts, end_offset - min(64, size), min(64, size)
                        )
                    else:
                        header_block = client.fetch(
                            "subtitles.tar",
                            header_offset,
                            header_offset + BLOCK_SIZE - 1,
                            EXPECTED_SUBTITLE_TAR_SIZE,
                        )
                        first = client.fetch(
                            "subtitles.tar",
                            data_offset,
                            data_offset + min(64, size) - 1,
                            EXPECTED_SUBTITLE_TAR_SIZE,
                        )
                        last_count = min(64, size)
                        last = client.fetch(
                            "subtitles.tar",
                            end_offset - last_count,
                            end_offset - 1,
                            EXPECTED_SUBTITLE_TAR_SIZE,
                        )
                    header = parse_tar_header(header_block)
                    basename = PurePosixPath(row["member_path"]).name
                    header_ok = (
                        PurePosixPath(header.path).name == basename
                        and header.path == row["member_path"]
                        and header.size == size
                        and header.typeflag in {"\0", "0", "7"}
                    )
                    content_check = (
                        mp4_prefix_result(first)
                        if archive == "videos.tar"
                        else json_prefix_result(first)
                    )
                    content_ok = (
                        content_check["compatible"]
                        if archive == "videos.tar"
                        else content_check["json_like"]
                    )
                    observations.append(
                        {
                            "archive": archive,
                            "candidate_id": row["candidate_id"],
                            "basename": basename,
                            "header_offset": header_offset,
                            "data_offset": data_offset,
                            "size": size,
                            "header": {
                                "path": header.path,
                                "typeflag": header.typeflag,
                                "size": header.size,
                                "checksum_valid": True,
                                "sha256": hashlib.sha256(header_block).hexdigest(),
                            },
                            "first_bytes": {
                                "count": len(first),
                                "sha256": hashlib.sha256(first).hexdigest(),
                            },
                            "last_bytes": {
                                "count": len(last),
                                "sha256": hashlib.sha256(last).hexdigest(),
                            },
                            "container_or_content_check": content_check,
                            "status": "PASS" if header_ok and content_ok else "FAIL",
                        }
                    )
        except AuditError as exc:
            return {
                "status": "NOT_COMPLETED",
                "attempted": True,
                "safe_error_code": str(exc),
                "successful_range_responses": client.request_count,
                "response_body_bytes": client.total_bytes,
                "predicted_response_body_bytes": predicted_bytes,
                "practical_64_kib_target_met": client.total_bytes <= PRACTICAL_AUDIT_TARGET,
                "hard_1_mib_limit_met": client.total_bytes <= AUDIT_TOTAL_BODY_LIMIT,
                "effective_hosts": sorted(client.hosts),
                "redirect_hops": client.redirects,
                "observations": observations,
            }

        all_passed = all(item["status"] == "PASS" for item in observations)
        budget_ok = (
            client.total_bytes == predicted_bytes
            and client.total_bytes <= PRACTICAL_AUDIT_TARGET
            and client.total_bytes <= AUDIT_TOTAL_BODY_LIMIT
        )
        all_passed &= budget_ok
        return {
            "status": "PASS" if all_passed else "FAIL",
            "attempted": True,
            "successful_range_responses": client.request_count,
            "response_body_bytes": client.total_bytes,
            "predicted_response_body_bytes": predicted_bytes,
            "practical_64_kib_target_met": client.total_bytes <= PRACTICAL_AUDIT_TARGET,
            "hard_1_mib_limit_met": client.total_bytes <= AUDIT_TOTAL_BODY_LIMIT,
            "effective_hosts": sorted(client.hosts),
            "redirect_hops": client.redirects,
            "observations": observations,
            "failures": [
                item["basename"] for item in observations if item["status"] != "PASS"
            ]
            + ([] if budget_ok else ["live_transfer_accounting"]),
        }
    finally:
        client.close()
        token = None


def build_audit(repo_root: Path, *, run_live: bool, client_factory: Any | None = None) -> dict[str, Any]:
    offline = offline_audit(repo_root)
    live: dict[str, Any]
    if run_live:
        try:
            live = live_spot_check(repo_root, offline, client_factory=client_factory)
        except AuditError as exc:
            live = {
                "status": "NOT_COMPLETED",
                "attempted": True,
                "safe_error_code": str(exc),
                "response_body_bytes": 0,
                "observations": [],
            }
    else:
        live = {
            "status": "NOT_RUN",
            "attempted": False,
            "response_body_bytes": 0,
            "observations": [],
        }
    overall_pass = offline["status"] == "PASS" and live["status"] == "PASS"
    return {
        "schema_version": "1.0",
        "task": "Task 59 — independent red-team of the successful live tar index",
        "generated_at_utc": utc_now(),
        "repository": REPOSITORY,
        "pinned_revision": REVISION,
        "independence": {
            "imports_task58_implementation": False,
            "offline_recomputed_from_persisted_primary_artifacts": True,
            "live_client_and_tar_parser_are_independent": True,
        },
        "offline_audit": offline,
        "live_spot_check": live,
        "scientific_scope": {
            "establishes": [
                "exact official archive member identities at the pinned repository revision",
                "validated tar-header metadata and exact byte-range geometry",
            ],
            "does_not_establish": [
                "source-owner rights or permission",
                "continued modality availability",
                "media decodability",
                "subtitle semantic or temporal validity",
                "suitability for benchmark questions",
            ],
        },
        "target_media_acquisition_decision": (
            "PASS_INDEPENDENT_AUDIT"
            if overall_pass
            else "NO_GO_FAIL_CLOSED"
        ),
        "task58_outputs_modified": False,
    }


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (json.dumps(value, indent=2, sort_keys=False, ensure_ascii=True) + "\n").encode()
    with tempfile.NamedTemporaryFile(
        mode="wb", prefix=f".{path.name}.", dir=path.parent, delete=False
    ) as handle:
        temp_path = Path(handle.name)
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, path)


def find_repo_root() -> Path:
    root = Path(__file__).resolve().parents[1]
    if not (root / "pyproject.toml").is_file():
        raise AuditError("REPOSITORY_ROOT_NOT_FOUND")
    return root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Independently audit the successful LongVideoBench live tar index."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--offline", action="store_true", help="audit persisted evidence only")
    mode.add_argument(
        "--live",
        action="store_true",
        help="also perform bounded header and payload-edge spot checks",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=AUDIT_REL,
        help=f"output JSON path relative to repository (default: {AUDIT_REL})",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        root = find_repo_root()
        output = args.output if args.output.is_absolute() else root / args.output
        resolved = output.resolve()
        try:
            resolved.relative_to(root.resolve())
        except ValueError:
            raise AuditError("OUTPUT_PATH_OUTSIDE_REPOSITORY") from None
        result = build_audit(root, run_live=args.live)
        atomic_write_json(resolved, result)
        summary = {
            "offline_status": result["offline_audit"]["status"],
            "live_status": result["live_spot_check"]["status"],
            "decision": result["target_media_acquisition_decision"],
            "audit_response_body_bytes": result["live_spot_check"].get(
                "response_body_bytes", 0
            ),
            "output": str(resolved.relative_to(root)),
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0 if result["target_media_acquisition_decision"] == "PASS_INDEPENDENT_AUDIT" else 2
    except AuditError as exc:
        print(f"lvb live-index audit failed: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"lvb live-index audit failed: INTERNAL_{type(exc).__name__.upper()}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
