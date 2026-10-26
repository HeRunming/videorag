from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from av_trace_mini_pilot_families import (
    assert_machine_provisional_only,
    build_dry_run_fixture_registry,
    slot_specs,
    validate_candidate_registry,
    validate_slot_matrix,
)

ROOT = Path(__file__).resolve().parents[1]


def test_dry_run_fixture_is_deterministic_and_matches_committed_registry():
    first = build_dry_run_fixture_registry()
    second = build_dry_run_fixture_registry()
    committed = json.loads(
        (ROOT / "data/rehearsal_plan/mini_pilot_family_mining_v1.json").read_text()
    )
    assert first == second == committed
    validate_candidate_registry(committed)
    assert committed["summary"]["real_index_access_count"] == 0
    assert committed["summary"]["real_family_count"] == 0
    assert committed["summary"]["human_reviewed_count"] == 0
    assert committed["summary"]["human_gold_count"] == 0
    assert committed["summary"]["final_accepted_family_count"] == 0


def test_slot_matrix_has_exact_12_plus_2_balance():
    slots = slot_specs()
    summary = validate_slot_matrix(slots)
    reported = [slot for slot in slots if slot.included_in_reported_denominator]
    calibration = [
        slot for slot in slots if not slot.included_in_reported_denominator
    ]
    assert summary["reported_slot_count"] == 12
    assert summary["excluded_calibration_slot_count"] == 2
    assert len(calibration) == 2
    assert Counter(slot.source_kind for slot in reported) == {
        "new_source": 8,
        "noaa_development": 4,
    }
    assert Counter(slot.target_modality_profile for slot in reported) == {
        "V": 2,
        "S": 2,
        "A": 2,
        "V+S": 2,
        "V+A/S+A": 2,
        "V+S+A": 2,
    }
    assert Counter(slot.target_intervention for slot in reported) == {
        "necessity_group_withholding": 6,
        "modality_channel_outage": 6,
    }
    assert Counter(slot.target_hop_stratum for slot in reported) == {
        "one_hop": 6,
        "multi_hop": 6,
    }
    assert Counter(slot.target_temporal_stratum for slot in reported) == {
        "near_local": 6,
        "far_separated": 6,
    }
    assert set(Counter(slot.source_id for slot in reported).values()) == {2}


def test_human_tiers_and_human_validation_assertions_fail_closed():
    with pytest.raises(ValueError, match="HUMAN_TIER_FORBIDDEN"):
        assert_machine_provisional_only({"current_tier": "H1_HUMAN_VALIDATED"})
    with pytest.raises(ValueError, match="HUMAN_OR_FINAL_ASSERTION_FORBIDDEN"):
        assert_machine_provisional_only({"human_minimality": True})

