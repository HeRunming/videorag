from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/p23_102_query_authoring_v2_canary.py"


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "p23_102_query_authoring_v2_canary", TOOL_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def synthetic_structural(tool):
    families = [
        {
            "family_key": "family-local-b",
            "private_family_id": "private-local-b",
            "shape": "one_component",
            "slot_names": ["OBJECT"],
            "private_template_hashes": {"question_template": "semantic-b"},
            "intervals": [
                {
                    "start_us": 3_000_000,
                    "end_us": 4_000_000,
                    "clip_key": "clip-003",
                    "private_evidence_handle_ids": ["h5", "h6"],
                }
            ],
            "score": 1_000_000,
        },
        {
            "family_key": "family-far-a",
            "private_family_id": "private-far-a",
            "shape": "two_component_ordered",
            "slot_names": ["FIRST", "SECOND"],
            "private_template_hashes": {"question_template": "semantic-c"},
            "intervals": [
                {
                    "start_us": 4_000_000,
                    "end_us": 5_000_000,
                    "clip_key": "clip-004",
                    "private_evidence_handle_ids": ["h7", "h8"],
                },
                {
                    "start_us": 5_000_000,
                    "end_us": 6_000_000,
                    "clip_key": "clip-005",
                    "private_evidence_handle_ids": ["h9", "h10"],
                },
            ],
            "score": -1_000_000,
        },
        {
            "family_key": "family-local-a",
            "private_family_id": "private-local-a",
            "shape": "one_component",
            "slot_names": ["ITEM"],
            "private_template_hashes": {"question_template": "semantic-a"},
            "intervals": [
                {
                    "start_us": 1_000_000,
                    "end_us": 2_000_000,
                    "clip_key": "clip-001",
                    "private_evidence_handle_ids": ["h1", "h2"],
                }
            ],
            "score": -1_000_000,
        },
        {
            "family_key": "family-far-b",
            "private_family_id": "private-far-b",
            "shape": "two_component_ordered",
            "slot_names": ["BEFORE", "AFTER"],
            "private_template_hashes": {"question_template": "semantic-d"},
            "intervals": [
                {
                    "start_us": 2_000_000,
                    "end_us": 3_000_000,
                    "clip_key": "clip-002",
                    "private_evidence_handle_ids": ["h3", "h4"],
                },
                {
                    "start_us": 3_000_000,
                    "end_us": 4_000_000,
                    "clip_key": "clip-003",
                    "private_evidence_handle_ids": ["h5", "h6"],
                },
            ],
            "score": 1_000_000,
        },
    ]
    targets = []
    for index in range(1, 6):
        targets.append(
            {
                "clip_key": f"clip-{index:03d}",
                "start_us": index * 1_000_000,
                "end_us": (index + 1) * 1_000_000,
                "duration_us": 1_000_000,
                "family_keys": sorted(
                    {
                        family["family_key"]
                        for family in families
                        for interval in family["intervals"]
                        if interval["clip_key"] == f"clip-{index:03d}"
                    }
                ),
            }
        )
    return {
        "file_hashes": {
            name: f"sha256:{index:064x}"
            for index, name in enumerate(
                sorted(tool.parent.ALLOWED_BUNDLE_FILES), 1
            )
        },
        "families": families,
        "targets": targets,
    }


def test_selection_is_hash_only_exactly_local_and_far() -> None:
    tool = load_tool()
    structural = synthetic_structural(tool)
    first = tool.select_canary_families(structural)
    structural["families"].reverse()
    for family in structural["families"]:
        family["score"] *= -99
        family["slot_names"] = ["CHANGED_SEMANTIC_SLOT"]
        family["private_template_hashes"] = {"question_template": "changed"}
    second = tool.select_canary_families(structural)
    assert first == second
    assert [row["family_class"] for row in first["families"]] == [
        "local",
        "far",
    ]
    assert first["score_fields_read"] is False
    assert first["semantic_ranking_used"] is False
    assert first["unique_clip_count"] <= 4
    subset = tool.build_subset_structural(structural, first)
    assert subset["counts"] == {
        "families": 2,
        "local_families": 1,
        "far_families": 1,
        "target_clips": first["unique_clip_count"],
        "queries": 8,
    }


