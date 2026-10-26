from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/untouched_v3_1_technical_preflight_wave1.py"
PRIVATE_LEDGER = (
    ROOT / "data/restricted/untouched_test_group_ledger_v3_1_private.json"
)
PUBLIC_LEDGER = (
    ROOT
    / "data/rehearsal_plan/"
    "untouched_test_group_ledger_v3_1_public_commitment.json"
)
PRIVATE_REPORT = (
    ROOT
    / "data/restricted/"
    "untouched_v3_1_technical_preflight_wave1_private.json"
)
PUBLIC_REPORT = (
    ROOT
    / "data/rehearsal_plan/"
    "untouched_v3_1_technical_preflight_wave1_public.json"
)
REVIEW = (
    ROOT / "docs/review/untouched_v3_1_technical_preflight_wave1.md"
)


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "untouched_v3_1_technical_preflight_wave1", TOOL_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_minimum_commitment_selection_is_exact_and_deterministic() -> None:
    tool = load_tool()
    public = load(PUBLIC_LEDGER)
    rows = public["group_commitments"]
    expected = {
        lineage: min(
            row["v3_1_group_commitment_sha256"]
            for row in rows
            if row["dataset_lineage"] == lineage
        )
        for lineage in tool.LINEAGES
    }
    assert tool.select_public_minima(rows) == expected
    assert tool.select_public_minima(list(reversed(rows))) == expected
    selected = tool.select_groups()
    assert {
        item.dataset_lineage: item.commitment_id for item in selected
    } == expected
    assert len(selected) == len(tool.LINEAGES) == 3


def test_private_identity_mutations_cannot_change_selection() -> None:
    tool = load_tool()
    public = load(PUBLIC_LEDGER)
    private = load(PRIVATE_LEDGER)
    expected = tool.select_public_minima(public["group_commitments"])
    changed = copy.deepcopy(private)
    for index, row in enumerate(changed["selected_groups"]):
        evidence = row["identity_and_evidence"]
        evidence["exact_object_or_session_id"] = f"private-mutation-{index}"
        evidence["closure_root"] = f"private-root-{index}"
    assert tool.select_public_minima(public["group_commitments"]) == expected
    assert (
        set(tool.select_public_minima(public["group_commitments"]))
        == set(tool.LINEAGES)
    )


def test_plan_build_is_byte_deterministic_with_fixed_timestamp() -> None:
    tool = load_tool()
    selected = tool.select_groups()
    local = tool.local_rights_and_routes(selected)
    first_private, first_public = tool.build_reports(
        mode="plan-only",
        selected_groups=selected,
        local=local,
        live=None,
        generated_at="2026-10-15T00:00:00Z",
    )
    second_private, second_public = tool.build_reports(
        mode="plan-only",
        selected_groups=selected,
        local=local,
        live=None,
        generated_at="2026-10-15T00:00:00Z",
    )
    assert tool.canonical_bytes(first_private) == tool.canonical_bytes(
        second_private
    )
    assert tool.canonical_bytes(first_public) == tool.canonical_bytes(
        second_public
    )


def test_public_and_review_contain_no_private_identity_or_exact_path() -> None:
    tool = load_tool()
    private = load(PRIVATE_REPORT)
    public = load(PUBLIC_REPORT)
    review_text = REVIEW.read_text(encoding="utf-8")
    tool.validate_public_non_disclosure(
        public,
        private_groups=private["groups"],
        review_text=review_text,
    )
    combined = PUBLIC_REPORT.read_text(encoding="utf-8") + review_text
    for identity in tool._private_identity_strings(private["groups"]):
        assert identity not in combined
    for forbidden in tool.FORBIDDEN_PUBLIC_TEXT:
        assert forbidden not in combined
    public_keys = tool._walk_keys(public)
    assert not (public_keys & tool.FORBIDDEN_PUBLIC_KEYS)


def test_public_surface_is_commitment_lineage_and_technical_status_only() -> None:
    tool = load_tool()
    public = load(PUBLIC_REPORT)
    assert len(public["groups"]) == 3
    for group in public["groups"]:
        assert set(group) == {
            "commitment_id",
            "dataset_lineage",
            "decision",
            "technical_status",
            "exposure",
        }
        assert group["dataset_lineage"] in tool.LINEAGES
        assert group["decision"] in tool.DECISIONS
        assert group["exposure"] == "METADATA_ACCESS_ONLY"
        assert set(group["technical_status"]) == {
            "head_or_exact_identity",
            "range_access",
            "duration_metadata",
            "video_stream",
            "audio_stream",
            "native_sync",
        }
        assert all(
            isinstance(value, bool)
            for value in group["technical_status"].values()
        )


