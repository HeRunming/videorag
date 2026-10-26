#!/usr/bin/env python3
"""Deterministic learned-retrieval diagnostic for P23_102.

This development-only tool reads the verified P23 full-timeline index and the
repaired machine-provisional family bundle.  It never opens media, semantic
annotations, human labels, answer keys, generation models, or agent traces.
Only exact machine-authored templates already present in the provisional
registry are embedded with the frozen local SigLIP/CLAP text encoders.
"""

from __future__ import annotations

import argparse
import gc
import gzip
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import resource
import statistics
import tempfile
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np

READY = "P23_102_REAL_RETRIEVAL_DIAGNOSTIC_READY"
REPAIR = "P23_102_REAL_RETRIEVAL_DIAGNOSTIC_REPAIR"
CREATED_DATE = "2026-10-15"
SCHEMA_VERSION = "av-trace.p23-102-real-retrieval-diagnostic/1.0"
SOURCE_ID = "P23_102"
SOURCE_GROUP_ID = "P23"
RRF_K = 60
TOP_KS = (1, 5, 10)
RANDOM_SEED = "p23_102_real_retrieval_diagnostic_v1"

INDEX_ROOT = Path("data/restricted/epic_p23_102_full_timeline_index_v1")
BUNDLE_ROOT = Path(
    "data/restricted/epic_p23_102_machine_provisional_families_v1"
)
MODEL_MANIFEST_PATH = Path(
    "data/restricted/scale1b/manifests/wave_r_model_acquisition.json"
)
OUTPUT_ROOT = Path(
    "data/restricted/p23_102_real_retrieval_diagnostic_v1"
)
PUBLIC_SUMMARY_PATH = Path(
    "data/rehearsal_plan/p23_102_real_retrieval_diagnostic_v1.json"
)

INPUT_PATHS = {
    "index": INDEX_ROOT / "full_timeline_index.json",
    "index_build": INDEX_ROOT / "build_manifest.json",
    "index_resource": INDEX_ROOT / "resource_manifest.json",
    "index_segments": INDEX_ROOT / "segment_manifest.json",
    "family_registry": BUNDLE_ROOT / "family_registry.json",
    "evidence_registry": BUNDLE_ROOT / "evidence_registry.json",
    "source_split": BUNDLE_ROOT / "source_split_manifest.json",
    "bundle_leakage": BUNDLE_ROOT / "leakage_gate.json",
    "model_manifest": MODEL_MANIFEST_PATH,
}

CORE_OUTPUT_NAMES = (
    "config.json",
    "queries.json",
    "rankings.jsonl.gz",
    "per_query_metrics.json",
    "metric_tables.json",
    "leakage_audit.json",
)

TOKEN_RE = re.compile(r"[a-z0-9]+")


class DiagnosticError(RuntimeError):
    """Fail-closed diagnostic or validation error."""


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


