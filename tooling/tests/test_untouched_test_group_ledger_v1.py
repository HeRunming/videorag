from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/untouched_test_group_ledger_v1.py"
LEDGER_PATH = (
    ROOT / "data/rehearsal_plan/untouched_test_group_ledger_v1.json"
)
MARKDOWN_PATH = ROOT / "docs/review/untouched_test_group_ledger_v1.md"


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "untouched_test_group_ledger_v1", TOOL_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_ledger() -> dict:
    return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))


def test_exact_12_groups_and_six_lineages_are_frozen() -> None:
    tool = load_tool()
    ledger = load_ledger()
    groups = ledger["test_groups"]

    assert ledger["final_marker"] == tool.FINAL_READY
    assert ledger["decision"]["freeze_decision"] == "READY"
    assert ledger["decision"]["controlled_test_construction"] == "LOCKED"
    assert [row["source_group_id"] for row in groups] == list(
        tool.EXPECTED_TEST_IDS
    )
    assert len(groups) == 12
    assert ledger["lineage_composition"]["counts"] == {
        "ASSEMBLY101": 3,
        "CAPTAINCOOK4D": 3,
        "EPIC_KITCHENS_100": 3,
        "NARA_ARCHIVAL_FILM": 1,
        "NASA_JPL_DOCUMENTARY": 1,
        "USGS_PUBLIC_MEDIA": 1,
    }
    assert ledger["lineage_composition"]["distinct_count"] == 6


def test_all_groups_are_conditional_unacquired_non_h2_reserves() -> None:
    ledger = load_ledger()

    assert ledger["scope"]["all_groups_are_conditional_reserves"]
    assert ledger["scope"]["groups_claimed_acquired"] == 0
    assert ledger["scope"]["h2_families_created_or_claimed"] == 0
    assert not ledger["scope"]["media_acquired_by_this_ledger"]
    assert not ledger["scope"]["scientific_test_execution_authorized"]
    for row in ledger["test_groups"]:
        assert row["reservation_class"] == "CONDITIONAL_RESERVE"
        assert row["semantic_exposure_allowed_now"] is False
        assert row["acquired_claimed"] is False
        assert row["rights_cleared_claimed"] is False
        assert row["h2_claimed"] is False


def test_group_closure_covers_all_media_views_annotations_derivatives() -> None:
    for row in load_ledger()["test_groups"]:
        closure = row["group_closure"].lower()
        assert "media" in closure
        assert "views" in closure
        assert "annotations" in closure
        assert "derivatives" in closure
        assert "embeddings" in closure
        assert "future derivatives" in closure


def test_forbidden_and_permitted_preunlock_activities_are_exact() -> None:
    tool = load_tool()
    policy = load_ledger()["governance_policy"]

    assert policy["permitted_scope_is_exhaustive"]
    assert policy["permitted_before_controlled_test_construction"] == list(
        tool.PERMITTED_TECHNICAL_PREFLIGHT
    )
    forbidden = " ".join(
        policy["forbidden_before_controlled_test_construction"]
    )
    for token in (
        "CANDIDATE_MINING",
        "LEARNED_RETRIEVAL",
        "ASR",
        "CLAP",
        "SIGLIP",
        "PROMPT_TUNING",
        "HUMAN_SEMANTIC_PRESCREEN",
    ):
        assert token in forbidden


def test_exposure_states_and_custodian_only_reveal_fail_closed() -> None:
    ledger = load_ledger()
    states = ledger["exposure_state_machine"]
    custody = ledger["custody_and_reveal_policy"]

    assert "CONTAMINATED_INVALID_FOR_UNTOUCHED_TEST" in states["states"]
    assert "CONTROLLED_TEST_CONSTRUCTION_UNLOCKED" in states["states"]
    assert states["state_changes_require_logged_event_and_recomputed_lock"]
    assert custody["development_team_reveal_before_unlock"] is False
    assert custody["unlogged_reveal_is_contamination"]
    held = " ".join(custody["custodian_only_before_unlock"]).lower()
    assert "playable media" in held
    assert "annotations" in held
    assert "embeddings" in held
    assert "model outputs" in held