def test_byte_accounting_is_bounded_and_media_payload_is_not_persisted() -> None:
    tool = load_tool()
    private = load(PRIVATE_REPORT)
    public = load(PUBLIC_REPORT)
    for report in (private, public):
        accounting = report["byte_accounting"]
        assert accounting["maximum_aggregate_response_payload_bytes"] == (
            16 * 1024 * 1024
        )
        assert accounting["maximum_response_payload_bytes"] == (
            2 * 1024 * 1024
        )
        assert (
            accounting["response_payload_bytes_read"]
            <= accounting["maximum_aggregate_response_payload_bytes"]
        )
        assert (
            accounting["maximum_observed_response_payload_bytes"]
            <= accounting["maximum_response_payload_bytes"]
        )
        assert accounting["response_payload_bytes_persisted"] == 0
        assert accounting["media_probe_bytes_deleted_or_released"] is True
    assert private["scope"]["full_media_downloads"] == 0
    assert private["scope"]["media_payload_bytes_persisted"] == 0


def test_over_budget_report_fails_closed() -> None:
    tool = load_tool()
    selected = tool.select_groups()
    local = tool.local_rights_and_routes(selected)
    live = {
        "byte_accounting": {
            "response_payload_bytes_read": tool.MAX_AGGREGATE_BYTES + 1,
            "maximum_observed_response_payload_bytes": 1,
            "response_payload_bytes_persisted": 0,
            "media_probe_bytes_deleted_or_released": True,
        }
    }
    with pytest.raises(tool.PreflightError, match="BYTE_ACCOUNTING"):
        tool.build_reports(
            mode="live",
            selected_groups=selected,
            local=local,
            live=live,
            generated_at="2026-10-15T00:00:00Z",
        )


def test_roster_is_locked_and_no_replacement_is_executed() -> None:
    private = load(PRIVATE_REPORT)
    public = load(PUBLIC_REPORT)
    for report in (private, public):
        assert report["locks"] == {
            "roster_remained_locked": True,
            "replacement_executed": False,
            "test_construction_remained_locked": True,
            "distribution_remained_locked": True,
        }
        assert report["selection"]["selected_group_count"] == 3
        assert report["selection"]["lineage_count"] == 3
        assert report["selection"]["identity_fields_used_for_selection"] is False


def test_semantic_and_media_content_boundaries_are_explicit() -> None:
    private = load(PRIVATE_REPORT)
    public = load(PUBLIC_REPORT)
    for report in (private, public):
        scope = report["scope"]
        assert scope["technical_only"] is True
        assert scope["semantic_annotations_opened"] is False
        assert scope["labels_opened"] is False
        assert scope["task_titles_or_descriptions_opened"] is False
        assert scope["transcripts_or_captions_opened"] is False
        assert scope["candidate_yield_estimated"] is False
        assert scope["exposure_classification"] == "METADATA_ACCESS_ONLY"
    for group in private["groups"]:
        assert group["exposure"] == {
            "classification": "METADATA_ACCESS_ONLY",
            "semantic_content_accessed": False,
            "media_content_inspected": False,
            "identity_publication": False,
        }


def test_holoassist_uses_timing_evidence_and_no_unpinned_video_probe() -> None:
    private = load(PRIVATE_REPORT)
    group = next(
        item for item in private["groups"]
        if item["dataset_lineage"] == "HOLOASSIST"
    )
    evidence = group["private_identity_and_exact_evidence"]
    assert evidence["timing_closed"] is True
    assert evidence["variants"]
    assert all(item["timing_bytes"] == 38 for item in evidence["variants"])
    assert group["technical_status"]["duration_metadata"] is True
    assert group["technical_status"]["range_access"] is False
    assert group["bounded_container_probe"] is None


def test_private_mode_and_public_modes() -> None:
    assert os.stat(PRIVATE_REPORT).st_mode & 0o777 == 0o600
    assert os.stat(PUBLIC_REPORT).st_mode & 0o777 == 0o644
    assert os.stat(REVIEW).st_mode & 0o777 == 0o644


def test_final_marker_is_consistent_with_group_decisions() -> None:
    tool = load_tool()
    private = load(PRIVATE_REPORT)
    public = load(PUBLIC_REPORT)
    expected = (
        tool.READY
        if all(group["decision"] == "TECH_READY" for group in public["groups"])
        else tool.REPAIR
    )
    assert private["final_marker"] == expected
    assert public["final_marker"] == expected
    assert REVIEW.read_text(encoding="utf-8").rstrip().endswith(
        f"**{expected}**"
    )
