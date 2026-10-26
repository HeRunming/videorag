from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/untouched_test_group_ledger_v2.py"
LEDGER_PATH = (
    ROOT / "data/rehearsal_plan/untouched_test_group_ledger_v2.json"
)
REVIEW_PATH = ROOT / "docs/review/untouched_test_group_ledger_v2.md"
MANIFEST_PATH = (
    ROOT / "data/rehearsal_plan/source_exposure_alias_manifest_v1.json"
)


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "untouched_test_group_ledger_v2", TOOL_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_freezes_at_least_12_conditional_groups_and_three_lineages() -> None:
    tool = load_tool()
    ledger = load(LEDGER_PATH)

    assert ledger["final_marker"] == tool.FINAL_READY
    assert ledger["decision"]["decision"] == "READY"
    assert ledger["decision"]["frozen_group_count"] >= 12
    assert len(ledger["test_groups"]) >= 12
    assert ledger["lineage_composition"]["distinct_count"] >= 3
    assert ledger["lineage_composition"]["production_lineage_count"] >= 12
    assert ledger["locks"]["distribution_locked"] is True
    assert ledger["locks"]["test_construction_locked"] is True


def test_nine_survivors_are_revalidated_and_all_manifest_candidates_selected() -> None:
    ledger = load(LEDGER_PATH)
    disposition = load(
        ROOT
        / "data/rehearsal_plan/untouched_test_group_ledger_v1_disposition.json"
    )
    manifest = load(MANIFEST_PATH)
    roots = {row["closure_root"] for row in ledger["test_groups"]}

    assert {
        row["participant_block_id"]
        for row in disposition["conditional_survivors"]
    } <= roots
    assert {
        row["closure_root"]
        for row in manifest["candidate_replacement_discovery"]
    } <= roots
    assert ledger["roster_construction"][
        "v1_conditional_survivors_revalidated"
    ] == 9
    assert ledger["roster_construction"][
        "manifest_replacement_candidates_selected"
    ] == 11


def test_eligibility_is_recomputed_from_manifest_events_not_empty_default() -> None:
    tool = load_tool()
    ledger = load(LEDGER_PATH)
    manifest = load(MANIFEST_PATH)
    by_root, _ = tool.component_maps(manifest)
    _, events_by_root = tool.indexed_events(manifest)

    assert manifest["exposure_events"]
    assert manifest["current_touched_groups"]
    for row in ledger["test_groups"]:
        result = tool.eligibility_for_root(
            row["closure_root"], manifest, by_root, events_by_root
        )
        assert result["eligible"]
        assert result["conditional_events"]
        assert not result["contaminating_events"]
        assert {
            event["event_id"] for event in result["conditional_events"]
        } == {
            event["event_id"]
            for event in row["exposure_event_bindings"]
        }


def test_cand_042_alias_and_any_touched_group_fail_closed() -> None:
    tool = load_tool()
    ledger = load(LEDGER_PATH)
    manifest = load(MANIFEST_PATH)

    changed = copy.deepcopy(ledger)
    changed["test_groups"][0]["resolved_aliases"].append("cand-042")
    changed["test_groups"][0]["group_lock_hash"] = tool.compute_group_lock_hash(
        changed["test_groups"][0]
    )
    with pytest.raises(tool.LedgerError, match="CAND_042_ALIAS_FORBIDDEN"):
        tool.validate_ledger(changed, manifest=manifest)

    changed = copy.deepcopy(ledger)
    touched = next(
        row
        for row in manifest["current_touched_groups"]
        if row["closure_root"] == "EPIC:P23"
    )
    changed["test_groups"][0]["closure_root"] = touched["closure_root"]
    changed["test_groups"][0]["resolved_aliases"] = touched["aliases"]
    changed["test_groups"][0]["group_lock_hash"] = tool.compute_group_lock_hash(
        changed["test_groups"][0]
    )
    with pytest.raises(tool.LedgerError, match="TOUCHED_GROUP_SELECTED"):
        tool.validate_ledger(changed, manifest=manifest)


