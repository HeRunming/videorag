from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/assembly101_9051_vsa_preflight.py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "assembly101_9051_vsa_preflight", TOOL_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_local_plan_is_closed_and_matches_frozen_route() -> None:
    tool = load_tool()
    local = tool.validate_local_inputs()
    candidates = local["selected_candidates"]

    assert [item.candidate_id for item in candidates] == [
        "assembly101-9051-primary",
        "assembly101-9051-secondary",
    ]
    assert candidates[0].path.endswith(
        "9051-c08a_9051_user_id_2021-02-22_115717/C10095_rgb.mp4"
    )
    assert candidates[1].path.endswith(
        "9051-b03a_9051_user_id_2021-02-22_114140/C10095_rgb.mp4"
    )
    assert all(item.repo_id == tool.REPO_ID for item in candidates)
    assert all(item.revision == tool.REVISION for item in candidates)


def test_lfs_blob_ids_are_reproducible() -> None:
    tool = load_tool()

    assert tool.SESSION_SPECS[0].blob_id == (
        "aa7721141655638eb93c1ab3d3723a4efc8a23cb"
    )
    assert tool.SESSION_SPECS[1].blob_id == (
        "2d70a1b1a00f12b87f014a941de2e113736db330"
    )


def test_plan_report_is_repair_and_makes_no_forbidden_claims() -> None:
    tool = load_tool()
    local = tool.validate_local_inputs()
    report = tool.build_report(mode="plan-only", local=local)

    assert report["final_marker"] == tool.REPAIR
    assert report["scope"]["full_media_downloads"] == 0
    assert report["scope"]["semantic_annotation_files_opened"] == 0
    assert report["scope"]["human_review_performed"] is False
    assert report["scope"]["ses_or_h_tier_claimed"] is False
    assert report["scope"]["gate_a_claimed"] is False
    assert report["scope"]["v_plus_s_plus_a_claimed"] is False
    assert report["routing_only_plausibility"]["vsa_credit"] is False
    assert (
        report["timestamp_annotations"]["contents_opened_or_used_for_selection"]
        is False
    )


def test_ready_requires_access_long_duration_and_audio() -> None:
    tool = load_tool()
    good = {
        "candidate_id": "x",
        "identity_match": True,
        "duration_seconds": 1800.0,
        "audio_track_count": 1,
        "av_timeline_relation": "PLAUSIBLY_SYNCHRONIZED",
    }
    metadata = {"status": "SUCCEEDED"}
    stream = {"candidates": [dict(good), dict(good)]}

    marker, blockers = tool.classify("live", metadata, stream)
    assert marker == tool.READY
    assert blockers == []

    stream["candidates"][1]["audio_track_count"] = 0
    marker, blockers = tool.classify("live", metadata, stream)
    assert marker == tool.REPAIR
    assert any("audio track" in item for item in blockers)


def test_live_metadata_validator_rejects_identity_drift() -> None:
    tool = load_tool()
    metadata = {
        "status": "SUCCEEDED",
        "repo_id": tool.REPO_ID,
        "revision": tool.REVISION,
        "license": "cc-by-nc-4.0",
        "selected_files": [
            {
                "path": spec.path,
                "size_bytes": spec.size_bytes,
                "lfs_sha256": spec.sha256,
                "blob_id": spec.blob_id,
            }
            for spec in tool.SESSION_SPECS
        ],
    }
    tool.validate_live_metadata(metadata)
    metadata["selected_files"][0]["size_bytes"] += 1
    with pytest.raises(tool.PreflightError, match="IDENTITY_MISMATCH"):
        tool.validate_live_metadata(metadata)


def test_cli_plan_only_writes_bounded_report(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(TOOL_PATH),
            "--plan-only",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout.strip() == (
        "ASSEMBLY101_9051_VSA_PREFLIGHT_REPAIR"
    )
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["authenticated_access"]["bounded_probe_bytes_read"] == 0
    assert report["authenticated_access"]["bounded_probe_bytes_persisted"] == 0
