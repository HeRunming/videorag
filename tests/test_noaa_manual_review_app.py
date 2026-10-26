from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import noaa_manual_review_app as review


ROOT = Path(__file__).resolve().parents[1]


def real_context(tmp_path: Path) -> review.AppContext:
    queue = review.load_json(ROOT / review.QUEUE_REL)
    template = review.load_json(ROOT / review.TEMPLATE_REL)
    media_paths = {
        item["candidate_id"]: ROOT / review.RAW_ROOT_REL / item["basename"]
        for item in queue["media_assets"]
    }
    return review.AppContext(
        repo_root=ROOT,
        queue=queue,
        template=template,
        media_paths=media_paths,
        decisions_path=tmp_path / "decisions.json",
        export_path=tmp_path / "export.json",
    )


def complete_judgment() -> dict:
    value = review.blank_judgment()
    value.update(
        {
            "media_loads_and_seeks_correctly": "yes",
            "speech_present": "yes",
            "speech_intelligible": "uncertain",
            "non_speech_audio_present": "no",
            "non_speech_audio_type": "uncertain",
            "meaningful_visual_information": "yes",
            "visual_type": "slide",
            "plausible_question_evidence_seed": "Human-entered seed.",
            "candidate_modality_role": "V+S",
            "sensitive_distressing_private_content": "no",
            "disposition": "defer",
            "reviewer_confidence": "medium",
            "reviewer_notes": "Needs a second pass.",
        }
    )
    value["modality_necessity"] = {
        "V": "potentially_necessary",
        "S": "potentially_necessary",
        "A": "not_selected",
    }
    value["evidence_interval_adjustment"] = {
        "status": "keep",
        "adjusted_start_seconds": None,
        "adjusted_end_seconds": None,
    }
    return value


def test_packet_is_deterministic_balanced_and_temporally_separated() -> None:
    queue = review.load_json(ROOT / review.QUEUE_REL)
    template = review.load_json(ROOT / review.TEMPLATE_REL)
    result = review.validate_packet(ROOT, queue, template)
    assert result["status"] == "VALID"
    assert result["listener_started"] is False
    assert result["queue_count"] == 18
    assert result["per_asset_count"] == {
        "cand-049": 6,
        "cand-051": 6,
        "cand-052": 6,
    }
    assert set(result["routing_hypothesis_counts"]) == review.ROUTING_HYPOTHESES


def test_queue_uses_only_allowlisted_assets_and_source_measurements() -> None:
    queue = review.build_queue(ROOT)
    assert tuple(queue["pilot_asset_ids"]) == review.PILOT_ASSET_IDS
    assert {item["candidate_id"] for item in queue["windows"]} == set(
        review.PILOT_ASSET_IDS
    )
    assert all(item["media_route"] == f"/media/{item['candidate_id']}" for item in queue["windows"])
    assert all(item["routing_only_not_human_judgment"] is True for item in queue["windows"])
    assert all("raw/" not in item["media_route"] for item in queue["windows"])


def test_template_is_unfilled_and_does_not_copy_routing_hypotheses() -> None:
    template = review.load_json(ROOT / review.TEMPLATE_REL)
    queue = review.load_json(ROOT / review.QUEUE_REL)
    assert template["status"] == "UNFILLED"
    assert template["human_answers_prefilled"] is False
    assert len(template["records"]) == queue["queue_count"]
    for record in template["records"]:
        assert record["judgment"] == review.blank_judgment()
        assert "routing_hypothesis" not in record["judgment"]


@pytest.mark.parametrize(
    ("header", "size", "expected"),
    [
        (None, 10, (0, 9, False)),
        ("bytes=2-5", 10, (2, 5, True)),
        ("bytes=7-", 10, (7, 9, True)),
        ("bytes=-3", 10, (7, 9, True)),
        ("bytes=0-99", 10, (0, 9, True)),
    ],
)
def test_parse_byte_range(
    header: str | None, size: int, expected: tuple[int, int, bool]
) -> None:
    assert review.parse_byte_range(header, size) == expected


