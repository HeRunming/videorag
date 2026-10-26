#!/usr/bin/env python3
"""Fail-closed semantic-stress canary over P23_102 query authoring v2.

The wrapper selects one local family that passed the successful canary-v1.5
structure plus two distinct far families.  The far choices maximize
machine-only structural risk for (a) human-vocalization/ASR ambiguity and
(b) continuity/anaphora.  Selection never reads semantic labels, retrieval
scores, retrieval outcomes, or human review.

Planning and preflight do not decode media or load models.  Execution requires
an independently created exact-input authorization receipt and reuses the
current repaired parent pipeline for constrained JSON authoring and every
semantic gate.  This module never creates authorization or runs retrieval.
"""

from __future__ import annotations

import argparse
import base64
import codecs
import contextlib
import errno
import hashlib
import importlib.util
import json
import math
import os
import re
import resource
import shutil
import stat
import sys
import tempfile
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CURRENT_DATE = "2026-10-22"
CANARY_ID = "AV-TRACE-P23-102-QUERY-AUTHORING-V2-CANARY2"
READY = "P23_102_QUERY_AUTHORING_V2_CANARY2_R22_F_IMPLEMENTATION_READY"
PLAN_SCHEMA_VERSION = (
    "av-trace.p23-102-query-authoring-v2-canary2-plan/27.0"
)
CONTRACT_SCHEMA_VERSION = (
    "av-trace.p23-102-query-authoring-v2-canary2-contract/14.0"
)
RUNTIME_SCHEMA_VERSION = (
    "av-trace.p23-102-query-authoring-v2-canary2-runtime/3.0"
)
AUTHORED_QUERIES_SCHEMA_VERSION = (
    "av-trace.p23-102-query-authoring-v2-canary2-queries/4.0"
)
SEAL_SCHEMA_VERSION = (
    "av-trace.p23-102-query-authoring-v2-canary2-seal/8.0"
)
PRIVATE_GOVERNANCE_SCHEMA_VERSION = (
    "av-trace.p23-102-query-authoring-v2-canary2-private-governance/4.0"
)
PUBLIC_COMMITMENT_SCHEMA_VERSION = (
    "av-trace.p23-102-query-authoring-v2-canary2-public-commitment/5.0"
)
ATTEMPT_MARKER_SCHEMA_VERSION = (
    "av-trace.p23-102-query-authoring-v2-canary2-attempt-marker/1.0"
)
MEDIA_CONTRACT_REPAIR_READY = (
    "P23_102_QUERY_AUTHORING_MEDIA_CONTRACT_REPAIR_READY"
)
CONSTRAINED_JSON_READY = "P23_102_QUERY_AUTHORING_CONSTRAINED_JSON_READY"
SEMANTIC_GATES_READY = "P23_102_QUERY_AUTHORING_SEMANTIC_GATES_READY"
SELECTION_ALGORITHM = "r22b_one_shot_reserve_selection"
SELECTION_VERSION = "2.0"
SELECTION_DOMAIN = (
    "AV-TRACE-P23-102-QUERY-AUTHORING-V2-CANARY2-SELECTION-R22B"
)
LOCAL_REFERENCE_DOMAIN = f"{SELECTION_DOMAIN}:LOCAL-V15-REFERENCE"
VOCALIZATION_RISK_DOMAIN = f"{SELECTION_DOMAIN}:VOCALIZATION-ASR-RISK"
CONTINUITY_RISK_DOMAIN = f"{SELECTION_DOMAIN}:CONTINUITY-ANAPHORA-RISK"

DEFAULT_PLAN = Path(
    "data/rehearsal_plan/p23_102_query_authoring_v2_canary2.json"
)
PRIVATE_GOVERNANCE_LEDGER = Path(
    "data/restricted/"
    "p23_102_query_authoring_v2_canary2_r22f_governance_ledger.json"
)
PUBLIC_SELECTION_COMMITMENT = Path(
    "data/rehearsal_plan/"
    "p23_102_query_authoring_v2_canary2_r22f_public_commitment.json"
)
DEFAULT_OUTPUT = Path(
    "data/restricted/p23_102_query_authoring_v2_canary2_run_v1"
)
DEFAULT_BUNDLE = Path(
    "data/restricted/epic_p23_102_machine_provisional_families_v1"
)
DEFAULT_MEDIA = Path(
    "data/restricted/epic_p23_102_source_v1/media/P23/P23_102.MP4"
)
PARENT_TOOL = Path("tools/p23_102_query_authoring_v2.py")
CANARY_TOOL = Path("tools/p23_102_query_authoring_v2_canary2.py")
DEFAULT_INDEX = Path(
    "data/restricted/epic_p23_102_full_timeline_index_v1"
)
SPEECH_INDEX = DEFAULT_INDEX / "full_timeline_index.json"
V15_SUBSET = Path(
    "data/restricted/p23_102_query_authoring_v2_canary_run_v1/"
    "canary_subset_bundle.json"
)
V15_AUDITS = Path(
    "data/restricted/p23_102_query_authoring_v2_canary_run_v1/audits.json"
)
V15_SEAL = Path(
    "data/restricted/p23_102_query_authoring_v2_canary_run_v1/seal.json"
)
PUBLIC_SURFACE_SCAN_POLICY_VERSION = (
    "av-trace.canary2-public-surface-scan/2.0"
)
PUBLIC_SURFACE_CHUNK_BYTES = 1024 * 1024
PUBLIC_SURFACE_EXCLUDED_DIR_NAMES = frozenset(
    {
        ".git",
        ".agents",
        ".codex",
    }
)
PUBLIC_SURFACE_EXCLUDED_DIR_PREFIXES = (
    Path(".cache"),
    Path(".mypy_cache"),
    Path(".pytest_cache"),
    Path(".ruff_cache"),
    Path(".tox"),
    Path(".venv"),
    Path("build"),
    Path("node_modules"),
    Path("venv"),
)
PUBLIC_SURFACE_BINARY_DIR_PREFIXES = (
    Path("mvp/generated/full/media"),
    Path("mvp/generated/quick/media"),
    Path("mvp/media_backed/fixtures"),
)
PUBLIC_SURFACE_ALLOWLISTED_GENERATED_PRIVATE_OUTPUTS = (
    Path("orchestration/logs"),
    Path("orchestration/results"),
    Path(
        "data/rehearsal_plan/"
        "external_gateway_strong_agent_smoke_run_v1"
    ),
)
PUBLIC_SURFACE_BINARY_SUFFIXES = frozenset(
    {
        ".7z",
        ".avi",
        ".bin",
        ".bmp",
        ".bz2",
        ".class",
        ".coverage",
        ".db",
        ".dll",
        ".dylib",
        ".flac",
        ".gif",
        ".gz",
        ".ico",
        ".jar",
        ".jpeg",
        ".jpg",
        ".m4a",
        ".m4v",
        ".mkv",
        ".mov",
        ".mp3",
        ".mp4",
        ".npz",
        ".npy",
        ".onnx",
        ".otf",
        ".parquet",
        ".pdf",
        ".png",
        ".pt",
        ".pth",
        ".pyc",
        ".safetensors",
        ".so",
        ".sqlite",
        ".tar",
        ".tflite",
        ".tgz",
        ".ttf",
        ".wav",
        ".webm",
        ".webp",
        ".whl",
        ".xz",
        ".zip",
    }
)
PUBLIC_SURFACE_BINARY_FILENAMES = frozenset({".coverage"})

EXPECTED_FAMILIES = 3
MAX_UNIQUE_CLIPS = 5
EXPECTED_QUERY_COUNT = 13
EXPECTED_VISUAL_FACTORS = 5
EXPECTED_AMBIENT_FACTORS = 5
EXPECTED_COMPOSITION_FACTORS = EXPECTED_FAMILIES
EXPECTED_INITIAL_FACTORS = (
    EXPECTED_VISUAL_FACTORS
    + EXPECTED_AMBIENT_FACTORS
    + EXPECTED_COMPOSITION_FACTORS
)
EXPECTED_MAX_SCHEMA_ONLY_REPAIRS = (
    EXPECTED_VISUAL_FACTORS + EXPECTED_COMPOSITION_FACTORS
)

FAMILY_ROLES = (
    "local_v15_structure",
    "far_vocalization_asr_ambiguity",
    "far_continuity_anaphora",
)

OUTPUT_FILES = (
    "canary2_contract.json",
    "canary2_subset_bundle.json",
    "target_manifest.json",
    "prompt_manifest.json",
    "raw_attempts.jsonl",
    "accepted_factor_manifest.json",
    "ambient_semantic_tuple_collisions.json",
    "asr_audit_inventory.json",
    "authored_queries.json",
    "audits.json",
    "gate_findings.json",
    "failure_accounting.json",
    "resource_runtime.json",
)
AUTHORIZATION_SCHEMA_VERSION = (
    "av-trace.p23-102-query-authoring-v2-canary2-authorization/3.0"
)
AUTHORIZATION_REQUIRED_BINDINGS = [
    "canary_config_sha256",
    "selected_family_hashes",
    "selection_algorithm",
    "selection_version",
    "private_governance_ledger_sha256",
    "private_governance_commitment_sha256",
    "public_selection_commitment_sha256",
    "main_pipeline_sha256",
    "canary_pipeline_sha256",
    "bundle_file_hashes",
    "selection_input_hashes",
    "model_hashes",
    "media_sha256",
    "subset_payload_sha256",
    "prompt_manifest_expected_hashes",
    "output_path",
]


