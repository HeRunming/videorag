#!/usr/bin/env python3
"""Qwen3 adapter-v2 fictional holdout execution and evaluation harness.

The three externally callable phases are intentionally separated:

* ``--preflight`` authenticates the Task-182 freeze, immutable adapter and
  Qwen transport sources, exact local snapshot, runtime policy, and one-run
  state without loading evaluator-private labels or model weights.
* ``--execute`` claims the sole authorization, executes (or fail-closed
  resumes) all 51 public cases, and seals every raw attempt and submission
  artifact before private evaluation.
* ``--evaluate`` verifies that run seal before loading the private key and
  applying the frozen Gate-C evaluator.

The execution/evaluation mechanics deliberately reuse the already audited
Task-177 harness. Qwen-specific bindings, native transport, prompt rendering,
schemas, seals, authorization keys, and decision tokens are overridden here.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from av_trace_strong_baselines.contracts import (
    InferenceStatus,
    ModelBinding,
    sha256_json,
)
from av_trace_strong_baselines_v2 import (
    ADAPTER_SCHEMA_VERSION,
    action_choice_spec,
    build_native_action_plan,
    evidence_state_spec,
    finalizer_factor_specs,
)
from scripts import audit_qwen3_adapter_v2_holdout as freeze_audit
from tools import granite_adapter_v2_holdout as _base
from tools import qwen3_8b_acquisition as acquisition

# Historical note: the sole authorized run was claimed and sealed under this
# harness identifier before Task 185 performed the final audit/reporting pass.
# It must not be renumbered because that would invalidate the sealed bytes.
TASK_ID = 184
RUNNER_SCHEMA = "av-trace.qwen3-adapter-v2-holdout-runner/1.0"
SUBMISSION_SCHEMA = "av-trace.qwen3-adapter-v2-holdout-submission/1.0"
RUN_SEAL_SCHEMA = "av-trace.qwen3-adapter-v2-holdout-run-seal/1.0"
EVALUATOR_SCHEMA = "av-trace.qwen3-adapter-v2-gate-c-report/1.0"
EVALUATION_SEAL_SCHEMA = (
    "av-trace.qwen3-adapter-v2-holdout-evaluation-seal/1.0"
)

HOLDOUT_DIR = Path("data/restricted/strong_baselines/qwen3_v2_holdout")
OUTPUT_DIR = Path(
    "data/restricted/strong_baselines/qwen3_v2_holdout_run"
)
SNAPSHOT = Path(
    "data/restricted/strong_baselines/models/"
    "Qwen--Qwen3-8B--b968826d9c46"
)
ACQUISITION_MANIFEST = Path(
    "data/restricted/strong_baselines/manifests/qwen3_8b_acquisition.json"
)
SMOKE_REPORT = Path(
    "data/restricted/strong_baselines/acquisition_records/"
    "qwen3-8b-b968826d9c46/cpu_load_smoke.json"
)

SUITE_ID = "qwen3-v2-fictional-holdout-20261008"
FREEZE_LABEL = "QWEN3_ADAPTER_V2_HOLDOUT_2026-10-08"
MODEL_REPO_ID = "Qwen/Qwen3-8B"
MODEL_REVISION = "b968826d9c46dd6066d109eabc6255188de91218"
THREADS = 8
MAX_NEW_TOKENS = 512
CONTEXT_CAP = 32_768
ADDRESS_SPACE_LIMIT_BYTES = 48 * 1024**3
WHOLE_RUN_TIMEOUT_SECONDS = 12 * 60 * 60

EXPECTED_COUNTS = {
    "controller": 24,
    "finalizer": 16,
    "runtime_failure": 11,
}
SEALED_RUN_FILES = (
    "authorization_claim.json",
    "preflight_report.json",
    "submission.json",
    "raw_attempts.jsonl",
    "run_metadata.json",
    "runner_manifest.json",
)
FROZEN_IMPLEMENTATION_HASHES = {
    "src/av_trace_strong_baselines_v2/qwen3_suite_generator.py": (
        "b463c9185ed0e16fea28b2464f8a5f8d89da4b2bd5e21435122e50cdebddfb39"
    ),
    "src/av_trace_strong_baselines_v2/adapter.py": (
        "13e1b49881672eac6125235c524e969543a337e3e100e163a7f7f5e696fea4e1"
    ),
    "src/av_trace_strong_baselines_v2/contracts.py": (
        "535b1e25aa63237cb0402fcc0f797e5e222c5637a318c2c27d08669fff1b79f1"
    ),
    "scripts/generate_qwen3_adapter_v2_suite.py": (
        "8b4f939f125a7dfefa2e167fe39116c610ee9e44a80dcd1c92639c76b7d75452"
    ),
    "scripts/audit_qwen3_adapter_v2_holdout.py": (
        "00918387b52b4b35b892abf5a51ad955d8020f2b00fdad909aa6e1f0505d1e9d"
    ),
    "tools/qwen3_8b_acquisition.py": (
        "dbe5135010498dfd2df0d16c6091d93d731b8cba94451aeafdfb3ef552fbcb7e"
    ),
}

HoldoutRunError = _base.HoldoutRunError
utc_now = _base.utc_now
_load_json = _base._load_json
_load_jsonl = _base._load_jsonl
_sha256_file = _base._sha256_file
_sha256_bytes = _base._sha256_bytes
_atomic_json = _base._atomic_json
_atomic_jsonl = _base._atomic_jsonl
_binding = _base._binding
_offline_environment = _base._offline_environment
_network_denial = _base._network_denial
_jsonable = _base._jsonable
_claim_handles = _base._claim_handles
_factor_key = _base._factor_key
_factor_messages = _base._factor_messages
_attempt_objects = _base._attempt_objects
_factor_outcome_for_records = _base._factor_outcome_for_records
_parse_action_for_runner = _base._parse_action_for_runner
_parse_state_for_runner = _base._parse_state_for_runner
_finalizer_validators_for_runner = _base._finalizer_validators_for_runner
_factor_names = _base._factor_names
_exception_status = _base._exception_status
_records_for_factor = _base._records_for_factor
_complete_factor = _base._complete_factor
_outcome_summary = _base._outcome_summary
_assemble_substantive_result = _base._assemble_substantive_result
_runtime_fixture = _base._runtime_fixture
_resolve_interrupted_factor = _base._resolve_interrupted_factor
_restoration_isolation_checks = _base._restoration_isolation_checks
_private_exposure = _base._private_exposure
_fraction = _base._fraction
_attempt_map = _base._attempt_map
_controller_replay = _base._controller_replay
_finalizer_replay = _base._finalizer_replay
_score_finalizer = _base._score_finalizer
_score_runtime = _base._score_runtime
_isolation_failures = _base._isolation_failures
_base_evaluate_payload = _base.evaluate_payload


def _preflight(
    root: Path,
    output_dir: Path,
    *,
    execution_mode: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Verify all frozen inputs without parsing evaluator-private labels."""

    restricted = root / HOLDOUT_DIR
    public_path = restricted / "public_suite.json"
    freeze_seal_path = restricted / "freeze_seal.json"
    freeze_manifest_path = restricted / "freeze_manifest.json"
    if not public_path.is_file():
        raise HoldoutRunError("FROZEN_HOLDOUT_NOT_FOUND")

    audit_report = freeze_audit.audit(restricted)
    if audit_report.get("status") != "PASS":
        raise HoldoutRunError("TASK182_INDEPENDENT_AUDIT_FAILED")

    public = _load_json(public_path)
    freeze_manifest = _load_json(freeze_manifest_path)
    freeze_seal = _load_json(freeze_seal_path)
    if (
        public.get("suite_id") != SUITE_ID
        or public.get("freeze_label") != FREEZE_LABEL
        or public.get("adapter_schema_version") != ADAPTER_SCHEMA_VERSION
        or public.get("adapter_profile")
        != "qwen3-native-transport-factorized-v2"
        or public.get("execution_status") != "SEALED_NOT_RUN"
    ):
        raise HoldoutRunError("FROZEN_SUITE_IDENTITY_MISMATCH")
    authorization = freeze_manifest.get("one_run_authorization")
    if authorization != {
        "authorization_state": "AUTHORIZED_EXACTLY_ONCE_AFTER_FREEZE",
        "development_or_smoke_subset_runs": 0,
        "execution_in_this_task": False,
        "maximum_full_suite_runs": 1,
        "model_inference_executed_during_freeze": False,
        "partial_model_runs": 0,
        "post_run_deterministic_evaluator_replays": 1,
        "pre_run_seal_environment_model_adapter_verification_required": True,
        "reruns_after_any_model_output": 0,
        "separate_execution_task_required": True,
    }:
        raise HoldoutRunError("ONE_RUN_AUTHORIZATION_MISMATCH")
    if freeze_seal.get("state") != "GOVERNANCE_FROZEN_NOT_RUN":
        raise HoldoutRunError("GOVERNANCE_FREEZE_STATE_MISMATCH")

    counts = Counter(str(case.get("case_type")) for case in public["cases"])
    if dict(counts) != EXPECTED_COUNTS:
        raise HoldoutRunError("HOLDOUT_CASE_COUNTS_MISMATCH")
    if public.get("content_boundary") != {
        "fictional_generated_primitives_only": True,
        "scientific_family_content": False,
        "real_source_content": False,
        "model_results_present": False,
        "private_labels_present": False,
    }:
        raise HoldoutRunError("HOLDOUT_CONTENT_BOUNDARY_MISMATCH")

    frozen_hashes: dict[str, str] = {}
    for relative, expected in FROZEN_IMPLEMENTATION_HASHES.items():
        observed = _sha256_file(root / relative)
        if observed != "sha256:" + expected:
            raise HoldoutRunError(
                f"FROZEN_IMPLEMENTATION_HASH_MISMATCH:{relative}"
            )
        frozen_hashes[relative] = observed

    binding = public["binding"]
    controller_binding = _binding(binding["controller"])
    finalizer_binding = _binding(binding["finalizer"])
    for expected in (controller_binding, finalizer_binding):
        if (
            expected.repo_id != MODEL_REPO_ID
            or expected.revision != MODEL_REVISION
            or expected.resolved_processor_revision != MODEL_REVISION
            or expected.resolved_tokenizer_revision != MODEL_REVISION
        ):
            raise HoldoutRunError("FROZEN_MODEL_BINDING_MISMATCH")
    if binding.get("same_exact_snapshot_required") is not True:
        raise HoldoutRunError("SAME_EXACT_SNAPSHOT_NOT_REQUIRED")

    acquisition_manifest = _load_json(root / ACQUISITION_MANIFEST)
    smoke = _load_json(root / SMOKE_REPORT)
    if acquisition_manifest.get("decision") != "QWEN3_8B_ACQUISITION_READY":
        raise HoldoutRunError("QWEN3_ACQUISITION_NOT_READY")
    if (
        smoke.get("status") != "LOAD_SMOKE_COMPLETE"
        or smoke.get("repo_id") != MODEL_REPO_ID
        or smoke.get("revision") != MODEL_REVISION
        or smoke.get("local_files_only") is not True
        or smoke.get("trust_remote_code") is not False
        or smoke.get("runtime", {}).get("threads") != THREADS
        or smoke.get("network_attempts") != 0
        or smoke.get("device") != "cpu"
        or smoke.get("dtype") != "torch.bfloat16"
        or smoke.get("config_model_type") != "qwen3"
    ):
        raise HoldoutRunError("QWEN3_SMOKE_CONTRACT_MISMATCH")
    plan = _load_json(root / acquisition.PLAN)
    acquisition.validate_plan(plan)
    snapshot = root / SNAPSHOT
    if (root / plan["model"]["snapshot_dir"]).resolve() != snapshot.resolve():
        raise HoldoutRunError("QWEN3_SNAPSHOT_PATH_MISMATCH")
    snapshot_rows = acquisition.validate_snapshot(plan, snapshot)

    run_state = "AVAILABLE"
    if output_dir.exists():
        if (output_dir / "seal.json").exists():
            run_state = "SEALED_DO_NOT_RESTART"
        elif (
            (output_dir / "authorization_claim.json").exists()
            and (output_dir / "progress.json").exists()
        ):
            run_state = "UNSEALED_RESUME_ONLY"
        elif any(output_dir.iterdir()):
            run_state = "AMBIGUOUS_EXISTING_ARTIFACTS"
        else:
            run_state = "EMPTY_EXISTING_DIRECTORY"
    if execution_mode and run_state not in {
        "AVAILABLE",
        "EMPTY_EXISTING_DIRECTORY",
        "UNSEALED_RESUME_ONLY",
    }:
        raise HoldoutRunError(f"ONE_RUN_NOT_EXECUTABLE:{run_state}")

    report = {
        "schema_version": "av-trace.qwen3-adapter-v2-preflight/1.0",
        "task_id": TASK_ID,
        "checked_at": utc_now(),
        "suite_id": SUITE_ID,
        "freeze_label": FREEZE_LABEL,
        "task182_audit_status": audit_report["status"],
        "freeze_seal_sha256": _sha256_file(freeze_seal_path),
        "freeze_manifest_sha256": _sha256_file(freeze_manifest_path),
        "public_suite_sha256": _sha256_file(public_path),
        "private_labels_sha256_verified_without_loading": _sha256_file(
            restricted / "private_labels.json"
        ),
        "one_run_authorization": authorization,
        "run_state": run_state,
        "frozen_implementation_hashes": frozen_hashes,
        "snapshot": {
            "path": str(SNAPSHOT),
            "validated_file_count": len(snapshot_rows),
            "local_manifest_sha256": _sha256_file(
                snapshot / "LOCAL_MANIFEST.json"
            ),
            "sha256s_sha256": _sha256_file(snapshot / "SHA256SUMS"),
        },
        "execution_policy": {
            "device": "cpu",
            "dtype": "torch.bfloat16",
            "threads": THREADS,
            "local_files_only": True,
            "trust_remote_code": False,
            "network": False,
            "gpu_or_api": False,
            "scientific_source": False,
            "enable_thinking": False,
            "decoding": "greedy",
            "native_tool_transport": "qwen_chat_template_tool_call",
            "maximum_schema_only_retries_per_factor": 1,
            "semantic_retries": 0,
            "cross_factor_retries": 0,
        },
        "status": "PASS",
    }
    return public, report


