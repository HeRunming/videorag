"""Restricted full-timeline indexing for the human mini-pilot source pool.

This module is intentionally limited to source verification, segmentation,
source-derived observations, retrieval indexes, and build/resource manifests.
It does not create benchmark families or any evaluation artifacts.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import os
import re
import stat
import tempfile
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Any, Protocol

import numpy as np

SCHEMA_VERSION = "av-trace.mini-pilot-index/1.0"
INDEX_VERSION = "mini-pilot-full-timeline-index/1.0"
STAGE = "RESTRICTED_SOURCE_DERIVED_INDEX"
TOKEN_RE = re.compile(r"[a-z0-9]+")

DEFAULT_SOURCE_MANIFEST = Path(
    "data/restricted/mini_pilot_sources_v1/acquisition_manifest.json"
)
DEFAULT_OUTPUT_DIR = Path("data/restricted/mini_pilot_index_v1")
DEFAULT_CLIP_PATH = Path(
    "data/restricted/noaa01/models/clip-vit-base-patch32-3d74acf"
)
DEFAULT_WHISPER_PATH = Path(
    "data/restricted/noaa01/models/whisper-tiny.en-87c7102"
)
DEFAULT_AST_PATH = Path("data/restricted/noaa01/models/ast-audioset-f826b80")
DEFAULT_HAAR_PATH = Path(
    "data/restricted/noaa01/models/opencv-haarcascade-frontalface-default.xml"
)

TOP_LEVEL_ARTIFACTS = (
    "segment_manifest.json",
    "observation_manifest.json",
    "full_timeline_index.json",
    "resource_manifest.json",
    "build_manifest.json",
)
PROHIBITED_ARTIFACT_TERMS = (
    "families",
    "family",
    "negatives",
    "negative",
    "interventions",
    "intervention",
    "trajectories",
    "trajectory",
    "evaluation",
)
FORBIDDEN_SEARCH_KEYS = {
    "title",
    "filename",
    "path",
    "url",
    "source_url",
    "attribution",
    "privacy",
    "question",
    "answer",
    "answer_hypothesis",
    "answer_aliases",
    "claims",
    "claim_id",
    "claim_ids",
    "reviewer_rationale",
    "state",
    "state_role",
    "family_id",
    "family",
    "review_id",
    "intervention_id",
    "intervention",
    "evidence_id",
    "evidence_ids",
    "legacy_codex_description",
    "generated_caption",
    "evaluation",
    "label",
    "gold",
    "rights",
    "rights_flags",
    "license",
    "license_url",
    "commercial_use",
    "license_attribution_boundary",
}
GENERIC_AUDIO = {
    "Speech",
    "Male speech, man speaking",
    "Female speech, woman speaking",
    "Child speech, kid speaking",
    "Conversation",
    "Narration, monologue",
    "Speech synthesizer",
    "Chatter",
    "Hubbub, speech noise, speech babble",
    "Inside, small room",
    "Inside, large room or hall",
    "Outside, urban or manmade",
    "Outside, rural or natural",
    "Music",
    "Musical instrument",
    "Background music",
    "Theme music",
    "Ambient music",
    "Noise",
    "White noise",
    "Pink noise",
    "Wind noise (microphone)",
    "Television",
    "Radio",
    "Silence",
}
AMBIENT_SYNONYMS = {
    "water": {"ocean", "waves", "surf", "water"},
    "wave": {"waves", "surf", "ocean"},
    "waves": {"waves", "surf", "ocean"},
    "wind": {"wind"},
    "storm": {"thunderstorm", "thunder", "rain", "wind"},
    "rain": {"rain", "raindrop"},
    "animal": {"animal", "bird", "dog"},
    "vehicle": {"vehicle", "boat", "aircraft", "car"},
}


class MiniPilotIndexError(RuntimeError):
    """Fail-closed mini-pilot indexing error."""


@dataclass(frozen=True)
class IndexConfig:
    """Paths and deterministic build controls.

    Paths may be absolute for callers, but every persisted path is converted
    to a path relative to ``repo_root``.
    """

    source_manifest_paths: tuple[str | Path, ...] = (DEFAULT_SOURCE_MANIFEST,)
    output_dir: str | Path = DEFAULT_OUTPUT_DIR
    clip_model_path: str | Path = DEFAULT_CLIP_PATH
    whisper_model_path: str | Path = DEFAULT_WHISPER_PATH
    ast_model_path: str | Path = DEFAULT_AST_PATH
    haar_model_path: str | Path = DEFAULT_HAAR_PATH
    expected_source_count: int = 4
    threads: int = 8
    whisper_batch_size: int = 8
    ast_batch_size: int = 16
    clip_batch_size: int = 16
    require_clip: bool = True
    derived_artifacts_hard_fail_cap_mib: int | None = None

    @classmethod
    def from_value(cls, value: Any | None) -> IndexConfig:
        if value is None:
            return cls()
        if isinstance(value, cls):
            return value
        if isinstance(value, (str, Path)):
            return cls(source_manifest_paths=(value,))
        if not isinstance(value, Mapping):
            # Accommodate a Workstream-A dataclass/namespace without importing
            # or depending on its package during parallel implementation.
            value = {
                field.name: getattr(value, field.name)
                for field in fields(cls)
                if hasattr(value, field.name)
            }
        elif isinstance(value.get("scope"), Mapping):
            # Also accept the raw JSON form emitted by Workstream A.
            scope = value["scope"]
            snapshots = value.get("model_snapshots", {})
            value = {
                **value,
                "source_manifest_paths": (
                    scope.get(
                        "acquisition_manifest_path", DEFAULT_SOURCE_MANIFEST
                    ),
                ),
                "output_dir": scope.get("output_root", DEFAULT_OUTPUT_DIR),
                "expected_source_count": scope.get(
                    "source_count", cls.expected_source_count
                ),
                "clip_model_path": snapshots.get("vision_semantic", {}).get(
                    "snapshot_path", DEFAULT_CLIP_PATH
                ),
                "whisper_model_path": snapshots.get("speech", {}).get(
                    "snapshot_path", DEFAULT_WHISPER_PATH
                ),
                "ast_model_path": snapshots.get("ambient", {}).get(
                    "snapshot_path", DEFAULT_AST_PATH
                ),
                "haar_model_path": snapshots.get("vision_routing", {}).get(
                    "haar_snapshot_path", DEFAULT_HAAR_PATH
                ),
            }
        aliases = {
            "source_manifests": "source_manifest_paths",
            "source_manifest": "source_manifest_paths",
            "acquisition_manifest": "source_manifest_paths",
            "output_root": "output_dir",
            "clip_path": "clip_model_path",
            "whisper_path": "whisper_model_path",
            "ast_path": "ast_model_path",
            "haar_path": "haar_model_path",
            "source_count": "expected_source_count",
        }
        normalized: dict[str, Any] = {}
        valid = {field.name for field in fields(cls)}
        for key, item in value.items():
            target = aliases.get(str(key), str(key))
            if target in valid:
                normalized[target] = item
        manifests = normalized.get("source_manifest_paths")
        if manifests is not None:
            if isinstance(manifests, (str, Path)):
                manifests = (manifests,)
            else:
                manifests = tuple(manifests)
            normalized["source_manifest_paths"] = manifests
        return cls(**normalized)


def _source_plan_types() -> tuple[type[Any] | None, Any | None]:
    """Return Workstream-A types lazily so this module remains independently usable."""
    try:
        from .sources import SourcePlan, load_source_plan
    except ImportError:
        return None, None
    return SourcePlan, load_source_plan


def _config_from_source_plan(plan: Any) -> IndexConfig:
    snapshots = plan.model_snapshots
    return IndexConfig(
        source_manifest_paths=tuple(
            _repo_relative(plan.repo_root, source.source_manifest_path)
            for source in plan.sources
        ),
        output_dir=_repo_relative(plan.repo_root, plan.output_root),
        clip_model_path=snapshots["vision_semantic"]["snapshot_path"],
        whisper_model_path=snapshots["speech"]["snapshot_path"],
        ast_model_path=snapshots["ambient"]["snapshot_path"],
        haar_model_path=snapshots["vision_routing"]["haar_snapshot_path"],
        expected_source_count=len(plan.sources),
        derived_artifacts_hard_fail_cap_mib=plan.raw.get("storage_caps", {}).get(
            "derived_artifacts_hard_fail_cap_mib"
        ),
    )


def _sources_from_source_plan(plan: Any) -> list[dict[str, Any]]:
    acquisition = _load(plan.acquisition_manifest_path)
    acquisition_by_id = {
        item["source_group_id"]: item for item in acquisition["sources"]
    }
    output = []
    for source in plan.sources:
        acquisition_source = acquisition_by_id[source.source_id]
        rights_status = _restricted_processing_status(acquisition_source)
        if not _rights_allow_restricted_processing(rights_status):
            raise MiniPilotIndexError(
                "RESTRICTED_PROCESSING_NOT_AUTHORIZED:"
                f"{source.source_id}:{rights_status}"
            )
        output.append(
            {
                "source_ref": source.source_id,
                "media_path": _repo_relative(plan.repo_root, source.media_path),
                "source_manifest_path": _repo_relative(
                    plan.repo_root, source.source_manifest_path
                ),
                "duration_s": source.duration_seconds,
                "size_bytes": source.media_bytes,
                "sha256": source.media_sha256,
                "restricted_processing_status": rights_status,
                "expected_counts": dict(source.expected_counts),
            }
        )
    return output


def _normalize_source(source: Any) -> dict[str, Any]:
    if isinstance(source, Mapping):
        return dict(source)
    if all(
        hasattr(source, name)
        for name in (
            "source_id",
            "media_path",
            "duration_seconds",
            "media_bytes",
            "media_sha256",
        )
    ):
        return {
            "source_ref": source.source_id,
            "media_path": str(source.media_path),
            "source_manifest_path": str(source.source_manifest_path),
            "duration_s": source.duration_seconds,
            "size_bytes": source.media_bytes,
            "sha256": source.media_sha256,
            "restricted_processing_status": "VERIFIED_BY_SOURCE_PLAN",
            "expected_counts": dict(source.expected_counts),
        }
    raise MiniPilotIndexError(f"UNSUPPORTED_SOURCE_SPEC:{type(source).__name__}")


class ModelBackend(Protocol):
    """Minimal injectable model interface used by fixture tests and builds."""

    runtime: Mapping[str, Any]

    def whisper(
        self, identifiers: Sequence[str], samples: Sequence[np.ndarray]
    ) -> list[dict[str, Any]]: ...

    def ast(self, samples: Sequence[np.ndarray]) -> list[dict[str, Any]]: ...

    def clip_images(self, images: Sequence[np.ndarray]) -> np.ndarray: ...

    def clip_text(self, texts: Sequence[str]) -> np.ndarray: ...


class MediaBackend(Protocol):
    def iter_sampled_frames(
        self, path: Path, cells: Sequence[Mapping[str, Any]]
    ) -> Iterator[tuple[Mapping[str, Any], np.ndarray, int, str]]: ...

    def decode_audio(self, path: Path, target_rate: int = 16_000) -> np.ndarray: ...


def _load(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _json_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _sha256(path: Path, *, prefixed: bool = False) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    value = digest.hexdigest()
    return f"sha256:{value}" if prefixed else value


def _atomic_dump(path: Path, value: Any, *, restricted: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if restricted:
        path.parent.chmod(0o700)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(name)
    try:
        os.fchmod(descriptor, 0o600 if restricted else 0o644)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(
                json.dumps(
                    value,
                    indent=2,
                    sort_keys=True,
                    ensure_ascii=False,
                    allow_nan=False,
                ).encode("utf-8")
                + b"\n"
            )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        path.chmod(0o600 if restricted else 0o644)
    finally:
        temporary.unlink(missing_ok=True)


def _safe_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _resolve_repo_path(repo_root: Path, value: str | Path) -> Path:
    path = Path(value)
    result = path if path.is_absolute() else repo_root / path
    if not _safe_under(result, repo_root):
        raise MiniPilotIndexError(f"PATH_OUTSIDE_REPOSITORY:{path}")
    return result


def _repo_relative(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise MiniPilotIndexError(f"PATH_OUTSIDE_REPOSITORY:{path}") from exc


def _tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(unicodedata.normalize("NFKC", text).casefold())


def _round(value: float | np.floating[Any], digits: int = 8) -> float:
    return round(float(value), digits)


def _version(package: str) -> str | None:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return None


def _make_windows(
    duration_s: float, *, length_s: int, stride_s: int, min_remaining_s: int
) -> list[tuple[int, int]]:
    duration_us = round(duration_s * 1_000_000)
    length_us = length_s * 1_000_000
    stride_us = stride_s * 1_000_000
    minimum_us = min_remaining_s * 1_000_000
    output: list[tuple[int, int]] = []
    index = 0
    while duration_us - index * stride_us >= minimum_us:
        start = index * stride_us
        end = min(start + length_us, duration_us)
        if end > start:
            output.append((start, end))
        index += 1
    return output


def _first(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def _restricted_processing_status(source: Mapping[str, Any]) -> str:
    boundary = source.get("license_attribution_boundary", {})
    decisions = boundary.get("decisions", {}) if isinstance(boundary, Mapping) else {}
    item = decisions.get("restricted_processing", {})
    if isinstance(item, Mapping):
        return str(item.get("status", ""))
    return str(item or source.get("restricted_processing_status", ""))


def _rights_allow_restricted_processing(status: str) -> bool:
    normalized = status.upper()
    return (
        ("ALLOWED" in normalized or "AUTHORIZED" in normalized)
        and "NOT_AUTHORIZED" not in normalized
        and "BLOCKED" not in normalized
        and "PROHIBITED" not in normalized
    )


def _source_from_record(
    repo_root: Path, source: Mapping[str, Any], manifest_path: Path
) -> dict[str, Any]:
    source_ref = str(
        _first(source, "source_group_id", "source_ref", "candidate_id", "stable_source_id")
        or ""
    )
    if not source_ref:
        raise MiniPilotIndexError(f"SOURCE_ID_MISSING:{manifest_path}")
    payloads = source.get("payload_files") or source.get("files") or ()
    videos = [
        item
        for item in payloads
        if str(item.get("role", "")).lower()
        in {"primary_video", "video", "source_video", "media"}
    ]
    if len(videos) != 1:
        raise MiniPilotIndexError(f"PRIMARY_VIDEO_COUNT:{source_ref}:{len(videos)}")
    video = videos[0]
    raw_path = _first(video, "custodian_path", "path", "repo_path")
    if not raw_path:
        directory = source.get("source_directory")
        filename = video.get("filename")
        if directory and filename:
            raw_path = str(Path(directory) / filename)
    if not raw_path:
        raise MiniPilotIndexError(f"SOURCE_PATH_MISSING:{source_ref}")
    media_path = _resolve_repo_path(repo_root, raw_path)
    if not media_path.is_file() or media_path.is_symlink():
        raise MiniPilotIndexError(f"SOURCE_MISSING_OR_UNSAFE:{source_ref}")
    expected_size = int(_first(video, "bytes", "size_bytes") or 0)
    expected_hash = str(_first(video, "sha256", "hash") or "").removeprefix("sha256:")
    if not expected_hash or not expected_size:
        raise MiniPilotIndexError(f"SOURCE_IDENTITY_INCOMPLETE:{source_ref}")
    if media_path.stat().st_size != expected_size or _sha256(media_path) != expected_hash:
        raise MiniPilotIndexError(f"SOURCE_IDENTITY_MISMATCH:{source_ref}")
    decode = source.get("decode_facts") or source.get("video_validation") or {}
    duration = _first(
        source,
        "duration_s",
        "duration_seconds",
    )
    if duration is None and isinstance(decode, Mapping):
        duration = _first(decode, "duration_s", "duration_seconds")
    if duration is None:
        raise MiniPilotIndexError(f"SOURCE_DURATION_MISSING:{source_ref}")
    rights_status = _restricted_processing_status(source)
    if not _rights_allow_restricted_processing(rights_status):
        raise MiniPilotIndexError(
            f"RESTRICTED_PROCESSING_NOT_AUTHORIZED:{source_ref}:{rights_status}"
        )
    status = str(source.get("status", ""))
    if status and not any(word in status.upper() for word in ("COMPLETE", "READY", "VALIDATED")):
        raise MiniPilotIndexError(f"SOURCE_NOT_READY:{source_ref}:{status}")
    return {
        "source_ref": source_ref,
        "media_path": _repo_relative(repo_root, media_path),
        "source_manifest_path": _repo_relative(repo_root, manifest_path),
        "duration_s": float(duration),
        "size_bytes": expected_size,
        "sha256": expected_hash,
        # Rights are retained only in resource/build metadata, never copied
        # into searchable records.
        "restricted_processing_status": rights_status,
    }


def load_sources(
    repo_root: str | Path,
    source_manifest_paths: Sequence[str | Path],
    *,
    expected_source_count: int,
) -> list[dict[str, Any]]:
    """Load and verify aggregate or per-source acquisition manifests."""
    root = Path(repo_root).resolve()
    output: list[dict[str, Any]] = []
    for raw_manifest in source_manifest_paths:
        path = _resolve_repo_path(root, raw_manifest)
        if not path.is_file() or path.is_symlink():
            raise MiniPilotIndexError(f"SOURCE_MANIFEST_MISSING_OR_UNSAFE:{raw_manifest}")
        document = _load(path)
        if isinstance(document, Mapping) and isinstance(document.get("sources"), list):
            records = document["sources"]
        elif isinstance(document, Mapping):
            records = [document]
        else:
            raise MiniPilotIndexError(f"SOURCE_MANIFEST_INVALID:{raw_manifest}")
        output.extend(_source_from_record(root, item, path) for item in records)
    output.sort(key=lambda item: item["source_ref"])
    refs = [item["source_ref"] for item in output]
    if len(refs) != len(set(refs)):
        raise MiniPilotIndexError("DUPLICATE_SOURCE_REF")
    if len(output) != expected_source_count:
        raise MiniPilotIndexError(
            f"EXPECTED_SOURCE_COUNT:{expected_source_count}:OBSERVED:{len(output)}"
        )
    return output


def build_segment_manifest(
    repo_root: str | Path,
    sources_or_config: Sequence[Mapping[str, Any]] | Mapping[str, Any] | IndexConfig,
) -> dict[str, Any]:
    """Build the exact 4 s / 8 s / 32 s timeline lattice."""
    root = Path(repo_root).resolve()
    source_plan_type, _ = _source_plan_types()
    if source_plan_type is not None and isinstance(sources_or_config, source_plan_type):
        sources = _sources_from_source_plan(sources_or_config)
    elif isinstance(sources_or_config, Sequence) and not isinstance(
        sources_or_config, (str, bytes, Mapping)
    ):
        sources = [_normalize_source(item) for item in sources_or_config]
    else:
        config = IndexConfig.from_value(sources_or_config)
        sources = load_sources(
            root,
            config.source_manifest_paths,
            expected_source_count=config.expected_source_count,
        )
    all_cells: list[dict[str, Any]] = []
    all_segments: list[dict[str, Any]] = []
    source_records: list[dict[str, Any]] = []
    totals: Counter[str] = Counter()
    for source in sorted(sources, key=lambda item: item["source_ref"]):
        duration_s = float(source["duration_s"])
        duration_us = round(duration_s * 1_000_000)
        prefix = str(source["sha256"])[:12]
        cells = _make_windows(
            duration_s, length_s=4, stride_s=4, min_remaining_s=0
        )
        fine = _make_windows(
            duration_s, length_s=8, stride_s=4, min_remaining_s=4
        )
        context = _make_windows(
            duration_s, length_s=32, stride_s=16, min_remaining_s=16
        )
        cell_records = []
        for index, (start, end) in enumerate(cells):
            cell = {
                "cell_id": f"cell.{prefix}.{index:06d}",
                "source_ref": source["source_ref"],
                "source_sha256": source["sha256"],
                "cell_index": index,
                "start_us": start,
                "end_us": end,
                "sample_time_us": min(
                    start + 2_000_000, max(start, duration_us - 1)
                ),
            }
            cell_records.append(cell)
            all_cells.append(cell)
        for scale, windows in (("fine", fine), ("context", context)):
            for index, (start, end) in enumerate(windows):
                all_segments.append(
                    {
                        "segment_id": f"seg.{prefix}.{scale}.{index:06d}",
                        "source_ref": source["source_ref"],
                        "source_sha256": source["sha256"],
                        "scale": scale,
                        "lattice_index": index,
                        "start_us": start,
                        "end_us": end,
                        "binding_cell_ids": [
                            cell["cell_id"]
                            for cell in cell_records
                            if cell["start_us"] < end and cell["end_us"] > start
                        ],
                    }
                )
        counts = {
            "base_cells": len(cells),
            "fine_windows": len(fine),
            "context_windows": len(context),
            "windows": len(fine) + len(context),
        }
        expected_counts = source.get("expected_counts")
        if expected_counts:
            observed = {
                "base_cells": counts["base_cells"],
                "fine_windows": counts["fine_windows"],
                "context_windows": counts["context_windows"],
                "temporal_segments": counts["windows"],
                "whisper_chunks": math.ceil(duration_s / 30),
                "checkpoints": 4,
            }
            if dict(expected_counts) != observed:
                raise MiniPilotIndexError(
                    f"SEGMENT_COUNT_MISMATCH:{source['source_ref']}"
                )
        totals.update(counts)
        source_records.append(
            {
                "source_ref": source["source_ref"],
                "media_path": source["media_path"],
                "source_manifest_path": source["source_manifest_path"],
                "duration_us": duration_us,
                "size_bytes": source["size_bytes"],
                "sha256": source["sha256"],
                "counts": counts,
            }
        )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "restricted": True,
        "time_unit": "integer_microseconds",
        "source_count": len(source_records),
        "segmentation": {
            "base_cell": {"length_s": 4, "stride_s": 4},
            "fine": {"length_s": 8, "stride_s": 4, "min_remaining_s": 4},
            "context": {
                "length_s": 32,
                "stride_s": 16,
                "min_remaining_s": 16,
            },
            "frame_sample_offset_s": 2,
        },
        "sources": source_records,
        "totals": {
            **dict(sorted(totals.items())),
            "maximum_modality_records": totals["windows"] * 3,
        },
        "base_cells": all_cells,
        "segments": all_segments,
    }
    manifest["segment_manifest_hash"] = _json_hash(manifest)
    return manifest


def _configure_runtime(threads: int) -> dict[str, Any]:
    if threads < 1:
        raise MiniPilotIndexError("THREAD_COUNT_MUST_BE_POSITIVE")
    for key in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HUGGINGFACE_TOKEN"):
        os.environ.pop(key, None)
    values = {
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "HF_HUB_DISABLE_PROGRESS_BARS": "1",
        "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1",
        "TOKENIZERS_PARALLELISM": "false",
        "OMP_NUM_THREADS": str(threads),
        "MKL_NUM_THREADS": str(threads),
    }
    os.environ.update(values)
    with np.errstate(all="ignore"):
        if "long" not in np.__dict__:
            np.long = np.int64  # type: ignore[attr-defined]
        if "ulong" not in np.__dict__:
            np.ulong = np.uint64  # type: ignore[attr-defined]
    return {**values, "device": "cpu", "network_access": "disabled"}


def _snapshot_files(
    repo_root: Path, raw_path: str | Path
) -> tuple[list[dict[str, Any]], str]:
    path = _resolve_repo_path(repo_root, raw_path)
    if not path.exists() or path.is_symlink():
        raise MiniPilotIndexError(f"MODEL_PATH_MISSING_OR_UNSAFE:{raw_path}")
    if path.is_file():
        records = [
            {
                "path": _repo_relative(repo_root, path),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        ]
        return records, _json_hash(
            [
                {
                    "path": path.name,
                    "size_bytes": path.stat().st_size,
                    "sha256": records[0]["sha256"],
                }
            ]
        )
    sums = path / "SHA256SUMS"
    hash_records: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    if sums.is_file() and not sums.is_symlink():
        for line in sums.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            digest, relative = line.split(maxsplit=1)
            listed = Path(relative.lstrip("*"))
            candidate = listed if listed.is_absolute() else path / listed
            if not candidate.is_file() and not listed.is_absolute():
                for ancestor in path.parents:
                    alternative = ancestor / listed
                    if alternative.is_file():
                        candidate = alternative
                        break
            if (
                not candidate.is_file()
                or candidate.is_symlink()
                or not _safe_under(candidate, repo_root)
            ):
                raise MiniPilotIndexError(
                    f"MODEL_FILE_MISSING_OR_UNSAFE:{raw_path}:{relative}"
                )
            observed = _sha256(candidate)
            if observed != digest:
                raise MiniPilotIndexError(
                    f"MODEL_FILE_HASH_MISMATCH:{raw_path}:{relative}"
                )
            snapshot_relative = (
                candidate.relative_to(path).as_posix()
                if _safe_under(candidate, path)
                else relative
            )
            hash_records.append(
                {
                    "path": snapshot_relative,
                    "size_bytes": candidate.stat().st_size,
                    "sha256": digest,
                }
            )
            records.append(
                {
                    "path": _repo_relative(repo_root, candidate),
                    "size_bytes": candidate.stat().st_size,
                    "sha256": digest,
                }
            )
    else:
        files = sorted(
            item
            for item in path.rglob("*")
            if item.is_file() and item.name != "SHA256SUMS"
        )
        for item in files:
            digest = _sha256(item)
            hash_records.append(
                {
                    "path": item.relative_to(path).as_posix(),
                    "size_bytes": item.stat().st_size,
                    "sha256": digest,
                }
            )
            records.append(
                {
                    "path": _repo_relative(repo_root, item),
                    "size_bytes": item.stat().st_size,
                    "sha256": digest,
                }
            )
    if not records:
        raise MiniPilotIndexError(f"MODEL_SNAPSHOT_EMPTY:{raw_path}")
    return records, _json_hash(hash_records)


def build_resource_manifest(
    repo_root: str | Path,
    config: IndexConfig | Mapping[str, Any],
    sources: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    source_plan_type, _ = _source_plan_types()
    cfg = (
        _config_from_source_plan(config)
        if source_plan_type is not None and isinstance(config, source_plan_type)
        else IndexConfig.from_value(config)
    )
    runtime = _configure_runtime(cfg.threads)
    models: dict[str, Any] = {}
    expected_snapshots = (
        config.model_snapshots
        if source_plan_type is not None and isinstance(config, source_plan_type)
        else {}
    )
    for name, path in (
        ("clip", cfg.clip_model_path),
        ("whisper", cfg.whisper_model_path),
        ("ast", cfg.ast_model_path),
        ("opencv_haar", cfg.haar_model_path),
    ):
        records, snapshot_hash = _snapshot_files(root, path)
        plan_name = {
            "clip": "vision_semantic",
            "whisper": "speech",
            "ast": "ambient",
            "opencv_haar": "vision_routing",
        }[name]
        expected = expected_snapshots.get(plan_name, {})
        if name == "opencv_haar":
            expected_hash = expected.get("haar_sha256")
            observed_hash = records[0]["sha256"]
            if expected_hash and observed_hash != expected_hash:
                raise MiniPilotIndexError("MODEL_PIN_MISMATCH:opencv_haar")
        else:
            expected_hash = expected.get("snapshot_hash")
            if expected_hash and snapshot_hash != expected_hash:
                raise MiniPilotIndexError(f"MODEL_PIN_MISMATCH:{name}")
            expected_weight = expected.get("weights_sha256")
            if expected_weight and not any(
                item["sha256"] == expected_weight for item in records
            ):
                raise MiniPilotIndexError(f"MODEL_WEIGHT_PIN_MISMATCH:{name}")
        models[name] = {
            "path": _repo_relative(root, _resolve_repo_path(root, path)),
            "files": records,
            "snapshot_hash": snapshot_hash,
            "frozen": True,
            "local_files_only": True,
            "device": "cpu",
        }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "runtime": runtime,
        "models": models,
        "sources": [
            {
                "source_ref": item["source_ref"],
                "media_path": item["media_path"],
                "source_manifest_path": item["source_manifest_path"],
                "sha256": item["sha256"],
                "size_bytes": item["size_bytes"],
                "restricted_processing_status": item[
                    "restricted_processing_status"
                ],
            }
            for item in sources
        ],
        "rights_policy": {
            "restricted_processing_required": True,
            "rights_metadata_searchable": False,
            "redistribution_authorized": False,
        },
        "media_derivatives": {
            "persisted_frames": False,
            "persisted_audio": False,
            "persisted_clips": False,
        },
    }
    manifest["resource_manifest_hash"] = _json_hash(manifest)
    return manifest


class PyAVMediaBackend:
    """Sequential media decoder. Decoded frames/audio remain memory-only."""

    def iter_sampled_frames(
        self, path: Path, cells: Sequence[Mapping[str, Any]]
    ) -> Iterator[tuple[Mapping[str, Any], np.ndarray, int, str]]:
        try:
            import av
        except Exception as exc:  # pragma: no cover - environment dependent
            raise MiniPilotIndexError("PYAV_IMPORT_FAILED") from exc
        targets = [int(item["sample_time_us"]) for item in cells]
        cursor = 0
        previous: tuple[Any, int, str] | None = None
        with av.open(str(path), mode="r") as container:
            stream = next((s for s in container.streams if s.type == "video"), None)
            if stream is None:
                raise MiniPilotIndexError(f"VIDEO_STREAM_MISSING:{path.name}")
            for frame in container.decode(stream):
                if frame.pts is None:
                    continue
                frame_us = round(float(frame.pts * frame.time_base) * 1_000_000)
                while cursor < len(targets) and frame_us >= targets[cursor]:
                    chosen = previous or (frame, int(frame.pts), str(frame.time_base))
                    yield (
                        cells[cursor],
                        chosen[0].to_ndarray(format="rgb24"),
                        chosen[1],
                        chosen[2],
                    )
                    cursor += 1
                if cursor >= len(targets):
                    break
                previous = (frame, int(frame.pts), str(frame.time_base))
        while cursor < len(targets) and previous is not None:
            yield (
                cells[cursor],
                previous[0].to_ndarray(format="rgb24"),
                previous[1],
                previous[2],
            )
            cursor += 1
        if cursor != len(targets):
            raise MiniPilotIndexError(
                f"FRAME_SAMPLING_INCOMPLETE:{path.name}:{cursor}/{len(targets)}"
            )

    def decode_audio(self, path: Path, target_rate: int = 16_000) -> np.ndarray:
        try:
            import av
        except Exception as exc:  # pragma: no cover - environment dependent
            raise MiniPilotIndexError("PYAV_IMPORT_FAILED") from exc
        parts: list[np.ndarray] = []
        with av.open(str(path), mode="r") as container:
            stream = next((s for s in container.streams if s.type == "audio"), None)
            if stream is None:
                raise MiniPilotIndexError(f"AUDIO_STREAM_MISSING:{path.name}")
            resampler = av.audio.resampler.AudioResampler(
                format="fltp", layout="mono", rate=target_rate
            )
            for frame in container.decode(stream):
                for converted in resampler.resample(frame):
                    parts.append(
                        converted.to_ndarray().reshape(-1).astype(np.float32)
                    )
            for converted in resampler.resample(None):
                parts.append(converted.to_ndarray().reshape(-1).astype(np.float32))
        if not parts:
            raise MiniPilotIndexError(f"AUDIO_DECODE_EMPTY:{path.name}")
        result = np.concatenate(parts)
        if not np.isfinite(result).all():
            raise MiniPilotIndexError(f"AUDIO_DECODE_NONFINITE:{path.name}")
        return result


def _routing_features(
    rgb: np.ndarray, previous_small: np.ndarray | None, face_cascade: Any
) -> tuple[dict[str, Any], np.ndarray]:
    try:
        import cv2
    except Exception as exc:  # pragma: no cover - environment dependent
        raise MiniPilotIndexError("OPENCV_IMPORT_FAILED") from exc
    small = cv2.resize(rgb, (160, 90), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    hsv = cv2.cvtColor(small, cv2.COLOR_RGB2HSV)
    edges = cv2.Canny(gray, 80, 160)
    histogram = cv2.calcHist([hsv], [0], None, [12], [0, 180]).reshape(-1)
    histogram = histogram / max(float(histogram.sum()), 1.0)
    motion = (
        float(np.mean(cv2.absdiff(gray, previous_small))) / 255.0
        if previous_small is not None
        else 0.0
    )
    faces = (
        face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4)
        if face_cascade is not None
        else ()
    )
    return (
        {
            "luminance_mean": _round(np.mean(gray) / 255.0),
            "luminance_std": _round(np.std(gray) / 255.0),
            "hue_histogram_12": [_round(item) for item in histogram],
            "edge_density": _round(np.mean(edges > 0)),
            "motion_or_change": _round(motion),
            "blank_frame": bool(np.std(gray) < 2.0),
            "pinned_haar_face_presence": bool(len(faces)),
            "semantic_claim_allowed": False,
        },
        gray,
    )


class LocalFrozenModels:
    """Frozen CPU-only transformers loaded exclusively from local paths."""

    def __init__(self, repo_root: Path, config: IndexConfig) -> None:
        self.runtime = _configure_runtime(config.threads)
        try:
            import torch
            from transformers import (
                ASTFeatureExtractor,
                ASTForAudioClassification,
                CLIPModel,
                CLIPProcessor,
                WhisperForConditionalGeneration,
                WhisperProcessor,
            )
        except Exception as exc:  # pragma: no cover - environment dependent
            raise MiniPilotIndexError("LOCAL_MODEL_IMPORT_FAILED") from exc
        self.torch = torch
        torch.manual_seed(0)
        torch.use_deterministic_algorithms(True)
        torch.set_num_threads(config.threads)
        try:
            torch.set_num_interop_threads(1)
        except RuntimeError:
            pass
        clip_path = _resolve_repo_path(repo_root, config.clip_model_path)
        whisper_path = _resolve_repo_path(repo_root, config.whisper_model_path)
        ast_path = _resolve_repo_path(repo_root, config.ast_model_path)
        try:
            self.clip_processor = CLIPProcessor.from_pretrained(
                clip_path, local_files_only=True, use_fast=False
            )
            self.clip_model = CLIPModel.from_pretrained(
                clip_path, local_files_only=True
            ).to("cpu").eval()
            self.whisper_processor = WhisperProcessor.from_pretrained(
                whisper_path, local_files_only=True
            )
            self.whisper_model = WhisperForConditionalGeneration.from_pretrained(
                whisper_path, local_files_only=True
            ).to("cpu").eval()
            self.ast_processor = ASTFeatureExtractor.from_pretrained(
                ast_path, local_files_only=True
            )
            self.ast_model = ASTForAudioClassification.from_pretrained(
                ast_path, local_files_only=True
            ).to("cpu").eval()
        except Exception as exc:  # pragma: no cover - environment dependent
            raise MiniPilotIndexError("LOCAL_MODEL_LOAD_FAILED") from exc
        for model in (self.clip_model, self.whisper_model, self.ast_model):
            for parameter in model.parameters():
                parameter.requires_grad_(False)

    def whisper(
        self, identifiers: Sequence[str], samples: Sequence[np.ndarray]
    ) -> list[dict[str, Any]]:
        inputs = self.whisper_processor(
            list(samples),
            sampling_rate=16_000,
            return_tensors="pt",
            padding=True,
            return_attention_mask=True,
        )
        with self.torch.inference_mode():
            generated = self.whisper_model.generate(
                inputs.input_features,
                attention_mask=inputs.attention_mask,
                do_sample=False,
                num_beams=1,
                max_new_tokens=128,
                return_dict_in_generate=True,
                output_scores=True,
                return_timestamps=False,
            )
            sequences = generated.sequences
            scores = self.whisper_model.compute_transition_scores(
                sequences, generated.scores, normalize_logits=True
            )
        special = set(self.whisper_processor.tokenizer.all_special_ids)
        output = []
        for row, sequence in enumerate(sequences):
            count = scores.shape[1]
            token_ids = sequence[-count:].tolist() if count else []
            values = [
                float(score)
                for token, score in zip(token_ids, scores[row].tolist())
                if token not in special
            ]
            text = " ".join(
                self.whisper_processor.tokenizer.decode(
                    sequence, skip_special_tokens=True
                ).split()
            )
            mean = float(np.mean(values)) if values else None
            flags = []
            if len(values) < 5:
                flags.append("TOO_FEW_LEXICAL_TOKENS")
            if mean is None or mean < -0.85:
                flags.append("LOW_GENERATED_TOKEN_LOGPROB")
            output.append(
                {
                    "chunk_id": identifiers[row],
                    "text": text,
                    "token_count": len(values),
                    "mean_generated_token_log_probability": (
                        _round(mean) if mean is not None else None
                    ),
                    "quality_gate_pass": bool(text) and not flags,
                    "quality_flags": flags,
                }
            )
        return output

    def ast(self, samples: Sequence[np.ndarray]) -> list[dict[str, Any]]:
        inputs = self.ast_processor(
            list(samples), sampling_rate=16_000, return_tensors="pt", padding=True
        )
        with self.torch.inference_mode():
            logits = self.ast_model(input_values=inputs.input_values).logits
            values, indices = self.torch.topk(
                self.torch.sigmoid(logits), k=15, dim=-1
            )
        output = []
        for row in range(values.shape[0]):
            labels = [
                {
                    "class_id": int(index),
                    "label": self.ast_model.config.id2label[int(index)],
                    "probability": _round(value),
                }
                for value, index in zip(
                    values[row].tolist(), indices[row].tolist()
                )
            ]
            specific = [
                item for item in labels if not _is_generic_audio(item["label"])
            ]
            output.append(
                {
                    "top15": labels,
                    "quality_gate_pass": bool(specific),
                    "quality_flags": [] if specific else ["NO_SPECIFIC_LABEL"],
                }
            )
        return output

    def clip_images(self, images: Sequence[np.ndarray]) -> np.ndarray:
        inputs = self.clip_processor(images=list(images), return_tensors="pt")
        with self.torch.inference_mode():
            outputs = self.clip_model.vision_model(
                pixel_values=inputs.pixel_values, return_dict=True
            )
            values = self.clip_model.visual_projection(outputs.pooler_output)
        values = values.float()
        values = values / values.norm(dim=-1, keepdim=True).clamp_min(1e-12)
        return values.cpu().numpy().astype(np.float32)

    def clip_text(self, texts: Sequence[str]) -> np.ndarray:
        inputs = self.clip_processor(
            text=list(texts),
            return_tensors="pt",
            padding=True,
            truncation=True,
        )
        with self.torch.inference_mode():
            outputs = self.clip_model.text_model(
                input_ids=inputs.input_ids,
                attention_mask=inputs.attention_mask,
                return_dict=True,
            )
            values = self.clip_model.text_projection(outputs.pooler_output)
        values = values.float()
        values = values / values.norm(dim=-1, keepdim=True).clamp_min(1e-12)
        return values.cpu().numpy().astype(np.float32)


def _slice_audio(
    audio: np.ndarray, start_us: int, end_us: int, rate: int = 16_000
) -> np.ndarray:
    left = max(0, round(start_us * rate / 1_000_000))
    right = min(len(audio), round(end_us * rate / 1_000_000))
    expected = max(1, round((end_us - start_us) * rate / 1_000_000))
    result = audio[left:right]
    if len(result) < expected:
        result = np.pad(result, (0, expected - len(result)))
    return result.astype(np.float32, copy=False)


def _overlaps(a: Sequence[int], b: Sequence[int]) -> bool:
    return max(a[0], b[0]) < min(a[1], b[1])


def _is_generic_audio(label: str) -> bool:
    return label in GENERIC_AUDIO or label.startswith(
        (
            "Music",
            "Speech",
            "Male speech",
            "Female speech",
            "Child speech",
            "Narration",
            "Conversation",
            "Inside,",
            "Outside,",
        )
    )


def _project_speech(chunks: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for chunk in chunks:
        chunk_id = str(chunk["chunk_id"])
        record_id = "asr." + hashlib.sha256(chunk_id.encode()).hexdigest()[:20]
        text = str(chunk.get("text", "")).strip()
        output.append(
            {
                "segment_id": record_id,
                "speech_record_id": record_id,
                "chunk_id": chunk_id,
                "source_ref": chunk["source_ref"],
                "scale": "speech_chunk_30s",
                "start_us": int(chunk["start_us"]),
                "end_us": int(chunk["end_us"]),
                "modality": "speech",
                "text": text,
                "derived_from_chunk_ids": [chunk_id],
                "searchable": bool(text and chunk.get("quality_gate_pass")),
                "exclusion_reason": (
                    None
                    if text and chunk.get("quality_gate_pass")
                    else "empty_or_failed_quality_gate"
                ),
                "citation_interval_truth": "whole_non_overlapping_asr_chunk",
            }
        )
    return output


def _aggregate_ambient(
    fine_records: Sequence[Mapping[str, Any]],
    segments: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    output = [dict(item) for item in fine_records]
    for segment in segments:
        if segment["scale"] != "context":
            continue
        children = [
            item
            for item in fine_records
            if _overlaps(
                (int(item["start_us"]), int(item["end_us"])),
                (int(segment["start_us"]), int(segment["end_us"])),
            )
        ]
        values: dict[int, list[tuple[str, float, bool]]] = defaultdict(list)
        for child in children:
            for item in child["labels"]:
                values[int(item["class_id"])].append(
                    (
                        str(item["label"]),
                        float(item["probability"]),
                        bool(item["generic"]),
                    )
                )
        labels = [
            {
                "class_id": class_id,
                "label": entries[0][0],
                "generic": entries[0][2],
                "max_probability": _round(max(item[1] for item in entries)),
                "mean_probability": _round(
                    np.mean([item[1] for item in entries])
                ),
            }
            for class_id, entries in values.items()
        ]
        labels.sort(
            key=lambda item: (
                -item["max_probability"],
                -item["mean_probability"],
                item["class_id"],
            )
        )
        output.append(
            {
                "segment_id": segment["segment_id"],
                "source_ref": segment["source_ref"],
                "scale": "context",
                "start_us": segment["start_us"],
                "end_us": segment["end_us"],
                "modality": "ambient",
                "labels": labels[:15],
                "child_fine_ids": [item["segment_id"] for item in children],
                "searchable": bool(labels),
                "exclusion_reason": None if labels else "empty_prediction",
            }
        )
    return output


def _pool_vectors(
    cell_ids: Sequence[str], vectors: Mapping[str, np.ndarray]
) -> np.ndarray:
    items = [vectors[cell].astype(np.float32) for cell in cell_ids if cell in vectors]
    if not items:
        raise MiniPilotIndexError("VISUAL_POOL_EMPTY")
    vector = np.mean(np.stack(items), axis=0)
    norm = float(np.linalg.norm(vector))
    if not math.isfinite(norm) or norm <= 0:
        raise MiniPilotIndexError("VISUAL_POOL_NONFINITE")
    return vector / norm


def _checkpoint_key(
    source_sha256: str,
    layer_version: str,
    scale: str,
    shard_index: int,
    config_hash: str,
) -> str:
    return "/".join(
        (source_sha256, layer_version, scale, str(shard_index), config_hash)
    )


def _checkpoint_meta(
    repo_root: Path,
    path: Path,
    *,
    key: str,
    record_count: int,
    payload_hash: str,
    reused: bool = False,
) -> dict[str, Any]:
    return {
        "path": _repo_relative(repo_root, path),
        "key": key,
        "record_count": record_count,
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path, prefixed=True),
        "payload_hash": payload_hash,
        **({"reused": True} if reused else {}),
    }


def _write_checkpoint(
    repo_root: Path,
    path: Path,
    payload: Mapping[str, Any],
    *,
    key: str,
    record_count: int,
) -> dict[str, Any]:
    body = dict(payload)
    body["checkpoint_key"] = key
    body["record_count"] = record_count
    body["payload_hash"] = _json_hash(payload)
    _atomic_dump(path, body)
    return _checkpoint_meta(
        repo_root,
        path,
        key=key,
        record_count=record_count,
        payload_hash=body["payload_hash"],
    )


def _read_checkpoint(
    repo_root: Path,
    path: Path,
    *,
    key: str,
    expected_count: int,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not path.exists():
        return None, None
    try:
        body = _load(path)
        payload = {
            name: value
            for name, value in body.items()
            if name not in {"checkpoint_key", "record_count", "payload_hash"}
        }
        valid = (
            path.is_file()
            and not path.is_symlink()
            and stat.S_IMODE(path.stat().st_mode) == 0o600
            and body.get("checkpoint_key") == key
            and body.get("record_count") == expected_count
            and body.get("payload_hash") == _json_hash(payload)
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        valid = False
        payload = {}
    if not valid:
        path.unlink(missing_ok=True)
        return None, None
    return payload, _checkpoint_meta(
        repo_root,
        path,
        key=key,
        record_count=expected_count,
        payload_hash=body["payload_hash"],
        reused=True,
    )


def _records_for_source(
    segment_manifest: Mapping[str, Any], source_ref: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cells = [
        dict(item)
        for item in segment_manifest["base_cells"]
        if item["source_ref"] == source_ref
    ]
    segments = [
        dict(item)
        for item in segment_manifest["segments"]
        if item["source_ref"] == source_ref
    ]
    return cells, segments


def build_observation_manifest(
    repo_root: str | Path,
    config: IndexConfig | Mapping[str, Any],
    sources: Sequence[Mapping[str, Any]],
    segment_manifest: Mapping[str, Any],
    *,
    resume: bool = True,
    model_backend: ModelBackend | None = None,
    media_backend: MediaBackend | None = None,
    routing_extractor: Any | None = None,
    resource_manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run local frozen inference, persisting records but no decoded media."""
    root = Path(repo_root).resolve()
    source_plan_type, _ = _source_plan_types()
    cfg = (
        _config_from_source_plan(config)
        if source_plan_type is not None and isinstance(config, source_plan_type)
        else IndexConfig.from_value(config)
    )
    output_dir = _resolve_repo_path(root, cfg.output_dir)
    checkpoint_root = output_dir / "checkpoints"
    checkpoint_root.mkdir(parents=True, exist_ok=True)
    checkpoint_root.chmod(0o700)
    runtime = _configure_runtime(cfg.threads)
    models = model_backend
    media = media_backend or PyAVMediaBackend()
    config_record = {
        "threads": cfg.threads,
        "device": "cpu",
        "offline_local_only": True,
        "whisper_batch_size": cfg.whisper_batch_size,
        "ast_batch_size": cfg.ast_batch_size,
        "clip_batch_size": cfg.clip_batch_size,
        "segment_manifest_hash": segment_manifest["segment_manifest_hash"],
        "sampling": {
            "cells_s": 4,
            "fine_length_s": 8,
            "fine_stride_s": 4,
            "context_length_s": 32,
            "context_stride_s": 16,
            "whisper_chunk_s": 30,
            "audio_rate_hz": 16_000,
            "audio_channels": 1,
        },
        "model_snapshot_hashes": {
            name: item["snapshot_hash"]
            for name, item in (
                resource_manifest
                or build_resource_manifest(root, cfg, sources)
            )["models"].items()
        },
    }
    config_hash = _json_hash(config_record)
    checkpoints: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()

    face = None
    if routing_extractor is None:
        try:
            import cv2
        except Exception as exc:  # pragma: no cover
            raise MiniPilotIndexError("OPENCV_IMPORT_FAILED") from exc
        face = cv2.CascadeClassifier(
            str(_resolve_repo_path(root, cfg.haar_model_path))
        )
        if face.empty():
            raise MiniPilotIndexError("HAAR_MODEL_LOAD_FAILED")
        routing_extractor = _routing_features

    for source in sorted(sources, key=lambda item: item["source_ref"]):
        source_ref = str(source["source_ref"])
        media_path = _resolve_repo_path(root, source["media_path"])
        if (
            not media_path.is_file()
            or media_path.is_symlink()
            or media_path.stat().st_size != int(source["size_bytes"])
            or _sha256(media_path) != source["sha256"]
        ):
            raise MiniPilotIndexError(f"SOURCE_IDENTITY_MISMATCH:{source_ref}")
        cells, segments = _records_for_source(segment_manifest, source_ref)
        source_checkpoint_dir = checkpoint_root / source_ref

        routing_path = source_checkpoint_dir / "vision_routing.json"
        routing_key = _checkpoint_key(
            source["sha256"], "opencv-routing/1.0", "base", 0, config_hash
        )
        routing_payload, routing_meta = (
            _read_checkpoint(
                root,
                routing_path,
                key=routing_key,
                expected_count=len(cells),
            )
            if resume
            else (None, None)
        )
        clip_path = source_checkpoint_dir / "vision_clip.json"
        clip_key = _checkpoint_key(
            source["sha256"], "clip-visual/1.0", "base", 0, config_hash
        )
        clip_payload, clip_meta = (
            _read_checkpoint(
                root, clip_path, key=clip_key, expected_count=len(cells)
            )
            if resume
            else (None, None)
        )
        if routing_payload is None or clip_payload is None:
            routing_records: list[dict[str, Any]] = []
            vector_records: list[dict[str, Any]] = []
            image_batch: list[np.ndarray] = []
            image_cells: list[Mapping[str, Any]] = []
            previous_gray = None

            def flush_images(target_records: list[dict[str, Any]]) -> None:
                nonlocal image_batch, image_cells, models
                if not image_batch:
                    return
                if models is None:
                    models = LocalFrozenModels(root, cfg)
                vectors = models.clip_images(image_batch)
                if len(vectors) != len(image_batch):
                    raise MiniPilotIndexError("CLIP_BATCH_CARDINALITY_MISMATCH")
                for cell, vector in zip(image_cells, vectors):
                    target_records.append(
                        {
                            "cell_id": cell["cell_id"],
                            "vector_f16_hex": np.asarray(
                                vector, dtype="<f2"
                            ).tobytes().hex(),
                            "dimension": int(np.asarray(vector).shape[0]),
                            "l2_normalized": True,
                        }
                    )
                image_batch, image_cells = [], []

            for cell, rgb, pts, time_base in media.iter_sampled_frames(
                media_path, cells
            ):
                if routing_payload is None:
                    features, previous_gray = routing_extractor(
                        rgb, previous_gray, face
                    )
                    routing_records.append(
                        {
                            "cell_id": cell["cell_id"],
                            "source_ref": source_ref,
                            "sample_time_us": cell["sample_time_us"],
                            "pts": int(pts),
                            "time_base": str(time_base),
                            "features": features,
                        }
                    )
                if clip_payload is None:
                    image_batch.append(rgb)
                    image_cells.append(cell)
                    if len(image_batch) >= cfg.clip_batch_size:
                        flush_images(vector_records)
            flush_images(vector_records)
            if routing_payload is None and len(routing_records) != len(cells):
                raise MiniPilotIndexError(f"ROUTING_RECORD_COUNT_MISMATCH:{source_ref}")
            if clip_payload is None and len(vector_records) != len(cells):
                raise MiniPilotIndexError(f"VIDEO_RECORD_COUNT_MISMATCH:{source_ref}")
            if routing_payload is None:
                routing_payload = {
                    "layer_version": "opencv-routing/1.0",
                    "semantic_claim_allowed": False,
                    "records": routing_records,
                }
                routing_meta = _write_checkpoint(
                    root,
                    routing_path,
                    routing_payload,
                    key=routing_key,
                    record_count=len(routing_records),
                )
            if clip_payload is None:
                by_cell = {
                    item["cell_id"]: np.frombuffer(
                        bytes.fromhex(item["vector_f16_hex"]), dtype="<f2"
                    ).astype(np.float32)
                    for item in vector_records
                }
                segment_records = []
                for segment in segments:
                    vector = _pool_vectors(segment["binding_cell_ids"], by_cell)
                    segment_records.append(
                        {
                            "segment_id": segment["segment_id"],
                            "source_ref": source_ref,
                            "scale": segment["scale"],
                            "start_us": segment["start_us"],
                            "end_us": segment["end_us"],
                            "modality": "vision",
                            "vector_f16_hex": vector.astype("<f2").tobytes().hex(),
                            "dimension": int(vector.shape[0]),
                            "searchable": True,
                        }
                    )
                clip_payload = {
                    "layer_version": "clip-visual/1.0",
                    "cell_vectors": vector_records,
                    "segment_records": segment_records,
                }
                clip_meta = _write_checkpoint(
                    root,
                    clip_path,
                    clip_payload,
                    key=clip_key,
                    record_count=len(vector_records),
                )
        assert routing_payload is not None and routing_meta is not None
        assert clip_payload is not None and clip_meta is not None
        checkpoints.extend((routing_meta, clip_meta))
        counts["routing_cells"] += len(routing_payload["records"])
        counts["clip_cells"] += len(clip_payload["cell_vectors"])
        counts["vision_records"] += len(clip_payload["segment_records"])

        speech_path = source_checkpoint_dir / "speech.json"
        duration_us = round(float(source["duration_s"]) * 1_000_000)
        chunk_specs = [
            (
                f"speech.{source['sha256'][:12]}.{index:06d}",
                start,
                min(start + 30_000_000, duration_us),
            )
            for index, start in enumerate(range(0, duration_us, 30_000_000))
        ]
        speech_key = _checkpoint_key(
            source["sha256"],
            "whisper-tiny-en-frozen/1.0",
            "30-second",
            0,
            config_hash,
        )
        speech_payload, speech_meta = (
            _read_checkpoint(
                root,
                speech_path,
                key=speech_key,
                expected_count=len(chunk_specs),
            )
            if resume
            else (None, None)
        )
        fine_segments = [item for item in segments if item["scale"] == "fine"]
        ambient_path = source_checkpoint_dir / "ambient.json"
        ambient_key = _checkpoint_key(
            source["sha256"], "ast-audioset-frozen/1.0", "fine", 0, config_hash
        )
        ambient_payload, ambient_meta = (
            _read_checkpoint(
                root,
                ambient_path,
                key=ambient_key,
                expected_count=len(fine_segments),
            )
            if resume
            else (None, None)
        )
        if speech_payload is None or ambient_payload is None:
            audio = media.decode_audio(media_path, target_rate=16_000)
            if models is None:
                models = LocalFrozenModels(root, cfg)
            if speech_payload is None:
                chunks: list[dict[str, Any]] = []
                for offset in range(0, len(chunk_specs), cfg.whisper_batch_size):
                    batch = chunk_specs[offset : offset + cfg.whisper_batch_size]
                    inferred = models.whisper(
                        [item[0] for item in batch],
                        [
                            _slice_audio(audio, item[1], item[2])
                            for item in batch
                        ],
                    )
                    if len(inferred) != len(batch):
                        raise MiniPilotIndexError(
                            "WHISPER_BATCH_CARDINALITY_MISMATCH"
                        )
                    chunks.extend(
                        {
                            **item,
                            "source_ref": source_ref,
                            "start_us": spec[1],
                            "end_us": spec[2],
                        }
                        for spec, item in zip(batch, inferred)
                    )
                speech_payload = {
                    "layer_version": "whisper-tiny-en-frozen/1.0",
                    "chunk_duration_s": 30,
                    "chunks": chunks,
                    "records": _project_speech(chunks),
                }
                speech_meta = _write_checkpoint(
                    root,
                    speech_path,
                    speech_payload,
                    key=speech_key,
                    record_count=len(chunks),
                )
            if ambient_payload is None:
                fine_records: list[dict[str, Any]] = []
                for offset in range(0, len(fine_segments), cfg.ast_batch_size):
                    batch = fine_segments[offset : offset + cfg.ast_batch_size]
                    inferred = models.ast(
                        [
                            _slice_audio(audio, item["start_us"], item["end_us"])
                            for item in batch
                        ]
                    )
                    if len(inferred) != len(batch):
                        raise MiniPilotIndexError("AST_BATCH_CARDINALITY_MISMATCH")
                    for segment, item in zip(batch, inferred):
                        labels = [
                            {
                                **label,
                                "generic": _is_generic_audio(label["label"]),
                                "ranking_probability": _round(
                                    float(label["probability"])
                                    * (
                                        0.25
                                        if _is_generic_audio(label["label"])
                                        else 1.0
                                    )
                                ),
                            }
                            for label in item["top15"]
                        ]
                        fine_records.append(
                            {
                                "segment_id": segment["segment_id"],
                                "source_ref": source_ref,
                                "scale": "fine",
                                "start_us": segment["start_us"],
                                "end_us": segment["end_us"],
                                "modality": "ambient",
                                "labels": labels,
                                "searchable": bool(labels),
                                "exclusion_reason": (
                                    None if labels else "empty_prediction"
                                ),
                                "quality_flags": item.get("quality_flags", []),
                            }
                        )
                ambient_payload = {
                    "layer_version": "ast-audioset-frozen/1.0",
                    "records": _aggregate_ambient(fine_records, segments),
                }
                ambient_meta = _write_checkpoint(
                    root,
                    ambient_path,
                    ambient_payload,
                    key=ambient_key,
                    record_count=len(fine_records),
                )
            del audio
        assert speech_payload is not None and speech_meta is not None
        assert ambient_payload is not None and ambient_meta is not None
        checkpoints.extend((speech_meta, ambient_meta))
        counts["whisper_chunks"] += len(speech_payload["chunks"])
        counts["speech_records"] += len(speech_payload["records"])
        counts["ast_fine_calls"] += len(fine_segments)
        counts["ambient_records"] += len(ambient_payload["records"])

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "restricted": True,
        "source_count": len(sources),
        "expected_source_count": cfg.expected_source_count,
        "all_sources_complete": len(sources) == cfg.expected_source_count,
        "config": config_record,
        "config_hash": config_hash,
        "runtime": dict(models.runtime) if hasattr(models, "runtime") else runtime,
        # ``reused`` is useful to the immediate caller of _read_checkpoint but
        # is intentionally not persisted: a checkpoint-only resume must yield
        # byte-identical manifests and index hashes.
        "checkpoints": sorted(
            (
                {key: value for key, value in item.items() if key != "reused"}
                for item in checkpoints
            ),
            key=lambda item: item["path"],
        ),
        "counts": dict(sorted(counts.items())),
        "complete_source_refs": sorted(item["source_ref"] for item in sources),
        "no_persisted_media_derivatives": True,
        "speech_representation": {
            "type": "non_overlapping_chunk_records",
            "chunk_duration_s": 30,
            "citation_interval": "whole_asr_chunk",
        },
        "rights_metadata_searchable": False,
    }
    manifest["observation_manifest_hash"] = _json_hash(manifest)
    return manifest


