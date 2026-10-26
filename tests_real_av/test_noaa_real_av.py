from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from av_trace_real_av.core import (
    AGENTS,
    BUILD_OUTPUTS,
    BlindPolicySession,
    MVPError,
    RealBackend,
    SourceVerifier,
    _validate_and_map_finalization,
    _run_policy,
    _assert_gate,
    _source_inputs,
    build_mvp,
)


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def built():
    build_mvp(ROOT)
    return {
        key: json.loads((ROOT / path).read_text())
        for key, path in BUILD_OUTPUTS.items()
    }


def test_gate_exact_retained_set_and_boundary():
    inputs = _source_inputs(ROOT)
    assert _assert_gate(inputs) == [
        "noaa01-review-004",
        "noaa01-review-007",
        "noaa01-review-011",
        "noaa01-review-014",
        "noaa01-review-016",
        "noaa01-review-017",
    ]
    assert inputs["redteam"]["human_reviewed"] is False
    assert inputs["redteam"]["gold_annotation"] is False


def test_gate_rejects_stale_counts():
    inputs = deepcopy(_source_inputs(ROOT))
    inputs["redteam"]["independently_recomputed_counts"]["accepted_windows"].append("stale")
    with pytest.raises(MVPError, match="stale"):
        _assert_gate(inputs)


def test_six_families_three_assets_and_exact_bindings(built):
    families = built["families"]
    assert families["family_count"] == 6
    assert families["asset_count"] == 3
    for family in families["families"]:
        source = family["source"]
        path = ROOT / source["restricted_media_path"]
        assert path.stat().st_size == source["size_bytes"]
        assert source["sha256"].startswith("sha256:")
        assert family["interval"]["end_s"] <= source["duration_s"]
        assert source["streams"]["video_count"] >= 1
        assert source["streams"]["audio_count"] >= 1


def test_index_has_18_windows_and_no_forbidden_fields(built):
    index = built["index"]
    assert index["window_count"] == 18
    assert len({x["source_review_id"] for x in index["records"]}) == 18
    forbidden = set(index["forbidden_searchable_fields"])
    for record in index["records"]:
        assert not forbidden.intersection(record)
        assert not forbidden.intersection(record["payload"])
        assert "state_role" not in record["search_text"]
        assert "intervention_id" not in record["search_text"]


def test_distractors_and_dual_validation(built):
    for row in built["validation"]["families"]:
        assert row["passed"]
        assert row["validator_agreement"]
        assert len(row["admitted_distractor_review_ids"]) >= 2
        assert {x["policy"] for x in row["validators"]} == {
            "lexical_entailment",
            "provenance_role",
        }
        assert row["semantic_minimality_status"] == "not_human_validated"
        assert row["modality_necessity_status"] == "not_human_validated"


def test_intervention_invariants_and_no_false_gold(built):
    assert all(x["invariants_passed"] for x in built["interventions"]["families"])
    serialized = json.dumps(built, sort_keys=True)
    assert '"human_reviewed": true' not in serialized
    assert '"gold_annotation": true' not in serialized
    assert "minimality_validated" not in serialized


def test_blind_policy_surface_and_opaque_search_pointer(built):
    family = built["families"]["families"][0]
    intervention = next(
        x for x in built["interventions"]["families"]
        if x["family_id"] == family["family_id"]
    )
    backend = RealBackend(
        ROOT,
        family,
        "CLEAN",
        built["index"],
        intervention,
        SourceVerifier(ROOT, {}),
    )
    session = BlindPolicySession(backend)
    assert set(session.start) == {
        "question", "video_duration_s", "available_tools", "budget",
        "tool_costs", "deterministic", "claim_slots",
    }
    assert all(x["claim_handle"].startswith("slot.") for x in session.start["claim_slots"])
    assert "claim.r" not in json.dumps(session.start)
    assert "e.r" not in json.dumps(session.start)
    assert not hasattr(session, "state")
    assert not hasattr(session, "family")
    assert not hasattr(session, "intervention")
    pointers = session.search("vision", session.start["question"])
    assert pointers
    assert "record_id" not in pointers[0]
    assert "route_evidence_ids" not in pointers[0]


