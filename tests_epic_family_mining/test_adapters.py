from __future__ import annotations

import json
from pathlib import Path

import pytest

from av_trace_epic_family_mining import (
    EpicFamilyInputError,
    load_canonical_epic_index,
    load_human_complete_prescreen,
)
from av_trace_epic_family_mining.contracts import json_hash


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    path.chmod(0o600)


def _sha(path: Path) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _self_hashed(value: dict, key: str) -> dict:
    output = dict(value)
    output[key] = json_hash(output)
    return output


def _canonical_fixture(tmp_path: Path, *, smoke: bool = False) -> Path:
    root = tmp_path / "data/restricted/epic_wave1_index_v1"
    root.mkdir(parents=True)
    root.chmod(0o700)
    source_hashes = {"P27_101": "2" * 64, "P28_103": "1" * 64}
    segment = _self_hashed(
        {
            "schema_version": "av-trace.epic-wave1-index/1.0",
            "stage": "RESTRICTED_EPIC_WAVE1_SOURCE_DERIVED_INDEX",
            "source_count": 2,
            "sources": [],
            "totals": {
                "base_cells": 4,
                "fine_windows": 4,
                "context_windows": 2,
                "windows": 6,
            },
        },
        "segment_manifest_hash",
    )
    checkpoint_records = []
    checkpoints = []
    for source_id in source_hashes:
        for name in (
            "speech.json",
            "ambient.json",
            "vision_routing.json",
            "vision_clip.json",
        ):
            path = root / "checkpoints" / source_id / name
            payload = {
                "records": (
                    [
                        {
                            "cell_id": f"cell.{source_id}.0",
                            "source_ref": source_id,
                            "features": {
                                "motion_or_change": 0.2,
                                "edge_density": 0.1,
                                "blank_frame": False,
                                "semantic_claim_allowed": False,
                            },
                        }
                    ]
                    if name == "vision_routing.json"
                    else []
                ),
                "semantic_claim_allowed": False,
            }
            _write(path, payload)
            checkpoints.append(
                {
                    "path": path.relative_to(tmp_path).as_posix(),
                    "sha256": _sha(path),
                    "size_bytes": path.stat().st_size,
                }
            )
            checkpoint_records.append(path)
    observation = _self_hashed(
        {
            "schema_version": "av-trace.epic-wave1-index/1.0",
            "stage": "RESTRICTED_EPIC_WAVE1_SOURCE_DERIVED_INDEX",
            "source_count": 2,
            "all_sources_complete": True,
            "complete_source_refs": ["P27_101", "P28_103"],
            "counts": {"whisper_chunks": 2},
            "checkpoints": checkpoints,
        },
        "observation_manifest_hash",
    )
    index = _self_hashed(
        {
            "schema_version": "av-trace.epic-wave1-index/1.0",
            "index_version": "epic-wave1-full-timeline-index/1.0",
            "stage": "RESTRICTED_EPIC_WAVE1_SOURCE_DERIVED_INDEX",
            "source_count": 2,
            "source_hashes": source_hashes,
            "segment_manifest_hash": segment["segment_manifest_hash"],
            "observation_manifest_hash": observation[
                "observation_manifest_hash"
            ],
            "modalities": {
                "vision": {"documents": []},
                "speech": {
                    "documents": [],
                    "document_count": 0,
                    "average_document_length": 0,
                    "document_frequency": {},
                },
                "ambient": {"documents": []},
            },
            "searchable_field_policy": {
                "evaluator_annotations_excluded": True,
                "rights_metadata_excluded": True,
            },
        },
        "index_hash",
    )
    resource = _self_hashed(
        {
            "schema_version": "av-trace.epic-wave1-index/1.0",
            "stage": "RESTRICTED_EPIC_WAVE1_SOURCE_DERIVED_INDEX",
            "acquisition_gate": {"passed": True},
        },
        "resource_manifest_hash",
    )
    for name, value in (
        ("segment_manifest.json", segment),
        ("observation_manifest.json", observation),
        ("full_timeline_index.json", index),
        ("resource_manifest.json", resource),
    ):
        _write(root / name, value)
    artifacts = [
        {
            "path": (root / name).relative_to(tmp_path).as_posix(),
            "sha256": _sha(root / name),
            "size_bytes": (root / name).stat().st_size,
        }
        for name in (
            "segment_manifest.json",
            "observation_manifest.json",
            "full_timeline_index.json",
            "resource_manifest.json",
        )
    ]
    build = _self_hashed(
        {
            "schema_version": "av-trace.epic-wave1-index/1.0",
            "stage": "RESTRICTED_EPIC_WAVE1_SOURCE_DERIVED_INDEX",
            "status": "COMPLETE",
            "mode": "smoke" if smoke else "full",
            "smoke_seconds": 32.0 if smoke else None,
            "source_count": 2,
            "expected_source_count": 2,
            "output_dir": root.relative_to(tmp_path).as_posix(),
            "plan_path": (
                "data/rehearsal_plan/"
                "epic_wave1_full_timeline_index_v1.json"
            ),
            "plan_sha256": "",
            "source_sha256": source_hashes,
            "terminal_boundary": {
                "last_allowed_stage": "resource_manifest",
                "families_generated": False,
                "interventions_generated": False,
                "trajectories_generated": False,
                "evaluation_generated": False,
            },
            "artifacts": artifacts,
        },
        "build_manifest_hash",
    )
    _write(root / "build_manifest.json", build)
    plan = {
        "sources": [
            {"source_id": "P28_103", "source_group_id": "P28"},
            {"source_id": "P27_101", "source_group_id": "P27"},
        ],
        "totals": {
            "base_cells": 4,
            "fine_windows": 4,
            "context_windows": 2,
            "temporal_segments": 6,
            "whisper_chunks": 2,
            "checkpoint_count": 8,
        },
    }
    _write(
        tmp_path
        / "data/rehearsal_plan/epic_wave1_full_timeline_index_v1.json",
        plan,
    )
    plan_path = (
        tmp_path / "data/rehearsal_plan/epic_wave1_full_timeline_index_v1.json"
    )
    build["plan_sha256"] = _sha(plan_path).removeprefix("sha256:")
    build.pop("build_manifest_hash")
    build["build_manifest_hash"] = json_hash(build)
    _write(root / "build_manifest.json", build)
    return root


