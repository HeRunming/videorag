from __future__ import annotations

import json
from pathlib import Path

import pytest

from av_trace_strong_baselines.errors import StrongBaselineError
from av_trace_strong_baselines_v2 import (
    AttemptKind,
    FactorStatus,
    ProjectionStatus,
    RawFactorAttempt,
    build_native_action_plan,
    controller_factor_contracts,
    finalizer_factor_contracts,
    generator_contract,
    parse_controller_factors,
    parse_finalizer_factors,
    run_task172_structural_regression,
    validate_future_seed,
)

ROOT = Path(__file__).resolve().parents[1]


def _search(tool: str, query: str) -> dict:
    arguments = {
        "query": query,
        "top_k": 5,
        "time_range": {"start_s": 0.0, "end_s": 20.0},
        "exclude_result_ids": [],
    }
    if tool == "search_speech":
        arguments["speaker_hint"] = None
    return {"tool": tool, "arguments": arguments}


def _attempt(
    value: object,
    *,
    index: int = 1,
    kind: AttemptKind = AttemptKind.INITIAL,
) -> RawFactorAttempt:
    return RawFactorAttempt.from_text(
        json.dumps(value),
        attempt_index=index,
        kind=kind,
    )


def _state(**overrides: object) -> dict:
    value = {
        "p_sufficient": 0.0,
        "covered_claim_handles": [],
        "missing_modalities": ["vision"],
        "missing_hops": ["entity_identity"],
        "missingness_cause": "evidence_accessible_but_not_found",
        "recovery_intent": "search_vision",
    }
    value.update(overrides)
    return value


def _observations() -> list[dict]:
    return [
        {
            "observation_id": "public.obs.1",
            "interval": {"start_s": 0.0, "end_s": 1.0},
            "modalities": ["vision"],
            "payload": {"text": "The fictional prism is cerulean."},
        }
    ]


def _valid_answer_factors() -> dict[str, tuple[RawFactorAttempt, ...]]:
    return {
        "disposition": (
            _attempt(
                {
                    "p_sufficient": 1.0,
                    "verdict": "sufficient",
                    "answer_mode": "answer",
                    "termination_reason": "sufficient_evidence",
                }
            ),
        ),
        "answer_text": (
            _attempt({"text": "The fictional prism is cerulean."}),
        ),
        "claim_drafts": (
            _attempt(
                {
                    "claims": [
                        {
                            "claim_id": "public.claim.1",
                            "registered_claim_id": "public.slot.1",
                            "text": "The fictional prism is cerulean.",
                            "confidence": 1.0,
                        }
                    ]
                }
            ),
        ),
        "citation_selections": (
            _attempt(
                {
                    "selections": [
                        {
                            "registered_claim_id": "public.slot.1",
                            "observation_ids": ["public.obs.1"],
                        }
                    ]
                }
            ),
        ),
        "diagnosis": (
            _attempt(
                {
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
                    "description": "The public observation directly supports the claim.",
                }
            ),
        ),
    }


def test_native_action_choice_is_separate_from_state_projection() -> None:
    menu = [
        _search("search_speech", "fictional spoken code"),
        _search("search_visual", "fictional prism color"),
    ]
    plan = build_native_action_plan(menu)
    result = parse_controller_factors(
        action_menu=menu,
        claim_handles=["public.slot.1"],
        observed_evidence=[],
        action_attempts=(
            _attempt(
                {
                    "function_name": plan.function_name_for_index(1),
                    "arguments": {},
                }
            ),
        ),
        evidence_state_attempts=(
            _attempt(
                _state(
                    covered_claim_handles=["public.slot.1"],
                    missing_modalities=["vision"],
                )
            ),
        ),
    )
    assert result.action_factor.status is FactorStatus.VALID
    assert result.native_action is not None
    assert result.native_action.action["tool"] == "search_visual"
    assert result.state_projection.status is ProjectionStatus.REJECTED
    assert result.state_projection.evidence_state is None
    assert result.canonical_decision is None


def test_controller_contract_uses_required_no_argument_native_tools() -> None:
    contract = controller_factor_contracts(
        action_menu=[
            _search("search_visual", "fictional prism color"),
            {"tool": "finalize", "arguments": {}},
        ],
        claim_handles=["public.slot.1"],
    )
    action_factor = contract["factors"][0]
    assert action_factor["transport"] == "granite_native_function_call"
    assert action_factor["tool_choice"] == "required"
    assert action_factor["parallel_tool_calls"] is False
    assert all(
        tool["function"]["parameters"]["properties"] == {}
        for tool in action_factor["tools"]
    )