def test_real_tool_time_decode_and_no_derivative_persistence(built):
    family = built["families"]["families"][0]
    intervention = next(
        x for x in built["interventions"]["families"]
        if x["family_id"] == family["family_id"]
    )
    before = {
        str(p.relative_to(ROOT))
        for p in (ROOT / "data/restricted/noaa01").rglob("*")
        if p.is_file() and p.suffix.lower() in {".wav", ".png", ".jpg", ".jpeg", ".npy"}
    }
    verifier = SourceVerifier(ROOT, {})
    backend = RealBackend(ROOT, family, "CLEAN", built["index"], intervention, verifier)
    session = BlindPolicySession(backend)
    pointer = session.search("vision", session.start["question"])[0]
    observation = session.observe(pointer["pointer_id"])
    assert observation is not None
    assert observation["provenance"]["exact_interval_decode"] is True
    assert observation["provenance"]["video_coverage"]
    assert observation["provenance"]["persistent_derivative_created"] is False
    assert verifier._verified_call_count == 1
    after = {
        str(p.relative_to(ROOT))
        for p in (ROOT / "data/restricted/noaa01").rglob("*")
        if p.is_file() and p.suffix.lower() in {".wav", ".png", ".jpg", ".jpeg", ".npy"}
    }
    assert after == before


def test_generated_run_contract_if_present():
    report_path = ROOT / "mvp/results/noaa01_real_av_mvp/report.json"
    if not report_path.exists():
        pytest.skip("run artifact not generated yet")
    report = json.loads(report_path.read_text())
    assert report["counts"]["trajectories"] == 6 * 3 * len(AGENTS)
    assert report["invariants"]["all_passed"]
    assert report["decisions"]["final_benchmark"] == "FINAL_BENCHMARK_NOT_YET_VALIDATED"
    modality = [x for x in report["metrics"] if x["metric"] == "Modality Recall"]
    assert modality and all(x["value"] is None and x["denominator"] == 0 for x in modality)
    recovery = [x for x in report["metrics"] if x["metric"] == "Recovery"]
    assert all(
        x["value"] is None
        for x in recovery
        if x["agent"] in {"direct-long-context", "single-shot-rag"}
    )
    assert report["counts"]["valid_trajectories"] == report["counts"]["trajectories"]
    assert all(
        all(value for key, value in row.items() if key != "family_id")
        for row in report["invariants"]["families"]
    )


def test_run_manifest_hashes_and_deterministic_index():
    manifest_path = ROOT / "mvp/results/noaa01_real_av_mvp/run_manifest.json"
    if not manifest_path.exists():
        pytest.skip("run artifact not generated yet")
    manifest = json.loads(manifest_path.read_text())
    import hashlib

    for relative, expected in manifest["artifact_hashes"].items():
        actual = "sha256:" + hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        assert actual == expected
    first = json.loads((ROOT / BUILD_OUTPUTS["index"]).read_text())["index_hash"]
    build_mvp(ROOT)
    second = json.loads((ROOT / BUILD_OUTPUTS["index"]).read_text())["index_hash"]
    assert first == second


def test_public_report_has_no_restricted_payload():
    path = ROOT / "mvp/results/noaa01_real_av_mvp/report.md"
    if not path.exists():
        pytest.skip("run artifact not generated yet")
    text = path.read_text()
    assert "data/restricted/noaa01/raw/" not in text
    assert "North Atlantic Basin, and we're" not in text
    assert "provisional_text" not in text


def test_distinct_agentic_controller_paths_and_actions(built):
    """Task 90: evidence sufficiency is not an alias of ReAct."""
    family = built["families"]["families"][0]
    intervention = next(
        x for x in built["interventions"]["families"]
        if x["family_id"] == family["family_id"]
    )
    runs = {}
    for agent in ("react-recovery", "evidence-sufficiency"):
        backend = RealBackend(
            ROOT,
            family,
            "CLEAN",
            built["index"],
            intervention,
            SourceVerifier(ROOT, {}),
        )
        runs[agent] = (_run_policy(agent, BlindPolicySession(backend)), backend.trace)
    react, react_trace = runs["react-recovery"]
    suff, suff_trace = runs["evidence-sufficiency"]
    assert react["controller_state"]["controller"] == "reactive-query-reformulation/2.0"
    assert suff["controller_state"]["controller"] == "explicit-evidence-sufficiency/2.0"
    assert react["controller_state"]["explicit_coverage_belief"] is False
    assert suff["controller_state"]["explicit_coverage_belief"] is True
    assert [(x["tool"], x["status"]) for x in react_trace] != [
        (x["tool"], x["status"]) for x in suff_trace
    ]


