from __future__ import annotations

import hashlib
import json
from pathlib import Path

import av
import numpy as np
import pytest

from av_trace_real_rehearsal.adapter import (
    AccessBlockedError,
    IntegrityBindingError,
    RestrictedAssetAdapter,
)
from av_trace_real_rehearsal.protocol import (
    RehearsalRunner,
    derive_provisional_tasks,
    write_rehearsal_report,
)


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def real_adapter() -> RestrictedAssetAdapter:
    return RestrictedAssetAdapter(ROOT)


def test_real_adapter_binds_all_five_and_never_exposes_content(real_adapter) -> None:
    assert set(real_adapter.candidate_ids) == {
        "ccp-003",
        "ccp-008",
        "ccp-009",
        "ccp-011",
        "ccp-012",
    }
    task = derive_provisional_tasks(real_adapter)[0]
    hit = real_adapter.search_subtitle_proxy(task.candidate_id, task.query_tokens)[0]
    sample = real_adapter.sample_frame(task.candidate_id, task.target_time_s)
    rendered = json.dumps({"hit": hit.safe_dict(), "sample": sample.safe_dict()})
    assert "subtitle-proxy text withheld" in rendered
    assert "rgb" not in rendered
    assert task.query_tokens[0] not in rendered


def test_provisional_tasks_cover_routes_and_are_not_annotations(real_adapter) -> None:
    tasks = derive_provisional_tasks(real_adapter)
    assert len(tasks) == 20
    assert {task.route for task in tasks} == {
        "visual_only",
        "subtitle_proxy_only",
        "video_to_subtitle_proxy",
        "subtitle_proxy_to_video",
    }
    assert all(task.status == "PROVISIONAL_REHEARSAL_ONLY" for task in tasks)
    assert all(task.final_benchmark_annotation is False for task in tasks)
    assert all(task.semantic_visual_retrieval == "UNAVAILABLE_NOT_FAKED" for task in tasks)


def test_blocked_routes_fail_and_restoration_recovers(real_adapter) -> None:
    runner = RehearsalRunner(real_adapter)
    tasks = derive_provisional_tasks(real_adapter)
    visual = next(task for task in tasks if task.route == "visual_only")
    subtitle = next(task for task in tasks if task.route == "subtitle_proxy_only")
    blocked_visual = runner.run_episode(visual, "BLOCKED", "recovery_agent")
    restored_visual = runner.run_episode(visual, "RESTORED", "recovery_agent")
    blocked_subtitle = runner.run_episode(subtitle, "BLOCKED", "recovery_agent")
    restored_subtitle = runner.run_episode(subtitle, "RESTORED", "recovery_agent")
    assert blocked_visual["metrics"]["evidence_acquisition_success"] == 0
    assert blocked_subtitle["metrics"]["evidence_acquisition_success"] == 0
    assert restored_visual["metrics"]["evidence_acquisition_success"] == 1
    assert restored_subtitle["metrics"]["evidence_acquisition_success"] == 1
    assert restored_visual["metrics"]["recovery_after_perturbation"] == 1
    assert restored_subtitle["metrics"]["recovery_after_perturbation"] == 1


def test_full_rehearsal_safe_metrics_and_matched_states(real_adapter) -> None:
    report = RehearsalRunner(real_adapter).run_all()
    assert report["audio_used"] is False
    assert report["raw_frames_persisted"] is False
    assert report["subtitle_text_persisted"] is False
    assert report["final_benchmark_annotations_created"] is False
    assert report["summary"]["asset_count"] == 5
    assert report["summary"]["task_count"] == 20
    assert report["summary"]["run_count"] == 240
    assert report["summary"]["matched_intervention_definition_across_states"] is True
    assert report["summary"]["strict_engineering_go"] is True
    assert all(
        run["metrics"]["timestamp_citation_validity"] == 1
        for run in report["runs"]
    )
    rendered = json.dumps(report)
    for task in derive_provisional_tasks(real_adapter):
        for token in task.query_tokens:
            assert token not in rendered


def test_safe_report_permissions(real_adapter, tmp_path: Path) -> None:
    report = RehearsalRunner(real_adapter).run_all()
    output = tmp_path / "safe.json"
    write_rehearsal_report(output, report)
    assert output.stat().st_mode & 0o077 == 0
    value = json.loads(output.read_text())
    assert value["scope_label"] == "V + subtitle-proxy internal engineering rehearsal"


