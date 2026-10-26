from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from av_trace_scale1b_agent.competence import (
    MODEL_SPECS,
    STRUCTURED_OUTPUT_FLOOR,
    SUPPORTED_ANSWER_FLOOR,
    TASK111_CONTRACT_HASH,
    _snapshot_from_manifest,
    evaluate_competence_results,
    paired_comparison,
    synthetic_competence_contract,
)
from av_trace_scale1b_agent.controller import _action_menu, run_controller_decision
from av_trace_scale1b_agent.process import ProcessConfig, QwenProcess
from av_trace_scale1b_agent.schema import PublicSchemaError, validate_finalization

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_WORKER = ROOT / "tests_scale1b_agent/fixture_worker.py"


def _final_two_claims() -> dict:
    return {
        "verdict": "answer",
        "answer_text": "The token is amber and the label is comet.",
        "asserted_claims": [
            {
                "claim_handle": "devslot.color",
                "text": "The token is amber.",
                "citations": ["devobs.shared"],
            },
            {
                "claim_handle": "devslot.label",
                "text": "The label is comet.",
                "citations": ["devobs.shared"],
            },
        ],
        "claim_to_citations": {
            "devslot.color": ["devobs.shared"],
            "devslot.label": ["devobs.shared"],
        },
        "missing_modalities": [],
        "missing_hops": [],
        "missingness_cause": "not_missing",
        "p_sufficient": 0.9,
        "recovery_intent": "",
        "stop_rationale": "Both required claims are cited.",
    }


def test_contract_is_synthetic_only_and_preregisters_requested_floors():
    contract = synthetic_competence_contract()
    assert contract["contract_hash"] == TASK111_CONTRACT_HASH
    assert contract["development_only"] is True
    assert contract["scientific_evaluation_eligible"] is False
    assert contract["actual_model_authorship_required"] is True
    assert contract["maximum_repairs_per_output"] == 1
    assert contract["strict_fail_closed"] is True
    assert contract["deterministic_answer_substitution"] is False
    floors = contract["preregistered_competence_floors"]
    assert floors["valid_structured_outputs_after_at_most_one_repair"] == 0.9
    assert floors["supported_answer_success_on_oracle_evidence"] == 0.8
    assert floors["unsupported_required_claims"] == 0
    serialized = json.dumps(contract).casefold()
    for forbidden in (
        "noaa01-",
        "r004",
        "r007",
        "r011",
        "r016",
        "r017",
        "claim.r",
        "e.r",
        "seg.",
        "cand-",
    ):
        assert forbidden not in serialized


def test_contract_covers_every_requested_capability():
    contract = synthetic_competence_contract()
    covered = {
        capability
        for case in [
            *contract["controller_cases"],
            *contract["generator_cases"],
        ]
        for capability in case["capabilities"]
    }
    assert {
        "initial_modality_routing",
        "inspect_read",
        "claim_slot_coverage",
        "exact_observation_id_citation_copy",
        "finalization",
        "justified_abstention",
        "no_progress_repeated_action_handling",
        "missing_hop_diagnosis",
        "recovery_after_route_restoration",
    } <= covered


def test_finalization_requires_every_claim_and_nonempty_exact_citations():
    final = _final_two_claims()
    assert validate_finalization(
        final,
        claim_handles={"devslot.color", "devslot.label"},
        observation_ids={"devobs.shared"},
    )["verdict"] == "answer"

    missing_claim = _final_two_claims()
    missing_claim["asserted_claims"] = missing_claim["asserted_claims"][:1]
    missing_claim["claim_to_citations"].pop("devslot.label")
    with pytest.raises(PublicSchemaError, match="ALL_REQUIRED_CLAIMS"):
        validate_finalization(
            missing_claim,
            claim_handles={"devslot.color", "devslot.label"},
            observation_ids={"devobs.shared"},
        )

    empty_citation = _final_two_claims()
    empty_citation["asserted_claims"][0]["citations"] = []
    empty_citation["claim_to_citations"]["devslot.color"] = []
    with pytest.raises(PublicSchemaError, match="CITATIONS_EMPTY"):
        validate_finalization(
            empty_citation,
            claim_handles={"devslot.color", "devslot.label"},
            observation_ids={"devobs.shared"},
        )


def test_nonanswer_requires_missingness_and_empty_answer():
    value = {
        "verdict": "insufficient",
        "answer_text": "",
        "asserted_claims": [],
        "claim_to_citations": {},
        "missing_modalities": ["speech"],
        "missing_hops": ["speech_content"],
        "missingness_cause": "evidence_accessible_but_not_found",
        "p_sufficient": 0.1,
        "recovery_intent": "Search speech.",
        "stop_rationale": "Speech evidence is unavailable.",
    }
    assert validate_finalization(
        value,
        claim_handles={"devslot.speech"},
        observation_ids=set(),
    )["verdict"] == "insufficient"
    bad = dict(value)
    bad["missing_modalities"] = []
    bad["missing_hops"] = []
    with pytest.raises(PublicSchemaError, match="WITHOUT_MISSING_REQUIREMENT"):
        validate_finalization(
            bad,
            claim_handles={"devslot.speech"},
            observation_ids=set(),
        )


