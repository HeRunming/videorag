from __future__ import annotations

import json
import stat
from pathlib import Path

import numpy as np
import pytest

from av_trace_scale1a.core import (
    _Models,
    Scale1AError,
    _checkpoint_key,
    _read_checkpoint,
    _write_checkpoint,
    _assert_search_record_safe,
    _displacement_summary_rows,
    _modality_action_diagnostic,
    _public_episode_rows,
    _query_reformulation_diagnostic,
    _summary_rows,
    _union_duration_us,
    _project_speech,
    _validate_final_output,
    build_interventions,
    build_segment_manifest,
    _query_rankings,
    search_fused,
    verify_trust_anchor,
)


ROOT = Path(__file__).resolve().parents[1]


def test_exact_segmentation_arithmetic_and_terminal_behavior():
    plan = json.loads((ROOT / "data/rehearsal_plan/scale1a_full_timeline_plan.json").read_text())
    manifest = build_segment_manifest(ROOT, plan)
    assert manifest["totals"] == {
        "base_cells": 3433,
        "fine_windows": 3428,
        "context_windows": 855,
        "windows": 4283,
        "maximum_modality_records": 12849,
    }
    for source in manifest["sources"]:
        cells = [x for x in manifest["base_cells"] if x["source_ref"] == source["source_ref"]]
        assert cells[-1]["end_us"] == source["duration_us"]
        assert 0 < cells[-1]["end_us"] - cells[-1]["start_us"] <= 4_000_000
        assert cells[-1]["sample_time_us"] < source["duration_us"]


def test_segment_ids_do_not_use_evaluator_fields():
    plan = json.loads((ROOT / "data/rehearsal_plan/scale1a_full_timeline_plan.json").read_text())
    manifest = build_segment_manifest(ROOT, plan)
    for item in manifest["segments"]:
        assert item["segment_id"].startswith("seg." + item["source_sha256"][:12])
        for forbidden in ("r004", "claim", "evidence", "clean", "blocked"):
            assert forbidden not in item["segment_id"].casefold()


def test_checkpoint_integrity_and_corruption_deletion(tmp_path: Path):
    path = tmp_path / "checkpoint.json"
    key = _checkpoint_key("abc", "layer/1", "fine", 0, "cfg")
    meta = _write_checkpoint(path, {"records": [{"x": 1}]}, key=key, record_count=1)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    payload, reused = _read_checkpoint(path, key=key, expected_count=1)
    assert payload == {"records": [{"x": 1}]}
    assert reused and reused["reused"]
    path.write_text(path.read_text().replace('"x": 1', '"x": 2'))
    payload, reused = _read_checkpoint(path, key=key, expected_count=1)
    assert payload is None and reused is None and not path.exists()


def test_forbidden_searchable_fields_fail_closed():
    with pytest.raises(Scale1AError, match="FORBIDDEN_SEARCH_FIELD"):
        _assert_search_record_safe({"segment_id": "x", "question": "leak"})
    _assert_search_record_safe({"segment_id": "x", "tokens": ["safe"]})
    _assert_search_record_safe(
        {
            "segment_id": "x",
            "tokens": ["question"],
            "term_frequency": {"question": 1, "answer": 2},
        }
    )


def test_rrf_is_deterministic_and_deduplicates_temporal_group():
    base = {
        "result_type": "segment_pointer", "source_ref": "s", "start_us": 0,
        "end_us": 8_000_000, "scale": "fine", "score": 1.0,
        "generic_preview": "x", "result_id": "p",
    }
    a = {**base, "segment_id": "a", "modality": "speech"}
    b = {**base, "segment_id": "b", "modality": "ambient"}
    one = search_fused({"speech": [a], "ambient": [b]}, top_k=5)
    two = search_fused({"ambient": [b], "speech": [a]}, top_k=5)
    assert one == two
    assert len(one) == 1
    assert one[0]["fused_modalities"] == ["ambient", "speech"]


