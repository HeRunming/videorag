from __future__ import annotations

import json
import math
import re
import struct
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest

from tools import hf_audio_stream_preflight as preflight


def box(kind: bytes, payload: bytes = b"", *, extended: bool = False) -> bytes:
    if extended:
        return struct.pack(">I4sQ", 1, kind, 16 + len(payload)) + payload
    return struct.pack(">I4s", 8 + len(payload), kind) + payload


def fullbox_payload(version: int, body: bytes) -> bytes:
    return bytes([version, 0, 0, 0]) + body


def mvhd(duration_seconds: int, *, timescale: int = 1000, version: int = 0) -> bytes:
    duration = duration_seconds * timescale
    if version == 0:
        body = struct.pack(">IIII", 0, 0, timescale, duration) + bytes(80)
    else:
        body = struct.pack(">QQIQ", 0, 0, timescale, duration) + bytes(80)
    return box(b"mvhd", fullbox_payload(version, body))


def tkhd(duration_seconds: int, *, timescale: int = 1000, version: int = 0) -> bytes:
    duration = duration_seconds * timescale
    if version == 0:
        body = struct.pack(">IIIII", 0, 0, 1, 0, duration) + bytes(60)
    else:
        body = struct.pack(">QQIIQ", 0, 0, 1, 0, duration) + bytes(60)
    return box(b"tkhd", fullbox_payload(version, body))


def mdhd(duration_seconds: int, *, timescale: int, version: int = 0) -> bytes:
    duration = duration_seconds * timescale
    if version == 0:
        body = struct.pack(">IIII", 0, 0, timescale, duration) + bytes(4)
    else:
        body = struct.pack(">QQIQ", 0, 0, timescale, duration) + bytes(4)
    return box(b"mdhd", fullbox_payload(version, body))


def hdlr(handler: bytes) -> bytes:
    return box(b"hdlr", fullbox_payload(0, struct.pack(">I4s", 0, handler) + bytes(12)))


def trak(
    handler: bytes,
    duration_seconds: int,
    *,
    media_timescale: int,
    version: int = 0,
    extended: bool = False,
) -> bytes:
    mdia = box(
        b"mdia",
        mdhd(duration_seconds, timescale=media_timescale, version=version)
        + hdlr(handler),
        extended=extended,
    )
    return box(
        b"trak",
        tkhd(duration_seconds, version=version) + mdia,
        extended=extended,
    )


def mp4_fixture(
    duration_seconds: int = 1800,
    *,
    audio: bool = True,
    video: bool = True,
    extended: bool = False,
    version: int = 0,
) -> bytes:
    ftyp = box(b"ftyp", b"isom" + struct.pack(">I", 0) + b"isommp42", extended=extended)
    children = mvhd(duration_seconds, version=version)
    if video:
        children += trak(
            b"vide",
            duration_seconds,
            media_timescale=90_000,
            version=version,
            extended=extended,
        )
    if audio:
        children += trak(
            b"soun",
            duration_seconds,
            media_timescale=48_000,
            version=version,
            extended=extended,
        )
    return ftyp + box(b"moov", children, extended=extended)


def candidate(size: int = 100) -> preflight.Candidate:
    return preflight.Candidate.from_mapping(
        {
            "candidate_id": "ccp-005",
            "repo_id": "AnonymousFLARE/FLARE_demo",
            "revision": "a7e85c038a16b86afe1109b33cd131ec80d67cb3",
            "path": "sample_0/K759eXmaMTY.mp4",
            "size_bytes": size,
            "hash_algorithm": "sha256",
            "hash": "40737590a6b572791746bea7a87ac80c270cdd0750e9aae65b1eeed08232c7c1",
            "blob_id": "111fedd3c829f22e4cf4ab5e6f3183b661751973",
        }
    )


