#!/usr/bin/env python3
"""Resumable exact acquisition and technical validation of EPIC P23_102.

This tool is intentionally scoped to one public EPIC-KITCHENS-100 object. It
does not open annotation files, decode media samples, or acquire any other
dataset asset.
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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
TASK_ID = 206
ASSET_ID = "P23_102"
PARTICIPANT_ID = "P23"
OBJECT_PATH = "P23/videos/P23_102.MP4"
OFFICIAL_URL = (
    "https://data.bris.ac.uk/datasets/"
    "2g1n6qdydwa9u22shpxqzp0t8m/P23/videos/P23_102.MP4"
)
EXPECTED_BYTES = 10_814_161_307
OFFICIAL_MD5 = "4698fcbf13782f6396029761eb3bd5f2"
OFFICIAL_DURATION_SECONDS = 3569.52
LICENSE_SPDX = "CC-BY-NC-4.0"

PROXIES = (
    "https://proxy.example.invalid:3128",
    "https://proxy.example.invalid:3128",
)
DEFAULT_CHUNK_BYTES = 512 * 1024 * 1024
DEFAULT_ATTEMPT_ROUNDS = 3
DEFAULT_CONNECT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_TIME_SECONDS = 3600
FREE_SPACE_MARGIN_BYTES = 1024 * 1024 * 1024
COPY_BLOCK_BYTES = 8 * 1024 * 1024
HASH_BLOCK_BYTES = 16 * 1024 * 1024
STREAM_DURATION_TOLERANCE_SECONDS = 0.25
OFFICIAL_DURATION_TOLERANCE_SECONDS = 0.25

BASE = ROOT / "data/restricted/epic_p23_102_source_v1"
MEDIA_DIR = BASE / "media/P23"
STAGING_DIR = BASE / "staging"
LOG_DIR = BASE / "logs"
MANIFEST_DIR = BASE / "manifests"
VALIDATION_DIR = BASE / "validation"
FINAL_MEDIA = MEDIA_DIR / "P23_102.MP4"
PART_MEDIA = STAGING_DIR / "P23_102.MP4.part"
SEGMENT_MEDIA = STAGING_DIR / ".P23_102.MP4.range.part"
HEADER_FILE = STAGING_DIR / ".P23_102.MP4.headers.part"
LOCK_FILE = STAGING_DIR / ".acquisition.lock"
PROGRESS_FILE = LOG_DIR / "acquisition_progress.json"
JOURNAL_FILE = LOG_DIR / "range_attempts.jsonl"
PROVENANCE_FILE = MANIFEST_DIR / "provenance_and_usage_boundary.json"
MANIFEST_FILE = MANIFEST_DIR / "epic_p23_102_exact_manifest.json"
FFPROBE_RAW_FILE = VALIDATION_DIR / "ffprobe_raw.json"
VALIDATION_FILE = VALIDATION_DIR / "exact_validation_report.json"
REVIEW_FILE = ROOT / "docs/review/epic_p23_102_exact_acquisition.md"
RESULT_FILE = (
    ROOT / "orchestration/results/206_epic_p23_102_exact_acquisition.txt"
)

README_EVIDENCE = (
    ROOT
    / "data/source_recon/assembly_epic_access_v2/metadata/epic"
    / "data_bris_readme.txt"
)
MD5_EVIDENCE = (
    ROOT
    / "data/source_recon/assembly_epic_access_v2/metadata/epic/md5.csv"
)
PREFLIGHT_EVIDENCE = (
    ROOT / "data/rehearsal_plan/epic_p23_102_vsa_preflight_v1.json"
)
INPUT_EVIDENCE = {
    "official_data_bris_readme": {
        "path": README_EVIDENCE,
        "bytes": 6466,
        "sha256": (
            "4198f81adff3055373fbf635475992d5b2227df8f9796d670f3bcf08fa74e260"
        ),
    },
    "official_md5_manifest": {
        "path": MD5_EVIDENCE,
        "bytes": 236630,
        "sha256": (
            "3f9c31899ff5807c8f0fed5d26a8fe62300f3f4c40dc3eea767345212c2e83c7"
        ),
    },
    "exact_asset_preflight": {
        "path": PREFLIGHT_EVIDENCE,
        "bytes": 8482,
        "sha256": (
            "11f757f251e385461b15dbcc7fa9dde601f4ffdd2d60799594e9306cec85ef0b"
        ),
    },
}

CONTENT_RANGE_RE = re.compile(r"bytes\s+(\d+)-(\d+)/(\d+)", re.IGNORECASE)
_LOCK_DESCRIPTOR: int | None = None


class AcquisitionError(RuntimeError):
    """A repairable transfer or local execution failure."""


class NoGoError(AcquisitionError):
    """An immutable identity, rights, or exactness failure."""


@dataclass(frozen=True)
class TransferOptions:
    chunk_bytes: int
    attempt_rounds: int
    connect_timeout_seconds: int
    max_time_seconds: int


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    ).encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write(path: Path, payload: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700 if path.is_relative_to(BASE) else 0o755)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        mode,
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


def write_json(path: Path, value: Any, *, public: bool = False) -> None:
    atomic_write(path, canonical_json_bytes(value), 0o644 if public else 0o600)


def write_text(path: Path, value: str, *, public: bool = False) -> None:
    atomic_write(path, value.encode(), 0o644 if public else 0o600)


def secure_directories() -> None:
    for path in (
        BASE,
        MEDIA_DIR,
        STAGING_DIR,
        LOG_DIR,
        MANIFEST_DIR,
        VALIDATION_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)
        os.chmod(path, 0o700)


def acquire_lock() -> None:
    global _LOCK_DESCRIPTOR
    try:
        _LOCK_DESCRIPTOR = os.open(
            LOCK_FILE,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        os.write(_LOCK_DESCRIPTOR, f"{os.getpid()}\n".encode())
        os.fsync(_LOCK_DESCRIPTOR)
    except FileExistsError as exc:
        raise AcquisitionError(f"ACQUISITION_LOCK_EXISTS:{LOCK_FILE}") from exc


def release_lock() -> None:
    global _LOCK_DESCRIPTOR
    if _LOCK_DESCRIPTOR is not None:
        os.close(_LOCK_DESCRIPTOR)
        _LOCK_DESCRIPTOR = None
    try:
        LOCK_FILE.unlink()
        fsync_directory(LOCK_FILE.parent)
    except FileNotFoundError:
        pass


def append_journal(record: Mapping[str, Any]) -> None:
    payload = json.dumps(
        dict(record), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    descriptor = os.open(
        JOURNAL_FILE,
        os.O_WRONLY | os.O_APPEND | os.O_CREAT,
        0o600,
    )
    try:
        os.write(descriptor, (payload + "\n").encode())
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.chmod(JOURNAL_FILE, 0o600)


def hash_file(path: Path) -> dict[str, Any]:
    md5 = hashlib.md5(usedforsecurity=False)
    sha256 = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while block := handle.read(HASH_BLOCK_BYTES):
            size += len(block)
            md5.update(block)
            sha256.update(block)
    return {"bytes": size, "md5": md5.hexdigest(), "sha256": sha256.hexdigest()}


def file_sha256_and_size(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while block := handle.read(HASH_BLOCK_BYTES):
            size += len(block)
            digest.update(block)
    return {"bytes": size, "sha256": digest.hexdigest()}


def validate_official_url(url: str) -> None:
    parsed = urlsplit(url)
    if (
        url != OFFICIAL_URL
        or parsed.scheme != "https"
        or parsed.hostname != "data.bris.ac.uk"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
        or parsed.query
        or parsed.fragment
        or parsed.path
        != "/datasets/2g1n6qdydwa9u22shpxqzp0t8m/P23/videos/P23_102.MP4"
    ):
        raise NoGoError("FROZEN_OFFICIAL_URL_MISMATCH")


def verify_evidence() -> dict[str, Any]:
    records: dict[str, Any] = {}
    for label, expected in INPUT_EVIDENCE.items():
        observed = file_sha256_and_size(expected["path"])
        if observed["bytes"] != expected["bytes"] or observed["sha256"] != expected[
            "sha256"
        ]:
            raise NoGoError(f"FROZEN_INPUT_EVIDENCE_MISMATCH:{label}")
        records[label] = {
            "path": expected["path"].relative_to(ROOT).as_posix(),
            **observed,
            "verified": True,
        }

    readme = README_EVIDENCE.read_text(encoding="utf-8")
    required_license_fragments = (
        "All files in this dataset are copyright by us",
        "Creative Commons Attribution-NonCommerial 4.0 International License",
        "You\nmay not use the material for commercial purposes.",
    )
    if any(fragment not in readme for fragment in required_license_fragments):
        raise NoGoError("OFFICIAL_CC_BY_NC_LICENSE_EVIDENCE_MISSING")

    matches = []
    with MD5_EVIDENCE.open(newline="", encoding="utf-8") as handle:
        for row in csv.reader(handle):
            if len(row) >= 3 and row[1] == OBJECT_PATH:
                matches.append(row[:3])
    if matches != [[OFFICIAL_MD5, OBJECT_PATH, "100"]]:
        raise NoGoError("OFFICIAL_MD5_ROW_NOT_EXACTLY_BOUND")

    preflight = json.loads(PREFLIGHT_EVIDENCE.read_text(encoding="utf-8"))
    authoritative = preflight.get("authoritative_asset", {})
    rights = preflight.get("rights_and_gate", {})
    if (
        authoritative.get("url") != OFFICIAL_URL
        or authoritative.get("expected_size_bytes_from_retained_head")
        != EXPECTED_BYTES
        or authoritative.get("expected_md5_from_official_manifest")
        != OFFICIAL_MD5
        or rights.get("operative_dataset_license") != LICENSE_SPDX
        or rights.get("commercial_use_authorized") is not False
    ):
        raise NoGoError("PREFLIGHT_EXACT_IDENTITY_OR_RIGHTS_MISMATCH")
    return records


def provenance_record(evidence: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "av-trace.epic-p23-102-provenance/1.0",
        "task_id": TASK_ID,
        "generated_at_utc": utc_now(),
        "asset": {
            "dataset": "EPIC-KITCHENS-100",
            "asset_id": ASSET_ID,
            "participant_id": PARTICIPANT_ID,
            "official_object_path": OBJECT_PATH,
            "official_url": OFFICIAL_URL,
            "expected_bytes": EXPECTED_BYTES,
            "official_md5": OFFICIAL_MD5,
            "official_md5_manifest_version": 100,
        },
        "evidence": dict(evidence),
        "license_and_usage_boundary": {
            "operative_license": LICENSE_SPDX,
            "attribution_required": True,
            "noncommercial_only": True,
            "commercial_use_authorized": False,
            "authorized_use": (
                "Restricted local acquisition and technical validation for "
                "noncommercial research."
            ),
            "public_release_or_redistribution_authorized": False,
            "human_annotation_authority_granted": False,
            "privacy_or_release_clearance_granted": False,
            "semantic_review_performed": False,
            "semantic_annotations_opened_or_used": False,
        },
        "scope_exclusion": {
            "captaincook_25_109_acquired": False,
            "other_epic_assets_acquired": False,
        },
    }


def parse_header_blocks(raw: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in raw.replace("\r\n", "\n").split("\n"):
        status = re.match(r"^HTTP/\S+\s+(\d{3})(?:\s+(.*))?$", line)
        if status:
            if current is not None:
                blocks.append(current)
            current = {
                "status_code": int(status.group(1)),
                "reason": status.group(2) or "",
                "headers": {},
            }
        elif current is not None and ":" in line:
            key, value = line.split(":", 1)
            normalized = key.strip().lower()
            if normalized in {
                "content-range",
                "content-length",
                "content-type",
                "accept-ranges",
                "etag",
                "last-modified",
                "location",
            }:
                current["headers"][normalized] = value.strip()
    if current is not None:
        blocks.append(current)
    return blocks


def parse_content_range(value: str | None) -> tuple[int, int, int]:
    match = CONTENT_RANGE_RE.fullmatch((value or "").strip())
    if match is None:
        raise AcquisitionError(f"INVALID_CONTENT_RANGE:{value!r}")
    start, end, total = map(int, match.groups())
    if start < 0 or end < start or total <= end:
        raise AcquisitionError(f"INCONSISTENT_CONTENT_RANGE:{value!r}")
    return start, end, total


def validate_range_response(
    *,
    blocks: Sequence[Mapping[str, Any]],
    requested_start: int,
    requested_end: int,
    body_bytes: int,
) -> dict[str, Any]:
    candidates = [
        block
        for block in blocks
        if block.get("headers", {}).get("content-range") is not None
    ]
    if not candidates:
        raise AcquisitionError("NO_HTTP_CONTENT_RANGE_RESPONSE")
    final = candidates[-1]
    if final.get("status_code") != 206:
        raise AcquisitionError(f"RANGE_HTTP_STATUS_NOT_206:{final.get('status_code')}")
    headers = final["headers"]
    start, end, total = parse_content_range(headers.get("content-range"))
    if start != requested_start:
        raise AcquisitionError(f"RANGE_START_MISMATCH:{start}!={requested_start}")
    if end != requested_end:
        raise AcquisitionError(f"RANGE_END_MISMATCH:{end}!={requested_end}")
    if total != EXPECTED_BYTES:
        raise NoGoError(f"RANGE_TOTAL_MISMATCH:{total}!={EXPECTED_BYTES}")
    content_type = (headers.get("content-type") or "").split(";", 1)[0].lower()
    if content_type != "video/mp4":
        raise NoGoError(f"CONTENT_TYPE_NOT_VIDEO_MP4:{content_type!r}")
    promised_bytes = end - start + 1
    if body_bytes <= 0 or body_bytes > promised_bytes:
        raise AcquisitionError(
            f"RANGE_BODY_SIZE_INVALID:{body_bytes}/{promised_bytes}"
        )
    return {
        "status_code": 206,
        "content_range": headers["content-range"],
        "content_type": content_type,
        "etag": headers.get("etag"),
        "last_modified": headers.get("last-modified"),
        "promised_bytes": promised_bytes,
        "accepted_prefix_bytes": body_bytes,
    }


def sanitize_stderr(value: str) -> str:
    value = value.replace(OFFICIAL_URL, "<official-url>")
    for proxy in PROXIES:
        value = value.replace(proxy, "<proxy>")
    return value[-4000:]


def run_range_request(
    *,
    proxy: str,
    start: int,
    end: int,
    options: TransferOptions,
) -> dict[str, Any]:
    for path in (SEGMENT_MEDIA, HEADER_FILE):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    descriptor = os.open(
        SEGMENT_MEDIA,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    os.close(descriptor)
    command = [
        "curl",
        "--proxy",
        proxy,
        "--location",
        "--silent",
        "--show-error",
        "--connect-timeout",
        str(options.connect_timeout_seconds),
        "--max-time",
        str(options.max_time_seconds),
        "--range",
        f"{start}-{end}",
        "--dump-header",
        str(HEADER_FILE),
        "--output",
        str(SEGMENT_MEDIA),
        OFFICIAL_URL,
    ]
    started = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        check=False,
    )
    elapsed = round(time.monotonic() - started, 6)
    os.chmod(SEGMENT_MEDIA, 0o600)
    body_bytes = SEGMENT_MEDIA.stat().st_size
    raw_headers = (
        HEADER_FILE.read_text(encoding="iso-8859-1", errors="replace")
        if HEADER_FILE.exists()
        else ""
    )
    return {
        "proxy_route": urlsplit(proxy).hostname,
        "requested_range": f"bytes={start}-{end}",
        "curl_exit_code": completed.returncode,
        "elapsed_seconds": elapsed,
        "body_bytes": body_bytes,
        "header_blocks": parse_header_blocks(raw_headers),
        "stderr": sanitize_stderr(
            completed.stderr.decode("utf-8", errors="replace").strip()
        ),
    }


def append_segment(expected_offset: int) -> int:
    if PART_MEDIA.exists() and PART_MEDIA.stat().st_size != expected_offset:
        raise AcquisitionError("CANONICAL_PART_SIZE_CHANGED_DURING_REQUEST")
    if not PART_MEDIA.exists():
        descriptor = os.open(
            PART_MEDIA,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        os.close(descriptor)
    copied = 0
    with SEGMENT_MEDIA.open("rb") as source, PART_MEDIA.open("ab") as target:
        while block := source.read(COPY_BLOCK_BYTES):
            target.write(block)
            copied += len(block)
        target.flush()
        os.fsync(target.fileno())
    os.chmod(PART_MEDIA, 0o600)
    SEGMENT_MEDIA.unlink()
    try:
        HEADER_FILE.unlink()
    except FileNotFoundError:
        pass
    fsync_directory(STAGING_DIR)
    return copied


def remove_ephemeral_transfer_files() -> None:
    for path in (SEGMENT_MEDIA, HEADER_FILE):
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def pre_transfer_free_space(options: TransferOptions) -> dict[str, int]:
    completed = PART_MEDIA.stat().st_size if PART_MEDIA.exists() else 0
    if completed > EXPECTED_BYTES:
        raise NoGoError(f"STAGING_PART_EXCEEDS_EXPECTED_BYTES:{completed}")
    remaining = EXPECTED_BYTES - completed
    temporary_peak = min(options.chunk_bytes, remaining)
    required = remaining + temporary_peak + FREE_SPACE_MARGIN_BYTES
    disk = shutil.disk_usage(BASE)
    if disk.free < required:
        raise AcquisitionError(f"INSUFFICIENT_FREE_SPACE:{disk.free}<{required}")
    return {
        "part_bytes": completed,
        "remaining_bytes": remaining,
        "free_bytes": disk.free,
        "required_free_bytes": required,
        "free_space_margin_bytes": FREE_SPACE_MARGIN_BYTES,
        "temporary_segment_peak_bytes": temporary_peak,
    }


def write_progress(
    *,
    status: str,
    disposition: str = "REPAIR",
    message: str | None = None,
    transfer: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    part_bytes = PART_MEDIA.stat().st_size if PART_MEDIA.exists() else 0
    final_bytes = FINAL_MEDIA.stat().st_size if FINAL_MEDIA.exists() else 0
    record = {
        "schema_version": "av-trace.epic-p23-102-progress/1.0",
        "task_id": TASK_ID,
        "updated_at_utc": utc_now(),
        "asset_id": ASSET_ID,
        "status": status,
        "disposition": disposition,
        "message": message,
        "expected_bytes": EXPECTED_BYTES,
        "resumable_part": {
            "path": PART_MEDIA.relative_to(ROOT).as_posix(),
            "exists": PART_MEDIA.exists(),
            "bytes": part_bytes,
            "mode": (
                oct(stat.S_IMODE(PART_MEDIA.stat().st_mode))
                if PART_MEDIA.exists()
                else None
            ),
        },
        "final_media": {
            "path": FINAL_MEDIA.relative_to(ROOT).as_posix(),
            "exists": FINAL_MEDIA.exists(),
            "bytes": final_bytes,
        },
        "partial_is_complete": False,
        "transfer": dict(transfer or {}),
    }
    write_json(PROGRESS_FILE, record)
    return record


def transfer_exact(options: TransferOptions) -> dict[str, Any]:
    if FINAL_MEDIA.exists():
        if FINAL_MEDIA.stat().st_size != EXPECTED_BYTES:
            raise NoGoError("EXISTING_FINAL_FILE_HAS_WRONG_SIZE")
        os.chmod(FINAL_MEDIA, 0o600)
        return {
            "status": "EXISTING_FINAL_REUSED_FOR_EXACT_REVALIDATION",
            "attempt_count": 0,
            "accepted_bytes_this_run": 0,
            "proxy_order": [urlsplit(proxy).hostname for proxy in PROXIES],
        }

    free_space = pre_transfer_free_space(options)
    if not PART_MEDIA.exists():
        descriptor = os.open(
            PART_MEDIA,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        os.close(descriptor)
    os.chmod(PART_MEDIA, 0o600)
    remove_ephemeral_transfer_files()

    attempt_count = 0
    accepted_this_run = 0
    proxies_used: list[str] = []
    while PART_MEDIA.stat().st_size < EXPECTED_BYTES:
        offset = PART_MEDIA.stat().st_size
        end = min(EXPECTED_BYTES - 1, offset + options.chunk_bytes - 1)
        made_progress = False
        failures: list[str] = []
        for round_number in range(1, options.attempt_rounds + 1):
            for proxy_number, proxy in enumerate(PROXIES, start=1):
                attempt_count += 1
                proxy_host = urlsplit(proxy).hostname or proxy
                proxies_used.append(proxy_host)
                write_progress(
                    status="TRANSFERRING",
                    transfer={
                        "current_offset": offset,
                        "current_end": end,
                        "attempt_count": attempt_count,
                        "attempt_round": round_number,
                        "proxy_position": proxy_number,
                        "proxy_route": proxy_host,
                        "accepted_bytes_this_run": accepted_this_run,
                        "free_space_check": free_space,
                    },
                )
                result = run_range_request(
                    proxy=proxy,
                    start=offset,
                    end=end,
                    options=options,
                )
                journal: dict[str, Any] = {
                    "recorded_at_utc": utc_now(),
                    "attempt": attempt_count,
                    "round": round_number,
                    "proxy_position": proxy_number,
                    **result,
                    "part_bytes_before": offset,
                }
                try:
                    response = validate_range_response(
                        blocks=result["header_blocks"],
                        requested_start=offset,
                        requested_end=end,
                        body_bytes=result["body_bytes"],
                    )
                    copied = append_segment(offset)
                    if copied != result["body_bytes"]:
                        raise AcquisitionError("APPENDED_BYTE_COUNT_MISMATCH")
                    accepted_this_run += copied
                    journal.update(
                        {
                            "outcome": (
                                "FULL_RANGE_ACCEPTED"
                                if copied == response["promised_bytes"]
                                else "VALID_PARTIAL_RANGE_PREFIX_ACCEPTED_FOR_RESUME"
                            ),
                            "validated_response": response,
                            "accepted_bytes": copied,
                            "part_bytes_after": PART_MEDIA.stat().st_size,
                        }
                    )
                    append_journal(journal)
                    made_progress = True
                    break
                except NoGoError:
                    journal["outcome"] = "NO_GO"
                    append_journal(journal)
                    remove_ephemeral_transfer_files()
                    raise
                except AcquisitionError as exc:
                    failure = str(exc)
                    failures.append(f"{proxy_host}:{failure}")
                    journal.update(
                        {
                            "outcome": "FAILED_NO_BYTES_ACCEPTED",
                            "validation_error": failure,
                            "accepted_bytes": 0,
                            "part_bytes_after": PART_MEDIA.stat().st_size,
                        }
                    )
                    append_journal(journal)
                    remove_ephemeral_transfer_files()
            if made_progress:
                break
            if round_number < options.attempt_rounds:
                time.sleep(min(10, 2**round_number))
        if not made_progress:
            raise AcquisitionError(
                "BOUNDED_RANGE_RETRIES_EXHAUSTED:" + "|".join(failures[-6:])
            )

    if PART_MEDIA.stat().st_size != EXPECTED_BYTES:
        raise AcquisitionError("TRANSFER_ENDED_WITH_NONEXACT_STAGING_SIZE")
    return {
        "status": "RANGE_TRANSFER_COMPLETE_IN_STAGING",
        "attempt_count": attempt_count,
        "accepted_bytes_this_run": accepted_this_run,
        "proxy_order": [urlsplit(proxy).hostname for proxy in PROXIES],
        "proxies_used_in_order": proxies_used,
        "free_space_check": free_space,
    }


def verify_and_promote(transfer: Mapping[str, Any]) -> dict[str, Any]:
    if FINAL_MEDIA.exists():
        digest = hash_file(FINAL_MEDIA)
        promoted = False
    else:
        if not PART_MEDIA.exists():
            raise AcquisitionError("NO_COMPLETE_STAGING_FILE_TO_VERIFY")
        digest = hash_file(PART_MEDIA)
        promoted = True
    if digest["bytes"] != EXPECTED_BYTES:
        raise AcquisitionError(
            f"EXACT_BYTE_COUNT_FAILED:{digest['bytes']}!={EXPECTED_BYTES}"
        )
    if digest["md5"] != OFFICIAL_MD5:
        raise NoGoError(f"OFFICIAL_MD5_FAILED:{digest['md5']}!={OFFICIAL_MD5}")
    if promoted:
        os.chmod(PART_MEDIA, 0o600)
        os.replace(PART_MEDIA, FINAL_MEDIA)
        os.chmod(FINAL_MEDIA, 0o600)
        fsync_directory(FINAL_MEDIA.parent)
        fsync_directory(STAGING_DIR)
    return {
        "path": FINAL_MEDIA.relative_to(ROOT).as_posix(),
        "bytes": digest["bytes"],
        "md5": digest["md5"],
        "sha256": digest["sha256"],
        "official_md5_verified": True,
        "atomic_staging_promotion": promoted,
        "mode": oct(stat.S_IMODE(FINAL_MEDIA.stat().st_mode)),
        "transfer": dict(transfer),
    }


def resolve_ffprobe(requested: str | None) -> str:
    candidate = requested or os.environ.get("FFPROBE") or shutil.which("ffprobe")
    if not candidate:
        raise AcquisitionError("FFPROBE_NOT_FOUND")
    resolved = Path(candidate)
    if resolved.is_absolute():
        if not resolved.is_file() or not os.access(resolved, os.X_OK):
            raise AcquisitionError(f"FFPROBE_NOT_EXECUTABLE:{candidate}")
        return str(resolved)
    found = shutil.which(candidate)
    if not found:
        raise AcquisitionError(f"FFPROBE_NOT_FOUND:{candidate}")
    return found


def run_ffprobe(ffprobe: str) -> dict[str, Any]:
    command = [
        ffprobe,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(FINAL_MEDIA),
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise AcquisitionError(
            "FFPROBE_FAILED:"
            + sanitize_stderr(
                completed.stderr.decode("utf-8", errors="replace").strip()
            )
        )
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AcquisitionError("FFPROBE_RETURNED_INVALID_JSON") from exc
    write_json(FFPROBE_RAW_FILE, report)
    return report


def numeric_duration(stream: Mapping[str, Any]) -> float:
    try:
        value = float(stream["duration"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AcquisitionError("FFPROBE_STREAM_DURATION_MISSING") from exc
    if value <= 0:
        raise AcquisitionError("FFPROBE_STREAM_DURATION_NOT_POSITIVE")
    return value


def validate_ffprobe_report(report: Mapping[str, Any]) -> dict[str, Any]:
    streams = report.get("streams")
    if not isinstance(streams, list):
        raise AcquisitionError("FFPROBE_STREAM_LIST_MISSING")
    videos = [item for item in streams if item.get("codec_type") == "video"]
    audios = [item for item in streams if item.get("codec_type") == "audio"]
    if len(videos) != 1 or len(audios) != 1:
        raise NoGoError(
            f"REQUIRED_SINGLE_AV_STREAMS_MISSING:video={len(videos)},audio={len(audios)}"
        )
    video = videos[0]
    audio = audios[0]
    video_checks = {
        "codec_name_hevc": video.get("codec_name") == "hevc",
        "codec_tag_hvc1": video.get("codec_tag_string") == "hvc1",
        "width_1920": video.get("width") == 1920,
        "height_1080": video.get("height") == 1080,
    }
    audio_checks = {
        "codec_name_aac": audio.get("codec_name") == "aac",
        "codec_tag_mp4a": audio.get("codec_tag_string") == "mp4a",
        "sample_rate_48000": str(audio.get("sample_rate")) == "48000",
        "channels_2": audio.get("channels") == 2,
        "channel_layout_stereo": audio.get("channel_layout") == "stereo",
    }
    if not all(video_checks.values()):
        raise NoGoError(f"VIDEO_STREAM_IDENTITY_FAILED:{video_checks}")
    if not all(audio_checks.values()):
        raise NoGoError(f"AUDIO_STREAM_IDENTITY_FAILED:{audio_checks}")

    video_duration = numeric_duration(video)
    audio_duration = numeric_duration(audio)
    duration_delta = abs(video_duration - audio_duration)
    if duration_delta > STREAM_DURATION_TOLERANCE_SECONDS:
        raise NoGoError(
            f"AV_STREAM_DURATION_DELTA_TOO_LARGE:{duration_delta:.6f}"
        )
    official_delta = abs(video_duration - OFFICIAL_DURATION_SECONDS)
    if official_delta > OFFICIAL_DURATION_TOLERANCE_SECONDS:
        raise NoGoError(
            f"VIDEO_DURATION_OFFICIAL_MISMATCH:{official_delta:.6f}"
        )
    try:
        format_duration = float(report.get("format", {}).get("duration"))
    except (TypeError, ValueError) as exc:
        raise AcquisitionError("FFPROBE_FORMAT_DURATION_MISSING") from exc
    format_delta = abs(format_duration - max(video_duration, audio_duration))
    if format_delta > STREAM_DURATION_TOLERANCE_SECONDS:
        raise NoGoError(
            f"CONTAINER_STREAM_DURATION_DELTA_TOO_LARGE:{format_delta:.6f}"
        )
    return {
        "ffprobe_passed": True,
        "video": {
            "index": video.get("index"),
            "codec_name": video.get("codec_name"),
            "codec_tag_string": video.get("codec_tag_string"),
            "width": video.get("width"),
            "height": video.get("height"),
            "duration_seconds": video_duration,
            "checks": video_checks,
        },
        "audio": {
            "index": audio.get("index"),
            "codec_name": audio.get("codec_name"),
            "codec_tag_string": audio.get("codec_tag_string"),
            "sample_rate_hz": int(audio["sample_rate"]),
            "channels": audio.get("channels"),
            "channel_layout": audio.get("channel_layout"),
            "duration_seconds": audio_duration,
            "checks": audio_checks,
        },
        "container_duration_seconds": format_duration,
        "av_duration_delta_seconds": duration_delta,
        "container_stream_duration_delta_seconds": format_delta,
        "official_video_duration_delta_seconds": official_delta,
        "tolerances_seconds": {
            "av_and_container": STREAM_DURATION_TOLERANCE_SECONDS,
            "official_video_duration": OFFICIAL_DURATION_TOLERANCE_SECONDS,
        },
    }


def create_manifest(
    *,
    evidence: Mapping[str, Any],
    media: Mapping[str, Any],
    technical: Mapping[str, Any],
) -> dict[str, Any]:
    manifest = {
        "schema_version": "av-trace.epic-p23-102-exact-manifest/1.0",
        "record_type": "command_independent_exact_source_manifest",
        "task_id": TASK_ID,
        "generated_at_utc": utc_now(),
        "status": "COMPLETE_VERIFIED_READY",
        "source": {
            "dataset": "EPIC-KITCHENS-100",
            "asset_id": ASSET_ID,
            "participant_id": PARTICIPANT_ID,
            "official_object_path": OBJECT_PATH,
            "official_url": OFFICIAL_URL,
            "license": LICENSE_SPDX,
        },
        "media": {
            "path": media["path"],
            "bytes": media["bytes"],
            "expected_bytes": EXPECTED_BYTES,
            "md5": media["md5"],
            "official_md5": OFFICIAL_MD5,
            "official_md5_verified": media["official_md5_verified"],
            "sha256": media["sha256"],
            "mode": media["mode"],
            "symlink": FINAL_MEDIA.is_symlink(),
        },
        "technical_validation": technical,
        "provenance_evidence": dict(evidence),
        "license_and_usage_boundary": provenance_record(evidence)[
            "license_and_usage_boundary"
        ],
        "acquisition_properties": {
            "resumable_exact_byte_ranges": True,
            "ordered_proxy_policy": [
                "https://proxy.example.invalid:3128",
                "https://proxy.example.invalid:3128",
            ],
            "restrictive_directory_mode": "0700",
            "restrictive_media_mode": "0600",
            "free_space_checked": True,
            "atomic_finalization": True,
            "partial_never_labeled_complete": True,
            "bounded_retries": True,
        },
        "scope": {
            "exact_asset_count": 1,
            "semantic_annotations_opened_or_used": False,
            "semantic_review_performed": False,
            "captaincook_25_109_acquired": False,
        },
    }
    write_json(MANIFEST_FILE, manifest)
    return manifest


def enforce_permissions() -> None:
    for directory in (
        BASE,
        MEDIA_DIR,
        STAGING_DIR,
        LOG_DIR,
        MANIFEST_DIR,
        VALIDATION_DIR,
    ):
        os.chmod(directory, 0o700)
    for path in BASE.rglob("*"):
        if path.is_dir():
            os.chmod(path, 0o700)
        elif path.is_file():
            os.chmod(path, 0o600)
    if FINAL_MEDIA.is_symlink():
        raise NoGoError("FINAL_MEDIA_MUST_NOT_BE_SYMLINK")


def review_markdown(
    *,
    disposition: str,
    message: str,
    media: Mapping[str, Any] | None = None,
    technical: Mapping[str, Any] | None = None,
) -> str:
    ready = disposition == "READY"
    media = media or {}
    technical = technical or {}
    token = (
        "EPIC_P23_102_ACQUISITION_READY"
        if ready
        else (
            "EPIC_P23_102_ACQUISITION_NO_GO"
            if disposition == "NO_GO"
            else "EPIC_P23_102_ACQUISITION_REPAIR"
        )
    )
    video = technical.get("video", {})
    audio = technical.get("audio", {})
    part_bytes = PART_MEDIA.stat().st_size if PART_MEDIA.exists() else 0
    return f"""# EPIC P23_102 exact acquisition

