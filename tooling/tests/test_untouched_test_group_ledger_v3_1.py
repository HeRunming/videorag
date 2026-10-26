from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/untouched_test_group_ledger_v3_1.py"
V3_PRIVATE_PATH = (
    ROOT / "data/restricted/untouched_test_group_ledger_v3_private.json"
)
V3_PUBLIC_PATH = (
    ROOT
    / "data/rehearsal_plan/"
    "untouched_test_group_ledger_v3_public_commitment.json"
)
MANIFEST_PATH = (
    ROOT / "data/rehearsal_plan/source_exposure_alias_manifest_v2.json"
)
HOLO_PRIVATE_PATH = (
    ROOT / "data/restricted/holoassist_opaque_group_universe_v1.json"
)
HOLO_PUBLIC_PATH = (
    ROOT / "data/rehearsal_plan/holoassist_opaque_group_commitment_v1.json"
)
PRIVATE_PATH = (
    ROOT
    / "data/restricted/"
    "untouched_test_group_ledger_v3_1_private.json"
)
PUBLIC_PATH = (
    ROOT
    / "data/rehearsal_plan/"
    "untouched_test_group_ledger_v3_1_public_commitment.json"
)
REVIEW_PATH = (
    ROOT / "docs/review/untouched_test_group_ledger_v3_1.md"
)


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "untouched_test_group_ledger_v3_1", TOOL_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def selected_identity_strings(private: dict) -> set[str]:
    values: set[str] = set()
    for group in private["selected_groups"]:
        evidence = group["identity_and_evidence"]
        if group["dataset_lineage"] == "HOLOASSIST":
            source = evidence["opaque_universe_group"]
            values.add(source["recording_root"])
            for variant in source["variants"]:
                values.add(variant["folder"])
                values.add(variant["timing_path"])
                values.add(variant["pose_path"])
        else:
            values.add(evidence["closure_root"])
            values.add(evidence["exact_object_or_session_id"])
            values.update(evidence["closure_aliases"])
    return {value for value in values if value}


def test_public_and_review_have_no_selected_identity_or_private_paths() -> None:
    tool = load_tool()
    private = load(PRIVATE_PATH)
    public_text = PUBLIC_PATH.read_text(encoding="utf-8")
    review_text = REVIEW_PATH.read_text(encoding="utf-8")
    tool.validate_public_non_disclosure(
        private, public_text=public_text, review_text=review_text
    )
    combined = public_text + "\n" + review_text
    for identity in selected_identity_strings(private):
        assert identity not in combined
    for forbidden in (
        '"identity_and_evidence"',
        '"v3_1_commitment_salt_hex"',
        "extracted_videos/",
        "VideoMp4Timing",
        "Pose_sync",
    ):
        assert forbidden not in combined


def test_private_public_group_commitments_match_exactly() -> None:
    tool = load_tool()
    private = load(PRIVATE_PATH)
    public = load(PUBLIC_PATH)
    public_by_slot = {
        row["slot"]: row for row in public["group_commitments"]
    }
    assert len(public_by_slot) == len(private["selected_groups"]) == 12
    for group in private["selected_groups"]:
        expected = tool.compute_group_commitment(group)
        public_group = public_by_slot[group["slot"]]
        assert group["v3_1_group_commitment_sha256"] == expected
        assert public_group["v3_1_group_commitment_sha256"] == expected
        assert (
            public_group["source_commitment_sha256"]
            == group["source_commitment_sha256"]
        )
        assert public_group["dataset_lineage"] == group["dataset_lineage"]
    roster_commitment = tool.compute_private_roster_commitment(private)
    assert private["sealed_private_roster_commitment_sha256"] == (
        roster_commitment
    )
    assert public["sealed_private_roster_commitment_sha256"] == (
        roster_commitment
    )


