#!/usr/bin/env python3
"""Build the offline, exact-object VES wave-2 stream-preflight plan.

Wave 2 uses the ten observed wave-1 container durations only to derive
bytes-per-second calibration ratios.  For each still-untested object, the
ranking counts how many observed ratios would place that object's byte size
inside the 1,200--5,400 second gate.  This is a sampling heuristic, not a
duration estimate: no untested object receives an inferred duration.

The selector excludes every wave-1 object, chooses exactly 18 YouTube and two
Ego4D objects, and then validates source, topic, and metadata-modality breadth.
It reads only pinned local snapshots and performs no network or media access.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    from tools import ves_discovery_preflight_plan as wave1_plan_tool
    from tools import ves_long_candidate_recon as recon
except ModuleNotFoundError:  # Support direct ``python tools/...py`` execution.
    import ves_discovery_preflight_plan as wave1_plan_tool  # type: ignore[no-redef]
    import ves_long_candidate_recon as recon  # type: ignore[no-redef]


SCHEMA_VERSION = "1.0.0"
PLAN_REL = Path(
    "data/acquisition_preflight/ves_wave2_stream_preflight_plan.json"
)
WAVE1_PLAN_REL = Path(
    "data/acquisition_preflight/ves_discovery_stream_preflight_plan.json"
)
WAVE1_RESULT_REL = Path(
    "data/acquisition_preflight/ves_discovery_stream_preflight_result.json"
)
EXPECTED_WAVE1_PLAN_SIZE = 54_553
EXPECTED_WAVE1_PLAN_SHA256 = (
    "26b91859e1e50a925afbca7d4f45a497b55a84528c9aa5022c3edde8234d701e"
)
EXPECTED_WAVE1_RESULT_SIZE = 103_336
EXPECTED_WAVE1_RESULT_SHA256 = (
    "b4ce2a3231cf731a53acefe0ad1b059424d28fa796a5e62045b44fb1870bb953"
)

WAVE2_OBJECT_COUNT = 20
YOUTUBE_OBJECT_COUNT = 18
EGO4D_OBJECT_COUNT = 2
MIN_YOUTUBE_OBJECT_COUNT = 15
MIN_TOPIC_COUNT = 6
MIN_DURATION_S = 1_200
MAX_DURATION_S = 5_400
UNRESOLVED = "UNRESOLVED_PENDING_BOUNDED_CONTAINER_PREFLIGHT"
NOT_QUALIFIED = "NOT_QUALIFIED_PENDING_BOUNDED_CONTAINER_PREFLIGHT"
REQUESTED_ACTION = "BOUNDED_ISO_BMFF_STREAM_CONTAINER_PREFLIGHT_ONLY"
AUTHORIZED_ACTION = (
    "BOUNDED_ISO_BMFF_RANGE_PREFLIGHT_FOR_THE_TWENTY_EXACT_OBJECTS_ONLY"
)


@dataclass(frozen=True)
class CalibrationObservation:
    wave1_id: str
    dataset: str
    path: str
    size_bytes: int
    duration_seconds: Fraction
    video_track_count: int
    audio_track_count: int
    av_timeline_relation: str
    decision: str

    @property
    def bytes_per_second(self) -> Fraction:
        return Fraction(self.size_bytes, 1) / self.duration_seconds

    def gate_supports_size(self, size_bytes: int) -> bool:
        ratio = self.bytes_per_second
        return MIN_DURATION_S * ratio <= size_bytes <= MAX_DURATION_S * ratio

    def as_plan_dict(self) -> dict[str, Any]:
        return {
            "wave1_id": self.wave1_id,
            "dataset": self.dataset,
            "path": self.path,
            "size_bytes": self.size_bytes,
            "observed_container_duration_seconds": float(
                self.duration_seconds
            ),
            "observed_bytes_per_second_ratio": round(
                float(self.bytes_per_second), 6
            ),
            "video_track_count": self.video_track_count,
            "audio_track_count": self.audio_track_count,
            "av_timeline_relation": self.av_timeline_relation,
            "decision": self.decision,
        }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_local_artifact(
    path: Path, *, expected_size: int, expected_sha256: str
) -> dict[str, Any]:
    observed_size = path.stat().st_size
    if observed_size != expected_size:
        raise recon.ReconError(
            "WAVE1_ARTIFACT_SIZE_MISMATCH",
            path=path.as_posix(),
            expected=expected_size,
            observed=observed_size,
        )
    observed_sha256 = _sha256_file(path)
    if observed_sha256 != expected_sha256:
        raise recon.ReconError(
            "WAVE1_ARTIFACT_SHA256_MISMATCH",
            path=path.as_posix(),
            expected=expected_sha256,
            observed=observed_sha256,
        )
    return {
        "path": path.as_posix(),
        "size": observed_size,
        "sha256": observed_sha256,
    }


def load_wave1_calibration(
    wave1_plan_path: Path,
    wave1_result_path: Path,
) -> tuple[
    list[CalibrationObservation],
    set[str],
    dict[str, Any],
    dict[str, Any],
]:
    """Load and cross-check the exact ten-object wave-1 calibration."""
    plan_identity = _validate_local_artifact(
        wave1_plan_path,
        expected_size=EXPECTED_WAVE1_PLAN_SIZE,
        expected_sha256=EXPECTED_WAVE1_PLAN_SHA256,
    )
    result_identity = _validate_local_artifact(
        wave1_result_path,
        expected_size=EXPECTED_WAVE1_RESULT_SIZE,
        expected_sha256=EXPECTED_WAVE1_RESULT_SHA256,
    )
    with wave1_plan_path.open(encoding="utf-8") as handle:
        wave1_plan = json.load(handle)
    wave1_plan_tool.validate_plan(wave1_plan)
    with wave1_result_path.open(encoding="utf-8") as handle:
        result = json.load(handle)

    planned = wave1_plan["discovery_objects"]
    observed = result.get("discovery_objects")
    if not isinstance(observed, list) or len(observed) != len(planned) != 0:
        raise recon.ReconError("WAVE1_RESULT_OBJECT_COUNT_INVALID")
    if len(planned) != wave1_plan_tool.DISCOVERY_OBJECT_COUNT:
        raise recon.ReconError("WAVE1_PLAN_OBJECT_COUNT_INVALID")

    calibration: list[CalibrationObservation] = []
    excluded_paths: set[str] = set()
    for source, item in zip(planned, observed, strict=True):
        identity = item.get("identity")
        metadata = item.get("metadata_provenance")
        if not isinstance(identity, Mapping) or not isinstance(metadata, Mapping):
            raise recon.ReconError("WAVE1_RESULT_PROVENANCE_ABSENT")
        expected_identity = {
            "candidate_id": source["discovery_id"],
            "repo_id": source["repo_id"],
            "revision": source["revision"],
            "path": source["path"],
            "size_bytes": source["size_bytes"],
            "hash_algorithm": source["hash_algorithm"],
            "hash": source["sha256"],
            "blob_id": source["blob_id"],
        }
        if identity != expected_identity:
            raise recon.ReconError(
                "WAVE1_RESULT_IDENTITY_MISMATCH",
                wave1_id=source["discovery_id"],
            )
        if (
            item.get("discovery_id") != source["discovery_id"]
            or metadata.get("dataset") != source["dataset"]
            or item.get("identity_match") is not True
        ):
            raise recon.ReconError("WAVE1_RESULT_MAPPING_MISMATCH")
        duration = item.get("duration_seconds")
        if (
            not isinstance(duration, (int, float))
            or isinstance(duration, bool)
            or duration <= 0
        ):
            raise recon.ReconError("WAVE1_DURATION_INVALID")
        video_tracks = item.get("video_track_count")
        audio_tracks = item.get("audio_track_count")
        if not isinstance(video_tracks, int) or not isinstance(audio_tracks, int):
            raise recon.ReconError("WAVE1_TRACK_COUNT_INVALID")
        calibration.append(
            CalibrationObservation(
                wave1_id=source["discovery_id"],
                dataset=source["dataset"],
                path=source["path"],
                size_bytes=source["size_bytes"],
                duration_seconds=Fraction(str(duration)),
                video_track_count=video_tracks,
                audio_track_count=audio_tracks,
                av_timeline_relation=str(item.get("av_timeline_relation")),
                decision=str(item.get("decision")),
            )
        )
        excluded_paths.add(source["path"])

    if len(excluded_paths) != wave1_plan_tool.DISCOVERY_OBJECT_COUNT:
        raise recon.ReconError("WAVE1_EXCLUSION_SET_NOT_UNIQUE")
    return calibration, excluded_paths, plan_identity, result_identity


def gate_supporting_observations(
    video: recon.JoinedVideo,
    calibration: Sequence[CalibrationObservation],
) -> tuple[str, ...]:
    return tuple(
        item.wave1_id
        for item in calibration
        if item.gate_supports_size(video.object_identity.size)
    )


def _rank_key(
    video: recon.JoinedVideo,
    calibration: Sequence[CalibrationObservation],
) -> tuple[Any, ...]:
    """Prefer calibration support, size, evidence extent, then stable coverage."""
    return (
        -len(gate_supporting_observations(video, calibration)),
        -video.object_identity.size,
        -video.max_evidence_end_s,
        -video.evidence_interval_count,
        -len(video.tasks),
        video.video_id,
    )


def select_wave2_objects(
    joined: Sequence[recon.JoinedVideo],
    calibration: Sequence[CalibrationObservation],
    excluded_paths: set[str],
) -> list[recon.JoinedVideo]:
    """Select exactly 18 YouTube and two Ego4D objects, excluding wave 1."""
    if len(calibration) != wave1_plan_tool.DISCOVERY_OBJECT_COUNT:
        raise recon.ReconError("WAVE1_CALIBRATION_COUNT_INVALID")
    if any(item.duration_s is not None for item in joined):
        raise recon.ReconError("WAVE2_REQUIRES_UNRESOLVED_METADATA_DURATION")
    remaining = [item for item in joined if item.video_path not in excluded_paths]
    if len(remaining) != len(joined) - len(excluded_paths):
        raise recon.ReconError("WAVE1_EXCLUSION_JOIN_CONFLICT")

    youtube = sorted(
        (item for item in remaining if item.dataset == "youtube"),
        key=lambda item: _rank_key(item, calibration),
    )
    ego4d = sorted(
        (item for item in remaining if item.dataset == "ego4d"),
        key=lambda item: _rank_key(item, calibration),
    )
    if len(youtube) < YOUTUBE_OBJECT_COUNT or len(ego4d) < EGO4D_OBJECT_COUNT:
        raise recon.ReconError(
            "INSUFFICIENT_WAVE2_DATASET_POOL",
            youtube=len(youtube),
            ego4d=len(ego4d),
        )

    # The fixed source quota embodies the wave-1 audio-track sampling
    # heuristic. Ranking within each source is entirely calibration/metadata
    # based and does not use or create an untested duration.
    selected = youtube[:YOUTUBE_OBJECT_COUNT] + ego4d[:EGO4D_OBJECT_COUNT]
    selected.sort(key=lambda item: _rank_key(item, calibration))
    validate_selection(selected, joined, excluded_paths)
    return selected


def validate_selection(
    selected: Sequence[recon.JoinedVideo],
    joined: Sequence[recon.JoinedVideo],
    excluded_paths: set[str],
) -> None:
    if len(selected) != WAVE2_OBJECT_COUNT:
        raise recon.ReconError(
            "WAVE2_OBJECT_COUNT_INVALID", observed=len(selected)
        )
    paths = [item.video_path for item in selected]
    blobs = [item.object_identity.blob_id for item in selected]
    hashes = [item.object_identity.sha256 for item in selected]
    if len(paths) != len(set(paths)):
        raise recon.ReconError("DUPLICATE_WAVE2_PATH")
    if len(blobs) != len(set(blobs)) or len(hashes) != len(set(hashes)):
        raise recon.ReconError("DUPLICATE_WAVE2_OBJECT_IDENTITY")
    if set(paths) & excluded_paths:
        raise recon.ReconError("WAVE1_OBJECT_SELECTED_IN_WAVE2")
    if any(item.duration_s is not None for item in selected):
        raise recon.ReconError("WAVE2_OBJECT_HAS_METADATA_DURATION")

    datasets = Counter(item.dataset for item in selected)
    if datasets != Counter(
        {"youtube": YOUTUBE_OBJECT_COUNT, "ego4d": EGO4D_OBJECT_COUNT}
    ):
        raise recon.ReconError(
            "WAVE2_DATASET_QUOTA_NOT_MET", observed=dict(datasets)
        )
    if datasets["youtube"] < MIN_YOUTUBE_OBJECT_COUNT:
        raise recon.ReconError("WAVE2_YOUTUBE_MINIMUM_NOT_MET")

    selected_topics = {recon.topic_hypothesis(item.text) for item in selected}
    if len(selected_topics) < MIN_TOPIC_COUNT:
        raise recon.ReconError(
            "WAVE2_TOPIC_DIVERSITY_NOT_MET", observed=len(selected_topics)
        )
    available_modalities = {
        recon.modality_hypothesis(item.text) for item in joined
    }
    selected_modalities = {
        recon.modality_hypothesis(item.text) for item in selected
    }
    if selected_modalities != available_modalities:
        raise recon.ReconError(
            "WAVE2_MODALITY_COVERAGE_NOT_MET",
            available=sorted(available_modalities),
            selected=sorted(selected_modalities),
        )


def build_plan(
    selected: Sequence[recon.JoinedVideo],
    calibration: Sequence[CalibrationObservation],
    excluded_paths: set[str],
    *,
    parquet_identity: recon.SnapshotIdentity,
    api_identity: recon.SnapshotIdentity,
    wave1_plan_identity: Mapping[str, Any],
    wave1_result_identity: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    joined_count: int,
) -> dict[str, Any]:
    # Revalidate against the selected subset plus explicit corpus modality
    # coverage already established by select_wave2_objects.
    if len(selected) != WAVE2_OBJECT_COUNT:
        raise recon.ReconError("WAVE2_OBJECT_COUNT_INVALID")

    objects: list[dict[str, Any]] = []
    for rank, item in enumerate(selected, start=1):
        supporting = gate_supporting_observations(item, calibration)
        objects.append(
            {
                "rank": rank,
                "wave2_id": f"ves-wave2-{rank:02d}",
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
                "modality_role_hypothesis": recon.modality_hypothesis(
                    item.text
                ),
                "metadata_evidence_rows": wave1_plan_tool.evidence_rows(
                    item, rows
                ),
                "evidence_interval_count": item.evidence_interval_count,
                "max_evidence_endpoint_s": item.max_evidence_end_s,
                "ranking_heuristic": {
                    "gate_compatible_wave1_ratio_count": len(supporting),
                    "gate_compatible_wave1_observation_ids": list(supporting),
                    "ordered_signals": [
                        "WAVE1_RATIO_GATE_COMPATIBILITY_COUNT_DESCENDING",
                        "OBJECT_SIZE_BYTES_DESCENDING",
                        "MAX_EVIDENCE_ENDPOINT_DESCENDING",
                        "EVIDENCE_INTERVAL_COUNT_DESCENDING",
                        "TASK_COUNT_DESCENDING",
                        "VIDEO_ID_ASCENDING",
                    ],
                    "interpretation": (
                        "A COUNTED CALIBRATION RATIO WOULD PLACE THIS BYTE "
                        "SIZE INSIDE THE TARGET DURATION GATE; THIS IS NOT AN "
                        "INFERRED OR PERSISTED DURATION."
                    ),
                },
                "actual_duration": UNRESOLVED,
                "audio_track": UNRESOLVED,
                "video_track": UNRESOLVED,
                "av_timeline": UNRESOLVED,
                "evidence_extent_is_duration": False,
                "size_ratio_is_duration": False,
                "qualification_status": NOT_QUALIFIED,
                "requested_action": REQUESTED_ACTION,
                "full_acquisition_authorized": False,
                "processing_authorized": False,
                "annotation_authorized": False,
                "release_authorized": False,
                "rights_status": "UNKNOWN_HOLD",
            }
        )

    youtube_observations = [
        item for item in calibration if item.dataset == "youtube"
    ]
    ego4d_observations = [
        item for item in calibration if item.dataset == "ego4d"
    ]
    plan: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "as_of_date": recon.AS_OF_DATE,
        "status": "READY_FOR_BOUNDED_WAVE2_STREAM_PREFLIGHT",
        "purpose": (
            "Closed exact-object wave-2 plan for bounded ISO-BMFF container "
            "preflight. Success is not claimed before the live bounded run."
        ),
        "repository": {"repo_id": recon.REPO_ID, "revision": recon.REVISION},
        "metadata_snapshots": {
            "parquet": asdict(parquet_identity),
            "repository_api": asdict(api_identity),
        },
        "wave1_calibration": {
            "plan_artifact": dict(wave1_plan_identity),
            "result_artifact": dict(wave1_result_identity),
            "observation_count": len(calibration),
            "observations": [item.as_plan_dict() for item in calibration],
            "sampling_observations": {
                "youtube_tested_count": len(youtube_observations),
                "youtube_declared_audio_count": sum(
                    item.audio_track_count >= 1
                    for item in youtube_observations
                ),
                "ego4d_tested_count": len(ego4d_observations),
                "ego4d_declared_no_audio_count": sum(
                    item.audio_track_count == 0
                    for item in ego4d_observations
                ),
                "interpretation": (
                    "SOURCE PREFERENCE IS A WAVE1 SAMPLING HEURISTIC, NOT A "
                    "CORPUS_LEVEL AUDIO CLAIM."
                ),
            },
            "ratio_policy": {
                "uses_all_observed_wave1_size_duration_ratios": True,
                "target_duration_gate_seconds": [
                    MIN_DURATION_S,
                    MAX_DURATION_S,
                ],
                "untested_duration_inference_performed": False,
                "untested_duration_persisted": False,
            },
        },
        "wave2_scope": {
            "selected_object_count": WAVE2_OBJECT_COUNT,
            "joined_exact_mp4_object_count": joined_count,
            "wave1_excluded_object_count": len(excluded_paths),
            "wave1_objects_excluded": True,
            "dataset_counts": dict(
                sorted(Counter(item.dataset for item in selected).items())
            ),
            "topic_hypotheses": sorted(
                {recon.topic_hypothesis(item.text) for item in selected}
            ),
            "modality_role_hypotheses": sorted(
                {recon.modality_hypothesis(item.text) for item in selected}
            ),
            "selected_objects_are_duration_qualified": False,
            "evidence_extent_is_duration": False,
            "ranking_policy": (
                "Within fixed 18-YouTube/2-Ego4D source quotas, rank by the "
                "count of all wave-1 observed size/duration ratios compatible "
                "with the duration gate, then larger byte size, later evidence "
                "extent, evidence count, task count, and video ID. Validate "
                "topic breadth and all available metadata modality hypotheses."
            ),
        },
        "authorization": {
            "authorized_actions": [AUTHORIZED_ACTION],
            "authorized_for_bounded_stream_container_preflight": [
                item["wave2_id"] for item in objects
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
        "wave2_objects": objects,
    }
    validate_plan(plan)
    return plan


def validate_plan(plan: Mapping[str, Any]) -> None:
    serialized = json.dumps(plan, sort_keys=True)
    if "*" in serialized:
        raise recon.ReconError("WILDCARD_PRESENT_IN_WAVE2_PLAN")
    if plan.get("schema_version") != SCHEMA_VERSION:
        raise recon.ReconError("WAVE2_SCHEMA_VERSION_INVALID")
    if plan.get("status") != "READY_FOR_BOUNDED_WAVE2_STREAM_PREFLIGHT":
        raise recon.ReconError("WAVE2_STATUS_INVALID")
    objects = plan.get("wave2_objects")
    if not isinstance(objects, list) or len(objects) != WAVE2_OBJECT_COUNT:
        raise recon.ReconError("WAVE2_PLAN_MUST_HAVE_EXACTLY_TWENTY_OBJECTS")

    authorization = plan.get("authorization")
    if not isinstance(authorization, Mapping):
        raise recon.ReconError("WAVE2_AUTHORIZATION_ABSENT")
    if authorization.get("authorized_actions") != [AUTHORIZED_ACTION]:
        raise recon.ReconError("WAVE2_ACTION_AUTHORIZATION_INVALID")
    if authorization.get(
        "authorized_for_bounded_stream_container_preflight"
    ) != [item.get("wave2_id") for item in objects]:
        raise recon.ReconError("WAVE2_PREFLIGHT_ALLOWLIST_MISMATCH")
    for key in (
        "authorized_for_full_acquisition",
        "authorized_for_full_media_download",
        "authorized_for_processing",
        "authorized_for_annotation",
        "authorized_for_release",
    ):
        if authorization.get(key) != []:
            raise recon.ReconError("WAVE2_BROAD_AUTHORIZATION_PROHIBITED")

    constraints = plan.get("constraints")
    if not isinstance(constraints, Mapping):
        raise recon.ReconError("WAVE2_CONSTRAINTS_ABSENT")
    if (
        constraints.get("closed_exact_object_list") is not True
        or constraints.get("wildcards_allowed") is not False
        or constraints.get("full_object_response_permitted_in_later_preflight")
        is not False
        or constraints.get("full_object_range_permitted_in_later_preflight")
        is not False
        or constraints.get("rights_cleared") is not False
    ):
        raise recon.ReconError("WAVE2_SCOPE_TOO_BROAD")

    calibration = plan.get("wave1_calibration")
    if not isinstance(calibration, Mapping):
        raise recon.ReconError("WAVE1_CALIBRATION_PROVENANCE_ABSENT")
    observations = calibration.get("observations")
    ratio_policy = calibration.get("ratio_policy")
    if (
        not isinstance(ratio_policy, Mapping)
        or calibration.get("observation_count") != 10
        or not isinstance(observations, list)
        or len(observations) != 10
        or ratio_policy.get("uses_all_observed_wave1_size_duration_ratios")
        is not True
        or ratio_policy.get("untested_duration_inference_performed") is not False
        or ratio_policy.get("untested_duration_persisted") is not False
    ):
        raise recon.ReconError("WAVE1_CALIBRATION_POLICY_INVALID")
    plan_artifact = calibration.get("plan_artifact")
    result_artifact = calibration.get("result_artifact")
    if (
        not isinstance(plan_artifact, Mapping)
        or plan_artifact.get("size") != EXPECTED_WAVE1_PLAN_SIZE
        or plan_artifact.get("sha256") != EXPECTED_WAVE1_PLAN_SHA256
        or not isinstance(result_artifact, Mapping)
        or result_artifact.get("size") != EXPECTED_WAVE1_RESULT_SIZE
        or result_artifact.get("sha256") != EXPECTED_WAVE1_RESULT_SHA256
    ):
        raise recon.ReconError("WAVE1_CALIBRATION_ARTIFACT_IDENTITY_INVALID")
    wave1_paths = {
        item.get("path")
        for item in observations
        if isinstance(item, Mapping)
    }
    if len(wave1_paths) != 10 or not all(
        isinstance(path, str) for path in wave1_paths
    ):
        raise recon.ReconError("WAVE1_CALIBRATION_OBSERVATIONS_INVALID")

    paths: set[str] = set()
    blobs: set[str] = set()
    hashes: set[str] = set()
    dataset_counts: Counter[str] = Counter()
    topics: set[str] = set()
    modalities: set[str] = set()
    for rank, item in enumerate(objects, start=1):
        if item.get("rank") != rank or item.get("wave2_id") != (
            f"ves-wave2-{rank:02d}"
        ):
            raise recon.ReconError("WAVE2_RANK_OR_ID_INVALID")
        if (
            item.get("repo_id") != recon.REPO_ID
            or item.get("revision") != recon.REVISION
        ):
            raise recon.ReconError("WAVE2_PINNED_REPOSITORY_CONFLICT")
        path = item.get("path")
        blob = item.get("blob_id")
        digest = item.get("sha256")
        size = item.get("size_bytes")
        if not isinstance(path, str) or not path.endswith(".mp4"):
            raise recon.ReconError("WAVE2_PATH_INVALID")
        if not isinstance(size, int) or size <= 0:
            raise recon.ReconError("WAVE2_SIZE_INVALID")
        if not recon.HEX40_RE.fullmatch(str(blob)):
            raise recon.ReconError("WAVE2_BLOB_ID_INVALID")
        if not recon.HEX64_RE.fullmatch(str(digest)):
            raise recon.ReconError("WAVE2_SHA256_INVALID")
        if path in paths or blob in blobs or digest in hashes:
            raise recon.ReconError("WAVE2_IDENTITY_DUPLICATED")
        paths.add(path)
        blobs.add(str(blob))
        hashes.add(str(digest))
        dataset_counts[str(item.get("dataset"))] += 1
        topics.add(str(item.get("topic_hypothesis")))
        modalities.add(str(item.get("modality_role_hypothesis")))
        if (
            item.get("actual_duration") != UNRESOLVED
            or item.get("audio_track") != UNRESOLVED
            or item.get("video_track") != UNRESOLVED
            or item.get("av_timeline") != UNRESOLVED
            or item.get("evidence_extent_is_duration") is not False
            or item.get("size_ratio_is_duration") is not False
            or item.get("qualification_status") != NOT_QUALIFIED
        ):
            raise recon.ReconError("WAVE2_UNTESTED_FACT_CONFLATION")
        if item.get("requested_action") != REQUESTED_ACTION:
            raise recon.ReconError("WAVE2_REQUESTED_ACTION_INVALID")
        if any(
            item.get(key) is not False
            for key in (
                "full_acquisition_authorized",
                "processing_authorized",
                "annotation_authorized",
                "release_authorized",
            )
        ):
            raise recon.ReconError("WAVE2_OBJECT_AUTHORITY_TOO_BROAD")
        if not item.get("metadata_evidence_rows"):
            raise recon.ReconError("WAVE2_EVIDENCE_ROWS_ABSENT")
        heuristic = item.get("ranking_heuristic")
        if not isinstance(heuristic, Mapping):
            raise recon.ReconError("WAVE2_RANKING_HEURISTIC_ABSENT")
        if not isinstance(
            heuristic.get("gate_compatible_wave1_ratio_count"), int
        ):
            raise recon.ReconError("WAVE2_CALIBRATION_RANK_ABSENT")

    if paths & wave1_paths:
        raise recon.ReconError("WAVE1_OBJECT_PRESENT_IN_WAVE2_PLAN")
    if dataset_counts != Counter(
        {"youtube": YOUTUBE_OBJECT_COUNT, "ego4d": EGO4D_OBJECT_COUNT}
    ):
        raise recon.ReconError(
            "WAVE2_DATASET_QUOTA_NOT_MET", observed=dict(dataset_counts)
        )
    if len(topics) < MIN_TOPIC_COUNT:
        raise recon.ReconError("WAVE2_TOPIC_DIVERSITY_NOT_MET")
    if len(modalities) < 3:
        raise recon.ReconError("WAVE2_MODALITY_DIVERSITY_NOT_MET")


def run(
    repo_root: Path,
    *,
    plan_path: Path | None = None,
    wave1_plan_path: Path | None = None,
    wave1_result_path: Path | None = None,
) -> dict[str, Any]:
    plan_path = plan_path or repo_root / PLAN_REL
    wave1_plan_path = wave1_plan_path or repo_root / WAVE1_PLAN_REL
    wave1_result_path = wave1_result_path or repo_root / WAVE1_RESULT_REL

    parquet_identity = recon.validate_snapshot(
        repo_root / recon.PARQUET_REL,
        expected_size=recon.EXPECTED_PARQUET_SIZE,
        expected_sha256=recon.EXPECTED_PARQUET_SHA256,
    )
    api_identity = recon.validate_snapshot(
        repo_root / recon.API_REL,
        expected_size=recon.EXPECTED_API_SIZE,
        expected_sha256=recon.EXPECTED_API_SHA256,
    )
    schema, rows = recon.read_parquet(repo_root / recon.PARQUET_REL)
    api = recon.load_api_snapshot(repo_root / recon.API_REL)
    parquet_identity = recon.validate_parquet_sibling(api, parquet_identity)
    object_index = recon.build_object_index(api)
    joined, duration_column = recon.join_rows(
        schema, rows, object_index, require_duration=False
    )
    if duration_column is not None:
        raise recon.ReconError("UNEXPECTED_ITEM_DURATION_COLUMN_IN_WAVE2")
    if len(joined) != len(object_index):
        raise recon.ReconError("WAVE2_METADATA_OBJECT_CARDINALITY_CONFLICT")

    calibration, excluded, wave1_plan_identity, wave1_result_identity = (
        load_wave1_calibration(wave1_plan_path, wave1_result_path)
    )
    selected = select_wave2_objects(joined, calibration, excluded)
    plan = build_plan(
        selected,
        calibration,
        excluded,
        parquet_identity=parquet_identity,
        api_identity=api_identity,
        wave1_plan_identity=wave1_plan_identity,
        wave1_result_identity=wave1_result_identity,
        rows=rows,
        joined_count=len(joined),
    )
    recon.write_json(plan_path, plan)
    return {
        "status": plan["status"],
        "plan_path": plan_path.as_posix(),
        "selected_object_count": len(selected),
        "dataset_counts": plan["wave2_scope"]["dataset_counts"],
        "topic_hypotheses": plan["wave2_scope"]["topic_hypotheses"],
        "modality_role_hypotheses": plan["wave2_scope"][
            "modality_role_hypotheses"
        ],
        "wave1_excluded_object_count": len(excluded),
        "duration_qualified_object_count": 0,
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
        result = run(args.repo_root.resolve(), plan_path=args.plan_path)
    except (recon.ReconError, OSError, ValueError, KeyError, TypeError) as exc:
        if isinstance(exc, recon.ReconError):
            print(json.dumps(exc.diagnostic(), sort_keys=True))
        else:
            print(
                json.dumps(
                    {"error": f"INPUT_OR_OUTPUT_{type(exc).__name__.upper()}"},
                    sort_keys=True,
                )
            )
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
