from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from av_trace_strong_baselines import (
    CHECKPOINT_EVENT,
    PRIMARY_BINDINGS,
    AdapterContext,
    AdapterKind,
    BudgetLedger,
    CompletedCycle,
    DeterministicControl,
    DirectAVAdapter,
    EvaluationViolation,
    EvidenceBundleAdapter,
    FrozenBlockedPrefix,
    IsolationAttestation,
    IsolationViolation,
    LoadStatus,
    ModelBinding,
    OutputProvenance,
    SameBackboneEvidenceSufficiencyAdapter,
    SameBackboneReActAdapter,
    SchemaViolation,
    SharedGroundedFinalizer,
    SingleShotRAGAdapter,
    StrongBaselineError,
    TraceStyleAdaptation,
    build_canonical_agent_action,
    build_schema_only_repair_request,
    copy_early_terminal_assignments,
    fork_restored_no_trigger,
)
from av_trace_strong_baselines.competence import (
    evaluate_competence_submission,
    generate_competence_suite,
    load_suite,
    model_public_case,
    validate_competence_suite,
)
from av_trace_strong_baselines.contracts import (
    InferenceStatus,
    sha256_json,
)
from av_trace_strong_baselines.runtime import (
    DryModelDriver,
    GenerationRequest,
    invoke_fail_closed,
)
from av_trace_strong_baselines.security import (
    ObservedEvidenceLock,
    assert_public_surface,
)

ROOT = Path(__file__).resolve().parents[1]
SUITE_PATH = (
    ROOT / "data/rehearsal_plan/strong_baseline_competence_suite_v1.json"
)


def _context() -> AdapterContext:
    return AdapterContext(
        episode_id="fictional.episode.1",
        question="What color is the fictional prism?",
        public_claim_slots=(
            {
                "claim_handle": "v1slot.color",
                "description": "Visible fictional prism color.",
            },
        ),
    )


def _observation(
    observation_id: str = "obs.public.1",
    *,
    modality: str = "vision",
    text: str = "The fictional prism is teal.",
) -> dict:
    return {
        "observation_id": observation_id,
        "interval": {"start_s": 0.0, "end_s": 1.0},
        "modalities": [modality],
        "payload": {"text": text},
    }


