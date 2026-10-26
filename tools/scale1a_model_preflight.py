#!/usr/bin/env python3
"""Fail-closed validation and offline smoke test for Task 94's CLIP snapshot."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import stat
import sys
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ID = "openai/clip-vit-base-patch32"
REVISION = "3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268"
CAP_BYTES = 1 << 30
PLAN_PATH = Path("data/acquisition_plan/scale1a_clip_model_plan.json")
FINAL_DIR = Path("data/restricted/noaa01/models/clip-vit-base-patch32-3d74acf")
MANIFEST_PATH = Path(
    "data/restricted/noaa01/models/scale1a_clip_acquisition_manifest.json"
)
OVERALL_DECISION = "CONDITIONAL_GO"
TECHNICAL_INFERENCE_DECISION = "CLIP_SNAPSHOT_READY"
REDISTRIBUTION_DECISION = "NOT_AUTHORIZED"
WEIGHT_NAMES = {
    "pytorch_model.bin",
    "model.safetensors",
    "tf_model.h5",
    "flax_model.msgpack",
}
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
LICENSE_FRONT_MATTER = re.compile(
    r"^---\s*\n(?P<header>.*?)\n---(?:\s*\n|$)", re.DOTALL
)


class ValidationError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def sha256_file(path: Path, chunk_bytes: int = 8 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_bytes):
            digest.update(chunk)
    return digest.hexdigest()


def git_blob_oid(path: Path, chunk_bytes: int = 8 << 20) -> str:
    size = path.stat().st_size
    digest = hashlib.sha1()
    digest.update(f"blob {size}\0".encode("ascii"))
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_bytes):
            digest.update(chunk)
    return digest.hexdigest()


def git_blob_oid_bytes(data: bytes) -> str:
    digest = hashlib.sha1()
    digest.update(f"blob {len(data)}\0".encode("ascii"))
    digest.update(data)
    return digest.hexdigest()


def lfs_pointer_git_oid(sha256: str, size: int) -> str:
    pointer = (
        "version https://git-lfs.github.com/spec/v1\n"
        f"oid sha256:{sha256}\n"
        f"size {size}\n"
    ).encode("ascii")
    return git_blob_oid_bytes(pointer)


def parse_readme_license(readme: bytes) -> str | None:
    text = readme.decode("utf-8")
    match = LICENSE_FRONT_MATTER.match(text)
    if not match:
        return None
    values = []
    for line in match.group("header").splitlines():
        key, separator, value = line.partition(":")
        if separator and key.strip().lower() == "license":
            normalized = value.strip().strip("\"'")
            if normalized:
                values.append(normalized)
    if len(values) > 1:
        raise ValidationError("AMBIGUOUS_README_LICENSE")
    return values[0] if values else None


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def atomic_json(path: Path, value: Any, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with temp.open("w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.chmod(temp, mode)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def validate_plan(plan: dict[str, Any]) -> list[dict[str, Any]]:
    if plan.get("repo_id") != REPO_ID or plan.get("revision") != REVISION:
        raise ValidationError("PLAN_IDENTITY_MISMATCH")
    if plan.get("cap_bytes") != CAP_BYTES:
        raise ValidationError("PLAN_CAP_MISMATCH")
    allowlist = plan.get("allowlist")
    if not isinstance(allowlist, list) or not allowlist:
        raise ValidationError("EMPTY_ALLOWLIST")
    names = [item.get("path") for item in allowlist]
    if len(names) != len(set(names)):
        raise ValidationError("DUPLICATE_ALLOWLIST_PATH")
    if any(not isinstance(name, str) or Path(name).name != name for name in names):
        raise ValidationError("NON_FLAT_OR_INVALID_ALLOWLIST_PATH")
    weights = set(names) & WEIGHT_NAMES
    if weights != {"pytorch_model.bin"}:
        raise ValidationError("WEIGHT_ALLOWLIST_NOT_MINIMAL")
    total = 0
    for item in allowlist:
        size = item.get("expected_bytes")
        oid = item.get("git_oid")
        lfs = item.get("lfs_sha256")
        if not isinstance(size, int) or size <= 0:
            raise ValidationError("INVALID_EXPECTED_SIZE")
        if not isinstance(oid, str) or not HEX40.fullmatch(oid):
            raise ValidationError("INVALID_GIT_OID")
        if lfs is not None and (not isinstance(lfs, str) or not HEX64.fullmatch(lfs)):
            raise ValidationError("INVALID_LFS_SHA256")
        if lfs is not None and oid != lfs_pointer_git_oid(lfs, size):
            raise ValidationError("LFS_POINTER_GIT_OID_MISMATCH")
        total += size
    if total != plan.get("expected_payload_bytes"):
        raise ValidationError("PAYLOAD_SUM_MISMATCH")
    if total > CAP_BYTES:
        raise ValidationError("CAP_OVERFLOW")
    return allowlist


def validate_metadata(
    plan: dict[str, Any],
    model_api: dict[str, Any],
    tree: list[dict[str, Any]],
    readme: bytes | None = None,
) -> dict[str, Any]:
    if model_api.get("id") != REPO_ID or model_api.get("sha") != REVISION:
        raise ValidationError("MODEL_API_IDENTITY_MISMATCH")
    if model_api.get("private") is not False or bool(model_api.get("gated")):
        raise ValidationError("MODEL_NOT_PUBLIC_UNGATED")
    by_path = {item.get("path"): item for item in tree if item.get("type") == "file"}
    for expected in validate_plan(plan):
        actual = by_path.get(expected["path"])
        if actual is None:
            raise ValidationError(f"METADATA_FILE_MISSING:{expected['path']}")
        if actual.get("size") != expected["expected_bytes"]:
            raise ValidationError(f"METADATA_SIZE_MISMATCH:{expected['path']}")
        if actual.get("oid") != expected["git_oid"]:
            raise ValidationError(f"METADATA_OID_MISMATCH:{expected['path']}")
        if expected["lfs_sha256"] is not None:
            if (actual.get("lfs") or {}).get("oid") != expected["lfs_sha256"]:
                raise ValidationError(f"METADATA_LFS_MISMATCH:{expected['path']}")
    if len(by_path) != len([item for item in tree if item.get("type") == "file"]):
        raise ValidationError("DUPLICATE_METADATA_PATH")
    tags = model_api.get("tags") or []
    card_data = model_api.get("cardData") or {}
    if "README.md" not in by_path:
        raise ValidationError("MODEL_CARD_MISSING")
    if readme is not None:
        readme_item = by_path["README.md"]
        if len(readme) != readme_item.get("size"):
            raise ValidationError("README_SIZE_MISMATCH")
        if git_blob_oid_bytes(readme) != readme_item.get("oid"):
            raise ValidationError("README_GIT_OID_MISMATCH")
    candidates: list[tuple[str, str]] = []
    card_license = card_data.get("license")
    if isinstance(card_license, str) and card_license.strip():
        candidates.append(("model_api_card_data", card_license.strip()))
    for tag in tags:
        if str(tag).startswith("license:") and str(tag).split(":", 1)[1].strip():
            candidates.append(("model_api_tag", str(tag).split(":", 1)[1].strip()))
    if readme is not None:
        readme_license = parse_readme_license(readme)
        if readme_license:
            candidates.append(("readme_front_matter", readme_license))
    distinct = {value.lower() for _, value in candidates}
    if len(distinct) > 1:
        raise ValidationError("AMBIGUOUS_LICENSE_EVIDENCE")
    declared = candidates[0][1] if candidates else None
    return {
        "model_card_present": True,
        "model_card_git_oid": by_path["README.md"]["oid"],
        "declared_license": declared,
        "license_status": "DECLARED" if declared else "UNDECLARED",
        "license_evidence": [
            {"source": source, "value": value} for source, value in candidates
        ],
    }


def validate_snapshot(
    plan: dict[str, Any], snapshot: Path, expected_hashes: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    if not snapshot.is_dir() or snapshot.is_symlink():
        raise ValidationError("SNAPSHOT_DIRECTORY_INVALID")
    allowed = {item["path"]: item for item in validate_plan(plan)}
    expected_names = set(allowed) | {"SHA256SUMS"}
    actual_names: set[str] = set()
    for entry in snapshot.iterdir():
        if entry.is_symlink():
            raise ValidationError(f"SYMLINK_PROHIBITED:{entry.name}")
        if not entry.is_file():
            raise ValidationError(f"NON_FILE_PROHIBITED:{entry.name}")
        actual_names.add(entry.name)
    if actual_names != expected_names:
        raise ValidationError(
            f"FILE_SET_MISMATCH:missing={sorted(expected_names-actual_names)}:"
            f"extra={sorted(actual_names-expected_names)}"
        )
    records = []
    for name, expected in allowed.items():
        path = snapshot / name
        if stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise ValidationError(f"FILE_PERMISSIONS_TOO_BROAD:{name}")
        size = path.stat().st_size
        digest = sha256_file(path)
        oid = (
            lfs_pointer_git_oid(expected["lfs_sha256"], size)
            if expected["lfs_sha256"]
            else git_blob_oid(path)
        )
        if size != expected["expected_bytes"]:
            raise ValidationError(f"LOCAL_SIZE_MISMATCH:{name}")
        if oid != expected["git_oid"]:
            raise ValidationError(f"LOCAL_GIT_OID_MISMATCH:{name}")
        if expected["lfs_sha256"] and digest != expected["lfs_sha256"]:
            raise ValidationError(f"LOCAL_LFS_HASH_MISMATCH:{name}")
        if expected_hashes is not None and expected_hashes.get(name) != digest:
            raise ValidationError(f"MANIFEST_HASH_MISMATCH:{name}")
        records.append(
            {"path": name, "bytes": size, "sha256": digest, "git_oid": oid}
        )
    if stat.S_IMODE((snapshot / "SHA256SUMS").stat().st_mode) & 0o077:
        raise ValidationError("FILE_PERMISSIONS_TOO_BROAD:SHA256SUMS")
    parsed: dict[str, str] = {}
    for line in (snapshot / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([^/]+)", line)
        if not match or match.group(2) in parsed:
            raise ValidationError("INVALID_SHA256SUMS")
        parsed[match.group(2)] = match.group(1)
    actual_hashes = {item["path"]: item["sha256"] for item in records}
    if parsed != actual_hashes:
        raise ValidationError("SHA256SUMS_CONTENT_MISMATCH")
    if stat.S_IMODE(snapshot.stat().st_mode) & 0o077:
        raise ValidationError("SNAPSHOT_PERMISSIONS_TOO_BROAD")
    return records


def validate_manifest_gates(manifest: dict[str, Any]) -> None:
    """Keep restricted technical use separate from release authorization."""
    if manifest.get("decision") != OVERALL_DECISION:
        raise ValidationError("OVERALL_DECISION_MISMATCH")
    if (
        manifest.get("technical_inference_decision")
        != TECHNICAL_INFERENCE_DECISION
    ):
        raise ValidationError("TECHNICAL_INFERENCE_DECISION_MISMATCH")
    if manifest.get("redistribution_decision") != REDISTRIBUTION_DECISION:
        raise ValidationError("REDISTRIBUTION_DECISION_MISMATCH")
    restrictions = manifest.get("restrictions")
    if not isinstance(restrictions, dict):
        raise ValidationError("RESTRICTIONS_MISSING")
    if restrictions.get("restricted") is not True:
        raise ValidationError("RESTRICTED_STORAGE_REQUIRED")
    if restrictions.get("redistribution_authorized") is not False:
        raise ValidationError("REDISTRIBUTION_MUST_REMAIN_CLOSED")
    if manifest.get("acquisition", {}).get("completed") is not True:
        raise ValidationError("ACQUISITION_NOT_COMPLETED")
    verification = manifest.get("verification")
    if not isinstance(verification, dict) or not all(
        verification.get(field) is True
        for field in (
            "complete_file_set_verified",
            "local_sha256_verified",
            "offline_local_files_only_load",
            "synthetic_image_embedding",
            "text_embedding",
            "deterministic_replay",
        )
    ):
        raise ValidationError("TECHNICAL_VERIFICATION_INCOMPLETE")


def offline_smoke(snapshot: Path) -> dict[str, Any]:
    # Transformers 5.2 still touches aliases removed from NumPy 2 while importing
    # some optional audio modules. This is local runtime compatibility only.
    import numpy as np

    if "long" not in np.__dict__:
        np.long = np.int64  # type: ignore[attr-defined]
    if "ulong" not in np.__dict__:
        np.ulong = np.uint64  # type: ignore[attr-defined]

    os.environ.update(
        {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "HF_DATASETS_OFFLINE": "1",
        }
    )
    for key in list(os.environ):
        if key.upper() in {"HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"}:
            os.environ.pop(key, None)

    import PIL
    import torch
    import transformers
    from PIL import Image
    from transformers import CLIPModel, CLIPProcessor

    torch.manual_seed(0)
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(1)
    load_parameters = {
        "local_files_only": True,
        "device": "cpu",
        "torch_num_threads": 1,
        "torch_seed": 0,
        "deterministic_algorithms": True,
        "processor_use_fast": False,
    }
    model = CLIPModel.from_pretrained(snapshot, local_files_only=True)
    processor = CLIPProcessor.from_pretrained(
        snapshot, local_files_only=True, use_fast=False
    )
    model.eval()
    pixels = np.zeros((224, 224, 3), dtype=np.uint8)
    pixels[:, :, 0] = np.arange(224, dtype=np.uint8)[None, :]
    pixels[:, :, 1] = np.arange(224, dtype=np.uint8)[:, None]
    pixels[:, :, 2] = 127
    image = Image.fromarray(pixels, mode="RGB")
    inputs = processor(
        text=["a synthetic red and green gradient"],
        images=image,
        return_tensors="pt",
        padding=True,
    )

    def run_once() -> tuple[Any, Any, Any]:
        with torch.inference_mode():
            outputs = model(
                pixel_values=inputs["pixel_values"],
                input_ids=inputs["input_ids"],
                attention_mask=inputs["attention_mask"],
                return_dict=True,
            )
            image_features = outputs.image_embeds
            text_features = outputs.text_embeds
            image_norm = torch.nn.functional.normalize(image_features, dim=-1)
            text_norm = torch.nn.functional.normalize(text_features, dim=-1)
            similarity = image_norm @ text_norm.T
        return image_norm.cpu(), text_norm.cpu(), similarity.cpu()

    first = run_once()
    second = run_once()
    exact = all(torch.equal(left, right) for left, right in zip(first, second))
    if not exact:
        raise ValidationError("DETERMINISTIC_REPLAY_MISMATCH")
    similarity = float(first[2][0, 0])
    if not (-1.000001 <= similarity <= 1.000001):
        raise ValidationError("NORMALIZED_SIMILARITY_OUT_OF_RANGE")
    return {
        "local_files_only": True,
        "synthetic_image_persisted": False,
        "text": "a synthetic red and green gradient",
        "image_embedding_shape": list(first[0].shape),
        "text_embedding_shape": list(first[1].shape),
        "normalized_similarity": similarity,
        "deterministic_replay_exact": exact,
        "model_class": type(model).__name__,
        "processor_class": type(processor).__name__,
        "load_parameters": load_parameters,
        "input_parameters": {
            "image_mode": "RGB",
            "image_size": [224, 224],
            "image_pattern": "uint8_xy_gradient_blue_127",
            "padding": True,
            "return_tensors": "pt",
        },
        "runtime": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "numpy": np.__version__,
            "pillow": PIL.__version__,
            "device": "cpu",
            "dtype": str(next(model.parameters()).dtype),
            "torch_num_threads": torch.get_num_threads(),
            "zlib": zlib.ZLIB_RUNTIME_VERSION,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--validate-existing", action="store_true")
    parser.add_argument("--offline-smoke", action="store_true")
    args = parser.parse_args()
    root = args.repo_root.resolve()
    plan = load_json(root / PLAN_PATH)
    validate_plan(plan)
    if not args.validate_existing:
        print("PLAN_VALID")
        return 0
    manifest = load_json(root / MANIFEST_PATH)
    validate_manifest_gates(manifest)
    expected_hashes = {
        item["path"]: item["sha256"] for item in manifest.get("files", [])
    }
    records = validate_snapshot(plan, root / FINAL_DIR, expected_hashes)
    smoke = offline_smoke(root / FINAL_DIR) if args.offline_smoke else None
    print(
        json.dumps(
            {
                "status": "VALID",
                "validated_at": utc_now(),
                "files": len(records),
                "payload_bytes": sum(item["bytes"] for item in records),
                "offline_smoke": smoke,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as error:
        print(f"NO_GO:{error}", file=sys.stderr)
        raise SystemExit(2)
