#!/usr/bin/env python3
"""Build Task174 CaptainCook4D metadata-only access artifacts.

This script is deliberately offline.  It reads only the official-source
evidence already retained under data/source_recon/captaincook4d_access_v1.
"""

from __future__ import annotations

import csv
import hashlib
import json
import statistics
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
RECON = ROOT / "data/source_recon/captaincook4d_access_v1"
DERIVED = RECON / "derived"
REGISTRY_PATH = ROOT / "data/rehearsal_plan/captaincook4d_access_registry_v1.json"
TODAY = date(2026, 10, 2).isoformat()
DECISION = "CAPTAINCOOK4D_ACCESS_REPAIR"
MIN_SECONDS = 20 * 60
MAX_SECONDS = 90 * 60


def natural_recording_id(recording_id: str) -> tuple[int, ...]:
    return tuple(int(part) for part in recording_id.split("_"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=False, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def stream_score(recording: dict[str, object]) -> tuple[int, int, int, float]:
    """Higher is better except that duration distance is negated."""
    return (
        int(recording["hololens_sync_pv_video_available"]),
        int(recording["is_spatial_enabled"]),
        int(recording["stream_count"]),
        -abs(float(recording["duration_seconds"]) - 1800.0),
    )


def choose_representative(recordings: list[dict[str, object]]) -> dict[str, object]:
    """Pick an eligible recording deterministically within a source group."""
    return sorted(
        recordings,
        key=lambda row: (
            -int(row["hololens_sync_pv_video_available"]),
            -int(row["is_spatial_enabled"]),
            -int(row["stream_count"]),
            abs(float(row["duration_seconds"]) - 1800.0),
            natural_recording_id(str(row["recording_id"])),
        ),
    )[0]


def selected_record(
    row: dict[str, object],
    role: str,
    rank: int,
    replacement_for: str | None = None,
) -> dict[str, object]:
    result = {
        "role": role,
        "rank": rank,
        "source_group_id": row["source_group_id"],
        "person_id": row["person_id"],
        "environment_id": row["environment_id"],
        "representative_recording_id": row["recording_id"],
        "duration_seconds": row["duration_seconds"],
        "duration_minutes": row["duration_minutes"],
        "gopro_360p_available": row["gopro_360p_available"],
        "gopro_4k_available": row["gopro_4k_available"],
        "hololens_sync_pv_video_available": row[
            "hololens_sync_pv_video_available"
        ],
        "is_hololens_enabled": row["is_hololens_enabled"],
        "is_spatial_enabled": row["is_spatial_enabled"],
        "microphone_manifest_key_available": row[
            "microphone_manifest_key_available"
        ],
        "native_audio_status": "UNRESOLVED_NO_SUCCESSFUL_CONTAINER_PROBE",
        "stream_count": row["stream_count"],
        "available_streams": row["available_streams"],
        "official_stream_urls": row["official_stream_urls"],
    }
    if replacement_for is not None:
        result["replacement_for_source_group_id"] = replacement_for
    return result


def main() -> None:
    DERIVED.mkdir(parents=True, exist_ok=True)

    links_path = RECON / "download_links.json"
    video_info_path = RECON / "video_information.csv"
    links: dict[str, dict[str, object]] = json.loads(links_path.read_text())
    rows = list(csv.DictReader(video_info_path.open(encoding="utf-8")))

    csv_ids = {row["recording_id"] for row in rows}
    link_ids = set(links)
    if len(rows) != 384 or len(csv_ids) != 384 or csv_ids != link_ids:
        raise RuntimeError(
            "Expected an exact 384-recording join between video_information.csv "
            "and download_links.json"
        )

    inventory: list[dict[str, object]] = []
    all_stream_keys: Counter[str] = Counter()
    domains: Counter[str] = Counter()
    url_count = 0
    unique_urls: set[str] = set()

    for csv_row in rows:
        recording_id = csv_row["recording_id"]
        link_row = links[recording_id]
        stream_urls = {
            key: value
            for key, value in sorted(link_row.items())
            if not key.startswith("is_") and isinstance(value, str)
        }
        for key, value in stream_urls.items():
            all_stream_keys[key] += 1
            domains[urlparse(value).netloc] += 1
            url_count += 1
            unique_urls.add(value)

        stream_names = sorted(stream_urls)
        microphone_keys = [
            key
            for key in stream_names
            if key == "mc"
            or key.endswith("_mc")
            or "_mc_" in key
            or "microphone" in key
        ]
        duration_seconds = float(csv_row["duration(sec)"])
        person_id = int(csv_row["person_id"])
        environment_id = int(csv_row["environment_id"])
        inventory.append(
            {
                "recording_id": recording_id,
                "person_id": person_id,
                "environment_id": environment_id,
                "source_group_id": f"cc4d_p{person_id:02d}_e{environment_id:02d}",
                "duration_seconds": duration_seconds,
                "duration_minutes": round(duration_seconds / 60.0, 4),
                "eligible_duration_20_to_90_minutes": (
                    MIN_SECONDS <= duration_seconds <= MAX_SECONDS
                ),
                "gopro_360p_available": "gopro_360p" in stream_urls,
                "gopro_4k_available": "gopro_4k" in stream_urls,
                "hololens_sync_pv_video_available": (
                    "hololens_sync_pv_video" in stream_urls
                ),
                "is_hololens_enabled": bool(
                    link_row.get("is_hololens_enabled", False)
                ),
                "is_spatial_enabled": bool(
                    link_row.get("is_spatial_enabled", False)
                ),
                "microphone_manifest_key_available": bool(microphone_keys),
                "microphone_manifest_keys": microphone_keys,
                "stream_count": len(stream_urls),
                "available_streams": stream_names,
                "official_stream_urls": stream_urls,
            }
        )

    inventory.sort(key=lambda row: natural_recording_id(str(row["recording_id"])))
    by_id = {str(row["recording_id"]): row for row in inventory}

    grouped: dict[tuple[int, int], list[dict[str, object]]] = defaultdict(list)
    for row in inventory:
        grouped[(int(row["person_id"]), int(row["environment_id"]))].append(row)

    source_groups: list[dict[str, object]] = []
    group_representatives: dict[tuple[int, int], dict[str, object]] = {}
    for (person_id, environment_id), group_rows in sorted(grouped.items()):
        group_rows.sort(
            key=lambda row: natural_recording_id(str(row["recording_id"]))
        )
        eligible = [
            row
            for row in group_rows
            if row["eligible_duration_20_to_90_minutes"]
            and row["gopro_360p_available"]
        ]
        preferred = [
            row for row in eligible if row["hololens_sync_pv_video_available"]
        ]
        if eligible:
            group_representatives[(person_id, environment_id)] = (
                choose_representative(eligible)
            )
        source_groups.append(
            {
                "source_group_id": f"cc4d_p{person_id:02d}_e{environment_id:02d}",
                "person_id": person_id,
                "environment_id": environment_id,
                "recording_count": len(group_rows),
                "recording_ids": [row["recording_id"] for row in group_rows],
                "duration_seconds_total": round(
                    sum(float(row["duration_seconds"]) for row in group_rows), 2
                ),
                "eligible_recording_count": len(eligible),
                "eligible_recording_ids": [
                    row["recording_id"] for row in eligible
                ],
                "eligible_with_hololens_pv_count": len(preferred),
                "representative_recording_id": (
                    group_representatives[(person_id, environment_id)][
                        "recording_id"
                    ]
                    if eligible
                    else None
                ),
                "person_level_supergroup_id": f"cc4d_p{person_id:02d}",
            }
        )

    # One primary source group per person.  Compare the complete Cartesian
    # product lexicographically to make the diversity preference reproducible.
    groups_by_person: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for group, representative in group_representatives.items():
        if representative["hololens_sync_pv_video_available"]:
            groups_by_person[group[0]].append(group)
    if sorted(groups_by_person) != list(range(1, 9)):
        raise RuntimeError("Could not form an eight-person eligible candidate pool")

    import itertools

    best_score: tuple[object, ...] | None = None
    best_combo: tuple[tuple[int, int], ...] | None = None
    for combo in itertools.product(
        *(sorted(groups_by_person[person]) for person in range(1, 9))
    ):
        representatives = [group_representatives[group] for group in combo]
        score = (
            sum(
                int(row["hololens_sync_pv_video_available"])
                for row in representatives
            ),
            sum(int(row["is_spatial_enabled"]) for row in representatives),
            len({group[1] for group in combo}),
            sum(int(row["stream_count"]) for row in representatives),
            -sum(
                abs(float(row["duration_seconds"]) - 1800.0)
                for row in representatives
            ),
        )
        if (
            best_score is None
            or score > best_score
            or (score == best_score and combo < best_combo)
        ):
            best_score = score
            best_combo = combo
    assert best_combo is not None

    primary_rows = [group_representatives[group] for group in best_combo]
    primary = [
        selected_record(row, "PRIMARY", rank)
        for rank, row in enumerate(primary_rows, start=1)
    ]

    # Two alternates from non-primary groups.  Require distinct replacement
    # persons and environments, then prefer HoloLens PV, spatial, stream
    # coverage, and durations nearest 30 minutes.  Map each alternate to the
    # same-person primary so activating it preserves eight-person diversity.
    non_primary_groups = [
        group
        for group in sorted(group_representatives)
        if group not in set(best_combo)
    ]
    replacement_score: tuple[object, ...] | None = None
    replacement_pair: tuple[tuple[int, int], tuple[int, int]] | None = None
    for group_a, group_b in itertools.combinations(non_primary_groups, 2):
        if group_a[0] == group_b[0] or group_a[1] == group_b[1]:
            continue
        representatives = [
            group_representatives[group_a],
            group_representatives[group_b],
        ]
        score = (
            sum(
                int(row["hololens_sync_pv_video_available"])
                for row in representatives
            ),
            sum(int(row["is_spatial_enabled"]) for row in representatives),
            sum(int(row["stream_count"]) for row in representatives),
            -sum(
                abs(float(row["duration_seconds"]) - 1800.0)
                for row in representatives
            ),
        )
        pair = (group_a, group_b)
        if (
            replacement_score is None
            or score > replacement_score
            or (score == replacement_score and pair < replacement_pair)
        ):
            replacement_score = score
            replacement_pair = pair
    assert replacement_pair is not None

    primary_by_person = {
        int(row["person_id"]): str(row["source_group_id"]) for row in primary
    }
    replacement = [
        selected_record(
            group_representatives[group],
            "REPLACEMENT",
            rank,
            replacement_for=primary_by_person[group[0]],
        )
        for rank, group in enumerate(replacement_pair, start=1)
    ]

    duration_values = [float(row["duration_seconds"]) for row in inventory]
    stream_coverage = {
        key: {
            "recording_count": count,
            "fraction_of_384": round(count / 384.0, 6),
        }
        for key, count in sorted(all_stream_keys.items())
    }

    inventory_evidence = {
        "schema_version": "av-trace.captaincook4d-recording-inventory/1.0",
        "task_id": 174,
        "created_at": TODAY,
        "source_files": [
            "data/source_recon/captaincook4d_access_v1/video_information.csv",
            "data/source_recon/captaincook4d_access_v1/download_links.json",
        ],
        "recording_count": len(inventory),
        "records": inventory,
    }
    inventory_path = DERIVED / "recording_stream_inventory_v1.json"
    write_json(inventory_path, inventory_evidence)

    groups_evidence = {
        "schema_version": "av-trace.captaincook4d-source-groups/1.0",
        "task_id": 174,
        "created_at": TODAY,
        "grouping_rule": (
            "One group per exact person_id x environment_id; every recording, "
            "device view, resolution, raw/synchronized sensor stream, annotation, "
            "clip, frame, and future derivative from those recordings remains "
            "co-grouped. A person-level supergroup is also recorded because the "
            "same person appears across environments."
        ),
        "source_group_count": len(source_groups),
        "eligible_source_group_count": sum(
            int(group["eligible_recording_count"] > 0) for group in source_groups
        ),
        "source_groups": source_groups,
    }
    groups_path = DERIVED / "source_group_inventory_v1.json"
    write_json(groups_path, groups_evidence)

    selection_evidence = {
        "schema_version": "av-trace.captaincook4d-selection/1.0",
        "task_id": 174,
        "created_at": TODAY,
        "status": "CANDIDATE_POOL_FROZEN_ACCESS_NOT_PROVEN",
        "eligibility": {
            "duration_seconds_inclusive": [MIN_SECONDS, MAX_SECONDS],
            "gopro_360p_url_required": True,
            "hololens_sync_pv_preferred": True,
            "microphone_preferred_but_not_enumerated": True,
        },
        "within_group_representative_rule": [
            "Prefer an official hololens_sync_pv_video URL.",
            "Prefer is_spatial_enabled=true.",
            "Maximize the count of official stream URL keys.",
            "Minimize absolute duration distance from 1800 seconds.",
            "Break ties by numeric recording_id ascending.",
        ],
        "primary_group_rule": [
            "Choose exactly one source group for each person_id 1 through 8.",
            "Lexicographically maximize HoloLens PV representatives, spatial-enabled representatives, distinct environment count, and total stream count.",
            "Then minimize total absolute duration distance from 1800 seconds and break ties by source_group_id.",
        ],
        "replacement_rule": [
            "Use non-primary eligible groups with distinct replacement person and environment IDs.",
            "Prefer HoloLens PV, spatial enablement, total stream coverage, and duration nearest 1800 seconds.",
            "Each replacement substitutes for the selected group of the same person; it is not an extra simultaneously active source group.",
        ],
        "primary": primary,
        "replacement": replacement,
    }
    selection_path = DERIVED / "selection_v1.json"
    write_json(selection_path, selection_evidence)

    network_stop = {
        "schema_version": "av-trace.network-stop-record/1.0",
        "task_id": 174,
        "created_at": TODAY,
        "user_stop_instruction_observed": True,
        "requests_started_after_stop": 0,
        "active_targeted_network_clients_after_stop_audit": 0,
        "required_proxy": "https://proxy.example.invalid:3128",
        "completed_media_head_requests": 1,
        "completed_media_range_requests": 0,
        "completed_media_get_requests": 0,
        "persisted_media_payload_bytes": 0,
        "completed_probe": {
            "recording_id": "15_5",
            "stream": "gopro_360p",
            "method": "HEAD",
            "follow_redirects": True,
            "http_status": 404,
            "content_type": "text/html; charset=UTF-8",
            "content_length": None,
            "accept_ranges": None,
            "num_redirects": 0,
            "size_download": 0,
            "mp4_atoms_parsed": False,
            "exact_bytes_established": False,
            "evidence_headers": (
                "data/source_recon/captaincook4d_access_v1/"
                "probe_test_15_5_gopro360.headers"
            ),
            "evidence_metrics": (
                "data/source_recon/captaincook4d_access_v1/"
                "probe_test_15_5_gopro360.metrics"
            ),
        },
        "aborted_official_source_fetch_batch": {
            "status": "ABORTED_BY_USER_STOP",
            "retained_bodies": 0,
            "retained_bytes": 0,
        },
    }
    network_path = DERIVED / "network_stop_record.json"
    write_json(network_path, network_stop)

    selected_ids = {
        str(row["representative_recording_id"]) for row in primary + replacement
    }
    selected_inventory = [by_id[recording_id] for recording_id in sorted(
        selected_ids, key=natural_recording_id
    )]

    registry = {
        "schema_version": "av-trace.captaincook4d-access-registry/1.0",
        "task_id": 174,
        "registry_id": "av-trace-captaincook4d-access-preflight-v1-20261002",
        "created_at": TODAY,
        "decision_token": DECISION,
        "scope": "OFFICIAL_CAPTAINCOOK4D_METADATA_AND_BOUNDED_ACCESS_PREFLIGHT_ONLY",
        "decision_summary": (
            "Official metadata closes the 384-recording inventory, duration and "
            "person/environment grouping, stream-key coverage, dataset-level "
            "Apache-2.0 claim, and an exact 8+2 candidate pool. It does not close "
            "media access or native audio: the only completed official Box HEAD "
            "probe returned HTTP 404, no range bytes or MP4 atoms were obtained, "
            "and the exact 700705-byte link manifest contains no microphone key."
        ),
        "release_and_provenance": {
            "official_release_statement": "Dataset version 1.0 released December 2023",
            "official_project_repository": "CaptainCook4D/captain-cook",
            "official_downloader_repository": "CaptainCook4D/downloader",
            "official_annotations_repository": "CaptainCook4D/annotations",
            "downloader_tree_sha": "cf248fe2139fc6e37f9737141ec719948fbd1747",
            "annotations_tree_sha": "a8a920a3293c4db27099a20ddbe3a3a9be1283e3",
            "download_links_blob_sha": "6aca4c4080b31dc0fdd0c800635db558d1952f58",
            "video_information_blob_sha": "9cbbcf0fd914536fe062e06d3cfb935081e693cd",
        },
        "dataset_statistics": {
            "recording_count": len(inventory),
            "person_ids": sorted({int(row["person_id"]) for row in inventory}),
            "person_count": len({int(row["person_id"]) for row in inventory}),
            "environment_ids": sorted(
                {int(row["environment_id"]) for row in inventory}
            ),
            "environment_count": len(
                {int(row["environment_id"]) for row in inventory}
            ),
            "source_group_count_person_x_environment": len(source_groups),
            "duration_seconds_total": round(sum(duration_values), 2),
            "duration_hours_total": round(sum(duration_values) / 3600.0, 6),
            "duration_seconds_min": min(duration_values),
            "duration_seconds_median": round(statistics.median(duration_values), 3),
            "duration_seconds_max": max(duration_values),
            "recordings_20_to_90_minutes_inclusive": sum(
                int(row["eligible_duration_20_to_90_minutes"])
                for row in inventory
            ),
            "eligible_source_groups": sum(
                int(group["eligible_recording_count"] > 0)
                for group in source_groups
            ),
        },
        "manifest_access": {
            "download_links_file_bytes": links_path.stat().st_size,
            "recording_rows_joined": len(inventory),
            "official_url_count": url_count,
            "unique_official_url_count": len(unique_urls),
            "official_url_domains": dict(sorted(domains.items())),
            "all_links_official_box_domain": set(domains) == {"utdallas.box.com"},
            "stream_coverage": stream_coverage,
            "is_hololens_enabled_recordings": sum(
                int(row["is_hololens_enabled"]) for row in inventory
            ),
            "is_spatial_enabled_recordings": sum(
                int(row["is_spatial_enabled"]) for row in inventory
            ),
            "microphone_manifest_key_recordings": sum(
                int(row["microphone_manifest_key_available"]) for row in inventory
            ),
            "readme_microphone_statement": (
                "The retained official downloader README describes raw `mc` "
                "microphone capture in PKL form, but no `mc` or microphone URL "
                "key occurs in the exact retained download_links.json."
            ),
        },
        "source_group_policy": {
            "primary_group_key": "person_id x environment_id",
            "person_level_supergroup_required_for_identity_safe_splits": True,
            "policy": groups_evidence["grouping_rule"],
            "source_groups": source_groups,
        },
        "candidate_pool": selection_evidence,
        "selected_recording_inventory": selected_inventory,
        "access_probe": network_stop,
        "native_audio": {
            "status": "NOT_ESTABLISHED",
            "gopro_mp4_audio": "UNRESOLVED_NO_CONTAINER_BYTES",
            "hololens_pv_mp4_audio": "UNRESOLVED_NO_CONTAINER_BYTES",
            "hololens_raw_microphone": (
                "DESCRIBED_IN_DOWNLOADER_README_BUT_NOT_ENUMERATED_IN_LINK_MANIFEST"
            ),
            "audio_codec": None,
            "audio_channels": None,
            "audio_sample_rate_hz": None,
            "audio_duration_seconds": None,
            "video_codec": None,
            "container_duration_seconds": None,
            "mp4_atoms_parsed": False,
        },
        "license_use_privacy_irb": {
            "dataset_license_statement": "Apache License 2.0",
            "downloader_repository_license": "Apache-2.0",
            "annotations_repository_license": "MIT",
            "irb_statement": (
                "Official project README says the dataset was approved by the "
                "University of Florida IRB."
            ),
            "consent_statement": (
                "Official project README says all participants provided written consent."
            ),
            "operative_irb_document_archived": False,
            "operative_consent_document_archived": False,
            "privacy_withdrawal_retention_terms_archived": False,
            "copyright_redistribution_boundary": (
                "The official dataset statement names Apache-2.0 and the "
                "downloader carries Apache-2.0; preserve license/notice, mark "
                "modified files, and retain attribution/NOTICE requirements "
                "where applicable. The annotation repository separately carries MIT."
            ),
            "noncopyright_boundary": (
                "No retained evidence establishes that Apache-2.0 grants privacy, "
                "publicity, biometric, voice, location, or participant-consent "
                "rights. Raw media and identity-bearing derivatives therefore "
                "remain restricted pending review of the linked IRB and consent text."
            ),
            "redistribution_status": "NOT_AUTHORIZED_BY_THIS_PREFLIGHT",
        },
        "semantic_annotation_leakage": {
            "risk": "HIGH",
            "sealed_during_selection": True,
            "not_opened_for_candidate_selection": [
                "step_annotations",
                "complete_step_annotations",
                "error_annotations",
                "activity_step_description",
                "step_idx_description",
                "recording_id_step_idx",
                "task_graphs",
                "person/environment/recipe/recording benchmark splits",
            ],
            "reason": (
                "These files expose recipe identity, steps, temporal boundaries, "
                "fine-grained actions, induced-error status/category, task order, "
                "and benchmark split membership. Selection used only IDs, person/"
                "environment fields, duration, and transport stream availability."
            ),
        },
        "authorization": {
            "metadata_use_for_planning": "READY",
            "candidate_pool_definition": "READY",
            "media_acquisition": "REPAIR_REQUIRED",
            "native_audio_dependent_use": "REPAIR_REQUIRED",
            "internal_processing": "NOT_AUTHORIZED_BY_TASK174",
            "annotation_use": "NOT_AUTHORIZED_BY_TASK174",
            "raw_media_redistribution": "NOT_AUTHORIZED_BY_TASK174",
            "clip_frame_audio_redistribution": "NOT_AUTHORIZED_BY_TASK174",
            "feature_embedding_redistribution": "NOT_AUTHORIZED_BY_TASK174",
        },
        "repair_requirements": [
            "Obtain a refreshed, commit-pinned official CaptainCook4D Box link manifest or corrected official downloader revision.",
            "Run one bounded Range probe for each selected GoPro 360p and preferred HoloLens PV representative; record status, redirects, Content-Range, total bytes, and validators.",
            "Parse bounded MP4 metadata atoms or use a bounded official technical manifest to establish video/audio codec, channels, sample rate, and stream durations.",
            "Resolve the downloader README versus download_links.json microphone-key mismatch.",
            "Archive and review the linked official IRB approval and participant consent text before identity-bearing media acquisition or redistribution.",
        ],
        "evidence_paths": {
            "recording_inventory": str(inventory_path.relative_to(ROOT)),
            "source_group_inventory": str(groups_path.relative_to(ROOT)),
            "selection": str(selection_path.relative_to(ROOT)),
            "network_stop_record": str(network_path.relative_to(ROOT)),
            "evidence_manifest": (
                "data/source_recon/captaincook4d_access_v1/evidence_manifest.json"
            ),
        },
        "all_recordings": [
            {
                key: value
                for key, value in row.items()
                if key != "official_stream_urls"
            }
            for row in inventory
        ],
    }
    write_json(REGISTRY_PATH, registry)

    evidence_inputs = [
        "annotations_LICENSE",
        "annotations_tree.json",
        "download_links.json",
        "downloader_LICENSE",
        "downloader_README.md",
        "downloader_repo.json",
        "downloader_tree.json",
        "main_README.md",
        "probe_test_15_5_gopro360.headers",
        "probe_test_15_5_gopro360.metrics",
        "video_information.csv",
    ]
    evidence_outputs = [
        "derived/network_stop_record.json",
        "derived/recording_stream_inventory_v1.json",
        "derived/selection_v1.json",
        "derived/source_group_inventory_v1.json",
    ]
    manifest = {
        "schema_version": "av-trace.evidence-manifest/1.0",
        "task_id": 174,
        "created_at": TODAY,
        "decision_token": DECISION,
        "network_stopped": True,
        "official_source_policy": (
            "Only retained official CaptainCook4D GitHub material and official "
            "utdallas.box.com links were used. No mirror evidence was used."
        ),
        "files": [],
        "registry": {
            "path": str(REGISTRY_PATH.relative_to(ROOT)),
            "bytes": REGISTRY_PATH.stat().st_size,
            "sha256": sha256(REGISTRY_PATH),
        },
    }
    for relative in evidence_inputs + evidence_outputs:
        path = RECON / relative
        manifest["files"].append(
            {
                "path": str(path.relative_to(ROOT)),
                "role": "retained_official_or_probe" if relative in evidence_inputs else "derived",
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    write_json(RECON / "evidence_manifest.json", manifest)


if __name__ == "__main__":
    main()
