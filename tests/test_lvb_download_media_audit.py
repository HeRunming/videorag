from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import lvb_download_media_audit as audit


def test_parse_timestamp_accepts_clock_and_numeric_and_rejects_invalid() -> None:
    assert audit.parse_timestamp("01:02:03.500") == pytest.approx(3723.5)
    assert audit.parse_timestamp("12.25") == pytest.approx(12.25)
    assert audit.parse_timestamp(7) == pytest.approx(7.0)
    for value in ("00:60:00", "00:00:60", "not-a-time", float("inf"), None, True):
        with pytest.raises((TypeError, ValueError)):
            audit.parse_timestamp(value)


def test_subtitle_analysis_reports_valid_timeline_without_disclosing_text() -> None:
    value = [
        {"start": "00:00:01.000", "end": "00:00:02.000", "line": "first secret line"},
        {"start": "00:00:03.000", "end": "00:00:04.000", "line": "second secret line"},
    ]
    result = audit.analyze_subtitle_value(value, 5.0)
    assert result["valid"] is True
    assert result["schema"]["entry_count"] == 2
    assert result["timeline"]["first_timestamp_seconds"] == 1.0
    assert result["timeline"]["last_timestamp_seconds"] == 4.0
    assert result["timeline"]["obvious_timeline_mismatch"] is False
    assert "secret" not in json.dumps(result)


def test_subtitle_analysis_detects_temporal_and_text_problems() -> None:
    value = [
        {"start": "00:00:03.000", "end": "00:00:05.500", "line": "ok"},
        {"start": "00:00:02.000", "end": "00:00:01.000", "line": " "},
    ]
    result = audit.analyze_subtitle_value(value, 10.0)
    assert result["valid"] is False
    assert "END_BEFORE_START" in result["errors"]
    assert "START_TIMES_NOT_ORDERED" in result["errors"]
    assert "EMPTY_TEXT_ENTRIES" in result["warnings"]
    assert result["temporal_validation"]["empty_text_entry_count"] == 1


def test_duration_comparison_uses_absolute_or_relative_tolerance() -> None:
    assert audit.compare_duration(1000.8, 1000.0)["within_tolerance"] is True
    assert audit.compare_duration(1002.0, 1000.0)["within_tolerance"] is False
    unavailable = audit.compare_duration(None, 1000.0)
    assert unavailable["within_tolerance"] is False
    assert unavailable["absolute_difference_seconds"] is None


def test_inventory_detects_partial_lock_symlink_orphan_and_unexpected(tmp_path: Path) -> None:
    repo = tmp_path
    root = repo / "data/restricted/lvb01"
    videos = root / "raw/videos"
    subtitles = root / "raw/subtitles"
    manifests = root / "manifests"
    videos.mkdir(parents=True)
    subtitles.mkdir(parents=True)
    manifests.mkdir(parents=True)
    payload = videos / "expected.mp4"
    payload.write_bytes(b"media")
    sidecar = videos / "expected.mp4.metadata.json"
    sidecar.write_text("{}")
    orphan = subtitles / "orphan.json.metadata.json"
    orphan.write_text("{}")
    (videos / "stale.partial").write_bytes(b"x")
    (manifests / ".stale.lock").write_text("x")
    (videos / "unexpected.mp4").write_bytes(b"x")
    (videos / "link").symlink_to(payload)

    result = audit.inventory_tree(
        root,
        {payload},
        {sidecar},
        set(),
        repo,
    )
    assert result["passed"] is False
    assert result["partial_files"]
    assert result["stale_locks"]
    assert result["symlinks"]
    assert result["orphan_sidecars"]
    assert result["unexpected_payload_files"]


def test_sensitive_json_scan_reports_locations_without_values(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "authorization": "do-not-repeat",
                "url": "https://example.test/file?X-Amz-Signature=do-not-repeat",
            }
        )
    )
    result = audit.scan_sensitive_json(path)
    rendered = json.dumps(result)
    assert result["passed"] is False
    assert result["finding_count"] >= 2
    assert "do-not-repeat" not in rendered


def test_path_safety_requires_restricted_permissions(tmp_path: Path) -> None:
    repo = tmp_path
    root = repo / "data/restricted/lvb01"
    root.mkdir(parents=True)
    path = root / "payload.bin"
    path.write_bytes(b"x")
    path.chmod(0o600)
    safe = audit.path_safety(path, root, repo)
    assert safe["resolved_under_restricted_root"] is True
    assert safe["restricted_permissions"] is True
    path.chmod(0o644)
    unsafe = audit.path_safety(path, root, repo)
    assert unsafe["restricted_permissions"] is False


def test_decision_is_conditional_when_external_probe_is_unavailable() -> None:
    integrity_entries = [{"passed": True}]
    integrity_summary = {
        "aggregate": {"exact_match": True},
        "inventory": {"passed": True},
    }
    videos = [
        {
            "technically_usable": True,
            "external_ffprobe": {"available": False},
            "streams": {"audio_stream_count": 1},
        }
    ]
    subtitles = [{"usable_speech_proxy": True, "warnings": []}]
    decision, reasons = audit.decide(
        integrity_entries,
        integrity_summary,
        videos,
        subtitles,
        [{"passed": True}],
    )
    assert decision == "CONDITIONAL_GO"
    assert any("ffprobe/ffmpeg" in reason for reason in reasons)


def test_decision_fails_closed_on_integrity_problem() -> None:
    decision, reasons = audit.decide(
        [{"passed": False}],
        {"aggregate": {"exact_match": True}, "inventory": {"passed": True}},
        [
            {
                "technically_usable": True,
                "external_ffprobe": {"available": True},
                "streams": {"audio_stream_count": 1},
            }
        ],
        [{"usable_speech_proxy": True, "warnings": []}],
        [{"passed": True}],
    )
    assert decision == "NO_GO"
    assert reasons
