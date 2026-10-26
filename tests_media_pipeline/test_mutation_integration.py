from __future__ import annotations

from av_trace import SchemaRegistry
from av_trace.util import load_json, sha256_json
from av_trace_agent_runtime import RuntimeConfig
from av_trace_media_pipeline.backend import MediaRegistration
from av_trace_media_pipeline.certification import verify_certified_dataset
from av_trace_media_pipeline.experiment import (
    MUTATIONS,
    _mutation_comparison,
    _run_one,
)
from av_trace_media_pipeline.indexing import build_media_index

from .conftest import ROOT


def _original_registration(asset_id: str) -> MediaRegistration:
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


def test_three_media_mutations_change_affected_case_and_preserve_control(
    corpus, media_index
):
    binding = verify_certified_dataset(
        corpus, validator_root=ROOT / "mvp/validator/generated"
    )
    fixture_hashes = {
        item["path"]: item["sha256"]
        for item in load_json(
            ROOT / "mvp/media_backed/fixtures/fixture_hashes.json"
        )["fixtures"]
    }
    families = {item["family_id"]: item for item in corpus.families}
    registry = SchemaRegistry(ROOT)
    config = RuntimeConfig(timeout_s=20, seed=23)
    agent = "EvidenceBeliefState"
    for spec in MUTATIONS:
        original = {}
        mutated = {}
        mutation_registration = MediaRegistration(
            asset_id=spec["asset_id"],
            path=ROOT / "mvp/media_backed/fixtures" / spec["fixture"],
            media_hash=fixture_hashes[spec["fixture"]],
        )
        mutated_media_index = build_media_index(
            generated_root=ROOT / "mvp/generated/full",
            families=corpus.families,
            media_overrides={
                spec["asset_id"]: (
                    mutation_registration.path,
                    mutation_registration.media_hash,
                )
            },
            require_full_coverage=False,
        )
        assert any(
            item["asset_id"] == spec["asset_id"]
            and item["media_hash"] == mutation_registration.media_hash
            and item["overridden"] is True
            for item in mutated_media_index.build_record["sources"]
        )
        affected = families[spec["affected_family"]]
        affected_ids = {
            item["evidence_id"]
            for item in affected["claim_evidence_graph"]["evidence_units"]
        }
        original_relevant = sorted(
            sha256_json(
                {
                    "interval": record.interval,
                    "modality": record.modality,
                    "search_text": record.search_text,
                    "payload": record.payload,
                }
            )
            for record in media_index.index.records
            if affected_ids.intersection(record.route_evidence_ids)
        )
        mutated_relevant = sorted(
            sha256_json(
                {
                    "interval": record.interval,
                    "modality": record.modality,
                    "search_text": record.search_text,
                    "payload": record.payload,
                }
            )
            for record in mutated_media_index.index.records
            if affected_ids.intersection(record.route_evidence_ids)
        )
        assert original_relevant != mutated_relevant
        for family_id in (spec["affected_family"], spec["control_family"]):
            family = families[family_id]
            original[(agent, family_id)] = _run_one(
                corpus=corpus,
                family=family,
                state_role="CLEAN",
                agent=agent,
                media_index=media_index,
                media=_original_registration(spec["asset_id"]),
                registry=registry,
                runtime_config=config,
            )
            mutated[(agent, family_id)] = _run_one(
                corpus=corpus,
                family=family,
                state_role="CLEAN",
                agent=agent,
                media_index=mutated_media_index,
                media=mutation_registration,
                registry=registry,
                runtime_config=config,
            )
        one_agent_spec = dict(spec)
        one_agent_spec["_denominator"] = binding.denominator
        # The helper's production matrix is four agents; supply four identical
        # named views here to verify the semantic mutation contract cheaply.
        from av_trace_media_pipeline import experiment

        old_agents = experiment.AGENTS
        experiment.AGENTS = (agent,)
        try:
            report = _mutation_comparison(
                mutation=one_agent_spec,
                original=original,
                mutated=mutated,
                families=families,
            )
        finally:
            experiment.AGENTS = old_agents
        assert report["passed"]