def compact_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def object_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def bytes_hash(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(16 * 1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def seal(document: dict[str, Any], field: str = "payload_sha256") -> dict[str, Any]:
    document[field] = object_hash(document)
    return document


def verify_seal(
    document: Mapping[str, Any], field: str, *, label: str
) -> None:
    payload = {key: value for key, value in document.items() if key != field}
    if document.get(field) != object_hash(payload):
        raise DiagnosticError(f"{label}_HASH_MISMATCH")


def _safe_path(root: Path, value: str | Path, *, label: str) -> Path:
    raw = Path(value)
    if raw.is_absolute():
        path = raw
    else:
        pure = PurePosixPath(str(raw))
        if ".." in pure.parts or ".staging" in pure.parts:
            raise DiagnosticError(f"{label}_UNSAFE:{value}")
        path = root.joinpath(*pure.parts)
    try:
        path.resolve(strict=False).relative_to(root.resolve())
    except ValueError as exc:
        raise DiagnosticError(f"{label}_OUTSIDE_REPOSITORY:{value}") from exc
    if path.is_symlink() or ".staging" in path.parts:
        raise DiagnosticError(f"{label}_UNSAFE:{value}")
    return path


def _relative(root: Path, path: Path) -> str:
    return path.resolve(strict=False).relative_to(root.resolve()).as_posix()


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _atomic_write(path: Path, payload: bytes, *, restricted: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700 if restricted else 0o755)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600 if restricted else 0o644)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        path.chmod(0o600 if restricted else 0o644)
    finally:
        temporary.unlink(missing_ok=True)


def _write_json(path: Path, value: Any, *, restricted: bool = True) -> None:
    _atomic_write(path, canonical_bytes(value), restricted=restricted)


def _gzip_jsonl(rows: Sequence[Mapping[str, Any]]) -> bytes:
    raw = b"".join(compact_bytes(row) + b"\n" for row in rows)
    return gzip.compress(raw, compresslevel=9, mtime=0)


def _tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def _normalize(values: np.ndarray) -> np.ndarray:
    matrix = np.asarray(values, dtype=np.float32)
    if matrix.ndim == 1:
        matrix = matrix[None, :]
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    if not np.isfinite(matrix).all() or np.any(norms <= 0):
        raise DiagnosticError("NONFINITE_OR_ZERO_VECTOR")
    return matrix / norms


def _decode_vectors(
    documents: Sequence[Mapping[str, Any]],
) -> tuple[list[str], np.ndarray, list[dict[str, Any]]]:
    ordered = sorted(documents, key=lambda row: str(row["segment_id"]))
    identifiers = [str(row["segment_id"]) for row in ordered]
    vectors = []
    for row in ordered:
        vector = np.frombuffer(
            bytes.fromhex(str(row["vector_f16_hex"])), dtype="<f2"
        ).astype(np.float32)
        if len(vector) != int(row["dimension"]):
            raise DiagnosticError("INDEX_VECTOR_DIMENSION_MISMATCH")
        vectors.append(vector)
    return identifiers, _normalize(np.stack(vectors)), [dict(row) for row in ordered]


def _stable_query_id(kind: str, family_id: str, target: str, text: str) -> str:
    payload = f"{kind}\x1f{family_id}\x1f{target}\x1f{text}".encode()
    return "p23q." + hashlib.sha256(payload).hexdigest()[:24]


def _claim_for_evidence(
    family: Mapping[str, Any], evidence: Mapping[str, Any]
) -> Mapping[str, Any]:
    claims = {
        str(item["claim_id"]): item
        for item in family["atomic_claim_templates"]
    }
    role = str(evidence["retrieval_role"])
    if role == "local_state_transition_hypothesis":
        claim_id = "c1"
    elif role == "local_non_speech_structure_hypothesis":
        claim_id = "c2"
    elif "component_1_state_or_object" in role:
        claim_id = "c1"
    elif "component_2_state_or_object" in role:
        claim_id = "c2"
    elif "non_speech" in role:
        claim_id = "c3"
    else:
        raise DiagnosticError(f"UNMAPPED_EVIDENCE_ROLE:{role}")
    if claim_id not in claims:
        raise DiagnosticError(f"CLAIM_MISSING:{family['family_id']}:{claim_id}")
    return claims[claim_id]


def build_queries(
    families: Sequence[Mapping[str, Any]],
    evidence_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Build exact-template handle and family queries without added prose."""
    evidence_by_family: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in evidence_rows:
        evidence_by_family[str(row["family_id"])].append(row)
    queries: list[dict[str, Any]] = []
    for family in sorted(families, key=lambda row: int(row["rank"])):
        family_id = str(family["family_id"])
        family_evidence = sorted(
            evidence_by_family[family_id],
            key=lambda row: str(row["evidence_handle_id"]),
        )
        fragments = [
            str(family["question_template"]),
            str(family["answer_template"]),
            *[
                str(item["template"])
                for item in family["atomic_claim_templates"]
            ],
        ]
        family_text = "\n".join(fragments)
        target_handles = [
            {
                "evidence_handle_id": str(row["evidence_handle_id"]),
                "modality": str(row["modality"]),
                "record_id": str(row["record_id"]),
            }
            for row in family_evidence
        ]
        queries.append(
            {
                "query_id": _stable_query_id(
                    "family", family_id, family_id, family_text
                ),
                "query_scope": "family",
                "family_id": family_id,
                "source_candidate_id": family["source_candidate_id"],
                "temporal_stratum": family["temporal_structure"][
                    "temporal_hypothesis"
                ],
                "query_text": family_text,
                "source_template_fields": [
                    "question_template",
                    "answer_template",
                    "atomic_claim_templates[*].template",
                ],
                "target_handles": target_handles,
                "machine_provisional_only": True,
            }
        )
        for evidence in family_evidence:
            claim = _claim_for_evidence(family, evidence)
            text = str(claim["template"])
            handle_id = str(evidence["evidence_handle_id"])
            queries.append(
                {
                    "query_id": _stable_query_id(
                        "handle", family_id, handle_id, text
                    ),
                    "query_scope": "handle",
                    "family_id": family_id,
                    "source_candidate_id": family["source_candidate_id"],
                    "temporal_stratum": family["temporal_structure"][
                        "temporal_hypothesis"
                    ],
                    "query_text": text,
                    "source_template_fields": [
                        f"atomic_claim_templates[{claim['claim_id']}].template"
                    ],
                    "target_handles": [
                        {
                            "evidence_handle_id": handle_id,
                            "modality": str(evidence["modality"]),
                            "record_id": str(evidence["record_id"]),
                        }
                    ],
                    "machine_provisional_only": True,
                }
            )
    return sorted(
        queries,
        key=lambda row: (
            int(
                next(
                    family["rank"]
                    for family in families
                    if family["family_id"] == row["family_id"]
                )
            ),
            0 if row["query_scope"] == "family" else 1,
            row["query_id"],
        ),
    )


def _verify_model_snapshot(
    root: Path, entry: Mapping[str, Any], *, label: str
) -> dict[str, Any]:
    snapshot = _safe_path(
        root, str(entry["snapshot_dir"]), label=f"{label}_SNAPSHOT"
    )
    if not snapshot.is_dir():
        raise DiagnosticError(f"{label}_SNAPSHOT_MISSING")
    inventory = []
    for item in entry["files"]:
        path = snapshot / str(item["path"])
        if not path.is_file() or path.is_symlink():
            raise DiagnosticError(f"{label}_MODEL_FILE_MISSING:{item['path']}")
        if path.stat().st_size != int(item["bytes"]):
            raise DiagnosticError(f"{label}_MODEL_FILE_SIZE:{item['path']}")
        actual = file_hash(path).removeprefix("sha256:")
        if actual != str(item["sha256"]):
            raise DiagnosticError(f"{label}_MODEL_FILE_HASH:{item['path']}")
        inventory.append(
            {
                "path": str(item["path"]),
                "bytes": int(item["bytes"]),
                "sha256": f"sha256:{actual}",
            }
        )
    return {
        "model_id": entry["repo_id"],
        "revision": entry["revision"],
        "snapshot_path": _relative(root, snapshot),
        "inventory_sha256": object_hash(inventory),
        "files": inventory,
    }


def load_inputs(root: Path, *, verify_model_files: bool = True) -> dict[str, Any]:
    paths = {
        key: _safe_path(root, value, label=key.upper())
        for key, value in INPUT_PATHS.items()
    }
    for key, path in paths.items():
        if not path.is_file():
            raise DiagnosticError(f"INPUT_MISSING:{key}:{_relative(root, path)}")
    inputs = {key: _load_json(path) for key, path in paths.items()}
    inputs["input_file_hashes"] = {
        _relative(root, path): file_hash(path)
        for path in paths.values()
    }
    validate_inputs(inputs)
    manifest = inputs["model_manifest"]
    if verify_model_files:
        inputs["verified_models"] = {
            key: _verify_model_snapshot(
                root, manifest["models"][key], label=key.upper()
            )
            for key in ("siglip2", "clap")
        }
    else:
        inputs["verified_models"] = {
            key: {
                "model_id": manifest["models"][key]["repo_id"],
                "revision": manifest["models"][key]["revision"],
                "snapshot_path": manifest["models"][key]["snapshot_dir"],
                "inventory_sha256": object_hash(
                    manifest["models"][key]["files"]
                ),
            }
            for key in ("siglip2", "clap")
        }
    return inputs


def validate_inputs(inputs: Mapping[str, Any]) -> None:
    family = inputs["family_registry"]
    evidence = inputs["evidence_registry"]
    split = inputs["source_split"]
    leakage = inputs["bundle_leakage"]
    index = inputs["index"]
    build = inputs["index_build"]
    resource_doc = inputs["index_resource"]
    models = inputs["model_manifest"]

    for label, document in (
        ("FAMILY_REGISTRY", family),
        ("EVIDENCE_REGISTRY", evidence),
        ("SOURCE_SPLIT", split),
        ("BUNDLE_LEAKAGE", leakage),
    ):
        verify_seal(document, "payload_sha256", label=label)
    verify_seal(index, "index_hash", label="INDEX")
    verify_seal(build, "build_manifest_hash", label="INDEX_BUILD")
    verify_seal(
        resource_doc, "resource_manifest_hash", label="INDEX_RESOURCE"
    )
    if family.get("family_count") != 20 or len(family.get("families", [])) != 20:
        raise DiagnosticError("EXACT_TWENTY_FAMILIES_REQUIRED")
    if evidence.get("evidence_count") != 56 or len(evidence.get("evidence", [])) != 56:
        raise DiagnosticError("EXACT_FIFTY_SIX_EVIDENCE_HANDLES_REQUIRED")
    if family.get("status") != "MACHINE_PROVISIONAL_FROZEN":
        raise DiagnosticError("FAMILY_BUNDLE_NOT_FROZEN")
    if evidence.get("status") != "MACHINE_PROVISIONAL_EVIDENCE_FROZEN":
        raise DiagnosticError("EVIDENCE_BUNDLE_NOT_FROZEN")
    if leakage.get("status") != "PASS":
        raise DiagnosticError("UPSTREAM_LEAKAGE_GATE_NOT_PASS")
    forbidden_true = (
        "semantic_annotations_entered",
        "private_human_labels_entered",
        "answer_keys_entered",
        "human_prescreen_entered",
        "raw_media_opened",
    )
    if any(leakage["checks"].get(key) is not False for key in forbidden_true):
        raise DiagnosticError("UPSTREAM_FORBIDDEN_INPUT_ENTERED")
    if any(
        row.get("machine_provisional_status") != "REPAIR"
        or row.get("accepted_family") is not False
        or row.get("accepted_ses") is not False
        or row.get("human_prescreen") != "NOT_PERFORMED"
        for row in family["families"]
    ):
        raise DiagnosticError("FAMILY_MACHINE_PROVISIONAL_BOUNDARY_BROKEN")
    if any(
        row.get("human_validated") is not False
        or row.get("semantic_content_asserted") is not False
        for row in evidence["evidence"]
    ):
        raise DiagnosticError("EVIDENCE_HUMAN_BOUNDARY_BROKEN")
    boundary = split.get("split_boundary", {})
    assignment = split.get("source_assignments", [{}])[0]
    if (
        split.get("status")
        != "P23_DEVELOPMENT_ONLY_SOURCE_DISJOINT_FROM_EVALUATION"
        or boundary.get("P23_102_development_only") is not True
        or boundary.get("P23_102_future_test_ineligible") is not True
        or boundary.get("evaluation_source_ids") != []
        or assignment.get("split") != "DEVELOPMENT_ONLY"
        or assignment.get("evaluation_eligible") is not False
    ):
        raise DiagnosticError("SOURCE_DISJOINT_DEVELOPMENT_BOUNDARY_BROKEN")
    if (
        build.get("decision") != "EPIC_P23_102_FULL_TIMELINE_PIPELINE_READY"
        or build.get("status") != "COMPLETE"
        or build.get("governance", {}).get("development_only") is not True
        or build.get("terminal_boundary", {}).get("index_only") is not True
    ):
        raise DiagnosticError("VERIFIED_INDEX_GATE_NOT_READY")
    modalities = index.get("modalities", {})
    visual = modalities.get("siglip2_visual", {}).get("documents", [])
    audio = modalities.get("clap_audio", {}).get("documents", [])
    if len(visual) != 1115 or len(audio) != 1115:
        raise DiagnosticError("FULL_INDEX_RECORD_COUNT_MISMATCH")
    visual_by_id = {str(row["segment_id"]): row for row in visual}
    audio_by_id = {str(row["segment_id"]): row for row in audio}
    if set(visual_by_id) != set(audio_by_id):
        raise DiagnosticError("MODALITY_RECORD_ID_SET_MISMATCH")
    for row in evidence["evidence"]:
        documents = (
            visual_by_id if row["modality"] == "vision" else audio_by_id
        )
        indexed = documents.get(str(row["record_id"]))
        if (
            indexed is None
            or int(indexed["start_us"]) != int(row["start_us"])
            or int(indexed["end_us"]) != int(row["end_us"])
        ):
            raise DiagnosticError(
                f"EVIDENCE_INDEX_BINDING_MISMATCH:{row['evidence_handle_id']}"
            )
    expected = {
        "siglip2": (
            "google/siglip2-base-patch16-224",
            "75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2",
        ),
        "clap": (
            "laion/clap-htsat-unfused",
            "8fa0f1c6d0433df6e97c127f64b2a1d6c0dcda8a",
        ),
    }
    if (
        models.get("status") != "ACQUISITION_COMPLETE"
        or models.get("wave_r_decision") != "WAVE_R_MODELS_READY"
        or models.get("technical_internal_use_authorized") is not True
    ):
        raise DiagnosticError("FROZEN_MODEL_GATE_NOT_READY")
    for key, (model_id, revision) in expected.items():
        entry = models["models"][key]
        if (
            entry.get("repo_id") != model_id
            or entry.get("revision") != revision
        ):
            raise DiagnosticError(f"FROZEN_MODEL_IDENTITY_MISMATCH:{key}")
        indexed_model = resource_doc["models"][
            "vision" if key == "siglip2" else "audio"
        ]
        if (
            indexed_model.get("model_id") != model_id
            or indexed_model.get("revision") != revision
        ):
            raise DiagnosticError(f"INDEX_MODEL_IDENTITY_MISMATCH:{key}")


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _embed_texts(
    texts: Sequence[str],
    *,
    model_path: Path,
    modality: str,
    threads: int,
) -> np.ndarray:
    if "long" not in np.__dict__:
        np.long = np.int64  # type: ignore[attr-defined]
    if "ulong" not in np.__dict__:
        np.ulong = np.uint64  # type: ignore[attr-defined]
    os.environ.update(
        {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "HF_DATASETS_OFFLINE": "1",
            "TOKENIZERS_PARALLELISM": "false",
        }
    )
    import torch

    torch.manual_seed(0)
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(max(1, threads))
    if modality == "vision":
        config_type = _load_json(model_path / "config.json").get("model_type")
        if config_type == "siglip":
            from transformers import SiglipModel as Model
            from transformers import SiglipProcessor as Processor
        elif config_type == "siglip2":
            from transformers import Siglip2Model as Model
            from transformers import Siglip2Processor as Processor
        else:
            raise DiagnosticError(
                f"UNSUPPORTED_SIGLIP_CONFIG_TYPE:{config_type}"
            )
        processor = Processor.from_pretrained(
            model_path, local_files_only=True, use_fast=False
        )
        model = Model.from_pretrained(
            model_path, local_files_only=True
        ).eval()
        inputs = processor(
            text=list(texts),
            padding="max_length",
            truncation=True,
            return_tensors="pt",
        )
        with torch.inference_mode():
            values = model.get_text_features(**inputs)
    elif modality == "ambient_audio":
        from transformers import ClapModel, ClapProcessor

        processor = ClapProcessor.from_pretrained(
            model_path, local_files_only=True
        )
        model = ClapModel.from_pretrained(
            model_path, local_files_only=True
        ).eval()
        inputs = processor(
            text=list(texts),
            padding=True,
            truncation=True,
            return_tensors="pt",
        )
        with torch.inference_mode():
            values = model.get_text_features(
                input_ids=inputs.input_ids,
                attention_mask=getattr(inputs, "attention_mask", None),
            )
    else:
        raise DiagnosticError(f"UNKNOWN_EMBEDDING_MODALITY:{modality}")
    if hasattr(values, "pooler_output"):
        values = values.pooler_output
    output = _normalize(values.float().cpu().numpy())
    del values, inputs, model, processor
    gc.collect()
    return output


def _rank_scores(
    identifiers: Sequence[str], scores: np.ndarray
) -> tuple[list[str], dict[str, int], dict[str, float]]:
    pairs = sorted(
        zip(identifiers, np.asarray(scores, dtype=np.float64).tolist()),
        key=lambda item: (-item[1], item[0]),
    )
    ranking = [item[0] for item in pairs]
    ranks = {identifier: rank for rank, identifier in enumerate(ranking, 1)}
    score_map = {identifier: round(float(score), 8) for identifier, score in pairs}
    return ranking, ranks, score_map


def _rrf(
    identifiers: Sequence[str],
    visual_ranks: Mapping[str, int],
    audio_ranks: Mapping[str, int],
) -> tuple[list[str], dict[str, int], dict[str, float]]:
    scores = {
        identifier: (
            1.0 / (RRF_K + int(visual_ranks[identifier]))
            + 1.0 / (RRF_K + int(audio_ranks[identifier]))
        )
        for identifier in identifiers
    }
    ranking = sorted(identifiers, key=lambda item: (-scores[item], item))
    return (
        ranking,
        {identifier: rank for rank, identifier in enumerate(ranking, 1)},
        {identifier: round(scores[identifier], 12) for identifier in ranking},
    )


def _random_ranking(
    query_id: str, identifiers: Sequence[str]
) -> tuple[list[str], dict[str, int], dict[str, float]]:
    values = {}
    for identifier in identifiers:
        digest = hashlib.sha256(
            f"{RANDOM_SEED}\x1f{query_id}\x1f{identifier}".encode()
        ).digest()
        values[identifier] = int.from_bytes(digest[:8], "big") / 2**64
    ranking = sorted(identifiers, key=lambda item: (-values[item], item))
    return (
        ranking,
        {identifier: rank for rank, identifier in enumerate(ranking, 1)},
        {identifier: round(values[identifier], 12) for identifier in ranking},
    )


def _temporal_ranking(
    documents: Sequence[Mapping[str, Any]],
) -> tuple[list[str], dict[str, int], dict[str, float]]:
    source_start = min(int(row["start_us"]) for row in documents)
    source_end = max(int(row["end_us"]) for row in documents)
    midpoint = (source_start + source_end) / 2.0
    span = max(1.0, source_end - source_start)
    scores = {
        str(row["segment_id"]): -abs(
            ((int(row["start_us"]) + int(row["end_us"])) / 2.0) - midpoint
        )
        / span
        for row in documents
    }
    ranking = sorted(scores, key=lambda item: (-scores[item], item))
    return (
        ranking,
        {identifier: rank for rank, identifier in enumerate(ranking, 1)},
        {identifier: round(scores[identifier], 12) for identifier in ranking},
    )


def _ranking_record(
    query_id: str,
    method: str,
    ranking: Sequence[str],
    scores: Mapping[str, float],
    *,
    ranking_space: str,
) -> dict[str, Any]:
    return {
        "query_id": query_id,
        "method": method,
        "ranking_space": ranking_space,
        "item_count": len(ranking),
        "items": [
            {
                "rank": rank,
                "record_id": identifier,
                "score": scores[identifier],
            }
            for rank, identifier in enumerate(ranking, 1)
        ],
    }


def _method_target_ranks(
    query: Mapping[str, Any],
    method: str,
    *,
    visual_ranks: Mapping[str, int],
    audio_ranks: Mapping[str, int],
    joint_ranks: Mapping[str, int],
    random_ranks: Mapping[str, int],
    temporal_ranks: Mapping[str, int],
) -> list[dict[str, Any]]:
    output = []
    for target in query["target_handles"]:
        modality = str(target["modality"])
        identifier = str(target["record_id"])
        if method == "visual_only":
            rank = visual_ranks.get(identifier) if modality == "vision" else None
        elif method == "audio_only":
            rank = (
                audio_ranks.get(identifier)
                if modality == "ambient_audio"
                else None
            )
        elif method == "equal_weight_rrf_joint":
            rank = joint_ranks.get(identifier)
        elif method == "oracle_modality_routing":
            rank = (
                visual_ranks.get(identifier)
                if modality == "vision"
                else audio_ranks.get(identifier)
            )
        elif method == "random_baseline":
            rank = random_ranks.get(identifier)
        elif method == "temporal_midpoint_baseline":
            rank = temporal_ranks.get(identifier)
        else:
            raise DiagnosticError(f"UNKNOWN_METHOD:{method}")
        output.append({**target, "rank": rank})
    return output


def compute_query_metrics(
    query: Mapping[str, Any],
    method: str,
    target_ranks: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    total = len(target_ranks)
    result: dict[str, Any] = {
        "query_id": query["query_id"],
        "query_scope": query["query_scope"],
        "family_id": query["family_id"],
        "temporal_stratum": query["temporal_stratum"],
        "method": method,
        "target_count": total,
        "target_ranks": list(target_ranks),
    }
    finite_ranks = [
        int(row["rank"]) for row in target_ranks if row["rank"] is not None
    ]
    result["first_target_rank"] = min(finite_ranks) if finite_ranks else None
    result["distractors_before_first_target"] = (
        min(finite_ranks) - 1 if finite_ranks else None
    )
    for cutoff in TOP_KS:
        hits = sum(
            row["rank"] is not None and int(row["rank"]) <= cutoff
            for row in target_ranks
        )
        result[f"evidence_recall_at_{cutoff}"] = round(hits / total, 8)
        result[f"all_evidence_success_at_{cutoff}"] = int(hits == total)
    modality_recall = {}
    for modality in ("vision", "ambient_audio"):
        rows = [row for row in target_ranks if row["modality"] == modality]
        modality_recall[modality] = {
            f"recall_at_{cutoff}": (
                round(
                    sum(
                        row["rank"] is not None
                        and int(row["rank"]) <= cutoff
                        for row in rows
                    )
                    / len(rows),
                    8,
                )
                if rows
                else None
            )
            for cutoff in TOP_KS
        }
    result["modality_conditioned_recall"] = modality_recall
    return result


def aggregate_metrics(
    per_query: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    groups: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(
        list
    )
    for row in per_query:
        for stratum in ("all", str(row["temporal_stratum"])):
            groups[
                (str(row["query_scope"]), stratum, str(row["method"]))
            ].append(row)
    rows = []
    for (scope, stratum, method), values in sorted(groups.items()):
        row: dict[str, Any] = {
            "query_scope": scope,
            "temporal_stratum": stratum,
            "method": method,
            "query_count": len(values),
            "target_count": sum(int(value["target_count"]) for value in values),
        }
        first_ranks = [
            int(value["first_target_rank"])
            for value in values
            if value["first_target_rank"] is not None
        ]
        row["mean_first_target_rank"] = (
            round(statistics.fmean(first_ranks), 8) if first_ranks else None
        )
        row["median_first_target_rank"] = (
            round(float(statistics.median(first_ranks)), 8)
            if first_ranks
            else None
        )
        row["mean_distractors_before_first_target"] = (
            round(
                statistics.fmean(
                    int(value["distractors_before_first_target"])
                    for value in values
                    if value["distractors_before_first_target"] is not None
                ),
                8,
            )
            if first_ranks
            else None
        )
        for cutoff in TOP_KS:
            row[f"evidence_recall_at_{cutoff}"] = round(
                statistics.fmean(
                    float(value[f"evidence_recall_at_{cutoff}"])
                    for value in values
                ),
                8,
            )
            row[f"all_evidence_success_at_{cutoff}"] = round(
                statistics.fmean(
                    float(value[f"all_evidence_success_at_{cutoff}"])
                    for value in values
                ),
                8,
            )
            for modality in ("vision", "ambient_audio"):
                candidates = [
                    value["modality_conditioned_recall"][modality][
                        f"recall_at_{cutoff}"
                    ]
                    for value in values
                ]
                candidates = [value for value in candidates if value is not None]
                row[
                    f"{modality}_conditioned_recall_at_{cutoff}"
                ] = (
                    round(statistics.fmean(candidates), 8)
                    if candidates
                    else None
                )
        rows.append(row)
    keyed = {
        (row["query_scope"], row["temporal_stratum"], row["method"]): row
        for row in rows
    }
    deltas = []
    for scope in ("family", "handle"):
        for stratum in ("all", "near_local", "far_separated"):
            joint = keyed.get((scope, stratum, "equal_weight_rrf_joint"))
            visual = keyed.get((scope, stratum, "visual_only"))
            audio = keyed.get((scope, stratum, "audio_only"))
            if not (joint and visual and audio):
                continue
            for cutoff in TOP_KS:
                metric = f"evidence_recall_at_{cutoff}"
                best = max(float(visual[metric]), float(audio[metric]))
                deltas.append(
                    {
                        "query_scope": scope,
                        "temporal_stratum": stratum,
                        "cutoff": cutoff,
                        "joint_evidence_recall": joint[metric],
                        "best_unimodal_evidence_recall": round(best, 8),
                        "joint_minus_best_unimodal": round(
                            float(joint[metric]) - best, 8
                        ),
                    }
                )
    return {
        "metric_definitions": {
            "evidence_recall_at_k": (
                "Macro mean, over queries, of machine-provisional evidence "
                "handles ranked at or above k. A unimodal method receives no "
                "credit for handles from the other modality."
            ),
            "all_evidence_success_at_k": (
                "Fraction of queries for which every machine-provisional "
                "target handle is ranked at or above k."
            ),
            "modality_conditioned_recall": (
                "Recall restricted to target handles of the named modality."
            ),
            "first_target_rank": (
                "Best target rank; distractors-before-first-target is rank-1."
            ),
            "oracle_modality_routing": (
                "Evaluation-only routing to the frozen learned ranker matching "
                "each target handle modality; it is not available at inference."
            ),
        },
        "rows": rows,
        "joint_minus_best_unimodal": deltas,
        "bm25_baseline": {
            "applicable": False,
            "status": "NOT_APPLICABLE_NO_SPEECH_EVIDENCE_HANDLE",
            "reason": (
                "All 56 provisional targets are vision or ambient_audio; "
                "speech/ASR is excluded from the V+A route hypotheses."
            ),
        },
    }


def leakage_audit(
    queries: Sequence[Mapping[str, Any]],
    speech_documents: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    text_groups: dict[str, list[str]] = defaultdict(list)
    exact_asr = {str(row.get("text", "")).strip() for row in speech_documents}
    per_query = []
    for query in queries:
        text = str(query["query_text"])
        text_groups[text].append(str(query["query_id"]))
        target_strings = {
            str(target["record_id"]) for target in query["target_handles"]
        }
        query_tokens = set(_tokens(text))
        max_overlap = 0.0
        max_overlap_chunk = None
        for document in speech_documents:
            speech_tokens = set(_tokens(str(document.get("text", ""))))
            if not query_tokens:
                overlap = 0.0
            else:
                overlap = len(query_tokens & speech_tokens) / len(query_tokens)
            if overlap > max_overlap:
                max_overlap = overlap
                max_overlap_chunk = document.get("chunk_id")
        per_query.append(
            {
                "query_id": query["query_id"],
                "query_scope": query["query_scope"],
                "target_record_id_literal_present": any(
                    value in text for value in target_strings
                ),
                "source_id_literal_present": SOURCE_ID in text,
                "timestamp_literal_present": bool(
                    re.search(r"\b\d+(?:\.\d+)?\s*(?:s|sec|seconds)\b", text)
                ),
                "exact_asr_text_match": text.strip() in exact_asr,
                "max_query_token_containment_in_asr": round(max_overlap, 8),
                "max_overlap_chunk_id": max_overlap_chunk,
            }
        )
    duplicate_groups = [
        {
            "query_text_sha256": bytes_hash(text.encode("utf-8")),
            "query_count": len(query_ids),
            "query_ids": sorted(query_ids),
        }
        for text, query_ids in text_groups.items()
        if len(query_ids) > 1
    ]
    duplicate_groups.sort(
        key=lambda row: (-int(row["query_count"]), row["query_text_sha256"])
    )
    direct_leakage = any(
        row["target_record_id_literal_present"]
        or row["source_id_literal_present"]
        or row["timestamp_literal_present"]
        or row["exact_asr_text_match"]
        for row in per_query
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_classification": (
            "DESCRIPTIVE_MACHINE_PROVISIONAL_DEVELOPMENT_ONLY"
        ),
        "checks": {
            "target_record_ids_in_query_text": any(
                row["target_record_id_literal_present"] for row in per_query
            ),
            "source_id_in_query_text": any(
                row["source_id_literal_present"] for row in per_query
            ),
            "timestamps_in_query_text": any(
                row["timestamp_literal_present"] for row in per_query
            ),
            "exact_query_equals_asr_text": any(
                row["exact_asr_text_match"] for row in per_query
            ),
            "human_labels_or_answer_keys_used": False,
            "semantic_annotations_used": False,
            "raw_media_opened": False,
            "generation_or_agent_used": False,
            "network_used": False,
        },
        "direct_query_to_index_text_leakage_detected": direct_leakage,
        "query_count": len(queries),
        "unique_query_text_count": len(text_groups),
        "duplicate_query_text_group_count": len(duplicate_groups),
        "identical_text_shortcut_risk": (
            "HIGH_NON_IDENTIFIABILITY"
            if duplicate_groups
            else "NOT_DETECTED"
        ),
        "interpretation": (
            "No direct record-id/timestamp/ASR exact-text shortcut is allowed. "
            "Repeated neutral templates are explicitly detected: families "
            "sharing identical text necessarily receive identical learned "
            "rankings, so results are descriptive diagnostics rather than "
            "evidence of semantic family retrieval."
        ),
        "duplicate_query_text_groups": duplicate_groups,
        "per_query": per_query,
    }


def _embedding_hash(
    texts: Sequence[str], visual: np.ndarray, audio: np.ndarray
) -> str:
    digest = hashlib.sha256()
    for text, visual_row, audio_row in zip(texts, visual, audio):
        encoded = text.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(np.asarray(visual_row, dtype="<f4").tobytes())
        digest.update(np.asarray(audio_row, dtype="<f4").tobytes())
    return "sha256:" + digest.hexdigest()


def run_diagnostic(
    root: Path,
    *,
    threads: int = 1,
    verify_model_files: bool = True,
) -> dict[str, Any]:
    started_wall = datetime.now(UTC)
    started = time.perf_counter()
    inputs = load_inputs(root, verify_model_files=verify_model_files)
    family_doc = inputs["family_registry"]
    evidence_doc = inputs["evidence_registry"]
    queries = build_queries(
        family_doc["families"], evidence_doc["evidence"]
    )
    unique_texts = sorted({str(query["query_text"]) for query in queries})
    text_index = {text: index for index, text in enumerate(unique_texts)}

    model_manifest = inputs["model_manifest"]["models"]
    siglip_path = _safe_path(
        root,
        model_manifest["siglip2"]["snapshot_dir"],
        label="SIGLIP_MODEL",
    )
    clap_path = _safe_path(
        root,
        model_manifest["clap"]["snapshot_dir"],
        label="CLAP_MODEL",
    )
    embedding_started = time.perf_counter()
    visual_text = _embed_texts(
        unique_texts,
        model_path=siglip_path,
        modality="vision",
        threads=threads,
    )
    audio_text = _embed_texts(
        unique_texts,
        model_path=clap_path,
        modality="ambient_audio",
        threads=threads,
    )
    embedding_seconds = time.perf_counter() - embedding_started

    modalities = inputs["index"]["modalities"]
    identifiers, visual_docs_matrix, visual_docs = _decode_vectors(
        modalities["siglip2_visual"]["documents"]
    )
    audio_identifiers, audio_docs_matrix, audio_docs = _decode_vectors(
        modalities["clap_audio"]["documents"]
    )
    if identifiers != audio_identifiers:
        raise DiagnosticError("MODALITY_IDENTIFIER_ORDER_MISMATCH")
    visual_scores = np.matmul(visual_text, visual_docs_matrix.T)
    audio_scores = np.matmul(audio_text, audio_docs_matrix.T)
    temporal_ranking, temporal_ranks, temporal_scores = _temporal_ranking(
        visual_docs
    )

    ranking_rows: list[dict[str, Any]] = []
    per_query_metrics: list[dict[str, Any]] = []
    learned_cache: dict[
        str,
        tuple[
            tuple[list[str], dict[str, int], dict[str, float]],
            tuple[list[str], dict[str, int], dict[str, float]],
            tuple[list[str], dict[str, int], dict[str, float]],
        ],
    ] = {}
    methods = (
        "visual_only",
        "audio_only",
        "equal_weight_rrf_joint",
        "oracle_modality_routing",
        "random_baseline",
        "temporal_midpoint_baseline",
    )
    for query in queries:
        text = str(query["query_text"])
        if text not in learned_cache:
            offset = text_index[text]
            visual_ranked = _rank_scores(identifiers, visual_scores[offset])
            audio_ranked = _rank_scores(identifiers, audio_scores[offset])
            joint_ranked = _rrf(
                identifiers, visual_ranked[1], audio_ranked[1]
            )
            learned_cache[text] = (
                visual_ranked,
                audio_ranked,
                joint_ranked,
            )
        visual_ranked, audio_ranked, joint_ranked = learned_cache[text]
        random_ranked = _random_ranking(str(query["query_id"]), identifiers)
        ranking_rows.extend(
            (
                _ranking_record(
                    str(query["query_id"]),
                    "visual_only",
                    visual_ranked[0],
                    visual_ranked[2],
                    ranking_space="vision_segments",
                ),
                _ranking_record(
                    str(query["query_id"]),
                    "audio_only",
                    audio_ranked[0],
                    audio_ranked[2],
                    ranking_space="ambient_audio_segments",
                ),
                _ranking_record(
                    str(query["query_id"]),
                    "equal_weight_rrf_joint",
                    joint_ranked[0],
                    joint_ranked[2],
                    ranking_space="temporally_aligned_segment_ids",
                ),
                _ranking_record(
                    str(query["query_id"]),
                    "random_baseline",
                    random_ranked[0],
                    random_ranked[2],
                    ranking_space="temporally_aligned_segment_ids",
                ),
                _ranking_record(
                    str(query["query_id"]),
                    "temporal_midpoint_baseline",
                    temporal_ranking,
                    temporal_scores,
                    ranking_space="temporally_aligned_segment_ids",
                ),
            )
        )
        for method in methods:
            target_ranks = _method_target_ranks(
                query,
                method,
                visual_ranks=visual_ranked[1],
                audio_ranks=audio_ranked[1],
                joint_ranks=joint_ranked[1],
                random_ranks=random_ranked[1],
                temporal_ranks=temporal_ranks,
            )
            per_query_metrics.append(
                compute_query_metrics(query, method, target_ranks)
            )

    leakage = leakage_audit(
        queries, modalities["speech"]["documents"]
    )
    metric_tables = aggregate_metrics(per_query_metrics)
    output_root = _safe_path(root, OUTPUT_ROOT, label="OUTPUT_ROOT")
    output_root.mkdir(parents=True, exist_ok=True)
    output_root.chmod(0o700)
    config = seal(
        {
            "schema_version": SCHEMA_VERSION,
            "created_date": CREATED_DATE,
            "diagnostic_id": "AV-TRACE-P23-102-REAL-RETRIEVAL-DIAGNOSTIC-V1",
            "artifact_classification": (
                "DESCRIPTIVE_MACHINE_PROVISIONAL_DEVELOPMENT_ONLY"
            ),
            "source_id": SOURCE_ID,
            "source_group_id": SOURCE_GROUP_ID,
            "source_boundary": {
                "development_only": True,
                "evaluation_eligible": False,
                "future_test_eligible": False,
                "source_disjoint_from_evaluation": True,
            },
            "allowed_inputs": sorted(inputs["input_file_hashes"]),
            "forbidden_inputs": [
                "raw media",
                "semantic annotations",
                "human labels",
                "answer keys",
                "accepted SES labels",
                "evaluation outcomes",
                "generation models",
                "agent trajectories",
            ],
            "retrieval": {
                "document_vectors": (
                    "stored verified SigLIP visual and CLAP audio float16 vectors"
                ),
                "query_text_policy": (
                    "exact registry question/answer/atomic-claim templates only"
                ),
                "rankers": {
                    "visual_only": "SigLIP text-image cosine",
                    "audio_only": "CLAP text-audio cosine",
                    "equal_weight_rrf_joint": {
                        "type": "equal-weight reciprocal-rank fusion",
                        "rrf_k": RRF_K,
                        "weights": {"vision": 1.0, "ambient_audio": 1.0},
                    },
                    "oracle_modality_routing": (
                        "evaluation-only target-modality routing"
                    ),
                },
                "baselines": {
                    "random": {
                        "seed": RANDOM_SEED,
                        "algorithm": "sha256(query_id, record_id) ordering",
                    },
                    "temporal": (
                        "query-independent distance to source timeline midpoint"
                    ),
                    "bm25": "not applicable: no speech evidence handles",
                },
                "top_ks": list(TOP_KS),
                "score_rounding_decimals": 8,
                "threads": threads,
            },
            "models": inputs["verified_models"],
            "input_hashes": inputs["input_file_hashes"],
            "upstream_hashes": {
                "index_hash": inputs["index"]["index_hash"],
                "index_build_hash": inputs["index_build"][
                    "build_manifest_hash"
                ],
                "index_resource_hash": inputs["index_resource"][
                    "resource_manifest_hash"
                ],
                "family_registry_hash": family_doc["payload_sha256"],
                "evidence_registry_hash": evidence_doc["payload_sha256"],
                "bundle_content_hash": inputs["bundle_leakage"][
                    "bundle_content_sha256"
                ],
                "source_split_hash": inputs["source_split"]["payload_sha256"],
            },
            "counts": {
                "families": len(family_doc["families"]),
                "evidence_handles": len(evidence_doc["evidence"]),
                "queries": len(queries),
                "unique_query_texts": len(unique_texts),
                "visual_index_records": len(visual_docs),
                "audio_index_records": len(audio_docs),
            },
        },
        "config_sha256",
    )
    query_document = seal(
        {
            "schema_version": SCHEMA_VERSION,
            "artifact_classification": (
                "DESCRIPTIVE_MACHINE_PROVISIONAL_DEVELOPMENT_ONLY"
            ),
            "query_policy": (
                "No text outside exact machine-generated provisional registry "
                "template fields is embedded."
            ),
            "query_count": len(queries),
            "unique_query_text_count": len(unique_texts),
            "embedding_sha256": _embedding_hash(
                unique_texts, visual_text, audio_text
            ),
            "queries": queries,
        }
    )
    per_query_document = seal(
        {
            "schema_version": SCHEMA_VERSION,
            "artifact_classification": (
                "DESCRIPTIVE_MACHINE_PROVISIONAL_DEVELOPMENT_ONLY"
            ),
            "row_count": len(per_query_metrics),
            "rows": per_query_metrics,
        }
    )
    metric_document = seal(
        {
            "schema_version": SCHEMA_VERSION,
            "artifact_classification": (
                "DESCRIPTIVE_MACHINE_PROVISIONAL_DEVELOPMENT_ONLY"
            ),
            **metric_tables,
        }
    )
    leakage_document = seal(leakage)

    ranking_payload = _gzip_jsonl(ranking_rows)
    core_payloads = {
        "config.json": canonical_bytes(config),
        "queries.json": canonical_bytes(query_document),
        "rankings.jsonl.gz": ranking_payload,
        "per_query_metrics.json": canonical_bytes(per_query_document),
        "metric_tables.json": canonical_bytes(metric_document),
        "leakage_audit.json": canonical_bytes(leakage_document),
    }
    for name, payload in core_payloads.items():
        _atomic_write(output_root / name, payload, restricted=True)
    core_hashes = {
        name: bytes_hash(payload) for name, payload in sorted(core_payloads.items())
    }
    deterministic = seal(
        {
            "schema_version": SCHEMA_VERSION,
            "artifact_classification": (
                "DESCRIPTIVE_MACHINE_PROVISIONAL_DEVELOPMENT_ONLY"
            ),
            "status": READY,
            "config_sha256": config["config_sha256"],
            "query_embedding_sha256": query_document["embedding_sha256"],
            "core_output_hashes": core_hashes,
            "ranking_record_count": len(ranking_rows),
            "ranking_item_count": sum(
                int(row["item_count"]) for row in ranking_rows
            ),
            "metric_row_count": len(metric_document["rows"]),
            "per_query_metric_row_count": len(per_query_metrics),
            "determinism_boundary": (
                "Runtime timestamps and elapsed/resource measurements are "
                "excluded; all query text, embeddings, rankings, scores, "
                "metrics, hashes, and tie-breaks are included."
            ),
        },
        "deterministic_rerun_sha256",
    )
    _write_json(output_root / "deterministic_payload.json", deterministic)

    runtime = seal(
        {
            "schema_version": SCHEMA_VERSION,
            "started_at_utc": started_wall.isoformat(),
            "completed_at_utc": datetime.now(UTC).isoformat(),
            "elapsed_seconds": round(time.perf_counter() - started, 6),
            "text_embedding_seconds": round(embedding_seconds, 6),
            "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "runtime": {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "numpy": _package_version("numpy"),
                "torch": _package_version("torch"),
                "transformers": _package_version("transformers"),
                "threads": threads,
                "device": "cpu",
                "deterministic_algorithms": True,
                "network_access": "disabled",
            },
            "resource_counts": {
                "queries": len(queries),
                "unique_query_texts_embedded_per_model": len(unique_texts),
                "index_vectors_scored_per_query_per_modality": len(identifiers),
                "ranking_records_written": len(ranking_rows),
            },
        },
        "runtime_payload_sha256",
    )
    _write_json(output_root / "resource_runtime.json", runtime)

    audit = validate_output(
        root,
        output_root=OUTPUT_ROOT,
        public_summary_path=None,
        require_public=False,
    )
    audit_document = seal(
        {
            "schema_version": SCHEMA_VERSION,
            "status": READY,
            "validation": audit,
            "deterministic_rerun_sha256": deterministic[
                "deterministic_rerun_sha256"
            ],
            "claim_boundary": (
                "Descriptive machine-provisional retrieval diagnostic only; "
                "not human-validated evidence, accepted SES, H-tier, Gate-A, "
                "or source-generalization evidence."
            ),
        }
    )
    _write_json(output_root / "audit.json", audit_document)

    all_output_hashes = {
        name: file_hash(output_root / name)
        for name in (
            *CORE_OUTPUT_NAMES,
            "deterministic_payload.json",
            "resource_runtime.json",
            "audit.json",
        )
    }
    summary = seal(
        {
            "schema_version": SCHEMA_VERSION,
            "created_date": CREATED_DATE,
            "status": READY,
            "decision": READY,
            "artifact_classification": (
                "DESCRIPTIVE_MACHINE_PROVISIONAL_DEVELOPMENT_ONLY"
            ),
            "source_id": SOURCE_ID,
            "source_group_id": SOURCE_GROUP_ID,
            "output_root": OUTPUT_ROOT.as_posix(),
            "deterministic_rerun_sha256": deterministic[
                "deterministic_rerun_sha256"
            ],
            "config_sha256": config["config_sha256"],
            "output_hashes": all_output_hashes,
            "counts": config["counts"],
            "source_disjoint_development_boundary": config["source_boundary"],
            "bm25_baseline": metric_document["bm25_baseline"],
            "leakage_summary": {
                "direct_query_to_index_text_leakage_detected": leakage_document[
                    "direct_query_to_index_text_leakage_detected"
                ],
                "unique_query_text_count": leakage_document[
                    "unique_query_text_count"
                ],
                "identical_text_shortcut_risk": leakage_document[
                    "identical_text_shortcut_risk"
                ],
            },
            "claim_boundary": (
                "Results are descriptive and machine-provisional only. They "
                "must not be interpreted as human-validated semantic support, "
                "modality necessity, accepted evidence, or generalization."
            ),
        }
    )
    public_path = _safe_path(
        root, PUBLIC_SUMMARY_PATH, label="PUBLIC_SUMMARY"
    )
    _write_json(public_path, summary, restricted=False)
    final_validation = validate_output(root)
    return {
        "status": READY,
        "summary_path": _relative(root, public_path),
        "output_root": _relative(root, output_root),
        "deterministic_rerun_sha256": deterministic[
            "deterministic_rerun_sha256"
        ],
        "validation": final_validation,
    }


def _read_rankings(path: Path) -> list[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def validate_output(
    root: Path,
    *,
    output_root: Path = OUTPUT_ROOT,
    public_summary_path: Path | None = PUBLIC_SUMMARY_PATH,
    require_public: bool = True,
) -> dict[str, Any]:
    restricted = _safe_path(root, output_root, label="VALIDATE_OUTPUT_ROOT")
    required = [
        *CORE_OUTPUT_NAMES,
        "deterministic_payload.json",
        "resource_runtime.json",
    ]
    if require_public:
        required.append("audit.json")
    for name in required:
        if not (restricted / name).is_file():
            raise DiagnosticError(f"OUTPUT_MISSING:{name}")
    config = _load_json(restricted / "config.json")
    queries = _load_json(restricted / "queries.json")
    per_query = _load_json(restricted / "per_query_metrics.json")
    metrics = _load_json(restricted / "metric_tables.json")
    leakage = _load_json(restricted / "leakage_audit.json")
    deterministic = _load_json(restricted / "deterministic_payload.json")
    runtime = _load_json(restricted / "resource_runtime.json")
    for label, document, field in (
        ("CONFIG", config, "config_sha256"),
        ("QUERIES", queries, "payload_sha256"),
        ("PER_QUERY", per_query, "payload_sha256"),
        ("METRICS", metrics, "payload_sha256"),
        ("LEAKAGE", leakage, "payload_sha256"),
        ("DETERMINISTIC", deterministic, "deterministic_rerun_sha256"),
        ("RUNTIME", runtime, "runtime_payload_sha256"),
    ):
        verify_seal(document, field, label=label)
    if (
        deterministic.get("status") != READY
        or config.get("counts", {}).get("families") != 20
        or config.get("counts", {}).get("evidence_handles") != 56
        or queries.get("query_count") != 76
        or per_query.get("row_count") != 456
        or leakage.get("checks", {}).get("raw_media_opened") is not False
        or leakage.get("checks", {}).get("semantic_annotations_used") is not False
        or leakage.get("checks", {}).get("human_labels_or_answer_keys_used")
        is not False
        or metrics.get("bm25_baseline", {}).get("applicable") is not False
    ):
        raise DiagnosticError("OUTPUT_SEMANTIC_VALIDATION_FAILED")
    if config["source_boundary"] != {
        "development_only": True,
        "evaluation_eligible": False,
        "future_test_eligible": False,
        "source_disjoint_from_evaluation": True,
    }:
        raise DiagnosticError("OUTPUT_SOURCE_BOUNDARY_MISMATCH")
    core_hashes = {
        name: file_hash(restricted / name) for name in CORE_OUTPUT_NAMES
    }
    if deterministic.get("core_output_hashes") != core_hashes:
        raise DiagnosticError("DETERMINISTIC_CORE_HASH_MISMATCH")
    ranking_rows = _read_rankings(restricted / "rankings.jsonl.gz")
    if len(ranking_rows) != deterministic.get("ranking_record_count"):
        raise DiagnosticError("RANKING_RECORD_COUNT_MISMATCH")
    ranking_item_count = 0
    for row in ranking_rows:
        items = row.get("items", [])
        if int(row.get("item_count", -1)) != len(items):
            raise DiagnosticError("RANKING_ITEM_COUNT_MISMATCH")
        if [item["rank"] for item in items] != list(
            range(1, len(items) + 1)
        ):
            raise DiagnosticError("RANKING_SEQUENCE_INVALID")
        if len({item["record_id"] for item in items}) != len(items):
            raise DiagnosticError("RANKING_DUPLICATE_RECORD")
        ranking_item_count += len(items)
    if ranking_item_count != deterministic.get("ranking_item_count"):
        raise DiagnosticError("RANKING_TOTAL_ITEM_COUNT_MISMATCH")
    if require_public:
        audit = _load_json(restricted / "audit.json")
        verify_seal(audit, "payload_sha256", label="AUDIT")
        if audit.get("status") != READY:
            raise DiagnosticError("AUDIT_NOT_READY")
        if public_summary_path is None:
            raise DiagnosticError("PUBLIC_SUMMARY_PATH_REQUIRED")
        public = _safe_path(
            root, public_summary_path, label="VALIDATE_PUBLIC_SUMMARY"
        )
        if not public.is_file():
            raise DiagnosticError("PUBLIC_SUMMARY_MISSING")
        summary = _load_json(public)
        verify_seal(summary, "payload_sha256", label="PUBLIC_SUMMARY")
        if (
            summary.get("status") != READY
            or summary.get("decision") != READY
            or summary.get("deterministic_rerun_sha256")
            != deterministic.get("deterministic_rerun_sha256")
        ):
            raise DiagnosticError("PUBLIC_SUMMARY_NOT_READY")
        expected_output_hashes = {
            name: file_hash(restricted / name)
            for name in (
                *CORE_OUTPUT_NAMES,
                "deterministic_payload.json",
                "resource_runtime.json",
                "audit.json",
            )
        }
        if summary.get("output_hashes") != expected_output_hashes:
            raise DiagnosticError("PUBLIC_OUTPUT_HASH_MISMATCH")
    return {
        "passed": True,
        "status": READY,
        "query_count": queries["query_count"],
        "per_query_metric_row_count": per_query["row_count"],
        "ranking_record_count": len(ranking_rows),
        "ranking_item_count": ranking_item_count,
        "deterministic_rerun_sha256": deterministic[
            "deterministic_rerun_sha256"
        ],
    }


def _synthetic_self_test() -> dict[str, Any]:
    query = {
        "query_id": "q",
        "query_scope": "family",
        "family_id": "f",
        "temporal_stratum": "near_local",
    }
    ranks = [
        {
            "evidence_handle_id": "v",
            "modality": "vision",
            "record_id": "a",
            "rank": 1,
        },
        {
            "evidence_handle_id": "a",
            "modality": "ambient_audio",
            "record_id": "b",
            "rank": 5,
        },
    ]
    metric = compute_query_metrics(query, "synthetic", ranks)
    if (
        metric["evidence_recall_at_1"] != 0.5
        or metric["evidence_recall_at_5"] != 1.0
        or metric["all_evidence_success_at_5"] != 1
    ):
        raise DiagnosticError("SYNTHETIC_METRIC_SELF_TEST_FAILED")
    identifiers = ["a", "b"]
    ranking, _, _ = _rrf(
        identifiers, {"a": 1, "b": 2}, {"a": 2, "b": 1}
    )
    if ranking != ["a", "b"]:
        raise DiagnosticError("SYNTHETIC_RRF_TIE_BREAK_FAILED")
    return {"passed": True}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--validate-output", action="store_true")
    mode.add_argument("--synthetic-self-test", action="store_true")
    parser.add_argument("--repo-root", default=str(repo_root_default()))
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--skip-model-file-rehash", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.repo_root).resolve()
    try:
        if args.synthetic_self_test:
            result = _synthetic_self_test()
        elif args.validate_output:
            result = validate_output(root)
        else:
            if args.threads < 1:
                raise DiagnosticError("THREADS_MUST_BE_POSITIVE")
            result = run_diagnostic(
                root,
                threads=args.threads,
                verify_model_files=not args.skip_model_file_rehash,
            )
        print(json.dumps(result, sort_keys=True))
        return 0
    except (DiagnosticError, OSError, ValueError, KeyError) as exc:
        print(
            json.dumps(
                {
                    "status": REPAIR,
                    "error": f"{type(exc).__name__}:{exc}",
                },
                sort_keys=True,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
