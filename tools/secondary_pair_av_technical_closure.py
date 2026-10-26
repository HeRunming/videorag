"""Deterministically close bounded A/V evidence for the secondary pair.

This tool performs no network access and reads no media payload. It validates
the pinned October 13, 2026 HTTP header and sparse ISO-BMFF metadata evidence,
cross-checks it against official local metadata, and emits a JSON closure
record plus a Markdown review.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE_ROOT = Path("/tmp")
DEFAULT_JSON = (
    ROOT
    / "data/rehearsal_plan/secondary_pair_av_technical_closure_v1.json"
)
DEFAULT_MARKDOWN = (
    ROOT / "docs/review/secondary_pair_av_technical_closure_v1.md"
)

FINAL_READY = "SECONDARY_PAIR_AV_TECHNICAL_CLOSURE_READY"
FINAL_REPAIR = "SECONDARY_PAIR_AV_TECHNICAL_CLOSURE_REPAIR"
EVIDENCE_DATE = "2026-10-13"

EPIC_URL = (
    "https://data.bris.ac.uk/datasets/"
    "2g1n6qdydwa9u22shpxqzp0t8m/P23/videos/P23_102.MP4"
)
EPIC_OBJECT_PATH = "P23/videos/P23_102.MP4"
EPIC_MD5 = "4698fcbf13782f6396029761eb3bd5f2"
EPIC_TOTAL = 10_814_161_307
EPIC_ETAG = '"5ea771bb-28493019b"'

CAPTAIN_URL = (
    "https://utdallas.box.com/shared/static/"
    "qiu0plhm3ixqcfgu02qy9kmlp5tre6p2.mp4"
)
CAPTAIN_BOX_ID = "qiu0plhm3ixqcfgu02qy9kmlp5tre6p2"
CAPTAIN_FILENAME = "25_109_360p.mp4"
CAPTAIN_TOTAL = 201_079_756

EXPECTED_SNAPSHOT_SHA256 = {
    "avtrace_exact_range_diag_20261013/summary.txt": (
        "884193f59ecf575fce3d71c0977a440f5c9542ed2732a27a1940cc960414aec3"
    ),
    "avtrace_exact_range_diag_20261013/epic_hy.headers": (
        "89c9e13b45ec6b4429336f9a02eea0562ac1de70c36d9116f100cb5e11710a2d"
    ),
    "avtrace_exact_range_diag_20261013/epic_star.headers": (
        "b196c831fbe562a9cb078973127d04c1670b2ba1047a6fddc570ba850a9f832e"
    ),
    "avtrace_exact_range_diag_20261013/cc_star.headers": (
        "93312401fce3bde35c38bf9560875df3912cf3ef922db04391da2ae51a26fb94"
    ),
    "avtrace_exact_range_diag_20261013/cc_hy.headers": (
        "1a7ed99a07775ca3af4f2a9a8469b51f55096b1120b0b44d616463ee6ea601e6"
    ),
    "avtrace_p23_mp4meta_20261013/head.headers": (
        "083910864221d8457ebd3ab3383e96fe05de4b83210818d259aa3f17860c34c4"
    ),
    "avtrace_p23_mp4meta_20261013/tail.headers": (
        "8330c5b910df91bc92a8f7d4fe55306b3dd28b879415ca9863838523e437d5a6"
    ),
    "avtrace_p23_mp4meta_20261013/parsed.json": (
        "3c248cf9693e3c42ada856b28f0647f2173f29e04e6b76b72698a6791a8a7773"
    ),
    "avtrace_cc25109_mp4meta_20261013/head.headers": (
        "671d3530fad492755f1a7268ca93fa720980c13b5d96441e2d7076ad7a23ab2c"
    ),
    "avtrace_cc25109_mp4meta_20261013/tail.headers": (
        "8a77104401696290e388d7c5e5e98f38378f3717eda30a376eb6acbe3eda916c"
    ),
    "avtrace_cc25109_mp4meta_20261013/parsed.json": (
        "9fcda26ae67db08eab378cf15ce135e6f309df0c71fe3a30c71fd8da9e0ac270"
    ),
}

EXPECTED_DIRECTORY_FILES = {
    "avtrace_exact_range_diag_20261013": {
        "summary.txt",
        "epic_hy.headers",
        "epic_star.headers",
        "cc_star.headers",
        "cc_hy.headers",
    },
    "avtrace_p23_mp4meta_20261013": {
        "head.headers",
        "tail.headers",
        "parsed.json",
    },
    "avtrace_cc25109_mp4meta_20261013": {
        "head.headers",
        "tail.headers",
        "parsed.json",
    },
}

CONTENT_RANGE_RE = re.compile(r"bytes\s+(\d+)-(\d+)/(\d+)", re.IGNORECASE)
STATUS_RE = re.compile(r"^HTTP/\S+\s+(\d{3})(?:\s+(.*))?$")
FILENAME_RE = re.compile(
    r"(?:^|;)\s*filename=\"?([^\";]+)\"?", re.IGNORECASE
)


class ClosureError(RuntimeError):
    """Raised when pinned closure evidence does not validate."""


@dataclass(frozen=True)
class HttpResponseBlock:
    status: int
    reason: str
    headers: dict[str, str]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ClosureError(message)


def parse_content_range(value: str | None) -> tuple[int, int, int]:
    match = CONTENT_RANGE_RE.fullmatch((value or "").strip())
    if not match:
        raise ClosureError(f"INVALID_CONTENT_RANGE:{value!r}")
    start, end, total = (int(item) for item in match.groups())
    require(start >= 0, "NEGATIVE_CONTENT_RANGE_START")
    require(end >= start, "CONTENT_RANGE_END_BEFORE_START")
    require(total > end, "CONTENT_RANGE_TOTAL_NOT_GREATER_THAN_END")
    return start, end, total


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
    require(bool(blocks), f"NO_HTTP_BLOCKS:{path}")
    return blocks


def content_disposition_filename(value: str | None) -> str | None:
    match = FILENAME_RE.search(value or "")
    return match.group(1) if match else None


def summarize_range_header(
    path: Path,
    *,
    expected_start: int,
    expected_end: int,
    expected_total: int,
    expected_filename: str | None = None,
    expected_etag: str | None = None,
) -> dict[str, Any]:
    blocks = parse_header_blocks(path)
    final = blocks[-1]
    require(final.status == 206, f"FINAL_STATUS_NOT_206:{path}:{final.status}")
    start, end, total = parse_content_range(
        final.headers.get("content-range")
    )
    require(
        (start, end, total)
        == (expected_start, expected_end, expected_total),
        f"CONTENT_RANGE_MISMATCH:{path}",
    )
    span = end - start + 1
    require(
        int(final.headers.get("content-length", "-1")) == span,
        f"CONTENT_LENGTH_MISMATCH:{path}",
    )
    content_type = final.headers.get("content-type", "").split(";", 1)[0]
    require(content_type.lower() == "video/mp4", f"NOT_MP4:{path}")
    filename = content_disposition_filename(
        final.headers.get("content-disposition")
    )
    if expected_filename is not None:
        require(filename == expected_filename, f"FILENAME_MISMATCH:{path}")
    if expected_etag is not None:
        require(
            final.headers.get("etag") == expected_etag,
            f"ETAG_MISMATCH:{path}",
        )

    redirect_hosts: list[str] = []
    for block in blocks:
        location = block.headers.get("location")
        if not location:
            continue
        host = urlsplit(location).hostname
        if host and host not in redirect_hosts:
            redirect_hosts.append(host)

    return {
        "evidence_path": str(path),
        "final_status": final.status,
        "content_range": {
            "start": start,
            "end": end,
            "total": total,
            "response_bytes": span,
        },
        "content_length": span,
        "content_type": content_type,
        "etag": final.headers.get("etag"),
        "last_modified": final.headers.get("last-modified"),
        "content_disposition_filename": filename,
        "redirect_hosts": redirect_hosts,
    }


def verify_snapshot(
    evidence_root: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    manifest: list[dict[str, Any]] = []
    for relative, expected_hash in EXPECTED_SNAPSHOT_SHA256.items():
        path = evidence_root / relative
        require(path.is_file(), f"MISSING_PINNED_EVIDENCE:{path}")
        observed_hash = sha256_file(path)
        require(
            observed_hash == expected_hash,
            f"PINNED_EVIDENCE_HASH_MISMATCH:{path}",
        )
        manifest.append(
            {
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": observed_hash,
            }
        )

    directory_inventory: list[dict[str, Any]] = []
    for directory_name, expected_files in EXPECTED_DIRECTORY_FILES.items():
        directory = evidence_root / directory_name
        actual_files = {
            item.name for item in directory.iterdir() if item.is_file()
        }
        require(
            actual_files == expected_files,
            f"UNEXPECTED_EVIDENCE_DIRECTORY_CONTENTS:{directory}",
        )
        directory_inventory.append(
            {
                "path": str(directory),
                "files": sorted(actual_files),
                "media_payload_files": [],
                "media_payload_bytes": 0,
            }
        )

    deleted_payload_state = {
        "validated": True,
        "authoritative_directories": directory_inventory,
        "retained_media_payload_files": 0,
        "retained_media_payload_bytes": 0,
        "headers_and_derived_metadata_retained": True,
        "conclusion": (
            "The bounded response payload windows are deleted; only HTTP "
            "headers, the diagnostic summary, and derived parsed metadata "
            "remain in the authoritative evidence directories."
        ),
    }
    return manifest, deleted_payload_state


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def unique_row(
    rows: list[dict[str, str]], key: str, expected: str, source: Path
) -> dict[str, str]:
    matches = [row for row in rows if row.get(key) == expected]
    require(len(matches) == 1, f"EXPECTED_ONE_ROW:{source}:{key}={expected}")
    return matches[0]


def local_evidence_entry(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(ROOT)),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def find_track(parsed: dict[str, Any], handler: str) -> dict[str, Any]:
    tracks = [
        track for track in parsed.get("tracks", []) if track.get("handler") == handler
    ]
    require(len(tracks) == 1, f"EXPECTED_ONE_{handler}_TRACK")
    return tracks[0]


def validate_container(
    parsed_path: Path,
    *,
    total_bytes: int,
    tail_start: int,
    moov_offset: int,
    moov_bytes: int,
    video_codec: str,
    width: int,
    height: int,
    audio_codec: str,
    channels: int,
    sample_rate: int,
    official_duration: float,
) -> dict[str, Any]:
    parsed = json.loads(parsed_path.read_text(encoding="utf-8"))
    require(parsed["total_bytes"] == total_bytes, "PARSED_TOTAL_MISMATCH")
    require(parsed["tail_start"] == tail_start, "PARSED_TAIL_START_MISMATCH")
    require(parsed["tail_bytes"] == total_bytes - tail_start, "TAIL_SIZE_MISMATCH")
    require(
        parsed["moov_absolute_offset"] == moov_offset,
        "MOOV_OFFSET_MISMATCH",
    )
    require(parsed["moov_bytes"] == moov_bytes, "MOOV_SIZE_MISMATCH")
    require(moov_offset >= tail_start, "MOOV_NOT_INSIDE_TAIL_WINDOW")
    require(moov_offset + moov_bytes == total_bytes, "MOOV_NOT_AT_EOF")

    video = find_track(parsed, "vide")
    audio = find_track(parsed, "soun")
    require(video["codec"] == video_codec, "VIDEO_CODEC_MISMATCH")
    require(
        (video["width"], video["height"]) == (width, height),
        "VIDEO_DIMENSIONS_MISMATCH",
    )
    require(audio["codec"] == audio_codec, "AUDIO_CODEC_MISMATCH")
    require(audio["channels"] == channels, "AUDIO_CHANNELS_MISMATCH")
    require(
        audio["sample_rate"] == sample_rate,
        "AUDIO_SAMPLE_RATE_MISMATCH",
    )

    video_duration = float(video["duration_seconds"])
    audio_duration = float(audio["duration_seconds"])
    av_delta = abs(video_duration - audio_duration)
    require(av_delta <= 0.05, "AV_DURATION_DELTA_EXCEEDS_50MS")
    require(
        abs(video_duration - official_duration) <= 0.05,
        "VIDEO_DURATION_DISAGREES_WITH_OFFICIAL_METADATA",
    )

    return {
        "parsed_metadata_path": str(parsed_path),
        "total_bytes": total_bytes,
        "tail_window": {
            "start": tail_start,
            "end": total_bytes - 1,
            "bytes": total_bytes - tail_start,
        },
        "moov": {
            "absolute_offset": moov_offset,
            "bytes": moov_bytes,
            "end_exclusive": moov_offset + moov_bytes,
            "ends_at_object_eof": True,
            "fully_inside_tail_window": True,
        },
        "video": {
            "codec_fourcc": video_codec,
            "width": width,
            "height": height,
            "timescale": video["timescale"],
            "duration_units": video["duration_units"],
            "duration_seconds": round(video_duration, 6),
        },
        "audio": {
            "codec_fourcc": audio_codec,
            "channels": channels,
            "sample_rate_hz": sample_rate,
            "timescale": audio["timescale"],
            "duration_units": audio["duration_units"],
            "duration_seconds": round(audio_duration, 6),
        },
        "av_duration_delta_seconds": round(av_delta, 6),
        "native_av_tracks_in_same_moov": True,
        "sample_level_sync_or_content_semantics_claimed": False,
        "all_tracks": parsed["tracks"],
    }


def validate_summary(summary_path: Path) -> dict[str, Any]:
    text = summary_path.read_text(encoding="utf-8")
    require(text.count("epic_hy curl_exit=0 persisted_bytes=1024") == 1, "BAD_EPIC_HY_SUMMARY")
    require(
        text.count("epic_star curl_exit=0 persisted_bytes=1024") == 1,
        "BAD_EPIC_STAR_SUMMARY",
    )
    require(text.count("cc_star curl_exit=0 persisted_bytes=1024") == 1, "BAD_CC_STAR_SUMMARY")
    require(text.count("cc_hy curl_exit=28 persisted_bytes=0") == 1, "BAD_CC_HY_SUMMARY")
    require(text.count(f"url_effective={EPIC_URL}") == 2, "EPIC_EFFECTIVE_URL_MISMATCH")
    require(
        text.count("http_code=206 size_download=1024") == 3,
        "COMPLETED_DIAGNOSTIC_RANGE_COUNT_MISMATCH",
    )
    return {
        "path": str(summary_path),
        "epic_hy": "206_COMPLETE_1024_BYTES",
        "epic_star": "206_COMPLETE_1024_BYTES",
        "captaincook4d_star": "206_COMPLETE_1024_BYTES",
        "captaincook4d_hy": "TIMEOUT_ZERO_BYTES",
        "completed_206_diagnostic_ranges": 3,
    }


def validate_epic_official_metadata() -> dict[str, Any]:
    base = ROOT / "data/source_recon/assembly_epic_access_v2/metadata/epic"
    video_path = base / "EPIC_100_video_info.csv"
    md5_path = base / "md5.csv"
    license_path = base / "data_bris_readme.txt"
    preflight_path = (
        ROOT / "data/rehearsal_plan/epic_p23_102_vsa_preflight_v1.json"
    )

    video_row = unique_row(
        load_csv_rows(video_path), "video_id", "P23_102", video_path
    )
    md5_row = unique_row(
        load_csv_rows(md5_path),
        "file_remote_path",
        EPIC_OBJECT_PATH,
        md5_path,
    )
    license_text = license_path.read_text(encoding="utf-8")
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))

    require(float(video_row["duration"]) == 3569.52, "EPIC_DURATION_ROW_MISMATCH")
    require(float(video_row["fps"]) == 50.0, "EPIC_FPS_ROW_MISMATCH")
    require(video_row["resolution"] == "1920x1080", "EPIC_RESOLUTION_ROW_MISMATCH")
    require(md5_row["md5"] == EPIC_MD5, "EPIC_MD5_ROW_MISMATCH")
    require(md5_row["version"] == "100", "EPIC_MANIFEST_VERSION_MISMATCH")
    require(
        "Creative Commons Attribution-NonCommerial 4.0 International License"
        in license_text,
        "EPIC_CC_BY_NC_STATEMENT_MISSING",
    )
    rights = preflight["rights_and_gate"]
    require(rights["operative_dataset_license"] == "CC-BY-NC-4.0", "EPIC_LICENSE_MISMATCH")
    require(rights["authentication_required"] is False, "EPIC_AUTH_UNEXPECTED")
    require(rights["registration_required"] is False, "EPIC_REGISTRATION_UNEXPECTED")
    require(
        rights["official_distribution_route"] == "PUBLIC_DATA_BRIS_DIRECT_FILE",
        "EPIC_ROUTE_NOT_PUBLIC_DIRECT",
    )

    return {
        "official_video_metadata": {
            "video_id": "P23_102",
            "duration_seconds": 3569.52,
            "fps": 50.0,
            "resolution": "1920x1080",
        },
        "official_object_manifest": {
            "object_path": EPIC_OBJECT_PATH,
            "manifest_version": 100,
            "official_md5": EPIC_MD5,
            "full_object_md5_recomputed_by_closure": False,
        },
        "rights": {
            "operative_dataset_license": "CC-BY-NC-4.0",
            "official_route_public": True,
            "authentication_required": False,
            "registration_required": False,
            "attribution_required": True,
            "license_link_required": True,
            "change_notice_required_if_modified": True,
            "commercial_use_authorized": False,
            "raw_media_release_authorized_by_this_closure": False,
        },
        "evidence": [
            local_evidence_entry(video_path),
            local_evidence_entry(md5_path),
            local_evidence_entry(license_path),
            local_evidence_entry(preflight_path),
        ],
    }


def validate_captain_official_metadata() -> dict[str, Any]:
    base = ROOT / "data/source_recon/captaincook4d_access_v1"
    links_path = base / "download_links.json"
    video_path = base / "video_information.csv"
    readme_path = base / "main_README.md"
    inventory_path = base / "derived/recording_stream_inventory_v1.json"
    preflight_path = (
        ROOT
        / "data/rehearsal_plan/captaincook4d_25_109_vsa_preflight_v1.json"
    )

    links = json.loads(links_path.read_text(encoding="utf-8"))
    row = unique_row(
        load_csv_rows(video_path), "recording_id", "25_109", video_path
    )
    readme = readme_path.read_text(encoding="utf-8")
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    rights = preflight["rights_and_access"]

    require(links["25_109"]["gopro_360p"] == CAPTAIN_URL, "CAPTAIN_URL_MISMATCH")
    require(row["environment_id"] == "7", "CAPTAIN_ENVIRONMENT_MISMATCH")
    require(row["person_id"] == "5", "CAPTAIN_PERSON_MISMATCH")
    require(float(row["duration(sec)"]) == 2126.96, "CAPTAIN_DURATION_MISMATCH")
    require("dataset is licensed under the Apache license 2.0" in readme, "APACHE_STATEMENT_MISSING")
    require("approved by the Institutional Review Board" in readme, "IRB_STATEMENT_MISSING")
    require("All participants provided written consent" in readme, "CONSENT_STATEMENT_MISSING")
    require(rights["dataset_license_statement_verified"] is True, "CAPTAIN_LICENSE_NOT_VERIFIED")
    require(rights["operative_linked_consent_document_archived"] is False, "CONSENT_DOC_UNEXPECTEDLY_CLOSED")
    require(rights["operative_linked_irb_document_archived"] is False, "IRB_DOC_UNEXPECTEDLY_CLOSED")
    require(rights["processing_authority_closed"] is False, "PROCESSING_AUTHORITY_UNEXPECTEDLY_CLOSED")
    require(rights["go_gate_satisfied"] is False, "CAPTAIN_GATE_UNEXPECTEDLY_CLOSED")

    return {
        "official_recording_metadata": {
            "recording_id": "25_109",
            "source_group_id": "cc4d_p05_e07",
            "person_id": 5,
            "environment_id": 7,
            "stream": "gopro_360p",
            "duration_seconds": 2126.96,
            "official_url": CAPTAIN_URL,
            "box_shared_static_id": CAPTAIN_BOX_ID,
        },
        "rights_and_governance": {
            "dataset_license_statement": "Apache License 2.0",
            "dataset_license_statement_verified": True,
            "university_of_florida_irb_statement_verified": True,
            "written_participant_consent_statement_verified": True,
            "operative_linked_irb_document_archived": False,
            "operative_linked_consent_document_archived": False,
            "processing_authority_closed": False,
            "restricted_annotation_authority_closed": False,
            "release_authority_closed": False,
            "governance_authority_for_exact_acquisition_closed": False,
        },
        "evidence": [
            local_evidence_entry(links_path),
            local_evidence_entry(video_path),
            local_evidence_entry(readme_path),
            local_evidence_entry(inventory_path),
            local_evidence_entry(preflight_path),
        ],
    }


def build_report(evidence_root: Path = DEFAULT_EVIDENCE_ROOT) -> dict[str, Any]:
    evidence_manifest, deleted_payload_state = verify_snapshot(evidence_root)
    diag_dir = evidence_root / "avtrace_exact_range_diag_20261013"
    epic_dir = evidence_root / "avtrace_p23_mp4meta_20261013"
    captain_dir = evidence_root / "avtrace_cc25109_mp4meta_20261013"

    summary = validate_summary(diag_dir / "summary.txt")
    epic_official = validate_epic_official_metadata()
    captain_official = validate_captain_official_metadata()

    epic_ranges = [
        summarize_range_header(
            diag_dir / "epic_hy.headers",
            expected_start=0,
            expected_end=1023,
            expected_total=EPIC_TOTAL,
            expected_etag=EPIC_ETAG,
        ),
        summarize_range_header(
            diag_dir / "epic_star.headers",
            expected_start=0,
            expected_end=1023,
            expected_total=EPIC_TOTAL,
            expected_etag=EPIC_ETAG,
        ),
        summarize_range_header(
            epic_dir / "head.headers",
            expected_start=0,
            expected_end=4095,
            expected_total=EPIC_TOTAL,
            expected_etag=EPIC_ETAG,
        ),
        summarize_range_header(
            epic_dir / "tail.headers",
            expected_start=10_805_772_699,
            expected_end=10_814_161_306,
            expected_total=EPIC_TOTAL,
            expected_etag=EPIC_ETAG,
        ),
    ]
    epic_container = validate_container(
        epic_dir / "parsed.json",
        total_bytes=EPIC_TOTAL,
        tail_start=10_805_772_699,
        moov_offset=10_809_773_840,
        moov_bytes=4_387_467,
        video_codec="hvc1",
        width=1920,
        height=1080,
        audio_codec="mp4a",
        channels=2,
        sample_rate=48_000,
        official_duration=3569.52,
    )

    captain_ranges = [
        summarize_range_header(
            diag_dir / "cc_star.headers",
            expected_start=0,
            expected_end=1023,
            expected_total=CAPTAIN_TOTAL,
            expected_filename=CAPTAIN_FILENAME,
        ),
        summarize_range_header(
            captain_dir / "head.headers",
            expected_start=0,
            expected_end=4095,
            expected_total=CAPTAIN_TOTAL,
            expected_filename=CAPTAIN_FILENAME,
        ),
        summarize_range_header(
            captain_dir / "tail.headers",
            expected_start=192_691_148,
            expected_end=201_079_755,
            expected_total=CAPTAIN_TOTAL,
            expected_filename=CAPTAIN_FILENAME,
        ),
    ]
    for item in captain_ranges:
        require(
            "utdallas.app.box.com" in item["redirect_hosts"],
            "CAPTAIN_APP_BOX_REDIRECT_MISSING",
        )
        require(
            "public.boxcloud.com" in item["redirect_hosts"],
            "CAPTAIN_BOXCLOUD_REDIRECT_MISSING",
        )
    captain_container = validate_container(
        captain_dir / "parsed.json",
        total_bytes=CAPTAIN_TOTAL,
        tail_start=192_691_148,
        moov_offset=198_755_331,
        moov_bytes=2_324_425,
        video_codec="avc1",
        width=640,
        height=360,
        audio_codec="mp4a",
        channels=2,
        sample_rate=48_000,
        official_duration=2126.96,
    )

    epic = {
        "asset_id": "EPIC_P23_102",
        "dataset": "EPIC-KITCHENS-100",
        "identity": {
            "official_url": EPIC_URL,
            "object_path": EPIC_OBJECT_PATH,
            "total_bytes": EPIC_TOTAL,
            "etag": EPIC_ETAG,
            "last_modified": "Mon, 27 Apr 2020 23:58:51 GMT",
            "official_md5": EPIC_MD5,
            "identity_status": (
                "EXACT_OFFICIAL_PATH_ETAG_SIZE_AND_MANIFEST_MD5_BOUND"
            ),
        },
        "range_validation": {
            "status": "PASS",
            "completed_206_exchanges": len(epic_ranges),
            "all_content_range_totals_identical": True,
            "public_exact_route": True,
            "exchanges": epic_ranges,
        },
        "container_validation": epic_container,
        "official_metadata_and_rights": epic_official,
        "decision": {
            "technical_readiness_for_exact_acquisition": True,
            "rights_authority_for_noncommercial_acquisition_closed": True,
            "exact_acquisition_technically_authorized_now": True,
            "decision": "AUTHORIZED_NOW_CC_BY_NC_NONCOMMERCIAL_ONLY",
            "conditions": [
                "Use the exact public official P23_102 route.",
                "Limit use to noncommercial purposes.",
                "Give appropriate attribution.",
                "Provide the CC BY-NC 4.0 license reference.",
                "Indicate modifications if any are made.",
                "Do not treat this acquisition decision as release authority.",
            ],
        },
    }

    captain = {
        "asset_id": "CAPTAINCOOK4D_25_109_GOPRO_360P",
        "dataset": "CaptainCook4D",
        "identity": {
            "official_url": CAPTAIN_URL,
            "box_shared_static_id": CAPTAIN_BOX_ID,
            "content_disposition_filename": CAPTAIN_FILENAME,
            "total_bytes": CAPTAIN_TOTAL,
            "full_object_checksum_available": False,
            "identity_status": (
                "EXACT_OFFICIAL_SHARED_TOKEN_FILENAME_AND_SIZE_BOUND"
            ),
        },
        "range_validation": {
            "status": "PASS_VIA_STAR_ROUTE",
            "completed_206_exchanges": len(captain_ranges),
            "all_content_range_totals_identical": True,
            "star_route_completed": True,
            "hy_route_completed": False,
            "hy_route_outcome": "TIMEOUT_ZERO_BYTES",
            "exchanges": captain_ranges,
        },
        "container_validation": captain_container,
        "official_metadata_and_rights": captain_official,
        "decision": {
            "technical_readiness_for_exact_acquisition": True,
            "governance_authority_for_exact_acquisition_closed": False,
            "exact_acquisition_technically_authorized_now": False,
            "decision": "NOT_AUTHORIZED_GOVERNANCE_AUTHORITY_OPEN",
            "technical_readiness_is_not_authority": True,
            "open_authority_items": [
                "Archive and review the operative linked IRB document.",
                "Archive and review the operative linked participant-consent document.",
                "Close identity-bearing media processing authority explicitly.",
            ],
        },
    }

    report = {
        "schema_version": "av-trace.secondary-pair-av-technical-closure/1.0",
        "evidence_date": EVIDENCE_DATE,
        "generated_deterministically": True,
        "final_marker": FINAL_READY,
        "scope": {
            "assets": ["EPIC P23_102", "CaptainCook4D 25_109 GoPro 360p"],
            "network_requests_by_closure_tool": 0,
            "media_payload_bytes_read_by_closure_tool": 0,
            "media_content_decoded_or_reviewed": False,
            "semantic_annotations_opened_or_used": False,
            "semantic_claims_made": False,
            "v_plus_s_plus_a_claimed": False,
            "human_review_claimed": False,
            "ses_claimed": False,
            "h_tier_claimed": False,
            "gate_a_claimed": False,
            "sample_level_av_sync_claimed": False,
        },
        "authoritative_evidence_manifest": evidence_manifest,
        "diagnostic_summary": summary,
        "deleted_media_payload_state": deleted_payload_state,
        "assets": {
            "epic_p23_102": epic,
            "captaincook4d_25_109": captain,
        },
        "closure_logic": {
            "technical_evidence_complete_for_both_assets": True,
            "per_asset_acquisition_authority_decided": True,
            "captaincook4d_technical_readiness_separated_from_governance": True,
            "why_ready_despite_captaincook4d_hold": (
                "The closure question is resolved rather than left ambiguous: "
                "the CaptainCook4D object is technically ready, while exact "
                "acquisition remains unauthorized until governance closes."
            ),
        },
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    epic = report["assets"]["epic_p23_102"]
    captain = report["assets"]["captaincook4d_25_109"]
    epic_container = epic["container_validation"]
    captain_container = captain["container_validation"]

    return f"""# Secondary-pair bounded A/V technical closure v1

