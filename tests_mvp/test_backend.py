from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from av_trace.schemas import SchemaRegistry
from av_trace.trajectory import validate_trajectory
from av_trace.util import sha256_json
from av_trace_mvp.backend import BackendProtocolError, FixedBackend
from av_trace_mvp.index import BackendManifest, FixedIndex, IndexFormatError, load_generated
from av_trace_mvp.runner import run_scripted_episode

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = SchemaRegistry(ROOT)
BASE_FAMILY = json.loads((ROOT / "docs/spec/fixtures/positive_episode_family.json").read_text())


def records() -> list[dict]:
    return [
        {
            "record_id": "speech_answer",
            "family_id": "syn_family",
            "asset_id": "asset_syn",
            "modality": "speech",
            "interval": {"start_s": 100.0, "end_s": 110.0},
            "payload": {"text": "A pressure drop caused the warning.", "speaker": "operator"},
            "search_text": "pressure drop warning alarm cause",
            "preview": "Pressure drop warning.",
            "route_evidence_ids": ["e1"],
            "is_distractor": False,
            "speaker": "operator",
            "transcript_sources": ["asr"],
        },
        {
            "record_id": "visual_answer",
            "family_id": "syn_family",
            "asset_id": "asset_syn",
            "modality": "vision",
            "interval": {"start_s": 112.0, "end_s": 120.0},
            "payload": {"description": "The operator closes the valve."},
            "search_text": "operator closes valve warning response",
            "preview": "Operator near the valve.",
            "route_evidence_ids": ["e2"],
            "is_distractor": False,
            "speaker": None,
            "transcript_sources": [],
        },
        {
            "record_id": "speech_distractor_early",
            "family_id": "syn_family",
            "asset_id": "asset_syn",
            "modality": "speech",
            "interval": {"start_s": 20.0, "end_s": 25.0},
            "payload": {"text": "A warning drill mentions pressure."},
            "search_text": "warning pressure drill",
            "preview": "Warning drill mentions pressure.",
            "route_evidence_ids": [],
            "is_distractor": True,
            "speaker": "narrator",
            "transcript_sources": ["asr"],
        },
        {
            "record_id": "ambient_distractor",
            "family_id": "syn_family",
            "asset_id": "asset_syn",
            "modality": "ambient",
            "interval": {"start_s": 40.0, "end_s": 45.0},
            "payload": {"label": "warning buzzer"},
            "search_text": "warning alarm buzzer tone",
            "preview": "A short warning buzzer.",
            "route_evidence_ids": [],
            "is_distractor": True,
            "speaker": None,
            "transcript_sources": [],
        },
    ]


def family_and_artifacts(state_mechanism: str = "necessity_group_withholding"):
    family = deepcopy(BASE_FAMILY)
    index = FixedIndex.from_records(records())
    costs = family["episodes"][0]["budget"]["tool_costs"]
    manifest = BackendManifest.for_index(index, costs)
    for episode in family["episodes"]:
        episode["backend"]["index_hash"] = index.index_hash
        episode["backend"]["backend_version"] = manifest.backend_version
        episode["backend"]["tool_api_version"] = manifest.document["tool_api_version"]
    if state_mechanism == "modality_channel_outage":
        family["intervention_mechanism"] = state_mechanism
        for episode in family["episodes"][1:]:
            episode["initial_state"]["enabled_channels"].remove("speech")
            block = episode["interventions"][0]
            block["mechanism"] = state_mechanism
            block["affected_necessity_group_id"] = None
            block["affected_channel"] = "speech"
        restore = family["episodes"][2]["interventions"][1]
        restore["mechanism"] = state_mechanism
        restore["affected_necessity_group_id"] = None
        restore["affected_channel"] = "speech"
    return family, index, manifest


def belief(sufficient: bool = False) -> dict:
    if sufficient:
        return {
            "p_sufficient": 0.96,
            "verdict": "sufficient",
            "missing_modality_probabilities": {"vision": 0.02, "speech": 0.02, "ambient": 0.01},
            "missing_hop_types": [],
            "missingness_cause_probabilities": {
                "source_evidence_absent": 0.01,
                "evidence_in_source_but_inaccessible": 0.01,
                "evidence_accessible_but_not_found": 0.01,
                "not_missing": 0.96,
                "uncertain": 0.01,
            },
            "next_action_rationale": "Finalize with citable evidence.",
        }
    return {
        "p_sufficient": 0.2,
        "verdict": "insufficient",
        "missing_modality_probabilities": {"vision": 0.1, "speech": 0.8, "ambient": 0.1},
        "missing_hop_types": ["speech_content"],
        "missingness_cause_probabilities": {
            "source_evidence_absent": 0.05,
            "evidence_in_source_but_inaccessible": 0.75,
            "evidence_accessible_but_not_found": 0.1,
            "not_missing": 0.05,
            "uncertain": 0.05,
        },
        "next_action_rationale": "Use the fixed backend.",
    }


