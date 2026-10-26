from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from typing import ClassVar

import numpy as np
import pytest

from av_trace_mini_pilot_index.core import (
    IndexConfig,
    MiniPilotIndexError,
    _assert_search_record_safe,
    _checkpoint_key,
    _read_checkpoint,
    _write_checkpoint,
    build_full_timeline_index,
    build_mini_pilot_index,
    build_observation_manifest,
    build_segment_manifest,
    load_sources,
    search_ambient,
    search_fused,
    search_speech,
    search_visual,
)
from av_trace_mini_pilot_index.sources import load_source_plan


class FakeMedia:
    def __init__(self) -> None:
        self.frame_decodes = 0
        self.audio_decodes = 0

    def iter_sampled_frames(self, path, cells):
        del path
        self.frame_decodes += 1
        for index, cell in enumerate(cells):
            rgb = np.full((10, 12, 3), index * 10, dtype=np.uint8)
            yield cell, rgb, index, "1/25"

    def decode_audio(self, path, target_rate=16_000):
        del path
        self.audio_decodes += 1
        return np.linspace(-0.5, 0.5, target_rate * 10, dtype=np.float32)


class FakeModels:
    runtime: ClassVar[dict[str, str]] = {
        "device": "cpu",
        "network_access": "disabled",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
    }

    def whisper(self, identifiers, samples):
        return [
            {
                "chunk_id": identifier,
                "text": f"lecture quantum mechanics chunk {index}",
                "token_count": 5,
                "mean_generated_token_log_probability": -0.2,
                "quality_gate_pass": True,
                "quality_flags": [],
            }
            for index, (identifier, sample) in enumerate(zip(identifiers, samples))
            if len(sample)
        ]

    def ast(self, samples):
        return [
            {
                "top15": [
                    {
                        "class_id": 1,
                        "label": "Speech",
                        "probability": 0.8,
                    },
                    {
                        "class_id": 2,
                        "label": "Writing",
                        "probability": 0.6,
                    },
                ],
                "quality_gate_pass": True,
                "quality_flags": [],
            }
            for _ in samples
        ]

    def clip_images(self, images):
        vectors = []
        for index, _ in enumerate(images):
            vector = np.array([1.0, float(index + 1), 0.5, 0.25])
            vectors.append(vector / np.linalg.norm(vector))
        return np.asarray(vectors, dtype=np.float32)

    def clip_text(self, texts):
        return np.asarray([[1.0, 0.0, 0.0, 0.0] for _ in texts], dtype=np.float32)


def fake_routing(rgb, previous, face):
    del face
    gray = rgb[..., 0]
    return (
        {
            "luminance_mean": float(gray.mean() / 255),
            "luminance_std": float(gray.std() / 255),
            "hue_histogram_12": [1.0] + [0.0] * 11,
            "edge_density": 0.0,
            "motion_or_change": (
                float(np.mean(np.abs(gray.astype(float) - previous.astype(float))) / 255)
                if previous is not None
                else 0.0
            ),
            "blank_frame": True,
            "pinned_haar_face_presence": False,
            "semantic_claim_allowed": False,
        },
        gray,
    )


def make_fixture_repo(tmp_path: Path, *, source_count: int = 2):
    source_root = tmp_path / "data/restricted/sources"
    model_root = tmp_path / "models"
    model_paths = {}
    for name in ("clip", "whisper", "ast"):
        path = model_root / name
        path.mkdir(parents=True)
        (path / "config.json").write_text(f'{{"model":"{name}"}}')
        model_paths[name] = path
    haar = model_root / "haar.xml"
    haar.write_text("fixture")

    sources = []
    durations = [10.0, 17.0, 9.0]
    for index in range(source_count):
        source_ref = f"source-{index}"
        directory = source_root / source_ref
        directory.mkdir(parents=True)
        media = directory / "video.mp4"
        media.write_bytes(f"fixture-video-{index}".encode())
        sources.append(
            {
                "source_group_id": source_ref,
                "status": "COMPLETE_VALIDATED_PROMOTED",
                "decode_facts": {"duration_seconds": durations[index]},
                "payload_files": [
                    {
                        "role": "primary_video",
                        "custodian_path": media.relative_to(tmp_path).as_posix(),
                        "bytes": media.stat().st_size,
                        "sha256": hashlib.sha256(media.read_bytes()).hexdigest(),
                    }
                ],
                "license_attribution_boundary": {
                    "decisions": {
                        "restricted_processing": {
                            "status": "ALLOWED_NONCOMMERCIAL_WITH_SAFEGUARDS"
                        }
                    }
                },
            }
        )
    manifest = source_root / "acquisition_manifest.json"
    manifest.write_text(json.dumps({"sources": sources}))
    config = IndexConfig(
        source_manifest_paths=(manifest.relative_to(tmp_path),),
        output_dir="data/restricted/index",
        clip_model_path=model_paths["clip"].relative_to(tmp_path),
        whisper_model_path=model_paths["whisper"].relative_to(tmp_path),
        ast_model_path=model_paths["ast"].relative_to(tmp_path),
        haar_model_path=haar.relative_to(tmp_path),
        expected_source_count=source_count,
        threads=1,
        whisper_batch_size=2,
        ast_batch_size=2,
        clip_batch_size=2,
    )
    return config


