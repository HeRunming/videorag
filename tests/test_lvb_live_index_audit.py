from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
import pytest

from tools import lvb_live_index_audit as audit


ROOT = Path(__file__).resolve().parents[1]


def tar_header(path: str, size: int, typeflag: bytes = b"0") -> bytes:
    block = bytearray(512)
    if "/" in path:
        prefix, name = path.rsplit("/", 1)
    else:
        prefix, name = "", path
    block[0 : len(name.encode())] = name.encode()
    block[100:108] = b"0000644\0"
    block[108:116] = b"0000000\0"
    block[116:124] = b"0000000\0"
    block[124:136] = f"{size:011o}\0".encode()
    block[136:148] = b"00000000000\0"
    block[148:156] = b"        "
    block[156:157] = typeflag
    block[257:263] = b"ustar\0"
    block[263:265] = b"00"
    block[345 : 345 + len(prefix.encode())] = prefix.encode()
    checksum = sum(block)
    block[148:156] = f"{checksum:06o}\0 ".encode()
    return bytes(block)


def test_repository_offline_audit_passes() -> None:
    result = audit.offline_audit(ROOT)
    assert result["status"] == "PASS"
    assert result["failures"] == []
    assert len(result["checks"]) == 26
    assert result["manifest"]["request_count"] == 13343
    assert result["manifest"]["response_body_bytes"] == 6830592
    assert len(result["geometry"]["videos"]) == 5
    assert len(result["geometry"]["subtitles"]) == 5


def test_independent_tar_parser_validates_name_size_type_and_checksum() -> None:
    block = tar_header("videos/example.mp4", 123)
    parsed = audit.parse_tar_header(block)
    assert parsed.path == "videos/example.mp4"
    assert parsed.size == 123
    assert parsed.typeflag == "0"
    assert parsed.stored_checksum == parsed.unsigned_checksum
    broken = bytearray(block)
    broken[8] ^= 1
    with pytest.raises(audit.AuditError, match="INVALID_TAR_HEADER_CHECKSUM"):
        audit.parse_tar_header(bytes(broken))


def test_secret_indicator_scan_catches_credentials_and_signed_urls() -> None:
    parsed = {
        "a": "Bearer not-safe",
        "b": "https://cdn.example/object?Policy=signed",
        "c": "https://user:password@example.test/object",
    }
    findings = audit.find_secret_indicators(str(parsed), parsed)
    assert "secret-pattern-1" in findings
    assert "url-query" in findings
    assert "url-userinfo" in findings


def test_mp4_and_json_prefix_classification() -> None:
    assert audit.mp4_prefix_result(b"\x00\x00\x00\x18ftypisom")["compatible"] is True
    assert audit.mp4_prefix_result(b"not an mp4")["compatible"] is False
    assert audit.json_prefix_result(b"\xef\xbb\xbf  [{\"x\":1}]")["json_like"] is True
    assert audit.json_prefix_result(b"WEBVTT")["json_like"] is False


def test_bounded_live_client_never_forwards_token_and_records_no_urls() -> None:
    seen: list[tuple[str, str | None, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(
            (
                request.url.host,
                request.headers.get("authorization"),
                str(request.url),
            )
        )
        if request.url.host == "huggingface.co":
            return httpx.Response(
                302,
                headers={
                    "location": "https://us.aws.cdn.hf.co/object?Policy=secret-value",
                    "content-length": "0",
                },
            )
        return httpx.Response(
            206,
            headers={
                "content-length": "8",
                "content-range": "bytes 0-7/100",
            },
            content=b"12345678",
        )

    raw_client = httpx.Client(
        transport=httpx.MockTransport(handler), follow_redirects=False
    )
    client = audit.BoundedLiveClient("unit-test-secret", client=raw_client)
    assert client.fetch("subtitles.tar", 0, 7, 100) == b"12345678"
    assert seen[0][1] == "Bearer unit-test-secret"
    assert seen[1][1] is None
    persisted = repr(client.redirects)
    assert "Policy" not in persisted
    assert "secret-value" not in persisted
    assert "unit-test-secret" not in persisted
    assert client.total_bytes == 8
    assert hashlib.sha256(b"12345678").hexdigest()
    client.close()


def test_bounded_live_client_rejects_complete_object() -> None:
    raw_client = httpx.Client(
        transport=httpx.MockTransport(lambda _: pytest.fail("must not request"))
    )
    client = audit.BoundedLiveClient("unit-test-secret", client=raw_client)
    with pytest.raises(
        audit.AuditError, match="LIVE_COMPLETE_OBJECT_RANGE_PROHIBITED"
    ):
        client.fetch("subtitles.tar", 0, 99, 100)
    client.close()


def test_full_live_spot_check_with_mocked_bounded_ranges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    offline = audit.offline_audit(ROOT)
    parts = audit.load_parts(audit.read_csv(ROOT / audit.PARTS_REL))
    video_rows = audit.read_csv(ROOT / audit.VIDEO_RANGES_REL)
    subtitle_rows = audit.read_csv(ROOT / audit.SUBTITLE_RANGES_REL)
    payloads: dict[tuple[str, int, int], bytes] = {}

    for row in video_rows:
        header_global = int(row["tar_header_global_offset"])
        data_global = int(row["tar_data_global_offset"])
        end_global = int(row["tar_end_global_offset"])
        size = int(row["member_size"])
        part = next(
            item for item in parts if item.start <= header_global <= item.end_inclusive
        )
        header_local = header_global - part.start
        data_local = data_global - part.start
        end_local = end_global - part.start
        payloads[(part.name, header_local, header_local + 511)] = tar_header(
            row["member_path"], size
        )
        payloads[(part.name, data_local, data_local + 63)] = (
            b"\x00\x00\x00\x18ftypisom" + b"\0" * 52
        )
        payloads[(part.name, end_local - 64, end_local - 1)] = b"z" * 64

    for row in subtitle_rows:
        header = int(row["tar_header_offset"])
        data = int(row["tar_data_offset"])
        end = int(row["tar_end_offset"])
        size = int(row["member_size"])
        payloads[("subtitles.tar", header, header + 511)] = tar_header(
            row["member_path"], size
        )
        payloads[("subtitles.tar", data, data + 63)] = b'[{"text":"ok"}]' + b" " * 49
        payloads[("subtitles.tar", end - 64, end - 1)] = b"}" * 64

    sizes = {part.name: part.size for part in parts}
    sizes["subtitles.tar"] = audit.EXPECTED_SUBTITLE_TAR_SIZE

    def handler(request: httpx.Request) -> httpx.Response:
        filename = request.url.path.rsplit("/", 1)[-1]
        start, end = map(
            int, request.headers["range"].removeprefix("bytes=").split("-")
        )
        body = payloads[(filename, start, end)]
        return httpx.Response(
            206,
            headers={
                "content-length": str(len(body)),
                "content-range": f"bytes {start}-{end}/{sizes[filename]}",
            },
            content=body,
        )

    monkeypatch.setattr("huggingface_hub.get_token", lambda: "mock-token")

    def factory(_: str) -> audit.BoundedLiveClient:
        return audit.BoundedLiveClient(
            "mock-token",
            client=httpx.Client(
                transport=httpx.MockTransport(handler), follow_redirects=False
            ),
        )

    result = audit.live_spot_check(ROOT, offline, client_factory=factory)
    assert result["status"] == "PASS"
    assert result["successful_range_responses"] == 30
    assert result["response_body_bytes"] == 6400
    assert len(result["observations"]) == 10