def mock_client(handler, *, response_limit: int = 1024, total_limit: int = 4096):
    transport = httpx.MockTransport(handler)
    raw = httpx.Client(transport=transport, follow_redirects=False)
    return preflight.SafeHFRangeClient(
        "unit-test-secret-token",
        clients=[raw],
        budget=preflight.Budget(
            maximum_response_bytes=response_limit,
            maximum_total_bytes=total_limit,
        ),
    )


def test_audio_video_duration_pass_and_declared_tracks() -> None:
    info = preflight.inspect_mp4_bytes(mp4_fixture())
    assert info.duration_seconds == 1800
    assert info.video_track_count == 1
    assert info.audio_track_count == 1
    assert info.av_timeline_relation == "PLAUSIBLY_SYNCHRONIZED"
    assert preflight.decide(info) == preflight.DECISION_GO


def test_video_only_is_no_go_no_audio() -> None:
    info = preflight.inspect_mp4_bytes(mp4_fixture(audio=False))
    assert info.video_track_count == 1
    assert info.audio_track_count == 0
    assert preflight.decide(info) == preflight.DECISION_NO_AUDIO


@pytest.mark.parametrize("seconds", [1199, 5401])
def test_duration_out_of_range(seconds: int) -> None:
    info = preflight.inspect_mp4_bytes(mp4_fixture(seconds))
    assert preflight.duration_gate(info.duration_seconds) == "FAIL"
    assert preflight.decide(info) == preflight.DECISION_DURATION


def test_64_bit_boxes_and_version_one_durations() -> None:
    info = preflight.inspect_mp4_bytes(
        mp4_fixture(2400, extended=True, version=1)
    )
    assert info.duration_seconds == 2400
    assert info.movie_timescale == 1000
    assert info.audio_track_count == info.video_track_count == 1


def test_malformed_sizes_fail_closed() -> None:
    malformed = struct.pack(">I4s", 4, b"ftyp") + bytes(8)
    with pytest.raises(preflight.ContainerError, match="BOX_SIZE_SMALLER_THAN_HEADER"):
        preflight.inspect_mp4_bytes(malformed)


def test_missing_moov_fails_closed() -> None:
    only_ftyp = box(b"ftyp", b"isom" + struct.pack(">I", 0) + b"isom")
    with pytest.raises(preflight.UnsupportedContainerError, match="MISSING_MOOV_BOX"):
        preflight.inspect_mp4_bytes(only_ftyp)


def test_fragmented_mp4_fails_closed() -> None:
    fragmented = mp4_fixture() + box(b"moof", box(b"traf"))
    with pytest.raises(
        preflight.UnsupportedContainerError,
        match="FRAGMENTED_MP4_MOOF_UNSUPPORTED",
    ):
        preflight.inspect_mp4_bytes(fragmented)


def test_range_response_ignored_with_200() -> None:
    client = mock_client(
        lambda _: httpx.Response(
            200, headers={"content-length": "100"}, content=b"x" * 100
        )
    )
    with pytest.raises(
        preflight.TransferValidationError, match="RANGE_IGNORED_FULL_OBJECT_200"
    ):
        client.fetch_range(candidate(), 0, 9, "test")


def test_complete_object_range_is_prohibited_before_transport() -> None:
    called = False

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(500)

    client = mock_client(handler)
    with pytest.raises(
        preflight.TransferValidationError,
        match="COMPLETE_OBJECT_RANGE_PROHIBITED",
    ):
        client.fetch_range(candidate(), 0, 99, "test")
    assert not called


def test_content_range_mismatch() -> None:
    client = mock_client(
        lambda _: httpx.Response(
            206,
            headers={
                "content-length": "10",
                "content-range": "bytes 1-10/100",
            },
            content=b"x" * 10,
        )
    )
    with pytest.raises(preflight.TransferValidationError, match="MISMATCHED_CONTENT_RANGE"):
        client.fetch_range(candidate(), 0, 9, "test")