def _checkpoint_payload(
    repo_root: Path, checkpoint: Mapping[str, Any]
) -> dict[str, Any]:
    path = _resolve_repo_path(repo_root, checkpoint["path"])
    if (
        not path.is_file()
        or path.is_symlink()
        or stat.S_IMODE(path.stat().st_mode) != 0o600
        or _sha256(path, prefixed=True) != checkpoint.get("sha256")
        or path.stat().st_size != checkpoint.get("size_bytes")
    ):
        raise MiniPilotIndexError(f"CHECKPOINT_IDENTITY_MISMATCH:{checkpoint['path']}")
    body = _load(path)
    payload = {
        key: value
        for key, value in body.items()
        if key not in {"checkpoint_key", "record_count", "payload_hash"}
    }
    if (
        body.get("checkpoint_key") != checkpoint.get("key")
        or body.get("record_count") != checkpoint.get("record_count")
        or body.get("payload_hash") != checkpoint.get("payload_hash")
        or body.get("payload_hash") != _json_hash(payload)
    ):
        raise MiniPilotIndexError(
            f"CHECKPOINT_PAYLOAD_MISMATCH:{checkpoint['path']}"
        )
    return payload


def _load_observation_records(
    repo_root: Path, observation_manifest: Mapping[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = {
        "speech": [],
        "ambient": [],
        "vision": [],
        "routing": [],
    }
    for checkpoint in observation_manifest["checkpoints"]:
        path = str(checkpoint["path"])
        payload = _checkpoint_payload(repo_root, checkpoint)
        if path.endswith("/speech.json"):
            output["speech"].extend(payload["records"])
        elif path.endswith("/ambient.json"):
            output["ambient"].extend(payload["records"])
        elif path.endswith("/vision_clip.json"):
            output["vision"].extend(payload["segment_records"])
        elif path.endswith("/vision_routing.json"):
            output["routing"].extend(payload["records"])
    return output


def _assert_search_record_safe(record: Mapping[str, Any]) -> None:
    stack: list[tuple[Any, str | None]] = [(record, None)]
    vocabulary_maps = {"term_frequency", "document_frequency"}
    while stack:
        value, parent_key = stack.pop()
        if isinstance(value, Mapping):
            for key, child in value.items():
                if parent_key not in vocabulary_maps and key in FORBIDDEN_SEARCH_KEYS:
                    raise MiniPilotIndexError(f"FORBIDDEN_SEARCH_FIELD:{key}")
                stack.append((child, str(key)))
        elif isinstance(value, list):
            stack.extend((child, parent_key) for child in value)


def _binding_cells(
    record: Mapping[str, Any],
    cells_by_source: Mapping[str, Sequence[Mapping[str, Any]]],
    segment_cells: Mapping[str, Sequence[str]],
) -> list[str]:
    exact = segment_cells.get(str(record["segment_id"]))
    if exact is not None:
        return list(exact)
    return [
        str(cell["cell_id"])
        for cell in cells_by_source.get(str(record["source_ref"]), ())
        if cell["start_us"] < record["end_us"]
        and cell["end_us"] > record["start_us"]
    ]


def _bm25_payload(
    records: Sequence[Mapping[str, Any]],
    source_hashes: Mapping[str, str],
    cells_by_source: Mapping[str, Sequence[Mapping[str, Any]]],
    segment_cells: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    documents_tokens = [_tokens(str(record.get("text", ""))) for record in records]
    document_frequency: Counter[str] = Counter()
    for tokens in documents_tokens:
        document_frequency.update(set(tokens))
    payload = {
        "kind": "bm25",
        "parameters": {"k1": 1.2, "b": 0.75},
        "document_count": len(records),
        "average_document_length": _round(
            np.mean([len(tokens) for tokens in documents_tokens])
            if documents_tokens
            else 0.0
        ),
        "document_frequency": dict(sorted(document_frequency.items())),
        "documents": [
            {
                "record_id": record["speech_record_id"],
                "segment_id": record["segment_id"],
                "source_ref": record["source_ref"],
                "source_sha256": source_hashes[record["source_ref"]],
                "scale": record["scale"],
                "start_us": record["start_us"],
                "end_us": record["end_us"],
                "modality": "speech",
                "binding_cell_ids": _binding_cells(
                    record, cells_by_source, segment_cells
                ),
                "search_payload": {
                    "tokens": tokens,
                    "term_frequency": dict(sorted(Counter(tokens).items())),
                    "derived_from_chunk_ids": record["derived_from_chunk_ids"],
                },
                "searchable": bool(record["searchable"]),
                "exclusion_reason": record.get("exclusion_reason"),
            }
            for record, tokens in zip(records, documents_tokens)
        ],
    }
    return payload


def _ambient_index_payload(
    records: Sequence[Mapping[str, Any]],
    source_hashes: Mapping[str, str],
    cells_by_source: Mapping[str, Sequence[Mapping[str, Any]]],
    segment_cells: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    documents = []
    for record in records:
        features = []
        for item in record["labels"]:
            probability = item.get(
                "ranking_probability",
                item.get("max_probability", item.get("probability", 0.0)),
            )
            generic = bool(item["generic"])
            if record["scale"] == "context":
                probability = (
                    float(item["max_probability"])
                    + float(item["mean_probability"])
                ) / 2
                if generic:
                    probability *= 0.25
            features.append(
                {
                    "class_id": int(item["class_id"]),
                    "class_name": item["label"],
                    "tokens": _tokens(item["label"]),
                    "weight": _round(probability),
                    "generic": generic,
                }
            )
        documents.append(
            {
                "record_id": f"ambient.{record['segment_id']}",
                "segment_id": record["segment_id"],
                "source_ref": record["source_ref"],
                "source_sha256": source_hashes[record["source_ref"]],
                "scale": record["scale"],
                "start_us": record["start_us"],
                "end_us": record["end_us"],
                "modality": "ambient",
                "binding_cell_ids": _binding_cells(
                    record, cells_by_source, segment_cells
                ),
                "search_payload": {"features": features},
                "searchable": bool(record["searchable"]),
                "exclusion_reason": record.get("exclusion_reason"),
            }
        )
    return {"kind": "weighted_sparse_labels", "documents": documents}


def _vision_index_payload(
    records: Sequence[Mapping[str, Any]],
    source_hashes: Mapping[str, str],
    cells_by_source: Mapping[str, Sequence[Mapping[str, Any]]],
    segment_cells: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    dimensions = {int(record["dimension"]) for record in records}
    if len(dimensions) > 1:
        raise MiniPilotIndexError("VISION_DIMENSION_MISMATCH")
    return {
        "kind": "normalized_float16_vectors",
        "metric": "cosine_via_dot_product",
        "dimension": next(iter(dimensions), 0),
        "documents": [
            {
                "record_id": f"vision.{record['segment_id']}",
                "segment_id": record["segment_id"],
                "source_ref": record["source_ref"],
                "source_sha256": source_hashes[record["source_ref"]],
                "scale": record["scale"],
                "start_us": record["start_us"],
                "end_us": record["end_us"],
                "modality": "vision",
                "binding_cell_ids": _binding_cells(
                    record, cells_by_source, segment_cells
                ),
                "search_payload": {
                    "vector_f16_hex": record["vector_f16_hex"],
                    "dimension": record["dimension"],
                },
                "searchable": bool(record["searchable"]),
                "exclusion_reason": record.get("exclusion_reason"),
            }
            for record in records
        ],
    }


def build_full_timeline_index(
    repo_root: str | Path,
    segment_manifest: Mapping[str, Any],
    observation_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    if not observation_manifest.get("all_sources_complete"):
        raise MiniPilotIndexError("OBSERVATION_BUILD_INCOMPLETE")
    records = _load_observation_records(root, observation_manifest)
    source_hashes = {
        item["source_ref"]: item["sha256"] for item in segment_manifest["sources"]
    }
    cells_by_source: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for cell in segment_manifest["base_cells"]:
        cells_by_source[cell["source_ref"]].append(cell)
    segment_cells = {
        item["segment_id"]: item["binding_cell_ids"]
        for item in segment_manifest["segments"]
    }
    modalities = {
        "speech": _bm25_payload(
            records["speech"], source_hashes, cells_by_source, segment_cells
        ),
        "ambient": _ambient_index_payload(
            records["ambient"], source_hashes, cells_by_source, segment_cells
        ),
        "vision": _vision_index_payload(
            records["vision"], source_hashes, cells_by_source, segment_cells
        ),
    }
    for modality in modalities.values():
        for record in modality["documents"]:
            _assert_search_record_safe(record)
    index = {
        "schema_version": SCHEMA_VERSION,
        "index_version": INDEX_VERSION,
        "stage": STAGE,
        "restricted": True,
        "source_count": segment_manifest["source_count"],
        "source_hashes": source_hashes,
        "segment_manifest_hash": segment_manifest["segment_manifest_hash"],
        "observation_manifest_hash": observation_manifest[
            "observation_manifest_hash"
        ],
        "rankers": {
            "speech": "bm25(k1=1.2,b=0.75)",
            "ambient": "weighted_sparse_label_cosine",
            "vision": "normalized_clip_cosine",
            "fusion": "rrf(k=60,4s_temporal_deduplication)",
        },
        "searchable_field_policy": {
            "forbidden_keys": sorted(FORBIDDEN_SEARCH_KEYS),
            "rights_metadata_excluded": True,
            "evaluator_annotations_excluded": True,
        },
        "modalities": modalities,
        "counts": {
            "speech_records": len(modalities["speech"]["documents"]),
            "ambient_records": len(modalities["ambient"]["documents"]),
            "vision_records": len(modalities["vision"]["documents"]),
        },
    }
    index["index_hash"] = _json_hash(index)
    return index


def _scope_filter(
    documents: Sequence[Mapping[str, Any]],
    source_ref: str | None,
    time_range: Sequence[float] | None,
) -> list[Mapping[str, Any]]:
    interval = (
        (
            round(float(time_range[0]) * 1_000_000),
            round(float(time_range[1]) * 1_000_000),
        )
        if time_range is not None
        else None
    )
    return [
        item
        for item in documents
        if item.get("searchable")
        and (source_ref is None or item["source_ref"] == source_ref)
        and (
            interval is None
            or item["start_us"] < interval[1]
            and item["end_us"] > interval[0]
        )
    ]


def _pointer(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "result_type": "segment_pointer",
        "result_id": "ptr."
        + hashlib.sha256(
            f"{record['segment_id']}:{record['modality']}".encode()
        ).hexdigest()[:16],
        "segment_id": record["segment_id"],
        "source_ref": record["source_ref"],
        "interval": {
            "start_s": _round(record["start_us"] / 1_000_000, 6),
            "end_s": _round(record["end_us"] / 1_000_000, 6),
        },
        "start_us": record["start_us"],
        "end_us": record["end_us"],
        "modality": record["modality"],
        "scale": record["scale"],
        "generic_preview": f"{record['modality']} {record['scale']} observation",
    }


def _rank_tie(record: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        record["source_ref"],
        record["start_us"],
        record["end_us"],
        record["segment_id"],
        record["modality"],
    )


def search_speech(
    index: Mapping[str, Any],
    query: str,
    *,
    top_k: int,
    source_ref: str | None = None,
    exclude_ids: Iterable[str] = (),
    time_range: Sequence[float] | None = None,
) -> list[dict[str, Any]]:
    modality = index["modalities"]["speech"]
    documents = _scope_filter(modality["documents"], source_ref, time_range)
    excluded = set(exclude_ids)
    n_documents = max(1, int(modality["document_count"]))
    average_length = max(1e-12, float(modality["average_document_length"]))
    scored = []
    for document in documents:
        if document["segment_id"] in excluded:
            continue
        score = 0.0
        payload = document["search_payload"]
        length = max(1, len(payload["tokens"]))
        for token in _tokens(query):
            frequency = payload["term_frequency"].get(token, 0)
            if not frequency:
                continue
            document_frequency = modality["document_frequency"].get(token, 0)
            inverse = math.log(
                1.0
                + (n_documents - document_frequency + 0.5)
                / (document_frequency + 0.5)
            )
            score += inverse * (frequency * 2.2) / (
                frequency
                + 1.2 * (1 - 0.75 + 0.75 * length / average_length)
            )
        if score > 0:
            scored.append({**_pointer(document), "score": _round(score)})
    scored.sort(key=lambda item: (-item["score"], *_rank_tie(item)))
    return scored[:top_k]


def search_ambient(
    index: Mapping[str, Any],
    query: str,
    *,
    top_k: int,
    source_ref: str | None = None,
    exclude_ids: Iterable[str] = (),
    time_range: Sequence[float] | None = None,
) -> list[dict[str, Any]]:
    documents = _scope_filter(
        index["modalities"]["ambient"]["documents"], source_ref, time_range
    )
    excluded = set(exclude_ids)
    query_tokens = set(_tokens(query))
    expanded = set(query_tokens)
    for token in query_tokens:
        expanded.update(AMBIENT_SYNONYMS.get(token, ()))
    query_norm = math.sqrt(max(1, len(expanded)))
    scored = []
    for document in documents:
        if document["segment_id"] in excluded:
            continue
        numerator = 0.0
        norm = 0.0
        for feature in document["search_payload"]["features"]:
            weight = float(feature["weight"])
            norm += weight * weight
            overlap = expanded.intersection(feature["tokens"])
            numerator += weight * len(overlap)
        score = numerator / (query_norm * math.sqrt(norm)) if numerator and norm else 0
        if score > 0:
            scored.append({**_pointer(document), "score": _round(score)})
    scored.sort(key=lambda item: (-item["score"], *_rank_tie(item)))
    return scored[:top_k]


def _decode_vector(record: Mapping[str, Any]) -> np.ndarray:
    payload = record["search_payload"]
    return np.frombuffer(
        bytes.fromhex(payload["vector_f16_hex"]), dtype="<f2"
    ).astype(np.float32)


def search_visual(
    index: Mapping[str, Any],
    query: str,
    *,
    top_k: int,
    text_vector: np.ndarray | None = None,
    model_backend: ModelBackend | None = None,
    source_ref: str | None = None,
    exclude_ids: Iterable[str] = (),
    time_range: Sequence[float] | None = None,
) -> list[dict[str, Any]]:
    if text_vector is None:
        if model_backend is None:
            raise MiniPilotIndexError("TEXT_VECTOR_OR_MODEL_BACKEND_REQUIRED")
        text_vector = model_backend.clip_text([query])[0]
    query_vector = np.asarray(text_vector, dtype=np.float32)
    norm = float(np.linalg.norm(query_vector))
    if not math.isfinite(norm) or norm <= 0:
        raise MiniPilotIndexError("QUERY_VECTOR_INVALID")
    query_vector = query_vector / norm
    documents = _scope_filter(
        index["modalities"]["vision"]["documents"], source_ref, time_range
    )
    excluded = set(exclude_ids)
    scored = []
    for document in documents:
        if document["segment_id"] in excluded:
            continue
        vector = _decode_vector(document)
        if vector.shape != query_vector.shape:
            raise MiniPilotIndexError("QUERY_VECTOR_DIMENSION_MISMATCH")
        scored.append(
            {
                **_pointer(document),
                "score": _round(np.dot(query_vector, vector)),
            }
        )
    scored.sort(key=lambda item: (-item["score"], *_rank_tie(item)))
    return scored[:top_k]


def search_fused(
    rankings: Mapping[str, Sequence[Mapping[str, Any]]], *, top_k: int
) -> list[dict[str, Any]]:
    scores: dict[tuple[str, int, int], float] = defaultdict(float)
    representatives: dict[tuple[str, int, int], dict[str, Any]] = {}
    modalities: dict[tuple[str, int, int], set[str]] = defaultdict(set)
    for modality, ranking in sorted(rankings.items()):
        for rank, result in enumerate(ranking, 1):
            key = (
                str(result["source_ref"]),
                int(result["start_us"] // 4_000_000),
                int((result["end_us"] - 1) // 4_000_000),
            )
            scores[key] += 1.0 / (60 + rank)
            modalities[key].add(modality)
            current = representatives.get(key)
            if current is None or _rank_tie(result) < _rank_tie(current):
                representatives[key] = dict(result)
    output = []
    for key, score in scores.items():
        item = dict(representatives[key])
        item["score"] = _round(score)
        item["fused_modalities"] = sorted(modalities[key])
        output.append(item)
    output.sort(key=lambda item: (-item["score"], *_rank_tie(item)))
    return output[:top_k]


def _artifact_record(repo_root: Path, path: Path) -> dict[str, Any]:
    return {
        "path": _repo_relative(repo_root, path),
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path, prefixed=True),
    }


def build_mini_pilot_index(
    repo_root: str | Path,
    config: IndexConfig | Mapping[str, Any] | str | Path | None = None,
    *,
    resume: bool = True,
    model_backend: ModelBackend | None = None,
    media_backend: MediaBackend | None = None,
    routing_extractor: Any | None = None,
    threads: int | None = None,
    device: str = "cpu",
    smoke_seconds: float | None = None,
) -> dict[str, Any]:
    """Build only segment, observation, index, resource, and build manifests."""
    root = Path(repo_root).resolve()
    if device != "cpu":
        raise MiniPilotIndexError("DEVICE_NOT_SUPPORTED:cpu")
    if smoke_seconds is not None and smoke_seconds <= 0:
        raise MiniPilotIndexError("SMOKE_SECONDS_MUST_BE_POSITIVE")
    source_plan_type, load_source_plan = _source_plan_types()
    source_plan = None
    if source_plan_type is not None and isinstance(config, source_plan_type):
        source_plan = config
    elif config is None and load_source_plan is not None:
        source_plan = load_source_plan(root)
    elif isinstance(config, (str, Path)):
        candidate = _resolve_repo_path(root, config)
        try:
            document = _load(candidate)
        except (OSError, json.JSONDecodeError):
            document = None
        if (
            load_source_plan is not None
            and isinstance(document, Mapping)
            and document.get("schema_version")
            == "av-trace.mini-pilot-full-timeline-plan/1.0"
        ):
            source_plan = load_source_plan(root, plan_path=candidate)
    cfg = (
        _config_from_source_plan(source_plan)
        if source_plan is not None
        else IndexConfig.from_value(config)
    )
    if threads is not None:
        cfg = replace(cfg, threads=threads)
    output_dir = _resolve_repo_path(root, cfg.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir.chmod(0o700)
    unexpected = [
        path.name
        for path in output_dir.iterdir()
        if path.is_file()
        and any(term in path.name.casefold() for term in PROHIBITED_ARTIFACT_TERMS)
    ]
    if unexpected:
        raise MiniPilotIndexError(
            "PROHIBITED_OUTPUT_ARTIFACT_PRESENT:" + ",".join(sorted(unexpected))
        )
    sources = (
        _sources_from_source_plan(source_plan)
        if source_plan is not None
        else load_sources(
            root,
            cfg.source_manifest_paths,
            expected_source_count=cfg.expected_source_count,
        )
    )
    if smoke_seconds is not None:
        sources = [
            {
                **source,
                "duration_s": min(float(source["duration_s"]), smoke_seconds),
                "expected_counts": {},
            }
            for source in sources
        ]
    segment_manifest = build_segment_manifest(root, sources)
    segment_path = output_dir / "segment_manifest.json"
    _atomic_dump(segment_path, segment_manifest)

    resource_manifest = build_resource_manifest(root, cfg, sources)
    resource_path = output_dir / "resource_manifest.json"
    _atomic_dump(resource_path, resource_manifest)

    observation_manifest = build_observation_manifest(
        root,
        cfg,
        sources,
        segment_manifest,
        resume=resume,
        model_backend=model_backend,
        media_backend=media_backend,
        routing_extractor=routing_extractor,
        resource_manifest=resource_manifest,
    )
    observation_path = output_dir / "observation_manifest.json"
    _atomic_dump(observation_path, observation_manifest)

    index = build_full_timeline_index(root, segment_manifest, observation_manifest)
    index_path = output_dir / "full_timeline_index.json"
    _atomic_dump(index_path, index)

    artifact_paths = [
        segment_path,
        observation_path,
        index_path,
        resource_path,
    ]
    build_manifest = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "status": "COMPLETE",
        "source_count": len(sources),
        "expected_source_count": cfg.expected_source_count,
        "output_dir": _repo_relative(root, output_dir),
        "completed_stages": [
            "segment_manifest",
            "observation_manifest",
            "full_timeline_index",
            "resource_manifest",
        ],
        "terminal_boundary": {
            "last_allowed_stage": "resource_manifest",
            "families_generated": False,
            "negatives_generated": False,
            "interventions_generated": False,
            "trajectories_generated": False,
            "evaluation_generated": False,
        },
        "artifacts": [_artifact_record(root, path) for path in artifact_paths],
        "checkpoint_count": len(observation_manifest["checkpoints"]),
        "no_persisted_media_derivatives": True,
        "smoke_seconds": smoke_seconds,
    }
    media_suffixes = {
        ".aac",
        ".avi",
        ".flac",
        ".gif",
        ".jpeg",
        ".jpg",
        ".m4a",
        ".m4v",
        ".mkv",
        ".mov",
        ".mp3",
        ".mp4",
        ".ogg",
        ".png",
        ".wav",
        ".webm",
    }
    persisted_media = [
        _repo_relative(root, path)
        for path in output_dir.rglob("*")
        if path.is_file() and path.suffix.casefold() in media_suffixes
    ]
    if persisted_media:
        raise MiniPilotIndexError(
            "PERSISTED_MEDIA_DERIVATIVE:" + ",".join(sorted(persisted_media))
        )
    hard_cap_mib = cfg.derived_artifacts_hard_fail_cap_mib
    build_path = output_dir / "build_manifest.json"
    derived_bytes = sum(
        path.stat().st_size
        for path in output_dir.rglob("*")
        if path.is_file() and path != build_path
    )
    if hard_cap_mib is not None and derived_bytes > int(hard_cap_mib) * 1024 * 1024:
        raise MiniPilotIndexError("DERIVED_ARTIFACT_HARD_CAP_EXCEEDED")
    build_manifest["derived_artifact_bytes_before_build_manifest"] = derived_bytes
    build_manifest["derived_artifact_hard_cap_mib"] = hard_cap_mib
    build_manifest["build_manifest_hash"] = _json_hash(build_manifest)
    _atomic_dump(build_path, build_manifest)
    return {
        "segment_manifest": segment_manifest,
        "observation_manifest": observation_manifest,
        "full_timeline_index": index,
        "resource_manifest": resource_manifest,
        "build_manifest": build_manifest,
    }


def build_observations(
    repo_root: str | Path,
    plan_or_config: Any,
    segment_manifest: Mapping[str, Any],
    **kwargs: Any,
) -> dict[str, Any]:
    """Scale-1A-shaped wrapper that accepts a Workstream-A ``SourcePlan``."""
    source_plan_type, _ = _source_plan_types()
    if source_plan_type is not None and isinstance(plan_or_config, source_plan_type):
        config = _config_from_source_plan(plan_or_config)
        sources = _sources_from_source_plan(plan_or_config)
        resource = build_resource_manifest(repo_root, plan_or_config, sources)
    else:
        config = IndexConfig.from_value(plan_or_config)
        sources = load_sources(
            repo_root,
            config.source_manifest_paths,
            expected_source_count=config.expected_source_count,
        )
        resource = build_resource_manifest(repo_root, config, sources)
    return build_observation_manifest(
        repo_root,
        config,
        sources,
        segment_manifest,
        resource_manifest=resource,
        **kwargs,
    )


def build_index(
    repo_root: str | Path,
    plan_or_segment_manifest: Mapping[str, Any] | Any,
    segment_or_observation_manifest: Mapping[str, Any],
    observation_manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Accept both compact and Scale-1A-shaped build-index signatures."""
    if observation_manifest is None:
        segment_manifest = plan_or_segment_manifest
        observations = segment_or_observation_manifest
    else:
        segment_manifest = segment_or_observation_manifest
        observations = observation_manifest
    return build_full_timeline_index(repo_root, segment_manifest, observations)


build_mini_pilot = build_mini_pilot_index
