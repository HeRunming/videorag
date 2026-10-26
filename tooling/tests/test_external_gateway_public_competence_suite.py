from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from tools import external_gateway_public_competence_suite as suite


def committed_artifact() -> dict[str, Any]:
    return json.loads((ROOT / suite.ARTIFACT_PATH).read_text(encoding="utf-8"))


def _diagnosis(
    *,
    modality: str | None = None,
    hop: str | None = None,
) -> dict[str, Any]:
    return {
        "modality_probabilities": {
            "vision": 1.0 if modality == "vision" else 0.0,
            "speech": 1.0 if modality == "speech" else 0.0,
            "ambient": 1.0 if modality == "ambient" else 0.0,
        },
        "hop_types": [] if hop is None else [hop],
        "cause_probabilities": {
            "source_evidence_absent": (
                1.0 if modality is not None else 0.0
            ),
            "evidence_in_source_but_inaccessible": 0.0,
            "evidence_accessible_but_not_found": 0.0,
            "not_missing": 1.0 if modality is None else 0.0,
            "uncertain": 0.0,
        },
        "recovery_route_declared": False,
        "description": (
            "The fictional packet is complete."
            if modality is None
            else "The requested fictional evidence is absent."
        ),
    }


def _attempt(raw: Any) -> list[dict[str, Any]]:
    return [
        {
            "attempt_index": 1,
            "kind": "initial",
            "raw_output": json.dumps(
                raw,
                sort_keys=True,
                separators=(",", ":"),
            ),
        }
    ]


def perfect_submission(artifact: dict[str, Any]) -> dict[str, Any]:
    labels = artifact["evaluator_private"]["labels"]
    rows: list[dict[str, Any]] = []
    for packet in suite.public_packet_projection(artifact):
        case_id = packet["case_id"]
        label = labels[case_id]
        if packet["case_type"] == "controller":
            attempts = {
                "action_choice": _attempt(
                    {
                        "function_name": (
                            f"select_action_{label['expected_action_index']:02d}"
                        ),
                        "arguments": {},
                    }
                ),
                "evidence_state": _attempt(
                    label["expected_evidence_state"]
                ),
            }
        elif label["answer_mode"] == "abstain":
            attempts = {
                "disposition": _attempt(
                    {
                        "p_sufficient": 0.0,
                        "verdict": "insufficient",
                        "answer_mode": "abstain",
                        "termination_reason": "no_recovery_route",
                    }
                ),
                "answer_text": _attempt({"text": ""}),
                "claim_drafts": _attempt({"claims": []}),
                "citation_selections": _attempt({"selections": []}),
                "diagnosis": _attempt(
                    _diagnosis(
                        modality=label["required_missing_modality"],
                        hop=label["required_missing_hop"],
                    )
                ),
            }
        else:
            claims = []
            selections = []
            for index, (handle, terms) in enumerate(
                label["required_terms_by_claim"].items(),
                1,
            ):
                claims.append(
                    {
                        "claim_id": f"claim.{case_id}.{index}",
                        "registered_claim_id": handle,
                        "text": " ".join(terms),
                        "confidence": 1.0,
                    }
                )
                selections.append(
                    {
                        "registered_claim_id": handle,
                        "observation_ids": label["expected_citations"][
                            handle
                        ],
                    }
                )
            attempts = {
                "disposition": _attempt(
                    {
                        "p_sufficient": 1.0,
                        "verdict": "sufficient",
                        "answer_mode": "answer",
                        "termination_reason": "sufficient_evidence",
                    }
                ),
                "answer_text": _attempt(
                    {"text": " ".join(label["answer_terms"])}
                ),
                "claim_drafts": _attempt({"claims": claims}),
                "citation_selections": _attempt(
                    {"selections": selections}
                ),
                "diagnosis": _attempt(_diagnosis()),
            }
        rows.append({"case_id": case_id, "factor_attempts": attempts})
    return {
        "schema_version": suite.SUBMISSION_SCHEMA,
        "suite_id": suite.SUITE_ID,
        "run_id": "test-perfect-run",
        "execution_state": "COMPLETE_UNEVALUATED",
        "public_suite_sha256": artifact["freeze_manifest"][
            "component_hashes"
        ]["public_suite"],
        "private_fields_supplied_to_model": False,
        "deterministic_answer_substitutions": 0,
        "cases": rows,
    }


def _perfect_metrics() -> dict[str, Any]:
    return {
        "case_count": 40,
        "complete_case_set": True,
        "valid_structured_model_calls": 1.0,
        "correct_first_actions_overall": 1.0,
        "correct_first_actions_by_stratum": {
            stratum: 1.0 for stratum in suite.CONTROLLER_STRATA
        },
        "exact_six_field_state": 1.0,
        "state_component_accuracy": {
            field: 1.0
            for field in (
                "p_sufficient",
                "covered_claim_handles",
                "missing_modalities",
                "missing_hops",
                "missingness_cause",
                "recovery_intent",
            )
        },
        "blocked_correct_abstention": 1.0,
        "restoration_recovery": 1.0,
        "supported_finalization": 1.0,
        "exact_citation_selection": 1.0,
        "premature_stop_prevention": 1.0,
        "unsupported_required_claims": 0,
        "unobserved_citation_selections": 0,
        "private_label_exposures": 0,
        "deterministic_answer_substitutions": 0,
    }


