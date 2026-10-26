"""Sealed public-packet execution without evaluator imports or scoring."""

from __future__ import annotations

import importlib.metadata
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .controller import (
    ControllerV2Config,
    execute_v1_case,
    execute_v2_case,
)
from .packet import (
    assert_path_is_not_forbidden,
    load_implementation_attestation,
    load_public_packet,
    seal_output_files,
    sha256_file,
    verify_contract_inputs,
    verify_model_snapshot,
    write_json,
    write_jsonl,
)
from .process import ConstrainedQwenProcess, ProcessConfig

PAIRED_ARM = "paired"
SINGLE_ARMS = {"v1", "v2"}
ALL_ARMS = {*SINGLE_ARMS, PAIRED_ARM}


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _without_calls(result: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in result.items() if key != "model_calls"}


def _append_case_artifacts(
    *,
    case: dict[str, Any],
    arm: str,
    result: dict[str, Any],
    results: list[dict[str, Any]],
    calls: list[dict[str, Any]],
    call_model_identity: dict[str, Any],
) -> None:
    for call in result["model_calls"]:
        calls.append(
            {
                "case_id": case["case_id"],
                "arm": arm,
                "model_identity": call_model_identity,
                **dict(call),
            }
        )
    results.append(_without_calls(result))


def _run_case(
    *,
    arm: str,
    model: ConstrainedQwenProcess,
    case: dict[str, Any],
    action_schema: Path,
    state_schema: Path,
    controller_config: ControllerV2Config,
) -> dict[str, Any]:
    if arm == "v2":
        return execute_v2_case(
            model,
            case,
            action_schema_path=action_schema,
            state_schema_path=state_schema,
            config=controller_config,
        )
    return execute_v1_case(
        model,
        case,
        config=controller_config,
    )


def _runtime_contract_matches(model_metadata: dict[str, Any]) -> bool:
    return (
        model_metadata.get("offline") is True
        and model_metadata.get("local_files_only") is True
        and model_metadata.get("network_namespace_denied") is True
        and model_metadata.get("device") == "cpu"
        and model_metadata.get("dtype") == "torch.bfloat16"
        and model_metadata.get("constraint_engine") == "xgrammar"
    )


def _verify_task111_hashes(
    *,
    repo_root: Path,
    expected_hashes: dict[str, str],
) -> dict[str, str]:
    verified: dict[str, str] = {}
    for relative, expected in expected_hashes.items():
        path = repo_root / relative
        assert_path_is_not_forbidden(repo_root=repo_root, path=path)
        actual = sha256_file(path)
        if actual != expected:
            raise RuntimeError(f"TASK111_ARTIFACT_HASH_MISMATCH:{relative}")
        verified[relative] = actual
    return verified


