from __future__ import annotations

from pathlib import Path

import pytest

from av_trace_media.reader import MediaDecodeError, MediaIntegrityError, PyAVMediaReader
from av_trace_media.types import TimeInterval

from .conftest import digest


FIXTURES = Path(__file__).resolve().parents[1] / "mvp/media_backed/fixtures"


def test_reader_validates_hash_and_reports_exact_bounded_coverage(registered):
    path, media_hash = registered["syn_source_01"]
    decoded = PyAVMediaReader(path, media_hash).read(
        TimeInterval(24.25, 26.75),
        include_video=True,
        include_audio=True,
    )
    assert decoded.media_hash == media_hash
    assert decoded.video_coverage[0].start_s == 24.25
    assert decoded.video_coverage[-1].end_s == 26.75
    assert decoded.audio is not None
    assert decoded.audio.interval.start_s == pytest.approx(24.25, abs=1 / decoded.audio.sample_rate)
    assert decoded.audio.interval.end_s == pytest.approx(26.75, abs=1 / decoded.audio.sample_rate)
    assert decoded.audio.sample_count == pytest.approx(2.5 * decoded.audio.sample_rate, abs=2)


def test_reader_fails_closed_on_missing_or_wrong_media(tmp_path: Path, registered):
    path, media_hash = registered["syn_source_01"]
    with pytest.raises(MediaIntegrityError):
        PyAVMediaReader(tmp_path / "missing.mp4", media_hash).read(
            TimeInterval(0, 1), include_video=True, include_audio=False
        )
    wrong = tmp_path / "wrong.mp4"
    wrong.write_bytes(path.read_bytes())
    with pytest.raises(MediaIntegrityError):
        PyAVMediaReader(wrong, "sha256:" + "0" * 64).read(
            TimeInterval(0, 1), include_video=True, include_audio=False
        )


def test_reader_fails_closed_on_registered_truncation(tmp_path: Path, registered):
    source, _ = registered["syn_source_01"]
    truncated = tmp_path / "truncated.mp4"
    truncated.write_bytes(source.read_bytes()[: source.stat().st_size // 2])
    with pytest.raises(MediaDecodeError):
        PyAVMediaReader(truncated, digest(truncated)).read(
            TimeInterval(175, 182), include_video=True, include_audio=True
        )


def test_reader_rejects_corrupt_registered_bytes(tmp_path: Path):
    corrupt = tmp_path / "corrupt.mp4"
    corrupt.write_bytes(b"not an mp4 container")
    with pytest.raises(MediaDecodeError):
        PyAVMediaReader(corrupt, digest(corrupt)).read(
            TimeInterval(0, 1), include_video=True, include_audio=True
        )


def test_checked_in_truncated_and_corrupt_fixtures_fail_closed():
    import json

    fixture_hashes = json.loads((FIXTURES / "fixture_hashes.json").read_text())
    registered = {item["path"]: item["sha256"] for item in fixture_hashes["fixtures"]}
    with pytest.raises(MediaDecodeError):
        PyAVMediaReader(
            FIXTURES / "syn_source_01_truncated.mp4",
            registered["syn_source_01_truncated.mp4"],
        ).read(TimeInterval(175, 182), include_video=True, include_audio=True)
    with pytest.raises(MediaDecodeError):
        PyAVMediaReader(
            FIXTURES / "corrupt.mp4",
            registered["corrupt.mp4"],
        ).read(TimeInterval(0, 1), include_video=True, include_audio=True)
