from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/source_exposure_alias_manifest_v1.py"
MANIFEST_PATH = (
    ROOT / "data/rehearsal_plan/source_exposure_alias_manifest_v1.json"
)
REVIEW_PATH = ROOT / "docs/review/source_exposure_alias_manifest_v1.md"


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "source_exposure_alias_manifest_v1", TOOL_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def component_containing(manifest: dict, alias: str) -> dict:
    for component in manifest["alias_graph"]["components"]:
        if alias in component["aliases"]:
            return component
    raise AssertionError(f"alias absent: {alias}")


def touched_group(manifest: dict, closure_root: str) -> dict:
    for row in manifest["current_touched_groups"]:
        if row["closure_root"] == closure_root:
            return row
    raise AssertionError(f"touched group absent: {closure_root}")


def test_cand_042_city_under_ice_and_naid_close_together() -> None:
    component = component_containing(load_manifest(), "cand-042")

    assert component["closure_root"] == "EC-NARA-CITY-UNDER-ICE"
    assert {
        "cand-042",
        "EC-NARA-CITY-UNDER-ICE",
        "NAID:2569752",
    } <= set(component["aliases"])
    evidence_paths = {
        evidence["path"]
        for edge in component["supporting_edges"]
        for evidence in edge["evidence"]
    }
    assert "data/candidates/source_candidates.csv" in evidence_paths
    assert "data/rehearsal_plan/nara_event_source_dossiers_v1.json" in evidence_paths


def test_p23_participant_closure_includes_derivatives_and_is_contaminated() -> None:
    manifest = load_manifest()
    component = component_containing(manifest, "P23_102")

    assert component["closure_root"] == "EPIC:P23"
    assert {"EPIC:P23", "P23", "P23_102", "P23_101"} <= set(
        component["aliases"]
    )
    row = touched_group(manifest, "EPIC:P23")
    assert {
        "media_acquired",
        "media_indexed",
        "learned_model_ranked",
        "candidate_mined",
    } <= set(row["event_types"])
    assert row["eligibility"] == "INELIGIBLE_CONTAMINATED"


def test_captaincook_recordings_close_by_person_across_environments() -> None:
    manifest = load_manifest()
    person_one = component_containing(manifest, "16_20")
    person_two = component_containing(manifest, "15_29")
    person_three = component_containing(manifest, "26_22")

    assert person_one["closure_root"] == "CC4D:P01"
    assert {"16_20", "cc4d_p01_e08", "CC4D:P01"} <= set(
        person_one["aliases"]
    )
    assert person_two["closure_root"] == "CC4D:P02"
    assert {"15_29", "cc4d_p02_e02", "CC4D:P02"} <= set(
        person_two["aliases"]
    )
    assert person_three["closure_root"] == "CC4D:P03"
    assert {"26_22", "cc4d_p03_e03", "CC4D:P03"} <= set(
        person_three["aliases"]
    )


def test_assembly_noaa_nasa_nara_and_public_lecture_alias_families_exist() -> None:
    manifest = load_manifest()

    assembly = component_containing(
        manifest,
        "nusar-2021_action_both_9056-b08a_9056_user_id_2021-02-22_141934",
    )
    assert assembly["closure_root"] == "ASSEMBLY101:9056"
    assert "assembly101_p9056" in assembly["aliases"]

    noaa = component_containing(manifest, "cand-048")
    assert noaa["closure_root"] == "EC-NOAA-SHIPWRECKS"
    assert "NOAA:cand-048" in noaa["aliases"]

    nasa = component_containing(manifest, "NASA:CONTENT:13675")
    assert nasa["closure_root"] == "EC-NASA-TO-THE-RESCUE"
    assert {"NASA:POST:4460", "NASA:ASSET:15687"} <= set(nasa["aliases"])

    nara = component_containing(manifest, "NAID:2569752")
    assert nara["closure_root"] == "EC-NARA-CITY-UNDER-ICE"

    lecture = component_containing(manifest, "repl-mit-res12-003-lecture-1")
    assert lecture["closure_root"] == "SG-MIT-RES12-003-L01"


