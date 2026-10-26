from __future__ import annotations

import json
from pathlib import Path

from av_trace import SchemaRegistry, validate_trajectory
from av_trace.util import load_json
from av_trace_agent_runtime import RuntimeConfig
from av_trace_media_pipeline.backend import MediaRegistration
from av_trace_media_pipeline.experiment import _observed_route_ids, _run_one
from av_trace_media_pipeline.indexing import build_media_index

from .conftest import ROOT


def _registration(asset_id: str) -> MediaRegistration:
    root = ROOT / "mvp/generated/full"
    source = next(
        item
        for item in load_json(root / "corpus_index.json")["sources"]
        if item["source_id"] == asset_id
    )
    return MediaRegistration(
        asset_id=asset_id,
        path=root / source["media_path"],
        media_hash=source["media_sha256"],
    )


def test_media_index_is_deterministic_and_covers_every_registered_evidence(corpus):
    first = build_media_index(
        generated_root=ROOT / "mvp/generated/full",
        families=corpus.families,
    )
    second = build_media_index(
        generated_root=ROOT / "mvp/generated/full",
        families=corpus.families,
    )
    assert first.index.to_document() == second.index.to_document()
    assert first.build_record == second.build_record
    expected = {
        evidence["evidence_id"]
        for family in corpus.families
        for evidence in family["claim_evidence_graph"]["evidence_units"]
    }
    observed = {
        evidence_id
        for record in first.index.records
        for evidence_id in record.route_evidence_ids
    }
    assert observed == expected
    serialized = json.dumps(first.index.to_document()).casefold()
    assert "accepted_sufficient_sets" not in serialized
    assert "necessity_groups" not in serialized
    assert "claim_syn_" not in serialized


def test_subprocess_trajectory_contains_media_provenance(corpus, media_index):
    family = corpus.family("syn_f01_visual_order")
    trajectory = _run_one(
        corpus=corpus,
        family=family,
        state_role="CLEAN",
        agent="EvidenceBeliefState",
        media_index=media_index,
        media=_registration("syn_source_01"),
        registry=SchemaRegistry(ROOT),
        runtime_config=RuntimeConfig(timeout_s=20, seed=17),
    )
    assert validate_trajectory(trajectory).ok
    observations = [
        result
        for event in trajectory["events"]
        for result in event.get("response", {}).get("results", ())
        if result.get("result_type") == "observation"
    ]
    assert observations
    assert all("media_provenance" in item["payload"] for item in observations)
    assert _observed_route_ids(family, trajectory) == [
        "s1_blue_triangle",
        "s1_green_circle",
    ]
