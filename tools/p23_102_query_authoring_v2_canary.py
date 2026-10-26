#!/usr/bin/env python3
"""Fail-closed two-family real A/V canary for P23_102 query authoring v2.

The canary is a separate wrapper over ``p23_102_query_authoring_v2.py``.  It
selects one local and one far family by structural hashes, creates a restricted
subset staging bundle, and reuses the parent pipeline's exact PyAV extraction,
Qwen2.5-Omni generation, Whisper leakage audit, and collision audits.

Planning and preflight do not decode media or load models.  Execution requires
an independently created, exact-input authorization receipt.  This module
never performs retrieval scoring and does not create an authorization receipt.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import os
import resource
import shutil
import sys
import tempfile
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CURRENT_DATE = "2026-10-15"
CANARY_ID = "AV-TRACE-P23-102-QUERY-AUTHORING-V2-CANARY"
READY = "P23_102_QUERY_AUTHORING_V2_CANARY_READY"
MEDIA_CONTRACT_REPAIR_READY = (
    "P23_102_QUERY_AUTHORING_MEDIA_CONTRACT_REPAIR_READY"
)
CONSTRAINED_JSON_READY = "P23_102_QUERY_AUTHORING_CONSTRAINED_JSON_READY"
SEMANTIC_GATES_READY = "P23_102_QUERY_AUTHORING_SEMANTIC_GATES_READY"
SELECTION_DOMAIN = (
    "AV-TRACE-P23-102-QUERY-AUTHORING-V2-CANARY-SELECTION-V1"
)

DEFAULT_PLAN = Path(
    "data/rehearsal_plan/p23_102_query_authoring_v2_canary.json"
)
DEFAULT_OUTPUT = Path(
    "data/restricted/p23_102_query_authoring_v2_canary_run_v1"
)
DEFAULT_BUNDLE = Path(
    "data/restricted/epic_p23_102_machine_provisional_families_v1"
)
DEFAULT_MEDIA = Path(
    "data/restricted/epic_p23_102_source_v1/media/P23/P23_102.MP4"
)
PARENT_TOOL = Path("tools/p23_102_query_authoring_v2.py")
CANARY_TOOL = Path("tools/p23_102_query_authoring_v2_canary.py")

EXPECTED_FAMILIES = 2
MAX_UNIQUE_CLIPS = 4
EXPECTED_QUERY_COUNT = 8
EXPECTED_COMPONENT_FACTORS = 3
EXPECTED_COMPOSITION_FACTORS = EXPECTED_FAMILIES
EXPECTED_INITIAL_FACTORS = (
    EXPECTED_COMPONENT_FACTORS + EXPECTED_COMPOSITION_FACTORS
)

OUTPUT_FILES = (
    "canary_contract.json",
    "canary_subset_bundle.json",
    "target_manifest.json",
    "prompt_manifest.json",
    "raw_attempts.jsonl",
    "asr_audit_inventory.json",
    "authored_queries.json",
    "audits.json",
    "resource_runtime.json",
)


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


def select_canary_families(
    structural: Mapping[str, Any],
) -> dict[str, Any]:
    """Select exactly one local and one far family by structural hash rank."""

    groups = {
        "local": [
            row
            for row in structural["families"]
            if row["shape"] == "one_component"
        ],
        "far": [
            row
            for row in structural["families"]
            if row["shape"] == "two_component_ordered"
        ],
    }
    selected: dict[str, Mapping[str, Any]] = {}
    selection_rows: list[dict[str, Any]] = []
    for family_class, candidates in groups.items():
        if not candidates:
            raise CanaryError(f"SELECTION_CLASS_EMPTY:{family_class}")
        ranked = []
        for family in candidates:
            family_sha256 = _family_hash(family)
            rank_sha256 = parent.semantic_hash(
                {
                    "domain": SELECTION_DOMAIN,
                    "bundle_file_hashes": structural["file_hashes"],
                    "family_class": family_class,
                    "family_structural_sha256": family_sha256,
                }
            )
            ranked.append((rank_sha256, family_sha256, family))
        rank_sha256, family_sha256, family = min(
            ranked, key=lambda row: (row[0], row[1])
        )
        selected[family_class] = family
        selection_rows.append(
            {
                "family_class": family_class,
                "family_key": family["family_key"],
                "shape": family["shape"],
                "family_structural_sha256": family_sha256,
                "selection_rank_sha256": rank_sha256,
            }
        )

    selected_families = [selected["local"], selected["far"]]
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
        "algorithm": "minimum_sha256_per_structural_family_class",
        "domain": SELECTION_DOMAIN,
        "score_fields_read": False,
        "semantic_ranking_used": False,
        "families": selection_rows,
        "selected_family_hashes": {
            row["family_class"]: row["family_structural_sha256"]
            for row in selection_rows
        },
        "selected_family_keys": {
            row["family_class"]: row["family_key"]
            for row in selection_rows
        },
        "unique_clip_keys": clip_keys,
        "unique_clip_count": len(clip_keys),
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
        selection["selected_family_keys"]["local"]: 0,
        selection["selected_family_keys"]["far"]: 1,
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
            "av-trace.p23-102-query-authoring-v2-canary-subset/1.0"
        ),
        "canary_id": CANARY_ID,
        "source_bundle_file_hashes": structural["file_hashes"],
        "selection": dict(selection),
        "families": families,
        "targets": targets,
        "counts": {
            "families": len(families),
            "local_families": 1,
            "far_families": 1,
            "target_clips": len(targets),
            "queries": query_count,
        },
        "retrieval_scores_read": False,
        "semantic_selection_used": False,
    }
    subset["subset_payload_sha256"] = parent.semantic_hash(subset)
    return subset


def _canary_config(
    *,
    structural: Mapping[str, Any],
    selection: Mapping[str, Any],
    main_pipeline_sha256: str,
    canary_pipeline_sha256: str,
) -> dict[str, Any]:
    return {
        "schema_version": (
            "av-trace.p23-102-query-authoring-v2-canary-config/1.0"
        ),
        "canary_id": CANARY_ID,
        "main_pipeline_id": parent.PIPELINE_ID,
        "main_pipeline_sha256": main_pipeline_sha256,
        "canary_pipeline_sha256": canary_pipeline_sha256,
        "source_bundle_file_hashes": structural["file_hashes"],
        "selection_algorithm": selection["algorithm"],
        "selection_domain": selection["domain"],
        "selected_family_hashes": selection["selected_family_hashes"],
        "family_classes": ["local", "far"],
        "maximum_unique_clips": MAX_UNIQUE_CLIPS,
        "expected_query_count": EXPECTED_QUERY_COUNT,
        "component_initial_authoring_model_calls": (
            EXPECTED_COMPONENT_FACTORS
        ),
        "composition_initial_authoring_model_calls": (
            EXPECTED_COMPOSITION_FACTORS
        ),
        "initial_authoring_model_calls": EXPECTED_INITIAL_FACTORS,
        "maximum_schema_only_repair_calls": EXPECTED_INITIAL_FACTORS,
        "maximum_authoring_model_calls": 2 * EXPECTED_INITIAL_FACTORS,
        "factorized_authoring": True,
        "ordinals_assigned_mechanically": True,
        "composition_media_present": False,
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
    return {
        "canary_config_sha256": parent.semantic_hash(config),
        "main_pipeline_sha256": main_pipeline_sha256,
        "canary_pipeline_sha256": _canary_tool_hash(root),
        "selected_family_hashes": selection["selected_family_hashes"],
        "bundle_file_hashes": structural["file_hashes"],
        "model_hashes": _model_hashes(root),
        "media_sha256": "sha256:" + parent.file_sha256(media_path),
    }


def validate_plan(
    root: Path = ROOT, plan: Path = DEFAULT_PLAN
) -> dict[str, Any]:
    path = _repo_path(root, plan)
    if not path.is_file():
        raise CanaryError("CANARY_PLAN_MISSING")
    value = parent.load_json(path)
    if value.get("canary_id") != CANARY_ID:
        raise CanaryError("CANARY_PLAN_ID_MISMATCH")
    expected = parent.semantic_hash(
        {key: item for key, item in value.items() if key != "plan_payload_sha256"}
    )
    if value.get("plan_payload_sha256") != expected:
        raise CanaryError("CANARY_PLAN_HASH_MISMATCH")
    structural = parent.load_structural_bundle(root, DEFAULT_BUNDLE)
    selection = select_canary_families(structural)
    if value.get("selected_family_hashes") != selection["selected_family_hashes"]:
        raise CanaryError("CANARY_PLAN_SELECTION_DRIFT")
    result = dict(value)
    current_main = _parent_tool_hash(root)
    current_canary = _canary_tool_hash(root)
    result["current_main_pipeline_sha256"] = current_main
    result["current_canary_pipeline_sha256"] = current_canary
    result["historical_plan_pipeline_hash_current"] = (
        value.get("main_pipeline_sha256") == current_main
    )
    result["old_authorization_receipts_valid"] = False
    return result


def plan_status(root: Path) -> dict[str, Any]:
    value = validate_plan(root)
    return {
        "status": READY,
        "repair_status": SEMANTIC_GATES_READY,
        "constrained_json_status": CONSTRAINED_JSON_READY,
        "plan_payload_sha256": value["plan_payload_sha256"],
        "selected_family_hashes": value["selected_family_hashes"],
        "selected_family_keys": value["selected_family_keys"],
        "unique_clip_count": value["unique_clip_count"],
        "current_main_pipeline_sha256": value[
            "current_main_pipeline_sha256"
        ],
        "current_canary_pipeline_sha256": value[
            "current_canary_pipeline_sha256"
        ],
        "old_authorization_receipts_valid": False,
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
) -> dict[str, Any]:
    failures = []
    try:
        structural = parent.load_structural_bundle(root, bundle)
        selection = select_canary_families(structural)
        subset = build_subset_structural(structural, selection)
    except (parent.AuthoringError, CanaryError) as exc:
        return {
            "schema_version": (
                "av-trace.p23-102-query-authoring-v2-canary-preflight/1.0"
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
    fingerprints = None
    if not failures:
        try:
            fingerprints = _input_fingerprints(
                root,
                media=media,
                structural=structural,
                selection=selection,
            )
        except CanaryError as exc:
            failures.append(str(exc))
    output_relative = _relative_repo_path(root, output)
    if output_relative != DEFAULT_OUTPUT.as_posix():
        failures.append("CANARY_OUTPUT_PATH_NOT_FIXED")
    if _repo_path(root, output).exists():
        failures.append("CANARY_OUTPUT_ALREADY_EXISTS")
    return {
        "schema_version": (
            "av-trace.p23-102-query-authoring-v2-canary-preflight/1.0"
        ),
        "canary_id": CANARY_ID,
        "date": CURRENT_DATE,
        "status": "READY" if not failures else "FAIL_CLOSED",
        "failures": failures,
        "selection": selection,
        "subset_counts": subset["counts"],
        "input_fingerprints": fingerprints,
        "source_media": parent_result["source_media"],
        "models": parent_result["models"],
        "decode_backend": parent_result["decode_backend"],
        "main_pipeline_reused": True,
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
        "main_pipeline_sha256",
        "canary_pipeline_sha256",
        "bundle_file_hashes",
        "model_hashes",
        "media_sha256",
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
        value["schema_version"]
        != "av-trace.p23-102-query-authoring-v2-canary-authorization/2.0"
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
        or value["main_pipeline_sha256"]
        != fingerprints["main_pipeline_sha256"]
        or value["canary_pipeline_sha256"]
        != fingerprints["canary_pipeline_sha256"]
        or value["bundle_file_hashes"] != fingerprints["bundle_file_hashes"]
        or value["model_hashes"] != fingerprints["model_hashes"]
        or value["media_sha256"] != fingerprints["media_sha256"]
        or value["output_path"] != _relative_repo_path(root, output)
    ):
        raise CanaryError("CANARY_EXECUTION_AUTHORIZATION_SCOPE_MISMATCH")
    return dict(value)


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
                "stop_boundary": "first_complete_top_level_json_object",
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


def _run_real_authoring(
    root: Path,
    *,
    media: Path,
    staging: Path,
    subset: Mapping[str, Any],
    contract: Mapping[str, Any],
    stage_times: dict[str, float],
) -> dict[str, int]:
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
                    "av-trace.p23-102-query-authoring-v2-canary-"
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

    with parent.timed_stage(stage_times, "exact_clip_extraction"):
        clips, clip_records = parent._extract_exact_clips(
            media_path,
            subset["targets"],
            staging,
            progress_callback=retain_clip_record,
        )
    target_manifest = {
        "schema_version": (
            "av-trace.p23-102-query-authoring-v2-canary-target-manifest/1.0"
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

    with parent.timed_stage(stage_times, "omni_load"):
        processor, model, torch = parent._load_omni(root)
    parsed_by_family: dict[str, Mapping[str, Any]] = {}
    attempts: list[dict[str, Any]] = []
    component_prompts_by_family: dict[str, list[Mapping[str, Any]]] = {}
    for row in prompt_manifest["component_prompts"]:
        component_prompts_by_family.setdefault(
            str(row["family_key"]), []
        ).append(row)
    for rows in component_prompts_by_family.values():
        rows.sort(key=lambda row: int(row["component_ordinal"]))
    clip_records_by_key = {
        row["clip_key"]: row for row in clip_records
    }
    authoring_model_calls = 0
    schema_only_repair_calls = 0
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
                component_prompts=component_prompts_by_family[family_key],
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
            initial_calls = len(family["intervals"]) + 1
            schema_only_repair_calls += calls - initial_calls

    with _parent_subset_counts():
        queries, descriptions = parent.materialize_query_records(
            subset, parsed_by_family
        )

    partial_asr_rows: list[dict[str, Any]] = []

    def retain_asr_row(row: Mapping[str, Any]) -> None:
        partial_asr_rows.append(dict(row))
        parent.atomic_json(
            staging / "asr_audit_inventory.json",
            {
                "schema_version": (
                    "av-trace.p23-102-query-authoring-v2-canary-asr/1.0"
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

    with parent.timed_stage(stage_times, "whisper_leakage_audit"):
        transcripts, asr_rows = parent._run_asr(
            root, clips, progress_callback=retain_asr_row
        )
    parent.atomic_json(
        staging / "asr_audit_inventory.json",
        {
            "schema_version": (
                "av-trace.p23-102-query-authoring-v2-canary-asr/1.0"
            ),
            "model_identity": contract["model_identities"][
                "asr_leakage_audit"
            ],
            "authoring_model_visible": False,
            "exact_canary_target_clips_only": True,
            "rows": asr_rows,
        },
    )

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
    audits["canary_scope"] = {
        "families": EXPECTED_FAMILIES,
        "queries": EXPECTED_QUERY_COUNT,
        "retrieval_vectors_read": False,
        "retrieval_scoring_executed": False,
    }
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
            "schema_version": (
                "av-trace.p23-102-query-authoring-v2-canary-queries/1.0"
            ),
            "canary_id": CANARY_ID,
            "status": "MACHINE_AUTHORED_CANARY_AUDITED_NOT_SCORED",
            "query_count": len(queries),
            "description_count": len(descriptions),
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
        "component_initial_authoring_calls": (
            EXPECTED_COMPONENT_FACTORS
        ),
        "composition_initial_authoring_calls": (
            EXPECTED_COMPOSITION_FACTORS
        ),
        "schema_only_repair_calls": schema_only_repair_calls,
        "asr_model_calls": len(asr_rows),
        "target_clip_decodes": len(clip_records),
    }


def _seal_output(output_dir: Path) -> dict[str, Any]:
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
            "av-trace.p23-102-query-authoring-v2-canary-seal/1.0"
        ),
        "canary_id": CANARY_ID,
        "sealed_at": CURRENT_DATE,
        "status": "SEALED_CANARY_AUTHORING_COMPLETE_SCORING_NOT_RUN",
        "files": files,
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
    if output_path.exists():
        raise CanaryError("CANARY_OUTPUT_ALREADY_EXISTS")

    structural = parent.load_structural_bundle(root, bundle)
    selection = select_canary_families(structural)
    subset = build_subset_structural(structural, selection)
    parent_result = parent.preflight(root, bundle=bundle, media=media)
    if parent_result["status"] != "READY":
        raise CanaryError(
            "CANARY_PREFLIGHT_FAIL_CLOSED:"
            + ",".join(parent_result["failures"])
        )
    fingerprints = _input_fingerprints(
        root,
        media=media,
        structural=structural,
        selection=selection,
    )
    authorization_value = validate_authorization(
        root,
        authorization,
        fingerprints=fingerprints,
        output=output,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{output_path.name}.staging-",
            dir=output_path.parent,
        )
    )
    os.chmod(staging, 0o700)
    wall_started = time.monotonic()
    rss_started = _peak_rss_bytes()
    stage_times: dict[str, float] = {}
    counts: dict[str, int] = {
        "authoring_model_calls": 0,
        "initial_authoring_calls": 0,
        "component_initial_authoring_calls": 0,
        "composition_initial_authoring_calls": 0,
        "schema_only_repair_calls": 0,
        "asr_model_calls": 0,
        "target_clip_decodes": 0,
    }
    try:
        parent.atomic_json(staging / "canary_subset_bundle.json", subset)
        contract = {
            "schema_version": (
                "av-trace.p23-102-query-authoring-v2-canary-contract/2.0"
            ),
            "canary_id": CANARY_ID,
            "date": CURRENT_DATE,
            "authorization": authorization_value,
            "authorization_receipt_sha256": (
                "sha256:"
                + parent.file_sha256(_repo_path(root, authorization))
            ),
            "input_fingerprints": fingerprints,
            "selection": selection,
            "subset_payload_sha256": subset["subset_payload_sha256"],
            "model_identities": _model_identities(),
            "factorization": {
                "component_initial_calls": EXPECTED_COMPONENT_FACTORS,
                "composition_initial_calls": EXPECTED_COMPOSITION_FACTORS,
                "total_initial_factor_calls": EXPECTED_INITIAL_FACTORS,
                "ordinals_assigned_mechanically": True,
                "composition_media_present": False,
            },
            "parent_pipeline_reused": True,
            "retrieval_scoring_permitted": False,
            "retrieval_scoring_executed": False,
            "scientific_claims_permitted": False,
        }
        parent.atomic_json(staging / "canary_contract.json", contract)
        runner = stage_runner or _run_real_authoring
        counts = parent.retained_runtime_counts(
            staging,
            dict(
                runner(
                    root,
                    media=media,
                    staging=staging,
                    subset=subset,
                    contract=contract,
                    stage_times=stage_times,
                )
            ),
        )
        runtime = {
            "schema_version": (
                "av-trace.p23-102-query-authoring-v2-canary-runtime/1.0"
            ),
            "canary_id": CANARY_ID,
            "wall_seconds": round(time.monotonic() - wall_started, 6),
            "peak_rss_bytes": _peak_rss_bytes(),
            "peak_rss_at_start_bytes": rss_started,
            "stage_wall_seconds": stage_times,
            "threads": parent.THREADS,
            "network_requests": 0,
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
        parent.install_failure_capsule(
            staging,
            output_path=output_path,
            authorization_id=str(authorization_value["authorization_id"]),
            exc=exc,
            wall_started=wall_started,
            stage_times=stage_times,
            failed_stage=(
                next(
                    (
                        stage
                        for stage in (
                            "query_collision_audits",
                            "whisper_leakage_audit",
                            "omni_authoring",
                            "omni_load",
                            "exact_clip_extraction",
                        )
                        if not any(
                            key.startswith(stage)
                            for key in stage_times
                        )
                    ),
                    "canary_seal",
                )
            ),
            runtime_counts=parent.retained_runtime_counts(staging, counts),
            capsule_kind="canary",
            pipeline_id=CANARY_ID,
        )
        raise


def validate_output(
    root: Path = ROOT, output: Path = DEFAULT_OUTPUT
) -> dict[str, Any]:
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
    subset = parent.load_json(output_path / "canary_subset_bundle.json")
    authored = parent.load_json(output_path / "authored_queries.json")
    audits = parent.load_json(output_path / "audits.json")
    runtime = parent.load_json(output_path / "resource_runtime.json")
    if subset.get("counts", {}).get("families") != EXPECTED_FAMILIES:
        raise CanaryError("CANARY_SEALED_FAMILY_COUNT_MISMATCH")
    if subset.get("counts", {}).get("target_clips", 0) > MAX_UNIQUE_CLIPS:
        raise CanaryError("CANARY_SEALED_CLIP_BOUND_VIOLATED")
    if authored.get("query_count") != EXPECTED_QUERY_COUNT:
        raise CanaryError("CANARY_SEALED_QUERY_COUNT_MISMATCH")
    if audits.get("status") != "PASS":
        raise CanaryError("CANARY_SEALED_AUDIT_NOT_PASS")
    if runtime.get("retrieval_scoring_executed") is not False:
        raise CanaryError("CANARY_SEALED_SCORING_FLAG_INVALID")
    return {
        "passed": True,
        "status": seal["status"],
        "families": EXPECTED_FAMILIES,
        "unique_clips": subset["counts"]["target_clips"],
        "query_count": authored["query_count"],
        "wall_seconds": runtime["wall_seconds"],
        "peak_rss_bytes": runtime["peak_rss_bytes"],
        "retrieval_scoring_executed": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--plan", action="store_true")
    modes.add_argument("--preflight", action="store_true")
    modes.add_argument("--execute", action="store_true")
    modes.add_argument("--validate-output", action="store_true")
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
        else:
            result = validate_output(root, args.output)
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
