from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from av_trace_epic_wave1_index.sources import (
    EXPECTED_ACQUISITION_MANIFEST,
    EpicWave1SourceError,
    computed_counts,
    load_plan_definition,
    load_source_plan,
)

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "data/rehearsal_plan/epic_wave1_full_timeline_index_v1.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _copy_static_plan(tmp_path: Path) -> dict:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    for binding in plan["official_metadata_bindings"].values():
        source = ROOT / binding["path"]
        target = tmp_path / binding["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    return plan


def _ready_fixture(tmp_path: Path) -> tuple[Path, dict[str, bytes]]:
    plan = _copy_static_plan(tmp_path)
    payloads = {
        "P28_103": b"P28 exact fixture media\n",
        "P27_101": b"P27 exact fixture media\n",
    }
    sources = []
    for item in plan["sources"]:
        source_id = item["source_id"]
        media_path = tmp_path / item["expected_final_media_path"]
        media_path.parent.mkdir(parents=True, exist_ok=True)
        media_path.parent.chmod(0o700)
        media_path.write_bytes(payloads[source_id])
        media_path.chmod(0o600)
        item["official_content_length_bytes"] = len(payloads[source_id])
        item["official_md5"] = hashlib.md5(
            payloads[source_id], usedforsecurity=False
        ).hexdigest()
        sources.append(
            {
                "source_id": source_id,
                "status": "COMPLETE",
                "duration_seconds": item["official_duration_seconds"],
                "media": {
                    "role": "primary_video",
                    "path": item["expected_final_media_path"],
                    "bytes": len(payloads[source_id]),
                    "sha256": hashlib.sha256(payloads[source_id]).hexdigest(),
                    "md5": item["official_md5"],
                    "version": item["official_media_version"],
                },
                "decode_facts": {
                    "duration_seconds": item["official_duration_seconds"],
                    "streams": [{"type": "video"}, {"type": "audio"}],
                    "av_sync_verified": True,
                },
            }
        )
    plan["totals"]["primary_media_bytes"] = sum(map(len, payloads.values()))
    video_path = tmp_path / plan["official_metadata_bindings"]["video_info_csv"]["path"]
    md5_path = tmp_path / plan["official_metadata_bindings"]["md5_csv"]["path"]
    video_path.write_text(
        "video_id,duration,fps,resolution\n"
        + "\n".join(
            f"{item['source_id']},{item['official_duration_seconds']},"
            f"{item['official_fps']},{item['official_resolution']}"
            for item in plan["sources"]
        )
        + "\n",
        encoding="utf-8",
    )
    md5_path.write_text(
        "md5,file_remote_path,version\n"
        + "\n".join(
            f"{item['official_md5']},{item['official_remote_path']},"
            f"{item['official_media_version']}"
            for item in plan["sources"]
        )
        + "\n",
        encoding="utf-8",
    )
    plan["official_metadata_bindings"]["video_info_csv"]["sha256"] = _sha256(
        video_path
    )
    plan["official_metadata_bindings"]["md5_csv"]["sha256"] = _sha256(md5_path)
    acquisition_path = tmp_path / EXPECTED_ACQUISITION_MANIFEST
    acquisition_path.parent.mkdir(parents=True, exist_ok=True)
    acquisition_path.parent.chmod(0o700)
    acquisition_path.write_text(
        json.dumps(
            {
                "decision": "EPIC_WAVE1_ACQUISITION_READY",
                "failed_transfer_accounting": {"count": 0, "objects": []},
                "incomplete_transfer_accounting": {"count": 0, "objects": []},
                "sources": sources,
            }
        ),
        encoding="utf-8",
    )
    acquisition_path.chmod(0o600)
    plan_path = tmp_path / PLAN.relative_to(ROOT)
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    return plan_path, payloads


def test_repository_plan_is_structurally_valid_without_task162_media():
    _, plan, _, acquisition, output = load_plan_definition(ROOT)
    assert [item["source_id"] for item in plan["sources"]] == [
        "P28_103",
        "P27_101",
    ]
    assert acquisition == ROOT / EXPECTED_ACQUISITION_MANIFEST
    assert output == ROOT / "data/restricted/epic_wave1_index_v1"


def test_lattice_counts_are_frozen():
    assert computed_counts(1825.16) == {
        "base_cells": 457,
        "fine_windows": 456,
        "context_windows": 114,
        "temporal_segments": 570,
        "whisper_chunks": 61,
        "checkpoints": 4,
    }
    assert computed_counts(1360.2) == {
        "base_cells": 341,
        "fine_windows": 340,
        "context_windows": 85,
        "temporal_segments": 425,
        "whisper_chunks": 46,
        "checkpoints": 4,
    }


def test_repository_loader_accepts_task162_ready():
    plan = load_source_plan(ROOT)
    assert [item.source_id for item in plan.sources] == [
        "P28_103",
        "P27_101",
    ]
    assert all(len(item.media_sha256) == 64 for item in plan.sources)
    assert plan.acquisition_manifest_sha256


def test_ready_fixture_requires_and_loads_exact_hashes(tmp_path: Path):
    plan_path, payloads = _ready_fixture(tmp_path)
    plan = load_source_plan(
        tmp_path,
        plan_path=plan_path,
        hash_files=True,
        verify_models=False,
    )
    assert [item.source_id for item in plan.sources] == ["P28_103", "P27_101"]
    assert plan.sources[0].media_sha256 == hashlib.sha256(
        payloads["P28_103"]
    ).hexdigest()
    assert plan.acquisition_manifest_sha256


def test_ready_token_without_sha256_is_rejected(tmp_path: Path):
    plan_path, _ = _ready_fixture(tmp_path)
    acquisition_path = tmp_path / EXPECTED_ACQUISITION_MANIFEST
    acquisition = json.loads(acquisition_path.read_text(encoding="utf-8"))
    del acquisition["sources"][0]["media"]["sha256"]
    acquisition_path.write_text(json.dumps(acquisition), encoding="utf-8")
    with pytest.raises(EpicWave1SourceError, match="EXACT_SHA256_MISSING"):
        load_source_plan(
            tmp_path, plan_path=plan_path, verify_models=False
        )


def test_staging_media_path_is_rejected(tmp_path: Path):
    plan_path, _ = _ready_fixture(tmp_path)
    acquisition_path = tmp_path / EXPECTED_ACQUISITION_MANIFEST
    acquisition = json.loads(acquisition_path.read_text(encoding="utf-8"))
    acquisition["sources"][0]["media"]["path"] = (
        "data/restricted/epic_wave1_sources_v1/.staging/P28_103.MP4"
    )
    acquisition_path.write_text(json.dumps(acquisition), encoding="utf-8")
    with pytest.raises(EpicWave1SourceError, match="MEDIA_PATH_INVALID"):
        load_source_plan(
            tmp_path, plan_path=plan_path, verify_models=False
        )
