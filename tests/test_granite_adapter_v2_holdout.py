from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from pathlib import Path

import pytest

from av_trace_strong_baselines.contracts import InferenceStatus
from av_trace_strong_baselines.errors import StrongBaselineError
from av_trace_strong_baselines.schemas import validate_evidence_state
from av_trace_strong_baselines_v2 import FutureSealedSuiteGenerator
from av_trace_strong_baselines_v2.suite_generator import (
    PRIVATE_LABEL_SCHEMA_VERSION,
    PROMPT_POLICY_SHA256,
)
from scripts.audit_granite_adapter_v2_holdout import (
    EXPECTED_FREEZE_LABEL,
    EXPECTED_SUITE_ID,
    audit,
)

ROOT = Path(__file__).resolve().parents[1]
RESTRICTED = (
    ROOT / "data/restricted/strong_baselines/granite_v2_holdout"
)
PUBLIC = (
    ROOT / "data/rehearsal_plan/granite_adapter_v2_holdout_public.json"
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_frozen_public_packet_schema_and_composition() -> None:
    value = _load(PUBLIC)
    assert value["suite_id"] == EXPECTED_SUITE_ID
    assert value["freeze_label"] == EXPECTED_FREEZE_LABEL
    assert value["generated_date"] == "2026-10-02"
    assert value["execution_status"] == "SEALED_NOT_RUN"
    assert value["prompt_policy"]["sha256"] == PROMPT_POLICY_SHA256
    counts = Counter(case["case_type"] for case in value["cases"])
    assert counts == {
        "controller": 24,
        "finalizer": 16,
        "runtime_failure": 11,
    }
    controller_strata = Counter(
        case["stratum"]
        for case in value["cases"]
        if case["case_type"] == "controller"
    )
    assert controller_strata == {
        "route_vision": 3,
        "route_speech": 3,
        "route_ambient": 3,
        "observe_pointer": 3,
        "blocked_status": 3,
        "restoration_reacquire": 3,
        "no_trigger": 3,
        "finalize_ready": 3,
    }
    finalizer_strata = Counter(
        case["stratum"]
        for case in value["cases"]
        if case["case_type"] == "finalizer"
    )
    assert finalizer_strata == {
        "oracle_complete": 8,
        "restoration_complete": 4,
        "blocked_partial": 4,
    }


def test_private_targets_are_restricted_and_absent_from_public_packet() -> None:
    assert "private_labels" not in _load(PUBLIC)
    private_path = RESTRICTED / "private_labels.json"
    assert private_path.is_file()
    assert private_path.stat().st_mode & 0o077 == 0
    assert RESTRICTED.stat().st_mode & 0o077 == 0
    rendered = PUBLIC.read_text(encoding="utf-8")
    for forbidden in (
        '"expected_action_index"',
        '"expected_evidence_state"',
        '"required_terms_by_claim"',
        '"accepted_support"',
        '"expected_inference_status"',
    ):
        assert forbidden not in rendered


def test_private_key_schema_is_validated_automatically_without_reporting_targets() -> None:
    public = _load(PUBLIC)
    private = _load(RESTRICTED / "private_labels.json")
    assert private["schema_version"] == PRIVATE_LABEL_SCHEMA_VERSION
    assert private["suite_id"] == EXPECTED_SUITE_ID
    assert private["seed"].bit_length() == 256
    cases = {case["case_id"]: case for case in public["cases"]}
    labels = private["labels"]
    assert set(labels) == set(cases)
    allowed_statuses = {str(status) for status in InferenceStatus}
    for case_id, case in cases.items():
        label = labels[case_id]
        public_input = case["public_input"]
        handle = public_input["public_claim_slots"][0]["claim_handle"]
        if case["case_type"] == "controller":
            assert set(label) == {
                "expected_action_index",
                "expected_evidence_state",
                "restoration_reacquisition",
                "no_trigger_control",
                "terminal",
            }
            index = label["expected_action_index"]
            assert isinstance(index, int)
            assert 0 <= index < len(public_input["action_menu"])
            validate_evidence_state(
                label["expected_evidence_state"],
                allowed_claim_handles=[handle],
            )
        elif case["case_type"] == "finalizer":
            assert label["answer_mode"] in {"answer", "abstain"}
            assert isinstance(label["required_terms_by_claim"], dict)
            assert isinstance(label["accepted_support"], dict)
            if label["answer_mode"] == "answer":
                assert set(label["required_terms_by_claim"]) == {handle}
                assert set(label["accepted_support"]) == {handle}
                observed_ids = {
                    row["observation_id"]
                    for row in public_input["observed_evidence"]
                }
                assert set(label["accepted_support"][handle]) <= observed_ids
            else:
                assert label["required_missing_modality"] in {
                    "vision",
                    "speech",
                    "ambient",
                }
                assert isinstance(label["required_missing_hop"], str)
                assert label["required_terms_by_claim"] == {}
                assert label["accepted_support"] == {}
        else:
            assert set(label) == {
                "expected_inference_status",
                "expected_model_called",
                "expected_final_answer",
                "fail_closed",
            }
            assert label["expected_inference_status"] in allowed_statuses
            assert isinstance(label["expected_model_called"], bool)
            assert label["expected_final_answer"] is None
            assert label["fail_closed"] is True


def test_seal_hashes_all_private_and_public_freeze_inputs() -> None:
    seal = _load(RESTRICTED / "seal.json")
    for name, record in seal["files"].items():
        path = RESTRICTED / name
        assert path.stat().st_size == record["bytes"]
        assert (
            "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
            == record["sha256"]
        )
    assert (
        _load(RESTRICTED / "public_suite.json")
        == _load(PUBLIC)
    )


def test_independent_audit_passes_without_loading_private_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = Path.read_text

    def guarded_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if Path(path).name == "private_labels.json":
            raise AssertionError("independent audit parsed evaluator-private key")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    report = audit(RESTRICTED)
    assert report["status"] == "PASS"
    assert report["private_target_policy"]["private_labels_loaded_or_parsed"] is False
    assert report["overlap_audit"]["exact_public_input_matches"] == 0
    assert report["overlap_audit"]["exact_question_matches"] == 0
    assert report["model_inference_executed"] is False


def test_generator_refuses_reuse_of_the_frozen_output_directory() -> None:
    private_stat = (RESTRICTED / "private_labels.json").stat()
    assert private_stat.st_size > 0
    with pytest.raises(
        StrongBaselineError,
        match="FUTURE_SUITE_OUTPUT_ALREADY_EXISTS",
    ):
        FutureSealedSuiteGenerator(
            seed=1 << 200,
            suite_id=EXPECTED_SUITE_ID,
            freeze_label=EXPECTED_FREEZE_LABEL,
        ).seal_to(RESTRICTED)


def test_runtime_fixtures_are_fail_closed_and_complete_via_aggregate() -> None:
    manifest = _load(RESTRICTED / "generation_manifest.json")
    private = manifest["aggregate_composition"]["private_label_aggregates"]
    assert private["runtime_expected_statuses"] == {
        "BUDGET_EXHAUSTED": 1,
        "INVALID_OUTPUT": 5,
        "OOM": 1,
        "PROCESS_FAILURE": 1,
        "PROVIDER_FAILURE": 1,
        "SNAPSHOT_MISMATCH": 1,
        "TIMEOUT": 1,
    }
    assert private["runtime_expected_model_called"] == {
        "false": 2,
        "true": 9,
    }
    public = _load(PUBLIC)
    fixtures = [
        case
        for case in public["cases"]
        if case["case_type"] == "runtime_failure"
    ]
    assert len(fixtures) == 11
    assert len({case["stratum"] for case in fixtures}) == 11
    assert all(
        "expected_" not in json.dumps(case, sort_keys=True)
        for case in fixtures
    )


def test_no_model_outputs_or_run_artifacts_exist_in_frozen_directory() -> None:
    names = {path.name for path in RESTRICTED.iterdir()}
    assert names == {
        "audit_report.json",
        "freeze_manifest.json",
        "freeze_seal.json",
        "generation_manifest.json",
        "private_labels.json",
        "prompt_policy.json",
        "public_suite.json",
        "seal.json",
    }
    for prohibited in (
        "submission.json",
        "raw_attempts.jsonl",
        "run_metadata.json",
        "evaluator_report.json",
    ):
        assert prohibited not in names
    assert _load(RESTRICTED / "generation_manifest.json")["model_used"] is False
    assert os.access(RESTRICTED / "private_labels.json", os.R_OK)