def test_eligibility_policy_is_fail_closed_for_content_and_semantics() -> None:
    tool = load_tool()
    policy = load_manifest()["untouched_eligibility_policy"]

    assert set(policy["conditional_event_types"]) == tool.CONDITIONAL_EVENTS
    assert set(policy["contaminating_event_types"]) == tool.CONTAMINATING_EVENTS
    assert {
        "metadata_catalog_only",
        "rights/access_preflight",
        "failed_zero_byte_probe",
    } == set(policy["conditional_event_types"])
    for event in (
        "media_acquired",
        "media_indexed",
        "learned_model_ranked",
        "candidate_mined",
        "semantic_prompt_exposed",
        "human_prescreened",
        "annotation_opened",
    ):
        assert event in policy["contaminating_event_types"]


def test_failed_zero_byte_probe_stays_conditional_without_other_exposure() -> None:
    tool = load_tool()

    assert tool.CONDITIONAL_EVENTS == {
        "metadata_catalog_only",
        "rights/access_preflight",
        "failed_zero_byte_probe",
    }
    assert not (tool.CONDITIONAL_EVENTS & tool.CONTAMINATING_EVENTS)


def test_scan_is_bounded_and_excludes_media_models_and_annotation_bodies() -> None:
    tool = load_tool()
    manifest = load_manifest()
    scan = manifest["scan"]

    assert scan["max_file_bytes"] == tool.MAX_FILE_BYTES
    assert set(scan["allowlisted_extensions"]) == tool.ALLOWLISTED_EXTENSIONS
    assert {"media", "models", "annotation", "annotations"} <= set(
        scan["excluded_directory_names"]
    )
    for event in manifest["exposure_events"]:
        parts = set(Path(event["evidence"]["path"]).parts)
        assert not parts & {"media", "models", "annotation", "annotations"}


def test_replacements_are_exact_local_metadata_and_never_touched() -> None:
    manifest = load_manifest()
    touched = {
        row["closure_root"] for row in manifest["current_touched_groups"]
    }
    replacements = manifest["candidate_replacement_discovery"]

    assert replacements
    assert {"EPIC:P01", "CC4D:P04", "ASSEMBLY101:9056"} <= {
        row["closure_root"] for row in replacements
    }
    for row in replacements:
        assert row["closure_root"] not in touched
        assert row["exact_locally_enumerated_id"]
        assert row["enumeration_basis"].startswith("EXACT_")
        assert row["evidence"]["path"]
        assert row["evidence"]["locator"]
        assert len(row["evidence"]["sha256"]) == 64


def test_contamination_is_evidence_derived_not_circular_empty_default() -> None:
    tool = load_tool()
    manifest = load_manifest()

    assert manifest["current_touched_groups"]
    assert manifest["exposure_events"]
    assert any(
        event["event_type"] == "media_acquired"
        and event["closure_root"] == "EPIC:P23"
        and event["evidence"]["path"].endswith(
            "epic_p23_102_exact_manifest.json"
        )
        for event in manifest["exposure_events"]
    )

    changed = copy.deepcopy(manifest)
    changed["current_touched_groups"] = []
    with pytest.raises(
        tool.ManifestError,
        match="EMPTY_TOUCHED_GROUPS_CIRCULAR_DEFAULT_FORBIDDEN",
    ):
        tool.validate_manifest(changed)


def test_evidence_has_path_locator_and_hash() -> None:
    manifest = load_manifest()

    for component in manifest["alias_graph"]["components"]:
        for edge in component["supporting_edges"]:
            assert len(edge["aliases"]) == 2
            for evidence in edge["evidence"]:
                assert evidence["path"]
                assert evidence["locator"]
                assert len(evidence["sha256"]) == 64
    for event in manifest["exposure_events"]:
        evidence = event["evidence"]
        assert evidence["path"]
        assert evidence["locator"]
        assert len(evidence["sha256"]) == 64


def test_committed_outputs_are_deterministic_and_current() -> None:
    tool = load_tool()
    manifest = tool.build_manifest(ROOT)

    assert MANIFEST_PATH.read_text(encoding="utf-8") == (
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    assert REVIEW_PATH.read_text(encoding="utf-8") == tool.render_markdown(
        manifest
    )
    assert manifest["final_marker"] == tool.FINAL_READY
