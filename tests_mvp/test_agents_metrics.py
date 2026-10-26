from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from av_trace.schemas import SchemaRegistry
from av_trace_mvp.agents import (
    AlwaysAnswerAgent,
    EvidenceBeliefStateAgent,
    ReActHeuristicAgent,
    SingleShotRAGAgent,
)
from av_trace_mvp.backend import FixedBackend
from av_trace_mvp.experiment import run_experiment
from av_trace_mvp.index import BackendManifest, FixedIndex
from av_trace_mvp.metrics import (
    _belief_labels,
    _stepwise_cause_scores,
    paired_restoration_rows,
    video_cluster_bootstrap,
)
from av_trace_mvp.experiment import _map_registered_claims

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = SchemaRegistry(ROOT)


def _family_and_backend():
    family = json.loads(
        (ROOT / "mvp/generated/full/families/syn_f01_visual_order.json").read_text()
    )
    records = []
    for evidence in family["claim_evidence_graph"]["evidence_units"]:
        records.append(
            {
                "record_id": f"record.{evidence['evidence_id']}",
                "family_id": family["family_id"],
                "asset_id": family["source"]["asset_id"],
                "modality": evidence["modality"],
                "interval": evidence["intervals"][0],
                "payload": {"description": evidence["observation"]},
                "search_text": evidence["observation"],
                "preview": evidence["observation"],
                "route_evidence_ids": [evidence["evidence_id"]],
                "is_distractor": False,
                "speaker": None,
                "transcript_sources": ["asr"] if evidence["modality"] == "speech" else [],
            }
        )
    index = FixedIndex.from_records(records)
    costs = family["episodes"][0]["budget"]["tool_costs"]
    manifest = BackendManifest.for_index(index, costs)
    for episode in family["episodes"]:
        episode["backend"]["index_hash"] = index.index_hash
        episode["backend"]["backend_version"] = manifest.backend_version
        episode["backend"]["tool_api_version"] = manifest.document["tool_api_version"]

    def factory(current_family, state_role):
        return FixedBackend(
            deepcopy(current_family),
            state_role,
            index,
            manifest,
            REGISTRY,
        )

    return family, factory


def _rows(report, agent, state):
    return [
        row
        for row in report["episode_metrics"]
        if row["agent"] == agent and row["state_role"] == state
    ]


def test_expected_agent_ordering_and_identical_clean_correctness():
    family, factory = _family_and_backend()
    report = run_experiment(
        [family],
        [
            AlwaysAnswerAgent(),
            SingleShotRAGAgent(),
            ReActHeuristicAgent(),
            EvidenceBeliefStateAgent(),
        ],
        factory,
        bootstrap_samples=50,
    )
    always_blocked = _rows(report, "AlwaysAnswer", "BLOCKED")[0]
    single_restored = _rows(report, "SingleShotRAG", "RESTORED")[0]
    belief_restored = _rows(report, "EvidenceBeliefState", "RESTORED")[0]

    assert always_blocked["false_sufficient"] == 1
    assert always_blocked["high_confidence_false_sufficient"] == 1
    # BLOCKED has no answer-bearing recovery route; without linked validator
    # trajectories the MVP must not manufacture denominator eligibility from an
    # unused diagnostic call.
    assert always_blocked["premature_stop"] == 0
    assert always_blocked["premature_stop_eligible"] == 0
    assert belief_restored["grounded_task_success"] > single_restored["grounded_task_success"]
    assert (
        belief_restored["triggered_supported_recovery"]
        > single_restored["triggered_supported_recovery"]
    )

    always_clean = _rows(report, "AlwaysAnswer", "CLEAN")[0]
    belief_clean = _rows(report, "EvidenceBeliefState", "CLEAN")[0]
    assert always_clean["grounded_task_success"] == belief_clean["grounded_task_success"] == 1
    assert always_clean["sufficiency_brier"] > belief_clean["sufficiency_brier"]
    assert always_clean["final_sufficiency_brier"] > belief_clean["final_sufficiency_brier"]


