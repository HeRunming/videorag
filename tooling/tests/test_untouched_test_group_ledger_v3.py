from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/untouched_test_group_ledger_v3.py"
MANIFEST_PATH = (
    ROOT / "data/rehearsal_plan/source_exposure_alias_manifest_v2.json"
)
PRIVATE_PATH = (
    ROOT / "data/restricted/untouched_test_group_ledger_v3_private.json"
)
PUBLIC_PATH = (
    ROOT
    / "data/rehearsal_plan/"
    "untouched_test_group_ledger_v3_public_commitment.json"
)
REVIEW_PATH = ROOT / "docs/review/untouched_test_group_ledger_v3.md"


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "untouched_test_group_ledger_v3", TOOL_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def selected_identity_strings(private: dict) -> set[str]:
    values: set[str] = set()
    for row in private["selected_groups"]:
        values.add(row["closure_root"])
        values.add(row["exact_object_or_session_id"])
        values.update(row["closure_aliases"])
    return {value for value in values if value}


def test_manifest_v2_neutral_universe_is_the_only_candidate_authority() -> None:
    tool = load_tool()
    manifest = load(MANIFEST_PATH)
    private = load(PRIVATE_PATH)
    eligible = tool.derive_eligible_universe(manifest)
    eligible_roots = {row["closure_root"] for row in eligible}
    contaminated = {
        row["closure_root"] for row in manifest["contaminated_closures"]
    }
    private_roots = {
        row["closure_root"] for row in private["selected_groups"]
    }
    replacement_roots = {
        row["closure_root"]
        for row in private["unselected_neutral_replacement_pool"]
    }

    assert manifest["final_marker"] == tool.MANIFEST_READY
    assert eligible
    assert not (eligible_roots & contaminated)
    assert private_roots <= eligible_roots
    assert replacement_roots <= eligible_roots
    assert private_roots.isdisjoint(replacement_roots)
    assert private_roots | replacement_roots == eligible_roots
    assert all(
        row["semantic_routing_event_count"] == 0 for row in eligible
    )


def test_twelve_exact_complete_conditional_closures_are_locked() -> None:
    tool = load_tool()
    private = load(PRIVATE_PATH)
    groups = private["selected_groups"]

    assert len(groups) == tool.TARGET_GROUP_COUNT
    assert len({row["closure_root"] for row in groups}) == len(groups)
    assert len(
        {row["production_lineage_id"] for row in groups}
    ) == len(groups)
    for row in groups:
        assert row["closure_kind"] == (
            "COMPLETE_SOURCE_PARTICIPANT_OR_PRODUCTION_CLOSURE"
        )
        assert row["closure_root"] in row["closure_aliases"]
        assert row["exact_object_or_session_id"] in row["closure_aliases"]
        assert row["closure_member_count"] == len(row["closure_aliases"])
        assert row["closure_evidence"]
        assert row["neutral_candidate_evidence"]
        assert row["conditional_status"] == "CONDITIONAL"
        assert row["test_construction_locked"] is True
        assert row["distribution_locked"] is True


def test_repair_is_required_because_manifest_has_only_two_lineages() -> None:
    tool = load_tool()
    manifest = load(MANIFEST_PATH)
    private = load(PRIVATE_PATH)
    public = load(PUBLIC_PATH)
    eligible = tool.derive_eligible_universe(manifest)
    universe_lineages = {row["family"] for row in eligible}

    assert universe_lineages == {"ASSEMBLY101", "EPIC"}
    assert len(universe_lineages) == 2
    assert tool.MINIMUM_DATASET_LINEAGES == 3
    assert len(private["selected_groups"]) >= 12
    assert (
        private["lineage_composition"]["selected_dataset_lineage_count"]
        == 2
    )
    assert private["decision"]["lineage_constraint_satisfied"] is False
    assert public["decision"]["lineage_constraint_satisfied"] is False
    assert private["final_marker"] == tool.FINAL_REPAIR
    assert public["final_marker"] == tool.FINAL_REPAIR
    assert "below the required minimum" in private["decision"][
        "repair_reason"
    ]