def _tiny_repo(tmp_path: Path) -> Path:
    root = tmp_path
    restricted = root / "data/restricted/lvb01"
    videos = restricted / "raw/videos"
    subtitles = restricted / "raw/subtitles"
    manifests = restricted / "manifests"
    plan_dir = root / "data/acquisition_plan"
    status_dir = root / "data/rehearsal_plan"
    for directory in (videos, subtitles, manifests, plan_dir, status_dir):
        directory.mkdir(parents=True, exist_ok=True)
    for directory in (restricted, videos, subtitles, manifests):
        directory.chmod(0o700)
    video = videos / "asset.mp4"
    container = av.open(str(video), mode="w")
    stream = container.add_stream("mpeg4", rate=2)
    stream.width = 32
    stream.height = 24
    stream.pix_fmt = "yuv420p"
    for index in range(4):
        frame = av.VideoFrame.from_ndarray(
            np.full((24, 32, 3), 30 + index, dtype=np.uint8),
            format="rgb24",
        )
        for packet in stream.encode(frame):
            container.mux(packet)
    for packet in stream.encode():
        container.mux(packet)
    container.close()
    subtitle = subtitles / "asset_en.json"
    subtitle.write_text(
        json.dumps([{"start": 0.5, "end": 0.51, "line": "private rehearsal token"}])
    )
    video.chmod(0o600)
    subtitle.chmod(0o600)

    def digest(path: Path) -> tuple[int, str]:
        data = path.read_bytes()
        return len(data), hashlib.sha256(data).hexdigest()

    vs, vh = digest(video)
    ss, sh = digest(subtitle)
    plan = {
        "plan_id": "test-plan",
        "pinned_revision": "test-revision",
        "targets": [
            {
                "candidate_id": "ccp-test",
                "video_id": "asset",
                "kind": "video",
                "basename": video.name,
                "destination": "raw/videos/asset.mp4",
                "size": vs,
            },
            {
                "candidate_id": "ccp-test",
                "video_id": "asset",
                "kind": "subtitle",
                "basename": subtitle.name,
                "destination": "raw/subtitles/asset_en.json",
                "size": ss,
            },
        ],
    }
    plan_path = plan_dir / "lvb01_exact_asset_plan.json"
    plan_path.write_text(json.dumps(plan))
    ps, ph = digest(plan_path)
    manifest = {
        "plan_id": "test-plan",
        "pinned_revision": "test-revision",
        "plan_sha256": ph,
        "targets": [
            {
                "kind": "video",
                "basename": video.name,
                "metadata_path": "raw/videos/asset.mp4.metadata.json",
                "size": vs,
                "sha256": vh,
                "status": "downloaded",
            },
            {
                "kind": "subtitle",
                "basename": subtitle.name,
                "metadata_path": "raw/subtitles/asset_en.json.metadata.json",
                "size": ss,
                "sha256": sh,
                "status": "downloaded",
            },
        ],
    }
    manifest_path = manifests / "lvb01_acquisition_manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    ms, mh = digest(manifest_path)
    entries = []
    for kind, path, size, sha, destination in (
        ("video", video, vs, vh, "raw/videos/asset.mp4"),
        ("subtitle", subtitle, ss, sh, "raw/subtitles/asset_en.json"),
    ):
        entries.append(
            {
                "candidate_id": "ccp-test",
                "video_id": "asset",
                "kind": kind,
                "basename": path.name,
                "path": f"data/restricted/lvb01/{destination}",
                "actual_size": size,
                "actual_sha256": sha,
                "passed": True,
            }
        )
    audit = {
        "decision": "CONDITIONAL_GO",
        "inputs": {
            "frozen_plan": {
                "path": "data/acquisition_plan/lvb01_exact_asset_plan.json",
                "size": ps,
                "sha256": ph,
            },
            "acquisition_manifest": {
                "path": "data/restricted/lvb01/manifests/lvb01_acquisition_manifest.json",
                "size": ms,
                "sha256": mh,
            },
        },
        "scope": {
            "restricted_root": "data/restricted/lvb01",
            "benchmark_annotations_created": False,
            "derived_media_persisted": False,
            "payloads_modified": False,
        },
        "integrity_and_provenance": {
            "passed": True,
            "aggregate": {"exact_match": True},
            "entries": entries,
        },
        "videos": [
            {
                "candidate_id": "ccp-test",
                "technically_usable": True,
                "duration": {"actual_seconds": 2.0},
                "streams": {"video_stream_count": 1, "audio_stream_count": 0},
            }
        ],
        "subtitles": [
            {
                "candidate_id": "ccp-test",
                "valid": True,
                "usable_speech_proxy": True,
                "schema": {"entry_count": 1},
            }
        ],
    }
    (manifests / "lvb01_media_audit.json").write_text(json.dumps(audit))
    (status_dir / "lvb01_verified_asset_status.csv").write_text(
        "candidate_id,download_integrity_status,video_stream_status,"
        "audio_stream_status,subtitle_proxy_status,"
        "internal_visual_subtitle_rehearsal_status\n"
        "ccp-test,DOWNLOADED_HASH_VERIFIED_INTERNAL,AVAILABLE_ONE_H264_STREAM,"
        "ABSENT_ZERO_STREAMS,AVAILABLE_ORDERED_NONEMPTY_TIMELINE,"
        "TECHNICALLY_READY_INTERNAL_ONLY\n"
    )
    return root


def test_adapter_fails_closed_if_payload_hash_drifts(tmp_path: Path) -> None:
    root = _tiny_repo(tmp_path)
    adapter = RestrictedAssetAdapter(root, expected_candidate_count=1)
    binding = adapter.binding("ccp-test")
    binding.subtitle_path.write_text("[]")
    with pytest.raises(IntegrityBindingError, match="SIZE_DRIFT|HASH_DRIFT"):
        adapter.search_subtitle_proxy("ccp-test", ["private"])


def test_adapter_rejects_non_allowlisted_candidate(real_adapter) -> None:
    with pytest.raises(Exception, match="NOT_ALLOWLISTED"):
        real_adapter.sample_frame("not-allowlisted", 1.0)
