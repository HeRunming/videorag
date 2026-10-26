from __future__ import annotations

import importlib.util
import json
import os
import struct
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools/ffprobe_mp4_metadata_shim.py"
P23_102_PATH = (
    ROOT
    / "data/restricted/epic_p23_102_source_v1/media/P23/P23_102.MP4"
)

SPEC = importlib.util.spec_from_file_location(
    "ffprobe_mp4_metadata_shim",
    MODULE_PATH,
)
assert SPEC and SPEC.loader
SHIM = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SHIM
SPEC.loader.exec_module(SHIM)


def box(kind: bytes, payload: bytes, *, extended: bool = False) -> bytes:
    assert len(kind) == 4
    if extended:
        return (
            struct.pack(">I4sQ", 1, kind, 16 + len(payload))
            + payload
        )
    return struct.pack(">I4s", 8 + len(payload), kind) + payload


def full_box(
    kind: bytes,
    payload: bytes,
    *,
    version: int = 0,
    flags: int = 0,
) -> bytes:
    return box(kind, bytes([version]) + flags.to_bytes(3, "big") + payload)


def mvhd(timescale: int, duration: int, *, version: int) -> bytes:
    if version == 0:
        payload = struct.pack(">IIII", 0, 0, timescale, duration)
    else:
        payload = struct.pack(">QQIQ", 0, 0, timescale, duration)
    return full_box(b"mvhd", payload, version=version)


def mdhd(timescale: int, duration: int, *, version: int) -> bytes:
    if version == 0:
        payload = struct.pack(">IIII", 0, 0, timescale, duration)
    else:
        payload = struct.pack(">QQIQ", 0, 0, timescale, duration)
    return full_box(b"mdhd", payload, version=version)


def tkhd(track_id: int, width: int, height: int, *, version: int) -> bytes:
    if version == 0:
        prefix = struct.pack(">IIIII", 0, 0, track_id, 0, 1)
    else:
        prefix = struct.pack(">QQIIQ", 0, 0, track_id, 0, 1)
    matrix = struct.pack(
        ">9I",
        0x00010000,
        0,
        0,
        0,
        0x00010000,
        0,
        0,
        0,
        0x40000000,
    )
    payload = (
        prefix
        + b"\x00" * 8
        + struct.pack(">hhhh", 0, 0, 0, 0)
        + matrix
        + struct.pack(">II", width << 16, height << 16)
    )
    return full_box(b"tkhd", payload, version=version, flags=3)


def hdlr(handler: bytes) -> bytes:
    return full_box(
        b"hdlr",
        struct.pack(">I4s", 0, handler) + b"\x00" * 12 + b"test\x00",
    )


def descriptor(tag: int, payload: bytes) -> bytes:
    assert len(payload) < 128
    return bytes([tag, len(payload)]) + payload


def video_stsd(width: int, height: int) -> bytes:
    compressor = b"\x00" * 32
    entry_payload = (
        b"\x00" * 6
        + struct.pack(">H", 1)
        + b"\x00" * 16
        + struct.pack(">HH", width, height)
        + struct.pack(">II", 0x00480000, 0x00480000)
        + b"\x00" * 4
        + struct.pack(">H", 1)
        + compressor
        + struct.pack(">HH", 24, 0xFFFF)
    )
    entry = box(b"hvc1", entry_payload + box(b"hvcC", b"\x01"))
    return full_box(b"stsd", struct.pack(">I", 1) + entry)


def audio_stsd(sample_rate: int, channels: int) -> bytes:
    audio_specific_config = descriptor(0x05, b"\x12\x10")
    decoder_config = descriptor(
        0x04,
        bytes([0x40, 0x15])
        + b"\x00\x00\x00"
        + b"\x00\x00\x00\x00"
        + b"\x00\x00\x00\x00"
        + audio_specific_config,
    )
    es_descriptor = descriptor(
        0x03,
        b"\x00\x01\x00" + decoder_config + descriptor(0x06, b"\x02"),
    )
    esds = full_box(b"esds", es_descriptor)
    entry_payload = (
        b"\x00" * 6
        + struct.pack(">H", 1)
        + b"\x00" * 8
        + struct.pack(">HHHHI", channels, 16, 0, 0, sample_rate << 16)
    )
    return full_box(
        b"stsd",
        struct.pack(">I", 1) + box(b"mp4a", entry_payload + esds),
    )


def track(
    handler: bytes,
    track_id: int,
    timescale: int,
    duration: int,
    sample_description: bytes,
    *,
    width: int = 0,
    height: int = 0,
    version: int = 0,
) -> bytes:
    stbl = box(b"stbl", sample_description)
    minf = box(b"minf", stbl)
    media = box(
        b"mdia",
        mdhd(timescale, duration, version=version)
        + hdlr(handler)
        + minf,
    )
    return box(
        b"trak",
        tkhd(track_id, width, height, version=version) + media,
    )


