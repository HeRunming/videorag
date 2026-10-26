from __future__ import annotations

import json
from pathlib import Path

import pytest

from av_trace_mini_pilot_families import (
    FamilyInputError,
    load_canonical_new_source_index,
    parse_official_sidecar,
)
from av_trace_mini_pilot_families.contracts import json_hash


def test_canonical_adapter_rejects_missing_unfinished_index(tmp_path: Path):
    output = tmp_path / "data/restricted/mini_pilot_index_v1"
    output.mkdir(parents=True)
    (output / "segment_manifest.json").write_text("{}")
    with pytest.raises(FamilyInputError, match="CANONICAL_INDEX_INCOMPLETE"):
        load_canonical_new_source_index(tmp_path)


def test_canonical_adapter_rejects_smoke_index_before_mining(tmp_path: Path):
    output = tmp_path / "data/restricted/mini_pilot_index_v1"
    output.mkdir(parents=True)
    for name in (
        "segment_manifest.json",
        "observation_manifest.json",
        "full_timeline_index.json",
        "resource_manifest.json",
    ):
        (output / name).write_text("{}")
    (output / "build_manifest.json").write_text(
        json.dumps(
            {
                "status": "COMPLETE",
                "smoke_seconds": 8.0,
                "source_count": 4,
                "expected_source_count": 4,
            }
        )
    )
    with pytest.raises(FamilyInputError, match="SMOKE_INDEX_FORBIDDEN"):
        load_canonical_new_source_index(tmp_path)


def test_canonical_adapter_reads_frozen_counts_from_plan_totals(
    tmp_path: Path,
    monkeypatch,
):
    output = tmp_path / "data/restricted/mini_pilot_index_v1"
    output.mkdir(parents=True)
    plan_path = tmp_path / "data/rehearsal_plan/mini_pilot_full_timeline_v1.json"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text(
        json.dumps(
            {
                "totals": {
                    "base_cells": 1,
                    "fine_windows": 1,
                    "context_windows": 0,
                },
                "sources": [],
            }
        )
    )
    segment = {
        "totals": {
            "base_cells": 1,
            "fine_windows": 1,
            "context_windows": 0,
        }
    }
    segment["segment_manifest_hash"] = json_hash(segment)
    observation = {
        "all_sources_complete": True,
        "complete_source_refs": ["source-a"],
        "checkpoints": [],
    }
    observation["observation_manifest_hash"] = json_hash(observation)
    index = {"source_hashes": {"source-a": "a" * 64}}
    index["index_hash"] = json_hash(index)
    resource = {}
    resource["resource_manifest_hash"] = json_hash(resource)
    for name, value in (
        ("segment_manifest.json", segment),
        ("observation_manifest.json", observation),
        ("full_timeline_index.json", index),
        ("resource_manifest.json", resource),
    ):
        (output / name).write_text(json.dumps(value))
    build = {
        "status": "COMPLETE",
        "smoke_seconds": None,
        "source_count": 4,
        "expected_source_count": 4,
        "terminal_boundary": {
            "families_generated": False,
            "negatives_generated": False,
            "interventions_generated": False,
            "trajectories_generated": False,
            "evaluation_generated": False,
        },
    }
    (output / "build_manifest.json").write_text(json.dumps(build))
    monkeypatch.setattr(
        "av_trace_mini_pilot_families.adapters._verify_inventory_artifact",
        lambda *args, **kwargs: None,
    )
    loaded, hashes, routing, routes, provenance = (
        load_canonical_new_source_index(tmp_path)
    )
    assert loaded["source_hashes"] == {"source-a": "a" * 64}
    assert hashes == {"source-a": "a" * 64}
    assert routing == ()
    assert routes == ()
    assert provenance["complete_non_smoke_index_required"] is True


def test_official_srt_is_parsed_only_as_non_citable_route_challenge(
    tmp_path: Path,
):
    path = tmp_path / "sample.srt"
    path.write_text(
        "1\n00:00:01,000 --> 00:00:03,500\nA visible pendulum swings.\n",
        encoding="utf-8",
    )
    import hashlib

    digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    routes = parse_official_sidecar(
        source_ref="source-a",
        path=path,
        format_name="srt",
        timing="timed",
        expected_sha256=digest,
    )
    assert len(routes) == 1
    assert routes[0].start_us == 1_000_000
    assert routes[0].end_us == 3_500_000
    assert "pendulum" in routes[0].tokens
    assert routes[0].use == "derived_route_challenge_only"
