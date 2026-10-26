from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest

from tools import granite33_8b_acquisition as granite

ROOT = Path(__file__).resolve().parents[1]


def plan() -> dict:
    return json.loads((ROOT / granite.PLAN).read_text())


def test_plan_is_exact_and_bounded() -> None:
    value = plan()
    granite.validate_plan(value)
    assert value["model"]["repo_id"] == granite.REPO_ID
    assert value["model"]["revision"] == granite.REVISION
    assert (
        value["model"]["expected_payload_bytes"]
        < value["caps"]["selected_payload_bytes"]
    )
    assert value["runtime_canary"]["max_new_tokens_per_case"] == 512
    assert value["runtime_canary"]["schema_only_retries_per_case"] == 1


def test_plan_rejects_revision_drift() -> None:
    value = copy.deepcopy(plan())
    value["model"]["revision"] = "0" * 40
    with pytest.raises(granite.AcquisitionError, match="IDENTITY"):
        granite.validate_plan(value)


def test_plan_selects_only_safetensors_weights() -> None:
    names = {item["path"] for item in plan()["model"]["allowlist"]}
    assert all(
        Path(name).suffix != ".bin" for name in names
    )
    assert {
        name for name in names if name.endswith(".safetensors")
    } == {
        "model-00001-of-00004.safetensors",
        "model-00002-of-00004.safetensors",
        "model-00003-of-00004.safetensors",
        "model-00004-of-00004.safetensors",
    }


def test_exact_url_contains_full_revision_and_mirror() -> None:
    value = plan()
    url = granite.exact_url(
        value["model"], "config.json", "https://hf-mirror.com"
    )
    assert url.startswith("https://hf-mirror.com/")
    assert f"/resolve/{granite.REVISION}/" in url


def test_atomic_json_is_restricted(tmp_path: Path) -> None:
    output = tmp_path / "restricted/value.json"
    granite.atomic_json(output, {"ok": True})
    assert os.stat(output).st_mode & 0o777 == 0o600


def test_network_guard_blocks_and_counts() -> None:
    with granite.deny_network() as attempts, pytest.raises(
        RuntimeError, match="NETWORK_ACCESS_FORBIDDEN_DURING_CPU_CANARY"
    ):
        __import__("socket").socket()
    assert attempts["count"] == 1


def test_task158_case_binding_is_exact() -> None:
    cases = granite._task158_cases(ROOT, plan())
    assert [case["case_id"] for case in cases] == [
        "sbc-controller-001",
        "sbc-finalizer-001",
    ]
    assert {case["case_type"] for case in cases} == {
        "controller",
        "finalizer",
    }
    for case in cases:
        serialized_messages = json.dumps(granite._messages(case))
        assert "scoring_target" not in serialized_messages
        assert "expected_action_index" not in serialized_messages
        assert "required_terms_by_claim" not in serialized_messages


def test_truncated_json_is_preserved_for_schema_only_retry() -> None:
    case = granite._task158_cases(ROOT, plan())[0]
    raw = '{"evidence_state":{"p_sufficient":0,"covered_claim_handles":[]'
    with pytest.raises(
        granite.AcquisitionError,
        match="SMOKE_OUTPUT_INVALID:MODEL_OUTPUT_MALFORMED_JSON",
    ):
        granite._parse_and_validate_smoke_output(case, raw)
    messages = granite._repair_messages(
        case,
        raw,
        "SMOKE_OUTPUT_INVALID:MODEL_OUTPUT_MALFORMED_JSON",
    )
    assert messages[-2] == {"role": "assistant", "content": raw}
    assert "same attempted content" in messages[-1]["content"]
    assert "Do not add facts" in messages[-1]["content"]
    assert granite._schema_retry_allowed(
        "SMOKE_OUTPUT_INVALID:MODEL_OUTPUT_MALFORMED_JSON"
    )
    assert not granite._schema_retry_allowed(
        "SMOKE_OUTPUT_INVALID:MISSINGNESS_CAUSE_ENUM"
    )


def test_schema_retry_cannot_change_semantic_content() -> None:
    invalid = (
        '{"evidence_state":{"missing_hops":"entity_identity",'
        '"missingness_cause":"source_evidence_absent"}}'
    )
    structural_only = (
        '{"evidence_state":{"missing_hops":["entity_identity"],'
        '"missingness_cause":"source_evidence_absent"}}'
    )
    semantic_change = (
        '{"evidence_state":{"missing_hops":["entity_identity"],'
        '"missingness_cause":"evidence_accessible_but_not_found"}}'
    )
    assert granite._schema_retry_preserved_content(invalid, structural_only)
    assert not granite._schema_retry_preserved_content(
        invalid, semantic_change
    )
    extra_unit = (
        '{"citation":{"observation_id":"obs.public.1","interval":'
        '{"start_s":0,"end_s":1,"unit":"s"}}}'
    )
    without_unit = (
        '{"citation":{"observation_id":"obs.public.1","interval":'
        '{"start_s":0,"end_s":1}}}'
    )
    assert granite._schema_retry_preserved_content(extra_unit, without_unit)


