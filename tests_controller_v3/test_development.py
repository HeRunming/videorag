from __future__ import annotations

from av_trace_controller_v3.controller import STATE_HEADS
from av_trace_controller_v3.development import (
    TASK111_CONTRACT_HASH,
    controller_v3_development_contract,
    evaluate_results,
)


def test_contract_is_consumed_task111_only() -> None:
    contract = controller_v3_development_contract()
    assert contract["source_contract_hash"] == TASK111_CONTRACT_HASH
    assert len(contract["cases"]) == 16
    assert all(case["consumed"] for case in contract["cases"])
    assert all(
        case["source"] == "TASK_111_CONSUMED_DEVELOPMENT"
        for case in contract["cases"]
    )
    assert contract["v2_holdout_consumed_for_tuning"] is False
    assert contract["v2_restricted_evaluator_key_read"] is False
    assert contract["v2_per_case_labels_read"] is False


def test_perfect_fixture_scores_all_gates() -> None:
    contract = controller_v3_development_contract()
    results = []
    for case in contract["cases"]:
        labels = case["development_labels"]
        calls = [
            {
                "phase": "action_head",
                "status": "valid",
                "prompt_tokens": 1,
                "generated_tokens": 1,
                "latency_seconds": 0.1,
            }
        ]
        state_heads = {}
        for head in STATE_HEADS:
            calls.append(
                {
                    "phase": f"state_head.{head}",
                    "status": "valid",
                    "prompt_tokens": 1,
                    "generated_tokens": 1,
                    "latency_seconds": 0.1,
                }
            )
            state_heads[head] = {
                "syntax_valid": True,
                "choice_index": case["state_choice_enums"][head].index(
                    labels["state"][head]
                ),
                "value": labels["state"][head],
            }
        final = None
        if case["terminal_case"]:
            terminal = labels["terminal"]
            if terminal["kind"] == "answer":
                assertions = []
                answer_terms = []
                for handle, citations in terminal["oracle_support"].items():
                    term = terminal["required_terms"][handle][0]
                    answer_terms.append(term)
                    assertions.append(
                        {
                            "claim_handle": handle,
                            "text": term,
                            "citations": citations,
                        }
                    )
                final = {
                    "verdict": "answer",
                    "answer_text": " ".join(answer_terms),
                    "asserted_claims": assertions,
                }
            else:
                final = {
                    "verdict": terminal["allowed_verdicts"][0],
                    "answer_text": "",
                    "asserted_claims": [],
                    "missing_modalities": terminal["missing_modalities"],
                    "missing_hops": terminal["missing_hops"],
                }
        results.append(
            {
                "case_id": case["case_id"],
                "action_syntax_valid": True,
                "selected_action_index": labels["action_index"],
                "dispatched_action": case["action_menu"][
                    labels["action_index"]
                ],
                "state_heads": state_heads,
                "finalizer_called": case["terminal_case"],
                "final": final,
                "model_calls": calls,
            }
        )
    metrics, _ = evaluate_results(contract, results)
    assert metrics["decision"] == "CONTROLLER_V3_DEV_READY"
    assert all(metrics["gates"].values())
