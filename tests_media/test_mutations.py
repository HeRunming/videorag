from __future__ import annotations

from pathlib import Path

from av_trace_media.adapters import MediaPerception
from av_trace_media.types import TimeInterval

from .conftest import digest
from .media_mutation import blank_frame, mute_audio, rewrite_media, speech_symbol


FIXTURES = Path(__file__).resolve().parents[1] / "mvp/media_backed/fixtures"


def _content(result):
    return [item["content"] for item in result["observations"]]


def test_blanking_relevant_visual_frames_removes_only_that_observation(tmp_path: Path, registered):
    source, _ = registered["syn_source_01"]
    mutated = rewrite_media(
        source,
        tmp_path / "blank_visual.mp4",
        interval=(24, 30),
        mutate_video=blank_frame,
    )
    perception = MediaPerception.synthetic(str(mutated), digest(mutated))
    blanked = perception.inspect_clip(
        TimeInterval(24, 30), include_video=True, include_audio=False
    )
    untouched = perception.inspect_clip(
        TimeInterval(176, 182), include_video=True, include_audio=False
    )
    assert blanked["observations"] == []
    assert _content(untouched)[0]["shape"] == "circle"
    assert _content(untouched)[0]["color"] == "green"


def test_muting_ambient_segment_removes_event_and_preserves_visual(tmp_path: Path, registered):
    source, _ = registered["syn_source_02"]
    mutated = rewrite_media(
        source,
        tmp_path / "mute_ambient.mp4",
        interval=(38, 44),
        mutate_audio=mute_audio,
    )
    perception = MediaPerception.synthetic(str(mutated), digest(mutated))
    muted = perception.observe_ambient(TimeInterval(38, 44))
    untouched = perception.inspect_clip(
        TimeInterval(224, 230), include_video=True, include_audio=False
    )
    assert muted["observations"] == []
    assert _content(untouched)[0]["shape"] == "square"


def test_altering_synthetic_speech_symbol_changes_transcript_only(tmp_path: Path, registered):
    source, _ = registered["syn_source_01"]
    mutated = rewrite_media(
        source,
        tmp_path / "alter_speech.mp4",
        interval=(72, 78),
        mutate_audio=speech_symbol(659.0),
    )
    perception = MediaPerception.synthetic(str(mutated), digest(mutated))
    changed = perception.read_transcript(TimeInterval(72, 78))
    untouched = perception.read_transcript(TimeInterval(198, 204))
    visual = perception.inspect_clip(
        TimeInterval(24, 30), include_video=True, include_audio=False
    )
    assert _content(changed)[0]["text"] == "OPEN GATE"
    assert _content(untouched)[0]["text"] == "OPEN GATE"
    assert _content(visual)[0]["shape"] == "triangle"


def test_checked_in_mutation_fixtures_are_registered_and_media_sensitive():
    fixture_hashes = __import__("json").loads((FIXTURES / "fixture_hashes.json").read_text())
    registered = {item["path"]: item["sha256"] for item in fixture_hashes["fixtures"]}

    blank = MediaPerception.synthetic(
        str(FIXTURES / "syn_source_01_blank_24_30.mp4"),
        registered["syn_source_01_blank_24_30.mp4"],
    )
    assert blank.inspect_clip(
        TimeInterval(24, 30), include_video=True, include_audio=False
    )["observations"] == []
    assert _content(
        blank.inspect_clip(TimeInterval(176, 182), include_video=True, include_audio=False)
    )[0]["shape"] == "circle"

    muted = MediaPerception.synthetic(
        str(FIXTURES / "syn_source_02_mute_38_44.mp4"),
        registered["syn_source_02_mute_38_44.mp4"],
    )
    assert muted.observe_ambient(TimeInterval(38, 44))["observations"] == []

    changed = MediaPerception.synthetic(
        str(FIXTURES / "syn_source_01_speech_72_78_to_659hz.mp4"),
        registered["syn_source_01_speech_72_78_to_659hz.mp4"],
    )
    assert _content(changed.read_transcript(TimeInterval(72, 78)))[0]["text"] == "OPEN GATE"