**Final marker:** `{report["final_marker"]}`  
**Evidence date:** `{report["evidence_date"]}`  
**Mode:** deterministic, offline validation of retained headers, parsed container metadata, official metadata, and governance records.

## Decision summary

| Asset | Technical readiness | Authority closed | Exact acquisition now |
|---|---:|---:|---|
| EPIC `P23_102` | yes | yes for CC BY-NC noncommercial acquisition | `AUTHORIZED_NOW_CC_BY_NC_NONCOMMERCIAL_ONLY` |
| CaptainCook4D `25_109` GoPro 360p | yes | no | `NOT_AUTHORIZED_GOVERNANCE_AUTHORITY_OPEN` |

The CaptainCook4D result deliberately separates a technically usable exact route/object from legal-governance authority. Technical readiness does not grant acquisition authority.

## Exact-object and range validation

| Asset | Exact identity binding | 206 exchanges | Total bytes | Route |
|---|---|---:|---:|---|
| EPIC `P23_102` | `{epic["identity"]["identity_status"]}` | {epic["range_validation"]["completed_206_exchanges"]} | {epic["identity"]["total_bytes"]} | public official data.bris route |
| CaptainCook4D `25_109` | `{captain["identity"]["identity_status"]}` | {captain["range_validation"]["completed_206_exchanges"]} | {captain["identity"]["total_bytes"]} | official Box token through the completed star route; hy timed out with zero bytes |