def test_selector_view_is_opaque_nonsemantic_and_blind_to_identity() -> None:
    tool = load_tool()
    manifest = load(MANIFEST_PATH)
    private = load(PRIVATE_PATH)
    material = private["private_material"]
    opaque = tool.build_opaque_universe(manifest, material)

    assert opaque
    for row in opaque:
        view = row["selector_view"]
        assert tuple(view) == tool.SELECTOR_ALLOWED_FIELDS
        assert not tool._contains_forbidden_selector_key(view)
        assert not tool._contains_forbidden_selector_key(
            {
                "opaque_candidate_id": view["opaque_candidate_id"],
                "opaque_dataset_lineage_id": view[
                    "opaque_dataset_lineage_id"
                ],
                "selection_score_sha256": row[
                    "selection_score_sha256"
                ],
            }
        )
        serialized = json.dumps(view, sort_keys=True)
        assert row["identity"]["closure_root"] not in serialized
        assert (
            row["identity"]["exact_object_or_session_id"]
            not in serialized
        )

    selected, _ = tool.blind_select(opaque)
    changed = copy.deepcopy(opaque)
    for index, row in enumerate(changed):
        row["identity"]["title"] = f"forbidden-title-{index}"
        row["identity"]["description"] = f"forbidden-description-{index}"
        row["identity"]["semantic_target"] = f"forbidden-target-{index}"
    selected_changed, _ = tool.blind_select(changed)
    assert [
        row["selector_view"]["opaque_candidate_id"] for row in selected
    ] == [
        row["selector_view"]["opaque_candidate_id"]
        for row in selected_changed
    ]


def test_public_commitment_and_review_disclose_no_selected_identity() -> None:
    tool = load_tool()
    private = load(PRIVATE_PATH)
    public_text = PUBLIC_PATH.read_text(encoding="utf-8")
    review_text = REVIEW_PATH.read_text(encoding="utf-8")
    public = json.loads(public_text)

    tool.validate_public_non_disclosure(
        private, public_text=public_text, review_text=review_text
    )
    for identity in selected_identity_strings(private):
        assert identity not in public_text
        assert identity not in review_text
    forbidden_public_keys = {
        "closure_root",
        "exact_object_or_session_id",
        "closure_aliases",
        "dataset_lineage_id",
        "production_lineage_id",
        "commitment_salt_hex",
    }
    assert forbidden_public_keys.isdisjoint(public.keys())
    for row in public["group_commitments"]:
        assert forbidden_public_keys.isdisjoint(row)
        assert row["opaque_candidate_id"].startswith("oc-")
        assert row["opaque_dataset_lineage_id"].startswith("dl-")


def test_salted_group_commitments_and_private_commitment_match() -> None:
    tool = load_tool()
    private = load(PRIVATE_PATH)
    public = load(PUBLIC_PATH)
    by_slot = {row["slot"]: row for row in public["group_commitments"]}

    assert len(by_slot) == len(private["selected_groups"])
    for row in private["selected_groups"]:
        assert len(row["commitment_salt_hex"]) == 64
        expected = tool.compute_group_commitment(row)
        assert row["group_commitment_sha256"] == expected
        assert by_slot[row["slot"]]["group_commitment_sha256"] == expected
        changed = copy.deepcopy(row)
        changed["commitment_salt_hex"] = "00" * 32
        assert tool.compute_group_commitment(changed) != expected

    private_commitment = tool.compute_private_roster_commitment(private)
    assert private["sealed_private_roster_commitment_sha256"] == (
        private_commitment
    )
    assert public["sealed_private_roster_commitment_sha256"] == (
        private_commitment
    )


def test_full_governance_split_lock_covers_every_required_surface() -> None:
    tool = load_tool()
    public = load(PUBLIC_PATH)
    required_surfaces = {
        "authoritative_inputs",
        "source_boundaries",
        "contamination_policy",
        "eligibility_policy",
        "blind_selection",
        "roster_construction",
        "lineage_composition",
        "locks",
        "claims",
        "custodian_reveal_rules",
        "replacement_policy",
        "group_commitments",
        "sealed_private_roster_commitment_sha256",
        "governance",
        "decision",
        "final_marker",
    }

    assert set(public["governance"]) == set(tool.GOVERNANCE_FIELDS)
    assert required_surfaces <= set(tool.SPLIT_LOCK_COVERED_FIELDS)
    assert public["split_lock"]["covered_top_level_fields"] == list(
        tool.SPLIT_LOCK_COVERED_FIELDS
    )
    assert set(public) - {"split_lock"} == set(
        tool.SPLIT_LOCK_COVERED_FIELDS
    )
    assert public["split_lock"]["split_lock_sha256"] == (
        tool.compute_split_lock_hash(public)
    )

    changed = copy.deepcopy(public)
    changed["locks"]["distribution_locked"] = False
    assert tool.compute_split_lock_hash(changed) != public["split_lock"][
        "split_lock_sha256"
    ]
    changed = copy.deepcopy(public)
    changed["governance"]["replacement_protocol"][
        "revealed_reserve_list_forbidden"
    ] = False
    assert tool.compute_split_lock_hash(changed) != public["split_lock"][
        "split_lock_sha256"
    ]
    changed = copy.deepcopy(public)
    changed["final_marker"] = "MUTATED"
    assert tool.compute_split_lock_hash(changed) != public["split_lock"][
        "split_lock_sha256"
    ]


