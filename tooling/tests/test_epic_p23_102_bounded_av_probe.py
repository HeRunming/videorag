from __future__ import annotations

import importlib.util
import struct
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/epic_p23_102_bounded_av_probe.py"


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "epic_p23_102_bounded_av_probe", TOOL_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def box(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", len(payload) + 8, kind) + payload


def full_box(kind: bytes, payload: bytes, *, version: int = 0) -> bytes:
    return box(kind, bytes([version, 0, 0, 0]) + payload)


def mvhd(timescale: int, duration: int) -> bytes:
    return full_box(
        b"mvhd",
        struct.pack(">IIII", 0, 0, timescale, duration),
    )


def tkhd(duration: int) -> bytes:
    payload = struct.pack(">IIII", 0, 0, 1, 0) + struct.pack(">I", duration)
    return box(b"tkhd", bytes([0, 0, 0, 1]) + payload)


def mdhd(timescale: int, duration: int) -> bytes:
    return full_box(
        b"mdhd",
        struct.pack(">IIII", 0, 0, timescale, duration),
    )


def hdlr(handler: bytes) -> bytes:
    return full_box(b"hdlr", struct.pack(">I4s", 0, handler))


def descriptor(tag: int, payload: bytes) -> bytes:
    assert len(payload) < 128
    return bytes([tag, len(payload)]) + payload


def audio_stsd() -> bytes:
    decoder_specific = descriptor(0x05, b"\x12\x10")
    decoder_config = descriptor(
        0x04,
        b"\x40\x15\0\0\0\0\0\0\0\0\0\0\0" + decoder_specific,
    )
    es_descriptor = descriptor(0x03, b"\0\x01\0" + decoder_config)
    esds = full_box(b"esds", es_descriptor)
    fixed = (
        b"\0" * 6
        + struct.pack(">H", 1)
        + struct.pack(">HHI", 0, 0, 0)
        + struct.pack(">HHHHI", 2, 16, 0, 0, 48_000 << 16)
    )
    entry = box(b"mp4a", fixed + esds)
    return full_box(b"stsd", struct.pack(">I", 1) + entry)


def video_stsd() -> bytes:
    entry = box(b"avc1", b"\0" * 78)
    return full_box(b"stsd", struct.pack(">I", 1) + entry)


def track(
    handler: bytes,
    timescale: int,
    media_duration: int,
    movie_duration: int,
    stsd: bytes,
) -> bytes:
    stbl = box(b"stbl", stsd)
    minf = box(b"minf", stbl)
    mdia = box(
        b"mdia", mdhd(timescale, media_duration) + hdlr(handler) + minf
    )
    return box(b"trak", tkhd(movie_duration) + mdia)


def fixture_mp4() -> bytes:
    duration = 3_600_000
    ftyp = box(b"ftyp", b"isom" + struct.pack(">I", 0) + b"isommp42")
    video = track(b"vide", 1_000, duration, duration, video_stsd())
    audio = track(
        b"soun", 48_000, 172_800_000, duration, audio_stsd()
    )
    moov = box(b"moov", mvhd(1_000, duration) + video + audio)
    return ftyp + box(b"mdat", b"\0" * 64) + moov


class MemoryReader:
    def __init__(self, data: bytes) -> None:
        self.data = data

    def read(self, start: int, length: int, purpose: str) -> bytes:
        del purpose
        return self.data[start : start + length]


def test_official_md5_binding_is_exact_but_not_full_file_verification() -> None:
    tool = load_tool()
    binding = tool.load_official_md5_binding()

    assert binding["object_path"] == "P23/videos/P23_102.MP4"
    assert binding["official_md5"] == "4698fcbf13782f6396029761eb3bd5f2"
    assert binding["full_object_md5_recomputed"] is False


def test_sparse_iso_bmff_parser_finds_native_av_codec_and_timeline() -> None:
    tool = load_tool()
    data = fixture_mp4()
    result = tool.inspect_iso_bmff(MemoryReader(data), len(data))

    assert result["video_track_count"] == 1
    assert result["audio_track_count"] == 1
    assert result["duration_seconds"] == 3600.0
    audio = next(
        track for track in result["tracks"] if track["handler_type"] == "soun"
    )
    assert audio["codec"] == "AAC LC"
    assert audio["channels"] == 2
    assert audio["sample_rate_hz"] == 48_000
    assert result["timeline"]["plausibly_synchronized"] is True
    assert result["timeline"]["sample_level_sync_decoded_or_verified"] is False


class IgnoredRangeResponse:
    def __init__(self) -> None:
        self.status_code = 200
        self.headers = {"content-length": "999999"}
        self.iterated = False

    def __enter__(self):
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def iter_bytes(self):
        self.iterated = True
        raise AssertionError("body must not be read when Range is ignored")


class IgnoredRangeClient:
    def __init__(self) -> None:
        self.response = IgnoredRangeResponse()

    def stream(self, *_: object, **__: object):
        return self.response


def test_range_ignored_200_aborts_before_reading_body() -> None:
    tool = load_tool()
    transport = IgnoredRangeClient()
    asset = tool.ExactAsset(size_bytes=1000)
    client = tool.BoundedRangeClient(
        asset,
        proxies=(),
        budget=tool.ByteBudget(maximum_response_bytes=100),
        clients=[transport],
    )

    with pytest.raises(
        tool.TransferError, match="RANGE_IGNORED_FULL_TRANSFER_ABORTED"
    ):
        client.fetch_range(0, 99, "test")

    assert transport.response.iterated is False
    assert client.budget.response_payload_bytes_read == 0
    assert client.records[-1].response_payload_bytes_read == 0


def test_exact_range_byte_accounting() -> None:
    tool = load_tool()
    payload = bytes(range(100))
    asset = tool.ExactAsset(size_bytes=100)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["range"] == "bytes=10-19"
        body = payload[10:20]
        return httpx.Response(
            206,
            headers={
                "content-length": str(len(body)),
                "content-range": "bytes 10-19/100",
                "content-encoding": "identity",
            },
            content=body,
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    budget = tool.ByteBudget(maximum_response_bytes=100, maximum_total_bytes=100)
    client = tool.BoundedRangeClient(
        asset,
        proxies=(),
        budget=budget,
        clients=[http_client],
    )
    body = client.fetch_range(10, 19, "test")

    assert body == payload[10:20]
    assert budget.response_payload_bytes_read == 10
    assert client.records[-1].response_payload_bytes_read == 10
    assert client.records[-1].body_sha256


def test_classification_ready_and_terminal_no_audio() -> None:
    tool = load_tool()
    container = {
        "video_track_count": 1,
        "audio_track_count": 1,
        "timeline": {"plausibly_synchronized": True},
    }
    marker, blockers = tool.classify(
        identity_match=True,
        range_verified=True,
        container=container,
        terminal_error=None,
    )
    assert marker == tool.READY
    assert blockers == []

    container["audio_track_count"] = 0
    marker, blockers = tool.classify(
        identity_match=True,
        range_verified=True,
        container=container,
        terminal_error="NO_ENABLED_AUDIO_TRACK",
    )
    assert marker == tool.NO_GO
    assert any("audio track" in blocker for blocker in blockers)


def test_caps_and_forbidden_claim_defaults() -> None:
    tool = load_tool()

    assert tool.MAX_RESPONSE_PAYLOAD_BYTES == 16 * 1024 * 1024
    assert tool.MAX_PERSISTED_RESPONSE_PAYLOAD_BYTES == 16 * 1024 * 1024
    assert tool.INITIAL_WINDOW_BYTES * 2 < tool.MAX_RESPONSE_PAYLOAD_BYTES
    source = TOOL_PATH.read_text(encoding="utf-8")
    assert '"persisted_response_payload_bytes": 0' in source
    assert '"semantic_labels_opened_or_used": False' in source
    assert '"v_plus_s_plus_a_claimed": False' in source
