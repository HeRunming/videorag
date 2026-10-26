#!/usr/bin/env python3
"""Task 179 exact Qwen3-8B acquisition and adapter-v2 CPU smoke.

The default operation is local preflight only. ``--execute`` is required for
network transfer. Exact model files are downloaded with curl resume support,
existing Hugging Face authentication, and no credential material in output.
The CPU child is offline, local-only, CPU BF16, and never reads a sealed suite
or a scientific source.
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
from collections.abc import Iterator, Mapping
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from av_trace_strong_baselines.errors import SchemaViolation
from av_trace_strong_baselines.schemas import parse_strict_json
from av_trace_strong_baselines_v2 import (
    ADAPTER_SCHEMA_VERSION,
    AttemptKind,
    FactorStatus,
    ProjectionStatus,
    RawFactorAttempt,
    action_choice_spec,
    build_native_action_plan,
    evidence_state_spec,
    finalizer_factor_specs,
    parse_controller_factors,
    parse_finalizer_factors,
)

PLAN = Path("data/acquisition_plan/qwen3_8b_acquisition_plan.json")
MANIFEST = Path(
    "data/restricted/strong_baselines/manifests/qwen3_8b_acquisition.json"
)
REPO_ID = "Qwen/Qwen3-8B"
REVISION = "b968826d9c46dd6066d109eabc6255188de91218"
READY = "QWEN3_8B_ACQUISITION_READY"
REPAIR = "QWEN3_8B_ACQUISITION_REPAIR"
NO_GO = "QWEN3_8B_ACQUISITION_NO_GO"
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
EXPECTED_TREE = {
    ".gitattributes",
    "LICENSE",
    "README.md",
    "config.json",
    "generation_config.json",
    "merges.txt",
    "model-00001-of-00005.safetensors",
    "model-00002-of-00005.safetensors",
    "model-00003-of-00005.safetensors",
    "model-00004-of-00005.safetensors",
    "model-00005-of-00005.safetensors",
    "model.safetensors.index.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.json",
}
HF_TOKEN_PATHS = (
    Path("/path/to/av-trace"),
    Path("/path/to/av-trace"),
)


class AcquisitionError(RuntimeError):
    """Fail-closed Task179 error."""


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


def selected_files(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [dict(item) for item in plan["model"]["allowlist"]]


def validate_plan(plan: dict[str, Any]) -> None:
    model = plan.get("model")
    if not isinstance(model, dict):
        raise AcquisitionError("MODEL_MISSING")
    if model.get("repo_id") != REPO_ID or model.get("revision") != REVISION:
        raise AcquisitionError("MODEL_IDENTITY_MISMATCH")
    if not HEX40.fullmatch(REVISION):
        raise AcquisitionError("REVISION_NOT_IMMUTABLE")
    tree = model.get("official_tree")
    files = model.get("allowlist")
    if not isinstance(tree, list) or not isinstance(files, list) or not files:
        raise AcquisitionError("FILE_PLAN_MISSING")
    tree_by_path = {item.get("path"): item for item in tree}
    if set(tree_by_path) != EXPECTED_TREE or len(tree_by_path) != len(tree):
        raise AcquisitionError("OFFICIAL_TREE_PLAN_MISMATCH")
    names = [item.get("path") for item in files]
    if len(names) != len(set(names)) or any(
        not isinstance(name, str) or Path(name).name != name for name in names
    ):
        raise AcquisitionError("ALLOWLIST_PATH_INVALID")
    expected_selected = {
        item["path"] for item in tree if item.get("selected_for_snapshot")
    }
    if set(names) != expected_selected:
        raise AcquisitionError("ALLOWLIST_SELECTION_MISMATCH")
    required_shards = {
        f"model-{index:05d}-of-00005.safetensors"
        for index in range(1, 6)
    }
    if set(model["weight_layout"]["required_shards"]) != required_shards:
        raise AcquisitionError("SHARD_SET_MISMATCH")
    if not required_shards <= set(names):
        raise AcquisitionError("SHARDS_NOT_ALLOWLISTED")
    if model["weight_layout"]["index"] not in names:
        raise AcquisitionError("INDEX_NOT_ALLOWLISTED")
    if {"merges.txt", "vocab.json"} & set(names):
        raise AcquisitionError("NONMINIMAL_TOKENIZER_FILES_SELECTED")
    total = 0
    weight_total = 0
    for item in tree:
        size = item.get("expected_bytes")
        oid = item.get("git_oid")
        lfs = item.get("lfs_sha256")
        if (
            not isinstance(size, int)
            or size <= 0
            or not isinstance(oid, str)
            or not HEX40.fullmatch(oid)
            or not isinstance(item.get("selected_for_snapshot"), bool)
        ):
            raise AcquisitionError(f"FILE_METADATA_INVALID:{item.get('path')}")
        if lfs is not None:
            if not isinstance(lfs, str) or not HEX64.fullmatch(lfs):
                raise AcquisitionError(f"LFS_HASH_INVALID:{item['path']}")
            if lfs_pointer_git_oid(lfs, size) != oid:
                raise AcquisitionError(f"LFS_POINTER_OID_MISMATCH:{item['path']}")
        if item["selected_for_snapshot"]:
            total += size
            if item["path"].endswith(".safetensors"):
                weight_total += size
    if total != model.get("expected_payload_bytes"):
        raise AcquisitionError("PAYLOAD_TOTAL_MISMATCH")
    if weight_total != model.get("expected_weight_bytes"):
        raise AcquisitionError("WEIGHT_TOTAL_MISMATCH")
    caps = plan.get("caps") or {}
    if total > caps.get("selected_payload_bytes", 0):
        raise AcquisitionError("PAYLOAD_CAP_EXCEEDED")
    runtime = plan.get("runtime_canary") or {}
    if (
        runtime.get("device") != "cpu"
        or runtime.get("dtype") != "bfloat16"
        or runtime.get("threads") != 8
        or runtime.get("local_files_only") is not True
        or runtime.get("trust_remote_code") is not False
        or runtime.get("adapter_schema_version") != ADAPTER_SCHEMA_VERSION
        or runtime.get("schema_only_retries_per_factor") != 0
        or runtime.get("factor_count") != 7
    ):
        raise AcquisitionError("RUNTIME_POLICY_MISMATCH")
    if runtime.get("case_ids") != [
        "qwen3-acq-controller-001",
        "qwen3-acq-finalizer-001",
    ]:
        raise AcquisitionError("SMOKE_CASE_SET_MISMATCH")


def validate_official_metadata(
    plan: dict[str, Any],
    api: dict[str, Any],
    tree: list[dict[str, Any]],
    readme: bytes,
    license_text: bytes,
) -> dict[str, Any]:
    if api.get("id") != REPO_ID or api.get("sha") != REVISION:
        raise AcquisitionError("OFFICIAL_API_IDENTITY_MISMATCH")
    if api.get("private") is not False or bool(api.get("gated")):
        raise AcquisitionError("MODEL_NOT_PUBLIC_UNGATED")
    by_path = {
        item.get("path"): item for item in tree if item.get("type") == "file"
    }
    if set(by_path) != EXPECTED_TREE:
        raise AcquisitionError("OFFICIAL_TREE_FILE_SET_CHANGED")
    for expected in plan["model"]["official_tree"]:
        actual = by_path.get(expected["path"])
        if (
            not actual
            or actual.get("size") != expected["expected_bytes"]
            or actual.get("oid") != expected["git_oid"]
            or (actual.get("lfs") or {}).get("oid")
            != expected["lfs_sha256"]
        ):
            raise AcquisitionError(f"OFFICIAL_TREE_MISMATCH:{expected['path']}")
    risky = sorted(
        name
        for name in by_path
        if Path(name).suffix.lower() in FORBIDDEN_SUFFIXES
    )
    if risky:
        raise AcquisitionError(f"RISKY_TREE_FILE:{risky}")
    readme_expected = by_path["README.md"]
    license_expected = by_path["LICENSE"]
    if (
        len(readme) != readme_expected["size"]
        or git_blob_oid_bytes(readme) != readme_expected["oid"]
    ):
        raise AcquisitionError("README_IDENTITY_MISMATCH")
    if (
        len(license_text) != license_expected["size"]
        or git_blob_oid_bytes(license_text) != license_expected["oid"]
    ):
        raise AcquisitionError("LICENSE_IDENTITY_MISMATCH")
    declared = {
        str((api.get("cardData") or {}).get("license", "")).lower(),
        *{
            str(tag).split(":", 1)[1].lower()
            for tag in api.get("tags", [])
            if str(tag).startswith("license:")
        },
    }
    if declared != {"apache-2.0"}:
        raise AcquisitionError("LICENSE_DECLARATION_MISMATCH")
    if "license: apache-2.0" not in readme.decode("utf-8", "strict").lower():
        raise AcquisitionError("MODEL_CARD_LICENSE_MISMATCH")
    license_string = license_text.decode("utf-8", "strict")
    if "Apache License" not in license_string or "Version 2.0" not in license_string:
        raise AcquisitionError("LICENSE_TEXT_MISMATCH")
    return {
        "acceptable_for_restricted_internal_preflight": True,
        "declared_license": "apache-2.0",
        "exact_repository_license_file_present": True,
        "exact_repository_license_git_oid": license_expected["oid"],
        "exact_repository_license_sha256": hashlib.sha256(
            license_text
        ).hexdigest(),
        "tree_file_count": len(by_path),
        "risky_code_or_pickle_files": risky,
        "redistribution_authorized": False,
    }


def exact_url(model: Mapping[str, Any], name: str, endpoint: str) -> str:
    repo = "/".join(quote(part, safe="") for part in model["repo_id"].split("/"))
    return (
        f"{endpoint.rstrip('/')}/{repo}/resolve/{model['revision']}/"
        f"{quote(name, safe='')}"
    )


def existing_hf_token() -> str:
    for path in HF_TOKEN_PATHS:
        if path.is_file():
            token = path.read_text(encoding="utf-8").strip()
            if token:
                return token
    raise AcquisitionError("EXISTING_HF_AUTH_NOT_FOUND")


def write_curl_auth_config(path: Path) -> None:
    token = existing_hf_token()
    escaped = token.replace("\\", "\\\\").replace('"', '\\"')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'header = "Authorization: Bearer {escaped}"\n',
        encoding="utf-8",
    )
    os.chmod(path, 0o600)


def _curl(
    url: str,
    output: Path,
    *,
    proxy: str,
    headers: Path,
    auth_config: Path,
    resume: bool,
    max_time: int,
) -> None:
    command = [
        "curl",
        "--config",
        str(auth_config),
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
    os.chmod(output, 0o600)
    os.chmod(headers, 0o600)


def _header_values(path: Path, names: set[str]) -> set[str]:
    values: set[str] = set()
    for line in path.read_text("iso-8859-1").splitlines():
        key, separator, value = line.partition(":")
        if separator and key.strip().lower() in names:
            values.add(value.strip().strip('"'))
    return values


def _file_complete(path: Path, expected: Mapping[str, Any]) -> bool:
    if not path.is_file() or path.is_symlink():
        return False
    if path.stat().st_size != expected["expected_bytes"]:
        return False
    if expected["lfs_sha256"]:
        return sha256_file(path) == expected["lfs_sha256"]
    return git_blob_oid(path) == expected["git_oid"]


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


def validate_snapshot(plan: dict[str, Any], snapshot: Path) -> list[dict[str, Any]]:
    model = plan["model"]
    if (
        not snapshot.is_dir()
        or snapshot.is_symlink()
        or stat.S_IMODE(snapshot.stat().st_mode) != 0o700
    ):
        raise AcquisitionError("SNAPSHOT_DIRECTORY_MODE")
    allowed = {item["path"]: item for item in selected_files(plan)}
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


def public_smoke_cases() -> list[dict[str, Any]]:
    """Return the two inline public fictional cases; no suite file is read."""

    return [
        {
            "case_id": "qwen3-acq-controller-001",
            "case_type": "controller",
            "public_input": {
                "question": (
                    "What fictional badge shape appears? No evidence has "
                    "been observed yet."
                ),
                "public_claim_slots": [
                    {
                        "claim_handle": "public.badge_shape",
                        "description": "Shape of the fictional badge.",
                    }
                ],
                "observed_evidence": [],
                "action_menu": [
                    {
                        "tool": "search_visual",
                        "arguments": {
                            "query": "fictional badge shape",
                            "top_k": 5,
                            "time_range": {"start_s": 0.0, "end_s": 1.0},
                            "exclude_result_ids": [],
                        },
                    },
                    {"tool": "finalize", "arguments": {}},
                ],
            },
        },
        {
            "case_id": "qwen3-acq-finalizer-001",
            "case_type": "finalizer",
            "public_input": {
                "question": "What shape is the fictional badge?",
                "public_claim_slots": [
                    {
                        "claim_handle": "public.badge_shape",
                        "description": "Shape of the fictional badge.",
                    }
                ],
                "observed_evidence": [
                    {
                        "observation_id": "obs.public.badge.0",
                        "interval": {"start_s": 0.0, "end_s": 1.0},
                        "modalities": ["vision"],
                        "payload": {
                            "text": (
                                "A fictional blue badge is visibly octagonal."
                            )
                        },
                    }
                ],
            },
        },
    ]


def _claim_handles(case: Mapping[str, Any]) -> list[str]:
    return [
        str(item["claim_handle"])
        for item in case["public_input"]["public_claim_slots"]
    ]


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _jsonable(child) for key, child in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _jsonable(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(child) for child in value]
    if hasattr(value, "value"):
        return value.value
    return value


def _factor_specs(case: Mapping[str, Any]) -> list[tuple[str, Any, str]]:
    handles = _claim_handles(case)
    if case["case_type"] == "controller":
        action_plan = build_native_action_plan(
            case["public_input"]["action_menu"]
        )
        return [
            (
                "action_choice",
                action_choice_spec(action_plan),
                "native_action_choice",
            ),
            (
                "evidence_state",
                evidence_state_spec(handles),
                "evidence_state_heads",
            ),
        ]
    observations = case["public_input"]["observed_evidence"]
    specs = finalizer_factor_specs(
        claim_handles=handles,
        observation_ids=[
            str(item["observation_id"]) for item in observations
        ],
    )
    return [(name, spec, spec.role) for name, spec in specs.items()]


def _factor_messages(
    *,
    case: Mapping[str, Any],
    factor_name: str,
    role: str,
    schema: Mapping[str, Any],
) -> list[dict[str, str]]:
    system = (
        "You are executing a tiny public fictional load smoke for a "
        "model-neutral factorized controller/finalizer adapter. This is not "
        "an evaluation. Use only the supplied public case. Do not add facts."
    )
    if factor_name == "action_choice":
        instruction = (
            "Choose exactly one supplied no-argument function. A function "
            "call is required. Do not emit prose or regenerate arguments."
        )
    else:
        instruction = (
            "Return exactly one compact JSON object and no prose or markdown. "
            "Match the factor schema exactly. Author only this factor."
        )
    payload = {
        "factor_id": factor_name,
        "factor_role": role,
        "output_schema": schema,
        "public_case": {
            "case_type": case["case_type"],
            "public_input": case["public_input"],
        },
    }
    return [
        {"role": "system", "content": system + " " + instruction},
        {
            "role": "user",
            "content": json.dumps(
                payload,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            ),
        },
    ]


def _strip_qwen_transport(raw: str) -> str:
    value = raw.strip()
    for token in ("<|im_end|>", "<|endoftext|>"):
        while value.endswith(token):
            value = value[: -len(token)].rstrip()
    return value


def normalize_action_transport(raw: str) -> tuple[bytes, str]:
    """Normalize only Qwen's native tool-call wrapper, never its choice."""

    content = _strip_qwen_transport(raw)
    if content.startswith("<tool_call>") and content.endswith("</tool_call>"):
        content = content[len("<tool_call>") : -len("</tool_call>")].strip()
    try:
        value = parse_strict_json(content, maximum_bytes=16_384)
    except SchemaViolation:
        return content.encode("utf-8"), "unparsed_passthrough"
    canonical: Mapping[str, Any] | None = None
    if isinstance(value, Mapping) and set(value) == {
        "function_name",
        "arguments",
    }:
        canonical = value
    elif isinstance(value, Mapping) and set(value) == {"name", "arguments"}:
        canonical = {
            "function_name": value["name"],
            "arguments": value["arguments"],
        }
    if canonical is None:
        return content.encode("utf-8"), "parsed_passthrough"
    return (
        json.dumps(
            canonical,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8"),
        "qwen_native_tool_call",
    )


def _factor_outcome(
    case: Mapping[str, Any],
    factor_name: str,
    adapter_input: bytes,
) -> Any:
    attempt = (
        RawFactorAttempt(
            attempt_index=1,
            kind=AttemptKind.INITIAL,
            raw_output=adapter_input,
        ),
    )
    handles = _claim_handles(case)
    if case["case_type"] == "controller":
        plan = build_native_action_plan(case["public_input"]["action_menu"])
        if factor_name == "action_choice":
            dummy_state = RawFactorAttempt.from_text(
                json.dumps(
                    {
                        "p_sufficient": 0.0,
                        "covered_claim_handles": [],
                        "missing_modalities": ["vision"],
                        "missing_hops": ["entity_identity"],
                        "missingness_cause": (
                            "evidence_accessible_but_not_found"
                        ),
                        "recovery_intent": "search_vision",
                    },
                    separators=(",", ":"),
                )
            )
            result = parse_controller_factors(
                action_menu=plan.action_menu,
                claim_handles=handles,
                observed_evidence=case["public_input"]["observed_evidence"],
                action_attempts=attempt,
                evidence_state_attempts=(dummy_state,),
            )
            return result.action_factor
        dummy_action = RawFactorAttempt.from_text(
            json.dumps(
                {
                    "function_name": plan.function_name_for_index(0),
                    "arguments": {},
                },
                separators=(",", ":"),
            )
        )
        result = parse_controller_factors(
            action_menu=plan.action_menu,
            claim_handles=handles,
            observed_evidence=case["public_input"]["observed_evidence"],
            action_attempts=(dummy_action,),
            evidence_state_attempts=attempt,
        )
        return result.evidence_state_factor
    observations = case["public_input"]["observed_evidence"]
    observation_ids = [
        str(item["observation_id"]) for item in observations
    ]
    specs = finalizer_factor_specs(
        claim_handles=handles,
        observation_ids=observation_ids,
    )
    valid = {
        "disposition": {
            "p_sufficient": 1.0,
            "verdict": "sufficient",
            "answer_mode": "answer",
            "termination_reason": "sufficient_evidence",
        },
        "answer_text": {
            "text": "The fictional badge is octagonal."
        },
        "claim_drafts": {
            "claims": [
                {
                    "claim_id": "public.badge.1",
                    "registered_claim_id": "public.badge_shape",
                    "text": "The fictional badge is octagonal.",
                    "confidence": 1.0,
                }
            ]
        },
        "citation_selections": {
            "selections": [
                {
                    "registered_claim_id": "public.badge_shape",
                    "observation_ids": ["obs.public.badge.0"],
                }
            ]
        },
        "diagnosis": {
            "modality_probabilities": {
                "vision": 1.0,
                "speech": 0.0,
                "ambient": 0.0,
            },
            "hop_types": [],
            "cause_probabilities": {
                "source_evidence_absent": 0.0,
                "evidence_in_source_but_inaccessible": 0.0,
                "evidence_accessible_but_not_found": 0.0,
                "not_missing": 1.0,
                "uncertain": 0.0,
            },
            "recovery_route_declared": False,
            "description": "Complete public fictional visual evidence.",
        },
    }
    attempts = {
        name: (
            attempt
            if name == factor_name
            else (
                RawFactorAttempt.from_text(
                    json.dumps(value, separators=(",", ":"))
                ),
            )
        )
        for name, value in valid.items()
    }
    result = parse_finalizer_factors(
        claim_handles=handles,
        observations=observations,
        attempts_by_factor=attempts,
    )
    if factor_name not in specs:
        raise AcquisitionError(f"UNKNOWN_FINALIZER_FACTOR:{factor_name}")
    return result.factors[factor_name]


def assemble_case(
    case: Mapping[str, Any],
    factor_records: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    def attempt(name: str) -> tuple[RawFactorAttempt, ...]:
        value = factor_records[name].get("adapter_input")
        if not isinstance(value, str):
            return ()
        return (RawFactorAttempt.from_text(value),)

    if case["case_type"] == "controller":
        result = parse_controller_factors(
            action_menu=case["public_input"]["action_menu"],
            claim_handles=_claim_handles(case),
            observed_evidence=case["public_input"]["observed_evidence"],
            action_attempts=attempt("action_choice"),
            evidence_state_attempts=attempt("evidence_state"),
        )
        return {
            "case_id": case["case_id"],
            "case_type": case["case_type"],
            "factor_outcomes": {
                "action_choice": {
                    "status": str(result.action_factor.status),
                    "error_code": result.action_factor.error_code,
                    "value": _jsonable(result.action_factor.value),
                },
                "evidence_state": {
                    "status": str(result.evidence_state_factor.status),
                    "error_code": result.evidence_state_factor.error_code,
                    "value": _jsonable(result.evidence_state_factor.value),
                },
            },
            "projection_status": str(result.state_projection.status),
            "projection_error_code": result.state_projection.error_code,
            "canonical_output": _jsonable(result.canonical_decision),
        }
    result = parse_finalizer_factors(
        claim_handles=_claim_handles(case),
        observations=case["public_input"]["observed_evidence"],
        attempts_by_factor={
            name: attempt(name)
            for name in (
                "disposition",
                "answer_text",
                "claim_drafts",
                "citation_selections",
                "diagnosis",
            )
        },
    )
    return {
        "case_id": case["case_id"],
        "case_type": case["case_type"],
        "factor_outcomes": {
            name: {
                "status": str(outcome.status),
                "error_code": outcome.error_code,
                "value": _jsonable(outcome.value),
            }
            for name, outcome in result.factors.items()
        },
        "projection_status": str(result.projection_status),
        "projection_error_code": result.projection_error_code,
        "canonical_output": _jsonable(result.canonical_envelope),
    }


def cpu_canary_child(root: Path, snapshot: Path, report: Path) -> None:
    plan = load_json(root / PLAN)
    validate_plan(plan)
    limits = plan["runtime_canary"]
    resource.setrlimit(
        resource.RLIMIT_AS,
        (
            limits["address_space_limit_bytes"],
            limits["address_space_limit_bytes"],
        ),
    )
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    _offline_environment()
    import numpy as np

    if "long" not in np.__dict__:
        np.long = np.int64  # type: ignore[attr-defined]
    if "ulong" not in np.__dict__:
        np.ulong = np.uint64  # type: ignore[attr-defined]
    import torch
    import transformers
    from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer

    torch.manual_seed(179)
    torch.set_num_threads(limits["threads"])
    started = time.perf_counter()
    with deny_network() as network:
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
        report_value: dict[str, Any] = {
            "schema_version": "av-trace.qwen3-acquisition-smoke/1.0",
            "status": "LOAD_SMOKE_IN_PROGRESS",
            "scope": limits["scope"],
            "competence_claimed": False,
            "repo_id": REPO_ID,
            "revision": REVISION,
            "adapter_schema_version": ADAPTER_SCHEMA_VERSION,
            "sealed_suite_read": False,
            "scientific_source_read": False,
            "local_files_only": True,
            "trust_remote_code": False,
            "network_attempts": network["count"],
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
            "raw_outputs_preserved": True,
            "semantic_repair": False,
            "schema_retries_used": 0,
            "factors": [],
            "cases": [],
        }
        atomic_json(report, report_value)
        factor_records_by_case: dict[str, dict[str, dict[str, Any]]] = {}
        for case in public_smoke_cases():
            case_records: dict[str, dict[str, Any]] = {}
            factor_records_by_case[str(case["case_id"])] = case_records
            for factor_name, spec, role in _factor_specs(case):
                messages = _factor_messages(
                    case=case,
                    factor_name=factor_name,
                    role=role,
                    schema=spec.output_schema,
                )
                tools = None
                if factor_name == "action_choice":
                    tools = list(
                        build_native_action_plan(
                            case["public_input"]["action_menu"]
                        ).tools
                    )
                rendered = tokenizer.apply_chat_template(
                    messages,
                    tools=tools,
                    tokenize=False,
                    add_generation_prompt=True,
                    enable_thinking=False,
                )
                inputs = tokenizer(rendered, return_tensors="pt")
                generation_started = time.perf_counter()
                with torch.inference_mode():
                    generated = model.generate(
                        **inputs,
                        do_sample=False,
                        max_new_tokens=limits["max_new_tokens_per_factor"],
                        pad_token_id=tokenizer.eos_token_id,
                        eos_token_id=tokenizer.eos_token_id,
                    )
                generation_seconds = time.perf_counter() - generation_started
                output_ids = generated[0, inputs["input_ids"].shape[1] :]
                raw_with_specials = tokenizer.decode(
                    output_ids,
                    skip_special_tokens=False,
                )
                raw = tokenizer.decode(
                    output_ids,
                    skip_special_tokens=True,
                ).strip()
                adapter_bytes = raw.encode("utf-8")
                normalization = "identity"
                if factor_name == "action_choice":
                    adapter_bytes, normalization = normalize_action_transport(
                        raw
                    )
                outcome = _factor_outcome(
                    case,
                    factor_name,
                    adapter_bytes,
                )
                record = {
                    "case_id": case["case_id"],
                    "case_type": case["case_type"],
                    "factor_name": factor_name,
                    "factor_id": spec.factor_id,
                    "attempt_index": 1,
                    "attempt_kind": "initial",
                    "prompt_tokens": int(inputs["input_ids"].numel()),
                    "completion_tokens": int(output_ids.numel()),
                    "generation_seconds": generation_seconds,
                    "raw_output": raw,
                    "raw_output_with_special_tokens": raw_with_specials,
                    "raw_output_sha256": hashlib.sha256(
                        raw.encode("utf-8")
                    ).hexdigest(),
                    "adapter_input": adapter_bytes.decode("utf-8"),
                    "adapter_input_sha256": hashlib.sha256(
                        adapter_bytes
                    ).hexdigest(),
                    "transport_normalization": normalization,
                    "factor_status": str(outcome.status),
                    "factor_error_code": outcome.error_code,
                    "factor_value": _jsonable(outcome.value),
                }
                case_records[factor_name] = record
                report_value["factors"].append(record)
                report_value["active_factor"] = {
                    "case_id": case["case_id"],
                    "factor_name": factor_name,
                }
                atomic_json(report, report_value)
            report_value["cases"].append(
                assemble_case(case, case_records)
            )
            report_value.pop("active_factor", None)
            atomic_json(report, report_value)
    report_value["network_attempts"] = network["count"]
    report_value["status"] = "LOAD_SMOKE_COMPLETE"
    report_value["elapsed_seconds"] = time.perf_counter() - started
    report_value["peak_rss_kib"] = resource.getrusage(
        resource.RUSAGE_SELF
    ).ru_maxrss
    atomic_json(report, report_value)


def validate_smoke(smoke: Mapping[str, Any]) -> None:
    factors = smoke.get("factors")
    cases = smoke.get("cases")
    if (
        smoke.get("status") != "LOAD_SMOKE_COMPLETE"
        or smoke.get("competence_claimed") is not False
        or smoke.get("sealed_suite_read") is not False
        or smoke.get("scientific_source_read") is not False
        or smoke.get("local_files_only") is not True
        or smoke.get("trust_remote_code") is not False
        or smoke.get("network_attempts") != 0
        or smoke.get("device") != "cpu"
        or smoke.get("dtype") != "torch.bfloat16"
        or smoke.get("config_model_type") != "qwen3"
        or smoke.get("runtime", {}).get("threads") != 8
        or smoke.get("raw_outputs_preserved") is not True
        or smoke.get("schema_retries_used") != 0
        or smoke.get("semantic_repair") is not False
        or not isinstance(factors, list)
        or len(factors) != 7
        or not isinstance(cases, list)
        or {case.get("case_id") for case in cases}
        != {
            "qwen3-acq-controller-001",
            "qwen3-acq-finalizer-001",
        }
    ):
        raise AcquisitionError("CPU_CANARY_RESULT_INVALID")
    for factor in factors:
        raw_output = factor.get("raw_output")
        raw_with_specials = factor.get("raw_output_with_special_tokens")
        adapter_input = factor.get("adapter_input")
        if (
            not isinstance(raw_output, str)
            or not isinstance(raw_with_specials, str)
            or not isinstance(adapter_input, str)
            or factor.get("attempt_index") != 1
            or factor.get("attempt_kind") != AttemptKind.INITIAL.value
            or factor.get("raw_output_sha256")
            != hashlib.sha256(raw_output.encode("utf-8")).hexdigest()
            or factor.get("adapter_input_sha256")
            != hashlib.sha256(adapter_input.encode("utf-8")).hexdigest()
        ):
            raise AcquisitionError("RAW_FACTOR_EVIDENCE_INVALID")
    for case in cases:
        outcomes = case.get("factor_outcomes")
        if not isinstance(outcomes, Mapping) or not outcomes:
            raise AcquisitionError("CASE_FACTOR_OUTCOMES_MISSING")
        valid_count = sum(
            outcome.get("status") == str(FactorStatus.VALID)
            for outcome in outcomes.values()
            if isinstance(outcome, Mapping)
        )
        if valid_count == 0:
            raise AcquisitionError(
                f"NO_VALID_ADAPTER_V2_FACTOR:{case.get('case_id')}"
            )
        if case.get("projection_status") not in {
            str(ProjectionStatus.ACCEPTED),
            str(ProjectionStatus.REJECTED),
            str(ProjectionStatus.NOT_RUN),
        }:
            raise AcquisitionError("CASE_PROJECTION_STATUS_INVALID")


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
    validate_smoke(value)
    return value


def initial_manifest(
    root: Path,
    plan: dict[str, Any],
    *,
    available_disk: int,
    available_ram: int,
) -> dict[str, Any]:
    return {
        "schema_version": "av-trace.qwen3-8b-acquisition/1.0",
        "task_id": 179,
        "created_at": utc_now(),
        "decision": REPAIR,
        "status": "ACQUISITION_IN_PROGRESS",
        "repo_id": REPO_ID,
        "revision": REVISION,
        "exact_files": plan["model"]["official_tree"],
        "model": {
            "repo_id": REPO_ID,
            "revision": REVISION,
            "snapshot_dir": plan["model"]["snapshot_dir"],
            "staging_dir": plan["model"]["staging_dir"],
            "expected_payload_bytes": plan["model"]["expected_payload_bytes"],
            "expected_weight_bytes": plan["model"]["expected_weight_bytes"],
            "snapshot_acquired": False,
            "snapshot_hash_verified": False,
            "files": [],
        },
        "disk_ram_gates": {
            "disk_available_bytes_approx": available_disk,
            "minimum_available_disk_bytes": plan["caps"][
                "minimum_available_disk_bytes"
            ],
            "disk_gate_passed": (
                available_disk
                >= plan["caps"]["minimum_available_disk_bytes"]
            ),
            "ram_available_bytes_approx": available_ram,
            "minimum_available_ram_bytes": plan["caps"][
                "minimum_available_ram_bytes"
            ],
            "ram_gate_passed": (
                available_ram >= plan["caps"]["minimum_available_ram_bytes"]
            ),
        },
        "archived_evidence": {},
        "license_review": None,
        "response_identities": [],
        "cpu_load_smoke": {
            "status": "NOT_RUN",
            "scope": plan["runtime_canary"]["scope"],
        },
        "local_model_inference_executed": False,
        "api_called": False,
        "api_called_definition": (
            "No external or paid model API is called. Official Hugging Face "
            "HTTP endpoints are used only for acquisition evidence and bytes."
        ),
        "credentials_persisted": False,
        "existing_hf_auth_used": True,
        "gpu_used": False,
        "competence_claimed": False,
        "sealed_competence_suite_run": False,
        "scientific_sources_touched": False,
        "qwen_omni_downloaded": False,
        "unrelated_ray_or_h20_jobs_touched": False,
        "redistribution_authorized": False,
        "repo_root": str(root),
    }


def _archive_metadata_evidence(
    records: Path,
    license_review: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "exact_model_api": {
            "archived": True,
            "local_path": str(records.relative_to(ROOT) / "model_api.json"),
            "sha256": sha256_file(records / "model_api.json"),
            "source_checked": (
                "official Hugging Face exact-revision model API through "
                "the required proxy with existing auth"
            ),
        },
        "recursive_tree": {
            "archived": True,
            "archive_kind": (
                "raw exact-revision recursive-tree endpoint response"
            ),
            "local_path": str(records.relative_to(ROOT) / "tree.json"),
            "sha256": sha256_file(records / "tree.json"),
        },
        "exact_model_card": {
            "archived": True,
            "local_path": str(records.relative_to(ROOT) / "README.md"),
            "bytes": (records / "README.md").stat().st_size,
            "git_blob_oid": git_blob_oid(records / "README.md"),
            "sha256": sha256_file(records / "README.md"),
            "x_repo_commit": REVISION,
        },
        "exact_license": {
            "archived": True,
            "local_path": str(records.relative_to(ROOT) / "LICENSE"),
            "bytes": (records / "LICENSE").stat().st_size,
            "git_blob_oid": git_blob_oid(records / "LICENSE"),
            "sha256": sha256_file(records / "LICENSE"),
            "x_repo_commit": REVISION,
            "declared_license": license_review["declared_license"],
        },
    }


def finalize_verified_stage(
    root: Path,
    plan: dict[str, Any],
    manifest: dict[str, Any],
    smoke: dict[str, Any],
) -> dict[str, Any]:
    model = plan["model"]
    stage = root / model["staging_dir"]
    final = root / model["snapshot_dir"]
    records = root / model["metadata_dir"]
    validate_smoke(smoke)
    rows = validate_snapshot(plan, stage)
    if final.exists():
        final_rows = validate_snapshot(plan, final)
        if final_rows != rows:
            raise AcquisitionError("FINAL_SNAPSHOT_CONFLICT")
        shutil.rmtree(stage)
    else:
        os.replace(stage, final)
    rows = validate_snapshot(plan, final)
    for path in records.iterdir():
        if path.is_file():
            os.chmod(path, 0o600)
    manifest.update(
        {
            "updated_at": utc_now(),
            "decision": READY,
            "status": "ACQUISITION_COMPLETE_CPU_ADAPTER_V2_SMOKE_COMPLETE",
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
            "local_model_inference_executed": True,
            "credentials_persisted": False,
            "api_called": False,
            "gpu_used": False,
            "competence_claimed": False,
            "sealed_competence_suite_run": False,
            "scientific_sources_touched": False,
            "qwen_omni_downloaded": False,
            "unrelated_ray_or_h20_jobs_touched": False,
            "redistribution_authorized": False,
        }
    )
    atomic_json(root / MANIFEST, manifest)
    return manifest


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
    manifest = initial_manifest(
        root,
        plan,
        available_disk=available_disk,
        available_ram=available_ram,
    )
    atomic_json(root / MANIFEST, manifest)
    if available_disk < plan["caps"]["minimum_available_disk_bytes"]:
        raise AcquisitionError("DISK_GATE_FAILED")
    if available_ram < plan["caps"]["minimum_available_ram_bytes"]:
        raise AcquisitionError("RAM_GATE_FAILED")
    auth_config = Path("/tmp/task179_qwen3_curl_auth.conf")
    write_curl_auth_config(auth_config)
    try:
        api_path = records / "model_api.json"
        tree_path = records / "tree.json"
        readme_path = records / "README.md"
        license_path = records / "LICENSE"
        api_headers = records / "model_api.headers"
        tree_headers = records / "tree.headers"
        readme_headers = records / "README.headers"
        license_headers = records / "LICENSE.headers"
        _curl(
            f"https://huggingface.co/api/models/{REPO_ID}/revision/{REVISION}",
            api_path,
            proxy=proxy,
            headers=api_headers,
            auth_config=auth_config,
            resume=False,
            max_time=max_time,
        )
        _curl(
            f"https://huggingface.co/api/models/{REPO_ID}/tree/{REVISION}"
            "?recursive=true&expand=true",
            tree_path,
            proxy=proxy,
            headers=tree_headers,
            auth_config=auth_config,
            resume=False,
            max_time=max_time,
        )
        for name, output, headers in (
            ("README.md", readme_path, readme_headers),
            ("LICENSE", license_path, license_headers),
        ):
            _curl(
                exact_url(model, name, endpoint),
                output,
                proxy=proxy,
                headers=headers,
                auth_config=auth_config,
                resume=False,
                max_time=max_time,
            )
            if _header_values(headers, {"x-repo-commit"}) != {REVISION}:
                raise AcquisitionError(f"{name}_RESPONSE_REVISION")
        license_review = validate_official_metadata(
            plan,
            load_json(api_path),
            load_json(tree_path),
            readme_path.read_bytes(),
            license_path.read_bytes(),
        )
        manifest["license_review"] = license_review
        manifest["archived_evidence"] = _archive_metadata_evidence(
            records,
            license_review,
        )
        atomic_json(root / MANIFEST, manifest)
        stage.mkdir(mode=0o700, exist_ok=True)
        os.chmod(stage, 0o700)
        allowed_stage = {
            item["path"] for item in selected_files(plan)
        } | {"SHA256SUMS", "LOCAL_MANIFEST.json"}
        extras = {path.name for path in stage.iterdir()} - allowed_stage
        if extras:
            raise AcquisitionError(f"UNEXPECTED_STAGING_FILES:{sorted(extras)}")
        response_identities = []
        for item in selected_files(plan):
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
                    auth_config=auth_config,
                    resume=True,
                    max_time=max_time,
                )
            os.chmod(destination, 0o600)
            if not _file_complete(destination, item):
                raise AcquisitionError(
                    f"DOWNLOADED_FILE_IDENTITY:{item['path']}"
                )
            commits = _header_values(headers, {"x-repo-commit"})
            object_ids = _header_values(
                headers,
                {"etag", "x-linked-etag"},
            )
            if commits != {REVISION}:
                raise AcquisitionError(
                    f"DOWNLOAD_RESPONSE_REVISION:{item['path']}"
                )
            if (
                item["git_oid"] not in object_ids
                and (item["lfs_sha256"] or "") not in object_ids
            ):
                raise AcquisitionError(
                    f"DOWNLOAD_RESPONSE_OBJECT:{item['path']}"
                )
            response_identities.append(
                {
                    "path": item["path"],
                    "x_repo_commit": REVISION,
                    "object_identity_values": sorted(object_ids),
                    "reused_complete_file": reused,
                }
            )
            manifest["response_identities"] = response_identities
            manifest["download_progress"] = {
                "completed_files": len(response_identities),
                "selected_files": len(selected_files(plan)),
                "completed_bytes": sum(
                    expected["expected_bytes"]
                    for expected in selected_files(plan)
                    if expected["path"]
                    in {row["path"] for row in response_identities}
                ),
                "selected_bytes": model["expected_payload_bytes"],
            }
            atomic_json(root / MANIFEST, manifest)
        rows = []
        for item in selected_files(plan):
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
                        "lfs_sha256"
                        if item["lfs_sha256"]
                        else "git_blob_oid"
                    ),
                }
            )
        _write_local_manifests(stage, rows)
        validate_snapshot(plan, stage)
        manifest["model"]["files"] = rows
        manifest["model"]["snapshot_hash_verified"] = True
        manifest["status"] = "SNAPSHOT_VERIFIED_CPU_SMOKE_PENDING"
        atomic_json(root / MANIFEST, manifest)
        smoke_report = records / "cpu_load_smoke.json"
        smoke = run_cpu_canary(
            root,
            stage,
            smoke_report,
            plan["runtime_canary"]["timeout_seconds"],
        )
        return finalize_verified_stage(
            root,
            plan,
            manifest,
            smoke,
        )
    except BaseException:
        if (root / MANIFEST).is_file():
            current = load_json(root / MANIFEST)
            current.update(
                {
                    "updated_at": utc_now(),
                    "decision": REPAIR,
                    "status": "INTERRUPTED_OR_REPAIR_REQUIRED",
                }
            )
            atomic_json(root / MANIFEST, current)
        raise
    finally:
        auth_config.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--validate-existing", action="store_true")
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
    if arguments.execute and arguments.validate_existing:
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
        if manifest.get("decision") != READY:
            raise AcquisitionError("MANIFEST_NOT_READY")
        validate_snapshot(plan, root / plan["model"]["snapshot_dir"])
        validate_smoke(manifest["cpu_load_smoke"])
        print("QWEN3_8B_SNAPSHOT_VALID")
        return 0
    print(
        json.dumps(
            {
                "status": "PREFLIGHT_ONLY",
                "repo_id": REPO_ID,
                "revision": REVISION,
                "payload_bytes": plan["model"]["expected_payload_bytes"],
                "runtime": plan["runtime_canary"],
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
        print(f"{NO_GO}:{exc}", file=sys.stderr)
        raise SystemExit(2)