def test_real_bundle_selection_is_stable_and_plan_bound() -> None:
    tool = load_tool()
    structural = tool.parent.load_structural_bundle(ROOT)
    selection = tool.select_canary_families(structural)
    plan = tool.validate_plan(ROOT)
    assert plan["decision"] == tool.READY
    assert tool.plan_status(ROOT)["repair_status"] == (
        "P23_102_QUERY_AUTHORING_SEMANTIC_GATES_READY"
    )
    assert plan["selected_family_hashes"] == selection[
        "selected_family_hashes"
    ]
    assert plan["selected_family_keys"] == selection["selected_family_keys"]
    assert plan["unique_clip_count"] == selection["unique_clip_count"]
    assert plan["unique_clip_count"] <= 4
    assert plan["scope"]["real_canary_run_performed"] is False
    assert plan["scope"]["authorization_receipt_created"] is False
    assert plan["scope"]["retrieval_scoring_performed"] is False
    assert plan["historical_plan_pipeline_hash_current"] is False
    assert plan["old_authorization_receipts_valid"] is False


def test_authorization_binds_every_exact_input(tmp_path: Path) -> None:
    tool = load_tool()
    fingerprints = {
        "canary_config_sha256": "sha256:config",
        "selected_family_hashes": {
            "local": "sha256:local",
            "far": "sha256:far",
        },
        "main_pipeline_sha256": "sha256:main",
        "canary_pipeline_sha256": "sha256:canary",
        "bundle_file_hashes": {"family_registry.json": "sha256:bundle"},
        "model_hashes": {"authoring_omni": {"snapshot": "sha256:model"}},
        "media_sha256": "sha256:media",
    }
    receipt = {
        "schema_version": (
            "av-trace.p23-102-query-authoring-v2-canary-authorization/2.0"
        ),
        "canary_id": tool.CANARY_ID,
        "decision": "AUTHORIZED",
        "authorization_id": "auth-test-one-run",
        "authorized_at": "2026-10-15T00:00:00Z",
        "single_local_run": True,
        **fingerprints,
        "output_path": tool.DEFAULT_OUTPUT.as_posix(),
    }
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    assert tool.validate_authorization(
        tmp_path,
        path,
        fingerprints=fingerprints,
        output=tool.DEFAULT_OUTPUT,
    )["authorization_id"] == "auth-test-one-run"

    for field in (
        "canary_config_sha256",
        "selected_family_hashes",
        "main_pipeline_sha256",
        "canary_pipeline_sha256",
        "bundle_file_hashes",
        "model_hashes",
        "media_sha256",
        "output_path",
        "single_local_run",
    ):
        invalid = dict(receipt)
        invalid[field] = False if field == "single_local_run" else "tampered"
        path.write_text(json.dumps(invalid), encoding="utf-8")
        with pytest.raises(
            tool.CanaryError,
            match="CANARY_EXECUTION_AUTHORIZATION_SCOPE_MISMATCH",
        ):
            tool.validate_authorization(
                tmp_path,
                path,
                fingerprints=fingerprints,
                output=tool.DEFAULT_OUTPUT,
            )


def test_execute_requires_separate_authorization_before_run(
    tmp_path: Path,
) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(TOOL_PATH),
            "--execute",
            "--repo-root",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2
    assert (
        "CANARY_EXECUTION_REQUIRES_SEPARATE_AUTHORIZATION_RECEIPT"
        in completed.stderr
    )
    assert not (tmp_path / "data/restricted").exists()