def _factor_spec(
    case: Mapping[str, Any],
    factor_name: str,
) -> tuple[Any, str]:
    handles = _claim_handles(case)
    if case["case_type"] == "controller":
        if factor_name == "action_choice":
            plan = build_native_action_plan(case["public_input"]["action_menu"])
            return action_choice_spec(plan), "qwen_native_tool_choice"
        if factor_name == "evidence_state":
            return evidence_state_spec(handles), "evidence_state_heads"
    if case["case_type"] == "finalizer":
        observations = case["public_input"]["observed_evidence"]
        specs = finalizer_factor_specs(
            claim_handles=handles,
            observation_ids=[
                str(item["observation_id"]) for item in observations
            ],
        )
        return specs[factor_name], specs[factor_name].role
    raise HoldoutRunError(f"FACTOR_SPEC_UNSUPPORTED:{factor_name}")


def _normalize_action_transport(raw: str) -> tuple[bytes, str]:
    """Use only the frozen Task-181 Qwen native-wrapper normalization."""

    return acquisition.normalize_action_transport(raw)


def _generate_factor_attempt(
    *,
    case: Mapping[str, Any],
    factor_name: str,
    prompt_policy: Mapping[str, Any],
    tokenizer: Any,
    model: Any,
    torch: Any,
    attempt_index: int,
    previous_raw: str | None,
    previous_error: str | None,
) -> dict[str, Any]:
    """Generate one immutable Qwen factor attempt under the frozen policy."""

    spec, role = _factor_spec(case, factor_name)
    messages = _factor_messages(
        case=case,
        factor_name=factor_name,
        role=role,
        schema=spec.output_schema,
        prompt_policy=prompt_policy,
        previous_raw=previous_raw,
        previous_error=previous_error,
    )
    tools = None
    if factor_name == "action_choice":
        tools = list(
            build_native_action_plan(case["public_input"]["action_menu"]).tools
        )
    rendered = tokenizer.apply_chat_template(
        messages,
        tools=tools,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )
    inputs = tokenizer(rendered, return_tensors="pt")
    prompt_tokens = int(inputs["input_ids"].numel())
    record: dict[str, Any] = {
        "attempt_id": f"{case['case_id']}::{factor_name}::{attempt_index}",
        "case_id": case["case_id"],
        "case_type": case["case_type"],
        "factor_name": factor_name,
        "attempt_index": attempt_index,
        "kind": "initial" if attempt_index == 1 else "schema_only_retry",
        "prompt_sha256": _sha256_bytes(rendered.encode("utf-8")),
        "public_case_sha256": sha256_json(
            {
                "case_type": case["case_type"],
                "public_input": case["public_input"],
            }
        ),
        "factor_schema_sha256": sha256_json(spec.output_schema),
        "prompt_tokens": prompt_tokens,
        "max_new_tokens": MAX_NEW_TOKENS,
        "transport": (
            "qwen_chat_template_tool_call"
            if factor_name == "action_choice"
            else "strict_constrained_json"
        ),
        "enable_thinking": False,
        "decoding": "greedy",
    }
    if prompt_tokens > CONTEXT_CAP:
        record.update(
            {
                "completion_tokens": None,
                "generation_seconds": 0.0,
                "raw_output": None,
                "raw_output_with_special_tokens": None,
                "raw_output_sha256": None,
                "raw_output_with_special_tokens_sha256": None,
                "adapter_input": None,
                "adapter_input_sha256": None,
                "transport_normalization": None,
                "inference_status": str(InferenceStatus.BUDGET_EXHAUSTED),
                "error_code": "CONTEXT_CAP_EXCEEDED",
            }
        )
        return record
    started = time.perf_counter()
    try:
        with torch.inference_mode():
            generated = model.generate(
                **inputs,
                do_sample=False,
                max_new_tokens=MAX_NEW_TOKENS,
                pad_token_id=tokenizer.eos_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )
        elapsed = time.perf_counter() - started
        output_ids = generated[0, inputs["input_ids"].shape[1] :]
        raw_with_specials = tokenizer.decode(
            output_ids,
            skip_special_tokens=False,
        )
        raw = tokenizer.decode(
            output_ids,
            skip_special_tokens=True,
        ).strip()
        if factor_name == "action_choice":
            adapter_bytes, normalization = _normalize_action_transport(raw)
        else:
            adapter_bytes = raw.encode("utf-8")
            normalization = "identity"
        record.update(
            {
                "completion_tokens": int(output_ids.numel()),
                "generation_seconds": elapsed,
                "raw_output": raw,
                "raw_output_with_special_tokens": raw_with_specials,
                "raw_output_sha256": _sha256_bytes(raw.encode("utf-8")),
                "raw_output_with_special_tokens_sha256": _sha256_bytes(
                    raw_with_specials.encode("utf-8")
                ),
                "adapter_input": adapter_bytes.decode("utf-8"),
                "adapter_input_sha256": _sha256_bytes(adapter_bytes),
                "transport_normalization": normalization,
                "inference_status": str(InferenceStatus.VALID),
                "error_code": None,
            }
        )
    except (MemoryError, OSError, RuntimeError, TimeoutError, ValueError) as exc:
        elapsed = time.perf_counter() - started
        record.update(
            {
                "completion_tokens": None,
                "generation_seconds": elapsed,
                "raw_output": None,
                "raw_output_with_special_tokens": None,
                "raw_output_sha256": None,
                "raw_output_with_special_tokens_sha256": None,
                "adapter_input": None,
                "adapter_input_sha256": None,
                "transport_normalization": None,
                "inference_status": str(_exception_status(exc)),
                "error_code": type(exc).__name__,
            }
        )
    return record


