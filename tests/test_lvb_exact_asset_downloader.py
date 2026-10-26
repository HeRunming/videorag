from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import httpx
import pytest

from tools import lvb_exact_asset_downloader as lvb


REPO_ROOT = Path(__file__).resolve().parents[1]


def tar_header(path: str, size: int, *, typeflag: bytes = b"0") -> bytes:
    header = bytearray(512)

    def field(offset: int, length: int, value: bytes) -> None:
        assert len(value) <= length
        header[offset : offset + len(value)] = value

    encoded = path.encode("utf-8")
    assert len(encoded) <= 100
    field(0, 100, encoded)
    field(100, 8, b"0000600\0")
    field(108, 8, b"0000000\0")
    field(116, 8, b"0000000\0")
    field(124, 12, f"{size:011o}\0".encode("ascii"))
    field(136, 12, b"00000000000\0")
    field(148, 8, b"        ")
    field(156, 1, typeflag)
    field(257, 6, b"ustar\0")
    field(263, 2, b"00")
    checksum = sum(header)
    field(148, 8, f"{checksum:06o}\0 ".encode("ascii"))
    return bytes(header)


def small_target(payload: bytes, *, kind: str = "subtitle") -> dict:
    basename = "-PgbM2MhcYQ_en.json" if kind == "subtitle" else "-PgbM2MhcYQ.mp4"
    member_path = f"{'subtitles' if kind == 'subtitle' else 'videos'}/{basename}"
    return {
        "kind": kind,
        "candidate_id": "fixture",
        "video_id": "-PgbM2MhcYQ",
        "basename": basename,
        "member_path": member_path,
        "size": len(payload),
        "destination": (
            f"raw/subtitles/{basename}" if kind == "subtitle" else f"raw/videos/{basename}"
        ),
        "source_object": "subtitles.tar" if kind == "subtitle" else "videos.tar.part.aa",
        "source_object_size": 4096,
        "source_object_lfs_sha256": "a" * 64,
        "header_range": {"start": 512, "end_inclusive": 1023, "length": 512},
        "payload_intervals": [
            {"start": 1024, "end_inclusive": 1024 + len(payload) - 1, "length": len(payload)}
        ],
    }


class FixtureFetcher:
    def __init__(self, target: dict, payload: bytes) -> None:
        self.target = target
        self.payload = payload
        self.calls: list[tuple[str, int, int, int, str]] = []

    def fetch_range(
        self, filename: str, start: int, end: int, expected_object_size: int, purpose: str
    ) -> bytes:
        self.calls.append((filename, start, end, expected_object_size, purpose))
        assert filename == self.target["source_object"]
        assert expected_object_size == self.target["source_object_size"]
        if (start, end) == (
            self.target["header_range"]["start"],
            self.target["header_range"]["end_inclusive"],
        ):
            return tar_header(self.target["member_path"], self.target["size"])
        interval = self.target["payload_intervals"][0]
        assert interval["start"] <= start <= end <= interval["end_inclusive"]
        relative_start = start - interval["start"]
        return self.payload[relative_start : relative_start + end - start + 1]


def test_frozen_plan_exact_totals_and_geometry() -> None:
    plan, digest = lvb.validate_frozen_plan(REPO_ROOT)
    assert digest == "cdd7f2661ad895e9e71c238be8d511f6513ed8ab08abd8a92a9c387fcd3cf08f"
    assert [target["basename"] for target in plan["targets"]] == list(lvb.ALLOWLIST)
    assert sum(target["size"] for target in plan["targets"]) == 581_129_056
    assert sum(target["size"] for target in plan["targets"] if target["kind"] == "video") == 580_719_669
    assert sum(target["size"] for target in plan["targets"] if target["kind"] == "subtitle") == 409_387
    for target in plan["targets"]:
        assert target["header_range"]["length"] == 512
        assert target["header_range"]["end_inclusive"] + 1 == target["payload_intervals"][0]["start"]
        assert target["payload_intervals"][0]["length"] == target["size"]
        assert target["payload_intervals"][0]["end_inclusive"] < target["source_object_size"]