def test_controller_smoke_semantics_are_not_repaired() -> None:
    case = granite._task158_cases(ROOT, plan())[0]
    parsed = {
        "evidence_state": {
            **case["scoring_target"]["expected_evidence_state"],
            "recovery_intent": "search_speech",
        },
        "action_index": 0,
    }
    result = granite._smoke_semantics(case, parsed)
    assert result["action_correct"] is True
    assert result["exact_six_field_state"] is False
    assert result["passed"] is False


def test_finalizer_smoke_requires_observed_grounding() -> None:
    case = granite._task158_cases(ROOT, plan())[1]
    invalid = {
        "final_answer": {
            "p_sufficient": 1,
            "verdict": "sufficient",
            "answer_mode": "answer",
            "claims": [{
                "claim_id": "c1",
                "registered_claim_id": "v1slot.final.0",
                "text": "The fictional badge shape is octagonal.",
                "confidence": 1,
                "citations": [{
                    "observation_id": "obs.public.future",
                    "interval": {"start_s": 0, "end_s": 1},
                    "modalities": ["vision"],
                }],
            }],
            "diagnosis": {
                "modality_probabilities": {
                    "vision": 1, "speech": 0, "ambient": 0
                },
                "hop_types": [],
                "cause_probabilities": {
                    "source_evidence_absent": 0,
                    "evidence_in_source_but_inaccessible": 0,
                    "evidence_accessible_but_not_found": 0,
                    "not_missing": 1,
                    "uncertain": 0,
                },
                "recovery_route_declared": False,
                "description": "Complete visual evidence.",
            },
            "natural_language_answer": (
                "The fictional badge shape is octagonal."
            ),
            "termination_reason": "sufficient_evidence",
        },
        "claim_to_citations": {
            "v1slot.final.0": ["obs.public.future"]
        },
    }
    with pytest.raises(
        granite.AcquisitionError,
        match="SMOKE_OUTPUT_INVALID:CITATION_NOT_OBSERVED",
    ):
        granite._parse_and_validate_smoke_output(
            case, json.dumps(invalid, separators=(",", ":"))
        )


def test_finalizer_smoke_accepts_grounded_natural_language_answer() -> None:
    case = granite._task158_cases(ROOT, plan())[1]
    parsed = {
        "final_answer": {
            "answer_mode": "answer",
            "claims": [{
                "registered_claim_id": "v1slot.final.0",
                "text": "The badge shape.",
                "citations": [{
                    "observation_id": "obs.public.final.0",
                }],
            }],
            "natural_language_answer": (
                "The fictional badge shape is octagonal."
            ),
        }
    }
    result = granite._smoke_semantics(case, parsed)
    assert result == {
        "answer_mode_correct": True,
        "support_correct": True,
        "unsupported_claims": 0,
        "passed": True,
    }


def test_delivered_manifest_has_honest_terminal_decision() -> None:
    manifest = json.loads((ROOT / granite.MANIFEST).read_text())
    assert manifest["decision"] in {
        "GRANITE33_8B_ACQUISITION_READY",
        "GRANITE33_8B_ACQUISITION_REPAIR",
        "GRANITE33_8B_ACQUISITION_NO_GO",
    }
    assert manifest["competence_claimed"] is False
    assert manifest["api_called"] is False
    if manifest["decision"] == "GRANITE33_8B_ACQUISITION_READY":
        assert manifest["local_model_inference_executed"] is True
    assert manifest["qwen_omni_downloaded"] is False
    if manifest["decision"] == "GRANITE33_8B_ACQUISITION_READY":
        assert manifest["model"]["snapshot_acquired"] is True
        assert manifest["model"]["snapshot_hash_verified"] is True
        assert manifest["cpu_load_smoke"]["status"] == "LOAD_SMOKE_COMPLETE"
        assert all(
            case["structural_grounding_valid"]
            and case["semantics"]["passed"]
            for case in manifest["cpu_load_smoke"]["cases"]
        )


def test_promotion_rejects_incomplete_smoke(tmp_path: Path) -> None:
    value = plan()
    with pytest.raises(granite.AcquisitionError, match="CPU_CANARY_NOT_COMPLETE"):
        granite.finalize_verified_stage(
            tmp_path,
            value,
            {"status": "LOAD_SMOKE_FAILED"},
        )