def _new_progress(
    public: Mapping[str, Any],
    preflight: Mapping[str, Any],
    controller_binding: ModelBinding,
    finalizer_binding: ModelBinding,
) -> dict[str, Any]:
    return {
        "schema_version": RUNNER_SCHEMA,
        "task_id": TASK_ID,
        "run_id": f"task184-{utc_now()}-{uuid.uuid4().hex[:12]}",
        "started_at": utc_now(),
        "suite_id": SUITE_ID,
        "public_suite_sha256": preflight["public_suite_sha256"],
        "freeze_seal_sha256": preflight["freeze_seal_sha256"],
        "runner_source_sha256": _sha256_file(Path(__file__)),
        "controller_binding": controller_binding.to_dict(),
        "finalizer_binding": finalizer_binding.to_dict(),
        "prompt_policy_sha256": public["prompt_policy"]["sha256"],
        "results": [],
        "attempts": [],
        "active_factor": None,
        "status": "RUNNING_UNSEALED",
    }


def _validate_progress(
    progress: Mapping[str, Any],
    public: Mapping[str, Any],
    preflight: Mapping[str, Any],
) -> None:
    if (
        progress.get("schema_version") != RUNNER_SCHEMA
        or progress.get("task_id") != TASK_ID
        or progress.get("suite_id") != SUITE_ID
        or progress.get("public_suite_sha256")
        != preflight["public_suite_sha256"]
        or progress.get("freeze_seal_sha256")
        != preflight["freeze_seal_sha256"]
        or progress.get("runner_source_sha256")
        != _sha256_file(Path(__file__))
        or progress.get("prompt_policy_sha256")
        != public["prompt_policy"]["sha256"]
    ):
        raise HoldoutRunError("UNSEALED_PROGRESS_CONTRACT_MISMATCH")
    expected_ids = {case["case_id"] for case in public["cases"]}
    result_ids = [row.get("case_id") for row in progress.get("results", [])]
    if len(result_ids) != len(set(result_ids)):
        raise HoldoutRunError("UNSEALED_PROGRESS_DUPLICATE_CASE")
    if not set(result_ids) <= expected_ids:
        raise HoldoutRunError("UNSEALED_PROGRESS_UNKNOWN_CASE")


