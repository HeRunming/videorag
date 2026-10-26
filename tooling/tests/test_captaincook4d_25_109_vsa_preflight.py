from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/captaincook4d_25_109_vsa_preflight.py"


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "captaincook4d_25_109_vsa_preflight", TOOL_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_local_inputs_pin_exact_route_and_two_assets() -> None:
    tool = load_tool()
    local = tool.validate_local_inputs()

    assert local["record"]["recording_id"] == "25_109"
    assert local["record"]["source_group_id"] == "cc4d_p05_e07"
    assert local["record"]["official_stream_urls"]["gopro_360p"] == tool.GOPRO_URL
    assert (
        local["record"]["official_stream_urls"]["hololens_sync_pv_video"]
        == tool.HOLOLENS_URL
    )
    assert local["group"]["eligible_recording_ids"] == [
        "20_17",
        "23_6",
        "25_109",
        "26_19",
    ]


def test_report_fails_closed_as_repair() -> None:
    tool = load_tool()
    report = tool.build_report(local=tool.validate_local_inputs())

    assert report["final_marker"] == tool.REPAIR
    assert report["rights_and_access"]["go_gate_satisfied"] is False
    assert report["exact_official_assets"]["go_gate_satisfied"] is False
    assert report["duration"]["long_duration_evidenced"] is True
    assert report["native_synchronized_audio"]["go_gate_satisfied"] is False
    assert len(report["blockers"]) == 3


def test_report_has_no_semantic_or_human_claims() -> None:
    tool = load_tool()
    report = tool.build_report(local=tool.validate_local_inputs())

    assert report["scope"]["network_requests"] == 0
    assert report["scope"]["full_media_downloads"] == 0
    assert report["scope"]["semantic_annotation_files_opened"] == 0
    assert report["scope"]["human_review_performed"] is False
    assert report["scope"]["v_plus_s_plus_a_claimed"] is False
    assert report["scope"]["ses_claimed"] is False
    assert report["scope"]["h_tier_claimed"] is False
    assert report["scope"]["gate_a_claimed"] is False
    assert report["candidate_family_feasibility"]["semantic_candidate_claimed"] is False
    assert report["candidate_family_feasibility"]["vsa_credit"] is False
    assert (
        report["timestamp_annotations"]["contents_opened_or_used_for_selection"]
        is False
    )


def test_ready_requires_all_four_go_gates() -> None:
    tool = load_tool()
    marker, blockers = tool.classify(
        rights_access=True,
        exact_asset=True,
        duration=True,
        native_audio=True,
    )
    assert marker == tool.READY
    assert blockers == []

    marker, blockers = tool.classify(
        rights_access=True,
        exact_asset=True,
        duration=True,
        native_audio=False,
    )
    assert marker == tool.REPAIR
    assert any("native synchronized audio" in item for item in blockers)


def test_hard_identity_failure_is_no_go() -> None:
    tool = load_tool()
    marker, blockers = tool.classify(
        rights_access=True,
        exact_asset=True,
        duration=True,
        native_audio=True,
        hard_identity_failure=True,
    )
    assert marker == tool.NO_GO
    assert len(blockers) == 1


def test_cli_writes_offline_report(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    completed = subprocess.run(
        [sys.executable, str(TOOL_PATH), "--output", str(output)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout.strip() == (
        "CAPTAINCOOK4D_25_109_VSA_PREFLIGHT_REPAIR"
    )
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["scope"]["network_requests"] == 0
    assert report["scope"]["media_bytes_read"] == 0
    assert report["exact_official_assets"]["gopro_360p"]["expected_bytes"] is None


def test_live_mode_is_rejected_without_network(tmp_path: Path) -> None:
    tool = load_tool()
    with pytest.raises(tool.PreflightError, match="LIVE_NETWORK_DISABLED"):
        old_argv = sys.argv
        try:
            sys.argv = [
                str(TOOL_PATH),
                "--live",
                "--output",
                str(tmp_path / "unused.json"),
            ]
            tool.main()
        finally:
            sys.argv = old_argv
