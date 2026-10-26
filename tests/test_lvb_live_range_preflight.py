from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import httpx
import pytest

from tools import lvb_live_range_preflight as lvb


def tar_header(
    name: str,
    size: int = 0,
    *,
    typeflag: bytes = b"0",
    prefix: str = "",
    linkname: str = "",
) -> bytes:
    block = bytearray(512)

    def put(start: int, length: int, value: bytes) -> None:
        assert len(value) <= length
        block[start : start + len(value)] = value

    put(0, 100, name.encode())
    put(100, 8, b"0000644\0")
    put(108, 8, b"0000000\0")
    put(116, 8, b"0000000\0")
    put(124, 12, f"{size:011o}\0".encode())
    put(136, 12, b"00000000000\0")
    block[148:156] = b"        "
    put(156, 1, typeflag)
    put(157, 100, linkname.encode())
    put(257, 6, b"ustar\0")
    put(263, 2, b"00")
    put(345, 155, prefix.encode())
    checksum = sum(block)
    block[148:156] = f"{checksum:06o}\0 ".encode()
    return bytes(block)


def pad(body: bytes) -> bytes:
    return body + bytes((-len(body)) % 512)


def regular(path: str, body: bytes = b"data") -> bytes:
    if "/" in path:
        prefix, name = path.rsplit("/", 1)
        if len(name.encode()) <= 100 and len(prefix.encode()) <= 155:
            return tar_header(name, len(body), prefix=prefix) + pad(body)
    return tar_header(path, len(body)) + pad(body)


def pax_record(key: str, value: str) -> bytes:
    suffix = f" {key}={value}\n".encode()
    length = len(suffix) + 1
    while True:
        raw = str(length).encode() + suffix
        if len(raw) == length:
            return raw
        length = len(raw)


def pax_member(path: str, body: bytes = b"pax-data") -> bytes:
    metadata = pax_record("path", path)
    return tar_header("PaxHeader", len(metadata), typeflag=b"x") + pad(metadata) + regular("placeholder", body)


def gnu_long_member(path: str, body: bytes = b"gnu-data") -> bytes:
    long_body = path.encode() + b"\0"
    return tar_header("././@LongLink", len(long_body), typeflag=b"L") + pad(long_body) + regular("placeholder", body)


def archive(*members: bytes) -> bytes:
    return b"".join(members) + bytes(1024)


class MemoryReader:
    def __init__(self, data: bytes):
        self.data = data
        self.total_size = len(data)
        self.reads: list[tuple[int, int, str]] = []

    def read(self, start: int, length: int, purpose: str) -> bytes:
        self.reads.append((start, length, purpose))
        return self.data[start : start + length]


def test_valid_ustar_header_prefix_and_checksum() -> None:
    block = tar_header("clip.mp4", 123, prefix="nested/videos")
    parsed = lvb.parse_tar_header(block)
    assert parsed.path == "nested/videos/clip.mp4"
    assert parsed.size == 123
    assert parsed.stored_checksum == parsed.computed_checksum_unsigned
    broken = bytearray(block)
    broken[10] ^= 1
    with pytest.raises(lvb.TarFormatError, match="INVALID_TAR_HEADER_CHECKSUM"):
        lvb.parse_tar_header(bytes(broken))


def test_gnu_long_name_and_pax_path_override() -> None:
    gnu_name = "deep/" + "x" * 140 + "/target.mp4"
    pax_name = "pax/overridden/target.json"
    data = archive(gnu_long_member(gnu_name), pax_member(pax_name))
    result = lvb.SparseTarScanner(MemoryReader(data), {"target.mp4", "target.json"}, "fixture").scan()
    assert result.found["target.mp4"].member_path == gnu_name
    assert result.found["target.json"].member_path == pax_name
    assert result.metadata_bodies_read > 0


def test_crossing_multipart_payload_boundary_and_exact_ranges() -> None:
    data = bytes(range(256)) * 8
    parts = [
        lvb.Part(0, "videos.tar.part.aa", 700, 0, 699, "a" * 64, "evidence.json"),
        lvb.Part(1, "videos.tar.part.ab", len(data) - 700, 700, len(data) - 1, "b" * 64, "evidence.json"),
    ]
    blobs = {parts[0].name: data[:700], parts[1].name: data[700:]}
    calls = []

    def fetch(name: str, start: int, end: int, size: int, purpose: str) -> bytes:
        calls.append((name, start, end, size, purpose))
        return blobs[name][start : end + 1]

    reader = lvb.MultipartRangeReader(parts, fetch)
    assert reader.read(650, 200, "cross-boundary") == data[650:850]
    assert [(call[0], call[1], call[2]) for call in calls] == [
        ("videos.tar.part.aa", 650, 699),
        ("videos.tar.part.ab", 0, 149),
    ]
    ranges = lvb.compute_part_ranges(650, 200, parts)
    assert [item["http_range"] for item in ranges] == ["bytes=650-699", "bytes=0-149"]