**Date:** 2026-10-13  
**Disposition:** `{token}`

## Outcome

{message}

The scope is exactly the official `P23/videos/P23_102.MP4` object. No semantic
annotation body was opened or used, no semantic review was performed, and
CaptainCook4D `25_109` was not acquired.

## Exact identity

| Field | Expected | Observed |
|---|---:|---:|
| Bytes | `{EXPECTED_BYTES}` | `{media.get("bytes", "not verified")}` |
| Official MD5 | `{OFFICIAL_MD5}` | `{media.get("md5", "not verified")}` |
| SHA-256 | computed locally | `{media.get("sha256", "not verified")}` |
| Final mode | `0600` | `{media.get("mode", "not finalized")}` |

Canonical resumable staging bytes retained: `{part_bytes}`.

## Stream validation

| Stream fact | Required | Observed |
|---|---|---|
| Video codec tag | `hvc1` | `{video.get("codec_tag_string", "not verified")}` |
| Video dimensions | `1920x1080` | `{video.get("width", "?")}x{video.get("height", "?")}` |
| Video duration | near official `3569.52 s` | `{video.get("duration_seconds", "not verified")}` |
| Audio codec tag | `mp4a` | `{audio.get("codec_tag_string", "not verified")}` |
| Audio layout | stereo | `{audio.get("channel_layout", "not verified")}` |
| Audio sample rate | `48000 Hz` | `{audio.get("sample_rate_hz", "not verified")}` |
| A/V duration delta | `<= {STREAM_DURATION_TOLERANCE_SECONDS} s` | `{technical.get("av_duration_delta_seconds", "not verified")}` |

