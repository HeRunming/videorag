#!/usr/bin/env python3
"""Independent public-surface and aggregate audit for the Task-176 holdout.

This audit deliberately does not load ``private_labels.json``. It verifies
the private file only by sealed bytes/hash and checks private-label balance
only through aggregate counts frozen in ``generation_manifest.json``.
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
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from av_trace_strong_baselines.competence import (
    CONTROLLER_FINALIZER_THRESHOLDS,
)
from av_trace_strong_baselines.contracts import (
    PRIMARY_BINDINGS,
    canonical_json_bytes,
    sha256_json,
)
from av_trace_strong_baselines.errors import (
    StrongBaselineError,
)
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
from av_trace_strong_baselines_v2.suite_generator import (
    CONTROLLER_PROMPT_POLICY,
    FINALIZER_PROMPT_POLICY,
    GENERATOR_SCHEMA_VERSION,
    PROMPT_POLICY,
    PROMPT_POLICY_SHA256,
    PUBLIC_SUITE_SCHEMA_VERSION,
    RUNTIME_FIXTURES,
    SEAL_SCHEMA_VERSION,
)

AUDIT_SCHEMA_VERSION = "av-trace.granite-v2-holdout-audit/1.0"
EXPECTED_SUITE_ID = "granite-v2-fictional-holdout-20261002"
EXPECTED_FREEZE_LABEL = "GRANITE_ADAPTER_V2_HOLDOUT_2026-10-02"
EXPECTED_DATE = "2026-10-02"
RESTRICTED_DIR = Path(
    "data/restricted/strong_baselines/granite_v2_holdout"
)
PUBLIC_PACKET = Path(
    "data/rehearsal_plan/granite_adapter_v2_holdout_public.json"
)
V1_PUBLIC = Path(
    "data/rehearsal_plan/strong_baseline_competence_suite_v1.json"
)
TASK172_RUNNER = Path("tools/granite33_competence.py")

MODEL_BINDING = {
    "repo_id": "ibm-granite/granite-3.3-8b-instruct",
    "revision": "51dd4bc2ade4059a6bd87649d68aa11e4fb2529b",
    "processor_revision": "51dd4bc2ade4059a6bd87649d68aa11e4fb2529b",
    "tokenizer_revision": "51dd4bc2ade4059a6bd87649d68aa11e4fb2529b",
}

GENERIC_TOKENS = frozenset(
    {
        "a",
        "an",
        "and",
        "answer",
        "card",
        "complete",
        "completed",
        "fictional",
        "fixture",
        "for",
        "in",
        "invented",
        "is",
        "item",
        "mark",
        "missing",
        "of",
        "on",
        "public",
        "recorded",
        "sealed",
        "signal",
        "the",
        "this",
        "to",
        "trial",
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
        raise StrongBaselineError("AUDIT_JSON_NOT_OBJECT")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
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


def _task172_prompt_strings() -> tuple[str, str]:
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
    return (
        values["_controller_system_prompt"],
        values["_finalizer_system_prompt"],
    )


def _validate_public_schema(public: dict[str, Any]) -> dict[str, Any]:
    if public.get("schema_version") != PUBLIC_SUITE_SCHEMA_VERSION:
        raise StrongBaselineError("HOLDOUT_PUBLIC_SCHEMA_VERSION_MISMATCH")
    if public.get("suite_id") != EXPECTED_SUITE_ID:
        raise StrongBaselineError("HOLDOUT_SUITE_ID_MISMATCH")
    if public.get("freeze_label") != EXPECTED_FREEZE_LABEL:
        raise StrongBaselineError("HOLDOUT_FREEZE_LABEL_MISMATCH")
    if public.get("generated_date") != EXPECTED_DATE:
        raise StrongBaselineError("HOLDOUT_DATE_MISMATCH")
    if public.get("adapter_schema_version") != ADAPTER_SCHEMA_VERSION:
        raise StrongBaselineError("HOLDOUT_ADAPTER_SCHEMA_MISMATCH")
    if public.get("execution_status") != "SEALED_NOT_RUN":
        raise StrongBaselineError("HOLDOUT_EXECUTION_STATUS_INVALID")
    if public.get("thresholds") != CONTROLLER_FINALIZER_THRESHOLDS:
        raise StrongBaselineError("HOLDOUT_THRESHOLDS_MISMATCH")
    boundary = public.get("content_boundary", {})
    if boundary != {
        "fictional_generated_primitives_only": True,
        "scientific_family_content": False,
        "real_source_content": False,
        "model_results_present": False,
        "private_labels_present": False,
    }:
        raise StrongBaselineError("HOLDOUT_CONTENT_BOUNDARY_INVALID")
    binding = public.get("binding", {})
    for role in ("controller", "finalizer"):
        observed = binding.get(role, {})
        expected = PRIMARY_BINDINGS[role].to_dict()
        if observed != expected:
            raise StrongBaselineError("HOLDOUT_MODEL_BINDING_MISMATCH")
        for key, value in MODEL_BINDING.items():
            if observed.get(key) != value:
                raise StrongBaselineError("HOLDOUT_MODEL_IDENTITY_MISMATCH")
    if binding.get("same_exact_snapshot_required") is not True:
        raise StrongBaselineError("HOLDOUT_SAME_SNAPSHOT_NOT_REQUIRED")
    prompt = public.get("prompt_policy", {})
    if prompt.get("sha256") != PROMPT_POLICY_SHA256:
        raise StrongBaselineError("HOLDOUT_PROMPT_POLICY_HASH_MISMATCH")
    cases = public.get("cases")
    if not isinstance(cases, list) or len(cases) != 51:
        raise StrongBaselineError("HOLDOUT_CASE_COUNT_INVALID")
    ids = [case.get("case_id") for case in cases]
    if any(not isinstance(case_id, str) for case_id in ids):
        raise StrongBaselineError("HOLDOUT_CASE_ID_INVALID")
    if len(ids) != len(set(ids)):
        raise StrongBaselineError("HOLDOUT_CASE_ID_DUPLICATE")
    for case in cases:
        if set(case) != {"case_id", "case_type", "stratum", "public_input"}:
            raise StrongBaselineError("HOLDOUT_CASE_FIELD_SET_INVALID")
        assert_public_surface(case)
        public_input = case["public_input"]
        slots = public_input.get("public_claim_slots")
        if not isinstance(slots, list) or len(slots) != 1:
            raise StrongBaselineError("HOLDOUT_CLAIM_SLOT_COUNT_INVALID")
        handles = [slots[0]["claim_handle"]]
        if case["case_type"] == "controller":
            menu = public_input.get("action_menu")
            if not isinstance(menu, list) or not menu:
                raise StrongBaselineError("HOLDOUT_ACTION_MENU_INVALID")
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
                raise StrongBaselineError("HOLDOUT_OBSERVATIONS_INVALID")
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
                raise StrongBaselineError("HOLDOUT_RUNTIME_FIXTURE_MISMATCH")
        else:
            raise StrongBaselineError("HOLDOUT_CASE_TYPE_INVALID")
    return {
        "case_count": len(cases),
        "unique_case_ids": len(set(ids)),
        "public_surface": "PASS",
        "adapter_contract_schema": "PASS",
    }


def _validate_aggregate_composition(
    public: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    cases = public["cases"]
    actual_types = Counter(case["case_type"] for case in cases)
    expected_types = {
        "controller": 24,
        "finalizer": 16,
        "runtime_failure": 11,
    }
    if dict(actual_types) != expected_types:
        raise StrongBaselineError("HOLDOUT_CASE_COMPOSITION_INVALID")
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
    if actual_strata["controller"] != expected_controller:
        raise StrongBaselineError("HOLDOUT_CONTROLLER_STRATA_INVALID")
    if actual_strata["finalizer"] != expected_finalizer:
        raise StrongBaselineError("HOLDOUT_FINALIZER_STRATA_INVALID")
    if actual_strata["runtime_failure"] != expected_runtime:
        raise StrongBaselineError("HOLDOUT_RUNTIME_STRATA_INVALID")
    policies = Counter(
        case["public_input"]["controller_policy"]
        for case in cases
        if case["case_type"] == "controller"
    )
    if dict(policies) != {"react_v2": 12, "sufficiency_v2": 12}:
        raise StrongBaselineError("HOLDOUT_CONTROLLER_POLICY_BALANCE_INVALID")
    aggregate = manifest.get("aggregate_composition")
    if not isinstance(aggregate, dict):
        raise StrongBaselineError("HOLDOUT_AGGREGATE_COMPOSITION_MISSING")
    if aggregate.get("case_types") != expected_types:
        raise StrongBaselineError("HOLDOUT_PRIVATE_AGGREGATE_CASE_TYPES_INVALID")
    if aggregate.get("strata") != actual_strata:
        raise StrongBaselineError("HOLDOUT_PRIVATE_AGGREGATE_STRATA_INVALID")
    private = aggregate.get("private_label_aggregates", {})
    expected_tools = {
        "finalize": 6,
        "get_channel_status": 3,
        "inspect_clip": 3,
        "search_ambient_audio": 3,
        "search_speech": 6,
        "search_visual": 3,
    }
    if private.get("controller_expected_tools") != expected_tools:
        raise StrongBaselineError("HOLDOUT_PRIVATE_TOOL_BALANCE_INVALID")
    if private.get("finalizer_answer_modes") != {
        "abstain": 4,
        "answer": 12,
    }:
        raise StrongBaselineError("HOLDOUT_PRIVATE_FINALIZER_BALANCE_INVALID")
    if private.get("finalizer_required_modalities") != {
        "ambient": 5,
        "speech": 5,
        "vision": 6,
    }:
        raise StrongBaselineError("HOLDOUT_PRIVATE_MODALITY_BALANCE_INVALID")
    if private.get("finalizer_required_missing_hops") != {
        "ambient_event": 1,
        "event_detection": 1,
        "speech_content": 1,
        "temporal_order": 1,
    }:
        raise StrongBaselineError("HOLDOUT_PRIVATE_HOP_BALANCE_INVALID")
    if private.get("runtime_expected_model_called") != {
        "false": 2,
        "true": 9,
    }:
        raise StrongBaselineError("HOLDOUT_RUNTIME_CALL_BALANCE_INVALID")
    state_heads = private.get("controller_state_heads", {})
    expected_state_aggregates = (
        set(EVIDENCE_STATE_FIELDS) - {"covered_claim_handles"}
    ) | {"covered_claim_count"}
    if set(state_heads) != expected_state_aggregates:
        raise StrongBaselineError("HOLDOUT_STATE_HEAD_AGGREGATES_INVALID")
    for required_value in ("0.0", "1.0"):
        if state_heads["p_sufficient"].get(required_value, 0) < 3:
            raise StrongBaselineError("HOLDOUT_P_SUFFICIENT_BALANCE_INVALID")
    for modality in ("vision", "speech", "ambient"):
        if state_heads["missing_modalities"].get(modality, 0) < 3:
            raise StrongBaselineError("HOLDOUT_STATE_MODALITY_BALANCE_INVALID")
    for cause in (
        "evidence_accessible_but_not_found",
        "evidence_in_source_but_inaccessible",
        "not_missing",
    ):
        if state_heads["missingness_cause"].get(cause, 0) < 3:
            raise StrongBaselineError("HOLDOUT_STATE_CAUSE_BALANCE_INVALID")
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
            raise StrongBaselineError("HOLDOUT_STATE_INTENT_BALANCE_INVALID")
    return {
        "case_types": expected_types,
        "controller_strata": expected_controller,
        "finalizer_strata": expected_finalizer,
        "runtime_strata": expected_runtime,
        "controller_policy_balance": dict(policies),
        "private_label_aggregate_only": True,
        "private_label_aggregates": private,
    }


def _overlap_audit(
    public: dict[str, Any],
    old_public: dict[str, Any],
) -> dict[str, Any]:
    new_cases = [
        case
        for case in public["cases"]
        if case["case_type"]
        in {"controller", "finalizer", "runtime_failure"}
    ]
    old_cases = [
        case
        for case in _public_case_rows(old_public)
        if case.get("case_type")
        in {"controller", "finalizer", "runtime_failure"}
        and not str(case.get("case_id", "")).startswith(
            "sbc-direct-failure-"
        )
    ]
    exact_public_inputs = 0
    exact_questions = 0
    maximum_sequence_ratio = 0.0
    maximum_token_jaccard = 0.0
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
        if new_hash in old_input_hashes:
            exact_public_inputs += 1
        new_question = _normalize(
            new_case["public_input"].get("question", "")
        )
        if new_question in old_questions:
            exact_questions += 1
        new_text = _case_text(new_case)
        new_tokens = _tokens(new_text)
        for old_case in old_cases:
            old_text = _case_text(old_case)
            old_tokens = _tokens(old_text)
            sequence_ratio = SequenceMatcher(
                None,
                _normalize(new_text),
                _normalize(old_text),
                autojunk=False,
            ).ratio()
            union = new_tokens | old_tokens
            token_jaccard = (
                len(new_tokens & old_tokens) / len(union) if union else 0.0
            )
            if (
                (
                    sequence_ratio > maximum_sequence_ratio
                    or token_jaccard > maximum_token_jaccard
                )
                and sequence_ratio + token_jaccard
                > maximum_sequence_ratio + maximum_token_jaccard
            ):
                closest_pair = {
                    "new_case_id": new_case["case_id"],
                    "old_case_id": old_case["case_id"],
                    "sequence_ratio": round(sequence_ratio, 6),
                    "token_jaccard": round(token_jaccard, 6),
                }
            maximum_sequence_ratio = max(
                maximum_sequence_ratio, sequence_ratio
            )
            maximum_token_jaccard = max(
                maximum_token_jaccard, token_jaccard
            )
    old_controller_prompt, old_finalizer_prompt = _task172_prompt_strings()
    prompt_checks = {
        "controller_exact_match": (
            _normalize(CONTROLLER_PROMPT_POLICY)
            == _normalize(old_controller_prompt)
        ),
        "finalizer_exact_match": (
            _normalize(FINALIZER_PROMPT_POLICY)
            == _normalize(old_finalizer_prompt)
        ),
        "controller_sequence_ratio": round(
            SequenceMatcher(
                None,
                _normalize(CONTROLLER_PROMPT_POLICY),
                _normalize(old_controller_prompt),
                autojunk=False,
            ).ratio(),
            6,
        ),
        "finalizer_sequence_ratio": round(
            SequenceMatcher(
                None,
                _normalize(FINALIZER_PROMPT_POLICY),
                _normalize(old_finalizer_prompt),
                autojunk=False,
            ).ratio(),
            6,
        ),
    }
    if exact_public_inputs or exact_questions:
        raise StrongBaselineError("HOLDOUT_EXACT_OVERLAP_DETECTED")
    if maximum_sequence_ratio >= 0.84 or maximum_token_jaccard >= 0.72:
        raise StrongBaselineError("HOLDOUT_NEAR_DUPLICATE_DETECTED")
    if (
        prompt_checks["controller_exact_match"]
        or prompt_checks["finalizer_exact_match"]
        or prompt_checks["controller_sequence_ratio"] >= 0.80
        or prompt_checks["finalizer_sequence_ratio"] >= 0.80
    ):
        raise StrongBaselineError("HOLDOUT_PROMPT_NEAR_DUPLICATE_DETECTED")
    return {
        "comparison_public_suite": str(V1_PUBLIC),
        "comparison_prompt_source": str(TASK172_RUNNER),
        "new_public_cases": len(new_cases),
        "old_public_controller_finalizer_cases": len(old_cases),
        "pairwise_public_case_comparisons": len(new_cases) * len(old_cases),
        "exact_public_input_matches": exact_public_inputs,
        "exact_question_matches": exact_questions,
        "maximum_sequence_ratio": round(maximum_sequence_ratio, 6),
        "maximum_token_jaccard": round(maximum_token_jaccard, 6),
        "thresholds": {
            "sequence_ratio_strictly_below": 0.84,
            "token_jaccard_strictly_below": 0.72,
            "prompt_sequence_ratio_strictly_below": 0.80,
        },
        "closest_pair": closest_pair,
        "prompt_checks": prompt_checks,
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
            "HOLDOUT_REAL_OR_SCIENTIFIC_CONTENT_DETECTED",
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
        raise StrongBaselineError("HOLDOUT_SEAL_SCHEMA_MISMATCH")
    if seal.get("state") != "SEALED_BEFORE_MODEL_EXECUTION":
        raise StrongBaselineError("HOLDOUT_SEAL_STATE_INVALID")
    expected_names = {
        "public_suite.json",
        "private_labels.json",
        "generation_manifest.json",
        "prompt_policy.json",
    }
    if set(seal.get("files", {})) != expected_names:
        raise StrongBaselineError("HOLDOUT_SEAL_FILE_SET_INVALID")
    for name, recorded in seal["files"].items():
        path = restricted_dir / name
        if not path.is_file():
            raise StrongBaselineError("HOLDOUT_SEALED_FILE_MISSING")
        if recorded.get("bytes") != path.stat().st_size:
            raise StrongBaselineError("HOLDOUT_SEALED_FILE_SIZE_MISMATCH")
        if recorded.get("sha256") != _sha256_file(path):
            raise StrongBaselineError("HOLDOUT_SEALED_FILE_HASH_MISMATCH")
    if (
        seal["semantic_hashes"].get("public_suite")
        != "sha256:" + hashlib.sha256(canonical_json_bytes(public)).hexdigest()
    ):
        raise StrongBaselineError("HOLDOUT_PUBLIC_SEMANTIC_HASH_MISMATCH")
    if (
        manifest.get("public_suite_sha256")
        != seal["semantic_hashes"]["public_suite"]
    ):
        raise StrongBaselineError("HOLDOUT_MANIFEST_PUBLIC_HASH_MISMATCH")
    private_path = restricted_dir / "private_labels.json"
    if (
        manifest.get("private_labels_sha256")
        != seal["semantic_hashes"]["private_labels"]
    ):
        raise StrongBaselineError("HOLDOUT_MANIFEST_PRIVATE_HASH_MISMATCH")
    if seal["semantic_hashes"].get("prompt_policy") != PROMPT_POLICY_SHA256:
        raise StrongBaselineError("HOLDOUT_PROMPT_SEMANTIC_HASH_MISMATCH")
    prompt = _load_json(restricted_dir / "prompt_policy.json")
    if prompt != PROMPT_POLICY:
        raise StrongBaselineError("HOLDOUT_PROMPT_POLICY_CONTENT_MISMATCH")
    public_copy = _load_json(PUBLIC_PACKET)
    if canonical_json_bytes(public_copy) != canonical_json_bytes(public):
        raise StrongBaselineError("HOLDOUT_PUBLIC_PACKET_COPY_MISMATCH")
    if manifest.get("schema_version") != GENERATOR_SCHEMA_VERSION:
        raise StrongBaselineError("HOLDOUT_MANIFEST_SCHEMA_MISMATCH")
    if manifest.get("private_target_manual_inspection") is not False:
        raise StrongBaselineError("HOLDOUT_PRIVATE_INSPECTION_FLAG_INVALID")
    if manifest.get("model_used") is not False:
        raise StrongBaselineError("HOLDOUT_MODEL_USE_FLAG_INVALID")
    if manifest.get("scientific_source_used") is not False:
        raise StrongBaselineError("HOLDOUT_SCIENTIFIC_SOURCE_FLAG_INVALID")
    return {
        "sealed_file_count": len(expected_names),
        "private_labels_file_sha256": _sha256_file(private_path),
        "private_labels_file_bytes": private_path.stat().st_size,
        "private_labels_parsed_by_independent_audit": False,
        "public_packet_copy_match": True,
        "status": "PASS",
    }


def _authorization_audit(
    restricted_dir: Path,
    public: dict[str, Any],
) -> dict[str, Any]:
    freeze = _load_json(restricted_dir / "freeze_manifest.json")
    if freeze.get("schema_version") != "av-trace.granite-v2-freeze/1.0":
        raise StrongBaselineError("HOLDOUT_FREEZE_MANIFEST_SCHEMA_MISMATCH")
    if freeze.get("suite_id") != EXPECTED_SUITE_ID:
        raise StrongBaselineError("HOLDOUT_FREEZE_MANIFEST_SUITE_MISMATCH")
    if freeze.get("freeze_label") != EXPECTED_FREEZE_LABEL:
        raise StrongBaselineError("HOLDOUT_FREEZE_MANIFEST_LABEL_MISMATCH")
    if freeze.get("date") != EXPECTED_DATE:
        raise StrongBaselineError("HOLDOUT_FREEZE_MANIFEST_DATE_MISMATCH")
    if freeze.get("decision_token") != (
        "GRANITE_ADAPTER_V2_HOLDOUT_FROZEN"
    ):
        raise StrongBaselineError("HOLDOUT_FREEZE_DECISION_MISMATCH")
    if freeze.get("model_binding") != public.get("binding"):
        raise StrongBaselineError("HOLDOUT_FREEZE_MODEL_BINDING_MISMATCH")
    if freeze.get("prompt_policy", {}).get("sha256") != PROMPT_POLICY_SHA256:
        raise StrongBaselineError("HOLDOUT_FREEZE_PROMPT_HASH_MISMATCH")
    if freeze.get("gate_c_thresholds") != CONTROLLER_FINALIZER_THRESHOLDS:
        raise StrongBaselineError("HOLDOUT_FREEZE_THRESHOLD_MISMATCH")
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
        "pre_run_seal_and_environment_verification_required": True,
        "post_run_evaluator_replay_count": 1,
    }
    if authorization != required_authorization:
        raise StrongBaselineError("HOLDOUT_ONE_RUN_AUTHORIZATION_INVALID")
    prohibited = freeze.get("prohibited_tuning_sources")
    required_prohibited = {
        "private_labels_or_derived_targets",
        "future_holdout_model_outputs",
        "future_holdout_evaluator_reports",
        "future_holdout_component_or_error_audits",
        "manual_review_of_holdout_errors",
        "scientific_family_content_or_keys",
        "task172_private_evaluator_targets",
        "task172_outputs_for_post_freeze_prompt_or_adapter_changes",
        "outcome_conditioned_threshold_prompt_adapter_runtime_or_model_changes",
    }
    if not isinstance(prohibited, list) or set(prohibited) != required_prohibited:
        raise StrongBaselineError("HOLDOUT_PROHIBITED_TUNING_SOURCES_INVALID")
    if freeze.get("post_freeze_mutation_policy") != {
        "public_suite": "IMMUTABLE",
        "private_evaluator_key": "IMMUTABLE",
        "prompt_policy": "IMMUTABLE",
        "model_binding": "IMMUTABLE",
        "thresholds": "IMMUTABLE",
        "adapter_v2_source_hashes": "IMMUTABLE_FOR_AUTHORIZED_RUN",
        "change_consequence": (
            "VOID_SUITE_AND_REQUIRE_NEW_SUITE_ID_SEED_FREEZE"
        ),
    }:
        raise StrongBaselineError("HOLDOUT_MUTATION_POLICY_INVALID")
    return {
        "one_run_authorization": required_authorization,
        "prohibited_tuning_source_count": len(required_prohibited),
        "post_freeze_mutation_policy": "PASS",
        "status": "PASS",
    }


def _dependency_hash_audit(
    restricted_dir: Path,
) -> dict[str, Any]:
    freeze = _load_json(restricted_dir / "freeze_manifest.json")
    checked: list[str] = []
    implementation = freeze.get("implementation_binding", {})
    for name in (
        "suite_generator",
        "adapter",
        "contracts",
        "generation_cli",
        "independent_audit",
    ):
        record = implementation.get(name, {})
        path = Path(str(record.get("path", "")))
        if not path.is_file() or record.get("file_sha256") != _sha256_file(
            path
        ):
            raise StrongBaselineError("HOLDOUT_IMPLEMENTATION_HASH_MISMATCH")
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
            raise StrongBaselineError("HOLDOUT_MODEL_EVIDENCE_HASH_MISMATCH")
        checked.append(str(path))
    prohibited_run_artifacts = (
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
            "HOLDOUT_PREMATURE_RUN_ARTIFACT_DETECTED",
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
    if freeze_seal.get("schema_version") != (
        "av-trace.granite-v2-governance-seal/1.0"
    ):
        raise StrongBaselineError("HOLDOUT_FREEZE_SEAL_SCHEMA_MISMATCH")
    if freeze_seal.get("state") != "GOVERNANCE_FROZEN_NOT_RUN":
        raise StrongBaselineError("HOLDOUT_FREEZE_SEAL_STATE_INVALID")
    expected_paths = {
        "data/rehearsal_plan/granite_adapter_v2_holdout_public.json",
        (
            "data/restricted/strong_baselines/granite_v2_holdout/"
            "public_suite.json"
        ),
        (
            "data/restricted/strong_baselines/granite_v2_holdout/"
            "private_labels.json"
        ),
        (
            "data/restricted/strong_baselines/granite_v2_holdout/"
            "generation_manifest.json"
        ),
        (
            "data/restricted/strong_baselines/granite_v2_holdout/"
            "prompt_policy.json"
        ),
        "data/restricted/strong_baselines/granite_v2_holdout/seal.json",
        (
            "data/restricted/strong_baselines/granite_v2_holdout/"
            "freeze_manifest.json"
        ),
    }
    files = freeze_seal.get("files", {})
    if set(files) != expected_paths:
        raise StrongBaselineError("HOLDOUT_FREEZE_SEAL_FILE_SET_INVALID")
    for relative, recorded in files.items():
        path = Path(relative)
        if not path.is_file():
            raise StrongBaselineError("HOLDOUT_FREEZE_SEALED_FILE_MISSING")
        if recorded.get("bytes") != path.stat().st_size:
            raise StrongBaselineError("HOLDOUT_FREEZE_SEALED_SIZE_MISMATCH")
        if recorded.get("sha256") != _sha256_file(path):
            raise StrongBaselineError("HOLDOUT_FREEZE_SEALED_HASH_MISMATCH")
    freeze = _load_json(restricted_dir / "freeze_manifest.json")
    semantic = freeze_seal.get("semantic_hashes", {})
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
    if semantic != required_semantic:
        raise StrongBaselineError("HOLDOUT_FREEZE_SEMANTIC_HASH_MISMATCH")
    return {
        "sealed_file_count": len(expected_paths),
        "semantic_hashes": required_semantic,
        "status": "PASS",
    }


def audit(restricted_dir: Path) -> dict[str, Any]:
    public = _load_json(restricted_dir / "public_suite.json")
    manifest = _load_json(restricted_dir / "generation_manifest.json")
    old_public = _load_json(V1_PUBLIC)
    schema = _validate_public_schema(public)
    composition = _validate_aggregate_composition(public, manifest)
    overlap = _overlap_audit(public, old_public)
    content = _content_audit(public)
    seal = _seal_audit(restricted_dir, public, manifest)
    authorization = _authorization_audit(restricted_dir, public)
    dependencies = _dependency_hash_audit(restricted_dir)
    freeze_seal = _freeze_seal_audit(restricted_dir, public)
    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "task_id": 176,
        "date": EXPECTED_DATE,
        "suite_id": EXPECTED_SUITE_ID,
        "freeze_label": EXPECTED_FREEZE_LABEL,
        "decision_token": "GRANITE_ADAPTER_V2_HOLDOUT_FROZEN",
        "schema_validation": schema,
        "aggregate_composition": composition,
        "overlap_audit": overlap,
        "content_audit": content,
        "seal_audit": seal,
        "authorization_audit": authorization,
        "dependency_hash_audit": dependencies,
        "freeze_seal_audit": freeze_seal,
        "private_target_policy": {
            "private_labels_loaded_or_parsed": False,
            "validation_basis": (
                "sealed bytes/hash plus generation-manifest aggregate counts"
            ),
        },
        "model_inference_executed": False,
        "granite_loaded": False,
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
    os_mode = args.output.stat().st_mode & 0o777
    if os_mode & 0o077:
        args.output.chmod(0o600)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