def _authorization_claim(
    preflight: Mapping[str, Any],
    progress: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "av-trace.qwen3-v2-one-run-claim/1.0",
        "task_id": TASK_ID,
        "run_id": progress["run_id"],
        "claimed_at": progress["started_at"],
        "suite_id": SUITE_ID,
        "freeze_label": FREEZE_LABEL,
        "authorization": "AUTHORIZED_EXACTLY_ONCE_AFTER_FREEZE",
        "public_suite_sha256": preflight["public_suite_sha256"],
        "freeze_seal_sha256": preflight["freeze_seal_sha256"],
        "runner_source_sha256": progress["runner_source_sha256"],
        "reruns_after_any_model_output": 0,
        "resume_policy": (
            "persisted completed factors are never regenerated; an active "
            "unpersisted factor is recorded PROCESS_FAILURE and not retried"
        ),
    }


def _write_sealed_run(
    root: Path,
    output_dir: Path,
    public: Mapping[str, Any],
    progress: dict[str, Any],
    *,
    runtime: Mapping[str, Any],
) -> dict[str, Any]:
    expected_ids = [case["case_id"] for case in public["cases"]]
    by_id = {row["case_id"]: row for row in progress["results"]}
    if set(by_id) != set(expected_ids):
        raise HoldoutRunError(
            "CANNOT_SEAL_INCOMPLETE_RUN:"
            + ",".join(sorted(set(expected_ids) - set(by_id)))
        )
    ordered_results = [by_id[case_id] for case_id in expected_ids]
    submission = {
        "schema_version": SUBMISSION_SCHEMA,
        "task_id": TASK_ID,
        "run_id": progress["run_id"],
        "suite_id": SUITE_ID,
        "freeze_label": FREEZE_LABEL,
        "public_suite_sha256": progress["public_suite_sha256"],
        "adapter_schema_version": ADAPTER_SCHEMA_VERSION,
        "load_status": "LOADED_VERIFIED",
        "observed_controller_binding": progress["controller_binding"],
        "observed_finalizer_binding": progress["finalizer_binding"],
        "results": ordered_results,
        "restoration_isolation_checks": _restoration_isolation_checks(
            str(progress["run_id"])
        ),
    }
    run_metadata = {
        "schema_version": RUNNER_SCHEMA,
        "task_id": TASK_ID,
        "run_id": progress["run_id"],
        "started_at": progress["started_at"],
        "completed_at": utc_now(),
        "execution_status": "COMPLETE_UNEVALUATED",
        "suite_id": SUITE_ID,
        "freeze_label": FREEZE_LABEL,
        "source_boundary": {
            "fictional_source_free_suite": True,
            "scientific_family_used": False,
            "scientific_source_content_used": False,
            "private_labels_loaded_before_seal": False,
            "evaluator_private_fields_exposed_to_model": False,
        },
        "governance": {
            "one_authorized_full_suite_run_consumed": True,
            "cpu_only": True,
            "gpu_or_api_used": False,
            "local_files_only": True,
            "trust_remote_code": False,
            "network_disabled": True,
            "threads": THREADS,
            "enable_thinking": False,
            "decoding": "greedy",
            "native_tool_transport": "qwen_chat_template_tool_call",
            "max_new_tokens_per_factor": MAX_NEW_TOKENS,
            "context_cap_tokens": CONTEXT_CAP,
            "maximum_schema_only_retries_per_factor": 1,
            "semantic_repairs": 0,
            "cross_factor_retries": 0,
            "answer_or_action_substitutions": 0,
            "raw_attempts_preserved": True,
            "sealed_before_private_evaluation": True,
        },
        "binding": {
            "controller": progress["controller_binding"],
            "finalizer": progress["finalizer_binding"],
            "snapshot_path": str(SNAPSHOT),
            "snapshot_local_manifest_sha256": _sha256_file(
                root / SNAPSHOT / "LOCAL_MANIFEST.json"
            ),
            "snapshot_sha256s_sha256": _sha256_file(
                root / SNAPSHOT / "SHA256SUMS"
            ),
        },
        "counts": {
            **EXPECTED_COUNTS,
            "substantive_total": 40,
            "total": 51,
            "completed": len(ordered_results),
            "actual_model_generation_attempts": sum(
                not bool(record.get("fixture_injected"))
                for record in progress["attempts"]
            ),
            "injected_fixture_attempts": sum(
                bool(record.get("fixture_injected"))
                for record in progress["attempts"]
            ),
            "schema_only_retries": sum(
                record.get("kind") == "schema_only_retry"
                for record in progress["attempts"]
                if not record.get("fixture_injected")
            ),
        },
        "runtime": dict(runtime),
        "runner_source_sha256": progress["runner_source_sha256"],
        "prompt_policy_sha256": progress["prompt_policy_sha256"],
    }
    runner_manifest = {
        "schema_version": "av-trace.qwen3-adapter-v2-run-manifest/1.0",
        "task_id": TASK_ID,
        "run_id": progress["run_id"],
        "suite_id": SUITE_ID,
        "runner_source": str(Path(__file__).relative_to(root)),
        "runner_source_sha256": progress["runner_source_sha256"],
        "frozen_adapter_sha256": _sha256_file(
            root / "src/av_trace_strong_baselines_v2/adapter.py"
        ),
        "frozen_contracts_sha256": _sha256_file(
            root / "src/av_trace_strong_baselines_v2/contracts.py"
        ),
        "frozen_qwen_transport_sha256": _sha256_file(
            root / "tools/qwen3_8b_acquisition.py"
        ),
        "frozen_prompt_policy_sha256": progress["prompt_policy_sha256"],
        "private_evaluation_executed_at_seal_time": False,
        "independent_audit": (
            "scripts/audit_qwen3_adapter_v2_holdout_run.py"
        ),
    }
    _atomic_json(output_dir / "submission.json", submission)
    _atomic_jsonl(output_dir / "raw_attempts.jsonl", progress["attempts"])
    _atomic_json(output_dir / "run_metadata.json", run_metadata)
    _atomic_json(output_dir / "runner_manifest.json", runner_manifest)
    seal = {
        "schema_version": RUN_SEAL_SCHEMA,
        "task_id": TASK_ID,
        "run_id": progress["run_id"],
        "suite_id": SUITE_ID,
        "sealed_at": utc_now(),
        "state": "SEALED_BEFORE_PRIVATE_EVALUATION",
        "files": {
            name: {
                "sha256": _sha256_file(output_dir / name),
                "bytes": (output_dir / name).stat().st_size,
            }
            for name in SEALED_RUN_FILES
        },
    }
    _atomic_json(output_dir / "seal.json", seal, mode=0o400)
    for name in SEALED_RUN_FILES:
        os.chmod(output_dir / name, 0o400)
    (output_dir / "progress.json").unlink(missing_ok=True)
    return seal


