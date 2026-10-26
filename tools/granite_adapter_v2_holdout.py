#!/usr/bin/env python3
"""Task 177: one-run Granite adapter-v2 fictional holdout execution.

The executable phases are deliberately separate:

* ``--preflight`` verifies the Task-176 suite/governance seals, frozen source
  hashes, exact local snapshot, environment policy, and one-run state without
  loading the model or private evaluator labels.
* ``--execute`` claims the one authorized run, executes or fail-closed resumes
  every public substantive/runtime case, and seals all raw attempts before any
  private evaluation.
* ``--evaluate`` verifies the run seal, then and only then loads the private
  evaluator key and applies the frozen Gate-C thresholds.

The independent evaluator replay/component audit is implemented separately in
``scripts/audit_granite_adapter_v2_holdout_run.py``.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import resource
import subprocess
import sys
import time
import uuid
from collections import Counter, defaultdict
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
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
    LoadStatus,
    ModelBinding,
    canonical_json_bytes,
    require_exact_binding,
    sha256_json,
)
from av_trace_strong_baselines.errors import (
    SchemaViolation,
    StrongBaselineError,
)
from av_trace_strong_baselines.schemas import (
    EVIDENCE_STATE_FIELDS,
    parse_strict_json,
)
from av_trace_strong_baselines.security import (
    FORBIDDEN_PRIVATE_KEYS,
    PRIVATE_IDENTIFIER_PATTERNS,
    assert_public_surface,
)
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
    parse_factor_attempts,
    parse_finalizer_factors,
)
from scripts import audit_granite_adapter_v2_holdout as freeze_audit
from tools import granite33_8b_acquisition as acquisition

TASK_ID = 177
RUNNER_SCHEMA = "av-trace.granite-adapter-v2-holdout-runner/1.0"
SUBMISSION_SCHEMA = "av-trace.granite-adapter-v2-holdout-submission/1.0"
RUN_SEAL_SCHEMA = "av-trace.granite-adapter-v2-holdout-run-seal/1.0"
EVALUATOR_SCHEMA = "av-trace.granite-adapter-v2-gate-c-report/1.0"
EVALUATION_SEAL_SCHEMA = (
    "av-trace.granite-adapter-v2-holdout-evaluation-seal/1.0"
)

HOLDOUT_DIR = Path("data/restricted/strong_baselines/granite_v2_holdout")
OUTPUT_DIR = Path(
    "data/restricted/strong_baselines/granite_v2_holdout_run"
)
SNAPSHOT = Path(
    "data/restricted/strong_baselines/models/"
    "ibm-granite--granite-3.3-8b-instruct--51dd4bc2ade4"
)
ACQUISITION_MANIFEST = Path(
    "data/restricted/strong_baselines/manifests/"
    "granite33_8b_acquisition.json"
)
SMOKE_REPORT = Path(
    "data/restricted/strong_baselines/acquisition_records/"
    "granite33-8b-51dd4bc2ade4/cpu_load_smoke.json"
)

SUITE_ID = "granite-v2-fictional-holdout-20261002"
FREEZE_LABEL = "GRANITE_ADAPTER_V2_HOLDOUT_2026-10-02"
MODEL_REPO_ID = "ibm-granite/granite-3.3-8b-instruct"
MODEL_REVISION = "51dd4bc2ade4059a6bd87649d68aa11e4fb2529b"
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
    "src/av_trace_strong_baselines_v2/adapter.py": (
        "13e1b49881672eac6125235c524e969543a337e3e100e163a7f7f5e696fea4e1"
    ),
    "src/av_trace_strong_baselines_v2/contracts.py": (
        "535b1e25aa63237cb0402fcc0f797e5e222c5637a318c2c27d08669fff1b79f1"
    ),
    "src/av_trace_strong_baselines_v2/suite_generator.py": (
        "292c438d4c1ad2e620f2090b3fb52344df064a528089fa06217919e1606409db"
    ),
    "scripts/generate_granite_adapter_v2_suite.py": (
        "74397ae4e5a1281ea8e7d85983e5fdcd5e5e531b995a94be19d6e040bfc91b2d"
    ),
    "scripts/audit_granite_adapter_v2_holdout.py": (
        "564db2c7d30fb866ba41525f44243a090b9f9e3bde13660714e23e954ecc2f66"
    ),
}


class HoldoutRunError(RuntimeError):
    """Fail-closed Task-177 runner/evaluator error."""


def utc_now() -> str:
    return (
        datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise HoldoutRunError(f"JSON_NOT_OBJECT:{path}")
    return value


def _sha256_file(path: Path, block_size: int = 8 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(block_size):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _atomic_bytes(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        temporary.write_bytes(payload)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_json(path: Path, value: Any, *, mode: int = 0o600) -> None:
    _atomic_bytes(
        path,
        (
            json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)
            + "\n"
        ).encode("utf-8"),
        mode=mode,
    )


def _atomic_jsonl(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    *,
    mode: int = 0o600,
) -> None:
    payload = "".join(
        json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n"
        for row in rows
    ).encode("utf-8")
    _atomic_bytes(path, payload, mode=mode)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        value = json.loads(line)
        if not isinstance(value, dict):
            raise HoldoutRunError(
                f"JSONL_ROW_NOT_OBJECT:{path}:{line_number}"
            )
        rows.append(value)
    return rows


def _binding(value: Mapping[str, Any]) -> ModelBinding:
    return ModelBinding(
        repo_id=str(value["repo_id"]),
        revision=str(value["revision"]),
        role=str(value["role"]),
        processor_revision=str(value["processor_revision"]),
        tokenizer_revision=str(value["tokenizer_revision"]),
    )


def _offline_environment() -> None:
    os.environ.update(
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
    for name in list(os.environ):
        if name.lower() in {
            "http_proxy",
            "https_proxy",
            "all_proxy",
            "no_proxy",
        } or name.upper() in {"HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"}:
            os.environ.pop(name, None)


@contextlib.contextmanager
def _network_denial() -> Iterator[dict[str, int]]:
    with acquisition.deny_network() as attempts:
        yield attempts


def _preflight(
    root: Path,
    output_dir: Path,
    *,
    execution_mode: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    restricted = root / HOLDOUT_DIR
    public_path = restricted / "public_suite.json"
    freeze_seal_path = restricted / "freeze_seal.json"
    freeze_manifest_path = restricted / "freeze_manifest.json"
    if not public_path.is_file():
        raise HoldoutRunError("FROZEN_HOLDOUT_NOT_FOUND")

    audit_report = freeze_audit.audit(restricted)
    if audit_report.get("status") != "PASS":
        raise HoldoutRunError("TASK176_INDEPENDENT_AUDIT_FAILED")

    public = _load_json(public_path)
    freeze_manifest = _load_json(freeze_manifest_path)
    freeze_seal = _load_json(freeze_seal_path)
    if (
        public.get("suite_id") != SUITE_ID
        or public.get("freeze_label") != FREEZE_LABEL
        or public.get("adapter_schema_version") != ADAPTER_SCHEMA_VERSION
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
        "post_run_evaluator_replay_count": 1,
        "pre_run_seal_and_environment_verification_required": True,
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
            raise HoldoutRunError(f"FROZEN_IMPLEMENTATION_HASH_MISMATCH:{relative}")
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
    if acquisition_manifest.get("decision") != "GRANITE33_8B_ACQUISITION_READY":
        raise HoldoutRunError("GRANITE_ACQUISITION_NOT_READY")
    if (
        smoke.get("status") != "LOAD_SMOKE_COMPLETE"
        or smoke.get("repo_id") != MODEL_REPO_ID
        or smoke.get("revision") != MODEL_REVISION
        or smoke.get("local_files_only") is not True
        or smoke.get("trust_remote_code") is not False
        or smoke.get("runtime", {}).get("threads") != THREADS
        or smoke.get("network_attempts") != 0
    ):
        raise HoldoutRunError("GRANITE_SMOKE_CONTRACT_MISMATCH")
    plan = _load_json(root / acquisition.PLAN)
    acquisition.validate_plan(plan)
    snapshot = root / SNAPSHOT
    if (root / plan["model"]["snapshot_dir"]).resolve() != snapshot.resolve():
        raise HoldoutRunError("GRANITE_SNAPSHOT_PATH_MISMATCH")
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
        "schema_version": "av-trace.granite-adapter-v2-preflight/1.0",
        "task_id": TASK_ID,
        "checked_at": utc_now(),
        "suite_id": SUITE_ID,
        "freeze_label": FREEZE_LABEL,
        "task176_audit_status": audit_report["status"],
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
            "maximum_schema_only_retries_per_factor": 1,
            "semantic_retries": 0,
            "cross_factor_retries": 0,
        },
        "status": "PASS",
    }
    return public, report


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


def _claim_handles(case: Mapping[str, Any]) -> list[str]:
    return [
        str(item["claim_handle"])
        for item in case["public_input"]["public_claim_slots"]
    ]


def _factor_key(case_id: str, factor_name: str) -> str:
    return f"{case_id}::{factor_name}"


def _factor_messages(
    *,
    case: Mapping[str, Any],
    factor_name: str,
    role: str,
    schema: Mapping[str, Any],
    prompt_policy: Mapping[str, Any],
    previous_raw: str | None = None,
    previous_error: str | None = None,
) -> list[dict[str, str]]:
    policy_key = "controller" if case["case_type"] == "controller" else "finalizer"
    system = str(prompt_policy[policy_key])
    if factor_name == "action_choice":
        factor_instruction = (
            "For this factor only, choose exactly one supplied no-argument "
            "function. A function call is required. Do not answer the case, "
            "do not emit prose, and do not regenerate tool arguments."
        )
    else:
        factor_instruction = (
            "For this factor only, return exactly one compact JSON object and "
            "no prose or markdown. Match the supplied schema exactly. Author "
            "only this factor; do not assume or repair another factor."
        )
    user_payload: dict[str, Any] = {
        "factor_id": factor_name,
        "factor_role": role,
        "output_schema": schema,
        "public_case": {
            "case_type": case["case_type"],
            "public_input": case["public_input"],
        },
    }
    if previous_raw is not None:
        factor_instruction += (
            " This is the one allowed schema-only retry. Preserve every "
            "semantic scalar value from the prior attempt exactly; change "
            "only JSON/schema representation. If that cannot be done, repeat "
            "the prior content without inventing or substituting semantics."
        )
        user_payload["schema_only_retry"] = {
            "prior_error_code": previous_error,
            "prior_raw_output": previous_raw,
        }
    return [
        {"role": "system", "content": system + " " + factor_instruction},
        {
            "role": "user",
            "content": json.dumps(
                user_payload,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            ),
        },
    ]


def _strip_transport_specials(raw: str) -> str:
    value = raw.strip()
    for token in ("<|end_of_text|>",):
        while value.endswith(token):
            value = value[: -len(token)].rstrip()
    return value


def _normalize_action_transport(raw: str) -> tuple[bytes, str]:
    """Decode only Granite's native tool-call transport, without choosing."""

    content = _strip_transport_specials(raw)
    if content.startswith("<|tool_call|>"):
        content = content[len("<|tool_call|>") :].lstrip()
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
    elif (
        isinstance(value, list)
        and len(value) == 1
        and isinstance(value[0], Mapping)
    ):
        item = value[0]
        if set(item) == {"name", "arguments"}:
            canonical = {
                "function_name": item["name"],
                "arguments": item["arguments"],
            }
        elif (
            set(item) == {"type", "function"}
            and item.get("type") == "function"
            and isinstance(item.get("function"), Mapping)
            and set(item["function"]) == {"name", "arguments"}
        ):
            canonical = {
                "function_name": item["function"]["name"],
                "arguments": item["function"]["arguments"],
            }
    if canonical is None:
        return content.encode("utf-8"), "parsed_passthrough"
    return canonical_json_bytes(canonical), "granite_native_tool_call"


