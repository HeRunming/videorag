#!/usr/bin/env python3
"""Repair, acquire, and technically validate CaptainCook4D Wave-0.

The network path intentionally preserves the official downloader's request
shape: ``requests.get(url, stream=True)`` with Requests-default redirect and
redirect-cookie handling.  This task adds only an explicit approved proxy,
longer bounded connect/read timeouts, validation, retries, secure permissions,
hashing, and same-directory ``.part`` atomic promotion.

No annotation endpoint or non-GoPro stream is requested.
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
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import parse_qsl, urlsplit, urlunsplit

import av
import cv2
import requests
from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
TASK_ID = 186
TASK_DATE = "2026-10-09"
PROXY = "https://proxy.example.invalid:3128"
MAX_RETRIES = 5
RETRY_DELAY_SECONDS = 5
CONNECT_TIMEOUT_SECONDS = 600
READ_TIMEOUT_SECONDS = 1800
CHUNK_BYTES = 1024 * 1024
MAX_SELECTED_MEDIA_BYTES = 1024 * 1024 * 1024
MAX_SINGLE_MEDIA_BYTES = 512 * 1024 * 1024
MIN_FREE_SPACE_MARGIN_BYTES = 256 * 1024 * 1024
DURATION_TOLERANCE_SECONDS = 0.5
SYNC_TOLERANCE_SECONDS = 0.25

BASE = ROOT / "data/restricted/captaincook4d_wave0_sources_v1"
LOGS = BASE / "logs"
MANIFESTS = BASE / "manifests"
PRESCREEN = BASE / "prescreen"
LOCK = BASE / ".task186.lock"
PREFLIGHT_LOG = LOGS / "task186_route_preflight.json"
TRANSFER_LOG = LOGS / "task186_transfer_log.json"
HASH_LOG = LOGS / "task186_final_hashes.json"
AUDIT_LOG = LOGS / "task186_technical_audit.json"
ROOT_MANIFEST = MANIFESTS / "captaincook4d_wave0_acquisition_manifest.json"
INVENTORY = PRESCREEN / "captaincook4d_wave0_semantic_source_prescreen_inventory.json"
PLAN = PRESCREEN / "captaincook4d_wave0_semantic_source_prescreen_plan.json"
REVIEW = ROOT / "docs/review/captaincook4d_wave0_exact_acquisition.md"
RESULT = (
    ROOT
    / "orchestration/results/186_captaincook4d_wave0_acquisition_repair.txt"
)

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
DOWNLOADER_SEMANTICS = (
    ROOT
    / "data/source_recon/captaincook4d_access_v3/derived"
    / "official_downloader_semantics_v3.json"
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
    "downloader_semantics": {
        "path": DOWNLOADER_SEMANTICS,
        "bytes": 3168,
        "sha256": "e81cfe87d11c953f03eb4e1b4f00a5f8a6eb98631590b28b88e9ccc386e18096",
    },
}

# This primary-only order was frozen before any Task186 network request.  The
# first three are the intended sample.  Later Task174-frozen primaries are the
# prospective route-replacement order.  Task174's two same-person replacement
# groups are intentionally excluded because Task186 requires all three records
# to come from the frozen primary pool.
CANDIDATE_ORDER: tuple[dict[str, Any], ...] = (
    {
        "recording_id": "16_20",
        "role": "PRIMARY",
        "rank": 1,
        "person_id": 1,
        "environment_id": 8,
        "source_group_id": "cc4d_p01_e08",
        "duration_seconds": 1930.90,
        "url": "https://utdallas.box.com/shared/static/btsy8iyqoztk0yt3006dqb4n5yfzj8rh.mp4",
        "mandatory": True,
    },
    {
        "recording_id": "15_29",
        "role": "PRIMARY",
        "rank": 2,
        "person_id": 2,
        "environment_id": 2,
        "source_group_id": "cc4d_p02_e02",
        "duration_seconds": 1292.82,
        "url": "https://utdallas.box.com/shared/static/dct3r6mjvfd7ehpl1leagu34fbxc2sj9.mp4",
        "mandatory": False,
    },
    {
        "recording_id": "26_22",
        "role": "PRIMARY",
        "rank": 3,
        "person_id": 3,
        "environment_id": 3,
        "source_group_id": "cc4d_p03_e03",
        "duration_seconds": 1324.22,
        "url": "https://utdallas.box.com/shared/static/u1qqdarxgxh7auz5amo8b2shyeanv2n8.mp4",
        "mandatory": False,
    },
    {
        "recording_id": "25_1",
        "role": "PRIMARY",
        "rank": 4,
        "person_id": 4,
        "environment_id": 6,
        "source_group_id": "cc4d_p04_e06",
        "duration_seconds": 1761.19,
        "url": "https://utdallas.box.com/shared/static/z08mhzff548ae3iinhp7dd5r8410m1lz.mp4",
        "mandatory": False,
    },
    {
        "recording_id": "25_109",
        "role": "PRIMARY",
        "rank": 5,
        "person_id": 5,
        "environment_id": 7,
        "source_group_id": "cc4d_p05_e07",
        "duration_seconds": 2126.96,
        "url": "https://utdallas.box.com/shared/static/qiu0plhm3ixqcfgu02qy9kmlp5tre6p2.mp4",
        "mandatory": False,
    },
    {
        "recording_id": "2_13",
        "role": "PRIMARY",
        "rank": 6,
        "person_id": 6,
        "environment_id": 1,
        "source_group_id": "cc4d_p06_e01",
        "duration_seconds": 1325.42,
        "url": "https://utdallas.box.com/shared/static/ga93bfhusmiyu2sm2i2955ndsf4dkvop.mp4",
        "mandatory": False,
    },
    {
        "recording_id": "16_23",
        "role": "PRIMARY",
        "rank": 7,
        "person_id": 7,
        "environment_id": 2,
        "source_group_id": "cc4d_p07_e02",
        "duration_seconds": 1290.49,
        "url": "https://utdallas.box.com/shared/static/eyp18sbqnxjydvlqkpcdxn0x8qh9uq0z.mp4",
        "mandatory": False,
    },
    {
        "recording_id": "23_19",
        "role": "PRIMARY",
        "rank": 8,
        "person_id": 8,
        "environment_id": 5,
        "source_group_id": "cc4d_p08_e05",
        "duration_seconds": 1803.03,
        "url": "https://utdallas.box.com/shared/static/hil67e0biwlix4gh8i953qstsp1eghp3.mp4",
        "mandatory": False,
    },
)

INITIAL_RECORDING_IDS = ("16_20", "15_29", "26_22")
PROSPECTIVE_REPLACEMENT_IDS = ("25_1", "25_109", "2_13", "16_23", "23_19")
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
URL_RE = re.compile(r"https?://[^\\s'\\\"]+")


class AcquisitionError(RuntimeError):
    """Fail-closed Task186 error."""


class RouteUnavailable(AcquisitionError):
    """A frozen route did not resolve after the bounded retry schedule."""

    def __init__(self, recording_id: str, attempts: list[dict[str, Any]]) -> None:
        super().__init__(
            f"ROUTE_UNAVAILABLE_AFTER_{MAX_RETRIES}_ATTEMPTS:{recording_id}"
        )
        self.recording_id = recording_id
        self.attempts = attempts


@dataclass(frozen=True)
class RouteResolution:
    candidate: dict[str, Any]
    content_length_bytes: int
    content_type: str
    content_disposition_filename: str
    accept_ranges: str | None
    exchange: dict[str, Any]
    attempts: list[dict[str, Any]]


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


def hash_file(path: Path) -> dict[str, Any]:
    sha256 = hashlib.sha256()
    md5 = hashlib.md5(usedforsecurity=False)
    count = 0
    with path.open("rb") as handle:
        while block := handle.read(4 * 1024 * 1024):
            count += len(block)
            sha256.update(block)
            md5.update(block)
    return {"bytes": count, "sha256": sha256.hexdigest(), "md5": md5.hexdigest()}


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AcquisitionError(f"INVALID_JSON:{path.relative_to(ROOT)}:{exc}") from exc


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


def atomic_write(path: Path, payload: bytes, *, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp, mode)
        os.replace(temp, path)
        fsync_directory(path.parent)
    except BaseException:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass
        raise


def write_restricted_json(path: Path, value: Any) -> None:
    atomic_write(path, canonical_json_bytes(value), mode=0o600)


def write_public_text(path: Path, value: str) -> None:
    atomic_write(path, value.encode("utf-8"), mode=0o644)


def acquire_lock() -> None:
    try:
        descriptor = os.open(LOCK, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise AcquisitionError("TASK186_LOCK_ALREADY_EXISTS") from exc
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
    path = parsed.path
    host = (parsed.hostname or "").lower()
    if host.endswith("boxcloud.com"):
        parts = path.split("/")
        if len(parts) >= 5 and parts[1:3] == ["d", "1"]:
            path = "/d/1/[REDACTED_EPHEMERAL_OBJECT_CAPABILITY]/" + parts[-1]
        else:
            path = "/[REDACTED_EPHEMERAL_OBJECT_CAPABILITY]"
    query = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if any(marker in key.lower() for marker in SENSITIVE_QUERY_MARKERS):
            value = "[REDACTED]"
        query.append((key, value))
    query_text = "&".join(f"{key}={value}" for key, value in query)
    return urlunsplit((parsed.scheme, parsed.netloc, path, query_text, ""))


def sanitize_error(value: str) -> str:
    return URL_RE.sub(lambda match: sanitize_url(match.group(0)) or "", value)


def set_cookie_names(response: requests.Response) -> list[str]:
    return sorted(set(response.cookies.keys()))


def response_identity(response: requests.Response) -> dict[str, Any]:
    parsed = urlsplit(response.url)
    return {
        "status_code": response.status_code,
        "reason": response.reason,
        "redacted_url": sanitize_url(response.url),
        "scheme": parsed.scheme,
        "host": (parsed.hostname or "").lower(),
        "port": parsed.port,
        "path_template": urlsplit(sanitize_url(response.url) or "").path,
        "full_url_sha256": sha256_bytes(response.url.encode("utf-8")),
        "full_path_sha256": sha256_bytes(parsed.path.encode("utf-8")),
        "query_keys": sorted(key for key, _ in parse_qsl(parsed.query)),
        "fragment_present": bool(parsed.fragment),
        "content_type": response.headers.get("Content-Type"),
        "content_length": response.headers.get("Content-Length"),
        "content_disposition": response.headers.get("Content-Disposition"),
        "accept_ranges": response.headers.get("Accept-Ranges"),
        "etag": response.headers.get("ETag"),
        "last_modified": response.headers.get("Last-Modified"),
        "date": response.headers.get("Date"),
        "set_cookie_names": set_cookie_names(response),
    }


def exchange_identity(response: requests.Response) -> dict[str, Any]:
    return {
        "redirect_count": len(response.history),
        "history": [response_identity(item) for item in response.history],
        "final": response_identity(response),
        "cookie_values_retained": False,
        "final_ephemeral_capability_retained": False,
    }


def parse_content_disposition_filename(value: str | None) -> str:
    if not value:
        return ""
    match = re.search(
        r"""filename\*?=(?:UTF-8'')?["']?([^;"']+)""",
        value,
        re.I,
    )
    return match.group(1).strip() if match else ""


