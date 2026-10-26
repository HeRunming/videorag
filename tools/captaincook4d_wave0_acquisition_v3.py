#!/usr/bin/env python3
"""Task188: exact CaptainCook4D Wave-0 acquisition through https://proxy.example.invalid:3128.

The acquisition is deliberately narrow:

* freeze 16_20, 15_29, and 26_22 before network access;
* 16_20 and 15_29 are mandatory and cannot be replaced;
* replace only 26_22, and only by advancing through Task174 primary rank;
* request only official GoPro 360p MP4 links;
* use curl with the explicit https://proxy.example.invalid:3128, redirects, and byte ranges;
* retain no unredacted ephemeral BoxCloud capability or cookie value;
* accumulate resumable bytes in ``.part`` and atomically promote exact files;
* run complete PyAV and OpenCV validation through EOF; and
* generate a deterministic Task153 inventory/plan without human review.

No annotation endpoint, HoloLens stream, 4K stream, Ray job, or public-release
path is accessed by this tool.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import parse_qsl, urljoin, urlsplit, urlunsplit

import av
import cv2
from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
TASK_ID = 188
TASK_DATE = "2026-10-09"
TOKEN_READY = "CAPTAINCOOK4D_WAVE0_ACQUISITION_READY"
TOKEN_REPAIR = "CAPTAINCOOK4D_WAVE0_ACQUISITION_REPAIR"
TOKEN_NO_GO = "CAPTAINCOOK4D_WAVE0_ACQUISITION_NO_GO"

PROXY = "https://proxy.example.invalid:3128"
CONNECT_TIMEOUT_SECONDS = 120
PROBE_MAX_TIME_SECONDS = 600
TRANSFER_MAX_TIME_SECONDS = 7200
PROBE_ATTEMPTS = 3
TRANSFER_ATTEMPTS = 8
RETRY_DELAY_SECONDS = 5
MAX_SINGLE_MEDIA_BYTES = 512 * 1024 * 1024
MAX_AGGREGATE_MEDIA_BYTES = 1024 * 1024 * 1024
FREE_SPACE_MARGIN_BYTES = 512 * 1024 * 1024
DURATION_TOLERANCE_SECONDS = 1.0
SYNC_TOLERANCE_SECONDS = 0.25
COPY_CHUNK_BYTES = 4 * 1024 * 1024

BASE = ROOT / "data/restricted/captaincook4d_wave0_sources_v3"
LOGS = BASE / "logs"
MANIFESTS = BASE / "manifests"
PRESCREEN = BASE / "prescreen"
LOCK = BASE / ".task188.lock"
FROZEN_MANIFEST = MANIFESTS / "task188_frozen_selection.json"
ROUTE_LOG = LOGS / "task188_curl_range_acquisition_log.json"
HASH_LOG = LOGS / "task188_final_hashes.json"
AUDIT_LOG = LOGS / "task188_technical_audit.json"
FAILURE_LOG = LOGS / "task188_failure.json"
ROOT_MANIFEST = MANIFESTS / "captaincook4d_wave0_acquisition_manifest.json"
INVENTORY = PRESCREEN / "captaincook4d_wave0_semantic_source_prescreen_inventory.json"
PLAN = PRESCREEN / "captaincook4d_wave0_semantic_source_prescreen_plan.json"
REVIEW = ROOT / "docs/review/captaincook4d_wave0_exact_acquisition_v3.md"
RESULT = ROOT / "orchestration/results/188_captaincook4d_wave0_acquisition_v3.txt"

SELECTION_V1 = (
    ROOT / "data/source_recon/captaincook4d_access_v1/derived/selection_v1.json"
)
ROUTE_INVENTORY_V3 = (
    ROOT
    / "data/source_recon/captaincook4d_access_v3/derived"
    / "selected_media_route_inventory_v3.json"
)
DOWNLOAD_LINKS = ROOT / "data/source_recon/captaincook4d_access_v1/download_links.json"
VIDEO_INFORMATION = (
    ROOT / "data/source_recon/captaincook4d_access_v1/video_information.csv"
)
PROJECT_README = ROOT / "data/source_recon/captaincook4d_access_v1/main_README.md"
DOWNLOADER_LICENSE = (
    ROOT / "data/source_recon/captaincook4d_access_v1/downloader_LICENSE"
)
INVENTORY_SCHEMA = (
    ROOT / "docs/spec/semantic_av_source_prescreen_inventory_schema.json"
)
PLAN_SCHEMA = ROOT / "docs/spec/semantic_av_source_prescreen_plan_schema.json"

INPUT_INTEGRITY = {
    "selection_v1": {
        "path": SELECTION_V1,
        "bytes": 41349,
        "sha256": "911b37e42643b9481d610f2762691df77fb7fde34aaaa1871ff4f3f9aa9d879e",
    },
    "route_inventory_v3": {
        "path": ROUTE_INVENTORY_V3,
        "bytes": 36712,
        "sha256": "df868526530e3783c6a9f944579eb6fe447c145d6e1b936403cbb0c338827347",
    },
    "download_links": {
        "path": DOWNLOAD_LINKS,
        "bytes": 700705,
        "sha256": "81b1e1ef571621da182c5fc31ef97f177927a1a95b22aa545229794542e6f2b4",
    },
    "video_information": {
        "path": VIDEO_INFORMATION,
        "bytes": 8684,
        "sha256": "51febe466df9d336eaca8c5a467475bc3909b9d597208861316be78f4dd50138",
    },
    "project_readme": {
        "path": PROJECT_README,
        "bytes": 10276,
        "sha256": "7a4e5566619bb4a85f83113a182e3b1731a65609acb4e46b4ddbfb3ed02c4a1c",
    },
    "downloader_license": {
        "path": DOWNLOADER_LICENSE,
        "bytes": 11357,
        "sha256": "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4",
    },
}

# The first two totals are explicit Task188 evidence from bounded 2026-10-08
# https://proxy.example.invalid:3128 range probes. They are checked against fresh Content-Range values.
PROVEN_TOTALS = {
    "16_20": 230_486_870,
    "15_29": 181_454_428,
}
FROZEN_INITIAL_IDS = ("16_20", "15_29", "26_22")
FALLBACK_PRIMARY_IDS = ("25_1", "25_109", "2_13", "16_23", "23_19")

ALLOWED_REDIRECT_HOSTS = {
    "utdallas.box.com",
    "utdallas.app.box.com",
    "public.boxcloud.com",
}
SENSITIVE_QUERY_MARKERS = (
    "auth",
    "credential",
    "key",
    "policy",
    "secret",
    "sig",
    "token",
)
URL_RE = re.compile(r"https?://[^\s\"'<>]+")
CONTENT_RANGE_RE = re.compile(
    r"^bytes\s+(\d+)-(\d+)/(\d+|\*)$", re.IGNORECASE
)


class AcquisitionError(RuntimeError):
    """Repairable acquisition or validation failure."""


class NoGoError(AcquisitionError):
    """Non-repairable frozen-identity, rights, or safety failure."""


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(COPY_CHUNK_BYTES):
            digest.update(block)
    return digest.hexdigest()


def hash_file(path: Path) -> dict[str, Any]:
    sha256 = hashlib.sha256()
    md5 = hashlib.md5(usedforsecurity=False)
    size = 0
    with path.open("rb") as handle:
        while block := handle.read(COPY_CHUNK_BYTES):
            size += len(block)
            sha256.update(block)
            md5.update(block)
    return {"bytes": size, "sha256": sha256.hexdigest(), "md5": md5.hexdigest()}


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise NoGoError(f"INVALID_JSON:{path.relative_to(ROOT)}:{exc}") from exc


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def secure_directories() -> None:
    for directory in (BASE, LOGS, MANIFESTS, PRESCREEN):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory.chmod(0o700)


def atomic_write(path: Path, payload: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    descriptor = os.open(
        temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        fsync_directory(path.parent)
    except BaseException:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def write_restricted_json(path: Path, value: Any) -> None:
    atomic_write(path, canonical_json_bytes(value), 0o600)


def write_public_text(path: Path, value: str) -> None:
    atomic_write(path, value.encode("utf-8"), 0o644)


def acquire_lock() -> None:
    try:
        descriptor = os.open(LOCK, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise AcquisitionError("TASK188_LOCK_ALREADY_EXISTS") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(f"pid={os.getpid()} started={utc_now()}\n")
        handle.flush()
        os.fsync(handle.fileno())


def release_lock() -> None:
    try:
        LOCK.unlink()
    except FileNotFoundError:
        return
    fsync_directory(BASE)


def sanitize_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    path = parsed.path
    if host.endswith("boxcloud.com"):
        pieces = path.split("/")
        filename = pieces[-1] if pieces else ""
        path = f"/d/1/[REDACTED_EPHEMERAL_OBJECT_CAPABILITY]/{filename}"
    query = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if any(marker in key.lower() for marker in SENSITIVE_QUERY_MARKERS):
            value = "[REDACTED]"
        query.append((key, value))
    query_text = "&".join(f"{key}={value}" for key, value in query)
    return urlunsplit((parsed.scheme, parsed.netloc, path, query_text, ""))


def sanitize_text(value: str) -> str:
    return URL_RE.sub(lambda match: sanitize_url(match.group(0)) or "", value)


def url_identity(url: str) -> dict[str, Any]:
    parsed = urlsplit(url)
    return {
        "scheme": parsed.scheme,
        "host": (parsed.hostname or "").lower(),
        "redacted_url": sanitize_url(url),
        "full_url_sha256": sha256_bytes(url.encode("utf-8")),
        "full_path_sha256": sha256_bytes(parsed.path.encode("utf-8")),
        "query_keys": sorted(key for key, _ in parse_qsl(parsed.query)),
        "fragment_present": bool(parsed.fragment),
    }


def parse_header_blocks(raw: bytes, initial_url: str) -> list[dict[str, Any]]:
    """Parse curl ``--dump-header -`` without retaining secrets."""

    text = raw.decode("iso-8859-1", errors="replace").replace("\r\n", "\n")
    raw_blocks = re.split(r"\n\n+", text.strip())
    current_url = initial_url
    records: list[dict[str, Any]] = []
    for raw_block in raw_blocks:
        lines = [line for line in raw_block.split("\n") if line]
        if not lines or not lines[0].startswith("HTTP/"):
            continue
        match = re.match(r"HTTP/\S+\s+(\d{3})(?:\s+(.*))?$", lines[0])
        if not match:
            continue
        status = int(match.group(1))
        reason = (match.group(2) or "").strip()
        headers: dict[str, list[str]] = {}
        for line in lines[1:]:
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            headers.setdefault(key.strip().lower(), []).append(value.strip())
        if reason.lower() == "connection established":
            continue
        location = headers.get("location", [None])[-1]
        record = {
            "status_code": status,
            "reason": reason,
            "request": url_identity(current_url),
            "content_type": headers.get("content-type", [None])[-1],
            "content_length": headers.get("content-length", [None])[-1],
            "content_range": headers.get("content-range", [None])[-1],
            "accept_ranges": headers.get("accept-ranges", [None])[-1],
            "etag": headers.get("etag", [None])[-1],
            "last_modified": headers.get("last-modified", [None])[-1],
            "content_disposition": headers.get("content-disposition", [None])[-1],
            "location": sanitize_url(urljoin(current_url, location))
            if location
            else None,
            "location_sha256": sha256_bytes(
                urljoin(current_url, location).encode("utf-8")
            )
            if location
            else None,
            "set_cookie_names": sorted(
                {
                    item.split("=", 1)[0].strip()
                    for item in headers.get("set-cookie", [])
                    if "=" in item
                }
            ),
            "cookie_values_retained": False,
        }
        records.append(record)
        if location:
            current_url = urljoin(current_url, location)
    return records


def parse_content_range(value: str | None) -> tuple[int, int, int]:
    match = CONTENT_RANGE_RE.fullmatch((value or "").strip())
    if not match or match.group(3) == "*":
        raise AcquisitionError(f"INVALID_CONTENT_RANGE:{value!r}")
    start, end, total = map(int, match.groups())
    if start < 0 or end < start or total <= end:
        raise AcquisitionError(f"INCONSISTENT_CONTENT_RANGE:{value!r}")
    return start, end, total


def validate_official_url(url: str) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").lower() != "utdallas.box.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
        or parsed.query
        or parsed.fragment
        or not re.fullmatch(r"/shared/static/[a-z0-9]{32}\.mp4", parsed.path)
    ):
        raise NoGoError(f"INVALID_FROZEN_OFFICIAL_URL:{url}")


def verify_input_integrity() -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, expected in INPUT_INTEGRITY.items():
        raw = expected["path"].read_bytes()
        observed = {"bytes": len(raw), "sha256": sha256_bytes(raw)}
        if observed != {
            "bytes": expected["bytes"],
            "sha256": expected["sha256"],
        }:
            raise NoGoError(f"FROZEN_INPUT_INTEGRITY_MISMATCH:{name}")
        result[name] = {
            "path": expected["path"].relative_to(ROOT).as_posix(),
            **observed,
            "verified": True,
        }
    return result


def verify_rights_evidence() -> dict[str, Any]:
    readme = PROJECT_README.read_text(encoding="utf-8")
    license_text = DOWNLOADER_LICENSE.read_text(encoding="utf-8")
    required = (
        "Our dataset is licensed under the Apache license 2.0",
        "approved by the Institutional Review Board (IRB) at the University of Florida",
        "All participants provided written consent for the data collection",
    )
    if any(fragment not in readme for fragment in required):
        raise NoGoError("OFFICIAL_LICENSE_OR_IRB_STATEMENT_MISSING")
    if (
        "Apache License" not in license_text
        or "Version 2.0, January 2004" not in license_text
    ):
        raise NoGoError("OFFICIAL_APACHE_2_LICENSE_TEXT_INVALID")
    return {
        "dataset_license_statement": "Apache License 2.0",
        "dataset_license_statement_verified": True,
        "university_of_florida_irb_statement_verified": True,
        "written_participant_consent_statement_verified": True,
        "operative_linked_irb_document_archived": False,
        "operative_linked_consent_document_archived": False,
        "use_boundary": (
            "Restricted internal research only for Task188; no public release "
            "or redistribution is authorized."
        ),
    }


def load_candidates() -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    selection = load_json(SELECTION_V1)
    route_inventory = load_json(ROUTE_INVENTORY_V3)
    download_links = load_json(DOWNLOAD_LINKS)
    with VIDEO_INFORMATION.open(newline="", encoding="utf-8") as handle:
        metadata = {row["recording_id"]: row for row in csv.DictReader(handle)}
    route_rows = {
        row["recording_id"]: row for row in route_inventory["recordings"]
    }
    primary_rows = {
        row["representative_recording_id"]: row for row in selection["primary"]
    }
    expected_order = [
        "16_20",
        "15_29",
        "26_22",
        "25_1",
        "25_109",
        "2_13",
        "16_23",
        "23_19",
    ]
    observed_order = [
        row["representative_recording_id"] for row in selection["primary"]
    ]
    if observed_order != expected_order:
        raise NoGoError("TASK174_PRIMARY_ORDER_CHANGED")

    candidates: dict[str, dict[str, Any]] = {}
    for recording_id in expected_order:
        row = primary_rows[recording_id]
        url = row["official_stream_urls"]["gopro_360p"]
        validate_official_url(url)
        candidate = {
            "recording_id": recording_id,
            "role": "PRIMARY",
            "rank": int(row["rank"]),
            "person_id": int(row["person_id"]),
            "environment_id": int(row["environment_id"]),
            "source_group_id": row["source_group_id"],
            "official_duration_seconds": float(row["duration_seconds"]),
            "official_url": url,
        }
        metadata_row = metadata.get(recording_id)
        route_row = route_rows.get(recording_id)
        if (
            metadata_row is None
            or route_row is None
            or recording_id not in download_links
            or int(metadata_row["person_id"]) != candidate["person_id"]
            or int(metadata_row["environment_id"]) != candidate["environment_id"]
            or float(metadata_row["duration(sec)"])
            != candidate["official_duration_seconds"]
            or download_links[recording_id].get("gopro_360p") != url
            or route_row.get("gopro_360p_url") != url
            or route_row.get("source_group_id") != candidate["source_group_id"]
        ):
            raise NoGoError(
                f"FROZEN_CANDIDATE_REVALIDATION_FAILED:{recording_id}"
            )
        candidates[recording_id] = candidate

    frozen = {
        "schema_version": "av-trace.captaincook4d-wave0-frozen-selection/3.0",
        "task_id": TASK_ID,
        "created_at": utc_now(),
        "frozen_before_task188_network": True,
        "initial_recording_ids": list(FROZEN_INITIAL_IDS),
        "mandatory_recording_ids": ["16_20", "15_29"],
        "conditionally_replaceable_recording_id": "26_22",
        "prospective_fallback_primary_order": list(FALLBACK_PRIMARY_IDS),
        "selection_rule": (
            "Freeze exactly 16_20, 15_29, and 26_22. Do not replace 16_20 "
            "or 15_29. Only if 26_22 fails its bounded official-link range "
            "probe, advance through later Task174 primaries in rank order, "
            "skipping any candidate that would duplicate a selected person "
            "or environment, and stop at the first successful route."
        ),
        "distinctness_required": {
            "person_id": True,
            "environment_id": True,
        },
        "stream": "gopro_360p",
        "candidate_rows": [
            candidates[item]
            for item in (*FROZEN_INITIAL_IDS, *FALLBACK_PRIMARY_IDS)
        ],
        "provided_2026_10_08_range_evidence": {
            "proxy": PROXY,
            "status": 206,
            "declared_totals_from_content_range": PROVEN_TOTALS,
            "fresh_revalidation_required": True,
        },
        "no_annotation_access": True,
        "no_h_tiers": True,
        "public_release_or_redistribution": "NOT_AUTHORIZED",
    }
    return candidates, frozen


def freeze_before_network(frozen: Mapping[str, Any]) -> dict[str, Any]:
    if FROZEN_MANIFEST.exists():
        existing = load_json(FROZEN_MANIFEST)
        comparable_keys = (
            "schema_version",
            "task_id",
            "frozen_before_task188_network",
            "initial_recording_ids",
            "mandatory_recording_ids",
            "conditionally_replaceable_recording_id",
            "prospective_fallback_primary_order",
            "selection_rule",
            "distinctness_required",
            "stream",
            "candidate_rows",
            "provided_2026_10_08_range_evidence",
            "no_annotation_access",
            "no_h_tiers",
            "public_release_or_redistribution",
        )
        if any(existing.get(key) != frozen.get(key) for key in comparable_keys):
            raise NoGoError("EXISTING_TASK188_FROZEN_SELECTION_MISMATCH")
        return existing
    write_restricted_json(FROZEN_MANIFEST, dict(frozen))
    return dict(frozen)


def curl_base(max_time_seconds: int) -> list[str]:
    return [
        "curl",
        "--proxy",
        PROXY,
        "-L",
        "--fail",
        "--silent",
        "--show-error",
        "--connect-timeout",
        str(CONNECT_TIMEOUT_SECONDS),
        "--max-time",
        str(max_time_seconds),
        "--dump-header",
        "-",
    ]


def run_curl_range(
    *,
    url: str,
    start: int,
    end: int | None,
    output: Path,
    max_time_seconds: int,
) -> dict[str, Any]:
    if start < 0 or (end is not None and end < start):
        raise ValueError("invalid byte range")
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.close(descriptor)
    range_text = f"{start}-{'' if end is None else end}"
    command = [
        *curl_base(max_time_seconds),
        "--range",
        range_text,
        "--output",
        str(output),
        url,
    ]
    started = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    elapsed = round(time.monotonic() - started, 6)
    os.chmod(output, 0o600)
    exchanges = parse_header_blocks(completed.stdout, url)
    final = exchanges[-1] if exchanges else None
    return {
        "curl_exit_code": completed.returncode,
        "elapsed_seconds": elapsed,
        "requested_range": f"bytes={range_text}",
        "output_bytes": output.stat().st_size,
        "exchange": {
            "redirect_count": max(0, len(exchanges) - 1),
            "responses": exchanges,
            "final": final,
            "cookie_values_retained": False,
            "ephemeral_capability_retained": False,
        },
        "stderr": sanitize_text(
            completed.stderr.decode("utf-8", errors="replace").strip()
        ),
        "command_template": (
            f"curl --proxy {PROXY} -L --range {range_text} "
            "--output <restricted-part> <official-url>"
        ),
    }


def validate_range_response(
    result: Mapping[str, Any],
    *,
    expected_start: int,
    expected_end: int | None,
    expected_total: int | None,
) -> tuple[int, int, int]:
    final = result.get("exchange", {}).get("final")
    if not final:
        raise AcquisitionError("CURL_RETURNED_NO_PARSEABLE_HTTP_RESPONSE")
    if final["request"]["host"] != "public.boxcloud.com":
        raise AcquisitionError("FINAL_RANGE_HOST_NOT_PUBLIC_BOXCLOUD")
    response_hosts = {
        item["request"]["host"]
        for item in result["exchange"]["responses"]
    }
    if not response_hosts.issubset(ALLOWED_REDIRECT_HOSTS):
        raise NoGoError("UNEXPECTED_REDIRECT_HOST")
    if final["status_code"] != 206:
        raise AcquisitionError(
            f"FINAL_RANGE_STATUS_NOT_206:{final['status_code']}"
        )
    content_type = (final.get("content_type") or "").split(";", 1)[0].lower()
    if content_type != "video/mp4":
        raise NoGoError(f"FINAL_CONTENT_TYPE_NOT_VIDEO_MP4:{content_type}")
    start, end, total = parse_content_range(final.get("content_range"))
    if start != expected_start:
        raise AcquisitionError(
            f"CONTENT_RANGE_START_MISMATCH:{start}!={expected_start}"
        )
    if expected_end is not None and end != expected_end:
        raise AcquisitionError(
            f"CONTENT_RANGE_END_MISMATCH:{end}!={expected_end}"
        )
    if expected_total is not None and total != expected_total:
        raise AcquisitionError(
            f"CONTENT_RANGE_TOTAL_CHANGED:{total}!={expected_total}"
        )
    if total <= 0 or total > MAX_SINGLE_MEDIA_BYTES:
        raise NoGoError(f"CONTENT_RANGE_TOTAL_OUTSIDE_BUDGET:{total}")
    return start, end, total


def safe_unlink(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def probe_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    recording_id = candidate["recording_id"]
    probe_part = LOGS / f".{recording_id}.range-probe.part"
    attempts = []
    for number in range(1, PROBE_ATTEMPTS + 1):
        safe_unlink(probe_part)
        result = run_curl_range(
            url=candidate["official_url"],
            start=0,
            end=0,
            output=probe_part,
            max_time_seconds=PROBE_MAX_TIME_SECONDS,
        )
        result["attempt"] = number
        try:
            _, _, total = validate_range_response(
                result,
                expected_start=0,
                expected_end=0,
                expected_total=None,
            )
            if result["curl_exit_code"] != 0:
                raise AcquisitionError(
                    f"RANGE_PROBE_CURL_EXIT_{result['curl_exit_code']}"
                )
            if probe_part.stat().st_size != 1:
                raise AcquisitionError("RANGE_PROBE_BODY_NOT_EXACTLY_ONE_BYTE")
            proven_total = PROVEN_TOTALS.get(recording_id)
            if proven_total is not None and total != proven_total:
                raise NoGoError(
                    f"PROVEN_CONTENT_RANGE_TOTAL_MISMATCH:"
                    f"{recording_id}:{total}!={proven_total}"
                )
            result["outcome"] = "SUCCESS"
            result["declared_total_bytes"] = total
            attempts.append(result)
            safe_unlink(probe_part)
            return {
                "recording_id": recording_id,
                "status": "RANGE_ROUTE_READY",
                "declared_total_bytes": total,
                "attempts": attempts,
            }
        except NoGoError:
            safe_unlink(probe_part)
            raise
        except AcquisitionError as exc:
            result["outcome"] = "FAILED"
            result["validation_error"] = sanitize_text(str(exc))
            attempts.append(result)
            safe_unlink(probe_part)
            if number < PROBE_ATTEMPTS:
                time.sleep(RETRY_DELAY_SECONDS)
    return {
        "recording_id": recording_id,
        "status": "RANGE_ROUTE_FAILED",
        "declared_total_bytes": None,
        "attempts": attempts,
    }


def write_route_progress(value: Mapping[str, Any]) -> None:
    write_restricted_json(ROUTE_LOG, dict(value))


def select_routes(
    candidates: Mapping[str, Mapping[str, Any]],
    frozen: Mapping[str, Any],
    input_integrity: Mapping[str, Any],
    rights: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    route_log: dict[str, Any] = {
        "schema_version": "av-trace.captaincook4d-wave0-curl-range/3.0",
        "task_id": TASK_ID,
        "created_at": utc_now(),
        "status": "PROBING",
        "proxy": PROXY,
        "required_prefix": f"curl --proxy {PROXY} -L",
        "range_probe": "bytes=0-0",
        "probe_attempt_limit": PROBE_ATTEMPTS,
        "transfer_attempt_limit": TRANSFER_ATTEMPTS,
        "input_integrity": dict(input_integrity),
        "rights_evidence": dict(rights),
        "frozen_selection_path": FROZEN_MANIFEST.relative_to(ROOT).as_posix(),
        "frozen_selection_sha256": sha256_file(FROZEN_MANIFEST),
        "probes": [],
        "selected_recording_ids": [],
        "replacement_events": [],
        "transfers": [],
        "cookie_values_retained": False,
        "ephemeral_capability_retained": False,
    }
    write_route_progress(route_log)

    selected: list[dict[str, Any]] = []
    used_people: set[int] = set()
    used_environments: set[int] = set()
    for recording_id in ("16_20", "15_29"):
        candidate = dict(candidates[recording_id])
        probe = probe_candidate(candidate)
        route_log["probes"].append(probe)
        write_route_progress(route_log)
        if probe["status"] != "RANGE_ROUTE_READY":
            route_log["status"] = f"MANDATORY_ROUTE_FAILED:{recording_id}"
            write_route_progress(route_log)
            raise AcquisitionError(
                f"MANDATORY_ROUTE_FAILED_AFTER_{PROBE_ATTEMPTS}_PROBES:"
                f"{recording_id}"
            )
        candidate["declared_total_bytes"] = probe["declared_total_bytes"]
        selected.append(candidate)
        used_people.add(candidate["person_id"])
        used_environments.add(candidate["environment_id"])

    intended = dict(candidates["26_22"])
    intended_probe = probe_candidate(intended)
    route_log["probes"].append(intended_probe)
    write_route_progress(route_log)
    if intended_probe["status"] == "RANGE_ROUTE_READY":
        intended["declared_total_bytes"] = intended_probe["declared_total_bytes"]
        selected.append(intended)
    else:
        replacement = None
        for recording_id in FALLBACK_PRIMARY_IDS:
            candidate = dict(candidates[recording_id])
            if (
                candidate["person_id"] in used_people
                or candidate["environment_id"] in used_environments
            ):
                route_log["probes"].append(
                    {
                        "recording_id": recording_id,
                        "status": "NOT_PROBED_DISTINCTNESS_CONFLICT",
                        "person_id": candidate["person_id"],
                        "environment_id": candidate["environment_id"],
                    }
                )
                write_route_progress(route_log)
                continue
            probe = probe_candidate(candidate)
            route_log["probes"].append(probe)
            write_route_progress(route_log)
            if probe["status"] == "RANGE_ROUTE_READY":
                candidate["declared_total_bytes"] = probe[
                    "declared_total_bytes"
                ]
                replacement = candidate
                break
        if replacement is None:
            route_log["status"] = "NO_ROUTE_FOR_CONDITIONAL_THIRD_SOURCE"
            write_route_progress(route_log)
            raise AcquisitionError(
                "NO_TASK174_ORDERED_ROUTE_AVAILABLE_TO_REPLACE_26_22"
            )
        selected.append(replacement)
        route_log["replacement_events"].append(
            {
                "failed_recording_id": "26_22",
                "replacement_recording_id": replacement["recording_id"],
                "rule": "Task174 later-primary rank order with distinct person/environment",
            }
        )

    people = {item["person_id"] for item in selected}
    environments = {item["environment_id"] for item in selected}
    if (
        len(selected) != 3
        or len(people) != 3
        or len(environments) != 3
        or selected[0]["recording_id"] != "16_20"
        or selected[1]["recording_id"] != "15_29"
    ):
        raise NoGoError("SELECTED_ROUTE_SET_VIOLATES_FROZEN_CONSTRAINTS")
    aggregate = sum(item["declared_total_bytes"] for item in selected)
    if aggregate > MAX_AGGREGATE_MEDIA_BYTES:
        raise NoGoError("AGGREGATE_MEDIA_BUDGET_EXCEEDED")
    disk = shutil.disk_usage(BASE)
    existing_parts = sum(
        min(
            (BASE / f"{item['recording_id']}_360p.mp4.part").stat().st_size,
            item["declared_total_bytes"],
        )
        if (BASE / f"{item['recording_id']}_360p.mp4.part").exists()
        else 0
        for item in selected
    )
    required = aggregate - existing_parts + FREE_SPACE_MARGIN_BYTES
    if disk.free < required:
        raise AcquisitionError(
            f"INSUFFICIENT_FREE_SPACE:{disk.free}<{required}"
        )
    route_log["status"] = "ROUTES_SELECTED"
    route_log["selected_recording_ids"] = [
        item["recording_id"] for item in selected
    ]
    route_log["selected"] = selected
    route_log["pre_transfer_checks"] = {
        "source_count": len(selected),
        "distinct_person_count": len(people),
        "distinct_environment_count": len(environments),
        "mandatory_16_20_present": True,
        "mandatory_15_29_present": True,
        "aggregate_declared_total_bytes": aggregate,
        "aggregate_budget_bytes": MAX_AGGREGATE_MEDIA_BYTES,
        "free_space_bytes": disk.free,
        "minimum_free_space_required_bytes": required,
    }
    write_route_progress(route_log)
    return selected, route_log


def append_segment(segment: Path, part: Path, expected_offset: int) -> int:
    if part.exists() and part.stat().st_size != expected_offset:
        raise AcquisitionError("PART_SIZE_CHANGED_DURING_TRANSFER")
    if not part.exists():
        descriptor = os.open(part, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
    copied = 0
    with segment.open("rb") as source, part.open("ab") as target:
        while block := source.read(COPY_CHUNK_BYTES):
            target.write(block)
            copied += len(block)
        target.flush()
        os.fsync(target.fileno())
    os.chmod(part, 0o600)
    safe_unlink(segment)
    fsync_directory(part.parent)
    return copied


def download_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    recording_id = candidate["recording_id"]
    total = int(candidate["declared_total_bytes"])
    target = BASE / f"{recording_id}_360p.mp4"
    part = BASE / f"{recording_id}_360p.mp4.part"
    segment = BASE / f".{recording_id}_360p.mp4.range.part"
    safe_unlink(segment)

    if target.exists():
        if target.stat().st_size != total:
            raise NoGoError(f"EXISTING_FINAL_SIZE_MISMATCH:{target.name}")
        os.chmod(target, 0o600)
        digest = hash_file(target)
        return {
            "recording_id": recording_id,
            "status": "EXISTING_EXACT_FILE_REUSED_AND_REHASHED",
            "path": target.relative_to(ROOT).as_posix(),
            "declared_total_bytes": total,
            "final_bytes": digest["bytes"],
            "sha256": digest["sha256"],
            "md5": digest["md5"],
            "attempts": [],
            "atomic_part_promotion": False,
            "mode": oct(stat.S_IMODE(target.stat().st_mode)),
        }
    if part.exists() and part.stat().st_size > total:
        raise NoGoError(f"EXISTING_PART_EXCEEDS_DECLARED_TOTAL:{part.name}")
    if not part.exists():
        descriptor = os.open(part, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
    os.chmod(part, 0o600)

    attempts = []
    for number in range(1, TRANSFER_ATTEMPTS + 1):
        offset = part.stat().st_size
        if offset == total:
            break
        result = run_curl_range(
            url=candidate["official_url"],
            start=offset,
            end=total - 1,
            output=segment,
            max_time_seconds=TRANSFER_MAX_TIME_SECONDS,
        )
        result["attempt"] = number
        result["part_bytes_before"] = offset
        accepted = 0
        try:
            start, promised_end, response_total = validate_range_response(
                result,
                expected_start=offset,
                expected_end=total - 1,
                expected_total=total,
            )
            del start, promised_end, response_total
            segment_bytes = segment.stat().st_size
            if segment_bytes > total - offset:
                raise NoGoError("RANGE_BODY_EXCEEDS_DECLARED_REMAINDER")
            if segment_bytes:
                accepted = append_segment(segment, part, offset)
            else:
                safe_unlink(segment)
            if part.stat().st_size > total:
                raise NoGoError("PART_EXCEEDS_DECLARED_TOTAL_AFTER_APPEND")
            result["outcome"] = (
                "COMPLETE"
                if part.stat().st_size == total
                else "PARTIAL_VALID_RANGE_RETAINED_FOR_RESUME"
            )
        except NoGoError:
            safe_unlink(segment)
            raise
        except AcquisitionError as exc:
            safe_unlink(segment)
            result["outcome"] = "FAILED_NO_BYTES_ACCEPTED"
            result["validation_error"] = sanitize_text(str(exc))
        result["accepted_bytes"] = accepted
        result["part_bytes_after"] = part.stat().st_size
        attempts.append(result)
        if part.stat().st_size == total:
            break
        if number < TRANSFER_ATTEMPTS:
            time.sleep(RETRY_DELAY_SECONDS)

    safe_unlink(segment)
    if part.stat().st_size != total:
        raise AcquisitionError(
            f"TRANSFER_INCOMPLETE_AFTER_{TRANSFER_ATTEMPTS}_ATTEMPTS:"
            f"{recording_id}:{part.stat().st_size}/{total}"
        )
    digest = hash_file(part)
    if digest["bytes"] != total:
        raise AcquisitionError(f"FINAL_PART_HASH_SIZE_MISMATCH:{recording_id}")
    os.chmod(part, 0o600)
    os.replace(part, target)
    os.chmod(target, 0o600)
    fsync_directory(BASE)
    return {
        "recording_id": recording_id,
        "status": "RANGE_RESUME_COMPLETE_AND_ATOMICALLY_PROMOTED",
        "path": target.relative_to(ROOT).as_posix(),
        "declared_total_bytes": total,
        "final_bytes": digest["bytes"],
        "sha256": digest["sha256"],
        "md5": digest["md5"],
        "attempts": attempts,
        "accepted_range_bytes": sum(
            item.get("accepted_bytes", 0) for item in attempts
        ),
        "atomic_part_promotion": True,
        "mode": oct(stat.S_IMODE(target.stat().st_mode)),
    }


def download_selected(
    selected: Iterable[Mapping[str, Any]], route_log: dict[str, Any]
) -> dict[str, Any]:
    results = []
    for candidate in selected:
        print(
            f"Downloading {candidate['recording_id']} "
            f"({candidate['declared_total_bytes']:,} bytes) via range/resume",
            flush=True,
        )
        transfer = download_candidate(candidate)
        results.append(transfer)
        route_log["transfers"] = results
        route_log["status"] = "TRANSFERRING"
        write_route_progress(route_log)
    paths = [ROOT / item["path"] for item in results]
    if len(paths) != 3 or len({path.name for path in paths}) != 3:
        raise NoGoError("EXACTLY_THREE_FINAL_MEDIA_FILES_REQUIRED")
    if sorted(BASE.glob("*.mp4")) != sorted(paths):
        raise NoGoError("UNEXPECTED_MP4_IN_TASK188_RESTRICTED_ROOT")
    if list(BASE.glob("*.mp4.part")):
        raise AcquisitionError("CANONICAL_PART_REMAINS_AFTER_DOWNLOAD")
    route_log["status"] = "TRANSFER_COMPLETE"
    route_log["transfers"] = results
    route_log["aggregate_final_bytes"] = sum(
        item["final_bytes"] for item in results
    )
    route_log["failed_transfers"] = 0
    route_log["incomplete_transfers"] = 0
    write_route_progress(route_log)
    return {
        "schema_version": "av-trace.captaincook4d-wave0-transfer/3.0",
        "task_id": TASK_ID,
        "created_at": utc_now(),
        "proxy": PROXY,
        "required_prefix": f"curl --proxy {PROXY} -L",
        "transfer_mode": "explicit byte-range requests resumed from .part size",
        "source_count": len(results),
        "aggregate_final_bytes": route_log["aggregate_final_bytes"],
        "failed_transfers": 0,
        "incomplete_transfers": 0,
        "sources": results,
    }


def fraction_text(value: Fraction | None) -> str | None:
    return str(value) if value is not None else None


def seconds_from_ts(
    value: int | None, time_base: Fraction | None
) -> float | None:
    if value is None or time_base is None:
        return None
    return float(value * time_base)


def stream_record(stream: av.stream.Stream) -> dict[str, Any]:
    context = stream.codec_context
    codec = getattr(context, "codec", None)
    record: dict[str, Any] = {
        "index": stream.index,
        "id": stream.id,
        "type": stream.type,
        "codec_name": getattr(context, "name", None),
        "codec_long_name": getattr(codec, "long_name", None) if codec else None,
        "profile": getattr(context, "profile", None),
        "time_base": fraction_text(stream.time_base),
        "start_time_ts": stream.start_time,
        "start_time_seconds": seconds_from_ts(stream.start_time, stream.time_base),
        "duration_ts": stream.duration,
        "duration_seconds": seconds_from_ts(stream.duration, stream.time_base),
        "declared_frames": stream.frames,
        "metadata": dict(stream.metadata),
    }
    if stream.type == "video":
        record.update(
            {
                "width": context.width,
                "height": context.height,
                "pixel_format": context.format.name if context.format else None,
                "average_rate": fraction_text(stream.average_rate),
                "base_rate": fraction_text(stream.base_rate),
                "guessed_rate": fraction_text(stream.guessed_rate),
            }
        )
    elif stream.type == "audio":
        record.update(
            {
                "sample_rate_hz": context.sample_rate,
                "channels": context.channels,
                "layout": context.layout.name if context.layout else None,
                "sample_format": context.format.name if context.format else None,
                "frame_size": context.frame_size,
            }
        )
    return record


def frame_timestamp(
    frame: av.frame.Frame, stream: av.stream.Stream
) -> float | None:
    if frame.pts is None:
        return None
    return seconds_from_ts(frame.pts, frame.time_base or stream.time_base)


def bme_probe(path: Path, target_seconds: float) -> dict[str, Any]:
    with av.open(str(path)) as container:
        video = next(iter(container.streams.video), None)
        audio = next(iter(container.streams.audio), None)
        if video is None or audio is None:
            return {
                "target_seconds": target_seconds,
                "video_decoded": False,
                "audio_decoded": False,
                "timestamps_synchronized_within_0_25s": False,
                "error": "VIDEO_OR_AUDIO_STREAM_MISSING",
            }
        seek_seconds = max(0.0, target_seconds - 3.0)
        upper = target_seconds + 3.0
        container.seek(
            int(seek_seconds * av.time_base), any_frame=False, backward=True
        )
        nearest: dict[str, float | None] = {"video": None, "audio": None}
        latest: dict[str, float | None] = {"video": None, "audio": None}
        decoded = {"video": 0, "audio": 0}
        for packet in container.demux(video, audio):
            for frame in packet.decode():
                kind = packet.stream.type
                timestamp = frame_timestamp(frame, packet.stream)
                decoded[kind] += 1
                if timestamp is None:
                    continue
                latest[kind] = timestamp
                current = nearest[kind]
                if current is None or abs(timestamp - target_seconds) < abs(
                    current - target_seconds
                ):
                    nearest[kind] = timestamp
            if all(
                latest[kind] is not None and latest[kind] >= upper
                for kind in ("video", "audio")
            ):
                break
        video_time = nearest["video"]
        audio_time = nearest["audio"]
        delta = (
            abs(video_time - audio_time)
            if video_time is not None and audio_time is not None
            else None
        )
        return {
            "target_seconds": target_seconds,
            "seek_start_seconds": seek_seconds,
            "video_decoded": video_time is not None,
            "audio_decoded": audio_time is not None,
            "video_timestamp_seconds": video_time,
            "audio_timestamp_seconds": audio_time,
            "absolute_av_timestamp_delta_seconds": delta,
            "timestamps_synchronized_within_0_25s": (
                delta is not None and delta <= SYNC_TOLERANCE_SECONDS
            ),
            "decoded_frame_counts_in_probe": decoded,
        }


def full_pyav_decode(path: Path) -> dict[str, Any]:
    started = time.monotonic()
    with av.open(str(path)) as container:
        streams = [
            stream
            for stream in container.streams
            if stream.type in {"video", "audio"}
        ]
        if not any(stream.type == "video" for stream in streams):
            raise AcquisitionError(f"PYAV_VIDEO_STREAM_MISSING:{path.name}")
        if not any(stream.type == "audio" for stream in streams):
            raise AcquisitionError(f"PYAV_AUDIO_STREAM_MISSING:{path.name}")
        for stream in streams:
            if stream.type == "video":
                try:
                    stream.codec_context.thread_type = "AUTO"
                except (AttributeError, RuntimeError):
                    pass
        stats: dict[int, dict[str, Any]] = {}
        for stream in streams:
            stats[stream.index] = {
                "stream_index": stream.index,
                "type": stream.type,
                "declared_frames": stream.frames,
                "decoded_frames": 0,
                "missing_pts_frames": 0,
                "first_pts_seconds": None,
                "last_pts_seconds": None,
                "last_frame_end_seconds": None,
                "timestamps_monotonic": True,
                "stream_duration_seconds": seconds_from_ts(
                    stream.duration, stream.time_base
                ),
            }
        for packet in container.demux(*streams):
            stream = packet.stream
            if stream.index not in stats:
                continue
            for frame in packet.decode():
                item = stats[stream.index]
                item["decoded_frames"] += 1
                timestamp = frame_timestamp(frame, stream)
                if timestamp is None:
                    item["missing_pts_frames"] += 1
                    continue
                previous = item["last_pts_seconds"]
                if previous is not None and timestamp + 1e-9 < previous:
                    item["timestamps_monotonic"] = False
                if item["first_pts_seconds"] is None:
                    item["first_pts_seconds"] = timestamp
                item["last_pts_seconds"] = timestamp
                if stream.type == "audio":
                    duration = (
                        frame.samples / frame.sample_rate
                        if frame.sample_rate and frame.samples
                        else 0.0
                    )
                else:
                    duration = (
                        float(
                            frame.duration
                            * (frame.time_base or stream.time_base)
                        )
                        if frame.duration and (frame.time_base or stream.time_base)
                        else (
                            1.0 / float(stream.average_rate)
                            if stream.average_rate
                            else 0.0
                        )
                    )
                item["last_frame_end_seconds"] = timestamp + duration

        records = list(stats.values())
        for item in records:
            declared = item["declared_frames"]
            item["frame_count_exact"] = (
                declared in (None, 0) or item["decoded_frames"] == declared
            )
            duration = item["stream_duration_seconds"]
            first = item["first_pts_seconds"]
            end = item["last_frame_end_seconds"]
            decoded_span = (
                end - first if first is not None and end is not None else None
            )
            item["decoded_span_seconds"] = decoded_span
            item["decoded_span_matches_stream_duration"] = (
                duration is None
                or decoded_span is not None
                and abs(decoded_span - duration) <= DURATION_TOLERANCE_SECONDS
            )
            item["no_truncation_verified"] = all(
                (
                    item["decoded_frames"] > 0,
                    item["missing_pts_frames"] == 0,
                    item["timestamps_monotonic"],
                    item["frame_count_exact"],
                    item["decoded_span_matches_stream_duration"],
                )
            )
        return {
            "elapsed_seconds": round(time.monotonic() - started, 6),
            "eof_reached": True,
            "streams": records,
            "all_streams_no_truncation_verified": all(
                item["no_truncation_verified"] for item in records
            ),
        }


def opencv_full_decode(path: Path, official_duration: float) -> dict[str, Any]:
    started = time.monotonic()
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        capture.release()
        raise AcquisitionError(f"OPENCV_OPEN_FAILED:{path.name}")
    backend = capture.getBackendName()
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    declared_raw = float(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    declared = int(round(declared_raw)) if declared_raw > 0 else 0
    width = int(round(capture.get(cv2.CAP_PROP_FRAME_WIDTH)))
    height = int(round(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    fourcc_int = int(capture.get(cv2.CAP_PROP_FOURCC))
    fourcc = "".join(
        chr((fourcc_int >> (8 * index)) & 0xFF) for index in range(4)
    )
    grabbed = 0
    while capture.grab():
        grabbed += 1
    eof_confirmed = not capture.grab()
    last_position_msec = float(capture.get(cv2.CAP_PROP_POS_MSEC))
    capture.release()
    duration = grabbed / fps if fps > 0 else None
    frame_count_exact = declared == 0 or grabbed == declared
    duration_delta = (
        abs(duration - official_duration) if duration is not None else None
    )
    return {
        "opened": True,
        "backend": backend,
        "fps": fps,
        "declared_frame_count": declared,
        "grabbed_frame_count": grabbed,
        "frame_count_exact": frame_count_exact,
        "width": width,
        "height": height,
        "fourcc": fourcc,
        "duration_seconds_from_grabbed_frames": duration,
        "official_duration_seconds": official_duration,
        "duration_delta_seconds": duration_delta,
        "duration_matches_official_within_tolerance": (
            duration_delta is not None
            and duration_delta <= DURATION_TOLERANCE_SECONDS
        ),
        "last_position_msec": last_position_msec,
        "eof_confirmed": eof_confirmed,
        "no_truncation_verified": (
            grabbed > 0
            and eof_confirmed
            and frame_count_exact
            and duration_delta is not None
            and duration_delta <= DURATION_TOLERANCE_SECONDS
        ),
        "elapsed_seconds": round(time.monotonic() - started, 6),
    }


def audit_source(
    candidate: Mapping[str, Any], transfer: Mapping[str, Any]
) -> dict[str, Any]:
    path = ROOT / transfer["path"]
    expected_size = int(candidate["declared_total_bytes"])
    if path.stat().st_size != expected_size:
        raise AcquisitionError(f"AUDIT_SIZE_MISMATCH:{path.name}")
    with av.open(str(path)) as container:
        container_duration = (
            float(container.duration / av.time_base)
            if container.duration is not None
            else None
        )
        format_name = container.format.name
        format_long_name = container.format.long_name
        streams = [stream_record(stream) for stream in container.streams]
    videos = [item for item in streams if item["type"] == "video"]
    audios = [item for item in streams if item["type"] == "audio"]
    if not videos or not audios:
        raise AcquisitionError(f"AUDIO_OR_VIDEO_STREAM_MISSING:{path.name}")
    official_duration = float(candidate["official_duration_seconds"])
    video_duration = videos[0]["duration_seconds"]
    container_delta = (
        abs(container_duration - official_duration)
        if container_duration is not None
        else None
    )
    video_delta = (
        abs(video_duration - official_duration)
        if video_duration is not None
        else None
    )
    probe_duration = video_duration or container_duration or official_duration
    targets = {
        "beginning": min(1.0, probe_duration / 4.0),
        "middle": probe_duration / 2.0,
        "end": max(0.0, probe_duration - 2.0),
    }
    bme = {
        name: bme_probe(path, round(target, 6))
        for name, target in targets.items()
    }
    full_pyav = full_pyav_decode(path)
    opencv = opencv_full_decode(path, official_duration)
    checks = {
        "exact_content_range_declared_file_size": path.stat().st_size
        == expected_size,
        "container_open": True,
        "video_stream_present": bool(videos),
        "audio_stream_present": bool(audios),
        "container_duration_matches_official": (
            container_delta is not None
            and container_delta <= DURATION_TOLERANCE_SECONDS
        ),
        "video_duration_matches_official": (
            video_delta is not None
            and video_delta <= DURATION_TOLERANCE_SECONDS
        ),
        "opencv_duration_matches_official": opencv[
            "duration_matches_official_within_tolerance"
        ],
        "beginning_middle_end_video_audio_decode": all(
            row["video_decoded"] and row["audio_decoded"]
            for row in bme.values()
        ),
        "beginning_middle_end_av_synchronization": all(
            row["timestamps_synchronized_within_0_25s"]
            for row in bme.values()
        ),
        "pyav_eof_no_truncation": (
            full_pyav["eof_reached"]
            and full_pyav["all_streams_no_truncation_verified"]
        ),
        "opencv_eof_no_truncation": opencv["no_truncation_verified"],
    }
    return {
        "source_id": candidate["recording_id"],
        "source_group_id": candidate["source_group_id"],
        "person_id": candidate["person_id"],
        "environment_id": candidate["environment_id"],
        "path": transfer["path"],
        "declared_total_bytes_from_content_range": expected_size,
        "sha256": transfer["sha256"],
        "official_metadata_duration_seconds": official_duration,
        "container": {
            "format_name": format_name,
            "format_long_name": format_long_name,
            "duration_seconds": container_duration,
            "duration_delta_from_official_seconds": container_delta,
        },
        "video_stream_duration_seconds": video_duration,
        "video_duration_delta_from_official_seconds": video_delta,
        "streams": streams,
        "beginning_middle_end_decode_and_sync": bme,
        "full_pyav_decode": full_pyav,
        "opencv_full_decode": opencv,
        "checks": checks,
        "technical_audit_passed": all(checks.values()),
    }


def run_audit(
    selected: Iterable[Mapping[str, Any]],
    transfer_log: Mapping[str, Any],
) -> dict[str, Any]:
    candidates = {item["recording_id"]: item for item in selected}
    audited = []
    for transfer in transfer_log["sources"]:
        recording_id = transfer["recording_id"]
        print(f"Full PyAV/OpenCV audit: {recording_id}", flush=True)
        audited.append(audit_source(candidates[recording_id], transfer))
    result = {
        "schema_version": "av-trace.captaincook4d-wave0-technical-audit/3.0",
        "task_id": TASK_ID,
        "created_at": utc_now(),
        "pyav_version": av.__version__,
        "opencv_version": cv2.__version__,
        "duration_tolerance_seconds": DURATION_TOLERANCE_SECONDS,
        "sync_tolerance_seconds": SYNC_TOLERANCE_SECONDS,
        "source_count": len(audited),
        "all_sources_passed": (
            len(audited) == 3
            and all(item["technical_audit_passed"] for item in audited)
        ),
        "sources": audited,
    }
    write_restricted_json(AUDIT_LOG, result)
    return result


def create_hash_log(transfer_log: Mapping[str, Any]) -> dict[str, Any]:
    rows = []
    for transfer in transfer_log["sources"]:
        path = ROOT / transfer["path"]
        observed = hash_file(path)
        if (
            observed["bytes"] != transfer["final_bytes"]
            or observed["sha256"] != transfer["sha256"]
            or observed["md5"] != transfer["md5"]
        ):
            raise AcquisitionError(f"POST_TRANSFER_HASH_MISMATCH:{path.name}")
        rows.append(
            {
                "recording_id": transfer["recording_id"],
                "path": transfer["path"],
                **observed,
            }
        )
    result = {
        "schema_version": "av-trace.captaincook4d-wave0-hashes/3.0",
        "task_id": TASK_ID,
        "created_at": utc_now(),
        "source_count": len(rows),
        "aggregate_bytes": sum(item["bytes"] for item in rows),
        "sources": rows,
    }
    write_restricted_json(HASH_LOG, result)
    return result


def validate_schema(instance: Any, schema_path: Path, label: str) -> None:
    schema = load_json(schema_path)
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(
            schema, format_checker=FormatChecker()
        ).iter_errors(instance),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        detail = "; ".join(
            f"{'.'.join(map(str, error.absolute_path)) or '$'}: {error.message}"
            for error in errors[:10]
        )
        raise AcquisitionError(f"{label}_SCHEMA_INVALID:{detail}")


def semantic_plan_hash(plan: Mapping[str, Any]) -> str:
    envelope = {key: value for key, value in plan.items() if key != "plan_sha256"}
    raw = (
        json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    return "sha256:" + sha256_bytes(raw)


def hash_unit(value: str) -> float:
    integer = int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:16], 16)
    return integer / float(0xFFFFFFFFFFFFFFFF)


def create_prescreen(
    selected: Iterable[Mapping[str, Any]],
    hashes: Mapping[str, Any],
    audit: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    candidates = {item["recording_id"]: item for item in selected}
    hash_rows = {item["recording_id"]: item for item in hashes["sources"]}
    audit_rows = {item["source_id"]: item for item in audit["sources"]}
    sources = []
    for recording_id in sorted(candidates):
        duration = audit_rows[recording_id]["video_stream_duration_seconds"]
        if duration is None:
            raise AcquisitionError(f"PRESCREEN_DURATION_MISSING:{recording_id}")
        sources.append(
            {
                "source_id": recording_id,
                "source_group_id": candidates[recording_id]["source_group_id"],
                "duration_s": duration,
                "source_content_sha256": (
                    f"sha256:{hash_rows[recording_id]['sha256']}"
                ),
                "adapter_reference": (
                    f"restricted-file://{recording_id}_360p.mp4"
                ),
                "media_included": False,
                "semantic_metadata_included": False,
            }
        )
    inventory = {
        "schema_version": "1.0.0",
        "record_type": "semantic_av_source_prescreen_inventory",
        "inventory_id": (
            "captaincook4d-wave0-task188-semantic-prescreen-inventory-v3"
        ),
        "inventory_status": "FROZEN_NONSEMANTIC_SOURCE_INVENTORY",
        "sources": sources,
        "notes": (
            "Task188/Task153 nonsemantic source inventory only. No humans, "
            "annotations, semantic labels, modality-necessity decisions, or "
            "H tiers."
        ),
    }
    validate_schema(inventory, INVENTORY_SCHEMA, "TASK153_INVENTORY")
    write_restricted_json(INVENTORY, inventory)

    plan_id = "captaincook4d-wave0-task188-semantic-prescreen-plan-v3"
    seed = "AVTRACE-CAPTAINCOOK4D-WAVE0-TASK188-TASK153-V3"
    interval = 12.0
    quota = 3
    samples = []
    sequence = 1
    for source in sorted(sources, key=lambda item: item["source_id"]):
        bin_width = source["duration_s"] / quota
        if interval > bin_width:
            raise AcquisitionError("TASK153_INTERVAL_DOES_NOT_FIT")
        for index in range(quota):
            slack = bin_width - interval
            start = round(
                index * bin_width
                + hash_unit(f"{seed}|{source['source_id']}|{index}") * slack,
                3,
            )
            samples.append(
                {
                    "sample_id": f"{plan_id}.sample-{sequence:04d}",
                    "source_id": source["source_id"],
                    "source_group_id": source["source_group_id"],
                    "source_content_sha256": source["source_content_sha256"],
                    "start_s": start,
                    "end_s": round(start + interval, 3),
                    "adapter_request": {
                        "adapter_reference": source["adapter_reference"],
                        "extract_media": False,
                    },
                }
            )
            sequence += 1
    plan = {
        "schema_version": "1.0.0",
        "record_type": "semantic_av_source_prescreen_plan",
        "plan_id": plan_id,
        "created_at": utc_now(),
        "inventory_id": inventory["inventory_id"],
        "inventory_sha256": f"sha256:{sha256_file(INVENTORY)}",
        "seed": seed,
        "algorithm": "source-uniform-temporal-bin-sha256-jitter-v1",
        "sample_count": len(samples),
        "interval_duration_s": interval,
        "source_uniformity": {
            "source_count": len(sources),
            "minimum_per_source": quota,
            "maximum_per_source": quota,
        },
        "samples": samples,
        "plan_sha256": "",
        "semantic_labels_present": False,
    }
    plan["plan_sha256"] = semantic_plan_hash(plan)
    validate_schema(plan, PLAN_SCHEMA, "TASK153_PLAN")
    if plan["plan_sha256"] != semantic_plan_hash(plan):
        raise AcquisitionError("TASK153_PLAN_HASH_MISMATCH")
    write_restricted_json(PLAN, plan)
    return inventory, plan


def enforce_restricted_permissions() -> None:
    for directory in [BASE, *[item for item in BASE.rglob("*") if item.is_dir()]]:
        directory.chmod(0o700)
    for path in BASE.rglob("*"):
        if path.is_file() and path != LOCK:
            path.chmod(0o600)


def assert_no_ephemeral_capability_leak() -> None:
    patterns = (
        re.compile(rb"public\.boxcloud\.com/d/1/(?!\[REDACTED_)"),
        re.compile(rb'"set-cookie"\s*:\s*"(?!\[REDACTED\])', re.I),
    )
    for path in BASE.rglob("*"):
        if not path.is_file() or path.suffix == ".mp4" or path.name.endswith(
            ".mp4.part"
        ):
            continue
        raw = path.read_bytes()
        for pattern in patterns:
            if pattern.search(raw):
                raise NoGoError(
                    f"UNREDACTED_EPHEMERAL_OR_COOKIE_VALUE:{path.relative_to(ROOT)}"
                )


def create_manifests(
    selected: list[Mapping[str, Any]],
    route_log: Mapping[str, Any],
    transfer_log: Mapping[str, Any],
    hashes: Mapping[str, Any],
    audit: Mapping[str, Any],
    rights: Mapping[str, Any],
    inventory: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    candidates = {item["recording_id"]: item for item in selected}
    transfers = {item["recording_id"]: item for item in transfer_log["sources"]}
    hash_rows = {item["recording_id"]: item for item in hashes["sources"]}
    audit_rows = {item["source_id"]: item for item in audit["sources"]}
    source_manifests = []
    for recording_id in [item["recording_id"] for item in selected]:
        candidate = candidates[recording_id]
        source_manifest = {
            "schema_version": "3.0",
            "record_type": "captaincook4d_wave0_source_manifest",
            "task_id": TASK_ID,
            "generated_at_utc": utc_now(),
            "dataset": "CaptainCook4D",
            "source_id": recording_id,
            "source_group_id": candidate["source_group_id"],
            "person_id": candidate["person_id"],
            "environment_id": candidate["environment_id"],
            "stream": "gopro_360p",
            "official_metadata_duration_seconds": candidate[
                "official_duration_seconds"
            ],
            "official_entrypoint": candidate["official_url"],
            "declared_total_bytes_from_content_range": candidate[
                "declared_total_bytes"
            ],
            "media": {
                "path": transfers[recording_id]["path"],
                **{
                    key: hash_rows[recording_id][key]
                    for key in ("bytes", "md5", "sha256")
                },
                "mode": transfers[recording_id]["mode"],
            },
            "route": {
                "proxy": PROXY,
                "curl_redirects": True,
                "range_resume": True,
                "cookie_values_retained": False,
                "ephemeral_capability_retained": False,
            },
            "technical_validation": audit_rows[recording_id],
            "rights_and_use": dict(rights),
            "human_semantic_review_performed": False,
            "annotations_accessed_or_produced": False,
            "h_tiers_assigned": False,
            "public_release_or_redistribution": "NOT_AUTHORIZED",
        }
        path = MANIFESTS / f"{recording_id}.source_manifest.json"
        write_restricted_json(path, source_manifest)
        source_manifests.append(
            {
                "recording_id": recording_id,
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": sha256_file(path),
            }
        )

    enforce_restricted_permissions()
    all_files_0600 = all(
        stat.S_IMODE(path.stat().st_mode) == 0o600
        for path in BASE.rglob("*")
        if path.is_file() and path != LOCK
    )
    all_dirs_0700 = all(
        stat.S_IMODE(path.stat().st_mode) == 0o700
        for path in [BASE, *[item for item in BASE.rglob("*") if item.is_dir()]]
    )
    ids = [item["recording_id"] for item in selected]
    root = {
        "schema_version": "3.0",
        "record_type": "captaincook4d_wave0_acquisition_manifest",
        "task_id": TASK_ID,
        "generated_at_utc": utc_now(),
        "decision": TOKEN_READY,
        "scope": (
            "Restricted internal exact acquisition and full technical "
            "validation of three Task174-bound CaptainCook4D GoPro 360p MP4s."
        ),
        "source_count": len(selected),
        "selected_recording_ids": ids,
        "initial_frozen_recording_ids": list(FROZEN_INITIAL_IDS),
        "replacement_events": route_log["replacement_events"],
        "distinct_person_count": len({item["person_id"] for item in selected}),
        "distinct_environment_count": len(
            {item["environment_id"] for item in selected}
        ),
        "aggregate_media_bytes": hashes["aggregate_bytes"],
        "aggregate_official_duration_seconds": sum(
            item["official_duration_seconds"] for item in selected
        ),
        "frozen_selection": {
            "path": FROZEN_MANIFEST.relative_to(ROOT).as_posix(),
            "sha256": sha256_file(FROZEN_MANIFEST),
        },
        "curl_range_acquisition": {
            "path": ROUTE_LOG.relative_to(ROOT).as_posix(),
            "sha256": sha256_file(ROUTE_LOG),
            "proxy": PROXY,
            "required_prefix": f"curl --proxy {PROXY} -L",
            "exact_total_source": "Content-Range",
            "range_resume": True,
            "part_atomic_promotion": True,
            "cookie_values_retained": False,
            "ephemeral_capability_retained": False,
        },
        "rights_and_use": dict(rights),
        "hashes": {
            "path": HASH_LOG.relative_to(ROOT).as_posix(),
            "sha256": sha256_file(HASH_LOG),
        },
        "technical_audit": {
            "path": AUDIT_LOG.relative_to(ROOT).as_posix(),
            "sha256": sha256_file(AUDIT_LOG),
            "pyav_version": audit["pyav_version"],
            "opencv_version": audit["opencv_version"],
            "all_sources_passed": audit["all_sources_passed"],
        },
        "task153_prescreen": {
            "inventory_path": INVENTORY.relative_to(ROOT).as_posix(),
            "inventory_sha256": f"sha256:{sha256_file(INVENTORY)}",
            "plan_path": PLAN.relative_to(ROOT).as_posix(),
            "plan_sha256": f"sha256:{sha256_file(PLAN)}",
            "sample_count": plan["sample_count"],
            "human_review_performed": False,
            "annotations_produced": False,
            "h_tiers_assigned": False,
        },
        "source_manifests": source_manifests,
        "sources": [
            {
                "source_id": item["recording_id"],
                "source_group_id": item["source_group_id"],
                "person_id": item["person_id"],
                "environment_id": item["environment_id"],
                "official_duration_seconds": item[
                    "official_duration_seconds"
                ],
                "declared_total_bytes_from_content_range": item[
                    "declared_total_bytes"
                ],
                "media": hash_rows[item["recording_id"]],
                "technical_audit_passed": audit_rows[item["recording_id"]][
                    "technical_audit_passed"
                ],
            }
            for item in selected
        ],
        "readiness_checks": {
            "exactly_three_sources": len(selected) == 3,
            "mandatory_16_20_present": "16_20" in ids,
            "mandatory_15_29_present": "15_29" in ids,
            "26_22_or_prospective_task174_replacement_present": ids[2]
            in {"26_22", *FALLBACK_PRIMARY_IDS},
            "three_distinct_people": len(
                {item["person_id"] for item in selected}
            )
            == 3,
            "three_distinct_environments": len(
                {item["environment_id"] for item in selected}
            )
            == 3,
            "all_gopro_360p": True,
            "all_exact_content_range_sizes_and_sha256_verified": True,
            "all_technical_audits_passed": audit["all_sources_passed"],
            "all_restricted_files_mode_0600": all_files_0600,
            "all_restricted_directories_mode_0700": all_dirs_0700,
            "no_unredacted_ephemeral_final_urls": True,
            "no_cookie_values_retained": True,
            "no_annotations": True,
            "no_h_tiers": True,
            "no_human_review": True,
            "public_release_not_authorized": True,
        },
        "explicit_non_claims": [
            "No annotation file was accessed or produced.",
            "No human semantic review or decision was performed.",
            "No H tier or modality-necessity label was assigned.",
            "No public release or redistribution is authorized.",
        ],
    }
    if not all(root["readiness_checks"].values()):
        raise AcquisitionError("ROOT_MANIFEST_READINESS_CHECK_FAILED")
    write_restricted_json(ROOT_MANIFEST, root)
    return root


def stream_summary(source: Mapping[str, Any]) -> tuple[str, str]:
    video = next(item for item in source["streams"] if item["type"] == "video")
    audio = next(item for item in source["streams"] if item["type"] == "audio")
    video_text = (
        f"{video['codec_name']} {video.get('profile') or ''}, "
        f"{video.get('width')}x{video.get('height')}, "
        f"time base {video['time_base']}"
    ).replace("  ", " ")
    audio_text = (
        f"{audio['codec_name']} {audio.get('profile') or ''}, "
        f"{audio.get('channels')} ch/{audio.get('layout')}, "
        f"{audio.get('sample_rate_hz')} Hz, "
        f"time base {audio['time_base']}"
    ).replace("  ", " ")
    return video_text, audio_text


def create_review_and_result(
    selected: list[Mapping[str, Any]],
    route_log: Mapping[str, Any],
    hashes: Mapping[str, Any],
    audit: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> None:
    hash_rows = {item["recording_id"]: item for item in hashes["sources"]}
    audit_rows = {item["source_id"]: item for item in audit["sources"]}
    rows = []
    details = []
    for candidate in selected:
        recording_id = candidate["recording_id"]
        digest = hash_rows[recording_id]
        source = audit_rows[recording_id]
        rows.append(
            f"| `{recording_id}` | {candidate['person_id']} | "
            f"{candidate['environment_id']} | `{candidate['source_group_id']}` | "
            f"{candidate['official_duration_seconds']:.2f} | "
            f"{digest['bytes']:,} | `{digest['sha256']}` |"
        )
        video, audio = stream_summary(source)
        bme = source["beginning_middle_end_decode_and_sync"]
        deltas = ", ".join(
            f"{name}={value['absolute_av_timestamp_delta_seconds']:.6f}s"
            for name, value in bme.items()
        )
        decode_counts = ", ".join(
            f"{item['type']}={item['decoded_frames']}"
            for item in source["full_pyav_decode"]["streams"]
        )
        details.append(
            "\n".join(
                [
                    f"### `{recording_id}`",
                    "",
                    f"- PyAV container duration: "
                    f"`{source['container']['duration_seconds']:.6f}` s; "
                    f"video duration: "
                    f"`{source['video_stream_duration_seconds']:.6f}` s; "
                    f"official: `{source['official_metadata_duration_seconds']:.2f}` s.",
                    f"- Video: {video}.",
                    f"- Audio: {audio}.",
                    f"- B/M/E nearest A/V timestamp deltas: {deltas}.",
                    f"- Full PyAV EOF decode counts: {decode_counts}; no truncation passed.",
                    f"- Full OpenCV EOF traversal: "
                    f"{source['opencv_full_decode']['grabbed_frame_count']} frames; "
                    f"duration "
                    f"`{source['opencv_full_decode']['duration_seconds_from_grabbed_frames']:.6f}` s; "
                    "no truncation passed.",
                ]
            )
        )
    replacement = route_log["replacement_events"]
    replacement_text = (
        "The intended `26_22` route passed, so no replacement was used."
        if not replacement
        else (
            "`26_22` failed its bounded range route probe and was replaced "
            "prospectively under Task174 order: "
            + json.dumps(replacement, sort_keys=True)
            + "."
        )
    )
    review = f"""# CaptainCook4D Wave-0 exact acquisition v3