def test_dry_run_is_offline_read_only_and_authorized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        __import__("sys").modules,
        "huggingface_hub",
        type("Trap", (), {"get_token": staticmethod(lambda: pytest.fail("token read in dry-run"))}),
    )
    result = lvb.dry_run(REPO_ROOT)
    assert result["status"] == "READY_FOR_EXACT_ACQUISITION"
    assert result["network_attempted"] is False
    assert result["credentials_read"] is False
    assert result["outputs_written"] is False


def test_tar_header_checks_checksum_path_type_size_and_data_offset() -> None:
    payload = b"[]"
    target = small_target(payload)
    parsed = lvb.validate_tar_header(tar_header(target["member_path"], len(payload)), target)
    assert parsed["checksum_valid"] is True
    assert parsed["path"] == target["member_path"]
    assert parsed["data_offset"] == 1024

    damaged = bytearray(tar_header(target["member_path"], len(payload)))
    damaged[10] ^= 1
    with pytest.raises(lvb.TarHeaderError, match="TAR_CHECKSUM_MISMATCH"):
        lvb.validate_tar_header(bytes(damaged), target)

    with pytest.raises(lvb.TarHeaderError, match="TAR_MEMBER_PATH_MISMATCH"):
        lvb.validate_tar_header(tar_header("subtitles/wrong.json", len(payload)), target)
    with pytest.raises(lvb.TarHeaderError, match="TAR_MEMBER_NOT_REGULAR_FILE"):
        lvb.validate_tar_header(tar_header(target["member_path"], len(payload), typeflag=b"2"), target)
    with pytest.raises(lvb.TarHeaderError, match="TAR_DECLARED_SIZE_MISMATCH"):
        lvb.validate_tar_header(tar_header(target["member_path"], len(payload) + 1), target)

    shifted = json.loads(json.dumps(target))
    shifted["payload_intervals"][0]["start"] += 1
    with pytest.raises(lvb.TarHeaderError, match="TAR_DATA_OFFSET_MISMATCH"):
        lvb.validate_tar_header(tar_header(target["member_path"], len(payload)), shifted)


def make_http_client(handler, *, maximum_total: int = 4096) -> lvb.SafeRangeClient:
    raw = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    return lvb.SafeRangeClient(
        "unit-test-secret",
        client=raw,
        budget=lvb.WireBudget(maximum_response_bytes=64, maximum_total_bytes=maximum_total),
    )


