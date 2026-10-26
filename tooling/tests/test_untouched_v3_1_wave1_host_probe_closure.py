from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/untouched_v3_1_wave1_host_probe_closure.py"
PRIVATE_REPORT = (
    ROOT
    / "data/restricted/"
    "untouched_v3_1_wave1_host_probe_closure_private.json"
)
PUBLIC_REPORT = (
    ROOT
    / "data/rehearsal_plan/"
    "untouched_v3_1_wave1_host_probe_closure_public.json"
)
REVIEW = (
    ROOT / "docs/review/untouched_v3_1_wave1_host_probe_closure.md"
)


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "untouched_v3_1_wave1_host_probe_closure", TOOL_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_header_and_content_range_parsers_are_strict() -> None:
    tool = load_tool()
    assert tool.parse_content_range("bytes 0-1023/11695708821") == (
        0,
        1023,
        11_695_708_821,
    )
    with pytest.raises(tool.ClosureError):
        tool.parse_content_range("bytes */11695708821")
    with pytest.raises(tool.ClosureError):
        tool.parse_content_range("bytes 0-100/100")


def test_selected_groups_are_public_minimum_commitments() -> None:
    tool = load_tool()
    selected = tool.selected_groups()
    public = load(tool.PUBLIC_LEDGER)
    for lineage in tool.LINEAGES:
        expected = min(
            row[tool.SELECTION_FIELD]
            for row in public["group_commitments"]
            if row["dataset_lineage"] == lineage
        )
        assert selected[lineage]["commitment_id"] == expected


def test_assembly_exact_route_is_gated_on_both_proxies() -> None:
    private = load(PRIVATE_REPORT)
    group = next(
        item
        for item in private["groups"]
        if item["dataset_lineage"] == "ASSEMBLY101"
    )
    assert group["status"]["both_proxy_probes_completed"] is True
    assert group["status"]["gated_401_on_both_proxies"] is True
    assert group["status"]["gated_repo_error_on_both_proxies"] is True
    assert group["status"]["anonymous_media_access"] is False
    assert {
        item["status"] for item in group["proxy_results"].values()
    } == {401}
    assert {
        item["gate_code"] for item in group["proxy_results"].values()
    } == {"GatedRepo"}


def test_epic_exact_route_has_identical_206_total_on_both_proxies() -> None:
    private = load(PRIVATE_REPORT)
    group = next(
        item
        for item in private["groups"]
        if item["dataset_lineage"] == "EPIC"
    )
    assert group["exact_total_bytes"] == 11_695_708_821
    assert group["etag"] == '"5a170ea9-2b91e5a95"'
    assert group["status"]["range_206_on_both_proxies"] is True
    assert group["status"]["exact_total_bytes_closed"] is True
    for result in group["proxy_results"].values():
        assert result["status"] == 206
        assert result["content_range"] == {
            "start": 0,
            "end": 1023,
            "total_bytes": 11_695_708_821,
        }
        assert result["content_length"] == 1024


def test_holoassist_timing_and_archive_facts_close_without_object_upgrade() -> None:
    tool = load_tool()
    private = load(PRIVATE_REPORT)
    group = next(
        item
        for item in private["groups"]
        if item["dataset_lineage"] == "HOLOASSIST"
    )
    status = group["status"]
    assert status["timing_closed"] is True
    assert status["hf_repository_public"] is True
    assert status["hf_repository_ungated"] is True
    assert status["archive_objects_public"] is True
    assert status["archive_part_sizes_closed"] is True
    assert status["archive_part_etags_closed"] is True
    assert status["selected_individual_video_exact_object_resolved"] is False
    assert status["selected_individual_audio_exact_object_resolved"] is False
    assert {
        item["object_name"]: {
            "size_bytes": item["size_bytes"],
            "etag": item["etag"],
        }
        for item in group["archive_parts"]
    } == tool.HOLO_ARCHIVE_PARTS
    assert all(
        item["timing_bytes"] == 38
        for item in group["identity"]["variants"]
    )