def make_client(handler, *, max_response=lvb.MAX_RESPONSE_BYTES, allowed=lvb.ALLOWED_REDIRECT_HOST_SUFFIXES):
    transport = httpx.MockTransport(handler)
    raw_client = httpx.Client(transport=transport, follow_redirects=False)
    return lvb.SafeRangeClient(
        "unit-test-token",
        client=raw_client,
        budget=lvb.Budget(maximum_response_bytes=max_response, maximum_total_bytes=4096),
        allowed_redirect_host_suffixes=allowed,
    )


def test_exact_content_range_validation() -> None:
    def good(request: httpx.Request) -> httpx.Response:
        assert request.headers["range"] == "bytes=10-19"
        return httpx.Response(
            206,
            headers={"content-length": "10", "content-range": "bytes 10-19/100"},
            content=b"0123456789",
        )

    client = make_client(good)
    assert client.fetch_range("subtitles.tar", 10, 19, 100, "test") == b"0123456789"

    def bad(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            206,
            headers={"content-length": "10", "content-range": "bytes 11-20/100"},
            content=b"0123456789",
        )

    client = make_client(bad)
    with pytest.raises(lvb.SafetyError, match="MISMATCHED_CONTENT_RANGE"):
        client.fetch_range("subtitles.tar", 10, 19, 100, "test")


def test_rejects_range_ignored_with_200() -> None:
    client = make_client(lambda _: httpx.Response(200, headers={"content-length": "100"}, content=b"x" * 100))
    with pytest.raises(lvb.SafetyError, match="RANGE_IGNORED_FULL_OBJECT_200"):
        client.fetch_range("subtitles.tar", 0, 9, 100, "test")


def test_rejects_oversized_or_excess_body() -> None:
    client = make_client(
        lambda _: httpx.Response(
            206,
            headers={"content-length": "10", "content-range": "bytes 0-9/100"},
            content=b"x" * 11,
        )
    )
    with pytest.raises(lvb.SafetyError, match="RANGE_RESPONSE_EXCESS_BYTES"):
        client.fetch_range("subtitles.tar", 0, 9, 100, "test")

    client = make_client(lambda _: pytest.fail("transport must not be called"), max_response=8)
    with pytest.raises(lvb.SafetyError, match="REQUEST_EXCEEDS_RESPONSE_BODY_LIMIT"):
        client.fetch_range("subtitles.tar", 0, 9, 100, "test")


@pytest.mark.parametrize(
    "location,error",
    [
        ("http://huggingface.co/object", "NON_HTTPS_REQUEST_OR_REDIRECT"),
        ("https://evil.example/object", "REDIRECT_HOST_NOT_ALLOWED"),
        ("https://credential@cdn-lfs.huggingface.co/object", "URL_USERINFO_PROHIBITED"),
    ],
)
def test_rejects_unexpected_redirect_scheme_or_host(location: str, error: str) -> None:
    client = make_client(lambda _: httpx.Response(302, headers={"location": location, "content-length": "0"}))
    with pytest.raises(lvb.SafetyError, match=error):
        client.fetch_range("subtitles.tar", 0, 9, 100, "test")
    assert all("?" not in hop["location"] for hop in client.records[0].redirect_chain)


def test_allowed_redirect_records_hosts_strips_query_and_does_not_forward_token() -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.host, request.headers.get("authorization")))
        if request.url.host == "huggingface.co":
            return httpx.Response(
                302,
                headers={
                    "location": "https://cdn-lfs.huggingface.co/object?Policy=secret-signature",
                    "content-length": "0",
                },
            )
        return httpx.Response(
            206,
            headers={"content-length": "10", "content-range": "bytes 0-9/100"},
            content=b"0123456789",
        )

    client = make_client(handler)
    assert client.fetch_range("subtitles.tar", 0, 9, 100, "test") == b"0123456789"
    assert seen == [
        ("huggingface.co", "Bearer unit-test-token"),
        ("cdn-lfs.huggingface.co", None),
    ]
    record = client.records[0]
    assert record.effective_host == "cdn-lfs.huggingface.co"
    assert record.redirect_chain == [
        {
            "status_code": 302,
            "from_host": "huggingface.co",
            "to_host": "cdn-lfs.huggingface.co",
            "location": "https://cdn-lfs.huggingface.co/object",
        }
    ]


