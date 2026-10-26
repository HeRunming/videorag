#!/usr/bin/env python3
"""Deterministic development-only family mining for EPIC P23_102.

The default plan mode does not require or open the future full-timeline index.
Mining is deliberately blind to EPIC semantic annotation labels: it uses only
the source-derived SigLIP2 vectors, quality-gated Whisper/BM25 records, CLAP
vectors, exact temporal structure, and machine-computed continuity/recurrence
signals already present in the canonical P23_102 index.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np

PIPELINE_READY = "EPIC_P23_102_FAMILY_MINING_PIPELINE_READY"
MINE_COMPLETE = "EPIC_P23_102_FAMILY_MINING_MACHINE_PROVISIONAL_COMPLETE"
REPAIR_READY = "EPIC_P23_102_FAMILY_MINING_REPAIR_READY"
REPAIR = "EPIC_P23_102_FAMILY_MINING_REPAIR"
SCHEMA_VERSION = "av-trace.epic-p23-102-family-mining/1.0"
PLAN_SCHEMA_VERSION = "av-trace.epic-p23-102-family-mining-plan/1.0"
PLAN_RELATIVE_PATH = Path(
    "data/rehearsal_plan/epic_p23_102_family_mining_v1.json"
)
INDEX_RELATIVE_ROOT = Path(
    "data/restricted/epic_p23_102_full_timeline_index_v1"
)
DEFAULT_OUTPUT = Path(
    "data/restricted/epic_p23_102_family_mining_v1_dev/"
    "candidate_registry.json"
)
REQUIRED_INDEX_FILES = (
    "segment_manifest.json",
    "observation_manifest.json",
    "full_timeline_index.json",
    "resource_manifest.json",
    "checkpoint_manifest.json",
    "build_manifest.json",
)
PROVISIONAL_STATUSES = frozenset({"KEEP", "REPAIR", "REJECT"})
PROFILE_LABELS = frozenset({"V+A", "V+S", "V+S+A"})
STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "but",
        "by",
        "for",
        "from",
        "he",
        "her",
        "here",
        "i",
        "if",
        "in",
        "is",
        "it",
        "its",
        "me",
        "my",
        "of",
        "on",
        "or",
        "our",
        "she",
        "so",
        "that",
        "the",
        "their",
        "then",
        "there",
        "they",
        "this",
        "to",
        "up",
        "was",
        "we",
        "were",
        "with",
        "you",
        "your",
    }
)


class MiningError(RuntimeError):
    """Fail-closed mining error."""


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


def _seal(value: dict[str, Any], field: str) -> dict[str, Any]:
    value[field] = object_hash(value)
    return value


def _safe_path(root: Path, value: str | Path, *, label: str) -> Path:
    raw = Path(value)
    if raw.is_absolute():
        path = raw
    else:
        pure = PurePosixPath(str(raw))
        if ".." in pure.parts or ".staging" in pure.parts:
            raise MiningError(f"{label}_UNSAFE:{value}")
        path = root.joinpath(*pure.parts)
    try:
        path.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        raise MiningError(f"{label}_OUTSIDE_REPOSITORY:{value}") from exc
    if path.is_symlink() or ".staging" in path.parts:
        raise MiningError(f"{label}_UNSAFE:{value}")
    return path


def _relative(root: Path, path: Path) -> str:
    return path.resolve(strict=False).relative_to(root).as_posix()


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    descriptor = os.open(
        temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(canonical_bytes(value))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _round(value: float) -> float:
    return round(float(value), 8)


def _seconds(value_us: int) -> float:
    return round(value_us / 1_000_000.0, 6)


def _center(document: Mapping[str, Any]) -> float:
    return (int(document["start_us"]) + int(document["end_us"])) / 2.0


def _overlap_us(first: Mapping[str, Any], second: Mapping[str, Any]) -> int:
    return max(
        0,
        min(int(first["end_us"]), int(second["end_us"]))
        - max(int(first["start_us"]), int(second["start_us"])),
    )


def _vector(document: Mapping[str, Any]) -> np.ndarray:
    dimension = int(document["dimension"])
    try:
        value = np.frombuffer(
            bytes.fromhex(str(document["vector_f16_hex"])), dtype="<f2"
        ).astype(np.float32)
    except ValueError as exc:
        raise MiningError("INVALID_VECTOR_ENCODING") from exc
    if len(value) != dimension or not np.isfinite(value).all():
        raise MiningError("INVALID_VECTOR")
    norm = float(np.linalg.norm(value))
    if norm <= 1e-12:
        raise MiningError("ZERO_VECTOR")
    return value / norm


def _cosine(first: np.ndarray, second: np.ndarray) -> float:
    return float(np.clip(np.dot(first, second), -1.0, 1.0))


def build_plan() -> dict[str, Any]:
    """Return the frozen implementation plan without consulting the index."""
    plan: dict[str, Any] = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "plan_id": "AV-TRACE-EPIC-P23-102-FAMILY-MINING-V1",
        "created_date": "2026-10-14",
        "implementation_decision": PIPELINE_READY,
        "repair_completion_token": REPAIR_READY,
        "plan_kind": "DETERMINISTIC_DEVELOPMENT_ONLY_SOURCE_CALIBRATED",
        "canonical_input": {
            "index_root": INDEX_RELATIVE_ROOT.as_posix(),
            "required_source_id": "P23_102",
            "required_source_group_id": "P23",
            "required_mode": "full",
            "smoke_forbidden": True,
            "required_build_status": "COMPLETE",
            "required_index_decision": (
                "EPIC_P23_102_FULL_TIMELINE_PIPELINE_READY"
            ),
            "required_files": list(REQUIRED_INDEX_FILES),
            "future_index_may_be_absent_in_plan_mode": True,
        },
        "blind_mining_boundary": {
            "allowed_inputs": [
                "SigLIP2 visual segment embeddings and exact intervals",
                "quality-gated Whisper chunks and BM25 statistics",
                "CLAP audio segment embeddings, RMS, and quality flags",
                "temporal separation",
                "embedding-based object/state continuity hypotheses",
                "whole-source recurrence and alternative-route searches",
            ],
            "sealed_inputs": [
                "EPIC action labels",
                "EPIC narration labels and timestamps",
                "EPIC-SOUNDS labels and timestamps",
                "task or procedure labels",
                "benchmark splits or outcomes",
                "human semantic annotations",
                "existing candidate-family labels",
            ],
            "semantic_annotation_parameter_exposed": False,
            "machine_retrieval_is_not_semantic_evidence": True,
            "raw_media_decoded_by_miner": False,
            "network_access": False,
        },
        "target_profiles": {
            "profiles": ["V+A", "V+S", "V+S+A", "coherent_far_multi_hop"],
            "quota_forcing_forbidden": True,
            "empty_profile_is_valid": True,
            "speech_absence_requires_honest_zero": True,
            "independent_non_speech_absence_requires_honest_zero": True,
        },
        "generation": {
            "fine_visual_windows_only": True,
            "local": {
                "visual_transition_calibration": {
                    "distribution": (
                        "all searchable fine-window local-neighbor cosine distances"
                    ),
                    "quantile": 0.95,
                    "quantile_interpolation": "linear",
                    "robust_mad_multiplier": 2.0,
                    "minimum_absolute_effect": 0.02,
                    "threshold_rule": (
                        "max(minimum_absolute_effect, quantile, "
                        "median + robust_mad_multiplier * median_absolute_deviation)"
                    ),
                    "semantic_labels_used": False,
                },
                "minimum_speech_quality": 0.2,
                "minimum_center_separation_seconds": 12.0,
                "diversity_time_bin_seconds": 300.0,
                "maximum_per_time_bin": 2,
                "maximum_retained_review_leads": 12,
            },
            "audio": {
                "minimum_audio_novelty": 0.16,
                "minimum_rms_full_scale": 0.00001,
                "maximum_overlapping_speech_tokens_for_independence": 8,
                "near_silence_is_ineligible": True,
                "inventory_only_asr_counts_as_speech": False,
            },
            "far": {
                "minimum_center_separation_seconds": 120.0,
                "minimum_visual_continuity": 0.88,
                "strong_visual_continuity": 0.96,
                "minimum_audio_continuity": 0.80,
                "shared_salient_term_minimum": 1,
                "pair_generation_scope": (
                    "all eligible separated searchable fine-window pairs"
                ),
                "maximum_endpoint_reuse": 1,
                "separation_bucket_seconds": [120.0, 300.0, 600.0, 1200.0],
                "maximum_per_separation_bucket": 2,
                "first_component_time_bin_seconds": 600.0,
                "maximum_per_first_component_time_bin": 2,
                "maximum_retained_review_leads": 8,
                "distance_alone_is_never_coherence": True,
            },
            "recurrence": {
                "visual_similarity_threshold": 0.985,
                "minimum_center_separation_seconds": 16.0,
                "speech_bm25_route_cap": 5,
                "visual_route_cap": 5,
            },
        },
        "candidate_contract": {
            "machine_provisional_statuses": sorted(PROVISIONAL_STATUSES),
            "required_outputs": [
                "exact evidence record handles and integer-microsecond timestamps",
                "modality-work hypotheses",
                "atomic claim templates",
                "alternative-route and substitution risks",
                "whole-source recurrence checks",
                "far-coherence metrics and hypothesis when applicable",
                "source calibration diagnostics and exact filter-flow counts",
                "candidate and registry deterministic hashes",
            ],
            "accepted_family_count": 0,
            "accepted_ses_count": 0,
            "h_tier_count": 0,
            "gate_a_credit": False,
            "future_test_eligible": False,
        },
        "human_prescreen_gate": {
            "required_before_any_accepted_family_ses_or_h_tier": True,
            "protocol_scope": "SOURCE_UNIFORM_ALL_MACHINE_LEADS",
            "same_form_and_exposure_policy_for_every_machine_lead": True,
            "full_source_recurrence_review_required": True,
            "prescreen_join_occurs_after_machine_ranking": True,
            "prescreen_labels_never_feed_back_into_machine_ranking": True,
            "even_complete_prescreen_does_not_accept_or_assign_tiers": True,
            "normal_acceptance_pipeline_not_implemented_here": True,
        },
        "execution": {
            "default_mode": "plan",
            "modes": ["plan", "mine", "check"],
            "default_output": DEFAULT_OUTPUT.as_posix(),
            "plan_mode_reads_index": False,
            "plan_mode_writes_output": False,
            "mine_requires_complete_future_index": True,
        },
        "resource_estimate": {
            "expected_fine_windows": 892,
            "expected_speech_chunks": 119,
            "vector_decode_peak_mib": "approximately 8-20",
            "candidate_working_set_peak_mib": "approximately 32-96",
            "single_cpu_wall_clock": "approximately 2-30 minutes",
            "dominant_operations": [
                "fine-window vector decode",
                "source-only transition quantile and robust-MAD calibration",
                "local-neighbor transition scoring",
                "bounded recurrence search",
                "all eligible separated fine-window far-pair coherence scoring",
                "deterministic diversity-capped candidate materialization",
                "BM25 recurrence replay",
            ],
            "media_decode_passes": 0,
            "model_inference_runs": 0,
            "network_requests": 0,
        },
        "post_index_commands": {
            "plan": (
                "python tools/epic_p23_102_family_mining_v1.py --mode plan"
            ),
            "mine": (
                "python tools/epic_p23_102_family_mining_v1.py --mode mine "
                "--output data/restricted/epic_p23_102_family_mining_v1_dev/"
                "candidate_registry.json"
            ),
            "mine_with_prescreen": (
                "python tools/epic_p23_102_family_mining_v1.py --mode mine "
                "--prescreen <completed-source-uniform-prescreen.json> "
                "--output data/restricted/epic_p23_102_family_mining_v1_dev/"
                "candidate_registry.json"
            ),
            "check": (
                "python tools/epic_p23_102_family_mining_v1.py --mode check "
                "--registry data/restricted/epic_p23_102_family_mining_v1_dev/"
                "candidate_registry.json"
            ),
        },
    }
    return _seal(plan, "plan_payload_sha256")


def _verify_self_hash(document: Mapping[str, Any], field: str) -> None:
    body = {key: value for key, value in document.items() if key != field}
    if document.get(field) != object_hash(body):
        raise MiningError(f"{field.upper()}_MISMATCH")


def load_index_bundle(
    repo_root: str | Path,
    *,
    index_root: str | Path = INDEX_RELATIVE_ROOT,
) -> dict[str, Any]:
    """Load and fail-closed validate the future canonical full index."""
    root = Path(repo_root).resolve()
    index_dir = _safe_path(root, index_root, label="INDEX_ROOT")
    if index_dir.name.endswith("_smoke"):
        raise MiningError("SMOKE_INDEX_FORBIDDEN")
    paths = {
        name: index_dir / name
        for name in REQUIRED_INDEX_FILES
    }
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise MiningError("FUTURE_FULL_INDEX_NOT_READY:" + ",".join(missing))
    documents = {name: _load_json(path) for name, path in paths.items()}
    segment = documents["segment_manifest.json"]
    observation = documents["observation_manifest.json"]
    index = documents["full_timeline_index.json"]
    resource = documents["resource_manifest.json"]
    checkpoint = documents["checkpoint_manifest.json"]
    build = documents["build_manifest.json"]
    for document, field in (
        (segment, "segment_manifest_hash"),
        (observation, "observation_manifest_hash"),
        (index, "index_hash"),
        (resource, "resource_manifest_hash"),
        (checkpoint, "checkpoint_manifest_hash"),
        (build, "build_manifest_hash"),
    ):
        _verify_self_hash(document, field)
    if build.get("status") != "COMPLETE" or build.get("smoke_seconds") is not None:
        raise MiningError("FULL_INDEX_NOT_COMPLETE")
    if build.get("decision") != "EPIC_P23_102_FULL_TIMELINE_PIPELINE_READY":
        raise MiningError("UNEXPECTED_INDEX_DECISION")
    for document in (segment, index, build):
        if document.get("source_ref") != "P23_102":
            raise MiningError("UNEXPECTED_SOURCE")
    terminal = build.get("terminal_boundary", {})
    if (
        terminal.get("index_only") is not True
        or terminal.get("families_generated") is not False
        or terminal.get("human_or_ses_or_h_or_gate_claim_generated") is not False
    ):
        raise MiningError("INDEX_TERMINAL_BOUNDARY_VIOLATION")
    governance = index.get("governance", {})
    if (
        governance.get("semantic_annotations_used_during_source_selection")
        is not False
        or governance.get("human_review_performed") is not False
        or governance.get("h_tier_assigned") is not False
    ):
        raise MiningError("INDEX_GOVERNANCE_VIOLATION")
    modalities = index.get("modalities", {})
    for modality in ("speech", "siglip2_visual", "clap_audio"):
        if not isinstance(modalities.get(modality, {}).get("documents"), list):
            raise MiningError(f"MISSING_MODALITY:{modality}")
    input_bindings = [
        {
            "path": _relative(root, path),
            "sha256": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in paths.values()
    ]
    return {
        "root": root,
        "index_root": index_dir,
        "documents": documents,
        "segment_manifest": segment,
        "observation_manifest": observation,
        "index": index,
        "resource_manifest": resource,
        "checkpoint_manifest": checkpoint,
        "build_manifest": build,
        "input_bindings": input_bindings,
    }


def _speech_terms(
    document: Mapping[str, Any],
    speech_index: Mapping[str, Any],
    *,
    limit: int = 6,
) -> list[str]:
    n = max(1, len(speech_index.get("documents", [])))
    frequencies = document.get("term_frequency", {})
    document_frequency = speech_index.get("document_frequency", {})
    scored = []
    for term, count in frequencies.items():
        if term in STOPWORDS or len(term) < 3:
            continue
        df = int(document_frequency.get(term, 0))
        idf = math.log(1.0 + (n + 0.5) / (df + 0.5))
        scored.append((float(count) * idf, term))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [term for _, term in scored[:limit]]


def _bm25_routes(
    anchor: Mapping[str, Any],
    speech_index: Mapping[str, Any],
    *,
    cap: int,
) -> list[dict[str, Any]]:
    query_terms = _speech_terms(anchor, speech_index)
    if not query_terms:
        return []
    documents = speech_index["documents"]
    average = float(speech_index.get("average_document_length", 0.0)) or 1.0
    n = max(1, len(documents))
    routes = []
    for document in documents:
        if (
            document.get("chunk_id") == anchor.get("chunk_id")
            or not document.get("searchable")
        ):
            continue
        score = 0.0
        for term in query_terms:
            frequency = int(document.get("term_frequency", {}).get(term, 0))
            if not frequency:
                continue
            df = int(
                speech_index.get("document_frequency", {}).get(term, 0)
            )
            inverse = math.log(1 + (n - df + 0.5) / (df + 0.5))
            denominator = frequency + 1.2 * (
                0.25
                + 0.75
                * int(document.get("document_length", 0))
                / average
            )
            score += inverse * frequency * 2.2 / denominator
        if score > 0:
            routes.append(
                {
                    "record_id": document["chunk_id"],
                    "start_us": int(document["start_us"]),
                    "end_us": int(document["end_us"]),
                    "bm25_score": _round(score),
                    "shared_salient_terms": sorted(
                        set(query_terms)
                        & set(document.get("term_frequency", {}))
                    ),
                }
            )
    routes.sort(key=lambda item: (-item["bm25_score"], item["record_id"]))
    return routes[:cap]


def _speech_for_window(
    window: Mapping[str, Any],
    documents: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    options = [
        item
        for item in documents
        if item.get("searchable") and _overlap_us(window, item) > 0
    ]
    if not options:
        return None
    options.sort(
        key=lambda item: (
            -_overlap_us(window, item),
            -int(item.get("document_length", 0)),
            str(item["chunk_id"]),
        )
    )
    return options[0]


def _overlapping_speech_token_count(
    window: Mapping[str, Any],
    documents: Sequence[Mapping[str, Any]],
) -> int:
    return sum(
        int(item.get("document_length", 0))
        for item in documents
        if item.get("searchable") and _overlap_us(window, item) > 0
    )


def _visual_recurrences(
    anchor_index: int,
    visual: Sequence[Mapping[str, Any]],
    vectors: Sequence[np.ndarray],
    *,
    threshold: float,
    separation_us: int,
    cap: int,
) -> list[dict[str, Any]]:
    anchor = visual[anchor_index]
    routes = []
    for index, document in enumerate(visual):
        if index == anchor_index:
            continue
        separation = abs(_center(document) - _center(anchor))
        if separation < separation_us:
            continue
        similarity = _cosine(vectors[anchor_index], vectors[index])
        if similarity >= threshold:
            routes.append(
                {
                    "record_id": document["segment_id"],
                    "start_us": int(document["start_us"]),
                    "end_us": int(document["end_us"]),
                    "cosine_similarity": _round(similarity),
                }
            )
    routes.sort(
        key=lambda item: (-item["cosine_similarity"], item["record_id"])
    )
    return routes[:cap]


def _evidence_handle(
    *,
    source_sha256: str,
    modality: str,
    document: Mapping[str, Any],
    role: str,
) -> dict[str, Any]:
    record_id = str(
        document.get("segment_id", document.get("chunk_id", ""))
    )
    body = {
        "source_id": "P23_102",
        "source_sha256": source_sha256,
        "modality": modality,
        "record_id": record_id,
        "start_us": int(document["start_us"]),
        "end_us": int(document["end_us"]),
        "start_seconds": _seconds(int(document["start_us"])),
        "end_seconds": _seconds(int(document["end_us"])),
        "retrieval_role": role,
        "human_semantic_validation": "NOT_PERFORMED",
    }
    body["evidence_handle_id"] = "eh." + object_hash(body).split(":", 1)[1][
        :20
    ]
    return body


def _transition_scores(vectors: Sequence[np.ndarray]) -> list[float]:
    scores = []
    for index, vector in enumerate(vectors):
        distances = []
        if index:
            distances.append(1.0 - _cosine(vector, vectors[index - 1]))
        if index + 1 < len(vectors):
            distances.append(1.0 - _cosine(vector, vectors[index + 1]))
        scores.append(max(distances, default=0.0))
    return scores


def _linear_quantile(values: Sequence[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _distribution_summary(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return {
            "count": 0,
            "minimum": 0.0,
            "median": 0.0,
            "p95": 0.0,
            "p99": 0.0,
            "maximum": 0.0,
        }
    return {
        "count": len(values),
        "minimum": _round(min(values)),
        "median": _round(_linear_quantile(values, 0.5)),
        "p95": _round(_linear_quantile(values, 0.95)),
        "p99": _round(_linear_quantile(values, 0.99)),
        "maximum": _round(max(values)),
    }


def _calibrate_transition(
    transitions: Sequence[float],
    rule: Mapping[str, Any],
) -> tuple[float, dict[str, Any]]:
    quantile = float(rule["quantile"])
    median = _linear_quantile(transitions, 0.5)
    deviations = [abs(float(value) - median) for value in transitions]
    mad = _linear_quantile(deviations, 0.5)
    quantile_value = _linear_quantile(transitions, quantile)
    robust_value = median + float(rule["robust_mad_multiplier"]) * mad
    absolute_floor = float(rule["minimum_absolute_effect"])
    selected = max(absolute_floor, quantile_value, robust_value)
    diagnostics = {
        "definition": (
            "max(1-cosine(previous,current),1-cosine(current,next))"
        ),
        "population": rule["distribution"],
        "semantic_labels_used": False,
        "distribution": _distribution_summary(transitions),
        "quantile": quantile,
        "quantile_interpolation": rule["quantile_interpolation"],
        "quantile_value": _round(quantile_value),
        "median_absolute_deviation": _round(mad),
        "robust_mad_multiplier": float(rule["robust_mad_multiplier"]),
        "robust_value": _round(robust_value),
        "minimum_absolute_effect": _round(absolute_floor),
        "selected_threshold": _round(selected),
        "selected_rule": rule["threshold_rule"],
        "pass_count": sum(value >= selected for value in transitions),
    }
    return selected, diagnostics


def _audio_novelty(
    visual_document: Mapping[str, Any],
    audio_by_id: Mapping[str, Mapping[str, Any]],
    ordered_audio: Sequence[Mapping[str, Any]],
    audio_vectors: Mapping[str, np.ndarray],
    audio_positions: Mapping[str, int] | None = None,
) -> tuple[Mapping[str, Any] | None, float]:
    audio = audio_by_id.get(str(visual_document["segment_id"]))
    if audio is None or str(audio["segment_id"]) not in audio_vectors:
        return None, 0.0
    identifier = str(audio["segment_id"])
    index = (
        int(audio_positions.get(identifier, -1))
        if audio_positions is not None
        else next(
            (
                idx
                for idx, item in enumerate(ordered_audio)
                if item["segment_id"] == audio["segment_id"]
            ),
            -1,
        )
    )
    distances = []
    if index > 0:
        distances.append(
            1.0
            - _cosine(
                audio_vectors[str(audio["segment_id"])],
                audio_vectors[str(ordered_audio[index - 1]["segment_id"])],
            )
        )
    if 0 <= index + 1 < len(ordered_audio):
        distances.append(
            1.0
            - _cosine(
                audio_vectors[str(audio["segment_id"])],
                audio_vectors[str(ordered_audio[index + 1]["segment_id"])],
            )
        )
    return audio, max(distances, default=0.0)


def _audio_floor_state(
    audio: Mapping[str, Any] | None,
    novelty: float,
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    novelty_pass = bool(
        audio is not None
        and novelty
        >= float(plan["generation"]["audio"]["minimum_audio_novelty"])
    )
    rms_pass = bool(
        audio is not None
        and float(audio.get("audio_rms_full_scale", 0.0))
        >= float(plan["generation"]["audio"]["minimum_rms_full_scale"])
    )
    silence_pass = bool(
        audio is not None
        and "NEAR_SILENCE" not in audio.get("quality_flags", [])
    )
    return {
        "novelty_pass": novelty_pass,
        "rms_pass": rms_pass,
        "not_near_silence": silence_pass,
        "structural_floor_pass": novelty_pass and rms_pass and silence_pass,
    }


def _status_for_local(
    transition: float,
    transition_threshold: float,
    speech_quality: float,
    visual_recurrence_count: int,
) -> tuple[str, str]:
    if visual_recurrence_count >= 4:
        return (
            "REJECT",
            (
                "The structural route is dominated by whole-source visual "
                "recurrence and is retained only as a machine-provisional "
                "shortcut rejection."
            ),
        )
    if (
        transition >= transition_threshold * 1.35
        and speech_quality >= 0.5
        and visual_recurrence_count <= 2
    ):
        return (
            "KEEP",
            (
                "Strong blind visual transition plus quality-gated speech with "
                "limited machine-detected visual recurrence."
            ),
        )
    if transition >= transition_threshold and speech_quality >= 0.2:
        return (
            "REPAIR",
            (
                "The structural V+S route clears generation floors but requires "
                "human source-world semantics and shortcut closure."
            ),
        )
    return (
        "REJECT",
        (
            "The blind structural route is too weak or recurrence-prone for "
            "prescreen priority."
        ),
    )


def _status_for_far(
    continuity: float,
    transition: float,
    transition_threshold: float,
    shared_terms: Sequence[str],
    recurrence_count: int,
) -> tuple[str, str]:
    if recurrence_count >= 6:
        return (
            "REJECT",
            (
                "The separated route is dominated by recurrent visual states; "
                "the apparent far composition is provisionally rejected as a "
                "shortcut-prone recurrence."
            ),
        )
    if (
        continuity >= 0.96
        and transition >= transition_threshold * 1.35
        and shared_terms
        and recurrence_count <= 3
    ):
        return (
            "KEEP",
            (
                "Far-separated components have strong visual continuity, a "
                "state-change anchor, and an independent lexical bridge."
            ),
        )
    if continuity >= 0.88 and (shared_terms or continuity >= 0.96):
        return (
            "REPAIR",
            (
                "Distance is accompanied by a measurable continuity bridge, but "
                "human review must establish one coherent source-world chain."
            ),
        )
    return (
        "REJECT",
        "Temporal distance lacks a sufficient independent coherence bridge.",
    )


def _candidate_hash(candidate: dict[str, Any]) -> dict[str, Any]:
    return _seal(candidate, "candidate_payload_sha256")


def _local_candidate(
    *,
    visual_index: int,
    visual: Sequence[Mapping[str, Any]],
    visual_vectors: Sequence[np.ndarray],
    transition_scores: Sequence[float],
    speech: Mapping[str, Any],
    speech_index: Mapping[str, Any],
    audio: Mapping[str, Any] | None,
    audio_novelty: float,
    source_sha256: str,
    plan: Mapping[str, Any],
    transition_threshold: float,
) -> dict[str, Any]:
    window = visual[visual_index]
    recurrence = _visual_recurrences(
        visual_index,
        visual,
        visual_vectors,
        threshold=float(
            plan["generation"]["recurrence"]["visual_similarity_threshold"]
        ),
        separation_us=round(
            float(
                plan["generation"]["recurrence"][
                    "minimum_center_separation_seconds"
                ]
            )
            * 1_000_000
        ),
        cap=int(plan["generation"]["recurrence"]["visual_route_cap"]),
    )
    speech_routes = _bm25_routes(
        speech,
        speech_index,
        cap=int(plan["generation"]["recurrence"]["speech_bm25_route_cap"]),
    )
    token_count = int(speech.get("document_length", 0))
    audio_floor = _audio_floor_state(audio, audio_novelty, plan)
    audio_eligible = bool(
        audio_floor["structural_floor_pass"]
        and token_count
        <= int(
            plan["generation"]["audio"][
                "maximum_overlapping_speech_tokens_for_independence"
            ]
        )
    )
    profile = "V+S+A" if audio_eligible else "V+S"
    speech_quality = min(1.0, token_count / 8.0)
    status, rationale = _status_for_local(
        transition_scores[visual_index],
        transition_threshold,
        speech_quality,
        len(recurrence),
    )
    handles = [
        _evidence_handle(
            source_sha256=source_sha256,
            modality="vision",
            document=window,
            role="local_state_transition_hypothesis",
        ),
        _evidence_handle(
            source_sha256=source_sha256,
            modality="speech",
            document=speech,
            role="local_spoken_proposition_hypothesis",
        ),
    ]
    if audio_eligible and audio is not None:
        handles.append(
            _evidence_handle(
                source_sha256=source_sha256,
                modality="ambient_audio",
                document=audio,
                role="structurally_independent_non_speech_hypothesis",
            )
        )
    fingerprint = {
        "kind": "local",
        "vision": window["segment_id"],
        "speech": speech["chunk_id"],
        "audio": audio["segment_id"] if audio_eligible and audio else None,
    }
    identifier = object_hash(fingerprint).split(":", 1)[1][:16]
    modality_work = {
        "V": (
            "Hypothesis: the cited non-text visual interval distinguishes an "
            "observable pre/post object or state configuration."
        ),
        "S": (
            "Hypothesis: the cited ASR interval supplies a proposition, relation, "
            "or procedural property not fixed by the visual transition alone."
        ),
        "A": (
            "Hypothesis: the cited CLAP window contains a temporally localized "
            "non-speech event with structural novelty not reducible to the sparse "
            "overlapping ASR route."
            if audio_eligible
            else (
                "HONEST_ZERO_FOR_THIS_LEAD: no structurally independent "
                "answer-bearing non-speech work is asserted."
            )
        ),
    }
    candidate = {
        "candidate_id": f"EPIC-P23-102-LOCAL-{identifier}",
        "candidate_kind": "near_local",
        "machine_provisional_status": status,
        "status_rationale": rationale,
        "profile_hypothesis": profile,
        "profile_status": "HYPOTHESIS_NOT_MODALITY_NECESSITY",
        "question_template": (
            "What visually observable state transition occurs in the cited "
            "interval, and which source-world proposition in the cited speech "
            "is needed to resolve its role or result?"
            + (
                " Which localized non-speech event may add a distinct component?"
                if audio_eligible
                else ""
            )
        ),
        "answer_template": (
            "[VISUAL_STATE_OR_TRANSITION] together with "
            "[SPOKEN_RELATION_OR_PROPERTY]"
            + (
                " and [INDEPENDENT_NON_SPEECH_EVENT_OR_PROPERTY]"
                if audio_eligible
                else ""
            )
        ),
        "atomic_claim_templates": [
            {
                "claim_id": "c1",
                "template": (
                    "The exact visual interval establishes "
                    "[OBJECT_OR_STATE_TRANSITION]."
                ),
                "status": "MACHINE_TEMPLATE_UNFILLED",
            },
            {
                "claim_id": "c2",
                "template": (
                    "The exact speech interval establishes "
                    "[RELATION_OR_PROCEDURAL_PROPERTY]."
                ),
                "status": "MACHINE_TEMPLATE_UNFILLED",
            },
        ]
        + (
            [
                {
                    "claim_id": "c3",
                    "template": (
                        "The exact audio interval establishes "
                        "[NON_SPEECH_EVENT_OR_AUDIO_PROPERTY]."
                    ),
                    "status": "MACHINE_TEMPLATE_UNFILLED",
                }
            ]
            if audio_eligible
            else []
        ),
        "modality_work_hypotheses": modality_work,
        "evidence_handles": handles,
        "temporal_structure": {
            "hop_hypothesis": "one_hop",
            "temporal_hypothesis": "near_local",
            "evidence_center_separation_seconds": _round(
                abs(_center(window) - _center(speech)) / 1_000_000.0
            ),
            "far_coherence": None,
        },
        "structural_scores": {
            "visual_transition": _round(transition_scores[visual_index]),
            "visual_transition_calibrated_threshold": _round(
                transition_threshold
            ),
            "speech_quality": _round(speech_quality),
            "audio_novelty": _round(audio_novelty),
            "audio_rms_full_scale": (
                _round(float(audio.get("audio_rms_full_scale", 0.0)))
                if audio is not None
                else None
            ),
            "audio_not_near_silence": audio_floor["not_near_silence"],
            "audio_independence_floor_pass": audio_eligible,
        },
        "recurrence_checks": {
            "whole_source_visual_routes": recurrence,
            "whole_source_speech_bm25_routes": speech_routes,
            "human_full_source_recurrence_review_required": True,
            "machine_recurrence_is_not_adjudication": True,
        },
        "alternative_evidence_routes": [
            {
                "route_type": "visual_near_duplicate",
                "record_id": item["record_id"],
                "risk": "A repeated visual state may substitute for the cited V.",
            }
            for item in recurrence
        ]
        + [
            {
                "route_type": "speech_bm25_recurrence",
                "record_id": item["record_id"],
                "risk": "Repeated speech may answer the same proposition.",
            }
            for item in speech_routes
        ],
        "substitution_risks": [
            "ASR may narrate the visible transition completely.",
            "Text, package labels, appliance displays, or OCR may expose the answer.",
            "A visually similar recurrence may be a complete alternative route.",
            (
                "The machine transition may reflect camera motion rather than "
                "object/state work."
            ),
        ]
        + (
            [
                (
                    "Speech leakage may explain the audio novelty; human "
                    "listening is required."
                ),
                (
                    "CLAP geometry is routing evidence and does not name a "
                    "source-world sound."
                ),
            ]
            if audio_eligible
            else []
        ),
        "semantic_annotation_firewall": {
            "epic_semantic_labels_accessed": False,
            "human_labels_used_for_generation_or_ranking": False,
            "retrieval_observations_are_not_gold": True,
        },
        "human_prescreen": "NOT_PERFORMED",
        "accepted_family": False,
        "accepted_ses": False,
        "h_tier": None,
        "gate_a_credit": False,
    }
    return _candidate_hash(candidate)


def _far_candidate(
    *,
    first_index: int,
    second_index: int,
    visual: Sequence[Mapping[str, Any]],
    visual_vectors: Sequence[np.ndarray],
    transition_scores: Sequence[float],
    speech_documents: Sequence[Mapping[str, Any]],
    speech_index: Mapping[str, Any],
    audio_by_id: Mapping[str, Mapping[str, Any]],
    ordered_audio: Sequence[Mapping[str, Any]],
    audio_vectors: Mapping[str, np.ndarray],
    source_sha256: str,
    plan: Mapping[str, Any],
    transition_threshold: float,
) -> dict[str, Any]:
    first = visual[first_index]
    second = visual[second_index]
    first_speech = _speech_for_window(first, speech_documents)
    second_speech = _speech_for_window(second, speech_documents)
    assert first_speech is not None and second_speech is not None
    first_terms = set(_speech_terms(first_speech, speech_index))
    second_terms = set(_speech_terms(second_speech, speech_index))
    shared_terms = sorted(first_terms & second_terms)
    continuity = _cosine(
        visual_vectors[first_index], visual_vectors[second_index]
    )
    first_recurrence = _visual_recurrences(
        first_index,
        visual,
        visual_vectors,
        threshold=float(
            plan["generation"]["recurrence"]["visual_similarity_threshold"]
        ),
        separation_us=round(
            float(
                plan["generation"]["recurrence"][
                    "minimum_center_separation_seconds"
                ]
            )
            * 1_000_000
        ),
        cap=int(plan["generation"]["recurrence"]["visual_route_cap"]),
    )
    second_recurrence = _visual_recurrences(
        second_index,
        visual,
        visual_vectors,
        threshold=float(
            plan["generation"]["recurrence"]["visual_similarity_threshold"]
        ),
        separation_us=round(
            float(
                plan["generation"]["recurrence"][
                    "minimum_center_separation_seconds"
                ]
            )
            * 1_000_000
        ),
        cap=int(plan["generation"]["recurrence"]["visual_route_cap"]),
    )
    first_audio, first_audio_novelty = _audio_novelty(
        first, audio_by_id, ordered_audio, audio_vectors
    )
    second_audio, second_audio_novelty = _audio_novelty(
        second, audio_by_id, ordered_audio, audio_vectors
    )
    audio_choice = None
    audio_novelty = 0.0
    for item, novelty, speech in (
        (first_audio, first_audio_novelty, first_speech),
        (second_audio, second_audio_novelty, second_speech),
    ):
        if (
            item is not None
            and novelty > audio_novelty
            and novelty
            >= float(plan["generation"]["audio"]["minimum_audio_novelty"])
            and float(item.get("audio_rms_full_scale", 0.0))
            >= float(plan["generation"]["audio"]["minimum_rms_full_scale"])
            and "NEAR_SILENCE" not in item.get("quality_flags", [])
            and int(speech.get("document_length", 0))
            <= int(
                plan["generation"]["audio"][
                    "maximum_overlapping_speech_tokens_for_independence"
                ]
            )
        ):
            audio_choice = item
            audio_novelty = novelty
    profile = "V+S+A" if audio_choice is not None else "V+S"
    recurrence_count = len(
        {item["record_id"] for item in first_recurrence + second_recurrence}
    )
    status, rationale = _status_for_far(
        continuity,
        max(transition_scores[first_index], transition_scores[second_index]),
        transition_threshold,
        shared_terms,
        recurrence_count,
    )
    handles = [
        _evidence_handle(
            source_sha256=source_sha256,
            modality="vision",
            document=first,
            role="far_component_1_state_or_object_hypothesis",
        ),
        _evidence_handle(
            source_sha256=source_sha256,
            modality="speech",
            document=first_speech,
            role="far_component_1_spoken_bridge_hypothesis",
        ),
        _evidence_handle(
            source_sha256=source_sha256,
            modality="vision",
            document=second,
            role="far_component_2_state_or_object_hypothesis",
        ),
        _evidence_handle(
            source_sha256=source_sha256,
            modality="speech",
            document=second_speech,
            role="far_component_2_spoken_bridge_hypothesis",
        ),
    ]
    if audio_choice is not None:
        handles.append(
            _evidence_handle(
                source_sha256=source_sha256,
                modality="ambient_audio",
                document=audio_choice,
                role="far_chain_independent_non_speech_hypothesis",
            )
        )
    fingerprint = {
        "kind": "far",
        "first": first["segment_id"],
        "second": second["segment_id"],
        "speech": [first_speech["chunk_id"], second_speech["chunk_id"]],
        "audio": (
            audio_choice["segment_id"] if audio_choice is not None else None
        ),
    }
    identifier = object_hash(fingerprint).split(":", 1)[1][:16]
    combined_recurrence = sorted(
        {
            item["record_id"]: item
            for item in first_recurrence + second_recurrence
        }.values(),
        key=lambda item: (-item["cosine_similarity"], item["record_id"]),
    )
    candidate = {
        "candidate_id": f"EPIC-P23-102-FAR-{identifier}",
        "candidate_kind": "coherent_far_multi_hop",
        "machine_provisional_status": status,
        "status_rationale": rationale,
        "profile_hypothesis": profile,
        "profile_status": "HYPOTHESIS_NOT_MODALITY_NECESSITY",
        "question_template": (
            "How does [EARLIER_OBJECT_OR_STATE] in the first exact interval "
            "relate to [LATER_STATE_OR_CONSEQUENCE] in the second exact interval, "
            "and which speech proposition is required to compose the relation?"
            + (
                " Which localized non-speech event may contribute distinct work?"
                if audio_choice is not None
                else ""
            )
        ),
        "answer_template": (
            "[EARLIER_COMPONENT] then [LATER_COMPONENT], linked by "
            "[OBJECT_STATE_OR_PROCEDURAL_CONTINUITY] and "
            "[SPOKEN_RELATION]"
            + (
                " with [INDEPENDENT_NON_SPEECH_COMPONENT]"
                if audio_choice is not None
                else ""
            )
        ),
        "atomic_claim_templates": [
            {
                "claim_id": "c1",
                "template": (
                    "The first exact interval establishes "
                    "[EARLIER_OBJECT_STATE_OR_ACTION_RESULT]."
                ),
                "status": "MACHINE_TEMPLATE_UNFILLED",
            },
            {
                "claim_id": "c2",
                "template": (
                    "The second exact interval establishes "
                    "[LATER_OBJECT_STATE_OR_CONSEQUENCE]."
                ),
                "status": "MACHINE_TEMPLATE_UNFILLED",
            },
            {
                "claim_id": "c3",
                "template": (
                    "The two components form one coherent chain because "
                    "[EXPLICIT_SOURCE_WORLD_CONTINUITY_RELATION]."
                ),
                "status": "MACHINE_TEMPLATE_UNFILLED",
            },
        ]
        + (
            [
                {
                    "claim_id": "c4",
                    "template": (
                        "The audio interval establishes "
                        "[INDEPENDENT_NON_SPEECH_EVENT_OR_PROPERTY]."
                    ),
                    "status": "MACHINE_TEMPLATE_UNFILLED",
                }
            ]
            if audio_choice is not None
            else []
        ),
        "modality_work_hypotheses": {
            "V": (
                "Hypothesis: the two visual intervals establish earlier/later "
                "object or state components and their continuity."
            ),
            "S": (
                "Hypothesis: speech supplies a relation or property needed to "
                "compose the separated components."
            ),
            "A": (
                "Hypothesis: the cited audio novelty contributes a localized "
                "non-speech component distinct from sparse ASR."
                if audio_choice is not None
                else (
                    "HONEST_ZERO_FOR_THIS_LEAD: no structurally independent "
                    "answer-bearing non-speech work is asserted."
                )
            ),
        },
        "evidence_handles": handles,
        "temporal_structure": {
            "hop_hypothesis": "multi_hop",
            "temporal_hypothesis": "far_separated",
            "evidence_center_separation_seconds": _round(
                abs(_center(second) - _center(first)) / 1_000_000.0
            ),
            "far_coherence": {
                "distance_alone_is_not_credited": True,
                "visual_object_or_state_continuity_cosine": _round(continuity),
                "shared_salient_asr_terms": shared_terms,
                "shared_term_count": len(shared_terms),
                "coherence_hypothesis": (
                    "The separated intervals may concern the same object/state "
                    "family because visual continuity exceeds the frozen floor"
                    + (
                        " and independently derived ASR terms recur."
                        if shared_terms
                        else (
                            "; no lexical bridge exists, so only very strong "
                            "visual continuity permits a REPAIR lead."
                        )
                    )
                ),
                "human_source_world_coherence_validation": "REQUIRED",
            },
        },
        "structural_scores": {
            "visual_transition_component_1": _round(
                transition_scores[first_index]
            ),
            "visual_transition_component_2": _round(
                transition_scores[second_index]
            ),
            "visual_continuity": _round(continuity),
            "audio_novelty": _round(audio_novelty),
            "audio_independence_floor_pass": audio_choice is not None,
        },
        "recurrence_checks": {
            "whole_source_visual_routes": combined_recurrence,
            "whole_source_speech_bm25_routes": {
                first_speech["chunk_id"]: _bm25_routes(
                    first_speech,
                    speech_index,
                    cap=int(
                        plan["generation"]["recurrence"][
                            "speech_bm25_route_cap"
                        ]
                    ),
                ),
                second_speech["chunk_id"]: _bm25_routes(
                    second_speech,
                    speech_index,
                    cap=int(
                        plan["generation"]["recurrence"][
                            "speech_bm25_route_cap"
                        ]
                    ),
                ),
            },
            "human_full_source_recurrence_review_required": True,
            "machine_recurrence_is_not_adjudication": True,
        },
        "alternative_evidence_routes": [
            {
                "route_type": "visual_near_duplicate",
                "record_id": item["record_id"],
                "risk": (
                    "A repeated object/state view may replace one composed hop "
                    "or reveal that the pair is merely recurrent."
                ),
            }
            for item in combined_recurrence
        ],
        "substitution_risks": [
            "One speech interval may answer the composed question alone.",
            (
                "The two intervals may be visually similar recurrences without "
                "one source-world chain."
            ),
            "Intervening intervals may provide a shorter complete route.",
            "Text, labels, OCR, or narration may duplicate either visual component.",
            "Far distance is not itself evidence of multi-hop coherence.",
        ]
        + (
            [
                "The CLAP novelty may be speech leakage or incidental handling.",
                "Human listening is required before any A work can be retained.",
            ]
            if audio_choice is not None
            else []
        ),
        "semantic_annotation_firewall": {
            "epic_semantic_labels_accessed": False,
            "human_labels_used_for_generation_or_ranking": False,
            "retrieval_observations_are_not_gold": True,
        },
        "human_prescreen": "NOT_PERFORMED",
        "accepted_family": False,
        "accepted_ses": False,
        "h_tier": None,
        "gate_a_credit": False,
    }
    return _candidate_hash(candidate)


def _far_visual_audio_candidate(
    *,
    first_index: int,
    second_index: int,
    visual: Sequence[Mapping[str, Any]],
    visual_vectors: Sequence[np.ndarray],
    transition_scores: Sequence[float],
    audio_by_id: Mapping[str, Mapping[str, Any]],
    audio_vectors: Mapping[str, np.ndarray],
    audio_novelties: Mapping[str, float],
    source_sha256: str,
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a speech-free far V+A structural lead."""
    first = visual[first_index]
    second = visual[second_index]
    first_audio = audio_by_id[str(first["segment_id"])]
    second_audio = audio_by_id[str(second["segment_id"])]
    continuity = _cosine(
        visual_vectors[first_index], visual_vectors[second_index]
    )
    audio_continuity = _cosine(
        audio_vectors[str(first_audio["segment_id"])],
        audio_vectors[str(second_audio["segment_id"])],
    )
    first_recurrence = _visual_recurrences(
        first_index,
        visual,
        visual_vectors,
        threshold=float(
            plan["generation"]["recurrence"]["visual_similarity_threshold"]
        ),
        separation_us=round(
            float(
                plan["generation"]["recurrence"][
                    "minimum_center_separation_seconds"
                ]
            )
            * 1_000_000
        ),
        cap=int(plan["generation"]["recurrence"]["visual_route_cap"]),
    )
    second_recurrence = _visual_recurrences(
        second_index,
        visual,
        visual_vectors,
        threshold=float(
            plan["generation"]["recurrence"]["visual_similarity_threshold"]
        ),
        separation_us=round(
            float(
                plan["generation"]["recurrence"][
                    "minimum_center_separation_seconds"
                ]
            )
            * 1_000_000
        ),
        cap=int(plan["generation"]["recurrence"]["visual_route_cap"]),
    )
    combined_recurrence = sorted(
        {
            item["record_id"]: item
            for item in first_recurrence + second_recurrence
        }.values(),
        key=lambda item: (-item["cosine_similarity"], item["record_id"]),
    )
    recurrence_count = len(combined_recurrence)
    if recurrence_count >= 6:
        status = "REJECT"
        rationale = (
            "The V+A far route is dominated by recurrent visual states and is "
            "retained only as a machine-provisional shortcut rejection."
        )
    else:
        status = "REPAIR"
        rationale = (
            "Separated visual and audio geometry provides a speech-free "
            "structural lead; human review must establish coherent source-world "
            "meaning, non-speech identity, and modality necessity."
        )
    fingerprint = {
        "kind": "far_visual_audio",
        "first": first["segment_id"],
        "second": second["segment_id"],
        "audio": [first_audio["segment_id"], second_audio["segment_id"]],
    }
    identifier = object_hash(fingerprint).split(":", 1)[1][:16]
    candidate = {
        "candidate_id": f"EPIC-P23-102-FAR-VA-{identifier}",
        "candidate_kind": "coherent_far_multi_hop",
        "machine_provisional_status": status,
        "status_rationale": rationale,
        "profile_hypothesis": "V+A",
        "profile_status": "HYPOTHESIS_NOT_MODALITY_NECESSITY",
        "question_template": (
            "How might the earlier and later visual states form one chain, and "
            "which localized non-speech audio change may distinguish the two "
            "components?"
        ),
        "answer_template": (
            "[EARLIER_VISUAL_COMPONENT] then [LATER_VISUAL_COMPONENT], linked "
            "by [SOURCE_WORLD_CONTINUITY] and [NON_SPEECH_AUDIO_RELATION]."
        ),
        "atomic_claim_templates": [
            {
                "claim_id": "c1",
                "template": (
                    "The first exact visual interval establishes "
                    "[EARLIER_OBJECT_OR_STATE]."
                ),
                "status": "MACHINE_TEMPLATE_UNFILLED",
            },
            {
                "claim_id": "c2",
                "template": (
                    "The second exact visual interval establishes "
                    "[LATER_OBJECT_OR_STATE]."
                ),
                "status": "MACHINE_TEMPLATE_UNFILLED",
            },
            {
                "claim_id": "c3",
                "template": (
                    "The exact audio intervals establish "
                    "[NON_SPEECH_CHANGE_OR_RELATION]."
                ),
                "status": "MACHINE_TEMPLATE_UNFILLED",
            },
        ],
        "modality_work_hypotheses": {
            "V": (
                "Hypothesis: separated visual intervals provide earlier/later "
                "object or state components."
            ),
            "S": (
                "NOT_USED: no inventory-only ASR is promoted and no "
                "quality-gated speech is required by this lead."
            ),
            "A": (
                "Hypothesis: both aligned audio windows clear structural "
                "novelty/RMS/silence floors and have cross-window continuity."
            ),
        },
        "evidence_handles": [
            _evidence_handle(
                source_sha256=source_sha256,
                modality="vision",
                document=first,
                role="far_component_1_state_or_object_hypothesis",
            ),
            _evidence_handle(
                source_sha256=source_sha256,
                modality="ambient_audio",
                document=first_audio,
                role="far_component_1_non_speech_structure_hypothesis",
            ),
            _evidence_handle(
                source_sha256=source_sha256,
                modality="vision",
                document=second,
                role="far_component_2_state_or_object_hypothesis",
            ),
            _evidence_handle(
                source_sha256=source_sha256,
                modality="ambient_audio",
                document=second_audio,
                role="far_component_2_non_speech_structure_hypothesis",
            ),
        ],
        "temporal_structure": {
            "hop_hypothesis": "multi_hop",
            "temporal_hypothesis": "far_separated",
            "evidence_center_separation_seconds": _round(
                abs(_center(second) - _center(first)) / 1_000_000.0
            ),
            "far_coherence": {
                "distance_alone_is_not_credited": True,
                "visual_object_or_state_continuity_cosine": _round(continuity),
                "audio_structural_continuity_cosine": _round(audio_continuity),
                "shared_salient_asr_terms": [],
                "shared_term_count": 0,
                "coherence_hypothesis": (
                    "The pair clears independently computed visual and audio "
                    "continuity floors without using speech inventory text."
                ),
                "human_source_world_coherence_validation": "REQUIRED",
            },
        },
        "structural_scores": {
            "visual_transition_component_1": _round(
                transition_scores[first_index]
            ),
            "visual_transition_component_2": _round(
                transition_scores[second_index]
            ),
            "visual_continuity": _round(continuity),
            "audio_continuity": _round(audio_continuity),
            "audio_novelty_component_1": _round(
                audio_novelties[str(first_audio["segment_id"])]
            ),
            "audio_novelty_component_2": _round(
                audio_novelties[str(second_audio["segment_id"])]
            ),
            "audio_rms_component_1": _round(
                float(first_audio.get("audio_rms_full_scale", 0.0))
            ),
            "audio_rms_component_2": _round(
                float(second_audio.get("audio_rms_full_scale", 0.0))
            ),
            "audio_independence_floor_pass": True,
        },
        "recurrence_checks": {
            "whole_source_visual_routes": combined_recurrence,
            "whole_source_speech_bm25_routes": {},
            "human_full_source_recurrence_review_required": True,
            "machine_recurrence_is_not_adjudication": True,
        },
        "alternative_evidence_routes": [
            {
                "route_type": "visual_near_duplicate",
                "record_id": item["record_id"],
                "risk": (
                    "A recurrent visual state may replace one component or show "
                    "that the pair is not one coherent chain."
                ),
            }
            for item in combined_recurrence
        ],
        "substitution_risks": [
            "The two intervals may be recurrent views rather than one chain.",
            "Audio continuity may be background ambience or recording conditions.",
            "CLAP novelty may reflect incidental handling or speech leakage.",
            "An intervening interval may provide a shorter complete route.",
            "Human listening and visual review are required before retaining A work.",
        ],
        "semantic_annotation_firewall": {
            "epic_semantic_labels_accessed": False,
            "human_labels_used_for_generation_or_ranking": False,
            "retrieval_observations_are_not_gold": True,
        },
        "human_prescreen": "NOT_PERFORMED",
        "accepted_family": False,
        "accepted_ses": False,
        "h_tier": None,
        "gate_a_credit": False,
    }
    return _candidate_hash(candidate)