def test_zero_retained_media_body_and_metadata_exposure() -> None:
    for report_path in (PRIVATE_REPORT, PUBLIC_REPORT):
        report = load(report_path)
        scope = report["scope"]
        accounting = report["probe_payload_accounting"]
        assert scope["network_used_by_closure"] is False
        assert scope["media_content_inspected"] is False
        assert scope["retained_media_body_files"] == 0
        assert scope["retained_media_body_bytes"] == 0
        assert scope["exposure_classification"] == "METADATA_ACCESS_ONLY"
        assert (
            accounting["historical_response_body_bytes_reported_by_summary"]
            == 2308
        )
        assert accounting["historical_media_range_body_bytes"] == 2048
        assert accounting["historical_gate_error_body_bytes"] == 260
        assert accounting["retained_media_body_files_in_closure_evidence"] == 0
        assert accounting["retained_media_body_bytes_in_closure_evidence"] == 0


def test_public_surface_is_commitments_and_status_booleans_only() -> None:
    public = load(PUBLIC_REPORT)
    assert len(public["groups"]) == 3
    for group in public["groups"]:
        assert set(group) == {
            "dataset_lineage",
            "commitment_id",
            "status",
            "exposure",
        }
        assert group["dataset_lineage"] in {"ASSEMBLY101", "EPIC", "HOLOASSIST"}
        assert group["exposure"] == "METADATA_ACCESS_ONLY"
        assert all(isinstance(value, bool) for value in group["status"].values())


def test_public_and_review_do_not_reveal_private_identities() -> None:
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
    assert not (tool._walk_keys(public) & tool.FORBIDDEN_PUBLIC_KEYS)


def test_privacy_validator_rejects_identity_mutation() -> None:
    tool = load_tool()
    private = load(PRIVATE_REPORT)
    public = load(PUBLIC_REPORT)
    mutated = copy.deepcopy(public)
    mutated["groups"][0]["session_id"] = private["groups"][0]["identity"][
        "exact_object_or_session_id"
    ]
    with pytest.raises(tool.ClosureError, match="PUBLIC_PRIVATE_KEY_LEAK"):
        tool.validate_public_non_disclosure(
            mutated,
            private_groups=private["groups"],
        )


def test_build_and_committed_artifacts_are_byte_deterministic() -> None:
    tool = load_tool()
    private_one, public_one = tool.build_reports()
    private_two, public_two = tool.build_reports()
    review_one = tool.render_review(public_one)
    review_two = tool.render_review(public_two)

    assert tool.canonical_bytes(private_one) == tool.canonical_bytes(private_two)
    assert tool.canonical_bytes(public_one) == tool.canonical_bytes(public_two)
    assert review_one == review_two
    assert PRIVATE_REPORT.read_bytes() == tool.canonical_bytes(private_one)
    assert PUBLIC_REPORT.read_bytes() == tool.canonical_bytes(public_one)
    assert REVIEW.read_text(encoding="utf-8") == review_one


def test_modes_markers_and_check_cli(capsys: pytest.CaptureFixture[str]) -> None:
    tool = load_tool()
    private = load(PRIVATE_REPORT)
    public = load(PUBLIC_REPORT)
    assert private["final_marker"] == tool.READY
    assert public["final_marker"] == tool.READY
    assert REVIEW.read_text(encoding="utf-8").rstrip().endswith(
        f"**{tool.READY}**"
    )
    assert os.stat(PRIVATE_REPORT).st_mode & 0o777 == 0o600
    assert os.stat(PUBLIC_REPORT).st_mode & 0o777 == 0o644
    assert os.stat(REVIEW).st_mode & 0o777 == 0o644
    assert tool.main(["--check"]) == 0
    assert capsys.readouterr().out.strip() == tool.READY