**Task:** 188  
**Date:** {TASK_DATE}  
**Decision:** `{TOKEN_READY}`

## Frozen scope

Before Task188 network access, the acquisition froze exactly `16_20`,
`15_29`, and `26_22`. The first two were mandatory. Only `26_22` could be
replaced, by advancing through later Task174 primaries in rank order while
preserving distinct person and environment IDs. {replacement_text}

Only official GoPro 360p MP4 links were requested. No annotations, HoloLens
streams, 4K streams, transcripts, features, clips, or Ray jobs were touched.

## Curl range/resume acquisition

Every network request used the required prefix
`curl --proxy {PROXY} -L`. Each route was first revalidated with the bounded
range `bytes=0-0`; the exact object total came from the final HTTP 206
`Content-Range`. The fresh totals for `16_20` and `15_29` matched the explicit
October 8, 2026 evidence: 230,486,870 and 181,454,428 bytes.

Transfers requested the remaining byte interval from the current `.part`
length. Valid partial response bytes were fsynced into the same-directory
`.part`, and exact completed files were promoted with atomic `os.replace`.
Restricted files are mode `0600`; restricted directories are mode `0700`.
Cookie values and unredacted ephemeral BoxCloud capabilities were not stored.

| Recording | Person | Environment | Source group | Official duration (s) | Bytes | SHA-256 |
| --- | ---: | ---: | --- | ---: | ---: | --- |
{chr(10).join(rows)}