def test_split_lock_hashes_verify_and_mutation_is_detected() -> None:
    tool = load_tool()
    ledger = load_ledger()

    tool.validate_ledger(ledger)
    assert all(
        row["group_lock_hash"] == tool.compute_group_lock_hash(row)
        for row in ledger["test_groups"]
    )

    changed = copy.deepcopy(ledger)
    changed["test_groups"][0]["exact_object_or_session_id"] = "P01_CHANGED"
    with pytest.raises(tool.LedgerError, match="GROUP_LOCK_MISMATCH"):
        tool.validate_ledger(changed)

    changed = copy.deepcopy(ledger)
    changed["replacement_policy"]["minimum_frozen_group_count"] = 11
    with pytest.raises(tool.LedgerError, match="SPLIT_LOCK_MISMATCH"):
        tool.validate_ledger(changed)


def test_development_calibration_and_mined_groups_are_excluded() -> None:
    exclusions = load_ledger()[
        "excluded_development_and_calibration_groups"
    ]
    exact = {row["source_group_id"] for row in exclusions["exact_exclusions"]}

    assert {"P23", "P27", "P28"} <= exact
    assert {
        "cc4d_p01_e08",
        "cc4d_p02_e02",
        "cc4d_p03_e03",
        "cc4d_p05_e07",
    } <= exact
    assert {"P12", "assembly101_p9051"} <= exact
    patterns = " ".join(
        row["pattern"] for row in exclusions["pattern_exclusions"]
    )
    assert "cand-" in patterns
    assert "after candidate mining" in patterns


def test_replacement_preserves_count_and_lineage_and_is_not_outcome_based() -> None:
    policy = load_ledger()["replacement_policy"]

    assert policy["outcome_conditioned_replacement_forbidden"]
    assert policy["minimum_frozen_group_count"] == 12
    assert policy["lineage_count_must_not_decrease"]
    assert "same dataset/production lineage" in policy[
        "automatic_replacement_rule"
    ]
    assert policy["predeclared_same_lineage_reserves"][
        "USGS_PUBLIC_MEDIA"
    ] == []
    assert policy["not_automatic_replacements"][0][
        "source_group_id"
    ] == "MECCANO"
    assert "mined" in policy["reserve_contamination_rule"]


def test_contamination_event_schema_and_empty_initial_log() -> None:
    contamination = load_ledger()["contamination_ledger"]

    assert contamination["events"] == []
    required = contamination["event_schema"]["required_fields"]
    assert {
        "actor_or_system_id",
        "source_group_id",
        "participant_block_id",
        "production_lineage_id",
        "exposure_class",
        "semantic_fields_visible",
        "disposition",
        "replacement_addendum_id",
    } <= set(required)
    classes = contamination["event_schema"]["exposure_classes"]
    assert "LEARNED_RETRIEVAL_INSPECTION" in classes
    assert "PROMPT_TUNING_OR_MODEL_GUIDED_AUTHORING" in classes


def test_authoritative_input_hashes_are_current() -> None:
    for row in load_ledger()["authoritative_inputs"]:
        observed = hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest()
        assert observed == row["sha256"]


def test_committed_outputs_are_deterministic_and_current() -> None:
    tool = load_tool()
    ledger = tool.build_ledger(ROOT)

    assert LEDGER_PATH.read_text(encoding="utf-8") == (
        json.dumps(ledger, indent=2, sort_keys=True) + "\n"
    )
    assert MARKDOWN_PATH.read_text(encoding="utf-8") == tool.render_markdown(
        ledger
    )


def test_check_cli_prints_ready_marker(
    capsys: pytest.CaptureFixture[str],
) -> None:
    tool = load_tool()

    result = tool.main(["--root", str(ROOT), "--check"])

    assert result == 0
    assert capsys.readouterr().out.strip() == tool.FINAL_READY
