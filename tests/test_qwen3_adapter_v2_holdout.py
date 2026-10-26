from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from pathlib import Path

import pytest

from av_trace_strong_baselines.contracts import FALLBACK_BINDINGS
from av_trace_strong_baselines.errors import StrongBaselineError
from av_trace_strong_baselines_v2.qwen3_suite_generator import (
    PROMPT_POLICY_SHA256,
    Qwen3FutureSealedSuiteGenerator,
)
from scripts.audit_qwen3_adapter_v2_holdout import (
    EXPECTED_FREEZE_LABEL,
    EXPECTED_SUITE_ID,
    audit,
)

ROOT = Path(__file__).resolve().parents[1]
RESTRICTED = (
    ROOT / "data/restricted/strong_baselines/qwen3_v2_holdout"
)
PUBLIC = (
    ROOT / "data/rehearsal_plan/qwen3_adapter_v2_holdout_public.json"
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_frozen_public_packet_schema_binding_and_composition() -> None:
    value = _load(PUBLIC)
    assert value["suite_id"] == EXPECTED_SUITE_ID
    assert value["freeze_label"] == EXPECTED_FREEZE_LABEL
    assert value["generated_date"] == "2026-10-08"
    assert value["execution_status"] == "SEALED_NOT_RUN"
    assert value["prompt_policy"]["sha256"] == PROMPT_POLICY_SHA256
    assert value["binding"]["controller"] == FALLBACK_BINDINGS[
        "controller"
    ].to_dict()
    assert value["binding"]["finalizer"] == FALLBACK_BINDINGS[
        "finalizer"
    ].to_dict()
    assert value["binding"]["same_exact_snapshot_required"] is True
    counts = Counter(case["case_type"] for case in value["cases"])
    assert counts == {
        "controller": 24,
        "finalizer": 16,
        "runtime_failure": 11,
    }
    assert Counter(
        case["stratum"]
        for case in value["cases"]
        if case["case_type"] == "controller"
    ) == {
        "route_vision": 3,
        "route_speech": 3,
        "route_ambient": 3,
        "observe_pointer": 3,
        "blocked_status": 3,
        "restoration_reacquire": 3,
        "no_trigger": 3,
        "finalize_ready": 3,
    }
    assert Counter(
        case["stratum"]
        for case in value["cases"]
        if case["case_type"] == "finalizer"
    ) == {
        "oracle_complete": 8,
        "restoration_complete": 4,
        "blocked_partial": 4,
    }


def test_private_targets_are_absent_from_the_public_packet() -> None:
    public = _load(PUBLIC)
    assert "private_labels" not in public
    rendered = PUBLIC.read_text(encoding="utf-8")
    for forbidden in (
        '"expected_action_index"',
        '"expected_evidence_state"',
        '"required_terms_by_claim"',
        '"accepted_support"',
        '"expected_inference_status"',
    ):
        assert forbidden not in rendered
    private_path = RESTRICTED / "private_labels.json"
    assert private_path.is_file()
    assert private_path.stat().st_mode & 0o077 == 0
    assert RESTRICTED.stat().st_mode & 0o077 == 0


def test_private_key_is_authenticated_without_parsing_targets() -> None:
    seal = _load(RESTRICTED / "seal.json")
    manifest = _load(RESTRICTED / "generation_manifest.json")
    private_path = RESTRICTED / "private_labels.json"
    record = seal["files"]["private_labels.json"]
    assert private_path.stat().st_size == record["bytes"]
    assert (
        "sha256:" + hashlib.sha256(private_path.read_bytes()).hexdigest()
        == record["sha256"]
    )
    assert (
        seal["semantic_hashes"]["private_labels"]
        == manifest["private_labels_sha256"]
    )
    assert manifest["private_target_manual_inspection"] is False


def test_suite_and_governance_seals_match_frozen_bytes() -> None:
    for seal_name in ("seal.json", "freeze_seal.json"):
        seal = _load(RESTRICTED / seal_name)
        for name, record in seal["files"].items():
            path = (
                RESTRICTED / name
                if seal_name == "seal.json"
                else ROOT / name
            )
            assert path.stat().st_size == record["bytes"]
            assert (
                "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
                == record["sha256"]
            )
    assert _load(RESTRICTED / "public_suite.json") == _load(PUBLIC)


def test_independent_audit_does_not_parse_private_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = Path.read_text

    def guarded_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if Path(path).name == "private_labels.json":
            raise AssertionError("independent audit parsed private targets")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    report = audit(RESTRICTED)
    assert report["status"] == "PASS"
    assert (
        report["private_target_policy"]["private_labels_loaded_or_parsed"]
        is False
    )
    assert (
        report["overlap_audit"][
            "case_exact_or_near_overlap_pairs_total"
        ]
        == 0
    )
    assert report["overlap_audit"]["exact_prompt_matches"] == 0
    assert report["overlap_audit"]["near_prompt_pairs"] == 0
    assert report["model_inference_executed"] is False
    assert report["qwen3_loaded_or_run"] is False


def test_generator_refuses_reuse_of_the_frozen_output_directory() -> None:
    with pytest.raises(
        StrongBaselineError,
        match="QWEN3_FUTURE_SUITE_OUTPUT_ALREADY_EXISTS",
    ):
        Qwen3FutureSealedSuiteGenerator(
            seed=(1 << 255) + 182,
            seed_recorded_at="2026-10-08T00:00:00+08:00",
            suite_id=EXPECTED_SUITE_ID,
            freeze_label=EXPECTED_FREEZE_LABEL,
        ).seal_to(RESTRICTED)


def test_runtime_and_coverage_aggregates_are_frozen() -> None:
    manifest = _load(RESTRICTED / "generation_manifest.json")
    aggregate = manifest["aggregate_composition"]
    assert aggregate["coverage_families"] == {
        "routing_controller_cases": 15,
        "state_controller_cases": 24,
        "terminal_controller_cases": 6,
        "restoration_cases": 7,
        "no_trigger_cases": 3,
        "oracle_finalizer_cases": 8,
        "partial_finalizer_cases": 4,
    }
    private = aggregate["private_label_aggregates"]
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


def test_no_qwen3_run_artifacts_exist_in_frozen_directory() -> None:
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
    assert _load(RESTRICTED / "generation_manifest.json")["model_used"] is False
    assert _load(RESTRICTED / "audit_report.json")[
        "qwen3_loaded_or_run"
    ] is False
    assert os.access(RESTRICTED / "private_labels.json", os.R_OK)
