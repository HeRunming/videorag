#!/usr/bin/env python3
"""Build an offline, exact-object VES discovery stream-preflight plan.

This tool deliberately does not modify Task 70's duration-qualified candidate
pool or its blocked long-stream plan.  It reads the same pinned metadata
snapshots, joins exact MP4 identities, and selects ten objects for a later
bounded ISO-BMFF container preflight.

Evidence endpoints are used only as a deterministic ranking signal.  They are
never copied into an actual-duration field and never make an object a
duration-qualified candidate.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    from tools import ves_long_candidate_recon as recon
except ModuleNotFoundError:  # Support direct ``python tools/...py`` execution.
    import ves_long_candidate_recon as recon  # type: ignore[no-redef]


SCHEMA_VERSION = "1.0.0"
PLAN_REL = Path(
    "data/acquisition_preflight/ves_discovery_stream_preflight_plan.json"
)
DISCOVERY_OBJECT_COUNT = 10
UNRESOLVED = "UNRESOLVED_PENDING_BOUNDED_CONTAINER_PREFLIGHT"
REQUESTED_ACTION = "BOUNDED_ISO_BMFF_STREAM_CONTAINER_PREFLIGHT_ONLY"
NOT_DURATION_QUALIFIED = (
    "NOT_DURATION_QUALIFIED_PENDING_BOUNDED_CONTAINER_PREFLIGHT"
)
REQUIRED_DATASETS = frozenset({"youtube", "ego4d"})
REQUIRED_TASKS = frozenset({"temporal_ordering", "event_counting"})
REQUIRED_TASK_PROFILES = frozenset(
    {
        ("event_counting",),
        ("temporal_ordering",),
        ("event_counting", "temporal_ordering"),
    }
)


def _rank_key(video: recon.JoinedVideo) -> tuple[Any, ...]:
    """Prefer evidence extent, then evidence coverage; size is only a tie-break."""
    return (
        -video.max_evidence_end_s,
        -video.evidence_interval_count,
        -len(video.tasks),
        video.object_identity.size,
        video.video_id,
    )


def _best(
    pool: Sequence[recon.JoinedVideo],
    selected: Sequence[recon.JoinedVideo],
) -> recon.JoinedVideo:
    selected_paths = {item.video_path for item in selected}
    remaining = [item for item in pool if item.video_path not in selected_paths]
    if not remaining:
        raise recon.ReconError("DISCOVERY_SELECTION_POOL_EXHAUSTED")
    return min(remaining, key=_rank_key)


def select_discovery_objects(
    joined: Sequence[recon.JoinedVideo],
    *,
    count: int = DISCOVERY_OBJECT_COUNT,
) -> list[recon.JoinedVideo]:
    """Select exact duration-unresolved objects under the discovery policy."""
    if count != DISCOVERY_OBJECT_COUNT:
        raise recon.ReconError(
            "DISCOVERY_OBJECT_COUNT_MUST_BE_EXACTLY_TEN", value=count
        )
    if len(joined) < count:
        raise recon.ReconError(
            "INSUFFICIENT_DISCOVERY_OBJECTS", required=count, observed=len(joined)
        )
    if any(item.duration_s is not None for item in joined):
        raise recon.ReconError(
            "DISCOVERY_SELECTION_REQUIRES_UNRESOLVED_METADATA_DURATION"
        )

    datasets = {item.dataset for item in joined}
    if not REQUIRED_DATASETS.issubset(datasets):
        raise recon.ReconError(
            "REQUIRED_DISCOVERY_DATASET_DIVERSITY_UNAVAILABLE",
            required=sorted(REQUIRED_DATASETS),
            observed=sorted(datasets),
        )
    task_profiles = {item.tasks for item in joined}
    if not REQUIRED_TASK_PROFILES.issubset(task_profiles):
        raise recon.ReconError(
            "REQUIRED_DISCOVERY_TASK_PROFILE_DIVERSITY_UNAVAILABLE",
            required=[list(item) for item in sorted(REQUIRED_TASK_PROFILES)],
            observed=[list(item) for item in sorted(task_profiles)],
        )

    selected: list[recon.JoinedVideo] = []

    # Seed both metadata sources.
    for dataset in sorted(REQUIRED_DATASETS):
        selected.append(
            _best([item for item in joined if item.dataset == dataset], selected)
        )

    # Include event-only, ordering-only, and dual-task evidence where feasible.
    for profile in sorted(REQUIRED_TASK_PROFILES):
        if profile not in {item.tasks for item in selected}:
            selected.append(
                _best([item for item in joined if item.tasks == profile], selected)
            )

    # Cover every observed modality-role hypothesis before adding topic breadth.
    all_roles = sorted({recon.modality_hypothesis(item.text) for item in joined})
    for role in all_roles:
        if role not in {
            recon.modality_hypothesis(item.text) for item in selected
        }:
            selected.append(
                _best(
                    [
                        item
                        for item in joined
                        if recon.modality_hypothesis(item.text) == role
                    ],
                    selected,
                )
            )

    # Spend the remaining slots on unseen topics, always taking the greatest
    # evidence extent available for that diversity gain.
    while len(selected) < count:
        selected_topics = {
            recon.topic_hypothesis(item.text) for item in selected
        }
        unseen_topic_pool = [
            item
            for item in joined
            if item not in selected
            and recon.topic_hypothesis(item.text) not in selected_topics
        ]
        selected.append(
            _best(unseen_topic_pool if unseen_topic_pool else joined, selected)
        )

    ranked = sorted(selected, key=_rank_key)
    validate_selection(ranked)
    return ranked


def validate_selection(selected: Sequence[recon.JoinedVideo]) -> None:
    if len(selected) != DISCOVERY_OBJECT_COUNT:
        raise recon.ReconError(
            "DISCOVERY_OBJECT_COUNT_INVALID", observed=len(selected)
        )
    paths = [item.video_path for item in selected]
    blobs = [item.object_identity.blob_id for item in selected]
    hashes = [item.object_identity.sha256 for item in selected]
    if len(paths) != len(set(paths)):
        raise recon.ReconError("DUPLICATE_DISCOVERY_PATH")
    if len(blobs) != len(set(blobs)):
        raise recon.ReconError("DUPLICATE_DISCOVERY_BLOB_ID")
    if len(hashes) != len(set(hashes)):
        raise recon.ReconError("DUPLICATE_DISCOVERY_SHA256")
    if any(item.duration_s is not None for item in selected):
        raise recon.ReconError("DISCOVERY_OBJECT_HAS_METADATA_DURATION")
    if {item.dataset for item in selected} != REQUIRED_DATASETS:
        raise recon.ReconError("DISCOVERY_DATASET_DIVERSITY_NOT_MET")
    if not REQUIRED_TASKS.issubset(
        {task for item in selected for task in item.tasks}
    ):
        raise recon.ReconError("DISCOVERY_TASK_DIVERSITY_NOT_MET")
    if not REQUIRED_TASK_PROFILES.issubset({item.tasks for item in selected}):
        raise recon.ReconError("DISCOVERY_TASK_PROFILE_DIVERSITY_NOT_MET")
    if len({recon.topic_hypothesis(item.text) for item in selected}) < 6:
        raise recon.ReconError("DISCOVERY_TOPIC_DIVERSITY_NOT_MET")
    if len({recon.modality_hypothesis(item.text) for item in selected}) < 3:
        raise recon.ReconError("DISCOVERY_MODALITY_DIVERSITY_NOT_MET")


def evidence_rows(
    item: recon.JoinedVideo,
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for ordinal in item.row_ordinals:
        row = rows[ordinal]
        intervals = row["evidence"]
        result.append(
            {
                "parquet_row_ordinal_zero_based": ordinal,
                "row_id": row["id"],
                "source_question_id": row["source_question_id"],
                "dataset": row["dataset"],
                "task": row["task"],
                "evidence_interval_count": len(intervals),
                "max_evidence_end_s": max(
                    (float(interval["end_sec"]) for interval in intervals),
                    default=0.0,
                ),
                "evidence_intervals": [
                    {
                        "evidence_id": interval["id"],
                        "start_sec": float(interval["start_sec"]),
                        "end_sec": float(interval["end_sec"]),
                        "description": interval["description"],
                    }
                    for interval in intervals
                ],
            }
        )
    return result


def build_plan(
    selected: Sequence[recon.JoinedVideo],
    *,
    parquet_identity: recon.SnapshotIdentity,
    api_identity: recon.SnapshotIdentity,
    rows: Sequence[Mapping[str, Any]],
    joined_count: int,
) -> dict[str, Any]:
    validate_selection(selected)
    objects = []
    for rank, item in enumerate(selected, start=1):
        objects.append(
            {
                "rank": rank,
                "discovery_id": f"ves-discovery-{rank:02d}",
                "repo_id": recon.REPO_ID,
                "revision": recon.REVISION,
                "path": item.video_path,
                "size_bytes": item.object_identity.size,
                "blob_id": item.object_identity.blob_id,
                "hash_algorithm": "sha256",
                "sha256": item.object_identity.sha256,
                "dataset": item.dataset,
                "tasks": list(item.tasks),
                "topic_hypothesis": (
                    f"UNVERIFIED_{recon.topic_hypothesis(item.text).upper()}"
                    "_HYPOTHESIS"
                ),
                "modality_role_hypothesis": recon.modality_hypothesis(item.text),
                "metadata_evidence_rows": evidence_rows(item, rows),
                "evidence_interval_count": item.evidence_interval_count,
                "max_evidence_endpoint_s": item.max_evidence_end_s,
                "ranking_provenance": {
                    "primary_signal": "MAX_EVIDENCE_ENDPOINT_DESCENDING",
                    "evidence_extent_interpretation": (
                        "RANKING_SIGNAL_ONLY_RAISES_BUT_DOES_NOT_PROVE_"
                        "PROBABILITY_OF_DURATION_AT_LEAST_1200_SECONDS"
                    ),
                    "diversity_signals": [
                        "dataset",
                        "task_profile",
                        "topic_hypothesis",
                        "modality_role_hypothesis",
                    ],
                    "object_size_role": "DETERMINISTIC_TIE_BREAK_ONLY",
                },
                "actual_duration": UNRESOLVED,
                "audio_track": UNRESOLVED,
                "video_track": UNRESOLVED,
                "evidence_extent_is_duration": False,
                "duration_qualification_status": NOT_DURATION_QUALIFIED,
                "requested_action": REQUESTED_ACTION,
                "full_acquisition_authorized": False,
                "processing_authorized": False,
                "annotation_authorized": False,
                "release_authorized": False,
                "rights_status": "UNKNOWN_HOLD",
            }
        )

    plan = {
        "schema_version": SCHEMA_VERSION,
        "as_of_date": recon.AS_OF_DATE,
        "status": "READY_FOR_BOUNDED_DISCOVERY_STREAM_PREFLIGHT",
        "purpose": (
            "Closed exact-object plan for bounded ISO-BMFF container discovery "
            "only. The later preflight establishes actual duration and declared "
            "audio/video tracks."
        ),
        "repository": {"repo_id": recon.REPO_ID, "revision": recon.REVISION},
        "metadata_snapshots": {
            "parquet": asdict(parquet_identity),
            "repository_api": asdict(api_identity),
        },
        "task_70_duration_qualified_pool": {
            "status": "EMPTY_FAIL_CLOSED",
            "candidate_count": 0,
            "reason": "NO_ITEM_LEVEL_WHOLE_VIDEO_DURATION_COLUMN",
            "unchanged_by_this_plan": True,
        },
        "discovery_scope": {
            "selected_object_count": DISCOVERY_OBJECT_COUNT,
            "joined_exact_mp4_object_count": joined_count,
            "selected_objects_are_duration_qualified_candidates": False,
            "evidence_extent_is_duration": False,
            "ranking_policy": (
                "Prefer greater maximum evidence endpoint while enforcing "
                "dataset, task-profile, topic, and modality-hypothesis breadth. "
                "Evidence extent is never duration evidence; object size is "
                "only a deterministic tie-break."
            ),
        },
        "authorization": {
            "authorized_actions": [
                "BOUNDED_ISO_BMFF_RANGE_PREFLIGHT_FOR_THE_TEN_EXACT_OBJECTS_ONLY"
            ],
            "authorized_for_bounded_stream_container_preflight": [
                item["discovery_id"] for item in objects
            ],
            "authorized_for_full_acquisition": [],
            "authorized_for_full_media_download": [],
            "authorized_for_processing": [],
            "authorized_for_annotation": [],
            "authorized_for_release": [],
        },
        "constraints": {
            "closed_exact_object_list": True,
            "wildcards_allowed": False,
            "network_access_performed_by_this_task": False,
            "media_body_or_range_request_performed_by_this_task": False,
            "full_object_response_permitted_in_later_preflight": False,
            "full_object_range_permitted_in_later_preflight": False,
            "rights_cleared": False,
        },
        "discovery_objects": objects,
    }
    validate_plan(plan)
    return plan


def validate_plan(plan: Mapping[str, Any]) -> None:
    serialized = json.dumps(plan, sort_keys=True)
    if "*" in serialized:
        raise recon.ReconError("WILDCARD_PRESENT_IN_DISCOVERY_PLAN")
    objects = plan.get("discovery_objects")
    if not isinstance(objects, list) or len(objects) != DISCOVERY_OBJECT_COUNT:
        raise recon.ReconError("DISCOVERY_PLAN_MUST_HAVE_EXACTLY_TEN_OBJECTS")
    authorization = plan.get("authorization")
    if not isinstance(authorization, Mapping):
        raise recon.ReconError("DISCOVERY_AUTHORIZATION_ABSENT")
    if authorization.get("authorized_actions") != [
        "BOUNDED_ISO_BMFF_RANGE_PREFLIGHT_FOR_THE_TEN_EXACT_OBJECTS_ONLY"
    ]:
        raise recon.ReconError("DISCOVERY_ACTION_AUTHORIZATION_INVALID")
    for key in (
        "authorized_for_full_acquisition",
        "authorized_for_full_media_download",
        "authorized_for_processing",
        "authorized_for_annotation",
        "authorized_for_release",
    ):
        if authorization.get(key) != []:
            raise recon.ReconError("ACQUISITION_AUTHORIZATION_MUST_REMAIN_EMPTY")
    authorized_ids = authorization.get(
        "authorized_for_bounded_stream_container_preflight"
    )
    if authorized_ids != [item.get("discovery_id") for item in objects]:
        raise recon.ReconError("BOUNDED_PREFLIGHT_ALLOWLIST_MISMATCH")

    paths: set[str] = set()
    blobs: set[str] = set()
    hashes: set[str] = set()
    for item in objects:
        if item.get("repo_id") != recon.REPO_ID:
            raise recon.ReconError("DISCOVERY_REPOSITORY_CONFLICT")
        if item.get("revision") != recon.REVISION:
            raise recon.ReconError("DISCOVERY_REVISION_CONFLICT")
        path = item.get("path")
        blob = item.get("blob_id")
        digest = item.get("sha256")
        if not isinstance(path, str) or not path.endswith(".mp4"):
            raise recon.ReconError("DISCOVERY_OBJECT_PATH_INVALID")
        if not recon.HEX40_RE.fullmatch(str(blob)):
            raise recon.ReconError("DISCOVERY_OBJECT_BLOB_ID_INVALID")
        if not recon.HEX64_RE.fullmatch(str(digest)):
            raise recon.ReconError("DISCOVERY_OBJECT_SHA256_INVALID")
        if path in paths or blob in blobs or digest in hashes:
            raise recon.ReconError("DISCOVERY_OBJECT_IDENTITY_DUPLICATED")
        paths.add(path)
        blobs.add(str(blob))
        hashes.add(str(digest))
        if (
            item.get("actual_duration") != UNRESOLVED
            or item.get("audio_track") != UNRESOLVED
            or item.get("video_track") != UNRESOLVED
            or item.get("evidence_extent_is_duration") is not False
            or item.get("duration_qualification_status")
            != NOT_DURATION_QUALIFIED
        ):
            raise recon.ReconError("DURATION_OR_TRACK_CONFLATION")
        if item.get("requested_action") != REQUESTED_ACTION:
            raise recon.ReconError("DISCOVERY_REQUESTED_ACTION_INVALID")
        if any(
            item.get(key) is not False
            for key in (
                "full_acquisition_authorized",
                "processing_authorized",
                "annotation_authorized",
                "release_authorized",
            )
        ):
            raise recon.ReconError("DISCOVERY_OBJECT_AUTHORITY_TOO_BROAD")
        if not item.get("metadata_evidence_rows"):
            raise recon.ReconError("DISCOVERY_EVIDENCE_ROWS_ABSENT")
        if not isinstance(item.get("max_evidence_endpoint_s"), (int, float)):
            raise recon.ReconError("DISCOVERY_EVIDENCE_EXTENT_ABSENT")


def run(
    repo_root: Path,
    *,
    parquet_path: Path | None = None,
    api_path: Path | None = None,
    plan_path: Path | None = None,
    expected_parquet_size: int = recon.EXPECTED_PARQUET_SIZE,
    expected_parquet_sha256: str = recon.EXPECTED_PARQUET_SHA256,
    expected_api_size: int = recon.EXPECTED_API_SIZE,
    expected_api_sha256: str = recon.EXPECTED_API_SHA256,
) -> dict[str, Any]:
    parquet_path = parquet_path or repo_root / recon.PARQUET_REL
    api_path = api_path or repo_root / recon.API_REL
    plan_path = plan_path or repo_root / PLAN_REL

    parquet_identity = recon.validate_snapshot(
        parquet_path,
        expected_size=expected_parquet_size,
        expected_sha256=expected_parquet_sha256,
    )
    api_identity = recon.validate_snapshot(
        api_path,
        expected_size=expected_api_size,
        expected_sha256=expected_api_sha256,
    )
    schema, rows = recon.read_parquet(parquet_path)
    api = recon.load_api_snapshot(api_path)
    parquet_identity = recon.validate_parquet_sibling(api, parquet_identity)
    objects = recon.build_object_index(api)
    joined, duration_column = recon.join_rows(
        schema, rows, objects, require_duration=False
    )
    if duration_column is not None:
        raise recon.ReconError(
            "UNEXPECTED_ITEM_DURATION_COLUMN_IN_PINNED_DISCOVERY_SNAPSHOT",
            column=duration_column,
        )
    if len(objects) != len(joined):
        raise recon.ReconError(
            "METADATA_OBJECT_CARDINALITY_CONFLICT",
            metadata_unique_videos=len(joined),
            sibling_mp4_objects=len(objects),
        )

    selected = select_discovery_objects(joined)
    plan = build_plan(
        selected,
        parquet_identity=parquet_identity,
        api_identity=api_identity,
        rows=rows,
        joined_count=len(joined),
    )
    recon.write_json(plan_path, plan)
    return {
        "status": plan["status"],
        "plan_path": plan_path.as_posix(),
        "selected_object_count": len(selected),
        "datasets": dict(sorted(Counter(item.dataset for item in selected).items())),
        "task_profiles": {
            "|".join(profile): count
            for profile, count in sorted(
                Counter(item.tasks for item in selected).items()
            )
        },
        "topic_hypotheses": sorted(
            {recon.topic_hypothesis(item.text) for item in selected}
        ),
        "modality_role_hypotheses": sorted(
            {recon.modality_hypothesis(item.text) for item in selected}
        ),
        "maximum_selected_evidence_endpoint_s": max(
            item.max_evidence_end_s for item in selected
        ),
        "duration_qualified_candidate_count": 0,
        "network_access_performed": False,
        "media_download_performed": False,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--plan-path", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = run(
            args.repo_root.resolve(),
            plan_path=args.plan_path,
        )
    except recon.ReconError as exc:
        print(json.dumps(exc.diagnostic(), sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