def action(episode: str, step: int, tool: str, arguments: dict, *, sufficient: bool = False) -> dict:
    return {
        "protocol_version": "0.2.0",
        "episode_id": episode,
        "request_id": f"r{step}",
        "step_index": step,
        "belief_state": belief(sufficient),
        "action": {"tool": tool, "arguments": arguments},
    }


def search_args(query: str = "pressure warning") -> dict:
    return {
        "query": query,
        "top_k": 10,
        "time_range": {"start_s": 0.0, "end_s": 1200.0},
        "exclude_result_ids": [],
        "speaker_hint": None,
    }


def final_answer(observation_id: str) -> dict:
    return {
        "p_sufficient": 0.96,
        "verdict": "sufficient",
        "answer_mode": "answer",
        "claims": [
            {
                "claim_id": "agent_c1",
                "registered_claim_id": "c1",
                "text": "A pressure drop caused the warning.",
                "confidence": 0.95,
                "citations": [
                    {
                        "observation_id": observation_id,
                        "interval": {"start_s": 100.0, "end_s": 110.0},
                        "modalities": ["speech"],
                    }
                ],
            }
        ],
        "diagnosis": {
            "modality_probabilities": {"vision": 0.02, "speech": 0.02, "ambient": 0.01},
            "hop_types": [],
            "cause_probabilities": {
                "source_evidence_absent": 0.01,
                "evidence_in_source_but_inaccessible": 0.01,
                "evidence_accessible_but_not_found": 0.01,
                "not_missing": 0.96,
                "uncertain": 0.01,
            },
            "recovery_route_declared": False,
            "description": "",
        },
        "natural_language_answer": "A pressure drop caused the warning.",
        "termination_reason": "sufficient_evidence",
    }


def test_ranked_distractors_and_stable_result_ids():
    family, index, manifest = family_and_artifacts()
    first = FixedBackend(family, "CLEAN", index, manifest, REGISTRY)
    second = FixedBackend(family, "CLEAN", index, manifest, REGISTRY)
    request = action("syn_family.clean", 0, "search_speech", search_args())
    left, right = first.execute(request), second.execute(request)
    assert left == right
    assert [item["result_id"] for item in left["results"]] == [
        next(item.result_id for item in index.records if item.record_id == record_id)
        for record_id in ("speech_distractor_early", "speech_answer")
    ]
    assert left["results"][0]["score"] == left["results"][1]["score"]


def test_source_level_index_exposes_same_source_records_across_families():
    family, index, manifest = family_and_artifacts()
    unrelated = deepcopy(records()[0])
    unrelated.update(
        {
            "record_id": "other_family_record",
            "family_id": None,
            "route_evidence_ids": ["other_evidence"],
            "search_text": "unrelated speech token",
            "preview": "candidate",
        }
    )
    index = FixedIndex.from_records(records() + [unrelated])
    manifest = BackendManifest.for_index(index, manifest.tool_costs)
    for episode in family["episodes"]:
        episode["backend"]["index_hash"] = index.index_hash
    backend = FixedBackend(family, "CLEAN", index, manifest, REGISTRY)
    response = backend.execute(
        action("syn_family.clean", 0, "search_speech", search_args("unrelated"))
    )
    assert response["results"][0]["result_id"] == next(
        item.result_id for item in index.records if item.record_id == "other_family_record"
    )


def test_fixed_call_index_restoration_executes():
    family, index, manifest = family_and_artifacts()
    restore = family["episodes"][2]["interventions"][1]["restoration"]
    restore["trigger_type"] = "fixed_call_index"
    restore["trigger_value"] = 1
    backend = FixedBackend(family, "RESTORED", index, manifest, REGISTRY)
    before = backend.execute(
        action("syn_family.restored", 0, "search_speech", search_args("pressure"))
    )
    assert [item["result_id"] for item in before["results"]] == [
        next(item.result_id for item in index.records if item.record_id == "speech_distractor_early")
    ]
    restored = backend.execute(
        action("syn_family.restored", 1, "search_speech", search_args("pressure"))
    )
    assert backend.last_active_hook_ids == ("restore1",)
    assert [item["result_id"] for item in restored["results"]] == [
        next(item.result_id for item in index.records if item.record_id == record_id)
        for record_id in ("speech_distractor_early", "speech_answer")
    ]


