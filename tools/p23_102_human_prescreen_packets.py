#!/usr/bin/env python3
"""Build and validate neutral P23_102 human-prescreen packets.

The tool reads only the repaired candidate registry and the verified timeline
index. It does not open media, semantic annotations, or any human review data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

READY = "P23_102_HUMAN_PRESCREEN_PACKETS_READY"
REPAIR = "P23_102_HUMAN_PRESCREEN_PACKETS_REPAIR"
IMPORT_VALID = "P23_102_HUMAN_PRESCREEN_IMPORT_VALID"

CREATED_DATE = "2026-10-14"
SOURCE_ID = "P23_102"
SOURCE_GROUP_ID = "P23"
PACKET_ID = "p23-102-human-prescreen-v1"
LEDGER_ID = "p23-source-exposure-ledger-v1"

REGISTRY_PATH = Path(
    "data/restricted/epic_p23_102_family_mining_v1_dev/"
    "candidate_registry.json"
)
INDEX_ROOT = Path("data/restricted/epic_p23_102_full_timeline_index_v1")
OUTPUT_ROOT = Path(
    "data/rehearsal_plan/p23_102_human_prescreen_packets_v1"
)
INDEX_FILES = (
    "segment_manifest.json",
    "observation_manifest.json",
    "full_timeline_index.json",
    "resource_manifest.json",
    "checkpoint_manifest.json",
    "build_manifest.json",
)

CHECK_NAMES = (
    "recurrence",
    "substitution",
    "ocr_text",
    "duplicate",
    "source_world_audio",
    "far_coherence",
    "alternative_route",
)
CHECK_OPTIONS = (
    "OBSERVED",
    "NOT_OBSERVED",
    "UNCERTAIN",
    "NOT_APPLICABLE",
)
PRESCREEN_CHOICES = (
    "RETAIN_FOR_AUTHORING",
    "REPAIR_AND_RECHECK",
    "REJECT",
)
CHECK_PROMPTS = {
    "recurrence": (
        "Check whether the same or a materially similar event recurs elsewhere "
        "in the source."
    ),
    "substitution": (
        "Check whether another available modality or a simpler cue could "
        "replace the proposed route."
    ),
    "ocr_text": (
        "Check whether visible text, labels, displays, or OCR-readable content "
        "supplies an easier route."
    ),
    "duplicate": (
        "Check whether this lead duplicates another reviewed lead or repeats "
        "the same underlying source event."
    ),
    "source_world_audio": (
        "Check whether synchronized non-speech audio carries a concrete "
        "source-world event rather than incidental recording noise."
    ),
    "far_coherence": (
        "When separated intervals are supplied, check whether they form one "
        "coherent source-world route; otherwise use NOT_APPLICABLE."
    ),
    "alternative_route": (
        "Check the source for a shorter, clearer, or modality-substituting "
        "route to the same source-world fact."
    ),
}

FORBIDDEN_SURFACE_PATTERNS = (
    r"\bmachine[ _-]?provisional\b",
    r"\bstatus(?:es)?\b",
    r"_status\b",
    r"\bstructural[ _-]?scores?\b",
    r"\bscores?\b",
    r"\bthresholds?\b",
    r"\branks?\b",
    r"\bquotas?\b",
    r"\banswer[ _-]?keys?\b",
    r"\banswer[ _-]?templates?\b",
    r"\binterventions?\b",
    r"\bcontrol[ _-]?arm\b",
    r"\brestoration[ _-]?arm\b",
    r"\bprivate[ _-]?labels?\b",
    r"\bnear_local\b",
    r"\bcoherent_far_multi_hop\b",
    r"\bv\+a\b",
    r"\baccepted_ses\b",
    r"\bh_tier\b",
    r"\bgate_a\b",
    r"\bgate a\b",
    r"\bses\b",
)
IDENTITY_KEYS = {
    "reviewer",
    "reviewer_id",
    "reviewer_name",
    "annotator",
    "annotator_id",
    "worker_id",
    "user_id",
    "person_id",
    "email",
    "phone",
}
CONTACT_PATTERN = re.compile(
    r"(?:[\w.+-]+@[\w.-]+\.[A-Za-z]{2,})|"
    r"(?:\+\d[\d ()-]{7,}\d)|"
    r"(?:\b\d{3}[- )]\d{3}[- ]\d{4}\b)"
)


class PrescreenPacketError(ValueError):
    """Raised when packet construction or validation fails closed."""


def repo_root_default() -> Path:
    return Path(__file__).resolve().parents[1]


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def object_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def bytes_hash(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def file_hash(path: Path) -> str:
    return bytes_hash(path.read_bytes())


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PrescreenPacketError(f"CANNOT_READ_JSON:{path}") from exc


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise PrescreenPacketError(code)


def _without(value: Mapping[str, Any], field: str) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key != field}


def _verify_foreign_hash(
    value: Mapping[str, Any],
    *,
    field: str,
    code: str,
) -> None:
    _require(value.get(field) == object_hash(_without(value, field)), code)


def _seal(value: dict[str, Any], field: str) -> dict[str, Any]:
    value[field] = object_hash(value)
    return value


def _verify_seal(value: Mapping[str, Any], field: str, code: str) -> None:
    _require(value.get(field) == object_hash(_without(value, field)), code)


def _stable_suffix(*parts: str, length: int = 16) -> str:
    payload = "\x1f".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:length].upper()


def _timecode(value_us: int) -> str:
    hours, remainder = divmod(value_us, 3_600_000_000)
    minutes, remainder = divmod(remainder, 60_000_000)
    seconds, micros = divmod(remainder, 1_000_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{micros:06d}"


def _relative(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise PrescreenPacketError(f"PATH_OUTSIDE_REPOSITORY:{path}") from exc


def _resolve_repo_path(repo_root: Path, path: Path, code: str) -> Path:
    resolved = path if path.is_absolute() else repo_root / path
    _relative(repo_root, resolved)
    _require(resolved.is_file(), f"{code}_MISSING")
    _require(not resolved.is_symlink(), f"{code}_SYMLINK")
    return resolved


def _index_documents(
    index: Mapping[str, Any],
) -> dict[str, dict[str, Mapping[str, Any]]]:
    modalities = index["modalities"]
    return {
        "vision": {
            str(row["segment_id"]): row
            for row in modalities["siglip2_visual"]["documents"]
        },
        "ambient_audio": {
            str(row["segment_id"]): row
            for row in modalities["clap_audio"]["documents"]
        },
    }


def load_inputs(
    repo_root: Path,
    *,
    registry_path: Path = REGISTRY_PATH,
    index_root: Path = INDEX_ROOT,
) -> dict[str, Any]:
    """Load and validate only the authorized registry and verified index."""
    registry_file = _resolve_repo_path(
        repo_root, registry_path, "REGISTRY"
    )
    index_dir = index_root if index_root.is_absolute() else repo_root / index_root
    _relative(repo_root, index_dir)
    _require(index_dir.is_dir(), "INDEX_ROOT_MISSING")
    _require(not index_dir.is_symlink(), "INDEX_ROOT_SYMLINK")

    index_paths = {
        name: _resolve_repo_path(
            repo_root,
            index_dir / name,
            f"INDEX_{name.upper().replace('.', '_')}",
        )
        for name in INDEX_FILES
    }
    inputs = {
        "registry": load_json(registry_file),
        "segment_manifest": load_json(index_paths["segment_manifest.json"]),
        "observation_manifest": load_json(
            index_paths["observation_manifest.json"]
        ),
        "index": load_json(index_paths["full_timeline_index.json"]),
        "resource_manifest": load_json(index_paths["resource_manifest.json"]),
        "checkpoint_manifest": load_json(
            index_paths["checkpoint_manifest.json"]
        ),
        "build_manifest": load_json(index_paths["build_manifest.json"]),
        "input_files": {
            _relative(repo_root, registry_file): file_hash(registry_file),
            **{
                _relative(repo_root, path): file_hash(path)
                for path in index_paths.values()
            },
        },
    }
    validate_inputs(inputs)
    return inputs


def validate_inputs(inputs: Mapping[str, Any]) -> None:
    registry = inputs["registry"]
    index = inputs["index"]
    segment_manifest = inputs["segment_manifest"]
    observation_manifest = inputs["observation_manifest"]
    build_manifest = inputs["build_manifest"]

    _require(registry.get("source_id") == SOURCE_ID, "SOURCE_ID_INVALID")
    _require(
        registry.get("source_group_id") == SOURCE_GROUP_ID,
        "SOURCE_GROUP_INVALID",
    )
    _require(
        registry.get("repair_completion_token")
        == "EPIC_P23_102_FAMILY_MINING_REPAIR_READY",
        "REGISTRY_REPAIR_BINDING_INVALID",
    )
    _verify_foreign_hash(
        registry,
        field="registry_payload_sha256",
        code="REGISTRY_HASH_INVALID",
    )
    _require(index.get("source_ref") == SOURCE_ID, "INDEX_SOURCE_INVALID")
    _require(
        index.get("index_hash") == registry["index_bindings"]["index_hash"],
        "INDEX_HASH_BINDING_INVALID",
    )
    _require(
        segment_manifest.get("segment_manifest_hash")
        == registry["index_bindings"]["segment_manifest_hash"],
        "SEGMENT_HASH_BINDING_INVALID",
    )
    _require(
        observation_manifest.get("observation_manifest_hash")
        == registry["index_bindings"]["observation_manifest_hash"],
        "OBSERVATION_HASH_BINDING_INVALID",
    )
    _require(
        build_manifest.get("build_manifest_hash")
        == registry["index_bindings"]["build_manifest_hash"],
        "BUILD_HASH_BINDING_INVALID",
    )

    expected_hashes = {
        row["path"]: row["sha256"] for row in registry["input_bindings"]
    }
    for path, expected in expected_hashes.items():
        _require(
            inputs["input_files"].get(path) == expected,
            f"PINNED_INPUT_HASH_INVALID:{path}",
        )

    candidates = registry.get("candidates")
    _require(
        isinstance(candidates, list) and len(candidates) == 20,
        "EXPECTED_TWENTY_LEADS",
    )
    documents = _index_documents(index)
    duration_us = int(segment_manifest["duration_us"])
    candidate_ids: set[str] = set()
    for candidate in candidates:
        _verify_foreign_hash(
            candidate,
            field="candidate_payload_sha256",
            code="CANDIDATE_HASH_INVALID",
        )
        candidate_id = str(candidate.get("candidate_id", ""))
        _require(candidate_id and candidate_id not in candidate_ids, "LEAD_ID_INVALID")
        candidate_ids.add(candidate_id)
        handles = candidate.get("evidence_handles")
        _require(isinstance(handles, list) and handles, "TIMESTAMP_HANDLES_MISSING")
        seen_modalities: set[str] = set()
        for handle in handles:
            modality = str(handle.get("modality"))
            _require(
                modality in documents,
                "TIMESTAMP_HANDLE_MODALITY_INVALID",
            )
            seen_modalities.add(modality)
            record = documents[modality].get(str(handle.get("record_id")))
            _require(record is not None, "TIMESTAMP_HANDLE_UNKNOWN")
            start_us = handle.get("start_us")
            end_us = handle.get("end_us")
            _require(
                isinstance(start_us, int)
                and isinstance(end_us, int)
                and 0 <= start_us < end_us <= duration_us,
                "TIMESTAMP_HANDLE_RANGE_INVALID",
            )
            _require(
                int(record["start_us"]) == start_us
                and int(record["end_us"]) == end_us
                and bool(record.get("searchable")) is True,
                "TIMESTAMP_HANDLE_INDEX_BINDING_INVALID",
            )
            _require(
                handle.get("source_id") == SOURCE_ID
                and handle.get("source_sha256")
                == registry.get("source_sha256"),
                "TIMESTAMP_HANDLE_SOURCE_BINDING_INVALID",
            )
        _require(
            seen_modalities == {"vision", "ambient_audio"},
            "LEAD_MODALITY_SET_INVALID",
        )


def _public_lead_id(candidate_id: str) -> str:
    return (
        "P23-102-LEAD-"
        + _stable_suffix("human-prescreen-v1", candidate_id)
    )


def _public_form_id(candidate_id: str) -> str:
    return (
        "P23-102-FORM-"
        + _stable_suffix("human-prescreen-form-v1", candidate_id)
    )


def _form_filename(candidate_id: str) -> str:
    suffix = _stable_suffix(
        "human-prescreen-file-v1", candidate_id, length=20
    ).lower()
    return f"lead_forms/form-{suffix}.json"


def _timestamp_handles(
    candidate: Mapping[str, Any],
    public_lead_id: str,
) -> list[dict[str, Any]]:
    intervals: dict[tuple[int, int], set[str]] = {}
    for handle in candidate["evidence_handles"]:
        key = (int(handle["start_us"]), int(handle["end_us"]))
        intervals.setdefault(key, set()).add(str(handle["modality"]))
    return [
        {
            "timestamp_handle_id": (
                "TH-"
                + _stable_suffix(
                    public_lead_id,
                    str(start_us),
                    str(end_us),
                    length=12,
                )
            ),
            "start_us": start_us,
            "end_us": end_us,
            "start_timecode": _timecode(start_us),
            "end_timecode": _timecode(end_us),
            "available_modalities": sorted(modalities),
        }
        for (start_us, end_us), modalities in sorted(intervals.items())
    ]


def _blank_checks() -> dict[str, Any]:
    return {
        name: {
            "prompt": CHECK_PROMPTS[name],
            "options": list(CHECK_OPTIONS),
            "selection": None,
            "notes": "",
        }
        for name in CHECK_NAMES
    }


def _build_form(candidate: Mapping[str, Any]) -> dict[str, Any]:
    candidate_id = str(candidate["candidate_id"])
    lead_id = _public_lead_id(candidate_id)
    form = {
        "format_version": "1.0.0",
        "record_type": "p23_102_neutral_lead_form",
        "packet_id": PACKET_ID,
        "form_id": _public_form_id(candidate_id),
        "lead_id": lead_id,
        "source_id": SOURCE_ID,
        "source_group_id": SOURCE_GROUP_ID,
        "distribution_authorized": False,
        "source_exposure_ledger_id": LEDGER_ID,
        "timestamp_handles": _timestamp_handles(candidate, lead_id),
        "neutral_modality_hypotheses": [
            {
                "modality": "visual",
                "hypothesis": (
                    "Inspect the supplied interval or intervals for an "
                    "observable source-world change, relation, or continuity."
                ),
            },
            {
                "modality": "ambient_audio",
                "hypothesis": (
                    "Inspect synchronized non-speech audio for a concrete "
                    "source-world event without presuming that it is necessary."
                ),
            },
        ],
        "review_checks": _blank_checks(),
        "prescreen_choice": {
            "options": list(PRESCREEN_CHOICES),
            "selection": None,
        },
        "free_rationale": "",
    }
    return _seal(form, "form_sha256")


def _build_source_packet() -> dict[str, Any]:
    packet = {
        "format_version": "1.0.0",
        "record_type": "p23_102_source_prescreen_packet",
        "packet_id": PACKET_ID,
        "created_date": CREATED_DATE,
        "source_id": SOURCE_ID,
        "source_group_id": SOURCE_GROUP_ID,
        "distribution_authorized": False,
        "source_access_reference": "restricted-source://P23/P23_102",
        "lead_form_count": 20,
        "lead_form_directory": "lead_forms",
        "source_exposure_ledger": "source_exposure_ledger.json",
        "synthetic_calibration_file": "synthetic_calibration_examples.json",
        "source_group_rule": (
            "Every source derivative whose origin is P23 is recorded under "
            "the single P23 source group."
        ),
        "review_instructions": [
            (
                "Inspect only the source intervals named by each timestamp "
                "handle, expanding source context only when needed."
            ),
            (
                "Apply the same seven checks to every lead and record one "
                "prescreen choice plus a free rationale."
            ),
            (
                "Treat all modality statements as neutral inspection "
                "hypotheses, not as established findings."
            ),
            (
                "Record any source or derivative exposure in the one P23 "
                "source exposure ledger used for this packet."
            ),
            (
                "The opaque file listing has no review preference; every lead "
                "must be completed exactly once."
            ),
        ],
        "allowed_prescreen_choices": list(PRESCREEN_CHOICES),
        "required_review_checks": list(CHECK_NAMES),
        "downstream_boundary": (
            "This packet records prescreen observations only and makes no "
            "downstream acceptance, tier, or eligibility finding."
        ),
    }
    return _seal(packet, "packet_sha256")


def _build_ledger() -> dict[str, Any]:
    ledger = {
        "format_version": "1.0.0",
        "record_type": "p23_source_exposure_ledger",
        "ledger_id": LEDGER_ID,
        "source_group_id": SOURCE_GROUP_ID,
        "covered_source_ids": [SOURCE_ID],
        "distribution_authorized": False,
        "derivative_group_rule": (
            "All derivatives originating from a P23 source use source group P23."
        ),
        "events": [],
    }
    return _seal(ledger, "ledger_sha256")


def _build_calibration() -> dict[str, Any]:
    calibration = {
        "format_version": "1.0.0",
        "record_type": "synthetic_prescreen_calibration",
        "synthetic_only": True,
        "distribution_authorized": False,
        "instruction": (
            "Use these fictional scenarios only to discuss how the checks are "
            "applied. They contain no packet observations or completed choices."
        ),
        "examples": [
            {
                "example_id": "SYN-CAL-01",
                "fictional_source": "SYNTHETIC-KITCHEN-A",
                "fictional_timestamps": ["00:00:12.000000-00:00:20.000000"],
                "discussion_focus": [
                    "Distinguish a source-world sound from incidental handling.",
                    "Look for visible text that could replace the audio route.",
                    "Leave the prescreen choice open during calibration.",
                ],
            },
            {
                "example_id": "SYN-CAL-02",
                "fictional_source": "SYNTHETIC-WORKBENCH-B",
                "fictional_timestamps": [
                    "00:00:40.000000-00:00:48.000000",
                    "00:03:20.000000-00:03:28.000000",
                ],
                "discussion_focus": [
                    "Ask whether separated intervals form one coherent route.",
                    "Search for recurrence and a shorter alternative route.",
                    "Leave the prescreen choice open during calibration.",
                ],
            },
            {
                "example_id": "SYN-CAL-03",
                "fictional_source": "SYNTHETIC-STUDIO-C",
                "fictional_timestamps": ["00:01:04.000000-00:01:12.000000"],
                "discussion_focus": [
                    "Check whether camera movement mimics a source-world change.",
                    "Check duplication against other fictional leads.",
                    "Leave the prescreen choice open during calibration.",
                ],
            },
        ],
    }
    return _seal(calibration, "calibration_sha256")


def _build_readme() -> str:
    return (
        "# P23_102 human prescreen packet v1\n\n"
        "distribution_authorized=false\n\n"
        "This directory contains one source packet, twenty blank neutral lead "
        "forms, one blank P23 source exposure ledger, and fictional calibration "
        "material. The source packet defines the common review instructions. "
        "Each lead form supplies timestamp handles, neutral modality hypotheses, "
        "the seven required checks, the three allowed choices, and a free "
        "rationale field.\n\n"
        "No form contains a human identity, observation, or completed choice. "
        "All source derivatives remain in source group P23. Validate this "
        "directory with:\n\n"
        "```text\n"
        "python tools/p23_102_human_prescreen_packets.py --mode check\n"
        "```\n\n"
        "Validate a completed import with:\n\n"
        "```text\n"
        "python tools/p23_102_human_prescreen_packets.py "
        "--mode validate-import --import-path completed.json\n"
        "```\n"
    )


def _manifest(
    inputs: Mapping[str, Any],
    rendered: Mapping[str, bytes],
) -> dict[str, Any]:
    hashes = {
        path: bytes_hash(content) for path, content in sorted(rendered.items())
    }
    manifest = {
        "format_version": "1.0.0",
        "record_type": "p23_102_human_prescreen_artifact_manifest",
        "packet_id": PACKET_ID,
        "created_date": CREATED_DATE,
        "source_id": SOURCE_ID,
        "source_group_id": SOURCE_GROUP_ID,
        "distribution_authorized": False,
        "completion_token": READY,
        "input_bindings": [
            {"path": path, "sha256": digest}
            for path, digest in sorted(inputs["input_files"].items())
        ],
        "artifacts": [
            {
                "path": path,
                "sha256": hashes[path],
                "size_bytes": len(rendered[path]),
            }
            for path in sorted(rendered)
        ],
        "package_content_sha256": object_hash(hashes),
    }
    return _seal(manifest, "manifest_sha256")


def build_artifacts(inputs: Mapping[str, Any]) -> dict[str, bytes]:
    forms = [_build_form(row) for row in inputs["registry"]["candidates"]]
    forms.sort(key=lambda row: row["lead_id"])
    rendered: dict[str, bytes] = {
        "README.md": _build_readme().encode("utf-8"),
        "source_prescreen_packet.json": canonical_bytes(
            _build_source_packet()
        ),
        "source_exposure_ledger.json": canonical_bytes(_build_ledger()),
        "synthetic_calibration_examples.json": canonical_bytes(
            _build_calibration()
        ),
    }
    by_candidate = {
        _public_lead_id(str(row["candidate_id"])): str(row["candidate_id"])
        for row in inputs["registry"]["candidates"]
    }
    for form in forms:
        candidate_id = by_candidate[form["lead_id"]]
        rendered[_form_filename(candidate_id)] = canonical_bytes(form)
    rendered["artifact_manifest.json"] = canonical_bytes(
        _manifest(inputs, rendered)
    )
    validate_artifacts(rendered, inputs=inputs)
    return dict(sorted(rendered.items()))


def _json_artifacts(rendered: Mapping[str, bytes]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for path, content in rendered.items():
        if path.endswith(".json"):
            try:
                values[path] = json.loads(content)
            except json.JSONDecodeError as exc:
                raise PrescreenPacketError(f"INVALID_JSON:{path}") from exc
    return values


def _walk_keys(value: Any) -> Sequence[str]:
    keys: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            keys.append(str(key))
            keys.extend(_walk_keys(item))
    elif isinstance(value, list):
        for item in value:
            keys.extend(_walk_keys(item))
    return keys


def _audit_text(
    text: str,
    *,
    candidate_ids: Sequence[str],
    code_prefix: str,
) -> None:
    lowered = text.lower()
    for pattern in FORBIDDEN_SURFACE_PATTERNS:
        if re.search(pattern, lowered, flags=re.IGNORECASE):
            raise PrescreenPacketError(
                f"{code_prefix}_FORBIDDEN_SURFACE:{pattern}"
            )
    for candidate_id in candidate_ids:
        if candidate_id in text:
            raise PrescreenPacketError(
                f"{code_prefix}_PRIVATE_LEAD_ID_EXPOSED"
            )


def _validate_distribution_flags(value: Any, code: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key == "distribution_authorized":
                _require(item is False, code)
            _validate_distribution_flags(item, code)
    elif isinstance(value, list):
        for item in value:
            _validate_distribution_flags(item, code)


def _validate_form(form: Mapping[str, Any]) -> None:
    required = {
        "format_version",
        "record_type",
        "packet_id",
        "form_id",
        "lead_id",
        "source_id",
        "source_group_id",
        "distribution_authorized",
        "source_exposure_ledger_id",
        "timestamp_handles",
        "neutral_modality_hypotheses",
        "review_checks",
        "prescreen_choice",
        "free_rationale",
        "form_sha256",
    }
    _require(set(form) == required, "FORM_FIELDS_INVALID")
    _verify_seal(form, "form_sha256", "FORM_HASH_INVALID")
    _require(form["record_type"] == "p23_102_neutral_lead_form", "FORM_TYPE_INVALID")
    _require(form["packet_id"] == PACKET_ID, "FORM_PACKET_INVALID")
    _require(form["source_id"] == SOURCE_ID, "FORM_SOURCE_INVALID")
    _require(form["source_group_id"] == SOURCE_GROUP_ID, "FORM_GROUP_INVALID")
    _require(form["distribution_authorized"] is False, "FORM_DISTRIBUTION_INVALID")
    _require(form["source_exposure_ledger_id"] == LEDGER_ID, "FORM_LEDGER_INVALID")
    _require(
        isinstance(form["timestamp_handles"], list)
        and form["timestamp_handles"],
        "FORM_TIMESTAMPS_EMPTY",
    )
    for handle in form["timestamp_handles"]:
        _require(
            set(handle)
            == {
                "timestamp_handle_id",
                "start_us",
                "end_us",
                "start_timecode",
                "end_timecode",
                "available_modalities",
            },
            "FORM_TIMESTAMP_FIELDS_INVALID",
        )
        _require(
            isinstance(handle["start_us"], int)
            and isinstance(handle["end_us"], int)
            and 0 <= handle["start_us"] < handle["end_us"],
            "FORM_TIMESTAMP_RANGE_INVALID",
        )
        _require(
            handle["start_timecode"] == _timecode(handle["start_us"])
            and handle["end_timecode"] == _timecode(handle["end_us"]),
            "FORM_TIMECODE_INVALID",
        )
        _require(
            set(handle["available_modalities"])
            == {"vision", "ambient_audio"},
            "FORM_TIMESTAMP_MODALITIES_INVALID",
        )
    hypotheses = form["neutral_modality_hypotheses"]
    _require(
        {row["modality"] for row in hypotheses}
        == {"visual", "ambient_audio"},
        "FORM_HYPOTHESES_INVALID",
    )
    checks = form["review_checks"]
    _require(set(checks) == set(CHECK_NAMES), "FORM_CHECKS_INVALID")
    for name in CHECK_NAMES:
        row = checks[name]
        _require(
            set(row) == {"prompt", "options", "selection", "notes"},
            "FORM_CHECK_FIELDS_INVALID",
        )
        _require(row["prompt"] == CHECK_PROMPTS[name], "FORM_CHECK_PROMPT_INVALID")
        _require(tuple(row["options"]) == CHECK_OPTIONS, "FORM_CHECK_OPTIONS_INVALID")
        _require(row["selection"] is None and row["notes"] == "", "FORM_NOT_BLANK")
    choice = form["prescreen_choice"]
    _require(
        set(choice) == {"options", "selection"}
        and tuple(choice["options"]) == PRESCREEN_CHOICES
        and choice["selection"] is None,
        "FORM_CHOICE_INVALID",
    )
    _require(form["free_rationale"] == "", "FORM_RATIONALE_NOT_BLANK")


def validate_artifacts(
    rendered: Mapping[str, bytes],
    *,
    inputs: Mapping[str, Any],
) -> None:
    values = _json_artifacts(rendered)
    _require("artifact_manifest.json" in values, "MANIFEST_MISSING")
    manifest = values["artifact_manifest.json"]
    _verify_seal(manifest, "manifest_sha256", "MANIFEST_HASH_INVALID")
    _require(manifest["completion_token"] == READY, "COMPLETION_TOKEN_INVALID")
    _require(manifest["distribution_authorized"] is False, "MANIFEST_DISTRIBUTION_INVALID")

    listed = {row["path"]: row for row in manifest["artifacts"]}
    expected_non_manifest = set(rendered) - {"artifact_manifest.json"}
    _require(set(listed) == expected_non_manifest, "MANIFEST_FILE_SET_INVALID")
    for path, row in listed.items():
        content = rendered[path]
        _require(row["sha256"] == bytes_hash(content), f"FILE_HASH_INVALID:{path}")
        _require(row["size_bytes"] == len(content), f"FILE_SIZE_INVALID:{path}")
    expected_hashes = {
        path: bytes_hash(rendered[path]) for path in sorted(expected_non_manifest)
    }
    _require(
        manifest["package_content_sha256"] == object_hash(expected_hashes),
        "PACKAGE_HASH_INVALID",
    )
    _require(
        manifest["input_bindings"]
        == [
            {"path": path, "sha256": digest}
            for path, digest in sorted(inputs["input_files"].items())
        ],
        "MANIFEST_INPUT_BINDINGS_INVALID",
    )

    packet = values["source_prescreen_packet.json"]
    ledger = values["source_exposure_ledger.json"]
    calibration = values["synthetic_calibration_examples.json"]
    _verify_seal(packet, "packet_sha256", "SOURCE_PACKET_HASH_INVALID")
    _verify_seal(ledger, "ledger_sha256", "LEDGER_HASH_INVALID")
    _verify_seal(
        calibration,
        "calibration_sha256",
        "CALIBRATION_HASH_INVALID",
    )
    _require(packet["distribution_authorized"] is False, "PACKET_DISTRIBUTION_INVALID")
    _require(ledger["distribution_authorized"] is False, "LEDGER_DISTRIBUTION_INVALID")
    _require(
        calibration["distribution_authorized"] is False
        and calibration["synthetic_only"] is True,
        "CALIBRATION_BOUNDARY_INVALID",
    )
    _require(ledger["source_group_id"] == SOURCE_GROUP_ID, "LEDGER_GROUP_INVALID")
    _require(ledger["covered_source_ids"] == [SOURCE_ID], "LEDGER_SOURCE_INVALID")
    _require(ledger["events"] == [], "LEDGER_NOT_BLANK")

    form_paths = sorted(
        path for path in values if path.startswith("lead_forms/")
    )
    _require(len(form_paths) == 20, "FORM_COUNT_INVALID")
    forms = [values[path] for path in form_paths]
    for form in forms:
        _validate_form(form)
    lead_ids = [str(form["lead_id"]) for form in forms]
    form_ids = [str(form["form_id"]) for form in forms]
    _require(len(set(lead_ids)) == 20, "LEAD_IDS_NOT_UNIQUE")
    _require(len(set(form_ids)) == 20, "FORM_IDS_NOT_UNIQUE")
    expected_lead_ids = {
        _public_lead_id(str(row["candidate_id"]))
        for row in inputs["registry"]["candidates"]
    }
    _require(set(lead_ids) == expected_lead_ids, "LEAD_COVERAGE_INVALID")

    candidate_ids = [
        str(row["candidate_id"]) for row in inputs["registry"]["candidates"]
    ]
    for path, content in rendered.items():
        text = content.decode("utf-8")
        _audit_text(
            text,
            candidate_ids=candidate_ids,
            code_prefix=f"ARTIFACT:{path}",
        )
    for path, value in values.items():
        keys = {key.lower() for key in _walk_keys(value)}
        _require(
            not keys.intersection(IDENTITY_KEYS),
            f"ARTIFACT_IDENTITY_FIELD:{path}",
        )
        _validate_distribution_flags(
            value,
            f"ARTIFACT_DISTRIBUTION_TRUE:{path}",
        )


def _read_directory(output_root: Path) -> dict[str, bytes]:
    _require(output_root.is_dir(), "OUTPUT_DIRECTORY_MISSING")
    rendered: dict[str, bytes] = {}
    for path in sorted(output_root.rglob("*")):
        if path.is_file():
            _require(not path.is_symlink(), "OUTPUT_SYMLINK_FORBIDDEN")
            rendered[path.relative_to(output_root).as_posix()] = path.read_bytes()
    return rendered


def write_artifacts(output_root: Path, rendered: Mapping[str, bytes]) -> None:
    if output_root.exists():
        existing = {
            path.relative_to(output_root).as_posix()
            for path in output_root.rglob("*")
            if path.is_file()
        }
        _require(
            not existing or existing == set(rendered),
            "OUTPUT_DIRECTORY_HAS_UNEXPECTED_FILES",
        )
    output_root.mkdir(parents=True, exist_ok=True)
    output_root.chmod(0o700)
    for relative, content in rendered.items():
        path = output_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.parent.chmod(0o700)
        temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            path.chmod(0o600)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise


def check_committed(
    output_root: Path,
    *,
    inputs: Mapping[str, Any],
) -> dict[str, bytes]:
    actual = _read_directory(output_root)
    validate_artifacts(actual, inputs=inputs)
    expected = build_artifacts(inputs)
    _require(set(actual) == set(expected), "COMMITTED_FILE_SET_INVALID")
    for path in expected:
        _require(actual[path] == expected[path], f"COMMITTED_BYTES_INVALID:{path}")
    return actual


def _require_exact_fields(
    value: Mapping[str, Any],
    fields: set[str],
    code: str,
) -> None:
    _require(set(value) == fields, code)


def _validate_no_identity(value: Any) -> None:
    keys = {key.lower() for key in _walk_keys(value)}
    _require(not keys.intersection(IDENTITY_KEYS), "IMPORT_IDENTITY_FIELD")
    serialized = json.dumps(value, ensure_ascii=False)
    _require(CONTACT_PATTERN.search(serialized) is None, "IMPORT_CONTACT_DATA")


def _validate_import_ledger(ledger: Mapping[str, Any]) -> None:
    _require_exact_fields(
        ledger,
        {
            "format_version",
            "record_type",
            "ledger_id",
            "source_group_id",
            "distribution_authorized",
            "derivative_group_rule",
            "events",
            "ledger_sha256",
        },
        "IMPORT_LEDGER_FIELDS_INVALID",
    )
    _verify_seal(ledger, "ledger_sha256", "IMPORT_LEDGER_HASH_INVALID")
    _require(ledger["ledger_id"] == LEDGER_ID, "IMPORT_LEDGER_ID_INVALID")
    _require(ledger["source_group_id"] == SOURCE_GROUP_ID, "IMPORT_LEDGER_GROUP_INVALID")
    _require(ledger["distribution_authorized"] is False, "IMPORT_LEDGER_DISTRIBUTION_INVALID")
    _require(
        ledger["derivative_group_rule"]
        == "All derivatives originating from a P23 source use source group P23.",
        "IMPORT_LEDGER_RULE_INVALID",
    )
    events = ledger["events"]
    _require(isinstance(events, list) and events, "IMPORT_LEDGER_EVENTS_EMPTY")
    event_ids: set[str] = set()
    for event in events:
        _require_exact_fields(
            event,
            {
                "event_id",
                "occurred_at",
                "source_group_id",
                "source_reference",
                "derivative_reference",
                "exposure_kind",
            },
            "IMPORT_EVENT_FIELDS_INVALID",
        )
        event_id = str(event["event_id"])
        _require(event_id and event_id not in event_ids, "IMPORT_EVENT_ID_INVALID")
        event_ids.add(event_id)
        _require(
            event["source_group_id"] == SOURCE_GROUP_ID,
            "IMPORT_EVENT_GROUP_INVALID",
        )
        _require(
            str(event["source_reference"]).startswith("P23")
            and str(event["derivative_reference"]).startswith("P23"),
            "IMPORT_EVENT_DERIVATIVE_GROUP_INVALID",
        )
        _require(
            event["exposure_kind"] in {"SOURCE_REVIEW", "DERIVATIVE_REVIEW"},
            "IMPORT_EVENT_KIND_INVALID",
        )
        try:
            occurred_at = datetime.fromisoformat(str(event["occurred_at"]))
        except ValueError as exc:
            raise PrescreenPacketError("IMPORT_EVENT_TIME_INVALID") from exc
        _require(occurred_at.tzinfo is not None, "IMPORT_EVENT_TIMEZONE_MISSING")


def validate_import(
    imported: Mapping[str, Any],
    *,
    rendered: Mapping[str, bytes],
    inputs: Mapping[str, Any],
) -> None:
    """Validate a completed, identity-free import against the packet."""
    validate_artifacts(rendered, inputs=inputs)
    _validate_no_identity(imported)
    _validate_distribution_flags(imported, "IMPORT_DISTRIBUTION_TRUE")
    _require_exact_fields(
        imported,
        {
            "format_version",
            "record_type",
            "packet_id",
            "source_group_id",
            "distribution_authorized",
            "responses",
            "source_exposure_ledger",
        },
        "IMPORT_FIELDS_INVALID",
    )
    _require(
        imported["record_type"] == "p23_102_human_prescreen_import",
        "IMPORT_TYPE_INVALID",
    )
    _require(imported["packet_id"] == PACKET_ID, "IMPORT_PACKET_INVALID")
    _require(imported["source_group_id"] == SOURCE_GROUP_ID, "IMPORT_GROUP_INVALID")
    _require(imported["distribution_authorized"] is False, "IMPORT_DISTRIBUTION_INVALID")

    values = _json_artifacts(rendered)
    forms = {
        form["lead_id"]: form
        for path, form in values.items()
        if path.startswith("lead_forms/")
    }
    responses = imported["responses"]
    _require(isinstance(responses, list), "IMPORT_RESPONSES_INVALID")
    response_ids = [str(row.get("lead_id", "")) for row in responses]
    _require(len(response_ids) == 20, "IMPORT_RESPONSE_COUNT_INVALID")
    _require(len(set(response_ids)) == 20, "IMPORT_RESPONSE_IDS_DUPLICATE")
    _require(set(response_ids) == set(forms), "IMPORT_RESPONSE_COVERAGE_INVALID")

    candidate_ids = [
        str(row["candidate_id"]) for row in inputs["registry"]["candidates"]
    ]
    for response in responses:
        _require_exact_fields(
            response,
            {
                "lead_id",
                "form_sha256",
                "review_checks",
                "prescreen_choice",
                "free_rationale",
            },
            "IMPORT_RESPONSE_FIELDS_INVALID",
        )
        form = forms[response["lead_id"]]
        _require(
            response["form_sha256"] == form["form_sha256"],
            "IMPORT_FORM_HASH_INVALID",
        )
        checks = response["review_checks"]
        _require(set(checks) == set(CHECK_NAMES), "IMPORT_CHECKS_INVALID")
        for name in CHECK_NAMES:
            row = checks[name]
            _require_exact_fields(
                row,
                {"selection", "notes"},
                "IMPORT_CHECK_FIELDS_INVALID",
            )
            _require(
                row["selection"] in CHECK_OPTIONS,
                "IMPORT_CHECK_SELECTION_INVALID",
            )
            _require(isinstance(row["notes"], str), "IMPORT_CHECK_NOTES_INVALID")
        _require(
            response["prescreen_choice"] in PRESCREEN_CHOICES,
            "IMPORT_CHOICE_INVALID",
        )
        rationale = response["free_rationale"]
        _require(
            isinstance(rationale, str) and bool(rationale.strip()),
            "IMPORT_RATIONALE_REQUIRED",
        )
        _audit_text(
            json.dumps(response, ensure_ascii=False),
            candidate_ids=candidate_ids,
            code_prefix="IMPORT_RESPONSE",
        )
    _validate_import_ledger(imported["source_exposure_ledger"])


def _output_path(repo_root: Path, value: Path) -> Path:
    if value.is_absolute():
        return value
    return repo_root / value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("build", "check", "audit", "validate-import"),
        default="check",
    )
    parser.add_argument("--repo-root", type=Path, default=repo_root_default())
    parser.add_argument("--registry-path", type=Path, default=REGISTRY_PATH)
    parser.add_argument("--index-root", type=Path, default=INDEX_ROOT)
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--import-path", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        repo_root = args.repo_root.resolve()
        inputs = load_inputs(
            repo_root,
            registry_path=args.registry_path,
            index_root=args.index_root,
        )
        output_root = _output_path(repo_root, args.output_root)
        if args.mode == "build":
            rendered = build_artifacts(inputs)
            write_artifacts(output_root, rendered)
            result = {
                "completion_token": READY,
                "artifact_count": len(rendered),
                "lead_form_count": 20,
                "output_root": str(output_root),
            }
        elif args.mode in {"check", "audit"}:
            rendered = check_committed(output_root, inputs=inputs)
            result = {
                "completion_token": READY,
                "artifact_count": len(rendered),
                "lead_form_count": 20,
                "output_root": str(output_root),
            }
        else:
            _require(args.import_path is not None, "IMPORT_PATH_REQUIRED")
            import_path = _output_path(repo_root, args.import_path)
            imported = load_json(import_path)
            _require(isinstance(imported, Mapping), "IMPORT_ROOT_INVALID")
            rendered = check_committed(output_root, inputs=inputs)
            validate_import(imported, rendered=rendered, inputs=inputs)
            result = {
                "completion_token": IMPORT_VALID,
                "lead_response_count": 20,
                "source_group_id": SOURCE_GROUP_ID,
            }
        print(json.dumps(result, sort_keys=True))
        return 0
    except (KeyError, TypeError, PrescreenPacketError) as exc:
        print(
            json.dumps(
                {
                    "completion_token": REPAIR,
                    "error": str(exc),
                },
                sort_keys=True,
            )
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
