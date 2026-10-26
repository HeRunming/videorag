#!/usr/bin/env python3
"""Task 172 governed CPU-only Granite competence execution.

The runner has two deliberately separate phases:

* ``--execute`` records all controller/finalizer outputs and runtime fixtures,
  writes the evaluator submission, and seals those artifacts.
* ``--evaluate`` first verifies the seal and only then invokes the frozen
  Task-158 evaluator.

The direct-A/V group is recorded as structurally ineligible for this text-only
Granite snapshot. It is never converted into zero-valued score rows.
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
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from av_trace_strong_baselines.competence import (
    evaluate_competence_submission,
    load_submission,
    load_suite,
    model_public_case,
)
from av_trace_strong_baselines.contracts import (
    BudgetLedger,
    InferenceStatus,
    LoadStatus,
    ModelBinding,
    require_exact_binding,
    sha256_json,
)
from av_trace_strong_baselines.errors import (
    SchemaViolation,
    StrongBaselineError,
)
from av_trace_strong_baselines.runtime import (
    SCHEMA_REPAIRABLE_ERRORS,
    DriverResponse,
    GenerationRequest,
    invoke_fail_closed,
)
from av_trace_strong_baselines.schemas import (
    EVIDENCE_STATE_FIELDS,
    parse_strict_json,
    validate_evidence_state,
    validate_final_answer_envelope,
)
from av_trace_strong_baselines.security import (
    ObservedEvidenceLock,
    OutputProvenance,
    assert_public_surface,
)
from tools import granite33_8b_acquisition as acquisition

TASK_ID = 172
RUNNER_SCHEMA = "av-trace.granite33-competence-runner/1.0"
SUBMISSION_SCHEMA = "av-trace.strong-baseline-competence-submission/1.0"
SEAL_SCHEMA = "av-trace.strong-baseline-run-seal/1.0"
AUDIT_SCHEMA = "av-trace.granite33-competence-independent-audit/1.0"
SUITE = Path("data/rehearsal_plan/strong_baseline_competence_suite_v1.json")
OUTPUT_DIR = Path(
    "data/restricted/strong_baselines/granite33_competence_v1"
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
MODEL_REPO_ID = "ibm-granite/granite-3.3-8b-instruct"
MODEL_REVISION = "51dd4bc2ade4059a6bd87649d68aa11e4fb2529b"
THREADS = 8
MAX_NEW_TOKENS = 512
CONTEXT_CAP = 32_768
SCHEMA_RETRIES = 1
ADDRESS_SPACE_LIMIT_BYTES = 48 * 1024**3
WHOLE_RUN_TIMEOUT_SECONDS = 6 * 60 * 60
EXPECTED_COUNTS = {
    "controller": 24,
    "finalizer": 16,
    "runtime_failure": 11,
}
TERMINAL_STRATA = {
    "no_progress_guard",
    "no_trigger",
    "finalize_ready",
}
SEALED_ARTIFACTS = (
    "submission.json",
    "raw_attempts.jsonl",
    "run_metadata.json",
    "direct_av_eligibility.json",
    "runner_manifest.json",
)
SCHEMA_ONLY_ERRORS = SCHEMA_REPAIRABLE_ERRORS | {
    "COVERED_CLAIMS_TYPE",
    "MISSING_MODALITIES_TYPE",
    "MISSING_HOPS_TYPE",
}


class CompetenceRunError(RuntimeError):
    """Fail-closed Task-172 runner error."""


def utc_now() -> str:
    return (
        datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_file(path: Path, block_size: int = 8 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(block_size):
            digest.update(chunk)
    return digest.hexdigest()


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


def _atomic_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    payload = "".join(
        json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n"
        for row in rows
    )
    _atomic_bytes(path, payload.encode("utf-8"))


def _binding(value: Mapping[str, Any]) -> ModelBinding:
    return ModelBinding(
        repo_id=str(value["repo_id"]),
        revision=str(value["revision"]),
        role=str(value["role"]),
        processor_revision=str(value["processor_revision"]),
        tokenizer_revision=str(value["tokenizer_revision"]),
    )


def _validate_static_contract(
    root: Path,
) -> tuple[dict[str, Any], Path, ModelBinding, ModelBinding]:
    suite = load_suite(root / SUITE)
    if suite["suite_hash"] != (
        "sha256:7b8f8d021b24cb244f0df0f6b02b3da91120df3817a5366350895eb24f4646dc"
    ):
        raise CompetenceRunError("FROZEN_SUITE_HASH_MISMATCH")
    cases = suite["cases"]["controller_finalizer"]
    counts = Counter(str(case["case_type"]) for case in cases)
    if counts != EXPECTED_COUNTS:
        raise CompetenceRunError(
            f"CONTROLLER_FINALIZER_CASE_COUNTS_MISMATCH:{dict(counts)}"
        )
    if len(suite["cases"]["direct_av"]) != 30:
        raise CompetenceRunError("DIRECT_AV_CASE_COUNT_MISMATCH")
    if (
        sum(
            case["case_type"] == "direct_av"
            for case in suite["cases"]["direct_av"]
        )
        != 24
    ):
        raise CompetenceRunError("DIRECT_AV_SUBSTANTIVE_COUNT_MISMATCH")
    boundary = suite["content_boundary"]
    if boundary != {
        "fictional_generated_primitives_only": True,
        "public_cases_only": True,
        "contains_scientific_family_content": False,
        "contains_real_benchmark_ground_truth": False,
        "contains_evaluator_private_benchmark_fields": False,
        "model_inputs_are_allowlisted_from_public_input_only": True,
    }:
        raise CompetenceRunError("SUITE_CONTENT_BOUNDARY_MISMATCH")

    controller_binding = _binding(suite["bindings"]["primary_controller"])
    finalizer_binding = _binding(suite["bindings"]["primary_finalizer"])
    for expected in (controller_binding, finalizer_binding):
        if (
            expected.repo_id != MODEL_REPO_ID
            or expected.revision != MODEL_REVISION
            or expected.resolved_processor_revision != MODEL_REVISION
            or expected.resolved_tokenizer_revision != MODEL_REVISION
        ):
            raise CompetenceRunError("SUITE_GRANITE_BINDING_MISMATCH")
    if (
        controller_binding.repo_id,
        controller_binding.revision,
        controller_binding.resolved_processor_revision,
        controller_binding.resolved_tokenizer_revision,
    ) != (
        finalizer_binding.repo_id,
        finalizer_binding.revision,
        finalizer_binding.resolved_processor_revision,
        finalizer_binding.resolved_tokenizer_revision,
    ):
        raise CompetenceRunError("CONTROLLER_FINALIZER_BACKBONE_MISMATCH")

    snapshot = root / SNAPSHOT
    manifest = _load_json(root / ACQUISITION_MANIFEST)
    smoke = _load_json(root / SMOKE_REPORT)
    if manifest.get("decision") != "GRANITE33_8B_ACQUISITION_READY":
        raise CompetenceRunError("GRANITE_ACQUISITION_NOT_READY")
    if (
        smoke.get("status") != "LOAD_SMOKE_COMPLETE"
        or smoke.get("repo_id") != MODEL_REPO_ID
        or smoke.get("revision") != MODEL_REVISION
        or smoke.get("local_files_only") is not True
        or smoke.get("trust_remote_code") is not False
        or smoke.get("runtime", {}).get("threads") != THREADS
        or smoke.get("network_attempts") != 0
    ):
        raise CompetenceRunError("GRANITE_SMOKE_CONTRACT_MISMATCH")
    plan = _load_json(root / acquisition.PLAN)
    acquisition.validate_plan(plan)
    if (root / plan["model"]["snapshot_dir"]).resolve() != snapshot.resolve():
        raise CompetenceRunError("GRANITE_SNAPSHOT_PATH_MISMATCH")
    acquisition.validate_snapshot(plan, snapshot)
    return suite, snapshot, controller_binding, finalizer_binding


def _controller_system_prompt() -> str:
    return (
        "Return exactly one compact JSON object and no other text. The object "
        "must have exactly two keys: evidence_state and action_index. "
        "evidence_state must have exactly these six keys: p_sufficient, "
        "covered_claim_handles, missing_modalities, missing_hops, "
        "missingness_cause, recovery_intent. p_sufficient must be one of "
        "0,0.25,0.5,0.75,1. covered_claim_handles must contain only supplied "
        "claim_handle values. missing_modalities must be in canonical order "
        "from vision,speech,ambient. missing_hops must be in canonical order "
        "from entity_identity,event_detection,speech_content,ambient_event,"
        "temporal_order,cross_modal_binding,causal_link,state_change,"
        "comparison,counting,other. missingness_cause must be one of "
        "source_evidence_absent,evidence_in_source_but_inaccessible,"
        "evidence_accessible_but_not_found,not_missing,uncertain. "
        "recovery_intent must be one of none,search_vision,search_speech,"
        "search_ambient,observe_pointer,check_channel_status,"
        "retry_restored_route,finalize_answer,finalize_abstain. "
        "Choose action_index from the supplied action_menu in its displayed "
        "order. Use only public input. Never invent an answer or evidence. "
        "If observed evidence directly answers every claim, mark all claim "
        "handles covered, no missing modality or hop, p_sufficient 1, cause "
        "not_missing, intent finalize_answer, and select finalize. If a "
        "needed known pointer is present but unobserved, select inspect_clip "
        "and use vision,event_detection,observe_pointer. If recent history "
        "shows a needed channel unavailable, select get_channel_status and "
        "use evidence_in_source_but_inaccessible with the matching missing "
        "modality and hop. After a protocol checkpoint, if a matching search "
        "route is supplied, retry that route and use retry_restored_route. "
        "Otherwise select the search matching the requested modality: visual "
        "identity uses vision,entity_identity,search_vision; speech content "
        "uses speech,speech_content,search_speech; non-speech sound uses "
        "ambient,ambient_event,search_ambient. If no acquisition action is "
        "available and evidence is insufficient, select finalize with "
        "p_sufficient 0, evidence_accessible_but_not_found, and "
        "finalize_abstain; temporal ordering uses temporal_order. All list "
        "fields must be JSON arrays, including empty and one-item lists."
    )


def _finalizer_system_prompt() -> str:
    return (
        "Return exactly one compact JSON object and no other text. Use only "
        "the supplied public question, public_claim_slots, and "
        "observed_evidence. Never invent evidence, citations, or facts. The "
        "top-level object must contain exactly final_answer and "
        "claim_to_citations. final_answer must contain exactly p_sufficient,"
        "verdict,answer_mode,claims,diagnosis,natural_language_answer,"
        "termination_reason. Every claim must contain exactly claim_id,"
        "registered_claim_id,text,confidence,citations. Every citation must "
        "copy an observed observation_id, its exact start_s/end_s interval, "
        "and its exact modalities. claim_to_citations must exactly repeat the "
        "claim citation IDs. diagnosis must contain exactly "
        "modality_probabilities,hop_types,cause_probabilities,"
        "recovery_route_declared,description. modality_probabilities must "
        "contain vision,speech,ambient. cause_probabilities must contain "
        "source_evidence_absent,evidence_in_source_but_inaccessible,"
        "evidence_accessible_but_not_found,not_missing,uncertain. hop_types "
        "values are entity_identity,event_detection,speech_content,"
        "ambient_event,temporal_order,cross_modal_binding,causal_link,"
        "state_change,comparison,counting,other_registered. "
        "If observed evidence answers the question, use answer_mode answer, "
        "verdict sufficient, p_sufficient 1, termination_reason "
        "sufficient_evidence, one claim for each supplied claim_handle, and "
        "make both claim text and natural_language_answer state the factual "
        "answer from the observed payload. Use not_missing probability 1 and "
        "other cause probabilities 0. If no observed evidence supports the "
        "required fact, abstain: answer_mode abstain, verdict insufficient, "
        "p_sufficient 0, claims [], natural_language_answer empty, "
        "claim_to_citations {}, and termination_reason no_recovery_route. "
        "For abstention, diagnose the modality explicitly requested by the "
        "question at probability 1 and the matching hop: speech facts use "
        "speech_content, vision events use event_detection unless temporal "
        "order is requested, ambient facts use ambient_event. Use "
        "evidence_accessible_but_not_found probability 1 for this public "
        "fictional fixture. All other probabilities are 0."
    )


def _messages(case: Mapping[str, Any]) -> list[dict[str, str]]:
    public_case = model_public_case(case)
    if case["case_type"] == "controller":
        system = _controller_system_prompt()
    elif case["case_type"] == "finalizer":
        system = _finalizer_system_prompt()
    else:
        raise CompetenceRunError("MODEL_MESSAGES_REQUESTED_FOR_FIXTURE")
    messages = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": json.dumps(
                public_case,
                separators=(",", ":"),
                sort_keys=True,
                ensure_ascii=False,
            ),
        },
    ]
    assert_public_surface(messages)
    serialized = json.dumps(messages, sort_keys=True)
    forbidden = {
        "scoring_target",
        "expected_action_index",
        "expected_evidence_state",
        "required_terms_by_claim",
        "accepted_support",
    }
    if any(name in serialized for name in forbidden):
        raise CompetenceRunError("EVALUATOR_PRIVATE_PROMPT_FIELD")
    return messages


def _repair_messages(
    case: Mapping[str, Any],
    invalid_raw_output: str,
    validation_error_code: str,
) -> list[dict[str, str]]:
    if validation_error_code not in SCHEMA_ONLY_ERRORS:
        raise CompetenceRunError("NON_SCHEMA_REPAIR_REQUESTED")
    messages = _messages(case) + [
        {"role": "assistant", "content": invalid_raw_output},
        {
            "role": "user",
            "content": (
                "Schema-only repair. Return the same attempted content in "
                "exactly the required JSON structure, with no markdown or "
                "extra text. Do not add or change facts, claims, citations, "
                "answers, selected actions, evidence-state judgments, or "
                "diagnoses. Validation error code: "
                f"{validation_error_code}."
            ),
        },
    ]
    assert_public_surface(messages)
    return messages


def _semantic_atoms(value: Any, key: str = "$") -> list[tuple[str, Any]]:
    if isinstance(value, Mapping):
        atoms: list[tuple[str, Any]] = []
        for child_key, child in value.items():
            if child_key == "unit":
                continue
            atoms.extend(_semantic_atoms(child, str(child_key)))
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


def _validate_model_output(case: Mapping[str, Any], raw: str) -> dict[str, Any]:
    value = parse_strict_json(
        raw,
        maximum_bytes=8_192 if case["case_type"] == "controller" else 64_000,
    )
    public = case["public_input"]
    if case["case_type"] == "controller":
        if not isinstance(value, Mapping) or set(value) != {
            "evidence_state",
            "action_index",
        }:
            raise SchemaViolation("CONTROLLER_DECISION_FIELD_SET")
        action_index = value["action_index"]
        if (
            isinstance(action_index, bool)
            or not isinstance(action_index, int)
            or not 0 <= action_index < len(public["action_menu"])
        ):
            raise SchemaViolation("CONTROLLER_ACTION_INDEX_INVALID")
        state = validate_evidence_state(
            value["evidence_state"],
            allowed_claim_handles=[
                item["claim_handle"] for item in public["public_claim_slots"]
            ],
        )
        return {
            "evidence_state": state,
            "action_index": action_index,
        }
    if case["case_type"] == "finalizer":
        return validate_final_answer_envelope(
            value,
            claim_handles=[
                item["claim_handle"] for item in public["public_claim_slots"]
            ],
            evidence_lock=ObservedEvidenceLock(public["observed_evidence"]),
            provenance=OutputProvenance(
                model_authored_paths=frozenset({"final_answer"})
            ),
        )
    raise CompetenceRunError("UNSUPPORTED_SUBSTANTIVE_CASE_TYPE")


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


def _exception_status(exc: BaseException) -> InferenceStatus:
    if isinstance(exc, TimeoutError):
        return InferenceStatus.TIMEOUT
    if isinstance(exc, MemoryError):
        return InferenceStatus.OOM
    return InferenceStatus.PROVIDER_FAILURE


def _substantive_result(
    *,
    case: Mapping[str, Any],
    tokenizer: Any,
    model: Any,
    torch: Any,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    messages = _messages(case)
    attempts: list[dict[str, Any]] = []
    initial_raw: str | None = None
    final_raw: str | None = None
    parsed: dict[str, Any] | None = None
    final_error: str | None = None
    inference_status = InferenceStatus.INVALID_OUTPUT
    for attempt_index in range(1, 2 + SCHEMA_RETRIES):
        rendered = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            thinking=False,
        )
        inputs = tokenizer(rendered, return_tensors="pt")
        prompt_tokens = int(inputs["input_ids"].numel())
        if prompt_tokens > CONTEXT_CAP:
            inference_status = InferenceStatus.BUDGET_EXHAUSTED
            final_error = "CONTEXT_CAP_EXCEEDED"
            break
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
            raw = tokenizer.decode(
                output_ids,
                skip_special_tokens=True,
            ).strip()
        except (MemoryError, OSError, RuntimeError, TimeoutError, ValueError) as exc:
            elapsed = time.perf_counter() - started
            inference_status = _exception_status(exc)
            final_error = type(exc).__name__
            attempts.append(
                {
                    "case_id": case["case_id"],
                    "attempt": attempt_index,
                    "kind": (
                        "initial" if attempt_index == 1 else "schema_only"
                    ),
                    "prompt_sha256": "sha256:"
                    + hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": None,
                    "generation_seconds": elapsed,
                    "raw_output": None,
                    "inference_status": str(inference_status),
                    "error_code": final_error,
                }
            )
            break
        final_raw = raw
        if initial_raw is None:
            initial_raw = raw
        attempt = {
            "case_id": case["case_id"],
            "attempt": attempt_index,
            "kind": "initial" if attempt_index == 1 else "schema_only",
            "prompt_sha256": "sha256:"
            + hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": int(output_ids.numel()),
            "generation_seconds": elapsed,
            "raw_output": raw,
            "inference_status": str(InferenceStatus.VALID),
            "error_code": None,
        }
        attempts.append(attempt)
        try:
            parsed = _validate_model_output(case, raw)
            if (
                attempt_index > 1
                and initial_raw is not None
                and not _schema_retry_preserved_content(initial_raw, raw)
            ):
                parsed = None
                inference_status = InferenceStatus.INVALID_OUTPUT
                final_error = "SCHEMA_RETRY_CHANGED_SEMANTIC_CONTENT"
                attempt["inference_status"] = str(inference_status)
                attempt["error_code"] = final_error
                break
            inference_status = InferenceStatus.VALID
            final_error = None
            break
        except SchemaViolation as exc:
            parsed = None
            inference_status = InferenceStatus.INVALID_OUTPUT
            final_error = exc.code
            attempt["inference_status"] = str(inference_status)
            attempt["error_code"] = final_error
            if attempt_index >= 1 + SCHEMA_RETRIES:
                break
            if final_error not in SCHEMA_ONLY_ERRORS:
                break
            messages = _repair_messages(case, raw, final_error)

    row: dict[str, Any] = {
        "case_id": case["case_id"],
        "inference_status": str(inference_status),
        "schema_repairs_used": max(0, len(attempts) - 1),
        "repair_kind": "schema_only" if len(attempts) > 1 else "none",
        "model_calls_used": len(attempts),
        "model_was_called": bool(attempts),
        "error_code": final_error,
    }
    if final_raw is not None:
        row["raw_output"] = final_raw
    if case["case_type"] == "finalizer":
        row["output_provenance"] = {
            "model_authored_paths": ["final_answer"],
            "deterministic_paths": [],
            "copied_paths": [],
        }
    if parsed is not None:
        row["parsed_output_sha256"] = sha256_json(parsed)
    return row, attempts


class _InjectedDriver:
    def __init__(
        self,
        binding: ModelBinding,
        *,
        behavior: str,
        observed_binding: ModelBinding | None = None,
    ) -> None:
        self._binding = observed_binding or binding
        self._behavior = behavior
        self.calls = 0

    @property
    def observed_binding(self) -> ModelBinding:
        return self._binding

    @property
    def load_status(self) -> LoadStatus:
        return LoadStatus.LOADED_VERIFIED

    def generate(self, request: GenerationRequest) -> DriverResponse:
        self.calls += 1
        if self._behavior == "malformed_output":
            return DriverResponse(
                raw_output=b"{not valid json",
                inference_status=InferenceStatus.VALID,
            )
        if self._behavior == "provider_failure":
            raise RuntimeError("INJECTED_PROVIDER_FAILURE")
        if self._behavior == "timeout":
            raise TimeoutError("INJECTED_TIMEOUT")
        if self._behavior == "oom":
            raise MemoryError("INJECTED_OOM")
        raise AssertionError(self._behavior)


def _fixture_request(case: Mapping[str, Any]) -> GenerationRequest:
    public_case = model_public_case(case)
    return GenerationRequest(
        request_id=str(case["case_id"]),
        role="TOOL_CONTROLLER_BACKBONE",
        public_payload=public_case["public_input"],
        max_new_tokens=MAX_NEW_TOKENS,
        context_cap_processor_tokens=CONTEXT_CAP,
    )


def _runtime_fixture_result(
    case: Mapping[str, Any],
    expected_binding: ModelBinding,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    fixture = str(case["public_input"]["injected_public_fixture"])
    request = _fixture_request(case)
    attempts: list[dict[str, Any]] = []
    if fixture == "wrong_snapshot":
        wrong = ModelBinding(
            repo_id=expected_binding.repo_id,
            revision="0" * 40,
            role=expected_binding.role,
            processor_revision="0" * 40,
            tokenizer_revision="0" * 40,
        )
        driver = _InjectedDriver(
            expected_binding,
            behavior="malformed_output",
            observed_binding=wrong,
        )
        outcome = invoke_fail_closed(
            driver,
            expected_binding=expected_binding,
            request=request,
        )
        status = outcome.status
        model_called = outcome.model_was_called
        calls = driver.calls
        error_code = outcome.error_code
        repairs = 0
    elif fixture == "budget_exhausted":
        ledger = BudgetLedger()
        for _ in range(ledger.budget.max_model_invocations_including_repair):
            ledger.charge_model_call()
        try:
            ledger.charge_model_call()
        except StrongBaselineError as exc:
            if exc.code != "MODEL_CALL_BUDGET_EXHAUSTED":
                raise
            status = InferenceStatus.BUDGET_EXHAUSTED
            error_code = exc.code
        else:
            raise CompetenceRunError("BUDGET_FIXTURE_DID_NOT_FAIL")
        model_called = False
        calls = 0
        repairs = 0
    elif fixture == "process_failure":
        status = InferenceStatus.PROCESS_FAILURE
        model_called = True
        calls = 1
        repairs = 0
        error_code = "INJECTED_CHILD_PROCESS_FAILURE"
        attempts.append(
            {
                "case_id": case["case_id"],
                "attempt": 1,
                "kind": "injected_runtime_fixture",
                "raw_output": None,
                "inference_status": str(status),
                "error_code": error_code,
                "fixture_injected": True,
            }
        )
    else:
        driver = _InjectedDriver(expected_binding, behavior=fixture)
        outcome = invoke_fail_closed(
            driver,
            expected_binding=expected_binding,
            request=request,
        )
        if fixture == "malformed_output":
            raw = (outcome.raw_output or b"").decode("utf-8", errors="strict")
            try:
                parse_strict_json(raw, maximum_bytes=64_000)
            except SchemaViolation as exc:
                first_error = exc.code
            else:
                raise CompetenceRunError("MALFORMED_FIXTURE_PARSED")
            attempts.append(
                {
                    "case_id": case["case_id"],
                    "attempt": 1,
                    "kind": "injected_runtime_fixture",
                    "raw_output": raw,
                    "inference_status": str(InferenceStatus.INVALID_OUTPUT),
                    "error_code": first_error,
                    "fixture_injected": True,
                }
            )
            attempts.append(
                {
                    "case_id": case["case_id"],
                    "attempt": 2,
                    "kind": "schema_only",
                    "raw_output": raw,
                    "inference_status": str(InferenceStatus.INVALID_OUTPUT),
                    "error_code": first_error,
                    "fixture_injected": True,
                }
            )
            status = InferenceStatus.INVALID_OUTPUT
            model_called = True
            calls = 2
            repairs = 1
            error_code = first_error
        else:
            status = outcome.status
            model_called = outcome.model_was_called
            calls = driver.calls
            repairs = 0
            error_code = outcome.error_code
            attempts.append(
                {
                    "case_id": case["case_id"],
                    "attempt": 1,
                    "kind": "injected_runtime_fixture",
                    "raw_output": None,
                    "inference_status": str(status),
                    "error_code": error_code,
                    "fixture_injected": True,
                }
            )
    row: dict[str, Any] = {
        "case_id": case["case_id"],
        "inference_status": str(status),
        "model_was_called": model_called,
        "model_calls_used": calls,
        "schema_repairs_used": repairs,
        "repair_kind": "schema_only" if repairs else "none",
        "final_answer": None,
        "error_code": error_code,
        "fixture_injected": True,
    }
    if fixture == "malformed_output":
        row["raw_output"] = "{not valid json"
    return row, attempts


def _new_progress(
    suite: Mapping[str, Any],
    controller_binding: ModelBinding,
    finalizer_binding: ModelBinding,
) -> dict[str, Any]:
    run_id = f"task172-{utc_now()}-{uuid.uuid4().hex[:12]}"
    return {
        "schema_version": RUNNER_SCHEMA,
        "task_id": TASK_ID,
        "run_id": run_id,
        "started_at": utc_now(),
        "suite_hash": suite["suite_hash"],
        "controller_binding": controller_binding.to_dict(),
        "finalizer_binding": finalizer_binding.to_dict(),
        "runner_source_sha256": _sha256_file(Path(__file__)),
        "prompt_policy_sha256": sha256_json(
            {
                "controller": _controller_system_prompt(),
                "finalizer": _finalizer_system_prompt(),
            }
        ),
        "results": [],
        "attempts": [],
        "status": "RUNNING_UNSEALED",
    }


def _validate_progress(
    progress: Mapping[str, Any],
    suite: Mapping[str, Any],
    controller_binding: ModelBinding,
    finalizer_binding: ModelBinding,
) -> None:
    if (
        progress.get("schema_version") != RUNNER_SCHEMA
        or progress.get("suite_hash") != suite["suite_hash"]
        or progress.get("controller_binding") != controller_binding.to_dict()
        or progress.get("finalizer_binding") != finalizer_binding.to_dict()
        or progress.get("runner_source_sha256") != _sha256_file(Path(__file__))
        or progress.get("prompt_policy_sha256")
        != sha256_json(
            {
                "controller": _controller_system_prompt(),
                "finalizer": _finalizer_system_prompt(),
            }
        )
    ):
        raise CompetenceRunError("UNSEALED_PROGRESS_CONTRACT_MISMATCH")
    expected_ids = {
        case["case_id"]
        for case in suite["cases"]["controller_finalizer"]
    }
    result_ids = [row.get("case_id") for row in progress.get("results", [])]
    if len(result_ids) != len(set(result_ids)):
        raise CompetenceRunError("UNSEALED_PROGRESS_DUPLICATE_CASE")
    if not set(result_ids) <= expected_ids:
        raise CompetenceRunError("UNSEALED_PROGRESS_UNKNOWN_CASE")


def _restoration_isolation_check(run_id: str) -> list[dict[str, Any]]:
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


def _direct_av_eligibility(suite: Mapping[str, Any]) -> dict[str, Any]:
    rows = suite["cases"]["direct_av"]
    return {
        "schema_version": "av-trace.strong-baseline-eligibility/1.0",
        "suite_id": suite["suite_id"],
        "suite_hash": suite["suite_hash"],
        "suite_group": "direct_av",
        "candidate": {
            "repo_id": MODEL_REPO_ID,
            "revision": MODEL_REVISION,
            "model_kind": "text_only_causal_language_model",
        },
        "eligibility": "STRUCTURALLY_INELIGIBLE",
        "reason": (
            "The acquired Granite snapshot is the frozen text controller and "
            "grounded finalizer. It is not a native or packed audiovisual "
            "processor/model and cannot consume the direct-A/V exposure "
            "contract."
        ),
        "substantive_cases_present": sum(
            case["case_type"] == "direct_av" for case in rows
        ),
        "runtime_fixtures_present": sum(
            case["case_type"] == "runtime_failure" for case in rows
        ),
        "model_calls_executed": 0,
        "score_rows_created": 0,
        "scored_as_zero": False,
        "excluded_from_controller_finalizer_denominator": True,
    }


def _write_sealed_run(
    root: Path,
    output_dir: Path,
    suite: Mapping[str, Any],
    progress: dict[str, Any],
    *,
    runtime: Mapping[str, Any],
) -> dict[str, Any]:
    cases = suite["cases"]["controller_finalizer"]
    expected_ids = [case["case_id"] for case in cases]
    by_id = {row["case_id"]: row for row in progress["results"]}
    if set(by_id) != set(expected_ids):
        missing = sorted(set(expected_ids) - set(by_id))
        raise CompetenceRunError(f"CANNOT_SEAL_INCOMPLETE_RUN:{missing}")
    ordered_results = [by_id[case_id] for case_id in expected_ids]
    submission = {
        "schema_version": SUBMISSION_SCHEMA,
        "suite_hash": suite["suite_hash"],
        "suite_group": "controller_finalizer",
        "binding_key": "primary_controller",
        "load_status": str(LoadStatus.LOADED_VERIFIED),
        "observed_binding": suite["bindings"]["primary_controller"],
        "finalizer_binding_key": "primary_finalizer",
        "observed_finalizer_binding": suite["bindings"]["primary_finalizer"],
        "restoration_isolation_checks": _restoration_isolation_check(
            str(progress["run_id"])
        ),
        "results": ordered_results,
    }
    run_metadata = {
        "schema_version": RUNNER_SCHEMA,
        "task_id": TASK_ID,
        "run_id": progress["run_id"],
        "started_at": progress["started_at"],
        "completed_at": utc_now(),
        "execution_status": "COMPLETE_UNEVALUATED",
        "suite_id": suite["suite_id"],
        "suite_hash": suite["suite_hash"],
        "source_boundary": {
            "fictional_source_free_suite": True,
            "scientific_family_used": False,
            "evaluator_private_fields_exposed_to_model": False,
        },
        "governance": {
            "cpu_only": True,
            "gpu_or_api_used": False,
            "unrelated_ray_jobs_touched": False,
            "local_files_only": True,
            "trust_remote_code": False,
            "threads": THREADS,
            "max_new_tokens": MAX_NEW_TOKENS,
            "context_cap_tokens": CONTEXT_CAP,
            "schema_only_retries_per_case": SCHEMA_RETRIES,
            "semantic_repairs": 0,
            "answer_or_action_substitutions": 0,
            "raw_attempts_preserved": True,
            "sealed_before_evaluation": True,
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
            "substantive_total": (
                EXPECTED_COUNTS["controller"] + EXPECTED_COUNTS["finalizer"]
            ),
            "total": len(cases),
            "completed": len(ordered_results),
            "actual_model_generation_attempts": sum(
                1
                for attempt in progress["attempts"]
                if not attempt.get("fixture_injected")
            ),
            "injected_fixture_attempts": sum(
                1
                for attempt in progress["attempts"]
                if attempt.get("fixture_injected")
            ),
        },
        "runtime": dict(runtime),
        "runner_source_sha256": progress["runner_source_sha256"],
        "prompt_policy_sha256": progress["prompt_policy_sha256"],
    }
    runner_manifest = {
        "schema_version": "av-trace.granite33-competence-manifest/1.0",
        "task_id": TASK_ID,
        "run_id": progress["run_id"],
        "suite_hash": suite["suite_hash"],
        "runner_source": str(Path(__file__).relative_to(root)),
        "runner_source_sha256": progress["runner_source_sha256"],
        "frozen_evaluator": "scripts/evaluate_strong_baseline_competence.py",
        "frozen_evaluator_sha256": _sha256_file(
            root / "scripts/evaluate_strong_baseline_competence.py"
        ),
        "competence_module_sha256": _sha256_file(
            root / "src/av_trace_strong_baselines/competence.py"
        ),
        "evaluation_executed_at_seal_time": False,
        "direct_av_disposition": "STRUCTURALLY_INELIGIBLE_NOT_SCORED",
    }
    _atomic_json(output_dir / "submission.json", submission)
    _atomic_jsonl(output_dir / "raw_attempts.jsonl", progress["attempts"])
    _atomic_json(output_dir / "run_metadata.json", run_metadata)
    _atomic_json(
        output_dir / "direct_av_eligibility.json",
        _direct_av_eligibility(suite),
    )
    _atomic_json(output_dir / "runner_manifest.json", runner_manifest)
    seal = {
        "schema_version": SEAL_SCHEMA,
        "task_id": TASK_ID,
        "run_id": progress["run_id"],
        "sealed_at": utc_now(),
        "state": "SEALED_BEFORE_EVALUATION",
        "suite_hash": suite["suite_hash"],
        "files": {
            name: {
                "sha256": _sha256_file(output_dir / name),
                "bytes": (output_dir / name).stat().st_size,
            }
            for name in SEALED_ARTIFACTS
        },
    }
    _atomic_json(output_dir / "seal.json", seal, mode=0o400)
    for name in SEALED_ARTIFACTS:
        os.chmod(output_dir / name, 0o400)
    (output_dir / "progress.json").unlink(missing_ok=True)
    return seal


def _execute_child(root: Path, output_dir: Path, *, resume: bool) -> None:
    resource.setrlimit(
        resource.RLIMIT_AS,
        (ADDRESS_SPACE_LIMIT_BYTES, ADDRESS_SPACE_LIMIT_BYTES),
    )
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    _offline_environment()
    suite, snapshot, controller_binding, finalizer_binding = (
        _validate_static_contract(root)
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(output_dir, 0o700)
    seal_path = output_dir / "seal.json"
    if seal_path.exists():
        raise CompetenceRunError("RUN_ALREADY_SEALED")
    progress_path = output_dir / "progress.json"
    if progress_path.exists():
        if not resume:
            raise CompetenceRunError("UNSEALED_PROGRESS_EXISTS_USE_RESUME")
        progress = _load_json(progress_path)
        _validate_progress(
            progress,
            suite,
            controller_binding,
            finalizer_binding,
        )
    else:
        progress = _new_progress(
            suite,
            controller_binding,
            finalizer_binding,
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
    started = time.perf_counter()
    completed_ids = {row["case_id"] for row in progress["results"]}
    substantive_missing = [
        case
        for case in suite["cases"]["controller_finalizer"]
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
                raise CompetenceRunError("MODEL_NOT_ON_CPU")
            if str(parameter.dtype) != "torch.bfloat16":
                raise CompetenceRunError("MODEL_DTYPE_MISMATCH")
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

        for position, case in enumerate(
            suite["cases"]["controller_finalizer"],
            1,
        ):
            if case["case_id"] in completed_ids:
                continue
            case_started = time.perf_counter()
            if case["case_type"] in {"controller", "finalizer"}:
                if tokenizer is None or model is None:
                    raise CompetenceRunError("MODEL_NOT_LOADED")
                row, attempts = _substantive_result(
                    case=case,
                    tokenizer=tokenizer,
                    model=model,
                    torch=torch,
                )
            else:
                row, attempts = _runtime_fixture_result(
                    case,
                    controller_binding,
                )
            row["wall_seconds"] = time.perf_counter() - case_started
            progress["results"].append(row)
            progress["attempts"].extend(attempts)
            progress["active_case"] = None
            progress["last_completed_case_id"] = case["case_id"]
            progress["last_completed_at"] = utc_now()
            _atomic_json(progress_path, progress)
            print(
                f"[{position:02d}/51] {case['case_id']} "
                f"{row['inference_status']} "
                f"attempts={row['model_calls_used']} "
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
            raise CompetenceRunError("NETWORK_ATTEMPT_DURING_RUN")
        progress["status"] = "COMPLETE_UNEVALUATED"
        progress["runtime"] = runtime
        _atomic_json(progress_path, progress)
        seal = _write_sealed_run(
            root,
            output_dir,
            suite,
            progress,
            runtime=runtime,
        )
        print(
            json.dumps(
                {
                    "status": "SEALED_UNEVALUATED",
                    "run_id": progress["run_id"],
                    "seal_sha256": "sha256:"
                    + _sha256_file(output_dir / "seal.json"),
                    "sealed_files": sorted(seal["files"]),
                },
                sort_keys=True,
            ),
            flush=True,
        )


def _verify_seal(output_dir: Path) -> dict[str, Any]:
    seal_path = output_dir / "seal.json"
    if not seal_path.is_file():
        raise CompetenceRunError("SEALED_RUN_NOT_FOUND")
    seal = _load_json(seal_path)
    if (
        seal.get("schema_version") != SEAL_SCHEMA
        or seal.get("state") != "SEALED_BEFORE_EVALUATION"
        or set(seal.get("files", {})) != set(SEALED_ARTIFACTS)
    ):
        raise CompetenceRunError("RUN_SEAL_INVALID")
    for name, expected in seal["files"].items():
        path = output_dir / name
        if (
            not path.is_file()
            or path.stat().st_size != expected["bytes"]
            or _sha256_file(path) != expected["sha256"]
        ):
            raise CompetenceRunError(f"SEALED_ARTIFACT_MISMATCH:{name}")
    return seal


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _independent_audit(
    suite: Mapping[str, Any],
    submission: Mapping[str, Any],
    report: Mapping[str, Any],
    seal: Mapping[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    cases = suite["cases"]["controller_finalizer"]
    results = {
        row["case_id"]: row
        for row in submission["results"]
    }
    scores = {
        row["case_id"]: row
        for row in report["case_scores"]
    }
    controllers = [
        case for case in cases if case["case_type"] == "controller"
    ]
    finalizers = [
        case for case in cases if case["case_type"] == "finalizer"
    ]
    fixtures = [
        case for case in cases if case["case_type"] == "runtime_failure"
    ]
    terminal = [
        case for case in controllers if case["stratum"] in TERMINAL_STRATA
    ]
    oracle = [
        case
        for case in finalizers
        if case["scoring_target"].get("oracle_complete")
    ]
    blocked = [
        case for case in finalizers if case["stratum"] == "blocked_partial"
    ]
    restoration_finalizers = [
        case
        for case in finalizers
        if case["stratum"] == "restoration_complete"
    ]
    state_heads = {}
    for field in EVIDENCE_STATE_FIELDS:
        correct = sum(
            bool(scores[case["case_id"]].get("state_component_correct", {}).get(field))
            for case in controllers
        )
        state_heads[field] = {
            "correct": correct,
            "total": len(controllers),
            "rate": _rate(correct, len(controllers)),
        }
    terminal_by_stratum: dict[str, dict[str, Any]] = {}
    for stratum in sorted(TERMINAL_STRATA):
        rows = [case for case in terminal if case["stratum"] == stratum]
        correct = sum(
            bool(scores[case["case_id"]].get("action_correct"))
            for case in rows
        )
        selected_finalize = 0
        for case in rows:
            raw = results[case["case_id"]].get("raw_output")
            if not isinstance(raw, str):
                continue
            try:
                parsed = parse_strict_json(raw, maximum_bytes=8_192)
                index = parsed["action_index"]
                if case["public_input"]["action_menu"][index]["tool"] == "finalize":
                    selected_finalize += 1
            except (KeyError, IndexError, SchemaViolation, TypeError):
                continue
        terminal_by_stratum[stratum] = {
            "correct": correct,
            "selected_finalize": selected_finalize,
            "total": len(rows),
            "rate": _rate(correct, len(rows)),
        }

    substantive = controllers + finalizers
    typed_invalids = Counter(
        str(results[case["case_id"]].get("inference_status"))
        for case in substantive
        if results[case["case_id"]].get("inference_status")
        != str(InferenceStatus.VALID)
    )
    structural_invalid_codes = Counter(
        str(scores[case["case_id"]].get("error_code"))
        for case in substantive
        if scores[case["case_id"]].get("structured_valid") is False
    )
    fixture_rows = []
    for case in fixtures:
        result = results[case["case_id"]]
        score = scores[case["case_id"]]
        fixture_rows.append(
            {
                "case_id": case["case_id"],
                "fixture": case["stratum"],
                "inference_status": result.get("inference_status"),
                "model_was_called": result.get("model_was_called"),
                "fixture_pass": score.get("failure_fixture_pass"),
            }
        )

    def semantic_summary(selected: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        correct = sum(
            bool(scores[case["case_id"]].get("semantic_success"))
            for case in selected
        )
        return {
            "correct": correct,
            "total": len(selected),
            "rate": _rate(correct, len(selected)),
        }

    controller_syntax = sum(
        bool(scores[case["case_id"]].get("structured_valid"))
        for case in controllers
    )
    controller_correct = sum(
        bool(scores[case["case_id"]].get("action_correct"))
        for case in controllers
    )
    finalizer_syntax = sum(
        bool(scores[case["case_id"]].get("structured_valid"))
        for case in finalizers
    )
    joint_state = sum(
        bool(scores[case["case_id"]].get("exact_six_field_state"))
        for case in controllers
    )
    fixture_passes = sum(bool(row["fixture_pass"]) for row in fixture_rows)
    direct = _load_json(output_dir / "direct_av_eligibility.json")
    return {
        "schema_version": AUDIT_SCHEMA,
        "task_id": TASK_ID,
        "audited_at": utc_now(),
        "run_id": seal["run_id"],
        "sealed_input_verified": True,
        "seal_sha256": "sha256:"
        + _sha256_file(output_dir / "seal.json"),
        "frozen_evaluator_decision": report["decision"],
        "action_syntax": {
            "valid": controller_syntax,
            "total": len(controllers),
            "rate": _rate(controller_syntax, len(controllers)),
        },
        "action_correctness": {
            "correct": controller_correct,
            "total": len(controllers),
            "rate": _rate(controller_correct, len(controllers)),
            "by_stratum": report["metrics"][
                "correct_first_actions_by_stratum"
            ],
        },
        "state_heads": state_heads,
        "joint_six_field_state": {
            "correct": joint_state,
            "total": len(controllers),
            "rate": _rate(joint_state, len(controllers)),
        },
        "terminal_behavior": {
            "correct": sum(
                bool(scores[case["case_id"]].get("action_correct"))
                for case in terminal
            ),
            "total": len(terminal),
            "rate": _rate(
                sum(
                    bool(scores[case["case_id"]].get("action_correct"))
                    for case in terminal
                ),
                len(terminal),
            ),
            "by_stratum": terminal_by_stratum,
        },
        "finalizer_syntax": {
            "valid": finalizer_syntax,
            "total": len(finalizers),
            "rate": _rate(finalizer_syntax, len(finalizers)),
        },
        "oracle_supported_answers": semantic_summary(oracle),
        "blocked_partial_abstentions": semantic_summary(blocked),
        "restoration_complete_answers": semantic_summary(
            restoration_finalizers
        ),
        "restoration_reacquisition_combined_rate": report["metrics"][
            "restoration_reacquisition"
        ],
        "unsupported_required_claims": report["metrics"][
            "unsupported_required_claims"
        ],
        "private_field_exposures": report["metrics"][
            "private_field_exposures"
        ],
        "deterministic_answer_substitutions": report["metrics"][
            "deterministic_answer_substitutions"
        ],
        "substantive_typed_invalids": {
            "total": sum(typed_invalids.values()),
            "by_status": dict(sorted(typed_invalids.items())),
            "structural_error_codes": dict(
                sorted(structural_invalid_codes.items())
            ),
        },
        "runtime_fixtures": {
            "passed": fixture_passes,
            "total": len(fixture_rows),
            "rate": _rate(fixture_passes, len(fixture_rows)),
            "rows": fixture_rows,
        },
        "schema_retries": {
            "used": sum(
                int(results[case["case_id"]]["schema_repairs_used"])
                for case in substantive
            ),
            "maximum_per_case": SCHEMA_RETRIES,
            "semantic_repairs": 0,
        },
        "direct_av": direct,
        "gate_checks": report["gate_checks"],
    }


def _evaluate_sealed(root: Path, output_dir: Path) -> dict[str, Any]:
    seal = _verify_seal(output_dir)
    suite = load_suite(root / SUITE)
    submission = load_submission(output_dir / "submission.json")
    report = evaluate_competence_submission(suite, submission)
    _atomic_json(output_dir / "evaluator_report.json", report)
    audit = _independent_audit(
        suite,
        submission,
        report,
        seal,
        output_dir,
    )
    _atomic_json(output_dir / "independent_audit.json", audit)
    evaluation_manifest = {
        "schema_version": "av-trace.strong-baseline-evaluation-seal/1.0",
        "task_id": TASK_ID,
        "run_id": seal["run_id"],
        "evaluated_at": utc_now(),
        "sealed_input_verified": True,
        "input_seal_sha256": "sha256:"
        + _sha256_file(output_dir / "seal.json"),
        "files": {
            name: {
                "sha256": _sha256_file(output_dir / name),
                "bytes": (output_dir / name).stat().st_size,
            }
            for name in ("evaluator_report.json", "independent_audit.json")
        },
        "decision": report["decision"],
    }
    _atomic_json(
        output_dir / "evaluation_seal.json",
        evaluation_manifest,
        mode=0o400,
    )
    for name in ("evaluator_report.json", "independent_audit.json"):
        os.chmod(output_dir / name, 0o400)
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
        description="Run and evaluate Task-172 Granite fictional competence."
    )
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--preflight", action="store_true")
    modes.add_argument("--execute", action="store_true")
    modes.add_argument("--evaluate", action="store_true")
    modes.add_argument("--all", action="store_true")
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
        suite, snapshot, controller, finalizer = _validate_static_contract(root)
        print(
            json.dumps(
                {
                    "status": "PREFLIGHT_PASS",
                    "suite_hash": suite["suite_hash"],
                    "snapshot": str(snapshot),
                    "controller_binding": controller.to_dict(),
                    "finalizer_binding": finalizer.to_dict(),
                    "counts": EXPECTED_COUNTS,
                    "direct_av": "STRUCTURALLY_INELIGIBLE_NOT_SCORED",
                },
                indent=2,
                sort_keys=True,
            )
        )
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
    if args.all:
        _run_parent(root, output_dir, resume=args.resume)
        report = _evaluate_sealed(root, output_dir)
        print(json.dumps(report, indent=2, sort_keys=True))
        return
    raise AssertionError("unreachable")


if __name__ == "__main__":
    main()