def test_holoassist_groups_are_exposure_clean_timing_closed_conditional() -> None:
    private = load(PRIVATE_PATH)
    holo_private = load(HOLO_PRIVATE_PATH)
    manifest_bytes = MANIFEST_PATH.read_bytes()
    exposed = set(holo_private["policy"]["explicit_exclusions"])
    exposed.update(holo_private["policy"]["semantic_text_exclusions"])
    groups = [
        row
        for row in private["selected_groups"]
        if row["dataset_lineage"] == "HOLOASSIST"
    ]
    assert len(groups) >= 3
    for group in groups:
        source = group["identity_and_evidence"]["opaque_universe_group"]
        identity = source["recording_root"]
        token = re.compile(
            rb"(?<![A-Za-z0-9])"
            + re.escape(identity.encode("ascii"))
            + rb"(?![A-Za-z0-9])",
            re.IGNORECASE,
        )
        assert identity not in exposed
        assert token.search(manifest_bytes) is None
        assert group["conditional_status"] == "CONDITIONAL"
        assert group["timing_closed"] is True
        assert group["video_exact_access_resolved"] is False
        assert group["audio_exact_access_resolved"] is False
        assert group["semantic_routing_event_count"] == 0
        assert group["production_closure_complete"] is True
        assert source["timing_closed"] is True
        assert source["variants"]
        for variant in source["variants"]:
            timing = variant["timing_evidence"]
            assert variant["timing_present"] is True
            assert timing["fetched"] is True
            assert timing["format_recognized"] is True
            assert re.fullmatch(r"[0-9a-f]{64}", timing["sha256"])


def test_lineage_group_and_production_closure_thresholds_are_met() -> None:
    tool = load_tool()
    private = load(PRIVATE_PATH)
    public = load(PUBLIC_PATH)
    groups = private["selected_groups"]
    lineages = {row["dataset_lineage"] for row in groups}
    assert len(groups) >= tool.TARGET_GROUP_COUNT
    assert lineages == {"ASSEMBLY101", "EPIC", "HOLOASSIST"}
    assert len(lineages) >= tool.MINIMUM_DATASET_LINEAGES
    assert sum(
        row["production_closure_complete"] for row in groups
    ) >= tool.MINIMUM_PRODUCTION_CLOSURES
    assert len(
        [
            row
            for row in groups
            if row["dataset_lineage"] == "HOLOASSIST"
        ]
    ) >= tool.HOLOASSIST_SELECTION_COUNT
    assert private["final_marker"] == tool.FINAL_READY
    assert public["final_marker"] == tool.FINAL_READY
    assert public["decision"]["decision"] == "FROZEN_PRIVATE_READY"


def test_selection_is_commitment_only_and_deterministic() -> None:
    tool = load_tool()
    v3 = load(V3_PRIVATE_PATH)
    holo_public = load(HOLO_PUBLIC_PATH)
    source_commitments = [
        row["group_commitment_sha256"] for row in v3["selected_groups"]
    ]
    holo_commitments = list(holo_public["commitments"])
    expected = tool.select_commitment_roster(
        source_commitments, holo_commitments
    )
    assert expected["selected_holoassist_commitments"] == sorted(
        holo_commitments
    )[: tool.HOLOASSIST_SELECTION_COUNT]
    assert expected["removed_v3_commitments"] == sorted(
        source_commitments, reverse=True
    )[: tool.HOLOASSIST_SELECTION_COUNT]

    # Identity-bearing mutations cannot enter the selector because its entire
    # input is the two commitment lists.
    mutated_v3 = copy.deepcopy(v3)
    for index, row in enumerate(mutated_v3["selected_groups"]):
        row["closure_root"] = f"mutated-private-identity-{index}"
        row["exact_object_or_session_id"] = (
            f"mutated-private-object-{index}"
        )
    mutated_source_commitments = [
        row["group_commitment_sha256"]
        for row in mutated_v3["selected_groups"]
    ]
    assert tool.select_commitment_roster(
        mutated_source_commitments, list(reversed(holo_commitments))
    ) == expected

    first_private, first_public = tool.build_artifacts(ROOT)
    second_private, second_public = tool.build_artifacts(ROOT)
    assert tool.canonical_bytes(first_private) == tool.canonical_bytes(
        second_private
    )
    assert tool.canonical_bytes(first_public) == tool.canonical_bytes(
        second_public
    )


def test_no_network_media_or_semantic_annotation_use() -> None:
    private = load(PRIVATE_PATH)
    public = load(PUBLIC_PATH)
    for boundary in (
        private["source_boundaries"],
        public["source_boundaries"],
    ):
        assert boundary["network_used"] is False
        assert boundary["media_opened_or_inspected"] is False
        assert boundary["semantic_annotation_bodies_opened"] is False
        assert boundary["transcript_or_caption_bodies_opened"] is False
        assert boundary["model_or_learned_ranking_used"] is False
        assert boundary["candidate_mining_performed"] is False
    assert private["selection"]["allowed_fields"] == [
        "source_commitment_sha256",
        "source_pool",
    ]
    selection_text = json.dumps(
        private["selection"]["final_selection_transcript"],
        sort_keys=True,
    ).lower()
    for forbidden in private["selection"]["forbidden_fields"]:
        assert forbidden not in selection_text


