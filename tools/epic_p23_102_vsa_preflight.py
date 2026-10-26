#!/usr/bin/env python3
"""Bounded exact-asset preflight for EPIC reserve source P23_102.

Plan-only and retained-head modes use only pre-existing repository metadata.
Live mode is intentionally limited to one exact official Data.Bris MP4, a
HEAD request, and bounded in-memory ISO-BMFF range probes through the shared
AV-TRACE stream preflight implementation. It has no full-download mode and
never opens semantic annotation tables.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from tools import hf_audio_stream_preflight as core
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    import hf_audio_stream_preflight as core  # type: ignore[no-redef]


SCHEMA_VERSION = "av-trace.epic-p23-102-vsa-preflight/1.0"
ROUTE_ID = "ARVSA-R03-EPIC-P23"
SLOT = "B08"
PARTICIPANT_ID = "P23"
VIDEO_ID = "P23_102"
DATASET = "EPIC-KITCHENS-100"
LICENSE_ID = "CC-BY-NC-4.0"

BASE_URL = "https://data.bris.ac.uk/datasets/2g1n6qdydwa9u22shpxqzp0t8m"
OBJECT_PATH = "P23/videos/P23_102.MP4"
ASSET_URL = f"{BASE_URL}/{OBJECT_PATH}"
EXPECTED_MD5 = "4698fcbf13782f6396029761eb3bd5f2"
EXPECTED_DURATION_SECONDS = 3569.52
EXPECTED_RESOLUTION = "1920x1080"
EXPECTED_FPS = 50.0

# Exact object identity retained from the completed official-object HEAD on
# 2026-10-12. No response body was transferred by that request.
EXPECTED_SIZE_BYTES = 10_814_161_307
EXPECTED_ETAG = '"5ea771bb-28493019b"'
EXPECTED_LAST_MODIFIED = "Mon, 27 Apr 2020 23:58:51 GMT"
EXPECTED_CONTENT_TYPE = "video/mp4"
EXPECTED_ACCEPT_RANGES = "bytes"

ROOT = Path(__file__).resolve().parents[1]
ROUTE_PATH = ROOT / "data/rehearsal_plan/audio_rich_vsa_acquisition_routes_v1.json"
ACCESS_REGISTRY_PATH = (
    ROOT / "data/rehearsal_plan/assembly_epic_access_registry_v2.json"
)
MANIFEST_PATH = (
    ROOT
    / "data/source_recon/assembly_epic_access_v2/derived/"
    "epic_video_manifest.csv"
)
MD5_PATH = (
    ROOT
    / "data/source_recon/assembly_epic_access_v2/metadata/epic/md5.csv"
)
SPLIT_PATH = (
    ROOT
    / "data/source_recon/assembly_epic_access_v2/metadata/epic/"
    "epic_100_splits.csv"
)
EXTENSION_PARTICIPANTS_PATH = (
    ROOT
    / "data/source_recon/assembly_epic_access_v2/metadata/epic/"
    "Extension_Participants.csv"
)
DATA_BRIS_README_PATH = (
    ROOT
    / "data/source_recon/assembly_epic_access_v2/metadata/epic/"
    "data_bris_readme.txt"
)
DOWNLOADER_PATH = (
    ROOT
    / "data/source_recon/assembly_epic_access_v2/metadata/epic/"
    "epic_downloader.py"
)
VERIFY_DOWNLOADER_PATH = (
    ROOT
    / "data/source_recon/assembly_epic_access_v2/metadata/epic/"
    "epic_video_downloader_verify.py"
)
ANNOTATION_TREE_PATH = (
    ROOT
    / "data/source_recon/assembly_epic_access_v2/api/epic/"
    "annotations_tree.json"
)
SOUNDS_TREE_PATH = (
    ROOT
    / "data/source_recon/assembly_epic_access_v2/api/epic/"
    "sounds_annotations_tree.json"
)
DEFAULT_OUTPUT = (
    ROOT / "data/rehearsal_plan/epic_p23_102_vsa_preflight_v1.json"
)

DEFAULT_PROXIES = (
    "https://proxy.example.invalid:3128",
    "https://proxy.example.invalid:3128",
)
WINDOW_BYTES = 1024 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_CANDIDATE_BYTES = 8 * 1024 * 1024
MAX_AGGREGATE_BYTES = 8 * 1024 * 1024
LONG_MIN_SECONDS = 1200.0
LONG_MAX_SECONDS = 5400.0

READY = "EPIC_P23_102_VSA_PREFLIGHT_READY"
REPAIR = "EPIC_P23_102_VSA_PREFLIGHT_REPAIR"
NO_GO = "EPIC_P23_102_VSA_PREFLIGHT_NO_GO"


class PreflightError(RuntimeError):
    """Stable preflight failure with no credential or signed-URL content."""


def utc_now() -> str:
    return (
        datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PreflightError(f"JSON_NOT_OBJECT:{path.relative_to(ROOT)}")
    return value


def find_route(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        if value.get("route_id") == ROUTE_ID:
            return value
        for child in value.values():
            try:
                return find_route(child)
            except PreflightError:
                continue
    elif isinstance(value, list):
        for child in value:
            try:
                return find_route(child)
            except PreflightError:
                continue
    raise PreflightError("FROZEN_ROUTE_NOT_FOUND")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def tree_paths(path: Path) -> set[str]:
    value = load_json(path)
    tree = value.get("tree")
    if not isinstance(tree, list):
        raise PreflightError("ANNOTATION_TREE_MISSING")
    return {
        str(item["path"])
        for item in tree
        if isinstance(item, Mapping) and isinstance(item.get("path"), str)
    }


def exact_candidate() -> core.DirectURLCandidate:
    return core.DirectURLCandidate.from_mapping(
        {
            "candidate_id": "epic-p23-102",
            "url": ASSET_URL,
            "size_bytes": EXPECTED_SIZE_BYTES,
            "etag": EXPECTED_ETAG,
            "last_modified": EXPECTED_LAST_MODIFIED,
            "content_type": EXPECTED_CONTENT_TYPE,
            "accept_ranges": EXPECTED_ACCEPT_RANGES,
        }
    )


def validate_local_inputs() -> dict[str, Any]:
    route = find_route(load_json(ROUTE_PATH))
    exact = route.get("exact_ids_or_pool")
    if not isinstance(exact, Mapping):
        raise PreflightError("ROUTE_EXACT_IDS_MISSING")
    expected_route = {
        "preferred_source_group_id": PARTICIPANT_ID,
        "preferred_video_id": VIDEO_ID,
        "preferred_duration_seconds": EXPECTED_DURATION_SECONDS,
    }
    for key, expected in expected_route.items():
        if exact.get(key) != expected:
            raise PreflightError(f"FROZEN_ROUTE_MISMATCH:{key}")
    if route.get("best_target_slot") != SLOT:
        raise PreflightError("FROZEN_SLOT_MISMATCH")

    registry = load_json(ACCESS_REGISTRY_PATH)
    epic = registry.get("epic")
    if not isinstance(epic, Mapping):
        raise PreflightError("EPIC_ACCESS_REGISTRY_MISSING")
    license_record = epic.get("license")
    access_record = epic.get("access")
    if not isinstance(license_record, Mapping) or not isinstance(
        access_record, Mapping
    ):
        raise PreflightError("EPIC_RIGHTS_OR_ACCESS_RECORD_MISSING")
    if license_record.get("spdx") != LICENSE_ID:
        raise PreflightError("LICENSE_REGISTRY_MISMATCH")
    if access_record.get("registration_required_for_data_bris_route") is not False:
        raise PreflightError("DATA_BRIS_GATE_STATE_MISMATCH")

    manifest_rows = read_csv(MANIFEST_PATH)
    by_video = {row["video_id"]: row for row in manifest_rows}
    selected = by_video.get(VIDEO_ID)
    if selected is None:
        raise PreflightError("SELECTED_VIDEO_NOT_IN_MANIFEST")
    expected_manifest = {
        "participant_id": PARTICIPANT_ID,
        "duration_seconds": str(EXPECTED_DURATION_SECONDS),
        "fps": str(EXPECTED_FPS),
        "resolution": EXPECTED_RESOLUTION,
        "media_manifest_version": "100",
        "md5": EXPECTED_MD5,
    }
    for key, expected in expected_manifest.items():
        if selected.get(key) != expected:
            raise PreflightError(f"SELECTED_MANIFEST_MISMATCH:{key}")

    md5_rows = read_csv(MD5_PATH)
    md5_match = [
        row
        for row in md5_rows
        if row.get("file_remote_path") == OBJECT_PATH
        and row.get("md5") == EXPECTED_MD5
        and row.get("version") == "100"
    ]
    if len(md5_match) != 1:
        raise PreflightError("EXACT_MD5_ROUTE_MISMATCH")

    split_rows = read_csv(SPLIT_PATH)
    selected_split = next(
        (row for row in split_rows if row.get("video_id") == VIDEO_ID), None
    )
    if selected_split is None:
        raise PreflightError("SELECTED_SPLIT_MEMBERSHIP_MISSING")

    extension_rows = read_csv(EXTENSION_PARTICIPANTS_PATH)
    participant = next(
        (
            row
            for row in extension_rows
            if row.get("Participant") == PARTICIPANT_ID
        ),
        None,
    )
    if participant is None or participant.get("ChangingKitchen") != "1":
        raise PreflightError("PARTICIPANT_LINEAGE_METADATA_MISMATCH")

    p23_long = sorted(
        (
            {
                "video_id": row["video_id"],
                "duration_seconds": float(row["duration_seconds"]),
                "duration_minutes": float(row["duration_minutes"]),
                "media_manifest_version": int(row["media_manifest_version"]),
                "md5": row["md5"],
            }
            for row in manifest_rows
            if row.get("participant_id") == PARTICIPANT_ID
            and LONG_MIN_SECONDS
            <= float(row["duration_seconds"])
            <= LONG_MAX_SECONDS
        ),
        key=lambda item: item["video_id"],
    )
    if len(p23_long) < 2:
        raise PreflightError("TWO_LONG_P23_FAMILIES_NOT_AVAILABLE")

    rights_text = DATA_BRIS_README_PATH.read_text(encoding="utf-8")
    if (
        "Creative Commons Attribution-NonCommerial 4.0 International License"
        not in rights_text.replace("\n", " ")
        or "may not use the material for commercial purposes." not in rights_text
    ):
        raise PreflightError("OFFICIAL_DATA_BRIS_LICENSE_TEXT_MISSING")

    downloader_text = DOWNLOADER_PATH.read_text(encoding="utf-8")
    verify_text = VERIFY_DOWNLOADER_PATH.read_text(encoding="utf-8")
    if BASE_URL not in downloader_text or BASE_URL not in verify_text:
        raise PreflightError("OFFICIAL_DOWNLOADER_BASE_URL_MISMATCH")
    if "return [d['participant_str'], 'videos'" not in downloader_text:
        raise PreflightError("OFFICIAL_EXTENSION_PATH_RULE_MISSING")

    annotation_paths = tree_paths(ANNOTATION_TREE_PATH)
    sounds_paths = tree_paths(SOUNDS_TREE_PATH)
    required_annotation_paths = {
        "EPIC_100_train.csv",
        "EPIC_100_validation.csv",
        "EPIC_100_test_timestamps.csv",
    }
    required_sound_paths = {
        "EPIC_Sounds_train.csv",
        "EPIC_Sounds_validation.csv",
        "EPIC_Sounds_recognition_test_timestamps.csv",
        "sound_events_not_categorised.csv",
    }
    if not required_annotation_paths <= annotation_paths:
        raise PreflightError("TIMESTAMP_ANNOTATION_ROUTE_MISSING")
    if not required_sound_paths <= sounds_paths:
        raise PreflightError("SOUND_TIMESTAMP_ROUTE_MISSING")

    return {
        "route": route,
        "registry": registry,
        "epic": epic,
        "selected_manifest": selected,
        "selected_split": selected_split,
        "participant_extension": participant,
        "p23_long_videos": p23_long,
        "candidate": exact_candidate(),
    }


def retained_head_evidence() -> dict[str, Any]:
    return {
        "status": "SUCCEEDED",
        "observed_at": "2026-10-12T08:17:19Z",
        "method": "HEAD",
        "url": ASSET_URL,
        "proxy_route": "https://proxy.example.invalid:3128",
        "http_status": 200,
        "content_type": EXPECTED_CONTENT_TYPE,
        "content_length": EXPECTED_SIZE_BYTES,
        "last_modified": EXPECTED_LAST_MODIFIED,
        "etag": EXPECTED_ETAG,
        "accept_ranges": EXPECTED_ACCEPT_RANGES,
        "response_body_bytes": 0,
        "identity_match": True,
        "authentication_requirement": "NOT_APPLICABLE_PUBLIC_OFFICIAL_ROUTE",
    }


def classify(
    *,
    rights_and_gate: bool,
    exact_asset: bool,
    long_duration: bool,
    range_access: bool,
    native_audio: bool,
    synchronized_timeline: bool,
    terminal_no_audio: bool = False,
    terminal_duration_failure: bool = False,
    terminal_identity_failure: bool = False,
) -> tuple[str, list[str]]:
    blockers: list[str] = []
    if not rights_and_gate:
        blockers.append("Operative dataset rights or gate state is unresolved.")
    if not exact_asset:
        blockers.append("Exact authoritative P23_102 object identity is unresolved.")
    if not long_duration:
        blockers.append("The 20-90 minute duration requirement is not evidenced.")
    if not range_access:
        blockers.append(
            "Bounded exact-object byte-range access was not completed or evidenced."
        )
    if not native_audio:
        blockers.append(
            "A native audio track in the exact P23_102 MP4 is not evidenced."
        )
    if not synchronized_timeline:
        blockers.append(
            "A synchronized native audio/video timeline is not evidenced."
        )
    if not blockers:
        return READY, []
    if (
        terminal_no_audio
        or terminal_duration_failure
        or terminal_identity_failure
    ):
        return NO_GO, blockers
    return REPAIR, blockers


def live_probe(
    local: Mapping[str, Any], proxies: Sequence[str]
) -> dict[str, Any]:
    budget = core.Budget(
        maximum_response_bytes=MAX_RESPONSE_BYTES,
        maximum_total_bytes=MAX_AGGREGATE_BYTES,
    )
    with core.SafeDirectURLRangeClient(
        allowed_host=lambda host: host.lower().rstrip(".") == "data.bris.ac.uk",
        proxies=proxies,
        budget=budget,
        maximum_candidate_bytes=MAX_CANDIDATE_BYTES,
        user_agent="AV-TRACE-EPIC-P23-102-VSA-Preflight/1.0",
    ) as client:
        result = core.run_candidate(
            local["candidate"], client, window_bytes=WINDOW_BYTES
        )
    return {
        "status": "COMPLETED",
        "candidate": result,
        "response_body_bytes_read": budget.total_bytes,
        "response_body_bytes_persisted": 0,
    }


def build_report(
    *,
    mode: str,
    local: Mapping[str, Any],
    retained_head: Mapping[str, Any] | None = None,
    live: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    candidate_result = live.get("candidate") if live else None
    head = retained_head
    if candidate_result and isinstance(candidate_result, Mapping):
        head_identity = candidate_result.get("head_identity")
        head = {
            "status": "SUCCEEDED"
            if candidate_result.get("identity_match") is True
            else "FAILED",
            "identity_match": candidate_result.get("identity_match") is True,
            "head_identity": head_identity,
            "authentication_requirement": (
                "NOT_APPLICABLE_PUBLIC_OFFICIAL_ROUTE"
            ),
        }

    rights_and_gate = True
    exact_asset = bool(head and head.get("identity_match") is True)
    long_duration = (
        LONG_MIN_SECONDS <= EXPECTED_DURATION_SECONDS <= LONG_MAX_SECONDS
    )
    range_access = bool(
        candidate_result
        and candidate_result.get("range_request_count", 0) > 0
        and candidate_result.get("identity_match") is True
    )
    native_audio = bool(
        candidate_result and candidate_result.get("audio_track_count", 0) >= 1
    )
    synchronized = bool(
        candidate_result
        and candidate_result.get("av_timeline_relation")
        == "PLAUSIBLY_SYNCHRONIZED"
    )
    terminal_no_audio = bool(
        candidate_result
        and candidate_result.get("container_parse_status") == "PARSED_ISO_BMFF"
        and candidate_result.get("audio_track_count") == 0
    )
    observed_duration = (
        candidate_result.get("duration_seconds") if candidate_result else None
    )
    terminal_duration_failure = bool(
        isinstance(observed_duration, (int, float))
        and not LONG_MIN_SECONDS <= float(observed_duration) <= LONG_MAX_SECONDS
    )
    terminal_identity_failure = bool(
        candidate_result
        and candidate_result.get("head_identity") is not None
        and candidate_result.get("identity_match") is not True
    )
    marker, blockers = classify(
        rights_and_gate=rights_and_gate,
        exact_asset=exact_asset,
        long_duration=long_duration,
        range_access=range_access,
        native_audio=native_audio,
        synchronized_timeline=synchronized,
        terminal_no_audio=terminal_no_audio,
        terminal_duration_failure=terminal_duration_failure,
        terminal_identity_failure=terminal_identity_failure,
    )

    p23_long = local["p23_long_videos"]
    probe_bytes = int((live or {}).get("response_body_bytes_read", 0))
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "audit_date": "2026-10-12",
        "mode": mode,
        "final_marker": marker,
        "disposition": marker.rsplit("_", 1)[-1],
        "scope": {
            "route_id": ROUTE_ID,
            "target_slot": SLOT,
            "participant_id": PARTICIPANT_ID,
            "video_id": VIDEO_ID,
            "bounded_metadata_and_exact_asset_preflight_only": True,
            "full_media_downloads": 0,
            "media_bytes_persisted": 0,
            "semantic_annotation_files_opened": 0,
            "semantic_labels_used": False,
            "human_review_performed": False,
            "v_plus_s_plus_a_claimed": False,
            "ses_or_h_tier_claimed": False,
            "gate_a_claimed": False,
        },
        "rights_and_gate": {
            "operative_dataset_license": LICENSE_ID,
            "official_license_evidence": str(
                DATA_BRIS_README_PATH.relative_to(ROOT)
            ),
            "attribution_required": True,
            "noncommercial_restriction": True,
            "commercial_use_authorized": False,
            "official_distribution_route": "PUBLIC_DATA_BRIS_DIRECT_FILE",
            "registration_required": False,
            "authentication_required": False,
            "dataset_gate": "NONE_ON_OFFICIAL_DATA_BRIS_ROUTE",
            "bounded_preflight_authorized": True,
            "full_acquisition_or_processing_authorized_by_this_run": False,
            "release_authorized": False,
            "license_is_not_privacy_or_release_clearance": True,
        },
        "authoritative_asset": {
            "dataset": DATASET,
            "participant_id": PARTICIPANT_ID,
            "video_id": VIDEO_ID,
            "official_downloader_commit": local["epic"]["release"].get(
                "downloader_commit"
            ),
            "base_url": BASE_URL,
            "object_path": OBJECT_PATH,
            "url": ASSET_URL,
            "expected_size_bytes_from_retained_head": EXPECTED_SIZE_BYTES,
            "expected_md5_from_official_manifest": EXPECTED_MD5,
            "checksum_recomputed_by_this_run": False,
            "etag": EXPECTED_ETAG,
            "last_modified": EXPECTED_LAST_MODIFIED,
            "content_type": EXPECTED_CONTENT_TYPE,
            "accept_ranges": EXPECTED_ACCEPT_RANGES,
            "official_mechanism": (
                "EPIC download-scripts-100 extension path rule: "
                "participant/videos/video_id.MP4"
            ),
        },
        "access_evidence": {
            "retained_or_live_head": head or {"status": "NOT_RUN"},
            "bounded_range_access_succeeded": range_access,
            "bounded_probe_bytes_read": probe_bytes,
            "bounded_probe_bytes_persisted": 0,
            "live_candidate_result": candidate_result,
            "limits": {
                "maximum_response_bytes": MAX_RESPONSE_BYTES,
                "maximum_candidate_bytes": MAX_CANDIDATE_BYTES,
                "maximum_aggregate_bytes": MAX_AGGREGATE_BYTES,
                "initial_head_and_tail_window_bytes": WINDOW_BYTES,
                "complete_object_range_prohibited": True,
            },
            "stop_boundary": {
                "user_stopped_live_network_activity": True,
                "network_attempts_after_stop": 0,
                "partially_started_range_probe_used_as_evidence": False,
                "aborted_range_attempt_body_bytes": (
                    "UNKNOWN_NOT_USED_AS_EVIDENCE"
                ),
                "aborted_range_attempt_files_remaining": 0,
            },
        },
        "duration_and_streams": {
            "official_duration_seconds": EXPECTED_DURATION_SECONDS,
            "official_duration_minutes": EXPECTED_DURATION_SECONDS / 60,
            "long_duration_gate": "PASS",
            "official_resolution": EXPECTED_RESOLUTION,
            "official_fps": EXPECTED_FPS,
            "bounded_container_duration_seconds": observed_duration,
            "bounded_container_parse_status": (
                candidate_result.get("container_parse_status")
                if candidate_result
                else "NOT_RUN"
            ),
            "declared_video_track_count": (
                candidate_result.get("video_track_count", 0)
                if candidate_result
                else 0
            ),
            "declared_audio_track_count": (
                candidate_result.get("audio_track_count", 0)
                if candidate_result
                else 0
            ),
            "native_audio_status": (
                "EXACT_FILE_DECLARED_AUDIO_TRACK_EVIDENCED"
                if native_audio
                else "DATASET_LEVEL_ONLY_EXACT_FILE_UNRESOLVED"
            ),
            "av_timeline_relation": (
                candidate_result.get("av_timeline_relation")
                if candidate_result
                else "UNRESOLVED"
            ),
            "samples_decoded_or_heard": False,
        },
        "participant_and_kitchen_lineage": {
            "source_group_id": PARTICIPANT_ID,
            "conservative_group_definition": (
                "All P23 recordings, kitchens, native streams, annotations, "
                "features, clips, encodes, and derivatives remain one group."
            ),
            "extension_participant_category": "CHANGING_KITCHEN",
            "distinct_participant_id_from_current_epic_groups": {
                "current_groups": ["P27", "P28"],
                "distinct": True,
            },
            "kitchen_identifier_available": False,
            "cross_dataset_hd_epic_overlap": "REQUIRES_SEPARATE_CHECK",
            "lineage_claim_limit": (
                "Participant-level distinctness is established; no independent "
                "kitchen identity beyond the conservative P23 block is claimed."
            ),
        },
        "timestamp_annotations": {
            "action_and_narration_timestamp_route": "PRESENT_BUT_SEALED",
            "sound_timestamp_route": (
                "DATASET_LEVEL_PRESENT_EXACT_VIDEO_MEMBERSHIP_NOT_OPENED"
            ),
            "selected_video_split_membership_present": True,
            "tree_metadata_files_checked": [
                "EPIC_100_train.csv",
                "EPIC_100_validation.csv",
                "EPIC_100_test_timestamps.csv",
                "EPIC_Sounds_train.csv",
                "EPIC_Sounds_validation.csv",
                "EPIC_Sounds_recognition_test_timestamps.csv",
                "sound_events_not_categorised.csv",
            ],
            "annotation_bodies_opened": False,
            "semantic_labels_opened_or_used": False,
            "timestamp_values_claimed": False,
        },
        "two_candidate_family_feasibility": {
            "status": "TECHNICALLY_FEASIBLE_WITHIN_ONE_ADMITTED_SOURCE_GROUP",
            "long_video_count_20_to_90_minutes": len(p23_long),
            "metadata_only_pool": p23_long,
            "two_frozen_nonsemantic_leads": [
                VIDEO_ID,
                next(
                    item["video_id"]
                    for item in p23_long
                    if item["video_id"] != VIDEO_ID
                    and item["media_manifest_version"] == 100
                ),
            ],
            "selection_fields": [
                "participant ID",
                "video ID",
                "duration",
                "manifest version",
                "official checksum",
            ],
            "semantic_selection_used": False,
            "scientific_defensibility_or_independence_claimed": False,
        },
        "routing_only_boundary": {
            "speech": "UNKNOWN",
            "source_world_audio": "UNKNOWN_FOR_EXACT_FILE",
            "semantic_credit": False,
            "note": (
                "Dataset-level EPIC-SOUNDS evidence does not substitute for an "
                "exact-file native audio-track probe."
            ),
        },
        "decision": {
            "go_rule": (
                "READY only if operative rights/gate, exact authoritative "
                "asset identity and bounded access, long duration, and native "
                "synchronized audio are evidenced."
            ),
            "blockers": blockers,
            "why_repair_not_no_go": (
                "The official public object, license, exact URL, retained HEAD "
                "identity, checksum manifest, and long duration are established, "
                "while the stopped bounded range/container probe leaves exact-"
                "file native audio unresolved rather than disproven."
            )
            if marker == REPAIR
            else None,
        },
        "reproduction": {
            "plan_only": (
                "python tools/epic_p23_102_vsa_preflight.py --plan-only"
            ),
            "retained_head": (
                "python tools/epic_p23_102_vsa_preflight.py --retained-head"
            ),
            "live_future_only": (
                "python tools/epic_p23_102_vsa_preflight.py --live "
                "--proxy https://proxy.example.invalid:3128 "
                "--proxy https://proxy.example.invalid:3128"
            ),
        },
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan-only", action="store_true")
    mode.add_argument("--retained-head", action="store_true")
    mode.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--proxy",
        action="append",
        default=[],
        help="Explicit proxy route; repeat for ordered failover.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        local = validate_local_inputs()
        if args.plan_only:
            report = build_report(mode="plan-only", local=local)
        elif args.retained_head:
            report = build_report(
                mode="retained-head",
                local=local,
                retained_head=retained_head_evidence(),
            )
        else:
            proxies = tuple(args.proxy) if args.proxy else DEFAULT_PROXIES
            live = live_probe(local, proxies)
            report = build_report(mode="live", local=local, live=live)
        core.atomic_write_json(args.output, report)
        print(report["final_marker"])
        return 0
    except (PreflightError, core.PreflightError) as exc:
        print(f"ERROR:{exc}", file=sys.stderr)
        return 2
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(
            f"ERROR:INPUT_OR_OUTPUT_{type(exc).__name__.upper()}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