def test_safe_client_exact_206_cdn_cache_and_bearer_scope() -> None:
    seen: list[tuple[str, str | None, str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(
            (
                request.url.host,
                request.headers.get("authorization"),
                request.headers["range"],
                str(request.url),
            )
        )
        if request.url.host == "huggingface.co":
            return httpx.Response(
                302,
                headers={
                    "location": "https://us.aws.cdn.hf.co/object?Policy=never-persist-this",
                    "content-length": "0",
                },
            )
        start, end = map(int, request.headers["range"].removeprefix("bytes=").split("-"))
        return httpx.Response(
            206,
            headers={
                "content-length": str(end - start + 1),
                "content-range": f"bytes {start}-{end}/100",
                "content-encoding": "identity",
            },
            content=bytes(range(start, end + 1)),
        )

    client = make_http_client(handler)
    assert client.fetch_range("subtitles.tar", 10, 19, 100, "first") == bytes(range(10, 20))
    assert client.fetch_range("subtitles.tar", 20, 29, 100, "second") == bytes(range(20, 30))
    assert [item[0] for item in seen] == [
        "huggingface.co",
        "us.aws.cdn.hf.co",
        "us.aws.cdn.hf.co",
    ]
    assert seen[0][1] == "Bearer unit-test-secret"
    assert seen[1][1] is None and seen[2][1] is None
    assert not hasattr(client, "records")


def test_safe_client_rejects_full_object_bad_range_and_oversize() -> None:
    client = make_http_client(lambda _: pytest.fail("transport must not be called"))
    with pytest.raises(lvb.SafetyError, match="COMPLETE_ARCHIVE"):
        client.fetch_range("subtitles.tar", 0, 99, 100, "bad")
    with pytest.raises(lvb.SafetyError, match="REQUEST_EXCEEDS_8_MIB"):
        client.fetch_range("subtitles.tar", 0, lvb.MAX_RESPONSE_BYTES, lvb.MAX_RESPONSE_BYTES + 2, "bad")

    client = make_http_client(
        lambda _: httpx.Response(
            206,
            headers={"content-length": "10", "content-range": "bytes 11-20/100"},
            content=b"x" * 10,
        )
    )
    with pytest.raises(lvb.SafetyError, match="MISMATCHED_CONTENT_RANGE"):
        client.fetch_range("subtitles.tar", 10, 19, 100, "bad")


def test_subtitle_download_chunks_fsync_atomic_sidecar_and_skip(tmp_path: Path) -> None:
    payload = b'[{"start": 0, "text": "hello"}]\n'
    target = small_target(payload)
    plan = {
        "plan_id": "fixture",
        "staging_root": "data/restricted/lvb01",
        "limits": {"chunk_bytes": 8},
        "targets": [target],
    }
    fetcher = FixtureFetcher(target, payload)
    progress = io.StringIO()
    acquirer = lvb.Acquirer(
        tmp_path,
        plan,
        "b" * 64,
        fetcher,
        progress_stream=progress,
        chunk_bytes=8,
    )
    result = acquirer.acquire_target(target, 1, 1)
    assert result["status"] == "downloaded"
    destination = tmp_path / "data/restricted/lvb01/raw/subtitles" / target["basename"]
    metadata_path = destination.with_name(destination.name + ".metadata.json")
    assert destination.read_bytes() == payload
    metadata = json.loads(metadata_path.read_text())
    assert metadata["sha256"] == hashlib.sha256(payload).hexdigest()
    assert metadata["content_validation"]["top_level_type"] == "array"
    assert not destination.with_name(destination.name + ".partial").exists()
    assert not destination.with_name(destination.name + ".partial.json").exists()
    assert fetcher.calls[0][1:3] == (512, 1023)
    assert all(end - start + 1 <= 8 for _, start, end, _, purpose in fetcher.calls if purpose.startswith("payload:"))

    second_fetcher = FixtureFetcher(target, payload)
    skipped = lvb.Acquirer(
        tmp_path,
        plan,
        "b" * 64,
        second_fetcher,
        progress_stream=io.StringIO(),
        chunk_bytes=8,
    ).acquire_target(target, 1, 1)
    assert skipped["status"] == "skipped_verified"
    assert second_fetcher.calls == []


def test_resume_requires_exact_boundary_binding_and_prefix_hash(tmp_path: Path) -> None:
    payload = b'[{"text":"resume-test"}]\n'
    target = small_target(payload)
    plan = {
        "plan_id": "fixture",
        "staging_root": "data/restricted/lvb01",
        "limits": {"chunk_bytes": 8},
        "targets": [target],
    }
    destination = tmp_path / "data/restricted/lvb01/raw/subtitles" / target["basename"]
    destination.parent.mkdir(parents=True)
    partial = destination.with_name(destination.name + ".partial")
    state_path = destination.with_name(destination.name + ".partial.json")
    prefix = payload[:8]
    partial.write_bytes(prefix)
    state = lvb._target_binding(target, "c" * 64, 8)
    state.update({"completed_bytes": 8, "prefix_sha256": hashlib.sha256(prefix).hexdigest()})
    state_path.write_bytes(lvb.canonical_json_bytes(state))

    fetcher = FixtureFetcher(target, payload)
    result = lvb.Acquirer(
        tmp_path,
        plan,
        "c" * 64,
        fetcher,
        progress_stream=io.StringIO(),
        chunk_bytes=8,
    ).acquire_target(target, 1, 1)
    assert result["status"] == "downloaded"
    payload_calls = [call for call in fetcher.calls if call[-1].startswith("payload:")]
    assert payload_calls[0][1] == target["payload_intervals"][0]["start"] + 8

    # A non-boundary partial is never truncated or appended to.
    other_root = tmp_path / "other"
    bad_destination = other_root / "data/restricted/lvb01/raw/subtitles" / target["basename"]
    bad_destination.parent.mkdir(parents=True)
    bad_partial = bad_destination.with_name(bad_destination.name + ".partial")
    bad_state_path = bad_destination.with_name(bad_destination.name + ".partial.json")
    bad_prefix = payload[:7]
    bad_partial.write_bytes(bad_prefix)
    bad_state = lvb._target_binding(target, "c" * 64, 8)
    bad_state.update({"completed_bytes": 7, "prefix_sha256": hashlib.sha256(bad_prefix).hexdigest()})
    bad_state_path.write_bytes(lvb.canonical_json_bytes(bad_state))
    with pytest.raises(lvb.SafetyError, match="PARTIAL_NOT_ON_EXACT_CHUNK_BOUNDARY"):
        lvb.Acquirer(
            other_root,
            plan,
            "c" * 64,
            FixtureFetcher(target, payload),
            progress_stream=io.StringIO(),
            chunk_bytes=8,
        ).acquire_target(target, 1, 1)


def test_existing_completed_file_fails_closed_on_hash_or_sidecar_problem(tmp_path: Path) -> None:
    payload = b"[]"
    target = small_target(payload)
    plan = {
        "plan_id": "fixture",
        "staging_root": "data/restricted/lvb01",
        "limits": {"chunk_bytes": 8},
        "targets": [target],
    }
    destination = tmp_path / "data/restricted/lvb01/raw/subtitles" / target["basename"]
    destination.parent.mkdir(parents=True)
    destination.write_bytes(payload)
    acquirer = lvb.Acquirer(
        tmp_path,
        plan,
        "d" * 64,
        FixtureFetcher(target, payload),
        progress_stream=io.StringIO(),
        chunk_bytes=8,
    )
    with pytest.raises(lvb.SafetyError, match="EXISTING_TARGET_WITHOUT_METADATA"):
        acquirer.acquire_target(target, 1, 1)

    metadata = lvb._completed_static_metadata(target, "d" * 64, 8)
    metadata["sha256"] = "0" * 64
    destination.with_name(destination.name + ".metadata.json").write_bytes(
        lvb.canonical_json_bytes(metadata)
    )
    with pytest.raises(lvb.SafetyError, match="COMPLETED_TARGET_SIZE_OR_HASH_MISMATCH"):
        acquirer.acquire_target(target, 1, 1)


def test_content_magic_validation(tmp_path: Path) -> None:
    mp4 = tmp_path / "ok.mp4"
    mp4.write_bytes(
        (24).to_bytes(4, "big")
        + b"ftyp"
        + b"isom"
        + (0).to_bytes(4, "big")
        + b"isom"
        + b"mp42"
    )
    assert lvb.validate_mp4(mp4)["major_brand"] == "isom"
    mp4.write_bytes(b"not an mp4")
    with pytest.raises(lvb.ContentValidationError):
        lvb.validate_mp4(mp4)

    subtitle = tmp_path / "sub.json"
    subtitle.write_bytes(b"\xef\xbb\xbf{\"items\": []}")
    assert lvb.validate_subtitle_json(subtitle)["encoding"] == "utf-8-bom"
    subtitle.write_bytes(b"\xff")
    with pytest.raises(lvb.ContentValidationError, match="SUBTITLE_NOT_UTF8"):
        lvb.validate_subtitle_json(subtitle)
