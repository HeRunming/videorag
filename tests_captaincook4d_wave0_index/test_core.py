from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import ClassVar

import numpy as np

from av_trace_captaincook4d_wave0_index import core
from av_trace_captaincook4d_wave0_index.sources import (
    CaptainCook4DSourceSpec,
    CaptainCook4DWave0Plan,
)


class FakeMedia:
    def iter_sampled_frames(self, path, cells):
        del path
        frame = np.zeros((8, 8, 3), dtype=np.uint8)
        for cell in cells:
            yield cell, frame, cell["sample_time_us"], "1/1000000"

    def decode_audio(self, path, target_rate=16_000):
        del path
        return np.zeros(target_rate * 8, dtype=np.float32)


class FakeModels:
    runtime: ClassVar = {"device": "cpu", "network_access": "disabled"}

    def clip_images(self, images):
        return [
            np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
            for _ in images
        ]

    def clip_text(self, texts):
        return [
            np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
            for _ in texts
        ]

    def whisper(self, chunk_ids, audio_chunks):
        del audio_chunks
        return [
            {
                "chunk_id": chunk_id,
                "text": "fixture speech",
                "searchable": True,
                "exclusion_reason": None,
                "quality_flags": [],
            }
            for chunk_id in chunk_ids
        ]

    def ast(self, audio_windows):
        return [
            {
                "top15": [
                    {
                        "class_id": 1,
                        "label": "Dishes",
                        "probability": 0.9,
                    }
                ],
                "quality_flags": [],
            }
            for _ in audio_windows
        ]


def _routing(rgb, previous, face):
    del rgb, face
    return (
        {
            "luminance_mean": 0.0,
            "luminance_std": 0.0,
            "hue_histogram_12": [0.0] * 12,
            "edge_density": 0.0,
            "motion_or_change": 0.0,
            "blank_frame": True,
            "pinned_haar_face_presence": False,
            "semantic_claim_allowed": False,
        },
        previous,
    )


def _fixture_plan(tmp_path: Path) -> CaptainCook4DWave0Plan:
    output = (
        tmp_path
        / "data/restricted/captaincook4d_wave0_index_v1_smoke"
    )
    acquisition = (
        tmp_path
        / "data/restricted/captaincook4d_wave0_sources_v3/manifests/"
        "captaincook4d_wave0_acquisition_manifest.json"
    )
    acquisition.parent.mkdir(parents=True, exist_ok=True)
    acquisition.write_text(
        '{"decision":"CAPTAINCOOK4D_WAVE0_ACQUISITION_READY"}\n'
    )
    acquisition.chmod(0o600)
    sources = []
    source_root = (
        tmp_path / "data/restricted/captaincook4d_wave0_sources_v3"
    )
    source_root.mkdir(parents=True, exist_ok=True)
    source_root.chmod(0o700)
    for source_id, group, person, environment in (
        ("16_20", "cc4d_p01_e08", 1, 8),
        ("15_29", "cc4d_p02_e02", 2, 2),
        ("26_22", "cc4d_p03_e03", 3, 3),
    ):
        media = source_root / f"{source_id}_360p.mp4"
        media.write_bytes(source_id.encode())
        media.chmod(0o600)
        source_manifest = acquisition.parent / f"{source_id}.source_manifest.json"
        source_manifest.write_text("{}\n")
        source_manifest.chmod(0o600)
        sources.append(
            CaptainCook4DSourceSpec(
                source_id=source_id,
                source_group_id=group,
                person_id=person,
                environment_id=environment,
                source_manifest_path=source_manifest,
                source_directory=source_root,
                media_path=media,
                media_bytes=media.stat().st_size,
                media_sha256=hashlib.sha256(media.read_bytes()).hexdigest(),
                media_md5=hashlib.md5(
                    media.read_bytes(), usedforsecurity=False
                ).hexdigest(),
                duration_seconds=8.0,
                duration_tolerance_seconds=0.01,
                expected_counts={
                    "base_cells": 2,
                    "fine_windows": 2,
                    "context_windows": 0,
                    "temporal_segments": 2,
                    "whisper_chunks": 1,
                    "checkpoints": 4,
                },
            )
        )
    snapshots = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "data/rehearsal_plan/"
            "captaincook4d_wave0_full_timeline_index_v1.json"
        ).read_text()
    )["model_snapshots"]
    return CaptainCook4DWave0Plan(
        repo_root=tmp_path,
        plan_path=tmp_path / "plan.json",
        output_root=output,
        allowed_restricted_source_root=source_root,
        acquisition_manifest_path=acquisition,
        acquisition_manifest_sha256=core._sha256(acquisition),
        sources=tuple(sources),
        totals={},
        model_snapshots=snapshots,
        index_policy={},
        raw={
            "storage_caps": {
                "derived_artifacts_hard_fail_cap_mib": 512
            }
        },
    )


def test_smoke_build_is_namespaced_and_resume_stable(tmp_path, monkeypatch):
    plan = _fixture_plan(tmp_path)
    plan.plan_path.write_text("{}\n")
    model_file = tmp_path / "model.bin"
    model_file.write_bytes(b"model")
    config = core.config_from_plan(plan, output_root=plan.output_root, threads=1)
    config = type(config)(
        **{
            **config.__dict__,
            "clip_model_path": model_file,
            "whisper_model_path": model_file,
            "ast_model_path": model_file,
            "haar_model_path": model_file,
        }
    )
    monkeypatch.setattr(core, "config_from_plan", lambda *args, **kwargs: config)
    result = core.build_captaincook4d_wave0_index(
        tmp_path,
        plan=plan,
        output_root=plan.output_root,
        smoke_seconds=8.0,
        model_backend=FakeModels(),
        media_backend=FakeMedia(),
        routing_extractor=_routing,
        threads=1,
    )
    assert result["build_manifest"]["mode"] == "smoke"
    assert result["build_manifest"]["checkpoint_count"] == 12
    assert result["full_timeline_index"]["index_version"].startswith(
        "captaincook4d-wave0"
    )
    assert result["build_manifest"]["terminal_boundary"][
        "semantic_annotations_generated"
    ] is False
    before = {
        path.relative_to(plan.output_root).as_posix(): core._sha256(path)
        for path in plan.output_root.rglob("*")
        if path.is_file()
    }
    mtimes = {
        path.relative_to(plan.output_root).as_posix(): path.stat().st_mtime_ns
        for path in (plan.output_root / "checkpoints").rglob("*.json")
    }
    core.build_captaincook4d_wave0_index(
        tmp_path,
        plan=plan,
        output_root=plan.output_root,
        smoke_seconds=8.0,
        model_backend=FakeModels(),
        media_backend=FakeMedia(),
        routing_extractor=_routing,
        threads=1,
        resume=True,
    )
    after = {
        path.relative_to(plan.output_root).as_posix(): core._sha256(path)
        for path in plan.output_root.rglob("*")
        if path.is_file()
    }
    after_mtimes = {
        path.relative_to(plan.output_root).as_posix(): path.stat().st_mtime_ns
        for path in (plan.output_root / "checkpoints").rglob("*.json")
    }
    assert before == after
    assert mtimes == after_mtimes