def _load_parent() -> Any:
    path = Path(__file__).with_name("p23_102_query_authoring_v2.py")
    spec = importlib.util.spec_from_file_location(
        "_p23_102_query_authoring_v2_parent", path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("PARENT_PIPELINE_IMPORT_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


parent = _load_parent()


class CanaryError(RuntimeError):
    """Fail-closed canary error."""


class PublicSurfaceScanError(CanaryError):
    """Public-surface failure carrying only a path/code/count report."""

    def __init__(self, message: str, report: Mapping[str, Any]) -> None:
        super().__init__(message)
        self.report = dict(report)


def _repo_path(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def _relative_repo_path(root: Path, path: Path) -> str:
    resolved = _repo_path(root, path).resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _parent_tool_hash(root: Path) -> str:
    path = _repo_path(root, PARENT_TOOL)
    if not path.is_file():
        raise CanaryError("MAIN_PIPELINE_MISSING")
    return "sha256:" + parent.file_sha256(path)


def _canary_tool_hash(root: Path) -> str:
    path = _repo_path(root, CANARY_TOOL)
    if not path.is_file():
        raise CanaryError("CANARY_PIPELINE_MISSING")
    return "sha256:" + parent.file_sha256(path)


def _family_descriptor(family: Mapping[str, Any]) -> dict[str, Any]:
    """Return only structural identity fields; no score or semantic ranking."""

    return {
        "family_key": family["family_key"],
        "private_family_id": family["private_family_id"],
        "shape": family["shape"],
        "intervals": [
            {
                "start_us": row["start_us"],
                "end_us": row["end_us"],
                "clip_key": row["clip_key"],
                "private_evidence_handle_ids": list(
                    row["private_evidence_handle_ids"]
                ),
            }
            for row in family["intervals"]
        ],
    }


def _family_hash(family: Mapping[str, Any]) -> str:
    return parent.semantic_hash(_family_descriptor(family))


def _load_v15_local_reference(root: Path) -> dict[str, Any]:
    subset_path = _repo_path(root, V15_SUBSET)
    audits_path = _repo_path(root, V15_AUDITS)
    seal_path = _repo_path(root, V15_SEAL)
    if not all(path.is_file() for path in (subset_path, audits_path, seal_path)):
        raise CanaryError("V15_REFERENCE_ARTIFACTS_MISSING")
    subset = parent.load_json(subset_path)
    audits = parent.load_json(audits_path)
    seal = parent.load_json(seal_path)
    if (
        subset.get("canary_id")
        != "AV-TRACE-P23-102-QUERY-AUTHORING-V2-CANARY"
        or audits.get("status") != "PASS"
        or seal.get("status")
        != "SEALED_CANARY_AUTHORING_COMPLETE_SCORING_NOT_RUN"
        or seal.get("retrieval_scoring_executed") is not False
    ):
        raise CanaryError("V15_REFERENCE_NOT_PASSING")
    local_hash = (
        subset.get("selection", {})
        .get("selected_family_hashes", {})
        .get("local")
    )
    if not isinstance(local_hash, str):
        raise CanaryError("V15_LOCAL_STRUCTURAL_HASH_MISSING")
    return {
        "local_family_structural_sha256": local_hash,
        "subset_file_sha256": "sha256:" + parent.file_sha256(subset_path),
        "audits_file_sha256": "sha256:" + parent.file_sha256(audits_path),
        "seal_file_sha256": "sha256:" + parent.file_sha256(seal_path),
    }


def _load_machine_diagnostics(root: Path) -> dict[str, Any]:
    path = _repo_path(root, SPEECH_INDEX)
    if not path.is_file():
        raise CanaryError("MACHINE_SPEECH_INDEX_MISSING")
    value = parent.load_json(path)
    if (
        value.get("source_ref") != "P23_102"
        or value.get("stage")
        != "RESTRICTED_DEVELOPMENT_ONLY_SOURCE_DERIVED_INDEX"
    ):
        raise CanaryError("MACHINE_SPEECH_INDEX_SCOPE_INVALID")
    speech = value.get("modalities", {}).get("speech", {})
    rows = speech.get("documents") if isinstance(speech, Mapping) else None
    if not isinstance(rows, list) or not rows:
        raise CanaryError("MACHINE_SPEECH_INDEX_ROWS_MISSING")
    if not isinstance(value.get("index_hash"), str):
        raise CanaryError("MACHINE_SPEECH_INDEX_HASH_MISSING")
    allowed = {
        "audio_rms_full_scale",
        "chunk_id",
        "document_length",
        "end_us",
        "mean_generated_token_log_probability",
        "model_observation_not_human_annotation",
        "quality_flags",
        "quality_gate_pass",
        "routing",
        "searchable",
        "source_ref",
        "start_us",
        "term_frequency",
        "text",
        "token_count",
    }
    if any(not isinstance(row, Mapping) or set(row) - allowed for row in rows):
        raise CanaryError("MACHINE_SPEECH_INDEX_ROW_SCHEMA_INVALID")
    return {
        "path": SPEECH_INDEX.as_posix(),
        "file_sha256": "sha256:" + parent.file_sha256(path),
        "index_hash": value.get("index_hash"),
        "speech_rows": rows,
    }


def _load_private_governance_ledger(root: Path) -> dict[str, Any]:
    path = _repo_path(root, PRIVATE_GOVERNANCE_LEDGER)
    if not path.is_file():
        raise CanaryError("PRIVATE_GOVERNANCE_LEDGER_MISSING")
    if stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise CanaryError("PRIVATE_GOVERNANCE_LEDGER_MODE_INVALID")
    value = parent.load_json(path)
    required = {
        "schema_version",
        "canary_id",
        "created_date",
        "status",
        "selection_algorithm",
        "selection_version",
        "role_priority",
        "exposure",
        "governance_limits",
        "attestations",
        "input_hashes",
        "r21_failure_evidence_path",
        "r21_failure_evidence_hashes",
        "selection",
        "public_surface_policy",
        "one_shot_policy",
        "canonical_commitment_sha256",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        raise CanaryError("PRIVATE_GOVERNANCE_LEDGER_SCHEMA_INVALID")
    if (
        value["schema_version"] != PRIVATE_GOVERNANCE_SCHEMA_VERSION
        or value["canary_id"] != CANARY_ID
        or value["created_date"] != CURRENT_DATE
        or value["status"] != "FROZEN_PRIVATE_GOVERNANCE"
        or value["selection_algorithm"] != SELECTION_ALGORITHM
        or value["selection_version"] != SELECTION_VERSION
        or value["role_priority"]
        != [
            "far_vocalization_asr_ambiguity",
            "far_continuity_anaphora",
        ]
    ):
        raise CanaryError("PRIVATE_GOVERNANCE_LEDGER_SCOPE_INVALID")
    limits = value["governance_limits"]
    if (
        not isinstance(limits, Mapping)
        or set(limits)
        != {
            "replacement_generation",
            "maximum_replacements",
            "run_attempt_limit",
            "redraw_after_output_permitted",
            "fallback_after_output_permitted",
            "runtime_fallback_permitted",
            "ranking_proof_only_family_keys",
        }
        or limits["replacement_generation"] != 1
        or limits["maximum_replacements"] != 2
        or limits["run_attempt_limit"] != 1
        or limits["redraw_after_output_permitted"] is not False
        or limits["fallback_after_output_permitted"] is not False
        or limits["runtime_fallback_permitted"] is not False
        or not isinstance(limits["ranking_proof_only_family_keys"], list)
        or len(limits["ranking_proof_only_family_keys"]) != 1
    ):
        raise CanaryError("PRIVATE_GOVERNANCE_LIMITS_INVALID")
    attestations = value["attestations"]
    if attestations != {
        "human_selection_performed": False,
        "retrieval_used_for_selection": False,
        "future_output_used_for_selection": False,
        "authorization_created": False,
        "real_model_run_performed": False,
    }:
        raise CanaryError("PRIVATE_GOVERNANCE_ATTESTATIONS_INVALID")
    if value["public_surface_policy"] != {
        "historical_public_identity_exemption": True,
        "private_token_values_reported": False,
        "r22_fresh_selected_publication_permitted": False,
        "unselected_reserve_publication_permitted": False,
        "scan_scope": "repo_root_recursive_all_regular_files",
        "scan_policy_version": PUBLIC_SURFACE_SCAN_POLICY_VERSION,
        "scan_policy_sha256": _public_surface_scan_policy_sha256(),
        "restricted_prefixes": ["data/restricted"],
        "excluded_directory_names": sorted(
            PUBLIC_SURFACE_EXCLUDED_DIR_NAMES
        ),
        "excluded_directory_prefixes": [
            path.as_posix()
            for path in PUBLIC_SURFACE_EXCLUDED_DIR_PREFIXES
        ],
        "binary_directory_prefixes": [
            path.as_posix()
            for path in PUBLIC_SURFACE_BINARY_DIR_PREFIXES
        ],
        "allowlisted_generated_private_output_prefixes": [
            path.as_posix()
            for path in PUBLIC_SURFACE_ALLOWLISTED_GENERATED_PRIVATE_OUTPUTS
        ],
        "binary_suffixes": sorted(PUBLIC_SURFACE_BINARY_SUFFIXES),
        "binary_filenames": sorted(PUBLIC_SURFACE_BINARY_FILENAMES),
        "chunk_bytes": PUBLIC_SURFACE_CHUNK_BYTES,
        "size_based_skip_permitted": False,
        "raw_bytes_private_token_scan": True,
        "binary_files_raw_scanned": True,
        "unknown_suffix_utf8_validated": True,
        "strict_utf8_decoding": True,
        "stat_open_read_fail_closed": True,
        "undecodable_text_failure_code": "PUBLIC_SURFACE_UNDECODABLE_TEXT",
        "binary_control_failure_code": (
            "PUBLIC_SURFACE_BINARY_CONTROL_BYTES"
        ),
    }:
        raise CanaryError("PRIVATE_GOVERNANCE_PUBLIC_SURFACE_POLICY_INVALID")
    if value["one_shot_policy"] != {
        "attempt_marker_schema_version": ATTEMPT_MARKER_SCHEMA_VERSION,
        "path_derived_from_authorization_id": True,
        "atomic_create": "O_CREAT|O_EXCL",
        "mode": "0600",
        "created_after_receipt_and_input_validation": True,
        "created_before_media_decode": True,
        "created_before_model_load_or_call": True,
        "file_fsync_required": True,
        "parent_directory_fsync_required": True,
        "post_create_chmod_required": True,
        "post_exclusive_create_failure_retains_inode": True,
        "partial_or_invalid_marker_consumes_receipt": True,
        "partial_or_invalid_marker_validates_as_success": False,
        "preflight_creates_marker": False,
        "failure_retains_marker_and_capsule": True,
        "success_retains_marker_and_output": True,
        "same_receipt_rerun_permitted": False,
    }:
        raise CanaryError("PRIVATE_GOVERNANCE_ONE_SHOT_POLICY_INVALID")
    failure_path = value["r21_failure_evidence_path"]
    if (
        not isinstance(failure_path, str)
        or not failure_path.startswith("data/restricted/")
        or not _repo_path(root, Path(failure_path)).is_dir()
    ):
        raise CanaryError("PRIVATE_GOVERNANCE_R21_EVIDENCE_PATH_INVALID")
    expected_commitment = parent.semantic_hash(
        {
            key: item
            for key, item in value.items()
            if key != "canonical_commitment_sha256"
        }
    )
    if value["canonical_commitment_sha256"] != expected_commitment:
        raise CanaryError("PRIVATE_GOVERNANCE_COMMITMENT_MISMATCH")
    return dict(value)


def _public_commitment_hashes(root: Path) -> dict[str, str]:
    private_path = _repo_path(root, PRIVATE_GOVERNANCE_LEDGER)
    public_path = _repo_path(root, PUBLIC_SELECTION_COMMITMENT)
    if not private_path.is_file() or not public_path.is_file():
        raise CanaryError("R22C_GOVERNANCE_COMMITMENT_MISSING")
    ledger = _load_private_governance_ledger(root)
    public = parent.load_json(public_path)
    expected_public_fields = {
        "schema_version",
        "canary_id",
        "created_date",
        "status",
        "selection_algorithm",
        "selection_version",
        "counts",
        "input_hashes",
        "private_canonical_commitment_sha256",
        "one_run",
        "no_redraw",
        "no_runtime_fallback",
        "one_shot_attempt_marker",
        "public_surface_private_leakage_scan",
        "public_surface_scan_scope",
        "public_surface_scan_policy_version",
        "public_surface_scan_policy_sha256",
        "public_surface_raw_bytes_private_token_scan",
        "public_surface_binary_files_raw_scanned",
        "public_surface_unknown_suffix_utf8_validated",
        "public_surface_strict_utf8",
        "public_surface_undecodable_failure_code",
        "public_surface_binary_control_failure_code",
        "public_surface_size_based_skip_permitted",
        "marker_fail_stop_persistence",
        "public_payload_sha256",
    }
    if not isinstance(public, Mapping) or set(public) != expected_public_fields:
        raise CanaryError("PUBLIC_SELECTION_COMMITMENT_SCHEMA_INVALID")
    expected_public_hash = parent.semantic_hash(
        {
            key: item
            for key, item in public.items()
            if key != "public_payload_sha256"
        }
    )
    if (
        public["schema_version"] != PUBLIC_COMMITMENT_SCHEMA_VERSION
        or public["canary_id"] != CANARY_ID
        or public["created_date"] != CURRENT_DATE
        or public["status"] != "PUBLIC_COMMITMENT_ONLY"
        or public["selection_algorithm"] != SELECTION_ALGORITHM
        or public["selection_version"] != SELECTION_VERSION
        or public["private_canonical_commitment_sha256"]
        != ledger["canonical_commitment_sha256"]
        or public["one_run"] is not True
        or public["no_redraw"] is not True
        or public["no_runtime_fallback"] is not True
        or public["one_shot_attempt_marker"] is not True
        or public["public_surface_private_leakage_scan"] is not True
        or public["public_surface_scan_scope"]
        != "repo_root_recursive_all_regular_files"
        or public["public_surface_scan_policy_version"]
        != PUBLIC_SURFACE_SCAN_POLICY_VERSION
        or public["public_surface_scan_policy_sha256"]
        != _public_surface_scan_policy_sha256()
        or public["public_surface_raw_bytes_private_token_scan"] is not True
        or public["public_surface_binary_files_raw_scanned"] is not True
        or public["public_surface_unknown_suffix_utf8_validated"] is not True
        or public["public_surface_strict_utf8"] is not True
        or public["public_surface_undecodable_failure_code"]
        != "PUBLIC_SURFACE_UNDECODABLE_TEXT"
        or public["public_surface_binary_control_failure_code"]
        != "PUBLIC_SURFACE_BINARY_CONTROL_BYTES"
        or public["public_surface_size_based_skip_permitted"] is not False
        or public["marker_fail_stop_persistence"] is not True
        or public["public_payload_sha256"] != expected_public_hash
    ):
        raise CanaryError("PUBLIC_SELECTION_COMMITMENT_INVALID")
    scan_public_surface_for_private_leakage(root, ledger=ledger)
    return {
        "private_governance_ledger_sha256": (
            "sha256:" + parent.file_sha256(private_path)
        ),
        "private_governance_commitment_sha256": ledger[
            "canonical_commitment_sha256"
        ],
        "public_selection_commitment_sha256": (
            "sha256:" + parent.file_sha256(public_path)
        ),
    }


def _canonical_token(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def _private_token_records(
    ledger: Mapping[str, Any],
) -> list[dict[str, str]]:
    """Return classified private literals without exposing them to callers."""

    records: dict[tuple[str, str], dict[str, str]] = {}

    def add(value: Any, *, category: str, classification: str) -> None:
        tokens = (
            [value]
            if isinstance(value, str)
            else [
                _canonical_token(value),
                json.dumps(value, sort_keys=True, ensure_ascii=False),
            ]
        )
        for token in tokens:
            if not token or token in {"[]", "{}"}:
                continue
            key = (category, token)
            records[key] = {
                "category": category,
                "classification": classification,
                "token": token,
            }

    exposure = ledger["exposure"]
    for category in (
        "family_keys",
        "family_hashes",
        "private_family_ids",
        "clip_keys",
        "private_evidence_handle_ids",
    ):
        for value in exposure[category]:
            add(
                value,
                category=f"historical_exposure.{category}",
                classification="historical_public_identity",
            )
    for interval in exposure["intervals"]:
        add(
            interval,
            category="historical_exposure.interval_literal",
            classification="historical_public_identity",
        )
    for key, value in exposure["anti_alias_exclusions"].items():
        add(
            key,
            category="historical_exposure.anti_alias_family_key",
            classification="historical_public_identity",
        )
        add(
            value,
            category="historical_exposure.anti_alias_reason",
            classification="historical_public_identity",
        )
    add(
        exposure["anchor_family_key"],
        category="historical_exposure.anchor_family_key",
        classification="historical_public_identity",
    )

    historical_family_keys = set(map(str, exposure["family_keys"]))
    historical_family_keys.update(
        map(str, exposure["anti_alias_exclusions"])
    )
    historical_identity_tokens: set[str] = set()
    for row in ledger["selection"]["complete_ranking"]:
        if str(row["family_key"]) not in historical_family_keys:
            continue
        historical_identity_tokens.update(
            {
                str(row["family_key"]),
                str(row["private_family_id"]),
                str(row["family_structural_sha256"]),
            }
        )
        historical_identity_tokens.update(map(str, row["clip_keys"]))
        historical_identity_tokens.update(
            map(str, row["private_evidence_handle_ids"])
        )
        for interval in row["intervals"]:
            historical_identity_tokens.update(
                {
                    _canonical_token(interval),
                    json.dumps(
                        interval, sort_keys=True, ensure_ascii=False
                    ),
                }
            )

    selected_rows = ledger["selection"]["selected_identities"]
    selected_roles_by_key = {
        row["family_key"]: role for role, row in selected_rows.items()
    }
    for role, row in selected_rows.items():
        classification = (
            "historical_public_identity"
            if role == "local_v15_structure"
            else "r22_fresh_selected"
        )
        for category in (
            "family_key",
            "private_family_id",
            "family_structural_sha256",
        ):
            classification = (
                "historical_public_identity"
                if str(row[category]) in historical_identity_tokens
                else classification
            )
            add(
                row[category],
                category=f"selected.{role}.{category}",
                classification=classification,
            )
        for category in ("clip_keys", "private_evidence_handle_ids"):
            for value in row[category]:
                item_classification = (
                    "historical_public_identity"
                    if str(value) in historical_identity_tokens
                    else classification
                )
                add(
                    value,
                    category=f"selected.{role}.{category}",
                    classification=item_classification,
                )
        for interval in row["intervals"]:
            interval_classification = (
                "historical_public_identity"
                if _canonical_token(interval) in historical_identity_tokens
                else classification
            )
            add(
                interval,
                category=f"selected.{role}.interval_literal",
                classification=interval_classification,
            )

    for row in ledger["selection"]["complete_ranking"]:
        row_classification = (
            "r22_fresh_selected"
            if row["family_key"] in selected_roles_by_key
            and selected_roles_by_key[row["family_key"]]
            != "local_v15_structure"
            else "r22_unselected_reserve"
        )
        if (
            selected_roles_by_key.get(row["family_key"])
            == "local_v15_structure"
        ):
            row_classification = "historical_public_identity"
        for category in (
            "family_key",
            "private_family_id",
            "family_structural_sha256",
        ):
            classification = (
                "historical_public_identity"
                if str(row[category]) in historical_identity_tokens
                else row_classification
            )
            add(
                row[category],
                category=f"ranking.{category}",
                classification=classification,
            )
        for category in ("clip_keys", "private_evidence_handle_ids"):
            for value in row[category]:
                classification = (
                    "historical_public_identity"
                    if str(value) in historical_identity_tokens
                    else row_classification
                )
                add(
                    value,
                    category=f"ranking.{category}",
                    classification=classification,
                )
        for interval in row["intervals"]:
            classification = (
                "historical_public_identity"
                if _canonical_token(interval) in historical_identity_tokens
                else row_classification
            )
            add(
                interval,
                category="ranking.interval_literal",
                classification=classification,
            )
        for category in (
            "vocalization_tie_sha256",
            "continuity_tie_sha256",
            "vocalization_risk_tuple",
            "continuity_risk_tuple",
            "exclusion_reasons",
        ):
            add(
                row[category],
                category=f"ranking.{category}",
                classification=row_classification,
            )
    return sorted(
        records.values(),
        key=lambda row: (
            row["classification"],
            row["category"],
            row["token"],
        ),
    )


def _path_is_under(path: Path, prefix: Path) -> bool:
    try:
        path.relative_to(prefix)
        return True
    except ValueError:
        return False


def _public_surface_scan_policy() -> dict[str, Any]:
    return {
        "schema_version": PUBLIC_SURFACE_SCAN_POLICY_VERSION,
        "scan_scope": "repo_root_recursive_all_regular_files",
        "restricted_prefixes": ["data/restricted"],
        "excluded_directory_names": sorted(
            PUBLIC_SURFACE_EXCLUDED_DIR_NAMES
        ),
        "excluded_directory_prefixes": [
            path.as_posix()
            for path in PUBLIC_SURFACE_EXCLUDED_DIR_PREFIXES
        ],
        "binary_directory_prefixes": [
            path.as_posix()
            for path in PUBLIC_SURFACE_BINARY_DIR_PREFIXES
        ],
        "allowlisted_generated_private_output_prefixes": [
            path.as_posix()
            for path in PUBLIC_SURFACE_ALLOWLISTED_GENERATED_PRIVATE_OUTPUTS
        ],
        "binary_suffixes": sorted(PUBLIC_SURFACE_BINARY_SUFFIXES),
        "binary_filenames": sorted(PUBLIC_SURFACE_BINARY_FILENAMES),
        "chunk_bytes": PUBLIC_SURFACE_CHUNK_BYTES,
        "size_based_skip_permitted": False,
        "raw_bytes_private_token_scan": True,
        "binary_files_raw_scanned": True,
        "unknown_suffix_utf8_validated": True,
        "strict_utf8_decoding": True,
        "allowed_control_characters": ["TAB", "LF", "CR"],
        "stat_open_read_fail_closed": True,
        "private_token_values_reported": False,
    }


def _public_surface_scan_policy_sha256() -> str:
    return parent.semantic_hash(_public_surface_scan_policy())


def _public_surface_path_classification(
    relative: Path,
) -> str | None:
    """Classify a repo-relative path using only narrow explicit policy."""

    if relative.is_absolute() or ".." in relative.parts:
        raise CanaryError("PUBLIC_SURFACE_PATH_OUTSIDE_REPO")
    if _path_is_under(relative, Path("data/restricted")):
        return "restricted"
    if any(
        part in PUBLIC_SURFACE_EXCLUDED_DIR_NAMES
        for part in relative.parts[:-1]
    ):
        return "excluded_directory"
    if any(
        _path_is_under(relative, prefix)
        for prefix in PUBLIC_SURFACE_EXCLUDED_DIR_PREFIXES
    ):
        return "excluded_directory"
    if any(
        _path_is_under(relative, prefix)
        for prefix in PUBLIC_SURFACE_ALLOWLISTED_GENERATED_PRIVATE_OUTPUTS
    ):
        return "allowlisted_generated_private_output"
    if any(
        _path_is_under(relative, prefix)
        for prefix in PUBLIC_SURFACE_BINARY_DIR_PREFIXES
    ):
        return "binary"
    if (
        relative.suffix.lower() in PUBLIC_SURFACE_BINARY_SUFFIXES
        or relative.name in PUBLIC_SURFACE_BINARY_FILENAMES
    ):
        return "binary"
    return None


def _public_surface_stat(path: Path) -> os.stat_result:
    return path.stat(follow_symlinks=False)


def _public_surface_open(path: Path) -> Any:
    return path.open("rb")


def _public_surface_read(stream: Any) -> bytes:
    return stream.read(PUBLIC_SURFACE_CHUNK_BYTES)


def _has_forbidden_control(text: str) -> bool:
    return any(
        (ord(character) < 32 and character not in "\t\n\r")
        or 127 <= ord(character) <= 159
        for character in text
    )


def _scan_public_surface_file(
    path: Path,
    *,
    relative: str,
    binary: bool,
    forbidden_bytes: Sequence[tuple[Mapping[str, str], bytes]],
) -> tuple[list[dict[str, str]], bool, bool]:
    """Stream one regular file; return matches, decode failure, controls."""

    decoder = (
        None
        if binary
        else codecs.getincrementaldecoder("utf-8")(errors="strict")
    )
    maximum_token_bytes = max(
        (len(token_bytes) for _, token_bytes in forbidden_bytes),
        default=1,
    )
    overlap_bytes = maximum_token_bytes - 1
    tail = b""
    matched: dict[tuple[str, str], dict[str, str]] = {}
    undecodable = False
    forbidden_control = False
    try:
        stream = _public_surface_open(path)
    except OSError as exc:
        raise CanaryError(
            f"PUBLIC_SURFACE_OPEN_ERROR:{relative}:{exc.errno}"
        ) from exc
    try:
        with stream:
            while True:
                try:
                    chunk = _public_surface_read(stream)
                except OSError as exc:
                    raise CanaryError(
                        f"PUBLIC_SURFACE_READ_ERROR:{relative}:{exc.errno}"
                    ) from exc
                if not chunk:
                    break
                searchable = tail + chunk
                for record, token_bytes in forbidden_bytes:
                    if token_bytes in searchable:
                        matched[
                            (record["category"], record["classification"])
                        ] = dict(record)
                tail = (
                    searchable[-overlap_bytes:]
                    if overlap_bytes
                    else b""
                )
                if decoder is not None and not undecodable:
                    try:
                        decoded = decoder.decode(chunk, final=False)
                    except UnicodeDecodeError:
                        undecodable = True
                    else:
                        forbidden_control = (
                            forbidden_control
                            or _has_forbidden_control(decoded)
                        )
            if decoder is not None and not undecodable:
                try:
                    decoded = decoder.decode(b"", final=True)
                except UnicodeDecodeError:
                    undecodable = True
                else:
                    forbidden_control = (
                        forbidden_control
                        or _has_forbidden_control(decoded)
                    )
    except CanaryError:
        raise
    except OSError as exc:
        raise CanaryError(
            f"PUBLIC_SURFACE_READ_ERROR:{relative}:{exc.errno}"
        ) from exc
    return list(matched.values()), undecodable, forbidden_control


def scan_public_surface_for_private_leakage(
    root: Path = ROOT,
    *,
    ledger: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Fail closed if R22-fresh or unselected private literals are public."""

    private = (
        dict(ledger)
        if ledger is not None
        else _load_private_governance_ledger(root)
    )
    forbidden = [
        record
        for record in _private_token_records(private)
        if record["classification"]
        in {"r22_fresh_selected", "r22_unselected_reserve"}
    ]
    forbidden_bytes = [
        (record, record["token"].encode("utf-8"))
        for record in forbidden
    ]
    root = root.resolve()
    findings: list[dict[str, Any]] = []
    undecodable_paths: list[str] = []
    control_paths: list[str] = []
    io_failures: list[str] = []
    counts = {
        "all_regular": 0,
        "raw_scanned": 0,
        "utf8_validated": 0,
        "binary_excluded": 0,
        "restricted_excluded": 0,
        "policy_excluded": 0,
        "failures": 0,
    }

    def walk_error(error: OSError) -> None:
        path = _relative_repo_path(
            root, Path(str(error.filename or root))
        )
        io_failures.append(
            f"PUBLIC_SURFACE_DIRECTORY_READ_ERROR:{path}:{error.errno}"
        )

    for directory, dirnames, filenames in os.walk(
        root, topdown=True, followlinks=False, onerror=walk_error
    ):
        dirnames.sort()
        filenames.sort()
        base = Path(directory)
        for name in filenames:
            path = base / name
            relative_path = path.relative_to(root)
            relative = relative_path.as_posix()
            try:
                file_stat = _public_surface_stat(path)
            except OSError as exc:
                io_failures.append(
                    f"PUBLIC_SURFACE_STAT_ERROR:{relative}:{exc.errno}"
                )
                continue
            if not stat.S_ISREG(file_stat.st_mode):
                continue
            counts["all_regular"] += 1
            classification = _public_surface_path_classification(
                relative_path
            )
            if classification == "restricted":
                counts["restricted_excluded"] += 1
                continue
            if classification in {
                "excluded_directory",
                "allowlisted_generated_private_output",
            }:
                counts["policy_excluded"] += 1
                continue
            binary = classification == "binary"
            if binary:
                counts["binary_excluded"] += 1
            try:
                matched, undecodable, forbidden_control = (
                    _scan_public_surface_file(
                        path,
                        relative=relative,
                        binary=binary,
                        forbidden_bytes=forbidden_bytes,
                    )
                )
            except CanaryError as exc:
                io_failures.append(str(exc))
                continue
            counts["raw_scanned"] += 1
            if not binary and not undecodable:
                counts["utf8_validated"] += 1
            if matched:
                findings.append(
                    {
                        "path": relative,
                        "classifications": sorted(
                            {row["classification"] for row in matched}
                        ),
                        "categories": sorted(
                            {row["category"] for row in matched}
                        ),
                        "match_count": len(matched),
                    }
                )
            if undecodable:
                undecodable_paths.append(relative)
            if forbidden_control:
                control_paths.append(relative)

    failures: list[str] = []
    if findings:
        failures.append(
            "PUBLIC_SURFACE_PRIVATE_LEAKAGE:"
            + ",".join(row["path"] for row in findings)
        )
    if undecodable_paths:
        failures.append(
            "PUBLIC_SURFACE_UNDECODABLE_TEXT:"
            + ",".join(undecodable_paths)
        )
    if control_paths:
        failures.append(
            "PUBLIC_SURFACE_BINARY_CONTROL_BYTES:"
            + ",".join(control_paths)
        )
    failures.extend(io_failures)
    counts["failures"] = (
        len(findings)
        + len(undecodable_paths)
        + len(control_paths)
        + len(io_failures)
    )
    report = {
        "status": "PASS" if not failures else "FAIL_CLOSED",
        "counts": counts,
        "forbidden_token_count": len(forbidden),
        "scan_scope": "repo_root_recursive_all_regular_files",
        "scan_policy_version": PUBLIC_SURFACE_SCAN_POLICY_VERSION,
        "scan_policy_sha256": _public_surface_scan_policy_sha256(),
        "chunk_bytes": PUBLIC_SURFACE_CHUNK_BYTES,
        "size_based_skip_permitted": False,
        "allowlisted_generated_private_output_prefix_count": len(
            PUBLIC_SURFACE_ALLOWLISTED_GENERATED_PRIVATE_OUTPUTS
        ),
        "historical_public_identities_exempted": True,
        "private_token_values_reported": False,
        "raw_bytes_private_token_scan": True,
        "binary_files_raw_scanned": True,
        "unknown_suffix_utf8_validated": True,
        "strict_utf8_decoding": True,
        "undecodable_text_failure_code": (
            "PUBLIC_SURFACE_UNDECODABLE_TEXT"
        ),
        "binary_control_failure_code": (
            "PUBLIC_SURFACE_BINARY_CONTROL_BYTES"
        ),
        "failure_paths_and_codes_reported": True,
    }
    if failures:
        raise PublicSurfaceScanError(";".join(failures), report)
    return report


def _public_selection_input_hashes(
    source_hashes: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        key: value
        for key, value in source_hashes.items()
        if key != "v15_local_family_structural_sha256"
    }


def _r21_failure_evidence_hashes(
    root: Path, ledger: Mapping[str, Any]
) -> dict[str, str]:
    directory = _repo_path(
        root, Path(str(ledger["r21_failure_evidence_path"]))
    )
    if not directory.is_dir():
        raise CanaryError("R21_FAILURE_EVIDENCE_MISSING")
    return {
        path.name: "sha256:" + parent.file_sha256(path)
        for path in sorted(directory.iterdir())
        if path.is_file()
    }


def _selection_source_hashes(
    structural: Mapping[str, Any],
    diagnostics: Mapping[str, Any],
    reference: Mapping[str, Any],
    r21_hashes: Mapping[str, str],
) -> dict[str, Any]:
    return {
        "bundle_file_hashes": dict(structural["file_hashes"]),
        "machine_speech_index_file_sha256": diagnostics["file_sha256"],
        "machine_index_hash": diagnostics["index_hash"],
        "v15_subset_file_sha256": reference["subset_file_sha256"],
        "v15_audits_file_sha256": reference["audits_file_sha256"],
        "v15_seal_file_sha256": reference["seal_file_sha256"],
        "v15_local_family_structural_sha256": reference[
            "local_family_structural_sha256"
        ],
        "r21_failure_evidence_hashes": dict(r21_hashes),
    }


def _overlapping_speech_rows(
    family: Mapping[str, Any], speech_rows: Sequence[Mapping[str, Any]]
) -> list[Mapping[str, Any]]:
    return [
        row
        for row in speech_rows
        if any(
            int(row["start_us"]) < int(interval["end_us"])
            and int(row["end_us"]) > int(interval["start_us"])
            for interval in family["intervals"]
        )
    ]


def _vocalization_risk(
    family: Mapping[str, Any], speech_rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    overlaps = _overlapping_speech_rows(family, speech_rows)
    degenerate_count = 0
    short_vocalization_count = 0
    low_quality_flag_count = 0
    inventory_only_count = 0
    low_logprob_milli = 0
    for row in overlaps:
        analysis = parent.degenerate_asr_analysis(str(row["text"]))
        words = set(parent._normalized_words(str(row["text"])))
        degenerate_count += int(bool(analysis["degenerate"]))
        short_vocalization_count += int(
            bool(words & parent.SHORT_VOCALIZATION_TOKENS)
        )
        flags = set(map(str, row.get("quality_flags", [])))
        low_quality_flag_count += len(flags)
        inventory_only_count += int(row.get("routing") == "inventory_only")
        logprob = row.get("mean_generated_token_log_probability")
        if isinstance(logprob, (int, float)) and not isinstance(logprob, bool):
            low_logprob_milli += max(0, round(-float(logprob) * 1000))
    risk_tuple = (
        degenerate_count,
        short_vocalization_count,
        low_quality_flag_count,
        inventory_only_count,
        low_logprob_milli,
        len(overlaps),
    )
    return {
        "risk_tuple": list(risk_tuple),
        "overlap_count": len(overlaps),
        "degenerate_overlap_count": degenerate_count,
        "short_vocalization_overlap_count": short_vocalization_count,
        "quality_flag_count": low_quality_flag_count,
        "inventory_only_overlap_count": inventory_only_count,
        "low_logprob_milli_sum": low_logprob_milli,
        "overlap_chunk_hashes": sorted(
            parent.semantic_hash(
                {
                    "chunk_id": row["chunk_id"],
                    "start_us": row["start_us"],
                    "end_us": row["end_us"],
                    "quality_flags": row.get("quality_flags", []),
                    "routing": row.get("routing"),
                    "token_count": row.get("token_count"),
                    "transcript_analysis": parent.degenerate_asr_analysis(
                        str(row["text"])
                    ),
                }
            )
            for row in overlaps
        ),
    }


def _continuity_risk(
    family: Mapping[str, Any], machine_family: Mapping[str, Any]
) -> dict[str, Any]:
    scores = machine_family.get("structural_scores", {})
    temporal = machine_family.get("temporal_structure", {})
    try:
        visual = float(scores["visual_continuity"])
        audio = float(scores["audio_continuity"])
        separation = float(temporal["evidence_center_separation_seconds"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CanaryError("FAR_CONTINUITY_DIAGNOSTICS_MISSING") from exc
    if not all(math.isfinite(value) for value in (visual, audio, separation)):
        raise CanaryError("FAR_CONTINUITY_DIAGNOSTICS_NONFINITE")
    risk_tuple = (
        round(min(visual, audio) * 1_000_000),
        round((visual + audio) * 500_000),
        round(separation * 1_000_000),
    )
    return {
        "risk_tuple": list(risk_tuple),
        "visual_continuity_ppm": round(visual * 1_000_000),
        "audio_continuity_ppm": round(audio * 1_000_000),
        "minimum_cross_channel_continuity_ppm": risk_tuple[0],
        "mean_cross_channel_continuity_ppm": risk_tuple[1],
        "evidence_center_separation_us": risk_tuple[2],
        "machine_diagnostic_sha256": parent.semantic_hash(
            {
                "family_structural_sha256": _family_hash(family),
                "visual_continuity": visual,
                "audio_continuity": audio,
                "evidence_center_separation_seconds": separation,
            }
        ),
    }


def _hash_tie_break(
    *, domain: str, structural: Mapping[str, Any], family_hash: str
) -> str:
    return parent.semantic_hash(
        {
            "domain": domain,
            "bundle_file_hashes": structural["file_hashes"],
            "family_structural_sha256": family_hash,
        }
    )


def _positive_interval_overlap(
    left: Mapping[str, Any], right: Mapping[str, Any]
) -> bool:
    return (
        int(left["start_us"]) < int(right["end_us"])
        and int(left["end_us"]) > int(right["start_us"])
    )


def _shared_speech_chunk_ids(
    family: Mapping[str, Any],
    exposed_intervals: Sequence[Mapping[str, Any]],
    speech_rows: Sequence[Mapping[str, Any]],
) -> list[str]:
    family_chunks = {
        str(row["chunk_id"])
        for row in _overlapping_speech_rows(family, speech_rows)
    }
    exposed_chunks = {
        str(row["chunk_id"])
        for row in speech_rows
        if any(_positive_interval_overlap(interval, row) for interval in exposed_intervals)
    }
    return sorted(family_chunks & exposed_chunks)


def _exposure_reasons(
    family: Mapping[str, Any],
    *,
    family_hash: str,
    exposure: Mapping[str, Any],
    speech_rows: Sequence[Mapping[str, Any]],
) -> list[str]:
    exposed_intervals = exposure["intervals"]
    reasons: list[str] = []
    if family["family_key"] in exposure["family_keys"]:
        reasons.append("family_key")
    if family_hash in exposure["family_hashes"]:
        reasons.append("family_structural_sha256")
    if family["private_family_id"] in exposure["private_family_ids"]:
        reasons.append("private_family_id")
    family_clips = {
        str(interval["clip_key"]) for interval in family["intervals"]
    }
    if family_clips & set(exposure["clip_keys"]):
        reasons.append("clip_key")
    family_handles = {
        str(handle)
        for interval in family["intervals"]
        for handle in interval["private_evidence_handle_ids"]
    }
    if family_handles & set(exposure["private_evidence_handle_ids"]):
        reasons.append("private_evidence_handle_id")
    if any(
        _positive_interval_overlap(interval, exposed)
        for interval in family["intervals"]
        for exposed in exposed_intervals
    ):
        reasons.append("positive_interval_overlap")
    shared_chunks = _shared_speech_chunk_ids(
        family, exposed_intervals, speech_rows
    )
    if shared_chunks:
        reasons.append("boundary_or_shared_speech_chunk")
    anti_alias = exposure.get("anti_alias_exclusions", {})
    if family["family_key"] in anti_alias:
        reasons.append(str(anti_alias[family["family_key"]]))
    return reasons


def _ranking_proof(
    ranked: Sequence[tuple[Any, ...]],
    *,
    excluded_by_family_key: Mapping[str, Sequence[str]],
) -> list[dict[str, Any]]:
    ordered = sorted(
        ranked, key=lambda row: (row[0], row[1], row[2]), reverse=True
    )
    return [
        {
            "ordinal": ordinal,
            "family_key": row[3]["family_key"],
            "private_family_id": row[3]["private_family_id"],
            "family_structural_sha256": row[2],
            "risk_tuple": list(row[0]),
            "tie_sha256": row[1],
            "exclusion_reasons": list(
                excluded_by_family_key.get(row[3]["family_key"], [])
            ),
        }
        for ordinal, row in enumerate(ordered, 1)
    ]


def _private_selection_record(
    structural: Mapping[str, Any],
    selection: Mapping[str, Any],
) -> dict[str, Any]:
    family_by_key = {
        str(row["family_key"]): row for row in structural["families"]
    }
    vocal_by_key = {
        str(row["family_key"]): row
        for row in selection["private_selection_proof"][
            "vocalization_ranking"
        ]
    }
    continuity_by_key = {
        str(row["family_key"]): row
        for row in selection["private_selection_proof"]["continuity_ranking"]
    }
    complete_ranking = []
    for family_key in sorted(vocal_by_key):
        family = family_by_key[family_key]
        vocal = vocal_by_key[family_key]
        continuity = continuity_by_key[family_key]
        complete_ranking.append(
            {
                "family_key": family_key,
                "private_family_id": family["private_family_id"],
                "family_structural_sha256": _family_hash(family),
                "clip_keys": [
                    interval["clip_key"] for interval in family["intervals"]
                ],
                "intervals": [
                    {
                        "start_us": interval["start_us"],
                        "end_us": interval["end_us"],
                    }
                    for interval in family["intervals"]
                ],
                "private_evidence_handle_ids": sorted(
                    handle
                    for interval in family["intervals"]
                    for handle in interval["private_evidence_handle_ids"]
                ),
                "vocalization_rank_ordinal": vocal["ordinal"],
                "vocalization_risk_tuple": vocal["risk_tuple"],
                "vocalization_tie_sha256": vocal["tie_sha256"],
                "continuity_rank_ordinal": continuity["ordinal"],
                "continuity_risk_tuple": continuity["risk_tuple"],
                "continuity_tie_sha256": continuity["tie_sha256"],
                "exclusion_reasons": vocal["exclusion_reasons"],
            }
        )
    return {
        "selected_identities": {
            row["family_role"]: {
                "family_key": row["family_key"],
                "private_family_id": family_by_key[row["family_key"]][
                    "private_family_id"
                ],
                "family_structural_sha256": row[
                    "family_structural_sha256"
                ],
                "clip_keys": [
                    interval["clip_key"]
                    for interval in family_by_key[row["family_key"]][
                        "intervals"
                    ]
                ],
                "intervals": [
                    {
                        "start_us": interval["start_us"],
                        "end_us": interval["end_us"],
                    }
                    for interval in family_by_key[row["family_key"]][
                        "intervals"
                    ]
                ],
                "private_evidence_handle_ids": sorted(
                    handle
                    for interval in family_by_key[row["family_key"]][
                        "intervals"
                    ]
                    for handle in interval["private_evidence_handle_ids"]
                ),
            }
            for row in selection["families"]
        },
        "complete_ranking": complete_ranking,
        "selection_proof_sha256": parent.semantic_hash(
            {
                "algorithm": selection["algorithm"],
                "version": selection["version"],
                "role_priority": selection["role_priority"],
                "selected_family_hashes": selection[
                    "selected_family_hashes"
                ],
                "rankings": selection["private_selection_proof"],
            }
        ),
    }


def select_canary_families(
    structural: Mapping[str, Any],
    *,
    machine_family_rows: Mapping[str, Mapping[str, Any]],
    speech_rows: Sequence[Mapping[str, Any]],
    v15_local_hash: str,
    exposure: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Select the anchor and fresh one-shot reserves after exposure filtering."""

    locals_ = [
        row for row in structural["families"] if row["shape"] == "one_component"
    ]
    far = [
        row
        for row in structural["families"]
        if row["shape"] == "two_component_ordered"
    ]
    local_matches = [row for row in locals_ if _family_hash(row) == v15_local_hash]
    if len(local_matches) != 1:
        raise CanaryError("V15_LOCAL_STRUCTURAL_REFERENCE_MISMATCH")
    if len(far) < 2:
        raise CanaryError("SELECTION_FAR_CLASS_TOO_SMALL")
    local = local_matches[0]

    vocalization_ranked = []
    continuity_ranked = []
    excluded_by_family_key: dict[str, list[str]] = {}
    for family in far:
        family_hash = _family_hash(family)
        machine_family = machine_family_rows.get(
            str(family["private_family_id"])
        )
        if machine_family is None:
            raise CanaryError("MACHINE_FAMILY_DIAGNOSTICS_MISSING")
        vocalization = _vocalization_risk(family, speech_rows)
        continuity = _continuity_risk(family, machine_family)
        vocalization_ranked.append(
            (
                tuple(vocalization["risk_tuple"]),
                _hash_tie_break(
                    domain=VOCALIZATION_RISK_DOMAIN,
                    structural=structural,
                    family_hash=family_hash,
                ),
                family_hash,
                family,
                vocalization,
            )
        )
        continuity_ranked.append(
            (
                tuple(continuity["risk_tuple"]),
                _hash_tie_break(
                    domain=CONTINUITY_RISK_DOMAIN,
                    structural=structural,
                    family_hash=family_hash,
                ),
                family_hash,
                family,
                continuity,
            )
        )
        if exposure is not None:
            excluded_by_family_key[family["family_key"]] = _exposure_reasons(
                family,
                family_hash=family_hash,
                exposure=exposure,
                speech_rows=speech_rows,
            )
        else:
            excluded_by_family_key[family["family_key"]] = []
    eligible_vocalization = [
        row
        for row in vocalization_ranked
        if not excluded_by_family_key[row[3]["family_key"]]
    ]
    eligible_continuity = [
        row
        for row in continuity_ranked
        if not excluded_by_family_key[row[3]["family_key"]]
    ]
    if not eligible_vocalization:
        raise CanaryError("SELECTION_NO_ELIGIBLE_VOCALIZATION_RESERVE")
    vocalization_choice = max(
        eligible_vocalization, key=lambda row: (row[0], row[1], row[2])
    )
    continuity_candidates = [
        row
        for row in eligible_continuity
        if row[3]["family_key"] != vocalization_choice[3]["family_key"]
    ]
    if not continuity_candidates:
        raise CanaryError("SELECTION_NO_ELIGIBLE_CONTINUITY_RESERVE")
    continuity_choice = max(
        continuity_candidates, key=lambda row: (row[0], row[1], row[2])
    )
    selected_families = [
        local,
        vocalization_choice[3],
        continuity_choice[3],
    ]
    selection_rows = [
        {
            "family_role": "local_v15_structure",
            "family_key": local["family_key"],
            "shape": local["shape"],
            "family_structural_sha256": _family_hash(local),
            "reference_domain": LOCAL_REFERENCE_DOMAIN,
            "v15_structure_pass_bound": True,
        },
        {
            "family_role": "far_vocalization_asr_ambiguity",
            "family_key": vocalization_choice[3]["family_key"],
            "shape": vocalization_choice[3]["shape"],
            "family_structural_sha256": vocalization_choice[2],
            "selection_rank_sha256": vocalization_choice[1],
            "risk_diagnostics": vocalization_choice[4],
        },
        {
            "family_role": "far_continuity_anaphora",
            "family_key": continuity_choice[3]["family_key"],
            "shape": continuity_choice[3]["shape"],
            "family_structural_sha256": continuity_choice[2],
            "selection_rank_sha256": continuity_choice[1],
            "risk_diagnostics": continuity_choice[4],
        },
    ]
    clip_keys = sorted(
        {
            interval["clip_key"]
            for family in selected_families
            for interval in family["intervals"]
        }
    )
    if len(selected_families) != EXPECTED_FAMILIES:
        raise CanaryError("SELECTION_FAMILY_COUNT_MISMATCH")
    if not 1 <= len(clip_keys) <= MAX_UNIQUE_CLIPS:
        raise CanaryError("SELECTION_UNIQUE_CLIP_BOUND_VIOLATED")
    return {
        "algorithm": (
            SELECTION_ALGORITHM
        ),
        "version": SELECTION_VERSION,
        "domain": SELECTION_DOMAIN,
        "role_priority": [
            "far_vocalization_asr_ambiguity",
            "far_continuity_anaphora",
        ],
        "exposure_filtering": exposure is not None,
        "machine_diagnostic_fields_read": True,
        "retrieval_score_fields_read": False,
        "manual_semantic_labels_read": False,
        "semantic_ranking_used": False,
        "families": selection_rows,
        "selected_family_hashes": {
            row["family_role"]: row["family_structural_sha256"]
            for row in selection_rows
        },
        "selected_family_keys": {
            row["family_role"]: row["family_key"]
            for row in selection_rows
        },
        "unique_clip_keys": clip_keys,
        "unique_clip_count": len(clip_keys),
        "private_selection_proof": {
            "vocalization_ranking": _ranking_proof(
                vocalization_ranked,
                excluded_by_family_key=excluded_by_family_key,
            ),
            "continuity_ranking": _ranking_proof(
                continuity_ranked,
                excluded_by_family_key=excluded_by_family_key,
            ),
        },
    }


def build_subset_structural(
    structural: Mapping[str, Any], selection: Mapping[str, Any]
) -> dict[str, Any]:
    family_keys = set(selection["selected_family_keys"].values())
    clip_keys = set(selection["unique_clip_keys"])
    families = [
        row for row in structural["families"] if row["family_key"] in family_keys
    ]
    family_order = {
        selection["selected_family_keys"][role]: index
        for index, role in enumerate(FAMILY_ROLES)
    }
    families.sort(key=lambda row: family_order[row["family_key"]])
    targets = [
        {
            **row,
            "family_keys": sorted(
                key for key in row["family_keys"] if key in family_keys
            ),
        }
        for row in structural["targets"]
        if row["clip_key"] in clip_keys
    ]
    query_count = sum(2 * len(row["intervals"]) + 1 for row in families)
    if query_count != EXPECTED_QUERY_COUNT:
        raise CanaryError("CANARY_QUERY_COUNT_MISMATCH")
    subset = {
        "schema_version": (
            "av-trace.p23-102-query-authoring-v2-canary2-subset/1.0"
        ),
        "canary_id": CANARY_ID,
        "source_bundle_file_hashes": structural["file_hashes"],
        "selection": dict(selection),
        "families": families,
        "targets": targets,
        "counts": {
            "families": len(families),
            "local_families": 1,
            "far_families": 2,
            "target_clips": len(targets),
            "queries": query_count,
        },
        "retrieval_scores_read": False,
        "retrieval_vectors_read": False,
        "manual_semantic_labels_read": False,
        "machine_structural_diagnostics_read": True,
    }
    subset["subset_payload_sha256"] = parent.semantic_hash(subset)
    return subset


def _subset_body_hash(subset: Mapping[str, Any]) -> str:
    """Hash the canonical subset body without trusting its stored hash."""

    return parent.semantic_hash(
        {
            key: value
            for key, value in subset.items()
            if key != "subset_payload_sha256"
        }
    )


def _prompt_manifest_expected_hashes(
    subset: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind all prompt material knowable before model execution."""

    manifest = parent.build_prompt_manifest(subset)
    return {
        "base_prompt_manifest_sha256": parent.semantic_hash(manifest),
        "media_factor_combined_prompt_sha256": {
            (
                f"{row['family_key']}:component:"
                f"{row['component_ordinal']}:{row['factor_kind']}"
            ): row["combined_prompt_sha256"]
            for row in [
                *manifest["visual_prompts"],
                *manifest["ambient_prompts"],
            ]
        },
        "composition_system_prompt_sha256": {
            f"{row['family_key']}:family_composition": row[
                "system_prompt_sha256"
            ]
            for row in manifest["composition_contracts"]
        },
        "visual_output_schema_sha256": parent.semantic_hash(
            parent.VISUAL_OUTPUT_SCHEMA
        ),
        "ambient_output_schema_sha256": parent.semantic_hash(
            parent.AMBIENT_OUTPUT_SCHEMA
        ),
        "ambient_registry_sha256": (
            parent.STRUCTURED_AMBIENT_REGISTRY_SHA256
        ),
        "ambient_generator_sha256": parent.AMBIENT_GENERATOR_SHA256,
        "ambient_template_sha256": parent.AMBIENT_TEMPLATE_SHA256,
        "ambient_constraint_kind": parent.AMBIENT_CONSTRAINT_KIND,
        "ambient_constraint_manifest_sha256": (
            parent.AMBIENT_CONSTRAINT_MANIFEST_SHA256
        ),
        "ambient_constraint_leaf_count": (
            parent.EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS
        ),
        "ambient_constraint_reachable_count": (
            parent.EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS
        ),
        "composition_output_schema_sha256": parent.semantic_hash(
            parent.COMPOSITION_OUTPUT_SCHEMA
        ),
    }


def _canary_config(
    *,
    structural: Mapping[str, Any],
    selection: Mapping[str, Any],
    main_pipeline_sha256: str,
    canary_pipeline_sha256: str,
) -> dict[str, Any]:
    return {
        "schema_version": (
            "av-trace.p23-102-query-authoring-v2-canary2-config/2.0"
        ),
        "canary_id": CANARY_ID,
        "main_pipeline_id": parent.PIPELINE_ID,
        "main_pipeline_sha256": main_pipeline_sha256,
        "canary_pipeline_sha256": canary_pipeline_sha256,
        "source_bundle_file_hashes": structural["file_hashes"],
        "selection_algorithm": selection["algorithm"],
        "selection_version": selection["version"],
        "selection_domain": selection["domain"],
        "selected_family_hashes": selection["selected_family_hashes"],
        "family_roles": list(FAMILY_ROLES),
        "maximum_unique_clips": MAX_UNIQUE_CLIPS,
        "expected_query_count": EXPECTED_QUERY_COUNT,
        "visual_initial_authoring_model_calls": EXPECTED_VISUAL_FACTORS,
        "ambient_initial_authoring_model_calls": EXPECTED_AMBIENT_FACTORS,
        "composition_initial_authoring_model_calls": (
            EXPECTED_COMPOSITION_FACTORS
        ),
        "initial_authoring_model_calls": EXPECTED_INITIAL_FACTORS,
        "maximum_schema_only_repair_calls": (
            EXPECTED_MAX_SCHEMA_ONLY_REPAIRS
        ),
        "maximum_authoring_model_calls": (
            EXPECTED_INITIAL_FACTORS + EXPECTED_MAX_SCHEMA_ONLY_REPAIRS
        ),
        "factorized_authoring": True,
        "ambient_model_authored_natural_language": False,
        "ambient_derived_text_model_calls": 0,
        "ambient_registry_sha256": (
            parent.STRUCTURED_AMBIENT_REGISTRY_SHA256
        ),
        "ambient_generator_sha256": parent.AMBIENT_GENERATOR_SHA256,
        "ambient_template_sha256": parent.AMBIENT_TEMPLATE_SHA256,
        "ambient_constraint_kind": parent.AMBIENT_CONSTRAINT_KIND,
        "ambient_constraint_manifest_sha256": (
            parent.AMBIENT_CONSTRAINT_MANIFEST_SHA256
        ),
        "ambient_constraint_leaf_count": (
            parent.EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS
        ),
        "ambient_constraint_reachable_count": (
            parent.EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS
        ),
        "ambient_schema_repair_permitted": False,
        "ordinals_assigned_mechanically": True,
        "composition_media_present": False,
        "composition_relation_kind_only": True,
        "composition_relation_text_generated_mechanically": True,
        "exact_parent_stages": [
            "_extract_exact_clips",
            "_load_omni",
            "_generate_one",
            "_run_asr",
            "_text_embedder",
            "audit_authored_content",
        ],
        "retrieval_scoring_permitted": False,
        "scientific_claims_permitted": False,
    }


def _snapshot_hash(root: Path, snapshot: Path) -> dict[str, Any]:
    """Verify every SHA256SUMS entry and hash the verified snapshot inventory."""

    snapshot_path = _repo_path(root, snapshot)
    sums_path = snapshot_path / "SHA256SUMS"
    if not sums_path.is_file():
        raise CanaryError(f"MODEL_SHA256SUMS_MISSING:{snapshot}")
    records = []
    for line_number, line in enumerate(
        sums_path.read_text(encoding="utf-8").splitlines(), 1
    ):
        stripped = line.strip()
        if not stripped:
            continue
        fields = stripped.split(maxsplit=1)
        if len(fields) != 2 or len(fields[0]) != 64:
            raise CanaryError(
                f"MODEL_SHA256SUMS_INVALID:{snapshot}:{line_number}"
            )
        expected, declared_name = fields
        name = Path(declared_name.strip().lstrip("*")).name
        path = snapshot_path / name
        if not path.is_file():
            raise CanaryError(f"MODEL_FILE_MISSING:{snapshot}:{name}")
        observed = parent.file_sha256(path)
        if observed != expected:
            raise CanaryError(f"MODEL_FILE_HASH_MISMATCH:{snapshot}:{name}")
        records.append(
            {"name": name, "sha256": f"sha256:{observed}", "bytes": path.stat().st_size}
        )
    if not records:
        raise CanaryError(f"MODEL_SHA256SUMS_EMPTY:{snapshot}")
    records.sort(key=lambda row: row["name"])
    return {
        "snapshot": str(snapshot),
        "verified_file_count": len(records),
        "snapshot_content_sha256": parent.semantic_hash(records),
        "sha256s_file_sha256": "sha256:" + parent.file_sha256(sums_path),
    }


def _model_hashes(root: Path) -> dict[str, Any]:
    return {
        name: _snapshot_hash(root, snapshot)
        for name, snapshot in (
            ("authoring_omni", parent.OMNI_SNAPSHOT),
            ("asr_leakage_whisper", parent.WHISPER_SNAPSHOT),
            ("visual_text_audit_siglip2", parent.SIGLIP_SNAPSHOT),
            ("ambient_text_audit_clap", parent.CLAP_SNAPSHOT),
        )
    }


def _input_fingerprints(
    root: Path,
    *,
    media: Path,
    structural: Mapping[str, Any],
    selection: Mapping[str, Any],
    selection_inputs: Mapping[str, Any],
) -> dict[str, Any]:
    media_path = _repo_path(root, media)
    if not media_path.is_file():
        raise CanaryError("SOURCE_MEDIA_MISSING")
    main_pipeline_sha256 = _parent_tool_hash(root)
    config = _canary_config(
        structural=structural,
        selection=selection,
        main_pipeline_sha256=main_pipeline_sha256,
        canary_pipeline_sha256=_canary_tool_hash(root),
    )
    subset = build_subset_structural(structural, selection)
    commitment_hashes = {
        key: selection_inputs[key]
        for key in (
            "private_governance_ledger_sha256",
            "private_governance_commitment_sha256",
            "public_selection_commitment_sha256",
        )
    }
    return {
        "canary_config_sha256": parent.semantic_hash(config),
        "main_pipeline_sha256": main_pipeline_sha256,
        "canary_pipeline_sha256": _canary_tool_hash(root),
        "selected_family_hashes": selection["selected_family_hashes"],
        "selection_algorithm": selection["algorithm"],
        "selection_version": selection["version"],
        **commitment_hashes,
        "bundle_file_hashes": structural["file_hashes"],
        "selection_input_hashes": dict(selection_inputs),
        "model_hashes": _model_hashes(root),
        "media_sha256": "sha256:" + parent.file_sha256(media_path),
        "subset_payload_sha256": _subset_body_hash(subset),
        "prompt_manifest_expected_hashes": (
            _prompt_manifest_expected_hashes(subset)
        ),
    }


def _selection_context(
    root: Path, structural: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    diagnostics = _load_machine_diagnostics(root)
    reference = _load_v15_local_reference(root)
    ledger = _load_private_governance_ledger(root)
    r21_hashes = _r21_failure_evidence_hashes(root, ledger)
    source_hashes = _selection_source_hashes(
        structural, diagnostics, reference, r21_hashes
    )
    family_rows = structural.get("documents", {}).get(
        "family_registry.json", {}
    ).get("families")
    if not isinstance(family_rows, list):
        raise CanaryError("MACHINE_FAMILY_REGISTRY_ROWS_MISSING")
    by_id = {
        str(row["family_id"]): row
        for row in family_rows
        if isinstance(row, Mapping) and "family_id" in row
    }
    selection = select_canary_families(
        structural,
        machine_family_rows=by_id,
        speech_rows=diagnostics["speech_rows"],
        v15_local_hash=reference["local_family_structural_sha256"],
        exposure=ledger["exposure"],
    )
    selection_inputs = dict(source_hashes)
    public = parent.load_json(_repo_path(root, PUBLIC_SELECTION_COMMITMENT))
    if public.get("input_hashes") != _public_selection_input_hashes(
        source_hashes
    ):
        raise CanaryError("PUBLIC_SELECTION_COMMITMENT_INPUT_DRIFT")
    expected_private_selection = _private_selection_record(
        structural, selection
    )
    if ledger["selection"] != expected_private_selection:
        raise CanaryError("PRIVATE_GOVERNANCE_SELECTION_DRIFT")
    if ledger["input_hashes"] != source_hashes:
        raise CanaryError("PRIVATE_GOVERNANCE_INPUT_HASH_DRIFT")
    if ledger["r21_failure_evidence_hashes"] != r21_hashes:
        raise CanaryError("PRIVATE_GOVERNANCE_R21_EVIDENCE_DRIFT")
    commitment_hashes = _public_commitment_hashes(root)
    selection_inputs.update(commitment_hashes)
    # Full reserve rankings are confined to the private governance ledger.
    selection = {
        key: value
        for key, value in selection.items()
        if key != "private_selection_proof"
    }
    return selection, selection_inputs


def validate_plan(
    root: Path = ROOT, plan: Path = DEFAULT_PLAN
) -> dict[str, Any]:
    path = _repo_path(root, plan)
    if not path.is_file():
        raise CanaryError("CANARY_PLAN_MISSING")
    value = parent.load_json(path)
    if value.get("canary_id") != CANARY_ID:
        raise CanaryError("CANARY_PLAN_ID_MISMATCH")
    if (
        value.get("schema_version") != PLAN_SCHEMA_VERSION
        or value.get("created_date") != CURRENT_DATE
        or value.get("decision") != READY
        or value.get("scope", {}).get("old_authorization_receipts_valid")
        is not False
        or value.get("scope", {}).get("plan_status_current") is not True
        or value.get("scope", {}).get(
            "r22f_public_surface_complete_scan_active"
        )
        is not True
        or value.get("scope", {}).get(
            "r22d_marker_fail_stop_persistence_active"
        )
        is not True
    ):
        raise CanaryError("CANARY_PLAN_R22F_CONTRACT_INVALID")
    expected = parent.semantic_hash(
        {key: item for key, item in value.items() if key != "plan_payload_sha256"}
    )
    if value.get("plan_payload_sha256") != expected:
        raise CanaryError("CANARY_PLAN_HASH_MISMATCH")
    structural = parent.load_structural_bundle(root, DEFAULT_BUNDLE)
    selection, selection_inputs = _selection_context(root, structural)
    subset = build_subset_structural(structural, selection)
    if value.get("planned_subset_counts") != subset["counts"]:
        raise CanaryError("CANARY_PLAN_SELECTION_COUNT_DRIFT")
    plan_selection = value.get("selection")
    if plan_selection != {
        "algorithm": SELECTION_ALGORITHM,
        "version": SELECTION_VERSION,
        "domain": SELECTION_DOMAIN,
        "role_priority": [
            "far_vocalization_asr_ambiguity",
            "far_continuity_anaphora",
        ],
        "exact_family_count": EXPECTED_FAMILIES,
        "maximum_unique_clip_count": MAX_UNIQUE_CLIPS,
        "actual_unique_clip_count": MAX_UNIQUE_CLIPS,
        "expected_query_count": EXPECTED_QUERY_COUNT,
        "exposure_filtering_active": True,
        "machine_registry_and_index_diagnostics_only": True,
        "structural_hash_tie_breaks_only": True,
        "retrieval_scores_rankings_outcomes_or_vectors_read": False,
        "manual_semantic_labels_read": False,
        "status_wording": (
            "one historical anchor role plus two opaque committed roles; "
            "private identities remain restricted"
        ),
    }:
        raise CanaryError("CANARY_PLAN_SELECTION_CONTRACT_INVALID")
    governance = value.get("selection_governance")
    if governance != {
        "private_governance_ledger_sha256": selection_inputs[
            "private_governance_ledger_sha256"
        ],
        "private_governance_commitment_sha256": selection_inputs[
            "private_governance_commitment_sha256"
        ],
        "public_selection_commitment_sha256": selection_inputs[
            "public_selection_commitment_sha256"
        ],
        "selection_algorithm": SELECTION_ALGORITHM,
        "selection_version": SELECTION_VERSION,
        "replacement_generation": 1,
        "maximum_replacements": 2,
        "run_attempt_limit": 1,
        "redraw_after_output_permitted": False,
        "runtime_fallback_permitted": False,
        "no_human_selection": True,
        "no_retrieval_selection": True,
        "no_future_output_selection": True,
        "public_surface_private_leakage_scan": True,
        "public_surface_scan_scope": (
            "repo_root_recursive_all_regular_files"
        ),
        "public_surface_scan_policy_version": (
            PUBLIC_SURFACE_SCAN_POLICY_VERSION
        ),
        "public_surface_scan_policy_sha256": (
            _public_surface_scan_policy_sha256()
        ),
        "public_surface_raw_bytes_private_token_scan": True,
        "public_surface_binary_files_raw_scanned": True,
        "public_surface_unknown_suffix_utf8_validated": True,
        "public_surface_strict_utf8": True,
        "public_surface_undecodable_failure_code": (
            "PUBLIC_SURFACE_UNDECODABLE_TEXT"
        ),
        "public_surface_binary_control_failure_code": (
            "PUBLIC_SURFACE_BINARY_CONTROL_BYTES"
        ),
        "public_surface_size_based_skip_permitted": False,
        "one_shot_attempt_marker": True,
        "marker_fail_stop_persistence": True,
    }:
        raise CanaryError("CANARY_PLAN_GOVERNANCE_BINDING_INVALID")
    result = dict(value)
    current_main = _parent_tool_hash(root)
    current_canary = _canary_tool_hash(root)
    authorization = value.get("authorization")
    if (
        not isinstance(authorization, Mapping)
        or set(authorization)
        != {
            "schema_version",
            "separate_receipt_required",
            "created_by_this_task",
            "main_pipeline_sha256",
            "canary2_pipeline_sha256",
            "required_bindings",
        }
        or authorization.get("schema_version")
        != AUTHORIZATION_SCHEMA_VERSION
        or authorization.get("separate_receipt_required") is not True
        or authorization.get("created_by_this_task") is not False
        or authorization.get("main_pipeline_sha256")
        != value.get("main_pipeline_sha256")
        or authorization.get("canary2_pipeline_sha256")
        != value.get("canary2_pipeline_sha256")
        or authorization.get("main_pipeline_sha256") != current_main
        or authorization.get("canary2_pipeline_sha256") != current_canary
        or authorization.get("required_bindings")
        != AUTHORIZATION_REQUIRED_BINDINGS
    ):
        raise CanaryError("CANARY_PLAN_EMBEDDED_AUTHORIZATION_INVALID")
    result["current_main_pipeline_sha256"] = current_main
    result["current_canary_pipeline_sha256"] = current_canary
    result["historical_plan_pipeline_hash_current"] = True
    result["current"] = True
    result["old_authorization_receipts_valid"] = False
    result["selected_family_hashes"] = selection["selected_family_hashes"]
    result["selected_family_keys"] = selection["selected_family_keys"]
    result["unique_clip_count"] = selection["unique_clip_count"]
    result["selection_input_hashes"] = selection_inputs
    if (
        value.get("execution_contract", {}).get(
            "ambient_token_constraint"
        )
        != parent.ambient_constraint_contract()
    ):
        raise CanaryError("CANARY_PLAN_AMBIENT_CONSTRAINT_BINDING_INVALID")
    public_surface = value.get("execution_contract", {}).get(
        "public_surface_confidentiality"
    )
    if public_surface != {
        "historical_public_identity_exemption_from_private_ledger": True,
        "private_token_values_reported": False,
        "r22_fresh_selected_private_tokens_permitted": False,
        "unselected_reserve_private_tokens_permitted": False,
        "scan_scope": "repo_root_recursive_all_regular_files",
        "scan_policy_version": PUBLIC_SURFACE_SCAN_POLICY_VERSION,
        "scan_policy_sha256": _public_surface_scan_policy_sha256(),
        "restricted_prefixes": ["data/restricted"],
        "excluded_directory_names": sorted(
            PUBLIC_SURFACE_EXCLUDED_DIR_NAMES
        ),
        "excluded_directory_prefixes": [
            path.as_posix()
            for path in PUBLIC_SURFACE_EXCLUDED_DIR_PREFIXES
        ],
        "binary_directory_prefixes": [
            path.as_posix()
            for path in PUBLIC_SURFACE_BINARY_DIR_PREFIXES
        ],
        "allowlisted_generated_private_output_prefixes": [
            path.as_posix()
            for path in PUBLIC_SURFACE_ALLOWLISTED_GENERATED_PRIVATE_OUTPUTS
        ],
        "binary_suffixes": sorted(PUBLIC_SURFACE_BINARY_SUFFIXES),
        "binary_filenames": sorted(PUBLIC_SURFACE_BINARY_FILENAMES),
        "chunk_bytes": PUBLIC_SURFACE_CHUNK_BYTES,
        "size_based_skip_permitted": False,
        "raw_bytes_private_token_scan": True,
        "binary_files_raw_scanned": True,
        "unknown_suffix_utf8_validated": True,
        "strict_utf8_decoding": True,
        "stat_open_read_fail_closed": True,
        "undecodable_text_failure_code": (
            "PUBLIC_SURFACE_UNDECODABLE_TEXT"
        ),
        "binary_control_failure_code": (
            "PUBLIC_SURFACE_BINARY_CONTROL_BYTES"
        ),
    }:
        raise CanaryError(
            "CANARY_PLAN_PUBLIC_SURFACE_CONFIDENTIALITY_INVALID"
        )
    one_shot = value.get("execution_contract", {}).get(
        "pre_execution_one_shot"
    )
    if not isinstance(one_shot, Mapping) or any(
        one_shot.get(key) is not True
        for key in (
            "file_fsync_required",
            "parent_directory_fsync_required",
            "post_create_chmod_required",
            "post_exclusive_create_failure_retains_inode",
            "partial_or_invalid_marker_consumes_receipt",
        )
    ) or one_shot.get(
        "partial_or_invalid_marker_validates_as_success"
    ) is not False:
        raise CanaryError("CANARY_PLAN_MARKER_FAIL_STOP_INVALID")
    return result


def plan_status(root: Path) -> dict[str, Any]:
    value = validate_plan(root)
    return {
        "status": READY,
        "repair_status": SEMANTIC_GATES_READY,
        "constrained_json_status": CONSTRAINED_JSON_READY,
        "plan_payload_sha256": value["plan_payload_sha256"],
        "unique_clip_count": value["unique_clip_count"],
        "set_status": (
            "EXPOSED_ANCHOR_PLUS_TWO_FRESH_RESERVES_"
            "NOT_UNTOUCHED_NOT_REPLICATION"
        ),
        "current_main_pipeline_sha256": value[
            "current_main_pipeline_sha256"
        ],
        "current_canary_pipeline_sha256": value[
            "current_canary_pipeline_sha256"
        ],
        "historical_plan_pipeline_hash_current": value[
            "historical_plan_pipeline_hash_current"
        ],
        "current": value["current"],
        "old_authorization_receipts_valid": False,
        "selection_algorithm": SELECTION_ALGORITHM,
        "selection_version": SELECTION_VERSION,
        "private_governance_ledger_sha256": value["selection_governance"][
            "private_governance_ledger_sha256"
        ],
        "public_selection_commitment_sha256": value[
            "selection_governance"
        ]["public_selection_commitment_sha256"],
        "public_surface_scan_policy_version": (
            PUBLIC_SURFACE_SCAN_POLICY_VERSION
        ),
        "public_surface_scan_policy_sha256": (
            _public_surface_scan_policy_sha256()
        ),
        "ambient_registry_sha256": (
            parent.STRUCTURED_AMBIENT_REGISTRY_SHA256
        ),
        "ambient_generator_sha256": parent.AMBIENT_GENERATOR_SHA256,
        "ambient_template_sha256": parent.AMBIENT_TEMPLATE_SHA256,
        "structured_ambient_combination_count": (
            parent.EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS
        ),
        "structured_ambient_unique_pair_count": (
            parent.EXPECTED_STRUCTURED_AMBIENT_UNIQUE_PAIRS
        ),
        "ambient_constraint_kind": parent.AMBIENT_CONSTRAINT_KIND,
        "ambient_constraint_manifest_sha256": (
            parent.AMBIENT_CONSTRAINT_MANIFEST_SHA256
        ),
        "ambient_constraint_leaf_count": (
            parent.EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS
        ),
        "ambient_constraint_reachable_count": (
            parent.EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS
        ),
        "real_execution_performed": False,
        "authorization_receipt_created": False,
        "model_calls": 0,
        "media_decodes": 0,
        "retrieval_scoring_executed": False,
    }


def preflight(
    root: Path = ROOT,
    *,
    bundle: Path = DEFAULT_BUNDLE,
    media: Path = DEFAULT_MEDIA,
    output: Path = DEFAULT_OUTPUT,
    authorization: Path | None = None,
) -> dict[str, Any]:
    failures = []
    try:
        structural = parent.load_structural_bundle(root, bundle)
        selection, selection_inputs = _selection_context(root, structural)
        subset = build_subset_structural(structural, selection)
    except (parent.AuthoringError, CanaryError) as exc:
        return {
            "schema_version": (
                "av-trace.p23-102-query-authoring-v2-canary2-preflight/2.0"
            ),
            "canary_id": CANARY_ID,
            "date": CURRENT_DATE,
            "status": "FAIL_CLOSED",
            "failures": [str(exc)],
            "model_calls": 0,
            "media_decodes": 0,
        }

    parent_result = parent.preflight(root, bundle=bundle, media=media)
    failures.extend(parent_result["failures"])
    public_surface_scan = None
    try:
        public_surface_scan = scan_public_surface_for_private_leakage(root)
    except PublicSurfaceScanError as exc:
        public_surface_scan = exc.report
        failures.append(str(exc))
    except CanaryError as exc:
        failures.append(str(exc))
    fingerprints = None
    if not failures:
        try:
            fingerprints = _input_fingerprints(
                root,
                media=media,
                structural=structural,
                selection=selection,
                selection_inputs=selection_inputs,
            )
            fingerprints["subset_payload_sha256"] = _subset_body_hash(subset)
            fingerprints["prompt_manifest_expected_hashes"] = (
                _prompt_manifest_expected_hashes(subset)
            )
        except CanaryError as exc:
            failures.append(str(exc))
    output_relative = _relative_repo_path(root, output)
    if output_relative != DEFAULT_OUTPUT.as_posix():
        failures.append("CANARY_OUTPUT_PATH_NOT_FIXED")
    output_path = _repo_path(root, output)
    if output_path.exists():
        failures.append("CANARY_OUTPUT_ALREADY_EXISTS")
    one_shot_artifacts: dict[str, Any] = {
        "output_clear": not output_path.exists(),
        "attempt_marker_created": False,
        "authorization_specific_paths_require_receipt": (
            authorization is None
        ),
    }
    if authorization is not None and fingerprints is not None:
        try:
            authorization_value = validate_authorization(
                root,
                authorization,
                fingerprints=fingerprints,
                output=output,
            )
            paths = authorization_governance_paths(
                output_path,
                str(authorization_value["authorization_id"]),
            )
            one_shot_artifacts.update(
                {
                    "authorization_specific_paths_require_receipt": False,
                    "attempt_marker_clear": not paths[
                        "attempt_marker"
                    ].exists(),
                    "failure_capsule_clear": not paths[
                        "failure_capsule"
                    ].exists(),
                }
            )
            if any(path.exists() for path in paths.values()):
                failures.append(
                    "CANARY_ONE_SHOT_AUTHORIZATION_ALREADY_CONSUMED"
                )
        except CanaryError as exc:
            failures.append(str(exc))
    return {
        "schema_version": (
            "av-trace.p23-102-query-authoring-v2-canary2-preflight/2.0"
        ),
        "canary_id": CANARY_ID,
        "date": CURRENT_DATE,
        "status": "READY" if not failures else "FAIL_CLOSED",
        "failures": failures,
        "selection": selection,
        "selection_input_hashes": selection_inputs,
        "subset_counts": subset["counts"],
        "input_fingerprints": fingerprints,
        "source_media": parent_result["source_media"],
        "models": parent_result["models"],
        "decode_backend": parent_result["decode_backend"],
        "one_shot_artifacts": one_shot_artifacts,
        "public_surface_scan": public_surface_scan,
        "public_surface_scan_policy_version": (
            PUBLIC_SURFACE_SCAN_POLICY_VERSION
        ),
        "public_surface_scan_policy_sha256": (
            _public_surface_scan_policy_sha256()
        ),
        "main_pipeline_reused": True,
        "structured_ambient_combination_count": (
            parent.EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS
        ),
        "structured_ambient_unique_pair_count": (
            parent.EXPECTED_STRUCTURED_AMBIENT_UNIQUE_PAIRS
        ),
        "model_calls": 0,
        "media_decodes": 0,
        "network_required": False,
        "retrieval_scoring_permitted": False,
    }


AUTHORIZATION_FIELDS = frozenset(
    {
        "schema_version",
        "canary_id",
        "decision",
        "authorization_id",
        "authorized_at",
        "single_local_run",
        "canary_config_sha256",
        "selected_family_hashes",
        "selection_algorithm",
        "selection_version",
        "private_governance_ledger_sha256",
        "private_governance_commitment_sha256",
        "public_selection_commitment_sha256",
        "main_pipeline_sha256",
        "canary_pipeline_sha256",
        "bundle_file_hashes",
        "selection_input_hashes",
        "model_hashes",
        "media_sha256",
        "subset_payload_sha256",
        "prompt_manifest_expected_hashes",
        "output_path",
    }
)


def validate_authorization(
    root: Path,
    authorization_path: Path,
    *,
    fingerprints: Mapping[str, Any],
    output: Path,
) -> dict[str, Any]:
    path = _repo_path(root, authorization_path)
    if not path.is_file():
        raise CanaryError("CANARY_EXECUTION_AUTHORIZATION_MISSING")
    value = parent.load_json(path)
    if not isinstance(value, Mapping) or set(value) != AUTHORIZATION_FIELDS:
        raise CanaryError("CANARY_EXECUTION_AUTHORIZATION_SCHEMA_INVALID")
    if (
        value["schema_version"] != AUTHORIZATION_SCHEMA_VERSION
        or value["canary_id"] != CANARY_ID
        or value["decision"] != "AUTHORIZED"
        or value["single_local_run"] is not True
        or not isinstance(value["authorization_id"], str)
        or not value["authorization_id"].strip()
        or not isinstance(value["authorized_at"], str)
        or not value["authorized_at"].strip()
        or value["canary_config_sha256"]
        != fingerprints["canary_config_sha256"]
        or value["selected_family_hashes"]
        != fingerprints["selected_family_hashes"]
        or value["selection_algorithm"]
        != fingerprints["selection_algorithm"]
        or value["selection_version"] != fingerprints["selection_version"]
        or value["private_governance_ledger_sha256"]
        != fingerprints["private_governance_ledger_sha256"]
        or value["private_governance_commitment_sha256"]
        != fingerprints["private_governance_commitment_sha256"]
        or value["public_selection_commitment_sha256"]
        != fingerprints["public_selection_commitment_sha256"]
        or value["main_pipeline_sha256"]
        != fingerprints["main_pipeline_sha256"]
        or value["canary_pipeline_sha256"]
        != fingerprints["canary_pipeline_sha256"]
        or value["bundle_file_hashes"] != fingerprints["bundle_file_hashes"]
        or value["selection_input_hashes"]
        != fingerprints["selection_input_hashes"]
        or value["model_hashes"] != fingerprints["model_hashes"]
        or value["media_sha256"] != fingerprints["media_sha256"]
        or value["subset_payload_sha256"]
        != fingerprints["subset_payload_sha256"]
        or value["prompt_manifest_expected_hashes"]
        != fingerprints["prompt_manifest_expected_hashes"]
        or value["output_path"] != _relative_repo_path(root, output)
    ):
        raise CanaryError("CANARY_EXECUTION_AUTHORIZATION_SCOPE_MISMATCH")
    return dict(value)


def _safe_authorization_id(authorization_id: str) -> str:
    safe_id = re.sub(
        r"[^A-Za-z0-9._-]+", "-", authorization_id
    ).strip("-")
    if not safe_id:
        raise CanaryError("CANARY_AUTHORIZATION_ID_PATH_INVALID")
    return safe_id


def attempt_marker_path(
    output_path: Path, authorization_id: str
) -> Path:
    safe_id = _safe_authorization_id(authorization_id)
    return output_path.with_name(f"{output_path.name}.attempt-{safe_id}.json")


def authorization_governance_paths(
    output_path: Path, authorization_id: str
) -> dict[str, Path]:
    return {
        "output": output_path,
        "failure_capsule": parent.failure_capsule_path(
            output_path, authorization_id
        ),
        "attempt_marker": attempt_marker_path(
            output_path, authorization_id
        ),
    }


def _attempt_marker_value(
    *,
    root: Path,
    marker_path: Path,
    authorization_path: Path,
    authorization_value: Mapping[str, Any],
    fingerprints: Mapping[str, Any],
) -> dict[str, Any]:
    receipt_path = _repo_path(root, authorization_path)
    return {
        "schema_version": ATTEMPT_MARKER_SCHEMA_VERSION,
        "canary_id": CANARY_ID,
        "authorization_id": authorization_value["authorization_id"],
        "authorization_receipt_path": _relative_repo_path(
            root, receipt_path
        ),
        "authorization_receipt_sha256": (
            "sha256:" + parent.file_sha256(receipt_path)
        ),
        "input_fingerprints": dict(fingerprints),
        "input_fingerprints_sha256": parent.semantic_hash(fingerprints),
        "private_governance_ledger_sha256": fingerprints[
            "private_governance_ledger_sha256"
        ],
        "private_governance_commitment_sha256": fingerprints[
            "private_governance_commitment_sha256"
        ],
        "public_selection_commitment_sha256": fingerprints[
            "public_selection_commitment_sha256"
        ],
        "output_path": authorization_value["output_path"],
        "attempt_marker_path": _relative_repo_path(root, marker_path),
        "started_at": (
            time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        ),
    }


def _marker_write(handle: Any, payload: bytes) -> int:
    return int(handle.write(payload))


def _marker_flush(handle: Any) -> None:
    handle.flush()


def _marker_file_fsync(descriptor: int) -> None:
    os.fsync(descriptor)


def _marker_chmod(marker_path: Path) -> None:
    os.chmod(marker_path, 0o600)


def _marker_parent_directory_fsync(parent_path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(parent_path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _create_attempt_marker(
    *,
    root: Path,
    marker_path: Path,
    authorization_path: Path,
    authorization_value: Mapping[str, Any],
    fingerprints: Mapping[str, Any],
) -> dict[str, Any]:
    marker_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    marker = _attempt_marker_value(
        root=root,
        marker_path=marker_path,
        authorization_path=authorization_path,
        authorization_value=authorization_value,
        fingerprints=fingerprints,
    )
    payload = (
        json.dumps(marker, indent=2, sort_keys=True, ensure_ascii=False)
        + "\n"
    ).encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(marker_path, flags, 0o600)
    except FileExistsError as exc:
        raise CanaryError(
            "CANARY_ONE_SHOT_AUTHORIZATION_ALREADY_CONSUMED"
        ) from exc
    handle = None
    try:
        handle = os.fdopen(descriptor, "wb")
        descriptor = -1
        written = _marker_write(handle, payload)
        if written != len(payload):
            raise OSError(
                errno.EIO,
                "attempt marker write was incomplete",
            )
        _marker_flush(handle)
        _marker_file_fsync(handle.fileno())
        handle.close()
        handle = None
        _marker_chmod(marker_path)
        _marker_parent_directory_fsync(marker_path.parent)
    except BaseException as exc:
        if handle is not None:
            with contextlib.suppress(BaseException):
                handle.close()
        if descriptor >= 0:
            with contextlib.suppress(OSError):
                os.close(descriptor)
        # O_EXCL is the consumption boundary.  Once the inode exists it is
        # never removed, even if persistence or permission hardening fails.
        raise CanaryError(
            "CANARY_ATTEMPT_MARKER_PERSISTENCE_FAILED"
        ) from exc
    if stat.S_IMODE(marker_path.stat().st_mode) != 0o600:
        raise CanaryError("CANARY_ATTEMPT_MARKER_MODE_INVALID")
    return marker


def _validate_attempt_marker(
    *,
    root: Path,
    marker_path: Path,
    authorization_path: Path,
    authorization_value: Mapping[str, Any],
    fingerprints: Mapping[str, Any],
) -> dict[str, Any]:
    if not marker_path.is_file():
        raise CanaryError("CANARY_ATTEMPT_MARKER_MISSING")
    if stat.S_IMODE(marker_path.stat().st_mode) != 0o600:
        raise CanaryError("CANARY_ATTEMPT_MARKER_MODE_INVALID")
    try:
        marker = parent.load_json(marker_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CanaryError("CANARY_ATTEMPT_MARKER_INVALID") from exc
    expected_fields = {
        "schema_version",
        "canary_id",
        "authorization_id",
        "authorization_receipt_path",
        "authorization_receipt_sha256",
        "input_fingerprints",
        "input_fingerprints_sha256",
        "private_governance_ledger_sha256",
        "private_governance_commitment_sha256",
        "public_selection_commitment_sha256",
        "output_path",
        "attempt_marker_path",
        "started_at",
    }
    if not isinstance(marker, Mapping) or set(marker) != expected_fields:
        raise CanaryError("CANARY_ATTEMPT_MARKER_SCHEMA_INVALID")
    if (
        marker["schema_version"] != ATTEMPT_MARKER_SCHEMA_VERSION
        or marker["canary_id"] != CANARY_ID
        or marker["authorization_id"]
        != authorization_value["authorization_id"]
        or marker["authorization_receipt_path"]
        != _relative_repo_path(root, _repo_path(root, authorization_path))
        or marker["authorization_receipt_sha256"]
        != "sha256:"
        + parent.file_sha256(_repo_path(root, authorization_path))
        or marker["input_fingerprints"] != fingerprints
        or marker["input_fingerprints_sha256"]
        != parent.semantic_hash(fingerprints)
        or marker["private_governance_ledger_sha256"]
        != fingerprints["private_governance_ledger_sha256"]
        or marker["private_governance_commitment_sha256"]
        != fingerprints["private_governance_commitment_sha256"]
        or marker["public_selection_commitment_sha256"]
        != fingerprints["public_selection_commitment_sha256"]
        or marker["output_path"] != authorization_value["output_path"]
        or marker["attempt_marker_path"]
        != _relative_repo_path(root, marker_path)
        or not isinstance(marker["started_at"], str)
        or not marker["started_at"]
    ):
        raise CanaryError("CANARY_ATTEMPT_MARKER_BINDING_INVALID")
    return dict(marker)


@contextlib.contextmanager
def _parent_subset_counts() -> Iterator[None]:
    original_families = parent.EXPECTED_FAMILIES
    original_queries = parent.EXPECTED_QUERY_COUNT
    parent.EXPECTED_FAMILIES = EXPECTED_FAMILIES
    parent.EXPECTED_QUERY_COUNT = EXPECTED_QUERY_COUNT
    try:
        yield
    finally:
        parent.EXPECTED_FAMILIES = original_families
        parent.EXPECTED_QUERY_COUNT = original_queries


def _peak_rss_bytes() -> int:
    # Linux reports ru_maxrss in KiB.
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024


def _safe_target_records(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    safe = []
    for row in records:
        value = dict(row)
        value["video_path"] = (
            f"ephemeral/clips/{row['clip_key']}/video_rgb_uint8.npy"
        )
        value["audio_path"] = (
            f"ephemeral/clips/{row['clip_key']}/audio_mono_16khz_float32.npy"
        )
        value["retained_after_seal"] = False
        safe.append(value)
    return safe


def _model_identities() -> dict[str, Any]:
    return {
        "authoring": {
            "repo_id": "Qwen/Qwen2.5-Omni-7B",
            "revision": "ae9e1690543ffd5c0221dc27f79834d0294cba00",
            "snapshot": str(parent.OMNI_SNAPSHOT),
            "generation": {
                "do_sample": False,
                "max_new_tokens": parent.MAX_NEW_TOKENS,
                "seed": 0,
                "constrained_json": True,
                "assistant_prefill": parent.JSON_ASSISTANT_PREFILL,
                "ambient_constraint": parent.ambient_constraint_contract(),
                "stop_boundary": (
                    "ambient leaf plus EOS/stop; JSON boundary for "
                    "visual/composition"
                ),
            },
        },
        "asr_leakage_audit": {
            "repo_id": "openai/whisper-tiny.en",
            "revision": "87c7102498dcde7456f24cfd30239ca606ed9063",
            "snapshot": str(parent.WHISPER_SNAPSHOT),
        },
        "visual_text_collision_audit": {
            "repo_id": "google/siglip2-base-patch16-224",
            "revision": "75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2",
            "snapshot": str(parent.SIGLIP_SNAPSHOT),
        },
        "ambient_text_collision_audit": {
            "repo_id": "laion/clap-htsat-unfused",
            "revision": "8fa0f1c6d0433df6e97c127f64b2a1d6c0dcda8a",
            "snapshot": str(parent.CLAP_SNAPSHOT),
        },
    }


def _contract_value(
    *,
    root: Path,
    authorization_path: Path,
    authorization_value: Mapping[str, Any],
    fingerprints: Mapping[str, Any],
    selection: Mapping[str, Any],
    selection_inputs: Mapping[str, Any],
    subset: Mapping[str, Any],
    attempt_marker_path_value: Path,
    attempt_marker: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": (
            CONTRACT_SCHEMA_VERSION
        ),
        "canary_id": CANARY_ID,
        "date": CURRENT_DATE,
        "authorization": dict(authorization_value),
        "authorization_receipt_path": _relative_repo_path(
            root, authorization_path
        ),
        "authorization_receipt_sha256": (
            "sha256:"
            + parent.file_sha256(_repo_path(root, authorization_path))
        ),
        "attempt_marker_path": _relative_repo_path(
            root, attempt_marker_path_value
        ),
        "attempt_marker_sha256": (
            "sha256:" + parent.file_sha256(attempt_marker_path_value)
        ),
        "attempt_marker": dict(attempt_marker),
        "input_fingerprints": dict(fingerprints),
        "selection_governance_bindings": {
            "selection_algorithm": fingerprints["selection_algorithm"],
            "selection_version": fingerprints["selection_version"],
            "private_governance_ledger_sha256": fingerprints[
                "private_governance_ledger_sha256"
            ],
            "private_governance_commitment_sha256": fingerprints[
                "private_governance_commitment_sha256"
            ],
            "public_selection_commitment_sha256": fingerprints[
                "public_selection_commitment_sha256"
            ],
            "replacement_generation": 1,
            "maximum_replacements": 2,
            "run_attempt_limit": 1,
            "redraw_after_output_permitted": False,
            "runtime_fallback_permitted": False,
        },
        "selection": dict(selection),
        "selection_input_hashes": dict(selection_inputs),
        "subset_payload_sha256": _subset_body_hash(subset),
        "prompt_manifest_expected_hashes": (
            _prompt_manifest_expected_hashes(subset)
        ),
        "model_identities": _model_identities(),
        "factorization": {
            "visual_initial_calls": EXPECTED_VISUAL_FACTORS,
            "ambient_initial_calls": EXPECTED_AMBIENT_FACTORS,
            "composition_initial_calls": EXPECTED_COMPOSITION_FACTORS,
            "total_initial_factor_calls": EXPECTED_INITIAL_FACTORS,
            "ordinals_assigned_mechanically": True,
            "composition_relation_kind_by_shape": dict(
                parent.RELATION_KIND_BY_SHAPE
            ),
            "composition_frozen_shape_and_count_bound": True,
            "composition_direction_generated_mechanically": True,
            "composition_relation_text_generated_mechanically": True,
            "composition_model_authored_natural_language": False,
            "ambient_model_authored_natural_language": False,
            "ambient_derived_text_model_calls": 0,
            "ambient_registry_sha256": (
                parent.STRUCTURED_AMBIENT_REGISTRY_SHA256
            ),
            "ambient_generator_sha256": parent.AMBIENT_GENERATOR_SHA256,
            "ambient_template_sha256": parent.AMBIENT_TEMPLATE_SHA256,
            "ambient_constraint_kind": parent.AMBIENT_CONSTRAINT_KIND,
            "ambient_constraint_manifest": json.loads(
                parent.canonical_bytes(parent.AMBIENT_CONSTRAINT_MANIFEST)
            ),
            "ambient_constraint_manifest_sha256": (
                parent.AMBIENT_CONSTRAINT_MANIFEST_SHA256
            ),
            "ambient_constraint_leaf_count": (
                parent.EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS
            ),
            "ambient_constraint_reachable_count": (
                parent.EXPECTED_STRUCTURED_AMBIENT_COMBINATIONS
            ),
            "ambient_schema_repair_permitted": False,
            "composition_media_present": False,
            "accepted_factor_manifest_sealed": True,
            "final_rows_bind_exact_accepted_factor": True,
            "cross_factor_fill_or_substitution_permitted": False,
            "ambient_semantic_tuple_duplicate_gate": {
                "same_family_duplicate": "FAIL_CLOSED",
                "global_collision_ledger_emitted": True,
                "automatic_rewrite_permitted": False,
                "authoring_retry_permitted": False,
                "replacement_governance": "outer_R22_selection_only",
            },
            "binding_cardinality_failure": "MODEL_COMPONENT_COUNT_MISMATCH",
        },
        "parent_pipeline_reused": True,
        "retrieval_scoring_permitted": False,
        "retrieval_scoring_executed": False,
        "scientific_claims_permitted": False,
    }


def _gate_findings(audits: Mapping[str, Any]) -> dict[str, Any]:
    semantic = audits.get("semantic_authoring_gates", {})
    if not isinstance(semantic, Mapping):
        raise CanaryError("SEMANTIC_GATE_AUDITS_MISSING")
    rows = []
    for gate_name in parent.SEMANTIC_GATE_NAMES:
        gate = semantic.get(gate_name)
        if not isinstance(gate, Mapping):
            raise CanaryError(f"SEMANTIC_GATE_RESULT_MISSING:{gate_name}")
        findings = gate.get("findings", [])
        if not isinstance(findings, list):
            raise CanaryError(f"SEMANTIC_GATE_FINDINGS_INVALID:{gate_name}")
        field_results = gate.get("field_results", {})
        rows.append(
            {
                "gate": gate_name,
                "status": gate.get("status"),
                "finding_count": len(findings),
                "findings": findings,
                "field_result_count": (
                    len(field_results)
                    if isinstance(field_results, Mapping)
                    else 0
                ),
            }
        )
    return {
        "schema_version": (
            "av-trace.p23-102-query-authoring-v2-canary2-gates/1.0"
        ),
        "canary_id": CANARY_ID,
        "status": audits.get("status"),
        "gates": rows,
        "failed_gates": [
            row["gate"] for row in rows if row["status"] != "PASS"
        ],
        "retrieval_scoring_executed": False,
    }


def _failure_accounting(
    audits: Mapping[str, Any],
    gate_findings: Mapping[str, Any],
) -> dict[str, Any]:
    failures = audits.get("failures", [])
    if not isinstance(failures, list):
        raise CanaryError("AUDIT_FAILURE_ACCOUNTING_INVALID")
    return {
        "schema_version": (
            "av-trace.p23-102-query-authoring-v2-canary2-"
            "failure-accounting/1.0"
        ),
        "canary_id": CANARY_ID,
        "status": "PASS" if not failures else "FAIL_CLOSED",
        "top_level_failure_count": len(failures),
        "top_level_failures": list(failures),
        "gate_failure_count": len(gate_findings["failed_gates"]),
        "gate_failures": list(gate_findings["failed_gates"]),
        "constrained_json_failures": 0,
        "failure_capsule_required": bool(failures),
        "retrieval_scoring_executed": False,
    }


def _write_gate_artifacts(staging: Path, audits: Mapping[str, Any]) -> None:
    gate_findings = _gate_findings(audits)
    accounting = _failure_accounting(audits, gate_findings)
    parent.atomic_json(staging / "gate_findings.json", gate_findings)
    parent.atomic_json(staging / "failure_accounting.json", accounting)


def _write_exception_accounting(staging: Path, exc: BaseException) -> None:
    audits_path = staging / "audits.failed.json"
    if audits_path.is_file():
        audits = parent.load_json(audits_path)
        _write_gate_artifacts(staging, audits)
        return
    if not (staging / "gate_findings.json").is_file():
        parent.atomic_json(
            staging / "gate_findings.json",
            {
                "schema_version": (
                    "av-trace.p23-102-query-authoring-v2-canary2-"
                    "gates/1.0"
                ),
                "canary_id": CANARY_ID,
                "status": "NOT_REACHED",
                "gates": [],
                "failed_gates": [],
                "retrieval_scoring_executed": False,
            },
        )
    error_code = str(exc).split(":", 1)[0]
    parent.atomic_json(
        staging / "failure_accounting.json",
        {
            "schema_version": (
                "av-trace.p23-102-query-authoring-v2-canary2-"
                "failure-accounting/1.0"
            ),
            "canary_id": CANARY_ID,
            "status": "FAIL_CLOSED",
            "top_level_failure_count": 1,
            "top_level_failures": [error_code],
            "gate_failure_count": 0,
            "gate_failures": [],
            "constrained_json_failures": int(
                "JSON" in error_code or "SCHEMA_ONLY_REPAIR" in error_code
            ),
            "failure_capsule_required": True,
            "retrieval_scoring_executed": False,
        },
    )


def _run_real_authoring(
    root: Path,
    *,
    media: Path,
    staging: Path,
    subset: Mapping[str, Any],
    contract: Mapping[str, Any],
    stage_times: dict[str, float],
    stage_tracker: dict[str, str] | None = None,
) -> dict[str, int]:
    def enter_stage(stage: str) -> None:
        if stage_tracker is not None:
            stage_tracker["current"] = stage

    """Run the parent pipeline's real A/V stages on the staged subset."""

    media_path = _repo_path(root, media)
    prompt_manifest = parent.build_prompt_manifest(subset)
    parent.atomic_json(staging / "prompt_manifest.json", prompt_manifest)

    partial_clip_records: list[dict[str, Any]] = []

    def retain_clip_record(record: Mapping[str, Any]) -> None:
        partial_clip_records.append(dict(record))
        parent.atomic_json(
            staging / "target_manifest.json",
            {
                "schema_version": (
                    "av-trace.p23-102-query-authoring-v2-canary2-"
                    "target-manifest/1.0"
                ),
                "canary_id": CANARY_ID,
                "source_media": {
                    "path": str(media),
                    "sha256": contract["input_fingerprints"][
                        "media_sha256"
                    ],
                },
                "target_count": len(partial_clip_records),
                "targets": _safe_target_records(partial_clip_records),
                "decode_scope": "EXACT_CANARY_TARGET_INTERVALS_ONLY",
                "partial_progress": True,
            },
        )

    enter_stage("exact_clip_extraction")
    with parent.timed_stage(stage_times, "exact_clip_extraction"):
        clips, clip_records = parent._extract_exact_clips(
            media_path,
            subset["targets"],
            staging,
            progress_callback=retain_clip_record,
        )
    target_manifest = {
        "schema_version": (
            "av-trace.p23-102-query-authoring-v2-canary2-target-manifest/1.0"
        ),
        "canary_id": CANARY_ID,
        "source_media": {
            "path": str(media),
            "sha256": contract["input_fingerprints"]["media_sha256"],
        },
        "target_count": len(clip_records),
        "targets": _safe_target_records(clip_records),
        "decode_scope": "EXACT_CANARY_TARGET_INTERVALS_ONLY",
        "decode_implementation": "parent._extract_exact_clips",
        "full_source_scan": False,
        "non_target_media_decoded": False,
        "ephemeral_arrays_removed_before_seal": True,
    }
    parent.atomic_json(staging / "target_manifest.json", target_manifest)

    enter_stage("omni_model_load")
    with parent.timed_stage(stage_times, "omni_load"):
        processor, model, torch = parent._load_omni(root)
    parsed_by_family: dict[str, Mapping[str, Any]] = {}
    attempts: list[dict[str, Any]] = []
    visual_prompts_by_family: dict[str, list[Mapping[str, Any]]] = {}
    ambient_prompts_by_family: dict[str, list[Mapping[str, Any]]] = {}
    for row in prompt_manifest["visual_prompts"]:
        visual_prompts_by_family.setdefault(
            str(row["family_key"]), []
        ).append(row)
    for row in prompt_manifest["ambient_prompts"]:
        ambient_prompts_by_family.setdefault(
            str(row["family_key"]), []
        ).append(row)
    for rows in [
        *visual_prompts_by_family.values(),
        *ambient_prompts_by_family.values(),
    ]:
        rows.sort(key=lambda row: int(row["component_ordinal"]))
    clip_records_by_key = {
        row["clip_key"]: row for row in clip_records
    }
    authoring_model_calls = 0
    schema_only_repair_calls = 0
    enter_stage("omni_authoring")
    with parent.timed_stage(stage_times, "omni_authoring"):
        for family in subset["families"]:
            family_key = family["family_key"]
            media_assets = [
                clips[row["clip_key"]] for row in family["intervals"]
            ]
            videos, audios = zip(
                *(parent._decode_av(asset) for asset in media_assets),
                strict=True,
            )
            parsed, calls = parent.author_one_family(
                processor,
                model,
                torch,
                family=family,
                visual_prompts=visual_prompts_by_family[family_key],
                ambient_prompts=ambient_prompts_by_family[family_key],
                videos=list(videos),
                audios=list(audios),
                clip_records=[
                    clip_records_by_key[row["clip_key"]]
                    for row in family["intervals"]
                ],
                model_identity=contract["model_identities"]["authoring"],
                attempts=attempts,
                attempts_path=staging / "raw_attempts.jsonl",
                prompt_manifest=prompt_manifest,
                prompt_manifest_path=staging / "prompt_manifest.json",
            )
            parsed_by_family[family_key] = parsed
            authoring_model_calls += calls
            initial_calls = 2 * len(family["intervals"]) + 1
            schema_only_repair_calls += calls - initial_calls

    with _parent_subset_counts():
        accepted_factor_manifest = parent.build_accepted_factor_manifest(
            subset, parsed_by_family, attempts
        )
        parent.atomic_json(
            staging / "accepted_factor_manifest.json",
            accepted_factor_manifest,
        )
        queries, descriptions = parent.materialize_query_records(
            subset, parsed_by_family, accepted_factor_manifest
        )
        parent.validate_accepted_factor_provenance(
            accepted_factor_manifest,
            attempts,
            queries,
            descriptions,
        )
        tuple_collisions = parent.ambient_semantic_tuple_duplicate_audit(
            accepted_factor_manifest,
            queries,
            scope="canary2",
        )
        parent.atomic_json(
            staging / "ambient_semantic_tuple_collisions.json",
            tuple_collisions,
        )
        if tuple_collisions["status"] != "PASS":
            raise CanaryError(
                "AMBIENT_SEMANTIC_TUPLE_DUPLICATE_FAIL_CLOSED"
            )

    partial_asr_rows: list[dict[str, Any]] = []

    def retain_asr_row(row: Mapping[str, Any]) -> None:
        partial_asr_rows.append(dict(row))
        parent.atomic_json(
            staging / "asr_audit_inventory.json",
            {
                "schema_version": (
                    "av-trace.p23-102-query-authoring-v2-canary2-asr/1.0"
                ),
                "model_identity": contract["model_identities"][
                    "asr_leakage_audit"
                ],
                "authoring_model_visible": False,
                "exact_canary_target_clips_only": True,
                "partial_progress": True,
                "rows": partial_asr_rows,
            },
        )

    enter_stage("whisper_leakage_audit")
    with parent.timed_stage(stage_times, "whisper_leakage_audit"):
        transcripts, asr_rows = parent._run_asr(
            root, clips, progress_callback=retain_asr_row
        )
    parent.atomic_json(
        staging / "asr_audit_inventory.json",
        asr_inventory := {
            "schema_version": (
                "av-trace.p23-102-query-authoring-v2-canary2-asr/1.0"
            ),
            "model_identity": contract["model_identities"][
                "asr_leakage_audit"
            ],
            "authoring_model_visible": False,
            "exact_canary_target_clips_only": True,
            "rows": asr_rows,
        },
    )

    enter_stage("query_collision_audits")
    with parent.timed_stage(stage_times, "query_collision_audits"):
        visual_embed = parent._text_embedder(root, parent.SIGLIP_SNAPSHOT)
        ambient_embed = parent._text_embedder(root, parent.CLAP_SNAPSHOT)
        with _parent_subset_counts():
            audits = parent.audit_authored_content(
                subset,
                queries,
                descriptions,
                transcripts_by_clip=transcripts,
                embed_visual=visual_embed,
                embed_ambient=ambient_embed,
            )
    audits["input_digest"] = parent._audit_input_digest(
        subset,
        queries,
        descriptions,
        asr_inventory,
    )
    audits["input_hashes"] = {
        "prompt_manifest": parent.semantic_hash(prompt_manifest),
        "accepted_factor_manifest": (
            accepted_factor_manifest["manifest_payload_sha256"]
        ),
        "asr_inventory": parent.semantic_hash(asr_inventory),
        "queries": parent.semantic_hash(queries),
        "descriptions": parent.semantic_hash(descriptions),
    }
    audits["canary_scope"] = {
        "families": EXPECTED_FAMILIES,
        "queries": EXPECTED_QUERY_COUNT,
        "retrieval_vectors_read": False,
        "retrieval_scoring_executed": False,
    }
    _write_gate_artifacts(staging, audits)
    if audits["status"] != "PASS":
        parent.atomic_json(staging / "audits.failed.json", audits)
        raise CanaryError(
            "CANARY_AUTHORING_AUDIT_FAIL_CLOSED:"
            + ",".join(audits["failures"])
        )
    parent.atomic_json(staging / "audits.json", audits)
    parent.atomic_json(
        staging / "authored_queries.json",
        {
            "schema_version": AUTHORED_QUERIES_SCHEMA_VERSION,
            "canary_id": CANARY_ID,
            "status": "MACHINE_AUTHORED_CANARY_AUDITED_NOT_SCORED",
            "query_count": len(queries),
            "description_count": len(descriptions),
            "accepted_factor_manifest_sha256": (
                accepted_factor_manifest["manifest_payload_sha256"]
            ),
            "prompt_manifest_sha256": parent.semantic_hash(prompt_manifest),
            "audits_input_digest": audits["input_digest"],
            "audits_payload_sha256": parent.semantic_hash(audits),
            "queries": queries,
            "descriptions": descriptions,
            "retrieval_results": [],
            "scoring_results": [],
            "scientific_claims": [],
        },
    )
    shutil.rmtree(staging / "clips", ignore_errors=True)
    return {
        "authoring_model_calls": authoring_model_calls,
        "initial_authoring_calls": EXPECTED_INITIAL_FACTORS,
        "visual_initial_authoring_calls": EXPECTED_VISUAL_FACTORS,
        "ambient_initial_authoring_calls": EXPECTED_AMBIENT_FACTORS,
        "composition_initial_authoring_calls": (
            EXPECTED_COMPOSITION_FACTORS
        ),
        "schema_only_repair_calls": schema_only_repair_calls,
        "asr_model_calls": len(asr_rows),
        "target_clip_decodes": len(clip_records),
    }


def _seal_output(output_dir: Path) -> dict[str, Any]:
    parent._validate_static_ambient_contract()
    files = {}
    for name in OUTPUT_FILES:
        path = output_dir / name
        if not path.is_file():
            raise CanaryError(f"CANARY_OUTPUT_FILE_MISSING:{name}")
        files[name] = {
            "sha256": "sha256:" + parent.file_sha256(path),
            "bytes": path.stat().st_size,
        }
    seal = {
        "schema_version": (
            SEAL_SCHEMA_VERSION
        ),
        "canary_id": CANARY_ID,
        "sealed_at": CURRENT_DATE,
        "status": "SEALED_CANARY_AUTHORING_COMPLETE_SCORING_NOT_RUN",
        "files": files,
        "ambient_constraint": parent.ambient_constraint_contract(),
        "retrieval_scoring_executed": False,
        "retrieval_rankings_read": False,
        "retrieval_outcomes_read": False,
        "non_target_vectors_read": False,
        "scientific_claims_made": False,
    }
    parent.atomic_json(output_dir / "seal.json", seal, mode=0o400)
    for name in OUTPUT_FILES:
        os.chmod(output_dir / name, 0o400)
    return seal


def execute(
    root: Path,
    *,
    bundle: Path = DEFAULT_BUNDLE,
    media: Path = DEFAULT_MEDIA,
    output: Path = DEFAULT_OUTPUT,
    authorization: Path,
    stage_runner: Callable[..., Mapping[str, int]] | None = None,
) -> dict[str, Any]:
    """Execute one authorized canary run and atomically install its seal."""

    parent._offline_environment()
    if _relative_repo_path(root, output) != DEFAULT_OUTPUT.as_posix():
        raise CanaryError("CANARY_OUTPUT_PATH_NOT_FIXED")
    output_path = _repo_path(root, output)

    structural = parent.load_structural_bundle(root, bundle)
    selection, selection_inputs = _selection_context(root, structural)
    subset = build_subset_structural(structural, selection)
    fingerprints = _input_fingerprints(
        root,
        media=media,
        structural=structural,
        selection=selection,
        selection_inputs=selection_inputs,
    )
    authorization_value = validate_authorization(
        root,
        authorization,
        fingerprints=fingerprints,
        output=output,
    )
    governance_paths = authorization_governance_paths(
        output_path, str(authorization_value["authorization_id"])
    )
    if any(path.exists() for path in governance_paths.values()):
        raise CanaryError(
            "CANARY_ONE_SHOT_AUTHORIZATION_ALREADY_CONSUMED"
        )
    output_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{output_path.name}.staging-",
            dir=output_path.parent,
        )
    )
    os.chmod(staging, 0o700)
    try:
        attempt_marker = _create_attempt_marker(
            root=root,
            marker_path=governance_paths["attempt_marker"],
            authorization_path=authorization,
            authorization_value=authorization_value,
            fingerprints=fingerprints,
        )
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    wall_started = time.monotonic()
    rss_started = _peak_rss_bytes()
    stage_times: dict[str, float] = {}
    stage_tracker = {"current": "canary_setup"}
    counts: dict[str, int] = {
        "authoring_model_calls": 0,
        "initial_authoring_calls": 0,
        "visual_initial_authoring_calls": 0,
        "ambient_initial_authoring_calls": 0,
        "composition_initial_authoring_calls": 0,
        "schema_only_repair_calls": 0,
        "asr_model_calls": 0,
        "target_clip_decodes": 0,
    }
    try:
        parent_result = parent.preflight(root, bundle=bundle, media=media)
        if parent_result["status"] != "READY":
            raise CanaryError(
                "CANARY_PREFLIGHT_FAIL_CLOSED:"
                + ",".join(parent_result["failures"])
            )
        parent.atomic_json(staging / "canary2_subset_bundle.json", subset)
        contract = _contract_value(
            root=root,
            authorization_path=authorization,
            authorization_value=authorization_value,
            fingerprints=fingerprints,
            selection=selection,
            selection_inputs=selection_inputs,
            subset=subset,
            attempt_marker_path_value=governance_paths["attempt_marker"],
            attempt_marker=attempt_marker,
        )
        parent.atomic_json(staging / "canary2_contract.json", contract)
        runner = stage_runner or _run_real_authoring
        runner_kwargs = {
            "media": media,
            "staging": staging,
            "subset": subset,
            "contract": contract,
            "stage_times": stage_times,
        }
        if runner is _run_real_authoring:
            runner_kwargs["stage_tracker"] = stage_tracker
        counts = parent.retained_runtime_counts(
            staging,
            dict(runner(root, **runner_kwargs)),
        )
        stage_tracker["current"] = "canary_seal"
        audits_path = staging / "audits.json"
        if not audits_path.is_file():
            raise CanaryError("CANARY_AUDITS_MISSING_AFTER_STAGE_RUNNER")
        audits = parent.load_json(audits_path)
        _write_gate_artifacts(staging, audits)
        runtime = {
            "schema_version": RUNTIME_SCHEMA_VERSION,
            "canary_id": CANARY_ID,
            "wall_seconds": round(time.monotonic() - wall_started, 6),
            "peak_rss_bytes": _peak_rss_bytes(),
            "peak_rss_at_start_bytes": rss_started,
            "stage_wall_seconds": stage_times,
            "threads": parent.THREADS,
            "network_requests": 0,
            "ambient_constraint": parent.ambient_constraint_contract(),
            **counts,
            "full_main_pipeline_executed": False,
            "canary_subset_only": True,
            "retrieval_scoring_executed": False,
        }
        parent.atomic_json(staging / "resource_runtime.json", runtime)
        seal = _seal_output(staging)
        os.replace(staging, output_path)
        return seal
    except Exception as exc:
        _write_exception_accounting(staging, exc)
        parent.install_failure_capsule(
            staging,
            output_path=output_path,
            authorization_id=str(authorization_value["authorization_id"]),
            exc=exc,
            wall_started=wall_started,
            stage_times=stage_times,
            failed_stage=stage_tracker["current"],
            runtime_counts=parent.retained_runtime_counts(staging, counts),
            capsule_kind="canary2",
            pipeline_id=CANARY_ID,
        )
        raise


def _validate_output_integrity(
    root: Path = ROOT, output: Path = DEFAULT_OUTPUT
) -> dict[str, Any]:
    trusted_constraint_context = (
        parent.trusted_ambient_constraint_context()
    )
    if _relative_repo_path(root, output) != DEFAULT_OUTPUT.as_posix():
        raise CanaryError("CANARY_OUTPUT_PATH_NOT_FIXED")
    output_path = _repo_path(root, output)
    seal_path = output_path / "seal.json"
    if not seal_path.is_file():
        raise CanaryError("CANARY_OUTPUT_SEAL_MISSING")
    seal = parent.load_json(seal_path)
    if (
        seal.get("status")
        != "SEALED_CANARY_AUTHORING_COMPLETE_SCORING_NOT_RUN"
        or seal.get("schema_version") != SEAL_SCHEMA_VERSION
        or seal.get("ambient_constraint")
        != parent.ambient_constraint_contract()
        or seal.get("retrieval_scoring_executed") is not False
        or seal.get("scientific_claims_made") is not False
    ):
        raise CanaryError("CANARY_OUTPUT_SEAL_STATUS_INVALID")
    if set(seal.get("files", {})) != set(OUTPUT_FILES):
        raise CanaryError("CANARY_OUTPUT_SEAL_FILE_SET_INVALID")
    for name, record in seal["files"].items():
        path = output_path / name
        if (
            not path.is_file()
            or "sha256:" + parent.file_sha256(path) != record.get("sha256")
            or path.stat().st_size != record.get("bytes")
        ):
            raise CanaryError(f"CANARY_SEALED_FILE_MISMATCH:{name}")
    subset = parent.load_json(output_path / "canary2_subset_bundle.json")
    contract = parent.load_json(output_path / "canary2_contract.json")
    target_manifest = parent.load_json(output_path / "target_manifest.json")
    prompt_manifest = parent.load_json(output_path / "prompt_manifest.json")
    asr_inventory = parent.load_json(
        output_path / "asr_audit_inventory.json"
    )
    authored = parent.load_json(output_path / "authored_queries.json")
    audits = parent.load_json(output_path / "audits.json")
    gate_findings = parent.load_json(output_path / "gate_findings.json")
    accounting = parent.load_json(output_path / "failure_accounting.json")
    runtime = parent.load_json(output_path / "resource_runtime.json")
    accepted = parent.load_json(
        output_path / "accepted_factor_manifest.json"
    )
    tuple_collisions = parent.load_json(
        output_path / "ambient_semantic_tuple_collisions.json"
    )
    if (
        contract.get("schema_version") != CONTRACT_SCHEMA_VERSION
        or prompt_manifest.get("schema_version")
        != parent.PROMPT_MANIFEST_SCHEMA_VERSION
        or accepted.get("schema_version")
        != parent.ACCEPTED_FACTOR_MANIFEST_SCHEMA_VERSION
        or authored.get("schema_version")
        != AUTHORED_QUERIES_SCHEMA_VERSION
        or runtime.get("schema_version") != RUNTIME_SCHEMA_VERSION
        or runtime.get("ambient_constraint")
        != parent.ambient_constraint_contract()
    ):
        raise CanaryError("CANARY_SEALED_R20_SCHEMA_OR_CONSTRAINT_INVALID")
    fingerprints = contract.get("input_fingerprints")
    governance = contract.get("selection_governance_bindings")
    if (
        not isinstance(fingerprints, Mapping)
        or not isinstance(governance, Mapping)
        or governance
        != {
            "selection_algorithm": fingerprints.get(
                "selection_algorithm"
            ),
            "selection_version": fingerprints.get("selection_version"),
            "private_governance_ledger_sha256": fingerprints.get(
                "private_governance_ledger_sha256"
            ),
            "private_governance_commitment_sha256": fingerprints.get(
                "private_governance_commitment_sha256"
            ),
            "public_selection_commitment_sha256": fingerprints.get(
                "public_selection_commitment_sha256"
            ),
            "replacement_generation": 1,
            "maximum_replacements": 2,
            "run_attempt_limit": 1,
            "redraw_after_output_permitted": False,
            "runtime_fallback_permitted": False,
        }
    ):
        raise CanaryError("CANARY_SEALED_R22B_GOVERNANCE_BINDING_INVALID")
    factorization = contract.get("factorization")
    if not isinstance(factorization, Mapping):
        raise CanaryError("CANARY_SEALED_R20_SCHEMA_OR_CONSTRAINT_INVALID")
    try:
        parent._validate_ambient_derivation_contract(
            factorization,
            error="CANARY_SEALED_R20_SCHEMA_OR_CONSTRAINT_INVALID",
        )
    except parent.AuthoringError as exc:
        raise CanaryError(str(exc)) from exc
    attempts = [
        json.loads(line)
        for line in (output_path / "raw_attempts.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    if subset.get("counts", {}).get("families") != EXPECTED_FAMILIES:
        raise CanaryError("CANARY_SEALED_FAMILY_COUNT_MISMATCH")
    if subset.get("counts", {}).get("target_clips", 0) > MAX_UNIQUE_CLIPS:
        raise CanaryError("CANARY_SEALED_CLIP_BOUND_VIOLATED")
    if authored.get("query_count") != EXPECTED_QUERY_COUNT:
        raise CanaryError("CANARY_SEALED_QUERY_COUNT_MISMATCH")
    if audits.get("status") != "PASS":
        raise CanaryError("CANARY_SEALED_AUDIT_NOT_PASS")
    if gate_findings.get("failed_gates") != []:
        raise CanaryError("CANARY_SEALED_GATE_FINDINGS_NOT_PASS")
    if (
        accounting.get("top_level_failure_count") != 0
        or accounting.get("gate_failure_count") != 0
        or accounting.get("failure_capsule_required") is not False
    ):
        raise CanaryError("CANARY_SEALED_FAILURE_ACCOUNTING_INVALID")
    if runtime.get("retrieval_scoring_executed") is not False:
        raise CanaryError("CANARY_SEALED_SCORING_FLAG_INVALID")
    try:
        expected = parent.derive_expected_factor_specs(
            subset, prompt_manifest
        )
    except parent.AuthoringError as exc:
        raise CanaryError(
            f"CANARY_SEALED_EXPECTED_FACTOR_SCOPE_INVALID:{exc}"
        ) from exc
    if (
        len(expected) != EXPECTED_INITIAL_FACTORS
        or target_manifest.get("target_count")
        != subset.get("counts", {}).get("target_clips")
    ):
        raise CanaryError("CANARY_SEALED_INITIAL_FACTOR_COUNT_MISMATCH")
    initial_attempts = sum(
        row.get("attempt_kind") == "initial" for row in attempts
    )
    repair_attempts = sum(
        row.get("attempt_kind") == "schema_only_repair" for row in attempts
    )
    if (
        initial_attempts != EXPECTED_INITIAL_FACTORS
        or repair_attempts > EXPECTED_MAX_SCHEMA_ONLY_REPAIRS
        or any(
            row.get("attempt_kind") == "schema_only_repair"
            and row.get("factor_kind") == "ambient"
            for row in attempts
        )
        or len(attempts) != initial_attempts + repair_attempts
    ):
        raise CanaryError("CANARY_SEALED_ATTEMPT_BUDGET_INVALID")
    if (
        runtime.get("initial_authoring_calls") != initial_attempts
        or runtime.get("schema_only_repair_calls") != repair_attempts
        or runtime.get("authoring_model_calls") != len(attempts)
        or runtime.get("visual_initial_authoring_calls")
        != EXPECTED_VISUAL_FACTORS
        or runtime.get("ambient_initial_authoring_calls")
        != EXPECTED_AMBIENT_FACTORS
        or runtime.get("composition_initial_authoring_calls")
        != EXPECTED_COMPOSITION_FACTORS
    ):
        raise CanaryError("CANARY_SEALED_RUNTIME_BUDGET_MISMATCH")
    try:
        parent.validate_accepted_factor_provenance(
            accepted,
            attempts,
            authored.get("queries", []),
            authored.get("descriptions", []),
            structural=subset,
            prompt_manifest=prompt_manifest,
            trusted_constraint_context=trusted_constraint_context,
        )
    except parent.AuthoringError as exc:
        raise CanaryError(f"CANARY_SEALED_PROVENANCE_INVALID:{exc}") from exc
    try:
        expected_tuple_collisions = (
            parent.ambient_semantic_tuple_duplicate_audit(
                accepted,
                authored.get("queries", []),
                scope="canary2",
            )
        )
    except parent.AuthoringError as exc:
        raise CanaryError(
            f"CANARY_SEALED_AMBIENT_TUPLE_LEDGER_INVALID:{exc}"
        ) from exc
    if (
        tuple_collisions != expected_tuple_collisions
        or tuple_collisions.get("status") != "PASS"
    ):
        raise CanaryError(
            "CANARY_SEALED_AMBIENT_TUPLE_LEDGER_INVALID"
        )
    if (
        authored.get("accepted_factor_manifest_sha256")
        != accepted.get("manifest_payload_sha256")
    ):
        raise CanaryError("CANARY_SEALED_ACCEPTED_FACTOR_BINDING_MISMATCH")
    if authored.get("prompt_manifest_sha256") != parent.semantic_hash(
        prompt_manifest
    ):
        raise CanaryError("CANARY_SEALED_PROMPT_MANIFEST_BINDING_MISMATCH")
    expected_digest = parent._audit_input_digest(
        subset,
        authored.get("queries", []),
        authored.get("descriptions", []),
        asr_inventory,
    )
    if (
        audits.get("input_digest") != expected_digest
        or authored.get("audits_input_digest") != expected_digest
    ):
        raise CanaryError("CANARY_SEALED_AUDIT_INPUT_DIGEST_MISMATCH")
    if authored.get("audits_payload_sha256") != parent.semantic_hash(audits):
        raise CanaryError("CANARY_SEALED_AUDIT_PAYLOAD_BINDING_MISMATCH")
    transcripts = parent._transcripts_from_asr_inventory(asr_inventory)
    with _parent_subset_counts():
        replay_queries, replay_descriptions = (
            parent._queries_for_audit_replay(
                authored.get("queries", []),
                authored.get("descriptions", []),
            )
        )
        rerun = parent.audit_authored_content(
            subset,
            replay_queries,
            replay_descriptions,
            transcripts_by_clip=transcripts,
            embed_visual=parent._synthetic_embed,
            embed_ambient=parent._synthetic_embed,
        )
    if parent._model_free_audit_projection(
        rerun
    ) != parent._model_free_audit_projection(audits):
        raise CanaryError("CANARY_SEALED_MODEL_FREE_AUDIT_REPLAY_MISMATCH")
    expected_gate_findings = _gate_findings(audits)
    expected_accounting = _failure_accounting(
        audits, expected_gate_findings
    )
    if gate_findings != expected_gate_findings:
        raise CanaryError("CANARY_SEALED_GATE_FINDINGS_BINDING_MISMATCH")
    if accounting != expected_accounting:
        raise CanaryError("CANARY_SEALED_FAILURE_ACCOUNTING_BINDING_MISMATCH")
    subset_body_hash = _subset_body_hash(subset)
    if subset.get("subset_payload_sha256") != subset_body_hash:
        raise CanaryError("CANARY_SEALED_SUBSET_BODY_HASH_MISMATCH")
    if contract.get("subset_payload_sha256") != subset_body_hash:
        raise CanaryError("CANARY_SEALED_CONTRACT_SUBSET_BINDING_MISMATCH")
    return {
        "passed": True,
        "validation_level": "INTEGRITY_ONLY",
        "input_authorization_verified": False,
        "execution_attested": False,
        "externally_attested": False,
        "status": seal["status"],
        "families": EXPECTED_FAMILIES,
        "unique_clips": subset["counts"]["target_clips"],
        "query_count": authored["query_count"],
        "wall_seconds": runtime["wall_seconds"],
        "peak_rss_bytes": runtime["peak_rss_bytes"],
        "retrieval_scoring_executed": False,
        "trusted_constraint_context_build_seconds": (
            trusted_constraint_context["context_build_seconds"]
        ),
    }


def validate_output_integrity_only(
    root: Path = ROOT, output: Path = DEFAULT_OUTPUT
) -> dict[str, Any]:
    """Explicit helper for synthetic fixtures with integrity checks only."""

    return _validate_output_integrity(root, output)


def _resolve_validation_authorization(
    root: Path,
    output_path: Path,
    contract: Mapping[str, Any],
    authorization: Path | None,
) -> Path:
    recorded = contract.get("authorization_receipt_path")
    if authorization is None:
        if not isinstance(recorded, str) or not recorded:
            raise CanaryError(
                "CANARY_OUTPUT_EXTERNAL_AUTHORIZATION_PATH_MISSING"
            )
        authorization = Path(recorded)
    resolved = _repo_path(root, authorization).resolve()
    try:
        resolved.relative_to(output_path.resolve())
    except ValueError:
        pass
    else:
        raise CanaryError(
            "CANARY_OUTPUT_AUTHORIZATION_RECEIPT_INSIDE_OUTPUT"
        )
    if (
        not isinstance(recorded, str)
        or _relative_repo_path(root, resolved) != recorded
    ):
        raise CanaryError(
            "CANARY_OUTPUT_AUTHORIZATION_RECEIPT_PATH_MISMATCH"
        )
    return resolved


def _trusted_validation_context(
    root: Path,
    *,
    bundle: Path,
    media: Path,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    structural = parent.load_structural_bundle(root, bundle)
    selection, selection_inputs = _selection_context(root, structural)
    subset = build_subset_structural(structural, selection)
    fingerprints = _input_fingerprints(
        root,
        media=media,
        structural=structural,
        selection=selection,
        selection_inputs=selection_inputs,
    )
    return structural, selection, selection_inputs, {
        "subset": subset,
        "fingerprints": fingerprints,
    }


def _prompt_rows_by_factor(
    prompt_manifest: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    rows: dict[str, Mapping[str, Any]] = {}
    for factor_kind, prompt_key in (
        ("visual", "visual_prompts"),
        ("ambient", "ambient_prompts"),
    ):
        for row in prompt_manifest.get(prompt_key, []):
            key = (
                f"{row.get('family_key')}:component:"
                f"{row.get('component_ordinal')}:{factor_kind}"
            )
            if key in rows:
                raise CanaryError("CANARY_PROMPT_FACTOR_DUPLICATE")
            rows[key] = row
    for row in prompt_manifest.get("resolved_composition_prompts", []):
        key = f"{row.get('family_key')}:family_composition"
        if key in rows:
            raise CanaryError("CANARY_PROMPT_FACTOR_DUPLICATE")
        rows[key] = row
    return rows


def _trusted_clip_projection(
    records: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    fields = (
        "clip_key",
        "start_us",
        "end_us",
        "duration_us",
        "decode_backend",
        "video_sha256",
        "video_bytes",
        "video_shape",
        "audio_sha256",
        "audio_bytes",
        "audio_shape",
        "sampled_video_frames",
        "decoded_video_frames_in_interval",
        "audio_sample_rate_hz",
        "audio_samples",
        "audio_coverage_fraction",
        "decoded_audio_frames_in_interval",
    )
    return [
        {field: row.get(field) for field in fields}
        for row in records
    ]


def _recompute_trusted_target_records(
    root: Path,
    *,
    media: Path,
    expected_subset: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Decode current trusted media into a temporary, non-output workspace."""

    media_path = _repo_path(root, media)
    with tempfile.TemporaryDirectory(
        prefix="p23-102-canary2-validate-media-"
    ) as temporary:
        _, records = parent._extract_exact_clips(
            media_path,
            expected_subset["targets"],
            Path(temporary),
        )
        return [dict(row) for row in records]


def _validate_attempt_integrity_bindings(
    attempts: Sequence[Mapping[str, Any]],
    *,
    expected_subset: Mapping[str, Any],
    prompt_manifest: Mapping[str, Any],
    target_manifest: Mapping[str, Any],
    contract: Mapping[str, Any],
    trusted_constraint_context: Mapping[str, Any],
) -> None:
    try:
        specs = parent.derive_expected_factor_specs(
            expected_subset, prompt_manifest
        )
    except parent.AuthoringError as exc:
        raise CanaryError(
            f"CANARY_ATTEMPT_EXPECTED_SCOPE_INVALID:{exc}"
        ) from exc
    prompts = _prompt_rows_by_factor(prompt_manifest)
    if set(prompts) != set(specs):
        raise CanaryError("CANARY_ATTEMPT_PROMPT_FACTOR_SET_MISMATCH")
    targets = target_manifest.get("targets")
    if not isinstance(targets, list):
        raise CanaryError("CANARY_TARGET_MANIFEST_ROWS_INVALID")
    target_by_key = {
        str(row.get("clip_key")): row
        for row in targets
        if isinstance(row, Mapping)
    }
    expected_model = contract.get("model_identities", {}).get("authoring")
    if expected_model != _model_identities()["authoring"]:
        raise CanaryError("CANARY_CONTRACT_AUTHORING_MODEL_IDENTITY_MISMATCH")

    attempts_by_factor: dict[str, list[Mapping[str, Any]]] = {}
    for attempt in attempts:
        key = attempt.get("factor_key")
        if not isinstance(key, str):
            raise CanaryError("CANARY_ATTEMPT_FACTOR_KEY_INVALID")
        raw = attempt.get("raw_output")
        if not isinstance(raw, str):
            raise CanaryError("CANARY_ATTEMPT_RAW_OUTPUT_MISSING")
        raw_bytes = raw.encode("utf-8")
        if (
            attempt.get("raw_output_bytes") != len(raw_bytes)
            or attempt.get("raw_output_base64")
            != base64.b64encode(raw_bytes).decode("ascii")
            or attempt.get("raw_output_sha256")
            != "sha256:" + hashlib.sha256(raw_bytes).hexdigest()
        ):
            raise CanaryError("CANARY_ATTEMPT_RAW_OUTPUT_HASH_MISMATCH")
        try:
            parent._validate_attempt_constraint_binding(
                attempt,
                trusted_context=trusted_constraint_context,
            )
        except parent.AuthoringError as exc:
            raise CanaryError(
                f"CANARY_ATTEMPT_CONSTRAINT_BINDING_INVALID:{exc}"
            ) from exc
        rendered = attempt.get("rendered_prompt")
        if not isinstance(rendered, str):
            raise CanaryError("CANARY_ATTEMPT_RENDERED_PROMPT_MISSING")
        rendered_bytes = rendered.encode("utf-8")
        if (
            attempt.get("rendered_prompt_bytes") != len(rendered_bytes)
            or attempt.get("rendered_prompt_sha256")
            != "sha256:" + hashlib.sha256(rendered_bytes).hexdigest()
        ):
            raise CanaryError(
                "CANARY_ATTEMPT_RENDERED_PROMPT_HASH_MISMATCH"
            )
        attempts_by_factor.setdefault(key, []).append(attempt)
    if set(attempts_by_factor) != set(specs):
        raise CanaryError("CANARY_ATTEMPT_FACTOR_SET_MISMATCH")

    expected_resolved_prompts = []
    expected_contracts = []
    base_manifest = parent.build_prompt_manifest(expected_subset)
    base_contract_by_family = {
        row["family_key"]: dict(row)
        for row in base_manifest["composition_contracts"]
    }
    for family in expected_subset["families"]:
        family_key = str(family["family_key"])
        component_factors = []
        for ordinal in range(1, len(family["intervals"]) + 1):
            factors = {}
            for factor_kind, validator in (
                ("visual", parent.validate_visual_factor_output),
                ("ambient", parent.validate_ambient_factor_output),
            ):
                key = (
                    f"{family_key}:component:{ordinal}:{factor_kind}"
                )
                successful = [
                    row
                    for row in attempts_by_factor[key]
                    if row.get("parser_error") is None
                    and isinstance(row.get("parsed_output_sha256"), str)
                ]
                if len(successful) != 1:
                    raise CanaryError(
                        "CANARY_ATTEMPT_COMPONENT_SUCCESS_CARDINALITY_INVALID"
                    )
                try:
                    parsed_factor = validator(
                        parent._strict_json_output(
                            str(successful[0].get("raw_output", ""))
                        )
                    )
                    factors.update(parsed_factor)
                except parent.AuthoringError as exc:
                    raise CanaryError(
                        f"CANARY_ATTEMPT_COMPONENT_PARSE_INVALID:{exc}"
                    ) from exc
            if set(factors) != set(parent.COMPONENT_OUTPUT_SCHEMA):
                raise CanaryError(
                    "CANARY_ATTEMPT_COMPONENT_FACTOR_ASSEMBLY_INVALID"
                )
            component_factors.append(factors)
        resolved_prompt = parent._resolved_composition_prompt(
            family, component_factors
        )
        expected_resolved_prompts.append(resolved_prompt)
        contract_row = base_contract_by_family[family_key]
        contract_row["resolved"] = True
        contract_row["resolved_user_payload_sha256"] = resolved_prompt[
            "user_payload_sha256"
        ]
        contract_row["resolved_combined_prompt_sha256"] = resolved_prompt[
            "combined_prompt_sha256"
        ]
        expected_contracts.append(contract_row)
    if (
        prompt_manifest.get("resolved_composition_prompts")
        != expected_resolved_prompts
        or prompt_manifest.get("composition_contracts")
        != expected_contracts
    ):
        raise CanaryError(
            "CANARY_OUTPUT_RESOLVED_COMPOSITION_PROMPT_SOURCE_MISMATCH"
        )

    for factor_key, spec in specs.items():
        prompt = prompts[factor_key]
        rows = sorted(
            attempts_by_factor[factor_key],
            key=lambda row: int(row.get("attempt", -1)),
        )
        initial = rows[0]
        expected_conversation = parent._model_conversation(prompt)
        expected_clip_keys = (
            [spec["clip_key"]]
            if spec["factor_kind"] in {"visual", "ambient"}
            else []
        )
        expected_clip_hashes = []
        if spec["factor_kind"] in {"visual", "ambient"}:
            target = target_by_key.get(str(spec["clip_key"]))
            if target is None:
                raise CanaryError("CANARY_ATTEMPT_TARGET_CLIP_MISSING")
            expected_clip_hashes = [
                {
                    "clip_key": target.get("clip_key"),
                    "start_us": target.get("start_us"),
                    "end_us": target.get("end_us"),
                    "duration_us": target.get("duration_us"),
                    (
                        "video_sha256"
                        if spec["factor_kind"] == "visual"
                        else "audio_sha256"
                    ): target.get(
                        "video_sha256"
                        if spec["factor_kind"] == "visual"
                        else "audio_sha256"
                    ),
                }
            ]
        for key in (
            "factor_key",
            "family_key",
            "factor_kind",
            "component_ordinal",
        ):
            if initial.get(key) != spec[key]:
                raise CanaryError(
                    f"CANARY_ATTEMPT_BINDING_MISMATCH:{key}"
                )
        if (
            initial.get("attempt") != 1
            or initial.get("attempt_kind") != "initial"
            or initial.get("system_prompt_sha256")
            != prompt.get("system_prompt_sha256")
            or initial.get("user_payload_sha256")
            != prompt.get("user_payload_sha256")
            or initial.get("combined_prompt_sha256")
            != prompt.get("combined_prompt_sha256")
            or initial.get("exact_conversation") != expected_conversation
            or initial.get("exact_conversation_sha256")
            != parent.semantic_hash(expected_conversation)
            or initial.get("model_identity") != expected_model
            or initial.get("clip_keys") != expected_clip_keys
            or initial.get("clip_manifest_hashes") != expected_clip_hashes
            or initial.get("media_modality")
            != spec.get("media_modality")
        ):
            raise CanaryError(
                "CANARY_ATTEMPT_INITIAL_PROMPT_PROVENANCE_MISMATCH"
            )
        media_expected = spec["factor_kind"] in {"visual", "ambient"}
        media_contract = initial.get("media_contract")
        if (
            initial.get("media_present") is not media_expected
            or not isinstance(media_contract, Mapping)
            or media_contract.get("media_present") is not media_expected
            or initial.get("media_contract_sha256")
            != parent.semantic_hash(media_contract)
        ):
            raise CanaryError("CANARY_ATTEMPT_MEDIA_CONTRACT_MISMATCH")
        if media_expected:
            if spec["factor_kind"] == "visual":
                valid_media = (
                    media_contract.get("media_mode") == "video_only"
                    and media_contract.get("video_placeholders") == 1
                    and media_contract.get("audio_placeholders") == 0
                    and media_contract.get("video_tensors") == 1
                    and media_contract.get("audio_tensors") == 0
                    and media_contract.get("use_audio_in_video") is False
                )
            else:
                valid_media = (
                    media_contract.get("media_mode") == "audio_only"
                    and media_contract.get("video_placeholders") == 0
                    and media_contract.get("audio_placeholders") == 1
                    and media_contract.get("video_tensors") == 0
                    and media_contract.get("audio_tensors") == 1
                    and media_contract.get("use_audio_in_video") is None
                )
            if not valid_media:
                raise CanaryError(
                    "CANARY_ATTEMPT_COMPONENT_MEDIA_BINDING_INVALID"
                )
        elif any(
            media_contract.get(key)
            for key in (
                "video_placeholders",
                "audio_placeholders",
                "video_tensors",
                "audio_tensors",
            )
        ):
            raise CanaryError(
                "CANARY_ATTEMPT_COMPOSITION_MEDIA_MUST_BE_ABSENT"
            )
        if len(rows) == 2:
            if spec["factor_kind"] == "ambient":
                raise CanaryError(
                    "CANARY_ATTEMPT_AMBIENT_SCHEMA_REPAIR_FORBIDDEN"
                )
            repair = rows[1]
            repair_conversation = parent._schema_repair_conversation(
                prompt,
                prior_raw=str(initial.get("raw_output", "")),
                validation_error=str(initial.get("parser_error", "")),
            )
            repair_media = repair.get("media_contract")
            if (
                repair.get("attempt") != 2
                or repair.get("attempt_kind") != "schema_only_repair"
                or repair.get("schema_only_repair") is not True
                or repair.get("prior_raw_output_sha256")
                != initial.get("raw_output_sha256")
                or repair.get("prior_parser_error")
                != initial.get("parser_error")
                or repair.get("exact_conversation") != repair_conversation
                or repair.get("exact_conversation_sha256")
                != parent.semantic_hash(repair_conversation)
                or repair.get("system_prompt_sha256")
                != prompt.get("system_prompt_sha256")
                or repair.get("user_payload_sha256")
                != prompt.get("user_payload_sha256")
                or repair.get("combined_prompt_sha256")
                != prompt.get("combined_prompt_sha256")
                or repair.get("model_identity") != expected_model
                or repair.get("clip_keys") != expected_clip_keys
                or repair.get("clip_manifest_hashes") != expected_clip_hashes
                or repair.get("media_present") is not False
                or not isinstance(repair_media, Mapping)
                or repair_media.get("media_present") is not False
                or repair.get("media_contract_sha256")
                != parent.semantic_hash(repair_media)
            ):
                raise CanaryError(
                    "CANARY_ATTEMPT_SCHEMA_REPAIR_PROVENANCE_MISMATCH"
                )
            if any(
                repair_media.get(key)
                for key in (
                    "video_placeholders",
                    "audio_placeholders",
                    "video_tensors",
                    "audio_tensors",
                )
            ):
                raise CanaryError(
                    "CANARY_ATTEMPT_SCHEMA_REPAIR_NOT_TEXT_ONLY"
                )


def validate_output(
    root: Path = ROOT,
    output: Path = DEFAULT_OUTPUT,
    *,
    authorization: Path | None = None,
    bundle: Path = DEFAULT_BUNDLE,
    media: Path = DEFAULT_MEDIA,
) -> dict[str, Any]:
    """Validate integrity plus exact current-input authorization.

    The execution-pre authorization binds exact inputs, code, model
    inventories, media, and output path.  It does not authenticate a model
    execution transcript or prove that the sealed output was emitted by an
    actual model execution.
    """

    trusted_constraint_context = (
        parent.trusted_ambient_constraint_context()
    )
    integrity = _validate_output_integrity(root, output)
    output_path = _repo_path(root, output)
    contract = parent.load_json(output_path / "canary2_contract.json")
    receipt_path = _resolve_validation_authorization(
        root, output_path, contract, authorization
    )
    if (
        "sha256:" + parent.file_sha256(receipt_path)
        != contract.get("authorization_receipt_sha256")
    ):
        raise CanaryError(
            "CANARY_OUTPUT_AUTHORIZATION_RECEIPT_HASH_MISMATCH"
        )

    _, selection, selection_inputs, trusted = _trusted_validation_context(
        root, bundle=bundle, media=media
    )
    expected_subset = trusted["subset"]
    fingerprints = trusted["fingerprints"]
    receipt = validate_authorization(
        root,
        receipt_path,
        fingerprints=fingerprints,
        output=output,
    )
    marker_recorded = contract.get("attempt_marker_path")
    if not isinstance(marker_recorded, str) or not marker_recorded:
        raise CanaryError("CANARY_OUTPUT_ATTEMPT_MARKER_PATH_MISSING")
    marker_path = _repo_path(root, Path(marker_recorded))
    expected_marker_path = attempt_marker_path(
        output_path, str(receipt["authorization_id"])
    )
    if marker_path.resolve() != expected_marker_path.resolve():
        raise CanaryError("CANARY_OUTPUT_ATTEMPT_MARKER_PATH_MISMATCH")
    marker = _validate_attempt_marker(
        root=root,
        marker_path=marker_path,
        authorization_path=receipt_path,
        authorization_value=receipt,
        fingerprints=fingerprints,
    )
    if (
        contract.get("attempt_marker") != marker
        or contract.get("attempt_marker_sha256")
        != "sha256:" + parent.file_sha256(marker_path)
    ):
        raise CanaryError("CANARY_OUTPUT_ATTEMPT_MARKER_HASH_MISMATCH")
    if contract.get("authorization") != receipt:
        raise CanaryError(
            "CANARY_OUTPUT_AUTHORIZATION_CONTRACT_MISMATCH"
        )
    expected_contract = _contract_value(
        root=root,
        authorization_path=receipt_path,
        authorization_value=receipt,
        fingerprints=fingerprints,
        selection=selection,
        selection_inputs=selection_inputs,
        subset=expected_subset,
        attempt_marker_path_value=marker_path,
        attempt_marker=marker,
    )
    if contract != expected_contract:
        raise CanaryError("CANARY_OUTPUT_CONTRACT_TRUSTED_INPUT_MISMATCH")

    sealed_subset = parent.load_json(
        output_path / "canary2_subset_bundle.json"
    )
    if sealed_subset != expected_subset:
        raise CanaryError("CANARY_OUTPUT_SUBSET_TRUSTED_SOURCE_MISMATCH")
    prompt_manifest = parent.load_json(output_path / "prompt_manifest.json")
    base_prompt_manifest = parent.build_prompt_manifest(expected_subset)
    for key in (
        "schema_version",
        "pipeline_id",
        "prompt_count",
        "visual_prompt_count",
        "ambient_prompt_count",
        "composition_prompt_count",
        "visual_prompts",
        "ambient_prompts",
        "model_visible_firewall",
    ):
        if prompt_manifest.get(key) != base_prompt_manifest.get(key):
            raise CanaryError(
                "CANARY_OUTPUT_PROMPT_MANIFEST_TRUSTED_SOURCE_MISMATCH"
            )
    resolved = prompt_manifest.get("resolved_composition_prompts")
    if not isinstance(resolved, list) or len(resolved) != EXPECTED_FAMILIES:
        raise CanaryError(
            "CANARY_OUTPUT_RESOLVED_COMPOSITION_PROMPTS_INVALID"
        )
    for row in resolved:
        if not isinstance(row, Mapping):
            raise CanaryError(
                "CANARY_OUTPUT_RESOLVED_COMPOSITION_PROMPT_INVALID"
            )
        expected_hash = parent.semantic_hash(
            {
                "system": row.get("system_prompt"),
                "user": row.get("user_payload"),
            }
        )
        if (
            row.get("factor_kind") != "family_composition"
            or row.get("media_component_count") != 0
            or row.get("media_component_clip_keys") != []
            or row.get("system_prompt")
            != parent.COMPOSITION_SYSTEM_PROMPT
            or row.get("system_prompt_sha256")
            != parent.semantic_hash(parent.COMPOSITION_SYSTEM_PROMPT)
            or row.get("user_payload_sha256")
            != parent.semantic_hash(row.get("user_payload"))
            or row.get("combined_prompt_sha256") != expected_hash
        ):
            raise CanaryError(
                "CANARY_OUTPUT_RESOLVED_COMPOSITION_PROMPT_HASH_MISMATCH"
            )

    target_manifest = parent.load_json(output_path / "target_manifest.json")
    if (
        target_manifest.get("source_media", {}).get("sha256")
        != fingerprints["media_sha256"]
        or target_manifest.get("target_count")
        != expected_subset["counts"]["target_clips"]
    ):
        raise CanaryError("CANARY_OUTPUT_TARGET_MEDIA_BINDING_MISMATCH")
    expected_target_scope = {
        row["clip_key"]: {
            "start_us": row["start_us"],
            "end_us": row["end_us"],
            "duration_us": row["duration_us"],
        }
        for row in expected_subset["targets"]
    }
    observed_target_scope = {
        row.get("clip_key"): {
            "start_us": row.get("start_us"),
            "end_us": row.get("end_us"),
            "duration_us": row.get("duration_us"),
        }
        for row in target_manifest.get("targets", [])
        if isinstance(row, Mapping)
    }
    if observed_target_scope != expected_target_scope:
        raise CanaryError("CANARY_OUTPUT_TARGET_INTERVAL_BINDING_MISMATCH")
    trusted_target_records = _recompute_trusted_target_records(
        root,
        media=media,
        expected_subset=expected_subset,
    )
    observed_targets = target_manifest.get("targets", [])
    if _trusted_clip_projection(
        [
            row
            for row in observed_targets
            if isinstance(row, Mapping)
        ]
    ) != _trusted_clip_projection(trusted_target_records):
        raise CanaryError("CANARY_OUTPUT_DECODED_MEDIA_HASH_MISMATCH")
    attempts = [
        json.loads(line)
        for line in (output_path / "raw_attempts.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    _validate_attempt_integrity_bindings(
        attempts,
        expected_subset=expected_subset,
        prompt_manifest=prompt_manifest,
        target_manifest=target_manifest,
        contract=contract,
        trusted_constraint_context=trusted_constraint_context,
    )
    return {
        **integrity,
        "validation_level": (
            "INTEGRITY_PLUS_CURRENT_INPUT_AUTHORIZATION_"
            "NOT_EXECUTION_ATTESTED"
        ),
        "input_authorization_verified": True,
        "execution_attested": False,
        "externally_attested": False,
        "authorization_id": receipt["authorization_id"],
        "authorization_receipt_sha256": contract[
            "authorization_receipt_sha256"
        ],
        "attempt_marker_path": contract["attempt_marker_path"],
        "attempt_marker_sha256": contract["attempt_marker_sha256"],
        "trusted_constraint_context_build_seconds": (
            trusted_constraint_context["context_build_seconds"]
        ),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--plan", action="store_true")
    modes.add_argument("--preflight", action="store_true")
    modes.add_argument("--execute", action="store_true")
    modes.add_argument("--validate-output", action="store_true")
    modes.add_argument("--scan-public-surface", action="store_true")
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--media", type=Path, default=DEFAULT_MEDIA)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--authorization", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = args.repo_root.resolve()
    try:
        if args.plan:
            result = plan_status(root)
        elif args.preflight:
            result = preflight(
                root,
                bundle=args.bundle,
                media=args.media,
                output=args.output,
                authorization=args.authorization,
            )
            if result["status"] != "READY":
                print(json.dumps(result, indent=2, sort_keys=True))
                return 2
        elif args.execute:
            if args.authorization is None:
                raise CanaryError(
                    "CANARY_EXECUTION_REQUIRES_SEPARATE_AUTHORIZATION_RECEIPT"
                )
            result = execute(
                root,
                bundle=args.bundle,
                media=args.media,
                output=args.output,
                authorization=args.authorization,
            )
        elif args.validate_output:
            result = validate_output(
                root,
                args.output,
                authorization=args.authorization,
                bundle=args.bundle,
                media=args.media,
            )
        else:
            result = scan_public_surface_for_private_leakage(root)
    except PublicSurfaceScanError as exc:
        print(
            json.dumps(
                {
                    **exc.report,
                    "error": str(exc),
                    "real_canary_substituted": False,
                    "retrieval_scoring_executed": False,
                },
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    except (CanaryError, parent.AuthoringError) as exc:
        print(
            json.dumps(
                {
                    "status": "FAIL_CLOSED",
                    "error": str(exc),
                    "real_canary_substituted": False,
                    "retrieval_scoring_executed": False,
                },
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