def test_one_canonical_redirect_then_multiple_cached_cdn_ranges() -> None:
    seen: list[tuple[str, str, str | None, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(
            (
                request.url.host,
                request.headers.get("range", ""),
                request.headers.get("authorization"),
                str(request.url),
            )
        )
        if request.url.host == "huggingface.co":
            return httpx.Response(
                302,
                headers={
                    "location": "https://us.aws.cdn.hf.co/object?Policy=secret-signature",
                    "content-length": "0",
                },
            )
        if request.method == "HEAD":
            return httpx.Response(200, headers={"content-length": "100"})
        start, end = map(int, request.headers["range"].removeprefix("bytes=").split("-"))
        return httpx.Response(
            206,
            headers={
                "content-length": str(end - start + 1),
                "content-range": f"bytes {start}-{end}/100",
            },
            content=bytes(range(start, end + 1)),
        )

    client = make_client(handler)
    client.head("subtitles.tar", 100, "first-head")
    assert client.fetch_range("subtitles.tar", 0, 9, 100, "first") == bytes(range(10))
    assert client.fetch_range("subtitles.tar", 10, 19, 100, "second") == bytes(range(10, 20))

    assert [host for host, *_ in seen] == [
        "huggingface.co",
        "us.aws.cdn.hf.co",
        "us.aws.cdn.hf.co",
        "us.aws.cdn.hf.co",
    ]
    assert [auth for host, _, auth, _ in seen if host == "huggingface.co"] == [
        "Bearer unit-test-token"
    ]
    assert all(auth is None for host, _, auth, _ in seen if host == "us.aws.cdn.hf.co")
    assert sum(record.redirect_chain != [] for record in client.records) == 1


def test_effective_url_cache_is_separate_per_repository_object() -> None:
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        filename = request.url.path.rsplit("/", 1)[-1]
        seen.append((request.url.host, filename))
        if request.url.host == "huggingface.co":
            return httpx.Response(
                302,
                headers={
                    "location": f"https://us.aws.cdn.hf.co/{filename}?Policy=secret-{filename}",
                    "content-length": "0",
                },
            )
        start, end = map(int, request.headers["range"].removeprefix("bytes=").split("-"))
        return httpx.Response(
            206,
            headers={
                "content-length": str(end - start + 1),
                "content-range": f"bytes {start}-{end}/100",
            },
            content=b"x" * (end - start + 1),
        )

    client = make_client(handler)
    client.fetch_range("videos.tar.part.aa", 0, 9, 100, "video")
    client.fetch_range("subtitles.tar", 0, 9, 100, "subtitle")
    client.fetch_range("videos.tar.part.aa", 10, 19, 100, "video-cached")
    client.fetch_range("subtitles.tar", 10, 19, 100, "subtitle-cached")
    assert seen == [
        ("huggingface.co", "videos.tar.part.aa"),
        ("us.aws.cdn.hf.co", "videos.tar.part.aa"),
        ("huggingface.co", "subtitles.tar"),
        ("us.aws.cdn.hf.co", "subtitles.tar"),
        ("us.aws.cdn.hf.co", "videos.tar.part.aa"),
        ("us.aws.cdn.hf.co", "subtitles.tar"),
    ]


def test_same_origin_relative_redirect_keeps_bearer_but_cache_does_not() -> None:
    seen: list[tuple[str, str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.host, request.url.path, request.headers.get("authorization")))
        if request.url.path.endswith("/subtitles.tar"):
            return httpx.Response(302, headers={"location": "/authorized/object", "content-length": "0"})
        return httpx.Response(
            206,
            headers={"content-length": "10", "content-range": "bytes 0-9/100"},
            content=b"0123456789",
        )

    client = make_client(handler)
    assert client.fetch_range("subtitles.tar", 0, 9, 100, "test") == b"0123456789"
    assert seen == [
        (
            "huggingface.co",
            f"/datasets/{lvb.REPOSITORY}/resolve/{lvb.REVISION}/subtitles.tar",
            "Bearer unit-test-token",
        ),
        ("huggingface.co", "/authorized/object", "Bearer unit-test-token"),
    ]


def test_cached_signed_url_expiry_triggers_one_safe_reresolution() -> None:
    calls: list[tuple[str, str | None, str]] = []
    canonical_resolutions = 0
    cdn_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal canonical_resolutions, cdn_calls
        calls.append((request.url.host, request.headers.get("authorization"), str(request.url)))
        if request.url.host == "huggingface.co":
            canonical_resolutions += 1
            return httpx.Response(
                302,
                headers={
                    "location": f"https://us.aws.cdn.hf.co/object?Policy=secret-{canonical_resolutions}",
                    "content-length": "0",
                },
            )
        cdn_calls += 1
        if cdn_calls == 2:
            return httpx.Response(403, headers={"content-length": "0"}, content=b"")
        start, end = map(int, request.headers["range"].removeprefix("bytes=").split("-"))
        return httpx.Response(
            206,
            headers={
                "content-length": str(end - start + 1),
                "content-range": f"bytes {start}-{end}/100",
            },
            content=bytes(range(start, end + 1)),
        )

    client = make_client(handler)
    assert client.fetch_range("subtitles.tar", 0, 9, 100, "first") == bytes(range(10))
    assert client.fetch_range("subtitles.tar", 10, 19, 100, "expired") == bytes(range(10, 20))
    assert client.fetch_range("subtitles.tar", 20, 29, 100, "new-cache") == bytes(range(20, 30))

    assert canonical_resolutions == 2
    assert [host for host, _, _ in calls] == [
        "huggingface.co",
        "us.aws.cdn.hf.co",
        "us.aws.cdn.hf.co",
        "huggingface.co",
        "us.aws.cdn.hf.co",
        "us.aws.cdn.hf.co",
    ]
    assert all(auth == "Bearer unit-test-token" for host, auth, _ in calls if host == "huggingface.co")
    assert all(auth is None for host, auth, _ in calls if host == "us.aws.cdn.hf.co")

    serialized = json.dumps([record.as_dict() for record in client.records], sort_keys=True)
    assert "Policy" not in serialized
    assert "secret-1" not in serialized
    assert "secret-2" not in serialized
    assert "unit-test-token" not in serialized
    assert all(not record.url_has_query for record in client.records)
    assert all(not record.credentials_or_query_secrets_recorded for record in client.records)


def test_cached_url_auth_failure_is_retried_only_once() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        if len(calls) == 1:
            return httpx.Response(
                302,
                headers={
                    "location": "https://us.aws.cdn.hf.co/object?Policy=expired",
                    "content-length": "0",
                },
            )
        if len(calls) == 2:
            return httpx.Response(
                206,
                headers={"content-length": "10", "content-range": "bytes 0-9/100"},
                content=b"0123456789",
            )
        if request.url.host == "huggingface.co":
            return httpx.Response(
                302,
                headers={
                    "location": "https://us.aws.cdn.hf.co/object?Policy=still-expired",
                    "content-length": "0",
                },
            )
        return httpx.Response(403, headers={"content-length": "0"}, content=b"")

    client = make_client(handler)
    assert client.fetch_range("subtitles.tar", 0, 9, 100, "prime") == b"0123456789"
    with pytest.raises(lvb.SafetyError, match="UNEXPECTED_RANGE_STATUS"):
        client.fetch_range("subtitles.tar", 10, 19, 100, "expired")
    assert calls == [
        "huggingface.co",
        "us.aws.cdn.hf.co",
        "us.aws.cdn.hf.co",
        "huggingface.co",
        "us.aws.cdn.hf.co",
    ]


def test_progress_output_has_required_fields_and_no_secrets() -> None:
    secret = "signed-super-secret"
    output = io.StringIO()
    client = make_client(lambda _: pytest.fail("progress must not make HTTP requests"))
    client.budget.total_bytes = 1536
    client._effective_url_cache[("canonical", 100)] = (
        f"https://us.aws.cdn.hf.co/object?Policy={secret}"
    )
    reporter = lvb.make_progress_reporter(client, output)
    data = archive(regular("other.bin"), regular("target.mp4"))
    reader = MemoryReader(data)
    scanner = lvb.SparseTarScanner(
        reader,
        {"target.mp4"},
        "videos.tar",
        progress_every=1,
        progress_callback=reporter,
    )
    scanner.scan()
    text = output.getvalue()
    assert "archive=videos.tar" in text
    assert "headers=1" in text
    assert "logical_offset=" in text
    assert "response_bytes=1536" in text
    assert "targets_found=1/1" in text
    assert secret not in text
    assert "Policy=" not in text
    assert "Authorization" not in text


def test_exact_matching_all_target_names() -> None:
    video_names = [f"{video_id}.mp4" for _, video_id in lvb.TARGETS]
    members = [regular(f"videos/{name}", name.encode()) for name in video_names]
    # Near matches must not satisfy or collide with exact basenames.
    members.insert(0, regular("videos/prefix-PgbM2MhcYQ.mp4", b"wrong"))
    members.insert(1, regular("videos/-PgbM2MhcYQ.mp4.bak", b"wrong"))
    result = lvb.SparseTarScanner(MemoryReader(archive(*members)), video_names, "videos").scan()
    assert set(result.found) == set(video_names)
    assert {Path(member.member_path).name for member in result.found.values()} == set(video_names)


def test_duplicate_target_after_all_targets_found_still_fails_closed() -> None:
    data = archive(regular("first/target.mp4"), regular("second/target.mp4"))
    with pytest.raises(lvb.TarFormatError, match="DUPLICATE_TARGET_MEMBER"):
        lvb.SparseTarScanner(MemoryReader(data), {"target.mp4"}, "fixture").scan()


def make_all_target_archives() -> tuple[bytes, bytes]:
    videos = archive(
        regular("unrelated.bin", b"skip" * 300),
        gnu_long_member("nested/" + "long/" * 24 + f"{lvb.TARGETS[0][1]}.mp4", b"v0"),
        pax_member(f"pax/{lvb.TARGETS[1][1]}.mp4", b"v1"),
        *[regular(f"videos/{video_id}.mp4", f"v{i}".encode()) for i, (_, video_id) in enumerate(lvb.TARGETS[2:], 2)],
    )
    subtitles = archive(
        *[regular(f"subtitles/{video_id}_en.json", b"{}") for _, video_id in lvb.TARGETS]
    )
    return videos, subtitles


def test_execute_redacts_token_and_dry_run_does_not_overwrite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "hf_super_secret_should_never_persist"
    videos, subtitles = make_all_target_archives()
    split = 1600  # cuts through an ordinary payload/padding region
    parts = [
        lvb.Part(0, "videos.tar.part.aa", split, 0, split - 1, "a" * 64, "fixture"),
        lvb.Part(1, "videos.tar.part.ab", len(videos) - split, split, len(videos) - 1, "b" * 64, "fixture"),
    ]
    blobs = {
        "videos.tar.part.aa": videos[:split],
        "videos.tar.part.ab": videos[split:],
        "subtitles.tar": subtitles,
    }
    evidence = {"id": lvb.REPOSITORY, "sha": lvb.REVISION, "gated": "auto"}
    evidence_path = tmp_path / lvb.EVIDENCE_REL
    evidence_path.parent.mkdir(parents=True)
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    monkeypatch.setattr(lvb, "load_official_inputs", lambda _: (parts, len(subtitles), evidence))
    monkeypatch.setattr("huggingface_hub.get_token", lambda: secret)

    def handler(request: httpx.Request) -> httpx.Response:
        name = request.url.path.rsplit("/", 1)[-1]
        if request.url.host == "huggingface.co":
            assert request.headers.get("authorization") == f"Bearer {secret}"
            return httpx.Response(
                302,
                headers={
                    "location": f"https://us.aws.cdn.hf.co/object/{name}?Policy=signed-output-secret",
                    "content-length": "0",
                },
            )
        assert request.url.host == "us.aws.cdn.hf.co"
        assert request.headers.get("authorization") is None
        blob = blobs[name]
        if request.method == "HEAD":
            return httpx.Response(200, headers={"content-length": str(len(blob)), "accept-ranges": "bytes"})
        start, end = map(int, request.headers["range"].removeprefix("bytes=").split("-"))
        body = blob[start : end + 1]
        return httpx.Response(
            206,
            headers={
                "content-length": str(len(body)),
                "content-range": f"bytes {start}-{end}/{len(blob)}",
                "accept-ranges": "bytes",
            },
            content=body,
        )

    def factory(token: str) -> lvb.SafeRangeClient:
        assert token == secret
        return lvb.SafeRangeClient(token, client=httpx.Client(transport=httpx.MockTransport(handler)))

    result = lvb.run_execute(tmp_path, client_factory=factory)
    assert result["conclusion"] == "GO"
    written = b"\n".join(path.read_bytes() for path in tmp_path.rglob("*") if path.is_file())
    assert secret.encode() not in written
    assert f"Bearer {secret}".encode() not in written
    assert b"signed-output-secret" not in written
    assert b"Policy=" not in written
    manifest = (tmp_path / lvb.MANIFEST_REL).read_bytes()
    before = manifest

    # Dry-run is read-only and must not replace a successful manifest.
    summary = lvb.dry_run(tmp_path)
    assert summary["outputs_written"] is False
    assert (tmp_path / lvb.MANIFEST_REL).read_bytes() == before

    with (tmp_path / lvb.VIDEO_RANGES_REL).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert {row["status"] for row in rows} == {"LOCATED_HEADER_ONLY"}
    assert {Path(row["member_path"]).name for row in rows} == {
        f"{video_id}.mp4" for _, video_id in lvb.TARGETS
    }
