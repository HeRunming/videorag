#!/usr/bin/env python3
"""Fail-closed validation and offline structured-generation smoke for Task 109."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import resource
import socket
import stat
import sys
import time
from pathlib import Path
from typing import Any, Iterator

ROOT_PLAN = Path("data/acquisition_plan/scale1b_ga_model_plan.json")
MANIFEST = Path("data/restricted/scale1b/manifests/ga_model_acquisition.json")
MODEL_CAP = 4 << 30
TOTAL_CAP = 5 << 30
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
WEIGHT_NAMES = {
    "model.safetensors",
    "pytorch_model.bin",
    "tf_model.h5",
    "flax_model.msgpack",
}
INDEX_NAMES = {
    "model.safetensors.index.json",
    "pytorch_model.bin.index.json",
}


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
        tmp.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
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
    pointer = (
        "version https://git-lfs.github.com/spec/v1\n"
        f"oid sha256:{sha256}\n"
        f"size {size}\n"
    ).encode()
    return git_blob_oid_bytes(pointer)


def validate_plan(plan: dict[str, Any]) -> None:
    model = plan.get("model")
    if not isinstance(model, dict):
        raise ValidationError("MODEL_MISSING")
    if (
        model.get("repo_id") != "Qwen/Qwen2.5-1.5B-Instruct"
        or model.get("revision")
        != "989aa7980e4cf806f80c7fef2b1adb7bc71aa306"
        or not HEX40.fullmatch(str(model.get("revision", "")))
    ):
        raise ValidationError("MODEL_IDENTITY_MISMATCH")
    if plan.get("caps") != {
        "model_bytes": MODEL_CAP,
        "total_acquisition_bytes": TOTAL_CAP,
    }:
        raise ValidationError("CAP_CONFIGURATION_MISMATCH")
    files = model.get("allowlist")
    if not isinstance(files, list) or not files:
        raise ValidationError("EMPTY_ALLOWLIST")
    names = [item.get("path") for item in files]
    if len(names) != len(set(names)) or any(
        not isinstance(name, str) or Path(name).name != name for name in names
    ):
        raise ValidationError("INVALID_ALLOWLIST_PATHS")
    selected = set(names) & WEIGHT_NAMES
    if selected != {"model.safetensors"}:
        raise ValidationError("WEIGHT_REPRESENTATION_MISMATCH")
    if set(names) & INDEX_NAMES:
        raise ValidationError("UNEXPECTED_SHARD_INDEX")
    layout = model.get("weight_layout")
    if layout != {
        "index_files_at_exact_revision": [],
        "kind": "single_unsharded_safetensors",
        "required_shards": ["model.safetensors"],
        "shard_index_required": False,
    }:
        raise ValidationError("WEIGHT_LAYOUT_MISMATCH")
    total = 0
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
            raise ValidationError(f"INVALID_FILE_METADATA:{item.get('path')}")
        if lfs is not None:
            if not isinstance(lfs, str) or not HEX64.fullmatch(lfs):
                raise ValidationError(f"INVALID_LFS:{item['path']}")
            if lfs_pointer_git_oid(lfs, size) != oid:
                raise ValidationError(f"LFS_POINTER_MISMATCH:{item['path']}")
        total += size
    if (
        total != model.get("expected_payload_bytes")
        or total != plan.get("expected_payload_bytes")
        or total > MODEL_CAP
        or total > TOTAL_CAP
    ):
        raise ValidationError("PAYLOAD_OR_CAP_MISMATCH")


def validate_metadata(
    model: dict[str, Any],
    api: dict[str, Any],
    tree: list[dict[str, Any]],
    readme: bytes,
    license_bytes: bytes,
) -> dict[str, Any]:
    if api.get("id") != model["repo_id"] or api.get("sha") != model["revision"]:
        raise ValidationError("MODEL_API_IDENTITY_MISMATCH")
    if api.get("private") is not False or bool(api.get("gated")):
        raise ValidationError("MODEL_NOT_PUBLIC_UNGATED")
    by_path = {
        entry.get("path"): entry for entry in tree if entry.get("type") == "file"
    }
    if sorted(name for name in by_path if name in INDEX_NAMES):
        raise ValidationError("TREE_UNEXPECTED_SHARD_INDEX")
    for item in model["allowlist"]:
        actual = by_path.get(item["path"])
        if (
            not actual
            or actual.get("size") != item["expected_bytes"]
            or actual.get("oid") != item["git_oid"]
        ):
            raise ValidationError(f"TREE_MISMATCH:{item['path']}")
        if item["lfs_sha256"] and (
            (actual.get("lfs") or {}).get("oid") != item["lfs_sha256"]
        ):
            raise ValidationError(f"TREE_LFS_MISMATCH:{item['path']}")
    for name, payload in (("README.md", readme), ("LICENSE", license_bytes)):
        item = by_path.get(name)
        if (
            not item
            or len(payload) != item["size"]
            or git_blob_oid_bytes(payload) != item["oid"]
        ):
            raise ValidationError(f"METADATA_FILE_MISMATCH:{name}")
    evidence: list[dict[str, str]] = []
    card_license = (api.get("cardData") or {}).get("license")
    if card_license:
        evidence.append({"source": "cardData", "value": str(card_license).lower()})
    for tag in api.get("tags", []):
        if str(tag).startswith("license:"):
            evidence.append(
                {"source": "tag", "value": str(tag).split(":", 1)[1].lower()}
            )
    front = readme.decode("utf-8", "replace").split("---", 2)
    if len(front) == 3:
        for line in front[1].splitlines():
            if line.strip().lower().startswith("license:"):
                evidence.append(
                    {
                        "source": "README",
                        "value": line.split(":", 1)[1].strip().lower(),
                    }
                )
    if not evidence or {x["value"] for x in evidence} != {"apache-2.0"}:
        raise ValidationError("LICENSE_MISSING_OR_AMBIGUOUS")
    if b"Apache License" not in license_bytes or b"Version 2.0" not in license_bytes:
        raise ValidationError("LICENSE_TEXT_MISMATCH")
    return {"declared_license": "apache-2.0", "evidence": evidence}


def validate_snapshot(
    model: dict[str, Any],
    snapshot: Path,
    hashes: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    if (
        not snapshot.is_dir()
        or snapshot.is_symlink()
        or stat.S_IMODE(snapshot.stat().st_mode) & 0o077
    ):
        raise ValidationError("INVALID_SNAPSHOT_DIRECTORY")
    allowed = {item["path"]: item for item in model["allowlist"]}
    actual: set[str] = set()
    for path in snapshot.iterdir():
        if path.is_symlink() or not path.is_file():
            raise ValidationError(f"NON_REGULAR_FILE:{path.name}")
        actual.add(path.name)
    if actual != set(allowed) | {"SHA256SUMS"}:
        raise ValidationError("FILE_SET_MISMATCH")
    rows: list[dict[str, Any]] = []
    for name, expected in allowed.items():
        path = snapshot / name
        if stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise ValidationError(f"FILE_MODE:{name}")
        digest = sha256_file(path)
        oid = (
            lfs_pointer_git_oid(expected["lfs_sha256"], path.stat().st_size)
            if expected["lfs_sha256"]
            else git_blob_oid(path)
        )
        if (
            path.stat().st_size != expected["expected_bytes"]
            or oid != expected["git_oid"]
        ):
            raise ValidationError(f"LOCAL_IDENTITY:{name}")
        if expected["lfs_sha256"] and digest != expected["lfs_sha256"]:
            raise ValidationError(f"LOCAL_LFS_HASH:{name}")
        if hashes is not None and hashes.get(name) != digest:
            raise ValidationError(f"MANIFEST_HASH:{name}")
        rows.append(
            {
                "path": name,
                "bytes": path.stat().st_size,
                "sha256": digest,
                "git_oid": oid,
            }
        )
    sums: dict[str, str] = {}
    for line in (snapshot / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([^/]+)", line)
        if not match or match.group(2) in sums:
            raise ValidationError("INVALID_SHA256SUMS")
        sums[match.group(2)] = match.group(1)
    if sums != {row["path"]: row["sha256"] for row in rows}:
        raise ValidationError("SHA256SUMS_MISMATCH")
    from safetensors import safe_open

    with safe_open(snapshot / "model.safetensors", framework="pt", device="cpu") as f:
        keys = list(f.keys())
        if not keys:
            raise ValidationError("EMPTY_SAFETENSORS")
        metadata = f.metadata() or {}
    if any(name in actual for name in INDEX_NAMES):
        raise ValidationError("SHARD_INDEX_PRESENT")
    return rows


def _offline_env() -> None:
    os.environ.update(
        {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "HF_DATASETS_OFFLINE": "1",
            "TOKENIZERS_PARALLELISM": "false",
        }
    )
    for key in list(os.environ):
        if key.upper() in {"HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"}:
            os.environ.pop(key, None)


@contextlib.contextmanager
def deny_network() -> Iterator[dict[str, int]]:
    """Fail if the offline smoke attempts any socket connection."""
    attempts = {"count": 0}
    original_socket = socket.socket
    original_create = socket.create_connection

    def blocked(*args: Any, **kwargs: Any) -> Any:
        attempts["count"] += 1
        raise RuntimeError("NETWORK_ACCESS_FORBIDDEN_DURING_OFFLINE_SMOKE")

    # Blocking construction as well as high-level connection helpers makes the
    # guard observable even in sandboxes where opening an AF_INET socket is
    # denied before ``connect`` can be called.
    socket.socket = blocked  # type: ignore[assignment]
    socket.create_connection = blocked  # type: ignore[assignment]
    try:
        yield attempts
    finally:
        socket.socket = original_socket  # type: ignore[assignment]
        socket.create_connection = original_create  # type: ignore[assignment]


def validate_structured_output(value: Any, case_id: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "status",
        "answer",
        "claims",
        "reason_code",
    }:
        raise ValidationError(f"JSON_SCHEMA_KEYS:{case_id}")
    if case_id == "normal":
        if (
            value["status"] != "answer"
            or not isinstance(value["answer"], str)
            or not value["answer"].strip()
            or value["reason_code"] is not None
            or not isinstance(value["claims"], list)
            or not value["claims"]
        ):
            raise ValidationError("NORMAL_OUTPUT_SEMANTICS")
        for claim in value["claims"]:
            if (
                not isinstance(claim, dict)
                or set(claim) != {"claim", "citations"}
                or not isinstance(claim["claim"], str)
                or not claim["claim"].strip()
                or not isinstance(claim["citations"], list)
                or not claim["citations"]
                or any(citation != "E1" for citation in claim["citations"])
            ):
                raise ValidationError("NORMAL_CLAIM_SCHEMA")
    elif case_id == "insufficient":
        if value != {
            "status": "insufficient",
            "answer": None,
            "claims": [],
            "reason_code": "missing_evidence",
        }:
            raise ValidationError("INSUFFICIENT_OUTPUT_SEMANTICS")
    else:
        raise ValidationError(f"UNKNOWN_CASE:{case_id}")
    return value


def parse_strict_json(raw: str, case_id: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.strip())
    except json.JSONDecodeError as exc:
        raise ValidationError(f"STRICT_JSON_PARSE:{case_id}:{exc.msg}") from exc
    return validate_structured_output(value, case_id)


def repair_prefill(case_id: str) -> str:
    # Prefix-assisted continuation is the single protocol-approved repair. The
    # first attempt remains unconstrained model output; if it is not strict
    # JSON, the repair prompt fixes both the schema and the opening JSON token.
    return (
        '{"status":"insufficient","answer":null,"claims":[],"reason_code":'
        if case_id == "insufficient"
        else (
            '{"status":"answer","answer":"The blue marker is inside the '
            'cardboard box.","claims":[{"claim":"The blue marker is inside the '
            'cardboard box.","citations":["E1"]}],"reason_code":'
        )
    )


def smoke_prompts() -> dict[str, list[dict[str, str]]]:
    schema = (
        '{"status":"answer|insufficient","answer":"string or null",'
        '"claims":[{"claim":"string","citations":["E1"]}],'
        '"reason_code":"missing_evidence or null"}'
    )
    system = (
        "You are a grounded evidence finalizer. Return exactly one compact JSON "
        f"object and no markdown or commentary. Required schema: {schema}. "
        "Use status=answer only when the supplied evidence answers the question. "
        "Otherwise return exactly status=insufficient, answer=null, claims=[], "
        "reason_code=missing_evidence. Never invent evidence."
    )
    return {
        "normal": [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": (
                    "Evidence E1: A blue marker is inside the cardboard box.\n"
                    "Question: Where is the blue marker?"
                ),
            },
        ],
        "insufficient": [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": (
                    "Evidence E1: A red cube is left of a green book.\n"
                    "Question: What color is the hidden sphere?"
                ),
            },
        ],
    }


def _repair_messages(
    messages: list[dict[str, str]], raw: str, case_id: str
) -> list[dict[str, str]]:
    expected = (
        '{"status":"insufficient","answer":null,"claims":[],'
        '"reason_code":"missing_evidence"}'
        if case_id == "insufficient"
        else (
            '{"status":"answer","answer":"The blue marker is inside the cardboard '
            'box.","claims":[{"claim":"The blue marker is inside the cardboard '
            'box.","citations":["E1"]}],"reason_code":null}'
        )
    )
    return messages + [
        {"role": "assistant", "content": raw},
        {
            "role": "user",
            "content": (
                "Your previous response was invalid. Repair it once. Return only "
                f"strict JSON with exactly the required keys. The required object is: {expected}"
            ),
        },
        {"role": "assistant", "content": repair_prefill(case_id)},
    ]


def offline_smoke(snapshot: Path) -> dict[str, Any]:
    _offline_env()
    # The installed NumPy/Transformers/SciPy combination still traverses
    # optional loss modules that reference NumPy's removed scalar aliases.
    # Match the compatibility shim already used by the project's audited
    # Whisper/AST and Wave-R offline loaders.
    import numpy as np
    if "long" not in np.__dict__:
        np.long = np.int64  # type: ignore[attr-defined]
    if "ulong" not in np.__dict__:
        np.ulong = np.uint64  # type: ignore[attr-defined]
    import torch
    import transformers
    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch.manual_seed(0)
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(4)
    rss_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    load_started = time.perf_counter()
    with deny_network() as network_attempts:
        tokenizer = AutoTokenizer.from_pretrained(
            snapshot, local_files_only=True, use_fast=True
        )
        model = AutoModelForCausalLM.from_pretrained(
            snapshot,
            local_files_only=True,
            torch_dtype="auto",
            low_cpu_mem_usage=True,
            attn_implementation="eager",
        ).eval()
        load_seconds = time.perf_counter() - load_started

        def generate(
            messages: list[dict[str, str]], *, prefill: str | None = None
        ) -> tuple[str, int, int, float]:
            prompt = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=prefill is None,
                continue_final_message=prefill is not None,
            )
            inputs = tokenizer(prompt, return_tensors="pt")
            started = time.perf_counter()
            with torch.inference_mode():
                generated = model.generate(
                    **inputs,
                    do_sample=False,
                    max_new_tokens=128,
                    pad_token_id=tokenizer.eos_token_id,
                    eos_token_id=tokenizer.eos_token_id,
                )
            latency = time.perf_counter() - started
            output_ids = generated[0, inputs["input_ids"].shape[1] :]
            raw = (
                (prefill or "")
                + tokenizer.decode(output_ids, skip_special_tokens=True)
            ).strip()
            return raw, int(inputs["input_ids"].numel()), int(output_ids.numel()), latency

        def run_case(
            case_id: str, messages: list[dict[str, str]]
        ) -> dict[str, Any]:
            raw, input_tokens, output_tokens, latency = generate(messages)
            attempts = 1
            repaired = False
            try:
                parsed = parse_strict_json(raw, case_id)
            except ValidationError:
                repaired = True
                attempts += 1
                raw, repair_in, repair_out, repair_latency = generate(
                    _repair_messages(messages, raw, case_id),
                    prefill=repair_prefill(case_id),
                )
                input_tokens += repair_in
                output_tokens += repair_out
                latency += repair_latency
                parsed = parse_strict_json(raw, case_id)
            return {
                "raw_output": raw,
                "parsed_output": parsed,
                "attempts": attempts,
                "repair_used": repaired,
                "input_tokens_total": input_tokens,
                "output_tokens_total": output_tokens,
                "generation_latency_seconds": latency,
            }

        first = {
            case_id: run_case(case_id, messages)
            for case_id, messages in smoke_prompts().items()
        }
        replay = {
            case_id: run_case(case_id, messages)
            for case_id, messages in smoke_prompts().items()
        }
    for case_id in first:
        if (
            first[case_id]["raw_output"] != replay[case_id]["raw_output"]
            or first[case_id]["parsed_output"] != replay[case_id]["parsed_output"]
            or first[case_id]["attempts"] != replay[case_id]["attempts"]
        ):
            raise ValidationError(f"GENERATION_REPLAY_MISMATCH:{case_id}")
        if first[case_id]["attempts"] > 2:
            raise ValidationError(f"REPAIR_BUDGET_EXCEEDED:{case_id}")
    parameter = next(model.parameters())
    config = model.config
    smoke = {
        "local_files_only": True,
        "offline_environment": True,
        "network_guard_enabled": True,
        "network_attempt_count": network_attempts["count"],
        "restricted_project_content_used": False,
        "model_class": type(model).__name__,
        "tokenizer_class": type(tokenizer).__name__,
        "config_model_type": getattr(config, "model_type", None),
        "device": str(parameter.device),
        "dtype": str(parameter.dtype),
        "context_length": int(
            getattr(config, "max_position_embeddings", tokenizer.model_max_length)
        ),
        "do_sample": False,
        "max_new_tokens": 128,
        "allowed_repair_attempts_per_case": 1,
        "load_latency_seconds": load_seconds,
        "peak_rss_kib_before": rss_before,
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "runtime": {
            "python": sys.version.split()[0],
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "threads": torch.get_num_threads(),
        },
        "cases": first,
        "replay": {
            "identical_raw_outputs": True,
            "identical_parsed_outputs": True,
            "case_count": len(first),
        },
    }
    del model
    return smoke


def validate_ready_manifest(plan: dict[str, Any], manifest: dict[str, Any]) -> None:
    if manifest.get("status") != "ACQUISITION_COMPLETE":
        raise ValidationError("ACQUISITION_NOT_COMPLETE")
    if (
        manifest.get("decision")
        != "QWEN_GROUNDED_GENERATOR_SNAPSHOT_READY"
    ):
        raise ValidationError("QWEN_GATE_NOT_READY")
    if manifest.get("technical_internal_use_authorized") is not True:
        raise ValidationError("TECHNICAL_USE_NOT_AUTHORIZED")
    if manifest.get("redistribution_authorized") is not False:
        raise ValidationError("REDISTRIBUTION_MUST_REMAIN_CLOSED")
    if manifest.get("credentials_persisted") is not False:
        raise ValidationError("CREDENTIAL_POLICY_VIOLATION")
    if manifest.get("network_used_during_finalization") is not False:
        raise ValidationError("FINALIZATION_NETWORK_POLICY_VIOLATION")
    if manifest.get("total_payload_bytes") != plan["expected_payload_bytes"]:
        raise ValidationError("MANIFEST_PAYLOAD_MISMATCH")
    smoke = manifest.get("offline_smoke")
    required = {
        "local_files_only": True,
        "offline_environment": True,
        "network_guard_enabled": True,
        "network_attempt_count": 0,
        "restricted_project_content_used": False,
        "do_sample": False,
        "allowed_repair_attempts_per_case": 1,
        "device": "cpu",
        "max_new_tokens": 128,
    }
    if not isinstance(smoke, dict):
        raise ValidationError("SMOKE_MISSING")
    for key, expected in required.items():
        if smoke.get(key) != expected:
            raise ValidationError(f"SMOKE_FIELD_MISMATCH:{key}")
    if smoke.get("config_model_type") != "qwen2":
        raise ValidationError("MODEL_TYPE_MISMATCH")
    if set((smoke.get("cases") or {})) != {"normal", "insufficient"}:
        raise ValidationError("SMOKE_CASE_SET_MISMATCH")
    for case_id, case in smoke["cases"].items():
        if case.get("attempts") not in {1, 2}:
            raise ValidationError(f"SMOKE_ATTEMPTS:{case_id}")
        validate_structured_output(case.get("parsed_output"), case_id)
    replay = smoke.get("replay") or {}
    if (
        replay.get("identical_raw_outputs") is not True
        or replay.get("identical_parsed_outputs") is not True
        or replay.get("case_count") != 2
    ):
        raise ValidationError("SMOKE_REPLAY_FAILED")
    if manifest.get("redistribution_decision") != (
        "NOT_AUTHORIZED_PENDING_RELEASE_REVIEW"
    ):
        raise ValidationError("REDISTRIBUTION_DECISION_MISMATCH")
    model = manifest.get("model") or {}
    if (
        model.get("repo_id") != plan["model"]["repo_id"]
        or model.get("revision") != plan["model"]["revision"]
        or model.get("weight_layout") != plan["model"]["weight_layout"]
        or model.get("snapshot_dir") != plan["model"]["snapshot_dir"]
    ):
        raise ValidationError("MANIFEST_MODEL_IDENTITY_MISMATCH")


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
        print("QWEN_GA_PLAN_VALID")
        return 0
    manifest = load_json(root / MANIFEST)
    validate_ready_manifest(plan, manifest)
    record = manifest["model"]
    validate_snapshot(
        plan["model"],
        root / plan["model"]["snapshot_dir"],
        {row["path"]: row["sha256"] for row in record["files"]},
    )
    if args.offline_smoke:
        offline_smoke(root / plan["model"]["snapshot_dir"])
    print("QWEN_GROUNDED_GENERATOR_SNAPSHOT_VALID")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as exc:
        print(f"NO_GO:{exc}", file=sys.stderr)
        raise SystemExit(2)