def test_intervention_pretrigger_identity_and_negative_minimum():
    plan = {
        "families": [{
            "family_id": "f", "blocked": {"mechanism": "necessity_group_withholding"},
            "restored": {"trigger": "second distinct visual query"},
        }],
        "interventions": {
            "budgets": {"primary": {"max_steps": 10, "cost_limit": 12}},
            "common_invariants": [],
        },
    }
    migration = {"families": [{
        "family_id": "f", "migration_disposition": "retained",
        "support_segment_ids": {"vision": ["s"]},
    }]}
    negatives = {"families": [{
        "family_id": "f", "admitted": [{"negative_id": f"n{i}"} for i in range(5)]
    }]}
    result = build_interventions(plan, migration, negatives)["families"][0]
    assert result["invariants_passed"]
    assert result["blocked"] == result["restored_pretrigger"]
    assert not result["no_trigger"]["recovered"]


def test_metric_null_denominators():
    rows = [{
        "scope": "full_source_scoped", "state": "CLEAN", "policy": "p",
        "family_id": "f", "source_ref": "s", "displacement": False,
        "Evidence Recall": 1.0, "All-Evidence Success": 1.0,
        "Answer Score": 1.0, "Citation F1": 1.0,
        "Supported-Claim Rate": 1.0, "Success@Budget": 1.0,
        "Premature Stop": 0.0, "Recovery": None, "Modality Recall": None,
        "Recall@1": 1.0, "Recall@5": 1.0, "Recall@10": 1.0,
        "Recall@20": 1.0, "All-Evidence@1": 1.0,
        "All-Evidence@5": 1.0, "All-Evidence@10": 1.0,
        "All-Evidence@20": 1.0, "first_accepted_evidence_rank": 1,
        "inspected_video_fraction": 0.01, "distractor_burden": 0.0,
        "query_reformulation_gain": None, "modality_switches": 0,
        "modality_switch_rate": 0.0,
    }]
    summary = _summary_rows(rows)
    modality = next(x for x in summary if x["metric"] == "Modality Recall")
    assert modality["numerator"] is None
    assert modality["denominator"] == 0
    assert modality["value"] is None


def test_interval_union_does_not_double_count_overlapping_inspections():
    assert _union_duration_us(
        [(0, 8_000_000), (4_000_000, 12_000_000), (20_000_000, 24_000_000)]
    ) == 16_000_000


def test_public_episode_rows_remove_evaluator_private_identifiers():
    rows = _public_episode_rows([{
        "family_id": "private-family",
        "source_ref": "private-source",
        "observed_segment_ids": ["private-segment"],
        "strict_final_route_certificate": {"private": True},
        "scope": "full_source_scoped",
    }])
    assert rows == [{
        "case_id": rows[0]["case_id"],
        "scope": "full_source_scoped",
    }]
    assert rows[0]["case_id"].startswith("case-")


def test_displacement_aggregate_has_explicit_denominators():
    episodes = [
        {
            "displacement": True, "policy": "react-recovery",
            "displacement_eligible": True,
            "recovery_disabled": False, "family_id": "f1", "source_ref": "s1",
            "evidence_reacquired_after_displacement": True,
            "answer_recovered_after_displacement": False,
        },
        {
            "displacement": True, "policy": "react-recovery",
            "displacement_eligible": True,
            "recovery_disabled": False, "family_id": "f2", "source_ref": "s2",
            "evidence_reacquired_after_displacement": False,
            "answer_recovered_after_displacement": False,
        },
    ]
    rows = _displacement_summary_rows(episodes)
    reacquisition = next(
        row for row in rows
        if row["metric"] == "Evidence reacquisition after displacement"
    )
    assert reacquisition["numerator"] == 1.0
    assert reacquisition["denominator"] == 2
    assert reacquisition["value"] == 0.5


