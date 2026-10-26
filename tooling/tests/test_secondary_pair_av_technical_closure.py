from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/secondary_pair_av_technical_closure.py"
REPORT_PATH = (
    ROOT / "data/rehearsal_plan/secondary_pair_av_technical_closure_v1.json"
)
MARKDOWN_PATH = (
    ROOT / "docs/review/secondary_pair_av_technical_closure_v1.md"
)


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "secondary_pair_av_technical_closure", TOOL_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_content_range_parser_is_strict() -> None:
    tool = load_tool()

    assert tool.parse_content_range("bytes 0-1023/201079756") == (
        0,
        1023,
        201079756,
    )
    with pytest.raises(tool.ClosureError):
        tool.parse_content_range("bytes */201079756")
    with pytest.raises(tool.ClosureError):
        tool.parse_content_range("bytes 0-100/100")


def test_authoritative_headers_validate_exact_totals_and_identity() -> None:
    tool = load_tool()
    evidence_root = Path("/tmp")

    epic = tool.summarize_range_header(
        evidence_root
        / "avtrace_p23_mp4meta_20261013/head.headers",
        expected_start=0,
        expected_end=4095,
        expected_total=tool.EPIC_TOTAL,
        expected_etag=tool.EPIC_ETAG,
    )
    captain = tool.summarize_range_header(
        evidence_root
        / "avtrace_cc25109_mp4meta_20261013/head.headers",
        expected_start=0,
        expected_end=4095,
        expected_total=tool.CAPTAIN_TOTAL,
        expected_filename=tool.CAPTAIN_FILENAME,
    )

    assert epic["final_status"] == 206
    assert epic["content_range"]["total"] == 10_814_161_307
    assert epic["etag"] == '"5ea771bb-28493019b"'
    assert captain["content_range"]["total"] == 201_079_756
    assert captain["content_disposition_filename"] == "25_109_360p.mp4"
    assert "utdallas.app.box.com" in captain["redirect_hosts"]
    assert "public.boxcloud.com" in captain["redirect_hosts"]


def test_build_report_closes_technical_facts_and_separates_authority() -> None:
    tool = load_tool()
    report = tool.build_report(Path("/tmp"))
    epic = report["assets"]["epic_p23_102"]
    captain = report["assets"]["captaincook4d_25_109"]

    assert report["final_marker"] == tool.FINAL_READY
    assert epic["container_validation"]["moov"] == {
        "absolute_offset": 10_809_773_840,
        "bytes": 4_387_467,
        "end_exclusive": 10_814_161_307,
        "ends_at_object_eof": True,
        "fully_inside_tail_window": True,
    }
    assert epic["container_validation"]["video"]["codec_fourcc"] == "hvc1"
    assert epic["container_validation"]["audio"]["codec_fourcc"] == "mp4a"
    assert epic["container_validation"]["av_duration_delta_seconds"] == 0.016
    assert epic["decision"]["exact_acquisition_technically_authorized_now"]

    assert captain["container_validation"]["moov"] == {
        "absolute_offset": 198_755_331,
        "bytes": 2_324_425,
        "end_exclusive": 201_079_756,
        "ends_at_object_eof": True,
        "fully_inside_tail_window": True,
    }
    assert captain["container_validation"]["video"][
        "codec_fourcc"
    ] == "avc1"
    assert captain["container_validation"]["audio"]["channels"] == 2
    assert captain["container_validation"][
        "av_duration_delta_seconds"
    ] == pytest.approx(0.024833)
    assert captain["decision"]["technical_readiness_for_exact_acquisition"]
    assert not captain["decision"][
        "governance_authority_for_exact_acquisition_closed"
    ]
    assert not captain["decision"][
        "exact_acquisition_technically_authorized_now"
    ]


def test_deleted_payload_and_forbidden_claim_boundaries() -> None:
    tool = load_tool()
    report = tool.build_report(Path("/tmp"))

    deleted = report["deleted_media_payload_state"]
    assert deleted["validated"] is True
    assert deleted["retained_media_payload_files"] == 0
    assert deleted["retained_media_payload_bytes"] == 0
    scope = report["scope"]
    assert scope["semantic_claims_made"] is False
    assert scope["v_plus_s_plus_a_claimed"] is False
    assert scope["human_review_claimed"] is False
    assert scope["ses_claimed"] is False
    assert scope["h_tier_claimed"] is False
    assert scope["gate_a_claimed"] is False
    assert scope["sample_level_av_sync_claimed"] is False


def test_snapshot_hash_mismatch_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = load_tool()
    relative = "snapshot/headers.txt"
    path = tmp_path / relative
    path.parent.mkdir()
    path.write_text("changed", encoding="utf-8")

    monkeypatch.setattr(
        tool,
        "EXPECTED_SNAPSHOT_SHA256",
        {relative: "0" * 64},
    )
    monkeypatch.setattr(
        tool,
        "EXPECTED_DIRECTORY_FILES",
        {"snapshot": {"headers.txt"}},
    )
    with pytest.raises(
        tool.ClosureError, match="PINNED_EVIDENCE_HASH_MISMATCH"
    ):
        tool.verify_snapshot(tmp_path)


def test_renderer_does_not_upgrade_captain_authority() -> None:
    tool = load_tool()
    report = tool.build_report(Path("/tmp"))
    markdown = tool.render_markdown(copy.deepcopy(report))

    assert "technically ready but exact acquisition is not authorized" in markdown
    assert "AUTHORIZED_NOW_CC_BY_NC_NONCOMMERCIAL_ONLY" in markdown
    assert "NOT_AUTHORIZED_GOVERNANCE_AUTHORITY_OPEN" in markdown
    assert "sample-level synchronization" in markdown
    assert "semantic, V+S+A, human-review, SES, H-tier" in markdown


def test_committed_outputs_are_deterministic_and_current() -> None:
    tool = load_tool()
    report = tool.build_report(Path("/tmp"))
    expected_json = json.dumps(report, indent=2, sort_keys=True) + "\n"
    expected_markdown = tool.render_markdown(report)

    assert REPORT_PATH.read_text(encoding="utf-8") == expected_json
    assert MARKDOWN_PATH.read_text(encoding="utf-8") == expected_markdown


def test_check_cli_prints_ready_marker(capsys: pytest.CaptureFixture[str]) -> None:
    tool = load_tool()

    result = tool.main(["--check"])

    assert result == 0
    assert capsys.readouterr().out.strip() == tool.FINAL_READY
