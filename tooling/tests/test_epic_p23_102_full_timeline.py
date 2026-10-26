from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
BUILD_PATH = ROOT / "scripts/build_epic_p23_102_full_timeline.py"
VERIFY_PATH = ROOT / "scripts/verify_epic_p23_102_full_timeline.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


BUILD = load_module(BUILD_PATH, "epic_p23_102_full_timeline_build")
VERIFY = load_module(VERIFY_PATH, "epic_p23_102_full_timeline_verify")


def canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value))
    path.chmod(mode)


def fixture_plan() -> dict:
    plan = json.loads(
        (
            ROOT
            / "data/rehearsal_plan/epic_p23_102_full_timeline_index_v1.json"
        ).read_text()
    )
    plan["synthetic_fixture"] = True
    source = plan["source"]
    source["official_duration_seconds"] = 9.5
    source["official_content_length_bytes"] = len(b"fixture-media")
    source["official_md5"] = hashlib.md5(
        b"fixture-media", usedforsecurity=False
    ).hexdigest()
    source["expected_final_media_path"] = (
        "data/restricted/epic_p23_102_source_v1/media/P23/P23_102.MP4"
    )
    source["acquisition_manifest_path"] = (
        "data/restricted/epic_p23_102_source_v1/manifests/"
        "epic_p23_102_exact_manifest.json"
    )
    plan["totals"] = BUILD.expected_counts(9.5)
    for model in plan["model_snapshots"].values():
        model["snapshot_path"] = f"models/{model['model_id'].split('/')[-1]}"
        model["files"] = [
            {
                "path": "weights.bin",
                "bytes": len(model["model_id"].encode()),
                "sha256": hashlib.sha256(model["model_id"].encode()).hexdigest(),
            }
        ]
    plan["scope"]["source_root"] = "data/restricted/epic_p23_102_source_v1"
    plan["scope"]["output_root"] = "output/full"
    plan["scope"]["smoke_output_root"] = "output/smoke"
    plan["storage"]["hard_cap_mib"] = 16
    return plan