def test_mocked_execute_seals_raw_outputs_runtime_and_no_scoring(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = load_tool()
    structural = synthetic_structural(tool)
    selection = tool.select_canary_families(structural)
    fingerprints = {
        "canary_config_sha256": "sha256:config",
        "selected_family_hashes": selection["selected_family_hashes"],
        "main_pipeline_sha256": "sha256:main",
        "canary_pipeline_sha256": "sha256:canary",
        "bundle_file_hashes": structural["file_hashes"],
        "model_hashes": {"mock": {"snapshot_content_sha256": "sha256:model"}},
        "media_sha256": "sha256:media",
    }
    monkeypatch.setattr(
        tool.parent,
        "load_structural_bundle",
        lambda root, bundle: structural,
    )
    monkeypatch.setattr(
        tool.parent,
        "preflight",
        lambda root, bundle, media: {"status": "READY", "failures": []},
    )
    monkeypatch.setattr(
        tool,
        "_input_fingerprints",
        lambda root, media, structural, selection: fingerprints,
    )

    receipt = {
        "schema_version": (
            "av-trace.p23-102-query-authoring-v2-canary-authorization/2.0"
        ),
        "canary_id": tool.CANARY_ID,
        "decision": "AUTHORIZED",
        "authorization_id": "mock-one-run",
        "authorized_at": "2026-10-15T00:00:00Z",
        "single_local_run": True,
        **fingerprints,
        "output_path": tool.DEFAULT_OUTPUT.as_posix(),
    }
    authorization = tmp_path / "authorization.json"
    authorization.write_text(json.dumps(receipt), encoding="utf-8")

    def mock_stage_runner(
        root,
        *,
        media,
        staging,
        subset,
        contract,
        stage_times,
    ):
        del root, media, contract
        stage_times.update(
            {
                "exact_clip_extraction_seconds": 0.01,
                "omni_authoring_seconds": 0.02,
                "whisper_leakage_audit_seconds": 0.03,
                "query_collision_audits_seconds": 0.04,
            }
        )
        tool.parent.atomic_json(
            staging / "target_manifest.json",
            {"targets": subset["targets"], "mock": True},
        )
        tool.parent.atomic_json(
            staging / "prompt_manifest.json", {"prompts": [], "mock": True}
        )
        tool.parent.atomic_jsonl(
            staging / "raw_attempts.jsonl",
            [
                {
                    "family_key": family["family_key"],
                    "raw_output": '{"mock":"raw model output"}',
                }
                for family in subset["families"]
            ],
        )
        tool.parent.atomic_json(
            staging / "asr_audit_inventory.json",
            {"rows": [{"raw_output": {"text": "mock whisper raw"}}]},
        )
        tool.parent.atomic_json(
            staging / "authored_queries.json",
            {
                "query_count": tool.EXPECTED_QUERY_COUNT,
                "queries": [{"query_key": f"q-{index}"} for index in range(8)],
                "retrieval_results": [],
                "scoring_results": [],
                "scientific_claims": [],
            },
        )
        tool.parent.atomic_json(
            staging / "audits.json",
            {
                "status": "PASS",
                "embedding_similarity": {
                    "target_embeddings_read": False,
                    "non_target_embeddings_read": False,
                },
            },
        )
        return {
            "authoring_model_calls": 2,
            "asr_model_calls": subset["counts"]["target_clips"],
            "target_clip_decodes": subset["counts"]["target_clips"],
        }

    seal = tool.execute(
        tmp_path,
        authorization=authorization,
        stage_runner=mock_stage_runner,
    )
    assert seal["status"] == (
        "SEALED_CANARY_AUTHORING_COMPLETE_SCORING_NOT_RUN"
    )
    output = tmp_path / tool.DEFAULT_OUTPUT
    validated = tool.validate_output(tmp_path)
    assert validated["passed"] is True
    assert validated["retrieval_scoring_executed"] is False
    runtime = json.loads(
        (output / "resource_runtime.json").read_text(encoding="utf-8")
    )
    assert runtime["peak_rss_bytes"] > 0
    assert runtime["wall_seconds"] >= 0
    assert runtime["authoring_model_calls"] == 2
    assert runtime["retrieval_scoring_executed"] is False
    assert "raw model output" in (
        output / "raw_attempts.jsonl"
    ).read_text(encoding="utf-8")
    assert "mock whisper raw" in (
        output / "asr_audit_inventory.json"
    ).read_text(encoding="utf-8")


def test_mocked_failure_installs_no_partial_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = load_tool()
    structural = synthetic_structural(tool)
    selection = tool.select_canary_families(structural)
    fingerprints = {
        "canary_config_sha256": "sha256:config",
        "selected_family_hashes": selection["selected_family_hashes"],
        "main_pipeline_sha256": "sha256:main",
        "canary_pipeline_sha256": "sha256:canary",
        "bundle_file_hashes": structural["file_hashes"],
        "model_hashes": {"mock": {}},
        "media_sha256": "sha256:media",
    }
    monkeypatch.setattr(
        tool.parent,
        "load_structural_bundle",
        lambda root, bundle: structural,
    )
    monkeypatch.setattr(
        tool.parent,
        "preflight",
        lambda root, bundle, media: {"status": "READY", "failures": []},
    )
    monkeypatch.setattr(
        tool,
        "_input_fingerprints",
        lambda root, media, structural, selection: fingerprints,
    )
    receipt = {
        "schema_version": (
            "av-trace.p23-102-query-authoring-v2-canary-authorization/2.0"
        ),
        "canary_id": tool.CANARY_ID,
        "decision": "AUTHORIZED",
        "authorization_id": "mock-failing-run",
        "authorized_at": "2026-10-15T00:00:00Z",
        "single_local_run": True,
        **fingerprints,
        "output_path": tool.DEFAULT_OUTPUT.as_posix(),
    }
    authorization = tmp_path / "authorization.json"
    authorization.write_text(json.dumps(receipt), encoding="utf-8")

    def fail_runner(*args, **kwargs):
        del args, kwargs
        raise tool.CanaryError("MOCK_AUDIT_FAIL_CLOSED")

    with pytest.raises(tool.CanaryError, match="MOCK_AUDIT_FAIL_CLOSED"):
        tool.execute(
            tmp_path,
            authorization=authorization,
            stage_runner=fail_runner,
        )
    output = tmp_path / tool.DEFAULT_OUTPUT
    assert not output.exists()
    assert not list(output.parent.glob(f".{output.name}.staging-*"))
    capsules = list(output.parent.glob(f"{output.name}.failure-*"))
    assert len(capsules) == 1
    failure = json.loads(
        (capsules[0] / "failure_capsule.json").read_text(encoding="utf-8")
    )
    assert failure["failure_error"] == "MOCK_AUDIT_FAIL_CLOSED"
    assert failure["ephemeral_clip_arrays_removed"] is True


def test_canary_uses_parent_semantic_gates_and_recovers_failure_counts(
    tmp_path: Path,
) -> None:
    tool = load_tool()
    assert tool.parent.SEMANTIC_GATES_READY == (
        "P23_102_QUERY_AUTHORING_SEMANTIC_GATES_READY"
    )
    staging = tmp_path / "staging"
    staging.mkdir()
    tool.parent.atomic_jsonl(
        staging / "raw_attempts.jsonl",
        [
            {"attempt_kind": "initial"},
            {"attempt_kind": "initial"},
            {"attempt_kind": "schema_only_repair"},
        ],
    )
    tool.parent.atomic_json(
        staging / "target_manifest.json",
        {"target_count": 2, "targets": [{}, {}]},
    )
    counts = tool.parent.retained_runtime_counts(staging, {})
    assert counts["authoring_model_calls"] == 3
    assert counts["initial_authoring_calls"] == 2
    assert counts["schema_only_repair_calls"] == 1
    assert counts["target_clip_decodes"] == 2
