#!/usr/bin/env python3
"""Independent public-surface and aggregate audit for Task 182.

The audit never opens or parses ``private_labels.json``.  It authenticates
that evaluator-private file only by sealed byte count and SHA-256, and checks
private-target balance only through aggregate counts emitted during
generation.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from av_trace_strong_baselines.competence import (
    CONTROLLER_FINALIZER_THRESHOLDS,
)
from av_trace_strong_baselines.contracts import (
    FALLBACK_BINDINGS,
    canonical_json_bytes,
    sha256_json,
)
from av_trace_strong_baselines.errors import StrongBaselineError
from av_trace_strong_baselines.schemas import (
    EVIDENCE_STATE_FIELDS,
    validate_tool_action,
)
from av_trace_strong_baselines.security import (
    ObservedEvidenceLock,
    assert_public_surface,
)
from av_trace_strong_baselines_v2 import (
    ADAPTER_SCHEMA_VERSION,
    build_native_action_plan,
    controller_factor_contracts,
    finalizer_factor_contracts,
)
from av_trace_strong_baselines_v2.qwen3_suite_generator import (
    CONTROLLER_PROMPT_POLICY,
    FINALIZER_PROMPT_POLICY,
    GENERATOR_SCHEMA_VERSION,
    PRIVATE_LABEL_SCHEMA_VERSION,
    PROMPT_POLICY,
    PROMPT_POLICY_SHA256,
    PUBLIC_SUITE_SCHEMA_VERSION,
    RUNTIME_FIXTURES,
    SEAL_SCHEMA_VERSION,
)
from tools import qwen3_8b_acquisition

AUDIT_SCHEMA_VERSION = "av-trace.qwen3-adapter-v2-holdout-audit/1.0"
FREEZE_SCHEMA_VERSION = "av-trace.qwen3-adapter-v2-freeze/1.0"
FREEZE_SEAL_SCHEMA_VERSION = (
    "av-trace.qwen3-adapter-v2-governance-seal/1.0"
)
EXPECTED_SUITE_ID = "qwen3-v2-fictional-holdout-20261008"
EXPECTED_FREEZE_LABEL = "QWEN3_ADAPTER_V2_HOLDOUT_2026-10-08"
EXPECTED_DATE = "2026-10-08"
DECISION_TOKEN = "QWEN3_ADAPTER_V2_HOLDOUT_FROZEN"
RESTRICTED_DIR = Path(
    "data/restricted/strong_baselines/qwen3_v2_holdout"
)
PUBLIC_PACKET = Path(
    "data/rehearsal_plan/qwen3_adapter_v2_holdout_public.json"
)
TASK158_PUBLIC = Path(
    "data/rehearsal_plan/strong_baseline_competence_suite_v1.json"
)
GRANITE_V2_PUBLIC = Path(
    "data/rehearsal_plan/granite_adapter_v2_holdout_public.json"
)
GRANITE_V2_PROMPT_POLICY = Path(
    "data/restricted/strong_baselines/granite_v2_holdout/"
    "prompt_policy.json"
)
TASK172_RUNNER = Path("tools/granite33_competence.py")

MODEL_BINDING = {
    "repo_id": "Qwen/Qwen3-8B",
    "revision": "b968826d9c46dd6066d109eabc6255188de91218",
    "processor_revision": "b968826d9c46dd6066d109eabc6255188de91218",
    "tokenizer_revision": "b968826d9c46dd6066d109eabc6255188de91218",
}
CASE_SEQUENCE_THRESHOLD = 0.84
CASE_JACCARD_THRESHOLD = 0.72
PROMPT_SEQUENCE_THRESHOLD = 0.80
PROMPT_JACCARD_THRESHOLD = 0.72

GENERIC_TOKENS = frozenset(
    {
        "a",
        "an",
        "and",
        "answer",
        "case",
        "complete",
        "fictional",
        "fixture",
        "for",
        "in",
        "invented",
        "is",
        "item",
        "missing",
        "of",
        "on",
        "public",
        "record",
        "recorded",
        "sealed",
        "signal",
        "the",
        "this",
        "to",
        "what",
        "which",
    }
)
PROHIBITED_REAL_OR_SCIENTIFIC_PATTERNS = (
    r"\bnoaa\b",
    r"\bdeutsche welle\b",
    r"\bdw news\b",
    r"\bmit\b",
    r"\byale\b",
    r"\boxford\b",
    r"\bearthquake\b",
    r"\bmarathon\b",
    r"\blaboratory\b",
    r"\bscientific source\b",
    r"\breal source\b",
    r"\bcandidate-",
    r"\bcand-",
)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise StrongBaselineError("QWEN3_AUDIT_JSON_NOT_OBJECT")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _normalize(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.casefold()))


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in _normalize(text).split()
        if token not in GENERIC_TOKENS and len(token) > 1
    }


def _similarity(left: str, right: str) -> tuple[float, float]:
    left_normalized = _normalize(left)
    right_normalized = _normalize(right)
    sequence = SequenceMatcher(
        None,
        left_normalized,
        right_normalized,
        autojunk=False,
    ).ratio()
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    union = left_tokens | right_tokens
    jaccard = len(left_tokens & right_tokens) / len(union) if union else 0.0
    return sequence, jaccard


def _flatten_strings(value: Any) -> list[str]:
    strings: list[str] = []
    if isinstance(value, dict):
        for child in value.values():
            strings.extend(_flatten_strings(child))
    elif isinstance(value, list):
        for child in value:
            strings.extend(_flatten_strings(child))
    elif isinstance(value, str):
        strings.append(value)
    return strings


def _case_text(case: dict[str, Any]) -> str:
    return " ".join(_flatten_strings(case["public_input"]))


def _public_case_rows(suite: dict[str, Any]) -> list[dict[str, Any]]:
    cases = suite["cases"]
    if isinstance(cases, list):
        return list(cases)
    rows: list[dict[str, Any]] = []
    for group in cases.values():
        rows.extend(group)
    return rows


def _task172_prompt_strings() -> dict[str, str]:
    source = TASK172_RUNNER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    wanted = {
        "_controller_system_prompt",
        "_finalizer_system_prompt",
    }
    values: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name not in wanted:
            continue
        returns = [
            child for child in ast.walk(node) if isinstance(child, ast.Return)
        ]
        if len(returns) != 1:
            raise StrongBaselineError("TASK172_PROMPT_EXTRACTION_FAILED")
        value = ast.literal_eval(returns[0].value)
        if not isinstance(value, str):
            raise StrongBaselineError("TASK172_PROMPT_EXTRACTION_FAILED")
        values[node.name] = value
    if set(values) != wanted:
        raise StrongBaselineError("TASK172_PROMPT_EXTRACTION_FAILED")
    return {
        "task172_controller": values["_controller_system_prompt"],
        "task172_finalizer": values["_finalizer_system_prompt"],
    }


def _task181_consumed_prompts() -> dict[str, str]:
    prompts: dict[str, str] = {}
    task181_cases = qwen3_8b_acquisition.public_smoke_cases()
    for case in task181_cases:
        for factor_name, spec, role in qwen3_8b_acquisition._factor_specs(case):
            messages = qwen3_8b_acquisition._factor_messages(
                case=case,
                factor_name=factor_name,
                role=role,
                schema=spec.output_schema,
            )
            prompt_id = f"task181_{case['case_id']}_{factor_name}"
            prompts[prompt_id] = "\n".join(
                f"{message['role']}:{message['content']}"
                for message in messages
            )
    if len(prompts) != 7:
        raise StrongBaselineError("TASK181_PROMPT_INVENTORY_INVALID")
    return prompts


def _render_factor_template(
    *,
    policy: str,
    factor_name: str,
    role: str,
    schema: dict[str, Any],
    case: dict[str, Any],
    retry: bool = False,
) -> str:
    if factor_name == "action_choice":
        instruction = (
            "For this factor only, choose exactly one supplied no-argument "
            "function. A function call is required. Do not answer the case, "
            "do not emit prose, and do not regenerate tool arguments."
        )
    else:
        instruction = (
            "For this factor only, return exactly one compact JSON object and "
            "no prose or markdown. Match the supplied schema exactly. Author "
            "only this factor; do not assume or repair another factor."
        )
    payload: dict[str, Any] = {
        "factor_id": factor_name,
        "factor_role": role,
        "output_schema": schema,
        "public_case": {
            "case_type": case["case_type"],
            "public_input": case["public_input"],
        },
    }
    if retry:
        instruction += (
            " This is the one allowed schema-only retry. Preserve every "
            "semantic scalar value from the prior attempt exactly; change "
            "only JSON/schema representation. If that cannot be done, repeat "
            "the prior content without inventing or substituting semantics."
        )
        payload["schema_only_retry"] = {
            "prior_error_code": "<PUBLIC_ERROR_CODE>",
            "prior_raw_output": "<PUBLIC_PRIOR_OUTPUT>",
        }
    return json.dumps(
        [
            {"role": "system", "content": policy + " " + instruction},
            {
                "role": "user",
                "content": json.dumps(
                    payload,
                    indent=2,
                    sort_keys=True,
                    ensure_ascii=False,
                ),
            },
        ],
        sort_keys=True,
        ensure_ascii=False,
    )


def _factor_specs(
    case: dict[str, Any],
    *,
    action_role: str = "qwen_native_tool_choice",
) -> list[tuple[str, Any, str]]:
    handles = [
        str(item["claim_handle"])
        for item in case["public_input"]["public_claim_slots"]
    ]
    if case["case_type"] == "controller":
        plan = build_native_action_plan(case["public_input"]["action_menu"])
        from av_trace_strong_baselines_v2 import (
            action_choice_spec,
            evidence_state_spec,
        )

        return [
            (
                "action_choice",
                action_choice_spec(plan),
                action_role,
            ),
            (
                "evidence_state",
                evidence_state_spec(handles),
                "evidence_state_heads",
            ),
        ]
    observations = case["public_input"]["observed_evidence"]
    from av_trace_strong_baselines_v2 import finalizer_factor_specs

    specs = finalizer_factor_specs(
        claim_handles=handles,
        observation_ids=[
            str(item["observation_id"]) for item in observations
        ],
    )
    return [(name, spec, spec.role) for name, spec in specs.items()]


def _new_rendered_prompts(public: dict[str, Any]) -> dict[str, str]:
    prompts: dict[str, str] = {}
    for case in public["cases"]:
        if case["case_type"] not in {"controller", "finalizer"}:
            continue
        policy = (
            CONTROLLER_PROMPT_POLICY
            if case["case_type"] == "controller"
            else FINALIZER_PROMPT_POLICY
        )
        for factor_name, spec, role in _factor_specs(case):
            prefix = f"{case['case_id']}::{factor_name}"
            prompts[prefix + "::initial"] = _render_factor_template(
                policy=policy,
                factor_name=factor_name,
                role=role,
                schema=dict(spec.output_schema),
                case=case,
            )
            prompts[prefix + "::schema_retry"] = _render_factor_template(
                policy=policy,
                factor_name=factor_name,
                role=role,
                schema=dict(spec.output_schema),
                case=case,
                retry=True,
            )
    if len(prompts) != 256:
        raise StrongBaselineError("QWEN3_RENDERED_PROMPT_COUNT_INVALID")
    return prompts


def _task172_rendered_prompts() -> dict[str, str]:
    prompts: dict[str, str] = {}
    systems = _task172_prompt_strings()
    suite = _load_json(TASK158_PUBLIC)
    for case in _public_case_rows(suite):
        if case.get("case_type") not in {"controller", "finalizer"}:
            continue
        system = systems[
            "task172_controller"
            if case["case_type"] == "controller"
            else "task172_finalizer"
        ]
        initial_messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "case_type": case["case_type"],
                        "public_input": case["public_input"],
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                    ensure_ascii=False,
                ),
            },
        ]
        prompts[f"task172::{case['case_id']}::initial"] = json.dumps(
            initial_messages,
            sort_keys=True,
            ensure_ascii=False,
        )
        repair_messages = [
            *initial_messages,
            {"role": "assistant", "content": "<PUBLIC_PRIOR_OUTPUT>"},
            {
                "role": "user",
                "content": (
                    "Schema-only repair. Return the same attempted content in "
                    "exactly the required JSON structure, with no markdown or "
                    "extra text. Do not add or change facts, claims, citations, "
                    "answers, selected actions, evidence-state judgments, or "
                    "diagnoses. Validation error code: <PUBLIC_ERROR_CODE>."
                ),
            },
        ]
        prompts[f"task172::{case['case_id']}::schema_retry"] = json.dumps(
            repair_messages,
            sort_keys=True,
            ensure_ascii=False,
        )
    if len(prompts) != 80:
        raise StrongBaselineError("TASK172_RENDERED_PROMPT_COUNT_INVALID")
    return prompts


def _granite_v2_rendered_prompts() -> dict[str, str]:
    prompts: dict[str, str] = {}
    policy = _load_json(GRANITE_V2_PROMPT_POLICY)
    suite = _load_json(GRANITE_V2_PUBLIC)
    for case in suite["cases"]:
        if case["case_type"] not in {"controller", "finalizer"}:
            continue
        factor_policy = (
            str(policy["controller"])
            if case["case_type"] == "controller"
            else str(policy["finalizer"])
        )
        for factor_name, spec, role in _factor_specs(
            case,
            action_role="granite_native_tool_choice",
        ):
            prefix = f"task177::{case['case_id']}::{factor_name}"
            prompts[prefix + "::initial"] = _render_factor_template(
                policy=factor_policy,
                factor_name=factor_name,
                role=role,
                schema=dict(spec.output_schema),
                case=case,
            )
            prompts[prefix + "::schema_retry"] = _render_factor_template(
                policy=factor_policy,
                factor_name=factor_name,
                role=role,
                schema=dict(spec.output_schema),
                case=case,
                retry=True,
            )
    if len(prompts) != 256:
        raise StrongBaselineError("TASK177_RENDERED_PROMPT_COUNT_INVALID")
    return prompts


def _consumed_rendered_prompts() -> dict[str, str]:
    prompts = _task172_rendered_prompts()
    prompts.update(_granite_v2_rendered_prompts())
    prompts.update(_task181_consumed_prompts())
    if len(prompts) != 343:
        raise StrongBaselineError("CONSUMED_RENDERED_PROMPT_COUNT_INVALID")
    return prompts


def _consumed_public_prompts() -> dict[str, str]:
    prompts = _task172_prompt_strings()
    granite_prompt = _load_json(GRANITE_V2_PROMPT_POLICY)
    prompts["granite_v2_controller"] = str(granite_prompt["controller"])
    prompts["granite_v2_finalizer"] = str(granite_prompt["finalizer"])
    granite_v2_factors = (
        "action_choice",
        "evidence_state",
        "disposition",
        "answer_text",
        "claim_drafts",
        "citation_selections",
        "diagnosis",
    )
    for factor_name in granite_v2_factors:
        if factor_name == "action_choice":
            factor_instruction = (
                "For this factor only, choose exactly one supplied "
                "no-argument function. A function call is required. Do not "
                "answer the case, do not emit prose, and do not regenerate "
                "tool arguments."
            )
            policy = str(granite_prompt["controller"])
        else:
            factor_instruction = (
                "For this factor only, return exactly one compact JSON object "
                "and no prose or markdown. Match the supplied schema exactly. "
                "Author only this factor; do not assume or repair another "
                "factor."
            )
            policy = (
                str(granite_prompt["controller"])
                if factor_name == "evidence_state"
                else str(granite_prompt["finalizer"])
            )
        prompts[f"granite_v2_factor_{factor_name}"] = (
            policy + " " + factor_instruction
        )
        prompts[f"granite_v2_retry_{factor_name}"] = (
            policy
            + " "
            + factor_instruction
            + " This is the one allowed schema-only retry. Preserve every "
            "semantic scalar value from the prior attempt exactly; change "
            "only JSON/schema representation. If that cannot be done, repeat "
            "the prior content without inventing or substituting semantics."
        )
    prompts.update(_task181_consumed_prompts())
    task181_smoke = qwen3_8b_acquisition.public_smoke_cases()
    prompts["task181_smoke_cases_public_json"] = json.dumps(
        task181_smoke,
        sort_keys=True,
        ensure_ascii=False,
    )
    prompts["task158_public_suite_json"] = json.dumps(
        _load_json(TASK158_PUBLIC),
        sort_keys=True,
        ensure_ascii=False,
    )
    prompts["granite_v2_public_suite_json"] = json.dumps(
        _load_json(GRANITE_V2_PUBLIC),
        sort_keys=True,
        ensure_ascii=False,
    )
    if len(prompts) != 28:
        raise StrongBaselineError("CONSUMED_PROMPT_INVENTORY_INVALID")
    return prompts


def _validate_public_schema(public: dict[str, Any]) -> dict[str, Any]:
    if public.get("schema_version") != PUBLIC_SUITE_SCHEMA_VERSION:
        raise StrongBaselineError("QWEN3_PUBLIC_SCHEMA_VERSION_MISMATCH")
    if public.get("suite_id") != EXPECTED_SUITE_ID:
        raise StrongBaselineError("QWEN3_SUITE_ID_MISMATCH")
    if public.get("freeze_label") != EXPECTED_FREEZE_LABEL:
        raise StrongBaselineError("QWEN3_FREEZE_LABEL_MISMATCH")
    if public.get("generated_date") != EXPECTED_DATE:
        raise StrongBaselineError("QWEN3_DATE_MISMATCH")
    if public.get("adapter_schema_version") != ADAPTER_SCHEMA_VERSION:
        raise StrongBaselineError("QWEN3_ADAPTER_SCHEMA_MISMATCH")
    if (
        public.get("adapter_profile")
        != "qwen3-native-transport-factorized-v2"
    ):
        raise StrongBaselineError("QWEN3_ADAPTER_PROFILE_MISMATCH")
    if public.get("execution_status") != "SEALED_NOT_RUN":
        raise StrongBaselineError("QWEN3_EXECUTION_STATUS_INVALID")
    if public.get("thresholds") != CONTROLLER_FINALIZER_THRESHOLDS:
        raise StrongBaselineError("QWEN3_THRESHOLDS_MISMATCH")
    if public.get("content_boundary") != {
        "fictional_generated_primitives_only": True,
        "scientific_family_content": False,
        "real_source_content": False,
        "model_results_present": False,
        "private_labels_present": False,
    }:
        raise StrongBaselineError("QWEN3_CONTENT_BOUNDARY_INVALID")
    binding = public.get("binding", {})
    for role in ("controller", "finalizer"):
        observed = binding.get(role, {})
        if observed != FALLBACK_BINDINGS[role].to_dict():
            raise StrongBaselineError("QWEN3_MODEL_BINDING_MISMATCH")
        for key, value in MODEL_BINDING.items():
            if observed.get(key) != value:
                raise StrongBaselineError("QWEN3_MODEL_IDENTITY_MISMATCH")
    if binding.get("same_exact_snapshot_required") is not True:
        raise StrongBaselineError("QWEN3_SAME_SNAPSHOT_NOT_REQUIRED")
    prompt = public.get("prompt_policy", {})
    if prompt.get("sha256") != PROMPT_POLICY_SHA256:
        raise StrongBaselineError("QWEN3_PROMPT_POLICY_HASH_MISMATCH")
    if (
        prompt.get("native_tool_transport")
        != "qwen_chat_template_tool_call"
        or prompt.get("enable_thinking") is not False
        or prompt.get("decoding") != "greedy"
    ):
        raise StrongBaselineError("QWEN3_PROMPT_RUNTIME_POLICY_MISMATCH")
    cases = public.get("cases")
    if not isinstance(cases, list) or len(cases) != 51:
        raise StrongBaselineError("QWEN3_CASE_COUNT_INVALID")
    ids = [case.get("case_id") for case in cases]
    if any(not isinstance(case_id, str) for case_id in ids):
        raise StrongBaselineError("QWEN3_CASE_ID_INVALID")
    if len(ids) != len(set(ids)):
        raise StrongBaselineError("QWEN3_CASE_ID_DUPLICATE")
    for case in cases:
        if set(case) != {"case_id", "case_type", "stratum", "public_input"}:
            raise StrongBaselineError("QWEN3_CASE_FIELD_SET_INVALID")
        assert_public_surface(case)
        public_input = case["public_input"]
        slots = public_input.get("public_claim_slots")
        if not isinstance(slots, list) or len(slots) != 1:
            raise StrongBaselineError("QWEN3_CLAIM_SLOT_COUNT_INVALID")
        handles = [slots[0]["claim_handle"]]
        if case["case_type"] == "controller":
            menu = public_input.get("action_menu")
            if not isinstance(menu, list) or not menu:
                raise StrongBaselineError("QWEN3_ACTION_MENU_INVALID")
            for action in menu:
                validate_tool_action(action)
            build_native_action_plan(menu)
            controller_factor_contracts(
                action_menu=menu,
                claim_handles=handles,
            )
            ObservedEvidenceLock(public_input["observed_evidence"])
        elif case["case_type"] == "finalizer":
            observations = public_input.get("observed_evidence")
            if not isinstance(observations, list):
                raise StrongBaselineError("QWEN3_OBSERVATIONS_INVALID")
            lock = ObservedEvidenceLock(observations)
            finalizer_factor_contracts(
                claim_handles=handles,
                observation_ids=[
                    item["observation_id"]
                    for item in lock.public_observations()
                ],
            )
        elif case["case_type"] == "runtime_failure":
            if (
                public_input.get("injected_public_fixture")
                != case["stratum"]
            ):
                raise StrongBaselineError("QWEN3_RUNTIME_FIXTURE_MISMATCH")
        else:
            raise StrongBaselineError("QWEN3_CASE_TYPE_INVALID")
    return {
        "case_count": len(cases),
        "unique_case_ids": len(set(ids)),
        "public_surface": "PASS",
        "adapter_contract_schema": "PASS",
        "exact_qwen3_binding": "PASS",
    }


def _validate_aggregate_composition(
    public: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    cases = public["cases"]
    expected_types = {
        "controller": 24,
        "finalizer": 16,
        "runtime_failure": 11,
    }
    expected_controller = {
        "route_vision": 3,
        "route_speech": 3,
        "route_ambient": 3,
        "observe_pointer": 3,
        "blocked_status": 3,
        "restoration_reacquire": 3,
        "no_trigger": 3,
        "finalize_ready": 3,
    }
    expected_finalizer = {
        "oracle_complete": 8,
        "restoration_complete": 4,
        "blocked_partial": 4,
    }
    expected_runtime = {fixture: 1 for fixture, _, _ in RUNTIME_FIXTURES}
    actual_types = dict(Counter(case["case_type"] for case in cases))
    if actual_types != expected_types:
        raise StrongBaselineError("QWEN3_CASE_COMPOSITION_INVALID")
    actual_strata = {
        kind: dict(
            Counter(
                case["stratum"]
                for case in cases
                if case["case_type"] == kind
            )
        )
        for kind in expected_types
    }
    if actual_strata != {
        "controller": expected_controller,
        "finalizer": expected_finalizer,
        "runtime_failure": expected_runtime,
    }:
        raise StrongBaselineError("QWEN3_STRATA_BALANCE_INVALID")
    policies = Counter(
        case["public_input"]["controller_policy"]
        for case in cases
        if case["case_type"] == "controller"
    )
    if dict(policies) != {"react_v2": 12, "sufficiency_v2": 12}:
        raise StrongBaselineError("QWEN3_CONTROLLER_POLICY_BALANCE_INVALID")
    aggregate = manifest.get("aggregate_composition")
    if not isinstance(aggregate, dict):
        raise StrongBaselineError("QWEN3_AGGREGATE_COMPOSITION_MISSING")
    if aggregate.get("case_types") != expected_types:
        raise StrongBaselineError("QWEN3_AGGREGATE_CASE_TYPES_INVALID")
    if aggregate.get("strata") != actual_strata:
        raise StrongBaselineError("QWEN3_AGGREGATE_STRATA_INVALID")
    if aggregate.get("coverage_families") != {
        "routing_controller_cases": 15,
        "state_controller_cases": 24,
        "terminal_controller_cases": 6,
        "restoration_cases": 7,
        "no_trigger_cases": 3,
        "oracle_finalizer_cases": 8,
        "partial_finalizer_cases": 4,
    }:
        raise StrongBaselineError("QWEN3_COVERAGE_FAMILY_BALANCE_INVALID")
    private = aggregate.get("private_label_aggregates", {})
    if private.get("controller_expected_tools") != {
        "finalize": 6,
        "get_channel_status": 3,
        "inspect_clip": 3,
        "search_ambient_audio": 3,
        "search_speech": 6,
        "search_visual": 3,
    }:
        raise StrongBaselineError("QWEN3_PRIVATE_TOOL_BALANCE_INVALID")
    if private.get("controller_terminal") != {"false": 18, "true": 6}:
        raise StrongBaselineError("QWEN3_TERMINAL_BALANCE_INVALID")
    if private.get("restoration_reacquisition") != {
        "false": 33,
        "true": 7,
    }:
        raise StrongBaselineError("QWEN3_RESTORATION_BALANCE_INVALID")
    if private.get("no_trigger_control") != {
        "false": 21,
        "true": 3,
    }:
        raise StrongBaselineError("QWEN3_NO_TRIGGER_BALANCE_INVALID")
    if private.get("finalizer_answer_modes") != {
        "abstain": 4,
        "answer": 12,
    }:
        raise StrongBaselineError("QWEN3_FINALIZER_BALANCE_INVALID")
    if private.get("finalizer_required_modalities") != {
        "ambient": 5,
        "speech": 5,
        "vision": 6,
    }:
        raise StrongBaselineError("QWEN3_MODALITY_BALANCE_INVALID")
    if private.get("finalizer_required_missing_hops") != {
        "ambient_event": 1,
        "event_detection": 1,
        "speech_content": 1,
        "temporal_order": 1,
    }:
        raise StrongBaselineError("QWEN3_HOP_BALANCE_INVALID")
    if private.get("runtime_expected_model_called") != {
        "false": 2,
        "true": 9,
    }:
        raise StrongBaselineError("QWEN3_RUNTIME_CALL_BALANCE_INVALID")
    if private.get("runtime_expected_statuses") != {
        "BUDGET_EXHAUSTED": 1,
        "INVALID_OUTPUT": 5,
        "OOM": 1,
        "PROCESS_FAILURE": 1,
        "PROVIDER_FAILURE": 1,
        "SNAPSHOT_MISMATCH": 1,
        "TIMEOUT": 1,
    }:
        raise StrongBaselineError("QWEN3_RUNTIME_STATUS_BALANCE_INVALID")
    state_heads = private.get("controller_state_heads", {})
    expected_state_aggregates = (
        set(EVIDENCE_STATE_FIELDS) - {"covered_claim_handles"}
    ) | {"covered_claim_count"}
    if set(state_heads) != expected_state_aggregates:
        raise StrongBaselineError("QWEN3_STATE_HEAD_AGGREGATES_INVALID")
    for value in ("0.0", "1.0"):
        if state_heads["p_sufficient"].get(value, 0) < 3:
            raise StrongBaselineError("QWEN3_P_SUFFICIENT_BALANCE_INVALID")
    for modality in ("vision", "speech", "ambient"):
        if state_heads["missing_modalities"].get(modality, 0) < 3:
            raise StrongBaselineError("QWEN3_STATE_MODALITY_BALANCE_INVALID")
    for cause in (
        "evidence_accessible_but_not_found",
        "evidence_in_source_but_inaccessible",
        "not_missing",
    ):
        if state_heads["missingness_cause"].get(cause, 0) < 3:
            raise StrongBaselineError("QWEN3_STATE_CAUSE_BALANCE_INVALID")
    for intent in (
        "search_vision",
        "search_speech",
        "search_ambient",
        "observe_pointer",
        "check_channel_status",
        "retry_restored_route",
        "finalize_answer",
        "finalize_abstain",
    ):
        if state_heads["recovery_intent"].get(intent) != 3:
            raise StrongBaselineError("QWEN3_STATE_INTENT_BALANCE_INVALID")
    return {
        "case_types": expected_types,
        "controller_strata": expected_controller,
        "finalizer_strata": expected_finalizer,
        "runtime_strata": expected_runtime,
        "coverage_families": aggregate["coverage_families"],
        "controller_policy_balance": dict(policies),
        "private_label_aggregate_only": True,
        "private_label_aggregates": private,
    }


def _case_overlap(
    new_cases: list[dict[str, Any]],
    old_cases: list[dict[str, Any]],
    *,
    corpus_name: str,
) -> dict[str, Any]:
    exact_public_inputs = 0
    exact_questions = 0
    near_pairs = 0
    maximum_sequence = 0.0
    maximum_jaccard = 0.0
    closest_pair: dict[str, Any] | None = None
    old_input_hashes = {
        sha256_json(case["public_input"]): case["case_id"]
        for case in old_cases
    }
    old_questions = {
        _normalize(case["public_input"].get("question", "")): case["case_id"]
        for case in old_cases
    }
    for new_case in new_cases:
        new_hash = sha256_json(new_case["public_input"])
        exact_public_inputs += int(new_hash in old_input_hashes)
        new_question = _normalize(
            new_case["public_input"].get("question", "")
        )
        exact_questions += int(new_question in old_questions)
        new_text = _case_text(new_case)
        for old_case in old_cases:
            sequence, jaccard = _similarity(
                new_text,
                _case_text(old_case),
            )
            if (
                sequence >= CASE_SEQUENCE_THRESHOLD
                or jaccard >= CASE_JACCARD_THRESHOLD
            ):
                near_pairs += 1
            if sequence + jaccard > maximum_sequence + maximum_jaccard:
                closest_pair = {
                    "new_case_id": new_case["case_id"],
                    "old_case_id": old_case["case_id"],
                    "sequence_ratio": round(sequence, 6),
                    "token_jaccard": round(jaccard, 6),
                }
            maximum_sequence = max(maximum_sequence, sequence)
            maximum_jaccard = max(maximum_jaccard, jaccard)
    if exact_public_inputs or exact_questions or near_pairs:
        raise StrongBaselineError(
            f"QWEN3_OVERLAP_DETECTED:{corpus_name}"
        )
    return {
        "corpus": corpus_name,
        "new_public_cases": len(new_cases),
        "consumed_public_cases": len(old_cases),
        "pairwise_comparisons": len(new_cases) * len(old_cases),
        "exact_public_input_matches": exact_public_inputs,
        "exact_question_matches": exact_questions,
        "near_overlap_pairs": near_pairs,
        "maximum_sequence_ratio": round(maximum_sequence, 6),
        "maximum_token_jaccard": round(maximum_jaccard, 6),
        "closest_pair": closest_pair,
        "status": "PASS",
    }


def _overlap_audit(public: dict[str, Any]) -> dict[str, Any]:
    new_cases = list(public["cases"])
    task158 = [
        case
        for case in _public_case_rows(_load_json(TASK158_PUBLIC))
        if case.get("case_type")
        in {"controller", "finalizer", "runtime_failure"}
        and not str(case.get("case_id", "")).startswith(
            "sbc-direct-failure-"
        )
    ]
    granite_v2 = [
        case
        for case in _public_case_rows(_load_json(GRANITE_V2_PUBLIC))
        if case.get("case_type")
        in {"controller", "finalizer", "runtime_failure"}
    ]
    task181 = qwen3_8b_acquisition.public_smoke_cases()
    case_reports = {
        "task158_public_suite": _case_overlap(
            new_cases,
            task158,
            corpus_name=str(TASK158_PUBLIC),
        ),
        "granite_v2_holdout": _case_overlap(
            new_cases,
            granite_v2,
            corpus_name=str(GRANITE_V2_PUBLIC),
        ),
        "task181_public_smoke": _case_overlap(
            new_cases,
            task181,
            corpus_name="tools/qwen3_8b_acquisition.py:public_smoke_cases",
        ),
    }
    new_prompts = {
        "qwen3_v2_controller": CONTROLLER_PROMPT_POLICY,
        "qwen3_v2_finalizer": FINALIZER_PROMPT_POLICY,
    }
    consumed_prompts = _consumed_public_prompts()
    prompt_pairs: list[dict[str, Any]] = []
    exact_prompt_matches = 0
    near_prompt_pairs = 0
    maximum_sequence = 0.0
    maximum_jaccard = 0.0
    closest_pair: dict[str, Any] | None = None
    for new_id, new_prompt in new_prompts.items():
        for consumed_id, consumed_prompt in consumed_prompts.items():
            sequence, jaccard = _similarity(new_prompt, consumed_prompt)
            exact = _normalize(new_prompt) == _normalize(consumed_prompt)
            near = (
                sequence >= PROMPT_SEQUENCE_THRESHOLD
                or jaccard >= PROMPT_JACCARD_THRESHOLD
            )
            exact_prompt_matches += int(exact)
            near_prompt_pairs += int(near)
            pair = {
                "new_prompt_id": new_id,
                "consumed_prompt_id": consumed_id,
                "exact_match": exact,
                "near_overlap": near,
                "sequence_ratio": round(sequence, 6),
                "token_jaccard": round(jaccard, 6),
            }
            prompt_pairs.append(pair)
            if sequence + jaccard > maximum_sequence + maximum_jaccard:
                closest_pair = pair
            maximum_sequence = max(maximum_sequence, sequence)
            maximum_jaccard = max(maximum_jaccard, jaccard)
    if exact_prompt_matches or near_prompt_pairs:
        raise StrongBaselineError("QWEN3_CONSUMED_PROMPT_OVERLAP_DETECTED")
    rendered_prompts = _new_rendered_prompts(public)
    consumed_rendered_prompts = _consumed_rendered_prompts()
    exact_rendered_matches = 0
    near_rendered_pairs = 0
    maximum_rendered_sequence = 0.0
    maximum_rendered_jaccard = 0.0
    closest_rendered_pair: dict[str, Any] | None = None
    # Full rendered prompts are large. Exact equality and token Jaccard are
    # computed for every pair. SequenceMatcher is computed for the five
    # lexically closest consumed prompts per new rendered prompt. Near
    # overlap fails if either metric crosses its frozen threshold.
    for new_id, new_prompt in rendered_prompts.items():
        new_normalized = _normalize(new_prompt)
        new_tokens = _tokens(new_prompt)
        candidates: list[tuple[float, str, str]] = []
        for consumed_id, consumed_prompt in consumed_rendered_prompts.items():
            consumed_normalized = _normalize(consumed_prompt)
            exact = new_normalized == consumed_normalized
            exact_rendered_matches += int(exact)
            consumed_tokens = _tokens(consumed_prompt)
            union = new_tokens | consumed_tokens
            jaccard = (
                len(new_tokens & consumed_tokens) / len(union)
                if union
                else 0.0
            )
            maximum_rendered_jaccard = max(
                maximum_rendered_jaccard,
                jaccard,
            )
            if jaccard >= PROMPT_JACCARD_THRESHOLD:
                near_rendered_pairs += 1
            candidates.append((jaccard, consumed_id, consumed_normalized))
        candidates.sort(reverse=True)
        for jaccard, consumed_id, consumed_normalized in candidates[:5]:
            sequence = SequenceMatcher(
                None,
                new_normalized,
                consumed_normalized,
                autojunk=True,
            ).ratio()
            if sequence >= PROMPT_SEQUENCE_THRESHOLD:
                near_rendered_pairs += 1
            if sequence > maximum_rendered_sequence:
                closest_rendered_pair = {
                    "new_prompt_id": new_id,
                    "consumed_prompt_id": consumed_id,
                    "sequence_ratio": round(sequence, 6),
                    "token_jaccard": round(jaccard, 6),
                }
                maximum_rendered_sequence = sequence
    if exact_rendered_matches or near_rendered_pairs:
        raise StrongBaselineError(
            "QWEN3_RENDERED_CONSUMED_PROMPT_OVERLAP_DETECTED"
        )
    return {
        "thresholds": {
            "case_sequence_ratio_strictly_below": CASE_SEQUENCE_THRESHOLD,
            "case_token_jaccard_strictly_below": CASE_JACCARD_THRESHOLD,
            "prompt_sequence_ratio_strictly_below": (
                PROMPT_SEQUENCE_THRESHOLD
            ),
            "prompt_token_jaccard_strictly_below": PROMPT_JACCARD_THRESHOLD,
        },
        "case_corpora": case_reports,
        "case_exact_or_near_overlap_pairs_total": sum(
            report["exact_public_input_matches"]
            + report["exact_question_matches"]
            + report["near_overlap_pairs"]
            for report in case_reports.values()
        ),
        "consumed_prompt_inventory": {
            "count": len(consumed_prompts),
            "ids": sorted(consumed_prompts),
            "sources": [
                str(TASK172_RUNNER),
                str(GRANITE_V2_PROMPT_POLICY),
                (
                    "tools/qwen3_8b_acquisition.py:public_smoke_cases/"
                    "_factor_messages"
                ),
            ],
        },
        "prompt_pairwise_comparisons": len(prompt_pairs),
        "exact_prompt_matches": exact_prompt_matches,
        "near_prompt_pairs": near_prompt_pairs,
        "maximum_prompt_sequence_ratio": round(maximum_sequence, 6),
        "maximum_prompt_token_jaccard": round(maximum_jaccard, 6),
        "closest_prompt_pair": closest_pair,
        "prompt_pair_details": prompt_pairs,
        "rendered_prompt_audit": {
            "new_initial_and_retry_prompts": len(rendered_prompts),
            "consumed_prompt_corpus": len(consumed_rendered_prompts),
            "pairwise_token_comparisons": (
                len(rendered_prompts) * len(consumed_rendered_prompts)
            ),
            "sequence_candidate_comparisons": len(rendered_prompts) * 5,
            "exact_matches": exact_rendered_matches,
            "near_overlap_pairs": near_rendered_pairs,
            "maximum_sequence_ratio_among_lexically_closest_candidates": (
                round(maximum_rendered_sequence, 6)
            ),
            "maximum_token_jaccard": round(
                maximum_rendered_jaccard,
                6,
            ),
            "closest_pair": closest_rendered_pair,
            "status": "PASS",
        },
        "status": "PASS",
    }


def _content_audit(public: dict[str, Any]) -> dict[str, Any]:
    rendered = json.dumps(public, sort_keys=True).casefold()
    hits = [
        pattern
        for pattern in PROHIBITED_REAL_OR_SCIENTIFIC_PATTERNS
        if re.search(pattern, rendered)
    ]
    if hits:
        raise StrongBaselineError(
            "QWEN3_REAL_OR_SCIENTIFIC_CONTENT_DETECTED",
            details={"terms": hits},
        )
    return {
        "prohibited_patterns_checked": list(
            PROHIBITED_REAL_OR_SCIENTIFIC_PATTERNS
        ),
        "hits": [],
        "status": "PASS",
    }


def _seal_audit(
    restricted_dir: Path,
    public: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    seal = _load_json(restricted_dir / "seal.json")
    if seal.get("schema_version") != SEAL_SCHEMA_VERSION:
        raise StrongBaselineError("QWEN3_SEAL_SCHEMA_MISMATCH")
    if seal.get("state") != "SEALED_BEFORE_MODEL_EXECUTION":
        raise StrongBaselineError("QWEN3_SEAL_STATE_INVALID")
    expected_names = {
        "public_suite.json",
        "private_labels.json",
        "generation_manifest.json",
        "prompt_policy.json",
    }
    if set(seal.get("files", {})) != expected_names:
        raise StrongBaselineError("QWEN3_SEAL_FILE_SET_INVALID")
    for name, recorded in seal["files"].items():
        path = restricted_dir / name
        if not path.is_file():
            raise StrongBaselineError("QWEN3_SEALED_FILE_MISSING")
        if recorded.get("bytes") != path.stat().st_size:
            raise StrongBaselineError("QWEN3_SEALED_FILE_SIZE_MISMATCH")
        if recorded.get("sha256") != _sha256_file(path):
            raise StrongBaselineError("QWEN3_SEALED_FILE_HASH_MISMATCH")
    if seal.get("semantic_hashes") != {
        "public_suite": sha256_json(public),
        "private_labels": manifest["private_labels_sha256"],
        "prompt_policy": PROMPT_POLICY_SHA256,
        "model_binding": sha256_json(public["binding"]),
        "gate_c_thresholds": sha256_json(
            CONTROLLER_FINALIZER_THRESHOLDS
        ),
    }:
        raise StrongBaselineError("QWEN3_SEMANTIC_HASH_MISMATCH")
    if manifest.get("public_suite_sha256") != sha256_json(public):
        raise StrongBaselineError("QWEN3_MANIFEST_PUBLIC_HASH_MISMATCH")
    if manifest.get("schema_version") != GENERATOR_SCHEMA_VERSION:
        raise StrongBaselineError("QWEN3_MANIFEST_SCHEMA_MISMATCH")
    if (
        manifest.get("private_target_manual_inspection") is not False
        or manifest.get("model_used") is not False
        or manifest.get("scientific_source_used") is not False
        or manifest.get("real_source_content_used") is not False
        or manifest.get("consumed_private_labels_used") is not False
        or manifest.get("consumed_public_prompts_used_for_generation")
        is not False
    ):
        raise StrongBaselineError("QWEN3_MANIFEST_SCOPE_FLAG_INVALID")
    prompt = _load_json(restricted_dir / "prompt_policy.json")
    if prompt != PROMPT_POLICY:
        raise StrongBaselineError("QWEN3_PROMPT_POLICY_CONTENT_MISMATCH")
    public_copy = _load_json(PUBLIC_PACKET)
    if canonical_json_bytes(public_copy) != canonical_json_bytes(public):
        raise StrongBaselineError("QWEN3_PUBLIC_PACKET_COPY_MISMATCH")
    private_path = restricted_dir / "private_labels.json"
    return {
        "sealed_file_count": len(expected_names),
        "private_labels_schema_version": PRIVATE_LABEL_SCHEMA_VERSION,
        "private_labels_file_sha256": _sha256_file(private_path),
        "private_labels_file_bytes": private_path.stat().st_size,
        "private_labels_loaded_or_parsed": False,
        "public_packet_copy_match": True,
        "status": "PASS",
    }


def _authorization_audit(
    restricted_dir: Path,
    public: dict[str, Any],
) -> dict[str, Any]:
    freeze = _load_json(restricted_dir / "freeze_manifest.json")
    if freeze.get("schema_version") != FREEZE_SCHEMA_VERSION:
        raise StrongBaselineError("QWEN3_FREEZE_MANIFEST_SCHEMA_MISMATCH")
    for key, expected in (
        ("task_id", 182),
        ("date", EXPECTED_DATE),
        ("suite_id", EXPECTED_SUITE_ID),
        ("freeze_label", EXPECTED_FREEZE_LABEL),
        ("decision_token", DECISION_TOKEN),
        ("status", "FROZEN_UNSEEN_NOT_RUN"),
    ):
        if freeze.get(key) != expected:
            raise StrongBaselineError(
                f"QWEN3_FREEZE_MANIFEST_{key.upper()}_MISMATCH"
            )
    if freeze.get("model_binding") != public["binding"]:
        raise StrongBaselineError("QWEN3_FREEZE_MODEL_BINDING_MISMATCH")
    if freeze.get("gate_c_thresholds") != CONTROLLER_FINALIZER_THRESHOLDS:
        raise StrongBaselineError("QWEN3_FREEZE_THRESHOLD_MISMATCH")
    authorization = freeze.get("one_run_authorization", {})
    required_authorization = {
        "authorization_state": "AUTHORIZED_EXACTLY_ONCE_AFTER_FREEZE",
        "maximum_full_suite_runs": 1,
        "development_or_smoke_subset_runs": 0,
        "partial_model_runs": 0,
        "reruns_after_any_model_output": 0,
        "model_inference_executed_during_freeze": False,
        "execution_in_this_task": False,
        "separate_execution_task_required": True,
        "pre_run_seal_environment_model_adapter_verification_required": True,
        "post_run_deterministic_evaluator_replays": 1,
    }
    if authorization != required_authorization:
        raise StrongBaselineError("QWEN3_ONE_RUN_AUTHORIZATION_INVALID")
    prohibited = freeze.get("prohibited_tuning_sources")
    required_prohibited = {
        "private_labels_or_derived_targets",
        "qwen3_holdout_model_outputs",
        "qwen3_holdout_evaluator_reports",
        "qwen3_holdout_component_or_error_audits",
        "manual_review_of_holdout_errors",
        "scientific_family_content_or_keys",
        "task158_private_evaluator_targets",
        "granite_v2_private_evaluator_targets",
        "task172_or_task177_outputs_for_post_freeze_changes",
        "task181_smoke_outputs_for_post_freeze_changes",
        "outcome_conditioned_threshold_prompt_adapter_runtime_or_model_changes",
    }
    if not isinstance(prohibited, list) or set(prohibited) != required_prohibited:
        raise StrongBaselineError("QWEN3_PROHIBITED_TUNING_SOURCES_INVALID")
    mutation_policy = {
        "public_suite": "IMMUTABLE",
        "private_evaluator_key": "IMMUTABLE",
        "prompt_policy": "IMMUTABLE",
        "model_binding": "IMMUTABLE",
        "thresholds": "IMMUTABLE",
        "adapter_v2_source_hashes": "IMMUTABLE_FOR_AUTHORIZED_RUN",
        "qwen3_transport_source_hash": "IMMUTABLE_FOR_AUTHORIZED_RUN",
        "change_consequence": (
            "VOID_SUITE_AND_REQUIRE_NEW_SUITE_ID_SEED_FREEZE"
        ),
    }
    if freeze.get("post_freeze_mutation_policy") != mutation_policy:
        raise StrongBaselineError("QWEN3_MUTATION_POLICY_INVALID")
    return {
        "one_run_authorization": required_authorization,
        "prohibited_tuning_source_count": len(required_prohibited),
        "post_freeze_mutation_policy": "PASS",
        "status": "PASS",
    }


def _dependency_hash_audit(restricted_dir: Path) -> dict[str, Any]:
    freeze = _load_json(restricted_dir / "freeze_manifest.json")
    checked: list[str] = []
    implementation = freeze.get("implementation_binding", {})
    for name in (
        "suite_generator",
        "adapter",
        "contracts",
        "generation_cli",
        "independent_audit",
        "qwen3_native_transport",
    ):
        record = implementation.get(name, {})
        path = Path(str(record.get("path", "")))
        if not path.is_file() or record.get("file_sha256") != _sha256_file(
            path
        ):
            raise StrongBaselineError("QWEN3_IMPLEMENTATION_HASH_MISMATCH")
        checked.append(str(path))
    evidence = freeze.get("model_snapshot_evidence", {})
    for name in (
        "acquisition_manifest",
        "local_manifest",
        "snapshot_sha256s",
    ):
        record = evidence.get(name, {})
        path = Path(str(record.get("path", "")))
        if not path.is_file() or record.get("file_sha256") != _sha256_file(
            path
        ):
            raise StrongBaselineError("QWEN3_MODEL_EVIDENCE_HASH_MISMATCH")
        checked.append(str(path))
    prohibited_run_artifacts = (
        "authorization_claim.json",
        "submission.json",
        "raw_attempts.jsonl",
        "run_metadata.json",
        "evaluator_report.json",
        "component_audit.json",
    )
    existing = [
        name
        for name in prohibited_run_artifacts
        if (restricted_dir / name).exists()
    ]
    if existing:
        raise StrongBaselineError(
            "QWEN3_PREMATURE_RUN_ARTIFACT_DETECTED",
            details={"files": existing},
        )
    return {
        "checked_file_count": len(checked),
        "checked_files": checked,
        "premature_run_artifacts": [],
        "status": "PASS",
    }


def _freeze_seal_audit(
    restricted_dir: Path,
    public: dict[str, Any],
) -> dict[str, Any]:
    freeze_seal = _load_json(restricted_dir / "freeze_seal.json")
    if freeze_seal.get("schema_version") != FREEZE_SEAL_SCHEMA_VERSION:
        raise StrongBaselineError("QWEN3_FREEZE_SEAL_SCHEMA_MISMATCH")
    if freeze_seal.get("state") != "GOVERNANCE_FROZEN_NOT_RUN":
        raise StrongBaselineError("QWEN3_FREEZE_SEAL_STATE_INVALID")
    expected_paths = {
        str(PUBLIC_PACKET),
        str(RESTRICTED_DIR / "public_suite.json"),
        str(RESTRICTED_DIR / "private_labels.json"),
        str(RESTRICTED_DIR / "generation_manifest.json"),
        str(RESTRICTED_DIR / "prompt_policy.json"),
        str(RESTRICTED_DIR / "seal.json"),
        str(RESTRICTED_DIR / "freeze_manifest.json"),
    }
    files = freeze_seal.get("files", {})
    if set(files) != expected_paths:
        raise StrongBaselineError("QWEN3_FREEZE_SEAL_FILE_SET_INVALID")
    for relative, recorded in files.items():
        path = Path(relative)
        if not path.is_file():
            raise StrongBaselineError("QWEN3_FREEZE_SEALED_FILE_MISSING")
        if recorded.get("bytes") != path.stat().st_size:
            raise StrongBaselineError("QWEN3_FREEZE_SEALED_SIZE_MISMATCH")
        if recorded.get("sha256") != _sha256_file(path):
            raise StrongBaselineError("QWEN3_FREEZE_SEALED_HASH_MISMATCH")
    freeze = _load_json(restricted_dir / "freeze_manifest.json")
    required_semantic = {
        "model_binding": sha256_json(public["binding"]),
        "prompt_policy": PROMPT_POLICY_SHA256,
        "gate_c_thresholds": sha256_json(CONTROLLER_FINALIZER_THRESHOLDS),
        "one_run_authorization": sha256_json(
            freeze["one_run_authorization"]
        ),
        "prohibited_tuning_sources": sha256_json(
            freeze["prohibited_tuning_sources"]
        ),
    }
    if freeze_seal.get("semantic_hashes") != required_semantic:
        raise StrongBaselineError("QWEN3_FREEZE_SEMANTIC_HASH_MISMATCH")
    return {
        "sealed_file_count": len(expected_paths),
        "semantic_hashes": required_semantic,
        "status": "PASS",
    }


def audit(restricted_dir: Path) -> dict[str, Any]:
    """Run the complete no-private-parse freeze audit."""

    public = _load_json(restricted_dir / "public_suite.json")
    manifest = _load_json(restricted_dir / "generation_manifest.json")
    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "task_id": 182,
        "date": EXPECTED_DATE,
        "suite_id": EXPECTED_SUITE_ID,
        "freeze_label": EXPECTED_FREEZE_LABEL,
        "decision_token": DECISION_TOKEN,
        "schema_validation": _validate_public_schema(public),
        "aggregate_composition": _validate_aggregate_composition(
            public,
            manifest,
        ),
        "overlap_audit": _overlap_audit(public),
        "content_audit": _content_audit(public),
        "seal_audit": _seal_audit(restricted_dir, public, manifest),
        "authorization_audit": _authorization_audit(
            restricted_dir,
            public,
        ),
        "dependency_hash_audit": _dependency_hash_audit(restricted_dir),
        "freeze_seal_audit": _freeze_seal_audit(restricted_dir, public),
        "private_target_policy": {
            "private_labels_loaded_or_parsed": False,
            "validation_basis": (
                "sealed bytes/hash plus generation-manifest aggregate counts"
            ),
        },
        "model_inference_executed": False,
        "qwen3_loaded_or_run": False,
        "scientific_source_content_used": False,
        "status": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--restricted-dir", type=Path, default=RESTRICTED_DIR)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(args.restricted_dir)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
        return 0
    args.output.write_text(rendered, encoding="utf-8")
    if args.output.stat().st_mode & 0o077:
        args.output.chmod(0o600)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