def make_repo(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "repo"
    root.mkdir()
    plan = fixture_plan()
    media = root / plan["source"]["expected_final_media_path"]
    media.parent.mkdir(parents=True)
    media.write_bytes(b"fixture-media")
    media.chmod(0o600)
    media.parent.chmod(0o700)
    for model in plan["model_snapshots"].values():
        weight = root / model["snapshot_path"] / "weights.bin"
        weight.parent.mkdir(parents=True)
        weight.write_bytes(model["model_id"].encode())
    media_sha256 = file_hash(media)
    manifest = {
        "schema_version": "av-trace.epic-p23-102-exact-manifest/1.0",
        "status": "COMPLETE_VERIFIED_READY",
        "source": {
            "asset_id": "P23_102",
            "license": "CC-BY-NC-4.0",
        },
        "media": {
            "path": plan["source"]["expected_final_media_path"],
            "bytes": media.stat().st_size,
            "md5": hashlib.md5(
                media.read_bytes(), usedforsecurity=False
            ).hexdigest(),
            "sha256": media_sha256,
        },
        "technical_validation": {
            "ffprobe_passed": True,
            "av_duration_delta_seconds": 0.01,
            "video": {
                "codec_name": "hevc",
                "codec_tag_string": "hvc1",
                "width": 1920,
                "height": 1080,
            },
            "audio": {
                "codec_name": "aac",
                "codec_tag_string": "mp4a",
                "sample_rate_hz": 48000,
                "channels": 2,
                "channel_layout": "stereo",
            },
        },
        "license_and_usage_boundary": {
            "operative_license": "CC-BY-NC-4.0",
            "noncommercial_only": True,
        },
        "scope": {"semantic_annotations_opened_or_used": False},
    }
    write_json(root / plan["source"]["acquisition_manifest_path"], manifest)
    plan_path = (
        root / "data/rehearsal_plan/epic_p23_102_full_timeline_index_v1.json"
    )
    write_json(plan_path, plan, mode=0o644)
    return root, plan_path


class FakeMedia:
    def __init__(self) -> None:
        self.probe_calls = 0
        self.frame_calls = 0
        self.audio_calls = 0

    def probe(self, path: Path) -> dict:
        assert path.name == "P23_102.MP4"
        self.probe_calls += 1
        return {
            "video_codec": "hevc",
            "audio_codec": "aac",
            "video_width": 1920,
            "video_height": 1080,
            "audio_rate_hz": 48000,
            "audio_channels": 2,
        }

    def iter_sampled_frames(self, path: Path, cells: list[dict]):
        del path
        self.frame_calls += 1
        for index, cell in enumerate(cells):
            yield cell, np.full(
                (8, 8, 3), index % 255, dtype=np.uint8
            )

    def decode_audio(self, path: Path, target_rate: int) -> np.ndarray:
        del path
        self.audio_calls += 1
        duration = 9.5
        samples = round(target_rate * duration)
        timeline = np.arange(samples, dtype=np.float32) / target_rate
        return np.sin(2 * np.pi * 220 * timeline).astype(np.float32) * 0.1


class FakeModels:
    def whisper(self, identifiers, samples):
        return [
            {
                "chunk_id": identifier,
                "text": f"fixture speech {index}",
                "token_count": 3,
                "mean_generated_token_log_probability": -0.1,
                "quality_gate_pass": True,
                "quality_flags": [],
            }
            for index, (identifier, _) in enumerate(zip(identifiers, samples))
        ]

    def siglip_images(self, images):
        rows = []
        for index, _ in enumerate(images):
            value = np.zeros(8, dtype=np.float32)
            value[index % 8] = 1.0
            rows.append(value)
        return np.stack(rows)

    def clap_audio(self, samples, rate):
        del rate
        rows = []
        for index, _ in enumerate(samples):
            value = np.zeros(6, dtype=np.float32)
            value[index % 6] = 1.0
            rows.append(value)
        return np.stack(rows)


def test_plan_is_frozen_and_default_cli_does_not_execute() -> None:
    _, plan = BUILD.load_plan(ROOT)
    assert plan["source"]["source_id"] == "P23_102"
    assert plan["totals"] == {
        "base_cells": 893,
        "fine_windows": 892,
        "context_windows": 223,
        "temporal_segments": 1115,
        "speech_chunks": 119,
        "checkpoints": 4,
    }
    args = BUILD.build_parser().parse_args([])
    assert args.mode == "plan"
    assert args.resume is True


def test_plan_mode_succeeds_without_full_media(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    plan = fixture_plan()
    plan_path = (
        root / "data/rehearsal_plan/epic_p23_102_full_timeline_index_v1.json"
    )
    write_json(plan_path, plan, mode=0o644)
    result = BUILD.plan_or_validate(
        root,
        plan_path=plan_path,
        validate=False,
        allow_synthetic_fixture=True,
    )
    assert result["decision"] == BUILD.PIPELINE_TOKEN
    assert result["status"] == "PLANNED_ACQUISITION_PENDING"
    assert result["media_decoded"] is False
    assert result["models_loaded"] is False
    assert not (root / "output").exists()


def test_synthetic_build_resume_and_independent_verifier(tmp_path: Path) -> None:
    root, plan_path = make_repo(tmp_path)
    media = FakeMedia()
    first = BUILD.build_index(
        root,
        plan_path=plan_path,
        media_backend=media,
        model_backend=FakeModels(),
        validate_model_files=True,
        allow_synthetic_fixture=True,
    )
    output = root / first["build_manifest"]["output_dir"]
    first_hashes = {
        path.relative_to(output).as_posix(): file_hash(path)
        for path in output.rglob("*")
        if path.is_file()
    }
    first_mtimes = {
        path.relative_to(output).as_posix(): path.stat().st_mtime_ns
        for path in (output / "checkpoints").rglob("*.json")
    }
    second_media = FakeMedia()
    second = BUILD.build_index(
        root,
        plan_path=plan_path,
        media_backend=second_media,
        model_backend=FakeModels(),
        validate_model_files=True,
        allow_synthetic_fixture=True,
    )
    second_hashes = {
        path.relative_to(output).as_posix(): file_hash(path)
        for path in output.rglob("*")
        if path.is_file()
    }
    second_mtimes = {
        path.relative_to(output).as_posix(): path.stat().st_mtime_ns
        for path in (output / "checkpoints").rglob("*.json")
    }
    assert first_hashes == second_hashes
    assert first_mtimes == second_mtimes
    assert second_media.probe_calls == 0
    assert second_media.frame_calls == 0
    assert second_media.audio_calls == 0
    assert second["build_manifest"]["build_manifest_hash"] == first[
        "build_manifest"
    ]["build_manifest_hash"]
    verified = VERIFY.verify_index(
        root,
        plan_path=plan_path,
        output_root=output,
        rehash_source=True,
        allow_synthetic_fixture=True,
    )
    assert verified["verified"] is True, verified["failures"]
    index = first["full_timeline_index"]
    assert BUILD.search_speech(index, "fixture", top_k=2)
    vision_query = [1.0] + [0.0] * 7
    audio_query = [1.0] + [0.0] * 5
    assert BUILD.search_vector(
        index, "siglip2_visual", vision_query, top_k=1
    )
    assert BUILD.search_vector(index, "clap_audio", audio_query, top_k=1)


def test_verifier_rejects_checkpoint_tamper(tmp_path: Path) -> None:
    root, plan_path = make_repo(tmp_path)
    result = BUILD.build_index(
        root,
        plan_path=plan_path,
        media_backend=FakeMedia(),
        model_backend=FakeModels(),
        validate_model_files=True,
        allow_synthetic_fixture=True,
    )
    output = root / result["build_manifest"]["output_dir"]
    checkpoint = output / "checkpoints/P23_102/speech_asr.json"
    body = json.loads(checkpoint.read_text())
    body["payload"]["chunks"][0]["text"] = "tampered"
    checkpoint.write_bytes(canonical(body))
    checkpoint.chmod(0o600)
    verified = VERIFY.verify_index(
        root,
        plan_path=plan_path,
        output_root=output,
        rehash_source=False,
        allow_synthetic_fixture=True,
    )
    assert verified["verified"] is False
    assert any("checkpoint_" in item for item in verified["failures"])


def test_documents_encode_required_nonclaims() -> None:
    plan_text = (
        ROOT
        / "data/rehearsal_plan/epic_p23_102_full_timeline_index_v1.json"
    ).read_text()
    design_text = (
        ROOT / "docs/design/epic_p23_102_full_timeline_v1.md"
    ).read_text()
    for required in (
        "CC-BY-NC-4.0",
        '"development_only": true',
        '"future_test_eligible": false',
        '"semantic_annotations_used_during_source_selection": false',
        '"human_review_performed": false',
        '"ses_assigned": false',
        '"h_tier_assigned": false',
        '"gate_a_claimed": false',
    ):
        assert required in plan_text
    assert "EPIC_P23_102_FULL_TIMELINE_PIPELINE_READY" in design_text
    assert "**Built-index token:** intentionally not issued" in design_text
    assert "10,814,161,307" in design_text
    assert os.path.basename(BUILD_PATH) in design_text