## Full technical validation

PyAV `{audit['pyav_version']}` and OpenCV `{audit['opencv_version']}` were
used. The duration tolerance was {DURATION_TOLERANCE_SECONDS:.1f} second and
the B/M/E A/V timestamp synchronization tolerance was
{SYNC_TOLERANCE_SECONDS:.2f} second.

{chr(10).join(details)}

All three sources passed exact Content-Range size and SHA-256 verification,
PyAV container/video duration comparison with official metadata, video/audio
stream codec and time-base inspection, beginning/middle/end A/V decode and
synchronization, complete PyAV decoding through EOF, complete OpenCV traversal
through EOF, and no-truncation checks.

## Task153 prescreen

- Inventory: `{INVENTORY.relative_to(ROOT).as_posix()}`
- Plan: `{PLAN.relative_to(ROOT).as_posix()}`
- Algorithm: `source-uniform-temporal-bin-sha256-jitter-v1`
- Plan: {plan['sample_count']} unlabeled 12-second intervals, three per source
- `extract_media=false`; `semantic_labels_present=false`
- Humans: none
- Annotations/H tiers/public release: none/not authorized

## Outputs

- `{ROOT_MANIFEST.relative_to(ROOT).as_posix()}`
- `{FROZEN_MANIFEST.relative_to(ROOT).as_posix()}`
- `{ROUTE_LOG.relative_to(ROOT).as_posix()}`
- `{HASH_LOG.relative_to(ROOT).as_posix()}`
- `{AUDIT_LOG.relative_to(ROOT).as_posix()}`
- `{INVENTORY.relative_to(ROOT).as_posix()}`
- `{PLAN.relative_to(ROOT).as_posix()}`
- three source manifests under `{MANIFESTS.relative_to(ROOT).as_posix()}/`
- exactly three MP4s under `{BASE.relative_to(ROOT).as_posix()}/`