## Provenance and usage boundary

The official Data.Bris README binds the deposit to CC BY-NC 4.0. Attribution is
required and commercial use is not authorized. This acquisition is restricted
to local noncommercial research and technical validation. It does not authorize
public release, redistribution, human annotation, or imply privacy/release
clearance.

The command-independent manifest is
`data/restricted/epic_p23_102_source_v1/manifests/epic_p23_102_exact_manifest.json`.
Transfer progress, range-attempt records, hashes, raw ffprobe output, and the
validation report are retained under the restricted source directory.

`{token}`
"""


def write_summary(
    *,
    disposition: str,
    message: str,
    media: Mapping[str, Any] | None = None,
    technical: Mapping[str, Any] | None = None,
) -> None:
    token = (
        "EPIC_P23_102_ACQUISITION_READY"
        if disposition == "READY"
        else (
            "EPIC_P23_102_ACQUISITION_NO_GO"
            if disposition == "NO_GO"
            else "EPIC_P23_102_ACQUISITION_REPAIR"
        )
    )
    write_text(
        REVIEW_FILE,
        review_markdown(
            disposition=disposition,
            message=message,
            media=media,
            technical=technical,
        ),
        public=True,
    )
    result = {
        "task_id": TASK_ID,
        "date": "2026-10-13",
        "disposition": disposition,
        "message": message,
        "final_media": (media or {}).get("path"),
        "bytes": (media or {}).get("bytes"),
        "md5": (media or {}).get("md5"),
        "sha256": (media or {}).get("sha256"),
        "ffprobe_passed": (technical or {}).get("ffprobe_passed", False),
        "resumable_staging_bytes": (
            PART_MEDIA.stat().st_size if PART_MEDIA.exists() else 0
        ),
        "semantic_annotations_opened_or_used": False,
        "captaincook_25_109_acquired": False,
        "final_token": token,
    }
    write_text(
        RESULT_FILE,
        canonical_json_bytes(result).decode() + token + "\n",
        public=True,
    )


def exact_validation_report(
    *,
    disposition: str,
    evidence: Mapping[str, Any],
    media: Mapping[str, Any] | None,
    technical: Mapping[str, Any] | None,
    message: str,
) -> dict[str, Any]:
    checks = {
        "exact_bytes": bool(media and media.get("bytes") == EXPECTED_BYTES),
        "official_md5": bool(media and media.get("md5") == OFFICIAL_MD5),
        "sha256_computed": bool(media and len(str(media.get("sha256", ""))) == 64),
        "ffprobe_stream_identity_and_durations": bool(
            technical and technical.get("ffprobe_passed")
        ),
        "restricted_media_mode": bool(media and media.get("mode") == "0o600"),
        "semantic_annotations_unused": True,
        "captaincook_25_109_not_acquired": True,
    }
    report = {
        "schema_version": "av-trace.epic-p23-102-validation/1.0",
        "task_id": TASK_ID,
        "generated_at_utc": utc_now(),
        "disposition": disposition,
        "message": message,
        "all_exact_checks_passed": disposition == "READY" and all(checks.values()),
        "checks": checks,
        "evidence": dict(evidence),
        "media": dict(media or {}),
        "technical": dict(technical or {}),
    }
    write_json(VALIDATION_FILE, report)
    return report


def run_execute(args: argparse.Namespace) -> int:
    secure_directories()
    acquire_lock()
    evidence: dict[str, Any] = {}
    media: dict[str, Any] | None = None
    technical: dict[str, Any] | None = None
    try:
        validate_official_url(OFFICIAL_URL)
        evidence = verify_evidence()
        write_json(PROVENANCE_FILE, provenance_record(evidence))
        options = TransferOptions(
            chunk_bytes=args.chunk_bytes,
            attempt_rounds=args.attempt_rounds,
            connect_timeout_seconds=args.connect_timeout,
            max_time_seconds=args.max_time,
        )
        write_progress(status="PRE_TRANSFER_VALIDATED")
        transfer = transfer_exact(options)
        write_progress(status="HASHING_AND_EXACT_VERIFICATION", transfer=transfer)
        media = verify_and_promote(transfer)
        write_progress(status="FFPROBE_VALIDATION", transfer=transfer)
        ffprobe = resolve_ffprobe(args.ffprobe)
        technical = validate_ffprobe_report(run_ffprobe(ffprobe))
        manifest = create_manifest(
            evidence=evidence,
            media=media,
            technical=technical,
        )
        del manifest
        enforce_permissions()
        message = (
            "The exact official object passed byte-count, official MD5, local "
            "SHA-256, restrictive-custody, and ffprobe stream checks."
        )
        report = exact_validation_report(
            disposition="READY",
            evidence=evidence,
            media=media,
            technical=technical,
            message=message,
        )
        if not report["all_exact_checks_passed"]:
            raise AcquisitionError("FINAL_VALIDATION_BOOLEAN_DID_NOT_CLOSE")
        write_progress(
            status="COMPLETE_VERIFIED_READY",
            disposition="READY",
            message=message,
            transfer=transfer,
        )
        write_summary(
            disposition="READY",
            message=message,
            media=media,
            technical=technical,
        )
        print("EPIC_P23_102_ACQUISITION_READY")
        return 0
    except KeyboardInterrupt:
        message = "Interrupted; exact resumable staging is preserved."
        write_progress(status="INTERRUPTED_RESUMABLE", message=message)
        exact_validation_report(
            disposition="REPAIR",
            evidence=evidence,
            media=media,
            technical=technical,
            message=message,
        )
        write_summary(
            disposition="REPAIR",
            message=message,
            media=media,
            technical=technical,
        )
        print("EPIC_P23_102_ACQUISITION_REPAIR")
        return 130
    except NoGoError as exc:
        message = str(exc)
        write_progress(status="NO_GO", disposition="NO_GO", message=message)
        exact_validation_report(
            disposition="NO_GO",
            evidence=evidence,
            media=media,
            technical=technical,
            message=message,
        )
        write_summary(
            disposition="NO_GO",
            message=message,
            media=media,
            technical=technical,
        )
        print("EPIC_P23_102_ACQUISITION_NO_GO")
        return 3
    except (AcquisitionError, OSError, subprocess.SubprocessError) as exc:
        message = str(exc)
        write_progress(status="REPAIR_REQUIRED", message=message)
        exact_validation_report(
            disposition="REPAIR",
            evidence=evidence,
            media=media,
            technical=technical,
            message=message,
        )
        write_summary(
            disposition="REPAIR",
            message=message,
            media=media,
            technical=technical,
        )
        print("EPIC_P23_102_ACQUISITION_REPAIR")
        return 2
    finally:
        release_lock()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--plan-only", action="store_true")
    parser.add_argument("--ffprobe")
    parser.add_argument("--chunk-bytes", type=int, default=DEFAULT_CHUNK_BYTES)
    parser.add_argument(
        "--attempt-rounds", type=int, default=DEFAULT_ATTEMPT_ROUNDS
    )
    parser.add_argument(
        "--connect-timeout",
        type=int,
        default=DEFAULT_CONNECT_TIMEOUT_SECONDS,
    )
    parser.add_argument("--max-time", type=int, default=DEFAULT_MAX_TIME_SECONDS)
    args = parser.parse_args()
    if args.chunk_bytes <= 0:
        parser.error("--chunk-bytes must be positive")
    if args.attempt_rounds <= 0:
        parser.error("--attempt-rounds must be positive")
    if args.connect_timeout <= 0 or args.max_time <= 0:
        parser.error("timeouts must be positive")
    return args


def main() -> int:
    args = parse_args()
    if args.plan_only:
        validate_official_url(OFFICIAL_URL)
        evidence = verify_evidence()
        plan = {
            "task_id": TASK_ID,
            "asset_id": ASSET_ID,
            "official_url": OFFICIAL_URL,
            "expected_bytes": EXPECTED_BYTES,
            "official_md5": OFFICIAL_MD5,
            "proxy_order": list(PROXIES),
            "chunk_bytes": args.chunk_bytes,
            "attempt_rounds": args.attempt_rounds,
            "final_media": FINAL_MEDIA.relative_to(ROOT).as_posix(),
            "resumable_part": PART_MEDIA.relative_to(ROOT).as_posix(),
            "evidence": evidence,
            "semantic_annotations_opened_or_used": False,
            "captaincook_25_109_acquired": False,
        }
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    return run_execute(args)


if __name__ == "__main__":
    sys.exit(main())
