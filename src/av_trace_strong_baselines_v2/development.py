"""Offline structural regression over the already-consumed Task-172 outputs.

This is not a competence evaluator. It never invokes a model, never consults
scientific families, and never changes the frozen Task-172 decision.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from av_trace_strong_baselines.schemas import parse_strict_json

from .adapter import (
    build_native_action_plan,
    parse_controller_factors,
    parse_finalizer_factors,
)
from .contracts import FactorStatus, ProjectionStatus, RawFactorAttempt

TASK172_SUITE = Path(
    "data/rehearsal_plan/strong_baseline_competence_suite_v1.json"
)
TASK172_SUBMISSION = Path(
    "data/restricted/strong_baselines/granite33_competence_v1/submission.json"
)
TASK172_COMPONENT_AUDIT = Path(
    "data/restricted/strong_baselines/granite33_competence_v1/"
    "component_audit.json"
)
TASK172_RAW_ATTEMPTS = Path(
    "data/restricted/strong_baselines/granite33_competence_v1/"
    "raw_attempts.jsonl"
)
EXPECTED_SUITE_HASH = (
    "sha256:7b8f8d021b24cb244f0df0f6b02b3da91120df3817a5366350895eb24f4646dc"
)


class DevelopmentBoundaryError(RuntimeError):
    """The consumed development inputs do not match Task 172."""


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 << 20):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _attempt(value: Any) -> tuple[RawFactorAttempt, ...]:
    return (
        RawFactorAttempt.from_text(
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
        ),
    )


def _legacy_finalizer_factors(
    parsed: Mapping[str, Any],
) -> dict[str, tuple[RawFactorAttempt, ...]]:
    final = parsed.get("final_answer")
    final = final if isinstance(final, Mapping) else {}
    claims = final.get("claims")
    claims = claims if isinstance(claims, list) else []
    claim_drafts = []
    selections = []
    for claim in claims:
        claim = claim if isinstance(claim, Mapping) else {}
        claim_drafts.append(
            {
                key: claim.get(key)
                for key in (
                    "claim_id",
                    "registered_claim_id",
                    "text",
                    "confidence",
                )
            }
        )
        citations = claim.get("citations")
        citations = citations if isinstance(citations, list) else []
        selections.append(
            {
                "registered_claim_id": claim.get("registered_claim_id"),
                "observation_ids": [
                    citation.get("observation_id")
                    for citation in citations
                    if isinstance(citation, Mapping)
                ],
            }
        )
    return {
        "disposition": _attempt(
            {
                key: final.get(key)
                for key in (
                    "p_sufficient",
                    "verdict",
                    "answer_mode",
                    "termination_reason",
                )
            }
        ),
        "answer_text": _attempt(
            {"text": final["natural_language_answer"]}
            if "natural_language_answer" in final
            else {}
        ),
        "claim_drafts": _attempt({"claims": claim_drafts}),
        "citation_selections": _attempt({"selections": selections}),
        "diagnosis": _attempt(final.get("diagnosis", {})),
    }


def run_task172_structural_regression(repo_root: str | Path) -> dict[str, Any]:
    """Replay only structure through v2; never score Task-172 competence."""

    root = Path(repo_root).resolve()
    suite_path = root / TASK172_SUITE
    submission_path = root / TASK172_SUBMISSION
    audit_path = root / TASK172_COMPONENT_AUDIT
    raw_attempts_path = root / TASK172_RAW_ATTEMPTS
    suite = _load(suite_path)
    submission = _load(submission_path)
    audit = _load(audit_path)
    raw_attempts = _load_jsonl(raw_attempts_path)
    if suite.get("suite_hash") != EXPECTED_SUITE_HASH:
        raise DevelopmentBoundaryError("TASK172_SUITE_HASH_MISMATCH")
    if submission.get("suite_hash") != EXPECTED_SUITE_HASH:
        raise DevelopmentBoundaryError("TASK172_SUBMISSION_HASH_MISMATCH")
    if audit.get("task_id") != 172:
        raise DevelopmentBoundaryError("TASK172_COMPONENT_AUDIT_MISMATCH")
    cases = {
        case["case_id"]: case
        for case in suite["cases"]["controller_finalizer"]
        if case["case_type"] in {"controller", "finalizer"}
    }
    results = {
        row["case_id"]: row
        for row in submission["results"]
        if row["case_id"] in cases
    }
    if set(results) != set(cases):
        raise DevelopmentBoundaryError("TASK172_SUBSTANTIVE_CASE_SET_MISMATCH")
    raw_by_case: dict[str, list[str]] = {}
    for attempt in raw_attempts:
        raw = attempt.get("raw_output")
        if isinstance(raw, str):
            raw_by_case.setdefault(str(attempt["case_id"]), []).append(raw)
    if any(
        result.get("raw_output") not in raw_by_case.get(case_id, [])
        for case_id, result in results.items()
    ):
        raise DevelopmentBoundaryError("TASK172_RAW_ATTEMPT_HISTORY_MISMATCH")

    controller_counts: Counter[str] = Counter(
        {
            "cases": 0,
            "legacy_action_index_in_range": 0,
            "partitioned_action_factor_valid": 0,
            "partitioned_state_factor_valid": 0,
            "state_projection_accepted": 0,
            "mechanical_controller_serialized": 0,
        }
    )
    finalizer_counts: Counter[str] = Counter(
        {
            "cases": 0,
            "mechanical_final_serialized": 0,
        }
    )
    factor_validity: Counter[str] = Counter(
        {
            "disposition": 0,
            "answer_text": 0,
            "claim_drafts": 0,
            "citation_selections": 0,
            "diagnosis": 0,
        }
    )
    for case_id, case in cases.items():
        raw = results[case_id].get("raw_output")
        if not isinstance(raw, str):
            continue
        parsed = parse_strict_json(
            raw,
            maximum_bytes=64_000,
        )
        public = case["public_input"]
        claim_handles = [
            item["claim_handle"] for item in public["public_claim_slots"]
        ]
        if case["case_type"] == "controller":
            controller_counts["cases"] += 1
            if not isinstance(parsed, Mapping):
                continue
            index = parsed.get("action_index")
            if (
                isinstance(index, int)
                and not isinstance(index, bool)
                and 0 <= index < len(public["action_menu"])
            ):
                controller_counts["legacy_action_index_in_range"] += 1
                plan = build_native_action_plan(public["action_menu"])
                action_raw = {
                    "function_name": plan.function_name_for_index(index),
                    "arguments": {},
                }
            else:
                action_raw = {"function_name": None, "arguments": {}}
            result = parse_controller_factors(
                action_menu=public["action_menu"],
                claim_handles=claim_handles,
                observed_evidence=public["observed_evidence"],
                action_attempts=_attempt(action_raw),
                evidence_state_attempts=_attempt(
                    parsed.get("evidence_state", {})
                ),
            )
            if result.action_factor.status is FactorStatus.VALID:
                controller_counts["partitioned_action_factor_valid"] += 1
            if result.evidence_state_factor.status is FactorStatus.VALID:
                controller_counts["partitioned_state_factor_valid"] += 1
            if result.state_projection.status is ProjectionStatus.ACCEPTED:
                controller_counts["state_projection_accepted"] += 1
            if result.canonical_decision is not None:
                controller_counts["mechanical_controller_serialized"] += 1
        else:
            finalizer_counts["cases"] += 1
            if not isinstance(parsed, Mapping):
                continue
            factorized = parse_finalizer_factors(
                claim_handles=claim_handles,
                observations=public["observed_evidence"],
                attempts_by_factor=_legacy_finalizer_factors(parsed),
            )
            for name, outcome in factorized.factors.items():
                if outcome.status is FactorStatus.VALID:
                    factor_validity[name] += 1
            if factorized.projection_status is ProjectionStatus.ACCEPTED:
                finalizer_counts["mechanical_final_serialized"] += 1

    return {
        "schema_version": "av-trace.granite-adapter-v2-dev-regression/1.0",
        "task_id": 175,
        "mode": "offline_structural_partition_of_consumed_task172_outputs",
        "not_a_competence_evaluation": True,
        "task172_evaluator_rerun": False,
        "model_inference_executed": False,
        "scientific_family_accessed": False,
        "semantic_fill_or_answer_substitution": False,
        "inputs": {
            "suite": {
                "path": str(TASK172_SUITE),
                "sha256": sha256_file(suite_path),
                "suite_hash": EXPECTED_SUITE_HASH,
            },
            "submission": {
                "path": str(TASK172_SUBMISSION),
                "sha256": sha256_file(submission_path),
            },
            "component_audit": {
                "path": str(TASK172_COMPONENT_AUDIT),
                "sha256": sha256_file(audit_path),
            },
            "raw_attempts": {
                "path": str(TASK172_RAW_ATTEMPTS),
                "sha256": sha256_file(raw_attempts_path),
                "attempt_count": len(raw_attempts),
            },
        },
        "consumed_task172_observation": {
            "raw_action_correct": audit["action_correctness"],
            "raw_p_sufficient": audit["state_heads_raw_exact_match"][
                "p_sufficient"
            ],
            "raw_natural_answer_terms": {
                "oracle": audit["oracle_supported_answers"][
                    "raw_natural_answer_required_terms"
                ],
                "restoration_complete": audit[
                    "restoration_complete_answers"
                ]["raw_natural_answer_required_terms"],
            },
            "frozen_valid_structured_substantive_calls": audit[
                "frozen_metrics"
            ]["valid_structured_model_calls"],
        },
        "v2_structural_partition": {
            "controller": dict(controller_counts),
            "finalizer": {
                **dict(finalizer_counts),
                "valid_factors": dict(factor_validity),
            },
        },
        "interpretation": (
            "Development-only structural diagnostics. Legacy monolithic fields "
            "were partitioned mechanically to exercise v2 parsers; this is "
            "not native v2 model output and does not alter Task-172 scores."
        ),
    }
