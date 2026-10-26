from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from av_trace_strong_baselines_v2 import (
    AttemptKind,
    FactorStatus,
    ProjectionStatus,
)
from tools import qwen3_8b_acquisition as qwen


def plan() -> dict:
    return json.loads((ROOT / qwen.PLAN).read_text())


def smoke_factor_record() -> dict:
    raw = "{}"
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return {
        "raw_output": raw,
        "raw_output_with_special_tokens": raw,
        "raw_output_sha256": digest,
        "adapter_input": raw,
        "adapter_input_sha256": digest,
        "attempt_index": 1,
        "attempt_kind": AttemptKind.INITIAL.value,
    }


def test_plan_is_exact_minimal_and_bounded() -> None:
    value = plan()
    qwen.validate_plan(value)
    assert value["model"]["repo_id"] == qwen.REPO_ID
    assert value["model"]["revision"] == qwen.REVISION
    names = {item["path"] for item in value["model"]["allowlist"]}
    assert "merges.txt" not in names
    assert "vocab.json" not in names
    assert "tokenizer.json" in names
    assert {
        name for name in names if name.endswith(".safetensors")
    } == {
        f"model-{index:05d}-of-00005.safetensors"
        for index in range(1, 6)
    }
    assert (
        value["model"]["expected_payload_bytes"]
        < value["caps"]["selected_payload_bytes"]
    )


def test_plan_rejects_revision_drift() -> None:
    value = copy.deepcopy(plan())
    value["model"]["revision"] = "0" * 40
    with pytest.raises(qwen.AcquisitionError, match="IDENTITY"):
        qwen.validate_plan(value)


def test_plan_rejects_nonminimal_tokenizer_files() -> None:
    value = copy.deepcopy(plan())
    item = next(
        row for row in value["model"]["official_tree"]
        if row["path"] == "merges.txt"
    )
    item["selected_for_snapshot"] = True
    value["model"]["allowlist"].append(
        {
            key: item[key]
            for key in (
                "path",
                "expected_bytes",
                "git_oid",
                "lfs_sha256",
            )
        }
    )
    value["model"]["expected_payload_bytes"] += item["expected_bytes"]
    with pytest.raises(
        qwen.AcquisitionError,
        match="NONMINIMAL_TOKENIZER_FILES_SELECTED",
    ):
        qwen.validate_plan(value)


def test_exact_url_contains_full_revision_and_mirror() -> None:
    value = plan()
    url = qwen.exact_url(
        value["model"], "config.json", "https://hf-mirror.com"
    )
    assert url.startswith("https://hf-mirror.com/")
    assert f"/resolve/{qwen.REVISION}/" in url


def test_atomic_json_is_restricted(tmp_path: Path) -> None:
    output = tmp_path / "restricted/value.json"
    qwen.atomic_json(output, {"ok": True})
    assert os.stat(output).st_mode & 0o777 == 0o600


def test_network_guard_blocks_and_counts() -> None:
    with qwen.deny_network() as attempts, pytest.raises(
        RuntimeError, match="NETWORK_ACCESS_FORBIDDEN_DURING_CPU_CANARY"
    ):
        __import__("socket").socket()
    assert attempts["count"] == 1


def test_public_smoke_is_inline_fictional_and_factorized() -> None:
    cases = qwen.public_smoke_cases()
    assert [case["case_id"] for case in cases] == [
        "qwen3-acq-controller-001",
        "qwen3-acq-finalizer-001",
    ]
    assert [len(qwen._factor_specs(case)) for case in cases] == [2, 5]
    serialized = json.dumps(cases).lower()
    assert "scientific" not in serialized
    assert "sealed" not in serialized
    assert "octagonal" in serialized


def test_qwen_tool_wrapper_normalization_preserves_choice() -> None:
    raw = (
        '<tool_call>\n{"name":"select_action_00",'
        '"arguments":{}}\n</tool_call>'
    )
    normalized, kind = qwen.normalize_action_transport(raw)
    assert kind == "qwen_native_tool_call"
    assert json.loads(normalized) == {
        "function_name": "select_action_00",
        "arguments": {},
    }


