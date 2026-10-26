from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import noaa_download_media_audit as audit


def test_compare_duration_uses_absolute_or_relative_tolerance() -> None:
    assert audit.compare_duration(1000.8, 1000.0)["within_tolerance"] is True
    assert audit.compare_duration(1002.0, 1000.0)["within_tolerance"] is False
    unavailable = audit.compare_duration(None, 1000.0)
    assert unavailable["within_tolerance"] is False
    assert unavailable["absolute_difference_seconds"] is None


def test_decode_points_are_beginning_middle_and_near_end() -> None:
    points = audit.decode_points(100.0)
    assert [point["label"] for point in points] == ["beginning", "middle", "near_end"]
    assert [point["seconds"] for point in points] == pytest.approx([0.0, 50.0, 98.0])


def test_timeline_assessment_accepts_small_offsets() -> None:
    streams = {
        "video_streams": [{"start_time_seconds": 0.0, "duration_seconds": 100.0}],
        "audio_streams": [{"start_time_seconds": 0.02, "duration_seconds": 99.99}],
    }
    result = audit.assess_timeline(streams)
    assert result["assessment"] == "PLAUSIBLE_AT_CONTAINER_TIMELINE_LEVEL"
    assert result["av_start_offset_seconds"] == pytest.approx(0.02)
    assert result["av_end_offset_seconds"] == pytest.approx(0.01)


def test_timeline_assessment_fails_closed_without_audio() -> None:
    result = audit.assess_timeline({"video_streams": [{}], "audio_streams": []})
    assert result["assessment"] == "NOT_PLAUSIBLE_MISSING_DECLARED_AV_STREAM"


def test_sensitive_scan_reports_locations_without_values(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "authorization_header": "Bearer do-not-repeat",
                "url": "https://example.test/file?X-Amz-Signature=do-not-repeat",
            }
        )
    )
    result = audit.scan_sensitive_json(path)
    rendered = json.dumps(result)
    assert result["passed"] is False
    assert result["finding_count"] >= 2
    assert "do-not-repeat" not in rendered


def test_sensitive_scan_allows_explicit_prohibition_controls(tmp_path: Path) -> None:
    path = tmp_path / "authorization.json"
    path.write_text(
        json.dumps(
            {
                "authorization_header": "PROHIBITED",
                "cookie_header": "PROHIBITED",
                "bearer_tokens_prohibited": True,
            }
        )
    )
    assert audit.scan_sensitive_json(path)["passed"] is True


def test_sensitive_scan_allows_authorization_metadata_container(tmp_path: Path) -> None:
    path = tmp_path / "authorization.json"
    path.write_text(
        json.dumps(
            {
                "authorization_source": "prior user instruction",
                "authorized_scope": {"operations": ["bounded decoding"]},
                "authorization_boundary": {"public_release_authorized": False},
            }
        )
    )
    assert audit.scan_sensitive_json(path)["passed"] is True


def test_sensitive_scan_rejects_common_leaf_secret_keys(tmp_path: Path) -> None:
    path = tmp_path / "control.json"
    path.write_text(
        json.dumps(
            {
                "api_key": "do-not-repeat",
                "access_key": "also-do-not-repeat",
            }
        )
    )
    result = audit.scan_sensitive_json(path)
    assert result["passed"] is False
    assert result["finding_count"] == 2
    assert "do-not-repeat" not in json.dumps(result)


def test_path_safety_requires_restricted_permissions(tmp_path: Path) -> None:
    root = tmp_path / "data/restricted/noaa01"
    root.mkdir(parents=True)
    payload = root / "asset.mp4"
    payload.write_bytes(b"x")
    payload.chmod(0o600)
    assert audit.path_safety(payload, root, tmp_path)["restricted_permissions"] is True
    payload.chmod(0o644)
    assert audit.path_safety(payload, root, tmp_path)["restricted_permissions"] is False


def test_inventory_requires_directory_permissions_to_be_restricted(tmp_path: Path) -> None:
    root = tmp_path / "data/restricted/noaa01"
    raw = root / "raw"
    manifests = root / "manifests"
    raw.mkdir(parents=True)
    manifests.mkdir()
    payload = raw / "expected.mp4"
    sidecar = raw / "expected.mp4.metadata.json"
    manifest = manifests / "manifest.json"
    payload.write_bytes(b"media")
    sidecar.write_text("{}")
    manifest.write_text("{}")
    for path in (root, raw, manifests):
        path.chmod(0o700)
    for path in (payload, sidecar, manifest):
        path.chmod(0o600)
    assert audit.inventory_tree(
        root, {payload}, {sidecar}, {manifest}, tmp_path
    )["passed"] is True
    raw.chmod(0o750)
    assert audit.inventory_tree(
        root, {payload}, {sidecar}, {manifest}, tmp_path
    )["passed"] is False
    raw.chmod(0o700)
    sidecar.chmod(0o644)
    assert audit.inventory_tree(
        root, {payload}, {sidecar}, {manifest}, tmp_path
    )["passed"] is False