def _attempt_objects(
    records: Sequence[Mapping[str, Any]],
) -> tuple[RawFactorAttempt, ...]:
    attempts: list[RawFactorAttempt] = []
    for record in records:
        adapter_input = record.get("adapter_input")
        if not isinstance(adapter_input, str):
            continue
        attempts.append(
            RawFactorAttempt.from_text(
                adapter_input,
                attempt_index=int(record["attempt_index"]),
                kind=(
                    AttemptKind.INITIAL
                    if int(record["attempt_index"]) == 1
                    else AttemptKind.SCHEMA_ONLY_RETRY
                ),
            )
        )
    return tuple(attempts)


def _factor_outcome_for_records(
    *,
    case: Mapping[str, Any],
    factor_name: str,
    records: Sequence[Mapping[str, Any]],
) -> Any:
    attempts = _attempt_objects(records)
    if not attempts:
        return None
    handles = _claim_handles(case)
    if case["case_type"] == "controller":
        if factor_name == "action_choice":
            plan = build_native_action_plan(case["public_input"]["action_menu"])
            return parse_factor_attempts(
                action_choice_spec(plan),
                attempts,
                lambda value: _parse_action_for_runner(value, plan),
            )
        if factor_name == "evidence_state":
            spec = evidence_state_spec(handles)
            return parse_factor_attempts(
                spec,
                attempts,
                lambda value: _parse_state_for_runner(
                    case=case,
                    records=records,
                    value=value,
                ),
            )
    if case["case_type"] == "finalizer":
        observations = case["public_input"]["observed_evidence"]
        observation_ids = [
            str(item["observation_id"]) for item in observations
        ]
        specs = finalizer_factor_specs(
            claim_handles=handles,
            observation_ids=observation_ids,
        )
        validators = _finalizer_validators_for_runner(
            handles=handles,
            observation_ids=observation_ids,
        )
        return parse_factor_attempts(
            specs[factor_name],
            attempts,
            validators[factor_name],
        )
    raise HoldoutRunError(f"FACTOR_OUTCOME_UNSUPPORTED:{factor_name}")


def _parse_action_for_runner(value: Any, plan: Any) -> Any:
    # Reuse the frozen public parser through a one-factor controller parse.
    raw = RawFactorAttempt.from_text(json.dumps(value, separators=(",", ":")))
    dummy_state = RawFactorAttempt.from_text(
        json.dumps(
            {
                "p_sufficient": 0.0,
                "covered_claim_handles": [],
                "missing_modalities": ["vision"],
                "missing_hops": ["entity_identity"],
                "missingness_cause": "evidence_accessible_but_not_found",
                "recovery_intent": "search_vision",
            },
            separators=(",", ":"),
        )
    )
    parsed = parse_controller_factors(
        action_menu=plan.action_menu,
        claim_handles=["public.runner.placeholder"],
        observed_evidence=[],
        action_attempts=(raw,),
        evidence_state_attempts=(dummy_state,),
    )
    if parsed.action_factor.status is not FactorStatus.VALID:
        raise SchemaViolation(
            parsed.action_factor.error_code or "ACTION_FACTOR_INVALID"
        )
    return parsed.action_factor.value


def _parse_state_for_runner(
    *,
    case: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    value: Any,
) -> Any:
    # Reuse the frozen state parser with a known-valid first menu choice.
    plan = build_native_action_plan(case["public_input"]["action_menu"])
    action = RawFactorAttempt.from_text(
        json.dumps(
            {
                "function_name": plan.function_name_for_index(0),
                "arguments": {},
            },
            separators=(",", ":"),
        )
    )
    state = RawFactorAttempt.from_text(json.dumps(value, separators=(",", ":")))
    parsed = parse_controller_factors(
        action_menu=case["public_input"]["action_menu"],
        claim_handles=_claim_handles(case),
        observed_evidence=case["public_input"]["observed_evidence"],
        action_attempts=(action,),
        evidence_state_attempts=(state,),
    )
    if parsed.evidence_state_factor.status is not FactorStatus.VALID:
        raise SchemaViolation(
            parsed.evidence_state_factor.error_code or "STATE_FACTOR_INVALID"
        )
    return parsed.evidence_state_factor.value