def test_factor_outcome_constructs_initial_attempt_with_exact_bytes() -> None:
    case = qwen.public_smoke_cases()[0]
    adapter_input = (
        b'{"function_name":"select_action_00","arguments":{}}\n'
    )
    outcome = qwen._factor_outcome(
        case,
        "action_choice",
        adapter_input,
    )
    assert outcome.status is FactorStatus.VALID
    assert len(outcome.attempts) == 1
    assert outcome.attempts[0].attempt_index == 1
    assert outcome.attempts[0].kind is AttemptKind.INITIAL
    assert outcome.attempts[0].raw_output == adapter_input


def test_smoke_validation_allows_rejection_but_requires_valid_factors() -> None:
    factors = [smoke_factor_record() for _ in range(7)]
    smoke = {
        "status": "LOAD_SMOKE_COMPLETE",
        "competence_claimed": False,
        "sealed_suite_read": False,
        "scientific_source_read": False,
        "local_files_only": True,
        "trust_remote_code": False,
        "network_attempts": 0,
        "device": "cpu",
        "dtype": "torch.bfloat16",
        "config_model_type": "qwen3",
        "runtime": {"threads": 8},
        "raw_outputs_preserved": True,
        "schema_retries_used": 0,
        "semantic_repair": False,
        "factors": factors,
        "cases": [
            {
                "case_id": "qwen3-acq-controller-001",
                "projection_status": str(ProjectionStatus.REJECTED),
                "factor_outcomes": {
                    "action_choice": {
                        "status": str(FactorStatus.VALID),
                    },
                    "evidence_state": {
                        "status": str(FactorStatus.INVALID_OUTPUT),
                    },
                },
            },
            {
                "case_id": "qwen3-acq-finalizer-001",
                "projection_status": str(ProjectionStatus.NOT_RUN),
                "factor_outcomes": {
                    "disposition": {
                        "status": str(FactorStatus.VALID),
                    },
                    "answer_text": {
                        "status": str(FactorStatus.INVALID_OUTPUT),
                    },
                },
            },
        ],
    }
    qwen.validate_smoke(smoke)


def test_smoke_validation_rejects_zero_valid_factor_case() -> None:
    factors = [smoke_factor_record() for _ in range(7)]
    smoke = {
        "status": "LOAD_SMOKE_COMPLETE",
        "competence_claimed": False,
        "sealed_suite_read": False,
        "scientific_source_read": False,
        "local_files_only": True,
        "trust_remote_code": False,
        "network_attempts": 0,
        "device": "cpu",
        "dtype": "torch.bfloat16",
        "config_model_type": "qwen3",
        "runtime": {"threads": 8},
        "raw_outputs_preserved": True,
        "schema_retries_used": 0,
        "semantic_repair": False,
        "factors": factors,
        "cases": [
            {
                "case_id": "qwen3-acq-controller-001",
                "projection_status": str(ProjectionStatus.NOT_RUN),
                "factor_outcomes": {
                    "action_choice": {
                        "status": str(FactorStatus.INVALID_OUTPUT),
                    },
                },
            },
            {
                "case_id": "qwen3-acq-finalizer-001",
                "projection_status": str(ProjectionStatus.ACCEPTED),
                "factor_outcomes": {
                    "disposition": {
                        "status": str(FactorStatus.VALID),
                    },
                },
            },
        ],
    }
    with pytest.raises(qwen.AcquisitionError, match="NO_VALID"):
        qwen.validate_smoke(smoke)


def test_delivered_manifest_has_honest_terminal_decision() -> None:
    path = ROOT / qwen.MANIFEST
    if not path.exists():
        pytest.skip("Task179 acquisition manifest not written yet")
    manifest = json.loads(path.read_text())
    assert manifest["decision"] in {
        qwen.READY,
        qwen.REPAIR,
        qwen.NO_GO,
    }
    assert manifest["competence_claimed"] is False
    assert manifest["sealed_competence_suite_run"] is False
    assert manifest["scientific_sources_touched"] is False
    assert manifest["gpu_used"] is False
    assert manifest["unrelated_ray_or_h20_jobs_touched"] is False
    if manifest["decision"] == qwen.READY:
        assert manifest["model"]["snapshot_acquired"] is True
        assert manifest["model"]["snapshot_hash_verified"] is True
        qwen.validate_smoke(manifest["cpu_load_smoke"])