def test_all_v3_locks_claims_custodian_and_replacement_policy_preserved() -> None:
    v3 = load(V3_PRIVATE_PATH)
    private = load(PRIVATE_PATH)
    public = load(PUBLIC_PATH)
    for field in (
        "locks",
        "claims",
        "custodian_reveal_rules",
        "replacement_policy",
    ):
        assert private[field] == v3[field]
        assert public[field] == v3[field]
    assert private["locks"]["test_construction_locked"] is True
    assert private["locks"]["distribution_locked"] is True
    assert private["locks"]["identity_publication_locked"] is True
    assert private["locks"]["evaluation_execution_locked"] is True
    assert private["locks"]["unlock_authorized"] is False
    assert not any(private["claims"].values())


def test_full_governance_split_lock_covers_every_public_field() -> None:
    tool = load_tool()
    public = load(PUBLIC_PATH)
    assert set(public["governance"]) == set(tool.GOVERNANCE_FIELDS)
    assert public["split_lock"]["covered_top_level_fields"] == list(
        tool.SPLIT_LOCK_COVERED_FIELDS
    )
    assert set(public) - {"split_lock"} == set(
        tool.SPLIT_LOCK_COVERED_FIELDS
    )
    assert public["split_lock"]["split_lock_sha256"] == (
        tool.compute_split_lock_hash(public)
    )
    for mutation in (
        ("locks", "distribution_locked", False),
        ("claims", "release_authorized", True),
        ("decision", "decision", "MUTATED"),
        ("historical_v3", "final_marker", "MUTATED"),
    ):
        changed = copy.deepcopy(public)
        changed[mutation[0]][mutation[1]] = mutation[2]
        assert tool.compute_split_lock_hash(changed) != public[
            "split_lock"
        ]["split_lock_sha256"]


def test_historical_v3_is_still_repair_and_bound_sources_are_unchanged() -> None:
    tool = load_tool()
    v3_private = load(V3_PRIVATE_PATH)
    v3_public = load(V3_PUBLIC_PATH)
    private = load(PRIVATE_PATH)
    public = load(PUBLIC_PATH)
    assert v3_private["final_marker"] == tool.V3_REPAIR
    assert v3_public["final_marker"] == tool.V3_REPAIR
    assert private["historical_v3"]["final_marker"] == tool.V3_REPAIR
    assert public["historical_v3"]["final_marker"] == tool.V3_REPAIR
    assert sha256_path(V3_PRIVATE_PATH) == (
        tool.EXPECTED_INPUT_HASHES[tool.V3_PRIVATE_REL.as_posix()]
    )
    assert sha256_path(MANIFEST_PATH) == (
        tool.EXPECTED_INPUT_HASHES[tool.MANIFEST_REL.as_posix()]
    )


def test_exact_permissions_and_committed_generation() -> None:
    tool = load_tool()
    assert PRIVATE_PATH.stat().st_mode & 0o777 == 0o600
    assert PUBLIC_PATH.stat().st_mode & 0o777 == 0o644
    assert REVIEW_PATH.stat().st_mode & 0o777 == 0o644
    assert PRIVATE_PATH.parent.stat().st_mode & 0o777 == 0o700
    run = subprocess.run(
        [sys.executable, str(TOOL_PATH), "--root", str(ROOT), "--check"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    assert run.stdout.strip() == tool.FINAL_READY


def test_committed_artifacts_validate_and_match_fresh_build() -> None:
    tool = load_tool()
    private = load(PRIVATE_PATH)
    public = load(PUBLIC_PATH)
    tool.validate_artifacts(ROOT, private=private, public=public)
    fresh_private, fresh_public = tool.build_artifacts(ROOT)
    assert json.dumps(
        fresh_private, indent=2, sort_keys=True
    ) + "\n" == PRIVATE_PATH.read_text(encoding="utf-8")
    assert json.dumps(
        fresh_public, indent=2, sort_keys=True
    ) + "\n" == PUBLIC_PATH.read_text(encoding="utf-8")
    assert tool.render_markdown(fresh_public) == REVIEW_PATH.read_text(
        encoding="utf-8"
    )