def _finalizer_validators_for_runner(
    *,
    handles: Sequence[str],
    observation_ids: Sequence[str],
) -> dict[str, Any]:
    # The frozen parsers are exercised by a full parse with placeholders for
    # all non-target factors. This avoids duplicating or weakening validation.
    def validate(name: str, value: Any) -> Any:
        valid = {
            "disposition": {
                "p_sufficient": 0.0,
                "verdict": "insufficient",
                "answer_mode": "abstain",
                "termination_reason": "no_recovery_route",
            },
            "answer_text": {"text": ""},
            "claim_drafts": {"claims": []},
            "citation_selections": {"selections": []},
            "diagnosis": {
                "modality_probabilities": {
                    "vision": 0.0,
                    "speech": 0.0,
                    "ambient": 0.0,
                },
                "hop_types": [],
                "cause_probabilities": {
                    "source_evidence_absent": 0.0,
                    "evidence_in_source_but_inaccessible": 0.0,
                    "evidence_accessible_but_not_found": 1.0,
                    "not_missing": 0.0,
                    "uncertain": 0.0,
                },
                "recovery_route_declared": False,
                "description": "",
            },
        }
        valid[name] = value
        attempts = {
            key: (
                RawFactorAttempt.from_text(
                    json.dumps(child, separators=(",", ":"))
                ),
            )
            for key, child in valid.items()
        }
        observations = [
            {
                "observation_id": observation_id,
                "interval": {"start_s": float(index), "end_s": float(index + 1)},
                "modalities": ["vision"],
                "payload": {"text": "runner validation placeholder"},
            }
            for index, observation_id in enumerate(observation_ids)
        ]
        result = parse_finalizer_factors(
            claim_handles=handles,
            observations=observations,
            attempts_by_factor=attempts,
        )
        outcome = result.factors[name]
        if outcome.status is not FactorStatus.VALID:
            raise SchemaViolation(outcome.error_code or "FACTOR_INVALID")
        return outcome.value

    return {
        name: (lambda value, name=name: validate(name, value))
        for name in (
            "disposition",
            "answer_text",
            "claim_drafts",
            "citation_selections",
            "diagnosis",
        )
    }


def _factor_spec(
    case: Mapping[str, Any],
    factor_name: str,
) -> tuple[Any, str]:
    handles = _claim_handles(case)
    if case["case_type"] == "controller":
        if factor_name == "action_choice":
            plan = build_native_action_plan(case["public_input"]["action_menu"])
            return action_choice_spec(plan), "granite_native_tool_choice"
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


def _factor_names(case: Mapping[str, Any]) -> tuple[str, ...]:
    if case["case_type"] == "controller":
        return ("action_choice", "evidence_state")
    if case["case_type"] == "finalizer":
        return (
            "disposition",
            "answer_text",
            "claim_drafts",
            "citation_selections",
            "diagnosis",
        )
    return ()


def _exception_status(exc: BaseException) -> InferenceStatus:
    if isinstance(exc, TimeoutError):
        return InferenceStatus.TIMEOUT
    if isinstance(exc, MemoryError):
        return InferenceStatus.OOM
    return InferenceStatus.PROVIDER_FAILURE


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
        thinking=False,
    )
    inputs = tokenizer(rendered, return_tensors="pt")
    prompt_tokens = int(inputs["input_ids"].numel())
    record: dict[str, Any] = {
        "attempt_id": (
            f"{case['case_id']}::{factor_name}::{attempt_index}"
        ),
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
            "granite_native_function_call"
            if factor_name == "action_choice"
            else "strict_constrained_json"
        ),
    }
    if prompt_tokens > CONTEXT_CAP:
        record.update(
            {
                "completion_tokens": None,
                "generation_seconds": 0.0,
                "raw_output": None,
                "raw_output_with_special_tokens": None,
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
                "adapter_input": None,
                "adapter_input_sha256": None,
                "transport_normalization": None,
                "inference_status": str(_exception_status(exc)),
                "error_code": type(exc).__name__,
            }
        )
    return record


def _records_for_factor(
    progress: Mapping[str, Any],
    case_id: str,
    factor_name: str,
) -> list[dict[str, Any]]:
    return [
        dict(record)
        for record in progress.get("attempts", [])
        if record.get("case_id") == case_id
        and record.get("factor_name") == factor_name
    ]


def _complete_factor(
    *,
    root: Path,
    output_dir: Path,
    progress: dict[str, Any],
    case: Mapping[str, Any],
    factor_name: str,
    prompt_policy: Mapping[str, Any],
    tokenizer: Any,
    model: Any,
    torch: Any,
) -> None:
    progress_path = output_dir / "progress.json"
    records = _records_for_factor(progress, str(case["case_id"]), factor_name)
    runtime_terminal = any(
        record.get("inference_status") != str(InferenceStatus.VALID)
        for record in records
    )
    outcome = (
        None
        if runtime_terminal
        else _factor_outcome_for_records(
            case=case,
            factor_name=factor_name,
            records=records,
        )
    )
    if runtime_terminal or (
        outcome is not None
        and (
            outcome.status is FactorStatus.VALID
            or len(records) >= 2
            or outcome.error_code
            not in _factor_spec(case, factor_name)[0].repairable_error_codes
        )
    ):
        return
    if len(records) >= 2:
        return
    attempt_index = len(records) + 1
    previous_raw = (
        str(records[0]["raw_output"]) if records and records[0].get("raw_output") is not None else None
    )
    previous_error = outcome.error_code if outcome is not None else None
    progress["active_factor"] = {
        "case_id": case["case_id"],
        "factor_name": factor_name,
        "attempt_index": attempt_index,
        "started_at": utc_now(),
    }
    _atomic_json(progress_path, progress)
    record = _generate_factor_attempt(
        case=case,
        factor_name=factor_name,
        prompt_policy=prompt_policy,
        tokenizer=tokenizer,
        model=model,
        torch=torch,
        attempt_index=attempt_index,
        previous_raw=previous_raw,
        previous_error=previous_error,
    )
    progress["attempts"].append(record)
    progress["active_factor"] = None
    progress["last_persisted_attempt_id"] = record["attempt_id"]
    progress["last_persisted_at"] = utc_now()
    _atomic_json(progress_path, progress)

    records = _records_for_factor(progress, str(case["case_id"]), factor_name)
    if record["inference_status"] != str(InferenceStatus.VALID):
        return
    outcome = _factor_outcome_for_records(
        case=case,
        factor_name=factor_name,
        records=records,
    )
    if (
        outcome is not None
        and outcome.status is FactorStatus.INVALID_OUTPUT
        and len(records) == 1
        and outcome.error_code
        in _factor_spec(case, factor_name)[0].repairable_error_codes
    ):
        _complete_factor(
            root=root,
            output_dir=output_dir,
            progress=progress,
            case=case,
            factor_name=factor_name,
            prompt_policy=prompt_policy,
            tokenizer=tokenizer,
            model=model,
            torch=torch,
        )


def _outcome_summary(outcome: Any) -> dict[str, Any] | None:
    if outcome is None:
        return None
    return {
        "factor_id": outcome.factor_id,
        "status": str(outcome.status),
        "error_code": outcome.error_code,
        "schema_retries_used": outcome.schema_retries_used,
        "value": _jsonable(outcome.value),
        "attempt_sha256s": [attempt.sha256 for attempt in outcome.attempts],
    }