def _local_visual_audio_candidate(
    *,
    visual_index: int,
    visual: Sequence[Mapping[str, Any]],
    visual_vectors: Sequence[np.ndarray],
    transition_scores: Sequence[float],
    transition_threshold: float,
    audio: Mapping[str, Any],
    audio_novelty: float,
    source_sha256: str,
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    window = visual[visual_index]
    recurrence = _visual_recurrences(
        visual_index,
        visual,
        visual_vectors,
        threshold=float(
            plan["generation"]["recurrence"]["visual_similarity_threshold"]
        ),
        separation_us=round(
            float(
                plan["generation"]["recurrence"][
                    "minimum_center_separation_seconds"
                ]
            )
            * 1_000_000
        ),
        cap=int(plan["generation"]["recurrence"]["visual_route_cap"]),
    )
    if len(recurrence) >= 4:
        status = "REJECT"
        rationale = (
            "The speech-free V+A route is dominated by visual recurrence and "
            "is retained only as a machine-provisional shortcut rejection."
        )
    else:
        status = "REPAIR"
        rationale = (
            "The calibrated visual transition and aligned audio structure clear "
            "source-only floors, but human review must establish semantics, "
            "non-speech identity, and modality necessity."
        )
    fingerprint = {
        "kind": "local_visual_audio",
        "vision": window["segment_id"],
        "audio": audio["segment_id"],
    }
    identifier = object_hash(fingerprint).split(":", 1)[1][:16]
    candidate = {
        "candidate_id": f"EPIC-P23-102-LOCAL-VA-{identifier}",
        "candidate_kind": "near_local",
        "machine_provisional_status": status,
        "status_rationale": rationale,
        "profile_hypothesis": "V+A",
        "profile_status": "HYPOTHESIS_NOT_MODALITY_NECESSITY",
        "question_template": (
            "What visual state transition occurs in the exact interval, and "
            "which localized non-speech audio change may distinguish it?"
        ),
        "answer_template": (
            "[VISUAL_STATE_OR_TRANSITION] together with "
            "[NON_SPEECH_AUDIO_EVENT_OR_PROPERTY]."
        ),
        "atomic_claim_templates": [
            {
                "claim_id": "c1",
                "template": (
                    "The exact visual interval establishes "
                    "[OBJECT_OR_STATE_TRANSITION]."
                ),
                "status": "MACHINE_TEMPLATE_UNFILLED",
            },
            {
                "claim_id": "c2",
                "template": (
                    "The exact audio interval establishes "
                    "[NON_SPEECH_EVENT_OR_AUDIO_PROPERTY]."
                ),
                "status": "MACHINE_TEMPLATE_UNFILLED",
            },
        ],
        "modality_work_hypotheses": {
            "V": (
                "Hypothesis: the visual interval distinguishes an observable "
                "pre/post object or state configuration."
            ),
            "S": (
                "NOT_USED: no inventory-only ASR is promoted and no "
                "quality-gated speech is required by this lead."
            ),
            "A": (
                "Hypothesis: the aligned audio window clears novelty, RMS, and "
                "near-silence structural floors."
            ),
        },
        "evidence_handles": [
            _evidence_handle(
                source_sha256=source_sha256,
                modality="vision",
                document=window,
                role="local_state_transition_hypothesis",
            ),
            _evidence_handle(
                source_sha256=source_sha256,
                modality="ambient_audio",
                document=audio,
                role="local_non_speech_structure_hypothesis",
            ),
        ],
        "temporal_structure": {
            "hop_hypothesis": "one_hop",
            "temporal_hypothesis": "near_local",
            "evidence_center_separation_seconds": _round(
                abs(_center(window) - _center(audio)) / 1_000_000.0
            ),
            "far_coherence": None,
        },
        "structural_scores": {
            "visual_transition": _round(transition_scores[visual_index]),
            "visual_transition_calibrated_threshold": _round(
                transition_threshold
            ),
            "audio_novelty": _round(audio_novelty),
            "audio_rms_full_scale": _round(
                float(audio.get("audio_rms_full_scale", 0.0))
            ),
            "audio_not_near_silence": (
                "NEAR_SILENCE" not in audio.get("quality_flags", [])
            ),
            "audio_independence_floor_pass": True,
        },
        "recurrence_checks": {
            "whole_source_visual_routes": recurrence,
            "whole_source_speech_bm25_routes": [],
            "human_full_source_recurrence_review_required": True,
            "machine_recurrence_is_not_adjudication": True,
        },
        "alternative_evidence_routes": [
            {
                "route_type": "visual_near_duplicate",
                "record_id": item["record_id"],
                "risk": "A repeated visual state may substitute for the cited V.",
            }
            for item in recurrence
        ],
        "substitution_risks": [
            "The visual transition may reflect camera motion.",
            "Audio novelty may be speech leakage or incidental handling.",
            "Background ambience may explain the audio geometry.",
            "Human listening is required before any A work can be retained.",
            "Text, labels, OCR, or displays may provide an easier route.",
        ],
        "semantic_annotation_firewall": {
            "epic_semantic_labels_accessed": False,
            "human_labels_used_for_generation_or_ranking": False,
            "retrieval_observations_are_not_gold": True,
        },
        "human_prescreen": "NOT_PERFORMED",
        "accepted_family": False,
        "accepted_ses": False,
        "h_tier": None,
        "gate_a_credit": False,
    }
    return _candidate_hash(candidate)


def _separation_bucket(seconds: float, boundaries: Sequence[float]) -> str:
    lower = 0.0
    for upper in boundaries:
        if seconds < float(upper):
            return f"{int(lower)}-{int(float(upper))}"
        lower = float(upper)
    return f"{int(lower)}+"


def _apply_prescreen(
    candidates: list[dict[str, Any]],
    prescreen: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if prescreen is None:
        return {
            "status": "NOT_PROVIDED",
            "protocol_scope": "SOURCE_UNIFORM_ALL_MACHINE_LEADS",
            "accepted_family_count": 0,
            "accepted_ses_count": 0,
            "h_tier_count": 0,
        }
    if (
        prescreen.get("schema_version")
        != "av-trace.source-uniform-human-prescreen/1.0"
        or prescreen.get("source_id") != "P23_102"
        or prescreen.get("protocol_scope")
        != "SOURCE_UNIFORM_ALL_MACHINE_LEADS"
        or prescreen.get("completed") is not True
        or prescreen.get("same_form_for_every_lead") is not True
        or prescreen.get("same_full_source_exposure_for_every_lead") is not True
        or prescreen.get("full_source_recurrence_review_completed") is not True
        or prescreen.get("necessity_or_h_tier_assigned") is not False
    ):
        raise MiningError("SOURCE_UNIFORM_HUMAN_PRESCREEN_INVALID")
    candidate_ids = [item["candidate_id"] for item in candidates]
    if prescreen.get("candidate_ids") != candidate_ids:
        raise MiningError("PRESCREEN_CANDIDATE_SET_OR_ORDER_MISMATCH")
    for candidate in candidates:
        body = {
            key: value
            for key, value in candidate.items()
            if key != "candidate_payload_sha256"
        }
        body["human_prescreen"] = "COMPLETE_NO_ACCEPTANCE_OR_TIER"
        candidate.clear()
        candidate.update(_candidate_hash(body))
    return {
        "status": "COMPLETE_NO_ACCEPTANCE_OR_TIER",
        "protocol_scope": "SOURCE_UNIFORM_ALL_MACHINE_LEADS",
        "same_form_for_every_lead": True,
        "same_full_source_exposure_for_every_lead": True,
        "full_source_recurrence_review_completed": True,
        "machine_ranking_recomputed_after_prescreen": False,
        "accepted_family_count": 0,
        "accepted_ses_count": 0,
        "h_tier_count": 0,
        "prescreen_payload_sha256": object_hash(prescreen),
    }


def mine_bundle(
    bundle: Mapping[str, Any],
    *,
    prescreen: Mapping[str, Any] | None = None,
    plan: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Mine deterministic machine-provisional candidates from an index bundle."""
    frozen_plan = copy.deepcopy(dict(plan or build_plan()))
    index = bundle["index"]
    modalities = index["modalities"]
    visual = sorted(
        [
            item
            for item in modalities["siglip2_visual"]["documents"]
            if item.get("searchable") and item.get("scale") == "fine"
        ],
        key=lambda item: (
            int(item["start_us"]),
            int(item["end_us"]),
            str(item["segment_id"]),
        ),
    )
    speech_index = modalities["speech"]
    all_speech_documents = sorted(
        list(speech_index["documents"]),
        key=lambda item: (
            int(item["start_us"]),
            int(item["end_us"]),
            str(item["chunk_id"]),
        ),
    )
    speech_documents = sorted(
        [
            item
            for item in all_speech_documents
            if item.get("searchable") and item.get("quality_gate_pass")
        ],
        key=lambda item: (
            int(item["start_us"]),
            int(item["end_us"]),
            str(item["chunk_id"]),
        ),
    )
    ordered_audio = sorted(
        [
            item
            for item in modalities["clap_audio"]["documents"]
            if item.get("searchable") and item.get("scale") == "fine"
        ],
        key=lambda item: (
            int(item["start_us"]),
            int(item["end_us"]),
            str(item["segment_id"]),
        ),
    )
    visual_vectors = [_vector(item) for item in visual]
    audio_vectors = {
        str(item["segment_id"]): _vector(item) for item in ordered_audio
    }
    audio_by_id = {
        str(item["segment_id"]): item for item in ordered_audio
    }
    audio_positions = {
        str(item["segment_id"]): index
        for index, item in enumerate(ordered_audio)
    }
    transitions = _transition_scores(visual_vectors)
    transition_rule = frozen_plan["generation"]["local"][
        "visual_transition_calibration"
    ]
    minimum_transition, transition_calibration = _calibrate_transition(
        transitions, transition_rule
    )
    speech_by_visual = [
        _speech_for_window(window, speech_documents) for window in visual
    ]
    searchable_speech_tokens_by_visual = [
        _overlapping_speech_token_count(window, speech_documents)
        for window in visual
    ]
    audio_novelties: dict[str, float] = {}
    audio_states: dict[str, dict[str, Any]] = {}
    for window in visual:
        audio, novelty = _audio_novelty(
            window,
            audio_by_id,
            ordered_audio,
            audio_vectors,
            audio_positions,
        )
        identifier = str(window["segment_id"])
        audio_novelties[identifier] = novelty
        audio_states[identifier] = _audio_floor_state(
            audio, novelty, frozen_plan
        )
    source_sha256 = str(
        bundle.get("resource_manifest", {})
        .get("source", {})
        .get("media_sha256", bundle.get("build_manifest", {}).get("source_sha256"))
    )
    local_rows: list[tuple[float, int, dict[str, Any]]] = []
    local_transition_pass = 0
    local_transition_with_speech = 0
    local_speech_quality_pass = 0
    local_transition_with_audio_structure = 0
    local_va_sparse_speech_pass = 0
    for visual_index, window in enumerate(visual):
        if transitions[visual_index] < minimum_transition:
            continue
        local_transition_pass += 1
        identifier = str(window["segment_id"])
        audio = audio_by_id.get(identifier)
        novelty = audio_novelties.get(identifier, 0.0)
        audio_state = audio_states[identifier]
        if audio_state["structural_floor_pass"]:
            local_transition_with_audio_structure += 1
        speech = speech_by_visual[visual_index]
        if speech is not None:
            local_transition_with_speech += 1
            speech_quality = min(
                1.0, int(speech.get("document_length", 0)) / 8.0
            )
            if speech_quality < float(
                frozen_plan["generation"]["local"]["minimum_speech_quality"]
            ):
                continue
            local_speech_quality_pass += 1
            candidate = _local_candidate(
                visual_index=visual_index,
                visual=visual,
                visual_vectors=visual_vectors,
                transition_scores=transitions,
                speech=speech,
                speech_index=speech_index,
                audio=audio,
                audio_novelty=novelty,
                source_sha256=source_sha256,
                plan=frozen_plan,
                transition_threshold=minimum_transition,
            )
            speech_quality_component = speech_quality
        elif (
            audio is not None
            and audio_state["structural_floor_pass"]
            and searchable_speech_tokens_by_visual[visual_index]
            <= int(
                frozen_plan["generation"]["audio"][
                    "maximum_overlapping_speech_tokens_for_independence"
                ]
            )
        ):
            local_va_sparse_speech_pass += 1
            candidate = _local_visual_audio_candidate(
                visual_index=visual_index,
                visual=visual,
                visual_vectors=visual_vectors,
                transition_scores=transitions,
                transition_threshold=minimum_transition,
                audio=audio,
                audio_novelty=novelty,
                source_sha256=source_sha256,
                plan=frozen_plan,
            )
            speech_quality_component = 0.0
        else:
            continue
        score = (
            0.65 * transitions[visual_index]
            + 0.2 * speech_quality_component
            + 0.15 * novelty
        )
        local_rows.append((score, visual_index, candidate))
    local_rows.sort(
        key=lambda item: (
            -item[0],
            int(visual[item[1]]["start_us"]),
            item[2]["candidate_id"],
        )
    )
    retained_local: list[dict[str, Any]] = []
    retained_centers: list[float] = []
    local_time_bin_counts: Counter[int] = Counter()
    local_separation_us = round(
        float(
            frozen_plan["generation"]["local"][
                "minimum_center_separation_seconds"
            ]
        )
        * 1_000_000
    )
    local_time_bin_us = round(
        float(
            frozen_plan["generation"]["local"]["diversity_time_bin_seconds"]
        )
        * 1_000_000
    )
    local_bin_cap = int(
        frozen_plan["generation"]["local"]["maximum_per_time_bin"]
    )
    local_center_dedup_rejected = 0
    local_time_bin_rejected = 0
    for _, visual_index, candidate in local_rows:
        center = _center(visual[visual_index])
        if any(
            abs(center - prior) < local_separation_us
            for prior in retained_centers
        ):
            local_center_dedup_rejected += 1
            continue
        time_bin = int(center // local_time_bin_us)
        if local_time_bin_counts[time_bin] >= local_bin_cap:
            local_time_bin_rejected += 1
            continue
        retained_local.append(candidate)
        retained_centers.append(center)
        local_time_bin_counts[time_bin] += 1
        if len(retained_local) >= int(
            frozen_plan["generation"]["local"][
                "maximum_retained_review_leads"
            ]
        ):
            break

    far_rows: list[tuple[float, int, int, str]] = []
    far_minimum_us = round(
        float(
            frozen_plan["generation"]["far"][
                "minimum_center_separation_seconds"
            ]
        )
        * 1_000_000
    )
    continuity_floor = float(
        frozen_plan["generation"]["far"]["minimum_visual_continuity"]
    )
    strong_continuity = float(
        frozen_plan["generation"]["far"]["strong_visual_continuity"]
    )
    shared_minimum = int(
        frozen_plan["generation"]["far"]["shared_salient_term_minimum"]
    )
    audio_continuity_floor = float(
        frozen_plan["generation"]["far"]["minimum_audio_continuity"]
    )
    far_separated_pairs = 0
    far_visual_continuity_pass = 0
    far_speech_at_both = 0
    far_speech_bridge_pass = 0
    far_audio_floor_at_both = 0
    far_audio_continuity_pass = 0
    for first_index, first in enumerate(visual):
        first = visual[first_index]
        first_speech = speech_by_visual[first_index]
        first_terms = (
            set(_speech_terms(first_speech, speech_index))
            if first_speech is not None
            else set()
        )
        first_identifier = str(first["segment_id"])
        for second_index in range(first_index + 1, len(visual)):
            second = visual[second_index]
            separation = abs(_center(second) - _center(first))
            if separation < far_minimum_us:
                continue
            far_separated_pairs += 1
            continuity = _cosine(
                visual_vectors[first_index], visual_vectors[second_index]
            )
            if continuity < continuity_floor:
                continue
            far_visual_continuity_pass += 1
            second_speech = speech_by_visual[second_index]
            shared_terms: set[str] = set()
            speech_bridge = False
            if first_speech is not None and second_speech is not None:
                far_speech_at_both += 1
                shared_terms = first_terms & set(
                    _speech_terms(second_speech, speech_index)
                )
                speech_bridge = bool(
                    len(shared_terms) >= shared_minimum
                    or continuity >= strong_continuity
                )
                if speech_bridge:
                    far_speech_bridge_pass += 1
            second_identifier = str(second["segment_id"])
            audio_pair_floor = bool(
                audio_states[first_identifier]["structural_floor_pass"]
                and audio_states[second_identifier]["structural_floor_pass"]
                and searchable_speech_tokens_by_visual[first_index]
                <= int(
                    frozen_plan["generation"]["audio"][
                        "maximum_overlapping_speech_tokens_for_independence"
                    ]
                )
                and searchable_speech_tokens_by_visual[second_index]
                <= int(
                    frozen_plan["generation"]["audio"][
                        "maximum_overlapping_speech_tokens_for_independence"
                    ]
                )
            )
            audio_continuity = -1.0
            audio_bridge = False
            if audio_pair_floor:
                far_audio_floor_at_both += 1
                audio_continuity = _cosine(
                    audio_vectors[first_identifier],
                    audio_vectors[second_identifier],
                )
                audio_bridge = audio_continuity >= audio_continuity_floor
                if audio_bridge:
                    far_audio_continuity_pass += 1
            route = (
                "speech"
                if speech_bridge
                else "visual_audio"
                if audio_bridge
                else ""
            )
            if not route:
                continue
            score = (
                0.55 * continuity
                + 0.3
                * max(transitions[first_index], transitions[second_index])
                + 0.05 * min(2, len(shared_terms))
                + 0.1 * min(1.0, separation / (600 * 1_000_000))
                + (0.05 * max(0.0, audio_continuity) if audio_bridge else 0.0)
            )
            far_rows.append((score, first_index, second_index, route))
    far_rows.sort(
        key=lambda item: (
            -item[0],
            int(visual[item[1]]["start_us"]),
            int(visual[item[2]]["start_us"]),
            item[3],
        )
    )
    retained_far: list[dict[str, Any]] = []
    far_used_endpoints: Counter[int] = Counter()
    far_bucket_counts: Counter[str] = Counter()
    far_first_time_bin_counts: Counter[int] = Counter()
    far_endpoint_reuse_rejected = 0
    far_bucket_rejected = 0
    far_time_bin_rejected = 0
    far_boundaries = list(
        frozen_plan["generation"]["far"]["separation_bucket_seconds"]
    )
    far_first_time_bin_us = round(
        float(
            frozen_plan["generation"]["far"][
                "first_component_time_bin_seconds"
            ]
        )
        * 1_000_000
    )
    for _, first_index, second_index, route in far_rows:
        endpoint_cap = int(
            frozen_plan["generation"]["far"]["maximum_endpoint_reuse"]
        )
        if (
            far_used_endpoints[first_index] >= endpoint_cap
            or far_used_endpoints[second_index] >= endpoint_cap
        ):
            far_endpoint_reuse_rejected += 1
            continue
        separation_seconds = abs(
            _center(visual[second_index]) - _center(visual[first_index])
        ) / 1_000_000.0
        separation_bucket = _separation_bucket(
            separation_seconds, far_boundaries
        )
        if far_bucket_counts[separation_bucket] >= int(
            frozen_plan["generation"]["far"][
                "maximum_per_separation_bucket"
            ]
        ):
            far_bucket_rejected += 1
            continue
        first_time_bin = int(
            _center(visual[first_index]) // far_first_time_bin_us
        )
        if far_first_time_bin_counts[first_time_bin] >= int(
            frozen_plan["generation"]["far"][
                "maximum_per_first_component_time_bin"
            ]
        ):
            far_time_bin_rejected += 1
            continue
        if route == "speech":
            candidate = _far_candidate(
                first_index=first_index,
                second_index=second_index,
                visual=visual,
                visual_vectors=visual_vectors,
                transition_scores=transitions,
                speech_documents=speech_documents,
                speech_index=speech_index,
                audio_by_id=audio_by_id,
                ordered_audio=ordered_audio,
                audio_vectors=audio_vectors,
                source_sha256=source_sha256,
                plan=frozen_plan,
                transition_threshold=minimum_transition,
            )
        else:
            candidate = _far_visual_audio_candidate(
                first_index=first_index,
                second_index=second_index,
                visual=visual,
                visual_vectors=visual_vectors,
                transition_scores=transitions,
                audio_by_id=audio_by_id,
                audio_vectors=audio_vectors,
                audio_novelties=audio_novelties,
                source_sha256=source_sha256,
                plan=frozen_plan,
            )
        retained_far.append(candidate)
        far_used_endpoints[first_index] += 1
        far_used_endpoints[second_index] += 1
        far_bucket_counts[separation_bucket] += 1
        far_first_time_bin_counts[first_time_bin] += 1
        if len(retained_far) >= int(
            frozen_plan["generation"]["far"][
                "maximum_retained_review_leads"
            ]
        ):
            break
    candidates = retained_local + retained_far
    candidates.sort(
        key=lambda item: (
            0 if item["machine_provisional_status"] == "KEEP" else 1
            if item["machine_provisional_status"] == "REPAIR"
            else 2,
            0 if item["candidate_kind"] == "coherent_far_multi_hop" else 1,
            item["evidence_handles"][0]["start_us"],
            item["candidate_id"],
        )
    )
    for rank, candidate in enumerate(candidates, 1):
        body = {
            key: value
            for key, value in candidate.items()
            if key != "candidate_payload_sha256"
        }
        body["rank"] = rank
        candidate.clear()
        candidate.update(_candidate_hash(body))
    prescreen_gate = _apply_prescreen(candidates, prescreen)
    audio_novelty_values = list(audio_novelties.values())
    audio_novelty_pass = sum(
        state["novelty_pass"] for state in audio_states.values()
    )
    audio_rms_pass = sum(
        state["rms_pass"] for state in audio_states.values()
    )
    audio_silence_pass = sum(
        state["not_near_silence"] for state in audio_states.values()
    )
    audio_structural_pass = sum(
        state["structural_floor_pass"] for state in audio_states.values()
    )
    audio_sparse_speech_pass = sum(
        state["structural_floor_pass"]
        and searchable_speech_tokens_by_visual[index]
        <= int(
            frozen_plan["generation"]["audio"][
                "maximum_overlapping_speech_tokens_for_independence"
            ]
        )
        for index, state in enumerate(audio_states.values())
    )
    filter_flow = {
        "local": [
            {"gate": "searchable_fine_visual", "count": len(visual)},
            {
                "gate": "calibrated_visual_transition",
                "count": local_transition_pass,
            },
            {
                "gate": "calibrated_transition_with_quality_gated_speech",
                "count": local_transition_with_speech,
            },
            {
                "gate": "speech_quality_floor",
                "count": local_speech_quality_pass,
            },
            {
                "gate": "calibrated_transition_with_audio_structural_floor",
                "count": local_transition_with_audio_structure,
            },
            {
                "gate": "speech_free_v+a_sparse_searchable_speech",
                "count": local_va_sparse_speech_pass,
            },
            {"gate": "raw_local_rows", "count": len(local_rows)},
            {
                "gate": "retained_after_dedup_diversity_and_cap",
                "count": len(retained_local),
            },
        ],
        "far_all_fine_pairs": [
            {
                "gate": "pairs_at_minimum_separation",
                "count": far_separated_pairs,
            },
            {
                "gate": "visual_continuity_floor",
                "count": far_visual_continuity_pass,
            },
            {
                "gate": "quality_gated_speech_at_both_components",
                "count": far_speech_at_both,
            },
            {
                "gate": "speech_lexical_or_strong_visual_bridge",
                "count": far_speech_bridge_pass,
            },
            {
                "gate": "audio_structural_floor_at_both_components",
                "count": far_audio_floor_at_both,
            },
            {
                "gate": "audio_continuity_floor",
                "count": far_audio_continuity_pass,
            },
            {"gate": "raw_far_rows", "count": len(far_rows)},
            {
                "gate": "retained_after_diversity_and_cap",
                "count": len(retained_far),
            },
        ],
    }
    profile_counts: dict[str, dict[str, Any]] = {}
    for profile in ("V+A", "V+S", "V+S+A"):
        members = [
            item
            for item in candidates
            if item["profile_hypothesis"] == profile
        ]
        profile_counts[profile] = {
            "keep": sum(
                item["machine_provisional_status"] == "KEEP"
                for item in members
            ),
            "repair": sum(
                item["machine_provisional_status"] == "REPAIR"
                for item in members
            ),
            "reject": sum(
                item["machine_provisional_status"] == "REJECT"
                for item in members
            ),
            "machine_lead_count": len(members),
            "validated_or_accepted": 0,
            "honest_zero": not members,
            "zero_reason": (
                "No retained structural route has exactly the V+A profile; "
                "inventory-only ASR was not promoted and source-level modality "
                "absence is not inferred."
                if profile == "V+A" and not members
                else (
                    "No retained route has actual quality-gated speech with the "
                    "V+S profile; inventory-only ASR was not promoted and "
                    "source-level speech absence is not inferred."
                    if profile == "V+S" and not members
                    else (
                        "No retained route combines actual quality-gated speech "
                        "with an audio window clearing novelty, RMS, near-silence, "
                        "and sparse-speech floors; source-level absence is not "
                        "inferred."
                        if profile == "V+S+A" and not members
                        else None
                    )
                )
            ),
        }
    far_members = [
        item
        for item in candidates
        if item["candidate_kind"] == "coherent_far_multi_hop"
    ]
    profile_counts["coherent_far_multi_hop"] = {
        "keep": sum(
            item["machine_provisional_status"] == "KEEP"
            for item in far_members
        ),
        "repair": sum(
            item["machine_provisional_status"] == "REPAIR"
            for item in far_members
        ),
        "reject": sum(
            item["machine_provisional_status"] == "REJECT"
            for item in far_members
        ),
        "machine_lead_count": len(far_members),
        "validated_or_accepted": 0,
        "honest_zero": not far_members,
        "zero_reason": (
            "No all-fine-window pair survives separation, visual continuity, "
            "a quality-gated speech bridge or V+A structural bridge, and the "
            "deterministic diversity cap; source-level absence is not inferred."
            if not far_members
            else None
        ),
    }
    registry: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "registry_id": "AV-TRACE-EPIC-P23-102-FAMILY-MINING-V1-DEV",
        "created_date": "2026-10-14",
        "decision": MINE_COMPLETE,
        "repair_completion_token": REPAIR_READY,
        "artifact_classification": (
            "DEVELOPMENT_ONLY_MACHINE_EXPERT_PROVISIONAL"
        ),
        "source_id": "P23_102",
        "source_group_id": "P23",
        "source_sha256": source_sha256,
        "plan_payload_sha256": frozen_plan["plan_payload_sha256"],
        "input_bindings": copy.deepcopy(
            list(bundle.get("input_bindings", []))
        ),
        "index_bindings": {
            "index_hash": index.get("index_hash"),
            "segment_manifest_hash": bundle.get(
                "segment_manifest", {}
            ).get("segment_manifest_hash"),
            "observation_manifest_hash": bundle.get(
                "observation_manifest", {}
            ).get("observation_manifest_hash"),
            "build_manifest_hash": bundle.get("build_manifest", {}).get(
                "build_manifest_hash"
            ),
        },
        "mining_boundary": {
            "semantic_annotations_accessed": False,
            "human_prescreen_used_during_generation_or_ranking": False,
            "raw_media_decoded": False,
            "models_loaded": False,
            "network_used": False,
            "quota_forcing_used": False,
            "candidate_caps_are_review_bounds_not_fill_targets": True,
        },
        "summary": {
            "candidate_count": len(candidates),
            "keep_count": sum(
                item["machine_provisional_status"] == "KEEP"
                for item in candidates
            ),
            "repair_count": sum(
                item["machine_provisional_status"] == "REPAIR"
                for item in candidates
            ),
            "reject_count": sum(
                item["machine_provisional_status"] == "REJECT"
                for item in candidates
            ),
            "accepted_family_count": 0,
            "accepted_ses_count": 0,
            "h_tier_count": 0,
            "gate_a_credit_count": 0,
        },
        "calibration_diagnostics": {
            "visual_transition": transition_calibration,
            "audio": {
                "novelty_definition": (
                    "max(1-cosine(previous,current),"
                    "1-cosine(current,next)) over ordered aligned fine audio"
                ),
                "novelty_distribution": _distribution_summary(
                    audio_novelty_values
                ),
                "minimum_audio_novelty": float(
                    frozen_plan["generation"]["audio"][
                        "minimum_audio_novelty"
                    ]
                ),
                "minimum_rms_full_scale": float(
                    frozen_plan["generation"]["audio"][
                        "minimum_rms_full_scale"
                    ]
                ),
                "novelty_pass_count": audio_novelty_pass,
                "rms_pass_count": audio_rms_pass,
                "not_near_silence_count": audio_silence_pass,
                "novelty_rms_and_silence_pass_count": audio_structural_pass,
                "structural_and_sparse_searchable_speech_pass_count": (
                    audio_sparse_speech_pass
                ),
            },
            "speech": {
                "indexed_chunks_total": len(all_speech_documents),
                "quality_gate_pass_count": sum(
                    bool(item.get("quality_gate_pass"))
                    for item in all_speech_documents
                ),
                "searchable_chunks": len(speech_documents),
                "inventory_only_chunks": sum(
                    item.get("routing") == "inventory_only"
                    or not item.get("searchable")
                    for item in all_speech_documents
                ),
                "inventory_only_promoted_to_searchable": 0,
            },
        },
        "filter_flow_counts": filter_flow,
        "diversity_accounting": {
            "local_center_dedup_rejected": local_center_dedup_rejected,
            "local_time_bin_rejected": local_time_bin_rejected,
            "far_endpoint_reuse_rejected": far_endpoint_reuse_rejected,
            "far_separation_bucket_rejected": far_bucket_rejected,
            "far_first_component_time_bin_rejected": far_time_bin_rejected,
            "local_cap": int(
                frozen_plan["generation"]["local"][
                    "maximum_retained_review_leads"
                ]
            ),
            "far_cap": int(
                frozen_plan["generation"]["far"][
                    "maximum_retained_review_leads"
                ]
            ),
        },
        "profile_accounting": profile_counts,
        "independent_work_accounting": {
            "speech": {
                "quality_gated_searchable_chunks": len(speech_documents),
                "machine_leads_with_speech_handles": sum(
                    any(
                        handle["modality"] == "speech"
                        for handle in item["evidence_handles"]
                    )
                    for item in candidates
                ),
                "inventory_only_chunks_not_promoted": sum(
                    item.get("routing") == "inventory_only"
                    or not item.get("searchable")
                    for item in all_speech_documents
                ),
                "honest_zero": not any(
                    any(
                        handle["modality"] == "speech"
                        for handle in item["evidence_handles"]
                    )
                    for item in candidates
                ),
                "reason": (
                    "No emitted lead contains actual quality-gated speech; "
                    "inventory-only ASR remains non-searchable and no "
                    "source-level absence claim is made."
                    if not any(
                        any(
                            handle["modality"] == "speech"
                            for handle in item["evidence_handles"]
                        )
                        for item in candidates
                    )
                    else None
                ),
            },
            "ambient_non_speech": {
                "machine_leads_clearing_structural_independence_floors": sum(
                    item["profile_hypothesis"] in {"V+A", "V+S+A"}
                    for item in candidates
                ),
                "eligible_fine_windows": audio_sparse_speech_pass,
                "honest_zero": not any(
                    item["profile_hypothesis"] in {"V+A", "V+S+A"}
                    for item in candidates
                ),
                "reason": (
                    "No emitted lead retains an audio structural hypothesis; "
                    "window-level floor counts are reported separately and no "
                    "answer-bearing or source-level absence claim is made."
                    if not any(
                        item["profile_hypothesis"] in {"V+A", "V+S+A"}
                        for item in candidates
                    )
                    else None
                ),
            },
        },
        "source_uniform_human_prescreen_gate": prescreen_gate,
        "acceptance_boundary": {
            "accepted_families": [],
            "accepted_ses": [],
            "h_tiers": [],
            "gate_a_asserted": False,
            "future_test_eligible": False,
            "required_before_any_future_acceptance": (
                "A separately authorized source-uniform human prescreen followed "
                "by a separately implemented acceptance protocol."
            ),
        },
        "resource_report": {
            "fine_visual_windows_read": len(visual),
            "speech_chunks_indexed": len(all_speech_documents),
            "speech_chunks_searchable": len(speech_documents),
            "fine_audio_windows_read": len(ordered_audio),
            "local_structural_routes_above_floor": len(local_rows),
            "far_structural_routes_above_floor": len(far_rows),
            "far_pairs_evaluated": far_separated_pairs,
            "media_decode_passes": 0,
            "model_inference_runs": 0,
            "network_requests": 0,
        },
        "candidates": candidates,
    }
    _seal(registry, "registry_payload_sha256")
    validate_registry(registry, bundle=bundle)
    return registry


def validate_registry(
    registry: Mapping[str, Any],
    *,
    bundle: Mapping[str, Any] | None = None,
) -> None:
    """Validate hashes, exact handles, far coherence, and fail-closed claims."""
    if registry.get("decision") != MINE_COMPLETE:
        raise MiningError("REGISTRY_DECISION_INVALID")
    if registry.get("repair_completion_token") != REPAIR_READY:
        raise MiningError("REGISTRY_REPAIR_TOKEN_INVALID")
    _verify_self_hash(registry, "registry_payload_sha256")
    boundary = registry.get("acceptance_boundary", {})
    summary = registry.get("summary", {})
    calibration = registry.get("calibration_diagnostics", {})
    visual_calibration = calibration.get("visual_transition", {})
    speech_calibration = calibration.get("speech", {})
    filter_flow = registry.get("filter_flow_counts", {})
    if (
        visual_calibration.get("semantic_labels_used") is not False
        or float(visual_calibration.get("selected_threshold", -1.0))
        < float(visual_calibration.get("minimum_absolute_effect", 0.0))
        or speech_calibration.get("inventory_only_promoted_to_searchable")
        != 0
        or not isinstance(filter_flow.get("local"), list)
        or not isinstance(filter_flow.get("far_all_fine_pairs"), list)
    ):
        raise MiningError("CALIBRATION_OR_FILTER_FLOW_INVALID")
    if (
        summary.get("accepted_family_count") != 0
        or summary.get("accepted_ses_count") != 0
        or summary.get("h_tier_count") != 0
        or summary.get("gate_a_credit_count") != 0
        or boundary.get("accepted_families") != []
        or boundary.get("accepted_ses") != []
        or boundary.get("h_tiers") != []
        or boundary.get("gate_a_asserted") is not False
        or boundary.get("future_test_eligible") is not False
    ):
        raise MiningError("DEVELOPMENT_ACCEPTANCE_BOUNDARY_VIOLATION")
    candidates = registry.get("candidates")
    if not isinstance(candidates, list):
        raise MiningError("CANDIDATES_NOT_LIST")
    if [item.get("rank") for item in candidates] != list(
        range(1, len(candidates) + 1)
    ):
        raise MiningError("CANDIDATE_RANKS_INVALID")
    known: dict[str, dict[str, Mapping[str, Any]]] = {
        "vision": {},
        "speech": {},
        "ambient_audio": {},
    }
    if bundle is not None:
        modalities = bundle["index"]["modalities"]
        known["vision"] = {
            str(item["segment_id"]): item
            for item in modalities["siglip2_visual"]["documents"]
        }
        known["speech"] = {
            str(item["chunk_id"]): item
            for item in modalities["speech"]["documents"]
        }
        known["ambient_audio"] = {
            str(item["segment_id"]): item
            for item in modalities["clap_audio"]["documents"]
        }
    for candidate in candidates:
        _verify_self_hash(candidate, "candidate_payload_sha256")
        if candidate.get("machine_provisional_status") not in PROVISIONAL_STATUSES:
            raise MiningError("INVALID_MACHINE_PROVISIONAL_STATUS")
        if candidate.get("profile_hypothesis") not in PROFILE_LABELS:
            raise MiningError("INVALID_PROFILE_HYPOTHESIS")
        if (
            candidate.get("accepted_family") is not False
            or candidate.get("accepted_ses") is not False
            or candidate.get("h_tier") is not None
            or candidate.get("gate_a_credit") is not False
        ):
            raise MiningError("CANDIDATE_CLAIMS_ACCEPTANCE_OR_TIER")
        if not candidate.get("atomic_claim_templates"):
            raise MiningError("MISSING_ATOMIC_CLAIM_TEMPLATES")
        seen_modalities = set()
        for handle in candidate.get("evidence_handles", []):
            modality = str(handle.get("modality"))
            seen_modalities.add(modality)
            start = handle.get("start_us")
            end = handle.get("end_us")
            if (
                not isinstance(start, int)
                or not isinstance(end, int)
                or start < 0
                or end <= start
            ):
                raise MiningError("INVALID_EVIDENCE_TIMESTAMP")
            if bundle is not None:
                record = known.get(modality, {}).get(str(handle["record_id"]))
                if record is None:
                    raise MiningError("UNKNOWN_EXACT_EVIDENCE_HANDLE")
                if (
                    int(record["start_us"]) != start
                    or int(record["end_us"]) != end
                ):
                    raise MiningError("EVIDENCE_TIMESTAMP_BINDING_MISMATCH")
        required = {"vision"}
        if candidate["profile_hypothesis"] in {"V+S", "V+S+A"}:
            required.add("speech")
        if candidate["profile_hypothesis"] in {"V+A", "V+S+A"}:
            required.add("ambient_audio")
        if not required.issubset(seen_modalities):
            raise MiningError("PROFILE_LACKS_REQUIRED_EXACT_HANDLES")
        if (
            candidate["profile_hypothesis"] == "V+A"
            and "speech" in seen_modalities
        ):
            raise MiningError("V+A_MUST_NOT_USE_SPEECH_HANDLE")
        temporal = candidate["temporal_structure"]
        if candidate["candidate_kind"] == "coherent_far_multi_hop":
            coherence = temporal.get("far_coherence")
            if (
                temporal.get("hop_hypothesis") != "multi_hop"
                or temporal.get("temporal_hypothesis") != "far_separated"
                or float(
                    temporal.get("evidence_center_separation_seconds", 0.0)
                )
                < 120.0
                or not isinstance(coherence, Mapping)
                or coherence.get("distance_alone_is_not_credited") is not True
                or not coherence.get("coherence_hypothesis")
            ):
                raise MiningError("INVALID_FAR_COHERENCE")
        elif (
            temporal.get("hop_hypothesis") != "one_hop"
            or temporal.get("temporal_hypothesis") != "near_local"
        ):
            raise MiningError("ONE_HOP_MUST_BE_NEAR_LOCAL")
        firewall = candidate.get("semantic_annotation_firewall", {})
        if (
            firewall.get("epic_semantic_labels_accessed") is not False
            or firewall.get("human_labels_used_for_generation_or_ranking")
            is not False
        ):
            raise MiningError("SEMANTIC_ANNOTATION_FIREWALL_VIOLATION")
    accounting = registry.get("profile_accounting", {})
    for profile in ("V+A", "V+S", "V+S+A", "coherent_far_multi_hop"):
        row = accounting.get(profile, {})
        members = (
            [
                item
                for item in candidates
                if item["candidate_kind"] == "coherent_far_multi_hop"
            ]
            if profile == "coherent_far_multi_hop"
            else [
                item
                for item in candidates
                if item["profile_hypothesis"] == profile
            ]
        )
        if row.get("machine_lead_count") != len(members):
            raise MiningError("PROFILE_ACCOUNTING_MISMATCH")
        if row.get("validated_or_accepted") != 0:
            raise MiningError("PROFILE_CLAIMS_VALIDATION")
        if not members and (
            row.get("honest_zero") is not True or not row.get("zero_reason")
        ):
            raise MiningError("MISSING_HONEST_ZERO")


def build_synthetic_bundle(
    *,
    speech_present: bool = True,
    independent_audio_present: bool = True,
) -> dict[str, Any]:
    """Create a deterministic in-memory fixture; no semantic labels are used."""

    def encoded(values: Sequence[float]) -> str:
        array = np.asarray(values, dtype=np.float32)
        array /= np.linalg.norm(array)
        return array.astype("<f2").tobytes().hex()

    windows = [
        ("seg.fixture.fine.000", 0, [1.0, 0.0, 0.0, 0.0]),
        ("seg.fixture.fine.001", 8, [0.0, 1.0, 0.0, 0.0]),
        ("seg.fixture.fine.002", 24, [0.0, 0.95, 0.05, 0.0]),
        ("seg.fixture.fine.003", 152, [1.0, 0.0, 0.0, 0.0]),
        ("seg.fixture.fine.004", 160, [0.0, 0.98, 0.02, 0.0]),
        ("seg.fixture.fine.005", 184, [0.0, 0.0, 1.0, 0.0]),
    ]
    visual = [
        {
            "segment_id": identifier,
            "source_ref": "P23_102",
            "scale": "fine",
            "start_us": start * 1_000_000,
            "end_us": (start + 8) * 1_000_000,
            "dimension": 4,
            "vector_f16_hex": encoded(vector),
            "l2_normalized": True,
            "searchable": True,
        }
        for identifier, start, vector in windows
    ]
    audio_vectors = [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0]
        if independent_audio_present
        else [1.0, 0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0]
        if independent_audio_present
        else [1.0, 0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0, 0.0],
    ]
    audio = [
        {
            "segment_id": row[0],
            "source_ref": "P23_102",
            "scale": "fine",
            "start_us": row[1] * 1_000_000,
            "end_us": (row[1] + 8) * 1_000_000,
            "dimension": 4,
            "vector_f16_hex": encoded(audio_vectors[index]),
            "l2_normalized": True,
            "searchable": True,
            "audio_rms_full_scale": (
                0.08 if independent_audio_present and index in {1, 4} else 0.02
            ),
            "quality_flags": [],
        }
        for index, row in enumerate(windows)
    ]
    speech_texts = [
        ("speech.fixture.000", 0, 30, ["container", "changes", "result"]),
        (
            "speech.fixture.001",
            150,
            180,
            ["container", "later", "result"],
        ),
        ("speech.fixture.002", 180, 210, ["different", "topic", "words"]),
    ]
    speech = []
    if speech_present:
        for identifier, start, end, tokens in speech_texts:
            frequencies = dict(sorted(Counter(tokens).items()))
            speech.append(
                {
                    "chunk_id": identifier,
                    "source_ref": "P23_102",
                    "start_us": start * 1_000_000,
                    "end_us": end * 1_000_000,
                    "text": " ".join(tokens),
                    "searchable": True,
                    "quality_gate_pass": True,
                    "term_frequency": frequencies,
                    "document_length": len(tokens),
                }
            )
    document_frequency: Counter[str] = Counter()
    for item in speech:
        document_frequency.update(item["term_frequency"].keys())
    index_body: dict[str, Any] = {
        "schema_version": "fixture",
        "index_version": "fixture",
        "stage": "RESTRICTED_DEVELOPMENT_ONLY_SOURCE_DERIVED_INDEX",
        "source_ref": "P23_102",
        "modalities": {
            "speech": {
                "ranker": "bm25-okapi/1.0",
                "documents": speech,
                "document_frequency": dict(sorted(document_frequency.items())),
                "average_document_length": (
                    sum(item["document_length"] for item in speech) / len(speech)
                    if speech
                    else 0.0
                ),
            },
            "siglip2_visual": {
                "ranker": "fixture",
                "documents": visual,
            },
            "clap_audio": {
                "ranker": "fixture",
                "documents": audio,
            },
        },
        "governance": {
            "semantic_annotations_used_during_source_selection": False,
            "human_review_performed": False,
            "h_tier_assigned": False,
        },
    }
    _seal(index_body, "index_hash")
    segment = _seal(
        {
            "source_ref": "P23_102",
            "duration_us": 210_000_000,
            "segments": [],
        },
        "segment_manifest_hash",
    )
    observation = _seal(
        {"counts": {}, "fixture": True}, "observation_manifest_hash"
    )
    build = _seal(
        {
            "source_ref": "P23_102",
            "source_sha256": "f" * 64,
            "status": "COMPLETE",
            "decision": "EPIC_P23_102_FULL_TIMELINE_PIPELINE_READY",
            "smoke_seconds": None,
            "terminal_boundary": {
                "index_only": True,
                "families_generated": False,
                "human_or_ses_or_h_or_gate_claim_generated": False,
            },
        },
        "build_manifest_hash",
    )
    return {
        "index": index_body,
        "segment_manifest": segment,
        "observation_manifest": observation,
        "resource_manifest": {
            "source": {"media_sha256": "f" * 64}
        },
        "checkpoint_manifest": {},
        "build_manifest": build,
        "input_bindings": [
            {
                "path": "synthetic://epic-p23-102-full-timeline",
                "sha256": object_hash(index_body),
            }
        ],
    }


def _load_plan(root: Path, value: str | Path) -> dict[str, Any]:
    path = _safe_path(root, value, label="PLAN")
    if not path.is_file():
        raise MiningError(f"PLAN_MISSING:{value}")
    committed = _load_json(path)
    generated = build_plan()
    if canonical_bytes(committed) != canonical_bytes(generated):
        raise MiningError("COMMITTED_PLAN_DRIFT")
    return committed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(repo_root_default()))
    parser.add_argument("--plan", default=str(PLAN_RELATIVE_PATH))
    parser.add_argument(
        "--mode", choices=("plan", "mine", "check"), default="plan"
    )
    parser.add_argument("--index-root", default=str(INDEX_RELATIVE_ROOT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--registry")
    parser.add_argument("--prescreen")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.repo_root).resolve()
    try:
        plan = _load_plan(root, args.plan)
        if args.mode == "plan":
            print(
                json.dumps(
                    {
                        "decision": PIPELINE_READY,
                        "status": "PLANNED_FUTURE_INDEX_MAY_BE_ABSENT",
                        "plan": str(args.plan),
                        "index_read": False,
                        "output_written": False,
                        "resource_estimate": plan["resource_estimate"],
                        "post_index_commands": plan["post_index_commands"],
                    },
                    sort_keys=True,
                )
            )
            return 0
        if args.mode == "mine":
            bundle = load_index_bundle(root, index_root=args.index_root)
            prescreen = None
            if args.prescreen:
                prescreen = _load_json(
                    _safe_path(root, args.prescreen, label="PRESCREEN")
                )
            registry = mine_bundle(
                bundle, prescreen=prescreen, plan=plan
            )
            output = _safe_path(root, args.output, label="OUTPUT")
            allowed = (root / DEFAULT_OUTPUT.parent).resolve(strict=False)
            try:
                output.resolve(strict=False).relative_to(allowed)
            except ValueError as exc:
                raise MiningError(
                    "OUTPUT_MUST_BE_UNDER_DEVELOPMENT_ONLY_ROOT"
                ) from exc
            _write_json(output, registry)
            print(MINE_COMPLETE)
            return 0
        registry_path = _safe_path(
            root, args.registry or args.output, label="REGISTRY"
        )
        registry = _load_json(registry_path)
        bundle = load_index_bundle(root, index_root=args.index_root)
        validate_registry(registry, bundle=bundle)
        print(REPAIR_READY)
        return 0
    except (MiningError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"{REPAIR}: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
