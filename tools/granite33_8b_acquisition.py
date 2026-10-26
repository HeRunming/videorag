#!/usr/bin/env python3
"""Task 169 fail-closed Granite acquisition and CPU load-smoke utility.

The checked-in default is validation/preflight only. Network transfer requires
an explicit ``--execute`` and uses the exact revision and allowlist in the plan.
The CPU child never downloads or calls an API.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import resource
import shutil
import socket
import stat
import subprocess
import sys
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

from av_trace_strong_baselines.errors import SchemaViolation
from av_trace_strong_baselines.runtime import SCHEMA_REPAIRABLE_ERRORS
from av_trace_strong_baselines.schemas import (
    parse_strict_json,
    validate_evidence_state,
    validate_final_answer_envelope,
)
from av_trace_strong_baselines.security import (
    ObservedEvidenceLock,
    OutputProvenance,
)

PLAN = Path("data/acquisition_plan/granite33_8b_acquisition_plan.json")
MANIFEST = Path(
    "data/restricted/strong_baselines/manifests/"
    "granite33_8b_acquisition.json"
)
REPO_ID = "ibm-granite/granite-3.3-8b-instruct"
REVISION = "51dd4bc2ade4059a6bd87649d68aa11e4fb2529b"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
FORBIDDEN_SUFFIXES = {
    ".bin",
    ".ckpt",
    ".h5",
    ".msgpack",
    ".onnx",
    ".py",
    ".so",
    ".dll",
    ".dylib",
}
SAFE_METADATA = {
    ".gitattributes",
    "README.md",
    "added_tokens.json",
    "config.json",
    "generation_config.json",
    "merges.txt",
    "model.safetensors.index.json",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.json",
}
SMOKE_SCHEMA_REPAIRABLE_ERRORS = SCHEMA_REPAIRABLE_ERRORS | {
    "COVERED_CLAIMS_TYPE",
    "MISSING_MODALITIES_TYPE",
    "MISSING_HOPS_TYPE",
}


class AcquisitionError(RuntimeError):
    pass


def utc_now() -> str:
    return (
        datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        temporary.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


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
    pointer = (
        "version https://git-lfs.github.com/spec/v1\n"
        f"oid sha256:{sha256}\n"
        f"size {size}\n"
    ).encode()
    return git_blob_oid_bytes(pointer)


def validate_plan(plan: dict[str, Any]) -> None:
    model = plan.get("model")
    if not isinstance(model, dict):
        raise AcquisitionError("MODEL_MISSING")
    if model.get("repo_id") != REPO_ID or model.get("revision") != REVISION:
        raise AcquisitionError("MODEL_IDENTITY_MISMATCH")
    if not HEX40.fullmatch(REVISION):
        raise AcquisitionError("REVISION_NOT_IMMUTABLE")
    files = model.get("allowlist")
    if not isinstance(files, list) or not files:
        raise AcquisitionError("ALLOWLIST_EMPTY")
    names = [item.get("path") for item in files]
    if len(names) != len(set(names)) or any(
        not isinstance(name, str) or Path(name).name != name for name in names
    ):
        raise AcquisitionError("ALLOWLIST_PATH_INVALID")
    required_shards = set(model["weight_layout"]["required_shards"])
    if required_shards != {
        "model-00001-of-00004.safetensors",
        "model-00002-of-00004.safetensors",
        "model-00003-of-00004.safetensors",
        "model-00004-of-00004.safetensors",
    }:
        raise AcquisitionError("SHARD_SET_MISMATCH")
    if set(names) & required_shards != required_shards:
        raise AcquisitionError("SHARDS_NOT_ALLOWLISTED")
    if set(names) & {"model.safetensors.index.json"} != {
        "model.safetensors.index.json"
    }:
        raise AcquisitionError("INDEX_NOT_ALLOWLISTED")
    total = 0
    weight_total = 0
    for item in files:
        size = item.get("expected_bytes")
        oid = item.get("git_oid")
        lfs = item.get("lfs_sha256")
        if (
            not isinstance(size, int)
            or size <= 0
            or not isinstance(oid, str)
            or not HEX40.fullmatch(oid)
        ):
            raise AcquisitionError(f"FILE_METADATA_INVALID:{item.get('path')}")
        if lfs is not None:
            if not isinstance(lfs, str) or not HEX64.fullmatch(lfs):
                raise AcquisitionError(f"LFS_HASH_INVALID:{item['path']}")
            if lfs_pointer_git_oid(lfs, size) != oid:
                raise AcquisitionError(f"LFS_POINTER_OID_MISMATCH:{item['path']}")
            weight_total += size
        total += size
    if total != model.get("expected_payload_bytes"):
        raise AcquisitionError("PAYLOAD_TOTAL_MISMATCH")
    if weight_total != model.get("expected_weight_bytes"):
        raise AcquisitionError("WEIGHT_TOTAL_MISMATCH")
    caps = plan.get("caps") or {}
    if total > caps.get("selected_payload_bytes", 0):
        raise AcquisitionError("PAYLOAD_CAP_EXCEEDED")
    runtime = plan.get("runtime_canary") or {}
    if runtime.get("device") != "cpu" or runtime.get("trust_remote_code") is not False:
        raise AcquisitionError("RUNTIME_POLICY_MISMATCH")
    if runtime.get("case_ids") != ["sbc-controller-001", "sbc-finalizer-001"]:
        raise AcquisitionError("TASK158_CASE_SET_MISMATCH")
    if runtime.get("max_new_tokens_per_case") != 512:
        raise AcquisitionError("TASK158_OUTPUT_CAP_MISMATCH")
    if runtime.get("schema_only_retries_per_case") != 1:
        raise AcquisitionError("TASK158_SCHEMA_REPAIR_CAP_MISMATCH")


def validate_official_metadata(
    plan: dict[str, Any],
    api: dict[str, Any],
    tree: list[dict[str, Any]],
    readme: bytes,
) -> dict[str, Any]:
    model = plan["model"]
    if api.get("id") != REPO_ID or api.get("sha") != REVISION:
        raise AcquisitionError("OFFICIAL_API_IDENTITY_MISMATCH")
    if api.get("private") is not False or bool(api.get("gated")):
        raise AcquisitionError("MODEL_NOT_PUBLIC_UNGATED")
    by_path = {
        item.get("path"): item for item in tree if item.get("type") == "file"
    }
    for expected in model["allowlist"]:
        actual = by_path.get(expected["path"])
        if (
            not actual
            or actual.get("size") != expected["expected_bytes"]
            or actual.get("oid") != expected["git_oid"]
        ):
            raise AcquisitionError(f"OFFICIAL_TREE_MISMATCH:{expected['path']}")
        if expected["lfs_sha256"] and (
            (actual.get("lfs") or {}).get("oid")
            != expected["lfs_sha256"]
        ):
            raise AcquisitionError(
                f"OFFICIAL_TREE_LFS_MISMATCH:{expected['path']}"
            )
    tree_names = set(by_path)
    unexpected_risky = sorted(
        name
        for name in tree_names
        if Path(name).suffix.lower() in FORBIDDEN_SUFFIXES
    )
    if unexpected_risky:
        raise AcquisitionError(f"RISKY_TREE_FILE:{unexpected_risky}")
    if tree_names != SAFE_METADATA | set(
        model["weight_layout"]["required_shards"]
    ):
        raise AcquisitionError("OFFICIAL_TREE_FILE_SET_CHANGED")
    readme_entry = by_path.get("README.md")
    if (
        not readme_entry
        or len(readme) != readme_entry["size"]
        or git_blob_oid_bytes(readme) != readme_entry["oid"]
    ):
        raise AcquisitionError("README_IDENTITY_MISMATCH")
    text = readme.decode("utf-8", "strict")
    declared = {
        str((api.get("cardData") or {}).get("license", "")).lower(),
        *{
            str(tag).split(":", 1)[1].lower()
            for tag in api.get("tags", [])
            if str(tag).startswith("license:")
        },
    }
    if declared != {"apache-2.0"} or "license: apache-2.0" not in text.lower():
        raise AcquisitionError("LICENSE_DECLARATION_MISMATCH")
    return {
        "declared_license": "apache-2.0",
        "license_text_in_exact_repository": False,
        "license_text_status": (
            "No LICENSE or NOTICE file exists in the exact 15-file revision; "
            "the exact model card links to the canonical Apache-2.0 license."
        ),
        "tree_file_count": len(tree_names),
        "risky_code_or_pickle_files": unexpected_risky,
    }


def exact_url(model: dict[str, Any], name: str, endpoint: str) -> str:
    repo = "/".join(quote(part, safe="") for part in model["repo_id"].split("/"))
    return (
        f"{endpoint.rstrip('/')}/{repo}/resolve/{model['revision']}/"
        f"{quote(name, safe='')}"
    )


def _curl(
    url: str,
    output: Path,
    *,
    proxy: str,
    headers: Path,
    resume: bool,
    max_time: int,
) -> None:
    command = [
        "curl",
        "--fail",
        "--location",
        "--silent",
        "--show-error",
        "--retry",
        "3",
        "--retry-delay",
        "2",
        "--connect-timeout",
        "20",
        "--max-time",
        str(max_time),
        "--proxy",
        proxy,
        "--dump-header",
        str(headers),
    ]
    if resume and output.exists():
        command += ["--continue-at", "-"]
    command += ["--output", str(output), url]
    subprocess.run(command, check=True)


def _header_values(path: Path, names: set[str]) -> set[str]:
    values: set[str] = set()
    for line in path.read_text("iso-8859-1").splitlines():
        key, separator, value = line.partition(":")
        if separator and key.strip().lower() in names:
            values.add(value.strip().strip('"'))
    return values


def _file_complete(path: Path, expected: dict[str, Any]) -> bool:
    if not path.is_file() or path.is_symlink():
        return False
    if path.stat().st_size != expected["expected_bytes"]:
        return False
    if expected["lfs_sha256"]:
        return sha256_file(path) == expected["lfs_sha256"]
    return git_blob_oid(path) == expected["git_oid"]


def validate_snapshot(plan: dict[str, Any], snapshot: Path) -> list[dict[str, Any]]:
    model = plan["model"]
    if (
        not snapshot.is_dir()
        or snapshot.is_symlink()
        or stat.S_IMODE(snapshot.stat().st_mode) != 0o700
    ):
        raise AcquisitionError("SNAPSHOT_DIRECTORY_MODE")
    allowed = {item["path"]: item for item in model["allowlist"]}
    actual = {item.name for item in snapshot.iterdir()}
    if actual != set(allowed) | {"LOCAL_MANIFEST.json", "SHA256SUMS"}:
        raise AcquisitionError("SNAPSHOT_FILE_SET_MISMATCH")
    rows: list[dict[str, Any]] = []
    for name, expected in allowed.items():
        path = snapshot / name
        if path.is_symlink() or not path.is_file():
            raise AcquisitionError(f"SNAPSHOT_NON_REGULAR:{name}")
        if stat.S_IMODE(path.stat().st_mode) != 0o600:
            raise AcquisitionError(f"SNAPSHOT_FILE_MODE:{name}")
        digest = sha256_file(path)
        identity = (
            expected["lfs_sha256"]
            if expected["lfs_sha256"]
            else git_blob_oid(path)
        )
        if (
            path.stat().st_size != expected["expected_bytes"]
            or identity
            != (expected["lfs_sha256"] or expected["git_oid"])
        ):
            raise AcquisitionError(f"SNAPSHOT_IDENTITY:{name}")
        rows.append(
            {
                "path": name,
                "bytes": path.stat().st_size,
                "sha256": digest,
                "upstream_identity": identity,
                "upstream_identity_kind": (
                    "lfs_sha256" if expected["lfs_sha256"] else "git_blob_oid"
                ),
            }
        )
    index = load_json(snapshot / model["weight_layout"]["index"])
    referenced = set((index.get("weight_map") or {}).values())
    if referenced != set(model["weight_layout"]["required_shards"]):
        raise AcquisitionError("SAFETENSORS_INDEX_SHARD_SET")
    from safetensors import safe_open

    keys: set[str] = set()
    for shard in sorted(referenced):
        with safe_open(snapshot / shard, framework="pt", device="cpu") as handle:
            keys.update(handle.keys())
    if keys != set(index.get("weight_map") or {}):
        raise AcquisitionError("SAFETENSORS_INDEX_TENSOR_SET")
    local_manifest = load_json(snapshot / "LOCAL_MANIFEST.json")
    if (
        local_manifest.get("repo_id") != REPO_ID
        or local_manifest.get("revision") != REVISION
        or local_manifest.get("files") != rows
    ):
        raise AcquisitionError("LOCAL_MANIFEST_MISMATCH")
    sums = {
        row.split("  ", 1)[1]: row.split("  ", 1)[0]
        for row in (snapshot / "SHA256SUMS").read_text().splitlines()
        if "  " in row
    }
    if sums != {row["path"]: row["sha256"] for row in rows}:
        raise AcquisitionError("SHA256SUMS_MISMATCH")
    return rows


@contextlib.contextmanager
def deny_network() -> Iterator[dict[str, int]]:
    attempts = {"count": 0}
    original_socket = socket.socket
    original_create = socket.create_connection

    def blocked(*args: Any, **kwargs: Any) -> Any:
        attempts["count"] += 1
        raise RuntimeError("NETWORK_ACCESS_FORBIDDEN_DURING_CPU_CANARY")

    socket.socket = blocked  # type: ignore[assignment]
    socket.create_connection = blocked  # type: ignore[assignment]
    try:
        yield attempts
    finally:
        socket.socket = original_socket  # type: ignore[assignment]
        socket.create_connection = original_create  # type: ignore[assignment]


def _offline_environment() -> None:
    os.environ.update(
        {
            "CUDA_VISIBLE_DEVICES": "",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "HF_DATASETS_OFFLINE": "1",
            "TOKENIZERS_PARALLELISM": "false",
        }
    )
    for name in list(os.environ):
        if name.lower() in {
            "http_proxy",
            "https_proxy",
            "all_proxy",
            "no_proxy",
        } or name.upper() in {"HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"}:
            os.environ.pop(name, None)


def _parse_and_validate_smoke_output(
    case: dict[str, Any], raw: str
) -> dict[str, Any]:
    try:
        value = parse_strict_json(raw, maximum_bytes=64_000)
        public = case["public_input"]
        if case["case_type"] == "controller":
            if not isinstance(value, dict) or set(value) != {
                "evidence_state",
                "action_index",
            }:
                raise SchemaViolation("CONTROLLER_DECISION_FIELD_SET")
            action_index = value["action_index"]
            action_menu = public["action_menu"]
            if (
                isinstance(action_index, bool)
                or not isinstance(action_index, int)
                or not 0 <= action_index < len(action_menu)
            ):
                raise SchemaViolation("CONTROLLER_ACTION_INDEX_INVALID")
            state = validate_evidence_state(
                value["evidence_state"],
                allowed_claim_handles=[
                    item["claim_handle"]
                    for item in public["public_claim_slots"]
                ],
            )
            if state["covered_claim_handles"] and not public[
                "observed_evidence"
            ]:
                raise SchemaViolation(
                    "COVERED_CLAIMS_WITHOUT_OBSERVED_EVIDENCE"
                )
            return {
                "evidence_state": state,
                "action_index": action_index,
            }
        if case["case_type"] == "finalizer":
            return validate_final_answer_envelope(
                value,
                claim_handles=[
                    item["claim_handle"]
                    for item in public["public_claim_slots"]
                ],
                evidence_lock=ObservedEvidenceLock(
                    public["observed_evidence"]
                ),
                provenance=OutputProvenance(
                    model_authored_paths=frozenset({"final_answer"})
                ),
            )
        raise AcquisitionError("UNSUPPORTED_TASK158_CASE_TYPE")
    except SchemaViolation as exc:
        raise AcquisitionError(f"SMOKE_OUTPUT_INVALID:{exc.code}") from exc


def _smoke_validation_code(error: str) -> str:
    return error.rsplit(":", 1)[-1]


def _schema_retry_allowed(error: str) -> bool:
    return _smoke_validation_code(error) in SMOKE_SCHEMA_REPAIRABLE_ERRORS


def _semantic_atoms(value: Any, key: str = "$") -> list[tuple[str, Any]]:
    if isinstance(value, dict):
        atoms = []
        for child_key, child in value.items():
            if child_key == "unit":
                continue
            atoms.extend(_semantic_atoms(child, child_key))
        return atoms
    if isinstance(value, list):
        atoms = []
        for child in value:
            atoms.extend(_semantic_atoms(child, key))
        return atoms
    return [(key, value)]


def _schema_retry_preserved_content(original: str, repaired: str) -> bool:
    try:
        before = parse_strict_json(original, maximum_bytes=64_000)
        after = parse_strict_json(repaired, maximum_bytes=64_000)
    except SchemaViolation:
        return True
    return sorted(
        _semantic_atoms(before), key=lambda item: (item[0], repr(item[1]))
    ) == sorted(
        _semantic_atoms(after), key=lambda item: (item[0], repr(item[1]))
    )


def _smoke_semantics(
    case: dict[str, Any], parsed: dict[str, Any]
) -> dict[str, Any]:
    target = case["scoring_target"]
    if case["case_type"] == "controller":
        state = parsed["evidence_state"]
        component_correct = {
            field: state[field] == target["expected_evidence_state"][field]
            for field in (
                "p_sufficient",
                "covered_claim_handles",
                "missing_modalities",
                "missing_hops",
                "missingness_cause",
                "recovery_intent",
            )
        }
        result = {
            "action_correct": (
                parsed["action_index"] == target["expected_action_index"]
            ),
            "state_component_correct": component_correct,
            "exact_six_field_state": all(component_correct.values()),
        }
        result["passed"] = (
            result["action_correct"] and result["exact_six_field_state"]
        )
        return result
    if case["case_type"] == "finalizer":
        final = parsed["final_answer"]
        claims = {
            claim["registered_claim_id"]: claim
            for claim in final["claims"]
        }
        support_correct = True
        unsupported_claims = 0
        for handle, terms in target["required_terms_by_claim"].items():
            claim = claims.get(handle)
            if claim is None:
                support_correct = False
                unsupported_claims += 1
                continue
            authored_answer_text = " ".join(
                (
                    claim["text"],
                    final["natural_language_answer"],
                )
            ).casefold()
            citations = {
                item["observation_id"] for item in claim["citations"]
            }
            if (
                any(
                    str(term).casefold() not in authored_answer_text
                    for term in terms
                )
                or not citations
                or not citations
                <= set(target["accepted_support"].get(handle, []))
            ):
                support_correct = False
                unsupported_claims += 1
        result = {
            "answer_mode_correct": (
                final["answer_mode"] == target["answer_mode"]
            ),
            "support_correct": support_correct,
            "unsupported_claims": unsupported_claims,
        }
        result["passed"] = (
            result["answer_mode_correct"]
            and result["support_correct"]
            and result["unsupported_claims"] == 0
        )
        return result
    raise AcquisitionError("UNSUPPORTED_TASK158_CASE_TYPE")


def _repair_messages(
    case: dict[str, Any],
    invalid_raw_output: str,
    validation_error_code: str,
) -> list[dict[str, str]]:
    return _messages(case) + [
        {"role": "assistant", "content": invalid_raw_output},
        {
            "role": "user",
            "content": (
                "Schema-only repair. Return the same attempted content in "
                "exactly the required JSON structure, with no markdown or "
                "extra text. Do not add facts, claims, citations, or answers. "
                f"Validation error: {validation_error_code}."
            ),
        },
    ]


def _task158_cases(root: Path, plan: dict[str, Any]) -> list[dict[str, Any]]:
    suite_path = root / plan["runtime_canary"]["task158_suite"]
    suite = load_json(suite_path)
    if suite.get("suite_hash") != plan["runtime_canary"]["task158_suite_hash"]:
        raise AcquisitionError("TASK158_SUITE_HASH_MISMATCH")
    by_id = {
        item["case_id"]: item
        for item in suite["cases"]["controller_finalizer"]
    }
    result = []
    for case_id in plan["runtime_canary"]["case_ids"]:
        item = by_id.get(case_id)
        if not item:
            raise AcquisitionError(f"TASK158_CASE_MISSING:{case_id}")
        result.append(
            {
                "case_id": case_id,
                "case_type": item["case_type"],
                "public_input": item["public_input"],
                "scoring_target": item["scoring_target"],
            }
        )
    return result


def _messages(case: dict[str, Any]) -> list[dict[str, str]]:
    if case["case_type"] == "controller":
        system = (
            "Return exactly one compact JSON object and no other text. Keys: "
            "evidence_state, action_index. evidence_state must have exactly "
            "p_sufficient (0|0.25|0.5|0.75|1), covered_claim_handles, "
            "missing_modalities (vision|speech|ambient), missing_hops, "
            "missingness_cause, recovery_intent. missing_hops values: "
            "entity_identity|event_detection|speech_content|ambient_event|"
            "temporal_order|cross_modal_binding|causal_link|state_change|"
            "comparison|counting|other. missingness_cause: "
            "source_evidence_absent|evidence_in_source_but_inaccessible|"
            "evidence_accessible_but_not_found|not_missing|uncertain. "
            "recovery_intent: none|search_vision|search_speech|search_ambient|"
            "observe_pointer|check_channel_status|retry_restored_route|"
            "finalize_answer|finalize_abstain. action_index must select the "
            "best supplied action. All list-valued fields must be JSON arrays, "
            "even with one item. If no evidence is observed yet and an "
            "applicable search action is available, the evidence is "
            "accessible_but_not_found, not source_evidence_absent. Use only "
            "public input."
        )
    elif case["case_type"] == "finalizer":
        system = (
            "Return exactly one compact JSON object and no other text. Use "
            "this exact shape and replace placeholders only with public input:"
            '{"final_answer":{"p_sufficient":1,"verdict":"sufficient",'
            '"answer_mode":"answer","claims":[{"claim_id":"public.1",'
            '"registered_claim_id":"PUBLIC_CLAIM_HANDLE","text":'
            '"GROUNDED_CLAIM_TEXT","confidence":1,"citations":['
            '{"observation_id":"PUBLIC_OBSERVATION_ID","interval":'
            '{"start_s":0,"end_s":1},"modalities":["vision"]}]}],'
            '"diagnosis":{"modality_probabilities":{"vision":1,"speech":0,'
            '"ambient":0},"hop_types":[],"cause_probabilities":{'
            '"source_evidence_absent":0,'
            '"evidence_in_source_but_inaccessible":0,'
            '"evidence_accessible_but_not_found":0,"not_missing":1,'
            '"uncertain":0},"recovery_route_declared":false,"description":'
            '"Complete public evidence."},"natural_language_answer":'
            '"GROUNDED_ANSWER","termination_reason":"sufficient_evidence"},'
            '"claim_to_citations":{"PUBLIC_CLAIM_HANDLE":'
            '["PUBLIC_OBSERVATION_ID"]}}. Objects must contain exactly those '
            "keys: citation interval has only start_s and end_s (never unit). "
            "registered_claim_id must copy the supplied claim_handle. Both "
            "claim text and natural_language_answer must state the factual "
            "answer found in the observed payload, not merely repeat the slot "
            "description. Use only public observed evidence."
        )
    else:
        raise AcquisitionError("UNSUPPORTED_TASK158_CASE_TYPE")
    return [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": json.dumps(
                case["public_input"], separators=(",", ":"), sort_keys=True
            ),
        },
    ]


def cpu_canary_child(root: Path, snapshot: Path, report: Path) -> None:
    plan = load_json(root / PLAN)
    validate_plan(plan)
    limits = plan["runtime_canary"]
    resource.setrlimit(
        resource.RLIMIT_AS,
        (limits["address_space_limit_bytes"], limits["address_space_limit_bytes"]),
    )
    resource.setrlimit(
        resource.RLIMIT_CORE,
        (0, 0),
    )
    _offline_environment()
    import numpy as np

    if "long" not in np.__dict__:
        np.long = np.int64  # type: ignore[attr-defined]
    if "ulong" not in np.__dict__:
        np.ulong = np.uint64  # type: ignore[attr-defined]
    import torch
    import transformers
    from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer

    torch.manual_seed(169)
    torch.set_num_threads(limits["threads"])
    started = time.perf_counter()
    with deny_network() as attempts:
        config = AutoConfig.from_pretrained(
            snapshot,
            local_files_only=True,
            trust_remote_code=False,
        )
        tokenizer_started = time.perf_counter()
        tokenizer = AutoTokenizer.from_pretrained(
            snapshot,
            local_files_only=True,
            trust_remote_code=False,
            use_fast=True,
        )
        tokenizer_seconds = time.perf_counter() - tokenizer_started
        model_started = time.perf_counter()
        model = AutoModelForCausalLM.from_pretrained(
            snapshot,
            local_files_only=True,
            trust_remote_code=False,
            dtype=torch.bfloat16,
            low_cpu_mem_usage=True,
            attn_implementation="eager",
        ).eval()
        model_seconds = time.perf_counter() - model_started
        parameter = next(model.parameters())
        outputs = []
        value = {
            "status": "LOAD_SMOKE_IN_PROGRESS",
            "scope": "tiny_fictional_public_task158_load_smoke_only",
            "competence_claimed": False,
            "repo_id": REPO_ID,
            "revision": REVISION,
            "local_files_only": True,
            "trust_remote_code": False,
            "network_attempts": attempts["count"],
            "device": str(parameter.device),
            "dtype": str(parameter.dtype),
            "model_class": type(model).__name__,
            "tokenizer_class": type(tokenizer).__name__,
            "config_model_type": getattr(config, "model_type", None),
            "tokenizer_load_seconds": tokenizer_seconds,
            "model_load_seconds": model_seconds,
            "runtime": {
                "python": sys.version.split()[0],
                "torch": torch.__version__,
                "transformers": transformers.__version__,
                "threads": torch.get_num_threads(),
            },
            "cases": outputs,
        }
        atomic_json(report, value)
        for case in _task158_cases(root, plan):
            attempts_for_case = []
            parsed = None
            final_error = None
            initial_raw = None
            messages = _messages(case)
            for attempt_index in range(
                1, 2 + limits["schema_only_retries_per_case"]
            ):
                rendered = tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True,
                    thinking=False,
                )
                inputs = tokenizer(rendered, return_tensors="pt")
                generation_started = time.perf_counter()
                with torch.inference_mode():
                    generated = model.generate(
                        **inputs,
                        do_sample=False,
                        max_new_tokens=limits["max_new_tokens_per_case"],
                        pad_token_id=tokenizer.eos_token_id,
                        eos_token_id=tokenizer.eos_token_id,
                    )
                generation_seconds = (
                    time.perf_counter() - generation_started
                )
                output_ids = generated[
                    0, inputs["input_ids"].shape[1] :
                ]
                raw = tokenizer.decode(
                    output_ids, skip_special_tokens=True
                ).strip()
                if initial_raw is None:
                    initial_raw = raw
                attempt = {
                    "attempt": attempt_index,
                    "kind": (
                        "initial" if attempt_index == 1 else "schema_only"
                    ),
                    "prompt_tokens": int(inputs["input_ids"].numel()),
                    "completion_tokens": int(output_ids.numel()),
                    "generation_seconds": generation_seconds,
                    "raw_output": raw,
                }
                attempts_for_case.append(attempt)
                case_report = {
                    "case_id": case["case_id"],
                    "case_type": case["case_type"],
                    "attempts": attempts_for_case,
                    "schema_repairs_used": len(attempts_for_case) - 1,
                    "strict_json_object": False,
                    "structural_grounding_valid": False,
                    "semantics": None,
                    "raw_output": raw,
                    "parsed_output": None,
                }
                value["active_case"] = case_report
                atomic_json(report, value)
                try:
                    parsed = _parse_and_validate_smoke_output(case, raw)
                    if (
                        attempt_index > 1
                        and initial_raw is not None
                        and not _schema_retry_preserved_content(
                            initial_raw, raw
                        )
                    ):
                        raise AcquisitionError(
                            "SMOKE_SCHEMA_RETRY_CHANGED_CONTENT"
                        )
                    final_error = None
                    break
                except AcquisitionError as exc:
                    final_error = str(exc)
                    attempt["validation_error"] = final_error
                    if (
                        attempt_index
                        == 1 + limits["schema_only_retries_per_case"]
                        or not _schema_retry_allowed(final_error)
                    ):
                        break
                    messages = _repair_messages(case, raw, final_error)
            if parsed is None:
                value["status"] = "LOAD_SMOKE_FAILED"
                value["failure"] = {
                    "case_id": case["case_id"],
                    "error": final_error,
                    "failure_kind": "STRUCTURAL_OR_GROUNDING",
                }
                value["active_case"] = case_report
                value["elapsed_seconds"] = time.perf_counter() - started
                value["peak_rss_kib"] = resource.getrusage(
                    resource.RUSAGE_SELF
                ).ru_maxrss
                atomic_json(report, value)
                raise AcquisitionError(
                    f"SMOKE_CASE_INVALID:{case['case_id']}:{final_error}"
                )
            semantics = _smoke_semantics(case, parsed)
            if not semantics["passed"]:
                case_report.update(
                    {
                        "strict_json_object": True,
                        "structural_grounding_valid": True,
                        "semantics": semantics,
                        "parsed_output": parsed,
                    }
                )
                value["status"] = "LOAD_SMOKE_FAILED"
                value["failure"] = {
                    "case_id": case["case_id"],
                    "error": "SMOKE_SEMANTICS_FAILED",
                    "failure_kind": "SEMANTIC",
                }
                value["active_case"] = case_report
                value["elapsed_seconds"] = time.perf_counter() - started
                value["peak_rss_kib"] = resource.getrusage(
                    resource.RUSAGE_SELF
                ).ru_maxrss
                atomic_json(report, value)
                raise AcquisitionError(
                    f"SMOKE_SEMANTICS_FAILED:{case['case_id']}"
                )
            case_report.update(
                {
                    "strict_json_object": True,
                    "structural_grounding_valid": True,
                    "semantics": semantics,
                    "parsed_output": parsed,
                }
            )
            outputs.append(case_report)
            value.pop("active_case", None)
            atomic_json(report, value)
    value["status"] = "LOAD_SMOKE_COMPLETE"
    value["elapsed_seconds"] = time.perf_counter() - started
    value["peak_rss_kib"] = resource.getrusage(
        resource.RUSAGE_SELF
    ).ru_maxrss
    atomic_json(report, value)


def run_cpu_canary(
    root: Path,
    snapshot: Path,
    report: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--repo-root",
        str(root),
        "--cpu-canary-child",
        "--snapshot",
        str(snapshot),
        "--smoke-report",
        str(report),
    ]
    environment = os.environ.copy()
    environment["CUDA_VISIBLE_DEVICES"] = ""
    for name in list(environment):
        if name.lower() in {
            "http_proxy",
            "https_proxy",
            "all_proxy",
            "no_proxy",
        } or name.upper() in {"HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"}:
            environment.pop(name, None)
    subprocess.run(
        command,
        check=True,
        timeout=timeout_seconds,
        env=environment,
    )
    value = load_json(report)
    if (
        value.get("status") != "LOAD_SMOKE_COMPLETE"
        or value.get("competence_claimed") is not False
        or value.get("network_attempts") != 0
        or value.get("device") != "cpu"
        or value.get("config_model_type") != "granite"
        or {case.get("case_id") for case in value.get("cases", [])}
        != {"sbc-controller-001", "sbc-finalizer-001"}
        or any(
            case.get("strict_json_object") is not True
            or case.get("structural_grounding_valid") is not True
            or (case.get("semantics") or {}).get("passed") is not True
            or case.get("schema_repairs_used") not in {0, 1}
            or not isinstance(case.get("attempts"), list)
            or len(case["attempts"]) != case["schema_repairs_used"] + 1
            or any(
                not isinstance(attempt.get("raw_output"), str)
                for attempt in case["attempts"]
            )
            for case in value.get("cases", [])
        )
    ):
        raise AcquisitionError("CPU_CANARY_RESULT_INVALID")
    return value


def finalize_verified_stage(
    root: Path,
    plan: dict[str, Any],
    smoke: dict[str, Any],
) -> dict[str, Any]:
    model = plan["model"]
    stage = root / model["staging_dir"]
    final = root / model["snapshot_dir"]
    records = root / model["metadata_dir"]
    if final.exists():
        raise AcquisitionError("FINAL_SNAPSHOT_ALREADY_EXISTS")
    if smoke.get("status") != "LOAD_SMOKE_COMPLETE":
        raise AcquisitionError("CPU_CANARY_NOT_COMPLETE")
    rows = validate_snapshot(plan, stage)
    os.replace(stage, final)
    rows = validate_snapshot(plan, final)
    for path in records.iterdir():
        if path.is_file():
            os.chmod(path, 0o600)
    manifest = load_json(root / MANIFEST)
    archived = manifest.get("archived_evidence") or {}
    api_path = records / "model_api.json"
    tree_path = records / "tree.json"
    if "exact_model_api" in archived and api_path.is_file():
        archived["exact_model_api"].update(
            {
                "sha256": sha256_file(api_path),
                "source_checked": (
                    "official Hugging Face exact-revision model API through "
                    "the required proxy"
                ),
                "source_checked_date": "2026-10-02",
            }
        )
    if "recursive_tree" in archived and tree_path.is_file():
        archived["recursive_tree"].update(
            {
                "archive_kind": (
                    "raw exact-revision recursive-tree endpoint response"
                ),
                "fresh_recursive_tree_endpoint_archive": True,
                "sha256": sha256_file(tree_path),
                "source_checked": (
                    "Official Hugging Face exact-revision recursive-tree "
                    "endpoint through the required proxy on 2026-10-02."
                ),
            }
        )
    manifest.update(
        {
            "updated_at": utc_now(),
            "decision": "GRANITE33_8B_ACQUISITION_READY",
            "status": "ACQUISITION_COMPLETE_CPU_LOAD_SMOKE_PASSED",
            "archived_evidence": archived,
            "api_called_definition": (
                "No external or paid model API call; local CPU inference "
                "occurred only for the bounded acquisition canary. Official "
                "Hugging Face metadata HTTP endpoints were accessed for "
                "acquisition evidence."
            ),
            "local_model_inference_executed": True,
            "model": {
                "repo_id": REPO_ID,
                "revision": REVISION,
                "expected_payload_bytes": model["expected_payload_bytes"],
                "expected_weight_bytes": model["expected_weight_bytes"],
                "snapshot_acquired": True,
                "snapshot_hash_verified": True,
                "snapshot_dir": model["snapshot_dir"],
                "staging_dir": model["staging_dir"],
                "files": rows,
            },
            "cpu_load_smoke": smoke,
            "network_blocker": {
                "resolved": True,
                "model_bytes_redownloaded_during_repair": 0,
                "resume_status": "NOT_NEEDED_EXISTING_STAGE_VERIFIED",
            },
            "credentials_persisted": False,
            "api_called": False,
            "gpu_used": False,
            "competence_claimed": False,
            "scientific_families_touched": False,
            "qwen_omni_downloaded": False,
            "redistribution_authorized": False,
        }
    )
    atomic_json(root / MANIFEST, manifest)
    return manifest


def _write_local_manifests(
    stage: Path, rows: list[dict[str, Any]]
) -> None:
    sums = stage / "SHA256SUMS"
    sums.write_text(
        "".join(f"{row['sha256']}  {row['path']}\n" for row in rows),
        encoding="utf-8",
    )
    os.chmod(sums, 0o600)
    atomic_json(
        stage / "LOCAL_MANIFEST.json",
        {
            "schema_version": "av-trace.local-model-snapshot/1.0",
            "repo_id": REPO_ID,
            "revision": REVISION,
            "created_at": utc_now(),
            "files": rows,
            "local_only": True,
            "redistribution_authorized": False,
        },
    )


def acquire(
    root: Path,
    *,
    proxy: str,
    endpoint: str,
    max_time: int,
) -> dict[str, Any]:
    plan = load_json(root / PLAN)
    validate_plan(plan)
    model = plan["model"]
    final = root / model["snapshot_dir"]
    stage = root / model["staging_dir"]
    records = root / model["metadata_dir"]
    for directory in (
        final.parent,
        stage.parent,
        records,
        (root / MANIFEST).parent,
    ):
        directory.mkdir(parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
    if final.exists():
        raise AcquisitionError("FINAL_SNAPSHOT_ALREADY_EXISTS")
    if stage.is_symlink() or (stage.exists() and not stage.is_dir()):
        raise AcquisitionError("STAGING_PATH_INVALID")
    available_disk = shutil.disk_usage(root).free
    available_ram = int(
        next(
            line.split()[1]
            for line in Path("/proc/meminfo").read_text().splitlines()
            if line.startswith("MemAvailable:")
        )
    ) * 1024
    if available_disk < plan["caps"]["minimum_available_disk_bytes"]:
        raise AcquisitionError("DISK_GATE_FAILED")
    if available_ram < plan["caps"]["minimum_available_ram_bytes"]:
        raise AcquisitionError("RAM_GATE_FAILED")
    api_path = records / "model_api.json"
    tree_path = records / "tree.json"
    readme_path = records / "README.md"
    api_headers = records / "model_api.headers"
    tree_headers = records / "tree.headers"
    readme_headers = records / "README.headers"
    _curl(
        f"https://huggingface.co/api/models/{REPO_ID}/revision/{REVISION}",
        api_path,
        proxy=proxy,
        headers=api_headers,
        resume=False,
        max_time=max_time,
    )
    _curl(
        f"https://huggingface.co/api/models/{REPO_ID}/tree/{REVISION}"
        "?recursive=true&expand=true",
        tree_path,
        proxy=proxy,
        headers=tree_headers,
        resume=False,
        max_time=max_time,
    )
    _curl(
        exact_url(model, "README.md", endpoint),
        readme_path,
        proxy=proxy,
        headers=readme_headers,
        resume=False,
        max_time=max_time,
    )
    license_review = validate_official_metadata(
        plan,
        load_json(api_path),
        load_json(tree_path),
        readme_path.read_bytes(),
    )
    if _header_values(readme_headers, {"x-repo-commit"}) != {REVISION}:
        raise AcquisitionError("README_RESPONSE_REVISION")
    stage.mkdir(mode=0o700, exist_ok=True)
    os.chmod(stage, 0o700)
    allowed_stage = {
        item["path"] for item in model["allowlist"]
    } | {"SHA256SUMS", "LOCAL_MANIFEST.json"}
    extras = {path.name for path in stage.iterdir()} - allowed_stage
    if extras:
        raise AcquisitionError(f"UNEXPECTED_STAGING_FILES:{sorted(extras)}")
    response_identities = []
    for item in model["allowlist"]:
        destination = stage / item["path"]
        headers = records / f"{item['path']}.headers"
        reused = _file_complete(destination, item)
        if not reused:
            if destination.exists() and (
                destination.is_symlink()
                or destination.stat().st_size >= item["expected_bytes"]
            ):
                destination.unlink()
            _curl(
                exact_url(model, item["path"], endpoint),
                destination,
                proxy=proxy,
                headers=headers,
                resume=True,
                max_time=max_time,
            )
        os.chmod(destination, 0o600)
        if not _file_complete(destination, item):
            raise AcquisitionError(f"DOWNLOADED_FILE_IDENTITY:{item['path']}")
        commits = _header_values(headers, {"x-repo-commit"})
        object_ids = _header_values(headers, {"etag", "x-linked-etag"})
        if commits != {REVISION}:
            raise AcquisitionError(f"DOWNLOAD_RESPONSE_REVISION:{item['path']}")
        if (
            item["git_oid"] not in object_ids
            and (item["lfs_sha256"] or "") not in object_ids
        ):
            raise AcquisitionError(f"DOWNLOAD_RESPONSE_OBJECT:{item['path']}")
        response_identities.append(
            {
                "path": item["path"],
                "x_repo_commit": REVISION,
                "object_identity_values": sorted(object_ids),
                "reused_complete_file": reused,
            }
        )
    rows = []
    for item in model["allowlist"]:
        path = stage / item["path"]
        rows.append(
            {
                "path": item["path"],
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "upstream_identity": (
                    item["lfs_sha256"] or item["git_oid"]
                ),
                "upstream_identity_kind": (
                    "lfs_sha256" if item["lfs_sha256"] else "git_blob_oid"
                ),
            }
        )
    _write_local_manifests(stage, rows)
    validate_snapshot(plan, stage)
    smoke_report = records / "cpu_load_smoke.json"
    smoke = run_cpu_canary(
        root,
        stage,
        smoke_report,
        plan["runtime_canary"]["timeout_seconds"],
    )
    manifest = finalize_verified_stage(root, plan, smoke)
    manifest["license_review"] = license_review
    manifest["response_identities"] = response_identities
    atomic_json(root / MANIFEST, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--validate-existing", action="store_true")
    parser.add_argument("--promote-verified-stage", action="store_true")
    parser.add_argument("--proxy", default="https://proxy.example.invalid:3128")
    parser.add_argument("--endpoint", default="https://hf-mirror.com")
    parser.add_argument("--max-time", type=int, default=7200)
    parser.add_argument("--cpu-canary-child", action="store_true")
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--smoke-report", type=Path)
    arguments = parser.parse_args()
    root = arguments.repo_root.resolve()
    plan = load_json(root / PLAN)
    validate_plan(plan)
    if arguments.cpu_canary_child:
        if not arguments.snapshot or not arguments.smoke_report:
            raise AcquisitionError("CPU_CHILD_ARGUMENTS_MISSING")
        cpu_canary_child(root, arguments.snapshot, arguments.smoke_report)
        return 0
    if sum(
        (
            arguments.execute,
            arguments.validate_existing,
            arguments.promote_verified_stage,
        )
    ) > 1:
        raise AcquisitionError("CHOOSE_ONE_OPERATION")
    if arguments.execute:
        result = acquire(
            root,
            proxy=arguments.proxy,
            endpoint=arguments.endpoint,
            max_time=arguments.max_time,
        )
        print(result["decision"])
        return 0
    if arguments.validate_existing:
        manifest = load_json(root / MANIFEST)
        if manifest.get("decision") != "GRANITE33_8B_ACQUISITION_READY":
            raise AcquisitionError("MANIFEST_NOT_READY")
        validate_snapshot(plan, root / plan["model"]["snapshot_dir"])
        print("GRANITE33_8B_SNAPSHOT_VALID")
        return 0
    if arguments.promote_verified_stage:
        smoke_report = (
            root / plan["model"]["metadata_dir"] / "cpu_load_smoke.json"
        )
        smoke = (
            load_json(smoke_report) if smoke_report.exists() else None
        )
        if (
            smoke is None
            or smoke.get("status") != "LOAD_SMOKE_COMPLETE"
            or smoke.get("repo_id") != REPO_ID
            or smoke.get("revision") != REVISION
        ):
            smoke = run_cpu_canary(
                root,
                root / plan["model"]["staging_dir"],
                smoke_report,
                plan["runtime_canary"]["timeout_seconds"],
            )
        result = finalize_verified_stage(
            root,
            plan,
            smoke,
        )
        print(result["decision"])
        return 0
    print(
        json.dumps(
            {
                "status": "PREFLIGHT_ONLY",
                "repo_id": REPO_ID,
                "revision": REVISION,
                "payload_bytes": plan["model"]["expected_payload_bytes"],
                "execute_required_for_network": True,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        AcquisitionError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ) as exc:
        print(f"GRANITE33_8B_ACQUISITION_NO_GO:{exc}", file=sys.stderr)
        raise SystemExit(2)
