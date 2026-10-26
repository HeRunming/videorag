"""Wave-R learned SigLIP2/CLAP retrieval on the frozen Scale-1A timeline.

This module deliberately does not import or mutate Scale-1A production code.
It consumes Scale-1A artifacts as immutable controls and writes learned
sidecars under ``data/restricted/scale1b/wave_r``.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import resource
import stat
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

import av
import numpy as np


SCHEMA = "av-trace.scale1b.wave-r/1.0"
STAGE = "MACHINE_ADJUDICATED_PROVISIONAL_MVP"
WARNING = "LOW_N_DESCRIPTIVE_WAVE_R"
FINAL_STATUS = "FINAL_BENCHMARK_NOT_YET_VALIDATED"
TOP_KS = (1, 5, 10, 20)
FORBIDDEN_SEARCH_KEYS = {
    "question", "answer", "answer_hypothesis", "answer_aliases", "claims",
    "claim_id", "claim_ids", "rationale", "reviewer_rationale", "state",
    "state_role", "family_id", "review_id", "source_review_id",
    "intervention_id", "evidence_id", "evidence_ids",
}

CONTRACT_REL = Path("data/rehearsal_plan/scale1b_wave_r_trust_anchor.json")
MODEL_MANIFEST_REL = Path(
    "data/restricted/scale1b/manifests/wave_r_model_acquisition.json"
)
SCALE1A_AUDIT_REL = Path("data/restricted/noaa01/scale1a/final_audit.json")
SCALE1A_ROOT_REL = Path("data/restricted/noaa01/scale1a")
SCALE1A_RESULT_REL = Path("mvp/results/scale1a_full_timeline")
ACQUISITION_REL = Path(
    "data/restricted/noaa01/manifests/noaa01_acquisition_manifest.json"
)
RESTRICTED_REL = Path("data/restricted/scale1b/wave_r")
RESULTS_REL = Path("mvp/results/scale1b_wave_r")


class Scale1BWaveRError(RuntimeError):
    """Fail-closed Wave-R error."""


def _load(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode()


def _json_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _self_hash_valid(document: Mapping[str, Any], field: str) -> bool:
    expected = document.get(field)
    if not isinstance(expected, str):
        return False
    payload = dict(document)
    payload.pop(field, None)
    return expected == _json_hash(payload)


def _sha256(path: Path, *, prefixed: bool = False) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    value = digest.hexdigest()
    return f"sha256:{value}" if prefixed else value


def _atomic(path: Path, payload: bytes, *, restricted: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if restricted:
        path.parent.chmod(0o700)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp = Path(name)
    try:
        os.fchmod(fd, 0o600 if restricted else 0o644)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        path.chmod(0o600 if restricted else 0o644)
    finally:
        tmp.unlink(missing_ok=True)


def _dump(path: Path, value: Any, *, restricted: bool = True) -> None:
    _atomic(
        path,
        json.dumps(
            value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False
        ).encode() + b"\n",
        restricted=restricted,
    )


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp = Path(name)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        path.chmod(0o644)
    finally:
        tmp.unlink(missing_ok=True)


def _version(package: str) -> str | None:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return None


def _decisions(document: Mapping[str, Any]) -> set[str]:
    values: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, str):
            values.add(value)
        elif isinstance(value, Mapping):
            for item in value.values():
                visit(item)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            for item in value:
                visit(item)

    # Acquisition manifests use both top-level ``*_decision`` fields and
    # per-model nested technical decisions. Collect exact scalar values from
    # the whole document; gates still require exact enum equality.
    visit(document)
    return values


def _verify_inventory(repo_root: Path, entries: Iterable[Mapping[str, Any]]) -> None:
    failures: list[str] = []
    for entry in entries:
        rel = entry.get("path") or entry.get("relative_path")
        if not rel:
            continue
        path = repo_root / str(rel)
        if not path.is_file() or path.is_symlink():
            failures.append(f"{rel}:missing_or_unsafe")
            continue
        expected_size = entry.get("size_bytes")
        if expected_size is not None and path.stat().st_size != int(expected_size):
            failures.append(f"{rel}:size")
        expected_hash = str(entry.get("sha256", "")).removeprefix("sha256:")
        if expected_hash and _sha256(path) != expected_hash:
            failures.append(f"{rel}:sha256")
        expected_mode = entry.get("mode")
        if expected_mode and f"{stat.S_IMODE(path.stat().st_mode):04o}" != str(
            expected_mode
        ).removeprefix("0o"):
            failures.append(f"{rel}:mode")
    if failures:
        raise Scale1BWaveRError("TRUST_ANCHOR_INVENTORY_MISMATCH:" + ",".join(failures))


def verify_gates(repo_root: Path) -> dict[str, Any]:
    paths = {
        "contract": repo_root / CONTRACT_REL,
        "models": repo_root / MODEL_MANIFEST_REL,
        "scale1a": repo_root / SCALE1A_AUDIT_REL,
    }
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise Scale1BWaveRError("PREREQUISITE_MISSING:" + ",".join(missing))
    contract, models, audit = (_load(paths[x]) for x in ("contract", "models", "scale1a"))
    if "WAVE_R_CONTRACT_FROZEN" not in _decisions(contract):
        raise Scale1BWaveRError("WAVE_R_CONTRACT_NOT_FROZEN")
    if not _self_hash_valid(contract, "anchor_sha256"):
        raise Scale1BWaveRError("WAVE_R_CONTRACT_SELF_HASH_MISMATCH")
    if models.get("status") != "ACQUISITION_COMPLETE":
        raise Scale1BWaveRError("WAVE_R_MODEL_ACQUISITION_INCOMPLETE")
    if models.get("siglip2_decision") != "SIGLIP2_SNAPSHOT_READY":
        raise Scale1BWaveRError("SIGLIP2_TECHNICAL_GATE_NOT_READY")
    if models.get("clap_decision") != "CLAP_SNAPSHOT_READY":
        raise Scale1BWaveRError("CLAP_TECHNICAL_GATE_NOT_READY")
    if models.get("wave_r_decision") != "WAVE_R_MODELS_READY":
        raise Scale1BWaveRError("WAVE_R_MODELS_GATE_NOT_READY")
    if models.get("technical_internal_use_authorized") is not True:
        raise Scale1BWaveRError("WAVE_R_INTERNAL_USE_NOT_AUTHORIZED")
    if set(models.get("models", {})) != {"siglip2", "clap"}:
        raise Scale1BWaveRError("WAVE_R_MODEL_SET_MISMATCH")
    for model_id, expected in (
        ("siglip2", "SIGLIP2_SNAPSHOT_READY"),
        ("clap", "CLAP_SNAPSHOT_READY"),
    ):
        if models["models"][model_id].get("technical_inference_decision") != expected:
            raise Scale1BWaveRError(f"{model_id.upper()}_NESTED_GATE_NOT_READY")
    audit_decisions = _decisions(audit)
    for required in ("SCALE1A_ENGINEERING_GO", "SCALE1A_MILESTONE_PROVEN"):
        if required not in audit_decisions:
            raise Scale1BWaveRError(f"SCALE1A_GATE_NOT_READY:{required}")
    inventories: list[Mapping[str, Any]] = []
    for key in ("inventory", "artifact_inventory", "frozen_artifacts"):
        value = contract.get(key)
        if isinstance(value, list):
            inventories.extend(value)
    _verify_inventory(repo_root, inventories)
    for model_id, entry in models.get("models", {}).items():
        snapshot_rel = entry.get("snapshot_dir")
        if not snapshot_rel:
            raise Scale1BWaveRError(f"MODEL_SNAPSHOT_PATH_MISSING:{model_id}")
        snapshot = repo_root / snapshot_rel
        if not snapshot.is_dir() or snapshot.is_symlink():
            raise Scale1BWaveRError(f"MODEL_SNAPSHOT_UNSAFE:{model_id}")
        declared = entry.get("files", [])
        declared_names = {str(item["path"]) for item in declared}
        actual_names = {
            path.relative_to(snapshot).as_posix()
            for path in snapshot.rglob("*") if path.is_file()
        }
        if actual_names != declared_names | {"SHA256SUMS"}:
            raise Scale1BWaveRError(f"MODEL_FILE_SET_MISMATCH:{model_id}")
        expected_sums: list[str] = []
        for item in declared:
            path = snapshot / item["path"]
            if (
                not path.is_file() or path.is_symlink()
                or path.stat().st_size != int(item["bytes"])
                or _sha256(path) != item["sha256"]
            ):
                raise Scale1BWaveRError(
                    f"MODEL_FILE_INTEGRITY:{model_id}:{item['path']}"
                )
            expected_sums.append(f"{item['sha256']}  {item['path']}")
        sums = snapshot / "SHA256SUMS"
        if sums.read_text(encoding="utf-8").splitlines() != expected_sums:
            raise Scale1BWaveRError(f"MODEL_SHA256SUMS_MISMATCH:{model_id}")
        if stat.S_IMODE(snapshot.stat().st_mode) != 0o700 or any(
            stat.S_IMODE(path.stat().st_mode) != 0o600
            for path in snapshot.rglob("*") if path.is_file()
        ):
            raise Scale1BWaveRError(f"MODEL_PERMISSION_MISMATCH:{model_id}")
    return {
        "contract_sha256": _sha256(paths["contract"], prefixed=True),
        "model_manifest_sha256": _sha256(paths["models"], prefixed=True),
        "scale1a_audit_sha256": _sha256(paths["scale1a"], prefixed=True),
        "contract": contract,
        "models": models,
    }


def _find_model(
    repo_root: Path, manifest: Mapping[str, Any], *, kind: str
) -> tuple[Path, Mapping[str, Any]]:
    needle = "siglip" if kind == "siglip2" else "clap"
    candidates: list[Mapping[str, Any]] = []

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            text = json.dumps(value, sort_keys=True).lower()
            if needle in text and any(
                key in value for key in ("local_dir", "snapshot_dir", "path", "repo_id")
            ):
                candidates.append(value)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(manifest)
    expected_repo = (
        "google/siglip2-base-patch16-224"
        if kind == "siglip2" else "laion/clap-htsat-unfused"
    )
    expected_revision = (
        "75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2"
        if kind == "siglip2" else "8fa0f1c6d0433df6e97c127f64b2a1d6c0dcda8a"
    )
    for item in candidates:
        repo_id = item.get("repo_id") or item.get("repo")
        revision = item.get("revision") or item.get("commit")
        local = item.get("local_dir") or item.get("snapshot_dir") or item.get("path")
        if repo_id == expected_repo and revision == expected_revision and local:
            path = repo_root / str(local)
            if path.is_dir() and not path.is_symlink():
                return path, item
    planned = repo_root / (
        "data/restricted/scale1b/models/"
        + (
            "google--siglip2-base-patch16-224--75de2d55ec2d"
            if kind == "siglip2"
            else "laion--clap-htsat-unfused--8fa0f1c6d043"
        )
    )
    if planned.is_dir() and not planned.is_symlink():
        return planned, {
            "repo_id": expected_repo, "revision": expected_revision,
            "local_dir": planned.relative_to(repo_root).as_posix(),
        }
    raise Scale1BWaveRError(f"{kind.upper()}_SNAPSHOT_PATH_NOT_FOUND")


def _source_paths(repo_root: Path) -> dict[str, Path]:
    manifest = _load(repo_root / ACQUISITION_REL)
    root = repo_root / "data/restricted/noaa01"
    output = {}
    for item in manifest["assets"]:
        path = root / "raw" / item["basename"]
        if not path.is_file() or path.stat().st_size != item["size_bytes"]:
            raise Scale1BWaveRError(f"SOURCE_MISSING:{item['candidate_id']}")
        if _sha256(path) != item["sha256"]:
            raise Scale1BWaveRError(f"SOURCE_HASH_MISMATCH:{item['candidate_id']}")
        output[item["candidate_id"]] = path
    return output


def _f16_hex(vector: np.ndarray) -> str:
    return np.asarray(vector, dtype="<f2").tobytes().hex()


def _from_f16(value: str, dimension: int) -> np.ndarray:
    vector = np.frombuffer(bytes.fromhex(value), dtype="<f2").astype(np.float32)
    if len(vector) != dimension:
        raise Scale1BWaveRError("VECTOR_DIMENSION_MISMATCH")
    return vector


def _normalize(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float32)
    norms = np.linalg.norm(values, axis=-1, keepdims=True)
    if not np.isfinite(values).all() or np.any(norms <= 1e-12):
        raise Scale1BWaveRError("NONFINITE_OR_ZERO_VECTOR")
    return values / norms


def _pool(ids: Sequence[str], vectors: Mapping[str, np.ndarray]) -> np.ndarray:
    value = np.mean(np.stack([vectors[item] for item in ids]), axis=0)
    return _normalize(value[None, :])[0]


def _iter_frames(
    path: Path, cells: Sequence[Mapping[str, Any]]
) -> Iterator[tuple[Mapping[str, Any], np.ndarray]]:
    targets = [int(item["sample_time_us"]) for item in cells]
    cursor = 0
    previous = None
    with av.open(str(path), mode="r") as container:
        stream = next((x for x in container.streams if x.type == "video"), None)
        if stream is None:
            raise Scale1BWaveRError(f"VIDEO_STREAM_MISSING:{path.name}")
        for frame in container.decode(stream):
            if frame.pts is None:
                continue
            frame_us = int(round(float(frame.pts * frame.time_base) * 1_000_000))
            while cursor < len(targets) and frame_us >= targets[cursor]:
                chosen = previous or frame
                yield cells[cursor], chosen.to_ndarray(format="rgb24")
                cursor += 1
            if cursor == len(targets):
                break
            previous = frame
    while cursor < len(targets) and previous is not None:
        yield cells[cursor], previous.to_ndarray(format="rgb24")
        cursor += 1
    if cursor != len(targets):
        raise Scale1BWaveRError(f"FRAME_DECODE_INCOMPLETE:{path.name}")


def _decode_audio(path: Path, rate: int = 48_000) -> np.ndarray:
    parts: list[np.ndarray] = []
    with av.open(str(path), mode="r") as container:
        stream = next((x for x in container.streams if x.type == "audio"), None)
        if stream is None:
            raise Scale1BWaveRError(f"AUDIO_STREAM_MISSING:{path.name}")
        resampler = av.audio.resampler.AudioResampler(
            format="fltp", layout="mono", rate=rate
        )
        for frame in container.decode(stream):
            for converted in resampler.resample(frame):
                parts.append(converted.to_ndarray().reshape(-1).astype(np.float32))
        for converted in resampler.resample(None):
            parts.append(converted.to_ndarray().reshape(-1).astype(np.float32))
    if not parts:
        raise Scale1BWaveRError(f"AUDIO_DECODE_EMPTY:{path.name}")
    values = np.concatenate(parts)
    if not np.isfinite(values).all():
        raise Scale1BWaveRError(f"AUDIO_DECODE_NONFINITE:{path.name}")
    return values


def _slice_audio(
    values: np.ndarray, start_us: int, end_us: int, rate: int
) -> np.ndarray:
    left = max(0, round(start_us * rate / 1_000_000))
    right = min(len(values), round(end_us * rate / 1_000_000))
    expected = max(1, round((end_us - start_us) * rate / 1_000_000))
    result = values[left:right]
    if len(result) < expected:
        result = np.pad(result, (0, expected - len(result)))
    return result.astype(np.float32, copy=False)


def _torch_output(value: Any) -> Any:
    return value.pooler_output if hasattr(value, "pooler_output") else value


class _WaveRModels:
    def __init__(
        self, siglip_path: Path | None, clap_path: Path | None, *, threads: int
    ):
        if "long" not in np.__dict__:
            np.long = np.int64  # type: ignore[attr-defined]
        if "ulong" not in np.__dict__:
            np.ulong = np.uint64  # type: ignore[attr-defined]
        os.environ.update({
            "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
            "HF_DATASETS_OFFLINE": "1",
        })
        import torch
        from transformers import ClapModel, ClapProcessor
        torch.manual_seed(0)
        torch.use_deterministic_algorithms(True)
        torch.set_num_threads(max(1, threads))
        self.torch = torch
        self.siglip_processor = self.siglip_model = None
        self.clap_processor = self.clap_model = None
        if siglip_path is not None:
            config_type = _load(siglip_path / "config.json").get("model_type")
            if config_type == "siglip":
                from transformers import SiglipModel as SiglipRuntimeModel
                from transformers import SiglipProcessor as SiglipRuntimeProcessor
            elif config_type == "siglip2":
                from transformers import Siglip2Model as SiglipRuntimeModel
                from transformers import Siglip2Processor as SiglipRuntimeProcessor
            else:
                raise Scale1BWaveRError(
                    f"UNSUPPORTED_SIGLIP_CONFIG_TYPE:{config_type}"
                )
            self.siglip_processor = SiglipRuntimeProcessor.from_pretrained(
                siglip_path, local_files_only=True, use_fast=False
            )
            self.siglip_model = SiglipRuntimeModel.from_pretrained(
                siglip_path, local_files_only=True
            ).eval()
        if clap_path is not None:
            self.clap_processor = ClapProcessor.from_pretrained(
                clap_path, local_files_only=True
            )
            self.clap_model = ClapModel.from_pretrained(
                clap_path, local_files_only=True
            ).eval()

    def siglip_images(self, images: Sequence[np.ndarray]) -> np.ndarray:
        assert self.siglip_processor is not None and self.siglip_model is not None
        inputs = self.siglip_processor(images=list(images), return_tensors="pt")
        with self.torch.inference_mode():
            values = _torch_output(self.siglip_model.get_image_features(**inputs))
        return _normalize(values.float().cpu().numpy())

    def siglip_text(self, texts: Sequence[str]) -> np.ndarray:
        assert self.siglip_processor is not None and self.siglip_model is not None
        inputs = self.siglip_processor(
            text=list(texts), padding="max_length", truncation=True,
            return_tensors="pt",
        )
        with self.torch.inference_mode():
            values = _torch_output(self.siglip_model.get_text_features(**inputs))
        return _normalize(values.float().cpu().numpy())

    def clap_audio(self, audio: Sequence[np.ndarray], rate: int) -> np.ndarray:
        assert self.clap_processor is not None and self.clap_model is not None
        inputs = self.clap_processor(
            audio=list(audio), sampling_rate=rate, padding=True,
            return_tensors="pt",
        )
        with self.torch.inference_mode():
            values = _torch_output(self.clap_model.get_audio_features(
                input_features=inputs.input_features,
                is_longer=getattr(inputs, "is_longer", None),
                attention_mask=getattr(inputs, "attention_mask", None),
            ))
        return _normalize(values.float().cpu().numpy())

    def clap_text(self, texts: Sequence[str]) -> np.ndarray:
        assert self.clap_processor is not None and self.clap_model is not None
        inputs = self.clap_processor(
            text=list(texts), padding=True, truncation=True, return_tensors="pt"
        )
        with self.torch.inference_mode():
            values = _torch_output(self.clap_model.get_text_features(
                input_ids=inputs.input_ids,
                attention_mask=getattr(inputs, "attention_mask", None),
            ))
        return _normalize(values.float().cpu().numpy())


def _checkpoint_read(
    path: Path, *, config_hash: str, source_sha256: str
) -> Mapping[str, Any] | None:
    if not path.is_file() or path.is_symlink():
        return None
    document = _load(path)
    if (
        document.get("config_hash") != config_hash
        or document.get("source_sha256") != source_sha256
        or document.get("payload_hash") != _json_hash(document.get("payload"))
    ):
        return None
    return document


def _checkpoint_write(
    path: Path, *, config_hash: str, source_sha256: str,
    payload: Mapping[str, Any],
) -> Mapping[str, Any]:
    document = {
        "schema_version": SCHEMA, "config_hash": config_hash,
        "source_sha256": source_sha256, "payload": payload,
        "payload_hash": _json_hash(payload),
    }
    _dump(path, document)
    return document


def _contract_rrf(contract: Mapping[str, Any]) -> tuple[int, dict[str, float]]:
    # Task-101 contract is authoritative. Refuse learned calibration and only
    # accept an explicitly frozen RRF constant/weights.
    fusion = contract.get("experiment_contract", {}).get("fusion")
    if not isinstance(fusion, Mapping):
        raise Scale1BWaveRError("RRF_CONTRACT_MISSING")
    if fusion.get("learned") is not False or fusion.get(
        "logistic_fusion_enabled"
    ) is not False:
        raise Scale1BWaveRError("EVALUATION_TUNED_FUSION_FORBIDDEN")
    if fusion.get("type") != "weighted-rrf/1.0":
        raise Scale1BWaveRError("RRF_TYPE_NOT_FROZEN")
    weights = fusion.get("weights")
    if not isinstance(weights, Mapping):
        raise Scale1BWaveRError("RRF_WEIGHTS_NOT_FROZEN")
    return int(fusion["rrf_k"]), {str(k): float(v) for k, v in weights.items()}


def build_wave_r(
    repo_root: str | Path, *, resume: bool = True, threads: int = 8,
    siglip_batch: int = 8, clap_batch: int = 4,
    source_limit: Sequence[str] | None = None,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    gates = verify_gates(root)
    rrf_k, weights = _contract_rrf(gates["contract"])
    segment_manifest = _load(root / SCALE1A_ROOT_REL / "segment_manifest.json")
    if (
        segment_manifest["totals"]["base_cells"] != 3433
        or segment_manifest["totals"]["fine_windows"] != 3428
        or segment_manifest["totals"]["context_windows"] != 855
    ):
        raise Scale1BWaveRError("FROZEN_TIMELINE_COUNT_MISMATCH")
    sources = _source_paths(root)
    siglip_path, siglip_info = _find_model(
        root, gates["models"], kind="siglip2"
    )
    clap_path, clap_info = _find_model(root, gates["models"], kind="clap")
    clap_rate = int(_load(clap_path / "preprocessor_config.json")["sampling_rate"])
    selected = sorted(source_limit or sources)
    if any(x not in sources for x in selected):
        raise Scale1BWaveRError("UNKNOWN_SOURCE_LIMIT")
    config = {
        "segment_manifest_hash": segment_manifest["segment_manifest_hash"],
        "gate_hashes": {
            key: gates[key] for key in (
                "contract_sha256", "model_manifest_sha256",
                "scale1a_audit_sha256",
            )
        },
        "models": {
            "siglip2": {
                "repo_id": "google/siglip2-base-patch16-224",
                "revision": "75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2",
                "snapshot": siglip_info.get("local_dir")
                or siglip_path.relative_to(root).as_posix(),
            },
            "clap": {
                "repo_id": "laion/clap-htsat-unfused",
                "revision": "8fa0f1c6d0433df6e97c127f64b2a1d6c0dcda8a",
                "snapshot": clap_info.get("local_dir")
                or clap_path.relative_to(root).as_posix(),
            },
        },
        "siglip": {
            "batch": siglip_batch, "sample": "frozen_base_cell_sample_time",
            "persist_dtype": "float16", "score_dtype": "float32",
            "pooling": "normalized_mean_of_bound_base_cell_vectors",
        },
        "clap": {
            "batch": clap_batch, "sample_rate": clap_rate,
            "fine_input": "exact_frozen_fine_window",
            "persist_dtype": "float16", "score_dtype": "float32",
            "context_pooling": "normalized_mean_of_overlapping_fine_vectors",
        },
        "rrf": {"rrf_k": rrf_k, "weights": weights},
        "threads": threads,
    }
    config_hash = _json_hash(config)
    restricted = root / RESTRICTED_REL
    checkpoints_root = restricted / "checkpoints"
    checkpoints_root.mkdir(parents=True, exist_ok=True)
    checkpoints_root.chmod(0o700)
    checkpoint_rows: list[dict[str, Any]] = []
    all_siglip: list[dict[str, Any]] = []
    all_clap: list[dict[str, Any]] = []
    perf: list[dict[str, Any]] = []
    resource_path = restricted / "resource_measurements.json"
    prior_performance: list[dict[str, Any]] = []
    if resource_path.is_file():
        prior_performance = list(_load(resource_path).get("records", []))
    elif (restricted / "observation_manifest.json").is_file():
        # One-time migration from the initial implementation, which embedded
        # non-deterministic timings in the observation manifest.
        prior_performance = list(
            _load(restricted / "observation_manifest.json").get("performance", [])
        )

    for source_ref in selected:
        source = next(x for x in segment_manifest["sources"] if x["source_ref"] == source_ref)
        cells = [x for x in segment_manifest["base_cells"] if x["source_ref"] == source_ref]
        segments = [x for x in segment_manifest["segments"] if x["source_ref"] == source_ref]
        fine = [x for x in segments if x["scale"] == "fine"]
        context = [x for x in segments if x["scale"] == "context"]
        source_path = sources[source_ref]

        vision_path = checkpoints_root / source_ref / "siglip2.json"
        vision_doc = (
            _checkpoint_read(
                vision_path, config_hash=config_hash,
                source_sha256=source["sha256"],
            ) if resume else None
        )
        # The first implementation pass used the Transformers 5.x implicit
        # fast image processor. Task-101 freezes the pinned processor behavior
        # and Task-102 validated the slow processor, so checkpoints lacking
        # this explicit binding are invalidated without touching CLAP shards.
        if vision_doc is not None and (
            vision_doc.get("payload", {}).get("processor_use_fast") is not False
        ):
            vision_doc = None
        if vision_doc is None:
            started = time.perf_counter()
            models = _WaveRModels(siglip_path, None, threads=threads)
            records: list[dict[str, Any]] = []
            batch_images: list[np.ndarray] = []
            batch_cells: list[Mapping[str, Any]] = []

            def flush() -> None:
                if not batch_images:
                    return
                vectors = models.siglip_images(batch_images)
                for cell, vector in zip(batch_cells, vectors):
                    records.append({
                        "cell_id": cell["cell_id"],
                        "vector_f16_hex": _f16_hex(vector),
                        "dimension": len(vector), "l2_normalized": True,
                    })
                batch_images.clear()
                batch_cells.clear()

            for cell, frame in _iter_frames(source_path, cells):
                batch_images.append(frame)
                batch_cells.append(cell)
                if len(batch_images) >= siglip_batch:
                    flush()
            flush()
            by_cell = {
                x["cell_id"]: _from_f16(x["vector_f16_hex"], x["dimension"])
                for x in records
            }
            segment_records = [{
                "segment_id": segment["segment_id"],
                "source_ref": source_ref, "scale": segment["scale"],
                "start_us": segment["start_us"], "end_us": segment["end_us"],
                "modality": "vision", "searchable": True,
                "vector_f16_hex": _f16_hex(_pool(
                    segment["binding_cell_ids"], by_cell
                )),
                "dimension": records[0]["dimension"],
            } for segment in segments]
            payload = {
                "layer": "siglip2_visual", "actual_learned_model": True,
                "model_revision": config["models"]["siglip2"]["revision"],
                "processor_use_fast": False,
                "cell_vectors": records, "segment_records": segment_records,
                "no_persisted_frames": True,
            }
            vision_doc = _checkpoint_write(
                vision_path, config_hash=config_hash,
                source_sha256=source["sha256"], payload=payload,
            )
            perf.append({
                "layer": "siglip2_visual", "source_ref": source_ref,
                "elapsed_seconds": round(time.perf_counter() - started, 6),
                "items": len(cells), "reused": False,
                "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            })
        else:
            perf.append({
                "layer": "siglip2_visual", "source_ref": source_ref,
                "elapsed_seconds": 0.0, "items": len(cells), "reused": True,
                "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            })
        all_siglip.extend(vision_doc["payload"]["segment_records"])
        checkpoint_rows.append({
            "layer": "siglip2_visual", "source_ref": source_ref,
            "path": vision_path.relative_to(root).as_posix(),
            "sha256": _sha256(vision_path, prefixed=True),
            "size_bytes": vision_path.stat().st_size,
            "payload_hash": vision_doc["payload_hash"], "reused": perf[-1]["reused"],
        })

        audio_path = checkpoints_root / source_ref / "clap.json"
        audio_doc = (
            _checkpoint_read(
                audio_path, config_hash=config_hash,
                source_sha256=source["sha256"],
            ) if resume else None
        )
        if audio_doc is None:
            started = time.perf_counter()
            models = _WaveRModels(None, clap_path, threads=threads)
            rate = int(config["clap"]["sample_rate"])
            waveform = _decode_audio(source_path, rate)
            fine_records: list[dict[str, Any]] = []
            for offset in range(0, len(fine), clap_batch):
                specs = fine[offset:offset + clap_batch]
                slices = [
                    _slice_audio(waveform, x["start_us"], x["end_us"], rate)
                    for x in specs
                ]
                vectors = models.clap_audio(slices, rate)
                for segment, samples, vector in zip(specs, slices, vectors):
                    rms = float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))
                    fine_records.append({
                        "segment_id": segment["segment_id"],
                        "source_ref": source_ref, "scale": "fine",
                        "start_us": segment["start_us"], "end_us": segment["end_us"],
                        "modality": "audio", "searchable": True,
                        "vector_f16_hex": _f16_hex(vector), "dimension": len(vector),
                        "audio_rms_full_scale": round(rms, 10),
                        "silent": rms < 1e-5, "decode_valid": True,
                        "quality_flags": ["NEAR_SILENCE"] if rms < 1e-5 else [],
                    })
            by_fine = {
                x["segment_id"]: _from_f16(x["vector_f16_hex"], x["dimension"])
                for x in fine_records
            }
            context_records = []
            for segment in context:
                overlap = [
                    x["segment_id"] for x in fine
                    if x["start_us"] < segment["end_us"]
                    and x["end_us"] > segment["start_us"]
                ]
                vector = _normalize(
                    np.mean(np.stack([by_fine[x] for x in overlap]), axis=0)[None, :]
                )[0]
                members = [x for x in fine_records if x["segment_id"] in overlap]
                context_records.append({
                    "segment_id": segment["segment_id"],
                    "source_ref": source_ref, "scale": "context",
                    "start_us": segment["start_us"], "end_us": segment["end_us"],
                    "modality": "audio", "searchable": True,
                    "vector_f16_hex": _f16_hex(vector),
                    "dimension": fine_records[0]["dimension"],
                    "derived_from_fine_ids": overlap,
                    "silent": all(x["silent"] for x in members),
                    "decode_valid": all(x["decode_valid"] for x in members),
                    "quality_flags": (
                        ["ALL_MEMBERS_NEAR_SILENCE"]
                        if all(x["silent"] for x in members) else []
                    ),
                })
            payload = {
                "layer": "clap_audio", "actual_learned_model": True,
                "model_revision": config["models"]["clap"]["revision"],
                "sample_rate": rate, "fine_records": fine_records,
                "context_records": context_records,
                "no_persisted_waveforms": True,
            }
            audio_doc = _checkpoint_write(
                audio_path, config_hash=config_hash,
                source_sha256=source["sha256"], payload=payload,
            )
            del waveform
            perf.append({
                "layer": "clap_audio", "source_ref": source_ref,
                "elapsed_seconds": round(time.perf_counter() - started, 6),
                "items": len(fine), "reused": False,
                "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            })
        else:
            perf.append({
                "layer": "clap_audio", "source_ref": source_ref,
                "elapsed_seconds": 0.0, "items": len(fine), "reused": True,
                "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            })
        all_clap.extend(audio_doc["payload"]["fine_records"])
        all_clap.extend(audio_doc["payload"]["context_records"])
        checkpoint_rows.append({
            "layer": "clap_audio", "source_ref": source_ref,
            "path": audio_path.relative_to(root).as_posix(),
            "sha256": _sha256(audio_path, prefixed=True),
            "size_bytes": audio_path.stat().st_size,
            "payload_hash": audio_doc["payload_hash"], "reused": perf[-1]["reused"],
        })

    complete = len(selected) == 5
    stable_performance = {
        (str(item["layer"]), str(item["source_ref"])): {
            key: value for key, value in item.items() if key != "reused"
        }
        for item in prior_performance
    }
    for item in perf:
        key = (str(item["layer"]), str(item["source_ref"]))
        if not item["reused"] or key not in stable_performance:
            stable = {
                field: value for field, value in item.items() if field != "reused"
            }
            stable["items_per_second"] = round(
                float(stable["items"]) / max(float(stable["elapsed_seconds"]), 1e-12),
                6,
            )
            stable_performance[key] = stable
    for stable in stable_performance.values():
        if "items_per_second" not in stable:
            stable["items_per_second"] = round(
                float(stable["items"]) / max(float(stable["elapsed_seconds"]), 1e-12),
                6,
            )
    resource_document = {
        "schema_version": SCHEMA,
        "records": [stable_performance[key] for key in sorted(stable_performance)],
        "measurement_policy": "first completed full-inference measurement retained across resume",
    }
    resource_document["resource_measurements_hash"] = _json_hash(resource_document)
    _dump(resource_path, resource_document)
    observation = {
        "schema_version": SCHEMA, "stage": STAGE, "restricted": True,
        "human_reviewed": False, "gold_annotation": False,
        "learned_model_evaluation": True,
        "timeline": {
            "segment_manifest_hash": segment_manifest["segment_manifest_hash"],
            "base_cells": len(segment_manifest["base_cells"]),
            "fine_windows": segment_manifest["totals"]["fine_windows"],
            "context_windows": segment_manifest["totals"]["context_windows"],
            "unchanged_ids_and_intervals": True,
        },
        "config": config, "config_hash": config_hash,
        "runtime_model_classes": {
            model_id: {
                "model_class": gates["models"]["models"][model_id][
                    "offline_smoke"
                ]["model_class"],
                "processor_class": gates["models"]["models"][model_id][
                    "offline_smoke"
                ]["processor_class"],
                "embedding_dimension": gates["models"]["models"][model_id][
                    "offline_smoke"
                ]["embedding_dimension"],
            }
            for model_id in ("siglip2", "clap")
        },
        "counts": {
            "siglip2_cells": sum(
                1 for s in segment_manifest["base_cells"]
                if s["source_ref"] in selected
            ),
            "siglip2_segment_vectors": len(all_siglip),
            "clap_fine_vectors": sum(x["scale"] == "fine" for x in all_clap),
            "clap_context_vectors": sum(x["scale"] == "context" for x in all_clap),
            "clap_silent_segments": sum(bool(x["silent"]) for x in all_clap),
            "clap_invalid_segments": sum(not bool(x["decode_valid"]) for x in all_clap),
        },
        "resource_measurements_hash": resource_document["resource_measurements_hash"],
        "complete_source_refs": selected,
        "all_five_complete": complete,
        "no_persisted_media_derivatives": True,
    }
    observation["observation_manifest_hash"] = _json_hash(observation)
    checkpoint_manifest = {
        "schema_version": SCHEMA, "config_hash": config_hash,
        "checkpoints": checkpoint_rows,
        "complete": complete and len(checkpoint_rows) == 10,
    }
    checkpoint_manifest["checkpoint_manifest_hash"] = _json_hash(checkpoint_manifest)
    index = {
        "schema_version": SCHEMA, "stage": STAGE, "restricted": True,
        "learned_model_evaluation": True,
        "timeline_hash": segment_manifest["segment_manifest_hash"],
        "observation_manifest_hash": observation["observation_manifest_hash"],
        "searchable_field_policy": {
            "forbidden_keys": sorted(FORBIDDEN_SEARCH_KEYS),
            "evaluation_annotations_excluded": True,
        },
        "rankers": {
            "siglip2_visual": {
                "type": "learned_cosine", "score_dtype": "float32",
                "model_revision": config["models"]["siglip2"]["revision"],
            },
            "clap_audio": {
                "type": "learned_cosine", "score_dtype": "float32",
                "model_revision": config["models"]["clap"]["revision"],
            },
            "wave_r_rrf": {
                "type": "fixed_non_learned_rrf", "learned": False,
                "rrf_k": rrf_k, "weights": weights,
                "evaluation_family_tuning": False,
            },
        },
        "modalities": {
            "siglip2_visual": {"documents": all_siglip},
            "clap_audio": {"documents": all_clap},
        },
        "counts": {
            "siglip2_visual": len(all_siglip), "clap_audio": len(all_clap),
        },
    }
    _assert_safe_index(index)
    index["index_hash"] = _json_hash(index)
    _dump(restricted / "observation_manifest.json", observation)
    _dump(restricted / "checkpoint_manifest.json", checkpoint_manifest)
    _dump(restricted / "learned_index.json", index)
    build_manifest = {
        "schema_version": SCHEMA, "stage": STAGE,
        "config_hash": config_hash,
        "observation_manifest_hash": observation["observation_manifest_hash"],
        "checkpoint_manifest_hash": checkpoint_manifest["checkpoint_manifest_hash"],
        "learned_index_hash": index["index_hash"],
        "resource_measurements_hash": resource_document["resource_measurements_hash"],
        "implementation_hashes": {
            rel.as_posix(): _sha256(root / rel, prefixed=True)
            for rel in (
                Path("src/av_trace_scale1b_retrieval/__init__.py"),
                Path("src/av_trace_scale1b_retrieval/core.py"),
                Path("scripts/build_scale1b_wave_r.py"),
                Path("scripts/audit_scale1b_wave_r.py"),
                Path("scripts/profile_scale1b_wave_r_model.py"),
                Path("scripts/run_scale1b_wave_r.py"),
                Path("scripts/verify_scale1b_wave_r.py"),
                Path("tests_scale1b/test_wave_r.py"),
            )
        },
        "source_refs": selected,
        "source_bindings": [
            {
                "source_ref": source["source_ref"],
                "sha256": source["sha256"],
                "size_bytes": source["size_bytes"],
            }
            for source in segment_manifest["sources"]
            if source["source_ref"] in selected
        ],
        "runtime": {
            "python": platform.python_version(), "numpy": _version("numpy"),
            "torch": _version("torch"), "transformers": _version("transformers"),
            "pyav": _version("av"),
        },
        "decisions": {
            "visual": "LEARNED_VISUAL_RETRIEVAL_READY" if complete else
            "LEARNED_VISUAL_RETRIEVAL_NO_GO",
            "audio": "LEARNED_AUDIO_RETRIEVAL_READY" if complete else
            "LEARNED_AUDIO_RETRIEVAL_NO_GO",
            "retrieval": "LEARNED_RETRIEVAL_READY" if complete else
            "LEARNED_RETRIEVAL_INCOMPLETE",
            "final_benchmark": FINAL_STATUS,
        },
    }
    build_manifest["build_manifest_hash"] = _json_hash(build_manifest)
    _dump(restricted / "build_manifest.json", build_manifest)
    return build_manifest


def _assert_safe_index(index: Mapping[str, Any]) -> None:
    def visit(value: Any, path: tuple[str, ...] = ()) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                if key in FORBIDDEN_SEARCH_KEYS and "searchable_field_policy" not in path:
                    raise Scale1BWaveRError(f"SEARCHABLE_FIELD_LEAKAGE:{key}")
                visit(child, (*path, str(key)))
        elif isinstance(value, list):
            for child in value:
                visit(child, path)
    for modality in index.get("modalities", {}).values():
        visit(modality)


def _rank_vectors(
    documents: Sequence[Mapping[str, Any]], query: np.ndarray,
    *, source_ref: str | None, suppressed: set[str] | None = None,
) -> list[dict[str, Any]]:
    suppressed = suppressed or set()
    rows = []
    for document in documents:
        if source_ref is not None and document["source_ref"] != source_ref:
            continue
        if document["segment_id"] in suppressed or not document.get("searchable", True):
            continue
        vector = _from_f16(document["vector_f16_hex"], int(document["dimension"]))
        score = float(np.dot(vector.astype(np.float32), query.astype(np.float32)))
        rows.append({
            "segment_id": document["segment_id"],
            "source_ref": document["source_ref"], "scale": document["scale"],
            "start_us": document["start_us"], "end_us": document["end_us"],
            "score": score,
        })
    rows.sort(key=lambda x: (
        -x["score"], x["source_ref"], x["start_us"], x["end_us"], x["segment_id"]
    ))
    return rows


def _control_rankings(
    root: Path, family_id: str, scope: str
) -> dict[str, list[str]]:
    suite = _load(root / SCALE1A_ROOT_REL / "fixed_query_suite.json")
    row = next(
        (x for x in suite["rows"] if x["family_id"] == family_id
         and x["scope"] == scope), None
    )
    return row["rankings"] if row else {}


def _control_direct_rankings(
    root: Path, scale1a_index: Mapping[str, Any],
    family: Mapping[str, Any], scope: str,
) -> tuple[dict[str, list[str]], dict[str, list[dict[str, Any]]]]:
    """Recompute exact Task-101 direct controls from frozen Scale-1A data."""
    from av_trace_scale1a.core import (
        _cached_clip_text, search_ambient, search_speech, search_visual,
    )

    source_ref = family["asset_id"] if scope == "source_scoped" else None
    ids: dict[str, list[str]] = {}
    records: dict[str, list[dict[str, Any]]] = {}
    queries = family["query_families"]
    if "vision" in family["provisional_modalities"]:
        query = queries[0]
        vector = _cached_clip_text(root, [query], threads=8)[0]
        rows = search_visual(
            root, scale1a_index, query, top_k=20, source_ref=source_ref,
            text_vector=vector,
        )
        ids["V-CLIP"] = [x["segment_id"] for x in rows]
        records["V-CLIP"] = rows
    if "ambient" in family["provisional_modalities"]:
        query = queries[min(1, len(queries) - 1)]
        rows = search_ambient(
            scale1a_index, query, top_k=20, source_ref=source_ref
        )
        ids["A-AST"] = [x["segment_id"] for x in rows]
        records["A-AST"] = rows
    if "speech" in family["provisional_modalities"]:
        query = queries[0]
        rows = search_speech(
            scale1a_index, query, top_k=20, source_ref=source_ref
        )
        ids["S-BM25"] = [x["segment_id"] for x in rows]
        records["S-BM25"] = rows
    return ids, records


def _temporal_bind_visual(
    visual_ranking: Sequence[Mapping[str, Any]],
    anchor_rankings: Mapping[str, Sequence[Mapping[str, Any]]],
    visual_documents: Sequence[Mapping[str, Any]], *,
    source_ref: str | None,
) -> list[dict[str, Any]]:
    """Frozen Scale-1A label-independent temporal-binding adapter."""
    available = [
        item for item in visual_documents
        if source_ref is None or item["source_ref"] == source_ref
    ]
    anchors: list[tuple[int, str, Mapping[str, Any]]] = []
    for modality in ("speech", "ambient"):
        for rank, item in enumerate(anchor_rankings.get(modality, ())[:20], 1):
            anchors.append((rank, modality, item))
    anchors.sort(key=lambda x: (
        x[0], x[1], x[2]["source_ref"], x[2]["start_us"],
        x[2]["end_us"], x[2]["segment_id"],
    ))
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for anchor_rank, anchor_modality, anchor in anchors:
        candidates = [
            item for item in available
            if item["source_ref"] == anchor["source_ref"]
            and item["start_us"] < anchor["end_us"]
            and item["end_us"] > anchor["start_us"]
        ]
        candidates.sort(key=lambda item: (
            item["scale"] != "fine",
            -max(0, min(item["end_us"], anchor["end_us"]) -
                 max(item["start_us"], anchor["start_us"]))
            / max(item["end_us"], anchor["end_us"]),
            item["source_ref"], item["start_us"], item["end_us"],
            item["segment_id"],
        ))
        if candidates and candidates[0]["segment_id"] not in seen:
            selected = dict(candidates[0])
            selected["_binding_modality"] = anchor_modality
            selected["_binding_rank"] = anchor_rank
            output.append(selected)
            seen.add(selected["segment_id"])
    for item in visual_ranking:
        if item["segment_id"] not in seen:
            output.append(dict(item))
            seen.add(item["segment_id"])
    return output[:20]


def _rrf(
    rankings: Mapping[str, Sequence[str]], *, rrf_k: int,
    weights: Mapping[str, float],
) -> list[str]:
    return _rrf_details(rankings, rrf_k=rrf_k, weights=weights)[0]


def _rrf_details(
    rankings: Mapping[str, Sequence[str]], *, rrf_k: int,
    weights: Mapping[str, float],
) -> tuple[list[str], dict[str, set[str]]]:
    scores: dict[str, float] = defaultdict(float)
    contributions: dict[str, set[str]] = defaultdict(set)
    for modality, ranking in rankings.items():
        weight = float(weights.get(modality, weights.get(
            "audio" if modality == "ambient" else modality, 1.0
        )))
        for rank, segment_id in enumerate(ranking[:20], 1):
            scores[segment_id] += weight / (rrf_k + rank)
            contributions[segment_id].add(modality)
    return (
        sorted(scores, key=lambda x: (-scores[x], x)),
        {key: set(value) for key, value in contributions.items()},
    )


def _temporal_group(record: Mapping[str, Any]) -> tuple[str, int, int]:
    return (
        str(record["source_ref"]),
        int(record["start_us"]) // 4_000_000,
        (int(record["end_us"]) - 1) // 4_000_000,
    )


def _opaque_result_id(ranker: str, segment_id: str) -> str:
    return "wr." + hashlib.sha256(
        f"{ranker}:{segment_id}".encode()
    ).hexdigest()[:20]


def _serialized_ranking(
    ranker: str, ranking: Sequence[str],
    contributions: Mapping[str, set[str]] | None,
) -> dict[str, Any]:
    """Persist opaque public-facing IDs alongside restricted evaluator IDs."""
    top = list(ranking[:20])
    return {
        "ranking_top20": [_opaque_result_id(ranker, item) for item in top],
        "evaluator_private_ranking_segment_ids": top,
        "fused_contributions": (
            {
                _opaque_result_id(ranker, item): sorted(
                    contributions.get(item, set())
                )
                for item in top
            }
            if contributions is not None else None
        ),
        "evaluator_private_fused_contributions": (
            {
                item: sorted(contributions.get(item, set()))
                for item in top
            }
            if contributions is not None else None
        ),
    }


def _rrf_record_details(
    rankings: Mapping[str, Sequence[Mapping[str, Any]]], *, rrf_k: int,
    weights: Mapping[str, float],
) -> tuple[list[str], dict[str, set[str]]]:
    """Scale-1A-compatible RRF with temporal-group deduplication.

    The representative segment is chosen only from ranker-visible metadata and
    the frozen tie break. Contributions explicitly track which modality made
    a fused result eligible for a support unit.
    """
    nonempty = {key: list(value) for key, value in rankings.items() if value}
    if len(nonempty) == 1:
        modality, values = next(iter(nonempty.items()))
        ranking = [str(item["segment_id"]) for item in values[:20]]
        return ranking, {item: {modality} for item in ranking}
    scores: dict[tuple[str, int, int], float] = defaultdict(float)
    representatives: dict[tuple[str, int, int], Mapping[str, Any]] = {}
    modalities: dict[tuple[str, int, int], set[str]] = defaultdict(set)
    for modality, ranking in nonempty.items():
        weight = float(weights.get(modality, 1.0))
        for rank, record in enumerate(ranking[:20], 1):
            key = _temporal_group(record)
            scores[key] += weight / (rrf_k + rank)
            modalities[key].add(modality)
            current = representatives.get(key)
            tie = (
                record["source_ref"], record["start_us"], record["end_us"],
                record["segment_id"], modality,
            )
            if current is None:
                representatives[key] = {**record, "_tie_modality": modality}
            else:
                old_tie = (
                    current["source_ref"], current["start_us"], current["end_us"],
                    current["segment_id"], current["_tie_modality"],
                )
                if tie < old_tie:
                    representatives[key] = {**record, "_tie_modality": modality}
    keys = sorted(
        scores,
        key=lambda key: (
            -scores[key], representatives[key]["source_ref"],
            representatives[key]["start_us"], representatives[key]["end_us"],
            representatives[key]["segment_id"],
            representatives[key]["_tie_modality"],
        ),
    )
    ranking = [str(representatives[key]["segment_id"]) for key in keys]
    contribution = {
        str(representatives[key]["segment_id"]): set(modalities[key])
        for key in keys
    }
    return ranking, contribution


def _supports(family: Mapping[str, Any]) -> dict[str, set[str]]:
    return {
        modality: set(ids)
        for modality, ids in family.get("support_segment_ids", {}).items()
    }


def _metrics(
    ranking: Sequence[str], support_groups: Mapping[str, set[str]], *,
    contributions: Mapping[str, set[str]] | None = None,
) -> dict[str, Any]:
    eligible = {k: v for k, v in support_groups.items() if v}
    first_by_group: dict[str, int | None] = {}
    for modality, ids in eligible.items():
        first_by_group[modality] = next(
            (
                rank for rank, item in enumerate(ranking[:20], 1)
                if item in ids and (
                    contributions is None
                    or modality in contributions.get(item, set())
                )
            ),
            None,
        )
    nonnull = [rank for rank in first_by_group.values() if rank is not None]
    first = min(nonnull) if nonnull else None
    output: dict[str, Any] = {
        "eligible_support_groups": len(eligible),
        "first_accepted_evidence_rank": first,
        "MRR": (
            sum(1.0 / rank if rank is not None else 0.0
                for rank in first_by_group.values()) / len(eligible)
            if eligible else None
        ),
        "modality_necessity": None,
    }
    for k in TOP_KS:
        hit_ranks = [
            rank for rank in first_by_group.values()
            if rank is not None and rank <= k
        ]
        hits = len(hit_ranks)
        output[f"Recall@{k}"] = hits / len(eligible) if eligible else None
        output[f"All-Evidence@{k}"] = (
            float(hits == len(eligible)) if eligible else None
        )
        ideal_count = min(len(eligible), k)
        ideal = sum(1 / math.log2(i + 1) for i in range(1, ideal_count + 1))
        dcg = sum(1 / math.log2(rank + 1) for rank in hit_ranks)
        output[f"nDCG@{k}"] = dcg / ideal if ideal else None
    return output


def _metrics_from_route_ranks(
    route_ranks: Mapping[str, int | None],
) -> dict[str, Any]:
    eligible = dict(route_ranks)
    present = [rank for rank in eligible.values() if rank is not None]
    first = min(present) if present else None
    output: dict[str, Any] = {
        "eligible_support_groups": len(eligible),
        "first_accepted_evidence_rank": first,
        "MRR": (
            sum(1.0 / rank if rank is not None else 0.0
                for rank in eligible.values()) / len(eligible)
            if eligible else None
        ),
        "modality_necessity": None,
    }
    for k in TOP_KS:
        hit_ranks = [
            rank for rank in eligible.values()
            if rank is not None and rank <= k
        ]
        hits = len(hit_ranks)
        output[f"Recall@{k}"] = hits / len(eligible) if eligible else None
        output[f"All-Evidence@{k}"] = (
            float(hits == len(eligible)) if eligible else None
        )
        ideal = sum(
            1 / math.log2(i + 1)
            for i in range(1, min(len(eligible), k) + 1)
        )
        dcg = sum(1 / math.log2(rank + 1) for rank in hit_ranks)
        output[f"nDCG@{k}"] = dcg / ideal if ideal else None
    return output


def _displace_to_outside_top5(
    ranking: Sequence[str], support_ids: set[str],
    validated_negative_ids: Sequence[str],
) -> list[str]:
    """Insert only validated negatives and move support below rank five."""
    if not validated_negative_ids or not support_ids:
        return list(ranking)
    clean = [
        item for item in ranking
        if item not in validated_negative_ids and item not in support_ids
    ]
    prefix = list(validated_negative_ids[:5])
    support = [item for item in ranking if item in support_ids]
    output = prefix + clean[: max(0, 5 - len(prefix))] + support + clean[
        max(0, 5 - len(prefix)):
    ]
    seen: set[str] = set()
    return [x for x in output if not (x in seen or seen.add(x))]


def _add_source_to_cross_deltas(
    paired: list[dict[str, Any]],
) -> None:
    by_key = {
        (row["comparison"], row["family_id"], row["scope"]): row
        for row in paired
    }
    metric_names = sorted({
        key.removeprefix("delta_")
        for row in paired for key in row if key.startswith("delta_")
    })
    for row in paired:
        if row["scope"] != "cross_source":
            continue
        source = by_key.get(
            (row["comparison"], row["family_id"], "source_scoped")
        )
        for metric in metric_names:
            cross_value = row.get(f"delta_{metric}")
            source_value = source.get(f"delta_{metric}") if source else None
            row[f"source_to_cross_delta_change_{metric}"] = (
                float(cross_value) - float(source_value)
                if cross_value is not None and source_value is not None else None
            )


def _mean(values: Sequence[float | None]) -> float | None:
    clean = [float(x) for x in values if x is not None]
    return sum(clean) / len(clean) if clean else None


def _rank_benchmark(
    documents: Sequence[Mapping[str, Any]], query: np.ndarray, *,
    source_ref: str | None, repeats: int = 6,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    outputs: list[list[dict[str, Any]]] = []
    timings: list[float] = []
    for _ in range(repeats):
        tick = time.perf_counter()
        output = _rank_vectors(documents, query, source_ref=source_ref)
        timings.append(time.perf_counter() - tick)
        outputs.append(output)
    identities = [
        [row["segment_id"] for row in output[:20]] for output in outputs
    ]
    if any(value != identities[0] for value in identities[1:]):
        raise Scale1BWaveRError("RANKING_REPLAY_MISMATCH")
    warm = sorted(timings[1:])
    return outputs[0], {
        "cold_ranking_seconds": round(timings[0], 8),
        "warm_median_ranking_seconds": round(warm[len(warm) // 2], 8),
        "warm_p95_ranking_seconds": round(warm[-1], 8),
        "warm_repeats": repeats - 1,
        "ranking_replay_exact": True,
    }


def _candidate_universe_count(
    ranker: str, family: Mapping[str, Any], scope: str,
    learned_index: Mapping[str, Any], scale1a_index: Mapping[str, Any],
) -> int:
    source_ref = family["asset_id"] if scope == "source_scoped" else None
    if ranker == "V-SIGLIP2":
        docs = learned_index["modalities"]["siglip2_visual"]["documents"]
    elif ranker == "A-CLAP":
        docs = learned_index["modalities"]["clap_audio"]["documents"]
    elif ranker == "V-CLIP":
        docs = scale1a_index["modalities"]["vision"]["documents"]
    elif ranker == "A-AST":
        docs = scale1a_index["modalities"]["ambient"]["documents"]
    elif ranker == "S-BM25":
        docs = scale1a_index["modalities"]["speech"]["documents"]
    elif family["provisional_modalities"] == ["speech"]:
        docs = scale1a_index["modalities"]["speech"]["documents"]
    else:
        docs = learned_index["modalities"]["siglip2_visual"]["documents"]
    return sum(
        source_ref is None or item["source_ref"] == source_ref for item in docs
    )


def run_wave_r(repo_root: str | Path) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    gates = verify_gates(root)
    rrf_k, weights = _contract_rrf(gates["contract"])
    restricted = root / RESTRICTED_REL
    index = _load(restricted / "learned_index.json")
    build = _load(restricted / "build_manifest.json")
    if build["decisions"]["retrieval"] != "LEARNED_RETRIEVAL_READY":
        raise Scale1BWaveRError("LEARNED_INDEX_NOT_READY")
    families_doc = _load(root / SCALE1A_ROOT_REL / "migrated_families.json")
    families = families_doc["families"]
    siglip_path, _ = _find_model(root, gates["models"], kind="siglip2")
    clap_path, _ = _find_model(root, gates["models"], kind="clap")
    models = _WaveRModels(siglip_path, clap_path, threads=8)
    queries = sorted({
        query for family in families for query in family["query_families"]
    })
    query_benchmarks: list[dict[str, Any]] = []
    siglip_queries: dict[str, np.ndarray] = {}
    clap_queries: dict[str, np.ndarray] = {}
    for model_name, function, target in (
        ("siglip2", models.siglip_text, siglip_queries),
        ("clap", models.clap_text, clap_queries),
    ):
        for query in queries:
            timings: list[float] = []
            vectors: list[np.ndarray] = []
            for _ in range(6):
                tick = time.perf_counter()
                vectors.append(function([query])[0])
                timings.append(time.perf_counter() - tick)
            target[query] = vectors[0]
            replay_delta = max(
                float(np.max(np.abs(vectors[0] - vector)))
                for vector in vectors[1:]
            )
            if replay_delta > 1e-6:
                raise Scale1BWaveRError(
                    f"QUERY_EMBEDDING_NONDETERMINISTIC:{model_name}:{query}"
                )
            warm = sorted(timings[1:])
            query_benchmarks.append({
                "model": model_name, "query": query,
                "cold_embedding_seconds": round(timings[0], 8),
                "warm_median_embedding_seconds": round(warm[len(warm) // 2], 8),
                "warm_p95_embedding_seconds": round(warm[-1], 8),
                "warm_repeats": 5, "replay_max_abs_delta": replay_delta,
            })
    documents = index["modalities"]
    scale1a_index = _load(root / SCALE1A_ROOT_REL / "full_timeline_index.json")
    run_rows: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    ranking_benchmarks: list[dict[str, Any]] = []
    comparison_rows = gates["contract"]["experiment_contract"]["comparison_rows"]
    comparison_by_id = {x["row_id"]: x for x in comparison_rows}
    frozen_control_rows = {
        (x["family_id"], x["scope"], x["row_id"]): x
        for x in gates["contract"]["wave_r_direct_control_preflight"]["rows"]
    }
    hard_negative_doc = _load(root / SCALE1A_ROOT_REL / "hard_negatives.json")
    intervention_doc = _load(root / SCALE1A_ROOT_REL / "interventions.json")
    intervention_by_family = {
        row["family_id"]: row for row in intervention_doc["families"]
    }
    validated_negatives = {
        row["family_id"]: [
            item["segment_id"] for item in row.get("admitted", [])
            if item.get("eligible_for_validated_hard_negative_metrics")
        ]
        for row in hard_negative_doc["families"]
    }

    for family in families:
        family_id = family["family_id"]
        disposition = family["migration_disposition"]
        support = _supports(family)
        for scope in ("source_scoped", "cross_source"):
            source_ref = family["asset_id"] if scope == "source_scoped" else None
            control, control_records = _control_direct_rankings(
                root, scale1a_index, family, scope
            )
            rankings: dict[str, list[str]] = dict(control)

            contributions: dict[str, dict[str, set[str]] | None] = {
                key: None for key in rankings
            }
            latency: dict[str, float] = {}
            if "vision" in family["provisional_modalities"]:
                query = family["query_families"][0]
                learned, rank_perf = _rank_benchmark(
                    documents["siglip2_visual"]["documents"],
                    siglip_queries[query], source_ref=source_ref,
                )
                latency["V-SIGLIP2"] = rank_perf["warm_median_ranking_seconds"]
                ranking_benchmarks.append({
                    "family_id": family_id, "scope": scope,
                    "ranker": "V-SIGLIP2", **rank_perf,
                })
                rankings["V-SIGLIP2"] = [x["segment_id"] for x in learned]
                contributions["V-SIGLIP2"] = None
                learned_visual_records = learned
            else:
                learned_visual_records = []
            if "ambient" in family["provisional_modalities"]:
                query = family["query_families"][min(1, len(family["query_families"]) - 1)]
                learned, rank_perf = _rank_benchmark(
                    documents["clap_audio"]["documents"],
                    clap_queries[query], source_ref=source_ref,
                )
                latency["A-CLAP"] = rank_perf["warm_median_ranking_seconds"]
                ranking_benchmarks.append({
                    "family_id": family_id, "scope": scope,
                    "ranker": "A-CLAP", **rank_perf,
                })
                rankings["A-CLAP"] = [x["segment_id"] for x in learned]
                contributions["A-CLAP"] = None
                learned_audio_records = learned
            else:
                learned_audio_records = []

            def components(
                vision: str, ambient: str, speech: str
            ) -> dict[str, Sequence[Mapping[str, Any]]]:
                result: dict[str, Sequence[Mapping[str, Any]]] = {}
                visual_documents: Sequence[Mapping[str, Any]] = ()
                if "vision" in family["provisional_modalities"]:
                    if vision == "V-SIGLIP2":
                        result["vision"] = learned_visual_records
                        visual_documents = documents["siglip2_visual"]["documents"]
                    else:
                        result["vision"] = control_records.get(vision, ())
                        visual_documents = scale1a_index["modalities"]["vision"][
                            "documents"
                        ]
                if "ambient" in family["provisional_modalities"]:
                    result["ambient"] = (
                        learned_audio_records if ambient == "A-CLAP"
                        else control_records.get(ambient, ())
                    )
                if "speech" in family["provisional_modalities"]:
                    result["speech"] = control_records.get(speech, ())
                # Task-101 freezes the Scale-1A label-independent temporal
                # binding adapter before every fusion variant. Apply it
                # symmetrically to control and learned visual inputs.
                if "vision" in result and any(
                    key in result for key in ("speech", "ambient")
                ):
                    result["vision"] = _temporal_bind_visual(
                        result["vision"],
                        {
                            key: result[key]
                            for key in ("speech", "ambient")
                            if key in result
                        },
                        visual_documents,
                        source_ref=source_ref,
                    )
                return result

            fusion_specs = {
                "F-CTRL": ("V-CLIP", "A-AST", "S-BM25"),
                "F-V": ("V-SIGLIP2", "A-AST", "S-BM25"),
                "F-A": ("V-CLIP", "A-CLAP", "S-BM25"),
                "F-VA": ("V-SIGLIP2", "A-CLAP", "S-BM25"),
            }
            for row_id, inputs in fusion_specs.items():
                component_records = components(*inputs)
                ranking, contrib = _rrf_record_details(
                    component_records, rrf_k=rrf_k, weights=weights
                )
                rankings[row_id] = ranking
                contributions[row_id] = contrib

            for ranker, ranking in rankings.items():
                contract_row = comparison_by_id[ranker]
                if family_id not in contract_row["eligible_families"]:
                    continue
                if ranker in {"V-CLIP", "V-SIGLIP2"}:
                    groups = {"vision": support.get("vision", set())}
                elif ranker in {"A-AST", "A-CLAP"}:
                    groups = {"ambient": support.get("ambient", set())}
                elif ranker == "S-BM25":
                    groups = {"speech": support.get("speech", set())}
                else:
                    groups = support
                groups = {k: v for k, v in groups.items() if v}
                frozen_control = frozen_control_rows.get(
                    (family_id, scope, ranker)
                )
                # Metrics must always be derivable from the persisted ranking
                # and modality-contribution evidence. Task-101 rows remain a
                # separate parity oracle; they must never override a ranking
                # when the two disagree.
                values = _metrics(
                    ranking, groups, contributions=contributions.get(ranker)
                )
                row = {
                    "family_id": family_id, "family_disposition": disposition,
                    "scope": scope, "probe": "clean", "ranker": ranker,
                    "learned": bool(contract_row.get("learned", False)),
                    "uses_learned_retriever": ranker in {
                        "V-SIGLIP2", "A-CLAP", "F-V", "F-A", "F-VA",
                    },
                    "candidate_count": _candidate_universe_count(
                        ranker, family, scope, index, scale1a_index
                    ),
                    "ranking_depth": min(20, len(ranking)),
                    "latency_seconds": latency.get(ranker),
                    "metric_source": (
                        "task104_ranking_recomputed_with_task101_parity"
                        if frozen_control is not None
                        else "task104_ranking_recomputed"
                    ),
                    WARNING: True, **values,
                }
                metric_rows.append(row)
                run_rows.append({
                    **{k: row[k] for k in (
                        "family_id", "family_disposition", "scope", "probe",
                        "ranker", "learned",
                    )},
                    "query": (
                        family["query_families"][
                            1 if ranker in {"A-CLAP", "A-AST"} and
                            len(family["query_families"]) > 1 else 0
                        ] if ranker in {
                            "V-CLIP", "V-SIGLIP2", "A-AST", "A-CLAP",
                            "S-BM25",
                        } else None
                    ),
                    "query_by_modality": (
                        {
                            modality: family["query_families"][min(
                                len(family["query_families"]) - 1,
                                1 if modality == "ambient" else 0,
                            )]
                            for modality in family["provisional_modalities"]
                        } if ranker.startswith("F-") else None
                    ),
                    **_serialized_ranking(
                        ranker, ranking, contributions.get(ranker)
                    ),
                    "support_groups": {
                        key: sorted(value) for key, value in groups.items()
                    },
                })

            # Retrieval-only CLEAN/BLOCKED/RESTORED route probes. These are
            # explicitly projections over the already persisted clean top-20,
            # not full-universe reranks and not learned-agent recovery.
            if disposition != "retained":
                continue
            for ranker in ("V-SIGLIP2", "A-CLAP", "F-VA"):
                if ranker not in rankings:
                    continue
                clean = rankings[ranker]
                route_ids = set(
                    intervention_by_family[family_id]["blocked"][
                        "suppressed_segment_ids"
                    ]
                )
                blocked = [item for item in clean if item not in route_ids]
                for state, ranking in (
                    ("CLEAN", clean), ("BLOCKED", blocked), ("RESTORED", clean)
                ):
                    run_rows.append({
                        "family_id": family_id,
                        "family_disposition": disposition, "scope": scope,
                        "probe": "route_suppression", "state": state,
                        "ranker": ranker,
                        "learned": ranker in {"V-SIGLIP2", "A-CLAP"},
                        **_serialized_ranking(
                            ranker, ranking, contributions.get(ranker)
                        ),
                        "support_groups": {
                            key: sorted(value) for key, value in support.items()
                        },
                        "retrieval_recovery_only": True,
                        "probe_scope": "clean_top20_suppression_projection",
                        "fresh_full_universe_rerank": False,
                        **_metrics(
                            ranking, support,
                            contributions=contributions.get(ranker),
                        ),
                    })

            # Contract-eligible validated-negative displacement. Current
            # Scale-1A validation admits speech negatives only, so the learned
            # visual/audio rows truthfully emit no displacement claim; F-VA
            # can be probed where a retained family has validated negative
            # segment IDs in its fused universe.
            negatives = validated_negatives.get(family_id, [])
            if disposition == "retained" and negatives and "F-VA" in rankings:
                displaced = _displace_to_outside_top5(
                    rankings["F-VA"], set().union(*support.values()), negatives
                )
                common = {
                    "family_id": family_id,
                    "family_disposition": disposition, "scope": scope,
                    "probe": "validated_negative_displacement",
                    "ranker": "F-VA", "learned": False,
                    "support_groups": {
                        key: sorted(value) for key, value in support.items()
                    },
                    "validated_negative_ids": negatives[:5],
                    "retrieval_recovery_only": True,
                }
                run_rows.append({
                    **common, "state": "DISPLACED",
                    **_serialized_ranking(
                        "F-VA", displaced, contributions["F-VA"]
                    ),
                    "top5_displacement": not any(
                        item in set().union(*support.values())
                        for item in displaced[:5]
                    ),
                    **_metrics(
                        displaced, support,
                        contributions=contributions.get("F-VA"),
                    ),
                })
                run_rows.append({
                    **common, "state": "RERANKED_RESTORED",
                    **_serialized_ranking(
                        "F-VA", rankings["F-VA"], contributions["F-VA"]
                    ),
                    "retrieval_recovered": (
                        _metrics(
                            rankings["F-VA"], support,
                            contributions=contributions.get("F-VA"),
                        )["Recall@5"]
                        > _metrics(
                            displaced, support,
                            contributions=contributions.get("F-VA"),
                        )["Recall@5"]
                    ),
                    **_metrics(
                        rankings["F-VA"], support,
                        contributions=contributions.get("F-VA"),
                    ),
                })

    # Paired differences are per-family and never tuned or pooled as evidence
    # of significance at this low N.
    pair_specs = (
        ("V-SIGLIP2", "V-CLIP", "SigLIP2-vs-CLIP"),
        ("A-CLAP", "A-AST", "CLAP-vs-AST"),
        ("F-V", "F-CTRL", "F-V-vs-F-CTRL"),
        ("F-A", "F-CTRL", "F-A-vs-F-CTRL"),
        ("F-VA", "F-CTRL", "F-VA-vs-F-CTRL"),
    )
    paired: list[dict[str, Any]] = []
    clean_rows = {
        (x["family_id"], x["scope"], x["ranker"]): x
        for x in metric_rows if x["probe"] == "clean"
    }
    for learned, control, label in pair_specs:
        keys = sorted({
            (family, scope) for family, scope, ranker in clean_rows
            if ranker == learned and (family, scope, control) in clean_rows
        })
        for family, scope in keys:
            left, right = (
                clean_rows[(family, scope, learned)],
                clean_rows[(family, scope, control)],
            )
            row = {
                "comparison": label, "family_id": family, "scope": scope,
                "learned_ranker": learned, "control_ranker": control,
                WARNING: True,
            }
            for metric in (
                "Recall@1", "Recall@5", "Recall@10", "Recall@20",
                "All-Evidence@1", "All-Evidence@5", "All-Evidence@10",
                "All-Evidence@20", "MRR", "nDCG@1", "nDCG@5",
                "nDCG@10", "nDCG@20",
            ):
                row[f"delta_{metric}"] = (
                    float(left[metric]) - float(right[metric])
                    if left[metric] is not None and right[metric] is not None
                    else None
                )
            left_rank = left["first_accepted_evidence_rank"]
            right_rank = right["first_accepted_evidence_rank"]
            row["paired_first_rank_delta"] = (
                (int(left_rank) if left_rank is not None else 21)
                - (int(right_rank) if right_rank is not None else 21)
            )
            paired.append(row)
    _add_source_to_cross_deltas(paired)

    metric_by_key = {
        (row["family_id"], row["ranker"], row["scope"]): row
        for row in metric_rows
    }
    for row in metric_rows:
        if row["scope"] != "cross_source":
            continue
        source = metric_by_key.get(
            (row["family_id"], row["ranker"], "source_scoped")
        )
        for metric in (
            "Recall@1", "Recall@5", "Recall@10", "Recall@20",
            "All-Evidence@1", "All-Evidence@5", "All-Evidence@10",
            "All-Evidence@20", "MRR", "nDCG@1", "nDCG@5",
            "nDCG@10", "nDCG@20",
        ):
            row[f"source_to_cross_degradation_{metric}"] = (
                float(row[metric]) - float(source[metric])
                if source and row[metric] is not None
                and source[metric] is not None else None
            )

    summary: list[dict[str, Any]] = []
    for scope in ("source_scoped", "cross_source"):
        for ranker in sorted({x["ranker"] for x in metric_rows}):
            rows = [
                x for x in metric_rows
                if x["scope"] == scope and x["ranker"] == ranker
                and x["family_disposition"] == "retained"
            ]
            if not rows:
                continue
            row = {
                "scope": scope, "ranker": ranker, "n": len(rows),
                WARNING: True,
                **{
                    metric: _mean([x[metric] for x in rows])
                    for metric in (
                        "Recall@1", "Recall@5", "Recall@10", "Recall@20",
                        "All-Evidence@1", "All-Evidence@5",
                        "All-Evidence@10", "All-Evidence@20", "MRR",
                        "nDCG@1", "nDCG@5", "nDCG@10", "nDCG@20",
                    )
                },
            }
            # At this low N we report only transparent descriptive ranges;
            # these are not confidence intervals or population estimates.
            for metric in ("Recall@5", "Recall@20", "All-Evidence@20", "MRR"):
                values = [
                    float(item[metric]) for item in rows
                    if item[metric] is not None
                ]
                row[f"{metric}_descriptive_min"] = min(values) if values else None
                row[f"{metric}_descriptive_max"] = max(values) if values else None
            summary.append(row)

    # Frozen diagnostic gate: nonzero source-scoped paired deltas on >=2
    # retained families, with at least one corresponding cross-source delta or
    # a fusion All-Evidence boundary change.
    primary_changed: set[tuple[str, str]] = set()
    stress_changed: set[tuple[str, str]] = set()
    fusion_boundary = False
    for row in paired:
        changed = any(
            row.get(key) not in (None, 0.0)
            for key in (
                "paired_first_rank_delta", "delta_Recall@1", "delta_Recall@5",
                "delta_Recall@10", "delta_Recall@20",
            )
        )
        if not changed:
            continue
        change_key = (row["comparison"], row["family_id"])
        if row["scope"] == "source_scoped":
            primary_changed.add(change_key)
        else:
            stress_changed.add(change_key)
        if row["comparison"].startswith("F-") and any(
            row.get(f"delta_All-Evidence@{k}") not in (None, 0.0)
            for k in TOP_KS
        ):
            fusion_boundary = True
    diagnostic = (
        "WAVE_R_DIAGNOSTIC_GO"
        if len({family for _, family in primary_changed}) >= 2
        and (bool(primary_changed & stress_changed) or fusion_boundary)
        else "WAVE_R_DIAGNOSTIC_INCONCLUSIVE"
    )
    replay_hashes = {
        "retrieval_rows": _json_hash(run_rows),
        "metric_rows": _json_hash([
            {key: value for key, value in row.items()
             if key != "latency_seconds"}
            for row in metric_rows
        ]),
        "paired_rows": _json_hash(paired),
        "summary_rows": _json_hash(summary),
    }

    observation = _load(restricted / "observation_manifest.json")
    resource_document = _load(restricted / "resource_measurements.json")
    isolated_profiles = {
        model_id: _load(restricted / f"profile_{model_id}.json")
        for model_id in ("siglip2", "clap")
    }
    learned_index_size = (restricted / "learned_index.json").stat().st_size
    report = {
        "schema_version": SCHEMA, "stage": STAGE,
        "human_reviewed": False, "gold_annotation": False,
        "learned_model_evaluation": True,
        "scope": "learned retrieval only; no learned generation or agent claims",
        "counts": {
            "families": len(families),
            "retained_families": sum(
                x["migration_disposition"] == "retained" for x in families
            ),
            "excluded_families": sum(
                x["migration_disposition"] == "excluded" for x in families
            ),
            "metric_rows": len(metric_rows), "probe_rows": len(run_rows),
            "paired_rows": len(paired),
        },
        "coverage": observation["counts"],
        "performance": {
            "build": resource_document["records"],
            "query_embeddings": query_benchmarks,
            "ranking": ranking_benchmarks,
            "isolated_one_item_profiles": isolated_profiles,
            "model_snapshot_bytes": {
                model_id: sum(
                    int(item["bytes"])
                    for item in gates["models"]["models"][model_id]["files"]
                )
                for model_id in ("siglip2", "clap")
            },
            "learned_index_storage_bytes": learned_index_size,
            "checkpoint_storage_bytes_by_layer": {
                layer: sum(
                    int(item["size_bytes"]) for item in _load(
                        restricted / "checkpoint_manifest.json"
                    )["checkpoints"] if item["layer"] == layer
                )
                for layer in ("siglip2_visual", "clap_audio")
            },
            "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        },
        "deterministic_ranking_replay": {
            "definition": "canonical hashes over derived ranking and metric payloads",
            "hashes": replay_hashes,
        },
        "summary": summary,
        "modality_necessity_metrics": None,
        "warning": WARNING,
        "limitations": [
            "Five retained machine-provisional families and one excluded record.",
            "No human-validated modality necessity or minimal support sets.",
            "This evaluates retrieval, not learned generation or agent recovery.",
            "Intervals and labels remain machine-adjudicated provisional.",
        ],
        "diagnostic_gate_evidence": {
            "source_scoped_changed_pairs": [
                {"comparison": comparison, "family_id": family}
                for comparison, family in sorted(primary_changed)
            ],
            "source_scoped_changed_families": sorted({
                family for _, family in primary_changed
            }),
            "cross_source_changed_pairs": [
                {"comparison": comparison, "family_id": family}
                for comparison, family in sorted(stress_changed)
            ],
            "cross_source_changed_families": sorted({
                family for _, family in stress_changed
            }),
            "fusion_all_evidence_boundary_change": fusion_boundary,
        },
        "per_family_failure_analysis": [
            {
                "family_id": family["family_id"],
                "disposition": family["migration_disposition"],
                "source_ref": family["asset_id"],
                "findings": [
                    {
                        "scope": scope,
                        "ranker": ranker,
                        "first_rank": clean_rows.get(
                            (family["family_id"], scope, ranker), {}
                        ).get("first_accepted_evidence_rank"),
                        "recall_at_5": clean_rows.get(
                            (family["family_id"], scope, ranker), {}
                        ).get("Recall@5"),
                        "recall_at_20": clean_rows.get(
                            (family["family_id"], scope, ranker), {}
                        ).get("Recall@20"),
                    }
                    for scope in ("source_scoped", "cross_source")
                    for ranker in comparison_by_id
                    if (family["family_id"], scope, ranker) in clean_rows
                ],
            }
            for family in families
        ],
        "excluded_family_records": [
            {
                "family_id": family["family_id"],
                "source_ref": family["asset_id"],
                "disposition": "excluded",
                "reasons": family["migration_failures"],
                "not_reintroduced_by_wave_r": True,
            }
            for family in families
            if family["migration_disposition"] == "excluded"
        ],
        "decisions": {
            "visual": "LEARNED_VISUAL_RETRIEVAL_READY",
            "audio": "LEARNED_AUDIO_RETRIEVAL_READY",
            "retrieval": "LEARNED_RETRIEVAL_READY",
            "diagnostic": diagnostic,
            "final_benchmark": FINAL_STATUS,
        },
    }
    report["report_hash"] = _json_hash(report)
    _dump(restricted / "retrieval_runs.json", {
        "schema_version": SCHEMA, "rows": run_rows,
        "retrieval_runs_hash": _json_hash(run_rows),
    })
    _dump(restricted / "evaluation_manifest.json", {
        "schema_version": SCHEMA, "metric_rows": metric_rows,
        "paired_rows": paired, "summary_rows": summary,
        "semantic_hashes": replay_hashes,
    })
    results = root / RESULTS_REL
    _write_csv(results / "retrieval_metrics.csv", metric_rows)
    _write_csv(results / "paired_comparisons.csv", paired)
    _write_csv(results / "summary.csv", summary)
    _dump(results / "report.json", report, restricted=False)
    markdown = _report_markdown(report)
    _atomic(results / "report.md", markdown.encode(), restricted=False)
    manifest = {
        "schema_version": SCHEMA, "restricted": True,
        "report_hash": report["report_hash"],
        "artifacts": [],
    }
    for rel in (
        RESTRICTED_REL / "observation_manifest.json",
        RESTRICTED_REL / "learned_index.json",
        RESTRICTED_REL / "checkpoint_manifest.json",
        RESTRICTED_REL / "resource_measurements.json",
        RESTRICTED_REL / "profile_siglip2.json",
        RESTRICTED_REL / "profile_clap.json",
        RESTRICTED_REL / "retrieval_runs.json",
        RESTRICTED_REL / "evaluation_manifest.json",
        RESTRICTED_REL / "build_manifest.json",
        RESULTS_REL / "retrieval_metrics.csv",
        RESULTS_REL / "paired_comparisons.csv",
        RESULTS_REL / "summary.csv",
        RESULTS_REL / "report.json",
        RESULTS_REL / "report.md",
        Path("src/av_trace_scale1b_retrieval/__init__.py"),
        Path("src/av_trace_scale1b_retrieval/core.py"),
        Path("scripts/build_scale1b_wave_r.py"),
        Path("scripts/audit_scale1b_wave_r.py"),
        Path("scripts/profile_scale1b_wave_r_model.py"),
        Path("scripts/run_scale1b_wave_r.py"),
        Path("scripts/verify_scale1b_wave_r.py"),
        Path("tests_scale1b/test_wave_r.py"),
    ):
        path = root / rel
        manifest["artifacts"].append({
            "path": rel.as_posix(), "size_bytes": path.stat().st_size,
            "sha256": _sha256(path, prefixed=True),
        })
    manifest["run_manifest_hash"] = _json_hash(manifest)
    _dump(results / "run_manifest.json", manifest)
    return report


def _report_markdown(report: Mapping[str, Any]) -> str:
    decisions = report["decisions"]
    return (
        "# Scale-1B Wave-R learned retrieval\n\n"
        f"Stage: `{STAGE}`  \nWarning: `{WARNING}`\n\n"
        "## Decisions\n\n"
        f"- `{decisions['visual']}`\n"
        f"- `{decisions['audio']}`\n"
        f"- `{decisions['retrieval']}`\n"
        f"- `{decisions['diagnostic']}`\n"
        f"- `{decisions['final_benchmark']}`\n\n"
        "Actual pinned SigLIP2 and CLAP vectors were used. Results are "
        "retrieval-only, low-N, machine-provisional, and do not establish "
        "learned generation or agent recovery.\n"
    )


def verify_wave_r(
    repo_root: str | Path, *, require_results: bool = True,
    spot_recompute: bool = False,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    failures: list[str] = []
    try:
        gates = verify_gates(root)
    except Exception as exc:
        return {"passed": False, "failures": [str(exc)]}
    restricted = root / RESTRICTED_REL
    required = [
        restricted / "observation_manifest.json",
        restricted / "learned_index.json",
        restricted / "checkpoint_manifest.json",
        restricted / "build_manifest.json",
    ]
    if require_results:
        required += [
            restricted / "retrieval_runs.json",
            restricted / "evaluation_manifest.json",
            restricted / "resource_measurements.json",
            restricted / "profile_siglip2.json",
            restricted / "profile_clap.json",
            root / RESULTS_REL / "retrieval_metrics.csv",
            root / RESULTS_REL / "paired_comparisons.csv",
            root / RESULTS_REL / "summary.csv",
            root / RESULTS_REL / "report.json",
            root / RESULTS_REL / "report.md",
            root / RESULTS_REL / "run_manifest.json",
        ]
    for path in required:
        if not path.is_file() or path.is_symlink():
            failures.append(f"MISSING_OR_UNSAFE:{path.relative_to(root)}")
    if failures:
        return {"passed": False, "failures": failures}
    observation = _load(required[0])
    index = _load(required[1])
    checkpoints = _load(required[2])
    build = _load(restricted / "build_manifest.json")
    expected_gate_hashes = {
        key: gates[key]
        for key in (
            "contract_sha256", "model_manifest_sha256",
            "scale1a_audit_sha256",
        )
    }
    if observation.get("config", {}).get("gate_hashes") != expected_gate_hashes:
        failures.append("STALE_GATE_HASH_BINDING")
    segment_manifest = _load(root / SCALE1A_ROOT_REL / "segment_manifest.json")
    for document, field, label in (
        (observation, "observation_manifest_hash", "OBSERVATION"),
        (index, "index_hash", "INDEX"),
        (checkpoints, "checkpoint_manifest_hash", "CHECKPOINT_MANIFEST"),
        (build, "build_manifest_hash", "BUILD_MANIFEST"),
    ):
        if not _self_hash_valid(document, field):
            failures.append(f"{label}_SELF_HASH")
    if observation.get("timeline") != {
        "segment_manifest_hash": _load(
            root / SCALE1A_ROOT_REL / "segment_manifest.json"
        )["segment_manifest_hash"],
        "base_cells": 3433, "fine_windows": 3428,
        "context_windows": 855, "unchanged_ids_and_intervals": True,
    }:
        failures.append("TIMELINE_IDENTITY")
    if observation.get("counts", {}).get("siglip2_cells") != 3433:
        failures.append("SIGLIP_CELL_COUNT")
    if observation.get("counts", {}).get("clap_fine_vectors") != 3428:
        failures.append("CLAP_FINE_COUNT")
    if observation.get("counts", {}).get("siglip2_segment_vectors") != 4283:
        failures.append("SIGLIP_SEGMENT_COUNT")
    if observation.get("counts", {}).get("clap_context_vectors") != 855:
        failures.append("CLAP_CONTEXT_COUNT")
    try:
        _assert_safe_index(index)
    except Exception as exc:
        failures.append(str(exc))
    for layer, expected_revision in (
        ("siglip2_visual", "75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2"),
        ("clap_audio", "8fa0f1c6d0433df6e97c127f64b2a1d6c0dcda8a"),
    ):
        ranker = index.get("rankers", {}).get(layer, {})
        if ranker.get("model_revision") != expected_revision:
            failures.append(f"MODEL_REVISION:{layer}")
        docs = index.get("modalities", {}).get(layer, {}).get("documents", [])
        for item in docs:
            try:
                vector = _from_f16(item["vector_f16_hex"], item["dimension"])
                norm = float(np.linalg.norm(vector))
                if not math.isfinite(norm) or abs(norm - 1.0) > 0.02:
                    failures.append(f"VECTOR_NORM:{layer}:{item['segment_id']}")
                    break
            except Exception:
                failures.append(f"VECTOR_INVALID:{layer}")
                break
    for checkpoint in checkpoints.get("checkpoints", []):
        path = root / checkpoint["path"]
        if (
            not path.is_file()
            or _sha256(path, prefixed=True) != checkpoint["sha256"]
            or path.stat().st_size != checkpoint["size_bytes"]
        ):
            failures.append(f"CHECKPOINT_MISMATCH:{checkpoint['path']}")
            continue
        document = _load(path)
        if (
            document.get("payload_hash") != checkpoint["payload_hash"]
            or document.get("payload_hash") != _json_hash(document.get("payload"))
            or document.get("config_hash") != observation.get("config_hash")
        ):
            failures.append(f"CHECKPOINT_PAYLOAD_MISMATCH:{checkpoint['path']}")
        payload = document.get("payload", {})
        if payload.get("actual_learned_model") is not True:
            failures.append(f"LEARNED_MODEL_PROOF_MISSING:{checkpoint['path']}")
        vector_rows = (
            payload.get("cell_vectors", [])
            if checkpoint["layer"] == "siglip2_visual"
            else payload.get("fine_records", [])
        )
        expected_ids = {
            row["cell_id"] for row in segment_manifest["base_cells"]
            if row["source_ref"] == checkpoint["source_ref"]
        } if checkpoint["layer"] == "siglip2_visual" else {
            row["segment_id"] for row in segment_manifest["segments"]
            if row["source_ref"] == checkpoint["source_ref"]
            and row["scale"] == "fine"
        }
        observed_ids = {
            row.get("cell_id") or row.get("segment_id") for row in vector_rows
        }
        if observed_ids != expected_ids:
            failures.append(f"CHECKPOINT_TIMELINE_IDS:{checkpoint['path']}")
        for row in vector_rows:
            try:
                vector = _from_f16(row["vector_f16_hex"], row["dimension"])
                norm = float(np.linalg.norm(vector))
                if not np.isfinite(vector).all() or abs(norm - 1.0) > 0.02:
                    failures.append(
                        f"CHECKPOINT_VECTOR_INVALID:{checkpoint['path']}"
                    )
                    break
            except Exception:
                failures.append(f"CHECKPOINT_VECTOR_INVALID:{checkpoint['path']}")
                break
    if len(checkpoints.get("checkpoints", [])) != 10:
        failures.append("CHECKPOINT_COUNT")
    for rel, expected in build.get("implementation_hashes", {}).items():
        path = root / rel
        if not path.is_file() or _sha256(path, prefixed=True) != expected:
            failures.append(f"IMPLEMENTATION_HASH:{rel}")
    expected_segments = {
        (
            row["segment_id"], row["source_ref"], row["scale"],
            row["start_us"], row["end_us"],
        )
        for row in segment_manifest["segments"]
    }
    for layer in ("siglip2_visual", "clap_audio"):
        observed_segments = {
            (
                row["segment_id"], row["source_ref"], row["scale"],
                row["start_us"], row["end_us"],
            )
            for row in index["modalities"][layer]["documents"]
        }
        if observed_segments != expected_segments:
            failures.append(f"INDEX_TIMELINE_PARITY:{layer}")
    try:
        _source_paths(root)
    except Exception as exc:
        failures.append(str(exc))
    for path in restricted.rglob("*"):
        if path.is_symlink():
            failures.append(f"RESTRICTED_SYMLINK:{path.relative_to(root)}")
        elif path.is_dir() and stat.S_IMODE(path.stat().st_mode) != 0o700:
            failures.append(f"RESTRICTED_DIR_MODE:{path.relative_to(root)}")
        elif path.is_file() and stat.S_IMODE(path.stat().st_mode) != 0o600:
            failures.append(f"RESTRICTED_FILE_MODE:{path.relative_to(root)}")
        if path.is_file() and path.suffix.lower() in {
            ".wav", ".flac", ".mp3", ".mp4", ".jpg", ".jpeg", ".png",
        }:
            failures.append(f"PERSISTED_MEDIA_DERIVATIVE:{path.relative_to(root)}")
    if require_results:
        report = _load(root / RESULTS_REL / "report.json")
        if not _self_hash_valid(report, "report_hash"):
            failures.append("REPORT_SELF_HASH")
        if report["decisions"]["retrieval"] != "LEARNED_RETRIEVAL_READY":
            failures.append("RETRIEVAL_DECISION")
        public_text = "\n".join(
            (root / RESULTS_REL / name).read_text(errors="ignore")
            for name in ("report.json", "report.md", "retrieval_metrics.csv",
                         "paired_comparisons.csv", "summary.csv")
        )
        forbidden = (
            "/jizhicfs/", "http_proxy", "https_proxy", "transcript_excerpt",
            "vector_f16_hex",
        )
        for token in forbidden:
            if token in public_text:
                failures.append(f"PUBLIC_LEAKAGE:{token}")
        runs = _load(restricted / "retrieval_runs.json")
        evaluation = _load(restricted / "evaluation_manifest.json")
        observed_hashes = {
            "retrieval_rows": _json_hash(runs.get("rows", [])),
            "metric_rows": _json_hash([
                {key: value for key, value in row.items()
                 if key != "latency_seconds"}
                for row in evaluation.get("metric_rows", [])
            ]),
            "paired_rows": _json_hash(evaluation.get("paired_rows", [])),
            "summary_rows": _json_hash(evaluation.get("summary_rows", [])),
        }
        if observed_hashes != report.get(
            "deterministic_ranking_replay", {}
        ).get("hashes"):
            failures.append("DERIVED_REPLAY_HASH_MISMATCH")
        expected_row_counts = {
            "V-CLIP": 8, "V-SIGLIP2": 8, "A-AST": 2, "A-CLAP": 2,
            "S-BM25": 4, "F-CTRL": 10, "F-V": 10, "F-A": 10, "F-VA": 10,
        }
        observed_row_counts = {
            ranker: sum(
                row["ranker"] == ranker
                for row in evaluation.get("metric_rows", [])
            )
            for ranker in expected_row_counts
        }
        if observed_row_counts != expected_row_counts:
            failures.append("COMPARISON_MATRIX_INCOMPLETE")
        if any(
            row.get("family_disposition") == "excluded"
            for row in evaluation.get("metric_rows", [])
        ):
            failures.append("EXCLUDED_FAMILY_REINTRODUCED")
        if any(
            row.get("modality_necessity") is not None
            for row in evaluation.get("metric_rows", [])
        ):
            failures.append("MODALITY_NECESSITY_NOT_NULL")
        run_by_key = {
            (row["family_id"], row["scope"], row["ranker"]): row
            for row in runs.get("rows", []) if row.get("probe") == "clean"
        }
        for stored in runs.get("rows", []):
            ranking_ids = stored.get("ranking_top20", [])
            private_ids = stored.get("evaluator_private_ranking_segment_ids", [])
            if len(ranking_ids) != len(private_ids):
                failures.append(
                    "OPAQUE_RANKING_LENGTH:"
                    f"{stored.get('family_id')}:{stored.get('scope')}:"
                    f"{stored.get('ranker')}:{stored.get('probe')}"
                )
                continue
            expected_opaque = [
                _opaque_result_id(str(stored["ranker"]), item)
                for item in private_ids
            ]
            if ranking_ids != expected_opaque:
                failures.append(
                    "OPAQUE_RANKING_ID_MISMATCH:"
                    f"{stored.get('family_id')}:{stored.get('scope')}:"
                    f"{stored.get('ranker')}:{stored.get('probe')}"
                )
        frozen_controls = {
            (row["family_id"], row["scope"], row["row_id"]): row
            for row in gates["contract"]["wave_r_direct_control_preflight"]["rows"]
        }
        for row in evaluation.get("metric_rows", []):
            key = (row["family_id"], row["scope"], row["ranker"])
            stored = run_by_key.get(key)
            if stored is None:
                failures.append(f"METRIC_RUN_ROW_MISSING:{key}")
                continue
            if row.get("metric_source") == "task101_frozen_direct_control":
                frozen = frozen_controls.get(key)
                if frozen is None:
                    failures.append(f"FROZEN_CONTROL_ROW_MISSING:{key}")
                    continue
                recalculated = _metrics_from_route_ranks(
                    frozen["support_route_ranks"]
                )
            else:
                recalculated = _metrics(
                    stored["evaluator_private_ranking_segment_ids"],
                    {
                        name: set(ids)
                        for name, ids in stored["support_groups"].items()
                    },
                    contributions=(
                        {
                            item: set(modalities)
                            for item, modalities in
                            (
                                stored.get(
                                    "evaluator_private_fused_contributions"
                                ) or {}
                            ).items()
                        }
                        if stored.get("fused_contributions") is not None
                        else None
                    ),
                )
            for metric in (
                "Recall@1", "Recall@5", "Recall@10", "Recall@20",
                "All-Evidence@1", "All-Evidence@5", "All-Evidence@10",
                "All-Evidence@20", "MRR", "nDCG@1", "nDCG@5",
                "nDCG@10", "nDCG@20", "first_accepted_evidence_rank",
            ):
                left, right = row.get(metric), recalculated.get(metric)
                if left is None or right is None:
                    equal = left is right
                else:
                    equal = abs(float(left) - float(right)) <= 1e-10
                if not equal:
                    failures.append(f"METRIC_RECOMPUTE:{key}:{metric}")
                    break
        run_manifest = _load(root / RESULTS_REL / "run_manifest.json")
        if not _self_hash_valid(run_manifest, "run_manifest_hash"):
            failures.append("RUN_MANIFEST_SELF_HASH")
        for artifact in run_manifest.get("artifacts", []):
            path = root / artifact["path"]
            if (
                not path.is_file()
                or path.stat().st_size != artifact["size_bytes"]
                or _sha256(path, prefixed=True) != artifact["sha256"]
            ):
                failures.append(f"RUN_MANIFEST_MISMATCH:{artifact['path']}")
    spot = None
    if spot_recompute and not failures:
        # Recompute one actual vector from each model and compare to its
        # persisted source checkpoint. This is intentionally optional because
        # it loads both large models.
        segment_manifest = _load(root / SCALE1A_ROOT_REL / "segment_manifest.json")
        source_ref = segment_manifest["sources"][0]["source_ref"]
        source = _source_paths(root)[source_ref]
        siglip_path, _ = _find_model(root, gates["models"], kind="siglip2")
        clap_path, _ = _find_model(root, gates["models"], kind="clap")
        models = _WaveRModels(siglip_path, clap_path, threads=8)
        cell = next(x for x in segment_manifest["base_cells"] if x["source_ref"] == source_ref)
        _, frame = next(_iter_frames(source, [cell]))
        vision = models.siglip_images([frame])[0]
        fine = next(
            x for x in segment_manifest["segments"]
            if x["source_ref"] == source_ref and x["scale"] == "fine"
        )
        waveform = _decode_audio(source, 48_000)
        audio = models.clap_audio([
            _slice_audio(waveform, fine["start_us"], fine["end_us"], 48_000)
        ], 48_000)[0]
        vision_cp = _load(
            restricted / "checkpoints" / source_ref / "siglip2.json"
        )["payload"]["cell_vectors"][0]
        audio_cp = _load(
            restricted / "checkpoints" / source_ref / "clap.json"
        )["payload"]["fine_records"][0]
        vd = float(np.max(np.abs(
            vision - _from_f16(vision_cp["vector_f16_hex"], vision_cp["dimension"])
        )))
        ad = float(np.max(np.abs(
            audio - _from_f16(audio_cp["vector_f16_hex"], audio_cp["dimension"])
        )))
        spot = {"siglip2_max_abs": vd, "clap_max_abs": ad}
        if vd > 0.002 or ad > 0.002:
            failures.append("SPOT_RECOMPUTE_MISMATCH")
    return {"passed": not failures, "failures": failures, "spot_recompute": spot}