def evaluate_payload(
    *,
    public: Mapping[str, Any],
    private: Mapping[str, Any],
    submission: Mapping[str, Any],
    raw_attempts: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Run the frozen metric logic with Qwen-specific identity and token."""

    report = _base_evaluate_payload(
        public=public,
        private=private,
        submission=submission,
        raw_attempts=raw_attempts,
    )
    suffix = str(report["decision"]).rsplit("_", 1)[-1]
    if str(report["decision"]).endswith("_NO_GO"):
        suffix = "NO_GO"
    report["schema_version"] = EVALUATOR_SCHEMA
    report["task_id"] = TASK_ID
    report["suite_id"] = SUITE_ID
    report["freeze_label"] = FREEZE_LABEL
    report["decision"] = f"QWEN3_ADAPTER_V2_HOLDOUT_{suffix}"
    return report


def _configure_base() -> None:
    """Bind the audited generic harness mechanics to the frozen Qwen suite."""

    overrides = {
        "TASK_ID": TASK_ID,
        "RUNNER_SCHEMA": RUNNER_SCHEMA,
        "SUBMISSION_SCHEMA": SUBMISSION_SCHEMA,
        "RUN_SEAL_SCHEMA": RUN_SEAL_SCHEMA,
        "EVALUATOR_SCHEMA": EVALUATOR_SCHEMA,
        "EVALUATION_SEAL_SCHEMA": EVALUATION_SEAL_SCHEMA,
        "HOLDOUT_DIR": HOLDOUT_DIR,
        "OUTPUT_DIR": OUTPUT_DIR,
        "SNAPSHOT": SNAPSHOT,
        "ACQUISITION_MANIFEST": ACQUISITION_MANIFEST,
        "SMOKE_REPORT": SMOKE_REPORT,
        "SUITE_ID": SUITE_ID,
        "FREEZE_LABEL": FREEZE_LABEL,
        "MODEL_REPO_ID": MODEL_REPO_ID,
        "MODEL_REVISION": MODEL_REVISION,
        "THREADS": THREADS,
        "MAX_NEW_TOKENS": MAX_NEW_TOKENS,
        "CONTEXT_CAP": CONTEXT_CAP,
        "ADDRESS_SPACE_LIMIT_BYTES": ADDRESS_SPACE_LIMIT_BYTES,
        "WHOLE_RUN_TIMEOUT_SECONDS": WHOLE_RUN_TIMEOUT_SECONDS,
        "EXPECTED_COUNTS": EXPECTED_COUNTS,
        "SEALED_RUN_FILES": SEALED_RUN_FILES,
        "FROZEN_IMPLEMENTATION_HASHES": FROZEN_IMPLEMENTATION_HASHES,
        "freeze_audit": freeze_audit,
        "acquisition": acquisition,
        "_preflight": _preflight,
        "_factor_spec": _factor_spec,
        "_normalize_action_transport": _normalize_action_transport,
        "_generate_factor_attempt": _generate_factor_attempt,
        "_new_progress": _new_progress,
        "_validate_progress": _validate_progress,
        "_authorization_claim": _authorization_claim,
        "_write_sealed_run": _write_sealed_run,
        "evaluate_payload": evaluate_payload,
    }
    for name, value in overrides.items():
        setattr(_base, name, value)


_configure_base()
EVIDENCE_STATE_FIELDS = _base.EVIDENCE_STATE_FIELDS
verify_run_seal = _base.verify_run_seal
_execute_child = _base._execute_child
_evaluate_sealed = _base._evaluate_sealed


def _run_parent(
    root: Path,
    output_dir: Path,
    *,
    resume: bool,
) -> None:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--child-run",
        "--repo-root",
        str(root),
        "--output-dir",
        str(output_dir),
    ]
    if resume:
        command.append("--resume")
    environment = os.environ.copy()
    environment.update(
        {
            "CUDA_VISIBLE_DEVICES": "",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "HF_DATASETS_OFFLINE": "1",
            "TOKENIZERS_PARALLELISM": "false",
            "OMP_NUM_THREADS": str(THREADS),
            "MKL_NUM_THREADS": str(THREADS),
            "OPENBLAS_NUM_THREADS": str(THREADS),
        }
    )
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
        cwd=root,
        env=environment,
        check=True,
        timeout=WHOLE_RUN_TIMEOUT_SECONDS,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Execute/evaluate the one authorized Qwen3 adapter-v2 holdout."
        )
    )
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--preflight", action="store_true")
    modes.add_argument("--execute", action="store_true")
    modes.add_argument("--evaluate", action="store_true")
    modes.add_argument("--child-run", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = root / output_dir
    if args.preflight:
        _, report = _preflight(root, output_dir, execution_mode=False)
        print(json.dumps(report, indent=2, sort_keys=True))
        return
    if args.child_run:
        _execute_child(root, output_dir, resume=args.resume)
        return
    if args.execute:
        _run_parent(root, output_dir, resume=args.resume)
        return
    if args.evaluate:
        report = _evaluate_sealed(root, output_dir)
        print(json.dumps(report, indent=2, sort_keys=True))
        return
    raise AssertionError("unreachable")


if __name__ == "__main__":
    main()
