#!/usr/bin/env python3
"""Fail-closed Wave-R snapshot validation and offline retrieval-model smoke tests."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import resource
import stat
import sys
import time
from pathlib import Path
from typing import Any

ROOT_PLAN = Path("data/acquisition_plan/scale1b_wave_r_model_plan.json")
MANIFEST = Path("data/restricted/scale1b/manifests/wave_r_model_acquisition.json")
CAP_TOTAL = 3 << 30
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
WEIGHTS = {"model.safetensors", "pytorch_model.bin", "tf_model.h5", "flax_model.msgpack"}


class ValidationError(RuntimeError):
    pass


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def sha256_file(path: Path, block: int = 8 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(block):
            digest.update(chunk)
    return digest.hexdigest()


def git_blob_oid(path: Path) -> str:
    digest = hashlib.sha1()
    digest.update(f"blob {path.stat().st_size}\0".encode())
    with path.open("rb") as handle:
        while chunk := handle.read(8 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def git_blob_oid_bytes(data: bytes) -> str:
    digest = hashlib.sha1()
    digest.update(f"blob {len(data)}\0".encode())
    digest.update(data)
    return digest.hexdigest()


def lfs_pointer_git_oid(sha256: str, size: int) -> str:
    data = (
        "version https://git-lfs.github.com/spec/v1\n"
        f"oid sha256:{sha256}\nsize {size}\n"
    ).encode()
    return git_blob_oid_bytes(data)


def model_map(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    models = plan.get("models")
    if not isinstance(models, list) or {m.get("id") for m in models} != {"siglip2", "clap"}:
        raise ValidationError("MODEL_SET_MISMATCH")
    return {m["id"]: m for m in models}


def validate_plan(plan: dict[str, Any]) -> None:
    models = model_map(plan)
    total = 0
    expected = {
        "siglip2": ("google/siglip2-base-patch16-224", "75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2", 2 << 30, "model.safetensors"),
        "clap": ("laion/clap-htsat-unfused", "8fa0f1c6d0433df6e97c127f64b2a1d6c0dcda8a", 1 << 30, "pytorch_model.bin"),
    }
    for model_id, (repo, revision, cap, weight) in expected.items():
        model = models[model_id]
        if (model.get("repo_id"), model.get("revision"), model.get("cap_bytes")) != (repo, revision, cap):
            raise ValidationError(f"IDENTITY_OR_CAP_MISMATCH:{model_id}")
        if not HEX40.fullmatch(revision):
            raise ValidationError(f"INVALID_REVISION:{model_id}")
        files = model.get("allowlist")
        if not isinstance(files, list) or not files:
            raise ValidationError(f"EMPTY_ALLOWLIST:{model_id}")
        names = [f.get("path") for f in files]
        if len(names) != len(set(names)) or any(Path(str(n)).name != n for n in names):
            raise ValidationError(f"INVALID_ALLOWLIST_PATHS:{model_id}")
        if set(names) & WEIGHTS != {weight}:
            raise ValidationError(f"WEIGHT_REPRESENTATION_MISMATCH:{model_id}")
        subtotal = 0
        for item in files:
            size, oid, lfs = item.get("expected_bytes"), item.get("git_oid"), item.get("lfs_sha256")
            if not isinstance(size, int) or size <= 0 or not isinstance(oid, str) or not HEX40.fullmatch(oid):
                raise ValidationError(f"INVALID_FILE_METADATA:{model_id}:{item.get('path')}")
            if lfs is not None:
                if not isinstance(lfs, str) or not HEX64.fullmatch(lfs):
                    raise ValidationError(f"INVALID_LFS:{model_id}:{item['path']}")
                if lfs_pointer_git_oid(lfs, size) != oid:
                    raise ValidationError(f"LFS_POINTER_MISMATCH:{model_id}:{item['path']}")
            subtotal += size
        if subtotal != model.get("expected_payload_bytes") or subtotal > cap:
            raise ValidationError(f"PAYLOAD_OR_CAP_MISMATCH:{model_id}")
        total += subtotal
    if total != plan.get("expected_total_bytes") or total > CAP_TOTAL:
        raise ValidationError("TOTAL_PAYLOAD_OR_CAP_MISMATCH")


def validate_metadata(model: dict[str, Any], api: dict[str, Any], tree: list[dict[str, Any]], readme: bytes) -> dict[str, Any]:
    if api.get("id") != model["repo_id"] or api.get("sha") != model["revision"]:
        raise ValidationError(f"MODEL_API_IDENTITY_MISMATCH:{model['id']}")
    if api.get("private") is not False or bool(api.get("gated")):
        raise ValidationError(f"MODEL_NOT_PUBLIC_UNGATED:{model['id']}")
    by_path = {x.get("path"): x for x in tree if x.get("type") == "file"}
    for item in model["allowlist"]:
        actual = by_path.get(item["path"])
        if not actual or actual.get("size") != item["expected_bytes"] or actual.get("oid") != item["git_oid"]:
            raise ValidationError(f"TREE_MISMATCH:{model['id']}:{item['path']}")
        if item["lfs_sha256"] and (actual.get("lfs") or {}).get("oid") != item["lfs_sha256"]:
            raise ValidationError(f"TREE_LFS_MISMATCH:{model['id']}:{item['path']}")
    readme_item = by_path.get("README.md")
    if not readme_item or len(readme) != readme_item["size"] or git_blob_oid_bytes(readme) != readme_item["oid"]:
        raise ValidationError(f"MODEL_CARD_MISMATCH:{model['id']}")
    licenses = []
    card_license = (api.get("cardData") or {}).get("license")
    if card_license:
        licenses.append(("cardData", str(card_license).lower()))
    licenses += [("tag", str(t).split(":", 1)[1].lower()) for t in api.get("tags", []) if str(t).startswith("license:")]
    front = readme.decode("utf-8", "replace").split("---", 2)
    if len(front) == 3:
        for line in front[1].splitlines():
            if line.strip().lower().startswith("license:"):
                licenses.append(("README", line.split(":", 1)[1].strip().lower()))
    values = {value for _, value in licenses}
    if not licenses or values != {"apache-2.0"}:
        raise ValidationError(f"LICENSE_MISSING_OR_AMBIGUOUS:{model['id']}")
    return {"declared_license": "apache-2.0", "evidence": [{"source": s, "value": v} for s, v in licenses]}


def validate_snapshot(model: dict[str, Any], snapshot: Path, hashes: dict[str, str] | None = None) -> list[dict[str, Any]]:
    if not snapshot.is_dir() or snapshot.is_symlink() or stat.S_IMODE(snapshot.stat().st_mode) & 0o077:
        raise ValidationError(f"INVALID_SNAPSHOT_DIRECTORY:{model['id']}")
    allowed = {x["path"]: x for x in model["allowlist"]}
    actual = set()
    for path in snapshot.iterdir():
        if path.is_symlink() or not path.is_file():
            raise ValidationError(f"NON_REGULAR_FILE:{model['id']}:{path.name}")
        actual.add(path.name)
    if actual != set(allowed) | {"SHA256SUMS"}:
        raise ValidationError(f"FILE_SET_MISMATCH:{model['id']}")
    rows = []
    for name, expected in allowed.items():
        path = snapshot / name
        if stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise ValidationError(f"FILE_MODE:{model['id']}:{name}")
        digest = sha256_file(path)
        oid = lfs_pointer_git_oid(expected["lfs_sha256"], path.stat().st_size) if expected["lfs_sha256"] else git_blob_oid(path)
        if path.stat().st_size != expected["expected_bytes"] or oid != expected["git_oid"]:
            raise ValidationError(f"LOCAL_IDENTITY:{model['id']}:{name}")
        if expected["lfs_sha256"] and digest != expected["lfs_sha256"]:
            raise ValidationError(f"LOCAL_LFS_HASH:{model['id']}:{name}")
        if hashes is not None and hashes.get(name) != digest:
            raise ValidationError(f"MANIFEST_HASH:{model['id']}:{name}")
        rows.append({"path": name, "bytes": path.stat().st_size, "sha256": digest, "git_oid": oid})
    sums = {}
    for line in (snapshot / "SHA256SUMS").read_text().splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([^/]+)", line)
        if not match or match.group(2) in sums:
            raise ValidationError(f"INVALID_SHA256SUMS:{model['id']}")
        sums[match.group(2)] = match.group(1)
    if sums != {r["path"]: r["sha256"] for r in rows}:
        raise ValidationError(f"SHA256SUMS_MISMATCH:{model['id']}")
    if model["id"] == "siglip2":
        from safetensors import safe_open
        with safe_open(snapshot / "model.safetensors", framework="pt", device="cpu") as handle:
            if not handle.keys():
                raise ValidationError("EMPTY_SAFETENSORS")
    return rows


def validate_ready_manifest(
    plan: dict[str, Any], manifest: dict[str, Any]
) -> None:
    if manifest.get("status") != "ACQUISITION_COMPLETE":
        raise ValidationError("ACQUISITION_NOT_COMPLETE")
    if manifest.get("siglip2_decision") != "SIGLIP2_SNAPSHOT_READY":
        raise ValidationError("SIGLIP2_GATE_NOT_READY")
    if manifest.get("clap_decision") != "CLAP_SNAPSHOT_READY":
        raise ValidationError("CLAP_GATE_NOT_READY")
    if manifest.get("wave_r_decision") != "WAVE_R_MODELS_READY":
        raise ValidationError("WAVE_R_GATE_NOT_READY")
    if manifest.get("technical_internal_use_authorized") is not True:
        raise ValidationError("TECHNICAL_USE_NOT_AUTHORIZED")
    if manifest.get("redistribution_authorized") is not False:
        raise ValidationError("REDISTRIBUTION_MUST_REMAIN_CLOSED")
    if manifest.get("credentials_persisted") is not False:
        raise ValidationError("CREDENTIAL_POLICY_VIOLATION")
    if manifest.get("total_payload_bytes") != plan["expected_total_bytes"]:
        raise ValidationError("MANIFEST_TOTAL_PAYLOAD_MISMATCH")
    records = manifest.get("models")
    if not isinstance(records, dict) or set(records) != {"siglip2", "clap"}:
        raise ValidationError("MANIFEST_MODEL_SET_MISMATCH")
    expected_runtime = {
        "siglip2": ("siglip", "SiglipModel", "SiglipProcessor", 768),
        "clap": ("clap", "ClapModel", "ClapProcessor", 512),
    }
    for model_id, (model_type, model_class, processor_class, dimension) in (
        expected_runtime.items()
    ):
        record = records[model_id]
        smoke = record.get("offline_smoke")
        if not isinstance(smoke, dict):
            raise ValidationError(f"SMOKE_MISSING:{model_id}")
        required = {
            "local_files_only": True,
            "config_model_type": model_type,
            "model_class": model_class,
            "processor_class": processor_class,
            "embedding_dimension": dimension,
            "runtime_class_resolution": "local_config_model_type",
        }
        for key, expected in required.items():
            if smoke.get(key) != expected:
                raise ValidationError(f"SMOKE_FIELD_MISMATCH:{model_id}:{key}")
        persisted_key = (
            "synthetic_image_persisted"
            if model_id == "siglip2"
            else "synthetic_audio_persisted"
        )
        if smoke.get(persisted_key) is not False:
            raise ValidationError(f"SYNTHETIC_DERIVATIVE_POLICY:{model_id}")
        tolerance = smoke.get("deterministic_replay_tolerance")
        delta = smoke.get("deterministic_replay_max_abs_delta")
        if (
            not isinstance(tolerance, (int, float))
            or not isinstance(delta, (int, float))
            or delta > tolerance
        ):
            raise ValidationError(f"REPLAY_TOLERANCE_FAILED:{model_id}")
        if record.get("redistribution_decision") != (
            "NOT_AUTHORIZED_PENDING_RELEASE_REVIEW"
        ):
            raise ValidationError(f"MODEL_REDISTRIBUTION_GATE:{model_id}")


def _offline_env() -> None:
    os.environ.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_DATASETS_OFFLINE": "1"})
    for key in list(os.environ):
        if key.upper() in {"HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"}:
            os.environ.pop(key, None)


def resolve_runtime_classes(model_id: str, snapshot: Path) -> tuple[Any, Any, str]:
    """Resolve classes from the pinned local config, not the marketing repo name."""
    import numpy as np
    # Transformers 5.2 imports SciPy paths that still reference these aliases.
    if "long" not in np.__dict__:
        np.long = np.int64  # type: ignore[attr-defined]
    if "ulong" not in np.__dict__:
        np.ulong = np.uint64  # type: ignore[attr-defined]
    config = load_json(snapshot / "config.json")
    model_type = config.get("model_type")
    if model_id == "siglip2":
        if model_type == "siglip":
            from transformers import SiglipModel, SiglipProcessor
            return SiglipModel, SiglipProcessor, model_type
        if model_type == "siglip2":
            from transformers import Siglip2Model, Siglip2Processor
            return Siglip2Model, Siglip2Processor, model_type
        raise ValidationError(f"UNSUPPORTED_SIGLIP_MODEL_TYPE:{model_type}")
    if model_id == "clap":
        if model_type != "clap":
            raise ValidationError(f"UNSUPPORTED_CLAP_MODEL_TYPE:{model_type}")
        from transformers import ClapModel, ClapProcessor
        return ClapModel, ClapProcessor, model_type
    raise ValidationError(f"UNKNOWN_MODEL_ID:{model_id}")


def offline_smoke(model_id: str, snapshot: Path, tolerance: float = 1e-6) -> dict[str, Any]:
    import numpy as np
    if "long" not in np.__dict__:
        np.long = np.int64  # type: ignore[attr-defined]
    if "ulong" not in np.__dict__:
        np.ulong = np.uint64  # type: ignore[attr-defined]
    _offline_env()
    import torch
    import transformers
    torch.manual_seed(0)
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(1)
    rss0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    started = time.perf_counter()
    model_class, processor_class, config_model_type = resolve_runtime_classes(
        model_id, snapshot
    )
    if model_id == "siglip2":
        from PIL import Image
        processor = processor_class.from_pretrained(
            snapshot, local_files_only=True, use_fast=False
        )
        model = model_class.from_pretrained(snapshot, local_files_only=True).eval()
        pixels = np.zeros((224, 224, 3), dtype=np.uint8)
        pixels[:, :, 0] = np.arange(224, dtype=np.uint8)[None, :]
        pixels[:, :, 1] = np.arange(224, dtype=np.uint8)[:, None]
        media = Image.fromarray(pixels, "RGB")
        inputs = processor(
            text=["a synthetic color gradient"],
            images=media,
            return_tensors="pt",
            padding="max_length",
        )
        def run():
            with torch.inference_mode():
                model_inputs = {
                    "pixel_values": inputs["pixel_values"],
                    "input_ids": inputs["input_ids"],
                    "return_dict": True,
                }
                if "attention_mask" in inputs:
                    model_inputs["attention_mask"] = inputs["attention_mask"]
                outputs = model(**model_inputs)
                a = torch.nn.functional.normalize(outputs.image_embeds, dim=-1)
                b = torch.nn.functional.normalize(outputs.text_embeds, dim=-1)
                similarity = a @ b.T
            return a.cpu(), b.cpu(), similarity.cpu()
        persisted = "synthetic_image_persisted"
    else:
        processor = processor_class.from_pretrained(
            snapshot, local_files_only=True
        )
        model = model_class.from_pretrained(snapshot, local_files_only=True).eval()
        sample_rate = int(getattr(processor.feature_extractor, "sampling_rate", 48000))
        waveform = (0.2 * np.sin(2 * np.pi * 440 * np.arange(sample_rate, dtype=np.float32) / sample_rate)).astype(np.float32)
        audio_inputs = processor(
            audio=waveform, sampling_rate=sample_rate, return_tensors="pt"
        )
        text_inputs = processor(text=["a steady synthetic tone"], return_tensors="pt", padding=True)
        def run():
            with torch.inference_mode():
                audio_output = model.get_audio_features(**audio_inputs)
                text_output = model.get_text_features(**text_inputs)
                a = torch.nn.functional.normalize(audio_output.pooler_output, dim=-1)
                b = torch.nn.functional.normalize(text_output.pooler_output, dim=-1)
                similarity = a @ b.T
            return a.cpu(), b.cpu(), similarity.cpu()
        persisted = "synthetic_audio_persisted"
    load_latency = time.perf_counter() - started
    t1 = time.perf_counter(); first = run(); first_latency = time.perf_counter() - t1
    t2 = time.perf_counter(); second = run(); replay_latency = time.perf_counter() - t2
    max_delta = max(float((x-y).abs().max()) for x, y in zip(first, second))
    if max_delta > tolerance or not all(torch.isfinite(x).all() for x in first):
        raise ValidationError(f"NONDETERMINISTIC_OR_NONFINITE:{model_id}")
    similarity = float(first[2][0, 0])
    if not math.isfinite(similarity) or not -1.000001 <= similarity <= 1.000001:
        raise ValidationError(f"INVALID_SIMILARITY:{model_id}")
    return {
        "local_files_only": True, persisted: False, "model_class": type(model).__name__,
        "processor_class": type(processor).__name__, "config_model_type": config_model_type,
        "runtime_class_resolution": "local_config_model_type",
        "embedding_dimension": int(first[0].shape[-1]),
        "dtype": str(first[0].dtype), "normalized_similarity": similarity,
        "deterministic_replay_tolerance": tolerance, "deterministic_replay_max_abs_delta": max_delta,
        "load_latency_seconds": load_latency, "first_inference_seconds": first_latency,
        "replay_inference_seconds": replay_latency,
        "peak_rss_kib": max(rss0, resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        "runtime": {"python": sys.version.split()[0], "torch": torch.__version__, "transformers": transformers.__version__, "numpy": np.__version__, "device": "cpu", "threads": torch.get_num_threads()},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--validate-existing", action="store_true")
    parser.add_argument("--offline-smoke", action="store_true")
    args = parser.parse_args()
    root = args.repo_root.resolve()
    plan = load_json(root / ROOT_PLAN)
    validate_plan(plan)
    if not args.validate_existing:
        print("WAVE_R_PLAN_VALID")
        return 0
    manifest = load_json(root / MANIFEST)
    validate_ready_manifest(plan, manifest)
    for model_id, model in model_map(plan).items():
        record = manifest["models"][model_id]
        snapshot = root / model["snapshot_dir"]
        validate_snapshot(model, snapshot, {x["path"]: x["sha256"] for x in record["files"]})
        if args.offline_smoke:
            offline_smoke(model_id, snapshot)
    print("WAVE_R_MODELS_VALID")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as exc:
        print(f"NO_GO:{exc}", file=sys.stderr)
        raise SystemExit(2)
