from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/epic_p23_102_family_mining_v1.py"
PLAN_PATH = (
    ROOT / "data/rehearsal_plan/epic_p23_102_family_mining_v1.json"
)


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "epic_p23_102_family_mining_v1", TOOL_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_plan_is_deterministic_and_matches_committed_artifact() -> None:
    tool = load_tool()
    first = tool.build_plan()
    second = tool.build_plan()
    committed = json.loads(PLAN_PATH.read_text(encoding="utf-8"))

    assert tool.canonical_bytes(first) == tool.canonical_bytes(second)
    assert tool.canonical_bytes(first) == tool.canonical_bytes(committed)
    assert first["implementation_decision"] == (
        "EPIC_P23_102_FAMILY_MINING_PIPELINE_READY"
    )
    assert first["repair_completion_token"] == (
        "EPIC_P23_102_FAMILY_MINING_REPAIR_READY"
    )
    calibration = first["generation"]["local"][
        "visual_transition_calibration"
    ]
    assert calibration["quantile"] == 0.95
    assert calibration["minimum_absolute_effect"] == 0.02
    assert calibration["semantic_labels_used"] is False
    assert "minimum_visual_transition" not in first["generation"]["local"]
    assert first["generation"]["far"]["pair_generation_scope"].startswith(
        "all eligible separated"
    )
    assert first["blind_mining_boundary"][
        "semantic_annotation_parameter_exposed"
    ] is False
    assert first["target_profiles"]["quota_forcing_forbidden"] is True
    assert first["human_prescreen_gate"][
        "required_before_any_accepted_family_ses_or_h_tier"
    ] is True


