from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/nasa_moonbound_vsa_preflight.py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "nasa_moonbound_vsa_preflight", TOOL_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_local_identity_and_saved_playlist_are_reproducible() -> None:
    tool = load_tool()
    local = tool.validate_local_inputs()

    assert local["api"]["id"] == 6979
    assert local["api"]["meta"]["content-id"] == "15230"
    assert local["api"]["meta"]["video-url"].endswith("/17905.m3u8")
    assert local["playlist"]["segment_count"] == 183
    assert local["playlist"]["duration_seconds"] == 1646.0
    assert local["item"]["official_download_control"] is True


def test_plan_report_is_repair_with_precise_gates() -> None:
    tool = load_tool()
    report = tool.build_report(
        mode="plan-only", local=tool.validate_local_inputs()
    )

    assert report["final_marker"] == tool.REPAIR
    assert report["duration_and_resolution"]["api_runtime_seconds"] == 2202.0
    assert (
        report["duration_and_resolution"]["selected_playlist_duration_seconds"]
        == 1646.0
    )
    assert report["duration_and_resolution"]["difference_seconds"] == 556.0
    assert report["rights_and_download_authority"]["acquisition"] == "HOLD"
    assert (
        report["exact_media"]["head_and_range"]["status"]
        == "NOT_EVIDENCED_IN_SAVED_RUN"
    )
    assert report["native_audio"]["bounded_media_payload_evidence"] is False


def test_report_makes_no_semantic_or_necessity_claim() -> None:
    tool = load_tool()
    report = tool.build_report(
        mode="plan-only", local=tool.validate_local_inputs()
    )

    assert report["scope"]["human_review_performed"] is False
    assert report["scope"]["semantic_claims_made"] is False
    assert report["scope"]["v_plus_s_plus_a_necessity_claimed"] is False
    assert (
        report["routing_only_plausibility"]["semantic_credit"] is False
    )
    assert len(
        report["routing_only_plausibility"]["candidate_event_rich_leads"]
    ) >= 2


def test_ready_requires_rights_asset_audio_and_duration() -> None:
    tool = load_tool()

    marker, blockers = tool.classify(
        component_rights_exact=True,
        exact_asset_evidenced=True,
        audio_evidenced=True,
        duration_resolved=True,
    )
    assert marker == tool.READY
    assert blockers == []

    marker, blockers = tool.classify(
        component_rights_exact=False,
        exact_asset_evidenced=True,
        audio_evidenced=True,
        duration_resolved=True,
    )
    assert marker == tool.REPAIR
    assert any("component rights" in blocker for blocker in blockers)

    marker, _ = tool.classify(
        component_rights_exact=True,
        exact_asset_evidenced=False,
        audio_evidenced=True,
        duration_resolved=True,
    )
    assert marker == tool.NO_GO


def test_master_parser_finds_muxed_audio_and_captions() -> None:
    tool = load_tool()
    master = tool.parse_master(
        (tool.SNAPSHOT_ROOT / "master.body").read_text(encoding="utf-8")
    )

    assert len(master["variants"]) == 9
    assert any(item["audio_only"] for item in master["variants"])
    assert any(
        item["resolution"] == "1920x1080"
        and "mp4a" in item["codecs"]
        for item in master["variants"]
    )
    assert {item["instream_id"] for item in master["closed_captions"]} == {
        "CC1",
        "CC3",
        "SERVICE3",
        "SERVICE4",
    }


def _ts_packet(pid: int, payload: bytes, *, payload_start: bool = True) -> bytes:
    second = ((0x40 if payload_start else 0) | ((pid >> 8) & 0x1F))
    packet = bytes([0x47, second, pid & 0xFF, 0x10]) + payload
    return packet.ljust(188, b"\xff")


def test_bounded_ts_parser_can_evidence_video_and_audio_stream_types() -> None:
    tool = load_tool()
    pat = bytes(
        [
            0,
            0x00,
            0xB0,
            0x0D,
            0,
            1,
            0xC1,
            0,
            0,
            0,
            1,
            0xE1,
            0,
            0,
            0,
            0,
            0,
        ]
    )
    pmt = bytes(
        [
            0,
            0x02,
            0xB0,
            0x17,
            0,
            1,
            0xC1,
            0,
            0,
            0xE1,
            1,
            0xF0,
            0,
            0x1B,
            0xE1,
            1,
            0xF0,
            0,
            0x0F,
            0xE1,
            2,
            0xF0,
            0,
            0,
            0,
            0,
            0,
        ]
    )
    data = _ts_packet(0, pat) + _ts_packet(0x100, pmt)
    evidence = tool.parse_ts_stream_types(data + data)

    assert evidence["packet_alignment"] is True
    assert evidence["video_stream_advertised"] is True
    assert evidence["audio_stream_advertised"] is True
    assert evidence["stream_types"] == ["0x0f", "0x1b"]


def test_cli_plan_only_writes_report_without_network(tmp_path: Path) -> None:
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
    assert completed.stdout.strip() == tool_marker()
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["live_run"]["network_requests"] == 0
    assert report["scope"]["full_media_downloads"] == 0
    assert report["scope"]["media_bytes_persisted"] == 0


def tool_marker() -> str:
    return "NASA_MOONBOUND_VSA_PREFLIGHT_REPAIR"


def test_policy_validator_fails_closed() -> None:
    tool = load_tool()
    with pytest.raises(tool.PreflightError, match="RIGHTS_POLICY_TEXT_MISSING"):
        tool.validate_policy(b"<html>generic permission only</html>")