def test_strict_metric_artifacts_if_present():
    report_path = ROOT / "mvp/results/noaa01_real_av_mvp/report.json"
    trajectories_path = ROOT / "mvp/results/noaa01_real_av_mvp/trajectories.restricted.json"
    runtime_path = ROOT / "mvp/results/noaa01_real_av_mvp/runtime_validation.restricted.json"
    if not runtime_path.exists():
        pytest.skip("Task 90 run artifact not generated yet")
    report = json.loads(report_path.read_text())
    traces = json.loads(trajectories_path.read_text())["trajectories"]
    runtime = json.loads(runtime_path.read_text())
    assert all(x["pilot_scale_warning"] == "LOW_N_DESCRIPTIVE_PILOT" for x in report["metrics"])
    assert report["pilot_scale_warning"] == "LOW_N_DESCRIPTIVE_PILOT"
    assert len(runtime["trajectory_evaluations"]) == 72
    for trajectory in traces:
        final = trajectory["final_output"]
        assert "claims" not in final and "citations" not in final
        assert isinstance(final["asserted_claims"], list)
        assert isinstance(final["claim_to_citations"], dict)
        restricted = trajectory["_restricted_evaluation"]
        cert = restricted["final_point_route_feasibility"]
        assert cert["certificate_id"].startswith("sha256:")
        assert "actual_final_decision_point" in cert


def test_unknown_and_private_assertions_count_against_groundedness(built):
    family = built["families"]["families"][0]
    run = {
        "observations": [],
        "_evaluator_evidence_by_observation": {},
        "final_output": {
            "verdict": "sufficient",
            "abstention": False,
            "answer": "invented",
            "asserted_claims": [
                {
                    "claim_handle": "claim.r004.visual",
                    "text": "invented unsupported claim",
                    "citation_ids": ["e.r004.vision"],
                }
            ],
            "claim_to_citations": {
                "claim.r004.visual": ["e.r004.vision"],
            },
        },
    }
    result = _validate_and_map_finalization(family, run)
    assert not result["output_valid"]
    assert result["forbidden_or_contradictory_claim"]
    assert result["supported_claim_rate"] == 0.0
    assert result["supported_asserted_claim_count"] == 0


def test_final_point_premature_stop_semantics_if_present():
    trajectory_path = ROOT / "mvp/results/noaa01_real_av_mvp/trajectories.restricted.json"
    metric_path = ROOT / "mvp/results/noaa01_real_av_mvp/episode_metrics.csv"
    if not trajectory_path.exists() or not metric_path.exists():
        pytest.skip("Task 90 run artifact not generated yet")
    import csv

    trajectories = json.loads(trajectory_path.read_text())["trajectories"]
    rows = list(csv.DictReader(metric_path.open()))
    by_key = {
        (x["family_id"], x["state"], x["agent"]): x for x in trajectories
    }
    metric_by_key = {
        (x["family_id"], x["state"], x["agent"]): x for x in rows
    }
    non_abstaining = by_key[
        ("noaa01-r004-surf-av", "RESTORED", "single-shot-rag")
    ]
    abstaining = by_key[
        ("noaa01-r017-north-atlantic-basin", "RESTORED", "single-shot-rag")
    ]
    assert non_abstaining["_restricted_evaluation"]["final_point_route_feasibility"]["route_feasible"]
    assert abstaining["_restricted_evaluation"]["final_point_route_feasibility"]["route_feasible"]
    assert non_abstaining["final_output"]["abstention"] is False
    assert abstaining["final_output"]["abstention"] is True
    assert metric_by_key[
        ("noaa01-r004-surf-av", "RESTORED", "single-shot-rag")
    ]["premature_stop"] == "1"
    assert metric_by_key[
        ("noaa01-r017-north-atlantic-basin", "RESTORED", "single-shot-rag")
    ]["premature_stop"] == "0"