def test_reports_and_video_cluster_bootstrap_are_deterministic(tmp_path: Path):
    family, factory = _family_and_backend()
    report = run_experiment(
        [family],
        [AlwaysAnswerAgent(), EvidenceBeliefStateAgent()],
        factory,
        output_dir=tmp_path,
        bootstrap_samples=25,
        bootstrap_seed=7,
    )
    for name in (
        "report.json",
        "episode_metrics.csv",
        "summary.csv",
        "dashboard.csv",
        "report.md",
    ):
        assert (tmp_path / name).is_file()
    assert "AV-TRACE MVP experiment report" in (tmp_path / "report.md").read_text()
    loaded = json.loads((tmp_path / "report.json").read_text())
    assert loaded["dashboard"] == report["dashboard"]

    rows = [
        {"video_id": "v1", "family_id": "f1", "metric": 0.0},
        {"video_id": "v1", "family_id": "f2", "metric": 1.0},
        {"video_id": "v2", "family_id": "f3", "metric": 1.0},
    ]
    first = video_cluster_bootstrap(rows, "metric", samples=100, seed=11)
    second = video_cluster_bootstrap(rows, "metric", samples=100, seed=11)
    assert first == second
    assert first["estimate"] == 0.75
    assert first["n_families"] == 3
    assert first["n_videos"] == 2


def test_evaluator_overwrites_agent_supplied_registered_claim_id():
    family, _factory = _family_and_backend()
    answer = {
        "claims": [
            {
                "registered_claim_id": family["answer_spec"]["required_claim_ids"][0],
                "text": "Completely wrong assertion.",
            }
        ]
    }
    mapped = _map_registered_claims(answer, family)
    assert mapped["claims"][0]["registered_claim_id"] is None


def test_state_target_difference_is_not_reported_as_restoration_gain():
    paired = paired_restoration_rows([
        {
            "agent": "probe",
            "track": "EXTERNAL_COMPATIBILITY_UNPOOLED",
            "family_id": "f1",
            "video_id": "v1",
            "state_role": "BLOCKED",
            "grounded_task_success": 1,
            "supported_answer_success": 0,
            "final_p_sufficient": 0.1,
            "access_failure_probability": 0.9,
            "search_route_fraction": 0.5,
        },
        {
            "agent": "probe",
            "track": "EXTERNAL_COMPATIBILITY_UNPOOLED",
            "family_id": "f1",
            "video_id": "v1",
            "state_role": "RESTORED",
            "grounded_task_success": 0,
            "supported_answer_success": 0,
            "final_p_sufficient": 0.1,
            "access_failure_probability": 0.9,
            "post_trigger_search_route_fraction": None,
            "restoration_triggered": 0,
            "triggered_supported_recovery": 0,
        },
    ])[0]
    assert paired["paired_restoration_gain"] == 0
    assert paired["state_target_success_difference"] == -1


def test_stepwise_diagnosis_labels_change_after_observed_sufficiency():
    family, factory = _family_and_backend()
    report = run_experiment(
        [family],
        [EvidenceBeliefStateAgent()],
        factory,
        bootstrap_samples=10,
    )
    trajectory = next(
        item["trajectory"]
        for item in report["trajectories"]
        if item["agent"] == "EvidenceBeliefState"
        and item["state_role"] == "RESTORED"
    )
    beliefs = _belief_labels(family, trajectory)
    restored = False
    for event, (_probability, sufficient) in zip(trajectory["events"], beliefs):
        if sufficient:
            gold = "not_missing"
        elif restored:
            gold = "evidence_accessible_but_not_found"
        else:
            gold = "evidence_in_source_but_inaccessible"
        probabilities = {
            key: float(key == gold)
            for key in (
                "source_evidence_absent",
                "evidence_in_source_but_inaccessible",
                "evidence_accessible_but_not_found",
                "not_missing",
                "uncertain",
            )
        }
        event["action"]["belief_state"]["missingness_cause_probabilities"] = probabilities
        if event.get("active_hook_ids"):
            restored = True
    accuracy, brier = _stepwise_cause_scores(family, "RESTORED", trajectory)
    assert accuracy == 1.0
    assert brier == 0.0


def test_video_cluster_bootstrap_equal_weights_videos_not_families():
    rows = [
        {"video_id": "v1", "family_id": "f1", "metric": 0.0},
        {"video_id": "v1", "family_id": "f2", "metric": 0.0},
        {"video_id": "v1", "family_id": "f3", "metric": 0.0},
        {"video_id": "v2", "family_id": "f4", "metric": 1.0},
    ]
    summary = video_cluster_bootstrap(rows, "metric", samples=0)
    assert summary["estimate"] == pytest.approx(0.5)
