from __future__ import annotations

import pytest

from av_trace_captaincook4d_family_mining import (
    build_rehearsal_plan,
    validate_hop_structure,
)


def test_plan_has_exactly_two_slots_per_three_sources_and_no_execution():
    plan = build_rehearsal_plan()
    slots = plan["lead_structure"]["slots"]
    assert len(slots) == 6
    assert {
        source_id: sum(item["source_id"] == source_id for item in slots)
        for source_id in ("15_29", "16_20", "26_22")
    } == {"15_29": 2, "16_20": 2, "26_22": 2}
    assert plan["execution_status"]["mining_executed_by_task190"] is False
    assert (
        plan["execution_status"]["active_index_output_or_checkpoints_touched"]
        is False
    )
    assert plan["task145_template"]["active_interventions"] is False


def test_one_hop_far_is_rejected():
    with pytest.raises(ValueError, match="ONE_HOP_MUST_BE_NEAR_LOCAL"):
        validate_hop_structure(
            {
                "hop_stratum": "one_hop",
                "temporal_stratum": "far_separated",
                "composition": None,
                "one_hop_implies_near": True,
            }
        )


def test_multihop_requires_coherent_composed_claim():
    with pytest.raises(
        ValueError, match="MULTI_HOP_COMPOSED_CLAIM_REQUIRED"
    ):
        validate_hop_structure(
            {
                "hop_stratum": "multi_hop",
                "temporal_stratum": "far_separated",
                "one_hop_implies_near": True,
                "composition": {
                    "operator": "earlier_action_then_later_consequence",
                    "coherence_basis": "same_procedure_stage_chain",
                    "components": [
                        {
                            "interval": {"start_s": 1.0, "end_s": 2.0},
                            "claim_hypothesis": "First action.",
                        },
                        {
                            "interval": {"start_s": 200.0, "end_s": 202.0},
                            "claim_hypothesis": "Later result.",
                        },
                    ],
                    "composed_claim_hypothesis": "",
                    "arbitrary_interval_pairing_forbidden": True,
                    "each_component_required_human_validated": False,
                },
            }
        )