def test_query_reformulation_gain_uses_actual_search_observation_rounds():
    actions = [
        {
            "step": 0, "action": {"tool": "search_visual"},
            "response": {"status": "ok"},
        },
        {
            "step": 1, "action": {"tool": "inspect_clip"},
            "response": {
                "status": "ok", "restricted_response_ref": "obs.first",
                "modality": "vision",
            },
        },
        {
            "step": 2, "action": {"tool": "search_speech"},
            "response": {"status": "ok"},
        },
        {
            "step": 3, "action": {"tool": "read_transcript"},
            "response": {
                "status": "ok", "restricted_response_ref": "obs.second",
                "modality": "speech",
            },
        },
    ]
    result = _query_reformulation_diagnostic(
        actions,
        {"obs.first": ["e1"], "obs.second": ["e2"]},
        [{"e1", "e2"}],
    )
    assert result["eligible"]
    assert result["first_round_coverage"] == 0.5
    assert result["final_coverage"] == 1.0
    assert result["value"] == 0.5


def test_query_reformulation_gain_null_with_one_search():
    actions = [{
        "step": 0, "action": {"tool": "search_visual"},
        "response": {"status": "ok"},
    }]
    result = _query_reformulation_diagnostic(actions, {}, [{"e1"}])
    assert not result["eligible"]
    assert result["value"] is None


def test_modality_switch_sequence_includes_search_inspect_and_read():
    actions = [
        {
            "step": 0, "action": {"tool": "search_visual"},
            "response": {"status": "ok"},
        },
        {
            "step": 1, "action": {"tool": "inspect_clip"},
            "response": {
                "status": "ok", "restricted_response_ref": "o1",
                "modality": "vision",
            },
        },
        {
            "step": 2, "action": {"tool": "get_channel_status"},
            "response": {"status": "ok"},
        },
        {
            "step": 3, "action": {"tool": "search_speech"},
            "response": {"status": "ok"},
        },
        {
            "step": 4, "action": {"tool": "read_transcript"},
            "response": {
                "status": "ok", "restricted_response_ref": "o2",
                "modality": "speech",
            },
        },
        {
            "step": 5, "action": {"tool": "finalize"},
            "response": {"status": "ok"},
        },
    ]
    result = _modality_action_diagnostic(actions)
    assert [x["modality"] for x in result["evaluated_sequence"]] == [
        "vision", "vision", "speech", "speech",
    ]
    assert result["switch_count"] == 1
    assert result["transition_count"] == 3
    assert result["switch_rate"] == pytest.approx(1 / 3, abs=1e-6)


def test_task93_trust_anchor_currently_verifies():
    result = verify_trust_anchor(ROOT)
    assert result["verified"]
    assert len(result["source_bindings"]) == 5


def test_clip_gate_uses_restricted_technical_gate_not_redistribution_gate():
    manifest = ROOT / "data/restricted/noaa01/models/scale1a_clip_acquisition_manifest.json"
    if manifest.exists():
        record = json.loads(manifest.read_text())
        assert record.get("technical_inference_decision") == "CLIP_SNAPSHOT_READY"
        assert record.get("redistribution_decision") == "NOT_AUTHORIZED"
        assert record.get("decision") == "CONDITIONAL_GO"
    else:
        assert not manifest.exists()


def test_clip_transformers5_adapter_returns_joint_512d_embeddings():
    manifest = ROOT / "data/restricted/noaa01/models/scale1a_clip_acquisition_manifest.json"
    if not manifest.exists():
        pytest.skip("Task 94 snapshot is not present")
    record = json.loads(manifest.read_text())
    if record.get("technical_inference_decision") != "CLIP_SNAPSHOT_READY":
        pytest.skip("Task 94 technical inference gate is not ready")
    models = _Models(
        ROOT, threads=1, load_whisper=False, load_ast=False, load_clip=True
    )
    image = np.zeros((224, 224, 3), dtype=np.uint8)
    image[:, :, 0] = np.arange(224, dtype=np.uint8)[None, :]
    visual = models.clip_images([image])
    textual = models.clip_text(["a synthetic gradient"])
    assert visual.shape == (1, 512)
    assert textual.shape == (1, 512)
    assert visual.dtype == np.float32
    assert textual.dtype == np.float32
    assert np.allclose(np.linalg.norm(visual, axis=1), 1.0, atol=1e-6)
    assert np.allclose(np.linalg.norm(textual, axis=1), 1.0, atol=1e-6)