def run_public_packet(
    *,
    repo_root: Path,
    arm: str,
    public_packet_path: Path,
    model_snapshot: Path,
    output_dir: Path,
    implementation_attestation_path: Path,
    startup_timeout_s: float = 240.0,
    generation_timeout_s: float = 180.0,
    threads: int = 8,
) -> dict[str, Any]:
    """Execute and seal public arms; this function never loads evaluator labels.

    ``arm="paired"`` is the only confirmatory mode. It reuses exactly one model
    process and executes v1 then v2 for each case before advancing.
    """

    if arm not in ALL_ARMS:
        raise ValueError("arm must be paired, v1, or v2")
    for path in (
        public_packet_path,
        model_snapshot,
        output_dir,
        implementation_attestation_path,
    ):
        assert_path_is_not_forbidden(repo_root=repo_root, path=path)
    attestation = load_implementation_attestation(
        implementation_attestation_path
    )
    contract_check = verify_contract_inputs(
        repo_root=repo_root,
        public_packet_path=public_packet_path,
    )
    task111_hashes = _verify_task111_hashes(
        repo_root=repo_root,
        expected_hashes=contract_check[
            "task111_protected_hashes_from_contract"
        ],
    )
    packet = load_public_packet(public_packet_path)
    model_identity = verify_model_snapshot(
        repo_root=repo_root,
        snapshot=model_snapshot,
    )
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError("output directory must be absent or empty")
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

    action_schema = repo_root / "docs/spec/controller_v2_action_schema.json"
    state_schema = repo_root / "docs/spec/controller_v2_state_schema.json"
    process_config = ProcessConfig(
        startup_timeout_s=startup_timeout_s,
        generation_timeout_s=generation_timeout_s,
        threads=threads,
        max_context_tokens=int(
            contract_check["contract"]["model_and_runtime"][
                "context_limit_tokens"
            ]
        ),
        deny_network_namespace=True,
    )
    controller_config = ControllerV2Config(
        action_max_new_tokens=int(
            contract_check["contract"]["model_and_runtime"][
                "action_max_new_tokens"
            ]
        ),
        state_max_new_tokens=int(
            contract_check["contract"]["model_and_runtime"][
                "state_max_new_tokens"
            ]
        ),
        finalizer_max_new_tokens=int(
            contract_check["contract"]["model_and_runtime"][
                "finalizer_max_new_tokens"
            ]
        ),
    )
    results_by_arm: dict[str, list[dict[str, Any]]] = {
        selected_arm: []
        for selected_arm in (
            ("v1", "v2") if arm == PAIRED_ARM else (arm,)
        )
    }
    calls_by_arm: dict[str, list[dict[str, Any]]] = {
        selected_arm: [] for selected_arm in results_by_arm
    }
    order_trace: list[dict[str, Any]] = []
    with ConstrainedQwenProcess(
        model_snapshot,
        config=process_config,
    ) as model:
        model_metadata = dict(model.metadata)
        if not _runtime_contract_matches(model_metadata):
            raise RuntimeError("MODEL_RUNTIME_CONTRACT_MISMATCH")
        call_model_identity = {
            "repo_id": model_identity["repo_id"],
            "revision": model_identity["revision"],
            "device": model_metadata["device"],
            "dtype": model_metadata["dtype"],
        }
        sequence = 0
        for case_index, case in enumerate(packet["cases"]):
            case_arms = ("v1", "v2") if arm == PAIRED_ARM else (arm,)
            for selected_arm in case_arms:
                result = _run_case(
                    arm=selected_arm,
                    model=model,
                    case=case,
                    action_schema=action_schema,
                    state_schema=state_schema,
                    controller_config=controller_config,
                )
                _append_case_artifacts(
                    case=case,
                    arm=selected_arm,
                    result=result,
                    results=results_by_arm[selected_arm],
                    calls=calls_by_arm[selected_arm],
                    call_model_identity=call_model_identity,
                )
                order_trace.append(
                    {
                        "sequence": sequence,
                        "case_index": case_index,
                        "case_id": case["case_id"],
                        "arm": selected_arm,
                    }
                )
                sequence += 1

    artifact_names: list[str] = []
    if arm == PAIRED_ARM:
        for selected_arm in ("v1", "v2"):
            results_name = f"{selected_arm}_results.jsonl"
            calls_name = f"{selected_arm}_calls.jsonl"
            write_jsonl(output_dir / results_name, results_by_arm[selected_arm])
            write_jsonl(output_dir / calls_name, calls_by_arm[selected_arm])
            artifact_names.extend([results_name, calls_name])
    else:
        write_jsonl(output_dir / "results.jsonl", results_by_arm[arm])
        write_jsonl(output_dir / "calls.jsonl", calls_by_arm[arm])
        artifact_names.extend(["results.jsonl", "calls.jsonl"])
    write_jsonl(output_dir / "order_trace.jsonl", order_trace)
    artifact_names.append("order_trace.jsonl")

    all_calls = [
        call
        for selected_arm in results_by_arm
        for call in calls_by_arm[selected_arm]
    ]
    constraint_runtime_failure = any(
        call.get("error_code") == "CONSTRAINT_RUNTIME_FAILURE"
        for call in all_calls
    )
    confirmatory = arm == PAIRED_ARM
    manifest = {
        "schema_version": "av-trace.controller-v2-execution-manifest/2.0",
        "created_at": datetime.now(UTC).isoformat(),
        "arm": arm,
        "execution_mode": (
            "confirmatory_paired" if confirmatory else "non_confirmatory_single_arm"
        ),
        "confirmatory": confirmatory,
        "paired_protocol": {
            "required_for_confirmation": True,
            "enabled": confirmatory,
            "arm_order_within_each_case": (
                ["v1", "v2"] if confirmatory else [arm]
            ),
            "one_shared_model_process": True,
            "model_process_count": 1,
            "separate_arm_artifacts": confirmatory,
            "order_trace": "order_trace.jsonl",
        },
        "packet_id": packet["packet_id"],
        "case_count": len(packet["cases"]),
        "case_order": [case["case_id"] for case in packet["cases"]],
        "correctness_scored": False,
        "evaluator_labels_loaded": False,
        "restricted_evaluator_key_accessed": False,
        "execution_status": (
            "NO_GO_CONSTRAINT_RUNTIME_FAILURE"
            if constraint_runtime_failure
            else (
                "SEALED_UNSCORED_PAIRED"
                if confirmatory
                else "SEALED_UNSCORED_NON_CONFIRMATORY"
            )
        ),
        "implementation_attestation": {
            "sha256": sha256_file(implementation_attestation_path),
            "implementation_worker": attestation["implementation_worker"],
            "attested_at": attestation["attested_at"],
            "forbidden_evaluator_key_not_accessed": True,
            "holdout_not_executed_during_implementation": True,
            "no_expected_outputs_or_labels_inspected": True,
        },
        "input_commitments": {
            "public_packet_sha256": sha256_file(public_packet_path),
            "contract_hash": contract_check["contract_hash"],
            "contract_file_sha256": contract_check["contract_file_sha256"],
            "checked_artifacts": contract_check["checked_artifacts"],
            "task111_protected_artifacts_accessed_for_hash_verification": True,
            "task111_protected_hashes_verified": task111_hashes,
            "restricted_evaluator_key_checked": False,
        },
        "model_identity": model_identity,
        "runtime": {
            "python": sys.version,
            "platform": platform.platform(),
            "threads": threads,
            "network_namespace_denied": True,
            "offline_environment": True,
            "model_worker": model_metadata,
            "packages": {
                "torch": _package_version("torch"),
                "transformers": _package_version("transformers"),
                "xgrammar": _package_version("xgrammar"),
                "lm-format-enforcer": _package_version("lm-format-enforcer"),
            },
        },
        "persisted_content_policy": {
            "raw_model_output": True,
            "request_hashes": True,
            "grammar_hashes": True,
            "token_counts": True,
            "latency": True,
            "rss": True,
            "full_system_prompt": False,
            "full_request_payload": False,
        },
    }
    write_json(output_dir / "execution_manifest.json", manifest)
    artifact_names.append("execution_manifest.json")
    seal = seal_output_files(
        output_dir,
        names=artifact_names,
        input_commitments=manifest["input_commitments"],
    )
    return {
        "manifest": manifest,
        "seal": seal,
        "output_dir": str(output_dir),
    }