def test_source_loading_rights_count_and_repo_relative_paths(tmp_path: Path):
    config = make_fixture_repo(tmp_path)
    sources = load_sources(
        tmp_path,
        config.source_manifest_paths,
        expected_source_count=2,
    )
    assert len(sources) == 2
    assert all(not Path(item["media_path"]).is_absolute() for item in sources)
    assert all("rights" not in item for item in sources)
    with pytest.raises(MiniPilotIndexError, match="EXPECTED_SOURCE_COUNT"):
        load_sources(
            tmp_path,
            config.source_manifest_paths,
            expected_source_count=3,
        )
    manifest = Path(config.source_manifest_paths[0])
    data = json.loads((tmp_path / manifest).read_text())
    data["sources"][0]["license_attribution_boundary"]["decisions"][
        "restricted_processing"
    ]["status"] = "BLOCKED"
    (tmp_path / manifest).write_text(json.dumps(data))
    with pytest.raises(MiniPilotIndexError, match="NOT_AUTHORIZED"):
        load_sources(tmp_path, config.source_manifest_paths, expected_source_count=2)


def test_exact_lattice_and_terminal_segments(tmp_path: Path):
    config = make_fixture_repo(tmp_path)
    sources = load_sources(
        tmp_path, config.source_manifest_paths, expected_source_count=2
    )
    manifest = build_segment_manifest(tmp_path, sources)
    assert manifest["totals"] == {
        "base_cells": 8,
        "context_windows": 1,
        "fine_windows": 6,
        "windows": 7,
        "maximum_modality_records": 21,
    }
    first_cells = [
        item for item in manifest["base_cells"] if item["source_ref"] == "source-0"
    ]
    assert [(x["start_us"], x["end_us"]) for x in first_cells] == [
        (0, 4_000_000),
        (4_000_000, 8_000_000),
        (8_000_000, 10_000_000),
    ]
    assert first_cells[-1]["sample_time_us"] == 9_999_999
    first_segments = [
        item for item in manifest["segments"] if item["source_ref"] == "source-0"
    ]
    assert [(x["scale"], x["start_us"], x["end_us"]) for x in first_segments] == [
        ("fine", 0, 8_000_000),
        ("fine", 4_000_000, 10_000_000),
    ]


def test_checkpoint_hash_resume_and_corruption_deletion(tmp_path: Path):
    path = tmp_path / "checkpoint.json"
    key = _checkpoint_key("abc", "layer/1", "fine", 0, "cfg")
    meta = _write_checkpoint(
        tmp_path, path, {"records": [{"x": 1}]}, key=key, record_count=1
    )
    assert meta["path"] == "checkpoint.json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    payload, reused = _read_checkpoint(
        tmp_path, path, key=key, expected_count=1
    )
    assert payload == {"records": [{"x": 1}]}
    assert reused and reused["reused"]
    path.write_text(path.read_text().replace('"x": 1', '"x": 2'))
    payload, reused = _read_checkpoint(
        tmp_path, path, key=key, expected_count=1
    )
    assert payload is None and reused is None and not path.exists()


