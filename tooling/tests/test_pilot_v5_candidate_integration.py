from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/pilot_v5_candidate_integration.py"
MATRIX_PATH = ROOT / "data/rehearsal_plan/pilot_v5_candidate_matrix.json"


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "pilot_v5_candidate_integration", TOOL_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rehash(tool, matrix):
    matrix["matrix_payload_sha256"] = tool.object_hash(
        {
            key: value
            for key, value in matrix.items()
            if key != "matrix_payload_sha256"
        }
    )


def test_build_is_deterministic_and_matches_checked_in_matrix() -> None:
    tool = load_tool()
    first = tool.build_matrix()
    second = tool.build_matrix()
    checked_in = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))

    assert tool.canonical_bytes(first) == tool.canonical_bytes(second)
    assert tool.canonical_bytes(first) == tool.canonical_bytes(checked_in)
    tool.validate_matrix(checked_in)


def test_baseline_slots_and_statuses_are_preserved_without_replacement() -> None:
    tool = load_tool()
    matrix = tool.build_matrix()
    v4 = json.loads(tool.V4_PATH.read_text(encoding="utf-8"))

    assert matrix["scope"]["baseline_v4_slots_modified"] == 0
    assert matrix["baseline_v4"]["candidate_slot_count"] == 12
    assert matrix["baseline_v4"]["all_slots_and_statuses_preserved"] is True
    assert [item["slot_id"] for item in matrix["baseline_v4"]["slots"]] == [
        item["slot_id"] for item in v4["candidate_slots"]
    ]
    assert [
        item["matrix_disposition"] for item in matrix["baseline_v4"]["slots"]
    ] == [item["matrix_disposition"] for item in v4["candidate_slots"]]
    assert all(
        lead["integration_treatment"]
        == "ADDITIVE_DEVELOPMENT_LEAD_OVERLAY_NOT_A_PILOT_V4_SLOT_REPLACEMENT"
        for lead in matrix["retained_v5_development_leads"]
    )


def test_retained_leads_keep_exact_status_and_never_receive_credit() -> None:
    tool = load_tool()
    retained = tool.build_matrix()["retained_v5_development_leads"]

    assert [item["candidate_id"] for item in retained] == [
        "NOAA-V5-047-OCEAN-MODEL-TWILIGHT",
        "NOAA-V5-051-TRASH-TRIP-DATA",
        "NOAA-V5-049-WAVE-ENTRY-RESCUE",
    ]
    assert [item["provisional_status"] for item in retained] == [
        "KEEP",
        "KEEP",
        "REPAIR",
    ]
    for item in retained:
        assert item["human_reviewed"] is False
        assert item["accepted_ses_count"] == 0
        assert item["h_tier"] is None
        assert item["gate_a_credit"] is False
        assert item["future_test_eligible"] is False
        assert item["counts_in_gate_a"] is False


def test_conservative_and_optimistic_coverage_is_honest() -> None:
    tool = load_tool()
    scenarios = tool.build_matrix()["coverage_scenarios"]
    conservative = scenarios["conservative_keep_only"]
    optimistic = scenarios["optimistic_all_retained"]

    assert conservative["included_statuses"] == ["KEEP"]
    assert conservative["inventory_view"]["retained_development_leads"] == 2
    assert conservative["delta_from_baseline_v4"] == {
        "profiles": {"V+S": 2},
        "hop": {"multi": 2},
        "temporal": {"far_separated": 2},
    }
    assert optimistic["included_statuses"] == ["KEEP", "REPAIR"]
    assert optimistic["inventory_view"]["retained_development_leads"] == 3
    assert optimistic["delta_from_baseline_v4"] == {
        "profiles": {"V+S": 3},
        "hop": {"multi": 3},
        "temporal": {"far_separated": 3},
    }

    for scenario, far_shortage in ((conservative, 3), (optimistic, 2)):
        closure = scenario["shortage_closure"]
        assert closure["V+S"]["provisionally_closed_by_retained_leads"] is True
        assert (
            closure["multi_hop"]["provisionally_closed_by_retained_leads"]
            is True
        )
        assert (
            closure["far_separated"]["provisionally_closed_by_retained_leads"]
            is False
        )
        assert closure["far_separated"]["provisional_shortage"] == far_shortage
        assert (
            closure["V+S+A"]["provisionally_closed_by_retained_leads"] is False
        )
        assert closure["V+S+A"]["provisional_shortage"] == 2
        assert (
            scenario["inventory_view"]["constraint_valid_exact_pilot_roster"]
            is False
        )


