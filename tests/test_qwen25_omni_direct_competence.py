from __future__ import annotations

import json
from pathlib import Path

from av_trace_strong_baselines.competence import load_suite
from tools.qwen25_omni_direct_competence import (
    MODEL_REVISION,
    SUITE,
    SUITE_HASH,
    _adapter_context,
    _binding,
    _mapped_exposure,
    _prompt_policy,
    _public_direct_suite,
    _runtime_result,
    _schema_retry_preserved_content,
)

ROOT = Path(__file__).resolve().parents[1]


def test_task198_public_projection_has_no_scoring_targets() -> None:
    suite = load_suite(ROOT / SUITE)
    projected = _public_direct_suite(suite)
    rendered_cases = json.dumps(projected["cases"])
    assert projected["source_suite_hash"] == SUITE_HASH
    assert "scoring_target" not in rendered_cases
    assert "required_terms_by_claim" not in rendered_cases
    assert len(projected["cases"]) == 30


def test_task198_binding_is_exact_qwen_omni() -> None:
    suite = load_suite(ROOT / SUITE)
    binding = _binding(suite["bindings"]["primary_direct"])
    assert binding.revision == MODEL_REVISION
    assert binding.resolved_processor_revision == MODEL_REVISION
    assert binding.resolved_tokenizer_revision == MODEL_REVISION
    assert binding.role == "DIRECT_AV_MODEL"


def test_task198_empty_masked_exposure_stays_empty() -> None:
    suite = load_suite(ROOT / SUITE)
    case = next(
        row
        for row in suite["cases"]["direct_av"]
        if row["stratum"] == "partial_masked"
    )
    assert _mapped_exposure(case, {}) == []
    assert _adapter_context(case).claim_handles


def test_task198_runtime_fixtures_fail_closed() -> None:
    suite = load_suite(ROOT / SUITE)
    binding = _binding(suite["bindings"]["primary_direct"])
    statuses = {}
    for case in suite["cases"]["direct_av"]:
        if case["case_type"] != "runtime_failure":
            continue
        row, _ = _runtime_result(case, binding)
        statuses[case["stratum"]] = row["inference_status"]
        assert row["final_answer"] is None
    assert statuses["malformed_manifest"] == "INVALID_OUTPUT"
    assert statuses["wrong_snapshot"] == "SNAPSHOT_MISMATCH"
    assert statuses["provider_failure"] == "PROVIDER_FAILURE"


def test_task198_schema_retry_semantic_change_rejected() -> None:
    before = json.dumps({"answer": "emerald", "citations": ["x"]})
    after = json.dumps({"answer": "blue", "citations": ["x"]})
    assert not _schema_retry_preserved_content(before, after)
    assert _schema_retry_preserved_content(before, before)


def test_task198_prompt_policy_is_strict_and_no_semantic_repair() -> None:
    policy = _prompt_policy()
    assert policy["generation"]["schema_only_retries_per_case"] == 1
    assert policy["generation"]["semantic_repair"] is False
    assert policy["generation"]["voting"] is False
    assert (
        policy["packing_policy"]
        == "question_independent_source_uniform_chronological"
    )