def test_per_response_and_aggregate_body_limits() -> None:
    not_called = False

    def should_not_run(_: httpx.Request) -> httpx.Response:
        nonlocal not_called
        not_called = True
        return httpx.Response(500)

    client = mock_client(should_not_run, response_limit=8, total_limit=100)
    with pytest.raises(preflight.TransferValidationError, match="REQUEST_EXCEEDS_BODY_LIMIT"):
        client.fetch_range(candidate(), 0, 9, "test")
    assert not not_called

    def handler(request: httpx.Request) -> httpx.Response:
        start, end = map(
            int, request.headers["range"].removeprefix("bytes=").split("-")
        )
        return httpx.Response(
            206,
            headers={
                "content-length": str(end - start + 1),
                "content-range": f"bytes {start}-{end}/100",
            },
            content=b"x" * (end - start + 1),
        )

    client = mock_client(handler, response_limit=10, total_limit=15)
    assert client.fetch_range(candidate(), 0, 9, "first") == b"x" * 10
    with pytest.raises(preflight.TransferValidationError, match="AGGREGATE_BODY_LIMIT_EXCEEDED"):
        client.fetch_range(candidate(), 10, 19, "second")


def test_credential_and_signed_url_redaction() -> None:
    seen_authorization: list[tuple[str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_authorization.append(
            (request.url.host, request.headers.get("authorization"))
        )
        if request.url.host == "huggingface.co":
            return httpx.Response(
                302,
                headers={
                    "content-length": "0",
                    "location": (
                        "https://cdn-lfs.huggingface.co/object"
                        "?Policy=secret&Signature=also-secret"
                    ),
                },
            )
        return httpx.Response(
            206,
            headers={
                "content-length": "10",
                "content-range": "bytes 0-9/100",
            },
            content=b"0123456789",
        )

    client = mock_client(handler)
    assert client.fetch_range(candidate(), 0, 9, "redaction") == b"0123456789"
    assert seen_authorization == [
        ("huggingface.co", "Bearer unit-test-secret-token"),
        ("cdn-lfs.huggingface.co", None),
    ]
    serialized = json.dumps([record.as_dict() for record in client.records])
    assert "unit-test-secret-token" not in serialized
    assert "Policy" not in serialized
    assert "Signature" not in serialized
    assert "secret" not in serialized
    assert client.records[0].redirect_chain[0]["location"] == (
        "https://cdn-lfs.huggingface.co/object"
    )


def test_head_binds_revision_size_and_lfs_sha256() -> None:
    expected = candidate()

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "content-length": "100",
                "x-repo-commit": expected.revision,
                "x-linked-size": "100",
                "x-linked-etag": f'"{expected.hash}"',
            },
        )

    client = mock_client(handler)
    identity = client.head(expected)
    assert identity.matches
    assert identity.observed_sha256 == expected.hash


