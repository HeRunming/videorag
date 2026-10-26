"""Fail-closed prerequisite gates for the learned G/A pilot."""

from __future__ import annotations

import hashlib
import json
import re
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any

EXPECTED_QWEN_REPO = "Qwen/Qwen2.5-1.5B-Instruct"
EXPECTED_QWEN_REVISION = "989aa7980e4cf806f80c7fef2b1adb7bc71aa306"
QWEN_READY = "QWEN_GROUNDED_GENERATOR_SNAPSHOT_READY"

REQUIRED = {
    "thesis": Path("docs/paper/cvpr_thesis_and_evidence_gates.md"),
    "claim_ledger": Path("data/rehearsal_plan/cvpr_claim_evidence_ledger.json"),
    "construct_plan": Path("data/rehearsal_plan/construct_validity_mini_pilot_plan.json"),
    "qwen_manifest": Path("data/restricted/scale1b/manifests/ga_model_acquisition.json"),
    "wave_r_audit": Path("data/restricted/scale1b/wave_r/final_post_repair_audit.json"),
    "scale1a_audit": Path("data/restricted/noaa01/scale1a/final_audit.json"),
}


class GateError(RuntimeError):
    pass


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _find_values(value: Any, key_fragment: str) -> list[Any]:
    output: list[Any] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key_fragment.casefold() in str(key).casefold():
                output.append(child)
            output.extend(_find_values(child, key_fragment))
    elif isinstance(value, list):
        for child in value:
            output.extend(_find_values(child, key_fragment))
    return output


def _decision_values(document: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(document, str):
        if re.fullmatch(r"[A-Z][A-Z0-9_]+", document):
            found.add(document)
    elif isinstance(document, Mapping):
        for value in document.values():
            found.update(_decision_values(value))
    elif isinstance(document, list):
        for value in document:
            found.update(_decision_values(value))
    return found


def verify_qwen_manifest(repo_root: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    decisions = _decision_values(manifest)
    if QWEN_READY not in decisions:
        errors.append("QWEN_TECHNICAL_GATE_NOT_READY")
    repo_values = [str(x) for x in _find_values(manifest, "repo") if isinstance(x, str)]
    revision_values = [
        str(x) for x in _find_values(manifest, "revision") if isinstance(x, str)
    ]
    if EXPECTED_QWEN_REPO not in repo_values:
        errors.append("QWEN_REPO_MISMATCH")
    if EXPECTED_QWEN_REVISION not in revision_values:
        errors.append("QWEN_REVISION_MISMATCH")
    path_values = [
        str(x)
        for fragment in ("snapshot_dir", "snapshot_path", "model_path")
        for x in _find_values(manifest, fragment)
        if isinstance(x, str)
    ]
    snapshot: Path | None = None
    for value in path_values:
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = repo_root / candidate
        if candidate.is_dir() and not candidate.is_symlink():
            snapshot = candidate
            break
    if snapshot is None:
        expected = (
            repo_root
            / "data/restricted/scale1b/models/"
            "Qwen--Qwen2.5-1.5B-Instruct--989aa7980e4c"
        )
        if expected.is_dir() and not expected.is_symlink():
            snapshot = expected
        else:
            errors.append("QWEN_SNAPSHOT_MISSING")
    files = [
        item
        for item in _find_values(manifest, "files")
        if isinstance(item, list)
        and all(isinstance(row, Mapping) for row in item)
    ]
    verified_files = 0
    if snapshot is not None and files:
        candidate_set = max(files, key=len)
        for row in candidate_set:
            relative = row.get("path")
            expected_hash = str(row.get("sha256", "")).removeprefix("sha256:")
            expected_bytes = row.get("bytes")
            if not isinstance(relative, str):
                continue
            path = snapshot / relative
            if not path.is_file() or path.is_symlink():
                errors.append(f"QWEN_FILE_MISSING:{relative}")
                continue
            if isinstance(expected_bytes, int) and path.stat().st_size != expected_bytes:
                errors.append(f"QWEN_FILE_SIZE:{relative}")
                continue
            if re.fullmatch(r"[a-f0-9]{64}", expected_hash) and _sha256(path) != expected_hash:
                errors.append(f"QWEN_FILE_HASH:{relative}")
                continue
            verified_files += 1
    elif snapshot is not None:
        errors.append("QWEN_FILE_MANIFEST_MISSING")
    if snapshot is not None:
        mode = stat.S_IMODE(snapshot.stat().st_mode)
        if mode & 0o077:
            errors.append("QWEN_SNAPSHOT_PERMISSIONS")
    return {
        "ready": not errors,
        "errors": errors,
        "snapshot_path": str(snapshot) if snapshot else None,
        "repo_id": EXPECTED_QWEN_REPO,
        "revision": EXPECTED_QWEN_REVISION,
        "verified_files": verified_files,
        "manifest_sha256": _sha256(
            repo_root / REQUIRED["qwen_manifest"]
        ),
    }


def verify_prerequisite_gates(repo_root: str | Path = ".") -> dict[str, Any]:
    root = Path(repo_root).resolve()
    missing = [
        str(relative) for relative in REQUIRED.values() if not (root / relative).is_file()
    ]
    result: dict[str, Any] = {
        "schema_version": "av-trace.scale1b.ga-gates/1.0",
        "ready": False,
        "missing": missing,
        "errors": [],
        "inputs": {},
    }
    if missing:
        result["errors"].append("PREREQUISITE_ARTIFACTS_MISSING")
        return result
    documents = {
        name: _load(root / relative)
        for name, relative in REQUIRED.items()
        if relative.suffix == ".json"
    }
    result["inputs"] = {
        name: {
            "path": str(relative),
            "sha256": _sha256(root / relative),
        }
        for name, relative in REQUIRED.items()
    }
    wave = documents["wave_r_audit"]
    scale = documents["scale1a_audit"]
    if not wave.get("passed"):
        result["errors"].append("WAVE_R_FINAL_AUDIT_NOT_PASSED")
    if wave.get("decisions", {}).get("retrieval") != "LEARNED_RETRIEVAL_READY":
        result["errors"].append("LEARNED_RETRIEVAL_NOT_READY")
    if scale.get("decisions", {}).get("engineering") != "SCALE1A_ENGINEERING_GO":
        result["errors"].append("SCALE1A_ENGINEERING_NOT_READY")
    qwen = verify_qwen_manifest(root, documents["qwen_manifest"])
    result["qwen"] = qwen
    result["errors"].extend(qwen["errors"])
    ledger = documents["claim_ledger"]
    if ledger.get("decision") != "CVPR_THESIS_FROZEN":
        result["errors"].append("CVPR_THESIS_NOT_FROZEN")
    construct = documents["construct_plan"]
    if construct.get("decision") != "DEFERRED_HUMAN_PROTOCOL_READY":
        result["errors"].append("CONSTRUCT_VALIDITY_PROTOCOL_NOT_READY")
    if not construct:
        result["errors"].append("CONSTRUCT_VALIDITY_PLAN_EMPTY")
    result["ready"] = not result["errors"]
    return result