`{TOKEN_READY}`
"""
    write_public_text(REVIEW, review)

    lines = [
        "Task188 CaptainCook4D Wave-0 exact acquisition v3",
        f"Date: {TASK_DATE}",
        f"Decision: {TOKEN_READY}",
        "",
        "FROZEN SCOPE",
        "- Initial IDs: 16_20, 15_29, 26_22.",
        "- 16_20 and 15_29 mandatory; only 26_22 prospectively replaceable.",
        f"- Replacement events: {json.dumps(replacement, sort_keys=True)}",
        "- Three distinct people and three distinct environments.",
        "",
        "TRANSFER",
        f"- Required prefix: curl --proxy {PROXY} -L",
        "- HTTP 206 bounded probes; exact totals from Content-Range.",
        "- Range resumed from .part length; fsync and atomic rename.",
        "- Restricted files/directories: 0600/0700.",
        "- Unredacted ephemeral final URLs and cookie values retained: no.",
        "",
        "SOURCES",
    ]
    for candidate in selected:
        digest = hash_rows[candidate["recording_id"]]
        lines.extend(
            [
                f"- {candidate['recording_id']}: person "
                f"{candidate['person_id']}, environment "
                f"{candidate['environment_id']}, "
                f"{candidate['official_duration_seconds']:.2f} s, "
                f"{digest['bytes']:,} bytes",
                f"  SHA-256: {digest['sha256']}",
            ]
        )
    lines.extend(
        [
            "",
            "TECHNICAL AUDIT",
            f"- PyAV {audit['pyav_version']}; OpenCV {audit['opencv_version']}.",
            "- Official-duration, streams/codecs/timebases, B/M/E decode/sync,",
            "  complete PyAV/OpenCV EOF, and no-truncation: PASS for 3/3.",
            "",
            "TASK153 / BOUNDARY",
            f"- {plan['sample_count']} deterministic unlabeled intervals; no humans.",
            "- No annotations, H tiers, public release, or Ray-job changes.",
            "",
            "REPORTS / MANIFEST",
            f"- {REVIEW.relative_to(ROOT).as_posix()}",
            f"- {ROOT_MANIFEST.relative_to(ROOT).as_posix()}",
            f"- {ROUTE_LOG.relative_to(ROOT).as_posix()}",
            f"- {AUDIT_LOG.relative_to(ROOT).as_posix()}",
            "",
            TOKEN_READY,
            "",
        ]
    )
    write_public_text(RESULT, "\n".join(lines))


def write_failure(
    exc: BaseException,
    *,
    token: str,
    selected: list[Mapping[str, Any]] | None = None,
) -> None:
    secure_directories()
    failure = {
        "schema_version": "av-trace.captaincook4d-wave0-failure/3.0",
        "task_id": TASK_ID,
        "created_at": utc_now(),
        "decision": token,
        "error_type": type(exc).__name__,
        "error": sanitize_text(str(exc)),
        "selected_recording_ids": [
            item["recording_id"] for item in (selected or [])
        ],
        "partial_files_preserved_for_range_resume": [
            {
                "path": path.relative_to(ROOT).as_posix(),
                "bytes": path.stat().st_size,
            }
            for path in sorted(BASE.glob("*.mp4.part"))
        ],
        "annotations_accessed_or_produced": False,
        "h_tiers_assigned": False,
        "human_review_performed": False,
        "public_release_or_redistribution": "NOT_AUTHORIZED",
    }
    write_restricted_json(FAILURE_LOG, failure)
    manifest = {
        "schema_version": "3.0",
        "record_type": "captaincook4d_wave0_acquisition_manifest",
        "task_id": TASK_ID,
        "generated_at_utc": utc_now(),
        "decision": token,
        "status": "FAILED_OR_INCOMPLETE",
        "failure_path": FAILURE_LOG.relative_to(ROOT).as_posix(),
        "failure_sha256": sha256_file(FAILURE_LOG),
        "frozen_selection_path": (
            FROZEN_MANIFEST.relative_to(ROOT).as_posix()
            if FROZEN_MANIFEST.exists()
            else None
        ),
        "range_log_path": (
            ROUTE_LOG.relative_to(ROOT).as_posix()
            if ROUTE_LOG.exists()
            else None
        ),
        "selected_recording_ids": failure["selected_recording_ids"],
        "no_annotations": True,
        "no_h_tiers": True,
        "no_human_review": True,
        "public_release_not_authorized": True,
    }
    write_restricted_json(ROOT_MANIFEST, manifest)
    summary = f"""# CaptainCook4D Wave-0 exact acquisition v3