def validate_url(url: str) -> None:
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
        raise AcquisitionError("INVALID_FROZEN_OFFICIAL_URL")


def validate_final_response(
    response: requests.Response,
    candidate: Mapping[str, Any],
    *,
    expected_size: int | None,
) -> tuple[int, str, str]:
    parsed = urlsplit(response.url)
    final_host = (parsed.hostname or "").lower()
    redirect_hosts = [
        (urlsplit(item.url).hostname or "").lower()
        for item in [*response.history, response]
    ]
    if any(host not in ALLOWED_REDIRECT_HOSTS for host in redirect_hosts):
        raise AcquisitionError("UNEXPECTED_REDIRECT_HOST")
    if final_host != "public.boxcloud.com":
        raise AcquisitionError("FINAL_HOST_NOT_PUBLIC_BOXCLOUD")
    if response.status_code != 200:
        raise AcquisitionError("FINAL_STATUS_NOT_200")
    content_type = (response.headers.get("Content-Type") or "").split(";")[0].lower()
    if content_type != "video/mp4":
        raise AcquisitionError("FINAL_CONTENT_TYPE_NOT_VIDEO_MP4")
    try:
        size = int(response.headers["Content-Length"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AcquisitionError("FINAL_CONTENT_LENGTH_INVALID") from exc
    if size <= 0 or size > MAX_SINGLE_MEDIA_BYTES:
        raise AcquisitionError("FINAL_CONTENT_LENGTH_OUTSIDE_SINGLE_FILE_BUDGET")
    if expected_size is not None and size != expected_size:
        raise AcquisitionError("FINAL_CONTENT_LENGTH_CHANGED_AFTER_PREFLIGHT")
    filename = parse_content_disposition_filename(
        response.headers.get("Content-Disposition")
    )
    expected_filename = f"{candidate['recording_id']}_360p.mp4"
    if filename and filename != expected_filename:
        raise AcquisitionError("FINAL_CONTENT_DISPOSITION_FILENAME_MISMATCH")
    return size, content_type, filename


def verify_input_integrity() -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, item in INPUT_INTEGRITY.items():
        path = item["path"]
        raw = path.read_bytes()
        observed = {"bytes": len(raw), "sha256": sha256_bytes(raw)}
        expected = {"bytes": item["bytes"], "sha256": item["sha256"]}
        if observed != expected:
            raise AcquisitionError(f"FROZEN_INPUT_INTEGRITY_MISMATCH:{name}")
        result[name] = {
            "path": path.relative_to(ROOT).as_posix(),
            **observed,
            "verified": True,
        }
    return result


def verify_official_rights_evidence() -> dict[str, Any]:
    readme = PROJECT_README.read_text(encoding="utf-8")
    license_text = DOWNLOADER_LICENSE.read_text(encoding="utf-8")
    required_readme_fragments = (
        "Our dataset is licensed under the Apache license 2.0",
        "approved by the Institutional Review Board (IRB) at the University of Florida",
        "All participants provided written consent for the data collection",
    )
    if any(fragment not in readme for fragment in required_readme_fragments):
        raise AcquisitionError("OFFICIAL_LICENSE_OR_IRB_STATEMENT_MISSING")
    if "Apache License" not in license_text or "Version 2.0, January 2004" not in license_text:
        raise AcquisitionError("OFFICIAL_APACHE_2_LICENSE_TEXT_INVALID")
    return {
        "dataset_license_statement": "Apache License 2.0",
        "dataset_license_statement_verified": True,
        "university_of_florida_irb_statement_verified": True,
        "written_participant_consent_statement_verified": True,
        "project_readme_path": PROJECT_README.relative_to(ROOT).as_posix(),
        "project_readme_sha256": INPUT_INTEGRITY["project_readme"]["sha256"],
        "downloader_license_path": DOWNLOADER_LICENSE.relative_to(ROOT).as_posix(),
        "downloader_license_sha256": INPUT_INTEGRITY["downloader_license"]["sha256"],
        "operative_linked_irb_document_archived": False,
        "operative_linked_consent_document_archived": False,
        "use_boundary": (
            "Restricted internal research only under the explicit Task186 "
            "instruction; no public release or redistribution."
        ),
    }


def candidate_map_from_selection() -> dict[str, dict[str, Any]]:
    selection = load_json(SELECTION_V1)
    rows = [*selection["primary"], *selection["replacement"]]
    return {row["representative_recording_id"]: row for row in rows}


def candidate_map_from_routes() -> dict[str, dict[str, Any]]:
    inventory = load_json(ROUTE_INVENTORY_V3)
    return {row["recording_id"]: row for row in inventory["recordings"]}


def candidate_map_from_csv() -> dict[str, dict[str, str]]:
    with VIDEO_INFORMATION.open(newline="", encoding="utf-8") as handle:
        return {row["recording_id"]: row for row in csv.DictReader(handle)}


def verify_frozen_candidates() -> dict[str, Any]:
    selection = candidate_map_from_selection()
    routes = candidate_map_from_routes()
    links = load_json(DOWNLOAD_LINKS)
    metadata = candidate_map_from_csv()
    verification = []
    for position, candidate in enumerate(CANDIDATE_ORDER, 1):
        recording_id = candidate["recording_id"]
        validate_url(candidate["url"])
        if recording_id not in selection or recording_id not in routes:
            raise AcquisitionError(f"FROZEN_CANDIDATE_MISSING:{recording_id}")
        if recording_id not in links or recording_id not in metadata:
            raise AcquisitionError(f"OFFICIAL_SOURCE_ID_MISSING:{recording_id}")
        selection_row = selection[recording_id]
        route_row = routes[recording_id]
        metadata_row = metadata[recording_id]
        expected = {
            "person_id": int(candidate["person_id"]),
            "environment_id": int(candidate["environment_id"]),
            "source_group_id": candidate["source_group_id"],
            "duration_seconds": float(candidate["duration_seconds"]),
            "url": candidate["url"],
        }
        observed = {
            "person_id": int(metadata_row["person_id"]),
            "environment_id": int(metadata_row["environment_id"]),
            "source_group_id": selection_row["source_group_id"],
            "duration_seconds": float(metadata_row["duration(sec)"]),
            "url": links[recording_id]["gopro_360p"],
        }
        if observed != expected:
            raise AcquisitionError(f"FROZEN_CANDIDATE_REVALIDATION_FAILED:{recording_id}")
        if (
            route_row["gopro_360p_url"] != candidate["url"]
            or float(route_row["official_metadata_duration_seconds"])
            != candidate["duration_seconds"]
            or int(route_row["person_id"]) != candidate["person_id"]
            or int(route_row["environment_id"]) != candidate["environment_id"]
            or route_row["source_group_id"] != candidate["source_group_id"]
        ):
            raise AcquisitionError(f"TASK180_ROUTE_BINDING_MISMATCH:{recording_id}")
        verification.append(
            {
                "prospective_order": position,
                "recording_id": recording_id,
                "role": candidate["role"],
                "rank": candidate["rank"],
                "person_id": candidate["person_id"],
                "environment_id": candidate["environment_id"],
                "source_group_id": candidate["source_group_id"],
                "official_metadata_duration_seconds": candidate["duration_seconds"],
                "stream": "gopro_360p",
                "official_url": candidate["url"],
                "task174_selection_match": True,
                "task180_route_inventory_match": True,
                "official_download_links_match": True,
                "official_video_information_match": True,
            }
        )
    return {
        "prospective_candidate_order_frozen_before_network": True,
        "candidate_pool": "Task174 primary pool only",
        "initial_recording_ids": list(INITIAL_RECORDING_IDS),
        "prospective_replacement_recording_ids": list(
            PROSPECTIVE_REPLACEMENT_IDS
        ),
        "replacement_rule": (
            "Attempt 16_20 and the next two deterministic Task174 primaries "
            "first. After five failed GET attempts for a non-mandatory route, "
            "advance through the remaining Task174 primaries in frozen rank "
            "order while preserving distinct person_id and environment_id. "
            "16_20 is mandatory and cannot be replaced."
        ),
        "candidates": verification,
    }


def get_with_retries(
    candidate: Mapping[str, Any],
    *,
    purpose: str,
) -> tuple[requests.Response | None, list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    proxies = {"http": PROXY, "https": PROXY}
    for attempt in range(1, MAX_RETRIES + 1):
        started = time.monotonic()
        response: requests.Response | None = None
        try:
            # Keep the official request shape exactly.  Explicit proxy and
            # longer timeouts are Task186 controls; Requests still follows
            # redirects and carries eligible cookies inside this one GET.
            response = requests.get(
                candidate["url"],
                stream=True,
                proxies=proxies,
                timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
            )
            response.raise_for_status()
            attempts.append(
                {
                    "attempt": attempt,
                    "purpose": purpose,
                    "elapsed_seconds": round(time.monotonic() - started, 6),
                    "outcome": "SUCCESS",
                    "status_code": response.status_code,
                    "redirect_count": len(response.history),
                }
            )
            return response, attempts
        except requests.exceptions.RequestException as exc:
            attempts.append(
                {
                    "attempt": attempt,
                    "purpose": purpose,
                    "elapsed_seconds": round(time.monotonic() - started, 6),
                    "outcome": "REQUEST_ERROR",
                    "error_type": type(exc).__name__,
                    "error": sanitize_error(str(exc)),
                    "status_code": (
                        exc.response.status_code if exc.response is not None else None
                    ),
                }
            )
            if response is not None:
                response.close()
            if exc.response is not None:
                exc.response.close()
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SECONDS)
    return None, attempts


def resolve_candidate(candidate: dict[str, Any]) -> RouteResolution:
    response, attempts = get_with_retries(candidate, purpose="pre_download_resolution")
    if response is None:
        raise RouteUnavailable(candidate["recording_id"], attempts)
    try:
        size, content_type, filename = validate_final_response(
            response, candidate, expected_size=None
        )
        exchange = exchange_identity(response)
        accept_ranges = response.headers.get("Accept-Ranges")
    finally:
        response.close()
    return RouteResolution(
        candidate=dict(candidate),
        content_length_bytes=size,
        content_type=content_type,
        content_disposition_filename=filename,
        accept_ranges=accept_ranges,
        exchange=exchange,
        attempts=attempts,
    )


def resolution_record(resolution: RouteResolution) -> dict[str, Any]:
    candidate = resolution.candidate
    return {
        "recording_id": candidate["recording_id"],
        "role": candidate["role"],
        "rank": candidate["rank"],
        "person_id": candidate["person_id"],
        "environment_id": candidate["environment_id"],
        "source_group_id": candidate["source_group_id"],
        "official_metadata_duration_seconds": candidate["duration_seconds"],
        "stream": "gopro_360p",
        "official_url": candidate["url"],
        "content_length_bytes": resolution.content_length_bytes,
        "content_type": resolution.content_type,
        "content_disposition_filename": resolution.content_disposition_filename,
        "accept_ranges": resolution.accept_ranges,
        "attempts": resolution.attempts,
        "exchange": resolution.exchange,
        "response_body_bytes_consumed": 0,
    }


def route_preflight(
    input_integrity: Mapping[str, Any],
    rights: Mapping[str, Any],
    frozen: Mapping[str, Any],
) -> dict[str, Any]:
    attempted: list[dict[str, Any]] = []
    selected: list[RouteResolution] = []
    unavailable: list[dict[str, Any]] = []
    selected_people: set[int] = set()
    selected_environments: set[int] = set()

    for candidate in CANDIDATE_ORDER:
        if len(selected) == 3:
            break
        if (
            candidate["person_id"] in selected_people
            or candidate["environment_id"] in selected_environments
        ):
            attempted.append(
                {
                    "recording_id": candidate["recording_id"],
                    "outcome": "NOT_PROBED_DISTINCTNESS_CONFLICT_WITH_SELECTED",
                }
            )
            continue
        try:
            resolution = resolve_candidate(dict(candidate))
        except RouteUnavailable as exc:
            record = {
                "recording_id": candidate["recording_id"],
                "outcome": "UNAVAILABLE",
                "reason": str(exc),
                "attempts": exc.attempts,
            }
            attempted.append(record)
            unavailable.append(record)
            if candidate["mandatory"]:
                break
            continue
        attempted.append(
            {
                "recording_id": candidate["recording_id"],
                "outcome": "REACHABLE_AND_SELECTED",
                "content_length_bytes": resolution.content_length_bytes,
            }
        )
        selected.append(resolution)
        selected_people.add(candidate["person_id"])
        selected_environments.add(candidate["environment_id"])

    if len(selected) != 3:
        partial = {
            "schema_version": "av-trace.captaincook4d-wave0-route-preflight/1.0",
            "task_id": TASK_ID,
            "created_at": utc_now(),
            "proxy": PROXY,
            "request_semantics": {
                "method": "GET",
                "stream": True,
                "allow_redirects": "requests.get default True",
                "headers": "requests defaults only",
                "cookies": (
                    "no caller cookies; redirect cookies handled by Requests"
                ),
                "query_added": False,
                "timeout_only_extension": [
                    CONNECT_TIMEOUT_SECONDS,
                    READ_TIMEOUT_SECONDS,
                ],
                "retry_count": MAX_RETRIES,
                "retry_delay_seconds": RETRY_DELAY_SECONDS,
            },
            "input_integrity": dict(input_integrity),
            "rights_evidence": dict(rights),
            "frozen_candidate_revalidation": dict(frozen),
            "attempted_candidates": attempted,
            "unavailable_candidates": unavailable,
            "selected_recording_ids": [
                item.candidate["recording_id"] for item in selected
            ],
            "selected": [resolution_record(item) for item in selected],
            "replacement_events": [],
            "preflight_complete": False,
            "preflight_failure": (
                f"MANDATORY_16_20_UNAVAILABLE_AFTER_{MAX_RETRIES}_ATTEMPTS"
                if "16_20"
                not in {item.candidate["recording_id"] for item in selected}
                else "FEWER_THAN_THREE_REACHABLE_DISTINCT_FROZEN_PRIMARIES"
            ),
        }
        write_restricted_json(PREFLIGHT_LOG, partial)
        raise AcquisitionError("FEWER_THAN_THREE_REACHABLE_DISTINCT_FROZEN_CANDIDATES")
    ids = [item.candidate["recording_id"] for item in selected]
    if "16_20" not in ids:
        raise AcquisitionError("MANDATORY_16_20_NOT_SELECTED")
    if len(selected_people) != 3 or len(selected_environments) != 3:
        raise AcquisitionError("SELECTED_PEOPLE_OR_ENVIRONMENTS_NOT_DISTINCT")
    total = sum(item.content_length_bytes for item in selected)
    if total > MAX_SELECTED_MEDIA_BYTES:
        raise AcquisitionError("SELECTED_MEDIA_BUDGET_EXCEEDED")
    disk = shutil.disk_usage(BASE)
    required_free = total + MIN_FREE_SPACE_MARGIN_BYTES
    if disk.free < required_free:
        raise AcquisitionError("INSUFFICIENT_FREE_SPACE_BEFORE_DOWNLOAD")

    unavailable_initial = [
        recording_id
        for recording_id in INITIAL_RECORDING_IDS
        if recording_id not in ids
    ]
    selected_replacements = [
        recording_id for recording_id in ids if recording_id not in INITIAL_RECORDING_IDS
    ]
    replacements = [
        {
            "unavailable_recording_id": unavailable_recording_id,
            "replacement_recording_id": replacement_recording_id,
        }
        for unavailable_recording_id, replacement_recording_id in zip(
            unavailable_initial, selected_replacements, strict=True
        )
    ]
    result = {
        "schema_version": "av-trace.captaincook4d-wave0-route-preflight/1.0",
        "task_id": TASK_ID,
        "created_at": utc_now(),
        "proxy": PROXY,
        "request_semantics": {
            "method": "GET",
            "stream": True,
            "allow_redirects": "requests.get default True",
            "headers": "requests defaults only",
            "cookies": "no caller cookies; redirect cookies handled by Requests",
            "query_added": False,
            "timeout_only_extension": [
                CONNECT_TIMEOUT_SECONDS,
                READ_TIMEOUT_SECONDS,
            ],
            "retry_count": MAX_RETRIES,
            "retry_delay_seconds": RETRY_DELAY_SECONDS,
        },
        "input_integrity": dict(input_integrity),
        "rights_evidence": dict(rights),
        "frozen_candidate_revalidation": dict(frozen),
        "attempted_candidates": attempted,
        "unavailable_candidates": unavailable,
        "selected_recording_ids": ids,
        "selected": [resolution_record(item) for item in selected],
        "replacement_events": replacements,
        "pre_download_checks": {
            "exact_selected_count": len(selected),
            "mandatory_16_20_present": "16_20" in ids,
            "distinct_person_count": len(selected_people),
            "distinct_environment_count": len(selected_environments),
            "all_streams_gopro_360p": True,
            "aggregate_content_length_bytes": total,
            "maximum_selected_media_bytes": MAX_SELECTED_MEDIA_BYTES,
            "within_media_budget": total <= MAX_SELECTED_MEDIA_BYTES,
            "free_space_bytes_before_download": disk.free,
            "minimum_free_space_required_bytes": required_free,
            "free_space_check_passed": disk.free >= required_free,
            "source_ids_revalidated_before_download": True,
            "urls_revalidated_before_download": True,
            "sizes_revalidated_before_download": True,
            "response_body_bytes_consumed": 0,
        },
    }
    write_restricted_json(PREFLIGHT_LOG, result)
    return result


def selected_from_preflight(preflight: Mapping[str, Any]) -> list[RouteResolution]:
    candidates = {item["recording_id"]: dict(item) for item in CANDIDATE_ORDER}
    selected: list[RouteResolution] = []
    for item in preflight["selected"]:
        candidate = candidates[item["recording_id"]]
        selected.append(
            RouteResolution(
                candidate=candidate,
                content_length_bytes=int(item["content_length_bytes"]),
                content_type=item["content_type"],
                content_disposition_filename=item["content_disposition_filename"],
                accept_ranges=item.get("accept_ranges"),
                exchange=item["exchange"],
                attempts=item["attempts"],
            )
        )
    return selected


def download_one(resolution: RouteResolution) -> dict[str, Any]:
    candidate = resolution.candidate
    target = BASE / f"{candidate['recording_id']}_360p.mp4"
    part = target.with_name(target.name + ".part")
    if target.exists():
        existing = hash_file(target)
        if existing["bytes"] == resolution.content_length_bytes:
            os.chmod(target, 0o600)
            return {
                "recording_id": candidate["recording_id"],
                "status": "EXISTING_EXACT_SIZE_REUSED_AND_REHASHED",
                "path": target.relative_to(ROOT).as_posix(),
                "expected_bytes": resolution.content_length_bytes,
                "downloaded_bytes": 0,
                "final_bytes": existing["bytes"],
                "md5": existing["md5"],
                "sha256": existing["sha256"],
                "attempts": [],
                "final_redirect_identity": None,
                "atomic_part_promotion": False,
                "mode": oct(stat.S_IMODE(target.stat().st_mode)),
            }
        raise AcquisitionError(f"EXISTING_FINAL_SIZE_MISMATCH:{target.name}")

    attempts: list[dict[str, Any]] = []
    for attempt in range(1, MAX_RETRIES + 1):
        response: requests.Response | None = None
        started = time.monotonic()
        bytes_written = 0
        sha256 = hashlib.sha256()
        md5 = hashlib.md5(usedforsecurity=False)
        try:
            response = requests.get(
                candidate["url"],
                stream=True,
                proxies={"http": PROXY, "https": PROXY},
                timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
            )
            response.raise_for_status()
            size, _, _ = validate_final_response(
                response,
                candidate,
                expected_size=resolution.content_length_bytes,
            )
            final_identity = exchange_identity(response)
            descriptor = os.open(
                part, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600
            )
            with os.fdopen(descriptor, "wb") as handle:
                for block in response.iter_content(chunk_size=CHUNK_BYTES):
                    if not block:
                        continue
                    bytes_written += len(block)
                    if bytes_written > size:
                        raise AcquisitionError("RESPONSE_BODY_EXCEEDED_CONTENT_LENGTH")
                    handle.write(block)
                    sha256.update(block)
                    md5.update(block)
                handle.flush()
                os.fsync(handle.fileno())
            if bytes_written != size:
                raise AcquisitionError("RESPONSE_BODY_SIZE_MISMATCH")
            os.chmod(part, 0o600)
            os.replace(part, target)
            fsync_directory(BASE)
            attempts.append(
                {
                    "attempt": attempt,
                    "outcome": "SUCCESS",
                    "elapsed_seconds": round(time.monotonic() - started, 6),
                    "bytes_written": bytes_written,
                }
            )
            return {
                "recording_id": candidate["recording_id"],
                "status": "DOWNLOADED_AND_ATOMICALLY_PROMOTED",
                "path": target.relative_to(ROOT).as_posix(),
                "expected_bytes": size,
                "downloaded_bytes": bytes_written,
                "final_bytes": target.stat().st_size,
                "md5": md5.hexdigest(),
                "sha256": sha256.hexdigest(),
                "attempts": attempts,
                "final_redirect_identity": final_identity,
                "atomic_part_promotion": True,
                "part_open_mode": "wb",
                "mode": oct(stat.S_IMODE(target.stat().st_mode)),
            }
        except (requests.exceptions.RequestException, OSError, AcquisitionError) as exc:
            attempts.append(
                {
                    "attempt": attempt,
                    "outcome": "TRANSFER_ERROR",
                    "elapsed_seconds": round(time.monotonic() - started, 6),
                    "bytes_written_before_failure": bytes_written,
                    "error_type": type(exc).__name__,
                    "error": sanitize_error(str(exc)),
                }
            )
            try:
                part.unlink()
            except FileNotFoundError:
                pass
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SECONDS)
        finally:
            if response is not None:
                response.close()
    raise AcquisitionError(
        f"DOWNLOAD_FAILED_AFTER_{MAX_RETRIES}_ATTEMPTS:{candidate['recording_id']}"
    )


def download_selected(preflight: Mapping[str, Any]) -> dict[str, Any]:
    selected = selected_from_preflight(preflight)
    results = []
    for resolution in selected:
        print(
            f"Downloading {resolution.candidate['recording_id']} "
            f"({resolution.content_length_bytes:,} bytes)",
            flush=True,
        )
        results.append(download_one(resolution))
    paths = [ROOT / item["path"] for item in results]
    if len(paths) != 3 or len({path.name for path in paths}) != 3:
        raise AcquisitionError("EXACT_THREE_FINAL_MEDIA_FILES_REQUIRED")
    all_mp4 = sorted(BASE.glob("*.mp4"))
    if all_mp4 != sorted(paths):
        raise AcquisitionError("UNEXPECTED_MP4_IN_WAVE0_ROOT")
    if any(BASE.glob("*.part")):
        raise AcquisitionError("PARTIAL_FILE_REMAINS_AFTER_DOWNLOAD")
    transfer = {
        "schema_version": "av-trace.captaincook4d-wave0-transfer/1.0",
        "task_id": TASK_ID,
        "created_at": utc_now(),
        "proxy": PROXY,
        "official_get_semantics": True,
        "retry_count": MAX_RETRIES,
        "chunk_bytes": CHUNK_BYTES,
        "partial_suffix": ".part",
        "partial_open_mode": "wb",
        "atomic_promotion": "os.replace",
        "source_count": len(results),
        "aggregate_final_bytes": sum(item["final_bytes"] for item in results),
        "failed_transfers": 0,
        "incomplete_transfers": 0,
        "sources": results,
    }
    write_restricted_json(TRANSFER_LOG, transfer)
    return transfer


def fraction_text(value: Fraction | None) -> str | None:
    return str(value) if value is not None else None


def seconds_from_ts(value: int | None, time_base: Fraction | None) -> float | None:
    if value is None or time_base is None:
        return None
    return float(value * time_base)


def stream_record(stream: av.stream.Stream) -> dict[str, Any]:
    context = stream.codec_context
    record: dict[str, Any] = {
        "index": stream.index,
        "id": stream.id,
        "type": stream.type,
        "codec_name": getattr(context, "name", None),
        "codec_long_name": getattr(context.codec, "long_name", None)
        if getattr(context, "codec", None)
        else None,
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


def frame_timestamp(frame: av.frame.Frame, stream: av.stream.Stream) -> float | None:
    if frame.pts is None:
        return None
    time_base = frame.time_base or stream.time_base
    return seconds_from_ts(frame.pts, time_base)


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
        seek_seconds = max(0.0, target_seconds - 2.0)
        container.seek(int(seek_seconds * av.time_base), any_frame=False, backward=True)
        video_times: list[float] = []
        audio_times: list[float] = []
        decoded = {"video": 0, "audio": 0}
        upper = target_seconds + 2.0
        for packet in container.demux(video, audio):
            for frame in packet.decode():
                kind = packet.stream.type
                decoded[kind] += 1
                timestamp = frame_timestamp(frame, packet.stream)
                if timestamp is None:
                    continue
                if target_seconds - 2.0 <= timestamp <= upper:
                    if kind == "video":
                        video_times.append(timestamp)
                    elif kind == "audio":
                        audio_times.append(timestamp)
            if video_times and audio_times:
                latest_video = video_times[-1]
                latest_audio = audio_times[-1]
                if latest_video >= upper and latest_audio >= upper:
                    break
        video_time = min(video_times, key=lambda value: abs(value - target_seconds), default=None)
        audio_time = min(audio_times, key=lambda value: abs(value - target_seconds), default=None)
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
                        float(frame.duration * (frame.time_base or stream.time_base))
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
            end = item["last_frame_end_seconds"]
            item["last_frame_end_matches_stream_duration"] = (
                duration is None
                or end is not None
                and abs(end - duration) <= DURATION_TOLERANCE_SECONDS
            )
            item["no_truncation_verified"] = all(
                (
                    item["decoded_frames"] > 0,
                    item["missing_pts_frames"] == 0,
                    item["timestamps_monotonic"],
                    item["frame_count_exact"],
                    item["last_frame_end_matches_stream_duration"],
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
    opened = capture.isOpened()
    if not opened:
        capture.release()
        raise AcquisitionError(f"OPENCV_OPEN_FAILED:{path.name}")
    backend = capture.getBackendName()
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    declared_raw = float(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    declared = int(round(declared_raw)) if declared_raw > 0 else 0
    width = int(round(capture.get(cv2.CAP_PROP_FRAME_WIDTH)))
    height = int(round(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    fourcc_int = int(capture.get(cv2.CAP_PROP_FOURCC))
    fourcc = "".join(chr((fourcc_int >> (8 * index)) & 0xFF) for index in range(4))
    grabbed = 0
    while capture.grab():
        grabbed += 1
    eof_confirmed = not capture.grab()
    last_position_msec = float(capture.get(cv2.CAP_PROP_POS_MSEC))
    capture.release()
    duration = grabbed / fps if fps > 0 else None
    frame_count_exact = declared == 0 or grabbed == declared
    duration_matches = (
        duration is not None
        and abs(duration - official_duration) <= DURATION_TOLERANCE_SECONDS
    )
    return {
        "opened": opened,
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
        "duration_delta_seconds": (
            abs(duration - official_duration) if duration is not None else None
        ),
        "duration_matches_official_within_0_5s": duration_matches,
        "last_position_msec": last_position_msec,
        "eof_confirmed": eof_confirmed,
        "no_truncation_verified": (
            grabbed > 0 and eof_confirmed and frame_count_exact and duration_matches
        ),
        "elapsed_seconds": round(time.monotonic() - started, 6),
    }


def technical_audit_source(
    candidate: Mapping[str, Any],
    transfer: Mapping[str, Any],
) -> dict[str, Any]:
    path = ROOT / transfer["path"]
    expected_size = int(transfer["expected_bytes"])
    if path.stat().st_size != expected_size:
        raise AcquisitionError(f"AUDIT_SIZE_MISMATCH:{path.name}")
    with av.open(str(path)) as container:
        container_duration = (
            float(container.duration / av.time_base)
            if container.duration is not None
            else None
        )
        streams = [stream_record(stream) for stream in container.streams]
    video_streams = [item for item in streams if item["type"] == "video"]
    audio_streams = [item for item in streams if item["type"] == "audio"]
    if not video_streams or not audio_streams:
        raise AcquisitionError(f"AUDIO_OR_VIDEO_STREAM_MISSING:{path.name}")
    video_duration = video_streams[0]["duration_seconds"]
    official_duration = float(candidate["duration_seconds"])
    duration_delta = (
        abs(video_duration - official_duration)
        if video_duration is not None
        else None
    )
    duration_match = (
        duration_delta is not None
        and duration_delta <= DURATION_TOLERANCE_SECONDS
    )
    probe_duration = video_duration or container_duration or official_duration
    targets = {
        "beginning": min(1.0, probe_duration / 4.0),
        "middle": probe_duration / 2.0,
        "end": max(0.0, probe_duration - 2.0),
    }
    probes = {
        name: bme_probe(path, round(target, 6)) for name, target in targets.items()
    }
    full_pyav = full_pyav_decode(path)
    opencv = opencv_full_decode(path, official_duration)
    checks = {
        "exact_file_size": path.stat().st_size == expected_size,
        "container_open": True,
        "video_stream_present": bool(video_streams),
        "audio_stream_present": bool(audio_streams),
        "duration_matches_official_within_0_5s": duration_match,
        "beginning_middle_end_av_decode": all(
            item["video_decoded"] and item["audio_decoded"] for item in probes.values()
        ),
        "beginning_middle_end_av_synchronization": all(
            item["timestamps_synchronized_within_0_25s"]
            for item in probes.values()
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
        "official_metadata_duration_seconds": official_duration,
        "container": {
            "format_name": None,
            "duration_seconds": container_duration,
        },
        "video_stream_duration_seconds": video_duration,
        "video_duration_delta_from_official_seconds": duration_delta,
        "streams": streams,
        "beginning_middle_end_decode": probes,
        "full_pyav_decode": full_pyav,
        "opencv_full_decode": opencv,
        "checks": checks,
        "technical_audit_passed": all(checks.values()),
    }


def run_technical_audit(
    preflight: Mapping[str, Any],
    transfer_log: Mapping[str, Any],
) -> dict[str, Any]:
    candidate_rows = {
        item.candidate["recording_id"]: item.candidate
        for item in selected_from_preflight(preflight)
    }
    audited = []
    for transfer in transfer_log["sources"]:
        recording_id = transfer["recording_id"]
        print(f"Auditing {recording_id} with PyAV/OpenCV", flush=True)
        audited.append(technical_audit_source(candidate_rows[recording_id], transfer))
    result = {
        "schema_version": "av-trace.captaincook4d-wave0-technical-audit/1.0",
        "task_id": TASK_ID,
        "created_at": utc_now(),
        "pyav_version": av.__version__,
        "opencv_version": cv2.__version__,
        "duration_tolerance_seconds": DURATION_TOLERANCE_SECONDS,
        "sync_tolerance_seconds": SYNC_TOLERANCE_SECONDS,
        "source_count": len(audited),
        "all_sources_passed": len(audited) == 3
        and all(item["technical_audit_passed"] for item in audited),
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
            raise AcquisitionError(f"POST_DOWNLOAD_HASH_MISMATCH:{path.name}")
        rows.append(
            {
                "recording_id": transfer["recording_id"],
                "path": transfer["path"],
                **observed,
            }
        )
    result = {
        "schema_version": "av-trace.captaincook4d-wave0-hashes/1.0",
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
        rendered = "; ".join(
            f"{'.'.join(map(str, error.absolute_path)) or '$'}: {error.message}"
            for error in errors[:10]
        )
        raise AcquisitionError(f"{label}_SCHEMA_INVALID:{rendered}")


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


def create_semantic_inventory_and_plan(
    preflight: Mapping[str, Any],
    hashes: Mapping[str, Any],
    audit: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    candidates = {
        item.candidate["recording_id"]: item.candidate
        for item in selected_from_preflight(preflight)
    }
    hash_rows = {item["recording_id"]: item for item in hashes["sources"]}
    audit_rows = {item["source_id"]: item for item in audit["sources"]}
    sources = []
    for recording_id in sorted(candidates):
        candidate = candidates[recording_id]
        duration = audit_rows[recording_id]["video_stream_duration_seconds"]
        if duration is None:
            raise AcquisitionError(f"PRESCREEN_DURATION_MISSING:{recording_id}")
        sources.append(
            {
                "source_id": recording_id,
                "source_group_id": candidate["source_group_id"],
                "duration_s": duration,
                "source_content_sha256": f"sha256:{hash_rows[recording_id]['sha256']}",
                "adapter_reference": f"restricted-file://{recording_id}_360p.mp4",
                "media_included": False,
                "semantic_metadata_included": False,
            }
        )
    inventory = {
        "schema_version": "1.0.0",
        "record_type": "semantic_av_source_prescreen_inventory",
        "inventory_id": "captaincook4d-wave0-task186-semantic-prescreen-inventory-v1",
        "inventory_status": "FROZEN_NONSEMANTIC_SOURCE_INVENTORY",
        "sources": sources,
        "notes": (
            "Task186 nonsemantic inventory only. No human semantic review, "
            "semantic annotation, modality-necessity decision, or H tier."
        ),
    }
    validate_schema(inventory, INVENTORY_SCHEMA, "PRESCREEN_INVENTORY")
    write_restricted_json(INVENTORY, inventory)
    inventory_sha256 = "sha256:" + sha256_bytes(INVENTORY.read_bytes())

    plan_id = "captaincook4d-wave0-task186-semantic-prescreen-plan-v1"
    seed = "AVTRACE-CAPTAINCOOK4D-WAVE0-TASK186-SEMANTIC-PRESCREEN-V1"
    interval_duration = 12.0
    sample_count = 9
    quota = sample_count // len(sources)
    samples = []
    sequence = 1
    for source in sorted(sources, key=lambda item: item["source_id"]):
        bin_width = source["duration_s"] / quota
        if interval_duration > bin_width:
            raise AcquisitionError("PRESCREEN_INTERVAL_DOES_NOT_FIT")
        for index in range(quota):
            slack = bin_width - interval_duration
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
                    "end_s": round(start + interval_duration, 3),
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
        "created_at": "2026-10-08T00:00:00Z",
        "inventory_id": inventory["inventory_id"],
        "inventory_sha256": inventory_sha256,
        "seed": seed,
        "algorithm": "source-uniform-temporal-bin-sha256-jitter-v1",
        "sample_count": len(samples),
        "interval_duration_s": interval_duration,
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
    validate_schema(plan, PLAN_SCHEMA, "PRESCREEN_PLAN")
    if plan["plan_sha256"] != semantic_plan_hash(plan):
        raise AcquisitionError("PRESCREEN_PLAN_HASH_MISMATCH")
    write_restricted_json(PLAN, plan)
    return inventory, plan


def create_manifests(
    preflight: Mapping[str, Any],
    transfer_log: Mapping[str, Any],
    hashes: Mapping[str, Any],
    audit: Mapping[str, Any],
    inventory: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    candidate_rows = {
        item.candidate["recording_id"]: item.candidate
        for item in selected_from_preflight(preflight)
    }
    preflight_rows = {item["recording_id"]: item for item in preflight["selected"]}
    transfer_rows = {item["recording_id"]: item for item in transfer_log["sources"]}
    hash_rows = {item["recording_id"]: item for item in hashes["sources"]}
    audit_rows = {item["source_id"]: item for item in audit["sources"]}
    source_manifests = []
    for recording_id in preflight["selected_recording_ids"]:
        candidate = candidate_rows[recording_id]
        source_manifest = {
            "schema_version": "1.0",
            "record_type": "captaincook4d_wave0_source_manifest",
            "task_id": TASK_ID,
            "generated_at_utc": utc_now(),
            "dataset": "CaptainCook4D",
            "source_id": recording_id,
            "source_group_id": candidate["source_group_id"],
            "person_id": candidate["person_id"],
            "environment_id": candidate["environment_id"],
            "stream": "gopro_360p",
            "official_metadata_duration_seconds": candidate["duration_seconds"],
            "media": {
                "path": transfer_rows[recording_id]["path"],
                **{
                    key: hash_rows[recording_id][key]
                    for key in ("bytes", "md5", "sha256")
                },
                "mode": transfer_rows[recording_id]["mode"],
            },
            "route": {
                "official_entrypoint": candidate["url"],
                "preflight_final_redirect_identity": preflight_rows[recording_id][
                    "exchange"
                ]["final"],
                "download_final_redirect_identity": transfer_rows[recording_id][
                    "final_redirect_identity"
                ],
                "cookie_values_retained": False,
                "ephemeral_capability_retained": False,
            },
            "technical_validation": audit_rows[recording_id],
            "rights_and_use": preflight["rights_evidence"],
            "human_semantic_review_performed": False,
            "necessity_assigned": False,
            "h1_assigned": False,
            "h2_assigned": False,
            "public_release_or_redistribution": "NOT_AUTHORIZED",
        }
        path = MANIFESTS / f"{recording_id}.source_manifest.json"
        write_restricted_json(path, source_manifest)
        source_manifests.append(
            {
                "recording_id": recording_id,
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": sha256_bytes(path.read_bytes()),
            }
        )

    all_files_0600 = all(
        stat.S_IMODE(path.stat().st_mode) == 0o600
        for path in BASE.rglob("*")
        if path.is_file() and path != LOCK
    )
    all_dirs_0700 = all(
        stat.S_IMODE(path.stat().st_mode) == 0o700
        for path in [BASE, *[item for item in BASE.rglob("*") if item.is_dir()]]
    )
    root = {
        "schema_version": "1.0",
        "record_type": "captaincook4d_wave0_acquisition_manifest",
        "task_id": TASK_ID,
        "generated_at_utc": utc_now(),
        "decision": "CAPTAINCOOK4D_WAVE0_ACQUISITION_READY",
        "scope": (
            "Restricted internal acquisition and technical validation of "
            "exactly three Task174-frozen CaptainCook4D GoPro 360p recordings."
        ),
        "source_count": 3,
        "selected_recording_ids": list(preflight["selected_recording_ids"]),
        "distinct_person_count": len(
            {candidate_rows[item]["person_id"] for item in candidate_rows}
        ),
        "distinct_environment_count": len(
            {candidate_rows[item]["environment_id"] for item in candidate_rows}
        ),
        "aggregate_primary_media_bytes": hashes["aggregate_bytes"],
        "aggregate_official_duration_seconds": sum(
            candidate_rows[item]["duration_seconds"] for item in candidate_rows
        ),
        "input_evidence": preflight["input_integrity"],
        "rights_and_use": preflight["rights_evidence"],
        "pre_download_revalidation": {
            **preflight["pre_download_checks"],
            "log_path": PREFLIGHT_LOG.relative_to(ROOT).as_posix(),
            "replacement_events": preflight["replacement_events"],
        },
        "transfer": {
            "log_path": TRANSFER_LOG.relative_to(ROOT).as_posix(),
            "official_get_semantics": True,
            "explicit_proxy": PROXY,
            "retries": MAX_RETRIES,
            "part_atomic_promotion": True,
            "failed_transfers": transfer_log["failed_transfers"],
            "incomplete_transfers": transfer_log["incomplete_transfers"],
        },
        "technical_audit": {
            "path": AUDIT_LOG.relative_to(ROOT).as_posix(),
            "pyav_version": audit["pyav_version"],
            "opencv_version": audit["opencv_version"],
            "all_sources_passed": audit["all_sources_passed"],
        },
        "semantic_prescreen": {
            "status": "DETERMINISTIC_INVENTORY_AND_PLAN_ONLY_NOT_HUMAN_REVIEWED",
            "inventory_path": INVENTORY.relative_to(ROOT).as_posix(),
            "inventory_sha256": "sha256:" + sha256_bytes(INVENTORY.read_bytes()),
            "plan_path": PLAN.relative_to(ROOT).as_posix(),
            "plan_sha256": "sha256:" + sha256_bytes(PLAN.read_bytes()),
            "sample_count": plan["sample_count"],
            "interval_duration_seconds": plan["interval_duration_s"],
            "human_review_performed": False,
            "human_decisions_recorded": False,
        },
        "source_manifests": source_manifests,
        "sources": [
            {
                "source_id": recording_id,
                "source_group_id": candidate_rows[recording_id]["source_group_id"],
                "person_id": candidate_rows[recording_id]["person_id"],
                "environment_id": candidate_rows[recording_id]["environment_id"],
                "official_duration_seconds": candidate_rows[recording_id][
                    "duration_seconds"
                ],
                "media": hash_rows[recording_id],
                "technical_audit_passed": audit_rows[recording_id][
                    "technical_audit_passed"
                ],
            }
            for recording_id in preflight["selected_recording_ids"]
        ],
        "readiness_checks": {
            "exact_three_sources": len(preflight["selected_recording_ids"]) == 3,
            "mandatory_16_20_included": "16_20"
            in preflight["selected_recording_ids"],
            "three_distinct_people": len(
                {candidate_rows[item]["person_id"] for item in candidate_rows}
            )
            == 3,
            "three_distinct_environments": len(
                {candidate_rows[item]["environment_id"] for item in candidate_rows}
            )
            == 3,
            "all_gopro_360p": True,
            "all_exact_sizes_and_hashes_verified": True,
            "all_technical_audits_passed": audit["all_sources_passed"],
            "all_restricted_files_mode_0600": all_files_0600,
            "all_restricted_directories_mode_0700": all_dirs_0700,
            "zero_failed_transfers": transfer_log["failed_transfers"] == 0,
            "zero_incomplete_transfers": transfer_log["incomplete_transfers"] == 0,
            "no_h_tiers": True,
            "no_semantic_annotations": True,
            "public_release_not_authorized": True,
        },
        "explicit_non_claims": [
            "No human semantic decision was made.",
            "No modality-necessity claim was made.",
            "No H tier was assigned.",
            "No public release or redistribution is authorized.",
        ],
    }
    if not all(root["readiness_checks"].values()):
        raise AcquisitionError("ROOT_MANIFEST_READINESS_CHECK_FAILED")
    write_restricted_json(ROOT_MANIFEST, root)
    return root


def stream_summary(source: Mapping[str, Any]) -> tuple[str, str]:
    videos = [item for item in source["streams"] if item["type"] == "video"]
    audios = [item for item in source["streams"] if item["type"] == "audio"]
    video = videos[0]
    audio = audios[0]
    video_text = (
        f"{video['codec_name']} {video.get('profile') or ''} "
        f"{video.get('width')}x{video.get('height')} "
        f"time base {video['time_base']}"
    ).replace("  ", " ")
    audio_text = (
        f"{audio['codec_name']} {audio.get('profile') or ''}, "
        f"{audio.get('channels')} ch/{audio.get('layout')}, "
        f"{audio.get('sample_rate_hz')} Hz, time base {audio['time_base']}"
    ).replace("  ", " ")
    return video_text, audio_text


def create_review_and_result(
    preflight: Mapping[str, Any],
    hashes: Mapping[str, Any],
    audit: Mapping[str, Any],
    root_manifest: Mapping[str, Any],
) -> None:
    audit_rows = {item["source_id"]: item for item in audit["sources"]}
    hash_rows = {item["recording_id"]: item for item in hashes["sources"]}
    selected_rows = {item["recording_id"]: item for item in preflight["selected"]}
    table_rows = []
    technical_sections = []
    for recording_id in preflight["selected_recording_ids"]:
        selected = selected_rows[recording_id]
        source = audit_rows[recording_id]
        digest = hash_rows[recording_id]
        table_rows.append(
            f"| `{recording_id}` | {selected['person_id']} | "
            f"{selected['environment_id']} | `{selected['source_group_id']}` | "
            f"{selected['official_metadata_duration_seconds']:.2f} | "
            f"{digest['bytes']:,} | `{digest['sha256']}` |"
        )
        video_text, audio_text = stream_summary(source)
        bme = source["beginning_middle_end_decode"]
        deltas = ", ".join(
            f"{name}={item['absolute_av_timestamp_delta_seconds']:.6f}s"
            for name, item in bme.items()
        )
        pyav_counts = ", ".join(
            f"{item['type']} {item['decoded_frames']}"
            for item in source["full_pyav_decode"]["streams"]
        )
        technical_sections.append(
            "\n".join(
                [
                    f"### `{recording_id}`",
                    "",
                    f"- Official duration: "
                    f"`{source['official_metadata_duration_seconds']:.2f}` s; "
                    f"decoded video duration: "
                    f"`{source['video_stream_duration_seconds']:.6f}` s; "
                    f"delta: `{source['video_duration_delta_from_official_seconds']:.6f}` s.",
                    f"- Video: {video_text}.",
                    f"- Audio: {audio_text}.",
                    f"- B/M/E nearest A/V timestamp deltas: {deltas}.",
                    f"- PyAV full decode through EOF: {pyav_counts}; "
                    f"all stream no-truncation checks passed.",
                    f"- OpenCV full decode through EOF: "
                    f"{source['opencv_full_decode']['grabbed_frame_count']} frames; "
                    f"declared-frame match and no-truncation checks passed.",
                ]
            )
        )

    replacements = preflight["replacement_events"]
    replacement_text = (
        "No route replacement was required; the intended first three "
        "Task174 primaries were reachable."
        if not replacements
        else (
            "After five failed preflight GET attempts for each unavailable "
            "route, the frozen replacement order was applied. Replacement "
            "events: "
            + json.dumps(replacements, sort_keys=True)
            + "."
        )
    )
    review = f"""# CaptainCook4D Wave-0 exact acquisition

**Task:** 186  
**Date:** {TASK_DATE}  
**Decision:** `CAPTAINCOOK4D_WAVE0_ACQUISITION_READY`

## Scope and boundaries

Task186 repaired the interrupted acquisition and technically validated exactly
three CaptainCook4D Task174-frozen primary recordings for restricted internal
research. All three
objects are GoPro 360p MP4s. Recording `16_20` is included. The sources span
three people and three environments.

No annotation file, HoloLens stream, 4K stream, feature, transcript, clip, or
other media object was downloaded. No human semantic review or decision was
performed. No modality-necessity claim or H tier was assigned, and no public
release or redistribution is authorized.

## Official evidence and authorization boundary

The retained official project README states that CaptainCook4D is licensed
under Apache License 2.0, that the dataset was approved by the University of
Florida IRB, and that all participants provided written consent for data
collection. The retained downloader repository includes the Apache-2.0 text.
Task186 authorizes only this exact restricted internal sample. The linked
operative IRB and consent document bodies remain unarchived, so the media and
all identity-bearing derivatives remain restricted.

## Frozen selection and pre-download revalidation

The prospective order was frozen before Task186 network access:
`16_20`, `15_29`, `26_22`, then the remaining Task174 primaries in rank
order: `25_1`, `25_109`, `2_13`, `16_23`, `23_19`. The two Task174
same-person replacement groups were excluded from Task186's primary-pool
scope. Selection used no semantic annotation. {replacement_text}

Before any media body was consumed, Task186 revalidated:

- the pinned Task174 selection and official recording metadata;
- the Task180 route inventory and official GoPro 360p URL;
- person, environment, source-group, recording ID, and duration bindings;
- a final HTTP 200 `video/mp4` response and exact `Content-Length`;
- final `Content-Disposition` identity;
- distinct-person/distinct-environment constraints;
- the {MAX_SELECTED_MEDIA_BYTES:,}-byte aggregate media budget; and
- free workspace capacity.

The selected aggregate expected size was
**{preflight['pre_download_checks']['aggregate_content_length_bytes']:,}
bytes**. Preflight consumed zero response-body bytes.

## Exact selected media

| Recording | Person | Environment | Source group | Official duration (s) | Bytes | SHA-256 |
| --- | ---: | ---: | --- | ---: | ---: | --- |
{chr(10).join(table_rows)}

Each transfer used the official `requests.get(url, stream=True)` GET shape,
Requests-default redirects and redirect-cookie handling, the explicit
`{PROXY}` proxy, connect/read timeouts of
`{CONNECT_TIMEOUT_SECONDS}/{READ_TIMEOUT_SECONDS}` seconds, five retries,
1 MiB streaming chunks, mode `0600`, a
same-directory `.part` opened with `wb`, `fsync`, and atomic `os.replace`.
Directories are mode `0700`. No partial remains.

The final BoxCloud capability and all cookie values are redacted. The
restricted logs retain only a redacted path template, host, response
metadata, cookie names, and one-way URL/path hashes.

## Technical audit

PyAV `{audit['pyav_version']}` and OpenCV `{audit['opencv_version']}` were
used. Duration tolerance was {DURATION_TOLERANCE_SECONDS:.1f} s and B/M/E
A/V timestamp synchronization tolerance was
{SYNC_TOLERANCE_SECONDS:.2f} s.

{chr(10).join(technical_sections)}

All three sources passed full container open, official-duration comparison,
video/audio stream and codec/time-base inspection, beginning/middle/end A/V
decode, timestamp synchronization, complete PyAV decoding through EOF,
complete OpenCV frame traversal through EOF, exact byte-size verification,
and no-truncation checks.

## Task153 semantic-prescreen inventory and plan

- Inventory: `{INVENTORY.relative_to(ROOT).as_posix()}`
- Plan: `{PLAN.relative_to(ROOT).as_posix()}`
- Algorithm: `source-uniform-temporal-bin-sha256-jitter-v1`
- Samples: 9 unlabeled 12-second intervals, exactly 3 per source
- `extract_media=false`
- `semantic_labels_present=false`
- Human review and human decisions: not performed
- Necessity/H1/H2: not assigned

## Outputs

- `{ROOT_MANIFEST.relative_to(ROOT).as_posix()}`
- `{PREFLIGHT_LOG.relative_to(ROOT).as_posix()}`
- `{TRANSFER_LOG.relative_to(ROOT).as_posix()}`
- `{HASH_LOG.relative_to(ROOT).as_posix()}`
- `{AUDIT_LOG.relative_to(ROOT).as_posix()}`
- `{INVENTORY.relative_to(ROOT).as_posix()}`
- `{PLAN.relative_to(ROOT).as_posix()}`
- three per-source manifests under
  `{MANIFESTS.relative_to(ROOT).as_posix()}/`
- exactly three MP4s in `{BASE.relative_to(ROOT).as_posix()}/`

## Decision

The exact restricted Wave-0 acquisition and technical validation requirements
are satisfied.

`CAPTAINCOOK4D_WAVE0_ACQUISITION_READY`
"""
    write_public_text(REVIEW, review)

    result_lines = [
        "Task186 CaptainCook4D Wave-0 acquisition repair",
        f"Date: {TASK_DATE}",
        "Decision: CAPTAINCOOK4D_WAVE0_ACQUISITION_READY",
        "",
        "SCOPE",
        "- Exactly 3 Task174-frozen GoPro 360p MP4s.",
        "- Distinct people: 3; distinct environments: 3.",
        "- Required recording 16_20 included.",
        "- No annotations, HoloLens, 4K, H tiers, semantic decisions, or public release.",
        "",
        "SELECTED",
    ]
    for recording_id in preflight["selected_recording_ids"]:
        selected = selected_rows[recording_id]
        digest = hash_rows[recording_id]
        result_lines.extend(
            [
                f"- {recording_id}: person {selected['person_id']}, "
                f"environment {selected['environment_id']}, "
                f"{selected['official_metadata_duration_seconds']:.2f} s, "
                f"{digest['bytes']:,} bytes",
                f"  SHA-256: {digest['sha256']}",
            ]
        )
    result_lines.extend(
        [
            "",
            "TRANSFER",
            f"- Explicit proxy: {PROXY}",
            "- Official requests.get(url, stream=True) redirect/cookie semantics.",
            f"- Connect/read timeouts: {CONNECT_TIMEOUT_SECONDS}/"
            f"{READ_TIMEOUT_SECONDS} seconds.",
            "- Five retries; 1 MiB chunks; .part wb; fsync; atomic os.replace.",
            "- Final redirect capability and cookie values redacted.",
            "- Failed/incomplete transfers: 0/0.",
            "",
            "TECHNICAL AUDIT",
            f"- PyAV {audit['pyav_version']}; OpenCV {audit['opencv_version']}.",
            "- Official duration, streams/codecs/timebases, B/M/E A/V decode,",
            "  synchronization, full EOF decode, and no truncation: PASS for 3/3.",
            "",
            "TASK153",
            "- Nonsemantic inventory and deterministic plan only.",
            "- 9 unlabeled 12-second intervals, 3 per source; extract_media=false.",
            "- Human review/decisions and necessity/H1/H2: NOT PERFORMED.",
            "",
            "OUTPUTS",
            f"- {REVIEW.relative_to(ROOT).as_posix()}",
            f"- {ROOT_MANIFEST.relative_to(ROOT).as_posix()}",
            f"- {PREFLIGHT_LOG.relative_to(ROOT).as_posix()}",
            f"- {TRANSFER_LOG.relative_to(ROOT).as_posix()}",
            f"- {HASH_LOG.relative_to(ROOT).as_posix()}",
            f"- {AUDIT_LOG.relative_to(ROOT).as_posix()}",
            f"- {INVENTORY.relative_to(ROOT).as_posix()}",
            f"- {PLAN.relative_to(ROOT).as_posix()}",
            "",
            "CAPTAINCOOK4D_WAVE0_ACQUISITION_READY",
            "",
        ]
    )
    write_public_text(RESULT, "\n".join(result_lines))


def ensure_final_permissions() -> None:
    for directory in [BASE, *[item for item in BASE.rglob("*") if item.is_dir()]]:
        directory.chmod(0o700)
    for path in BASE.rglob("*"):
        if path.is_file() and path != LOCK:
            path.chmod(0o600)


def load_completed_transfer() -> dict[str, Any]:
    transfer = load_json(TRANSFER_LOG)
    if transfer.get("source_count") != 3:
        raise AcquisitionError("FINALIZE_TRANSFER_LOG_NOT_COMPLETE")
    for item in transfer["sources"]:
        path = ROOT / item["path"]
        if not path.is_file() or path.stat().st_size != item["final_bytes"]:
            raise AcquisitionError(f"FINALIZE_MEDIA_MISSING_OR_WRONG_SIZE:{path.name}")
    return transfer


def finalize(preflight: Mapping[str, Any], transfer: Mapping[str, Any]) -> None:
    hashes = create_hash_log(transfer)
    audit = run_technical_audit(preflight, transfer)
    if not audit["all_sources_passed"]:
        raise AcquisitionError("TECHNICAL_AUDIT_FAILED")
    inventory, plan = create_semantic_inventory_and_plan(preflight, hashes, audit)
    ensure_final_permissions()
    manifest = create_manifests(preflight, transfer, hashes, audit, inventory, plan)
    ensure_final_permissions()
    create_review_and_result(preflight, hashes, audit, manifest)


def write_failure(exc: BaseException) -> None:
    secure_directories()
    failure = {
        "schema_version": "av-trace.captaincook4d-wave0-failure/1.0",
        "task_id": TASK_ID,
        "created_at": utc_now(),
        "decision": "CAPTAINCOOK4D_WAVE0_ACQUISITION_REPAIR",
        "error_type": type(exc).__name__,
        "error": sanitize_error(str(exc)),
        "repair_context": "Task183 interrupted acquisition",
        "public_release_or_redistribution": "NOT_AUTHORIZED",
    }
    write_restricted_json(LOGS / "task186_failure.json", failure)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--preflight-only", action="store_true")
    mode.add_argument("--finalize-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    os.umask(0o077)
    secure_directories()
    acquire_lock()
    try:
        if args.finalize_only:
            preflight = load_json(PREFLIGHT_LOG)
            transfer = load_completed_transfer()
            finalize(preflight, transfer)
            print("CAPTAINCOOK4D_WAVE0_ACQUISITION_READY")
            return 0

        input_integrity = verify_input_integrity()
        rights = verify_official_rights_evidence()
        frozen = verify_frozen_candidates()
        preflight = route_preflight(input_integrity, rights, frozen)
        if args.preflight_only:
            print(
                "CAPTAINCOOK4D_WAVE0_PREFLIGHT_READY "
                + ",".join(preflight["selected_recording_ids"])
            )
            return 0
        transfer = download_selected(preflight)
        finalize(preflight, transfer)
        print("CAPTAINCOOK4D_WAVE0_ACQUISITION_READY")
        return 0
    except BaseException as exc:
        write_failure(exc)
        print(f"CAPTAINCOOK4D_WAVE0_ACQUISITION_REPAIR: {sanitize_error(str(exc))}")
        return 2
    finally:
        release_lock()


if __name__ == "__main__":
    raise SystemExit(main())