def test_all_rows_bind_closure_assets_events_actions_and_status() -> None:
    tool = load_tool()
    for row in load(LEDGER_PATH)["test_groups"]:
        assert row["closure_root"]
        assert row["production_lineage_id"]
        assert row["exact_object_or_session_id"]
        assert row["representative_ids_or_assets"]
        assert row["registry_path"]
        assert row["registry_locator"]
        assert row["resolved_aliases"]
        assert row["alias_evidence"]
        assert row["exposure_event_bindings"]
        assert row["permitted_technical_only_actions"] == list(
            tool.PERMITTED_TECHNICAL_ONLY_ACTIONS
        )
        assert row["forbidden_semantics"] == list(tool.FORBIDDEN_SEMANTICS)
        assert row["conditional_status"] == "CONDITIONAL_UNTOUCHED"
        assert row["contaminating_event_ids"] == []


def test_only_technical_conditional_events_and_no_claims() -> None:
    tool = load_tool()
    ledger = load(LEDGER_PATH)

    for row in ledger["test_groups"]:
        assert {
            event["event_type"] for event in row["exposure_event_bindings"]
        } <= tool.CONDITIONAL_EVENT_TYPES
        assert not row["acquired_claimed"]
        assert not row["rights_cleared_claimed"]
        assert not row["h2_claimed"]
    assert ledger["claims"]["groups_claimed_acquired"] == 0
    assert ledger["claims"]["rights_clearance_claimed"] is False
    assert ledger["claims"]["h2_claimed"] is False


def test_contamination_log_is_derived_nonempty_and_alias_resolved() -> None:
    ledger = load(LEDGER_PATH)
    manifest = load(MANIFEST_PATH)
    touched = {
        row["closure_root"]: row
        for row in manifest["current_touched_groups"]
    }

    assert ledger["contamination_log"]
    assert {row["closure_root"] for row in ledger["contamination_log"]} == set(
        touched
    )
    city = next(
        row
        for row in ledger["contamination_log"]
        if "cand-042" in row["resolved_aliases"]
    )
    assert "cand-042" in city["resolved_aliases"]
    assert city["contaminating_event_ids"]
    assert "candidate_mined" in city["contaminating_event_types"]


def test_group_and_split_locks_detect_mutation() -> None:
    tool = load_tool()
    ledger = load(LEDGER_PATH)
    manifest = load(MANIFEST_PATH)
    tool.validate_ledger(ledger, manifest=manifest)

    changed = copy.deepcopy(ledger)
    changed["test_groups"][0]["exact_object_or_session_id"] += "_CHANGED"
    with pytest.raises(tool.LedgerError, match="GROUP_LOCK_MISMATCH"):
        tool.validate_ledger(changed, manifest=manifest)

    changed = copy.deepcopy(ledger)
    changed["decision"]["minimum_group_count"] = 13
    with pytest.raises(tool.LedgerError, match="SPLIT_LOCK_MISMATCH"):
        tool.validate_ledger(changed, manifest=manifest)


def test_authoritative_input_hashes_and_deterministic_outputs() -> None:
    tool = load_tool()
    ledger = load(LEDGER_PATH)
    for row in ledger["authoritative_inputs"]:
        assert hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest() == row[
            "sha256"
        ]

    rebuilt = tool.build_ledger(ROOT)
    assert LEDGER_PATH.read_text(encoding="utf-8") == (
        json.dumps(rebuilt, indent=2, sort_keys=True) + "\n"
    )
    assert REVIEW_PATH.read_text(encoding="utf-8") == tool.render_markdown(
        rebuilt
    )


def test_check_cli_prints_ready_marker(
    capsys: pytest.CaptureFixture[str],
) -> None:
    tool = load_tool()
    assert tool.main(["--root", str(ROOT), "--check"]) == 0
    assert capsys.readouterr().out.strip() == tool.FINAL_READY