def test_withholding_closes_direct_and_derived_routes():
    family, index, manifest = family_and_artifacts()
    leaked = records() + [
        {
            "record_id": "derived_answer",
            "family_id": "syn_family",
            "asset_id": "asset_syn",
            "modality": "speech",
            "interval": {"start_s": 101.0, "end_s": 102.0},
            "payload": {"text": "Derived pressure answer."},
            "search_text": "pressure answer",
            "preview": "Derived pressure answer.",
            "route_evidence_ids": ["e1"],
            "is_distractor": False,
            "transcript_sources": ["asr"],
        }
    ]
    index = FixedIndex.from_records(leaked)
    manifest = BackendManifest.for_index(index, manifest.tool_costs)
    for episode in family["episodes"]:
        episode["backend"]["index_hash"] = index.index_hash
    backend = FixedBackend(family, "BLOCKED", index, manifest, REGISTRY)
    response = backend.execute(action("syn_family.blocked", 0, "search_speech", search_args("pressure")))
    assert response["status"] == "ok"
    assert [item["result_id"] for item in response["results"]] == [
        next(item.result_id for item in index.records if item.record_id == "speech_distractor_early")
    ]


def test_restoration_is_exact_and_replayable():
    family, index, manifest = family_and_artifacts()
    clean = FixedBackend(family, "CLEAN", index, manifest, REGISTRY)
    restored = FixedBackend(family, "RESTORED", index, manifest, REGISTRY)
    clean_result = clean.execute(action("syn_family.clean", 0, "search_speech", search_args()))
    before = restored.execute(action("syn_family.restored", 0, "search_speech", search_args()))
    assert [item["result_id"] for item in before["results"]] == [
        next(item.result_id for item in index.records if item.record_id == "speech_distractor_early")
    ]
    status = restored.execute(action("syn_family.restored", 1, "get_channel_status", {"channels": ["speech"]}))
    assert restored.last_active_hook_ids == ("restore1",)
    assert status["results"][0]["channels"]["speech"]["status"] == "available"
    after = restored.execute(action("syn_family.restored", 2, "search_speech", search_args()))
    assert after["results"] == clean_result["results"]


def test_channel_outage_returns_typed_failure_then_restores():
    family, index, manifest = family_and_artifacts("modality_channel_outage")
    backend = FixedBackend(family, "RESTORED", index, manifest, REGISTRY)
    unavailable = backend.execute(action("syn_family.restored", 0, "search_speech", search_args()))
    assert unavailable["status"] == "channel_unavailable"
    assert unavailable["error"]["code"] == "SPEECH_CHANNEL_UNAVAILABLE"
    assert unavailable["cost_charged"] == 1.0
    backend.execute(action("syn_family.restored", 1, "get_channel_status", {"channels": ["speech"]}))
    found = backend.execute(action("syn_family.restored", 2, "search_speech", search_args()))
    assert found["status"] == "ok"


def test_budget_exhaustion_is_zero_cost_and_allows_finalization():
    family, index, manifest = family_and_artifacts()
    for episode in family["episodes"]:
        episode["budget"]["cost_limit"] = 0.25
        episode["budget"]["max_steps"] = 2
    backend = FixedBackend(family, "CLEAN", index, manifest, REGISTRY)
    rejected = backend.execute(action("syn_family.clean", 0, "search_speech", search_args()))
    assert rejected["status"] == "budget_exhausted"
    assert rejected["cost_charged"] == 0.0
    assert rejected["cost_used_total"] == 0.0
    final = {
        "p_sufficient": 0.2,
        "verdict": "insufficient",
        "answer_mode": "abstain",
        "claims": [],
        "diagnosis": {
            "modality_probabilities": {"vision": 0.1, "speech": 0.8, "ambient": 0.1},
            "hop_types": ["speech_content"],
            "cause_probabilities": {
                "source_evidence_absent": 0.05,
                "evidence_in_source_but_inaccessible": 0.75,
                "evidence_accessible_but_not_found": 0.1,
                "not_missing": 0.05,
                "uncertain": 0.05,
            },
            "recovery_route_declared": False,
            "description": "Budget guard.",
        },
        "natural_language_answer": "",
        "termination_reason": "budget_guard",
    }
    assert backend.execute(action("syn_family.clean", 1, "finalize", final)) is None