def test_cross_modal_temporal_binding_is_label_independent(monkeypatch):
    index = {
        "modalities": {
            "vision": {
                "ready": True,
                "documents": [
                    {
                        "segment_id": "v-bound",
                        "source_ref": "source",
                        "scale": "fine",
                        "start_us": 4_000_000,
                        "end_us": 12_000_000,
                        "modality": "vision",
                        "vector_f16_hex": np.zeros(512, dtype="<f2").tobytes().hex(),
                        "dimension": 512,
                        "searchable": True,
                    }
                ],
            },
            "speech": {
                "document_count": 1,
                "average_document_length": 1.0,
                "document_frequency": {"storm": 1},
                "documents": [
                    {
                        "segment_id": "s-anchor",
                        "source_ref": "source",
                        "scale": "fine",
                        "start_us": 4_000_000,
                        "end_us": 12_000_000,
                        "modality": "speech",
                        "tokens": ["storm"],
                        "term_frequency": {"storm": 1},
                        "searchable": True,
                    }
                ],
            },
            "ambient": {"documents": []},
        }
    }
    family = {
        "asset_id": "source",
        "provisional_modalities": ["speech", "vision"],
        "query_families": ["storm"],
    }

    class FakeModels:
        def __init__(self, *args, **kwargs):
            pass

        def clip_text(self, texts):
            return np.zeros((len(texts), 512), dtype=np.float32)

    monkeypatch.setattr("av_trace_scale1a.core._Models", FakeModels)
    rankings = _query_rankings(
        ROOT, index, family, source_scoped=True, top_k=20
    )
    assert rankings["vision"][0]["segment_id"] == "v-bound"
    assert rankings["vision"][0]["temporal_binding_from"] == "speech"


def test_task97_speech_records_are_unique_chunk_level_records():
    chunks = [
        {
            "chunk_id": "speech.source.000001",
            "source_ref": "source",
            "start_us": 30_000_000,
            "end_us": 60_000_000,
            "text": "unique evidence",
            "quality_gate_pass": True,
        }
    ]
    overlapping_segments = [
        {
            "segment_id": "fine-a", "source_ref": "source", "scale": "fine",
            "start_us": 28_000_000, "end_us": 36_000_000,
        },
        {
            "segment_id": "context-b", "source_ref": "source",
            "scale": "context", "start_us": 32_000_000,
            "end_us": 64_000_000,
        },
    ]
    records = _project_speech(chunks, overlapping_segments)
    assert len(records) == 1
    assert records[0]["scale"] == "speech_chunk_30s"
    assert records[0]["derived_from_chunk_ids"] == ["speech.source.000001"]
    assert records[0]["start_us"] == 30_000_000
    assert records[0]["end_us"] == 60_000_000


def test_task97_current_speech_lineage_and_blocked_closure():
    index = json.loads(
        (ROOT / "data/restricted/noaa01/scale1a/full_timeline_index.json").read_text()
    )
    migration = json.loads(
        (ROOT / "data/restricted/noaa01/scale1a/migrated_families.json").read_text()
    )
    interventions = json.loads(
        (ROOT / "data/restricted/noaa01/scale1a/interventions.json").read_text()
    )
    speech = index["modalities"]["speech"]["documents"]
    assert len(speech) == 461
    assert len({x["segment_id"] for x in speech}) == 461
    assert all(len(x["derived_from_chunk_ids"]) == 1 for x in speech)
    assert all(len(ids) == 1 for ids in index["speech_lineage"]["chunk_to_record_ids"].values())
    by_family = {x["family_id"]: x for x in migration["families"]}
    by_intervention = {x["family_id"]: x for x in interventions["families"]}
    lineage = {
        x["segment_id"]: set(x["derived_from_chunk_ids"]) for x in speech
    }
    for family_id in (
        "noaa01-r016-three-factors-vs",
        "noaa01-r017-north-atlantic-basin",
    ):
        support_ids = set(by_family[family_id]["support_segment_ids"]["speech"])
        support_chunks = set().union(*(lineage[x] for x in support_ids))
        closure = {
            record_id for record_id, chunks in lineage.items()
            if chunks & support_chunks
        }
        blocked = set(
            by_intervention[family_id]["blocked"]["suppressed_segment_ids"]
        )
        assert closure
        assert closure <= blocked
        assert by_intervention[family_id]["blocked"]["closure_proof"][
            "searchable_records_remaining_from_support_chunks"
        ] == []


