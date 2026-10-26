#!/usr/bin/env python3
"""Local-only manual review app for the restricted NOAA-01 pilot.

The application streams bytes from three allowlisted source MP4 files. It does
not decode media and never writes clips, frames, audio, thumbnails, waveforms,
or transcripts. Review state and deterministic exports stay under the
restricted NOAA-01 review directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import tempfile
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit


SCHEMA_VERSION = "1.0"
PACKET_ID = "NOAA-01-MANUAL-REVIEW-PILOT-01"
LOOPBACK_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
MAX_REQUEST_BYTES = 128 * 1024
PILOT_ASSET_IDS = ("cand-049", "cand-051", "cand-052")

RESTRICTED_ROOT_REL = Path("data/restricted/noaa01")
RAW_ROOT_REL = RESTRICTED_ROOT_REL / "raw"
CANDIDATES_REL = RESTRICTED_ROOT_REL / "recon/noaa01_candidate_windows.json"
MEASUREMENTS_REL = RESTRICTED_ROOT_REL / "recon/noaa01_window_measurements.jsonl"
MEDIA_AUDIT_REL = RESTRICTED_ROOT_REL / "manifests/noaa01_media_audit.json"
REVIEW_ROOT_REL = RESTRICTED_ROOT_REL / "review"
QUEUE_REL = REVIEW_ROOT_REL / "noaa01_manual_review_queue.json"
TEMPLATE_REL = REVIEW_ROOT_REL / "noaa01_manual_review_template.json"
DECISIONS_REL = REVIEW_ROOT_REL / "noaa01_manual_review_decisions.json"
EXPORT_REL = REVIEW_ROOT_REL / "noaa01_manual_review_export.json"

# Frozen selection from the Task 80 measurement pool. The categories are
# routing hypotheses only. Human-answer fields are never populated from them.
FROZEN_SELECTION: Mapping[str, tuple[tuple[str, str], ...]] = {
    "cand-049": (
        ("cand-049-coarse-001", "combined"),
        ("cand-049-coarse-003", "speech_priority"),
        ("cand-049-coarse-005", "non_speech_priority"),
        ("cand-049-coarse-008", "visual_change"),
        ("cand-049-coarse-012", "combined"),
        ("cand-049-coarse-018", "visual_change"),
    ),
    "cand-051": (
        ("cand-051-coarse-001", "combined"),
        ("cand-051-coarse-002", "speech_priority"),
        ("cand-051-coarse-009", "speech_priority"),
        ("cand-051-adaptive-002", "non_speech_priority"),
        ("cand-051-coarse-015", "visual_change"),
        ("cand-051-coarse-018", "combined"),
    ),
    "cand-052": (
        ("cand-052-coarse-001", "combined"),
        ("cand-052-coarse-003", "visual_change"),
        ("cand-052-coarse-005", "speech_priority"),
        ("cand-052-coarse-007", "non_speech_priority"),
        ("cand-052-coarse-013", "speech_priority"),
        ("cand-052-coarse-018", "combined"),
    ),
}

TRI_STATE = {"yes", "no", "uncertain"}
SPEECH_INTELLIGIBILITY = {"yes", "no", "uncertain", "not_applicable"}
NON_SPEECH_TYPES = {
    "music",
    "environmental",
    "demonstration",
    "interface",
    "applause",
    "other",
    "uncertain",
}
VISUAL_TYPES = {
    "slide",
    "chart",
    "text",
    "talking-head",
    "field-footage",
    "demonstration",
    "animation",
    "other",
    "uncertain",
}
MODALITY_ROLES = {"V", "S", "A", "V+S", "V+A", "S+A", "V+S+A", "none", "uncertain"}
NECESSITY_VALUES = {
    "potentially_necessary",
    "merely_co_occurring",
    "not_selected",
    "uncertain",
}
INTERVAL_STATUSES = {"keep", "adjust", "uncertain", "not_applicable"}
DISPOSITIONS = {"accept", "reject", "defer"}
CONFIDENCE_VALUES = {"low", "medium", "high", "uncertain"}
ROUTING_HYPOTHESES = {
    "speech_priority",
    "non_speech_priority",
    "visual_change",
    "combined",
}


class ReviewError(RuntimeError):
    """Fail-closed packet or review-state error."""


@dataclass(frozen=True)
class AppContext:
    repo_root: Path
    queue: Mapping[str, Any]
    template: Mapping[str, Any]
    media_paths: Mapping[str, Path]
    decisions_path: Path
    export_path: Path

    @property
    def windows_by_id(self) -> dict[str, Mapping[str, Any]]:
        return {str(item["review_id"]): item for item in self.queue["windows"]}


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def atomic_write_json(path: Path, value: Any) -> None:
    """Write restricted JSON atomically with owner-only permissions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(canonical_json_bytes(value))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        path.chmod(0o600)
    finally:
        temporary_path.unlink(missing_ok=True)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReviewError(f"INVALID_JSON:{path.as_posix()}") from exc


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReviewError(f"INVALID_JSONL:{path.as_posix()}") from exc