def test_inspect_cost_and_duration_are_exact():
    family, index, manifest = family_and_artifacts()
    backend = FixedBackend(family, "CLEAN", index, manifest, REGISTRY)
    response = backend.execute(
        action(
            "syn_family.clean",
            0,
            "inspect_clip",
            {"interval": {"start_s": 100.0, "end_s": 120.0}, "include_video": True, "include_audio": True},
        )
    )
    assert response["status"] == "ok"
    assert response["cost_charged"] == 2.0
    assert response["cost_used_total"] == 2.0
    assert backend.inspected_duration_s == 20.0
    assert {item["payload"]["inspection"]["inspected_duration_s"] for item in response["results"]} == {20.0}


def test_scripted_trajectory_is_valid_deterministic_and_hashed():
    family, index, manifest = family_and_artifacts()

    def run():
        backend = FixedBackend(family, "CLEAN", index, manifest, REGISTRY)
        read = action(
            "syn_family.clean",
            0,
            "read_transcript",
            {
                "interval": {"start_s": 100.0, "end_s": 110.0},
                "source": "asr",
                "include_word_timestamps": False,
            },
        )
        preview_backend = FixedBackend(family, "CLEAN", index, manifest, REGISTRY)
        observation_id = preview_backend.execute(deepcopy(read))["results"][0]["observation_id"]
        final = action("syn_family.clean", 1, "finalize", final_answer(observation_id), sufficient=True)
        return run_scripted_episode(backend, [read, final])

    first, second = run(), run()
    assert first == second
    assert validate_trajectory(first, REGISTRY).ok
    assert first["replay"]["backend_hash"] == manifest.manifest_hash
    assert first["replay"]["trajectory_hash"].startswith("sha256:")
    assert first["events"][0]["response"]["results"][0]["payload_hash"].startswith("sha256:")


def test_manifest_loader_fails_closed_and_loads_temp_fixture(tmp_path: Path):
    family, index, manifest = family_and_artifacts()
    index_path = tmp_path / "index.json"
    family_path = tmp_path / "families.json"
    index_document = index.to_document()
    index_path.write_text(json.dumps(index_document), encoding="utf-8")
    family_path.write_text(json.dumps([family]), encoding="utf-8")
    document = deepcopy(manifest.document)
    document["artifacts"] = [
        {"role": "index", "path": "index.json", "sha256": sha256_json(index_document)},
        {"role": "family", "path": "families.json", "sha256": sha256_json([family])},
    ]
    document["index_hash"] = sha256_json(index_document)
    for episode in family["episodes"]:
        episode["backend"]["index_hash"] = document["index_hash"]
    family_path.write_text(json.dumps([family]), encoding="utf-8")
    document["artifacts"][1]["sha256"] = sha256_json([family])
    (tmp_path / "backend_manifest.json").write_text(json.dumps(document), encoding="utf-8")
    corpus = load_generated(tmp_path)
    assert corpus.family("syn_family")["family_id"] == "syn_family"
    index_path.write_text(json.dumps({"tampered": True}), encoding="utf-8")
    with pytest.raises(IndexFormatError, match="MANIFEST_HASH"):
        load_generated(tmp_path)


def test_documented_sibling_generated_layout_is_ingested_when_present():
    generated = ROOT / "mvp/generated/quick/corpus_index.json"
    if not generated.is_file():
        pytest.skip("Sibling synthetic corpus has not been generated in this checkout.")
    corpus = load_generated(generated.parent)
    assert len(corpus.families) >= 1
    family = corpus.families[0]
    backend = FixedBackend(family, "CLEAN", corpus.index, corpus.manifest, REGISTRY)
    assert backend.index_version.startswith("synthetic-")
    assert backend.episode_start()["family_id"] == family["family_id"]


def test_invalid_route_and_protocol_errors_fail_closed():
    family, index, manifest = family_and_artifacts()
    bad = deepcopy(records())
    bad[0]["route_evidence_ids"] = []
    with pytest.raises(IndexFormatError, match="INDEX_ROUTE"):
        FixedIndex.from_records(bad)
    backend = FixedBackend(family, "CLEAN", index, manifest, REGISTRY)
    with pytest.raises(BackendProtocolError, match="BACKEND_STEP_MISMATCH"):
        backend.execute(action("syn_family.clean", 2, "get_channel_status", {"channels": ["speech"]}))