@pytest.mark.parametrize("header", ["bytes=", "bytes=8-2", "bytes=0-1,3-4", "items=0-1"])
def test_parse_byte_range_rejects_invalid_or_multiple_ranges(header: str) -> None:
    with pytest.raises(review.ReviewError):
        review.parse_byte_range(header, 10)


def test_save_resume_and_export_are_structured_and_deterministic(
    tmp_path: Path,
) -> None:
    context = real_context(tmp_path)
    first = context.queue["windows"][0]
    saved = review.save_record(
        context, first["review_id"], complete_judgment(), "reviewer-01"
    )
    resumed = review.load_state(context)
    assert resumed == saved
    assert context.decisions_path.stat().st_mode & 0o777 == 0o600

    first_export = review.deterministic_export(context)
    first_bytes = context.export_path.read_bytes()
    second_export = review.deterministic_export(context)
    assert second_export == first_export
    assert context.export_path.read_bytes() == first_bytes
    assert first_export["record_count"] == 18
    assert first_export["completed_count"] == 1
    assert first_export["records"][0]["judgment"]["plausible_question_evidence_seed"] == (
        "Human-entered seed."
    )
    assert context.export_path.stat().st_mode & 0o777 == 0o600


def test_adjusted_interval_must_be_bounded_by_original_asset(tmp_path: Path) -> None:
    context = real_context(tmp_path)
    first = context.queue["windows"][0]
    judgment = complete_judgment()
    judgment["evidence_interval_adjustment"] = {
        "status": "adjust",
        "adjusted_start_seconds": 0.0,
        "adjusted_end_seconds": 999999.0,
    }
    with pytest.raises(review.ReviewError, match="ADJUSTED_INTERVAL_OUT_OF_BOUNDS"):
        review.save_record(context, first["review_id"], judgment, None)


def test_unknown_review_id_and_invalid_enum_fail_closed(tmp_path: Path) -> None:
    context = real_context(tmp_path)
    with pytest.raises(review.ReviewError, match="UNKNOWN_REVIEW_ID"):
        review.save_record(context, "not-a-window", complete_judgment(), None)
    first = context.queue["windows"][0]
    judgment = complete_judgment()
    judgment["speech_present"] = "probably"
    with pytest.raises(review.ReviewError, match="INVALID_SPEECH_PRESENT"):
        review.save_record(context, first["review_id"], judgment, None)


def test_dry_run_does_not_create_server(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("dry-run attempted to create a listener")

    monkeypatch.setattr(review, "create_server", forbidden)
    assert review.main(["--repo-root", str(ROOT), "--dry-run"]) == 0


def test_media_range_reads_only_requested_source_bytes(tmp_path: Path) -> None:
    context = real_context(tmp_path)
    payload = b"0123456789abcdef"
    path = tmp_path / "source.mp4"
    path.write_bytes(payload)
    start, end, partial = review.parse_byte_range("bytes=3-7", len(payload))
    assert partial is True
    assert b"".join(review.iter_file_range(path, start, end, chunk_size=2)) == b"34567"
    assert set(context.media_paths) == set(review.PILOT_ASSET_IDS)


def test_server_creation_uses_only_loopback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = real_context(tmp_path)
    captured = {}

    class FakeServer:
        def __init__(self, address, handler):  # type: ignore[no-untyped-def]
            captured["address"] = address
            captured["handler"] = handler

    monkeypatch.setattr(review, "ThreadingHTTPServer", FakeServer)
    server = review.create_server(context, 4321)
    assert isinstance(server, FakeServer)
    assert captured["address"] == (review.LOOPBACK_HOST, 4321)
    assert review.host_header_is_loopback("127.0.0.1:4321")
    assert review.host_header_is_loopback("localhost:4321")
    assert not review.host_header_is_loopback("example.invalid")


def test_source_has_no_media_decoder_or_outbound_client() -> None:
    source = (ROOT / "tools/noaa_manual_review_app.py").read_text()
    assert "import av" not in source
    assert "subprocess" not in source
    assert "requests" not in source
    assert "urllib.request" not in source
    assert "0.0.0.0" not in source
    assert "cv2.imwrite" not in source
    assert "waveform" in source
