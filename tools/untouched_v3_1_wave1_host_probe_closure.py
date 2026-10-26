#!/usr/bin/env python3
"""Close retained host-probe evidence for untouched v3.1 wave 1.

This tool is deliberately offline. It validates already-retained HTTP headers,
commitment mappings, HoloAssist technical timing metadata, Hugging Face
repository metadata, and a retained command-output record of archive HEAD
facts. It never opens media, semantic annotations, labels, transcripts, or
captions, and it writes only the three closure artifacts owned by this task.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

PRIVATE_LEDGER = (
    ROOT / "data/restricted/untouched_test_group_ledger_v3_1_private.json"
)
PUBLIC_LEDGER = (
    ROOT
    / "data/rehearsal_plan/"
    "untouched_test_group_ledger_v3_1_public_commitment.json"
)
HOLO_UNIVERSE = (
    ROOT / "data/restricted/holoassist_opaque_group_universe_v1.json"
)
HOLO_EXPOSURE = (
    ROOT / "data/rehearsal_plan/holoassist_exposure_supplement_v1.json"
)
HOLO_TIMING_CACHE = (
    ROOT / "data/restricted/holoassist_technical_timing_cache_v1"
)

DEFAULT_DIAGNOSTIC_ROOT = Path("/tmp/avtrace_v31_wave1_diag_20261015")
DEFAULT_HF_INFO = Path("/tmp/holo_hf_info.json")
DEFAULT_HEAD_TRANSCRIPT = Path(
    "/path/to/av-trace"
    "rollout-2026-09-05T15-27-54-01a07077-7fab-7ad3-a211-566c8342b541.jsonl"
)

PRIVATE_OUTPUT = (
    ROOT
    / "data/restricted/"
    "untouched_v3_1_wave1_host_probe_closure_private.json"
)
PUBLIC_OUTPUT = (
    ROOT
    / "data/rehearsal_plan/"
    "untouched_v3_1_wave1_host_probe_closure_public.json"
)
REVIEW_OUTPUT = (
    ROOT / "docs/review/untouched_v3_1_wave1_host_probe_closure.md"
)

SCHEMA_PRIVATE = "av-trace.untouched-v3.1-wave1-host-probe-private/1.0"
SCHEMA_PUBLIC = "av-trace.untouched-v3.1-wave1-host-probe-public/1.0"
GENERATED_DATE = "2026-10-15"
READY = "WAVE1_HOST_PROBE_CLOSURE_READY"
REPAIR = "WAVE1_HOST_PROBE_CLOSURE_REPAIR"
EXPOSURE_CLASS = "METADATA_ACCESS_ONLY"

LINEAGES = ("ASSEMBLY101", "EPIC", "HOLOASSIST")
SELECTION_FIELD = "v3_1_group_commitment_sha256"
PROXY_LABELS = ("hy", "star")

ASSEMBLY_REVISION = "bfc15ea5e3f0bc8f8c232af6c1b45aa137a9d967"
ASSEMBLY_OBJECT_BYTES = 1_197_122_429
ASSEMBLY_LFS_SHA256 = (
    "f2fcd54671e9d2f3c62bf9401d447dc5174516aa05228776a139cdfd24cd0cd8"
)
ASSEMBLY_VIEW = "C10095_rgb.mp4"

EPIC_TOTAL_BYTES = 11_695_708_821
EPIC_ETAG = '"5a170ea9-2b91e5a95"'
EPIC_LAST_MODIFIED = "Thu, 23 Nov 2017 18:08:41 GMT"

HOLO_REVISION = "7ad9269e82503f677cb4ec64d77a460d0790a6c4"
HOLO_ARCHIVE_PARTS = {
    "video_compress_part_aa": {
        "size_bytes": 42_949_672_960,
        "etag": (
            "d17bc70d63abbc347150e35f1a6bf5caa68c31df6ab1426e06c9370a9c462825"
        ),
    },
    "video_compress_part_ab": {
        "size_bytes": 1_407_188_992,
        "etag": (
            "410665cd37c42d4089f79e4d58194803e9476d1a311a43f322b9c78badab25d3"
        ),
    },
    "video_pitch_shifted_part_aa": {
        "size_bytes": 42_949_672_960,
        "etag": (
            "52effbb892b704aa877bfc19039c066f83c90431f99a966c97c4b4bc7bec84cf"
        ),
    },
    "video_pitch_shifted_part_ab": {
        "size_bytes": 42_949_672_960,
        "etag": (
            "b8d839e8772e849f6ee4ff1fe681a39219fa8eeb4f61ab786dd6beafb6d5045b"
        ),
    },
    "video_pitch_shifted_part_ac": {
        "size_bytes": 42_949_672_960,
        "etag": (
            "1b6a660d347f4c89b9707da2ea7da7aba7727d4dca7a1161e881f5b62a4b6f1e"
        ),
    },
}

EXPECTED_FILE_SHA256 = {
    PRIVATE_LEDGER: (
        "11f87b1d3d39c5ca12859b7cb5385eaae923add03075a0bd0984155cf403a149"
    ),
    PUBLIC_LEDGER: (
        "0e5b98ef6ec19d8ac5124cce53035eccab3f75955f38e7fe0999ab850ef40f15"
    ),
    HOLO_UNIVERSE: (
        "bfed01c6cf5d1fb6ac5befb2959dacedeba649aa0d33112338e7eb49ae4bf529"
    ),
    HOLO_EXPOSURE: (
        "47060b97dbf80e84c9ec4c5f7db07e2e2f841269293e402954321e825c85e890"
    ),
}

EXPECTED_DIAGNOSTIC_SHA256 = {
    "assembly_hy.headers": (
        "cb40f431a963294d79c745e153662854ef903118f72402bf54d1e3819ec56280"
    ),
    "assembly_star.headers": (
        "f023be6eec2228885f6683a80d5c0f65ea5603fde733123645bb4694a2c7bcad"
    ),
    "epic_hy.headers": (
        "c0132650f71b92714bf25127139e712de37aa8f78c17b51e19da39af1acbcc83"
    ),
    "epic_star.headers": (
        "89e16b76d01b04d63345e21a20e8f483d4be372f1c304addc072263a92cbb42a"
    ),
    "summary.txt": (
        "9a86c4251daf3eeebeb20b9855373c3197f1b398b63c11053e8b4fba643d7e00"
    ),
}

EXPECTED_HF_INFO_SHA256 = (
    "c1b060cbfeafe7873c5e3849d1afe110ad2540dff89a898c722f1e2d518db053"
)
EXPECTED_ARCHIVE_HEAD_OUTPUT_SHA256 = (
    "817bb568162da8ba450fe0b07df2a560fdfa3bce050cf3f4f64132fae76be92e"
)

STATUS_RE = re.compile(r"^HTTP/\S+\s+(\d{3})(?:\s+(.*))?$")
CONTENT_RANGE_RE = re.compile(r"bytes\s+(\d+)-(\d+)/(\d+)", re.IGNORECASE)
ARCHIVE_OUTPUT_MARKER = "Chunk ID: c27e76"
IDENTITY_PATTERNS = (
    re.compile(r"(?<![A-Za-z0-9])R\d{3,}(?!\d)", re.IGNORECASE),
    re.compile(r"(?<![A-Za-z0-9])Z\d{3,}(?!\d)", re.IGNORECASE),
    re.compile(r"(?<![A-Za-z0-9])P\d{2}_\d{2,3}(?!\d)"),
    re.compile(r"nusar-[A-Za-z0-9_-]+", re.IGNORECASE),
)
FORBIDDEN_PUBLIC_KEYS = {
    "aliases",
    "closure_root",
    "exact_object_or_session_id",
    "folder",
    "identity",
    "object_path",
    "participant_id",
    "recording_root",
    "session_id",
    "source_url",
    "timing_path",
    "video_id",
}
FORBIDDEN_PUBLIC_TEXT = (
    "extracted_videos/",
    "recordings/",
    "VideoMp4Timing",
    "data.bris.ac.uk/datasets/",
)


class ClosureError(RuntimeError):
    """Stable local-evidence validation failure."""


@dataclass(frozen=True)
class HttpResponseBlock:
    status: int
    reason: str
    headers: dict[str, str]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ClosureError(message)


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value, ensure_ascii=True, separators=(",", ":"), sort_keys=True
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON_OBJECT_REQUIRED:{path}")
    return value


def file_binding(path: Path, *, public_path: str | None = None) -> dict[str, Any]:
    return {
        "path": public_path or str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def validate_bound_inputs(
    *,
    diagnostic_root: Path,
    hf_info_path: Path,
    head_transcript_path: Path,
) -> None:
    for path, expected_hash in EXPECTED_FILE_SHA256.items():
        require(path.is_file(), f"BOUND_INPUT_MISSING:{path}")
        require(
            sha256_file(path) == expected_hash,
            f"BOUND_INPUT_HASH_MISMATCH:{path}",
        )
    for name, expected_hash in EXPECTED_DIAGNOSTIC_SHA256.items():
        path = diagnostic_root / name
        require(path.is_file(), f"DIAGNOSTIC_INPUT_MISSING:{path}")
        require(
            sha256_file(path) == expected_hash,
            f"DIAGNOSTIC_HASH_MISMATCH:{path}",
        )
    require(hf_info_path.is_file(), f"HF_INFO_MISSING:{hf_info_path}")
    require(
        sha256_file(hf_info_path) == EXPECTED_HF_INFO_SHA256,
        "HF_INFO_HASH_MISMATCH",
    )
    require(
        head_transcript_path.is_file(),
        f"HEAD_TRANSCRIPT_MISSING:{head_transcript_path}",
    )
    archive_output = extract_archive_head_output(head_transcript_path)
    require(
        sha256_bytes(archive_output.encode("utf-8"))
        == EXPECTED_ARCHIVE_HEAD_OUTPUT_SHA256,
        "ARCHIVE_HEAD_OUTPUT_HASH_MISMATCH",
    )


def parse_header_blocks(path: Path) -> list[HttpResponseBlock]:
    blocks: list[HttpResponseBlock] = []
    status: int | None = None
    reason = ""
    headers: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip("\r")
        status_match = STATUS_RE.match(line)
        if status_match:
            if status is not None:
                blocks.append(HttpResponseBlock(status, reason, headers))
            status = int(status_match.group(1))
            reason = (status_match.group(2) or "").strip()
            headers = {}
            continue
        if status is None or not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    if status is not None:
        blocks.append(HttpResponseBlock(status, reason, headers))
    require(bool(blocks), f"NO_HTTP_RESPONSE_BLOCKS:{path}")
    return blocks


def parse_content_range(value: str | None) -> tuple[int, int, int]:
    match = CONTENT_RANGE_RE.fullmatch((value or "").strip())
    require(bool(match), f"INVALID_CONTENT_RANGE:{value!r}")
    assert match is not None
    start, end, total = (int(item) for item in match.groups())
    require(start >= 0, "NEGATIVE_CONTENT_RANGE_START")
    require(end >= start, "CONTENT_RANGE_END_BEFORE_START")
    require(total > end, "CONTENT_RANGE_TOTAL_NOT_GREATER_THAN_END")
    return start, end, total


def parse_summary(path: Path) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    current: dict[str, Any] | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line == "---":
            current = None
            continue
        if line.startswith("http_code="):
            fields = dict(
                item.split("=", 1)
                for item in line.split()
                if "=" in item
            )
            current = {
                "http_code": int(fields["http_code"]),
                "size_download": int(fields["size_download"]),
                "url_effective": fields["url_effective"],
            }
            continue
        if current is not None and " curl_exit=" in line:
            name, rest = line.split(" ", 1)
            fields = dict(
                item.split("=", 1) for item in rest.split() if "=" in item
            )
            current.update(
                {
                    "curl_exit": int(fields["curl_exit"]),
                    "persisted_bytes": int(fields["persisted_bytes"]),
                }
            )
            entries[name] = current
    require(
        set(entries)
        == {"assembly_hy", "assembly_star", "epic_hy", "epic_star"},
        "SUMMARY_ENTRY_SET_MISMATCH",
    )
    return entries


def selected_groups() -> dict[str, dict[str, Any]]:
    public = load_json(PUBLIC_LEDGER)
    private = load_json(PRIVATE_LEDGER)
    public_rows = public.get("group_commitments")
    private_rows = private.get("selected_groups")
    require(isinstance(public_rows, list), "PUBLIC_COMMITMENTS_MISSING")
    require(isinstance(private_rows, list), "PRIVATE_GROUPS_MISSING")

    selected: dict[str, dict[str, Any]] = {}
    for lineage in LINEAGES:
        candidates = [
            row
            for row in public_rows
            if row.get("dataset_lineage") == lineage
        ]
        require(bool(candidates), f"NO_PUBLIC_GROUPS:{lineage}")
        public_row = min(
            candidates, key=lambda row: row[SELECTION_FIELD]
        )
        matches = [
            row
            for row in private_rows
            if row.get(SELECTION_FIELD) == public_row[SELECTION_FIELD]
        ]
        require(len(matches) == 1, f"PRIVATE_GROUP_MATCH_COUNT:{lineage}")
        private_row = matches[0]
        require(
            private_row.get("dataset_lineage") == lineage,
            f"PRIVATE_LINEAGE_MISMATCH:{lineage}",
        )
        selected[lineage] = {
            "commitment_id": public_row[SELECTION_FIELD],
            "slot": public_row["slot"],
            "source_commitment_sha256": public_row[
                "source_commitment_sha256"
            ],
            "private_group": private_row,
        }
    return selected


def validate_assembly(
    diagnostic_root: Path,
    summary: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    proxy_results: dict[str, Any] = {}
    expected_url: str | None = None
    for proxy in PROXY_LABELS:
        path = diagnostic_root / f"assembly_{proxy}.headers"
        blocks = parse_header_blocks(path)
        final = blocks[-1]
        summary_entry = summary[f"assembly_{proxy}"]
        require(final.status == 401, f"ASSEMBLY_STATUS_NOT_401:{proxy}")
        require(
            final.headers.get("x-error-code") == "GatedRepo",
            f"ASSEMBLY_GATE_CODE_MISMATCH:{proxy}",
        )
        require(
            int(final.headers.get("content-length", "-1")) == 130,
            f"ASSEMBLY_BODY_LENGTH_MISMATCH:{proxy}",
        )
        require(
            summary_entry["http_code"] == 401
            and summary_entry["size_download"] == 130
            and summary_entry["persisted_bytes"] == 130
            and summary_entry["curl_exit"] == 0,
            f"ASSEMBLY_SUMMARY_MISMATCH:{proxy}",
        )
        url = str(summary_entry["url_effective"])
        expected_url = expected_url or url
        require(url == expected_url, f"ASSEMBLY_URL_MISMATCH:{proxy}")
        require(
            f"/resolve/{ASSEMBLY_REVISION}/" in url
            and url.endswith("/" + ASSEMBLY_VIEW),
            f"ASSEMBLY_URL_NOT_EXACT:{proxy}",
        )
        proxy_results[proxy] = {
            "status": final.status,
            "gate_code": final.headers["x-error-code"],
            "content_length": 130,
            "etag": final.headers.get("etag"),
            "url_sha256": sha256_bytes(url.encode("utf-8")),
        }

    selected = selected_groups()["ASSEMBLY101"]["private_group"]
    identity = selected["identity_and_evidence"]
    exact_session = identity["exact_object_or_session_id"]
    require(
        exact_session in (expected_url or ""),
        "ASSEMBLY_SELECTED_SESSION_NOT_IN_URL",
    )
    object_path = f"recordings/{exact_session}/{ASSEMBLY_VIEW}"
    return {
        "dataset_lineage": "ASSEMBLY101",
        "commitment_id": selected[SELECTION_FIELD],
        "slot": selected["slot"],
        "source_commitment_sha256": selected[
            "source_commitment_sha256"
        ],
        "identity": {
            "closure_root": identity["closure_root"],
            "exact_object_or_session_id": exact_session,
            "object_path": object_path,
            "exact_url": expected_url,
            "revision": ASSEMBLY_REVISION,
            "size_bytes_from_bound_metadata": ASSEMBLY_OBJECT_BYTES,
            "lfs_sha256_from_bound_metadata": ASSEMBLY_LFS_SHA256,
        },
        "status": {
            "exact_route_identified": True,
            "both_proxy_probes_completed": True,
            "gated_401_on_both_proxies": True,
            "gated_repo_error_on_both_proxies": True,
            "anonymous_media_access": False,
            "exact_media_object_resolved_for_anonymous_access": False,
            "repair_required": True,
        },
        "proxy_results": proxy_results,
        "open_items": ["AUTHENTICATED_MEDIA_ACCESS_REQUIRED"],
    }


def validate_epic(
    diagnostic_root: Path,
    summary: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    proxy_results: dict[str, Any] = {}
    expected_url: str | None = None
    for proxy in PROXY_LABELS:
        path = diagnostic_root / f"epic_{proxy}.headers"
        blocks = parse_header_blocks(path)
        final = blocks[-1]
        summary_entry = summary[f"epic_{proxy}"]
        require(final.status == 206, f"EPIC_STATUS_NOT_206:{proxy}")
        start, end, total = parse_content_range(
            final.headers.get("content-range")
        )
        require(
            (start, end, total) == (0, 1023, EPIC_TOTAL_BYTES),
            f"EPIC_CONTENT_RANGE_MISMATCH:{proxy}",
        )
        require(
            int(final.headers.get("content-length", "-1")) == 1024,
            f"EPIC_CONTENT_LENGTH_MISMATCH:{proxy}",
        )
        require(
            final.headers.get("content-type", "").lower() == "video/mp4",
            f"EPIC_CONTENT_TYPE_MISMATCH:{proxy}",
        )
        require(
            final.headers.get("etag") == EPIC_ETAG,
            f"EPIC_ETAG_MISMATCH:{proxy}",
        )
        require(
            final.headers.get("last-modified") == EPIC_LAST_MODIFIED,
            f"EPIC_LAST_MODIFIED_MISMATCH:{proxy}",
        )
        require(
            summary_entry["http_code"] == 206
            and summary_entry["size_download"] == 1024
            and summary_entry["persisted_bytes"] == 1024
            and summary_entry["curl_exit"] == 0,
            f"EPIC_SUMMARY_MISMATCH:{proxy}",
        )
        url = str(summary_entry["url_effective"])
        expected_url = expected_url or url
        require(url == expected_url, f"EPIC_URL_MISMATCH:{proxy}")
        proxy_results[proxy] = {
            "status": final.status,
            "content_range": {
                "start": start,
                "end": end,
                "total_bytes": total,
            },
            "content_length": 1024,
            "content_type": "video/mp4",
            "etag": EPIC_ETAG,
            "last_modified": EPIC_LAST_MODIFIED,
            "url_sha256": sha256_bytes(url.encode("utf-8")),
        }

    selected = selected_groups()["EPIC"]["private_group"]
    identity = selected["identity_and_evidence"]
    require(
        str(identity["exact_object_or_session_id"]) in (expected_url or ""),
        "EPIC_SELECTED_OBJECT_NOT_IN_URL",
    )
    return {
        "dataset_lineage": "EPIC",
        "commitment_id": selected[SELECTION_FIELD],
        "slot": selected["slot"],
        "source_commitment_sha256": selected[
            "source_commitment_sha256"
        ],
        "identity": {
            "closure_root": identity["closure_root"],
            "exact_object_or_session_id": identity[
                "exact_object_or_session_id"
            ],
            "object_path": "videos/train/P29/P29_03.MP4",
            "exact_url": expected_url,
            "manifest_md5": "f03451b585fc36655ecd62b746b22ad0",
        },
        "status": {
            "exact_route_identified": True,
            "both_proxy_probes_completed": True,
            "range_206_on_both_proxies": True,
            "exact_total_bytes_closed": True,
            "etag_closed": True,
            "public_range_access": True,
            "repair_required": False,
        },
        "exact_total_bytes": EPIC_TOTAL_BYTES,
        "etag": EPIC_ETAG,
        "last_modified": EPIC_LAST_MODIFIED,
        "proxy_results": proxy_results,
        "open_items": [],
    }


def extract_archive_head_output(path: Path) -> str:
    matched: list[str] = []
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if ARCHIVE_OUTPUT_MARKER not in line:
                continue
            record = json.loads(line)
            output = record.get("payload", {}).get("output")
            if isinstance(output, str):
                matched.append(output)
    require(len(matched) == 1, "ARCHIVE_HEAD_OUTPUT_MATCH_COUNT")
    return matched[0]


def parse_archive_head_output(text: str) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    current: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("==="):
            current = line[3:]
            results[current] = {
                "http_statuses": [],
            }
            continue
        if current is None:
            continue
        status_match = STATUS_RE.match(line)
        if status_match:
            results[current]["http_statuses"].append(
                int(status_match.group(1))
            )
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if key == "x-linked-size":
            results[current]["size_bytes"] = int(value)
        elif key == "x-linked-etag":
            results[current]["etag"] = value.strip('"')
        elif key == "x-repo-commit":
            results[current]["revision"] = value
        elif key == "accept-ranges":
            results[current]["accept_ranges"] = value
    require(
        set(results) == set(HOLO_ARCHIVE_PARTS),
        "ARCHIVE_HEAD_PART_SET_MISMATCH",
    )
    for name, expected in HOLO_ARCHIVE_PARTS.items():
        item = results[name]
        require(
            item.get("http_statuses") == [200, 302],
            f"ARCHIVE_HEAD_STATUS_MISMATCH:{name}",
        )
        require(
            item.get("revision") == HOLO_REVISION,
            f"ARCHIVE_REVISION_MISMATCH:{name}",
        )
        require(
            item.get("accept_ranges") == "bytes",
            f"ARCHIVE_RANGE_SUPPORT_MISMATCH:{name}",
        )
        require(
            item.get("size_bytes") == expected["size_bytes"],
            f"ARCHIVE_SIZE_MISMATCH:{name}",
        )
        require(
            item.get("etag") == expected["etag"],
            f"ARCHIVE_ETAG_MISMATCH:{name}",
        )
    return results


def validate_holoassist(
    hf_info_path: Path,
    head_transcript_path: Path,
) -> dict[str, Any]:
    selection = selected_groups()["HOLOASSIST"]
    selected = selection["private_group"]
    identity = selected["identity_and_evidence"]
    universe_group = identity["opaque_universe_group"]
    source_commitment = selection["source_commitment_sha256"]

    universe = load_json(HOLO_UNIVERSE)
    matches = [
        group
        for group in universe["selected_groups"]
        if group["private_commitment"] == source_commitment
    ]
    require(len(matches) == 1, "HOLO_UNIVERSE_GROUP_MATCH_COUNT")
    group = matches[0]
    require(
        group["recording_root"] == universe_group["recording_root"],
        "HOLO_RECORDING_ROOT_MISMATCH",
    )
    require(group["timing_closed"] is True, "HOLO_TIMING_NOT_CLOSED")

    variants: list[dict[str, Any]] = []
    for variant in group["variants"]:
        timing_path = HOLO_TIMING_CACHE / variant["timing_path"]
        evidence = variant["timing_evidence"]
        require(timing_path.is_file(), f"HOLO_TIMING_FILE_MISSING:{timing_path}")
        require(
            timing_path.stat().st_size == evidence["bytes"] == 38,
            f"HOLO_TIMING_SIZE_MISMATCH:{timing_path}",
        )
        require(
            sha256_file(timing_path) == evidence["sha256"],
            f"HOLO_TIMING_HASH_MISMATCH:{timing_path}",
        )
        require(
            evidence["format_recognized"] is True
            and evidence["frame_count"] == 2,
            f"HOLO_TIMING_FORMAT_MISMATCH:{timing_path}",
        )
        variants.append(
            {
                "folder": variant["folder"],
                "timing_path": variant["timing_path"],
                "timing_bytes": evidence["bytes"],
                "timing_sha256": evidence["sha256"],
                "frame_count": evidence["frame_count"],
                "duration_seconds": evidence["duration_seconds"],
            }
        )

    exposure = load_json(HOLO_EXPOSURE)
    hf_bound = exposure["hugging_face_metadata_evidence"]
    hf_info = load_json(hf_info_path)
    require(hf_info["id"] == "SitongGong/HoloAssist", "HF_REPOSITORY_MISMATCH")
    require(hf_info["sha"] == HOLO_REVISION, "HF_REVISION_MISMATCH")
    require(hf_info["private"] is False, "HF_REPOSITORY_PRIVATE")
    require(hf_info["gated"] is False, "HF_REPOSITORY_GATED")
    require(hf_bound["revision"] == HOLO_REVISION, "HF_BOUND_REVISION_MISMATCH")
    sibling_names = {
        item["rfilename"] for item in hf_info.get("siblings", [])
    }
    require(
        set(HOLO_ARCHIVE_PARTS) <= sibling_names,
        "HF_ARCHIVE_PARTS_MISSING_FROM_SIBLINGS",
    )

    archive_results = parse_archive_head_output(
        extract_archive_head_output(head_transcript_path)
    )
    archive_parts = [
        {
            "object_name": name,
            "revision": archive_results[name]["revision"],
            "size_bytes": archive_results[name]["size_bytes"],
            "etag": archive_results[name]["etag"],
            "accept_ranges": archive_results[name]["accept_ranges"],
            "public_redirect": True,
        }
        for name in sorted(archive_results)
    ]
    return {
        "dataset_lineage": "HOLOASSIST",
        "commitment_id": selection["commitment_id"],
        "slot": selection["slot"],
        "source_commitment_sha256": source_commitment,
        "identity": {
            "recording_root": group["recording_root"],
            "private_commitment": group["private_commitment"],
            "variants": variants,
        },
        "status": {
            "timing_closed": True,
            "hf_repository_public": True,
            "hf_repository_ungated": True,
            "hf_revision_closed": True,
            "archive_objects_public": True,
            "archive_part_sizes_closed": True,
            "archive_part_etags_closed": True,
            "selected_individual_video_exact_object_resolved": False,
            "selected_individual_audio_exact_object_resolved": False,
            "repair_required": True,
        },
        "hf_repository": {
            "repository": hf_info["id"],
            "revision": HOLO_REVISION,
            "private": False,
            "gated": False,
            "used_storage_bytes": hf_info["usedStorage"],
            "sibling_count": len(hf_info["siblings"]),
        },
        "archive_parts": archive_parts,
        "open_items": [
            "SELECTED_INDIVIDUAL_VIDEO_EXACT_OBJECT_UNRESOLVED",
            "SELECTED_INDIVIDUAL_AUDIO_EXACT_OBJECT_UNRESOLVED",
        ],
    }


def _private_identity_strings(
    private_groups: Sequence[Mapping[str, Any]],
) -> set[str]:
    values: set[str] = set()
    for group in private_groups:
        identity = group.get("identity")
        if not isinstance(identity, Mapping):
            continue
        for key in (
            "closure_root",
            "exact_object_or_session_id",
            "object_path",
            "exact_url",
            "recording_root",
        ):
            value = identity.get(key)
            if isinstance(value, str) and value:
                values.add(value)
        variants = identity.get("variants", [])
        if isinstance(variants, list):
            for variant in variants:
                if not isinstance(variant, Mapping):
                    continue
                for key in ("folder", "timing_path"):
                    value = variant.get(key)
                    if isinstance(value, str) and value:
                        values.add(value)
    return values


def _walk_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            keys.add(str(key).lower())
            keys.update(_walk_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(_walk_keys(child))
    return keys


def validate_public_non_disclosure(
    public: Mapping[str, Any],
    *,
    private_groups: Sequence[Mapping[str, Any]],
    review_text: str | None = None,
) -> None:
    leaked_keys = _walk_keys(public) & FORBIDDEN_PUBLIC_KEYS
    require(
        not leaked_keys,
        "PUBLIC_PRIVATE_KEY_LEAK:" + ",".join(sorted(leaked_keys)),
    )
    combined = canonical_bytes(public).decode("utf-8")
    if review_text is not None:
        combined += "\n" + review_text
    for identity in _private_identity_strings(private_groups):
        require(identity not in combined, "PUBLIC_IDENTITY_LEAK")
    require(
        not any(pattern.search(combined) for pattern in IDENTITY_PATTERNS),
        "PUBLIC_IDENTITY_PATTERN_LEAK",
    )
    require(
        not any(token in combined for token in FORBIDDEN_PUBLIC_TEXT),
        "PUBLIC_TECHNICAL_PATH_LEAK",
    )


def build_reports(
    *,
    diagnostic_root: Path = DEFAULT_DIAGNOSTIC_ROOT,
    hf_info_path: Path = DEFAULT_HF_INFO,
    head_transcript_path: Path = DEFAULT_HEAD_TRANSCRIPT,
) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_bound_inputs(
        diagnostic_root=diagnostic_root,
        hf_info_path=hf_info_path,
        head_transcript_path=head_transcript_path,
    )
    archive_head_output = extract_archive_head_output(head_transcript_path)
    summary = parse_summary(diagnostic_root / "summary.txt")
    groups = [
        validate_assembly(diagnostic_root, summary),
        validate_epic(diagnostic_root, summary),
        validate_holoassist(hf_info_path, head_transcript_path),
    ]
    groups.sort(key=lambda item: item["dataset_lineage"])

    retained_probe_body_bytes = sum(
        int(item["persisted_bytes"]) for item in summary.values()
    )
    media_body_bytes = sum(
        int(item["persisted_bytes"])
        for name, item in summary.items()
        if name.startswith("epic_")
    )
    error_body_bytes = retained_probe_body_bytes - media_body_bytes
    all_expected_closed = (
        groups[0]["status"]["gated_401_on_both_proxies"]
        and groups[1]["status"]["exact_total_bytes_closed"]
        and groups[2]["status"]["timing_closed"]
        and groups[2]["status"]["archive_objects_public"]
        and not groups[2]["status"][
            "selected_individual_video_exact_object_resolved"
        ]
        and not groups[2]["status"][
            "selected_individual_audio_exact_object_resolved"
        ]
    )
    final_marker = READY if all_expected_closed else REPAIR

    common = {
        "generated_date": GENERATED_DATE,
        "selection": {
            "rule": (
                "Exactly one frozen group per lineage, selected by the "
                "lexicographically minimum public v3.1 group commitment."
            ),
            "selection_field": SELECTION_FIELD,
            "lineage_count": len(LINEAGES),
            "selected_group_count": len(groups),
            "identity_fields_used_for_selection": False,
        },
        "scope": {
            "offline_only": True,
            "network_used_by_closure": False,
            "technical_metadata_only": True,
            "semantic_annotations_opened": False,
            "labels_opened": False,
            "transcripts_or_captions_opened": False,
            "media_content_inspected": False,
            "full_media_downloads": 0,
            "retained_media_body_files": 0,
            "retained_media_body_bytes": 0,
            "exposure_classification": EXPOSURE_CLASS,
        },
        "probe_payload_accounting": {
            "historical_response_body_bytes_reported_by_summary": (
                retained_probe_body_bytes
            ),
            "historical_media_range_body_bytes": media_body_bytes,
            "historical_gate_error_body_bytes": error_body_bytes,
            "retained_media_body_files_in_closure_evidence": 0,
            "retained_media_body_bytes_in_closure_evidence": 0,
            "headers_and_derived_metadata_retained": True,
        },
        "locks": {
            "roster_remained_locked": True,
            "replacement_executed": False,
            "test_construction_remained_locked": True,
            "distribution_remained_locked": True,
        },
        "decision_basis": {
            "expected_host_facts_closed": all_expected_closed,
            "assembly_anonymous_access_remains_gated": True,
            "epic_public_range_route_closed": True,
            "holoassist_timing_and_archive_host_facts_closed": True,
            "holoassist_selected_individual_av_objects_remain_unresolved": True,
            "closure_ready_does_not_mean_every_group_is_acquisition_ready": True,
        },
        "final_marker": final_marker,
    }
    private = {
        "schema_version": SCHEMA_PRIVATE,
        "artifact_classification": "CUSTODIAN_PRIVATE",
        **common,
        "source_bindings": {
            "repository_inputs": [
                file_binding(
                    path, public_path=path.relative_to(ROOT).as_posix()
                )
                for path in EXPECTED_FILE_SHA256
            ],
            "diagnostic_inputs": [
                file_binding(
                    diagnostic_root / name,
                    public_path=f"diagnostic_snapshot/{name}",
                )
                for name in sorted(EXPECTED_DIAGNOSTIC_SHA256)
            ],
            "hf_info": file_binding(
                hf_info_path, public_path="local_retained_hf_info.json"
            ),
            "archive_head_command_output": {
                "source_path": "local_retained_command_evidence.jsonl",
                "bytes": len(archive_head_output.encode("utf-8")),
                "sha256": sha256_bytes(
                    archive_head_output.encode("utf-8")
                ),
            },
        },
        "groups": groups,
    }
    public_groups = [
        {
            "dataset_lineage": group["dataset_lineage"],
            "commitment_id": group["commitment_id"],
            "status": dict(group["status"]),
            "exposure": EXPOSURE_CLASS,
        }
        for group in groups
    ]
    public = {
        "schema_version": SCHEMA_PUBLIC,
        "artifact_classification": "PUBLIC_COMMITMENT_STATUS_ONLY",
        **common,
        "groups": public_groups,
        "private_report_sha256": sha256_bytes(canonical_bytes(private)),
    }
    validate_public_non_disclosure(
        public, private_groups=groups, review_text=None
    )
    return private, public


def render_review(public: Mapping[str, Any]) -> str:
    group_map = {
        group["dataset_lineage"]: group for group in public["groups"]
    }
    lines = [
        "# Untouched v3.1 wave 1 host-probe closure",
        "",
        f"**Final marker: `{public['final_marker']}`**",
        "",
        "Closed on **October 15, 2026** from retained local evidence only.",
        "The closure performed no network operation, opened no media content,",
        "and did not modify the frozen ledger or technical-preflight outputs.",
        "",
        "## Public commitment status",
        "",
        "| Dataset lineage | Commitment | Host facts closed | Remaining repair | Exposure |",
        "|---|---|---:|---:|---|",
    ]
    for lineage in LINEAGES:
        group = group_map[lineage]
        status = group["status"]
        if lineage == "ASSEMBLY101":
            closed = (
                status["gated_401_on_both_proxies"]
                and status["gated_repo_error_on_both_proxies"]
            )
        elif lineage == "EPIC":
            closed = (
                status["range_206_on_both_proxies"]
                and status["exact_total_bytes_closed"]
                and status["etag_closed"]
            )
        else:
            closed = (
                status["timing_closed"]
                and status["archive_objects_public"]
                and status["archive_part_sizes_closed"]
                and status["archive_part_etags_closed"]
            )
        lines.append(
            f"| {lineage} | `{group['commitment_id']}` | "
            f"{'yes' if closed else 'no'} | "
            f"{'yes' if status['repair_required'] else 'no'} | "
            f"{group['exposure']} |"
        )
    accounting = public["probe_payload_accounting"]
    lines.extend(
        [
            "",
            "## Consolidated findings",
            "",
            "- Assembly101: the exact selected route returned **401** with",
            "  **GatedRepo** on both retained proxy observations. Anonymous",
            "  exact-media access therefore remains unresolved.",
            "- EPIC: the exact selected route returned **206 Partial Content**",
            "  on both retained proxy observations, with an identical exact",
            "  object total of **11,695,708,821 bytes**.",
            "- HoloAssist: retained timing evidence is closed. The pinned public",
            "  Hugging Face revision and five public archive-part objects have",
            "  closed part sizes and ETags.",
            "- HoloAssist selected individual video and audio exact objects",
            "  remain unresolved; archive-level availability is not upgraded to",
            "  selected-object A/V resolution.",
            "",
            "## Payload and exposure boundary",
            "",
            f"- Historical bounded response bytes reported by the diagnostic summary: **{accounting['historical_response_body_bytes_reported_by_summary']}**.",
            f"- Historical EPIC range bytes in those probes: **{accounting['historical_media_range_body_bytes']}**.",
            "- Retained media body files in closure evidence: **0**.",
            "- Retained media body bytes in closure evidence: **0**.",
            "- Exposure classification: **METADATA_ACCESS_ONLY**.",
            "- No identity is published in this review; the private report alone",
            "  maps commitments to exact identities and technical paths.",
            "",
            "## Decision semantics",
            "",
            "`WAVE1_HOST_PROBE_CLOSURE_READY` means the expected retained host",
            "facts were validated and the unresolved states were recorded",
            "without upgrading them. It does not authorize acquisition, replace",
            "a frozen group, or claim selected HoloAssist A/V object closure.",
            "",
            f"**{public['final_marker']}**",
            "",
        ]
    )
    return "\n".join(lines)


def atomic_write(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with temporary.open("wb") as handle:
            handle.write(data)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        os.chmod(path, mode)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def write_artifacts(
    private: Mapping[str, Any],
    public: Mapping[str, Any],
    review: str,
    *,
    private_path: Path = PRIVATE_OUTPUT,
    public_path: Path = PUBLIC_OUTPUT,
    review_path: Path = REVIEW_OUTPUT,
) -> None:
    validate_public_non_disclosure(
        public, private_groups=private["groups"], review_text=review
    )
    atomic_write(private_path, canonical_bytes(private), 0o600)
    atomic_write(public_path, canonical_bytes(public), 0o644)
    atomic_write(review_path, review.encode("utf-8"), 0o644)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--diagnostic-root",
        type=Path,
        default=DEFAULT_DIAGNOSTIC_ROOT,
    )
    parser.add_argument("--hf-info", type=Path, default=DEFAULT_HF_INFO)
    parser.add_argument(
        "--head-transcript",
        type=Path,
        default=DEFAULT_HEAD_TRANSCRIPT,
    )
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        private, public = build_reports(
            diagnostic_root=args.diagnostic_root,
            hf_info_path=args.hf_info,
            head_transcript_path=args.head_transcript,
        )
        review = render_review(public)
        if args.check:
            require(
                PRIVATE_OUTPUT.read_bytes() == canonical_bytes(private),
                "PRIVATE_OUTPUT_NOT_CURRENT",
            )
            require(
                PUBLIC_OUTPUT.read_bytes() == canonical_bytes(public),
                "PUBLIC_OUTPUT_NOT_CURRENT",
            )
            require(
                REVIEW_OUTPUT.read_text(encoding="utf-8") == review,
                "REVIEW_OUTPUT_NOT_CURRENT",
            )
        else:
            write_artifacts(private, public, review)
    except (ClosureError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"{REPAIR}:{exc}", file=sys.stderr)
        return 2
    print(public["final_marker"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
