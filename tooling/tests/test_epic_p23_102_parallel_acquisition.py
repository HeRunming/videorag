from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Self

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools/epic_p23_102_parallel_acquisition.py"
SPEC = importlib.util.spec_from_file_location(
    "epic_p23_102_parallel_acquisition", MODULE_PATH
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def configure_small_asset(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    expected_bytes: int = 20,
    alignment_bytes: int = 4,
    segment_bytes: int = 4,
) -> dict[str, Path]:
    base = tmp_path / "restricted"
    staging = base / "staging"
    segment_dir = staging / "parallel_segments"
    paths = {
        "base": base,
        "staging": staging,
        "segments": segment_dir,
        "part": staging / "P23_102.MP4.part",
        "final": base / "media/P23/P23_102.MP4",
        "manifest": segment_dir / "manifest.json",
        "parallel_lock": staging / ".parallel_acquisition.lock",
        "canonical_lock": staging / ".acquisition.lock",
        "journal": base / "logs/range_attempts.jsonl",
    }
    monkeypatch.setattr(MODULE, "BASE", paths["base"])
    monkeypatch.setattr(MODULE, "STAGING_DIR", paths["staging"])
    monkeypatch.setattr(MODULE, "SEGMENT_DIR", paths["segments"])
    monkeypatch.setattr(MODULE, "PART_MEDIA", paths["part"])
    monkeypatch.setattr(MODULE, "FINAL_MEDIA", paths["final"])
    monkeypatch.setattr(MODULE, "SEGMENT_MANIFEST", paths["manifest"])
    monkeypatch.setattr(MODULE, "PARALLEL_LOCK_FILE", paths["parallel_lock"])
    monkeypatch.setattr(MODULE, "CANONICAL_LOCK_FILE", paths["canonical_lock"])
    monkeypatch.setattr(MODULE, "JOURNAL_FILE", paths["journal"])
    monkeypatch.setattr(MODULE, "EXPECTED_BYTES", expected_bytes)
    monkeypatch.setattr(MODULE, "ALIGNMENT_BYTES", alignment_bytes)
    monkeypatch.setattr(MODULE, "SEGMENT_BYTES", segment_bytes)
    monkeypatch.setattr(MODULE, "FREE_SPACE_MARGIN_BYTES", 0)
    MODULE.secure_parallel_directories()
    return paths


def response_blocks(
    start: int,
    end: int,
    *,
    total: int,
    etag: str | None = MODULE.EXPECTED_ETAG,
    status: int = 206,
    content_length: int | None = None,
) -> list[dict]:
    headers = {
        "content-range": f"bytes {start}-{end}/{total}",
        "content-length": str(
            end - start + 1 if content_length is None else content_length
        ),
        "content-type": "video/mp4",
    }
    if etag is not None:
        headers["etag"] = etag
    return [{"status_code": status, "headers": headers}]


def prefix_snapshot(
    paths: dict[str, Path],
    payload: bytes,
) -> MODULE.PrefixSnapshot:
    paths["part"].write_bytes(payload)
    return MODULE.snapshot_prefix()


def complete_segment(
    store: MODULE.ManifestStore,
    segment: MODULE.Segment,
    payload: bytes,
) -> None:
    assert len(payload) == segment.byte_count
    segment.path.write_bytes(payload)
    record = store.data["segments"][segment.key]
    record.update(
        {
            "status": "complete",
            "etag": MODULE.EXPECTED_ETAG,
            "sha256": MODULE.hashlib.sha256(payload).hexdigest(),
            "observed_bytes": len(payload),
        }
    )
    store.data["object_etag"] = MODULE.EXPECTED_ETAG


def test_validate_prefix_accepts_arbitrary_incomplete_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = configure_small_asset(monkeypatch, tmp_path)
    paths["part"].write_bytes(b"12345678")
    assert MODULE.validate_prefix() == 8
    paths["part"].write_bytes(b"123456")
    assert MODULE.validate_prefix() == 6
    snapshot = MODULE.snapshot_prefix()
    assert snapshot.byte_count == 6
    assert snapshot.sha256 == MODULE.hashlib.sha256(b"123456").hexdigest()


def test_segments_from_arbitrary_prefix_rejoins_grid_and_ends_at_eof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure_small_asset(monkeypatch, tmp_path, expected_bytes=18)
    segments = MODULE.segments_from(6)
    assert [(item.start, item.end) for item in segments] == [
        (6, 7),
        (8, 11),
        (12, 15),
        (16, 17),
    ]


def test_strict_range_validation() -> None:
    blocks = response_blocks(
        100,
        199,
        total=MODULE.EXPECTED_BYTES,
    )
    result = MODULE.validate_range_response(
        blocks=blocks,
        requested_start=100,
        requested_end=199,
        body_bytes=100,
    )
    assert result["etag"] == MODULE.EXPECTED_ETAG
    assert result["validated_bytes"] == 100

    with pytest.raises(MODULE.AcquisitionError, match="CURL_EXIT_CODE"):
        MODULE.validate_range_response(
            blocks=blocks,
            requested_start=100,
            requested_end=199,
            body_bytes=100,
            curl_exit_code=28,
        )
    with pytest.raises(MODULE.AcquisitionError, match="RANGE_BODY_SIZE_MISMATCH"):
        MODULE.validate_range_response(
            blocks=blocks,
            requested_start=100,
            requested_end=199,
            body_bytes=99,
        )
    with pytest.raises(MODULE.NoGoError, match="ETAG_MISSING"):
        MODULE.validate_range_response(
            blocks=response_blocks(
                100,
                199,
                total=MODULE.EXPECTED_BYTES,
                etag=None,
            ),
            requested_start=100,
            requested_end=199,
            body_bytes=100,
        )
    with pytest.raises(MODULE.NoGoError, match="ETAG_MISMATCH"):
        MODULE.validate_range_response(
            blocks=response_blocks(
                100,
                199,
                total=MODULE.EXPECTED_BYTES,
                etag='"changed"',
            ),
            requested_start=100,
            requested_end=199,
            body_bytes=100,
        )


def test_proxy_fallback_commits_exact_segment_and_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = configure_small_asset(monkeypatch, tmp_path)
    store = MODULE.ManifestStore()
    store.load_or_create(prefix_snapshot(paths, b"ABCD"))
    segment = MODULE.Segment(4, 7)
    calls: list[str] = []

    def fake_request(**kwargs: object) -> dict:
        proxy = str(kwargs["proxy"])
        calls.append(proxy)
        attempt = int(kwargs["attempt"])
        temporary = paths["segments"] / f".response-{attempt}"
        temporary.write_bytes(b"EFGH")
        if len(calls) == 1:
            return {
                "temporary_body": temporary,
                "proxy_route": "https://proxy.example.invalid:3128",
                "requested_range": "bytes=4-7",
                "curl_exit_code": 28,
                "elapsed_seconds": 0.1,
                "body_bytes": 4,
                "header_blocks": response_blocks(4, 7, total=20),
                "stderr": "timeout",
            }
        return {
            "temporary_body": temporary,
            "proxy_route": "https://proxy.example.invalid:3128",
            "requested_range": "bytes=4-7",
            "curl_exit_code": 0,
            "elapsed_seconds": 0.1,
            "body_bytes": 4,
            "header_blocks": response_blocks(4, 7, total=20),
            "stderr": "",
        }

    monkeypatch.setattr(MODULE, "run_segment_request", fake_request)
    result = MODULE.acquire_one_segment(
        segment,
        options=MODULE.TransferOptions(
            concurrency=1,
            attempt_rounds=1,
            connect_timeout_seconds=1,
            max_time_seconds=1,
        ),
        store=store,
    )
    assert calls == list(MODULE.PROXIES)
    assert segment.path.read_bytes() == b"EFGH"
    assert oct(segment.path.stat().st_mode & 0o777) == "0o600"
    record = store.data["segments"][segment.key]
    assert record["status"] == "complete"
    assert record["attempts"] == 2
    assert record["sha256"] == result["sha256"]
    assert store.data["object_etag"] == MODULE.EXPECTED_ETAG


def test_manifest_reconciles_crash_after_segment_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = configure_small_asset(monkeypatch, tmp_path)
    store = MODULE.ManifestStore()
    store.load_or_create(prefix_snapshot(paths, b"ABCD"))
    segment = MODULE.Segment(4, 7)
    payload = b"EFGH"
    segment.path.write_bytes(payload)
    record = store.data["segments"][segment.key]
    record.update(
        {
            "status": "committing",
            "etag": MODULE.EXPECTED_ETAG,
            "sha256": MODULE.hashlib.sha256(payload).hexdigest(),
        }
    )
    store.data["object_etag"] = MODULE.EXPECTED_ETAG
    store.save()

    resumed = MODULE.ManifestStore()
    resumed.load_existing()
    assert resumed.data["segments"][segment.key]["status"] == "complete"


def test_parallel_lock_is_exclusive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure_small_asset(monkeypatch, tmp_path)
    with MODULE.ExclusiveParallelLock(), pytest.raises(
        MODULE.AcquisitionError,
        match="PARALLEL_ACQUISITION_OR_ASSEMBLY_LOCKED",
    ), MODULE.ExclusiveParallelLock():
        pass


def test_canonical_guard_refuses_existing_sequential_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = configure_small_asset(monkeypatch, tmp_path)
    paths["canonical_lock"].write_text("sequential\n", encoding="utf-8")
    with pytest.raises(
        MODULE.AcquisitionError,
        match="CANONICAL_ACQUISITION_LOCK_PRESENT",
    ), MODULE.CanonicalMutationGuard():
        pass
    assert paths["canonical_lock"].read_text(encoding="utf-8") == "sequential\n"


def test_recover_interrupted_append_truncates_to_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = configure_small_asset(monkeypatch, tmp_path)
    paths["part"].write_bytes(b"ABCDEFGHxx")
    store = MODULE.ManifestStore()
    store.load_or_create(MODULE.snapshot_prefix(byte_count=8))
    store.set_assembly(
        status_value="appending",
        stable_prefix=8,
        segment_start=8,
    )
    MODULE.recover_interrupted_append(store)
    assert paths["part"].read_bytes() == b"ABCDEFGH"
    assert store.data["assembly"]["status"] == "recovered"


def test_assembly_appends_in_order_then_reuses_exact_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = configure_small_asset(monkeypatch, tmp_path, expected_bytes=12)
    paths["part"].write_bytes(b"ABCD")
    store = MODULE.ManifestStore()
    store.load_or_create(MODULE.snapshot_prefix())
    for segment, payload in (
        (MODULE.Segment(4, 7), b"EFGH"),
        (MODULE.Segment(8, 11), b"IJKL"),
    ):
        segment.path.write_bytes(payload)
        record = store.data["segments"][segment.key]
        record.update(
            {
                "status": "complete",
                "etag": MODULE.EXPECTED_ETAG,
                "sha256": MODULE.hashlib.sha256(payload).hexdigest(),
                "observed_bytes": len(payload),
            }
        )
    store.data["object_etag"] = MODULE.EXPECTED_ETAG
    store.save()

    captured: dict[str, object] = {}

    def fake_reuse(**kwargs: object) -> dict:
        captured.update(kwargs)
        assert paths["part"].read_bytes() == b"ABCDEFGHIJKL"
        return {
            "media": {"bytes": 12},
            "technical": {"ffprobe_passed": True},
        }

    monkeypatch.setattr(MODULE, "reuse_exact_validation", fake_reuse)
    result = MODULE.run_assembly("/synthetic/ffprobe")
    assert result["status"] == "COMPLETE_VERIFIED_READY"
    assert result["transfer"]["assembled_segment_count"] == 2
    assert captured["ffprobe_requested"] == "/synthetic/ffprobe"
    assert not paths["canonical_lock"].exists()


def test_assembly_skips_segments_covered_by_prefix_growth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = configure_small_asset(
        monkeypatch,
        tmp_path,
        expected_bytes=14,
    )
    store = MODULE.ManifestStore()
    store.load_or_create(prefix_snapshot(paths, b"ABCDEF"))
    complete_segment(store, MODULE.Segment(6, 7), b"GH")
    complete_segment(store, MODULE.Segment(8, 11), b"IJKL")
    complete_segment(store, MODULE.Segment(12, 13), b"MN")
    store.save()

    paths["part"].write_bytes(b"ABCDEFGHIJKL")
    captured: dict[str, object] = {}

    def fake_reuse(**kwargs: object) -> dict:
        captured.update(kwargs)
        assert paths["part"].read_bytes() == b"ABCDEFGHIJKLMN"
        return {
            "media": {"bytes": 14},
            "technical": {"ffprobe_passed": True},
        }

    monkeypatch.setattr(MODULE, "reuse_exact_validation", fake_reuse)
    result = MODULE.run_assembly(None)
    assert result["transfer"]["assembly_prefix_bytes"] == 12
    assert result["transfer"]["assembled_segment_count"] == 1
    assert result["transfer"]["assembled_bytes"] == 2
    assert captured["transfer"] == result["transfer"]


def test_assembly_rejects_stale_partial_overlap_after_prefix_growth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = configure_small_asset(
        monkeypatch,
        tmp_path,
        expected_bytes=14,
    )
    store = MODULE.ManifestStore()
    store.load_or_create(prefix_snapshot(paths, b"ABCDEF"))
    complete_segment(store, MODULE.Segment(6, 7), b"GH")
    complete_segment(store, MODULE.Segment(8, 11), b"IJKL")
    complete_segment(store, MODULE.Segment(12, 13), b"MN")
    store.save()

    paths["part"].write_bytes(b"ABCDEFGHIJ")
    with pytest.raises(
        MODULE.AcquisitionError,
        match="STALE_SEGMENT_PARTIAL_OVERLAP:10:8-11",
    ):
        MODULE.run_assembly(None)
    assert paths["part"].read_bytes() == b"ABCDEFGHIJ"
    assert not paths["canonical_lock"].exists()


def test_assembly_rejects_segment_when_prefix_provenance_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = configure_small_asset(
        monkeypatch,
        tmp_path,
        expected_bytes=10,
    )
    store = MODULE.ManifestStore()
    store.load_or_create(prefix_snapshot(paths, b"ABCDEF"))
    complete_segment(store, MODULE.Segment(6, 7), b"GH")
    complete_segment(store, MODULE.Segment(8, 9), b"IJ")
    store.save()

    paths["part"].write_bytes(b"ABXDEF")
    with pytest.raises(
        MODULE.NoGoError,
        match="SEGMENT_PREFIX_PROVENANCE_MISMATCH:6-7",
    ):
        MODULE.run_assembly(None)
    assert paths["part"].read_bytes() == b"ABXDEF"


def test_eof_prefix_needs_no_segments_or_manifest_etag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = configure_small_asset(
        monkeypatch,
        tmp_path,
        expected_bytes=6,
    )
    paths["part"].write_bytes(b"ABCDEF")
    store = MODULE.ManifestStore()
    store.load_or_create(MODULE.snapshot_prefix())
    assert MODULE.segments_from(6) == []
    assert MODULE.verified_coverage(store, 6) == []

    monkeypatch.setattr(
        MODULE,
        "reuse_exact_validation",
        lambda **_kwargs: {
            "media": {"bytes": 6},
            "technical": {"ffprobe_passed": True},
        },
    )
    result = MODULE.run_assembly(None)
    assert result["transfer"]["assembled_segment_count"] == 0
    assert result["transfer"]["assembled_bytes"] == 0


def test_assembly_rolls_back_partial_segment_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = configure_small_asset(monkeypatch, tmp_path)
    paths["part"].write_bytes(b"ABCD")
    source = paths["segments"] / "source"
    source.write_bytes(b"EFGH")
    store = MODULE.ManifestStore()
    store.load_or_create(MODULE.snapshot_prefix())
    segment = MODULE.Segment(4, 7)
    original_open = Path.open

    class FailingSource:
        def __init__(self, handle: object) -> None:
            self.handle = handle
            self.reads = 0

        def __enter__(self) -> Self:
            self.handle.__enter__()
            return self

        def __exit__(self, *args: object) -> object:
            return self.handle.__exit__(*args)

        def read(self, size: int = -1) -> bytes:
            self.reads += 1
            if self.reads == 1:
                return b"EF"
            raise OSError("synthetic copy failure")

    def patched_open(path: Path, *args: object, **kwargs: object) -> object:
        handle = original_open(path, *args, **kwargs)
        if path == source and args and args[0] == "rb":
            return FailingSource(handle)
        return handle

    monkeypatch.setattr(Path, "open", patched_open)
    with pytest.raises(OSError, match="synthetic copy failure"):
        MODULE.append_segment_to_canonical(
            segment=segment,
            source_path=source,
            store=store,
        )
    assert paths["part"].read_bytes() == b"ABCD"
    assert store.data["assembly"]["status"] == "append_rolled_back"


def test_run_acquisition_uses_bounded_concurrency_without_canonical_append(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = configure_small_asset(monkeypatch, tmp_path, expected_bytes=12)
    paths["part"].write_bytes(b"ABCD")
    active = 0
    peak = 0
    canonical_sizes: list[int] = []

    def fake_acquire(
        segment: MODULE.Segment,
        *,
        options: MODULE.TransferOptions,
        store: MODULE.ManifestStore,
    ) -> dict:
        nonlocal active, peak
        del options, store
        active += 1
        peak = max(peak, active)
        canonical_sizes.append(paths["part"].stat().st_size)
        payload = bytes([segment.start]) * segment.byte_count
        segment.path.write_bytes(payload)
        active -= 1
        return {
            "segment": segment.key,
            "bytes": segment.byte_count,
            "sha256": "synthetic",
            "etag": MODULE.EXPECTED_ETAG,
        }

    monkeypatch.setattr(MODULE, "acquire_one_segment", fake_acquire)
    monkeypatch.setattr(
        MODULE,
        "acquisition_free_space",
        lambda missing: {
            "free_bytes": 100,
            "missing_segment_bytes": sum(item.byte_count for item in missing),
            "required_free_bytes": 0,
            "free_space_margin_bytes": 0,
        },
    )
    result = MODULE.run_acquisition(
        MODULE.TransferOptions(
            concurrency=2,
            attempt_rounds=1,
            connect_timeout_seconds=1,
            max_time_seconds=1,
        )
    )
    assert peak <= 2
    assert canonical_sizes == [4, 4]
    assert paths["part"].read_bytes() == b"ABCD"
    assert result["canonical_staging_modified"] is False


def test_load_exact_tool_identity_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = SimpleNamespace(
        EXPECTED_BYTES=MODULE.EXPECTED_BYTES,
        OFFICIAL_MD5=MODULE.OFFICIAL_MD5,
        OFFICIAL_URL=MODULE.OFFICIAL_URL,
        PART_MEDIA=MODULE.PART_MEDIA,
        FINAL_MEDIA=MODULE.FINAL_MEDIA,
    )
    spec = SimpleNamespace(
        loader=SimpleNamespace(exec_module=lambda module: module.__dict__.update(fake.__dict__))
    )
    monkeypatch.setattr(
        MODULE.importlib.util,
        "spec_from_file_location",
        lambda *_args, **_kwargs: spec,
    )
    monkeypatch.setattr(
        MODULE.importlib.util,
        "module_from_spec",
        lambda _spec: SimpleNamespace(),
    )
    loaded = MODULE.load_exact_tool()
    assert loaded.EXPECTED_BYTES == MODULE.EXPECTED_BYTES


def test_manifest_file_is_canonical_json_and_restrictive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = configure_small_asset(monkeypatch, tmp_path)
    store = MODULE.ManifestStore()
    store.load_or_create(MODULE.snapshot_prefix())
    parsed = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert parsed["expected_etag"] == MODULE.EXPECTED_ETAG
    assert os.stat(paths["manifest"]).st_mode & 0o777 == 0o600