def _assemble_substantive_result(
    case: Mapping[str, Any],
    progress: Mapping[str, Any],
) -> dict[str, Any]:
    factor_records = {
        name: _records_for_factor(progress, str(case["case_id"]), name)
        for name in _factor_names(case)
    }
    runtime_errors = [
        record
        for records in factor_records.values()
        for record in records
        if record.get("inference_status") != str(InferenceStatus.VALID)
    ]
    calls = sum(len(records) for records in factor_records.values())
    retries = sum(max(0, len(records) - 1) for records in factor_records.values())
    base: dict[str, Any] = {
        "case_id": case["case_id"],
        "case_type": case["case_type"],
        "stratum": case["stratum"],
        "model_was_called": calls > 0,
        "model_calls_used": calls,
        "schema_repairs_used": retries,
        "repair_kind": "schema_only" if retries else "none",
        "factor_attempt_ids": {
            name: [record["attempt_id"] for record in records]
            for name, records in factor_records.items()
        },
        "deterministic_answer_substitution": False,
        "private_fields_supplied_to_model": False,
    }
    if runtime_errors:
        base.update(
            {
                "inference_status": runtime_errors[0]["inference_status"],
                "error_code": runtime_errors[0]["error_code"],
                "structured_output": None,
                "factor_outcomes": {},
            }
        )
        return base

    if case["case_type"] == "controller":
        action_attempts = _attempt_objects(factor_records["action_choice"])
        state_attempts = _attempt_objects(factor_records["evidence_state"])
        result = parse_controller_factors(
            action_menu=case["public_input"]["action_menu"],
            claim_handles=_claim_handles(case),
            observed_evidence=case["public_input"]["observed_evidence"],
            action_attempts=action_attempts,
            evidence_state_attempts=state_attempts,
        )
        structured = None
        if result.canonical_decision is not None:
            structured = {
                "action_index": result.canonical_decision["action_index"],
                "evidence_state": result.canonical_decision["evidence_state"],
            }
        valid = structured is not None
        base.update(
            {
                "inference_status": str(
                    InferenceStatus.VALID
                    if valid
                    else InferenceStatus.INVALID_OUTPUT
                ),
                "error_code": (
                    None
                    if valid
                    else result.state_projection.error_code
                    or result.evidence_state_factor.error_code
                    or result.action_factor.error_code
                    or "CONTROLLER_FACTORS_INVALID"
                ),
                "structured_output": structured,
                "factor_outcomes": {
                    "action_choice": _outcome_summary(result.action_factor),
                    "evidence_state": _outcome_summary(
                        result.evidence_state_factor
                    ),
                },
                "state_projection": {
                    "status": str(result.state_projection.status),
                    "error_code": result.state_projection.error_code,
                },
            }
        )
        return base

    attempts_by_factor = {
        name: _attempt_objects(records)
        for name, records in factor_records.items()
    }
    result = parse_finalizer_factors(
        claim_handles=_claim_handles(case),
        observations=case["public_input"]["observed_evidence"],
        attempts_by_factor=attempts_by_factor,
    )
    valid = result.canonical_envelope is not None
    base.update(
        {
            "inference_status": str(
                InferenceStatus.VALID
                if valid
                else InferenceStatus.INVALID_OUTPUT
            ),
            "error_code": (
                None
                if valid
                else result.projection_error_code
                or "FINALIZER_FACTORS_INVALID"
            ),
            "structured_output": _jsonable(result.canonical_envelope),
            "factor_outcomes": {
                name: _outcome_summary(outcome)
                for name, outcome in result.factors.items()
            },
            "projection_status": str(result.projection_status),
            "projection_error_code": result.projection_error_code,
            "output_provenance": {
                "model_authored_paths": [
                    "final_answer.p_sufficient",
                    "final_answer.verdict",
                    "final_answer.answer_mode",
                    "final_answer.claims",
                    "final_answer.diagnosis",
                    "final_answer.natural_language_answer",
                    "final_answer.termination_reason",
                ],
                "copied_paths": [
                    "final_answer.claims.citations.interval",
                    "final_answer.claims.citations.modalities",
                    "claim_to_citations",
                ],
                "deterministic_paths": [],
            },
        }
    )
    return base


