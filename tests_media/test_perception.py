from __future__ import annotations

import json
from pathlib import Path

import pytest

from av_trace_media.adapters import MediaPerception
from av_trace_media.speech import SpeechAdapter, SyntheticSpeechCodec
from av_trace_media.types import TimeInterval


@pytest.mark.parametrize(
    ("source", "interval", "expected"),
    [
        ("syn_source_01", (24, 30), ("triangle", "blue", None, "BLUE TRIANGLE")),
        ("syn_source_01", (176, 182), ("circle", "green", None, "GREEN CIRCLE")),
        ("syn_source_02", (92, 98), ("star", "yellow", None, "YELLOW STAR")),
        ("syn_source_02", (224, 230), ("square", "red", None, "RED SQUARE")),
        ("syn_source_03", (310, 316), ("arrow", "cobalt", "right", "COBALT ARROW POINTS RIGHT")),
        ("syn_source_04", (62, 68), ("hexagon", "orange", None, "ORANGE HEXAGON")),
    ],
)
def test_visual_observations_come_from_pixels(registered, source, interval, expected):
    path, media_hash = registered[source]
    result = MediaPerception.synthetic(str(path), media_hash).inspect_clip(
        TimeInterval(*interval), include_video=True, include_audio=False
    )
    observation = result["observations"][0]
    content = observation["content"]
    assert (content["shape"], content["color"], content["arrow_direction"], content["visible_text"]) == expected
    assert observation["provenance"]["media_hash"] == media_hash
    assert observation["provenance"]["decoded_interval"] == {"start_s": interval[0], "end_s": interval[1]}
    assert observation["provenance"]["observation_confidence"] >= 0.75


def test_visual_ocr_reads_visible_numeric_counter(registered):
    path, media_hash = registered["syn_source_01"]
    observation = MediaPerception.synthetic(str(path), media_hash).inspect_clip(
        TimeInterval(24, 25), include_video=True, include_audio=False
    )["observations"][0]
    assert observation["content"]["numeric_tokens"] == ["0", "0", "2", "4"]


@pytest.mark.parametrize(
    ("source", "interval", "signature", "count", "frequency"),
    [
        ("syn_source_02", (38, 44), "bell_pulses", 3, 880),
        ("syn_source_03", (110, 118), "motor_hum", None, 110),
        ("syn_source_03", (276, 282), "click_pulses", 2, 698),
        ("syn_source_04", (398, 404), "confirmation_chime", None, 1047),
    ],
)
def test_ambient_observations_come_from_waveform(registered, source, interval, signature, count, frequency):
    path, media_hash = registered[source]
    result = MediaPerception.synthetic(str(path), media_hash).observe_ambient(TimeInterval(*interval))
    observation = result["observations"][0]
    assert observation["content"]["signature"] == signature
    assert observation["content"]["pulse_count"] == count
    assert observation["content"]["dominant_frequency_hz"] == pytest.approx(frequency, abs=2)
    assert observation["content"]["dominant_frequency_bands"]
    assert observation["provenance"]["adapter_version"]
    assert observation["provenance"]["observation_confidence"] >= 0.75


@pytest.mark.parametrize(
    ("source", "interval", "text"),
    [
        ("syn_source_01", (72, 78), "DELTA SEVEN"),
        ("syn_source_01", (198, 204), "OPEN GATE"),
        ("syn_source_02", (246, 252), "PLACE IN BIN FOUR"),
        ("syn_source_03", (48, 54), "ROUTE COBALT"),
        ("syn_source_04", (146, 152), "FIVE UNITS"),
        ("syn_source_04", (432, 438), "STATUS CLEAR"),
    ],
)
def test_synthetic_codec_transcribes_waveform_symbols(registered, source, interval, text):
    path, media_hash = registered[source]
    result = MediaPerception.synthetic(str(path), media_hash).read_transcript(TimeInterval(*interval))
    assert result["source"] == "synthetic_codec"
    assert result["observations"][0]["content"]["text"] == text
    assert result["observations"][0]["content"]["source"] == "synthetic_codec"
    assert result["observations"][0]["provenance"]["media_hash"] == media_hash


def test_speech_adapter_is_versioned_and_replaceable():
    codec = SyntheticSpeechCodec()
    assert isinstance(codec, SpeechAdapter)
    assert codec.adapter_kind == "synthetic_codec"
    assert codec.version.startswith("synthetic_codec/")
    assert codec.interface_version.startswith("speech-adapter/")


def test_annotation_is_evaluator_only_not_adapter_input(registered):
    # This test alone reads annotations, after perception has run.  It checks
    # output against gold and demonstrates that no annotation object/path is
    # accepted by the media adapter API.
    path, media_hash = registered["syn_source_02"]
    perception = MediaPerception.synthetic(str(path), media_hash)
    observed = perception.inspect_clip(
        TimeInterval(224, 230), include_video=True, include_audio=False
    )["observations"][0]["content"]
    annotation_path = Path(__file__).resolve().parents[1] / "mvp/generated/full/evidence/syn_source_02.json"
    annotation = json.loads(annotation_path.read_text(encoding="utf-8"))
    gold = next(item for item in annotation["evidence"] if item["evidence_id"] == "s2_red_square")
    assert gold["observation"] == f"{observed['color'].upper()} {observed['shape'].upper()}"
