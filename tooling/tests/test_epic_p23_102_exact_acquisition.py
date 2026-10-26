from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools/epic_p23_102_exact_acquisition.py"
SPEC = importlib.util.spec_from_file_location("epic_p23_102_exact", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_frozen_exact_identity() -> None:
    assert MODULE.ASSET_ID == "P23_102"
    assert MODULE.OBJECT_PATH == "P23/videos/P23_102.MP4"
    assert MODULE.EXPECTED_BYTES == 10_814_161_307
    assert MODULE.OFFICIAL_MD5 == "4698fcbf13782f6396029761eb3bd5f2"
    assert "25_109" not in MODULE.OFFICIAL_URL
    MODULE.validate_official_url(MODULE.OFFICIAL_URL)


def test_rejects_nonfrozen_url() -> None:
    with pytest.raises(MODULE.NoGoError):
        MODULE.validate_official_url(
            MODULE.OFFICIAL_URL.replace("P23_102", "P23_101")
        )


def test_parse_header_blocks_and_validate_partial_prefix() -> None:
    raw = (
        "HTTP/1.1 200 Connection established\r\n\r\n"
        "HTTP/1.1 206 Partial Content\r\n"
        "Content-Type: video/mp4\r\n"
        f"Content-Range: bytes 100-199/{MODULE.EXPECTED_BYTES}\r\n"
        "Content-Length: 100\r\n\r\n"
    )
    blocks = MODULE.parse_header_blocks(raw)
    result = MODULE.validate_range_response(
        blocks=blocks,
        requested_start=100,
        requested_end=199,
        body_bytes=37,
    )
    assert result["accepted_prefix_bytes"] == 37
    assert result["promised_bytes"] == 100


def test_rejects_range_total_change() -> None:
    blocks = [
        {
            "status_code": 206,
            "headers": {
                "content-type": "video/mp4",
                "content-range": "bytes 0-9/10",
            },
        }
    ]
    with pytest.raises(MODULE.NoGoError):
        MODULE.validate_range_response(
            blocks=blocks,
            requested_start=0,
            requested_end=9,
            body_bytes=10,
        )


def valid_ffprobe_report() -> dict:
    return {
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "hevc",
                "codec_tag_string": "hvc1",
                "width": 1920,
                "height": 1080,
                "duration": "3569.520000",
            },
            {
                "index": 1,
                "codec_type": "audio",
                "codec_name": "aac",
                "codec_tag_string": "mp4a",
                "sample_rate": "48000",
                "channels": 2,
                "channel_layout": "stereo",
                "duration": "3569.533333",
            },
            {
                "index": 2,
                "codec_type": "data",
                "codec_name": "bin_data",
                "duration": "3569.533000",
            },
        ],
        "format": {"duration": "3569.533333"},
    }


def test_ffprobe_exact_stream_gate_passes() -> None:
    result = MODULE.validate_ffprobe_report(valid_ffprobe_report())
    assert result["ffprobe_passed"] is True
    assert result["video"]["codec_tag_string"] == "hvc1"
    assert result["audio"]["codec_tag_string"] == "mp4a"
    assert result["av_duration_delta_seconds"] < 0.02


@pytest.mark.parametrize(
    ("field_path", "bad_value"),
    [
        (("streams", 0, "codec_tag_string"), "hev1"),
        (("streams", 0, "width"), 1280),
        (("streams", 1, "codec_tag_string"), "NONE"),
        (("streams", 1, "sample_rate"), "44100"),
        (("streams", 1, "channels"), 1),
    ],
)
def test_ffprobe_exact_stream_gate_rejects_identity_changes(
    field_path: tuple, bad_value: object
) -> None:
    report = json.loads(json.dumps(valid_ffprobe_report()))
    current = report
    for key in field_path[:-1]:
        current = current[key]
    current[field_path[-1]] = bad_value
    with pytest.raises(MODULE.NoGoError):
        MODULE.validate_ffprobe_report(report)


def test_ffprobe_rejects_non_near_equal_durations() -> None:
    report = valid_ffprobe_report()
    report["streams"][1]["duration"] = "3570.000000"
    with pytest.raises(MODULE.NoGoError):
        MODULE.validate_ffprobe_report(report)


def test_evidence_is_exact_and_nonsemantic() -> None:
    evidence = MODULE.verify_evidence()
    assert evidence["official_md5_manifest"]["verified"] is True
    provenance = MODULE.provenance_record(evidence)
    boundary = provenance["license_and_usage_boundary"]
    assert boundary["operative_license"] == "CC-BY-NC-4.0"
    assert boundary["noncommercial_only"] is True
    assert boundary["semantic_annotations_opened_or_used"] is False
    assert provenance["scope_exclusion"]["captaincook_25_109_acquired"] is False


def test_review_never_marks_partial_complete(tmp_path: Path, monkeypatch) -> None:
    part = tmp_path / "asset.part"
    part.write_bytes(b"partial")
    monkeypatch.setattr(MODULE, "PART_MEDIA", part)
    text = MODULE.review_markdown(
        disposition="REPAIR",
        message="interrupted",
    )
    assert "EPIC_P23_102_ACQUISITION_REPAIR" in text
    assert "EPIC_P23_102_ACQUISITION_READY" not in text
    assert "Canonical resumable staging bytes retained: `7`" in text
