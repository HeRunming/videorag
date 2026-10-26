from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/p23_102_global_distinctiveness_canary.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("r23c_canary_tested", TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_exposed_selection_is_exactly_three_families_five_clips() -> None:
    tool = load_tool()
    selection = tool.load_exposed_selection()
    assert selection["fresh_or_untouched"] is False
    assert selection["fresh_reserve_consumed"] is False
    assert selection["unselected_reserve"] == {
        "read": False,
        "included": False,
        "disclosed": False,
    }
    assert selection["counts"] == {
        "families": 3,
        "clips": 5,
        "primary_queries": 13,
    }
    assert [row["family_key"] for row in selection["families"]] == [
        "family-009",
        "family-005",
        "family-003",
    ]
    assert [row["clip_key"] for row in selection["clips"]] == [
        "clip-003",
        "clip-011",
        "clip-019",
        "clip-007",
        "clip-010",
    ]
    assert tool.verify_exposed_selection(selection)["status"] == "PASS"


def test_plan_binds_v9_parent_constraints_and_zero_execution() -> None:
    tool = load_tool()
    plan = tool.build_plan()
    assert plan["status"] == tool.STATUS_TOKEN
    assert plan["scientific_go"] is False
    assert plan["call_budget"] == {
        "visual_video_only": 5,
        "ambient_audio_only": 5,
        "relation_text_only_closed_kind": 3,
        "total": 13,
        "additional_repair_retry_calls": 0,
    }
    assert plan["constraints"]["visual"]["constraint_kind"] == (
        "strict_json_object_boundary_plus_exact_r23b_v9_post_validation"
    )
    assert plan["constraints"]["visual"]["closed_finite_language"] is True
    assert plan["constraints"]["visual"]["canonical_leaf_count"] > 33_000_000
    assert "token trie is not committed" in plan["constraints"]["visual"]["boundary"]
    assert plan["constraints"]["ambient"]["constraint_kind"] == (
        "canonical_ambient_tuple_token_prefix_trie"
    )
    assert plan["constraints"]["relation"]["constraint_kind"] == (
        "closed_required_relation_kind"
    )
    assert plan["scope"]["model_calls"] == 0
    assert plan["scope"]["attempt_marker_created"] is False
    assert plan["scope"]["old_r22_marker_capsule_authorization_modified"] is False
    assert plan["machine_calibration"]["maximum_success_status"] == (
        "MACHINE_CALIBRATION_PASS_HUMAN_PENDING"
    )
    assert tool.verify_plan(plan)["status"] == "PASS"


def test_synthetic_stage_runner_builds_13_query_machine_pass() -> None:
    tool = load_tool()
    stage = tool.run_synthetic_stage_runner()
    bundle = tool.build_calibration_bundle(stage)
    verified = tool.verify_calibration_bundle(bundle)
    assert verified["status"] == "PASS"
    assert bundle["status"] == "MACHINE_CALIBRATION_PASS_HUMAN_PENDING"
    assert bundle["scientific_go"] is False
    assert bundle["fresh_evaluation"] is False
    assert bundle["retrieval_or_embedding_executed"] is False
    assert bundle["call_accounting"]["total"] == 13
    assert len(bundle["r23b_v9_bundle"]["primary_queries"]) == 13
    assert bundle["r23b_v9_bundle"]["global_distinctiveness"]["status"] == "PASS"
    packets = bundle["review_packet_set"]
    assert packets["status"] == "UNFILLED_HUMAN_REVIEW_PACKETS_ONLY"
    assert packets["human_results_present"] is False
    assert packets["machine_calibration_blocking"] is False
    assert packets["scientific_go_blocking"] is True
    assert packets["packet_count"] == 5
    for packet in packets["packets"]:
        assert packet["reviewer_1"] is None
        assert packet["reviewer_2"] is None
        assert packet["adjudication"] is None
        assert packet["decision"] is None


def test_global_failures_are_fail_closed_and_never_sealed_as_pass() -> None:
    tool = load_tool()
    for mutation in ("ambient_duplicate", "visual_duplicate"):
        with pytest.raises(tool.ContractError, match="R23C_GLOBAL_GATES_FAILED"):
            tool.build_calibration_bundle(
                tool.run_synthetic_stage_runner(mutation=mutation)
            )
    with pytest.raises(tool.ContractError):
        tool.build_calibration_bundle(
            tool.run_synthetic_stage_runner(mutation="generic")
        )
    with pytest.raises(tool.ContractError, match="R23C_RELATION_KIND_MISMATCH"):
        tool.build_calibration_bundle(
            tool.run_synthetic_stage_runner(mutation="bad_relation")
        )


def test_strict_model_output_parsers_reject_trailing_duplicate_and_free_text() -> None:
    tool = load_tool()
    stage = tool.run_synthetic_stage_runner()
    visual_text = json.dumps(stage["visual_atoms"]["clip-003"])
    ambient_text = json.dumps(stage["ambient_tuples"]["clip-003"])
    relation_text = json.dumps({"relation": "single"})
    assert tool.parse_visual_model_output(visual_text)["action"] == "cutting"
    assert tool.parse_ambient_model_output(ambient_text)["event_kind"] == "scrape"
    assert (
        tool.parse_relation_model_output(
            relation_text, required_relation="single"
        )
        == "single"
    )
    with pytest.raises(tool.ContractError, match="R23C_VISUAL_JSON_INVALID"):
        tool.parse_visual_model_output(visual_text + " trailing")
    with pytest.raises(tool.ContractError, match="R23C_VISUAL_JSON_INVALID"):
        tool.parse_visual_model_output(
            '{"kind":"event","kind":"state","action":"cutting"}'
        )
    with pytest.raises(tool.ContractError, match="R23C_RELATION_KIND_MISMATCH"):
        tool.parse_relation_model_output(
            '{"relation":"before"}', required_relation="single"
        )


def test_stage_hash_budget_and_identity_tamper_fail_closed() -> None:
    tool = load_tool()
    stage = tool.run_synthetic_stage_runner()
    tampered = copy.deepcopy(stage)
    tampered["call_accounting"]["total"] = 14
    tampered["stage_output_payload_sha256"] = tool.semantic_hash(
        {k: v for k, v in tampered.items() if k != "stage_output_payload_sha256"}
    )
    with pytest.raises(tool.ContractError, match="R23C_CALL_BUDGET_MISMATCH"):
        tool.build_calibration_bundle(tampered)

    identity = copy.deepcopy(stage)
    identity["selection_payload_sha256"] = "sha256:" + "0" * 64
    identity["stage_output_payload_sha256"] = tool.semantic_hash(
        {k: v for k, v in identity.items() if k != "stage_output_payload_sha256"}
    )
    with pytest.raises(tool.ContractError, match="R23C_STAGE_OUTPUT_BINDING_MISMATCH"):
        tool.build_calibration_bundle(identity)


def test_one_shot_namespace_is_new_and_marker_is_exclusive(tmp_path: Path) -> None:
    tool = load_tool()
    assert "query_authoring_v2_canary2" not in tool.DEFAULT_OUTPUT.as_posix()
    assert tool.ATTEMPT_MARKER_SCHEMA_VERSION.startswith(
        "av-trace.p23-102-r23c-exposed-calibration-attempt-marker/"
    )
    output = Path("out/r23c-v1")
    marker = tool.attempt_marker_path(output, "AUTH-R23C-V1")
    assert marker.as_posix() == "out/r23c-v1.attempt-AUTH-R23C-V1.json"

    authorization_path = tmp_path / "authorization.json"
    authorization_path.write_text("{}\n", encoding="utf-8")
    authorization = {
        "authorization_id": "AUTH-R23C-V1",
        "attempt_marker_path": marker.as_posix(),
        "output_path": output.as_posix(),
    }
    first = tool._create_attempt_marker(
        authorization_path, authorization, root=tmp_path
    )
    assert first["failure_consumes_receipt"] is True
    assert (tmp_path / marker).stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        tool._create_attempt_marker(
            authorization_path, authorization, root=tmp_path
        )


def test_preflight_self_test_and_cli_never_execute_models() -> None:
    tool = load_tool()
    self_test = tool.run_self_test()
    preflight = tool.run_preflight()
    assert self_test["model_calls"] == 0
    assert self_test["authorization_calls"] == 0
    assert self_test["attempt_markers_created"] == 0
    assert self_test["retrieval_or_embedding_calls"] == 0
    assert preflight["model_calls"] == 0
    assert preflight["authorization_calls"] == 0
    assert preflight["attempt_markers_created"] == 0
    assert preflight["media_decode"] is False
    assert preflight["retrieval_or_embedding"] is False


def test_committed_artifact_builders_are_deterministic_and_disclosure_safe() -> None:
    tool = load_tool()
    public = tool.build_public_summary()
    ledger = tool.build_restricted_ledger()
    encoded_public = json.dumps(public, sort_keys=True)
    assert public["status"] == tool.STATUS_TOKEN
    assert public["fresh_reserve_consumed"] is False
    assert public["unselected_reserve_disclosed"] is False
    assert "family-004" not in encoded_public
    assert "family-006" not in encoded_public
    assert "family-007" not in encoded_public
    assert ledger["old_r22_paths_reused"] is False
    assert ledger["authorization_created"] is False
    assert ledger["attempt_marker_created"] is False
    assert ledger["one_shot_versioning"]["new_code_version_requires_new_pipeline_id"] is True
