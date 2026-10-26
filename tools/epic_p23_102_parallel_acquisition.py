#!/usr/bin/env python3
"""Parallel, crash-resumable range acquisition for EPIC P23_102.

Acquisition writes only independent segment files.  The canonical staging
prefix is changed only by the separately requested ``--assemble`` phase.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import fcntl
import hashlib
import importlib.util
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any, Self
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
EXACT_TOOL = ROOT / "tools/epic_p23_102_exact_acquisition.py"

TASK_ID = 206
ASSET_ID = "P23_102"
OFFICIAL_URL = (
    "https://data.bris.ac.uk/datasets/"
    "2g1n6qdydwa9u22shpxqzp0t8m/P23/videos/P23_102.MP4"
)
EXPECTED_BYTES = 10_814_161_307
OFFICIAL_MD5 = "4698fcbf13782f6396029761eb3bd5f2"
EXPECTED_ETAG = '"5ea771bb-28493019b"'
ALIGNMENT_BYTES = 64 * 1024 * 1024
SEGMENT_BYTES = ALIGNMENT_BYTES
FREE_SPACE_MARGIN_BYTES = 1024 * 1024 * 1024
COPY_BLOCK_BYTES = 8 * 1024 * 1024
HASH_BLOCK_BYTES = 16 * 1024 * 1024

PROXIES = (
    "https://proxy.example.invalid:3128",
    "https://proxy.example.invalid:3128",
)
DEFAULT_CONCURRENCY = 8
MAX_CONCURRENCY = 32
DEFAULT_ATTEMPT_ROUNDS = 3
DEFAULT_CONNECT_TIMEOUT_SECONDS = 20
DEFAULT_MAX_TIME_SECONDS = 600

BASE = ROOT / "data/restricted/epic_p23_102_source_v1"
STAGING_DIR = BASE / "staging"
PART_MEDIA = STAGING_DIR / "P23_102.MP4.part"
FINAL_MEDIA = BASE / "media/P23/P23_102.MP4"
SEGMENT_DIR = STAGING_DIR / "parallel_segments"
SEGMENT_MANIFEST = SEGMENT_DIR / "manifest.json"
PARALLEL_LOCK_FILE = STAGING_DIR / ".parallel_acquisition.lock"
CANONICAL_LOCK_FILE = STAGING_DIR / ".acquisition.lock"
JOURNAL_FILE = BASE / "logs/range_attempts.jsonl"

CONTENT_RANGE_RE = re.compile(r"bytes\s+(\d+)-(\d+)/(\d+)", re.IGNORECASE)


class AcquisitionError(RuntimeError):
    """A retryable or locally repairable acquisition failure."""


class NoGoError(AcquisitionError):
    """An immutable identity or source-consistency failure."""


@dataclass(frozen=True)
class TransferOptions:
    concurrency: int
    attempt_rounds: int
    connect_timeout_seconds: int
    max_time_seconds: int


@dataclass(frozen=True)
class Segment:
    start: int
    end: int

    @property
    def byte_count(self) -> int:
        return self.end - self.start + 1

    @property
    def key(self) -> str:
        return f"{self.start}-{self.end}"

    @property
    def filename(self) -> str:
        return (
            f"P23_102.MP4.bytes-{self.start:012d}-{self.end:012d}.segment"
        )

    @property
    def path(self) -> Path:
        return SEGMENT_DIR / self.filename


@dataclass(frozen=True)
class PrefixSnapshot:
    byte_count: int
    sha256: str

    @property
    def identity(self) -> str:
        payload = f"{self.byte_count}:{self.sha256}".encode()
        return hashlib.sha256(payload).hexdigest()

    def record(self) -> dict[str, Any]:
        return {
            "id": self.identity,
            "bytes": self.byte_count,
            "sha256": self.sha256,
        }


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    ).encode()


def display_path(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write(path: Path, payload: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
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


def secure_parallel_directories() -> None:
    for directory in (BASE, STAGING_DIR, SEGMENT_DIR, JOURNAL_FILE.parent):
        directory.mkdir(parents=True, exist_ok=True)
        os.chmod(directory, 0o700)


class ExclusiveParallelLock:
    """Process lock shared by this tool's acquire and assemble modes."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or PARALLEL_LOCK_FILE
        self.descriptor: int | None = None

    def __enter__(self) -> Self:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        os.chmod(self.path, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(descriptor)
            raise AcquisitionError(
                f"PARALLEL_ACQUISITION_OR_ASSEMBLY_LOCKED:{self.path}"
            ) from exc
        os.ftruncate(descriptor, 0)
        os.write(
            descriptor,
            (
                json.dumps({"pid": os.getpid(), "locked_at_utc": utc_now()})
                + "\n"
            ).encode(),
        )
        os.fsync(descriptor)
        self.descriptor = descriptor
        return self

    def __exit__(self, *_args: object) -> None:
        if self.descriptor is not None:
            fcntl.flock(self.descriptor, fcntl.LOCK_UN)
            os.close(self.descriptor)
            self.descriptor = None


class CanonicalMutationGuard:
    """Interlock assembly with the existing sequential exact downloader."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or CANONICAL_LOCK_FILE
        self.descriptor: int | None = None

    def __enter__(self) -> Self:
        try:
            descriptor = os.open(
                self.path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError as exc:
            raise AcquisitionError(
                "CANONICAL_ACQUISITION_LOCK_PRESENT:"
                f"{self.path}; stop/wait for the sequential downloader"
            ) from exc
        os.write(
            descriptor,
            (
                f"{os.getpid()} parallel-assembly {utc_now()}\n"
            ).encode(),
        )
        os.fsync(descriptor)
        self.descriptor = descriptor
        fsync_directory(self.path.parent)
        return self

    def __exit__(self, *_args: object) -> None:
        if self.descriptor is not None:
            os.close(self.descriptor)
            self.descriptor = None
        try:
            self.path.unlink()
            fsync_directory(self.path.parent)
        except FileNotFoundError:
            pass


def append_journal(record: Mapping[str, Any]) -> None:
    payload = json.dumps(
        dict(record), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    JOURNAL_FILE.parent.mkdir(parents=True, exist_ok=True)
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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(HASH_BLOCK_BYTES):
            digest.update(block)
    return digest.hexdigest()


def sha256_file_prefix(path: Path, byte_count: int) -> str:
    if byte_count < 0:
        raise AcquisitionError(f"INVALID_PREFIX_HASH_LENGTH:{byte_count}")
    digest = hashlib.sha256()
    remaining = byte_count
    if remaining == 0:
        return digest.hexdigest()
    with path.open("rb") as handle:
        while remaining:
            block = handle.read(min(HASH_BLOCK_BYTES, remaining))
            if not block:
                raise AcquisitionError(
                    f"CANONICAL_PREFIX_SHORT_READ:{byte_count - remaining}"
                    f"!={byte_count}"
                )
            digest.update(block)
            remaining -= len(block)
    return digest.hexdigest()


def validate_prefix(
    path: Path | None = None,
    *,
    enforce_mode: bool = True,
) -> int:
    path = path or PART_MEDIA
    if not path.exists():
        return 0
    if path.is_symlink() or not path.is_file():
        raise NoGoError(f"CANONICAL_STAGING_NOT_REGULAR_FILE:{path}")
    size = path.stat().st_size
    if size > EXPECTED_BYTES:
        raise NoGoError(
            f"CANONICAL_STAGING_EXCEEDS_EXPECTED_BYTES:{size}>{EXPECTED_BYTES}"
        )
    if enforce_mode:
        os.chmod(path, 0o600)
    return size


def snapshot_prefix(
    path: Path | None = None,
    *,
    enforce_mode: bool = True,
    byte_count: int | None = None,
) -> PrefixSnapshot:
    path = path or PART_MEDIA
    observed = validate_prefix(path, enforce_mode=enforce_mode)
    length = observed if byte_count is None else byte_count
    if length < 0 or length > observed:
        raise AcquisitionError(
            f"PREFIX_SNAPSHOT_LENGTH_OUT_OF_RANGE:{length}>{observed}"
        )
    if length == 0:
        digest = hashlib.sha256(b"").hexdigest()
    else:
        digest = sha256_file_prefix(path, length)
    return PrefixSnapshot(byte_count=length, sha256=digest)


def segments_from(prefix: int) -> list[Segment]:
    if prefix < 0 or prefix > EXPECTED_BYTES:
        raise AcquisitionError(f"INVALID_PREFIX:{prefix}")
    segments: list[Segment] = []
    start = prefix
    while start < EXPECTED_BYTES:
        next_grid_boundary = (
            ((start // SEGMENT_BYTES) + 1) * SEGMENT_BYTES
        )
        end = min(EXPECTED_BYTES, next_grid_boundary) - 1
        segments.append(Segment(start, end))
        start = end + 1
    return segments


def segment_record(
    segment: Segment,
    prefix_snapshot: PrefixSnapshot,
) -> dict[str, Any]:
    return {
        "start": segment.start,
        "end": segment.end,
        "expected_bytes": segment.byte_count,
        "path": segment.filename,
        "status": "pending",
        "attempts": 0,
        "etag": None,
        "sha256": None,
        "completed_at_utc": None,
        "prefix_provenance": prefix_snapshot.record(),
    }


def new_manifest(prefix_snapshot: PrefixSnapshot) -> dict[str, Any]:
    prefix = prefix_snapshot.byte_count
    return {
        "schema_version": "av-trace.epic-p23-102-parallel-segments/2.0",
        "task_id": TASK_ID,
        "asset_id": ASSET_ID,
        "official_url": OFFICIAL_URL,
        "expected_bytes": EXPECTED_BYTES,
        "official_md5": OFFICIAL_MD5,
        "expected_etag": EXPECTED_ETAG,
        "alignment_bytes": ALIGNMENT_BYTES,
        "segment_bytes": SEGMENT_BYTES,
        "prefix_provenance_scheme": "sha256-exact-prefix-v1",
        "created_at_utc": utc_now(),
        "updated_at_utc": utc_now(),
        "object_etag": None,
        "planning_prefixes": [
            {
                "observed_at_utc": utc_now(),
                **prefix_snapshot.record(),
            }
        ],
        "segments": {
            item.key: segment_record(item, prefix_snapshot)
            for item in segments_from(prefix)
        },
        "assembly": {
            "status": "not_started",
            "stable_prefix_bytes": prefix,
            "segment_start": None,
            "updated_at_utc": utc_now(),
        },
    }


class ManifestStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or SEGMENT_MANIFEST
        self.lock = threading.RLock()
        self.data: dict[str, Any] = {}

    def save(self) -> None:
        self.data["updated_at_utc"] = utc_now()
        atomic_write(self.path, canonical_json_bytes(self.data))

    def load_or_create(self, prefix_snapshot: PrefixSnapshot) -> None:
        with self.lock:
            prefix = prefix_snapshot.byte_count
            if self.path.exists():
                try:
                    value = json.loads(self.path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    raise AcquisitionError(
                        f"SEGMENT_MANIFEST_UNREADABLE:{self.path}"
                    ) from exc
                self._validate_identity(value)
                self.data = value
                self.data.setdefault("planning_prefixes", []).append(
                    {
                        "observed_at_utc": utc_now(),
                        **prefix_snapshot.record(),
                    }
                )
                records = self.data.setdefault("segments", {})
                for segment in segments_from(prefix):
                    record = records.get(segment.key)
                    if record is not None:
                        self._validate_record_bounds(segment.key, record)
                        if not self._record_matches_prefix(
                            record, prefix_snapshot
                        ):
                            self._discard_record_file(record)
                            record = None
                    if record is None:
                        records[segment.key] = segment_record(
                            segment, prefix_snapshot
                        )
            else:
                self.data = new_manifest(prefix_snapshot)
            self.reconcile_files(segments_from(prefix))
            self.save()

    def load_existing(self, *, reconcile: bool = True) -> None:
        with self.lock:
            if not self.path.exists():
                raise AcquisitionError(
                    f"SEGMENT_MANIFEST_MISSING:{self.path}"
                )
            try:
                value = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise AcquisitionError(
                    f"SEGMENT_MANIFEST_UNREADABLE:{self.path}"
                ) from exc
            self._validate_identity(value)
            self.data = value
            if reconcile:
                self.reconcile_files()
            self.save()

    @staticmethod
    def _validate_identity(value: Mapping[str, Any]) -> None:
        expected = {
            "schema_version": (
                "av-trace.epic-p23-102-parallel-segments/2.0"
            ),
            "asset_id": ASSET_ID,
            "official_url": OFFICIAL_URL,
            "expected_bytes": EXPECTED_BYTES,
            "official_md5": OFFICIAL_MD5,
            "expected_etag": EXPECTED_ETAG,
            "alignment_bytes": ALIGNMENT_BYTES,
            "segment_bytes": SEGMENT_BYTES,
            "prefix_provenance_scheme": "sha256-exact-prefix-v1",
        }
        mismatches = {
            key: (value.get(key), expected_value)
            for key, expected_value in expected.items()
            if value.get(key) != expected_value
        }
        if mismatches:
            raise NoGoError(f"SEGMENT_MANIFEST_IDENTITY_MISMATCH:{mismatches}")

    @staticmethod
    def _validate_record_bounds(
        key: str,
        record: Mapping[str, Any],
    ) -> Segment:
        try:
            segment = Segment(int(record["start"]), int(record["end"]))
            expected_bytes = int(record["expected_bytes"])
        except (KeyError, TypeError, ValueError) as exc:
            raise NoGoError(
                f"SEGMENT_MANIFEST_RECORD_INVALID:{key}"
            ) from exc
        expected = segments_from(segment.start)
        if (
            key != segment.key
            or not expected
            or expected[0] != segment
            or expected_bytes != segment.byte_count
            or record.get("path") != segment.filename
        ):
            raise NoGoError(f"SEGMENT_MANIFEST_BOUNDS_MISMATCH:{key}")
        return segment

    @staticmethod
    def _record_provenance(
        record: Mapping[str, Any],
    ) -> PrefixSnapshot:
        value = record.get("prefix_provenance")
        if not isinstance(value, Mapping):
            raise NoGoError("SEGMENT_PREFIX_PROVENANCE_MISSING")
        try:
            snapshot = PrefixSnapshot(
                byte_count=int(value["bytes"]),
                sha256=str(value["sha256"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise NoGoError("SEGMENT_PREFIX_PROVENANCE_INVALID") from exc
        if (
            snapshot.byte_count < 0
            or snapshot.byte_count > EXPECTED_BYTES
            or not re.fullmatch(r"[0-9a-f]{64}", snapshot.sha256)
            or value.get("id") != snapshot.identity
        ):
            raise NoGoError("SEGMENT_PREFIX_PROVENANCE_INVALID")
        return snapshot

    @classmethod
    def _record_matches_prefix(
        cls,
        record: Mapping[str, Any],
        current: PrefixSnapshot,
    ) -> bool:
        provenance = cls._record_provenance(record)
        if provenance.byte_count > current.byte_count:
            return False
        if provenance.byte_count == current.byte_count:
            return provenance.sha256 == current.sha256
        if provenance.byte_count == 0:
            return provenance.sha256 == hashlib.sha256(b"").hexdigest()
        return (
            sha256_file_prefix(PART_MEDIA, provenance.byte_count)
            == provenance.sha256
        )

    @staticmethod
    def _discard_record_file(record: Mapping[str, Any]) -> None:
        path_value = record.get("path")
        if not isinstance(path_value, str):
            return
        path = SEGMENT_DIR / path_value
        if not path.exists():
            return
        try:
            if path.is_symlink() or not path.is_file():
                raise NoGoError(f"SEGMENT_NOT_REGULAR_FILE:{path}")
            path.unlink()
            fsync_directory(SEGMENT_DIR)
        except FileNotFoundError:
            pass

    def reconcile_files(
        self,
        segments: Sequence[Segment] | None = None,
    ) -> None:
        records = self.data.get("segments", {})
        keys = (
            [segment.key for segment in segments]
            if segments is not None
            else list(records)
        )
        for key in keys:
            record = records.get(key)
            if record is None:
                continue
            segment = self._validate_record_bounds(key, record)
            provenance = self._record_provenance(record)
            if provenance.byte_count > segment.start:
                raise NoGoError(
                    f"SEGMENT_PROVENANCE_AFTER_RANGE_START:{key}"
                )
            if (
                segment.start != provenance.byte_count
                and segment.start % SEGMENT_BYTES
            ):
                raise NoGoError(
                    f"SEGMENT_NOT_ON_PREFIX_OR_FIXED_GRID:{key}"
                )
            path = SEGMENT_DIR / record["path"]
            expected_size = int(record["expected_bytes"])
            if path.exists():
                if path.is_symlink() or not path.is_file():
                    raise NoGoError(f"SEGMENT_NOT_REGULAR_FILE:{path}")
                observed_size = path.stat().st_size
                if observed_size != expected_size:
                    raise AcquisitionError(
                        f"SEGMENT_SIZE_MISMATCH:{path}:{observed_size}"
                        f"!={expected_size}"
                    )
                observed_sha256 = sha256_file(path)
                recorded_sha256 = record.get("sha256")
                if recorded_sha256 and recorded_sha256 != observed_sha256:
                    raise NoGoError(f"SEGMENT_SHA256_MISMATCH:{path}")
                if not record.get("etag"):
                    raise AcquisitionError(
                        f"SEGMENT_ETAG_METADATA_MISSING:{path}"
                    )
                record.update(
                    {
                        "status": "complete",
                        "sha256": observed_sha256,
                        "observed_bytes": observed_size,
                    }
                )
                os.chmod(path, 0o600)
            elif record.get("status") in {"complete", "committing"}:
                record.update(
                    {
                        "status": "pending",
                        "sha256": None,
                        "completed_at_utc": None,
                    }
                )

    def incomplete_segments(self, prefix: int) -> list[Segment]:
        with self.lock:
            result = []
            for segment in segments_from(prefix):
                record = self.data["segments"][segment.key]
                if record.get("status") != "complete":
                    result.append(segment)
            return result

    def mark_downloading(self, segment: Segment) -> None:
        with self.lock:
            record = self.data["segments"][segment.key]
            record["status"] = "downloading"
            record["last_started_at_utc"] = utc_now()
            self.save()

    def record_attempt(self, segment: Segment) -> int:
        with self.lock:
            record = self.data["segments"][segment.key]
            record["attempts"] = int(record.get("attempts", 0)) + 1
            self.save()
            return int(record["attempts"])

    def commit(
        self,
        *,
        segment: Segment,
        temporary: Path,
        response: Mapping[str, Any],
        digest: str,
    ) -> None:
        with self.lock:
            etag = str(response["etag"])
            object_etag = self.data.get("object_etag")
            if object_etag is not None and etag != object_etag:
                raise NoGoError(
                    f"SEGMENT_ETAG_MISMATCH:{etag!r}!={object_etag!r}"
                )
            if object_etag is None:
                self.data["object_etag"] = etag
            record = self.data["segments"][segment.key]
            record.update(
                {
                    "status": "committing",
                    "etag": etag,
                    "sha256": digest,
                    "observed_bytes": segment.byte_count,
                    "validated_response": dict(response),
                    "completed_at_utc": utc_now(),
                }
            )
            self.save()
            os.replace(temporary, segment.path)
            os.chmod(segment.path, 0o600)
            fsync_directory(SEGMENT_DIR)
            record["status"] = "complete"
            self.save()

    def set_assembly(
        self,
        *,
        status_value: str,
        stable_prefix: int,
        segment_start: int | None,
    ) -> None:
        with self.lock:
            self.data["assembly"] = {
                "status": status_value,
                "stable_prefix_bytes": stable_prefix,
                "segment_start": segment_start,
                "updated_at_utc": utc_now(),
            }
            self.save()


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
    curl_exit_code: int = 0,
) -> dict[str, Any]:
    if curl_exit_code != 0:
        raise AcquisitionError(f"CURL_EXIT_CODE:{curl_exit_code}")
    candidates = [
        block
        for block in blocks
        if block.get("headers", {}).get("content-range") is not None
    ]
    if not candidates:
        raise AcquisitionError("NO_HTTP_CONTENT_RANGE_RESPONSE")
    final = candidates[-1]
    if final.get("status_code") != 206:
        raise AcquisitionError(
            f"RANGE_HTTP_STATUS_NOT_206:{final.get('status_code')}"
        )
    headers = final["headers"]
    start, end, total = parse_content_range(headers.get("content-range"))
    if (start, end) != (requested_start, requested_end):
        raise AcquisitionError(
            "RANGE_BOUNDS_MISMATCH:"
            f"{start}-{end}!={requested_start}-{requested_end}"
        )
    if total != EXPECTED_BYTES:
        raise NoGoError(f"RANGE_TOTAL_MISMATCH:{total}!={EXPECTED_BYTES}")
    expected_body = requested_end - requested_start + 1
    if body_bytes != expected_body:
        raise AcquisitionError(
            f"RANGE_BODY_SIZE_MISMATCH:{body_bytes}!={expected_body}"
        )
    content_length = headers.get("content-length")
    if content_length is None:
        raise AcquisitionError("CONTENT_LENGTH_MISSING")
    try:
        parsed_content_length = int(content_length)
    except ValueError as exc:
        raise AcquisitionError(
            f"CONTENT_LENGTH_INVALID:{content_length!r}"
        ) from exc
    if parsed_content_length != expected_body:
        raise AcquisitionError(
            "CONTENT_LENGTH_MISMATCH:"
            f"{parsed_content_length}!={expected_body}"
        )
    etag = (headers.get("etag") or "").strip()
    if not etag:
        raise NoGoError("ETAG_MISSING")
    if etag != EXPECTED_ETAG:
        raise NoGoError(f"ETAG_MISMATCH:{etag!r}!={EXPECTED_ETAG!r}")
    content_type = (headers.get("content-type") or "").split(";", 1)[0].lower()
    if content_type != "video/mp4":
        raise NoGoError(f"CONTENT_TYPE_NOT_VIDEO_MP4:{content_type!r}")
    return {
        "status_code": 206,
        "content_range": headers["content-range"],
        "content_length": parsed_content_length,
        "content_type": content_type,
        "etag": etag,
        "last_modified": headers.get("last-modified"),
        "validated_bytes": expected_body,
    }


def sanitize_stderr(value: str) -> str:
    value = value.replace(OFFICIAL_URL, "<official-url>")
    for proxy in PROXIES:
        value = value.replace(proxy, "<proxy>")
    return value[-4000:]


def run_segment_request(
    *,
    segment: Segment,
    proxy: str,
    options: TransferOptions,
    attempt: int,
) -> dict[str, Any]:
    token = f"{os.getpid()}-{threading.get_ident()}-{attempt}"
    body = SEGMENT_DIR / f".{segment.filename}.{token}.body"
    headers_path = SEGMENT_DIR / f".{segment.filename}.{token}.headers"
    for path in (body, headers_path):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    descriptor = os.open(body, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    command = [
        "curl",
        "--proxy",
        proxy,
        "--location",
        "--proto",
        "=https",
        "--proto-redir",
        "=https",
        "--silent",
        "--show-error",
        "--connect-timeout",
        str(options.connect_timeout_seconds),
        "--max-time",
        str(options.max_time_seconds),
        "--range",
        f"{segment.start}-{segment.end}",
        "--dump-header",
        str(headers_path),
        "--output",
        str(body),
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
    os.chmod(body, 0o600)
    raw_headers = (
        headers_path.read_text(encoding="iso-8859-1", errors="replace")
        if headers_path.exists()
        else ""
    )
    try:
        headers_path.unlink()
    except FileNotFoundError:
        pass
    return {
        "temporary_body": body,
        "proxy_route": urlsplit(proxy).hostname or proxy,
        "requested_range": f"bytes={segment.start}-{segment.end}",
        "curl_exit_code": completed.returncode,
        "elapsed_seconds": elapsed,
        "body_bytes": body.stat().st_size,
        "header_blocks": parse_header_blocks(raw_headers),
        "stderr": sanitize_stderr(
            completed.stderr.decode("utf-8", errors="replace").strip()
        ),
    }


def remove_temporary(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def acquire_one_segment(
    segment: Segment,
    *,
    options: TransferOptions,
    store: ManifestStore,
) -> dict[str, Any]:
    store.mark_downloading(segment)
    failures: list[str] = []
    for round_number in range(1, options.attempt_rounds + 1):
        for proxy_number, proxy in enumerate(PROXIES, start=1):
            attempt = store.record_attempt(segment)
            result: dict[str, Any] | None = None
            temporary: Path | None = None
            try:
                result = run_segment_request(
                    segment=segment,
                    proxy=proxy,
                    options=options,
                    attempt=attempt,
                )
                temporary = result["temporary_body"]
                response = validate_range_response(
                    blocks=result["header_blocks"],
                    requested_start=segment.start,
                    requested_end=segment.end,
                    body_bytes=result["body_bytes"],
                    curl_exit_code=result["curl_exit_code"],
                )
                descriptor = os.open(temporary, os.O_RDONLY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
                digest = sha256_file(temporary)
                store.commit(
                    segment=segment,
                    temporary=temporary,
                    response=response,
                    digest=digest,
                )
                append_journal(
                    {
                        "recorded_at_utc": utc_now(),
                        "tool": "epic_p23_102_parallel_acquisition",
                        "mode": "parallel_segment",
                        "segment": segment.key,
                        "attempt": attempt,
                        "round": round_number,
                        "proxy_position": proxy_number,
                        "proxy_route": result["proxy_route"],
                        "requested_range": result["requested_range"],
                        "curl_exit_code": result["curl_exit_code"],
                        "elapsed_seconds": result["elapsed_seconds"],
                        "body_bytes": result["body_bytes"],
                        "outcome": "COMPLETE_SEGMENT_ACCEPTED",
                        "validated_response": response,
                        "sha256": digest,
                    }
                )
                return {
                    "segment": segment.key,
                    "bytes": segment.byte_count,
                    "sha256": digest,
                    "etag": response["etag"],
                    "attempt": attempt,
                }
            except NoGoError as exc:
                remove_temporary(temporary)
                append_journal(
                    {
                        "recorded_at_utc": utc_now(),
                        "tool": "epic_p23_102_parallel_acquisition",
                        "mode": "parallel_segment",
                        "segment": segment.key,
                        "attempt": attempt,
                        "round": round_number,
                        "proxy_position": proxy_number,
                        "proxy_route": urlsplit(proxy).hostname or proxy,
                        "outcome": "NO_GO",
                        "validation_error": str(exc),
                    }
                )
                raise
            except (AcquisitionError, OSError, subprocess.SubprocessError) as exc:
                remove_temporary(temporary)
                failure = (
                    f"{urlsplit(proxy).hostname or proxy}:{type(exc).__name__}:"
                    f"{exc}"
                )
                failures.append(failure)
                append_journal(
                    {
                        "recorded_at_utc": utc_now(),
                        "tool": "epic_p23_102_parallel_acquisition",
                        "mode": "parallel_segment",
                        "segment": segment.key,
                        "attempt": attempt,
                        "round": round_number,
                        "proxy_position": proxy_number,
                        "proxy_route": urlsplit(proxy).hostname or proxy,
                        "outcome": "FAILED_NO_SEGMENT_ACCEPTED",
                        "validation_error": str(exc),
                    }
                )
        if round_number < options.attempt_rounds:
            time.sleep(min(10, 2**round_number))
    raise AcquisitionError(
        f"SEGMENT_RETRIES_EXHAUSTED:{segment.key}:"
        + "|".join(failures[-6:])
    )


def acquisition_free_space(
    missing_segments: Sequence[Segment],
) -> dict[str, int]:
    missing_bytes = sum(item.byte_count for item in missing_segments)
    disk = shutil.disk_usage(BASE)
    required = missing_bytes + FREE_SPACE_MARGIN_BYTES
    if disk.free < required:
        raise AcquisitionError(f"INSUFFICIENT_FREE_SPACE:{disk.free}<{required}")
    return {
        "free_bytes": disk.free,
        "missing_segment_bytes": missing_bytes,
        "required_free_bytes": required,
        "free_space_margin_bytes": FREE_SPACE_MARGIN_BYTES,
    }


def run_acquisition(options: TransferOptions) -> dict[str, Any]:
    secure_parallel_directories()
    with ExclusiveParallelLock():
        prefix_snapshot = snapshot_prefix()
        prefix = prefix_snapshot.byte_count
        store = ManifestStore()
        store.load_or_create(prefix_snapshot)
        missing = store.incomplete_segments(prefix)
        free_space = acquisition_free_space(missing)
        results: list[dict[str, Any]] = []
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=options.concurrency,
            thread_name_prefix="epic-range",
        ) as executor:
            futures = {
                executor.submit(
                    acquire_one_segment,
                    segment,
                    options=options,
                    store=store,
                ): segment
                for segment in missing
            }
            try:
                for future in concurrent.futures.as_completed(futures):
                    results.append(future.result())
            except BaseException:
                for future in futures:
                    future.cancel()
                raise
        return {
            "status": "PARALLEL_SEGMENTS_COMPLETE",
            "prefix_observed_bytes": prefix,
            "prefix_observed_sha256": prefix_snapshot.sha256,
            "prefix_identity": prefix_snapshot.identity,
            "segment_count_acquired": len(results),
            "segment_bytes_acquired": sum(item["bytes"] for item in results),
            "manifest": display_path(SEGMENT_MANIFEST),
            "object_etag": store.data.get("object_etag"),
            "free_space_check": free_space,
            "canonical_staging_modified": False,
        }


def recover_interrupted_append(store: ManifestStore) -> None:
    assembly = store.data.get("assembly", {})
    if assembly.get("status") != "appending":
        return
    stable = int(assembly.get("stable_prefix_bytes", -1))
    segment_start = assembly.get("segment_start")
    if (
        stable < 0
        or stable > EXPECTED_BYTES
        or stable != segment_start
        or not PART_MEDIA.exists()
    ):
        raise AcquisitionError("UNSAFE_INTERRUPTED_ASSEMBLY_STATE")
    observed = PART_MEDIA.stat().st_size
    record = store.data.get("segments", {}).get(
        next(
            (
                key
                for key, value in store.data.get("segments", {}).items()
                if value.get("start") == stable
            ),
            "",
        ),
        {},
    )
    upper_bound = int(record.get("end", stable - 1)) + 1
    if observed < stable or observed > upper_bound:
        raise AcquisitionError(
            f"INTERRUPTED_ASSEMBLY_SIZE_OUTSIDE_SEGMENT:{observed}"
        )
    with PART_MEDIA.open("r+b") as handle:
        handle.truncate(stable)
        handle.flush()
        os.fsync(handle.fileno())
    fsync_directory(PART_MEDIA.parent)
    store.set_assembly(
        status_value="recovered",
        stable_prefix=stable,
        segment_start=None,
    )


def verified_coverage(
    store: ManifestStore,
    prefix: int,
) -> list[tuple[Segment, Path]]:
    coverage: list[tuple[Segment, Path]] = []
    object_etag = store.data.get("object_etag")
    if prefix < EXPECTED_BYTES and not object_etag:
        raise AcquisitionError("MANIFEST_OBJECT_ETAG_MISSING")
    records = store.data.get("segments", {})
    if not isinstance(records, Mapping):
        raise NoGoError("SEGMENT_MANIFEST_RECORDS_INVALID")
    by_start: dict[int, tuple[Segment, Mapping[str, Any]]] = {}
    for key, value in records.items():
        if not isinstance(key, str) or not isinstance(value, Mapping):
            raise NoGoError("SEGMENT_MANIFEST_RECORD_INVALID")
        segment = store._validate_record_bounds(key, value)
        provenance = store._record_provenance(value)
        if provenance.byte_count > segment.start:
            raise NoGoError(
                f"SEGMENT_PROVENANCE_AFTER_RANGE_START:{segment.key}"
            )
        if (
            segment.start != provenance.byte_count
            and segment.start % SEGMENT_BYTES
        ):
            raise NoGoError(
                f"SEGMENT_NOT_ON_PREFIX_OR_FIXED_GRID:{segment.key}"
            )
        if segment.start in by_start:
            raise NoGoError(
                f"AMBIGUOUS_SEGMENT_START:{segment.start}"
            )
        by_start[segment.start] = (segment, value)

    current_snapshot = snapshot_prefix(byte_count=prefix)
    prefix_hashes = {prefix: current_snapshot.sha256}
    expected_start = prefix
    while expected_start < EXPECTED_BYTES:
        item = by_start.get(expected_start)
        if item is None:
            overlapping = sorted(
                segment.key
                for segment, _record in by_start.values()
                if segment.start < expected_start <= segment.end
            )
            if overlapping:
                raise AcquisitionError(
                    "STALE_SEGMENT_PARTIAL_OVERLAP:"
                    f"{expected_start}:{','.join(overlapping)}"
                )
            raise AcquisitionError(
                f"SEGMENT_COVERAGE_GAP_AT:{expected_start}"
            )
        segment, record = item
        if not record or record.get("status") != "complete":
            raise AcquisitionError(f"SEGMENT_COVERAGE_GAP:{segment.key}")
        if record.get("etag") != object_etag:
            raise NoGoError(f"SEGMENT_MANIFEST_ETAG_MISMATCH:{segment.key}")
        provenance = store._record_provenance(record)
        observed_prefix_hash = prefix_hashes.get(provenance.byte_count)
        if observed_prefix_hash is None:
            observed_prefix_hash = snapshot_prefix(
                byte_count=provenance.byte_count
            ).sha256
            prefix_hashes[provenance.byte_count] = observed_prefix_hash
        if observed_prefix_hash != provenance.sha256:
            raise NoGoError(
                f"SEGMENT_PREFIX_PROVENANCE_MISMATCH:{segment.key}"
            )
        path = SEGMENT_DIR / record["path"]
        if path.is_symlink() or not path.is_file():
            raise AcquisitionError(f"SEGMENT_FILE_MISSING:{path}")
        if path.stat().st_size != segment.byte_count:
            raise AcquisitionError(f"SEGMENT_FILE_SIZE_MISMATCH:{path}")
        if sha256_file(path) != record.get("sha256"):
            raise NoGoError(f"SEGMENT_FILE_SHA256_MISMATCH:{path}")
        coverage.append((segment, path))
        expected_start = segment.end + 1
    if coverage:
        if coverage[0][0].start != prefix:
            raise AcquisitionError("SEGMENT_COVERAGE_DOES_NOT_START_AT_PREFIX")
        if coverage[-1][0].end != EXPECTED_BYTES - 1:
            raise AcquisitionError("SEGMENT_COVERAGE_DOES_NOT_REACH_EOF")
        for (left, _), (right, _) in itertools.pairwise(coverage):
            if left.end + 1 != right.start:
                raise AcquisitionError(
                    f"NONCONTIGUOUS_SEGMENT_COVERAGE:{left.key}:{right.key}"
                )
    elif prefix != EXPECTED_BYTES:
        raise AcquisitionError("SEGMENT_COVERAGE_EMPTY_BEFORE_EOF")
    return coverage


def assembly_free_space(prefix: int) -> dict[str, int]:
    remaining = EXPECTED_BYTES - prefix
    disk = shutil.disk_usage(BASE)
    required = remaining + FREE_SPACE_MARGIN_BYTES
    if disk.free < required:
        raise AcquisitionError(
            f"INSUFFICIENT_ASSEMBLY_FREE_SPACE:{disk.free}<{required}"
        )
    return {
        "free_bytes": disk.free,
        "append_bytes": remaining,
        "required_free_bytes": required,
        "free_space_margin_bytes": FREE_SPACE_MARGIN_BYTES,
    }


def append_segment_to_canonical(
    *,
    segment: Segment,
    source_path: Path,
    store: ManifestStore,
) -> None:
    if PART_MEDIA.exists() and PART_MEDIA.stat().st_size != segment.start:
        raise AcquisitionError(
            "CANONICAL_PREFIX_CHANGED_DURING_ASSEMBLY:"
            f"{PART_MEDIA.stat().st_size}!={segment.start}"
        )
    if not PART_MEDIA.exists():
        if segment.start != 0:
            raise AcquisitionError("CANONICAL_STAGING_DISAPPEARED")
        descriptor = os.open(
            PART_MEDIA,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        os.close(descriptor)
    store.set_assembly(
        status_value="appending",
        stable_prefix=segment.start,
        segment_start=segment.start,
    )
    copied = 0
    digest = hashlib.sha256()
    expected_digest = store.data["segments"][segment.key]["sha256"]
    try:
        with source_path.open("rb") as source, PART_MEDIA.open("ab") as target:
            while block := source.read(COPY_BLOCK_BYTES):
                target.write(block)
                copied += len(block)
                digest.update(block)
            target.flush()
            os.fsync(target.fileno())
        if copied != segment.byte_count:
            raise AcquisitionError(
                f"ASSEMBLY_COPY_SIZE_MISMATCH:{copied}!={segment.byte_count}"
            )
        if digest.hexdigest() != expected_digest:
            raise NoGoError(
                f"SEGMENT_CHANGED_DURING_ASSEMBLY:{source_path}"
            )
        os.chmod(PART_MEDIA, 0o600)
        fsync_directory(PART_MEDIA.parent)
        store.set_assembly(
            status_value="segment_committed",
            stable_prefix=segment.end + 1,
            segment_start=None,
        )
    except BaseException:
        if PART_MEDIA.exists():
            with PART_MEDIA.open("r+b") as target:
                target.truncate(segment.start)
                target.flush()
                os.fsync(target.fileno())
            fsync_directory(PART_MEDIA.parent)
        store.set_assembly(
            status_value="append_rolled_back",
            stable_prefix=segment.start,
            segment_start=None,
        )
        raise


def load_exact_tool() -> ModuleType:
    module_name = "_epic_p23_102_exact_acquisition_for_parallel"
    spec = importlib.util.spec_from_file_location(module_name, EXACT_TOOL)
    if spec is None or spec.loader is None:
        raise AcquisitionError(f"EXACT_TOOL_IMPORT_FAILED:{EXACT_TOOL}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    if (
        module.EXPECTED_BYTES != EXPECTED_BYTES
        or module.OFFICIAL_MD5 != OFFICIAL_MD5
        or module.OFFICIAL_URL != OFFICIAL_URL
        or module.PART_MEDIA != PART_MEDIA
        or module.FINAL_MEDIA != FINAL_MEDIA
    ):
        raise NoGoError("EXACT_TOOL_IDENTITY_OR_PATH_MISMATCH")
    return module


def reuse_exact_validation(
    *,
    ffprobe_requested: str | None,
    transfer: Mapping[str, Any],
) -> dict[str, Any]:
    exact = load_exact_tool()
    exact.secure_directories()
    exact.validate_official_url(OFFICIAL_URL)
    evidence = exact.verify_evidence()
    exact.write_json(exact.PROVENANCE_FILE, exact.provenance_record(evidence))
    exact.write_progress(
        status="HASHING_AND_EXACT_VERIFICATION",
        transfer=transfer,
    )
    media = exact.verify_and_promote(transfer)
    exact.write_progress(status="FFPROBE_VALIDATION", transfer=transfer)
    ffprobe = exact.resolve_ffprobe(ffprobe_requested)
    technical = exact.validate_ffprobe_report(exact.run_ffprobe(ffprobe))
    exact.create_manifest(
        evidence=evidence,
        media=media,
        technical=technical,
    )
    exact.enforce_permissions()
    message = (
        "Parallel segments were assembled in exact byte order; the official "
        "MD5, local SHA-256, restrictive-custody, and ffprobe checks passed."
    )
    report = exact.exact_validation_report(
        disposition="READY",
        evidence=evidence,
        media=media,
        technical=technical,
        message=message,
    )
    if not report["all_exact_checks_passed"]:
        raise AcquisitionError("FINAL_VALIDATION_BOOLEAN_DID_NOT_CLOSE")
    exact.write_progress(
        status="COMPLETE_VERIFIED_READY",
        disposition="READY",
        message=message,
        transfer=transfer,
    )
    exact.write_summary(
        disposition="READY",
        message=message,
        media=media,
        technical=technical,
    )
    return {"media": media, "technical": technical}


def run_assembly(ffprobe_requested: str | None) -> dict[str, Any]:
    secure_parallel_directories()
    with ExclusiveParallelLock(), CanonicalMutationGuard():
        store = ManifestStore()
        # Load without first requiring alignment so an interrupted append can
        # be rolled back from its manifest checkpoint. Covered stale segments
        # are deliberately not reconciled here; exact live coverage is
        # selected and validated after the current prefix is known.
        store.load_existing(reconcile=False)
        if FINAL_MEDIA.exists():
            if FINAL_MEDIA.is_symlink() or FINAL_MEDIA.stat().st_size != EXPECTED_BYTES:
                raise NoGoError("EXISTING_FINAL_FILE_HAS_WRONG_IDENTITY")
            transfer = {
                "status": "EXISTING_FINAL_REUSED_FOR_EXACT_REVALIDATION",
                "assembled_segment_count": 0,
                "assembled_bytes": 0,
                "segment_manifest": display_path(SEGMENT_MANIFEST),
                "object_etag": store.data.get("object_etag"),
                "parallel_concurrency": True,
                "canonical_append_during_acquisition": False,
            }
            validation = reuse_exact_validation(
                ffprobe_requested=ffprobe_requested,
                transfer=transfer,
            )
            store.set_assembly(
                status_value="complete_verified_ready",
                stable_prefix=EXPECTED_BYTES,
                segment_start=None,
            )
            return {
                "status": "COMPLETE_VERIFIED_READY",
                "transfer": transfer,
                **validation,
            }
        recover_interrupted_append(store)
        prefix = validate_prefix()
        coverage = verified_coverage(store, prefix)
        free_space = assembly_free_space(prefix)
        for segment, source_path in coverage:
            append_segment_to_canonical(
                segment=segment,
                source_path=source_path,
                store=store,
            )
        if validate_prefix() != EXPECTED_BYTES:
            raise AcquisitionError("ASSEMBLY_DID_NOT_REACH_EXACT_EOF")
        store.set_assembly(
            status_value="assembled_pending_exact_validation",
            stable_prefix=EXPECTED_BYTES,
            segment_start=None,
        )
        transfer = {
            "status": "PARALLEL_SEGMENTS_ASSEMBLED",
            "assembly_prefix_bytes": prefix,
            "assembled_segment_count": len(coverage),
            "assembled_bytes": EXPECTED_BYTES - prefix,
            "segment_manifest": display_path(SEGMENT_MANIFEST),
            "object_etag": store.data.get("object_etag"),
            "free_space_check": free_space,
            "parallel_concurrency": True,
            "canonical_append_during_acquisition": False,
        }
        validation = reuse_exact_validation(
            ffprobe_requested=ffprobe_requested,
            transfer=transfer,
        )
        store.set_assembly(
            status_value="complete_verified_ready",
            stable_prefix=EXPECTED_BYTES,
            segment_start=None,
        )
        return {
            "status": "COMPLETE_VERIFIED_READY",
            "transfer": transfer,
            **validation,
        }


def plan() -> dict[str, Any]:
    prefix = validate_prefix(enforce_mode=False)
    segments = segments_from(prefix)
    existing_complete = 0
    object_etag = None
    if SEGMENT_MANIFEST.exists():
        try:
            manifest = json.loads(
                SEGMENT_MANIFEST.read_text(encoding="utf-8")
            )
            ManifestStore._validate_identity(manifest)
            object_etag = manifest.get("object_etag")
            existing_complete = sum(
                1
                for segment in segments
                if manifest.get("segments", {})
                .get(segment.key, {})
                .get("status")
                == "complete"
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise AcquisitionError("SEGMENT_MANIFEST_UNREADABLE") from exc
    return {
        "mode": "plan_only",
        "task_id": TASK_ID,
        "asset_id": ASSET_ID,
        "official_url": OFFICIAL_URL,
        "expected_bytes": EXPECTED_BYTES,
        "official_md5": OFFICIAL_MD5,
        "expected_etag": EXPECTED_ETAG,
        "canonical_prefix_bytes": prefix,
        "canonical_prefix_on_fixed_grid": (
            prefix == EXPECTED_BYTES or prefix % ALIGNMENT_BYTES == 0
        ),
        "arbitrary_canonical_prefix_supported": True,
        "segment_bytes": SEGMENT_BYTES,
        "remaining_segment_count": len(segments),
        "remaining_bytes": EXPECTED_BYTES - prefix,
        "manifest_complete_segments_from_prefix": existing_complete,
        "manifest_object_etag": object_etag,
        "default_concurrency": DEFAULT_CONCURRENCY,
        "proxy_order": [urlsplit(proxy).hostname for proxy in PROXIES],
        "canonical_acquisition_lock_present": CANONICAL_LOCK_FILE.exists(),
        "acquisition_writes_canonical_staging": False,
        "assembly_requires_canonical_acquisition_lock_absent": True,
        "segment_manifest": display_path(SEGMENT_MANIFEST),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan-only", action="store_true")
    mode.add_argument("--acquire", action="store_true")
    mode.add_argument("--assemble", action="store_true")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument(
        "--attempt-rounds", type=int, default=DEFAULT_ATTEMPT_ROUNDS
    )
    parser.add_argument(
        "--connect-timeout",
        type=int,
        default=DEFAULT_CONNECT_TIMEOUT_SECONDS,
    )
    parser.add_argument("--max-time", type=int, default=DEFAULT_MAX_TIME_SECONDS)
    parser.add_argument("--ffprobe")
    args = parser.parse_args()
    if not 1 <= args.concurrency <= MAX_CONCURRENCY:
        parser.error(f"--concurrency must be between 1 and {MAX_CONCURRENCY}")
    if args.attempt_rounds <= 0:
        parser.error("--attempt-rounds must be positive")
    if args.connect_timeout <= 0 or args.max_time <= 0:
        parser.error("timeouts must be positive")
    return args


def main() -> int:
    args = parse_args()
    try:
        if args.plan_only:
            print(json.dumps(plan(), indent=2, sort_keys=True))
            return 0
        if args.acquire:
            result = run_acquisition(
                TransferOptions(
                    concurrency=args.concurrency,
                    attempt_rounds=args.attempt_rounds,
                    connect_timeout_seconds=args.connect_timeout,
                    max_time_seconds=args.max_time,
                )
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            print("EPIC_P23_102_PARALLEL_SEGMENTS_READY")
            return 0
        result = run_assembly(args.ffprobe)
        print(json.dumps(result, indent=2, sort_keys=True))
        print("EPIC_P23_102_PARALLEL_ACQUISITION_READY")
        return 0
    except KeyboardInterrupt:
        print("EPIC_P23_102_PARALLEL_ACQUISITION_INTERRUPTED")
        return 130
    except NoGoError as exc:
        print(f"EPIC_P23_102_PARALLEL_ACQUISITION_NO_GO:{exc}")
        return 3
    except (AcquisitionError, OSError, subprocess.SubprocessError) as exc:
        print(f"EPIC_P23_102_PARALLEL_ACQUISITION_REPAIR:{exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