def test_incomplete_index_fails_before_checkpoint_access(tmp_path):
    root = tmp_path / "data/restricted/epic_wave1_index_v1"
    root.mkdir(parents=True)
    with pytest.raises(
        EpicFamilyInputError, match="EPIC_CANONICAL_INDEX_INCOMPLETE_MISSING"
    ):
        load_canonical_epic_index(tmp_path)


def test_smoke_index_is_never_mining_input(tmp_path):
    _canonical_fixture(tmp_path, smoke=True)
    with pytest.raises(EpicFamilyInputError, match="EPIC_SMOKE_INDEX_FORBIDDEN"):
        load_canonical_epic_index(tmp_path)


def test_complete_fixture_loads_without_epic_semantic_annotations(tmp_path):
    _canonical_fixture(tmp_path)
    result = load_canonical_epic_index(tmp_path)
    assert sorted(result.source_hashes) == ["P27_101", "P28_103"]
    assert result.provenance["semantic_epic_annotations_accessed"] is False
    assert result.provenance["existing_annotation_vault_accessed"] is False


def test_existing_annotation_vault_path_is_rejected_before_read(tmp_path):
    from av_trace_epic_family_mining.adapters import _repo_path

    with pytest.raises(
        EpicFamilyInputError,
        match="EXISTING_ANNOTATION_VAULT_PATH_FORBIDDEN",
    ):
        _repo_path(tmp_path, "data/restricted/annotation_vault/actions.csv")


def test_semantic_epic_field_is_rejected():
    from av_trace_epic_family_mining.adapters import (
        _scan_forbidden_semantic_keys,
    )

    with pytest.raises(
        EpicFamilyInputError,
        match="SEALED_EPIC_SEMANTIC_FIELD_PRESENT",
    ):
        _scan_forbidden_semantic_keys(
            {"modalities": {"vision": {"action_label": "forbidden"}}}
        )


def test_incomplete_human_prescreen_fails_closed():
    root = Path(__file__).resolve().parents[1]
    with pytest.raises(
        EpicFamilyInputError, match="PRESCREEN_NOT_HUMAN_COMPLETE"
    ):
        load_human_complete_prescreen(
            root,
            plan_path=(
                "data/rehearsal_plan/"
                "semantic_av_source_prescreen_portable_blank_plan.json"
            ),
            form_path=(
                "data/rehearsal_plan/"
                "semantic_av_source_prescreen_portable_blank_form.json"
            ),
            report_path=(
                "data/rehearsal_plan/"
                "semantic_av_source_prescreen_portable_blank_import.json"
            ),
            source_groups={
                "portable-source-a": "portable-source-group-a",
                "portable-source-b": "portable-source-group-b",
            },
        )