def _answer_envelope(
    *,
    handle: str,
    observation_id: str,
    modalities: list[str],
    text: str,
    interval: dict[str, float] | None = None,
) -> dict:
    interval = interval or {"start_s": 0.0, "end_s": 1.0}
    return {
        "final_answer": {
            "p_sufficient": 1.0,
            "verdict": "sufficient",
            "answer_mode": "answer",
            "claims": [
                {
                    "claim_id": "claim.public.1",
                    "registered_claim_id": handle,
                    "text": text,
                    "confidence": 1.0,
                    "citations": [
                        {
                            "observation_id": observation_id,
                            "interval": interval,
                            "modalities": modalities,
                        }
                    ],
                }
            ],
            "diagnosis": {
                "modality_probabilities": {
                    "vision": 0.0,
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
                "description": "All required fictional evidence is observed.",
            },
            "natural_language_answer": text,
            "termination_reason": "sufficient_evidence",
        },
        "claim_to_citations": {handle: [observation_id]},
    }


def _abstain_envelope(
    *,
    modality: str,
    hop: str,
) -> dict:
    return {
        "final_answer": {
            "p_sufficient": 0.0,
            "verdict": "insufficient",
            "answer_mode": "abstain",
            "claims": [],
            "diagnosis": {
                "modality_probabilities": {
                    "vision": 1.0 if modality == "vision" else 0.0,
                    "speech": 1.0 if modality == "speech" else 0.0,
                    "ambient": 1.0 if modality == "ambient" else 0.0,
                },
                "hop_types": [hop],
                "cause_probabilities": {
                    "source_evidence_absent": 0.0,
                    "evidence_in_source_but_inaccessible": 0.0,
                    "evidence_accessible_but_not_found": 1.0,
                    "not_missing": 0.0,
                    "uncertain": 0.0,
                },
                "recovery_route_declared": False,
                "description": "Required fictional evidence is unavailable.",
            },
            "natural_language_answer": "",
            "termination_reason": "no_recovery_route",
        },
        "claim_to_citations": {},
    }


def _model_provenance() -> dict:
    return {
        "model_authored_paths": ["final_answer"],
        "deterministic_paths": [],
        "copied_paths": ["claim_to_citations"],
    }


def _isolation(prefix: str) -> dict:
    return {
        "provider_session_id": f"{prefix}.provider",
        "model_cache_namespace": f"{prefix}.model",
        "retrieval_cache_namespace": f"{prefix}.retrieval",
        "tool_cache_namespace": f"{prefix}.tool",
        "artifact_namespace": f"{prefix}.artifact",
        "generated_memory_namespace": f"{prefix}.memory",
    }


def _perfect_submission(suite: dict, group: str) -> dict:
    binding_key = (
        "primary_controller" if group == "controller_finalizer" else "primary_direct"
    )
    results = []
    replay_outputs: dict[str, str] = {}
    for case in suite["cases"][group]:
        target = case["scoring_target"]
        if case["case_type"] == "controller":
            raw = json.dumps(
                {
                    "evidence_state": target["expected_evidence_state"],
                    "action_index": target["expected_action_index"],
                }
            )
            results.append(
                {
                    "case_id": case["case_id"],
                    "raw_output": raw,
                    "schema_repairs_used": 0,
                    "repair_kind": "none",
                    "model_calls_used": 1,
                    "model_was_called": True,
                }
            )
        elif case["case_type"] in {"finalizer", "direct_av"}:
            if target["answer_mode"] == "abstain":
                envelope = _abstain_envelope(
                    modality=target["required_missing_modality"],
                    hop=target["required_missing_hop"],
                )
            else:
                handle, terms = next(
                    iter(target["required_terms_by_claim"].items())
                )
                observation_id = target["accepted_support"][handle][0]
                if case["case_type"] == "direct_av":
                    exposure = case["public_input"]["media_exposure_manifest"][0]
                    modalities = exposure["modalities"]
                    interval = exposure["interval"]
                else:
                    observation = case["public_input"]["observed_evidence"][0]
                    modalities = observation["modalities"]
                    interval = observation["interval"]
                envelope = _answer_envelope(
                    handle=handle,
                    observation_id=observation_id,
                    modalities=modalities,
                    text=" ".join(terms),
                    interval=interval,
                )
            raw = json.dumps(envelope, sort_keys=True)
            replay_group = target.get("replay_group")
            if replay_group:
                raw = replay_outputs.setdefault(replay_group, raw)
            results.append(
                {
                    "case_id": case["case_id"],
                    "raw_output": raw,
                    "output_provenance": _model_provenance(),
                    "schema_repairs_used": 0,
                    "repair_kind": "none",
                    "model_calls_used": 1,
                    "model_was_called": True,
                }
            )
        else:
            status = str(target["expected_inference_status"])
            row = {
                "case_id": case["case_id"],
                "inference_status": status,
                "model_was_called": target["expected_model_called"],
                "model_calls_used": 1 if target["expected_model_called"] else 0,
                "schema_repairs_used": 0,
                "repair_kind": "none",
                "final_answer": None,
            }
            if case["stratum"] == "malformed_output":
                row["raw_output"] = "{not valid json"
            results.append(row)
    submission = {
        "suite_hash": suite["suite_hash"],
        "suite_group": group,
        "binding_key": binding_key,
        "load_status": LoadStatus.LOADED_VERIFIED,
        "observed_binding": copy.deepcopy(suite["bindings"][binding_key]),
        "restoration_isolation_checks": [
            {
                "restored": {
                    "isolation_attestation": _isolation("restored"),
                    "public_prefix_hash_through_checkpoint": "sha256:"
                    + "a" * 64,
                },
                "no_trigger": {
                    "isolation_attestation": _isolation("no-trigger"),
                    "public_prefix_hash_through_checkpoint": "sha256:"
                    + "a" * 64,
                },
            }
        ],
        "results": results,
    }
    if group == "controller_finalizer":
        submission["finalizer_binding_key"] = "primary_finalizer"
        submission["observed_finalizer_binding"] = copy.deepcopy(
            suite["bindings"]["primary_finalizer"]
        )
    return submission


def test_suite_file_is_exact_frozen_generator_output() -> None:
    generated = generate_competence_suite()
    stored = load_suite(SUITE_PATH)
    assert stored == generated
    assert len(stored["cases"]["controller_finalizer"]) == 51
    failure_strata = {
        case["stratum"]
        for case in stored["cases"]["controller_finalizer"]
        if case["case_type"] == "runtime_failure"
    }
    assert {
        "malformed_output",
        "wrong_snapshot",
        "provider_failure",
        "timeout",
        "process_failure",
        "oom",
        "budget_exhausted",
    } <= failure_strata
    assert len(stored["cases"]["direct_av"]) == 30
    assert (
        sum(
            case["case_type"] == "direct_av"
            for case in stored["cases"]["direct_av"]
        )
        == 24
    )
    assert stored["model_results_present"] is False


def test_public_case_projection_excludes_scoring_target_and_case_id() -> None:
    case = generate_competence_suite()["cases"]["controller_finalizer"][0]
    projected = model_public_case(case)
    assert set(projected) == {"case_type", "public_input"}
    assert "scoring_target" not in json.dumps(projected)


def test_private_field_leakage_fails_closed() -> None:
    with pytest.raises(SchemaViolation, match="EVALUATOR_PRIVATE_FIELD_EXPOSED"):
        assert_public_surface(
            {"public": {"answer_keys": {"v1slot.color": "teal"}}}
        )


def test_private_identifier_leakage_fails_closed() -> None:
    with pytest.raises(SchemaViolation, match="PRIVATE_IDENTIFIER_EXPOSED"):
        assert_public_surface({"note": "Use claim.r004.visual."})


def test_observed_evidence_lock_rejects_unknown_and_mismatched_citations() -> None:
    lock = ObservedEvidenceLock([_observation()])
    with pytest.raises(SchemaViolation, match="CITATION_NOT_OBSERVED"):
        lock.validate_citation(
            {
                "observation_id": "obs.future",
                "interval": {"start_s": 0.0, "end_s": 1.0},
                "modalities": ["vision"],
            }
        )
    with pytest.raises(SchemaViolation, match="CITATION_INTERVAL_MISMATCH"):
        lock.validate_citation(
            {
                "observation_id": "obs.public.1",
                "interval": {"start_s": 1.0, "end_s": 2.0},
                "modalities": ["vision"],
            }
        )


def test_finalizer_rejects_deterministic_answer_substitution() -> None:
    finalizer = SharedGroundedFinalizer(
        model_binding=PRIMARY_BINDINGS["finalizer"]
    )
    envelope = _answer_envelope(
        handle="v1slot.color",
        observation_id="obs.public.1",
        modalities=["vision"],
        text="teal",
    )
    with pytest.raises(
        SchemaViolation, match="DETERMINISTIC_ANSWER_SUBSTITUTION"
    ):
        finalizer.parse_and_validate(
            json.dumps(envelope),
            context=_context(),
            observations=[_observation()],
            provenance=OutputProvenance(
                model_authored_paths=frozenset(),
                deterministic_paths=frozenset({"final_answer"}),
            ),
        )


def test_semantic_fallback_is_not_a_schema_repair() -> None:
    original = GenerationRequest(
        request_id="fixture.request",
        role="controller",
        public_payload={"task": "choose_next_action"},
        max_new_tokens=512,
        context_cap_processor_tokens=32_768,
    )
    with pytest.raises(StrongBaselineError, match="SEMANTIC_REPAIR_FORBIDDEN"):
        build_schema_only_repair_request(
            original,
            invalid_raw_output=b'{"action_index":0}',
            validation_error_code="WRONG_FIRST_ACTION",
            public_output_schema={"type": "object"},
        )


def test_malformed_output_is_rejected() -> None:
    finalizer = SharedGroundedFinalizer(
        model_binding=PRIMARY_BINDINGS["finalizer"]
    )
    with pytest.raises(SchemaViolation, match="MODEL_OUTPUT_MALFORMED_JSON"):
        finalizer.parse_and_validate(
            "{bad",
            context=_context(),
            observations=[_observation()],
            provenance=OutputProvenance(
                model_authored_paths=frozenset({"final_answer"})
            ),
        )


def test_wrong_snapshot_stops_before_driver_call() -> None:
    wrong = ModelBinding(
        repo_id=PRIMARY_BINDINGS["controller"].repo_id,
        revision="0" * 40,
        role=PRIMARY_BINDINGS["controller"].role,
    )
    driver = DryModelDriver(wrong, load_status=LoadStatus.LOADED_VERIFIED)
    outcome = invoke_fail_closed(
        driver,
        expected_binding=PRIMARY_BINDINGS["controller"],
        request=GenerationRequest(
            request_id="fixture.identity",
            role="controller",
            public_payload={"task": "choose_next_action"},
            max_new_tokens=512,
            context_cap_processor_tokens=32_768,
        ),
    )
    assert outcome.status == InferenceStatus.SNAPSHOT_MISMATCH
    assert not outcome.model_was_called
    assert driver.calls == 0


def test_unverified_load_stops_before_driver_call() -> None:
    driver = DryModelDriver(
        PRIMARY_BINDINGS["controller"], load_status=LoadStatus.NOT_ACQUIRED
    )
    outcome = invoke_fail_closed(
        driver,
        expected_binding=PRIMARY_BINDINGS["controller"],
        request=GenerationRequest(
            request_id="fixture.unloaded",
            role="controller",
            public_payload={"task": "choose_next_action"},
            max_new_tokens=512,
            context_cap_processor_tokens=32_768,
        ),
    )
    assert outcome.status == InferenceStatus.LOAD_NOT_VERIFIED
    assert not outcome.model_was_called
    assert driver.calls == 0


def test_cross_state_cache_collision_is_rejected() -> None:
    restored = IsolationAttestation(**_isolation("restored"))
    collided = _isolation("no-trigger")
    collided["retrieval_cache_namespace"] = (
        restored.retrieval_cache_namespace
    )
    with pytest.raises(
        IsolationViolation, match="INVALID_CROSS_STATE_CONTAMINATION"
    ):
        fork_restored_no_trigger(
            FrozenBlockedPrefix.freeze(
                [
                    CompletedCycle(
                        action=_search_action("vision", index),
                        response={"status": "ok", "results": []},
                    )
                    for index in range(4)
                ],
                ledger=_ledger_at_four(),
            ),
            restored_isolation=restored,
            no_trigger_isolation=IsolationAttestation(**collided),
        )


def _search_action(modality: str, index: int) -> dict:
    tool = {
        "vision": "search_visual",
        "speech": "search_speech",
        "ambient": "search_ambient_audio",
    }[modality]
    return {
        "tool": tool,
        "arguments": {
            "query": f"fictional query {index}",
            "top_k": 5,
            "time_range": {"start_s": 0.0, "end_s": 120.0},
            "exclude_result_ids": [],
            **({"speaker_hint": None} if modality == "speech" else {}),
        },
    }


def _ledger_at_four() -> BudgetLedger:
    ledger = BudgetLedger()
    for index in range(4):
        ledger.charge_action(_search_action("vision", index))
    return ledger


def test_task145_staged_fork_has_identical_public_event_and_budget() -> None:
    prefix = FrozenBlockedPrefix.freeze(
        [
            CompletedCycle(
                action=_search_action("vision", index),
                response={"status": "ok", "results": []},
            )
            for index in range(4)
        ],
        ledger=_ledger_at_four(),
    )
    restored, no_trigger = fork_restored_no_trigger(
        prefix,
        restored_isolation=IsolationAttestation(**_isolation("restored")),
        no_trigger_isolation=IsolationAttestation(**_isolation("no-trigger")),
    )
    assert restored.public_transcript_hash_through_event == (
        no_trigger.public_transcript_hash_through_event
    )
    assert restored.public_transcript[-1] == CHECKPOINT_EVENT
    assert restored.ledger_snapshot == no_trigger.ledger_snapshot
    assert restored.route_available_private
    assert not no_trigger.route_available_private
    assert "arm" not in restored.model_visible_payload()
    assert "route" not in json.dumps(restored.model_visible_payload())


def test_staged_prefix_requires_exact_four_completed_cycles() -> None:
    with pytest.raises(
        StrongBaselineError, match="RESTORATION_PREFIX_WRONG_ACTION_BOUNDARY"
    ):
        FrozenBlockedPrefix.freeze(
            [
                CompletedCycle(
                    action=_search_action("vision", index),
                    response={"status": "ok", "results": []},
                )
                for index in range(3)
            ],
            ledger=BudgetLedger(),
        )


def test_early_terminal_is_copied_to_both_itt_assignments_without_event() -> None:
    transcript = [
        {
            "action": _finalize_action(),
            "response": {"status": "finalized"},
        }
    ]
    restored, no_trigger = copy_early_terminal_assignments(transcript)
    assert restored.terminal_public_transcript_hash == (
        no_trigger.terminal_public_transcript_hash
    )
    assert not restored.trigger_opportunity_reached
    assert not no_trigger.trigger_opportunity_reached
    assert not restored.checkpoint_delivered
    assert not no_trigger.checkpoint_delivered
    assert CHECKPOINT_EVENT not in restored.terminal_public_transcript


def test_same_backbone_adapters_reject_snapshot_mixing() -> None:
    finalizer = SharedGroundedFinalizer(
        model_binding=PRIMARY_BINDINGS["finalizer"]
    )
    wrong = ModelBinding(
        repo_id=PRIMARY_BINDINGS["controller"].repo_id,
        revision="0" * 40,
        role="TOOL_CONTROLLER_BACKBONE",
    )
    with pytest.raises(StrongBaselineError, match="SAME_BACKBONE"):
        SameBackboneReActAdapter(
            controller_binding=wrong, finalizer=finalizer
        )
    with pytest.raises(StrongBaselineError, match="SAME_BACKBONE"):
        SameBackboneEvidenceSufficiencyAdapter(
            controller_binding=wrong, finalizer=finalizer
        )


def test_direct_adapter_rejects_nonchronological_packing() -> None:
    adapter = DirectAVAdapter(
        model_binding=PRIMARY_BINDINGS["direct_av"],
        route_label="native-video-plus-in-video-audio",
        strict_native_av=True,
    )
    manifest = [
        {
            "exposure_id": "exp.2",
            "source_ordinal": 0,
            "interval": {"start_s": 2.0, "end_s": 3.0},
            "modalities": ["vision"],
            "asset_locator": "generated://fictional/2",
        },
        {
            "exposure_id": "exp.1",
            "source_ordinal": 0,
            "interval": {"start_s": 0.0, "end_s": 1.0},
            "modalities": ["vision"],
            "asset_locator": "generated://fictional/1",
        },
    ]
    with pytest.raises(
        SchemaViolation,
        match="DIRECT_PACKING_NOT_QUESTION_INDEPENDENT_CHRONOLOGICAL",
    ):
        adapter.prepare(_context(), media_exposure_manifest=manifest)


def test_rag_uses_one_frozen_search_per_modality_and_common_budget() -> None:
    finalizer = SharedGroundedFinalizer(
        model_binding=PRIMARY_BINDINGS["finalizer"]
    )
    adapter = SingleShotRAGAdapter(
        controller_binding=PRIMARY_BINDINGS["controller"],
        finalizer=finalizer,
    )
    actions, ledger = adapter.prepare_retrieval(_context())
    assert [action["tool"] for action in actions] == [
        "search_visual",
        "search_speech",
        "search_ambient_audio",
    ]
    assert all(action["arguments"]["top_k"] == 5 for action in actions)
    assert ledger.actions_used == 3
    assert ledger.cost_used == 3.0


def test_canonical_action_wrapper_requires_model_authored_belief_state() -> None:
    with pytest.raises(
        SchemaViolation, match="CANONICAL_BELIEF_STATE_NOT_MODEL_AUTHORED"
    ):
        build_canonical_agent_action(
            _context(),
            request_id="request.1",
            step_index=0,
            canonical_belief_state={
                "p_sufficient": 0.0,
                "verdict": "uncertain",
                "missing_modality_probabilities": {
                    "vision": 1.0,
                    "speech": 0.0,
                    "ambient": 0.0,
                },
                "missing_hop_types": ["event_detection"],
                "missingness_cause_probabilities": {
                    "source_evidence_absent": 0.0,
                    "evidence_in_source_but_inaccessible": 0.0,
                    "evidence_accessible_but_not_found": 1.0,
                    "not_missing": 0.0,
                    "uncertain": 0.0,
                },
                "next_action_rationale": "Search visual evidence.",
            },
            selected_action=_search_action("vision", 0),
            belief_state_model_authored=False,
        )


def test_canonical_action_wrapper_uses_existing_action_schema() -> None:
    belief = {
        "p_sufficient": 0.0,
        "verdict": "uncertain",
        "missing_modality_probabilities": {
            "vision": 1.0,
            "speech": 0.0,
            "ambient": 0.0,
        },
        "missing_hop_types": ["event_detection"],
        "missingness_cause_probabilities": {
            "source_evidence_absent": 0.0,
            "evidence_in_source_but_inaccessible": 0.0,
            "evidence_accessible_but_not_found": 1.0,
            "not_missing": 0.0,
            "uncertain": 0.0,
        },
        "next_action_rationale": "Search visual evidence.",
    }
    envelope = build_canonical_agent_action(
        _context(),
        request_id="request.2",
        step_index=0,
        canonical_belief_state=belief,
        selected_action=_search_action("vision", 0),
        belief_state_model_authored=True,
    )
    assert envelope["action"]["tool"] == "search_visual"
    assert envelope["belief_state"] == belief


def test_rag_fixed_rrf_is_order_deterministic() -> None:
    rankings = {
        "vision": [
            {"pointer_id": "ptr.a"},
            {"pointer_id": "ptr.b"},
        ],
        "speech": [
            {"pointer_id": "ptr.b"},
            {"pointer_id": "ptr.c"},
        ],
        "ambient": [
            {"pointer_id": "ptr.c"},
            {"pointer_id": "ptr.a"},
        ],
    }
    first = SingleShotRAGAdapter.fuse_pointers(rankings)
    second = SingleShotRAGAdapter.fuse_pointers(copy.deepcopy(rankings))
    assert first == second
    assert {row["pointer_id"] for row in first} == {"ptr.a", "ptr.b", "ptr.c"}


def test_oracle_and_partial_bundle_contracts_are_explicit() -> None:
    finalizer = SharedGroundedFinalizer(
        model_binding=PRIMARY_BINDINGS["finalizer"]
    )
    oracle = EvidenceBundleAdapter(
        finalizer=finalizer, bundle_kind=AdapterKind.ORACLE_EVIDENCE
    )
    partial = EvidenceBundleAdapter(
        finalizer=finalizer, bundle_kind=AdapterKind.PARTIAL_EVIDENCE
    )
    assert oracle.prepare(
        _context(),
        observations=[_observation()],
        complete_claim_handles=["v1slot.color"],
    ).adapter_kind == AdapterKind.ORACLE_EVIDENCE
    with pytest.raises(SchemaViolation, match="PARTIAL_BUNDLE_NOT_PROPER_SUBSET"):
        partial.prepare(
            _context(),
            observations=[_observation()],
            complete_claim_handles=["v1slot.color"],
        )


def test_trace_style_comparator_requires_adaptation_label() -> None:
    finalizer = SharedGroundedFinalizer(
        model_binding=PRIMARY_BINDINGS["finalizer"]
    )
    with pytest.raises(StrongBaselineError, match="TRACE_ADAPTATION_LABEL_REQUIRED"):
        TraceStyleAdaptation(
            finalizer=finalizer, disclosure_label="Official TRACE reproduction"
        )
    comparator = TraceStyleAdaptation(finalizer=finalizer)
    answer = _answer_envelope(
        handle="v1slot.color",
        observation_id="obs.public.1",
        modalities=["vision"],
        text="teal",
    )
    assert not comparator.record_model_candidate(answer)
    assert comparator.record_model_candidate(answer)


def test_deterministic_control_cannot_substitute_learned_result() -> None:
    control = DeterministicControl(system_id="DET-SUFF", sufficiency_guard=True)
    decision = control.choose_action(
        [_finalize_action()],
        observed_claim_count=1,
        required_claim_count=1,
    )
    assert decision.final_answer is None
    with pytest.raises(
        StrongBaselineError,
        match="DETERMINISTIC_CONTROL_CANNOT_SUBSTITUTE_LEARNED_RESULT",
    ):
        control.reject_learned_substitution(
            decision, target_system_id="SUFF-A-GRANITE33-8B"
        )


def _finalize_action() -> dict:
    return {"tool": "finalize", "arguments": {}}


def test_perfect_dry_controller_submission_passes_frozen_gates() -> None:
    suite = generate_competence_suite()
    report = evaluate_competence_submission(
        suite, _perfect_submission(suite, "controller_finalizer")
    )
    assert report["decision"] == "STRONG_BASELINE_COMPETENCE_PASS"
    assert all(report["gate_checks"].values())


def test_perfect_dry_direct_submission_passes_frozen_gates() -> None:
    suite = generate_competence_suite()
    report = evaluate_competence_submission(
        suite, _perfect_submission(suite, "direct_av")
    )
    assert report["decision"] == "STRONG_BASELINE_COMPETENCE_PASS"
    assert all(report["gate_checks"].values())


def test_evaluator_rejects_wrong_snapshot() -> None:
    suite = generate_competence_suite()
    submission = _perfect_submission(suite, "controller_finalizer")
    submission["observed_binding"]["revision"] = "0" * 40
    with pytest.raises(
        EvaluationViolation, match="SUBMISSION_SNAPSHOT_MISMATCH"
    ):
        evaluate_competence_submission(suite, submission)


def test_evaluator_rejects_cross_state_cache_contamination() -> None:
    suite = generate_competence_suite()
    submission = _perfect_submission(suite, "controller_finalizer")
    submission["restoration_isolation_checks"][0]["no_trigger"][
        "isolation_attestation"
    ]["tool_cache_namespace"] = submission["restoration_isolation_checks"][0][
        "restored"
    ]["isolation_attestation"]["tool_cache_namespace"]
    report = evaluate_competence_submission(suite, submission)
    assert report["decision"] == "STRONG_BASELINE_COMPETENCE_REPAIR"
    assert not report["gate_checks"]["cross_state_isolation"]


def test_evaluator_counts_unsupported_claim_and_fails_gate() -> None:
    suite = generate_competence_suite()
    submission = _perfect_submission(suite, "controller_finalizer")
    final_case = next(
        case
        for case in suite["cases"]["controller_finalizer"]
        if case["case_type"] == "finalizer"
        and case["scoring_target"].get("oracle_complete")
    )
    row = next(
        item for item in submission["results"] if item["case_id"] == final_case["case_id"]
    )
    envelope = json.loads(row["raw_output"])
    envelope["final_answer"]["claims"][0]["text"] = "unsupported fiction"
    envelope["final_answer"]["natural_language_answer"] = "unsupported fiction"
    row["raw_output"] = json.dumps(envelope)
    report = evaluate_competence_submission(suite, submission)
    assert report["metrics"]["unsupported_required_claims"] > 0
    assert report["decision"] == "STRONG_BASELINE_COMPETENCE_REPAIR"
    assert not report["gate_checks"]["unsupported_claims"]


def test_evaluator_rejects_modified_suite_hash() -> None:
    suite = generate_competence_suite()
    changed = copy.deepcopy(suite)
    changed["thresholds"]["controller_finalizer"][
        "oracle_supported_answer_min"
    ] = 0.79
    with pytest.raises(EvaluationViolation, match="SUITE_HASH_MISMATCH"):
        validate_competence_suite(changed)


def test_evaluator_rejects_semantic_repair_metadata() -> None:
    suite = generate_competence_suite()
    submission = _perfect_submission(suite, "controller_finalizer")
    submission["results"][0]["schema_repairs_used"] = 1
    submission["results"][0]["model_calls_used"] = 2
    submission["results"][0]["repair_kind"] = "semantic"
    with pytest.raises(
        EvaluationViolation, match="RESULT_SEMANTIC_REPAIR_FORBIDDEN"
    ):
        evaluate_competence_submission(suite, submission)


def test_suite_contains_no_real_or_private_identifiers() -> None:
    suite = generate_competence_suite()
    serialized = json.dumps(suite).casefold()
    for forbidden in (
        "noaa01",
        "cand-",
        "claim.r",
        "answer_keys",
    ):
        assert forbidden not in serialized
    assert suite["suite_hash"] == sha256_json(
        {key: value for key, value in suite.items() if key != "suite_hash"}
    )