def synthetic_mp4(
    *,
    moov_first: bool = False,
    extended_moov: bool = False,
    version: int = 0,
) -> bytes:
    video_timescale = 90_000
    video_duration = 900_000
    audio_timescale = 48_000
    audio_duration = 480_000
    movie_timescale = 1_000
    movie_duration = 10_000
    movie = box(
        b"moov",
        mvhd(movie_timescale, movie_duration, version=version)
        + track(
            b"vide",
            1,
            video_timescale,
            video_duration,
            video_stsd(1920, 1080),
            width=1920,
            height=1080,
            version=version,
        )
        + track(
            b"soun",
            2,
            audio_timescale,
            audio_duration,
            audio_stsd(48_000, 2),
            version=version,
        ),
        extended=extended_moov,
    )
    file_type = box(b"ftyp", b"isom" + struct.pack(">I", 512) + b"isommp41")
    media_data = box(b"mdat", b"SAMPLE_BYTES_MUST_NOT_BE_READ")
    if moov_first:
        return file_type + movie + media_data
    return file_type + media_data + movie


@pytest.mark.parametrize(
    ("moov_first", "extended_moov", "version"),
    [
        (False, False, 0),
        (True, False, 0),
        (False, True, 0),
        (True, True, 1),
    ],
)
def test_synthetic_mp4_reports_required_ffprobe_fields(
    tmp_path: Path,
    moov_first: bool,
    extended_moov: bool,
    version: int,
) -> None:
    path = tmp_path / "fixture.mp4"
    path.write_bytes(
        synthetic_mp4(
            moov_first=moov_first,
            extended_moov=extended_moov,
            version=version,
        )
    )

    result = SHIM.probe_path(path)
    streams = result.report["streams"]
    assert streams == [
        {
            "codec_type": "video",
            "codec_name": "hevc",
            "codec_tag_string": "hvc1",
            "width": 1920,
            "height": 1080,
            "index": 0,
            "id": "0x1",
            "time_base": "1/90000",
            "duration_ts": 900_000,
            "duration": "10.000000",
        },
        {
            "codec_type": "audio",
            "codec_name": "aac",
            "codec_tag_string": "mp4a",
            "sample_rate": "48000",
            "channels": 2,
            "channel_layout": "stereo",
            "index": 1,
            "id": "0x2",
            "time_base": "1/48000",
            "duration_ts": 480_000,
            "duration": "10.000000",
        },
    ]
    assert result.report["format"]["duration"] == "10.000000"
    assert result.report["format"]["nb_streams"] == 2
    mdat = next(box for box in result.top_level_boxes if box.type == b"mdat")
    assert all(
        read_end <= mdat.payload_start or read_start >= mdat.end
        for read_start, read_end in result.read_ranges
    )


def test_cli_accepts_exact_acquisition_argv(tmp_path: Path) -> None:
    path = tmp_path / "fixture.mp4"
    path.write_bytes(synthetic_mp4())
    completed = subprocess.run(
        [
            str(MODULE_PATH),
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["streams"][0]["codec_tag_string"] == "hvc1"
    assert report["streams"][1]["channel_layout"] == "stereo"
    assert report["format"]["duration"] == "10.000000"


@pytest.mark.parametrize(
    "payload",
    [
        b"\x00\x00\x00\x04moov",
        box(b"ftyp", b"isom\x00\x00\x00\x00isom")
        + struct.pack(">I4s", 1000, b"moov"),
        box(b"ftyp", b"isom\x00\x00\x00\x00isom")
        + box(b"moof", b"")
        + box(b"mdat", b"x")
        + box(b"moov", mvhd(1000, 1000, version=0)),
    ],
)
def test_malformed_or_unsupported_files_fail_closed(
    tmp_path: Path,
    payload: bytes,
) -> None:
    path = tmp_path / "bad.mp4"
    path.write_bytes(payload)
    with pytest.raises(SHIM.ProbeError):
        SHIM.probe_path(path)


def test_rejects_unsupported_cli_option(tmp_path: Path) -> None:
    path = tmp_path / "fixture.mp4"
    path.write_bytes(synthetic_mp4())
    assert SHIM.main(["-show_packets", str(path)]) == 1


@pytest.mark.skipif(
    not P23_102_PATH.is_file(),
    reason="assembled local P23_102 is unavailable",
)
def test_local_p23_102_bounded_metadata_only_smoke() -> None:
    result = SHIM.probe_path(P23_102_PATH)
    streams = result.report["streams"]
    videos = [stream for stream in streams if stream["codec_type"] == "video"]
    audios = [stream for stream in streams if stream["codec_type"] == "audio"]
    assert len(videos) == 1
    assert len(audios) == 1
    assert videos[0]["codec_name"] == "hevc"
    assert videos[0]["codec_tag_string"] == "hvc1"
    assert (videos[0]["width"], videos[0]["height"]) == (1920, 1080)
    assert videos[0]["time_base"] == "1/90000"
    assert float(videos[0]["duration"]) == pytest.approx(3569.52)
    assert audios[0]["codec_name"] == "aac"
    assert audios[0]["codec_tag_string"] == "mp4a"
    assert audios[0]["sample_rate"] == "48000"
    assert audios[0]["channels"] == 2
    assert audios[0]["channel_layout"] == "stereo"
    assert audios[0]["time_base"] == "1/48000"
    assert float(audios[0]["duration"]) == pytest.approx(3569.536)
    assert float(result.report["format"]["duration"]) == pytest.approx(3569.536)

    mdat = next(box for box in result.top_level_boxes if box.type == b"mdat")
    assert result.bytes_read < 1 * 1024 * 1024
    assert result.largest_read < 64 * 1024
    assert all(
        read_end <= mdat.payload_start or read_start >= mdat.end
        for read_start, read_end in result.read_ranges
    )
    assert os.access(MODULE_PATH, os.X_OK)
