from __future__ import annotations

import json
from pathlib import Path

import pytest

from av_trace_mini_pilot_index.sources import SourcePlanError, load_source_plan

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "data/rehearsal_plan/mini_pilot_full_timeline_v1.json"


def _copied_plan(tmp_path: Path) -> tuple[Path, dict]:
    value = json.loads(PLAN.read_text(encoding="utf-8"))
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path, value


def test_loads_exact_four_sources_and_frozen_counts():
    plan = load_source_plan(ROOT)

    assert [source.source_id for source in plan.sources] == [
        "SG-OXFORD-QM-001",
        "SG-OXFORD-DHL-CONSCIOUSNESS",
        "SG-MIT-RES12-003-L01",
        "SG-YALE-PHYS200-L01",
    ]
    assert plan.totals["base_cells"] == 3208
    assert plan.totals["fine_windows"] == 3204
    assert plan.totals["context_windows"] == 800
    assert plan.totals["temporal_segments"] == 4004
    assert plan.totals["whisper_chunks"] == 430
    assert plan.totals["checkpoint_count"] == 16
    assert (
        plan.output_root.relative_to(plan.repo_root).as_posix()
        == "data/restricted/mini_pilot_index_v1"
    )


def test_media_and_sidecars_are_repo_relative_and_confined():
    plan = load_source_plan(ROOT, hash_files=False)

    for source in plan.sources:
        assert source.media_path.is_relative_to(plan.allowed_restricted_source_root)
        assert source.media_path.parent == source.source_directory
        assert len([stream for stream in source.streams if stream.kind == "video"]) == 1
        assert len([stream for stream in source.streams if stream.kind == "audio"]) == 1
        for sidecar in source.transcript_sidecars:
            assert sidecar.path.is_relative_to(source.source_directory)
            assert sidecar.index_use == "verification_only"


def test_official_transcripts_are_not_search_inputs():
    plan = load_source_plan(ROOT, hash_files=False)
    policy = plan.official_transcript_sidecar_policy

    assert policy["searchable"] is False
    assert policy["citable"] is False
    assert policy["training_label"] is False
    assert policy["family_or_evaluation_input"] is False
    assert plan.index_policy["speech"]["source"] == "Whisper only"
    assert plan.index_policy["speech"]["official_sidecars_searchable"] is False


def test_rejects_fifth_source(tmp_path: Path):
    path, value = _copied_plan(tmp_path)
    value["sources"].append(dict(value["sources"][0]))
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(SourcePlanError, match="PLAN_SOURCE_COUNT_MISMATCH"):
        load_source_plan(ROOT, plan_path=path, hash_files=False)


def test_rejects_source_outside_allowed_restricted_root(tmp_path: Path):
    path, value = _copied_plan(tmp_path)
    value["sources"][0]["media"]["path"] = "data/rehearsal_plan/not-media.mp4"
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(SourcePlanError, match="SOURCE_OUTSIDE_ALLOWED_ROOT"):
        load_source_plan(ROOT, plan_path=path, hash_files=False)


def test_rejects_evaluator_private_fields(tmp_path: Path):
    path, value = _copied_plan(tmp_path)
    value["sources"][0]["family_id"] = "must-not-enter-indexing"
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(SourcePlanError, match="EVALUATOR_PRIVATE_FIELD"):
        load_source_plan(ROOT, plan_path=path, hash_files=False)


def test_rejects_wrong_lattice_count(tmp_path: Path):
    path, value = _copied_plan(tmp_path)
    value["sources"][0]["expected_counts"]["fine_windows"] = 660
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(SourcePlanError, match="SOURCE_COUNT_MISMATCH"):
        load_source_plan(ROOT, plan_path=path, hash_files=False)


def test_rejects_missing_single_video_role(tmp_path: Path):
    path, value = _copied_plan(tmp_path)
    value["sources"][0]["media"]["role"] = "video"
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(SourcePlanError, match="PLAN_VIDEO_ROLE_MISMATCH"):
        load_source_plan(ROOT, plan_path=path, hash_files=False)


def test_rejects_acquisition_manifest_hash_drift(tmp_path: Path):
    path, value = _copied_plan(tmp_path)
    value["scope"]["acquisition_manifest_sha256"] = "0" * 64
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(SourcePlanError, match="ACQUISITION_MANIFEST_HASH_MISMATCH"):
        load_source_plan(ROOT, plan_path=path)


def test_rejects_model_revision_drift(tmp_path: Path):
    path, value = _copied_plan(tmp_path)
    value["model_snapshots"]["speech"]["revision"] = "moving-main"
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(SourcePlanError, match="MODEL_SNAPSHOT_IDENTITY_MISMATCH"):
        load_source_plan(ROOT, plan_path=path, hash_files=False)


def test_rejects_output_root_drift(tmp_path: Path):
    path, value = _copied_plan(tmp_path)
    value["scope"]["output_root"] = "data/restricted/other-index"
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(SourcePlanError, match="OUTPUT_ROOT_MISMATCH"):
        load_source_plan(ROOT, plan_path=path, hash_files=False)


def test_no_downstream_family_or_evaluation_stages():
    plan = load_source_plan(ROOT, hash_files=False)
    forbidden = set(plan.raw["scope"]["forbidden_downstream_stages"])

    assert "candidate-family generation" in forbidden
    assert "evaluation" in forbidden
    assert "family migration" in forbidden
    assert "agent or controller execution" in forbidden