def file_identity(path: Path, repo_root: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as handle:
            while block := handle.read(1024 * 1024):
                size += len(block)
                digest.update(block)
    except OSError as exc:
        raise ReviewError(f"UNREADABLE_INPUT:{path.as_posix()}") from exc
    return {
        "path": path.relative_to(repo_root).as_posix(),
        "size_bytes": size,
        "sha256": digest.hexdigest(),
    }


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ReviewError(f"MALFORMED_{label}")
    return value


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ReviewError(f"MALFORMED_{label}")
    return value


def _safe_media_path(repo_root: Path, path_text: str, basename: str) -> Path:
    expected = RAW_ROOT_REL / basename
    if Path(path_text) != expected:
        raise ReviewError(f"MEDIA_PATH_NOT_EXACT_ALLOWLIST:{basename}")
    path = repo_root / expected
    raw_root = (repo_root / RAW_ROOT_REL).resolve()
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ReviewError(f"MISSING_MEDIA:{basename}") from exc
    if path.is_symlink() or not path.is_file() or resolved.parent != raw_root:
        raise ReviewError(f"UNSAFE_MEDIA_PATH:{basename}")
    return path


def load_authoritative_sources(
    repo_root: Path,
) -> tuple[dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]], dict[str, Any]]:
    candidate_doc = _mapping(load_json(repo_root / CANDIDATES_REL), "CANDIDATES")
    measurements = load_jsonl(repo_root / MEASUREMENTS_REL)
    audit = _mapping(load_json(repo_root / MEDIA_AUDIT_REL), "MEDIA_AUDIT")

    candidate_by_measurement_window = {
        str(item["candidate_window_id"]): _mapping(item, "CANDIDATE")
        for item in _list(candidate_doc.get("candidates"), "CANDIDATE_LIST")
    }
    measurement_by_id = {
        str(item["measurement_id"]): _mapping(item, "MEASUREMENT")
        for item in measurements
    }
    audit_by_id = {
        str(item["candidate_id"]): _mapping(item, "AUDIT_MEDIA_ITEM")
        for item in _list(audit.get("media"), "AUDIT_MEDIA")
    }
    if set(PILOT_ASSET_IDS) - set(audit_by_id):
        raise ReviewError("PILOT_ASSET_MISSING_FROM_AUDIT")

    # Map Task 80 shortlist entries to their exact source measurement when one
    # exists. This is provenance only and does not import any answer.
    shortlist_by_signature: dict[tuple[str, float, float], str] = {}
    for window_id, candidate in candidate_by_measurement_window.items():
        signature = (
            str(candidate.get("video_id")),
            float(candidate.get("start_seconds")),
            float(candidate.get("end_seconds")),
        )
        shortlist_by_signature[signature] = window_id
    return measurement_by_id, audit_by_id, shortlist_by_signature


def build_queue(repo_root: Path) -> dict[str, Any]:
    measurements, audit_by_id, shortlist = load_authoritative_sources(repo_root)
    windows: list[dict[str, Any]] = []
    media_assets: list[dict[str, Any]] = []
    position = 0
    for candidate_id in PILOT_ASSET_IDS:
        audited = audit_by_id[candidate_id]
        if not all(
            audited.get(key) is True
            for key in (
                "technical_audit_pass",
                "actual_decode_pass",
                "declared_audiovisual_pass",
                "timeline_plausibility_pass",
            )
        ):
            raise ReviewError(f"AUDIT_NOT_PASSING:{candidate_id}")
        basename = str(audited.get("basename"))
        media_path = _safe_media_path(
            repo_root, str(audited.get("path")), basename
        )
        media_assets.append(
            {
                "candidate_id": candidate_id,
                "basename": basename,
                "duration_seconds": float(
                    _mapping(audited.get("container"), "AUDIT_CONTAINER").get(
                        "duration_seconds"
                    )
                ),
                "size_bytes": media_path.stat().st_size,
            }
        )
        previous_end = -1.0
        for measurement_id, hypothesis in FROZEN_SELECTION[candidate_id]:
            position += 1
            measurement = measurements.get(measurement_id)
            if measurement is None:
                raise ReviewError(f"FROZEN_MEASUREMENT_MISSING:{measurement_id}")
            if str(measurement.get("candidate_id")) != candidate_id:
                raise ReviewError(f"FROZEN_MEASUREMENT_ASSET_MISMATCH:{measurement_id}")
            start = float(measurement.get("start_seconds"))
            end = float(measurement.get("end_seconds"))
            if start < 0 or end <= start or start < previous_end:
                raise ReviewError(f"INVALID_FROZEN_INTERVAL:{measurement_id}")
            previous_end = end
            signature = (candidate_id, start, end)
            inferences = _mapping(measurement.get("inferences"), "INFERENCES")
            windows.append(
                {
                    "review_id": f"noaa01-review-{position:03d}",
                    "queue_position": position,
                    "candidate_id": candidate_id,
                    "basename": basename,
                    "media_route": f"/media/{candidate_id}",
                    "start_seconds": start,
                    "end_seconds": end,
                    "source_measurement_id": measurement_id,
                    "source_task80_candidate_window_id": shortlist.get(signature),
                    "routing_hypothesis": hypothesis,
                    "routing_signals": {
                        "candidate_modality_families": list(
                            measurement.get("candidate_modality_families", [])
                        ),
                        "speech_score": float(inferences.get("speech_score")),
                        "non_speech_audio_score": float(
                            inferences.get("non_speech_audio_score")
                        ),
                        "visual_change_score": float(
                            inferences.get("visual_change_score")
                        ),
                    },
                    "routing_only_not_human_judgment": True,
                }
            )

    counts = {
        hypothesis: sum(
            item["routing_hypothesis"] == hypothesis for item in windows
        )
        for hypothesis in sorted(ROUTING_HYPOTHESES)
    }
    inputs = [
        file_identity(repo_root / relative, repo_root)
        for relative in (CANDIDATES_REL, MEASUREMENTS_REL, MEDIA_AUDIT_REL)
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "packet_id": PACKET_ID,
        "status": "UNREVIEWED_ROUTING_QUEUE",
        "restricted": True,
        "human_answers_prefilled": False,
        "task80_labels_are_routing_hypotheses_only": True,
        "persistent_media_derivatives_allowed": False,
        "pilot_asset_ids": list(PILOT_ASSET_IDS),
        "queue_count": len(windows),
        "per_asset_count": {
            candidate_id: sum(
                item["candidate_id"] == candidate_id for item in windows
            )
            for candidate_id in PILOT_ASSET_IDS
        },
        "routing_hypothesis_counts": counts,
        "selection_policy": {
            "target": "six temporally separated windows per pilot asset",
            "minimum_gap_seconds_within_asset": 100.0,
            "near_duplicate_policy": (
                "No selected intervals overlap; adjacent adaptive neighbors were excluded."
            ),
            "balance_requirements": sorted(ROUTING_HYPOTHESES),
            "randomness": "none",
        },
        "inputs": inputs,
        "media_assets": media_assets,
        "windows": windows,
    }


