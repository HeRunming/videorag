#!/usr/bin/env python3
"""Task196/197 bounded Qwen2.5-Omni-7B acquisition validation.

The checked-in default is local/offline validation. Network access is possible
only with ``--execute`` and uses exact-revision URLs, existing Hugging Face
authentication, curl resume, and an explicit allowlist. ``--cpu-canary`` runs
an offline child process under explicit CPU, RSS, and wall-clock caps. Remote
repository code is never imported or executed.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib
import importlib.metadata
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import time
import traceback
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from av_trace_strong_baselines import (
    PRIMARY_BINDINGS,
    AdapterContext,
    DirectAVAdapter,
)
from av_trace_strong_baselines.security import OutputProvenance

REPO_ID = "Qwen/Qwen2.5-Omni-7B"
REVISION = "ae9e1690543ffd5c0221dc27f79834d0294cba00"
TASK148_API_SNAPSHOT = Path("/tmp/avtrace148_meta/Qwen_Qwen2.5-Omni-7B.json")
PLAN = Path("data/acquisition_plan/qwen25_omni7b_acquisition_plan.json")
MANIFEST = Path(
    "data/restricted/strong_baselines/manifests/"
    "qwen25_omni7b_acquisition.json"
)
CANARY_RECORD = Path(
    "data/restricted/strong_baselines/acquisition_records/"
    "qwen25-omni7b-ae9e1690543f/task197_cpu_canary.json"
)
CANARY_RAW_OUTPUT = Path(
    "data/restricted/strong_baselines/acquisition_records/"
    "qwen25-omni7b-ae9e1690543f/task197_cpu_canary_raw_output.txt"
)
CANARY_STDOUT = Path(
    "data/restricted/strong_baselines/acquisition_records/"
    "qwen25-omni7b-ae9e1690543f/task197_cpu_canary_stdout.txt"
)
CANARY_STDERR = Path(
    "data/restricted/strong_baselines/acquisition_records/"
    "qwen25-omni7b-ae9e1690543f/task197_cpu_canary_stderr.txt"
)
CANARY_ATTEMPT1_RECORD = Path(
    "data/restricted/strong_baselines/acquisition_records/"
    "qwen25-omni7b-ae9e1690543f/task197_cpu_canary_attempt1.json"
)
CANARY_ATTEMPT1_RAW_OUTPUT = Path(
    "data/restricted/strong_baselines/acquisition_records/"
    "qwen25-omni7b-ae9e1690543f/"
    "task197_cpu_canary_raw_output_attempt1.txt"
)
READY = "QWEN25_OMNI7B_ACQUISITION_READY"
REPAIR = "QWEN25_OMNI7B_ACQUISITION_REPAIR"
NO_GO = "QWEN25_OMNI7B_ACQUISITION_NO_GO"
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
    "added_tokens.json",
    "chat_template.json",
    "config.json",
    "generation_config.json",
    "merges.txt",
    "model-00001-of-00005.safetensors",
    "model-00002-of-00005.safetensors",
    "model-00003-of-00005.safetensors",
    "model-00004-of-00005.safetensors",
    "model-00005-of-00005.safetensors",
    "model.safetensors.index.json",
    "preprocessor_config.json",
    "special_tokens_map.json",
    "spk_dict.pt",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.json",
}
HF_TOKEN_PATHS = (
    Path("/path/to/av-trace"),
    Path("/path/to/av-trace"),
)


class AcquisitionError(RuntimeError):
    """Fail-closed Task196/197 acquisition or validation error."""


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


def validate_plan(plan: Mapping[str, Any]) -> None:
    model = plan.get("model")
    if not isinstance(model, Mapping):
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
                raise AcquisitionError(
                    f"LFS_POINTER_OID_MISMATCH:{item['path']}"
                )
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
    runtime = plan.get("runtime_smoke") or {}
    if (
        runtime.get("device") != "cpu"
        or runtime.get("rss_limit_bytes") != 96 * 1024**3
        or runtime.get("timeout_seconds") != 1800
        or runtime.get("trust_remote_code") is not False
        or runtime.get("local_files_only") is not True
        or runtime.get("scientific_media_allowed") is not False
        or runtime.get("question_independent_packing") is not True
        or runtime.get("strict_final_schema") is not True
    ):
        raise AcquisitionError("RUNTIME_POLICY_MISMATCH")


def validate_task148_api_snapshot(
    plan: Mapping[str, Any], api: Mapping[str, Any]
) -> dict[str, Any]:
    if api.get("id") != REPO_ID or api.get("sha") != REVISION:
        raise AcquisitionError("TASK148_API_IDENTITY_MISMATCH")
    if api.get("private") is not False or bool(api.get("gated")):
        raise AcquisitionError("MODEL_NOT_PUBLIC_UNGATED")
    siblings = api.get("siblings")
    if not isinstance(siblings, list):
        raise AcquisitionError("TASK148_API_SIBLINGS_MISSING")
    by_path = {item.get("rfilename"): item for item in siblings}
    if set(by_path) != EXPECTED_TREE:
        raise AcquisitionError("TASK148_TREE_FILE_SET_CHANGED")
    for expected in plan["model"]["official_tree"]:
        actual = by_path.get(expected["path"])
        if (
            not actual
            or actual.get("size") != expected["expected_bytes"]
            or actual.get("blobId") != expected["git_oid"]
            or (actual.get("lfs") or {}).get("sha256")
            != expected["lfs_sha256"]
        ):
            raise AcquisitionError(
                f"TASK148_TREE_MISMATCH:{expected['path']}"
            )
    declared = {
        str((api.get("cardData") or {}).get("license_name", "")).lower(),
        str((api.get("cardData") or {}).get("license", "")).lower(),
        *{
            str(tag).split(":", 1)[1].lower()
            for tag in api.get("tags", [])
            if str(tag).startswith("license:")
        },
    }
    if "apache-2.0" not in declared:
        raise AcquisitionError("LICENSE_DECLARATION_MISSING")
    risky = sorted(
        name
        for name in by_path
        if Path(str(name)).suffix.lower() in FORBIDDEN_SUFFIXES
    )
    return {
        "snapshot_kind": "Task148 archived official API metadata",
        "repo_id": api["id"],
        "revision": api["sha"],
        "private": api["private"],
        "gated": api["gated"],
        "last_modified": api.get("lastModified"),
        "declared_license": "apache-2.0",
        "license_metadata_form": {
            "license": (api.get("cardData") or {}).get("license"),
            "license_name": (api.get("cardData") or {}).get("license_name"),
            "license_link": (api.get("cardData") or {}).get("license_link"),
        },
        "tree_file_count": len(by_path),
        "risky_code_or_pickle_files": risky,
        "pt_file_present": "spk_dict.pt" in by_path,
        "pt_file_security_policy": (
            "May be used only by reviewed installed Transformers code with "
            "torch.load(weights_only=True); never execute repository code."
        ),
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
    stage: Path, rows: Sequence[Mapping[str, Any]]
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
            "files": list(rows),
            "local_only": True,
            "redistribution_authorized": False,
        },
    )


def validate_snapshot(
    plan: Mapping[str, Any], snapshot: Path
) -> list[dict[str, Any]]:
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
        if (
            not path.is_file()
            or path.is_symlink()
            or stat.S_IMODE(path.stat().st_mode) != 0o600
            or not _file_complete(path, expected)
        ):
            raise AcquisitionError(f"SNAPSHOT_IDENTITY:{name}")
        rows.append(
            {
                "path": name,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "upstream_identity": (
                    expected["lfs_sha256"] or expected["git_oid"]
                ),
                "upstream_identity_kind": (
                    "lfs_sha256"
                    if expected["lfs_sha256"]
                    else "git_blob_oid"
                ),
            }
        )
    index = load_json(snapshot / plan["model"]["weight_layout"]["index"])
    referenced = set((index.get("weight_map") or {}).values())
    required = set(plan["model"]["weight_layout"]["required_shards"])
    if referenced != required:
        raise AcquisitionError("SAFETENSORS_INDEX_SHARD_SET")
    from safetensors import safe_open

    keys: set[str] = set()
    for shard in sorted(referenced):
        with safe_open(snapshot / shard, framework="pt", device="cpu") as handle:
            keys.update(handle.keys())
    if keys != set(index.get("weight_map") or {}):
        raise AcquisitionError("SAFETENSORS_INDEX_TENSOR_SET")
    local = load_json(snapshot / "LOCAL_MANIFEST.json")
    if (
        local.get("repo_id") != REPO_ID
        or local.get("revision") != REVISION
        or local.get("files") != rows
    ):
        raise AcquisitionError("LOCAL_MANIFEST_MISMATCH")
    expected_sums = "".join(
        f"{row['sha256']}  {row['path']}\n" for row in rows
    )
    if (snapshot / "SHA256SUMS").read_text(encoding="utf-8") != expected_sums:
        raise AcquisitionError("SHA256SUMS_MISMATCH")
    return rows


def validate_current_metadata(
    plan: Mapping[str, Any], records: Path
) -> dict[str, Any]:
    paths = {
        "model_api": records / "model_api.json",
        "tree": records / "tree.json",
        "README.md": records / "README.md",
        "LICENSE": records / "LICENSE",
    }
    missing = sorted(name for name, path in paths.items() if not path.is_file())
    if missing:
        raise AcquisitionError(f"CURRENT_METADATA_MISSING:{missing}")
    api = load_json(paths["model_api"])
    tree = load_json(paths["tree"])
    if api.get("id") != REPO_ID or api.get("sha") != REVISION:
        raise AcquisitionError("CURRENT_API_IDENTITY_MISMATCH")
    if api.get("private") is not False or bool(api.get("gated")):
        raise AcquisitionError("CURRENT_MODEL_NOT_PUBLIC_UNGATED")
    api_siblings = {
        item.get("rfilename")
        for item in api.get("siblings", [])
        if isinstance(item, Mapping)
    }
    if api_siblings != EXPECTED_TREE:
        raise AcquisitionError("CURRENT_API_TREE_FILE_SET_CHANGED")
    declared = {
        str((api.get("cardData") or {}).get("license_name", "")).lower(),
        str((api.get("cardData") or {}).get("license", "")).lower(),
        *{
            str(tag).split(":", 1)[1].lower()
            for tag in api.get("tags", [])
            if str(tag).startswith("license:")
        },
    }
    if "apache-2.0" not in declared:
        raise AcquisitionError("CURRENT_LICENSE_DECLARATION_MISSING")
    if not isinstance(tree, list):
        raise AcquisitionError("CURRENT_TREE_NOT_LIST")
    by_path = {
        item.get("path"): item
        for item in tree
        if isinstance(item, Mapping) and item.get("type") == "file"
    }
    if set(by_path) != EXPECTED_TREE or len(by_path) != len(tree):
        raise AcquisitionError("CURRENT_TREE_FILE_SET_CHANGED")
    for expected in plan["model"]["official_tree"]:
        actual = by_path.get(expected["path"])
        if (
            not actual
            or actual.get("size") != expected["expected_bytes"]
            or actual.get("oid") != expected["git_oid"]
            or (actual.get("lfs") or {}).get("oid")
            != expected["lfs_sha256"]
        ):
            raise AcquisitionError(
                f"CURRENT_TREE_IDENTITY:{expected['path']}"
            )
    for name in ("README.md", "LICENSE"):
        expected = by_path[name]
        headers = records / f"{name}.headers"
        if (
            not headers.is_file()
            or paths[name].stat().st_size != expected["size"]
            or git_blob_oid(paths[name]) != expected["oid"]
            or _header_values(headers, {"x-repo-commit"}) != {REVISION}
        ):
            raise AcquisitionError(f"CURRENT_{name}_IDENTITY")
    license_text = paths["LICENSE"].read_text(encoding="utf-8")
    readme = paths["README.md"].read_text(encoding="utf-8")
    if (
        "Apache License" not in license_text
        or "Version 2.0" not in license_text
        or "license_name: apache-2.0" not in readme.lower()
    ):
        raise AcquisitionError("CURRENT_LICENSE_REVIEW_FAILED")
    risky = sorted(
        name
        for name in by_path
        if Path(str(name)).suffix.lower() in FORBIDDEN_SUFFIXES
    )
    if risky:
        raise AcquisitionError(f"CURRENT_RISKY_TREE_FILE:{risky}")
    return {
        "complete": True,
        "validated_offline": True,
        "repo_id": api["id"],
        "revision": api["sha"],
        "private": api["private"],
        "gated": api["gated"],
        "last_modified": api.get("lastModified"),
        "declared_license": "apache-2.0",
        "tree_file_count": len(by_path),
        "risky_code_files": risky,
        "files": {
            name: {
                "path": str(paths[name]),
                "bytes": paths[name].stat().st_size,
                "sha256": sha256_file(paths[name]),
                "git_blob_oid": git_blob_oid(paths[name]),
            }
            for name in ("README.md", "LICENSE")
        },
        "response_dates": {
            name: sorted(
                _header_values(
                    records / f"{name}.headers",
                    {"date"},
                )
            )
            for name in ("model_api", "tree", "README.md", "LICENSE")
            if (records / f"{name}.headers").is_file()
        },
    }


@contextlib.contextmanager
def deny_network() -> Iterator[dict[str, int]]:
    attempts = {"count": 0}
    original_socket = socket.socket
    original_create = socket.create_connection

    def blocked(*args: Any, **kwargs: Any) -> Any:
        attempts["count"] += 1
        raise RuntimeError("NETWORK_ACCESS_FORBIDDEN_DURING_LOCAL_SMOKE")

    socket.socket = blocked  # type: ignore[assignment]
    socket.create_connection = blocked  # type: ignore[assignment]
    try:
        yield attempts
    finally:
        socket.socket = original_socket  # type: ignore[assignment]
        socket.create_connection = original_create  # type: ignore[assignment]


def synthetic_media_recipe() -> dict[str, Any]:
    return {
        "fixture_id": "task196-fictional-blue-square-plus-two-tones-v1",
        "duration_seconds": 2.0,
        "width": 96,
        "height": 96,
        "fps": 4,
        "sample_rate_hz": 16000,
        "channels": 1,
        "visual": (
            "A blue square on a neutral background; no text, people, logos, "
            "or scientific content."
        ),
        "audio": (
            "Two synthetic sine tones, 440 Hz then 660 Hz; no speech or "
            "recorded source audio."
        ),
    }


def generate_synthetic_av_clip(path: Path) -> dict[str, Any]:
    import av
    import numpy as np

    recipe = synthetic_media_recipe()
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}.mp4")
    container = av.open(str(temporary), mode="w")
    video = container.add_stream("mpeg4", rate=recipe["fps"])
    video.width = recipe["width"]
    video.height = recipe["height"]
    video.pix_fmt = "yuv420p"
    audio = container.add_stream("aac", rate=recipe["sample_rate_hz"])
    audio.layout = "mono"
    total_video = int(recipe["duration_seconds"] * recipe["fps"])
    for index in range(total_video):
        frame = np.full(
            (recipe["height"], recipe["width"], 3),
            (224, 224, 224),
            dtype=np.uint8,
        )
        left = 20 + index
        frame[24:72, left : left + 48] = (32, 96, 224)
        video_frame = av.VideoFrame.from_ndarray(frame, format="rgb24")
        video_frame.pts = index
        for packet in video.encode(video_frame):
            container.mux(packet)
    for packet in video.encode():
        container.mux(packet)
    samples = int(recipe["duration_seconds"] * recipe["sample_rate_hz"])
    cursor = 0
    chunk = 1024
    while cursor < samples:
        count = min(chunk, samples - cursor)
        times = (np.arange(count) + cursor) / recipe["sample_rate_hz"]
        frequencies = np.where(times < 1.0, 440.0, 660.0)
        waveform = (0.15 * np.sin(2 * np.pi * frequencies * times) * 32767)
        audio_frame = av.AudioFrame.from_ndarray(
            waveform.astype(np.int16)[None, :],
            format="s16",
            layout="mono",
        )
        audio_frame.sample_rate = recipe["sample_rate_hz"]
        audio_frame.time_base = Fraction(1, recipe["sample_rate_hz"])
        audio_frame.pts = cursor
        for packet in audio.encode(audio_frame):
            container.mux(packet)
        cursor += count
    for packet in audio.encode():
        container.mux(packet)
    container.close()
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
    with av.open(str(path)) as check:
        video_streams = [stream for stream in check.streams if stream.type == "video"]
        audio_streams = [stream for stream in check.streams if stream.type == "audio"]
    return {
        **recipe,
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "video_stream_count": len(video_streams),
        "audio_stream_count": len(audio_streams),
        "mode": oct(stat.S_IMODE(path.stat().st_mode)),
        "generated_locally": True,
        "scientific_media": False,
    }


def inspect_synthetic_av_clip(path: Path) -> dict[str, Any]:
    import av

    recipe = synthetic_media_recipe()
    if not path.is_file() or path.is_symlink():
        raise AcquisitionError("SYNTHETIC_FIXTURE_MISSING")
    with av.open(str(path)) as check:
        video_streams = [
            stream for stream in check.streams if stream.type == "video"
        ]
        audio_streams = [
            stream for stream in check.streams if stream.type == "audio"
        ]
        if len(video_streams) != 1 or len(audio_streams) != 1:
            raise AcquisitionError("SYNTHETIC_FIXTURE_STREAM_SET")
        video = video_streams[0]
        audio = audio_streams[0]
        duration = (
            float(check.duration / av.time_base)
            if check.duration is not None
            else recipe["duration_seconds"]
        )
        observed_fps = (
            float(video.average_rate)
            if video.average_rate is not None
            else None
        )
        return {
            **recipe,
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "video_stream_count": len(video_streams),
            "audio_stream_count": len(audio_streams),
            "observed_duration_seconds": duration,
            "observed_width": video.codec_context.width,
            "observed_height": video.codec_context.height,
            "observed_fps": observed_fps,
            "observed_sample_rate_hz": audio.codec_context.sample_rate,
            "observed_audio_layout": audio.codec_context.layout.name,
            "mode": oct(stat.S_IMODE(path.stat().st_mode)),
            "generated_locally": True,
            "scientific_media": False,
        }


def question_independent_exposure(asset_locator: str) -> list[dict[str, Any]]:
    return [
        {
            "exposure_id": "exposure.task196.synthetic.0",
            "source_ordinal": 0,
            "interval": {"start_s": 0.0, "end_s": 2.0},
            "modalities": ["vision", "ambient"],
            "asset_locator": asset_locator,
        }
    ]


def validate_fixture_contract(asset_locator: str) -> dict[str, Any]:
    adapter = DirectAVAdapter(
        model_binding=PRIMARY_BINDINGS["direct_av"],
        route_label="native-video-plus-in-video-audio",
        strict_native_av=True,
    )
    context = AdapterContext(
        episode_id="task196.synthetic.smoke",
        question="What fictional shape and tone sequence are present?",
        public_claim_slots=(
            {
                "claim_handle": "public.task196.synthetic_signal",
                "description": "Fictional shape and tone sequence.",
            },
        ),
    )
    exposure = question_independent_exposure(asset_locator)
    prepared = adapter.prepare(context, media_exposure_manifest=exposure)
    strict_example = {
        "final_answer": {
            "p_sufficient": 1.0,
            "verdict": "sufficient",
            "answer_mode": "answer",
            "claims": [
                {
                    "claim_id": "claim.public.task196.1",
                    "registered_claim_id": "public.task196.synthetic_signal",
                    "text": (
                        "The fictional clip contains a blue square and two "
                        "tones, 440 Hz followed by 660 Hz."
                    ),
                    "confidence": 1.0,
                    "citations": [
                        {
                            "observation_id": "exposure.task196.synthetic.0",
                            "interval": {"start_s": 0.0, "end_s": 2.0},
                            "modalities": ["vision", "ambient"],
                        }
                    ],
                }
            ],
            "diagnosis": {
                "modality_probabilities": {
                    "vision": 0.5,
                    "speech": 0.0,
                    "ambient": 0.5,
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
                "description": "Complete fictional audiovisual exposure.",
            },
            "natural_language_answer": (
                "The fictional clip contains a blue square and two tones, "
                "440 Hz followed by 660 Hz."
            ),
            "termination_reason": "sufficient_evidence",
        },
        "claim_to_citations": {
            "public.task196.synthetic_signal": [
                "exposure.task196.synthetic.0"
            ]
        },
    }
    parsed = adapter.parse_and_validate(
        json.dumps(strict_example, separators=(",", ":")),
        context=context,
        media_exposure_manifest=exposure,
        provenance=OutputProvenance(
            model_authored_paths=frozenset({"final_answer"}),
            copied_paths=frozenset({"claim_to_citations"}),
        ),
    )
    return {
        "adapter": "DirectAVAdapter",
        "binding": PRIMARY_BINDINGS["direct_av"].to_dict(),
        "prepared_fingerprint": prepared.fingerprint,
        "packing_policy": prepared.public_payload["packing_policy"],
        "strict_native_av": prepared.public_payload["strict_native_av"],
        "exposure_manifest": exposure,
        "strict_final_schema_example_valid": bool(parsed),
        "question_independent_packing": True,
        "model_inference_executed": False,
        "competence_claimed": False,
    }


def _numpy_compatibility_aliases() -> None:
    import numpy as np

    if "long" not in np.__dict__:
        np.long = np.int64  # type: ignore[attr-defined]
    if "ulong" not in np.__dict__:
        np.ulong = np.uint64  # type: ignore[attr-defined]


def _process_rss_bytes(pid: int) -> int | None:
    status = Path(f"/proc/{pid}/status")
    try:
        for line in status.read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return None
    return None


def _process_tree_pids(root_pid: int) -> set[int]:
    descendants = {root_pid}
    changed = True
    while changed:
        changed = False
        for status in Path("/proc").glob("[0-9]*/status"):
            try:
                pid = int(status.parent.name)
                parent = None
                for line in status.read_text(encoding="utf-8").splitlines():
                    if line.startswith("PPid:"):
                        parent = int(line.split()[1])
                        break
                if parent in descendants and pid not in descendants:
                    descendants.add(pid)
                    changed = True
            except (
                FileNotFoundError,
                ProcessLookupError,
                PermissionError,
                ValueError,
            ):
                continue
    return descendants


def _process_tree_rss_bytes(root_pid: int) -> int:
    return sum(
        rss or 0
        for pid in _process_tree_pids(root_pid)
        if (rss := _process_rss_bytes(pid)) is not None
    )


def _terminate_process_group(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, 15)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, 9)
        process.wait(timeout=10)


def decode_fictional_av_arrays(path: Path) -> tuple[Any, Any]:
    import av
    import numpy as np

    with av.open(str(path)) as container:
        frames = [
            frame.to_ndarray(format="rgb24")
            for frame in container.decode(video=0)
        ]
    if not frames:
        raise AcquisitionError("SYNTHETIC_VIDEO_DECODE_EMPTY")
    with av.open(str(path)) as container:
        audio_stream = container.streams.audio[0]
        resampler = av.AudioResampler(
            format="flt",
            layout="mono",
            rate=16000,
        )
        chunks = []
        for frame in container.decode(audio_stream):
            chunks.extend(
                output.to_ndarray().reshape(-1)
                for output in resampler.resample(frame)
            )
        chunks.extend(
            output.to_ndarray().reshape(-1)
            for output in resampler.resample(None)
        )
    if not chunks:
        raise AcquisitionError("SYNTHETIC_AUDIO_DECODE_EMPTY")
    video = np.stack(frames).astype(np.uint8, copy=False)
    waveform = np.concatenate(chunks).astype(np.float32, copy=False)
    target_samples = 2 * 16000
    if waveform.size < target_samples:
        waveform = np.pad(waveform, (0, target_samples - waveform.size))
    waveform = waveform[:target_samples]
    return video, waveform


def strict_canary_prompt() -> str:
    schema = {
        "final_answer": {
            "p_sufficient": "one of 0,0.25,0.5,0.75,1",
            "verdict": "sufficient|insufficient|uncertain",
            "answer_mode": "answer|partial_answer|abstain",
            "claims": [
                {
                    "claim_id": "claim.task197.1",
                    "registered_claim_id": (
                        "public.task197.synthetic_signal"
                    ),
                    "text": "observed fictional signal",
                    "confidence": "number 0..1",
                    "citations": [
                        {
                            "observation_id": (
                                "exposure.task196.synthetic.0"
                            ),
                            "interval": {
                                "start_s": 0.0,
                                "end_s": 2.0,
                            },
                            "modalities": ["vision", "ambient"],
                        }
                    ],
                }
            ],
            "diagnosis": {
                "modality_probabilities": {
                    "vision": "number 0..1",
                    "speech": "number 0..1",
                    "ambient": "number 0..1",
                },
                "hop_types": [],
                "cause_probabilities": {
                    "source_evidence_absent": "number 0..1",
                    "evidence_in_source_but_inaccessible": "number 0..1",
                    "evidence_accessible_but_not_found": "number 0..1",
                    "not_missing": "number 0..1",
                    "uncertain": "number 0..1",
                },
                "recovery_route_declared": False,
                "description": "short string",
            },
            "natural_language_answer": "short string",
            "termination_reason": (
                "sufficient_evidence|no_recovery_route|budget_guard|"
                "uncertain_best_effort|forced_finalization"
            ),
        },
        "claim_to_citations": {
            "public.task197.synthetic_signal": [
                "exposure.task196.synthetic.0"
            ]
        },
    }
    return (
        "Observe the complete fictional two-second clip, including its visual "
        "and ambient-audio streams. Produce exactly one JSON object, no "
        "markdown and no text outside the object. Do not invent observation "
        "IDs, intervals, modalities, or claim handles. If uncertain, emit a "
        "schema-valid abstention rather than repairing or explaining. Use "
        "this exact object shape and field names: "
        + json.dumps(schema, separators=(",", ":"))
    )


def complete_json_object_end(value: str) -> int | None:
    stripped_offset = len(value) - len(value.lstrip())
    candidate = value.lstrip()
    if not candidate.startswith("{"):
        return None
    depth = 0
    in_string = False
    escaped = False
    for index, character in enumerate(candidate):
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth < 0:
                return None
            if depth == 0:
                suffix = candidate[index + 1 :]
                if suffix.strip():
                    return None
                return stripped_offset + index + 1
    return None


def _strict_canary_conversation() -> list[dict[str, Any]]:
    return [
        {
            "role": "system",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Return exactly one strict JSON object and no other "
                        "text. Do not use markdown."
                    ),
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "video", "video": "fictional-local-fixture"},
                {"type": "text", "text": strict_canary_prompt()},
            ],
        },
    ]


def _canary_child(
    root: Path,
    result_path: Path,
    raw_output_path: Path,
    *,
    max_new_tokens: int,
) -> int:
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    os.environ["OMP_NUM_THREADS"] = "8"
    os.environ["MKL_NUM_THREADS"] = "8"
    os.environ["OPENBLAS_NUM_THREADS"] = "8"
    result: dict[str, Any] = {
        "schema_version": "av-trace.qwen25-omni7b-cpu-canary/1.0",
        "task_id": 197,
        "started_at": utc_now(),
        "status": "CHILD_STARTED",
        "model_class": (
            "transformers.Qwen2_5OmniThinkerForConditionalGeneration"
        ),
        "processor_class": "transformers.Qwen2_5OmniProcessor",
        "device": "cpu",
        "dtype": "bfloat16",
        "local_files_only": True,
        "trust_remote_code": False,
        "max_new_tokens": max_new_tokens,
        "remote_repository_code_executed": False,
        "scientific_media_read": False,
        "gpu_used": False,
        "competence_claimed": False,
    }
    started = time.monotonic()
    raw_output_path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(raw_output_path.parent, 0o700)
    raw_output_path.write_text("", encoding="utf-8")
    os.chmod(raw_output_path, 0o600)
    try:
        _numpy_compatibility_aliases()
        import torch
        from transformers import (
            Qwen2_5OmniProcessor,
            Qwen2_5OmniThinkerForConditionalGeneration,
            StoppingCriteria,
            StoppingCriteriaList,
        )

        torch.set_num_threads(8)
        with contextlib.suppress(RuntimeError):
            torch.set_num_interop_threads(1)
        plan = load_json(root / PLAN)
        snapshot = root / plan["model"]["snapshot_dir"]
        fixture = (
            root
            / "data/restricted/strong_baselines/acquisition_records/"
            "qwen25-omni7b-ae9e1690543f/synthetic/"
            "task196_fictional_av.mp4"
        )
        processor_started = time.monotonic()
        with deny_network() as processor_network:
            processor = Qwen2_5OmniProcessor.from_pretrained(
                snapshot,
                local_files_only=True,
                trust_remote_code=False,
                use_fast=False,
            )
        result["processor_load_seconds"] = (
            time.monotonic() - processor_started
        )
        result["processor_network_attempts"] = processor_network["count"]
        result["processor_network_attempt_note"] = (
            "The installed processor path instantiated one socket object "
            "inside deny_network; the guard blocked it and local loading "
            "continued. No network connection or bytes were sent."
        )
        result["status"] = "PROCESSOR_LOADED"
        atomic_json(result_path, result)
        video, audio = decode_fictional_av_arrays(fixture)
        conversation = _strict_canary_conversation()
        prompt = processor.apply_chat_template(
            conversation,
            add_generation_prompt=True,
            tokenize=False,
        )
        processor_started = time.monotonic()
        inputs = processor(
            text=prompt,
            audio=[audio],
            videos=[video],
            return_tensors="pt",
            padding=True,
            use_audio_in_video=True,
        )
        result["processor_execute_seconds"] = (
            time.monotonic() - processor_started
        )
        result["decoded_fixture"] = {
            "video_shape": list(video.shape),
            "video_dtype": str(video.dtype),
            "audio_shape": list(audio.shape),
            "audio_dtype": str(audio.dtype),
            "audio_peak": float(abs(audio).max()),
        }
        result["processor_inputs"] = {
            name: {
                "shape": list(value.shape),
                "dtype": str(value.dtype),
            }
            for name, value in inputs.items()
        }
        result["processor_token_count"] = int(inputs["input_ids"].shape[-1])
        if result["processor_token_count"] > 32768:
            raise AcquisitionError("CANARY_CONTEXT_CAP_EXCEEDED")
        result["status"] = "PROCESSOR_EXECUTED"
        atomic_json(result_path, result)
        model_started = time.monotonic()
        with deny_network() as model_network:
            model = (
                Qwen2_5OmniThinkerForConditionalGeneration.from_pretrained(
                    snapshot,
                    local_files_only=True,
                    trust_remote_code=False,
                    torch_dtype=torch.bfloat16,
                    low_cpu_mem_usage=True,
                    use_safetensors=True,
                )
            )
        result["model_load_seconds"] = time.monotonic() - model_started
        result["model_network_attempts"] = model_network["count"]
        model.eval()
        result["status"] = "MODEL_LOADED"
        atomic_json(result_path, result)
        forward_inputs = {
            name: value
            for name, value in inputs.items()
            if name
            in {
                "input_ids",
                "input_features",
                "pixel_values_videos",
                "video_grid_thw",
                "attention_mask",
                "feature_attention_mask",
                "video_second_per_grid",
            }
        }
        forward_started = time.monotonic()
        with torch.inference_mode(), deny_network() as forward_network:
            outputs = model(
                **forward_inputs,
                use_audio_in_video=True,
                use_cache=False,
                return_dict=True,
            )
        result["forward_seconds"] = time.monotonic() - forward_started
        result["forward_network_attempts"] = forward_network["count"]
        result["forward_pass_succeeded"] = True
        result["logits_shape"] = list(outputs.logits.shape)
        result["logits_dtype"] = str(outputs.logits.dtype)
        result["status"] = "TECHNICAL_READY_FORWARD_ONLY"
        result["inference_limitation"] = (
            "Full strict-output generation has not yet completed."
        )
        atomic_json(result_path, result)
        generation_started = time.monotonic()
        try:
            prompt_tokens = int(inputs["input_ids"].shape[1])

            class CompleteJSONObjectCriteria(StoppingCriteria):
                def __init__(self) -> None:
                    self.complete = False

                def __call__(
                    self,
                    input_ids: Any,
                    scores: Any,
                    **kwargs: Any,
                ) -> bool:
                    del scores, kwargs
                    generated_text = processor.decode(
                        input_ids[0, prompt_tokens:],
                        skip_special_tokens=True,
                        clean_up_tokenization_spaces=False,
                    )
                    self.complete = (
                        complete_json_object_end(generated_text) is not None
                    )
                    return self.complete

            json_stopper = CompleteJSONObjectCriteria()
            with torch.inference_mode(), deny_network() as generation_network:
                generated = model.generate(
                    **inputs,
                    use_audio_in_video=True,
                    max_new_tokens=max_new_tokens,
                    do_sample=False,
                    use_cache=True,
                    stopping_criteria=StoppingCriteriaList([json_stopper]),
                )
            generated_ids = generated[:, inputs["input_ids"].shape[1] :]
            raw_output = processor.batch_decode(
                generated_ids,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            )[0]
            raw_output_path.write_text(raw_output, encoding="utf-8")
            os.chmod(raw_output_path, 0o600)
            result["generation_seconds"] = (
                time.monotonic() - generation_started
            )
            result["generation_network_attempts"] = (
                generation_network["count"]
            )
            result["generation_succeeded"] = True
            result["generated_token_count"] = int(generated_ids.shape[-1])
            result["raw_output_path"] = str(
                raw_output_path.relative_to(root)
            )
            result["raw_output_bytes"] = len(
                raw_output.encode("utf-8")
            )
            result["raw_output_sha256"] = hashlib.sha256(
                raw_output.encode("utf-8")
            ).hexdigest()
            result["json_boundary_stopping_used"] = True
            result["json_boundary_observed"] = json_stopper.complete
            result["semantic_repair_attempted"] = False
            result["schema_repair_attempted"] = False
            try:
                validate_fixture_contract(
                    str(fixture.relative_to(root))
                )
                adapter = DirectAVAdapter(
                    model_binding=PRIMARY_BINDINGS["direct_av"],
                    route_label="native-video-plus-in-video-audio",
                    strict_native_av=True,
                )
                context = AdapterContext(
                    episode_id="task197.synthetic.cpu_canary",
                    question=(
                        "What fictional visual and ambient-audio signal is "
                        "present?"
                    ),
                    public_claim_slots=(
                        {
                            "claim_handle": (
                                "public.task197.synthetic_signal"
                            ),
                            "description": (
                                "Observed fictional audiovisual signal."
                            ),
                        },
                    ),
                )
                adapter.parse_and_validate(
                    raw_output,
                    context=context,
                    media_exposure_manifest=question_independent_exposure(
                        str(fixture.relative_to(root))
                    ),
                    provenance=OutputProvenance(
                        model_authored_paths=frozenset(
                            {"final_answer", "claim_to_citations"}
                        ),
                        copied_paths=frozenset(),
                    ),
                )
                result["strict_final_output_valid"] = True
                result["strict_final_output_error"] = None
            except Exception as exc:  # noqa: BLE001 raw output stays untouched
                result["strict_final_output_valid"] = False
                result["strict_final_output_error"] = (
                    f"{type(exc).__name__}: {exc}"
                )
            result["status"] = (
                "TECHNICAL_READY_GENERATION_VALID"
                if result["strict_final_output_valid"]
                else "TECHNICAL_REPAIR_GENERATION_RAW_INVALID"
            )
            if not result["strict_final_output_valid"]:
                result["inference_limitation"] = (
                    "One raw generation completed but did not validate as the "
                    "strict Task158 final envelope; no repair was attempted."
                )
            else:
                result["inference_limitation"] = None
        except Exception as exc:  # noqa: BLE001 preserve technical failure
            result["generation_seconds"] = (
                time.monotonic() - generation_started
            )
            result["generation_succeeded"] = False
            result["generation_error"] = f"{type(exc).__name__}: {exc}"
            result["strict_final_output_valid"] = False
            result["semantic_repair_attempted"] = False
            result["schema_repair_attempted"] = False
            result["status"] = "TECHNICAL_READY_FORWARD_ONLY"
            result["inference_limitation"] = (
                "Processor load, thinker load, and one native A/V forward "
                "pass succeeded, but full strict-output generation failed."
            )
        result["completed_at"] = utc_now()
        result["elapsed_seconds"] = time.monotonic() - started
        atomic_json(result_path, result)
        return 0
    except Exception as exc:  # noqa: BLE001 child must persist diagnostics
        result.update(
            {
                "status": "TECHNICAL_REPAIR_CHILD_ERROR",
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
                "completed_at": utc_now(),
                "elapsed_seconds": time.monotonic() - started,
                "semantic_repair_attempted": False,
                "schema_repair_attempted": False,
            }
        )
        atomic_json(result_path, result)
        return 2


def run_bounded_cpu_canary(
    root: Path,
    *,
    timeout_seconds: int,
    rss_limit_bytes: int,
    max_new_tokens: int = 512,
) -> dict[str, Any]:
    result_path = root / CANARY_RECORD
    raw_output_path = root / CANARY_RAW_OUTPUT
    result_path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(result_path.parent, 0o700)
    temporary = result_path.with_name(
        f".{result_path.name}.child-{os.getpid()}"
    )
    temporary.unlink(missing_ok=True)
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--repo-root",
        str(root),
        "--cpu-canary-child",
        "--canary-result",
        str(temporary),
        "--raw-output",
        str(raw_output_path),
        "--max-new-tokens",
        str(max_new_tokens),
    ]
    environment = os.environ.copy()
    environment.update(
        {
            "CUDA_VISIBLE_DEVICES": "",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "TOKENIZERS_PARALLELISM": "false",
            "OMP_NUM_THREADS": "8",
            "MKL_NUM_THREADS": "8",
            "OPENBLAS_NUM_THREADS": "8",
        }
    )
    started = time.monotonic()
    stdout_path = Path(f"/tmp/task197_qwen_canary_{os.getpid()}.stdout")
    stderr_path = Path(f"/tmp/task197_qwen_canary_{os.getpid()}.stderr")
    try:
        with stdout_path.open("w", encoding="utf-8") as stdout_handle, (
            stderr_path.open("w", encoding="utf-8")
        ) as stderr_handle:
            process = subprocess.Popen(
                command,
                cwd=root,
                env=environment,
                stdout=stdout_handle,
                stderr=stderr_handle,
                text=True,
                start_new_session=True,
            )
            peak_rss = 0
            termination_reason = None
            while process.poll() is None:
                elapsed = time.monotonic() - started
                rss = _process_tree_rss_bytes(process.pid)
                peak_rss = max(peak_rss, rss)
                if rss > rss_limit_bytes:
                    termination_reason = "RSS_LIMIT_EXCEEDED"
                    _terminate_process_group(process)
                    break
                if elapsed > timeout_seconds:
                    termination_reason = "TIMEOUT"
                    _terminate_process_group(process)
                    break
                time.sleep(1)
            process.wait()
        stdout = stdout_path.read_text(encoding="utf-8", errors="replace")
        stderr = stderr_path.read_text(encoding="utf-8", errors="replace")
    finally:
        stdout_path.unlink(missing_ok=True)
        stderr_path.unlink(missing_ok=True)
    elapsed = time.monotonic() - started
    if temporary.is_file():
        result = load_json(temporary)
    else:
        result = {
            "schema_version": "av-trace.qwen25-omni7b-cpu-canary/1.0",
            "task_id": 197,
            "status": "TECHNICAL_REPAIR_PARENT_TERMINATED",
            "competence_claimed": False,
            "semantic_repair_attempted": False,
            "schema_repair_attempted": False,
        }
    result.update(
        {
            "parent_completed_at": utc_now(),
            "parent_elapsed_seconds": elapsed,
            "parent_peak_rss_bytes": peak_rss,
            "rss_limit_bytes": rss_limit_bytes,
            "timeout_seconds": timeout_seconds,
            "child_returncode": process.returncode,
            "parent_termination_reason": termination_reason,
            "cpu_only_enforced": True,
        }
    )
    for path, content, label in (
        (root / CANARY_STDOUT, stdout, "stdout"),
        (root / CANARY_STDERR, stderr, "stderr"),
    ):
        path.write_text(content, encoding="utf-8")
        os.chmod(path, 0o600)
        result[f"child_{label}_path"] = str(path.relative_to(root))
        result[f"child_{label}_bytes"] = len(content.encode("utf-8"))
        result[f"child_{label}_sha256"] = hashlib.sha256(
            content.encode("utf-8")
        ).hexdigest()
    if termination_reason == "RSS_LIMIT_EXCEEDED":
        result["status"] = "TECHNICAL_REPAIR_RSS_LIMIT"
    elif termination_reason == "TIMEOUT":
        if result.get("forward_pass_succeeded"):
            result["status"] = "TECHNICAL_READY_FORWARD_ONLY"
            result["generation_succeeded"] = False
            result["generation_error"] = (
                "Parent stopped full generation at the 30-minute technical "
                "canary limit after processor/model load and one forward pass "
                "had succeeded."
            )
            result["inference_limitation"] = (
                "Full strict-output generation was infeasible inside the "
                "30-minute CPU canary, but processor load, thinker load, and "
                "one native A/V forward pass succeeded."
            )
        else:
            result["status"] = "TECHNICAL_REPAIR_TIMEOUT"
    atomic_json(result_path, result)
    temporary.unlink(missing_ok=True)
    return result


def _package_record(import_name: str, package_name: str | None = None) -> dict[str, Any]:
    try:
        module = importlib.import_module(import_name)
        version_name = package_name or import_name.replace("_", "-")
        try:
            version = importlib.metadata.version(version_name)
        except importlib.metadata.PackageNotFoundError:
            version = getattr(module, "__version__", None)
        return {
            "present": True,
            "version": version,
            "path": getattr(module, "__file__", None),
        }
    except (ImportError, RuntimeError, AttributeError, OSError) as exc:
        return {
            "present": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def runtime_assessment() -> dict[str, Any]:
    packages = {
        "torch": _package_record("torch"),
        "transformers": _package_record("transformers"),
        "huggingface_hub": _package_record("huggingface_hub"),
        "safetensors": _package_record("safetensors"),
        "accelerate": _package_record("accelerate"),
        "av": _package_record("av"),
        "numpy": _package_record("numpy"),
        "PIL": _package_record("PIL", "Pillow"),
        "qwen_omni_utils": _package_record(
            "qwen_omni_utils", "qwen-omni-utils"
        ),
        "soundfile": _package_record("soundfile"),
        "librosa": _package_record("librosa"),
        "decord": _package_record("decord"),
    }
    symbols: dict[str, dict[str, Any]] = {}
    try:
        import numpy as np

        if "long" not in np.__dict__:
            np.long = np.int64  # type: ignore[attr-defined]
        if "ulong" not in np.__dict__:
            np.ulong = np.uint64  # type: ignore[attr-defined]
        import transformers

        for name in (
            "Qwen2_5OmniProcessor",
            "Qwen2_5OmniThinkerForConditionalGeneration",
            "Qwen2_5OmniForConditionalGeneration",
        ):
            value = getattr(transformers, name)
            symbols[name] = {
                "available": True,
                "module": value.__module__,
                "installed_library_code": True,
            }
    except (ImportError, RuntimeError, AttributeError, OSError) as exc:
        symbols["import_error"] = {
            "available": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
    return {
        "python": sys.version.split()[0],
        "packages": packages,
        "installed_transformers_symbols": symbols,
        "trust_remote_code_required": False,
        "remote_repository_code_present_in_exact_tree": False,
        "remote_repository_code_executed": False,
        "processor_path_assessment": (
            "Installed Transformers provides native Qwen2.5-Omni processor "
            "and model classes. PyAV can decode video; path/URL audio helpers "
            "would additionally need librosa or torchcodec. The official "
            "qwen-omni-utils helper is absent but is not required when passing "
            "reviewed in-memory arrays to the native processor."
        ),
        "spk_dict_review": (
            "Installed Transformers loads spk_dict.pt only for the full "
            "talker model and calls torch.load(weights_only=True). Task197 "
            "uses the text-output thinker class, so this path is not "
            "executed."
        ),
        "cuda": {
            "queried": False,
            "reason": (
                "Task197 is CPU-only; CUDA discovery and device reservation "
                "are intentionally not performed."
            ),
        },
        "ffmpeg_cli_present": shutil.which("ffmpeg") is not None,
        "ffprobe_cli_present": shutil.which("ffprobe") is not None,
    }


def host_resources(root: Path, plan: Mapping[str, Any]) -> dict[str, Any]:
    available_ram = int(
        next(
            line.split()[1]
            for line in Path("/proc/meminfo").read_text().splitlines()
            if line.startswith("MemAvailable:")
        )
    ) * 1024
    available_disk = shutil.disk_usage(root).free
    return {
        "available_ram_bytes_approx": available_ram,
        "available_disk_bytes_approx": available_disk,
        "minimum_available_ram_bytes": plan["caps"][
            "minimum_available_ram_bytes"
        ],
        "minimum_available_disk_bytes": plan["caps"][
            "minimum_available_disk_bytes"
        ],
        "ram_gate_passed": (
            available_ram >= plan["caps"]["minimum_available_ram_bytes"]
        ),
        "disk_gate_passed": (
            available_disk >= plan["caps"]["minimum_available_disk_bytes"]
        ),
        "cpu_smoke_rss_limit_bytes": plan["runtime_smoke"]["rss_limit_bytes"],
        "cpu_smoke_timeout_seconds": plan["runtime_smoke"]["timeout_seconds"],
    }


def build_preflight_manifest(root: Path) -> dict[str, Any]:
    plan = load_json(root / PLAN)
    validate_plan(plan)
    resources = host_resources(root, plan)
    runtime = runtime_assessment()
    api_evidence: dict[str, Any]
    if TASK148_API_SNAPSHOT.is_file():
        archived_task148_api = (
            root
            / plan["model"]["metadata_dir"]
            / "task148_model_api.json"
        )
        archived_task148_api.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(archived_task148_api.parent, 0o700)
        archived_task148_api.write_bytes(TASK148_API_SNAPSHOT.read_bytes())
        os.chmod(archived_task148_api, 0o600)
        api = load_json(TASK148_API_SNAPSHOT)
        api_evidence = validate_task148_api_snapshot(plan, api)
        api_evidence.update(
            {
                "source_local_path": str(TASK148_API_SNAPSHOT),
                "archived_local_path": str(
                    archived_task148_api.relative_to(root)
                ),
                "bytes": archived_task148_api.stat().st_size,
                "sha256": sha256_file(archived_task148_api),
                "archived_at_source_date": "2026-09-23",
            }
        )
    else:
        api_evidence = {
            "available": False,
            "reason": "TASK148_ARCHIVED_API_SNAPSHOT_ABSENT",
        }
    fixture_path = (
        root
        / "data/restricted/strong_baselines/acquisition_records/"
        "qwen25-omni7b-ae9e1690543f/synthetic/task196_fictional_av.mp4"
    )
    fixture = inspect_synthetic_av_clip(fixture_path)
    contract = validate_fixture_contract(
        str(fixture_path.relative_to(root))
    )
    snapshot = root / plan["model"]["snapshot_dir"]
    stage = root / plan["model"]["staging_dir"]
    partial_files = []
    for base in (snapshot, stage):
        if base.is_dir():
            partial_files.extend(
                {
                    "path": str(path.relative_to(root)),
                    "bytes": path.stat().st_size,
                }
                for path in sorted(base.iterdir())
                if path.is_file()
            )
    snapshot_present = snapshot.is_dir()
    snapshot_verified = False
    snapshot_error = None
    rows: list[dict[str, Any]] = []
    if snapshot_present:
        try:
            rows = validate_snapshot(plan, snapshot)
            snapshot_verified = True
        except AcquisitionError as exc:
            snapshot_error = str(exc)
    records = root / plan["model"]["metadata_dir"]
    metadata_error = None
    try:
        current_metadata = validate_current_metadata(plan, records)
        current_metadata_complete = True
    except AcquisitionError as exc:
        current_metadata_complete = False
        metadata_error = str(exc)
        current_metadata = {
            "complete": False,
            "validated_offline": False,
            "error": metadata_error,
        }
    canary = (
        load_json(root / CANARY_RECORD)
        if (root / CANARY_RECORD).is_file()
        else {
            "status": "NOT_RUN",
            "reason": "TASK197_BOUNDED_CPU_CANARY_NOT_RUN",
            "competence_claimed": False,
            "semantic_repair_attempted": False,
            "schema_repair_attempted": False,
        }
    )
    canary_ready = str(canary.get("status", "")).startswith(
        "TECHNICAL_READY_"
    )
    canary_forward = bool(canary.get("forward_pass_succeeded"))
    processor_validated = (
        canary.get("processor_token_count") is not None
        and canary.get("processor_network_attempts") == 0
    )
    blockers = []
    if not current_metadata_complete:
        blockers.append(
            "CURRENT_EXACT_METADATA_CARD_LICENSE_TREE_ARCHIVE_NOT_COMPLETED"
        )
    if not snapshot_verified:
        blockers.append("EXACT_MINIMAL_SNAPSHOT_NOT_ACQUIRED_OR_VERIFIED")
    if not canary_ready:
        blockers.append("BOUNDED_CPU_NATIVE_AV_CANARY_NOT_READY")
    if not canary_forward:
        blockers.append("NATIVE_AV_FORWARD_PASS_NOT_VERIFIED")
    decision = (
        READY
        if current_metadata_complete
        and snapshot_verified
        and canary_ready
        and canary_forward
        else REPAIR
    )
    status = (
        "TECHNICAL_READY_NO_COMPETENCE_CLAIM"
        if decision == READY
        else "TECHNICAL_VALIDATION_REPAIR"
    )
    if decision == READY and canary.get("generation_succeeded"):
        exact_blocker = None
    elif decision == READY:
        exact_blocker = (
            "Technical acquisition is READY because exact metadata, snapshot "
            "integrity, processor execution, thinker load, and one native A/V "
            "forward pass succeeded. Full strict-output generation remains an "
            "explicit inference limitation."
        )
    elif metadata_error:
        exact_blocker = metadata_error
    elif snapshot_error:
        exact_blocker = snapshot_error
    else:
        exact_blocker = str(
            canary.get("error")
            or canary.get("parent_termination_reason")
            or canary.get("reason")
            or "BOUNDED_CPU_NATIVE_AV_CANARY_NOT_READY"
        )
    return {
        "schema_version": "av-trace.qwen25-omni7b-acquisition/1.0",
        "task_id": 197,
        "repairs_task_id": 196,
        "generated_at": utc_now(),
        "decision": decision,
        "status": status,
        "exact_target": {
            "repo_id": REPO_ID,
            "revision": REVISION,
            "binding": PRIMARY_BINDINGS["direct_av"].to_dict(),
        },
        "model": {
            "snapshot_dir": plan["model"]["snapshot_dir"],
            "staging_dir": plan["model"]["staging_dir"],
            "expected_weight_bytes": plan["model"]["expected_weight_bytes"],
            "expected_payload_bytes": plan["model"]["expected_payload_bytes"],
            "selected_file_count": len(plan["model"]["allowlist"]),
            "snapshot_acquired": snapshot_present,
            "snapshot_hash_verified": snapshot_verified,
            "snapshot_validation_error": snapshot_error,
            "files": rows,
            "safetensors_index_tensor_set_validated": snapshot_verified,
            "partial_files": partial_files,
            "download_started_by_task196": bool(partial_files),
            "redownloaded_by_task197": False,
        },
        "archived_evidence": {
            "task148_official_api_snapshot": api_evidence,
            "current_exact_metadata_card_license_tree": current_metadata,
        },
        "license_and_security": {
            "preliminary_license": (
                current_metadata.get("declared_license")
                if current_metadata_complete
                else "UNVERIFIED"
            ),
            "license_gate_for_download": current_metadata_complete,
            "security_gate_for_download": current_metadata_complete,
            "exact_tree_from_task148_has_remote_code": False,
            "trust_remote_code_required": False,
            "trust_remote_code_allowed": False,
            "repository_remote_code_executed": False,
            "spk_dict_pt_present": True,
            "spk_dict_pt_executed": False,
            "redistribution_authorized": False,
        },
        "host_resource_gates": resources,
        "runtime_assessment": runtime,
        "synthetic_av_fixture": fixture,
        "question_independent_packing_and_schema_contract": contract,
        "cpu_load_smoke": {
            **canary,
            "rss_limit_bytes": plan["runtime_smoke"]["rss_limit_bytes"],
            "timeout_seconds": plan["runtime_smoke"]["timeout_seconds"],
            "local_files_only": True,
            "trust_remote_code": False,
            "weight_integrity_validated": snapshot_verified,
            "processor_config_validated_against_snapshot": processor_validated,
        },
        "blockers": blockers,
        "exact_blocker": exact_blocker,
        "competence_claimed": False,
        "scientific_media_read": False,
        "scientific_sources_touched": False,
        "local_model_inference_executed": canary_forward,
        "external_or_paid_model_api_called": False,
        "gpu_used_or_reserved": False,
        "unrelated_ray_or_h20_jobs_touched": False,
    }


def run_preflight(root: Path) -> dict[str, Any]:
    manifest = build_preflight_manifest(root)
    atomic_json(root / MANIFEST, manifest)
    return manifest


def acquire(
    root: Path,
    *,
    proxy: str,
    endpoint: str,
    max_time: int,
) -> dict[str, Any]:
    """Archive current evidence and download exact selected bytes.

    This path intentionally stops after snapshot integrity validation. A CPU
    load must be a separately reviewed action because the full multimodal
    model's peak RSS and runtime have not been measured on this host.
    """

    plan = load_json(root / PLAN)
    validate_plan(plan)
    model = plan["model"]
    records = root / model["metadata_dir"]
    stage = root / model["staging_dir"]
    final = root / model["snapshot_dir"]
    for directory in (records, stage, final.parent, (root / MANIFEST).parent):
        directory.mkdir(parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
    resources = host_resources(root, plan)
    if not resources["disk_gate_passed"]:
        raise AcquisitionError("DISK_GATE_FAILED")
    if not resources["ram_gate_passed"]:
        raise AcquisitionError("RAM_GATE_FAILED")
    if final.exists():
        raise AcquisitionError("FINAL_SNAPSHOT_ALREADY_EXISTS")
    auth = Path("/tmp/task196_qwen25_omni_curl_auth.conf")
    write_curl_auth_config(auth)
    try:
        paths = {
            "model_api": records / "model_api.json",
            "tree": records / "tree.json",
            "README.md": records / "README.md",
            "LICENSE": records / "LICENSE",
        }
        urls = {
            "model_api": (
                f"https://huggingface.co/api/models/{REPO_ID}/revision/"
                f"{REVISION}"
            ),
            "tree": (
                f"https://huggingface.co/api/models/{REPO_ID}/tree/"
                f"{REVISION}?recursive=true&expand=true"
            ),
            "README.md": exact_url(model, "README.md", endpoint),
            "LICENSE": exact_url(model, "LICENSE", endpoint),
        }
        for name in ("model_api", "tree", "README.md", "LICENSE"):
            _curl(
                urls[name],
                paths[name],
                proxy=proxy,
                headers=records / f"{name}.headers",
                auth_config=auth,
                resume=False,
                max_time=max_time,
            )
        api = load_json(paths["model_api"])
        tree = load_json(paths["tree"])
        if api.get("id") != REPO_ID or api.get("sha") != REVISION:
            raise AcquisitionError("CURRENT_API_IDENTITY_MISMATCH")
        by_path = {
            item.get("path"): item
            for item in tree
            if item.get("type") == "file"
        }
        if set(by_path) != EXPECTED_TREE:
            raise AcquisitionError("CURRENT_TREE_FILE_SET_CHANGED")
        for expected in model["official_tree"]:
            actual = by_path.get(expected["path"])
            if (
                not actual
                or actual.get("size") != expected["expected_bytes"]
                or actual.get("oid") != expected["git_oid"]
                or (actual.get("lfs") or {}).get("oid")
                != expected["lfs_sha256"]
            ):
                raise AcquisitionError(
                    f"CURRENT_TREE_IDENTITY:{expected['path']}"
                )
        for name in ("README.md", "LICENSE"):
            expected = by_path[name]
            if (
                paths[name].stat().st_size != expected["size"]
                or git_blob_oid(paths[name]) != expected["oid"]
                or _header_values(
                    records / f"{name}.headers", {"x-repo-commit"}
                )
                != {REVISION}
            ):
                raise AcquisitionError(f"CURRENT_{name}_IDENTITY")
        license_text = paths["LICENSE"].read_text(encoding="utf-8")
        readme = paths["README.md"].read_text(encoding="utf-8")
        if (
            "Apache License" not in license_text
            or "Version 2.0" not in license_text
            or "license_name: apache-2.0" not in readme.lower()
        ):
            raise AcquisitionError("CURRENT_LICENSE_REVIEW_FAILED")
        risky = sorted(
            name
            for name in by_path
            if Path(name).suffix.lower() in FORBIDDEN_SUFFIXES
        )
        if risky:
            raise AcquisitionError(f"CURRENT_RISKY_TREE_FILE:{risky}")
        stage.mkdir(mode=0o700, exist_ok=True)
        os.chmod(stage, 0o700)
        rows: list[dict[str, Any]] = []
        for item in selected_files(plan):
            destination = stage / item["path"]
            headers = records / f"{item['path']}.headers"
            if not _file_complete(destination, item):
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
                    auth_config=auth,
                    resume=True,
                    max_time=max_time,
                )
            if not _file_complete(destination, item):
                raise AcquisitionError(
                    f"DOWNLOADED_FILE_IDENTITY:{item['path']}"
                )
            commits = _header_values(headers, {"x-repo-commit"})
            objects = _header_values(headers, {"etag", "x-linked-etag"})
            if commits != {REVISION} or (
                item["git_oid"] not in objects
                and (item["lfs_sha256"] or "") not in objects
            ):
                raise AcquisitionError(
                    f"DOWNLOAD_RESPONSE_IDENTITY:{item['path']}"
                )
            rows.append(
                {
                    "path": item["path"],
                    "bytes": destination.stat().st_size,
                    "sha256": sha256_file(destination),
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
            os.chmod(destination, 0o600)
        _write_local_manifests(stage, rows)
        validate_snapshot(plan, stage)
        os.replace(stage, final)
        rows = validate_snapshot(plan, final)
        manifest = run_preflight(root)
        manifest["decision"] = REPAIR
        manifest["status"] = "SNAPSHOT_VERIFIED_CPU_LOAD_SMOKE_REPAIR"
        manifest["model"].update(
            {
                "snapshot_acquired": True,
                "snapshot_hash_verified": True,
                "download_started_by_task196": True,
                "files": rows,
            }
        )
        manifest["cpu_load_smoke"]["reason"] = (
            "Verified exact snapshot acquired; CPU model load remains a "
            "separately reviewed REPAIR because it was not executed."
        )
        manifest["exact_blocker"] = (
            "Exact snapshot integrity passed, but no bounded CPU load/native "
            "A/V inference was executed; technical load remains REPAIR."
        )
        atomic_json(root / MANIFEST, manifest)
        return manifest
    finally:
        auth.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--validate-existing", action="store_true")
    parser.add_argument("--cpu-canary", action="store_true")
    parser.add_argument(
        "--cpu-canary-child",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--canary-result",
        type=Path,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--raw-output",
        type=Path,
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--max-new-tokens", type=int, default=512)
    parser.add_argument("--proxy", default="https://proxy.example.invalid:3128")
    parser.add_argument("--endpoint", default="https://hf-mirror.com")
    parser.add_argument("--max-time", type=int, default=7200)
    arguments = parser.parse_args()
    root = arguments.repo_root.resolve()
    if arguments.cpu_canary_child:
        if arguments.canary_result is None or arguments.raw_output is None:
            raise AcquisitionError("CANARY_CHILD_OUTPUT_PATHS_REQUIRED")
        return _canary_child(
            root,
            arguments.canary_result,
            arguments.raw_output,
            max_new_tokens=arguments.max_new_tokens,
        )
    operations = sum(
        bool(value)
        for value in (
            arguments.preflight,
            arguments.execute,
            arguments.validate_existing,
            arguments.cpu_canary,
        )
    )
    if operations > 1:
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
        plan = load_json(root / PLAN)
        validate_plan(plan)
        validate_snapshot(plan, root / plan["model"]["snapshot_dir"])
        validate_current_metadata(
            plan,
            root / plan["model"]["metadata_dir"],
        )
        print("QWEN25_OMNI7B_SNAPSHOT_VALID")
        return 0
    if arguments.cpu_canary:
        plan = load_json(root / PLAN)
        validate_plan(plan)
        validate_snapshot(plan, root / plan["model"]["snapshot_dir"])
        validate_current_metadata(
            plan,
            root / plan["model"]["metadata_dir"],
        )
        canary = run_bounded_cpu_canary(
            root,
            timeout_seconds=plan["runtime_smoke"]["timeout_seconds"],
            rss_limit_bytes=plan["runtime_smoke"]["rss_limit_bytes"],
            max_new_tokens=arguments.max_new_tokens,
        )
        manifest = run_preflight(root)
        print(manifest["decision"])
        return 0 if str(canary.get("status", "")).startswith(
            "TECHNICAL_READY_"
        ) else 2
    result = run_preflight(root)
    print(result["decision"])
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
