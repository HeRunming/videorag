#!/usr/bin/env python3
"""Offline, bounded preflight for CaptainCook4D reserve recording 25_109.

This tool intentionally performs no network request.  It validates the frozen
secondary-B12 route against pre-existing official metadata and prior local
technical evidence.  A live range/audio probe is still required for READY.
Semantic annotation bodies are never opened.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

SCHEMA_VERSION = "av-trace.captaincook4d-25-109-vsa-preflight/1.0"
ROUTE_ID = "ARVSA-R04-CC4D-P05-E07"
RECORDING_ID = "25_109"
SOURCE_GROUP_ID = "cc4d_p05_e07"
PERSON_ID = 5
ENVIRONMENT_ID = 7
OFFICIAL_DURATION_SECONDS = 2126.96
LONG_DURATION_MIN_SECONDS = 1200.0

GOPRO_URL = (
    "https://utdallas.box.com/shared/static/"
    "qiu0plhm3ixqcfgu02qy9kmlp5tre6p2.mp4"
)
HOLOLENS_URL = (
    "https://utdallas.box.com/shared/static/"
    "ipq0k4e5l55cf9u8x1lvdy2uk6ko1od3.mp4"
)
GOPRO_BOX_ID = "qiu0plhm3ixqcfgu02qy9kmlp5tre6p2"
HOLOLENS_BOX_ID = "ipq0k4e5l55cf9u8x1lvdy2uk6ko1od3"

READY = "CAPTAINCOOK4D_25_109_VSA_PREFLIGHT_READY"
REPAIR = "CAPTAINCOOK4D_25_109_VSA_PREFLIGHT_REPAIR"
NO_GO = "CAPTAINCOOK4D_25_109_VSA_PREFLIGHT_NO_GO"

ROOT = Path(__file__).resolve().parents[1]
ROUTE_PATH = ROOT / "data/rehearsal_plan/audio_rich_vsa_acquisition_routes_v1.json"
REGISTRY_PATH = ROOT / "data/rehearsal_plan/captaincook4d_access_registry_v3.json"
RECORDING_INVENTORY_PATH = (
    ROOT
    / "data/source_recon/captaincook4d_access_v1/derived/"
    "recording_stream_inventory_v1.json"
)
GROUP_INVENTORY_PATH = (
    ROOT
    / "data/source_recon/captaincook4d_access_v1/derived/"
    "source_group_inventory_v1.json"
)
DOWNLOAD_LINKS_PATH = (
    ROOT / "data/source_recon/captaincook4d_access_v1/download_links.json"
)
VIDEO_INFORMATION_PATH = (
    ROOT / "data/source_recon/captaincook4d_access_v1/video_information.csv"
)
PROJECT_README_PATH = (
    ROOT / "data/source_recon/captaincook4d_access_v1/main_README.md"
)
DOWNLOADER_LICENSE_PATH = (
    ROOT / "data/source_recon/captaincook4d_access_v1/downloader_LICENSE"
)
ANNOTATION_TREE_PATH = (
    ROOT / "data/source_recon/captaincook4d_access_v1/annotations_tree.json"
)
WAVE0_MANIFEST_PATH = (
    ROOT
    / "data/restricted/captaincook4d_wave0_sources_v3/manifests/"
    "captaincook4d_wave0_acquisition_manifest.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "data/rehearsal_plan/captaincook4d_25_109_vsa_preflight_v1.json"
)

EXPECTED_INPUTS = {
    DOWNLOAD_LINKS_PATH: (
        700705,
        "81b1e1ef571621da182c5fc31ef97f177927a1a95b22aa545229794542e6f2b4",
    ),
    VIDEO_INFORMATION_PATH: (
        8684,
        "51febe466df9d336eaca8c5a467475bc3909b9d597208861316be78f4dd50138",
    ),
    PROJECT_README_PATH: (
        10276,
        "7a4e5566619bb4a85f83113a182e3b1731a65609acb4e46b4ddbfb3ed02c4a1c",
    ),
    DOWNLOADER_LICENSE_PATH: (
        11357,
        "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4",
    ),
}


class PreflightError(RuntimeError):
    """Stable failure for inconsistent frozen metadata."""


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
                pass
    elif isinstance(value, list):
        for child in value:
            try:
                return find_route(child)
            except PreflightError:
                pass
    raise PreflightError("FROZEN_ROUTE_NOT_FOUND")


def file_identity(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def validate_url(url: str, expected_id: str) -> None:
    parsed = urlsplit(url)
    expected_path = f"/shared/static/{expected_id}.mp4"
    if (
        parsed.scheme != "https"
        or parsed.hostname != "utdallas.box.com"
        or parsed.path != expected_path
        or parsed.query
        or parsed.fragment
    ):
        raise PreflightError("OFFICIAL_ASSET_URL_INVALID")


def validate_local_inputs() -> dict[str, Any]:
    identities: list[dict[str, Any]] = []
    for path, (expected_bytes, expected_sha256) in EXPECTED_INPUTS.items():
        observed = file_identity(path)
        if (
            observed["bytes"] != expected_bytes
            or observed["sha256"] != expected_sha256
        ):
            raise PreflightError(f"FROZEN_INPUT_DRIFT:{path.name}")
        identities.append(observed)

    route = find_route(load_json(ROUTE_PATH))
    exact = route.get("exact_ids_or_pool")
    if not isinstance(exact, Mapping):
        raise PreflightError("ROUTE_EXACT_IDS_MISSING")
    if (
        exact.get("preferred_source_group_id") != SOURCE_GROUP_ID
        or exact.get("preferred_recording_id") != RECORDING_ID
        or exact.get("preferred_duration_seconds") != OFFICIAL_DURATION_SECONDS
        or route.get("best_target_slot") != "B12"
        or route.get("selection_role") != "SECONDARY"
    ):
        raise PreflightError("FROZEN_ROUTE_IDENTITY_MISMATCH")

    inventory = load_json(RECORDING_INVENTORY_PATH)
    records = inventory.get("records")
    if not isinstance(records, list):
        raise PreflightError("RECORDING_INVENTORY_MISSING")
    selected = next(
        (
            item
            for item in records
            if isinstance(item, Mapping)
            and item.get("recording_id") == RECORDING_ID
        ),
        None,
    )
    if selected is None:
        raise PreflightError("RECORDING_NOT_FOUND")
    expected_record = {
        "person_id": PERSON_ID,
        "environment_id": ENVIRONMENT_ID,
        "source_group_id": SOURCE_GROUP_ID,
        "duration_seconds": OFFICIAL_DURATION_SECONDS,
        "gopro_360p_available": True,
        "hololens_sync_pv_video_available": True,
        "is_hololens_enabled": True,
        "is_spatial_enabled": True,
        "stream_count": 21,
    }
    for key, expected in expected_record.items():
        if selected.get(key) != expected:
            raise PreflightError(f"RECORDING_IDENTITY_MISMATCH:{key}")
    urls = selected.get("official_stream_urls")
    if not isinstance(urls, Mapping):
        raise PreflightError("OFFICIAL_STREAM_URLS_MISSING")
    if (
        urls.get("gopro_360p") != GOPRO_URL
        or urls.get("hololens_sync_pv_video") != HOLOLENS_URL
    ):
        raise PreflightError("OFFICIAL_STREAM_URL_MISMATCH")

    links = load_json(DOWNLOAD_LINKS_PATH)
    selected_links = links.get(RECORDING_ID)
    if not isinstance(selected_links, Mapping):
        raise PreflightError("DOWNLOAD_LINK_RECORD_MISSING")
    if (
        selected_links.get("gopro_360p") != GOPRO_URL
        or selected_links.get("hololens_sync_pv_video") != HOLOLENS_URL
    ):
        raise PreflightError("DOWNLOAD_LINK_IDENTITY_MISMATCH")
    validate_url(GOPRO_URL, GOPRO_BOX_ID)
    validate_url(HOLOLENS_URL, HOLOLENS_BOX_ID)

    with VIDEO_INFORMATION_PATH.open(newline="", encoding="utf-8") as handle:
        metadata_rows = list(csv.DictReader(handle))
    metadata = next(
        (row for row in metadata_rows if row["recording_id"] == RECORDING_ID),
        None,
    )
    if metadata is None:
        raise PreflightError("VIDEO_INFORMATION_ROW_MISSING")
    if (
        int(metadata["person_id"]) != PERSON_ID
        or int(metadata["environment_id"]) != ENVIRONMENT_ID
        or float(metadata["duration(sec)"]) != OFFICIAL_DURATION_SECONDS
    ):
        raise PreflightError("VIDEO_INFORMATION_IDENTITY_MISMATCH")

    groups = load_json(GROUP_INVENTORY_PATH).get("source_groups")
    if not isinstance(groups, list):
        raise PreflightError("SOURCE_GROUP_INVENTORY_MISSING")
    group = next(
        (
            item
            for item in groups
            if isinstance(item, Mapping)
            and item.get("source_group_id") == SOURCE_GROUP_ID
        ),
        None,
    )
    if group is None:
        raise PreflightError("SOURCE_GROUP_NOT_FOUND")
    expected_eligible = ["20_17", "23_6", "25_109", "26_19"]
    if (
        group.get("person_id") != PERSON_ID
        or group.get("environment_id") != ENVIRONMENT_ID
        or group.get("recording_count") != 10
        or group.get("eligible_recording_ids") != expected_eligible
        or group.get("eligible_with_hololens_pv_count") != 4
    ):
        raise PreflightError("SOURCE_GROUP_IDENTITY_MISMATCH")

    readme = PROJECT_README_PATH.read_text(encoding="utf-8")
    license_text = DOWNLOADER_LICENSE_PATH.read_text(encoding="utf-8")
    required_rights = (
        "Our dataset is licensed under the Apache license 2.0",
        "approved by the Institutional Review Board (IRB) at the University of Florida",
        "All participants provided written consent for the data collection",
    )
    if any(item not in readme for item in required_rights):
        raise PreflightError("RIGHTS_STATEMENT_MISSING")
    if (
        "Apache License" not in license_text
        or "Version 2.0, January 2004" not in license_text
    ):
        raise PreflightError("LICENSE_TEXT_INVALID")

    annotation_tree = load_json(ANNOTATION_TREE_PATH)
    annotation_paths = [
        str(item.get("path"))
        for item in annotation_tree.get("tree", [])
        if isinstance(item, Mapping)
    ]
    timestamp_carriers = sorted(
        path
        for path in annotation_paths
        if path
        in {
            "annotation_csv/step_annotations.csv",
            "annotation_csv/error_annotations.csv",
            "annotation_json/complete_step_annotations.json",
            "annotation_json/error_annotations.json",
        }
    )
    if len(timestamp_carriers) != 4:
        raise PreflightError("TIMESTAMP_ANNOTATION_PATHS_MISSING")

    registry = load_json(REGISTRY_PATH)
    wave0 = load_json(WAVE0_MANIFEST_PATH)
    selected_wave0 = set(wave0.get("selected_recording_ids", []))
    established_groups = {
        str(item.get("source_group_id"))
        for item in wave0.get("sources", [])
        if isinstance(item, Mapping)
    }
    if SOURCE_GROUP_ID in established_groups:
        raise PreflightError("LINEAGE_NOT_DISTINCT_FROM_WAVE0")

    return {
        "route": route,
        "record": dict(selected),
        "group": dict(group),
        "input_identities": identities,
        "timestamp_carriers": timestamp_carriers,
        "registry": registry,
        "wave0_selected_recordings": sorted(selected_wave0),
        "wave0_source_groups": sorted(established_groups),
    }


def classify(
    *,
    rights_access: bool,
    exact_asset: bool,
    duration: bool,
    native_audio: bool,
    hard_identity_failure: bool = False,
) -> tuple[str, list[str]]:
    if hard_identity_failure:
        return NO_GO, ["Frozen route or exact official asset identity failed."]
    blockers: list[str] = []
    if not rights_access:
        blockers.append(
            "Operative processing and restricted-annotation authority is not "
            "closed by the archived linked governance documents."
        )
    if not exact_asset:
        blockers.append(
            "No completed bounded 25_109 Box range exchange establishes exact "
            "object bytes."
        )
    if not duration:
        blockers.append("Long duration is not established.")
    if not native_audio:
        blockers.append(
            "No bounded container evidence proves native synchronized audio "
            "for either exact 25_109 MP4."
        )
    if not blockers:
        return READY, []
    return REPAIR, blockers


def build_report(*, local: Mapping[str, Any]) -> dict[str, Any]:
    rights_access = False
    exact_asset = False
    duration = OFFICIAL_DURATION_SECONDS >= LONG_DURATION_MIN_SECONDS
    native_audio = False
    marker, blockers = classify(
        rights_access=rights_access,
        exact_asset=exact_asset,
        duration=duration,
        native_audio=native_audio,
    )

    group = local["group"]
    family_a = ["20_17", "25_109"]
    family_b = ["23_6", "26_19"]
    eligible = set(group["eligible_recording_ids"])
    family_feasible = all(set(item).issubset(eligible) for item in (family_a, family_b))

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now(),
        "mode": "pre-existing-metadata-only",
        "target": {
            "slot": "B12",
            "selection_role": "SECONDARY",
            "dataset": "CaptainCook4D",
            "source_group_id": SOURCE_GROUP_ID,
            "recording_id": RECORDING_ID,
            "person_id": PERSON_ID,
            "environment_id": ENVIRONMENT_ID,
        },
        "scope": {
            "network_requests": 0,
            "full_media_downloads": 0,
            "media_bytes_read": 0,
            "media_bytes_persisted": 0,
            "semantic_annotation_files_opened": 0,
            "semantic_labels_opened": False,
            "human_review_performed": False,
            "v_plus_s_plus_a_claimed": False,
            "ses_claimed": False,
            "h_tier_claimed": False,
            "gate_a_claimed": False,
        },
        "pre_existing_inputs": local["input_identities"],
        "rights_and_access": {
            "dataset_license_statement": "Apache License 2.0",
            "dataset_license_statement_verified": True,
            "university_of_florida_irb_statement_verified": True,
            "written_participant_consent_statement_verified": True,
            "official_box_links_publicly_addressed": True,
            "operative_linked_irb_document_archived": False,
            "operative_linked_consent_document_archived": False,
            "processing_authority_closed": False,
            "restricted_annotation_authority_closed": False,
            "release_authority_closed": False,
            "go_gate_satisfied": rights_access,
        },
        "exact_official_assets": {
            "gopro_360p": {
                "url": GOPRO_URL,
                "box_shared_static_id": GOPRO_BOX_ID,
                "expected_bytes": None,
                "expected_sha256": None,
                "bounded_range_access_for_this_asset": "NOT_EVIDENCED",
                "native_audio_for_this_asset": "NOT_EVIDENCED",
            },
            "hololens_sync_pv_video": {
                "url": HOLOLENS_URL,
                "box_shared_static_id": HOLOLENS_BOX_ID,
                "expected_bytes": None,
                "expected_sha256": None,
                "bounded_range_access_for_this_asset": "NOT_EVIDENCED",
                "native_audio_for_this_asset": "NOT_EVIDENCED",
            },
            "identity_from_official_manifest": True,
            "exact_bytes_or_checksum_available": False,
            "go_gate_satisfied": exact_asset,
        },
        "duration": {
            "official_duration_seconds": OFFICIAL_DURATION_SECONDS,
            "official_duration_minutes": round(OFFICIAL_DURATION_SECONDS / 60, 4),
            "long_duration_threshold_seconds": LONG_DURATION_MIN_SECONDS,
            "long_duration_evidenced": duration,
            "container_duration_for_selected_asset": None,
        },
        "native_synchronized_audio": {
            "selected_view": "gopro_360p",
            "track_present": None,
            "codec": None,
            "channels": None,
            "sample_rate_hz": None,
            "av_timestamp_relation": "NOT_PROBED",
            "go_gate_satisfied": native_audio,
            "cross_recording_inference_rejected": True,
            "note": (
                "Prior GoPro audio evidence covers other recordings only and "
                "cannot establish audio for 25_109."
            ),
        },
        "lineage": {
            "policy": (
                "All recordings, views, annotations, and derivatives for "
                "person 5 x environment 7 remain in one source group."
            ),
            "recording_count": group["recording_count"],
            "recording_ids": group["recording_ids"],
            "distinct_from_wave0_recordings": local["wave0_selected_recordings"],
            "distinct_from_wave0_source_groups": local["wave0_source_groups"],
            "participant_environment_lineage_distinct": True,
        },
        "timestamp_annotations": {
            "availability": "PATHS_EVIDENCED_CONTENTS_SEALED",
            "official_tree_sha": "a8a920a3293c4db27099a20ddbe3a3a9be1283e3",
            "carrier_paths": local["timestamp_carriers"],
            "contents_opened_or_used_for_selection": False,
            "semantic_labels_opened": False,
        },
        "candidate_family_feasibility": {
            "status": (
                "TWO_NONSEMANTIC_METADATA_FAMILIES_FEASIBLE"
                if family_feasible
                else "NOT_FEASIBLE"
            ),
            "family_a_recording_ids": family_a,
            "family_b_recording_ids": family_b,
            "basis": (
                "Same source group, each recording is 20-90 minutes, each has "
                "official GoPro and HoloLens synchronized-PV routes. This is "
                "inventory feasibility only, not semantic candidate survival."
            ),
            "semantic_candidate_claimed": False,
            "vsa_credit": False,
        },
        "prior_route_context": {
            "primary_proxy_previously_succeeded_for_other_box_assets": True,
            "fallback_proxy_previously_unstable_for_box": True,
            "transferability_to_25_109_claimed": False,
            "new_live_probe_performed": False,
        },
        "go_rule": (
            "READY only if operative rights/access, exact selected asset, long "
            "duration, and native synchronized audio are all evidenced."
        ),
        "blockers": blockers,
        "final_marker": marker,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Rejected: this finalized tool is deliberately offline.",
    )
    args = parser.parse_args()
    if args.live:
        raise PreflightError("LIVE_NETWORK_DISABLED_BY_STOP_ORDER")

    report = build_report(local=validate_local_inputs())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(report["final_marker"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