def _runtime_fixture(
    case: Mapping[str, Any],
    controller_binding: ModelBinding,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    fixture = str(case["public_input"]["injected_public_fixture"])
    case_id = str(case["case_id"])
    attempts: list[dict[str, Any]] = []
    status = InferenceStatus.INVALID_OUTPUT
    model_called = True
    calls = 1
    retries = 0
    error = f"INJECTED_{fixture.upper()}"

    def injected(
        factor_name: str,
        index: int,
        raw: str | None,
        *,
        kind: str = "initial",
        inference_status: InferenceStatus = InferenceStatus.VALID,
        error_code: str | None = None,
    ) -> dict[str, Any]:
        return {
            "attempt_id": f"{case_id}::{factor_name}::{index}",
            "case_id": case_id,
            "case_type": "runtime_failure",
            "factor_name": factor_name,
            "attempt_index": index,
            "kind": kind,
            "prompt_sha256": None,
            "public_case_sha256": sha256_json(
                {
                    "case_type": case["case_type"],
                    "public_input": case["public_input"],
                }
            ),
            "factor_schema_sha256": None,
            "prompt_tokens": 0,
            "completion_tokens": 0 if raw is not None else None,
            "generation_seconds": 0.0,
            "raw_output": raw,
            "raw_output_with_special_tokens": raw,
            "raw_output_sha256": (
                _sha256_bytes(raw.encode("utf-8")) if raw is not None else None
            ),
            "raw_output_with_special_tokens_sha256": (
                _sha256_bytes(raw.encode("utf-8")) if raw is not None else None
            ),
            "adapter_input": raw,
            "adapter_input_sha256": (
                _sha256_bytes(raw.encode("utf-8")) if raw is not None else None
            ),
            "transport_normalization": "injected_fixture",
            "inference_status": str(inference_status),
            "error_code": error_code,
            "fixture_injected": True,
        }

    if fixture in {
        "malformed_action_factor",
        "malformed_state_factor",
        "malformed_claim_factor",
        "malformed_citation_factor",
    }:
        factor = {
            "malformed_action_factor": "action_choice",
            "malformed_state_factor": "evidence_state",
            "malformed_claim_factor": "claim_drafts",
            "malformed_citation_factor": "citation_selections",
        }[fixture]
        attempts = [
            injected(factor, 1, "{not valid json", error_code="MODEL_OUTPUT_MALFORMED_JSON"),
            injected(
                factor,
                2,
                "{not valid json",
                kind="schema_only_retry",
                error_code="MODEL_OUTPUT_MALFORMED_JSON",
            ),
        ]
        calls = 2
        retries = 1
        error = "MODEL_OUTPUT_MALFORMED_JSON"
    elif fixture == "wrong_snapshot":
        status = InferenceStatus.SNAPSHOT_MISMATCH
        model_called = False
        calls = 0
        error = "INJECTED_WRONG_SNAPSHOT"
        wrong = ModelBinding(
            repo_id=controller_binding.repo_id,
            revision="0" * 40,
            role=controller_binding.role,
            processor_revision="0" * 40,
            tokenizer_revision="0" * 40,
        )
        try:
            require_exact_binding(
                controller_binding,
                wrong,
                load_status=LoadStatus.LOADED_VERIFIED,
            )
        except StrongBaselineError:
            pass
        else:
            raise HoldoutRunError("WRONG_SNAPSHOT_FIXTURE_DID_NOT_FAIL")
    elif fixture == "provider_failure":
        status = InferenceStatus.PROVIDER_FAILURE
        error = "INJECTED_PROVIDER_FAILURE"
        attempts = [
            injected(
                "runtime",
                1,
                None,
                inference_status=status,
                error_code=error,
            )
        ]
    elif fixture == "timeout":
        status = InferenceStatus.TIMEOUT
        error = "INJECTED_TIMEOUT"
        attempts = [
            injected(
                "runtime",
                1,
                None,
                inference_status=status,
                error_code=error,
            )
        ]
    elif fixture == "process_failure":
        status = InferenceStatus.PROCESS_FAILURE
        error = "INJECTED_PROCESS_FAILURE"
        attempts = [
            injected(
                "runtime",
                1,
                None,
                inference_status=status,
                error_code=error,
            )
        ]
    elif fixture == "oom":
        status = InferenceStatus.OOM
        error = "INJECTED_OOM"
        attempts = [
            injected(
                "runtime",
                1,
                None,
                inference_status=status,
                error_code=error,
            )
        ]
    elif fixture == "budget_exhausted":
        status = InferenceStatus.BUDGET_EXHAUSTED
        model_called = False
        calls = 0
        error = "MODEL_CALL_BUDGET_EXHAUSTED"
    elif fixture == "cross_factor_semantic_retry":
        menu = [
            {
                "tool": "finalize",
                "arguments": {},
            },
            {
                "tool": "get_channel_status",
                "arguments": {"channels": ["speech"]},
            },
        ]
        plan = build_native_action_plan(menu)
        first = json.dumps(
            {
                "function_name": plan.function_name_for_index(0),
                "arguments": [],
            },
            separators=(",", ":"),
        )
        second = json.dumps(
            {
                "function_name": plan.function_name_for_index(1),
                "arguments": {},
            },
            separators=(",", ":"),
        )
        attempts = [
            injected(
                "action_choice",
                1,
                first,
                error_code="NATIVE_ARGUMENTS_NOT_EMPTY_OBJECT",
            ),
            injected(
                "action_choice",
                2,
                second,
                kind="schema_only_retry",
                error_code="SCHEMA_RETRY_CHANGED_CONTENT",
            ),
        ]
        outcome = parse_factor_attempts(
            action_choice_spec(plan),
            (
                RawFactorAttempt.from_text(first),
                RawFactorAttempt.from_text(
                    second,
                    attempt_index=2,
                    kind=AttemptKind.SCHEMA_ONLY_RETRY,
                ),
            ),
            lambda value: _parse_action_for_runner(value, plan),
        )
        if (
            outcome.status is not FactorStatus.INVALID_OUTPUT
            or outcome.error_code != "SCHEMA_RETRY_CHANGED_CONTENT"
        ):
            raise HoldoutRunError("SEMANTIC_RETRY_FIXTURE_DID_NOT_FAIL")
        calls = 2
        retries = 1
        error = outcome.error_code
    else:
        raise HoldoutRunError(f"UNKNOWN_RUNTIME_FIXTURE:{fixture}")

    row = {
        "case_id": case_id,
        "case_type": "runtime_failure",
        "stratum": fixture,
        "inference_status": str(status),
        "model_was_called": model_called,
        "model_calls_used": calls,
        "schema_repairs_used": retries,
        "repair_kind": "schema_only" if retries else "none",
        "factor_attempt_ids": {
            "fixture": [record["attempt_id"] for record in attempts]
        },
        "error_code": error,
        "structured_output": None,
        "final_answer": None,
        "fixture_injected": True,
        "deterministic_answer_substitution": False,
        "private_fields_supplied_to_model": False,
    }
    return row, attempts


def _new_progress(
    public: Mapping[str, Any],
    preflight: Mapping[str, Any],
    controller_binding: ModelBinding,
    finalizer_binding: ModelBinding,
) -> dict[str, Any]:
    return {
        "schema_version": RUNNER_SCHEMA,
        "task_id": TASK_ID,
        "run_id": f"task177-{utc_now()}-{uuid.uuid4().hex[:12]}",
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
        or progress.get("runner_source_sha256") != _sha256_file(Path(__file__))
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


def _resolve_interrupted_factor(
    progress: dict[str, Any],
    output_dir: Path,
) -> None:
    active = progress.get("active_factor")
    if not isinstance(active, Mapping):
        return
    case_id = str(active["case_id"])
    factor_name = str(active["factor_name"])
    attempt_index = int(active["attempt_index"])
    attempt_id = f"{case_id}::{factor_name}::{attempt_index}"
    if not any(
        record.get("attempt_id") == attempt_id
        for record in progress.get("attempts", [])
    ):
        progress["attempts"].append(
            {
                "attempt_id": attempt_id,
                "case_id": case_id,
                "case_type": "unknown_after_interruption",
                "factor_name": factor_name,
                "attempt_index": attempt_index,
                "kind": (
                    "initial"
                    if attempt_index == 1
                    else "schema_only_retry"
                ),
                "prompt_sha256": None,
                "public_case_sha256": None,
                "factor_schema_sha256": None,
                "prompt_tokens": None,
                "completion_tokens": None,
                "generation_seconds": None,
                "raw_output": None,
                "raw_output_with_special_tokens": None,
                "adapter_input": None,
                "adapter_input_sha256": None,
                "transport_normalization": None,
                "inference_status": str(InferenceStatus.PROCESS_FAILURE),
                "error_code": "INTERRUPTED_ACTIVE_FACTOR_NOT_RETRIED",
                "resume_fail_closed": True,
            }
        )
    progress["active_factor"] = None
    progress["resume_event"] = {
        "resolved_at": utc_now(),
        "policy": "active_factor_marked_process_failure_without_rerun",
        "attempt_id": attempt_id,
    }
    _atomic_json(output_dir / "progress.json", progress)


def _authorization_claim(
    preflight: Mapping[str, Any],
    progress: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "av-trace.granite-v2-one-run-claim/1.0",
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
        "load_status": str(LoadStatus.LOADED_VERIFIED),
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
        "schema_version": "av-trace.granite-adapter-v2-run-manifest/1.0",
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
        "frozen_prompt_policy_sha256": progress["prompt_policy_sha256"],
        "private_evaluation_executed_at_seal_time": False,
        "independent_audit": (
            "scripts/audit_granite_adapter_v2_holdout_run.py"
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


def _restoration_isolation_checks(run_id: str) -> list[dict[str, Any]]:
    checkpoint = {
        "event_type": "protocol_checkpoint",
        "event_version": "2.0.0",
        "message": "Scheduled protocol checkpoint completed.",
        "cost": 0.0,
    }
    prefix_hash = sha256_json(checkpoint)

    def attestation(arm: str) -> dict[str, str]:
        return {
            "provider_session_id": f"{run_id}.{arm}.provider",
            "model_cache_namespace": f"{run_id}.{arm}.model",
            "retrieval_cache_namespace": f"{run_id}.{arm}.retrieval",
            "tool_cache_namespace": f"{run_id}.{arm}.tool",
            "artifact_namespace": f"{run_id}.{arm}.artifact",
            "generated_memory_namespace": f"{run_id}.{arm}.memory",
        }

    return [
        {
            "restored": {
                "isolation_attestation": attestation("restored"),
                "public_prefix_hash_through_checkpoint": prefix_hash,
            },
            "no_trigger": {
                "isolation_attestation": attestation("no-trigger"),
                "public_prefix_hash_through_checkpoint": prefix_hash,
            },
        }
    ]


def _execute_child(root: Path, output_dir: Path, *, resume: bool) -> None:
    resource.setrlimit(
        resource.RLIMIT_AS,
        (ADDRESS_SPACE_LIMIT_BYTES, ADDRESS_SPACE_LIMIT_BYTES),
    )
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    _offline_environment()
    public, preflight = _preflight(root, output_dir, execution_mode=True)
    prompt_policy = _load_json(root / HOLDOUT_DIR / "prompt_policy.json")
    if sha256_json(prompt_policy) != public["prompt_policy"]["sha256"]:
        raise HoldoutRunError("PROMPT_POLICY_SEMANTIC_HASH_MISMATCH")
    controller_binding = _binding(public["binding"]["controller"])
    finalizer_binding = _binding(public["binding"]["finalizer"])

    output_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(output_dir, 0o700)
    seal_path = output_dir / "seal.json"
    if seal_path.exists():
        raise HoldoutRunError("RUN_ALREADY_SEALED_DO_NOT_RESTART")
    progress_path = output_dir / "progress.json"
    authorization_path = output_dir / "authorization_claim.json"
    preflight_path = output_dir / "preflight_report.json"
    if progress_path.exists():
        if not resume:
            raise HoldoutRunError("UNSEALED_RUN_EXISTS_RESUME_ONLY")
        if not authorization_path.is_file():
            raise HoldoutRunError("RESUME_AUTHORIZATION_CLAIM_MISSING")
        progress = _load_json(progress_path)
        _validate_progress(progress, public, preflight)
        _resolve_interrupted_factor(progress, output_dir)
    else:
        if resume:
            raise HoldoutRunError("RESUME_REQUESTED_WITHOUT_PROGRESS")
        if authorization_path.exists():
            raise HoldoutRunError("AUTHORIZATION_ALREADY_CLAIMED")
        progress = _new_progress(
            public,
            preflight,
            controller_binding,
            finalizer_binding,
        )
        _atomic_json(preflight_path, preflight)
        _atomic_json(
            authorization_path,
            _authorization_claim(preflight, progress),
        )
        _atomic_json(progress_path, progress)

    import numpy as np

    if "long" not in np.__dict__:
        np.long = np.int64  # type: ignore[attr-defined]
    if "ulong" not in np.__dict__:
        np.ulong = np.uint64  # type: ignore[attr-defined]
    import torch
    import transformers
    from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer

    torch.manual_seed(TASK_ID)
    torch.set_num_threads(THREADS)
    with contextlib.suppress(RuntimeError):
        torch.set_num_interop_threads(1)
    if torch.cuda.is_available() or torch.cuda.device_count() != 0:
        raise HoldoutRunError("GPU_VISIBLE_IN_CPU_ONLY_RUN")

    started = time.perf_counter()
    completed_ids = {row["case_id"] for row in progress["results"]}
    substantive_missing = [
        case
        for case in public["cases"]
        if case["case_type"] in {"controller", "finalizer"}
        and case["case_id"] not in completed_ids
    ]
    tokenizer = None
    model = None
    config = None
    tokenizer_seconds = 0.0
    model_seconds = 0.0
    with _network_denial() as network_attempts:
        if substantive_missing:
            snapshot = root / SNAPSHOT
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
            if str(parameter.device) != "cpu":
                raise HoldoutRunError("MODEL_NOT_ON_CPU")
            if str(parameter.dtype) != "torch.bfloat16":
                raise HoldoutRunError("MODEL_DTYPE_MISMATCH")
            observed_controller = ModelBinding(
                repo_id=MODEL_REPO_ID,
                revision=MODEL_REVISION,
                role=controller_binding.role,
                processor_revision=MODEL_REVISION,
                tokenizer_revision=MODEL_REVISION,
            )
            observed_finalizer = ModelBinding(
                repo_id=MODEL_REPO_ID,
                revision=MODEL_REVISION,
                role=finalizer_binding.role,
                processor_revision=MODEL_REVISION,
                tokenizer_revision=MODEL_REVISION,
            )
            require_exact_binding(
                controller_binding,
                observed_controller,
                load_status=LoadStatus.LOADED_VERIFIED,
            )
            require_exact_binding(
                finalizer_binding,
                observed_finalizer,
                load_status=LoadStatus.LOADED_VERIFIED,
            )

        for position, case in enumerate(public["cases"], 1):
            if case["case_id"] in completed_ids:
                continue
            case_started = time.perf_counter()
            if case["case_type"] in {"controller", "finalizer"}:
                if tokenizer is None or model is None:
                    raise HoldoutRunError("MODEL_NOT_LOADED")
                for factor_name in _factor_names(case):
                    _complete_factor(
                        root=root,
                        output_dir=output_dir,
                        progress=progress,
                        case=case,
                        factor_name=factor_name,
                        prompt_policy=prompt_policy,
                        tokenizer=tokenizer,
                        model=model,
                        torch=torch,
                    )
                row = _assemble_substantive_result(case, progress)
            else:
                row, attempts = _runtime_fixture(case, controller_binding)
                progress["attempts"].extend(attempts)
            row["wall_seconds"] = time.perf_counter() - case_started
            progress["results"].append(row)
            progress["last_completed_case_id"] = case["case_id"]
            progress["last_completed_at"] = utc_now()
            _atomic_json(progress_path, progress)
            print(
                f"[{position:02d}/51] {case['case_id']} "
                f"{row['inference_status']} "
                f"calls={row['model_calls_used']} "
                f"seconds={row['wall_seconds']:.3f}",
                flush=True,
            )

        runtime = {
            "python": sys.version.split()[0],
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "threads": torch.get_num_threads(),
            "interop_threads": torch.get_num_interop_threads(),
            "device": "cpu",
            "dtype": "torch.bfloat16",
            "cuda_available": torch.cuda.is_available(),
            "cuda_device_count": torch.cuda.device_count(),
            "model_class": type(model).__name__ if model is not None else None,
            "tokenizer_class": (
                type(tokenizer).__name__ if tokenizer is not None else None
            ),
            "config_model_type": (
                getattr(config, "model_type", None)
                if config is not None
                else None
            ),
            "tokenizer_load_seconds": tokenizer_seconds,
            "model_load_seconds": model_seconds,
            "elapsed_seconds_this_process": time.perf_counter() - started,
            "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "network_attempts": network_attempts["count"],
            "local_files_only": True,
            "trust_remote_code": False,
        }
        if network_attempts["count"] != 0:
            raise HoldoutRunError("NETWORK_ATTEMPT_DURING_RUN")
        progress["status"] = "COMPLETE_UNEVALUATED"
        progress["runtime"] = runtime
        _atomic_json(progress_path, progress)
        seal = _write_sealed_run(
            root,
            output_dir,
            public,
            progress,
            runtime=runtime,
        )
        print(
            json.dumps(
                {
                    "status": "SEALED_UNEVALUATED",
                    "run_id": progress["run_id"],
                    "seal_sha256": _sha256_file(output_dir / "seal.json"),
                    "sealed_files": sorted(seal["files"]),
                },
                sort_keys=True,
            ),
            flush=True,
        )


def verify_run_seal(output_dir: Path) -> dict[str, Any]:
    seal_path = output_dir / "seal.json"
    if not seal_path.is_file():
        raise HoldoutRunError("SEALED_RUN_NOT_FOUND")
    seal = _load_json(seal_path)
    if (
        seal.get("schema_version") != RUN_SEAL_SCHEMA
        or seal.get("task_id") != TASK_ID
        or seal.get("suite_id") != SUITE_ID
        or seal.get("state") != "SEALED_BEFORE_PRIVATE_EVALUATION"
        or set(seal.get("files", {})) != set(SEALED_RUN_FILES)
    ):
        raise HoldoutRunError("RUN_SEAL_INVALID")
    for name, expected in seal["files"].items():
        path = output_dir / name
        if (
            not path.is_file()
            or path.stat().st_size != expected["bytes"]
            or _sha256_file(path) != expected["sha256"]
        ):
            raise HoldoutRunError(f"SEALED_RUN_ARTIFACT_MISMATCH:{name}")
    return seal


def _private_exposure(raw: str | None) -> bool:
    if not isinstance(raw, str):
        return False
    try:
        parsed = parse_strict_json(raw, maximum_bytes=64_000)
        assert_public_surface(parsed)
    except SchemaViolation as exc:
        if exc.code in {
            "EVALUATOR_PRIVATE_FIELD_EXPOSED",
            "PRIVATE_IDENTIFIER_EXPOSED",
        }:
            return True
    folded = raw.casefold()
    if any(f'"{key.casefold()}"' in folded for key in FORBIDDEN_PRIVATE_KEYS):
        return True
    return any(pattern.search(raw) for pattern in PRIVATE_IDENTIFIER_PATTERNS)


def _fraction(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _attempt_map(
    attempts: Sequence[Mapping[str, Any]],
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    mapped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in attempts:
        mapped[(str(record["case_id"]), str(record["factor_name"]))].append(
            dict(record)
        )
    for records in mapped.values():
        records.sort(key=lambda row: int(row["attempt_index"]))
    return mapped


def _controller_replay(
    case: Mapping[str, Any],
    attempts: Mapping[tuple[str, str], Sequence[Mapping[str, Any]]],
) -> Any:
    return parse_controller_factors(
        action_menu=case["public_input"]["action_menu"],
        claim_handles=_claim_handles(case),
        observed_evidence=case["public_input"]["observed_evidence"],
        action_attempts=_attempt_objects(
            attempts.get((str(case["case_id"]), "action_choice"), [])
        ),
        evidence_state_attempts=_attempt_objects(
            attempts.get((str(case["case_id"]), "evidence_state"), [])
        ),
    )


def _finalizer_replay(
    case: Mapping[str, Any],
    attempts: Mapping[tuple[str, str], Sequence[Mapping[str, Any]]],
) -> Any:
    return parse_finalizer_factors(
        claim_handles=_claim_handles(case),
        observations=case["public_input"]["observed_evidence"],
        attempts_by_factor={
            name: _attempt_objects(
                attempts.get((str(case["case_id"]), name), [])
            )
            for name in _factor_names(case)
        },
    )


def _score_finalizer(
    case: Mapping[str, Any],
    label: Mapping[str, Any],
    result: Any,
) -> dict[str, Any]:
    if result.canonical_envelope is None:
        return {
            "structured_valid": False,
            "semantic_success": False,
            "unsupported_claims": 0,
            "answer_mode_correct": False,
            "error_code": result.projection_error_code,
        }
    envelope = result.canonical_envelope
    final = envelope["final_answer"]
    answer_mode_correct = final["answer_mode"] == label["answer_mode"]
    unsupported = 0
    if label["answer_mode"] == "abstain":
        diagnosis = final["diagnosis"]
        semantic = (
            answer_mode_correct
            and label["required_missing_modality"]
            in {
                modality
                for modality, probability in diagnosis[
                    "modality_probabilities"
                ].items()
                if probability >= 0.5
            }
            and label["required_missing_hop"] in diagnosis["hop_types"]
        )
    else:
        claims = {
            claim["registered_claim_id"]: claim
            for claim in final["claims"]
        }
        for handle, terms in label["required_terms_by_claim"].items():
            claim = claims.get(handle)
            if claim is None:
                unsupported += 1
                continue
            text = claim["text"].casefold()
            if any(str(term).casefold() not in text for term in terms):
                unsupported += 1
            citations = {
                item["observation_id"] for item in claim["citations"]
            }
            if (
                not citations
                or not citations
                <= set(label["accepted_support"].get(handle, []))
            ):
                unsupported += 1
        semantic = answer_mode_correct and unsupported == 0
    return {
        "structured_valid": True,
        "semantic_success": semantic,
        "unsupported_claims": unsupported,
        "answer_mode_correct": answer_mode_correct,
        "parsed_output_sha256": sha256_json(envelope),
        "error_code": None,
    }


def _score_runtime(
    case: Mapping[str, Any],
    label: Mapping[str, Any],
    row: Mapping[str, Any],
    attempts: Mapping[tuple[str, str], Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    fixture = str(case["stratum"])
    pass_common = (
        row.get("inference_status") == label["expected_inference_status"]
        and row.get("model_was_called") is label["expected_model_called"]
        and row.get("structured_output") is None
        and row.get("final_answer") is None
    )
    detail_pass = True
    if fixture.startswith("malformed_"):
        records = [
            record
            for (case_id, _), rows in attempts.items()
            if case_id == case["case_id"]
            for record in rows
        ]
        detail_pass = (
            len(records) == 2
            and records[1]["kind"] == "schema_only_retry"
            and all(
                record.get("raw_output") == "{not valid json"
                for record in records
            )
        )
    elif fixture == "cross_factor_semantic_retry":
        detail_pass = (
            row.get("error_code") == "SCHEMA_RETRY_CHANGED_CONTENT"
            and row.get("schema_repairs_used") == 1
        )
    elif fixture in {"wrong_snapshot", "budget_exhausted"}:
        detail_pass = row.get("model_calls_used") == 0
    return {
        "structured_valid": None,
        "failure_fixture_pass": bool(pass_common and detail_pass),
        "identity_or_injected_failure_pass": bool(
            pass_common and detail_pass
        ),
        "error_code": None if pass_common and detail_pass else "FIXTURE_FAILED",
    }


def evaluate_payload(
    *,
    public: Mapping[str, Any],
    private: Mapping[str, Any],
    submission: Mapping[str, Any],
    raw_attempts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Frozen Task-177 private evaluator; performs no model inference."""

    if (
        public.get("suite_id") != SUITE_ID
        or private.get("suite_id") != SUITE_ID
        or submission.get("suite_id") != SUITE_ID
    ):
        raise HoldoutRunError("EVALUATION_SUITE_ID_MISMATCH")
    if submission.get("public_suite_sha256") != _sha256_file(
        ROOT / HOLDOUT_DIR / "public_suite.json"
    ):
        raise HoldoutRunError("EVALUATION_PUBLIC_SUITE_HASH_MISMATCH")
    labels = private.get("labels")
    if not isinstance(labels, Mapping):
        raise HoldoutRunError("PRIVATE_LABELS_INVALID")
    expected_ids = {case["case_id"] for case in public["cases"]}
    if set(labels) != expected_ids:
        raise HoldoutRunError("PRIVATE_LABEL_CASE_SET_MISMATCH")
    results = submission.get("results")
    if not isinstance(results, list):
        raise HoldoutRunError("SUBMISSION_RESULTS_INVALID")
    by_id = {str(row.get("case_id")): row for row in results}
    if set(by_id) != expected_ids or len(by_id) != len(results):
        raise HoldoutRunError("SUBMISSION_CASE_SET_MISMATCH")
    if submission.get("adapter_schema_version") != ADAPTER_SCHEMA_VERSION:
        raise HoldoutRunError("SUBMISSION_ADAPTER_VERSION_MISMATCH")
    if submission.get("load_status") != str(LoadStatus.LOADED_VERIFIED):
        raise HoldoutRunError("SUBMISSION_LOAD_NOT_VERIFIED")
    if (
        submission.get("observed_controller_binding")
        != public["binding"]["controller"]
        or submission.get("observed_finalizer_binding")
        != public["binding"]["finalizer"]
    ):
        raise HoldoutRunError("SUBMISSION_BINDING_MISMATCH")

    attempts = _attempt_map(raw_attempts)
    scores: list[dict[str, Any]] = []
    private_exposures = 0
    substitutions = 0
    for case in public["cases"]:
        case_id = str(case["case_id"])
        row = by_id[case_id]
        label = labels[case_id]
        case_attempts = [
            record
            for (attempt_case_id, _), records in attempts.items()
            if attempt_case_id == case_id
            for record in records
        ]
        exposure = any(
            _private_exposure(record.get("raw_output"))
            for record in case_attempts
        )
        private_exposures += int(exposure)
        substitution = bool(row.get("deterministic_answer_substitution"))
        substitutions += int(substitution)
        if case["case_type"] == "controller":
            replay = _controller_replay(case, attempts)
            action_valid = (
                replay.action_factor.status is FactorStatus.VALID
                and replay.native_action is not None
            )
            state_valid = (
                replay.evidence_state_factor.status is FactorStatus.VALID
                and isinstance(replay.evidence_state_factor.value, Mapping)
            )
            expected_state = label["expected_evidence_state"]
            state_components = {
                field: bool(
                    state_valid
                    and replay.evidence_state_factor.value[field]
                    == expected_state[field]
                )
                for field in EVIDENCE_STATE_FIELDS
            }
            structured = bool(
                action_valid
                and state_valid
                and replay.state_projection.status
                is ProjectionStatus.ACCEPTED
                and replay.canonical_decision is not None
            )
            action_correct = bool(
                action_valid
                and replay.native_action.action_index
                == label["expected_action_index"]
            )
            score = {
                "structured_valid": structured,
                "action_factor_valid": action_valid,
                "action_correct": action_correct,
                "state_factor_valid": state_valid,
                "state_projection_accepted": (
                    replay.state_projection.status
                    is ProjectionStatus.ACCEPTED
                ),
                "state_component_correct": state_components,
                "exact_six_field_state": all(state_components.values()),
                "restoration_reacquisition_success": (
                    action_correct
                    if label.get("restoration_reacquisition")
                    else None
                ),
                "error_code": (
                    None
                    if structured
                    else replay.state_projection.error_code
                    or replay.evidence_state_factor.error_code
                    or replay.action_factor.error_code
                ),
            }
        elif case["case_type"] == "finalizer":
            replay = _finalizer_replay(case, attempts)
            score = _score_finalizer(case, label, replay)
        else:
            score = _score_runtime(case, label, row, attempts)
        scores.append(
            {
                "case_id": case_id,
                "case_type": case["case_type"],
                "stratum": case["stratum"],
                "private_exposure": exposure,
                "deterministic_answer_substitution": substitution,
                **score,
            }
        )

    controllers = [row for row in scores if row["case_type"] == "controller"]
    finalizers = [row for row in scores if row["case_type"] == "finalizer"]
    fixtures = [
        row for row in scores if row["case_type"] == "runtime_failure"
    ]
    substantive = controllers + finalizers
    controller_cases = {
        case["case_id"]: case
        for case in public["cases"]
        if case["case_type"] == "controller"
    }
    finalizer_cases = {
        case["case_id"]: case
        for case in public["cases"]
        if case["case_type"] == "finalizer"
    }
    action_strata: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in controllers:
        action_strata[str(row["stratum"])].append(row)
    state_components = {
        field: _fraction(
            sum(bool(row["state_component_correct"][field]) for row in controllers),
            len(controllers),
        )
        for field in EVIDENCE_STATE_FIELDS
    }
    oracle = [
        row
        for row in finalizers
        if labels[row["case_id"]].get("oracle_complete")
    ]
    blocked = [
        row for row in finalizers if row["stratum"] == "blocked_partial"
    ]
    restoration = [
        row
        for row in controllers + finalizers
        if labels[row["case_id"]].get("restoration_reacquisition")
    ]
    restoration_successes = sum(
        bool(
            row.get("semantic_success")
            or row.get("restoration_reacquisition_success")
        )
        for row in restoration
    )
    unsupported_claims = sum(
        int(row.get("unsupported_claims", 0)) for row in finalizers
    )
    metrics = {
        "case_count": len(scores),
        "substantive_case_count": len(substantive),
        "deterministic_parser_schema_failure_fixtures": _fraction(
            sum(bool(row["failure_fixture_pass"]) for row in fixtures),
            len(fixtures),
        ),
        "valid_structured_model_calls": _fraction(
            sum(bool(row["structured_valid"]) for row in substantive),
            len(substantive),
        ),
        "correct_first_actions_overall": _fraction(
            sum(bool(row["action_correct"]) for row in controllers),
            len(controllers),
        ),
        "correct_first_actions_by_stratum": {
            stratum: _fraction(
                sum(bool(row["action_correct"]) for row in rows),
                len(rows),
            )
            for stratum, rows in sorted(action_strata.items())
        },
        "exact_six_field_state": _fraction(
            sum(bool(row["exact_six_field_state"]) for row in controllers),
            len(controllers),
        ),
        "state_component_accuracy": state_components,
        "oracle_supported_answer": _fraction(
            sum(bool(row["semantic_success"]) for row in oracle),
            len(oracle),
        ),
        "blocked_partial_correct_abstention": _fraction(
            sum(bool(row["semantic_success"]) for row in blocked),
            len(blocked),
        ),
        "restoration_reacquisition": _fraction(
            restoration_successes,
            len(restoration),
        ),
        "unsupported_required_claims": unsupported_claims,
        "private_field_exposures": private_exposures,
        "deterministic_answer_substitutions": substitutions,
        "identity_and_injected_failure_fail_closed": _fraction(
            sum(
                bool(row["identity_or_injected_failure_pass"])
                for row in fixtures
            ),
            len(fixtures),
        ),
        "cross_state_isolation_failures": _isolation_failures(
            submission.get("restoration_isolation_checks", [])
        ),
        "controller_case_count": len(controller_cases),
        "finalizer_case_count": len(finalizer_cases),
    }
    thresholds = public["thresholds"]
    checks = {
        "minimum_cases": metrics["case_count"] >= thresholds["minimum_cases"],
        "failure_fixtures": metrics[
            "deterministic_parser_schema_failure_fixtures"
        ]
        == thresholds["deterministic_parser_schema_failure_fixtures"],
        "valid_structured": metrics["valid_structured_model_calls"] is not None
        and metrics["valid_structured_model_calls"]
        >= thresholds["valid_structured_model_calls_min"],
        "actions_overall": metrics["correct_first_actions_overall"] is not None
        and metrics["correct_first_actions_overall"]
        >= thresholds["correct_first_actions_overall_min"],
        "actions_each_stratum": all(
            value is not None
            and value >= thresholds["correct_first_actions_each_stratum_min"]
            for value in metrics["correct_first_actions_by_stratum"].values()
        ),
        "joint_state": metrics["exact_six_field_state"] is not None
        and metrics["exact_six_field_state"]
        >= thresholds["exact_six_field_state_min"],
        "state_components": all(
            value is not None
            and value >= thresholds["each_state_component_min"]
            for value in state_components.values()
        ),
        "oracle": metrics["oracle_supported_answer"] is not None
        and metrics["oracle_supported_answer"]
        >= thresholds["oracle_supported_answer_min"],
        "blocked_partial": metrics[
            "blocked_partial_correct_abstention"
        ]
        is not None
        and metrics["blocked_partial_correct_abstention"]
        >= thresholds["blocked_partial_correct_abstention_min"],
        "restoration": metrics["restoration_reacquisition"] is not None
        and metrics["restoration_reacquisition"]
        >= thresholds["restoration_reacquisition_min"],
        "unsupported_claims": unsupported_claims
        <= thresholds["unsupported_required_claims_max"],
        "private_exposure": private_exposures
        <= thresholds["private_field_exposures_max"],
        "no_substitution": substitutions
        <= thresholds["deterministic_answer_substitutions_max"],
        "fail_closed": metrics[
            "identity_and_injected_failure_fail_closed"
        ]
        == thresholds["identity_and_injected_failure_fail_closed"],
        "cross_state_isolation": metrics[
            "cross_state_isolation_failures"
        ]
        == 0,
    }
    integrity_names = {
        "minimum_cases",
        "failure_fixtures",
        "unsupported_claims",
        "private_exposure",
        "no_substitution",
        "fail_closed",
        "cross_state_isolation",
    }
    competence_names = set(checks) - integrity_names
    if all(checks.values()):
        disposition = "GO"
    elif any(not checks[name] for name in integrity_names):
        disposition = "NO_GO"
    elif sum(not checks[name] for name in competence_names) <= 1:
        disposition = "REPAIR"
    else:
        disposition = "NO_GO"
    return {
        "schema_version": EVALUATOR_SCHEMA,
        "task_id": TASK_ID,
        "suite_id": SUITE_ID,
        "freeze_label": FREEZE_LABEL,
        "run_id": submission["run_id"],
        "evaluated_at": utc_now(),
        "thresholds": thresholds,
        "metrics": metrics,
        "gate_checks": checks,
        "decision": f"GRANITE_ADAPTER_V2_HOLDOUT_{disposition}",
        "case_scores": scores,
        "model_inference_executed_by_evaluator": False,
        "private_key_loaded_only_after_run_seal_verification": True,
    }


def _isolation_failures(checks: Any) -> int:
    if not isinstance(checks, list) or not checks:
        return 1
    failures = 0
    fields = (
        "provider_session_id",
        "model_cache_namespace",
        "retrieval_cache_namespace",
        "tool_cache_namespace",
        "artifact_namespace",
        "generated_memory_namespace",
    )
    for check in checks:
        try:
            restored = check["restored"]
            no_trigger = check["no_trigger"]
            if (
                restored["public_prefix_hash_through_checkpoint"]
                != no_trigger["public_prefix_hash_through_checkpoint"]
            ):
                failures += 1
                continue
            if any(
                restored["isolation_attestation"][field]
                == no_trigger["isolation_attestation"][field]
                for field in fields
            ):
                failures += 1
        except (KeyError, TypeError):
            failures += 1
    return failures


def _evaluate_sealed(root: Path, output_dir: Path) -> dict[str, Any]:
    seal = verify_run_seal(output_dir)
    if (output_dir / "evaluator_report.json").exists():
        raise HoldoutRunError("EVALUATION_ALREADY_EXISTS_DO_NOT_RERUN")
    # Revalidate Task-176 artifacts before opening the private key.
    public, _ = _preflight(root, output_dir, execution_mode=False)
    if _sha256_file(root / HOLDOUT_DIR / "freeze_seal.json") != _load_json(
        output_dir / "preflight_report.json"
    )["freeze_seal_sha256"]:
        raise HoldoutRunError("POST_RUN_FREEZE_SEAL_MISMATCH")
    submission = _load_json(output_dir / "submission.json")
    attempts = _load_jsonl(output_dir / "raw_attempts.jsonl")
    private = _load_json(root / HOLDOUT_DIR / "private_labels.json")
    report = evaluate_payload(
        public=public,
        private=private,
        submission=submission,
        raw_attempts=attempts,
    )
    _atomic_json(output_dir / "evaluator_report.json", report, mode=0o400)
    pending = {
        "schema_version": EVALUATION_SEAL_SCHEMA,
        "task_id": TASK_ID,
        "run_id": seal["run_id"],
        "evaluated_at": utc_now(),
        "state": "EVALUATED_AWAITING_INDEPENDENT_AUDIT",
        "sealed_input_verified": True,
        "input_seal_sha256": _sha256_file(output_dir / "seal.json"),
        "evaluator_report": {
            "sha256": _sha256_file(output_dir / "evaluator_report.json"),
            "bytes": (output_dir / "evaluator_report.json").stat().st_size,
        },
        "decision": report["decision"],
        "deterministic_replay_count_completed": 0,
    }
    _atomic_json(
        output_dir / "evaluation_pending_audit.json",
        pending,
        mode=0o400,
    )
    return report


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
            "Execute/evaluate the one authorized Granite adapter-v2 holdout."
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
