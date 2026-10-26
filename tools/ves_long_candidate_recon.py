#!/usr/bin/env python3
"""Offline, metadata-only VES-Bench long-video candidate reconnaissance.

The tool reads one pinned Parquet metadata object and one pinned Hugging Face
repository API snapshot.  It never opens a network connection and never reads
an MP4 body.  Candidate selection is permitted only when the Parquet contains
an unambiguous, item-level duration field.

The released VES-Bench Parquet inspected in Task 70 does not contain such a
field.  Consequently, the default run emits a fail-closed empty pool and a
blocked preflight plan rather than treating evidence interval endpoints as
video durations.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except ImportError:  # pragma: no cover - exercised only outside test/runtime env
    pa = None  # type: ignore[assignment]
    pq = None  # type: ignore[assignment]


AS_OF_DATE = "2026-09-09"
SCHEMA_VERSION = "1.0.0"
REPO_ID = "buaaplay/VES-Bench"
REVISION = "b1cdbb370ad866090e6fec82ccb9e699b10edbc7"
PARQUET_REPO_PATH = "VES-Bench.parquet"
PARQUET_REL = Path(
    "data/hf_recon/snapshots/"
    "hf_buaaplay_VES-Bench_b1cdbb3_VES-Bench.parquet"
)
API_REL = Path("data/hf_recon/snapshots/hf_api_buaaplay_VES-Bench.json")
POOL_REL = Path("data/rehearsal_plan/ves_long_candidate_pool.csv")
PLAN_REL = Path(
    "data/acquisition_preflight/ves_long_stream_preflight_plan.json"
)

EXPECTED_PARQUET_SIZE = 422_415
EXPECTED_PARQUET_SHA256 = (
    "be2dca2e9e7561ca9606291fd22f86c0a54eea353fac8c8ac3cf964b4c612376"
)
EXPECTED_API_SIZE = 79_549
EXPECTED_API_SHA256 = (
    "a1f844b2f6632e4e8a01038342239854338c9ca85e21ea9e3642cef486a69c6a"
)
MIN_DURATION_S = 1_200.0
MAX_DURATION_S = 5_400.0
DEFAULT_POOL_SIZE = 10
DEFAULT_PREFLIGHT_SIZE = 6

HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
SAFE_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")

CSV_FIELDS = [
    "candidate_id",
    "candidate_rank",
    "repo_id",
    "revision",
    "video_id",
    "video_path",
    "object_size_bytes",
    "object_blob_id",
    "object_sha256",
    "metadata_duration_s",
    "duration_column",
    "duration_gate",
    "dataset",
    "tasks",
    "topic_hypothesis",
    "modality_role_hypothesis",
    "modality_verification_status",
    "metadata_row_ordinals",
    "metadata_row_ids",
    "source_question_ids",
    "evidence_interval_count",
    "max_evidence_end_s",
    "stream_status",
    "content_status",
    "source_media_rights_status",
    "processing_rights_status",
    "annotation_rights_status",
    "full_acquisition_authorized",
    "selection_reason",
]


class ReconError(RuntimeError):
    """Structured, credential-free fail-closed error."""

    def __init__(self, code: str, **details: Any) -> None:
        super().__init__(code)
        self.code = code
        self.details = details

    def diagnostic(self) -> dict[str, Any]:
        return {"error": self.code, **self.details}


@dataclass(frozen=True)
class SnapshotIdentity:
    path: str
    size: int
    sha256: str
    repo_path: str | None = None
    blob_id: str | None = None


@dataclass(frozen=True)
class ObjectIdentity:
    path: str
    size: int
    blob_id: str
    sha256: str


@dataclass
class JoinedVideo:
    video_id: str
    video_path: str
    object_identity: ObjectIdentity
    dataset: str
    tasks: tuple[str, ...]
    duration_s: float | None
    duration_column: str | None
    row_ordinals: tuple[int, ...]
    row_ids: tuple[str, ...]
    source_question_ids: tuple[str, ...]
    evidence_interval_count: int
    max_evidence_end_s: float
    text: str


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    candidate_rank: int
    repo_id: str
    revision: str
    video_id: str
    video_path: str
    object_size_bytes: int
    object_blob_id: str
    object_sha256: str
    metadata_duration_s: float
    duration_column: str
    duration_gate: str
    dataset: str
    tasks: str
    topic_hypothesis: str
    modality_role_hypothesis: str
    modality_verification_status: str
    metadata_row_ordinals: str
    metadata_row_ids: str
    source_question_ids: str
    evidence_interval_count: int
    max_evidence_end_s: float
    stream_status: str
    content_status: str
    source_media_rights_status: str
    processing_rights_status: str
    annotation_rights_status: str
    full_acquisition_authorized: bool
    selection_reason: str


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(chunk_size):
            digest.update(block)
    return digest.hexdigest()


def validate_snapshot(
    path: Path, *, expected_size: int, expected_sha256: str
) -> SnapshotIdentity:
    if not path.is_file():
        raise ReconError("SNAPSHOT_MISSING", path=path.as_posix())
    size = path.stat().st_size
    digest = sha256_file(path)
    if size != expected_size:
        raise ReconError(
            "SNAPSHOT_SIZE_MISMATCH",
            path=path.as_posix(),
            expected=expected_size,
            observed=size,
        )
    if digest != expected_sha256:
        raise ReconError(
            "SNAPSHOT_SHA256_MISMATCH",
            path=path.as_posix(),
            expected=expected_sha256,
            observed=digest,
        )
    return SnapshotIdentity(path.as_posix(), size, digest)


def _require_pyarrow() -> None:
    if pq is None:
        raise ReconError("PYARROW_REQUIRED_FOR_PARQUET")


def read_parquet(path: Path) -> tuple[Any, list[dict[str, Any]]]:
    _require_pyarrow()
    try:
        table = pq.read_table(path)
    except Exception as exc:  # pragma: no cover - backend-specific subclasses
        raise ReconError(
            "PARQUET_PARSE_FAILED", exception_class=exc.__class__.__name__
        ) from exc
    return table.schema, table.to_pylist()


def _normalize_column(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def discover_column(
    names: Iterable[str], aliases: Sequence[str], semantic_name: str
) -> str:
    normalized_aliases = {_normalize_column(alias) for alias in aliases}
    matches = [name for name in names if _normalize_column(name) in normalized_aliases]
    if not matches:
        raise ReconError(
            "REQUIRED_COLUMN_ABSENT",
            semantic_name=semantic_name,
            observed_columns=sorted(names),
        )
    if len(matches) != 1:
        raise ReconError(
            "AMBIGUOUS_SEMANTIC_COLUMNS",
            semantic_name=semantic_name,
            matches=sorted(matches),
        )
    return matches[0]


def discover_duration_column(schema: Any) -> str:
    """Find one top-level item-duration field without considering evidence ends."""
    candidates: list[str] = []
    accepted = {
        "duration",
        "durations",
        "durationsec",
        "durationsecs",
        "durationsecond",
        "durationseconds",
        "videoduration",
        "videodurations",
        "videodurationsec",
        "videodurationsecs",
        "videodurationsecond",
        "videodurationseconds",
        "lengthsec",
        "lengthseconds",
        "videolengthsec",
        "videolengthseconds",
    }
    for field in schema:
        normalized = _normalize_column(field.name)
        if normalized not in accepted:
            continue
        if pa is not None and not (
            pa.types.is_integer(field.type)
            or pa.types.is_floating(field.type)
            or pa.types.is_string(field.type)
            or pa.types.is_large_string(field.type)
            or pa.types.is_null(field.type)
        ):
            continue
        candidates.append(field.name)
    if not candidates:
        raise ReconError(
            "MISSING_ITEM_DURATION_COLUMN",
            observed_columns=[field.name for field in schema],
            rejected_proxy="evidence.start_sec/evidence.end_sec are intervals, not video duration",
        )
    if len(candidates) != 1:
        raise ReconError(
            "AMBIGUOUS_DURATION_COLUMNS", matches=sorted(candidates)
        )
    return candidates[0]


def parse_duration(value: Any) -> float:
    if value is None or isinstance(value, bool):
        raise ReconError("ABSENT_DURATION")
    if isinstance(value, (int, float)):
        duration = float(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if re.fullmatch(r"\d+(?:\.\d+)?", stripped):
            duration = float(stripped)
        elif re.fullmatch(r"\d+:[0-5]\d(?::[0-5]\d(?:\.\d+)?)?", stripped):
            parts = [float(part) for part in stripped.split(":")]
            duration = (
                parts[0] * 60 + parts[1]
                if len(parts) == 2
                else parts[0] * 3600 + parts[1] * 60 + parts[2]
            )
        else:
            raise ReconError("INVALID_DURATION_VALUE", value=stripped[:80])
    else:
        raise ReconError("INVALID_DURATION_TYPE", type=type(value).__name__)
    if not math.isfinite(duration) or duration <= 0:
        raise ReconError("INVALID_DURATION_VALUE", value=repr(duration))
    return duration


def duration_in_gate(duration_s: float) -> bool:
    return MIN_DURATION_S <= duration_s <= MAX_DURATION_S


def load_api_snapshot(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReconError(
            "API_SNAPSHOT_PARSE_FAILED", exception_class=exc.__class__.__name__
        ) from exc
    if not isinstance(value, dict):
        raise ReconError("API_SNAPSHOT_NOT_OBJECT")
    if value.get("id") != REPO_ID:
        raise ReconError(
            "REPOSITORY_IDENTITY_CONFLICT",
            expected=REPO_ID,
            observed=value.get("id"),
        )
    if value.get("sha") != REVISION:
        raise ReconError(
            "REVISION_IDENTITY_CONFLICT",
            expected=REVISION,
            observed=value.get("sha"),
        )
    if value.get("private") is not False or value.get("gated") is not False:
        raise ReconError("REPOSITORY_ACCESS_STATE_CONFLICT")
    if not isinstance(value.get("siblings"), list):
        raise ReconError("SIBLING_INDEX_ABSENT")
    return value


def build_object_index(api: Mapping[str, Any]) -> dict[str, ObjectIdentity]:
    by_path: dict[str, ObjectIdentity] = {}
    blobs: dict[str, str] = {}
    hashes: dict[str, str] = {}
    for raw in api["siblings"]:
        if not isinstance(raw, Mapping):
            raise ReconError("INVALID_SIBLING_ENTRY")
        path = raw.get("rfilename")
        if not isinstance(path, str) or not path:
            raise ReconError("SIBLING_PATH_ABSENT")
        if path in by_path:
            raise ReconError("DUPLICATE_SIBLING_PATH", path=path)
        if not path.lower().endswith(".mp4"):
            continue
        lfs = raw.get("lfs")
        if not isinstance(lfs, Mapping):
            raise ReconError("MP4_LFS_IDENTITY_ABSENT", path=path)
        size = raw.get("size")
        lfs_size = lfs.get("size")
        blob_id = raw.get("blobId")
        sha256 = lfs.get("sha256")
        if (
            not isinstance(size, int)
            or size <= 0
            or lfs_size != size
            or not isinstance(blob_id, str)
            or not HEX40_RE.fullmatch(blob_id)
            or not isinstance(sha256, str)
            or not HEX64_RE.fullmatch(sha256)
        ):
            raise ReconError("CONFLICTING_OBJECT_IDENTITY", path=path)
        if blob_id in blobs:
            raise ReconError(
                "AMBIGUOUS_OBJECT_BLOB_ID", paths=sorted([blobs[blob_id], path])
            )
        if sha256 in hashes:
            raise ReconError(
                "AMBIGUOUS_OBJECT_SHA256", paths=sorted([hashes[sha256], path])
            )
        blobs[blob_id] = path
        hashes[sha256] = path
        by_path[path] = ObjectIdentity(path, size, blob_id, sha256)
    return by_path


def validate_parquet_sibling(
    api: Mapping[str, Any], snapshot: SnapshotIdentity
) -> SnapshotIdentity:
    matches = [
        item
        for item in api["siblings"]
        if isinstance(item, Mapping)
        and item.get("rfilename") == PARQUET_REPO_PATH
    ]
    if len(matches) != 1:
        raise ReconError(
            "PARQUET_SIBLING_JOIN_AMBIGUOUS_OR_ABSENT", match_count=len(matches)
        )
    item = matches[0]
    lfs = item.get("lfs")
    if not isinstance(lfs, Mapping):
        raise ReconError("PARQUET_LFS_IDENTITY_ABSENT")
    if (
        item.get("size") != snapshot.size
        or lfs.get("size") != snapshot.size
        or lfs.get("sha256") != snapshot.sha256
        or not isinstance(item.get("blobId"), str)
        or not HEX40_RE.fullmatch(str(item["blobId"]))
    ):
        raise ReconError(
            "PARQUET_OBJECT_IDENTITY_CONFLICT",
            repo_path=PARQUET_REPO_PATH,
        )
    return SnapshotIdentity(
        snapshot.path,
        snapshot.size,
        snapshot.sha256,
        PARQUET_REPO_PATH,
        str(item["blobId"]),
    )


def _row_identity(row: Mapping[str, Any], ordinal: int) -> tuple[str, str]:
    row_id = row.get("id")
    source_question_id = row.get("source_question_id")
    if row_id is None or not isinstance(source_question_id, str) or not source_question_id:
        raise ReconError("EVIDENCE_ROW_IDENTITY_ABSENT", row_ordinal=ordinal)
    return str(row_id), source_question_id


def join_rows(
    schema: Any,
    rows: Sequence[Mapping[str, Any]],
    objects: Mapping[str, ObjectIdentity],
    *,
    require_duration: bool,
) -> tuple[list[JoinedVideo], str | None]:
    names = [field.name for field in schema]
    video_id_col = discover_column(
        names, ["video_id", "video_identifier", "videoid"], "video_id"
    )
    video_path_col = discover_column(
        names, ["video_path", "video_file", "path", "filename"], "video_path"
    )
    duration_col: str | None
    try:
        duration_col = discover_duration_column(schema)
    except ReconError as exc:
        if exc.code != "MISSING_ITEM_DURATION_COLUMN" or require_duration:
            raise
        duration_col = None

    grouped: dict[str, list[tuple[int, Mapping[str, Any]]]] = defaultdict(list)
    path_to_video: dict[str, str] = {}
    row_ids: set[str] = set()
    source_question_ids: set[str] = set()
    for ordinal, row in enumerate(rows):
        video_id = row.get(video_id_col)
        path = row.get(video_path_col)
        if (
            not isinstance(video_id, str)
            or not video_id
            or not SAFE_VIDEO_ID_RE.fullmatch(video_id)
        ):
            raise ReconError("INVALID_VIDEO_ID", row_ordinal=ordinal)
        if not isinstance(path, str) or not path:
            raise ReconError("VIDEO_PATH_ABSENT", row_ordinal=ordinal)
        if not path.lower().endswith(".mp4"):
            raise ReconError("NON_MP4_METADATA_OBJECT", path=path)
        expected_path = f"videos/{video_id}.mp4"
        if path != expected_path:
            raise ReconError(
                "CONFLICTING_OBJECT_IDENTITY",
                video_id=video_id,
                observed_path=path,
                expected_path=expected_path,
            )
        prior_video = path_to_video.setdefault(path, video_id)
        if prior_video != video_id:
            raise ReconError(
                "AMBIGUOUS_VIDEO_PATH",
                path=path,
                video_ids=sorted([prior_video, video_id]),
            )
        if path not in objects:
            raise ReconError("MP4_OBJECT_MISSING_FROM_SIBLING_INDEX", path=path)
        rid, sqid = _row_identity(row, ordinal)
        if rid in row_ids:
            raise ReconError("DUPLICATE_METADATA_ROW_ID", row_id=rid)
        if sqid in source_question_ids:
            raise ReconError("DUPLICATE_SOURCE_QUESTION_ID", source_question_id=sqid)
        row_ids.add(rid)
        source_question_ids.add(sqid)
        grouped[video_id].append((ordinal, row))

    joined: list[JoinedVideo] = []
    for video_id in sorted(grouped):
        members = grouped[video_id]
        path = str(members[0][1][video_path_col])
        durations: list[float] = []
        if duration_col is not None:
            durations = [parse_duration(row.get(duration_col)) for _, row in members]
            if any(value != durations[0] for value in durations[1:]):
                raise ReconError(
                    "CONFLICTING_ITEM_DURATION",
                    video_id=video_id,
                    values=sorted(set(durations)),
                )
        evidence_count = 0
        max_evidence_end = 0.0
        text_parts: list[str] = []
        datasets: set[str] = set()
        tasks: set[str] = set()
        local_row_ids: list[str] = []
        local_source_ids: list[str] = []
        for ordinal, row in members:
            rid, sqid = _row_identity(row, ordinal)
            local_row_ids.append(rid)
            local_source_ids.append(sqid)
            if isinstance(row.get("dataset"), str):
                datasets.add(str(row["dataset"]))
            if isinstance(row.get("task"), str):
                tasks.add(str(row["task"]))
            for key in ("question",):
                if isinstance(row.get(key), str):
                    text_parts.append(str(row[key]))
            evidence = row.get("evidence")
            if evidence is None:
                raise ReconError("EVIDENCE_LIST_ABSENT", row_ordinal=ordinal)
            if not isinstance(evidence, list):
                raise ReconError("INVALID_EVIDENCE_LIST", row_ordinal=ordinal)
            for item in evidence:
                if not isinstance(item, Mapping):
                    raise ReconError("INVALID_EVIDENCE_ITEM", row_ordinal=ordinal)
                start = item.get("start_sec")
                end = item.get("end_sec")
                if not isinstance(start, (int, float)) or not isinstance(
                    end, (int, float)
                ):
                    raise ReconError("EVIDENCE_INTERVAL_ABSENT", row_ordinal=ordinal)
                if not math.isfinite(float(start)) or not math.isfinite(float(end)):
                    raise ReconError("INVALID_EVIDENCE_INTERVAL", row_ordinal=ordinal)
                if float(start) < 0 or float(end) < float(start):
                    raise ReconError("INVALID_EVIDENCE_INTERVAL", row_ordinal=ordinal)
                max_evidence_end = max(max_evidence_end, float(end))
                evidence_count += 1
                if isinstance(item.get("description"), str):
                    text_parts.append(str(item["description"]))
        if len(datasets) != 1:
            raise ReconError(
                "CONFLICTING_DATASET_IDENTITY",
                video_id=video_id,
                values=sorted(datasets),
            )
        joined.append(
            JoinedVideo(
                video_id=video_id,
                video_path=path,
                object_identity=objects[path],
                dataset=next(iter(datasets)),
                tasks=tuple(sorted(tasks)),
                duration_s=durations[0] if durations else None,
                duration_column=duration_col,
                row_ordinals=tuple(ordinal for ordinal, _ in members),
                row_ids=tuple(local_row_ids),
                source_question_ids=tuple(local_source_ids),
                evidence_interval_count=evidence_count,
                max_evidence_end_s=max_evidence_end,
                text=" ".join(text_parts),
            )
        )
    return joined, duration_col


TOPIC_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("sports_performance", ("athlete", "race", "goal", "gym", "dance", "performer")),
    ("food_cooking", ("cook", "food", "restaurant", "cookie", "meal", "kitchen")),
    ("technology_science", ("computer", "technology", "website", "tool", "cable", "game")),
    ("home_diy", ("house", "home", "build", "repair", "cabinet", "garden")),
    ("outdoors_travel", ("travel", "island", "beach", "outdoor", "mountain", "vehicle")),
    ("animals_nature", ("animal", "dog", "spider", "fish", "bird", "plant")),
    ("history_news", ("history", "historical", "news", "election", "map", "official")),
    ("retail_daily_life", ("store", "shopping", "receipt", "lipstick", "clothing")),
)


def topic_hypothesis(text: str) -> str:
    lowered = text.lower()
    scores = [
        (sum(lowered.count(word) for word in words), topic)
        for topic, words in TOPIC_RULES
    ]
    best_score, best_topic = max(scores, key=lambda item: (item[0], item[1]))
    return best_topic if best_score else "general_visual_events"


def modality_hypothesis(text: str) -> str:
    """Return a triage label, never a claim that an audio stream exists."""
    lowered = text.lower()
    speech = sum(
        lowered.count(word)
        for word in (
            "speak",
            "speech",
            "explain",
            "interview",
            "conversation",
            "dialogue",
            "talk",
            "announce",
        )
    )
    environment = sum(
        lowered.count(word)
        for word in (
            "drive",
            "machine",
            "hammer",
            "water",
            "crowd",
            "animal",
            "outdoor",
            "cook",
            "cut",
        )
    )
    if speech >= environment + 2:
        return "UNVERIFIED_SPEECH_HEAVY_HYPOTHESIS"
    if environment >= speech + 2:
        return "UNVERIFIED_ENVIRONMENTAL_NON_SPEECH_HYPOTHESIS"
    return "UNVERIFIED_MIXED_AV_HYPOTHESIS"


def _base_sort_key(video: JoinedVideo) -> tuple[Any, ...]:
    assert video.duration_s is not None
    # Smaller objects are cheaper for a later bounded header preflight, while
    # more evidence/task coverage is useful. Video ID is the final stable tie.
    return (
        -len(video.tasks),
        -video.evidence_interval_count,
        video.object_identity.size,
        video.duration_s,
        video.video_id,
    )


def select_diverse(
    joined: Sequence[JoinedVideo], *, count: int = DEFAULT_POOL_SIZE
) -> list[JoinedVideo]:
    eligible = [
        item
        for item in joined
        if item.duration_s is not None and duration_in_gate(item.duration_s)
    ]
    if len(eligible) < count:
        raise ReconError(
            "INSUFFICIENT_DURATION_ELIGIBLE_OBJECTS",
            required=count,
            observed=len(eligible),
        )
    remaining = sorted(eligible, key=_base_sort_key)
    selected: list[JoinedVideo] = []
    seen_datasets: Counter[str] = Counter()
    seen_topics: Counter[str] = Counter()
    seen_roles: Counter[str] = Counter()
    while len(selected) < count:
        def key(item: JoinedVideo) -> tuple[Any, ...]:
            topic = topic_hypothesis(item.text)
            role = modality_hypothesis(item.text)
            diversity_penalty = (
                seen_datasets[item.dataset] * 4
                + seen_topics[topic] * 3
                + seen_roles[role] * 2
            )
            return (diversity_penalty, *_base_sort_key(item))

        chosen = min(remaining, key=key)
        remaining.remove(chosen)
        selected.append(chosen)
        seen_datasets[chosen.dataset] += 1
        seen_topics[topic_hypothesis(chosen.text)] += 1
        seen_roles[modality_hypothesis(chosen.text)] += 1
    return selected


def candidates_from_joined(selected: Sequence[JoinedVideo]) -> list[Candidate]:
    candidates: list[Candidate] = []
    for rank, item in enumerate(selected, start=1):
        assert item.duration_s is not None and item.duration_column is not None
        topic = topic_hypothesis(item.text)
        role = modality_hypothesis(item.text)
        candidates.append(
            Candidate(
                candidate_id=f"ves-{rank:03d}",
                candidate_rank=rank,
                repo_id=REPO_ID,
                revision=REVISION,
                video_id=item.video_id,
                video_path=item.video_path,
                object_size_bytes=item.object_identity.size,
                object_blob_id=item.object_identity.blob_id,
                object_sha256=item.object_identity.sha256,
                metadata_duration_s=item.duration_s,
                duration_column=item.duration_column,
                duration_gate="PASS_1200_TO_5400_SECONDS_INCLUSIVE",
                dataset=item.dataset,
                tasks="|".join(item.tasks),
                topic_hypothesis=f"UNVERIFIED_{topic.upper()}_HYPOTHESIS",
                modality_role_hypothesis=role,
                modality_verification_status=(
                    "UNVERIFIED_PENDING_STREAM_AND_CONTENT_CHECKS"
                ),
                metadata_row_ordinals="|".join(map(str, item.row_ordinals)),
                metadata_row_ids="|".join(item.row_ids),
                source_question_ids="|".join(item.source_question_ids),
                evidence_interval_count=item.evidence_interval_count,
                max_evidence_end_s=item.max_evidence_end_s,
                stream_status="UNVERIFIED_NOT_PROBED",
                content_status="UNVERIFIED_NOT_REVIEWED",
                source_media_rights_status="UNKNOWN_HOLD",
                processing_rights_status="UNKNOWN_HOLD",
                annotation_rights_status="UNKNOWN_HOLD",
                full_acquisition_authorized=False,
                selection_reason=(
                    "DETERMINISTIC_METADATA_ONLY_DIVERSITY_TRIAGE;"
                    "ROLE_AND_TOPIC_ARE_UNVERIFIED"
                ),
            )
        )
    return candidates


def schema_audit(schema: Any, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    evidence_count = 0
    max_evidence_end = 0.0
    for row in rows:
        evidence = row.get("evidence")
        if isinstance(evidence, list):
            evidence_count += len(evidence)
            for item in evidence:
                if isinstance(item, Mapping) and isinstance(
                    item.get("end_sec"), (int, float)
                ):
                    max_evidence_end = max(max_evidence_end, float(item["end_sec"]))
    return {
        "top_level_columns": [field.name for field in schema],
        "arrow_schema": str(schema),
        "row_count": len(rows),
        "unique_video_id_count": len(
            {row.get("video_id") for row in rows if row.get("video_id") is not None}
        ),
        "evidence_interval_count": evidence_count,
        "max_evidence_end_s": max_evidence_end,
        "duration_column": None,
        "duration_finding": (
            "ABSENT: evidence interval endpoints are not whole-video durations"
        ),
    }


def hypothesis_audit(joined: Sequence[JoinedVideo]) -> dict[str, Any]:
    dataset_counts = Counter(item.dataset for item in joined)
    topic_counts = Counter(topic_hypothesis(item.text) for item in joined)
    role_counts = Counter(modality_hypothesis(item.text) for item in joined)
    return {
        "scope": "all exactly joined metadata objects; not a selected pool",
        "joined_object_count": len(joined),
        "dataset_counts": dict(sorted(dataset_counts.items())),
        "topic_hypothesis_counts": dict(sorted(topic_counts.items())),
        "modality_role_hypothesis_counts": dict(sorted(role_counts.items())),
        "verification_status": "UNVERIFIED_PENDING_STREAM_AND_CONTENT_CHECKS",
        "limitations": [
            "Question and evidence text describe visible benchmark events, not audio streams.",
            "No audio track, codec, channel, language, speech, music, or environmental-sound field exists.",
            "Hypothesis counts cannot establish candidate eligibility because item duration is absent.",
        ],
    }


def candidate_evidence_rows(
    candidate: Candidate, row_lookup: Mapping[int, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    result = []
    for ordinal_text in candidate.metadata_row_ordinals.split("|"):
        ordinal = int(ordinal_text)
        row = row_lookup[ordinal]
        result.append(
            {
                "parquet_row_ordinal_zero_based": ordinal,
                "row_id": row["id"],
                "source_question_id": row["source_question_id"],
                "dataset": row["dataset"],
                "task": row["task"],
                "evidence_interval_count": len(row["evidence"]),
            }
        )
    return result


def build_plan(
    candidates: Sequence[Candidate],
    *,
    parquet_identity: SnapshotIdentity,
    api_identity: SnapshotIdentity,
    schema_details: Mapping[str, Any],
    joined_count: int,
    rows: Sequence[Mapping[str, Any]],
    hypotheses: Mapping[str, Any],
    blocker: Mapping[str, Any] | None = None,
    preflight_count: int = DEFAULT_PREFLIGHT_SIZE,
) -> dict[str, Any]:
    if blocker is None and not (5 <= preflight_count <= 8):
        raise ReconError("INVALID_PREFLIGHT_COUNT", value=preflight_count)
    selected = list(candidates[:preflight_count]) if blocker is None else []
    row_lookup = {ordinal: row for ordinal, row in enumerate(rows)}
    plan = {
        "schema_version": SCHEMA_VERSION,
        "as_of_date": AS_OF_DATE,
        "status": "READY_FOR_LATER_BOUNDED_PREFLIGHT" if selected else "BLOCKED",
        "purpose": (
            "Closed exact-object proposal for a later bounded stream/container "
            "preflight only; this file performs and authorizes no media transfer."
        ),
        "repository": {"repo_id": REPO_ID, "revision": REVISION},
        "metadata_snapshots": {
            "parquet": asdict(parquet_identity),
            "repository_api": asdict(api_identity),
        },
        "duration_gate_seconds_inclusive": {
            "minimum": MIN_DURATION_S,
            "maximum": MAX_DURATION_S,
        },
        "schema_audit": dict(schema_details),
        "join_audit": {
            "joined_unique_video_count": joined_count,
            "join_key": "exact metadata video_path to exact sibling rfilename",
            "duplicate_or_ambiguous_joins": 0,
            "missing_mp4_objects": 0,
            "conflicting_object_identities": 0,
        },
        "metadata_hypothesis_audit": dict(hypotheses),
        "authorization": {
            "authorized_actions": [],
            "authorized_for_full_acquisition": [],
            "authorized_for_media_download": [],
            "authorized_for_processing": [],
            "authorized_for_annotation": [],
            "authorized_for_release": [],
        },
        "constraints": {
            "closed_exact_object_list": True,
            "wildcards_allowed": False,
            "network_access_performed_by_this_task": False,
            "media_body_or_range_request_performed_by_this_task": False,
            "stream_and_content_claims_verified": False,
            "rights_cleared": False,
        },
        "blocker": dict(blocker) if blocker else None,
        "ranked_objects": [],
        "unresolved_rights": [
            "No dataset card or substantive dataset/media license is present in the pinned API snapshot.",
            "Upstream source ownership, redistribution authority, and asset-level provenance are unresolved.",
            "Processing, annotation, publication, and release rights remain UNKNOWN_HOLD.",
        ],
        "modality_hypothesis_policy": (
            "All topic, speech, environmental-sound, and mixed-A/V roles are "
            "metadata-derived unverified hypotheses pending bounded stream and "
            "human content checks."
        ),
    }
    for candidate in selected:
        plan["ranked_objects"].append(
            {
                "rank": candidate.candidate_rank,
                "candidate_id": candidate.candidate_id,
                "repo_id": candidate.repo_id,
                "revision": candidate.revision,
                "path": candidate.video_path,
                "size": candidate.object_size_bytes,
                "blob_id": candidate.object_blob_id,
                "sha256": candidate.object_sha256,
                "metadata_duration_s": candidate.metadata_duration_s,
                "duration_column": candidate.duration_column,
                "evidence_rows": candidate_evidence_rows(candidate, row_lookup),
                "topic_hypothesis": candidate.topic_hypothesis,
                "modality_role_hypothesis": candidate.modality_role_hypothesis,
                "verification_status": candidate.modality_verification_status,
                "rights_status": "UNKNOWN_HOLD",
                "requested_later_action": (
                    "BOUNDED_HEADER_STREAM_CONTAINER_PREFLIGHT_ONLY"
                ),
                "full_acquisition_authorized": False,
            }
        )
    validate_plan(plan)
    return plan


def validate_plan(plan: Mapping[str, Any]) -> None:
    serialized = json.dumps(plan, sort_keys=True)
    if "*" in serialized:
        raise ReconError("WILDCARD_PRESENT_IN_PLAN")
    authorization = plan.get("authorization")
    if not isinstance(authorization, Mapping) or any(
        authorization.get(key)
        for key in (
            "authorized_actions",
            "authorized_for_full_acquisition",
            "authorized_for_media_download",
            "authorized_for_processing",
            "authorized_for_annotation",
            "authorized_for_release",
        )
    ):
        raise ReconError("PLAN_AUTHORIZATION_MUST_REMAIN_EMPTY")
    objects = plan.get("ranked_objects")
    if not isinstance(objects, list):
        raise ReconError("PLAN_OBJECT_LIST_ABSENT")
    if plan.get("status") == "READY_FOR_LATER_BOUNDED_PREFLIGHT":
        if not 5 <= len(objects) <= 8:
            raise ReconError("PLAN_OBJECT_COUNT_OUT_OF_RANGE", count=len(objects))
    elif objects:
        raise ReconError("BLOCKED_PLAN_MUST_HAVE_NO_OBJECTS")
    for item in objects:
        if item.get("repo_id") != REPO_ID or item.get("revision") != REVISION:
            raise ReconError("PLAN_OBJECT_REPOSITORY_CONFLICT")
        if not str(item.get("path", "")).endswith(".mp4"):
            raise ReconError("PLAN_OBJECT_NOT_MP4")
        if not HEX40_RE.fullmatch(str(item.get("blob_id", ""))):
            raise ReconError("PLAN_OBJECT_BLOB_ID_INVALID")
        if not HEX64_RE.fullmatch(str(item.get("sha256", ""))):
            raise ReconError("PLAN_OBJECT_SHA256_INVALID")
        if item.get("full_acquisition_authorized") is not False:
            raise ReconError("FULL_ACQUISITION_AUTHORIZATION_PROHIBITED")


def write_pool(path: Path, candidates: Sequence[Candidate]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        for candidate in candidates:
            writer.writerow(asdict(candidate))


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def run(
    repo_root: Path,
    *,
    parquet_path: Path | None = None,
    api_path: Path | None = None,
    pool_path: Path | None = None,
    plan_path: Path | None = None,
    expected_parquet_size: int = EXPECTED_PARQUET_SIZE,
    expected_parquet_sha256: str = EXPECTED_PARQUET_SHA256,
    expected_api_size: int = EXPECTED_API_SIZE,
    expected_api_sha256: str = EXPECTED_API_SHA256,
    pool_size: int = DEFAULT_POOL_SIZE,
    preflight_size: int = DEFAULT_PREFLIGHT_SIZE,
) -> dict[str, Any]:
    parquet_path = parquet_path or repo_root / PARQUET_REL
    api_path = api_path or repo_root / API_REL
    pool_path = pool_path or repo_root / POOL_REL
    plan_path = plan_path or repo_root / PLAN_REL

    parquet_identity = validate_snapshot(
        parquet_path,
        expected_size=expected_parquet_size,
        expected_sha256=expected_parquet_sha256,
    )
    api_identity = validate_snapshot(
        api_path,
        expected_size=expected_api_size,
        expected_sha256=expected_api_sha256,
    )
    schema, rows = read_parquet(parquet_path)
    details = schema_audit(schema, rows)
    api = load_api_snapshot(api_path)
    parquet_identity = validate_parquet_sibling(api, parquet_identity)
    objects = build_object_index(api)
    joined, duration_col = join_rows(
        schema, rows, objects, require_duration=False
    )
    if len(objects) != len(joined):
        raise ReconError(
            "METADATA_OBJECT_CARDINALITY_CONFLICT",
            metadata_unique_videos=len(joined),
            sibling_mp4_objects=len(objects),
        )

    candidates: list[Candidate] = []
    blocker: dict[str, Any] | None = None
    if duration_col is None:
        blocker = {
            "code": "MISSING_ITEM_DURATION_COLUMN",
            "effect": (
                "No exact 1200-to-5400-second candidate pool or ranked "
                "stream-preflight object list can be frozen."
            ),
            "why_evidence_is_not_duration": (
                "The nested evidence.start_sec and evidence.end_sec values "
                "identify question evidence intervals only. Their maximum "
                "observed endpoint is 1080.0 seconds and cannot establish a "
                "whole-video duration."
            ),
            "required_resolution": (
                "Provide authoritative item-level durations bound to these "
                "exact repo/revision/path identities, or perform a separately "
                "authorized bounded container-duration probe."
            ),
        }
    else:
        details["duration_column"] = duration_col
        details["duration_finding"] = "PRESENT_AND_ITEM_LEVEL"
        selected = select_diverse(joined, count=pool_size)
        candidates = candidates_from_joined(selected)

    write_pool(pool_path, candidates)
    plan = build_plan(
        candidates,
        parquet_identity=parquet_identity,
        api_identity=api_identity,
        schema_details=details,
        joined_count=len(joined),
        rows=rows,
        hypotheses=hypothesis_audit(joined),
        blocker=blocker,
        preflight_count=preflight_size,
    )
    write_json(plan_path, plan)
    return {
        "status": plan["status"],
        "parquet": asdict(parquet_identity),
        "repository_api": asdict(api_identity),
        "schema_audit": details,
        "joined_unique_video_count": len(joined),
        "candidate_count": len(candidates),
        "preflight_object_count": len(plan["ranked_objects"]),
        "blocker": blocker,
        "pool_path": pool_path.as_posix(),
        "plan_path": plan_path.as_posix(),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--pool-size", type=int, default=DEFAULT_POOL_SIZE)
    parser.add_argument(
        "--preflight-size", type=int, default=DEFAULT_PREFLIGHT_SIZE
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = run(
            args.repo_root.resolve(),
            pool_size=args.pool_size,
            preflight_size=args.preflight_size,
        )
    except ReconError as exc:
        print(json.dumps(exc.diagnostic(), sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] != "BLOCKED" else 3


if __name__ == "__main__":
    raise SystemExit(main())