def test_task97_current_trajectories_are_action_level_and_blind():
    episodes = json.loads(
        (ROOT / "data/restricted/noaa01/scale1a/trajectories.json").read_text()
    )["episodes"]
    ordinary = [x for x in episodes if x["experiment_role"] == "ordinary"]
    controls = [
        x for x in episodes
        if x["experiment_role"] == "restored_no_trigger_control"
    ]
    displaced = [
        x for x in episodes
        if x["experiment_role"] == "hard_negative_displacement"
    ]
    assert len(ordinary) == 120
    assert len(controls) == 10
    assert len(displaced) == 8
    assert len(episodes) == 138
    for episode in episodes:
        assert episode["actions"]
        assert episode["actions"][-1]["action"]["tool"] == "finalize"
        assert episode["steps_used"] == len(episode["actions"])
        assert episode["steps_used"] <= episode["budget"]["max_steps"]
        assert episode["cost_used"] <= episode["budget"]["cost_limit"]
        assert not any(episode["policy_blindness"].values())
        route = episode["strict_final_route_certificate"]["route_feasibility"]
        assert route["eligibility_proven"]
        assert "actual_final_decision_point" in route
        for action in episode["actions"]:
            visible = json.dumps(action["action"], sort_keys=True)
            assert "noaa01-r" not in visible
            assert "claim.r" not in visible
            assert "e.r" not in visible


def test_task97_strict_claim_scoring_fails_closed_and_abstention_is_null():
    family = {
        "provisional_modalities": ["speech"],
        "evidence_units": [
            {"evidence_id": "e.private", "modality": "speech"}
        ],
        "claims": [
            {
                "claim_id": "claim.private",
                "semantic_terms": ["north atlantic basin"],
                "support_evidence_ids": ["e.private"],
            }
        ],
    }
    observation = {"observation_id": "obs.public"}
    evidence_map = {"obs.public": ["e.private"]}
    good = _validate_final_output(
        family,
        {
            "verdict": "sufficient", "abstention": False,
            "answer": "North Atlantic Basin",
            "asserted_claims": [{
                "claim_handle": "slot.speech.1",
                "text": "North Atlantic Basin",
                "citation_ids": ["obs.public"],
            }],
            "claim_to_citations": {"slot.speech.1": ["obs.public"]},
        },
        [observation],
        evidence_map,
    )
    assert good["output_valid"]
    assert good["required_claims_correct"]
    assert good["supported_claim_rate"] == 1.0
    bad = _validate_final_output(
        family,
        {
            "verdict": "sufficient", "abstention": False,
            "answer": "North Atlantic Basin",
            "asserted_claims": [{
                "claim_handle": "claim.private",
                "text": "North Atlantic Basin",
                "citation_ids": ["missing"],
            }],
            "claim_to_citations": {"claim.private": ["missing"]},
        },
        [observation],
        evidence_map,
    )
    assert not bad["output_valid"]
    abstain = _validate_final_output(
        family,
        {
            "verdict": "insufficient", "abstention": True, "answer": "",
            "asserted_claims": [], "claim_to_citations": {},
        },
        [observation],
        evidence_map,
    )
    assert abstain["supported_claim_rate"] is None


def test_task97_visual_negative_eligibility_is_fail_closed():
    negatives = json.loads(
        (ROOT / "data/restricted/noaa01/scale1a/hard_negatives.json").read_text()
    )
    for family in negatives["families"]:
        for candidate in family.get(
            "machine_provisional_hard_negative_candidates", []
        ):
            if candidate["modality"] == "vision":
                assert not candidate["admitted"]
                assert not candidate[
                    "eligible_for_validated_hard_negative_metrics"
                ]
                assert candidate["independent_content_checks"] == []
                assert candidate["answer_alias_scan"][
                    "vacuous_for_vector_only_visual"
                ]