def test_plan_mode_does_not_require_or_read_future_index(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    plan = root / "data/rehearsal_plan/epic_p23_102_family_mining_v1.json"
    plan.parent.mkdir(parents=True)
    plan.write_bytes(TOOL_PATH.read_bytes()[:0])
    tool = load_tool()
    plan.write_bytes(tool.canonical_bytes(tool.build_plan()))

    completed = subprocess.run(
        [
            sys.executable,
            str(TOOL_PATH),
            "--repo-root",
            str(root),
            "--mode",
            "plan",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(completed.stdout)
    assert result["decision"] == tool.PIPELINE_READY
    assert result["index_read"] is False
    assert result["output_written"] is False
    assert not (root / "data/restricted").exists()


def test_synthetic_mining_is_deterministic_and_emits_exact_handles() -> None:
    tool = load_tool()
    bundle = tool.build_synthetic_bundle(
        speech_present=True, independent_audio_present=False
    )
    first = tool.mine_bundle(bundle)
    second = tool.mine_bundle(bundle)

    assert tool.canonical_bytes(first) == tool.canonical_bytes(second)
    tool.validate_registry(first, bundle=bundle)
    assert first["summary"]["accepted_family_count"] == 0
    assert first["summary"]["accepted_ses_count"] == 0
    assert first["summary"]["h_tier_count"] == 0
    assert first["profile_accounting"]["V+S"]["machine_lead_count"] > 0
    assert first["profile_accounting"]["V+S+A"]["honest_zero"] is True
    assert first["calibration_diagnostics"]["visual_transition"][
        "selected_threshold"
    ] == 1.0
    assert first["filter_flow_counts"]["far_all_fine_pairs"][0] == {
        "gate": "pairs_at_minimum_separation",
        "count": 9,
    }
    assert {
        candidate["machine_provisional_status"]
        for candidate in first["candidates"]
    }.issubset({"KEEP", "REPAIR", "REJECT"})

    modality_documents = {
        "vision": {
            item["segment_id"]: item
            for item in bundle["index"]["modalities"]["siglip2_visual"][
                "documents"
            ]
        },
        "speech": {
            item["chunk_id"]: item
            for item in bundle["index"]["modalities"]["speech"]["documents"]
        },
        "ambient_audio": {
            item["segment_id"]: item
            for item in bundle["index"]["modalities"]["clap_audio"][
                "documents"
            ]
        },
    }
    for candidate in first["candidates"]:
        assert candidate["atomic_claim_templates"]
        assert candidate["alternative_evidence_routes"] is not None
        assert candidate["substitution_risks"]
        assert candidate["recurrence_checks"][
            "human_full_source_recurrence_review_required"
        ] is True
        for handle in candidate["evidence_handles"]:
            indexed = modality_documents[handle["modality"]][
                handle["record_id"]
            ]
            assert handle["start_us"] == indexed["start_us"]
            assert handle["end_us"] == indexed["end_us"]
            assert handle["human_semantic_validation"] == "NOT_PERFORMED"


def test_far_leads_require_distance_and_independent_coherence() -> None:
    tool = load_tool()
    registry = tool.mine_bundle(
        tool.build_synthetic_bundle(
            speech_present=True, independent_audio_present=False
        )
    )
    far = [
        item
        for item in registry["candidates"]
        if item["candidate_kind"] == "coherent_far_multi_hop"
    ]

    assert far
    for candidate in far:
        temporal = candidate["temporal_structure"]
        coherence = temporal["far_coherence"]
        assert temporal["hop_hypothesis"] == "multi_hop"
        assert temporal["evidence_center_separation_seconds"] >= 120.0
        assert coherence["distance_alone_is_not_credited"] is True
        assert (
            coherence["visual_object_or_state_continuity_cosine"] >= 0.88
        )
        assert coherence["coherence_hypothesis"]


def test_far_generation_is_decoupled_from_local_transition_anchors() -> None:
    tool = load_tool()
    plan = tool.build_plan()
    plan["generation"]["local"]["visual_transition_calibration"][
        "minimum_absolute_effect"
    ] = 1.1
    registry = tool.mine_bundle(
        tool.build_synthetic_bundle(
            speech_present=True, independent_audio_present=False
        ),
        plan=plan,
    )

    local_flow = registry["filter_flow_counts"]["local"]
    far_flow = registry["filter_flow_counts"]["far_all_fine_pairs"]
    assert local_flow[1] == {
        "gate": "calibrated_visual_transition",
        "count": 0,
    }
    assert far_flow[0]["count"] == 9
    assert far_flow[1]["count"] == 3
    assert any(
        item["candidate_kind"] == "coherent_far_multi_hop"
        for item in registry["candidates"]
    )


def test_sparse_speech_allows_va_but_never_promotes_inventory_only_asr() -> None:
    tool = load_tool()
    no_speech = tool.mine_bundle(
        tool.build_synthetic_bundle(
            speech_present=False, independent_audio_present=True
        )
    )
    assert no_speech["candidates"]
    assert all(
        item["profile_hypothesis"] == "V+A"
        for item in no_speech["candidates"]
    )
    assert all(
        all(
            handle["modality"] != "speech"
            for handle in item["evidence_handles"]
        )
        for item in no_speech["candidates"]
    )
    assert no_speech["profile_accounting"]["V+S"]["honest_zero"] is True
    assert "inventory-only ASR was not promoted" in (
        no_speech["profile_accounting"]["V+S"]["zero_reason"]
    )
    assert no_speech["independent_work_accounting"]["speech"][
        "honest_zero"
    ] is True

    no_independent_audio = tool.mine_bundle(
        tool.build_synthetic_bundle(
            speech_present=True, independent_audio_present=False
        )
    )
    assert no_independent_audio["profile_accounting"]["V+S+A"][
        "honest_zero"
    ] is True
    assert no_independent_audio["independent_work_accounting"][
        "ambient_non_speech"
    ]["honest_zero"] is True
    assert all(
        candidate["profile_hypothesis"] == "V+S"
        for candidate in no_independent_audio["candidates"]
    )


def test_audio_accounting_and_deterministic_diversity_caps() -> None:
    tool = load_tool()
    registry = tool.mine_bundle(
        tool.build_synthetic_bundle(
            speech_present=False, independent_audio_present=True
        )
    )
    audio = registry["calibration_diagnostics"]["audio"]
    assert audio["novelty_pass_count"] == 6
    assert audio["rms_pass_count"] == 6
    assert audio["not_near_silence_count"] == 6
    assert audio["novelty_rms_and_silence_pass_count"] == 6
    assert audio["structural_and_sparse_searchable_speech_pass_count"] == 6

    local = [
        item for item in registry["candidates"]
        if item["candidate_kind"] == "near_local"
    ]
    far = [
        item for item in registry["candidates"]
        if item["candidate_kind"] == "coherent_far_multi_hop"
    ]
    assert len(local) <= registry["diversity_accounting"]["local_cap"]
    assert len(far) <= registry["diversity_accounting"]["far_cap"]
    far_vision_ids = [
        handle["record_id"]
        for item in far
        for handle in item["evidence_handles"]
        if handle["modality"] == "vision"
    ]
    assert len(far_vision_ids) == len(set(far_vision_ids))


def test_source_uniform_prescreen_is_required_and_never_accepts() -> None:
    tool = load_tool()
    bundle = tool.build_synthetic_bundle(
        speech_present=True, independent_audio_present=False
    )
    unreviewed = tool.mine_bundle(bundle)
    invalid = {
        "schema_version": "av-trace.source-uniform-human-prescreen/1.0",
        "source_id": "P23_102",
        "protocol_scope": "SELECTED_LEADS_ONLY",
        "completed": True,
        "same_form_for_every_lead": True,
        "same_full_source_exposure_for_every_lead": True,
        "full_source_recurrence_review_completed": True,
        "necessity_or_h_tier_assigned": False,
        "candidate_ids": [
            item["candidate_id"] for item in unreviewed["candidates"]
        ],
    }
    with pytest.raises(
        tool.MiningError, match="SOURCE_UNIFORM_HUMAN_PRESCREEN_INVALID"
    ):
        tool.mine_bundle(bundle, prescreen=invalid)

    complete = {
        **invalid,
        "protocol_scope": "SOURCE_UNIFORM_ALL_MACHINE_LEADS",
    }
    reviewed = tool.mine_bundle(bundle, prescreen=complete)
    gate = reviewed["source_uniform_human_prescreen_gate"]
    assert gate["status"] == "COMPLETE_NO_ACCEPTANCE_OR_TIER"
    assert reviewed["summary"]["accepted_family_count"] == 0
    assert reviewed["summary"]["accepted_ses_count"] == 0
    assert reviewed["summary"]["h_tier_count"] == 0
    assert all(
        item["human_prescreen"] == "COMPLETE_NO_ACCEPTANCE_OR_TIER"
        and item["accepted_family"] is False
        and item["accepted_ses"] is False
        and item["h_tier"] is None
        for item in reviewed["candidates"]
    )


def test_validator_rejects_hash_tamper_acceptance_and_unknown_handle() -> None:
    tool = load_tool()
    bundle = tool.build_synthetic_bundle(
        speech_present=True, independent_audio_present=False
    )
    registry = tool.mine_bundle(bundle)

    tampered = copy.deepcopy(registry)
    tampered["candidates"][0]["accepted_family"] = True
    with pytest.raises(tool.MiningError):
        tool.validate_registry(tampered, bundle=bundle)

    unknown = copy.deepcopy(registry)
    candidate = unknown["candidates"][0]
    candidate["evidence_handles"][0]["record_id"] = "seg.unknown"
    candidate["candidate_payload_sha256"] = tool.object_hash(
        {
            key: value
            for key, value in candidate.items()
            if key != "candidate_payload_sha256"
        }
    )
    unknown["registry_payload_sha256"] = tool.object_hash(
        {
            key: value
            for key, value in unknown.items()
            if key != "registry_payload_sha256"
        }
    )
    with pytest.raises(
        tool.MiningError, match="UNKNOWN_EXACT_EVIDENCE_HANDLE"
    ):
        tool.validate_registry(unknown, bundle=bundle)