def test_factor_retry_is_at_most_one_and_cannot_change_content() -> None:
    menu = [_search("search_visual", "fictional prism color")]
    plan = build_native_action_plan(menu)
    result = parse_controller_factors(
        action_menu=menu,
        claim_handles=["public.slot.1"],
        observed_evidence=[],
        action_attempts=(
            RawFactorAttempt.from_text(
                '{"function_name":"select_action_00","arguments":[]}',
            ),
            _attempt(
                {
                    "function_name": plan.function_name_for_index(0),
                    "arguments": {},
                },
                index=2,
                kind=AttemptKind.SCHEMA_ONLY_RETRY,
            ),
        ),
        evidence_state_attempts=(_attempt(_state()),),
    )
    assert result.action_factor.status is FactorStatus.VALID
    assert len(result.action_factor.attempts) == 2
    assert (
        result.action_factor.attempts[0].raw_output
        == b'{"function_name":"select_action_00","arguments":[]}'
    )

    changed = parse_controller_factors(
        action_menu=menu,
        claim_handles=["public.slot.1"],
        observed_evidence=[],
        action_attempts=(
            RawFactorAttempt.from_text(
                '{"function_name":"not_a_menu_entry","arguments":[]}',
            ),
            _attempt(
                {
                    "function_name": plan.function_name_for_index(0),
                    "arguments": {},
                },
                index=2,
                kind=AttemptKind.SCHEMA_ONLY_RETRY,
            ),
        ),
        evidence_state_attempts=(_attempt(_state()),),
    )
    assert changed.action_factor.status is FactorStatus.INVALID_OUTPUT
    assert changed.action_factor.error_code == "SEMANTIC_RETRY_FORBIDDEN"


def test_finalizer_serialization_is_mechanical_and_preserves_authored_text() -> None:
    factors = _valid_answer_factors()
    result = parse_finalizer_factors(
        claim_handles=["public.slot.1"],
        observations=_observations(),
        attempts_by_factor=factors,
    )
    assert result.projection_status is ProjectionStatus.ACCEPTED
    envelope = result.canonical_envelope
    assert envelope is not None
    final = envelope["final_answer"]
    assert final["natural_language_answer"] == (
        "The fictional prism is cerulean."
    )
    assert final["claims"][0]["text"] == "The fictional prism is cerulean."
    assert final["claims"][0]["citations"] == [
        {
            "observation_id": "public.obs.1",
            "interval": {"start_s": 0.0, "end_s": 1.0},
            "modalities": ["vision"],
        }
    ]
    assert envelope["claim_to_citations"] == {
        "public.slot.1": ["public.obs.1"]
    }


def test_finalizer_rejects_missing_claim_without_answer_substitution() -> None:
    factors = _valid_answer_factors()
    factors["claim_drafts"] = (_attempt({"claims": []}),)
    factors["citation_selections"] = (_attempt({"selections": []}),)
    result = parse_finalizer_factors(
        claim_handles=["public.slot.1"],
        observations=_observations(),
        attempts_by_factor=factors,
    )
    assert result.projection_status is ProjectionStatus.REJECTED
    assert result.projection_error_code == "ANSWER_MISSING_REQUIRED_CLAIMS"
    assert result.canonical_envelope is None


def test_finalizer_contract_is_five_factor_strict_interface() -> None:
    contract = finalizer_factor_contracts(
        claim_handles=["public.slot.1"],
        observation_ids=["public.obs.1"],
    )
    assert [item["factor_id"] for item in contract["factors"]] == [
        "finalizer.disposition",
        "finalizer.answer_text",
        "finalizer.claim_drafts",
        "finalizer.citation_selections",
        "finalizer.diagnosis",
    ]
    assert contract["retry_policy"] == {
        "maximum_schema_only_retries_per_factor": 1,
        "semantic_retry": False,
        "cross_factor_retry": False,
    }
    assert contract["answer_substitution"] is False


def test_future_generator_is_capable_but_not_instantiated_by_registry() -> None:
    contract = generator_contract()
    assert contract["task175_instantiated"] is False
    assert contract["task175_evaluated"] is False
    assert contract["requires_caller_supplied_new_seed"] is True
    with pytest.raises(
        StrongBaselineError,
        match="FUTURE_SUITE_SEED_NOT_NEW",
    ):
        validate_future_seed(15820260924)


def test_task172_dev_regression_is_offline_and_not_evaluation() -> None:
    report = run_task172_structural_regression(ROOT)
    assert report["not_a_competence_evaluation"] is True
    assert report["task172_evaluator_rerun"] is False
    assert report["model_inference_executed"] is False
    assert report["scientific_family_accessed"] is False
    assert report["inputs"]["raw_attempts"]["attempt_count"] == 54
    assert report["v2_structural_partition"]["controller"][
        "partitioned_action_factor_valid"
    ] == 24