def test_committed_freeze_schema_balance_and_not_run_state() -> None:
    artifact = committed_artifact()
    suite.validate_frozen_artifact(artifact)
    packets = suite.public_packet_projection(artifact)
    assert artifact["status"] == suite.FROZEN_NOT_RUN
    assert artifact["one_shot_state"]["state"] == "NOT_RUN"
    assert artifact["one_shot_state"]["gateway_calls"] == 0
    assert artifact["one_shot_state"]["model_outputs_present"] is False
    assert len(packets) == 40
    assert sum(row["case_type"] == "controller" for row in packets) == 24
    assert sum(row["case_type"] == "finalizer" for row in packets) == 16
    assert all(row["public_fictional"] is True for row in packets)
    assert all(row["source_free"] is True for row in packets)
    assert all(row["prospective_unseen"] is True for row in packets)


def test_prompt_projection_excludes_private_evaluator_labels() -> None:
    artifact = committed_artifact()
    projection = suite.public_packet_projection(artifact)
    serialized = json.dumps(projection, sort_keys=True)
    assert artifact["evaluator_private"]["private_canary"] not in serialized
    for key in suite.PROHIBITED_PROMPT_KEYS:
        assert f'"{key}"' not in serialized
    assert "evaluator_private" not in serialized
    assert "expected_action_index" not in serialized
    assert "required_terms_by_claim" not in serialized


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("expected_action_index", 0),
        ("H1", "forbidden"),
        ("H2", "forbidden"),
        ("SES", "forbidden"),
        ("source_uri", "https://example.invalid/item"),
        ("clip_path", "fixture.mp4"),
    ],
)
def test_leakage_guard_rejects_forbidden_prompt_material(
    key: str,
    value: object,
) -> None:
    packet = suite.public_packet_projection(committed_artifact())[0]
    packet[key] = value
    with pytest.raises(suite.CompetenceSuiteError):
        suite.validate_prompt_packet(packet)


def test_generation_and_manifest_are_deterministic() -> None:
    first = suite.build_frozen_artifact()
    second = suite.build_frozen_artifact()
    assert first == second == committed_artifact()
    assert suite.sha256_json(first) == suite.sha256_json(second)
    assert first["freeze_manifest"]["packet_hashes"] == second[
        "freeze_manifest"
    ]["packet_hashes"]


def test_non_overlap_with_granite_qwen_and_two_smoke_fixtures() -> None:
    artifact = committed_artifact()
    audit = suite.compute_non_overlap_audit(
        suite.public_packet_projection(artifact)
    )
    assert audit["status"] == "PASS"
    assert audit["smoke_fixture_case_id_overlap"] == []
    assert set(audit["comparators"]) == {
        "granite_v2",
        "qwen3_v2",
        "external_gateway_smoke",
    }
    for report in audit["comparators"].values():
        assert report["case_id_overlap"] == []
        assert report["normalized_question_overlap"] == []
        assert report["public_input_hash_overlap"] == []


def test_threshold_mechanics_go_repair_and_fail_closed_no_go() -> None:
    metrics = _perfect_metrics()
    assert suite.apply_thresholds(metrics)["decision"].endswith("_GO")

    repair = copy.deepcopy(metrics)
    repair["supported_finalization"] = 0.8
    repair_result = suite.apply_thresholds(repair)
    assert repair_result["decision"].endswith("_REPAIR")
    assert repair_result["gate_checks"]["supported_finalization"] is False

    no_go = copy.deepcopy(metrics)
    no_go["private_label_exposures"] = 1
    no_go_result = suite.apply_thresholds(no_go)
    assert no_go_result["decision"].endswith("_NO_GO")
    assert no_go_result["gate_checks"]["private_exposure"] is False

    malformed = copy.deepcopy(metrics)
    del malformed["correct_first_actions_by_stratum"]
    malformed_result = suite.apply_thresholds(malformed)
    assert malformed_result["decision"].endswith("_REPAIR")
    assert malformed_result["gate_checks"]["actions_each_stratum"] is False


def test_perfect_factorized_submission_replays_to_gate_c_go() -> None:
    artifact = committed_artifact()
    report = suite.evaluate_submission(
        artifact,
        perfect_submission(artifact),
    )
    assert report["decision"] == (
        "EXTERNAL_GATEWAY_PUBLIC_COMPETENCE_GATE_C_GO"
    )
    assert all(report["gate_checks"].values())
    assert report["metrics"]["case_count"] == 40
    assert report["metrics"]["restoration_recovery"] == 1.0
    assert report["metrics"]["exact_citation_selection"] == 1.0
    assert report["metrics"]["premature_stop_prevention"] == 1.0


def test_evaluator_rejects_incomplete_case_set() -> None:
    artifact = committed_artifact()
    submission = perfect_submission(artifact)
    submission["cases"].pop()
    with pytest.raises(
        suite.CompetenceSuiteError,
        match="SUBMISSION_CASE_SET_MISMATCH",
    ):
        suite.evaluate_submission(artifact, submission)


def test_evaluator_detects_private_canary_in_raw_output() -> None:
    artifact = committed_artifact()
    submission = perfect_submission(artifact)
    submission["cases"][0]["factor_attempts"]["action_choice"][0][
        "raw_output"
    ] = json.dumps(
        {
            "function_name": "select_action_00",
            "arguments": {},
            "note": artifact["evaluator_private"]["private_canary"],
        }
    )
    report = suite.evaluate_submission(artifact, submission)
    assert report["metrics"]["private_label_exposures"] == 1
    assert report["decision"].endswith("_NO_GO")
