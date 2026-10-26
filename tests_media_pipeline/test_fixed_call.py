from __future__ import annotations

from av_trace import SchemaRegistry, validate_trajectory
from av_trace_agent_runtime import RuntimeConfig
from av_trace_media_pipeline.backend import MediaRegistration
from av_trace_media_pipeline.certification import verify_certified_dataset
from av_trace_media_pipeline.experiment import AGENTS, _run_one
from av_trace.util import load_json

from .conftest import ROOT


def test_all_four_agents_cross_subprocess_boundary_on_fixed_call_fixture(
    corpus, media_index
):
    binding = verify_certified_dataset(
        corpus, validator_root=ROOT / "mvp/validator/generated"
    )
    family = binding.fixed_call_family
    source = next(
        item
        for item in load_json(
            ROOT / "mvp/generated/full/corpus_index.json"
        )["sources"]
        if item["source_id"] == family["source"]["asset_id"]
    )
    media = MediaRegistration(
        asset_id=source["source_id"],
        path=ROOT / "mvp/generated/full" / source["media_path"],
        media_hash=source["media_sha256"],
    )
    for agent in AGENTS:
        trajectory = _run_one(
            corpus=corpus,
            family=family,
            state_role="RESTORED",
            agent=agent,
            media_index=media_index,
            media=media,
            registry=SchemaRegistry(ROOT),
            runtime_config=RuntimeConfig(timeout_s=20, seed=29),
        )
        assert validate_trajectory(trajectory).ok
        assert [
            index
            for index, event in enumerate(trajectory["events"])
            if event.get("active_hook_ids")
        ] == [binding.fixed_call_case["trigger_value"]]
