"""Structural checks for the sealed Qwen3 adapter-v2 holdout run."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts import audit_qwen3_adapter_v2_holdout_run as audit
from tools import qwen3_adapter_v2_holdout as runner

ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = ROOT / runner.OUTPUT_DIR


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def test_sealed_qwen3_run_and_evaluation_are_complete() -> None:
    seal = runner.verify_run_seal(RUN_DIR)
    assert seal["state"] == "SEALED_BEFORE_PRIVATE_EVALUATION"

    submission = json.loads((RUN_DIR / "submission.json").read_text())
    metadata = json.loads((RUN_DIR / "run_metadata.json").read_text())
    evaluation = json.loads((RUN_DIR / "evaluator_report.json").read_text())
    component = json.loads((RUN_DIR / "component_audit.json").read_text())
    evaluation_seal = json.loads(
        (RUN_DIR / "evaluation_seal.json").read_text()
    )

    assert len(submission["results"]) == 51
    assert metadata["counts"]["completed"] == 51
    assert metadata["governance"]["one_authorized_full_suite_run_consumed"]
    assert metadata["governance"]["cpu_only"]
    assert metadata["governance"]["local_files_only"]
    assert metadata["governance"]["trust_remote_code"] is False
    assert metadata["runtime"]["network_attempts"] == 0
    assert metadata["runtime"]["cuda_available"] is False
    assert metadata["runtime"]["cuda_device_count"] == 0
    assert metadata["runtime"]["dtype"] == "torch.bfloat16"
    assert metadata["runtime"]["threads"] == 8
    assert evaluation["decision"] == "QWEN3_ADAPTER_V2_HOLDOUT_NO_GO"
    assert component["status"] == "PASS"
    assert component["frozen_evaluator_replay"][
        "byte_identical_ignoring_evaluation_timestamp"
    ]
    assert evaluation_seal["state"] == (
        "EVALUATED_AND_INDEPENDENTLY_AUDITED"
    )
    for name, record in evaluation_seal["files"].items():
        path = RUN_DIR / name
        assert path.stat().st_size == record["bytes"]
        assert _sha256(path) == record["sha256"]


def test_independent_audit_refuses_a_second_replay() -> None:
    try:
        audit.build_audit(ROOT, RUN_DIR)
    except audit.AuditError as exc:
        assert str(exc) in {
            "PRIVATE_EVALUATION_NOT_COMPLETE",
            "INDEPENDENT_AUDIT_ALREADY_EXISTS_DO_NOT_RERUN",
        }
    else:
        raise AssertionError("a consumed deterministic replay was rerun")
