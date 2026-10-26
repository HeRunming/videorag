from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from av_trace_strong_baselines.competence import load_suite
from av_trace_strong_baselines.contracts import InferenceStatus
from tools import granite33_competence as competence

ROOT = Path(__file__).resolve().parents[1]


def suite() -> dict:
    return load_suite(ROOT / competence.SUITE)


def test_static_runner_contract_is_frozen() -> None:
    assert competence.MODEL_REPO_ID == "ibm-granite/granite-3.3-8b-instruct"
    assert (
        competence.MODEL_REVISION
        == "51dd4bc2ade4059a6bd87649d68aa11e4fb2529b"
    )
    assert competence.THREADS == 8
    assert competence.MAX_NEW_TOKENS == 512
    assert competence.SCHEMA_RETRIES == 1


def test_prompts_expose_only_public_projection() -> None:
    value = suite()
    for case in value["cases"]["controller_finalizer"]:
        if case["case_type"] not in {"controller", "finalizer"}:
            continue
        rendered = json.dumps(competence._messages(case), sort_keys=True)
        for forbidden in (
            "scoring_target",
            "expected_action_index",
            "expected_evidence_state",
            "required_terms_by_claim",
            "accepted_support",
        ):
            assert forbidden not in rendered


def test_finalizer_prompt_supports_answer_and_abstention() -> None:
    prompt = competence._finalizer_system_prompt()
    assert "answer_mode answer" in prompt
    assert "answer_mode abstain" in prompt
    assert "Never invent evidence" in prompt
    assert "claim text" in prompt


def test_schema_retry_rejects_semantic_change() -> None:
    before = (
        '{"evidence_state":{"missing_modalities":["vision"],'
        '"missingness_cause":"evidence_accessible_but_not_found"}}'
    )
    structural = (
        '{"evidence_state":{"missing_modalities":"vision",'
        '"missingness_cause":"evidence_accessible_but_not_found"}}'
    )
    changed = (
        '{"evidence_state":{"missing_modalities":["speech"],'
        '"missingness_cause":"evidence_in_source_but_inaccessible"}}'
    )
    assert competence._schema_retry_preserved_content(before, structural)
    assert not competence._schema_retry_preserved_content(before, changed)


def test_all_runtime_fixtures_are_typed_and_fail_closed() -> None:
    value = suite()
    binding = competence._binding(value["bindings"]["primary_controller"])
    fixtures = [
        case
        for case in value["cases"]["controller_finalizer"]
        if case["case_type"] == "runtime_failure"
    ]
    assert len(fixtures) == 11
    for case in fixtures:
        row, attempts = competence._runtime_fixture_result(case, binding)
        assert row["inference_status"] == str(
            case["scoring_target"]["expected_inference_status"]
        )
        assert row["model_was_called"] is case["scoring_target"][
            "expected_model_called"
        ]
        assert row["final_answer"] is None
        assert row["schema_repairs_used"] in {0, 1}
        if case["stratum"] == "malformed_output":
            assert row["schema_repairs_used"] == 1
            assert len(attempts) == 2
            assert row["inference_status"] == str(
                InferenceStatus.INVALID_OUTPUT
            )


def test_direct_av_is_structurally_ineligible_not_zero() -> None:
    eligibility = competence._direct_av_eligibility(suite())
    assert eligibility["eligibility"] == "STRUCTURALLY_INELIGIBLE"
    assert eligibility["substantive_cases_present"] == 24
    assert eligibility["runtime_fixtures_present"] == 6
    assert eligibility["model_calls_executed"] == 0
    assert eligibility["score_rows_created"] == 0
    assert eligibility["scored_as_zero"] is False


def test_seal_detects_tampering(tmp_path: Path) -> None:
    output = tmp_path / "restricted"
    output.mkdir()
    os.chmod(output, 0o700)
    for name in competence.SEALED_ARTIFACTS:
        (output / name).write_text(name, encoding="utf-8")
    seal = {
        "schema_version": competence.SEAL_SCHEMA,
        "state": "SEALED_BEFORE_EVALUATION",
        "files": {
            name: {
                "sha256": competence._sha256_file(output / name),
                "bytes": (output / name).stat().st_size,
            }
            for name in competence.SEALED_ARTIFACTS
        },
    }
    competence._atomic_json(output / "seal.json", seal, mode=0o400)
    competence._verify_seal(output)
    (output / "submission.json").write_text("changed", encoding="utf-8")
    with pytest.raises(
        competence.CompetenceRunError,
        match="SEALED_ARTIFACT_MISMATCH",
    ):
        competence._verify_seal(output)