def test_inventory_detects_partial_lock_symlink_state_and_unexpected(
    tmp_path: Path,
) -> None:
    root = tmp_path / "data/restricted/noaa01"
    raw = root / "raw"
    manifests = root / "manifests"
    raw.mkdir(parents=True)
    manifests.mkdir()
    payload = raw / "expected.mp4"
    payload.write_bytes(b"media")
    sidecar = raw / "expected.mp4.metadata.json"
    sidecar.write_text("{}")
    (raw / "stale.partial").write_bytes(b"x")
    (raw / "orphan.state.json").write_text("{}")
    (raw / "unexpected.mp4").write_bytes(b"x")
    (manifests / ".stale.lock").write_text("x")
    (raw / "link").symlink_to(payload)
    result = audit.inventory_tree(root, {payload}, {sidecar}, set(), tmp_path)
    assert result["passed"] is False
    assert result["partial_files"]
    assert result["stale_locks"]
    assert result["symlinks"]
    assert result["orphan_state_files"]
    assert result["unexpected_payload_files"]


def test_ffprobe_compaction_tracks_stream_fields_and_stderr() -> None:
    parsed = {
        "format": {
            "format_name": "mov,mp4",
            "start_time": "0.0",
            "duration": "10.0",
        },
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "h264",
                "time_base": "1/1000",
                "start_time": "0.0",
                "duration": "10.0",
                "disposition": {"default": 1},
            }
        ],
    }
    result = audit._ffprobe_compact(parsed, "warning", 0)
    assert result["readable_container"] is True
    assert result["streams"][0]["codec_name"] == "h264"
    assert result["streams"][0]["start_time_seconds"] == 0.0
    assert result["streams"][0]["duration_seconds"] == 10.0
    assert result["streams"][0]["dispositions"] == ["default"]
    assert result["warning_or_error_output_present"] is True


def test_ffprobe_compaction_rejects_nonfinite_stream_timeline() -> None:
    parsed = {
        "format": {"format_name": "mov,mp4", "duration": "10.0"},
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "start_time": "nan",
                "duration": "10.0",
            }
        ],
    }
    result = audit._ffprobe_compact(parsed, "", 0)
    assert result["readable_container"] is False
    assert "FFPROBE_NONFINITE_STREAM_METADATA" in result["errors"]


def test_decode_observation_requires_targeted_finite_audio_statistics() -> None:
    observation = {
        "target_seconds": 50.0,
        "video": {"decoded": True, "frame_time_seconds": 50.04},
        "audio": {
            "decoded": True,
            "decoded_samples_exist": True,
            "finite_values": True,
            "peak_absolute_normalized": 0.8,
            "rms_normalized": 0.2,
            "first_frame_time_seconds": 49.99,
            "last_frame_end_seconds": 51.01,
        },
    }
    assert audit.decode_observation_passes(observation) == (True, True)
    observation["video"]["frame_time_seconds"] = 10.0
    assert audit.decode_observation_passes(observation) == (False, True)
    observation["video"]["frame_time_seconds"] = 50.0
    observation["audio"]["rms_normalized"] = None
    assert audit.decode_observation_passes(observation) == (True, False)


def test_decision_is_conditional_only_for_missing_external_ffprobe() -> None:
    gate = {"passed": True}
    integrity = [{"passed": True}]
    summary = {"aggregate": {"exact_match": True}, "inventory": {"passed": True}}
    media = [
        {
            "technical_audit_pass": True,
            "external_ffprobe": {"available": False},
        }
    ] * audit.EXPECTED_PAYLOAD_COUNT
    decision, reasons = audit.decide(
        gate, integrity, summary, media, [{"passed": True}]
    )
    assert decision == "CONDITIONAL_GO"
    assert any("ffprobe" in reason for reason in reasons)


def test_decision_fails_closed_on_decode_or_integrity_problem() -> None:
    media = [
        {
            "technical_audit_pass": False,
            "external_ffprobe": {"available": True},
        }
    ] * audit.EXPECTED_PAYLOAD_COUNT
    decision, reasons = audit.decide(
        {"passed": True},
        [{"passed": False}],
        {"aggregate": {"exact_match": True}, "inventory": {"passed": True}},
        media,
        [{"passed": True}],
    )
    assert decision == "NO_GO"
    assert reasons