def test_action_menu_reserves_finalization_when_no_progress_or_budget_exhausted():
    assert _action_menu(
        question="What is shown?",
        pointers={},
        observations={},
        available_tools={"search_visual", "finalize"},
        turn=1,
        no_progress_rounds=2,
        remaining_steps=3,
        remaining_cost=3.0,
        tool_costs={"search_visual": 1.0},
    ) == [{"type": "finalize"}]
    assert _action_menu(
        question="What is shown?",
        pointers={},
        observations={},
        available_tools={"search_visual", "finalize"},
        turn=1,
        no_progress_rounds=0,
        remaining_steps=1,
        remaining_cost=3.0,
        tool_costs={"search_visual": 1.0},
    ) == [{"type": "finalize"}]


def test_repair_payload_retains_visible_context_for_controller(tmp_path):
    action_menu = [
        {
            "type": "search",
            "modality": "speech",
            "query": "spoken word",
            "top_k": 3,
        }
    ]
    with QwenProcess(
        tmp_path,
        config=ProcessConfig(startup_timeout_s=5, generation_timeout_s=5),
        command=[
            sys.executable,
            str(FIXTURE_WORKER),
            "controller_context_repair",
        ],
    ) as process:
        result = run_controller_decision(
            process,
            policy="evidence_sufficiency",
            turn=0,
            question="Which word is spoken?",
            claim_slots=[
                {
                    "claim_handle": "devslot.word",
                    "description": "The spoken word.",
                }
            ],
            available_tools=["search_speech", "finalize"],
            remaining_budget={
                "steps": 3,
                "cost": 3.0,
                "tool_costs": {"search_speech": 1.0, "finalize": 0.0},
            },
            known_pointers=[],
            citable_observations=[],
            recent_public_events=[],
            action_menu=action_menu,
        )
    assert result["decision"]["action"]["modality"] == "speech"
    assert [row["status"] for row in result["model_calls"]] == ["invalid", "valid"]
    for row in result["model_calls"]:
        assert "system_prompt" not in row
        assert "request_payload" not in row
        assert row["system_prompt_sha256"].startswith("sha256:")


def test_metric_gate_is_strict_and_zero_unsupported_is_mandatory():
    contract = synthetic_competence_contract()
    all_cases = [
        *contract["controller_cases"],
        *contract["generator_cases"],
    ]
    results = [
        {
            "case_id": case["case_id"],
            "structured_valid": True,
            "semantic_success": bool(case.get("oracle_evidence", False)),
            "unsupported_required_claims": 0,
        }
        for case in all_cases
    ]
    metrics = evaluate_competence_results(contract, results)
    assert metrics["valid_structured_output_rate"] >= STRUCTURED_OUTPUT_FLOOR
    assert metrics["supported_answer_success_rate"] >= SUPPORTED_ANSWER_FLOOR
    assert metrics["decision"] == "GO"
    results[0]["unsupported_required_claims"] = 1
    assert evaluate_competence_results(contract, results)["decision"] == "NO_GO"


def test_qwen7b_selection_is_exactly_pinned_to_strong_manifest():
    snapshot, manifest = _snapshot_from_manifest(ROOT, "qwen7b")
    spec = MODEL_SPECS["qwen7b"]
    assert manifest["candidate"]["repo_id"] == spec["repo_id"]
    assert manifest["candidate"]["revision"] == spec["revision"]
    assert snapshot == ROOT / spec["snapshot_dir"]


def test_paired_comparison_reports_case_and_capability_deltas():
    contract = synthetic_competence_contract()
    all_cases = [
        *contract["controller_cases"],
        *contract["generator_cases"],
    ]

    def report(success_ids: set[str]) -> dict:
        results = [
            {
                "case_id": case["case_id"],
                "case_type": (
                    "generator_finalization"
                    if "oracle_evidence" in case
                    else "controller"
                ),
                "structured_valid": True,
                "semantic_success": case["case_id"] in success_ids,
                "unsupported_required_claims": 0,
                "errors": [],
            }
            for case in all_cases
        ]
        return {
            "contract_hash": contract["contract_hash"],
            "metrics": evaluate_competence_results(contract, results),
            "results": results,
        }

    baseline = report(set())
    qwen7b = report({all_cases[0]["case_id"]})
    comparison = paired_comparison(contract, baseline, qwen7b)
    assert comparison["same_frozen_contract"] is True
    assert comparison["cases"][0]["semantic_delta"] == 1
    routing = next(
        row
        for row in comparison["capabilities"]
        if row["capability"] == "initial_modality_routing"
    )
    assert routing["success_count_delta"] == 1
