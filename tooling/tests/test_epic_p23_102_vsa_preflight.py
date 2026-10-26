from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/epic_p23_102_vsa_preflight.py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "epic_p23_102_vsa_preflight", TOOL_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_local_exact_route_rights_and_manifest_are_closed() -> None:
    tool = load_tool()
    local = tool.validate_local_inputs()

    assert local["selected_manifest"]["video_id"] == "P23_102"
    assert local["selected_manifest"]["duration_seconds"] == "3569.52"
    assert local["selected_manifest"]["md5"] == tool.EXPECTED_MD5
    assert local["candidate"].url == tool.ASSET_URL
    assert local["candidate"].size_bytes == 10_814_161_307
    assert local["epic"]["license"]["spdx"] == "CC-BY-NC-4.0"
    assert (
        local["epic"]["access"][
            "registration_required_for_data_bris_route"
        ]
        is False
    )


def test_p23_has_two_or_more_long_metadata_only_family_leads() -> None:
    tool = load_tool()
    local = tool.validate_local_inputs()
    videos = local["p23_long_videos"]

    assert len(videos) == 5
    assert "P23_102" in {item["video_id"] for item in videos}
    assert all(
        tool.LONG_MIN_SECONDS
        <= item["duration_seconds"]
        <= tool.LONG_MAX_SECONDS
        for item in videos
    )


def test_retained_head_report_is_repair_not_ready() -> None:
    tool = load_tool()
    report = tool.build_report(
        mode="retained-head",
        local=tool.validate_local_inputs(),
        retained_head=tool.retained_head_evidence(),
    )

    assert report["final_marker"] == tool.REPAIR
    assert report["authoritative_asset"]["expected_size_bytes_from_retained_head"] == (
        10_814_161_307
    )
    assert (
        report["access_evidence"]["retained_or_live_head"]["http_status"] == 200
    )
    assert report["access_evidence"]["bounded_range_access_succeeded"] is False
    assert (
        report["duration_and_streams"]["native_audio_status"]
        == "DATASET_LEVEL_ONLY_EXACT_FILE_UNRESOLVED"
    )


def test_ready_requires_range_and_exact_native_synchronized_audio() -> None:
    tool = load_tool()
    marker, blockers = tool.classify(
        rights_and_gate=True,
        exact_asset=True,
        long_duration=True,
        range_access=True,
        native_audio=True,
        synchronized_timeline=True,
    )
    assert marker == tool.READY
    assert blockers == []

    marker, blockers = tool.classify(
        rights_and_gate=True,
        exact_asset=True,
        long_duration=True,
        range_access=False,
        native_audio=False,
        synchronized_timeline=False,
    )
    assert marker == tool.REPAIR
    assert any("byte-range" in item for item in blockers)
    assert any("native audio track" in item for item in blockers)


def test_parsed_exact_file_without_audio_is_no_go() -> None:
    tool = load_tool()
    marker, _ = tool.classify(
        rights_and_gate=True,
        exact_asset=True,
        long_duration=True,
        range_access=True,
        native_audio=False,
        synchronized_timeline=False,
        terminal_no_audio=True,
    )
    assert marker == tool.NO_GO


def test_report_makes_no_forbidden_semantic_or_human_claims() -> None:
    tool = load_tool()
    report = tool.build_report(
        mode="retained-head",
        local=tool.validate_local_inputs(),
        retained_head=tool.retained_head_evidence(),
    )

    assert report["scope"]["semantic_annotation_files_opened"] == 0
    assert report["scope"]["semantic_labels_used"] is False
    assert report["scope"]["human_review_performed"] is False
    assert report["scope"]["v_plus_s_plus_a_claimed"] is False
    assert report["scope"]["ses_or_h_tier_claimed"] is False
    assert report["scope"]["gate_a_claimed"] is False
    assert report["routing_only_boundary"]["semantic_credit"] is False
    assert report["timestamp_annotations"]["annotation_bodies_opened"] is False
    assert (
        report["two_candidate_family_feasibility"][
            "scientific_defensibility_or_independence_claimed"
        ]
        is False
    )


def test_cli_retained_head_writes_bounded_report_without_network(
    tmp_path: Path,
) -> None:
    output = tmp_path / "report.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(TOOL_PATH),
            "--retained-head",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout.strip() == "EPIC_P23_102_VSA_PREFLIGHT_REPAIR"
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["access_evidence"]["bounded_probe_bytes_read"] == 0
    assert report["access_evidence"]["bounded_probe_bytes_persisted"] == 0
    assert report["scope"]["full_media_downloads"] == 0
