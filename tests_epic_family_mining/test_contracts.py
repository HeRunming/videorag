from __future__ import annotations

import pytest

from av_trace_epic_family_mining import (
    build_rehearsal_plan,
    validate_hop_structure,
)


def test_rehearsal_plan_has_exactly_two_slots_per_source_and_no_execution():
    plan = build_rehearsal_plan()
    slots = plan["lead_structure"]["slots"]
    assert len(slots) == 4
    assert {
        source_id: sum(item["source_id"] == source_id for item in slots)
        for source_id in ("P27_101", "P28_103")
    } == {"P27_101": 2, "P28_103": 2}
    assert plan["execution_status"]["mining_executed_by_task165"] is False
    assert plan["task145_template"]["active_interventions"] is False
    assert plan["output_boundary"]["H_tiers"] is False


def test_one_hop_must_be_near():
    with pytest.raises(ValueError, match="ONE_HOP_MUST_BE_NEAR_LOCAL"):
        validate_hop_structure(
            {
                "hop_stratum": "one_hop",
                "temporal_stratum": "far_separated",
                "composition": None,
            }
        )


def test_multi_hop_requires_compositional_placeholders():
    with pytest.raises(
        TypeError, match="MULTI_HOP_REQUIRES_COMPOSITION_PLACEHOLDER"
    ):
        validate_hop_structure(
            {
                "hop_stratum": "multi_hop",
                "temporal_stratum": "near_local",
                "composition": None,
            }
        )