def test_lightweight_full_build_resume_indexes_and_strict_boundary(tmp_path: Path):
    config = make_fixture_repo(tmp_path)
    media = FakeMedia()
    models = FakeModels()
    result = build_mini_pilot_index(
        tmp_path,
        config,
        model_backend=models,
        media_backend=media,
        routing_extractor=fake_routing,
    )
    output = tmp_path / config.output_dir
    assert {path.name for path in output.iterdir() if path.is_file()} == {
        "segment_manifest.json",
        "observation_manifest.json",
        "full_timeline_index.json",
        "resource_manifest.json",
        "build_manifest.json",
    }
    assert not list(output.rglob("*.wav"))
    assert not list(output.rglob("*.png"))
    assert not list(output.rglob("*.mp4"))
    assert result["build_manifest"]["terminal_boundary"] == {
        "last_allowed_stage": "resource_manifest",
        "families_generated": False,
        "negatives_generated": False,
        "interventions_generated": False,
        "trajectories_generated": False,
        "evaluation_generated": False,
    }
    assert result["build_manifest"]["derived_artifact_hard_cap_mib"] is None
    assert all(
        not Path(item["path"]).is_absolute()
        for item in result["observation_manifest"]["checkpoints"]
    )
    assert result["resource_manifest"]["runtime"]["device"] == "cpu"
    assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert os.environ["TRANSFORMERS_OFFLINE"] == "1"
    assert media.frame_decodes == 2
    assert media.audio_decodes == 2

    second = build_mini_pilot_index(
        tmp_path,
        config,
        model_backend=models,
        media_backend=media,
        routing_extractor=fake_routing,
    )
    assert media.frame_decodes == 2
    assert media.audio_decodes == 2
    assert all(
        "reused" not in item
        for item in second["observation_manifest"]["checkpoints"]
    )
    assert (
        result["full_timeline_index"]["index_hash"]
        == second["full_timeline_index"]["index_hash"]
    )
    assert result["build_manifest"] == second["build_manifest"]


def test_source_plan_config_carries_derived_storage_cap():
    class Plan:
        repo_root = Path("/repo")
        output_root = Path("/repo/output")
        sources = ()
        model_snapshots: ClassVar = {
            "vision_semantic": {"snapshot_path": "models/clip"},
            "speech": {"snapshot_path": "models/whisper"},
            "ambient": {"snapshot_path": "models/ast"},
            "vision_routing": {"haar_snapshot_path": "models/haar.xml"},
        }
        raw: ClassVar = {
            "storage_caps": {"derived_artifacts_hard_fail_cap_mib": 512}
        }

    from av_trace_mini_pilot_index.core import _config_from_source_plan

    config = _config_from_source_plan(Plan())
    assert config.derived_artifacts_hard_fail_cap_mib == 512


def test_indexes_search_and_forbidden_rights_fields(tmp_path: Path):
    config = make_fixture_repo(tmp_path, source_count=1)
    sources = load_sources(
        tmp_path, config.source_manifest_paths, expected_source_count=1
    )
    segments = build_segment_manifest(tmp_path, sources)
    observations = build_observation_manifest(
        tmp_path,
        config,
        sources,
        segments,
        model_backend=FakeModels(),
        media_backend=FakeMedia(),
        routing_extractor=fake_routing,
    )
    index = build_full_timeline_index(tmp_path, segments, observations)
    assert search_speech(index, "quantum mechanics", top_k=2)
    assert search_ambient(index, "writing", top_k=2)
    assert search_visual(
        index,
        "board",
        top_k=2,
        text_vector=np.array([1.0, 0.0, 0.0, 0.0]),
    )
    searchable = json.dumps(index["modalities"])
    assert "restricted_processing_status" not in searchable
    assert "license_attribution_boundary" not in searchable
    with pytest.raises(MiniPilotIndexError, match="FORBIDDEN_SEARCH_FIELD"):
        _assert_search_record_safe(
            {"segment_id": "x", "rights_flags": {"release": False}}
        )
    _assert_search_record_safe(
        {
            "segment_id": "x",
            "tokens": ["rights", "question"],
            "term_frequency": {"rights": 1, "question": 1},
        }
    )


def test_rrf_deterministic_and_collapses_matching_temporal_groups():
    base = {
        "result_type": "segment_pointer",
        "source_ref": "source",
        "start_us": 0,
        "end_us": 8_000_000,
        "scale": "fine",
        "score": 1.0,
        "generic_preview": "x",
        "result_id": "p",
    }
    speech = {**base, "segment_id": "speech", "modality": "speech"}
    ambient = {**base, "segment_id": "ambient", "modality": "ambient"}
    one = search_fused({"speech": [speech], "ambient": [ambient]}, top_k=5)
    two = search_fused({"ambient": [ambient], "speech": [speech]}, top_k=5)
    assert one == two
    assert len(one) == 1
    assert one[0]["fused_modalities"] == ["ambient", "speech"]


def test_workstream_a_source_plan_adapter_uses_frozen_counts():
    root = Path(__file__).resolve().parents[1]
    plan = load_source_plan(root, hash_files=False)
    manifest = build_segment_manifest(root, plan)
    assert manifest["source_count"] == 4
    assert manifest["totals"] == {
        "base_cells": 3208,
        "context_windows": 800,
        "fine_windows": 3204,
        "windows": 4004,
        "maximum_modality_records": 12012,
    }