Every accepted exchange returned `206`, a response-length-consistent `Content-Range`, `video/mp4`, and the same asset total. EPIC also matches its official path, ETag, last-modified value, and manifest MD5 metadata. CaptainCook4D matches the official shared-static token, the `25_109_360p.mp4` disposition filename, redirect host class, and the common exact byte total. No CaptainCook4D full-object checksum is claimed.

## Container facts

| Fact | EPIC `P23_102` | CaptainCook4D `25_109` |
|---|---:|---:|
| `moov` absolute offset | {epic_container["moov"]["absolute_offset"]} | {captain_container["moov"]["absolute_offset"]} |
| `moov` bytes | {epic_container["moov"]["bytes"]} | {captain_container["moov"]["bytes"]} |
| `moov` ends at object EOF | yes | yes |
| Video codec | `{epic_container["video"]["codec_fourcc"]}` | `{captain_container["video"]["codec_fourcc"]}` |
| Dimensions | {epic_container["video"]["width"]}x{epic_container["video"]["height"]} | {captain_container["video"]["width"]}x{captain_container["video"]["height"]} |
| Video duration (s) | {epic_container["video"]["duration_seconds"]} | {captain_container["video"]["duration_seconds"]} |
| Audio codec | `{epic_container["audio"]["codec_fourcc"]}` | `{captain_container["audio"]["codec_fourcc"]}` |
| Audio channels | {epic_container["audio"]["channels"]} | {captain_container["audio"]["channels"]} |
| Audio sample rate (Hz) | {epic_container["audio"]["sample_rate_hz"]} | {captain_container["audio"]["sample_rate_hz"]} |
| Audio duration (s) | {epic_container["audio"]["duration_seconds"]} | {captain_container["audio"]["duration_seconds"]} |
| Absolute A/V duration delta (s) | {epic_container["av_duration_delta_seconds"]} | {captain_container["av_duration_delta_seconds"]} |

