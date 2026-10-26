from __future__ import annotations

from copy import deepcopy

from av_trace.util import load_json, trajectory_content_hash
from av_trace_validation.metrics_adapter import adapt_episode_metrics, evaluate_premature_stop


def _load_family_and_trajectory(root, index, family_id, state, validator="synthetic_validator_a"):
    entry = next(item for item in index["families"] if item["family_id"] == family_id)
    family = load_json(root / entry["family_path"])
    trajectory = load_json(
        root / "families" / family_id / "trajectories" / f"{validator}.{state.lower()}.json"
    )
    return family, trajectory


def test_denominator_is_external_to_tested_trajectory(validator_bundle):
    root, index, _certificate = validator_bundle
    denominator = load_json(root / "premature_stop_denominator.json")
    family, clean = _load_family_and_trajectory(
        root, index, "syn_f01_visual_order", "CLEAN"
    )
    # Truncate before any evidence and append the original valid final abstention
    # structure. The denominator still comes from validator route templates,
    # never from this tested trajectory's attempted actions.
    tested = deepcopy(clean)
    tested["events"] = [tested["events"][-1]]
    action = tested["events"][0]["action"]
    action["step_index"] = 0
    action["request_id"] = "tested.r0000"
    action["action"]["arguments"] = {
        "p_sufficient": 0.05,
        "verdict": "insufficient",
        "answer_mode": "abstain",
        "claims": [],
        "diagnosis": {
            "modality_probabilities": {"vision": 0.95, "speech": 0.05, "ambient": 0.05},
            "hop_types": ["event_detection"],
            "cause_probabilities": {
                "source_evidence_absent": 0.02,
                "evidence_in_source_but_inaccessible": 0.03,
                "evidence_accessible_but_not_found": 0.9,
                "not_missing": 0.02,
                "uncertain": 0.03
            },
            "recovery_route_declared": False,
            "description": "Stopped without using an available route."
        },
        "natural_language_answer": "",
        "termination_reason": "no_recovery_route"
    }
    belief = action["belief_state"]
    belief["p_sufficient"] = 0.05
    belief["verdict"] = "insufficient"
    belief["missing_modality_probabilities"] = {"vision": 0.95, "speech": 0.05, "ambient": 0.05}
    belief["missing_hop_types"] = ["event_detection"]
    belief["missingness_cause_probabilities"] = deepcopy(
        action["action"]["arguments"]["diagnosis"]["cause_probabilities"]
    )
    tested["final_output"] = deepcopy(action["action"]["arguments"])
    tested["completion"]["total_steps"] = 1
    tested["completion"]["total_cost"] = 0.0
    tested["replay"]["trajectory_hash"] = trajectory_content_hash(tested)
    result = evaluate_premature_stop(family, "CLEAN", tested, denominator)
    assert result.eligible == 1
    assert result.premature_stop == 1
    assert result.feasible_route_ids


def test_adapter_overrides_only_premature_stop_fields(validator_bundle):
    root, index, _certificate = validator_bundle
    denominator = load_json(root / "premature_stop_denominator.json")
    family, trajectory = _load_family_and_trajectory(
        root, index, "syn_f01_visual_order", "CLEAN"
    )
    row = adapt_episode_metrics(
        "validator-smoke", family, "CLEAN", trajectory, denominator
    )
    assert row["grounded_task_success"] == 1
    assert row["premature_stop_eligible"] == 0
    assert row["premature_stop"] == 0
    assert row["premature_stop_denominator_source"] == denominator["artifact_id"]


def test_blocked_infeasible_zero_step_records_are_not_routes(validator_bundle):
    root, index, _certificate = validator_bundle
    denominator = load_json(root / "premature_stop_denominator.json")
    family, trajectory = _load_family_and_trajectory(
        root, index, "syn_f01_visual_order", "BLOCKED"
    )
    result = evaluate_premature_stop(
        family, "BLOCKED", trajectory, denominator
    )
    assert result.eligible == 0
    assert result.premature_stop == 0
    assert result.feasible_route_ids == ()