def test_source_group_constraints_are_explicitly_failed_not_hidden() -> None:
    tool = load_tool()
    matrix = tool.build_matrix()
    baseline_groups = set(matrix["baseline_v4"]["source_group_ids"])
    retained_groups = {
        item["source_group_id"]
        for item in matrix["retained_v5_development_leads"]
    }

    assert baseline_groups.isdisjoint(retained_groups)
    for scenario in matrix["coverage_scenarios"].values():
        result = scenario["structural_constraint_result"]
        assert result["exact_six_source_groups"] is False
        assert result["exact_two_candidates_per_source_group"] is False
        assert result["exact_twelve_candidates"] is False
        assert result["presentation_wrapped_group_cap_satisfied"] is False


def test_exact_next_wave_routes_prescreen_acquisition_and_narrowing() -> None:
    tool = load_tool()
    wave = tool.build_matrix()["exact_next_wave"]

    assert [item["candidate_id"] for item in wave["wave_0_human_prescreen"]] == [
        "NOAA-V5-047-OCEAN-MODEL-TWILIGHT",
        "NOAA-V5-051-TRASH-TRIP-DATA",
        "NOAA-V5-049-WAVE-ENTRY-RESCUE",
    ]
    assert all(
        item["automatic_roster_replacement"] is False
        for item in wave["wave_0_human_prescreen"]
    )
    assert [
        item["target_slot"]
        for item in wave["wave_1_new_audio_rich_source_acquisition"]
    ] == ["B08", "B12", "FAR-KEEP-ONLY-01"]
    assert wave["wave_1_new_audio_rich_source_acquisition"][0][
        "required_profile"
    ] == "V+S+A"
    assert wave["wave_1_new_audio_rich_source_acquisition"][1][
        "required_profile"
    ] == "V+S+A"
    assert [item["target_slots"] for item in wave["wave_2_prospective_target_narrowing"]] == [
        ["B08", "B12"],
        ["far_separated_quota"],
        ["B02", "B11"],
    ]


def test_validator_rejects_status_promotion_double_counting_and_vsa_invention() -> None:
    tool = load_tool()
    matrix = tool.build_matrix()

    promoted = copy.deepcopy(matrix)
    promoted["retained_v5_development_leads"][0]["gate_a_credit"] = True
    rehash(tool, promoted)
    with pytest.raises(tool.IntegrationError, match="promoted"):
        tool.validate_matrix(promoted)

    duplicate = copy.deepcopy(matrix)
    duplicate["retained_v5_development_leads"][0]["integration_slot_id"] = (
        duplicate["baseline_v4"]["slots"][0]["slot_id"]
    )
    rehash(tool, duplicate)
    with pytest.raises(tool.IntegrationError, match="double counting"):
        tool.validate_matrix(duplicate)

    invented = copy.deepcopy(matrix)
    invented["coverage_scenarios"]["conservative_keep_only"]["shortage_closure"][
        "V+S+A"
    ]["provisionally_closed_by_retained_leads"] = True
    rehash(tool, invented)
    with pytest.raises(tool.IntegrationError, match="V\\+S\\+A"):
        tool.validate_matrix(invented)


def test_cli_check_mode_reports_honest_repair() -> None:
    completed = subprocess.run(
        [sys.executable, str(TOOL_PATH), "--check"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout.strip() == "PILOT_V5_CANDIDATE_MATRIX_REPAIR"