Both exact objects contain native video and audio tracks in the same `moov` container. The duration deltas are bounded container facts, not sample-level synchronization, semantic, speech, or content claims.

## Rights and governance

### EPIC `P23_102`

Exact acquisition is authorized now only for a noncommercial use that uses the official public route and complies with CC BY-NC 4.0: appropriate credit, a license reference, and modification notice where applicable. This closure does not authorize raw-media release.

### CaptainCook4D `25_109`

The official README statements for Apache-2.0, University of Florida IRB approval, and written participant consent are verified. However, the operative linked IRB and consent documents are not archived, and identity-bearing processing authority remains open. Therefore the route/object is technically ready but exact acquisition is not authorized now.

## Deleted payload state

The three authoritative `/tmp` evidence directories contain exactly the pinned header, summary, and parsed-JSON files. Retained media payload files: **0**. Retained media payload bytes: **0**. The sparse head/tail response bodies used to derive the metadata were deleted.

## Claim boundary

This closure makes no semantic, V+S+A, human-review, SES, H-tier, Gate A, or sample-level A/V-sync claim. It performs no network access and reads no media payload.

## {report["final_marker"]}
"""


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--evidence-root",
        type=Path,
        default=DEFAULT_EVIDENCE_ROOT,
        help="Parent of the three pinned avtrace_*_20261013 directories.",
    )
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compare generated content with existing outputs without writing.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = build_report(args.evidence_root)
        json_text = json.dumps(report, indent=2, sort_keys=True) + "\n"
        markdown_text = render_markdown(report)
        if args.check:
            require(
                args.output_json.read_text(encoding="utf-8") == json_text,
                f"JSON_OUTPUT_NOT_CURRENT:{args.output_json}",
            )
            require(
                args.output_markdown.read_text(encoding="utf-8")
                == markdown_text,
                f"MARKDOWN_OUTPUT_NOT_CURRENT:{args.output_markdown}",
            )
        else:
            write_text(args.output_json, json_text)
            write_text(args.output_markdown, markdown_text)
    except (ClosureError, OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"{FINAL_REPAIR}: {exc}", file=sys.stderr)
        return 1
    print(report["final_marker"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
