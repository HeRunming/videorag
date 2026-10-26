from __future__ import annotations

import importlib.util
import json
import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/captaincook4d_25_109_bounded_av_probe.py"


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "captaincook4d_25_109_bounded_av_probe", TOOL_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def box(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", len(payload) + 8, kind) + payload


def fullbox(version: int, payload: bytes) -> bytes:
    return bytes([version, 0, 0, 0]) + payload


def mvhd(timescale: int, duration: int) -> bytes:
    payload = fullbox(
        0,
        struct.pack(">IIII", 0, 0, timescale, duration)
        + b"\x00" * 80,
    )
    return box(b"mvhd", payload)


def tkhd(track_id: int, duration: int, width: int, height: int) -> bytes:
    payload = fullbox(
        0,
        struct.pack(">IIIII", 0, 0, track_id, 0, duration)
        + b"\x00" * 60
        + struct.pack(">II", width << 16, height << 16),
    )
    return box(b"tkhd", payload)


def mdhd(timescale: int, duration: int) -> bytes:
    return box(
        b"mdhd",
        fullbox(
            0,
            struct.pack(">IIIIH", 0, 0, timescale, duration, 0)
            + b"\x00\x00",
        ),
    )


def hdlr(handler: bytes) -> bytes:
    return box(b"hdlr", fullbox(0, b"\x00" * 4 + handler + b"\x00" * 12))


def stsd_video() -> bytes:
    entry_payload = (
        b"\x00" * 24
        + struct.pack(">HH", 640, 360)
        + b"\x00" * 42
    )
    entry = box(b"avc1", entry_payload)
    return box(b"stsd", fullbox(0, struct.pack(">I", 1) + entry))


def stsd_audio() -> bytes:
    entry_payload = (
        b"\x00" * 16
        + struct.pack(">HHHHI", 2, 16, 0, 0, 48000 << 16)
        + b"\x00" * 8
    )
    entry = box(b"mp4a", entry_payload)
    return box(b"stsd", fullbox(0, struct.pack(">I", 1) + entry))


def trak(
    track_id: int,
    handler: bytes,
    movie_duration: int,
    media_timescale: int,
    media_duration: int,
) -> bytes:
    sample_description = stsd_video() if handler == b"vide" else stsd_audio()
    stbl = box(b"stbl", sample_description)
    minf = box(b"minf", stbl)
    mdia = box(
        b"mdia",
        mdhd(media_timescale, media_duration) + hdlr(handler) + minf,
    )
    dimensions = (640, 360) if handler == b"vide" else (0, 0)
    return box(
        b"trak",
        tkhd(track_id, movie_duration, *dimensions) + mdia,
    )


def synthetic_mp4(total: int = 20 * 1024 * 1024) -> bytes:
    movie_timescale = 1000
    duration = 2_126_960
    moov = box(
        b"moov",
        mvhd(movie_timescale, duration)
        + trak(1, b"vide", duration, 90000, 191_426_400)
        + trak(2, b"soun", duration, 48000, 102_094_080),
    )
    ftyp = box(b"ftyp", b"isom\x00\x00\x00\x00isom")
    mdat_size = total - len(ftyp) - len(moov)
    assert mdat_size >= 8
    mdat = struct.pack(">I4s", mdat_size, b"mdat") + b"\x00" * (mdat_size - 8)
    return ftyp + mdat + moov


def test_local_identity_pins_exact_gopro_asset() -> None:
    tool = load_tool()
    local = tool.validate_local_identity()

    assert local["record"]["recording_id"] == "25_109"
    assert local["record"]["source_group_id"] == "cc4d_p05_e07"
    assert local["record"]["official_url"] == tool.OFFICIAL_URL
    assert tool.BOX_SHARED_STATIC_ID in tool.OFFICIAL_URL


def test_content_range_is_strict() -> None:
    tool = load_tool()
    assert tool.parse_content_range("bytes 1-9/100") == (1, 9, 100)
    with pytest.raises(tool.RangeRejected):
        tool.parse_content_range("bytes */100")
    with pytest.raises(tool.RangeRejected):
        tool.parse_content_range("bytes 0-100/100")


def test_range_ignored_fails_before_body_read() -> None:
    tool = load_tool()

    class Response:
        def __init__(self) -> None:
            self.status_code = 200
            self.history = []
            self.url = tool.OFFICIAL_URL
            self.headers = {
                "Content-Type": "video/mp4",
                "Content-Length": "999999",
            }

        def iter_content(self, chunk_size: int):
            raise AssertionError("body must not be read")

    with pytest.raises(tool.RangeRejected, match="RANGE_STATUS_NOT_206"):
        tool.validate_range_headers(
            Response(),
            expected_start=0,
            expected_end=0,
            expected_total=None,
        )


def test_iso_parser_extracts_native_av_and_shared_timeline(
    tmp_path: Path,
) -> None:
    tool = load_tool()
    raw = synthetic_mp4()
    path = tmp_path / "synthetic.mp4"
    path.write_bytes(raw)

    parsed = tool.parse_iso_bmff(
        path,
        total=len(raw),
        intervals=[(0, len(raw))],
    )

    assert parsed["movie"]["duration_seconds"] == pytest.approx(2126.96)
    assert parsed["video"]["codec"] == "h264"
    assert parsed["video"]["width"] == 640
    assert parsed["video"]["height"] == 360
    assert parsed["audio"]["codec"] == "aac"
    assert parsed["audio"]["channels"] == 2
    assert parsed["audio"]["sample_rate_hz"] == 48000
    assert parsed["shared_timeline"]["same_moov_movie_timeline"] is True
    assert parsed["shared_timeline"]["absolute_start_delta_seconds"] == 0


def test_sparse_parser_never_reads_unpersisted_mdat(tmp_path: Path) -> None:
    tool = load_tool()
    raw = synthetic_mp4()
    head = tool.HEAD_WINDOW_BYTES
    tail = len(raw) - tool.TAIL_WINDOW_BYTES
    path = tmp_path / "sparse.mp4"
    with path.open("w+b") as handle:
        handle.truncate(len(raw))
        handle.seek(0)
        handle.write(raw[:head])
        handle.seek(tail)
        handle.write(raw[tail:])

    parsed = tool.parse_iso_bmff(
        path,
        total=len(raw),
        intervals=[(0, head), (tail, len(raw))],
    )
    assert parsed["moov"]["offset"] >= tail
    assert parsed["audio"]["sample_rate_hz"] == 48000


def test_budget_is_exactly_16_mib() -> None:
    tool = load_tool()
    assert tool.HEAD_WINDOW_BYTES + tool.TAIL_WINDOW_BYTES == 16 * 1024 * 1024
    assert (
        tool.HEAD_WINDOW_BYTES + tool.TAIL_WINDOW_BYTES
        == tool.MAX_PERSISTED_RESPONSE_BYTES
    )


def test_proxy_failure_preserves_attempt_evidence(monkeypatch) -> None:
    tool = load_tool()
    calls = []

    def reject(*args, **kwargs):
        calls.append(kwargs["proxy"])
        raise tool.RangeRejected("synthetic rejection")

    monkeypatch.setattr(tool, "request_range", reject)
    with pytest.raises(tool.ProxySelectionFailed) as raised:
        tool.choose_proxy(object())

    assert calls == [tool.PRIMARY_PROXY, tool.FALLBACK_PROXY]
    assert [item["proxy_name"] for item in raised.value.attempts] == [
        "https://proxy.example.invalid:3128",
        "https://proxy.example.invalid:3128-fallback",
    ]
    assert all(
        item["accepted_body_bytes"] == 0
        for item in raised.value.attempts
    )


def test_offline_cli_report_is_fail_closed(tmp_path: Path, monkeypatch) -> None:
    tool = load_tool()
    output = tmp_path / "report.json"
    monkeypatch.setattr(sys, "argv", [str(TOOL_PATH), "--output", str(output)])

    assert tool.main() == 1
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["final_marker"] == tool.REPAIR
    assert report["scope"]["network_requests"] == 0
    assert report["policy"]["semantic_annotations_opened"] is False
    assert report["policy"]["v_plus_s_plus_a_asserted"] is False