**Task:** 188  
**Date:** {TASK_DATE}  
**Decision:** `{token}`

Task188 did not reach READY.

- Error type: `{type(exc).__name__}`
- Error: `{sanitize_text(str(exc))}`
- Selected routes at failure: `{failure['selected_recording_ids']}`
- Canonical `.part` files were preserved for bounded range resume.
- No annotations, human review, H tiers, public release, or Ray jobs.

- Failure record: `{FAILURE_LOG.relative_to(ROOT).as_posix()}`
- Manifest: `{ROOT_MANIFEST.relative_to(ROOT).as_posix()}`

`{token}`
"""
    write_public_text(REVIEW, summary)
    write_public_text(
        RESULT,
        "\n".join(
            [
                "Task188 CaptainCook4D Wave-0 exact acquisition v3",
                f"Date: {TASK_DATE}",
                f"Decision: {token}",
                f"Error: {sanitize_text(str(exc))}",
                "No annotations, humans, H tiers, public release, or Ray jobs.",
                token,
                "",
            ]
        ),
    )
    enforce_restricted_permissions()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run frozen range probes, acquisition, audits, and reports.",
    )
    parser.add_argument(
        "--validate-local",
        action="store_true",
        help="Validate frozen inputs and emit the pre-network freeze only.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.execute == args.validate_local:
        print("Choose exactly one of --execute or --validate-local", file=sys.stderr)
        return 2
    os.umask(0o077)
    secure_directories()
    acquire_lock()
    selected: list[Mapping[str, Any]] = []
    try:
        input_integrity = verify_input_integrity()
        rights = verify_rights_evidence()
        candidates, frozen = load_candidates()
        frozen["input_integrity"] = input_integrity
        frozen["rights_evidence"] = rights
        frozen = freeze_before_network(frozen)
        enforce_restricted_permissions()
        if args.validate_local:
            print("CAPTAINCOOK4D_WAVE0_LOCAL_FREEZE_READY")
            return 0

        selected, route_log = select_routes(
            candidates, frozen, input_integrity, rights
        )
        transfer_log = download_selected(selected, route_log)
        hashes = create_hash_log(transfer_log)
        audit = run_audit(selected, transfer_log)
        if not audit["all_sources_passed"]:
            raise AcquisitionError("ONE_OR_MORE_FULL_TECHNICAL_AUDITS_FAILED")
        inventory, plan = create_prescreen(selected, hashes, audit)
        del inventory
        enforce_restricted_permissions()
        assert_no_ephemeral_capability_leak()
        create_manifests(
            selected,
            route_log,
            transfer_log,
            hashes,
            audit,
            rights,
            load_json(INVENTORY),
            plan,
        )
        enforce_restricted_permissions()
        assert_no_ephemeral_capability_leak()
        create_review_and_result(selected, route_log, hashes, audit, plan)
        print(TOKEN_READY)
        return 0
    except BaseException as exc:
        token = TOKEN_NO_GO if isinstance(exc, NoGoError) else TOKEN_REPAIR
        write_failure(exc, token=token, selected=selected)
        print(f"{token}: {sanitize_text(str(exc))}")
        return 3 if token == TOKEN_NO_GO else 2
    finally:
        release_lock()


if __name__ == "__main__":
    raise SystemExit(main())