def test_custodian_reveal_and_unselected_replacement_rules_fail_closed() -> None:
    private = load(PRIVATE_PATH)
    public = load(PUBLIC_PATH)
    reveal = public["custodian_reveal_rules"]
    replacement = public["replacement_policy"]

    assert reveal["identity_mapping_custodian_only"] is True
    assert "OPAQUE_SELECTOR" in reveal["forbidden_identity_recipients"]
    assert "TEST_CONSTRUCTION_ROLE" in reveal[
        "forbidden_identity_recipients"
    ]
    assert "REPAIR forbids reveal" in reveal["repair_state_rule"]
    assert replacement["source"] == "PRIVATE_UNSELECTED_NEUTRAL_POOL_ONLY"
    assert replacement["allowed_before_identity_reveal_only"] is True
    assert replacement["revealed_reserve_list_forbidden"] is True
    assert private["unselected_neutral_replacement_pool"]
    assert all(
        row["replacement_eligibility"]
        == "UNSELECTED_NEUTRAL_POOL_ONLY"
        for row in private["unselected_neutral_replacement_pool"]
    )


def test_all_locks_claims_boundaries_and_authoritative_hashes() -> None:
    tool = load_tool()
    private = load(PRIVATE_PATH)
    public = load(PUBLIC_PATH)

    assert private["locks"] == public["locks"] == tool._locks()
    assert private["claims"] == public["claims"] == tool._claims()
    assert all(private["locks"][key] for key in (
        "test_construction_locked",
        "distribution_locked",
        "identity_publication_locked",
        "evaluation_execution_locked",
    ))
    assert private["locks"]["unlock_authorized"] is False
    assert not any(private["claims"].values())
    boundaries = private["source_boundaries"]
    assert boundaries["network_used"] is False
    assert boundaries["media_opened_or_inspected"] is False
    assert boundaries["semantic_annotation_bodies_opened"] is False
    assert boundaries["transcript_or_caption_bodies_opened"] is False
    assert boundaries["model_or_learned_ranking_used"] is False
    for row in private["authoritative_inputs"]:
        assert tool.sha256_file(ROOT / row["path"]) == row["sha256"]


def test_exact_permissions_are_enforced() -> None:
    tool = load_tool()
    tool.check_permissions(ROOT)
    assert PRIVATE_PATH.parent.stat().st_mode & 0o777 == 0o700
    assert PRIVATE_PATH.stat().st_mode & 0o777 == 0o600
    assert PUBLIC_PATH.stat().st_mode & 0o777 == 0o644
    assert REVIEW_PATH.stat().st_mode & 0o777 == 0o644


def test_deterministic_rebuild_and_render() -> None:
    tool = load_tool()
    rebuilt_private, rebuilt_public = tool.build_artifacts(ROOT)
    assert PRIVATE_PATH.read_text(encoding="utf-8") == (
        json.dumps(rebuilt_private, indent=2, sort_keys=True) + "\n"
    )
    assert PUBLIC_PATH.read_text(encoding="utf-8") == (
        json.dumps(rebuilt_public, indent=2, sort_keys=True) + "\n"
    )
    assert REVIEW_PATH.read_text(encoding="utf-8") == tool.render_markdown(
        rebuilt_public
    )


def test_validation_detects_group_public_and_split_mutations() -> None:
    tool = load_tool()
    private = load(PRIVATE_PATH)
    public = load(PUBLIC_PATH)
    manifest = load(MANIFEST_PATH)
    tool.validate_artifacts(private, public, manifest=manifest)

    changed_private = copy.deepcopy(private)
    changed_private["selected_groups"][0][
        "exact_object_or_session_id"
    ] += "-changed"
    with pytest.raises(
        tool.LedgerError, match="SELECTED_EXACT_ID_MISMATCH"
    ):
        tool.validate_artifacts(
            changed_private, public, manifest=manifest
        )

    changed_public = copy.deepcopy(public)
    changed_public["group_commitments"][0][
        "group_commitment_sha256"
    ] = "0" * 64
    with pytest.raises(
        tool.LedgerError, match="PUBLIC_GROUP_COMMITMENT_MISMATCH"
    ):
        tool.validate_artifacts(
            private, changed_public, manifest=manifest
        )

    changed_public = copy.deepcopy(public)
    changed_public["decision"]["repair_reason"] += " mutated"
    with pytest.raises(tool.LedgerError, match="SPLIT_LOCK_MISMATCH"):
        tool.validate_artifacts(
            private, changed_public, manifest=manifest
        )


def test_check_cli_prints_repair_marker(
    capsys: pytest.CaptureFixture[str],
) -> None:
    tool = load_tool()
    assert tool.main(["--root", str(ROOT), "--check"]) == 0
    assert capsys.readouterr().out.strip() == tool.FINAL_REPAIR