def blank_judgment() -> dict[str, Any]:
    return {
        "media_loads_and_seeks_correctly": None,
        "speech_present": None,
        "speech_intelligible": None,
        "non_speech_audio_present": None,
        "non_speech_audio_type": None,
        "meaningful_visual_information": None,
        "visual_type": None,
        "plausible_question_evidence_seed": "",
        "candidate_modality_role": None,
        "modality_necessity": {
            "V": None,
            "S": None,
            "A": None,
        },
        "evidence_interval_adjustment": {
            "status": None,
            "adjusted_start_seconds": None,
            "adjusted_end_seconds": None,
        },
        "sensitive_distressing_private_content": None,
        "disposition": None,
        "reviewer_confidence": None,
        "reviewer_notes": "",
    }


def build_template(queue: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "packet_id": PACKET_ID,
        "status": "UNFILLED",
        "human_answers_prefilled": False,
        "reviewer_id": None,
        "records": [
            {
                "review_id": item["review_id"],
                "candidate_id": item["candidate_id"],
                "source_measurement_id": item["source_measurement_id"],
                "judgment": blank_judgment(),
            }
            for item in queue["windows"]
        ],
    }


def build_packet(repo_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    queue = build_queue(repo_root)
    template = build_template(queue)
    atomic_write_json(repo_root / QUEUE_REL, queue)
    atomic_write_json(repo_root / TEMPLATE_REL, template)
    return queue, template


def _nullable_enum(value: Any, allowed: set[str], label: str) -> None:
    if value is not None and value not in allowed:
        raise ReviewError(f"INVALID_{label}")


def validate_judgment(
    judgment: Any, window: Mapping[str, Any], *, allow_partial: bool = True
) -> dict[str, Any]:
    value = dict(_mapping(judgment, "JUDGMENT"))
    expected_keys = set(blank_judgment())
    if set(value) != expected_keys:
        raise ReviewError("JUDGMENT_FIELDS_MISMATCH")
    for key in (
        "media_loads_and_seeks_correctly",
        "speech_present",
        "non_speech_audio_present",
        "meaningful_visual_information",
        "sensitive_distressing_private_content",
    ):
        _nullable_enum(value[key], TRI_STATE, key.upper())
    _nullable_enum(
        value["speech_intelligible"],
        SPEECH_INTELLIGIBILITY,
        "SPEECH_INTELLIGIBLE",
    )
    _nullable_enum(
        value["non_speech_audio_type"],
        NON_SPEECH_TYPES,
        "NON_SPEECH_AUDIO_TYPE",
    )
    _nullable_enum(value["visual_type"], VISUAL_TYPES, "VISUAL_TYPE")
    _nullable_enum(
        value["candidate_modality_role"], MODALITY_ROLES, "CANDIDATE_MODALITY_ROLE"
    )
    _nullable_enum(value["disposition"], DISPOSITIONS, "DISPOSITION")
    _nullable_enum(
        value["reviewer_confidence"], CONFIDENCE_VALUES, "REVIEWER_CONFIDENCE"
    )
    for key in ("plausible_question_evidence_seed", "reviewer_notes"):
        if not isinstance(value[key], str) or len(value[key]) > 10_000:
            raise ReviewError(f"INVALID_{key.upper()}")

    necessity = dict(_mapping(value["modality_necessity"], "MODALITY_NECESSITY"))
    if set(necessity) != {"V", "S", "A"}:
        raise ReviewError("MODALITY_NECESSITY_FIELDS_MISMATCH")
    for modality, assessment in necessity.items():
        _nullable_enum(
            assessment, NECESSITY_VALUES, f"MODALITY_NECESSITY_{modality}"
        )
    value["modality_necessity"] = necessity

    interval = dict(
        _mapping(
            value["evidence_interval_adjustment"], "EVIDENCE_INTERVAL_ADJUSTMENT"
        )
    )
    if set(interval) != {
        "status",
        "adjusted_start_seconds",
        "adjusted_end_seconds",
    }:
        raise ReviewError("INTERVAL_ADJUSTMENT_FIELDS_MISMATCH")
    _nullable_enum(interval["status"], INTERVAL_STATUSES, "INTERVAL_STATUS")
    adjusted_start = interval["adjusted_start_seconds"]
    adjusted_end = interval["adjusted_end_seconds"]
    if interval["status"] == "adjust":
        if not isinstance(adjusted_start, (int, float)) or isinstance(
            adjusted_start, bool
        ):
            raise ReviewError("INVALID_ADJUSTED_START")
        if not isinstance(adjusted_end, (int, float)) or isinstance(
            adjusted_end, bool
        ):
            raise ReviewError("INVALID_ADJUSTED_END")
        duration = float(window["asset_duration_seconds"])
        if not 0 <= float(adjusted_start) < float(adjusted_end) <= duration:
            raise ReviewError("ADJUSTED_INTERVAL_OUT_OF_BOUNDS")
        interval["adjusted_start_seconds"] = float(adjusted_start)
        interval["adjusted_end_seconds"] = float(adjusted_end)
    elif adjusted_start is not None or adjusted_end is not None:
        raise ReviewError("ADJUSTED_INTERVAL_REQUIRES_ADJUST_STATUS")
    value["evidence_interval_adjustment"] = interval

    if not allow_partial and any(
        value[key] is None
        for key in (
            "media_loads_and_seeks_correctly",
            "speech_present",
            "speech_intelligible",
            "non_speech_audio_present",
            "non_speech_audio_type",
            "meaningful_visual_information",
            "visual_type",
            "candidate_modality_role",
            "sensitive_distressing_private_content",
            "disposition",
            "reviewer_confidence",
        )
    ):
        raise ReviewError("INCOMPLETE_JUDGMENT")
    return value


def _queue_with_durations(queue: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    durations = {
        item["candidate_id"]: float(item["duration_seconds"])
        for item in queue["media_assets"]
    }
    return {
        item["review_id"]: {**item, "asset_duration_seconds": durations[item["candidate_id"]]}
        for item in queue["windows"]
    }


def validate_packet(
    repo_root: Path, queue: Mapping[str, Any], template: Mapping[str, Any]
) -> dict[str, Any]:
    expected_queue = build_queue(repo_root)
    if canonical_json_bytes(queue) != canonical_json_bytes(expected_queue):
        raise ReviewError("QUEUE_DOES_NOT_MATCH_DETERMINISTIC_BUILD")
    expected_template = build_template(expected_queue)
    if canonical_json_bytes(template) != canonical_json_bytes(expected_template):
        raise ReviewError("TEMPLATE_IS_NOT_UNFILLED_OR_DETERMINISTIC")
    if queue.get("queue_count") not in range(15, 19):
        raise ReviewError("QUEUE_COUNT_OUT_OF_RANGE")
    if set(queue.get("routing_hypothesis_counts", {})) != ROUTING_HYPOTHESES:
        raise ReviewError("ROUTING_HYPOTHESIS_COVERAGE_FAILED")
    if any(queue["per_asset_count"].get(item) not in {5, 6} for item in PILOT_ASSET_IDS):
        raise ReviewError("PER_ASSET_BALANCE_FAILED")

    for candidate_id in PILOT_ASSET_IDS:
        selected = [
            item for item in queue["windows"] if item["candidate_id"] == candidate_id
        ]
        for left, right in zip(selected, selected[1:]):
            if float(right["start_seconds"]) - float(left["end_seconds"]) < 100.0:
                raise ReviewError(f"TEMPORAL_SEPARATION_FAILED:{candidate_id}")
    return {
        "status": "VALID",
        "packet_id": PACKET_ID,
        "queue_count": queue["queue_count"],
        "per_asset_count": queue["per_asset_count"],
        "routing_hypothesis_counts": queue["routing_hypothesis_counts"],
        "listener_started": False,
        "persistent_media_derivatives_created": False,
    }


def load_context(repo_root: Path) -> AppContext:
    queue = _mapping(load_json(repo_root / QUEUE_REL), "QUEUE")
    template = _mapping(load_json(repo_root / TEMPLATE_REL), "TEMPLATE")
    validate_packet(repo_root, queue, template)
    media_paths: dict[str, Path] = {}
    for item in queue["media_assets"]:
        candidate_id = str(item["candidate_id"])
        if candidate_id not in PILOT_ASSET_IDS:
            raise ReviewError("NON_PILOT_ASSET_IN_QUEUE")
        media_paths[candidate_id] = _safe_media_path(
            repo_root,
            (RAW_ROOT_REL / str(item["basename"])).as_posix(),
            str(item["basename"]),
        )
    return AppContext(
        repo_root=repo_root,
        queue=queue,
        template=template,
        media_paths=media_paths,
        decisions_path=repo_root / DECISIONS_REL,
        export_path=repo_root / EXPORT_REL,
    )


def initial_state(context: AppContext) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "packet_id": PACKET_ID,
        "reviewer_id": None,
        "records": list(context.template["records"]),
    }


def validate_state(context: AppContext, state: Any) -> dict[str, Any]:
    value = dict(_mapping(state, "STATE"))
    if value.get("schema_version") != SCHEMA_VERSION or value.get("packet_id") != PACKET_ID:
        raise ReviewError("STATE_PACKET_MISMATCH")
    reviewer_id = value.get("reviewer_id")
    if reviewer_id is not None and (
        not isinstance(reviewer_id, str) or len(reviewer_id) > 200
    ):
        raise ReviewError("INVALID_REVIEWER_ID")
    records = _list(value.get("records"), "STATE_RECORDS")
    windows = _queue_with_durations(context.queue)
    if [item.get("review_id") for item in records] != list(windows):
        raise ReviewError("STATE_RECORD_ORDER_MISMATCH")
    clean_records = []
    for record in records:
        item = _mapping(record, "STATE_RECORD")
        review_id = str(item.get("review_id"))
        window = windows[review_id]
        if (
            item.get("candidate_id") != window["candidate_id"]
            or item.get("source_measurement_id") != window["source_measurement_id"]
        ):
            raise ReviewError("STATE_RECORD_IDENTITY_MISMATCH")
        clean_records.append(
            {
                "review_id": review_id,
                "candidate_id": window["candidate_id"],
                "source_measurement_id": window["source_measurement_id"],
                "judgment": validate_judgment(item.get("judgment"), window),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "packet_id": PACKET_ID,
        "reviewer_id": reviewer_id,
        "records": clean_records,
    }


def load_state(context: AppContext) -> dict[str, Any]:
    if not context.decisions_path.exists():
        return initial_state(context)
    return validate_state(context, load_json(context.decisions_path))


def save_record(
    context: AppContext,
    review_id: str,
    judgment: Any,
    reviewer_id: Any,
) -> dict[str, Any]:
    windows = _queue_with_durations(context.queue)
    if review_id not in windows:
        raise ReviewError("UNKNOWN_REVIEW_ID")
    if reviewer_id is not None and (
        not isinstance(reviewer_id, str) or len(reviewer_id) > 200
    ):
        raise ReviewError("INVALID_REVIEWER_ID")
    clean = validate_judgment(judgment, windows[review_id])
    state = load_state(context)
    state["reviewer_id"] = reviewer_id
    for record in state["records"]:
        if record["review_id"] == review_id:
            record["judgment"] = clean
            break
    atomic_write_json(context.decisions_path, state)
    return state


def record_is_complete(judgment: Mapping[str, Any]) -> bool:
    required = (
        "media_loads_and_seeks_correctly",
        "speech_present",
        "speech_intelligible",
        "non_speech_audio_present",
        "non_speech_audio_type",
        "meaningful_visual_information",
        "visual_type",
        "candidate_modality_role",
        "sensitive_distressing_private_content",
        "disposition",
        "reviewer_confidence",
    )
    if any(judgment.get(key) is None for key in required):
        return False
    necessity = _mapping(judgment.get("modality_necessity"), "MODALITY_NECESSITY")
    if any(necessity.get(key) is None for key in ("V", "S", "A")):
        return False
    interval = _mapping(
        judgment.get("evidence_interval_adjustment"), "INTERVAL_ADJUSTMENT"
    )
    return interval.get("status") is not None


def deterministic_export(context: AppContext) -> dict[str, Any]:
    state = load_state(context)
    windows = context.windows_by_id
    records = []
    for record in state["records"]:
        window = windows[record["review_id"]]
        records.append(
            {
                "review_id": record["review_id"],
                "queue_position": window["queue_position"],
                "candidate_id": window["candidate_id"],
                "basename": window["basename"],
                "source_measurement_id": window["source_measurement_id"],
                "source_task80_candidate_window_id": window[
                    "source_task80_candidate_window_id"
                ],
                "review_interval": {
                    "start_seconds": window["start_seconds"],
                    "end_seconds": window["end_seconds"],
                },
                "routing_hypothesis": window["routing_hypothesis"],
                "routing_only_not_human_judgment": True,
                "complete": record_is_complete(record["judgment"]),
                "judgment": record["judgment"],
            }
        )
    export = {
        "schema_version": SCHEMA_VERSION,
        "packet_id": PACKET_ID,
        "restricted": True,
        "reviewer_id": state["reviewer_id"],
        "record_count": len(records),
        "completed_count": sum(item["complete"] for item in records),
        "records": records,
    }
    atomic_write_json(context.export_path, export)
    return export


def parse_byte_range(header: str | None, size: int) -> tuple[int, int, bool]:
    """Return inclusive start/end and whether this is a partial response."""
    if not header:
        return 0, size - 1, False
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", header.strip())
    if not match or "," in header:
        raise ReviewError("INVALID_RANGE")
    first, last = match.groups()
    if not first and not last:
        raise ReviewError("INVALID_RANGE")
    if not first:
        suffix = int(last)
        if suffix <= 0:
            raise ReviewError("INVALID_RANGE")
        start = max(0, size - suffix)
        end = size - 1
    else:
        start = int(first)
        end = int(last) if last else size - 1
        if start >= size:
            raise ReviewError("RANGE_NOT_SATISFIABLE")
        end = min(end, size - 1)
        if end < start:
            raise ReviewError("INVALID_RANGE")
    return start, end, True


def host_header_is_loopback(host: str) -> bool:
    hostname = host.rsplit(":", 1)[0].strip("[]").lower()
    return hostname in {LOOPBACK_HOST, "localhost"}


def iter_file_range(
    path: Path, start: int, end: int, *, chunk_size: int = 1024 * 1024
):
    """Yield an inclusive byte range without creating a media derivative."""
    with path.open("rb") as handle:
        handle.seek(start)
        remaining = end - start + 1
        while remaining:
            block = handle.read(min(chunk_size, remaining))
            if not block:
                break
            yield block
            remaining -= len(block)


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>NOAA-01 restricted manual review</title>
<style>
body{font-family:system-ui,sans-serif;margin:0;background:#eef2f5;color:#17212b}
header{background:#17324d;color:white;padding:12px 20px} main{max-width:1180px;margin:auto;padding:16px}
.notice{background:#fff4cc;border:1px solid #d5a400;padding:10px;margin-bottom:12px}
.layout{display:grid;grid-template-columns:1.2fr 1fr;gap:16px}.panel{background:white;padding:14px;border-radius:6px}
video{width:100%;background:#111;max-height:58vh}label{display:block;margin:9px 0 3px;font-weight:600}
select,input,textarea,button{font:inherit}select,input,textarea{width:100%;box-sizing:border-box;padding:6px}
textarea{min-height:62px}.row{display:grid;grid-template-columns:1fr 1fr;gap:9px}
.necessity{display:grid;grid-template-columns:repeat(3,1fr);gap:7px}.buttons{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
button{padding:8px 12px}.status{padding:7px;margin-top:8px;background:#edf7ed}
.meta{font-family:ui-monospace,monospace;font-size:.9em}.routing{color:#744b00}
@media(max-width:850px){.layout{grid-template-columns:1fr}}
</style>
</head>
<body>
<header><strong>NOAA-01 restricted manual review</strong></header>
<main>
<div class="notice"><strong>Restricted local workflow.</strong> Task 80 labels are routing hypotheses only. Make independent judgments. No media derivative is created.</div>
<div class="layout">
<section class="panel">
  <label for="window">Review window</label><select id="window"></select>
  <p id="meta" class="meta"></p><p id="routing" class="routing"></p>
  <video id="video" controls controlsList="nodownload noremoteplayback" disablePictureInPicture preload="metadata"></video>
  <div class="buttons"><button id="seek">Seek to interval start</button><button id="replay">Replay interval</button></div>
</section>
<section class="panel">
  <label>Reviewer ID (optional)</label><input id="reviewer_id">
  <div id="form"></div>
  <div class="buttons"><button id="save">Save / resume</button><button id="prev">Previous</button><button id="next">Next</button><button id="export">Export JSON</button></div>
  <div id="status" class="status">Loading…</div>
</section>
</div>
</main>
<script>
"use strict";
const tri=["","yes","no","uncertain"], fields=[
["media_loads_and_seeks_correctly","Media loads and seeks correctly",tri],
["speech_present","Speech present",tri],
["speech_intelligible","Speech intelligible",["","yes","no","uncertain","not_applicable"]],
["non_speech_audio_present","Non-speech audio present",tri],
["non_speech_audio_type","Non-speech audio type",["","music","environmental","demonstration","interface","applause","other","uncertain"]],
["meaningful_visual_information","Meaningful visual information",tri],
["visual_type","Visual type",["","slide","chart","text","talking-head","field-footage","demonstration","animation","other","uncertain"]],
["candidate_modality_role","Candidate modality role",["","V","S","A","V+S","V+A","S+A","V+S+A","none","uncertain"]],
["sensitive_distressing_private_content","Sensitive / distressing / private content",tri],
["disposition","Decision",["","accept","reject","defer"]],
["reviewer_confidence","Reviewer confidence",["","low","medium","high","uncertain"]]
];
let queue,state,index=0,stopAt=null;
const $=id=>document.getElementById(id), option=v=>`<option value="${v}">${v||"— select —"}</option>`;
function buildForm(){
 let html=fields.map(([id,label,vals])=>`<label>${label}</label><select id="${id}">${vals.map(option).join("")}</select>`).join("");
 html+=`<label>Plausible question/evidence seed</label><textarea id="plausible_question_evidence_seed"></textarea>
 <label>Modality necessity (selected modality: potentially necessary or merely co-occurring)</label><div class="necessity">${["V","S","A"].map(m=>`<div><label>${m}</label><select id="need_${m}">${["","potentially_necessary","merely_co_occurring","not_selected","uncertain"].map(option).join("")}</select></div>`).join("")}</div>
 <label>Evidence interval adjustment</label><select id="interval_status">${["","keep","adjust","uncertain","not_applicable"].map(option).join("")}</select>
 <div class="row"><div><label>Adjusted start (seconds)</label><input id="adjusted_start" type="number" step="0.001"></div><div><label>Adjusted end (seconds)</label><input id="adjusted_end" type="number" step="0.001"></div></div>
 <label>Reviewer notes</label><textarea id="reviewer_notes"></textarea>`;
 $("form").innerHTML=html;
}
function currentRecord(){return state.records[index]}
function setStatus(text){$("status").textContent=text}
function render(){
 const w=queue.windows[index],j=currentRecord().judgment;
 $("window").value=String(index); $("meta").textContent=`${w.review_id} · ${w.candidate_id} · ${w.start_seconds.toFixed(3)}–${w.end_seconds.toFixed(3)} s`;
 $("routing").textContent=`Routing hypothesis only: ${w.routing_hypothesis}. Do not copy it into the answer.`;
 const v=$("video"); stopAt=w.end_seconds;
 if(v.dataset.asset!==w.candidate_id){v.dataset.asset=w.candidate_id;v.src=w.media_route;v.load()}
 else {v.currentTime=w.start_seconds}
 fields.forEach(([id])=>$(id).value=j[id]??"");
 $("plausible_question_evidence_seed").value=j.plausible_question_evidence_seed;
 ["V","S","A"].forEach(m=>$("need_"+m).value=j.modality_necessity[m]??"");
 $("interval_status").value=j.evidence_interval_adjustment.status??"";
 $("adjusted_start").value=j.evidence_interval_adjustment.adjusted_start_seconds??"";
 $("adjusted_end").value=j.evidence_interval_adjustment.adjusted_end_seconds??"";
 $("reviewer_notes").value=j.reviewer_notes;
 setStatus(`Window ${index+1} of ${queue.windows.length}`);
}
function readForm(){
 const j={};fields.forEach(([id])=>j[id]=$(id).value||null);
 j.plausible_question_evidence_seed=$("plausible_question_evidence_seed").value;
 j.modality_necessity={};["V","S","A"].forEach(m=>j.modality_necessity[m]=$("need_"+m).value||null);
 const num=id=>$(id).value===""?null:Number($(id).value);
 j.evidence_interval_adjustment={status:$("interval_status").value||null,adjusted_start_seconds:num("adjusted_start"),adjusted_end_seconds:num("adjusted_end")};
 j.reviewer_notes=$("reviewer_notes").value;return j;
}
async function save(){
 const id=queue.windows[index].review_id;
 const r=await fetch(`/api/decisions/${id}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({reviewer_id:$("reviewer_id").value||null,judgment:readForm()})});
 const data=await r.json();if(!r.ok)throw Error(data.error||"save failed");state=data;setStatus(`Saved ${id}`);
}
async function init(){
 buildForm();[queue,state]=await Promise.all([fetch("/api/queue").then(r=>r.json()),fetch("/api/state").then(r=>r.json())]);
 $("reviewer_id").value=state.reviewer_id??"";
 $("window").innerHTML=queue.windows.map((w,i)=>`<option value="${i}">${i+1}. ${w.candidate_id} · ${w.routing_hypothesis}</option>`).join("");
 $("window").onchange=()=>{index=Number($("window").value);render()};
 $("video").onloadedmetadata=()=>{$("video").currentTime=queue.windows[index].start_seconds};
 $("video").ontimeupdate=()=>{if(stopAt!==null&&$("video").currentTime>=stopAt)$("video").pause()};
 $("seek").onclick=()=>{$("video").currentTime=queue.windows[index].start_seconds};
 $("replay").onclick=()=>{$("video").currentTime=queue.windows[index].start_seconds;$("video").play()};
 $("save").onclick=()=>save().catch(e=>setStatus(e.message));
 $("prev").onclick=()=>{index=Math.max(0,index-1);render()};
 $("next").onclick=()=>{index=Math.min(queue.windows.length-1,index+1);render()};
 $("export").onclick=async()=>{try{await save();const r=await fetch("/api/export",{method:"POST"}),d=await r.json();if(!r.ok)throw Error(d.error);setStatus(`Exported ${d.completed_count}/${d.record_count} completed records`) }catch(e){setStatus(e.message)}};
 render();
}
init().catch(e=>setStatus(e.message));
</script>
</body></html>
"""


class ReviewRequestHandler(BaseHTTPRequestHandler):
    server_version = "NOAAReview/1.0"
    context: AppContext

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")

    def _security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; media-src 'self'; connect-src 'self'; "
            "img-src 'none'; object-src 'none'; frame-ancestors 'none'; "
            "style-src 'unsafe-inline'; script-src 'unsafe-inline'",
        )
        self.send_header("Cache-Control", "no-store")

    def _send_bytes(
        self, status: HTTPStatus, payload: bytes, content_type: str
    ) -> None:
        self.send_response(status)
        self._security_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _send_json(self, status: HTTPStatus, value: Any) -> None:
        self._send_bytes(status, canonical_json_bytes(value), "application/json; charset=utf-8")

    def _reject_bad_host(self) -> bool:
        host = self.headers.get("Host", "")
        if not host_header_is_loopback(host):
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "LOOPBACK_HOST_REQUIRED"})
            return True
        return False

    def _reject_bad_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return False
        parsed = urlsplit(origin)
        expected = f"http://{self.headers.get('Host', '').lower()}"
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {LOOPBACK_HOST, "localhost"}
            or origin.lower().rstrip("/") != expected
        ):
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "LOOPBACK_ORIGIN_REQUIRED"})
            return True
        return False

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        if self._reject_bad_host():
            return
        path = urlsplit(self.path).path
        if path == "/":
            self._send_bytes(
                HTTPStatus.OK, INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8"
            )
        elif path == "/api/queue":
            self._send_json(HTTPStatus.OK, self.context.queue)
        elif path == "/api/state":
            try:
                self._send_json(HTTPStatus.OK, load_state(self.context))
            except ReviewError as exc:
                self._send_json(HTTPStatus.CONFLICT, {"error": str(exc)})
        elif path.startswith("/media/"):
            self._serve_media(path.removeprefix("/media/"))
        else:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "NOT_FOUND"})

    def do_POST(self) -> None:
        if self._reject_bad_host() or self._reject_bad_origin():
            return
        path = urlsplit(self.path).path
        try:
            if path.startswith("/api/decisions/"):
                review_id = path.removeprefix("/api/decisions/")
                body = self._read_json_body()
                state = save_record(
                    self.context,
                    review_id,
                    body.get("judgment"),
                    body.get("reviewer_id"),
                )
                self._send_json(HTTPStatus.OK, state)
            elif path == "/api/export":
                self._send_json(HTTPStatus.OK, deterministic_export(self.context))
            else:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "NOT_FOUND"})
        except ReviewError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def _read_json_body(self) -> Mapping[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ReviewError("INVALID_CONTENT_LENGTH") from exc
        if length <= 0 or length > MAX_REQUEST_BYTES:
            raise ReviewError("REQUEST_SIZE_REJECTED")
        try:
            value = json.loads(self.rfile.read(length))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ReviewError("INVALID_REQUEST_JSON") from exc
        return _mapping(value, "REQUEST")

    def _serve_media(self, candidate_id: str) -> None:
        if candidate_id not in PILOT_ASSET_IDS or candidate_id not in self.context.media_paths:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "MEDIA_NOT_ALLOWLISTED"})
            return
        path = self.context.media_paths[candidate_id]
        size = path.stat().st_size
        try:
            start, end, partial = parse_byte_range(self.headers.get("Range"), size)
        except ReviewError:
            self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            self._security_headers()
            self.send_header("Content-Range", f"bytes */{size}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(HTTPStatus.PARTIAL_CONTENT if partial else HTTPStatus.OK)
        self._security_headers()
        self.send_header("Accept-Ranges", "bytes")
        self.send_header(
            "Content-Type", mimetypes.guess_type(path.name)[0] or "video/mp4"
        )
        self.send_header("Content-Length", str(end - start + 1))
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if self.command == "HEAD":
            return
        for block in iter_file_range(path, start, end):
            self.wfile.write(block)


def create_server(context: AppContext, port: int) -> ThreadingHTTPServer:
    handler = type(
        "BoundReviewRequestHandler",
        (ReviewRequestHandler,),
        {"context": context},
    )
    server = ThreadingHTTPServer((LOOPBACK_HOST, port), handler)
    server.daemon_threads = True
    return server


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the packet and media allowlist without starting a listener.",
    )
    parser.add_argument(
        "--rebuild-packet",
        action="store_true",
        help="Deterministically rebuild the restricted queue and blank template.",
    )
    parser.add_argument(
        "--export",
        action="store_true",
        help="Write the deterministic restricted export and exit.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = args.repo_root.resolve()
    try:
        if args.rebuild_packet:
            build_packet(repo_root)
        context = load_context(repo_root)
        validation = validate_packet(repo_root, context.queue, context.template)
        if args.dry_run:
            print(json.dumps(validation, indent=2, sort_keys=True))
            return 0
        if args.export:
            export = deterministic_export(context)
            print(
                json.dumps(
                    {
                        "export_path": context.export_path.relative_to(repo_root).as_posix(),
                        "record_count": export["record_count"],
                        "completed_count": export["completed_count"],
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if not 1 <= args.port <= 65535:
            raise ReviewError("INVALID_PORT")
        server = create_server(context, args.port)
        print(f"Restricted NOAA-01 review app: http://{LOOPBACK_HOST}:{server.server_port}/")
        print("Listener is bound to 127.0.0.1 only. Press Ctrl-C to stop.")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
    except ReviewError as exc:
        print(f"ERROR:{exc}", file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