def test_box_guided_middle_moov_fetch_is_bounded() -> None:
    fixture = (
        box(b"ftyp", b"isom" + struct.pack(">I", 0) + b"isom")
        + box(b"free", bytes(600))
        + box(
            b"moov",
            mvhd(1800)
            + trak(b"vide", 1800, media_timescale=90_000)
            + trak(b"soun", 1800, media_timescale=48_000),
        )
        + box(b"free", bytes(800))
    )
    expected = candidate(len(fixture))
    ranges: list[tuple[int, int]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            return httpx.Response(
                200,
                headers={
                    "content-length": str(len(fixture)),
                    "x-repo-commit": expected.revision,
                    "x-linked-size": str(len(fixture)),
                    "x-linked-etag": expected.hash,
                },
            )
        start, end = map(
            int, request.headers["range"].removeprefix("bytes=").split("-")
        )
        ranges.append((start, end))
        return httpx.Response(
            206,
            headers={
                "content-length": str(end - start + 1),
                "content-range": f"bytes {start}-{end}/{len(fixture)}",
            },
            content=fixture[start : end + 1],
        )

    client = mock_client(handler, response_limit=1024, total_limit=4096)
    assert client.head(expected).matches
    info = preflight.locate_and_parse(expected, client, window_bytes=64)
    moov_start = 20 + 608
    assert info.audio_track_count == info.video_track_count == 1
    assert any(start <= moov_start < end + 1 for start, end in ranges)
    assert all(end - start + 1 <= 1024 for start, end in ranges)
    assert all((start, end) != (0, len(fixture) - 1) for start, end in ranges)


def test_ordered_route_failover_after_transport_failure() -> None:
    expected = candidate()

    def first(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("contains ?Signature=secret", request=request)

    def second(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "content-length": "100",
                "x-repo-commit": expected.revision,
                "x-linked-size": "100",
                "x-linked-etag": expected.hash,
            },
        )

    clients = [
        httpx.Client(transport=httpx.MockTransport(first)),
        httpx.Client(transport=httpx.MockTransport(second)),
    ]
    client = preflight.SafeHFRangeClient(
        "secret-token",
        clients=clients,
        budget=preflight.Budget(1024, 4096),
    )
    assert client.head(expected).matches
    serialized = json.dumps([record.as_dict() for record in client.records])
    assert "secret-token" not in serialized
    assert "Signature" not in serialized


def test_plan_is_exact_closed_allowlist_and_matches_csv() -> None:
    plan, candidates = preflight.load_plan()
    preflight.validate_source_csv(candidates)
    assert plan["schema_version"] == preflight.SCHEMA_VERSION
    assert [item.identity_dict() for item in candidates] == list(
        preflight.EXACT_CANDIDATES
    )
    raw = Path(preflight.PLAN_PATH).read_text(encoding="utf-8")
    assert "*" not in raw
    assert len(candidates) == 5


def test_live_result_matches_plan_and_is_internally_coherent() -> None:
    plan, candidates = preflight.load_plan()
    result = json.loads(Path(preflight.RESULT_PATH).read_text(encoding="utf-8"))

    assert result["schema_version"] == preflight.SCHEMA_VERSION
    assert result["plan_schema_version"] == plan["schema_version"]
    assert result["mode"] == "live_bounded_metadata_and_stream_headers"
    assert result["candidate_count"] == len(candidates) == 5
    assert re.fullmatch(
        r"2026-09-09T\d{2}:\d{2}:\d{2}Z", result["generated_at"]
    )
    assert [item["candidate_id"] for item in result["candidates"]] == [
        item.candidate_id for item in candidates
    ]

    expected = {item.candidate_id: item for item in candidates}
    requests: list[dict[str, object]] = []
    for item in result["candidates"]:
        candidate = expected[item["candidate_id"]]
        assert item["identity"] == candidate.identity_dict()
        assert item["range_request_count"] == sum(
            request["method"] == "GET" for request in item["requests"]
        )
        assert item["response_body_bytes"] == sum(
            request["bytes_received"] for request in item["requests"]
        )
        requests.extend(item["requests"])

        if item["container_parse_status"] != "PARSED_ISO_BMFF":
            assert item["decision"] == preflight.DECISION_IDENTITY
            assert item["duration_seconds"] is None
            assert item["duration_gate"] == "UNRESOLVED"
            assert item["video_track_count"] == item["audio_track_count"] == 0
            assert item["av_timeline_relation"] == "UNRESOLVED"
            continue

        tracks = tuple(preflight.TrackInfo(**track) for track in item["tracks"])
        assert item["video_track_count"] == sum(
            track.handler_type == "vide" for track in tracks
        )
        assert item["audio_track_count"] == sum(
            track.handler_type == "soun" for track in tracks
        )
        assert math.isclose(
            item["duration_seconds"],
            item["movie_duration_units"] / item["movie_timescale"],
        )
        for track in tracks:
            assert math.isclose(
                track.media_duration_seconds,
                track.media_duration_units / track.media_timescale,
            )
            if track.movie_duration_units is not None:
                assert track.movie_duration_seconds is not None
                assert math.isclose(
                    track.movie_duration_seconds,
                    track.movie_duration_units / item["movie_timescale"],
                )
        assert item["duration_gate"] == preflight.duration_gate(
            item["duration_seconds"]
        )
        assert item["av_timeline_relation"] == preflight.timeline_relation(
            tracks, item["duration_seconds"]
        )
        info = preflight.ContainerInfo(
            major_brand=item["major_brand"],
            compatible_brands=tuple(item["compatible_brands"]),
            duration_seconds=item["duration_seconds"],
            movie_timescale=item["movie_timescale"],
            movie_duration_units=item["movie_duration_units"],
            tracks=tracks,
            video_track_count=item["video_track_count"],
            audio_track_count=item["audio_track_count"],
            av_timeline_relation=item["av_timeline_relation"],
        )
        assert item["decision"] == preflight.decide(info)

    aggregate = result["aggregate"]
    assert aggregate["request_count"] == len(requests) == 9
    assert aggregate["range_request_count"] == sum(
        request["method"] == "GET" for request in requests
    ) == 4
    assert aggregate["response_body_bytes"] == sum(
        request["bytes_received"] for request in requests
    ) == 4_194_304
    assert aggregate["maximum_observed_response_bytes"] == max(
        request["bytes_received"] for request in requests
    )
    assert aggregate["decision_counts"] == {
        decision: count
        for decision, count in Counter(
            item["decision"] for item in result["candidates"]
        ).items()
    } | {
        decision: 0
        for decision in (
            preflight.DECISION_GO,
            preflight.DECISION_NO_AUDIO,
            preflight.DECISION_DURATION,
            preflight.DECISION_CONTAINER,
            preflight.DECISION_IDENTITY,
        )
        if decision not in {
            item["decision"] for item in result["candidates"]
        }
    }


def test_live_result_requests_are_bounded_and_secret_free() -> None:
    _, candidates = preflight.load_plan()
    result = json.loads(Path(preflight.RESULT_PATH).read_text(encoding="utf-8"))
    expected = {item.candidate_id: item for item in candidates}
    all_requests = [
        request
        for item in result["candidates"]
        for request in item["requests"]
    ]

    assert result["aggregate"]["response_body_bytes"] <= result["limits"][
        "aggregate_body_bytes"
    ]
    for item in result["candidates"]:
        assert item["response_body_bytes"] <= result["limits"][
            "per_candidate_body_bytes"
        ]
        assert item["range_request_count"] <= result["limits"][
            "per_candidate_range_request_count"
        ]

    for request in all_requests:
        candidate = expected[request["candidate_id"]]
        canonical = urlsplit(request["canonical_url"])
        assert not canonical.query
        assert not canonical.fragment
        assert canonical.username is canonical.password is None
        for redirect in request["redirect_chain"]:
            location = urlsplit(redirect["location"])
            assert not location.query
            assert not location.fragment
            assert location.username is location.password is None

        serialized = json.dumps(request).lower()
        assert "authorization" not in serialized
        assert "bearer " not in serialized
        assert "hf_token" not in serialized
        assert "signature=" not in serialized
        assert "policy=" not in serialized
        assert "credential=" not in serialized

        if request["method"] == "HEAD":
            assert request["bytes_received"] == 0
            continue

        assert request["method"] == "GET"
        assert request["response_status"] == 206
        match = re.fullmatch(
            r"bytes=(\d+)-(\d+)", request["requested_range"]
        )
        assert match is not None
        start, end = map(int, match.groups())
        length = end - start + 1
        assert (start, end) != (0, candidate.size_bytes - 1)
        assert length == request["bytes_received"] == request["content_length"]
        assert length <= result["limits"]["per_request_body_bytes"]
        assert request["content_range"] == (
            f"bytes {start}-{end}/{candidate.size_bytes}"
        )
        assert re.fullmatch(r"[0-9a-f]{64}", request["body_sha256"])
