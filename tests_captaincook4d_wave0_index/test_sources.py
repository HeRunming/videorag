from __future__ import annotations

import json
from pathlib import Path

import pytest

from av_trace_captaincook4d_wave0_index.sources import (
    CaptainCook4DWave0SourceError,
    computed_counts,
    load_plan_definition,
    load_source_plan,
)

ROOT = Path(__file__).resolve().parents[1]
PLAN = (
    ROOT
    / "data/rehearsal_plan/"
    "captaincook4d_wave0_full_timeline_index_v1.json"
)


def test_repository_plan_binds_task188_and_three_sources():
    plan_file, plan, source_root, acquisition, output = load_plan_definition(
        ROOT
    )
    assert plan_file == PLAN
    assert [item["source_id"] for item in plan["sources"]] == [
        "16_20",
        "15_29",
        "26_22",
    ]
    assert source_root == (
        ROOT / "data/restricted/captaincook4d_wave0_sources_v3"
    )
    assert acquisition.name == "captaincook4d_wave0_acquisition_manifest.json"
    assert output == (
        ROOT / "data/restricted/captaincook4d_wave0_index_v1"
    )


@pytest.mark.parametrize(
    ("duration", "expected"),
    (
        (
            1930.9,
            {
                "base_cells": 483,
                "fine_windows": 482,
                "context_windows": 120,
                "temporal_segments": 602,
                "whisper_chunks": 65,
                "checkpoints": 4,
            },
        ),
        (
            1292.82,
            {
                "base_cells": 324,
                "fine_windows": 323,
                "context_windows": 80,
                "temporal_segments": 403,
                "whisper_chunks": 44,
                "checkpoints": 4,
            },
        ),
        (
            1324.22,
            {
                "base_cells": 332,
                "fine_windows": 331,
                "context_windows": 82,
                "temporal_segments": 413,
                "whisper_chunks": 45,
                "checkpoints": 4,
            },
        ),
    ),
)
def test_lattice_counts_are_frozen(duration: float, expected: dict[str, int]):
    assert computed_counts(duration) == expected


def test_repository_loader_accepts_task188_ready():
    plan = load_source_plan(ROOT)
    assert [item.source_id for item in plan.sources] == [
        "16_20",
        "15_29",
        "26_22",
    ]
    assert [item.person_id for item in plan.sources] == [1, 2, 3]
    assert [item.environment_id for item in plan.sources] == [8, 2, 3]
    assert plan.acquisition_manifest_sha256 == (
        "ee50c9579b77f7ee4f45753adad1d5d1e09569c6b1be5308a82ccbcc9a05934a"
    )


def test_tampered_acquisition_manifest_hash_is_rejected(tmp_path: Path):
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    plan_path = tmp_path / "plan.json"
    plan["authoritative_input_bindings"] = {}
    plan["scope"]["acquisition_manifest_sha256"] = "0" * 64
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(
        CaptainCook4DWave0SourceError,
        match="ACQUISITION_MANIFEST_HASH_MISMATCH",
    ):
        load_source_plan(
            ROOT,
            plan_path=plan_path,
            hash_files=False,
            verify_models=False,
        )


def test_staging_media_path_is_rejected(tmp_path: Path):
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    plan["authoritative_input_bindings"] = {}
    plan["sources"][0]["media_path"] = (
        "data/restricted/captaincook4d_wave0_sources_v3/.staging/"
        "16_20_360p.mp4"
    )
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(
        CaptainCook4DWave0SourceError, match="MEDIA_PATH_INVALID"
    ):
        load_plan_definition(
            ROOT,
            plan_path=plan_path,
            verify_bound_inputs=False,
            verify_models=False,
        )
